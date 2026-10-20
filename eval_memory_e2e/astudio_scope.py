"""Same-account AStudio memory units, with private homes and an OS access boundary.

A unit is one case/repetition, including its multi-session C0/M+ chain. It is
never reset mid-chain. Old units and the ordinary account home are preserved.
Only the native login session and a small provider configuration are imported;
conversations, memories, indexes, instructions and plugins are not imported.
"""
import argparse
import json
import os
import plistlib
import re
import struct
import subprocess
import time
import tomllib
from pathlib import Path
from uuid import uuid4

if __package__ in (None, ''):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_memory_e2e.io import publish, read_json, require, sha, timestamp
from eval_memory_e2e.machine import machine_paths, kernel_identity
from eval_memory_e2e.configuration import ASTUDIO_MEMORY_FIELDS, set_toml_fields

CONTRACT = 'astudio-case-memory-unit/v1'
SELF = Path(__file__).resolve()
APP = '/Applications/AStudio.app/Contents/MacOS/AStudio'


def asar_file(archive, name):
    with Path(archive).open('rb') as stream:
        _, size, _, length = struct.unpack('<4I', stream.read(16))
        entry = json.loads(stream.read(length))
        for part in name.split('/'):
            entry = entry['files'][part]
        require(not entry.get('unpacked') and not entry.get('link'), 'SCOPE_ASAR_ENTRY', name)
        stream.seek(8 + size + int(entry['offset']))
        data = stream.read(entry['size'])
        require(len(data) == entry['size'], 'SCOPE_ASAR_ENTRY', name)
        return data


def installation_witness():
    archive = Path('/Applications/AStudio.app/Contents/Resources/app.asar')
    names = ['apps/desktop/dist-electron/main.js', 'apps/server/dist/index.mjs']
    code = {name: asar_file(archive, name).decode() for name in names}
    main, server = (code[name] for name in names)
    checks = {
        'desktop_native_home_override': 'const configuredBaseDir = process.env.ASTUDIO_HOME?.trim()' in main,
        'desktop_userdata_from_base': 'const STATE_DIR = node_path.join(BASE_DIR, "userdata")' in main,
        'desktop_electron_from_base': 'return node_path.join(BASE_DIR, "electron")' in main,
        'backend_source_home_override': 'env[ASTUDIO_ACODE_HOME_ENV]?.trim()' in server,
        'overlay_from_desktop_home': 'return path.join(overlayRoot, ACODE_HOME_OVERLAY_DIR)' in server,
        'overlay_current_name': 'const ACODE_HOME_OVERLAY_DIR = "acode-home-overlay"' in server,
        'login_session_from_state': 'const SESSION_FILE_NAME = "astron-session.json"' in server,
    }
    require(all(checks.values()), 'SCOPE_INSTALLATION_UNSUPPORTED', str(checks))
    with Path('/Applications/AStudio.app/Contents/Info.plist').open('rb') as stream:
        version = plistlib.load(stream)['CFBundleShortVersionString']
    return {'app_version': version, 'asar_sha256': sha(archive.read_bytes()),
            'source_sha256': {name: sha(value.encode()) for name, value in code.items()},
            'checks': checks, 'kernel': kernel_identity()}


def _private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _path(path):
    path = Path(path).absolute()
    require(path.is_relative_to(machine_paths()['debug']) and path.resolve() == path
            and not re.search(r'[\s\x00]', str(path)), 'SCOPE_PATH', str(path))
    return path


def minimal_config(original, generate_memories=False):
    parsed = tomllib.loads(original)
    provider = parsed.get('model_providers', {}).get('astron-spark')
    require(isinstance(provider, dict), 'SCOPE_PROVIDER', 'Current AStudio provider is required')
    allowed = {'name', 'base_url', 'wire_api', 'requires_openai_auth', 'experimental_bearer_token',
               'uid', 'stream_idle_timeout_ms', 'request_max_retries', 'stream_max_retries'}
    fields = {k: v for k, v in provider.items() if k in allowed and type(v) in (str, int, bool)}
    text = 'model_provider = "astron-spark"\n\n[model_providers.astron-spark]\n'
    text += ''.join(k + ' = ' + json.dumps(v, ensure_ascii=False) + '\n' for k, v in fields.items())
    for table, values in ASTUDIO_MEMORY_FIELDS.items():
        values = dict(values)
        if table == 'memories':
            values['generate_memories'] = generate_memories
        text = set_toml_fields(text, table, values)
    return text


