"""Deterministic H002 fields and immutable event bindings; no NLP keywords."""
from collections import Counter
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import runpy


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_actions(path, contract):
    if not path.is_file() or path.is_symlink():
        return [], False, False, 'actions.csv missing or not a regular file'
    try:
        if path.stat().st_size > 2_000_000:
            return [], False, False, 'actions.csv exceeds size limit'
        text = path.read_text(encoding='utf-8-sig')
        reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
        raw_fields = reader.fieldnames
        fields = [name.strip().lower() for name in raw_fields] if raw_fields else []
        if not fields or len(set(fields)) != len(fields):
            return [], False, False, 'CSV headers absent or ambiguous'
        missing = set(contract['required_columns']) - set(fields)
        reader.fieldnames = fields
        rows = []
        for raw in reader:
            if None in raw or any(value is None for value in raw.values()):
                return [], False, False, 'inconsistent CSV row width'
            if not any(str(value or '').strip() for value in raw.values()):
                continue
            # Missing a description/evidence column must not erase otherwise
            # judgeable business fields or couple all checkpoints together.
            rows.append({**{key: str(raw.get(key, '')).strip() for key in contract['required_columns']},
                         '_present_columns': set(fields)})
            if len(rows) > 1000:
                return [], False, False, 'actions.csv exceeds row limit'
        return rows, True, not missing, 'missing required headers: ' + ','.join(sorted(missing)) if missing else None
    except (OSError, UnicodeError, csv.Error, ValueError):
        return [], False, False, 'actions.csv cannot be parsed as UTF-8 CSV'


def blank(value, contract):
    text = str(value or '').strip()
    return '' if text.lower() in {item.lower() for item in contract['blank_markers']} else text


def normalize(row, contract):
    result = dict(row)
    result['issue_id'] = result['issue_id'].upper()
    result['owner_id'] = blank(result['owner_id'], contract).upper()
    result['owner_role'] = blank(result['owner_role'], contract)
    value = blank(result['due_date'], contract)
    try:
        value = date.fromisoformat(value.replace('/', '-')).isoformat() if value else ''
    except ValueError:
        pass
    result['due_date'] = value
    aliases = {key.lower(): value for key, value in contract['status_aliases'].items()}
    result['status'] = aliases.get(result['status'].lower(), result['status'])
    return result


def evaluate(root):
    root = Path(root).resolve()
    gt = root / 'gt'
    expected = load(gt / 'expected.json')['issues']
    oracle = load(gt / 'business_oracle.json')
    boundary_groups = load(gt / 'counterexamples.json')['groups']
    contract = load(gt / 'artifact_contract.json')
    protected = load(gt / 'protected_sha256.json')
    source_index = load(gt / 'evidence_index.json')['events']
    load(gt / 'evidence_requirements.json')
    native = runpy.run_path(str(gt / 'native_text.py'))
    if (len(expected) != 17 or len({row['issue_id'] for row in expected}) != 17
            or len(source_index) != 96 or set(protected) != {'meeting_transcript.txt', 'corrections.jsonl', 'staff.csv'}):
        raise ValueError('H002 private GT contract is incomplete')
    if any(item['source_sha256'] != protected[item['source']] for item in source_index.values()):
        raise ValueError('H002 source index/protection contract mismatch')
    intact = all((root / name).is_file() and not (root / name).is_symlink()
                 and digest(root / name) == sha for name, sha in protected.items())
    rows, csv_ok, csv_complete, csv_error = read_actions(root / contract['actions'], contract)
    normalized = [normalize(row, contract) for row in rows]
    counts = Counter(row['issue_id'] for row in normalized)
    actual = {row['issue_id']: row for row in normalized if counts[row['issue_id']] == 1}
    checks, evidence_checks = {}, {}
    for label in expected:
        issue = label['issue_id']
        row = actual.get(issue)
        checks[issue] = {key: bool(row is not None and key in row['_present_columns'] and row[key] == label[key])
                         for key in oracle['field_weights']}
        cited = set(re.findall(r'\b(?:S[0-9]{3}|E[0-9]{2})\b', row['evidence_ids'].upper())) if row else set()
        needed = set(label['evidence_ids'].split(';'))
        evidence_checks[issue] = bool(cited and needed <= cited and cited <= set(source_index))
    business = sum(sum(checks[label['issue_id']][key] * weight for key, weight in oracle['field_weights'].items())
                   for label in expected) / len(expected)
    grouped = {group['key']: sum(all(checks[issue][key] for key in group['fields'])
                                for issue in group['issue_ids']) / len(group['issue_ids']) for group in boundary_groups}
    boundary = sum(grouped.values()) / len(grouped)
    minutes = root / contract['minutes']
    docx_ok = False
    if minutes.is_file() and not minutes.is_symlink():
        try:
            projection = native['extract_native_text'](minutes, max_chars=200_000)
            docx_ok = not projection['truncated'] and bool(projection['text'].strip())
        except (native['NativeTextError'], OSError):
            pass
    expected_ids = {label['issue_id'] for label in expected}
    unique_complete = set(counts) == expected_ids and all(value == 1 for value in counts.values())
    descriptions = sum(all(actual.get(issue, {}).get(key) for key in ('subject', 'status_reason', 'next_step'))
                       for issue in expected_ids) / len(expected_ids)
    delivery = (float(csv_complete) + float(docx_ok) + float(unique_complete) + descriptions + float(intact)) / 5
    if not (csv_ok or docx_ok):
        delivery = 0.0
    evidence = sum(evidence_checks.values()) / len(expected)
    if not intact:
        boundary, delivery, evidence = 0.0, 0.0, 0.0
    scores = {'business_correctness': business, 'boundary_cases': boundary,
              'delivery_integrity': delivery, 'evidence_binding': evidence}
    scores['overall_score'] = sum(scores[key] * weight for key, weight in oracle['checkpoint_weights'].items())
    return {'scores': scores, 'observations': {'csv_parseable': csv_ok, 'csv_complete_headers': csv_complete,
            'csv_error': csv_error, 'minutes_parseable': docx_ok,
            'protected_inputs_unchanged': intact, 'case_checks': checks, 'boundary_groups': grouped,
            'evidence_bindings': evidence_checks, 'unique_complete_issue_set': unique_complete}}


def grade(root):
    return evaluate(root)['scores']
