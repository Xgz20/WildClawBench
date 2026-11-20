"""Run actual candidate queries and bound-value changes in inert SQLite databases."""
from pathlib import Path
import copy
import importlib
import json
import math
import re
import sqlite3
import sys

workspace,gt,request_path,output=map(Path,sys.argv[1:])
request=json.loads(request_path.read_text())
schema=(gt/'schema.sql').read_text()
def database(data):
    connection=sqlite3.connect(':memory:');connection.executescript(schema)
    for table,rows in data.items():
        for row in rows:
            names=list(row)
            connection.execute('INSERT INTO "'+table+'" ('+','.join('"'+n+'"' for n in names)+') VALUES ('+','.join('?' for _ in names)+')',[row[n] for n in names])
    connection.commit();connection.execute('PRAGMA query_only=ON')
    def authorize(action,a,b,db,trigger):
        allowed={sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_RECURSIVE}
        if action not in allowed:return sqlite3.SQLITE_DENY
        if action==sqlite3.SQLITE_READ and a not in {'customer','order'}:return sqlite3.SQLITE_DENY
        if action==sqlite3.SQLITE_FUNCTION and (b or a or '').lower() in {'load_extension','readfile','writefile'}:return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    connection.set_authorizer(authorize)
    return connection
try:
    private=database(json.loads((gt/'private_data.json').read_text()))
    public=database(json.loads((gt/'protected_inputs/fixtures/data.json').read_text()))
except Exception as error:
    output.write_text(json.dumps({'infrastructure_error':'H045_DB_SETUP_FAILED','detail':type(error).__name__+': '+str(error)})+'\n')
    raise SystemExit(2)
output.write_text(json.dumps({'phase':'candidate_start'})+'\n')
sys.path.insert(0,str(workspace))
try:
    build=importlib.import_module('project.query_builder').build_query
    load_error=None
except BaseException as error:
    build=None;load_error=type(error).__name__+': '+str(error)

def placeholders(sql):
    """Lex placeholders outside quoted literals/identifiers and comments."""
    anonymous=0;names=[];i=0
    while i<len(sql):
        if sql.startswith('--',i):
            end=sql.find('\n',i+2);i=len(sql) if end<0 else end+1;continue
        if sql.startswith('/*',i):
            end=sql.find('*/',i+2)
            if end<0:raise ValueError('unterminated SQL comment')
            i=end+2;continue
        char=sql[i]
        if char in "'\"`[":
            closing=']' if char=='[' else char;i+=1
            while i<len(sql):
                if sql[i]==closing:
                    if char!='[' and i+1<len(sql) and sql[i+1]==closing:i+=2;continue
                    i+=1;break
                i+=1
            continue
        if char=='?':
            if i+1<len(sql) and sql[i+1].isdigit():raise ValueError('numbered placeholders unsupported')
            anonymous+=1;i+=1;continue
        if char==':':
            match=re.match(r':([A-Za-z_][A-Za-z_0-9]*)',sql[i:])
            if match:names.append(match.group(1));i+=len(match.group(0));continue
        if char in '@$':raise ValueError('unsupported parameter style')
        i+=1
    return anonymous,names
def binding_shape(sql,params):
    if not isinstance(sql,str) or not sql.strip():raise ValueError('SQL string required')
    anonymous,names=placeholders(sql)
    if isinstance(params,(list,tuple)):
        if names or anonymous!=len(params):raise ValueError('placeholder/sequence mismatch')
        values=list(params)
    elif isinstance(params,dict):
        if anonymous or set(names)!=set(params):raise ValueError('placeholder/mapping mismatch')
        values=list(params.values())
    else:raise ValueError('binding container required')
    if any(v is not None and type(v) not in (str,int,float) or isinstance(v,float) and not math.isfinite(v) for v in values):
        raise ValueError('unsupported bound value')
    return values
def rows(connection,sql,params,spec):
    steps=[0]
    def progress():steps[0]+=1;return int(steps[0]>2000)
    connection.set_progress_handler(progress,1000)
    result=[list(row) for row in connection.execute(sql,params).fetchall()]
    connection.set_progress_handler(None,0)
    if not spec.get('order_by'):result.sort(key=lambda row:json.dumps(row,ensure_ascii=False,sort_keys=True))
    return result
