"""Verify an explicitly selected AStudio turn stopped by its native runtime."""

from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from astronstudio_sdk_final_admission import sha

ADMISSION = "authorized-astronstudio-native-interruption/v1"
AUTHORIZATION = "reviewed-interruption-authorization.json"
VERIFIER = "astronstudio-runtime-interruption.mjs"
SDK = "raw/astronstudio-rollout.jsonl"
PROOF = "bindings/runtime-interruption-proof.json"


def _require(condition, detail):
    if not condition:
        raise ValueError(detail)


def candidate(execution):
    evidence = execution.get("evidence", {})
    return (
        execution.get("harness", {}).get("id") == "astronstudio"
        and execution.get("phase") == "FAILED"
        and execution.get("execution", {}).get("business_status") in {"cancelled", "candidate_error"}
        and execution.get("prompt", {}).get("send_status") == "sent"
        and execution.get("session", {}).get("verified") is True
        and evidence.get("completeness") == "partial"
        and not evidence.get("final_response_path")
        and all(evidence.get(key) for key in ("trace_index_path", "transcript_path"))
    )


def _verifier():
    skill = Path(__file__).resolve().parents[1]
    packaged = skill / "vendor/e2e-shared/general-resource-supplements" / VERIFIER
    if packaged.is_file():
        return packaged
    for parent in skill.parents:
        source = parent / "tools/report/e2e-shared/general-resource-supplements" / VERIFIER
        if (parent / ".git").exists() and source.is_file():
            return source
    raise ValueError("native interruption verifier unavailable")


def _verify_native(files, record_bytes):
    script = """
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const {verifyRuntimeInterruption, RUNTIME_INTERRUPTION_STATE} = await import(process.argv[1]);
const root = process.argv[2];
const read = name => readFile(resolve(root, name));
const index = JSON.parse(await read('trace-index.json'));
const record = JSON.parse(await read('bound-execution.json'));
const proof = await verifyRuntimeInterruption(index, await read(RUNTIME_INTERRUPTION_STATE), root, record);
process.stdout.write(JSON.stringify(proof));
"""
    node = shutil.which("node")
    _require(node, "Node runtime unavailable")
    with tempfile.TemporaryDirectory(prefix="astronstudio-interruption-") as directory:
        root = Path(directory)
        for name, raw in files.items():
            relative = Path(name)
            _require(not relative.is_absolute() and ".." not in relative.parts
                     and relative.as_posix() != "bound-execution.json", "invalid evidence path")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (root / "bound-execution.json").write_bytes(record_bytes)
        result = subprocess.run([node, "--input-type=module", "-e", script, _verifier().as_uri(), str(root)],
                                capture_output=True, timeout=30)
        _require(result.returncode == 0, "native interruption rejected: " + result.stderr.decode(errors="replace")[-1200:])
        return json.loads(result.stdout)


def validate(execution, record_bytes, contract_bytes, files):
    _require(candidate(execution), "expected a verified native interruption without a final response")
    authority = json.loads(files[AUTHORIZATION])
    identity = execution["identity"]
    _require(authority.get("schema_version") == ADMISSION
             and isinstance(authority.get("authorization_reference"), str)
             and authority["authorization_reference"].strip(), "authorization required")
    approved = [row for row in authority["tasks"] if row["identity"] == identity]
    binding = {
        "execution_record_sha256": sha(record_bytes), "contract_sha256": sha(contract_bytes),
        "trace_index_sha256": sha(files["trace-index.json"]), "sdk_sha256": sha(files[SDK]),
        "proof_sha256": sha(files[PROOF]), "candidate_sha256": execution["candidate"]["frozen_sha256"],
        "prompt_sha256": execution["prompt"]["sha256"],
    }
    _require(len(approved) == 1 and all(approved[0].get(key) == value for key, value in binding.items()),
             "authorization binding drift")
    index = json.loads(files["trace-index.json"])
    _require(index.get("identity") == identity
             and index.get("schema_id") == "urn:wildclawbench:schema:general-e2e:trace-index:v1"
             and index.get("adapter", {}).get("id") == "astronstudio-provider-runtime-events"
             and index.get("canonical_source_policy", {}).get("id") == "bound-native-sdk-canonical/v1"
             and index.get("completeness", {}).get("omitted_event_count") == 0
             and set(index["completeness"]["missing"]) <= {
                 "assistant_message", "runtime-provider-turn-projection-unavailable", "runtime-state-session-projection-stale",
             }, "unexpected trace scope")
    for row in [index["transcript"], *index["raw_trace"], *index["binding_evidence"]]:
        raw = files[row["path"]]
        _require(len(raw) == row["size"] and sha(raw) == row["sha256"], "trace artifact drift")
    proof = _verify_native(files, record_bytes)
    _require(proof and proof == json.loads(files[PROOF]), "native interruption proof drift")
    state = json.loads(files["bindings/runtime-interruption-original-state.json"])
    _require(state["prompt"]["sha256"] == binding["prompt_sha256"], "sent prompt mismatch")
    events = [json.loads(line) for line in files[index["transcript"]["path"]].splitlines() if line.strip()]
    calls = Counter(row["tool"]["call_id"] for row in events if row["type"] == "tool_call")
    results = Counter(row["tool"]["call_id"] for row in events if row["type"] == "tool_result")
    _require(len(events) == index["transcript"]["event_count"] and all(row["identity"] == identity for row in events)
             and calls and calls == results and all(call_id and count == 1 for call_id, count in calls.items())
             and events[-1]["type"] == "status"
             and events[-1]["status"]["type"] == "turn_aborted"
             and events[-1]["status"]["turn_id"] == execution["session"]["turn_id"]
             and not any(row.get("final") is True for row in events), "canonical interruption transcript is incomplete")
    return {
        "schema_version": ADMISSION, "profile": ADMISSION, "identity": identity, **binding,
        "authorization_reference": authority["authorization_reference"], "proof": proof,
        "matched_tool_call_results": len(calls), "final_response_present": False,
        "original_execution_changed": False, "original_trace_changed": False,
        "files": [{"path": name, "sha256": sha(raw), "size": len(raw)} for name, raw in sorted(files.items())],
    }
