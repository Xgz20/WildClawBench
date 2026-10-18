"""Private, deterministic prerequisites and independent channel review admission.

Passing an exact response gate proves observed recall only, never a background
formation event. Channel claims require cited review; directory names do not
establish a mechanism. Nothing here sends or modifies client memory.
"""
import json
from pathlib import Path

from .batch import episode, load_batch, operation_id
from .dataset_v3 import CHANNELS
from .io import (MemoryEvaluationError, append, archive, decode, digest, events, lock,
                 read_json, require, verify_artifact)


def response_json(text, answer_format='raw_json'):
    require(answer_format in {'raw_json', 'single_json_object'}, 'RESPONSE_FORMAT', 'Unknown answer parser')
    if answer_format == 'raw_json':
        if text.startswith('```json\n') and text.endswith('\n```'):
            text = text[8:-4].strip()
        return decode(text)
    # One complete container; duplicate keys and nonfinite values still fail.
    decoder = json.JSONDecoder()
    candidates, end = [], 0
    for index, char in enumerate(text):
        if index < end or char not in '{[':
            continue
        try:
            _, stop = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            continue
        candidates.append(decode(text[index:stop])); end = stop
    require(len(candidates) == 1 and isinstance(candidates[0], dict), 'RESPONSE_FORMAT',
            'Expected one unambiguous JSON object')
    return candidates[0]


def exact_response(root, receipt, expected, answer_format='raw_json'):
    if not receipt or receipt['status'] != 'completed':
        return {'passed': False, 'reason': 'source_not_completed', 'field_matches': {}}
    reference = receipt['artifacts']['final_response']
    text = verify_artifact(root, reference).decode('utf-8').strip()
    try:
        observed = response_json(text, answer_format)
    except MemoryEvaluationError:
        observed = None
    matches = {key: isinstance(observed, dict) and type(observed.get(key)) is str and observed[key] == value
               for key, value in expected.items()}
    passed = isinstance(observed, dict) and set(observed) == set(expected) and all(matches.values())
    return {'passed': passed, 'reason': 'exact_json_match' if passed else 'recall_or_format_not_confirmed',
            'field_matches': matches, 'response_artifact': reference}


def _case(root, item):
    return read_json(Path(root) / 'private/scenarios.json')[item['private_key']]


def channel_evidence(root, item, receipt):
    available = [{'kind': name, 'reference': ref} for name, ref in receipt['artifacts'].items()]
    available += [{'kind': 'workspace_files', 'source_path': entry['workspace_path'], 'reference': entry['artifact']}
                  for entry in receipt.get('candidate_snapshot', [])]
    for event in events(root):
        if event['kind'] != 'MEMORY_OBSERVATION' or event['episode_id'] != item['id']:
            continue
        payload = event['payload']
        if payload['operation_id'] != receipt['operation_id'] or payload['stage'] != 'after':
            continue
        snapshot = decode(verify_artifact(root, payload['snapshot']))
        available += [{'kind': file.get('channel_location', 'native_local_files'),
                       'source_path': file['source_path'], 'reference': file['artifact']} for file in snapshot['files']]
    for entry in available:
        verify_artifact(root, entry['reference'])
    return available


