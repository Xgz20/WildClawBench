"""Independent review only for the original escrow grader's declared status ambiguity."""
import hashlib

PROFILE='escrow-status-equivalence-review/v1'
ERROR_KIND='declared-status-equivalence-review-required/v1'
TASK='03_Data_Analysis_task_010_contract_escrow_refund_reconciliation'
CONTRACT_SHA='faa1141cd2c5e8dc3e31e4ef0f94744f520f10e85243f84d8898cef4d8b5a3da'
SOURCE_SHA='a16b0e1b172dd17536f754d1f5c506a3220facfec584a0d6efc16ed85006c22d'

from source_identities import accepted_contracts

def matches(contract,contract_sha=None):
    return (contract.get('task_id')==TASK and (contract_sha is None or contract_sha in accepted_contracts(CONTRACT_SHA))
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE_SHA)

WRAPPERS=r'''
def _ge2e_escrow_state(field,row,allowed):
    state=globals().get('_GENERAL_E2E_RULE_REVIEW',{})
    payload={'field':field,'original_row':row,'allowed_original_states':sorted(v for v in allowed if v)}
    group=_rr_hashlib.sha256(_rr_json.dumps(_rr_normalize(payload),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    choices=sorted(v for v in allowed if v)+['__keep_literal_known_distinct__']
    selected=[]
    for choice in choices:
        yes=_rr_decide({'kind':'escrow-status-equivalence','group_id':group,**payload,'canonical_choice':choice,
          'instruction':'Only decide wording equivalence in this exact field/row from public policy and candidate meaning. Never correct a wrong candidate status to the reference fact. The keep-literal choice means the original wording is clearly understood and distinct from every listed state, so the original numerical comparison may fail. Ambiguous meaning remains unresolved/null. Exactly one choice per group may be true.'})
        if yes:selected.append(choice)
    if state.get('mode')=='discover':return row[field]
    if len(selected)!=1:raise RuntimeError('RULE_REVIEW_STATE_EQUIVALENCE_NOT_UNIQUE:'+group)
    return row[field] if selected[0]=='__keep_literal_known_distinct__' else selected[0]

def grade(transcript,workspace_path):
    try:return _ge2e_escrow_original_grade(transcript,workspace_path)
    except RuntimeError as error:
        state=globals().get('_GENERAL_E2E_RULE_REVIEW',{})
        if (state.get('mode')=='discover' and state.get('observations')
                and str(error).startswith('评测不可判定，禁止形成正式综合分：')):
            return {}  # Only discovery; every provisional number is suppressed.
        raise
'''

def effective_source(manifest,original,current,prior):
    if manifest.get('runtime',{}).get('rule_review_profile')!=PROFILE:return current,prior
    if not matches({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256']):
        raise ValueError('ESCROW_STATE_REVIEW_PROFILE_MISMATCH')
    old="                if value and value not in known_states[field]:diagnostic['review_required'].append(f'未识别但可能等价的状态：{field}={value}；需依据公开口径复核')"
    new="                if value and value not in known_states[field]:row[field]=_ge2e_escrow_state(field,row,known_states[field])"
    declaration='def grade(transcript: list, workspace_path: str) -> dict:'
    if current.count(old)!=1 or current.count(declaration)!=1:raise ValueError('ESCROW_STATE_REVIEW_SOURCE_SPAN_MISMATCH')
    import rule_review
    common=rule_review.WRAPPERS.split('_rr_original_impact=',1)[0].replace(rule_review.PROFILE,PROFILE)
    effective=current.replace(old,new).replace(declaration,'def _ge2e_escrow_original_grade(transcript: list, workspace_path: str) -> dict:')+common+WRAPPERS
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,'task_id':TASK,
        'contract_sha256':CONTRACT_SHA,'original_source_sha256':SOURCE_SHA,'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_decisions_assigned':False,
        'reason':'只将原规则明确需复核的逐行状态词交独立裁判判断等价，不将GT事实补给候选；保留明确不同原词供原比较扣分，歧义不猜测。原范围、来源、数值、分母及权重不变。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def validate_choices(request,decisions):
    groups={}
    for item in request['contexts']:
        context=item['context']
        if context.get('kind')=='escrow-unknown-marker-equivalence':
            if context.get('expected_original_marker') not in {'待确认','不适用'} or not isinstance(context.get('original_row'),dict):raise ValueError('ESCROW_MARKER_CONTEXT_INVALID')
            continue
        if context.get('kind')!='escrow-status-equivalence':raise ValueError('ESCROW_REVIEW_CONTEXT_INVALID')
        groups.setdefault(context['group_id'],[]).append(decisions[item['id']])
    for values in groups.values():
        if None not in values and sum(v is True for v in values)!=1:raise ValueError('ESCROW_REVIEW_EXACTLY_ONE_CHOICE_REQUIRED')

def original_failure(manifest,contract,audit,worker):
    error=worker.get('error') or {}
    return (matches(contract,manifest.get('digests',{}).get('contract_sha256')) and audit.get('status')=='failed'
        and worker.get('ok') is False and error.get('type')=='RuntimeError'
        and error.get('message','').startswith('评测不可判定，禁止形成正式综合分：未识别但可能等价的状态：'))
