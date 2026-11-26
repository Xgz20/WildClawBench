import json
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from src.e2e.common import E2EError, atomic_json, digest
from src.e2e.engine import _failure, run_batch
from src.e2e.protocol import snapshot
from src.e2e.retention import preserve_failure, reap
from src.e2e.store import BatchStore
from tests.e2e import test_scheduler as fixtures


@pytest.fixture
def fixture():
    value = fixtures.SchedulerTests()
    value.setUp()
    value.manifest["plan"]["failure_retention_seconds"] = 1800
    atomic_json(value.root / "batch.json", value.manifest)
    with BatchStore(value.root).transaction() as db:
        db.execute("UPDATE metadata SET value=? WHERE key='plan_sha256'", (digest(value.manifest),))
    yield value
    value.tearDown()


def failed(fixture):
    store = BatchStore(fixture.root)
    row = store.rows()[0]
    store.update(row["key"], "RUNNING", resource_held=True, session_id="failed-session",
                 dispatch_armed_at="2026-11-25T00:00:00+00:00", runtime=fixture.config.public())
    driver = Mock()
    driver.config = fixture.config
    driver.root = fixture.root / row["execution_root"]
    driver.staging = driver.root / "staging"
    driver.salvage.return_value = {"complete": True}
    _failure(fixture.root, store, row, driver, E2EError("model HTTP429"))
    return store, row, driver


def test_failure_is_terminal_with_retained_vm_and_no_delete(fixture):
    store, row, driver = failed(fixture)
    current = store.get(row["key"])
    assert current["phase"] == "FAILED" and current["resource_held"]
    retention = current["sandbox_retention"]
    assert datetime.fromisoformat(retention["destroy_after"]) - datetime.fromisoformat(retention["retained_at"]) == timedelta(minutes=30)
    driver.client.delete_session.assert_not_called()
    public = next(value for value in snapshot(fixture.root)["executions"] if value["execution_key"] == row["key"])
    assert public["terminal"] and public["sandbox_retention"]["client_state"] == "stopped"
    assert "runtime" not in public["sandbox_retention"]
    assert store.summary()["execution_resources_held"] == 0
    assert store.summary()["retained_sandboxes_held"] == 1
    assert store.summary()["resource_held"] == 1


def test_retained_failure_does_not_block_other_execution_slots(fixture):
    fixture.manifest["plan"]["execution_concurrency"] = 2
    fixture.manifest["units"][0]["max_concurrency"] = 2
    atomic_json(fixture.root / "batch.json", fixture.manifest)
    with BatchStore(fixture.root).transaction() as db:
        db.execute("UPDATE metadata SET value=? WHERE key='plan_sha256'", (digest(fixture.manifest),))
    provider = fixture.provider
    provider.executing = provider.peak = 0
    class Driver(fixtures.FakeDriver):
        def execute(self):
            with provider.lock:
                provider.executing += 1
                provider.peak = max(provider.peak, provider.executing)
            try:
                if self.item["task_id"] == "t0":
                    self.store.update(self.item["key"], "RUNNING", session_id="failed-session",
                                      runtime=self.config.public(), dispatch_armed_at="2026-11-25T00:00:00+00:00")
                    raise E2EError("HTTP429")
                return super().execute()
            finally:
                with provider.lock:
                    provider.executing -= 1
        def salvage(self):
            return {"complete": True}
    result = run_batch(fixture.root, fixture.config, driver_factory=lambda **kw: Driver(**kw, provider=provider))
    assert result["phase_counts"] == {"FAILED": 1, "COMPLETED": 9}
    assert result["execution_resources_held"] == 0 and result["retained_sandboxes_held"] == 1
    assert provider.peak <= 2
    view = snapshot(fixture.root)
    assert view["terminal"] and view["state"] == "partial"
    assert view["resource_held"] == 1 and view["execution_resources_held"] == 0


