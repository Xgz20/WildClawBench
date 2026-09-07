import json
import importlib.util
from pathlib import Path
from unittest.mock import patch

from src.utils.anomalies import RULESET_VERSION, SCHEMA_VERSION
from tools.report.lib.eval_dataset.contracts import PASS, Report
from tools.report.lib.eval_dataset.reporting import _markdown

_SPEC = importlib.util.spec_from_file_location(
    "audit_eval_dataset_quality_script",
    Path(__file__).resolve().parents[1] / "skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
main = _MODULE.main


def _anomalies(verdict="PASS", items=None):
    items = list(items or [])
    return {
        "schema_version": SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "validity_verdict": verdict,
        "is_anomalous": bool(items),
        "has_error": verdict == "FAIL",
        "has_validity_failure": verdict == "FAIL",
        "has_model_or_harness_issue": any(
            item.get("attribution") in {"model", "harness"} for item in items
        ),
        "needs_review": verdict == "REVIEW",
        "needs_rerun": any(
            item.get("rerun_action") == "required_after_fix" for item in items
        ),
        "items": items,
    }


def _write_run(
    root: Path,
    task_id: str,
    *,
    model: str = "model-a",
    harness: str = "harness-a",
    score: float = 0.5,
) -> Path:
    run = root / model / harness / "01_Category" / task_id / "run-1"
    run.mkdir(parents=True)
    (run / "score.json").write_text(
        json.dumps({"overall_score": score}), encoding="utf-8"
    )
    (run / "execution_status.json").write_text(
        json.dumps({
            "model": model,
            "harness": harness,
            "status": "finished",
            "exit_code": 0,
        }),
        encoding="utf-8",
    )
    (run / "anomalies.json").write_text(
        json.dumps(_anomalies()), encoding="utf-8"
    )
    return run


def _write_validity(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _report(output: Path) -> dict:
    return json.loads(next(output.glob("*/report.json")).read_text(encoding="utf-8"))


def test_quality_cli_accepts_external_root_and_reports_single_harness(tmp_path):
    _write_run(tmp_path / "external", "task-a")
    output = tmp_path / "out"
    assert main(["--result-root", str(tmp_path / "external"), "--output-dir", str(output)]) == 0
    report = json.loads(next(output.glob("*/report.json")).read_text(encoding="utf-8"))
    assert report["summary"]["harness_count"] == 1
    assert any(issue["code"] == "HARNESS_SAMPLE_INSUFFICIENT" for issue in report["issues"])
    assert "transcript" not in json.dumps(report).lower()


def test_quality_cli_flags_common_zero_with_completion_trace(tmp_path):
    external = tmp_path / "external"
    for model in ("model-a", "model-b", "model-c"):
        root = _write_run(
            external, "task-common-zero", model=model, score=0.0
        )
        (root / "score.json").write_text(
            json.dumps({"overall_score": 0.0, "automated.checkpoint": 0.0}),
            encoding="utf-8",
        )
        (root / "agent.log").write_text("Completed and saved output. The criterion checkpoint expected by the rubric was checked.\n", encoding="utf-8")
    output = tmp_path / "out"
    assert main(["--result-root", str(external), "--output-dir", str(output)]) == 0
    report_path = next(output.glob("*/report.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    candidates = report["summary"]["common_zero_candidates"]
    assert candidates[0]["reason_code"] == "CHECKPOINT_STRICTNESS_SUSPECTED"
    review = report["summary"]["action_summary"]["tasks_for_review"]
    assert review[0]["task_id"] == "task-common-zero"
    assert "检查点" in review[0]["hypothesis"]
    markdown = report_path.with_name("report.md").read_text(encoding="utf-8")
    assert "结论摘要" in markdown
    assert "多模型共同低分候选" in markdown


def test_validate_results_schema_filters_run_error_and_routes_rerun(tmp_path):
    external = tmp_path / "external"
    invalid_run = _write_run(external, "task-invalid")
    _write_run(external, "task-valid")
    validity = _write_validity(
        tmp_path / "validity.json",
        {
            "schema_version": 2,
            "check_type": "eval_result_validity",
            "result_root": str(external),
            "verdict": "FAIL",
            "summary": {"errors": 1, "warnings": 0},
            "units": {},
            "findings": [{
                "id": "REQUEST_COUNT_DRIFT",
                "severity": "error",
                "run_dir": str(invalid_run).replace("/", "\\"),
                "evidence": {},
            }],
        },
    )
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--validity", str(validity),
        "--output-dir", str(output),
    ]) == 1

    report = _report(output)
    summary = report["summary"]
    assert summary["usable_score_count"] == 1
    assert summary["validity_filtered_score_count"] == 1
    assert summary["validity_evidence"]["detected_schema"] == "eval_result_validity"
    assert summary["validity_evidence"]["verdict"] == "FAIL"
    assert summary["validity_evidence"]["validity_verdict"] == "FAIL"
    actions = summary["action_summary"]
    assert actions["results_to_rerun"][0]["task_id"] == "task-invalid"
    assert actions["tasks_to_fix"] == []


def test_duplicate_transcript_occurrences_filter_every_affected_run(tmp_path):
    external = tmp_path / "external"
    first = _write_run(external, "task-a")
    second = _write_run(external, "task-b")
    validity = _write_validity(
        tmp_path / "validity.json",
        {
            "schema_version": 2,
            "check_type": "eval_result_validity",
            "result_root": str(external),
            "verdict": "FAIL",
            "units": {},
            "findings": [{
                "id": "DUPLICATE_TRANSCRIPT",
                "severity": "error",
                "run_dir": "",
                "evidence": {
                    "occurrences": [
                        ["model-a@harness-a", "01_Category/task-a", str(first)],
                        ["model-a@harness-a", "01_Category/task-b", str(second)],
                    ]
                },
            }],
        },
    )
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--validity", str(validity),
        "--output-dir", str(output),
    ]) == 1

    report = _report(output)
    assert report["summary"]["usable_score_count"] == 0
    assert report["summary"]["validity_filtered_score_count"] == 2
    reruns = report["summary"]["action_summary"]["results_to_rerun"]
    assert {item["task_id"] for item in reruns} == {"task-a", "task-b"}


