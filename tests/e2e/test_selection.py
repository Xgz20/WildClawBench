from pathlib import Path
import tempfile
import unittest

from src.e2e.common import E2EError, atomic_json, read_json
from src.e2e.selection import compose_results
from src.e2e.store import BatchStore


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.batch = Path(self.temp.name) / "batch"
        self.batch.mkdir()
        tasks = [{"task_id": task, "dataset": {"id": "general-custom70-v3", "digest": "a" * 64}} for task in ("t1", "t2")]
        units = [{"unit_id": unit, "scene": "general", "task_ids": [task["task_id"] for task in tasks]} for unit in ("u1", "u2")]
        manifest = {"schema": "wildclawbench.sandbox-batch/v1", "plan": {"batch_id": "batch", "runs": 2},
                    "tasks": tasks, "units": units}
        atomic_json(self.batch / "batch.json", manifest)
        self.items = [{"key": f"{unit['unit_id']}/run-{run:04d}/{task}", "unit_id": unit["unit_id"], "run_index": run,
                       "task_id": task, "attempt_id": f"exec-{unit['unit_id']}-{run}-{task}"}
                      for run in (1, 2) for unit in units for task in unit["task_ids"]]
        self.store = BatchStore(self.batch)
        self.store.initialize(manifest, self.items)

    def tearDown(self):
        self.temp.cleanup()

    def finish_failed(self):
        for item in self.items:
            self.store.update(item["key"], "FAILED", error={"code": "fixture_infrastructure_error"})

    def test_composition_preserves_failed_tasks_units_runs_and_order(self):
        self.finish_failed()
        result = compose_results(self.batch)
        self.assertEqual(result["task_count"], 8)
        self.assertEqual(result["status_counts"], {"unscored": 8})
        self.assertEqual([row["execution_key"] for row in result["tasks"]], [row["key"] for row in self.items])
        for unit in ("u1", "u2"):
            for run in (1, 2):
                submission = read_json(self.batch / f"units/{unit}/runs/run-{run:04d}/submission/submission.json")
                self.assertEqual(submission["task_ids"], ["t1", "t2"])
                self.assertTrue(all(row["score_status"] == "unscored" for row in submission["tasks"]))
                self.assertTrue(all(row["execution_status"] == "infrastructure_error" for row in submission["tasks"]))
        self.assertEqual(compose_results(self.batch), result)

    def test_active_scope_cannot_be_finalized(self):
        with self.assertRaisesRegex(E2EError, "SCOPE_NOT_TERMINAL"):
            compose_results(self.batch)

    def test_composed_submission_drift_is_rejected(self):
        self.finish_failed()
        result = compose_results(self.batch)
        path = self.batch / result["artifacts"][1]["path"]
        path.write_text("{}")
        with self.assertRaisesRegex(E2EError, "COMPOSED_SUBMISSION_DRIFT"):
            compose_results(self.batch)


if __name__ == "__main__":
    unittest.main()
