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
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    from openpyxl.formatting.rule import ColorScaleRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("缺少 openpyxl（需 3.1+，含富文本支持），请先安装：pip install 'openpyxl>=3.1'")

SUITE_DIR_RE = re.compile(r"^\d{2}_")
CELL_MAX_LEN = 32000

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="4472C4")
CENTER = Alignment(horizontal="center", vertical="center")
WRAP_TOP = Alignment(wrap_text=True, vertical="top")

DIFFICULTY_ORDER = ["L1", "L2", "L3", "L4", "L5"]
MODALITY_ORDER = ["pure-text", "multimodal"]
MODALITY_ZH = {"pure-text": "纯文本", "multimodal": "多模态"}

# 多轮 pass@k/pass^k：复用评测框架的无偏估计公式，避免口径漂移。
# 展示层默认阈值 0.99（满分算 pass），与 summary 默认口径一致。
PASS_THRESHOLD_DISPLAY = 0.99
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from src.utils.multirun_stats import pass_at_k as _pass_at_k, pass_hat_k as _pass_hat_k
except Exception:  # 独立分发/路径异常时内联同款公式兜底
    import math as _math
    def _pass_at_k(n: int, c: int, k: int) -> float:
        if k > n or n <= 0 or c <= 0:
            return 0.0
        if n - c < k:
            return 1.0
        return 1.0 - _math.comb(n - c, k) / _math.comb(n, k)
    def _pass_hat_k(n: int, c: int, k: int) -> float:
        if k > n or n <= 0 or c < k:
            return 0.0
        return _math.comb(c, k) / _math.comb(n, k)

# 工具调用指标：复用评测框架共享模块（判定口径唯一来源），避免与平台后端漂移。
# 见 docs/local/design/Harness工具调用指标设计.md。
try:
    from src.utils.tool_metrics import (
        parse_tool_metrics as _parse_tool_metrics,
        merge_metrics as _merge_tool_metrics,
        format_accuracy as _tm_format_accuracy,
        execution_success_rate as _tm_exec_success,
        overall_success_rate as _tm_overall_success,
        unclear_ratio as _tm_unclear_ratio,
    )
    _TOOL_METRICS_OK = True
except Exception:  # 独立分发/路径异常时降级：不统计工具调用指标
    _TOOL_METRICS_OK = False
    def _parse_tool_metrics(path, harness):
        return {"total": 0, "success": 0, "failure": 0, "format_error": 0,
                "unclear": 0, "by_tool": {}}
    def _merge_tool_metrics(lst):
        return {"total": 0, "success": 0, "failure": 0, "format_error": 0,
                "unclear": 0, "by_tool": {}}
    _tm_format_accuracy = _tm_exec_success = _tm_overall_success = \
        _tm_unclear_ratio = lambda m: None

# 7 维能力口径（与 PinchBench cap7 对齐）；映射文件见 tools/report/data/checkpoint_capability_map7.yaml
CAP7_ORDER = ["code_generation", "tool_use", "data_processing", "retrieval_verification",
              "reasoning_planning", "content_generation", "verification_delivery"]
CAP7_ZH = {
    "code_generation": "代码生成", "tool_use": "工具调用", "data_processing": "数据处理",
    "retrieval_verification": "检索验证", "reasoning_planning": "推理规划",
    "content_generation": "内容生成", "verification_delivery": "验证交付",
}
# 去落盘污染列：仅统计"产物成功落盘"的用例，剥离未落盘对上游能力得分的污染
CAP7_DECON = ["data_processing", "reasoning_planning", "content_generation"]
FILE_CKPT_RE = re.compile(r"exist|created|saved|written|parseable", re.I)
CAP_RANK_MIN_COUNT = 5  # 强项/短板排名要求的最少涉及用例数
# 诊断计量键（调用次数/重试次数/满分常量等），不是 0~1 得分，不参与能力聚合
METRIC_CKPT_RE = re.compile(r"(_max$|_calls$|_attempts$|_triggered$|^penalty)")


def normalize_ckpt_value(key: str, value: float, all_ckpts: dict) -> float | None:
    """把检查点值归一到 0~1；诊断计量键与无法归一的原始值返回 None。

    WildClawBench 的 score.json 混有三类值：0~1 比率（主体）、
    `X_earned`/`X_max` 原始计分对（按比值归一）、诊断计数（排除）。
    """
    if METRIC_CKPT_RE.search(key):
        return None
    if key.endswith("_earned"):
        mx = all_ckpts.get(key[: -len("_earned")] + "_max")
        if isinstance(mx, (int, float)) and mx > 0:
            return min(1.0, max(0.0, value / mx))
    if 0 <= value <= 1:
        return float(value)
    return None


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
    """返回 [(model, harness, unit_dir)]，result_root 可为 round 根 / 模型目录 / unit 目录。

    支持两种 round 布局：
    - 双层 `<round>/<model>/<harness>`（单 harness 汇总，历史默认）；
    - 三层 `<round>/<harness>/<model>/<harness>`（多 harness 汇总，同一
      模型集在多个 harness 各跑一遍时使用）。
    自动向下探测，遇到 unit 目录（含 summary_all_*.json 或套件子目录）即停。
    """
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
            if not grand.is_dir() or grand.name in ("report-workspace", "output"):
                continue
            if is_unit_dir(grand):
                # 双层：child=model, grand=harness
                units.append((child.name, grand.name, grand))
                continue
            # 三层：child=harness, grand=model，再下探一层找 unit
            for ggrand in sorted(grand.iterdir()):
                if ggrand.is_dir() and is_unit_dir(ggrand):
                    units.append((grand.name, ggrand.name, ggrand))
    return units


def round_root_from_unit_dir(unit_dir: Path) -> Path:
    """按双层或三层结果结构从 unit 反推 round 根目录。"""
    unit_dir = unit_dir.resolve()
    # 三层：<round>/<harness>/<model>/<harness>，首尾 harness 重复。
    if unit_dir.parent.parent.name == unit_dir.name:
        return unit_dir.parents[2]
    return unit_dir.parents[1]


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# 裁判判词类字段：键名含 reason/reasoning（如 judge_reason、image_judge_reason、
# llm_judge_reasoning、嵌套 llm_judge.reasoning、06 套件 recognized_*_reason）
_JUDGE_REASON_RE = re.compile(r"reason", re.I)
_JUDGE_ERROR_RE = re.compile(r"(judge_error|llm_error)$", re.I)


def extract_judge_notes(score: dict) -> str:
    """从 score.json 递归提取 LLM/VLM 裁判判词与裁判异常，逐行 `键: 文本`。"""
    lines: list[str] = []

    def walk(prefix: str, obj: dict) -> None:
        for k, v in obj.items():
            key = f"{prefix}{k}"
            if isinstance(v, dict):
                walk(f"{key}.", v)
            elif isinstance(v, str) and v.strip():
                if _JUDGE_REASON_RE.search(k):
                    lines.append(f"{key}: {v.strip()}")
                elif _JUDGE_ERROR_RE.search(k):
                    lines.append(f"⚠裁判异常 {key}: {v.strip()}")

    walk("", score)
    return "\n".join(lines)


