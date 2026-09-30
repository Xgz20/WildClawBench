#!/usr/bin/env python3
"""Analyze per-model-request token growth from frozen General E2E traces.

The analyzer intentionally separates request-level context growth from exact
system-prompt attribution.  The latter requires a complete outbound request
payload and is reported unavailable when the trace does not contain one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable


HARNESS_NAMES = {
    "astronstudio-macos-x86-64": "AstronStudio",
    "workbuddy-macos-x86-64": "WorkBuddy",
    "qwenwork-macos-x86-64": "QwenWork",
    "doubaowork-macos-x86-64": "DoubaoWork",
}
FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usage_row(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    aliases = {
        "input_tokens": ("input_tokens", "inputTokens"),
        "cached_input_tokens": ("cached_input_tokens", "cachedInputTokens", "cache_read_input_tokens"),
        "output_tokens": ("output_tokens", "outputTokens"),
        "reasoning_output_tokens": ("reasoning_output_tokens", "reasoningOutputTokens"),
        "total_tokens": ("total_tokens", "totalTokens"),
    }
    result: dict[str, int] = {}
    for field, names in aliases.items():
        number = next((_int(value.get(name)) for name in names if _int(value.get(name)) is not None), None)
        if number is None and field == "cached_input_tokens":
            details = value.get("inputTokensDetails") or value.get("input_tokens_details")
            if isinstance(details, list) and details:
                number = sum(_int(item.get("cached_tokens")) or 0 for item in details if isinstance(item, dict))
        if field == "reasoning_output_tokens" and number is None:
            details = value.get("outputTokensDetails") or value.get("output_tokens_details")
            if isinstance(details, list) and details:
                number = sum(_int(item.get("reasoning_tokens")) or 0 for item in details if isinstance(item, dict))
            else:
                number = 0
        if field == "total_tokens" and number is None:
            input_value = _int(value.get("input_tokens")) or _int(value.get("inputTokens"))
            output_value = _int(value.get("output_tokens")) or _int(value.get("outputTokens"))
            if input_value is not None and output_value is not None:
                number = input_value + output_value
        if number is None:
            return None
        result[field] = number
    if result["total_tokens"] != result["input_tokens"] + result["output_tokens"]:
        return None
    if result["cached_input_tokens"] > result["input_tokens"] or result["reasoning_output_tokens"] > result["output_tokens"]:
        return None
    return result


def _series_from_astron(path: Path) -> list[dict[str, Any]]:
    previous = {field: 0 for field in FIELDS}
    cumulative = {field: 0 for field in FIELDS}
    series: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        payload = event.get("payload") or {}
        if event.get("type") != "event_msg" or payload.get("type") != "token_count":
            continue
        total = _usage_row(payload.get("info", {}).get("total_token_usage"))
        last = _usage_row(payload.get("info", {}).get("last_token_usage"))
        if total is None or last is None or total == previous:
            continue
        if any(total[field] < previous[field] for field in FIELDS):
            continue
        if any(total[field] != previous[field] + last[field] for field in FIELDS):
            continue
        for field in FIELDS:
            cumulative[field] += last[field]
        series.append({
            "interaction_index": len(series) + 1,
            "raw_line": line_number,
            **last,
            **{f"cumulative_{field}": cumulative[field] for field in FIELDS},
        })
        previous = total
    return series


def _walk_usage(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_usage(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_usage(child)


def _series_from_jsonl(path: Path) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        document = json.loads(line)
        preferred: list[Any] = []
        if isinstance(document, dict) and isinstance(document.get("providerData"), dict):
            preferred.append(document["providerData"].get("usage"))
        if isinstance(document, dict):
            preferred.append(document.get("usage"))
        candidates = [item for item in preferred if item is not None]
        if not candidates:
            candidates = list(_walk_usage(document))
        usage = next((_usage_row(item) for item in candidates if _usage_row(item)), None)
        if usage is None:
            continue
        request_id = None
        for key in ("request_id", "requestId", "message_id", "messageId", "provider_message_id"):
            if isinstance(document, dict) and document.get(key):
                request_id = document[key]
                break
        signature = (request_id, *(usage[field] for field in FIELDS))
        if signature in seen:
            continue
        seen.add(signature)
        series.append({"interaction_index": len(series) + 1, "raw_line": line_number, **usage})
    cumulative = {field: 0 for field in FIELDS}
    for row in series:
        for field in FIELDS:
            cumulative[field] += row[field]
            row[f"cumulative_{field}"] = cumulative[field]
    return series


def _find_raw(round_root: Path, harness: str, task_id: str) -> tuple[Path | None, str]:
    harness_dir = round_root / harness
    task_dir = harness_dir / "score" / "tasks" / task_id
    candidates = {
        "AstronStudio": task_dir / "trace/supplemental/raw/astronstudio-rollout.jsonl",
        "WorkBuddy": task_dir / "trace/as-executed/raw/workbuddy-session.jsonl",
        "QwenWork": task_dir / "trace/as-executed/raw/transcript.jsonl",
    }
    selected = candidates.get(harness)
    if selected and selected.is_file():
        return selected, "rollout" if harness == "AstronStudio" else "normalized-transcript"
    return None, "unavailable"


def _slope(values: list[int]) -> float | None:
    if len(values) < 2:
        return None
    x_mean = (len(values) + 1) / 2
    y_mean = statistics.mean(values)
    denominator = sum((index + 1 - x_mean) ** 2 for index in range(len(values)))
    return sum((index + 1 - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator


def _task_summary(series: list[dict[str, Any]]) -> dict[str, Any]:
    inputs = [row["input_tokens"] for row in series]
    outputs = [row["output_tokens"] for row in series]
    first = inputs[0] if inputs else None
    last = inputs[-1] if inputs else None
    return {
        "interaction_count": len(series),
        "first_input_tokens": first,
        "last_input_tokens": last,
        "last_to_first_input_ratio": (last / first) if first else None,
        "input_growth_tokens": (last - first) if first is not None and last is not None else None,
        "input_slope_tokens_per_interaction": _slope(inputs),
        "input_tokens_sum": sum(inputs) if inputs else None,
        "cached_input_tokens_sum": sum(row["cached_input_tokens"] for row in series) if series else None,
        "output_tokens_sum": sum(outputs) if outputs else None,
        "reasoning_output_tokens_sum": sum(row["reasoning_output_tokens"] for row in series) if series else None,
        "peak_input_tokens": max(inputs) if inputs else None,
        "series": series,
    }


def _median(values: list[float | int | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return statistics.median(valid) if valid else None


def _curve(summaries: list[dict[str, Any]], points: int = 11) -> list[dict[str, Any]]:
    result = []
    for point in range(points):
        values = []
        fraction = point / (points - 1)
        for summary in summaries:
            series = summary["series"]
            if not series:
                continue
            index = round(fraction * (len(series) - 1))
            values.append(series[index]["input_tokens"])
        result.append({"normalized_progress": fraction, "median_input_tokens": _median(values), "task_count": len(values)})
    return result


def analyze(round_root: Path, report_json: Path, include_doubao: bool = False) -> dict[str, Any]:
    report = json.loads(report_json.read_text(encoding="utf-8"))
    tasks = report["tasks"]
    by_harness: dict[str, dict[str, Any]] = {}
    task_rows = []
    for task in tasks:
        harness = HARNESS_NAMES.get(task["unit_id"], task["harness"]["id"])
        if harness == "DoubaoWork" and not include_doubao:
            continue
        raw, source_kind = _find_raw(round_root, harness, task["task_id"])
        if raw is None:
            series = []
            source = None
        elif harness == "AstronStudio":
            series = _series_from_astron(raw)
            source = {"path": str(raw), "sha256": sha256(raw)}
        else:
            series = _series_from_jsonl(raw)
            source = {"path": str(raw), "sha256": sha256(raw)}
        summary = _task_summary(series)
        task_rows.append({"harness": harness, "unit_id": task["unit_id"], "task_id": task["task_id"],
                          "source_kind": source_kind, "source": source, **{k: v for k, v in summary.items() if k != "series"},
                          "series": series})
        by_harness.setdefault(harness, {"task_summaries": [], "coverage": {"known_tasks": 0, "total_tasks": 0}})["task_summaries"].append(summary)
    for harness, group in by_harness.items():
        summaries = group["task_summaries"]
        group["coverage"] = {"known_tasks": sum(bool(s["series"]) for s in summaries), "total_tasks": len(summaries)}
        group["aggregate"] = {
            "median_first_input_tokens": _median([s["first_input_tokens"] for s in summaries]),
            "median_last_input_tokens": _median([s["last_input_tokens"] for s in summaries]),
            "median_last_to_first_input_ratio": _median([s["last_to_first_input_ratio"] for s in summaries]),
            "median_input_slope_tokens_per_interaction": _median([s["input_slope_tokens_per_interaction"] for s in summaries]),
            "sum_input_tokens": sum(s["input_tokens_sum"] or 0 for s in summaries),
            "sum_cached_input_tokens": sum(s["cached_input_tokens_sum"] or 0 for s in summaries),
            "sum_output_tokens": sum(s["output_tokens_sum"] or 0 for s in summaries),
            "sum_reasoning_output_tokens": sum(s["reasoning_output_tokens_sum"] or 0 for s in summaries),
        }
        group["median_input_curve"] = _curve(summaries)
        del group["task_summaries"]
    return {
        "schema_version": "wildclawbench.general-e2e-token-growth/v1",
        "report_source": str(report_json),
        "scope": {"selected_task_runs": len(task_rows), "excluded_harnesses": [] if include_doubao else ["DoubaoWork"]},
        "attribution": {
            "system_prompt_tokens": {"status": "unavailable", "reason": "完整 outbound request 的 role 级 payload 未随当前证据冻结，不能从 usage 反推"},
            "static_baseline_proxy": {"status": "observed", "definition": "首个模型请求的 input_tokens；包含系统、工具定义、任务Prompt和首轮上下文，不能当作纯系统Prompt"},
            "dynamic_context_growth": {"status": "observed", "definition": "同题最后一次 input_tokens 减首轮 input_tokens；包含历史、工具结果和运行时注入"},
        },
        "harnesses": by_harness,
        "tasks": task_rows,
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = ["# General E2E 模型交互 Token 增长分析", "", "当前分析按题目内模型请求序号统计；系统提示词精确拆分在缺少完整 outbound request 时保持 unavailable。", "", "## Harness 汇总", "", "| Harness | 任务覆盖 | 首轮输入中位数 | 末轮输入中位数 | 末轮/首轮 | 输入斜率 | 输入总量 | 缓存读取 | 输出总量 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for harness, group in data["harnesses"].items():
        a = group["aggregate"]
        lines.append(f"| {harness} | {group['coverage']['known_tasks']}/{group['coverage']['total_tasks']} | {a['median_first_input_tokens']} | {a['median_last_input_tokens']} | {a['median_last_to_first_input_ratio']} | {a['median_input_slope_tokens_per_interaction']} | {a['sum_input_tokens']} | {a['sum_cached_input_tokens']} | {a['sum_output_tokens']} |")
    lines += ["", "## 口径", "", "- AstronStudio 仅读取绑定的 `astronstudio-rollout.jsonl`；不读取 `astronstudio-provider-events.jsonl` 作为正式 Token 来源。", "- WorkBuddy 使用冻结评分轨迹中的 session JSONL，QwenWork 使用冻结 transcript JSONL。", "- `首轮输入`是动态系统/工具/任务混合基线，不能等同于系统提示词大小。", "- `末轮/首轮`和输入斜率用于判断滚雪球；请求数、输出和推理输出单独统计，不重复相加。", "- DoubaoWork 默认排除，因为当前没有可比较的 Token usage。", "", "## 证据边界", "", "精确拆分系统提示词、开发者提示词、工具 Schema、历史消息和工具结果，需要保存完整 outbound request 的角色级 payload；当前证据不足时不估算。"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-root", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--include-doubao", action="store_true")
    args = parser.parse_args()
    result = analyze(args.round_root.resolve(), args.report_json.resolve(), args.include_doubao)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"status": "PASS", "output_json": str(args.output_json), "output_md": str(args.output_md), "tasks": result["scope"]["selected_task_runs"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
