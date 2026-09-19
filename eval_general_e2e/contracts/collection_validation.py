"""Read-only validation of a generic collection's complete input snapshot.

Run as a vendored script. Paths and hashes returned to the Node finalizer bind
its in-memory inputs to the exact state/trace/resource bytes validated here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from execution_state import _relative_path, validate_terminal_execution_state
from validator import validate_contract, validate_transcript_jsonl_bytes


TRACE_SCHEMA = "urn:wildclawbench:schema:general-e2e:trace-index:v2"
RESOURCE_SCHEMA = "urn:wildclawbench:schema:general-e2e:resource-metrics:v1"


def validate_collection(unit_root: Path, state_path: Path, index_path: Path, resource_path: Path) -> dict:
    lexical_root = unit_root.absolute()
    root = unit_root.resolve(strict=True)
    locks: dict[str, dict] = {}

    def read(path: Path) -> bytes:
        original = path.absolute()
        try:
            relative = original.relative_to(lexical_root).as_posix()
        except ValueError:
            relative = original.relative_to(root).as_posix()
        resolved = _relative_path(root, relative, "COLLECTION_PATH_INVALID")
        if resolved != path.resolve(strict=True):
            raise ValueError("COLLECTION_PATH_INVALID")
        if not resolved.is_file():
            raise ValueError("COLLECTION_NOT_REGULAR_FILE")
        if resolved.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("COLLECTION_INPUT_TOO_LARGE")
        data = resolved.read_bytes()
        locked = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        if str(resolved) in locks and locks[str(resolved)] != locked:
            raise ValueError("COLLECTION_INPUT_CHANGED")
        locks[str(resolved)] = locked
        return data

    manifest = json.loads(read(root / "manifest.json"))
    state = json.loads(read(state_path))
    validate_terminal_execution_state(state, unit_root=root, manifest=manifest)
    # Include inputs read by state validation in the snapshot returned to Node.
    prompt_path = Path(state["prompt"]["path"])
    prompt_bytes = read(prompt_path)
    prompt_sha = hashlib.sha256(prompt_bytes).hexdigest()
    task = next(task for task in manifest["tasks"] if task["task_id"] == state["identity"]["task_id"])
    if prompt_sha != state["prompt"]["sha256"] or prompt_sha != task["prompt"]["sent_sha256"]:
        raise ValueError("COLLECTION_PROMPT_SNAPSHOT_MISMATCH")
    for row in state["session"]["binding_evidence"]:
        path = _relative_path(root, row["path"], "BINDING_PATH_INVALID")
        read(path)
        if locks[str(path)] != {"sha256": row["sha256"], "size": row["size"]}:
            raise ValueError("BINDING_DIGEST_MISMATCH")
    index_bytes = read(index_path)
    index = json.loads(index_bytes)
    validate_contract(index, expected_schema_id=TRACE_SCHEMA)
    if index["identity"] != state["identity"]:
        raise ValueError("TRACE_IDENTITY_MISMATCH")
    for key in ("thread_id", "turn_id", "session_id", "cwd"):
        if index["session"][key] != state["session"][key]:
            raise ValueError(f"TRACE_SESSION_MISMATCH: {key}")
    trace_root = index_path.resolve(strict=True).parent
    trusted = {
        "execution/automation-state.json": locks[str(state_path.resolve())],
        "trace/trace-index.json": locks[str(index_path.resolve())],
    }
    artifacts = [index["transcript"], *index["raw_trace"], *index["binding_evidence"]]
    source_paths = set()
    raw_bytes = {}
    transcript_bytes = None
    for row in artifacts:
        path = _relative_path(trace_root, row["path"], "TRACE_ARTIFACT_PATH_INVALID")
        data = read(path)
        if locks[str(path)] != {"sha256": row["sha256"], "size": row["size"]}:
            raise ValueError(f"TRACE_ARTIFACT_HASH_MISMATCH: {row['path']}")
        if row["path"] == "transcript.jsonl":
            transcript_bytes = data
        else:
            trusted[f"trace/{row['path']}"] = locks[str(path)]
            source_paths.add(row["path"])
            raw_bytes[row["path"]] = data
    native_binding = sorted((row["sha256"], row["size"]) for row in state["session"]["binding_evidence"])
    archived_binding = sorted((row["sha256"], row["size"]) for row in index["binding_evidence"])
    if not native_binding or native_binding != archived_binding:
        raise ValueError("TRACE_BINDING_PROVENANCE_MISMATCH")
    events = validate_transcript_jsonl_bytes(transcript_bytes)
    if len(events) != index["transcript"]["event_count"]:
        raise ValueError("TRANSCRIPT_COUNT_MISMATCH")
    if [event["sequence"] for event in events] != list(range(len(events))):
        raise ValueError("TRANSCRIPT_SEQUENCE_NOT_CONTIGUOUS")
    for call in index["calls"]:
        event = events[call["call_sequence"]]
        if event["type"] != "tool_call" or event.get("tool", {}).get("call_id") != call["call_id"]:
            raise ValueError("TRANSCRIPT_CALL_INDEX_MISMATCH")
        if call["result_sequence"] is not None:
            result = events[call["result_sequence"]]
            if result["type"] != "tool_result" or result.get("tool", {}).get("call_id") != call["call_id"]:
                raise ValueError("TRANSCRIPT_RESULT_INDEX_MISMATCH")
    for event in events:
        if event["identity"] != state["identity"]:
            raise ValueError("TRANSCRIPT_IDENTITY_MISMATCH")
        if event["source"]["adapter"] != index["adapter"]["id"]:
            raise ValueError("TRANSCRIPT_ADAPTER_MISMATCH")
        ref = event["source"]["raw_ref"]
        path, _, anchor = (ref or "").partition("#")
        if path not in source_paths:
            raise ValueError(f"TRANSCRIPT_PROVENANCE_UNKNOWN: {ref}")
        if anchor.startswith("L"):
            if not re.fullmatch(r"L[1-9][0-9]*", anchor) or int(anchor[1:]) > len(raw_bytes[path].splitlines()):
                raise ValueError(f"TRANSCRIPT_RAW_RANGE_INVALID: {ref}")
    resource = json.loads(read(resource_path))
    validate_contract(resource, expected_schema_id=RESOURCE_SCHEMA)
    if resource["identity"] != state["identity"]:
        raise ValueError("RESOURCE_IDENTITY_MISMATCH")
    sources = resource["collection"]["sources"]
    seen = set()
    for row in sources:
        path = row["path"]
        if path in seen or path not in trusted:
            raise ValueError(f"RESOURCE_PROVENANCE_UNKNOWN_OR_DUPLICATE: {path}")
        seen.add(path)
        if trusted[path] != {"sha256": row["sha256"], "size": row["size"]}:
            raise ValueError(f"RESOURCE_PROVENANCE_HASH_MISMATCH: {path}")
    if not {"execution/automation-state.json", "trace/trace-index.json"}.issubset(seen):
        raise ValueError("RESOURCE_PROVENANCE_REQUIRED")
    for refs in resource["collection"].get("metric_sources", {}).values():
        for ref in refs:
            if ref.partition("#")[0] not in seen:
                raise ValueError(f"RESOURCE_METRIC_SOURCE_UNKNOWN: {ref}")
    evidence = state.get("extensions", {}).get("evidence", {})
    if evidence.get("final_response_path"):
        path = _relative_path(root, evidence["final_response_path"], "FINAL_RESPONSE_PATH_INVALID")
        read(path)
        if locks[str(path)]["sha256"] != evidence.get("final_response_sha256"):
            raise ValueError("FINAL_RESPONSE_HASH_MISMATCH")
    # Verify every input still equals its validated snapshot before returning.
    for path, expected in list(locks.items()):
        read(Path(path))
    return {"status": "PASS", "locks": locks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("unit-root", "state-file", "trace-index", "resource-metrics"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_collection(args.unit_root, args.state_file, args.trace_index, args.resource_metrics)))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"COLLECTION_VALIDATION_FAILED: {exc}\n")
