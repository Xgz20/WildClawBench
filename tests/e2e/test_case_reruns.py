import copy
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from src.e2e.common import E2EError, atomic_json, file_sha256
from src.e2e.engine import run_batch
from src.e2e.packages import export_package
from src.e2e.protocol import execution_history, snapshot
from src.e2e.store import BatchStore
from tests.e2e import test_scheduler


class CaseRerunTests(unittest.TestCase):
    def test_public_cli_rerun_without_repo_root_can_cancel_before_dispatch(self):
        from src.e2e import cli
        workspace = self.root.parent / 'cli-workspace'
        (workspace / 'batches').mkdir(parents=True)
        moved = workspace / 'batches' / self.root.name
        self.root.rename(moved)
        self.root = moved
        self.store = BatchStore(moved)
        calls = len(self.fixture.provider.calls)
        output = io.StringIO()
        with patch('src.e2e.agentcube.AgentCubeConfig.load', return_value=self.fixture.config), contextlib.redirect_stdout(output):
            cli.main(['--api-version', '1', 'rerun-case', '--workspace-root', str(workspace),
                      '--batch-id', moved.name, '--unit-id', 'unit', '--task-id', 't0', '--run-index', '1',
                      '--request-id', 'public-cli-cancelled', '--cancel-before-dispatch'])
        envelope = json.loads(output.getvalue().strip().split('\n')[-1])
        self.assertEqual(envelope['type'], 'result')
        current = self.store.get('unit/run-0001/t0')
        self.assertEqual((current['phase'], current['execution_version']), ('CANCELLED', 2))
        self.assertEqual(len(self.fixture.provider.calls), calls)

    def setUp(self):
        self.fixture = test_scheduler.SchedulerTests()
        self.fixture.setUp()
        self.root = Path(self.fixture.temp.name) / "versioned"
        self.root.mkdir()
        self.manifest = copy.deepcopy(self.fixture.manifest)
        self.manifest["plan"].update(batch_id="versioned", execution_concurrency=1)
        self.manifest["tasks"] = self.manifest["tasks"][:2]
        first = self.manifest["units"][0]
        first.update(task_ids=["t0", "t1"], max_concurrency=1)
        second = dict(first, unit_id="other")
        self.manifest["units"].append(second)
        atomic_json(self.root / "batch.json", self.manifest)
        items = []
        for unit in ("unit", "other"):
            for task in ("t0", "t1"):
                for run in (1, 2, 3):
                    attempt = f"exec-{unit}-{task}-{run}"
                    items.append({"key": f"{unit}/run-{run:04d}/{task}", "unit_id": unit, "task_id": task,
                                  "run_index": run, "attempt_id": attempt,
                                  "execution_root": f"units/{unit}/runs/run-{run:04d}/tasks/{task}/executions/{attempt}"})
        self.store = BatchStore(self.root)
        self.store.initialize(self.manifest, items)
        self.execute()

    def tearDown(self):
        self.fixture.tearDown()

    def execute(self, rerun=None):
        return run_batch(self.root, self.fixture.config, driver_factory=self.fixture.factory, rerun_case=rerun)

    def test_one_round_keeps_other_cases_units_and_old_bytes(self):
        before = {row["key"]: row for row in self.store.rows()}
        key = "unit/run-0002/t0"
        old = before[key]
        seal = self.root / old["execution_root"] / "backups/execution-original.zip"
        checksum = file_sha256(seal)
        calls = len(self.fixture.provider.calls)
        request = {"unit_id": "unit", "task_id": "t0", "run_indices": [2], "request_id": "one-round",
                   "expected_attempts": {key: old["attempt_id"]}, "executor_revision": "fixed-reader"}
        self.execute(request)
        after = {row["key"]: row for row in self.store.rows()}
        self.assertEqual(len(self.fixture.provider.calls), calls + 1)
        self.assertEqual(len(after), 12)
        for other in before:
            if other != key:
                self.assertEqual(before[other], after[other])
        self.assertNotEqual(old["attempt_id"], after[key]["attempt_id"])
        self.assertEqual(after[key]["execution_version"], 2)
        self.assertEqual(file_sha256(seal), checksum)
        versions = execution_history(self.root, key)["versions"]
        self.assertEqual([row["execution_version"] for row in versions], [2, 1])
        self.assertEqual([row["is_final"] for row in versions], [True, False])
        self.execute(request)
        self.assertEqual(len(self.fixture.provider.calls), calls + 1)
        with self.assertRaisesRegex(E2EError, "VERSION_CONFLICT"):
            self.execute({**request, "request_id": "stale-new-request"})

    def test_whole_case_rerun_is_three_rounds_not_a_new_batch(self):
        before = {row["key"]: row["attempt_id"] for row in self.store.rows()}
        calls = len(self.fixture.provider.calls)
        self.execute({"unit_id": "unit", "task_id": "t1", "request_id": "whole-case"})
        self.assertEqual(len(self.fixture.provider.calls), calls + 3)
        changed = [row for row in self.store.rows() if before[row["key"]] != row["attempt_id"]]
        self.assertEqual({row["run_index"] for row in changed}, {1, 2, 3})
        self.assertEqual({row["task_id"] for row in changed}, {"t1"})
        self.assertEqual({row["unit_id"] for row in changed}, {"unit"})
        self.assertEqual(snapshot(self.root)["total"], 12)

    def test_failed_latest_never_falls_back_and_exports_history_only_when_selected(self):
        key = "unit/run-0001/t0"
        self.store.rerun_case("unit", "t0", "latest-failed", run_indices=[1])
        self.store.update(key, "FAILED", resource_held=False, error={"code": "fixture_framework_error"})
        current = next(row for row in snapshot(self.root)["executions"] if row["execution_key"] == key)
        self.assertEqual((current["stage"], current["execution_version"]), ("FAILED", 2))
        final = self.root / "final.zip"
        all_versions = self.root / "all.zip"
        export_package(self.root, final, keys=[key], include_unsealed=True)
        export_package(self.root, all_versions, keys=[key], include_unsealed=True, include_history=True)
        with zipfile.ZipFile(final) as archive:
            index = json.loads(archive.read("package-index.json"))
            self.assertEqual(index["version_policy"], "final-only")
            self.assertEqual(index["exported"], [])
            self.assertEqual(index["unavailable_executions"][0]["execution"]["attempt_id"], current["attempt_id"])
            self.assertEqual(index["unavailable_executions"][0]["reason"], 'EXECUTION_NOT_SEALED')
        with zipfile.ZipFile(all_versions) as archive:
            index = json.loads(archive.read("package-index.json"))
            self.assertEqual(index["version_policy"], "all")
            self.assertEqual(len(index["exported"]), 1)
            self.assertFalse(index["exported"][0]["execution"]["is_final"])
            self.assertIn(key, index["not_exported"])

    def test_unknown_round_or_active_resource_does_not_create_a_version(self):
        with self.assertRaisesRegex(E2EError, "ROUND_UNKNOWN"):
            self.store.rerun_case("unit", "t0", "unknown", run_indices=[4])
        key = "unit/run-0001/t0"
        self.store.update(key, "COMPLETED", resource_held=True)
        with self.assertRaisesRegex(E2EError, "REQUIRES_RELEASED"):
            self.store.rerun_case("unit", "t0", "held")
        self.assertEqual(len(self.store.versions(key)), 1)

    def test_queued_cancellation_retains_cancelled_new_version_without_dispatch(self):
        calls = len(self.fixture.provider.calls)
        key = "unit/run-0001/t0"
        old = self.store.get(key)
        run_batch(self.root, self.fixture.config, driver_factory=self.fixture.factory,
                  rerun_case={"unit_id": "unit", "task_id": "t0", "run_indices": [1], "request_id": "cancelled"},
                  cancel_before_dispatch=True)
        self.assertEqual(len(self.fixture.provider.calls), calls)
        current = self.store.get(key)
        self.assertEqual((current["phase"], current["execution_version"]), ("CANCELLED", 2))
        self.assertNotEqual(current["attempt_id"], old["attempt_id"])
