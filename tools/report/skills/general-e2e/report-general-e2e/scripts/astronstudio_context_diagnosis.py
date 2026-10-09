#!/usr/bin/env python3
"""Locate AstronStudio context jumps using bound rollout usage and text lengths.

Native usage remains authoritative. Character counts diagnose visible content;
they are never substituted for usage or promoted to exact input attribution.
"""
from __future__ import annotations

import argparse
import collections
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo


FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens",
          "reasoning_output_tokens", "total_tokens")
CATEGORIES = ("reasoning", "assistant_text", "tool_arguments", "tool_results",
              "developer_messages", "user_messages")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_file(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), f"UNSAFE_SOURCE: {path}")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino) ==
            (after.st_size, after.st_mtime_ns, after.st_ino), f"SOURCE_CHANGED: {path}")
    return data


def child(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute()
            and ".." not in Path(name).parts and "\\" not in name, "UNSAFE_RELATIVE_PATH")
    result = root / name
    require(result.resolve().is_relative_to(root.resolve()), "SOURCE_OUTSIDE_ROUND")
    return result


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(text_content(item) for item in value)
    if isinstance(value, dict):
        return "".join(text_content(value[key]) for key in ("text", "content", "summary")
                       if key in value)
    return ""


def wire_text(value):
    if isinstance(value, str):
        return value, "text"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")), "serialized-json"


def valid_usage(value):
    return (isinstance(value, dict)
            and all(type(value.get(k)) is int and value[k] >= 0 for k in FIELDS)
            and value["total_tokens"] == value["input_tokens"] + value["output_tokens"]
            and value["cached_input_tokens"] <= value["input_tokens"]
            and value["reasoning_output_tokens"] <= value["output_tokens"])


def summarize_contents(contents):
    counts = {category + "_chars": 0 for category in CATEGORIES}
    for item in contents:
        counts[item["category"] + "_chars"] += item["chars"]
    return counts