@pytest.mark.parametrize('preserved', [True, False])
def test_completed_native_binding_rejection_seals_before_releasing_its_slot(fixture, preserved):
    fixture.manifest['plan']['execution_concurrency'] = 2
    fixture.manifest['units'][0]['max_concurrency'] = 2
    atomic_json(fixture.root / 'batch.json', fixture.manifest)
    store = BatchStore(fixture.root)
    with store.transaction() as db:
        db.execute("UPDATE metadata SET value=? WHERE key='plan_sha256'", (digest(fixture.manifest),))
    provider = fixture.provider
    provider.executing = provider.peak_after_retention = 0

    class Driver(fixtures.FakeDriver):
        def execute(self):
            with provider.lock:
                provider.executing += 1
                if self.store.retentions():
                    provider.peak_after_retention = max(provider.peak_after_retention, provider.executing)
            try:
                if self.item['task_id'] == 't0':
                    self.store.update(self.item['key'], 'COLLECTING', session_id='completed-session',
                        report={'status': 'completed'}, runtime=self.config.public(),
                        dispatch_armed_at='2026-11-25T00:00:00+00:00')
                    atomic_json(self.staging / 'metadata/report.json', {'status': 'completed'})
                    raise E2EError('TASK_NATIVE_BINDING_AMBIGUOUS: NATIVE_MCP_INVOCATION_MISMATCH')
                return super().execute()
            finally:
                with provider.lock:
                    provider.executing -= 1

        def salvage(self):
            return {'complete': preserved, 'components': {'process_cleanup': preserved}}

    result = run_batch(fixture.root, fixture.config, driver_factory=lambda **kw: Driver(**kw, provider=provider))
    row = store.rows()[0]
    assert row['error']['report_status'] == 'completed'
    assert row['error']['failure_stage'] == 'native_trace_validation'
    execution = fixture.root / row['execution_root']
    if preserved:
        assert result['phase_counts'] == {'FAILED': 1, 'COMPLETED': 9}
        assert result['execution_resources_held'] == 0 and result['retained_sandboxes_held'] == 1
        assert provider.peak_after_retention == 2
        assert row['sandbox_retention']['evidence_sealed'] and row['resource_held']
        assert (execution / 'original/metadata/report.json').is_file()
        assert not (execution / 'execution-ready.json').exists()
        # Rerun only this round with the new reader, retaining the failed attempt.
        old_attempt = row['attempt_id']
        store.rerun_case('unit', 't0', 'fixed-native-reader', run_indices=[1], executor_revision='fixed')
        assert store.rows()[0]['attempt_id'] != old_attempt
        assert store.versions(row['key'])[0]['attempt_id'] == old_attempt
    else:
        assert row['phase'] == 'NEEDS_ATTENTION' and row['resource_held']
        assert result['execution_resources_held'] == 1 and result['retained_sandboxes_held'] == 0
        assert not (execution / 'backups/backup-receipt.json').exists()
        assert result['phase_counts'].get('PENDING', 0) > 0
        with pytest.raises(E2EError, match='RERUN_REQUIRES_RELEASED'):
            store.rerun_case('unit', 't0', 'unsafe-rerun')


def test_restart_reaper_waits_until_deadline_and_does_not_inflate_duration(fixture):
    store, row, _ = failed(fixture)
    original = next(value for value in snapshot(fixture.root)["executions"] if value["execution_key"] == row["key"])
    deadline = datetime.fromisoformat(store.retentions()[0]["destroy_after"])
    client = Mock()
    client.delete_session.return_value = {"confirmed": True, "http_status": 200}
    factory = Mock(return_value=client)
    reap(fixture.root, fixture.config, now=deadline-timedelta(seconds=1), client_factory=factory)
    factory.assert_not_called()
    reap(fixture.root, fixture.config, now=deadline, client_factory=factory)
    client.delete_session.assert_called_once_with("failed-session")
    assert not BatchStore(fixture.root).get(row["key"])["resource_held"]
    again = next(value for value in snapshot(fixture.root)["executions"] if value["execution_key"] == row["key"])
    assert again["duration_seconds"] == original["duration_seconds"]
    reap(fixture.root, fixture.config, now=deadline+timedelta(seconds=60), client_factory=factory)
    assert client.delete_session.call_count == 1


