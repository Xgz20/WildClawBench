"""Trusted probe of a captured pure Python API source; no OS sandbox claim."""
from pathlib import Path
import hashlib, importlib.util, json, sys
spec=importlib.util.spec_from_file_location('h050_profile',Path(__file__).with_name('profile.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
raw=Path(sys.argv[1]).read_bytes();requests=json.load(sys.stdin)
try:fn=p.load_source(raw)
except p.ProfileUnsupported as exc:
 print(json.dumps({'status':'profile_unsupported','error':str(exc)}));raise SystemExit(0)
except Exception as exc:
 print(json.dumps({'status':'candidate_error','error':type(exc).__name__+': '+str(exc)}));raise SystemExit(0)
out=[]
for row in requests:
 records=json.loads(json.dumps(row['records']));query=json.loads(json.dumps(row['query']));before=json.dumps([records,query],sort_keys=True)
 try:
  result=fn(records,query,row['version']);json.dumps(result,allow_nan=False)
  out.append({'case_id':row.get('case_id'),'status':'completed','output':result,'inputs_unchanged':before==json.dumps([records,query],sort_keys=True)})
 except p.ProfileUnsupported as exc:out.append({'case_id':row.get('case_id'),'status':'profile_unsupported','error':str(exc)})
 except Exception as exc:out.append({'case_id':row.get('case_id'),'status':'candidate_error','error':type(exc).__name__+': '+str(exc)})
print(json.dumps({'status':'completed','source_sha256':hashlib.sha256(raw).hexdigest(),'cases':out},ensure_ascii=False,allow_nan=False))
