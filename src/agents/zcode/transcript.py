from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ZCodeTraceFormatError(ValueError):
    """Raised when a ZCode stream-json trace cannot be converted safely."""


@dataclass(frozen=True)
class ConversionResult:
    messages: list[dict[str, Any]]
    usage: dict[str, Any]
    source: dict[str, Any]
    terminal_result: dict[str, Any] | None


_KNOWN_EVENT_TYPES = frozenset(
    {
        "session.created",
        "session.resumed",
        "session.updated",
        "session.titleUpdated",
        "session.closed",
        "turn.started",
        "turn.steerQueued",
        "turn.steerDrained",
        "turn.completed",
        "turn.failed",
        "message.upserted",
        "message.removed",
        "part.started",
        "part.delta",
        "part.upserted",
        "part.removed",
        "model.streaming",
        "tool.updated",
        "permission.requested",
        "permission.resolved",
        "userInput.requested",
        "userInput.resolved",
        "checkpoint.created",
        "rewind.triggered",
        "streamRecovery.updated",
        "workflow.run.progress",
    }
)


def _empty_usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "provider_total_tokens": 0,
        "cost_usd": 0.0,
        "request_count": 0,
        "cost_status": "not_applicable",
        "cost_source": "none",
        "cost_scope": "none",
        "cost_reason": "",
        "usage_source": "unavailable",
        "usage_complete": False,
        "request_count_source": "unavailable",
    }


