"""Verify native terminal failures for scoring admission or a quota stop.

This admission preserves FAILED and the source failure; it never manufactures
a successful execution or decides a score. Reviewed candidate failures use the
ordinary grader/Judge; verified external quota failures require human recovery.
"""
import hashlib
import base64
import json
import re
from datetime import datetime
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
    require(execution.get("harness", {}).get("id") in {"astronstudio", "loomy"}, "NATIVE_FAILURE_PROFILE_UNSUPPORTED")
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
    elif execution['harness']['id'] == 'loomy':
        manifest = json.loads(files['original-evidence-manifest.json'])
        states = [row for row in manifest['artifacts'] if row['path'].endswith('/execution/automation-state.json')]
        require(len(states) == 1 and states[0]['sha256'] == sha(files['original-state.json'])
                and states[0]['size'] == len(files['original-state.json']), 'LOOMY_STATE_BINDING')
        _validate_loomy_sources(execution, state, files)
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
    harness = execution.get('harness', {}).get('id')
    codes = {'ASTRONSTUDIO_TURN_ERROR', 'ASTRONSTUDIO_TURN_FAILED'} if harness == 'astronstudio' else {'LOOMY_NATIVE_HTTP_ERROR'} if harness == 'loomy' else set()
    return (bool(codes)
            and execution.get('phase') == 'FAILED'
            and execution.get('execution', {}).get('business_status') == 'candidate_error'
            and isinstance(error, dict) and error.get('code') in codes
            and isinstance(error.get('message'), str) and bool(error['message'])
            and execution.get('prompt', {}).get('send_status') == 'sent'
            and execution.get('session', {}).get('verified') is True
            and execution.get('candidate', {}).get('drift_status') == 'stable')


