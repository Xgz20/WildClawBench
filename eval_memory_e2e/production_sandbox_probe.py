"""No-model probes of the installed AStudio kernel; never an application lease.

All file RPCs and access attempts target newly created synthetic fixtures. A
native command passing its own policy is not proof of backend-wide OS isolation.
"""
import argparse
import base64
import errno
import json
import os
import platform
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_memory_e2e.io import publish, read_json, require, sha, timestamp
from eval_memory_e2e.machine import kernel_identity, machine_paths
from eval_memory_e2e.os_boundary import check_policy, process_table, profile_text

SELF = Path(__file__).resolve()
PROFILE = 'memory_synthetic_probe'


def fixture_path(folder, relative):
    root = Path(folder).absolute()
    path = root / 'fixture' / relative
    require(not Path(relative).is_absolute() and '..' not in Path(relative).parts
            and path.is_relative_to(root / 'fixture'), 'PRODUCTION_PROBE_FIXTURE_SCOPE', relative)
    return path


def owned_fixture(folder):
    folder = Path(folder).absolute()
    require(folder.is_relative_to(machine_paths()['debug']) and folder.resolve() == folder,
            'PRODUCTION_PROBE_FIXTURE_SCOPE', str(folder))
    witness = read_json(folder / 'synthetic-root.json')
    require(witness == {'contract': 'astudio-production-synthetic-root/v1', 'root': str(folder)},
            'PRODUCTION_PROBE_FIXTURE_SCOPE', 'Only a controller-created synthetic root may be probed')
    return folder


def profile_config(folder):
    """Exact paths only; no real client data directories or account settings."""
    paths = {'/': 'read', str(fixture_path(folder, 'active')): 'write'}
    for relative in ('non-target', 'old-case', 'old-repeat', 'active/private'):
        paths[str(fixture_path(folder, relative))] = 'deny'
    paths[str(fixture_path(folder, 'active/readonly'))] = 'read'
    return ('approval_policy = "never"\ndefault_permissions = ' + json.dumps(PROFILE)
            + '\n[analytics]\nenabled = false\n[permissions.' + PROFILE + '.filesystem]\n'
            + ''.join(json.dumps(p) + ' = ' + json.dumps(access) + '\n' for p, access in paths.items())
            + '[permissions.' + PROFILE + '.network]\nenabled = false\n')


def probe_environment(home, temp):
    # Do not inherit credentials, injected libraries, custom kernels or remote
    # execution services. HOME remains the OS account; ACODE_HOME is private.
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin'),
            'HOME': str(machine_paths()['home']), 'LANG': 'en_US.UTF-8',
            'ACODE_HOME': str(home), 'TMPDIR': str(temp) + '/',
            'PYTHONDONTWRITEBYTECODE': '1'}


def fixture_probe(folder, port, child=False):
    folder = owned_fixture(folder)
    rows = []
    def attempt(name, action, denied):
        try:
            action()
            rows.append({'name': name, 'denied': False, 'pass': not denied})
        except OSError as error:
            blocked = error.errno in (errno.EPERM, errno.EACCES)
            rows.append({'name': name, 'denied': blocked, 'errno': error.errno,
                         'pass': denied and blocked})
    for name in ('non-target', 'old-case', 'old-repeat', 'active/private'):
        root = fixture_path(folder, name); fact = root / 'memory.md'
        attempt(name + '-read', fact.read_bytes, True)
        attempt(name + '-stat', fact.stat, True)
        attempt(name + '-enumerate', lambda p=root: list(p.iterdir()), True)
        attempt(name + '-write', lambda p=fact: p.write_bytes(b'UNEXPECTED'), True)
        attempt(name + '-create', lambda p=root: (p / 'unexpected').write_bytes(b'UNEXPECTED'), True)
        alias = fixture_path(folder, 'active/' + name.replace('/', '-') + '-alias/memory.md')
        attempt(name + '-symlink-read', alias.read_bytes, True)
    active = fixture_path(folder, 'active/memory.md')
    attempt('active-read', active.read_bytes, False)
    attempt('active-write', lambda: active.write_bytes(b'SYNTHETIC-ACTIVE-UPDATED\n'), False)
    readonly = fixture_path(folder, 'active/readonly/memory.md')
    attempt('native-readonly-read', readonly.read_bytes, False)
    attempt('native-readonly-write', lambda: readonly.write_bytes(b'UNEXPECTED'), True)
    attempt('native-network-deny', lambda: socket.create_connection(('127.0.0.1', port), timeout=2), True)
    policies = {name: check_policy(os.getpid(), fixture_path(folder, name + '/memory.md'), 'file-read-data')
                for name in ('active', 'non-target', 'old-case', 'old-repeat', 'active/private')}
    descendants = []
    if not child:
        command = [sys.executable, str(SELF), '_fixture', '--output', str(folder), '--port', str(port), '--child']
        result = subprocess.run(command, capture_output=True, timeout=20)
        descendants.append({'returncode': result.returncode,
                            'result': json.loads(result.stdout) if result.returncode == 0 else None,
                            'stderr': result.stderr.decode()[-1000:]})
    return {'pid': os.getpid(), 'results': rows, 'policy': policies, 'descendants': descendants,
            'pass': all(r['pass'] for r in rows) and policies['active'] == 0
                    and all(v == 1 for k, v in policies.items() if k != 'active')
                    and all(r['result'] and r['result']['pass'] for r in descendants)}


