"""Independent expected-set comparison; no reference-layout or formula mandate."""
from pathlib import Path
from collections import defaultdict
import csv
import json
import runpy

T = runpy.run_path(str(Path(__file__).with_name('h021_tables.py')))

def average(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0

def close(value, expected):
    return value == expected if expected is None else isinstance(value, (int, float)) and abs(value - expected) <= 1e-9

def source_index(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return {row['record_id']: {**row, 'source_row': number} for number, row in enumerate(csv.DictReader(stream), 2)}

def safe_ids(value, prefix):
    try:
        return T['ids'](value, prefix)
    except T['CandidateError']:
        return None

def subset_witness(value, expected, prefix, *, required):
    values = safe_ids(value, prefix)
    return values is not None and values <= set(expected) and (bool(values) if required else not values)

def ledger(book, expected, contract, source):
    tables, headers = T['discover'](book, contract)
    key_fields = {'summaries': ['metric_date', 'cohort'], 'memberships': ['metric_date', 'cohort', 'user_id'],
        'user_days': ['user_id', 'activity_date'], 'audit': ['record_id']}
    indices = {kind: T['index_rows'](tables[kind], keys, contract) for kind, keys in key_fields.items()}
    checks = defaultdict(dict)
    findings = []
    for kind, fields in key_fields.items():
        keys = {tuple(row[field] for field in fields) for row in expected[kind]}
        extra = sum(len(rows) for key, rows in indices[kind].items() if key not in keys)
        checks['coverage'][kind] = len(keys) / (len(keys) + extra) if keys else 0
        if extra:
            findings.append({'kind': kind, 'unexpected_rows': extra})

    def row(kind, wanted):
        key = tuple(wanted[field] for field in key_fields[kind])
        rows = indices[kind].get(key, [])
        if len(rows) != 1 or not rows[0].get('_visible'):
            findings.append({'kind': kind, 'key': key, 'problem': 'missing/duplicate/invisible'})
            return None, key
        return rows[0], key

    for wanted in expected['summaries']:
        actual, key = row('summaries', wanted)
        fields = {}
        if actual:
            for field in ['denominator', 'numerator', 'rate']:
                fields[field] = close(T['number'](actual[field], missing=True), wanted[field])
            fields['observable'] = T['bit'](actual['observable']) == wanted['observable']
            fields['reason'] = T['alias'](actual['reason'], contract['reason_aliases']) == wanted['reason']
        checks['summaries'][key] = fields if actual else {f: False for f in ['denominator', 'numerator', 'rate', 'observable', 'reason']}
        if not all(checks['summaries'][key].values()):
            findings.append({'kind': 'summary', 'key': key, 'fields': checks['summaries'][key]})

    for wanted in expected['audit']:
        actual, key = row('audit', wanted)
        facts = {'decision': False, 'canonical': False, 'source_row': False}
        if actual:
            facts['decision'] = T['alias'](actual['decision'], contract['decision_aliases']) == wanted['decision']
            canonical = '' if T['blank'](actual['canonical_record_id']) else T['identifier'](actual['canonical_record_id'], 'R')
            facts['canonical'] = canonical == wanted['canonical_record_id']
            facts['source_row'] = close(T['number'](actual['source_row']), wanted['source_row'])
        checks['audit'][key[0]] = facts

    for wanted in expected['user_days']:
        actual, key = row('user_days', wanted)
        facts = {'first_date': False, 'witness': False}
        if actual:
            facts['first_date'] = T['date'](actual['first_active_date']) == wanted['first_active_date']
            event_ids = safe_ids(actual['event_ids'], 'E')
            record_ids = safe_ids(actual['record_ids'], 'R')
            facts['witness'] = bool(event_ids) and bool(record_ids) and event_ids <= set(wanted['event_ids']) and record_ids <= set(wanted['record_ids'])
            if facts['witness']:
                facts['witness'] = event_ids == {source[r]['event_id'].strip().upper() for r in record_ids}
        checks['user_days'][key] = facts

    for wanted in expected['memberships']:
        actual, key = row('memberships', wanted)
        facts = {'first_date': False, 'returned_next': False, 'lost': False, 'base_witness': False, 'next_witness': False}
        if actual:
            facts['first_date'] = T['date'](actual['first_active_date']) == wanted['first_active_date']
            for field in ['returned_next', 'lost']:
                facts[field] = (T['number'](actual[field], missing=True) is None if wanted[field] is None else T['bit'](actual[field]) == wanted[field])
            facts['base_witness'] = subset_witness(actual['base_event_ids'], wanted['base_event_ids'], 'E', required=True)
            facts['next_witness'] = subset_witness(actual['next_event_ids'], wanted['next_event_ids'], 'E', required=bool(wanted['returned_next']))
        checks['memberships'][key] = facts

    summary_score = average(average(v.values()) for v in checks['summaries'].values()) * checks['coverage']['summaries']
    members_score = average(average(v[k] for k in ['first_date', 'returned_next', 'lost']) for v in checks['memberships'].values()) * checks['coverage']['memberships']
    user_day_score = average(v['first_date'] for v in checks['user_days'].values()) * checks['coverage']['user_days']
    audit_groups = {}
    for decision in expected['decision_counts']:
        rows = [checks['audit'][r['record_id']] for r in expected['audit'] if r['decision'] == decision]
        audit_groups[decision] = average(all(r[f] for f in ['decision', 'canonical']) for r in rows) * checks['coverage']['audit']
    evidence_score = average([
        average(all(v.values()) for v in checks['audit'].values()) * checks['coverage']['audit'],
        average(v['witness'] for v in checks['user_days'].values()) * checks['coverage']['user_days'],
        average(v['base_witness'] and v['next_witness'] for v in checks['memberships'].values()) * checks['coverage']['memberships'],
    ])
    boundary_summary = average(all(checks['summaries'][(d, c)].values()) for d, c in [
        ('2026-09-10', 'new'), ('2026-09-15', 'new'), ('2026-09-15', 'old'), ('2026-09-12', 'new'),
        ('2026-09-04', 'old'), ('2026-09-08', 'old'), ('2026-09-12', 'old')])
    boundary_members = average(all(v.values()) for key, v in checks['memberships'].items() if key[0] in {'2026-09-04', '2026-09-08', '2026-09-12', '2026-09-15'})
    return {'tables': tables, 'headers': headers, 'checks': checks, 'findings': findings,
        'summary_score': summary_score, 'members_score': members_score, 'user_day_score': user_day_score,
        'audit_groups': audit_groups, 'evidence_score': evidence_score,
        'boundary_score': .65 * average(audit_groups.values()) + .2 * boundary_summary + .15 * boundary_members,
        'complete_detail': len(tables['audit']) == 1200 and len(tables['user_days']) == 500 and len(tables['memberships']) == 476}

def anomaly_facts(document, expected, contract, source):
    if not isinstance(document, dict) or not isinstance(document.get('anomalies'), list) or len(document['anomalies']) > 100:
        return {'facts': 0.0, 'evidence': 0.0, 'findings': ['invalid anomalies object']}
    actual_rows = defaultdict(list)
    for row in document['anomalies']:
        if isinstance(row, dict):
            actual_rows[(T['date'](row.get('metric_date')), T['alias'](row.get('cohort'), contract['cohort_aliases']))].append(row)
    expected_keys = {(r['metric_date'], r['cohort']) for r in expected['anomalies']}
    extra = sum(len(rows) for key, rows in actual_rows.items() if key not in expected_keys)
    precision = 3 / (3 + extra)
    findings = []
    all_facts, all_evidence = [], []
    trace = {r['trace_id']: r for r in expected['legacy_trace']}
    for wanted in expected['anomalies']:
        key = wanted['metric_date'], wanted['cohort']
        rows = actual_rows.get(key, [])
        if len(rows) != 1:
            all_facts.append(0.0);all_evidence.append(0.0)
            findings.append({'key': key, 'problem': 'missing or duplicate anomaly'})
            continue
        actual = rows[0]
        facts = []
        for group in ['old', 'corrected']:
            values = actual.get(group)
            facts.extend(isinstance(values, dict) and close(T['number'](values.get(f), missing=True), wanted[group][f]) for f in ['numerator', 'denominator', 'rate'])
        mechanism = T['alias'](actual.get('mechanism'), contract['mechanism_aliases'])
        facts.append(mechanism == wanted['mechanism'])
        all_facts.append(average(facts))
        evidence = actual.get('evidence', {})
        if not isinstance(evidence, dict):
            all_evidence.append(0.0)
            continue
        witnesses = {field: safe_ids(evidence.get(field), prefix) for field, prefix in [('affected_users', 'U'), ('trace_ids', 'T'), ('record_ids', 'R'), ('event_ids', 'E')]}
        if any(not value for value in witnesses.values()):
            all_evidence.append(0.0)
            findings.append({'key': key, 'problem': 'missing/invalid evidence identities'})
            continue
        allowed = wanted['evidence']
        valid = all(witnesses[field] <= set(allowed[field]) for field in ['trace_ids', 'record_ids', 'event_ids'])
        selected = [trace[t] for t in witnesses['trace_ids']] if valid else []
        roles = defaultdict(list)
        for item in selected:
            roles[item['role']].append(item)
        valid = valid and all(item['record_id'] in witnesses['record_ids'] and item['event_id'] in witnesses['event_ids'] for item in selected)
        valid = valid and witnesses['event_ids'] == {source[r]['event_id'].strip().upper() for r in witnesses['record_ids']}
        source_rows = evidence.get('source_rows')
        if source_rows is not None:
            normalized_rows = [T['number'](v) for v in source_rows] if isinstance(source_rows, list) else []
            valid = valid and isinstance(source_rows, list) and set(normalized_rows) == {source[r]['source_row'] for r in witnesses['record_ids']}
        affected = witnesses['affected_users']
        if wanted['mechanism'] == 'duplicate_event_rows':
            valid = valid and affected == set(allowed['affected_users'])
            for user in allowed['affected_users']:
                counted = [r for r in roles['lost'] if r['user_id'] == user]
                # The actual old rows must count the same normalized event twice.
                valid = valid and len(counted) >= 2 and len({r['record_id'] for r in counted}) >= 2 and len({r['event_id'] for r in counted}) == 1
        elif wanted['mechanism'] == 'utc_day_cutover':
            valid = valid and affected == set(allowed['affected_users'])
            for user in allowed['affected_users']:
                counted = [r for r in roles['return_evidence'] if r['user_id'] == user]
                valid = valid and any(r['day_used'] != '2026-09-09' for r in counted)
        else:
            base_users = {r['user_id'] for r in expected['legacy_trace'] if r['metric_date'] == key[0] and r['role'] == 'base'}
            wrong_users = {r['user_id'] for r in expected['legacy_trace'] if r['metric_date'] == key[0] and r['role'] == 'denominator'}
            valid = valid and affected in [base_users, wrong_users, base_users | wrong_users]
            valid = valid and bool(roles['base']) and bool(roles['denominator']) and all(r['user_id'] in wrong_users and r['user_id'] not in base_users for r in roles['denominator'])
        all_evidence.append(float(bool(valid)))
        if not valid or not all(facts):
            findings.append({'key': key, 'facts': facts, 'direct_evidence': bool(valid)})
    clock = document.get('analysis_cutoff') == expected['analysis_cutoff'] and document.get('business_timezone') in {'Asia/Shanghai', 'UTC+08:00', '+08:00'}
    return {'facts': average(all_facts) * precision, 'evidence': average(all_evidence) * precision * float(clock), 'findings': findings}
