import json
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "audit_eval_dataset_quality_script",
    Path(__file__).resolve().parents[1] / "skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
main = _MODULE.main


def test_quality_cli_accepts_external_root_and_reports_single_harness(tmp_path):
    root = tmp_path / "external" / "model-a" / "harness-a" / "cat" / "task-a" / "run-1"
    root.mkdir(parents=True)
    (root / "score.json").write_text(json.dumps({"overall_score": .5}), encoding="utf-8")
    (root / "execution_status.json").write_text(json.dumps({"model": "model-a", "harness": "harness-a", "status": "finished", "exit_code": 0}), encoding="utf-8")
    output = tmp_path / "out"
    assert main(["--result-root", str(tmp_path / "external"), "--output-dir", str(output)]) == 0
    report = json.loads(next(output.glob("*/report.json")).read_text(encoding="utf-8"))
    assert report["summary"]["harness_count"] == 1
    assert any(issue["code"] == "HARNESS_SAMPLE_INSUFFICIENT" for issue in report["issues"])
    assert "transcript" not in json.dumps(report).lower()


def test_quality_cli_flags_common_zero_with_completion_trace(tmp_path):
    external = tmp_path / "external"
    for model in ("model-a", "model-b", "model-c"):
        root = external / model / "harness-a" / "cat" / "task-common-zero" / "run-1"
        root.mkdir(parents=True)
        (root / "score.json").write_text(json.dumps({"overall_score": 0.0, "automated.checkpoint": 0.0}), encoding="utf-8")
        (root / "execution_status.json").write_text(json.dumps({"model": model, "harness": "harness-a", "status": "finished", "exit_code": 0}), encoding="utf-8")
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
