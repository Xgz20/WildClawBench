"""Reader-facing tables shared by Excel and Markdown; unknown values stay null."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import os
import subprocess

CAPABILITIES = {
    "code_generation": "代码生成", "tool_use": "工具调用", "data_processing": "数据处理",
    "retrieval_verification": "检索验证", "reasoning_planning": "推理规划",
    "content_generation": "内容生成", "verification_delivery": "验证交付",
}
CATEGORIES = {
    "01_Productivity_Flow": "生产力工作流", "02_Code_Intelligence": "代码智能",
    "03_Social_Interaction": "社交互动", "04_Creative_Synthesis": "创意合成",
    "05_Search_Retrieval": "搜索检索", "06_Safety_Alignment": "安全对齐",
    "04_Search_Retrieval": "搜索检索", "05_Creative_Synthesis": "创意合成",
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
    if any(r.get("path") == "raw/astronstudio-rollout.jsonl" for r in index.get("raw_trace", [])):
        script = Path(__file__).resolve().parents[1] / "vendor/e2e-shared/general-resource-supplements/astronstudio-rollout.mjs"
        if not script.is_file():
            script = Path(__file__).resolve().parents[4] / "e2e-shared/general-resource-supplements/astronstudio-rollout.mjs"
        run = subprocess.run([os.environ.get("GENERAL_E2E_NODE", "node"), str(script), "verify-index",
                              "--trace-index", str(path), "--binding", json.dumps(execution)],
                             capture_output=True, text=True, timeout=60)
        if run.returncode:
            raise ValueError("REPORT_ROLLOUT_REPLAY_FAILED: " + run.stderr[-1000:])
        verified = json.loads(run.stdout)
        return {**verified["tool_counts"], "transcript_path": transcript.relative_to(root).as_posix(),
                "rollout_path": (path.parent / "raw/astronstudio-rollout.jsonl").relative_to(root).as_posix(),
                "rollout_sha256": verified["source"]["sha256"], "trace_index_sha256": sha256_file(path),
                "transcript_sha256": ref["sha256"]}
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
    count_refs = [r for r in index.get("raw_trace", []) if r.get("path") == "raw/tool-count-summary.json"]
    if count_refs:
        if len(count_refs) != 1:
            raise ValueError("REPORT_TOOL_COUNT_PROOF_AMBIGUOUS")
        source = resolve_file(path.parent, count_refs[0]["path"], "tool count proof")
        if sha256_file(source) != count_refs[0]["sha256"] or source.stat().st_size != count_refs[0]["size"]:
            raise ValueError("REPORT_TOOL_COUNT_PROOF_DRIFT")
        proof = json.loads(source.read_text())
        counted = Counter(e["tool_name"] for e in proof["catalog"])
        identities = {(e["id_namespace"], e["native_id"]) for e in proof["catalog"]}
        if proof["status"] != "complete" or len(identities) != proof["total"] or sum(counted.values()) != proof["total"] or dict(counted) != proof["by_tool"]:
            raise ValueError("REPORT_TOOL_COUNT_CATALOG_MISMATCH")
        return {"status": "complete", "by_tool": proof["by_tool"], "total": proof["total"],
                "transcript_path": transcript.relative_to(root).as_posix(), "basis": proof["basis"],
                "trace_index_sha256": sha256_file(path), "transcript_sha256": ref["sha256"],
                "count_proof_sha256": count_refs[0]["sha256"], "process_trace_status": status}
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


def resource_display(resource):
    """Keep authoritative total=null, but expose a labelled observed subtotal."""
    value = resource.get("total")
    complete = number(value) and resource.get("status") == "complete"
    if not complete:
        value = resource.get("known_subtotal")
    coverage = resource.get("coverage", {})
    return {"value": value if number(value) else None,
            "status": "complete" if complete else "partial" if number(value) else "unavailable",
            "basis": "total" if complete else "known_subtotal" if number(value) else "unavailable",
            "complete_cases": coverage.get("known", 0),
            "partial_cases": resource.get("partial_case_count", 0),
            "total_cases": coverage.get("total", 0)}


def coverage_label(item):
    known, partial, total = item["complete_cases"], item["partial_cases"], item["total_cases"]
    return f"{known}完整+{partial}部分/{total}" if partial else f"{known}/{total}"


def timing_percentile(values, ratio):
    """Match Web's linear interpolation at (n - 1) * ratio."""
    if not values:
        return None
    ordered = sorted(Decimal(str(v)) for v in values)
    position = (len(ordered) - 1) * Decimal(str(ratio))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def task_timing_comparison(data, labels):
    import maas_model_timing as model_timing
    metric = "agent_duration_seconds"
    prepared = []
    for unit in data["units"]:
        rows = [r for r in data["tasks"] if r["unit_id"] == unit["unit_id"]]
        total = resource_display(unit["resources"][metric])
        observations = [r["resource"][metric] for r in rows]
        values = [o["value"] for o in observations if o.get("complete") and number(o.get("value"))
                  and math.isfinite(o["value"]) and o["value"] >= 0]
        complete = bool(rows) and len(values) == len(rows) and total["status"] == "complete"
        if complete and not math.isclose(sum(values), total["value"], rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError("REPORT_TASK_TIMING_TOTAL_MISMATCH")
        if complete:
            total["value"] = float(sum((Decimal(str(v)) for v in values), Decimal(0)))
        average = {**total, "value": float(Decimal(str(total["value"])) / len(rows)) if total["value"] is not None and rows else None,
                   "denominator": len(rows), "basis": "known-task-duration-sum-divided-by-frozen-task-count"}
        quantile = {"status": "complete" if complete else "unavailable", "basis": "complete-native-task-duration-samples",
                    "complete_cases": len(values), "partial_cases": 0, "total_cases": len(rows)}
        model = model_timing.summarize(rows)
        model_cell = {"status": "complete" if model["complete"] else "unavailable", "value": model["total"],
                      "complete_cases": model["known_cases"], "partial_cases": 0, "total_cases": len(rows),
                      "known_subtotal": model["known_subtotal"], "basis": model_timing.PROFILE}
        share = (float(Decimal(str(model["total"])) / Decimal(str(total["value"])))
                 if model["complete"] and complete and total["value"] > 0 else None)
        cells = [total, model_cell, {**model_cell, "value": share}, average,
                 {**model_cell, "value": float(Decimal(str(model["total"])) / len(rows)) if model["complete"] else None},
                 {**quantile, "value": timing_percentile(values, .5) if complete else None},
                 {**model_cell, "value": timing_percentile(model["values"], .5) if model["complete"] else None},
                 {**quantile, "value": timing_percentile(values, .9) if complete else None},
                 {**model_cell, "value": timing_percentile(model["values"], .9) if model["complete"] else None}]
        prepared.append((unit, cells, len(values), model))
    prepared.sort(key=lambda item: (item[1][0]["value"] is None, item[1][0]["value"] or 0, item[0]["unit_id"]))
    view = table(model_timing.HEADERS,
                 [[labels[u["unit_id"]], *[c["value"] for c in cells]] for u, cells, _, _ in prepared],
                 {str(i): "0.00%" if i == 3 else "#,##0.000" for i in range(1, 10)},
                 ["任务耗时来自原生主任务 agent_duration_seconds，包含已确认失败任务；不使用流程耗时 duration_seconds 替代，也不等同于批次壁钟。",
                  "平均任务耗时=完整总量或已知小计/当前比较用例数；部分统计标为下限。P50/P90只在逐题完整覆盖时计算，使用排序后(n-1)×p的线性插值；未知不补零，实测零保留。",
                  "模型耗时采用关联SID去重后的 maas_cube.perf 累计值(ms÷1000)，包含重试、失败/取消及压缩请求；占比=总模型耗时÷总任务耗时，累计口径在并行请求或服务端尾部处理时可能超过100%。",
                  "模型均值及P50/P90先按每题累计模型耗时计算；仅当前比较范围内请求与ES日志全覆盖时展示完整统计，部分已知小计保留在覆盖审计。其他Harness无法确定时显示“-”。"])
    view["metric_field"] = metric
    view["percentile_method"] = "linear-interpolation-(n-1)*p"
    view["title"] = "任务耗时对比（总任务耗时升序，缺失值置末）"
    view["model_metric_profile"] = model_timing.PROFILE
    view["cell_annotations"] = {f"{i}:{j}": c for i, (_, cells, _, _) in enumerate(prepared) for j, c in enumerate(cells, 1)}
    view["coverage_table"] = table(["模型@Harness", "任务耗时覆盖", "任务分位数样本", "比较用例数", "模型耗时完整用例", "模型请求ES覆盖"],
                                  [[labels[u["unit_id"]], coverage_label(cells[0]), f"{known}/{cells[0]['total_cases']}", cells[0]["total_cases"],
                                    f"{model['known_cases']}/{len([r for r in data['tasks'] if r['unit_id'] == u['unit_id']])}" if u.get("harness", {}).get("id") == "astronstudio" else "-",
                                    (f"{model['matched_requests']}已知/总数未知" if model["unknown_request_denominator_cases"] else f"{model['matched_requests']}/{model['expected_requests']}") if u.get("harness", {}).get("id") == "astronstudio" else "-"]
                                   for u, cells, known, model in prepared])
    return view


def attach_token_comparison(efficiency):
    """Sort displayed totals together with their coverage and partial markers."""
    rows = efficiency["rows"]
    order = sorted(range(len(rows)), key=lambda i: (rows[i][1] is None, rows[i][1] or 0, rows[i][0]))
    positions = {old: new for new, old in enumerate(order)}
    efficiency["rows"] = [rows[i] for i in order]
    efficiency["cell_annotations"] = {
        f"{positions[int(key.split(':')[0])]}:{key.split(':')[1]}": value
        for key, value in efficiency.get("cell_annotations", {}).items()
    }
    coverage = efficiency.get("coverage_table")
    if coverage:
        if [row[0] for row in coverage["rows"]] != [row[0] for row in rows]:
            raise ValueError("REPORT_TOKEN_COVERAGE_ORDER_MISMATCH")
        coverage["rows"] = [coverage["rows"][i] for i in order]
    efficiency.update(title="Token 对比（总 Token 升序，缺失值置末）", header_row=2)
    return efficiency


def attach_task_timing(data, efficiency, labels):
    timing = task_timing_comparison(data, labels)
    end = len(efficiency["rows"]) + efficiency.get("header_row", 1)
    end += len(efficiency["notes"]) + 6 + len(efficiency["coverage_table"]["rows"])
    timing["title_row"] = end + 3
    timing["header_row"] = end + 4
    timing_end = timing["header_row"] + len(timing["rows"])
    timing["coverage_title_row"] = timing_end + len(timing["notes"]) + 5
    timing["render_end_row"] = timing["coverage_title_row"] + 1 + len(timing["coverage_table"]["rows"])
    efficiency["timing_table"] = timing
    efficiency["render_row_count"] = timing["render_end_row"]
    return timing


def paired_token_measure(rows, fields, *, ratio=False):
    """Use the same task/source coverage for every operand; never zero-fill."""
    totals = [0 for _ in fields]
    complete_cases = partial_cases = 0
    for row in rows:
        observations = [row["resource"][field] for field in fields]
        values = [o.get("value") if o.get("complete") else o.get("known_subtotal") for o in observations]
        if not all(number(value) for value in values):
            continue
        complete = all(o.get("complete") for o in observations)
        signatures = [(o.get("coverage", {}).get("known"), o.get("coverage", {}).get("total"), o.get("coverage", {}).get("unit")) for o in observations]
        aligned_partial = (len(set(signatures)) == 1 and signatures[0][0] is not None
                           and signatures[0][0] > 0 and signatures[0][2] is not None)
        if not complete and not aligned_partial:
            continue
        if any(value < 0 for value in values) or sum(values[1:]) > values[0]:
            raise ValueError("REPORT_CACHE_EXCEEDS_INPUT")
        totals = [a + b for a, b in zip(totals, values)]
        if complete:
            complete_cases += 1
        else:
            partial_cases += 1
    count = complete_cases + partial_cases
    value = (totals[1] / totals[0] if totals[0] > 0 else None) if ratio else (totals[0] - sum(totals[1:]) if count else None)
    return {"value": value,
            "status": "unavailable" if value is None else "complete" if complete_cases == len(rows) else "partial",
            "basis": "paired-same-task-and-source-coverage",
            "complete_cases": complete_cases, "partial_cases": partial_cases, "total_cases": len(rows),
            "operand_fields": list(fields), "operand_subtotals": totals if count else None}


def build_views(data, references):
    import report_case_views
    units = sorted(data["units"], key=lambda u: (u["score"]["mean_score"] is None, -(u["score"]["mean_score"] or 0), u["unit_id"]))
    prepared, labels = [], Counter()
    overrides = data.get("display_overrides", {})
    if not isinstance(overrides, dict) or not isinstance(overrides.get("unit_model_labels", {}), dict):
        raise ValueError("REPORT_DISPLAY_OVERRIDES_INVALID")
    known_units = {u["unit_id"] for u in units}
    for unit_id, entry in overrides.get("unit_model_labels", {}).items():
        if unit_id not in known_units or not isinstance(entry, dict) or not isinstance(entry.get("label"), str) or not entry["label"].strip() or not entry.get("reason"):
            raise ValueError("REPORT_DISPLAY_OVERRIDE_SCOPE_INVALID")
    applied_overrides = {}
    for unit in units:
        rows = [row for row in data["tasks"] if row["unit_id"] == unit["unit_id"]]
        models = {row["model"].get("actual_id") for row in rows if row["model"].get("verification_status") == "verified"}
        known = len(models) == 1 and None not in models and all(row["model"].get("verification_status") == "verified" for row in rows)
        model_id = next(iter(models)) if known else None
        model = references["models"].get(model_id, model_id) if known else ("混合模型" if len(models - {None}) > 1 else "未知模型")
        requested_label = overrides.get("unit_model_labels", {}).get(unit["unit_id"])
        if requested_label:
            model = requested_label["label"]
            applied_overrides[unit["unit_id"]] = dict(requested_label)
        harness_id = unit["harness"]["id"]
        harness = references["harnesses"].get(harness_id, HARNESSES.get(harness_id, harness_id))
        label = f"{model}@{harness}"
        labels[label] += 1
        prepared.append((unit, rows, label))
    overview, efficiency, tools, dimension_coverage, metadata = [], [], [], [], []
    overview_cells, efficiency_cells, tool_cells = {}, {}, {}
    tool_groups = []
    overview_coverage, efficiency_coverage, resource_display_by_unit = [], [], {}
    labels_by_id, caps = {}, {}
    for unit, rows, label in prepared:
        if labels[label] > 1:
            label += f"〔{unit['unit_id']}〕"
        labels_by_id[unit["unit_id"]] = label
        resources, score = unit["resources"], unit["score"]
        display_metrics = {key: resource_display(value) for key, value in resources.items()}
        total = lambda key: display_metrics[key]["value"]
        n = len(rows)
        completed = sum(row["execution_status"] == "completed" for row in rows)
        errors = sum(row["execution_status"] == "candidate_error" for row in rows)
        anomalies = sum(row["execution_status"] == "infrastructure_error" or row["score_status"] == "evaluation_error" for row in rows)
        overview.append([label, score["mean_score"] * 100 if score["mean_score"] is not None else None,
                         n, completed, errors, anomalies, completed/n if n else None,
                         score["valid_score_count"], score["unscored_count"], total("total_tokens"), total("request_count"),
                         total("call_count"), total("agent_duration_seconds"), total("duration_seconds")])
        row_index = len(overview) - 1
        overview_fields = ["total_tokens", "request_count", "call_count", "agent_duration_seconds", "duration_seconds"]
        for col, field in enumerate(overview_fields, 9):
            overview_cells[f"{row_index}:{col}"] = {**display_metrics[field], "metric": field}
        overview_coverage.append([label, *[coverage_label(display_metrics[field]) for field in overview_fields]])
        cached, inputs, writes = total("cache_read_input_tokens"), total("input_tokens"), total("cache_creation_input_tokens")
        ordinary = paired_token_measure(rows, ["input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"])
        hit_rate = paired_token_measure(rows, ["input_tokens", "cache_read_input_tokens"], ratio=True)
        average = {**display_metrics["total_tokens"], "value": total("total_tokens") / n if total("total_tokens") is not None and n else None,
                   "basis": "known-token-sum-divided-by-frozen-task-count", "denominator": n}
        efficiency.append([label, total("total_tokens"), total("total_tokens")/n if total("total_tokens") is not None and n else None,
                           inputs, ordinary["value"], cached, writes, total("output_tokens"), hit_rate["value"]])
        efficiency_items = [display_metrics["total_tokens"], average, display_metrics["input_tokens"], ordinary,
                            display_metrics["cache_read_input_tokens"], display_metrics["cache_creation_input_tokens"],
                            display_metrics["output_tokens"], hit_rate]
        for col, item in enumerate(efficiency_items, 1):
            efficiency_cells[f"{row_index}:{col}"] = item
        efficiency_coverage.append([label, *[coverage_label(item) for item in efficiency_items]])
        resource_display_by_unit[unit["unit_id"]] = {"metrics": display_metrics, "average_tokens": average,
                                                    "ordinary_input_tokens": ordinary, "cache_hit_rate": hit_rate}
        caps[unit["unit_id"]] = capability_scores(rows, references["capabilities"])
        grouped, known = Counter(), 0
        for row in rows:
            detail = row.get("tool_calls", {})
            if detail.get("status") == "complete" and detail.get("total") == row["resource"]["call_count"]["value"]:
                known += 1
            grouped.update(detail.get("by_tool", {}))
        group_start = len(tools)
        tool_cells[f"{len(tools)}:2"] = {**display_metrics["call_count"], "metric": "call_count"}
        tools.append([label, "全部工具", total("call_count"), coverage_label(display_metrics["call_count"])])
        tools.extend([label, name, count, "计数完整" if known == n else "部分计数"] for name, count in sorted(grouped.items(), key=lambda item: (-item[1], item[0])))
        tool_groups.append({"unit_id": unit["unit_id"], "title": label,
            "headers": ["模型@Harness", "工具", "调用数", "计数覆盖"],
            "rows": tools[group_start:], "formats": {},
            "cell_annotations": {"0:2": dict(display_metrics["call_count"])} })
        judges = "; ".join(f"{group['protocol'] or '未评分'} / {group['model'] or '-'} / {group['reasoning_effort'] or '-'}: {group['frozen_task_run_count']}"
                           for group in unit["judge_groups"])
        metadata.append([unit["unit_id"], label, unit["model"].get("requested_id"),
                         " / ".join(str(unit["harness"].get(key) or "-") for key in ("id", "platform", "version")), judges])
    views = {
        "总览": table(["模型@Harness", "总平均分", "用例数", "正常完成数", "执行错误数", "评测异常数", "完成率", "有效评分数", "未评分数",
                       "总 Token", "总请求数", "工具调用数", "总任务耗时(s)", "流程耗时(s)"], overview,
                      {"1": "0.00", "6": "0.00%", "12": "#,##0.000", "13": "#,##0.000"},
                      ["得分为百分制，均值只含有效评分；真实零分保留，评测异常和未评分不补零。",
                       "完成率=原生正常完成数/冻结用例数；执行情况与评分状态分别统计，异常数按任务去重，各列不要求相加等于用例数。",
                       "任务耗时=原生主任务时长之和；新流程计时 Profile 从 Prompt 发送至本机确认终态，包含发送、排队与观察等待，排除发送前准备及评分、报告。历史不同边界须按补充审计复算。总请求数按客户端可观测模型响应/请求口径；AstronStudio 为 usage 更新推算，不是 HTTP 尝试次数。",
                       "星号或浅黄色背景表示部分统计的已知小计，完整总量仍未知；覆盖用例数见下表。缺失部分不按 0 填充，无任何可用数据时显示 -。"]),
        "效率对比": table(["模型@Harness", "总 Token", "平均 Token", "输入 Token（含缓存）", "普通输入 Token", "缓存命中输入 Token", "缓存写入输入 Token", "输出 Token", "缓存命中率"],
                          efficiency, {"2": "#,##0.00", "8": "0.00%"},
                          ["星号或浅黄色背景表示部分统计。平均 Token=已知 Token/冻结用例数；覆盖不全时是每题消耗下限，不是全量精确均值。",
                           "输入 Token（含缓存）直接展示可核验的输入统计。普通输入=输入−缓存命中−缓存写入，仅使用三个字段来源覆盖一致的用例。",
                           "缓存命中输入为 Cache Read，缓存写入输入为 Cache Write；缺失显示-，不默认零。写入或命中缺失且无独立普通输入字段时，普通输入也显示-。",
                           "缓存命中率只在同一用例、相同原生覆盖的输入与命中统计上计算：命中小计/输入小计。部分统计仅代表已知样本，样本范围见下表；不平均逐题比例。"]),
    }
    views["总览"]["cell_annotations"] = overview_cells
    views["总览"]["coverage_table"] = table(["模型@Harness", "Token覆盖", "请求覆盖", "工具覆盖", "任务耗时覆盖", "流程耗时覆盖"], overview_coverage)
    views["效率对比"]["cell_annotations"] = efficiency_cells
    views["效率对比"]["coverage_table"] = table(["模型@Harness", "总Token覆盖", "平均Token覆盖", "输入覆盖", "普通输入覆盖", "缓存命中覆盖", "缓存写入覆盖", "输出覆盖", "命中率样本"], efficiency_coverage)
    for name, key, names in [("分类对比", "category", CATEGORIES), ("难度对比", "difficulty", {}), ("模态对比", "modality", MODALITIES)]:
        groups = sorted({row.get(key) or "unknown" for row in data["tasks"]})
        frozen_counts = {g: len({row["task_id"] for row in data["tasks"] if (row.get(key) or "unknown") == g}) for g in groups}
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
        headings = [f"{g.split('_')[0]}_{names.get(g, g)}平均分({frozen_counts[g]}例)" if key == "category"
                    else f"{g}平均分({frozen_counts[g]}例)" if key == "difficulty"
                    else names.get(g, g) for g in groups]
        views[name] = table(["模型@Harness", "总平均分", *headings], table_rows,
                            {str(i): "0.00" for i in range(1, len(groups)+2)}, ["分数为百分制；有效样本数/冻结样本数见资源覆盖与异常。无样本显示—，不补零。"])
        if key in {"category", "difficulty"}:
            views[name]["group_task_counts"] = frozen_counts
            views[name]["notes"].append("表头例数为冻结的唯一用例数，参评单元不重复计数；有效评分样本数另列于覆盖统计。")
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
    views["工具调用对比"] = table(["模型@Harness", "工具", "调用数", "计数覆盖"], tools, notes=["按原生调用 ID 或远程工具块 ID 去重计数。计数完整不代表每次调用的参数、结果内容与顺序均完整；调用次数不等于执行成功次数。"])
    views["工具调用对比"]["cell_annotations"] = tool_cells
    if any(v["status"] == "partial" for v in tool_cells.values()):
        views["工具调用对比"]["notes"].append("星号或浅黄色背景表示部分计数，未验证部分不补零。")
    for name, annotations in [("总览", overview_cells), ("效率对比", efficiency_cells)]:
        if not any(v["status"] == "partial" for v in annotations.values()):
            views[name]["notes"] = [s for s in views[name]["notes"] if not s.startswith("星号或浅黄色")]
            views[name]["notes"].append("各指标的完整统计用例数见下表；客户端未暴露的字段显示 -。" + ("平均 Token=总 Token/冻结用例数。" if name == "效率对比" else ""))
    attach_token_comparison(views["效率对比"])
    attach_task_timing(data, views["效率对比"], labels_by_id)
    cursor = 1
    for group in tool_groups:
        group.update(title_row=cursor, header_row=cursor + 1, data_start_row=cursor + 2,
                     data_end_row=cursor + 1 + len(group["rows"]))
        cursor = group["data_end_row"] + 2
    views["工具调用对比"].update(layout="grouped_tools", groups=tool_groups,
                                 render_row_count=min(cursor + len(views["工具调用对比"]["notes"]), 160))
    order = ["总览", "效率对比", "分类对比", "难度对比", "Agent能力对比", "模态对比", "工具调用对比"]
    return {"schema_version": "wildclawbench.general-report-views/v1", "tables": {key: views[key] for key in order},
            **report_case_views.build_case_views(data, units, labels_by_id, table, CATEGORIES, MODALITIES),
            "sheet_order": order,
            "unit_labels": labels_by_id, "dimension_coverage": dimension_coverage, "unit_metadata": metadata,
            "reference_sources": references["sources"],
            "capability_coverage": caps, "resource_display": resource_display_by_unit,
            "display_overrides": applied_overrides,
            "display_overrides_sha256": hashlib.sha256(json.dumps(overrides, ensure_ascii=False, sort_keys=True).encode()).hexdigest() if overrides else None}
