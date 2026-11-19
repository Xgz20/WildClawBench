"""Legacy mutable request state."""
import json
def new_state(request_id):
    return {'request_id':request_id,'status':'streaming','body':'','reasoning':'','last_seq':0,'done':False,'error':None}
def apply_event(state,event):
    value=json.loads(event['data'])
    if value.get('request_id')!=state['request_id']:return state
    state['last_seq']=value['seq']
    if value['kind'] in ['body','reasoning']:state['body']+=value['text']
    elif value['kind']=='done':state['status']='succeeded';state['done']=True
    elif value['kind']=='error':state['status']='failed';state['error']={'code':value['code'],'message':value['message']}
    elif value['kind']=='cancel':state['status']='cancelled'
    return state
def mark_disconnected(state):state['status']='succeeded';state['done']=True;return state
def mark_reconnected(state):return new_state(state['request_id'])
def snapshot(state):return {k:state[k] for k in ['request_id','status','body','reasoning','last_seq','done','error']}
