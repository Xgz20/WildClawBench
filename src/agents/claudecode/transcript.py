from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _message(role: str) -> dict[str, Any]:
    return {
        "type": "message",
        "message": {
            "role": role or "assistant",
            "content": [],
        },
    }


def _is_openclaw_message(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and item.get("type") == "message"
        and isinstance(item.get("message"), dict)
    )


def _read_rows(chat_path: Path) -> list[Any]:
    try:
        raw = chat_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    parsed = _safe_json_loads(raw)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]

    rows: list[Any] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parsed_line = _safe_json_loads(line)
        if parsed_line is not None:
            rows.append(parsed_line)
    return rows


def _normalize_role_content_message(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    role = item.get("role")
    if not isinstance(role, str):
        return None

    normalized = _message(role)
    normalized_message = normalized["message"]
    for key in ("id", "model", "stop_reason", "stop_sequence"):
        value = item.get(key)
        if value is not None:
            normalized_message[key] = value
    if isinstance(item.get("usage"), dict):
        normalized_message["usage"] = _to_openclaw_usage(item["usage"])

    content = item.get("content", "")
    blocks = normalized_message["content"]

    if isinstance(content, str):
        if content:
            blocks.append({"type": "text", "text": content})
        return normalized

    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                blocks.append({"type": "text", "text": str(block.get("text", ""))})
                continue
            if block_type in ("tool_use", "toolCall"):
                tool_input = block.get("input", block.get("arguments", {}))
                if isinstance(tool_input, str):
                    parsed = _safe_json_loads(tool_input)
                    if parsed is not None:
                        tool_input = parsed
                tool_use = {
                    "type": "tool_use",
                    "name": str(block.get("name", block.get("tool_name", ""))),
                    "input": tool_input,
                }
                tool_id = block.get("id", block.get("tool_use_id"))
                if tool_id is not None:
                    tool_use["id"] = str(tool_id)
                blocks.append(tool_use)
                continue
            if block_type == "tool_result":
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": str(block.get("tool_use_id", "")),
                    "content": block.get("content", ""),
                }
                if "is_error" in block:
                    tool_result["is_error"] = bool(block.get("is_error"))
                blocks.append(tool_result)
    return normalized


def _normalize_claude_message_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    nested_message = item.get("message")
    if isinstance(nested_message, dict):
        normalized = _normalize_role_content_message(nested_message)
        if normalized is not None:
            wrapper_id = item.get("uuid")
            if wrapper_id is not None and "id" not in normalized["message"]:
                normalized["message"]["id"] = str(wrapper_id)
        return normalized

    if isinstance(item.get("role"), str):
        return _normalize_role_content_message(item)

    wrapper_role = item.get("type")
    if wrapper_role not in {"user", "assistant"}:
        return None
    if not isinstance(nested_message, (str, list)):
        return None
    return _normalize_role_content_message(
        {
            "role": wrapper_role,
            "content": nested_message,
            "id": item.get("uuid"),
        }
    )


