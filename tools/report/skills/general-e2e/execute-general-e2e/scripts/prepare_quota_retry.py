#!/usr/bin/env python3
"""Archive a failed quota attempt and restore only its pristine workspace.

Called under the task/UI locks. No client, Prompt send, rule or Judge is run.
The immutable receipt makes the filesystem transition resumable after a crash.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def tree_sha(entries):
    return sha(json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def create_inside(unit, path):
    current = unit
    for part in path.relative_to(unit).parts:
        current = current / part
        if os.path.lexists(current):
            require(not current.is_symlink() and current.is_dir(), 'RECOVERY_DIRECTORY_SYMLINK')
        else:
            current.mkdir()


def safe(value):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value and '\0' not in value,
            'UNSAFE_PATH')
    require(not value.startswith('/') and all(p not in ('', '.', '..') for p in value.split('/')), 'UNSAFE_PATH')
    return PurePosixPath(value)


def once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        require(not path.is_symlink() and path.read_bytes() == data, 'ARCHIVE_COLLISION: ' + str(path))
        return
    temp = path.with_name(path.name + '.tmp')
    with temp.open('wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp, path)
    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def inventory(root):
    rows = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            data = os.readlink(path).encode('utf-8', errors='surrogateescape')
            kind = 'symlink'
        elif path.is_dir():
            data, kind = b'', 'directory'
        else:
            require(path.is_file(), 'UNSUPPORTED_FILE_TYPE')
            data, kind = None, 'file'
        rows.append(dict(path=relative, kind=kind, mode=format(mode, '04o'),
                         size=path.stat().st_size if kind == 'file' else len(data),
                         sha256=file_sha(path) if kind == 'file' else sha(data)))
    return rows


def check_entries(root, entries):
    require(root.is_dir() and not root.is_symlink(), 'SNAPSHOT_DIRECTORY_TYPE')
    require(inventory(root) == [{k: e[k] for k in ('path', 'kind', 'mode', 'size', 'sha256')}
                                for e in sorted(entries, key=lambda e: e['path'])], 'WORKSPACE_DRIFT')


def control_inventory(root):
    return [entry for entry in inventory(root) if entry['path'] != 'driver.lock']


def quota_state(state):
    error = state.get('execution', {}).get('error', {})
    require(state.get('phase') == 'FAILED' and state.get('execution', {}).get('business_status') == 'candidate_error'
            and error.get('code') in ('ASTRONSTUDIO_TURN_ERROR', 'ASTRONSTUDIO_TURN_FAILED')
            and isinstance(error.get('message'), str)
            and re.fullmatch(r'unexpected status 402(?: Payment Required)?: astron_points_exhausted(?:, url: \S+)?', error['message']),
            'QUOTA_FAILURE_NOT_RETRYABLE')
    require(state.get('prompt', {}).get('send_status') == 'sent'
            and state.get('send', {}).get('dispatch_attempt_count') == 1
            and state.get('session', {}).get('verified') is True
            and all(state['session'].get(key) for key in ('thread_id', 'turn_id', 'session_id', 'cwd')), 'NATIVE_TERMINAL_REQUIRED')


def live_unit(unit):
    flow = unit / '.general-e2e/run-general-e2e-state.json'
    if flow.is_file():
        stages = json.loads(flow.read_bytes()).get('stages', {})
        require(not any(stages.get(stage) == 'COMPLETED' for stage in ('score', 'package')), 'FROZEN_COMPLETED_UNIT')
    for marker in (unit / '.general-e2e/round.json', unit.parent / '.general-e2e/round.json'):
        if marker.is_file():
            require(json.loads(marker.read_bytes()).get('kind') != 'history', 'HISTORICAL_ROUND_READ_ONLY')


def pristine_entries(unit, manifest, task, authorization):
    safe(task['prompt']['path'])
    safe(task['workspace']['path'])
    package = Path(authorization['execution_package']['path']).expanduser().resolve(strict=True)
    require(file_sha(package) == authorization['execution_package']['sha256'], 'EXECUTION_PACKAGE_SHA')
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        names = [i.filename.rstrip('/') for i in infos]
        require(len(names) == len(set(names)), 'DUPLICATE_ZIP_MEMBER')
        for name in names:
            safe(name)
        roots = {n.split('/')[0] for n in names}
        require(len(roots) == 1, 'ZIP_ROOT')
        prefix = roots.pop() + '/'
        members = {i.filename[len(prefix):].rstrip('/'): i for i in infos if i.filename.startswith(prefix)}
        require(json.loads(archive.read(members['manifest.json'])) == manifest, 'EXECUTION_MANIFEST_MISMATCH')
        require(sha(archive.read(members[task['prompt']['path']])) == task['prompt']['sent_sha256'], 'PROMPT_SHA')
        require(sha((unit / task['prompt']['path']).read_bytes()) == task['prompt']['sent_sha256'], 'CURRENT_PROMPT_DRIFT')
        workspace_prefix = task['workspace']['path'] + '/'
        entries = task['workspace']['entries']
        require(len(entries) == len({e['path'] for e in entries}), 'DUPLICATE_WORKSPACE_ENTRY')
        require({n[len(workspace_prefix):] for n in members if n.startswith(workspace_prefix)} == {e['path'] for e in entries},
                'WORKSPACE_SCOPE_MISMATCH')
        links = {e['path'] for e in entries if e['kind'] == 'symlink'}
        output = []
        for entry in entries:
            relative = safe(entry['path'])
            require(not any(parent.as_posix() in links for parent in relative.parents), 'SYMLINK_PARENT')
            info = members[workspace_prefix + entry['path']]
            mode = stat.S_IFMT(info.external_attr >> 16)
            kind = 'directory' if info.is_dir() else 'symlink' if mode == stat.S_IFLNK else 'file'
            require(mode in (0, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFREG), 'ZIP_MEMBER_TYPE')
            data = archive.read(info)
            require(kind == entry['kind'] and len(data) == entry['size'] and sha(data) == entry['sha256'], 'WORKSPACE_MEMBER_SHA')
            require(stat.S_IMODE(info.external_attr >> 16) == int(entry['mode'], 8), 'WORKSPACE_MEMBER_MODE')
            if kind == 'symlink':
                target = data.decode('utf-8')
                require(target == entry['link_target'] and not target.startswith('/') and '\\' not in target and ':' not in target,
                        'SYMLINK_TARGET')
                parts = list(relative.parent.parts)
                for part in target.split('/'):
                    if part == '..':
                        require(bool(parts), 'SYMLINK_ESCAPE')
                        parts.pop()
                    elif part not in ('', '.'):
                        parts.append(part)
            output.append((entry, data))
        return output


def prepare(unit, authorization_path, expected_sha, validate_only=False):
    unit = unit.resolve(strict=True)
    live_unit(unit)
    auth_raw = authorization_path.read_bytes()
    require(sha(auth_raw) == expected_sha, 'AUTHORIZATION_SHA')
    auth = json.loads(auth_raw)
    require(auth.get('schema_version') == 'general-e2e.quota-retry-authorization/v1', 'AUTHORIZATION_SCHEMA')
    require(all(isinstance(auth.get(key), str) and auth[key].strip() for key in
                ('authorized_by', 'authorized_at', 'authorization_reference', 'reason')), 'AUTHORIZATION_AUDIT_REQUIRED')
    task_id = str(safe(auth['task_id']))
    require('/' not in task_id, 'TASK_ID')
    new_id = auth['new_attempt_id']
    require(str(uuid.UUID(new_id)) == new_id and new_id != auth['old_attempt_id'], 'NEW_ATTEMPT_ID')
    manifest_raw = (unit / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    require(sha(manifest_raw) == auth['unit_manifest_sha256'], 'UNIT_MANIFEST_SHA')
    require(manifest['batch_id'] == auth['batch_id'] and manifest['unit_id'] == auth['unit_id'], 'UNIT_IDENTITY')
    task = next(t for t in manifest['tasks'] if t['task_id'] == task_id)
    controls = unit / '.general-e2e/execution' / task_id
    require(controls.resolve() == controls and not (controls / 'automation-state.json').is_symlink()
            and not (controls / 'execution-record.json').is_symlink(), 'CONTROL_PATH')
    old_raw = (controls / 'automation-state.json').read_bytes()
    require(sha(old_raw) == auth['old_state_sha256'], 'OLD_STATE_SHA')
    old = json.loads(old_raw)
    quota_state(old)
    require(all(old['identity'][key] == auth[key] for key in ('task_id', 'batch_id', 'unit_id'))
            and old['identity']['attempt_id'] == auth['old_attempt_id'], 'OLD_ATTEMPT_ID')
    require(old['run_config']['config_digest'] == auth['run_config_digest'], 'RUN_CONFIG_DIGEST')
    record_raw = (controls / 'execution-record.json').read_bytes()
    require(sha(record_raw) == auth['old_record_sha256'], 'OLD_RECORD_SHA')
    require(json.loads(record_raw)['identity'] == old['identity'], 'OLD_RECORD_IDENTITY')
    require(tree_sha(control_inventory(controls)) == auth['old_control_sha256'], 'OLD_CONTROL_SHA')
    require(auth['quota_restored'] is True and auth['retry_authorized'] is True, 'HUMAN_AUTHORIZATION_REQUIRED')
    entries = pristine_entries(unit, manifest, task, auth)
    workspace = unit / task['workspace']['path']
    require(not workspace.is_symlink() and workspace.parent.resolve() == workspace.parent
            and workspace.parent.is_relative_to(unit), 'WORKSPACE_PATH')
    for other in manifest['tasks']:
        if other['task_id'] != task_id:
            peer = unit / str(safe(other['workspace']['path']))
            require(not workspace.is_relative_to(peer) and not peer.is_relative_to(workspace), 'WORKSPACE_OVERLAPS_OTHER_TASK')
    if validate_only:
        require(tree_sha(inventory(workspace)) == auth['old_workspace_sha256'], 'OLD_WORKSPACE_SHA')
        return dict(status='VALIDATED', new_attempt_id=new_id)
    queue = json.loads((unit / '.general-e2e/queues' / str(safe(auth['queue_id'])) / 'queue-state.json').read_bytes())
    require(queue['identity']['queue_digest'] == auth['queue_digest'], 'QUEUE_DIGEST')
    row = next(t for t in queue['tasks'] if t['task_id'] == task_id)
    require(any(t['authorization_sha256'] == expected_sha and t['old_attempt_id'] == auth['old_attempt_id']
                and t['new_attempt_id'] == new_id for t in row.get('quota_recoveries', [])), 'QUEUE_INTENT_REQUIRED')
    recovery = unit / '.general-e2e/quota-recoveries' / task_id / new_id
    create_inside(unit, recovery)
    receipt_path = recovery / 'receipt.json'
    if receipt_path.exists():
        return verify_receipt(unit, authorization_path, expected_sha, True)
    once(recovery / 'authorization.json', auth_raw)
    control_archive = recovery / 'failed-control'
    control_archive.mkdir(exist_ok=True)
    for path in sorted(controls.rglob('*')):
        if path.relative_to(controls).as_posix() == 'driver.lock':
            continue
        relative = path.relative_to(controls)
        target = control_archive / relative
        if path.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            link = os.readlink(path)
            if os.path.lexists(target):
                require(target.is_symlink() and os.readlink(target) == link, 'CONTROL_ARCHIVE_COLLISION')
            else:
                target.symlink_to(link)
        elif path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            once(target, path.read_bytes())
            target.chmod(stat.S_IMODE(path.stat().st_mode))
    for path in sorted(controls.rglob('*'), reverse=True):
        if path.is_dir() and not path.is_symlink():
            (control_archive / path.relative_to(controls)).chmod(stat.S_IMODE(path.stat().st_mode))
    require(tree_sha(inventory(control_archive)) == auth['old_control_sha256'], 'CONTROL_ARCHIVE_SHA')
    stage = recovery / 'pristine-workspace'
    if not stage.exists():
        with tempfile.TemporaryDirectory(prefix='.restore-', dir=recovery) as temporary:
            candidate = Path(temporary) / 'workspace'
            candidate.mkdir()
            for entry, data in sorted(entries, key=lambda e: (e[0]['kind'] != 'directory', e[0]['path'])):
                target = candidate / str(safe(entry['path']))
                target.parent.mkdir(parents=True, exist_ok=True)
                if entry['kind'] == 'directory':
                    target.mkdir(exist_ok=True)
                elif entry['kind'] == 'symlink':
                    target.symlink_to(data.decode('utf-8'))
                else:
                    target.write_bytes(data)
                if entry['kind'] == 'file':
                    target.chmod(int(entry['mode'], 8))
            for entry, _ in sorted(entries, key=lambda e: e[0]['path'], reverse=True):
                if entry['kind'] == 'directory':
                    (candidate / entry['path']).chmod(int(entry['mode'], 8))
            check_entries(candidate, task['workspace']['entries'])
            candidate.rename(stage)
    archived = recovery / 'failed-workspace'
    intent_path = recovery / 'intent.json'
    if not intent_path.exists():
        require(workspace.is_dir() and not archived.exists(), 'WORKSPACE_ARCHIVE_STATE')
        original_entries = inventory(workspace)
        require(tree_sha(original_entries) == auth['old_workspace_sha256'], 'OLD_WORKSPACE_SHA')
        once(intent_path, encoded(dict(authorization_sha256=expected_sha, failed_workspace_entries=original_entries)))
    intent = json.loads(intent_path.read_bytes())
    require(intent['authorization_sha256'] == expected_sha, 'RECOVERY_INTENT_SHA')
    require(tree_sha(intent['failed_workspace_entries']) == auth['old_workspace_sha256'], 'OLD_WORKSPACE_SHA')
    if not archived.exists():
        check_entries(workspace, intent['failed_workspace_entries'])
        workspace.rename(archived)
    check_entries(archived, intent['failed_workspace_entries'])
    if not workspace.exists():
        stage.rename(workspace)
    check_entries(workspace, task['workspace']['entries'])
    archive_manifest = dict(authorization_sha256=expected_sha, old_identity=old['identity'],
                            control_entries=inventory(control_archive), workspace_entries=intent['failed_workspace_entries'])
    once(recovery / 'archive-manifest.json', encoded(archive_manifest))
    receipt = dict(schema_version='general-e2e.quota-retry-receipt/v1', authorization_sha256=expected_sha,
                   prepared_at=datetime.now(timezone.utc).isoformat(),
                   old_attempt_id=auth['old_attempt_id'], new_attempt_id=new_id,
                   old_state_sha256=auth['old_state_sha256'], old_record_sha256=auth['old_record_sha256'],
                   old_state_archive=str((control_archive / 'automation-state.json').relative_to(unit)),
                   archive_manifest=str((recovery / 'archive-manifest.json').relative_to(unit)),
                   archive_manifest_sha256=file_sha(recovery / 'archive-manifest.json'),
                   receipt_path=str(receipt_path), initial_workspace_restored=True)
    once(receipt_path, encoded(receipt))
    return receipt


def verify_receipt(unit, authorization_path, expected_sha, pristine=False):
    unit = unit.resolve(strict=True)
    raw = authorization_path.read_bytes()
    require(sha(raw) == expected_sha, 'AUTHORIZATION_SHA')
    auth = json.loads(raw)
    safe(auth['task_id'])
    safe(auth['new_attempt_id'])
    recovery = unit / '.general-e2e/quota-recoveries' / auth['task_id'] / auth['new_attempt_id']
    require(recovery.resolve() == recovery and not recovery.is_symlink(), 'RECOVERY_DIRECTORY_SYMLINK')
    receipt = json.loads((recovery / 'receipt.json').read_bytes())
    require(receipt['authorization_sha256'] == expected_sha and receipt['old_attempt_id'] == auth['old_attempt_id']
            and receipt['new_attempt_id'] == auth['new_attempt_id'], 'RECOVERY_RECEIPT_IDENTITY')
    require(receipt['old_state_sha256'] == auth['old_state_sha256']
            and receipt['old_record_sha256'] == auth['old_record_sha256']
            and receipt.get('initial_workspace_restored') is True, 'RECOVERY_RECEIPT_BINDING')
    require(receipt['old_state_archive'] == str((recovery / 'failed-control/automation-state.json').relative_to(unit))
            and receipt['receipt_path'] == str(recovery / 'receipt.json'), 'RECOVERY_RECEIPT_PATH')
    require(file_sha(recovery / 'archive-manifest.json') == receipt['archive_manifest_sha256'], 'ARCHIVE_MANIFEST_SHA')
    metadata = json.loads((recovery / 'archive-manifest.json').read_bytes())
    require(metadata['authorization_sha256'] == expected_sha, 'ARCHIVE_AUTHORIZATION_SHA')
    require(tree_sha(metadata['workspace_entries']) == auth['old_workspace_sha256'], 'OLD_WORKSPACE_SHA')
    require(tree_sha(metadata['control_entries']) == auth['old_control_sha256'], 'OLD_CONTROL_SHA')
    check_entries(recovery / 'failed-control', metadata['control_entries'])
    check_entries(recovery / 'failed-workspace', metadata['workspace_entries'])
    require(file_sha(recovery / 'failed-control/automation-state.json') == auth['old_state_sha256'], 'OLD_STATE_SHA')
    old = json.loads((recovery / 'failed-control/automation-state.json').read_bytes())
    require(metadata['old_identity'] == old['identity'], 'ARCHIVE_IDENTITY')
    require(file_sha(recovery / 'failed-control/execution-record.json') == auth['old_record_sha256'], 'OLD_RECORD_SHA')
    if pristine:
        live_unit(unit)
        manifest = json.loads((unit / 'manifest.json').read_bytes())
        task = next(t for t in manifest['tasks'] if t['task_id'] == auth['task_id'])
        check_entries(unit / task['workspace']['path'], task['workspace']['entries'])
    return receipt


def describe(unit, queue_id, task_id, execution_package):
    unit = unit.resolve(strict=True)
    live_unit(unit)
    safe(queue_id)
    safe(task_id)
    queue = json.loads((unit / '.general-e2e/queues' / queue_id / 'queue-state.json').read_bytes())
    row = next(t for t in queue['tasks'] if t['task_id'] == task_id)
    manifest_raw = (unit / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    task = next(t for t in manifest['tasks'] if t['task_id'] == task_id)
    control = unit / '.general-e2e/execution' / task_id
    raw = (control / 'automation-state.json').read_bytes()
    state = json.loads(raw)
    quota_state(state)
    require(state['phase'] == 'FAILED' and state['identity']['attempt_id'] == row['selected_attempt_id'], 'OLD_ATTEMPT_ID')
    auth = dict(schema_version='general-e2e.quota-retry-authorization/v1', authorization_id=str(uuid.uuid4()),
                authorized_by='', authorization_reference='', authorized_at=datetime.now(timezone.utc).isoformat(),
                reason='', quota_restored=False, retry_authorized=False,
                **{k: queue['identity'][k] for k in ('batch_id', 'unit_id', 'queue_id', 'queue_digest')},
                task_id=task_id, old_attempt_id=state['identity']['attempt_id'], new_attempt_id=str(uuid.uuid4()),
                old_state_sha256=sha(raw), old_record_sha256=file_sha(control / 'execution-record.json'),
                old_workspace_sha256=tree_sha(inventory(unit / task['workspace']['path'])),
                old_control_sha256=tree_sha(control_inventory(control)),
                unit_manifest_sha256=sha(manifest_raw), run_config_digest=queue['configuration']['run_config_digest'],
                execution_package=dict(path=str(execution_package.resolve(strict=True)), sha256=file_sha(execution_package)))
    pristine_entries(unit, manifest, task, auth)
    return auth


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit-root', required=True, type=Path)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--authorization-sha256')
    parser.add_argument('--describe-authorization', action='store_true')
    parser.add_argument('--queue-id')
    parser.add_argument('--task-id')
    parser.add_argument('--execution-package', type=Path)
    parser.add_argument('--verify-receipt', action='store_true')
    parser.add_argument('--verify-pristine', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    require(not args.verify_pristine or args.verify_receipt, 'VERIFY_PRISTINE_REQUIRES_VERIFY_RECEIPT')
    require(not (args.validate_only and args.verify_receipt), 'CONFLICTING_READ_ONLY_MODES')
    if args.describe_authorization:
        require(args.queue_id and args.task_id and args.execution_package, 'DESCRIPTION_INPUTS_REQUIRED')
        result = describe(args.unit_root, args.queue_id, args.task_id, args.execution_package)
    else:
        require(args.authorization and args.authorization_sha256, 'AUTHORIZATION_REQUIRED')
        result = (verify_receipt(args.unit_root, args.authorization, args.authorization_sha256, args.verify_pristine)
                  if args.verify_receipt else prepare(args.unit_root, args.authorization, args.authorization_sha256, args.validate_only))
    print(json.dumps(result, ensure_ascii=False))
