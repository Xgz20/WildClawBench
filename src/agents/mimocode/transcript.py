from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MiMoCodeTraceFormatError(ValueError):
    """Raised when a MiMoCode JSON event trace cannot be converted safely."""


@dataclass(frozen=True)
class ConversionResult:
    messages: list[dict[str, Any]]
    usage: dict[str, Any]
    source: dict[str, Any]
    terminal_result: dict[str, Any] | None


_EVENT_TYPES = frozenset(
    {"text", "reasoning", "tool_use", "step_start", "step_finish", "error"}
)


def _empty_usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "provider_total_tokens": None,
        "cost_usd": 0.0,
        "request_count": 0,
        "cost_status": "unavailable",
        "cost_source": "none",
        "cost_scope": "model_tokens_only",
        "cost_reason": (
            "MiMoCode JSON events expose token usage but not provider cost; "
            "calculate cost from the model pricing registry when generating the report"
        ),
        "usage_source": "unavailable",
        "usage_scope": "main_session_completed_steps",
        "usage_complete": False,
        "request_count_source": "unavailable",
    }


def _integer(value: Any, field: str) -> int:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MiMoCodeTraceFormatError(f"{field} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MiMoCodeTraceFormatError(
            f"{field} must be a non-negative integer"
        ) from exc
    if parsed < 0 or isinstance(value, float) and not value.is_integer():
        raise MiMoCodeTraceFormatError(f"{field} must be a non-negative integer")
    return parsed


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
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"_raw": value}
        return decoded if isinstance(decoded, dict) else {"_value": decoded}
    return {"_value": value}


def _message(role: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "message", "message": {"role": role, "content": blocks}}


def _read_trace(path: Path, *, allow_incomplete: bool) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MiMoCodeTraceFormatError(
            f"cannot read MiMoCode trace {path}: {exc}"
        ) from exc
    events: list[dict[str, Any]] = []
    session_id: str | None = None
    parts: dict[str, dict[str, Any]] = {}
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            # timeout can interrupt a stdout write; only tolerate the last row.
            if allow_incomplete and line_number == len(lines):
                break
            raise MiMoCodeTraceFormatError(
                f"invalid JSON in {path} line {line_number}"
            ) from exc
        if not isinstance(event, dict):
            raise MiMoCodeTraceFormatError(
                f"trace row in {path} line {line_number} is not an object"
            )
        event_type = str(event.get("type") or "")
        if event_type not in _EVENT_TYPES:
            raise MiMoCodeTraceFormatError(
                f"unsupported event type {event_type!r} in {path} line {line_number}"
            )
        identity = event.get("sessionID")
        if not isinstance(identity, str) or not identity:
            raise MiMoCodeTraceFormatError(
                f"sessionID missing in {path} line {line_number}"
            )
        if session_id is not None and identity != session_id:
            raise MiMoCodeTraceFormatError("MiMoCode stream sessionID changed")
        session_id = identity
        if event_type != "error":
            part = event.get("part")
            if not isinstance(part, dict) or not part.get("id"):
                raise MiMoCodeTraceFormatError(
                    f"part id missing in {path} line {line_number}"
                )
            if part.get("sessionID", session_id) != session_id:
                raise MiMoCodeTraceFormatError("MiMoCode part sessionID changed")
            part_id = part["id"]
            if part_id in parts:
                if parts[part_id] != part:
                    raise MiMoCodeTraceFormatError(f"completed part changed: {part_id}")
                continue
            parts[part_id] = part
        events.append(event)
    if not events:
        raise MiMoCodeTraceFormatError(f"MiMoCode trace is empty: {path}")
    return events


def execution_outcome(
    events: list[dict[str, Any]], exit_code: int | None
) -> dict[str, Any]:
    """CLI has no native terminal event; distinguish process exit from model stop."""
    errors = [event.get("error") for event in events if event.get("type") == "error"]
    finishes = [
        event["part"].get("reason")
        for event in events
        if event.get("type") == "step_finish"
    ]
    reason = finishes[-1] if finishes else None
    status = "incomplete"
    if exit_code == 124:
        status = "timeout"
    elif exit_code is not None:
        status = (
            "succeeded"
            if exit_code == 0 and reason == "stop" and not errors
            else "failed"
        )
    return {
        "source": "runner_exit_and_native_step_finish",
        "status": status,
        "exit_code": exit_code,
        "finish_reason": reason,
        "errors": errors,
    }


def _part(event: dict[str, Any]) -> dict[str, Any]:
    part = event.get("part")
    return part if isinstance(part, dict) else event


