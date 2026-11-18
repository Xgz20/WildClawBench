"""Normalize native judge response metadata while retaining the raw response."""
from copy import deepcopy
import hashlib
import json

LEGACY_PROFILE = 'native-query-reference-transport/v1'
PROFILE = 'native-query-reference-transport/v2'
RESPONSE_SCHEMA = 'wildclawbench.general-e2e-codex-judge-response/v1'


def policy(manifest):
    frozen = manifest.get('runtime', {}).get('native_response_transport_profile')
    if frozen is None:
        return None
    if frozen not in {LEGACY_PROFILE, PROFILE}:
        raise ValueError('NATIVE_RESPONSE_TRANSPORT_PROFILE_INVALID')
    result = {'profile': frozen, 'deduplicate_exact_review_query_ids': True,
              'preserve_raw_response_bytes': True, 'modify_decisions_or_evidence': False}
    if frozen == PROFILE:
        result['restore_omitted_schema_version'] = RESPONSE_SCHEMA
    return result


def schema_omission_allowed(manifest, response):
    return (isinstance(response, dict) and 'schema_version' not in response
            and manifest.get('runtime', {}).get('native_response_transport_profile') == PROFILE
            and manifest.get('judge', {}).get('protocol') == 'codex-agent-judge-v1')


def normalize(manifest, response, raw_sha256):
    transport = policy(manifest)
    if transport is None:
        return response, None
    effective = deepcopy(response)
    restored_schema = schema_omission_allowed(manifest, effective)
    if restored_schema:
        effective['schema_version'] = RESPONSE_SCHEMA
    changed = []

    def review(value, path):
        if not isinstance(value, dict) or not isinstance(value.get('review'), dict):
            return
        ids = value['review'].get('query_ids')
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            return
        unique = list(dict.fromkeys(ids))
        if unique != ids:
            changed.append({'path': path + '.review.query_ids', 'removed_count': len(ids)-len(unique)})
            value['review']['query_ids'] = unique

    if isinstance(effective, dict):
        rows=effective.get('criteria', [])
        for index, row in enumerate(rows if isinstance(rows,list) else []):
            review(row, 'criteria.' + str(index))
        review(effective.get('run_validity'), 'run_validity')
        for name in ('criterion_evidence_statuses', 'capability_evidence_statuses'):
            values = effective.get(name, {})
            if isinstance(values, dict):
                for key, value in values.items():
                    review(value, name + '.' + str(key))
    encoded = json.dumps(effective, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    proof = {'profile': transport['profile'], 'raw_response_sha256': raw_sha256,
        'effective_response_sha256': hashlib.sha256(encoded).hexdigest(), 'deduplicated_reviews': changed,
        'removed_query_reference_count': sum(item['removed_count'] for item in changed),
        'decisions_or_evidence_modified': False}
    if transport['profile'] == PROFILE:
        proof['restored_schema_version'] = RESPONSE_SCHEMA if restored_schema else None
    return effective, proof