def create(folder, *, case_id, repetition, batch_root, generate_memories=False):
    folder, batch_root = _path(folder), _path(batch_root)
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', case_id) and type(repetition) is int
            and 1 <= repetition <= 20, 'SCOPE_UNIT_KEY', 'Case id and repetition 1..20 required')
    require(not folder.exists() and not batch_root.exists() and not batch_root.is_relative_to(folder),
            'SCOPE_FRESH_PATH', 'Use new separate unit and batch directories')
    witness = installation_witness()
    ordinary = machine_paths()
    login = ordinary['acode'] / 'acode/userdata/astron-session.json'
    config = ordinary['acode'] / 'config.toml'
    require(login.resolve() == login and config.resolve() == config, 'SCOPE_SOURCE_SYMLINK', 'Native account files only')
    login_bytes = login.read_bytes(); account = json.loads(login_bytes)
    require(account.get('uid') and account.get('loginMethod') in ('sms', 'password', 'wechat'),
            'SCOPE_LOGIN_REQUIRED', 'Keep the currently signed-in native account')
    config_bytes = config.read_bytes()
    baseline_paths = [login, config, ordinary['overlay'] / 'config.toml', ordinary['astudio_db']]
    baseline = [{'path': str(p), 'sha256': sha(p.read_bytes()), 'size': p.stat().st_size}
                for p in baseline_paths if p.is_file()]
    folder.mkdir(parents=True, mode=0o700)
    runtime = folder / 'runtime'
    paths = {'runtime': str(runtime), 'acode': str(runtime / 'source-home'),
             'desktop': str(runtime / 'desktop'), 'overlay': str(runtime / 'desktop/acode-home-overlay'),
             'astudio_db': str(runtime / 'desktop/userdata/state.sqlite'),
             'temp': str(runtime / 'tmp'), 'candidate': str(batch_root / 'candidate')}
    for key in ('acode', 'desktop', 'overlay', 'temp'):
        Path(paths[key]).mkdir(parents=True, mode=0o700)
    _private(Path(paths['desktop']) / 'userdata/astron-session.json', login_bytes)
    require(type(generate_memories) is bool, 'SCOPE_MEMORY_CONDITION', 'Explicit boolean required')
    selected = minimal_config(config_bytes.decode(), generate_memories).encode()
    _private(Path(paths['acode']) / 'config.toml', selected)
    _private(Path(paths['overlay']) / 'config.toml', selected)
    spec = {'contract': CONTRACT, 'unit_id': uuid4().hex, 'created_at': timestamp(),
            'case_id': case_id, 'repetition': repetition, 'batch_root': str(batch_root), 'paths': paths,
            'account_fingerprint': sha(str(account['uid']).encode()),
            'ordinary_baseline': baseline, 'installation': witness,
            'imported': ['native_login_session', 'allowlisted_provider_configuration'],
            'memory_baseline': 'new_empty_unit', 'ordinary_memory_cleared': False,
            'memory_condition': {'enabled': True, 'use_memories': True,
                                 'generate_memories': generate_memories, 'dedicated_tools': True},
            'within_unit_reset': False, 'scope_helper_sha256': sha(SELF.read_bytes())}
    _private(folder / 'scope.json', (json.dumps(spec, ensure_ascii=False, indent=2) + '\n').encode())
    return {'scope': str(folder / 'scope.json'), 'unit_id': spec['unit_id'],
            'account_fingerprint': spec['account_fingerprint'], 'paths': paths}


