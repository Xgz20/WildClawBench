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

from tools.report.lib.eval_dataset.contracts import FAIL, REVIEW, Issue, Report, exit_code, status_for_issues
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


def _validity_schema(validity: dict[str, Any]) -> str:
    if isinstance(validity.get("runs"), dict):
        return "legacy_runs"
    if (
        validity.get("check_type") == "eval_result_validity"
        and isinstance(validity.get("verdict"), str)
        and isinstance(validity.get("units"), dict)
        and isinstance(validity.get("findings"), list)
    ):
        return "eval_result_validity"
    return "unsupported"


def _normalized_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    parts: list[str] = []
    prefix = "/" if text.startswith("/") else ""
    for part in text.split("/"):
        if not part or part == ".":
            continue
        if part == ".." and parts and parts[-1] != "..":
            parts.pop()
        else:
            parts.append(part)
    return prefix + "/".join(parts)


def _record_matches_path(
    record: ResultRecord, raw_path: Any, validity_root: Any = ""
) -> bool:
    candidate = _normalized_path(raw_path)
    if not candidate:
        return False
    absolute = _normalized_path(record.run_dir.resolve())
    try:
        relative = _normalized_path(record.run_dir.relative_to(record.result_root))
    except ValueError:
        relative = _normalized_path(record.run_dir.name)
    if candidate in {absolute, relative}:
        return True

    source_root = _normalized_path(validity_root)
    if source_root and candidate.startswith(f"{source_root}/"):
        candidate = candidate[len(source_root) + 1 :]
        if candidate == relative:
            return True

    # 支持 validity JSON 与结果包被移动到不同绝对目录后的复用。
    return bool(relative and candidate.endswith(f"/{relative}"))


