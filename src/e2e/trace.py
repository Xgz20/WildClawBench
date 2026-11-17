"""Bound AStudio rollout normalization with raw line provenance."""
from __future__ import annotations

import base64
import hashlib
import json
import ntpath
import re
from pathlib import Path

from .common import E2EError, atomic_json, file_sha256, utc_now


ADAPTER = "agentcube-astudio-native"


def mcp_callable_matches(name, server, tool) -> bool:
    """Replay acode's ASCII connector-name shortening; never relax argument binding."""
    if not all(isinstance(value, str) and value for value in (name, server, tool)):
        return False
    prefix = "mcp__" + server + "__"
    if name.startswith(prefix) and name.endswith("__" + tool):
        return True
    # acode hashes the raw five-part identity before truncating a name to 64 bytes.
    # Namespace collision hashes, sanitization and Unicode aliases remain unsupported.
    if server != "acode_apps" or len(name) != 64 or not re.fullmatch(r"[A-Za-z0-9_]+", tool):
        return False
    match = re.fullmatch(r"mcp__acode_apps__(connector_[A-Za-z0-9_]+)__(.+)", name)
    if not match:
        return False
    connector = match[1]
    namespace = server + "__" + connector
    visible_prefix = "mcp__" + namespace + "__"
    if len(visible_prefix + tool) <= 64:
        return False
    identity = "\0".join((server, namespace, connector, tool, tool))
    suffix = "_" + hashlib.sha1(identity.encode("ascii")).hexdigest()[:12]
    keep = 64 - len(visible_prefix) - len(suffix)
    return keep >= 1 and name == visible_prefix + tool[:keep] + suffix


def windows_equal(left: str, right: str) -> bool:
    return ntpath.normcase(ntpath.normpath(left)) == ntpath.normcase(ntpath.normpath(right))


def model_identity(value: str) -> str:
    if value.startswith("builtin/"):
        encoded = value.split("/", 1)[1]
        try:
            return base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True).decode("utf-8")
        except (ValueError, UnicodeError) as error:
            raise E2EError("NATIVE_MODEL_ENCODING_INVALID") from error
    return value


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


def _prompt_binding(actual, expected: str) -> dict:
    def canonical(value):
        return value.replace("\r\n", "\n").strip()

    if not isinstance(actual, str):
        raise E2EError("NATIVE_PROMPT_MISMATCH")
    kind = "plain-text"
    decoded = actual
    if canonical(actual) != canonical(expected):
        # 新版客户端会折叠长粘贴；只接受单个纯文本块，正文仍须完整匹配冻结题目。
        # 不丢弃附加正文、多附件或未知字段，原始 user_message 继续按原字节留证。
        value = canonical(actual)
        opening, closing = "<pasted_text>\n", "\n</pasted_text>"
        if not value.startswith(opening) or not value.endswith(closing):
            raise E2EError("NATIVE_PROMPT_MISMATCH")
        try:
            entries = json.loads(value[len(opening):-len(closing)])
        except json.JSONDecodeError as error:
            raise E2EError("NATIVE_PROMPT_MISMATCH") from error
        if (not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict)
                or set(entries[0]) != {"text"} or not isinstance(entries[0]["text"], str)):
            raise E2EError("NATIVE_PROMPT_MISMATCH")
        decoded = entries[0]["text"]
        if canonical(decoded) != canonical(expected):
            raise E2EError("NATIVE_PROMPT_MISMATCH")
        kind = "astudio-single-pasted-text-json"
    return {"kind": kind, "native_message_sha256": hashlib.sha256(actual.encode("utf-8")).hexdigest(),
            "decoded_text_sha256": hashlib.sha256(decoded.encode("utf-8")).hexdigest()}


