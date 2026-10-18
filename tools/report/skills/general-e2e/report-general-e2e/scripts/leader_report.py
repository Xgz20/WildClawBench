"""Target-focused leadership preview, extracted from the exported workbook.

Adapted to General E2E's sparse model/Harness combinations. Do not invent
controlled comparisons when the target model or Harness has no peer.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

DIMENSIONS = ["分类对比", "Agent能力对比", "难度对比", "模态对比"]


def add_arguments(parser):
    parser.add_argument("--leader-comparison-scope", choices=["same-harness-version", "all-combinations"],
                        help="领导版主要比较范围；默认优先同Harness、同客户端版本，表格始终保留全部单元")
    parser.add_argument("--leader-secondary-table", action="append", choices=["none", "总览", *DIMENSIONS],
                        help="可重复：允许补充总体最高分外部参照的章节；默认仅总览，none关闭补充")


def configure(data, args):
    target = getattr(args, "target_unit", None)
    scope = getattr(args, "leader_comparison_scope", None)
    secondary = getattr(args, "leader_secondary_table", None)
    if not target:
        if scope is not None or secondary is not None:
            raise ValueError("LEADER_OPTIONS_REQUIRE_TARGET")
        return
    config = deepcopy(data.get("leader_config", {}))
    config["target_unit_id"] = target
    if scope is not None:
        config["comparison_scope"] = scope
    if secondary is not None:
        if "none" in secondary and secondary != ["none"]:
            raise ValueError("LEADER_SECONDARY_CONFIG_INVALID")
        config["secondary_tables"] = [] if secondary == ["none"] else list(dict.fromkeys(secondary))
    data["leader_config"] = config


def comparison_context(data, target_unit_id):
    units = {u["unit_id"]: u for u in data["units"]}
    if len(units) != len(data["units"]):
        raise ValueError("LEADER_DUPLICATE_UNIT")
    config = data.get("leader_config", {})
    scope = config.get("comparison_scope", "same-harness-version")
    secondary = config.get("secondary_tables", ["总览"])
    if scope not in ["same-harness-version", "all-combinations"]:
        raise ValueError("LEADER_COMPARISON_SCOPE_INVALID")
    if (not isinstance(secondary, list) or any(s not in ["总览", *DIMENSIONS] for s in secondary)
            or len(secondary) != len(set(secondary))):
        raise ValueError("LEADER_SECONDARY_CONFIG_INVALID")
    target = units[target_unit_id]
    harness = target["harness"]
    peers = [u for u in units if u != target_unit_id]
    matching = [u for u in peers if harness.get("version") and
                units[u]["harness"].get("id") == harness.get("id") and
                units[u]["harness"].get("version") == harness["version"]]
    use_matching = scope == "same-harness-version" and bool(matching)
    primary = matching if use_matching else peers
    labels = data["presentation"]["unit_labels"]
    return {"requested_scope": scope, "primary_scope": "same-harness-version" if use_matching else "all-combinations",
            "fallback_reason": "no-same-version-peer" if scope == "same-harness-version" and not matching else None,
            "fixed_harness": harness.get("id") if use_matching else None,
            "fixed_version": harness.get("version") if use_matching else None,
            "fixed_client_label": labels[target_unit_id].rsplit("@", 1)[-1] if use_matching else None,
            "primary_unit_ids": primary, "primary_labels": [labels[u] for u in primary],
            "secondary_tables": secondary, "all_units_retained_in_tables": True}


def narrative_peer_labels(data):
    return data.get("comparison_context", {}).get("primary_labels")


def workbook_cells(path):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        strings = ["".join(x.itertext()) for x in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("s:si", ns)] if "xl/sharedStrings.xml" in z.namelist() else []
        rels = {x.attrib["Id"]: x.attrib["Target"] for x in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        result = {}
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).find("s:sheets", ns):
            target = rels[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            tree = ET.fromstring(z.read(target.lstrip("/") if target.startswith("/") else "xl/" + target))
            cells = {}
            for cell in tree.findall(".//s:sheetData/s:row/s:c", ns):
                v = cell.find("s:v", ns)
                value = v.text if v is not None else None
                if cell.attrib.get("t") == "s": value = strings[int(value)]
                elif cell.attrib.get("t") == "inlineStr": value = "".join(cell.find("s:is", ns).itertext())
                elif value is not None and cell.attrib.get("t") in [None, "n", "b"]: value = float(value)
                cells[cell.attrib["r"]] = value
            result[sheet.attrib["name"]] = cells
        return result


def column(i):
    out = ""
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def num(value, digits=2, percent=False, grouping=False):
    if value is None: return "-"
    d = Decimal(str(value)) * (100 if percent else 1)
    d = d.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return format(d, ("," if grouping else "") + f".{digits}f") + ("%" if percent else "")


def average_token_comparisons(data, peer_labels=None):
    """Compare unrounded workbook values while retaining each coverage bound."""
    label = data["target"]["label"]
    view = data["tables"]["效率对比"]
    annotations = view.get("cell_annotations", {})
    index = next(i for i, row in enumerate(view["rows"]) if row[0] == label)
    value = view["rows"][index][2]
    numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    coverage = annotations.get(f"{index}:2", {})
    result = {"target_label": label, "target_average_tokens": value if numeric(value) and value >= 0 else None,
              "target_coverage": coverage, "comparisons": [], "unavailable_peers": [], "zero_peers": []}
    for i, row in enumerate(view["rows"]):
        if i == index:
            continue
        if peer_labels is not None and row[0] not in peer_labels:
            continue
        peer_value = row[2]
        if not numeric(peer_value) or peer_value < 0:
            result["unavailable_peers"].append(row[0])
            continue
        if peer_value == 0:
            result["zero_peers"].append(row[0])
            continue
        if result["target_average_tokens"] is None:
            continue
        peer_coverage = annotations.get(f"{i}:2", {})
        statuses = (coverage.get("status"), peer_coverage.get("status"))
        basis = {("complete", "complete"): "complete",
                 ("partial", "complete"): "lower_bound",
                 ("complete", "partial"): "upper_bound"}.get(statuses, "observed_values_only")
        ratio = Decimal(str(value)) / Decimal(str(peer_value))
        result["comparisons"].append({"peer_label": row[0], "peer_average_tokens": peer_value,
                                      "peer_coverage": peer_coverage, "ratio": float(ratio),
                                      "display_ratio": num(ratio), "basis": basis})
    return result


def render_efficiency_summary(data, comparison):
    label = comparison["target_label"]
    value = comparison["target_average_tokens"]
    if value is None:
        return f"{label} 的 Token 消耗不可用，不能据此作消耗排名。"
    text = f"{label} 每个冻结用例平均 Token 为 {num(value, grouping=True)}"
    peers = comparison["comparisons"]
    if peers:
        text += "，按当前可核验用量约为" + "、".join(
            f"{peer['peer_label']} 的 {peer['display_ratio']} 倍" for peer in peers) + "。"
    else:
        text += "。本批次没有可用于倍数比较的参照 Token 值。"
    coverage = comparison["target_coverage"]
    if coverage.get("status") == "complete":
        text += f"目标组覆盖全部 {coverage.get('total_cases', data['scope']['unique_task_count'])} 题。"
    elif coverage.get("status") == "partial":
        if coverage.get("complete_cases") is not None and coverage.get("partial_cases") is not None:
            text += f"目标组 {coverage['complete_cases']} 题完整、{coverage['partial_cases']} 题部分统计；"
        else:
            text += "目标组覆盖不全；"
        text += "该均值及相对完整参照的倍数是当前可核验消耗下限。"
    else:
        text += "目标组统计覆盖尚未确认，倍数只比较当前观测值。"
    incomplete_peers = [p["peer_label"] for p in peers if p["peer_coverage"].get("status") != "complete"]
    if incomplete_peers:
        text += "、".join(incomplete_peers) + " 的覆盖不完整或未确认，相应倍数不代表全量精确消耗比。"
    if comparison["unavailable_peers"]:
        text += "、".join(comparison["unavailable_peers"]) + " 缺少可用 Token 统计，暂不参与这项比较。"
    if comparison["zero_peers"]:
        text += "、".join(comparison["zero_peers"]) + " 的平均 Token 为 0，倍数不适用。"
    return text


def render_task_timing_summary(data, peer_labels=None):
    label = data["target"]["label"]
    timing = data["tables"]["效率对比"].get("timing_table")
    if not timing:
        return None
    index = next(i for i, row in enumerate(timing["rows"]) if row[0] == label)
    row = timing["rows"][index]
    indices = {h: i for i, h in enumerate(timing["headers"])}
    avg = indices["平均任务耗时(s)"]
    p50 = indices["任务耗时P50(s)"]
    p90 = indices["任务耗时P90(s)"]
    if row[avg] is None:
        return f"{label} 的原生任务耗时不可用，不用流程耗时替代。"
    text = f"{label} 每个冻结用例平均任务耗时为 {num(row[avg], 3, grouping=True)} 秒"
    if row[p50] is not None and row[p90] is not None:
        text += f"，P50 为 {num(row[p50], 3, grouping=True)} 秒，P90 为 {num(row[p90], 3, grouping=True)} 秒"
    text += "。"
    peers = [f"{peer[0]} 的 {num(Decimal(str(row[avg])) / Decimal(str(peer[avg])))} 倍"
             for peer in timing["rows"] if peer[0] != label and (peer_labels is None or peer[0] in peer_labels)
             and isinstance(peer[avg], (int, float)) and peer[avg] > 0]
    if peers:
        text += "按可核验用量，平均任务耗时约为" + "、".join(peers) + "。"
    if timing.get("cell_annotations", {}).get(f"{index}:{avg}", {}).get("status") == "partial":
        text += "目标组计时覆盖不足，平均值是已知用量下限；分位数未补算。"
    if any(timing.get("cell_annotations", {}).get(f"{i}:{avg}", {}).get("status") == "partial"
           for i, peer in enumerate(timing["rows"]) if peer[0] != label and (peer_labels is None or peer[0] in peer_labels)):
        text += "部分参照计时不完整，相关倍数只比较已知用量。"
    text += "任务耗时包含已确认失败任务的原生耗时，流程等待另计。"
    model = indices.get("总模型耗时(s)")
    if model is not None:
        if row[model] is not None:
            model_avg = row[indices["平均模型耗时(s)"]]
            share = row[indices["总模型耗时占比"]]
            text += f"目标单元每题累计模型耗时平均 {num(model_avg, 3, grouping=True)} 秒"
            if share is not None: text += f"，占总任务耗时的 {num(share, percent=True)}"
            text += "，采用 maas_cube.perf 累计口径。"
        else:
            coverage = timing["coverage_table"]
            coverage_row = next(r for r in coverage["rows"] if r[0] == label)
            known = coverage_row[coverage["headers"].index("模型耗时完整用例")]
            text += f"目标单元模型耗时完整覆盖 {known} 题，全量统计暂以“-”展示；口径为 maas_cube.perf。"
    return text


def tool_call_comparisons(data, peer_labels=None):
    """Compare per-frozen-case call counts, retaining partial-count bounds."""
    label = data["target"]["label"]
    groups = data["tables"]["工具调用对比"].get("groups", [])
    cases = {row[0]: row[2] for row in data["tables"].get("总览", {}).get("rows", [])}
    count = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 and float(v).is_integer()
    def observation(group):
        coverage = group.get("cell_annotations", {}).get("0:2", {})
        total = group["rows"][0][2] if group.get("rows") else None
        n = cases.get(group["title"], coverage.get("total_cases"))
        valid = count(total)
        return {"label": group["title"], "total_calls": total if valid else None,
                "frozen_task_count": n if count(n) else None, "coverage": coverage,
                "average_calls": float(Decimal(str(total)) / Decimal(str(n))) if valid and count(n) and n > 0 else None}
    target_group = next((group for group in groups if group["title"] == label), None)
    target = observation(target_group) if target_group else {"label": label, "total_calls": None, "frozen_task_count": None, "coverage": {}, "average_calls": None}
    result = {"target": target, "comparisons": [], "unavailable_peers": [], "zero_peers": [], "composition": None}
    for group in groups:
        if group["title"] == label:
            continue
        if peer_labels is not None and group["title"] not in peer_labels:
            continue
        peer = observation(group)
        if peer["average_calls"] is None:
            result["unavailable_peers"].append(peer["label"])
            continue
        if peer["average_calls"] == 0:
            result["zero_peers"].append(peer["label"])
            continue
        if target["average_calls"] is None:
            continue
        ratio = (Decimal(str(target["total_calls"])) * Decimal(str(peer["frozen_task_count"]))
                 / (Decimal(str(target["frozen_task_count"])) * Decimal(str(peer["total_calls"]))))
        basis = {("complete", "complete"): "complete", ("partial", "complete"): "lower_bound",
                 ("complete", "partial"): "upper_bound"}.get((target["coverage"].get("status"), peer["coverage"].get("status")), "observed_values_only")
        result["comparisons"].append({**peer, "ratio": float(ratio), "display_ratio": num(ratio), "basis": basis})
    details = [row for row in target_group.get("rows", [])[1:] if count(row[2]) and row[2] > 0] if target_group else []
    known = sum(row[2] for row in details)
    if known:
        top = sorted(details, key=lambda row: (-row[2], row[1]))[:3]
        complete = target["coverage"].get("status") == "complete" and known == target["total_calls"] and all(row[3] == "计数完整" for row in details)
        result["composition"] = {"tools": [{"name": row[1], "calls": row[2]} for row in top],
                                 "known_detail_calls": known, "share": sum(row[2] for row in top) / known,
                                 "basis": "complete_calls" if complete else "known_detail_calls"}
    return result


def render_tool_call_summary(comparison):
    target = comparison["target"]; label = target["label"]
    if target["total_calls"] is None:
        return f"{label} 的工具调用计数不可用，无法比较调用频度。"
    text = f"{label} 本轮共调用工具 {num(target['total_calls'], 0, grouping=True)} 次"
    if target["average_calls"] is not None:
        text += f"，平均每个冻结用例 {num(target['average_calls'])} 次"
        if comparison["comparisons"]:
            text += "，约为" + "、".join(f"{peer['label']} 的 {peer['display_ratio']} 倍" for peer in comparison["comparisons"])
    text += "。"
    coverage = target["coverage"]
    if coverage.get("status") == "complete":
        text += f"计数覆盖全部 {int(target['frozen_task_count'])} 题。" if target["frozen_task_count"] is not None else "工具总计数完整。"
    elif coverage.get("status") == "partial":
        text += "目标组计数覆盖不全，当前总量和每题均值是已知调用量下限；相对完整参照的倍数也为下限。"
    else:
        text += "目标组计数覆盖尚未确认，倍数只比较当前观测值。"
    incomplete = [peer["label"] for peer in comparison["comparisons"] if peer["coverage"].get("status") != "complete"]
    if incomplete:
        text += "、".join(incomplete) + " 的计数覆盖不完整或未确认，相关倍数不代表全量精确调用比。"
    if comparison["unavailable_peers"]:
        text += "、".join(comparison["unavailable_peers"]) + " 缺少可用的调用计数或冻结用例数，暂不参与这项比较。"
    if comparison["zero_peers"]:
        text += "、".join(comparison["zero_peers"]) + " 的平均调用数为 0，倍数不适用。"
    composition = comparison["composition"]
    if composition:
        names = "、".join(tool["name"] for tool in composition["tools"])
        basis = "全部工具调用" if composition["basis"] == "complete_calls" else "已知工具明细计数"
        text += f"调用主要集中在 {names}，合计占{basis}的 {num(composition['share'], percent=True)}。"
    return text


def extract(workbook, data, target_unit_id):
    units = {x["unit_id"]: x for x in data["units"]}
    if target_unit_id not in units: raise ValueError("LEADER_TARGET_UNIT_NOT_FOUND")
    labels = data["presentation"]["unit_labels"]
    label = labels[target_unit_id]
    tables = deepcopy(data["presentation"]["tables"])
    cells = workbook_cells(workbook)
    for name, view in tables.items():
        # Detail sheets are audited separately; leadership consumes seven views.
        if name not in ["总览", "效率对比", "工具调用对比", *DIMENSIONS]: continue
        header_row = view.get("header_row", 1)
        row_numbers = [i + header_row + 1 for i in range(len(view["rows"]))]
        if view.get("layout") == "grouped_tools":
            row_numbers = [g["data_start_row"] + i for g in view["groups"] for i in range(len(g["rows"]))]
        else:
            for i, h in enumerate(view["headers"]):
                assert str(cells[name][column(i + 1) + str(header_row)]).replace("\n", "") == h
            if view.get("title"):
                assert cells[name]["A" + str(header_row - 1)] == view["title"]
        rows = []
        for rn, expected in zip(row_numbers, view["rows"]):
            row = []
            for i, value in enumerate(expected):
                actual = cells[name].get(column(i + 1) + str(rn))
                if value is None:
                    assert actual in [None, "-", ""]
                    actual = None
                elif isinstance(value, (int, float)):
                    assert isinstance(actual, (int, float)) and abs(actual - value) < 1e-8
                else: assert actual == value
                row.append(actual)
            rows.append(row)
        view["rows"] = rows
        if view.get("timing_table"):
            timing = view["timing_table"]
            for i, heading in enumerate(timing["headers"]):
                assert str(cells[name][column(i + 1) + str(timing["header_row"])]).replace("\n", "") == heading
            extracted = []
            for rn, expected in enumerate(timing["rows"], timing["header_row"] + 1):
                actual_row = []
                for i, value in enumerate(expected):
                    actual = cells[name].get(column(i + 1) + str(rn))
                    if value is None:
                        assert actual in [None, "-", ""]
                        actual = None
                    elif isinstance(value, (int, float)):
                        assert isinstance(actual, (int, float)) and abs(actual - value) < 1e-8
                    else:
                        assert actual == value
                    actual_row.append(actual)
                extracted.append(actual_row)
            timing["rows"] = extracted
        for additional in view.get("additional_views", []):
            for table in [additional, additional.get("timing_table")]:
                if not table: continue
                header = table["header_row"]
                for i, heading in enumerate(table["headers"]):
                    assert str(cells[name][column(i + 1) + str(header)]).replace("\n", "") == heading
                extracted = []
                for rn, expected in enumerate(table["rows"], header + 1):
                    actual_row = []
                    for i, value in enumerate(expected):
                        actual = cells[name].get(column(i + 1) + str(rn))
                        if value is None:
                            assert actual in [None, "-", ""]
                            actual = None
                        elif isinstance(value, (int, float)):
                            assert isinstance(actual, (int, float)) and abs(actual - value) < 1e-8
                        else: assert actual == value
                        actual_row.append(actual)
                    extracted.append(actual_row)
                table["rows"] = extracted
    target = units[target_unit_id]
    # Use actual selected task identities; mixed/unknown model values do not
    # establish a controlled model comparison.
    actual_models = {x["model"].get("actual_id") for x in data["tasks"] if x["unit_id"] == target_unit_id}
    model = next(iter(actual_models)) if len(actual_models) == 1 else None
    harness = target["harness"]["id"]
    model_peers = [u for u in units if units[u]["harness"]["id"] == harness]
    harness_peers = [u for u in units if model is not None and {x["model"].get("actual_id") for x in data["tasks"] if x["unit_id"] == u} == {model}]
    result = {"schema_version": "wildclawbench.general-leader-data/v1", "report_mode": "preview",
              "source_excel": Path(workbook).name, "source_excel_sha256": hashlib.sha256(Path(workbook).read_bytes()).hexdigest(),
              "target": {"unit_id": target_unit_id, "label": label, "model": model, "harness": harness},
              "scope": {**data["scope"], "model_view_applicable": len(model_peers) > 1,
                        "harness_view_applicable": len(harness_peers) > 1,
                        "comparison_design": "selected-model-harness-combinations",
                        "comparison_gap_basis": "difference-of-unrounded-final-excel-values"},
              "tables": tables, "dimensions": {}, "narratives": {}}
    result["comparison_context"] = comparison_context(data, target_unit_id)
    for name in DIMENSIONS:
        view = tables[name]
        result["dimensions"][name] = {
            "target_view": [r for r in view["rows"] if r[0] == label],
            "combination_view": view["rows"],
            "model_view": [r for r in view["rows"] if r[0] in [labels[u] for u in model_peers]] if len(model_peers) > 1 else [],
            "harness_view": [r for r in view["rows"] if r[0] in [labels[u] for u in harness_peers]] if len(harness_peers) > 1 else [],
        }
    result["resource_comparisons"] = {"average_tokens": average_token_comparisons(result),
                                      "tool_calls": tool_call_comparisons(result)}
    result["narratives"] = summaries(result)
    result["efficiency_subsections"] = {
        "token_summary": result["narratives"]["效率对比"],
        "task_timing_summary": result["narratives"].get("任务耗时对比"),
    }
    return result


def summaries(data):
    label, tables = data["target"]["label"], data["tables"]
    target = lambda name: next(r for r in tables[name]["rows"] if r[0] == label)
    primary = narrative_peer_labels(data)
    peers = lambda name: [r for r in tables[name]["rows"] if r[0] != label and (primary is None or r[0] in primary)]
    numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    o = target("总览")
    context = data.get("comparison_context", {})
    prefix = (f"固定 {context['fixed_client_label']}，"
              if context.get("primary_scope") == "same-harness-version" else "")
    def compare(delta):
        if delta == 0:
            return "相同"
        return f"{'高' if delta > 0 else '低'} {num(abs(delta))} 分"
    overall = [f"相较{r[0]}{compare(Decimal(str(o[1]))-Decimal(str(r[1])))}" for r in peers("总览") if numeric(r[1]) and numeric(o[1])]
    out = {"总览": prefix + f"{label} 均分为 {num(o[1])}。" + ("；".join(overall)+"。" if overall else "没有可比较的参照均分。") +
           "执行完成情况与有效评分分母分别统计，真实能力零分保留。"}
    clean = lambda h: re.sub(r"平均分.*$", "", re.sub(r"^\d+_", "", h))
    def gaps(name, peer):
        row = target(name)
        values = []
        for i, heading in enumerate(tables[name]["headers"][2:], 2):
            if numeric(row[i]) and numeric(peer[i]):
                values.append((clean(heading), Decimal(str(row[i])) - Decimal(str(peer[i]))))
        return sorted(values, key=lambda x: x[1], reverse=True)
    for name in DIMENSIONS:
        descriptions = []
        for peer in peers(name):
            values = gaps(name, peer)
            if not values:
                continue
            chosen = [values[0]] if len(values) == 1 else [values[0], values[-1]]
            descriptions.append(f"相较{peer[0]}，" + "，".join(f"{heading}{compare(delta)}" for heading, delta in chosen))
        if not descriptions:
            out[name] = f"{label} 的有效维度得分与覆盖范围见表；本批次没有可比较的参照维度分数。"
            continue
        out[name] = prefix + f"{label}：" + "；".join(descriptions) + "。"
        if name == "分类对比": out[name] += "表中为模型与客户端的组合对照，不能单独归因于某一因素。"
        elif name == "Agent能力对比": out[name] += "七维得分来自检查点评分，工具次数不替代能力得分。"
        elif name == "难度对比": out[name] += "各分层的冻结用例数见表头，缺失评分不补零。"
        else: out[name] += "结果范围限于表中列出的输入模态。"
    out["效率对比"] = render_efficiency_summary(data, average_token_comparisons(data, primary))
    task_timing = render_task_timing_summary(data, primary)
    if task_timing:
        out["任务耗时对比"] = task_timing
    out["工具调用对比"] = render_tool_call_summary(tool_call_comparisons(data, primary))
    # Supplemental references never change the primary peer group or the tables.
    references = [r for r in tables["总览"]["rows"] if r[0] != label and numeric(r[1])]
    best = max(references, key=lambda r: r[1]) if references else None
    if best is not None and primary is not None and best[0] not in primary:
        for name in context.get("secondary_tables", []):
            if name == "总览" and numeric(o[1]):
                out[name] += f"补充跨配置参照：其余参照中总体均分最高的{best[0]}为{num(best[1])}，目标单元{compare(Decimal(str(o[1]))-Decimal(str(best[1])))}。"
            elif name in DIMENSIONS:
                peer = next((r for r in tables[name]["rows"] if r[0] == best[0]), None)
                values = gaps(name, peer) if peer else []
                if values:
                    heading, delta = max(values, key=lambda x: abs(x[1]))
                    out[name] += f"补充跨配置参照：与总体均分最高的{best[0]}相比，{heading}{compare(delta)}。"
    return out


def efficiency_sections(data):
    sections = data.get("efficiency_subsections")
    if sections:
        return sections["token_summary"], sections.get("task_timing_summary")
    token = data["narratives"]["效率对比"]
    timing = data["narratives"].get("任务耗时对比")
    if timing is None and "\n\n" in token and data["tables"]["效率对比"].get("timing_table"):
        token, timing = token.split("\n\n", 1)
    return token, timing


def md_table(headers, rows, formats=None, annotations=None):
    formats = formats or {}; annotations = annotations or {}
    def escape(x): return str(x).replace("|", "\\|").replace("\n", "<br>")
    out = ["| " + " | ".join(map(escape, headers)) + " |", "| " + " | ".join(["---"]*len(headers)) + " |"]
    for rn, row in enumerate(rows):
        values = []
        for i, v in enumerate(row):
            if isinstance(v, (int, float)):
                fmt = formats.get(str(i), "#,##0")
                digits = len(fmt.split(".")[1].replace("%", "")) if "." in fmt else 0
                v = num(v, digits, "%" in fmt, True)
            elif v is None: v = "-"
            if annotations.get(f"{rn}:{i}", {}).get("status") == "partial" and v != "-": v = str(v) + "\\*"
            values.append(escape(v))
        out.append("| " + " | ".join(values) + " |")
    return out


def render(data):
    label = data["target"]["label"]; scope=data["scope"]; tables=data["tables"]
    lines = [f"# {label} 通用场景端到端评测报告", "", "> 报告类型：通用场景维度分析", f"> 目标单元：{label}",
             f"> 参评范围：{scope['unit_count']} 个模型与 Harness 组合，每组 {scope['unique_task_count']} 道相同用例", "",
             "各章节保留全部参评组合，文字总结以目标单元为主体。模型与 Harness 同时变化的组合不能作为单因素因果对照。", "",
             "以下结论只基于得分、执行状态和可核验资源，不包含低分用例的模型侧／Harness 侧因果归因。", ""]
    titles={"总览":"一、总览","分类对比":"二、分类维度","Agent能力对比":"三、Agent能力","难度对比":"四、难度等级","模态对比":"五、模态对比","效率对比":"六、效率与资源","工具调用对比":"七、工具调用"}
    for name in ["总览",*DIMENSIONS,"效率对比","工具调用对比"]:
        v=tables[name]; lines += ["## "+titles[name], ""]
        if name == "效率对比":
            token_summary, timing_summary = efficiency_sections(data)
            lines += ["### Token对比", "", token_summary, ""]
        else:
            lines += [data["narratives"][name], ""]
        if name in DIMENSIONS:
            lines += md_table(v["headers"],data["dimensions"][name]["combination_view"],v["formats"])+[""]
        elif name=="工具调用对比":
            for g in v["groups"]:
                lines += ["### "+g["title"],"",*md_table(g["headers"],g["rows"],v["formats"]),""]
        else:
            lines += md_table(v["headers"],v["rows"],v["formats"],v.get("cell_annotations"))+[""]
        lines += v.get("notes",[])+[""]
        if v.get("coverage_table"):
            c=v["coverage_table"];lines += ["完整统计用例数 / 冻结用例数；部分统计单列：","",*md_table(c["headers"],c["rows"]),""]
        if v.get("timing_table"):
            t=v["timing_table"]
            lines += ["### 任务耗时对比", ""]
            if name == "效率对比" and timing_summary:
                lines += [timing_summary, ""]
            lines += [*md_table(t["headers"],t["rows"],t["formats"],t.get("cell_annotations")), "", *t["notes"], ""]
            c=t["coverage_table"]
            lines += ["任务耗时完整统计覆盖：", "", *md_table(c["headers"],c["rows"]), ""]
        for extra in v.get("additional_views", []):
            lines += ["### " + extra["title"], "", *md_table(extra["headers"],extra["rows"],extra["formats"],extra.get("cell_annotations")), "", *extra["notes"], ""]
            t = extra.get("timing_table")
            if t:
                target_row = next(r for r in t["rows"] if r[0] == label)
                idx = {h:i for i,h in enumerate(t["headers"])}
                if target_row[idx["总模型耗时(s)"]] is not None:
                    lines += [f"在共同任务范围内，{label} 每题平均模型耗时为 {num(target_row[idx['平均模型耗时(s)']],3,grouping=True)} 秒，占总任务耗时的 {num(target_row[idx['总模型耗时占比']],percent=True)}。", ""]
                lines += ["### " + t.get("title", "任务耗时对比"), "", *md_table(t["headers"],t["rows"],t["formats"],t.get("cell_annotations")), "", *t["notes"], ""]
                c = t["coverage_table"]
                lines += ["任务与模型耗时覆盖：", "", *md_table(c["headers"],c["rows"]), ""]
    lines += ["## 总结","",
              f"本轮以 {label} 为目标单元，与参照组合在分类、七维能力和难度分层上的差异已在各章节列明。失败任务的真实产物得分计入均值，完成率单独呈现，不以剔除失败的方式抬高效果指标。",
              "资源缺口保留覆盖说明；组合对照应结合模型与 Harness 的实际配置解释。所有表格数值均从本版 Excel 提取并与同源 JSON 逐项核对。","",
              "数据追溯：同目录 `general_e2e_leader_data.json`、`general_e2e_report_data.json` 与审计报告。",""]
    return "\n".join(lines)
