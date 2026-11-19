from pathlib import Path
import importlib
import json
import sys

workspace,gt,request_file,output=map(Path,sys.argv[1:]);request=json.loads(request_file.read_text());sys.path.insert(0,str(workspace))
output.write_text(json.dumps({'phase':'candidate_start'})+'\n')
try:
    stream=importlib.import_module('project.stream');state=importlib.import_module('project.state');render=importlib.import_module('project.render');load_error=None
except BaseException as error:load_error=type(error).__name__+': '+str(error)
S=['request_id','status','body','reasoning','last_seq','done','error'];V=['markdown','reasoning','status','completed','error']
def snapshot(value):return {k:value[k] for k in S}
def rendered(value):return {k:value[k] for k in V}
def normalize(value):
    return {'snapshots':[{'step':x['step'],'decoded':[{k:e[k] for k in ['id','event','data']} for e in x['decoded']],
             'states':[snapshot(v) for v in x['states']],'state':snapshot(x['state']),'render':rendered(x['render'])} for x in value['snapshots']],
            'final':snapshot(value['final']),'final_render':rendered(value['final_render'])}
def observe(case):
    try:
        if load_error:raise RuntimeError(load_error)
        current=state.new_state(case['request_id']);decoder=None;observations=[]
        for index,step in enumerate(case['steps']):
            decoded=[];states=[]
            if step['op']=='open':decoder=stream.SSEDecoder();current=state.mark_reconnected(current)
            elif step['op']=='disconnect':decoder.close();decoder=None;current=state.mark_disconnected(current)
            else:
                decoded=decoder.feed(bytes.fromhex(step['hex']))
                for event in decoded:current=state.apply_event(current,event);states.append(state.snapshot(current))
            observations.append({'step':index,'decoded':decoded,'states':states,'state':state.snapshot(current),'render':render.render_state(current)})
        result=normalize({'snapshots':observations,'final':state.snapshot(current),'final_render':render.render_state(current)})
        json.dumps(result,allow_nan=False);return {'status':'ok','result':result}
    except BaseException as error:return {'status':'error','error_type':type(error).__name__,'message':str(error)}
def equal(a,b):
    if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b
rows=[]
for case in request['cases']:
    actual=observe(case);prefix_count=len(case['expected']['snapshots']);passed=0;final=False
    if actual['status']=='ok':
        result=actual['result'];final=equal(result['final'],case['expected']['final']) and equal(result['final_render'],case['expected']['final_render'])
        passed=sum(index<len(result['snapshots']) and equal(result['snapshots'][index],expected) for index,expected in enumerate(case['expected']['snapshots']))
    score=.5*float(final)+.5*passed/prefix_count
    rows.append({'id':case['id'],'group':case['group'],'score':score,'final_passed':final,'prefix_passed':passed,'prefix_count':prefix_count,'actual':actual})
provided=request.get('report_cases');provided=provided if isinstance(provided,list) else []
checks=[];public=[]
for case in request['public_cases']:
    actual=observe(case);public.append({'id':case['id'],**actual});found=[r for r in provided if isinstance(r,dict) and r.get('id')==case['id']];passed=False
    if len(found)==1:
        item=found[0]
        try:passed=(item.get('status')=='error' and actual['status']=='error' and item.get('error_type')==actual['error_type']) or (item.get('status')=='ok' and actual['status']=='ok' and equal(normalize(item['result']),actual['result']))
        except BaseException:passed=False
    checks.append({'id':case['id'],'passed':bool(passed)})
output.write_text(json.dumps({'schema':'h048-independent-prefix-run/v1','cases':rows,'public_generated':public,'report_checks':checks},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'scenarios':len(rows),'full':sum(r['score']==1 for r in rows),'prefixes':sum(r['prefix_count'] for r in rows),'report_matches':sum(c['passed'] for c in checks)}))