def backend_probe(folder, kernel, environment):
    """Only initialize and read synthetic files; no thread/turn/model RPCs."""
    folder = owned_fixture(folder)
    command = [kernel['path'], 'app-server', '--stdio']
    raw_rows = []
    with (folder / 'backend.stderr').open('xb') as err:
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=err, env=environment, cwd=fixture_path(folder, 'active'), bufsize=0)
        buffer = b''
        def request(number, method, params):
            nonlocal buffer
            message = {'id': number, 'method': method, 'params': params}
            raw_rows.append({'direction': 'request', 'message': message})
            child.stdin.write(json.dumps(message).encode() + b'\n'); child.stdin.flush()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if b'\n' not in buffer:
                    ready, _, _ = select.select([child.stdout], [], [], min(1, deadline - time.monotonic()))
                    if not ready:
                        require(child.poll() is None, 'PRODUCTION_PROBE_BACKEND_EXITED', str(child.returncode))
                        continue
                    chunk = os.read(child.stdout.fileno(), 65536)
                    require(bool(chunk), 'PRODUCTION_PROBE_BACKEND_EOF', method)
                    buffer += chunk
                    continue
                line, buffer = buffer.split(b'\n', 1)
                row = json.loads(line)
                raw_rows.append({'direction': 'response', 'message': row})
                if row.get('id') == number:
                    return row
            require(False, 'PRODUCTION_PROBE_RPC_TIMEOUT', method)
        rows = []
        try:
            initialized = request(1, 'initialize', {'clientInfo': {'name': 'memory_production_synthetic_probe', 'version': '1'},
                                                   'capabilities': {'experimentalApi': True}})
            require('result' in initialized, 'PRODUCTION_PROBE_INITIALIZE', repr(initialized))
            child.stdin.write(b'{"method":"initialized"}\n'); child.stdin.flush()
            identity = process_table().get(child.pid)
            for number, name in enumerate(('active', 'non-target', 'old-case', 'old-repeat'), 2):
                path = fixture_path(folder, name + '/memory.md')
                policy = check_policy(child.pid, path, 'file-read-data')
                response = request(number, 'fs/readFile', {'path': str(path)})
                data = response.get('result', {}).get('dataBase64')
                returned_fixture = data is not None and base64.b64decode(data) == path.read_bytes()
                rows.append({'fixture': name, 'os_file_read_policy': policy,
                             'rpc_returned_exact_synthetic_fact': returned_fixture,
                             'error': response.get('error')})
            return {'identity': identity, 'reads': rows,
                    'backend_denies_non_target': all(r['os_file_read_policy'] == 1
                                                    and not r['rpc_returned_exact_synthetic_fact'] for r in rows[1:])}
        finally:
            publish(folder / 'backend-rpc.json', raw_rows)
            child.stdin.close()
            try:
                code = child.wait(timeout=10)
                close = {'exit_code': code, 'method': 'stdio_eof'}
            except subprocess.TimeoutExpired:
                # This owned probe has no model tasks and never receives a
                # cancellation RPC. SIGTERM only stops the diagnostic server.
                child.terminate(); code = child.wait(timeout=10)
                close = {'exit_code': code, 'method': 'owned_probe_sigterm_after_eof'}
            child.stdout.close()
            publish(folder / 'backend-close.json', close)


