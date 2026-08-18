"""low-score-report Skill 辅助工具（WildClawBench 版）。

输入：
- _failed_tasks_<unit>__<scope>.json：低分任务清单（low-score-analysis 产出）
- analysis_<unit>__<scope>.json：{task_id: {result_analysis, root_cause_analysis}}
- <unit_dir>/summary_all_*.json：评测元信息（global_avg / task_count）

职责：分桶（主口径 / 执行失效专项）、根因分类、五层归因、
代码执行提取（transcript 的 tool_use）、Markdown 表格格式化。
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ANALYSIS_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "low-score-analysis/scripts"
sys.path.insert(0, str(ANALYSIS_SCRIPTS_DIR))
from analysis_quality import load_analysis as load_quality_analysis  # noqa: E402
from analysis_quality import load_manifest as load_quality_manifest  # noqa: E402
from analysis_quality import validate_analysis as validate_quality_analysis  # noqa: E402

# ---------------------------------------------------------------------------
# 分桶：主口径低分 vs 执行失效专项
# ---------------------------------------------------------------------------

def is_infra_failure(task: dict) -> bool:
    """执行失效专项：任务根本没跑起来，或存在非超时的执行层错误。

    该分桶只用于报告筛选，不等于 L3；Runner/容器/Workspace 等评测框架
    失败也可能属于 L4。超时任务不自动归 infra，定性交给 LLM 分析结果。
    """
    usage = task.get("usage") or {}
    if usage.get("request_count", 0) == 0:
        return True
    err = (task.get("error_execution") or "").strip()
    return bool(err) and not task.get("timed_out", False) and "timed out" not in err.lower()


def split_tasks_by_bucket(tasks: list[dict]) -> tuple[list[dict], list[dict]]:
    """返回 (主口径低分任务, 执行失效专项任务)，组内按得分升序。"""
    low, infra = [], []
    for t in tasks:
        (infra if is_infra_failure(t) else low).append(t)
    key = lambda t: (t.get("score_pct") is not None, t.get("score_pct") or 0.0)
    return sorted(low, key=key), sorted(infra, key=key)


# ---------------------------------------------------------------------------
# 根因分类（对 root_cause_analysis 文本做关键词匹配，按优先级）
# ---------------------------------------------------------------------------

ROOT_CAUSE_RULES: list[tuple[str, list[str]]] = [
    ("工具调用协议不兼容", ["协议不兼容", "unsupported call", "工具调用格式", "工具协议", "tool-calling 协议"]),
    ("API额度或认证故障", ["额度", "quota", "401", "403", "认证", "unauthorized", "令牌"]),
    ("视觉通道失效", ["视觉通道", "视觉助手", "看图", "视觉调用"]),
    ("超时或循环不收敛", ["超时", "循环", "不收敛", "timed out", "反复尝试"]),
    ("产物未落盘或路径错误", ["未落盘", "没有写", "路径错误", "写错路径", "未创建文件", "未保存"]),
    ("判分脚本刚性或评测系统问题", ["判分脚本", "评分脚本", "评测系统", "判分刚性", "裁判", "判分误判", "误扣", "假阳性", "评分标准过严"]),
    ("幻觉或编造", ["幻觉", "编造", "伪造", "捏造", "虚构"]),
    ("任务理解偏离", ["理解偏离", "理解错误", "偏离任务", "误解", "答非所问"]),
    ("代码错误", ["代码错误", "KeyError", "逻辑错误", "语法错误", "脚本报错", "异常"]),
    ("能力短板", ["能力短板", "能力不足", "质量不佳", "不准确", "遗漏"]),
]


def classify_root_causes(analysis: dict) -> dict[str, list[str]]:
    """{task_id: {root_cause_analysis}} → {根因类别: [task_id...]}（每任务归入首个命中类别）。"""
    buckets: dict[str, list[str]] = {}
    for task_id, item in analysis.items():
        text = (item.get("root_cause_analysis") or "") + " " + (item.get("result_analysis") or "")[:200]
        matched = "其他"
        for label, keywords in ROOT_CAUSE_RULES:
            if any(kw.lower() in text.lower() for kw in keywords):
                matched = label
                break
        buckets.setdefault(matched, []).append(task_id)
    return buckets


def load_validated_analysis(
    analysis_path: str | Path,
    manifest_path: str | Path,
    *,
    allow_partial: bool = True,
) -> tuple[dict, dict]:
    """加载并校验分析；返回 (analysis, quality)。

    允许 analysis 只是 manifest 子集，但不允许越界任务、空字段或来源快照变化。
    """
    analysis_file = Path(analysis_path)
    manifest_file = Path(manifest_path)
    analysis = load_quality_analysis(analysis_file)
    manifest = load_quality_manifest(manifest_file)
    expected = {
        str(item.get("task_id")): item
        for item in manifest
        if item.get("task_id")
    }
    quality = validate_quality_analysis(
        analysis,
        expected=expected,
        allow_partial=allow_partial,
        source_records=manifest,
    )
    if quality["status"] == "FAIL":
        messages = "；".join(
            f"{item['code']}：{item['message']}"
            for item in quality["issues"]
            if item["severity"] == "error"
        )
        raise ValueError(f"分析质量校验失败：{messages}")
    return analysis, quality


def analysis_coverage(tasks: list[dict], analysis: dict) -> dict[str, object]:
    """返回报告可展示的分析覆盖范围，不把缺失分析视作成功。"""
    expected_ids = {str(task.get("task_id")) for task in tasks if task.get("task_id")}
    analyzed_ids = expected_ids & set(analysis)
    expected = len(expected_ids)
    return {
        "expected": expected,
        "analyzed": len(analyzed_ids),
        "missing": expected - len(analyzed_ids),
        "ratio": round(len(analyzed_ids) / expected, 4) if expected else 0.0,
        "state": "complete" if len(analyzed_ids) == expected else "partial",
    }


# ---------------------------------------------------------------------------
# 五层归因与待确认状态
# ---------------------------------------------------------------------------

LAYERS = {
    "L1a": "L1a-模型基础推理能力",
    "L1b": "L1b-模型 Agent 能力",
    "L2": "L2-Harness 运行与工具编排",
    "L3": "L3-评测环境与推理服务基础设施",
    "L4": "L4-评测系统、任务与 Grader",
}

ATTRIBUTION_STATUSES = {
    "uncertain": "待确认-归因证据不足",
    "none": "成功对照-无失分根因",
}

_LAYER_KEYWORDS = [
    ("L4", ["评测系统", "评测框架", "评测 Runner", "评测runner", "Runner 创建 Workspace", "Workspace 创建失败", "workspace 缺失", "workspace 初始化失败", "Runner 强制杀进程", "Runner 被强制终止", "容器强制杀进程", "容器强制终止", "容器被强制终止", "进程被评测框架终止", "任务定义", "判分脚本", "评分脚本", "裁判", "判分误判", "误扣", "假阳性", "评分标准", "grader"]),
    ("L3", ["评测环境", "环境基础设施", "额度", "quota", "流控", "限流", "rate limit", "大模型调不通", "模型服务不可用", "API 不可用", "401", "403", "认证", "网络不通", "连接失败", "网络", "推理服务不可用", "推理服务", "视觉通道", "非模型能力"]),
    ("L2", ["工具未按契约", "工具暴露异常", "工具映射异常", "协议适配", "工具调用适配", "适配层", "调度失败", "Harness 会话", "会话生命周期", "会话状态异常", "上下文注入异常", "工具结果未回传", "产物回收", "重试策略异常", "超时控制异常"]),
    ("L1b", ["模型 agent", "agent 能力", "长程", "任务规划", "多步规划", "循环不收敛", "中途放弃", "验证交付", "执行链路", "未落盘", "路径错误", "调用未提供的工具", "调用不存在的工具", "工具选择错误"]),
    ("L1a", ["基础推理", "推理", "任务理解", "理解偏离", "幻觉", "编造", "代码错误", "逻辑错误", "能力短板", "知识"]),
]


def extract_layer_attribution(item: dict) -> str:
    """从分析结果推断主导归属层，兼容旧的纯文本分析结果。"""
    text = (item.get("root_cause_analysis") or "") + " " + (item.get("result_analysis") or "")[:300]
    explicit = item.get("attribution_layer") or item.get("primary_layer")
    explicit_key = str(explicit).strip() if explicit is not None else ""
    explicit_key_lower = explicit_key.lower()
    layer_key = next((key for key in LAYERS if key.lower() == explicit_key_lower), None)
    if layer_key:
        return LAYERS[layer_key]
    status_key = next((key for key in ATTRIBUTION_STATUSES if key.lower() == explicit_key_lower), None)
    if status_key:
        return ATTRIBUTION_STATUSES[status_key]

    m = re.search(
        r"(?:attribution_layer|主导归属层|归属层|主导层|责任层|定性)\s*[=：:]?\s*"
        r"(L1a|L1b|L2|L3|L4|uncertain|待确认)",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        key = m.group(1).lower()
        if key in ATTRIBUTION_STATUSES or key == "待确认":
            return ATTRIBUTION_STATUSES["uncertain"]
        layer_key = next((name for name in LAYERS if name.lower() == key), None)
        if layer_key:
            return LAYERS[layer_key]

    if re.search(r"证据不足|无法区分|无法判断|待确认|缺少.*证据|unsupported call", text, flags=re.IGNORECASE):
        return ATTRIBUTION_STATUSES["uncertain"]

    m = re.search(r"\b(L1a|L1b|L2|L3|L4)\b", text, flags=re.IGNORECASE)
    if m:
        layer_key = next((name for name in LAYERS if name.lower() == m.group(1).lower()), None)
        if layer_key:
            return LAYERS[layer_key]
    for layer, keywords in _LAYER_KEYWORDS:
        if any(kw.lower() in text.lower() for kw in keywords):
            return LAYERS[layer]
    return "未归类"


# ---------------------------------------------------------------------------
# transcript 代码执行提取
# ---------------------------------------------------------------------------

EXEC_TOOL_NAMES = ("exec_command", "shell", "bash", "exec", "write_stdin")


def extract_code_executions(transcript_path: str | Path, tool_names: tuple = EXEC_TOOL_NAMES, limit: int = 50) -> list[dict]:
    """从 chat_openclaw.jsonl 提取工具执行记录 [{name, input, result, is_error}]。"""
    path = Path(transcript_path)
    if not path.is_file():
        return []
    executions: list[dict] = []
    pending: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = event.get("message") or {}
            for part in msg.get("content") or []:
                ptype = part.get("type")
                if ptype == "tool_use" and part.get("name") in tool_names:
                    rec = {
                        "name": part.get("name"),
                        "input": part.get("input"),
                        "result": None,
                        "is_error": False,
                    }
                    pending[part.get("id", "")] = rec
                    executions.append(rec)
                elif ptype == "tool_result":
                    rec = pending.pop(part.get("tool_use_id", ""), None)
                    if rec is not None:
                        content = part.get("content")
                        if isinstance(content, list):
                            content = " ".join(
                                c.get("text", "") for c in content if isinstance(c, dict)
                            )
                        rec["result"] = (str(content) if content is not None else "")[:2000]
                        rec["is_error"] = bool(part.get("is_error"))
            if len(executions) >= limit:
                break
    return executions


# ---------------------------------------------------------------------------
# 评测元信息
# ---------------------------------------------------------------------------

def extract_eval_metadata(unit_dir: str | Path) -> dict:
    """从 <unit_dir>/summary_all_*.json 提取 {global_avg, task_count, ...}。"""
    files = sorted(glob.glob(str(Path(unit_dir) / "summary_all_*.json")))
    if not files:
        return {}
    try:
        data = json.loads(Path(files[0]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "global_avg": data.get("global_avg"),
        "task_count": data.get("task_count"),
        "scored_task_count": data.get("scored_task_count"),
        "missing_score_task_count": data.get("missing_score_task_count"),
    }


def format_round_description(round_name: str, task_count: int | None, extra: str = "") -> str:
    desc = f"{round_name}（all_suite {task_count if task_count is not None else '?'} 个评测任务，单轮）"
    if extra:
        desc = desc[:-1] + f"，{extra}）"
    return desc


# ---------------------------------------------------------------------------
# Markdown 格式化
# ---------------------------------------------------------------------------

def _fmt_pct(v) -> str:
    return f"{v:.1f}" if isinstance(v, (int, float)) else "-"


def format_task_table(tasks: list[dict], analysis: dict | None = None) -> str:
    """主口径低分任务详表。"""
    lines = [
        "| 任务ID | 套件 | 得分 | 失分检查点数 | 超时 | 主导归属层 | 归因置信度 | 归因证据摘要 |",
        "|---|---|---:|---:|:---:|---|---|---|",
    ]
    for t in tasks:
        item = (analysis or {}).get(t["task_id"], {})
        layer = extract_layer_attribution(item) if item else "-"
        confidence = item.get("attribution_confidence", "待补充") if item else "-"
        evidence = (item.get("attribution_evidence") or "缺少归因证据，无法区分具体是模型问题还是 Harness 问题") if item else "-"
        evidence = " ".join(str(evidence).split()).replace("|", "\\|")[:160]
        lines.append(
            f"| {t['task_id']} | {t.get('suite','-')} | {_fmt_pct(t.get('score_pct'))} "
            f"| {len(t.get('failed_checkpoints') or {})} | {'是' if t.get('timed_out') else '否'} | {layer} "
            f"| {confidence} | {evidence} |"
        )
    return "\n".join(lines)


def format_infra_table(tasks: list[dict]) -> str:
    """执行失效专项详表。"""
    lines = [
        "| 任务ID | 套件 | 得分 | 请求数 | 执行层错误（摘要） |",
        "|---|---|---:|---:|---|",
    ]
    for t in tasks:
        err = (t.get("error_execution") or t.get("error_grading") or "").replace("\n", " ").replace("|", "\\|")
        lines.append(
            f"| {t['task_id']} | {t.get('suite','-')} | {_fmt_pct(t.get('score_pct'))} "
            f"| {(t.get('usage') or {}).get('request_count', 0)} | {err[:80]} |"
        )
    return "\n".join(lines)


def suite_avg_table(all_tasks: list[dict]) -> str:
    """按套件的均分表（基于清单里的任务；如需全量套件均分请用 Excel 脚本）。"""
    by_suite: dict[str, list[float]] = {}
    for t in all_tasks:
        if t.get("score_pct") is not None:
            by_suite.setdefault(t.get("suite", "?"), []).append(t["score_pct"])
    lines = ["| 套件 | 低分任务数 | 低分任务均分 |", "|---|---:|---:|"]
    for suite in sorted(by_suite):
        scores = by_suite[suite]
        lines.append(f"| {suite} | {len(scores)} | {sum(scores)/len(scores):.1f} |")
    return "\n".join(lines)


def generate_report_header(
    unit: str,
    round_desc: str,
    n_low: int,
    n_infra: int,
    workspace: str,
    selection_label: str = "单轮得分 < 60",
    analysis_expected: int | None = None,
    analysis_analyzed: int | None = None,
    analysis_state: str = "",
) -> str:
    model, _, harness = unit.partition("@")
    if analysis_expected is not None and analysis_analyzed is not None:
        coverage_text = f"已分析 {analysis_analyzed}/{analysis_expected} 个任务"
        if analysis_state:
            coverage_text += f"（{analysis_state}）"
    else:
        coverage_text = f"主口径低分任务 {n_low} 个，执行失效专项 {n_infra} 个"
    return f"""# WildClawBench {unit} 低分任务根因分析报告

