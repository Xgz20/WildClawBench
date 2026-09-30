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


def _mean(values: list[float | int | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return statistics.mean(valid) if valid else None


def _percentile(values: list[float | int | None], quantile: float) -> float | None:
    valid = sorted(float(value) for value in values if value is not None)
    if not valid:
        return None
    rank = max(0, min(len(valid) - 1, math.ceil(quantile * len(valid)) - 1))
    return valid[rank]


def _curve(summaries: list[dict[str, Any]], points: int = 11) -> list[dict[str, Any]]:
    result = []
    baseline_values = [summary["series"][0]["input_tokens"] for summary in summaries if summary["series"]]
    baseline = _median(baseline_values)
    for point in range(points):
        values = []
        fraction = point / (points - 1)
        for summary in summaries:
            series = summary["series"]
            if not series:
                continue
            index = round(fraction * (len(series) - 1))
            values.append(series[index]["input_tokens"])
        median_input = _median(values)
        result.append({"normalized_progress": fraction, "median_input_tokens": median_input,
                       "delta_from_zero_tokens": None if median_input is None or baseline is None else median_input - baseline,
                       "baseline_zero_progress_median": baseline, "task_count": len(values)})
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
            "p90_first_input_tokens": _percentile([s["first_input_tokens"] for s in summaries], 0.90),
            "median_last_input_tokens": _median([s["last_input_tokens"] for s in summaries]),
            "p90_last_input_tokens": _percentile([s["last_input_tokens"] for s in summaries], 0.90),
            "median_last_to_first_input_ratio": _median([s["last_to_first_input_ratio"] for s in summaries]),
            "p90_last_to_first_input_ratio": _percentile([s["last_to_first_input_ratio"] for s in summaries], 0.90),
            "median_input_slope_tokens_per_interaction": _median([s["input_slope_tokens_per_interaction"] for s in summaries]),
            "p90_input_slope_tokens_per_interaction": _percentile([s["input_slope_tokens_per_interaction"] for s in summaries], 0.90),
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
        "methodology": {
            "interaction_unit": "同一 task_run 内按 usage advance 排序的模型请求；interaction_index 从1开始",
            "first_input_tokens": "该 task_run 的第一个有效模型请求 input_tokens",
            "last_input_tokens": "该 task_run 的最后一个有效模型请求 input_tokens",
            "median_across_tasks": "先对每个 task_run 求首轮/末轮值，再在 Harness 内跨 task_run 求 median；偶数样本取中间两个排序值的算术平均",
            "p90_across_tasks": "先对每个 task_run 求值，再取排序后的最近秩 P90；用于展示长尾任务，不代表平均任务",
            "last_to_first_input_ratio": "last_input_tokens / first_input_tokens；首轮为0时 unavailable",
            "input_slope_tokens_per_interaction": "每题以k=1..n为有效请求序号、y_k为单次input_tokens，拟合y_hat_k=a+b*k；b=Σ((k-k_bar)*(y_k-y_bar))/Σ((k-k_bar)^2)，a=y_bar-b*k_bar。a是k=0的拟合截距，不是首轮输入或系统提示词Token；b单位为Token/交互。Harness汇总对题级b取中位数和P90，n<2不纳入斜率",
            "input_tokens_definition": "每次模型请求的输入 Token，包含缓存读取 Token；cache_read 单独统计，不能从 input_tokens 中扣除后再称为输入总量",
            "source_policy": "AstronStudio 使用绑定 rollout 的 last_token_usage；WorkBuddy/QwenWork 使用冻结轨迹 usage；provider events 不用于 AstronStudio正式Token统计",
        },
        "attribution": {
            "system_prompt_tokens": {"status": "unavailable", "reason": "完整 outbound request 的 role 级 payload 未随当前证据冻结，不能从 usage 反推"},
            "static_baseline_proxy": {"status": "observed", "definition": "首个模型请求的 input_tokens；包含系统、工具定义、任务Prompt和首轮上下文，不能当作纯系统Prompt"},
            "dynamic_context_growth": {"status": "observed", "definition": "同题最后一次 input_tokens 减首轮 input_tokens；包含历史、工具结果和运行时注入"},
        },
        "harnesses": by_harness,
        "tasks": task_rows,
    }


def render_markdown(data: dict[str, Any]) -> str:
    def fmt(value: Any) -> str:
        if value is None:
            return "unavailable"
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)

    lines = [
        "# General E2E 模型交互 Token 增长分析",
        "",
        "当前分析按题目内模型请求序号统计；系统提示词精确拆分在缺少完整 outbound request 时保持 unavailable。",
        "",
        "## Harness 汇总",
        "",
        "下表以任务级中位数描述典型题目，以P90描述长尾题目；总量描述整个Harness的实际消耗。平均值不作为主指标，以免被少数超长任务主导。",
        "",
        "| Harness | 任务覆盖 | 首轮输入中位数 | 首轮输入P90 | 末轮输入中位数 | 末轮输入P90 | 末轮/首轮中位数 | 末轮/首轮P90 | 斜率中位数 | 斜率P90 | 输入总量 | 缓存读取 | 输出总量 | 推理输出总量 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for harness, group in data["harnesses"].items():
        a = group["aggregate"]
        lines.append(
            f"| {harness} | {group['coverage']['known_tasks']}/{group['coverage']['total_tasks']} | "
            f"{fmt(a['median_first_input_tokens'])} | {fmt(a['p90_first_input_tokens'])} | "
            f"{fmt(a['median_last_input_tokens'])} | {fmt(a['p90_last_input_tokens'])} | "
            f"{fmt(a['median_last_to_first_input_ratio'])} | {fmt(a['p90_last_to_first_input_ratio'])} | "
            f"{fmt(a['median_input_slope_tokens_per_interaction'])} | {fmt(a['p90_input_slope_tokens_per_interaction'])} | {fmt(a['sum_input_tokens'])} | "
            f"{fmt(a['sum_cached_input_tokens'])} | {fmt(a['sum_output_tokens'])} | "
            f"{fmt(a['sum_reasoning_output_tokens'])} |"
        )
    lines += [
        "", "## 输入斜率：a、b、k 的含义与计算", "",
        "对每题分别用全部有效请求的数据拟合直线 `ŷ_k = a + b × k`。`ŷ_k` 是拟合值，实际输入量 `y_k` 可以高于或低于这条直线。",
        "",
        "| 符号 | 取值与含义 | 单位 |",
        "| --- | --- | --- |",
        "| `n` | 该题有效模型请求数，即 `interaction_count` | 次 |",
        "| `k` | 该题内的请求序号 `1, 2, …, n`，即 `interaction_index`；每道题从1重新编号 | 次 |",
        "| `y_k` | 第k次请求实际记录的 `input_tokens`，包含缓存读取；不是截至第k次的累计输入 | Token |",
        "| `b` | 利用全部n个点计算的最小二乘斜率，表示每增加一次请求时输入上下文的线性增长趋势 | Token/交互 |",
        "| `a` | 拟合直线在k=0处的截距，由本题数据计算；不是预设常量，不是首轮实际输入，也不是系统提示词Token | Token |",
        "",
        "计算公式（求和范围均为 `k=1..n`）：", "",
        "```text",
        "k̄ = (n + 1) / 2                  # 本题请求序号的均值",
        "ȳ = Σ y_k / n                    # 本题单次输入Token的均值",
        "b = Σ[(k − k̄)(y_k − ȳ)] / Σ[(k − k̄)²]",
        "a = ȳ − b × k̄",
        "ŷ_k = a + b × k",
        "```", "",
        "计算示例（仅演示公式，不是本轮真实用例）：某题4次请求的输入为 `[1000, 1400, 1600, 2200]`，对应 `k=[1,2,3,4]`。此时 `k̄=2.5`、`ȳ=1550`，斜率分子为1900、分母为5，因此 `b=380 Token/交互`，`a=600 Token`，拟合直线为 `ŷ_k=600+380×k`。首轮实际输入仍为1000 Token，不能用截距600替代。",
        "",
        "这里的b描述整体线性趋势，不保证相邻两次请求都恰好增加b。它使用全部请求点，也不等于只用首尾两点计算的 `(末轮−首轮)/(n−1)`；上述示例的首尾平均增量是400，而拟合斜率是380。b为负时表示整体下降趋势；压缩、裁剪或其他上下文变化的原因须回查轨迹。",
        "",
        "代码先通过 `_slope` 计算每题的b，再对有效题级b取中位数与P90；不会把60题请求拼成一条长序列拟合。n小于2时斜率为unavailable并排除，不补0。a仅用于解释拟合直线，当前汇总指标保存的是b。本题拟合所用的均值与跨60题报告是否展示平均值是不同层次的计算。",
    ]
    lines += ["", "## 三端上下文滚雪球趋势", "", "下面按每题交互进度归一化到0%–100%，每个点先在每题内取最近的请求，再跨题取中位数。它展示典型任务的输入上下文如何随交互推进。", ""]
    for harness, group in data["harnesses"].items():
        lines += [f"### {harness}", "", "| 交互进度 | 典型输入 Token 中位数 | 相对0%增量(Token) | 任务数 |", "| ---: | ---: | ---: | ---: |"]
        for point in group["median_input_curve"]:
            delta = point["delta_from_zero_tokens"]
            delta_text = "unavailable" if delta is None else f"{delta:+.0f}"
            lines.append(f"| {point['normalized_progress']:.0%} | {fmt(point['median_input_tokens'])} | {delta_text} | {point['task_count']} |")
        lines.append("")
    lines += ["## 每题级汇总", "", "每行是一题；`interaction_count` 是该题内有效模型请求数。首轮、末轮、增长倍数、斜率和累计字段均来自该题自己的请求序列。", "", "| Harness | task_id | 请求数 | 首轮输入 | 末轮输入 | 增长倍数 | 输入斜率 | 累计输入 | 累计缓存读取 | 累计输出 | 累计推理输出 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in data["tasks"]:
        lines.append(
            f"| {row['harness']} | {row['task_id']} | {row['interaction_count']} | {fmt(row['first_input_tokens'])} | "
            f"{fmt(row['last_input_tokens'])} | {fmt(row['last_to_first_input_ratio'])} | {fmt(row['input_slope_tokens_per_interaction'])} | "
            f"{fmt(row['input_tokens_sum'])} | {fmt(row['cached_input_tokens_sum'])} | {fmt(row['output_tokens_sum'])} | "
            f"{fmt(row['reasoning_output_tokens_sum'])} |"
        )
    lines += ["", "## 每题请求级明细", "", "下表保留每题内第几次模型请求，以及单次和累计输入、缓存读取、输出、推理输出和总 Token。AstronStudio 的这些行来自 rollout，其他两端来自冻结标准轨迹。", "", "| Harness | task_id | 交互序号 | 单次输入 | 单次缓存读取 | 单次输出 | 单次推理输出 | 单次总量 | 累计输入 | 累计缓存读取 | 累计输出 | 累计推理输出 | 累计总量 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in data["tasks"]:
        for point in row["series"]:
            lines.append(
                f"| {row['harness']} | {row['task_id']} | {point['interaction_index']} | {fmt(point['input_tokens'])} | "
                f"{fmt(point['cached_input_tokens'])} | {fmt(point['output_tokens'])} | {fmt(point['reasoning_output_tokens'])} | {fmt(point['total_tokens'])} | "
                f"{fmt(point['cumulative_input_tokens'])} | {fmt(point['cumulative_cached_input_tokens'])} | {fmt(point['cumulative_output_tokens'])} | "
                f"{fmt(point['cumulative_reasoning_output_tokens'])} | {fmt(point['cumulative_total_tokens'])} |"
            )
    lines += ["", "## 统计口径", "", "- `首轮输入中位数`和`末轮输入中位数`不是60题所有请求混合后的中位数，而是先逐题取首轮/末轮，再对60个题级值取中位数；60题为偶数时取排序后第30和第31个值的算术平均。", "- `P90`同样先逐题取值，再按最近秩取排序后的P90，用来表示长尾题目；它不是平均值。", "- 每题斜率使用普通最小二乘拟合 `ŷ_k = a + b × k`，符号和公式见前文；随后对题级斜率b取中位数和P90。少于2次请求的题目不纳入斜率。", "- 主分析不使用跨题平均值，因为少数超长代码/搜索任务会显著拉高均值；整体资源负担直接看输入总量、缓存读取总量、输出总量和推理输出总量。", "- 输入 Token 包含缓存读取 Token；缓存读取单独列出，不能从输入中扣除后再次相加。输出 Token、推理输出 Token、请求数和工具调用数分别统计。", "- `末轮/首轮`用于观察上下文滚雪球，不等于系统提示词增长倍数。", "", "## 数据来源", "", "- AstronStudio：绑定 `astronstudio-rollout.jsonl` 的 `last_token_usage`，累计值和单次值对账后去重。", "- WorkBuddy：冻结 `workbuddy-session.jsonl` 中每个模型响应的 usage。", "- QwenWork：冻结 `transcript.jsonl` 中每个模型响应的 usage。", "- AstronStudio 的 `astronstudio-provider-events.jsonl` 只用于独立核对，不作为正式 Token 来源。", "- DoubaoWork 默认排除，因为当前没有可比较的 Token usage。", "", "## 证据边界", "", "精确拆分系统提示词、开发者提示词、工具 Schema、历史消息和工具结果，需要完整 outbound request 的 role 级 payload；当前证据不足时不估算。"]
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
