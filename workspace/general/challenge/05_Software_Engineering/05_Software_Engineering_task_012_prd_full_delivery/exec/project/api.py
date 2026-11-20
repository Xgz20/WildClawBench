from urllib.parse import urlsplit,parse_qs
from . import repository as repo, service, legacy
def handle(db,method,path,body,actor_id):
    parsed=urlsplit(path);path=parsed.path
    if method=='GET' and path=='/health':return 200,legacy.health()
    try:
        who=service.actor(db,actor_id)
        if method=='GET' and path=='/session':return 200,{'ok':True,'code':'session','data':who,'replayed':False}
        if method=='GET' and path=='/members':
            rows=repo.list_members(db);return 200,{'ok':True,'code':'members','data':{'items':rows,'total':len(rows)},'replayed':False}
        if method=='GET' and path=='/audit':return 200,{'ok':True,'code':'audit','data':repo.list_audit(db),'replayed':False}
        if method=='GET' and path=='/legacy-export':return 200,{'ok':True,'code':'export','data':{'csv':legacy.export_members(db)},'replayed':False}
        if method=='POST' and path=='/members':return service.apply(db,actor_id,'create',None,body)
        if path.startswith('/members/'):
            target=path.split('/')[2]
            if method=='PATCH':return service.apply(db,actor_id,'update',target,body)
            if method=='POST' and path.endswith('/deactivate'):return service.apply(db,actor_id,'deactivate',target,body)
        raise service.Problem(404,'NOT_FOUND')
    except service.Problem as e:return e.status,{'ok':False,'code':e.code,'data':None,'replayed':False}
