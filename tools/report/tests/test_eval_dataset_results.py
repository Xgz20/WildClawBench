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


def test_discovery_rejects_evaluator_failed_score_even_when_execution_finished(tmp_path):
    root = tmp_path / "results"
    run = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.0)
    (run / "score.json").write_text(
        json.dumps({
            "overall_score": 0.0,
            "_grading": {
                "status": "evaluator_failed",
                "score_reliability": "unreliable",
                "partial_overall_score": 0.5,
            },
        }),
        encoding="utf-8",
    )

    result = discover_results([root])

    assert len(result.records) == 1
    assert not result.records[0].usable
    assert result.records[0].validity == "evaluator_error"
    assert any(issue.code == "RESULT_EVALUATOR_INVALID" for issue in result.issues)


def test_discovery_rejects_unreliable_score_without_failure_status(tmp_path):
    root = tmp_path / "results"
    run = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.0)
    (run / "score.json").write_text(
        json.dumps({
            "overall_score": 0.0,
            "_grading": {
                "status": "completed",
                "score_reliability": "unreliable_evaluator_failure",
            },
        }),
        encoding="utf-8",
    )

    result = discover_results([root])

    assert not result.records[0].usable
    assert result.records[0].validity == "evaluator_error"
    assert any(issue.code == "RESULT_EVALUATOR_INVALID" for issue in result.issues)


def test_discovery_includes_anomaly_confirmed_harness_capability_outcome(tmp_path):
    root = tmp_path / "results"
    run = _run(
        root, "model-a", "harness-a", "task-a", "run-1", 0.0, status="error"
    )
    (run / "anomalies.json").write_text(
        json.dumps({
            "validity_verdict": "PASS",
            "has_validity_failure": False,
            "items": [{
                "attribution": "harness",
                "validity_impact": "none",
                "score_reliability": "valid_capability_outcome",
            }],
        }),
        encoding="utf-8",
    )

    result = discover_results([root])

    assert result.records[0].usable
    assert result.records[0].validity == "capability_outcome"
    assert not any(issue.code == "RESULT_EXECUTION_INVALID" for issue in result.issues)


def test_discovery_rejects_anomaly_validity_failure(tmp_path):
    root = tmp_path / "results"
    run = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.5)
    (run / "anomalies.json").write_text(
        json.dumps({
            "validity_verdict": "FAIL",
            "has_validity_failure": True,
            "items": [{
                "id": "EXECUTION_ERROR",
                "attribution": "evaluation_framework",
                "validity_impact": "fail",
                "score_reliability": "unreliable",
            }],
        }),
        encoding="utf-8",
    )

    result = discover_results([root])

    assert not result.records[0].usable
    assert result.records[0].validity == "validity_failure"
    assert any(issue.code == "RESULT_VALIDITY_INVALID" for issue in result.issues)
