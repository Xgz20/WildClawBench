import json
from pathlib import Path

from tools.report.lib.eval_dataset.result_files import discover_results


def _run(root: Path, model: str, harness: str, task: str, name: str, score=None, status="finished", supersedes=None):
    run = root / model / harness / "01_Category" / task / name
    run.mkdir(parents=True, exist_ok=True)
    if score is not None:
        (run / "score.json").write_text(json.dumps({"overall_score": score}), encoding="utf-8")
    (run / "execution_status.json").write_text(json.dumps({"model": model, "harness": harness, "status": status, "exit_code": 0 if status == "finished" else 1}), encoding="utf-8")
    if supersedes:
        (run / "run_metadata.json").write_text(json.dumps({"supersedes_run": supersedes}), encoding="utf-8")
    return run


def test_discovery_normalizes_and_excludes_superseded(tmp_path):
    root = tmp_path / "results"
    _run(root, "model-a", "harness-a", "task-a", "run-1", 0.0)
    _run(root, "model-a", "harness-a", "task-a", "run-2", 1.0, supersedes="run-1")
    _run(root, "model-b", "harness-b", "task-a", "run-1", None, status="failed")
    result = discover_results([root])
    assert len(result.records) == 2
    assert any(record.score == 1.0 and record.usable for record in result.records)
    assert any(record.score is None and not record.usable for record in result.records)
    assert any(issue.code == "RESULT_SCORE_MISSING" for issue in result.issues)
