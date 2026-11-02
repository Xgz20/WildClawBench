"""Exact-source profiles and portable arithmetic for independent validity v2.

No task grader is executed here. Its original aggregate_review runs only in the
managed Worker and its response-bound result is retained with the evidence.
"""
from copy import deepcopy
from decimal import Decimal
import ast
import hashlib
import json
import math
from pathlib import Path

PROFILE = 'independent-business-capability/v2'
SCHEMA = 'wildclawbench.general-e2e-independent-capabilities/v2'
AVAILABLE = {'pass', 'partial', 'fail'}
UNAVAILABLE = {'evidence_insufficient', 'blocked_external', 'not_observed', 'evaluator_error'}
REGISTRY = json.loads(Path(__file__).with_name('independent_validity_profiles.json').read_text(encoding='utf-8'))['profiles']
REGISTRY_70_V2 = json.loads(Path(__file__).with_name('independent_validity_profiles_70_v2.json').read_text(encoding='utf-8'))['profiles']


def complete_transcript(queries, query_ids, total):
    selected = {q.get('query_id'): q for q in queries}; ranges = []
    for qid in query_ids:
        coverage = selected.get(qid, {}).get('coverage') or {}
        if not isinstance(coverage,dict):continue
        if (coverage.get('kind') == 'transcript-range' and coverage.get('unfiltered') is True
                and coverage.get('total') == total and isinstance(coverage.get('start'), int)
                and isinstance(coverage.get('end'), int)):
            ranges.append((coverage['start'], coverage['end']))
    cursor = 0
    for start, end in sorted(ranges):
        if start > cursor:return False
        cursor = max(cursor, end)
    return cursor >= total


