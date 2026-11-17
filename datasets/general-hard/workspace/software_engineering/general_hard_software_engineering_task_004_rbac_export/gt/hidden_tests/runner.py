"""Trusted behavior runner: operates on frozen cases, never on reference patches."""
from pathlib import Path
import copy
import importlib
import json
import sys
import traceback

workspace, case_file, output = map(Path, sys.argv[1:])
sys.path.insert(0,str(workspace))
cases=json.loads(case_file.read_text())
rows=[]
output.write_text(json.dumps({'schema':'h044-private-behavior-run/v1','phase':'candidate_start'})+'\n')
try:
    auth=importlib.import_module('project.auth')
    export=importlib.import_module('project.export')
    routes=importlib.import_module('project.routes')
except BaseException as exc:
    rows=[{'id':c['id'],'group':c['group'],'positive':c['expected']['status']==200,'passed':False,
           'candidate_error':'import: '+type(exc).__name__+': '+str(exc)} for c in cases]
else:
    for case in cases:
        db=copy.deepcopy(case['db']);sessions=copy.deepcopy(case['sessions']);q=copy.deepcopy(case['request'])
        initial_db=copy.deepcopy(db);initial_sessions=copy.deepcopy(sessions)
        detail=None
        try:
            if case['kind']=='login':
                if case['entry']=='route':
                    response=routes.login_route(db,sessions,q)
                    status=response.get('status');token=response.get('body',{}).get('token')
                    if status!=200 and response.get('body')!={'error':'unauthorized'}:
                        raise AssertionError('invalid login error body')
                else:
                    try:
                        token=auth.login(db,sessions,q.get('username'),q.get('password'));status=200
                    except auth.AuthError:
                        token=None;status=401
                actual={'status':status}
                if status==200:
                    if not isinstance(token,str) or not token or token in initial_sessions or token not in sessions:
                        raise AssertionError('token missing, reused, or absent from server store')
                    matched=[u for u in db['users'] if isinstance(q.get('username'),str) and u['username'].strip().casefold()==q['username'].strip().casefold()]
                    session=sessions[token]
                    if len(matched)!=1 or session.get('user_id')!=matched[0]['id'] or session.get('expires_at')!=db['now']+db['session_ttl'] or session.get('revoked') is not False:
                        raise AssertionError('issued session does not bind current user/TTL/revocation')
                    if set(sessions)-set(initial_sessions)!={token}:
                        raise AssertionError('login changed unrelated session membership')
                elif sessions!=initial_sessions:
                    raise AssertionError('failed login mutated sessions')
            elif case['kind']=='resolve':
                try:
                    principal=auth.resolve_session(db,sessions,q.get('token'))
                    actual={'status':200,'body':copy.deepcopy(principal)}
                    principal['_copy_probe']='must not mutate the authoritative user'
                except auth.AuthError:
                    actual={'status':401}
            elif case['entry']=='route':
                response=routes.export_route(db,sessions,q)
                status=response.get('status')
                if status==200:
                    actual={'status':200,'body':response.get('body')}
                else:
                    names={401:'unauthorized',403:'forbidden',404:'not_found',400:'bad_request'}
                    if status not in names or response.get('body')!={'error':names[status]}:
                        raise AssertionError('wrong status/error envelope')
                    actual={'status':status}
            else:
                try:
                    value=export.export_data(db,sessions,q.get('token'),q.get('resource_id'),q.get('fields'))
                    actual={'status':200,'body':value}
                except auth.AuthError:
                    actual={'status':401}
                except export.ExportDenied:
                    actual={'status':403}
                except KeyError:
                    actual={'status':404}
                except ValueError:
                    actual={'status':400}
            if db!=initial_db or case['kind']!='login' and sessions!=initial_sessions:
                raise AssertionError('export/resolve mutated authoritative data or session state')
            passed=actual==case['expected']
        except BaseException as exc:
            passed=False;actual=None;detail=type(exc).__name__+': '+str(exc)
        rows.append({'id':case['id'],'group':case['group'],'positive':case['expected']['status']==200,
                     'passed':passed,'actual':actual,'expected':case['expected'],'candidate_error':detail})
output.write_text(json.dumps({'schema':'h044-private-behavior-run/v1','cases':rows},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'case_count':len(rows),'passed':sum(r['passed'] for r in rows)}))