- **被测模型**：{model}（Agent Harness：{harness}）
- **评测轮次**：{round_desc}
- **分析样本**：{coverage_text}；报告范围为主口径低分任务 {n_low} 个（{selection_label}），执行失效专项 {n_infra} 个
- **数据来源**：`{workspace}` 下的低分任务清单与逐任务根因分析（判分明细 + transcript 全量取证）

## 分析维度定义

- **L1a-模型基础推理能力**：模型单步推理、任务理解和生成质量问题（理解偏离、幻觉、代码逻辑错误、知识或能力短板）
- **L1b-模型 Agent 能力**：模型的任务规划、多步执行、状态保持、循环收敛、验证和结果交付问题
- **L2-Harness 运行与工具编排**：Harness 的工具暴露、协议适配、参数映射、调度、会话状态、重试/超时控制和 Harness 自身产物回收问题
- **L3-评测环境与推理服务基础设施**：外部大模型服务不可用、API 额度/流控、服务认证、网络不通和模型专属视觉服务故障
- **L4-评测系统、任务与 Grader**：评测框架、Runner、容器生命周期、框架创建/挂载 Workspace、框架控制的任务超时/进程终止、任务定义和判分脚本问题

工具协议问题不能仅凭 `unsupported call` 归层：先核对模型请求体/响应体中的工具清单、Harness 工具契约和调度日志。模型调用未出现在可用工具清单中的工具，才可归 L1b；只有 Harness 违反已声明工具契约，才归 L2。缺少关键材料时显示“待确认-归因证据不足”，并明确缺少什么证据；Harness 增加拒绝或替代工具等兜底属于改进建议，不改变模型根因。

任务达到统一规定的超时时间，不因最终由 Runner/容器结束进程就自动归 L4：如果模型在截止时间前持续循环、反复报错或没有完成交付，归 L1b；如果 Runner/容器在规定时间前异常终止、错误读取 timeout 配置或违反评测框架生命周期契约，归 L4。外部模型服务调不通、流控或网络故障归 L3；Harness 自身会话中断或产物回收失败归 L2。

“待确认-归因证据不足”不是第六层，不参与五层归因统计；`confirmed` 表示直接证据充分且排除了主要替代解释，`probable` 表示仍有一个未闭环因素但现有证据支持当前判断，`unconfirmed` 表示关键证据缺失、无法可靠归因。
"""