def validate_auxiliary(response, criteria, catalog, queries, policy):
    def fail(code):raise ValueError(code)
    index = {i['id']: i['reference'] for i in catalog['evidence_index']['entries']}
    by_query = {q['query_id']: q for q in queries}
    def decision(value, allowed):
        if (not isinstance(value, dict) or value.get('status') not in allowed
                or not isinstance(value.get('reason'), str)
                or sum('\u3400' <= c <= '\u9fff' for c in value['reason']) < 4
                or not isinstance(value.get('review'), dict) or not isinstance(value.get('evidence_ids'), list)):
            fail('INDEPENDENT_CAPABILITY_DECISION_INVALID')
        ids=value['evidence_ids'];review=value['review'];qids=review.get('query_ids')
        if (not ids or len(ids)!=len(set(ids)) or not isinstance(qids,list) or not qids
                or len(qids)!=len(set(qids)) or not set(qids)<=set(by_query)
                or not set(ids)<=set(index) or not set(ids)<={eid for q in qids for eid in by_query[q].get('returned_evidence_ids',[])}
                or review.get('supporting_evidence_checked') is not True or review.get('contradicting_evidence_checked') is not True):
            fail('INDEPENDENT_CAPABILITY_QUERY_PROOF_REQUIRED')
        if review.get('absence_claim') or value['status']=='not_observed':
            if review.get('complete_event_range_checked') is not True or not complete_transcript(queries,qids,catalog['transcript']['event_count']):
                fail('INDEPENDENT_CAPABILITY_ABSENCE_COVERAGE_REQUIRED')
        return {'status':value['status'],'reason':value['reason'],'evidence':[deepcopy(index[i]) for i in ids],'query_ids':list(qids)}
    run=decision(response.get('run_validity'),{'valid','contaminated_run','evidence_insufficient'})
    if run['status']=='valid':
        total=catalog.get('transcript',{}).get('event_count',0);review=response['run_validity']['review']
        if total<=0 or review.get('complete_event_range_checked') is not True or not complete_transcript(queries,review['query_ids'],total):
            fail('INDEPENDENT_RUN_VALIDITY_COMPLETE_TRACE_REQUIRED')
    by_key={x['key']:x for x in criteria};values=response.get('criterion_evidence_statuses');cap_values=response.get('capability_evidence_statuses')
    if (not isinstance(values,dict) or set(values)!=set(policy['criterion_keys']) or set(by_key)!=set(policy['criterion_keys'])
            or not isinstance(cap_values,dict) or set(cap_values)!=set(policy['ability_map'])):
        fail('INDEPENDENT_V2_STATUS_SCOPE_MISMATCH')
    checked={};caps={}
    for key in policy['criterion_keys']:
        dec=decision(values[key],AVAILABLE|UNAVAILABLE|({'not_triggered_exempt'} if key=='process_fallback' else set()));row=by_key[key]
        if dec['status'] in AVAILABLE|{'not_triggered_exempt'}:
            score=row.get('score');expected='pass' if score==1 else 'fail' if score==0 else 'partial'
            if (row.get('status')!='judged' or isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score)
                    or not 0<=score<=1 or dec['status']!='not_triggered_exempt' and dec['status']!=expected
                    or dec['status']=='not_triggered_exempt' and score!=1):fail('INDEPENDENT_V2_CRITERION_STATUS_MISMATCH')
        elif row.get('status')!='unresolved' or row.get('score') is not None:fail('INDEPENDENT_V2_UNAVAILABLE_NOT_NULL')
        checked[key]=dec
    for key in policy['ability_map']:
        dec=decision(cap_values[key],AVAILABLE|UNAVAILABLE);row=by_key[key];number=cap_values[key].get('score')
        if dec['status'] in AVAILABLE:
            expected='pass' if number==1 else 'fail' if number==0 else 'partial'
            if (isinstance(number,bool) or not isinstance(number,(int,float)) or not math.isfinite(number) or not 0<=number<=1
                    or dec['status']!=expected or key not in policy['independent_ability_score_keys']
                    and (row.get('status')!='judged' or checked[key]['status'] not in AVAILABLE or number!=row.get('score'))):
                fail('INDEPENDENT_V2_CAPABILITY_STATUS_MISMATCH')
        elif number is not None:fail('INDEPENDENT_V2_UNAVAILABLE_NOT_NULL')
        elif key not in policy['exempt_business_capability_keys'] and checked[key]['status'] in AVAILABLE:
            fail('INDEPENDENT_V2_SHARED_EVIDENCE_STATUS_MISMATCH')
        dec['score']=number;caps[key]=dec
    ledger=response.get('aggregation_review',{}).get('process_error_ledger')
    if ledger is not None:
        native_rows={r['key']:r for r in response['criteria']}
        if not isinstance(ledger,list):fail('INDEPENDENT_V2_LEDGER_EVIDENCE_REQUIRED')
        for item in ledger:
            if (not isinstance(item,dict) or item.get('owner') not in by_key or not isinstance(item.get('evidence'),list)
                    or not item['evidence'] or not set(item['evidence'])<=set(index)
                    or not set(item['evidence'])<=set(native_rows[item['owner']]['evidence_ids'])):
                fail('INDEPENDENT_V2_LEDGER_EVIDENCE_REQUIRED')
    return {'run_validity':run,'criteria':checked,'capabilities':caps,'policy':policy}


def registered(contract, contract_sha256=None):
    spec = (REGISTRY_70_V2 if contract.get('judge_evidence',{}).get('semantic_status_profile')=='evidence-aware-v1' else REGISTRY).get(contract.get('task_id'))
    if (spec is None or hashlib.sha256(contract.get('automated_checks', '').encode('utf-8')).hexdigest() != spec['automated_source_sha256']
            or contract.get('grading_weights') != {'automated': 0, 'llm_judge': 1}
            or contract_sha256 is not None and contract_sha256 != spec['contract_sha256']):
        return None
    declarations={}
    for node in ast.parse(contract['automated_checks']).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='ABILITY_MAP':
            declarations['ABILITY_MAP']=json.loads(json.dumps(ast.literal_eval(node.value)))
    if (declarations.get('ABILITY_MAP')!=spec['ability_map']
            or sum(v[1] for v in spec['ability_map'].values())!=spec['capability_budget']):
        raise ValueError('INDEPENDENT_V2_REGISTRY_ABILITY_BUDGET_DRIFT')
    return deepcopy(spec)