def _usage_from_events(
    events: list[dict[str, Any]], terminal: dict[str, Any] | None
) -> dict[str, Any]:
    usage = _empty_usage()
    steps = 0
    complete_tokens = True
    totals: list[int] = []
    for event in events:
        if event.get("type") != "step_finish":
            continue
        tokens = _part(event).get("tokens")
        if not isinstance(tokens, dict):
            complete_tokens = False
            continue
        steps += 1
        complete_tokens &= all(
            tokens.get(key) is not None for key in ("input", "output")
        )
        usage["input_tokens"] += _integer(tokens.get("input", 0), "input")
        reasoning = _integer(tokens.get("reasoning", 0), "reasoning")
        # MiMoCode Session.getUsage subtracts reasoning from its native output.
        # WCB output includes reasoning, with reasoning_tokens as a subset.
        usage["output_tokens"] += (
            _integer(tokens.get("output", 0), "output") + reasoning
        )
        usage["reasoning_tokens"] += reasoning
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        usage["cache_read_tokens"] += _integer(cache.get("read", 0), "cache.read")
        usage["cache_write_tokens"] += _integer(cache.get("write", 0), "cache.write")
        if tokens.get("total") is not None:
            totals.append(_integer(tokens["total"], "total"))
    usage["request_count"] = steps
    usage["request_count_source"] = "mimocode_step_finish"
    usage["total_tokens"] = sum(
        usage[key]
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        )
    )
    usage["provider_total_tokens"] = (
        sum(totals) if steps and len(totals) == steps else None
    )
    usage["usage_source"] = "mimocode_step_finish"
    starts = sum(event.get("type") == "step_start" for event in events)
    usage["usage_complete"] = (
        terminal is not None and steps > 0 and complete_tokens and starts == steps
    )
    if terminal is not None and terminal.get("status") != "succeeded":
        usage["usage_complete"] = False
    return usage