def parse_rollout(data, execution):
    """Flush text at EVERY usage checkpoint, including unchanged snapshots.

    Otherwise unmetered reasoning preceding a repeated snapshot leaks into the
    next advancing request and corrupts both attribution and chars/token ratios.
    """
    session = execution["session"]
    target = session["turn_id"]
    require(target and session["session_id"] and session["cwd"], "MISSING_SESSION_BINDING")
    require(execution["prompt"]["send_status"] == "sent", "PROMPT_NOT_SENT")
    previous = {key: 0 for key in FIELDS}
    current = None
    meta = None
    starts = prompt_matches = 0
    ended = False
    requests, unmetered, buffer, items = [], [], [], []
    seen, call_names, call_owners = {}, {}, {}
    startup, compactions, context_changes = [], [], []
    repeated_snapshots = late_outputs = 0

    for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        payload = event.get("payload") or {}
        kind = payload.get("type")
        if event["type"] == "session_meta":
            require(meta is None, "AMBIGUOUS_SESSION_META")
            require(payload.get("id", payload.get("session_id")) == session["session_id"]
                    and Path(payload["cwd"]).resolve() == Path(session["cwd"]).resolve(),
                    "ROLLOUT_SESSION_MISMATCH")
            base = text_content(payload.get("base_instructions"))
            meta = {"line": number, "base_instructions_chars": len(base),
                    "base_instructions_sha256": digest(base.encode()),
                    "cli_version": payload.get("cli_version"),
                    "model_provider": payload.get("model_provider")}
        if event["type"] == "event_msg" and kind == "task_started":
            current = payload.get("turn_id")
            if current == target:
                starts += 1
        if event["type"] == "turn_context":
            current = payload.get("turn_id")
            if current == target:
                require(Path(payload["cwd"]).resolve() == Path(session["cwd"]).resolve(),
                        "ROLLOUT_CWD_MISMATCH")
        explicit = (payload.get("internal_chat_message_metadata_passthrough") or {}).get("turn_id")
        require(not (explicit and current and explicit != current), "ITEM_TURN_MISMATCH")
        bound = (explicit or current) == target

        if event["type"] == "event_msg" and kind == "token_count":
            info = payload.get("info") or {}
            total, last = info.get("total_token_usage"), info.get("last_token_usage")
            if not bound:
                if valid_usage(total):
                    previous = {key: total[key] for key in FIELDS}
                continue
            require(valid_usage(total) and valid_usage(last), "INVALID_NATIVE_USAGE")
            total = {key: total[key] for key in FIELDS}
            if total == previous:
                repeated_snapshots += 1
                if buffer:
                    unmetered.append({"checkpoint_line": number,
                        "checkpoint_timestamp": event.get("timestamp"),
                        "after_metered_request": len(requests),
                        "status": "content-without-usage-advance", "native_tokens": None,
                        **summarize_contents(buffer), "contents": buffer})
                buffer = []
                continue
            require(all(total[k] == previous[k] + last[k] for k in FIELDS),
                    "NATIVE_USAGE_UNRECONCILED")
            row = {"request_index": len(requests) + 1, "usage_line": number,
                   "usage_timestamp": event.get("timestamp"),
                   **{key: last[key] for key in FIELDS}, "contents": buffer}
            for item in buffer:
                if item["category"] == "tool_arguments" and item.get("call_id"):
                    call_owners[item["call_id"]] = row
            requests.append(row)
            buffer = []
            previous = total
            continue
        if not bound:
            continue
        if event["type"] == "event_msg" and kind == "user_message":
            require(digest(payload["message"].encode()) == execution["prompt"]["sha256"],
                    "PROMPT_SHA_MISMATCH")
            prompt_matches += 1
        if event["type"] == "event_msg" and kind in ("task_complete", "turn_aborted"):
            require(payload.get("turn_id") == target, "TERMINAL_TURN_MISMATCH")
            ended = True
        if event["type"] == "compacted":
            compactions.append(number)
        if event["type"] != "response_item":
            continue  # agent_reasoning/agent_message mirror response items

        category, content = None, None
        item_id = payload.get("id")
        call_id = payload.get("call_id")
        if kind == "reasoning":
            category = "reasoning"
            content = text_content(payload.get("content")) or text_content(payload.get("summary"))
        elif kind == "message":
            role = payload.get("role")
            category = {"assistant": "assistant_text", "developer": "developer_messages",
                        "system": "developer_messages", "user": "user_messages"}.get(role)
            content = text_content(payload.get("content"))
        elif kind in ("function_call", "custom_tool_call", "tool_search_call"):
            category = "tool_arguments"
            content, encoding = wire_text(payload.get("arguments", payload.get("input")))
            call_id = call_id or item_id
            name = "tool_search" if kind == "tool_search_call" else payload.get("name")
            if call_id:
                call_names[call_id] = name
        elif kind in ("function_call_output", "custom_tool_call_output"):
            category = "tool_results"
            content, encoding = wire_text(payload.get("output"))
        if category is None:
            continue
        signature = digest(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode())
        key = (kind, item_id or call_id) if item_id or call_id else None
        if key is not None and key in seen:
            require(seen[key] == signature, "REPLAY_ITEM_CONTENT_CONFLICT")
            continue
        if key is not None:
            seen[key] = signature
        item = {"line": number, "timestamp": event.get("timestamp"), "category": category,
                "source_type": kind, "item_id": item_id, "call_id": call_id,
                "chars": len(content), "utf8_bytes": len(content.encode()),
                "content_sha256": digest(content.encode())}
        if category in ("tool_arguments", "tool_results"):
            item["tool_name"] = call_names.get(call_id)
            item["encoding"] = encoding
        if category == "reasoning":
            item["source_field"] = "content" if text_content(payload.get("content")) else "summary"
            item["encrypted_content_chars"] = len(payload.get("encrypted_content") or "")
        items.append(item)
        if category in ("developer_messages", "user_messages") and not requests:
            startup.append(item)
        elif category in ("developer_messages", "user_messages"):
            context_changes.append(item)
        if category == "tool_results" and call_id in call_owners:
            call_owners[call_id]["contents"].append(item)
            item["late_result_after_checkpoint"] = True
            late_outputs += 1
        else:
            buffer.append(item)

    require(meta is not None and starts == 1 and prompt_matches == 1 and ended,
            "ROLLOUT_TURN_SCOPE_INVALID")
    require(requests, "NO_RECONCILED_MODEL_RESPONSES")
    if buffer:
        unmetered.append({"checkpoint_line": None, "after_metered_request": len(requests),
                          "status": "content-after-last-usage", "native_tokens": None,
                          **summarize_contents(buffer), "contents": buffer})
    for row in requests:
        row.update(summarize_contents(row["contents"]))
        row["non_reasoning_output_tokens"] = row["output_tokens"] - row["reasoning_output_tokens"]
        row["text_usage_alignment"] = ("multiple-reasoning-items" if
            sum(item["category"] == "reasoning" for item in row["contents"]) > 1 else "ordered-window")
    return {"requests": requests, "unmetered_windows": unmetered, "items": items,
            "startup": {**meta, **summarize_contents(startup), "contents": startup},
            "post_initial_context_messages": context_changes,
            "compaction_lines": compactions, "repeated_usage_snapshots": repeated_snapshots,
            "late_tool_results": late_outputs}


