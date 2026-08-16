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