def normalize_rollout(path: Path, *, identity: dict, prompt: str, guest_cwd: str,
                      requested_model: str, requested_effort: str | None, report: dict) -> dict:
    raw = path.read_bytes()
    rows = []
    for number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if line.strip():
            item = json.loads(line)
            if not isinstance(item, dict) or not isinstance(item.get("payload"), dict):
                raise E2EError("NATIVE_EVENT_SHAPE_INVALID")
            rows.append((number, item))
    headers = [item["payload"] for _, item in rows if item.get("type") == "session_meta"]
    contexts = [item["payload"] for _, item in rows if item.get("type") == "turn_context"]
    users = [(line, item) for line, item in rows if item.get("type") == "event_msg" and item["payload"].get("type") == "user_message"]
    terminals = [(line, item) for line, item in rows if item.get("type") == "event_msg" and item["payload"].get("type") == "task_complete"]
    if len(headers) != 1 or not contexts or len(users) != 1 or len(terminals) != 1:
        raise E2EError("NATIVE_SINGLE_TASK_BINDING_AMBIGUOUS")
    header = headers[0]
    turn_ids = {context.get("turn_id") for context in contexts}
    if len(turn_ids) != 1 or None in turn_ids or not header.get("id"):
        raise E2EError("NATIVE_IDENTITY_MISSING")
    turn_id = next(iter(turn_ids))
    if terminals[0][1]["payload"].get("turn_id") != turn_id or terminals[0][0] <= users[0][0]:
        raise E2EError("NATIVE_TERMINAL_MISMATCH")
    if any(not isinstance(context.get("cwd"), str) or not windows_equal(context["cwd"], guest_cwd)
           for context in [header, *contexts]):
        raise E2EError("NATIVE_WORKSPACE_MISMATCH")
    actual_prompt = users[0][1]["payload"].get("message")
    prompt_binding = _prompt_binding(actual_prompt, prompt)
    models = {model_identity(str(context.get("model") or "")) for context in contexts}
    expected_model = "astronclaw-auto" if requested_model.casefold() == "auto" else requested_model
    if len(models) != 1 or next(iter(models)).casefold() != expected_model.casefold():
        raise E2EError("TESTED_MODEL_MISMATCH")
    efforts = {str(context.get("effort") or "").casefold() for context in contexts}
    if requested_effort is not None and efforts != {requested_effort.casefold()}:
        raise E2EError("TESTED_REASONING_MISMATCH")
    events, missing, calls, results = [], [], {}, {}
    mcp_ends = []
    filtered = 0
    raw_name = "raw/" + path.name

    def emit(number, item, kind, **data):
        sequence = len(events)
        events.append({"schema_id": "urn:wildclawbench:schema:general-e2e:transcript-event:v1",
                       "schema_version": 1, "identity": identity, "event_id": f"native-L{number}",
                       "sequence": sequence, "occurred_at": item.get("timestamp"), "type": kind,
                       "source": {"adapter": ADAPTER, "raw_ref": f"{raw_name}#L{number}", "redacted": False}, **data})
        return sequence

    for number, item in rows:
        outer, payload = item.get("type"), item["payload"]
        kind = payload.get("type")
        if outer == "event_msg" and kind == "user_message":
            emit(number, item, "user_message", role="user", content=payload["message"])
        elif outer == "response_item" and kind == "message" and payload.get("role") == "assistant":
            emit(number, item, "assistant_message", role="assistant", content=_text(payload.get("content")))
        elif outer == "response_item" and kind in {"function_call", "custom_tool_call"}:
            call_id = payload.get("call_id")
            if not call_id or call_id in calls or not isinstance(payload.get("name"), str) or not payload["name"]:
                raise E2EError("NATIVE_CALL_ID_INVALID")
            arguments = payload.get("arguments", payload.get("input"))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    pass
            calls[call_id] = emit(number, item, "tool_call", tool={"call_id": call_id,
                "name": payload["name"], "arguments": arguments})
        elif outer == "response_item" and kind in {"function_call_output", "custom_tool_call_output"}:
            call_id = payload.get("call_id")
            if not call_id or call_id in results:
                raise E2EError("NATIVE_RESULT_ID_INVALID")
            result = payload.get("output")
            results[call_id] = emit(number, item, "tool_result", tool={"call_id": call_id,
                "result": result, "status": "unknown"}, content=result if isinstance(result, str) else None)
        elif outer == "event_msg" and kind == "token_count":
            emit(number, item, "usage", usage=payload.get("info"))
        elif outer == "event_msg" and kind in {"task_started", "task_complete", "error", "warning"}:
            emit(number, item, "error" if kind == "error" else "status", content=kind,
                 native_status=payload)
        elif outer == "event_msg" and kind == "mcp_tool_call_end":
            mcp_ends.append(payload)
            emit(number, item, "status", content=kind, native_status=payload)
        elif outer in {"session_meta", "world_state", "turn_context", "compacted"}:
            if outer == "compacted":
                missing.append("unsupported_native_type:compacted")
            filtered += 1
        elif outer == "response_item" and kind in {"message", "reasoning"}:
            filtered += 1
        elif outer == "event_msg" and kind in {"agent_reasoning", "agent_message", "patch_apply_end"}:
            filtered += 1
        else:
            missing.append(f"unsupported_native_type:{outer}/{kind}")
            filtered += 1
    if set(calls) != set(results):
        missing.append("native-tool-trajectory-incomplete")
    for end in mcp_ends:
        call_id = end.get("call_id")
        if call_id not in calls or call_id not in results:
            missing.append("mcp-end-without-canonical-pair")
            continue
        invocation = end.get("invocation") or {}
        call = events[calls[call_id]]["tool"]
        server, tool = invocation.get("server"), invocation.get("tool")
        if (not mcp_callable_matches(call["name"], server, tool)
                or call["arguments"] != invocation.get("arguments")):
            raise E2EError("NATIVE_MCP_INVOCATION_MISMATCH")
    if any(results[key] < calls[key] for key in set(calls) & set(results)):
        raise E2EError("NATIVE_TOOL_ORDER_INVALID")
    final = terminals[0][1]["payload"].get("last_agent_message")
    if not isinstance(final, str):
        raise E2EError("NATIVE_FINAL_RESPONSE_MISSING")
    assistant = [event for event in events if event["type"] == "assistant_message"]
    if not assistant or assistant[-1]["content"].strip() != final.strip():
        raise E2EError("NATIVE_FINAL_RESPONSE_MISMATCH")
    native_usage = [item["payload"]["info"].get("total_token_usage") for _, item in rows
                    if item["payload"].get("type") == "token_count" and isinstance(item["payload"].get("info"), dict)]
    usage = report.get("usage")
    usage_valid = isinstance(usage, dict)
    if usage_valid:
        for report_key, native_key in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                                       ("cache_tokens", "cached_input_tokens")):
            value = usage.get(report_key)
            if type(value) is not int or value < 0 or not native_usage or value != (native_usage[-1] or {}).get(native_key):
                usage_valid = False
    binding = {"schema": "wildclawbench.agentcube-native-binding/v1", "identity": identity,
            "session": {"thread_id": None, "turn_id": turn_id, "session_id": header["id"],
                        "cwd": contexts[0]["cwd"], "lifecycle_generation": None},
            "actual_model": "auto" if next(iter(models)) == "astronclaw-auto" else next(iter(models)),
            "native_model": next(iter(models)),
            "reasoning_effort": next(iter(efforts)) if len(efforts) == 1 else None,
            "prompt_transport": prompt_binding,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "user_line": users[0][0], "terminal_line": terminals[0][0],
            "native_event_count": len(rows), "filtered_native_event_count": filtered,
            "events": events, "calls": [{"call_id": key, "call_sequence": sequence,
                                           "result_sequence": results.get(key)} for key, sequence in calls.items()],
            "missing": sorted(set(missing)), "final_response": final,
            "usage": usage if usage_valid else None,
            "usage_warning": None if usage_valid else "report-usage-native-reconciliation-unavailable",
            "native_duration_ms": terminals[0][1]["payload"].get("duration_ms")}
    # Current clients expose complete native last/cumulative usage; replay the exact
    # same deduplication/reconciliation profile used by the General report Skill.
    if any(isinstance(item["payload"].get("info"), dict) and "last_token_usage" in item["payload"]["info"]
           for _, item in rows if item["payload"].get("type") == "token_count"):
        from .native_resources import replay_resources
        try:
            binding["native_resources"] = replay_resources(path, binding)
        except E2EError as error:
            binding["native_resource_error"] = str(error)
    return binding