class TaskRecord:
    def __init__(self, suite: str, task_dir: Path, harness: str = ""):
        self.task_id = task_dir.name
        self.suite = suite
        self.harness = harness
        run_dirs = sorted(p for p in task_dir.iterdir() if p.is_dir())

        # 多轮支持：收集全部 run 的 overall_score，取 mean 作为代表分
        all_scores = []
        for rd in run_dirs:
            s = _load_json(rd / "score.json")
            ov = s.get("overall_score") if s else None
            if isinstance(ov, (int, float)):
                all_scores.append(float(ov))

        # 展示用最新一轮（transcript/检查点明细）
        self.run_dir = run_dirs[-1] if run_dirs else None

        score = _load_json(self.run_dir / "score.json") if self.run_dir else {}
        status = _load_json(self.run_dir / "execution_status.json") if self.run_dir else {}
        self.usage = _load_json(self.run_dir / "usage.json") if self.run_dir else {}

        self.checkpoints = {
            k: v for k, v in score.items()
            if k != "overall_score" and isinstance(v, (int, float))
        }

        # 多轮聚合：score 取 mean（单轮时 mean == 单值）
        # pass@k/pass^k 按默认阈值 0.99（满分算 pass）计算——展示层用默认即可，
        # 与 summary_all_*.json 的 multirun.pass_threshold 口径一致（默认未改时）。
        if all_scores:
            from statistics import fmean, pstdev
            self.score = fmean(all_scores)
            self.runs = len(all_scores)
            self.std = pstdev(all_scores) if len(all_scores) > 1 else 0.0
            self.all_scores = all_scores
            if len(all_scores) > 1:
                n = len(all_scores)
                c = sum(1 for s in all_scores if s >= PASS_THRESHOLD_DISPLAY)
                self.pass_at_k = _pass_at_k(n, c, n)
                self.pass_hat_k = _pass_hat_k(n, c, n)
            else:
                self.pass_at_k = None
                self.pass_hat_k = None
        else:
            self.score = None
            self.runs = 0
            self.std = None
            self.all_scores = []
            self.pass_at_k = None
            self.pass_hat_k = None

        overall = score.get("overall_score")
        # 兼容：如果 all_scores 空但最新 run 有 overall_score，回退单值
        if self.score is None and isinstance(overall, (int, float)):
            self.score = float(overall)
            self.runs = 1
            self.std = 0.0
            self.all_scores = [self.score]

        self.judge_notes = extract_judge_notes(score)
        self.error_grading = score.get("error") or ("" if score else "score.json 缺失")
        self.error_execution = status.get("error") or ""
        self.timed_out = bool(status.get("timed_out"))
        self.status = status.get("status") or ""
        self.elapsed = status.get("elapsed_time")
        # Harness build version (runner writes it to execution_status.json).
        self.harness_version = status.get("harness_version") or ""

        self.transcript = None
        if self.run_dir:
            for name in ("chat_openclaw.jsonl", "chat.jsonl"):
                cand = self.run_dir / name
                if cand.is_file():
                    self.transcript = cand
                    break

        # 工具调用指标（基于最新一轮的归一化轨迹）。未注册 harness / 无轨迹 → 空指标。
        self.tool_metrics = _parse_tool_metrics(self.transcript, self.harness)

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
                    self.tasks.append(TaskRecord(suite_dir.name, task_dir, harness))
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

    def tool_metrics_total(self) -> dict:
        """聚合该 unit 全部用例的工具调用指标（含 by_tool 明细）。"""
        return _merge_tool_metrics([t.tool_metrics for t in self.tasks])

    @property
    def harness_version(self) -> str:
        """该 unit 的 harness 版本（取任务中出现最多的非空版本）。

        版本由 runner 写入各 run 的 execution_status.json。旧结果没有该字段
        时返回 ""，展示层退化为不带版本的 harness 名。
        """
        from collections import Counter
        versions = Counter(t.harness_version for t in self.tasks if t.harness_version)
        return versions.most_common(1)[0][0] if versions else ""

    @property
    def harness_label(self) -> str:
        """带版本的 harness 展示名，如 "opencode (1.18.4)"；无版本则退化为 "opencode"。"""
        return f"{self.harness} ({self.harness_version})" if self.harness_version else self.harness


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
    "Workspace Path": "workspace",
    "Skills": "skills",
    "Env": "env",
    "Warmup": "warmup",
}


def strip_code_fence(text: str) -> str:
    """去掉章节内容外层的 ``` 围栏，只留内容本身。"""
    lines = [l for l in text.strip().splitlines() if not l.strip().startswith("```")]
    return "\n".join(lines).strip()


# 非数值检查点的键（文本型字段 / 汇总键），提取时排除
_CKPT_KEY_BLACKLIST_RE = re.compile(r"^(overall_score|error)$|(_reason|_error)$")


def extract_defined_ckpts(checks_code: str) -> list[str]:
    """从任务 md 的 Automated Checks 判分代码提取检查点键（定义序）。

    检查点由任务定义决定，与是否跑过评测无关。静态解析覆盖两种主流写法：
    scores["key"] = ... 赋值、ALL_CRITERIA 键列表；动态键（如 f"..._{i}"）
    解析不到，由调用方用实测键补全。
    """
    keys: dict[str, None] = {}
    for lst in re.findall(r"(?:ALL_CRITERIA|CRITERIA|ALL_KEYS)\s*=\s*[\[\(](.*?)[\]\)]",
                          checks_code, re.S):
        for k in re.findall(r"[\"']([A-Za-z_][A-Za-z_0-9]*)[\"']", lst):
            keys.setdefault(k)
    for k in re.findall(r"scores\[\s*[\"']([A-Za-z_][A-Za-z_0-9]*)[\"']\s*\]", checks_code):
        keys.setdefault(k)
    return [k for k in keys if not _CKPT_KEY_BLACKLIST_RE.search(k)]


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
    if meta.get("checks"):
        ckpts = extract_defined_ckpts(meta["checks"])
        if ckpts:
            meta["ckpt_keys"] = ckpts
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
# transcript 执行记录（jsonl 原文，超出单元格上限时截断）
# ===========================================================================

def read_transcript_raw(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        # 单元格上限 32000，最多多读一段用于触发截断标记
        with path.open(encoding="utf-8") as f:
            return f.read(CELL_MAX_LEN + 1024)
    except OSError:
        return ""


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
            merged_key = f"{unit}::{key}"
            if merged_key in merged:
                print(f"[警告] 分析项重复，后加载文件覆盖前值：{merged_key}（{path.name}）",
                      file=sys.stderr)
            merged[merged_key] = val
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


def style_row(ws, row: int) -> None:
    """把指定行作为表头样式（用于多分区 Sheet 的各段表头）。"""
    for cell in ws[row]:
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


def _pct_or_dash(frac: float | None):
    """比率(0~1)转百分比数值(如 68.3)供 PCT_FMT 展示；None → "-"。"""
    return round(frac * 100, 1) if frac is not None else "-"


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
    # 检测是否有多轮数据（任一 task.runs > 1）
    # 总览只放"平均轮数"（说明这是几轮的结果）；std/pass@k/pass^k 跨题聚合无统计意义，
    # 移到独立的「多轮稳定性分析」Sheet 用分布统计展示（见 write_stability_sheet）。
    has_multirun = any(t.runs > 1 for u in units for t in u.tasks)
    multirun_cols = ["平均轮数"] if has_multirun else []
    # 工具调用指标列（放最末，避免打乱既有百分比/色阶列索引）。
    # 仅当存在任一已注册 harness 的有效指标时才追加，避免全 N/A 空列。
    has_tool_metrics = any(u.tool_metrics_total().get("total", 0) for u in units)
    tool_cols = ["工具调用数", "格式准确率", "执行成功率", "不确定占比"] if has_tool_metrics else []
    header = (["模型", "Harness", "总平均分", "用例数", "正常完成数", "执行错误数", "超时数", "完成率"]
              + multirun_cols
              + ["总tokens", "总请求数", "总耗时(s)", "总成本(USD)"]
              + tool_cols)
    ws.append(header)
    for u in units:
        suite_ids = {s: {t.task_id for t in u.tasks if t.suite == s} for s in suites}
        n_total = len(u.tasks)
        # 三态互斥且完备（finished + 非超时执行错误 + 超时 = 用例数）：
        # 超时任务的 execution_status 同时写了 error 字段（"...timed out"），
        # 故执行错误数排除 timed_out，使三列互斥不重复计数。
        n_error = sum(1 for t in u.tasks if t.error_execution and not t.timed_out)
        n_timeout = sum(1 for t in u.tasks if t.timed_out)
        n_finished = n_total - n_error - n_timeout
        finish_rate = round(n_finished / n_total * 100, 1) if n_total else 0.0
        row = [
            u.model, u.harness_label, round(u.total_pct, 1), n_total,
            n_finished, n_error, n_timeout, finish_rate,
        ]
        if has_multirun:
            # 仅平均轮数（跨题平均 std 无统计意义，不展示）
            valid_tasks = [t for t in u.tasks if t.runs > 0]
            avg_runs = sum(t.runs for t in valid_tasks) / len(valid_tasks) if valid_tasks else 0
            row += [round(avg_runs, 1)]
        row += [
            int(u.usage_total("total_tokens")),
            int(u.usage_total("request_count")),
            round(u.usage_total("elapsed_time"), 1),
            round(u.usage_total("cost_usd"), 4),
        ]
        if tool_cols:
            tm = u.tool_metrics_total()
            row += [
                tm.get("total", 0),
                _pct_or_dash(_tm_format_accuracy(tm)),
                _pct_or_dash(_tm_exec_success(tm)),
                _pct_or_dash(_tm_unclear_ratio(tm)),
            ]
        ws.append(row)
        # 百分比列：总平均分(3)、完成率(8)
        pct_cols = [3, 8]
        if tool_cols:
            # 工具指标 3 个比率列（资源列之后，从 tokens/请求数/耗时/成本 再 +1）
            tool_start = 9 + len(multirun_cols) + 4  # 完成率后+multirun+4资源
            pct_cols += [tool_start + 1, tool_start + 2, tool_start + 3]  # 格式/成功/不确定
        apply_pct_format(ws, ws.max_row, pct_cols)
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


# 检查点富文本字体色（语义同能力 Sheet 色阶：0 红 / 部分 黄 / 满分 绿，取文字可读的深色变体）
CKPT_FONT_GREEN = "FF2E7D32"
CKPT_FONT_AMBER = "FFBF8F00"
CKPT_FONT_RED = "FFC00000"


def _ckpt_font_color(v: float) -> str:
    if v >= 1.0 - 1e-9:
        return CKPT_FONT_GREEN
    if v <= 1e-9:
        return CKPT_FONT_RED
    return CKPT_FONT_AMBER


def build_unit_score_cell(t: TaskRecord | None):
    """unit 得分单元格：总分 + 按得分着色的检查点明细（富文本）。"""
    if t is None:
        return "-"
    total = round(t.score, 3) if t.score is not None else "-"
    if not t.checkpoints:  # 单分制（LLM 裁判）或判分失败，无检查点明细
        return f"总分：{total}"
    rt = CellRichText(f"总分：{total}\n检查点得分：\n")
    items = list(t.checkpoints.items())
    for i, (k, v) in enumerate(items):
        line = f"{k}: {v}" + ("" if i == len(items) - 1 else "\n")
        rt.append(TextBlock(InlineFont(color=_ckpt_font_color(v)), line))
    return rt


def write_case_compare_sheet(wb, units: list[UnitResult], order: list[tuple[str, str]],
                             task_meta: dict[str, dict], suite_zh: dict[str, str]) -> None:
    ws = wb.create_sheet("用例对比明细")
    header = (["分类", "用例ID", "用例名称", "难度", "模态", "输入(Prompt)", "预期行为", "评分标准", "检查点"]
              + [f"{u.unit} 得分" for u in units]
              + ["最优单元", "最大分差"])
    ws.append(header)
    n_meta_cols = 9
    for suite, tid in order:
        meta = task_meta.get(tid, {})
        scores = {u.unit: u.task_map[tid].score for u in units if tid in u.task_map}
        valid = {k: v for k, v in scores.items() if v is not None}
        best = max(valid, key=valid.get) if valid else "-"
        spread = round(max(valid.values()) - min(valid.values()), 3) if len(valid) > 1 else "-"
        # 检查点列表由任务定义决定（md 判分代码提取，定义序）；
        # 动态键名（如 f"ordered_match_{i}"）静态解析不到，用各 unit 实测键补全
        ckpt_keys: dict[str, None] = {k: None for k in meta.get("ckpt_keys", [])}
        for u in units:
            t = u.task_map.get(tid)
            if t:
                for k in t.checkpoints:
                    ckpt_keys.setdefault(k)
        if ckpt_keys:
            ckpt_cell = "\n".join(ckpt_keys)
        elif meta.get("checks"):  # 判分代码存在但无明细键 → 单分制（如 LLM 裁判、跑分任务）
            ckpt_cell = "（单分制：判分仅输出 overall_score）"
        else:
            ckpt_cell = "-"
        row = [suite_zh.get(suite, suite), tid, meta.get("name", "-"), meta.get("difficulty", "-"),
               meta.get("modality", "-"), truncate(meta.get("prompt", "")),
               truncate(meta.get("expected", "")), truncate(meta.get("criteria", "")),
               ckpt_cell]
        row += [build_unit_score_cell(u.task_map.get(tid)) for u in units]
        row += [best, spread]
        ws.append(row)
        r = ws.max_row
        for col in list(range(6, n_meta_cols + 1)) + list(range(n_meta_cols + 1, n_meta_cols + 1 + len(units))):
            ws.cell(row=r, column=col).alignment = WRAP_TOP
    style_header_row(ws)
    set_widths(ws, {1: 22, 2: 40, 3: 30, 4: 8, 5: 12, 6: 45, 7: 45, 8: 45, 9: 35,
                    n_meta_cols + 1 + len(units): 26, n_meta_cols + 2 + len(units): 10}, default=34)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}1"


