"""Protected actual localhost HTTP entrypoint. Candidate implements all business modules."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import argparse,json,sqlite3,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from project import api,repository
p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--port',type=int,default=0);p.add_argument('--ready-file',required=True);a=p.parse_args()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):self.execute()
    def do_POST(self):self.execute()
    def do_PATCH(self):self.execute()
    def execute(self):
        if self.command=='GET' and self.path in ('/','/project/client.mjs'):
            file=ROOT/('index.html' if self.path=='/' else 'project/client.mjs');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8' if self.path=='/' else 'text/javascript; charset=utf-8');self.end_headers();self.wfile.write(file.read_bytes());return
        db=sqlite3.connect(a.db,timeout=10)
        try:
            repository.initialize(db)
            raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
            body=json.loads(raw.decode()) if raw else {}
            status,value=api.handle(db,self.command,self.path,body,self.headers.get('X-Actor',''))
        except Exception:
            db.rollback();status,value=500,{'ok':False,'code':'INTERNAL','data':None,'replayed':False}
        finally:db.close()
        raw=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
db=sqlite3.connect(a.db,timeout=10)
if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'").fetchone() is None:
    db.execute('CREATE TABLE members(id TEXT PRIMARY KEY,email TEXT,name TEXT,role TEXT,status TEXT,version INTEGER)')
    for row in json.loads((ROOT/'fixtures/seed.json').read_text())['members']:
        db.execute('INSERT INTO members VALUES(:id,:email,:name,:role,:status,:version)',row)
    db.commit()
repository.initialize(db);db.close()
s=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);Path(a.ready_file).write_text(json.dumps({'host':'127.0.0.1','port':s.server_port}));s.serve_forever()
