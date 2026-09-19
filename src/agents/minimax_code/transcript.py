from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class McodeTraceFormatError(ValueError):
    """Raised when an mcode stream-json trace cannot be converted safely."""


@dataclass(frozen=True)
class ConversionResult:
    messages: list[dict[str, Any]]
    usage: dict[str, Any]
    source: dict[str, Any]
    terminal_result: dict[str, Any] | None


_EVENT_TYPES = frozenset(
    {
        "exec.started",
        "session.started",
        "session.resumed",
        "turn.started",
        "item.started",
        "item.updated",
        "item.completed",
        "turn.completed",
        "turn.failed",
        "exec.completed",
    }
)
_USAGE_FIELDS = (
    ("inputTokens", "input_tokens", "input"),
    ("outputTokens", "output_tokens", "output"),
    ("cacheReadTokens", "cache_read_tokens", "cacheRead"),
    ("cacheWriteTokens", "cache_write_tokens", "cacheWrite"),
)


def _empty_usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
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
        raise McodeTraceFormatError(f"{field} must be a non-negative integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise McodeTraceFormatError(f"{field} must be a non-negative integer") from exc
    if number < 0 or (isinstance(value, float) and not value.is_integer()):
        raise McodeTraceFormatError(f"{field} must be a non-negative integer")
    return number


def _read_trace(path: Path, *, allow_incomplete: bool) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise McodeTraceFormatError(f"cannot read mcode trace {path}: {exc}") from exc

    events: list[dict[str, Any]] = []
    previous_sequence = 0
    identity: tuple[str, str, str] | None = None
    terminal_count = 0
    turn_terminal_count = 0
    finalized_items: set[str] = set()
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise McodeTraceFormatError(
                f"invalid JSON in {path} line {line_number}"
            ) from exc
        if not isinstance(event, dict):
            raise McodeTraceFormatError(
                f"trace row in {path} line {line_number} is not an object"
            )
        if event.get("schemaVersion") != 1:
            raise McodeTraceFormatError(
                f"unsupported schemaVersion in {path} line {line_number}"
            )
        event_type = event.get("type")
        if event_type not in _EVENT_TYPES:
            raise McodeTraceFormatError(
                f"unsupported event type {event_type!r} in {path} line {line_number}"
            )
        sequence = _nonnegative_int(event.get("sequence"), field="sequence")
        if sequence <= previous_sequence:
            raise McodeTraceFormatError(
                f"sequence must increase strictly in {path} line {line_number}"
            )
        previous_sequence = sequence
        timestamp = event.get("timestampMs")
        _nonnegative_int(timestamp, field="timestampMs")
        current_identity = tuple(
            str(event.get(field) or "") for field in ("runId", "sessionId", "turnId")
        )
        if not all(current_identity):
            raise McodeTraceFormatError(
                f"runId/sessionId/turnId missing in {path} line {line_number}"
            )
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise McodeTraceFormatError(
                f"trace identity changed in {path} line {line_number}"
            )

        if terminal_count:
            raise McodeTraceFormatError("events cannot follow exec.completed")
        if event_type == "exec.completed":
            terminal_count += 1
            _validate_terminal_result(event, identity, path, line_number)
        elif event_type in {"turn.completed", "turn.failed"}:
            turn_terminal_count += 1
            if turn_terminal_count > 1:
                raise McodeTraceFormatError("turn terminal event appeared more than once")
        elif event_type.startswith("item."):
            item = event.get("item")
            if not isinstance(item, dict) or not str(item.get("id") or ""):
                raise McodeTraceFormatError(
                    f"invalid item in {path} line {line_number}"
                )
            item_id = str(item["id"])
            if item_id in finalized_items:
                raise McodeTraceFormatError(f"item {item_id!r} changed after completion")
            if event_type == "item.completed":
                finalized_items.add(item_id)
        events.append(event)

    if not events:
        raise McodeTraceFormatError(f"mcode trace is empty: {path}")
    if not allow_incomplete and terminal_count != 1:
        raise McodeTraceFormatError("exec.completed is missing")
    if terminal_count == 1 and turn_terminal_count != 1:
        raise McodeTraceFormatError("terminal trace must contain one turn terminal event")
    return events


def _validate_terminal_result(
    event: dict[str, Any],
    identity: tuple[str, str, str],
    path: Path,
    line_number: int,
) -> None:
    result = event.get("result")
    if not isinstance(result, dict):
        raise McodeTraceFormatError(
            f"exec.completed result missing in {path} line {line_number}"
        )
    if result.get("schemaVersion") != 1 or result.get("type") != "exec.result":
        raise McodeTraceFormatError("invalid exec.completed result contract")
    if tuple(str(result.get(field) or "") for field in ("runId", "sessionId", "turnId")) != identity:
        raise McodeTraceFormatError("exec.completed result identity does not match the trace")
    if result.get("status") not in {
        "succeeded",
        "failed",
        "timeout",
        "cancelled",
        "limit_exceeded",
    }:
        raise McodeTraceFormatError("invalid exec.completed result status")
    duration = result.get("durationMs")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration < 0
    ):
        raise McodeTraceFormatError("invalid exec.completed result durationMs")
    if result.get("usageSource") not in {
        None,
        "completed_responses",
        "analytics_fallback",
        "unavailable",
    }:
        raise McodeTraceFormatError("invalid exec.completed result usageSource")
    if not isinstance(result.get("usageIncomplete", False), bool):
        raise McodeTraceFormatError("invalid exec.completed result usageIncomplete")
    usage = result.get("usage")
    if usage is not None:
        if not isinstance(usage, dict):
            raise McodeTraceFormatError("exec.completed usage must be an object")
        for field, value in usage.items():
            if field.endswith("Tokens"):
                _nonnegative_int(value, field=field)


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


