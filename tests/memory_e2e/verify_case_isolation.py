"""Recompute this admission from frozen native evidence, without model calls."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval_memory_e2e.batch import load_batch
from eval_memory_e2e.io import events, read_json, verify_artifact, require, publish, sha, timestamp
from eval_memory_e2e.admission import exact_response

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--generation-enabled', action='store_true',
                    help='Verify the same explicit-note isolation chain with native generation left enabled; not an automatic-fact-formation claim')
args = parser.parse_args()
prefix = 'generated' if args.generation_enabled else 'explicit'
units = [(prefix + '-A-r1', 'MEM-unit-A', 1, 'a'), (prefix + '-B-r1', 'MEM-unit-B', 1, 'b'),
         (prefix + '-A-r2', 'MEM-unit-A', 2, 'a')]
results, previous, queries, configs, native_ids, intents, kernels = [], [], [], [], [], [], []
for name, case_id, repetition, own_key in units:
    batch = args.root / 'batches' / name
    manifest = load_batch(batch)
    require(manifest['harnesses'] == ['AstronStudio'] and manifest['scenario_ids'] == [case_id]
            and manifest['repeats'] == 1 and manifest['first_repetition'] == repetition,
            'VERIFY_SCOPE', name)
    profile = manifest['profiles']['AstronStudio']
    kernels.append(profile.get('kernel'))
    require(profile['memory_protocol']['formal_scoring_allowed'] is False, 'VERIFY_NO_FORMAL', name)
    scope = profile['astudio_scope']
    require(scope['case_id'] == case_id and scope['repetition'] == repetition, 'VERIFY_UNIT_BINDING', name)
    case = read_json(batch / 'private/scenarios.json')[f'{case_id}/r{repetition:02d}']
    own = case['facts']['own_value']
    require(own not in previous, 'VERIFY_NEW_LEARNING_FACT', name)
    history = events(batch)
    receipts = {e['payload']['operation_id']: e['payload'] for e in history
                if e['kind'] == 'RECEIPT' and e['payload']['status'] == 'completed'
                and e['payload']['step_id'] != 'prepare'}
    require(len(receipts) == 3, 'VERIFY_PROMPT_COUNT', name)
    bindings = {e['payload']['operation_id']: e for e in history if e['kind'] == 'INTENT'
                and e['payload']['request']['action'] == 'execute_step'}
    require(set(bindings) == set(receipts), 'VERIFY_NO_EXTRA_SEND', name)
    intents.extend(bindings)
    checks, trace_leaks, tool_calls = [], [], []
    for operation, row in receipts.items():
        for artifact in row['artifacts'].values():
            verify_artifact(batch, artifact)
        native_ids.append((row['native']['session_id'], row['native']['turn_id']))
        configs.append(row['actual_config'])
        request = bindings[operation]['payload']['request']
        require(any(e['kind'] == 'OS_BOUNDARY_VERIFIED' and e['payload']['operation_id'] == operation
                    and e['sequence'] < bindings[operation]['sequence'] for e in history),
                'VERIFY_BOUNDARY_BEFORE_INTENT', operation)
        state = read_json(batch / '.native/AstronStudio' / operation / 'state.json')
        require(state['click_result']['clicked'] is True and state['click_result']['mouse_press_count'] == 1,
                'VERIFY_SINGLE_PRESS', operation)
        observed = list((batch / '.native/AstronStudio' / operation).glob('send-dom-events-*.json'))
        require(len(observed) == 1, 'VERIFY_DOM_EVIDENCE', operation)
        dom = read_json(observed[0])
        require(sum(e.get('type') == 'click' for e in dom['events']) == 1
                and sum(e.get('type') == 'submit' for e in dom['events']) == 1
                and all(e.get('trusted') is True for e in dom['events']) and dom['dropped_events'] == 0,
                'VERIFY_SINGLE_SUBMIT', operation)
        raw = verify_artifact(batch, row['artifacts']['trace'])
        leaks = [sha(value.encode()) for value in previous if value.lower().encode() in raw.lower()]
        trace_leaks.extend(leaks)
        for line in raw.splitlines():
            entry = json.loads(line)
            payload = entry.get('payload', {})
            if entry.get('type') == 'response_item' and payload.get('type') == 'function_call':
                tool_calls.append({'name': payload.get('name'), 'call_id': payload.get('call_id')})
        if request['step_id'] == 'recall':
            expected = {'a': '未知', 'b': '未知'}
            if row['episode_id'].endswith('experienced'):
                expected[own_key] = own
            checked = exact_response(batch, row, expected, 'single_json_object')
            require(checked['passed'], 'VERIFY_RECALL', name + ' ' + row['episode_id'])
            checks.append({'arm': request['arm'], 'passed': True, 'response': row['artifacts']['final_response']})
            queries.append(request['prompt_sha256'])
    require(not trace_leaks, 'VERIFY_OLD_FACT_IN_NATIVE_TRACE', name)
    require(len(checks) == 2, 'VERIFY_CHECKPOINT_COUNT', name)
    # Inspect all owned runtime files after shutdown, including logs/SQLite and
    # source conversations, to catch retrieval that a final answer might hide.
    runtime = Path(scope['paths']['runtime'])
    scanned, total, skipped_links, storage_leaks = 0, 0, [], []
    for storage_root in (runtime, Path(scope['paths']['candidate'])):
        for directory, dirs, files in os.walk(storage_root, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
            for filename in files:
                path = Path(directory) / filename
                if path.is_symlink():
                    skipped_links.append(str(path)); continue
                size = path.stat().st_size
                require(size < 200 * 1024 * 1024 and total + size < 2 * 1024 ** 3,
                        'VERIFY_RUNTIME_SCAN_BUDGET', str(path))
                data = path.read_bytes(); scanned += 1; total += size
                hits = [sha(value.encode()) for value in previous if value.lower().encode() in data.lower()]
                if hits:
                    storage_leaks.append({'path': str(path), 'old_fact_hashes': hits})
    require(not storage_leaks, 'VERIFY_OLD_FACT_IN_RUNTIME', name)
    closed = read_json(args.root / 'units' / name / 'closed.json')
    preclose = args.root / (name + '-idle-before-close.json')
    if not preclose.exists():
        available = list((args.root / 'units' / name).glob('close-idle-*.json'))
        require(len(available) == 1, 'VERIFY_IDLE_PROOF', name)
        preclose = available[0]
    idle = read_json(preclose)
    require(idle['unit_id'] == scope['unit_id'] and idle['idle'] is True and idle['running_jobs'] == 0
            and idle['blocking_session_count'] == 0 and idle['native_session_count'] == 3,
            'VERIFY_IDLE_BEFORE_CLOSE', name)
    require(closed['all_execution_roots_exited']
            and closed['ordinary']['status'] == 'PASS', 'VERIFY_CLOSEOUT', name)
    results.append({'unit': name, 'case_id': case_id, 'repetition': repetition, 'unit_id': scope['unit_id'],
                    'completed_prompts': 3, 'recall_checks': checks, 'old_fact_trace_hits': trace_leaks,
                    'old_fact_runtime_hits': storage_leaks, 'runtime_files_scanned': scanned,
                    'runtime_bytes_scanned': total, 'skipped_file_symlinks': skipped_links,
                    'visible_function_calls': tool_calls, 'account_fingerprint': scope['account_fingerprint'],
                    'original_unchanged': True})
    previous.append(own)
require(len(set(queries)) == 1, 'VERIFY_IDENTICAL_QUERIES', 'All six probes must have the same frozen user input')
require(len(set(native_ids)) == 9 and len({x[0] for x in native_ids}) == 9 and len(set(intents)) == 9,
        'VERIFY_INDEPENDENT_NATIVE_OPERATIONS', 'Nine distinct native sessions and single sends required')
require(len({c['account_fingerprint'] for c in configs}) == 1, 'VERIFY_SAME_ACCOUNT', 'UID changed')
require(len({json.dumps(c['memory_settings'], sort_keys=True) for c in configs}) == 1,
        'VERIFY_SAME_MEMORY_CONDITION', 'Memory settings differ across units')
for config in configs:
    require(config['app_version'] == '3.5.0' and config['model_display'] == 'GLM-5.2'
            and config['reasoning'] == 'High' and config['permissions'] == '完全访问', 'VERIFY_CONFIGURATION', 'Configuration differs')
    require(all(x['enabled'] and x['use_memories'] and x['dedicated_tools'] and x['generate_memories'] is args.generation_enabled
                for x in config['memory_settings'].values()), 'VERIFY_MEMORY_CONFIGURATION', 'Memory condition differs')
require(all(kernels) and len({json.dumps(x, sort_keys=True) for x in kernels}) == 1,
        'VERIFY_SAME_KERNEL', 'All case/repetition units must use the same frozen kernel')
cross = [read_json(args.root / name) for name in ('B1-deny-A1.json', 'A2-deny-A1-B1.json')]
require(all(x['status'] == 'PASS' and x['filesystem_probe']['pass'] for x in cross), 'VERIFY_CROSS_UNIT_FS', 'Cross-unit denial failed')
for proof in cross:
    require(all(sha(Path(row['path']).read_bytes()) == row['sha256'] for row in proof['old_synthetic_notes']),
            'VERIFY_OLD_NOTES_PRESERVED', 'First-round facts were changed or removed')
record = {'status': 'PASS_MEMORY_UNIT_ISOLATION_GENERATION_ENABLED' if args.generation_enabled else 'PASS_EXPLICIT_MEMORY_UNIT_ISOLATION',
          'at': timestamp(), 'completed_prompts': 9,
          'distinct_native_sessions': 9, 'identical_query_sha256': queries[0], 'within_unit_recall_passed': 3,
          'cross_case_passed': True, 'cross_repetition_passed': True, 'units': results,
          'actual_cross_unit_fs_denials': sum(len(x['filesystem_probe']['operations']) for x in cross),
          'actual_backend_kernel_denial_queries': sum(len(x['actual_backend_kernel_policy']) * 4 for x in cross),
          'old_notes_preserved': True, 'ordinary_account_memory_reset': False, 'formal20_started': False,
          'automatic_consolidation_admitted': False, 'scoring': 'UNSCORED',
          'generation_enabled': args.generation_enabled, 'learning_mode': 'explicit_native_notes',
          'automatic_fact_formation_verified': False, 'frozen_kernel': kernels[0],
          'source_sha256': sha(Path(__file__).read_bytes())}
publish(args.output, record)
print(json.dumps({k: v for k, v in record.items() if k != 'units'}, ensure_ascii=False))