def write_trace(directory: Path, native_path: Path, binding: dict, *, binding_artifacts: list[dict]) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    raw = directory / "raw" / native_path.name
    raw.parent.mkdir(exist_ok=True)
    raw.write_bytes(native_path.read_bytes())
    transcript = directory / "transcript.jsonl"
    transcript.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in binding["events"]), encoding="utf-8")
    index = {"schema_id": "urn:wildclawbench:schema:general-e2e:trace-index:v2", "schema_version": 2,
             "identity": binding["identity"], "adapter": {"id": binding.get("adapter",ADAPTER), "version": "0.1.0", "source": "bound product native trace" if binding.get("adapter") else "bound AStudio native rollout"},
             "session": binding["session"],
             "transcript": {"path": "transcript.jsonl", "sha256": file_sha256(transcript), "size": transcript.stat().st_size,
                            "event_count": len(binding["events"])},
             "raw_trace": [{"path": raw.relative_to(directory).as_posix(), "sha256": file_sha256(raw), "size": raw.stat().st_size}],
             "raw_event_range": {"first_sequence": 0, "last_sequence": binding["native_event_count"] - 1,
                                 "event_count": binding["native_event_count"]},
             "normalization": {"native_event_count": binding["native_event_count"], "normalized_event_count": len(binding["events"]),
                               "filtered_native_event_count": binding["filtered_native_event_count"],
                               "compatibility_profiles": [binding.get("adapter",ADAPTER)+"/v1"]},
             "completeness": {"status": "partial" if binding["missing"] else "complete",
                              "omitted_event_count": 0, "missing": binding["missing"]},
             "calls": binding["calls"], "binding_evidence": binding_artifacts}
    atomic_json(directory / "trace-index.json", index)
    return index


