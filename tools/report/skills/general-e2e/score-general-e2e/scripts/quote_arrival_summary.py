"""Read one explicit arrival heading and formula-linked, explicitly named mode totals."""
import hashlib
import json
from io import BytesIO

TASK='02_Office_task_024_sterilization_quote'
CONTRACT='35838d318be427d0d292b7ae866761c4a66f0ada24c977e69ea4e15d9607fb13'
SOURCE='9db04e9b4d6dd9abbfbe990454b84022847355ca37093c52109770674ba4a5ee'
BASE='530705542b2aca0a8c638f2ad642e4bc996c4feaae9a63b5ea832867eb0567e0'
DATASET={'id':'general-custom70-v6','digest':'20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'}
PROFILE='quote-explicit-arrival-and-mode-summary/v1'
ERROR_KIND='quote-native-arrival-heading-review/v1'
RUNTIME_KEY='quote_arrival_summary_profile'

def marker(contract,sha,dataset):
    if (contract.get('task_id')==TASK and sha==CONTRACT
            and {k:dataset.get(k) for k in DATASET}==DATASET
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE):
        return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE,
                'base_effective_source_sha256':BASE,'heading':{'Estimated arrival time':'elapsed'},
                'summary_policy':'visible explicit total, two-cell addition, one original EXW reference and one explicitly named recommended freight-mode reference; no total synthesis'}
    return None

BRIDGE=r'''
_quote_arrival_previous_role=role
def role(value):
    return _quote_arrival_previous_role(value) or ('elapsed' if norm(value)=='estimatedarrivaltime' else None)

_quote_arrival_previous_extract=Book.extract
def _quote_arrival_extract(self):
    products,options,exw=_quote_arrival_previous_extract(self)
    exw_locations={(r['sheet'],r['cell']) for r in exw}
    visible={(r['sheet'],r['cell']):r for r in self.records if r['visible']}
    summaries={key:[] for key in MODE_DATA}
    for (sheet,row),cells in self.rows.items():
        labels=[r for r in cells if norm(r['value'])=='estimatedtotalcipgoodsfreight']
        for label in labels:
            right=[r for r in cells if r['col']>label['col']]
            if not right:continue
            total=right[0]
            # Keep the original safe evaluator and its result. Never calculate
            # a missing option total from goods and freight values here.
            expression=total.get('formula','')
            match=re.fullmatch(r'\s*=\s*(\$?[A-Za-z]{1,3}\$?\d+)\s*\+\s*(\$?[A-Za-z]{1,3}\$?\d+)\s*',expression)
            if not match:continue
            refs=[(sheet,ref.replace('$','').upper()) for ref in match.groups()]
            if len(set(refs))!=2 or sum(ref in exw_locations for ref in refs)!=1:continue
            freight_ref=next(ref for ref in refs if ref not in exw_locations)
            freight=visible.get(freight_ref)
            if freight is None:continue
            preceding=[r for r in self.rows.get((sheet,freight['row']),[]) if r['col']<freight['col']]
            if not preceding:continue
            explicit=re.fullmatch(r'freightcostrecommended(air|sea|road)',norm(preceding[-1]['value']))
            if explicit:summaries[explicit.group(1)].append(total)
    for mode_name,totals in summaries.items():
        if len(totals)>1:raise EvaluationError('Ambiguous explicitly mode-bound quote total; review extraction')
        if len(totals)==1 and len(options[mode_name])==1 and options[mode_name][0].get('grand') is None:
            options[mode_name][0]['grand']=totals[0]
    return products,options,exw
Book.extract=_quote_arrival_extract
'''

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get(RUNTIME_KEY)
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},
                    manifest['digests']['contract_sha256'],manifest['dataset'])
    if expected is None or frozen!=expected or hashlib.sha256(current.encode()).hexdigest()!=BASE:
        raise ValueError('QUOTE_ARRIVAL_SUMMARY_PROFILE_MISMATCH')
    effective=current+'\n'+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_decisions_assigned':False,'rubric_and_weights_changed':False,
        'reason':'仅识别明确的Estimated arrival time表头；单方式汇总须由原公式引用原EXW及明确recommended模式运费，读取原公式结果，不为其他方式补算。保留原可见性、安全公式、数值比较、重大事件封顶、分母和60/40。',
        'prior_correction':prior}
    return effective,receipt

def blocker_paths(attempt):
    return [attempt/name for name in ['scoring-infrastructure-review.json','judge-readonly-workbook-check.py',
                                      'semantic-response-draft-not-imported.json']]

