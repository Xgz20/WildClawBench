#!/usr/bin/env python3
"""Compare visible text in selected, immutable General E2E traces.

Counts describe persisted content once, not repeatedly submitted context or
billable Tokens. Raw text is never copied into the analysis artifacts.
"""
from __future__ import annotations

import argparse
import collections
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

from astronstudio_context_diagnosis import (
    child, digest, parse_rollout, percentile, read_file, require, text_content,
)


HARNESSES = ("AstronStudio", "WorkBuddy", "QwenWork", "DoubaoWork")
CATEGORIES = ("user_prompt", "injected_context", "reasoning", "assistant_text",
              "tool_arguments", "tool_results", "tool_schema")
LABELS = dict(zip(CATEGORIES, ("用户输入", "可见注入上下文", "思考/思考摘要",
                  "模型正文", "工具参数", "工具返回文本", "工具 Schema")))


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def argument_text(value):
    # Normalize JSON arguments across clients; retain opaque argument strings.
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return value
        if isinstance(parsed, (dict, list)):
            return json_text(parsed)
        return value
    return json_text(value) if value is not None else ""


def visible_text(value):
    """Take the text channel once; exclude binary data and UI/transport mirrors."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(visible_text(v) for v in value)
    if isinstance(value, dict):
        if value.get("type") in ("image", "input_image", "audio", "video"):
            return ""
        for key in ("text", "content"):
            if isinstance(value.get(key), (str, dict, list)):
                return visible_text(value[key])
    return ""


def image_count(value):
    if isinstance(value, list):
        return sum(image_count(v) for v in value)
    if isinstance(value, dict):
        return int(value.get("type") in ("image", "input_image")) + sum(
            image_count(v) for k, v in value.items() if k not in ("source", "data"))
    return 0


class Contents:
    def __init__(self, available):
        self.available = set(available)
        self.items = []
        self.seen = {}
        self.diagnostics = collections.Counter()

    def add(self, category, text, source, ref, *, key=None, tool=None, scope=None):
        require(category in self.available, "UNSUPPORTED_CATEGORY")
        require(isinstance(text, str), "TEXT_EXPECTED")
        signature = digest(text.encode())
        if key is not None:
            if key in self.seen:
                require(self.seen[key] == (category, signature), "REPLAY_CONTENT_CONFLICT")
                self.diagnostics["duplicate_items_excluded"] += 1
                return
            self.seen[key] = (category, signature)
        self.items.append({"category": category, "chars": len(text),
            "utf8_bytes": len(text.encode()), "content_sha256": signature,
            "source": source, "ref": ref, "tool_name": tool, "scope": scope})

    def totals(self, items=None):
        selected = self.items if items is None else items
        return {k: sum(i["chars"] for i in selected if i["category"] == k)
                if k in self.available else None for k in CATEGORIES}


def lines(data):
    return [(i, json.loads(line)) for i, line in enumerate(data.decode().splitlines(), 1)
            if line.strip()]


def check_session(row, execution):
    session = execution["session"]
    if row.get("sessionId") is not None:
        require(row["sessionId"] == session["session_id"], "NATIVE_SESSION_MISMATCH")
    if row.get("cwd") is not None:
        require(Path(row["cwd"]).resolve() == Path(session["cwd"]).resolve(), "NATIVE_CWD_MISMATCH")


def parse_workbuddy(data, execution, prompt, source):
    result = Contents(set(CATEGORIES) - {"reasoning", "tool_schema"})
    names = {}
    prompt_matches = 0
    for number, row in lines(data):
        check_session(row, execution)
        kind = row.get("type")
        if kind == "message":
            for index, part in enumerate(row.get("content") or []):
                require(isinstance(part, dict) and part.get("type") in ("input_text", "output_text"),
                        "WORKBUDDY_UNKNOWN_MESSAGE_BLOCK")
                text = visible_text(part)
                key = (kind, row["id"], index)
                if row.get("role") == "user":
                    require(text.count(prompt) == 1, "WORKBUDDY_PROMPT_BINDING")
                    prompt_matches += 1
                    result.add("user_prompt", prompt, source, f"line:{number}/content/{index}", key=key)
                    result.add("injected_context", text.replace(prompt, "", 1), source,
                               f"line:{number}/content/{index}:excluding-frozen-prompt")
                elif row.get("role") == "assistant":
                    result.add("assistant_text", text, source, f"line:{number}/content/{index}", key=key)
                else:
                    raise ValueError("WORKBUDDY_UNKNOWN_MESSAGE_ROLE")
        elif kind == "function_call":
            names[row["callId"]] = row["name"]
            result.add("tool_arguments", argument_text(row.get("arguments")), source,
                       f"line:{number}/arguments", key=(kind, row["callId"]), tool=row["name"])
        elif kind == "function_call_result":
            output = row.get("output")
            result.diagnostics["image_blocks_excluded"] += image_count(output)
            result.add("tool_results", visible_text(output), source, f"line:{number}/output",
                       key=(kind, row["callId"]), tool=names.get(row["callId"]))
    require(prompt_matches == 1, "WORKBUDDY_PROMPT_COUNT")
    return result


def parse_qwen(data, execution, prompt, source):
    result = Contents(set(CATEGORIES) - {"tool_schema"})
    names = {}
    prompt_matches = 0
    for number, row in lines(data):
        check_session(row, execution)
        require(row.get("isSidechain") is not True, "QWEN_SIDECHAIN_REQUIRES_SEPARATE_SCOPE")
        kind = row.get("type")
        if kind == "attachment":
            attachment = row.get("attachment") or {}
            content = attachment.get("content")
            if isinstance(content, str):
                result.add("injected_context", content, source, f"line:{number}/attachment/content",
                           key=(kind, row.get("uuid", number)))
            elif content is not None:
                result.diagnostics["nontext_attachments_excluded"] += 1
            continue
        if kind not in ("user", "assistant"):
            continue
        parts = (row.get("message") or {}).get("content") or []
        require(isinstance(parts, list), "QWEN_MESSAGE_BLOCKS_EXPECTED")
        for index, part in enumerate(parts):
            ref = f"line:{number}/message/content/{index}"
            typ = part.get("type")
            key = (kind, row["uuid"], index)
            if typ == "text":
                text = part.get("text") or ""
                category = "assistant_text" if kind == "assistant" else "injected_context"
                if kind == "user" and text == prompt:
                    prompt_matches += 1
                    category = "user_prompt"
                result.add(category, text, source, ref, key=key)
            elif typ == "thinking" and kind == "assistant":
                result.add("reasoning", part.get("thinking") or "", source, ref, key=key)
            elif typ == "tool_use":
                names[part["id"]] = part["name"]
                result.add("tool_arguments", argument_text(part.get("input")), source, ref,
                           key=(typ, part["id"]), tool=part["name"])
            elif typ == "tool_result":
                # row.toolUseResult also contains local transport/display data.
                # The content block is the persisted model-facing result.
                result.diagnostics["image_blocks_excluded"] += image_count(part.get("content"))
                result.add("tool_results", visible_text(part.get("content")), source, ref,
                           key=(typ, part["tool_use_id"]), tool=names.get(part["tool_use_id"]))
            else:
                raise ValueError(f"QWEN_UNKNOWN_CONTENT_BLOCK: {typ}")
    require(prompt_matches == 1, "QWEN_PROMPT_COUNT")
    return result


def parse_doubao(transcript, runtime, execution, source, runtime_source):
    result = Contents({"user_prompt", "assistant_text", "tool_arguments", "tool_results"})
    names = {}
    for number, row in lines(transcript):
        require(row["identity"] == execution["identity"], "TRANSCRIPT_IDENTITY_MISMATCH")
        typ = row["type"]
        tool = row.get("tool") or {}
        if typ == "tool_call":
            names[tool["call_id"]] = tool["name"]
            result.add("tool_arguments", argument_text(tool.get("arguments")), source,
                       f"line:{number}/tool/arguments", key=(typ, tool["call_id"]), tool=tool["name"])
        elif typ == "tool_result":
            result.add("tool_results", visible_text(tool.get("result")), source,
                       f"line:{number}/tool/result:content-channel-only", key=(typ, tool["call_id"]),
                       tool=tool.get("name") or names.get(tool["call_id"]),
                       scope="native/model-result-or-bound-local-result")
        elif typ == "user_message":
            result.add("user_prompt", row.get("content") or "", source,
                       f"line:{number}/content", key=(typ, row["event_id"]))
    document = json.loads(runtime)
    sid, mid = execution["session"]["session_id"], execution["session"]["turn_id"]
    require(str(document["conversation_id"]) == sid, "DOUBAO_CONVERSATION_MISMATCH")
    message = document["maps"]["messageMap"][mid]
    require(str(message["message_id"]) == mid and str(message["conversation_id"]) == sid,
            "DOUBAO_MESSAGE_MISMATCH")
    for index, block in enumerate(message.get("content_blocks_v2") or []):
        content = block.get("content") or {}
        if "text_block" in content:
            text = content["text_block"].get("text") or ""
            # summary is a UI heading; never count it as reasoning or output.
            result.add("assistant_text", text, runtime_source,
                       f"/maps/messageMap/{mid}/content_blocks_v2/{index}/content/text_block/text",
                       key=("text_block", block["block_id"]))
            result.diagnostics["ui_summary_chars_excluded"] += len(content["text_block"].get("summary") or "")
        if "thinking_block" in content:
            require(set(content["thinking_block"]) <= {
                "finish_title", "streaming_title", "icon_url", "icon_url_dark", "unfold_streaming_title"},
                "DOUBAO_THINKING_SHAPE_CHANGED")
            result.diagnostics["thinking_title_blocks_without_body"] += 1
    return result


def parse_astron(data, execution, prompt, source):
    parsed = parse_rollout(data, execution)
    result = Contents(CATEGORIES)
    rows = dict(lines(data))
    metered = {id(item) for request in parsed["requests"] for item in request["contents"]}
    mapping = {"developer_messages": "injected_context", "user_messages": "user_prompt"}
    prompt_matches = 0
    for item in parsed["items"]:
        category = mapping.get(item["category"], item["category"])
        payload = rows[item["line"]]["payload"]
        if category == "tool_arguments":
            text = argument_text(payload.get("arguments", payload.get("input")))
        elif category == "tool_results":
            value = payload.get("output")
            text = value if isinstance(value, str) else visible_text(value)
        elif category == "reasoning":
            text = text_content(payload.get("content")) or text_content(payload.get("summary"))
            result.diagnostics[f"reasoning_source_{item['source_field']}"] += 1
        else:
            text = text_content(payload.get("content"))
        scope = "metered-window" if id(item) in metered else "unmetered-window"
        if category in ("user_prompt", "injected_context"):
            scope = "context-record"
        if category == "user_prompt":
            count = text.count(prompt)
            require(count <= 1, "ASTRON_AUGMENTED_PROMPT_BINDING")
            if count:
                prompt_matches += 1
                result.add("user_prompt", prompt, source, f"line:{item['line']}:frozen-prompt", scope=scope)
                result.add("injected_context", text.replace(prompt, "", 1), source,
                           f"line:{item['line']}:excluding-frozen-prompt", scope="context-record")
            else:
                result.add("injected_context", text, source, f"line:{item['line']}:other-user-context",
                           scope="context-record")
        else:
            result.add(category, text, source, f"line:{item['line']}", tool=item.get("tool_name"), scope=scope)
    require(prompt_matches == 1, "ASTRON_RESPONSE_PROMPT_COUNT")
    meta = next(row["payload"] for _, row in rows.items() if row["type"] == "session_meta")
    result.add("injected_context", text_content(meta.get("base_instructions")), source,
               "line:1/base_instructions", scope="context-record")
    result.add("tool_schema", json_text(meta.get("dynamic_tools") or []), source,
               "line:1/dynamic_tools", scope="initial-schema-registry")
    for number, row in rows.items():
        payload = row.get("payload") or {}
        if row["type"] == "response_item" and payload.get("type") == "tool_search_output":
            result.add("tool_schema", json_text(payload["tools"]), source,
                       f"line:{number}/tools", key=("tool_search_output", payload["call_id"]),
                       tool="tool_search", scope="loaded-schema-result")
    result.diagnostics["native_metered_responses"] = len(parsed["requests"])
    result.diagnostics["unmetered_reasoning_chars"] = sum(
        i["chars"] for i in result.items if i["category"] == "reasoning" and i["scope"] == "unmetered-window")
    return result


def statistics_for(tasks, category):
    values = [t["visible_chars"][category] for t in tasks if t["visible_chars"][category] is not None]
    return {"visible_sum_chars": sum(values) if values else None,
            "median_per_task_chars": statistics.median(values) if values else None,
            "p90_per_task_chars": percentile(values, .9), "available_tasks": len(values),
            "positive_tasks": sum(v > 0 for v in values), "task_denominator": len(tasks)}


def aggregate(tasks):
    groups = {}
    for harness in HARNESSES:
        selected = [t for t in tasks if t["harness"] == harness]
        categories = {k: statistics_for(selected, k) for k in CATEGORIES}
        tools = collections.defaultdict(lambda: {"argument_chars": 0, "result_chars": 0,
                                                "call_items": 0, "result_items": 0})
        for task in selected:
            for item in task["items"]:
                if item["category"] not in ("tool_arguments", "tool_results"):
                    continue
                value = tools[item["tool_name"] or "unknown-native-tool-name"]
                if item["category"] == "tool_arguments":
                    value["argument_chars"] += item["chars"]
                    value["call_items"] += 1
                else:
                    value["result_chars"] += item["chars"]
                    value["result_items"] += 1
        formal_known = sum(t["formal_tool_count"] for t in selected if t["formal_tool_count"] is not None)
        formal_complete = bool(selected) and all(t["formal_tool_count"] is not None for t in selected)
        groups[harness] = {"tasks": len(selected), "categories": categories,
            "formal_tool_count": formal_known if formal_complete else None,
            "formal_tool_count_known_subtotal": formal_known if selected else None,
            "formal_tool_count_known_tasks": sum(t["formal_tool_count"] is not None for t in selected),
            "observed_tool_argument_items": sum(v["call_items"] for v in tools.values()),
            "observed_tool_result_items": sum(v["result_items"] for v in tools.values()),
            "loaded_schema_result_items": sum(i["scope"] == "loaded-schema-result" for t in selected for i in t["items"]),
            "by_tool": dict(sorted(tools.items(), key=lambda kv: -kv[1]["result_chars"])),
            "trace_completeness": dict(collections.Counter(t["trace_completeness"] for t in selected)),
            "diagnostics": dict(sum((collections.Counter(t["diagnostics"]) for t in selected), collections.Counter()))}
    return groups


def analyze(round_root):
    index_path = round_root / "TASK_INDEX.json"
    index_data = read_file(index_path)
    tasks = []
    selected_keys = set()
    for selected in json.loads(index_data)["tasks"]:
        harness = selected["harness"]
        if harness not in HARNESSES:
            continue
        key = (harness, selected["task_id"])
        require(key not in selected_keys, "DUPLICATE_SELECTED_TASK")
        selected_keys.add(key)
        execution_path = child(round_root, selected["execution_record"])
        execution_data = read_file(execution_path)
        require(digest(execution_data) == selected["execution_record_sha256"], "EXECUTION_SHA_DRIFT")
        execution = json.loads(execution_data)
        identity = execution["identity"]
        require(identity["attempt_id"] == selected["execution_attempt_id"] and
                identity["task_id"] == selected["task_id"] and identity["unit_id"] == selected["unit_id"],
                "ATTEMPT_SELECTION_MISMATCH")
        manifest_path = child(round_root, selected["trace_index"])
        manifest = json.loads(read_file(manifest_path))
        require(manifest["identity"] == identity, "TRACE_IDENTITY_DRIFT")
        require(all(manifest["session"].get(k) == execution["session"].get(k)
                    for k in ("session_id", "turn_id", "cwd")), "TRACE_SESSION_BINDING_DRIFT")
        sources = []

        def load_manifest_file(name, *, supplement=False):
            owner, table = manifest_path, manifest["raw_trace"]
            if name == "transcript.jsonl":
                table = [manifest["transcript"]]
            if supplement:
                owner = child(round_root, selected["resource_supplement"])
                supplement_doc = json.loads(read_file(owner))
                require(supplement_doc["identity"] == identity and
                        supplement_doc["execution_record_sha256"] == digest(execution_data),
                        "SUPPLEMENT_BINDING_DRIFT")
                table = supplement_doc["artifacts"]
            refs = [v for v in table if v["path"] == name]
            require(len(refs) == 1, f"TRACE_REFERENCE_MISSING: {name}")
            ref = refs[0]
            path = child(owner.parent, name)
            data = read_file(path)
            require(digest(data) == ref["sha256"] and len(data) == ref["size"], "TRACE_SHA_DRIFT")
            sources.append({"path": str(path), "sha256": digest(data), "size": len(data)})
            return data, str(path)

        transcript_data, transcript_path = load_manifest_file("transcript.jsonl")
        normalized = [row for _, row in lines(transcript_data)]
        require(all(row["identity"] == identity for row in normalized), "TRANSCRIPT_IDENTITY_DRIFT")
        prompts = [row["content"] for row in normalized if row["type"] == "user_message"]
        require(len(prompts) == 1 and digest(prompts[0].encode()) == execution["prompt"]["sha256"],
                "SELECTED_PROMPT_SHA_MISMATCH")
        if harness == "AstronStudio":
            name = "raw/astronstudio-rollout.jsonl"
            data, path = load_manifest_file(name, supplement=bool(selected.get("resource_supplement")))
            require(child(round_root, selected["rollout"]).resolve() == Path(path).resolve(), "ROLLOUT_SELECTION_DRIFT")
            parsed = parse_astron(data, execution, prompts[0], path)
        elif harness == "WorkBuddy":
            data, path = load_manifest_file("raw/workbuddy-session.jsonl")
            parsed = parse_workbuddy(data, execution, prompts[0], path)
        elif harness == "QwenWork":
            data, path = load_manifest_file("raw/transcript.jsonl")
            parsed = parse_qwen(data, execution, prompts[0], path)
        else:
            data, path = load_manifest_file("raw/runtime-messages.json")
            parsed = parse_doubao(transcript_data, data, execution, transcript_path, path)
        task = {"harness": harness, "task_id": selected["task_id"], "identity": identity,
                "prompt_sha256": execution["prompt"]["sha256"],
                "execution_status": selected["execution_status"],
                "trace_completeness": manifest["completeness"]["status"],
                "formal_tool_count": selected.get("call_count"),
                "sources": sources, "execution_source": {"path": str(execution_path), "sha256": digest(execution_data)},
                "visible_chars": parsed.totals(), "diagnostics": dict(parsed.diagnostics),
                "items": parsed.items}
        tasks.append(task)
    task_sets = [{t["task_id"] for t in tasks if t["harness"] == h} for h in HARNESSES]
    require(task_sets[0] and all(v == task_sets[0] for v in task_sets), "HARNESS_TASK_SETS_DIFFER")
    failed = {t["task_id"] for t in tasks if t["execution_status"] != "completed"}
    require(all(t["prompt_sha256"] == next(
        u["prompt_sha256"] for u in tasks if u["task_id"] == t["task_id"])
        for t in tasks), "CROSS_HARNESS_PROMPT_SHA_MISMATCH")
    return {"schema_version": "general-e2e-trace-character-analysis/v1",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "task_index": {"path": str(index_path), "sha256": digest(index_data)},
        "analysis_source": {"path": str(Path(__file__).resolve()), "sha256": digest(read_file(Path(__file__)))},
        "measurement": "Unicode code points; each persisted content item once; not Tokens or repeated request payload size",
        "groups": aggregate(tasks), "matched_completed_groups": aggregate([t for t in tasks if t["task_id"] not in failed]),
        "excluded_task_ids_for_matched_completed": sorted(failed), "tasks": tasks}


def fmt(value):
    return "不可见" if value is None else f"{value:,.0f}"


def render(report):
    normal = report["matched_completed_groups"]
    astron = normal["AstronStudio"]["categories"]
    qwen = normal["QwenWork"]["categories"]
    reason_ratio = astron["reasoning"]["visible_sum_chars"] / qwen["reasoning"]["visible_sum_chars"] if qwen["reasoning"]["visible_sum_chars"] else None
    metered = report["groups"]["AstronStudio"]["diagnostics"].get("unmetered_reasoning_chars", 0)
    comparisons = []
    for h in ("WorkBuddy", "QwenWork"):
        value = normal[h]["categories"]["tool_results"]["visible_sum_chars"]
        if value:
            comparisons.append(f"{h} 的 {astron['tool_results']['visible_sum_chars'] / value:.2f} 倍")
    output = ["# 四端轨迹字符分布对比", "", f"生成时间：{report['generated_at']}", "",
        "统计 TASK_INDEX 选定的有效执行，每端同一组用例。字符数描述日志中新增内容的构成，每个内容项只计一次，不能直接当作累计输入 Token、计费量或完整上下文。", "",
        "## 结论", "",
        "- 四端可以比较已保存的模型正文、工具参数和工具返回文本。思考文本只能对比 AStudio 与 QwenWork 的可见部分，不能对 WorkBuddy/DoubaoWork 作零值推断。",
        f"- 同题完成样本中，AStudio 可见思考/摘要 {fmt(astron['reasoning']['visible_sum_chars'])} 字符，QwenWork {fmt(qwen['reasoning']['visible_sum_chars'])} 字符，比例 {reason_ratio:.2f} 倍。这支持优先核查 AStudio 的长思考和历史保留环节；字符量本身不证明实际输入或收费量。" if reason_ratio else "- 可见思考样本不足，无法计算比例。",
        f"- 同题完成样本中，AStudio 工具返回文本是{'、'.join(comparisons)}。与 WorkBuddy 的差距较小，与 QwenWork 的差距较大；需结合工具种类和内容截断策略解释。",
        f"- AStudio 有 {fmt(metered)} 个思考字符没有原生 usage 推进，单独记录，不能换算后补入正式 Token 总量。",
        "- AStudio 的异常检索题有超长、未推进 usage 的思考。全量小计与四端共同排除该题的同题比较并列展示，避免把这一异常当作正常交互特征。", "",
        "## 可见字符总量", "", "| Harness / 用例数 | 思考/摘要 | 模型正文 | 工具参数 | 工具返回文本 |", "|---|---:|---:|---:|---:|"]
    for h, g in report["groups"].items():
        output.append(f"| {h} / {g['tasks']} | " + " | ".join(fmt(g['categories'][k]['visible_sum_chars'])
                      for k in ("reasoning", "assistant_text", "tool_arguments", "tool_results")) + " |")
    a_group = report["groups"]["AstronStudio"]
    output += ["", f"工具 Schema 单独列在上下文表中，不重复计入工具返回。AStudio 返回项为普通结果 {a_group['observed_tool_result_items']} 项及 Schema 结果 {a_group['loaded_schema_result_items']} 项；各端回执中的调用总数与字符分析覆盖如下。", "",
        "| Harness | 正式工具调用数 | 保存参数的调用数 | 保存普通返回的项数 |", "|---|---:|---:|---:|"]
    for h, g in report["groups"].items():
        output.append(f"| {h} | {fmt(g['formal_tool_count'])} | {g['observed_tool_argument_items']} | {g['observed_tool_result_items']} |")
    output += ["", "## 排除执行异常题的同题比较", "",
        "四端同时排除以下 task_id，仅用于减少异常长尾对比较的影响；有效评测的分母和原结果保持不变：", "",
        *[f"- `{t}`" for t in report["excluded_task_ids_for_matched_completed"]], "",
        "| Harness / 同题数 | 思考/摘要 | 模型正文 | 工具参数 | 工具返回文本 |", "|---|---:|---:|---:|---:|"]
    for h, g in report["matched_completed_groups"].items():
        output.append(f"| {h} / {g['tasks']} | " + " | ".join(fmt(g['categories'][k]['visible_sum_chars'])
                      for k in ("reasoning", "assistant_text", "tool_arguments", "tool_results")) + " |")
    output += ["", "## 共同可见的三类内容构成", "",
        "仅以模型正文、工具参数、工具返回文本之和为分母，排除思考、用户 Prompt、上下文和 Schema。DoubaoWork 为已保存内容的小计构成。", "",
        "| Harness | 正文占比 | 工具参数占比 | 工具返回占比 |", "|---|---:|---:|---:|"]
    for h, g in report["groups"].items():
        values = [g["categories"][k]["visible_sum_chars"] for k in ("assistant_text", "tool_arguments", "tool_results")]
        total = sum(values)
        output.append(f"| {h} | " + " | ".join(f"{v / total:.1%}" if total else "不可见" for v in values) + " |")
    output += ["", "## 每题分布", "", "中位数用于描述典型用例，P90 使用最近秩法（排序后第 ceil(0.9 × n) 项）。零表示该字段在日志中没有可见内容；不可见字段记为 null，不用零替代。", "",
        "| Harness | 内容 | 每题中位数 | 每题 P90 | 记录到非空内容的题数 |", "|---|---|---:|---:|---:|"]
    for h, g in report["groups"].items():
        for k in ("reasoning", "assistant_text", "tool_arguments", "tool_results"):
            c = g["categories"][k]
            coverage = f"{c['positive_tasks']}/{g['tasks']}" if c['available_tasks'] else "不可见"
            output.append(f"| {h} | {LABELS[k]} | {fmt(c['median_per_task_chars'])} | {fmt(c['p90_per_task_chars'])} | {coverage} |")
    output += ["", "## 用户输入与可见上下文", "",
        "| Harness | 用户输入 | 可见注入上下文 | 已记录工具 Schema |", "|---|---:|---:|---:|"]
    for h, g in report["groups"].items():
        output.append(f"| {h} | " + " | ".join(fmt(g['categories'][k]['visible_sum_chars'])
                      for k in ("user_prompt", "injected_context", "tool_schema")) + " |")
    output += ["", "AStudio 的上下文包含 base_instructions、developer 消息和用户通道中的额外上下文；WorkBuddy 是原始用户消息扣除冻结 Prompt 后的前缀；QwenWork 是 system-reminder 和有明文 content 的 attachment。它们都不代表完整系统提示词，不能直接比较系统提示词大小。Schema 仅计已记录定义；重复展开计实际记录次数，无法确定每轮请求重复携带量。", "",
        "## 工具返回的主要来源", ""]
    for h, g in report["groups"].items():
        output += [f"### {h}", "", "| 工具名 | 参数字符 | 返回字符 | 参数项数 | 返回项数 |", "|---|---:|---:|---:|---:|"]
        for name, v in list(g["by_tool"].items())[:8]:
            output.append(f"| {name} | {fmt(v['argument_chars'])} | {fmt(v['result_chars'])} | {v['call_items']} | {v['result_items']} |")
        output.append("")
    output += ["## 来源差异与结论边界", "",
        "- **AStudio**：只读取绑定 rollout 的 response_item，排除 event_msg 镜像。思考正文优先 content，其次 summary；两者都是可见文本。没有推进原生 usage 的思考单独标记，不混入已计量响应。",
        "- **WorkBuddy**：读取 workbuddy-session.jsonl；该批日志只有 input_text/output_text，没有明文思考。工具结果只取 output 文本，不重复统计 providerData.toolResult 和 rawResponse。",
        "- **QwenWork**：读取原始 transcript.jsonl 的 thinking/text/tool_use/tool_result；不合并 segments 中的镜像。工具返回取 content block，不取含本地展示信息的 toolUseResult；图片内容不折算字符。",
        "- **DoubaoWork**：正文取绑定回复的 runtime-messages text_block.text，工具内容取正式归一化 transcript。thinking_block 只有标题，text_block.summary 是展示摘要，两者都不当作模型思考。缺少远端参数/结果的调用不补造内容；工具字符量是可见小计。部分本地工具结果尚不能证明与模型实际接收文本完全一致。",
        "- 参数为字符串时先解析 JSON，并统一为 ensure_ascii=False、sort_keys=True 的紧凑 JSON。长度含字段名、JSON 结构与转义字符；工具返回只统计文本通道，不计本地包装、重复 stdout、图片 base64。其他正文按解码后的 Unicode 字符数统计。",
        "- 同一块内容只计一次；不根据重复文本去重。只有相同原生事件/调用 ID 的一致重放才去重，ID 相同而内容不同会报错。",
        "- 可比较模型正文和工具内容的可见负担；不能用思考不可见推导没有思考，也不能凭字符总量推断历史保留策略、每轮输入增量或因果关系。", "",
        "## 原件可追溯性", "",
        "所有数据读取前核对执行 attempt、执行记录 SHA、trace-index 身份及原件 SHA/大小；AStudio supplemental rollout 同时核对补充回执绑定。JSON 逐题保留来源绝对路径、SHA、内容长度/哈希和行号或 JSON 指针，不复制原始内容。", ""]
    return "\n".join(output)


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=False)
    (output / "trace-character-analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (output / "trace-character-analysis.md").write_text(render(report))
    with (output / "task-character-distribution.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["harness", "task_id", "execution_status", "trace_completeness", *CATEGORIES]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for task in report["tasks"]:
            writer.writerow({**{k: task[k] for k in fields[:4]}, **task["visible_chars"]})
    with (output / "content-length-evidence.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["harness", "task_id", "category", "chars", "utf8_bytes", "content_sha256", "source", "ref", "tool_name", "scope"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for task in report["tasks"]:
            for item in task["items"]:
                writer.writerow({"harness": task["harness"], "task_id": task["task_id"], **item})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.round_root.resolve())
    require(not args.output_dir.exists(), "OUTPUT_DIRECTORY_EXISTS")
    write_report(report, args.output_dir.resolve())
    print(json.dumps({"output_dir": str(args.output_dir.resolve()),
                      "tasks": {h: g["tasks"] for h, g in report["groups"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
