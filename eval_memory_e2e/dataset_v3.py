"""Opt-in admission gates and condition-specific probes; v1/v2 stay frozen."""
import copy
from string import Formatter

from .dataset_v2 import BASE_FIELDS, validate_v2
from .io import identifier, require

CHANNELS = {'account_profile', 'native_local_memory', 'workspace_files', 'external_injected', 'unknown'}


def validate_v3(data, path):
    require(type(data.get('version')) is int and data['version'] == 3, 'DATASET_VERSION', 'Expected v3')
    legacy = copy.deepcopy(data)
    legacy['version'] = 2
    for case in legacy['scenarios']:
        for key in ('conditions', 'gates', 'cleanup'):
            case.pop(key, None)
    validate_v2(legacy, path)
    for case in data['scenarios']:
        steps = {step['id']: step for step in case['steps']}
        order = list(steps)
        probes = [s['id'] for s in case['steps'] if s['phase'] == 'probe']
        conditions = case.get('conditions', {'C0': {'probe_steps': probes}})
        require(isinstance(conditions, dict) and set(conditions) == {'C0'}
                and isinstance(conditions['C0'], dict) and set(conditions['C0']) == {'probe_steps'},
                'CONDITION_SCOPE', case['id'])
        cold = conditions['C0']['probe_steps']
        require(isinstance(cold, list) and cold and all(isinstance(s, str) for s in cold)
                and len(set(cold)) == len(cold) and cold == [s for s in probes if s in cold],
                'CONDITION_SCOPE', 'C0 must select nonempty ordered probe IDs')
        require(not case['experience_gain'] or cold == probes, 'UNPAIRED_CHECKPOINTS',
                'Experience gain requires the same probe/checkpoint scope in both arms')
        # C0 has independent new sessions; a continuation may never refer to an omitted learning turn.
        require(all(steps[s]['session'] != 'continue' for s in cold[1:]),
                'CONDITION_SESSION', 'Selected C0 probes after the first must start new sessions')
        gates = case.get('gates', [])
        require(isinstance(gates, list), 'GATE_POLICY', case['id'])
        ids = []
        for gate in gates:
            common = {'id', 'before_step', 'source_step', 'arms', 'kind'}
            require(isinstance(gate, dict) and common <= set(gate), 'GATE_POLICY', case['id'])
            identifier(gate['id']); ids.append(gate['id'])
            require(gate['before_step'] in steps and gate['source_step'] in steps
                    and order.index(gate['source_step']) < order.index(gate['before_step'])
                    and gate['arms'] == ['M+'], 'GATE_POLICY', 'Admission gates currently apply to M+ only')
            if gate['kind'] == 'response_json_exact':
                expected = gate.get('expected')
                require(set(gate) == common | {'expected'} and steps[gate['source_step']]['phase'] == 'probe'
                        and isinstance(expected, dict) and expected
                        and all(isinstance(k, str) and k and isinstance(v, str) and v for k, v in expected.items()),
                        'GATE_POLICY', 'Exact gate needs a probe and string JSON fields')
                for text in expected.values():
                    for _, field, spec, conversion in Formatter().parse(text):
                        require(field is None or (field in BASE_FIELDS | set(case.get('variables', {})) and not spec and conversion is None),
                                'DATASET_PLACEHOLDER', str(field))
            else:
                allowed = gate.get('allowed_channels')
                require(gate['kind'] == 'channel_review' and set(gate) == common | {'allowed_channels'}
                        and isinstance(allowed, list) and allowed and all(isinstance(c, str) for c in allowed)
                        and len(set(allowed)) == len(allowed) and set(allowed) <= CHANNELS - {'unknown'},
                        'GATE_POLICY', 'Channel gate requires an evidence-bound independent review')
        require(len(ids) == len(set(ids)), 'DUPLICATE_ID', case['id'])
        cleanup = case.get('cleanup')
        if cleanup is not None:
            require(isinstance(cleanup, dict) and set(cleanup) == {'before_step', 'after_steps', 'target_fact', 'keep_fact',
                                                                 'target_key', 'keep_key', 'unknown_value'}, 'CLEANUP_POLICY', case['id'])
            require(cleanup['before_step'] in probes and isinstance(cleanup['after_steps'], list)
                    and cleanup['after_steps'] and len(set(cleanup['after_steps'])) == len(cleanup['after_steps'])
                    and all(s in probes and order.index(s) > order.index(cleanup['before_step']) for s in cleanup['after_steps'])
                    and all(isinstance(cleanup[k], str) and cleanup[k] for k in ('target_fact', 'keep_fact', 'target_key', 'keep_key', 'unknown_value'))
                    and cleanup['target_fact'] in BASE_FIELDS | set(case.get('variables', {}))
                    and cleanup['keep_fact'] in BASE_FIELDS | set(case.get('variables', {}))
                    and cleanup['target_fact'] != cleanup['keep_fact'] and cleanup['target_key'] != cleanup['keep_key'],
                    'CLEANUP_POLICY', case['id'])
    return data
