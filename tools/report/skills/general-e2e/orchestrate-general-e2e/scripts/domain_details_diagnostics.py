"""Preserve the exact attribution-family boolean domain ledger as diagnostics."""
from copy import deepcopy
import hashlib
import math

PROFILE='attribution-domain-details-diagnostics/v1'
ERROR_KIND='declared-domain-details-diagnostic-repair/v1'
TASK_PREFIXES=tuple('03_Data_Analysis_task_'+n+'_' for n in ['014','015','016'])

def marker(contract,contract_sha,dataset):
    import grade_wrapper_normalization
    if not contract.get('task_id','').startswith(TASK_PREFIXES):return None
    parent=grade_wrapper_normalization.marker(contract,contract_sha,dataset)
    return None if parent is None else {'profile':PROFILE,**{k:parent[k] for k in ['catalog_sha256','contract_sha256','source_sha256']}}

def validate_details(value):
    if (not isinstance(value,dict) or set(value)!={'domains','read_error'} or not isinstance(value['domains'],dict)
            or (value['read_error'] is not None and not isinstance(value['read_error'],str))
            or not set(value['domains'])<={'C1_scope','C2_current','C3_attribution','C3_metrics','C4_unknown','C5_source'}
            or any(not isinstance(k,str) or not isinstance(v,list) or any(not isinstance(item,bool) for item in v) for k,v in value['domains'].items())):
        raise ValueError('DOMAIN_DETAILS_DIAGNOSTIC_INVALID')
    return deepcopy(value)

def effective_adapter(manifest,contract,original):
    frozen=manifest.get('runtime',{}).get('domain_details_diagnostics_profile')
    if frozen is None:return original
    expected=marker(contract,manifest['digests']['contract_sha256'],manifest['dataset'])
    if expected is None or expected!=frozen:raise ValueError('DOMAIN_DETAILS_PROFILE_MISMATCH')
    result=deepcopy(original)
    if not isinstance(result,dict):raise ValueError('DOMAIN_DETAILS_ADAPTER_INVALID')
    result['domain_details_object_key']='details'
    return result

def original_failure(manifest,contract,audit,worker):
    if marker(contract,manifest.get('digests',{}).get('contract_sha256'),manifest.get('dataset',{})) is None:return False
    result=worker.get('result') or {}
    if audit.get('status')!='failed' or audit.get('error',{}).get('code')!='SCORE_VALUE_INVALID' or worker.get('ok') is not True:return False
    try:validate_details(result.get('details'))
    except ValueError:return False
    numeric={k:v for k,v in result.items() if k!='details'}
    return bool(numeric) and all(not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1 for v in numeric.values())
