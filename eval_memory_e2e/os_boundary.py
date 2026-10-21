"""macOS process-tree Seatbelt boundary; test fixtures never read real non-target data."""
import argparse
import ctypes
import errno
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_memory_e2e.io import publish, read_json, require, sha, timestamp
from eval_memory_e2e.machine import machine_paths, machine_identity, kernel_identity
from eval_memory_e2e.production import require_production_lease, require_production_environment, reject_source_build

ADAPTER = 'macos-seatbelt-astudio-backend/v1'
COMPOSED_ADAPTER = 'macos-seatbelt-astudio-native-executor/v2'
COMPILED_ADAPTER = 'macos-seatbelt-astudio-compiled-kernel/v3'
APP = '/Applications/AStudio.app/Contents/MacOS/AStudio'
SELF = Path(__file__).resolve()
BRIDGE = SELF.parent / 'native/seatbelt-bridge.c'
GUARD = SELF.parent / 'native/seatbelt-spawn-guard.cjs'
LAUNCHER = SELF.parent / 'native/seatbelt-launch.mjs'
OPERATIONS = ('file-read-data', 'file-read-metadata', 'file-write-data', 'file-write-unlink')


def non_target_roots():
    # Construct literals only. Never stat, enumerate, resolve or open these roots.
    home = machine_paths()['home']
    return [home / name for name in ('.codex', '.workbuddy', '.qwenworkcn', '.doubaowork',
            'Library/Application Support/Codex', 'Library/Application Support/ChatGPT',
            'Library/Application Support/WorkBuddy', 'Library/Application Support/WorkBuddyExtension',
            'Library/Application Support/QwenWorkCN', 'Library/Application Support/DoubaoWork')]


def profile_text(roots, readonly=(), immutable=()):
    paths = set()
    for value in roots:
        p = str(value)
        require(p.startswith('/Users/') and '\n' not in p and '\x00' not in p,
                'BOUNDARY_PROFILE_PATH', p)
        paths.add(p)
        paths.add('/System/Volumes/Data' + p)
    rules = '\n'.join('  (subpath ' + json.dumps(p) + ')' for p in sorted(paths))
    readonly_rules = '\n'.join('  (subpath ' + json.dumps(str(p)) + ')' for p in readonly)
    readonly_rules += '\n' + '\n'.join('  (literal ' + json.dumps(str(p)) + ')' for p in immutable)
    return ('(version 1)\n(allow default)\n'
            '(deny file-read* file-write*\n' + rules + ')\n'
            '(deny appleevent-send)\n'
            + ('(deny file-write*\n' + readonly_rules + ')\n' if readonly or immutable else ''))


def lease_profile(folder, scope=None):
    result = profile_text(non_target_roots() + [folder / 'synthetic/non-target'],
                          readonly=[SELF.parent, folder / 'control'], immutable=[folder, folder / 'lease.json'])
    if scope is not None:
        from .astudio_scope import load, profile_rules
        result += profile_rules(load(scope['scope'], scope), folder / 'synthetic/allowed')
    return result


def _folder(value, new=False):
    p = Path(value).absolute()
    require(p.is_relative_to(machine_paths()['debug']) and p.resolve() == p,
            'BOUNDARY_EVIDENCE_SCOPE', str(p))
    if new:
        require(not p.exists(), 'OUTPUT_EXISTS', str(p))
        p.mkdir(parents=True, mode=0o700)
    return p


def process_table():
    result = subprocess.check_output(['/bin/ps', '-axo', 'pid=,ppid=,lstart=,args='], text=True)
    table = {}
    for line in result.splitlines():
        parts = line.split(None, 7)
        if len(parts) == 8:
            pid, ppid = int(parts[0]), int(parts[1])
            table[pid] = {'pid': pid, 'ppid': ppid, 'started_at': ' '.join(parts[2:7]),
                          'command': parts[7]}
    return table


