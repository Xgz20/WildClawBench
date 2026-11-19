"""Keep the unique complete learning business table apart from chart helpers."""
import hashlib
from inspect import getsource
from io import BytesIO
import funnel_summary_tables as funnel

TASK='03_Data_Analysis_task_012_learning_product_activation_retention'
CONTRACT='20cc871fd1fefff2b3cb667d66a6f309b166e2a330b5fe7d9bcb20dc9a20d29d'
SOURCE='a7d33513b3b2ce4795ede1877332f8e84efc12916f02f3a829dd583e94bbc901'
DATASET=funnel.DATASET
PROFILE='learning-disjoint-summary-tables/v1'
RUNTIME_KEY='learning_summary_table_profile'

def marker(contract,sha,dataset):
    if (contract.get('task_id')==TASK and sha==CONTRACT and dataset==DATASET
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE):
        return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE}
    return None

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get(RUNTIME_KEY)
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'],manifest['dataset'])
    if expected is None or frozen!=expected or current.count(funnel.OLD_READER)!=1:raise ValueError('LEARNING_SUMMARY_TABLE_PROFILE_MISMATCH')
    effective=current.replace(funnel.OLD_READER,funnel.NEW_READER)+'\n'+getsource(funnel._ge2e_funnel_summary_columns)+'\n_GE2E_FUNNEL_FIELDS = '+repr(funnel.REQUIRED_FIELDS)+'\n'
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_decisions_assigned':False,'rubric_and_weights_changed':False,
        'reason':'仅当汇总页出现必需表头重复时选取空列分隔的唯一完整业务表，按原字段和值交原比较函数；图表及辅助区原件保留，缺少唯一表域不猜测选择，原分母、分档及权重保持。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def blocker_paths(attempt):
    return [attempt/p for p in ['judge-review/evaluation-blocker.json','judge-review/table-extraction-observation.py',
        'judge-review/table-extraction-observation.json','grader-evidence/files/评分证据/指标与分析.json',
        'candidate-original/workspace/results/用户行为分析.xlsx']]

def validate_blocker(rt,attempt,manifest,contract,task):
    if (marker(contract,manifest['digests']['contract_sha256'],manifest['dataset']) is None
        or manifest.get('runtime',{}).get(RUNTIME_KEY) is not None
        or (task.get('thread') or {}).get('status')!='COMPLETED' or task.get('score') is not None
        or any((attempt/p).exists() for p in ['score.json','semantic/response.json','semantic/semantic-component.json'])):
        raise ValueError('LEARNING_SUMMARY_FAILURE_IDENTITY_INVALID')
    paths=blocker_paths(attempt)
    if any(p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(attempt.resolve()) for p in paths):raise ValueError('LEARNING_SUMMARY_FAILURE_EVIDENCE_INVALID')
    issue=rt._read_json(paths[0]);observation=rt._read_json(paths[2]);identity={k:manifest['identity'][k] for k in ['task_id','scoring_attempt_id','execution_attempt_id']}
    digest=rt._sha256_file(paths[-1]);bound=issue.get('independent_observation',{})
    if (issue.get('schema_version')!='general-e2e-independent-judge-blocker/v1' or issue.get('identity')!=identity
        or issue.get('status')!='evaluator_repair_required_before_formal_score' or issue.get('origin')!='evaluator'
        or any(issue.get(k) is not False for k in ['formal_score_published','semantic_response_imported','verify_score_completed'])
        or bound.get('candidate_sha256_before_and_after')!=digest or bound.get('candidate_unchanged') is not True
        or bound.get('rule_functions_executed') is not False
        or observation.get('candidate_sha256_before')!=digest or observation.get('candidate_sha256_after')!=digest
        or observation.get('candidate_unchanged') is not True):raise ValueError('LEARNING_SUMMARY_NATIVE_ISSUE_INVALID')
    audit=rt._read_json(attempt/'rule-audit.json');request=rt._read_json(attempt/'worker/request.json');worker=rt._read_json(attempt/'worker/result.json')
    if (audit.get('status')!='completed' or audit.get('identity')!=manifest['identity']
        or audit.get('worker',{}).get('return_code')!=0
        or audit.get('worker',{}).get('request_sha256')!=rt._sha256_file(attempt/'worker/request.json')
        or audit.get('worker',{}).get('process_tree_cleanup',{}).get('remaining') is not False
        or worker.get('ok') is not True or hashlib.sha256(request.get('automated_checks','').encode()).hexdigest()!=SOURCE
        or not (attempt/'rule-component.json').is_file()):raise ValueError('LEARNING_SUMMARY_FAILURE_WORKER_INVALID')
    extracted=rt._read_json(paths[-2])['汇总与修订']
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    book=load_workbook(BytesIO(paths[-1].read_bytes()),read_only=True,data_only=True)
    try:
        result=[]
        for sheet,field in [('漏斗汇总','步骤'),('留存汇总','留存周期')]:
            rows=list(book[sheet].values);hi,head=next((i,r) for i,r in enumerate(rows) if set(funnel.REQUIRED_FIELDS[sheet]).issubset(r))
            headers=[str(x).strip() if x is not None else '' for x in head];columns=funnel._ge2e_funnel_summary_columns(headers,funnel.REQUIRED_FIELDS[sheet])
            primary,=[i for i in columns if headers[i]==field];helper=max(i for i,h in enumerate(headers) if h==field)
            body=[(i,r) for i,r in enumerate(rows[hi+1:],hi+2) if any(v is not None for v in r)]
            if headers.count(field)<2 or primary==helper or len(body)!=len(extracted[sheet]):raise ValueError('LEARNING_SUMMARY_OVERWRITE_NOT_PROVEN')
            mismatches=[]
            for index,(rn,row) in enumerate(body):
                if row[primary]!=extracted[sheet][index].get(field) and row[helper]==extracted[sheet][index].get(field):
                    mismatches.append({'row':rn,'primary':get_column_letter(primary+1)+str(rn),
                        'helper':get_column_letter(helper+1)+str(rn),'original_business_value':row[primary],
                        'frozen_extracted_value':extracted[sheet][index].get(field)})
            if not mismatches:raise ValueError('LEARNING_SUMMARY_MISMATCH_ABSENT')
            claimed=next((o for o in observation.get('observations',[]) if o.get('sheet')==sheet and o.get('field')==field),None)
            if (claimed is None or len(claimed.get('frozen_extracted_rows',[]))!=len(extracted[sheet])
                or any({f:a.get(f) for f in funnel.REQUIRED_FIELDS[sheet]}!={f:b.get(f) for f in funnel.REQUIRED_FIELDS[sheet]}
                    for a,b in zip(claimed['frozen_extracted_rows'],extracted[sheet]))):raise ValueError('LEARNING_SUMMARY_OBSERVATION_DRIFT')
            result.append({'sheet':sheet,'field':field,'candidate_sha256':digest,'mismatches':mismatches,'numeric_score_assigned':False})
        return result
    finally:book.close()
