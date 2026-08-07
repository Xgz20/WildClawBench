#!/usr/bin/env python3
"""独立复算并审核 WildClawBench Excel 评测报告。"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import fmean
from datetime import date
from decimal import Decimal

try:
    from openpyxl import load_workbook
except ImportError:
    sys.exit("缺少 openpyxl，请先安装：pip install 'openpyxl>=3.1'")

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT))

from src.utils.tool_metrics import parse_tool_metrics  # noqa: E402
from src.utils.anomalies import classify_report_outcome, scan_run_dir  # noqa: E402
from src.utils.run_selection import select_effective_run_dirs  # noqa: E402

REPORT_SCRIPTS_DIR = REPO_ROOT / "tools/report/scripts"
sys.path.insert(0, str(REPORT_SCRIPTS_DIR))
import report_entities  # noqa: E402

SUITE_RE = re.compile(r"^\d{2}_")
DIMENSION_HEADER_RE = re.compile(r"^(.*?)平均分\((\d+)例\)$")
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
CORE_SHEETS = {"总览", "模型×Harness矩阵", "用例对比明细", "分类对比", "难度对比", "模态对比", "分差矩阵"}
OVERVIEW_FIELDS = {
    "总平均分": ("score_pct", 0.11),
    "用例数": ("task_count", 0),
    "正常完成数": ("finished", 0),
    "执行错误数": ("errors", 0),
    "超时数": ("timeouts", 0),
    "评测异常数": ("evaluation_anomalies", 0),
    "完成率": ("finish_rate", 0.11),
    "总tokens": ("total_tokens", 0),
    "总请求数": ("request_count", 0),
    "总耗时(s)": ("elapsed_time", 0.11),
    "总成本(USD)": ("cost_usd", 0.00011),
    "工具调用数": ("tool_calls", 0),
}
REQUIRED_OVERVIEW_FIELDS = tuple(column for column in OVERVIEW_FIELDS if column != "工具调用数")
CAP7_ORDER = ["code_generation", "tool_use", "data_processing", "retrieval_verification",
              "reasoning_planning", "content_generation", "verification_delivery"]
CAP7_ZH = {
    "code_generation": "代码生成", "tool_use": "工具调用", "data_processing": "数据处理",
    "retrieval_verification": "检索验证", "reasoning_planning": "推理规划",
    "content_generation": "内容生成", "verification_delivery": "验证交付",
}
CAP7_DECON = ["data_processing", "reasoning_planning", "content_generation"]
FILE_CKPT_RE = re.compile(r"exist|created|saved|written|parseable", re.I)
METRIC_CKPT_RE = re.compile(r"(_max$|_calls$|_attempts$|_triggered$|^penalty)")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def is_unit_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if any(path.glob("summary_all_*.json")):
        return True
    return any(child.is_dir() and SUITE_RE.match(child.name) for child in path.iterdir())


def discover_units(root: Path) -> list[tuple[str, str, Path]]:
    units: list[tuple[str, str, Path]] = []

    def walk(path: Path, depth: int) -> None:
        if is_unit_dir(path):
            units.append((path.parent.name, path.name, path))
            return
        if depth >= 3:
            return
        for child in sorted(path.iterdir()):
            if child.is_dir() and child.name not in {"report-workspace", "output"}:
                walk(child, depth + 1)

    walk(root, 0)
    dedup = {str(path.resolve()): (model, harness, path.resolve()) for model, harness, path in units}
    return sorted(dedup.values(), key=lambda item: (item[0], item[1]))


def round_root_from_units(result_root: Path, units: list[tuple[str, str, Path]]) -> Path:
    roots = set()
    for _, _, unit_dir in units:
        if unit_dir.parent.parent.name == unit_dir.name:
            roots.add(unit_dir.parents[2])
        else:
            roots.add(unit_dir.parents[1])
    return next(iter(roots)) if len(roots) == 1 else result_root


def transcript_path(run_dir: Path) -> Path | None:
    for name in ("chat_openclaw.jsonl", "chat.jsonl"):
        path = run_dir / name
        if path.is_file():
            return path
    return None


def parse_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    result = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip("\"'")
    return result


def load_task_meta(tasks_dir: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    # 与 generate_eval_report.load_all_task_meta 保持同一口径：extension/ 下的
    # 扩展任务（task_00N 系列）同样参与评测，须纳入元数据。
    for base in (tasks_dir, tasks_dir / "extension",
                 tasks_dir / "cn", tasks_dir / "extension" / "cn"):
        if not base.is_dir():
            continue
        is_ext = base != tasks_dir and "extension" in base.relative_to(tasks_dir).parts
        for suite in sorted(base.iterdir()):
            if not suite.is_dir() or not SUITE_RE.match(suite.name):
                continue
            for path in suite.glob("*.md"):
                meta = parse_frontmatter(path)
                meta["suite"] = suite.name
                if is_ext:
                    meta["meta_source"] = "extension"
                result.setdefault(path.stem, {}).update({key: value for key, value in meta.items() if value})

    # 扩展任务自带另一套中文 category（如 06_安全对齐），与主任务标签
    # （06_Safety_Alignment）不一致，会把同一套件拆成两个分类列。统一改用
    # 主任务（非 extension）为该套件确立的规范标签，扩展任务只贡献难度/模态
    # 等度量元数据，不参与分类命名。
    canonical: dict[str, str] = {}
    for meta in result.values():
        if meta.get("meta_source") == "extension":
            continue
        suite, category = meta.get("suite"), meta.get("category")
        if suite and category:
            canonical.setdefault(suite, category)
    for meta in result.values():
        if meta.get("meta_source") != "extension":
            continue
        label = canonical.get(meta.get("suite", ""))
        if label:
            meta["category"] = label
    return result


def finding(rule_id: str, severity: str, message: str, *, sheet: str = "",
            unit: str = "", task_id: str = "", evidence=None,
            recommendation: str = "") -> dict:
    return {
        "id": rule_id,
        "severity": severity,
        "sheet": sheet,
        "unit": unit,
        "task_id": task_id,
        "message": message,
        "evidence": evidence if evidence is not None else {},
        "recommendation": recommendation,
    }


def scan_raw_units(specs: list[tuple[str, str, Path]]) -> dict[str, dict]:
    units: dict[str, dict] = {}
    for model, harness, unit_dir in specs:
        tasks: dict[str, dict] = {}
        for suite_dir in sorted(unit_dir.iterdir()):
            if not suite_dir.is_dir() or not SUITE_RE.match(suite_dir.name):
                continue
            for task_dir in sorted(path for path in suite_dir.iterdir() if path.is_dir()):
                all_run_dirs = sorted(path for path in task_dir.iterdir() if path.is_dir())
                run_dirs = select_effective_run_dirs(all_run_dirs, scan_run_dir)
                scores = []
                for run_dir in run_dirs:
                    value = load_json(run_dir / "score.json").get("overall_score")
                    if isinstance(value, (int, float)) and math.isfinite(float(value)):
                        scores.append(float(value))
                latest = run_dirs[-1] if run_dirs else None
                status = load_json(latest / "execution_status.json") if latest else {}
                usage = load_json(latest / "usage.json") if latest else {}
                latest_score = load_json(latest / "score.json") if latest else {}
                grading_error = latest_score.get("error") or ("" if latest_score else "score.json 缺失")
                anomaly_items = scan_run_dir(latest).get("items", []) if latest else []
                outcome = classify_report_outcome(status, grading_error, anomaly_items)
                transcript = transcript_path(latest) if latest else None
                metrics = parse_tool_metrics(transcript, harness)
                tasks[task_dir.name] = {
                    "suite": suite_dir.name,
                    "score": fmean(scores) if scores else None,
                    "checkpoints": {key: value for key, value in latest_score.items()
                                    if key != "overall_score" and isinstance(value, (int, float))},
                    "runs": len(scores),
                    "status": status.get("status") or "",
                    "timed_out": bool(status.get("timed_out")),
                    "error": status.get("error") or "",
                    "grading_error": grading_error,
                    "outcome": outcome,
                    "elapsed": status.get("elapsed_time"),
                    "usage": usage,
                    "tool_calls": metrics.get("total", 0),
                }
        unit = f"{model}@{harness}"
        score_pct = fmean([(task["score"] if task["score"] is not None else 0.0)
                           for task in tasks.values()]) * 100 if tasks else 0.0
        errors = sum(1 for task in tasks.values() if task["outcome"] == "execution_error")
        timeouts = sum(1 for task in tasks.values() if task["outcome"] == "timeout")
        evaluation_anomalies = sum(
            1 for task in tasks.values() if task["outcome"] == "evaluation_anomaly"
        )
        finished = sum(1 for task in tasks.values() if task["outcome"] == "finished")
        task_count = len(tasks)
        def usage_total(key: str) -> float:
            return sum((task["usage"].get(key, 0) or 0) for task in tasks.values())
        units[unit] = {
            "model": model,
            "harness": harness,
            "path": str(unit_dir),
            "tasks": tasks,
            "score_pct": score_pct,
            "task_count": task_count,
            "finished": finished,
            "errors": errors,
            "timeouts": timeouts,
            "evaluation_anomalies": evaluation_anomalies,
            "finish_rate": finished / task_count * 100 if task_count else 0.0,
            "total_tokens": usage_total("total_tokens"),
            "request_count": usage_total("request_count"),
            "elapsed_time": usage_total("elapsed_time"),
            "cost_usd": usage_total("cost_usd"),
            "tool_calls": sum(task["tool_calls"] for task in tasks.values()),
        }
    return units


def iter_row_dicts(ws):
    """流式读取只读 worksheet，避免 ws.cell() 每次从头解析 XML。"""
    rows = ws.iter_rows(values_only=True)
    headers = list(next(rows, ()))
    for row_number, values in enumerate(rows, 2):
        yield row_number, dict(zip(headers, values))


def as_number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(float(value)) else None


def mismatch(actual, expected, tolerance: float) -> bool:
    number = as_number(actual)
    return number is None or abs(number - float(expected)) > tolerance


def normalize_harness(label: str) -> str:
    value = str(label or "").strip()
    return value.split(" (", 1)[0].strip()


def load_identity_maps(wb) -> dict[str, dict[str, str]]:
    result = {
        "model_display_to_raw": {},
        "harness_display_to_raw": {},
        "unit_display_to_raw": {},
        "unit_raw_to_display": {},
    }
    if "_报告元数据" not in wb.sheetnames:
        return result
    ws = wb["_报告元数据"]
    for _, row in iter_row_dicts(ws):
        entity_type = row.get("类型")
        raw_id = str(row.get("原始ID") or "")
        display = str(row.get("展示名称") or "")
        if not raw_id or not display:
            continue
        if entity_type == "模型":
            result["model_display_to_raw"][display] = raw_id
        elif entity_type == "Harness":
            result["harness_display_to_raw"][display] = raw_id
        elif entity_type == "单元":
            result["unit_display_to_raw"][display] = raw_id
            result["unit_raw_to_display"][raw_id] = display
    return result


def resolve_model(label, identities: dict[str, dict[str, str]]) -> str:
    value = str(label or "").strip()
    return identities["model_display_to_raw"].get(value, value)


def resolve_harness(label, identities: dict[str, dict[str, str]]) -> str:
    value = normalize_harness(label)
    return identities["harness_display_to_raw"].get(value, value)


def resolve_unit(label, identities: dict[str, dict[str, str]]) -> str:
    value = str(label or "").strip()
    return identities["unit_display_to_raw"].get(value, value)


def original_table_rows(ws):
    for row in range(2, ws.max_row + 1):
        if ws.cell(row, 1).value in (None, ""):
            break
        yield row


def audit_overview(wb, units: dict[str, dict], findings: list[dict], identities,
                   recomputed_costs: dict[str, dict] | None = None) -> None:
    ws = wb["总览"]
    headers = [cell.value for cell in ws[1]]
    for required in ("模型", "Harness", *REQUIRED_OVERVIEW_FIELDS):
        if required not in headers:
            findings.append(finding("OVERVIEW_COLUMN_MISSING", "error", f"总览缺少列：{required}", sheet="总览"))
    reported = {}
    for row_number, row in iter_row_dicts(ws):
        if not row.get("模型"):
            continue
        unit = (
            f"{resolve_model(row['模型'], identities)}@"
            f"{resolve_harness(row.get('Harness'), identities)}"
        )
        reported[unit] = row
    if set(reported) != set(units):
        findings.append(finding("OVERVIEW_UNIT_SET_MISMATCH", "error", "总览 unit 集合与原始结果不一致",
                                sheet="总览", evidence={"excel": sorted(reported), "raw": sorted(units)}))
    for unit in sorted(set(reported) & set(units)):
        row, raw = reported[unit], units[unit]
        for column, (key, tolerance) in OVERVIEW_FIELDS.items():
            if column not in headers:
                continue
            if column == "总成本(USD)" and recomputed_costs is not None:
                continue
            if mismatch(row.get(column), raw[key], tolerance):
                findings.append(finding("OVERVIEW_VALUE_MISMATCH", "error",
                                        f"{column} 与原始结果独立复算不一致", sheet="总览", unit=unit,
                                        evidence={"excel": row.get(column), "recomputed": round(raw[key], 6)}))
        if recomputed_costs is not None:
            estimate = recomputed_costs.get(unit, {})
            expected_cost = estimate.get("usd")
            actual_cost = row.get("总成本(USD)")
            differs = (
                expected_cost is None and actual_cost not in (None, "-")
            ) or (
                expected_cost is not None and mismatch(actual_cost, expected_cost, 0.00011)
            )
            if differs:
                findings.append(finding(
                    "OVERVIEW_COST_MISMATCH",
                    "error",
                    "总成本与定价快照独立复算不一致",
                    sheet="总览",
                    unit=unit,
                    evidence={
                        "excel": actual_cost,
                        "recomputed": expected_cost,
                        "profile_ids": estimate.get("profile_ids", []),
                        "status": estimate.get("status", ""),
                        "reason": estimate.get("reason", ""),
                    },
                ))
        total = sum(as_number(row.get(key)) or 0 for key in
                    ("正常完成数", "执行错误数", "超时数", "评测异常数"))
        if as_number(row.get("用例数")) is not None and total != as_number(row.get("用例数")):
            findings.append(finding("STATUS_TOTAL_CONTRADICTION", "error",
                                    "正常完成数+执行错误数+超时数+评测异常数不等于用例数",
                                    sheet="总览", unit=unit,
                                    evidence={"status_total": total, "tasks": row.get("用例数")}))
        requests = raw["request_count"]
        tools = raw["tool_calls"]
        if tools > 0 and requests == 0:
            findings.append(finding("REQUESTS_ZERO_WITH_TOOLS", "error", "有工具调用但总请求数为 0",
                                    sheet="总览", unit=unit, evidence={"tool_calls": tools, "requests": requests}))
        elif requests > 0 and tools / requests > 5:
            findings.append(finding("TOOL_REQUEST_RATIO_HIGH", "warning",
                                    "工具调用数显著高于请求数，需确认请求数解析口径", sheet="总览", unit=unit,
                                    evidence={"tool_calls": tools, "requests": requests,
                                              "ratio": round(tools / requests, 2)}))


def audit_matrix(wb, units: dict[str, dict], findings: list[dict], identities) -> None:
    ws = wb["模型×Harness矩阵"]
    harnesses = [value for value in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))[1:] if value]
    seen = set()
    for values in ws.iter_rows(min_row=2, values_only=True):
        model = resolve_model(values[0], identities)
        if not model:
            continue
        for index, harness_display in enumerate(harnesses, start=1):
            harness = resolve_harness(harness_display, identities)
            unit = f"{model}@{harness}"
            value = values[index] if index < len(values) else None
            if unit not in units:
                if value not in (None, "-"):
                    findings.append(finding("MATRIX_UNKNOWN_UNIT", "error", "矩阵包含原始结果外的 unit",
                                            sheet=ws.title, unit=unit))
                continue
            seen.add(unit)
            if mismatch(value, units[unit]["score_pct"], 0.11):
                findings.append(finding("MATRIX_SCORE_MISMATCH", "error", "矩阵总分与原始结果不一致",
                                        sheet=ws.title, unit=unit,
                                        evidence={"excel": value, "recomputed": round(units[unit]["score_pct"], 6)}))
    missing = set(units) - seen
    if missing:
        findings.append(finding("MATRIX_UNIT_MISSING", "error", "矩阵缺少 unit", sheet=ws.title,
                                evidence={"units": sorted(missing)}))


def score_from_compare_cell(value) -> float | None:
    match = re.search(r"总分[：:]\s*(-|\d+(?:\.\d+)?)", str(value or ""))
    return float(match.group(1)) if match and match.group(1) != "-" else None


def audit_case_compare(wb, units: dict[str, dict], findings: list[dict], identities) -> None:
    ws = wb["用例对比明细"]
    headers = [cell.value for cell in ws[1]]
    required = {"用例ID", "最优单元", "最大分差"}
    for unit in units:
        required.add(f"{identities['unit_raw_to_display'].get(unit, unit)} 得分")
    missing = required - set(headers)
    for column in sorted(missing):
        findings.append(finding("CASE_COMPARE_COLUMN_MISSING", "error", f"用例对比缺少列：{column}",
                                sheet=ws.title))
    expected_tasks = set().union(*(set(data["tasks"]) for data in units.values())) if units else set()
    rows = {}
    for row_number, row in iter_row_dicts(ws):
        if row.get("用例ID"):
            rows[row["用例ID"]] = row
    if set(rows) != expected_tasks:
        findings.append(finding("CASE_COMPARE_TASK_SET_MISMATCH", "error", "用例对比任务集合不一致",
                                sheet=ws.title,
                                evidence={"excel_count": len(rows), "raw_count": len(expected_tasks),
                                          "missing": sorted(expected_tasks - set(rows))}))
    for task_id in set(rows) & expected_tasks:
        row = rows[task_id]
        valid_scores = {}
        for unit, data in units.items():
            task = data["tasks"].get(task_id)
            if task is None:
                continue
            expected = task["score"]
            column = f"{identities['unit_raw_to_display'].get(unit, unit)} 得分"
            if column not in headers:
                continue
            actual = score_from_compare_cell(row.get(column))
            if expected is None:
                differs = actual is not None
            else:
                differs = actual is None or abs(actual - expected) > 0.00051
                valid_scores[unit] = expected
            if differs:
                findings.append(finding("CASE_COMPARE_SCORE_MISMATCH", "error",
                                        "用例对比得分与原始结果不一致", sheet=ws.title,
                                        unit=unit, task_id=task_id,
                                        evidence={"excel": actual, "recomputed": expected}))
        if valid_scores:
            maximum = max(valid_scores.values())
            best_units = {unit for unit, score in valid_scores.items() if abs(score - maximum) <= 1e-12}
            reported_best = resolve_unit(row.get("最优单元"), identities)
            if reported_best not in best_units:
                findings.append(finding("CASE_COMPARE_BEST_MISMATCH", "error", "最优单元计算错误",
                                        sheet=ws.title, task_id=task_id,
                                        evidence={"excel": row.get("最优单元"),
                                                  "recomputed_candidates": sorted(best_units)}))
            expected_spread = max(valid_scores.values()) - min(valid_scores.values())
            if len(valid_scores) > 1 and mismatch(row.get("最大分差"), expected_spread, 0.00051):
                findings.append(finding("CASE_COMPARE_SPREAD_MISMATCH", "error", "最大分差计算错误",
                                        sheet=ws.title, task_id=task_id,
                                        evidence={"excel": row.get("最大分差"),
                                                  "recomputed": round(expected_spread, 6)}))


def load_capability_map(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (ImportError, OSError, ValueError):
        return {}
    return {task_id: {checkpoint: list(dimensions) for checkpoint, dimensions in (mapping or {}).items()}
            for task_id, mapping in data.items() if isinstance(mapping, dict)}


def normalize_checkpoint(key: str, value: float, checkpoints: dict) -> float | None:
    if METRIC_CKPT_RE.search(key):
        return None
    if key.endswith("_earned"):
        maximum = checkpoints.get(key[:-len("_earned")] + "_max")
        if isinstance(maximum, (int, float)) and maximum > 0:
            return min(1.0, max(0.0, value / maximum))
    return float(value) if 0 <= value <= 1 else None


def capability_score(data: dict, mapping: dict, dimension: str, delivered_only: bool) -> float | None:
    task_scores = []
    for task_id, task in data["tasks"].items():
        checkpoints = task["checkpoints"]
        if not checkpoints:
            continue
        if delivered_only:
            file_scores = [value for key, value in checkpoints.items() if FILE_CKPT_RE.search(key)]
            if file_scores and fmean(file_scores) < 0.5:
                continue
        candidates = {key: normalized for key, value in checkpoints.items()
                      if (normalized := normalize_checkpoint(key, value, checkpoints)) is not None}
        if task["score"] is not None and 0 <= task["score"] <= 1:
            candidates["overall_score"] = task["score"]
        values = [candidates[key] for key, dimensions in mapping.get(task_id, {}).items()
                  if dimension in dimensions and key in candidates]
        if values:
            task_scores.append(fmean(values))
    return fmean(task_scores) * 100 if task_scores else None


def audit_capabilities(wb, units: dict[str, dict], capability_map: dict,
                       findings: list[dict], identities) -> None:
    if not capability_map:
        findings.append(finding("CAPABILITY_MAP_MISSING", "warning", "能力映射缺失，无法独立审核能力指标"))
        return
    specs = {
        "Agent能力对比": [(dimension, CAP7_ZH[dimension], False) for dimension in CAP7_ORDER],
        "Agent能力对比·去污染": [(dimension, f"{CAP7_ZH[dimension]}·去落盘污染", True)
                                  for dimension in CAP7_DECON],
    }
    for title, dimensions in specs.items():
        if title not in wb.sheetnames:
            findings.append(finding("CAPABILITY_SHEET_MISSING", "error", f"缺少能力 Sheet：{title}", sheet=title))
            continue
        ws = wb[title]
        headers = [cell.value for cell in ws[1]]
        rows = {
            resolve_unit(ws.cell(row, 1).value, identities): row
            for row in original_table_rows(ws)
        }
        if set(rows) != set(units):
            findings.append(finding("CAPABILITY_UNIT_SET_MISMATCH", "error", "能力 Sheet 的 unit 集合不一致",
                                    sheet=title, evidence={"excel": sorted(rows), "raw": sorted(units)}))
        for dimension, column, delivered_only in dimensions:
            if column not in headers:
                findings.append(finding("CAPABILITY_COLUMN_MISSING", "error", f"缺少能力列：{column}", sheet=title))
                continue
            column_number = headers.index(column) + 1
            for unit in set(rows) & set(units):
                expected = capability_score(units[unit], capability_map, dimension, delivered_only)
                actual = ws.cell(rows[unit], column_number).value
                differs = ((expected is None and actual not in (None, "-")) or
                           (expected is not None and mismatch(actual, expected, 0.11)))
                if differs:
                    findings.append(finding("CAPABILITY_SCORE_MISMATCH", "error",
                                            "能力得分与检查点映射独立复算不一致", sheet=title, unit=unit,
                                            evidence={"dimension": column, "excel": actual,
                                                      "recomputed": round(expected, 6) if expected is not None else None}))


def build_groups(meta: dict[str, dict], units: dict[str, dict], field: str) -> dict[str, set[str]]:
    task_ids = set().union(*(set(unit["tasks"]) for unit in units.values())) if units else set()
    groups: dict[str, set[str]] = {}
    for task_id in task_ids:
        item = meta.get(task_id, {})
        value = item.get(field, "")
        if field == "category":
            value = item.get("category") or item.get("suite", "")
        if field == "modality":
            value = {"pure-text": "纯文本", "multimodal": "多模态"}.get(value, value)
        if value:
            groups.setdefault(value, set()).add(task_id)
    return groups


def audit_dimension_sheet(wb, title: str, units: dict[str, dict], groups: dict[str, set[str]],
                          findings: list[dict], identities) -> None:
    ws = wb[title]
    headers = [cell.value for cell in ws[1]]
    reported_groups = {}
    for column, header in enumerate(headers[2:], start=3):
        match = DIMENSION_HEADER_RE.match(str(header or ""))
        if not match:
            findings.append(finding("DIMENSION_HEADER_INVALID", "error", f"无法解析维度列头：{header}", sheet=title))
            continue
        label, count = match.group(1), int(match.group(2))
        reported_groups[label] = column
        expected_count = len(groups.get(label, set()))
        if count != expected_count:
            findings.append(finding("DIMENSION_SAMPLE_COUNT_MISMATCH", "error", "列头用例数与任务定义不一致",
                                    sheet=title, evidence={"dimension": label, "excel": count,
                                                           "recomputed": expected_count}))
    if set(reported_groups) != set(groups):
        findings.append(finding("DIMENSION_SET_MISMATCH", "error", "维度集合与任务定义不一致", sheet=title,
                                evidence={"excel": sorted(reported_groups), "raw": sorted(groups)}))
    rows = {
        resolve_unit(ws.cell(row, 1).value, identities): row
        for row in original_table_rows(ws)
    }
    if set(rows) != set(units):
        findings.append(finding("DIMENSION_UNIT_SET_MISMATCH", "error", "维度 Sheet 的 unit 集合不一致",
                                sheet=title, evidence={"excel": sorted(rows), "raw": sorted(units)}))
    for unit in sorted(set(rows) & set(units)):
        row = rows[unit]
        if mismatch(ws.cell(row, 2).value, units[unit]["score_pct"], 0.11):
            findings.append(finding("DIMENSION_TOTAL_MISMATCH", "error", "维度 Sheet 总平均分不一致",
                                    sheet=title, unit=unit))
        for label in set(reported_groups) & set(groups):
            scores = [units[unit]["tasks"][task_id]["score"]
                      for task_id in groups[label] if task_id in units[unit]["tasks"]]
            expected = fmean([score if score is not None else 0.0 for score in scores]) * 100 if scores else None
            actual = ws.cell(row, reported_groups[label]).value
            if expected is None or mismatch(actual, expected, 0.11):
                findings.append(finding("DIMENSION_SCORE_MISMATCH", "error", "维度得分与原始结果不一致",
                                        sheet=title, unit=unit,
                                        evidence={"dimension": label, "excel": actual,
                                                  "recomputed": round(expected, 6) if expected is not None else None}))


def audit_difficulty_inversion(units: dict[str, dict], groups: dict[str, set[str]],
                               findings: list[dict]) -> None:
    levels = [level for level in ("L1", "L2", "L3", "L4", "L5") if len(groups.get(level, set())) >= 3]
    minimum_units = max(3, math.ceil(len(units) * 0.6))
    for easy, hard in zip(levels, levels[1:]):
        affected = {}
        for unit, data in units.items():
            def average(task_ids: set[str]) -> float | None:
                scores = [data["tasks"][task_id]["score"] for task_id in task_ids if task_id in data["tasks"]]
                return fmean([score if score is not None else 0.0 for score in scores]) * 100 if scores else None
            easy_score, hard_score = average(groups[easy]), average(groups[hard])
            if easy_score is not None and hard_score is not None and hard_score - easy_score >= 10:
                affected[unit] = round(hard_score - easy_score, 1)
        if len(affected) >= minimum_units:
            findings.append(finding("DIFFICULTY_INVERSION", "warning",
                                    f"多数 unit 的更高难度 {hard} 得分反而显著高于 {easy}", sheet="难度对比",
                                    evidence={"easy": easy, "hard": hard,
                                              "easy_tasks": len(groups[easy]), "hard_tasks": len(groups[hard]),
                                              "affected_units": affected, "required_units": minimum_units},
                                    recommendation="复核难度标签、样本构成和评分标准；不能直接推断模型更擅长难题。"))


def audit_diff_matrix(wb, units: dict[str, dict], findings: list[dict], identities) -> None:
    ws = wb["分差矩阵"]
    columns = [
        resolve_unit(value, identities)
        for value in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))[1:]
        if value
    ]
    rows = {
        resolve_unit(ws.cell(row, 1).value, identities): row
        for row in range(2, ws.max_row + 1) if ws.cell(row, 1).value
    }
    if set(columns) != set(units) or set(rows) != set(units):
        findings.append(finding("DIFF_MATRIX_UNIT_SET_MISMATCH", "error", "分差矩阵行列 unit 集合不一致",
                                sheet=ws.title, evidence={"columns": columns, "rows": sorted(rows),
                                                          "raw": sorted(units)}))
        return
    for row_unit, row in rows.items():
        for offset, column_unit in enumerate(columns, start=2):
            expected = units[row_unit]["score_pct"] - units[column_unit]["score_pct"]
            if mismatch(ws.cell(row, offset).value, expected, 0.11):
                findings.append(finding("DIFF_MATRIX_VALUE_MISMATCH", "error", "分差矩阵数值不一致",
                                        sheet=ws.title, unit=row_unit,
                                        evidence={"column_unit": column_unit,
                                                  "excel": ws.cell(row, offset).value,
                                                  "recomputed": round(expected, 6)}))


def audit_detail_sheets(wb, units: dict[str, dict], findings: list[dict],
                        skip_root_cause_check: bool = False) -> None:
    """审核评分详情 Sheet，skip_root_cause_check=True 时不检查根因列内容（preview 模式）。"""
    for unit, data in units.items():
        title = f"评分详情_{unit}"[:31]
        if title not in wb.sheetnames:
            findings.append(finding("DETAIL_SHEET_MISSING", "error", "缺少 unit 评分详情 Sheet",
                                    sheet=title, unit=unit))
            continue
        ws = wb[title]
        headers = [cell.value for cell in ws[1]]
        for column in ("用例ID", "总得分", "状态", "总tokens", "请求数", "耗时(s)",
                       "结果分析", "根因分析", "工具调用数"):
            if column not in headers:
                findings.append(finding("DETAIL_COLUMN_MISSING", "error", f"详情缺少列：{column}",
                                        sheet=title, unit=unit))
        rows = {}
        for row_number, row in iter_row_dicts(ws):
            if row.get("用例ID"):
                rows[row["用例ID"]] = row
        if set(rows) != set(data["tasks"]):
            findings.append(finding("DETAIL_TASK_SET_MISMATCH", "error", "详情用例集合与原始结果不一致",
                                    sheet=title, unit=unit,
                                    evidence={"excel_count": len(rows), "raw_count": len(data["tasks"]),
                                              "missing": sorted(set(data["tasks"]) - set(rows))}))
        for task_id in set(rows) & set(data["tasks"]):
            row, raw = rows[task_id], data["tasks"][task_id]
            expected_score = raw["score"]
            if expected_score is None:
                if row.get("总得分") not in (None, "-"):
                    findings.append(finding("DETAIL_SCORE_MISMATCH", "error", "无有效原始分但详情含分数",
                                            sheet=title, unit=unit, task_id=task_id))
            elif mismatch(row.get("总得分"), expected_score, 0.00051):
                findings.append(finding("DETAIL_SCORE_MISMATCH", "error", "详情总得分与原始结果不一致",
                                        sheet=title, unit=unit, task_id=task_id,
                                        evidence={"excel": row.get("总得分"), "recomputed": expected_score}))
            expected_values = {
                "总tokens": raw["usage"].get("total_tokens", 0) or 0,
                "请求数": raw["usage"].get("request_count", 0) or 0,
                "工具调用数": raw["tool_calls"],
            }
            for column, expected in expected_values.items():
                if column in headers and mismatch(row.get(column), expected, 0):
                    findings.append(finding("DETAIL_USAGE_MISMATCH", "error", f"详情{column}与原始结果不一致",
                                            sheet=title, unit=unit, task_id=task_id,
                                            evidence={"excel": row.get(column), "recomputed": expected}))
            if "耗时(s)" in headers and isinstance(raw["elapsed"], (int, float)) \
                    and mismatch(row.get("耗时(s)"), raw["elapsed"], 0.11):
                findings.append(finding("DETAIL_ELAPSED_MISMATCH", "error", "详情耗时与 execution_status 不一致",
                                        sheet=title, unit=unit, task_id=task_id))


def load_validity(path: Path | None, findings: list[dict], skip: bool = False) -> dict | None:
    """加载有效性检查结果，skip=True 时跳过检查（preview 模式）。"""
    if skip:
        return None
    if path is None or not path.is_file():
        findings.append(finding("VALIDITY_RESULT_MISSING", "warning", "未提供前置评测结果有效性检查结论",
                                recommendation="先运行 validate-eval-results，再确认报告可发布。"))
        return None
    report = load_json(path)
    verdict = report.get("verdict")
    if verdict == "FAIL":
        findings.append(finding("UPSTREAM_VALIDITY_FAILED", "error", "前置评测结果有效性检查为 FAIL",
                                evidence={"path": str(path), "summary": report.get("summary", {})},
                                recommendation="先修复原始评测结果，不能通过报告层修饰问题。"))
    elif verdict == "REVIEW":
        findings.append(finding("UPSTREAM_VALIDITY_REVIEW", "warning", "前置有效性检查仍有待人工归因项",
                                evidence={"path": str(path), "summary": report.get("summary", {})}))
    elif verdict != "PASS":
        findings.append(finding("UPSTREAM_VALIDITY_INVALID", "warning", "无法识别前置有效性检查结论",
                                evidence={"path": str(path), "verdict": verdict}))
    return report


def recompute_unit_costs(specs, registry, pricing_date: date) -> dict[str, dict]:
    result = {}
    for model, harness, unit_dir in specs:
        total = Decimal(0)
        profile_ids = set()
        status = "estimated"
        reason = ""
        for suite_dir in sorted(unit_dir.iterdir()):
            if not suite_dir.is_dir() or not SUITE_RE.match(suite_dir.name):
                continue
            for task_dir in sorted(path for path in suite_dir.iterdir() if path.is_dir()):
                run_dirs = select_effective_run_dirs(
                    sorted(path for path in task_dir.iterdir() if path.is_dir()),
                    scan_run_dir,
                )
                if not run_dirs:
                    continue
                run_dir = run_dirs[-1]
                try:
                    usage = report_entities.normalize_billable_usage(
                        load_json(run_dir / "usage.json")
                    )
                    profile = registry.pricing_profile(model, pricing_date)
                    if len(profile.tiers) == 1:
                        estimate = report_entities.estimate_cost_usd(
                            registry, model, pricing_date, usage,
                            request_input_tokens=None,
                        )
                    else:
                        requests = (
                            report_entities.extract_astroncode_requests(run_dir)
                            if harness in ("astroncode", "codex")
                            else report_entities.extract_opencode_requests(run_dir)
                        )
                        estimate = report_entities.estimate_request_costs_usd(
                            registry, model, pricing_date, requests
                        )
                except (OSError, ValueError) as exc:
                    estimate = report_entities.CostEstimate(
                        None, None, "unavailable", str(exc)
                    )
                if estimate.profile_id:
                    profile_ids.add(estimate.profile_id)
                if estimate.usd is None:
                    status = "unavailable"
                    reason = estimate.reason
                    break
                total += estimate.usd
            if status == "unavailable":
                break
        unit = f"{model}@{harness}"
        result[unit] = {
            "usd": float(total) if status == "estimated" else None,
            "profile_ids": sorted(profile_ids),
            "status": status,
            "reason": reason,
        }
    return result


def audit_report(result_root: Path, excel_path: Path, tasks_dir: Path,
                 validity_path: Path | None = None, capability_map_path: Path | None = None,
                 models: set[str] | None = None,
                 harnesses: set[str] | None = None,
                 entities_path: Path | None = None,
                 pricing_date: date | None = None,
                 skip_checks: set[str] | None = None) -> dict:
    """审核报告，skip_checks 可包含 'validity_gate', 'root_cause_coverage'。"""
    skip_checks = skip_checks or set()
    findings: list[dict] = []
    specs = discover_units(result_root)
    if models:
        specs = [spec for spec in specs if spec[0] in models]
    if harnesses:
        specs = [spec for spec in specs if spec[1] in harnesses]
    if not specs:
        findings.append(finding(
            "NO_UNITS", "error", "过滤后未发现任何评测结果 unit"
        ))
    units = scan_raw_units(specs)
    meta = load_task_meta(tasks_dir)
    capability_map_path = capability_map_path or REPO_ROOT / "tools/report/data/checkpoint_capability_map7.yaml"
    capability_map = load_capability_map(capability_map_path)
    validity = load_validity(validity_path, findings, skip="validity_gate" in skip_checks)
    recomputed_costs = None
    if entities_path is not None and pricing_date is not None:
        try:
            registry = report_entities.load_registry(entities_path)
            recomputed_costs = recompute_unit_costs(specs, registry, pricing_date)
        except (OSError, ValueError) as exc:
            findings.append(finding(
                "PRICING_CONFIG_INVALID", "error", f"成本配置无法加载：{exc}"
            ))
    try:
        wb = load_workbook(excel_path, read_only=True, data_only=True)
    except Exception as exc:
        findings.append(finding("WORKBOOK_INVALID", "error", f"Excel 无法打开：{exc}"))
        wb = None
    if wb is not None:
        identities = load_identity_maps(wb)
        missing_sheets = CORE_SHEETS - set(wb.sheetnames)
        for title in sorted(missing_sheets):
            findings.append(finding("SHEET_MISSING", "error", f"缺少必需 Sheet：{title}", sheet=title))
        if "总览" in wb.sheetnames:
            audit_overview(wb, units, findings, identities, recomputed_costs)
        if "模型×Harness矩阵" in wb.sheetnames:
            audit_matrix(wb, units, findings, identities)
        if "用例对比明细" in wb.sheetnames:
            audit_case_compare(wb, units, findings, identities)
        audit_capabilities(wb, units, capability_map, findings, identities)
        dimension_specs = {
            "分类对比": build_groups(meta, units, "category"),
            "难度对比": build_groups(meta, units, "difficulty"),
            "模态对比": build_groups(meta, units, "modality"),
        }
        for title, groups in dimension_specs.items():
            if title in wb.sheetnames:
                audit_dimension_sheet(wb, title, units, groups, findings, identities)
        audit_difficulty_inversion(units, dimension_specs["难度对比"], findings)
        if "分差矩阵" in wb.sheetnames:
            audit_diff_matrix(wb, units, findings, identities)
        audit_detail_sheets(wb, units, findings, skip_root_cause_check="root_cause_coverage" in skip_checks)
        wb.close()
    counts = Counter(item["severity"] for item in findings)
    verdict = "FAIL" if counts["error"] else ("REVIEW" if counts["warning"] else "PASS")
    findings.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["id"],
                                    item["sheet"], item["unit"], item["task_id"]))
    return {
        "schema_version": 1,
        "check_type": "eval_report_audit",
        "result_root": str(result_root),
        "excel_path": str(excel_path),
        "tasks_dir": str(tasks_dir),
        "validity_path": str(validity_path) if validity_path else "",
        "capability_map_path": str(capability_map_path),
        "scope": {
            "models": sorted(models or {model for model, _, _ in specs}),
            "harnesses": sorted(harnesses or {harness for _, harness, _ in specs}),
        },
        "entities_path": str(entities_path) if entities_path else "",
        "pricing_date": pricing_date.isoformat() if pricing_date else "",
        "upstream_validity": validity.get("verdict") if validity else "UNKNOWN",
        "verdict": verdict,
        "summary": {"units": len(units), "errors": counts["error"],
                    "warnings": counts["warning"], "info": counts["info"],
                    "findings": len(findings)},
        "findings": findings,
    }


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# WildClawBench 评测报告审核",
        "",
        f"- 结论：**{report['verdict']}**",
        f"- Excel：`{report['excel_path']}`",
        f"- 原始结果：`{report['result_root']}`",
        f"- 前置有效性：**{report['upstream_validity']}**",
        f"- 问题：error {summary['errors']} / warning {summary['warnings']} / info {summary['info']}",
        "",
        "## 审核结果",
        "",
        "| 级别 | 规则 | Sheet | Unit/用例 | 说明 | 处置 |",
        "|---|---|---|---|---|---|",
    ]
    clean = lambda value: str(value or "-").replace("|", "\\|").replace("\n", " ")
    for item in report["findings"]:
        target = "/".join(value for value in (item["unit"], item["task_id"]) if value) or "-"
        lines.append("| " + " | ".join([
            clean(item["severity"]), clean(item["id"]), clean(item["sheet"]), clean(target),
            clean(item["message"]), clean(item["recommendation"]),
        ]) + " |")
    if not report["findings"]:
        lines.append("| info | NONE | - | - | 未发现异常 | - |")
    lines += [
        "", "## 发布门禁", "",
        "- `PASS`：自动对账通过，人工审核清单完成后可发布。",
        "- `REVIEW`：存在可解释但反常的统计信号，必须记录人工结论。",
        "- `FAIL`：存在数据或计算口径错误，修复并重新生成报告。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="审核 WildClawBench Excel 评测报告")
    parser.add_argument("--result-root", required=True, help="round/model/unit 原始结果目录")
    parser.add_argument("--excel", required=True, help="待审核 Excel")
    parser.add_argument("--tasks-dir", default=str(REPO_ROOT / "tasks"), help="任务定义目录")
    parser.add_argument("--models", nargs="+", help="仅审核指定模型原始 ID")
    parser.add_argument("--harnesses", nargs="+", help="仅审核指定 Harness 原始 ID")
    parser.add_argument("--entities", help="实体注册表 YAML，用于独立复算成本")
    parser.add_argument("--pricing-date", type=date.fromisoformat,
                        help="成本复算使用的定价快照日期 YYYY-MM-DD")
    parser.add_argument("--validity", help="有效性检查 JSON；默认从 round 工作区发现")
    parser.add_argument("--capability-map", help="能力映射 YAML")
    parser.add_argument("--skip-checks", nargs="+", default=[],
                        choices=["validity_gate", "root_cause_coverage"],
                        help="跳过指定检查项（preview 模式用）")
    parser.add_argument("--output-dir", help="默认 <round>/report-workspace/audit")
    parser.add_argument("--fail-on", choices=("never", "fail", "review"), default="never")
    args = parser.parse_args()

    result_root = Path(args.result_root).expanduser().resolve()
    excel_path = Path(args.excel).expanduser().resolve()
    tasks_dir = Path(args.tasks_dir).expanduser().resolve()
    if not result_root.is_dir():
        parser.error(f"结果目录不存在：{result_root}")
    if not excel_path.is_file():
        parser.error(f"Excel 不存在：{excel_path}")
    specs = discover_units(result_root)
    models = set(args.models or [])
    harnesses = set(args.harnesses or [])
    if models:
        specs = [spec for spec in specs if spec[0] in models]
    if harnesses:
        specs = [spec for spec in specs if spec[1] in harnesses]
    round_root = round_root_from_units(result_root, specs)
    default_validity = round_root / "report-workspace/validity/eval_result_validity.json"
    validity_path = Path(args.validity).expanduser().resolve() if args.validity else default_validity
    capability_map_path = (Path(args.capability_map).expanduser().resolve() if args.capability_map else
                           REPO_ROOT / "tools/report/data/checkpoint_capability_map7.yaml")
    entities_path = Path(args.entities).expanduser().resolve() if args.entities else None
    output_dir = (Path(args.output_dir).expanduser().resolve() if args.output_dir else
                  round_root / "report-workspace/audit")
    output_dir.mkdir(parents=True, exist_ok=True)
    skip_checks = set(args.skip_checks)
    report = audit_report(
        result_root, excel_path, tasks_dir, validity_path, capability_map_path,
        models or None, harnesses or None, entities_path, args.pricing_date,
        skip_checks,
    )
    stem = f"report_audit_{excel_path.stem}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"结论: {report['verdict']} | error={report['summary']['errors']} "
          f"warning={report['summary']['warnings']} | units={report['summary']['units']}")
    print(f"AUDIT_JSON={json_path}")
    print(f"AUDIT_REPORT={md_path}")
    if args.fail_on == "review" and report["verdict"] in {"REVIEW", "FAIL"}:
        return 2
    if args.fail_on == "fail" and report["verdict"] == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
