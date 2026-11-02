#!/usr/bin/env python3
"""Check frozen reference workbooks against their authored automatic grader.

This is a framework self-check, not a model evaluation or semantic judgment.
Two data tasks requiring prior semantic rule review are explicitly excluded.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from eval_general_e2e.datasets.bundle import compile_dataset,GENERAL70_V2_DEFINITION
from src.utils.task_parser import parse_task_md


def check(row,contract,output,probe_rule_review_paths=False):
    tid=row['task_id']
    if not probe_rule_review_paths and tid.startswith(('03_Data_Analysis_task_001_','03_Data_Analysis_task_010_')):
        return {'task_id':tid,'status':'requires_semantic_rule_review','not_model_evaluation':True}
    work=output/tid/'workspace';work.mkdir(parents=True,exist_ok=False)
    source=ROOT/row['source']['workspace_path']
    shutil.copytree(source/'exec',work,dirs_exist_ok=True)
    shutil.copytree(source/'gt',work/'gt')
    results=work/'results';results.mkdir(exist_ok=True)
    prompt=parse_task_md(ROOT/row['source']['task_path'])['prompt']
    targets=set(re.findall(r'results/([^`\s/]+\.xlsx)',prompt))
    copied=[]
    for name in targets:
        matches=list((source/'gt').rglob(name))
        if len(matches)!=1:return {'task_id':tid,'status':'reference_layout_requires_review','name':name}
        shutil.copyfile(matches[0],results/name);copied.append(name)
    request=work.parent/'request.json';result=work.parent/'worker-result.json'
    request.write_text(json.dumps({'schema_version':'wildclawbench.general-e2e-rule-worker-request/v1',
        'workspace_path':str(work),'transcript':[], 'automated_checks':contract['automated_checks'],
        'rule_result_adapter':contract.get('rule_result_adapter')},ensure_ascii=False))
    worker=ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/rule_worker.py'
    try:
        process=subprocess.run([sys.executable,'-X','utf8',str(worker),'--request',str(request),'--result',str(result)],
            capture_output=True,text=True,timeout=60)
    except subprocess.TimeoutExpired:
        return {'task_id':tid,'status':'selfcheck_timeout','not_model_evaluation':True}
    if not result.exists():return {'task_id':tid,'status':'worker_failed','stderr':process.stderr[-1000:]}
    payload=json.loads(result.read_text());raw=payload.get('raw_result') or payload.get('result') or {}
    numeric={k:v for k,v in raw.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
    return {'task_id':tid,'status':'completed' if payload.get('ok') else 'worker_failed',
        'not_model_evaluation':True,'reference_outputs':sorted(copied),'numeric_diagnostics':numeric,
        'error':payload.get('error'),'request_sha256':hashlib.sha256(request.read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--probe-rule-review-paths',action='store_true',help='Attempt raw reference checks without fabricating any semantic review')
    args=parser.parse_args()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest,members=compile_dataset(ROOT,definition=GENERAL70_V2_DEFINITION)
    contracts={json.loads(m.data)['task_id']:json.loads(m.data) for m in members if m.path.endswith('/private-scoring/contract.json')}
    rows=[r for r in manifest['tasks'] if r['category']=='data-analysis']
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(check,row,contracts[row['task_id']],out,args.probe_rule_review_paths) for row in rows]
        results=[f.result() for f in futures]
    report={'schema_version':'general-e2e-reference-selfcheck/v1','not_model_evaluation':True,
        'source_dataset_id':manifest['dataset_id'],'scope':20,'cases':results}
    (out/'reference-selfcheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'scope':20,'completed':sum(r['status']=='completed' for r in results),
        'requires_semantic_review':sum(r['status']=='requires_semantic_rule_review' for r in results),
        'other':sum(r['status'] not in {'completed','requires_semantic_rule_review'} for r in results)},ensure_ascii=False))


if __name__=='__main__':main()
