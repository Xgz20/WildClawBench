"""Control-plane launch and synthetic admission for the composed native service."""
import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

from .io import publish, read_json, require, sha, timestamp
from .machine import machine_paths
from .os_boundary import profile_text, non_target_roots, process_table, check_policy, OPERATIONS
from .astudio_scope import profile_rules

ROOT = Path(__file__).resolve().parents[1]
BROKER = ROOT / 'eval_memory_e2e/native/astudio-native-broker.mjs'
PROBE = BROKER.parent / 'astudio-composed-exec-probe.mjs'
BUNDLE = ROOT / 'tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/node_modules/playwright-core/lib/utilsBundle.js'


def build(path):
    value = read_json(path)
    require(value['contract'] == 'astudio-native-controller-build/v1', 'NATIVE_EXECUTOR_BUILD', str(path))
    binary = Path(value['binary'])
    require(binary.is_relative_to(ROOT / '.kernel-tools/approved') and binary.resolve() == binary
            and sha(binary.read_bytes()) == value['sha256'], 'NATIVE_EXECUTOR_BINARY_DRIFT', str(binary))
    return value


def specification(folder, manifest, profile, *, mode, runtime, acode_home, temp, main=None, test_peer=None):
    value = build(manifest)
    sources = [BROKER, Path(__file__).resolve(), BUNDLE, BUNDLE.parent / 'utilsBundleImpl/index.js']
    return {'contract': 'astudio-composed-native-executor/v2', 'mode': mode,
            'executor': value['binary'], 'executor_sha256': value['sha256'],
            'build_manifest': str(Path(manifest).absolute()), 'build_manifest_sha256': sha(Path(manifest).read_bytes()),
            'profile': str(profile), 'profile_sha256': sha(Path(profile).read_bytes()),
            'sources': {str(p): sha(p.read_bytes()) for p in sources}, 'ws_bundle': str(BUNDLE),
            'token_path': '/' + secrets.token_hex(32), 'runtime': str(runtime), 'acode_home': str(acode_home),
            'temp': str(temp), 'os_home': str(machine_paths()['home']), 'path_env': os.environ.get('PATH', ''),
            'policy_audit_dir': str(Path(folder) / 'policies'), 'main': main, 'test_peer': test_peer,
            'installed_kernel': '/Applications/AStudio.app/Contents/Resources/bin/acode-darwin-arm64'}


def start(folder, spec):
    folder = Path(folder)
    (folder / 'policies').mkdir(mode=0o700)
    path = folder / 'broker-spec.json'; publish(path, spec)
    with (folder / 'broker.stdout').open('xb') as out, (folder / 'broker.stderr').open('xb') as err:
        child = subprocess.Popen(['node', str(BROKER), str(path)], stdout=out, stderr=err, start_new_session=True)
    ready = folder / 'broker-ready.json'
    for _ in range(200):
        if ready.exists():
            return child, read_json(ready)
        require(child.poll() is None, 'NATIVE_BROKER_EXITED', str(child.returncode))
        time.sleep(.05)
    require(False, 'NATIVE_BROKER_READY_TIMEOUT', str(child.pid))


