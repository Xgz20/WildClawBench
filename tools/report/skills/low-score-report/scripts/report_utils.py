"""low-score-report Skill 辅助工具（WildClawBench 版）。

输入：
- _failed_tasks_<unit>.json：低分任务清单（low-score-analysis 产出）
- analysis_<unit>.json：{task_id: {result_analysis, root_cause_analysis}}
- <unit_dir>/summary_all_*.json：评测元信息（global_avg / task_count）

职责：分桶（主口径 / 环境失效专项）、根因分类、四层归因、
代码执行提取（transcript 的 tool_use）、Markdown 表格格式化。
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# 分桶：主口径低分 vs 环境/基础设施失效专项
# ---------------------------------------------------------------------------

def is_infra_failure(task: dict) -> bool:
    """环境/基础设施失效：任务根本没跑起来，或存在非超时的执行层错误。

    超时任务不自动归 infra —— 超时可能是模型循环不收敛（能力问题），
    定性交给 LLM 分析结果（root_cause_analysis）。
    """
    usage = task.get("usage") or {}
    if usage.get("request_count", 0) == 0:
        return True
    err = (task.get("error_execution") or "").strip()
    return bool(err) and not task.get("timed_out", False) and "timed out" not in err.lower()


def split_tasks_by_bucket(tasks: list[dict]) -> tuple[list[dict], list[dict]]:
    """返回 (主口径低分任务, 环境失效专项任务)，组内按得分升序。"""
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
    ("判分脚本刚性或评测系统问题", ["判分脚本", "评分脚本", "评测系统", "判分刚性", "裁判", "假阳性", "评分标准过严"]),
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


# ---------------------------------------------------------------------------
# 四层归因
# ---------------------------------------------------------------------------

LAYERS = {
    "L1a": "L1a-底层推理",
    "L1b": "L1b-长程执行",
    "L3": "L3-环境基础设施",
    "L4": "L4-评测系统",
}

_LAYER_KEYWORDS = [
    ("L3", ["环境", "额度", "quota", "401", "403", "认证", "网络", "docker", "workspace 缺失", "基础设施", "视觉通道", "非模型能力"]),
    ("L4", ["评测系统", "判分脚本", "评分脚本", "裁判", "假阳性", "评分标准"]),
    ("L1b", ["超时", "循环", "不收敛", "长程", "未落盘", "路径错误", "中途放弃", "执行链路", "工具调用协议"]),
    ("L1a", ["推理", "理解", "幻觉", "编造", "代码错误", "逻辑错误", "能力短板", "知识"]),
]


def extract_layer_attribution(item: dict) -> str:
    """从分析结果推断主导归属层。优先取显式 L1a/L1b/L3/L4 标注，否则关键词推断。"""
    text = (item.get("root_cause_analysis") or "") + " " + (item.get("result_analysis") or "")[:300]
    m = re.search(r"\bL1a\b|\bL1b\b|\bL3\b|\bL4\b", text)
    if m:
        return LAYERS[m.group(0)]
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
        "| 任务ID | 套件 | 得分 | 失分检查点数 | 超时 | 主导归属层 |",
        "|---|---|---:|---:|:---:|---|",
    ]
    for t in tasks:
        item = (analysis or {}).get(t["task_id"], {})
        layer = extract_layer_attribution(item) if item else "-"
        lines.append(
            f"| {t['task_id']} | {t.get('suite','-')} | {_fmt_pct(t.get('score_pct'))} "
            f"| {len(t.get('failed_checkpoints') or {})} | {'是' if t.get('timed_out') else '否'} | {layer} |"
        )
    return "\n".join(lines)


def format_infra_table(tasks: list[dict]) -> str:
    """环境/基础设施失效专项详表。"""
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


def generate_report_header(unit: str, round_desc: str, n_low: int, n_infra: int, workspace: str) -> str:
    model, _, harness = unit.partition("@")
    return f"""# WildClawBench {unit} 低分任务根因分析报告

- **被测模型**：{model}（Agent Harness：{harness}）
- **评测轮次**：{round_desc}
- **分析样本**：主口径低分任务 {n_low} 个（单轮得分 < 60），环境/基础设施失效专项 {n_infra} 个
- **数据来源**：`{workspace}` 下的低分任务清单与逐任务根因分析（判分明细 + transcript 全量取证）

## 分析维度定义

- **L1a-底层推理**：模型单步推理/理解/生成质量问题（理解偏离、幻觉、代码逻辑错误、能力短板）
- **L1b-长程执行**：多步执行链路问题（循环不收敛、产物未落盘、中途放弃、工具调用协议不兼容）
- **L3-环境基础设施**：推理服务/评测环境问题（API 额度、认证故障、视觉通道失效、workspace 缺失）
- **L4-评测系统**：判分脚本刚性、裁判假阳性、评分标准问题
"""
