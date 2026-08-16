"""对评测轨迹做有限信号扫描，生成质量审计的人工复核候选。

这里不把 transcript 全文放入报告，也不声称自动完成根因归因；只统计
完成/错误/评分契约相关信号，帮助产品优先查看共同低分用例。
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .contracts import Issue, REVIEW
from .result_files import ResultRecord
from .security import redact_text


TRACE_FILENAMES = ("agent.log", "chat.jsonl", "chat_openclaw.jsonl", "agent_interaction.jsonl")
SIGNAL_PATTERNS = {
    "completion": re.compile(r"(?:done|completed|finished|created|saved|wrote|successfully|已完成|已保存|已生成|已创建|写入成功)", re.I),
    "execution_error": re.compile(r"(?:error|exception|traceback|failed|failure|timed[_ -]?out|no such file|cannot|unable|错误|异常|失败|超时)", re.I),
    "grading_contract": re.compile(r"(?:checkpoint|criterion|rubric|ground truth|expected behavior|评分标准|检查点|评分契约|预期结果)", re.I),
}


def _read_bounded(path: Path, max_bytes: int) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > max_bytes:
        half = max_bytes // 2
        data = data[:half] + b"\n...[trace middle omitted]...\n" + data[-half:]
    return redact_text(data.decode("utf-8", errors="replace"), max_length=max_bytes)


def _record_signals(record: ResultRecord, max_bytes: int) -> tuple[dict[str, int], list[str]]:
    counts = {key: 0 for key in SIGNAL_PATTERNS}
    files: list[str] = []
    remaining = max_bytes
    for filename in TRACE_FILENAMES:
        path = record.run_dir / filename
        if not path.is_file() or remaining <= 0:
            continue
        text = _read_bounded(path, min(remaining, max_bytes))
        if text:
            files.append(filename)
            remaining -= min(len(text.encode("utf-8")), remaining)
            for key, pattern in SIGNAL_PATTERNS.items():
                counts[key] += len(pattern.findall(text))
    return counts, files


def analyze_common_zero_scores(
    records: Iterable[ResultRecord],
    *,
    minimum_units: int = 3,
    zero_threshold: float = 0.001,
    max_trace_bytes_per_task: int = 600_000,
) -> tuple[list[dict[str, Any]], list[Issue]]:
    """找出多模型共同接近 0 分的任务，并给出有限轨迹信号假设。"""
    usable = [record for record in records if record.usable and record.score is not None]
    by_task_unit: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    by_task_records: dict[str, list[ResultRecord]] = defaultdict(list)
    for record in usable:
        by_task_unit[record.task_id][record.unit].append(float(record.score))
        by_task_records[record.task_id].append(record)

    candidates: list[dict[str, Any]] = []
    issues: list[Issue] = []
    for task_id, units in sorted(by_task_unit.items()):
        unit_scores = {unit: sum(values) / len(values) for unit, values in units.items()}
        if len(unit_scores) < minimum_units or not all(score <= zero_threshold for score in unit_scores.values()):
            continue
        signal_counts = {key: 0 for key in SIGNAL_PATTERNS}
        trace_files: set[str] = set()
        sampled_runs = 0
        per_run_budget = max(1, max_trace_bytes_per_task // max(1, len(by_task_records[task_id])))
        for record in by_task_records[task_id]:
            counts, files = _record_signals(record, per_run_budget)
            sampled_runs += int(bool(files))
            trace_files.update(files)
            for key, value in counts.items():
                signal_counts[key] += value
        if signal_counts["execution_error"] > signal_counts["completion"] and signal_counts["execution_error"] > 0:
            hypothesis = "疑似共同执行/基础设施失败，先排除运行时问题，不应直接解释为模型能力。"
            reason_code = "COMMON_EXECUTION_FAILURE"
        elif signal_counts["completion"] > 0 and signal_counts["execution_error"] == 0:
            hypothesis = "多个模型轨迹出现完成信号但共同接近 0 分，疑似评分检查点或评分契约过严；需要人工对照轨迹与 grade/rubric。"
            reason_code = "CHECKPOINT_STRICTNESS_SUSPECTED"
        elif not trace_files:
            hypothesis = "多个模型共同接近 0 分，但没有可读取的轨迹信号；需要人工补查结果包。"
            reason_code = "TRACE_EVIDENCE_MISSING"
        else:
            hypothesis = "多个模型共同接近 0 分，暂不能从有限轨迹信号确定原因。"
            reason_code = "COMMON_ZERO_SCORE_NEEDS_REVIEW"
        candidate = {
            "task_id": task_id,
            "unit_count": len(unit_scores),
            "units": sorted(unit_scores),
            "unit_scores": unit_scores,
            "hypothesis": hypothesis,
            "reason_code": reason_code,
            "trace_signal_counts": signal_counts,
            "trace_files_sampled": sorted(trace_files),
            "sampled_run_count": sampled_runs,
            "recommendation": "人工抽查至少两个模型的轨迹、Automated Checks/LLM Judge Rubric 和 ground truth；确认是共同完成但检查点过严，还是共同未完成。",
        }
        candidates.append(candidate)
        issues.append(Issue(REVIEW, "COMMON_ZERO_SCORE", hypothesis, task_id=task_id, evidence={"unit_count": len(unit_scores), "unit_scores": unit_scores, "reason_code": reason_code, "trace_signal_counts": signal_counts, "sampled_run_count": sampled_runs}))
    return candidates, issues