def _message(role: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "message", "message": {"role": role, "content": blocks}}


def _tool_status(tool_call: dict[str, Any]) -> str:
    status = str(tool_call.get("status") or "").strip().lower()
    if tool_call.get("error") is not None or status in {"3", "error", "failed", "failure"}:
        return "error"
    if status in {"2", "completed", "succeeded", "success", "ok"}:
        return "completed"
    return "pending"


def _convert_completed_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    item_type = item.get("type")
    if item_type == "reasoning":
        content = item.get("content")
        return [] if not isinstance(content, str) else [_message("assistant", [{"type": "reasoning", "text": content}])]
    if item_type == "agent_message":
        content = item.get("content")
        return [] if not isinstance(content, str) else [_message("assistant", [{"type": "text", "text": content}])]
    if item_type != "tool_call":
        raise McodeTraceFormatError(f"unsupported completed item type {item_type!r}")
    tool_call = item.get("toolCall")
    if not isinstance(tool_call, dict):
        raise McodeTraceFormatError("completed tool_call item is missing toolCall")
    call_id = str(tool_call.get("id") or item.get("id") or "")
    tool_name = str(tool_call.get("name") or "")
    if not call_id or not tool_name:
        raise McodeTraceFormatError("completed tool_call is missing id or name")
    status = _tool_status(tool_call)
    tool_use = _message(
        "assistant",
        [
            {
                "type": "tool_use",
                "id": call_id,
                "name": tool_name,
                "input": _tool_input(tool_call.get("input", {})),
            }
        ],
    )
    result_value = (
        tool_call.get("error") if tool_call.get("error") is not None else tool_call.get("output")
    )
    tool_result = _message(
        "user",
        [
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": _serialize(result_value),
                "status": status,
            }
        ],
    )
    return [tool_use, tool_result]


def _usage_from_result(result: dict[str, Any] | None) -> dict[str, Any]:
    usage = _empty_usage()
    if not isinstance(result, dict) or not isinstance(result.get("usage"), dict):
        if isinstance(result, dict):
            usage["usage_source"] = str(result.get("usageSource") or "unavailable")
            usage["usage_complete"] = result.get("usageIncomplete") is False
        return usage
    raw = result["usage"]
    for source, destination, _ in _USAGE_FIELDS:
        usage[destination] = _nonnegative_int(raw.get(source), field=source)
    native_total = raw.get("totalTokens")
    if native_total is not None:
        usage["provider_total_tokens"] = _nonnegative_int(
            native_total, field="totalTokens"
        )
    # WildClawBench totals every disjoint billing bucket. MiniMax Code's native
    # total is input + output only, while cache buckets are reported separately.
    usage["total_tokens"] = sum(
        usage[field]
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        )
    )
    usage["request_count"] = 1
    usage["request_count_source"] = "minimum_one_from_exec_aggregate"
    # Some mcode releases emit the aggregate usage while omitting the optional
    # usageSource/usageIncomplete metadata. Presence of the authoritative
    # terminal usage object is still a complete aggregate observation; only an
    # explicit usageIncomplete=true makes it incomplete.
    usage["usage_source"] = str(result.get("usageSource") or "exec_result")
    usage["usage_complete"] = result.get("usageIncomplete") is not True
    usage.update(
        {
            "cost_status": "unavailable",
            "cost_source": "none",
            "cost_scope": "model_tokens_only",
            "cost_reason": (
                "MiniMax Code stream-json exposes aggregate token usage but not provider cost; "
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
    events = _read_trace(trace_path, allow_incomplete=allow_incomplete)
    messages: list[dict[str, Any]] = []
    if prompt:
        messages.append(_message("user", [{"type": "text", "text": prompt}]))
    terminal_result: dict[str, Any] | None = None
    completed_items = 0
    for event in events:
        if event["type"] == "item.completed":
            completed_items += 1
            messages.extend(_convert_completed_item(event["item"]))
        elif event["type"] == "exec.completed":
            terminal_result = event["result"]
    usage = _usage_from_result(terminal_result)
    if usage["request_count"]:
        assistant_entries = [
            entry for entry in messages if entry["message"].get("role") == "assistant"
        ]
        if not assistant_entries:
            assistant_entries = [_message("assistant", [])]
            messages.extend(assistant_entries)
        assistant_entries[-1]["message"]["usage"] = _openclaw_usage(usage)
    first = events[0]
    source = {
        "trace": trace_path.name,
        "schema_version": first["schemaVersion"],
        "run_id": first["runId"],
        "session_id": first["sessionId"],
        "turn_id": first["turnId"],
        "event_count": len(events),
        "completed_item_count": completed_items,
        "terminal_complete": terminal_result is not None,
    }
    return ConversionResult(messages, usage, source, terminal_result)


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
        "source_format": "minimax-code-exec-stream-json-v1",
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
