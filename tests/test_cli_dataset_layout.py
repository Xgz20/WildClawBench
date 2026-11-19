"""Run the actual CLI selection path up to the dispatch boundary."""

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eval import run_batch
from eval_general_e2e.datasets.layout import load_layout, workspace_for_task


class SelectionReady(Exception):
    pass


class CLIDatasetLayoutTests(unittest.TestCase):
    def select(self, *args):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as mocks:
            mocks.enter_context(patch("sys.argv", ["run_batch.py", *args]))
            mocks.enter_context(patch.object(run_batch, "OUTPUT_DIR", Path(temp)))
            mocks.enter_context(patch.object(run_batch, "attach_file_logging"))
            mocks.enter_context(patch.object(run_batch, "_build_agent_backend"))
            mocks.enter_context(patch.object(run_batch, "_prepare_model_limit_resolution"))
            mocks.enter_context(patch.object(run_batch, "_log_run_configuration",
                return_value={"invocation": {"id": "test", "started_at": "2026-11-19T00:00:00Z"}}))
            scope = mocks.enter_context(patch.object(run_batch, "_write_evaluation_scope", side_effect=SelectionReady))
            with self.assertRaises(SelectionReady):
                run_batch.main()
            return scope.call_args.args[1], scope.call_args.kwargs

    def test_task_id_and_legacy_path_select_the_same_current_task(self):
        old = "tasks/extension/01_Productivity_Flow/01_Productivity_Flow_task_001_expense_policy_check.md"
        paths = load_layout(run_batch.ROOT_DIR)["task_paths"]
        results = [self.select("--task", value)[0][0] for value in (old, paths[old], Path(old).stem)]
        self.assertTrue(all(r == results[0] for r in results))
        self.assertIn("/workspace/general/regression/", results[0]["workspace_path"])
        self.assertTrue((Path(results[0]["workspace_path"]) / "gt/expected.json").is_file())

    def test_legacy_category_filters_match_only_the_original_task_pools(self):
        tasks, scope = self.select("--category", "all", "--tag", "custom", "--exclude-tag", "ppt",
                                   "--exclude-tag", "web-site-gen")
        self.assertEqual(len(tasks), 60)
        self.assertEqual(scope["mode"], "category")
        self.assertTrue(all("/tasks/general/regression/" in task["file_path"] for task in tasks))
        web, _ = self.select("--category", "07_Website_Generation", "--tag", "custom")
        self.assertEqual(len(web), 40)
        self.assertTrue(all("/tasks/web/custom/" in task["file_path"] for task in web))
        work, _ = self.select("--category", "general/work/data-analysis")
        self.assertEqual(len(work), 66)
        self.assertEqual({task["category"] for task in work}, {"data-analysis"})

    def test_legacy_and_catalog_selectors_match_exact_frozen_membership(self):
        for dataset_id, alias, count in (
            ("general-custom60-v1", "general-regression", 60),
            ("general-custom70-v6", "general-work", 70),
        ):
            with self.subTest(dataset=dataset_id):
                manifest = json.loads((run_batch.ROOT_DIR / "eval_general_e2e/datasets/manifests"
                                       / f"{dataset_id}.json").read_text())
                legacy, scope = self.select("--dataset", dataset_id)
                current, _ = self.select("--dataset-id", alias, "--release-id", dataset_id)
                self.assertEqual(scope["mode"], "dataset")
                self.assertEqual(len(legacy), count)
                self.assertEqual([t["task_id"] for t in legacy], [t["task_id"] for t in current])
                self.assertEqual({t["task_id"] for t in current}, {t["task_id"] for t in manifest["tasks"]})
                self.assertTrue(all(t["dataset"]["digest"] == manifest["dataset_digest"] for t in legacy))
                self.assertTrue(all(t["dataset_selection"]["dataset_digest"] == manifest["dataset_digest"]
                                    for t in current))

    def test_upstream_materials_fall_back_to_existing_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = next((old, new) for old, new in load_layout(run_batch.ROOT_DIR)["workspace_paths"].items()
                            if new.startswith("workspace/general/wildclawbench/en/"))
            (root / "datasets").mkdir()
            (root / "datasets/layout.json").write_text(json.dumps({"workspace_paths": {old: new}}))
            (root / old).mkdir(parents=True)
            self.assertEqual(workspace_for_task(root, Path(new)), root / old)
            (root / new).mkdir(parents=True)
            self.assertEqual(workspace_for_task(root, Path(new)), root / new)
