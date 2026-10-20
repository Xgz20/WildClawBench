"""Verify the generated-memory readback from its actual UI/native/tool evidence."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from eval_memory_e2e.io import publish


def verify(root,output=None):
    intent=json.loads((root/'recall2-send-intent.json').read_text())
    result=json.loads((root/'readback-native-completed.json').read_text())
    dom=json.loads((root/'recall2-send-dom-events.json').read_text())
    view=json.loads((root/'unit-view/scope.json').read_text())
    prior=json.loads((root/'automatic-formation-audit.json').read_text())
    origin=json.loads(Path(view['origin_scope']).read_text())
    case=next(iter(json.loads(Path(origin['batch_root'],'private/scenarios.json').read_text()).values()))
    target=case['facts'][case['cleanup']['target_fact']];keep=case['facts'][case['cleanup']['keep_fact']]
    assert target not in intent['prompt'] and keep not in intent['prompt']
    assert target in result['response'] and keep in result['response']
    assert result['status']['kind']=='completed' and result['session']['cwd']==intent['workspace']
    assert result['session']['turn_id']!=intent['native_binding']['previous_turn_id']
    assert sum(e['type']=='click' and e['trusted'] for e in dom['events'])==1
    assert sum(e['type']=='submit' and e['trusted'] for e in dom['events'])==1
    rows=[json.loads(s) for s in (root/'readback-full-rollout.jsonl').read_text().splitlines()]
    prompts=[''.join(c.get('text','') for c in r['payload'].get('content',[]) if c.get('type')=='input_text')
             for r in rows if r['type']=='response_item' and r['payload'].get('role')=='user']
    assert prompts.count(intent['prompt'])==1 and hashlib.sha256(intent['prompt'].encode()).hexdigest()==intent['prompt_sha256']
    start=next(i for i,r in enumerate(rows) if r['type']=='turn_context' and r['payload'].get('turn_id')==result['session']['turn_id'])
    context=rows[start]['payload'];assert context['model']=='builtin/eG9wZ2xtNTI' and context['effort']=='high' and context['cwd']==intent['workspace']
    calls=[r['payload'] for r in rows[start:] if r['type']=='response_item' and r['payload'].get('type')=='function_call']
    outputs={r['payload']['call_id']:r['payload'] for r in rows[start:] if r['type']=='response_item' and r['payload'].get('type')=='function_call_output'}
    memory=Path(view['paths']['overlay'])/'memories';reads=[]
    for call in calls:
        assert call['name'] in ('read','glob')
        args=json.loads(call['arguments'])
        if call['name']=='read':
            file=Path(args['file_path']);assert file.resolve()==file
            assert file in (memory/'MEMORY.md',memory/'raw_memories.md') or file.is_relative_to(memory/'rollout_summaries')
            text=outputs[call['call_id']]['output'];assert 'Error:' not in text
            reads.append({'path':str(file),'call_id':call['call_id'],'target_in_output':target in text,'keep_in_output':keep in text})
        else:
            assert args['path']==str(memory) and args['pattern'] in ('**/raw_memories.md','rollout_summaries/**')
    assert len(reads)==3 and len(calls)==5
    assert any(r['target_in_output'] and r['keep_in_output'] and '/rollout_summaries/' in r['path'] for r in reads)
    cycle=json.loads((root/'cycle-observations/0010.json').read_text())
    memory_files=[x for x in cycle['files'] if x['path'].endswith('.md')]
    assert all(hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()==x['sha256'] for x in memory_files)
    audit={'status':'PASS_GENERATED_MEMORY_UI_READBACK','operation_id':intent['operation_id'],'native':result['session'],
           'model':'builtin/eG9wZ2xtNTI','reasoning':'high','trusted_clicks':1,'trusted_submits':1,
           'prompt_contains_answer':False,'actual_reads':reads,'read_calls':3,'glob_calls':2,'write_calls':0,
           'generated_markdown_sha_unchanged':True,'no_ad_hoc_note_or_history_read':True,
           'same_ui_conversation':True,'new_turn_after_formation':True,'automatic_formation_audit_sha256':hashlib.sha256((root/'automatic-formation-audit.json').read_bytes()).hexdigest(),
           'stage1_partial_failure_preserved':prior['stage1_errors'],'global_memory_reset_verified':False,'formal20_prompts':0,'capability_score':None}
    publish(output or root/'automatic-readback-audit.json',audit)
    print(json.dumps({k:audit[k] for k in ('status','read_calls','glob_calls','write_calls','generated_markdown_sha_unchanged')},ensure_ascii=False))


if __name__=='__main__':verify(Path(sys.argv[1]),Path(sys.argv[2]) if len(sys.argv)>2 else None)