def check_policy(pid, path, operation):
    lib = ctypes.CDLL('/usr/lib/libsandbox.1.dylib', use_errno=True)
    call = lib.sandbox_check
    # Apple arm64 variadic arguments use the stack. Fixed args MUST be declared.
    call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    call.restype = ctypes.c_int
    no_report = ctypes.c_int.in_dll(lib, 'SANDBOX_CHECK_NO_REPORT').value
    ctypes.set_errno(0)
    result = call(pid, operation.encode(), 1 | no_report, ctypes.c_char_p(os.fsencode(path)))
    require(result in (0, 1), 'BOUNDARY_OS_QUERY_FAILED', str(ctypes.get_errno()))
    return result


def _attempt(name, action, denied):
    try:
        action()
        return {'operation': name, 'denied': False, 'pass': not denied}
    except OSError as exc:
        rejected = exc.errno in (errno.EPERM, errno.EACCES)
        return {'operation': name, 'denied': rejected, 'errno': exc.errno,
                'pass': denied and rejected}


def fixture_probe(folder, child=False):
    """Only paths owned by this synthetic fixture are ever attempted."""
    folder = _folder(folder)
    protected, allowed = folder / 'synthetic/non-target', folder / 'synthetic/allowed'
    secret, control = protected / 'canary.txt', allowed / 'control.txt'
    alias = allowed / 'alias/canary.txt'
    results = []
    def write_existing(path):
        with path.open('r+b') as stream:
            stream.write(b'UNEXPECTED')
    tests = [('read', lambda: secret.read_bytes()),
             ('enumerate', lambda: list(protected.iterdir())),
             ('stat', lambda: secret.stat()),
             ('write', lambda: write_existing(secret)),
             ('create', lambda: (protected / 'created').write_text('bad')),
             ('delete', lambda: secret.unlink()),
             ('rename_out', lambda: secret.rename(allowed / 'stolen')),
             ('rename_in', lambda: control.rename(protected / 'replaced')),
             ('symlink_alias_read', lambda: alias.read_bytes()),
             ('hardlink_out', lambda: os.link(secret, allowed / 'linked'))]
    for name, action in tests:
        results.append(_attempt(name, action, True))
    results.append(_attempt('allowed_read', lambda: control.read_bytes(), False))
    results.append(_attempt('allowed_create', lambda: (allowed / ('child-ok' if child else 'ok')).write_text('ok'), False))
    policies = {op: {'protected': check_policy(os.getpid(), secret, op),
                     'allowed': check_policy(os.getpid(), control, op)} for op in OPERATIONS}
    require(all(x['protected'] == 1 and x['allowed'] == 0 for x in policies.values()),
            'BOUNDARY_FIXTURE_OS_POLICY', 'OS query must agree with actual denied operations and positive controls')
    descendants = []
    if not child:
        proc = subprocess.run([sys.executable, str(SELF), '_fixture-probe', '--lease-dir', str(folder), '--child'],
                              capture_output=True, text=True, timeout=30)
        require(proc.returncode == 0, 'BOUNDARY_CHILD_FIXTURE', proc.stderr[-500:])
        descendants.append(json.loads(proc.stdout))
        for command in (['/bin/cat', str(secret)], ['/usr/bin/find', str(protected), '-type', 'f']):
            proc = subprocess.run(command, capture_output=True, timeout=10)
            results.append({'operation': 'exec_' + Path(command[0]).name, 'returncode': proc.returncode,
                            'stdout_bytes': len(proc.stdout), 'pass': proc.returncode != 0 and not proc.stdout})
    return {'pid': os.getpid(), 'ppid': os.getppid(), 'fixture_only': True,
            'results': results, 'os_policy': policies, 'children': descendants,
            'pass': all(x['pass'] for x in results) and all(x['pass'] for x in descendants)}


