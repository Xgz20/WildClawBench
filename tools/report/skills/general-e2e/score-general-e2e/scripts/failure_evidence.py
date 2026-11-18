"""Verify native terminal failures for scoring admission or a quota stop.

This admission preserves FAILED and the source failure; it never manufactures
a successful execution or decides a score. Reviewed candidate failures use the
ordinary grader/Judge; verified external quota failures require human recovery.
"""
import hashlib
import base64
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
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
    codes = {'ASTRONSTUDIO_TURN_ERROR', 'ASTRONSTUDIO_TURN_FAILED'} if harness == 'astronstudio' else {'LOOMY_NATIVE_HTTP_ERROR', 'LOOMY_NATIVE_OUTPUT_LENGTH_LIMIT'} if harness == 'loomy' else set()
    if native_start_candidate(execution):
        return True
    return (bool(codes)
            and execution.get('phase') == 'FAILED'
            and execution.get('execution', {}).get('business_status') == 'candidate_error'
            and isinstance(error, dict) and error.get('code') in codes
            and isinstance(error.get('message'), str) and bool(error['message'])
            and execution.get('prompt', {}).get('send_status') == 'sent'
            and execution.get('session', {}).get('verified') is True
            and execution.get('candidate', {}).get('drift_status') == 'stable')


def native_start_candidate(execution):
    """Recognition only; admission still replays every frozen native source."""
    error=execution.get('execution', {}).get('error')
    return (execution.get('harness', {}).get('id') == 'astronstudio'
            and execution.get('phase') == 'FAILED'
            and execution.get('execution', {}).get('business_status') == 'candidate_error'
            and isinstance(error,dict) and error.get('code') == 'ASTRONSTUDIO_NATIVE_START_REJECTED'
            and execution.get('prompt', {}).get('send_status') == 'sent'
            and execution.get('session', {}).get('verified') is False
            and execution['session'].get('turn_id') is None
            and execution['session'].get('session_id') is None
            and isinstance(execution.get('evidence', {}).get('native_start_rejection'), dict)
            and execution.get('candidate', {}).get('drift_status') == 'stable')


def _validate_loomy_sources(execution, state, files):
    """Replay primary-provider failure from retained source bytes, never task IDs."""
    if execution['execution']['error']['code'] == 'LOOMY_NATIVE_OUTPUT_LENGTH_LIMIT':
        return _validate_loomy_length_sources(execution, state, files)
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