def _nonnegative_int(value: Any, *, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ZCodeTraceFormatError(f"{field} must be a non-negative integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ZCodeTraceFormatError(f"{field} must be a non-negative integer") from exc
    if number < 0 or (isinstance(value, float) and not value.is_integer()):
        raise ZCodeTraceFormatError(f"{field} must be a non-negative integer")
    return number


def _read_trace(path: Path, *, allow_incomplete: bool) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ZCodeTraceFormatError(f"cannot read ZCode trace {path}: {exc}") from exc

    rows: list[dict[str, Any]] = []
    previous_sequence = -1
    identity: tuple[str, str] | None = None
    terminal_seen = False
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ZCodeTraceFormatError(
                f"invalid JSON in {path} line {line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise ZCodeTraceFormatError(
                f"trace row in {path} line {line_number} is not an object"
            )
        row_type = str(row.get("type") or "")
        if terminal_seen:
            raise ZCodeTraceFormatError("events cannot follow the ZCode result row")
        if row_type == "result":
            terminal_seen = True
            if not str(row.get("sessionId") or "") or not isinstance(row.get("response"), str):
                raise ZCodeTraceFormatError("invalid ZCode result row")
            rows.append(row)
            continue
        if row_type not in _KNOWN_EVENT_TYPES:
            raise ZCodeTraceFormatError(
                f"unsupported ZCode event type {row_type!r} in {path} line {line_number}"
            )
        sequence = _nonnegative_int(row.get("seq"), field="seq")
        if sequence <= previous_sequence:
            raise ZCodeTraceFormatError(
                f"seq must increase strictly in {path} line {line_number}"
            )
        previous_sequence = sequence
        _nonnegative_int(row.get("timestamp"), field="timestamp")
        current_identity = (str(row.get("sessionId") or ""), str(row.get("traceId") or ""))
        if not current_identity[0]:
            raise ZCodeTraceFormatError(
                f"sessionId missing in {path} line {line_number}"
            )
        if identity is None:
            identity = current_identity
        elif current_identity[0] != identity[0]:
            raise ZCodeTraceFormatError(
                f"sessionId changed in {path} line {line_number}"
            )
        rows.append(row)

    if not rows:
        raise ZCodeTraceFormatError(f"ZCode trace is empty: {path}")
    if not allow_incomplete and not terminal_seen:
        raise ZCodeTraceFormatError("ZCode result row is missing")
    return rows


def _message(role: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "message", "message": {"role": role, "content": blocks}}


def _serialize(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tool_input(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"_raw": value}
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    return {"_value": value}


def _usage_from_terminal(terminal: dict[str, Any] | None) -> dict[str, Any]:
    usage = _empty_usage()
    raw = terminal.get("usage") if isinstance(terminal, dict) else None
    if not isinstance(raw, dict):
        return usage
    mapping = {
        "inputTokens": "input_tokens",
        "outputTokens": "output_tokens",
        "cacheReadTokens": "cache_read_tokens",
        "cacheWriteTokens": "cache_write_tokens",
        "reasoningTokens": "reasoning_tokens",
    }
    for source, destination in mapping.items():
        usage[destination] = _nonnegative_int(raw.get(source), field=source)
    native_total = raw.get("totalTokens")
    if native_total is not None:
        usage["provider_total_tokens"] = _nonnegative_int(
            native_total, field="totalTokens"
        )
    usage["total_tokens"] = sum(
        usage[field]
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        )
    )
    usage["request_count"] = _nonnegative_int(
        raw.get("modelRequestCount"), field="modelRequestCount"
    )
    usage["request_count_source"] = "zcode_result_usage"
    usage["usage_source"] = str(raw.get("source") or "zcode_result")
    usage["usage_complete"] = True
    usage.update(
        {
            "cost_status": "unavailable",
            "cost_source": "none",
            "cost_scope": "model_tokens_only",
            "cost_reason": (
                "ZCode stream-json exposes aggregate provider token usage but not cost; "
                "calculate cost from the model pricing registry when generating the report"
            ),
        }
    )
    return usage


def _openclaw_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "input": usage["input_tokens"],
        "output": usage["output_tokens"],
        "cacheRead": usage["cache_read_tokens"],
        "cacheWrite": usage["cache_write_tokens"],
        "totalTokens": usage["total_tokens"],
        "cost": {"total": 0.0},
    }


def convert_trace(
    trace_path: Path,
    *,
    prompt: str = "",
    allow_incomplete: bool = False,
) -> ConversionResult:
    trace_path = Path(trace_path)
    rows = _read_trace(trace_path, allow_incomplete=allow_incomplete)
    messages: list[dict[str, Any]] = []
    if prompt:
        messages.append(_message("user", [{"type": "text", "text": prompt}]))

    pending_reasoning: list[str] = []
    pending_text: list[str] = []
    terminal: dict[str, Any] | None = None
    terminal_response = ""
    tool_uses: set[str] = set()
    tool_results: set[str] = set()

    def flush_assistant() -> None:
        blocks: list[dict[str, Any]] = []
        reasoning = "".join(pending_reasoning)
        text = "".join(pending_text)
        if reasoning:
            blocks.append({"type": "reasoning", "text": reasoning})
        if text:
            blocks.append({"type": "text", "text": text})
        pending_reasoning.clear()
        pending_text.clear()
        if blocks:
            messages.append(_message("assistant", blocks))

    for row in rows:
        row_type = row["type"]
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if row_type == "result":
            terminal = row
            terminal_response = str(row.get("response") or "")
            continue
        if row_type == "model.streaming":
            kind = str(payload.get("kind") or "")
            delta = payload.get("delta")
            if isinstance(delta, str):
                if kind == "reasoning_delta":
                    pending_reasoning.append(delta)
                elif kind == "text_delta":
                    pending_text.append(delta)
            continue
        if row_type == "tool.updated":
            kind = str(payload.get("kind") or "")
            call_id = str(payload.get("toolCallId") or "")
            tool_name = str(payload.get("toolName") or "")
            if kind == "scheduled" and call_id and tool_name and call_id not in tool_uses:
                flush_assistant()
                messages.append(
                    _message(
                        "assistant",
                        [
                            {
                                "type": "tool_use",
                                "id": call_id,
                                "name": tool_name,
                                "input": _tool_input(payload.get("input", {})),
                            }
                        ],
                    )
                )
                tool_uses.add(call_id)
            elif kind in {"result", "error"} and call_id and call_id not in tool_results:
                flush_assistant()
                if kind == "result":
                    result = payload.get("result")
                    result_object = result if isinstance(result, dict) else {}
                    content = _serialize(result_object.get("content", result))
                    status = "completed" if result_object.get("success") is not False else "error"
                else:
                    content = _serialize(payload.get("error"))
                    status = "error"
                messages.append(
                    _message(
                        "user",
                        [
                            {
                                "type": "tool_result",
                                "tool_use_id": call_id,
                                "content": content,
                                "status": status,
                            }
                        ],
                    )
                )
                tool_results.add(call_id)
            continue
        if row_type == "turn.failed":
            flush_assistant()
            error = payload.get("error")
            if error:
                messages.append(
                    _message("assistant", [{"type": "text", "text": _serialize(error)}])
                )
            continue
        if row_type == "turn.completed":
            response = str(payload.get("response") or "")
            if response and not pending_text:
                pending_text.append(response)
            flush_assistant()

    flush_assistant()
    if terminal_response:
        assistant_text = "\n".join(
            str(block.get("text") or "")
            for entry in messages
            if entry.get("message", {}).get("role") == "assistant"
            for block in entry.get("message", {}).get("content", [])
            if block.get("type") == "text"
        )
        if terminal_response not in assistant_text:
            messages.append(
                _message("assistant", [{"type": "text", "text": terminal_response}])
            )

    usage = _usage_from_terminal(terminal)
    if usage["request_count"]:
        assistant_entries = [
            entry for entry in messages if entry.get("message", {}).get("role") == "assistant"
        ]
        if not assistant_entries:
            assistant_entries = [_message("assistant", [])]
            messages.extend(assistant_entries)
        assistant_entries[-1]["message"]["usage"] = _openclaw_usage(usage)

    first_event = next((row for row in rows if row.get("type") != "result"), {})
    source = {
        "trace": trace_path.name,
        "session_id": str((terminal or first_event).get("sessionId") or ""),
        "trace_id": str((terminal or first_event).get("traceId") or ""),
        "event_count": sum(1 for row in rows if row.get("type") != "result"),
        "tool_use_count": len(tool_uses),
        "tool_result_count": len(tool_results),
        "terminal_complete": terminal is not None,
    }
    return ConversionResult(messages, usage, source, terminal)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def write_conversion(
    trace_path: Path,
    output_dir: Path,
    *,
    prompt: str = "",
    allow_incomplete: bool = False,
) -> ConversionResult:
    result = convert_trace(
        trace_path,
        prompt=prompt,
        allow_incomplete=allow_incomplete,
    )
    output_dir = Path(output_dir)
    chat = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in result.messages
    )
    _atomic_write(output_dir / "chat.jsonl", chat)
    _atomic_write(
        output_dir / "usage.json",
        json.dumps(result.usage, ensure_ascii=False, indent=2) + "\n",
    )
    manifest = {
        "format": "wildclawbench-openclaw-transcript-v1",
        "source_format": "zcode-headless-stream-json-v1",
        "source": result.source,
        "message_count": len(result.messages),
        "usage": result.usage,
        "terminal_result": result.terminal_result,
    }
    _atomic_write(
        output_dir / "conversion_manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return result
