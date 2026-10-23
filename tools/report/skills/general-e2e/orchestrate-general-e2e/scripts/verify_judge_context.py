"""Read only native judge identity, prompt transport and turn boundaries.

Never exports model reasoning or arbitrary SDK message/tool contents.
"""
import hashlib,json,pathlib,xml.etree.ElementTree as ET

def _require(ok,code):
    if not ok:raise ValueError(code)

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
    starts={};intervals=[]
    for n,row in rows:
        payload=row.get('payload',{})
        if row.get('type')!='event_msg':continue
        if payload.get('type')=='task_started':starts[payload['turn_id']]={'line':n,'at':row.get('timestamp')}
        elif payload.get('type')=='task_complete':
            begin=starts.pop(payload['turn_id'],None)
            _require(begin is not None,'NATIVE_JUDGE_TURN_START_MISSING')
            intervals.append({'turn_id':payload['turn_id'],'start':begin,'end':{'line':n,'at':row.get('timestamp')},'duration_ms':payload.get('duration_ms')})
    _require(allow_running or (not starts and len(intervals)==1),'NATIVE_JUDGE_COMPLETION_NOT_PROVEN')
    return {'status':'PASS','thread_id':thread_id,'cwd':cwd,'model':model,'effort':effort,'provider':meta[0].get('model_provider'),'cli_version':meta[0].get('cli_version'),'sdk_path':str(path),'sdk_observed_sha256':hashlib.sha256(raw).hexdigest(),'sdk_observed_size':len(raw),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'prompt_transport':matches,'context_lines':[n for n,_ in contexts],'intervals':intervals,'unfinished_turns':list(starts),'reasoning_content_exported':False}
