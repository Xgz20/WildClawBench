import json
from pathlib import Path
import tempfile
import unittest

from src.e2e.common import E2EError, atomic_json, read_json
from src.e2e.store import BatchStore, controller_lock, refresh_controller_heartbeat


class ControllerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = BatchStore(self.root)
        self.store.initialize({}, [{"key": "u/r/t", "unit_id": "u", "run_index": 1, "task_id": "t"}])

    def tearDown(self):
        self.temp.cleanup()

    def expire_pipeline_lease(self):
        with self.store.transaction() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='pipeline_owner_lease'").fetchone()
            lease = json.loads(row[0])
            lease.update(heartbeat_at="2000-01-01T00:00:00+00:00", lease_expires_at="2000-01-01T00:02:00+00:00")
            db.execute("UPDATE metadata SET value=? WHERE key='pipeline_owner_lease'", (json.dumps(lease),))

    def test_execution_heartbeat_is_owned_and_marked_released(self):
        with controller_lock(self.root) as owner:
            initial = read_json(self.root / "control/execution-owner.json")
            refresh_controller_heartbeat(self.root, owner)
            current = self.store.summary()["controllers"]["execution"]
            self.assertEqual(current["instance_id"], initial["instance_id"])
            self.assertNotEqual(current["heartbeat_at"], initial["heartbeat_at"])
            self.assertEqual(current["lease_status"], "fresh")
            with self.assertRaisesRegex(E2EError, "OWNER_MISMATCH"):
                refresh_controller_heartbeat(self.root, {**owner, "instance_id": "another-controller"})
        released = self.store.summary()["controllers"]["execution"]
        self.assertEqual(released["lease_status"], "released")
        self.assertEqual(released["released_at"], released["lease_expires_at"])

    def test_idle_owner_is_fenced_until_its_lease_expires(self):
        self.store.publish_ready("u/r/t", {"backup_sha256": "source"})
        self.store.pipeline_owner("first")
        with self.assertRaisesRegex(E2EError, "OWNER_CONFLICT"):
            self.store.pipeline_owner("second")
        self.expire_pipeline_lease()
        self.store.pipeline_owner("second")
        with self.assertRaisesRegex(E2EError, "OWNER_CONFLICT"):
            self.store.claim_score("first", 1, mode="streaming")
        claim = self.store.claim_score("second", 1, mode="streaming")
        self.assertEqual(claim["owner"], "second")

    def test_expiry_keeps_active_claim_and_requires_explicit_takeover(self):
        self.store.publish_ready("u/r/t", {"backup_sha256": "source"})
        self.store.pipeline_owner("first")
        claim = self.store.claim_score("first", 1, mode="streaming")
        self.store.score_update(claim["key"], claim["claim_id"], "RUNNING", orchestration={"thread_id": "original-thread"})
        self.expire_pipeline_lease()
        with self.assertRaisesRegex(E2EError, "OWNER_CONFLICT"):
            self.store.pipeline_owner("second")
        self.store.transfer_pipeline_owner("first", "second", "旧控制会话已停止，接续原评分线程")
        continued = self.store.scoring_rows()[0]
        self.assertEqual(continued["claim_id"], claim["claim_id"])
        self.assertEqual(continued["orchestration"]["thread_id"], "original-thread")
        self.assertTrue(continued["takeover_requires_reconciliation"])
        self.assertEqual(self.store.summary()["controllers"]["pipeline"]["lease_status"], "fresh")

    def test_old_controller_metadata_remains_readable_and_can_be_renewed(self):
        atomic_json(self.root / "control/execution-owner.json", {"pid": 123, "host": "legacy", "instance_id": "legacy"})
        with self.store.transaction() as db:
            db.execute("INSERT INTO metadata VALUES ('pipeline_owner','legacy')")
        before = self.store.summary()["controllers"]
        self.assertEqual(before["execution"]["lease_status"], "unknown")
        self.assertEqual(before["pipeline"]["lease_status"], "unknown")
        self.store.pipeline_owner("legacy")
        self.assertEqual(self.store.summary()["controllers"]["pipeline"]["lease_status"], "fresh")
