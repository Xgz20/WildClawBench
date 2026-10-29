"""Unsafe prototype trusts requested rows instead of checking scope."""
class AccessError(Exception):
    def __init__(self,status,code):self.status,self.code=status,code
def actor_for(state,actor_id,action):
    actor=state['actors'].get(actor_id)
    if actor is None:raise AccessError(401,'UNAUTHENTICATED')
    return actor

def select_records(state,actor_id,action,params):
    actor=actor_for(state,actor_id,action)
    ids=params.get('ids')
    rows=state['records'] if ids is None else [r for r in state['records'] if r['id'] in ids]
    columns=params.get('columns') or ['id','display_name','note','amount']
    return actor,rows,columns
