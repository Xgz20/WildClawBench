"""Extensible linear memory recipes; unsupported execution semantics fail closed."""
import re
from pathlib import Path
from string import Formatter

from . import METRICS
from .io import digest, identifier, require, safe_file, sha

BASE_FIELDS = {'project', 'code', 'other', 'person', 'old', 'new', 'secret', 'keep', 'city', 'date1', 'date2'}


def validate_v2(data, path):
    identifier(data.get('dataset_id'))
    require(data['version'] == 2 and type(data['version']) is int, 'DATASET_VERSION', 'Expected v2')
    require(set(data) <= {'dataset_id', 'version', 'scenarios', 'source_assets', 'fixture_assets', 'description', 'metadata'},
            'DATASET_SHAPE', 'Unknown v2 dataset field')
    cases = data.get('scenarios')
    require(isinstance(cases, list) and 0 < len(cases) <= 10000, 'DATASET_SCOPE', 'Expected 1..10000 independent scenarios')
    ids = []
    for case in cases:
        required = {'id', 'dimension', 'title', 'difficulty', 'experience_gain', 'fixtures', 'steps', 'checkpoints', 'scopes', 'learning'}
        require(isinstance(case, dict) and required <= set(case)
                and set(case) <= required | {'variables', 'provenance', 'control_flow'}, 'DATASET_SHAPE', 'Unknown or missing v2 scenario fields')
        identifier(case['id']); ids.append(case['id'])
        require(case.get('control_flow', 'linear') == 'linear', 'UNSUPPORTED_CONTROL_FLOW', 'DAG/conditional branches are not admitted')
        require(case['dimension'] in {'retention', 'personalization', 'temporal', 'updates', 'forgetting', 'isolation', 'relevance', 'procedural'},
                'DIMENSION_SCOPE', case['id'])
        require(case['difficulty'] in {'easy', 'medium', 'hard'} and type(case['experience_gain']) is bool
                and isinstance(case['title'], str) and case['title'].strip(), 'DATASET_SHAPE', case['id'])
        scopes = case['scopes']
        require(isinstance(scopes, list) and 0 < len(scopes) <= 32 and len(set(scopes)) == len(scopes)
                and all(isinstance(s, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', s) for s in scopes),
                'DATASET_SCOPE', 'Scopes are workspace namespaces, not separate accounts')
        learning = case['learning']
        require(isinstance(learning, dict) and set(learning) == {'mode', 'formation'}
                and learning['mode'] in {'explicit', 'automatic', 'eviction'}, 'LEARNING_POLICY', case['id'])
        formation = learning['formation']
        require(isinstance(formation, dict) and set(formation) <= {'kind', 'minimum_seconds', 'event'}
                and formation.get('kind') in {'immediate_observation', 'elapsed_observation', 'native_event'}
                and type(formation.get('minimum_seconds', 0)) in {int, float}
                and 0 <= formation.get('minimum_seconds', 0) <= 604800, 'FORMATION_POLICY', case['id'])
        require(formation['kind'] != 'native_event' or (isinstance(formation.get('event'), str) and formation['event'].strip()),
                'FORMATION_POLICY', 'Native formation requires a named event and an admitted adapter')
        variables = case.get('variables', {})
        require(isinstance(variables, dict) and len(variables) <= 256, 'DATASET_VARIABLE', case['id'])
        for name, spec in variables.items():
            require(isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', name)
                    and name not in BASE_FIELDS and isinstance(spec, dict), 'DATASET_VARIABLE', str(name))
            kind = spec.get('kind')
            if kind == 'token':
                require(set(spec) <= {'kind', 'prefix', 'length'} and type(spec.get('length', 12)) is int
                        and 4 <= spec.get('length', 12) <= 32 and isinstance(spec.get('prefix', ''), str), 'DATASET_VARIABLE', name)
            elif kind == 'integer':
                require(set(spec) == {'kind', 'min', 'max'} and type(spec['min']) is int and type(spec['max']) is int
                        and spec['min'] <= spec['max'], 'DATASET_VARIABLE', name)
            else:
                require(kind == 'literal' and set(spec) == {'kind', 'value'} and isinstance(spec['value'], str), 'DATASET_VARIABLE', name)
        require(isinstance(case['fixtures'], list) and len(case['fixtures']) == len(set(case['fixtures'])), 'DATASET_FIXTURE', case['id'])
        for name in case['fixtures']:
            identifier(name)
            asset = data.get('fixture_assets', {}).get(name)
            if asset:
                require(isinstance(asset, dict) and set(asset) == {'path', 'sha256'}, 'DATASET_FIXTURE', name)
                source = safe_file(Path(path).parent / asset['path'], Path(path).parent)
                require(source.stat().st_size <= 25 * 1024 * 1024 and sha(source.read_bytes()) == asset['sha256'], 'SOURCE_ASSET_DRIFT', name)
            else:
                safe_file(Path(__file__).with_name('fixtures') / name, Path(__file__).with_name('fixtures'))
        steps, checks = case['steps'], case['checkpoints']
        require(isinstance(steps, list) and 0 < len(steps) <= 1000 and isinstance(checks, list) and checks, 'DATASET_SHAPE', case['id'])
        seen, step_map = set(), {}
        for step in steps:
            require(isinstance(step, dict) and set(step) == {'id', 'phase', 'session', 'scope', 'prompt'}, 'DATASET_STEP', case['id'])
            identifier(step['id'])
            require(step['id'] != 'prepare', 'RESERVED_STEP_ID', 'prepare is reserved for namespace initialization')
            require(step['id'] not in step_map and step['phase'] in {'seed', 'interference', 'update', 'forget', 'learn', 'probe'}
                    and step['session'] in {'new', 'continue', 'restart_new'} and step['scope'] in scopes
                    and isinstance(step['prompt'], str) and step['prompt'].strip(), 'DATASET_STEP', case['id'])
            require(step['session'] != 'continue' or step['scope'] in seen, 'DATASET_SESSION', case['id'])
            seen.add(step['scope']); step_map[step['id']] = step
        require(steps[0]['session'] == 'new' and any(c.get('required') is True for c in checks), 'DATASET_CHECKPOINT', case['id'])
        check_ids = []
        for check in checks:
            require(isinstance(check, dict) and set(check) == {'id', 'step_id', 'metric', 'expectation', 'required'}, 'DATASET_CHECKPOINT', case['id'])
            identifier(check['id']); check_ids.append(check['id'])
            require(check['step_id'] in step_map and step_map[check['step_id']]['phase'] == 'probe' and check['metric'] in METRICS
                    and isinstance(check['expectation'], str) and check['expectation'].strip() and type(check['required']) is bool,
                    'DATASET_CHECKPOINT', case['id'])
        require(len(set(check_ids)) == len(check_ids), 'DUPLICATE_ID', case['id'])
        require({s['id'] for s in steps if s['phase'] == 'probe'} <= {c['step_id'] for c in checks}, 'UNSCORED_PROBE', case['id'])
        for value in [s['prompt'] for s in steps] + [c['expectation'] for c in checks]:
            for _, field, spec, conversion in Formatter().parse(value):
                require(field is None or (field in BASE_FIELDS | set(variables) and not spec and conversion is None), 'DATASET_PLACEHOLDER', str(field))
    require(len(set(ids)) == len(ids), 'DUPLICATE_ID', 'Scenario IDs must be unique')
    for relative, checksum in data.get('source_assets', {}).items():
        require(sha(safe_file(Path(path).parent / relative, Path(path).parent).read_bytes()) == checksum, 'SOURCE_ASSET_DRIFT', relative)
    return data


def custom_values(case, token):
    values = {}
    for name, spec in case.get('variables', {}).items():
        random = digest({'variant': token, 'field': name})
        if spec['kind'] == 'token':
            value = spec.get('prefix', '') + random[:spec.get('length', 12)].upper()
        elif spec['kind'] == 'integer':
            value = str(spec['min'] + int(random, 16) % (spec['max'] - spec['min'] + 1))
        else:
            value = spec['value']
        values[name] = value
    return values
