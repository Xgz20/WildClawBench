"""Local export service; intentionally retains the legacy permission gaps."""
from .auth import resolve_session

class ExportDenied(Exception):
    pass

FIELDS={'student':['student_id','display_name','score','feedback'],
        'teacher':['student_id','display_name','score','feedback','email'],
        'tenant_admin':['student_id','display_name','score','feedback','email','support_tag']}

def export_data(db, sessions, token, resource_id, fields=None):
    user=resolve_session(db,sessions,token)
    if user['role'] not in FIELDS:
        raise ExportDenied('role_denied')
    resource=db['resources'][resource_id]
    selected=FIELDS[user['role']] if fields is None else list(dict.fromkeys(fields))
    rows=resource['rows']
    if user['role']=='student':
        rows=[r for r in rows if r['student_id']==user['id']]
    return {'resource_id':resource_id,'fields':selected,
            'rows':[{key:r[key] for key in selected} for r in rows]}