def run(folder):
    folder = Path(folder).absolute()
    require(sys.platform == 'darwin' and platform.machine() == 'arm64', 'PRODUCTION_PROBE_PLATFORM', 'macOS arm64 required')
    require(folder.is_relative_to(machine_paths()['debug']) and folder.resolve() == folder and not folder.exists(),
            'PRODUCTION_PROBE_FRESH_PATH', str(folder))
    kernel = kernel_identity()
    folder.mkdir(parents=True, mode=0o700)
    publish(folder / 'synthetic-root.json', {'contract': 'astudio-production-synthetic-root/v1', 'root': str(folder)})
    publish(folder / 'source.py', SELF.read_bytes())
    protected = {}
    for name in ('active', 'non-target', 'old-case', 'old-repeat', 'active/private', 'active/readonly'):
        path = fixture_path(folder, name); path.mkdir(parents=True, exist_ok=True)
        fact = path / 'memory.md'; fact.write_text('SYNTHETIC-' + name + '\n')
        if name != 'active':
            protected[str(fact)] = sha(fact.read_bytes())
    for name in ('non-target', 'old-case', 'old-repeat', 'active/private'):
        fixture_path(folder, 'active/' + name.replace('/', '-') + '-alias').symlink_to(fixture_path(folder, name), target_is_directory=True)
    home, temp = folder / 'acode-home', folder / 'tmp'; home.mkdir(); temp.mkdir()
    publish(home / 'config.toml', profile_config(folder).encode())
    environment = probe_environment(home, temp)
    command = [kernel['path'], 'sandbox', '--permission-profile', PROFILE, '--include-managed-config',
               '-C', str(fixture_path(folder, 'active')), '--', sys.executable, str(SELF), '_fixture', '--output', str(folder)]
    listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen()
    command += ['--port', str(listener.getsockname()[1])]
    try:
        result = subprocess.run(command, env=environment, capture_output=True, timeout=45)
    finally:
        listener.close()
    publish(folder / 'native.stdout', result.stdout); publish(folder / 'native.stderr', result.stderr)
    native = json.loads(result.stdout) if result.returncode == 0 else None
    nested = []
    for name, policy in [('minimal', '(version 1)(allow default)'),
                         ('synthetic_deny', profile_text([fixture_path(folder, 'non-target')]))]:
        args = ['/usr/bin/sandbox-exec', '-p', policy] + command
        proc = subprocess.run(args, env=environment, capture_output=True, timeout=45)
        publish(folder / (name + '.stdout'), proc.stdout); publish(folder / (name + '.stderr'), proc.stderr)
        nested.append({'outer': name, 'returncode': proc.returncode,
                       'nested_apply_failed': b'sandbox_apply: Operation not permitted' in proc.stderr})
    backend = backend_probe(folder, kernel, environment)
    unchanged = all(Path(p).is_file() and sha(Path(p).read_bytes()) == checksum for p, checksum in protected.items())
    report = {'contract': 'astudio-production-sandbox-research/v1', 'at': timestamp(), 'kernel': kernel,
              'native_command': command, 'native_returncode': result.returncode,
              'native_policy_pass': bool(native and native['pass']), 'native_probe': native,
              'nested': nested, 'backend_probe': backend, 'synthetic_protected_files_unchanged': unchanged,
              'installed_kernel_unchanged': kernel_identity() == kernel,
              'real_non_target_paths_attempted': False, 'ordinary_client_changed': False,
              'account_login_changed': False, 'model_prompts': 0, 'formal20_started': False,
              'application_integration_allowed': False, 'automatic_generation_admitted': False,
              'status': 'NOT_ADMITTED_BACKEND_COVERAGE_GAP' if not backend['backend_denies_non_target']
                        else 'RESEARCH_ONLY_NOT_ADMITTED'}
    publish(folder / 'result.json', report)
    return {k: v for k, v in report.items() if k not in ('native_probe', 'backend_probe', 'native_command')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', '_fixture'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    result = run(args.output) if args.action == 'run' else fixture_probe(args.output, args.port, args.child)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
