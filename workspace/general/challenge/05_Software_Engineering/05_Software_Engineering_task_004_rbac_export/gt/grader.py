"""Frozen behavior oracle and protected-input/evidence checks; no reference import."""
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

class H044TrustedInputError(RuntimeError):
    pass

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def required_json(path):
    if not path.is_file() or path.is_symlink():
        raise H044TrustedInputError('H044_GT_REQUIRED: '+path.name)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        raise H044TrustedInputError('H044_GT_INVALID: '+path.name) from exc

def test_results(text):
    found=re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped[^\n]*)$',text,re.M)
    return [{'test':name+' ('+owner+')','status':status} for name,owner,status in found]

def balanced(rows):
    slices=[[r for r in rows if r['positive']==v] for v in [True,False]]
    if any(not s for s in slices):
        raise H044TrustedInputError('H044_ORACLE_INVALID: positive/negative stratum empty')
    return sum(sum(r['passed'] for r in s)/len(s) for s in slices)/2

def grade(workspace_path, transcript=None):
    root=Path(workspace_path);gt=root/'gt'
    expected=required_json(gt/'expected.json')
    manifest=required_json(gt/'trusted_manifest.json')
    for relative,sha in manifest['files'].items():
        path=gt/relative
        if not path.is_file() or path.is_symlink():
            raise H044TrustedInputError('H044_GT_REQUIRED: '+relative)
        if digest(path)!=sha:
            raise H044TrustedInputError('H044_GT_SHA_MISMATCH: '+relative)
    business=required_json(gt/'business_oracle.json')['cases']
    boundary=required_json(gt/'counterexamples.json')['cases']
    cases=business+boundary
    if any([c['id'] for c in cases if c['group']==g]!=expected['case_ids'][g] for g in ['business','boundary']):
        raise H044TrustedInputError('H044_ORACLE_INVALID: case binding')
    contract=required_json(gt/'artifact_contract.json')
    evidence=required_json(gt/'evidence_requirements.json')
    protected=required_json(gt/'protected_sha256.json')
    sources=contract['mutable_sources']
    source_sha={};parse=[]
    for relative in sources:
        path=root/relative
        valid=path.is_file() and not path.is_symlink()
        if valid:
            source_sha[relative]=digest(path)
            try:
                ast.parse(path.read_text(encoding='utf-8'))
            except (OSError,UnicodeError,SyntaxError):
                valid=False
        parse.append(valid)
    changed=[relative for relative,sha in protected.items() if not (root/relative).is_file() or (root/relative).is_symlink() or digest(root/relative)!=sha]
    permitted=set(sources)|set(protected)
    extra=[]
    for p in root.rglob('*'):
        relative=p.relative_to(root)
        if relative.parts[0] in {'gt','results'} or '__pycache__' in relative.parts or p.suffix=='.pyc':
            continue
        if p.is_symlink() or p.is_file() and relative.as_posix() not in permitted:
            extra.append(relative.as_posix())
    delivery=.5*sum(parse)/len(parse)+.5*float(not changed and not extra)
    executable=Path(sys.executable)
    if not executable.is_file() or not os.access(executable,os.X_OK):
        raise H044TrustedInputError('H044_RUNTIME_UNAVAILABLE: existing Python executable missing')
    with tempfile.TemporaryDirectory(prefix='h044-independent-tests-') as temporary:
        temp=Path(temporary);candidate=temp/'candidate';candidate.mkdir()
        for relative in protected:
            target=candidate/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(gt/'protected_inputs'/relative,target)
        for relative in sources:
            if (root/relative).is_file() and not (root/relative).is_symlink():
                shutil.copyfile(root/relative,candidate/relative)
        case_path=temp/'cases.json';case_path.write_text(json.dumps(cases,ensure_ascii=False))
        output=temp/'observations.json'
        command=[str(executable),'-I','-B',str(gt/'hidden_tests/runner.py'),str(candidate),str(case_path),str(output)]
        try:
            private=subprocess.run(command,cwd=candidate,capture_output=True,text=True,check=False,timeout=12,
                                   env={'PATH':str(executable.parent),'PYTHONDONTWRITEBYTECODE':'1'})
        except subprocess.TimeoutExpired:
            observed=[{'id':c['id'],'group':c['group'],'positive':c['expected']['status']==200,'passed':False,'candidate_error':'candidate timeout'} for c in cases]
            private_record={'command':command,'returncode':None,'candidate_timeout':True}
        else:
            if not output.is_file():
                raise H044TrustedInputError('H044_HIDDEN_RUNNER_FAILED: '+private.stderr[-2000:])
            try:
                payload=json.loads(output.read_text())
                if payload.get('phase')=='candidate_start':
                    observed=[{'id':c['id'],'group':c['group'],'positive':c['expected']['status']==200,'passed':False,'candidate_error':'candidate process terminated: '+str(private.returncode)} for c in cases]
                elif private.returncode==0:
                    observed=payload['cases']
                else:
                    raise H044TrustedInputError('H044_HIDDEN_RUNNER_FAILED: '+private.stderr[-2000:])
            except (ValueError,KeyError) as exc:
                raise H044TrustedInputError('H044_HIDDEN_RUNNER_INVALID') from exc
            if [r['id'] for r in observed]!=[c['id'] for c in cases]:
                raise H044TrustedInputError('H044_HIDDEN_RUNNER_INVALID: case binding')
            private_record={'command':command,'returncode':private.returncode,'stdout':private.stdout,'stderr':private.stderr}
        public_command=[str(executable),*evidence['command_tail']]
        try:
            public=subprocess.run(public_command,cwd=candidate,text=True,capture_output=True,check=False,timeout=12,
                                  env={'PATH':str(executable.parent),'PYTHONDONTWRITEBYTECODE':'1'})
        except subprocess.TimeoutExpired:
            public_record={'command':public_command,'returncode':None,'candidate_timeout':True,'test_results':[],'stdout':'','stderr':''}
        else:
            public_record={'command':public_command,'returncode':public.returncode,'test_results':test_results(public.stderr),'stdout':public.stdout,'stderr':public.stderr}
    rule={'business_correctness':balanced([r for r in observed if r['group']=='business']),
          'boundary_cases':balanced([r for r in observed if r['group']=='boundary']),
          'delivery_integrity':delivery,'evidence_binding':0.0}
    receipt=None
    try:
        report=root/contract['report']
        if report.is_file() and not report.is_symlink():
            receipt=json.loads(report.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        receipt=None
    if isinstance(receipt,dict):
        bound=receipt.get('source_sha256') if isinstance(receipt.get('source_sha256'),dict) else {}
        binding=sum(bound.get(s)==source_sha.get(s) and s in source_sha for s in sources)/len(sources)
        command=receipt.get('command')
        complete=(receipt.get('schema_version')==contract['report_schema'] and isinstance(command,list)
                  and len(command)==len(evidence['command_tail'])+1 and command[1:]==evidence['command_tail']
                  and isinstance(command[0],str) and receipt.get('returncode')==public_record['returncode']
                  and public_record['returncode'] is not None
                  and len(public_record['test_results'])==evidence['public_test_count']
                  and receipt.get('test_results')==public_record['test_results']
                  and isinstance(receipt.get('stderr'),str)
                  and test_results(receipt['stderr'])==public_record['test_results']
                  and receipt.get('stdout')==public_record['stdout'])
        rule['evidence_binding']=.5*binding+.5*float(complete)
    rule['overall_score']=sum(rule[k]*w for k,w in expected['weights'].items())
    derived=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not derived:
        raise H044TrustedInputError('H044_RULE_EVIDENCE_DIR_REQUIRED')
    witness={'schema':'h044-independent-author-test-evidence/v1','purpose':'actual behavior observations; not Harness/Judge/final score',
             'source_sha256':source_sha,'trusted_gt_manifest_sha256':digest(gt/'trusted_manifest.json'),
             'protected_changes':changed,'extra_paths':extra,'private_subprocess':private_record,
             'public_subprocess':public_record,'cases':observed,'rule_result':rule}
    destination=Path(derived)/'h044-test-witness.json'
    destination.write_text(json.dumps(witness,ensure_ascii=False,indent=2)+'\n')
    return rule