def selftest(folder, scope=None, native_build=None, compiled_kernel=None, sdk_root=None):
    if native_build is not None or compiled_kernel is not None:
        reject_source_build()
    require(sys.platform == 'darwin' and platform.machine() == 'arm64', 'BOUNDARY_PLATFORM', 'This admission is macOS arm64 only')
    require(native_build is None or scope is not None, 'BOUNDARY_NATIVE_SCOPE_REQUIRED', 'Native composition requires a fresh case/repetition scope')
    folder = _folder(folder, True)
    protected, allowed = folder / 'synthetic/non-target', folder / 'synthetic/allowed'
    protected.mkdir(parents=True); allowed.mkdir()
    secret, control = protected / 'canary.txt', allowed / 'control.txt'
    secret.write_text('SYNTHETIC-DENY-' + folder.name + '\n'); control.write_text('SYNTHETIC-ALLOW\n')
    (allowed / 'alias').symlink_to(protected, target_is_directory=True)
    before = sha(secret.read_bytes())
    roots = non_target_roots() + [protected]
    control_folder = folder / 'control'; control_folder.mkdir()
    binary = control_folder / 'seatbelt.node'
    sdk = Path(sdk_root or '/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk').resolve()
    require(sdk.parent == Path('/Library/Developer/CommandLineTools/SDKs') and (sdk / 'SDKSettings.json').is_file(),
            'BOUNDARY_SDK_PATH', 'Use an installed Command Line Tools SDK')
    build = ['xcrun','clang','-bundle','-undefined','dynamic_lookup','-fvisibility=hidden',
             '-arch','arm64','-Wall','-Wextra','-isysroot',str(sdk),str(BRIDGE),'-o',str(binary)]
    compiled = subprocess.run(build,capture_output=True,timeout=60)
    publish(folder / 'build.stdout',compiled.stdout); publish(folder / 'build.stderr',compiled.stderr)
    require(compiled.returncode == 0,'BOUNDARY_BRIDGE_BUILD',compiled.stderr.decode()[-1000:])
    publish(folder / 'build.json',{'command':build,'source_sha256':sha(BRIDGE.read_bytes()),'binary_sha256':sha(binary.read_bytes())})
    if scope is not None:
        from .astudio_scope import freeze
        scope = freeze(scope)
    source = lease_profile(folder, scope)
    publish(control_folder / 'profile.sb', source.encode())
    parent_policy = {op: check_policy(os.getpid(), secret, op) for op in OPERATIONS}
    require(all(x == 0 for x in parent_policy.values()), 'BOUNDARY_POSITIVE_CONTROL', 'Controller must be able to access its synthetic fixture')
    command = ['/usr/bin/sandbox-exec', '-f', str(control_folder / 'profile.sb'), sys.executable,
               str(SELF), '_fixture-probe', '--lease-dir', str(folder)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    publish(folder / 'selftest.stdout', result.stdout); publish(folder / 'selftest.stderr', result.stderr)
    require(result.returncode == 0, 'BOUNDARY_SELFTEST_FAILED', result.stderr.decode()[-1000:])
    probe = json.loads(result.stdout)
    require(probe['pass'] and sha(secret.read_bytes()) == before and control.read_text() == 'SYNTHETIC-ALLOW\n',
            'BOUNDARY_SELFTEST_FAILED', 'Synthetic protected bytes and positive control must survive unchanged')
    # Same native Node bridge and installed Electron RunAsNode runtime as the
    # actual backend; no business RPC, model, real memory or Chrome flags.
    code = "const fs=require('fs');require(process.argv[1]).apply(fs.readFileSync(process.argv[2],'utf8'));fs.realpathSync(process.argv[5]+'/synthetic/allowed/control.txt');const p=require('child_process').spawnSync(process.argv[3],[process.argv[4],'_fixture-probe','--lease-dir',process.argv[5]],{encoding:'utf8'});process.stdout.write(p.stdout);process.stderr.write(p.stderr);process.exit(p.status??1)"
    node_command = [APP,'-e',code,str(binary),str(control_folder / 'profile.sb'),sys.executable,str(SELF),str(folder)]
    node_result = subprocess.run(node_command,env=dict(os.environ,ELECTRON_RUN_AS_NODE='1'),capture_output=True,timeout=60)
    publish(folder / 'node-selftest.stdout',node_result.stdout);publish(folder / 'node-selftest.stderr',node_result.stderr)
    require(node_result.returncode == 0 and json.loads(node_result.stdout)['pass'],
            'BOUNDARY_NODE_SELFTEST_FAILED',node_result.stderr.decode()[-1000:])
    require(sha(secret.read_bytes()) == before,'BOUNDARY_FIXTURE_DRIFT','Synthetic protected bytes changed')
    nested = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(control_folder / 'profile.sb'),
                             '/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)', '/bin/cat', str(control)],
                            capture_output=True, timeout=20)
    publish(folder / 'nested-sandbox.stdout', nested.stdout)
    publish(folder / 'nested-sandbox.stderr', nested.stderr)
    adapter = ADAPTER
    lease = {'contract': adapter, 'created_at': timestamp(), 'machine': machine_identity(),
             'kernel': kernel_identity(), 'profile': str(control_folder / 'profile.sb'), 'profile_sha256': sha(source.encode()),
             'protected_root_literals': [str(x) for x in roots], 'synthetic_root': str(protected),
             'synthetic_secret': str(secret), 'allowed_control': str(control), 'synthetic_secret_sha256': before,
             'helper_sha256': sha(SELF.read_bytes()), 'selftest': str(folder / 'selftest.json'),
             'real_non_target_files_attempted': False, 'launch': None,
             'bridge_source_sha256':sha(BRIDGE.read_bytes()),'spawn_guard_sha256':sha(GUARD.read_bytes()),
             'launch_helper_sha256':sha(LAUNCHER.read_bytes()),
             'bridge':str(binary),'bridge_sha256':sha(binary.read_bytes())}
    if scope is not None:
        lease['astudio_scope'] = scope
    publish(folder / 'selftest.json', {'status': 'PASS', 'at': timestamp(), 'command': command,
            'controller_policy': parent_policy, 'probe': probe, 'node_command':node_command,
            'node_bridge_probe':json.loads(node_result.stdout),'real_memory_read': False,
            'nested_native_sandbox': {'returncode': nested.returncode,
                'compatible': nested.returncode == 0 and nested.stdout == control.read_bytes(),
                'automatic_consolidation_admitted': False}})
    lease['selftest_sha256'] = sha((folder / 'selftest.json').read_bytes())
    publish(folder / 'lease.json', lease)
    return {'status': 'PASS', 'adapter': adapter, 'lease': str(folder / 'lease.json'),
            'synthetic_only': True, 'descendant_probe_passed': True}