def percentile(values, q):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * q) - 1)] if values else None


def calibration(requests, character_field, token_field):
    ratios = [r[character_field] / r[token_field] for r in requests
              if r[token_field] > 0 and r[character_field] > 0
              and r["text_usage_alignment"] == "ordered-window"]
    return {"status": "empirical-proxy" if ratios else "unavailable", "samples": len(ratios),
            "median_chars_per_token": statistics.median(ratios) if ratios else None,
            "p10_chars_per_token": percentile(ratios, .10),
            "p90_chars_per_token": percentile(ratios, .90)}


def correlation(rows, key):
    if len(rows) < 2:
        return None
    xs, ys = [r[key] for r in rows], [r["input_delta_tokens"] for r in rows]
    xm, ym = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    denominator = (sum((x - xm) ** 2 for x in xs) * sum((y - ym) ** 2 for y in ys)) ** .5
    return numerator / denominator if denominator else None


def diagnose(round_root, task_index, report_json, jump_threshold=10000):
    index_bytes = read_file(task_index)
    index = json.loads(index_bytes)
    report_bytes = read_file(report_json)
    report = json.loads(report_bytes)
    reports = {(r["unit_id"], r["task_id"]): r for r in report["tasks"]}
    tasks, transitions, all_requests, all_unmetered = [], [], [], []
    for selected in index["tasks"]:
        if selected["harness"] != "AstronStudio":
            continue
        execution_path = child(round_root, selected["execution_record"])
        execution_bytes = read_file(execution_path)
        require(digest(execution_bytes) == selected["execution_record_sha256"], "EXECUTION_SHA_DRIFT")
        execution = json.loads(execution_bytes)
        identity = execution["identity"]
        require(identity["task_id"] == selected["task_id"] and
                identity["attempt_id"] == selected["execution_attempt_id"], "ATTEMPT_SELECTION_MISMATCH")
        rollout = child(round_root, selected["rollout"])
        require(rollout.name == "astronstudio-rollout.jsonl", "ASTRON_SOURCE_MUST_BE_ROLLOUT")
        if selected.get("resource_supplement"):
            manifest_path = child(round_root, selected["resource_supplement"])
            manifest = json.loads(read_file(manifest_path))
            require(manifest["identity"] == identity and
                    manifest["execution_record_sha256"] == digest(execution_bytes), "SUPPLEMENT_BINDING_DRIFT")
            refs = [r for r in manifest["artifacts"] if r["path"] == manifest["rollout_path"]]
        else:
            manifest_path = child(round_root, selected["trace_index"])
            manifest = json.loads(read_file(manifest_path))
            require(manifest["identity"] == identity and all(
                manifest["session"][k] == execution["session"][k]
                for k in ("session_id", "turn_id", "cwd")), "TRACE_INDEX_BINDING_DRIFT")
            refs = [r for r in manifest["raw_trace"] if r["path"] == "raw/astronstudio-rollout.jsonl"]
        require(len(refs) == 1 and child(manifest_path.parent, refs[0]["path"]).resolve() == rollout.resolve(),
                "ROLLOUT_SELECTION_MISMATCH")
        raw = read_file(rollout)
        require(digest(raw) == refs[0]["sha256"] and len(raw) == refs[0]["size"], "ROLLOUT_SHA_DRIFT")
        parsed = parse_rollout(raw, execution)
        response_sums = {key: sum(r[key] for r in parsed["requests"]) for key in FIELDS}
        original_report = reports[(identity["unit_id"], identity["task_id"])]
        for key, report_key in [("input_tokens", "input_tokens"), ("cached_input_tokens", "cache_read_input_tokens"),
                                ("output_tokens", "output_tokens"), ("reasoning_output_tokens", "reasoning_output_tokens"),
                                ("total_tokens", "total_tokens")]:
            require(response_sums[key] == original_report["resource"][report_key]["value"],
                    f"REPORT_USAGE_RECONCILIATION_FAILED: {identity['task_id']}:{key}")
        require(len(parsed["requests"]) == original_report["resource"]["request_count"]["value"],
                "REPORT_RESPONSE_COUNT_MISMATCH")
        task = {"task_id": identity["task_id"], "identity": identity,
                "execution_status": execution.get("execution", {}).get("business_status"),
                "execution_error": execution.get("execution", {}).get("error"),
                "rollout_source": {"path": str(rollout), "sha256": digest(raw), "size": len(raw)},
                "execution_source": {"path": str(execution_path), "sha256": digest(execution_bytes)},
                "request_count": len(parsed["requests"]), "native_usage": response_sums, **parsed}
        for a, b in zip(parsed["requests"], parsed["requests"][1:]):
            delta = b["input_tokens"] - a["input_tokens"]
            residual = delta - a["output_tokens"]
            kind = "ordinary-or-unresolved"
            if delta >= jump_threshold:
                if (a["reasoning_output_tokens"] >= .7 * delta
                        and abs(residual) <= max(1000, .15 * delta)):
                    kind = "reasoning-history-candidate"
                elif a["tool_results_chars"] >= 10000 and a["output_tokens"] < .3 * delta:
                    kind = "large-tool-result-candidate"
                else:
                    kind = "mixed-or-unresolved-large-jump"
            transitions.append({"task_id": identity["task_id"],
                "from_request": a["request_index"], "to_request": b["request_index"],
                "from_usage_line": a["usage_line"], "to_usage_line": b["usage_line"],
                "rollout_path": str(rollout), "input_before": a["input_tokens"],
                "input_after": b["input_tokens"], "input_delta_tokens": delta,
                "previous_output_tokens": a["output_tokens"],
                "previous_reasoning_tokens": a["reasoning_output_tokens"],
                "previous_non_reasoning_output_tokens": a["non_reasoning_output_tokens"],
                "residual_after_previous_output": residual,
                **{key + "_chars": a[key + "_chars"] for key in CATEGORIES},
                "screening_label": kind, "attribution_status": "temporal-and-arithmetic-association"})
        all_requests.extend(parsed["requests"])
        for window in parsed["unmetered_windows"]:
            window["task_id"] = identity["task_id"]
            window["rollout_path"] = str(rollout)
            all_unmetered.append(window)
        tasks.append(task)

    require(tasks, "NO_SELECTED_ASTRONSTUDIO_TASKS")
    for r in all_requests:
        r["non_reasoning_output_chars"] = r["assistant_text_chars"] + r["tool_arguments_chars"]
    reasoning_calibration = calibration(all_requests, "reasoning_chars", "reasoning_output_tokens")
    other_calibration = calibration(all_requests, "non_reasoning_output_chars", "non_reasoning_output_tokens")
    for row in transitions:
        median = other_calibration["median_chars_per_token"]
        p10, p90 = other_calibration["p10_chars_per_token"], other_calibration["p90_chars_per_token"]
        row["tool_result_token_proxy"] = {
            "status": "estimated" if median else "unavailable",
            "median_calibrated_estimate": row["tool_results_chars"] / median if median else None,
            "empirical_low": row["tool_results_chars"] / p90 if p90 else None,
            "empirical_high": row["tool_results_chars"] / p10 if p10 else None}
    large = [r for r in transitions if r["input_delta_tokens"] >= jump_threshold]
    return {"schema_version": "wildclawbench.astronstudio-context-diagnosis/v1",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "analysis_implementation": {"path": str(Path(__file__).resolve()),
                                    "sha256": digest(read_file(Path(__file__).resolve()))},
        "sources": {"task_index": {"path": str(task_index), "sha256": digest(index_bytes)},
                    "report": {"path": str(report_json), "sha256": digest(report_bytes)}},
        "methodology": {"character_unit": "Unicode code points of decoded text; UTF-8 bytes separate",
            "model_output": "reasoning + assistant text + tool argument JSON; native output includes reasoning",
            "grouping": "response_item only; flush at every token_count, unchanged snapshots retain content as unmetered",
            "delta": "input_tokens(k+1) - input_tokens(k)",
            "residual": "delta - native_output_tokens(k); arithmetic balance, not causal attribution",
            "large_jump_threshold_tokens": jump_threshold,
            "reasoning_candidate": "previous reasoning >=70% of delta and |delta-previous output| <= max(1000,15% delta)",
            "tool_candidate": "tool-result chars >=10000 and previous output <30% of delta",
            "character_conversion": "successful paired output characters/native tokens calibration; estimated proxy only",
            "limits": "no complete outbound requests, exact role attribution unavailable; observed text may be summary/partial; unmetered text has no trustworthy token conversion"},
        "summary": {"tasks_verified": len(tasks), "usage_advances": len(all_requests),
            "adjacent_request_transitions": len(transitions),
            "native_usage_reconciled_to_report": True,
            "native_usage": {key: sum(r[key] for r in all_requests) for key in FIELDS},
            "net_first_to_last_input_growth": sum(r["input_delta_tokens"] for r in transitions),
            "negative_delta_count": sum(r["input_delta_tokens"] < 0 for r in transitions),
            "large_jump_count": len(large),
            "large_jump_labels": dict(collections.Counter(r["screening_label"] for r in large)),
            "large_jump_input_delta_sum": sum(r["input_delta_tokens"] for r in large),
            "metered_content_chars": {key: sum(r[key + "_chars"] for r in all_requests) for key in CATEGORIES},
            "unmetered_windows": len(all_unmetered),
            "unmetered_task_count": len({r["task_id"] for r in all_unmetered}),
            "unmetered_reasoning_chars": sum(r["reasoning_chars"] for r in all_unmetered),
            "compaction_event_count": sum(len(t["compaction_lines"]) for t in tasks),
            "post_initial_context_message_count": sum(len(t["post_initial_context_messages"]) for t in tasks),
            "base_instruction_char_lengths": sorted({t["startup"]["base_instructions_chars"] for t in tasks}),
            "initial_developer_message_char_lengths": sorted({t["startup"]["developer_messages_chars"] for t in tasks}),
            "correlations_with_next_input_delta": {
                key: correlation(transitions, key) for key in
                ("previous_reasoning_tokens", "previous_output_tokens", "tool_results_chars", "reasoning_chars")}},
        "character_token_calibration": {"reasoning": reasoning_calibration, "non_reasoning_output": other_calibration},
        "tasks": tasks, "transitions": transitions, "unmetered_windows": all_unmetered}


