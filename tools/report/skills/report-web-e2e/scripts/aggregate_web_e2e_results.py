#!/usr/bin/env python3
"""Aggregate standalone Web E2E submissions into report data and Markdown."""
from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
import tarfile
import zipfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("缺少 pyyaml，请先安装：pip install pyyaml")


SUBMISSION_SCHEMA = "wildclawbench.web-e2e-submission/v1"
REPORT_CONFIG_SCHEMA = "wildclawbench.web-e2e-report-config/v1"
PRIMARY_LABELS = {
    "content_structure": "内容与结构",
    "interaction_function": "交互与功能",
    "visual_layout": "视觉与布局",
}
SECONDARY_LABELS = {
    "basic_content": "基础内容",
    "information_organization": "信息组织",
    "lists_tables": "列表与表格",
    "detail_display": "详情展示",
    "data_visualization": "数据可视化",
    "page_navigation": "页面导航",
    "content_switching": "内容切换",
    "form_validation": "表单填写与校验",
    "operation_feedback": "操作反馈",
    "state_persistence": "状态持久化",
    "cross_region_linkage": "跨区域联动",
    "filtering_sorting": "筛选与排序",
    "search_filtering": "搜索与筛选",
    "popup_overlay": "弹窗与浮层",
    "search": "搜索",
    "content_editing": "内容创建与编辑",
    "file_upload_and_download": "文件上传与下载",
    "realtime_auto_progress": "实时自动推进",
    "rule_settlement": "规则结算",
    "visual_style": "视觉风格",
    "page_layout": "页面布局",
    "component_style": "组件样式",
    "responsive_layout": "响应式布局",
}
SECONDARY_PRIMARY = {
    "basic_content": "content_structure",
    "information_organization": "content_structure",
    "lists_tables": "content_structure",
    "detail_display": "content_structure",
    "data_visualization": "content_structure",
    "page_navigation": "interaction_function",
    "content_switching": "interaction_function",
    "form_validation": "interaction_function",
    "operation_feedback": "interaction_function",
    "state_persistence": "interaction_function",
    "cross_region_linkage": "interaction_function",
    "filtering_sorting": "interaction_function",
    "search_filtering": "interaction_function",
    "popup_overlay": "interaction_function",
    "search": "interaction_function",
    "content_editing": "interaction_function",
    "file_upload_and_download": "interaction_function",
    "realtime_auto_progress": "interaction_function",
    "rule_settlement": "interaction_function",
    "visual_style": "visual_layout",
    "page_layout": "visual_layout",
    "component_style": "visual_layout",
    "responsive_layout": "visual_layout",
}
AESTHETIC_PRIMARY_LABELS = {
    "render_integrity": "渲染与完整性(15%)",
    "layout_hierarchy": "页面布局与信息层级(25%)",
    "color_typography": "视觉风格：配色与排版(20%)",
    "component_state": "组件精细度与状态(15%)",
    "responsive": "响应式表现(10%)",
    "tone_fit": "调性契合(15%)",
}
AESTHETIC_SECONDARY_LABELS = {
    "v-01": "v-01 完整渲染",
    "v-02": "v-02 无占位内容",
    "v-03": "v-03 文字与图片完整",
    "v-04": "v-04 桌面无横向滚动",
    "v-05": "v-05 统一栅格与边距",
    "v-06": "v-06 留白有节奏",
    "v-07": "v-07 首屏主次明确",
    "v-08": "v-08 分组分隔清晰",
    "p-01": "p-01 首屏视觉焦点",
    "p-02": "p-02 间距序列",
    "v-09": "v-09 色板收敛",
    "v-10": "v-10 字体层级",
    "v-11": "v-11 正文对比度",
    "v-12": "v-12 行高字距舒适",
    "p-03": "p-03 语义色阶",
    "p-04": "p-04 字号序列与行长",
    "v-13": "v-13 组件样式一致",
    "v-14": "v-14 非默认控件",
    "v-15": "v-15 空状态设计",
    "v-16": "v-16 组件状态可辨",
    "p-05": "p-05 多类状态设计",
    "p-06": "p-06 一致交互反馈",
    "v-17": "v-17 窄屏无溢出",
    "v-18": "v-18 窄屏合理重排",
    "v-19": "v-19 窄屏可读可点",
    "p-07": "p-07 窄屏布局重构",
    "p-08": "p-08 窄屏优先级重排",
    "v-20": "v-20 契合业务场景",
    "v-21": "v-21 装饰克制",
    "v-22": "v-22 中文排版",
    "p-09": "p-09 业务定制细节",
    "p-10": "p-10 视觉语言一致",
}
AESTHETIC_SECONDARY_PRIMARY = {
    **{key: "render_integrity" for key in ("v-01", "v-02", "v-03", "v-04")},
    **{key: "layout_hierarchy" for key in ("v-05", "v-06", "v-07", "v-08", "p-01", "p-02")},
    **{key: "color_typography" for key in ("v-09", "v-10", "v-11", "v-12", "p-03", "p-04")},
    **{key: "component_state" for key in ("v-13", "v-14", "v-15", "v-16", "p-05", "p-06")},
    **{key: "responsive" for key in ("v-17", "v-18", "v-19", "p-07", "p-08")},
    **{key: "tone_fit" for key in ("v-20", "v-21", "v-22", "p-09", "p-10")},
}


