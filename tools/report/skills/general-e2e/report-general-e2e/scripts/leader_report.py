"""Target-focused leadership preview, extracted from the exported workbook.

Adapted to General E2E's sparse model/Harness combinations. Do not invent
controlled comparisons when the target model or Harness has no peer.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

DIMENSIONS = ["分类对比", "Agent能力对比", "难度对比", "模态对比"]


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
        row_numbers = [i + 2 for i in range(len(view["rows"]))]
        if view.get("layout") == "grouped_tools":
            row_numbers = [g["data_start_row"] + i for g in view["groups"] for i in range(len(g["rows"]))]
        else:
            for i, h in enumerate(view["headers"]):
                assert str(cells[name][column(i + 1) + "1"]).replace("\n", "") == h
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
                        "comparison_gap_basis": "difference-of-displayed-two-decimal-scores"},
              "tables": tables, "dimensions": {}, "narratives": {}}
    for name in DIMENSIONS:
        view = tables[name]
        result["dimensions"][name] = {
            "target_view": [r for r in view["rows"] if r[0] == label],
            "combination_view": view["rows"],
            "model_view": [r for r in view["rows"] if r[0] in [labels[u] for u in model_peers]] if len(model_peers) > 1 else [],
            "harness_view": [r for r in view["rows"] if r[0] in [labels[u] for u in harness_peers]] if len(harness_peers) > 1 else [],
        }
    result["narratives"] = summaries(result)
    return result


def summaries(data):
    label, tables = data["target"]["label"], data["tables"]
    target = lambda name: next(r for r in tables[name]["rows"] if r[0] == label)
    peers = lambda name: [r for r in tables[name]["rows"] if r[0] != label]
    numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    o = target("总览")
    other = [r[1] for r in peers("总览") if numeric(r[1])]
    ref = (f"参照组合均分范围为 {num(min(other))}–{num(max(other))}。" if other
           else "本批次没有可比较的参照均分。")
    out = {"总览": f"{label} 本轮均分为 {num(o[1])}。" + ref + "执行完成情况与能力得分分别统计，已确认的执行失败按真实产物评分。"}
    clean = lambda h: re.sub(r"平均分.*$", "", re.sub(r"^\d+_", "", h))
    def gaps(name):
        row = target(name)
        values = []
        for i, heading in enumerate(tables[name]["headers"][2:], 2):
            other_values = [r[i] for r in peers(name) if numeric(r[i])]
            if numeric(row[i]) and other_values:
                values.append((clean(heading), Decimal(num(row[i])) - Decimal(num(max(other_values)))))
        return sorted(values, key=lambda x: x[1], reverse=True)
    for name in DIMENSIONS:
        values = gaps(name)
        if not values:
            out[name] = f"{label} 的有效维度得分与覆盖范围见表；本批次没有可比较的参照维度分数。"
            continue
        def compare(item):
            heading, delta = item
            if delta == 0: return f"{heading}与参照最高值相同"
            return f"{heading}{'高于' if delta > 0 else '低于'}参照最高值 {num(abs(delta))} 分"
        chosen = [values[0]] if len(values) == 1 else [values[0], values[-1]]
        out[name] = f"{label} 在" + "，在".join(compare(item) for item in chosen) + "。"
        if name == "分类对比": out[name] += "表中为模型与客户端的组合对照，不能单独归因于某一因素。"
        elif name == "Agent能力对比": out[name] += "七维得分来自检查点评分，工具次数不替代能力得分。"
        elif name == "难度对比": out[name] += "各分层的冻结用例数见表头，缺失评分不补零。"
        else: out[name] += "结果范围限于表中列出的输入模态。"
    e = target("效率对比")
    refs = [f"{r[0]} 为 {num(r[2], grouping=True)}" for r in peers("效率对比") if numeric(r[2])]
    index = next(i for i, r in enumerate(tables["效率对比"]["rows"]) if r[0] == label)
    coverage = tables["效率对比"].get("cell_annotations", {}).get(f"{index}:2", {})
    if numeric(e[2]):
        out["效率对比"] = f"{label} 每个冻结用例平均 Token 为 {num(e[2], grouping=True)}。"
        if refs: out["效率对比"] += "参照组合：" + "，".join(refs) + "。"
        if coverage.get("status") == "complete":
            out["效率对比"] += f"目标组覆盖全部 {coverage.get('total_cases', o[2])} 题。"
        else: out["效率对比"] += "目标组覆盖不全，该值为可核验消耗下限。"
    else: out["效率对比"] = f"{label} 的 Token 消耗不可用，不能据此作消耗排名。"
    out["效率对比"] += "未暴露字段保持不可用；部分统计范围另列。"
    groups = tables["工具调用对比"].get("groups", [])
    group = next((g for g in groups if g["title"] == label), None)
    total = group["rows"][0][2] if group and group.get("rows") else None
    out["工具调用对比"] = f"{label} 工具调用为 {num(total, 0)} 次。" if numeric(total) else f"{label} 的工具总调用数不可用。"
    if group:
        coverage = group.get("cell_annotations", {}).get("0:2", {})
        if coverage.get("status") == "complete": out["工具调用对比"] += f"计数覆盖全部 {coverage.get('total_cases', o[2])} 题。"
        elif numeric(total): out["工具调用对比"] += "当前仅有部分计数。"
    refs = [f"{g['title']} 为 {num(g['rows'][0][2], 0)} 次" for g in groups
            if g["title"] != label and g.get("rows") and numeric(g["rows"][0][2])]
    if refs: out["工具调用对比"] += "参照组合：" + "，".join(refs) + "。"
    out["工具调用对比"] += "计数覆盖、参数及结果内容完整度、工具成功率和能力得分分别解释。"
    return out


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
        v=tables[name]; lines += ["## "+titles[name], "",data["narratives"][name], ""]
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
    lines += ["## 总结","",
              f"本轮以 {label} 为目标单元，与参照组合在分类、七维能力和难度分层上的差异已在各章节列明。失败任务的真实产物得分计入均值，完成率单独呈现，不以剔除失败的方式抬高效果指标。",
              "资源缺口保留覆盖说明；组合对照应结合模型与 Harness 的实际配置解释。所有表格数值均从本版 Excel 提取并与同源 JSON 逐项核对。","",
              "数据追溯：同目录 `general_e2e_leader_data.json`、`general_e2e_report_data.json` 与审计报告。",""]
    return "\n".join(lines)
