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

class H046TrustedInputError(RuntimeError):pass
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def required(path):
    if not path.is_file() or path.is_symlink():raise H046TrustedInputError('H046_GT_REQUIRED: '+path.name)
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:raise H046TrustedInputError('H046_GT_INVALID: '+path.name) from error
def candidate_json(path):
    try:
        value=json.loads(path.read_text(encoding='utf-8')) if path.is_file() and not path.is_symlink() else None
        return value if isinstance(value,dict) else None
    except (OSError,ValueError):return None
def tests(text):
    return [{'test':a+' ('+b+')','status':c} for a,b,c in re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped[^\n]*)$',text,re.M)]

def grade(workspace_path,transcript=None):
    root=Path(workspace_path);gt=root/'gt'
    expected=required(gt/'expected.json');manifest=required(gt/'trusted_manifest.json')
    for relative,digest in manifest['files'].items():
        p=gt/relative
        if not p.is_file() or p.is_symlink():raise H046TrustedInputError('H046_GT_REQUIRED: '+relative)
        if sha(p)!=digest:raise H046TrustedInputError('H046_GT_SHA_MISMATCH: '+relative)
    cases=required(gt/'business_oracle.json')['cases']+required(gt/'counterexamples.json')['cases']
    if any([c['id'] for c in cases if c['group']==g]!=expected['case_ids'][g] for g in ['business','boundary']):
        raise H046TrustedInputError('H046_ORACLE_INVALID: fixed case IDs')
    contract=required(gt/'artifact_contract.json');evidence=required(gt/'evidence_requirements.json');protected=required(gt/'protected_sha256.json')
    source=root/contract['mutable_sources'][0];source_sha=sha(source) if source.is_file() and not source.is_symlink() else None
    parse=bool(source_sha)
    if parse:
        try:ast.parse(source.read_text(encoding='utf-8'))
        except (OSError,UnicodeError,SyntaxError):parse=False
    changed=[rel for rel,digest in protected.items() if not (root/rel).is_file() or (root/rel).is_symlink() or sha(root/rel)!=digest]
    permitted=set(protected)|set(contract['mutable_sources']);extra=[]
    for p in root.rglob('*'):
        rel=p.relative_to(root)
        if rel.parts[0] in {'gt','results'} or '__pycache__' in rel.parts or p.suffix=='.pyc':continue
        if p.is_symlink() or p.is_file() and rel.as_posix() not in permitted:extra.append(rel.as_posix())
    audit=candidate_json(root/contract['reports']['audit']);test_report=candidate_json(root/contract['reports']['tests'])
    audit_valid=isinstance(audit,dict) and audit.get('schema_version')==contract['schemas']['audit'] and isinstance(audit.get('cases'),list)
    tests_valid=isinstance(test_report,dict) and test_report.get('schema_version')==contract['schemas']['tests'] and isinstance(test_report.get('command'),list)
    delivery=.3*parse+.4*float(not changed and not extra)+.15*audit_valid+.15*tests_valid
    executable=Path(sys.executable)
    if not executable.is_file() or not os.access(executable,os.X_OK):raise H046TrustedInputError('H046_RUNTIME_UNAVAILABLE')
    public_queries=[]
    for path in sorted((gt/'protected_inputs/fixtures/configs').glob('*.json')):
        item=required(path)
        public_queries.append({'id':item['case_id'],'layers':[item['defaults'],item['project'],item['user']]})
    with tempfile.TemporaryDirectory(prefix='h046-independent-config-') as temp:
        temp=Path(temp);candidate=temp/'candidate';candidate.mkdir()
        for relative in protected:
            destination=candidate/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(gt/'protected_inputs'/relative,destination)
        if source_sha:
            staged_source=candidate/contract['mutable_sources'][0]
            shutil.copyfile(source,staged_source)
            if not staged_source.is_file() or sha(staged_source)!=source_sha:
                raise H046TrustedInputError('H046_CANDIDATE_STAGING_FAILED')
        request=temp/'request.json';output=temp/'observations.json'
        request.write_text(json.dumps({'cases':cases,'public_queries':public_queries,'audit_cases':audit.get('cases') if audit else None},ensure_ascii=False))
        command=[str(executable),'-I','-B',str(gt/'hidden_tests/runner.py'),str(candidate),str(gt),str(request),str(output)]
        try:
            process=subprocess.run(command,cwd=candidate,text=True,capture_output=True,check=False,timeout=15,env={'PATH':str(executable.parent),'PYTHONDONTWRITEBYTECODE':'1'})
        except subprocess.TimeoutExpired:
            payload={'cases':[{'id':c['id'],'group':c['group'],'passed':False,'candidate_error':'candidate timeout'} for c in cases],
                     'audit_checks':[{'id':p['id'],'passed':False} for p in public_queries]}
            private_record={'command':command,'returncode':None,'candidate_timeout':True}
        else:
            if not output.is_file():raise H046TrustedInputError('H046_HIDDEN_RUNNER_FAILED: '+process.stderr[-2000:])
            payload=required(output)
            if payload.get('infrastructure_error'):raise H046TrustedInputError(payload['infrastructure_error']+': '+payload.get('detail',''))
            if payload.get('phase')=='candidate_start':
                payload={'cases':[{'id':c['id'],'group':c['group'],'passed':False,'candidate_error':'candidate subprocess exit '+str(process.returncode)} for c in cases],
                         'audit_checks':[{'id':p['id'],'passed':False} for p in public_queries]}
            elif process.returncode!=0:raise H046TrustedInputError('H046_HIDDEN_RUNNER_FAILED: '+process.stderr[-2000:])
            private_record={'command':command,'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr}
        if [c['id'] for c in payload.get('cases',[])]!=[c['id'] for c in cases] or [c['id'] for c in payload.get('audit_checks',[])]!=evidence['public_ids']:
            raise H046TrustedInputError('H046_HIDDEN_RUNNER_INVALID: fixed denominator/case IDs')
        public_command=[str(executable),*evidence['command_tail']]
        try:public=subprocess.run(public_command,cwd=candidate,text=True,capture_output=True,check=False,timeout=12,env={'PATH':str(executable.parent),'PYTHONDONTWRITEBYTECODE':'1'})
        except subprocess.TimeoutExpired:public_record={'command':public_command,'returncode':None,'candidate_timeout':True,'test_results':[],'stdout':'','stderr':''}
        else:public_record={'command':public_command,'returncode':public.returncode,'stdout':public.stdout,'stderr':public.stderr,'test_results':tests(public.stderr)}
    rule={}
    for group,key in [('business','business_correctness'),('boundary','boundary_cases')]:
        records=[c for c in payload['cases'] if c['group']==group]
        rule[key]=sum(c['passed'] for c in records)/len(expected['case_ids'][group])
    fixture_sha={rel:digest for rel,digest in protected.items() if rel.startswith('fixtures/')}
    bound=.2*float(bool(audit) and audit.get('source_sha256')==source_sha and source_sha is not None
                  and audit.get('input_sha256')==fixture_sha)
    bound+=.2*float(bool(test_report) and test_report.get('source_sha256')==source_sha and source_sha is not None)
    bound+=.4*sum(c['passed'] for c in payload['audit_checks'])/len(evidence['public_ids'])
    actual=False
    if tests_valid:
        command=test_report['command'];audit_path=root/contract['reports']['audit']
        actual=(len(command)==len(evidence['command_tail'])+1 and isinstance(command[0],str) and bool(command[0])
                and command[1:]==evidence['command_tail']
                and type(test_report.get('returncode')) is int
                and test_report.get('returncode')==public_record['returncode'] and public_record['returncode'] is not None
                and len(public_record['test_results'])==evidence['test_count']
                and test_report.get('test_results')==public_record['test_results']
                and isinstance(test_report.get('stderr'),str) and tests(test_report['stderr'])==public_record['test_results']
                and test_report.get('stdout')==public_record['stdout'] and audit_path.is_file()
                and test_report.get('migration_audit_sha256')==sha(audit_path))
    bound+=.2*float(actual)
    rule['delivery_integrity']=delivery;rule['evidence_binding']=bound
    rule['overall_score']=sum(rule[k]*weight for k,weight in expected['weights'].items())
    derived=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not derived:raise H046TrustedInputError('H046_RULE_EVIDENCE_DIR_REQUIRED')
    witness={'schema':'h046-independent-config-witness/v1','purpose':'author real migration observations, not formal Harness/Judge/final score',
             'source_sha256':source_sha,'gt_manifest_sha256':sha(gt/'trusted_manifest.json'),
             'fixed_denominators':{g:len(expected['case_ids'][g]) for g in ['business','boundary']},
             'protected_changes':changed,'extra_paths':extra,'private_subprocess':private_record,'public_subprocess':public_record,'observations':payload,'rule_result':rule}
    (Path(derived)/'h046-migration-witness.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2)+'\n')
    return rule
