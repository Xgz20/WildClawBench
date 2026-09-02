from __future__ import annotations

import csv
import json
import shutil
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
CENSUS_TASK = (
    ROOT
    / "tasks/extension/04_Search_Retrieval"
    / "04_Search_Retrieval_task_007_census_province_change.md"
)
CENSUS_GT = (
    ROOT
    / "workspace/extension/04_Search_Retrieval"
    / "task_007_census_province_change/gt/expected.json"
)
HOLIDAY_TASK = (
    ROOT
    / "tasks/extension/01_Productivity_Flow"
    / "01_Productivity_Flow_task_006_holiday_calendar.md"
)
HOLIDAY_GT = (
    ROOT
    / "workspace/extension/01_Productivity_Flow"
    / "task_006_holiday_calendar/gt/expected.json"
)
VENDOR_GT = (
    ROOT
    / "workspace/extension/03_Social_Interaction"
    / "task_010_vendor_delay_stakeholder_comms/gt/expected.json"
)
VENDOR_WORKSPACE = VENDOR_GT.parent.parent
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

    def test_census_accepts_official_province_suffixes(self) -> None:
        expected = json.loads(CENSUS_GT.read_text(encoding="utf-8"))
        rows = [
            {**row, "province": f"{row['province']}省"}
            for row in expected["rows"]
        ]

        score = self._grade_census(rows)

        self.assertEqual(score["official_sources"], 1.0)
        self.assertEqual(score["population_values"], 1.0)
        self.assertEqual(score["change_calculations"], 1.0)
        self.assertEqual(score["structured_delivery"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_holiday_accepts_joint_name_order_and_delimiters(self) -> None:
        expected = json.loads(HOLIDAY_GT.read_text(encoding="utf-8"))
        rows = []
        for row in expected["rows"]:
            if row["holiday_name"] == "国庆节、中秋节":
                name = (
                    "中秋节、国庆节"
                    if row["type"] == "workday"
                    else "国庆节/中秋节"
                )
                rows.append({**row, "holiday_name": name})
            else:
                rows.append(dict(row))

        score = self._grade_holiday(rows)

        self.assertEqual(score["holiday_rows_correct"], 1.0)
        self.assertEqual(score["makeup_workdays_correct"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_holiday_does_not_accept_status_text_as_name(self) -> None:
        expected = json.loads(HOLIDAY_GT.read_text(encoding="utf-8"))
        rows = [
            {
                **row,
                "holiday_name": (
                    f"{row['holiday_name']}调休上班"
                    if row["type"] == "workday"
                    else row["holiday_name"]
                ),
            }
            for row in expected["rows"]
        ]

        score = self._grade_holiday(rows)

        self.assertLess(score["makeup_workdays_correct"], 1.0)
        self.assertLess(score["overall_score"], 1.0)

    def test_vendor_rich_nested_plan_keeps_business_credit(self) -> None:
        plan = {
            "purchase_order_id": "PO-8841",
            "source_timeline": {
                "batches": [
                    {
                        "batch": "first_batch",
                        "quantity": 600,
                        "ship_date": "2026-10-10",
                        "estimated_arrival": "2026-10-13",
                    },
                    {
                        "batch": "remaining_batch",
                        "quantity": 600,
                        "ship_window": "2026-10-19 to 2026-10-21",
                        "arrival_date": None,
                        "arrival_committed": False,
                    },
                ],
                "inventory": {
                    "on_hand_units": 240,
                    "usable_launch_units": 120,
                    "reserved_support_units": 120,
                    "qa_duration_calendar_days_after_arrival": 2,
                },
                "milestone_requirements": [
                    {"milestone_id": "pilot", "cumulative_units_required": 300},
                    {"milestone_id": "regional_launch", "cumulative_units_required": 800},
                    {"milestone_id": "general_availability", "cumulative_units_required": 1200},
                ],
            },
            "recommended_options": [
                {"option_id": "reduced_pilot_existing_inventory", "selected": True},
                {"option_id": "expedite_first_600", "selected": True},
                {"option_id": "alternate_supplier_200", "selected": True},
                {
                    "option_id": "borrow_support_inventory",
                    "selected": False,
                    "reason": "forbidden",
                },
            ],
            "total_incremental_cost_cny": 13900,
            "available_by_regional_launch": {
                "total_qa_cleared_units": 920,
                "required": 800,
                "conditional": True,
            },
            "required_approvals": [
                {"role": "Program Director", "status": "pending"},
                {"approver": "CFO", "status": "pending"},
                {"approver": "Release Manager", "status": "blocked"},
            ],
            "trigger_conditions": [
                {
                    "condition": "First batch misses ship date 2026-10-10",
                    "action": "escalate",
                },
                {
                    "condition": "First batch does not arrive by estimated arrival 2026-10-13",
                    "action": "escalate",
                },
                {
                    "condition": "QA not completed for first batch by 2026-10-15",
                    "action": "escalate",
                },
                {
                    "condition": "Remaining batch has no committed arrival by 2026-10-16",
                    "action": "escalate",
                },
            ],
            "milestones": [
                {
                    "milestone_id": "pilot",
                    "date": "2026-10-12",
                    "status": "reduced_pending_approval",
                    "available_units": 120,
                    "note": "extra explanation",
                },
                {
                    "milestone_id": "regional_launch",
                    "date": "2026-10-16",
                    "status": "conditional",
                    "available_units": 920,
                    "required_units": 800,
                },
                {
                    "milestone_id": "general_availability",
                    "date": "2026-10-23",
                    "status": "cannot_commit",
                    "available_units": 920,
                    "required_units": 1200,
                },
            ],
        }

        score = self._grade_vendor(plan)

        self.assertEqual(score["source_timeline_and_quantities"], 1.0)
        self.assertEqual(score["critical_path_impact"], 1.0)
        self.assertEqual(score["contingency_math_and_constraints"], 1.0)
        self.assertEqual(score["structured_delivery"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_vendor_numeric_batch_map_and_demand_alias_keeps_timeline_credit(self) -> None:
        expected = json.loads(VENDOR_GT.read_text(encoding="utf-8"))
        plan = {key: expected[key] for key in expected["plan_fields"]}
        plan["source_timeline"] = {
            "vendor_batches": {
                "batch_1": {
                    "quantity": 600,
                    "ship_date": "2026-10-10",
                    "estimated_arrival": "2026-10-13",
                },
                "batch_2": {
                    "quantity": 600,
                    "ship_window_start": "2026-10-19",
                    "ship_window_end": "2026-10-21",
                    "arrival_committed": False,
                },
            },
            "inventory": {
                "usable_launch_units": 120,
                "reserved_support_units": 120,
                "qa_duration_calendar_days": 2,
            },
            "milestone_demands": [
                {"milestone_id": "pilot", "units_required": 300},
                {"milestone_id": "regional_launch", "units_required": 800},
                {"milestone_id": "general_availability", "units_required": 1200},
            ],
        }
        plan["milestones"] = [
            {
                "milestone_id": "pilot",
                "date": "2026-10-12",
                "status": "conditional_on_program_director_approval",
                "available_units": 120,
            },
            {
                "milestone_id": "regional_launch",
                "date": "2026-10-16",
                "status": "conditional_on_approvals_and_first_batch_arrival",
                "available_units": 920,
            },
            {
                "milestone_id": "general_availability",
                "date": "2026-10-23",
                "status": "uncertain_pending_second_batch_arrival",
                "available_units": "dependent_on_second_batch",
            },
        ]

        score = self._grade_vendor(plan)

        self.assertEqual(score["source_timeline_and_quantities"], 1.0)

    def test_vendor_latest_update_record_keeps_flat_batch_timeline_credit(self) -> None:
        expected = json.loads(VENDOR_GT.read_text(encoding="utf-8"))
        plan = {key: expected[key] for key in expected["plan_fields"]}
        plan["source_timeline"] = {
            "vendor_batches": [
                {
                    "batch": "latest_written_update",
                    "first_batch_quantity": 600,
                    "first_batch_ship_date": "2026-10-10",
                    "first_batch_estimated_arrival": "2026-10-13",
                    "remaining_quantity": 600,
                    "remaining_ship_window_start": "2026-10-19",
                    "remaining_ship_window_end": "2026-10-21",
                    "remaining_arrival_date": None,
                }
            ],
            "inventory": {
                "usable_launch_units": 120,
                "reserved_support_units": 120,
                "qa_duration_calendar_days_after_arrival": 2,
            },
            "qa_duration_calendar_days": 2,
            "milestone_requirements": expected["source_timeline"]["milestone_requirements"],
        }

        score = self._grade_vendor(plan)

        self.assertEqual(score["source_timeline_and_quantities"], 1.0)

    def test_vendor_missing_remaining_arrival_is_not_credited(self) -> None:
        expected = json.loads(VENDOR_GT.read_text(encoding="utf-8"))
        plan = {key: expected[key] for key in expected["plan_fields"]}
        plan["source_timeline"] = dict(plan["source_timeline"])
        plan["source_timeline"].pop("remaining_arrival_date")

        score = self._grade_vendor(plan)

        self.assertLess(score["source_timeline_and_quantities"], 1.0)

    def test_vendor_selected_support_inventory_still_loses_constraint_credit(self) -> None:
        expected = json.loads(VENDOR_GT.read_text(encoding="utf-8"))
        plan = {key: expected[key] for key in expected["plan_fields"]}
        plan["recommended_options"] = list(expected["recommended_options"]) + [
            "borrow_support_inventory"
        ]

        score = self._grade_vendor(plan)

        self.assertLess(score["contingency_math_and_constraints"], 1.0)

    def test_vendor_trigger_conditions_do_not_cross_credit_between_entries(self) -> None:
        expected = json.loads(VENDOR_GT.read_text(encoding="utf-8"))
        plan = {key: expected[key] for key in expected["plan_fields"]}
        plan["trigger_conditions"] = [
            "First batch ship date is 2026-10-10.",
            "Remaining batch has no committed arrival by 2026-10-16.",
        ]

        score = self._grade_vendor(plan)

        self.assertLess(score["contingency_math_and_constraints"], 1.0)

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

    def _grade_vendor(self, plan: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gt").mkdir()
            (root / "results").mkdir()
            workspace = VENDOR_WORKSPACE
            (root / "gt/expected.json").write_text(
                VENDOR_GT.read_text(encoding="utf-8"), encoding="utf-8"
            )
            for source in (workspace / "exec").iterdir():
                if source.is_file():
                    shutil.copy2(source, root / source.name)
            (root / "results/impact_plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for name in json.loads(VENDOR_GT.read_text(encoding="utf-8"))["result_files"]:
                if name != "impact_plan.json":
                    (root / "results" / name).write_text("draft", encoding="utf-8")
            return load_grader(VENDOR_TASK)(workspace_path=str(root))

    def _grade_census(self, rows: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gt").mkdir()
            (root / "results").mkdir()
            expected = json.loads(CENSUS_GT.read_text(encoding="utf-8"))
            (root / "gt/expected.json").write_text(
                CENSUS_GT.read_text(encoding="utf-8"), encoding="utf-8"
            )
            columns = [
                "province",
                "population_2010",
                "population_2020",
                "absolute_change",
                "percent_change",
            ]
            with (root / "results/province_change.csv").open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            (root / "results/calculation_note.md").write_text(
                "第六次和第七次全国人口普查。\n"
                + "\n".join(expected["source_urls"]),
                encoding="utf-8",
            )

            return load_grader(CENSUS_TASK)(workspace_path=str(root))

    def _grade_holiday(self, rows: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gt").mkdir()
            (root / "results").mkdir()
            (root / "gt/expected.json").write_text(
                HOLIDAY_GT.read_text(encoding="utf-8"), encoding="utf-8"
            )
            columns = ["date", "type", "holiday_name", "source_document"]
            with (root / "results/holidays.csv").open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            (root / "results/staffing_note.md").write_text(
                "排班提醒", encoding="utf-8"
            )

            return load_grader(HOLIDAY_TASK)(workspace_path=str(root))

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
