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
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
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
EXCEL_SHEET_TITLE_MAX_LEN = 31

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="4472C4")
SECTION_FILL = PatternFill("solid", fgColor="D9EAF7")
TARGET_FILL = PatternFill("solid", fgColor="FFF2CC")
CENTER = Alignment(horizontal="center", vertical="center")
WRAP_TOP = Alignment(wrap_text=True, vertical="top")

DIFFICULTY_ORDER = ["L1", "L2", "L3", "L4", "L5"]
MODALITY_ORDER = ["pure-text", "multimodal"]
MODALITY_ZH = {"pure-text": "纯文本", "multimodal": "多模态"}


def detail_sheet_title(unit: str) -> str:
    base = f"评分详情_{unit}"
    if len(base) <= EXCEL_SHEET_TITLE_MAX_LEN:
        return base
    digest = hashlib.sha1(unit.encode("utf-8")).hexdigest()[:8]
    prefix_len = EXCEL_SHEET_TITLE_MAX_LEN - len(digest) - 1
    return f"{base[:prefix_len]}~{digest}"

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
        parse_report_tool_metrics as _parse_report_tool_metrics,
        merge_metrics as _merge_tool_metrics,
        format_accuracy as _tm_format_accuracy,
        execution_success_rate as _tm_exec_success,
        overall_success_rate as _tm_overall_success,
        unclear_ratio as _tm_unclear_ratio,
        tool_search_hit_rate as _tm_tool_search_hit_rate,
    )
    _TOOL_METRICS_OK = True
except Exception:  # 独立分发/路径异常时降级：不统计工具调用指标
    _TOOL_METRICS_OK = False
    def _parse_report_tool_metrics(path, harness, run_dir=None):
        return {"total": 0, "success": 0, "failure": 0, "format_error": 0,
                "unclear": 0, "search_total": 0, "search_hit": 0,
                "search_miss": 0, "search_unresolved": 0, "by_tool": {}}
    def _merge_tool_metrics(lst):
        return {"total": 0, "success": 0, "failure": 0, "format_error": 0,
                "unclear": 0, "search_total": 0, "search_hit": 0,
                "search_miss": 0, "search_unresolved": 0, "by_tool": {}}
    _tm_format_accuracy = _tm_exec_success = _tm_overall_success = \
    _tm_unclear_ratio = _tm_tool_search_hit_rate = lambda m: None

from src.utils.anomalies import classify_execution_error, classify_report_outcome, scan_run_dir
from src.utils.run_selection import select_effective_run_dirs

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import report_entities  # noqa: E402
from report_workspace_paths import round_root_from_unit_dir  # noqa: E402

ANALYSIS_SCRIPTS_DIR = SCRIPT_DIR.parent / "skills/low-score-analysis/scripts"
sys.path.insert(0, str(ANALYSIS_SCRIPTS_DIR))
from analysis_quality import load_manifest as load_analysis_manifest  # noqa: E402
from analysis_quality import validate_analysis as validate_analysis_quality  # noqa: E402

DEFAULT_ENTITIES_PATH = SCRIPT_DIR.parent / "data/entities.yaml"

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
    def __init__(self, suite: str, task_dir: Path, harness: str = "",
                 model: str = "", registry=None, pricing_date: date | None = None):
        self.task_id = task_dir.name
        self.suite = suite
        self.harness = harness
        self.canonical_harness = (
            registry.harness_canonical(harness) if registry else harness
        )
        self.model = model
        self.registry = registry
        self.pricing_date = pricing_date
        all_run_dirs = sorted(p for p in task_dir.iterdir() if p.is_dir())
        run_dirs = select_effective_run_dirs(all_run_dirs, scan_run_dir)
        self.effective_run_dirs = run_dirs
        self.run_provenance = []
        for run_dir in run_dirs:
            provenance_path = run_dir / "provenance.json"
            provenance = _load_json(provenance_path)
            if not provenance:
                provenance = {
                    "schema_version": None,
                    "provenance_status": "legacy_missing",
                    "task_sha256": None,
                    "execution_contract_sha256": None,
                    "scoring_contract_sha256": None,
                }
            self.run_provenance.append({
                "run_dir": run_dir.name,
                **provenance,
            })

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
        self.cost_estimate = self._estimate_cost(
            model, self.canonical_harness, registry, pricing_date
        )

        self.checkpoints = {
            k: v for k, v in score.items()
            if k != "overall_score" and isinstance(v, (int, float))
        }
        raw_dimensions = score.get("_dimensions", {})
        self.metric_dimensions = (
            raw_dimensions if isinstance(raw_dimensions, dict) else {}
        )

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
        self.run_anomalies = scan_run_dir(self.run_dir) if self.run_dir else {"items": []}
        self.outcome = classify_report_outcome(
            status, self.error_grading, self.run_anomalies.get("items", [])
        )
        self.execution_attribution = ""
        if self.error_execution or self.status == "error":
            material_attributions = sorted({
                str(item.get("attribution"))
                for item in self.run_anomalies.get("items", [])
                if item.get("validity_impact") in {"fail", "review"}
                and item.get("attribution")
            })
            self.execution_attribution = (
                ",".join(material_attributions)
                or classify_execution_error(status).get("attribution", "")
            )
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
        self.tool_metrics = _parse_report_tool_metrics(
            self.transcript, self.canonical_harness, self.run_dir
        )

    def _estimate_cost(self, model: str, harness: str, registry, pricing_date):
        return _estimate_run_cost(
            model, harness, self.run_dir, self.usage, registry, pricing_date
        )

    @property
    def effective_score(self) -> float:
        """聚合口径：无有效得分按 0 计（与 summary global_avg 口径一致）。"""
        return self.score if self.score is not None else 0.0


def _estimate_run_cost(
    model: str,
    harness: str,
    run_dir: Path | None,
    usage: dict,
    registry,
    pricing_date: date | None,
):
    """Recompute one run cost using the report entity registry."""
    raw_usage = usage or {}
    raw_status = str(raw_usage.get("cost_status") or "reported")
    if raw_status == "not_applicable":
        return report_entities.CostEstimate(Decimal(0), None, raw_status)
    if registry is None or pricing_date is None:
        if raw_status == "unavailable":
            return report_entities.CostEstimate(
                None,
                None,
                "unavailable",
                str(raw_usage.get("cost_reason") or "cost unavailable"),
            )
        return report_entities.CostEstimate(
            Decimal(str(raw_usage.get("cost_usd") or 0)),
            None,
            raw_status,
        )
    try:
        billable_usage = report_entities.normalize_billable_usage(usage or {})
        profile = registry.pricing_profile(model, pricing_date)
        if len(profile.tiers) == 1:
            return report_entities.estimate_cost_usd(
                registry,
                model,
                pricing_date,
                billable_usage,
                request_input_tokens=None,
            )
        if not run_dir:
            raise ValueError("缺少有效 run 目录")
        if harness in ("astroncode", "codex"):
            requests = report_entities.extract_astroncode_requests(run_dir)
        elif harness == "opencode":
            requests = report_entities.extract_opencode_requests(run_dir)
        elif harness == "deepseek-harness":
            requests = report_entities.extract_deepseek_harness_requests(run_dir)
        else:
            raise ValueError(f"分档定价不支持 Harness: {harness}")
        return report_entities.estimate_request_costs_usd(
            registry, model, pricing_date, requests
        )
    except (OSError, ValueError) as exc:
        return report_entities.CostEstimate(None, None, "unavailable", str(exc))


class UnitResult:
    def __init__(self, model: str, harness: str, unit_dir: Path,
                 registry=None, pricing_date: date | None = None):
        self.model = model
        self.harness = harness
        self.unit = f"{model}@{harness}"
        self.registry = registry
        self.pricing_date = pricing_date
        self.model_display = registry.model_display(model) if registry else model
        self.harness_display = registry.harness_display(harness) if registry else harness
        self.unit_display = f"{self.model_display}@{self.harness_display}"
        self.unit_dir = unit_dir
        self.tasks: list[TaskRecord] = []
        for suite_dir in sorted(unit_dir.iterdir()):
            if not suite_dir.is_dir() or not SUITE_DIR_RE.match(suite_dir.name):
                continue
            for task_dir in sorted(suite_dir.iterdir()):
                if task_dir.is_dir() and any(p.is_dir() for p in task_dir.iterdir()):
                    self.tasks.append(TaskRecord(
                        suite_dir.name, task_dir, harness, model, registry, pricing_date
                    ))
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

    def estimated_cost_total(self) -> Decimal | None:
        estimates = [task.cost_estimate for task in self.tasks]
        if any(item.usd is None for item in estimates):
            return None
        return sum((item.usd for item in estimates if item.usd is not None), Decimal(0))

    @property
    def cost_status(self) -> str:
        statuses = {task.cost_estimate.status for task in self.tasks}
        return ",".join(sorted(statuses)) if statuses else "unavailable"

    @property
    def cost_profile_ids(self) -> list[str]:
        return sorted({
            task.cost_estimate.profile_id
            for task in self.tasks
            if task.cost_estimate.profile_id
        })

    @property
    def cost_reasons(self) -> list[str]:
        return sorted({
            task.cost_estimate.reason
            for task in self.tasks
            if task.cost_estimate.reason
        })

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
        """带版本的 Harness 展示名；无版本时退化为友好名称。"""
        return (f"{self.harness_display} ({self.harness_version})"
                if self.harness_version else self.harness_display)


PROVENANCE_HASH_FIELDS = (
    "task_sha256",
    "execution_contract_sha256",
    "scoring_contract_sha256",
)


def _short_hash(value: str | None) -> str:
    return value[:12] if isinstance(value, str) and value else "-"


