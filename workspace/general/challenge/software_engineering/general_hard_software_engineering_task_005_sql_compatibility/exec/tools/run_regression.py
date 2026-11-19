"""Produce actual query/audit records; no expected SQL or answer strings."""
from pathlib import Path
import hashlib
import importlib
import json
import os
import re
import sqlite3
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from project.db_fixture import open_database
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
try:
    build=importlib.import_module('project.query_builder').build_query
    load_error=None
except BaseException as exc:
    build=None;load_error=type(exc).__name__+': '+str(exc)
fixtures=json.loads((root/'fixtures/queries.json').read_text())['cases']
records=[]
for item in fixtures:
    db=open_database(root);sql=None;params=None
    try:
        if load_error:raise RuntimeError(load_error)
        sql,params=build(item['spec'])
        cursor=db.execute(sql,params)
        records.append({'id':item['id'],'status':'ok','sql':sql,'params':params,'rows':[list(r) for r in cursor.fetchall()]})
    except BaseException as error:
        records.append({'id':item['id'],'status':'error','sql':sql,'params':params,'error_type':type(error).__name__,'message':str(error)})
    finally:db.close()
result=root/'results';result.mkdir(exist_ok=True)
audit={'schema_version':'h045-query-audit/v1','source_sha256':sha(root/'project/query_builder.py'),
       'input_sha256':{p.relative_to(root).as_posix():sha(p) for p in sorted((root/'fixtures').iterdir()) if p.is_file()},
       'sqlite_version':sqlite3.sqlite_version,'cases':records}
audit_path=result/'query_audit.json';audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
command=[sys.executable,'-B','-m','unittest','project.test_public','-v']
completed=subprocess.run(command,cwd=root,text=True,capture_output=True,check=False,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
tests=re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped[^\n]*)$',completed.stderr,re.M)
report={'schema_version':'h045-public-test-run/v1','source_sha256':sha(root/'project/query_builder.py'),'query_audit_sha256':sha(audit_path),
        'command':command,'returncode':completed.returncode,'stdout':completed.stdout,'stderr':completed.stderr,
        'test_results':[{'test':name+' ('+owner+')','status':status} for name,owner,status in tests]}
(result/'tests.txt').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'audit_cases':len(records),'query_errors':sum(c['status']=='error' for c in records),'public_returncode':completed.returncode}))
sys.exit(completed.returncode)
