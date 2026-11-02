"""Transport and apply the exact original Office026 final-total cap."""
from copy import deepcopy
import hashlib
import math

PROFILE='work-order-original-final-total-cap/v1'
ERROR_KIND='declared-final-total-policy-adapter-repair/v1'
TASK='02_Office_task_026_work_order_labor_reconciliation'
CONTRACT_SHA='c44c983d8373f7075baeee65e327cf886ed2931368b8a59dcd8dae5d484d6cc1'
SOURCE_SHA='fab46597d51de9869feeef882eaa222b9ced1ecc8809ad10c7a8fa1be697bfac'
VERSION='office026-v2-20261021'
SCORE_KEYS=frozenset({'order_scope','source_binding','labor_reconciliation','order_allocation',
 'quality_metrics','anomaly_detection','workbook_usable','overall_score'})
REASON_CAPS={'no_substantive_workbook':0.,'coverage_below_80_percent':.29,
 'allocated_hours_absolute_error_at_least_5_percent':.49,'unresolved_hours_presented_as_determined':.49,
 'unresolved_quality_presented_as_determined':.49,'systematic_quality_error_at_least_20_percent':.49,
 'material_wrong_object_binding':.49,'critical_events_unmarked_or_missing':.59,'material_false_alarm_rate':.59}


def marker(contract,contract_sha):
    from source_identities import accepted_contracts
    if (contract.get('task_id')==TASK and contract_sha in accepted_contracts(CONTRACT_SHA)
            and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE_SHA):
        return {'profile':PROFILE,'contract_sha256':contract_sha,'source_sha256':SOURCE_SHA,'policy_version':VERSION}
    return None

def validate_policy(value):
    # Load the same leaf implementation in both isolated workers and CLI. Do
    # not import the package __init__ in a dependency-isolated rule process.
    import importlib.util
    from pathlib import Path
    leaf=Path(__file__).resolve().parents[1]/'vendor/e2e-shared/wildclawbench_grading_core/original_policies.py'
    if not leaf.is_file():
        leaf=Path(__file__).resolve().parents[6]/'src/wildclawbench_grading_core/original_policies.py'
    spec=importlib.util.spec_from_file_location('_shared_original_final_policy',leaf)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.validate_original_work_order_policy(value)


def effective_adapter(manifest,contract,original):
    frozen=manifest.get('runtime',{}).get('work_order_final_total_policy_profile')
    if frozen is None:return original
    expected=marker(contract,manifest['digests']['contract_sha256'])
    if expected is None or frozen!=expected:raise ValueError('WORK_ORDER_FINAL_POLICY_PROFILE_MISMATCH')
    result=deepcopy(original)
    if not isinstance(result,dict):raise ValueError('WORK_ORDER_FINAL_POLICY_ADAPTER_INVALID')
    result['final_total_policy_object_key']='_score_policy'
    return result

def apply(final,policy):
    value=validate_policy(policy);result=deepcopy(final)
    if result['result']['valid']:
        result['result']['total_score']=min(result['result']['total_score'],value['upper_bound'])
    return result

def original_failure(manifest,contract,audit,worker):
    if marker(contract,manifest.get('digests',{}).get('contract_sha256')) is None:return False
    result=worker.get('result')
    error=audit.get('error')
    if (audit.get('status')!='failed' or not isinstance(error,dict) or error.get('code')!='SCORE_VALUE_INVALID'
            or worker.get('ok') is not True or worker.get('error') is not None or not isinstance(result,dict)
            or set(result)!=SCORE_KEYS|{'_score_policy'}):return False
    try:validate_policy(result.get('_score_policy'))
    except ValueError:return False
    return all(not isinstance(result[k],bool) and isinstance(result[k],(int,float))
        and math.isfinite(result[k]) and 0<=result[k]<=1 for k in SCORE_KEYS)
