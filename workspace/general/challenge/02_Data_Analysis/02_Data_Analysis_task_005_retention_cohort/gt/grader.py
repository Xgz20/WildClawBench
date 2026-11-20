"""Retention cohort task: complete sets, source witnesses, and real HTML paint."""
from pathlib import Path
import hashlib
import json
import os
import runpy

def grade(workspace):
    root = Path(workspace).resolve()
    private = root / 'gt'
    def load(name):
        return json.loads((private / name).read_text(encoding='utf-8'))
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    binding = load('scoring_contract.json')
    if binding.get('schema_version') != 'h021-scoring/v1':
        raise RuntimeError('H021 private scoring contract invalid')
    for name, digest in binding['private_sha256'].items():
        if sha(private / name) != digest:
            raise RuntimeError('H021 private source/helper drift: ' + name)
    expected = load('expected.json')
    contract = load('runtime_contract.json')
    source = load('source_bindings.json')['records']
    if expected.get('status') != 'native_csv_and_dashboard_two_path_verified' or contract.get('grading_type') != 'automated' or [len(expected[k]) for k in ['audit', 'user_days', 'memberships', 'summaries']] != [1200, 500, 476, 30]:
        raise RuntimeError('H021 private retention truth invalid')
    ledger_api = runpy.run_path(str(private / 'h021_ledger.py'))
    html_api = runpy.run_path(str(private / 'h021_html.py'))
    T = ledger_api['T']
    office = runpy.run_path(str(private / 'office_runtime.py'))
    html = runpy.run_path(str(private / contract['html_helper']))
    for name in ['GENERAL_E2E_OFFICE_LOCK', 'GENERAL_E2E_HTML_LOCK', 'GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):
            raise RuntimeError('H021 managed scoring runtime missing ' + name)
    office_lock = json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text(encoding='utf-8'))
    html_lock = json.loads(Path(os.environ['GENERAL_E2E_HTML_LOCK']).read_text(encoding='utf-8'))
    office['validate_office_lock'](office_lock)
    html['validate_html_lock'](html_lock)
    derived = Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived == root or derived.is_relative_to(root):
        raise RuntimeError('H021 derived observations must be outside candidate Workspace')
    protected = load(contract.get('protected_file', 'protected_sha256.json'))
    intact = all((root / name).is_file() and not (root / name).is_symlink() and sha(root / name) == digest for name, digest in protected.items())
    parsed = {'cohorts.xlsx': False, 'anomalies.json': False, 'report.html': False}
    errors = {}
    mean = ledger_api['average']
    results = {}
    calculation = None

    def candidate(name):
        path = root / 'results' / name
        if (root / 'results').is_symlink() or path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 5 * 1024 * 1024:
            raise T['CandidateError']('missing, symbolic or oversized delivery ' + name)
        return path

    def attempt(name, action):
        try:
            value = action()
            parsed[name] = True
            return value
        except T['CandidateError'] as exc:
            errors[name] = str(exc)
            return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in {'OFFICE_INPUT_INVALID', 'OFFICE_INPUT_LIMIT', 'OFFICE_ACTIVE_CONTENT_UNSUPPORTED', 'OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:
                raise
            errors[name] = exc.code
            return None

    def read_xlsx():
        nonlocal calculation
        path = candidate('cohorts.xlsx')
        original = T['read_book'](path)
        office['_clean_package'](path.read_bytes())
        calculation = office['recalculate_xlsx'](path, office_lock, derived / 'cohort-recalculation', timeout_seconds=90)
        calculated = T['read_book'](calculation['path'])
        previous = {s['name']: s for s in original}
        for sheet in calculated:
            if sheet['name'] not in previous:
                raise RuntimeError('H021 trusted Office changed sheet identity')
            for position, cell in sheet['cells'].items():
                old = previous[sheet['name']]['cells'].get(position)
                cell['visible'] = cell['visible'] and old is not None and old['visible']
        observation = ledger_api['ledger'](calculated, expected, contract, source)
        observation['native_errors'] = [error for sheet in calculated for error in sheet['errors']]
        return observation

    def read_json():
        try:
            value = json.loads(candidate('anomalies.json').read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError) as exc:
            raise T['CandidateError']('invalid anomalies JSON') from exc
        if not isinstance(value, dict) or not isinstance(value.get('anomalies'), list):
            raise T['CandidateError']('anomalies object/list required')
        return ledger_api['anomaly_facts'](value, expected, contract, source)

    book = attempt('cohorts.xlsx', read_xlsx)
    anomalies = attempt('anomalies.json', read_json)
    report = attempt('report.html', lambda: html_api['assess_html'](candidate('report.html'), html_lock, derived, expected, contract, resource_root=root))
    if book is None:
        book = {'summary_score': 0., 'members_score': 0., 'user_day_score': 0., 'evidence_score': 0., 'boundary_score': 0., 'complete_detail': False,
            'checks': {'summaries': {}, 'memberships': {}, 'user_days': {}, 'audit': {}}, 'tables': {}, 'headers': {}, 'findings': [], 'audit_groups': {}, 'native_errors': []}
    if anomalies is None:
        anomalies = {'facts': 0., 'evidence': 0., 'findings': []}
    if report is None:
        report = {'table': {'score': 0., 'rows': []}, 'chart': {'points': 0., 'gaps': 0.}, 'offline_dependencies': False, 'render_usable': False,
            'visible_evidence': {'score': 0., 'cutoff_visible': False, 'observation_limit_visible': False}}
    graph = .7 * report['chart']['points'] + .3 * report['chart']['gaps']
    scores = {
        'business_correctness': .30 * book['summary_score'] + .25 * book['members_score'] + .10 * book['user_day_score'] + .15 * anomalies['facts'] + .20 * graph,
        'boundary_cases': .85 * book['boundary_score'] + .15 * report['chart']['gaps'],
        'delivery_integrity': 0.,
        'evidence_binding': .6 * book['evidence_score'] + .25 * anomalies['evidence'] + .15 * report['visible_evidence']['score'],
    }
    # These compare independent truth on both surfaces, so a correct chart does
    # not cover wrong Excel member sets or event classifications.
    cross = mean(bool(book['checks']['summaries'].get(tuple(row['key']))) and all(book['checks']['summaries'][tuple(row['key'])].values()) and row['passed']
        for row in report['table']['rows']) if len(report['table']['rows']) == 30 else 0.
    native_usable = bool(parsed['cohorts.xlsx'] and book['complete_detail'] and not book['native_errors'])
    parsed_usable = mean([native_usable, parsed['anomalies.json'], parsed['report.html'] and report['render_usable'] and report['offline_dependencies']])
    report_handoff = .8 * report['visible_evidence']['score'] + .1 * report['visible_evidence']['cutoff_visible'] + .1 * report['visible_evidence']['observation_limit_visible']
    scores['delivery_integrity'] = .2 * parsed_usable + .2 * report['table']['score'] + .2 * graph + .2 * cross + .2 * report_handoff
    cap = None
    if not book['complete_detail']:
        scores['business_correctness'] = min(scores['business_correctness'], .5)
        cap = 'complete event/user-day/member ledgers absent'
    if not intact:
        scores['business_correctness'] = min(scores['business_correctness'], .5)
        scores['boundary_cases'] = scores['delivery_integrity'] = scores['evidence_binding'] = 0.
        cap = 'frozen input changed'
    scores = {key: round(value, 12) for key, value in scores.items()}
    scores['overall_score'] = round(sum(scores[key] * weight for key, weight in binding['checkpoint_weights'].items()), 12)
    if any(not 0 <= value <= 1 for value in scores.values()):
        raise RuntimeError('H021 invalid score range')

    def serializable(value):
        if isinstance(value, dict):
            return {('|'.join(map(str, key)) if isinstance(key, tuple) else str(key)): serializable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [serializable(item) for item in value]
        return value
    observation = {'schema_version': 'h021-rule-observations/v1', 'scores': scores, 'input_unchanged': intact,
        'parsed_deliveries': parsed, 'candidate_errors': errors, 'business_cap_reason': cap,
        'ledger': {k: v for k, v in book.items() if k != 'tables'}, 'anomalies': anomalies,
        'report': report, 'office_baseline': calculation, 'cross_surface_summary': cross,
        'limit': 'Automated structural/source/set/numeric/native-paint verification. Difficulty, model/Harness discrimination and production execution are not proven by author fixtures.'}
    derived.mkdir(parents=True, exist_ok=True)
    with (derived / 'h021-analysis.json').open('x', encoding='utf-8') as stream:
        json.dump(serializable(observation), stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return scores
