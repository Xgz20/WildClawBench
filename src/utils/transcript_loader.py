from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

OPENCLAW_FALLBACK_PATH = "/root/.openclaw/agents/main/sessions/chat.jsonl"
JUDGE_EVIDENCE_FORMAT = "wildclaw_judge_evidence_v1"
GRADING_TRANSCRIPT_POLICY_VERSION = "grading_transcript_v2_inline_think_filtered"
COMPACT_EVENT_STRING_CHARS = 1200
_INLINE_THINK_OPEN_RE = re.compile(r"<\s*think\s*>", flags=re.I)
_INLINE_THINK_CLOSE_RE = re.compile(r"<\s*/\s*think\s*>", flags=re.I)
_VISIBLE_TEXT_BLOCK_TYPES = {"text", "output_text", "message", "assistant_text"}


def _safe_json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _transcript_rows(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("transcript", "messages", "chat"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return [value]


def parse_transcript_text(raw: str) -> list[Any]:
    """解析 JSON 数组、标准 JSONL 或连续的跨行 JSON 对象。"""
    parsed = _safe_json_loads(raw)
    if parsed is not None:
        return _transcript_rows(parsed)

    rows: list[Any] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(raw):
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index >= len(raw):
            break
        try:
            value, end = decoder.raw_decode(raw, index)
        except json.JSONDecodeError:
            next_line = raw.find("\n", index)
            if next_line < 0:
                break
            index = next_line + 1
            continue
        rows.extend(_transcript_rows(value))
        index = end
    return rows


def _read_transcript_file(path: Path) -> list[Any]:
    if not path.exists():
        return []

    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    return parse_transcript_text(raw)


def _unquoted_tag_matches(pattern: re.Pattern[str], text: str) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for match in pattern.finditer(text):
        before = text[match.start() - 1] if match.start() > 0 else ""
        after = text[match.end()] if match.end() < len(text) else ""
        if before == "`" or after == "`":
            continue
        matches.append(match)
    return matches


def _strip_inline_thinking(text: str) -> str:
    """Remove leaked provider reasoning while preserving the visible final answer."""
    closing_tags = _unquoted_tag_matches(_INLINE_THINK_CLOSE_RE, text)
    if closing_tags:
        return text[closing_tags[-1].end() :].lstrip()

    opening_tags = _unquoted_tag_matches(_INLINE_THINK_OPEN_RE, text)
    if opening_tags:
        return text[: opening_tags[0].start()].rstrip()
    return text


def _sanitize_assistant_content(content: Any) -> Any:
    if isinstance(content, str):
        return _strip_inline_thinking(content)
    if not isinstance(content, list):
        return content

    for index, block in enumerate(content):
        if isinstance(block, str):
            content[index] = _strip_inline_thinking(block)
            continue
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").lower()
        if block_type not in _VISIBLE_TEXT_BLOCK_TYPES:
            continue
        for key in ("text", "content"):
            value = block.get(key)
            if isinstance(value, str):
                block[key] = _strip_inline_thinking(value)
            elif isinstance(value, dict) and isinstance(value.get("value"), str):
                value["value"] = _strip_inline_thinking(value["value"])
    return content


def _sanitize_transcript_for_grading(transcript: list[Any]) -> list[Any]:
    def sanitize_mapping(candidate: dict[str, Any]) -> None:
        if str(candidate.get("role") or "").strip().lower() == "assistant":
            if "content" in candidate:
                candidate["content"] = _sanitize_assistant_content(
                    candidate.get("content")
                )
            if isinstance(candidate.get("text"), str):
                candidate["text"] = _strip_inline_thinking(candidate["text"])
        for key in ("message", "payload"):
            nested = candidate.get(key)
            if isinstance(nested, dict):
                sanitize_mapping(nested)

    for event in transcript:
        if isinstance(event, dict):
            sanitize_mapping(event)
    return transcript


def load_transcript(path_str: str = "") -> list[Any]:
    candidates: list[str] = []
    if path_str:
        candidates.append(path_str)
    candidates.append(OPENCLAW_FALLBACK_PATH)

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        loaded = _read_transcript_file(Path(candidate))
        if loaded:
            return _sanitize_transcript_for_grading(loaded)
    return []


def _event_role(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    candidates = [event]
    for key in ("message", "payload"):
        nested = event.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        role = str(candidate.get("role") or "").strip().lower()
        if role:
            return role
    return ""


def _event_has_visible_text(event: Any) -> bool:
    if not isinstance(event, dict):
        return False
    candidates = [event]
    for key in ("message", "payload"):
        nested = event.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        content = candidate.get("content")
        if isinstance(content, str) and content.strip():
            return True
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, str) and block.strip():
                return True
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").lower()
            text = block.get("text") or block.get("content")
            if block_type in {"text", "output_text", "input_text"} and str(text or "").strip():
                return True
    return False


def _first_role_index(transcript: list[Any], role: str) -> int | None:
    for index, event in enumerate(transcript):
        if _event_role(event) == role:
            return index
    return None


def _final_assistant_index(transcript: list[Any]) -> int | None:
    final_assistant: int | None = None
    final_visible_assistant: int | None = None
    for index, event in enumerate(transcript):
        if _event_role(event) != "assistant":
            continue
        final_assistant = index
        if _event_has_visible_text(event):
            final_visible_assistant = index
    return (
        final_visible_assistant
        if final_visible_assistant is not None
        else final_assistant
    )


def _head_tail(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    marker = f"\n...[{len(value) - max_chars} chars omitted]...\n"
    if max_chars <= len(marker) + 2:
        return value[:max_chars]
    remaining = max_chars - len(marker)
    head_chars = remaining // 2
    tail_chars = remaining - head_chars
    return value[:head_chars] + marker + value[-tail_chars:]


def _compact_value(value: Any, string_limit: int) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _compact_value(item, string_limit)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_compact_value(item, string_limit) for item in value]
    if isinstance(value, str):
        return _head_tail(value, string_limit)
    return value


def _index_ranges(indices: list[int]) -> list[str]:
    if not indices:
        return []
    ranges: list[str] = []
    start = previous = indices[0]
    for index in indices[1:]:
        if index == previous + 1:
            previous = index
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = index
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ranges


def _event_outline(index: int, event: Any) -> dict[str, Any]:
    outline: dict[str, Any] = {"event_index": index}
    role = _event_role(event)
    if role:
        outline["role"] = role
    if not isinstance(event, dict):
        outline["value_type"] = type(event).__name__
        return outline

    candidates = [event]
    for key in ("message", "payload"):
        nested = event.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    event_types: list[str] = []
    statuses: list[str] = []
    tools: list[dict[str, str]] = []
    for candidate in candidates:
        event_type = str(candidate.get("type") or "").strip()
        if event_type and event_type not in event_types:
            event_types.append(event_type)
        status = str(candidate.get("status") or "").strip()
        if status and status not in statuses:
            statuses.append(status)
        content = candidate.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip()
            if block_type not in {"tool_use", "toolCall", "tool_call", "tool_result"}:
                continue
            tool = {"type": block_type}
            for source_key, target_key in (
                ("name", "name"),
                ("tool_name", "name"),
                ("toolName", "name"),
                ("id", "id"),
                ("tool_use_id", "tool_use_id"),
                ("status", "status"),
            ):
                value = str(block.get(source_key) or "").strip()
                if value and target_key not in tool:
                    tool[target_key] = value
            tools.append(tool)
    if event_types:
        outline["types"] = event_types
    if statuses:
        outline["statuses"] = statuses
    if tools:
        outline["tools"] = tools
    return outline


def _render_compacted_evidence(
    transcript: list[Any],
    selected: dict[int, Any],
) -> str:
    included_indices = set(selected)
    omitted_indices = [
        index for index in range(len(transcript))
        if index not in included_indices
    ]
    payload = {
        "format": JUDGE_EVIDENCE_FORMAT,
        "omitted_event_ranges": _index_ranges(omitted_indices),
        "omitted_event_outlines": [
            _event_outline(index, transcript[index])
            for index in omitted_indices
        ],
        "events": [
            {"event_index": index, "event": selected[index]}
            for index in sorted(selected)
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def build_judge_evidence(
    transcript: list[Any],
    *,
    max_chars: int,
) -> dict[str, Any]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")

    full_text = json.dumps(transcript, ensure_ascii=False)
    first_user_index = _first_role_index(transcript, "user")
    final_assistant_index = _final_assistant_index(transcript)
    if len(full_text) <= max_chars:
        return {
            "text": full_text,
            "metadata": {
                "policy": "complete",
                "max_chars": max_chars,
                "original_chars": len(full_text),
                "included_chars": len(full_text),
                "original_event_count": len(transcript),
                "included_event_count": len(transcript),
                "omitted_event_count": 0,
                "omitted_event_ranges": [],
                "truncated_event_count": 0,
                "truncated_event_ranges": [],
                "compacted": False,
                "first_user_event_index": first_user_index,
                "final_answer_event_index": final_assistant_index,
                "final_answer_included": final_assistant_index is not None,
                "final_answer_truncated": False,
            },
        }

    mandatory_indices = {
        index for index in (first_user_index, final_assistant_index)
        if index is not None
    }
    if not mandatory_indices and transcript:
        mandatory_indices.add(len(transcript) - 1)

    selected = {index: transcript[index] for index in mandatory_indices}
    evidence_text = _render_compacted_evidence(transcript, selected)
    string_limit = min(
        COMPACT_EVENT_STRING_CHARS,
        max(128, max_chars // max(2, len(mandatory_indices) * 2)),
    )
    while len(evidence_text) > max_chars and string_limit >= 128:
        selected = {
            index: _compact_value(transcript[index], string_limit)
            for index in mandatory_indices
        }
        evidence_text = _render_compacted_evidence(transcript, selected)
        string_limit //= 2

    if len(evidence_text) > max_chars:
        excerpt_limit = max(64, max_chars // max(4, len(mandatory_indices) * 3))
        while True:
            selected = {
                index: {
                    "event_excerpt": _head_tail(
                        json.dumps(transcript[index], ensure_ascii=False),
                        excerpt_limit,
                    )
                }
                for index in mandatory_indices
            }
            evidence_text = _render_compacted_evidence(transcript, selected)
            if len(evidence_text) <= max_chars or excerpt_limit <= 32:
                break
            excerpt_limit //= 2

    candidate_indices = [
        index for index in range(len(transcript) - 1, -1, -1)
        if index not in mandatory_indices
    ]
    for index in candidate_indices:
        trial = {**selected, index: transcript[index]}
        trial_text = _render_compacted_evidence(transcript, trial)
        if len(trial_text) <= max_chars:
            selected = trial
            evidence_text = trial_text
            continue
        candidate = _compact_value(
            transcript[index], COMPACT_EVENT_STRING_CHARS
        )
        trial = {**selected, index: candidate}
        trial_text = _render_compacted_evidence(transcript, trial)
        if len(trial_text) <= max_chars:
            selected = trial
            evidence_text = trial_text

    final_answer_truncated = False
    if final_assistant_index is not None and final_assistant_index in selected:
        final_answer_truncated = (
            json.dumps(selected[final_assistant_index], ensure_ascii=False)
            != json.dumps(transcript[final_assistant_index], ensure_ascii=False)
        )
    omitted_indices = [
        index for index in range(len(transcript))
        if index not in selected
    ]
    truncated_indices = sorted(
        index for index in selected
        if json.dumps(selected[index], ensure_ascii=False)
        != json.dumps(transcript[index], ensure_ascii=False)
    )
    return {
        "text": evidence_text,
        "metadata": {
            "policy": "deterministic_compaction_v1",
            "max_chars": max_chars,
            "original_chars": len(full_text),
            "included_chars": len(evidence_text),
            "original_event_count": len(transcript),
            "included_event_count": len(selected),
            "omitted_event_count": len(omitted_indices),
            "omitted_event_ranges": _index_ranges(omitted_indices),
            "truncated_event_count": len(truncated_indices),
            "truncated_event_ranges": _index_ranges(truncated_indices),
            "compacted": True,
            "first_user_event_index": first_user_index,
            "final_answer_event_index": final_assistant_index,
            "final_answer_included": (
                final_assistant_index is not None
                and final_assistant_index in selected
            ),
            "final_answer_truncated": final_answer_truncated,
        },
    }
