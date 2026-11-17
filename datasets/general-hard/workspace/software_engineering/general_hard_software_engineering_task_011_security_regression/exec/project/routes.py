import copy,re
from . import authorization as auth,exporter,health

def handle(state,actor_id,method,path,params):
    result=copy.deepcopy(state)
    if method=='GET' and path=='/health':return {'status':200,'headers':{},'body':health.health()},result
    try:
        action='preview' if path=='/preview' else 'job_create' if method=='POST' and path=='/jobs' else 'job_get' if path.startswith('/jobs/') else 'download'
        if action=='job_get':
            job=result['jobs'].get(path.split('/')[-1])
            if job is None:raise auth.AccessError(404,'NOT_FOUND')
            return {'status':200,'headers':{'content-type':'text/csv; charset=utf-8'},'body':job['csv']},result
        actor,rows,columns=auth.select_records(result,actor_id,action,params)
        if action=='preview':rows=rows[:2]
        text=exporter.render_csv(rows,columns)
        if action=='job_create':
            job_id=params['job_id'];result['jobs'][job_id]={'owner_id':actor_id,'tenant_id':actor['tenant_id'],'ids':[r['id'] for r in rows],'columns':columns,'csv':text}
            return {'status':202,'headers':{},'body':{'job_id':job_id,'row_count':len(rows)}},result
        return {'status':200,'headers':{'content-type':'text/csv; charset=utf-8'},'body':text},result
    except auth.AccessError as e:return {'status':e.status,'headers':{},'body':{'code':e.code}},result
