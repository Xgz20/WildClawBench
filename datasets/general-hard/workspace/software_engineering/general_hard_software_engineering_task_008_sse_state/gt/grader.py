from pathlib import Path
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

class H048TrustedInputError(RuntimeError):pass
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def required(p):
    if not p.is_file() or p.is_symlink():raise H048TrustedInputError('H048_GT_REQUIRED: '+p.name)
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError) as e:raise H048TrustedInputError('H048_GT_INVALID: '+p.name) from e
def candidate_json(p):
    try:v=json.loads(p.read_text()) if p.is_file() and not p.is_symlink() else None;return v if isinstance(v,dict) else None
    except (OSError,ValueError):return None
def tests(text):return [{'test':a+' ('+b+')','status':c} for a,b,c in re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped[^\n]*)$',text,re.M)]
def grade(workspace_path,transcript=None):
    root=Path(workspace_path);gt=root/'gt';expected=required(gt/'expected.json');manifest=required(gt/'trusted_manifest.json')
    for rel,digest in manifest['files'].items():
        p=gt/rel
        if not p.is_file() or p.is_symlink():raise H048TrustedInputError('H048_GT_REQUIRED: '+rel)
        if sha(p)!=digest:raise H048TrustedInputError('H048_GT_SHA_MISMATCH: '+rel)
    cases=required(gt/'business_oracle.json')['cases']+required(gt/'counterexamples.json')['cases']
    if any([c['id'] for c in cases if c['group']==g]!=expected['case_ids'][g] for g in ['business','boundary']):raise H048TrustedInputError('H048_ORACLE_INVALID: fixed IDs')
    contract=required(gt/'artifact_contract.json');evidence=required(gt/'evidence_requirements.json');protected=required(gt/'protected_sha256.json')
    source_sha={};parsed=[]
    for rel in contract['mutable_sources']:
        p=root/rel;ok=p.is_file() and not p.is_symlink()
        if ok:
            source_sha[rel]=sha(p)
            try:ast.parse(p.read_text(encoding='utf-8'))
            except (OSError,ValueError,SyntaxError,UnicodeError):ok=False
        parsed.append(ok)
    changed=[rel for rel,digest in protected.items() if not (root/rel).is_file() or (root/rel).is_symlink() or sha(root/rel)!=digest]
    allowed=set(protected)|set(contract['mutable_sources']);extra=[]
    for p in root.rglob('*'):
        rel=p.relative_to(root)
        if rel.parts[0] in {'gt','results'} or '__pycache__' in rel.parts or p.suffix=='.pyc':continue
        if p.is_symlink() or p.is_file() and rel.as_posix() not in allowed:extra.append(rel.as_posix())
    report=candidate_json(root/contract['report']);valid=bool(report) and report.get('schema_version')==contract['schema'] and isinstance(report.get('cases'),list) and isinstance(report.get('test_run'),dict)
    delivery=.4*sum(parsed)/len(parsed)+.4*float(not changed and not extra)+.2*float(valid)
    executable=Path(sys.executable)
    if not executable.is_file() or not os.access(executable,os.X_OK):raise H048TrustedInputError('H048_RUNTIME_UNAVAILABLE')
    public=[json.loads(line) for line in (gt/'protected_inputs/fixtures/events.jsonl').read_text().splitlines()]
    with tempfile.TemporaryDirectory(prefix='h048-independent-replay-') as directory:
        temp=Path(directory);candidate=temp/'candidate';candidate.mkdir()
        for rel in protected:
            target=candidate/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(gt/'protected_inputs'/rel,target)
        for rel,digest in source_sha.items():
            target=candidate/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/rel,target)
            if sha(target)!=digest:raise H048TrustedInputError('H048_CANDIDATE_STAGING_FAILED: '+rel)
        request=temp/'request.json';output=temp/'observations.json';request.write_text(json.dumps({'cases':cases,'public_cases':public,'report_cases':report.get('cases') if report else None},ensure_ascii=False))
        command=[str(executable),'-I','-B',str(gt/'hidden_tests/runner.py'),str(candidate),str(gt),str(request),str(output)]
        try:p=subprocess.run(command,cwd=candidate,text=True,capture_output=True,check=False,timeout=20,env={'PATH':str(executable.parent),'PYTHONDONTWRITEBYTECODE':'1'})
        except subprocess.TimeoutExpired:payload=None;private_record={'command':command,'returncode':None,'candidate_timeout':True}
        else:
            if not output.is_file():raise H048TrustedInputError('H048_HIDDEN_RUNNER_FAILED: '+p.stderr[-2000:])
            payload=required(output);private_record={'command':command,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
            if payload.get('phase')=='candidate_start':payload=None
            elif p.returncode!=0:raise H048TrustedInputError('H048_HIDDEN_RUNNER_FAILED: '+p.stderr[-2000:])
        if payload is None:
            payload={'cases':[{'id':c['id'],'group':c['group'],'score':0.0,'prefix_count':len(c['expected']['snapshots']),'prefix_passed':0,'final_passed':False,'candidate_error':'candidate subprocess exited or timed out'} for c in cases],
                     'report_checks':[{'id':c['id'],'passed':False} for c in public]}
        if [c['id'] for c in payload.get('cases',[])]!=[c['id'] for c in cases] or [c['id'] for c in payload.get('report_checks',[])]!=evidence['public_ids']:
            raise H048TrustedInputError('H048_HIDDEN_RUNNER_INVALID: fixed denominator')
        test_command=[str(executable),*evidence['command_tail']]
        try:p=subprocess.run(test_command,cwd=candidate,text=True,capture_output=True,check=False,timeout=12,env={'PATH':str(executable.parent),'PYTHONDONTWRITEBYTECODE':'1'})
        except subprocess.TimeoutExpired:test_record={'command':test_command,'returncode':None,'candidate_timeout':True,'stdout':'','stderr':'','test_results':[]}
        else:test_record={'command':test_command,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'test_results':tests(p.stderr)}
    result={key:sum(c['score'] for c in payload['cases'] if c['group']==group)/len(expected['case_ids'][group]) for group,key in [('business','business_correctness'),('boundary','boundary_cases')]}
    binding=0.0
    if report:
        declared=report.get('source_sha256') if isinstance(report.get('source_sha256'),dict) else {}
        input_bound=report.get('input_sha256')=={'fixtures/events.jsonl':protected['fixtures/events.jsonl']}
        binding=.4*sum(rel in source_sha and declared.get(rel)==source_sha[rel] for rel in contract['mutable_sources'])/len(parsed)*float(input_bound)
        binding+=.4*sum(c['passed'] for c in payload['report_checks'])/len(evidence['public_ids'])
        run=report.get('test_run') if isinstance(report.get('test_run'),dict) else {};command=run.get('command')
        same=(isinstance(command,list) and len(command)==len(evidence['command_tail'])+1 and isinstance(command[0],str) and bool(command[0]) and command[1:]==evidence['command_tail']
              and type(run.get('returncode')) is int and run['returncode']==test_record['returncode'] and test_record['returncode'] is not None
              and len(test_record['test_results'])==evidence['test_count'] and run.get('test_results')==test_record['test_results']
              and isinstance(run.get('stderr'),str) and tests(run['stderr'])==test_record['test_results'] and run.get('stdout')==test_record['stdout'])
        binding+=.2*float(same)
    result.update(delivery_integrity=delivery,evidence_binding=binding);result['overall_score']=sum(result[k]*weight for k,weight in expected['weights'].items())
    directory=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not directory:raise H048TrustedInputError('H048_RULE_EVIDENCE_DIR_REQUIRED')
    witness={'schema':'h048-independent-prefix-witness/v1','purpose':'actual offline author prefixes, not formal Harness/Judge/final score','source_sha256':source_sha,
             'gt_manifest_sha256':sha(gt/'trusted_manifest.json'),'fixed_scenario_denominators':{g:len(expected['case_ids'][g]) for g in ['business','boundary']},
             'fixed_prefix_count':sum(len(c['steps']) for c in cases),'protected_changes':changed,'extra_paths':extra,
             'private_subprocess':private_record,'public_subprocess':test_record,'observations':payload,'rule_result':result}
    (Path(directory)/'h048-prefix-witness.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2)+'\n');return result
