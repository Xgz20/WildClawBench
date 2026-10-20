"""Private, read-only store observations; text presence is not semantic scoring."""
import os
from pathlib import Path
from uuid import uuid4

from . import HARNESS_PORTS
from .io import append, digest, events, publish, read_json, require, safe_file, sha, timestamp

from .machine import machine_paths

PATHS = machine_paths()
STORE_ROOTS = {
    'AstronStudio': (PATHS['overlay'] / 'memories',
                    PATHS['overlay'] / 'memories_extensions'),
    'QwenWork': (PATHS['qwen_trace'] / 'awareness/main',),
    'WorkBuddy': (PATHS['workbuddy'] / 'memory',),
    'DoubaoWork': (),
}


def capture_state(root, request, stage):
    """Observe only the evaluated client's known memory stores, never Codex."""
    require(request.get('harness') in HARNESS_PORTS, 'OBSERVATION_SCOPE', 'Only the four evaluated clients')
    root = Path(root)
    manifest = read_json(root / 'manifest.json')
    if manifest['mode'] != 'native' or request.get('action') != 'execute_step' or not manifest['profiles'][request['harness']].get('state_observation', False):
        return None
    episode = next(item for item in manifest['episodes'] if item['id'] == request['episode_id'])
    facts = read_json(root / 'private/scenarios.json')[episode['private_key']].get('facts', {})
    folder = root / 'private/memory-state'
    folder.mkdir(mode=0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    files, total, error = [], 0, None
    roots = STORE_ROOTS[request['harness']]
    workbuddy_base = PATHS['workbuddy']
    if request['harness'] == 'WorkBuddy' and manifest['profiles']['WorkBuddy'].get('workbuddy_scope'):
        from .workbuddy_scope import load
        unit = manifest['profiles']['WorkBuddy']['workbuddy_scope']
        workbuddy_base = Path(load(unit['scope'], unit)['app_home'])
        roots = (workbuddy_base / 'memories', workbuddy_base / 'memory', workbuddy_base / 'agent-memory')
        project_root = workbuddy_base / 'projects'
        if project_root.exists():
            additional = tuple(p for p in project_root.rglob('memory') if p.is_dir())
            require(len(additional) <= 100, 'OBSERVATION_BUDGET', 'At most 100 private project memory roots')
            roots += additional
    if request['harness'] == 'AstronStudio' and manifest['profiles']['AstronStudio'].get('astudio_scope'):
        from .astudio_scope import load
        frozen = manifest['profiles']['AstronStudio']['astudio_scope']
        spec = load(frozen['scope'], frozen)
        base = Path(spec['paths']['overlay'])
        roots = (base / 'memories', base / 'memories_extensions')
    try:
        paths = []
        for store in roots:
            require(store.resolve() == store, 'OBSERVATION_SYMLINK', str(store))
            if store.exists(): paths.extend(store.rglob('*.md'))
        if request['harness'] == 'WorkBuddy' and (workbuddy_base / 'MEMORY.md').is_file():
            paths.append((workbuddy_base / 'MEMORY.md'))
        workspace_store = None
        workspace_roots = []
        if request['harness'] == 'WorkBuddy':
            workspace_store = Path(episode['workspaces'][request.get('scope', next(iter(episode['workspaces'])))]) / '.workbuddy/memory'
            require(workspace_store.resolve() == workspace_store, 'OBSERVATION_SYMLINK', str(workspace_store))
            workspace_roots.append(workspace_store)
            if workspace_store.exists(): paths.extend(workspace_store.rglob('*.md'))
            if manifest['profiles']['WorkBuddy'].get('workbuddy_scope'):
                codebuddy = Path(episode['workspaces'][request.get('scope', next(iter(episode['workspaces'])))]) / '.codebuddy'
                require(codebuddy.resolve() == codebuddy, 'OBSERVATION_SYMLINK', str(codebuddy))
                workspace_roots.append(codebuddy)
                if codebuddy.exists(): paths.extend(codebuddy.rglob('*.md'))
        require(len(paths) <= 200, 'OBSERVATION_BUDGET', 'At most 200 memory files')
        for path in sorted(set(paths)):
            before = path.lstat()
            require(before.st_size <= 1024 * 1024, 'OBSERVATION_BUDGET', 'At most 1 MiB per memory file')
            data = safe_file(path).read_bytes()
            after = path.stat()
            require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'OBSERVATION_UNSTABLE', str(path))
            total += len(data)
            require(total <= 4 * 1024 * 1024, 'OBSERVATION_BUDGET', 'At most 4 MiB per state snapshot')
            checksum = sha(data)
            raw = folder / checksum
            if not raw.exists():
                publish(raw, data); os.chmod(raw, 0o600)
            else:
                require(sha(safe_file(raw, root).read_bytes()) == checksum, 'ARTIFACT_DRIFT', str(raw))
            text = data.decode('utf-8', errors='replace')
            namespace_present = bool(facts.get('project') and facts['project'] in text)
            files.append({'source_path': str(path), 'source_mtime_ns': after.st_mtime_ns,
                          'channel_location': 'workspace_files' if any(path.is_relative_to(p) for p in workspace_roots) else 'native_local_files',
                          'artifact': {'path': str(raw.relative_to(root)), 'sha256': checksum, 'size': len(data)},
                          'namespace_present': namespace_present,
                          'scoped_text_presence': {key: bool(namespace_present and str(value) in text) for key, value in facts.items()}})
    except (OSError, ValueError) as exc:
        error = getattr(exc, 'code', type(exc).__name__)
    status = 'error' if error else 'observed_file_scope' if roots else 'unobservable'
    signature = digest({'status': status, 'files': files, 'error': error})
    previous = [event for event in events(root) if event['kind'] == 'MEMORY_OBSERVATION'
                and event['payload']['operation_id'] == request['operation_id'] and event['payload']['stage'] == stage]
    if previous and previous[-1]['payload']['signature'] == signature:
        return previous[-1]['payload']
    snapshot = {'contract': 'wildclawbench.memory-state-observation/v1', 'observed_at': timestamp(),
                'harness': request['harness'], 'operation_id': request['operation_id'], 'step_id': request['step_id'],
                'stage': stage, 'status': status, 'error': error, 'files': files,
                'visibility': 'known_local_memory_files_only', 'global_store_exhaustiveness_verified': False,
                'semantic_fact_retention_verified': False, 'formation_event_verified': False}
    path = publish(folder / (uuid4().hex + '.json'), snapshot)
    os.chmod(path, 0o600)
    reference = {'path': str(path.relative_to(root)), 'sha256': sha(path.read_bytes()), 'size': path.stat().st_size}
    payload = {'operation_id': request['operation_id'], 'stage': stage, 'status': status,
               'signature': signature, 'snapshot': reference}
    append(root, 'MEMORY_OBSERVATION', request['episode_id'], payload)
    return payload
