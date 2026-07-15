#!/usr/bin/env python3
"""WildClawBench 评测报告 Excel 生成脚本。

数据源：WildClawBench 评测结果目录（目录扫描为主，summary_all_*.json 仅校验）：

    <result-root>/<model>/<harness>/<suite>/<task_id>/<run_dir>/
        score.json / execution_status.json / usage.json / chat_openclaw.jsonl

对比单元为 (model, harness) 二元组，记 "<model>@<harness>"。

Sheet 布局（7 + N）：
    1. 总览                  每 unit 一行（总分 / 各分类均分 / 错误统计 / 资源）
    2. 模型×Harness矩阵       行=模型，列=harness，格=总均分
    3. 用例对比明细           每 unit 一列得分 + 最优/分差
    4. 分类对比 / 5. 难度对比 / 6. 模态对比
    7. 分差矩阵              unit×unit
    8+ 评分详情_<unit>       每 unit 一个（含预期行为/评分标准/Automated Checks），
                            支持 --analysis 回填结果分析/根因分析

任务元数据展示以中文版（tasks/cn/）为准，缺失字段回退英文版（tasks/）；
分类名取中文 md frontmatter 的 category（如 01_生产力工作流）。

用法示例：
    python3 generate_eval_report.py --result-root eval_out/all_suite/round1
    python3 generate_eval_report.py --result-root ... \
        --analysis report-workspace/analysis_gpt-5.5-pro@codex.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.formatting.rule import ColorScaleRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("缺少 openpyxl，请先安装：pip install openpyxl")

SUITE_DIR_RE = re.compile(r"^\d{2}_")
CELL_MAX_LEN = 32000
TRANSCRIPT_SUMMARY_MAX = 20000

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="4472C4")
CENTER = Alignment(horizontal="center", vertical="center")
WRAP_TOP = Alignment(wrap_text=True, vertical="top")

DIFFICULTY_ORDER = ["L1", "L2", "L3", "L4", "L5"]
MODALITY_ORDER = ["pure-text", "multimodal"]


# ===========================================================================
# 数据加载
# ===========================================================================

def is_unit_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if list(path.glob("summary_all_*.json")):
        return True
    return any(SUITE_DIR_RE.match(p.name) for p in path.iterdir() if p.is_dir())


def discover_units(result_root: Path) -> list[tuple[str, str, Path]]:
    """返回 [(model, harness, unit_dir)]，result_root 可为 round 根 / 模型目录 / unit 目录。"""
    if is_unit_dir(result_root):
        return [(result_root.parent.name, result_root.name, result_root)]
    units: list[tuple[str, str, Path]] = []
    for child in sorted(result_root.iterdir()):
        if not child.is_dir() or child.name in ("report-workspace", "output"):
            continue
        if is_unit_dir(child):
            units.append((result_root.name, child.name, child))
            continue
        for grand in sorted(child.iterdir()):
            if grand.is_dir() and is_unit_dir(grand):
                units.append((child.name, grand.name, grand))
    return units


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


class TaskRecord:
    def __init__(self, suite: str, task_dir: Path):
        self.task_id = task_dir.name
        self.suite = suite
        run_dirs = sorted(p for p in task_dir.iterdir() if p.is_dir())
        self.run_dir = run_dirs[-1] if run_dirs else None

        score = _load_json(self.run_dir / "score.json") if self.run_dir else {}
        status = _load_json(self.run_dir / "execution_status.json") if self.run_dir else {}
        self.usage = _load_json(self.run_dir / "usage.json") if self.run_dir else {}

        self.checkpoints = {
            k: v for k, v in score.items()
            if k != "overall_score" and isinstance(v, (int, float))
        }
        overall = score.get("overall_score")
        self.score = float(overall) if isinstance(overall, (int, float)) else None
        self.error_grading = score.get("error") or ("" if score else "score.json 缺失")
        self.error_execution = status.get("error") or ""
        self.timed_out = bool(status.get("timed_out"))
        self.status = status.get("status") or ""
        self.elapsed = status.get("elapsed_time")

        self.transcript = None
        if self.run_dir:
            for name in ("chat_openclaw.jsonl", "chat.jsonl"):
                cand = self.run_dir / name
                if cand.is_file():
                    self.transcript = cand
                    break

    @property
    def effective_score(self) -> float:
        """聚合口径：无有效得分按 0 计（与 summary global_avg 口径一致）。"""
        return self.score if self.score is not None else 0.0


class UnitResult:
    def __init__(self, model: str, harness: str, unit_dir: Path):
        self.model = model
        self.harness = harness
        self.unit = f"{model}@{harness}"
        self.unit_dir = unit_dir
        self.tasks: list[TaskRecord] = []
        for suite_dir in sorted(unit_dir.iterdir()):
            if not suite_dir.is_dir() or not SUITE_DIR_RE.match(suite_dir.name):
                continue
            for task_dir in sorted(suite_dir.iterdir()):
                if task_dir.is_dir() and any(p.is_dir() for p in task_dir.iterdir()):
                    self.tasks.append(TaskRecord(suite_dir.name, task_dir))
        self.task_map = {t.task_id: t for t in self.tasks}
        self.summary = self._load_summary()

    def _load_summary(self) -> dict:
        files = sorted(self.unit_dir.glob("summary_all_*.json"))
        return _load_json(files[0]) if files else {}

    @property
    def total_pct(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(t.effective_score for t in self.tasks) / len(self.tasks) * 100

    def avg_pct(self, task_ids: set[str]) -> float | None:
        hit = [t for t in self.tasks if t.task_id in task_ids]
        if not hit:
            return None
        return sum(t.effective_score for t in hit) / len(hit) * 100

    def usage_total(self, key: str) -> float:
        return sum((t.usage or {}).get(key, 0) or 0 for t in self.tasks)


# ===========================================================================
# 任务元数据（tasks/<套件>/<task_id>.md）
# ===========================================================================

def find_tasks_dir(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).resolve()
        return p if p.is_dir() else None
    cur = Path(__file__).resolve().parent
    for _ in range(8):
        cand = cur / "tasks"
        if cand.is_dir() and any(SUITE_DIR_RE.match(p.name) for p in cand.iterdir() if p.is_dir()):
            return cand
        cur = cur.parent
    return None


SECTION_KEYS = {
    "Prompt": "prompt",
    "Expected Behavior": "expected",
    "Grading Criteria": "criteria",
    "Automated Checks": "checks",
}


def parse_task_md(path: Path) -> dict:
    """解析任务 .md：frontmatter（name/category/difficulty/...）+ 正文各章节。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    meta: dict = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line and not line.startswith((" ", "\t", "#")):
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip().strip('"').strip("'")
            body = text[end + 4:]
    for m in re.finditer(r"^##\s*(.+?)\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S):
        key = SECTION_KEYS.get(m.group(1).strip())
        if key:
            meta[key] = m.group(2).strip()
    return meta


def load_all_task_meta(tasks_dir: Path | None) -> dict[str, dict]:
    """加载任务元数据：以中文版（tasks/cn/）为准展示，缺失字段回退英文版。"""
    if tasks_dir is None:
        return {}
    out: dict[str, dict] = {}
    for base in (tasks_dir, tasks_dir / "cn"):  # 先英文打底，再中文覆盖
        if not base.is_dir():
            continue
        for suite_dir in sorted(base.iterdir()):
            if not suite_dir.is_dir() or not SUITE_DIR_RE.match(suite_dir.name):
                continue
            for md in sorted(suite_dir.glob("*.md")):
                meta = parse_task_md(md)
                meta["suite"] = suite_dir.name
                merged = out.setdefault(md.stem, {})
                merged.update({k: v for k, v in meta.items() if v})
    return out


def build_suite_zh_map(task_meta: dict[str, dict]) -> dict[str, str]:
    """套件目录名 → 中文分类名（取自中文 md frontmatter 的 category 字段）。"""
    mapping: dict[str, str] = {}
    for meta in task_meta.values():
        suite, category = meta.get("suite"), meta.get("category", "")
        if suite and category and re.search(r"[一-鿿]", category):
            mapping.setdefault(suite, category)
    return mapping


# ===========================================================================
# transcript 执行记录摘要
# ===========================================================================

def summarize_transcript(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    parts: list[str] = []
    total = 0
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = event.get("message") or {}
                role = msg.get("role", "")
                for c in msg.get("content") or []:
                    ctype = c.get("type")
                    if ctype == "text" and role == "assistant":
                        snippet = f"[assistant] {c.get('text', '').strip()}"
                    elif ctype == "tool_use":
                        arg = json.dumps(c.get("input"), ensure_ascii=False)
                        snippet = f"[tool_use {c.get('name')}] {arg[:500]}"
                    elif ctype == "tool_result":
                        content = c.get("content")
                        if isinstance(content, list):
                            content = " ".join(x.get("text", "") for x in content if isinstance(x, dict))
                        snippet = f"[tool_result] {str(content).strip()[:300]}"
                    else:
                        continue
                    parts.append(snippet)
                    total += len(snippet)
                    if total > TRANSCRIPT_SUMMARY_MAX:
                        parts.append("…（已截断）")
                        return "\n".join(parts)
    except OSError:
        return ""
    return "\n".join(parts)


# ===========================================================================
# 分析结果加载（--analysis 回填）
# ===========================================================================

def load_analysis(specs: list[str], units: list[UnitResult]) -> dict[str, dict]:
    """返回 {"<unit>::<task_id>": {result_analysis, root_cause_analysis}}。

    spec 形式：PATH 或 UNIT=PATH。文件内容两种格式：
    - {task_id: {...}}（单 unit，unit 由显式绑定或文件名 analysis_<unit>*.json 推断）
    - {"<unit>::<task_id>": {...}}（多 unit 合并文件）
    """
    unit_ids = [u.unit for u in units]
    merged: dict[str, dict] = {}
    for spec in specs:
        bound = None
        path_str = spec
        if "=" in spec and not Path(spec).exists():
            bound, _, path_str = spec.partition("=")
        path = Path(path_str)
        if not path.is_file():
            print(f"[警告] 分析文件不存在，跳过：{path}", file=sys.stderr)
            continue
        data = _load_json(path)
        if not isinstance(data, dict):
            print(f"[警告] 分析文件格式不是字典，跳过：{path}", file=sys.stderr)
            continue
        count = 0
        for key, val in data.items():
            if not isinstance(val, dict):
                continue
            if "::" in key:
                merged[key] = val
                count += 1
                continue
            unit = bound
            if unit is None:
                matches = [u for u in unit_ids if u in path.name]
                unit = max(matches, key=len) if matches else None
            if unit is None:
                print(f"[警告] 无法从文件名 {path.name} 匹配到已加载 unit，"
                      f"请用 UNIT=PATH 显式绑定（已加载：{unit_ids}）", file=sys.stderr)
                break
            merged[f"{unit}::{key}"] = val
            count += 1
        if count:
            print(f"已加载分析 {count} 条：{path.name}")
    print(f"已加载分析回填合计 {len(merged)} 条（来自 {len(specs)} 个文件）")
    return merged


# ===========================================================================
# Excel 辅助
# ===========================================================================

def style_header_row(ws) -> None:
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER


def set_widths(ws, widths: dict[int, int], default: int = 16, ncols: int | None = None) -> None:
    ncols = ncols or ws.max_column
    for i in range(1, ncols + 1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(i, default)


def truncate(text: str) -> str:
    text = ILLEGAL_CHARACTERS_RE.sub("", text)  # openpyxl 拒绝 XML 非法控制字符
    if len(text) > CELL_MAX_LEN:
        return text[: CELL_MAX_LEN - 20] + "\n…（已截断）"
    return text


PCT_FMT = '0.0"%"'            # 数值单元格显示为 41.6%，排序/色阶仍按数值生效
PCT_SIGNED_FMT = '+0.0"%";-0.0"%";0.0"%"'


def apply_pct_format(ws, row: int, cols) -> None:
    """对指定行的列应用百分比数字格式（仅数值单元格）。"""
    for col in cols:
        cell = ws.cell(row=row, column=col)
        if isinstance(cell.value, (int, float)):
            cell.number_format = PCT_FMT


def add_color_scale(ws, first_row: int, last_row: int, first_col: int, last_col: int) -> None:
    if last_row < first_row or last_col < first_col:
        return
    rng = (f"{get_column_letter(first_col)}{first_row}:"
           f"{get_column_letter(last_col)}{last_row}")
    ws.conditional_formatting.add(rng, ColorScaleRule(
        start_type="num", start_value=0, start_color="F8696B",
        mid_type="num", mid_value=50, mid_color="FFEB84",
        end_type="num", end_value=100, end_color="63BE7B",
    ))


# ===========================================================================
# Sheet 写入
# ===========================================================================

def write_overview_sheet(wb, units: list[UnitResult], suites: list[str],
                         suite_zh: dict[str, str]) -> None:
    ws = wb.active
    ws.title = "总览"
    header = (["模型", "Harness", "总平均分", "用例数", "执行错误数", "超时数"]
              + [suite_zh.get(s, s) for s in suites]
              + ["总tokens", "总请求数", "总耗时(s)", "总成本(USD)"])
    ws.append(header)
    for u in units:
        suite_ids = {s: {t.task_id for t in u.tasks if t.suite == s} for s in suites}
        row = [
            u.model, u.harness, round(u.total_pct, 1), len(u.tasks),
            sum(1 for t in u.tasks if t.error_execution),
            sum(1 for t in u.tasks if t.timed_out),
        ]
        suite_avgs = [u.avg_pct(suite_ids[s]) for s in suites]
        row += [round(v, 1) if v is not None else "-" for v in suite_avgs]
        row += [
            int(u.usage_total("total_tokens")),
            int(u.usage_total("request_count")),
            round(u.usage_total("elapsed_time"), 1),
            round(u.usage_total("cost_usd"), 4),
        ]
        ws.append(row)
        apply_pct_format(ws, ws.max_row, [3] + list(range(7, 7 + len(suites))))
        g_avg = u.summary.get("global_avg")
        if g_avg is not None and abs(u.total_pct / 100 - g_avg) > 0.005:
            print(f"[警告] {u.unit} 重算均分 {u.total_pct / 100:.4f} 与 summary "
                  f"global_avg {g_avg:.4f} 偏差过大", file=sys.stderr)
    style_header_row(ws)
    set_widths(ws, {1: 22, 2: 12}, default=18)
    ws.freeze_panes = "C2"


def write_matrix_sheet(wb, units: list[UnitResult]) -> None:
    ws = wb.create_sheet("模型×Harness矩阵")
    lookup = {(u.model, u.harness): u.total_pct for u in units}
    # 行（模型）按该模型各 harness 的最高总均分降序；列（harness）按列均分降序
    models = sorted({u.model for u in units},
                    key=lambda m: max(v for (mm, _), v in lookup.items() if mm == m),
                    reverse=True)
    harnesses = sorted({u.harness for u in units},
                       key=lambda h: (sum(v for (_, hh), v in lookup.items() if hh == h)
                                      / max(1, sum(1 for (_, hh) in lookup if hh == h))),
                       reverse=True)
    ws.append(["模型 \\ Harness"] + harnesses)
    for m in models:
        row = [m]
        for h in harnesses:
            v = lookup.get((m, h))
            row.append(round(v, 1) if v is not None else "-")
        ws.append(row)
        apply_pct_format(ws, ws.max_row, range(2, 2 + len(harnesses)))
    style_header_row(ws)
    set_widths(ws, {1: 24}, default=16)
    ws.freeze_panes = "B2"
    add_color_scale(ws, 2, 1 + len(models), 2, 1 + len(harnesses))


def build_task_order(units: list[UnitResult]) -> list[tuple[str, str]]:
    """全部 unit 的 (suite, task_id) 并集，按套件、任务序号排序。"""
    seen: dict[str, str] = {}
    for u in units:
        for t in u.tasks:
            seen.setdefault(t.task_id, t.suite)

    def sort_key(item):
        task_id, suite = item
        m = re.search(r"task_(\d+)", task_id)
        return (suite, int(m.group(1)) if m else 999, task_id)

    return [(suite, tid) for tid, suite in sorted(seen.items(), key=sort_key)]


def write_case_compare_sheet(wb, units: list[UnitResult], order: list[tuple[str, str]],
                             task_meta: dict[str, dict], suite_zh: dict[str, str]) -> None:
    ws = wb.create_sheet("用例对比明细")
    header = (["分类", "用例ID", "用例名称", "难度", "模态", "输入(Prompt)"]
              + [f"{u.unit} 得分" for u in units]
              + ["最优单元", "最大分差"])
    ws.append(header)
    for suite, tid in order:
        meta = task_meta.get(tid, {})
        scores = {u.unit: u.task_map[tid].score for u in units if tid in u.task_map}
        valid = {k: v for k, v in scores.items() if v is not None}
        best = max(valid, key=valid.get) if valid else "-"
        spread = round(max(valid.values()) - min(valid.values()), 3) if len(valid) > 1 else "-"
        row = [suite_zh.get(suite, suite), tid, meta.get("name", "-"), meta.get("difficulty", "-"),
               meta.get("modality", "-"), truncate(meta.get("prompt", ""))]
        row += [(round(scores[u.unit], 3) if scores.get(u.unit) is not None else "-")
                if u.unit in scores else "-" for u in units]
        row += [best, spread]
        ws.append(row)
        ws.cell(row=ws.max_row, column=6).alignment = WRAP_TOP
    style_header_row(ws)
    set_widths(ws, {1: 22, 2: 40, 3: 30, 4: 8, 5: 12, 6: 50,
                    7 + len(units): 26, 8 + len(units): 10}, default=20)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}1"


def write_dimension_sheet(wb, title: str, dim_label: str, units: list[UnitResult],
                          groups: list[tuple[str, set[str]]]) -> None:
    """通用维度对比：行=维度取值，列=各 unit 均分 + 最佳 + 分差。"""
    ws = wb.create_sheet(title)
    ws.append([dim_label, "用例数"] + [f"{u.unit} 平均分" for u in units] + ["最佳单元", "最高-最低分差"])
    for label, task_ids in groups:
        if not task_ids:
            continue
        vals = {u.unit: u.avg_pct(task_ids) for u in units}
        valid = {k: v for k, v in vals.items() if v is not None}
        best = max(valid, key=valid.get) if valid else "-"
        spread = round(max(valid.values()) - min(valid.values()), 1) if len(valid) > 1 else "-"
        ws.append([label, len(task_ids)]
                  + [round(vals[u.unit], 1) if vals[u.unit] is not None else "-" for u in units]
                  + [best, spread])
        apply_pct_format(ws, ws.max_row, list(range(3, 3 + len(units))) + [4 + len(units)])
    style_header_row(ws)
    set_widths(ws, {1: 30, 2: 10, 3 + len(units): 26}, default=20)
    ws.freeze_panes = "B2"
    add_color_scale(ws, 2, ws.max_row, 3, 2 + len(units))


def write_dimension_sheet_transposed(wb, title: str, units: list[UnitResult],
                                     groups: list[tuple[str, set[str]]]) -> None:
    """转置维度对比：行=unit（按总平均分降序），列=维度取值（表头带用例数）。"""
    ws = wb.create_sheet(title)
    groups = [(label, ids) for label, ids in groups if ids]
    ws.append(["模型@Harness", "总平均分"]
              + [f"{label} 平均分({len(ids)}例)" for label, ids in groups])
    for u in units:  # units 已按总平均分降序
        row = [u.unit, round(u.total_pct, 1)]
        for _, ids in groups:
            v = u.avg_pct(ids)
            row.append(round(v, 1) if v is not None else "-")
        ws.append(row)
        apply_pct_format(ws, ws.max_row, range(2, 3 + len(groups)))
    style_header_row(ws)
    set_widths(ws, {1: 28, 2: 12}, default=22)
    ws.freeze_panes = "B2"
    add_color_scale(ws, 2, ws.max_row, 2, 2 + len(groups))


def write_diff_matrix_sheet(wb, units: list[UnitResult]) -> None:
    ws = wb.create_sheet("分差矩阵")
    ws.append(["行单元 - 列单元"] + [u.unit for u in units])
    for a in units:
        row = [a.unit]
        for b in units:
            row.append(0 if a is b else round(a.total_pct - b.total_pct, 1))
        ws.append(row)
        for col in range(2, 2 + len(units)):
            ws.cell(row=ws.max_row, column=col).number_format = PCT_SIGNED_FMT
    style_header_row(ws)
    set_widths(ws, {1: 28}, default=22)
    ws.freeze_panes = "B2"


def format_breakdown(t: TaskRecord) -> str:
    if not t.checkpoints:
        return "-"
    return "\n".join(f"{k}: {v}" for k, v in t.checkpoints.items())


def format_lost_points(t: TaskRecord) -> str:
    if not t.checkpoints:
        return "无检查点数据"
    zero = [k for k, v in t.checkpoints.items() if v <= 1e-9]
    partial = [f"{k}={v}" for k, v in t.checkpoints.items() if 1e-9 < v < 1.0 - 1e-9]
    if not zero and not partial:
        return "无失分"
    lines = []
    if zero:
        lines.append("完全失分: " + ", ".join(zero))
    if partial:
        lines.append("部分失分: " + ", ".join(partial))
    return "\n".join(lines)


def write_detail_sheet(wb, u: UnitResult, order: list[tuple[str, str]],
                       task_meta: dict[str, dict], analysis: dict[str, dict],
                       suite_zh: dict[str, str]) -> None:
    ws = wb.create_sheet(f"评分详情_{u.unit}"[:31])
    header = ["分类", "用例ID", "用例名称", "难度", "超时时间(秒)", "模态",
              "输入(Prompt)", "预期行为", "评分标准", "Automated Checks",
              "状态", "总得分", "检查点得分明细", "失分点", "执行错误",
              "总tokens", "请求数", "耗时(s)", "执行记录摘要", "结果分析", "根因分析"]
    ws.append(header)
    wrap_cols = {7, 8, 9, 10, 13, 14, 15, 19, 20, 21}
    for suite, tid in order:
        t = u.task_map.get(tid)
        if t is None:
            continue
        meta = task_meta.get(tid, {})
        item = analysis.get(f"{u.unit}::{tid}", {})
        err = "\n".join(x for x in (
            f"执行层: {t.error_execution}" if t.error_execution else "",
            f"判分层: {t.error_grading}" if t.error_grading else "",
        ) if x) or "-"
        ws.append([
            suite_zh.get(suite, suite), tid, meta.get("name", "-"),
            meta.get("difficulty", "-"), meta.get("timeout_seconds", "-"),
            meta.get("modality", "-"),
            truncate(meta.get("prompt", "")), truncate(meta.get("expected", "")),
            truncate(meta.get("criteria", "")), truncate(meta.get("checks", "")),
            (t.status or "-") + ("（超时）" if t.timed_out else ""),
            round(t.score, 3) if t.score is not None else "-",
            format_breakdown(t), format_lost_points(t), truncate(err),
            int((t.usage or {}).get("total_tokens", 0)),
            int((t.usage or {}).get("request_count", 0)),
            round(t.elapsed, 1) if isinstance(t.elapsed, (int, float)) else "-",
            truncate(summarize_transcript(t.transcript)),
            truncate(item.get("result_analysis", "") or ""),
            truncate(item.get("root_cause_analysis", "") or item.get("root_cause", "") or ""),
        ])
        for col in wrap_cols:
            ws.cell(row=ws.max_row, column=col).alignment = WRAP_TOP
    style_header_row(ws)
    set_widths(ws, {1: 18, 2: 40, 3: 30, 4: 8, 5: 12, 6: 12,
                    7: 45, 8: 45, 9: 45, 10: 45, 11: 14, 12: 8,
                    13: 40, 14: 40, 15: 40, 16: 12, 17: 8, 18: 8,
                    19: 60, 20: 45, 21: 40})
    ws.freeze_panes = "C2"


# ===========================================================================
# main
# ===========================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="WildClawBench 评测报告 Excel 生成")
    ap.add_argument("--result-root", required=True, help="round 根目录 / 模型目录 / unit 目录")
    ap.add_argument("--models", nargs="+", help="按模型目录名过滤")
    ap.add_argument("--harnesses", nargs="+", help="按 harness 目录名过滤")
    ap.add_argument("--analysis", nargs="+", default=[], metavar="[UNIT=]PATH",
                    help="根因分析 JSON（可多个），回填到详情 Sheet")
    ap.add_argument("-o", "--output-dir", help="输出目录（默认 <result-root>/report-workspace/output）")
    ap.add_argument("--tasks-dir", help="任务定义目录（默认从脚本位置向上找 <repo>/tasks）")
    args = ap.parse_args()

    result_root = Path(args.result_root).resolve()
    if not result_root.is_dir():
        sys.exit(f"错误：结果目录不存在：{result_root}")

    unit_specs = discover_units(result_root)
    if args.models:
        unit_specs = [u for u in unit_specs if u[0] in args.models]
    if args.harnesses:
        unit_specs = [u for u in unit_specs if u[1] in args.harnesses]
    if not unit_specs:
        sys.exit("错误：未发现任何 (model, harness) 结果单元")

    units = []
    for model, harness, unit_dir in unit_specs:
        u = UnitResult(model, harness, unit_dir)
        print(f"已加载 {u.unit}：{len(u.tasks)} 个任务，总均分 {u.total_pct:.1f}%")
        units.append(u)
    # 全局按总平均分降序：决定总览行序与各对比 Sheet 的 unit 列序（最高分在前）
    units.sort(key=lambda u: u.total_pct, reverse=True)

    tasks_dir = find_tasks_dir(args.tasks_dir)
    if tasks_dir is None:
        print("[警告] 未找到任务定义目录（tasks/），名称/难度/模态/Prompt 列将为空；"
              "可用 --tasks-dir 指定", file=sys.stderr)
    task_meta = load_all_task_meta(tasks_dir)
    analysis = load_analysis(args.analysis, units) if args.analysis else {}

    order = build_task_order(units)
    suites = sorted({s for s, _ in order})
    suite_zh = build_suite_zh_map(task_meta)

    wb = Workbook()
    write_overview_sheet(wb, units, suites, suite_zh)
    write_matrix_sheet(wb, units)
    write_case_compare_sheet(wb, units, order, task_meta, suite_zh)
    write_dimension_sheet(wb, "分类对比", "分类", units,
                          [(suite_zh.get(s, s), {tid for su, tid in order if su == s})
                           for s in suites])

    def meta_groups(field: str, known_order: list[str]) -> list[tuple[str, set[str]]]:
        values = {task_meta.get(tid, {}).get(field, "") for _, tid in order}
        values.discard("")
        ordered = [v for v in known_order if v in values] + sorted(values - set(known_order))
        return [(v, {tid for _, tid in order if task_meta.get(tid, {}).get(field) == v})
                for v in ordered]

    write_dimension_sheet_transposed(wb, "难度对比", units, meta_groups("difficulty", DIFFICULTY_ORDER))
    write_dimension_sheet_transposed(wb, "模态对比", units, meta_groups("modality", MODALITY_ORDER))
    write_diff_matrix_sheet(wb, units)
    for u in units:
        write_detail_sheet(wb, u, order, task_meta, analysis, suite_zh)

    out_dir = Path(args.output_dir) if args.output_dir else result_root / "report-workspace" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"report_{len(units)}units_{ts}.xlsx"
    wb.save(out_path)
    print(f"\n✅ 报告已生成：{out_path}")


if __name__ == "__main__":
    main()