def test_unmatched_top_level_validity_failure_becomes_framework_issue(tmp_path):
    external = tmp_path / "external"
    _write_run(external, "task-a")
    validity = _write_validity(
        tmp_path / "validity.json",
        {
            "schema_version": 2,
            "check_type": "eval_result_validity",
            "result_root": str(external),
            "verdict": "FAIL",
            "units": {},
            "findings": [{
                "id": "UNIT_TASK_SET_MISMATCH",
                "severity": "error",
                "run_dir": "",
                "evidence": {"model-a@harness-a": 1},
            }],
        },
    )
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--validity", str(validity),
        "--output-dir", str(output),
    ]) == 1

    report = _report(output)
    assert report["summary"]["validity_filtered_score_count"] == 0
    framework = report["summary"]["action_summary"]["framework_issues"]
    assert any(item["issue_code"] == "UPSTREAM_VALIDITY_FAILED" for item in framework)


def test_validate_results_warning_is_filtered_for_review_without_forcing_rerun(tmp_path):
    external = tmp_path / "external"
    run = _write_run(external, "task-review")
    validity = _write_validity(
        tmp_path / "validity.json",
        {
            "schema_version": 2,
            "check_type": "eval_result_validity",
            "result_root": str(external),
            "verdict": "REVIEW",
            "units": {},
            "findings": [{
                "id": "TIMEOUT_CONFIG_MISMATCH",
                "severity": "warning",
                "run_dir": str(run),
                "evidence": {},
            }],
        },
    )
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--validity", str(validity),
        "--output-dir", str(output),
    ]) == 0

    report = _report(output)
    assert report["summary"]["validity_filtered_score_count"] == 1
    actions = report["summary"]["action_summary"]
    assert actions["results_to_rerun"] == []
    assert actions["tasks_for_review"][0]["task_id"] == "task-review"


def test_legacy_runs_validity_schema_remains_supported(tmp_path):
    external = tmp_path / "external"
    run = _write_run(external, "task-a")
    relative = str(run.relative_to(external)).replace("/", "\\")
    validity = _write_validity(
        tmp_path / "validity.json",
        {
            "schema_version": 1,
            "validity_verdict": "FAIL",
            "runs": {
                relative: {
                    "has_validity_failure": True,
                    "validity_verdict": "FAIL",
                }
            },
        },
    )
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--validity", str(validity),
        "--output-dir", str(output),
    ]) == 1

    report = _report(output)
    assert report["summary"]["validity_filtered_score_count"] == 1
    assert report["summary"]["validity_evidence"]["detected_schema"] == "legacy_runs"


def test_unsupported_validity_schema_is_not_silently_accepted(tmp_path):
    external = tmp_path / "external"
    _write_run(external, "task-a")
    validity = _write_validity(
        tmp_path / "validity.json",
        {"schema_version": 99, "verdict": "FAIL", "findings": []},
    )
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--validity", str(validity),
        "--output-dir", str(output),
    ]) == 1

    report = _report(output)
    codes = {item["code"] for item in report["issues"]}
    assert "VALIDITY_SCHEMA_UNSUPPORTED" in codes
    framework = report["summary"]["action_summary"]["framework_issues"]
    assert framework[0]["issue_code"] == "VALIDITY_SCHEMA_UNSUPPORTED"


