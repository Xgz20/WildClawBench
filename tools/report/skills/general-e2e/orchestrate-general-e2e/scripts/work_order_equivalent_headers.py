"""Exact equivalent work-order headers; keep literal zeros and status contradictions."""
import hashlib,json
from io import BytesIO

TASK='02_Office_task_026_work_order_labor_reconciliation'
CONTRACT='da305783b6cd1427d8e5f59922310896bdf55c4520093da1aaea34240c24bcf2'
SOURCE='0df6363a8bb5cc0f1f27fc30e6c62f02a84212e67cc43351eee5767ec6dc87c7'
BASE='e70fa8f963704f5f48d4957abb8986d0ecc6145d0fc8142e252dc7896dcad8de'
DATASET={'id':'general-custom70-v6','digest':'20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'}
PROFILE='work-order-explicit-equivalent-headers/v2'
ERROR_KIND='work-order-native-equivalent-header-review/v1'
HEADERS={'分摊生产工时':'actual','排期偏差异常':'flags','缺陷率异常':'flags',
         '加班占比异常':'flags','核对状态':'flags','问题/备注':'notes'}

def marker(contract,sha,dataset):
    if (contract.get('task_id')==TASK and sha==CONTRACT
            and {k:dataset.get(k) for k in DATASET}==DATASET
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE):
        return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE,
                'base_effective_source_sha256':BASE,'headers':HEADERS,
                'allocation_status_policy':'literal annotation only, not an anomaly label'}
    return None

BRIDGE=r'''
LOOKUP.update({norm(header):key for header,key in _WO_EQ_HEADERS.items()})
_wo_eq_previous_mapping=_ge2e_work_order_mapping
def _ge2e_work_order_mapping(values,order_table,mapping):
    if order_table and norm('分摊生产工时') in {norm(v) for v in values}:
        available={norm(v) for v in ['可分摊生产工时','可分摊工时','可分摊h','可分摊人时']}
        mapping={i:('available' if key=='actual' and norm(values[i]) in available else key) for i,key in mapping.items()}
    return _wo_eq_previous_mapping(values,order_table,mapping)

_wo_eq_previous_extract=extract
def extract(path):
    orders,days,texts,errors=_wo_eq_previous_extract(path)
    # Allocation eligibility is a literal statement. Do not turn 可分摊 into an
    # anomaly or replace the candidate's zero/pending values with GT facts.
    reader=Reader(path)
    try:
        for sheet in reader.wb:
            if sheet.max_row*sheet.max_column>1000000:raise EvaluationError('Workbook needs a larger bounded extractor')
            columns=[]
            for row in sheet.iter_rows(max_row=min(15,sheet.max_row)):
                names=[reader.value(sheet.title,cell.coordinate) for cell in row]
                if {'date','dept'}<={field(v) for v in names if field(v)}:
                    for heading in ['分摊状态','核对状态']:
                        hits=[i for i,value in enumerate(names) if norm(value)==norm(heading)]
                        if len(hits)>1:raise EvaluationError('Ambiguous literal status annotation')
                        if hits:columns.append((row[0].row,hits[0]+1,heading))
            if len({h for h,_,_ in columns})>1:raise EvaluationError('Multiple status annotation headers')
            if not columns:continue
            for header,column,heading in columns:
                for number in range(header+1,sheet.max_row+1):
                    cell=sheet.cell(number,column);value=reader.value(sheet.title,cell.coordinate)
                    if value is not None:
                        texts.append({'at':path.name+'!'+sheet.title+'!'+cell.coordinate,
                            'text':json.dumps({'role':'candidate_literal_status','header':heading,'value':value,
                                              'not_synthesized':True,'not_automatic_anomaly_flag':True},ensure_ascii=False,default=str)})
    finally:
        reader.wb.close();reader.form.close()
    return orders,days,texts,errors
'''

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('work_order_equivalent_header_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},
                    manifest['digests']['contract_sha256'],manifest['dataset'])
    if expected is None or frozen!=expected or hashlib.sha256(current.encode()).hexdigest()!=BASE:
        raise ValueError('WORK_ORDER_EQUIVALENT_HEADER_PROFILE_MISMATCH')
    code=current+'\n_WO_EQ_HEADERS='+repr(HEADERS)+'\n'+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
             'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
             'effective_source_sha256':hashlib.sha256(code.encode()).hexdigest(),'headers':HEADERS,
             'candidate_rewritten':False,'numeric_decisions_assigned':False,'rubric_and_weights_changed':False,
             'reason':'仅增加明确等价表头，布尔异常沿原flag_value合并，备注保留原文；分摊状态按原格保留为非评分注释，不把可分摊当异常。保留工单/线日粒度、真实0、缺失、矛盾、原数字函数、关键对象、分母、封顶及90/10。'}
    if prior:receipt['prior_correction']=prior
    return code,receipt