def load_lease(path, expected=None):
    path = Path(path).absolute(); folder = _folder(path.parent)
    require(path.name == 'lease.json' and path.resolve() == path, 'BOUNDARY_LEASE_PATH', str(path))
    data = read_json(path)
    require_production_lease(data)
    require(data['contract'] in (ADAPTER, COMPOSED_ADAPTER, COMPILED_ADAPTER) and data['machine'] == machine_identity(), 'BOUNDARY_MACHINE_DRIFT', str(path))
    require(data['helper_sha256'] == sha(SELF.read_bytes()) and data['kernel'] == kernel_identity(),
            'BOUNDARY_RUNTIME_DRIFT', 'Create a fresh lease for changed source/kernel')
    profile = folder / 'control/profile.sb'
    roots = non_target_roots() + [folder / 'synthetic/non-target']
    require(data['protected_root_literals'] == [str(x) for x in roots]
            and data['profile'] == str(profile) and profile.resolve() == profile
            and profile.read_text() == lease_profile(folder, data.get('astudio_scope'))
            and sha(profile.read_bytes()) == data['profile_sha256'], 'BOUNDARY_PROFILE_DRIFT', str(profile))
    require(data['bridge_source_sha256'] == sha(BRIDGE.read_bytes()) and data['spawn_guard_sha256'] == sha(GUARD.read_bytes())
            and data['launch_helper_sha256'] == sha(LAUNCHER.read_bytes())
            and data['bridge'] == str(folder / 'control/seatbelt.node') and sha(Path(data['bridge']).read_bytes()) == data['bridge_sha256']
            , 'BOUNDARY_BRIDGE_DRIFT',str(path))
    require(sha((folder / 'selftest.json').read_bytes()) == data['selftest_sha256']
            and read_json(folder / 'selftest.json')['status'] == 'PASS', 'BOUNDARY_SELFTEST_DRIFT', str(path))
    if expected is not None:
        require(expected.get('admitted_adapter') == data['contract'] and expected.get('lease') == str(path)
                and expected.get('profile_sha256') == data['profile_sha256']
                and expected.get('selftest_sha256') == data['selftest_sha256']
                and expected.get('lease_sha256') == sha(path.read_bytes())
                and expected.get('required') is True, 'BOUNDARY_PROFILE_BINDING', 'Frozen boundary must match the lease')
    return data