def load(path, frozen=None):
    path = _path(path)
    require(path.name == 'scope.json', 'SCOPE_SPEC_PATH', str(path))
    spec = read_json(path)
    runtime = path.parent / 'runtime'
    expected = {'runtime': str(runtime), 'acode': str(runtime / 'source-home'),
                'desktop': str(runtime / 'desktop'), 'overlay': str(runtime / 'desktop/acode-home-overlay'),
                'astudio_db': str(runtime / 'desktop/userdata/state.sqlite'),
                'temp': str(runtime / 'tmp'), 'candidate': str(_path(spec['batch_root']) / 'candidate')}
    require(spec['contract'] == CONTRACT and spec['paths'] == expected
            and spec['scope_helper_sha256'] == sha(SELF.read_bytes()), 'SCOPE_SPEC_DRIFT', str(path))
    require(spec['installation'] == installation_witness(), 'SCOPE_INSTALLATION_DRIFT', str(path))
    for value in expected.values():
        _path(value)
    if frozen is not None:
        require(frozen == freeze(path, spec=spec), 'SCOPE_FROZEN_DRIFT', str(path))
    return spec


def freeze(path, *, spec=None):
    path = _path(path)
    spec = spec or load(path)
    return {'contract': CONTRACT, 'scope': str(path), 'scope_sha256': sha(path.read_bytes()),
            'unit_id': spec['unit_id'], 'case_id': spec['case_id'], 'repetition': spec['repetition'],
            'batch_root': spec['batch_root'], 'paths': spec['paths'],
            'account_fingerprint': spec['account_fingerprint']}


def profile_rules(spec, fixture_allowed):
    """Old test evidence and source homes are inaccessible, including path aliases.

    Persistent writes are restricted to the current unit/workspaces, preventing
    the evaluated backend from making a second memory cache outside the unit.
    """
    allowed = [spec['paths']['runtime'], spec['paths']['candidate'], str(fixture_allowed)]
    def aliases(values):
        return [p for value in values for p in (str(value), '/System/Volumes/Data' + str(value))]
    exclusions = '\n'.join('    (require-not (subpath ' + json.dumps(p) + '))' for p in aliases(allowed))
    debug = str(machine_paths()['debug'])
    ancestors = sorted({str(parent) for value in allowed for parent in Path(value).parents
                        if parent.is_relative_to(machine_paths()['debug'])})
    metadata_exclusions = '\n'.join('    (require-not (literal ' + json.dumps(p) + '))' for p in aliases(ancestors))
    debug_rules = '\n'.join('  (require-all (subpath ' + json.dumps(p) + ')\n' + exclusions
                            + '\n' + metadata_exclusions + ')' for p in aliases([debug]))
    # Node's native realpath walks ancestor metadata. Permit that traversal,
    # while still denying directory enumeration and writes at those ancestors.
    ancestor_data = '\n'.join('  (literal ' + json.dumps(p) + ')' for p in aliases(ancestors))
    home_rules = '\n'.join('  (subpath ' + json.dumps(p) + ')' for p in aliases([machine_paths()['acode']]))
    writes = exclusions + '\n    (require-not (literal "/dev/null"))\n    (require-not (literal "/dev/tty"))'
    return ('\n(deny file-read* file-write*\n' + home_rules + '\n' + debug_rules + ')\n'
            '(deny file-read-data\n' + ancestor_data + ')\n'
            '(deny file-write* (require-all\n' + writes + '))\n')


def bind_batch(profile, root, scope, scenarios, repeats):
    spec = load(scope)
    require(str(Path(root).absolute()) == spec['batch_root'] and scenarios == [spec['case_id']] and repeats == 1,
            'SCOPE_BATCH_BINDING', 'One case per unit; use a new unit for each case/repetition')
    profile['astudio_scope'] = freeze(scope)
    profile['isolation'] = 'verified_namespace'
    return profile


def environment(spec):
    p = spec['paths']
    return {'ASTUDIO_HOME': p['desktop'], 'ASTUDIO_ACODE_HOME': p['acode'],
            'ACODE_HOME': p['acode'], 'TMPDIR': p['temp'] + '/'}