def load_capability_map(explicit: str | None) -> dict[str, dict[str, list[str]]]:
    """加载 {task_id: {checkpoint: [维度...]}} 映射；文件或 pyyaml 缺失时返回空。"""
    path = Path(explicit) if explicit else Path(__file__).resolve().parent.parent / "data" / "checkpoint_capability_map7.yaml"
    if not path.is_file():
        print(f"[警告] 能力映射文件不存在（{path}），跳过 Agent能力对比 Sheet", file=sys.stderr)
        return {}
    try:
        import yaml
    except ImportError:
        print("[警告] 缺少 pyyaml，跳过 Agent能力对比 Sheet（pip install pyyaml）", file=sys.stderr)
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {t: {c: list(dims) for c, dims in (ckpts or {}).items()}
            for t, ckpts in data.items() if isinstance(ckpts, dict)}


def _cap_task_scores(u: UnitResult, cap_map: dict, dim: str, delivered_only: bool) -> list[float]:
    """该 unit 在某维度上的任务级得分列表（任务内映射检查点均值）。"""
    out = []
    for t in u.tasks:
        if not t.checkpoints:
            continue
        if delivered_only:
            file_scores = [v for k, v in t.checkpoints.items() if FILE_CKPT_RE.search(k)]
            if file_scores and sum(file_scores) / len(file_scores) < 0.5:
                continue
        # LLM 裁判单分制任务（如 04 套件）无检查点明细，映射可显式引用 overall_score
        candidates = {
            k: nv for k, v in t.checkpoints.items()
            if (nv := normalize_ckpt_value(k, v, t.checkpoints)) is not None
        }
        if t.score is not None and 0 <= t.score <= 1:
            candidates["overall_score"] = t.score
        mapped = [candidates[c] for c, dims in cap_map.get(t.task_id, {}).items()
                  if dim in dims and c in candidates]
        if mapped:
            out.append(sum(mapped) / len(mapped))
    return out


def write_capability_sheet(wb, units: list[UnitResult], cap_map: dict) -> None:
    from openpyxl.comments import Comment

    # 预先计算每个 unit 的 7 项原始能力分与 3 项去污染分（供两个 Sheet 复用）
    unit_scores: dict[str, dict[str, tuple[float | None, int]]] = {}
    unit_decon: dict[str, dict[str, tuple[float | None, int]]] = {}
    for u in units:
        scores: dict[str, tuple[float | None, int]] = {}
        for d in CAP7_ORDER:
            vals = _cap_task_scores(u, cap_map, d, delivered_only=False)
            scores[d] = (sum(vals) / len(vals) * 100 if vals else None, len(vals))
        unit_scores[u.unit] = scores
        decon: dict[str, tuple[float | None, int]] = {}
        for d in CAP7_DECON:
            vals = _cap_task_scores(u, cap_map, d, delivered_only=True)
            decon[d] = (sum(vals) / len(vals) * 100 if vals else None, len(vals))
        unit_decon[u.unit] = decon

    # ---- Sheet 1：7 项原始能力（不去污染）+ 强项/短板 ----
    ws = wb.create_sheet("Agent能力对比", index=3)  # 紧跟用例对比明细之后
    header = (["模型@Harness", "总平均分"]
              + [f"{CAP7_ZH[d]}" for d in CAP7_ORDER]
              + ["模型强项", "模型短板"])
    ws.append(header)
    n_dims = len(CAP7_ORDER)
    for u in units:
        scores = unit_scores[u.unit]
        row = [u.unit, round(u.total_pct, 1)]
        row += [round(scores[d][0], 1) if scores[d][0] is not None else "-" for d in CAP7_ORDER]
        ranked = sorted((d for d in CAP7_ORDER
                         if scores[d][0] is not None and scores[d][1] >= CAP_RANK_MIN_COUNT),
                        key=lambda d: scores[d][0], reverse=True)
        fmt_rank = lambda ds: "\n".join(f"{CAP7_ZH[d]} {scores[d][0]:.1f}%" for d in ds) or "-"
        row += [fmt_rank(ranked[:3]), fmt_rank(list(reversed(ranked[-3:])))]
        ws.append(row)
        r = ws.max_row
        apply_pct_format(ws, r, range(2, 3 + n_dims))
        for i, d in enumerate(CAP7_ORDER):
            ws.cell(row=r, column=3 + i).comment = Comment(f"涉及 {scores[d][1]} 例", "report")
        for col in (3 + n_dims, 4 + n_dims):
            ws.cell(row=r, column=col).alignment = WRAP_TOP
    style_header_row(ws)
    set_widths(ws, {1: 28, 2: 12, 3 + n_dims: 24, 4 + n_dims: 24}, default=17)
    ws.freeze_panes = "C2"
    add_color_scale(ws, 2, ws.max_row, 2, 2 + n_dims)

    # ---- Sheet 2：仅 3 项去落盘污染能力 ----
    ws2 = wb.create_sheet("Agent能力对比·去污染", index=4)
    header2 = (["模型@Harness", "总平均分"]
               + [f"{CAP7_ZH[d]}·去落盘污染" for d in CAP7_DECON])
    ws2.append(header2)
    n_decon = len(CAP7_DECON)
    for u in units:
        decon = unit_decon[u.unit]
        row = [u.unit, round(u.total_pct, 1)]
        row += [round(decon[d][0], 1) if decon[d][0] is not None else "-" for d in CAP7_DECON]
        ws2.append(row)
        r = ws2.max_row
        apply_pct_format(ws2, r, range(2, 3 + n_decon))
        for i, d in enumerate(CAP7_DECON):
            ws2.cell(row=r, column=3 + i).comment = Comment(
                f"涉及 {decon[d][1]} 例（仅产物落盘成功的用例）", "report")
    style_header_row(ws2)
    set_widths(ws2, {1: 28, 2: 12}, default=20)
    ws2.freeze_panes = "C2"
    add_color_scale(ws2, 2, ws2.max_row, 2, 2 + n_decon)

    # 覆盖率告警：实测检查点未被映射的
    unmapped = set()
    for u in units:
        for t in u.tasks:
            known = cap_map.get(t.task_id, {})
            if "overall_score" in known:  # 单分制任务不要求逐检查点覆盖
                continue
            unmapped |= {f"{t.task_id}.{c}" for c in t.checkpoints
                         if c not in known and not METRIC_CKPT_RE.search(c)}
    if unmapped:
        print(f"[警告] {len(unmapped)} 个实测检查点未被能力映射覆盖（不计入能力得分），"
              f"示例：{sorted(unmapped)[:5]}", file=sys.stderr)


