"""Harness 工具调用指标：从归一化轨迹 chat_openclaw.jsonl 统计工具调用情况。

口径与设计见 docs/local/design/Harness工具调用指标设计.md。

四类互斥判定（每次 tool_use 归入其一）：
    success       工具被执行且明确成功
    failure       工具被执行但明确失败（运行时异常、非0退出码）
    format_error  harness 拒绝：工具名不支持 / 参数格式错误
    unclear       无法判定：后台进程、超时、无明确标记

通用解析派生四个比率（上层从计数算，与 harness 无关）：
    格式准确率   = (total - format_error) / total
    执行成功率   = success / (success + failure)
    综合成功率   = success / total
    不确定占比   = unclear / total

跨 harness 差异用注册表模式隔离：每个 harness 注册一个 classifier
((tool_name, content, status) -> category)，新增 harness 只需写一个函数 + 一行注册。
纯标准库，无第三方依赖，供报告脚本与平台后端共同 import。

报告生成对 OpenCode、DeepSeek Harness、HermesAgent 使用独立入口
parse_report_tool_metrics：按 tool_use 尝试计数并在报告阶段校验格式，
不改变 Harness 执行、评分或其他调用方的通用解析口径。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

CATEGORIES = ("success", "failure", "format_error", "unclear")
REPORT_FORMAT_HARNESSES = frozenset({"opencode", "deepseek-harness", "hermesagent"})

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
    - status 优先保留原生字段；`is_error=true` 统一折算为 error
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
            if btype in {"tool_use", "toolCall"}:
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
                if not status and block.get("is_error") is True:
                    status = "error"
                pairs.append((name, content_text, status))

        # OpenClaw/AstronClaw 原生轨迹把 toolResult 放在 message 本身，
        # details.status 才是工具执行状态；外层 isError 在业务错误时仍可能为 false。
        if str(message.get("role") or "") == "toolResult":
            call_id = str(message.get("toolCallId") or "")
            name = str(message.get("toolName") or tool_names.get(call_id) or "unknown")
            details = message.get("details")
            details = details if isinstance(details, dict) else {}
            content_text = json.dumps(content_blocks, ensure_ascii=False)
            if details.get("error"):
                content_text = f"{content_text}\n{details['error']}"
            status = str(details.get("status") or "")
            if not status and message.get("isError") is True:
                status = "error"
            pairs.append((name, content_text, status))

    return pairs


def _load_tool_attempts_and_results(
    transcript_path: Path | None,
) -> tuple[list[dict], dict[str, list[tuple[str, str]]]]:
    """读取报告侧格式校验所需的调用尝试及结果，不改变通用解析口径。"""
    if transcript_path is None:
        return [], {}
    path = Path(transcript_path)
    if not path.is_file():
        return [], {}
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], {}

    attempts: list[dict] = []
    results: dict[str, list[tuple[str, str]]] = {}
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
            block_type = block.get("type")
            if block_type in {"tool_use", "toolCall"}:
                arguments = (
                    block.get("arguments", block.get("input", {}))
                    if block_type == "toolCall"
                    else block.get("input", block.get("arguments", {}))
                )
                attempts.append(
                    {
                        "call_id": str(block.get("id") or ""),
                        "tool_name": str(block.get("name") or "unknown"),
                        "arguments": arguments,
                    }
                )
            elif block_type == "tool_result":
                call_id = str(block.get("tool_use_id") or "")
                content = block.get("content")
                content_text = (
                    content
                    if isinstance(content, str)
                    else json.dumps(content, ensure_ascii=False)
                )
                status = str(block.get("status") or "")
                if not status and block.get("is_error") is True:
                    status = "error"
                results.setdefault(call_id, []).append((content_text, status))
    return attempts, results


def _invalid_argument_shape(arguments) -> bool:
    """判断归一化后仍可确定的参数结构错误。"""
    parsed = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return True
    if not isinstance(parsed, dict):
        return True
    return "_raw" in parsed or "_value" in parsed


_FORMAT_REJECTION_MARKERS = (
    "unknown tool",
    "unsupported tool",
    "unsupported call",
    "tool not found",
    "failed to parse function arguments",
    "invalid tool arguments",
    "invalid arguments for tool",
    "tool input validation",
    "arguments must be an object",
    "arguments must be a json object",
)


def _result_error_text(content: str) -> str:
    stripped = (content or "").strip()
    if not stripped:
        return ""
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return " ".join(
            str(error.get(key) or "") for key in ("type", "code", "message")
        ).strip()
    if error is not None:
        return str(error)
    return str(payload.get("message") or "")


def _is_report_format_rejection(content: str, status: str) -> bool:
    error_text = _result_error_text(content)
    if not error_text:
        return False
    normalized = error_text.strip().lower()
    normalized_status = (status or "").strip().lower()
    if normalized_status in {"completed", "success", "ok"}:
        return False
    status_is_error = normalized_status in {"error", "failed", "failure"}
    explicit_error_payload = bool(
        (content or "").lstrip().startswith("{") and error_text != (content or "").strip()
    )
    if not status_is_error and not explicit_error_payload:
        return normalized.startswith(_FORMAT_REJECTION_MARKERS)
    return any(marker in normalized for marker in _FORMAT_REJECTION_MARKERS)


def _schema_accepts(value, schema: dict) -> bool:
    """校验报告需要的 JSON Schema 子集；未知关键字不影响结论。"""
    if not isinstance(schema, dict):
        return True
    if "const" in schema and value != schema["const"]:
        return False
    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        return False
    if isinstance(schema.get("allOf"), list) and not all(
        _schema_accepts(value, item) for item in schema["allOf"]
    ):
        return False
    if isinstance(schema.get("anyOf"), list) and not any(
        _schema_accepts(value, item) for item in schema["anyOf"]
    ):
        return False
    if isinstance(schema.get("oneOf"), list):
        if sum(_schema_accepts(value, item) for item in schema["oneOf"]) != 1:
            return False

    expected = schema.get("type")
    expected_types = expected if isinstance(expected, list) else [expected]
    expected_types = [item for item in expected_types if isinstance(item, str)]
    type_checks = {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }
    if expected_types and not any(type_checks.get(item, True) for item in expected_types):
        return False

    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list) and any(key not in value for key in required):
            return False
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, item in value.items():
                if key in properties and not _schema_accepts(item, properties[key]):
                    return False
            if schema.get("additionalProperties") is False:
                if any(key not in properties for key in value):
                    return False
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        if any(not _schema_accepts(item, schema["items"]) for item in value):
            return False
    return True


def _parse_call_arguments(raw_arguments) -> tuple[bool, object]:
    if not isinstance(raw_arguments, str):
        return True, raw_arguments
    try:
        return True, json.loads(raw_arguments)
    except json.JSONDecodeError:
        return False, raw_arguments


def _deepseek_format_decisions(run_dir: Path | None) -> dict[str, bool]:
    """从 DSH 原生会话返回 call_id -> 是否格式错误。"""
    if run_dir is None:
        return {}
    session_root = Path(run_dir) / "dsh_sessions"
    if not session_root.is_dir():
        return {}

    decisions: dict[str, bool] = {}
    for session_path in sorted(session_root.rglob("session.jsonl")):
        schemas: dict[str, dict] = {}
        try:
            lines = session_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            if event_type == "request/header":
                header = data.get("header") if isinstance(data.get("header"), dict) else {}
                tools = header.get("tools") if isinstance(header.get("tools"), list) else []
                schemas = {}
                for tool in tools:
                    if not isinstance(tool, dict):
                        continue
                    function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
                    name = str(function.get("name") or "")
                    parameters = function.get("parameters")
                    if name and isinstance(parameters, dict):
                        schemas[name] = parameters
                continue

            calls: list[tuple[str, str, object]] = []
            if event_type == "tool/call":
                calls.append(
                    (
                        str(data.get("callId") or ""),
                        str(data.get("name") or ""),
                        data.get("arguments", {}),
                    )
                )
            elif event_type == "assistant/message":
                message = data.get("message") if isinstance(data.get("message"), dict) else {}
                blocks = message.get("content") if isinstance(message.get("content"), list) else []
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") not in {
                        "tool-call", "toolCall", "tool_use",
                    }:
                        continue
                    calls.append(
                        (
                            str(block.get("id") or block.get("callId") or ""),
                            str(block.get("name") or block.get("tool_name") or ""),
                            block.get("arguments", block.get("input", block.get("args", {}))),
                        )
                    )

            if not schemas:
                continue
            for call_id, tool_name, raw_arguments in calls:
                parsed_ok, arguments = _parse_call_arguments(raw_arguments)
                decisions[call_id] = (
                    not call_id
                    or tool_name not in schemas
                    or not parsed_ok
                    or not _schema_accepts(arguments, schemas.get(tool_name, {}))
                )
    return decisions


# ---------------------------------------------------------------------------
# Codex classifier（同时供 AstronCode 旧轨迹兜底）
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

    # 2b. Codex GPT-5.6-sol 格式（Script completed/failed）
    if "Script completed" in text:
        return "success"
    if "Script failed" in text:
        return "failure"

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
# AstronCode classifier（兼容 Codex 旧轨迹与新版原生工具返回）
# ---------------------------------------------------------------------------

_ASTRONCODE_FETCH_TOOLS = {
    "fetch",
    "get",
    "stealthy_fetch",
    "bulk_fetch",
    "bulk_get",
    "bulk_stealthy_fetch",
    "web_search",
}
_ASTRONCODE_PLAIN_RESULT_TOOLS = {"web-search"}
_ASTRONCODE_DISCOVERY_TOOLS = {"glob", "grep"}
_ASTRONCODE_JSON_TOOLS = {
    "close_session",
    "list_mcp_resources",
    "list_mcp_resource_templates",
    "open_session",
    "screenshot",
}
_ASTRONCODE_FILE_SUCCESS_MARKERS = (
    "Created file",
    "Updated file",
    "Deleted file",
)
_ASTRONCODE_FAILURE_PREFIXES = (
    "cannot read ",
    "cannot write ",
    "cannot edit ",
    "error reading ",
    "error writing ",
    "error editing ",
    "failed to read ",
    "failed to write ",
    "failed to edit ",
    "error executing tool ",
    "tool error:",
    "view_image is not allowed",
)


def _is_format_error(text: str) -> bool:
    stripped = text.lstrip()
    return (
        stripped.startswith("unsupported call:")
        or stripped.startswith("failed to parse function arguments:")
        or stripped.startswith("approval policy is Never; reject command")
    )


def _astroncode_failure_prefix(text: str) -> bool:
    low = text.lstrip().lower()
    return low.startswith(_ASTRONCODE_FAILURE_PREFIXES)


def _astroncode_json_payload(text: str):
    candidate = (
        text.split("Output:", 1)[1].strip()
        if "Output:" in text
        else text.strip()
    )
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        return None


def _astroncode_structured_result(payload) -> str:
    if isinstance(payload, dict):
        status = payload.get("status")
        if isinstance(status, int):
            return "success" if 200 <= status < 400 else "failure"
        if isinstance(status, str):
            normalized = status.strip().lower()
            if normalized in {"success", "completed", "ok"}:
                return "success"
            if normalized in {"error", "failed", "failure"}:
                return "failure"
            if normalized in {"running", "pending"}:
                return "unclear"
        if payload.get("error"):
            return "failure"
        if "result" in payload:
            return _astroncode_structured_result(payload["result"])
        if "resources" in payload or "content" in payload:
            return "success"
        return "success"

    if isinstance(payload, list):
        categories = []
        for item in payload:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text") or "")
                categories.append(
                    "failure" if _astroncode_failure_prefix(text) else "success"
                )
            else:
                categories.append(_astroncode_structured_result(item))
        if "failure" in categories:
            return "failure"
        if "unclear" in categories:
            return "unclear"
        return "success"

    if payload is None:
        return "unclear"
    return "success"


def classify_astroncode(tool_name: str, content: str, status: str = "") -> str:
    """AstronCode 判定：优先使用结构化状态和新版工具返回契约。"""
    text = content or ""
    normalized_status = (status or "").strip().lower()

    if normalized_status in {"completed", "success", "ok"}:
        return "success"
    if normalized_status in {"error", "failed", "failure"}:
        return "format_error" if _is_format_error(text) else "failure"
    if normalized_status in {"running", "pending"}:
        return "unclear"

    if _is_format_error(text):
        return "format_error"

    stripped = text.lstrip()
    if _astroncode_failure_prefix(stripped):
        return "failure"

    if tool_name == "bash":
        match = re.match(r"Exit code:\s*(-?\d+)", stripped)
        if match:
            return "success" if int(match.group(1)) == 0 else "failure"

    if tool_name == "read":
        if all(marker in text for marker in ("<path>", "<type>", "<content>")):
            return "success"

    if tool_name in {"write", "edit"}:
        if "<path>" in text and any(
            marker in text for marker in _ASTRONCODE_FILE_SUCCESS_MARKERS
        ):
            return "success"

    if tool_name in _ASTRONCODE_DISCOVERY_TOOLS:
        return "success" if stripped else "unclear"

    if tool_name in _ASTRONCODE_FETCH_TOOLS:
        payload = _astroncode_json_payload(text)
        if payload is not None:
            return _astroncode_structured_result(payload)
        http_status = re.search(r'\{\s*"status"\s*:\s*(\d+)', stripped)
        if http_status:
            return "success" if 200 <= int(http_status.group(1)) < 400 else "failure"

    if tool_name in _ASTRONCODE_PLAIN_RESULT_TOOLS:
        return "success" if stripped else "unclear"

    if tool_name in _ASTRONCODE_JSON_TOOLS:
        payload = _astroncode_json_payload(text)
        if payload is not None:
            return _astroncode_structured_result(payload)

    return classify_codex(tool_name, text, status)


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
    故本通用 classifier 不产出 format_error；报告另走调用尝试校验。
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


def classify_openclaw(tool_name: str, content: str, status: str = "") -> str:
    """OpenClaw/AstronClaw 判定：以 details.status 为权威状态。"""
    st = (status or "").lower()
    text = content or ""
    low = text.lower()
    if st == "error":
        if "unknown tool" in low or "unsupported call" in low or "invalid arguments" in low:
            return "format_error"
        return "failure"
    if st == "completed":
        return "success"
    if st in {"running", "pending"}:
        return "unclear"
    if '"status": "error"' in low or '"status":"error"' in low:
        return "failure"
    if text:
        return "success"
    return "unclear"


def classify_deepseek_harness(tool_name: str, content: str, status: str = "") -> str:
    """DeepSeek Harness：以 DSH tool_result.status 为权威状态。"""
    _ = tool_name
    st = (status or "").lower()
    if st == "completed":
        return "success"
    if st == "error":
        return "failure"
    if st in {"running", "pending"}:
        return "unclear"
    return "success" if content else "unclear"


def classify_hermesagent(tool_name: str, content: str, status: str = "") -> str:
    """HermesAgent：优先读取工具结果 JSON 中的 status/success 字段。"""
    _ = tool_name
    st = (status or "").strip().lower()
    payload = None
    if content:
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            payload = None

    if isinstance(payload, dict):
        payload_status = str(payload.get("status") or "").strip().lower()
        st = payload_status or st
        if payload.get("success") is False:
            return "failure"
        if payload.get("success") is True:
            return "success"

    if st in {"error", "failed", "failure"}:
        return "failure"
    if st in {"success", "completed", "ok"}:
        return "success"
    if st in {"running", "pending"}:
        return "unclear"
    return "success" if content else "unclear"


def classify_claudecode(tool_name: str, content: str, status: str = "") -> str:
    """ClaudeCode：优先使用转换轨迹保留的 tool_result.is_error。"""
    _ = tool_name
    st = (status or "").strip().lower()
    text = content or ""

    if st in {"error", "failed", "failure"}:
        return "format_error" if _is_format_error(text) else "failure"
    if st in {"success", "completed", "ok"}:
        return "success"
    if st in {"running", "pending"}:
        return "unclear"
    if _is_format_error(text):
        return "format_error"
    return "success" if text else "unclear"


register_classifier(("codex",), classify_codex)
register_classifier(("astroncode",), classify_astroncode)
register_classifier(("opencode",), classify_opencode)
register_classifier(("openclaw", "astronclaw"), classify_openclaw)
register_classifier(("deepseek-harness",), classify_deepseek_harness)
register_classifier(("hermesagent",), classify_hermesagent)
register_classifier(("claudecode",), classify_claudecode)


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


def _increment_metric(result: dict, tool_name: str, category: str) -> None:
    result["total"] += 1
    result[category] += 1
    bucket = result["by_tool"].setdefault(
        tool_name,
        {
            "total": 0,
            "success": 0,
            "failure": 0,
            "format_error": 0,
            "unclear": 0,
            "format_unresolved": 0,
        },
    )
    bucket["total"] += 1
    bucket[category] += 1


def _combined_result_category(
    classifier: Classifier,
    tool_name: str,
    result_records: list[tuple[str, str]],
) -> str:
    categories = {
        classifier(tool_name, content, status)
        for content, status in result_records
    }
    for category in ("format_error", "failure", "success", "unclear"):
        if category in categories:
            return category
    return "unclear"


def parse_report_tool_metrics(
    transcript_path: Path | None,
    harness: str,
    run_dir: Path | None = None,
) -> dict:
    """报告专用口径：三类 Harness 按调用尝试校验格式，其他 Harness 保持原口径。

    OpenCode、DeepSeek Harness、HermesAgent 的通用 classifier 不产出
    format_error。报告侧改为读取 tool_use 尝试：明确的参数结构错误、工具拒绝，
    以及 DSH 原生 request/header 中 Schema 校验失败均计为 format_error。
    无结果且无法取得 Schema 的调用计为 unclear，并使报告格式准确率显示 `-`。
    """
    if harness not in REPORT_FORMAT_HARNESSES:
        return parse_tool_metrics(transcript_path, harness)
    classifier = _CLASSIFIERS.get(harness)
    if classifier is None:
        return _empty()

    attempts, results_by_id = _load_tool_attempts_and_results(transcript_path)
    result = _empty()
    result["format_unresolved"] = 0
    if not attempts and not results_by_id:
        return result

    deepseek_decisions = (
        _deepseek_format_decisions(run_dir)
        if harness == "deepseek-harness"
        else {}
    )
    remaining_results = {
        call_id: list(records) for call_id, records in results_by_id.items()
    }
    for attempt in attempts:
        call_id = attempt["call_id"]
        tool_name = attempt["tool_name"]
        result_records = remaining_results.pop(call_id, [])
        structural_error = (
            not call_id
            or not tool_name
            or tool_name == "unknown"
            or _invalid_argument_shape(attempt["arguments"])
        )
        schema_error = deepseek_decisions.get(call_id)
        result_format_error = any(
            _is_report_format_rejection(content, status)
            for content, status in result_records
        )
        if structural_error or schema_error is True or result_format_error:
            category = "format_error"
        elif result_records:
            category = _combined_result_category(classifier, tool_name, result_records)
        else:
            category = "unclear"
            if schema_error is not False:
                result["format_unresolved"] += 1
        _increment_metric(result, tool_name, category)
        if category == "unclear" and schema_error is not False and not result_records:
            result["by_tool"][tool_name]["format_unresolved"] += 1

    for orphan_records in remaining_results.values():
        if not orphan_records:
            continue
        result["format_unresolved"] += 1

    return result


# ---------------------------------------------------------------------------
# 比率派生（供报告/平台展示；分母为 0 时返回 None，由调用方决定展示）
# ---------------------------------------------------------------------------

def format_accuracy(m: dict) -> float | None:
    """格式准确率 = (total - format_error) / total。"""
    if m.get("format_unresolved", 0):
        return None
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
    if any("format_unresolved" in metrics for metrics in metrics_list if metrics):
        agg["format_unresolved"] = 0
    for m in metrics_list:
        if not m:
            continue
        for key in ("total", "success", "failure", "format_error", "unclear"):
            agg[key] += m.get(key, 0)
        if "format_unresolved" in agg:
            agg["format_unresolved"] += m.get("format_unresolved", 0)
        for tool_name, bucket in (m.get("by_tool") or {}).items():
            dst = by_tool.setdefault(
                tool_name,
                {
                    "total": 0,
                    "success": 0,
                    "failure": 0,
                    "format_error": 0,
                    "unclear": 0,
                },
            )
            for key in ("total", "success", "failure", "format_error", "unclear"):
                dst[key] += bucket.get(key, 0)
            if "format_unresolved" in bucket:
                dst["format_unresolved"] = (
                    dst.get("format_unresolved", 0)
                    + bucket.get("format_unresolved", 0)
                )
    return agg