def completion_policy(manifest, contract):
    spec = registered(contract, manifest['digests']['contract_sha256'])
    if (spec is None or manifest.get('judge', {}).get('protocol') != 'codex-agent-judge-v1'
            or manifest.get('runtime', {}).get('business_capability_profile') != PROFILE):
        raise ValueError('INDEPENDENT_V2_PROFILE_MISMATCH')
    return {'profile': PROFILE, **spec, 'valid_run_required_for_both': True,
            'unavailable_capabilities_do_not_zero_business': True,
            'aggregation_check_required': True, 'helper_runs_only_in_managed_worker': True}


def template_fields(policy):
    review = {'query_ids': [], 'supporting_evidence_checked': False,
              'contradicting_evidence_checked': False, 'absence_claim': False,
              'complete_event_range_checked': False}
    decision = {'status': 'evidence_insufficient', 'reason': '', 'evidence_ids': [], 'review': review}
    return {'run_validity': deepcopy(decision),
            'criterion_evidence_statuses': {k: deepcopy(decision) for k in policy['criterion_keys']},
            'capability_evidence_statuses': {k: {**deepcopy(decision),'score':None} for k in policy['ability_map']},
            'aggregation_review': {k: None for k in policy['aggregation_auxiliary_keys']}}


def helper_arguments(policy, response):
    rows = {r['key']: r for r in response['criteria']}
    if set(rows) != set(policy['criterion_keys']):
        raise ValueError('INDEPENDENT_V2_CRITERIA_MISMATCH')
    statuses = {k: response['criterion_evidence_statuses'][k]['status'] for k in rows}
    abilities = {k: response['capability_evidence_statuses'][k]['status'] for k in policy['ability_map']}
    auxiliary = response.get('aggregation_review')
    if not isinstance(auxiliary, dict) or set(auxiliary) != set(policy['aggregation_auxiliary_keys']):
        raise ValueError('INDEPENDENT_V2_AGGREGATION_INPUT_SCOPE')
    scores = {k: r['score'] if r['status'] == 'judged' else 0 for k, r in rows.items()}
    placeholders = [k for k, r in rows.items() if r['status'] != 'judged']
    if not policy['helper_has_separate_ability_statuses']:
        statuses.update(abilities)
    # The original raptor helper requires legal algebraic values even for an
    # unavailable final result. These are private validator inputs only; its own
    # result_valid gate suppresses business publication. Native scores stay null.
    if 'result_final' in scores:
        if 'result_cap' in placeholders:
            scores['result_cap'] = 1
        if 'result_final' in placeholders:
            weights = policy['constants']['RESULT_WEIGHTS']
            raw = sum(Decimal(str(w)) * Decimal(str(scores[k])) for k, w in weights.items())
            scores['result_final'] = float(min(raw, Decimal(100) * Decimal(str(scores['result_cap']))) / 100)
    arguments = {'scores': scores, 'statuses': statuses, **deepcopy(auxiliary)}
    if policy['helper_has_separate_ability_statuses']:
        arguments['ability_statuses'] = abilities
    if policy['helper_has_ability_scores']:
        arguments['ability_scores'] = {k: response['capability_evidence_statuses'][k]['score']
            if abilities[k] in AVAILABLE else 0 for k in abilities}
    if policy['helper_has_run_status']:
        arguments['run_status'] = response['run_validity']['status']
    return arguments, placeholders


def worker_source(original_source, arguments):
    encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return original_source + '\n\nimport json as _general_aggregation_json\n_GENERAL_E2E_AGGREGATE_INPUTS = ' + repr(encoded) + '''
def grade(transcript, workspace_path):
    reviewed = aggregate_review(**_general_aggregation_json.loads(_GENERAL_E2E_AGGREGATE_INPUTS))
    return {'diagnostics': {'aggregation_review': reviewed}}
'''


