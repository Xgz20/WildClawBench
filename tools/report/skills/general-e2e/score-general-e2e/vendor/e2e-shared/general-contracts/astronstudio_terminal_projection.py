"""Prove a completed SDK turn while preserving an older running projection.

Only the completed execution driver's exact historical status mismatch is
admitted. Original state bytes, SDK records, transcript, prompt and final are
bound independently; this module never changes state or assigns a score.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

PROFILE = "bound-sdk-completed-turn-projection-status/v1"
STATE_PATH = "bindings/terminal-projection-original-state.json"
PROOF_PATH = "bindings/terminal-projection-proof.json"
SDK_PATH = "raw/astronstudio-rollout.jsonl"


def require(condition, code):
    if not condition:
        raise ValueError("TERMINAL_PROJECTION_" + code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def candidate(state):
    return (state.get("phase") == "COMPLETED"
            and state.get("execution", {}).get("business_status") == "completed"
            and state.get("session", {}).get("native_status") == "running")


def jsonl(data):
    # Unicode separators inside JSON strings are not physical JSONL rows.
    return [(n, json.loads(line), line) for n, line in enumerate(data.split(b"\n"), 1) if line.strip()]


def assistant_text(payload):
    content = payload.get("content")
    require(isinstance(content, list) and content, "ASSISTANT_CONTENT")
    require(all(isinstance(x, dict) and x.get("type") in ("text", "output_text")
                and isinstance(x.get("text"), str) for x in content), "ASSISTANT_CONTENT")
    return "\n".join(x["text"] for x in content)


def derive(state_bytes, index, sdk_bytes, transcript_bytes):
    state = json.loads(state_bytes)
    require(candidate(state), "NOT_HISTORICAL_MISMATCH")
    session = state["session"]
    require(session.get("verified") is True and state.get("prompt", {}).get("send_status") == "sent"
            and state.get("send", {}).get("dispatch_attempt_count") == 1
            and state["execution"].get("error") is None, "STATE_UNVERIFIED")
    history = state.get("history", [])
    terminals = [(n, e) for n, e in enumerate(history) if e.get("event") == "NATIVE_TERMINAL_OBSERVED"]
    finals = [(n, e) for n, e in enumerate(history) if e.get("event") == "TERMINAL_FINAL_RESPONSE_BOUND"]
    require(len(terminals) == len(finals) == 1, "HISTORY_AMBIGUOUS")
    terminal_index, terminal = terminals[0]
    final_index, final = finals[0]
    require(final_index < terminal_index == len(history) - 1
            and terminal.get("phase") == "COMPLETED" and terminal.get("native_status") == "running"
            and terminal.get("turn_state") == "completed"
            and terminal.get("at") == state["execution"].get("finished_at")
            and final.get("source") == "completed-turn.assistant_message_id"
            and isinstance(final.get("message_id"), str) and final["message_id"], "HISTORY_UNBOUND")
    require(index.get("identity") == state.get("identity"), "IDENTITY")
    require(all(index.get("session", {}).get(k) == session.get(k)
                and isinstance(session.get(k), str) and session[k]
                for k in ("thread_id", "turn_id", "session_id", "cwd")), "SESSION")
    require(index.get("canonical_source_policy", {}).get("id") == "bound-native-sdk-canonical/v1"
            and index.get("completeness") == {"status": "complete", "omitted_event_count": 0, "missing": []},
            "CANONICAL_COMPLETE_REQUIRED")
    sdk_refs = [r for r in index.get("raw_trace", []) if r.get("path") == SDK_PATH]
    require(len(sdk_refs) == 1 and sdk_refs[0].get("sha256") == sha(sdk_bytes)
            and sdk_refs[0].get("size") == len(sdk_bytes), "SDK_DIGEST")
    transcript_ref = index.get("transcript", {})
    require(transcript_ref.get("sha256") == sha(transcript_bytes)
            and transcript_ref.get("size") == len(transcript_bytes), "TRANSCRIPT_DIGEST")
    current = None
    meta, starts, contexts, users, completions, assistants = [], [], [], [], [], []
    ended = False
    for n, row, raw in jsonl(sdk_bytes):
        payload = row.get("payload", {})
        kind = row.get("type")
        if ended:
            require(kind == "event_msg" and payload.get("type") == "token_count", "CONTENT_AFTER_TERMINAL")
        if kind == "session_meta":
            meta.append(payload)
        if kind == "event_msg" and payload.get("type") == "task_started":
            require(not ended and payload.get("turn_id") == session["turn_id"], "SDK_OTHER_OR_REOPENED_TURN")
            current = payload.get("turn_id")
            if current == session["turn_id"]:
                starts.append(n)
        if kind == "turn_context":
            require(payload.get("turn_id") == session["turn_id"], "SDK_OTHER_TURN_CONTEXT")
            current = payload.get("turn_id")
            if current == session["turn_id"]:
                require(not ended and payload.get("cwd") == session["cwd"], "CONTEXT")
                contexts.append(n)
        explicit = payload.get("internal_chat_message_metadata_passthrough", {}).get("turn_id")
        if explicit is not None:
            require(explicit == session["turn_id"], "SDK_OTHER_ITEM_TURN")
        if explicit is not None and current is not None:
            require(explicit == current, "ITEM_TURN")
        if (explicit or current) != session["turn_id"]:
            continue
        ptype = payload.get("type")
        if kind == "event_msg" and ptype == "user_message":
            require(not ended and isinstance(payload.get("message"), str)
                    and sha(payload["message"].encode()) == state["prompt"]["sha256"], "PROMPT")
            users.append(n)
        if kind == "response_item" and ptype == "message" and payload.get("role") == "assistant":
            require(not ended, "CONTENT_AFTER_TERMINAL")
            assistants.append((n, assistant_text(payload)))
        if kind == "event_msg" and ptype == "agent_message":
            require(not ended, "CONTENT_AFTER_TERMINAL")
        if kind == "event_msg" and ptype in ("agent_reasoning", "agent_reasoning_raw_content"):
            require(not ended, "CONTENT_AFTER_TERMINAL")
        if kind == "response_item" and ptype == "message" and payload.get("role") == "user":
            require(not ended, "CONTENT_AFTER_TERMINAL")
        if kind == "response_item" and ptype in ("function_call", "custom_tool_call", "tool_search_call",
                                                   "function_call_output", "custom_tool_call_output"):
            require(not ended, "CONTENT_AFTER_TERMINAL")
        if kind == "event_msg" and ptype == "turn_aborted":
            require(False, "ABORTED")
        if kind == "event_msg" and ptype == "task_complete":
            require(not ended and payload.get("turn_id") == session["turn_id"], "TERMINAL_AMBIGUOUS")
            completions.append((n, payload, raw))
            ended = True
    require(len(meta) == len(starts) == len(users) == len(completions) == 1 and contexts and assistants,
            "SDK_SCOPE")
    require(meta[0].get("id") == session["session_id"] and meta[0].get("cwd") == session["cwd"], "SDK_SESSION")
    complete_line, complete, complete_raw = completions[0]
    final_line, final_text = assistants[-1]
    require(isinstance(complete.get("last_agent_message"), str) and final_text
            and complete["last_agent_message"] == final_text, "FINAL")
    bound_final_sha = state.get("evidence", {}).get("final_response_sha256")
    require(bound_final_sha in (sha(final_text.encode()), sha((final_text + "\n").encode())), "FINAL_SHA")
    events = [r for _, r, _ in jsonl(transcript_bytes)]
    require(len(events) == transcript_ref.get("event_count")
            and [e.get("sequence") for e in events] == list(range(len(events)))
            and all(e.get("identity") == state["identity"] for e in events), "TRANSCRIPT_SCOPE")
    prompt_events = [e for e in events if e.get("type") == "user_message"]
    final_events = [e for e in events if e.get("type") == "assistant_message" and e.get("final") is True]
    terminal_events = [e for e in events if e.get("type") == "status" and e.get("content") == "turn.completed"]
    require(len(prompt_events) == len(final_events) == len(terminal_events) == 1, "TRANSCRIPT_TERMINAL")
    require(sha(prompt_events[0].get("content", "").encode()) == state["prompt"]["sha256"]
            and prompt_events[0].get("source", {}).get("raw_ref") == SDK_PATH + "#L" + str(users[0])
            and final_events[0].get("content") == final_text
            and final_events[0].get("source", {}).get("raw_ref") == SDK_PATH + "#L" + str(final_line)
            and terminal_events[0].get("status", {}).get("turn_id") == session["turn_id"]
            and terminal_events[0].get("source", {}).get("raw_ref") == SDK_PATH + "#L" + str(complete_line),
            "TRANSCRIPT_BINDING")
    return {"profile": PROFILE, "identity": state["identity"],
            "session": {k: session[k] for k in ("thread_id", "turn_id", "session_id", "cwd")},
            "original_state_sha256": sha(state_bytes), "original_projection_status": "running",
            "bound_turn_state": "completed", "history_terminal_event_index": terminal_index,
            "bound_final_message_id": final["message_id"], "bound_final_response_sha256": bound_final_sha,
            "sdk": {"sha256": sha(sdk_bytes), "size": len(sdk_bytes), "terminal_line": complete_line,
                    "terminal_line_sha256_without_lf": sha(complete_raw)},
            "transcript": {"sha256": sha(transcript_bytes), "size": len(transcript_bytes)},
            "original_state_preserved": True, "prompts_resent": False, "scoring_rules_changed": False}


def read_child(root, name):
    require(isinstance(name, str) and name, "PATH")
    p = PurePosixPath(name)
    require(isinstance(name, str) and not p.is_absolute() and ".." not in p.parts and "\\" not in name,
            "PATH")
    path = Path(root).joinpath(*p.parts)
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(Path(root).resolve())
            and path.stat().st_size <= 64 * 1024 * 1024, "FILE")
    return path.read_bytes()


def verify_index(root, index, execution=None, state_bytes=None):
    refs = [r for r in index.get("binding_evidence", []) if r.get("path") in (STATE_PATH, PROOF_PATH)]
    if not refs:
        require(state_bytes is None or not candidate(json.loads(state_bytes)), "PROOF_REQUIRED")
        return None
    require(len(refs) == 2 and {r["path"] for r in refs} == {STATE_PATH, PROOF_PATH}, "PROOF_SCOPE")
    data = {}
    for ref in refs:
        raw = read_child(root, ref["path"])
        require(ref.get("sha256") == sha(raw) and ref.get("size") == len(raw), "PROOF_DIGEST")
        data[ref["path"]] = raw
    require(state_bytes is None or data[STATE_PATH] == state_bytes, "ORIGINAL_STATE_CHANGED")
    state = json.loads(data[STATE_PATH])
    if execution is not None:
        require(execution.get("identity") == state.get("identity") and execution.get("phase") == "COMPLETED"
                and execution.get("execution", {}).get("business_status") == "completed"
                and execution.get("prompt", {}).get("sha256") == state.get("prompt", {}).get("sha256")
                and all(execution.get("session", {}).get(k) == state.get("session", {}).get(k)
                        for k in ("thread_id", "turn_id", "session_id", "cwd")), "EXECUTION_BINDING")
    proof = derive(data[STATE_PATH], index, read_child(root, SDK_PATH), read_child(root, index["transcript"]["path"]))
    require(json.loads(data[PROOF_PATH]) == proof, "PROOF_CONTENT")
    return proof


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if request.get("operation") == "derive":
            result = derive(base64.b64decode(request["state_bytes"]), request["index"],
                            base64.b64decode(request["sdk_bytes"]), base64.b64decode(request["transcript_bytes"]))
        elif request.get("operation") == "verify":
            original = base64.b64decode(request["state_bytes"]) if request.get("state_bytes") else None
            result = verify_index(request["trace_root"], request["index"], request.get("execution"), original)
        else:
            raise ValueError("TERMINAL_PROJECTION_OPERATION")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        sys.exit(str(exc))