def write_dimension_sheet_transposed(wb, title: str, units: list[UnitResult],
                                     groups: list[tuple[str, set[str]]]) -> None:
    """转置维度对比：行=unit（按总平均分降序），列=维度取值（表头带用例数）。

    分类/难度/模态三张对比表统一用此布局：第 1 列模型@Harness、第 2 列总平均分，
    其后每个维度取值一列，列头形如 `<取值>平均分(N例)`。
    """
    ws = wb.create_sheet(title)
    groups = [(label, ids) for label, ids in groups if ids]
    ws.append(["模型@Harness", "总平均分"]
              + [f"{label}平均分({len(ids)}例)" for label, ids in groups])
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


def write_tool_compare_sheet(wb, units: list[UnitResult]) -> None:
    """工具调用对比：按 harness 分块，块内每行 = 模型 × 工具名。

    列：模型 / 工具 / 调用数 / 成功 / 失败 / 不确定 / 格式错误 / 成功率 / 格式准确率。
    仅纳入已注册（有有效指标）的 harness；无任何有效指标则不建表。
    区分模型：同 harness 下不同模型的工具画像差异大（有的用 shell、有的用
    exec_command），逐模型展示才能定位某模型在某工具上的系统性失败。
    见 docs/local/design/Harness工具调用指标设计.md §6.4。
    """
    # 按 harness 分组，仅保留有工具调用记录的 unit
    from collections import OrderedDict
    by_harness: "OrderedDict[str, list[UnitResult]]" = OrderedDict()
    for u in units:
        if u.tool_metrics_total().get("total", 0):
            by_harness.setdefault(u.harness, []).append(u)
    if not by_harness:
        return  # 无任何已注册 harness 的有效指标（如仅 openclaw/hermes）

    ws = wb.create_sheet("工具调用对比", index=2)  # 紧跟模型×Harness矩阵之后
    header = ["模型", "工具", "调用数", "成功", "失败", "不确定", "格式错误",
              "成功率", "格式准确率"]
    section_fill = PatternFill("solid", fgColor="D9E1F2")
    # 模型行底色：浅灰/浅蓝交替，比表头淡，用于区分同 harness 下不同模型
    model_fills = [
        PatternFill("solid", fgColor="F2F2F2"),  # 浅灰
        PatternFill("solid", fgColor="E7F3FF"),  # 浅蓝
    ]

    for harness, hunits in by_harness.items():
        # harness 分节标题行（合并首列展示）
        ws.append([f"【Harness: {harness}】"] + [""] * (len(header) - 1))
        sec_row = ws.max_row
        for cell in ws[sec_row]:
            cell.fill = section_fill
            cell.font = Font(bold=True)
        # 列名行
        ws.append(header)
        style_header_row_at(ws, ws.max_row)

        # 每个 unit（模型）：先总计行，再按调用数降序的各工具行
        for idx, u in enumerate(hunits):
            fill = model_fills[idx % len(model_fills)]
            tm = u.tool_metrics_total()
            start_row = ws.max_row + 1
            _append_tool_row(ws, u.model, "（全部工具）", tm, bold=True)
            by_tool = tm.get("by_tool", {})
            for tool_name in sorted(by_tool, key=lambda k: -by_tool[k]["total"]):
                _append_tool_row(ws, u.model, tool_name, by_tool[tool_name])
            # 给这个模型的所有行（总计+各工具）加底色
            for row_idx in range(start_row, ws.max_row + 1):
                for cell in ws[row_idx]:
                    cell.fill = fill
        ws.append([""] * len(header))  # 块间空行

    set_widths(ws, {1: 24, 2: 22}, default=12)
    ws.freeze_panes = "A1"


def _append_tool_row(ws, model: str, tool_name: str, m: dict, bold: bool = False) -> None:
    """向工具对比表追加一行（成功率=综合成功率，格式准确率单列）。"""
    ws.append([
        model, tool_name, m.get("total", 0), m.get("success", 0),
        m.get("failure", 0), m.get("unclear", 0), m.get("format_error", 0),
        _pct_or_dash(_tm_overall_success(m)),
        _pct_or_dash(_tm_format_accuracy(m)),
    ])
    apply_pct_format(ws, ws.max_row, [8, 9])
    # 统一居中对齐(否则文本列左对齐、数字列右对齐，参差不齐)
    for cell in ws[ws.max_row]:
        cell.alignment = CENTER
        if bold:
            cell.font = Font(bold=True)


def style_header_row_at(ws, row: int) -> None:
    """对指定行应用表头样式（用于同 Sheet 内多个子表头）。"""
    for cell in ws[row]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER


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


def _write_stability_distributions(ws, units, mtasks, high_std: float) -> None:
    """std 分布 + pass@k/pass^k 分布（各区间题数与占比）。"""
    def dist_row(vals, edges):
        # edges 如 [0, 0.05, 0.15, 1.01]，返回各桶计数
        buckets = [0] * (len(edges) - 1)
        for v in vals:
            for i in range(len(edges) - 1):
                if edges[i] <= v < edges[i + 1]:
                    buckets[i] += 1
                    break
        return buckets

    ws.append([])
    ws.append(["【std 分布】（跨题聚合无意义，故看分布：低=稳定 / 高=抖动）"])
    ws.append(["模型@Harness", "std[0,0.05] 稳定", "std[0.05,0.15] 中抖", "std[0.15,1] 高抖"])
    hdr = ws.max_row
    for u in units:
        mt = mtasks(u)
        if not mt:
            continue
        b = dist_row([t.std or 0 for t in mt], [0, 0.05, high_std, 1.01])
        n = len(mt)
        ws.append([u.unit] + [f"{c} ({c/n*100:.0f}%)" for c in b])
    style_row(ws, hdr)

    ws.append([])
    ws.append(["【pass@k 分布】能力上界：k 次至少成功一次的概率（越高越有潜力攻克）"])
    ws.append(["模型@Harness", "pass@k[0.95,1] 优", "pass@k[0.8,0.95) 良", "pass@k[0,0.8) 弱"])
    hdr = ws.max_row
    for u in units:
        mt = [t for t in mtasks(u) if t.pass_at_k is not None]
        if not mt:
            continue
        b = dist_row([t.pass_at_k for t in mt], [0, 0.8, 0.95, 1.01])
        n = len(mt)
        # 注意桶顺序：[0,0.8)/[0.8,0.95)/[0.95,1]，展示时倒序为 优/良/弱
        ws.append([u.unit, f"{b[2]} ({b[2]/n*100:.0f}%)",
                   f"{b[1]} ({b[1]/n*100:.0f}%)", f"{b[0]} ({b[0]/n*100:.0f}%)"])
    style_row(ws, hdr)

    ws.append([])
    ws.append(["【pass^k 分布】可靠性下界：连续 k 次全部成功的概率（越高越可稳定交付）"])
    ws.append(["模型@Harness", "pass^k[0.8,1] 优", "pass^k[0.5,0.8) 中", "pass^k[0,0.5) 差"])
    hdr = ws.max_row
    for u in units:
        mt = [t for t in mtasks(u) if t.pass_hat_k is not None]
        if not mt:
            continue
        b = dist_row([t.pass_hat_k for t in mt], [0, 0.5, 0.8, 1.01])
        n = len(mt)
        ws.append([u.unit, f"{b[2]} ({b[2]/n*100:.0f}%)",
                   f"{b[1]} ({b[1]/n*100:.0f}%)", f"{b[0]} ({b[0]/n*100:.0f}%)"])
    style_row(ws, hdr)


