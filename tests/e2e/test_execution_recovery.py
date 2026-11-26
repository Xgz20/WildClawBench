from copy import deepcopy
import contextlib
import io
import json
from unittest.mock import patch

import pytest

from src.e2e.agentcube import PlatformError
from src.e2e.backend import AStudioSandboxDriver
from src.e2e.common import E2EError, file_sha256
from src.e2e.engine import run_batch
from src.e2e.protocol import snapshot
from src.e2e.recovery import SCHEMA, inspect_recovery, register_recovery
from src.e2e.store import BatchStore, controller_lock
from tests.e2e import test_scheduler as fixtures

FakeDriver = fixtures.FakeDriver


@pytest.fixture
def fixture():
    value = fixtures.SchedulerTests(); value.setUp()
    yield value
    value.tearDown()


def recovery_request(root):
    check = inspect_recovery(root)
    return {'schema': SCHEMA, 'recovery_id': 'upgrade-one', 'source_revision': 'b' * 40,
            'target_revision': check['target_revision'], 'manifest_sha256': check['basis']['manifest_sha256'],
            'basis_sha256': check['basis_sha256']}


def test_recovery_continues_same_attempt_and_pending_cases_without_repeating_successes(fixture):
    store = BatchStore(fixture.root)
    first = store.rows()[0]
    driver = fixture.factory(batch_root=fixture.root, store=store, item=first,
        task=fixture.manifest['tasks'][0], unit=fixture.manifest['units'][0], config=fixture.config, stop_event=None)
    original_outcome = driver.execute()
    original_bytes = (driver.staging / 'native/rollout-test.jsonl').read_bytes()
    jobs = {'task-run': {'job_id': 'original-job', 'command_sha256': 'fixed',
                          'result': {'exit_code': 0}, 'submission': 'confirmed'}}
    store.update(first['key'], 'NEEDS_ATTENTION', dispatch_armed_at='2026-11-26T00:00:00+00:00',
                 jobs=jobs, error={'message': 'TASK_NATIVE_BINDING_AMBIGUOUS'})
    run_batch(fixture.root, fixture.config, task_ids=['t1'], driver_factory=fixture.factory)
    completed = store.rows()[1]
    old_record = deepcopy(completed)
    old_archive = fixture.root / completed['execution_root'] / 'backups/execution-original.zip'
    old_sha = file_sha256(old_archive)
    parent_sha = file_sha256(fixture.root / 'batch.json')
    before = {row['key']: row['attempt_id'] for row in store.rows()}
    request = recovery_request(fixture.root)

    class Driver(FakeDriver):
        def execute(self):
            if self.item['key'] == first['key']:
                assert self.store.get(self.item['key'])['jobs'] == jobs
                return original_outcome
            return super().execute()

    calls_before = len(fixture.provider.calls)
    factory = lambda **kw: Driver(**kw, provider=fixture.provider)
    result = run_batch(fixture.root, fixture.config, recovery=request, driver_factory=factory)
    assert result['phase_counts'] == {'COMPLETED': 10}
    assert len(fixture.provider.calls) == calls_before + 8
    assert {row['key']: row['attempt_id'] for row in store.rows()} == before
    assert store.rows()[1] == old_record
    assert file_sha256(old_archive) == old_sha and file_sha256(fixture.root / 'batch.json') == parent_sha
    assert (fixture.root / first['execution_root'] / 'original/native/rollout-test.jsonl').read_bytes() == original_bytes
    assert store.get(first['key'])['jobs'] == jobs
    assert store.get(first['key'])['collector_revision'] == request['target_revision']
    assert store.rows()[2]['executor_revision'] == request['target_revision']
    assert len(store.versions(first['key'])) == 1
    run_batch(fixture.root, fixture.config, recovery=request, driver_factory=factory)
    assert len(fixture.provider.calls) == calls_before + 8
    assert sum(event['type'] == 'EXECUTION_RECOVERY_REGISTERED' for event in store.events()) == 1


def test_cached_native_job_is_read_without_repeating_dispatch():
    from unittest.mock import Mock
    from src.e2e.common import digest
    driver = object.__new__(AStudioSandboxDriver)
    driver.key = 'key'; driver.checkpoint = Mock(); driver.client = Mock(); driver.store = Mock()
    result = {'exit_code': 0}
    driver.store.get.return_value = {'jobs': {'task-run': {'command_sha256': digest('original command'), 'result': result}}}
    assert driver._job('task-run', 'original command') == result
    driver.client.submit_job.assert_not_called()
    driver.client.await_job.assert_not_called()


@pytest.mark.parametrize('change,error', [('state', 'STATE_DRIFT'), ('manifest', 'MANIFEST_DRIFT'), ('revision', 'REVISION_DRIFT')])
def test_recovery_rejects_changed_basis_without_mutating_attempts(fixture, change, error):
    store = BatchStore(fixture.root)
    request = recovery_request(fixture.root)
    if change == 'state':
        store.update(store.rows()[0]['key'], 'RESERVED')
    elif change == 'manifest':
        request['manifest_sha256'] = '0' * 64
    else:
        request['target_revision'] = '0' * 40
    before = store.rows()
    with controller_lock(fixture.root), pytest.raises(E2EError, match=error):
        register_recovery(fixture.root, request)
    assert store.rows() == before


def test_recovery_refuses_active_execution_controller(fixture):
    with controller_lock(fixture.root), pytest.raises(E2EError, match='CONTROLLER_ACTIVE'):
        inspect_recovery(fixture.root)


