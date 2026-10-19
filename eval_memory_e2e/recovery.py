"""Recover only a dead controller's shared UI lock; never resend or cancel a turn."""
import os
import re
import socket
import subprocess
from pathlib import Path

from . import HARNESS_PORTS
from .batch import load_batch, memory_ui_lock_path
from .io import append, events, publish, read_json, require, sha, timestamp, lock, encoded, decode, archive

from .machine import machine_paths

DEBUG_ROOT = machine_paths()['debug']


def recover_qwen_step_lock(root, episode_id, operation, expected_owner_id, probe):
    root = Path(root).absolute()
    require(root.is_relative_to(DEBUG_ROOT) and root.resolve() == root, 'RECOVERY_ROOT', str(root))
    require(re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', expected_owner_id or '') is not None,
            'RECOVERY_OWNER', 'Expected a canonical owner UUID')
    require(re.fullmatch(r'op-[a-f0-9]{64}', operation or '') is not None, 'RECOVERY_OPERATION', 'Expected a frozen operation ID')
    with lock(root):
        manifest = load_batch(root, episode_id=episode_id)
        require(any(e['id'] == episode_id and e['harness'] == 'QwenWork' for e in manifest['episodes']),
                'RECOVERY_SCOPE', 'Only the QwenWork Memory step lock')
        output = root / 'runtime-recovery' / ('qwen-step-' + expected_owner_id + '.json')
        output.parent.mkdir(exist_ok=True)
        require(not output.exists(), 'RECOVERY_ALREADY_ARCHIVED', str(output))
        script = Path(__file__).parent / 'native/recover-qwen-lock.mjs'
        source_artifact = archive(root, script)
        request = {'root': str(root), 'episode_id': episode_id, 'operation_id': operation,
                   'expected_owner_id': expected_owner_id, 'probe': str(Path(probe).absolute()), 'output': str(output)}
        result = subprocess.run(['node', str(script)], input=encoded(request), capture_output=True, timeout=60)
        publish(output.with_suffix('.stdout'), result.stdout); publish(output.with_suffix('.stderr'), result.stderr)
        require(result.returncode == 0, 'RECOVERY_QWEN_REJECTED', 'Controlled recovery rejected; private diagnostics retained')
        receipt = decode(result.stdout)
        append(root, 'QWEN_STEP_LOCK_RECOVERED', episode_id, {'receipt': archive(root, output),
               'recovery_source_sha256': source_artifact['sha256'], 'recovery_source_artifact': source_artifact,
               'prompt_resent': False})
        return receipt


def recover_ui_lock(root, expected_owner_id):
    root = Path(root).absolute()
    require(root.is_relative_to(DEBUG_ROOT) and root.resolve() == root, 'RECOVERY_ROOT', str(root))
    manifest = load_batch(root)
    require(set(manifest['harnesses']) <= set(HARNESS_PORTS), 'RECOVERY_SCOPE', 'Codex is not an evaluation target')
    path = memory_ui_lock_path(root, manifest['profiles'])
    require(not path.is_symlink() and path.is_file(), 'RECOVERY_LOCK_PATH', str(path))
    original = path.read_bytes()
    owner = read_json(path)
    require(re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', expected_owner_id or '') is not None,
            'RECOVERY_OWNER', 'Expected a canonical owner UUID')
    require(owner.get('id') == expected_owner_id and owner.get('host') == socket.gethostname(),
            'RECOVERY_OWNER', 'Expected exact same-host owner identity')
    pid = owner.get('pid')
    require(type(pid) is int and pid > 1, 'RECOVERY_PID', str(pid))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    else:
        require(False, 'RECOVERY_OWNER_ALIVE', str(pid))
    intents = [e['payload']['request'] for e in events(root) if e['kind'] == 'INTENT'
               and e['payload'].get('operation_id') == owner.get('operation_id')]
    require(len(intents) == 1 and intents[0]['harness'] in HARNESS_PORTS,
            'RECOVERY_OPERATION', 'Lock must belong to an existing allowed dispatch intent')
    archive = root / 'runtime-recovery' / ('ui-lock-' + expected_owner_id + '.json')
    require(not archive.exists(), 'RECOVERY_ALREADY_ARCHIVED', str(archive))
    archive.parent.mkdir(exist_ok=True)
    require(archive.parent.resolve() == archive.parent, 'RECOVERY_ARCHIVE_PATH', str(archive.parent))
    require(path.read_bytes() == original, 'RECOVERY_LOCK_DRIFT', str(path))
    path.rename(archive)
    require(archive.read_bytes() == original, 'RECOVERY_LOCK_DRIFT', str(archive))
    receipt = {'status': 'RECOVERED', 'created_at': timestamp(), 'owner': owner,
               'lock_sha256': sha(original), 'archive': str(archive),
               'prompt_send_attempted': False, 'native_turn_cancelled': False, 'journal_rewritten': False}
    publish(archive.with_suffix('.receipt.json'), receipt)
    append(root, 'UI_LOCK_RECOVERED', intents[0]['episode_id'], receipt)
    return receipt
