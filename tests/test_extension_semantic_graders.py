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
APPLE_TASK = (
    ROOT
    / "tasks/extension/04_Search_Retrieval"
    / "04_Search_Retrieval_task_005_apple_2023_segment_revenue.md"
)
MOUTAI_TASK = (
    ROOT
    / "tasks/extension/04_Search_Retrieval"
    / "04_Search_Retrieval_task_009_sse_annual_report_metrics.md"
)
APPLE_GT = (
    ROOT
    / "workspace/extension/04_Search_Retrieval"
    / "task_005_apple_2023_segment_revenue/gt/expected.json"
)
MOUTAI_GT = (
    ROOT
    / "workspace/extension/04_Search_Retrieval"
    / "task_009_sse_annual_report_metrics/gt/expected.json"
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

    def test_financial_retrieval_prompts_publish_json_value_contracts(self) -> None:
        apple_prompt = parse_task_md(APPLE_TASK)["prompt"]
        moutai_prompt = parse_task_md(MOUTAI_TASK)["prompt"]

        self.assertIn("`fiscal_year`使用JSON整数`2023`", apple_prompt)
        self.assertIn('`security_code`使用JSON字符串`"600519"`', moutai_prompt)
        self.assertIn('`unit`写为`"人民币元"`', moutai_prompt)
        self.assertIn("可使用这两个字段名或实际金额", moutai_prompt)

    def test_apple_year_type_error_only_reduces_structured_delivery(self) -> None:
        answer = {
            "fiscal_year": "2023",
            "unit": "USD millions",
            "greater_china_net_sales": 72559,
            "total_net_sales": 383285,
            "share_percent": 18.9,
            "formula": "72559 / 383285 * 100 = 18.9308, rounded to 18.9",
            "accession": "0000320193-23-000106",
            "source_table": "Net Sales by Reportable Segment",
        }

        score = self._grade_json_task(
            APPLE_TASK,
            APPLE_GT,
            "apple_sales_check.json",
            "brief_correction.md",
            answer,
        )

        self.assertEqual(score["filing_identity"], 1.0)
        self.assertEqual(score["sales_values"], 1.0)
        self.assertEqual(score["share_calculation"], 1.0)
        self.assertEqual(score["structured_delivery"], 0.75)
        self.assertEqual(score["overall_score"], 0.95)

        canonical = {**answer, "fiscal_year": 2023}
        canonical_score = self._grade_json_task(
            APPLE_TASK,
            APPLE_GT,
            "apple_sales_check.json",
            "brief_correction.md",
            canonical,
        )
        self.assertEqual(canonical_score["overall_score"], 1.0)

    def test_moutai_identifier_type_error_only_reduces_delivery(self) -> None:
        answer = {
            "security_code": 600519,
            "report_year": 2023,
            "disclosure_date": "2024-04-03",
            "unit": "人民币元",
            "total_operating_revenue": 150560330316.45,
            "net_profit_attributable_to_listed_company_shareholders": 74734071550.75,
            "research_and_development_expense": 157371873.01,
            "ratio_formula": (
                "research_and_development_expense / "
                "total_operating_revenue * 100"
            ),
            "ratio_percent": 0.10,
            "source_url": (
                "https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/"
                "2024-04-03/600519_20240403_W0YD.pdf"
            ),
        }

        score = self._grade_json_task(
            MOUTAI_TASK,
            MOUTAI_GT,
            "moutai_metrics.json",
            "metric_note.md",
            answer,
        )

        self.assertEqual(score["report_identity"], 1.0)
        self.assertEqual(score["reported_metrics"], 1.0)
        self.assertEqual(score["ratio_calculation"], 1.0)
        self.assertEqual(score["structured_delivery"], 0.8)
        self.assertEqual(score["overall_score"], 0.96)

        canonical = {**answer, "security_code": "600519"}
        canonical_score = self._grade_json_task(
            MOUTAI_TASK,
            MOUTAI_GT,
            "moutai_metrics.json",
            "metric_note.md",
            canonical,
        )
        self.assertEqual(canonical_score["overall_score"], 1.0)

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

    def _grade_json_task(
        self,
        task_file: Path,
        gt_file: Path,
        json_name: str,
        note_name: str,
        answer: dict,
    ) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gt").mkdir()
            (root / "results").mkdir()
            (root / "gt/expected.json").write_text(
                gt_file.read_text(encoding="utf-8"), encoding="utf-8"
            )
            (root / "results" / json_name).write_text(
                json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (root / "results" / note_name).write_text("核对说明", encoding="utf-8")

            return load_grader(task_file)(workspace_path=str(root))


if __name__ == "__main__":
    unittest.main()
