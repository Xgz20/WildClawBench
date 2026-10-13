#!/usr/bin/env python3
"""Compare a bound AstronStudio result with frozen round1 Token diagnostics.

This writes derived diagnostics only. It does not repair frozen receipts,
reinterpret scores, or convert visible characters into billable Tokens.
"""
from __future__ import annotations

import argparse
import collections
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import statistics
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from astronstudio_context_diagnosis import FIELDS, digest, parse_rollout, read_file, require
from token_growth_analysis import _task_summary, _percentile, _curve
from trace_character_analysis import parse_astron


OUTPUT_CATEGORIES = ("reasoning", "assistant_text", "tool_arguments", "tool_results")
GROUPS = ("AstronStudio 3.3.1", "AstronStudio 3.5.0", "WorkBuddy round1", "QwenWork round1")


def normalize_workspace_prompt(text):
    return re.sub(r"\./workspace(?=/|[`\"'\s]|$)", ".", text)


def load(path):
    data = read_file(path)
    return json.loads(data), {"path": str(Path(path).resolve()), "sha256": digest(data), "size": len(data)}


def summary(tasks):
    result = {"tasks": len(tasks), "responses": sum(t["interaction_count"] for t in tasks),
              "transitions": sum(max(0, t["interaction_count"] - 1) for t in tasks)}
    for name in ("first_input_tokens", "last_input_tokens", "last_to_first_input_ratio", "input_slope_tokens_per_interaction"):
        values = [t[name] for t in tasks if t[name] is not None]
        result[name] = {"median": statistics.median(values) if values else None,
                        "p90": _percentile(values, .9), "samples": len(values)}
    result["native_usage"] = {k: sum(sum(s[k] for s in t["series"]) for t in tasks) for k in FIELDS}
    result["curve"] = _curve(tasks)
    return result


def transitions(task_id, requests):
    """Use a shared character screen when reasoning Token splits are absent."""
    result = []
    for a, b in zip(requests, requests[1:]):
        delta = b["input_tokens"] - a["input_tokens"]
        residual = delta - a["output_tokens"]
        model_chars = a["reasoning_chars"] + a["assistant_text_chars"] + a["tool_arguments_chars"]
        share = a["reasoning_chars"] / model_chars if model_chars else None
        original = common = "ordinary-or-unresolved"
        if delta >= 10000:
            if a["reasoning_output_tokens"] >= .7 * delta and abs(residual) <= max(1000, .15 * delta):
                original = "reasoning-history-candidate"
            elif a["tool_results_chars"] >= 10000 and a["output_tokens"] < .3 * delta:
                original = "large-tool-result-candidate"
            else:
                original = "mixed-or-unresolved-large-jump"
            if (a["output_tokens"] >= .7 * delta and abs(residual) <= max(1000, .15 * delta)
                    and a["reasoning_chars"] >= 10000 and share is not None and share >= .7):
                common = "reasoning-dominated-output-history-candidate"
            elif a["tool_results_chars"] >= 10000 and a["output_tokens"] < .3 * delta:
                common = "large-tool-result-candidate"
            else:
                common = "mixed-or-unresolved-large-jump"
        result.append({"task_id": task_id, "from_request": a["request_index"], "to_request": b["request_index"],
            "from_usage_line": a["usage_line"], "to_usage_line": b["usage_line"],
            "input_before": a["input_tokens"], "input_after": b["input_tokens"], "input_delta_tokens": delta,
            "previous_output_tokens": a["output_tokens"], "previous_reasoning_tokens": a["reasoning_output_tokens"],
            "previous_reasoning_chars": a["reasoning_chars"], "previous_assistant_chars": a["assistant_text_chars"],
            "previous_tool_arguments_chars": a["tool_arguments_chars"], "previous_tool_results_chars": a["tool_results_chars"],
            "visible_reasoning_share_of_model_output_chars": share, "residual_after_previous_output": residual,
            "original_screen": original, "common_screen": common})
    return result


def prompt_from_transcript(path):
    rows = [json.loads(line) for line in read_file(path).decode().splitlines() if line.strip()]
    matches = [r["content"] for r in rows if isinstance(r, dict) and r.get("type") == "user_message"]
    require(len(matches) == 1, "PROMPT_TRANSCRIPT_BINDING")
    return matches[0]