def _validate_loomy_length_sources(execution, state, files):
    """The native completed length finish proves failure, never an assigned zero."""
    names = ['native-length-failure.json', 'native-scoped-snapshot.json', 'dispatch-journal.json', 'frozen-run-config.json']
    proof, native, journal, config = [json.loads(files[name]) for name in names]
    manifest = json.loads(files['original-evidence-manifest.json'])
    require(manifest['identity'] == execution['identity'], 'LOOMY_LENGTH_IDENTITY')
    for name in names:
        rows = [row for row in manifest['artifacts'] if row['path'].endswith('/trace/raw/' + name)]
        require(len(rows) == 1 and rows[0]['sha256'] == sha(files[name]) and rows[0]['size'] == len(files[name]), 'LOOMY_LENGTH_SOURCE_SHA')
    binding = journal.get('native_length_failure', {})
    require(binding.get('sha256') == sha(files[names[0]]) and binding.get('size') == len(files[names[0]])
            and state['extensions']['loomy']['native_length_failure'] == binding, 'LOOMY_LENGTH_PROOF_SHA')
    require(proof.get('profile') == 'loomy-native-output-length-failure/v1'
            and proof['identity'] == journal['identity'] == execution['identity']
            and journal['phase'] == 'FAILED' and journal['dispatch_attempt_count'] == 1 and journal['send_status'] == 'sent'
            and journal['input_locks']['config'] == sha(files[names[3]])
            and proof['prompt_sha256'] == execution['prompt']['sha256'] == sha(files['PROMPT.md']), 'LOOMY_LENGTH_BINDING')
    require(native.get('profile') == 'loomy-opencode-sqlite/v1'
            and native['snapshot']['method'] == 'readonly-source-sqlite-online-backup' and native['snapshot']['quick_check'] == 'ok', 'LOOMY_LENGTH_SOURCE')
    sid = execution['session']['session_id']; workspace = execution['session']['cwd']
    roots = [r for r in native['sessions'] if r['id'] == sid and r['parent_id'] is None and r['directory'] == workspace]
    scope = {sid}
    while True:
        expanded = scope | {r['id'] for r in native['sessions'] if r['parent_id'] in scope}
        if expanded == scope: break
        scope = expanded
    require(len(roots) == 1 and {r['id'] for r in native['sessions']} == scope
            and all(r['directory'] == workspace for r in native['sessions']), 'LOOMY_LENGTH_SCOPE')
    messages = [(r, json.loads(r['data'])) for r in native['messages']]
    parts = [(r, json.loads(r['data'])) for r in native['parts']]
    message_ids = {r['id']: r for r, _ in messages}
    require(len(message_ids) == len(messages) and len({r['id'] for r, _ in parts}) == len(parts)
            and all(r['session_id'] in scope for r, _ in messages)
            and all(r['session_id'] in scope and message_ids.get(r['message_id'], {}).get('session_id') == r['session_id'] for r, _ in parts), 'LOOMY_LENGTH_ROWS')
    users = [(r, d) for r, d in messages if r['session_id'] == sid and d.get('role') == 'user']
    assistants = [(r, d) for r, d in messages if r['session_id'] == sid and d.get('role') == 'assistant']
    require(len(users) == 1 and bool(assistants) and users[0][1].get('model') == {'providerID':'imodel','modelID':'spark-x2.6','variant':'high'}
            and sum(d.get('text') == files['PROMPT.md'].decode('utf-8') for r, d in parts if r['message_id'] == users[0][0]['id']) == 1
            and all(d.get('providerID') == 'imodel' and d.get('modelID') == 'spark-x2.6' and d.get('variant') == 'high' for _, d in assistants), 'LOOMY_LENGTH_PROMPT_MODEL')
    texts = [d.get('text') for r, d in parts if r['message_id'] == users[0][0]['id'] and d.get('type') == 'text' and not d.get('synthetic') and not d.get('ignored')]
    memory_prefix = '## 可用记忆条目\n\n'
    memory_empty = memory_prefix + '当前没有可用记忆条目。不要调用 Read 读取记忆文件，也不要猜测任何文件路径；直接基于本轮对话自然回复。'
    memory_suffix = '\n\n只在条目与当前请求明确相关时读取对应文件。不要向用户提及这些条目、路径或读取过程。'
    require(texts and texts[-1] == files['PROMPT.md'].decode('utf-8') and (len(texts) == 1 or len(texts) == 2
            and isinstance(texts[0],str) and (texts[0] == memory_empty or texts[0].startswith(memory_prefix)
                and texts[0].endswith(memory_suffix) and bool(texts[0][len(memory_prefix):-len(memory_suffix)].strip()))), 'LOOMY_LENGTH_USER_TEXT_SCOPE')
    head, final = assistants[-1]; created = final.get('time', {}).get('created'); completed = final.get('time', {}).get('completed')
    require(final.get('finish') == 'length' and not final.get('error') and type(created) is int and type(completed) is int and completed >= created
            and head['id'] == proof['final_message_id'] == state['extensions']['loomy']['final_message_id'] == journal['final_message_id']
            and proof['session_id'] == sid, 'LOOMY_LENGTH_FINAL')
    require(all(d.get('tool') != 'question' and d.get('state', {}).get('status') in {'completed','error'} for _, d in parts if d.get('type') == 'tool'), 'LOOMY_LENGTH_TOOLS')
    for child in scope:
        tails = [d for r, d in messages if r['session_id'] == child and d.get('role') == 'assistant']
        require(bool(tails) and type(tails[-1].get('time', {}).get('completed')) is int
                and (tails[-1].get('finish') in {'stop','length'} or bool(tails[-1].get('error'))), 'LOOMY_LENGTH_CHILD')
    runtime = proof['runtime']
    endpoint = urlsplit(proof['runtime_status_scope']['endpoint']); base = urlsplit(runtime['endpoint'])
    require(base.scheme == endpoint.scheme == 'http' and base.hostname == endpoint.hostname == '127.0.0.1'
            and base.port == endpoint.port and not base.username and not endpoint.username
            and base.path in {'','/'} and endpoint.path == '/session/status' and not endpoint.fragment
            and parse_qs(endpoint.query) == {'directory':[workspace]}, 'LOOMY_LENGTH_STATUS_SCOPE')
    require(runtime == state['extensions']['loomy']['runtime'] == journal['runtime_binding'] and runtime['database_owned'] is True
            and runtime['health_version'] == '1.14.22' and runtime['ppid'] == config['process']['pid']
            and all(runtime[k] == config['runtime'][k] for k in ['executable','binary_sha256','database'])
            and all(proof['runtime_status'].get(child, {}).get('type','idle') == 'idle' for child in scope)
            and proof['runtime_status_scope']['directory'] == workspace
            and datetime.fromisoformat(proof['observed_at'].replace('Z','+00:00')).timestamp()*1000 >= completed, 'LOOMY_LENGTH_IDLE')
    expected = {'code':'LOOMY_NATIVE_OUTPUT_LENGTH_LIMIT','message':'Native primary model ended with finish=length'}
    require(execution['execution']['error'] == state['execution']['error'] == journal['native_error'] == expected, 'LOOMY_LENGTH_ERROR')


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
    if native_start_candidate(execution):
        binding=execution['evidence']['native_start_rejection']
        proof_path=root/binding['path']
        files['start-rejection/proof.json']=read(proof_path)
        proof=json.loads(files['start-rejection/proof.json'])
        require(sha(files['start-rejection/proof.json'])==binding['sha256'], 'START_PROOF_SHA')
        require({r['path'] for r in proof['files']}=={'original-state.json','original-execution-record.json','native-snapshot.json'}
                and len(proof['files'])==3, 'START_PROOF_SOURCES')
        for name in ['proof.json',*[r['path'] for r in proof['files']]]:
            path=proof_path.with_name(name)
            value=read(path)
            artifacts=[r for r in manifest['artifacts'] if r['path']==path.relative_to(root).as_posix()]
            require(len(artifacts)==1 and artifacts[0]['sha256']==sha(value)
                    and artifacts[0]['size']==len(value), 'START_MANIFEST_BINDING')
            files['start-rejection/'+name]=value
    return files


