from pathlib import Path

from tools.report.lib.eval_dataset.metrics import compare_harnesses, compare_models, difficulty_summary, stability_summary
from tools.report.lib.eval_dataset.result_files import ResultRecord


def _record(model, harness, task, score, run="r1"):
    return ResultRecord(Path("/tmp"), Path("/tmp") / run, Path("/tmp") / "score.json", model, harness, "cat", task, run, score, {"overall_score": score}, {"status": "finished", "exit_code": 0}, {}, {}, True, "valid")


def test_metrics_report_sample_limits_and_differences():
    records = [_record("a", "h1", "t1", 0.0), _record("b", "h1", "t1", 1.0), _record("a", "h2", "t1", .5), _record("b", "h2", "t1", .5)]
    model, model_issues = compare_models(records)
    harness, harness_issues = compare_harnesses(records)
    assert model["pairwise"][0]["mean_abs_gap"] == 0.5
    assert not any(issue.code == "MODEL_SAMPLE_INSUFFICIENT" for issue in model_issues)
    assert harness["pairwise"]
    assert not any(issue.code == "HARNESS_SAMPLE_INSUFFICIENT" for issue in harness_issues)
    difficulty, _ = difficulty_summary(records, {"t1": {"difficulty": "L1"}})
    assert difficulty["tasks"]["t1"]["floor_rate"] == 0.25
    _, stability_issues = stability_summary(records)
    assert any(issue.code == "STABILITY_SAMPLE_INSUFFICIENT" for issue in stability_issues)
