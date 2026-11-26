"""Keep real guest links out of WGUI's regular-file-only transport."""
import json
import hashlib
from pathlib import Path, PureWindowsPath
import shlex

from .common import E2EError, atomic_json, digest, file_sha256, identifier
from . import workspace_links


def specs(driver):
    public = driver.batch / driver.task['input_root'] / 'execution/workspace'
    return [{'path': path.relative_to(public).as_posix(), 'target': str(path.readlink()),
             'target_is_directory': path.is_dir()}
            for path in sorted(public.rglob('*')) if path.is_symlink()]


def _run(driver, sid, action, powershell):
    from .windows_preprocess import PYTHON
    from .backend import WGUI, GUEST_WORKSPACE
    row = driver.store.get(driver.key)
    attempt = identifier(row['attempt_id'], 'attempt_id')
    linux = '/tmp/wcb-workspace-links-' + attempt
    guest = PureWindowsPath(r'C:\ProgramData\WGUI\workspace-links') / attempt
    identity = {'attempt_id': attempt, 'task_id': driver.task['task_id'], 'unit_id': row['unit_id']}
    spec = {'identity': identity, 'links': specs(driver)}
    worker = Path(workspace_links.__file__).read_bytes()
    payload = json.dumps(spec, ensure_ascii=False, sort_keys=True).encode('utf-8')
    driver.client.checked(sid, 'mkdir -p ' + shlex.quote(linux))
    driver.client.upload(sid, linux + '/worker.py', worker)
    driver.client.upload(sid, linux + '/spec.json', payload)
    driver._checked_job('workspace-link-worker-' + digest([worker.hex(), spec])[:12],
        WGUI + ' workspace upload --source ' + shlex.quote(linux) + ' --guest ' + shlex.quote(str(guest)), timeout=120)
    receipt = guest / (action + '.bin')
    destination = guest / 'snapshot'
    root = getattr(driver, 'guest_workspace', GUEST_WORKSPACE)
    script = ("$ErrorActionPreference='Stop';$python=" + PYTHON + ";& $python -X utf8 '" + str(guest / 'worker.py')
              + "' " + action + " --root '" + root + "' --spec '" + str(guest / 'spec.json')
              + "' --receipt '" + str(receipt) + "'"
              + (" --destination '" + str(destination) + "'" if action == 'snapshot' else '')
              + ";if($LASTEXITCODE -ne 0){throw 'WORKSPACE_LINK_WORKER_FAILED'}")
    driver.client.windows_execute(sid, powershell(script), timeout=180)
    value = json.loads(driver.client.windows_download(sid, str(receipt)))
    if value.get('schema') != workspace_links.SCHEMA or value.get('identity') != identity:
        raise E2EError('WORKSPACE_LINK_RECEIPT_IDENTITY_MISMATCH')
    value['transport'] = {'worker_sha256': hashlib.sha256(worker).hexdigest(),
                          'spec_sha256': hashlib.sha256(payload).hexdigest()}
    atomic_json(driver.staging / ('metadata/workspace-links-' + action + '.json'), value)
    return value, str(destination)


def install(driver, sid, powershell):
    if not specs(driver):
        return
    _run(driver, sid, 'install', powershell)


def prepare_collection(driver, sid, powershell):
    if not specs(driver):
        return None
    receipt, destination = _run(driver, sid, 'snapshot', powershell)
    request = {'schema_version': 2, 'workspace': {'guest': destination}}
    driver.client.upload(sid, '/run/wgui/collect-request.json', json.dumps(request).encode('utf-8'))
    atomic_json(driver.staging / 'metadata/collect-request.json', request)
    return receipt


def restore_collection(driver, collected):
    path = driver.staging / 'metadata/workspace-links-snapshot.json'
    if not path.is_file():
        return
    receipt = json.loads(path.read_text(encoding='utf-8'))
    root = collected / 'workspace'
    observed = workspace_links.entries(root)
    expected = receipt['entries']
    # Resumes may already have restored links. Never invent a missing link from
    # the original task: only the post-execution guest snapshot is authoritative.
    if observed == expected:
        return
    expected_by_path = {row['path']: row for row in expected}
    observed_by_path = {row['path']: row for row in observed}
    if (any(expected_by_path.get(row['path']) != row for row in observed)
            or any(row['kind'] == 'file' and row['path'] not in observed_by_path for row in expected)):
        raise E2EError('WORKSPACE_LINK_COLLECTED_FILES_DRIFT')
    directories = [root, *(p for p in root.rglob('*') if p.is_dir() and not p.is_symlink())]
    modes = [(p, p.stat().st_mode) for p in directories]
    try:
        for directory, mode in modes:
            directory.chmod(mode | 0o200)
        # WGUI's file transport omits empty directories. Recreate only those
        # observed in the quiescent guest snapshot, before restoring its links.
        for row in expected:
            if row['kind'] == 'directory':
                root.joinpath(*workspace_links.relative(row['path']).parts).mkdir(parents=True, exist_ok=True)
        workspace_links.install(root, [row for row in expected if row['kind'] == 'symlink'])
    finally:
        for directory, mode in reversed(modes):
            directory.chmod(mode)
    from .artifacts import _protect
    _protect(root, allow_symlinks=True)
    if workspace_links.entries(root) != expected:
        raise E2EError('WORKSPACE_LINK_RESTORATION_DRIFT')
    atomic_json(driver.staging / 'metadata/workspace-links-transport.json', {
        'schema': workspace_links.SCHEMA, 'identity': receipt['identity'],
        'receipt_sha256': file_sha256(path), 'collect_manifest_sha256': file_sha256(collected / 'manifest.json'),
        'links': [row for row in expected if row['kind'] == 'symlink'], 'status': 'verified'})
