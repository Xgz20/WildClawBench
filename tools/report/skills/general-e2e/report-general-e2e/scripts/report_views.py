"""Reader-facing tables shared by Excel and Markdown; unknown values stay null."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

CAPABILITIES = {
    "code_generation": "代码生成", "tool_use": "工具调用", "data_processing": "数据处理",
    "retrieval_verification": "检索验证", "reasoning_planning": "推理规划",
    "content_generation": "内容生成", "verification_delivery": "验证交付",
}
CATEGORIES = {
    "01_Productivity_Flow": "生产力工作流", "02_Code_Intelligence": "代码智能",
    "03_Social_Interaction": "社交互动", "04_Creative_Synthesis": "创意合成",
    "05_Search_Retrieval": "搜索检索", "06_Safety_Alignment": "安全对齐",
}
HARNESSES = {"workbuddy": "WorkBuddy", "astronstudio": "AstronStudio", "qwenwork": "QwenWork", "doubaowork": "DoubaoWork"}
MODALITIES = {"pure-text": "纯文本", "multimodal": "多模态"}


def reference_payload(root):
    # YAML is needed only in the source checkout/build environment. Distributed
    # Skills consume a deterministic JSON snapshot with canonical-source hashes.
    import yaml
    paths = [root / "entities.yaml", root / "checkpoint_capability_map7.yaml"]
    entities, capabilities = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in paths]
    names = {}
    for kind in ("models", "harnesses"):
        names[kind] = {}
        for key, value in entities.get(kind, {}).items():
            for alias in [key, *value.get("aliases", [])]:
                names[kind][alias] = value.get("display_name") or key
    return {"schema_version": "wildclawbench.general-report-reference/v1", **names,
            "capabilities": capabilities,
            "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def load_references():
    skill = Path(__file__).resolve().parents[1]
    bundled = skill / "data/report-reference.json"
    if bundled.is_file():
        value = json.loads(bundled.read_text(encoding="utf-8"))
        root = skill / "vendor/e2e-shared/report-reference-data"
        for name, expected in value["sources"].items():
            if Path(name).name != name or hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
                raise ValueError("REPORT_REFERENCE_SOURCE_DRIFT")
        return value
    return reference_payload(Path(__file__).resolve().parents[4] / "data")


def checkpoints(score, score_path, resolve_file, sha256_file):
    if not score or score.get("result", {}).get("valid") is not True:
        return {"values": {}, "sources": []}
    values, sources = {}, []
    semantic = score.get("components", {}).get("semantics", {}).get("status") == "completed"
    for criterion in score.get("evaluation", {}).get("criteria", []):
        if criterion["key"] != "automated_component":
            if criterion.get("status") == "judged":
                values[f"llm_judge.{criterion['key']}"] = criterion.get("score")
            continue
        refs = [r for r in criterion.get("evidence", []) if r.get("type") == "rule_result"]
        if len(refs) > 1:
            raise ValueError("REPORT_RULE_RESULT_AMBIGUOUS")
        if not refs:
            continue
        ref = refs[0]
        path = resolve_file(score_path.parent, ref["path"], "rule result")
        digest = sha256_file(path)
        if ref.get("sha256") != digest:
            raise ValueError("REPORT_RULE_RESULT_DRIFT")
        rule = json.loads(path.read_text(encoding="utf-8"))
        if rule.get("status") != "completed" or rule.get("score") != criterion.get("score"):
            raise ValueError("REPORT_RULE_RESULT_MISMATCH")
        for key, value in rule.get("raw_scores", {}).items():
            values[("automated." if semantic else "") + key] = value
        sources.append({"path": ref["path"], "sha256": digest})
    values["overall_score"] = score["result"]["total_score"]
    return {"values": values, "sources": sources}


def trace_tools(root, execution, resolve_file, sha256_file):
    rel = execution.get("evidence", {}).get("trace_index_path")
    if not rel or not (root / rel).exists():
        return {"status": "unavailable", "by_tool": {}, "total": None, "basis": "归档中没有可读取的标准轨迹"}
    path = resolve_file(root, rel, "trace index")
    index = json.loads(path.read_text(encoding="utf-8"))
    if index.get("identity") != execution["identity"]:
        raise ValueError("REPORT_TRACE_IDENTITY_MISMATCH")
    ref = index["transcript"]
    transcript = resolve_file(path.parent, ref["path"], "transcript")
    if sha256_file(transcript) != ref["sha256"] or transcript.stat().st_size != ref["size"]:
        raise ValueError("REPORT_TRANSCRIPT_DRIFT")
    calls = {}
    for line in transcript.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("identity") != execution["identity"]:
            raise ValueError("REPORT_TRANSCRIPT_IDENTITY_MISMATCH")
        if event.get("type") != "tool_call":
            continue
        tool = event.get("tool") or {}
        call_id, name = tool.get("call_id"), tool.get("name") or "未命名工具"
        if not call_id or (call_id in calls and calls[call_id] != name):
            raise ValueError("REPORT_TOOL_CALL_ID_CONFLICT")
        calls[call_id] = name
    status = "complete" if index.get("completeness", {}).get("status") == "complete" else "partial"
    return {"status": status, "by_tool": dict(sorted(Counter(calls.values()).items())), "total": len(calls),
            "transcript_path": transcript.relative_to(root).as_posix(),
            "basis": "标准轨迹 tool_call 按单题 call_id 去重，不从 completed 推断工具成功",
            "trace_index_sha256": sha256_file(path), "transcript_sha256": ref["sha256"]}


def number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool)


def normalized(key, value, values):
    if not number(value) or re.search(r"(_max$|_calls$|_attempts$|_triggered$|^penalty)", key):
        return None
    if key.endswith("_earned"):
        maximum = values.get(key[:-7] + "_max")
        return min(1, max(0, value / maximum)) if number(maximum) and maximum > 0 else None
    return value if 0 <= value <= 1 else None


def capability_scores(rows, mapping):
    result = {}
    for dimension in CAPABILITIES:
        scores, eligible = [], 0
        for row in rows:
            keys = [key for key, dims in mapping.get(row["task_id"], {}).items() if dimension in dims]
            if not keys:
                continue
            eligible += 1
            if row["score_status"] != "valid":
                continue
            values = row.get("checkpoints", {}).get("values", {})
            mapped = [normalized(key, values.get(key), values) for key in keys]
            # Missing a mapped criterion must not silently improve the task mean.
            if all(value is not None for value in mapped):
                scores.append(sum(mapped) / len(mapped))
        result[dimension] = {"score": sum(scores) / len(scores) if scores else None,
                             "known": len(scores), "total": eligible}
    return result


def table(headers, rows, formats=None, notes=None):
    return {"headers": headers, "rows": rows, "formats": formats or {}, "notes": notes or []}


def build_views(data, references):
    import report_case_views
    units = sorted(data["units"], key=lambda u: (u["score"]["mean_score"] is None, -(u["score"]["mean_score"] or 0), u["unit_id"]))
    prepared, labels = [], Counter()
    for unit in units:
        rows = [row for row in data["tasks"] if row["unit_id"] == unit["unit_id"]]
        models = {row["model"].get("actual_id") for row in rows if row["model"].get("verification_status") == "verified"}
        known = len(models) == 1 and None not in models and all(row["model"].get("verification_status") == "verified" for row in rows)
        model_id = next(iter(models)) if known else None
        model = references["models"].get(model_id, model_id) if known else ("混合模型" if len(models - {None}) > 1 else "未知模型")
        harness_id = unit["harness"]["id"]
        harness = references["harnesses"].get(harness_id, HARNESSES.get(harness_id, harness_id))
        label = f"{model}@{harness}"
        labels[label] += 1
        prepared.append((unit, rows, label))
    overview, efficiency, tools, dimension_coverage, metadata = [], [], [], [], []
    labels_by_id, caps = {}, {}
    for unit, rows, label in prepared:
        if labels[label] > 1:
            label += f"〔{unit['unit_id']}〕"
        labels_by_id[unit["unit_id"]] = label
        resources, score = unit["resources"], unit["score"]
        total = lambda key: resources[key]["total"]
        n = len(rows)
        completed = sum(row["execution_status"] == "completed" for row in rows)
        errors = sum(row["execution_status"] == "candidate_error" for row in rows)
        anomalies = sum(row["execution_status"] == "infrastructure_error" or row["score_status"] == "evaluation_error" for row in rows)
        overview.append([label, score["mean_score"] * 100 if score["mean_score"] is not None else None,
                         n, completed, errors, anomalies, completed/n if n else None,
                         score["valid_score_count"], score["unscored_count"], total("total_tokens"), total("request_count"),
                         total("call_count"), total("agent_duration_seconds"), total("duration_seconds")])
        cached, inputs, writes = total("cache_read_input_tokens"), total("input_tokens"), total("cache_creation_input_tokens")
        if inputs is not None and ((cached is not None and cached > inputs) or (writes is not None and writes > inputs)
                                   or (cached is not None and writes is not None and cached + writes > inputs)):
            raise ValueError("REPORT_CACHE_EXCEEDS_INPUT")
        ordinary = inputs - cached - writes if inputs is not None and cached is not None and writes is not None else None
        efficiency.append([label, total("total_tokens"), total("total_tokens")/n if total("total_tokens") is not None and n else None,
                           ordinary, cached, writes, total("output_tokens"),
                           cached/inputs if cached is not None and inputs is not None and inputs > 0 else None])
        caps[unit["unit_id"]] = capability_scores(rows, references["capabilities"])
        grouped, known = Counter(), 0
        for row in rows:
            detail = row.get("tool_calls", {})
            if detail.get("status") == "complete" and detail.get("total") == row["resource"]["call_count"]["value"]:
                known += 1
            grouped.update(detail.get("by_tool", {}))
        tools.append([label, "全部工具", total("call_count"), f"{known}/{n}"])
        tools.extend([label, name, count, "完整" if known == n else "已知小计"] for name, count in sorted(grouped.items(), key=lambda item: (-item[1], item[0])))
        judges = "; ".join(f"{group['protocol'] or '未评分'} / {group['model'] or '-'} / {group['reasoning_effort'] or '-'}: {group['frozen_task_run_count']}"
                           for group in unit["judge_groups"])
        metadata.append([unit["unit_id"], label, unit["model"].get("requested_id"),
                         " / ".join(str(unit["harness"].get(key) or "-") for key in ("id", "platform", "version")), judges])
    views = {
        "总览": table(["模型@Harness", "总平均分", "用例数", "正常完成数", "执行错误数", "评测异常数", "完成率", "有效评分数", "未评分数",
                       "总tokens", "总请求数", "工具调用数", "任务耗时(s)", "流程耗时(s)"], overview,
                      {"1": "0.00", "6": "0.00%", "12": "#,##0.000", "13": "#,##0.000"},
                      ["得分为百分制，均值只含有效评分；真实零分保留，评测异常和未评分不补零。",
                       "完成率=原生正常完成数/冻结用例数；执行情况与评分状态分别统计，异常数按任务去重，各列不要求相加等于用例数。",
                       "任务耗时=原生请求耗时之和；流程耗时包含发送及等待。总请求数按客户端可观测模型响应/请求口径，来源详见资源覆盖。"]),
        "效率对比": table(["模型@Harness", "总 Token", "平均 Token", "普通输入 Token", "缓存命中输入 Token", "缓存写入输入 Token", "输出 Token", "缓存命中率"],
                          efficiency, {"2": "#,##0.00", "7": "0.00%"},
                          ["平均 Token=总 Token/冻结任务运行数。普通输入=归一化输入总量−缓存命中输入−缓存写入输入；三项完整可观测时才计算。",
                           "缓存命中输入为 Cache Read，缓存写入输入为 Cache Write；缺失显示-，不默认零。写入或命中缺失且无独立普通输入字段时，普通输入也显示-。",
                           "缓存命中率=缓存命中输入 Token 总量/含缓存的输入 Token 总量，不平均逐题比例。缓存已计入输入总量，不再次加到总 Token。"]),
    }
    for name, key, names in [("分类对比", "category", CATEGORIES), ("难度对比", "difficulty", {}), ("模态对比", "modality", MODALITIES)]:
        groups = sorted({row.get(key) or "unknown" for row in data["tasks"]})
        table_rows = []
        for unit, rows, _ in prepared:
            label = labels_by_id[unit["unit_id"]]
            cells = []
            for group in groups:
                matching = [row for row in rows if (row.get(key) or "unknown") == group]
                values = [row["total_score"] for row in matching if row["score_status"] == "valid"]
                cells.append(sum(values)/len(values)*100 if values else None)
                dimension_coverage.append([label, name, names.get(group, group), len(values), len(matching)])
            table_rows.append([label, unit["score"]["mean_score"]*100 if unit["score"]["mean_score"] is not None else None, *cells])
        views[name] = table(["模型@Harness", "总平均分", *[names.get(g, g) for g in groups]], table_rows,
                            {str(i): "0.00" for i in range(1, len(groups)+2)}, ["分数为百分制；有效样本数/冻结样本数见资源覆盖与异常。无样本显示—，不补零。"])
    cap_rows = []
    for unit, rows, _ in prepared:
        label = labels_by_id[unit["unit_id"]]
        values = caps[unit["unit_id"]]
        cap_rows.append([label, unit["score"]["mean_score"]*100 if unit["score"]["mean_score"] is not None else None,
                         *[values[key]["score"]*100 if values[key]["score"] is not None else None for key in CAPABILITIES]])
        dimension_coverage.extend([label, "Agent能力对比", CAPABILITIES[key], value["known"], value["total"]] for key, value in values.items())
    views["Agent能力对比"] = table(["模型@Harness", "总平均分", *CAPABILITIES.values()], cap_rows,
                                      {str(i): "0.00" for i in range(1, 9)},
                                      ["复用常规报告七维检查点映射：任务内映射检查点取均值，再对任务均值取平均。缺失映射检查点不补分，不使用整题总分代替。",
                                       "无涉及任务的维度显示—；本表不依据少量样本自动判定强项或短板。"])
    views["工具调用对比"] = table(["模型@Harness", "工具", "调用数", "明细覆盖"], tools, notes=["仅统计调用次数。调用结束不等于执行成功；本版不计算格式准确率、执行成功率、不确定占比。"])
    order = ["总览", "效率对比", "分类对比", "难度对比", "Agent能力对比", "模态对比", "工具调用对比"]
    return {"schema_version": "wildclawbench.general-report-views/v1", "tables": {key: views[key] for key in order},
            **report_case_views.build_case_views(data, units, labels_by_id, table, CATEGORIES, MODALITIES),
            "sheet_order": order,
            "unit_labels": labels_by_id, "dimension_coverage": dimension_coverage, "unit_metadata": metadata,
            "reference_sources": references["sources"],
            "capability_coverage": caps}