def validate_channel_review(root, review, manifest, item, gate, receipt):
    require(isinstance(review, dict) and review.get('contract') == 'wildclawbench.memory-channel-review/v1'
            and review.get('manifest_sha256') == digest(manifest) and review.get('episode_id') == item['id']
            and review.get('gate_id') == gate['id'] and review.get('source_operation_id') == receipt['operation_id']
            and review.get('source_receipt_sha256') == digest(receipt), 'CHANNEL_REVIEW_BINDING', item['id'])
    context = review.get('review_context_id')
    require(isinstance(context, str) and context.strip() and context not in receipt.get('native', {}).values(),
            'CHANNEL_REVIEW_CONTEXT', 'Use an independent evidence review context')
    claims = {'channel', 'storage_locations', 'writer', 'read_mechanism', 'control'}
    require(isinstance(review.get('channel'), str) and review['channel'] in CHANNELS and isinstance(review.get('storage_locations'), list)
            and review['storage_locations'] and all(isinstance(s, str) and s.strip() for s in review['storage_locations'])
            and isinstance(review.get('writer'), str) and review['writer'] in {'agent_tool', 'client_background', 'user', 'unknown'}
            and all(isinstance(review.get(k), str) and review[k].strip() for k in ('read_mechanism', 'control', 'reason'))
            and isinstance(review.get('decision'), str) and review['decision'] in {'admitted', 'not_admitted'}, 'CHANNEL_REVIEW_SHAPE', gate['id'])
    available = channel_evidence(root, item, receipt)
    citations = review.get('evidence')
    require(isinstance(citations, list) and citations, 'CHANNEL_REVIEW_EVIDENCE', gate['id'])
    supported = set()
    for citation in citations:
        require(isinstance(citation, dict) and citation.get('reference') in [e['reference'] for e in available]
                and isinstance(citation.get('supports'), list) and citation['supports']
                and all(isinstance(s, str) for s in citation['supports']) and set(citation['supports']) <= claims,
                'CHANNEL_REVIEW_EVIDENCE', 'Cite frozen source-step evidence only')
        quote = citation.get('quote')
        require(isinstance(quote, str) and quote.strip()
                and quote in verify_artifact(root, citation['reference']).decode('utf-8'),
                'CITATION_NOT_FOUND', gate['id'])
        if review['channel'] == 'account_profile' and 'channel' in citation['supports']:
            require(any(e['reference'] == citation['reference'] and e['kind'] in {'trace', 'binding_evidence'} for e in available),
                    'CHANNEL_PROMOTION_REJECTED', 'Workspace files alone cannot establish an account profile')
        supported.update(citation['supports'])
    require(supported == claims, 'CHANNEL_REVIEW_EVIDENCE', 'Each channel/mechanism claim needs cited support')
    if review['decision'] == 'admitted':
        location_kind = {'workspace_files': 'workspace_files', 'native_local_memory': 'native_local_files'}.get(review['channel'])
        if location_kind:
            require(any('channel' in c['supports'] and any(e['reference'] == c['reference'] and e['kind'] == location_kind
                        for e in available) for c in citations), 'CHANNEL_LOCATION_UNVERIFIED',
                    'An observed source file is required for this storage channel')
            require(all(any(e.get('source_path') == location and e['kind'] == location_kind
                            and any(c['reference'] == e['reference'] and 'storage_locations' in c['supports'] for c in citations)
                            for e in available) for location in review['storage_locations']),
                    'CHANNEL_LOCATION_UNVERIFIED', 'Storage locations must name the cited observed files')
        require(review['channel'] in gate['allowed_channels'] and review['writer'] != 'unknown'
                and review['read_mechanism'] != 'unknown' and review['control'] != 'unknown',
                'CHANNEL_NOT_ADMITTED', 'Unknown or disallowed mechanisms cannot pass the gate')
    return review


def gate_results(root, manifest, item, before_step, receipts):
    results = []
    for gate in _case(root, item).get('gates', []):
        if gate['before_step'] != before_step or item['arm'] not in gate['arms']:
            continue
        source = receipts.get(operation_id(manifest, item['id'], gate['source_step']))
        base = {'gate_id': gate['id'], 'kind': gate['kind'], 'before_step': before_step,
                'source_step': gate['source_step'], 'score': None}
        if gate['kind'] == 'response_json_exact':
            outcome = exact_response(root, source, gate['expected'], gate.get('answer_format', 'raw_json'))
            results.append({**base, **outcome, 'status': 'passed' if outcome['passed'] else 'prerequisite_failed'})
        else:
            records = [e for e in events(root) if e['kind'] == 'CHANNEL_REVIEW' and e['episode_id'] == item['id']
                       and e['payload']['gate_id'] == gate['id']]
            require(len(records) <= 1, 'DUPLICATE_CHANNEL_REVIEW', gate['id'])
            if not records:
                results.append({**base, 'status': 'awaiting_channel_review'})
                continue
            review = decode(verify_artifact(root, records[0]['payload']['review_artifact']))
            require(source and source['status'] == 'completed', 'CHANNEL_SOURCE_INCOMPLETE', gate['id'])
            validate_channel_review(root, review, manifest, item, gate, source)
            results.append({**base, 'status': 'passed' if review['decision'] == 'admitted' else 'prerequisite_failed',
                            'channel': review['channel'], 'review_artifact': records[0]['payload']['review_artifact']})
    return results


