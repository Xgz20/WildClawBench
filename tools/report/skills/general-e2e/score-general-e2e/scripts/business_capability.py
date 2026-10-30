"""Registered independent validity, retaining the original SPY v1 path."""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal
import hashlib
import importlib.util
from pathlib import Path
import sys

PROFILE='independent-business-capability/v1'
SCHEMA='wildclawbench.general-e2e-independent-capabilities/v1'
TASK='01_Information_Search_Organization_task_013_spy_voo_2024_return_fee_comparison'
SOURCE_SHA='8d1a0a8be83233fd099478a491c329e27d67ca2752d36c76eeb720aedcd7a9e6'
CONTRACT_SHA='939b80b68b78b7a1e073d6b5dbacd2fef3d31f55a2059b11f5ac4a4e4c47080b'
BUSINESS={'core_accuracy':.85,'source_binding':.15}
ABILITY={'source_binding':('state_awareness',10),'scope_execution':('intent_understanding',5),
         'difference_inference':('reasoning_and_decision_making',15),'tool_call_contract':('tool_invocation',10),
         'verification_calibration':('result_evaluation',5)}
AVAILABLE={'pass','partial','fail'}
UNAVAILABLE={'evidence_insufficient','blocked_external','not_observed','evaluator_error'}


def general_module():
    vendor=Path(__file__).resolve().parents[1]/'vendor/e2e-shared/independent-validity'
    if str(vendor) not in sys.path:sys.path.insert(0,str(vendor))
    try:
        import independent_validity
        return independent_validity
    except ModuleNotFoundError as exc:
        if exc.name != 'independent_validity':raise
    # Source checkout only; released Skills include the general-contracts vendor.
    key='_general_e2e_independent_validity_source'
    if key not in sys.modules:
        path=Path(__file__).resolve().parents[6]/'tools/report/e2e-shared/independent-validity/independent_validity.py'
        spec=importlib.util.spec_from_file_location(key,path);module=importlib.util.module_from_spec(spec)
        sys.modules[key]=module;spec.loader.exec_module(module)
    return sys.modules[key]


def profile_marker(contract,contract_sha256):
    if matches(contract) and contract_sha256==CONTRACT_SHA:return PROFILE
    general=general_module()
    return general.PROFILE if general.registered(contract,contract_sha256) is not None else None


def matches(contract):
    return (contract.get('task_id')==TASK
        and hashlib.sha256(contract.get('automated_checks','').encode('utf-8')).hexdigest()==SOURCE_SHA
        and contract.get('grading_weights')=={'automated':0,'llm_judge':1})


def policy(manifest,contract):
    marker=manifest.get('runtime',{}).get('business_capability_profile')
    if marker is None:return None
    if marker=='independent-business-capability/v2':
        return general_module().completion_policy(manifest,contract)
    if (marker!=PROFILE or not matches(contract) or manifest['digests']['contract_sha256']!=CONTRACT_SHA
            or manifest.get('judge',{}).get('protocol')!='codex-agent-judge-v1'):
        raise ValueError('INDEPENDENT_CAPABILITY_PROFILE_MISMATCH')
    return {'profile':PROFILE,'business_criteria':list(BUSINESS),'capability_criteria':list(ABILITY),
            'business_weights':BUSINESS,'source_contract_sha256':manifest['digests']['contract_sha256'],
            'unavailable_capabilities_do_not_zero_business':True,'valid_run_required_for_both':True}


def template_fields(policy=None):
    if policy is not None and policy.get('profile')=='independent-business-capability/v2':
        return general_module().template_fields(policy)
    review={'query_ids':[],'supporting_evidence_checked':False,'contradicting_evidence_checked':False,
            'absence_claim':False,'complete_event_range_checked':False}
    decision={'status':'evidence_insufficient','reason':'','evidence_ids':[],'review':review}
    return {'run_validity':deepcopy(decision),
            'capability_evidence_statuses':{key:deepcopy(decision) for key in ABILITY}}


def _decision(rt,value,catalog,queries,valid_statuses):
    if (not isinstance(value,dict) or value.get('status') not in valid_statuses
            or not rt._contains_chinese_explanation(value.get('reason'))
            or not isinstance(value.get('evidence_ids'),list) or len(value['evidence_ids'])!=len(set(value['evidence_ids']))
            or not isinstance(value.get('review'),dict)):
        raise rt.ScoringRuntimeError('INDEPENDENT_CAPABILITY_DECISION_INVALID')
    ids=value['evidence_ids'];review=value['review'];qids=review.get('query_ids')
    index={i['id']:i['reference'] for i in catalog['evidence_index']['entries']}
    by_query={q['query_id']:q for q in queries}
    if (not isinstance(qids,list) or not qids or len(qids)!=len(set(qids))
            or not set(qids).issubset(by_query) or not set(ids).issubset(index)
            or not set(ids).issubset({eid for q in qids for eid in by_query[q].get('returned_evidence_ids',[])})
            or review.get('supporting_evidence_checked') is not True
            or review.get('contradicting_evidence_checked') is not True
            or not ids):
        raise rt.ScoringRuntimeError('INDEPENDENT_CAPABILITY_QUERY_PROOF_REQUIRED')
    if review.get('absence_claim') or value['status']=='not_observed':
        if (review.get('complete_event_range_checked') is not True
                or not rt._queries_cover_complete_transcript(queries,qids,catalog.get('transcript',{}).get('event_count',0))):
            raise rt.ScoringRuntimeError('INDEPENDENT_CAPABILITY_ABSENCE_COVERAGE_REQUIRED')
    return {'status':value['status'],'reason':value['reason'],
            'evidence':[deepcopy(index[i]) for i in ids],'query_ids':list(qids)}


