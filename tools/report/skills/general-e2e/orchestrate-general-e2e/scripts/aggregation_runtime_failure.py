"""Retain a completed judge blocked by a frozen scoring-Python/runtime mismatch."""
from pathlib import Path

ERROR_KIND = 'semantic-aggregation-score-python-mismatch/v1'
PROFILE = 'independent-business-capability/v2'


def evidence(rt, root, state, task):
    attempt = root / task['attempt_path']
    manifest = rt._read_json(attempt / 'attempt-manifest.json')
    if manifest.get('runtime', {}).get('business_capability_profile') != PROFILE:
        raise ValueError('AGGREGATION_RUNTIME_FAILURE_PROFILE')
    lock = rt._read_json(attempt / manifest['paths']['runtime_lock'])
    expected = [lock['python']['major'], lock['python']['minor']]
    python = state['score_skill']['python']
    if python.get('version', [])[:2] == expected:
        raise ValueError('AGGREGATION_RUNTIME_FAILURE_NOT_MISMATCHED')
    if task.get('score') is not None or (attempt / 'score.json').exists() or (attempt / 'semantic/semantic-component.json').exists():
        raise ValueError('AGGREGATION_RUNTIME_FAILURE_HAS_RESULT')
    if (task.get('thread') or {}).get('status') != 'COMPLETED':
        raise ValueError('AGGREGATION_RUNTIME_FAILURE_THREAD_NOT_COMPLETED')
    request = attempt / 'semantic/request.json'
    checks = attempt / 'semantic/aggregation-checks'
    prompt = (root / task['prompt_path']).read_text(encoding='utf-8')
    if not request.is_file() or not checks.is_dir() or not any(checks.iterdir()) or 'check-aggregation' not in prompt:
        raise ValueError('AGGREGATION_RUNTIME_FAILURE_CHECK_MISSING')
    actual = rt._score_python_lock(Path(python['executable']))
    if actual != python:
        raise ValueError('AGGREGATION_RUNTIME_FAILURE_INTERPRETER_DRIFT')
    return {'profile': PROFILE, 'expected_python': expected, 'frozen_scoring_python': python,
            'runtime_lock_sha256': rt._sha256_file(attempt / manifest['paths']['runtime_lock']),
            'request_sha256': rt._sha256_file(request), 'semantic_result_published': False}


def matches(rt, root, state, task):
    try:
        evidence(rt, root, state, task)
        return True
    except (ValueError, KeyError, FileNotFoundError):
        return False