def channel_template(root, episode_id, gate_id):
    from .runner import _receipts
    manifest = load_batch(root, episode_id=episode_id)
    item = episode(manifest, episode_id)
    found = [g for g in _case(root, item).get('gates', []) if g['id'] == gate_id and g['kind'] == 'channel_review'
             and item['arm'] in g['arms']]
    require(len(found) == 1, 'CHANNEL_GATE_SCOPE', gate_id)
    gate = found[0]
    receipt = _receipts(root, episode_id).get(operation_id(manifest, episode_id, gate['source_step']))
    require(receipt and receipt['status'] == 'completed', 'CHANNEL_SOURCE_INCOMPLETE', gate_id)
    return {'contract': 'wildclawbench.memory-channel-review/v1', 'manifest_sha256': digest(manifest),
            'episode_id': episode_id, 'gate_id': gate_id, 'source_operation_id': receipt['operation_id'],
            'source_receipt_sha256': digest(receipt), 'review_context_id': None, 'decision': None,
            'channel': 'unknown', 'storage_locations': [], 'writer': 'unknown', 'read_mechanism': 'unknown',
            'control': 'unknown', 'reason': '', 'evidence': [], 'allowed_channels': gate['allowed_channels'],
            'available_evidence': channel_evidence(root, item, receipt)}


def import_channel_review(root, path):
    from .runner import _receipts
    with lock(root):
        manifest = load_batch(root)
        reference = archive(root, path)
        item, gate = None, None
        try:
            review = read_json(path)
            require(isinstance(review, dict), 'CHANNEL_REVIEW_SHAPE', 'Expected a review object')
            item = episode(manifest, review.get('episode_id'))
            gate = next((g for g in _case(root, item).get('gates', []) if g['id'] == review.get('gate_id')
                         and g['kind'] == 'channel_review' and item['arm'] in g['arms']), None)
            require(gate, 'CHANNEL_GATE_SCOPE', str(review.get('gate_id')))
            receipt = _receipts(root, item['id']).get(operation_id(manifest, item['id'], gate['source_step']))
            require(receipt and receipt['status'] == 'completed', 'CHANNEL_SOURCE_INCOMPLETE', gate['id'])
            validate_channel_review(root, review, manifest, item, gate, receipt)
            require(not any(e['kind'] == 'CHANNEL_REVIEW' and e['episode_id'] == item['id'] and e['payload']['gate_id'] == gate['id']
                            for e in events(root)), 'CHANNEL_REVIEW_EXISTS', 'Keep the original review; use a new batch to change conditions')
        except MemoryEvaluationError as exc:
            append(root, 'CHANNEL_REVIEW_ERROR', item['id'] if item else None,
                   {'gate_id': gate['id'] if gate else None, 'review_artifact': reference, 'error_code': exc.code})
            raise
        payload = {'gate_id': gate['id'], 'review_artifact': reference, 'decision': review['decision'], 'channel': review['channel']}
        append(root, 'CHANNEL_REVIEW', item['id'], payload)
        return payload


def record_gate_pause(root, action):
    previous = [e for e in events(root) if e['kind'] == 'ADMISSION_PAUSE' and e['episode_id'] == action['episode_id']]
    if not previous or previous[-1]['payload'] != action:
        append(root, 'ADMISSION_PAUSE', action['episode_id'], action)
