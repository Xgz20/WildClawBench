"""Verified terminal failures may be graded against an output-only contract.

This admission preserves FAILED and the source failure; it never manufactures
a successful execution or decides a score. The ordinary grader and Judge run.
"""
import hashlib
import json
from pathlib import Path

ADMISSION = "verified-failed-output-evidence/v1"
POLICY_PATH = Path(__file__).resolve().parents[1] / "references/reviewed-failure-evidence-policy.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError("FAILED_OUTPUT_ADMISSION_" + code)


def profile(execution, contract):
    digest = sha(json.dumps(dict(contract), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    require(POLICY_PATH.is_file() and not POLICY_PATH.is_symlink(), "POLICY_MISSING")
    policy = json.loads(POLICY_PATH.read_text())
    reviewed = policy.get("profiles", {}).get(digest)
    require(policy.get("schema_version") == "wildclawbench.failed-output-evidence-policy/v1"
            and isinstance(reviewed, dict) and reviewed.get("task_id") == contract.get("task_id")
            and reviewed.get("grading_type") == contract.get("grading_type")
            and reviewed.get("candidate_required") is True
            and reviewed.get("tool_history_required") is False
            and reviewed.get("final_response_required") is False, "CONTRACT_NOT_REVIEWED")
    require(execution.get("harness", {}).get("id") == "astronstudio", "NATIVE_FAILURE_PROFILE_UNSUPPORTED")
    require(execution.get("phase") == "FAILED"
            and execution["execution"]["business_status"] == "candidate_error"
            and execution["prompt"]["send_status"] == "sent"
            and execution["session"]["verified"] is True
            and execution["candidate"]["drift_status"] == "stable"
            and execution.get("failure_evidence", {}).get("schema") == ADMISSION, "EXECUTION_INVALID")
    return ADMISSION


def read_files(unit_root, execution):
    binding = execution["failure_evidence"]
    p = Path(unit_root) / binding["path"]
    require(p.resolve().is_relative_to(Path(unit_root).resolve()) and p.is_file() and not p.is_symlink(), "PATH")
    files = {"proof.json": p.read_bytes()}
    require(sha(files["proof.json"]) == binding["sha256"], "PROOF_SHA")
    proof = json.loads(files["proof.json"])
    names = [row["path"] for row in proof["files"]]
    require(len(set(names)) == len(names) and "proof.json" not in names, "DUPLICATE_SOURCE")
    for row in proof["files"]:
        q = p.parent / row["path"]
        require(q.resolve().is_relative_to(p.parent.resolve()) and q.is_file() and not q.is_symlink(), "SOURCE_PATH")
        files[row["path"]] = q.read_bytes()
    return files


def validate(execution, contract, files):
    profile(execution, contract)
    require(sha(files["proof.json"]) == execution["failure_evidence"]["sha256"], "PROOF_SHA")
    proof = json.loads(files["proof.json"])
    require(proof["identity"] == execution["identity"], "IDENTITY")
    names = [row["path"] for row in proof["files"]]
    require(len(set(names)) == len(names) and "proof.json" not in names, "DUPLICATE_SOURCE")
    for row in proof["files"]:
        require(row["path"] in files and sha(files[row["path"]]) == row["sha256"]
                and len(files[row["path"]]) == row["size"], "ARTIFACT_SHA")
    original = json.loads(files["original-execution-record.json"])
    require(sha(files["original-execution-record.json"]) == proof.get("source_record_sha256"), "ORIGINAL_RECORD_SHA")
    revision = execution.get("collection_revision")
    if revision is not None:
        require(revision.get("source_execution_record_sha256") == proof["source_record_sha256"]
                and revision.get("original_business_status") == original["execution"]["business_status"]
                and revision.get("no_prompt_resent") is True, "REVISION_BINDING")
    state = json.loads(files["original-state.json"])
    require(original["identity"] == state["identity"] == execution["identity"], "SOURCE_IDENTITY")
    require(original["candidate"]["frozen_sha256"] == execution["candidate"]["frozen_sha256"], "CANDIDATE_BINDING")
    require(original["prompt"] == execution["prompt"] == state["prompt"] or
            (original["prompt"] == execution["prompt"] and state["prompt"]["sha256"] == execution["prompt"]["sha256"]), "PROMPT_BINDING")
    require(sha(files["PROMPT.md"]) == execution["prompt"]["sha256"], "PROMPT_SHA")
    require(state["phase"] == "FAILED" and state["session"]["verified"] is True
            and state["send"]["dispatch_attempt_count"] == 1
            and state["session"]["session_id"] == execution["session"]["session_id"]
            and state["session"]["cwd"] == execution["session"]["cwd"], "TERMINAL_BINDING")
    if execution["harness"]["id"] == "astronstudio":
        require(state["session"]["native_status"] in {"error", "failed"}
                and state["execution"]["error"]["code"] in {"ASTRONSTUDIO_TURN_ERROR", "ASTRONSTUDIO_TURN_FAILED"}
                and bool(state["execution"]["error"]["message"]), "ASTRON_NATIVE_FAILURE")
        manifest = json.loads(files["original-evidence-manifest.json"])
        entry = [r for r in manifest["artifacts"] if r["path"].endswith("/execution/automation-state.json")]
        require(len(entry) == 1 and entry[0]["sha256"] == sha(files["original-state.json"]), "ASTRON_STATE_BINDING")
    else:
        raise ValueError("FAILED_OUTPUT_ADMISSION_HARNESS_UNSUPPORTED")
    return {"schema_version": ADMISSION, "identity": execution["identity"],
            "policy_sha256": sha(POLICY_PATH.read_bytes()),
            "contract_canonical_sha256": sha(json.dumps(dict(contract), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()),
            "original_failure_preserved": True, "candidate_required": True,
            "tool_history_required_by_rubric": False,
            "files": [{"path": name, "sha256": sha(value), "size": len(value)} for name, value in sorted(files.items())]}
