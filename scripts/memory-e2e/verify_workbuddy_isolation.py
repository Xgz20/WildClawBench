"""Recompute A1 -> B1 -> A2 admission from immutable native evidence, no scoring."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval_memory_e2e.admission import response_json
from eval_memory_e2e.batch import load_batch
from eval_memory_e2e.io import events, publish, verify_artifact


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scan(folder, needles):
    count = size = skipped = 0
    hits = []
    for base, dirs, files in os.walk(folder, followlinks=False):
        for name in list(dirs):
            if Path(base, name).is_symlink():
                dirs.remove(name)
                skipped += 1
        for name in files:
            file = Path(base, name)
            if file.is_symlink():
                skipped += 1
                continue
            if not file.is_file():
                continue
            data = file.read_bytes()
            count += 1
            size += len(data)
            for needle in needles:
                if needle.encode() in data:
                    hits.append({'path': str(file), 'fact_sha256': sha(needle.encode())})
    return {'files': count, 'bytes': size, 'symlinks_not_followed': skipped, 'hits': hits}


def verify(base):
    rows, known, sessions, prompts, accounts = [], [], set(), set(), set()
    for label, case, repetition, key in [('A1','MEM-unit-A',1,'a'), ('B1','MEM-unit-B',1,'b'), ('A2','MEM-unit-A',2,'a')]:
        root = base / label
        manifest = load_batch(root)
        profile = manifest['profiles']['WorkBuddy']
        unit = profile['workbuddy_scope']
        accounts.add(unit['account_fingerprint'])
        assert manifest['dataset_id'] == 'memory-case-isolation-v2'
        assert manifest['scenario_ids'] == [case] and unit['repetition'] == repetition
        assert manifest['first_repetition'] == repetition and profile['memory_protocol']['formal_scoring_allowed'] is False
        cases = json.loads((root/'private/scenarios.json').read_text())
        journals = events(root)
        latest = {e['payload']['operation_id']: e['payload'] for e in journals if e['kind'] == 'RECEIPT'}
        replies, traces = [], []
        own, stored = None, []
        for episode in manifest['episodes']:
            scenario = cases[episode['private_key']]
            own = scenario['facts']['own_value']
            for receipt in latest.values():
                if receipt['episode_id'] != episode['id'] or receipt['step_id'] == 'prepare':
                    continue
                assert receipt['status'] == 'completed', (label, receipt['step_id'], receipt['status'])
                assert receipt['actual_config']['model_display'] == 'xopglm52'
                assert receipt['actual_config']['underlying_model'] == 'xopglm52'
                assert receipt['actual_config']['permissions'] == 'default-sandbox'
                native = receipt['native']
                assert native['session_id'] not in sessions
                sessions.add(native['session_id'])
                trace_bytes = verify_artifact(root, receipt['artifacts']['trace'])
                trace = json.loads(trace_bytes)
                req = trace['request']
                assert req['state'] == 'completed' and req['requestedModel']['id'] == 'custom-local:xopglm52'
                assert req['responseModel']['id'] == 'xopglm52'
                assert trace['native'] == native
                assert trace['selected_request_id'] == native['turn_id']
                state = json.loads((root/'.native/WorkBuddy'/receipt['operation_id']/'state.json').read_text())
                assert state['phase'] == 'invoked' and state['native'] == native
                source = state['prompt_input_evidence']['content']
                assert sha(source.encode()) == receipt['prompt_sha256']
                user = ''.join(x.get('text','') for x in req['userMessage']['content'] if x.get('type') == 'text')
                assert sha(user.encode()) == receipt['prompt_sha256']
                traces.append(trace_bytes)
                if receipt['step_id'] == 'seed':
                    for file in receipt.get('candidate_snapshot',[]):
                        if own.encode() in verify_artifact(root,file['artifact']):
                            stored.append({'channel':'workspace_files','file':file['workspace_path'],'artifact':file['artifact']})
                if receipt['step_id'] == 'recall':
                    prompts.add(receipt['prompt_sha256'])
                    observed = response_json(verify_artifact(root, receipt['artifacts']['final_response']).decode().strip(), 'single_json_object')
                    expected = {'a':'未知', 'b':'未知'}
                    if episode['arm'] == 'M+':
                        expected[key] = own
                    assert observed == expected, (label, episode['arm'], observed, expected)
                    replies.append({'arm': episode['arm'], 'operation_id':receipt['operation_id'], 'response':observed})
        assert len(traces) == 3 and len(replies) == 2 and isinstance(own,str) and stored
        for old in known:
            assert all(old.encode() not in trace for trace in traces), (label, 'old fact in native trace')
        scanned = {name: scan(root/name, known) for name in ('app-home','candidate','tmp')}
        assert not any(x['hits'] for x in scanned.values()), (label, 'old fact in unit data')
        audit = json.loads((root/'closed-audit.json').read_text())
        assert audit['ordinary_model_unchanged'] and audit['control_listeners'] == ''
        assert audit['supervisor']['main_exit'] == {'code':0,'signal':None}
        assert audit['supervisor']['gateway_exit'] == {'code':0,'signal':None}
        assert audit['temp_alias']['removed']
        for file in audit['memory_files']:
            assert sha(Path(file['path']).read_bytes()) == file['sha256'], ('old memory changed',file['path'])
        os_probe = json.loads((root/'app-home/admission-probe/result.json').read_text())
        assert os_probe['pass'] is True
        denials = 0
        if known:
            cross = json.loads((root/'cross-unit-control-receipt.json').read_text())
            assert cross['old_files_unchanged'] and cross['result']['pass']
            assert len(cross['old_files']) == len(known)
            assert all(t['denied'] and t['code'] == 'EPERM' for t in cross['result']['tests'])
            denials = len(cross['result']['tests'])
            assert denials == len(known)*5
        rows.append({'unit':label,'case':case,'repetition':repetition,'manifest_sha256':(root/'manifest.sha256').read_text().strip(),
                     'queries':replies,'old_facts_checked':len(known),'native_requests':3,'os_probe_pass':True,'unit_scan':scanned,
                     'memory_files_preserved':len(audit['memory_files']),'actual_old_unit_denials':denials,'observed_storage':stored})
        known.append(own)
    assert len(sessions) == 9 and len(prompts) == 1 and len(accounts) == 1
    return {'status':'PASS_WORKBUDDY_CASE_REPETITION_ISOLATION','native_requests':9,'distinct_sessions':9,
            'query_sha256':next(iter(prompts)),'units':rows,'capability_score':None,'formal20_prompts':0,
            'scope':'Observed current-account case x repetition isolation. Memory channels require separate trace review; automatic extraction and exhaustive external-broker isolation are not implied.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    result = verify(args.root)
    publish(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k!='units'},ensure_ascii=False))
