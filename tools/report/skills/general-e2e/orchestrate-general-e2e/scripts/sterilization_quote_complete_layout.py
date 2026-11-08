"""Read explicit horizontal quote fields within their transport-header domain."""
from pathlib import Path
import hashlib,json,re

TASK='02_Office_task_024_sterilization_quote'
CONTRACT='35838d318be427d0d292b7ae866761c4a66f0ada24c977e69ea4e15d9607fb13'
SOURCE='9db04e9b4d6dd9abbfbe990454b84022847355ca37093c52109770674ba4a5ee'
DATASET={'id':'general-custom70-v4','digest':'914783354b23efa4f814342187ebe931df76cbcb0b2ea3dd85bd3f5705f485ff'}
PROFILE='sterilization-quote-complete-horizontal-fields/v3'
HEADINGS={'Total (USD)':'grand','Quote validity':'validity','Estimated total delivery':'elapsed'}
OLD_SCAN="""                    for rr in range(rn+1,min(rn+15,self.w[sn].max_row+1)):
                        line=self.rows.get((sn,rr),[])
                        labels=[c for c in line if role(c['value'])]"""
NEW_SCAN="""                    for rr in range(rn+1,self.w[sn].max_row+1):
                        line=self.rows.get((sn,rr),[])
                        # A later multi-mode header starts a separate domain.
                        if sum(mode(c['value']) is not None for c in line)>=2: break
                        labels=[c for c in line if role(c['value']) or norm(c['value'])=='totalusd']"""

def marker(contract,sha,dataset):
    if (contract.get('task_id')==TASK and sha==CONTRACT
        and {k:dataset.get(k) for k in DATASET}==DATASET
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE):
        return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE,'headings':HEADINGS,
                'scan_boundary':'sheet end or next explicit multi-mode header'}
    return None

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('sterilization_quote_layout_profile')
    if (frozen or {}).get('profile')!=PROFILE:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'],manifest['dataset'])
    anchor=" or {'estimatedtransittime': 'transit', 'esttotaldeliverytime': 'elapsed', 'validityofrate': 'validity'}.get(s)"
    if expected is None or frozen!=expected or hashlib.sha256(current.encode()).hexdigest()!=SOURCE or current.count(OLD_SCAN)!=1 or current.count(anchor)!=1:
        raise ValueError('QUOTE_COMPLETE_LAYOUT_PROFILE_MISMATCH')
    aliases={re.sub(r'[\s\W_]+','',k.lower()):v for k,v in HEADINGS.items() if v!='grand'}
    field="                        label=labels[0]; field=role(label['value'])"
    if current.count(field)!=1:raise ValueError('QUOTE_COMPLETE_LAYOUT_FIELD_SCOPE_MISMATCH')
    effective=current.replace(anchor,anchor+' or '+repr(aliases)+'.get(s)').replace(OLD_SCAN,NEW_SCAN)
    effective=effective.replace(field,"                        label=labels[0]; field='grand' if norm(label['value'])=='totalusd' else role(label['value'])")
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'candidate_rewritten':False,
        'numeric_decisions_assigned':False,'equivalent_headings':HEADINGS,
        'reason':'仅识别三项明确字段表头，横向方案按原列读取至本表结束或下个明确多方式表头；保留原可见性、安全公式求值、金额/交期/有效期比较、全部重大事件限分及60/40。候选EXW/CIP改动等真实缺陷不修正，独立裁判重新评价。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def blocker_files(attempt):
    return [Path(attempt)/name for name in ['judge-evaluation-blocker.json','judge-readonly-inspection.py','judge-readonly-inspection.json']]

def validate_blocker(attempt,m,contract,b):
    attempt=Path(attempt)
    if marker(contract,m['digests']['contract_sha256'],m['dataset']) is None:raise ValueError('QUOTE_COMPLETE_FAILURE_UNREGISTERED')
    if (b.get('schema_version')!='judge-local-evaluation-blocker/v1' or b.get('task_id')!=TASK
        or b.get('scoring_attempt_id')!=m['identity']['scoring_attempt_id']
        or b.get('formal_score_published') is not False or b.get('verify_score_passed') is not False
        or {x.get('criterion') for x in b.get('extraction_conflicts',[])}!={'automated.scenario_totals','automated.validity_by_mode','automated.elapsed_time'}
        or len(b.get('extraction_conflicts',[]))!=3 or any(x.get('replacement_score') is not None for x in b['extraction_conflicts'])):
        raise ValueError('QUOTE_COMPLETE_BLOCKER_INVALID')
    for key in ['candidate_modified','rule_component_modified','rule_rerun','skill_modified','harness_executed','new_task_or_attempt_created','semantic_response_imported','finalize_executed']:
        if b.get('preservation',{}).get(key) is not False:raise ValueError('QUOTE_COMPLETE_BLOCKER_ACTION_INVALID')
    for p in blocker_files(attempt):
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(attempt.resolve()):raise ValueError('QUOTE_COMPLETE_BLOCKER_FILE_INVALID')
    worker=json.loads((attempt/'worker/result.json').read_text())
    if worker.get('ok') is not True:raise ValueError('QUOTE_COMPLETE_WORKER_INVALID')
    extracted=worker.get('raw_result',{}).get('diagnostics',{}).get('extracted',{})
    for mode_name in ['air','sea','road']:
        if any(extracted.get(mode_name,{}).get(k) is not None for k in ['grand_total','validity_days','order_to_arrival_days']):raise ValueError('QUOTE_COMPLETE_ORIGINAL_FIELDS_NOT_MISSING')
    sha=b.get('evidence',{}).get('candidate_sha256')
    candidates=[p for p in (attempt/m['paths']['candidate_original']).rglob('*.xlsx') if p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==sha]
    if len(candidates)!=1:raise ValueError('QUOTE_COMPLETE_CANDIDATE_BINDING_INVALID')
    import io,openpyxl
    workbook=openpyxl.load_workbook(io.BytesIO(candidates[0].read_bytes()),data_only=False,keep_links=False)
    try:
        sheet=workbook['Transport Comparison']
        for cell,value in {'A13':'Quote validity','A20':'Estimated total delivery','A25':'Total (USD)'}.items():
            if sheet[cell].value!=value:raise ValueError('QUOTE_COMPLETE_HEADER_DRIFT')
        for col in ['B','C','D']:
            if sheet[col+'25'].value!='='+col+'23+'+col+'24':raise ValueError('QUOTE_COMPLETE_FORMULA_DRIFT')
    finally:workbook.close()
    return True