def test_unconfirmed_delete_keeps_resource_and_retries_after_backoff(fixture):
    store, row, _ = failed(fixture)
    deadline = datetime.fromisoformat(store.retentions()[0]["destroy_after"])
    client = Mock()
    client.delete_session.side_effect = [{"confirmed": False, "http_status": 202},
                                        {"confirmed": True, "http_status": 200}]
    factory = Mock(return_value=client)
    reap(fixture.root, fixture.config, now=deadline, client_factory=factory)
    assert store.get(row["key"])["sandbox_retention"]["status"] == "release_pending"
    assert store.get(row["key"])["resource_held"]
    reap(fixture.root, fixture.config, now=deadline+timedelta(seconds=10), client_factory=factory)
    assert client.delete_session.call_count == 1
    reap(fixture.root, fixture.config, now=deadline+timedelta(seconds=30), client_factory=factory)
    assert not store.get(row["key"])["resource_held"]


def test_explicit_release_uses_attempt_identity_and_checks_account(fixture):
    store, row, _ = failed(fixture)
    with pytest.raises(E2EError, match="RETENTION_FORCE_REQUIRES_ATTEMPT"):
        reap(fixture.root, fixture.config, force=True)
    with pytest.raises(E2EError, match="RETAINED_ATTEMPT_UNKNOWN"):
        reap(fixture.root, fixture.config, attempt_id="other", force=True)
    from dataclasses import replace
    with pytest.raises(E2EError, match="ACCOUNT_MISMATCH"):
        reap(fixture.root, replace(fixture.config, user_id="other"), attempt_id=row["attempt_id"], force=True)
    client = Mock()
    client.delete_session.return_value = {"confirmed": True}
    reap(fixture.root, fixture.config, attempt_id=row["attempt_id"], force=True, client_factory=lambda _: client)
    assert store.retentions()[0]["status"] == "released"


def test_case_rerun_keeps_old_retention_and_release_does_not_touch_new_attempt(fixture):
    store, row, _ = failed(fixture)
    for other in store.rows()[1:]:
        store.update(other["key"], "CANCELLED", resource_held=False)
    store.rerun_case("unit", "t0", "rerun-one")
    fresh = store.get(row["key"])
    assert fresh["attempt_id"] != row["attempt_id"] and not fresh["resource_held"]
    assert store.summary()["retained_sandboxes_held"] == 1
    client = Mock()
    client.delete_session.return_value = {"confirmed": True}
    reap(fixture.root, fixture.config, attempt_id=row["attempt_id"], force=True, client_factory=lambda _: client)
    assert store.get(row["key"])["phase"] == "PENDING"
    assert not store.get_version(row["key"], row["attempt_id"])["resource_held"]


def test_cancel_does_not_retain_and_legacy_manifest_is_unchanged(fixture):
    store = BatchStore(fixture.root)
    row = store.rows()[0]
    store.update(row["key"], "RUNNING", resource_held=True, session_id="cancelled-session")
    driver = Mock(root=fixture.root / row["execution_root"], config=fixture.config)
    driver.staging = driver.root / "staging"
    driver.salvage.return_value = {"complete": True}
    driver.client.delete_session.return_value = {"confirmed": True}
    _failure(fixture.root, store, row, driver, E2EError("cancelled"), final_phase="CANCELLED")
    assert not store.retentions()
    assert store.get(row["key"])["phase"] == "CANCELLED"
    assert not store.get(row["key"])["resource_held"]


def test_corrupted_backup_prevents_retained_vm_deletion(fixture):
    store, row, _ = failed(fixture)
    archive = fixture.root / row["execution_root"] / "backups/execution-original.zip"
    archive.chmod(0o600)
    with archive.open("ab") as stream:
        stream.write(b"changed")
    client = Mock()
    reap(fixture.root, fixture.config, attempt_id=row["attempt_id"], force=True, client_factory=lambda _: client)
    client.delete_session.assert_not_called()
    assert store.get(row["key"])["sandbox_retention"]["status"] == "release_failed"
    assert store.get(row["key"])["resource_held"]