def inspect(folder, *, expected_mode='astudio-owned-session', main_exited_ok=False):
    folder = Path(folder)
    spec_path = folder / 'broker-spec.json'
    spec, ready, status = read_json(spec_path), read_json(folder / 'broker-ready.json'), read_json(folder / 'broker-status.json')
    require(spec['mode'] == expected_mode and ready['spec_sha256'] == sha(spec_path.read_bytes()),
            'NATIVE_BROKER_BINDING', str(folder))
    build(spec['build_manifest'])
    require(sha(Path(spec['build_manifest']).read_bytes()) == spec['build_manifest_sha256']
            and sha(Path(spec['profile']).read_bytes()) == spec['profile_sha256'], 'NATIVE_BROKER_PROFILE_DRIFT', str(folder))
    for file, digest in spec['sources'].items():
        require(sha(Path(file).read_bytes()) == digest, 'NATIVE_BROKER_SOURCE_DRIFT', file)
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(status['at'].replace('Z', '+00:00'))).total_seconds()
    require(0 <= age < 3 and status['mode'] == expected_mode and not status['stopping'], 'NATIVE_BROKER_HEARTBEAT', str(age))
    table = process_table(); identity = ready['identity']; current = table.get(identity['pid'])
    require(current and all(current[k] == identity[k] for k in ('pid', 'started_at', 'command')),
            'NATIVE_BROKER_REPLACED', str(identity['pid']))
    if expected_mode == 'astudio-owned-session':
        main = table.get(spec['main']['pid'])
        require((main is None and main_exited_ok) or main and all(main[k] == spec['main'][k] for k in ('pid', 'started_at', 'command')),
                'NATIVE_BROKER_MAIN_REPLACED', str(spec['main']['pid']))
    trusted = {identity['pid']}; controllers = []
    for session in status['sessions']:
        row = session.get('identity'); require(row, 'NATIVE_CONTROLLER_STARTING', 'Await a fresh native controller identity')
        actual = table.get(row['pid'])
        command = f"{spec['executor']} --deny-profile {spec['profile']} --audit-dir {spec['policy_audit_dir']}"
        require(actual and actual['ppid'] == identity['pid'] and actual['command'] == command
                and actual['started_at'] == row['started_at'], 'NATIVE_CONTROLLER_REPLACED', str(row['pid']))
        loaded = Path(spec['policy_audit_dir']) / f"loaded-denies-{row['pid']}.sb"
        require(loaded.is_file() and sha(loaded.read_bytes()) == spec['profile_sha256'],
                'NATIVE_CONTROLLER_PROFILE_NOT_LOADED', str(row['pid']))
        trusted.add(row['pid']); controllers.append({**actual, 'role': 'trusted_native_policy_controller',
            'pending': session['pending'], 'active_processes': session['active_processes'],
            'active_http': session.get('active_http', []), 'open_handles': session['open_handles']})
    owned = set(trusted)
    while True:
        more = {p for p, row in table.items() if row['ppid'] in owned}
        if more <= owned: break
        owned |= more
    workers = []
    protected = spec.get('synthetic_secret')
    require(expected_mode != 'astudio-owned-session' or protected is not None,
            'NATIVE_WORKER_FIXTURE_MISSING', 'Live admission requires an OS-query-only synthetic protected path')
    if protected:
        for pid in sorted(owned - trusted):
            actual = table[pid]
            checks = {op: check_policy(pid, protected, op) for op in OPERATIONS}
            if not all(x == 1 for x in checks.values()):
                # sandbox-exec has a short trusted bootstrap before applying its
                # profile. Never admit a live data worker with zero denials.
                for _ in range(10):
                    time.sleep(.02); refreshed = process_table().get(pid)
                    if refreshed is None: break
                    checks = {op: check_policy(pid, protected, op) for op in OPERATIONS}
                    if all(x == 1 for x in checks.values()): break
                else: require(False, 'NATIVE_WORKER_NOT_RESTRICTED', str(pid))
                if process_table().get(pid) is None: continue
            require(all(x == 1 for x in checks.values()), 'NATIVE_WORKER_NOT_RESTRICTED', str(pid))
            workers.append({**actual, 'synthetic_protected': checks, 'role': 'native_sandboxed_data_worker'})
    # Unknown controllers are never granted a broad out-of-tree exemption.
    for pid, row in table.items():
        if pid in owned: continue
        starts_executor = row['command'].startswith(str(ROOT / '.kernel-tools/approved') + '/') and '/acode-memory-executor ' in row['command']
        pieces = row['command'].split(None, 2)
        is_broker = len(pieces) >= 2 and pieces[1] == str(BROKER)
        require(not starts_executor and not is_broker, 'NATIVE_FOREIGN_EXECUTOR', str(pid))
    return {'status': 'PASS', 'at': timestamp(), 'mode': expected_mode, 'broker_identity': identity,
            'controllers': controllers, 'workers': workers, 'owned_pids': sorted(owned),
            'controller_state': 'live' if controllers else 'lazy_no_data_requests',
            'data_workers_enforced_by': 'frozen native SBPL plus literal controller denies, applied once'}


def require_idle(folder):
    proof = inspect(folder)
    require(all(not row['pending'] and not row['active_processes'] and not row['active_http'] for row in proof['controllers']),
            'NATIVE_EXECUTOR_ACTIVE', 'Native process, filesystem request or HTTP stream is still active')
    return proof


def stop(folder):
    proof = inspect(folder, main_exited_ok=True)
    require(all(not row['pending'] and not row['active_processes'] and not row['active_http'] for row in proof['controllers']),
            'NATIVE_EXECUTOR_ACTIVE', 'Never cancel an accepted operation to close an execution unit')
    identity = proof['broker_identity']; os.kill(identity['pid'], signal.SIGTERM)
    for _ in range(150):
        table = process_table()
        if not any(pid in table for pid in proof['owned_pids']):
            result = {'status': 'CLOSED', 'at': timestamp(), 'identity': identity, 'native_work_idle_before_close': True}
            publish(Path(folder) / 'broker-closed.json', result); return result
        time.sleep(.1)
    require(False, 'NATIVE_EXECUTOR_CLOSE_PENDING', 'Preserve the processes and observe; do not force-quit')