def validate_blocker(rt,attempt,manifest,contract,task):
    if (marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is None
            or manifest.get('runtime',{}).get(RUNTIME_KEY) is not None
            or (task.get('thread') or {}).get('status')!='COMPLETED' or task.get('score') is not None
            or any((attempt/name).exists() for name in ['score.json','semantic/response.json','semantic/semantic-component.json'])):
        raise ValueError('QUOTE_ARRIVAL_FAILURE_IDENTITY_INVALID')
    import sterilization_quote_complete_layout as complete
    if manifest.get('runtime',{}).get('sterilization_quote_layout_profile')!=complete.marker(contract,CONTRACT,DATASET):
        raise ValueError('QUOTE_ARRIVAL_FAILURE_BASE_PROFILE_INVALID')
    audit=rt._read_json(attempt/'rule-audit.json');request=rt._read_json(attempt/'worker/request.json')
    worker=rt._read_json(attempt/'worker/result.json')
    if (audit.get('status')!='completed' or audit.get('identity')!=manifest['identity']
            or audit.get('worker',{}).get('return_code')!=0
            or audit['worker'].get('request_sha256')!=rt._sha256_file(attempt/'worker/request.json')
            or audit['worker'].get('process_tree_cleanup',{}).get('remaining') is not False
            or worker.get('ok') is not True or not (attempt/'rule-component.json').is_file()
            or hashlib.sha256(request.get('automated_checks','').encode()).hexdigest()!=BASE):
        raise ValueError('QUOTE_ARRIVAL_FAILURE_WORKER_INVALID')
    issue=rt._read_json(attempt/'scoring-infrastructure-review.json')
    if (issue.get('status')!='evaluation_infrastructure_issue' or issue.get('task_id')!=TASK
            or issue.get('scoring_attempt_id')!=manifest['identity']['scoring_attempt_id']
            or issue.get('criterion_key')!='automated.elapsed_time' or issue.get('origin')!='evaluator'
            or issue.get('official_score_created') is not False or issue.get('verify_inputs')!='PASS'
            or issue.get('verify_score')!='not_run_no_official_score' or BASE not in issue.get('extractor_entry','')
            or any(issue.get('preservation',{}).get(k) is not False for k in
                   ['candidate_original_modified','frozen_skill_modified','rules_rerun','semantic_response_imported','harness_executed'])):
        raise ValueError('QUOTE_ARRIVAL_NATIVE_ISSUE_INVALID')
    for path in blocker_paths(attempt):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(attempt.resolve()):
            raise ValueError('QUOTE_ARRIVAL_NATIVE_EVIDENCE_INVALID')
    extracted=worker.get('raw_result',{}).get('diagnostics',{}).get('extracted',{})
    if set(extracted)!={'air','sea','road'} or any(
            extracted[k].get('order_to_arrival_days') is not None
            or extracted[k].get('elapsed_assessment',{}).get('classification')!='missing_or_unreadable'
            for k in extracted):raise ValueError('QUOTE_ARRIVAL_OMISSION_NOT_PROVEN')
    overview=rt._read_json(attempt/'grader-evidence/files/evaluator_evidence/task024/overview.json')
    if overview.get('extracted_options')!=extracted:raise ValueError('QUOTE_ARRIVAL_EXPORTED_EVIDENCE_DRIFT')
    files=[p for p in (attempt/manifest['paths']['candidate_original']/'results').glob('*.xlsx') if p.is_file() and not p.is_symlink()]
    declared=' '.join(issue.get('evidence_checked',[]))
    files=[p for p in files if rt._sha256_file(p) in declared]
    if len(files)!=1:raise ValueError('QUOTE_ARRIVAL_CANDIDATE_BINDING_INVALID')
    import openpyxl
    workbook=openpyxl.load_workbook(BytesIO(files[0].read_bytes()),data_only=False,keep_links=False)
    try:
        headers=[(sheet,cell) for sheet in workbook for row in sheet for cell in row
                 if cell.value=='Estimated arrival time' and sheet.sheet_state=='visible'
                 and not sheet.row_dimensions[cell.row].hidden and not sheet.column_dimensions[cell.column_letter].hidden
                 and cell.number_format.replace(' ','') not in (';;;',';;;;')]
        if len(headers)!=1:raise ValueError('QUOTE_ARRIVAL_HEADER_BINDING_INVALID')
        sheet,header=headers[0]
        reported=[sheet.cell(extracted[k]['row'],header.column) for k in ['air','sea','road']]
        if any(not isinstance(c.value,str) or 'production' not in c.value or 'transit' not in c.value
               or sheet.row_dimensions[c.row].hidden for c in reported):
            raise ValueError('QUOTE_ARRIVAL_REPORTED_TOTAL_NOT_PROVEN')
    finally:workbook.close()
    return {'profile':PROFILE,'candidate_sha256':rt._sha256_file(files[0]),
            'old_elapsed_fields_missing':True,'explicit_arrival_heading_preserved':True,
            'numeric_score_assigned':False,'old_draft_not_imported':True}
