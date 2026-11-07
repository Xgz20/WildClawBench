"""Read only native judge identity, prompt transport and turn boundaries.

Never exports model reasoning or arbitrary SDK message/tool contents.
"""
import hashlib,json,pathlib,xml.etree.ElementTree as ET
from datetime import datetime

def _require(ok,code):
    if not ok:raise ValueError(code)

def native_turn_boundaries(rows,contexts,*,allow_running):
    """Keep update-interrupted work separate from the final completed turn."""
    starts={};seen=set();intervals=[];interrupted=[];ordered=[]
    for n,row in rows:
        payload=row.get('payload',{})
        if row.get('type')!='event_msg':continue
        kind=payload.get('type');turn=payload.get('turn_id')
        if kind=='task_started':
            _require(turn and turn not in seen and not starts and not intervals,
                     'NATIVE_JUDGE_TURN_SEQUENCE_INVALID')
            attribution=payload.get('turn_attribution',{})
            if interrupted:
                _require(attribution.get('turn_trigger')=='app_update_resume'
                         and attribution.get('turn_id')==turn,
                         'NATIVE_JUDGE_RESUME_TRIGGER_INVALID')
            seen.add(turn);ordered.append((n,payload))
            starts[turn]={'line':n,'at':row.get('timestamp')}
        elif kind in ('task_complete','turn_aborted'):
            begin=starts.pop(turn,None)
            _require(begin is not None,'NATIVE_JUDGE_TURN_START_MISSING')
            item={'turn_id':turn,'start':begin,'end':{'line':n,'at':row.get('timestamp')},
                  'duration_ms':payload.get('duration_ms')}
            if kind=='task_complete':intervals.append(item)
            else:
                _require(payload.get('reason')=='interrupted','NATIVE_JUDGE_ABORT_REASON_INVALID')
                interrupted.append(item)
    resumed=bool(interrupted and len(ordered)>1)
    if resumed:
        first=ordered[0][1];attribution=first.get('turn_attribution',{})
        _require(attribution.get('turn_trigger')=='app_tool_create_thread'
                 and attribution.get('turn_id')==first.get('turn_id'),
                 'NATIVE_JUDGE_RESUME_ORIGIN_INVALID')
        _require({c.get('turn_id') for _,c in contexts}==seen,
                 'NATIVE_JUDGE_RESUME_CONTEXT_MISSING')
        first_action=next((n for n,r in rows if r.get('type')=='response_item'
                           and (r.get('payload',{}).get('role')=='assistant'
                                or r.get('payload',{}).get('type') in
                                   ('reasoning','custom_tool_call','function_call'))),None)
        _require(first_action is not None,'NATIVE_JUDGE_RESUME_ORIGIN_INVALID')
        for n,row in rows:
            if n<=first_action:continue
            p=row.get('payload',{})
            _require(not (row.get('type')=='response_item' and p.get('role')=='user')
                     and not (row.get('type')=='event_msg' and p.get('type')=='user_message')
                     and not (row.get('type')=='response_item'
                              and p.get('type')=='function_call_output'
                              and '<codex_delegation>' in str(p.get('output',''))),
                     'NATIVE_JUDGE_RESUME_ADDITIONAL_INPUT')
        closed=sorted(interrupted+intervals,key=lambda x:x['start']['line'])
        last_end=None
        for item in closed:
            try:
                begin=datetime.fromisoformat(item['start']['at'].replace('Z','+00:00'))
                end=datetime.fromisoformat(item['end']['at'].replace('Z','+00:00'))
                _require(begin.tzinfo is not None and end.tzinfo is not None
                         and end>=begin and (last_end is None or begin>=last_end),
                         'NATIVE_JUDGE_RESUME_TIME_INVALID')
            except (AttributeError,TypeError,ValueError) as error:
                raise ValueError('NATIVE_JUDGE_RESUME_TIME_INVALID') from error
            last_end=end
    _require(allow_running or (not starts and len(intervals)==1
                              and (not interrupted or resumed)),
             'NATIVE_JUDGE_COMPLETION_NOT_PROVEN')
    return intervals,interrupted,list(starts),resumed

def prompt_transport(text,prompt):
    if not isinstance(text,str):return None
    if text.startswith('<codex_delegation>'):
        envelope=ET.fromstring(text)
        _require(envelope.tag=='codex_delegation' and len(envelope.findall('input'))==1,'NATIVE_PROMPT_ENVELOPE_INVALID')
        node=envelope.find('input')
        _require(not list(node),'NATIVE_PROMPT_ENVELOPE_NESTED_INPUT')
        if node.text==prompt:return 'codex-delegation-xml-input'
        return None
    if text==prompt:return 'literal'
    return None

def verify_context(path,*,thread_id,cwd,model,effort,prompt,allow_running=False):
    path=pathlib.Path(path)
    _require(path.is_file() and not path.is_symlink(),'NATIVE_JUDGE_SDK_INVALID')
    raw=path.read_bytes();lines=raw.decode('utf-8').split('\n');rows=[]
    for index,line in enumerate(lines):
        if not line.strip():continue
        try:rows.append((index+1,json.loads(line)))
        except json.JSONDecodeError:
            if not (allow_running and index==len(lines)-1):raise
    meta=[r['payload'] for _,r in rows if r.get('type')=='session_meta']
    _require(len(meta)==1 and meta[0].get('id')==thread_id,'NATIVE_JUDGE_THREAD_MISMATCH')
    _require(meta[0].get('cwd')==cwd and meta[0].get('runtime_workspace_roots')==[cwd],'NATIVE_JUDGE_WORKSPACE_MISMATCH')
    contexts=[(n,r['payload']) for n,r in rows if r.get('type')=='turn_context']
    _require(contexts,'NATIVE_JUDGE_CONTEXT_NOT_READY')
    _require(all(c.get('cwd')==cwd and c.get('model')==model and c.get('effort')==effort for _,c in contexts),'NATIVE_JUDGE_MODEL_OR_EFFORT_MISMATCH')
    matches=[]
    for n,row in rows:
        payload=row.get('payload',{})
        if row.get('type')=='response_item' and (payload.get('role')=='assistant' or payload.get('type') in ('reasoning','custom_tool_call','function_call')):break
        texts=[]
        if row.get('type')=='response_item' and payload.get('type')=='function_call_output':texts=[payload.get('output')]
        elif row.get('type')=='response_item' and payload.get('role')=='user':
            content=payload.get('content',[])
            texts=[''.join(x.get('text','') for x in content if x.get('type') in ('input_text','text'))] if isinstance(content,list) else [content]
        for text in texts:
            transport=prompt_transport(text,prompt)
            if transport:matches.append({'line':n,'transport':transport,'container_sha256':hashlib.sha256(text.encode()).hexdigest(),'decoded_prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
    _require(matches,'NATIVE_JUDGE_FROZEN_PROMPT_MISMATCH')
    intervals,interrupted,unfinished,resumed=native_turn_boundaries(rows,contexts,allow_running=allow_running)
    proof={'status':'PASS','thread_id':thread_id,'cwd':cwd,'model':model,'effort':effort,'provider':meta[0].get('model_provider'),'cli_version':meta[0].get('cli_version'),'sdk_path':str(path),'sdk_observed_sha256':hashlib.sha256(raw).hexdigest(),'sdk_observed_size':len(raw),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'prompt_transport':matches,'context_lines':[n for n,_ in contexts],'intervals':intervals,'unfinished_turns':unfinished,'reasoning_content_exported':False}
    if interrupted:
        proof['interrupted_intervals']=interrupted
        proof['resume_profile']='native-app-update-resume/v1' if resumed else None
    return proof
