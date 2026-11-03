"""Recover unjudged Office audit copies from the SHA-locked execution ZIP.

Explicit maintenance only. Preserve mutated files; never accept new hashes,
change candidates, change manifests, or relax normal trace verification.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile
from source_office_metadata import office_delta

PROFILE = 'wildclawbench.trace-office-canonical-recovery/v1'

def sha(data): return hashlib.sha256(data).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def require(value, message):
    if not value: raise ValueError(message)

def inside(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), 'relative path required')
    path = root / relative
    require(not any(p in ('.', '..') for p in relative.split('/')), 'unsafe path')
    require(path.resolve().is_relative_to(root.resolve()), 'path escapes root')
    current = path
    while current != root:
        require(not current.is_symlink(), 'symlink not allowed')
        current = current.parent
    return path

def seal(path):
    if hasattr(os, 'chflags'):
        os.chflags(path, path.stat().st_flags | stat.UF_IMMUTABLE, follow_symlinks=False)

def write_new(path, data, *, protect=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle: handle.write(data)
    if protect: seal(path)

def recover(unit_root, orchestration_root, execution_zip, output_root):
    unit, orchestration = Path(unit_root).resolve(), Path(orchestration_root).resolve()
    output, archive = Path(output_root).absolute(), Path(execution_zip).resolve()
    require(output.resolve().is_relative_to(unit / 'evidence/trace-office-recoveries'), 'recovery output namespace')
    require(not output.exists(), 'recovery output exists; inspect intent before resuming')
    require(not any(p.is_symlink() for p in [output, *output.parents]), 'recovery output symlink')
    state_path = orchestration / 'orchestration-state.json'
    state_bytes = state_path.read_bytes(); state = json.loads(state_bytes)
    manifest_bytes = (unit / 'manifest.json').read_bytes(); manifest = json.loads(manifest_bytes)
    require(sha(manifest_bytes) == state['sources']['unit_manifest_sha256'], 'unit manifest drift')
    lock = load(unit / '.general-e2e/round-unit.json')
    package_bytes = archive.read_bytes()
    require(sha(package_bytes) == lock['execution_sha256'], 'execution ZIP drift')
    targets, seals = [], []
    with zipfile.ZipFile(archive) as package:
        names = package.namelist(); require(len(names) == len(set(names)), 'duplicate ZIP member')
        manifests = [n for n in names if n.endswith('manifest.json') and package.getinfo(n).file_size == len(manifest_bytes) and package.read(n) == manifest_bytes]
        require(len(manifests) == 1, 'execution manifest not unique')
        prefix = manifests[0][:-len('manifest.json')]
        task_sources = {t['task_id']: t for t in manifest['tasks']}
        for task in state['tasks']:
            execution = load(inside(orchestration, task['execution_record_path']))
            require(sha(inside(orchestration, task['execution_record_path']).read_bytes()) == task['execution_record_sha256'], 'execution record drift')
            index_path = inside(unit, execution['evidence']['trace_index_path'])
            index = load(index_path)
            attempt = inside(orchestration, task['attempt_path'])
            am_bytes = (attempt / 'attempt-manifest.json').read_bytes(); am = json.loads(am_bytes)
            require(sha(am_bytes) == task['attempt_manifest_sha256'], 'attempt manifest drift')
            bundle_path = inside(attempt, am['trace_bundle']['path'])
            require(sha(bundle_path.read_bytes()) == am['trace_bundle']['sha256'], 'bundle manifest drift')
            bundle = load(bundle_path)
            score_refs = {r['path']: r for r in bundle['artifacts']}
            for ref in index.get('binding_evidence', []):
                if not ref['path'].endswith('.bin'): continue
                require(score_refs.get(ref['path']) == ref, 'trace reference mismatch')
                for root in (index_path.parent, bundle_path.parent):
                    path = inside(root, ref['path']); raw = path.read_bytes()
                    if sha(raw) == ref['sha256'] and len(raw) == ref['size']:
                        seals.append(path); continue
                    require(ref['path'].endswith('-original.bin'), 'only canonical original copies can be recovered')
                    require(task['phase'] == 'RULES_READY' and task.get('thread') is None and task.get('project') is None and task.get('preflight') is None and task.get('score') is None, 'affected task already started')
                    require(not (attempt / 'score.json').exists() and not (attempt / 'rule-worker').exists() and not (attempt / 'rule-score.json').exists(), 'affected task has scoring artifacts')
                    source = task_sources[task['task_id']]
                    matches = []
                    for entry in source['workspace']['entries']:
                        if entry.get('kind') == 'file' and entry['sha256'] == ref['sha256'] and entry['size'] == ref['size']:
                            member = prefix + source['workspace']['path'] + '/' + entry['path']
                            info = package.getinfo(member)
                            require(not stat.S_ISLNK(info.external_attr >> 16), 'ZIP symlink')
                            canonical = package.read(member)
                            if sha(canonical) == ref['sha256'] and len(canonical) == ref['size']: matches.append((member, canonical))
                    require(len(matches) == 1, 'canonical task input not unique')
                    member, canonical = matches[0]
                    delta = office_delta(canonical, raw)
                    targets.append({'path': path, 'before': raw, 'canonical': canonical, 'task_id': task['task_id'], 'zip_member': member, 'delta': delta})
    require(targets, 'no eligible drift')
    require(state_path.read_bytes() == state_bytes, 'orchestration changed during recovery planning')
    for item in targets: require(item['path'].read_bytes() == item['before'], 'copy changed during recovery planning')
    output.mkdir(parents=True)
    summary = {'profile': PROFILE, 'at': datetime.now(timezone.utc).isoformat(), 'execution_zip': str(archive), 'execution_zip_sha256': sha(package_bytes), 'orchestration_state_sha256': sha(state_bytes), 'copies': []}
    for ordinal, item in enumerate(targets):
        variant = output / ('variants/%03d.bin' % ordinal)
        write_new(variant, item['before'])
        summary['copies'].append({'path': str(item['path']), 'task_id': item['task_id'], 'variant': str(variant), 'variant_sha256': sha(item['before']), 'canonical_sha256': sha(item['canonical']), 'canonical_zip_member': item['zip_member'], 'office_delta': item['delta']})
    write_new(output / 'intent.json', (json.dumps(summary, ensure_ascii=False, indent=2)+'\n').encode())
    for ordinal, item in enumerate(targets):
        path = item['path']; require(path.read_bytes() == item['before'], 'copy changed before recovery')
        require(not path.stat().st_flags & stat.UF_IMMUTABLE if hasattr(os, 'chflags') else True, 'unexpected immutable drift')
        temporary = path.with_name(path.name + '.canonical-recovery')
        write_new(temporary, item['canonical'], protect=False)
        # Rename the existing file into the audit tree; never discard its bytes.
        path.rename(output / ('original-location-%03d.bin' % ordinal))
        seal(output / ('original-location-%03d.bin' % ordinal))
        temporary.rename(path)
        seal(path)
        require(sha(path.read_bytes()) == sha(item['canonical']), 'canonical recovery drift')
    for path in seals: seal(path)
    require(state_path.read_bytes() == state_bytes, 'orchestration changed during recovery')
    summary.update(status='PASS', manifests_modified=False, candidates_modified=False, scores_modified=False)
    write_new(output / 'receipt.json', (json.dumps(summary, ensure_ascii=False, indent=2)+'\n').encode())
    return summary

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('unit-root', 'orchestration-root', 'execution-zip', 'output-root'): parser.add_argument('--'+flag, required=True)
    args = parser.parse_args()
    print(json.dumps(recover(args.unit_root, args.orchestration_root, args.execution_zip, args.output_root), ensure_ascii=False, indent=2))
