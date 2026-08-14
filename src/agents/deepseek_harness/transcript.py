from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class DshSessionFormatError(ValueError):
    """Raised when a DSH session artifact cannot be converted safely."""


@dataclass(frozen=True)
class ConversionResult:
    """Converted transcript plus source metadata and aggregate usage."""

    messages: list[dict[str, Any]]
    usage: dict[str, int | float]
    sessions: list[dict[str, Any]]


_USAGE_FIELDS = (
    ("inputTokens", "input_tokens", "input"),
    ("outputTokens", "output_tokens", "output"),
    ("cacheReadTokens", "cache_read_tokens", "cacheRead"),
    ("cacheWriteTokens", "cache_write_tokens", "cacheWrite"),
)


def _empty_usage() -> dict[str, int | float]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "request_count": 0,
    }


def _as_nonnegative_int(value: Any, *, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise DshSessionFormatError(f"usage field {field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise DshSessionFormatError(f"usage field {field} must be an integer") from exc
    if number < 0 or (isinstance(value, float) and not value.is_integer()):
        raise DshSessionFormatError(f"usage field {field} must be a non-negative integer")
    return number


def _parse_json_argument(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def _tool_input(raw: Any) -> Any:
    parsed = _parse_json_argument(raw)
    if isinstance(parsed, dict):
        return parsed
    return {"_value": parsed}


def _content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if not isinstance(content, list):
        return []

    blocks: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            blocks.append({"type": "text", "text": json.dumps(block, ensure_ascii=False)})
            continue
        block_type = block.get("type")
        if block_type in {"text", "reasoning"}:
            normalized = {"type": block_type, "text": str(block.get("text", ""))}
            blocks.append(normalized)
        elif block_type in {"tool-call", "toolCall", "tool_use"}:
            blocks.append(
                {
                    "type": "tool_use",
                    "id": str(block.get("id") or block.get("callId") or ""),
                    "name": str(block.get("name") or block.get("tool_name") or ""),
                    "input": _tool_input(
                        block.get("arguments", block.get("input", block.get("args", {})))
                    ),
                }
            )
        elif block_type == "tool-result":
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": str(block.get("toolCallId") or block.get("tool_use_id") or ""),
                    "content": _result_content(block.get("content", "")),
                    "status": "error" if block.get("isError") is True else "completed",
                }
            )
        else:
            blocks.append(dict(block))
    return blocks


def _result_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _message_entry(role: str, content: Any) -> dict[str, Any]:
    return {"type": "message", "message": {"role": role, "content": _content_blocks(content)}}


def _assistant_entry(message: dict[str, Any], usage: dict[str, Any] | None) -> dict[str, Any]:
    entry = _message_entry("assistant", message.get("content", []))
    if usage is not None:
        openclaw_usage = {
            "input": _as_nonnegative_int(usage.get("inputTokens"), field="inputTokens"),
            "output": _as_nonnegative_int(usage.get("outputTokens"), field="outputTokens"),
            "cacheRead": _as_nonnegative_int(usage.get("cacheReadTokens"), field="cacheReadTokens"),
            "cacheWrite": _as_nonnegative_int(usage.get("cacheWriteTokens"), field="cacheWriteTokens"),
        }
        openclaw_usage["totalTokens"] = sum(openclaw_usage.values())
        openclaw_usage["cost"] = {"total": 0.0}
        entry["message"]["usage"] = openclaw_usage
    return entry


def _assistant_tool_ids(entry: dict[str, Any]) -> set[str]:
    return {
        str(block.get("id"))
        for block in entry["message"].get("content", [])
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id")
    }


def _tool_result_entry(data: dict[str, Any]) -> dict[str, Any]:
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    source = message.get("source") if isinstance(message.get("source"), dict) else {}
    raw_blocks = message.get("content")
    blocks = raw_blocks if isinstance(raw_blocks, list) else []
    source_call_id = str(source.get("callId") or data.get("callId") or "")
    found: dict[str, Any] | None = None
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool-result":
            found = block
            break
    found = found or {}
    call_id = str(found.get("toolCallId") or found.get("tool_use_id") or source_call_id)
    raw_content = found.get("content", "")
    is_error = (
        data.get("error") is not None
        or message.get("isError") is True
        or found.get("isError") is True
    )
    tool_result = {
        "type": "tool_result",
        "tool_use_id": call_id,
        "content": _result_content(raw_content),
        "status": "error" if is_error else "completed",
    }
    return {"type": "message", "message": {"role": "user", "content": [tool_result]}}


def _iter_session_files(session_root: Path) -> list[Path]:
    if not session_root.exists():
        raise DshSessionFormatError(f"session root does not exist: {session_root}")
    if session_root.is_file():
        if session_root.name.endswith((".jsonl.zst", ".jsonl.gz")):
            raise DshSessionFormatError(
                f"compressed session artifact is unsupported: {session_root}"
            )
        candidates = [session_root]
    else:
        compressed = sorted(
            path
            for path in session_root.rglob("session.jsonl.*")
            if path.is_file() and path.suffix in {".zst", ".gz"}
        )
        if compressed:
            raise DshSessionFormatError(f"compressed session artifact is unsupported: {compressed[0]}")
        candidates = sorted(
            path for path in session_root.rglob("session.jsonl") if path.is_file()
        )
    if not candidates:
        raise DshSessionFormatError(f"no session.jsonl found below {session_root}")
    return sorted(candidates, key=lambda path: (len(path.relative_to(session_root).parts), str(path)))


def _read_session(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DshSessionFormatError(f"cannot read session {path}: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DshSessionFormatError(f"invalid JSON in {path} line {line_number}") from exc
        if not isinstance(value, dict):
            raise DshSessionFormatError(f"session row in {path} line {line_number} is not an object")
        rows.append(value)

    if not rows or rows[0].get("type") != "session":
        raise DshSessionFormatError(f"session header missing in {path}")
    header = rows[0]
    if not isinstance(header.get("version"), int) or isinstance(header.get("version"), bool):
        raise DshSessionFormatError(f"invalid session header version in {path}")
    if not isinstance(header.get("id"), str) or not header["id"]:
        raise DshSessionFormatError(f"invalid session header id in {path}")
    created_at = header.get("createdAt")
    if (
        not isinstance(created_at, int)
        or isinstance(created_at, bool)
        or created_at < 0
    ):
        raise DshSessionFormatError(f"invalid session header createdAt in {path}")
    return header, rows[1:]


def _convert_events(events: Iterable[dict[str, Any]], usage: dict[str, int | float]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen_tool_ids: set[str] = set()
    for event in events:
        event_type = event.get("type")
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if event_type == "user/message":
            message = data.get("message") if isinstance(data.get("message"), dict) else data
            output.append(_message_entry("user", message.get("content", [])))
        elif event_type == "assistant/message":
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            row = _assistant_entry(message, data.get("usage") if isinstance(data.get("usage"), dict) else None)
            seen_tool_ids.update(_assistant_tool_ids(row))
            if isinstance(data.get("usage"), dict):
                for dsh_name, aggregate_name, _ in _USAGE_FIELDS:
                    value = _as_nonnegative_int(data["usage"].get(dsh_name), field=dsh_name)
                    usage[aggregate_name] = int(usage[aggregate_name]) + value
                usage["request_count"] = int(usage["request_count"]) + 1
            output.append(row)
        elif event_type == "tool/call":
            call_id = str(data.get("callId") or "")
            if call_id and call_id in seen_tool_ids:
                continue
            # A standalone tool/call is a log-only fallback, not another model
            # request. Keep it visible for tool pairing without inflating the
            # existing WCB assistant-message request counter.
            row = {
                "type": "message",
                "message": {
                    "role": "tool",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": call_id,
                            "name": str(data.get("name") or ""),
                            "input": _tool_input(data.get("arguments", {})),
                        }
                    ],
                },
            }
            seen_tool_ids.add(call_id)
            output.append(row)
        elif event_type == "tool/result":
            output.append(_tool_result_entry(data))
    return output


def convert_sessions(session_root: Path) -> ConversionResult:
    session_root = Path(session_root)
    aggregate = _empty_usage()
    messages: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    for path in _iter_session_files(session_root):
        header, events = _read_session(path)
        metadata = dict(header)
        metadata["path"] = str(path.relative_to(session_root)) if session_root.is_dir() else path.name
        sessions.append(metadata)
        messages.extend(_convert_events(events, aggregate))
    aggregate["total_tokens"] = sum(
        int(aggregate[field])
        for field in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    )
    return ConversionResult(messages=messages, usage=aggregate, sessions=sessions)


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


def write_conversion(session_root: Path, output_dir: Path) -> ConversionResult:
    result = convert_sessions(session_root)
    output_dir = Path(output_dir)
    chat = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in result.messages)
    _atomic_write(output_dir / "chat.jsonl", chat)
    _atomic_write(
        output_dir / "usage.json",
        json.dumps(result.usage, ensure_ascii=False, indent=2) + "\n",
    )
    manifest = {
        "format": "wildclawbench-openclaw-transcript-v1",
        "source_sessions": result.sessions,
        "message_count": len(result.messages),
        "usage": result.usage,
    }
    _atomic_write(
        output_dir / "conversion_manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return result
