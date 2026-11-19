from pathlib import Path
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
try:merge=importlib.import_module('project.config').merge_configs;load_error=None
except BaseException as error:merge=None;load_error=type(error).__name__+': '+str(error)
items=[]
for path in sorted((root/'fixtures/configs').glob('*.json')):
    payload=json.loads(path.read_text())
    try:
        if load_error:raise RuntimeError(load_error)
        value=merge(payload['defaults'],payload['project'],payload['user'],with_audit=True)
        items.append({'case_id':payload['case_id'],'status':'ok','result':value})
    except BaseException as error:items.append({'case_id':payload['case_id'],'status':'error','error_type':type(error).__name__,'message':str(error)})
output=root/'results';output.mkdir(exist_ok=True)
audit={'schema_version':'h046-migration-audit/v1','source_sha256':sha(root/'project/config.py'),
       'input_sha256':{p.relative_to(root).as_posix():sha(p) for p in sorted((root/'fixtures/configs').glob('*.json'))},'cases':items}
path=output/'migration_audit.json';path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
command=[sys.executable,'-B','-m','unittest','project.test_public','-v']
p=subprocess.run(command,cwd=root,text=True,capture_output=True,check=False,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
found=re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped[^\n]*)$',p.stderr,re.M)
report={'schema_version':'h046-public-test-run/v1','source_sha256':sha(root/'project/config.py'),'migration_audit_sha256':sha(path),
        'command':command,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,
        'test_results':[{'test':a+' ('+b+')','status':c} for a,b,c in found]}
(output/'tests.txt').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'case_count':len(items),'errors':sum(x['status']=='error' for x in items),'public_returncode':p.returncode}))
sys.exit(p.returncode)