def test_result_validity_invalid_is_rerun_not_task_fix(tmp_path):
    external = tmp_path / "external"
    run = _write_run(external, "task-invalid")
    (run / "anomalies.json").write_text(
        json.dumps(_anomalies("FAIL", [{
            "id": "JUDGE_FAILED",
            "validity_impact": "fail",
            "rerun_action": "required_after_fix",
        }])),
        encoding="utf-8",
    )
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--output-dir", str(output),
    ]) == 1

    actions = _report(output)["summary"]["action_summary"]
    assert actions["results_to_rerun"][0]["task_id"] == "task-invalid"
    assert "RESULT_VALIDITY_INVALID" in actions["results_to_rerun"][0]["issue_codes"]
    assert actions["tasks_to_fix"] == []


def test_quality_audit_rescans_stale_anomalies_with_current_rules(tmp_path):
    external = tmp_path / "external"
    run = _write_run(external, "task-stale")
    (run / "score.json").write_text(
        json.dumps({
            "overall_score": 0.5,
            "_grading": {
                "llm_notes": "judge failed: judge returned no valid JSON",
            },
        }),
        encoding="utf-8",
    )
    stale = _anomalies()
    stale["ruleset_version"] = "obsolete"
    stale_text = json.dumps(stale)
    (run / "anomalies.json").write_text(stale_text, encoding="utf-8")
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--output-dir", str(output),
    ]) == 1

    report = _report(output)
    assert report["summary"]["usable_score_count"] == 0
    assert any(
        issue["code"] == "RESULT_VALIDITY_INVALID"
        for issue in report["issues"]
    )
    assert (
        report["summary"]["action_summary"]["results_to_rerun"][0]["task_id"]
        == "task-stale"
    )
    assert (run / "anomalies.json").read_text(encoding="utf-8") == stale_text


def test_quality_audit_reports_current_anomaly_scan_failure_as_framework_issue(tmp_path):
    external = tmp_path / "external"
    run = _write_run(external, "task-scan-failed")
    stale = _anomalies()
    stale["ruleset_version"] = "obsolete"
    (run / "anomalies.json").write_text(json.dumps(stale), encoding="utf-8")
    output = tmp_path / "out"

    with patch(
        "tools.report.lib.eval_dataset.result_files.scan_run_dir",
        side_effect=RuntimeError("scan exploded"),
    ):
        assert main([
            "--result-root", str(external),
            "--output-dir", str(output),
        ]) == 1

    report = _report(output)
    framework = report["summary"]["action_summary"]["framework_issues"]
    assert framework[0]["issue_code"] == "RESULT_ANOMALY_REFRESH_FAILED"
    assert report["summary"]["action_summary"]["results_to_rerun"] == []


def test_missing_task_results_expand_into_rerun_actions(tmp_path):
    external = tmp_path / "external"
    _write_run(external, "task-present")
    task = tmp_path / "task-missing.md"
    task.write_text(
        "---\nid: task-missing\ncategory: test\n---\n## Prompt\nDo it\n",
        encoding="utf-8",
    )
    output = tmp_path / "out"

    assert main([
        "--result-root", str(external),
        "--task-path", str(task),
        "--output-dir", str(output),
    ]) == 1

    actions = _report(output)["summary"]["action_summary"]
    rerun = next(
        item for item in actions["results_to_rerun"]
        if item["task_id"] == "task-missing"
    )
    assert rerun["unit"] == "model-a@harness-a"
    assert rerun["issue_codes"] == ["RESULT_TASK_MISSING"]


def test_markdown_renders_new_and_legacy_action_summaries():
    new_report = Report(
        1,
        PASS,
        {},
        {
            "action_summary": {
                "counts": {
                    "results_to_rerun": 1,
                    "framework_issues": 1,
                    "tasks_to_fix": 0,
                    "tasks_for_review": 0,
                    "tasks_pass": 0,
                },
                "results_to_rerun": [{
                    "task_id": "task-a",
                    "unit": "model@harness",
                    "issue_codes": ["RESULT_VALIDITY_INVALID"],
                    "recommendations": ["重跑"],
                }],
                "framework_issues": [{
                    "issue_code": "UPSTREAM_VALIDITY_FAILED",
                    "severity": "FAIL",
                    "location": "",
                    "recommendation": "修复输入",
                }],
                "tasks_to_fix": [],
                "tasks_for_review": [],
                "tasks_pass": [],
            }
        },
    )
    new_markdown = _markdown(new_report)
    assert "需要重跑或补齐的结果" in new_markdown
    assert "需要修复的框架或审计输入" in new_markdown

    legacy_report = Report(
        1,
        PASS,
        {},
        {
            "action_summary": {
                "counts": {
                    "tasks_to_fix": 1,
                    "tasks_for_review": 0,
                    "tasks_pass": 0,
                },
                "tasks_to_fix": [{
                    "task_id": "task-a",
                    "issue_codes": ["TASK_INVALID"],
                    "recommendations": ["修复"],
                }],
                "tasks_for_review": [],
                "tasks_pass": [],
            }
        },
    )
    legacy_markdown = _markdown(legacy_report)
    assert "| 需要修改 | 1 |" in legacy_markdown
    assert "需要重跑或补齐的结果" not in legacy_markdown
