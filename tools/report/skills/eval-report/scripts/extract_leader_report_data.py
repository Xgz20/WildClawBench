#!/usr/bin/env python3
"""从评测 Excel 提取领导版报告所需的稳定 JSON 数据。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpyxl import load_workbook


DIMENSION_SHEETS = (
    "分类对比",
    "Agent能力对比",
    "Agent能力对比·去污染",
    "难度对比",
    "模态对比",
)


def _row_dicts(ws, header_row: int, start_row: int):
    headers = [cell.value for cell in ws[header_row]]
    for row_number in range(start_row, ws.max_row + 1):
        values = [ws.cell(row_number, column).value
                  for column in range(1, len(headers) + 1)]
        if values[0] in (None, ""):
            break
        yield {header: value for header, value in zip(headers, values) if header is not None}


def _metadata_rows(wb) -> list[dict]:
    if "_报告元数据" not in wb.sheetnames:
        raise ValueError("Excel 缺少 _报告元数据 Sheet")
    ws = wb["_报告元数据"]
    return list(_row_dicts(ws, 1, 2))


def _find_title_row(ws, title: str) -> int | None:
    """找到控制变量视图标题所在行，找不到时返回 None（单 Harness/单模型场景）。"""
    for row in range(1, ws.max_row + 1):
        if ws.cell(row, 1).value == title:
            return row
    return None


def _extract_controlled_view(ws, title: str) -> list[dict]:
    """提取控制变量视图，找不到时返回空列表。"""
    title_row = _find_title_row(ws, title)
    if title_row is None:
        return []
    return list(_row_dicts(ws, title_row + 1, title_row + 2))


def _extract_website_metrics(workbook) -> dict[str, dict[str, dict]]:
    if "站点评测指标" not in workbook.sheetnames:
        return {}
    ws = workbook["站点评测指标"]

    if "_站点评测指标口径" in workbook.sheetnames:
        glossary = workbook["_站点评测指标口径"]
        glossary_rows = {
            (str(row["模型@Harness"]), str(row["指标名称"])): row
            for row in _row_dicts(glossary, 1, 2)
            if row.get("模型@Harness") not in (None, "")
            and row.get("指标名称") not in (None, "")
        }
        metric_names = []
        column = 2
        while ws.cell(4, column).value not in (None, ""):
            metric_names.append(ws.cell(4, column).value)
            column += 1
        if all(metric_names):
            metrics: dict[str, dict[str, dict]] = {}
            for row_number in range(5, ws.max_row + 1):
                unit = ws.cell(row_number, 1).value
                if unit in (None, ""):
                    break
                unit_metrics = metrics.setdefault(str(unit), {})
                for column, name in enumerate(metric_names, start=2):
                    glossary_row = glossary_rows.get((str(unit), str(name)), {})
                    unit_metrics[str(name)] = {
                        "category": glossary_row.get("指标分类"),
                        "value": ws.cell(row_number, column).value,
                        "sample": glossary_row.get("样本数"),
                        "method": glossary_row.get("计算方法"),
                    }
            return metrics

    # 兼容改造前的纵向六列表报告。
    title_row = _find_title_row(ws, "结果与效率指标汇总")
    if title_row is None:
        return {}
    rows = _row_dicts(ws, title_row + 1, title_row + 2)
    metrics: dict[str, dict[str, dict]] = {}
    for row in rows:
        unit = row.get("模型@Harness")
        name = row.get("指标名称")
        if unit in (None, "") or name in (None, ""):
            continue
        metrics.setdefault(str(unit), {})[str(name)] = {
            "category": row.get("指标分类"),
            "value": row.get("数值"),
            "sample": row.get("样本数"),
            "method": row.get("计算方法"),
        }
    return metrics


def extract_workbook(excel_path: Path) -> dict:
    workbook = load_workbook(excel_path, data_only=True)
    metadata = _metadata_rows(workbook)
    target_rows = [row for row in metadata if row.get("类型") == "目标"]
    if not target_rows:
        raise ValueError("_报告元数据 缺少目标模型/Harness")
    target = {
        "unit_id": target_rows[0]["原始ID"],
        "unit_display": target_rows[0]["展示名称"],
        "model_id": next(
            row["值"] for row in target_rows if row.get("属性") == "model_id"
        ),
        "harness_id": next(
            row["值"] for row in target_rows if row.get("属性") == "harness_id"
        ),
    }
    target_model_display, target_harness_display = target["unit_display"].split("@", 1)
    target["model_display"] = target_model_display
    target["harness_display"] = target_harness_display

    overview = list(_row_dicts(workbook["总览"], 1, 2))
    # 参评模型/Harness 只有一个时，对应的控制变量对比不成立（无参照对象），
    # Excel 侧不会生成该视图。这里显式记录，供报告撰写端判断是否整节省略。
    models_in_scope = sorted({
        str(row.get("模型")) for row in overview if row.get("模型") not in (None, "")
    })
    harnesses_in_scope = sorted({
        # 总览的 Harness 列形如 "AstronCode (0.0.13)"，取版本号前的名称
        str(row.get("Harness")).split("(")[0].strip()
        for row in overview if row.get("Harness") not in (None, "")
    })
    scope = {
        "model_count": len(models_in_scope),
        "harness_count": len(harnesses_in_scope),
        "models": models_in_scope,
        "harnesses": harnesses_in_scope,
        # 单模型时"固定模型比 Harness"无参照；单 Harness 时"固定 Harness 比模型"无参照
        "model_view_applicable": len(models_in_scope) >= 2,
        "harness_view_applicable": len(harnesses_in_scope) >= 2,
    }

    dimensions = {}
    model_title = f"固定 {target_harness_display}：模型对比"
    harness_title = f"固定 {target_model_display}：Harness 对比"
    for sheet_name in DIMENSION_SHEETS:
        ws = workbook[sheet_name]
        model_view = _extract_controlled_view(ws, model_title)
        harness_view = _extract_controlled_view(ws, harness_title)
        dimensions[sheet_name] = {
            "model_view_title": model_title if model_view else None,
            "model_view": model_view,
            "model_view_applicable": bool(model_view),
            "harness_view_title": harness_title if harness_view else None,
            "harness_view": harness_view,
            "harness_view_applicable": bool(harness_view),
        }

    pricing = [
        row for row in metadata
        if row.get("类型") in {"成本", "汇率", "配置"}
    ]
    website_metrics = _extract_website_metrics(workbook)
    workbook.close()
    return {
        "schema_version": 1,
        "source_excel": str(excel_path),
        "target": target,
        "scope": scope,
        "pricing_snapshot": pricing,
        "overview": overview,
        "dimensions": dimensions,
        "website_metrics": website_metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="提取领导版评测报告数据")
    parser.add_argument("--excel", required=True, help="评测 Excel 路径")
    parser.add_argument("--output", required=True, help="输出 JSON 路径")
    args = parser.parse_args()

    excel_path = Path(args.excel).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not excel_path.is_file():
        parser.error(f"Excel 不存在：{excel_path}")
    payload = extract_workbook(excel_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"LEADER_DATA={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