def launch(folder):
    require_production_environment()
    folder = _folder(folder); data = load_lease(folder / 'lease.json')
    require(data['launch'] is None, 'BOUNDARY_ALREADY_LAUNCHED', 'Never silently restart a lease')
    table = process_table()
    require(not any(x['command'].startswith(APP) for x in table.values()), 'BOUNDARY_APP_MUST_BE_STOPPED',
            'Confirm native/background idle and quit AStudio normally first')
    require(not os.environ.get('NODE_OPTIONS'),'BOUNDARY_NODE_OPTIONS','Do not inherit an unknown Node preload')
    command = [APP,'--inspect-brk=127.0.0.1:9271','--remote-debugging-port=9240', '--remote-debugging-address=127.0.0.1']
    extra_env = {}
    if data.get('astudio_scope') is not None:
        from .astudio_scope import load, environment
        extra_env = environment(load(data['astudio_scope']['scope'], data['astudio_scope']))
    with (folder / 'app.stdout').open('xb') as out, (folder / 'app.stderr').open('xb') as err:
        child = subprocess.Popen(command, env=dict(os.environ, **extra_env), stdout=out, stderr=err, start_new_session=True)
    for _ in range(100):
        table = process_table(); identity = table.get(child.pid)
        if identity and identity['command'].startswith(APP + ' '):
            break
        require(child.poll() is None, 'BOUNDARY_APP_EXITED', str(child.returncode))
        time.sleep(.1)
    else:
        require(False, 'BOUNDARY_APP_START_UNVERIFIED', str(child.pid))
    data['launch'] = {'command': command, 'identity': identity, 'at': timestamp(),
                      'bootstrap_mode':'paused-main-inspector-exact-backend-spawn-wrapper','environment_added':extra_env}
    # The only lease mutation is recording this one launch before profile binding.
    (folder / 'lease.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    bootstrap = subprocess.run(['node',str(LAUNCHER),str(folder/'lease.json'),str(child.pid)],capture_output=True,timeout=90)
    publish(folder/'bootstrap.stdout',bootstrap.stdout);publish(folder/'bootstrap.stderr',bootstrap.stderr)
    require(bootstrap.returncode == 0,'BOUNDARY_BOOTSTRAP_FAILED',bootstrap.stderr.decode()[-1500:])
    data['launch']['bootstrap_receipt_sha256']=sha((folder/'bootstrap-install.json').read_bytes())
    (folder / 'lease.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    return {'status': 'LAUNCHED', 'pid': child.pid, 'lease': str(folder / 'lease.json'), 'adapter': data['contract']}


def attest(path, expected=None):
    data = load_lease(path, expected)
    require(data['launch'] is not None, 'BOUNDARY_NOT_LAUNCHED', str(path))
    require(data['launch'].get('bootstrap_receipt_sha256') == sha((Path(path).parent/'bootstrap-install.json').read_bytes()),
            'BOUNDARY_BOOTSTRAP_DRIFT',str(path))
    table = process_table(); identity = data['launch']['identity']; pid = identity['pid']
    def same_process():
        current = process_table().get(pid)
        return current is not None and all(current[k] == identity[k] for k in ('pid', 'started_at', 'command'))
    require(same_process(), 'BOUNDARY_PROCESS_REPLACED', 'Launch PID/start/command must remain exact; exited launcher may reparent to PID1')
    selected = {pid}
    while True:
        more = {p for p,x in table.items() if x['ppid'] in selected}
        if more <= selected: break
        selected |= more
    # Reject another independent AStudio main/backend/kernel. Pre-existing
    # orphan crash reporters are not tool execution roots and are not claimed.
    application_kernel = data['kernel']
    kernel_command = application_kernel['path'] + ' '
    foreign = [x for p,x in table.items() if p not in selected and (x['command'].startswith(APP)
               or x['command'].startswith('/Applications/AStudio.app/Contents/Resources/bin/acode-')
               or x['command'].startswith(kernel_command))]
    require(not foreign, 'BOUNDARY_FOREIGN_APP_PROCESS', 'An unbound AStudio execution root exists')
    backend_roots = {p for p in selected if '/app.asar/apps/server/dist/index.mjs' in table[p]['command']}
    require(len(backend_roots)==1,'BOUNDARY_BACKEND_NOT_READY','Exactly one installed backend required')
    restricted = set(backend_roots)
    while True:
        more={p for p in selected if table[p]['ppid'] in restricted}
        if more <= restricted:break
        restricted |= more
    processes = []
    for p in sorted(restricted):
        row = table[p]
        checks = {op: check_policy(p, data['synthetic_secret'], op) for op in OPERATIONS}
        require(all(x == 1 for x in checks.values()), 'BOUNDARY_CHILD_NOT_RESTRICTED', str(p))
        allowed = check_policy(p, data['allowed_control'], 'file-read-data')
        processes.append({**row, 'synthetic_protected': checks, 'allowed_read': allowed})
    commands = [x['command'] for x in processes]
    require(any(x.startswith(kernel_command) and 'app-server' in x for x in commands),
            'BOUNDARY_BACKEND_NOT_READY', 'Backend and the exact selected kernel must both be descendants')
    for row in processes:
        if row['pid'] in backend_roots or row['command'].startswith(kernel_command):
            require(row['allowed_read'] == 0, 'BOUNDARY_POSITIVE_CONTROL', str(row['pid']))
    require(same_process(), 'BOUNDARY_PROCESS_REPLACED', 'Identity changed during OS checks')
    return {'contract': data['contract'], 'status': 'PASS', 'at': timestamp(), 'profile_sha256': data['profile_sha256'],
            'selftest_sha256': data['selftest_sha256'], 'lease': str(Path(path).absolute()),
            'launch_identity': identity, 'processes': processes, 'real_memory_probed': False,
            'enforcement_scope': 'installed backend, ACode kernel and their descendant filesystem operations',
            'ui_chromium_sandbox': 'unchanged; UI process not covered by this additional backend deny profile',
            'external_broker_isolation_exhaustive': False, 'native_executor': None,
            'application_kernel': application_kernel, 'installed_kernel_reference': data['kernel']}


def frozen_boundary(path):
    data = load_lease(path)
    attest(path)
    return {'required': True, 'status': 'os_enforced', 'admitted_adapter': data['contract'],
            'lease': str(Path(path).absolute()), 'profile_sha256': data['profile_sha256'],
            'selftest_sha256': data['selftest_sha256'],'lease_sha256':sha(Path(path).read_bytes())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['selftest', 'launch', 'attest', '_fixture-probe'])
    parser.add_argument('--lease-dir', type=Path, required=True)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--expected-json')
    parser.add_argument('--astudio-scope', type=Path)
    parser.add_argument('--sdk-root', type=Path)
    parser.add_argument('--native-executor-build', type=Path)
    parser.add_argument('--compiled-kernel-build', type=Path)
    args = parser.parse_args()
    if args.action == 'selftest': result = selftest(args.lease_dir, args.astudio_scope, args.native_executor_build, args.compiled_kernel_build, args.sdk_root)
    elif args.action == 'launch': result = launch(args.lease_dir)
    elif args.action == 'attest': result = attest(args.lease_dir / 'lease.json', json.loads(args.expected_json) if args.expected_json else None)
    else: result = fixture_probe(args.lease_dir, args.child)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