def _finding_run_paths(finding: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    if finding.get("run_dir"):
        paths.append(str(finding["run_dir"]))
    evidence = finding.get("evidence")
    if not isinstance(evidence, dict):
        return list(dict.fromkeys(paths))

    occurrences = evidence.get("occurrences")
    if isinstance(occurrences, list):
        for occurrence in occurrences:
            if isinstance(occurrence, (list, tuple)) and len(occurrence) >= 3:
                paths.append(str(occurrence[2]))
            elif isinstance(occurrence, dict):
                value = occurrence.get("run_dir") or occurrence.get("path")
                if value:
                    paths.append(str(value))
    affected_runs = evidence.get("affected_runs")
    if isinstance(affected_runs, list):
        paths.extend(str(value) for value in affected_runs if value)
    return list(dict.fromkeys(paths))


def _validity_run_entry(validity: dict[str, Any], record: ResultRecord) -> dict[str, Any]:
    runs = validity.get("runs")
    if not isinstance(runs, dict):
        return {}
    try:
        relative = str(record.run_dir.relative_to(record.result_root))
    except ValueError:
        relative = record.run_dir.name
    entry = runs.get(relative)
    if isinstance(entry, dict):
        return entry
    # Keep compatibility with reports written on a Windows host.
    entry = runs.get(relative.replace("/", "\\"))
    return entry if isinstance(entry, dict) else {}


def _filter_validity_records(
    records: list[ResultRecord],
    validity: dict[str, Any],
    inventory_records: list[ResultRecord] | None = None,
) -> tuple[list[ResultRecord], list[Issue]]:
    """Exclude validity-failed runs from capability statistics, not from inventory."""
    if not validity:
        return records, []
    schema = _validity_schema(validity)
    if schema == "unsupported":
        return records, [Issue(
            FAIL,
            "VALIDITY_SCHEMA_UNSUPPORTED",
            "validity JSON 的数据契约不受质量审计支持",
            evidence={
                "schema_version": validity.get("schema_version"),
                "check_type": validity.get("check_type"),
                "top_level_keys": sorted(str(key) for key in validity),
            },
        )]

    usable: list[ResultRecord] = []
    issues: list[Issue] = []
    if schema == "legacy_runs":
        for record in records:
            entry = _validity_run_entry(validity, record)
            verdict = str(entry.get("validity_verdict") or "").upper()
            failed = bool(entry.get("has_validity_failure") or verdict == "FAIL")
            review = verdict == "REVIEW"
            if failed or review:
                issues.append(Issue(
                    FAIL if failed else REVIEW,
                    "RESULT_VALIDITY_FAILED",
                    "该 run 存在评测有效性失败，不纳入能力统计"
                    if failed else "该 run 的评测有效性需要复核，暂不纳入能力统计",
                    task_id=record.task_id,
                    location=str(record.run_dir),
                    evidence={
                        "unit": record.unit,
                        "validity_verdict": verdict,
                        "validity_schema": schema,
                    },
                ))
                continue
            usable.append(record)
        return usable, issues

    affected: dict[int, list[dict[str, Any]]] = {}
    unmatched: dict[str, list[dict[str, Any]]] = {"error": [], "warning": []}
    seen: dict[str, int] = {"error": 0, "warning": 0}
    validity_root = validity.get("result_root")
    inventory = inventory_records if inventory_records is not None else records
    for raw_finding in validity.get("findings", []):
        if not isinstance(raw_finding, dict):
            continue
        severity = str(raw_finding.get("severity") or "").lower()
        if severity not in unmatched:
            continue
        seen[severity] += 1
        paths = _finding_run_paths(raw_finding)
        inventory_match = any(
            _record_matches_path(record, path, validity_root)
            for record in inventory
            for path in paths
        )
        indexes = {
            index
            for index, record in enumerate(records)
            if any(
                _record_matches_path(record, path, validity_root)
                for path in paths
            )
        }
        if not indexes and not inventory_match:
            unmatched[severity].append(raw_finding)
            continue
        for index in indexes:
            affected.setdefault(index, []).append(raw_finding)

    for index, record in enumerate(records):
        matched = affected.get(index, [])
        if not matched:
            usable.append(record)
            continue
        severities = {
            str(item.get("severity") or "").lower() for item in matched
        }
        failed = "error" in severities
        finding_ids = sorted({
            str(item.get("id") or "UNKNOWN") for item in matched
        })
        issues.append(Issue(
            FAIL if failed else REVIEW,
            "RESULT_VALIDITY_FAILED",
            "上游有效性检查判定该 run 无效，不纳入能力统计"
            if failed else "上游有效性检查要求复核该 run，暂不纳入能力统计",
            task_id=record.task_id,
            location=str(record.run_dir),
            evidence={
                "unit": record.unit,
                "validity_verdict": "FAIL" if failed else "REVIEW",
                "validity_schema": schema,
                "finding_ids": finding_ids,
            },
        ))

    top_verdict = str(validity.get("verdict") or "").upper()
    unmatched_errors = unmatched["error"]
    unmatched_warnings = unmatched["warning"]
    if unmatched_errors or (top_verdict == "FAIL" and not seen["error"]):
        issues.append(Issue(
            FAIL,
            "UPSTREAM_VALIDITY_FAILED",
            "上游有效性检查为 FAIL，且存在无法落实到当前单个 run 的错误",
            evidence={
                "validity_verdict": top_verdict,
                "unmatched_finding_count": len(unmatched_errors),
                "finding_ids": sorted({
                    str(item.get("id") or "UNKNOWN") for item in unmatched_errors
                }),
            },
        ))
    if unmatched_warnings or (top_verdict == "REVIEW" and not seen["warning"]):
        issues.append(Issue(
            REVIEW,
            "UPSTREAM_VALIDITY_REVIEW",
            "上游有效性检查为 REVIEW，且存在无法落实到当前单个 run 的警告",
            evidence={
                "validity_verdict": top_verdict,
                "unmatched_finding_count": len(unmatched_warnings),
                "finding_ids": sorted({
                    str(item.get("id") or "UNKNOWN") for item in unmatched_warnings
                }),
            },
        ))
    return usable, issues


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
    "RESULT_EVALUATOR_INVALID": "修复 Judge/评分失败后重新评分或重跑该结果",
    "RESULT_VALIDITY_INVALID": "修复异常检测指出的有效性问题后重跑该结果",
    "RESULT_VALIDITY_FAILED": "复核或修复上游有效性问题；判定失败后重跑该结果",
    "RESULT_TASK_MISSING": "补齐选定任务在该 model@harness 下的结果",
    "VALIDITY_INPUT_INVALID": "修复或重新生成可解析的有效性检查 JSON",
    "VALIDITY_SCHEMA_UNSUPPORTED": "使用 validate-eval-results 当前输出，或升级质量审计的契约适配",
    "UPSTREAM_VALIDITY_FAILED": "先处理无法定位到单个 run 的上游有效性错误，再解释审计结论",
    "UPSTREAM_VALIDITY_REVIEW": "人工复核无法定位到单个 run 的上游有效性警告",
    "RESULT_ROOT_NOT_FOUND": "修正结果根目录后重新运行质量审计",
    "TASK_TOO_EASY": "检查任务是否缺少梯度或输出要求过于宽松",
    "TASK_TOO_HARD": "检查任务是否不可达、输入是否缺失或评分标准过严",
    "MODEL_DISCRIMINATION_LOW": "抽查共同任务的评分分布，确认是否需要增加梯度题",
    "HARNESS_SAMPLE_INSUFFICIENT": "增加第二个 Harness 的控制变量结果，暂不下 Harness 结论",
    "STABILITY_SAMPLE_INSUFFICIENT": "增加同一任务的重复 run，再判断稳定性",
    "COMMON_ZERO_SCORE": "人工对照多个模型轨迹与 grade/rubric，确认共同 0 分是否由检查点过严导致",
    "DIFFICULTY_GRADIENT_INVERTED": "复核 difficulty 标签与题目构成，不要把标签当作等距分数",
}


