"""Owned, recoverable configuration lease for AStudio; never touches Codex home."""
import json
import os
import subprocess
import tomllib
from pathlib import Path

from .configuration import ASTUDIO_MEMORY_FIELDS, _replace_owned, set_toml_fields
from .io import publish, read_json, require, sha, timestamp

HOMES = (Path('/Users/gzx/.acode'), Path('/Users/gzx/.acode/acode/acode-home-overlay'))
KERNEL = '/Applications/AStudio.app/Contents/Resources/bin/acode-darwin-x64'
DEBUG = Path('/Users/gzx/debug-workspace/e2e-evaluate/memory-e2e')


def _idle(folder):
    script = Path(__file__).parent / 'native/astronstudio-config.mjs'
    result = subprocess.run(['node', str(script)], capture_output=True, timeout=60)
    publish(folder / ('guard-' + timestamp().replace(':', '-') + '.stdout'), result.stdout)
    publish(folder / ('guard-' + timestamp().replace(':', '-') + '.stderr'), result.stderr)
    require(result.returncode == 0, 'ASTUDIO_NOT_IDLE', 'AStudio identity, GUI and native idle must be verified')


def astudio_memory_config(folder, action):
    folder = Path(folder).absolute()
    require(action in {'enable', 'restore'} and folder.is_relative_to(DEBUG) and folder.resolve() == folder,
            'ASTUDIO_ACTIVATION_SCOPE', 'Use an owned debug directory and enable/restore only')
    if action == 'enable':
        require(not folder.exists(), 'OUTPUT_EXISTS', str(folder))
        folder.mkdir(parents=True, mode=0o700)
    else:
        require(folder.is_dir() and not (folder / 'restoration.json').exists(), 'ASTUDIO_LEASE_STATE', str(folder))
    _idle(folder)
    if action == 'enable':
        records = []
        for index, home in enumerate(HOMES):
            path = home / 'config.toml'
            require(path.resolve() == path and path.is_file(), 'ASTUDIO_HOME_PATH', str(path))
            original = path.read_bytes()
            desired = original.decode()
            for table, fields in ASTUDIO_MEMORY_FIELDS.items():
                desired = set_toml_fields(desired, table, fields)
            backup = folder / f'config-{index}.original.private'
            with backup.open('xb') as stream:
                os.chmod(backup, 0o600)
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
            records.append({'path': str(path), 'backup': str(backup), 'before_sha256': sha(original),
                            'desired_sha256': sha(desired.encode()), 'desired': desired, 'mode': path.stat().st_mode})
        # Keep secrets in private backups, never in the public lease or stdout.
        lease = {'harness': 'AstronStudio', 'created_at': timestamp(), 'fields': ASTUDIO_MEMORY_FIELDS,
                 'records': [{k: v for k, v in record.items() if k != 'desired'} for record in records],
                 'runtime_apply_verified': False, 'codex_memory_touched': False}
        publish(folder / 'lease.json', lease)
        try:
            for record in records:
                path = Path(record['path'])
                _replace_owned(path, Path(record['backup']).read_bytes(), record['desired'].encode(), record['mode'])
                env = dict(os.environ, ACODE_HOME=str(path.parent))
                checked = subprocess.run([KERNEL, 'features', 'list'], env=env, capture_output=True, timeout=30)
                lines = [line for line in checked.stdout.decode().splitlines() if line.split()[:1] == ['memories']]
                require(checked.returncode == 0 and len(lines) == 1 and lines[0].split()[-1] == 'true',
                        'ASTUDIO_CONFIG_READBACK', 'Installed ACode did not confirm memories=true')
        except Exception:
            for record in reversed(records):
                path = Path(record['path'])
                if sha(path.read_bytes()) == record['desired_sha256']:
                    _replace_owned(path, path.read_bytes(), Path(record['backup']).read_bytes(), record['mode'])
            raise
        receipt = {'status': 'CONFIG_ENABLED', 'created_at': timestamp(), 'harness': 'AstronStudio',
                   'fields': ASTUDIO_MEMORY_FIELDS, 'runtime_apply_verified': False, 'automatic_formation_verified': False}
        publish(folder / 'activation.json', receipt)
        return receipt
    lease = read_json(folder / 'lease.json')
    require(lease.get('harness') == 'AstronStudio' and lease.get('fields') == ASTUDIO_MEMORY_FIELDS,
            'ASTUDIO_LEASE_STATE', 'Unknown configuration lease')
    require([row['path'] for row in lease['records']] == [str(home / 'config.toml') for home in HOMES],
            'ASTUDIO_HOME_PATH', 'Lease paths must be the two AStudio homes')
    restored = []
    for record in reversed(lease['records']):
        path, backup = Path(record['path']), Path(record['backup'])
        require(backup.parent == folder and not backup.is_symlink() and sha(backup.read_bytes()) == record['before_sha256'],
                'ASTUDIO_BACKUP_DRIFT', str(backup))
        current, original = path.read_bytes(), backup.read_bytes()
        if sha(current) == record['desired_sha256']:
            desired, method = original, 'original_bytes'
        elif current == original:
            restored.append({'path': str(path), 'method': 'already_original'})
            continue
        else:
            parsed, before = tomllib.loads(current.decode()), tomllib.loads(original.decode())
            require(all(parsed.get(table, {}).get(key) == value for table, fields in ASTUDIO_MEMORY_FIELDS.items()
                        for key, value in fields.items()), 'CONFIG_CONCURRENT_EDIT', 'A controlled memory field changed; preserve it')
            text = current.decode()
            for table, fields in ASTUDIO_MEMORY_FIELDS.items():
                text = set_toml_fields(text, table, {key: before.get(table, {}).get(key) for key in fields})
            desired, method = text.encode(), 'controlled_fields_only_preserving_other_changes'
        _replace_owned(path, current, desired, path.stat().st_mode)
        restored.append({'path': str(path), 'method': method, 'sha256': sha(desired)})
    receipt = {'status': 'CONFIG_RESTORED', 'created_at': timestamp(), 'records': restored,
               'running_session_reapply_required': True, 'codex_memory_touched': False}
    publish(folder / 'restoration.json', receipt)
    return receipt
