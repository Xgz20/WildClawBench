from pathlib import Path
import copy
import importlib
import json
import math
import sys

workspace,gt,request_path,output=map(Path,sys.argv[1:]);request=json.loads(request_path.read_text())
output.write_text(json.dumps({'phase':'candidate_start'})+'\n');sys.path.insert(0,str(workspace))
try:module=importlib.import_module('project.config');load_error=None
except BaseException as error:module=None;load_error=type(error).__name__+': '+str(error)
def equal(a,b):
    if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
    if type(a) in (int,float) and type(b) in (int,float):return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-12
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b
def normalize_trace(result):
    if not isinstance(result,dict) or not {'config','sources','migrations'}<=set(result):raise ValueError('audit result missing fields')
    if not isinstance(result['sources'],dict) or not isinstance(result['migrations'],list):raise ValueError('audit containers')
    sources={path:{k:value[k] for k in ['layer','source_path']} for path,value in result['sources'].items()}
    events=[]
    for event in result['migrations']:
        keys=['layer','from','to','action','input']+(['output'] if event['action']=='migrated' else ['reason'])
        events.append({key:event[key] for key in keys})
    events.sort(key=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True))
    return {'config':result['config'],'sources':sources,'migrations':events}
def observe(layers,op):
    args=copy.deepcopy(layers);before=copy.deepcopy(args)
    try:
        if load_error:raise RuntimeError(load_error)
        if op in {'migrate','repeat_migrate'}:
            value=module.migrate_config(args[2])
            if op=='repeat_migrate':
                first=copy.deepcopy(value)
                value=module.migrate_config(value)
                if not equal(value,first):raise AssertionError('second migration lost or changed data')
                value=module.migrate_config(value)
                if not equal(value,first):raise AssertionError('third migration unstable')
        elif op=='trace':value=normalize_trace(module.merge_configs(*args,with_audit=True))
        else:
            value=module.merge_configs(*args)
            if op=='repeat_merge':
                first=copy.deepcopy(value);value=module.merge_configs({}, {},value)
                if not equal(value,first):raise AssertionError('remerging normalized user config changed data')
            if op=='defensive_copy':
                retained=copy.deepcopy(value)
                value['unknown']['deep'][0]['x']='h046-output-mutation'
                if not equal(args,before):raise AssertionError('returned value aliases caller input')
                value=retained
        if not equal(args,before):raise AssertionError('candidate changed input configuration')
        json.dumps(value,ensure_ascii=False,allow_nan=False)
        return {'status':'ok','result':value}
    except BaseException as error:
        if not equal(args,before):return {'status':'error','error_type':'AssertionError','message':'candidate changed input before failing'}
        return {'status':'error','error_type':type(error).__name__,'message':str(error)}
rows=[]
for c in request['cases']:
    actual=observe(c['layers'],c['op'])
    if c['invalid']:passed=actual['status']=='error' and actual['error_type']=='ValueError'
    else:
        expected=normalize_trace(c['expected']) if c['op']=='trace' else c['expected']['config']
        passed=actual['status']=='ok' and equal(actual['result'],expected)
    rows.append({'id':c['id'],'group':c['group'],'passed':passed,'op':c['op'],'actual':actual,'expected':c['expected']})
provided=request.get('audit_cases');provided=provided if isinstance(provided,list) else []
public=[];audit_checks=[]
for item in request['public_queries']:
    actual=observe(item['layers'],'trace');public.append({'id':item['id'],**actual})
    found=[r for r in provided if isinstance(r,dict) and r.get('case_id')==item['id']];passed=False
    if len(found)==1:
        record=found[0]
        try:
            passed=(record.get('status')=='error' and actual['status']=='error' and record.get('error_type')==actual['error_type']) or (
                record.get('status')=='ok' and actual['status']=='ok' and equal(normalize_trace(record['result']),actual['result']))
        except BaseException:passed=False
    audit_checks.append({'id':item['id'],'passed':bool(passed)})
output.write_text(json.dumps({'schema':'h046-independent-config-run/v1','cases':rows,'public_generated':public,'audit_checks':audit_checks},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'cases':len(rows),'passed':sum(r['passed'] for r in rows),'public_audit_passed':sum(r['passed'] for r in audit_checks)}))
