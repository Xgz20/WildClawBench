"""Verify native terminal failures for scoring admission or a quota stop.

This admission preserves FAILED and the source failure; it never manufactures
a successful execution or decides a score. Reviewed candidate failures use the
ordinary grader/Judge; verified external quota failures require human recovery.
"""
import hashlib
import json
import re
from pathlib import Path
import execution_accountability

ADMISSION = "verified-failed-output-evidence/v1"
POLICY_PATH = Path(__file__).resolve().parents[1] / "references/reviewed-failure-evidence-policy.json"
NATIVE_QUOTA_MESSAGE = re.compile(
    r"unexpected status 402(?: Payment Required)?: astron_points_exhausted(?:, url: \S+)?\Z"
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError("FAILED_OUTPUT_ADMISSION_" + code)


def _native_failure_profile(execution):
    require(execution.get("harness", {}).get("id") == "astronstudio", "NATIVE_FAILURE_PROFILE_UNSUPPORTED")
    require(execution.get("phase") == "FAILED"
            and execution["execution"]["business_status"] == "candidate_error"
            and execution["prompt"]["send_status"] == "sent"
            and execution["session"]["verified"] is True
            and execution["candidate"]["drift_status"] == "stable"
            and execution.get("failure_evidence", {}).get("schema") == ADMISSION, "EXECUTION_INVALID")


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
    _native_failure_profile(execution)
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


def _validate_sources(execution, files):
    """Validate native failure provenance independently of scoring policy."""
    _native_failure_profile(execution)
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
    return proof, original, state


def is_external_quota(execution):
    """Recognize only the native provider error format, never candidate text."""
    native = execution.get("execution")
    error = native.get("error") if isinstance(native, dict) else None
    harness = execution.get("harness")
    if not isinstance(error, dict) or not isinstance(harness, dict):
        return False
    return (harness.get("id") == "astronstudio"
            and isinstance(error.get("code"), str)
            and error["code"] in {"ASTRONSTUDIO_TURN_ERROR", "ASTRONSTUDIO_TURN_FAILED"}
            and isinstance(error.get("message"), str)
            and NATIVE_QUOTA_MESSAGE.fullmatch(error["message"]) is not None)


def validate_external_quota(execution, files):
    """Prove an infrastructure stop without grading or an ID allowlist.

    Both source records and the state must bind the same native error; edited
    messages, unbound proofs and arbitrary HTTP 402 responses remain failures.
    """
    proof, original, state = _validate_sources(execution, files)
    require(proof.get("schema") == ADMISSION, "PROOF_SCHEMA")
    manifest = json.loads(files["original-evidence-manifest.json"])
    require(manifest.get("identity") == execution["identity"], "EVIDENCE_IDENTITY")
    require(original.get("phase") == "FAILED"
            and original["execution"].get("business_status") == "candidate_error"
            and original["session"].get("verified") is True, "ORIGINAL_TERMINAL")
    for key in ("thread_id", "turn_id", "session_id", "cwd"):
        value = execution["session"].get(key)
        require(isinstance(value, str) and bool(value)
                and value == original["session"].get(key) == state["session"].get(key), "NATIVE_SESSION_BINDING")
    error = execution["execution"].get("error")
    require(error == original["execution"].get("error") == state["execution"].get("error"), "NATIVE_ERROR_BINDING")
    require(is_external_quota(execution), "EXTERNAL_QUOTA_INVALID")


def validate(execution, contract, files):
    profile(execution, contract)
    _validate_sources(execution, files)
    return {"schema_version": ADMISSION, "identity": execution["identity"],
            "policy_sha256": sha(POLICY_PATH.read_bytes()),
            "contract_canonical_sha256": sha(json.dumps(dict(contract), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()),
            "original_failure_preserved": True, "candidate_required": True,
            "tool_history_required_by_rubric": False,
            "files": [{"path": name, "sha256": sha(value), "size": len(value)} for name, value in sorted(files.items())]}


def accountable_profile(execution):
    """Admission by verified native provenance, independent of task allowlists."""
    require(native_candidate(execution), 'EXECUTION_INVALID')
    require(not is_external_quota(execution), "EXTERNAL_QUOTA_REQUIRES_RECOVERY")
    return execution_accountability.FAILED_ADMISSION


def native_candidate(execution):
    error = execution.get('execution', {}).get('error')
    return (execution.get('harness', {}).get('id') == 'astronstudio'
            and execution.get('phase') == 'FAILED'
            and execution.get('execution', {}).get('business_status') == 'candidate_error'
            and isinstance(error, dict) and error.get('code') in {'ASTRONSTUDIO_TURN_ERROR', 'ASTRONSTUDIO_TURN_FAILED'}
            and isinstance(error.get('message'), str) and bool(error['message'])
            and execution.get('prompt', {}).get('send_status') == 'sent'
            and execution.get('session', {}).get('verified') is True
            and execution.get('candidate', {}).get('drift_status') == 'stable')


def read_collected_files(unit_root, record_path, execution):
    """Bind an existing native-error collection without rewriting its record."""
    root = Path(unit_root).resolve()
    record_path = Path(record_path)
    def read(path):
        require(path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink(), 'SOURCE_PATH')
        return path.read_bytes()
    files = {'original-execution-record.json': read(record_path),
             'original-evidence-manifest.json': read(record_path.with_name('evidence-manifest.json'))}
    manifest = json.loads(files['original-evidence-manifest.json'])
    states = [row for row in manifest['artifacts'] if row['path'].endswith('/execution/automation-state.json')]
    require(len(states) == 1, 'ASTRON_STATE_BINDING')
    files['original-state.json'] = read(root / states[0]['path'])
    state = json.loads(files['original-state.json'])
    files['PROMPT.md'] = read(Path(state['prompt']['path']))
    return files


def validate_collected(execution, contract, files):
    accountable_profile(execution)
    original = json.loads(files['original-execution-record.json'])
    state = json.loads(files['original-state.json'])
    manifest = json.loads(files['original-evidence-manifest.json'])
    require(original == execution and original['identity'] == state['identity'] == manifest['identity'], 'SOURCE_IDENTITY')
    states = [row for row in manifest['artifacts'] if row['path'].endswith('/execution/automation-state.json')]
    require(len(states) == 1 and states[0]['sha256'] == sha(files['original-state.json'])
            and states[0]['size'] == len(files['original-state.json']), 'ASTRON_STATE_BINDING')
    require(state.get('phase') == 'FAILED' and state['session'].get('verified') is True
            and state['send'].get('dispatch_attempt_count') == 1
            and state['prompt'].get('send_status') == 'sent'
            and state['prompt'].get('sha256') == execution['prompt']['sha256'] == sha(files['PROMPT.md']), 'TERMINAL_BINDING')
    for key in ('thread_id', 'turn_id', 'session_id', 'cwd'):
        value = execution['session'].get(key)
        require(isinstance(value, str) and bool(value) and value == state['session'].get(key), 'NATIVE_SESSION_BINDING')
    require(state['execution'].get('error') == execution['execution']['error'], 'NATIVE_ERROR_BINDING')
    history = state.get('history') or []
    terminal = history[-1] if history else {}
    native_turn = terminal.get('turn_state') or terminal.get('native_status')
    require(terminal.get('phase') == 'FAILED' and terminal.get('event') == 'NATIVE_TERMINAL_OBSERVED'
            and native_turn in {'error', 'failed'}
            and execution['execution']['error']['code'] == 'ASTRONSTUDIO_TURN_' + native_turn.upper(), 'NATIVE_TERMINAL_OBSERVED')
    # native_status is a periodically refreshed projection. The bound native
    # TURN_ERROR and FAILED record remain authoritative if it still says running.
    return {'schema_version': execution_accountability.FAILED_ADMISSION,
            'identity': execution['identity'], 'profile': execution_accountability.PROFILE,
            'source_kind': 'collected-native-turn-error',
            'source_record_sha256': sha(files['original-execution-record.json']),
            'contract_canonical_sha256': sha(json.dumps(dict(contract), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()),
            'original_failure_preserved': True, 'numeric_decisions_assigned': False,
            'sdk_terminal_required_for_admission': False,
            'native_terminal_observed': True, 'native_turn_state': native_turn,
            'native_session_status_projection': state['session'].get('native_status'),
            'missing_evidence': execution['evidence'].get('missing', []), 'policy': execution_accountability.POLICY,
            'files': [{'path': name, 'sha256': sha(value), 'size': len(value)} for name, value in sorted(files.items())]}


def validate_accountable(execution, contract, files):
    accountable_profile(execution)
    proof, original, state = _validate_sources(execution, files)
    require(proof.get("schema") == ADMISSION, "PROOF_SCHEMA")
    require(original.get("phase") == "FAILED"
            and original["execution"].get("business_status") == "candidate_error"
            and original["session"].get("verified") is True, "ORIGINAL_TERMINAL")
    manifest = json.loads(files["original-evidence-manifest.json"])
    require(manifest.get("identity") == execution["identity"], "EVIDENCE_IDENTITY")
    for key in ("thread_id", "turn_id", "session_id", "cwd"):
        value = execution["session"].get(key)
        require(isinstance(value, str) and bool(value)
                and value == original["session"].get(key) == state["session"].get(key), "NATIVE_SESSION_BINDING")
    require(execution["execution"].get("error") == original["execution"].get("error")
            == state["execution"].get("error"), "NATIVE_ERROR_BINDING")
    return {
        "schema_version": execution_accountability.FAILED_ADMISSION,
        "identity": execution["identity"],
        "profile": execution_accountability.PROFILE,
        "contract_canonical_sha256": sha(json.dumps(dict(contract), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()),
        "original_failure_preserved": True,
        "numeric_decisions_assigned": False,
        "candidate_required": True,
        "sdk_terminal_required_for_admission": False,
        "missing_evidence": execution["evidence"].get("missing", []),
        "policy": execution_accountability.POLICY,
        "files": [{"path": name, "sha256": sha(value), "size": len(value)} for name, value in sorted(files.items())],
    }
