import json
from pathlib import Path
from unittest.mock import patch

from src.utils.anomalies import RULESET_VERSION, SCHEMA_VERSION
from tools.report.lib.eval_dataset.result_files import discover_results


def _anomalies(verdict="PASS", items=None):
    items = list(items or [])
    has_failure = verdict == "FAIL"
    needs_review = verdict == "REVIEW"
    return {
        "schema_version": SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "validity_verdict": verdict,
        "is_anomalous": bool(items),
        "has_error": has_failure,
        "has_validity_failure": has_failure,
        "has_model_or_harness_issue": any(
            item.get("attribution") in {"model", "harness"} for item in items
        ),
        "needs_review": needs_review,
        "needs_rerun": any(
            item.get("rerun_action") == "required_after_fix" for item in items
        ),
        "items": items,
    }


def _run(root: Path, model: str, harness: str, task: str, name: str, score=None, status="finished", supersedes=None):
    run = root / model / harness / "01_Category" / task / name
    run.mkdir(parents=True, exist_ok=True)
    if score is not None:
        (run / "score.json").write_text(json.dumps({"overall_score": score}), encoding="utf-8")
    (run / "execution_status.json").write_text(json.dumps({"model": model, "harness": harness, "status": status, "exit_code": 0 if status == "finished" else 1}), encoding="utf-8")
    (run / "anomalies.json").write_text(
        json.dumps(_anomalies()), encoding="utf-8"
    )
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
        json.dumps(_anomalies(items=[{
                "attribution": "harness",
                "validity_impact": "none",
                "score_reliability": "valid_capability_outcome",
            }])),
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
        json.dumps(_anomalies("FAIL", [{
                "id": "EXECUTION_ERROR",
                "attribution": "evaluation_framework",
                "validity_impact": "fail",
                "score_reliability": "unreliable",
            }])),
        encoding="utf-8",
    )

    result = discover_results([root])

    assert not result.records[0].usable
    assert result.records[0].validity == "validity_failure"
    assert any(issue.code == "RESULT_VALIDITY_INVALID" for issue in result.issues)


def test_discovery_reuses_current_anomaly_snapshot_without_rescan(tmp_path):
    root = tmp_path / "results"
    run = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.5)
    persisted = json.loads((run / "anomalies.json").read_text(encoding="utf-8"))

    with patch(
        "tools.report.lib.eval_dataset.result_files.scan_run_dir"
    ) as scan:
        result = discover_results([root])

    scan.assert_not_called()
    assert result.records[0].anomalies == persisted


def test_discovery_rescans_stale_pass_before_effective_run_selection(tmp_path):
    root = tmp_path / "results"
    stale = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.0)
    _run(root, "model-a", "harness-a", "task-a", "run-2", 1.0)
    (stale / "score.json").write_text(
        json.dumps({
            "overall_score": 0.0,
            "_grading": {"llm_notes": "judge failed: judge returned no valid JSON"},
        }),
        encoding="utf-8",
    )
    stale_payload = _anomalies()
    stale_payload["ruleset_version"] = "obsolete"
    stale_text = json.dumps(stale_payload)
    (stale / "anomalies.json").write_text(stale_text, encoding="utf-8")

    result = discover_results([root])

    assert [record.run_name for record in result.records] == ["run-2"]
    assert (stale / "anomalies.json").read_text(encoding="utf-8") == stale_text


def test_discovery_uses_current_review_instead_of_stale_fail(tmp_path):
    root = tmp_path / "results"
    run = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.5)
    stale = _anomalies("FAIL", [{"validity_impact": "fail"}])
    stale["ruleset_version"] = "obsolete"
    (run / "anomalies.json").write_text(json.dumps(stale), encoding="utf-8")
    current_review = _anomalies("REVIEW", [{
        "id": "USAGE_UNAVAILABLE_ON_TIMEOUT",
        "attribution": "harness",
        "validity_impact": "review",
        "score_reliability": "valid_capability_outcome",
        "rerun_action": "do_not_rerun",
    }])

    with patch(
        "tools.report.lib.eval_dataset.result_files.scan_run_dir",
        return_value=current_review,
    ) as scan:
        result = discover_results([root])

    scan.assert_called_once_with(run.resolve())
    assert result.records[0].anomalies == current_review
    assert result.records[0].usable


def test_discovery_rescans_missing_and_corrupt_snapshots_without_writing(tmp_path):
    root = tmp_path / "results"
    missing = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.5)
    corrupt = _run(root, "model-a", "harness-a", "task-b", "run-1", 0.6)
    malformed = _run(root, "model-a", "harness-a", "task-c", "run-1", 0.7)
    (missing / "anomalies.json").unlink()
    corrupt_text = "{not-json"
    (corrupt / "anomalies.json").write_text(corrupt_text, encoding="utf-8")
    malformed_payload = _anomalies()
    malformed_payload["items"] = ["not-an-anomaly-item"]
    malformed_text = json.dumps(malformed_payload)
    (malformed / "anomalies.json").write_text(malformed_text, encoding="utf-8")
    current = _anomalies()

    with patch(
        "tools.report.lib.eval_dataset.result_files.scan_run_dir",
        return_value=current,
    ) as scan:
        result = discover_results([root])

    assert scan.call_count == 3
    assert {record.task_id for record in result.records if record.usable} == {
        "task-a", "task-b", "task-c"
    }
    assert not (missing / "anomalies.json").exists()
    assert (corrupt / "anomalies.json").read_text(encoding="utf-8") == corrupt_text
    assert (
        (malformed / "anomalies.json").read_text(encoding="utf-8")
        == malformed_text
    )


def test_discovery_uses_one_refreshed_snapshot_for_selection_and_record(tmp_path):
    root = tmp_path / "results"
    stale = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.5)
    _run(root, "model-a", "harness-a", "task-a", "run-2", 0.6)
    stale_payload = _anomalies()
    stale_payload["ruleset_version"] = "obsolete"
    (stale / "anomalies.json").write_text(json.dumps(stale_payload), encoding="utf-8")
    current = _anomalies(items=[{"id": "CACHE_MARKER", "validity_impact": "none"}])

    with patch(
        "tools.report.lib.eval_dataset.result_files.scan_run_dir",
        return_value=current,
    ) as scan:
        result = discover_results([root])

    scan.assert_called_once_with(stale.resolve())
    first = next(
        record for record in result.records if record.run_dir == stale.resolve()
    )
    assert first.anomalies == current


def test_discovery_fails_closed_when_current_anomaly_scan_fails(tmp_path):
    root = tmp_path / "results"
    run = _run(root, "model-a", "harness-a", "task-a", "run-1", 0.5)
    stale_payload = _anomalies()
    stale_payload["ruleset_version"] = "obsolete"
    stale_text = json.dumps(stale_payload)
    (run / "anomalies.json").write_text(stale_text, encoding="utf-8")

    with patch(
        "tools.report.lib.eval_dataset.result_files.scan_run_dir",
        side_effect=RuntimeError("scan exploded"),
    ):
        result = discover_results([root])

    assert not result.records[0].usable
    assert result.records[0].validity == "validity_failure"
    assert any(
        issue.code == "RESULT_ANOMALY_REFRESH_FAILED"
        for issue in result.issues
    )
    assert not any(
        issue.code == "RESULT_VALIDITY_INVALID"
        for issue in result.issues
    )
    assert (run / "anomalies.json").read_text(encoding="utf-8") == stale_text
