"""Use the bound SDK final only for an explicitly authorized execution record."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ADMISSION = "authorized-astronstudio-sdk-final/v1"
AUTHORIZATION = "sdk-final-authorization.json"
VERIFIER = "astronstudio-final-prefix-divergence.mjs"
MISSING = "native-final-prefix-divergence"
PROOF = "bindings/final-prefix-divergence-proof.json"
ORIGINAL_STATE = "bindings/final-prefix-original-state.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _require(value, label):
    if not value:
        raise ValueError(label)


def candidate(execution):
    evidence = execution.get("evidence", {})
    return (
        execution.get("harness", {}).get("id") == "astronstudio"
        and execution.get("phase") == "COMPLETED"
        and execution.get("execution", {}).get("business_status") == "completed"
        and execution.get("session", {}).get("verified") is True
        and evidence.get("completeness") == "partial"
        and evidence.get("missing") == [MISSING]
        and all(evidence.get(key) for key in ("trace_index_path", "transcript_path", "final_response_path"))
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
    raise ValueError("SDK final verifier unavailable")


def validate(execution, record_bytes, contract_bytes, files):
    _require(candidate(execution), "expected only the authorized native final discrepancy")
    authority = json.loads(files[AUTHORIZATION])
    identity = execution["identity"]
    _require(authority.get("schema_version") == ADMISSION
             and isinstance(authority.get("authorization_reference"), str)
             and authority["authorization_reference"].strip(), "authorization required")
    records = [row for row in authority["tasks"] if row["identity"] == identity]
    _require(len(records) == 1, "execution not uniquely authorized")
    approved = records[0]
    _require(approved["execution_record_sha256"] == sha(record_bytes)
             and approved["contract_sha256"] == sha(contract_bytes)
             and approved["trace_index_sha256"] == sha(files["trace-index.json"])
             and approved["divergence_proof_sha256"] == sha(files[PROOF]), "authorization binding drift")
    index = json.loads(files["trace-index.json"])
    _require(index.get("schema_id") == "urn:wildclawbench:schema:general-e2e:trace-index:v1"
             and index.get("adapter", {}).get("id") == "astronstudio-provider-runtime-events"
             and index.get("completeness", {}).get("missing") == [MISSING]
             and index.get("completeness", {}).get("omitted_event_count") == 0,
             "unexpected trace scope")
    verifier = _verifier()
    node = shutil.which("node")
    _require(node, "Node runtime unavailable")
    script = """
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const {verifyFinalPrefix, FINAL_PREFIX_STATE} = await import(process.argv[1]);
const root = process.argv[2];
const read = name => readFile(resolve(root, name));
const index = JSON.parse(await read('trace-index.json'));
const record = JSON.parse(await read('bound-execution.json'));
const proof = await verifyFinalPrefix(index, await read(FINAL_PREFIX_STATE), root, record);
process.stdout.write(JSON.stringify(proof));
"""
    with tempfile.TemporaryDirectory(prefix="astronstudio-sdk-final-") as directory:
        root = Path(directory)
        for name, raw in files.items():
            relative = Path(name)
            _require(not relative.is_absolute() and ".." not in relative.parts, "invalid evidence path")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (root / "bound-execution.json").write_bytes(record_bytes)
        run = subprocess.run([node, "--input-type=module", "-e", script, verifier.as_uri(), str(root)],
                             capture_output=True, timeout=30)
        _require(run.returncode == 0, "native divergence proof rejected: " + run.stderr.decode(errors="replace")[-1200:])
        proof = json.loads(run.stdout)
    _require(proof == json.loads(files[PROOF])
             and proof["source_state_sha256"] == sha(files[ORIGINAL_STATE])
             and proof["original_final_sha256"] == sha(files["final-response-bound.txt"])
             and proof["sdk_final_sha256"] == approved["sdk_final_sha256"], "native proof binding drift")
    state = json.loads(files[ORIGINAL_STATE])
    _require(state.get("prompt", {}).get("sha256") == execution.get("prompt", {}).get("sha256"),
             "sent prompt mismatch")
    transcript_ref = index["transcript"]
    transcript = files[transcript_ref["path"]]
    _require(sha(transcript) == transcript_ref["sha256"] and len(transcript) == transcript_ref["size"],
             "canonical transcript mismatch")
    messages = [row for row in map(json.loads, transcript.splitlines()) if row.get("type") == "assistant_message"]
    _require(messages and messages[-1].get("identity") == identity
             and sha(messages[-1]["content"].encode()) == proof["sdk_final_sha256"],
             "canonical transcript final differs from the authorized SDK final")
    return {
        "schema_version": ADMISSION, "identity": identity, "profile": ADMISSION,
        "authorization_reference": authority["authorization_reference"],
        "execution_record_sha256": sha(record_bytes),
        "scoring_reply_sha256": proof["sdk_final_sha256"],
        "native_reply_document_sha256": proof["original_final_sha256"],
        "scoring_reply_event_id": messages[-1]["event_id"],
        "scoring_reply_basis": "same-turn SDK final explicitly authorized for scoring",
        "client_display_of_sdk_final_verified": False,
        "original_execution_changed": False, "original_trace_changed": False,
        "proof": proof,
        "files": [{"path": name, "sha256": sha(raw), "size": len(raw)} for name, raw in sorted(files.items())],
    }