def _write_stability_high_std_detail(ws, units, mtasks, task_meta, suite_zh, high_std: float) -> None:
    """高抖题明细：std>阈值的题逐条列出（跨所有 unit，按 std 降序）。"""
    ws.append([])
    ws.append([f"【高抖题明细】std>{high_std} 的用例（按 std 降序；结合难度判断是难题固有抖动还是模型不稳）"])
    ws.append(["模型@Harness", "分类", "用例ID", "难度", "轮数", "mean", "std",
               "各轮分数", "pass@k", "pass^k"])
    hdr = ws.max_row
    rows = []
    for u in units:
        for t in mtasks(u):
            if (t.std or 0) > high_std:
                meta = task_meta.get(t.task_id, {})
                rows.append((
                    (t.std or 0), u.unit, suite_zh.get(t.suite, t.suite), t.task_id,
                    meta.get("difficulty", "-"), t.runs, round(t.score, 3), round(t.std, 3),
                    ", ".join(str(round(s, 3)) for s in t.all_scores),
                    round(t.pass_at_k, 3) if t.pass_at_k is not None else "-",
                    round(t.pass_hat_k, 3) if t.pass_hat_k is not None else "-",
                ))
    rows.sort(key=lambda r: -r[0])  # std 降序
    for r in rows:
        ws.append(list(r[1:]))  # 去掉排序键
    if not rows:
        ws.append(["（无高抖题：所有多轮用例 std 均 ≤ 阈值，稳定性良好）"])
    style_row(ws, hdr)


def write_stability_sheet(wb, units: list[UnitResult],
                          task_meta: dict[str, dict], suite_zh: dict[str, str]) -> None:
    """多轮稳定性分析 Sheet（仅在有多轮数据时生成）。

    std/pass@k/pass^k 跨题聚合无统计意义，故用「分布统计」而非「平均值」呈现：
    - 第1部分 模型宏观对比：高抖题数/不稳定率 + 能力上界/可靠性优秀率
    - 第2部分 std 分布：各 std 区间的题数占比
    - 第3部分 pass@k/pass^k 分布：能力上界/可靠性下界的分层
    - 第4部分 高抖题明细：std>0.15 的题逐条列出（含各轮分数）
    """
    if not any(t.runs > 1 for u in units for t in u.tasks):
        return  # 无多轮数据，不生成
    ws = wb.create_sheet("多轮稳定性分析", index=1)  # 紧跟总览
    HIGH_STD = 0.15  # 高抖动阈值

    def mtasks(u):  # 该 unit 的多轮任务
        return [t for t in u.tasks if t.runs > 1]

    # ---- 第 1 部分：模型宏观对比 ----
    ws.append(["【模型宏观对比】"])
    ws.append(["模型@Harness", "轮数", "多轮题数", "高抖题数(std>0.15)", "不稳定率",
               "pass@k≥0.95题数", "能力上界优秀率", "pass^k≥0.8题数", "可靠性优秀率"])
    for u in units:
        mt = mtasks(u)
        if not mt:
            continue
        n = len(mt)
        runs = max((t.runs for t in mt), default=0)
        high_std = sum(1 for t in mt if (t.std or 0) > HIGH_STD)
        pak_good = sum(1 for t in mt if t.pass_at_k is not None and t.pass_at_k >= 0.95)
        phk_good = sum(1 for t in mt if t.pass_hat_k is not None and t.pass_hat_k >= 0.8)
        ws.append([
            u.unit, runs, n, high_std, round(high_std / n * 100, 1),
            pak_good, round(pak_good / n * 100, 1),
            phk_good, round(phk_good / n * 100, 1),
        ])
        apply_pct_format(ws, ws.max_row, [5, 7, 9])
    style_row(ws, 2)

    _write_stability_distributions(ws, units, mtasks, HIGH_STD)
    _write_stability_high_std_detail(ws, units, mtasks, task_meta, suite_zh, HIGH_STD)
    set_widths(ws, {1: 30, 2: 8, 3: 10, 4: 18, 5: 12, 6: 16, 7: 14, 8: 16, 9: 14}, default=14)


def write_detail_sheet(wb, u: UnitResult, order: list[tuple[str, str]],
                       task_meta: dict[str, dict], analysis: dict[str, dict],
                       suite_zh: dict[str, str], has_multirun: bool = False) -> None:
    ws = wb.create_sheet(f"评分详情_{u.unit}"[:31])
    # 多轮列仅在存在多轮数据时插入（单轮评测报告结构与改造前完全一致）
    mr_cols = ["轮数", "Std", "各轮分数"] if has_multirun else []
    header = (["分类", "用例ID", "用例名称", "难度", "超时时间(秒)", "模态",
               "输入(Prompt)", "预期行为", "评分标准", "Automated Checks",
               "工作目录(Workspace)", "预置技能(Skills)", "环境变量(Env)", "预热(Warmup)",
               "状态", "总得分"]
              + mr_cols
              + ["检查点得分明细", "失分点", "裁判判词", "执行错误",
                 "总tokens", "请求数", "耗时(s)", "执行记录(jsonl)", "结果分析", "根因分析"]
              + ["工具调用数", "格式准确率", "执行成功率", "不确定占比"])
    ws.append(header)
    # 自动换行列：按是否有多轮列动态偏移（多轮列占 3 列，之后的列右移 3）
    off = len(mr_cols)  # 0 或 3
    wrap_cols = {7, 8, 9, 10, 12, 14}
    if has_multirun:
        wrap_cols.add(19)  # 各轮分数列
    wrap_cols |= {17 + off, 18 + off, 19 + off, 20 + off, 24 + off, 25 + off, 26 + off}
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

        # 多轮列（仅 has_multirun 时插入）：轮数/Std/各轮分数
        mr_cells = []
        if has_multirun:
            std_display = round(t.std, 3) if t.std is not None and t.runs > 1 else "-"
            all_scores_display = (
                ", ".join(str(round(s, 3)) for s in t.all_scores)
                if len(t.all_scores) > 1 else "-"
            )
            mr_cells = [t.runs if t.runs > 0 else 1, std_display, all_scores_display]

        ws.append([
            suite_zh.get(suite, suite), tid, meta.get("name", "-"),
            meta.get("difficulty", "-"), meta.get("timeout_seconds", "-"),
            meta.get("modality", "-"),
            truncate(meta.get("prompt", "")), truncate(meta.get("expected", "")),
            truncate(meta.get("criteria", "")), truncate(meta.get("checks", "")),
            strip_code_fence(meta.get("workspace", "")) or "-",
            strip_code_fence(meta.get("skills", "")) or "-",
            strip_code_fence(meta.get("env", "")) or "-",
            strip_code_fence(meta.get("warmup", "")) or "-",
            (t.status or "-") + ("（超时）" if t.timed_out else ""),
            round(t.score, 3) if t.score is not None else "-",
            *mr_cells,  # 多轮列（单轮时为空，结构不变）
            format_breakdown(t), format_lost_points(t),
            truncate(t.judge_notes) or "-", truncate(err),
            int((t.usage or {}).get("total_tokens", 0)),
            int((t.usage or {}).get("request_count", 0)),
            round(t.elapsed, 1) if isinstance(t.elapsed, (int, float)) else "-",
            truncate(read_transcript_raw(t.transcript)),
            truncate(item.get("result_analysis", "") or ""),
            truncate(item.get("root_cause_analysis", "") or item.get("root_cause", "") or ""),
            t.tool_metrics.get("total", 0),
            _pct_or_dash(_tm_format_accuracy(t.tool_metrics)),
            _pct_or_dash(_tm_exec_success(t.tool_metrics)),
            _pct_or_dash(_tm_unclear_ratio(t.tool_metrics)),
        ])
        # 工具指标 3 个比率列（末尾 4 列的后 3 列）应用百分比格式
        _tm_last = ws.max_column
        apply_pct_format(ws, ws.max_row, [_tm_last - 2, _tm_last - 1, _tm_last])
        for col in wrap_cols:
            ws.cell(row=ws.max_row, column=col).alignment = WRAP_TOP
    style_header_row(ws)
    # 列宽：前 16 列固定；多轮 3 列（17/18/19）仅 has_multirun 时存在；其后列按 off 偏移
    widths = {1: 18, 2: 40, 3: 30, 4: 8, 5: 12, 6: 12,
              7: 45, 8: 45, 9: 45, 10: 45,
              11: 38, 12: 20, 13: 20, 14: 30,
              15: 14, 16: 8}  # 状态、总得分
    if has_multirun:
        widths.update({17: 6, 18: 8, 19: 20})  # 轮数、Std、各轮分数
    # 检查点明细、失分点、判词、执行错误、tokens、请求数、耗时、执行记录、结果分析、根因分析
    for base, w in {17: 40, 18: 40, 19: 45, 20: 40, 21: 12, 22: 8, 23: 8, 24: 60, 25: 45, 26: 40}.items():
        widths[base + off] = w
    set_widths(ws, widths)
    ws.freeze_panes = "C2"


