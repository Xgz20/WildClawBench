"""Run the protected public tests and bind their actual output to source bytes."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
files=['project/auth.py','project/export.py','project/routes.py']
command=[sys.executable,'-B','-m','unittest','discover','-s','tests','-v']
completed=subprocess.run(command,cwd=root,text=True,capture_output=True,check=False,
                         env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
tests=re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped[^\n]*)$',completed.stderr,re.M)
report={'schema_version':'h044-public-test-run/v1','command':command,'returncode':completed.returncode,
        'source_sha256':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files},
        'test_results':[{'test':name+' ('+owner+')','status':status} for name,owner,status in tests],
        'stdout':completed.stdout,'stderr':completed.stderr}
output=root/'results/security_tests.txt'
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'output':'results/security_tests.txt','returncode':completed.returncode,'test_count':len(tests)}))
sys.exit(completed.returncode)
