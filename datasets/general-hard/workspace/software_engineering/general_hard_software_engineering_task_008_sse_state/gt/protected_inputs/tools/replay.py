from pathlib import Path
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
FILES=['project/stream.py','project/state.py','project/render.py']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replay(case):
    stream=importlib.import_module('project.stream');state=importlib.import_module('project.state');render=importlib.import_module('project.render')
    current=state.new_state(case['request_id']);decoder=None;snapshots=[]
    for index,step in enumerate(case['steps']):
        decoded=[];states=[]
        if step['op']=='open':decoder=stream.SSEDecoder();current=state.mark_reconnected(current)
        elif step['op']=='disconnect':decoder.close();decoder=None;current=state.mark_disconnected(current)
        else:
            decoded=decoder.feed(bytes.fromhex(step['hex']))
            for event in decoded:current=state.apply_event(current,event);states.append(state.snapshot(current))
        snapshots.append({'step':index,'decoded':decoded,'states':states,'state':state.snapshot(current),'render':render.render_state(current)})
    result={'snapshots':snapshots,'final':state.snapshot(current),'final_render':render.render_state(current)}
    json.dumps(result,ensure_ascii=False,allow_nan=False);return result
rows=[]
for line in (root/'fixtures/events.jsonl').read_text().splitlines():
    case=json.loads(line)
    try:rows.append({'id':case['id'],'status':'ok','result':replay(case)})
    except BaseException as error:rows.append({'id':case['id'],'status':'error','error_type':type(error).__name__,'message':str(error)})
command=[sys.executable,'-B','-m','unittest','project.test_public','-v'];p=subprocess.run(command,cwd=root,text=True,capture_output=True,check=False,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
found=re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped[^\n]*)$',p.stderr,re.M)
report={'schema_version':'h048-replay/v1','source_sha256':{f:sha(root/f) for f in FILES},'input_sha256':{'fixtures/events.jsonl':sha(root/'fixtures/events.jsonl')},'cases':rows,
        'test_run':{'command':command,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'test_results':[{'test':a+' ('+b+')','status':c} for a,b,c in found]}}
output=root/'results/replay.json';output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'scenarios':len(rows),'errors':sum(r['status']=='error' for r in rows),'public_returncode':p.returncode}));sys.exit(p.returncode)