def validate_blocker(rt,attempt,manifest,contract,task):
    if (marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is None
            or manifest.get('runtime',{}).get('work_order_equivalent_header_profile') is not None
            or (task.get('thread') or {}).get('status')!='COMPLETED' or task.get('score') is not None
            or any((attempt/name).exists() for name in ['score.json','semantic/response.json','semantic/semantic-component.json'])):
        raise ValueError('WORK_ORDER_HEADER_FAILURE_IDENTITY_INVALID')
    audit=rt._read_json(attempt/'rule-audit.json');request=rt._read_json(attempt/'worker/request.json')
    worker=rt._read_json(attempt/'worker/result.json')
    if (audit.get('status')!='completed' or audit.get('identity')!=manifest['identity']
            or audit.get('worker',{}).get('return_code')!=0
            or audit['worker'].get('request_sha256')!=rt._sha256_file(attempt/'worker/request.json')
            or audit['worker'].get('process_tree_cleanup',{}).get('remaining') is not False
            or worker.get('ok') is not True or not (attempt/'rule-component.json').is_file()
            or hashlib.sha256(request.get('automated_checks','').encode()).hexdigest()!=BASE):
        raise ValueError('WORK_ORDER_HEADER_FAILURE_WORKER_INVALID')
    issue=rt._read_json(attempt/'scoring-evaluation-issue.json');observed=rt._read_json(attempt/'judge-readonly-observations.json')
    expected={k:manifest['identity'][k] for k in ['task_id','scoring_attempt_id','execution_attempt_id']}
    if (issue.get('schema_version')!='general-e2e-judge-evaluation-issue/v1' or issue.get('identity')!=expected
            or issue.get('status')!='NEEDS_ATTENTION' or issue.get('origin')!='evaluator'
            or any(issue.get(k) is not False for k in ['score_published','rule_rerun','candidate_modified'])
            or observed.get('role')!='judge_readonly_observation_not_score'):
        raise ValueError('WORK_ORDER_HEADER_NATIVE_ISSUE_INVALID')
    files=[p for p in (attempt/manifest['paths']['candidate_original']/'results').glob('*.xlsx')
           if p.is_file() and not p.is_symlink() and rt._sha256_file(p)==observed.get('candidate_sha256')]
    if len(files)!=1:raise ValueError('WORK_ORDER_HEADER_CANDIDATE_BINDING_INVALID')
    import openpyxl
    workbook=openpyxl.load_workbook(BytesIO(files[0].read_bytes()),data_only=True,keep_links=False)
    try:
        cells=observed.get('candidate_cells',{})
        if not cells or not all(key in cells for key in ['工单核对准表!O1','工单核对准表!O44','工单核对准表!Q1','工单核对准表!Q44','工单核对准表!W1']):
            raise ValueError('WORK_ORDER_HEADER_OBSERVATION_SCOPE_INVALID')
        for location,value in cells.items():
            sheet,address=location.rsplit('!',1)
            if workbook[sheet][address].value!=value:raise ValueError('WORK_ORDER_HEADER_OBSERVATION_DRIFT')
        if (cells['工单核对准表!O1']!='分摊生产工时' or cells['工单核对准表!Q1']!='排期偏差异常'
                or cells['工单核对准表!W1']!='问题/备注' or cells['工单核对准表!O44'] is None):
            raise ValueError('WORK_ORDER_HEADER_OMISSION_NOT_PROVEN')
    finally:workbook.close()
    exported=observed.get('exported_case',{})
    if not exported.get('wo') or exported.get('candidate',{}).get('actual') is not None:
        raise ValueError('WORK_ORDER_HEADER_EXPORTED_OMISSION_INVALID')
    snapshots=[]
    for path in (attempt/'grader-evidence').rglob('critical*.json'):
        data=rt._read_json(path)
        if isinstance(data,list):snapshots.extend(data)
        elif isinstance(data,dict):
            for value in data.values():
                if isinstance(value,list):snapshots.extend(value)
    if exported not in snapshots:raise ValueError('WORK_ORDER_HEADER_CRITICAL_SOURCE_BINDING_INVALID')
    return {'profile':PROFILE,'candidate_sha256':observed['candidate_sha256'],
            'old_actual_missing':True,'original_actual_cell_preserved':True,
            'real_zero_and_status_contradictions_preserved':True,'numeric_score_assigned':False}