def build_provenance_consistency(units: list[UnitResult]) -> dict:
    """Inspect contract fingerprints without filtering scores or blocking reports."""
    task_ids = sorted({task_id for unit in units for task_id in unit.task_map})
    items = []
    counts: dict[str, int] = {}
    for task_id in task_ids:
        observations = []
        for unit in units:
            task = unit.task_map.get(task_id)
            if task is None:
                continue
            for provenance in task.run_provenance:
                observations.append({
                    "unit_id": unit.unit,
                    "run_dir": provenance.get("run_dir"),
                    "provenance_status": provenance.get("provenance_status") or "legacy_missing",
                    **{
                        field: provenance.get(field)
                        if isinstance(provenance.get(field), str) and provenance.get(field)
                        else None
                        for field in PROVENANCE_HASH_FIELDS
                    },
                })

        hashes = {
            field: sorted({
                observation[field]
                for observation in observations
                if observation.get(field)
            })
            for field in PROVENANCE_HASH_FIELDS
        }
        missing = [
            observation for observation in observations
            if any(not observation.get(field) for field in PROVENANCE_HASH_FIELDS)
        ]
        execution_mismatch = len(hashes["execution_contract_sha256"]) > 1
        scoring_mismatch = len(hashes["scoring_contract_sha256"]) > 1
        task_source_mismatch = len(hashes["task_sha256"]) > 1

        if not observations:
            status = "no_provenance_observation"
            recommendation = "没有可检查的有效 run；本次报告仍正常生成"
        elif execution_mismatch and scoring_mismatch:
            status = "execution_and_scoring_mismatch"
            recommendation = "执行与评分契约均不一致；如需同口径比较，通常需要重跑"
        elif execution_mismatch:
            status = "execution_mismatch"
            recommendation = "执行契约不一致；如需同口径比较，应重跑不一致版本"
        elif scoring_mismatch:
            status = "scoring_mismatch"
            recommendation = "评分契约不一致；优先判断能否基于现有产物重新评分"
        elif missing and len(missing) == len(observations):
            status = "legacy_missing"
            recommendation = "历史结果缺少 hash，无法自动判断；本次报告仍正常生成"
        elif missing:
            status = "partial_legacy_missing"
            recommendation = "部分结果缺少 hash；结合任务历史人工判断是否需要重评"
        elif task_source_mismatch:
            status = "task_source_only_changed"
            recommendation = "原始任务文件不同，但执行与评分契约一致；通常无需重跑或重评"
        else:
            status = "consistent"
            recommendation = "执行与评分契约一致"

        counts[status] = counts.get(status, 0) + 1
        items.append({
            "task_id": task_id,
            "status": status,
            "report_blocked": False,
            "observation_count": len(observations),
            "missing_provenance_count": len(missing),
            "task_sha256_values": hashes["task_sha256"],
            "execution_contract_sha256_values": hashes["execution_contract_sha256"],
            "scoring_contract_sha256_values": hashes["scoring_contract_sha256"],
            "recommendation": recommendation,
            "observations": observations,
        })

    mismatch_statuses = {
        "execution_and_scoring_mismatch",
        "execution_mismatch",
        "scoring_mismatch",
    }
    return {
        "schema_version": 1,
        "mode": "informational_non_blocking",
        "report_scores_unchanged": True,
        "task_count": len(items),
        "counts": counts,
        "mismatch_task_count": sum(
            count for status, count in counts.items() if status in mismatch_statuses
        ),
        "legacy_or_missing_task_count": (
            counts.get("legacy_missing", 0)
            + counts.get("partial_legacy_missing", 0)
            + counts.get("no_provenance_observation", 0)
        ),
        "compatibility_hash_fields": [
            "execution_contract_sha256",
            "scoring_contract_sha256",
        ],
        "task_sha256_informational_only": True,
        "items": items,
    }


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
            pending_list_key: str | None = None
            list_items: list[str] = []

            def _flush_list() -> None:
                # YAML 列表块（如 tags:\n  - custom）归一为逗号分隔字符串
                nonlocal pending_list_key, list_items
                if pending_list_key and list_items:
                    meta[pending_list_key] = ", ".join(list_items)
                pending_list_key, list_items = None, []

            for line in text[3:end].splitlines():
                stripped = line.strip()
                # 缩进的 `- item` 行：归属于上一个空值键（YAML 列表块）
                if pending_list_key and line.startswith((" ", "\t")) and stripped.startswith("- "):
                    list_items.append(stripped[2:].strip().strip('"').strip("'"))
                    continue
                if ":" in line and not line.startswith((" ", "\t", "#")):
                    _flush_list()
                    key, _, val = line.partition(":")
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    # 内联数组 tags: [a, b] 直接展开；空值键可能是列表块的开头
                    if val.startswith("[") and val.endswith("]"):
                        items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",")]
                        meta[key] = ", ".join(x for x in items if x)
                    elif val:
                        meta[key] = val
                    else:
                        meta[key] = ""
                        pending_list_key = key
            _flush_list()
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
    # extension/ 下是扩展任务（task_00N 系列），同样参与评测，其难度/模态元数据
    # 必须纳入，否则难度与模态维度会漏掉这批用例（合计小于总用例数）。
    for base in (tasks_dir, tasks_dir / "extension",
                 tasks_dir / "cn", tasks_dir / "extension" / "cn"):  # 先英文打底，再中文覆盖
        if not base.is_dir():
            continue
        is_ext = "extension" in base.relative_to(tasks_dir).parts if base != tasks_dir else False
        for suite_dir in sorted(base.iterdir()):
            if not suite_dir.is_dir() or not SUITE_DIR_RE.match(suite_dir.name):
                continue
            for md in sorted(suite_dir.glob("*.md")):
                meta = parse_task_md(md)
                meta["suite"] = suite_dir.name
                if is_ext:
                    meta["meta_source"] = "extension"
                merged = out.setdefault(md.stem, {})
                merged.update({k: v for k, v in meta.items() if v})
    return out


def build_suite_zh_map(task_meta: dict[str, dict]) -> dict[str, str]:
    """套件目录名 → 中文分类名（取自中文 md frontmatter 的 category 字段）。

    展示标签只认 tasks/cn/（`meta_source != "extension"`）：extension 下的扩展任务
    自带另一套中文 category（如 06_安全对齐），若参与取名会与主任务标签（06_Safety_
    Alignment）分裂成两个分类列。扩展任务只贡献难度/模态等度量元数据，不参与命名。
    """
    mapping: dict[str, str] = {}
    for meta in task_meta.values():
        if meta.get("meta_source") == "extension":
            continue
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

def load_analysis(
    specs: list[str],
    units: list[UnitResult],
    quality_out: dict | None = None,
) -> dict[str, dict]:
    """返回 {"<unit>::<task_id>": {result_analysis, root_cause_analysis}}。

    spec 形式：PATH 或 UNIT=PATH。文件内容两种格式：
    - {task_id: {...}}（单 unit，unit 由显式绑定或文件名 analysis_<unit>*.json 推断）
    - {"<unit>::<task_id>": {...}}（多 unit 合并文件）
    """
    unit_ids = [u.unit for u in units]
    merged: dict[str, dict] = {}
    duplicate_count = 0
    malformed_entries: list[str] = []
    out_of_scope_keys: list[str] = []
    manifest_by_unit: dict[str, list[dict]] = {}
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
        inferred_unit = bound
        if inferred_unit is None:
            matches = [u for u in unit_ids if u in path.name]
            inferred_unit = max(matches, key=len) if matches else None
        if path.name.startswith("analysis_") and path.name.endswith(".json"):
            stem = path.name[len("analysis_"):-len(".json")]
            candidate = path.with_name(f"_failed_tasks_{stem}.json")
            if candidate.is_file():
                try:
                    manifest_records = load_analysis_manifest(candidate)
                    manifest_units = {str(item.get("unit") or "") for item in manifest_records}
                    for manifest_unit in manifest_units:
                        if manifest_unit:
                            manifest_by_unit.setdefault(manifest_unit, []).extend(
                                item for item in manifest_records
                                if item.get("unit") == manifest_unit
                            )
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"manifest 无法读取：{candidate}: {exc}") from exc
        for key, val in data.items():
            if not isinstance(val, dict):
                malformed_entries.append(str(key))
                continue
            if "::" in key:
                key_unit, _, _ = key.partition("::")
                if key_unit not in unit_ids:
                    out_of_scope_keys.append(key)
                    continue
                if key in merged:
                    duplicate_count += 1
                merged[key] = val
                count += 1
                continue
            unit = bound
            if unit is None:
                unit = inferred_unit
            if unit is None:
                print(f"[警告] 无法从文件名 {path.name} 匹配到已加载 unit，"
                      f"请用 UNIT=PATH 显式绑定（已加载：{unit_ids}）", file=sys.stderr)
                break
            merged_key = f"{unit}::{key}"
            if merged_key in merged:
                duplicate_count += 1
                print(f"[警告] 分析项重复，后加载文件覆盖前值：{merged_key}（{path.name}）",
                      file=sys.stderr)
            merged[merged_key] = val
            count += 1
        if count:
            print(f"已加载分析 {count} 条：{path.name}")
    print(f"已加载分析回填合计 {len(merged)} 条（来自 {len(specs)} 个文件）")
    quality = {
        "schema_version": 1,
        "status": "PASS",
        "files": len(specs),
        "duplicate_overrides": duplicate_count,
        "malformed_entries": malformed_entries,
        "out_of_scope_keys": out_of_scope_keys,
        "units": {},
    }
    if duplicate_count:
        quality["status"] = "REVIEW"
    if malformed_entries or out_of_scope_keys:
        quality["status"] = "FAIL"
    for current_unit in unit_ids:
        prefix = f"{current_unit}::"
        entries = {
            key[len(prefix):]: value
            for key, value in merged.items()
            if key.startswith(prefix)
        }
        manifest_records = manifest_by_unit.get(current_unit)
        if manifest_records is not None:
            expected_records = {
                str(item.get("task_id")): item
                for item in manifest_records
                if item.get("task_id")
            }
        else:
            current_unit_obj = next(u for u in units if u.unit == current_unit)
            task_map = getattr(current_unit_obj, "task_map", {})
            expected_records = {task_id: {} for task_id in task_map}
        unit_quality = validate_analysis_quality(
            entries,
            expected=expected_records,
            allow_partial=True,
            source_records=manifest_records,
        )
        quality["units"][current_unit] = unit_quality
        if unit_quality["status"] == "FAIL":
            quality["status"] = "FAIL"
        elif unit_quality["status"] == "REVIEW" and quality["status"] == "PASS":
            quality["status"] = "REVIEW"
    if quality_out is not None:
        quality_out.update(quality)
    if quality["status"] == "FAIL":
        failed = (
            [f"analysis 文件包含非法条目：{key}" for key in malformed_entries]
            + [f"analysis 文件包含越界任务：{key}" for key in out_of_scope_keys]
            + [
                f"{unit}: {issue['code']} {issue['message']}"
                for unit, unit_quality in quality["units"].items()
                for issue in unit_quality["issues"]
                if issue["severity"] == "error"
            ]
        )
        raise ValueError("；".join(failed[:8]))
    for current_unit, unit_quality in quality["units"].items():
        coverage = unit_quality["coverage"]
        if unit_quality["status"] == "REVIEW":
            print(
                f"[提示] {current_unit} 分析质量为 REVIEW："
                f"已覆盖 {coverage['analyzed']}/{coverage['expected']} 个任务，"
                "未分析任务不会被当作已分析",
                file=sys.stderr,
            )
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