def derive_record(manifest, component, auxiliary, sources, policy, aggregation):
    rows = {r['key']: r for r in component['criteria']}
    if set(rows) != set(policy['criterion_keys']):
        raise ValueError('INDEPENDENT_V2_CRITERIA_MISMATCH')
    weights = policy['business_weights']
    if any(abs(rows[k]['weight'] - weights.get(k, 0)) > 1e-10 for k in rows):
        raise ValueError('INDEPENDENT_V2_WEIGHT_MISMATCH')
    run = auxiliary['run_validity']; original = aggregation['original_result']
    value = original.get(policy['helper_result_key'])
    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
        raise ValueError('INDEPENDENT_V2_BUSINESS_RANGE')
    valid = (run['status'] == 'valid' and value is not None
             and all(auxiliary['criteria'][k]['status'] in AVAILABLE for k in policy['business_dependencies']))
    score = value / policy['helper_score_scale'] if valid else None
    if score is not None and not 0 <= score <= 1:
        raise ValueError('INDEPENDENT_V2_BUSINESS_RANGE')
    if valid:
        expected = sum(Decimal(str(w)) * Decimal(str(rows[k]['score'])) for k, w in weights.items())
        if abs(expected - Decimal(str(score))) > Decimal('0.000000001'):
            raise ValueError('INDEPENDENT_V2_BUSINESS_HELPER_MISMATCH')
    criteria = []; dimensions = {}
    for key, (dimension, budget) in policy['ability_map'].items():
        decision = auxiliary['capabilities'][key]
        available = (run['status'] == 'valid' and decision['status'] in AVAILABLE
                     and (key in policy['independent_ability_score_keys']
                          or auxiliary['criteria'][key]['status'] in AVAILABLE and rows[key]['status'] == 'judged'))
        number = decision['score'] if available else None
        item = {'key': key, 'dimension': dimension, 'budget': budget, 'status': decision['status'],
                'score': number, 'publishable': available, 'run_status': run['status'],
                'reason': decision['reason'], 'evidence': decision['evidence'], 'query_ids': decision['query_ids']}
        criteria.append(item); dimensions.setdefault(dimension, []).append(item)
    capabilities = {}
    for dimension, members in dimensions.items():
        budget = sum(x['budget'] for x in members)
        number = (float(sum(Decimal(str(x['score'])) * x['budget'] for x in members) / budget)
                  if all(x['score'] is not None for x in members) else None)
        status = ('pass' if number == 1 else 'fail' if number == 0 else 'partial') if number is not None else next(
            (x['status'] for x in members if x['score'] is None and x['status'] in UNAVAILABLE), 'evidence_insufficient')
        capabilities[dimension] = {'score': number, 'budget': budget, 'evidence_status': status}
        helper_number = original.get('capabilities', {}).get(dimension)
        if run['status'] == 'valid' and ((number is None) != (helper_number is None)
                or number is not None and abs(number * 100 - helper_number) > 1e-8):
            raise ValueError('INDEPENDENT_V2_CAPABILITY_HELPER_MISMATCH')
    budget = policy['capability_budget']
    if budget<=0 or sum(x['budget'] for x in criteria)!=budget:
        raise ValueError('INDEPENDENT_V2_CAPABILITY_BUDGET_MISMATCH')
    total = (float(sum(Decimal(str(x['score'])) * x['budget'] for x in criteria) / budget)
             if all(x['score'] is not None for x in criteria) else None)
    total_key=policy['helper_capability_total_key']
    if total_key not in original:
        raise ValueError('INDEPENDENT_V2_HELPER_TOTAL_MISSING')
    helper_total=original[total_key]
    if run['status']=='valid' and ((total is None)!=(helper_total is None)
            or total is not None and (isinstance(helper_total,bool) or not isinstance(helper_total,(int,float))
                                     or not math.isfinite(helper_total) or abs(total*100-helper_total)>1e-8)):
        raise ValueError('INDEPENDENT_V2_CAPABILITY_TOTAL_HELPER_MISMATCH')
    return {'schema_version': SCHEMA, 'profile': PROFILE, 'identity': manifest['identity'], 'sources': sources,
            'run_validity': run, 'business_result': {'valid': valid, 'score': round(score, 5) if score is not None else None,
                'weights': weights, 'criterion_keys': list(weights), 'dependency_keys': policy['business_dependencies']},
            'semantic_criteria': deepcopy(component['criteria']), 'capability_criteria': criteria,
            'capabilities': capabilities, 'capability_total_score': total, 'capability_budget': budget,
            'missing_capability_not_zero': True, 'business_and_capability_scores_separate': True,
            'criterion_evidence_statuses': auxiliary['criteria'], 'aggregation_review': aggregation}
