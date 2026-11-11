"""Freeze retained native SDK prefixes as original behavior evidence, never GT."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import os
import shutil
import uuid

import execution_accountability

DIRECTORY = 'execution-supplement'
SCHEMA = 'wildclawbench.native-execution-supplement/v1'
INPUT = 'wildclawbench.native-execution-supplement-input/v1'


def require(ok, code):
    if not ok:
        raise ValueError('EXECUTION_SUPPLEMENT_' + code)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def safe_file(root, name):
    require(isinstance(name, str) and name and '\\' not in name, 'PATH')
    parts = name.split('/')
    require(all(p not in {'', '.', '..'} for p in parts), 'PATH')
    path = Path(root)
    for part in parts:
        path /= part
        require(not path.is_symlink(), 'SYMLINK')
    require(path.is_file() and 0 < path.stat().st_size <= 64 * 1024 * 1024, 'FILE')
    return path


def sdk_binding(raw, execution):
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    session = execution['session']; target = session['turn_id']
    meta = [r.get('payload', {}) for r in rows if r.get('type') == 'session_meta']
    require(len(meta) == 1 and meta[0].get('id') == session['session_id']
            and os.path.normpath(meta[0].get('cwd', '')) == os.path.normpath(session['cwd']), 'SESSION')
    current = None; starts = 0; prompts = 0; calls = set(); results = set()
    for row in rows:
        payload = row.get('payload', {})
        if row.get('type') == 'turn_context' or row.get('type') == 'event_msg' and payload.get('type') == 'task_started':
            require(payload.get('turn_id') == target, 'TURN')
            current = target
            if row['type'] == 'event_msg': starts += 1
            elif payload.get('cwd'):
                require(os.path.normpath(payload['cwd']) == os.path.normpath(session['cwd']), 'CWD')
        explicit = (payload.get('internal_chat_message_metadata_passthrough') or {}).get('turn_id')
        require(not explicit or explicit == target and current == target, 'TURN')
        if row.get('type') == 'event_msg' and payload.get('type') == 'user_message':
            require(current == target and isinstance(payload.get('message'), str)
                    and hashlib.sha256(payload['message'].encode()).hexdigest() == execution['prompt']['sha256'], 'PROMPT')
            prompts += 1
        if row.get('type') == 'event_msg' and payload.get('type') in {'task_complete', 'turn_aborted'}:
            raise ValueError('EXECUTION_SUPPLEMENT_NOT_A_PREFIX')
        if row.get('type') == 'response_item' and payload.get('type') in {'function_call', 'custom_tool_call', 'tool_search_call'}:
            require(current == target and prompts == 1, 'CALL_SCOPE')
            call_id = payload.get('call_id') or payload.get('id')
            require(isinstance(call_id, str) and bool(call_id), 'CALL_ID')
            calls.add(call_id)
        if row.get('type') == 'response_item' and payload.get('type') in {'function_call_output', 'custom_tool_call_output', 'tool_search_output'}:
            call_id = payload.get('call_id') or payload.get('id')
            require(current == target and call_id in calls, 'RESULT_SCOPE')
            results.add(call_id)
    require(starts == 1 and prompts == 1, 'SCOPE')
    return {'session_id': session['session_id'], 'turn_id': target, 'cwd': session['cwd'],
            'retained_lines': len(rows), 'observed_unique_calls': len(calls),
            'observed_result_ids': len(results), 'calls_without_retained_result': sorted(calls - results),
            'sdk_terminal_present': False, 'full_turn_coverage_claimed': False}


def validate(root, attempt):
    directory = root / DIRECTORY
    if not os.path.lexists(directory):
        return []
    require(directory.is_dir() and not directory.is_symlink(), 'DIRECTORY')
    require(attempt.get('runtime', {}).get('evidence_accountability_profile') == execution_accountability.PROFILE
            and attempt.get('evidence_admission') in execution_accountability.NATIVE_ADMISSIONS, 'PROFILE')
    manifest_path = safe_file(directory, 'manifest.json'); document = load(manifest_path)
    require(document.get('schema_version') == SCHEMA and document.get('identity') == attempt['identity'], 'IDENTITY')
    require(document.get('execution_record_sha256') == attempt['digests']['execution_record_sha256']
            and document.get('candidate_sha256') == attempt['source']['candidate_sha256'], 'SOURCE')
    require(document.get('candidate_behavior_evidence') is True and document.get('candidate_output') is False
            and document.get('rubric_changed') is False, 'ROLE')
    rows = document.get('files')
    require(isinstance(rows, list) and len(rows) == 1, 'SCOPE')
    execution = load(root / attempt['paths']['execution_record'])
    files = [manifest_path]
    for row in rows:
        require(row.get('kind') == 'native-sdk-prefix', 'KIND')
        path = safe_file(directory, row['path'])
        require(path.stat().st_size == row['size'] and digest(path) == row['sha256'], 'DRIFT')
        require(sdk_binding(path.read_bytes(), execution) == row['binding'], 'BINDING')
        files.append(path)
    actual = set()
    for path in directory.rglob('*'):
        require(not path.is_symlink(), 'SYMLINK')
        if path.is_file(): actual.add(path.relative_to(directory).as_posix())
    require(actual == {p.relative_to(directory).as_posix() for p in files}, 'MEMBERS')
    if (root / 'semantic').exists():
        entries = load(root / 'semantic/evidence-catalog.json')['evidence_index']['entries']
        indexed = {r['reference'].get('path'): r['reference'] for r in entries}
        for path in files:
            ref = indexed.get(path.relative_to(root).as_posix(), {})
            require(ref.get('sha256') == digest(path) and ref.get('type') ==
                    ('rule_audit' if path == manifest_path else 'raw_trace'), 'CATALOG')
    return files


def register(rt, *, attempt_root, source_manifest):
    root = Path(attempt_root).resolve(strict=True)
    rt.verify_attempt(root)
    attempt = load(root / 'attempt-manifest.json')
    require(attempt.get('runtime', {}).get('evidence_accountability_profile') == execution_accountability.PROFILE
            and attempt.get('evidence_admission') in execution_accountability.NATIVE_ADMISSIONS, 'PROFILE')
    require(not (root / 'semantic').exists() and not (root / 'score.json').exists(), 'TOO_LATE')
    source_manifest = Path(source_manifest).absolute()
    require(source_manifest.is_file() and not source_manifest.is_symlink() and source_manifest.stat().st_size <= 1024*1024, 'INPUT')
    incoming = load(source_manifest)
    require(incoming.get('schema_version') == INPUT and incoming.get('execution_record_sha256') == attempt['digests']['execution_record_sha256']
            and incoming.get('candidate_sha256') == attempt['source']['candidate_sha256'], 'INPUT_BINDING')
    execution = load(root / attempt['paths']['execution_record'])
    require(incoming.get('identity') == execution['identity'], 'INPUT_IDENTITY')
    rows = incoming.get('files'); require(isinstance(rows, list) and len(rows) == 1, 'SCOPE')
    row = rows[0]; require(row.get('kind') == 'native-sdk-prefix', 'KIND')
    source = safe_file(source_manifest.parent, row['path'])
    require(source.stat().st_size == row['size'] and digest(source) == row['sha256'], 'INPUT_DRIFT')
    binding = sdk_binding(source.read_bytes(), execution)
    target = root / DIRECTORY; require(not os.path.lexists(target), 'EXISTS')
    staging = root / ('.execution-supplement-' + uuid.uuid4().hex); staging.mkdir()
    published = False
    try:
        shutil.copyfile(source, staging / 'native-sdk-prefix.jsonl')
        document = {'schema_version': SCHEMA, 'identity': attempt['identity'],
                    'execution_record_sha256': attempt['digests']['execution_record_sha256'],
                    'candidate_sha256': attempt['source']['candidate_sha256'], 'input_manifest_sha256': digest(source_manifest),
                    'candidate_behavior_evidence': True, 'candidate_output': False, 'rubric_changed': False,
                    'files': [{'path': 'native-sdk-prefix.jsonl', 'kind': row['kind'], 'sha256': row['sha256'],
                               'size': row['size'], 'binding': binding}]}
        (staging / 'manifest.json').write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        rt._make_read_only(staging); staging.rename(target)
        published = True
        validate(root, attempt)
    except BaseException:
        rt._remove_tree(staging)
        if published: rt._remove_tree(target)
        raise
    return {'status': 'PASS', 'manifest': str(target / 'manifest.json'), 'binding': binding,
            'original_execution_changed': False, 'numeric_decisions_assigned': False}


def copy_frozen(rt, source, destination, manifest):
    source_attempt = load(source / 'attempt-manifest.json')
    if not validate(source, source_attempt): return
    target = destination / DIRECTORY
    shutil.copytree(source / DIRECTORY, target)
    for path in [target, *target.rglob('*')]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    document = load(target / 'manifest.json')
    document['copied_from_manifest_sha256'] = digest(source / DIRECTORY / 'manifest.json')
    document['identity'] = deepcopy(manifest['identity'])
    (target / 'manifest.json').write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    rt._make_read_only(target)
    validate(destination, manifest)
