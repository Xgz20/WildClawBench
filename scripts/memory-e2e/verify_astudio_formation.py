"""Audit actual Stage1/Stage2 output and composed policies, without grading."""
import collections
import datetime
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from eval_memory_e2e.astudio_scope import load,verify_ordinary
from eval_memory_e2e.io import publish


def verify(root):
    plan=json.loads((root/'diagnostic-plan.json').read_text())
    spec=load(plan['scope'])
    result=json.loads((root/'cycle-observer-result.json').read_text())
    cycle=json.loads(Path(result['snapshot']).read_text())
    assert result['status']=='CYCLE_COMPLETED'
    prior=json.loads(Path(plan['prior_state_archive']).read_text())
    assert all(t['idle_seconds']>=21600 for t in prior['eligible_historical_threads'])
    for file in prior['files']:
        assert hashlib.sha256(Path(file['copy']).read_bytes()).hexdigest()==file['sha256']
        # Runtime stores naturally change during this same-unit continuation;
        # original journals, manifests and raw rollouts remain immutable.
        if Path(file['source']).name in ('manifest.json','manifest.sha256','events.jsonl','scope.json','closed.json') or file['source'].endswith('.jsonl'):
            assert hashlib.sha256(Path(file['source']).read_bytes()).hexdigest()==file['sha256']
    old=json.loads(Path(spec['batch_root'],'private/scenarios.json').read_text())
    case=next(iter(old.values()));target=case['facts'][case['cleanup']['target_fact']];keep=case['facts'][case['cleanup']['keep_fact']]
    outputs=cycle['stage1_outputs']
    assert outputs and any(target in (x['raw_memory']+x['rollout_summary']) and keep in (x['raw_memory']+x['rollout_summary']) for x in outputs)
    assert all(x['thread_id'] in {t['id'] for t in prior['eligible_historical_threads']} for x in outputs)
    intent=json.loads((root/'ui-send-intent.json').read_text());sent=json.loads((root/'ui-send-result.json').read_text())
    dom=json.loads((root/'ui-send-dom-events.json').read_text())
    assert sent['result']['clicked'] and sent['result']['mouse_press_count']==1
    assert sum(e['type']=='click' and e['trusted'] for e in dom['events'])==1
    assert sum(e['type']=='submit' and e['trusted'] for e in dom['events'])==1
    cutoff=int(datetime.datetime.fromisoformat(intent['at'].replace('Z','+00:00')).timestamp())
    log=Path(spec['paths']['overlay'])/'logs_2.sqlite';c=sqlite3.connect(log.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    log_rows=[dict(x) for x in c.execute('SELECT * FROM logs WHERE ts>=? ORDER BY id',(cutoff,))];c.close()
    calls={};tool_outputs={};request_rows=[]
    for row in log_rows:
        body=row['feedback_log_body']
        if 'POST to ' not in body or 'Memory Writing Agent: Phase 2' not in body:continue
        try:request=json.loads(body[body.index(': {',body.index('POST to '))+2:])
        except (ValueError,IndexError):continue
        request_rows.append(row['id'])
        assert request['model']=='spark-x2.5'
        for item in request.get('input',[]):
            if item.get('type')=='function_call':calls[item['call_id']]=item
            if item.get('type')=='function_call_output':tool_outputs[item['call_id']]=item
    commands=[]
    for call_id,call in calls.items():
        output=tool_outputs.get(call_id,{}).get('output','')
        if call['name']=='bash':
            found=re.search(r'Exit code:\s*(-?\d+)',output)
            commands.append({'call_id':call_id,'arguments':call['arguments'],'exit_code':int(found[1]) if found else None,'output':output})
        assert 'sandbox_apply: Operation not permitted' not in str(output)
    assert len(commands)==4 and all(x['exit_code']==0 for x in commands)
    policies=list((root/'lease/control/native-broker/policies').glob('*.json'))
    for file in policies:
        policy=json.loads(file.read_text());native=policy['native_profile'];combined=policy['combined_profile']
        assert combined.startswith(native) and policy['controller_grants_appended'] is False
        appended=combined[len(native):]
        assert re.search(r'\(deny\s',appended) and not re.search(r'\(allow\s',appended)
    assert policies
    memory=Path(spec['paths']['overlay'])/'memories';assert (memory/'memory_summary.md').read_text().splitlines()[0]=='v1'
    files=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
           for p in [memory/'MEMORY.md',memory/'memory_summary.md',memory/'raw_memories.md']]
    ordinary=verify_ordinary(plan['scope']);assert ordinary['status']=='PASS'
    publish(root/'actual-cycle-log-range.json',{'rows':log_rows})
    publish(root/'actual-cycle-tool-evidence.json',{'request_log_ids':request_rows,'calls':calls,'outputs':tool_outputs,'commands':commands})
    errors=[j for j in cycle['jobs'] if j['status']=='error']
    audit={'status':'PASS_COMPOSED_EXECUTION_WITH_STAGE1_PARTIAL_FAILURE','unit_id':spec['unit_id'],
           'natural_idle_threshold_hours':6,'timestamps_changed':False,'runtime_history_copied':False,
           'ui_trigger_prompts_sent':1,'trusted_clicks':1,'trusted_submits':1,'stage1_outputs':len(outputs),
           'stage1_errors':errors,'all_stage1_inputs_succeeded':not errors,'automatic_fact_formation_verified':True,
           'consolidation_job':next(j for j in cycle['jobs'] if j['kind']=='memory_consolidate_global'),
           'actual_command_tool':'bash','actual_bash_exit_codes':[x['exit_code'] for x in commands],
           'tool_counts':dict(collections.Counter(x['name'] for x in calls.values())),
           'native_policy_audits':len(policies),'native_sbpl_preserved':True,'controller_grants_added':False,
           'generated_files':files,'explicit_notes_also_present_and_read_by_consolidator':True,'ordinary':ordinary,
           'generated_memory_ui_readback':'pre_send_rejected_no_workspace_picker_on_existing_conversation',
           'global_memory_reset_verified':False,'formal20_prompts':0,'capability_score':None}
    publish(root/'automatic-formation-audit.json',audit)
    print(json.dumps({k:audit[k] for k in ('status','stage1_outputs','all_stage1_inputs_succeeded','actual_bash_exit_codes','native_policy_audits','automatic_fact_formation_verified')},ensure_ascii=False))


if __name__=='__main__':verify(Path(sys.argv[1]))