def selftest(folder, manifest):
    folder = Path(folder).absolute()
    require(folder.is_relative_to(machine_paths()['debug']) and folder.resolve() == folder and not folder.exists(),
            'NATIVE_EXECUTOR_FRESH_TEST', str(folder))
    folder.mkdir(parents=True, mode=0o700)
    allowed, protected = folder / 'synthetic/allowed', folder / 'synthetic/non-target'
    allowed.mkdir(parents=True); protected.mkdir()
    (protected / 'canary.txt').write_text('SYNTHETIC-PROTECTED')
    (allowed / 'control.txt').write_text('SYNTHETIC-ALLOW\n')
    (allowed / 'current.md').write_text('SYNTHETIC-CURRENT-ONE')
    (allowed / 'alias').symlink_to(protected, target_is_directory=True)
    for name in ('native-private', 'native-readonly'):
        (allowed / name).mkdir(); (allowed / name / 'fact.txt').write_text('SYNTHETIC-' + name)
    immutable = {}
    for name in ('old-case-r1', 'same-case-r1'):
        (folder / name).mkdir(); fact = folder / name / 'memory.md'; fact.write_text('SYNTHETIC-PREVIOUS-' + name)
        immutable[str(fact)] = sha(fact.read_bytes())
    immutable[str(protected / 'canary.txt')] = sha((protected / 'canary.txt').read_bytes())
    (allowed / 'old-repeat-alias').symlink_to(folder / 'same-case-r1', target_is_directory=True)
    runtime = folder / 'runtime'; runtime.mkdir(); (runtime / 'home').mkdir(); (runtime / 'tmp').mkdir()
    control = folder / 'control'; control.mkdir()
    profile = profile_text(non_target_roots() + [protected])
    with patch('eval_memory_e2e.astudio_scope.machine_paths', return_value={'debug': folder, 'acode': folder / 'ordinary-home'}):
        profile += profile_rules({'paths': {'runtime': str(runtime), 'candidate': str(allowed)}}, allowed)
    publish(control / 'profile.sb', profile.encode())
    env = dict(os.environ, MEMORY_E2E_PYTHON=sys.executable, MEMORY_E2E_REPO=str(ROOT))
    with (folder / 'client.stdout').open('xb') as out, (folder / 'client.stderr').open('xb') as err:
        client = subprocess.Popen(['node', str(PROBE), str(folder)], env=env, stdout=out, stderr=err)
    broker = None
    try:
        identity = process_table()[client.pid]
        spec = specification(control, manifest, control / 'profile.sb', mode='synthetic-admission', runtime=runtime,
                             acode_home=runtime / 'home', temp=runtime / 'tmp', test_peer=identity)
        spec['sources'][str(PROBE)] = sha(PROBE.read_bytes())
        broker, ready = start(control, spec)
        # A second process receives the valid token but must fail socket-PID binding.
        code = "const fs=require('fs'),u=JSON.parse(fs.readFileSync(process.argv[1])).url;const w=new WebSocket(u);w.onopen=()=>process.exit(9);w.onerror=()=>process.exit(0);w.onclose=()=>process.exit(0);setTimeout(()=>process.exit(8),3000).unref()"
        foreign = subprocess.run(['node', '-e', code, str(control / 'broker-ready.json')], capture_output=True, timeout=5)
        publish(folder / 'foreign-peer.json', {'returncode': foreign.returncode, 'pass': foreign.returncode == 0})
        code = client.wait(timeout=120)
        result = read_json(folder / 'probe-result.json') if (folder / 'probe-result.json').exists() else {'pass': False}
        audits = [read_json(p) for p in (control / 'policies').glob('policy-*.json')]
        denies = profile.removeprefix('(version 1)\n(allow default)\n')
        audit_pass = bool(audits) and all(a['combined_profile'] == a['native_profile'] + '\n; immutable controller deny boundary\n' + denies
                                         and a['controller_grants_appended'] is False for a in audits)
        loaded = list((control / 'policies').glob('loaded-denies-*.sb'))
        loaded_pass = bool(loaded) and all(sha(p.read_bytes()) == sha(profile.encode()) for p in loaded)
        old_pass = all(sha(Path(p).read_bytes()) == digest for p, digest in immutable.items())
        final = {'contract': 'astudio-composed-native-selftest/v2', 'at': timestamp(),
                 'status': 'PASS' if code == 0 and result['pass'] and audit_pass and loaded_pass and old_pass and foreign.returncode == 0 else 'FAIL',
                 'build_manifest': str(Path(manifest).absolute()), 'build_manifest_sha256': sha(Path(manifest).read_bytes()),
                 'native_policy_audits': len(audits), 'original_native_sbpl_preserved': audit_pass,
                 'loaded_controller_profile_matches': loaded_pass, 'old_fixture_hashes': immutable, 'old_fixtures_unchanged': old_pass,
                 'model_prompts': 0, 'real_non_target_data_attempted': False, 'application_automatic_consolidation_verified': False}
        publish(folder / 'selftest.json', final)
        return final
    finally:
        if client.poll() is None:
            client.terminate(); client.wait(timeout=10)
        if broker is not None:
            broker.terminate()
            try: broker.wait(timeout=15)
            except subprocess.TimeoutExpired:
                publish(folder / 'closeout-needs-attention.json', {'at': timestamp(), 'broker_pid': broker.pid,
                         'reason': 'refused shutdown or controller still active; do not launch an application'})
        publish(folder / 'closeout.json', {'at': timestamp(), 'client_pid': client.pid, 'client_exit': client.returncode,
                'broker_pid': broker.pid if broker else None, 'broker_exit': broker.returncode if broker else None})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['selftest'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(selftest(args.output, args.build_manifest), ensure_ascii=False))


if __name__ == '__main__':
    main()
