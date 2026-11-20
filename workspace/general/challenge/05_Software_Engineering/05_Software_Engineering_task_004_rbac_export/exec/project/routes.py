"""Framework-free request adapters for the same in-memory service."""
from .auth import AuthError, login, resolve_session
from .export import ExportDenied, export_data

def login_route(db,sessions,request):
    try:
        return {'status':200,'body':{'token':login(db,sessions,request.get('username'),request.get('password'))}}
    except AuthError:
        return {'status':401,'body':{'error':'unauthorized'}}

def export_route(db,sessions,request):
    try:
        token=request.get('token')
        user=resolve_session(db,sessions,token)
        # Old UI forwarded its cached profile; this mutates trusted session state.
        if isinstance(request.get('identity'),dict):
            sessions[token]['cached_user'].update(request['identity'])
            user=sessions[token]['cached_user']
        resource=db['resources'][request.get('resource_id')]
        if resource['tenant_id']!=user['tenant_id']:
            raise ExportDenied('tenant_denied')
        result=export_data(db,sessions,token,request.get('resource_id'),request.get('fields'))
        return {'status':200,'body':result}
    except AuthError:
        return {'status':401,'body':{'error':'unauthorized'}}
    except ExportDenied:
        return {'status':403,'body':{'error':'forbidden'}}
    except KeyError:
        return {'status':404,'body':{'error':'not_found'}}
    except ValueError:
        return {'status':400,'body':{'error':'bad_request'}}