_RESULT_RERUN_CODES = {
    "RESULT_EXECUTION_INVALID",
    "RESULT_SCORE_MISSING",
    "RESULT_EVALUATOR_INVALID",
    "RESULT_VALIDITY_INVALID",
    "RESULT_VALIDITY_FAILED",
    "RESULT_TASK_MISSING",
}

_FRAMEWORK_ISSUE_CODES = {
    "VALIDITY_INPUT_INVALID",
    "VALIDITY_SCHEMA_UNSUPPORTED",
    "UPSTREAM_VALIDITY_FAILED",
    "UPSTREAM_VALIDITY_REVIEW",
    "RESULT_ROOT_NOT_FOUND",
    "TASK_DIR_NOT_FOUND",
    "TASK_PATH_NOT_FOUND",
    "TASK_PATH_NOT_MARKDOWN",
    "TASK_ID_NOT_FOUND",
    "TASK_ID_AMBIGUOUS",
    "TASK_READ_ERROR",
}


def _is_failure(issue: Issue) -> bool:
    return issue.severity in {FAIL, "error"}


def _is_review(issue: Issue) -> bool:
    return issue.severity in {REVIEW, "warning"}


def _recommendation(issue: Issue) -> str:
    return _QUALITY_ACTIONS.get(issue.code, issue.message)