def validate_auxiliary(rt,response,criteria,catalog,queries,policy=None):
    if policy is not None and policy.get('profile')=='independent-business-capability/v2':
        return validate_general_auxiliary(rt,response,criteria,catalog,queries,policy)
    run=_decision(rt,response.get('run_validity'),catalog,queries,{'valid','contaminated_run','evidence_insufficient'})
    if run['status']=='valid':
        review=response['run_validity']['review'];total=catalog.get('transcript',{}).get('event_count',0)
        if (total<=0 or review.get('complete_event_range_checked') is not True
                or not rt._queries_cover_complete_transcript(queries,review['query_ids'],total)):
            raise rt.ScoringRuntimeError('INDEPENDENT_RUN_VALIDITY_COMPLETE_TRACE_REQUIRED')
    values=response.get('capability_evidence_statuses')
    if not isinstance(values,dict) or set(values)!=set(ABILITY):
        raise rt.ScoringRuntimeError('INDEPENDENT_CAPABILITY_SCOPE_MISMATCH')
    by_key={row['key']:row for row in criteria}
    capabilities={}
    for key in ABILITY:
        decision=_decision(rt,values[key],catalog,queries,AVAILABLE|UNAVAILABLE)
        criterion=by_key[key]
        if decision['status'] in AVAILABLE:
            score=criterion.get('score')
            if (criterion.get('status')!='judged' or isinstance(score,bool) or not isinstance(score,(float,int))
                    or decision['status']!=('pass' if score==1 else 'fail' if score==0 else 'partial')):
                raise rt.ScoringRuntimeError('INDEPENDENT_CAPABILITY_SCORE_STATUS_MISMATCH',key)
        capabilities[key]=decision
    return {'run_validity':run,'capabilities':capabilities}


def derive(manifest,component,auxiliary,sources):
    if manifest.get('runtime',{}).get('business_capability_profile')=='independent-business-capability/v2':
        general=general_module()
        return general.derive_record(manifest,component,auxiliary,sources,
            auxiliary['policy'],auxiliary['aggregation_review'])
    by_key={row['key']:row for row in component['criteria']}
    if set(by_key)!=set(BUSINESS)|set(ABILITY):
        raise ValueError('INDEPENDENT_CAPABILITY_CRITERIA_MISMATCH')
    if any(abs(by_key[k]['weight']-w)>1e-10 for k,w in BUSINESS.items()) or any(by_key[k]['weight']!=0 for k in set(ABILITY)-set(BUSINESS)):
        raise ValueError('INDEPENDENT_CAPABILITY_WEIGHT_MISMATCH')
    run=auxiliary['run_validity']
    valid=run['status']=='valid' and all(by_key[k]['status']=='judged' for k in BUSINESS)
    score=float(sum(Decimal(str(w))*Decimal(str(by_key[k]['score'])) for k,w in BUSINESS.items())) if valid else None
    capabilities={};criteria=[]
    for key,(dimension,budget) in ABILITY.items():
        dec=auxiliary['capabilities'][key]
        available=run['status']=='valid' and dec['status'] in AVAILABLE and by_key[key]['status']=='judged'
        value=by_key[key]['score'] if available else None
        record={'key':key,'dimension':dimension,'budget':budget,'status':dec['status'],
                'score':value,'publishable':available,'run_status':run['status'],
                'reason':dec['reason'],'evidence':dec['evidence'],'query_ids':dec['query_ids']}
        criteria.append(record);capabilities[dimension]={'score':value,'budget':budget,'evidence_status':dec['status']}
    total=(float(sum(Decimal(str(i['score']))*Decimal(i['budget']) for i in criteria)/45)
           if all(i['score'] is not None for i in criteria) else None)
    return {'schema_version':SCHEMA,'profile':PROFILE,'identity':manifest['identity'],'sources':sources,
        'run_validity':run,'business_result':{'valid':valid,'score':round(score,5) if score is not None else None,
            'weights':BUSINESS,'criterion_keys':list(BUSINESS)},
        'semantic_criteria':deepcopy(component['criteria']),'capability_criteria':criteria,
        'capabilities':capabilities,'capability_total_score':total,'capability_budget':45,
        'missing_capability_not_zero':True,'business_and_capability_scores_separate':True}


def business_component(component,record):
    result=deepcopy(component);business=record['business_result']
    result['criteria']=[row for row in result['criteria'] if row['key'] in business['criterion_keys']]
    result['status']='completed' if business['valid'] else 'evaluation_error'
    result['score']=business['score']
    result['error']=None if business['valid'] else {'code':'BUSINESS_EVALUATION_UNAVAILABLE',
        'message':'Frozen business criteria or explicit native run validity are unavailable; no score is published.'}
    return result


def validate_general_auxiliary(rt,response,criteria,catalog,queries,policy):
    try:return general_module().validate_auxiliary(response,criteria,catalog,queries,policy)
    except ValueError as exc:raise rt.ScoringRuntimeError(str(exc)) from exc
