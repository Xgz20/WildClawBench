from pathlib import Path
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import subprocess
import sys

WEIGHTS = {'business_correctness': .55, 'boundary_cases': .25, 'delivery_integrity': .15, 'evidence_binding': .05}

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return int(result) if result.is_finite() and result == result.to_integral_value() else None
    except (ValueError, TypeError, InvalidOperation):
        return None

def hex_equal(value, expected):
    return isinstance(value, str) and value.lower() == expected

def grade(**kwargs):
    root = Path(kwargs.get('workspace_path') or '/tmp_workspace')
    gt = root / 'gt'
    trusted_path = gt / 'trusted_files.json'
    if not trusted_path.is_file() or trusted_path.is_symlink():
        raise RuntimeError('H047_TRUSTED_CONTEXT_MISSING_OR_DRIFT: trusted_files.json')
    trusted = read(trusted_path)
    for relative, digest in trusted.items():
        path = gt / relative
        if not path.is_file() or path.is_symlink() or sha(path) != digest:
            raise RuntimeError('H047_TRUSTED_CONTEXT_MISSING_OR_DRIFT: ' + relative)
    expected = read(gt / 'expected.json')
    oracle = read(gt / 'business_oracle.json')
    protected = read(gt / 'protected_sha256.json')
    runtime = read(gt / 'runtime_contract.json')
    context = os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not context:
        raise RuntimeError('H047_RULE_EVIDENCE_CONTEXT_REQUIRED')
    derived = Path(context) / 'actual-replay'
    derived.mkdir(parents=True, exist_ok=False)
    def safe(path):
        return path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve())
    source_path = root / 'project/matcher.py'
    source = source_path.read_bytes() if safe(source_path) else b''
    source_sha = hashlib.sha256(source).hexdigest()
    (derived / 'candidate-source.py').write_bytes(source)
    public_paths = sorted((gt / 'source_originals/fixtures').glob('*.json'))
    public = [read(path) for path in public_paths]
    cases = public + read(gt / 'hidden_cases.json')
    public_ids = [case['case_id'] for case in public]
    request = {'schema_version': 'h047-replay-request/v1', 'candidate_source': 'candidate-source.py',
        'candidate_source_sha256': source_sha, 'cases': cases, 'public_case_ids': public_ids,
        'case_truth_sha256': sha(gt / 'expected.json'), 'source_policy': 'frozen candidate source plus trusted private original counter/profile/baseline',
        'infrastructure_timeout_is_capability_gate': False}
    request_path = derived / 'request.json'
    response_path = derived / 'response.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    command = [sys.executable, '-I', '-B', '-X', 'utf8', str(gt / 'runner.py'), str(request_path), str(response_path)]
    invocation = {'argv': command, 'cwd': str(derived), 'timeout_seconds': runtime['child_timeout_seconds'], 'OS_sandbox_claimed': False}
    (derived / 'invocation.json').write_text(json.dumps(invocation, indent=2) + '\n', encoding='utf-8')
    try:
        process = subprocess.run(command, cwd=derived, capture_output=True, text=True, encoding='utf-8', timeout=runtime['child_timeout_seconds'],
            env={key: value for key, value in os.environ.items() if key in {'PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'PYTHONUTF8'}})
    except subprocess.TimeoutExpired as exc:
        (derived / 'incomplete.json').write_text(json.dumps({'status': 'unassessed_infrastructure_timeout', 'candidate_zero': False,
            'timeout_seconds': runtime['child_timeout_seconds']}, indent=2) + '\n', encoding='utf-8')
        raise RuntimeError('H047_REPLAY_TIMEOUT_UNASSESSED_NO_CANDIDATE_ZERO') from exc
    (derived / 'stdout.log').write_text(process.stdout, encoding='utf-8')
    (derived / 'stderr.log').write_text(process.stderr, encoding='utf-8')
    if process.returncode or not response_path.is_file():
        raise RuntimeError('H047_REPLAY_INFRASTRUCTURE_FAILED: ' + str(process.returncode))
    replay = read(response_path)
    if not replay['isolated'] or replay['candidate_source_sha256'] != source_sha:
        raise RuntimeError('H047_REPLAY_BINDING_INVALID')
    actual = {row['case_id']: row for row in replay['cases']}
    if any(row['after']['status'] == 'profile_unsupported' for row in actual.values()):
        error = next(row['after']['error'] for row in actual.values() if row['after']['status'] == 'profile_unsupported')
        raise RuntimeError('H047_CANDIDATE_PROFILE_UNSUPPORTED_UNASSESSED: ' + error)
    if set(actual) != set(expected):
        raise RuntimeError('H047_REPLAY_CASES_INCOMPLETE')
    for case_id in public_ids:
        before = actual[case_id]['before']
        if before['status'] != 'completed' or before['output_sha256'] != expected[case_id]['output_sha256']:
            raise RuntimeError('H047_TRUSTED_BASELINE_OR_SOURCE_TRUTH_MISMATCH: ' + case_id)

    semantic = []
    # Every frozen workload has independent semantic truth as well. Otherwise
    # deliberately returning wrong results only on scale cases could turn a
    # neutral, unassessed work conclusion into an undeserved full score.
    for case_id in expected:
        after = actual[case_id]['after']
        if after['status'] == 'work_stop_limit':
            raise RuntimeError('H047_SEMANTIC_REPLAY_INCOMPLETE_WORK_STOP_UNASSESSED: ' + case_id)
        target = expected[case_id]['output']
        got = after.get('output') if after['status'] == 'completed' else None
        if not isinstance(got, list) or len(got) != len(target):
            value = 0.0
        elif not target:
            value = 1.0
        else:
            value = sum(row == wanted for row, wanted in zip(got, target)) / len(target)
        semantic.append({'case_id': case_id, 'fraction': value, 'status': after['status']})
    business = sum(row['fraction'] for row in semantic) / len(semantic)
    workload = []
    for case_id in oracle['performance_cases']:
        after = actual[case_id]['after']
        equivalent = after['status'] == 'completed' and after['output_sha256'] == expected[case_id]['output_sha256']
        if after['status'] == 'work_stop_limit':
            status, value = 'proven_over_stop_work_ceiling', 0.0
        elif not equivalent:
            status, value = 'not_assessed_non_equivalent_output', 1.0
        else:
            value = float(after['total_work'] <= expected[case_id]['work_bound'])
            status = 'verified_within_bound' if value else 'verified_over_bound'
        workload.append({'case_id': case_id, 'status': status, 'score': value,
            'actual_work': after.get('total_work'), 'bound': expected[case_id]['work_bound'], 'output_equivalent': equivalent})
    boundary = sum(row['score'] for row in workload) / len(workload)

    protected_actual = {}
    for path in root.rglob('*'):
        relative = path.relative_to(root).as_posix()
        if relative.split('/')[0] in {'gt', 'results'} or relative == 'project/matcher.py':
            continue
        if path.is_symlink():
            protected_actual[relative] = 'SYMLINK'
        elif path.is_file():
            protected_actual[relative] = sha(path)
    protected_ok = protected_actual == protected
    benchmark = None
    review_text = None
    try:
        path = root / 'results/benchmark.json'
        if safe(path):
            value = read(path)
            if isinstance(value, dict):
                benchmark = value
    except (ValueError, UnicodeError, OSError):
        pass
    try:
        path = root / 'results/review.md'
        if safe(path):
            review_text = path.read_text(encoding='utf-8-sig')
    except (UnicodeError, OSError):
        pass
    delivery = .8 * float(protected_ok) + .1 * float(benchmark is not None) + .1 * float(bool(review_text and review_text.strip()))
    metadata = benchmark or {}
    source_bindings = [hex_equal(metadata.get('matcher_sha256'), source_sha),
        hex_equal(metadata.get('baseline_sha256'), replay['baseline_source_sha256']),
        hex_equal(metadata.get('instrumentation_sha256'), replay['instrumentation_sha256']),
        hex_equal(metadata.get('profile_sha256'), replay['profile_sha256']),
        metadata.get('work_profile') == 'h047-counted-keys/v1', metadata.get('wall_time_is_gate') is False, metadata.get('threads_required') is False]
    report_rows = metadata.get('cases') if isinstance(metadata.get('cases'), list) else []
    reported_checks = []
    fixture_hashes = {read(path)['case_id']: sha(path) for path in public_paths}
    for case_id in public_ids:
        matching = [row for row in report_rows if isinstance(row, dict) and row.get('case_id') == case_id]
        if len(matching) != 1:
            reported_checks.append(False)
            continue
        row = matching[0]
        checks = [hex_equal(row.get('fixture_sha256'), fixture_hashes[case_id])]
        for side in ('before', 'after'):
            report = row.get(side) if isinstance(row.get(side), dict) else {}
            observed = actual[case_id][side]
            counters = report.get('counters') if isinstance(report.get('counters'), dict) else {}
            checks.extend([report.get('status') == observed['status'],
                hex_equal(report.get('output_sha256'), observed['output_sha256']) if observed.get('output_sha256') else report.get('output_sha256') is None,
                number(report.get('total_work')) == observed.get('total_work'),
                set(counters) == set(observed.get('counters', {})),
                all(number(counters.get(name)) == value for name, value in observed.get('counters', {}).items())])
        observed_equivalence = actual[case_id]['after']['status'] == 'completed' and actual[case_id]['after'].get('output_sha256') == actual[case_id]['before']['output_sha256']
        checks.append(row.get('equivalent') is observed_equivalence)
        reported_checks.append(all(checks))
    summary = None
    if review_text:
        for block in re.findall(r'```(?:json|JSON)\s*\n(.*?)\n```', review_text, flags=re.S):
            try:
                value = json.loads(block)
                if isinstance(value, dict) and 'algorithm_family' in value:
                    summary = value
                    break
            except ValueError:
                continue
    summary = summary or {}
    summary_ids = summary.get('public_case_ids')
    review_bindings = [isinstance(summary.get('algorithm_family'), str) and bool(summary['algorithm_family'].strip()),
        hex_equal(summary.get('before_source_sha256'), replay['baseline_source_sha256']), hex_equal(summary.get('after_source_sha256'), source_sha),
        isinstance(summary_ids, list) and len(summary_ids) == len(public_ids) and all(isinstance(item, str) for item in summary_ids) and set(summary_ids) == set(public_ids),
        summary.get('work_measure') == 'h047-counted-keys/v1', summary.get('wall_time_is_gate') is False, summary.get('threads_required') is False]
    evidence = .2 * sum(source_bindings) / len(source_bindings) + .6 * sum(reported_checks) / len(reported_checks) + .2 * sum(review_bindings) / len(review_bindings)
    observations = {'schema_version': 'h047-scoring-observations/v1', 'candidate_source_sha256': source_sha,
        'semantic_cases': semantic, 'workload': workload, 'protected_inputs_intact': protected_ok,
        'source_report_bindings': source_bindings, 'public_actual_counter_report_checks': reported_checks,
        'review_summary_bindings': review_bindings,
        'scope': 'Actual pure-profile candidate replay and trusted counted views; no OS sandbox or real Harness/Judge claim.',
        'non_equivalent_workload_neutral_is_not_verified': True, 'elapsed_time_not_a_capability_gate': True}
    (derived / 'scoring-observations.json').write_text(json.dumps(observations, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    scores = {'business_correctness': business, 'boundary_cases': boundary, 'delivery_integrity': delivery, 'evidence_binding': evidence}
    scores['overall_score'] = sum(scores[key] * weight for key, weight in WEIGHTS.items())
    print(json.dumps({'h047_actual_scores': scores, 'workload_status': [row['status'] for row in workload], 'counter_reports': reported_checks}))
    return scores