def attest(frozen, boundary):
    from eval_memory_e2e.os_boundary import attest as os_attest, load_lease, check_policy, OPERATIONS
    spec = load(frozen['scope'], frozen)
    lease = load_lease(boundary['lease'], boundary)
    require(lease.get('astudio_scope') == frozen, 'SCOPE_BOUNDARY_BINDING', 'OS lease belongs to another unit')
    proof = os_attest(boundary['lease'], boundary)
    application_kernel = lease.get('compiled_kernel', {}).get('identity', lease['kernel'])
    kernel_command = application_kernel['path'] + ' '
    selected = []
    for process in proof['processes']:
        is_kernel = process['command'].startswith(kernel_command)
        is_backend = '/app.asar/apps/server/dist/index.mjs' in process['command']
        if not is_backend and not is_kernel:
            continue
        raw = subprocess.check_output(['/bin/ps', 'eww', '-p', str(process['pid']), '-o', 'command='], text=True)
        found = {}
        # Never persist the full environment: it contains authentication tokens.
        keys = ('ASTUDIO_HOME', 'ASTUDIO_ACODE_HOME', 'ACODE_HOME', 'TMPDIR')
        if lease.get('native_executor'): keys += ('ACODE_EXEC_SERVER_URL',)
        if is_backend and lease.get('compiled_kernel'): keys += ('ASTUDIO_ACODE_BIN',)
        for key in keys:
            matches = re.findall(r'(?:^| )' + key + r'=([^ ]+)', raw)
            found[key] = matches[-1] if matches else None
        expected = environment(spec)
        if lease.get('native_executor'): expected['ACODE_EXEC_SERVER_URL'] = lease['native_executor']['launch']['url']
        if is_backend and lease.get('compiled_kernel'): expected['ASTUDIO_ACODE_BIN'] = application_kernel['path']
        if is_kernel:
            expected['ACODE_HOME'] = spec['paths']['overlay']
            # The installed backend deliberately strips desktop-only variables
            # from the app-server child; its actual write root is ACODE_HOME.
            expected['ASTUDIO_HOME'] = None
            expected['ASTUDIO_ACODE_HOME'] = None
        require(found == expected, 'SCOPE_RUNTIME_ENVIRONMENT', str(process['pid']))
        if 'ACODE_EXEC_SERVER_URL' in found:
            found['native_executor_url_sha256'] = sha(found.pop('ACODE_EXEC_SERVER_URL').encode())
        tests = {}
        # Query only synthetic paths and the policy for the ordinary home literal.
        for name, value in [('ordinary_home', machine_paths()['acode'] / 'scope-deny-canary'),
                            ('other_units', machine_paths()['debug'] / 'scope-deny-canary'),
                            ('active_unit', Path(spec['paths']['acode']) / 'config.toml')]:
            tests[name] = {op: check_policy(process['pid'], value, op) for op in OPERATIONS}
        require(all(v == 1 for k in ('ordinary_home', 'other_units') for v in tests[k].values())
                and all(v == 0 for v in tests['active_unit'].values()), 'SCOPE_OS_POLICY', str(process['pid']))
        selected.append({'pid': process['pid'], 'environment': found, 'policy': tests})
    require(len(selected) >= 2, 'SCOPE_EXECUTION_ROOTS', 'Backend and kernel must be bound')
    account = read_json(Path(spec['paths']['desktop']) / 'userdata/astron-session.json')
    require(sha(str(account.get('uid', '')).encode()) == spec['account_fingerprint'], 'SCOPE_ACCOUNT_CHANGED', 'Native account UID differs')
    conditions = {}
    for name in ('acode', 'overlay'):
        parsed = tomllib.loads((Path(spec['paths'][name]) / 'config.toml').read_text())
        conditions[name] = {'enabled': parsed.get('features', {}).get('memories', False),
                            **{key: parsed.get('memories', {}).get(key) for key in ('use_memories', 'generate_memories', 'dedicated_tools')}}
        require(conditions[name] == spec['memory_condition'], 'SCOPE_MEMORY_CONDITION_DRIFT', name)
    return {**proof, 'status': 'PASS', 'contract': CONTRACT, 'at': timestamp(), 'unit_id': spec['unit_id'],
            'case_id': spec['case_id'], 'repetition': spec['repetition'],
            'account_fingerprint': spec['account_fingerprint'], 'execution_roots': selected,
            'os_boundary': proof, 'memory_condition': conditions, 'ordinary_memory_cleared': False}