def _database_usage(
    path: Path, session_id: str, terminal: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Count persisted model steps once across the run's session tree.

    Message tokens duplicate step-finish tokens and must not be summed again.
    Other root sessions are not assumed to belong to this run.
    """
    try:
        with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise MiMoCodeTraceFormatError(
                    "MiMoCode database integrity check failed"
                )
            sessions = dict(db.execute("SELECT id,parent_id FROM session"))
            if session_id not in sessions:
                raise MiMoCodeTraceFormatError(
                    "trace sessionID is absent from native database"
                )
            selected = {session_id}
            while True:
                children = {
                    sid for sid, parent in sessions.items() if parent in selected
                }
                if children <= selected:
                    break
                selected |= children
            rows = db.execute(
                "SELECT id,session_id,data FROM part ORDER BY time_created,id"
            ).fetchall()
    except sqlite3.Error as exc:
        raise MiMoCodeTraceFormatError(f"invalid MiMoCode database: {exc}") from exc
    events = []
    last_reason = {}
    pending_tools = 0
    for part_id, sid, raw in rows:
        if sid not in selected:
            continue
        part = json.loads(raw)
        kind = part.get("type")
        if kind == "tool" and part.get("state", {}).get("status") in {
            "pending",
            "running",
        }:
            pending_tools += 1
        if kind not in {"step-start", "step-finish"}:
            continue
        events.append(
            {
                "type": kind.replace("-", "_"),
                "sessionID": sid,
                "part": {**part, "id": part_id},
            }
        )
        if kind == "step-finish":
            last_reason[sid] = part.get("reason")
    usage = _usage_from_events(events, terminal)
    usage["usage_source"] = "mimocode_sqlite_step_finish"
    usage["request_count_source"] = "mimocode_sqlite_step_finish"
    usage["usage_scope"] = "session_tree_completed_steps"
    usage["usage_complete"] &= not pending_tools and all(
        reason == "stop" for reason in last_reason.values()
    )
    usage["session_count"] = len(selected)
    usage["usage_limitations"] = (
        "Persisted completed steps only; unpersisted attempts and out-of-tree auxiliary requests are not observable."
    )
    return usage, {
        "file": path.name,
        "integrity": "ok",
        "session_count": len(selected),
        "other_root_session_count": len(sessions) - len(selected),
        "pending_tool_count": pending_tools,
    }


def convert_trace(
    trace_path: Path,
    *,
    prompt: str = "",
    allow_incomplete: bool = False,
    exit_code: int | None = None,
    database_path: Path | None = None,
) -> ConversionResult:
    events = _read_trace(Path(trace_path), allow_incomplete=allow_incomplete)
    terminal = execution_outcome(events, exit_code)
    if not allow_incomplete and terminal["status"] != "succeeded":
        raise MiMoCodeTraceFormatError(
            f"MiMoCode did not complete successfully: {terminal}"
        )
    messages: list[dict[str, Any]] = []
    if prompt:
        messages.append(_message("user", [{"type": "text", "text": prompt}]))
    seen_tools: set[str] = set()
    for event in events:
        event_type = event.get("type")
        if event_type == "text":
            text = _part(event).get("text")
            if isinstance(text, str) and text:
                messages.append(_message("assistant", [{"type": "text", "text": text}]))
        elif event_type == "reasoning":
            text = _part(event).get("text")
            if isinstance(text, str) and text:
                messages.append(
                    _message("assistant", [{"type": "reasoning", "text": text}])
                )
        elif event_type == "tool_use":
            part = _part(event)
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            call_id = str(
                part.get("callID") or part.get("id") or state.get("callID") or ""
            )
            name = str(part.get("tool") or part.get("name") or "")
            if not call_id or not name:
                raise MiMoCodeTraceFormatError("tool_use missing callID/name")
            if call_id in seen_tools:
                continue
            seen_tools.add(call_id)
            input_value = state.get("input", part.get("input", {}))
            messages.append(
                _message(
                    "assistant",
                    [
                        {
                            "type": "tool_use",
                            "id": call_id,
                            "name": name,
                            "input": _tool_input(input_value),
                        }
                    ],
                )
            )
            result = state.get(
                "output", state.get("error", part.get("output", part.get("error")))
            )
            native_status = state.get("status")
            if native_status not in {"completed", "error"}:
                raise MiMoCodeTraceFormatError(
                    f"unsupported tool terminal status: {native_status}"
                )
            status = "error" if native_status == "error" else "completed"
            metadata = state.get("metadata") or {}
            if (
                isinstance(metadata, dict)
                and isinstance(metadata.get("exit"), int)
                and metadata["exit"] != 0
            ):
                status = "error"
            messages.append(
                _message(
                    "user",
                    [
                        {
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": _serialize(result),
                            "status": status,
                        }
                    ],
                )
            )
        elif event_type == "error":
            error = event.get("error") or event.get("message")
            if error:
                messages.append(
                    _message("assistant", [{"type": "text", "text": _serialize(error)}])
                )
    usage = _usage_from_events(events, terminal)
    native_database = None
    if database_path is not None:
        usage, native_database = _database_usage(
            Path(database_path), str(events[0]["sessionID"]), terminal
        )
    if usage["request_count"]:
        assistants = [
            entry
            for entry in messages
            if entry.get("message", {}).get("role") == "assistant"
        ]
        if not assistants:
            assistants = [_message("assistant", [])]
            messages.extend(assistants)
        assistants[-1]["message"]["usage"] = {
            "input": usage["input_tokens"],
            "output": usage["output_tokens"],
            "cacheRead": usage["cache_read_tokens"],
            "cacheWrite": usage["cache_write_tokens"],
            "totalTokens": usage["total_tokens"],
            "cost": {"total": 0.0},
        }
    source = {
        "trace": Path(trace_path).name,
        "source_format": "mimocode-run-json-v1",
        "event_count": len(events),
        "tool_use_count": len(seen_tools),
        "terminal_complete": terminal["status"] == "succeeded",
        "trace_scope": "main_session_cli_events; all session data retained separately in mimocode.db",
        "native_database": native_database,
        "session_id": str(
            next(
                (event.get("sessionID") for event in events if event.get("sessionID")),
                "",
            )
        ),
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
    exit_code: int | None = None,
    database_path: Path | None = None,
) -> ConversionResult:
    result = convert_trace(
        trace_path,
        prompt=prompt,
        allow_incomplete=allow_incomplete,
        exit_code=exit_code,
        database_path=database_path,
    )
    output_dir = Path(output_dir)
    _atomic_write(
        output_dir / "chat.jsonl",
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in result.messages
        ),
    )
    _atomic_write(
        output_dir / "usage.json",
        json.dumps(result.usage, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write(
        output_dir / "conversion_manifest.json",
        json.dumps(
            {
                "format": "wildclawbench-openclaw-transcript-v1",
                "source_format": "mimocode-run-json-v1",
                "source": result.source,
                "message_count": len(result.messages),
                "usage": result.usage,
                "terminal_result": result.terminal_result,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return result
