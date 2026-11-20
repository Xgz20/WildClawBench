"""Trusted isolated child; static profile plus immutable counted inputs, not OS sandbox."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import time

sys.dont_write_bytecode = True

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def main():
    request_path = Path(sys.argv[1]).resolve()
    response_path = Path(sys.argv[2]).resolve()
    request = json.loads(request_path.read_text(encoding='utf-8'))
    trusted = Path(__file__).resolve().parent / 'source_originals'
    instrumentation = load('instrumentation', trusted / 'instrumentation.py')
    profile = load('profile', trusted / 'profile.py')
    output = load('h047_trusted_output', trusted / 'benchmark.py')
    source = (request_path.parent / request['candidate_source']).read_bytes()
    baseline = (trusted / 'baseline_matcher.py').read_bytes()
    rows = []
    def measure(raw, case):
        try:
            function = profile.load_source(raw)
        except profile.ProfileUnsupported as exc:
            return {'status': 'profile_unsupported', 'error': str(exc)}
        except (SyntaxError, UnicodeError, ValueError, TypeError) as exc:
            return {'status': 'candidate_source_error', 'error': {'type': type(exc).__name__, 'message': str(exc)}}
        queries, catalog, snapshot = instrumentation.make_views(case, maximum_work=5000000)
        started = time.perf_counter()
        status = 'completed'
        result = None
        digest = None
        error = None
        try:
            result = json.loads(output.output_bytes(function(queries, catalog)))
            digest = hashlib.sha256(output.output_bytes(result)).hexdigest()
        except instrumentation.WorkLimitExceeded:
            status = 'work_stop_limit'
        except Exception as exc:
            status = 'candidate_error'
            error = {'type': type(exc).__name__, 'message': str(exc)}
        return {'status': status, 'output': result, 'output_sha256': digest, **snapshot(),
                'elapsed_seconds': time.perf_counter() - started, 'error': error}
    for case in request['cases']:
        before = measure(baseline, case) if case['case_id'] in request['public_case_ids'] else None
        current = measure(source, case)
        rows.append({'case_id': case['case_id'], 'before': before, 'after': current})
        if current['status'] == 'profile_unsupported':
            break
    response = {'schema_version': 'h047-actual-replay/v1', 'work_profile': instrumentation.PROFILE,
        'execution_profile': profile.PROFILE, 'isolated': bool(sys.flags.isolated),
        'python': {'implementation': sys.implementation.name, 'version': list(sys.version_info[:3])},
        'candidate_source_sha256': hashlib.sha256(source).hexdigest(),
        'baseline_source_sha256': hashlib.sha256(baseline).hexdigest(),
        'instrumentation_sha256': hashlib.sha256((trusted / 'instrumentation.py').read_bytes()).hexdigest(),
        'profile_sha256': hashlib.sha256((trusted / 'profile.py').read_bytes()).hexdigest(),
        'cases': rows,
        'actual_candidate_calls': sum(row['after']['status'] in {'completed', 'candidate_error', 'work_stop_limit'} for row in rows),
        'unsupported_source_executed': False,
        'wall_time_is_capability_gate': False, 'OS_sandbox_claimed': False}
    with response_path.open('x', encoding='utf-8') as handle:
        json.dump(response, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'status': 'REPLAY_RECORDED', 'cases': len(rows), 'response': str(response_path)}))

if __name__ == '__main__':
    main()