PCT_FMT = "0.0"               # 保留 0~100 分值，避免 QuickLook/Numbers 将字面百分号再放大 100 倍
PCT_SIGNED_FMT = "+0.0;-0.0;0.0"


def _pct_or_dash(frac: float | None):
    """比率(0~1)转百分制数值（如 68.3）供 PCT_FMT 展示；None → "-"。"""
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


def append_controlled_views(
    ws,
    units: list[UnitResult],
    value_headers: list[str],
    values_by_raw_unit: dict[str, list],
    target_model: str | None,
    target_harness: str | None,
) -> None:
    if not target_model or not target_harness:
        return

    def append_view(title: str, first_header: str, selected: list[UnitResult],
                    label_getter, target_id: str, id_getter) -> None:
        if len(selected) < 2:
            # 该维度只有 1 个参评对象，控制变量对比不成立（无参照），整表省略。
            # 报告撰写端据 leader_data 的 *_view_applicable 判断是否省略对应章节。
            print(f"[提示] {title} 仅 1 个参评对象，该维度无对比意义，跳过此表",
                  file=sys.stderr)
            return
        title_row = ws.max_row + 3
        ws.cell(title_row, 1, title)
        for column in range(1, 2 + len(value_headers)):
            cell = ws.cell(title_row, column)
            cell.fill = SECTION_FILL
            cell.font = Font(bold=True, color="1F4E78")
        header_row = title_row + 1
        ws.append([first_header] + value_headers)
        style_header_row_at(ws, header_row)
        ws.row_dimensions[header_row].height = 42
        for cell in ws[header_row]:
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
        data_start = header_row + 1
        for unit in selected:
            ws.append([label_getter(unit)] + list(values_by_raw_unit[unit.unit]))
            current_row = ws.max_row
            multiline_cells = [
                cell
                for cell in ws[current_row]
                if isinstance(cell.value, str) and "\n" in cell.value
            ]
            if multiline_cells:
                ws.row_dimensions[current_row].height = 48
                for cell in multiline_cells:
                    cell.alignment = WRAP_TOP
            if id_getter(unit) == target_id:
                for cell in ws[current_row]:
                    cell.font = Font(bold=True)
                ws.cell(current_row, 1).fill = TARGET_FILL
        data_end = ws.max_row

        numeric_offsets = [
            index
            for index in range(len(value_headers))
            if any(
                isinstance(values_by_raw_unit[unit.unit][index], (int, float))
                for unit in selected
            )
        ]
        for row in range(data_start, data_end + 1):
            apply_pct_format(ws, row, [2 + offset for offset in numeric_offsets])
        groups: list[list[int]] = []
        for offset in numeric_offsets:
            if not groups or offset != groups[-1][-1] + 1:
                groups.append([offset])
            else:
                groups[-1].append(offset)
        for group in groups:
            add_color_scale(
                ws, data_start, data_end, 2 + group[0], 2 + group[-1]
            )

    model_units = [unit for unit in units if unit.harness == target_harness]
    target_harness_display = next(
        (unit.harness_display for unit in units if unit.harness == target_harness),
        target_harness,
    )
    append_view(
        f"固定 {target_harness_display}：模型对比",
        "模型",
        model_units,
        lambda unit: unit.model_display,
        target_model,
        lambda unit: unit.model,
    )

    harness_units = [unit for unit in units if unit.model == target_model]
    target_model_display = next(
        (unit.model_display for unit in units if unit.model == target_model),
        target_model,
    )
    append_view(
        f"固定 {target_model_display}：Harness 对比",
        "Harness",
        harness_units,
        lambda unit: unit.harness_display,
        target_harness,
        lambda unit: unit.harness,
    )


# ===========================================================================
# Sheet 写入
# ===========================================================================

