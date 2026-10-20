"""Synthetic-only admission research for nested AStudio Seatbelt execution.

No model, account, ordinary memory or desktop instance is used. This does not
create a boundary lease and cannot enable automatic-generation model sends.
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from .io import publish, require, sha, timestamp
from .machine import machine_paths, kernel_identity
from .os_boundary import process_table, check_policy
from .native_sandbox import intersect_permissions, native_path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'eval_memory_e2e/native'


def counterexample(folder):
    """Retain an actual failed isolation result, rather than relabeling it pass."""
    folder = Path(folder).absolute()
    require(folder.is_relative_to(machine_paths()['debug']) and folder.resolve() == folder
            and not folder.exists(), 'NATIVE_PROBE_FRESH_PATH', str(folder))
    folder.mkdir(parents=True, mode=0o700)
    workspace, denied = folder / 'workspace', folder / 'non-target'
    workspace.mkdir(); denied.mkdir()
    fact = denied / 'memory.md'; fact.write_text('SYNTHETIC-ONLY-PREVIOUS-ROUND')
    before = sha(fact.read_bytes())
    alias = workspace / 'alias'; alias.symlink_to(denied, target_is_directory=True)
    home, temp = folder / 'native-home', folder / 'tmp'; home.mkdir(); temp.mkdir()
    env = dict(os.environ, ACODE_HOME=str(home), TMPDIR=str(temp) + '/', PYTHONDONTWRITEBYTECODE='1')
    rows = []
    from unittest.mock import patch
    with patch.dict(os.environ, ACODE_HOME=str(home), TMPDIR=str(temp) + '/'):
        witness = kernel_identity()
    for access in ('read', 'write'):
        native = {'type': 'managed', 'network': 'restricted', 'file_system': {'type': 'restricted', 'entries': [
            {'path': {'type': 'path', 'path': p.as_uri()}, 'access': mode}
            for p, mode in [(Path('/'), 'read'), (workspace, 'write'), (alias, access)]]}}
        combined = intersect_permissions(native, [('/', 'read'), (str(workspace), 'write'), (str(denied), 'none')])
        state = {'permissionProfile': json.loads(json.dumps(combined)), 'sandboxCwd': workspace.as_uri()}
        # CLI permissionProfile uses native paths; exec-server uses file URIs.
        for entry in state['permissionProfile']['file_system']['entries']:
            entry['path']['path'] = native_path(entry['path']['path'])
        code = "import json,sys;from pathlib import Path;rows=[]\nfor p in sys.argv[1:]:\n try:Path(p).read_bytes();rows.append({'path':p,'denied':False})\n except OSError as e:rows.append({'path':p,'denied':True,'errno':e.errno})\nprint(json.dumps(rows))"
        proc = subprocess.run([witness['path'], 'sandbox', '--sandbox-state-json', json.dumps(state), '--',
                               sys.executable, '-c', code, str(alias / 'memory.md'), str(fact)],
                              env=env, capture_output=True, timeout=20)
        observed = json.loads(proc.stdout) if proc.returncode == 0 else []
        rows.append({'native_alias_grant': access, 'original_native_policy': native, 'combined_policy': combined,
                     'returncode': proc.returncode, 'observed': observed, 'stderr': proc.stderr.decode(),
                     'isolation_pass': bool(observed) and all(x['denied'] for x in observed)})
    unexpected = sum(not item['denied'] for row in rows for item in row['observed'])
    status = 'FAIL_ISOLATION_PREFIX_INTERSECTION' if unexpected else (
        'COUNTEREXAMPLE_NOT_REPRODUCED' if all(x['isolation_pass'] for x in rows) else 'PROBE_ERROR')
    result = {'status': status,
              'at': timestamp(), 'kernel': witness, 'cases': rows, 'actual_denial_attempts': sum(len(x['observed']) for x in rows),
              'unexpected_reads': unexpected,
              'protected_fixture_unchanged': before == sha(fact.read_bytes()),
              'real_non_target_paths_attempted': False, 'model_prompts': 0, 'security_admitted': False,
              'automatic_consolidation_admitted': False, 'formal20_started': False}
    publish(folder / 'result.json', result)
    return {k: v for k, v in result.items() if k != 'cases'}


def run(folder, ancestor_deny=False):
    folder = Path(folder).absolute()
    require(folder.is_relative_to(machine_paths()['debug']) and folder.resolve() == folder
            and not folder.exists(), 'NATIVE_PROBE_FRESH_PATH', str(folder))
    folder.mkdir(parents=True, mode=0o700)
    fixture = folder / 'fixture'; fixture.mkdir()
    for rel in ['workspace', 'workspace/readonly', 'workspace/private', 'non-target', 'other-runtime']:
        dest = fixture / rel; dest.mkdir(); (dest / 'fact.txt').write_text('SYNTHETIC-' + rel)
    (fixture / 'workspace/alias').symlink_to(fixture / 'non-target', target_is_directory=True)
    for name in ('acode-home', 'tmp'):
        (folder / name).mkdir()
    secret = fixture / 'non-target/fact.txt'; before = sha(secret.read_bytes())
    bundle = ROOT / 'tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/node_modules/playwright-core/lib/utilsBundle.js'
    node = subprocess.check_output(['which', 'node'], text=True).strip()
    kernel = kernel_identity()
    files = [Path(__file__).resolve(), ROOT / 'eval_memory_e2e/native_sandbox.py', ROOT / 'eval_memory_e2e/io.py',
             NATIVE / 'astudio-exec-proxy.mjs', NATIVE / 'astudio-native-exec-probe.mjs']
    snapshots = folder / 'source-snapshot'; snapshots.mkdir()
    for source in files:
        publish(snapshots / source.name, source.read_bytes())
    env = dict(os.environ, MEMORY_E2E_PYTHON=sys.executable)
    proxy = client = None
    checks, owned, negatives = [], set(), []
    try:
        with (folder / 'client.stdout').open('xb') as out, (folder / 'client.stderr').open('xb') as err:
            client = subprocess.Popen([node, str(NATIVE / 'astudio-native-exec-probe.mjs'), str(folder)], env=env, stdout=out, stderr=err)
        identity = process_table()[client.pid]
        mandatory = [('/', 'read')]
        if ancestor_deny:
            mandatory += [(str(fixture), 'none'), ('/System/Volumes/Data' + str(fixture), 'none')]
        for path, access in [(fixture / 'workspace', 'write'), (fixture / 'other-runtime', 'write'), (fixture / 'non-target', 'none')]:
            mandatory += [(str(path), access), ('/System/Volumes/Data' + str(path), access)]
        spec = {'contract': 'astudio-native-exec-experiment/v1', 'python': sys.executable,
                'synthetic_only': True, 'application_integration_allowed': False,
                'kernel': kernel['path'], 'kernel_witness': kernel,
                'sources': {str(p): sha(p.read_bytes()) for p in files},
                'bundle_sha256': sha(bundle.read_bytes()), 'bundle_impl_sha256': sha((bundle.parent / 'utilsBundleImpl/index.js').read_bytes()),
                'runtime': str(folder), 'acode_home': str(folder / 'acode-home'), 'temp': str(folder / 'tmp'),
                'token_path': '/' + secrets.token_hex(32),
                'diagnostic_peer': {'pid': client.pid, 'started': identity['started_at'], 'command': identity['command']}, 'mandatory': mandatory}
        spec_path = folder / 'proxy-spec.json'; publish(spec_path, spec); spec_path.chmod(0o600)
        with (folder / 'proxy.stdout').open('xb') as out, (folder / 'proxy.stderr').open('xb') as err:
            proxy = subprocess.Popen([node, str(NATIVE / 'astudio-exec-proxy.mjs'), str(spec_path)], stdout=out, stderr=err)
        deadline = time.monotonic() + 45
        negative_sent = False
        while time.monotonic() < deadline and client.poll() is None:
            ready = folder / 'proxy-ready.json'
            if ready.exists() and not negative_sent:
                # This second process knows the exact token but has the wrong
                # socket owner PID; denial must precede all native operations.
                code = "const fs=require('fs'),u=JSON.parse(fs.readFileSync(process.argv[1])).url;const w=new WebSocket(u);w.onopen=()=>process.exit(9);w.onerror=()=>process.exit(0);w.onclose=()=>process.exit(0);setTimeout(()=>process.exit(8),3000).unref()"
                wrong = subprocess.run([node, '-e', code, str(ready)], capture_output=True, timeout=5)
                negatives.append({'test': 'valid-token-wrong-peer-pid', 'returncode': wrong.returncode, 'pass': wrong.returncode == 0})
                negative_sent = True
            table = process_table()
            for pid, row in table.items():
                if pid in owned or not row['command'].startswith(sys.executable + ' -c import os,json,sys,time,socket'):
                    continue
                ancestor = row
                while ancestor and ancestor['pid'] != proxy.pid:
                    ancestor = table.get(ancestor['ppid'])
                if not ancestor:
                    continue
                owned.add(pid)
                policies = {name: check_policy(pid, path, op) for name, path, op in [
                    ('outer_denied_read', secret, 'file-read-data'), ('outer_denied_metadata', secret, 'file-read-metadata'),
                    ('native_private_read', fixture / 'workspace/private/fact.txt', 'file-read-data'),
                    ('native_readonly_write', fixture / 'workspace/readonly/new', 'file-write-data'),
                    ('allowed_read', fixture / 'workspace/fact.txt', 'file-read-data'),
                    ('allowed_write', fixture / 'workspace/new', 'file-write-data')]}
                checks.append({'worker_pid': pid, 'worker_started_at': row['started_at'], 'policies': policies,
                               'pass': list(policies.values()) == [1, 1, 1, 1, 0, 0]})
            time.sleep(.1)
        require(client.poll() is not None, 'NATIVE_PROBE_TIMEOUT', 'Synthetic client did not finish')
        publish(folder / 'worker-os-checks.json', checks)
        publish(folder / 'negative-peers.json', negatives)
        probe = json.loads((folder / 'probe-result.json').read_text())
        functional = bool(probe['pass'] and checks and all(x['pass'] for x in checks + negatives))
        result = {'status': 'NOT_ADMITTED', 'functional_checks_pass': functional,
                  'security_admitted': False, 'blocker': 'native canonicalization can reopen a denied symlink target',
                  'at': timestamp(), 'kernel': kernel, 'ancestor_deny': ancestor_deny,
                  'protocol_checks': len(probe['rows']), 'filesystem_checks': len(probe.get('matrix', {}).get('results', [])),
                  'os_policy_checks': len(checks) * 6, 'negative_peer_checks': len(negatives),
                  'protected_fixture_unchanged': sha(secret.read_bytes()) == before,
                  'model_prompts': 0, 'real_non_target_paths_attempted': False,
                  'automatic_consolidation_admitted': False, 'formal20_started': False}
        publish(folder / 'result.json', result)
        return result
    finally:
        forced = []
        for role, child in [('client', client), ('proxy', proxy)]:
            if child is None or child.poll() is not None:
                continue
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Synthetic diagnostic processes only; never native memory jobs
                # or previously accepted/unknown model operations.
                forced.append(role); child.kill(); child.wait(timeout=5)
        table = process_table()
        publish(folder / 'closeout.json', {'at': timestamp(), 'client_pid': client.pid if client else None,
                'client_exit': client.returncode if client else None, 'proxy_pid': proxy.pid if proxy else None,
                'proxy_exit': proxy.returncode if proxy else None, 'forced_synthetic_processes': forced,
                'remaining_owned_processes': [r for p, r in table.items() if p in owned or proxy and r['ppid'] == proxy.pid]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ancestor-deny', action='store_true')
    parser.add_argument('--symlink-counterexample', action='store_true')
    args = parser.parse_args()
    result = counterexample(args.output) if args.symlink_counterexample else run(args.output, args.ancestor_deny)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