# ===========================================================================
# Summary JSON / Markdown / HTML 产出（供 --emit）
# ===========================================================================

def _build_dim_comparison(
    units: list[UnitResult],
    task_meta: dict[str, dict],
    dim_field: str,
    order: list[str],
) -> list[dict]:
    """按某维度（category/difficulty/modality）聚合各 unit 的平均分。"""
    dim_to_tasks: dict[str, set[str]] = {}
    for tid, meta in task_meta.items():
        val = meta.get(dim_field)
        if val:
            dim_to_tasks.setdefault(val, set()).add(tid)

    # 按给定顺序排列，未知值追加到末尾
    known_vals = [v for v in order if v in dim_to_tasks]
    unknown_vals = sorted(v for v in dim_to_tasks if v not in order)
    ordered_vals = known_vals + unknown_vals

    rows = []
    for val in ordered_vals:
        task_ids = dim_to_tasks[val]
        row = {
            "name": val,
            "task_count": len(task_ids),
            "scores": {},  # unit → 平均分（百分制）
        }
        for u in units:
            avg = u.avg_pct(task_ids)
            if avg is not None:
                row["scores"][u.unit] = round(avg, 1)
        rows.append(row)
    return rows


def build_summary(
    units: list[UnitResult],
    task_meta: dict[str, dict],
    cap_map: dict[str, dict[str, list[str]]],
    suite_zh: dict[str, str],
    analysis_by_unit: dict[str, dict],
    task_order: list[tuple[str, str]],
) -> dict:
    """组装 summary JSON，章节与 Excel Sheet 一一对应。

    返回结构：
    - units: 单元标签列表（与 scores_by_unit 位置数组同序）
    - overview: 总览指标
    - unit_summaries: 各单元汇总（对应「总览」Sheet）
    - case_comparisons: 用例对比明细（对应「用例对比明细」Sheet）
    - capability_comparison: 7维能力对比（对应「Agent能力对比」Sheet）
    - dimension_comparisons: 分类/难度/模态对比（对应「分类/难度/模态」Sheet）
    - score_matrix: 模型×Harness 得分矩阵
    - diff_matrix: 分差矩阵
    - root_cause_summary: 根因分析统计
    - recommendations: 改进建议
    """
    # 各 unit 按套件分类的均分
    suites = sorted({suite for suite, _ in task_order})
    category_scores = {}
    for suite in suites:
        task_ids = {tid for s, tid in task_order if s == suite}
        category_scores[suite] = {
            u.unit: u.avg_pct(task_ids) for u in units
        }

    # run_summaries（对应「总览」Sheet，字段名对齐前端）
    run_summaries = []
    for u in units:
        # 多轮聚合：该 unit 内所有多轮任务的 pass@k/pass^k 平均；max_runs 标识是否多轮
        pass_at_k_vals = [t.pass_at_k for t in u.tasks if t.pass_at_k is not None]
        pass_hat_k_vals = [t.pass_hat_k for t in u.tasks if t.pass_hat_k is not None]
        max_runs = max((t.runs for t in u.tasks), default=0)
        run_summaries.append({
            "run_label": u.unit,  # 前端期望 run_label
            "model": u.model,
            "harness": u.harness,
            "average_score": round(u.total_pct / 100, 4),  # 前端期望 0-1 范围
            "category_scores": {
                suite_zh.get(suite, suite): round(score / 100, 4) if score is not None else None
                for suite, scores in category_scores.items()
                for unit, score in scores.items()
                if unit == u.unit
            },
            "total_tokens": int(u.usage_total("total_tokens")),
            "cost_usd": round(u.usage_total("cost_usd"), 4),
            "elapsed_time": round(u.usage_total("elapsed_time"), 1),
            "request_count": int(u.usage_total("request_count")),
            # 与总览 Sheet 一致：排除超时（超时任务也写了 execution error 字段），
            # 使 error_count 与 timeout_count 互斥。
            "error_count": sum(
                1 for t in u.tasks
                if (t.error_grading or t.error_execution) and not t.timed_out
            ),
            "timeout_count": sum(1 for t in u.tasks if t.timed_out),
            "max_runs": max_runs,
            "avg_pass_at_k": (
                round(sum(pass_at_k_vals) / len(pass_at_k_vals), 4)
                if pass_at_k_vals else None
            ),
            "avg_pass_hat_k": (
                round(sum(pass_hat_k_vals) / len(pass_hat_k_vals), 4)
                if pass_hat_k_vals else None
            ),
        })

    # case_comparisons（对应「用例对比明细」Sheet）
    case_comparisons = []
    for suite, tid in task_order:
        meta = task_meta.get(tid, {})
        scores_by_unit = []
        for u in units:
            t = u.task_map.get(tid)
            scores_by_unit.append(t.score if t and t.score is not None else None)

        valid_scores = [s for s in scores_by_unit if s is not None]

        # 构建前端期望的 results 对象数组格式（含多轮统计）
        results = []
        for i, u in enumerate(units):
            score = scores_by_unit[i]
            t = u.task_map.get(tid)
            results.append({
                "run_label": u.unit,
                "average_score": score,
                "runs": t.runs if t else 0,
                "std": t.std if t else None,
                "pass_at_k": t.pass_at_k if t else None,
                "pass_hat_k": t.pass_hat_k if t else None,
                "round_scores": t.all_scores if t else [],
            })

        case_comparisons.append({
            "case_task_id": tid,
            "case_name": meta.get("name", ""),
            "suite": suite,
            "suite_zh": suite_zh.get(suite, suite),
            "category": suite_zh.get(suite, suite),
            "difficulty": meta.get("difficulty", ""),
            "modality": meta.get("modality", ""),
            "results": results,  # 前端期望的对象数组
            "best_score": max(valid_scores) if valid_scores else None,
            "score_gap": round((max(valid_scores) - min(valid_scores)), 4) if len(valid_scores) > 1 else None,
        })

    # capability_comparison（对应「Agent能力对比」Sheet，7维）
    capability_comparison = {
        "dimensions": [{"code": d, "label": CAP7_ZH[d]} for d in CAP7_ORDER],
        "rows": [],
    }
    for u in units:
        dim_scores = {}
        for dim in CAP7_ORDER:
            scores = _cap_task_scores(u, cap_map, dim, delivered_only=False)
            dim_scores[dim] = round(sum(scores) / len(scores), 4) if scores else None
        capability_comparison["rows"].append({
            "run_label": u.unit,
            "dim_scores": dim_scores,
        })

    # dimension_comparisons（对应「分类/难度/模态」Sheet）
    dimension_comparisons = {
        "category": _build_dim_comparison(units, task_meta, "category", sorted(suites)),
        "difficulty": _build_dim_comparison(units, task_meta, "difficulty", DIFFICULTY_ORDER),
        "modality": _build_dim_comparison(units, task_meta, "modality", MODALITY_ORDER),
    }

    # score_matrix 和 diff_matrix（对应「模型×Harness 矩阵」和「分差矩阵」Sheet）
    score_matrix = [[round(u.total_pct, 1) for u in units] for _ in units]
    diff_matrix = []
    for i, u_a in enumerate(units):
        row = []
        for u_b in units:
            row.append(0.0 if u_a is u_b else round(u_a.total_pct - u_b.total_pct, 1))
        diff_matrix.append(row)

    # root_cause_summary（前端期望 {completed_count, items[]}）+ recommendations 汇总。
    # analysis_by_unit 的 key 为 "<unit>::<task_id>"，value 为
    # {result_analysis, root_cause_analysis}（backend 已把 summary/root_causes/
    # recommendations 规整并折叠进这两个字符串字段）。
    unit_map = {u.unit: u for u in units}
    rc_items = []
    rec_lines: list[str] = []
    for full_key, ana_data in analysis_by_unit.items():
        if not isinstance(ana_data, dict) or "::" not in full_key:
            continue
        unit, task_id = full_key.split("::", 1)
        result_analysis = (ana_data.get("result_analysis", "") or "").strip()
        root_cause_text = (
            ana_data.get("root_cause_analysis", "")
            or ana_data.get("root_cause", "")
            or ""
        ).strip()
        if not result_analysis and not root_cause_text:
            continue
        # root_cause_analysis 已是多行文本（含「改进建议：」分隔），按行拆分回列表；
        # 「改进建议：」之后的行归入 recommendations。
        root_causes: list[str] = []
        recommendations_item: list[str] = []
        in_rec = False
        for line in root_cause_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("改进建议"):
                in_rec = True
                continue
            (recommendations_item if in_rec else root_causes).append(line)
        rec_lines.extend(recommendations_item)
        task_record = unit_map.get(unit, {})
        score = None
        if task_record and hasattr(task_record, "task_map"):
            tr = task_record.task_map.get(task_id)
            score = tr.score if tr else None
        rc_items.append({
            "task_run_id": unit,  # 无数值 run_id，用 unit 标签作稳定 key
            "case_task_id": task_id,
            "run_label": unit,
            "average_score": score,
            "summary": result_analysis,
            "root_causes": root_causes,
            "recommendations": recommendations_item,
        })
    root_cause_summary = {
        "completed_count": len(rc_items),
        "items": rc_items,
    }
    # 顶层 recommendations 去重保序
    recommendations = list(dict.fromkeys(rec_lines))

    # 用例交集对齐信息（参考 PinchBench）
    case_sets = [set(u.task_map.keys()) for u in units]
    intersection = set.intersection(*case_sets) if case_sets else set()
    aligned = all(len(s) == len(intersection) for s in case_sets) if case_sets else True

    return {
        "units": [u.unit for u in units],  # 位置数组基准
        "overview": {
            "unit_count": len(units),
            "total_tasks": len(task_order),
            "average_score": round(sum(u.total_pct for u in units) / len(units) / 100, 4) if units else 0.0,
            "pass_threshold": PASS_THRESHOLD_DISPLAY,
        },
        "run_summaries": run_summaries,
        "case_comparisons": case_comparisons,
        "capability_comparison": capability_comparison,
        "dimension_comparisons": dimension_comparisons,
        "score_matrix": score_matrix,
        "diff_matrix": diff_matrix,
        "alignment": {
            "runs": [{"label": u.unit, "case_count": len(u.task_map)} for u in units],
            "intersection_count": len(intersection),
            "aligned": aligned,
        },
        "root_cause_summary": root_cause_summary,
        "recommendations": recommendations,
    }


