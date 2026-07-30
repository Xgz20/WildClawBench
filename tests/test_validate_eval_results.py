from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "tools/report/skills/validate-eval-results/scripts/validate_eval_results.py"
)
SPEC = importlib.util.spec_from_file_location("validate_eval_results", SCRIPT)
assert SPEC and SPEC.loader
validate_eval_results = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_eval_results)


class ExpectedTasksTest(unittest.TestCase):
    def test_official_and_extension_tasks_are_combined(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tasks = Path(temp)
            official = tasks / "01_Productivity_Flow"
            extension = tasks / "extension/01_Productivity_Flow"
            official.mkdir(parents=True)
            extension.mkdir(parents=True)
            (official / "01_Productivity_Flow_task_1.md").write_text("official")
            (extension / "01_Productivity_Flow_task_001.md").write_text("extension")

            result = validate_eval_results.expected_tasks(tasks)

            self.assertEqual(result["01_Productivity_Flow"], {
                "01_Productivity_Flow_task_1",
                "01_Productivity_Flow_task_001",
            })

    def test_gitignored_local_extension_task_is_excluded(self) -> None:
        repo_tasks = Path(__file__).resolve().parents[1] / "tasks"

        result = validate_eval_results.expected_tasks(repo_tasks)

        self.assertNotIn(
            "04_Search_Retrieval_task_101_csv_gdp_regions",
            result["04_Search_Retrieval"],
        )


if __name__ == "__main__":
    unittest.main()
