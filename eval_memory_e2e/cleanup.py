"""Layered cleanup observations, deliberately never an account reset certificate."""
from .admission import exact_response
from .batch import operation_id
from .io import decode, events, verify_artifact


def cleanup_layers(root, manifest, item, case, receipts):
    policy = case.get('cleanup')
    if policy is None or item['arm'] != 'M+':
        return None
    facts = case['facts']
    target, keep = facts[policy['target_fact']], facts[policy['keep_fact']]
    before = receipts.get(operation_id(manifest, item['id'], policy['before_step']))
    answer_format = policy.get('answer_format', 'raw_json')
    formed = exact_response(root, before, {policy['target_key']: target, policy['keep_key']: keep}, answer_format)
    behavior, storage = [], []
    for step in policy['after_steps']:
        op = operation_id(manifest, item['id'], step)
        receipt = receipts.get(op)
        result = exact_response(root, receipt, {policy['target_key']: policy['unknown_value'], policy['keep_key']: keep}, answer_format)
        if receipt and receipt['status'] == 'completed':
            raw = verify_artifact(root, receipt['artifacts']['final_response']).decode('utf-8')
            result['target_leaked_in_response'] = target.casefold() in raw.casefold()
            if result['target_leaked_in_response']:
                result.update(passed=False, reason='target_value_leaked_in_response')
        behavior.append({'step_id': step, 'status': 'not_evaluable' if not formed['passed'] else
                         'not_observed' if not receipt or receipt['status'] != 'completed' else
                         'passed' if result['passed'] else 'failed', **result})
        files = []
        for entry in (receipt or {}).get('candidate_snapshot', []):
            files.append({'source_path': entry['workspace_path'], 'location': 'workspace_files', 'artifact': entry['artifact']})
        snapshots = []
        for event in events(root):
            if event['kind'] == 'MEMORY_OBSERVATION' and event['episode_id'] == item['id'] and event['payload']['operation_id'] == op and event['payload']['stage'] == 'after':
                snapshots.append(decode(verify_artifact(root, event['payload']['snapshot'])))
        # Use the latest after-state, never a union with an earlier state.
        if snapshots:
            files += [{'source_path': f['source_path'], 'location': f.get('channel_location', 'native_local_files'), 'artifact': f['artifact']}
                      for f in snapshots[-1]['files']]
        inspected = []
        for file in files:
            text = verify_artifact(root, file['artifact']).decode('utf-8', errors='replace')
            inspected.append({**file, 'target_present': target in text, 'keep_present': keep in text})
        residual = any(f['target_present'] for f in inspected)
        status = 'residue_found' if residual else 'observation_error' if snapshots and snapshots[-1]['status'] == 'error' else \
                 'no_residue_in_observed_files' if inspected else 'unobservable'
        storage.append({'step_id': step, 'status': status, 'files': inspected,
                        'observed_file_count': len(inspected), 'exhaustive': False})
    return {'formation_recall': formed, 'behavior': behavior, 'known_storage': storage,
            'old_sources': {'status': 'unverified', 'reason': 'Original conversations, indexes and caches are not exhaustively inspected or removed'},
            'periodic_regeneration': {'status': 'unverified', 'reason': 'Elapsed time and neutral sessions do not prove a real maintenance cycle'},
            'environment_reset': {'status': 'not_admitted', 'verified': False},
            'capability_score': None}
