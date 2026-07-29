from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook


REPORT_DIR = Path(__file__).resolve().parents[1]
MANIFEST_SCRIPT = REPORT_DIR / "skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py"
UTILS_SCRIPT = REPORT_DIR / "skills/low-score-analysis/scripts/utils.py"
EXCEL_SCRIPT = REPORT_DIR / "scripts/generate_eval_report.py"
VALIDITY_SCRIPT = REPORT_DIR / "skills/validate-eval-results/scripts/validate_eval_results.py"
AUDIT_SCRIPT = REPORT_DIR / "skills/audit-eval-report/scripts/audit_eval_report.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


manifest = load_module("analysis_manifest", MANIFEST_SCRIPT)
analysis_utils = load_module("analysis_utils", UTILS_SCRIPT)
excel_report = load_module("excel_report", EXCEL_SCRIPT)
validity_check = load_module("validity_check", VALIDITY_SCRIPT)
report_audit = load_module("report_audit", AUDIT_SCRIPT)


class AnalysisPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.round_dir = Path(self.temp_dir.name) / "round3"
        self.unit_dir = self.round_dir / "model-x" / "harness-y"
        self.suite_dir = self.unit_dir / "01_suite"
        self.paths = {}
        for task_id, score in (
            ("task_50", 0.5),
            ("task_70", 0.7),
            ("task_almost_full", 0.9996),
            ("task_float_edge", 0.9999999995),
            ("task_full", 1.0),
            ("task_unscored", None),
        ):
            run_dir = self.suite_dir / task_id / "run_001"
            run_dir.mkdir(parents=True)
            if score is not None:
                (run_dir / "score.json").write_text(
                    json.dumps({"overall_score": score, "check": score}), encoding="utf-8"
                )
            (run_dir / "execution_status.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (run_dir / "usage.json").write_text(
                json.dumps({"request_count": 1}), encoding="utf-8"
            )
            (run_dir / "chat_openclaw.jsonl").write_text("", encoding="utf-8")
            self.paths[task_id] = run_dir

        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        task_suite = self.tasks_dir / "01_suite"
        task_suite.mkdir(parents=True)
        for task_id in self.paths:
            (task_suite / f"{task_id}.md").write_text(
                "---\n"
                f"id: {task_id}\n"
                "name: Test task\n"
                "category: 01_suite\n"
                "difficulty: L2\n"
                "modality: pure-text\n"
                "timeout_seconds: 300\n"
                "grading_type: automated\n"
                "---\n\n## Prompt\nTest\n",
                encoding="utf-8",
            )

        self.records = manifest.scan_unit("model-x", "harness-y", self.unit_dir, None)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def selection(self, **overrides):
        values = {
            "select_all": False,
            "imperfect": False,
            "threshold": None,
            "score_min": None,
            "score_max": None,
            "task_ids": [],
            "task_paths": [],
        }
        values.update(overrides)
        return manifest.build_selection(**values)

    def selected_ids(self, selection, task_ids=None, task_paths=None):
        records = [dict(record) for record in self.records]
        selected = manifest.select_tasks(records, selection, task_ids or [], task_paths or [])
        return {item["task_id"] for item in selected}, selected

    def test_selection_modes_use_raw_score(self) -> None:
        ids, _ = self.selected_ids(self.selection())
        self.assertEqual(ids, {"task_50", "task_unscored"})

        ids, selected = self.selected_ids(self.selection(imperfect=True))
        self.assertEqual(ids, {"task_50", "task_70", "task_almost_full", "task_float_edge",
                               "task_unscored"})
        almost = next(item for item in selected if item["task_id"] == "task_almost_full")
        self.assertEqual(almost["score_pct"], 100.0)
        self.assertEqual(almost["analysis_type"], "failure")

        ids, selected = self.selected_ids(self.selection(select_all=True))
        self.assertEqual(ids, {record["task_id"] for record in self.records})
        full = next(item for item in selected if item["task_id"] == "task_full")
        self.assertEqual(full["analysis_type"], "success_control")

    def test_score_range_and_result_path_selection(self) -> None:
        selection = self.selection(score_min=60, score_max=80)
        self.assertEqual(selection["scope"], "gte60_lt80")
        ids, _ = self.selected_ids(selection)
        self.assertEqual(ids, {"task_70"})

        score_path = self.paths["task_70"] / "score.json"
        selection = self.selection(task_paths=[str(score_path)])
        ids, _ = self.selected_ids(selection, task_paths=[str(score_path)])
        self.assertEqual(ids, {"task_70"})
        self.assertEqual(manifest.find_unit_for_result_path(str(score_path)), self.unit_dir.resolve())

    def test_result_file_path_locks_the_selected_run(self) -> None:
        old_run = self.suite_dir / "task_70/run_000"
        old_run.mkdir()
        (old_run / "score.json").write_text(
            json.dumps({"overall_score": 0.65, "check": 0.65}), encoding="utf-8"
        )
        (old_run / "execution_status.json").write_text("{}", encoding="utf-8")
        records = manifest.apply_task_path_run_overrides(
            self.records, [str(old_run / "score.json")], None
        )
        record = next(item for item in records if item["task_id"] == "task_70")
        self.assertEqual(record["overall_score"], 0.65)
        self.assertEqual(Path(record["run_dir"]), old_run.resolve())

    def test_cli_places_manifest_in_round_workspace(self) -> None:
        result = subprocess.run(
            [sys.executable, str(MANIFEST_SCRIPT), "--result-root", str(self.unit_dir),
             "--threshold", "60", "--tasks-dir", str(Path(self.temp_dir.name) / "missing-tasks")],
            check=True,
            capture_output=True,
            text=True,
        )
        expected = self.round_dir / "report-workspace/_failed_tasks_model-x@harness-y__lt60.json"
        self.assertTrue(expected.is_file())
        self.assertFalse((self.unit_dir / "report-workspace").exists())
        workspace = self.round_dir.resolve() / "report-workspace"
        self.assertIn(f"WORKSPACE_DIR={workspace}", result.stdout)
        self.assertIn(f"ANALYSIS_PATH={workspace / 'analysis_model-x@harness-y__lt60.json'}",
                      result.stdout)

    def test_validity_cli_places_output_in_round_workspace(self) -> None:
        subprocess.run(
            [sys.executable, str(VALIDITY_SCRIPT), "--result-root", str(self.unit_dir),
             "--tasks-dir", str(self.tasks_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        expected = self.round_dir / "report-workspace/validity/eval_result_validity.json"
        self.assertTrue(expected.is_file())
        self.assertFalse((self.unit_dir / "report-workspace/validity").exists())
        self.assertEqual(
            validity_check.round_root_from_units(self.unit_dir, validity_check.discover_units(self.unit_dir)),
            self.round_dir.resolve(),
        )

    def test_validity_round_root_supports_three_level_layout(self) -> None:
        unit_dir = self.round_dir / "opencode" / "model-z" / "opencode"
        unit_dir.mkdir(parents=True)
        specs = [("model-z", "opencode", unit_dir)]
        self.assertEqual(
            validity_check.round_root_from_units(unit_dir, specs),
            self.round_dir.resolve(),
        )

    def test_validity_ignores_api_keywords_in_agent_log(self) -> None:
        run_dir = self.suite_dir / "task_50/run_001"
        (run_dir / "agent.log").write_text(
            'level=INFO message="task says rate limit and 500"\n'
            'level=ERROR small=true agent=title error="service unavailable"\n'
            'level=ERROR small=false agent=build error="HTTP 429 too many requests"\n',
            encoding="utf-8",
        )
        report = validity_check.scan_round(self.unit_dir, self.tasks_dir)
        ids = {item["id"] for item in report["findings"]}
        self.assertNotIn("MODEL_API_RATE_LIMIT", ids)
        self.assertNotIn("MODEL_API_SERVER_ERROR", ids)
        self.assertNotIn("AGENT_LOG_ERROR", ids)

    def test_validity_findings_redact_credentials(self) -> None:
        item = validity_check.finding(
            "TEST", "error",
            'request failed: AK="ak-ba7df6029dd8d8baae7b62983221a940" password=hunter2',
            evidence={"authorization": "Bearer secret-token-value"},
        )
        serialized = json.dumps(item)
        self.assertNotIn("ba7df6029dd8d8baae7b62983221a940", serialized)
        self.assertNotIn("hunter2", serialized)
        self.assertNotIn("secret-token-value", serialized)
        self.assertIn("REDACTED", serialized)

    def test_validity_gate_distinguishes_harness_outcomes_from_framework_errors(self) -> None:
        for item, attribution in (
            ({"id": "TASK_TIMED_OUT", "attribution": "model"}, "model"),
            ({"id": "TOOL_CALLS_ALL_REJECTED", "attribution": "model"}, "model"),
            ({"id": "EXECUTION_ERROR", "attribution": "harness"}, "harness"),
        ):
            item.update({"validity_impact": "none", "rerun_action": "do_not_rerun"})
            severity, actual_attribution, _ = validity_check.classify_run_anomaly(item, {})
            self.assertEqual(severity, "info")
            self.assertEqual(actual_attribution, attribution)

        severity, attribution, _ = validity_check.classify_run_anomaly(
            {"id": "EXECUTION_ERROR", "severity": "error",
             "attribution": "evaluation_framework", "validity_impact": "fail",
             "rerun_action": "required_after_fix"},
            {},
        )
        self.assertEqual(severity, "error")
        self.assertEqual(attribution, "evaluation_framework")

        severity, attribution, _ = validity_check.classify_run_anomaly(
            {"id": "EXECUTION_ERROR", "severity": "error"},
            {},
        )
        self.assertEqual(severity, "warning")
        self.assertEqual(attribution, "undetermined")

        severity, attribution, recommendation = validity_check.classify_run_anomaly(
            {
                "id": "MODEL_API_RATE_LIMIT",
                "severity": "warning",
                "attribution": "external_service",
                "validity_impact": "review",
                "rerun_action": "review_first",
            },
            {},
        )
        self.assertEqual(severity, "warning")
        self.assertEqual(attribution, "external_service")
        self.assertIn("人工归因", recommendation)

    def test_model_api_errors_across_units_do_not_become_common_mode_failure(self) -> None:
        result_root = Path(self.temp_dir.name) / "api-review-round"
        for model in ("model-a", "model-b"):
            run_dir = result_root / model / "harness-y/01_suite/task_api/run_001"
            run_dir.mkdir(parents=True)
            (run_dir / "execution_status.json").write_text(json.dumps({
                "status": "finished", "timed_out": False, "elapsed_time": 30,
                "model": model, "harness": "harness-y",
            }), encoding="utf-8")
            (run_dir / "usage.json").write_text(json.dumps({
                "request_count": 1, "total_tokens": 100,
            }), encoding="utf-8")
            (run_dir / "score.json").write_text(
                json.dumps({"overall_score": 0.5}), encoding="utf-8"
            )
            events = [{"type": "event", "payload": {"index": index}} for index in range(5)]
            (run_dir / "chat.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events), encoding="utf-8"
            )
            (run_dir / "runtime_events.jsonl").write_text(json.dumps({
                "stage": "model_inference", "model": model,
                "event_type": "request_failed", "http_status": 429,
            }) + "\n", encoding="utf-8")

        report = validity_check.scan_round(result_root, None)
        ids = [item["id"] for item in report["findings"]]
        self.assertEqual(ids.count("MODEL_API_RATE_LIMIT"), 2)
        self.assertNotIn("COMMON_MODE_ENV_FAILURE", ids)
        api_findings = [item for item in report["findings"]
                        if item["id"] == "MODEL_API_RATE_LIMIT"]
        self.assertTrue(all(item["severity"] == "warning" for item in api_findings))

    def test_scoped_batches_are_isolated_and_merge_without_overwrite(self) -> None:
        workspace = self.round_dir / "report-workspace"
        analysis_utils.save_batch_result(
            [{"task_id": "task_50", "result_analysis": "a", "root_cause_analysis": "b"}],
            workspace, "model-x@harness-y", 0, "lt60",
        )
        analysis_utils.save_batch_result(
            [{"task_id": "task_70", "result_analysis": "c", "root_cause_analysis": "d"}],
            workspace, "model-x@harness-y", 0, "gte60_lt80",
        )
        analysis_utils.save_batch_result(
            [{"task_id": "task_unscored", "result_analysis": "e", "root_cause_analysis": "f"}],
            workspace, "model-x@harness-y", 0, "lt60",
        )

        self.assertEqual(
            set(analysis_utils.load_completed_tasks(workspace, "model-x@harness-y", "lt60")),
            {"task_50", "task_unscored"},
        )
        self.assertEqual(
            set(analysis_utils.load_completed_tasks(workspace, "model-x@harness-y", "gte60_lt80")),
            {"task_70"},
        )
        final_path = analysis_utils.merge_all_batches(workspace, "model-x@harness-y", "lt60")
        self.assertEqual(final_path.name, "analysis_model-x@harness-y__lt60.json")

    def test_excel_loader_accepts_scoped_analysis_name(self) -> None:
        workspace = self.round_dir / "report-workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        path = workspace / "analysis_model-x@harness-y__lt60.json"
        path.write_text(json.dumps({
            "task_50": {"result_analysis": "结果", "root_cause_analysis": "根因"}
        }), encoding="utf-8")

        unit = type("Unit", (), {"unit": "model-x@harness-y"})()
        loaded = excel_report.load_analysis([str(path)], [unit])
        self.assertEqual(loaded["model-x@harness-y::task_50"]["result_analysis"], "结果")
        self.assertEqual(excel_report.round_root_from_unit_dir(self.unit_dir), self.round_dir.resolve())

        three_level_unit = self.round_dir / "opencode" / "model-z" / "opencode"
        three_level_unit.mkdir(parents=True)
        self.assertEqual(excel_report.round_root_from_unit_dir(three_level_unit), self.round_dir.resolve())

    def test_excel_cli_backfills_scoped_analysis_in_detail_sheet(self) -> None:
        workspace = self.round_dir / "report-workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        analysis_path = workspace / "analysis_model-x@harness-y__lt60.json"
        analysis_path.write_text(json.dumps({
            "task_50": {"result_analysis": "结果证据", "root_cause_analysis": "根因证据"}
        }), encoding="utf-8")

        subprocess.run(
            [sys.executable, str(EXCEL_SCRIPT), "--result-root", str(self.unit_dir),
             "--analysis", f"model-x@harness-y={analysis_path}",
             "--tasks-dir", str(Path(self.temp_dir.name) / "missing-tasks")],
            check=True,
            capture_output=True,
            text=True,
        )
        output_dir = self.round_dir / "report-workspace/output"
        workbooks = list(output_dir.glob("report_1units_*.xlsx"))
        self.assertEqual(len(workbooks), 1)
        workbook = load_workbook(workbooks[0], read_only=True)
        sheet = workbook["评分详情_model-x@harness-y"]
        headers = [cell.value for cell in sheet[1]]
        result_col = headers.index("结果分析") + 1
        root_col = headers.index("根因分析") + 1
        task_id_col = headers.index("用例ID") + 1
        row = next(row for row in range(2, sheet.max_row + 1)
                   if sheet.cell(row, task_id_col).value == "task_50")
        self.assertEqual(sheet.cell(row, result_col).value, "结果证据")
        self.assertEqual(sheet.cell(row, root_col).value, "根因证据")

    def generate_auditable_excel(self) -> Path:
        output_dir = self.round_dir / "audit-fixture-output"
        subprocess.run(
            [sys.executable, str(EXCEL_SCRIPT), "--result-root", str(self.unit_dir),
             "--tasks-dir", str(self.tasks_dir), "--output-dir", str(output_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        return next(output_dir.glob("report_1units_*.xlsx"))

    def test_audit_reconciles_generated_workbook(self) -> None:
        excel_path = self.generate_auditable_excel()
        report = report_audit.audit_report(self.unit_dir, excel_path, self.tasks_dir, None)
        self.assertFalse([item for item in report["findings"] if item["severity"] == "error"])
        self.assertEqual(report["verdict"], "REVIEW")  # 缺少可选 validity，仅需人工复核。

    def test_audit_detects_request_count_regression(self) -> None:
        excel_path = self.generate_auditable_excel()
        workbook = load_workbook(excel_path)
        sheet = workbook["总览"]
        headers = [cell.value for cell in sheet[1]]
        request_column = headers.index("总请求数") + 1
        sheet.cell(2, request_column).value = 999
        workbook.save(excel_path)

        report = report_audit.audit_report(self.unit_dir, excel_path, self.tasks_dir, None)
        errors = [item for item in report["findings"] if item["severity"] == "error"]
        self.assertTrue(any(item["id"] == "OVERVIEW_VALUE_MISMATCH" for item in errors))

    def test_audit_propagates_upstream_validity_failure(self) -> None:
        excel_path = self.generate_auditable_excel()
        validity_path = self.round_dir / "report-workspace/validity/eval_result_validity.json"
        validity_path.parent.mkdir(parents=True, exist_ok=True)
        validity_path.write_text(json.dumps({
            "verdict": "FAIL", "summary": {"errors": 1, "warnings": 0}
        }), encoding="utf-8")
        report = report_audit.audit_report(
            self.unit_dir, excel_path, self.tasks_dir, validity_path
        )
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(any(item["id"] == "UPSTREAM_VALIDITY_FAILED"
                            for item in report["findings"]))

    def test_difficulty_inversion_is_review_not_failure(self) -> None:
        units = {}
        for index in range(5):
            tasks = {}
            for task_index in range(3):
                tasks[f"easy_{task_index}"] = {"score": 0.2}
                tasks[f"hard_{task_index}"] = {"score": 0.8}
            units[f"model-{index}@harness"] = {"tasks": tasks}
        groups = {
            "L2": {f"easy_{index}" for index in range(3)},
            "L3": {f"hard_{index}" for index in range(3)},
        }
        findings = []
        report_audit.audit_difficulty_inversion(units, groups, findings)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "DIFFICULTY_INVERSION")
        self.assertEqual(findings[0]["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
