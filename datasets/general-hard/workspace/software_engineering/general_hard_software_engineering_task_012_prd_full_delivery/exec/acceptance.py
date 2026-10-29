"""Actual fixed public regression, producing source-bound native text evidence."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--output',default='results/tests.txt');p.add_argument('--work-root');a=p.parse_args()
out=Path(a.output).resolve();out.parent.mkdir(parents=True,exist_ok=True);work=Path(a.work_root).resolve() if a.work_root else out.parent/('acceptance-run-'+str(time.time_ns()))
sp=importlib.util.spec_from_file_location('h052_public_runner',ROOT/'runner.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
request={'candidate_root':str(ROOT),'trusted_root':str(ROOT),'work_root':str(work),'cases':json.loads((ROOT/'fixtures/acceptance_cases.json').read_text())}
raw=r.replay(request,work.parent/(work.name+'-raw-response.json'))
expected=json.loads((ROOT/'fixtures/acceptance_expected.json').read_text());rows=[]
for actual in raw['cases']:
 target=expected[actual['case_id']];case=next(c for c in request['cases'] if c['case_id']==actual['case_id']);ok=r.satisfies(case,actual,target)
 rows.append({'case_id':actual['case_id'],'status':'PASS' if ok else 'FAIL','actual':actual})
report={'schema_version':'h052-acceptance-run/v1','source_sha256':raw['source_sha256'],'source_digest':raw['source_digest'],'fixture_sha256':r.sha(ROOT/'fixtures/acceptance_cases.json'),'public_expected_sha256':r.sha(ROOT/'fixtures/acceptance_expected.json'),'runner_sha256':r.sha(ROOT/'runner.py'),'client_runner_sha256':r.sha(ROOT/'client_runner.mjs'),'runtime':raw['runtime'],'cases':rows,'scope':raw['scope']}
out.write_text('实际本地 HTTP / SQLite / JS 控制器回归；独立源码绑定。\n\n```json\n'+json.dumps(report,ensure_ascii=False,indent=2)+'\n```\n',encoding='utf-8')
print(json.dumps({'output':str(out),'source_digest':raw['source_digest'],'passed':sum(x['status']=='PASS' for x in rows),'total':len(rows)}))