def verify_ordinary(scope):
    spec = load(scope)
    rows = [{**row, 'unchanged': sha(Path(row['path']).read_bytes()) == row['sha256']}
            for row in spec['ordinary_baseline']]
    return {'at': timestamp(), 'status': 'PASS' if all(r['unchanged'] for r in rows) else 'CHANGED', 'files': rows}


def close(scope, boundary):
    """Quit only this owned, idle instance; retain all its stores and pending rows."""
    from eval_memory_e2e.os_boundary import load_lease, process_table
    spec = load(scope)
    data = load_lease(boundary)
    require(data.get('astudio_scope') == freeze(scope), 'SCOPE_BOUNDARY_BINDING', str(scope))
    identity = data['launch']['identity']
    current = process_table().get(identity['pid'])
    require(current and all(current[k] == identity[k] for k in ('pid', 'started_at', 'command')),
            'SCOPE_OWNED_INSTANCE_REQUIRED', 'Never quit an unrelated application instance')
    require(not machine_paths()['ui_lock'].exists(), 'SCOPE_UI_LOCK', 'UI operation still owns the lock')
    helper = SELF.parent / 'native/astudio-unit-idle.mjs'
    result = subprocess.run(['node', str(helper), str(scope)], capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, 'SCOPE_IDLE_UNVERIFIED', result.stderr[-800:])
    idle = json.loads(result.stdout)
    require(idle['idle'], 'SCOPE_NOT_IDLE', 'Native session or memory job remains active')
    folder = Path(scope).parent
    publish(folder / ('close-idle-' + uuid4().hex + '.json'), idle)
    if data.get('native_executor'):
        from eval_memory_e2e.native_executor import require_idle
        publish(folder / ('close-native-idle-' + uuid4().hex + '.json'), require_idle(data['native_executor']['launch']['control']))
    # Native application quit; no signal, cancellation or mutation of sessions.
    result = subprocess.run(['/usr/bin/osascript', '-e', 'tell application id "cn.xfyun.acode" to quit'],
                            capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, 'SCOPE_NATIVE_QUIT_FAILED', result.stderr[-800:])
    deadline = time.monotonic() + 30
    kernel_command = data.get('compiled_kernel', {}).get('identity', data['kernel'])['path'] + ' '
    while time.monotonic() < deadline:
        roots = [x for x in process_table().values() if x['command'].startswith(APP)
                 or x['command'].startswith('/Applications/AStudio.app/Contents/Resources/bin/acode-')
                 or x['command'].startswith(kernel_command)]
        if not roots:
            native_closed = None
            if data.get('native_executor'):
                from eval_memory_e2e.native_executor import stop
                native_closed = stop(data['native_executor']['launch']['control'])
            record = {'status': 'CLOSED', 'unit_id': spec['unit_id'], 'at': timestamp(),
                      'native_quit': True, 'all_execution_roots_exited': True,
                      'ordinary': verify_ordinary(scope), 'stores_preserved': True, 'native_executor_closed': native_closed}
            publish(folder / 'closed.json', record)
            return record
        time.sleep(.2)
    require(False, 'SCOPE_PROCESSES_REMAIN', 'Do not start another unit while an old execution root remains')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['create', 'verify-ordinary', 'attest', 'close'])
    parser.add_argument('--scope', type=Path, required=True)
    parser.add_argument('--case-id')
    parser.add_argument('--repetition', type=int)
    parser.add_argument('--batch-root', type=Path)
    parser.add_argument('--boundary-json')
    parser.add_argument('--boundary-lease', type=Path)
    parser.add_argument('--generate-memories', action='store_true', help='diagnostic only; nested native sandbox is not admitted')
    parser.add_argument('--frozen-json')
    args = parser.parse_args()
    if args.action == 'create':
        result = create(args.scope.parent, case_id=args.case_id, repetition=args.repetition,
                        batch_root=args.batch_root, generate_memories=args.generate_memories)
    elif args.action == 'verify-ordinary':
        result = verify_ordinary(args.scope)
    elif args.action == 'close':
        result = close(args.scope, args.boundary_lease)
    else:
        result = attest(json.loads(args.frozen_json) if args.frozen_json else freeze(args.scope), json.loads(args.boundary_json))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