def _md_table(headers: list[str], rows: list[list]) -> str:
    """生成 Markdown 表格。"""
    lines = []
    lines.append("| " + " | ".join(str(h) for h in headers) + " |")
    lines.append("|" + "---|" * len(headers))
    for row in rows:
        lines.append("| " + " | ".join(str(cell) if cell is not None else "-" for cell in row) + " |")
    return "\n".join(lines)



def render_markdown(summary: dict) -> str:
    """从 summary JSON 渲染 Markdown 报告。"""
    lines = []
    lines.append(f"# WildClawBench 评测报告")
    lines.append("")
    lines.append(f"**单元数**: {summary['overview']['unit_count']}  ")
    lines.append(f"**总任务数**: {summary['overview']['total_tasks']}  ")
    lines.append(f"**平均分**: {summary['overview']['average_score']*100:.1f}%")
    lines.append("")

    # 单元汇总
    lines.append("## 单元汇总")
    lines.append("")
    lines.append("| 单元 | 平均分 | Tokens | 成本($) | 错误 | 超时 |")
    lines.append("|------|--------|--------|---------|------|------|")
    for item in summary["run_summaries"]:
        lines.append(
            f"| {item['run_label']} | {item['average_score']*100:.1f}% | "
            f"{item['total_tokens']:,} | {item['cost_usd']:.4f} | "
            f"{item['error_count']} | {item['timeout_count']} |"
        )
    lines.append("")

    # 用例对比明细（简化版，仅展示部分列）
    lines.append("## 用例对比明细")
    lines.append("")
    run_labels = [item['run_label'] for item in summary["run_summaries"]]
    lines.append("| 用例ID | 难度 | 最优分 | 分差 | " + " | ".join(run_labels) + " |")
    lines.append("|" + "---|" * (4 + len(run_labels)))
    for case in summary["case_comparisons"]:
        scores_str = " | ".join(
            f"{r['average_score']*100:.1f}%" if r['average_score'] is not None else "-"
            for r in case["results"]
        )
        gap_str = f"{case['score_gap']*100:.1f}%" if case['score_gap'] is not None else "-"
        best_str = f"{case['best_score']*100:.1f}%" if case['best_score'] is not None else "-"
        lines.append(
            f"| {case['case_task_id']} | {case['difficulty']} | "
            f"{best_str} | {gap_str} | {scores_str} |"
        )
    lines.append("")

    # Agent能力对比
    cap = summary.get("capability_comparison", {})
    if cap.get("dimensions"):
        lines.append("## Agent能力对比")
        lines.append("")
        headers = ["单元"] + [f"{d['label']}" for d in cap["dimensions"]]
        rows = []
        for r in cap.get("rows", []):
            row = [r["run_label"]]
            for d in cap["dimensions"]:
                v = r["dim_scores"].get(d["code"])
                row.append(f"{v*100:.1f}%" if v is not None else "-")
            rows.append(row)
        lines.append(_md_table(headers, rows))
        lines.append("")

    # 分类/难度/模态对比
    for title, key in [("分类对比", "category"), ("难度对比", "difficulty"), ("模态对比", "modality")]:
        dim_data = summary.get("dimension_comparisons", {}).get(key, [])
        if dim_data:
            lines.append(f"## {title}")
            lines.append("")

            # 难度对比特殊处理：转置为模型×难度（参考 PinchBench）
            if key == "difficulty":
                headers = ["模型"] + [f"{d['name']}(用例数{d['task_count']})" for d in dim_data]
                rows = []
                for label in run_labels:
                    row = [label]
                    for d in dim_data:
                        v = d["scores"].get(label)
                        row.append(f"{v:.1f}%" if v is not None else "-")
                    rows.append(row)
                lines.append(_md_table(headers, rows))
            else:
                # 分类/模态：维度×模型（原逻辑）
                headers = ["名称", "任务数"] + run_labels
                rows = []
                for d in dim_data:
                    row = [d["name"], d["task_count"]]
                    for label in run_labels:
                        v = d["scores"].get(label)
                        row.append(f"{v:.1f}%" if v is not None else "-")
                    rows.append(row)
                lines.append(_md_table(headers, rows))
            lines.append("")

    # 分差矩阵
    diff = summary.get("diff_matrix", [])
    if diff:
        lines.append("## 分差矩阵")
        lines.append("")
        headers = ["行单元 - 列单元"] + run_labels
        rows = []
        for i, row_vals in enumerate(diff):
            row = [run_labels[i]] + [f"{v:+.1f}%" for v in row_vals]
            rows.append(row)
        lines.append(_md_table(headers, rows))
        lines.append("")

    return "\n".join(lines)


