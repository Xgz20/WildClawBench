"""Independent state fold over source-bound annotations and actual corrections.

Does not import the manual final labels or any reference output. It validates
state propagation/order/authority, not an independent NLP/human annotation.
"""
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fold(exec_root, gt_root, cutoff='2026-10-27T12:30:00+08:00'):
    exec_root, gt_root = Path(exec_root), Path(gt_root)
    limit = datetime.fromisoformat(cutoff)
    with (exec_root / 'staff.csv').open(encoding='utf-8', newline='') as handle:
        people = {row['person_id']: row for row in csv.DictReader(handle)}
    raw = {line[1:5]: line for line in (exec_root / 'meeting_transcript.txt').read_text(encoding='utf-8').splitlines() if line.startswith('[S')}
    events = json.loads((gt_root / 'events.json').read_text(encoding='utf-8'))['segments']
    assert len(raw) == len(events) == 90 and {event['segment_id'] for event in events} == set(raw)
    states = {}
    audit = {'accepted_meeting': [], 'accepted_corrections': [], 'rejected_corrections': [], 'ignored_after_cutoff': []}

    def state_for(issue):
        return states.setdefault(issue, {'status': '待定', 'owner_id': '', 'owner_role': '', 'due_date': '', 'field_evidence': {}})

    def apply(issue, patch, source):
        state = state_for(issue)
        for key, value in patch.items():
            if key not in {'status', 'owner_id', 'due_date'}:
                raise ValueError('unexpected annotated field')
            state[key] = value
            state['field_evidence'][key] = source
            if key == 'owner_id':
                state['owner_role'] = people[value]['role'] if value else ''
                state['field_evidence']['owner_role'] = source

    for event in sorted(events, key=lambda item: datetime.fromisoformat(item['effective_at'])):
        source, issue, kind = event['segment_id'], event['issue_id'], event['kind']
        assert sha(raw[source]) == event['segment_sha256']
        if datetime.fromisoformat(event['effective_at']) > limit or issue is None or kind == 'context':
            continue
        if kind == 'propose':
            state_for(issue)
            continue
        if people[event['speaker_id']]['can_approve'] != 'yes':
            raise ValueError('annotated approval without authority')
        if kind in {'approve', 'withdraw', 'pending'}:
            patch = dict(event['patch'])
            if kind == 'pending':
                patch.update(owner_id='', due_date='')
            apply(issue, patch, source)
            audit['accepted_meeting'].append(source)
        else:
            raise ValueError('unexpected event annotation')
    corrections = [json.loads(line) for line in (exec_root / 'corrections.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    for event in sorted(corrections, key=lambda item: (datetime.fromisoformat(item['effective_at']), item['event_id'])):
        source = event['event_id']
        if datetime.fromisoformat(event['effective_at']) > limit:
            audit['ignored_after_cutoff'].append(source)
            continue
        if people[event['author_id']]['can_approve'] != 'yes':
            audit['rejected_corrections'].append({'event_id': source, 'actual_role': people[event['author_id']]['role'], 'reason': 'no_approval_authority'})
            continue
        if event['issue_id'] not in states:
            raise ValueError('amendment references absent issue')
        apply(event['issue_id'], event['patch'], source)
        audit['accepted_corrections'].append(source)
    for issue, state in states.items():
        if state['status'] == '待办' and (state['owner_id'] not in people or not state['due_date']):
            raise ValueError('active issue lacks owner/date')
        if state['due_date']:
            datetime.strptime(state['due_date'], '%Y-%m-%d')
    return {'issues': states, 'audit': audit}
