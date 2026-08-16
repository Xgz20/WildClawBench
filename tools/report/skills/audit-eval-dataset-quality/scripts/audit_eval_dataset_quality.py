#!/usr/bin/env python3
"""基于外部结果的 WildClawBench 评测集质量审计入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.report.lib.eval_dataset.contracts import FAIL, Issue, Report, exit_code, status_for_issues
from tools.report.lib.eval_dataset.metrics import MetricThresholds, aggregate_task_scores, compare_harnesses, compare_models, difficulty_summary, stability_summary
from tools.report.lib.eval_dataset.reporting import write_report
from tools.report.lib.eval_dataset.result_files import ResultRecord, discover_results, effective_records
from tools.report.lib.eval_dataset.selectors import select_task_files
from tools.report.lib.eval_dataset.task_files import parse_task_document


def _load_validity(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", action="append", required=True)
    parser.add_argument("--task-dir", action="append", default=[])
    parser.add_argument("--task-path", action="append", default=[])
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--validity")
    parser.add_argument("--output-dir")
    parser.add_argument("--fail-on", choices=("fail", "review"), default="fail")
    parser.add_argument("--ceiling-rate", type=float, default=0.8)
    parser.add_argument("--floor-rate", type=float, default=0.8)
    parser.add_argument("--model-gap", type=float, default=0.1)
    return parser


def _selected_metadata(paths: list[Path]) -> tuple[set[str], dict[str, dict[str, Any]], list[Issue]]:
    ids: set[str] = set()
    metadata: dict[str, dict[str, Any]] = {}
    issues: list[Issue] = []
    for path in paths:
        try:
            doc = parse_task_document(path)
            ids.add(doc.task_id)
            metadata[doc.task_id] = doc.metadata
        except (OSError, UnicodeError) as exc:
            issues.append(Issue(FAIL, "TASK_READ_ERROR", str(exc), location=str(path)))
    return ids, metadata, issues


def _coverage(records: list[ResultRecord], selected_ids: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    units = sorted({record.unit for record in records})
    if not selected_ids:
        return issues
    for unit in units:
        seen = {record.task_id for record in records if record.unit == unit and record.usable}
        missing = sorted(selected_ids - seen)
        if missing:
            issues.append(Issue(FAIL, "RESULT_TASK_MISSING", f"{unit} 缺少选中任务结果", evidence={"unit": unit, "missing_count": len(missing), "missing_task_ids": missing[:100]}))
    return issues


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selection = select_task_files(REPO_ROOT, task_dirs=args.task_dir, task_paths=args.task_path, task_ids=args.task_id, default_root="tasks")
    selected_ids, metadata, task_issues = _selected_metadata(selection.files)
    discovery = discover_results(args.result_root)
    records = discovery.records
    issues = list(selection.issues) + task_issues + list(discovery.issues)
    # With no explicit task selector, an external result bundle is commonly a
    # deliberate subset of the repository. Use it for statistics and reserve
    # deterministic coverage FAIL for an explicitly requested task scope.
    explicit_scope = bool(args.task_dir or args.task_path or args.task_id)
    issues.extend(_coverage(records, selected_ids if explicit_scope else set()))
    usable = effective_records(discovery)
    thresholds = MetricThresholds(ceiling_rate=args.ceiling_rate, floor_rate=args.floor_rate, model_gap=args.model_gap)
    model_stats, model_issues = compare_models(usable, thresholds)
    harness_stats, harness_issues = compare_harnesses(usable, thresholds)
    difficulty_stats, difficulty_issues = difficulty_summary(usable, metadata, thresholds)
    stability_stats, stability_issues = stability_summary(usable, thresholds)
    issues.extend(model_issues + harness_issues + difficulty_issues + stability_issues)
    validity = _load_validity(args.validity)
    validity_summary = {
        key: validity.get(key)
        for key in ("schema_version", "validity_verdict", "summary", "has_validity_failure", "needs_review")
        if key in validity
    }
    summary = {
        "result_root_count": len(args.result_root),
        "score_file_count": len(records),
        "usable_score_count": len(usable),
        "unit_count": len({record.unit for record in usable}),
        "model_count": len(model_stats["models"]),
        "harness_count": len(harness_stats["harnesses"]),
        "validity_loaded": bool(validity),
        "validity_evidence": validity_summary,
        "model_comparison": model_stats,
        "harness_comparison": harness_stats,
        "difficulty": difficulty_stats,
        "stability": stability_stats,
        "task_scores": aggregate_task_scores(usable),
    }
    status = status_for_issues(issues)
    report = Report(1, status, {"repo": str(REPO_ROOT), "result_roots": [str(Path(item).expanduser().resolve()) for item in args.result_root], "tasks": [str(path) for path in selection.files], "selectors": selection.selectors}, summary, issues)
    target = write_report(report, repo_root=REPO_ROOT, kind="quality", output_dir=args.output_dir)
    print(target)
    return exit_code(status, fail_on_review=args.fail_on == "review")


if __name__ == "__main__":
    raise SystemExit(main())
