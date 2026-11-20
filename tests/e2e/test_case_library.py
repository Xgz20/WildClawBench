import tempfile
import unittest
from pathlib import Path

from src.case_catalog import current_cases, document, index, runnable
from src.e2e.preparation import _current_general, canonical_script
from src.e2e.protocol import resolve


REPO = Path(__file__).resolve().parents[2]


class CaseLibraryTests(unittest.TestCase):
    def test_localized_copy_is_display_only_and_invalid_beats_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "datasets").mkdir()
            (repo / "datasets/case-library.yaml").write_text(
                "scenarios: {general: 通用}\n"
                "datasets:\n"
                "  upstream:\n"
                "    name: WildClawBench\n"
                "    scene: general\n"
                "    task_root: tasks/general/upstream/en\n"
                "    display_root: tasks/general/upstream/cn\n"
                "    modes: [cli]\n",
                encoding="utf-8",
            )
            for lang, name in (("en", "English task"), ("cn", "中文题目")):
                root = repo / f"tasks/general/upstream/{lang}/01_Category"
                root.mkdir(parents=True)
                (root / "sample.md").write_text(
                    f"---\nid: sample\nname: {name}\ntags: [draft]\n---\n## Prompt\n{name}\n",
                    encoding="utf-8",
                )
                (root / "invalid.md").write_text(
                    "---\nid: invalid\nname: 无效题\ntags: [draft, invalid]\n---\n", encoding="utf-8",
                )
            group = index(repo)["datasets"][0]
            self.assertEqual(group["draft_count"], 1)
            self.assertEqual([row["name"] for row in group["cases"]], ["中文题目"])
            self.assertIn("中文题目", document(repo, "upstream", "sample")["content"])
            self.assertIn("/en/", current_cases(repo, "upstream")[0]["task_path"])
            self.assertFalse(runnable(group["cases"][0]["tags"]))
            self.assertTrue(runnable(group["cases"][0]["tags"], True))
            self.assertFalse(runnable(["invalid", "draft"], True))

    def test_formal_version_and_working_subset_are_distinct(self):
        working = index(REPO, "general-work")["datasets"][0]
        frozen = index(REPO, "general-work", "general-custom70-v6")["datasets"][0]
        self.assertGreater(working["task_count"], len(frozen["cases"]))
        self.assertEqual(len(frozen["cases"]), 70)
        selection = {"task_ids": [frozen["cases"][0]["task_id"]]}
        web = canonical_script(REPO, "web-e2e", "prepare-web-e2e-workspaces", "prepare_web_e2e_workspaces.py")
        _, _, manifest = _current_general(REPO, "general-work", selection, web)
        self.assertEqual(manifest["dataset_id"], "general-work-working")
        self.assertEqual(manifest["task_count"], 1)
        self.assertNotEqual(manifest["dataset_digest"], frozen["releases"][0]["digest"])

    def test_web_library_rejects_case_from_other_web_dataset(self):
        task = current_cases(REPO, "web-artifactsbench")[0]
        plan = {
            "batch_id": "test-case-library",
            "selection": {"scenario": "web", "library_dataset": "web-custom", "task_ids": [task["task_id"]]},
            "units": [{"harness": "astronstudio", "model": "spark-x2.6"}],
        }
        with self.assertRaisesRegex(ValueError, "TASK_IDS_UNKNOWN"):
            resolve(REPO, plan)
