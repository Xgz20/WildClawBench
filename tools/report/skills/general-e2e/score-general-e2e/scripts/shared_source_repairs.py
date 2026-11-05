"""Load the packaged, shared exact-source repairs without importing a checkout."""
from functools import lru_cache
import importlib.util
from pathlib import Path
import hashlib


@lru_cache(maxsize=1)
def _module():
    path=Path(__file__).parent.parent/'vendor/e2e-shared/wildclawbench_grading_core/source_repairs.py'
    if not path.is_file():
        if (Path(__file__).parent.parent/'bundled-components.json').exists():
            raise ValueError('SHARED_RULE_SOURCE_REPAIRS_UNAVAILABLE')
        # The repository CLI also runs in isolated subprocesses without
        # PYTHONPATH. Resolve its sibling source explicitly; a standalone
        # package (bundled-components.json present) must never use a checkout.
        path=Path(__file__).resolve().parents[6]/'src/wildclawbench_grading_core/source_repairs.py'
        if not path.is_file():
            raise ValueError('SHARED_RULE_SOURCE_REPAIRS_UNAVAILABLE')
    spec=importlib.util.spec_from_file_location('_general_e2e_shared_source_repairs',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def effective_source(manifest, original, effective, prior):
    frozen = manifest.get('runtime', {}).get('shared_rule_source_repair')
    if frozen is None:
        return effective, prior
    expected = marker({'task_id': manifest.get('identity', {}).get('task_id'),
                       'automated_checks': original}, profile=frozen.get('profile'))
    if expected is None or frozen != expected:
        raise ValueError('SHARED_RULE_SOURCE_REPAIR_PROFILE_MISMATCH')
    return _module().effective_source(manifest.get('identity',{}).get('task_id'),original,effective,prior,
                                     profile=frozen['profile'])


def marker(contract, *, profile=None):
    source_sha = hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest()
    row = _module().profile_entry(source_sha,profile)
    if row is None or row['task_id'] != contract.get('task_id'):
        return None
    return {'profile': row['profile'], 'source_sha256': source_sha,
            'current_source_sha256': row['current_source_sha256']}
