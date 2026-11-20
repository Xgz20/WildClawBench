from .state import snapshot
def render_state(state):
    value=snapshot(state)
    return {'markdown':value['reasoning'] or value['body'],'reasoning':value['reasoning'],'status':value['status'],
            'completed':value['status'] in ['succeeded','failed','cancelled'],'error':value['error']}