def _validate_loomy_sources(execution, state, files):
    """Replay primary-provider failure from retained source bytes, never task IDs."""
    proof_bytes = files['native-http-failure.json']
    proof = json.loads(proof_bytes)
    native = json.loads(files['native-scoped-snapshot.json'])
    journal = json.loads(files['dispatch-journal.json'])
    config = json.loads(files['frozen-run-config.json'])
    manifest = json.loads(files['original-evidence-manifest.json'])
    require(manifest['identity'] == execution['identity'], 'LOOMY_EVIDENCE_IDENTITY')
    for name in ('native-http-failure.json', 'native-scoped-snapshot.json', 'dispatch-journal.json', 'frozen-run-config.json'):
        rows = [row for row in manifest['artifacts'] if row['path'].endswith('/trace/raw/' + name)]
        require(len(rows) == 1 and rows[0]['sha256'] == sha(files[name]) and rows[0]['size'] == len(files[name]), 'LOOMY_TRACE_BINDING')
    binding = journal.get('native_http_failure', {})
    require(binding.get('sha256') == sha(proof_bytes) and binding.get('size') == len(proof_bytes)
            and state['extensions']['loomy']['native_http_failure'] == binding, 'LOOMY_PROOF_SHA')
    require(proof.get('profile') == 'loomy-native-primary-http-failure/v1'
            and proof['identity'] == execution['identity'] == journal['identity']
            and journal['phase'] == 'FAILED' and journal['dispatch_attempt_count'] == 1
            and journal['send_status'] == 'sent'
            and journal['input_locks']['config'] == sha(files['frozen-run-config.json'])
            and proof['prompt_sha256'] == execution['prompt']['sha256'] == sha(files['PROMPT.md']), 'LOOMY_IDENTITY')
    require(native['profile'] == 'loomy-opencode-sqlite/v1'
            and native['snapshot']['method'] == 'readonly-source-sqlite-online-backup'
            and native['snapshot']['quick_check'] == 'ok', 'LOOMY_SOURCE')
    sid = execution['session']['session_id']
    root = [row for row in native['sessions'] if row['id'] == sid and row['parent_id'] is None]
    require(len(root) == 1 and root[0]['directory'] == execution['session']['cwd']
            and all(row['directory'] == root[0]['directory'] for row in native['sessions'])
            and proof['session_id'] == sid, 'LOOMY_SESSION')
    messages = [(row, json.loads(row['data'])) for row in native['messages']]
    parts = [(row, json.loads(row['data'])) for row in native['parts']]
    users = [(row, data) for row, data in messages if row['session_id'] == sid and data.get('role') == 'user']
    assistants = [(row, data) for row, data in messages if row['session_id'] == sid and data.get('role') == 'assistant']
    require(len(users) == 1 and bool(assistants), 'LOOMY_MESSAGE_SCOPE')
    prompt = files['PROMPT.md'].decode('utf-8')
    require(sum(data.get('text') == prompt for row, data in parts if row['message_id'] == users[0][0]['id']) == 1
            and users[0][1].get('model') == {'providerID': 'imodel', 'modelID': 'spark-x2.6', 'variant': 'high'}
            and all(data.get('providerID') == 'imodel' and data.get('modelID') == 'spark-x2.6' and data.get('variant') == 'high'
                    for _, data in assistants), 'LOOMY_PROMPT_MODEL')
    head, data = assistants[-1]
    start, finish = data.get('time', {}).get('created'), data.get('time', {}).get('completed')
    require(type(start) is int and type(finish) is int and finish >= start
            and not data.get('finish') and not data.get('error')
            and head['id'] == proof['final_message_id'] == state['extensions']['loomy']['final_message_id']
            and not any(row['message_id'] == head['id'] for row, _ in parts)
            and all(part.get('state', {}).get('status') in {'completed', 'error'} for _, part in parts if part.get('type') == 'tool'), 'LOOMY_EMPTY_COMPLETED_HEAD')
    require(datetime.fromisoformat(proof['observed_at'].replace('Z', '+00:00')).timestamp() * 1000 >= finish,
            'LOOMY_FAILURE_OBSERVATION')
    before, after = proof['original_runtime'], proof['observed_runtime']
    require(all(before[key] == after[key] for key in ('ppid', 'executable', 'binary_sha256', 'database', 'health_version'))
            and before['database_owned'] is True and after['database_owned'] is True
            and after['health_version'] == '1.14.22' and after['ppid'] == config['process']['pid']
            and state['extensions']['loomy']['runtime'] == after
            and all(proof['runtime_status'].get(row['id'], {}).get('type', 'idle') == 'idle' for row in native['sessions']), 'LOOMY_RUNTIME')
    pattern = re.compile(r'^ERROR (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) .*?service=llm providerID=imodel modelID=spark-x2\.6 session\.id=(ses_[A-Za-z0-9]+) small=false agent=loomy mode=primary error=')
    def text_values(content):
        if isinstance(content, str): return [content]
        if isinstance(content, list): return [text for item in content for text in text_values(item)]
        if isinstance(content, dict) and content.get('type') == 'text': return text_values(content.get('text'))
        return []
    errors = []
    require(bool(proof.get('source_lines')), 'LOOMY_LOG_MISSING')
    for row in proof['source_lines']:
        raw = base64.b64decode(row['bytes_base64'], validate=True)
        require(sha(raw) == row['sha256'] and len(raw) == row['size'] and type(row['line_number']) is int and row['line_number'] > 0,
                'LOOMY_LOG_SHA')
        line = raw.decode('utf-8'); match = pattern.match(line)
        require(match is not None and match[2] == sid, 'LOOMY_LOG_SESSION')
        error = json.JSONDecoder().raw_decode(line[match.end():])[0]['error']
        timestamp = datetime.fromisoformat(match[1] + '+00:00').timestamp() * 1000
        require(start - 1000 <= timestamp <= finish + 1000 and error.get('name') == 'AI_APICallError'
                and error.get('url') == 'https://loomyad.xunfei.cn/api/v1/chat/completions'
                and type(error.get('statusCode')) is int and 500 <= error['statusCode'] <= 599
                and error.get('requestBodyValues', {}).get('model') == 'spark-x2.6'
                and any(message.get('role') == 'user' and any(prompt in text for text in text_values(message.get('content')))
                        for message in error['requestBodyValues']['messages']), 'LOOMY_LOG_REQUEST')
        errors.append(error)
    expected = {'code': 'LOOMY_NATIVE_HTTP_ERROR', 'message': f"Native primary model HTTP {errors[-1]['statusCode']} after provider retries"}
    require(execution['execution']['error'] == state['execution']['error'] == journal['native_error'] == expected,
            'LOOMY_NATIVE_ERROR')


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
