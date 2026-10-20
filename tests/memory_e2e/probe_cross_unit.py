"""Live synthetic-only cross-unit denial probe; never opens ordinary memory.

Run from the repository with the admitted Python. All previous inputs must be
owned memory-e2e units. This is an environment probe, not a capability score.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval_memory_e2e.astudio_scope import freeze, load, attest
from eval_memory_e2e.os_boundary import frozen_boundary, check_policy, OPERATIONS
from eval_memory_e2e.io import read_json, publish, require, sha, timestamp
from eval_memory_e2e.machine import machine_paths

parser = argparse.ArgumentParser()
parser.add_argument('--scope', type=Path, required=True)
parser.add_argument('--lease', type=Path, required=True)
parser.add_argument('--previous-batch', type=Path, action='append', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
current = load(args.scope)
boundary = frozen_boundary(args.lease)
proof = attest(freeze(args.scope), boundary)
debug = machine_paths()['debug']
old = []
for batch in args.previous_batch:
    require(batch.is_relative_to(debug) and batch.resolve() == batch, 'CROSS_UNIT_INPUT', str(batch))
    manifest = read_json(batch / 'manifest.json')
    scope = manifest['profiles']['AstronStudio']['astudio_scope']
    require(scope['unit_id'] != current['unit_id'] and scope['paths']['runtime'] != current['paths']['runtime'],
            'CROSS_UNIT_SAME_STORE', str(batch))
    old_runtime = Path(scope['paths']['runtime'])
    require(old_runtime.is_relative_to(debug) and old_runtime.resolve() == old_runtime, 'CROSS_UNIT_INPUT', str(old_runtime))
    facts = [case['facts']['own_value'] for case in read_json(batch / 'private/scenarios.json').values()]
    matches = []
    notes = Path(scope['paths']['overlay']) / 'memories/extensions/ad_hoc/notes'
    for path in notes.glob('*.md'):
        require(path.resolve() == path and path.is_relative_to(old_runtime), 'CROSS_UNIT_INPUT', str(path))
        data = path.read_bytes()
        if any(value.encode() in data for value in facts):
            matches.append({'path': str(path), 'sha256': sha(data), 'size': len(data)})
    require(matches, 'CROSS_UNIT_POSITIVE_PREREQUISITE', 'First round must have real synthetic native memory')
    old.extend(matches)

allowed = args.lease.parent / 'synthetic/allowed'
aliases = []
for index, row in enumerate(old):
    alias = allowed / ('old-unit-alias-' + str(index) + '-' + uuid4().hex)
    alias.symlink_to(row['path'])
    aliases.append(str(alias))
fixture = {'old': old, 'aliases': aliases, 'control': str(allowed / 'control.txt')}
probe = r'''
import json,sys,errno
from pathlib import Path
d=json.loads(sys.argv[1]);rows=[]
for item,alias in zip(d['old'],d['aliases']):
 p=Path(item['path'])
 for name,call in [('read',lambda:p.read_bytes()),('stat',lambda:p.stat()),
                   ('list',lambda:list(p.parent.iterdir())),('alias_read',lambda:Path(alias).read_bytes()),
                   ('write_outside_unit',lambda:(p.parent/'cross-unit-negative-write').write_text('SYNTHETIC'))]:
  try: call(); rows.append({'path':str(p),'operation':name,'denied':False})
  except OSError as e: rows.append({'path':str(p),'operation':name,'denied':e.errno in (errno.EPERM,errno.EACCES),'errno':e.errno})
control=Path(d['control']).read_text().strip()=='SYNTHETIC-ALLOW'
print(json.dumps({'pass':control and all(r['denied'] for r in rows),'positive_control':control,'operations':rows}))
'''
result = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(args.lease.parent / 'control/profile.sb'),
                         sys.executable, '-c', probe, json.dumps(fixture)], capture_output=True, text=True, timeout=30)
require(result.returncode == 0, 'CROSS_UNIT_PROBE_PROCESS', result.stderr[-1000:])
observed = json.loads(result.stdout)
require(observed['pass'], 'CROSS_UNIT_DENIAL_FAILED', 'An actual old synthetic note was accessible')
policies = []
for process in proof['execution_roots']:
    for row in old:
        checks = {op: check_policy(process['pid'], row['path'], op) for op in OPERATIONS}
        require(all(x == 1 for x in checks.values()), 'CROSS_UNIT_ACTUAL_POLICY', str(process['pid']))
        policies.append({'pid': process['pid'], 'path': row['path'], 'denials': checks})
require(all(sha(Path(row['path']).read_bytes()) == row['sha256'] for row in old),
        'CROSS_UNIT_OLD_FACT_CHANGED', 'Previous synthetic notes must survive unchanged')
receipt = {'status': 'PASS', 'at': timestamp(), 'unit_id': current['unit_id'],
           'current_account_fingerprint': current['account_fingerprint'], 'old_synthetic_notes': old,
           'filesystem_probe': observed, 'actual_backend_kernel_policy': policies,
           'ordinary_memory_probed': False, 'source_sha256': sha(Path(__file__).read_bytes())}
publish(args.output, receipt)
print(json.dumps({'status': 'PASS', 'old_notes': len(old), 'filesystem_checks': len(observed['operations']),
                  'actual_process_checks': len(policies) * len(OPERATIONS), 'output': str(args.output)}))