def _merge_assistant_message_fragments(
    normalized: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    last_assistant_id: str | None = None
    last_assistant: dict[str, Any] | None = None

    for item in normalized:
        message = item.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            merged.append(item)
            content = message.get("content") if isinstance(message, dict) else None
            is_tool_result_message = (
                message.get("role") == "user"
                and isinstance(content, list)
                and bool(content)
                and all(
                    isinstance(block, dict) and block.get("type") == "tool_result"
                    for block in content
                )
            )
            if is_tool_result_message and last_assistant is not None:
                continue
            last_assistant_id = None
            last_assistant = None
            continue

        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        message_id = message.get("id")
        if message_id is None:
            if blocks:
                merged.append(item)
            last_assistant_id = None
            last_assistant = None
            continue

        key = str(message_id)
        if last_assistant is not None and key == last_assistant_id:
            existing_message = last_assistant["message"]
            existing_message["content"].extend(blocks)
            for metadata_key, value in message.items():
                if metadata_key not in {"role", "content", "id"} and value is not None:
                    existing_message[metadata_key] = value
            continue

        last_assistant_id = None
        last_assistant = None
        if not blocks:
            continue
        merged.append(item)
        last_assistant_id = key
        last_assistant = item

    return merged


def _merge_user_tool_result_fragments(
    normalized: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []

    for item in normalized:
        message = item.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        is_tool_result_message = (
            isinstance(message, dict)
            and message.get("role") == "user"
            and isinstance(content, list)
            and bool(content)
            and all(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in content
            )
        )
        if not is_tool_result_message or not merged:
            merged.append(item)
            continue

        previous_message = merged[-1].get("message")
        previous_content = (
            previous_message.get("content")
            if isinstance(previous_message, dict)
            else None
        )
        previous_is_tool_result_message = (
            isinstance(previous_message, dict)
            and previous_message.get("role") == "user"
            and isinstance(previous_content, list)
            and bool(previous_content)
            and all(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in previous_content
            )
        )
        if previous_is_tool_result_message:
            previous_content.extend(content)
            continue

        merged.append(item)

    return merged


def _merge_message_fragments(
    normalized: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _merge_user_tool_result_fragments(
        _merge_assistant_message_fragments(normalized)
    )


def _last_model_request_context(rows: list[Any]) -> tuple[int, list[dict[str, Any]]] | None:
    last_index = -1
    last_messages: list[Any] | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("event") != "model_request":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            continue
        last_index = index
        last_messages = payload["messages"]

    if last_messages is None:
        return None

    normalized = []
    for item in last_messages:
        message = _normalize_claude_message_item(item)
        if message is not None:
            normalized.append(message)
    return last_index, _merge_message_fragments(normalized)


def _complete_message_from_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None

    candidate: Any = row
    if row.get("event") == "query_yield":
        payload = row.get("payload")
        if not isinstance(payload, dict):
            return None
        candidate = payload.get("message")

    if not isinstance(candidate, dict) or candidate.get("type") == "stream_event":
        return None
    return _normalize_claude_message_item(candidate)


def _message_signature(item: dict[str, Any]) -> str:
    message = item.get("message")
    if not isinstance(message, dict):
        return ""
    return json.dumps(
        {
            "role": message.get("role"),
            "content": message.get("content"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _append_unique_message(
    normalized: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> None:
    candidate_message = candidate.get("message")
    candidate_id = candidate_message.get("id") if isinstance(candidate_message, dict) else None
    candidate_signature = _message_signature(candidate)

    for existing in normalized:
        existing_message = existing.get("message")
        if not isinstance(existing_message, dict):
            continue
        existing_id = existing_message.get("id")
        if candidate_id is not None and existing_id is not None:
            if existing_id == candidate_id:
                return
            continue
        if candidate_signature and _message_signature(existing) == candidate_signature:
            return
    normalized.append(candidate)


def _extract_stream_event(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("event") != "query_yield":
        return None
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return None
    payload_message = payload.get("message")
    if not isinstance(payload_message, dict):
        return None
    if payload_message.get("type") != "stream_event":
        return None
    stream_event = payload_message.get("event")
    if isinstance(stream_event, dict):
        return stream_event
    return None


def _to_openclaw_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "input": int(usage.get("input_tokens", 0) or 0),
        "output": int(usage.get("output_tokens", 0) or 0),
        "cacheRead": int(usage.get("cache_read_input_tokens", 0) or 0),
        "cacheWrite": int(usage.get("cache_creation_input_tokens", 0) or 0),
        "totalTokens": (
            int(usage.get("input_tokens", 0) or 0)
            + int(usage.get("output_tokens", 0) or 0)
            + int(usage.get("cache_read_input_tokens", 0) or 0)
            + int(usage.get("cache_creation_input_tokens", 0) or 0)
        ),
        "cost": {"total": float(usage.get("cost_usd", usage.get("total_cost_usd", 0.0)) or 0.0)},
    }


def _normalize_claude_event_rows(rows: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    current_role: str | None = None
    blocks_by_index: dict[int, dict[str, Any]] = {}
    tool_input_deltas: dict[int, str] = {}
    last_assistant_index: int | None = None

    def flush_current() -> None:
        nonlocal current_role, blocks_by_index, tool_input_deltas, last_assistant_index
        if current_role is None:
            blocks_by_index = {}
            tool_input_deltas = {}
            return

        message = _message(current_role)
        content = message["message"]["content"]
        for index in sorted(blocks_by_index.keys()):
            block = blocks_by_index[index]
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text:
                    content.append({"type": "text", "text": text})
            elif block_type in ("tool_use", "toolCall"):
                tool_use = {
                    "type": "tool_use",
                    "name": str(block.get("name", "")),
                    "input": block.get("input", {}),
                }
                if block.get("id") is not None:
                    tool_use["id"] = str(block["id"])
                content.append(tool_use)
            elif block_type == "tool_result":
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": str(block.get("tool_use_id", "")),
                    "content": block.get("content", ""),
                }
                if "is_error" in block:
                    tool_result["is_error"] = bool(block.get("is_error"))
                content.append(tool_result)

        if content:
            normalized.append(message)
            if current_role == "assistant":
                last_assistant_index = len(normalized) - 1

        current_role = None
        blocks_by_index = {}
        tool_input_deltas = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        if row.get("event") == "query_end":
            payload = row.get("payload")
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("usage"), dict)
                and last_assistant_index is not None
            ):
                normalized[last_assistant_index]["message"]["usage"] = _to_openclaw_usage(payload["usage"])
            continue

        stream_event = _extract_stream_event(row)
        if not isinstance(stream_event, dict):
            continue

        event_type = stream_event.get("type")
        if event_type == "message_start":
            flush_current()
            message_payload = stream_event.get("message")
            if isinstance(message_payload, dict):
                current_role = str(message_payload.get("role", "assistant"))
            else:
                current_role = "assistant"
            continue

        if current_role is None:
            continue

        if event_type == "content_block_start":
            index = int(stream_event.get("index", 0))
            content_block = stream_event.get("content_block")
            if not isinstance(content_block, dict):
                continue
            block_type = content_block.get("type")
            if block_type == "text":
                blocks_by_index[index] = {"type": "text", "text": str(content_block.get("text", ""))}
            elif block_type == "tool_use":
                blocks_by_index[index] = {
                    "type": "tool_use",
                    "id": content_block.get("id"),
                    "name": str(content_block.get("name", "")),
                    "input": content_block.get("input", {}),
                }
                if "input" not in content_block or content_block.get("input") in ({}, None, ""):
                    tool_input_deltas[index] = ""
            elif block_type == "tool_result":
                blocks_by_index[index] = {
                    "type": "tool_result",
                    "tool_use_id": str(content_block.get("tool_use_id", "")),
                    "content": content_block.get("content", ""),
                    "is_error": content_block.get("is_error", False),
                }
            continue

        if event_type == "content_block_delta":
            index = int(stream_event.get("index", 0))
            delta = stream_event.get("delta")
            if not isinstance(delta, dict):
                continue
            delta_type = delta.get("type")
            if delta_type == "text_delta":
                block = blocks_by_index.get(index)
                if not isinstance(block, dict) or block.get("type") != "text":
                    block = {"type": "text", "text": ""}
                    blocks_by_index[index] = block
                block["text"] = str(block.get("text", "")) + str(delta.get("text", ""))
            elif delta_type == "input_json_delta":
                block = blocks_by_index.get(index)
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    block = {"type": "tool_use", "name": "", "input": {}}
                    blocks_by_index[index] = block
                tool_input_deltas[index] = tool_input_deltas.get(index, "") + str(
                    delta.get("partial_json", "")
                )
            continue

        if event_type == "content_block_stop":
            index = int(stream_event.get("index", 0))
            partial = tool_input_deltas.pop(index, "")
            if not partial:
                continue
            parsed = _safe_json_loads(partial)
            if parsed is None:
                parsed = {"raw": partial}
            block = blocks_by_index.get(index)
            if isinstance(block, dict) and block.get("type") == "tool_use":
                block["input"] = parsed
            continue

        if event_type == "message_stop":
            flush_current()

    flush_current()
    return normalized


def convert_claudecode_chat_to_openclaw_jsonl(chat_path: Path, output_path: Path) -> int:
    rows = _read_rows(chat_path)
    if not rows:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        return 0

    openclaw_rows = [row for row in rows if _is_openclaw_message(row)]
    if openclaw_rows:
        normalized = openclaw_rows
    else:
        request_context = _last_model_request_context(rows)
        if request_context is not None:
            request_index, normalized = request_context
            complete_assistants: list[dict[str, Any]] = []
            for row in rows[request_index + 1 :]:
                candidate = _complete_message_from_row(row)
                if (
                    candidate is not None
                    and candidate["message"].get("role") == "assistant"
                ):
                    complete_assistants.append(candidate)

            if complete_assistants:
                for candidate in complete_assistants:
                    _append_unique_message(normalized, candidate)
            else:
                for candidate in _normalize_claude_event_rows(rows[request_index + 1 :]):
                    if candidate["message"].get("role") == "assistant":
                        _append_unique_message(normalized, candidate)
        else:
            normalized = _normalize_claude_event_rows(rows)

        if not normalized:
            role_messages: list[dict[str, Any]] = []
            for row in rows:
                normalized_row = _normalize_claude_message_item(row)
                if normalized_row is not None:
                    role_messages.append(normalized_row)
            normalized = role_messages

    normalized = _merge_message_fragments(normalized)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = ""
    if normalized:
        payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in normalized) + "\n"
    output_path.write_text(payload, encoding="utf-8")
    return len(normalized)