def test_recovery_checks_the_real_lock_even_if_a_lease_is_stale(fixture):
    from src.e2e.common import atomic_json
    with controller_lock(fixture.root), pytest.raises(E2EError, match='CONTROLLER_ACTIVE'):
        atomic_json(fixture.root / 'control/execution-owner.json', {'lease_expires_at': '2000-01-01T00:00:00+00:00'})
        inspect_recovery(fixture.root)


def test_recovery_check_public_cli_does_not_register_or_dispatch(fixture):
    from src.e2e.cli import main
    # Fixture directories are already workspace/batches/<id> in production;
    # point only the CLI's root resolver at the isolated test batch here.
    before = BatchStore(fixture.root).rows()
    output = io.StringIO()
    with patch('src.e2e.cli._batch_root', return_value=fixture.root), contextlib.redirect_stdout(output):
        assert main(['--api-version', '1', 'recovery-check', '--workspace-root', str(fixture.root.parent), '--batch-id', 'batch']) == 0
    result = json.loads(output.getvalue())
    assert result['data']['controller_idle']
    assert BatchStore(fixture.root).rows() == before
    assert fixture.provider.calls == []


@pytest.mark.parametrize('error', [PlatformError('CREATE_SESSION_HTTP_401: rejected'),
                                 PlatformError('quota', platform_code='USER_QUOTA_NOT_ACTIVE')])
def test_known_batch_wide_fault_stops_new_dispatches(fixture, error):
    fixture.manifest['plan']['execution_concurrency'] = 1
    fixture.manifest['units'][0]['max_concurrency'] = 1
    from src.e2e.common import atomic_json, digest
    atomic_json(fixture.root / 'batch.json', fixture.manifest)
    with BatchStore(fixture.root).transaction() as db:
        db.execute("UPDATE metadata SET value=? WHERE key='plan_sha256'", (digest(fixture.manifest),))

    class Driver(FakeDriver):
        def execute(self):
            raise error

        def salvage(self):
            return {'complete': True}

    result = run_batch(fixture.root, fixture.config, driver_factory=lambda **kw: Driver(**kw, provider=fixture.provider))
    assert result['phase_counts'] == {'FAILED': 1, 'PENDING': 9}
    assert result['executions'][0]['error']['fault_scope'] == 'batch'


def test_attention_is_an_automatic_terminal_but_keeps_physical_resources(fixture):
    class Driver(FakeDriver):
        def execute(self):
            if self.item['task_id'] == 't0':
                self.store.update(self.item['key'], 'COLLECTING', session_id='unknown-session', report={'status': 'completed'})
                raise E2EError('POSTPROCESSING_REQUIRES_RECONCILIATION')
            return super().execute()

    result = run_batch(fixture.root, fixture.config, driver_factory=lambda **kw: Driver(**kw, provider=fixture.provider))
    assert result['phase_counts'] == {'NEEDS_ATTENTION': 1, 'COMPLETED': 9}
    view = snapshot(fixture.root)
    assert view['terminal'] and view['finished'] == 10
    assert view['execution_resources_held'] == 0 and view['resource_held'] == 1
    assert view['attention_resources_held'] == 1
    assert not view['executions'][0]['exportable']
    assert view['executions'][0]['terminal']


def test_attention_does_not_make_a_running_batch_look_paused(fixture):
    store = BatchStore(fixture.root)
    store.update(store.rows()[0]['key'], 'NEEDS_ATTENTION', resource_held=True, session_id='preserved')
    with controller_lock(fixture.root):
        assert snapshot(fixture.root)['state'] == 'running'
    assert snapshot(fixture.root)['state'] == 'needs_attention'


def test_attention_is_unscored_without_launching_a_desktop_judge(fixture):
    from src.e2e.desktop_scoring import _job
    item = {**BatchStore(fixture.root).rows()[0], 'phase': 'NEEDS_ATTENTION', 'scene': 'web'}
    root = fixture.root / 'score-work'
    with patch('src.e2e.desktop_scoring.ScoringDriver') as driver:
        result = _job(fixture.root, item, {}, None, root, 'score-one', root / 'cancel.json')
    assert result['status'] == 'unscored' and result['total_score'] is None
    assert not result['agent_used']
    driver.assert_not_called()


@pytest.mark.parametrize('proof,released', [
    ({'confirmed': True, 'session_id': 'expired-session'}, True),
    ({'confirmed': True, 'session_id': 'another-session'}, False),
    ({'confirmed': False, 'session_id': 'expired-session'}, False),
])
def test_only_exact_absence_proof_releases_an_attention_resource(fixture, proof, released):
    from unittest.mock import Mock
    from src.e2e.engine import _reconcile_attention_resource
    store = BatchStore(fixture.root); row = store.rows()[0]
    store.update(row['key'], 'NEEDS_ATTENTION', resource_held=True, session_id='expired-session',
                 runtime=fixture.config.public())
    driver = Mock(); driver.config = fixture.config
    driver.client.confirm_session_absent.return_value = proof
    _reconcile_attention_resource(store, row['key'], driver)
    assert store.get(row['key'])['resource_held'] is (not released)
    assert store.get(row['key'])['phase'] == 'NEEDS_ATTENTION'


def test_attention_absence_check_never_uses_a_changed_account(fixture):
    from dataclasses import replace
    from unittest.mock import Mock
    from src.e2e.engine import _reconcile_attention_resource
    store = BatchStore(fixture.root); row = store.rows()[0]
    store.update(row['key'], 'NEEDS_ATTENTION', resource_held=True, session_id='original-session',
                 runtime=fixture.config.public())
    driver = Mock(); driver.config = replace(fixture.config, user_id='different-account')
    _reconcile_attention_resource(store, row['key'], driver)
    driver.client.confirm_session_absent.assert_not_called()
    assert store.get(row['key'])['resource_held']