def write_overview_sheet(wb, units: list[UnitResult], suites: list[str],
                         suite_zh: dict[str, str],
                         target_model: str | None = None,
                         target_harness: str | None = None) -> None:
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
    first_token_cols = [
        "平均首 Token 响应时间",
        "首 Token 响应时间 P50",
        "首 Token 响应时间 P90",
        "首 Token 指标覆盖率",
        "首 Token 响应有效样本数",
    ]
    header = (["模型", "Harness", "总平均分", "用例数", "正常完成数", "执行错误数", "超时数",
               "评测异常数", "完成率"]
              + multirun_cols
              + ["总tokens", "总请求数", "总耗时(s)", "总成本(USD)"]
              + first_token_cols
              + tool_cols)
    ws.append(header)
    for u in units:
        suite_ids = {s: {t.task_id for t in u.tasks if t.suite == s} for s in suites}
        n_total = len(u.tasks)
        # 四态互斥且完备。执行错误只保留模型/Harness 组合错误；评测框架、
        # 环境、外部服务、未定执行错误及判分错误归入“评测异常数”。
        n_finished = sum(1 for t in u.tasks if t.outcome == "finished")
        n_error = sum(1 for t in u.tasks if t.outcome == "execution_error")
        n_timeout = sum(1 for t in u.tasks if t.outcome == "timeout")
        n_evaluation_anomaly = sum(1 for t in u.tasks if t.outcome == "evaluation_anomaly")
        finish_rate = round(n_finished / n_total * 100, 1) if n_total else 0.0
        row = [
            u.model_display, u.harness_label, round(u.total_pct, 1), n_total,
            n_finished, n_error, n_timeout, n_evaluation_anomaly, finish_rate,
        ]
        if has_multirun:
            # 仅平均轮数（跨题平均 std 无统计意义，不展示）
            valid_tasks = [t for t in u.tasks if t.runs > 0]
            avg_runs = sum(t.runs for t in valid_tasks) / len(valid_tasks) if valid_tasks else 0
            row += [round(avg_runs, 1)]
        estimated_cost = u.estimated_cost_total()
        first_token = _first_token_metrics(u.tasks)
        row += [
            int(u.usage_total("total_tokens")),
            int(u.usage_total("request_count")),
            round(u.usage_total("elapsed_time"), 1),
            round(float(estimated_cost), 4) if estimated_cost is not None else "-",
            first_token.average_ms if first_token.average_ms is not None else "-",
            first_token.p50_ms if first_token.p50_ms is not None else "-",
            first_token.p90_ms if first_token.p90_ms is not None else "-",
            (
                first_token.coverage_pct
                if first_token.coverage_pct is not None
                else "-"
            ),
            first_token.valid_samples,
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
        if u.model == target_model and u.harness == target_harness:
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)
            ws.cell(ws.max_row, 1).fill = TARGET_FILL
            ws.cell(ws.max_row, 2).fill = TARGET_FILL
        pct_cols = [
            header.index("总平均分") + 1,
            header.index("完成率") + 1,
            header.index("首 Token 指标覆盖率") + 1,
        ]
        if tool_cols:
            pct_cols += [header.index(name) + 1 for name in
                         ("格式准确率", "执行成功率", "不确定占比")]
        apply_pct_format(ws, ws.max_row, pct_cols)
        g_avg = u.summary.get("global_avg")
        if g_avg is not None and abs(u.total_pct / 100 - g_avg) > 0.005:
            print(f"[警告] {u.unit} 重算均分 {u.total_pct / 100:.4f} 与 summary "
                  f"global_avg {g_avg:.4f} 偏差过大", file=sys.stderr)
    style_header_row(ws)
    set_widths(
        ws,
        {
            1: 22,
            2: 34,
            **{
                header.index(name) + 1: 24
                for name in first_token_cols
            },
        },
        default=18,
    )
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
    model_displays = {u.model: u.model_display for u in units}
    harness_displays = {u.harness: u.harness_display for u in units}
    ws.append(["模型 \\ Harness"] + [harness_displays[h] for h in harnesses])
    for m in models:
        row = [model_displays[m]]
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
    header = (["分类", "用例ID", "用例名称", "难度", "模态", "标签",
               "输入(Prompt)", "预期行为", "评分标准", "检查点"]
              + [f"{u.unit_display} 得分" for u in units]
              + ["最优单元", "最大分差"])
    ws.append(header)
    n_meta_cols = 10
    for suite, tid in order:
        meta = task_meta.get(tid, {})
        scores = {u.unit: u.task_map[tid].score for u in units if tid in u.task_map}
        valid = {k: v for k, v in scores.items() if v is not None}
        best_raw = max(valid, key=valid.get) if valid else ""
        best = next((u.unit_display for u in units if u.unit == best_raw), "-")
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
               meta.get("modality", "-"), meta.get("tags") or "-",
               truncate(meta.get("prompt", "")),
               truncate(meta.get("expected", "")), truncate(meta.get("criteria", "")),
               ckpt_cell]
        row += [build_unit_score_cell(u.task_map.get(tid)) for u in units]
        row += [best, spread]
        ws.append(row)
        r = ws.max_row
        for col in list(range(7, n_meta_cols + 1)) + list(range(n_meta_cols + 1, n_meta_cols + 1 + len(units))):
            ws.cell(row=r, column=col).alignment = WRAP_TOP
    style_header_row(ws)
    set_widths(ws, {1: 22, 2: 40, 3: 30, 4: 8, 5: 12, 6: 24, 7: 45, 8: 45, 9: 45, 10: 35,
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


def write_capability_sheet(wb, units: list[UnitResult], cap_map: dict,
                           target_model: str | None = None,
                           target_harness: str | None = None) -> None:
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
    view_values: dict[str, list] = {}
    for u in units:
        scores = unit_scores[u.unit]
        row = [u.unit_display, round(u.total_pct, 1)]
        row += [round(scores[d][0], 1) if scores[d][0] is not None else "-" for d in CAP7_ORDER]
        ranked = sorted((d for d in CAP7_ORDER
                         if scores[d][0] is not None and scores[d][1] >= CAP_RANK_MIN_COUNT),
                        key=lambda d: scores[d][0], reverse=True)
        fmt_rank = lambda ds: "\n".join(f"{CAP7_ZH[d]} {scores[d][0]:.1f}%" for d in ds) or "-"
        row += [fmt_rank(ranked[:3]), fmt_rank(list(reversed(ranked[-3:])))]
        view_values[u.unit] = row[1:]
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
    append_controlled_views(
        ws, units, header[1:], view_values, target_model, target_harness
    )

    # ---- Sheet 2：仅 3 项去落盘污染能力 ----
    ws2 = wb.create_sheet("Agent能力对比·去污染", index=4)
    header2 = (["模型@Harness", "总平均分"]
               + [f"{CAP7_ZH[d]}·去落盘污染" for d in CAP7_DECON])
    ws2.append(header2)
    n_decon = len(CAP7_DECON)
    decon_view_values: dict[str, list] = {}
    for u in units:
        decon = unit_decon[u.unit]
        row = [u.unit_display, round(u.total_pct, 1)]
        row += [round(decon[d][0], 1) if decon[d][0] is not None else "-" for d in CAP7_DECON]
        decon_view_values[u.unit] = row[1:]
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
    append_controlled_views(
        ws2, units, header2[1:], decon_view_values, target_model, target_harness
    )

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


WEBSITE_PRIMARY_ZH = {
    "content_structure": "内容与结构",
    "interaction_function": "交互与功能",
    "visual_layout": "视觉与布局",
}

WEBSITE_SECONDARY_ZH = {
    "basic_content": "基础内容",
    "information_organization": "信息组织",
    "lists_tables": "列表与表格",
    "detail_display": "详情展示",
    "data_visualization": "数据可视化",
    "page_navigation": "页面导航",
    "content_switching": "内容切换",
    "form_validation": "表单填写与校验",
    "operation_feedback": "操作反馈",
    "state_persistence": "状态持久化",
    "cross_region_linkage": "跨区域联动",
    "filtering_sorting": "筛选与排序",
    "popup_overlay": "弹窗与浮层",
    "search": "搜索",
    "content_editing": "内容创建与编辑",
    "visual_style": "视觉风格",
    "page_layout": "页面布局",
    "component_style": "组件样式",
}

WEBSITE_SECONDARY_PRIMARY = {
    "basic_content": "content_structure",
    "information_organization": "content_structure",
    "lists_tables": "content_structure",
    "detail_display": "content_structure",
    "data_visualization": "content_structure",
    "page_navigation": "interaction_function",
    "content_switching": "interaction_function",
    "form_validation": "interaction_function",
    "operation_feedback": "interaction_function",
    "state_persistence": "interaction_function",
    "cross_region_linkage": "interaction_function",
    "filtering_sorting": "interaction_function",
    "popup_overlay": "interaction_function",
    "search": "interaction_function",
    "content_editing": "interaction_function",
    "visual_style": "visual_layout",
    "page_layout": "visual_layout",
    "component_style": "visual_layout",
}


@dataclass(frozen=True)
class WebsiteMetric:
    category: str
    name: str
    value: float | None
    sample: int | str
    method: str
    value_type: str


@dataclass(frozen=True)
class FirstTokenMetrics:
    average_ms: float | None
    p50_ms: float | None
    p90_ms: float | None
    coverage_pct: float | None
    valid_samples: int
    total_samples: int


WEBSITE_EVIDENCE_MODES = {
    "source_semantic",
    "browser_runtime+visual_llm",
}


def _is_website_metric_task(task) -> bool:
    dimensions = getattr(task, "metric_dimensions", {})
    return (
        dimensions.get("metric_profile") == "web-site-gen"
        and dimensions.get("evidence_mode") in WEBSITE_EVIDENCE_MODES
    )


# Kept as a compatibility alias for report extensions importing the old helper.
_is_website_semantic_task = _is_website_metric_task


def _has_website_tag(task, task_meta: dict[str, dict]) -> bool:
    tags = str(task_meta.get(task.task_id, {}).get("tags") or "")
    return "web-site-gen" in {
        item.strip() for item in tags.split(",") if item.strip()
    }


def _linear_percentile(values: list[float], percentile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _numeric_usage_value(usage: dict, key: str) -> float | None:
    value = usage.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _run_has_explicit_execution_failure(status: dict) -> bool:
    if not isinstance(status, dict):
        return False
    normalized = str(status.get("status") or "").strip().lower()
    return (
        bool(status.get("timed_out"))
        or status.get("task_completed") is False
        or normalized
        in {"error", "failed", "timed_out", "timeout", "cancelled", "aborted"}
        or bool(str(status.get("error") or "").strip())
    )


def _first_token_metrics(tasks: list) -> FirstTokenMetrics:
    """Aggregate native per-run TTFT without coercing missing values to zero."""

    values: list[float] = []
    total_samples = 0
    for task in tasks:
        for run_dir in getattr(task, "effective_run_dirs", []):
            total_samples += 1
            status = _load_json(run_dir / "execution_status.json")
            if _run_has_explicit_execution_failure(status):
                continue
            usage = _load_json(run_dir / "usage.json")
            value = _numeric_usage_value(usage, "time_to_first_token_ms")
            if value is not None:
                values.append(value)

    valid_samples = len(values)
    average = sum(values) / valid_samples if valid_samples else None
    p50 = _linear_percentile(values, 0.5)
    p90 = _linear_percentile(values, 0.9)
    coverage = (
        valid_samples / total_samples * 100 if total_samples else None
    )
    return FirstTokenMetrics(
        average_ms=round(average, 1) if average is not None else None,
        p50_ms=round(p50, 1) if p50 is not None else None,
        p90_ms=round(p90, 1) if p90 is not None else None,
        coverage_pct=round(coverage, 1) if coverage is not None else None,
        valid_samples=valid_samples,
        total_samples=total_samples,
    )


def _website_unit_metrics(unit, task_meta: dict[str, dict]) -> dict[str, WebsiteMetric]:
    tasks = [
        task for task in unit.tasks
        if _is_website_metric_task(task) or _has_website_tag(task, task_meta)
    ]

    def _score_average(selected: list) -> float | None:
        if not selected:
            return None
        scores = [
            getattr(task, "effective_score", None)
            if getattr(task, "effective_score", None) is not None
            else getattr(task, "score", 0.0)
            for task in selected
        ]
        return round(
            sum(float(score or 0.0) for score in scores) / len(selected) * 100, 1
        )

    metrics: dict[str, WebsiteMetric] = {}

    def add(category, name, value, sample, method, value_type):
        metrics[name] = WebsiteMetric(
            category, name, value, sample, method, value_type
        )

    add(
        "结果指标", "得分率", _score_average(tasks), len(tasks),
        "各任务 overall_score 按任务等权平均", "percent",
    )
    full_count = sum(getattr(task, "score", None) == 1.0 for task in tasks)
    full_rate = round(full_count / len(tasks) * 100, 1) if tasks else None
    add(
        "结果指标", "满分率", full_rate, len(tasks),
        "overall_score = 1.0 的任务数 / Web 任务数", "percent",
    )

    for difficulty in ("L1", "L2"):
        selected = [
            task for task in tasks
            if task_meta.get(task.task_id, {}).get("difficulty") == difficulty
        ]
        add(
            "分层分析", f"{difficulty} 题目得分率", _score_average(selected), len(selected),
            f"difficulty={difficulty} 的任务按任务等权平均", "percent",
        )

    for key, label in WEBSITE_PRIMARY_ZH.items():
        values = []
        for task in tasks:
            dimensions = getattr(task, "metric_dimensions", {})
            item = dimensions.get("primary", {}).get(key, {})
            score = item.get("score") if isinstance(item, dict) else None
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                values.append(float(score))
        value = round(sum(values) / len(values) * 100, 1) if values else None
        add(
            "分层分析", f"{label}得分率", value, len(values),
            f"一级维度 {key} 按任务等权平均", "percent",
        )

    elapsed_values: list[float] = []
    token_values = {key: [] for key in ("total_tokens", "input_tokens", "output_tokens")}
    cost_estimates = []
    cost_expected = 0
    for task in tasks:
        for run_dir in getattr(task, "effective_run_dirs", []):
            status = _load_json(run_dir / "execution_status.json")
            elapsed = status.get("elapsed_time")
            if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and elapsed >= 0:
                elapsed_values.append(float(elapsed))
            usage = _load_json(run_dir / "usage.json")
            has_usage = any(
                _numeric_usage_value(usage, key) is not None for key in token_values
            )
            for key in token_values:
                value = _numeric_usage_value(usage, key)
                if value is not None:
                    token_values[key].append(value)
            if has_usage:
                cost_expected += 1
                cost_estimates.append(_estimate_run_cost(
                    getattr(unit, "model", ""),
                    getattr(unit, "harness", ""),
                    run_dir,
                    usage,
                    getattr(unit, "registry", None),
                    getattr(unit, "pricing_date", None),
                ))

    elapsed_average = (
        round(sum(elapsed_values) / len(elapsed_values), 1) if elapsed_values else None
    )
    add(
        "效率指标", "运行耗时平均值", elapsed_average, len(elapsed_values),
        "未被替代 run 的 elapsed_time 算术平均", "seconds",
    )
    for name, percentile in (("运行耗时 P50", 0.5), ("运行耗时 P90", 0.9)):
        value = _linear_percentile(elapsed_values, percentile)
        add(
            "效率指标", name, round(value, 1) if value is not None else None,
            len(elapsed_values),
            f"未被替代 run 耗时的第 {int(percentile * 100)} 百分位",
            "seconds",
        )

    first_token = _first_token_metrics(tasks)
    first_token_sample = (
        f"{first_token.valid_samples}/{first_token.total_samples}"
    )
    for name, value, method in (
        (
            "平均首 Token 响应时间",
            first_token.average_ms,
            "正常完成且 usage.json 含 time_to_first_token_ms 的 run 算术平均",
        ),
        (
            "首 Token 响应时间 P50",
            first_token.p50_ms,
            "正常完成且含首 Token 指标的 run 第 50 百分位",
        ),
        (
            "首 Token 响应时间 P90",
            first_token.p90_ms,
            "正常完成且含首 Token 指标的 run 第 90 百分位",
        ),
    ):
        add(
            "效率指标", name, value, first_token_sample, method, "milliseconds",
        )
    add(
        "效率指标",
        "首 Token 指标覆盖率",
        first_token.coverage_pct,
        first_token_sample,
        "首 Token 有效样本数 / 未被替代 run 总数；超时、异常退出和缺失字段不计为有效样本",
        "percent",
    )
    add(
        "效率指标",
        "首 Token 响应有效样本数",
        first_token.valid_samples,
        first_token_sample,
        "正常完成且 usage.json 含有效 time_to_first_token_ms 的 run 数",
        "count",
    )

    available_costs = [item.usd for item in cost_estimates if item.usd is not None]
    average_cost = None
    if cost_expected and len(available_costs) == cost_expected:
        average_cost = float(sum(available_costs, Decimal(0)) / cost_expected)
    add(
        "效率指标", "单次运行平均成本", average_cost,
        f"{len(available_costs)}/{cost_expected}",
        "按 entities.yaml 模型单价逐 run 复算后求平均", "usd",
    )

    for key, name in (
        ("total_tokens", "单次运行平均总 Token"),
        ("input_tokens", "单次运行平均输入 Token"),
        ("output_tokens", "单次运行平均输出 Token"),
    ):
        values = token_values[key]
        add(
            "效率指标", name,
            round(sum(values) / len(values), 1) if values else None,
            len(values), f"未被替代 run 的 {key} 算术平均", "tokens",
        )
    return metrics


def _website_dimension_unit_scores(unit, level: str) -> dict[str, tuple[float, int]]:
    """Return task-equal website dimension averages as percentage + task count."""
    values: dict[str, list[float]] = {}
    for task in unit.tasks:
        dimensions = getattr(task, "metric_dimensions", {})
        if (
            dimensions.get("metric_profile") != "web-site-gen"
            or dimensions.get("evidence_mode") not in WEBSITE_EVIDENCE_MODES
        ):
            continue
        groups = dimensions.get(level, {})
        if not isinstance(groups, dict):
            continue
        for key, item in groups.items():
            score = item.get("score") if isinstance(item, dict) else None
            if isinstance(score, (int, float)):
                values.setdefault(key, []).append(float(score))
    return {
        key: (round(sum(scores) / len(scores) * 100, 1), len(scores))
        for key, scores in values.items()
    }


def _website_dimension_keys(
    units: list[UnitResult], level: str, labels: dict[str, str]
) -> list[str]:
    dimensions = {
        key
        for unit in units
        for key in _website_dimension_unit_scores(unit, level)
    }
    known = [key for key in labels if key in dimensions]
    unknown = sorted(dimensions.difference(labels))
    return known + unknown


def _website_secondary_primary_map(units: list[UnitResult]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for unit in units:
        for task in unit.tasks:
            if not _is_website_semantic_task(task):
                continue
            secondary = getattr(task, "metric_dimensions", {}).get("secondary", {})
            if not isinstance(secondary, dict):
                continue
            for key, item in secondary.items():
                primary = item.get("primary") if isinstance(item, dict) else None
                if isinstance(primary, str) and primary.strip():
                    mapping.setdefault(key, primary.strip())
    for key, primary in WEBSITE_SECONDARY_PRIMARY.items():
        mapping.setdefault(key, primary)
    return mapping


def _style_website_header_range(ws, row: int, last_column: int) -> None:
    for column in range(1, last_column + 1):
        cell = ws.cell(row, column)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER


def _append_website_dimension_summary(
    ws,
    units: list[UnitResult],
    *,
    title: str,
    level: str,
    dimensions: list[str],
    labels: dict[str, str],
    groups: list[tuple[str, list[str]]] | None = None,
) -> None:
    if not dimensions:
        return

    last_column = 1 + len(dimensions)
    ws.append([])
    ws.append([title])
    title_row = ws.max_row
    for column in range(1, last_column + 1):
        cell = ws.cell(title_row, column)
        cell.fill = SECTION_FILL
        cell.font = Font(bold=True, color="1F4E78")

    if groups is None:
        ws.append(["模型@Harness"] + [labels.get(key, key) for key in dimensions])
        _style_website_header_range(ws, ws.max_row, last_column)
        ws.row_dimensions[ws.max_row].height = 32
    else:
        group_row = ws.max_row + 1
        label_row = group_row + 1
        ws.cell(group_row, 1, "模型@Harness")
        ws.merge_cells(
            start_row=group_row, start_column=1,
            end_row=label_row, end_column=1,
        )
        column = 2
        for group_label, group_dimensions in groups:
            group_start = column
            for dimension in group_dimensions:
                ws.cell(label_row, column, labels.get(dimension, dimension))
                column += 1
            group_end = column - 1
            ws.cell(group_row, group_start, group_label)
            if group_end > group_start:
                ws.merge_cells(
                    start_row=group_row, start_column=group_start,
                    end_row=group_row, end_column=group_end,
                )
        _style_website_header_range(ws, group_row, last_column)
        _style_website_header_range(ws, label_row, last_column)
        ws.row_dimensions[group_row].height = 24
        ws.row_dimensions[label_row].height = 36

    data_start = ws.max_row + 1
    for unit in units:
        unit_scores = _website_dimension_unit_scores(unit, level)
        ws.append([
            unit.unit_display,
            *[
                unit_scores[dimension][0] if dimension in unit_scores else "-"
                for dimension in dimensions
            ],
        ])
        apply_pct_format(ws, ws.max_row, range(2, last_column + 1))
    add_color_scale(ws, data_start, ws.max_row, 2, last_column)


def write_website_metrics_sheet(
    wb, units: list[UnitResult], task_meta: dict[str, dict] | None = None
) -> bool:
    """Write website metrics for legacy source and browser-runtime evidence."""
    task_meta = task_meta or {}
    website_tasks = [
        (unit, task)
        for unit in units
        for task in unit.tasks
        if _is_website_metric_task(task) or _has_website_tag(task, task_meta)
    ]
    if not website_tasks:
        return False

    ws = wb.create_sheet("站点评测指标")
    metrics_by_unit = [
        (unit, list(_website_unit_metrics(unit, task_meta).values()))
        for unit in units
    ]
    metric_names = [metric.name for metric in metrics_by_unit[0][1]]
    total_metric_columns = len(metric_names) + 1
    evidence_modes = {
        getattr(task, "metric_dimensions", {}).get("evidence_mode")
        for _, task in website_tasks
        if getattr(task, "metric_dimensions", {}).get("evidence_mode")
    }
    if evidence_modes == {"browser_runtime+visual_llm"}:
        scope_note = (
            "一期口径：浏览器动态检查 + 视觉大模型；内容与交互指标由确定性运行时检查，"
            "视觉与布局指标由视觉大模型基于浏览器截图评测。跨任务统计先计算任务内维度分，再按任务等权平均。"
        )
    elif evidence_modes == {"source_semantic"} or not evidence_modes:
        scope_note = (
            "一期口径：源码语义评测；仅判断提交源码中的实现证据，不代表站点启动、"
            "浏览器渲染、动态点击或真实运行结果。跨任务统计先计算任务内维度分，再按任务等权平均。"
        )
    else:
        scope_note = (
            "评测口径包含源码语义评测与浏览器动态检查 + 视觉大模型两类证据；"
            "具体以各任务 score.json 的 _dimensions.evidence_mode 为准。跨任务统计先计算任务内维度分，再按任务等权平均。"
        )
    ws.append([scope_note])
    ws.merge_cells(
        start_row=1,
        start_column=1,
        end_row=1,
        end_column=total_metric_columns,
    )
    ws.cell(1, 1).alignment = WRAP_TOP
    ws.cell(1, 1).fill = SECTION_FILL
    ws.cell(1, 1).font = Font(bold=True, color="1F4E78")

    ws.append([])
    metric_groups = tuple(
        (
            category,
            sum(1 for metric in metrics_by_unit[0][1] if metric.category == category),
        )
        for category in ("结果指标", "分层分析", "效率指标")
    )
    ws.append(["模型@Harness"])
    ws.append([None])
    for column, name in enumerate(metric_names, start=2):
        ws.cell(4, column).value = name
    ws.merge_cells("A3:A4")
    start_column = 2
    for group_name, width in metric_groups:
        end_column = start_column + width - 1
        ws.merge_cells(
            start_row=3, start_column=start_column,
            end_row=3, end_column=end_column,
        )
        ws.cell(3, start_column).value = group_name
        start_column = end_column + 1
    for row in (3, 4):
        style_header_row_at(ws, row)
        for cell in ws[row][:total_metric_columns]:
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )

    glossary = wb.create_sheet("_站点评测指标口径")
    glossary.append([
        "模型@Harness", "指标分类", "指标名称", "单位", "样本数", "计算方法",
    ])
    style_header_row_at(glossary, 1)
    for unit, unit_metrics in metrics_by_unit:
        metrics = {metric.name: metric for metric in unit_metrics}
        ws.append([
            unit.unit_display,
            *[
                metrics[name].value if metrics[name].value is not None else "-"
                for name in metric_names
            ],
        ])
        row = ws.max_row
        for column, name in enumerate(metric_names, start=2):
            metric = metrics[name]
            if metric.value_type == "percent":
                apply_pct_format(ws, row, [column])
            elif metric.value_type == "usd":
                ws.cell(row, column).number_format = '$0.0000'
            elif metric.value_type == "tokens":
                ws.cell(row, column).number_format = '#,##0.0'
            elif metric.value_type == "seconds":
                ws.cell(row, column).number_format = '0.0'
            elif metric.value_type == "milliseconds":
                ws.cell(row, column).number_format = '#,##0.0'
            elif metric.value_type == "count":
                ws.cell(row, column).number_format = '#,##0'
            glossary.append([
                unit.unit_display,
                metric.category,
                metric.name,
                {
                    "percent": "%",
                    "seconds": "秒",
                    "usd": "USD",
                    "tokens": "Token",
                    "milliseconds": "毫秒",
                    "count": "个",
                }[metric.value_type],
                metric.sample,
                metric.method,
            ])
    glossary.sheet_state = "hidden"
    set_widths(glossary, {1: 30, 2: 14, 3: 30, 4: 12, 5: 14, 6: 62}, default=18)
    glossary.freeze_panes = "A2"

    actual_primary_dimensions = _website_dimension_keys(
        units, "primary", WEBSITE_PRIMARY_ZH
    )
    primary_dimensions = list(WEBSITE_PRIMARY_ZH) + [
        key for key in actual_primary_dimensions if key not in WEBSITE_PRIMARY_ZH
    ]
    _append_website_dimension_summary(
        ws,
        units,
        title="一级维度汇总",
        level="primary",
        dimensions=primary_dimensions,
        labels=WEBSITE_PRIMARY_ZH,
    )

    secondary_dimensions = _website_dimension_keys(
        units, "secondary", WEBSITE_SECONDARY_ZH
    )
    secondary_primary = _website_secondary_primary_map(units)
    secondary_groups = [
        (
            primary_label,
            [
                key for key in secondary_dimensions
                if secondary_primary.get(key) == primary_key
            ],
        )
        for primary_key, primary_label in WEBSITE_PRIMARY_ZH.items()
    ]
    secondary_groups = [group for group in secondary_groups if group[1]]
    grouped_dimensions = {
        dimension for _, dimensions in secondary_groups for dimension in dimensions
    }
    other_dimensions = [
        key for key in secondary_dimensions if key not in grouped_dimensions
    ]
    if other_dimensions:
        secondary_groups.append(("其他", other_dimensions))
    ordered_secondary_dimensions = [
        dimension
        for _, dimensions in secondary_groups
        for dimension in dimensions
    ]
    _append_website_dimension_summary(
        ws,
        units,
        title="二级维度汇总",
        level="secondary",
        dimensions=ordered_secondary_dimensions,
        labels=WEBSITE_SECONDARY_ZH,
        groups=secondary_groups,
    )

    ws.append([])
    ws.append(["逐任务维度明细"])
    ws.cell(ws.max_row, 1).fill = SECTION_FILL
    ws.cell(ws.max_row, 1).font = Font(bold=True, color="1F4E78")
    ws.append([
        "模型@Harness", "任务ID", "层级", "维度", "维度得分", "任务内权重",
        "Criterion 数",
    ])
    style_header_row_at(ws, ws.max_row)
    for unit, task in website_tasks:
        dimensions = getattr(task, "metric_dimensions", {})
        for level, labels in (
            ("primary", WEBSITE_PRIMARY_ZH),
            ("secondary", WEBSITE_SECONDARY_ZH),
        ):
            for key, item in dimensions.get(level, {}).items():
                ws.append([
                    unit.unit_display,
                    task.task_id,
                    "一级" if level == "primary" else "二级",
                    labels.get(key, key),
                    round(float(item.get("score", 0)) * 100, 1),
                    round(float(item.get("weight", 0)) * 100, 2),
                    item.get("criterion_count", 0),
                ])
                apply_pct_format(ws, ws.max_row, [5, 6])

    set_widths(
        ws,
        {
            1: 30,
            2: 13,
            3: 13,
            4: 16,
            5: 16,
            6: 20,
            7: 20,
            8: 20,
            9: 18,
            10: 16,
            11: 16,
            12: 20,
            13: 22,
            14: 22,
            15: 22,
            16: 24,
            17: 24,
            18: 22,
            19: 22,
            20: 24,
        },
        default=18,
    )
    ws.row_dimensions[3].height = 24
    ws.row_dimensions[4].height = 42
    ws.freeze_panes = "B5"
    return True


def write_dimension_sheet_transposed(wb, title: str, units: list[UnitResult],
                                     groups: list[tuple[str, set[str]]],
                                     target_model: str | None = None,
                                     target_harness: str | None = None) -> None:
    """转置维度对比：行=unit（按总平均分降序），列=维度取值（表头带用例数）。

    分类/难度/模态三张对比表统一用此布局：第 1 列模型@Harness、第 2 列总平均分，
    其后每个维度取值一列，列头形如 `<取值>平均分(N例)`。
    """
    ws = wb.create_sheet(title)
    groups = [(label, ids) for label, ids in groups if ids]
    header = (["模型@Harness", "总平均分"]
              + [f"{label}平均分({len(ids)}例)" for label, ids in groups])
    ws.append(header)
    view_values: dict[str, list] = {}
    for u in units:  # units 已按总平均分降序
        row = [u.unit_display, round(u.total_pct, 1)]
        for _, ids in groups:
            v = u.avg_pct(ids)
            row.append(round(v, 1) if v is not None else "-")
        view_values[u.unit] = row[1:]
        ws.append(row)
        apply_pct_format(ws, ws.max_row, range(2, 3 + len(groups)))
    style_header_row(ws)
    set_widths(ws, {1: 28, 2: 12}, default=22)
    ws.freeze_panes = "B2"
    add_color_scale(ws, 2, ws.max_row, 2, 2 + len(groups))
    append_controlled_views(
        ws, units, header[1:], view_values, target_model, target_harness
    )


REPORT_SHEET_ORDER = [
    "总览",
    "分类对比",
    "站点评测指标",
    "Agent能力对比",
    "Agent能力对比·去污染",
    "难度对比",
    "模态对比",
    "评测契约一致性",
]


def reorder_report_sheets(wb) -> None:
    prefix = [wb[name] for name in REPORT_SHEET_ORDER if name in wb.sheetnames]
    prefix_names = {sheet.title for sheet in prefix}
    wb._sheets = prefix + [sheet for sheet in wb.worksheets if sheet.title not in prefix_names]


def write_tool_compare_sheet(wb, units: list[UnitResult]) -> None:
    """工具调用对比：按 harness 分块，块内每行 = 模型 × 工具名。

    列：模型 / 工具 / 调用数 / 成功 / 失败 / 不确定 / 格式错误 / 成功率 /
    格式准确率 / tool_search 检索命中率。
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
              "成功率", "格式准确率", "检索命中率（tool_search）"]
    section_fill = PatternFill("solid", fgColor="D9E1F2")
    # 模型行底色：浅灰/浅蓝交替，比表头淡，用于区分同 harness 下不同模型
    model_fills = [
        PatternFill("solid", fgColor="F2F2F2"),  # 浅灰
        PatternFill("solid", fgColor="E7F3FF"),  # 浅蓝
    ]

    for harness, hunits in by_harness.items():
        # harness 分节标题行（合并首列展示）
        harness_display = hunits[0].harness_display
        ws.append([f"【Harness: {harness_display}】"] + [""] * (len(header) - 1))
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
            _append_tool_row(ws, u.model_display, "（全部工具）", tm, bold=True)
            by_tool = tm.get("by_tool", {})
            for tool_name in sorted(by_tool, key=lambda k: -by_tool[k]["total"]):
                _append_tool_row(ws, u.model_display, tool_name, by_tool[tool_name])
            # 给这个模型的所有行（总计+各工具）加底色
            for row_idx in range(start_row, ws.max_row + 1):
                for cell in ws[row_idx]:
                    cell.fill = fill
        ws.append([""] * len(header))  # 块间空行

    set_widths(ws, {1: 24, 2: 22, 10: 26}, default=12)
    ws.freeze_panes = "A1"


def _append_tool_row(ws, model: str, tool_name: str, m: dict, bold: bool = False) -> None:
    """向工具对比表追加一行（成功率=综合成功率，格式准确率单列）。"""
    ws.append([
        model, tool_name, m.get("total", 0), m.get("success", 0),
        m.get("failure", 0), m.get("unclear", 0), m.get("format_error", 0),
        _pct_or_dash(_tm_overall_success(m)),
        _pct_or_dash(_tm_format_accuracy(m)),
        _pct_or_dash(_tm_tool_search_hit_rate(m)),
    ])
    apply_pct_format(ws, ws.max_row, [8, 9, 10])
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
    ws.append(["行单元 - 列单元"] + [u.unit_display for u in units])
    for a in units:
        row = [a.unit_display]
        for b in units:
            row.append(0 if a is b else round(a.total_pct - b.total_pct, 1))
        ws.append(row)
        for col in range(2, 2 + len(units)):
            ws.cell(row=ws.max_row, column=col).number_format = PCT_SIGNED_FMT
    style_header_row(ws)
    set_widths(ws, {1: 28}, default=22)
    ws.freeze_panes = "B2"


def write_provenance_consistency_sheet(wb, consistency: dict) -> None:
    """Write informational contract-version diagnostics without changing scores."""
    ws = wb.create_sheet("评测契约一致性")
    ws.append([
        "说明",
        "非阻断检查；兼容性仅按 execution_contract_sha256 与 "
        "scoring_contract_sha256 判断，task_sha256 只用于完整任务追溯。",
    ])
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=12)
    ws["A1"].font = Font(bold=True)
    ws["A1"].fill = SECTION_FILL
    ws["B1"].fill = SECTION_FILL
    ws["B1"].alignment = WRAP_TOP
    ws.append([
        "用例ID",
        "检查状态",
        "执行契约版本数",
        "评分契约版本数",
        "任务文件版本数",
        "缺少hash的结果数",
        "是否阻断报告",
        "建议",
        "执行契约hash",
        "评分契约hash",
        "任务hash",
        "结果明细",
    ])
    for item in consistency.get("items", []):
        details = []
        for observation in item.get("observations", []):
            details.append(
                f"{observation.get('unit_id')}/{observation.get('run_dir')}: "
                f"execution={_short_hash(observation.get('execution_contract_sha256'))}, "
                f"scoring={_short_hash(observation.get('scoring_contract_sha256'))}, "
                f"task={_short_hash(observation.get('task_sha256'))}, "
                f"status={observation.get('provenance_status')}"
            )
        ws.append([
            item["task_id"],
            item["status"],
            len(item.get("execution_contract_sha256_values", [])),
            len(item.get("scoring_contract_sha256_values", [])),
            len(item.get("task_sha256_values", [])),
            item.get("missing_provenance_count", 0),
            "否",
            item.get("recommendation", ""),
            "\n".join(item.get("execution_contract_sha256_values", [])) or "-",
            "\n".join(item.get("scoring_contract_sha256_values", [])) or "-",
            "\n".join(item.get("task_sha256_values", [])) or "-",
            "\n".join(details) or "-",
        ])
        for cell in ws[ws.max_row]:
            cell.alignment = WRAP_TOP
    style_header_row_at(ws, 2)
    set_widths(
        ws,
        {1: 52, 2: 34, 6: 18, 7: 16, 8: 54, 9: 68, 10: 68, 11: 68, 12: 100},
        default=18,
    )
    ws.freeze_panes = "B3"
    ws.auto_filter.ref = f"A2:L{ws.max_row}"


def write_report_metadata_sheet(
    wb,
    units: list[UnitResult],
    registry,
    entities_path: Path,
    pricing_date: date | None,
    target_model: str | None,
    target_harness: str | None,
) -> None:
    ws = wb.create_sheet("_报告元数据")
    ws.append(["类型", "原始ID", "展示名称", "属性", "值"])
    for model in sorted({u.model for u in units}):
        display = next(u.model_display for u in units if u.model == model)
        ws.append(["模型", model, display, "display_name", display])
    for harness in sorted({u.harness for u in units}):
        display = next(u.harness_display for u in units if u.harness == harness)
        ws.append(["Harness", harness, display, "display_name", display])
    for unit in sorted(units, key=lambda item: item.unit):
        ws.append(["单元", unit.unit, unit.unit_display, "model_id", unit.model])
        ws.append(["单元", unit.unit, unit.unit_display, "harness_id", unit.harness])
        ws.append([
            "单元", unit.unit, unit.unit_display, "detail_sheet",
            detail_sheet_title(unit.unit),
        ])
        ws.append([
            "成本", unit.unit, unit.unit_display, "pricing_profile_id",
            ",".join(unit.cost_profile_ids) or "-",
        ])
        ws.append(["成本", unit.unit, unit.unit_display, "status", unit.cost_status])
        if unit.cost_reasons:
            ws.append([
                "成本", unit.unit, unit.unit_display, "reason",
                "；".join(unit.cost_reasons),
            ])
    ws.append(["配置", "entities", str(entities_path), "schema_version", 1])
    if pricing_date is not None:
        ws.append([
            "配置", "pricing_date", pricing_date.isoformat(), "pricing_date",
            pricing_date.isoformat(),
        ])
        try:
            cny_per_usd = registry.cny_per_usd(pricing_date)
            ws.append([
                "汇率", "CNY", "CNY/USD", "cny_per_usd", float(cny_per_usd),
            ])
        except ValueError as exc:
            ws.append(["汇率", "CNY", "CNY/USD", "status", str(exc)])
    if target_model and target_harness:
        target_unit = f"{target_model}@{target_harness}"
        target = next(u for u in units if u.unit == target_unit)
        ws.append(["目标", target.unit, target.unit_display, "model_id", target.model])
        ws.append(["目标", target.unit, target.unit_display, "harness_id", target.harness])
    style_header_row(ws)
    set_widths(ws, {1: 12, 2: 32, 3: 38, 4: 24, 5: 72}, default=20)
    ws.sheet_state = "hidden"


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
        ws.append([u.unit_display] + [f"{c} ({c/n*100:.0f}%)" for c in b])
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
        ws.append([u.unit_display, f"{b[2]} ({b[2]/n*100:.0f}%)",
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
        ws.append([u.unit_display, f"{b[2]} ({b[2]/n*100:.0f}%)",
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
                    (t.std or 0), u.unit_display, suite_zh.get(t.suite, t.suite), t.task_id,
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
            u.unit_display, runs, n, high_std, round(high_std / n * 100, 1),
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
    ws = wb.create_sheet(detail_sheet_title(u.unit))
    # 多轮列仅在存在多轮数据时插入（单轮评测报告结构与改造前完全一致）
    mr_cols = ["轮数", "Std", "各轮分数"] if has_multirun else []
    header = (["分类", "用例ID", "用例名称", "难度", "超时时间(秒)", "模态", "标签",
               "输入(Prompt)", "预期行为", "评分标准", "Automated Checks",
               "工作目录(Workspace)", "预置技能(Skills)", "环境变量(Env)", "预热(Warmup)",
               "状态", "总得分"]
              + mr_cols
              + ["检查点得分明细", "失分点", "裁判判词", "执行错误",
                 "总tokens", "请求数", "耗时(s)", "执行记录(jsonl)", "结果分析", "根因分析"]
              + ["工具调用数", "格式准确率", "执行成功率", "不确定占比"])
    ws.append(header)
    # 自动换行列：按是否有多轮列动态偏移（多轮列占 3 列，之后的列右移 3）
    # 新增"标签"列后，原第 7 列起整体右移 1（故下方基准列号 +1）
    off = len(mr_cols)  # 0 或 3
    wrap_cols = {8, 9, 10, 11, 13, 15}
    if has_multirun:
        wrap_cols.add(20)  # 各轮分数列
    wrap_cols |= {18 + off, 19 + off, 20 + off, 21 + off, 25 + off, 26 + off, 27 + off}
    for suite, tid in order:
        t = u.task_map.get(tid)
        if t is None:
            continue
        meta = task_meta.get(tid, {})
        item = analysis.get(f"{u.unit}::{tid}", {})
        err = "\n".join(x for x in (
            (f"执行层[{t.execution_attribution or 'undetermined'}]: {t.error_execution}"
             if t.error_execution else ""),
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
            meta.get("modality", "-"), meta.get("tags") or "-",
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
    # 列宽：前 17 列固定（含新增"标签"列）；多轮 3 列（18/19/20）仅 has_multirun 时存在；
    # 其后列按 off 偏移
    widths = {1: 18, 2: 40, 3: 30, 4: 8, 5: 12, 6: 12, 7: 24,
              8: 45, 9: 45, 10: 45, 11: 45,
              12: 38, 13: 20, 14: 20, 15: 30,
              16: 14, 17: 8}  # 状态、总得分
    if has_multirun:
        widths.update({18: 6, 19: 8, 20: 20})  # 轮数、Std、各轮分数
    # 检查点明细、失分点、判词、执行错误、tokens、请求数、耗时、执行记录、结果分析、根因分析
    for base, w in {18: 40, 19: 40, 20: 45, 21: 40, 22: 12, 23: 8, 24: 8, 25: 60, 26: 45, 27: 40}.items():
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
    active_task_ids = {
        task.task_id
        for unit in units
        for task in unit.tasks
    }
    dim_to_tasks: dict[str, set[str]] = {}
    for tid, meta in task_meta.items():
        if tid not in active_task_ids:
            continue
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
                row["scores"][u.unit_display] = round(avg, 1)
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
        first_token = _first_token_metrics(u.tasks)
        run_summaries.append({
            "run_label": u.unit_display,
            "unit_id": u.unit,
            "model": u.model,
            "harness": u.harness,
            "model_display": u.model_display,
            "harness_display": u.harness_display,
            "average_score": round(u.total_pct / 100, 4),  # 前端期望 0-1 范围
            "category_scores": {
                suite_zh.get(suite, suite): round(score / 100, 4) if score is not None else None
                for suite, scores in category_scores.items()
                for unit, score in scores.items()
                if unit == u.unit
            },
            "total_tokens": int(u.usage_total("total_tokens")),
            "cost_usd": (
                round(float(u.estimated_cost_total()), 4)
                if u.estimated_cost_total() is not None else None
            ),
            "elapsed_time": round(u.usage_total("elapsed_time"), 1),
            "request_count": int(u.usage_total("request_count")),
            "average_time_to_first_token_ms": first_token.average_ms,
            "time_to_first_token_p50_ms": first_token.p50_ms,
            "time_to_first_token_p90_ms": first_token.p90_ms,
            "time_to_first_token_coverage": (
                round(first_token.coverage_pct / 100, 4)
                if first_token.coverage_pct is not None
                else None
            ),
            "time_to_first_token_valid_samples": first_token.valid_samples,
            "time_to_first_token_total_samples": first_token.total_samples,
            "finished_count": sum(1 for t in u.tasks if t.outcome == "finished"),
            "error_count": sum(1 for t in u.tasks if t.outcome == "execution_error"),
            "timeout_count": sum(1 for t in u.tasks if t.outcome == "timeout"),
            "evaluation_anomaly_count": sum(
                1 for t in u.tasks if t.outcome == "evaluation_anomaly"
            ),
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
                "run_label": u.unit_display,
                "unit_id": u.unit,
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
            "run_label": u.unit_display,
            "unit_id": u.unit,
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
            "run_label": unit_map[unit].unit_display if unit in unit_map else unit,
            "unit_id": unit,
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
            "runs": [
                {"label": u.unit_display, "unit_id": u.unit, "case_count": len(u.task_map)}
                for u in units
            ],
            "intersection_count": len(intersection),
            "aligned": aligned,
        },
        "provenance_consistency": build_provenance_consistency(units),
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


def _format_cost_usd(value) -> str:
    """格式化美元成本；成本不可用时保留缺失语义。"""
    return f"{value:.4f}" if value is not None else "-"



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
    lines.append("| 单元 | 平均分 | Tokens | 成本($) | 执行错误 | 超时 | 评测异常 |")
    lines.append("|------|--------|--------|---------|----------|------|----------|")
    for item in summary["run_summaries"]:
        lines.append(
            f"| {item['run_label']} | {item['average_score']*100:.1f}% | "
            f"{item['total_tokens']:,} | {_format_cost_usd(item['cost_usd'])} | "
            f"{item['error_count']} | {item['timeout_count']} | "
            f"{item['evaluation_anomaly_count']} |"
        )
    lines.append("")

    provenance = summary.get("provenance_consistency", {})
    if provenance:
        lines.append("## 评测契约一致性（非阻断）")
        lines.append("")
        lines.append(
            "该检查仅辅助判断是否需要重新运行或重新评分，不过滤分数，"
            "也不影响本报告生成。"
        )
        lines.append(
            "兼容性仅按 `execution_contract_sha256` 与 "
            "`scoring_contract_sha256` 判断；`task_sha256` 只用于完整任务追溯。"
        )
        lines.append("")
        counts = provenance.get("counts", {})
        lines.append(
            f"- 检查任务数：{provenance.get('task_count', 0)}；"
            f"契约不一致：{provenance.get('mismatch_task_count', 0)}；"
            f"历史或缺少 hash：{provenance.get('legacy_or_missing_task_count', 0)}；"
            f"一致：{counts.get('consistent', 0)}。"
        )
        actionable = [
            item for item in provenance.get("items", [])
            if item.get("status") in {
                "execution_and_scoring_mismatch",
                "execution_mismatch",
                "scoring_mismatch",
                "task_source_only_changed",
            }
        ]
        if actionable:
            lines.append("")
            lines.append("| 用例ID | 状态 | 建议 |")
            lines.append("|---|---|---|")
            for item in actionable:
                lines.append(
                    f"| {item['task_id']} | {item['status']} | "
                    f"{item['recommendation']} |"
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
        f"<td>{item['total_tokens']:,}</td><td>{_format_cost_usd(item['cost_usd'])}</td>"
        f"<td>{item['error_count']}</td><td>{item['timeout_count']}</td>"
        f"<td>{item['evaluation_anomaly_count']}</td></tr>"
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

    provenance = summary.get("provenance_consistency", {})
    provenance_section = ""
    if provenance:
        counts = provenance.get("counts", {})
        provenance_section = f"""
<h2>评测契约一致性（非阻断）</h2>
<p>该检查仅辅助判断是否需要重新运行或重新评分，不过滤分数，
也不影响本报告生成。</p>
<p>兼容性仅按 <code>execution_contract_sha256</code> 与
<code>scoring_contract_sha256</code> 判断；<code>task_sha256</code>
只用于完整任务追溯。</p>
<ul>
<li>检查任务数：{provenance.get('task_count', 0)}</li>
<li>契约不一致：{provenance.get('mismatch_task_count', 0)}</li>
<li>历史或缺少 hash：{provenance.get('legacy_or_missing_task_count', 0)}</li>
<li>一致：{counts.get('consistent', 0)}</li>
</ul>"""

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
<table><thead><tr><th>单元</th><th>平均分</th><th>Tokens</th><th>成本($)</th><th>执行错误</th><th>超时</th><th>评测异常</th></tr></thead>
<tbody>{unit_rows}</tbody></table>
{provenance_section}
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
    ap.add_argument("--target-model", help="控制变量视图的目标模型原始 ID")
    ap.add_argument("--target-harness", help="控制变量视图的目标 Harness 原始 ID")
    ap.add_argument("--entities", default=str(DEFAULT_ENTITIES_PATH),
                    help="实体注册表 YAML")
    ap.add_argument("--pricing-date", type=date.fromisoformat,
                    help="成本重算使用的定价快照日期 YYYY-MM-DD")
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

    if bool(args.target_model) != bool(args.target_harness):
        ap.error("--target-model 与 --target-harness 必须同时提供")
    entities_path = Path(args.entities).resolve()
    try:
        registry = report_entities.load_registry(entities_path)
    except (OSError, ValueError) as exc:
        ap.error(f"实体注册表加载失败: {exc}")

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
    if args.target_model and args.target_harness:
        target_unit = f"{args.target_model}@{args.target_harness}"
        available_units = {f"{model}@{harness}" for model, harness, _ in unit_specs}
        if target_unit not in available_units:
            ap.error(f"目标单元不在过滤后的评测范围内: {target_unit}")

    units = []
    for model, harness, unit_dir in unit_specs:
        u = UnitResult(model, harness, unit_dir, registry, args.pricing_date)
        print(f"已加载 {u.unit}：{len(u.tasks)} 个任务，总均分 {u.total_pct:.1f}%")
        units.append(u)
    # 全局按总平均分降序：决定总览行序与各对比 Sheet 的 unit 列序（最高分在前）
    units.sort(key=lambda u: u.total_pct, reverse=True)

    tasks_dir = find_tasks_dir(args.tasks_dir)
    if tasks_dir is None:
        print("[警告] 未找到任务定义目录（tasks/），名称/难度/模态/Prompt 列将为空；"
              "可用 --tasks-dir 指定", file=sys.stderr)
    task_meta = load_all_task_meta(tasks_dir)
    analysis_quality: dict = {}
    try:
        analysis = (
            load_analysis(args.analysis, units, analysis_quality)
            if args.analysis else {}
        )
    except ValueError as exc:
        ap.error(f"分析结果质量校验失败：{exc}")

    order = build_task_order(units)
    suites = sorted({s for s, _ in order})
    suite_zh = build_suite_zh_map(task_meta)
    provenance_consistency = build_provenance_consistency(units)
    print(
        "评测契约一致性检查（非阻断）："
        f"不一致 {provenance_consistency['mismatch_task_count']} 个任务，"
        f"历史或缺少 hash {provenance_consistency['legacy_or_missing_task_count']} 个任务；"
        "分数与报告生成不受影响"
    )

    wb = Workbook()
    write_overview_sheet(
        wb, units, suites, suite_zh, args.target_model, args.target_harness
    )
    write_matrix_sheet(wb, units)
    write_tool_compare_sheet(wb, units)
    write_case_compare_sheet(wb, units, order, task_meta, suite_zh)
    write_website_metrics_sheet(wb, units, task_meta)
    cap_map = load_capability_map(args.capability_map)
    if cap_map:
        write_capability_sheet(
            wb, units, cap_map, args.target_model, args.target_harness
        )
    write_dimension_sheet_transposed(
        wb, "分类对比", units,
        [(suite_zh.get(s, s), {tid for su, tid in order if su == s})
         for s in suites],
        args.target_model, args.target_harness,
    )

    def meta_groups(field: str, known_order: list[str],
                    label_map: dict[str, str] | None = None) -> list[tuple[str, set[str]]]:
        values = {task_meta.get(tid, {}).get(field, "") for _, tid in order}
        values.discard("")
        ordered = [v for v in known_order if v in values] + sorted(values - set(known_order))
        return [((label_map or {}).get(v, v),
                 {tid for _, tid in order if task_meta.get(tid, {}).get(field) == v})
                for v in ordered]

    write_dimension_sheet_transposed(
        wb, "难度对比", units, meta_groups("difficulty", DIFFICULTY_ORDER),
        args.target_model, args.target_harness,
    )
    write_dimension_sheet_transposed(
        wb, "模态对比", units, meta_groups("modality", MODALITY_ORDER, MODALITY_ZH),
        args.target_model, args.target_harness,
    )
    write_diff_matrix_sheet(wb, units)
    write_provenance_consistency_sheet(wb, provenance_consistency)
    # 全局多轮判定：任一 unit 任一 task 跑了多轮才启用多轮列/Sheet（单轮报告零变化）
    has_multirun = any(t.runs > 1 for u in units for t in u.tasks)
    write_stability_sheet(wb, units, task_meta, suite_zh)  # 内部同样判定，无多轮则跳过
    for u in units:
        write_detail_sheet(wb, u, order, task_meta, analysis, suite_zh, has_multirun)
    write_report_metadata_sheet(
        wb, units, registry, entities_path, args.pricing_date,
        args.target_model, args.target_harness,
    )
    reorder_report_sheets(wb)

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
    if args.analysis:
        quality_path = out_dir / f"report_{len(units)}units_{ts}.analysis_quality.json"
        quality_path.write_text(
            json.dumps(analysis_quality, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"✓ 分析质量报告已生成：{quality_path}")

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
