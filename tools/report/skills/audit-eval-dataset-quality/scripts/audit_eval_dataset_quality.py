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
from tools.report.lib.eval_dataset.trace_analysis import analyze_common_zero_scores


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
    parser.add_argument("--include-doc-copies", action="store_true", help="显式包含 tasks/cn 等仅供阅读的中文副本")
    parser.add_argument("--validity")
    parser.add_argument("--output-dir")
    parser.add_argument("--fail-on", choices=("fail", "review"), default="fail")
    parser.add_argument("--ceiling-rate", type=float, default=0.8)
    parser.add_argument("--floor-rate", type=float, default=0.8)
    parser.add_argument("--model-gap", type=float, default=0.1)
    parser.add_argument("--no-trace-analysis", action="store_true", help="不扫描有限轨迹信号，仅计算分数统计")
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


_QUALITY_ACTIONS = {
    "RESULT_EXECUTION_INVALID": "先排除 timed-out/执行失败结果，重新运行后再解释模型能力",
    "RESULT_SCORE_MISSING": "补齐 score.json 或从统计范围中移除该 run",
    "RESULT_TASK_MISSING": "补齐选定任务在该 model@harness 下的结果",
    "TASK_TOO_EASY": "检查任务是否缺少梯度或输出要求过于宽松",
    "TASK_TOO_HARD": "检查任务是否不可达、输入是否缺失或评分标准过严",
    "MODEL_DISCRIMINATION_LOW": "抽查共同任务的评分分布，确认是否需要增加梯度题",
    "HARNESS_SAMPLE_INSUFFICIENT": "增加第二个 Harness 的控制变量结果，暂不下 Harness 结论",
    "STABILITY_SAMPLE_INSUFFICIENT": "增加同一任务的重复 run，再判断稳定性",
    "COMMON_ZERO_SCORE": "人工对照多个模型轨迹与 grade/rubric，确认共同 0 分是否由检查点过严导致",
    "DIFFICULTY_GRADIENT_INVERTED": "复核 difficulty 标签与题目构成，不要把标签当作等距分数",
}


def build_quality_action_summary(records: list[ResultRecord], issues: list[Issue], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Issue]] = {}
    global_actions: list[str] = []
    for issue in issues:
        if issue.task_id:
            grouped.setdefault(issue.task_id, []).append(issue)
        else:
            action = _QUALITY_ACTIONS.get(issue.code, issue.message)
            if action not in global_actions:
                global_actions.append(action)
    candidate_by_task = {item["task_id"]: item for item in candidates}
    task_ids = sorted({record.task_id for record in records})
    to_fix: list[dict[str, Any]] = []
    to_review: list[dict[str, Any]] = []
    for task_id in task_ids:
        task_issues = grouped.get(task_id, [])
        fail_issues = [issue for issue in task_issues if issue.severity in {FAIL, "error"}]
        review_issues = [issue for issue in task_issues if issue.severity in {"REVIEW", "warning"}]
        candidate = candidate_by_task.get(task_id)
        codes = sorted({issue.code for issue in task_issues})
        if candidate and "COMMON_ZERO_SCORE" not in codes:
            codes.append("COMMON_ZERO_SCORE")
        recommendations = list(dict.fromkeys(_QUALITY_ACTIONS.get(code, "检查该用例的质量审计证据") for code in codes))
        if fail_issues:
            to_fix.append({"task_id": task_id, "issue_codes": codes, "recommendations": recommendations})
        elif review_issues or candidate:
            item = {"task_id": task_id, "reasons": codes, "recommendation": "；".join(recommendations)}
            if candidate:
                item.update({"hypothesis": candidate["hypothesis"], "unit_scores": candidate["unit_scores"], "trace_signal_counts": candidate["trace_signal_counts"], "sampled_run_count": candidate["sampled_run_count"]})
            to_review.append(item)
    if to_fix:
        decision = "先修复无效/缺失结果，再使用剩余有效结果判断评测集质量。"
    elif to_review:
        decision = "结果可用于初步审计，但有用例需要人工复核后才能判断评测集是否合理。"
    else:
        decision = "当前结果未发现需要修改或人工复核的质量问题。"
    return {
        "decision": decision,
        "counts": {"tasks_to_fix": len(to_fix), "tasks_for_review": len(to_review), "tasks_pass": max(0, len(task_ids) - len(to_fix) - len(to_review))},
        "tasks_to_fix": to_fix,
        "tasks_for_review": to_review,
        "tasks_pass": sorted(set(task_ids) - {item["task_id"] for item in to_fix} - {item["task_id"] for item in to_review}),
        "global_actions": global_actions,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selection = select_task_files(REPO_ROOT, task_dirs=args.task_dir, task_paths=args.task_path, task_ids=args.task_id, default_root="tasks", include_doc_copies=args.include_doc_copies)
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
    common_zero_candidates: list[dict[str, Any]] = []
    if not args.no_trace_analysis:
        common_zero_candidates, trace_issues = analyze_common_zero_scores(usable)
        issues.extend(trace_issues)
    validity = _load_validity(args.validity)
    if args.validity and not validity:
        issues.append(Issue(FAIL, "VALIDITY_INPUT_INVALID", f"无法读取或解析 validity JSON: {args.validity}", location=str(Path(args.validity).expanduser())))
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
        "common_zero_candidates": common_zero_candidates,
        "action_summary": build_quality_action_summary(records, issues, common_zero_candidates),
    }
    status = status_for_issues(issues)
    report = Report(1, status, {"repo": str(REPO_ROOT), "result_roots": [str(Path(item).expanduser().resolve()) for item in args.result_root], "tasks": [str(path) for path in selection.files], "selectors": selection.selectors, "include_doc_copies": args.include_doc_copies}, summary, issues)
    target = write_report(report, repo_root=REPO_ROOT, kind="quality", output_dir=args.output_dir)
    print(target)
    return exit_code(status, fail_on_review=args.fail_on == "review")


if __name__ == "__main__":
    raise SystemExit(main())
