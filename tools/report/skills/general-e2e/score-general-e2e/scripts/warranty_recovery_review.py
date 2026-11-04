"""Exact-contract row transport and independent reason-category review.

Original amount arithmetic, object sets, caps, denominators and87/13 stay intact.
"""
import hashlib

TASK='02_Office_task_010_warranty_recovery_allocation'
CONTRACT='5070a56c5dcf4dc302cdec4a9ac5bc2ca31eb0c09908220531ca88b5a79fb376'
SOURCE='3a95ad18bd352380241234b8a641536ff5b87b2f61e347a9edb1aedb0201da6a'
DATASET={'id':'general-custom70-v2','digest':'001016f24b4bc20f96733592ea4aabe6a3b8e1e5bfd0dbc9052254ea36430c0e'}
PROFILE='warranty-recovery-reason-semantic-review/v1'
LAYOUT_PROFILE='warranty-recovery-row-evidence/v2'

def matches(contract,contract_sha=None):
    from source_identities import materialized_rule_review_profile
    return (contract.get('task_id')==TASK and contract_sha==CONTRACT and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE
        or materialized_rule_review_profile(contract,contract_sha)==PROFILE)

def marker(contract,contract_sha,dataset):
    if matches(contract,contract_sha) and {k:dataset.get(k) for k in DATASET}==DATASET:
        return {'profile':LAYOUT_PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE}
    return None

HELPERS=r'''
def _warranty_no_initiation(row):
    # Zero alone remains a clean recovery row under the original unsafe test.
    # Only an explicit candidate declaration plus zero changes its logical role.
    action=re.sub(r'\s+','',str(row.get('action') or ''))
    return number(row.get('current'))==0 and bool(re.fullmatch(
        r'(?:不再发起|本次不发起|不予追偿|本次不予追偿|暂缓追偿|待核查暂不发起)(?:[（(][^()（）]*[）)])?',action))

def _warranty_reason_matches(key,row,fact,context):
    return _rr_decide({'kind':'warranty-non-initiation-reason-category',
        'unit':list(key),'candidate_row':row,'candidate_shared_context':context,
        'expected_category':fact['decision'],
        'category_definitions':{'covered':'Historical booked recoveries already cover the policy entitlement; no new recovery is initiated.',
            'review':'An initiation condition or required adopted evidence is incomplete; hold or investigate, without inventing a missing business voucher.'},
        'instruction':'Judge only whether the actual candidate reason/note/action and explicitly applicable shared explanation express this original category for this same claim/supplier. Do not infer a candidate statement from the expected category or repair a wrong statement. Missing/clearly wrong is false; insufficient evidence is unresolved. Never decide amounts, assign a rule score, or change the denominator.'})
'''

REPLACEMENTS=(
    (" 'supplier':['supplier'", " 'supplier':['追偿供应商','supplier'"),
    (" 'share':['分摊比例'", " 'share':['实际分摊比例','分摊比例'"),
    (" 'cap':['封顶金额'", " 'cap':['CAP上限','封顶金额'"),
    (" 'already':['已追偿'", " 'already':['已追偿汇总','已追偿'"),
    (" 'reason':['原因类型'", " 'reason':['原因说明','原因类型'"),
    (" 'action':['next_action'", " 'action':['处理动作','next_action'"),
    ("            header_row=ri\n", "            header_row=ri\n            found['_context'].append({'role':'grader_header_location','location':f'{ws.title}!row{ri}','values':[cells.cell(ws.title,ws.cell(ri,c).coordinate) for c in range(1,ws.max_column+1)]})\n"),
    ("                item['_location']=f'{ws.title}!row{r}';out[kind].append(item)",
     "                item['_location']=f'{ws.title}!row{r}'\n                item['_raw_values']=[cells.cell(ws.title,ws.cell(r,c).coordinate) for c in range(1,ws.max_column+1)]\n                row_kind='review' if kind=='detail' and _warranty_no_initiation(item) else kind\n                out[row_kind].append(item)"),
    ("    return out,found", "    for logical_kind,rows in out.items():\n        if rows and logical_kind not in found:found[logical_kind]='explicit candidate non-initiation rows'\n    return out,found"),
    ("review_ok=sum(len(ar[k])==1 and reason_class(ar[k][0].get('reason'))==facts[k]['decision'] for k in er)",
     "review_ok=sum(len(ar[k])==1 and _warranty_reason_matches(k,ar[k][0],facts[k],found.get('_context',[])) for k in er)"),
)

def effective_source(manifest,original,current,prior):
    from source_identities import materialized_rule_review_profile
    if materialized_rule_review_profile({'task_id':manifest.get('identity',{}).get('task_id'),'automated_checks':original},
            manifest.get('digests',{}).get('contract_sha256'))==PROFILE:
        if manifest.get('runtime',{}).get('rule_review_profile')!=PROFILE:
            raise ValueError('MATERIALIZED_WARRANTY_REVIEW_REQUIRED')
        return current,prior
    frozen=manifest.get('runtime',{}).get('warranty_recovery_layout_profile')
    if (frozen or {}).get('profile')!=LAYOUT_PROFILE:
        if manifest.get('runtime',{}).get('rule_review_profile')==PROFILE:raise ValueError('WARRANTY_REVIEW_LAYOUT_REQUIRED')
        return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'],manifest['dataset'])
    if (frozen!=expected or expected is None or current!=original
        or manifest.get('runtime',{}).get('rule_review_profile')!=PROFILE
        or manifest.get('judge',{}).get('protocol')!='codex-agent-judge-v1'):
        raise ValueError('WARRANTY_ROW_REVIEW_PROFILE_MISMATCH')
    effective=current
    for old,new in REPLACEMENTS:
        if effective.count(old)!=1:raise ValueError('WARRANTY_ROW_REVIEW_SOURCE_SPAN_MISMATCH')
        effective=effective.replace(old,new)
    import rule_review
    common=rule_review.WRAPPERS.split('_rr_original_impact=',1)[0].replace(rule_review.PROFILE,PROFILE)
    effective+=common+HELPERS
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':LAYOUT_PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_decisions_assigned':False,'review_profile':PROFILE,
        'discovery_provisional_scores_publishable':False,
        'reason':'仅识别等价表头、保留原行全部值及表头、按明确不发起且零金额区分同表逻辑行；不把零金额本身当合格。原6个不发起组合的原因类别由独立裁判复核原文及明确共享说明，缺失/错误不猜补。原对象、金额、分母、封顶、87/13与两项语义Rubric不改。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
