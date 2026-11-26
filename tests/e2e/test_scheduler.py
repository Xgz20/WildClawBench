import base64
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from src.e2e.agentcube import AgentCubeConfig, PlatformError
from src.e2e.common import E2EError, atomic_json
from src.e2e.engine import _failure, cleanup_batch, run_batch, verify_ready
from src.e2e.store import BatchStore, refresh_controller_heartbeat
from src.e2e.trace import normalize_rollout


GUEST = r"C:\ProgramData\WGUI\workspace\project"


def native_fixture(prompt, session_id, turn_id):
    timestamp = "2026-11-04T01:00:00+00:00"
    data = [
        {"type": "session_meta", "payload": {"id": session_id, "cwd": GUEST}},
        {"type": "turn_context", "payload": {"turn_id": turn_id, "cwd": GUEST,
          "model": "builtin/" + base64.b64encode(b"spark-x2.6").decode().rstrip("="), "effort": "high"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": prompt}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "write", "call_id": "call-1", "arguments": '{"path":"answer.txt"}'}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": "written"}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"text": "done"}]}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 100, "output_tokens": 10, "cached_input_tokens": 50}}}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn_id, "last_agent_message": "done", "duration_ms": 1000}},
    ]
    return "\n".join(json.dumps({"timestamp": timestamp, **row}) for row in data) + "\n"


class Provider:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = set()
        self.max_active = 0
        self.calls = []
        self.retain_one = False


class FakeClient:
    def __init__(self, provider):
        self.provider = provider

    def close(self):
        pass

    def delete_session(self, sid):
        with self.provider.lock:
            if self.provider.retain_one and sid.endswith("t0-1"):
                return {"confirmed": False, "http_status": 202}
            self.provider.active.discard(sid)
        return {"confirmed": True, "http_status": 200}