def shell_commands_for_candidates(data, requests, step_rows):
    indexes = {r["from_request"] for r in step_rows if r["common_screen"] == "large-tool-result-candidate"}
    selected = {i["call_id"] for r in requests if r["request_index"] in indexes for i in r["contents"]
                if i["category"] == "tool_results" and i.get("tool_name") in ("bash", "exec_command")}
    result = {}
    for number, line in enumerate(data.decode().splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        payload = event.get("payload") or {}
        if event["type"] != "response_item" or payload.get("type") != "function_call" or payload.get("call_id") not in selected:
            continue
        arguments = payload.get("arguments")
        arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
        require(isinstance(arguments, dict), "SHELL_ARGUMENTS_OBJECT_EXPECTED")
        name = payload["name"]
        field = "command" if name == "bash" else "cmd"
        command = arguments.get(field)
        require(name in ("bash", "exec_command") and isinstance(command, str), "SHELL_COMMAND_MISSING")
        result[payload["call_id"]] = {"tool_name": name, "call_id": payload["call_id"], "call_line": number,
            "argument_field": field, "command": command, "command_sha256": digest(command.encode()),
            "max_output_tokens": arguments.get("max_output_tokens")}
    require(set(result) == selected, "SHELL_COMMAND_BINDING_INCOMPLETE")
    return result


def characterize(rows):
    result = {}
    for category in OUTPUT_CATEGORIES:
        values = [r["visible_chars"][category] for r in rows if r["visible_chars"][category] is not None]
        result[category] = {"sum_chars": sum(values) if values else None,
            "median_per_task": statistics.median(values) if values else None,
            "p90_per_task": _percentile(values, .9), "known_tasks": len(values), "tasks": len(rows)}
    return result


def analyze(old_root, round2_root, report_path):
    old_growth, old_growth_ref = load(old_root / ".general-e2e/audit/token-growth-analysis-final.json")
    old_diagnosis, old_diag_ref = load(old_root / "reports/astronstudio-context-diagnosis-20261009/astronstudio-context-diagnosis.json")
    old_chars, old_char_ref = load(old_root / "reports/trace-character-analysis-20261010-101615/trace-character-analysis.json")
    old_md = old_root / ".general-e2e/audit/token-growth-analysis-final.md"
    old_md_data = read_file(old_md)
    old_md_ref = {"path": str(old_md), "sha256": digest(old_md_data), "size": len(old_md_data)}
    report, report_ref = load(report_path)
    target_rows = [t for t in report["tasks"] if t["harness"]["id"] == "astronstudio" and t["harness"]["version"] == "3.5.0"]
    old_report_rows = {t["task_id"]: t for t in report["tasks"] if t["harness"]["id"] == "astronstudio" and t["harness"]["version"] == "3.3.1"}
    old_tasks = [t for t in old_growth["tasks"] if t["harness"] == "AstronStudio"]
    require(len(target_rows) == 60 and {t["task_id"] for t in target_rows} == {t["task_id"] for t in old_tasks}, "TASK_SCOPE_MISMATCH")
    require(all(t["task_definition"]["prompt"] == old_report_rows[t["task_id"]]["task_definition"]["prompt"] for t in target_rows), "BENCHMARK_PROMPT_DEFINITION_DRIFT")
    require(old_diagnosis["summary"]["native_usage"] == summary(old_tasks)["native_usage"], "OLD_DIAGNOSTIC_USAGE_DRIFT")
    current, step_rows, provenance, reconciliation = [], [], [], []
    archive_path = old_root / "deliverables/general-e2e-valid_20260929_144149.zip"
    old_prompts = {}
    # The source ZIP is used only to verify the actual old prompt, not to
    # replace the frozen diagnostic series or reinterpret old responses.
    with ZipFile(archive_path) as archive:
        prefix = archive_path.stem + "/ResourceSupplements/supplements/astronstudio/"
        for task in old_tasks:
            name = prefix + task["task_id"] + "/raw/astronstudio-rollout.jsonl"
            raw = archive.read(name)
            events = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
            prompts = [e["payload"]["message"] for e in events if e["type"] == "event_msg"
                       and e.get("payload", {}).get("type") == "user_message"]
            require(len(prompts) == 1, "OLD_ARCHIVED_PROMPT_AMBIGUOUS")
            old_prompts[task["task_id"]] = {"text": prompts[0], "archive": str(archive_path),
                "member": name, "member_sha256": digest(raw), "prompt_sha256": digest(prompts[0].encode())}
    prompt_equivalence = []
    for reported in target_rows:
        ep = Path(reported["lineage"]["source_execution_record"])
        require(ep.resolve().is_relative_to(round2_root.resolve()), "NEW_SOURCE_OUTSIDE_ROUND2")
        execution, ex_ref = load(ep)
        require(ex_ref["sha256"] == reported["lineage"]["execution_record_sha256"], "EXECUTION_SHA_DRIFT")
        identity = execution["identity"]
        require(identity["task_id"] == reported["task_id"] and identity["attempt_id"] == reported["execution_attempt_id"], "ATTEMPT_BINDING_DRIFT")
        require(execution["harness"]["version"] == "3.5.0" and execution["harness"]["platform"] == "macos-arm64", "CLIENT_VERSION_DRIFT")
        require(str(execution["model"].get("actual_id", "")).replace("-", "").replace(" ", "").lower() == "sparkx2.5"
                and str(execution["model"].get("reasoning_effort", "")).lower() == "high", "MODEL_CONFIGURATION_DRIFT")
        trace_index, trace_ref = load(ep.parent / "trace/trace-index.json")
        require(trace_index["identity"] == identity and all(
            trace_index["session"].get(k) == execution["session"].get(k)
            for k in ("thread_id", "turn_id", "session_id", "cwd")), "TRACE_BINDING_DRIFT")
        ref = next(r for r in trace_index["raw_trace"] if r["path"] == "raw/astronstudio-rollout.jsonl")
        rollout_path = ep.parent / "trace/raw/astronstudio-rollout.jsonl"
        raw = read_file(rollout_path)
        require(digest(raw) == ref["sha256"] and len(raw) == ref["size"], "ROLLOUT_SHA_DRIFT")
        parsed = parse_rollout(raw, execution)
        prompt = prompt_from_transcript(ep.parent / "trace/transcript.jsonl")
        require(digest(prompt.encode()) == execution["prompt"]["sha256"], "PROMPT_SHA_DRIFT")
        old_prompt = old_prompts[identity["task_id"]]
        require(normalize_workspace_prompt(old_prompt["text"]) == prompt, "ACTUAL_PROMPT_CONTENT_DRIFT")
        prompt_equivalence.append({"task_id": identity["task_id"], "old_archive": old_prompt["archive"],
            "old_member": old_prompt["member"], "old_member_sha256": old_prompt["member_sha256"],
            "old_prompt_sha256": old_prompt["prompt_sha256"], "new_prompt_sha256": execution["prompt"]["sha256"],
            "normalization": "Only the known ./workspace root (including child paths) -> .", "equivalent": True})
        characters = parse_astron(raw, execution, prompt, str(rollout_path))
        series = [{"interaction_index": r["request_index"], **{k: r[k] for k in FIELDS},
                   "raw_line": r["usage_line"]} for r in parsed["requests"]]
        native = {k: sum(r[k] for r in series) for k in FIELDS}
        partial = []
        for field, resource_key in [("input_tokens", "input_tokens"), ("cached_input_tokens", "cache_read_input_tokens"),
            ("output_tokens", "output_tokens"), ("reasoning_output_tokens", "reasoning_output_tokens"), ("total_tokens", "total_tokens")]:
            metric = reported["resource"][resource_key]
            if metric["value"] is not None:
                require(native[field] == metric["value"], "REPORT_USAGE_DRIFT")
            else:
                require(metric["status"] == "partial" and native[field] == metric["known_subtotal"]
                        and parsed["nonadvancing_invalid_last_usage"], "UNEXPLAINED_PARTIAL_USAGE")
                partial.append(resource_key)
        count_metric = reported["resource"]["request_count"]
        require(len(series) == (count_metric["value"] if count_metric["value"] is not None else count_metric["known_subtotal"]), "RESPONSE_COUNT_DRIFT")
        task = {"task_id": identity["task_id"], "identity": identity, "execution_status": reported["execution_status"],
            "frozen_execution_status": execution["execution"]["business_status"], "execution_error": execution["execution"]["error"],
            "model": execution["model"], "harness": execution["harness"], "rollout_path": str(rollout_path),
            "rollout_sha256": digest(raw), "execution_source": ex_ref, "trace_index_source": trace_ref,
            "visible_chars": characters.totals(), "character_diagnostics": dict(characters.diagnostics),
            "startup": parsed["startup"],
            "post_initial_context_messages": parsed["post_initial_context_messages"],
            "compaction_lines": parsed["compaction_lines"], "unmetered_windows": parsed["unmetered_windows"],
            "nonadvancing_invalid_last_usage": parsed["nonadvancing_invalid_last_usage"],
            "requests": parsed["requests"], "character_items": characters.items, **_task_summary(series)}
        task_steps = transitions(identity["task_id"], parsed["requests"])
        task["candidate_shell_commands"] = shell_commands_for_candidates(raw, parsed["requests"], task_steps)
        current.append(task)
        step_rows.extend(task_steps)
        provenance.extend([ex_ref, trace_ref, {"path": str(rollout_path), "sha256": digest(raw), "size": len(raw)}])
        reconciliation.append({"task_id": identity["task_id"], "responses": len(series), "native_usage": native,
            "formal_report_partial_fields": partial, "formal_receipts_changed": False})
    groups = {"AstronStudio 3.3.1": summary(old_tasks), "AstronStudio 3.5.0": summary(current)}
    for h in ("WorkBuddy", "QwenWork"):
        groups[h + " round1"] = summary([t for t in old_growth["tasks"] if t["harness"] == h])
    old_noncompleted = {t["task_id"] for t in old_chars["tasks"] if t["harness"] == "AstronStudio" and t["execution_status"] != "completed"}
    new_noncompleted = {t["task_id"] for t in current if t["execution_status"] != "completed"}
    excluded = old_noncompleted | new_noncompleted
    matched = {t["task_id"] for t in current} - excluded
    character_groups = {"AstronStudio 3.5.0": characterize([t for t in current if t["task_id"] in matched])}
    all_character_groups = {"AstronStudio 3.5.0": characterize(current)}
    for h in ("AstronStudio", "WorkBuddy", "QwenWork"):
        label = "AstronStudio 3.3.1" if h == "AstronStudio" else h + " round1"
        rows = [t for t in old_chars["tasks"] if t["harness"] == h]
        character_groups[label] = characterize([t for t in rows if t["task_id"] in matched])
        all_character_groups[label] = characterize(rows)
    paired_growth = {"AstronStudio 3.3.1": summary([t for t in old_tasks if t["task_id"] in matched]),
                     "AstronStudio 3.5.0": summary([t for t in current if t["task_id"] in matched])}
    old_steps = [r for t in old_diagnosis["tasks"] for r in transitions(t["task_id"], t["requests"])]
    screens = {}
    for label, rows in (("AstronStudio 3.3.1", old_steps), ("AstronStudio 3.5.0", step_rows)):
        large = [r for r in rows if r["input_delta_tokens"] >= 10000]
        screens[label] = {"large_jumps": len(large), "all_transitions": len(rows),
            "original_screen": dict(collections.Counter(r["original_screen"] for r in large)),
            "common_screen": dict(collections.Counter(r["common_screen"] for r in large)),
            "large_tool_task_ids": sorted({r["task_id"] for r in large if r["common_screen"] == "large-tool-result-candidate"})}
    def startup_profile(tasks, character_tasks):
        return {"provider_ids": sorted({t["startup"]["model_provider"] for t in tasks}),
                "core_versions": sorted({t["startup"]["cli_version"] for t in tasks}),
                "base_instruction_chars": sorted({t["startup"]["base_instructions_chars"] for t in tasks}),
                "initial_developer_chars": sorted({t["startup"]["developer_messages_chars"] for t in tasks}),
                "initial_schema_chars": sorted({i["chars"] for t in character_tasks
                    for i in t.get("character_items", t.get("items", [])) if i.get("scope") == "initial-schema-registry"})}
    return {"schema_version": "astronstudio-version-token-comparison/v1", "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "groups": groups, "matched_completed_growth": paired_growth,
        "matched_completed_character_groups": character_groups, "all_character_groups": all_character_groups,
        "matched_completed_task_ids": sorted(matched), "excluded_task_ids_for_matched_completed": sorted(excluded),
        "jump_screens": screens, "new_tasks": current, "new_transitions": step_rows,
        "old_transitions_common_screen": old_steps, "reconciliation": reconciliation,
        "prompt_equivalence": prompt_equivalence,
        "startup_profiles": {"AstronStudio 3.3.1": startup_profile(old_diagnosis["tasks"], [t for t in old_chars["tasks"] if t["harness"] == "AstronStudio"]),
                             "AstronStudio 3.5.0": startup_profile(current, current)},
        "sources": [old_growth_ref, old_diag_ref, old_char_ref, report_ref, *provenance],
        "baseline_document": old_md_ref,
        "comparison_scope": "Same 60 benchmark task IDs and frozen benchmark prompt definitions; different client version, architecture, date and relative-workspace rendering; historical peers not rerun",
        "formal_source_report_modified": False, "formal_partial_reconciled_diagnostically": [r["task_id"] for r in reconciliation if r["formal_report_partial_fields"]]}


def fmt(v, decimals=0):
    return "unavailable" if v is None else f"{v:,.{decimals}f}"


def change(a, b):
    return (b / a - 1) * 100


def large_tool_problem_summary_markdown(d, candidates):
    section = d.get("large_tool_problem_summary")
    if not section:
        return []
    require(section["source_report_sha256"] == d["sources"][3]["sha256"], "EDITORIAL_SOURCE_REPORT_DRIFT")
    key = lambda r: (r["task_id"], r["from_request"], r["to_request"])
    selected = {key(r): r for r in candidates}
    problems = section["specific_problems"]
    require(len(problems) == len(selected) and {key(r) for r in problems} == set(selected), "EDITORIAL_CANDIDATE_SCOPE_DRIFT")
    lines = ["", "### 9大工具问题总结", "", "#### 共性问题", "",
        "从这9个候选窗口看，问题主要集中在以下几方面：", ""]
    for number, item in enumerate(section["common_problems"], 1):
        lines += [f"{number}. **{item['title']}**", f"   {item['description']}", ""]
    lines += [f"**建议优先处理：{section['recommendation']}**", "", "#### 具体9个问题", "",
        "下面逐条对应9个相邻请求窗口。同类问题可能出现在多个窗口，一个窗口也可能包含多个工具调用；输入增量是相邻请求的观测值，不是已证明的精确工具Token归因。", ""]
    for number, item in enumerate(problems, 1):
        row = selected[key(item)]
        require(item["return_chars"] == row["previous_tool_results_chars"] and
                item["input_delta_tokens"] == row["input_delta_tokens"], "EDITORIAL_MEASUREMENT_DRIFT")
        lines += [f"{number}. **{item['title']}**", f"   用例：`{item['task_id']}`；请求变化：{item['from_request']}→{item['to_request']}。",
            f"   {item['description']} 返回合计 **{fmt(item['return_chars'])}字符**，相邻输入增加 **{fmt(item['input_delta_tokens'])} Token**。", ""]
    return lines


def markdown(d):
    g, c = d["groups"], d["matched_completed_character_groups"]
    old, new, wb, qw = (g[k] for k in GROUPS)
    ratio = lambda label, other, k: c[label][k]["sum_chars"] / c[other][k]["sum_chars"]
    med = lambda group, k: group[k]["median"]
    p90 = lambda group, k: group[k]["p90"]
    ns = d["jump_screens"]["AstronStudio 3.5.0"]
    os = d["jump_screens"]["AstronStudio 3.3.1"]
    pipl = next(t for t in d["new_tasks"] if "pipl_article13" in t["task_id"])
    sec = next(t for t in d["new_tasks"] if "sec_filing_preread" in t["task_id"])
    nchar = len(d["matched_completed_task_ids"])
    lines = ["# AstronStudio 3.5.0 与 3.3.1 模型交互 Token 增长分析", "", f"生成时间：{d['generated_at']}", "",
        "## 结论", "",
        "基于相同60道通用场景题目，以中位数看典型增长、P90看长尾膨胀、斜率看每次交互的增长速度。目标为 M 芯片 Mac 上的 AstronStudio 3.5.0 官方正式版，旧版为 Intel Mac 上的3.3.1；两者均使用 Spark X2.5 / High。WorkBuddy、QwenWork沿用 round1 历史结果，没有在 round2 重跑。", "",
        f"1. **输入上下文增长更快的结论仍成立，但首尾涨幅有所收敛。** 3.5.0的末轮/首轮增长倍数中位数为 **{med(new,'last_to_first_input_ratio'):.2f}倍**，旧版为{med(old,'last_to_first_input_ratio'):.2f}倍，WorkBuddy、QwenWork为{med(wb,'last_to_first_input_ratio'):.2f}倍、{med(qw,'last_to_first_input_ratio'):.2f}倍。新版本输入增长斜率中位数为 **{fmt(med(new,'input_slope_tokens_per_interaction'))} Token/交互**，约为两端的 **{med(new,'input_slope_tokens_per_interaction')/med(wb,'input_slope_tokens_per_interaction'):.2f}倍、{med(new,'input_slope_tokens_per_interaction')/med(qw,'input_slope_tokens_per_interaction'):.2f}倍**；比旧版{fmt(med(old,'input_slope_tokens_per_interaction'))}高{change(med(old,'input_slope_tokens_per_interaction'),med(new,'input_slope_tokens_per_interaction')):.1f}%。",
        f"2. **长尾膨胀仍明显，但幅度比旧版降低。** 末轮/首轮增长倍数P90为 **{p90(new,'last_to_first_input_ratio'):.2f}倍**，旧版{p90(old,'last_to_first_input_ratio'):.2f}倍，下降{-change(p90(old,'last_to_first_input_ratio'),p90(new,'last_to_first_input_ratio')):.1f}%；仍高于WorkBuddy、QwenWork的{p90(wb,'last_to_first_input_ratio'):.2f}倍、{p90(qw,'last_to_first_input_ratio'):.2f}倍。可以说首尾膨胀收敛，不能说每次交互的增长速度已降下来。",
        f"3. **累计输入仍受到个别长循环任务支配。** 新版可对账输入合计{fmt(new['native_usage']['input_tokens'])} Token，约为旧版的{new['native_usage']['input_tokens']/old['native_usage']['input_tokens']:.2f}倍。PIPL题单独有{pipl['interaction_count']}次响应、{fmt(pipl['input_tokens_sum'])}输入 Token，占新版本输入的{pipl['input_tokens_sum']/new['native_usage']['input_tokens']:.1%}。输入包含缓存读取，这个数字表示上下文处理量，不等同于费用。", "",
        "### 增长主要来自哪些内容", "",
        f"字符比较使用四组共同完成的 **{nchar}道题**：同时排除旧版执行错误的PIPL题和新版终态异常的SEC题，避免不同异常长尾主导比较。旧报告的4.77倍、2.86倍和1.06倍来自另一组59题，不与这里的{nchar}题比例混用。", "",
        f"1. **长思考及其历史保留仍值得优先核查。** 新版可见思考/摘要{fmt(c['AstronStudio 3.5.0']['reasoning']['sum_chars'])}字符，是历史QwenWork的 **{ratio('AstronStudio 3.5.0','QwenWork round1','reasoning'):.2f}倍**；同题旧版为{ratio('AstronStudio 3.3.1','QwenWork round1','reasoning'):.2f}倍，新版字符量减少{-change(c['AstronStudio 3.3.1']['reasoning']['sum_chars'],c['AstronStudio 3.5.0']['reasoning']['sum_chars']):.1f}%，差距仍然存在。WorkBuddy、DoubaoWork未保存明文思考，不能按0比较。",
        f"2. **工具返回偏大的结论相对QwenWork仍成立，相对WorkBuddy差距很小。** 新版工具返回文本是QwenWork的 **{ratio('AstronStudio 3.5.0','QwenWork round1','tool_results'):.2f}倍**，为WorkBuddy的 **{ratio('AstronStudio 3.5.0','WorkBuddy round1','tool_results'):.2f}倍**。同题工具返回总字符较旧版减少{-change(c['AstronStudio 3.3.1']['tool_results']['sum_chars'],c['AstronStudio 3.5.0']['tool_results']['sum_chars']):.1f}%，仍需核查具体检索命令、内容提取和裁剪方式。",
        f"3. **大幅输入跃升的现象仍存在，思考来源需要用内容证据判断。** 新版核验60题、{new['responses']}次可对账响应、{new['transitions']}次相邻变化，输入增量≥1万Token共 **{ns['large_jumps']}次**：{ns['common_screen'].get('reasoning-dominated-output-history-candidate',0)}次符合“上一响应以思考文本为主、输出量与下一次输入增量接近”的特征，{ns['common_screen'].get('large-tool-result-candidate',0)}次符合大工具返回特征。旧版为{os['large_jumps']}次。**这些是诊断线索，不能当作精确因果归因。**", "",
        "新版原生usage的 `reasoning_output_tokens` 全部为0，但rollout中确实有思考文本。因此无法沿用依赖推理Token细分的旧版15次判据来证明新版具体的推理保留量，也不能把0解释为没有思考。", "",
        "## 样本与统计来源", "",
        "| 单元 | 题目 | 可对账响应 | 相邻请求变化 | 两次以上响应的斜率样本 |", "|---|---:|---:|---:|---:|"]
    for label in GROUPS:
        x = g[label]
        lines.append(f"| {label} | {x['tasks']} | {x['responses']} | {x['transitions']} | {x['input_slope_tokens_per_interaction']['samples']} |")
    lines += ["", "60题ID和冻结题目定义中的Prompt逐题一致。实际发送时旧版采用 `./workspace/` 路径，新版采用 `./`，工作目录组织方式不同；版本、芯片、日期和运行环境也不同。本报告属于跨轮结果对比，不将变化单独归因于3.5.0代码或M芯片。", "",
        "实际发送Prompt也已逐题核对：仅将已知工作目录 `./workspace`（含子路径）归一为 `.` 后，60/60相同。对比表中的客户端版本、模型和推理配置来自冻结执行记录；官方正式版本的分发属性由本次结果提供方说明。", "",
        "### 初始上下文与运行链路变化", "",
        "| 版本 | rollout Provider | Core版本 | 基础指令字符 | 初始developer字符 | 初始动态工具Schema字符 |", "|---|---|---|---:|---:|---:|"]
    for label, profile in d["startup_profiles"].items():
        values = lambda k: ", ".join(fmt(v) for v in profile[k])
        lines.append(f"| {label} | {', '.join(profile['provider_ids'])} | {', '.join(profile['core_versions'])} | {values('base_instruction_chars')} | {values('initial_developer_chars')} | {values('initial_schema_chars')} |")
    lines += ["", f"新版首轮输入中位数比旧版增加{change(med(old,'first_input_tokens'),med(new,'first_input_tokens')):.1f}%。这说明初始混合上下文也变化了，不能直接称为系统提示词Token增加。Schema这里只计已记录的初始动态注册定义，不能保证覆盖每次请求实际携带的全部工具。Provider/Core链路也变了，模型显示名一致不证明后端协议和计量细分一致。", "",
        "### PIPL原报告partial的处理", "",
        f"`{pipl['task_id']}` 的原资源报告为partial，输入已知小计{fmt(pipl['input_tokens_sum'])}、响应已知小计{pipl['interaction_count']}。本次只读核对原件发现：压缩后有一条累计用量不变的快照，其last为input=0、output=0、total=16912，不满足模型响应的计量等式；本分析单独登记，未计为新增响应或Token。其余{pipl['interaction_count']}次累计推进均与last逐字段对账，因而纳入本报告的增长诊断。**原资源回执、评分和正式汇总报告未改写；这里统计的是可对账响应量，不能据此证明完整HTTP账单或压缩模型调用消耗。**", "",
        "## 首轮、末轮与增长速度", "",
        "| 单元 | 首轮输入中位数 | 末轮输入中位数 | 末轮/首轮中位数 | 末轮/首轮P90 | 斜率中位数 | 斜率P90 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for label in GROUPS:
        x = g[label]
        lines.append(f"| {label} | {fmt(med(x,'first_input_tokens'),1)} | {fmt(med(x,'last_input_tokens'),1)} | {med(x,'last_to_first_input_ratio'):.3f} | {p90(x,'last_to_first_input_ratio'):.3f} | {fmt(med(x,'input_slope_tokens_per_interaction'),1)} | {fmt(p90(x,'input_slope_tokens_per_interaction'),1)} |")
    lines += ["", "增长倍数先逐题计算末轮/首轮，再跨题取中位数或P90；不等于“末轮中位数÷首轮中位数”。斜率对每题分别拟合，并仅使用至少两次响应的题目。", "",
        "### 共同完成58题的敏感性检查", "",
        "| 版本 | 样本数 | 增长倍数中位数 | 增长倍数P90 | 斜率中位数 |", "|---|---:|---:|---:|---:|"]
    for label, x in d["matched_completed_growth"].items():
        lines.append(f"| {label} | {x['tasks']} | {med(x,'last_to_first_input_ratio'):.3f} | {p90(x,'last_to_first_input_ratio'):.3f} | {fmt(med(x,'input_slope_tokens_per_interaction'),1)} |")
    lines += ["", "## 可对账响应的累计用量", "",
        "| 单元 | 输入Token（含缓存） | 缓存读取Token | 输出Token | 原生推理输出细分 |", "|---|---:|---:|---:|---:|"]
    for label in GROUPS:
        u = g[label]["native_usage"]
        lines.append(f"| {label} | {fmt(u['input_tokens'])} | {fmt(u['cached_input_tokens'])} | {fmt(u['output_tokens'])} | {fmt(u['reasoning_output_tokens'])} |")
    lines += ["", "输入包含缓存读取，输出包含原生推理输出细分，不能重复相加。新版推理细分0、其他两端历史推理细分0均不能推导实际无思考；不同模型计量字段的可见范围不同。", "",
        "### 长循环与终态异常", "",
        "| 新版用例 | 响应数 | 累计输入 | 峰值单次输入 | 首轮→末轮输入 | 原始终态 |", "|---|---:|---:|---:|---:|---|"]
    for t in (pipl, sec):
        lines.append(f"| [{t['task_id']}]({t['execution_source']['path']}) | {t['interaction_count']} | {fmt(t['input_tokens_sum'])} | {fmt(t['peak_input_tokens'])} | {fmt(t['first_input_tokens'])}→{fmt(t['last_input_tokens'])} | {t['frozen_execution_status']} |")
    lines += ["", "PIPL题包含一次上下文压缩，首尾指标不能反映期间反复携带较大上下文的累计负担。SEC题的原始错误是 `ASTRONSTUDIO_NATIVE_IDLE_WATCHDOG`，冻结执行状态为infrastructure_error；管理员后续将其派生报告状态裁定为candidate_error。这里保留来源差异，不重评分。", "",
        "## 按交互进度观察上下文滚雪球", "",
        "每题按0%–100%映射到最近的一次请求，再跨题取中位数。它用于描述典型任务轨迹，不能代表某一题或把长短任务当作相同轮数。增量为当前进度中位数减0%中位数。", "",
        "| 进度 | AStudio 3.3.1 | 相对0%增量 | AStudio 3.5.0 | 相对0%增量 | WorkBuddy历史 | QwenWork历史 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for i, point in enumerate(new["curve"]):
        oldp, wp, qp = old["curve"][i], wb["curve"][i], qw["curve"][i]
        lines.append(f"| {point['normalized_progress']:.0%} | {fmt(oldp['median_input_tokens'],1)} | {oldp['delta_from_zero_tokens']:+,.1f} | {fmt(point['median_input_tokens'],1)} | {point['delta_from_zero_tokens']:+,.1f} | {fmt(wp['median_input_tokens'],1)} | {fmt(qp['median_input_tokens'],1)} |")
    lines += ["", "## 思考、正文、工具参数和工具返回字符", "",
        f"以下使用共同完成的{nchar}题，单位为Unicode字符。每条可见内容只计一次；不累计后续请求中的重传，不换算计费Token。AStudio取reasoning.content或summary，QwenWork取thinking，两者可见字段范围不同。", "",
        "| 单元 | 可见思考/摘要 | 模型正文 | 工具参数 | 工具返回文本 |", "|---|---:|---:|---:|---:|"]
    for label in GROUPS:
        x = c[label]
        lines.append(f"| {label} | " + " | ".join(fmt(x[k]["sum_chars"]) for k in OUTPUT_CATEGORIES) + " |")
    lines += ["", "### 每题字符中位数与P90", "",
        "| 单元 | 思考中位数 / P90 | 正文中位数 / P90 | 参数中位数 / P90 | 返回中位数 / P90 |", "|---|---:|---:|---:|---:|"]
    for label in GROUPS:
        x = c[label]
        lines.append(f"| {label} | " + " | ".join(f"{fmt(x[k]['median_per_task'])} / {fmt(x[k]['p90_per_task'])}" for k in OUTPUT_CATEGORIES) + " |")
    lines += ["", "### 全60题的可见字符小计", "",
        "| 单元 | 思考/摘要 | 正文 | 工具参数 | 工具返回 |", "|---|---:|---:|---:|---:|"]
    for label in GROUPS:
        x = d["all_character_groups"][label]
        lines.append(f"| {label} | " + " | ".join(fmt(x[k]["sum_chars"]) for k in OUTPUT_CATEGORIES) + " |")
    lines += ["", "旧版全量思考包含5,191,758字符的未计量异常区间，不能与新版全量小计直接解释为正常思考强度变化。共同完成样本避开该异常。", "",
        "## 输入跃升与来源线索", "",
        "| 版本 | 响应 / 相邻变化 | ≥1万Token跃升 | 跃升比例 | 思考为主的输出历史候选 | 大工具返回候选 |", "|---|---:|---:|---:|---:|---:|"]
    for label in ("AstronStudio 3.3.1", "AstronStudio 3.5.0"):
        x, ss = d["jump_screens"][label], g[label]
        lines.append(f"| {label} | {ss['responses']} / {ss['transitions']} | {x['large_jumps']} | {x['large_jumps']/x['all_transitions']:.1%} | {x['common_screen'].get('reasoning-dominated-output-history-candidate',0)} | {x['common_screen'].get('large-tool-result-candidate',0)} |")
    lines += ["", "旧报告15次思考历史保留候选依赖原生reasoning_output_tokens。为跨版本比较，本节另用统一字符判据：Δ输入≥10,000，上次输出≥Δ输入的70%，|Δ输入−上次输出|≤max(1,000,15%×Δ输入)，上次可见思考≥10,000字符且占可见模型输出字符≥70%。大工具判据维持：返回≥10,000字符，上次输出<Δ输入的30%。", "",
        "此判据只说明时序与量级吻合。尤其新版推理Token细分不可用，不能把“思考为主的输出历史候选”改称已证明的推理Token保留。", "",
        "### 新版最大跃升实例", "",
        "| 用例 | 请求变化 | 输入增量 | 上次输出Token | 上次思考字符 | 上次工具返回字符 | 线索 |", "|---|---|---:|---:|---:|---:|---|"]
    labels = {"reasoning-dominated-output-history-candidate": "思考为主的输出历史候选", "large-tool-result-candidate": "大工具返回候选", "mixed-or-unresolved-large-jump": "待解释"}
    byid = {t["task_id"]: t for t in d["new_tasks"]}
    for row in sorted(d["new_transitions"], key=lambda x: -x["input_delta_tokens"])[:12]:
        t = byid[row["task_id"]]
        lines.append(f"| [{row['task_id']}]({t['rollout_path']}:{row['from_usage_line']}) | {row['from_request']}→{row['to_request']} | {fmt(row['input_delta_tokens'])} | {fmt(row['previous_output_tokens'])} | {fmt(row['previous_reasoning_chars'])} | {fmt(row['previous_tool_results_chars'])} | {labels.get(row['common_screen'],'普通/待解释')} |")
    candidates = [r for r in d["new_transitions"] if r["common_screen"] == "large-tool-result-candidate"]
    lines += large_tool_problem_summary_markdown(d, candidates)
    lines += ["", f"### 新版{len(candidates)}次大工具返回候选完整明细", "",
        f"下表逐条列出全部{len(candidates)}个相邻请求窗口，涉及{len({r['task_id'] for r in candidates})}个用例。`10→11`表示第10次响应及其工具结果之后，第11次请求的输入增长。字符数是该窗口内工具返回的合计，可能包含多个工具结果；它不是每个工具的单次最大返回，也不意味着已证明精确的Token归因。", "",
        "| 序号 | 用例ID | 请求变化 | 实际工具及返回项数 | 工具返回字符合计 | 输入增加Token | 原始返回行 |", "|---:|---|---|---|---:|---:|---|"]
    call_details = []
    for number, row in enumerate(candidates, 1):
        task = byid[row["task_id"]]
        request = next(r for r in task["requests"] if r["request_index"] == row["from_request"])
        results = [i for i in request["contents"] if i["category"] == "tool_results"]
        counts = collections.Counter(i.get("tool_name") or "unknown-native-tool-name" for i in results)
        tools = "、".join(f"`{name}` × {count}" for name, count in counts.items())
        refs = "、".join(f"[{i['line']}]({task['rollout_path']}:{i['line']})" for i in results)
        lines.append(f"| {number} | {row['task_id']} | {row['from_request']}→{row['to_request']} | {tools} | {fmt(row['previous_tool_results_chars'])} | {fmt(row['input_delta_tokens'])} | {refs} |")
        argument_refs = {i["call_id"]: i for request in task["requests"] for i in request["contents"]
                         if i["category"] == "tool_arguments" and i.get("call_id")}
        for item in results:
            argument = argument_refs.get(item.get("call_id"))
            require(argument is not None and argument.get("tool_name") == item.get("tool_name"), "TOOL_CALL_RETURN_BINDING_DRIFT")
            call_details.append({"window": number, "task_id": row["task_id"], "tool_name": item["tool_name"],
                "call_id": item["call_id"], "chars": item["chars"], "call_line": argument["line"],
                "result_line": item["line"], "rollout_path": task["rollout_path"]})
    lines += ["", "其中SEC题3次窗口使用bash，Apple题2次使用exec_command；RFC题2次、Node题1次、NIST题1次使用原生astron_web_fetch。新版本这4次Web Fetch窗口不能沿用旧版的curl来源解释。工具名可直接由原始调用及返回关联核验；Web Fetch存在调用不代表每条返回都成功。", "",
        "### 实际工具调用汇总", "",
        f"上述{len(candidates)}个窗口内共关联{len(call_details)}条工具调用及返回，其中{sum(r['chars'] >= 10000 for r in call_details)}条单独返回达到1万字符。工具名称按rollout中的原始调用名统计，不把bash内部的curl、grep等命令另算为工具。", "",
        "| 原始工具名 | 覆盖候选窗口数 | 关联调用及返回条数 | 单条返回≥1万字符的条数 |", "|---|---:|---:|---:|"]
    for name in dict.fromkeys(r["tool_name"] for r in call_details):
        selected = [r for r in call_details if r["tool_name"] == name]
        lines.append(f"| `{name}` | {len({r['window'] for r in selected})} | {len(selected)} | {sum(r['chars'] >= 10000 for r in selected)} |")
    lines += ["", f"### 窗口内{len(call_details)}条工具调用逐项明细", "",
        "窗口序号对应上一张9行候选表。每条通过call_id将原始function_call与function_call_output关联；行号链接可直接查看调用参数及返回内容。", "",
        "| 窗口序号 | 原始工具名 | 调用ID | 返回字符数 | 调用行 | 返回行 |", "|---:|---|---|---:|---:|---:|"]
    for item in call_details:
        path = item["rollout_path"]
        lines.append(f"| {item['window']} | `{item['tool_name']}` | `{item['call_id']}` | {fmt(item['chars'])} | [{item['call_line']}]({path}:{item['call_line']}) | [{item['result_line']}]({path}:{item['result_line']}) |")
    shell_details = [i for i in call_details if i["tool_name"] in ("bash", "exec_command")]
    lines += ["", "### bash与exec_command的具体命令", "",
        f"这{len(shell_details)}次shell调用的完整命令可以直接读取：bash取function_call.arguments.command，exec_command取function_call.arguments.cmd。以下保留原始命令文本及当时的/tmp路径，并关联调用和返回原件。", "",
        "SEC题的5次调用都是对已下载的Microsoft 10-K HTML执行rg；Apple题的第1次是curl下载后打印HTML头部，第2次是在本地HTML中搜索Greater China。head只限制行数，不能保证单行HTML的字符长度较小。", ""]
    for number, item in enumerate(shell_details, 1):
        task = byid[item["task_id"]]
        command = task["candidate_shell_commands"][item["call_id"]]
        require(command["tool_name"] == item["tool_name"] and command["call_line"] == item["call_line"], "SHELL_COMMAND_REFERENCE_DRIFT")
        budget = command["max_output_tokens"]
        budget_text = "未显式设置" if budget is None else json.dumps(budget, ensure_ascii=False)
        path = item["rollout_path"]
        lines += [f"#### shell调用{number}：窗口{item['window']} / {item['tool_name']}", "",
            f"用例：`{item['task_id']}`；call_id：`{item['call_id']}`。",
            f"原始max_output_tokens参数：{budget_text}；返回{fmt(item['chars'])}字符。"
            f"[调用行{item['call_line']}]({path}:{item['call_line']})、[返回行{item['result_line']}]({path}:{item['result_line']})。", "",
            "```bash", command["command"], "```", ""]
    lines += ["max_output_tokens展示原始参数值；引号表示原件中以字符串传递。这里没有确认该参数在bash实现中实际生效，不能据此认定执行输出已按该Token上限裁剪。", "",
        "### 旧版4个大工具返回用例在新版的表现", "",
        "| 用例ID | 旧版大返回跃升次数 | 新版大返回跃升次数 | 新版最大输入跃升 |", "|---|---:|---:|---:|"]
    for task_id in os["large_tool_task_ids"]:
        previous = [r for r in d["old_transitions_common_screen"] if r["task_id"] == task_id and r["common_screen"] == "large-tool-result-candidate"]
        now = [r for r in d["new_transitions"] if r["task_id"] == task_id]
        count = sum(r["common_screen"] == "large-tool-result-candidate" for r in now)
        lines.append(f"| {task_id} | {len(previous)} | {count} | {fmt(max((r['input_delta_tokens'] for r in now), default=None))} |")
    lines += ["", "新版另有SEC题3次、NIST题1次大返回候选。每次候选对应相邻请求窗口，该窗口可能包含多个工具结果；候选次数不等于大工具调用次数。没有达到阈值不代表没有较长返回。", "",
        "## 公式与可复核口径", "",
        "- 请求k：本题第k次累计usage推进且与last逐字段对账的模型响应，从1开始；不等同于HTTP尝试次数。",
        "- 首轮/末轮：各题第一个/最后一个有效响应的input_tokens；增长倍数=末轮/首轮。",
        "- 中位数：先逐题计算指标，再跨题取中位数；偶数样本取中间两项平均。P90采用排序后的第ceil(0.9×n)项。",
        "- 斜率：每题拟合 ŷ_k=a+b×k；k是响应序号，y_k是单次输入，b=Σ[(k−k̄)(y_k−ȳ)]/Σ[(k−k̄)²]，a=ȳ−b×k̄。b单位Token/交互，a不是系统提示词Token；少于2次响应记unavailable，不补0。",
        "- 字符：只统计response_item，排除镜像，重复同ID一致项去重；工具参数统一紧凑JSON，可见工具返回只计文本，不把图片base64当正文。",
        "- 系统提示词、工具Schema、历史思考和工具返回的精确输入Token占比仍需要完整outbound payload；首轮混合输入和缓存读取无法反推。",
        "- 用量未推进的新内容独立保存；压缩时的16912快照未补入正式Token总量。未知消耗保持未知。", "",
        "## 数据与证据位置", "",
        "本报告的JSON保存全部新版本请求序列、逐题字符、跃升判据、异常快照以及原件路径、SHA和身份。CSV供逐题及逐请求复核。旧版沿用已有冻结分析结果，本次没有重跑旧客户端或重评分。", "",
        "- [分析数据 JSON](evidence/analysis-data.json)", "- [逐题增长 CSV](evidence/task-growth.csv)", "- [逐请求原生用量 CSV](evidence/model-responses.csv)", "- [相邻输入变化 CSV](evidence/adjacent-request-changes.csv)", "",
        "### 固定输入", ""]
    baseline = d["baseline_document"]
    lines.append(f"- [旧版分析文档]({baseline['path']})：SHA256 `{baseline['sha256']}`")
    for source in d["sources"][:4]:
        lines.append(f"- [{Path(source['path']).name}]({source['path']})：SHA256 `{source['sha256']}`")
    lines += ["", "### 分析代码", "", "分析器位于WildClawBench的 `report-general-e2e/scripts/astronstudio_version_comparison.py`。重复累计快照的异常last仅在累计有效且不推进时单独审计；推进快照必须满足完整计量等式与累计对账，错误不放行。", ""]
    return "\n".join(lines)


def write(d, output):
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence"
    evidence.mkdir()
    (output / "astronstudio-token-growth-analysis.md").write_text(markdown(d), encoding="utf-8")
    (evidence / "analysis-data.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (evidence / "task-growth.csv").open("w", newline="", encoding="utf-8-sig") as f:
        keys = ["task_id", "interaction_count", "first_input_tokens", "last_input_tokens", "last_to_first_input_ratio", "input_slope_tokens_per_interaction", "input_tokens_sum", "cached_input_tokens_sum", "output_tokens_sum", "reasoning_output_tokens_sum", "execution_status", "frozen_execution_status", "rollout_path"]
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for task in d["new_tasks"]:
            writer.writerow({k: task[k] for k in keys})
    with (evidence / "model-responses.csv").open("w", newline="", encoding="utf-8-sig") as f:
        keys = ["task_id", "request_index", "usage_line", *FIELDS, "reasoning_chars", "assistant_text_chars", "tool_arguments_chars", "tool_results_chars"]
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for task in d["new_tasks"]:
            for row in task["requests"]:
                writer.writerow({"task_id": task["task_id"], **{k: row[k] for k in keys if k != "task_id"}})
    with (evidence / "adjacent-request-changes.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(d["new_transitions"][0]))
        writer.writeheader()
        writer.writerows(d["new_transitions"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round1-root", type=Path, required=True)
    parser.add_argument("--round2-root", type=Path, required=True)
    parser.add_argument("--target-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    d = analyze(args.round1_root.resolve(), args.round2_root.resolve(), args.target_report.resolve())
    d["analysis_implementation"] = [{"path": str((Path(__file__).parent / name).resolve()),
        "sha256": digest(read_file(Path(__file__).parent / name))} for name in
        ("astronstudio_version_comparison.py", "astronstudio_context_diagnosis.py", "trace_character_analysis.py", "token_growth_analysis.py")]
    write(d, args.output_dir.resolve())
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "new_summary": d["groups"]["AstronStudio 3.5.0"],
                      "new_jump_screens": d["jump_screens"]["AstronStudio 3.5.0"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