def build_quality_action_summary(records: list[ResultRecord], issues: list[Issue], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Issue]] = {}
    global_actions: list[str] = []
    framework_issues: list[dict[str, Any]] = []
    rerun_groups: dict[tuple[str, str], dict[str, Any]] = {}
    record_by_location = {str(record.run_dir): record for record in records}
    missing_task_ids: set[str] = set()

    for issue in issues:
        if issue.code == "RESULT_TASK_MISSING" and _is_failure(issue):
            unit = str(issue.evidence.get("unit") or "")
            values = issue.evidence.get("missing_task_ids")
            if isinstance(values, list):
                for value in values:
                    task_id = str(value)
                    missing_task_ids.add(task_id)
                    item = rerun_groups.setdefault(
                        (task_id, unit),
                        {
                            "task_id": task_id,
                            "unit": unit,
                            "issue_codes": [],
                            "locations": [],
                            "recommendations": [],
                        },
                    )
                    item["issue_codes"].append(issue.code)
                    item["recommendations"].append(_recommendation(issue))
            continue

        if issue.code in _RESULT_RERUN_CODES and _is_failure(issue):
            record = record_by_location.get(issue.location)
            unit = str(issue.evidence.get("unit") or (record.unit if record else ""))
            task_id = issue.task_id or (record.task_id if record else "")
            item = rerun_groups.setdefault(
                (task_id, unit),
                {
                    "task_id": task_id,
                    "unit": unit,
                    "issue_codes": [],
                    "locations": [],
                    "recommendations": [],
                },
            )
            item["issue_codes"].append(issue.code)
            if issue.location:
                item["locations"].append(issue.location)
            item["recommendations"].append(_recommendation(issue))
            continue

        is_framework_issue = issue.code in _FRAMEWORK_ISSUE_CODES or (
            not issue.task_id and _is_failure(issue)
        )
        if is_framework_issue:
            framework_issues.append({
                "issue_code": issue.code,
                "severity": issue.severity,
                "task_id": issue.task_id,
                "location": issue.location,
                "message": issue.message,
                "recommendation": _recommendation(issue),
                "evidence": issue.evidence,
            })
            continue

        if issue.task_id:
            grouped.setdefault(issue.task_id, []).append(issue)
            continue

        action = _recommendation(issue)
        if action not in global_actions:
            global_actions.append(action)

    results_to_rerun: list[dict[str, Any]] = []
    for item in rerun_groups.values():
        item["issue_codes"] = sorted(set(item["issue_codes"]))
        item["locations"] = sorted(set(item["locations"]))
        item["recommendations"] = list(dict.fromkeys(item["recommendations"]))
        results_to_rerun.append(item)
    results_to_rerun.sort(key=lambda item: (item["task_id"], item["unit"]))

    candidate_by_task = {item["task_id"]: item for item in candidates}
    task_ids = sorted(
        {record.task_id for record in records}
        | set(grouped)
        | missing_task_ids
        | set(candidate_by_task)
    )
    rerun_task_ids = {
        item["task_id"] for item in results_to_rerun if item["task_id"]
    }
    framework_task_ids = {
        item["task_id"] for item in framework_issues if item["task_id"]
    }
    to_fix: list[dict[str, Any]] = []
    to_review: list[dict[str, Any]] = []
    for task_id in task_ids:
        task_issues = grouped.get(task_id, [])
        fail_issues = [issue for issue in task_issues if _is_failure(issue)]
        review_issues = [issue for issue in task_issues if _is_review(issue)]
        candidate = candidate_by_task.get(task_id)
        codes = sorted({issue.code for issue in task_issues})
        if candidate and "COMMON_ZERO_SCORE" not in codes:
            codes.append("COMMON_ZERO_SCORE")
        recommendations = list(dict.fromkeys(
            _QUALITY_ACTIONS.get(code, "检查该用例的质量审计证据")
            for code in codes
        ))
        if fail_issues:
            to_fix.append({"task_id": task_id, "issue_codes": codes, "recommendations": recommendations})
        elif (
            task_id not in rerun_task_ids
            and task_id not in framework_task_ids
            and (review_issues or candidate)
        ):
            item = {"task_id": task_id, "reasons": codes, "recommendation": "；".join(recommendations)}
            if candidate:
                item.update({"hypothesis": candidate["hypothesis"], "unit_scores": candidate["unit_scores"], "trace_signal_counts": candidate["trace_signal_counts"], "sampled_run_count": candidate["sampled_run_count"]})
            to_review.append(item)

    action_task_ids = (
        rerun_task_ids
        | framework_task_ids
        | {item["task_id"] for item in to_fix}
        | {item["task_id"] for item in to_review}
    )
    tasks_pass = sorted(set(task_ids) - action_task_ids)
    if framework_issues and results_to_rerun:
        decision = "先修复框架/审计输入，并重跑或补齐无效结果，再判断评测集质量。"
    elif results_to_rerun:
        decision = "先重跑或补齐无效结果，再使用剩余有效结果判断评测集质量。"
    elif framework_issues:
        decision = "先修复框架或审计输入，再解释质量审计结论。"
    elif to_fix:
        decision = "先修复确定的评测用例问题，再用有效结果复核。"
    elif to_review:
        decision = "结果可用于初步审计，但有用例需要人工复核后才能判断评测集是否合理。"
    else:
        decision = "当前结果未发现需要修改或人工复核的质量问题。"
    return {
        "decision": decision,
        "counts": {
            "results_to_rerun": len(results_to_rerun),
            "framework_issues": len(framework_issues),
            "tasks_to_fix": len(to_fix),
            "tasks_for_review": len(to_review),
            "tasks_pass": len(tasks_pass),
        },
        "results_to_rerun": results_to_rerun,
        "framework_issues": framework_issues,
        "tasks_to_fix": to_fix,
        "tasks_for_review": to_review,
        "tasks_pass": tasks_pass,
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
    validity = _load_validity(args.validity)
    if args.validity and not validity:
        issues.append(Issue(FAIL, "VALIDITY_INPUT_INVALID", f"无法读取或解析 validity JSON: {args.validity}", location=str(Path(args.validity).expanduser())))
    effective = effective_records(discovery)
    usable, validity_issues = _filter_validity_records(
        effective, validity, inventory_records=records
    )
    issues.extend(validity_issues)
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
    validity_verdict = validity.get("verdict", validity.get("validity_verdict"))
    validity_summary = {
        "detected_schema": _validity_schema(validity) if validity else "none",
        "schema_version": validity.get("schema_version"),
        "check_type": validity.get("check_type"),
        "verdict": validity_verdict,
        # 兼容旧消费方；新版 validate-eval-results 使用 verdict。
        "validity_verdict": validity.get("validity_verdict", validity_verdict),
    }
    for key in ("summary", "has_validity_failure", "needs_review"):
        if key in validity:
            validity_summary[key] = validity.get(key)
    summary = {
        "result_root_count": len(args.result_root),
        "score_file_count": len(records),
        "usable_score_count": len(usable),
        "unit_count": len({record.unit for record in usable}),
        "model_count": len(model_stats["models"]),
        "harness_count": len(harness_stats["harnesses"]),
        "validity_loaded": bool(validity),
        "validity_evidence": validity_summary,
        "validity_filtered_score_count": len(effective) - len(usable),
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
