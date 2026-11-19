"""Prototype lacks authorization, normalization and conflict checks."""
from . import repository as repo
class Problem(Exception):
    def __init__(self,status,code):self.status,self.code=status,code
def actor(db,actor_id):
    value=repo.get_member(db,actor_id)
    if value is None:raise Problem(401,'UNAUTHENTICATED')
    return value
def apply(db,actor_id,operation,target,payload):
    who=actor(db,actor_id)
    if operation=='create':row={k:payload.get(k) for k in ('id','email','name','role')};row.update(status='active',version=1)
    else:
        row=repo.get_member(db,target)
        if row is None:raise Problem(404,'NOT_FOUND')
        if operation=='deactivate':row['status']='inactive'
        else:row.update({k:payload[k] for k in ('name','email','role') if k in payload})
        row['version']+=1
    repo.put_member(db,row,operation=='create')
    return (201 if operation=='create' else 200),{'ok':True,'code':{'create':'created','update':'updated','deactivate':'deactivated'}[operation],'data':row,'replayed':False}