def observe(spec,connection):
    sql=None;params=None
    try:
        if load_error:raise RuntimeError(load_error)
        original=copy.deepcopy(spec);argument=copy.deepcopy(spec)
        pair=build(argument)
        if argument!=original:raise ValueError('candidate mutated query specification')
        if not isinstance(pair,(tuple,list)) or len(pair)!=2:raise ValueError('query pair required')
        sql,params=pair
        # SQLite itself checks executable binding count; the lexical audit also detects unused named keys.
        value=rows(connection,sql,params,spec)
        shape_error=None
        try:binding_shape(sql,params)
        except Exception as error:shape_error=type(error).__name__+': '+str(error)
        return {'status':'ok','sql':sql,'params':params,'rows':value,'binding_shape_error':shape_error}
    except BaseException as error:
        return {'status':'error','sql':sql,'params':params,'error_type':type(error).__name__,'message':str(error)}
def scalar_values(node):
    if not isinstance(node,dict):return []
    if 'all' in node or 'any' in node:return [v for n in node.get('all',node.get('any',[])) for v in scalar_values(n)]
    value=node.get('value')
    return [v for v in (value if isinstance(value,list) else [value]) if v is not None]
observations=[]
for case in request['cases']:
    actual=observe(case['spec'],private)
    if case['invalid']:
        passed=actual['status']=='error' and actual['error_type']=='ValueError'
        bound_ok=None;rebound=None
    else:
        passed=actual['status']=='ok' and actual['rows']==case['expected']['rows']
        bound_ok=actual.get('binding_shape_error') is None if actual['status']=='ok' else False
        # The pre-frozen public contract requires every non-NULL external leaf value
        # to remain bound, including ordinary numeric/date/business queries.
        if bound_ok:
            values=binding_shape(actual['sql'],actual['params'])
            equivalent=lambda a,b:(type(a) is type(b) or type(a) in (int,float) and type(b) in (int,float)) and a==b
            bound_ok=all(any(equivalent(v,p) for p in values) for v in scalar_values(case['spec'].get('where')))
        passed=passed and bound_ok
        rebound=None
        if case['binding'] and actual['status']=='ok':
            try:
                values=binding_shape(actual['sql'],actual['params'])
                inputs=scalar_values(case['spec'].get('where'))
                bound_ok=bound_ok and all(any(type(v) is type(p) and v==p for p in values) for v in inputs)
                bound_ok=bound_ok and all(not isinstance(v,str) or v not in actual['sql'] for v in inputs)
                reb=case['rebind'];params=actual['params']
                convert=lambda v:reb['new'] if type(v) is type(reb['old']) and v==reb['old'] else v
                params={k:convert(v) for k,v in params.items()} if isinstance(params,dict) else [convert(v) for v in params]
                rebound=rows(private,actual['sql'],params,reb['spec'])
                bound_ok=bound_ok and rebound==reb['expected_rows']
            except BaseException as error:
                bound_ok=False;rebound={'candidate_error':type(error).__name__+': '+str(error)}
            passed=passed and bound_ok
    observations.append({'id':case['id'],'group':case['group'],'passed':bool(passed),'actual':actual,
                         'expected':case['expected'],'binding_passed':bound_ok,'actual_rebound_rows':rebound})

provided=request.get('audit_cases')
provided=provided if isinstance(provided,list) else []
audit_checks=[];public_generated=[]
for item in request['public_queries']:
    actual=observe(item['spec'],public);public_generated.append({'id':item['id'],**actual})
    selected=[r for r in provided if isinstance(r,dict) and r.get('id')==item['id']]
    passed=False;replay=None
    if len(selected)==1:
        record=selected[0]
        if actual['status']=='error':
            passed=record.get('status')=='error' and record.get('error_type')==actual['error_type']
            if passed and isinstance(record.get('sql'),str):
                try:rows(public,record['sql'],record.get('params'),item['spec']);passed=False
                except BaseException as error:passed=type(error).__name__==record.get('error_type')
        elif record.get('status')=='ok':
            try:
                binding_shape(record.get('sql'),record.get('params'))
                replay=rows(public,record['sql'],record['params'],item['spec'])
                reported=record.get('rows')
                if isinstance(reported,list) and not item['spec'].get('order_by'):
                    reported=sorted(reported,key=lambda row:json.dumps(row,ensure_ascii=False,sort_keys=True))
                passed=replay==actual['rows'] and reported==replay
            except BaseException as error:
                replay={'candidate_audit_error':type(error).__name__+': '+str(error)}
    audit_checks.append({'id':item['id'],'passed':passed,'replayed_rows':replay})
output.write_text(json.dumps({'schema':'h045-private-sqlite-run/v1','sqlite_version':sqlite3.sqlite_version,
                              'cases':observations,'public_generated':public_generated,'audit_checks':audit_checks},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'cases':len(observations),'passed':sum(r['passed'] for r in observations),'audit_passed':sum(r['passed'] for r in audit_checks),'sqlite_version':sqlite3.sqlite_version}))