def _validate_start_rejection(execution, state, files):
    require(native_start_candidate(execution), 'START_EXECUTION_INVALID')
    require(state['session'].get('verified') is False
            and state['execution'].get('error')==execution['execution']['error'], 'START_TERMINAL_BINDING')
    require(all(state['session'].get(k)==execution['session'].get(k)
                for k in ('thread_id','turn_id','session_id','cwd')), 'START_SESSION_BINDING')
    binding=execution['evidence']['native_start_rejection']
    require(isinstance(binding.get('path'),str), 'START_PATH')
    relative=Path(binding['path'])
    require(not relative.is_absolute() and '..' not in relative.parts
            and '\\' not in binding['path'] and relative.name=='proof.json', 'START_PATH')
    node=shutil.which('node');require(node is not None,'START_NODE_REQUIRED')
    with tempfile.TemporaryDirectory(prefix='general-start-rejection-replay-') as directory:
        root=Path(directory);proof_path=root/relative;proof_path.parent.mkdir(parents=True)
        for name in ('proof.json','original-state.json','original-execution-record.json','native-snapshot.json'):
            proof_path.with_name(name).write_bytes(files['start-rejection/'+name])
        state_path=root/'state.json';state_path.write_bytes(files['original-state.json'])
        record_path=root/'record.json';record_path.write_bytes(files['original-execution-record.json'])
        try:
            result=subprocess.run([node,str(Path(__file__).with_name('verify_start_rejection.mjs')),
                str(root),str(state_path),str(record_path)],capture_output=True,text=True,timeout=30,check=True)
            replay=json.loads(result.stdout)
        except (subprocess.SubprocessError,json.JSONDecodeError) as exc:
            raise ValueError('FAILED_OUTPUT_ADMISSION_START_REPLAY_REJECTED') from exc
    require(replay.get('status')=='PASS' and replay.get('identity')==execution['identity']
            and replay.get('prompt_sha256')==execution['prompt']['sha256']
            and replay.get('native_message_accepted') is True
            and replay.get('native_turn_id') is None and replay.get('native_sdk_session_id') is None
            and replay.get('error')==execution['execution']['error']['message'], 'START_REPLAY_BINDING')
    return replay


def validate_collected(execution, contract, files):
    accountable_profile(execution)
    original = json.loads(files['original-execution-record.json'])
    state = json.loads(files['original-state.json'])
    manifest = json.loads(files['original-evidence-manifest.json'])
    require(original == execution and original['identity'] == state['identity'] == manifest['identity'], 'SOURCE_IDENTITY')
    states = [row for row in manifest['artifacts'] if row['path'].endswith('/execution/automation-state.json')]
    require(len(states) == 1 and states[0]['sha256'] == sha(files['original-state.json'])
            and states[0]['size'] == len(files['original-state.json']), 'ASTRON_STATE_BINDING')
    require(state.get('phase') == 'FAILED'
            and state['send'].get('dispatch_attempt_count') == 1
            and state['prompt'].get('send_status') == 'sent'
            and state['prompt'].get('sha256') == execution['prompt']['sha256'] == sha(files['PROMPT.md']), 'TERMINAL_BINDING')
    if native_start_candidate(execution):
        replay=_validate_start_rejection(execution,state,files)
        return {'schema_version':execution_accountability.FAILED_ADMISSION,
            'identity':execution['identity'],'profile':execution_accountability.PROFILE,
            'source_kind':'collected-native-start-rejection','native_rejection_profile':replay['profile'],
            'source_record_sha256':sha(files['original-execution-record.json']),
            'contract_canonical_sha256':sha(json.dumps(dict(contract),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()),
            'original_failure_preserved':True,'numeric_decisions_assigned':False,
            'sdk_terminal_required_for_admission':False,'native_message_accepted':True,'native_model_turn_started':False,
            'missing_evidence':execution['evidence'].get('missing',[]),'policy':execution_accountability.POLICY,
            'files':[{'path':name,'sha256':sha(value),'size':len(value)} for name,value in sorted(files.items())]}
    require(state['session'].get('verified') is True, 'TERMINAL_BINDING')
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
