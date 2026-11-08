"""Three explicit English quote headings, preserving every original calculation."""
import ast
import hashlib
import re
import unicodedata
from pathlib import Path

TASK='02_Office_task_024_sterilization_quote'
CONTRACT_SHA='f69a2a0698d8f023ef76ece7337bb631a51f1fe912b64e084b98fe682bed5439'
SOURCE_SHA='d15a0df8c0357524b09168bf8d1d9dd5b90642a22366ffa6d24c0eeca64c9b9e'
DATASET={'id':'general-custom116-v1','digest':'8a066c60dfb1b45403b5b792f9cd6264a5ee639e9cd263b8dc0acfc2031dcb01'}
PROFILE='sterilization-quote-equivalent-headings/v1'
ERROR_KIND='sterilization-quote-layout-extraction-repair/v1'
HEADINGS={'Est. Total incl. goods (USD)':'grand','Estimated Delivery (from order)':'elapsed','Rate Validity':'validity'}

def normalized(value):return re.sub(r'[\s\W_]+','',unicodedata.normalize('NFKC',str(value or '')).lower())

def marker(contract,contract_sha,dataset):
    import sterilization_quote_complete_layout
    complete=sterilization_quote_complete_layout.marker(contract,contract_sha,dataset)
    if complete is not None:return complete
    if (contract.get('task_id')==TASK and contract_sha==CONTRACT_SHA
            and {k:dataset.get(k) for k in DATASET}==DATASET
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE_SHA):
        return {'profile':PROFILE,'contract_sha256':CONTRACT_SHA,'source_sha256':SOURCE_SHA,'headings':HEADINGS}
    import sterilization_quote_domain
    return sterilization_quote_domain.marker(contract,contract_sha,dataset)

def effective_source(manifest,original,current,prior):
    import sterilization_quote_complete_layout
    complete=manifest.get('runtime',{}).get('sterilization_quote_layout_profile')
    if (complete or {}).get('profile')==sterilization_quote_complete_layout.PROFILE:
        return sterilization_quote_complete_layout.effective_source(manifest,original,current,prior)
    import sterilization_quote_domain
    frozen=manifest.get('runtime',{}).get('sterilization_quote_layout_profile')
    if (frozen or {}).get('profile')==sterilization_quote_domain.PROFILE:return sterilization_quote_domain.effective_source(manifest,original,current,prior)
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'],manifest['dataset'])
    old='    return next((k for k,rx in PATTERNS.items() if re.fullmatch(rx,s)),None)'
    if expected is None or frozen!=expected or current.count(old)!=1:raise ValueError('QUOTE_HEADING_PROFILE_MISMATCH')
    aliases={normalized(k):v for k,v in HEADINGS.items()}
    effective=current.replace(old,old+' or '+repr(aliases)+'.get(s)')
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT_SHA,'original_source_sha256':SOURCE_SHA,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'equivalent_headings':HEADINGS,
        'candidate_rewritten':False,'numeric_decisions_assigned':False,
        'reason':'仅增加三项明确英文表头的原字段等价匹配；原匹配优先，其他未知表头仍不推断。保留原公式安全求值、总价/交期/有效期比较、可见性、分母、60/40权重及freight_identity等真实限分，独立语义裁判重新评价。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def validate_blocker(attempt,manifest,contract,blocker):
    import sterilization_quote_complete_layout
    if sterilization_quote_complete_layout.marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is not None:
        return sterilization_quote_complete_layout.validate_blocker(attempt,manifest,contract,blocker)
    import sterilization_quote_domain
    if sterilization_quote_domain.marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is not None:
        return sterilization_quote_domain.validate_blocker(attempt,manifest,contract,blocker)
    if marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is None:raise ValueError('QUOTE_LAYOUT_FAILURE_UNREGISTERED')
    identity=manifest['identity'];expected={'task_id':TASK,'scoring_attempt_id':identity['scoring_attempt_id'],
        'execution_attempt_id':identity['execution_attempt_id'],'batch_id':identity['batch_id'],'unit_id':identity['unit_id']}
    if (blocker.get('schema_version')!='general-e2e-independent-judge-blocker/v1'
            or blocker.get('identity')!=expected or blocker.get('error_code')!='FROZEN_RULE_REASONABLE_LAYOUT_EXTRACTION_MISMATCH'
            or blocker.get('total_score') is not None or blocker.get('formal_score_completed') is not False
            or any(blocker.get('judge',{}).get(k)!=manifest['judge'][k] for k in ['protocol','model','reasoning_effort'])
            or blocker.get('evidence_review',{}).get('all_six_declared_evidence_files_read_completely') is not True):raise ValueError('QUOTE_LAYOUT_BLOCKER_INVALID')
    conflicts=blocker.get('conflicts',[])
    if len(conflicts)!=3 or {r.get('header') for r in conflicts}!=set(HEADINGS):raise ValueError('QUOTE_LAYOUT_CONFLICT_SCOPE_INVALID')
    patterns=next(ast.literal_eval(n.value) for n in ast.parse(contract['automated_checks']).body
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PATTERNS' for t in n.targets))
    for heading in HEADINGS:
        if any(re.fullmatch(rx,normalized(heading)) for rx in patterns.values()):raise ValueError('QUOTE_LAYOUT_ORIGINAL_ALREADY_MATCHES')
    base=Path(attempt)/manifest['paths']['candidate_original'];sha=blocker['evidence_review'].get('candidate_sha256')
    candidates=[p for p in base.rglob('*.xlsx') if p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==sha]
    if len(candidates)!=1:raise ValueError('QUOTE_LAYOUT_CANDIDATE_BINDING_INVALID')
    import io,openpyxl
    workbook=openpyxl.load_workbook(io.BytesIO(candidates[0].read_bytes()),data_only=False,keep_links=False)
    try:
        for row in conflicts:
            if workbook[row['candidate_sheet']][row['header_cell']].value!=row['header']:raise ValueError('QUOTE_LAYOUT_HEADER_DRIFT')
            if not row.get('rule_extracted') or any(value is not None for value in row['rule_extracted'].values()):raise ValueError('QUOTE_LAYOUT_EXTRACTION_NOT_NULL')
            for cell,formula in row.get('formulas',{}).items():
                if workbook[row['candidate_sheet']][cell].value!=formula:raise ValueError('QUOTE_LAYOUT_FORMULA_DRIFT')
    finally:workbook.close()
    if any(blocker.get('actions',{}).get(k) is not False for k in ['rules_rerun','candidate_modified','rule_component_modified','semantic_response_imported','finalize_run','verify_score_passed']):raise ValueError('QUOTE_LAYOUT_BLOCKER_ACTIONS_INVALID')
    return True

def blocker_paths(attempt,manifest,contract):
    import sterilization_quote_complete_layout
    if sterilization_quote_complete_layout.marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is not None:
        return sterilization_quote_complete_layout.blocker_files(attempt)
    return [Path(attempt)/'scoring-infrastructure-blocker.json']