def render_html(summary: dict) -> str:
    """从 summary JSON 渲染自包含 HTML 报告。"""
    run_labels = [item['run_label'] for item in summary["run_summaries"]]

    def pct01(v):
        """0-1 分数格式化为百分比（None → '-'）。"""
        return f"{v*100:.1f}%" if v is not None else "-"

    def pct100(v):
        """已是百分制的分数格式化（None → '-'）。"""
        return f"{v:.1f}%" if v is not None else "-"

    # 单元汇总表
    unit_rows = "".join(
        f"<tr><td>{item['run_label']}</td><td>{pct01(item['average_score'])}</td>"
        f"<td>{item['total_tokens']:,}</td><td>{item['cost_usd']:.4f}</td>"
        f"<td>{item['error_count']}</td><td>{item['timeout_count']}</td></tr>"
        for item in summary["run_summaries"]
    )

    # 用例对比明细表
    units_th = "".join(f"<th>{label}</th>" for label in run_labels)
    case_rows = "".join(
        f"<tr><td>{case['case_task_id']}</td><td>{case['difficulty']}</td>"
        f"<td>{pct01(case['best_score'])}</td>"
        f"<td>{pct01(case['score_gap'])}</td>"
        + "".join(f"<td>{pct01(r['average_score'])}</td>" for r in case["results"])
        + "</tr>"
        for case in summary["case_comparisons"]
    )

    # Agent能力对比表
    cap = summary.get("capability_comparison", {})
    cap_section = ""
    if cap.get("dimensions"):
        cap_headers = "".join(f"<th>{d['label']}</th>" for d in cap["dimensions"])
        cap_rows = "".join(
            f"<tr><td>{r['run_label']}</td>"
            + "".join(f"<td>{pct01(r['dim_scores'].get(d['code']))}</td>"
                      for d in cap["dimensions"])
            + "</tr>"
            for r in cap.get("rows", [])
        )
        cap_section = f"""
<h2>Agent能力对比</h2>
<table><thead><tr><th>单元</th>{cap_headers}</tr></thead>
<tbody>{cap_rows}</tbody></table>"""

    # 分类/难度/模态对比表
    dim_sections = ""
    for title, key in [("分类对比", "category"), ("难度对比", "difficulty"), ("模态对比", "modality")]:
        dim_data = summary.get("dimension_comparisons", {}).get(key, [])
        if dim_data:
            # 难度对比特殊处理：转置为模型×难度
            if key == "difficulty":
                diff_headers = "".join(f"<th>{d['name']}(用例数{d['task_count']})</th>" for d in dim_data)
                diff_rows = "".join(
                    f"<tr><td>{label}</td>"
                    + "".join(f"<td>{pct100(d['scores'].get(label))}</td>" for d in dim_data)
                    + "</tr>"
                    for label in run_labels
                )
                dim_sections += f"""
<h2>{title}</h2>
<table><thead><tr><th>模型</th>{diff_headers}</tr></thead>
<tbody>{diff_rows}</tbody></table>"""
            else:
                # 分类/模态：维度×模型（原逻辑）
                dim_headers = "".join(f"<th>{label}</th>" for label in run_labels)
                dim_rows = "".join(
                    f"<tr><td>{d['name']}</td><td>{d['task_count']}</td>"
                    + "".join(f"<td>{pct100(d['scores'].get(label))}</td>"
                              for label in run_labels)
                    + "</tr>"
                    for d in dim_data
                )
                dim_sections += f"""
<h2>{title}</h2>
<table><thead><tr><th>名称</th><th>任务数</th>{dim_headers}</tr></thead>
<tbody>{dim_rows}</tbody></table>"""

    # 分差矩阵表
    diff_section = ""
    diff = summary.get("diff_matrix", [])
    if diff:
        diff_headers = "".join(f"<th>{label}</th>" for label in run_labels)
        diff_rows = "".join(
            f"<tr><td>{run_labels[i]}</td>"
            + "".join(f"<td>{v:+.1f}%</td>" for v in row_vals)
            + "</tr>"
            for i, row_vals in enumerate(diff)
        )
        diff_section = f"""
<h2>分差矩阵</h2>
<table><thead><tr><th>行单元 - 列单元</th>{diff_headers}</tr></thead>
<tbody>{diff_rows}</tbody></table>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>WildClawBench 评测报告</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1400px;margin:20px auto;padding:0 20px}}
h1,h2{{color:#1f2937}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}
th,td{{border:1px solid #d1d5db;padding:8px;text-align:left}}
th{{background:#f3f4f6;font-weight:600}}
</style>
</head>
<body>
<h1>WildClawBench 评测报告</h1>
<p><strong>单元数</strong>: {summary['overview']['unit_count']} |
<strong>总任务数</strong>: {summary['overview']['total_tasks']} |
<strong>平均分</strong>: {summary['overview']['average_score']*100:.1f}%</p>
<h2>单元汇总</h2>
<table><thead><tr><th>单元</th><th>平均分</th><th>Tokens</th><th>成本($)</th><th>错误</th><th>超时</th></tr></thead>
<tbody>{unit_rows}</tbody></table>
<h2>用例对比明细</h2>
<table><thead><tr><th>用例ID</th><th>难度</th><th>最优分</th><th>分差</th>{units_th}</tr></thead>
<tbody>{case_rows}</tbody></table>
{cap_section}
{dim_sections}
{diff_section}
</body></html>"""


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
    ap.add_argument("-o", "--output-dir", help="输出目录（默认 <round>/report-workspace/output）")
    ap.add_argument("--tasks-dir", help="任务定义目录（默认从脚本位置向上找 <repo>/tasks）")
    ap.add_argument("--capability-map", help="检查点能力映射 YAML（默认 tools/report/data/checkpoint_capability_map7.yaml）")
    ap.add_argument("--emit", type=str, help="额外产出，逗号分隔：summary_json,md,html（默认仅 Excel）")
    ap.add_argument(
        "--pass-threshold",
        type=float,
        default=None,
        help="pass@k/pass^k 判定阈值：overall_score >= T 记为 pass（默认 0.99 满分）",
    )
    args = ap.parse_args()

    # 展示层 pass@k 阈值可由 CLI 覆盖（默认 PASS_THRESHOLD_DISPLAY=0.99）；
    # 须在创建 UnitResult/TaskRecord 之前设置，因为 TaskRecord 构造时即计算 pass@k。
    if args.pass_threshold is not None:
        if not 0 < args.pass_threshold <= 1:
            ap.error("--pass-threshold 必须在 (0, 1] 区间")
        global PASS_THRESHOLD_DISPLAY
        PASS_THRESHOLD_DISPLAY = args.pass_threshold

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
    write_tool_compare_sheet(wb, units)
    write_case_compare_sheet(wb, units, order, task_meta, suite_zh)
    cap_map = load_capability_map(args.capability_map)
    if cap_map:
        write_capability_sheet(wb, units, cap_map)
    write_dimension_sheet_transposed(
        wb, "分类对比", units,
        [(suite_zh.get(s, s), {tid for su, tid in order if su == s})
         for s in suites])

    def meta_groups(field: str, known_order: list[str],
                    label_map: dict[str, str] | None = None) -> list[tuple[str, set[str]]]:
        values = {task_meta.get(tid, {}).get(field, "") for _, tid in order}
        values.discard("")
        ordered = [v for v in known_order if v in values] + sorted(values - set(known_order))
        return [((label_map or {}).get(v, v),
                 {tid for _, tid in order if task_meta.get(tid, {}).get(field) == v})
                for v in ordered]

    write_dimension_sheet_transposed(wb, "难度对比", units, meta_groups("difficulty", DIFFICULTY_ORDER))
    write_dimension_sheet_transposed(wb, "模态对比", units, meta_groups("modality", MODALITY_ORDER, MODALITY_ZH))
    write_diff_matrix_sheet(wb, units)
    # 全局多轮判定：任一 unit 任一 task 跑了多轮才启用多轮列/Sheet（单轮报告零变化）
    has_multirun = any(t.runs > 1 for u in units for t in u.tasks)
    write_stability_sheet(wb, units, task_meta, suite_zh)  # 内部同样判定，无多轮则跳过
    for u in units:
        write_detail_sheet(wb, u, order, task_meta, analysis, suite_zh, has_multirun)

    # 即使 --result-root 传入 model 或 unit，报告仍集中到 round 工作区。
    # 若 --result-root 本身就是 round 根（非 unit 目录、下辖多 unit），直接用它，
    # 兼容双层 <round>/<model>/<harness> 与三层 <round>/<harness>/<model>/<harness>；
    # 仅当传入的是 unit / model 子目录时，才从 unit 反推（支持双层/三层布局）。
    if not is_unit_dir(result_root) and len(units) > 1:
        round_root = result_root
    else:
        round_roots = {round_root_from_unit_dir(u.unit_dir) for u in units}
        if len(round_roots) != 1:
            sys.exit(f"错误：加载的 unit 不属于同一个 round：{sorted(map(str, round_roots))}")
        round_root = next(iter(round_roots))
    out_dir = Path(args.output_dir) if args.output_dir else round_root / "report-workspace" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"report_{len(units)}units_{ts}.xlsx"
    wb.save(out_path)
    print(f"\n✅ Excel 报告已生成：{out_path}")

    # --emit 额外产出
    if args.emit:
        emit_set = set(args.emit.split(","))
        summary = build_summary(units, task_meta, cap_map or {}, suite_zh, analysis, order)

        if "summary_json" in emit_set:
            summary_path = out_dir / f"report_{len(units)}units_{ts}.summary.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✓ summary.json 已生成：{summary_path}")

        if "md" in emit_set:
            md_path = out_dir / f"report_{len(units)}units_{ts}.md"
            md_path.write_text(render_markdown(summary), encoding="utf-8")
            print(f"✓ Markdown 已生成：{md_path}")

        if "html" in emit_set:
            html_path = out_dir / f"report_{len(units)}units_{ts}.html"
            html_path.write_text(render_html(summary), encoding="utf-8")
            print(f"✓ HTML 已生成：{html_path}")


if __name__ == "__main__":
    main()
