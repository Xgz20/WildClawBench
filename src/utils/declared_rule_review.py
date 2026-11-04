"""CLI discovery -> independent API review -> original numeric rule replay.

The task embeds the same _rr_decide implementation consumed by native E2E.
Discovery never publishes a provisional score; missing decisions stay errors.
"""
from __future__ import annotations
import ast,hashlib,json,re
from pathlib import Path

PROFILE='warranty-recovery-reason-semantic-review/v1'
TASK='02_Office_task_010_warranty_recovery_allocation'

def profile_for(task_id,source):
    declarations=[n.value.value for n in ast.parse(source).body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='RULE_REVIEW_PROFILE' for t in n.targets)
        and isinstance(n.value,ast.Constant)]
    if not declarations:return None
    if declarations!=[PROFILE] or task_id!=TASK:raise ValueError('DECLARED_RULE_REVIEW_PROFILE_INVALID')
    return PROFILE

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate_decisions(request,response):
    rows=response.get('decisions') if isinstance(response,dict) else None
    expected=set(request['contexts'])
    if (not isinstance(rows,list) or len(rows)!=len(expected)
        or any(not isinstance(row,dict) for row in rows)
        or {row.get('context_id') for row in rows}!=expected):
        raise ValueError('RULE_REVIEW_RESPONSE_SCOPE_MISMATCH')
    values={}
    for row in rows:
        if not isinstance(row.get('reason'),str) or not re.search('[\u4e00-\u9fff]',row['reason']):
            raise ValueError('RULE_REVIEW_REASON_REQUIRED')
        locations=row.get('evidence_locations')
        if not isinstance(locations,list) or not locations or any(not isinstance(x,str) or not x.strip() for x in locations):
            raise ValueError('RULE_REVIEW_EVIDENCE_LOCATIONS_REQUIRED')
        if row.get('status')=='unresolved' and row.get('passed') is None:
            raise ValueError('RULE_REVIEW_UNRESOLVED:'+row['context_id'])
        if row.get('status')!='judged' or not isinstance(row.get('passed'),bool):
            raise ValueError('RULE_REVIEW_BOOLEAN_REQUIRED')
        values[row['context_id']]=row['passed']
    return values

def reviewer_code(request,model,max_tokens):
    instructions=("只复核原规则声明的不发起追偿原因类别；读取每项完整候选原行、表头及明确适用的共享说明。"
        "不得从expected_category替候选补事实，不判断金额或给分。明确缺失/错误为false，符合为true，"
        "证据不足为unresolved/null。逐项返回{context_id,status:judged或unresolved,passed:布尔值或null,"
        "reason:中文证据理由,evidence_locations:[上下文中的原表/行/共享说明位置]}，JSON顶层仅decisions。")
    message=instructions+'\n'+json.dumps(request,ensure_ascii=False)
    if len(message.encode())>16777216:raise ValueError('RULE_REVIEW_INPUT_RESOURCE_LIMIT')
    return ("import os,json\nimport _judge_shim\n_judge_shim.install()\nfrom openai import OpenAI\n"
        "client=OpenAI(api_key=os.environ.get('OPENROUTER_API_KEY',''),base_url=os.environ.get('OPENROUTER_BASE_URL',''))\n"
        f"message={message!r}\nmodel={model!r}\n"
        f"response=client.chat.completions.create(model=model,max_tokens={max_tokens},messages=[{{'role':'user','content':message}}],response_format={{'type':'json_object'}})\n"
        "choice=response.choices[0]\n"
        "print(json.dumps({'candidate_text':choice.message.content,'request':{'model':model,'messages':[{'role':'user','content':message}]},"
        "'response':{'finish_reason':getattr(choice,'finish_reason',None),'model':getattr(response,'model',None),"
        "'raw':response.model_dump() if callable(getattr(response,'model_dump',None)) else None}},ensure_ascii=False,default=str))\n")

def run(task_id,source,extra_env,lobster_env,transcript_path,*,output_dir,grade,judge,model,max_tokens):
    profile=profile_for(task_id,source)
    if profile is None:raise ValueError('DECLARED_RULE_REVIEW_REQUIRED')
    folder=Path(output_dir)/'rule-review';folder.mkdir(parents=True,exist_ok=True)
    # Every actual invocation receives a new audit directory, preserving failed attempts.
    import uuid
    folder=folder/uuid.uuid4().hex;folder.mkdir()
    save=lambda name,value:(folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    discovered,err=grade(task_id,source,extra_env,lobster_env,transcript_path,
        rule_review_configuration={'profile':profile,'mode':'discover','decisions':{}})
    save('discovery.json',{'result':discovered,'error':err,'provisional_scores_published':False})
    if err:return None,err
    contexts=(discovered or {}).get('contexts')
    if (not isinstance(contexts,dict) or (discovered or {}).get('profile')!=profile
        or (discovered or {}).get('provisional_scores_published') is not False
        or any(digest(context)!=key for key,context in contexts.items())):
        return None,'RULE_REVIEW_DISCOVERY_INVALID'
    request={'profile':profile,'task_id':task_id,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'contexts':contexts,'input_snapshot':discovered.get('input_snapshot'),'provisional_scores_published':False}
    save('request.json',request)
    if not contexts:decisions={}
    else:
        try:code=reviewer_code(request,model,max_tokens)
        except ValueError as exc:return None,str(exc)
        envelope,err=judge(task_id,code,transcript_path,audit_dir=folder/'judge')
        save('judge-envelope.json',{'envelope':envelope,'error':err})
        if err:return None,err
        try:
            if (envelope or {}).get('response',{}).get('finish_reason') not in {'stop','end_turn'}:
                raise ValueError('RULE_REVIEW_INCOMPLETE_RESPONSE')
            response=json.loads(envelope['candidate_text'])
            save('response.json',response)
            decisions=validate_decisions(request,response)
        except (KeyError,ValueError,TypeError) as exc:return None,str(exc)
    result,err=grade(task_id,source,extra_env,lobster_env,transcript_path,
        rule_review_configuration={'profile':profile,'mode':'apply','decisions':decisions,
            'expected_input_snapshot':request['input_snapshot']})
    save('apply-result.json',{'result':result,'error':err,'decision_count':len(decisions)})
    return result,err
