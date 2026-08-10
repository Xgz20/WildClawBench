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
    dimensions = {}
    model_title = f"固定 {target_harness_display}：模型对比"
    harness_title = f"固定 {target_model_display}：Harness 对比"
    for sheet_name in DIMENSION_SHEETS:
        ws = workbook[sheet_name]
        dimensions[sheet_name] = {
            "model_view_title": model_title,
            "model_view": _extract_controlled_view(ws, model_title),
            "harness_view_title": harness_title,
            "harness_view": _extract_controlled_view(ws, harness_title),
        }

    pricing = [
        row for row in metadata
        if row.get("类型") in {"成本", "汇率", "配置"}
    ]
    workbook.close()
    return {
        "schema_version": 1,
        "source_excel": str(excel_path),
        "target": target,
        "pricing_snapshot": pricing,
        "overview": overview,
        "dimensions": dimensions,
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