def load_submission(path: Path) -> dict:
    suffix = path.name.lower()
    if suffix.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            candidates = [name for name in archive.namelist() if Path(name).name == "submission.json"]
            if len(candidates) != 1:
                raise ValueError(f"zip 中 submission.json 应唯一: {path}")
            raw = archive.read(candidates[0])
    elif suffix.endswith(".tar.gz") or suffix.endswith(".tgz"):
        with tarfile.open(path, "r:gz") as archive:
            candidates = [member for member in archive.getmembers() if Path(member.name).name == "submission.json" and member.isfile()]
            if len(candidates) != 1:
                raise ValueError(f"tar.gz 中 submission.json 应唯一: {path}")
            handle = archive.extractfile(candidates[0])
            if handle is None:
                raise ValueError(f"无法读取 submission.json: {path}")
            raw = handle.read()
    else:
        raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SUBMISSION_SCHEMA:
        raise ValueError(f"submission schema 不兼容: {path}")
    return payload


def load_report_config(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or payload.get("schema_version") != REPORT_CONFIG_SCHEMA:
        raise ValueError(f"报告配置 schema 不兼容: {path}")
    batch_id = str(payload.get("batch_id") or "").strip()
    raw_units = payload.get("units") or []
    if not batch_id or not isinstance(raw_units, list) or not raw_units:
        raise ValueError(f"报告配置必须包含 batch_id 和非空 units: {path}")
    units = []
    seen = set()
    for index, raw in enumerate(raw_units, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"报告配置 units[{index}] 必须是对象: {path}")
        model_id = str(raw.get("model_id") or "").strip()
        harness_id = str(raw.get("harness_id") or "").strip()
        if not model_id or not harness_id:
            raise ValueError(f"报告配置 units[{index}] 缺少 model_id 或 harness_id: {path}")
        key = (model_id, harness_id)
        if key in seen:
            raise ValueError(f"报告配置存在重复 model@harness: {model_id}@{harness_id}")
        seen.add(key)
        order = raw.get("order", index)
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            raise ValueError(f"报告配置 units[{index}].order 必须是正整数: {path}")
        units.append({
            "model_id": model_id,
            "model_display_name": str(raw.get("model_display_name") or model_id).strip(),
            "harness_id": harness_id,
            "harness_display_name": str(raw.get("harness_display_name") or harness_id).strip(),
            "reasoning_effort": str(raw.get("reasoning_effort") or "").strip(),
            "order": order,
        })
    if len({item["order"] for item in units}) != len(units):
        raise ValueError(f"报告配置 unit order 必须唯一: {path}")
    return {"schema_version": REPORT_CONFIG_SCHEMA, "batch_id": batch_id, "units": units}


def configured_submissions(submissions: list[dict], config: dict | None) -> list[dict]:
    if config is None:
        return submissions
    batch_ids = {item.get("batch_id") for item in submissions}
    if batch_ids != {config.get("batch_id")}:
        raise ValueError(f"报告配置 batch_id 与回传包不一致: {config.get('batch_id')} vs {sorted(str(v) for v in batch_ids)}")
    config_by_key = {
        (item["model_id"], item["harness_id"]): item
        for item in config.get("units") or []
    }
    resolved = copy.deepcopy(submissions)
    matched = set()
    for submission in resolved:
        raw_unit = submission["unit"]
        raw_model_id = str(raw_unit.get("model_id") or "")
        raw_harness_id = str(raw_unit.get("harness_id") or "")
        candidates = [
            (key, value) for key, value in config_by_key.items()
            if key[1] == raw_harness_id and (not raw_model_id or key[0] == raw_model_id)
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"回传单元无法唯一匹配报告配置: model_id={raw_model_id or '<empty>'}, "
                f"harness_id={raw_harness_id or '<empty>'}, matches={len(candidates)}"
            )
        key, configured = candidates[0]
        if key in matched:
            raise ValueError(f"存在重复 model@harness 回传包: {key[0]}@{key[1]}")
        matched.add(key)
        raw_unit.update({
            "model_id": configured["model_id"],
            "model_display_name": configured["model_display_name"],
            "harness_display_name": configured["harness_display_name"],
            "reasoning_effort": configured["reasoning_effort"],
            "sort_order": configured["order"],
        })
        for task in submission.get("tasks") or []:
            identity = task.get("identity") or {}
            identity.setdefault("model", {}).update({
                "id": configured["model_id"],
                "display_name": configured["model_display_name"],
            })
            identity.setdefault("harness", {})["display_name"] = configured["harness_display_name"]
    if matched != set(config_by_key):
        missing = sorted(set(config_by_key) - matched)
        raise ValueError(f"报告配置与回传 model@harness 范围不一致，缺少 {missing}")
    return resolved


def numeric(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def complete_sum(values: list):
    numbers = [numeric(value) for value in values]
    return round(sum(numbers), 6) if numbers and all(value is not None for value in numbers) else None


def complete_values(values: list) -> list[float]:
    numbers = [numeric(value) for value in values]
    return numbers if numbers and all(value is not None for value in numbers) else []


def average(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 2)


def dimension_average(tasks: list[dict], key: str, level: str) -> float | None:
    values = []
    for task in tasks:
        dimensions = task.get("metrics", {}).get(level) or {}
        value = numeric(dimensions.get(key))
        if value is not None:
            values.append(value)
    return average(values)


def completed_aesthetic(task: dict) -> dict:
    aesthetic = task.get("metrics", {}).get("aesthetic", {}) or {}
    return aesthetic if aesthetic.get("status") == "completed" else {}


def aesthetic_primary_average(tasks: list[dict], key: str) -> float | None:
    values = [
        numeric((completed_aesthetic(task).get("primary_dimensions") or {}).get(key))
        for task in tasks
    ]
    return average([value for value in values if value is not None])


def aesthetic_checklist_summary(tasks: list[dict], key: str) -> dict:
    counts = {status: 0 for status in ("MET", "PARTIAL", "UNMET", "NA")}
    for task in tasks:
        status = str(
            (completed_aesthetic(task).get("secondary_dimensions") or {}).get(key) or ""
        )
        if status in counts:
            counts[status] += 1
    applicable_count = counts["MET"] + counts["PARTIAL"] + counts["UNMET"]
    score_sum = counts["MET"] * 100 + counts["PARTIAL"] * 50
    average_score = round(score_sum / applicable_count, 2) if applicable_count else None
    return {
        "met_count": counts["MET"],
        "partial_count": counts["PARTIAL"],
        "unmet_count": counts["UNMET"],
        "na_count": counts["NA"],
        "applicable_count": applicable_count,
        "met_rate": round(counts["MET"] / applicable_count * 100, 2) if applicable_count else None,
        "score_sum": score_sum,
        "average_score": average_score,
        "score_rate": average_score,
    }


def format_accuracy(tasks: list[dict]) -> float | None:
    rows = []
    for task in tasks:
        accuracy = numeric((task.get("tools") or {}).get("format_accuracy"))
        calls = numeric((task.get("tools") or {}).get("call_count"))
        if accuracy is None:
            return None
        if 0 <= accuracy <= 1:
            accuracy *= 100
        if not 0 <= accuracy <= 100:
            return None
        rows.append((accuracy, calls))
    if not rows:
        return None
    if all(calls is not None for _, calls in rows) and sum(calls for _, calls in rows) > 0:
        return round(sum(accuracy * calls for accuracy, calls in rows) / sum(calls for _, calls in rows), 2)
    return round(statistics.fmean(accuracy for accuracy, _ in rows), 2)


def unit_summary(submission: dict, primary_keys: list[str], secondary_keys: list[str]) -> dict:
    tasks = submission.get("tasks") or []
    unit = submission["unit"]
    scores = [numeric(task.get("metrics", {}).get("total_score")) or 0.0 for task in tasks]
    execution_statuses = [str(task.get("execution", {}).get("status") or "") for task in tasks]
    evaluation_statuses = [str(task.get("evaluation", {}).get("status") or "") for task in tasks]
    scorable_execution_statuses = {"completed", "not_recorded"}
    completed = sum(e in scorable_execution_statuses and v == "completed" for e, v in zip(execution_statuses, evaluation_statuses))
    execution_errors = sum(status == "execution_error" for status in execution_statuses)
    timeouts = sum(status == "timeout" for status in execution_statuses)
    execution_not_recorded = sum(status == "not_recorded" for status in execution_statuses)
    evaluation_errors = sum(
        execution_status in scorable_execution_statuses and evaluation_status == "evaluation_error"
        for execution_status, evaluation_status in zip(execution_statuses, evaluation_statuses)
    )
    aesthetic_values = [
        numeric(completed_aesthetic(task).get("score"))
        for task in tasks
    ]
    aesthetic_scored = [value for value in aesthetic_values if value is not None]
    durations = complete_values([(task.get("execution") or {}).get("duration_seconds") for task in tasks])
    costs = complete_values([(task.get("usage") or {}).get("cost_usd") for task in tasks])
    total_token_values = complete_values([(task.get("usage") or {}).get("total_tokens") for task in tasks])
    input_token_values = complete_values([(task.get("usage") or {}).get("input_tokens") for task in tasks])
    output_token_values = complete_values([(task.get("usage") or {}).get("output_tokens") for task in tasks])
    return {
        "model": unit["model_display_name"],
        "model_id": unit["model_id"],
        "harness": unit["harness_display_name"],
        "harness_id": unit["harness_id"],
        "unit": f"{unit['model_display_name']}@{unit['harness_display_name']}",
        "reasoning_effort": unit.get("reasoning_effort") or None,
        "sort_order": unit.get("sort_order"),
        "total_average_score": average(scores) or 0.0,
        "score_rate": average(scores) or 0.0,
        "case_count": len(tasks),
        "completed_count": completed,
        "execution_error_count": execution_errors,
        "timeout_count": timeouts,
        "execution_not_recorded_count": execution_not_recorded,
        "evaluation_error_count": evaluation_errors,
        "completion_rate": round(completed / len(tasks) * 100, 2) if tasks else 0.0,
        "strict_full_score_rate": round(sum(score == 100 for score in scores) / len(tasks) * 100, 2) if tasks else 0.0,
        "aesthetic_score": average(aesthetic_scored),
        "aesthetic_sample_count": len(aesthetic_scored),
        "average_duration_seconds": average(durations),
        "duration_p50_seconds": percentile(durations, 0.5),
        "duration_p90_seconds": percentile(durations, 0.9),
        "average_cost_usd": average(costs),
        "average_total_tokens": average(total_token_values),
        "average_input_tokens": average(input_token_values),
        "average_output_tokens": average(output_token_values),
        "total_tokens": round(sum(total_token_values), 6) if total_token_values else None,
        "total_requests": complete_sum([(task.get("usage") or {}).get("request_count") for task in tasks]),
        "total_duration_seconds": complete_sum([(task.get("execution") or {}).get("duration_seconds") for task in tasks]),
        "total_cost_usd": complete_sum([(task.get("usage") or {}).get("cost_usd") for task in tasks]),
        "tool_call_count": complete_sum([(task.get("tools") or {}).get("call_count") for task in tasks]),
        "format_accuracy": format_accuracy(tasks),
        "primary_dimensions": {key: dimension_average(tasks, key, "primary_dimensions") for key in primary_keys},
        "secondary_dimensions": {key: dimension_average(tasks, key, "secondary_dimensions") for key in secondary_keys},
        "aesthetic_primary_dimensions": {
            key: aesthetic_primary_average(tasks, key) for key in AESTHETIC_PRIMARY_LABELS
        },
        "aesthetic_secondary_dimensions": {
            key: aesthetic_checklist_summary(tasks, key) for key in AESTHETIC_SECONDARY_LABELS
        },
    }


def build_report_data(submissions: list[dict], config: dict | None = None) -> dict:
    if not submissions:
        raise ValueError("至少提供一个回传包")
    submissions = configured_submissions(submissions, config)
    batch_ids = {item.get("batch_id") for item in submissions}
    revisions = {item.get("source_revision") for item in submissions}
    task_sets = {tuple(item.get("task_ids") or []) for item in submissions}
    if len(batch_ids) != 1:
        raise ValueError(f"batch_id 不一致: {sorted(str(v) for v in batch_ids)}")
    if len(revisions) != 1:
        raise ValueError(f"source_revision 不一致: {sorted(str(v) for v in revisions)}")
    if len(task_sets) != 1:
        raise ValueError("回传包 task_ids 或顺序不一致")
    units = [
        (item["unit"]["model_id"], item["unit"]["harness_id"])
        for item in submissions
    ]
    if len(units) != len(set(units)):
        raise ValueError("存在重复 model@harness 回传包")

    primary_keys = list(PRIMARY_LABELS)
    primary_keys.extend(sorted({
        key for item in submissions for task in item.get("tasks", [])
        for key in (task.get("metrics", {}).get("primary_dimensions") or {})
        if key not in PRIMARY_LABELS
    }))
    secondary_keys = [
        key for key in SECONDARY_LABELS
        if any(key in (task.get("metrics", {}).get("secondary_dimensions") or {})
               for item in submissions for task in item.get("tasks", []))
    ]
    secondary_keys.extend(sorted({
        key for item in submissions for task in item.get("tasks", [])
        for key in (task.get("metrics", {}).get("secondary_dimensions") or {})
        if key not in SECONDARY_LABELS
    }))
    difficulty_values = sorted({
        str(task.get("identity", {}).get("difficulty") or "unknown")
        for item in submissions for task in item.get("tasks", [])
    }, key=lambda value: (not value.startswith("L"), value))
    summaries = [unit_summary(item, primary_keys, secondary_keys) for item in submissions]
    if config is None:
        summaries.sort(key=lambda item: (-item["total_average_score"], item["unit"]))
    else:
        summaries.sort(key=lambda item: (item["sort_order"], item["unit"]))

    difficulty_rows = []
    detail_rows = []
    by_unit = {
        (item["unit"]["model_id"], item["unit"]["harness_id"]): item
        for item in submissions
    }
    for summary in summaries:
        submission = by_unit[(summary["model_id"], summary["harness_id"])]
        tasks = submission.get("tasks") or []
        row = {"unit": summary["unit"], "total_average_score": summary["total_average_score"], "difficulties": {}}
        for difficulty in difficulty_values:
            selected = [
                numeric(task.get("metrics", {}).get("total_score")) or 0.0
                for task in tasks
                if str(task.get("identity", {}).get("difficulty") or "unknown") == difficulty
            ]
            row["difficulties"][difficulty] = {"score": average(selected), "count": len(selected)}
        difficulty_rows.append(row)
        for task in tasks:
            identity = task.get("identity") or {}
            detail_rows.append({
                "task_id": identity.get("task_id"),
                "task_name": identity.get("task_name"),
                "difficulty": identity.get("difficulty"),
                "model": summary["model"],
                "harness": summary["harness"],
                "reasoning_effort": summary["reasoning_effort"],
                "unit": summary["unit"],
                "execution_status": task.get("execution", {}).get("status"),
                "evaluation_status": task.get("evaluation", {}).get("status"),
                "total_score": numeric(task.get("metrics", {}).get("total_score")) or 0.0,
                "aesthetic_score": numeric(completed_aesthetic(task).get("score")),
                "duration_seconds": numeric(task.get("execution", {}).get("duration_seconds")),
                "total_tokens": numeric(task.get("usage", {}).get("total_tokens")),
                "input_tokens": numeric(task.get("usage", {}).get("input_tokens")),
                "output_tokens": numeric(task.get("usage", {}).get("output_tokens")),
                "request_count": numeric(task.get("usage", {}).get("request_count")),
                "cost_usd": numeric(task.get("usage", {}).get("cost_usd")),
                "tool_call_count": numeric(task.get("tools", {}).get("call_count")),
                "format_accuracy": numeric(task.get("tools", {}).get("format_accuracy")),
                "primary_dimensions": task.get("metrics", {}).get("primary_dimensions") or {},
                "secondary_dimensions": task.get("metrics", {}).get("secondary_dimensions") or {},
                "aesthetic_primary_dimensions": completed_aesthetic(task).get("primary_dimensions") or {},
                "aesthetic_secondary_dimensions": completed_aesthetic(task).get("secondary_dimensions") or {},
                "aesthetic_secondary_dimension_scores": completed_aesthetic(task).get("secondary_dimension_scores") or {},
            })
    return {
        "schema_version": "wildclawbench.web-e2e-report-data/v1",
        "batch_id": next(iter(batch_ids)),
        "source_revision": next(iter(revisions)),
        "task_ids": list(next(iter(task_sets))),
        "labels": {
            "primary": {key: PRIMARY_LABELS.get(key, key) for key in primary_keys},
            "secondary": {key: SECONDARY_LABELS.get(key, key) for key in secondary_keys},
            "secondary_primary": {key: SECONDARY_PRIMARY.get(key, "other") for key in secondary_keys},
            "aesthetic_primary": AESTHETIC_PRIMARY_LABELS,
            "aesthetic_secondary": AESTHETIC_SECONDARY_LABELS,
            "aesthetic_secondary_primary": AESTHETIC_SECONDARY_PRIMARY,
        },
        "difficulty_values": difficulty_values,
        "units": summaries,
        "difficulty_rows": difficulty_rows,
        "detail_rows": detail_rows,
    }


def display(value, decimals: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def markdown_table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(display(value) for value in row) + " |" for row in rows)
    return lines


def spread_statement(rows: list[dict], value_getter, labels: dict[str, str]) -> str:
    candidates = []
    for key, display_label in labels.items():
        values = [value_getter(row, key) for row in rows]
        values = [value for value in values if value is not None]
        if len(values) >= 2:
            candidates.append((max(values) - min(values), display_label))
    if not candidates:
        return "当前参评范围不足以形成稳定的横向分差结论。"
    gap, label = max(candidates)
    return f"最大横向分差出现在“{label}”，分差为 {gap:.2f} 分。"


def render_markdown(data: dict) -> str:
    units = data["units"]
    leader = max(units, key=lambda item: (item["total_average_score"], item["unit"]))
    all_aesthetic_missing = all(item["aesthetic_score"] is None for item in units)
    execution_not_recorded = sum(item.get("execution_not_recorded_count", 0) for item in units)
    lines = [
        "# Web 站点端到端评测领导版报告",
        "",
        f"> 批次：{data['batch_id']}  ",
        f"> 源版本：{data['source_revision']}  ",
        f"> 参评范围：{len(units)} 个模型@Harness 单元 × {len(data['task_ids'])} 个 Web 用例",
        "",
        "## 结论",
        "",
        f"- {leader['unit']} 的总平均分最高，为 {leader['total_average_score']:.2f} 分。",
        f"- 各单元完成率区间为 {min(item['completion_rate'] for item in units):.2f}%–{max(item['completion_rate'] for item in units):.2f}%。",
        f"- 共 {execution_not_recorded} 个用例结果未采集执行状态与资源数据；执行错误数和超时数只反映显式记录。" if execution_not_recorded else "- 全部用例均提供执行状态记录。",
        "- 本批次没有可用的页面美观度结果，可能来自旧版评分结果或美观度取证异常；显示为 `-`，不参与总分。" if all_aesthetic_missing else f"- 页面美观度按独立 100 分制展示，共取得 {sum(item['aesthetic_sample_count'] for item in units)} 个用例样本，不参与总分、得分率或满分率。",
        "",
        "## 总览",
        "",
        f"本批次共比较 {len(units)} 个模型@Harness 单元；总平均分范围为 {min(item['total_average_score'] for item in units):.2f}–{max(item['total_average_score'] for item in units):.2f} 分。资源字段只有在单元内全部用例均提供时才汇总，缺失显示 `-`。",
        "",
    ]
    overview_headers = [
        "模型", "Harness", "推理强度", "总平均分", "美观度总分", "用例数", "正常完成数", "执行错误数", "超时数", "评测异常数",
        "完成率", "总tokens", "总请求数", "总耗时(s)", "总成本(USD)", "工具调用数", "格式准确率",
    ]
    overview_rows = [[
        item["model"], item["harness"], item["reasoning_effort"], item["total_average_score"], item["aesthetic_score"], item["case_count"],
        item["completed_count"], item["execution_error_count"], item["timeout_count"],
        item["evaluation_error_count"], item["completion_rate"], item["total_tokens"],
        item["total_requests"], item["total_duration_seconds"], item["total_cost_usd"],
        item["tool_call_count"], item["format_accuracy"],
    ] for item in units]
    lines.extend(markdown_table(overview_headers, overview_rows))

    lines.extend(["", "## 难度等级", ""])
    lines.append(spread_statement(
        data["difficulty_rows"],
        lambda row, label: row["difficulties"].get(label, {}).get("score"),
        {difficulty: difficulty for difficulty in data["difficulty_values"]},
    ))
    lines.append("")
    difficulty_headers = ["模型@Harness", "总平均分"] + [
        f"{difficulty}平均分({next((row['difficulties'][difficulty]['count'] for row in data['difficulty_rows'] if row['difficulties'][difficulty]['count']), 0)}例)"
        for difficulty in data["difficulty_values"]
    ]
    difficulty_table = [[
        row["unit"], row["total_average_score"],
        *[row["difficulties"][difficulty]["score"] for difficulty in data["difficulty_values"]],
    ] for row in data["difficulty_rows"]]
    lines.extend(markdown_table(difficulty_headers, difficulty_table))

    primary_labels = data["labels"]["primary"]
    lines.extend(["", "## 一级维度", "", "### 站点评测一级维度", ""])
    lines.append(spread_statement(
        units,
        lambda row, label: row["primary_dimensions"].get(label),
        primary_labels,
    ))
    lines.append("")
    lines.extend(markdown_table(
        ["模型@Harness", "总平均分"] + list(primary_labels.values()),
        [[item["unit"], item["total_average_score"], *[item["primary_dimensions"].get(key) for key in primary_labels]] for item in units],
    ))

    aesthetic_primary_labels = data["labels"]["aesthetic_primary"]
    lines.extend(["", "### 美观度一级维度", ""])
    lines.append(spread_statement(
        units,
        lambda row, label: row["aesthetic_primary_dimensions"].get(label),
        aesthetic_primary_labels,
    ))
    lines.append("")
    lines.extend(markdown_table(
        ["模型@Harness", "美观度总分"] + list(aesthetic_primary_labels.values()),
        [[item["unit"], item["aesthetic_score"], *[item["aesthetic_primary_dimensions"].get(key) for key in aesthetic_primary_labels]] for item in units],
    ))

    secondary_labels = data["labels"]["secondary"]
    lines.extend(["", "## 二级维度", "", "### 站点评测二级维度", ""])
    lines.append(spread_statement(
        units,
        lambda row, label: row["secondary_dimensions"].get(label),
        secondary_labels,
    ))
    lines.append("")
    lines.extend(markdown_table(
        ["模型@Harness", "总平均分"] + list(secondary_labels.values()),
        [[item["unit"], item["total_average_score"], *[item["secondary_dimensions"].get(key) for key in secondary_labels]] for item in units],
    ))

    aesthetic_secondary_labels = data["labels"]["aesthetic_secondary"]
    lines.extend([
        "",
        "### 美观度二级维度",
        "",
        "表中展示每个检查点在适用用例中的百分制平均分：`(MET×100 + PARTIAL×50 + UNMET×0) / (MET + PARTIAL + UNMET)`；`NA` 不计入分母。得分合计和四种状态计数保留在报告数据 JSON 中。",
        "",
    ])
    lines.extend(markdown_table(
        ["模型@Harness", "美观度总分"] + [f"{label} 平均分" for label in aesthetic_secondary_labels.values()],
        [[
            item["unit"],
            item["aesthetic_score"],
            *[item["aesthetic_secondary_dimensions"].get(key, {}).get("average_score") for key in aesthetic_secondary_labels],
        ] for item in units],
    ))
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总独立 Web E2E 评分回传包")
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", default="", help="批次报告配置；默认 tools/report/config/web-e2e/<batch_id>.yaml")
    args = parser.parse_args()
    submissions = [load_submission(Path(value).expanduser().resolve()) for value in args.input]
    batch_ids = {str(item.get("batch_id") or "") for item in submissions}
    if len(batch_ids) != 1 or not next(iter(batch_ids)):
        raise ValueError(f"无法根据回传包确定唯一 batch_id: {sorted(batch_ids)}")
    batch_id = next(iter(batch_ids))
    config_path = (
        Path(args.config).expanduser().resolve()
        if args.config
        else Path.cwd() / "tools" / "report" / "config" / "web-e2e" / f"{batch_id}.yaml"
    )
    if not config_path.is_file():
        raise FileNotFoundError(f"缺少批次报告配置: {config_path}")
    config = load_report_config(config_path)
    data = build_report_data(submissions, config)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "web_e2e_report_data.json"
    md_path = output_dir / "Web站点端到端评测领导版.md"
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")
    print(json.dumps({"status": "PASS", "data": str(data_path), "markdown": str(md_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
