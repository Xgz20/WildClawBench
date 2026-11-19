from pathlib import Path
import argparse,hashlib,importlib.util,json
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--output',default='results/regression.json');a=p.parse_args()
sp=importlib.util.spec_from_file_location('h051_public_runner',ROOT/'runner.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
cases=json.loads((ROOT/'fixtures/public_cases.json').read_text());expected=json.loads((ROOT/'fixtures/public_expected.json').read_text());actual=m.replay(ROOT,cases)
for row in actual['cases']:
 row['result']='PASS' if row['status']=='completed' and m.equal(row['trace'],expected[row['case_id']]) else 'FAIL'
actual['schema_version']='h051-regression/v1'
actual['bindings']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('permission_matrix.csv','export_contract.json','repair_plan.md','plan_items.json','fixtures/public_cases.json','fixtures/public_expected.json','runner.py')}
out=Path(a.output).resolve();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(actual,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(out),'passed':sum(x['result']=='PASS' for x in actual['cases']),'total':len(actual['cases'])}))