def ensure_resource_coverage(document: dict) -> dict:
    """Describe coverage of the single bound task turn for report consumers."""
    document["collection"].setdefault("coverage", {
        field: {"known": int(value["value"] is not None and value["status"] in {"observed", "inferred"}),
                "total": 1, "unit": "task-turn"}
        for group in document["metrics"].values() for field, value in group.items()
    })
    return document


def resource_metrics(identity: dict, binding: dict, sources: list[dict]) -> dict:
    if binding.get("adapter")=="agentcube-workbuddy-native":
        native=binding["native_resources"]
        return ensure_resource_coverage({"schema_id":"urn:wildclawbench:schema:general-e2e:resource-metrics:v1","schema_version":1,"identity":identity,
            "collection":{"collector":binding["adapter"],"version":"0.1.0","status":"partial","collected_at":utc_now(),"sources":sources,"excluded_scope":["controller","judge","unlinked_child_agents"],"known_subtotals":native.get("collection",{}).get("known_subtotals",{}),"warnings":native.get("collection",{}).get("warnings",[])},"metrics":native["metrics"]})
    def metric(value, basis):
        return {"value": value, "status": "observed" if value is not None else "unavailable", "basis": basis}
    usage = binding.get("usage") or {}
    input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    duration_ms = binding.get("native_duration_ms")
    duration = duration_ms / 1000 if type(duration_ms) in {int, float} and duration_ms >= 0 else None
    document = ensure_resource_coverage({"schema_id": "urn:wildclawbench:schema:general-e2e:resource-metrics:v1", "schema_version": 1,
            "identity": identity,
            "collection": {"collector": ADAPTER, "version": "0.1.0", "status": "partial", "collected_at": utc_now(),
                           "sources": sources, "warnings": [binding["usage_warning"]] if binding.get("usage_warning") else [],
                           "excluded_scope": ["controller", "judge", "unbound_background_activity"]},
            "metrics": {"usage": {
                "input_tokens": metric(input_tokens, "wgui RunReport usage reconciled with native cumulative usage"),
                "output_tokens": metric(output_tokens, "wgui RunReport usage reconciled with native cumulative usage"),
                "total_tokens": metric(input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None, "input plus output"),
                "cache_read_input_tokens": metric(usage.get("cache_tokens"), "wgui RunReport cache_tokens"),
                "cache_creation_input_tokens": metric(None, "not supplied by controller v2"),
                "reasoning_output_tokens": metric(None, "not supplied by controller v2")},
                "requests": {"request_count": metric(None, "controller v2 does not expose a verified model request count"),
                             "request_attempt_count": metric(None, "HTTP attempts unavailable")},
                "tools": {"call_count": metric(len(binding["calls"]) if not binding["missing"] else None,
                                                "unique bound native call IDs with paired results")},
                "timing": {"duration_seconds": metric(None, "same-clock local prompt acceptance time unavailable"),
                           "agent_duration_seconds": metric(duration, "native task_complete.duration_ms")}}})

    native = binding.get('native_resources')
    if native:
        for group in ('usage', 'requests'):
            document['metrics'][group] = native['metrics'][group]
            for field in native['metrics'][group]:
                document['collection']['coverage'][field] = native['collection']['coverage'][field]
        document['collection']['known_subtotals'] = {k: v for k, v in native['collection']['known_subtotals'].items()
                                                    if k in document['collection']['coverage']}
        document['collection']['native_usage_reconciliation'] = native['usage_reconciliation']
        document['collection']['native_parser'] = native['parser']
        document['collection']['warnings'] += native['collection']['warnings']
        if native['usage_reconciliation']['reconciled']:
            document['collection']['warnings'] = [w for w in document['collection']['warnings']
                if w != 'report-usage-native-reconciliation-unavailable']
            if not binding.get('usage'):
                document['collection']['warnings'].append('controller-usage-differs; bound native usage is authoritative; reasoning is included in output')
    elif binding.get('native_resource_error'):
        document['collection']['warnings'].append(binding['native_resource_error'])
        for group in ('usage', 'requests'):
            for field in document['metrics'][group]:
                document['metrics'][group][field] = metric(None, 'native usage replay failed; no controller fallback')
                document['collection']['coverage'][field]['known'] = 0
    return document