def render_markdown(data):
    s = data["summary"]
    native = s["native_usage"]
    share = f"{native['reasoning_output_tokens']/native['output_tokens']:.1%}" if native["output_tokens"] else "unavailable"
    lines = ["# AstronStudio 输入 Token 增长定位", "",
        f"分析{ s['tasks_verified'] }题、{s['usage_advances']}次可对账模型响应、{s['adjacent_request_transitions']}次相邻请求变化。所有原件核验身份、SHA及原生用量；统计与原报告逐题对账。", "",
        "## 当前发现", "",
        f"- 输入增量≥{data['methodology']['large_jump_threshold_tokens']:,} Token的跃升共{s['large_jump_count']}次："
        f"{s['large_jump_labels'].get('reasoning-history-candidate',0)}次符合大量思考历史保留的诊断特征，"
        f"{s['large_jump_labels'].get('large-tool-result-candidate',0)}次符合大工具返回的特征。标签为排查线索，非因果证明。",
        f"- 原生总输出{native['output_tokens']:,} Token，其中推理{native['reasoning_output_tokens']:,} Token"
        f"（{share}）。非推理部分包含工具调用参数和助手回复。",
        f"- {s['unmetered_task_count']}题存在{s['unmetered_windows']}段新内容、用量未推进的区间；"
        f"思考文本共{s['unmetered_reasoning_chars']:,}字符。这些区间不能按旧usage或字符换算计入正式Token。", "",
        f"本轮基础指令为{s['base_instruction_char_lengths']}字符，首轮developer内容为"
        f"{s['initial_developer_message_char_lengths']}字符；首轮后新增可见developer/user消息"
        f"{s['post_initial_context_message_count']}条。当前没有证据显示它们在逐轮膨胀；"
        "但rollout缺少完整请求工具Schema，仍不能排除未记录的运行时上下文变化。", "",
        "## 字符数怎么用于定位", "",
        "分别统计工具输入（参数JSON）、工具输出（返回文本）、思考文本、助手正文。"
        "只统计response_item，排除agent_reasoning/agent_message镜像，按身份去重。"
        "思考优先取content，没有content时取summary；加密内容不作为可读文本计算。",
        "原生input/output/reasoning Token是实测量。字符/Token换算是同模型已计量输出的经验代理；"
        "编码、中文比例、JSON转义、协议开销和截断都会影响比值，工具返回的估计不可替代原生计量。",
        "分析输入变化时使用：`ΔI_k = I_(k+1) − I_k`，再查看上一响应的输出、思考和工具返回。"
        "`ΔI_k − O_k`是算术剩余项，包括工具返回、消息格式、上下文修改等，不能全称为工具Token。", "",
        "## 同模型字符/Token经验换算", "",
        "| 文本 | 可用响应数 | 字符/Token中位数 | P10 | P90 |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for name, key in [("已计量思考文本", "reasoning"), ("助手正文+工具参数", "non_reasoning_output")]:
        c = data["character_token_calibration"][key]
        f = lambda v: f"{v:.3f}" if v is not None else "unavailable"
        lines.append(f"| {name} | {c['samples']} | {f(c['median_chars_per_token'])} | {f(c['p10_chars_per_token'])} | {f(c['p90_chars_per_token'])} |")
    lines += ["", "`粗估Token ≈ 字符数 ÷ 经验字符/Token比值`。P10/P90形成经验范围，不是置信区间，也不是精确Tokenizer结果。未计量区间不使用这套换算。", "",
        "## 最大相邻请求跃升", "",
        "| 题目 | 请求变化 | 输入前→后 | Δ输入Token | 上次输出Token | 上次推理Token | 思考字符 | 工具参数字符 | 工具返回字符 | 助手正文字符 | Δ输入−上次输出 | 线索 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    labels = {"reasoning-history-candidate": "思考历史保留候选", "large-tool-result-candidate": "大工具返回候选",
              "ordinary-or-unresolved": "普通/待解释", "mixed-or-unresolved-large-jump": "混合/待解释"}
    for r in sorted(data["transitions"], key=lambda r: r["input_delta_tokens"], reverse=True)[:25]:
        lines.append(f"| [{r['task_id']}]({r['rollout_path']}:{r['from_usage_line']}) | {r['from_request']}→{r['to_request']} | "
            f"{r['input_before']:,}→{r['input_after']:,} | {r['input_delta_tokens']:,} | {r['previous_output_tokens']:,} | "
            f"{r['previous_reasoning_tokens']:,} | {r['reasoning_chars']:,} | {r['tool_arguments_chars']:,} | "
            f"{r['tool_results_chars']:,} | {r['assistant_text_chars']:,} | {r['residual_after_previous_output']:,} | {labels[r['screening_label']]} |")
    lines += ["", "## 新思考文本出现，但用量未推进", "",
        "不能直接叫重复日志：同一累计用量旁可能出现新的reasoning item。"
        "这里只确认原件中新增了内容、计量没有推进；是否重试、异常生成、客户端重复或Provider漏返usage，需要请求级原件进一步确认。", "",
        "| 题目 | 快照行 | 思考字符 | 对应reasoning原件行 |",
        "| --- | ---: | ---: | --- |"]
    for r in data["unmetered_windows"]:
        refs = ", ".join(str(i["line"]) for i in r["contents"] if i["category"] == "reasoning")
        lines.append(f"| {r['task_id']} | {r['checkpoint_line']} | {r['reasoning_chars']:,} | {refs} |")
    affected = {r["task_id"] for r in data["unmetered_windows"]}
    for task in data["tasks"]:
        if task["task_id"] in affected and task.get("execution_error"):
            error = task["execution_error"]
            lines += ["", f"该题原执行记录状态为 `{task['execution_status']}`，错误为 "
                      f"`{error.get('code')}: {error.get('message')}`。"
                      f"[原执行记录]({task['execution_source']['path']})。"
                      "这支持优先核查长思考/生成异常及usage返回链路，仍不能确定每个未计量区间的实际消耗。"]
    lines += ["", "## 相关性与证据边界", "",
        "下表为全部相邻请求变化的Pearson相关系数；它帮助选择排查方向，不证明输入增量的精确组成。", "",
        "| 上一响应指标 | 与下一次输入增量的r |", "| --- | ---: |"]
    for key, value in s["correlations_with_next_input_delta"].items():
        lines.append(f"| {key} | {value:.3f} |" if value is not None else f"| {key} | unavailable |")
    lines += ["", "- 首轮系统/开发者/用户文本单独保存在JSON startup字段；不会把它们每轮再计一次。"
              "首轮混合输入不能反推纯系统提示词Token。",
        "- 最后一响应没有本题下一请求，所以不会纳入下一次输入增长比较。",
        "- 思考、工具参数与助手回复共同构成输出；推理Token是输出子集，不能再次相加。",
        "- 观察到内容与下一请求增量量级一致，是历史保留的强线索；精确验证须拿到下一请求的角色级payload。",
        "- 当前客户端版本和模型绑定在原执行记录；结果属于本轮Spark X2.5@AstronStudio组合，不能外推所有版本。",
        "- 建议优先核查：思考内容进入下一请求历史的策略、工具结果裁剪/重复读取、无usage推进的长思考区间。"
        "修改这些策略后，以同题、同模型、同配置的对照运行验证收益。", "",
        "完整逐请求、工具名、字符数、原始行号和SHA见 `astronstudio-context-diagnosis.json`，"
        "相邻变化表另有CSV。原执行、评分和轨迹原件保持冻结。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-root", type=Path, required=True)
    parser.add_argument("--task-index", type=Path)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jump-threshold", type=int, default=10000)
    args = parser.parse_args()
    require(args.jump_threshold > 0, "INVALID_JUMP_THRESHOLD")
    root = args.round_root.resolve()
    index = args.task_index or root / "TASK_INDEX.json"
    report = args.report_json or root / "reports/final/general_e2e_report_data.json"
    require(not args.output_dir.exists(), "OUTPUT_DIRECTORY_ALREADY_EXISTS")
    result = diagnose(root, index, report, args.jump_threshold)
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "astronstudio-context-diagnosis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "astronstudio-context-diagnosis.md").write_text(render_markdown(result), encoding="utf-8")
    with (args.output_dir / "adjacent-request-changes.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [key for key in result["transitions"][0] if key != "tool_result_token_proxy"] if result["transitions"] else ["task_id"]
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["transitions"])
    print(json.dumps({"status": "PASS", "output_dir": str(args.output_dir),
                      "summary": result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