class FakeDriver:
    def __init__(self, *, batch_root, store, item, task, unit, config, stop_event, provider):
        self.batch, self.store, self.item, self.task, self.unit, self.config = batch_root, store, item, task, unit, config
        self.root = batch_root / item["execution_root"]
        self.staging = self.root / "staging"
        self.staging.mkdir(parents=True, exist_ok=True)
        self.client = FakeClient(provider)
        self.provider = provider

    def preflight(self):
        pass

    def execute(self):
        sid = "session-" + self.item["task_id"] + "-" + str(self.item["run_index"])
        with self.provider.lock:
            self.provider.active.add(sid)
            self.provider.calls.append(sid)
            self.provider.max_active = max(self.provider.max_active, len(self.provider.active))
        self.store.update(self.item["key"], "CREATING", creation_intent_at="created", runtime=self.config.public())
        self.store.update(self.item["key"], "RUNNING", session_id=sid)
        time.sleep(0.025)
        identity = {"batch_id": self.batch.name + f"-r{self.item['run_index']:04d}", "unit_id": self.item["unit_id"],
                    "task_id": self.item["task_id"], "attempt_id": self.item["attempt_id"]}
        native = self.staging / "native/rollout-test.jsonl"
        native.parent.mkdir()
        native.write_text(native_fixture(self.task["prompt"], "native-" + sid, "turn-" + sid))
        report = {"schema_version": 2, "status": "completed", "usage": {"input_tokens": 100, "output_tokens": 10, "cache_tokens": 50}}
        binding = normalize_rollout(native, identity=identity, prompt=self.task["prompt"], guest_cwd=GUEST,
                                    requested_model="spark-x2.6", requested_effort="high", report=report)
        cleanup = {"schema": "wildclawbench.agentcube-process-cleanup/v1", "phase": "completed", "success": True,
                   "supported": True, "after": [], "quiet_observed_milliseconds": 5000}
        atomic_json(self.staging / "metadata/report.json", report)
        atomic_json(self.staging / "metadata/native-binding.json", {key: value for key, value in binding.items() if key != "events"})
        (self.staging / "collect/workspace").mkdir(parents=True)
        (self.staging / "collect/workspace/answer.txt").write_text("done")
        self.store.update(self.item["key"], "COLLECTING", report=report)
        return {"identity": identity, "binding": binding, "native_path": "native/rollout-test.jsonl",
                "report": report, "workspace": "collect/workspace", "cleanup": cleanup}


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "batch"
        self.root.mkdir()
        self.provider = Provider()
        tasks = [{"task_id": "t" + str(i), "prompt": "task " + str(i), "public_inventory": [],
                  "prompt_sha256": hashlib.sha256(("task " + str(i)).encode()).hexdigest()} for i in range(10)]
        unit = {"unit_id": "unit", "harness": "astronstudio", "backend": "agentcube", "model": "spark-x2.6",
                "reasoning_effort": "high", "max_concurrency": 3, "template": "winarena-pc-20261104-a", "task_ids": [t["task_id"] for t in tasks]}
        self.manifest = {"schema": "wildclawbench.sandbox-batch/v1", "plan": {"batch_id": "batch", "execution_concurrency": 3},
                         "units": [unit], "tasks": tasks}
        atomic_json(self.root / "batch.json", self.manifest)
        items = [{"key": f"unit/run-0001/t{i}", "unit_id": "unit", "run_index": 1, "task_id": "t" + str(i),
                  "attempt_id": "exec-" + str(i), "execution_root": f"units/unit/runs/run-0001/tasks/t{i}/executions/exec-{i}"} for i in range(10)]
        BatchStore(self.root).initialize(self.manifest, items)
        self.config = AgentCubeConfig(user_id="test", auth_token="not-a-real-credential")

    def tearDown(self):
        for path in self.root.rglob("*"):
            if path.is_dir():
                path.chmod(0o700)
        self.temp.cleanup()

    def test_failed_collection_retains_sandbox_until_preservation_is_complete(self):
        store = BatchStore(self.root)
        item = store.rows()[0]
        store.update(item["key"], "RUNNING", resource_held=True, session_id="existing-session", dispatch_armed_at="sent",
                     report={"status": "task_timeout"})
        driver = Mock()
        driver.root = self.root / item["execution_root"]
        driver.staging = driver.root / "staging"
        driver.config = self.config
        driver.salvage.return_value = {"complete": False, "components": {"collect": False}}
        _failure(self.root, store, item, driver, E2EError("task_timeout"))
        self.assertEqual(store.get(item["key"])["phase"], "NEEDS_ATTENTION")
        self.assertTrue(store.get(item["key"])["resource_held"])
        driver.client.delete_session.assert_not_called()
        driver.salvage.return_value = {"complete": True}
        driver.client.delete_session.return_value = {"confirmed": True}
        _failure(self.root, store, item, driver, E2EError("task_timeout"))
        self.assertEqual(store.get(item["key"])["phase"], "FAILED")
        self.assertFalse(store.get(item["key"])["resource_held"])
        self.assertEqual(store.get(item["key"])["preservation"], {"complete": True})
        self.assertIsNone(store.get(item["key"])["preservation_error"])
        driver.client.delete_session.assert_called_once_with("existing-session")
        self.assertTrue((driver.root / "backups/backup-receipt.json").is_file())

    def factory(self, **kwargs):
        return FakeDriver(**kwargs, provider=self.provider)

    def test_explicit_task_resume_preserves_other_attention_and_counts_its_resource(self):
        store = BatchStore(self.root)
        item = store.rows()[0]
        store.update(item['key'], 'NEEDS_ATTENTION', resource_held=True, session_id='preserved-session')
        self.provider.active.add('preserved-session')
        before = store.get(item['key'])
        result = run_batch(self.root, self.config, task_ids=['t1', 't2', 't3'], driver_factory=self.factory)
        self.assertEqual(store.get(item['key']), before)
        self.assertEqual({row['task_id'] for row in store.rows() if row['phase'] == 'COMPLETED'}, {'t1', 't2', 't3'})
        self.assertLessEqual(self.provider.max_active, 4)
        self.assertEqual(self.provider.active, {'preserved-session'})
        self.assertEqual(result['execution_resources_held'], 0)
        self.assertEqual(result['resource_held'], 1)
        self.assertEqual(len(result['executions']), 10)
        self.assertFalse(any('t0-' in call for call in self.provider.calls))

    def test_task_resume_rejects_unknown_scope_before_any_dispatch(self):
        with self.assertRaisesRegex(E2EError, 'TASK_RESUME_SELECTION_UNKNOWN'):
            run_batch(self.root, self.config, task_ids=['not-in-frozen-batch'], driver_factory=self.factory)
        self.assertEqual(self.provider.calls, [])

    def test_resume_sealed_failure_retries_release_without_recollecting_or_rerunning(self):
        store = BatchStore(self.root)
        item = store.rows()[0]
        for other in store.rows()[1:]:
            store.update(other["key"], "CANCELLED")
        store.update(item["key"], "RUNNING", resource_held=True, session_id="existing-session", dispatch_armed_at="sent",
                     creation_intent_at="created", runtime=self.config.public(), report={"status": "task_timeout"})
        driver = Mock()
        driver.root = self.root / item["execution_root"]
        driver.staging = driver.root / "staging"
        driver.config = self.config
        driver.salvage.return_value = {"complete": True}
        driver.client.delete_session.side_effect = PlatformError("release response lost", uncertain=True)
        _failure(self.root, store, item, driver, E2EError("task_timeout"))
        self.assertTrue((driver.root / "backups/backup-receipt.json").is_file())
        self.assertTrue(store.get(item["key"])["resource_held"])

        class ReleaseOnlyDriver(FakeDriver):
            def execute(self):
                raise AssertionError("sealed failures must retain the original execution")

            def salvage(self):
                raise AssertionError("sealed failures already contain the preserved evidence")

        def factory(**kwargs):
            return ReleaseOnlyDriver(**kwargs, provider=self.provider)

        summary = run_batch(self.root, self.config, driver_factory=factory)
        recovered = store.get(item["key"])
        self.assertEqual(recovered["phase"], "FAILED")
        self.assertFalse(recovered["resource_held"])
        self.assertEqual(recovered["error"]["message"], "task_timeout")
        self.assertEqual(summary["resource_held"], 0)
        self.assertEqual(store.scoring_rows(), [])

    def test_cleanup_retains_completed_product_when_collection_is_unfinished(self):
        store = BatchStore(self.root)
        item = store.rows()[0]
        store.update(item["key"], "NEEDS_ATTENTION", resource_held=True, session_id="existing-session",
                     runtime=self.config.public(), report={"status": "completed"})
        with patch("src.e2e.engine.AgentCubeClient") as client:
            with self.assertRaisesRegex(E2EError, "EXPLICIT_CANCEL"):
                cleanup_batch(self.root, self.config)
            client.assert_not_called()
        self.assertTrue(store.get(item["key"])["resource_held"])

    def test_ten_jobs_respect_three_sandbox_slots_until_cleanup(self):
        self.provider.retain_one = True
        summary = run_batch(self.root, self.config, driver_factory=self.factory)
        self.assertEqual(summary["resource_held"], 1)
        self.assertEqual(len(self.provider.calls), 10)
        self.assertLessEqual(self.provider.max_active, 3)
        self.assertEqual(len(summary["scoring"]), 10)
        self.provider.retain_one = False
        resumed = run_batch(self.root, self.config, driver_factory=self.factory)
        self.assertEqual(resumed["status"], "COMPLETED")
        self.assertEqual(len(self.provider.calls), 10)

    def test_executor_renews_heartbeat_while_preserving_remote_job_identity(self):
        with patch("src.e2e.engine.HEARTBEAT_INTERVAL_SECONDS", 0), patch(
                "src.e2e.engine.refresh_controller_heartbeat", wraps=refresh_controller_heartbeat) as renew:
            summary = run_batch(self.root, self.config, driver_factory=self.factory)
        self.assertEqual(summary["status"], "COMPLETED")
        self.assertGreater(renew.call_count, 10)
        self.assertEqual(len(self.provider.calls), 10)
        self.assertEqual(BatchStore(self.root).summary()["controllers"]["execution"]["lease_status"], "released")

    def test_ready_record_cannot_change_model_without_changing_original(self):
        summary = run_batch(self.root, self.config, driver_factory=self.factory)
        item = summary["executions"][0]
        path = self.root / item["execution_root"] / "execution-ready.json"
        path.chmod(0o600)
        ready = json.loads(path.read_text())
        ready["actual_model"] = "another-model"
        path.write_text(json.dumps(ready))
        with self.assertRaisesRegex(ValueError, "PROVENANCE_INVALID"):
            verify_ready(self.root, item, self.manifest)


if __name__ == "__main__":
    unittest.main()
