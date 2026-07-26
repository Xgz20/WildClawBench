"""Harness 工具调用指标：从归一化轨迹 chat_openclaw.jsonl 统计工具调用情况。

口径与设计见 docs/local/design/Harness工具调用指标设计.md。

四类互斥判定（每次 tool_use 归入其一）：
    success       工具被执行且明确成功
    failure       工具被执行但明确失败（运行时异常、非0退出码）
    format_error  harness 拒绝：工具名不支持 / 参数格式错误
    unclear       无法判定：后台进程、超时、无明确标记

派生四个比率（上层从计数算，与 harness 无关）：
    格式准确率   = (total - format_error) / total
    执行成功率   = success / (success + failure)
    综合成功率   = success / total
    不确定占比   = unclear / total

跨 harness 差异用注册表模式隔离：每个 harness 注册一个 classifier
((tool_name, content, status) -> category)，新增 harness 只需写一个函数 + 一行注册。
纯标准库，无第三方依赖，供报告脚本与平台后端共同 import。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

CATEGORIES = ("success", "failure", "format_error", "unclear")

# classifier 签名：(tool_name, content, status) -> category(∈ CATEGORIES)
Classifier = Callable[[str, str, str], str]

_CLASSIFIERS: dict[str, Classifier] = {}


def register_classifier(harness_names: tuple[str, ...], fn: Classifier) -> None:
    """注册某些 harness 的判定器。同名重复注册以最后一次为准。"""
    for name in harness_names:
        _CLASSIFIERS[name] = fn


def supported_harnesses() -> tuple[str, ...]:
    """已注册（可统计工具调用指标）的 harness 名。"""
    return tuple(sorted(_CLASSIFIERS))


def _empty() -> dict:
    """未注册 harness / 无轨迹时的空指标。"""
    return {
        "total": 0,
        "success": 0,
        "failure": 0,
        "format_error": 0,
        "unclear": 0,
        "by_tool": {},
    }


# ---------------------------------------------------------------------------
# 轨迹加载：兼容 Codex 逐行 JSONL 与 OpenCode 多行 pretty JSON
# ---------------------------------------------------------------------------

def _iter_json_objects(raw: str):
    """用 raw_decode 扫描出连续的 JSON 顶层对象。

    统一处理两种格式：
    - Codex：一行一个 JSON 对象（换行分隔）
    - OpenCode：多个 pretty-printed 对象直接拼接（对象跨多行）
    raw_decode 从当前位置解析一个值并返回结束下标，跳过其间空白后继续。
    """
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw)
    while idx < n:
        # 跳过对象之间的空白（含换行）
        while idx < n and raw[idx] in " \t\r\n":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
        except json.JSONDecodeError:
            # 跳到下一行重试，容忍个别坏行
            nl = raw.find("\n", idx)
            if nl == -1:
                break
            idx = nl + 1
            continue
        yield obj
        idx = end


def _load_tool_pairs(transcript_path: Path | None) -> list[tuple[str, str, str]]:
    """解析轨迹，返回 [(tool_name, content, status), ...]，按出现顺序。

    - 建立 call_id -> tool_name 映射（tool_use 块）
    - 每个 tool_result 块配对出工具名、结果文本、可选 status 字段
    - status 仅 OpenCode 新轨迹有（runner 保留），其余为 ""
    """
    if transcript_path is None:
        return []
    path = Path(transcript_path)
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    tool_names: dict[str, str] = {}
    pairs: list[tuple[str, str, str]] = []

    for obj in _iter_json_objects(raw):
        if not isinstance(obj, dict):
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        content_blocks = message.get("content")
        if not isinstance(content_blocks, list):
            continue

        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_use":
                call_id = str(block.get("id") or "")
                tool_names[call_id] = str(block.get("name") or "unknown")
            elif btype == "tool_result":
                call_id = str(block.get("tool_use_id") or "")
                name = tool_names.get(call_id, "unknown")
                content = block.get("content")
                content_text = content if isinstance(content, str) else json.dumps(
                    content, ensure_ascii=False
                )
                status = str(block.get("status") or "")
                pairs.append((name, content_text, status))

    return pairs


# ---------------------------------------------------------------------------
# Codex / AstronCode classifier（AstronCode 基于 Codex 二开，同口径）
# ---------------------------------------------------------------------------

_CODEX_RUNTIME_ERRORS = (
    "Traceback",
    "ImportError",
    "Exception:",
    "AttributeError",
    "TypeError",
    "ValueError",
    "NameError",
    "SyntaxError",
)

# 状态型工具的成功标记（子串命中即成功）；失败普遍以 error/unavailable 表征
_CODEX_STATE_SUCCESS = {
    "update_plan": ("Plan updated",),
    "spawn_agent": ('"agent_id"', '"nickname"'),  # 需全部命中
    "send_input": ('"submission_id"',),
    "close_agent": ('"previous_status"',),
    "wait_agent": ('"status"', '"timed_out"'),  # 需全部命中
    "view_image": ('"type": "input_image"', '"image_url"'),  # 任一命中
}


def classify_codex(tool_name: str, content: str, status: str = "") -> str:
    """Codex/AstronCode 判定：基于 tool_result content 模式。

    优先级：格式错误 > 执行标记(Process) > 运行时异常 > 状态型消息 > unclear。
    """
    text = content or ""

    # 1. 格式错误（harness 层拒绝）
    if text.startswith("unsupported call:"):
        return "format_error"
    if text.startswith("failed to parse function arguments:"):
        return "format_error"

    # 2. 执行型结果（exec_command / write_stdin 等带 Process 标记）
    if "Process exited with code 0" in text:
        return "success"
    if "Process exited with code" in text:
        return "failure"
    if "Process running with session ID" in text:
        return "unclear"  # 后台进程，最终结果未知

    # 3. 运行时异常
    if any(kw in text for kw in _CODEX_RUNTIME_ERRORS):
        return "failure"

    # 4. 状态型工具（无 Process 标记，按语义消息）
    markers = _CODEX_STATE_SUCCESS.get(tool_name)
    if markers is not None:
        # spawn_agent / wait_agent 需全部标记命中；其余任一命中即可
        need_all = tool_name in ("spawn_agent", "wait_agent")
        hit = all(m in text for m in markers) if need_all else any(m in text for m in markers)
        if hit:
            return "success"
        low = text.lower()
        if "error" in low or "failed" in low or "unavailable" in low:
            return "failure"
        # wait_agent 特例：明确的空 id 报错
        if tool_name == "wait_agent" and "agent ids must be non-empty" in text:
            return "failure"
        return "unclear"

    # request_user_input 在 Default 模式恒不可用
    if tool_name == "request_user_input":
        if "unavailable" in text.lower():
            return "failure"
        return "unclear"

    # write_stdin 的软失败（stdin 关闭等）在上面 Process/异常均未命中时兜底
    if tool_name == "write_stdin" and "failed" in text.lower():
        return "failure"

    return "unclear"


# ---------------------------------------------------------------------------
# OpenCode classifier（基于 runner 保留的 state.status，高保真）
# ---------------------------------------------------------------------------

_OPENCODE_RUNTIME_ERRORS = (
    "Traceback",
    "ImportError",
    "Exception:",
    "AttributeError",
    "TypeError",
    "ValueError",
    "NameError",
    "SyntaxError",
)


def classify_opencode(tool_name: str, content: str, status: str = "") -> str:
    """OpenCode 判定：优先用 runner 保留的 state.status，无则退回 content 推断。

    OpenCode 无 harness 层 format_error（工具名/参数由 OpenCode 自身校验），
    故本 classifier 不产出 format_error，格式准确率对 OpenCode 恒 100%。
    业务错误（如 {"error":"rate_limit"}）status 仍为 completed，正确归 success。
    """
    st = (status or "").lower()
    if st == "completed":
        return "success"
    if st == "error":
        return "failure"
    if st in ("running", "pending"):
        return "unclear"

    # 存量轨迹无 status 字段 → content 推断兜底
    text = (content or "").lstrip()
    if any(text.startswith(kw) or ("\n" + kw) in text[:200] for kw in _OPENCODE_RUNTIME_ERRORS):
        return "failure"
    if text:
        return "success"  # 有正常返回内容（含业务 error JSON）视为工具执行成功
    return "unclear"


register_classifier(("codex", "astroncode"), classify_codex)
register_classifier(("opencode",), classify_opencode)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def parse_tool_metrics(transcript_path: Path | None, harness: str) -> dict:
    """统计一条轨迹的工具调用指标。

    返回 {total, success, failure, format_error, unclear, by_tool}。
    by_tool: {tool_name: {total, success, failure, format_error, unclear}}。
    未注册 harness 或无轨迹 → 空指标（total=0）。
    """
    classifier = _CLASSIFIERS.get(harness)
    if classifier is None:
        return _empty()

    pairs = _load_tool_pairs(transcript_path)
    if not pairs:
        return _empty()

    result = _empty()
    by_tool = result["by_tool"]
    for tool_name, content, status in pairs:
        category = classifier(tool_name, content, status)
        if category not in CATEGORIES:
            category = "unclear"
        result["total"] += 1
        result[category] += 1
        bucket = by_tool.setdefault(
            tool_name,
            {"total": 0, "success": 0, "failure": 0, "format_error": 0, "unclear": 0},
        )
        bucket["total"] += 1
        bucket[category] += 1

    return result


# ---------------------------------------------------------------------------
# 比率派生（供报告/平台展示；分母为 0 时返回 None，由调用方渲染 N/A）
# ---------------------------------------------------------------------------

def format_accuracy(m: dict) -> float | None:
    """格式准确率 = (total - format_error) / total。"""
    total = m.get("total", 0)
    if not total:
        return None
    return (total - m.get("format_error", 0)) / total


def execution_success_rate(m: dict) -> float | None:
    """执行成功率 = success / (success + failure)。分母 0 → None。"""
    denom = m.get("success", 0) + m.get("failure", 0)
    if not denom:
        return None
    return m.get("success", 0) / denom


def overall_success_rate(m: dict) -> float | None:
    """综合成功率 = success / total。"""
    total = m.get("total", 0)
    if not total:
        return None
    return m.get("success", 0) / total


def unclear_ratio(m: dict) -> float | None:
    """不确定占比 = unclear / total。"""
    total = m.get("total", 0)
    if not total:
        return None
    return m.get("unclear", 0) / total


def merge_metrics(metrics_list: list[dict]) -> dict:
    """把多条（用例级）指标聚合成一条（unit 级）。"""
    agg = _empty()
    by_tool = agg["by_tool"]
    for m in metrics_list:
        if not m:
            continue
        for key in ("total", "success", "failure", "format_error", "unclear"):
            agg[key] += m.get(key, 0)
        for tool_name, bucket in (m.get("by_tool") or {}).items():
            dst = by_tool.setdefault(
                tool_name,
                {"total": 0, "success": 0, "failure": 0, "format_error": 0, "unclear": 0},
            )
            for key in ("total", "success", "failure", "format_error", "unclear"):
                dst[key] += bucket.get(key, 0)
    return agg
