from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.utils.task_parser import parse_task_md


ROOT = Path(__file__).resolve().parents[1]
RFC_TASK = (
    ROOT
    / "tasks/extension/04_Search_Retrieval"
    / "04_Search_Retrieval_task_006_rfc_http_obsolescence.md"
)
PENSION_TASK = (
    ROOT
    / "tasks/extension/04_Search_Retrieval"
    / "04_Search_Retrieval_task_012_personal_pension_policy_timeline.md"
)
VENDOR_TASK = (
    ROOT
    / "tasks/extension/03_Social_Interaction"
    / "03_Social_Interaction_task_010_vendor_delay_stakeholder_comms.md"
)
PENSION_GT = (
    ROOT
    / "workspace/extension/04_Search_Retrieval"
    / "task_012_personal_pension_policy_timeline/gt/expected.json"
)


def load_grader(task_file: Path):
    namespace: dict = {}
    exec(parse_task_md(task_file)["automated_checks"], namespace)
    return namespace["grade"]


class ExtensionSemanticGraderTest(unittest.TestCase):
    def test_rfc_prompt_publishes_machine_readable_scope_values(self) -> None:
        prompt = parse_task_md(RFC_TASK)["prompt"]

        self.assertIn("HTTP semantics", prompt)
        self.assertIn("HTTP/1.1 message syntax", prompt)

    def test_vendor_prompt_publishes_milestone_status_enum(self) -> None:
        prompt = parse_task_md(VENDOR_TASK)["prompt"]

        for value in (
            "reduced_to_120",
            "conditional_pending_approvals",
            "date_not_committed",
        ):
            self.assertIn(value, prompt)

    def test_pension_coverage_accepts_equivalent_natural_language(self) -> None:
        rows = json.loads(PENSION_GT.read_text(encoding="utf-8"))["rows"]
        equivalents = {
            "institutional_framework": "确立个人养老金制度的基本框架",
            "implementation_measures": "细化账户、业务流程和管理规范，文件发布后即施行",
            "pilot_in_36_cities_or_regions": "率先在36个城市和地区开展试点",
            "national_implementation": "面向全国正式落地实施",
        }

        score = self._grade_pension(rows, equivalents)

        self.assertEqual(score["coverage_and_effect"], 1.0)

    def test_pension_coverage_rejects_missing_or_negated_facts(self) -> None:
        rows = json.loads(PENSION_GT.read_text(encoding="utf-8"))["rows"]
        incomplete = {
            "institutional_framework": "建立个人养老金制度框架",
            "implementation_measures": "规定账户与业务流程",
            "pilot_in_36_cities_or_regions": "未在36个城市先行试点",
            "national_implementation": "尚未全国实施",
        }

        score = self._grade_pension(rows, incomplete)

        self.assertEqual(score["coverage_and_effect"], 0.25)

    def _grade_pension(self, rows: list[dict], coverage: dict[str, str]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gt").mkdir()
            (root / "results").mkdir()
            (root / "gt/expected.json").write_text(
                PENSION_GT.read_text(encoding="utf-8"), encoding="utf-8"
            )
            columns = [
                "stage",
                "document_number",
                "document_date",
                "published_or_effective_date",
                "coverage",
                "source_url",
            ]
            with (root / "results/pension_timeline.csv").open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                for row in rows:
                    writer.writerow({**row, "coverage": coverage[row["stage"]]})
            (root / "results/answer.md").write_text("答案", encoding="utf-8")

            return load_grader(PENSION_TASK)(workspace_path=str(root))


if __name__ == "__main__":
    unittest.main()
