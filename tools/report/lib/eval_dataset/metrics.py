"""评测集质量审计的确定性统计汇总。"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from .contracts import Issue, REVIEW
from .result_files import ResultRecord, effective_records


@dataclass(frozen=True)
class MetricThresholds:
    ceiling_rate: float = 0.8
    floor_rate: float = 0.8
    model_gap: float = 0.1
    minimum_models: int = 2
    minimum_harnesses: int = 2
    minimum_runs: int = 2


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def aggregate_task_scores(records: Iterable[ResultRecord]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for record in effective_records(type("D", (), {"records": list(records)})()):
        grouped_key = f"{record.unit}::{record.task_id}"
        grouped[grouped_key].append(float(record.score))
    result: dict[str, dict[str, Any]] = {}
    for key, values in sorted(grouped.items()):
        unit, task_id = key.split("::", 1)
        result[key] = {"unit": unit, "task_id": task_id, "mean": _mean(values), "run_count": len(values), "scores": values}
    return result


def _task_unit_means(records: Iterable[ResultRecord]) -> dict[tuple[str, str], float]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for record in effective_records(type("D", (), {"records": list(records)})()):
        grouped[(record.unit, record.task_id)].append(float(record.score))
    return {key: statistics.fmean(values) for key, values in grouped.items()}


def compare_models(records: Iterable[ResultRecord], thresholds: MetricThresholds = MetricThresholds()) -> tuple[dict[str, Any], list[Issue]]:
    values = _task_unit_means(records)
    models = sorted({unit.split("@", 1)[0] for unit, _ in values})
    by_model_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (unit, task_id), score in values.items():
        by_model_values[(unit.split("@", 1)[0], task_id)].append(score)
    by_model: dict[str, dict[str, float]] = defaultdict(dict)
    for (model, task_id), scores in by_model_values.items():
        by_model[model][task_id] = statistics.fmean(scores)
    pairwise: list[dict[str, Any]] = []
    issues: list[Issue] = []
    for index, left in enumerate(models):
        for right in models[index + 1:]:
            common = sorted(set(by_model[left]) & set(by_model[right]))
            if not common:
                continue
            deltas = [by_model[left][task] - by_model[right][task] for task in common]
            pairwise.append({"left": left, "right": right, "common_tasks": len(common), "mean_gap": statistics.fmean(deltas), "mean_abs_gap": statistics.fmean([abs(item) for item in deltas]), "separable_rate": sum(abs(item) >= thresholds.model_gap for item in deltas) / len(deltas)})
    if len(models) < thresholds.minimum_models:
        issues.append(Issue(REVIEW, "MODEL_SAMPLE_INSUFFICIENT", "少于两个模型，无法评估模型区分度", evidence={"models": models}))
    elif not pairwise:
        issues.append(Issue(REVIEW, "MODEL_COMMON_TASKS_INSUFFICIENT", "模型之间没有共同有效任务", evidence={"models": models}))
    return {"models": models, "pairwise": pairwise}, issues


def compare_harnesses(records: Iterable[ResultRecord], thresholds: MetricThresholds = MetricThresholds()) -> tuple[dict[str, Any], list[Issue]]:
    values = _task_unit_means(records)
    harnesses = sorted({unit.split("@", 1)[1] for unit, _ in values if "@" in unit})
    by_harness_values: dict[tuple[str, tuple[str, str]], list[float]] = defaultdict(list)
    for (unit, task_id), score in values.items():
        model, harness = unit.split("@", 1)
        by_harness_values[(harness, (model, task_id))].append(score)
    by_harness: dict[str, dict[tuple[str, str], float]] = defaultdict(dict)
    for (harness, key), scores in by_harness_values.items():
        by_harness[harness][key] = statistics.fmean(scores)
    pairwise: list[dict[str, Any]] = []
    issues: list[Issue] = []
    for index, left in enumerate(harnesses):
        for right in harnesses[index + 1:]:
            common = sorted(set(by_harness[left]) & set(by_harness[right]))
            deltas = [by_harness[left][key] - by_harness[right][key] for key in common]
            if deltas:
                pairwise.append({"left": left, "right": right, "common_model_tasks": len(common), "mean_gap": statistics.fmean(deltas), "mean_abs_gap": statistics.fmean([abs(item) for item in deltas])})
    if len(harnesses) < thresholds.minimum_harnesses:
        issues.append(Issue(REVIEW, "HARNESS_SAMPLE_INSUFFICIENT", "少于两个 Harness，无法评估 Harness 敏感性", evidence={"harnesses": harnesses}))
    elif not pairwise:
        issues.append(Issue(REVIEW, "HARNESS_COMMON_TASKS_INSUFFICIENT", "Harness 之间没有共同有效的模型/任务样本", evidence={"harnesses": harnesses}))
    return {"harnesses": harnesses, "pairwise": pairwise}, issues


def difficulty_summary(records: Iterable[ResultRecord], task_metadata: dict[str, dict[str, Any]] | None = None, thresholds: MetricThresholds = MetricThresholds()) -> tuple[dict[str, Any], list[Issue]]:
    values = _task_unit_means(records)
    task_values: dict[str, list[float]] = defaultdict(list)
    for (_, task_id), score in values.items():
        task_values[task_id].append(score)
    tasks: dict[str, dict[str, Any]] = {}
    issues: list[Issue] = []
    for task_id, scores in sorted(task_values.items()):
        ceiling = sum(score >= 0.999 for score in scores) / len(scores)
        floor = sum(score <= 0.001 for score in scores) / len(scores)
        item = {"task_id": task_id, "mean": statistics.fmean(scores), "sample_count": len(scores), "ceiling_rate": ceiling, "floor_rate": floor}
        if ceiling >= thresholds.ceiling_rate:
            issues.append(Issue(REVIEW, "TASK_TOO_EASY", f"任务分数集中在天花板: {task_id}", task_id=task_id, evidence=item))
        if floor >= thresholds.floor_rate:
            issues.append(Issue(REVIEW, "TASK_TOO_HARD", f"任务分数集中在地板: {task_id}", task_id=task_id, evidence=item))
        tasks[task_id] = item
    groups: dict[str, list[float]] = defaultdict(list)
    for task_id, item in tasks.items():
        difficulty = (task_metadata or {}).get(task_id, {}).get("difficulty")
        if difficulty:
            groups[str(difficulty)].append(float(item["mean"]))
    return {"tasks": tasks, "difficulty_groups": {key: {"mean": statistics.fmean(vals), "task_count": len(vals)} for key, vals in sorted(groups.items())}}, issues


def stability_summary(records: Iterable[ResultRecord], thresholds: MetricThresholds = MetricThresholds()) -> tuple[dict[str, Any], list[Issue]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for record in effective_records(type("D", (), {"records": list(records)})()):
        grouped[(record.unit, record.task_id)].append(float(record.score))
    summary: dict[str, Any] = {}
    issues: list[Issue] = []
    for (unit, task_id), values in sorted(grouped.items()):
        std = statistics.pstdev(values) if len(values) > 1 else None
        summary[f"{unit}::{task_id}"] = {"unit": unit, "task_id": task_id, "run_count": len(values), "mean": statistics.fmean(values), "stddev": std}
        if len(values) < thresholds.minimum_runs:
            issues.append(Issue(REVIEW, "STABILITY_SAMPLE_INSUFFICIENT", f"仅有 {len(values)} 个有效 run，稳定性证据不足", task_id=task_id, evidence={"unit": unit, "run_count": len(values)}))
    return summary, issues
