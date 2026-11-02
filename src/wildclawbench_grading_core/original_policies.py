"""Authored final-total policies applied identically by CLI and General E2E."""
from copy import deepcopy
import math

WORK_ORDER_CAPS = {'no_substantive_workbook':0., 'coverage_below_80_percent':.29,
    'allocated_hours_absolute_error_at_least_5_percent':.49, 'unresolved_hours_presented_as_determined':.49,
    'unresolved_quality_presented_as_determined':.49, 'systematic_quality_error_at_least_20_percent':.49,
    'material_wrong_object_binding':.49, 'critical_events_unmarked_or_missing':.59, 'material_false_alarm_rate':.59}


def validate_original_work_order_policy(value):
    if (not isinstance(value,dict) or set(value)!={'mode','upper_bound','reasons','version'}
            or value.get('mode')!='final_total_cap' or value.get('version')!='office026-v2-20261021'
            or isinstance(value.get('upper_bound'),bool) or not isinstance(value.get('upper_bound'),(int,float))
            or not math.isfinite(value['upper_bound']) or not 0<=value['upper_bound']<=1
            or not isinstance(value.get('reasons'),list) or any(not isinstance(r,str) for r in value['reasons'])):
        raise ValueError('WORK_ORDER_FINAL_POLICY_INVALID')
    if (len(value['reasons'])!=len(set(value['reasons'])) or any(r not in WORK_ORDER_CAPS for r in value['reasons'])
            or value['upper_bound']!=min([1.]+[WORK_ORDER_CAPS[r] for r in value['reasons']])):
        raise ValueError('WORK_ORDER_FINAL_POLICY_REASONS_MISMATCH')
    return deepcopy(value)
