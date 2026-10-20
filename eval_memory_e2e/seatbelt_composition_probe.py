"""Actual OS probes for single-application SBPL composition, synthetic only.

The native side here is an explicit synthetic deny-default policy, not an
unobserved AStudio Phase-2 policy. Passing cannot admit automatic memories.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from .astudio_scope import profile_rules
from .io import publish, require, sha, timestamp
from .machine import machine_paths, kernel_identity
from .os_boundary import profile_text, SELF, APP
from .seatbelt_composition import compose


def run(folder):
    folder = Path(folder).absolute()
    require(folder.is_relative_to(machine_paths()['debug']) and folder.resolve() == folder and not folder.exists(),
            'COMPOSITE_FRESH_PATH', str(folder))
    folder.mkdir(parents=True, mode=0o700)
    protected, allowed = folder / 'synthetic/non-target', folder / 'synthetic/allowed'
    protected.mkdir(parents=True); allowed.mkdir()
    secret, control = protected / 'canary.txt', allowed / 'control.txt'
    secret.write_text('SYNTHETIC-DENY\n'); control.write_text('SYNTHETIC-ALLOW\n')
    (allowed / 'alias').symlink_to(protected, target_is_directory=True)
    runtime = folder / 'unit-runtime'; runtime.mkdir()
    for name in ('native-home', 'tmp'):
        (runtime / name).mkdir()
    for name in ('native-private', 'native-readonly'):
        (allowed / name).mkdir(); (allowed / name / 'fact.txt').write_text('SYNTHETIC-' + name)
    old_hashes = {}
    for name in ('old-case-r1', 'same-case-r1'):
        previous = folder / name; previous.mkdir()
        (previous / 'memory.md').write_text('SYNTHETIC-SAME-PROJECT-PREVIOUS-' + name)
        old_hashes[name] = sha((previous / 'memory.md').read_bytes())
        (allowed / (name + '-alias')).symlink_to(previous, target_is_directory=True)
    (allowed / 'existing.txt').write_text('SYNTHETIC-EXISTING')
    before = sha(secret.read_bytes())
    native = ('(version 1)\n(deny default)\n'
              '(allow process-exec process-fork)\n'
              '(allow signal (target same-sandbox))\n'
              '(allow process-info* (target same-sandbox))\n'
              '(allow sysctl-read)\n(allow mach-lookup)\n(allow file-read*)\n'
              '(allow file-write* (subpath ' + json.dumps(str(allowed)) + '))\n'
              '(allow file-write-data (literal "/dev/null"))\n'
              '(deny file-read* file-write* (subpath ' + json.dumps(str(allowed / 'native-private')) + '))\n'
              '(deny file-write* (subpath ' + json.dumps(str(allowed / 'native-readonly')) + '))\n'
              # An explicit native grant must not reopen the outer deny, even
              # when its source path was a symlink normalized to this target.
              '(allow file-read* (subpath ' + json.dumps(str(protected)) + '))\n')
    outer = profile_text([protected])
    with patch('eval_memory_e2e.astudio_scope.machine_paths', return_value={
            'debug': folder, 'acode': folder / 'ordinary-native-home'}):
        outer += profile_rules({'paths': {'runtime': str(runtime), 'candidate': str(allowed)}}, allowed)
    composed = compose(native, sha(native.encode()), outer, sha(outer.encode()))
    controls = folder / 'control'; controls.mkdir()
    for name, text in [('native.sb', native), ('outer.sb', outer), ('composed.sb', composed['profile'])]:
        publish(controls / name, text.encode())
    publish(controls / 'composition.json', {k: v for k, v in composed.items() if k != 'profile'})
    env = dict(os.environ, ACODE_HOME=str(runtime / 'native-home'), TMPDIR=str(runtime / 'tmp') + '/', PYTHONDONTWRITEBYTECODE='1')
    prefix = ['/usr/bin/sandbox-exec', '-f', str(controls / 'composed.sb')]
    commands = [prefix + [sys.executable, str(SELF), '_fixture-probe', '--lease-dir', str(folder)]]
    node_code = "const fs=require('fs');fs.realpathSync(process.argv[1]+'/synthetic/allowed/control.txt');const p=require('child_process').spawnSync(process.argv[2],[process.argv[3],'_fixture-probe','--lease-dir',process.argv[1]],{encoding:'utf8'});process.stdout.write(p.stdout);process.stderr.write(p.stderr);process.exit(p.status??1)"
    commands += [prefix + [APP, '-e', node_code, str(folder), sys.executable, str(SELF)]]
    fixtures = []
    for index, command in enumerate(commands):
        actual_env = dict(env, ELECTRON_RUN_AS_NODE='1') if index else env
        proc = subprocess.run(command, env=actual_env, capture_output=True, timeout=30)
        publish(folder / f'fixture-{index}.stdout', proc.stdout); publish(folder / f'fixture-{index}.stderr', proc.stderr)
        probe = json.loads(proc.stdout) if proc.returncode == 0 else None
        fixtures.append({'argv': command, 'returncode': proc.returncode, 'pass': bool(probe and probe['pass']), 'probe': probe})
    listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen()
    try:
        code = '''import json,sys,socket,os\nfrom pathlib import Path\nfrom eval_memory_e2e.os_boundary import check_policy\np=Path(sys.argv[1]);rows=[]\ntests=[('native-private-read',lambda:(p/'synthetic/allowed/native-private/fact.txt').read_bytes(),True),('native-readonly-write',lambda:(p/'synthetic/allowed/native-readonly/fact.txt').write_text('bad'),True),('native-outside-write',lambda:(p/'unit-runtime/escape').write_text('bad'),True),('allowed-existing-write',lambda:(p/'synthetic/allowed/existing.txt').write_text('SYNTHETIC-NEW'),False),('ancestor-metadata',lambda:p.stat(),False),('ancestor-enumeration',lambda:list(p.iterdir()),True),('outer-deny-after-native-grant',lambda:(p/'synthetic/non-target/canary.txt').read_bytes(),True),('network-restricted',lambda:socket.create_connection(('127.0.0.1',int(sys.argv[2])),timeout=2),True)]\nfor name in ('old-case-r1','same-case-r1'):\n old=p/name\n tests += [(name+'-read',lambda old=old:(old/'memory.md').read_bytes(),True),(name+'-stat',lambda old=old:(old/'memory.md').stat(),True),(name+'-enumerate',lambda old=old:list(old.iterdir()),True),(name+'-write',lambda old=old:(old/'memory.md').write_text('bad'),True),(name+'-alias',lambda name=name:(p/'synthetic/allowed'/(name+'-alias')/'memory.md').read_bytes(),True)]\nfor label,fn,denied in tests:\n try:fn();rows.append({'test':label,'denied':False,'pass':not denied})\n except OSError as e:rows.append({'test':label,'denied':True,'errno':e.errno,'pass':denied and e.errno in (1,13)})\npolicies=[]\nfor rel,op,want in [('synthetic/allowed/control.txt','file-read-data',0),('synthetic/allowed/existing.txt','file-write-data',0),('synthetic/non-target/canary.txt','file-read-data',1),('old-case-r1/memory.md','file-read-metadata',1),('same-case-r1/memory.md','file-read-data',1),('synthetic/allowed/native-readonly/fact.txt','file-write-data',1)]:\n got=check_policy(os.getpid(),p/rel,op);policies.append({'path':rel,'operation':op,'actual':got,'expected':want,'pass':got==want})\nprint(json.dumps({'results':rows,'os_policy':policies}))\n'''
        proc = subprocess.run(prefix + [sys.executable, '-c', code, str(folder), str(listener.getsockname()[1])], env=env, capture_output=True, timeout=20)
    finally:
        listener.close()
    publish(folder / 'native-restrictions.stdout', proc.stdout); publish(folder / 'native-restrictions.stderr', proc.stderr)
    detail = json.loads(proc.stdout) if proc.returncode == 0 else {'results': [], 'os_policy': []}
    restrictions, os_checks = detail['results'], detail['os_policy']
    # Preserve a same-machine reproduction of the original mechanism.
    nested = subprocess.run(['/usr/bin/sandbox-exec', '-p', outer, '/usr/bin/sandbox-exec', '-p', native,
                             '/bin/cat', str(control)], env=env, capture_output=True, timeout=20)
    publish(folder / 'nested.stdout', nested.stdout); publish(folder / 'nested.stderr', nested.stderr)
    def count(probe):
        return len(probe['results']) + sum(count(x) for x in probe.get('children', [])) if probe else 0
    retained = all(sha((folder / name / 'memory.md').read_bytes()) == digest for name, digest in old_hashes.items())
    restrictions_pass = len(restrictions) == 18 and len(os_checks) == 6 and all(x['pass'] for x in restrictions + os_checks)
    result = {'status': 'PASS_SYNTHETIC_SBPL_COMPOSITION' if all(x['pass'] for x in fixtures)
              and restrictions_pass and sha(secret.read_bytes()) == before and retained else 'FAIL',
              'at': timestamp(), 'kernel': kernel_identity(), 'fixtures': fixtures,
              'filesystem_checks': sum(count(x['probe']) for x in fixtures), 'native_restrictions': restrictions,
              'os_policy_checks': os_checks, 'old_memory_fixture_hashes': old_hashes, 'old_memory_fixtures_retained': retained,
              'native_and_outer_restrictions_retained': restrictions_pass,
              'nested_returncode': nested.returncode, 'nested_sandbox_apply_failed': b'sandbox_apply: Operation not permitted' in nested.stderr,
              'single_sandbox_installation': True, 'native_policy_source': 'explicit synthetic deny-default fixture',
              'real_non_target_paths_attempted': False, 'model_prompts': 0,
              'automatic_consolidation_admitted': False, 'formal20_started': False,
              'blocker': 'installed kernel has no admitted generated-SBPL composition hook'}
    publish(folder / 'result.json', result)
    return {k: v for k, v in result.items() if k not in ('fixtures', 'native_restrictions')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
