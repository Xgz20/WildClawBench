import copy
import json
from pathlib import Path
import unittest
from project import auth, export, routes

class PublicCompatibility(unittest.TestCase):
    def setUp(self):
        self.db=json.loads((Path(__file__).resolve().parents[1]/'fixtures/users.json').read_text())
        self.sessions={}
    def token(self,name):
        u=next(u for u in self.db['users'] if u['id']==name+'-public44')
        return auth.login(self.db,self.sessions,u['username'],u['password'])
    def test_enabled_student_can_log_in(self):
        self.assertTrue(self.token('s1'))
    def test_teacher_can_export_owned_resource(self):
        value=export.export_data(self.db,self.sessions,self.token('t1'),'ra-public44',['student_id','score'])
        self.assertEqual([r['score'] for r in value['rows']],[81,93])
    def test_admin_route_keeps_legal_export(self):
        value=routes.export_route(self.db,self.sessions,{'token':self.token('admin'),'resource_id':'ra2-public44'})
        self.assertEqual(value['status'],200)
        self.assertEqual(len(value['body']['rows']),1)
    def test_unknown_session_is_unauthorized(self):
        value=routes.export_route(self.db,self.sessions,{'token':'not-a-session','resource_id':'ra-public44'})
        self.assertEqual(value['status'],401)

if __name__=='__main__': unittest.main()
