"""Keep the exact collaborative-sales error list as diagnostics, never a score."""
from copy import deepcopy
import hashlib
import math
import json
from pathlib import Path

PROFILE='collaborative-errors-list-diagnostics/v1'
ERROR_KIND='declared-diagnostic-list-adapter-repair/v1'
TASK='03_Data_Analysis_task_006_collaborative_sales_customer_attribution'
CONTRACT_SHA='4aa0f9ae2a43b42bdba3543fb0355ad34ba9101fa25d9eea37b5741a35f7573b'
SOURCE_SHA='3f0d299234cf8d067ef652629b88f160a3baa3a201491af4753a21f0db438ebd'
CATALOG_SHA='9d9734705f30573667babc82eb09a2704a2380f1db4ba5d52f63a883aeb0b889'

def registry():
    raw=(Path(__file__).resolve().parents[1]/'data/reviewed-result-metadata-v1.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA:raise ValueError('TYPED_RESULT_METADATA_CATALOG_DRIFT')
    return json.loads(raw)['profiles']

def marker(contract,contract_sha):
    for row in registry():
        if (contract.get('task_id')==row['task_id'] and contract_sha==row['contract_sha256']
                and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==row['source_sha256']):
            return {'profile':PROFILE if row['task_id']==TASK else 'feedback-read-error-diagnostics/v1',
                'catalog_sha256':CATALOG_SHA,'contract_sha256':contract_sha,'source_sha256':row['source_sha256']}
    return None

def effective_adapter(manifest,contract,original):
    frozen=manifest.get('runtime',{}).get('typed_rule_diagnostics_profile')
    if frozen is None:return original
    expected=marker(contract,manifest.get('digests',{}).get('contract_sha256'))
    if expected is None or expected!=frozen:raise ValueError('TYPED_RULE_DIAGNOSTICS_PROFILE_MISMATCH')
    result=deepcopy(original)
    if not isinstance(result,dict) or result.get('schema_version')!='wildclawbench.general-e2e-numeric-diagnostics/v1':
        raise ValueError('TYPED_RULE_DIAGNOSTICS_ADAPTER_INVALID')
    row=next(r for r in registry() if r['task_id']==contract['task_id'])
    if row['diagnostic_list_keys']:result['diagnostic_list_keys']=row['diagnostic_list_keys']
    if row['diagnostic_nullable_text_keys']:result['diagnostic_nullable_text_keys']=row['diagnostic_nullable_text_keys']
    return result

def original_failure(manifest,contract,audit,worker):
    if marker(contract,manifest.get('digests',{}).get('contract_sha256')) is None:return False
    result=worker.get('result') or {}
    row=next(r for r in registry() if r['task_id']==contract['task_id']);keys=set(row['numeric_keys'])
    metadata=set(row['diagnostic_list_keys'])|set(row['diagnostic_nullable_text_keys'])
    shapes=all(isinstance(result.get(k),list) and all(isinstance(x,str) for x in result[k]) for k in row['diagnostic_list_keys'])
    shapes=shapes and all(result.get(k) is None or isinstance(result.get(k),str) for k in row['diagnostic_nullable_text_keys'])
    return (audit.get('status')=='failed' and audit.get('error',{}).get('code')=='SCORE_VALUE_INVALID'
        and worker.get('ok') is True and set(result)==keys|metadata and shapes
        and all(not isinstance(result[k],bool) and isinstance(result[k],(int,float))
                and math.isfinite(result[k]) and 0<=result[k]<=1 for k in keys))
