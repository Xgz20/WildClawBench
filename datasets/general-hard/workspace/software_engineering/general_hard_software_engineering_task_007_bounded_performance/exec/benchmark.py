"""Protected reproducible benchmark command; elapsed time is information only."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import argparse
import hashlib
import json
import time
import instrumentation
import profile as matcher_profile

def output_bytes(value):
    value = json.loads(json.dumps(value, ensure_ascii=False))
    if not isinstance(value, list):
        raise ValueError('result must be a JSON-equivalent sequence')
    for row in value:
        if (not isinstance(row, dict) or set(row) != {'query_id', 'matched_by', 'row_ids'}
                or not isinstance(row['query_id'], str) or row['matched_by'] not in (*instrumentation.KINDS, 'unmatched')
                or not isinstance(row['row_ids'], list) or any(not isinstance(item, str) for item in row['row_ids'])):
            raise ValueError('result row outside public schema')
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def measure(source, case, maximum_work=5000000):
    function = matcher_profile.load_source(source)
    queries, catalog, snapshot = instrumentation.make_views(case, maximum_work)
    started = time.perf_counter()
    status = 'completed'
    digest = None
    error = None
    try:
        result = function(queries, catalog)
        digest = hashlib.sha256(output_bytes(result)).hexdigest()
    except instrumentation.WorkLimitExceeded:
        status = 'work_stop_limit'
    except Exception as exc:
        status = 'candidate_error'
        error = {'type': type(exc).__name__, 'message': str(exc)}
    return {'status': status, 'output_sha256': digest, **snapshot(), 'elapsed_seconds': time.perf_counter() - started,
            'error': error}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--matcher', default='project/matcher.py')
    parser.add_argument('--output', default='results/benchmark.json')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    candidate = root / args.matcher
    baseline = root / 'baseline_matcher.py'
    rows = []
    for path in sorted((root / 'fixtures').glob('*.json')):
        raw = path.read_bytes()
        case = json.loads(raw)
        before = measure(baseline.read_bytes(), case)
        after = measure(candidate.read_bytes(), case)
        rows.append({'case_id': case['case_id'], 'fixture_sha256': hashlib.sha256(raw).hexdigest(),
                     'before': before, 'after': after,
                     'equivalent': before['status'] == after['status'] == 'completed' and before['output_sha256'] == after['output_sha256']})
    report = {'schema_version': 'h047-benchmark/v1', 'work_profile': instrumentation.PROFILE,
        'python': {'implementation': sys.implementation.name, 'version': list(sys.version_info[:3])},
        'baseline_sha256': hashlib.sha256(baseline.read_bytes()).hexdigest(),
        'matcher_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
        'instrumentation_sha256': hashlib.sha256((root / 'instrumentation.py').read_bytes()).hexdigest(),
        'profile_sha256': hashlib.sha256((root / 'profile.py').read_bytes()).hexdigest(), 'cases': rows,
        'wall_time_is_gate': False, 'threads_required': False}
    target = root / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(target), 'cases': len(rows), 'elapsed_is_not_a_gate': True}))

if __name__ == '__main__':
    main()
