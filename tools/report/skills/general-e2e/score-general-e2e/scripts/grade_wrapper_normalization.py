"""Disambiguate six exact authored business-grade + evidence-wrapper entrypoints."""
import ast
import hashlib
import json
from pathlib import Path

PROFILE='reviewed-grade-wrapper-normalization/v1'
ERROR_KIND='declared-wrapper-entrypoint-implementation-repair/v1'
CATALOG_SHA='8ab5776d2352fd6e3b43414d9989cd0e300098b0cba67784f4525156e07cc276'

def registry():
    raw=(Path(__file__).resolve().parents[1]/'data/reviewed-grade-wrapper-normalization-v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA:raise ValueError('GRADE_WRAPPER_CATALOG_DRIFT')
    return json.loads(raw)['profiles']

def marker(contract,contract_sha,dataset):
    for row in registry():
        if (row['task_id']==contract.get('task_id') and row['contract_sha256']==contract_sha
                and row['dataset']=={k:dataset.get(k) for k in ['id','digest']}
                and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==row['source_sha256']):
            return {'profile':PROFILE,'catalog_sha256':CATALOG_SHA,'contract_sha256':contract_sha,'source_sha256':row['source_sha256']}
    return None

def normalized(source,row):
    name='_ge2e_original_business_grade'
    declaration=row['first_declaration'];alias=row['alias_statement']
    if source.count(alias)!=1 or declaration not in source:raise ValueError('GRADE_WRAPPER_SOURCE_SPAN_MISMATCH')
    result=source.replace(declaration,declaration.replace('def grade(','def '+name+'(',1),1)
    result=result.replace(alias,alias.rsplit('grade',1)[0]+name,1)
    if sum(isinstance(n,ast.FunctionDef) and n.name=='grade' for n in ast.parse(result).body)!=1:
        raise ValueError('GRADE_WRAPPER_NORMALIZED_ENTRYPOINT_INVALID')
    return result

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('grade_wrapper_normalization_profile')
    if frozen is None:return current,prior
    contract={'task_id':manifest['identity']['task_id'],'automated_checks':original}
    expected=marker(contract,manifest['digests']['contract_sha256'],manifest['dataset'])
    if expected is None or frozen!=expected:raise ValueError('GRADE_WRAPPER_PROFILE_MISMATCH')
    row=next(r for r in registry() if r['task_id']==contract['task_id']);effective=normalized(current,row)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':row['task_id'],'contract_sha256':row['contract_sha256'],'original_source_sha256':row['source_sha256'],
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'catalog_sha256':CATALOG_SHA,
        'business_function_rewritten':False,'evidence_wrapper_removed':False,'candidate_rewritten':False,
        'reason':'仅将原业务grade声明及原捕获别名重命名为独立私有函数，最终公开grade仍调用原业务函数并执行原取证包装；所有函数体、权重和数据不改。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def original_failure(manifest,contract,audit,worker_exists):
    if marker(contract,manifest.get('digests',{}).get('contract_sha256'),manifest.get('dataset',{})) is None:return False
    return (audit.get('status')=='failed' and audit.get('identity')==manifest.get('identity')
        and audit.get('error',{}).get('code')=='RULE_ENTRYPOINT_INVALID' and not worker_exists)
