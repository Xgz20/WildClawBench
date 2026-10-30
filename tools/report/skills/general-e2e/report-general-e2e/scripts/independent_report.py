"""Portable v2 sidecar verification; never runs a judge or a task grader."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def general_module():
    vendor=Path(__file__).resolve().parents[1]/'vendor/e2e-shared/independent-validity'
    if str(vendor) not in sys.path:sys.path.insert(0,str(vendor))
    try:
        import independent_validity
        return independent_validity
    except ModuleNotFoundError as exc:
        if exc.name!='independent_validity':raise
    key='_general_e2e_independent_validity_source'
    if key not in sys.modules:
        path=Path(__file__).resolve().parents[6]/'tools/report/e2e-shared/independent-validity/independent_validity.py'
        spec=importlib.util.spec_from_file_location(key,path);module=importlib.util.module_from_spec(spec)
        sys.modules[key]=module;spec.loader.exec_module(module)
    return sys.modules[key]


def verify(record,score,score_path,resolve_file,sha256_file):
    root=score_path.parent;general=general_module()
    def path(value):return resolve_file(root,value,'independent validity v2 source')
    def read(value):return json.loads(path(value).read_text(encoding='utf-8'))
    manifest=read('attempt-manifest.json');contract=read('private/contract.json')
    policy=general.completion_policy(manifest,contract)
    sid=score['identity'];identity=record.get('identity',{})
    if (record.get('schema_version')!=general.SCHEMA or record.get('profile')!=general.PROFILE
            or any(identity.get(k)!=sid.get(k) for k in ['batch_id','unit_id','task_id'])
            or identity.get('scoring_attempt_id')!=sid.get('attempt_id')):
        raise ValueError('REPORT_INDEPENDENT_V2_IDENTITY')
    refs={'attempt_manifest_sha256':'attempt-manifest.json','contract_sha256':'private/contract.json',
          'semantic_request_sha256':'semantic/request.json','semantic_catalog_sha256':'semantic/evidence-catalog.json',
          'semantic_response_sha256':'semantic/response.json','semantic_component_sha256':'semantic/semantic-component.json',
          'query_log_sha256':'semantic/query-log.json'}
    if any(sha256_file(path(value))!=record.get('sources',{}).get(key) for key,value in refs.items()):
        raise ValueError('REPORT_INDEPENDENT_V2_SOURCE_DRIFT')
    request=read('semantic/request.json');response=read('semantic/response.json');component=read('semantic/semantic-component.json')
    if request.get('completion_policy')!=policy:raise ValueError('REPORT_INDEPENDENT_V2_POLICY')
    auxiliary=general.validate_auxiliary(response,component['criteria'],read('semantic/evidence-catalog.json'),read('semantic/query-log.json')['queries'],policy)
    arguments,placeholders=general.helper_arguments(policy,response);source=general.worker_source(contract['automated_checks'],arguments)
    locks={'response_sha256':sha256_file(path('semantic/response.json')),
           'attempt_manifest_sha256':sha256_file(path('attempt-manifest.json')),
           'request_sha256':sha256_file(path('semantic/request.json')),
           'query_log_sha256':sha256_file(path('semantic/query-log.json')),
           'source_sha256':hashlib.sha256(source.encode('utf-8')).hexdigest()}
    check_id=hashlib.sha256(json.dumps(locks,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    prefix='semantic/aggregation-checks/'+check_id;aggregation=record.get('aggregation_review',{})
    if aggregation.get('proof_path')!=prefix+'/proof.json' or sha256_file(path(prefix+'/proof.json'))!=aggregation.get('proof_sha256'):
        raise ValueError('REPORT_INDEPENDENT_V2_AGGREGATION_REF')
    proof=read(prefix+'/proof.json')
    if (proof.get('schema')!='managed-semantic-aggregation-check/v1' or proof.get('identity')!=manifest['identity']
            or proof.get('locks')!=locks or proof.get('arguments')!=arguments
            or proof.get('placeholder_keys')!=placeholders or proof.get('provisional_values_publishable') is not False):
        raise ValueError('REPORT_INDEPENDENT_V2_AGGREGATION_DRIFT')
    for name in ['request.json','result.json','stdout.log','stderr.log']:
        if sha256_file(path(prefix+'/worker/'+name))!=proof['worker_files'].get(name):
            raise ValueError('REPORT_INDEPENDENT_V2_WORKER_DRIFT')
    worker_request=read(prefix+'/worker/request.json');worker_result=read(prefix+'/worker/result.json');audit=proof.get('worker',{})
    if (worker_request.get('automated_checks')!=source or worker_request.get('transcript')!=[]
            or worker_request.get('rule_result_adapter')!={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':['diagnostics']}
            or worker_result.get('ok') is not True or worker_result.get('result')!={}
            or worker_result.get('raw_result')!={'diagnostics':{'aggregation_review':proof.get('original_result')}}
            or audit.get('request_sha256')!=proof['worker_files']['request.json']
            or audit.get('stdout_sha256')!=proof['worker_files']['stdout.log']
            or audit.get('stderr_sha256')!=proof['worker_files']['stderr.log']
            or audit.get('return_code')!=0 or audit.get('timed_out') is not False or audit.get('log_too_large') is not False
            or audit.get('process_tree_cleanup',{}).get('remaining')):
        raise ValueError('REPORT_INDEPENDENT_V2_WORKER_INVALID')
    expected_aggregation={'status':'PASS','proof_path':prefix+'/proof.json','proof_sha256':sha256_file(path(prefix+'/proof.json')),
                          'original_result':proof['original_result'],'placeholder_keys':placeholders,'provisional_values_publishable':False}
    expected=general.derive_record(manifest,component,auxiliary,record['sources'],policy,expected_aggregation)
    if record!=expected or score['result']['valid']!=record['business_result']['valid'] or score['result']['total_score']!=record['business_result']['score']:
        raise ValueError('REPORT_INDEPENDENT_V2_VALUE_DRIFT')
    return record
