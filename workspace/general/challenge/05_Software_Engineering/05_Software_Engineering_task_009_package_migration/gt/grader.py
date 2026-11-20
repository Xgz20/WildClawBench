from pathlib import Path
import ast
import hashlib
import json
import os
import runpy
import shutil
import tempfile
import zipfile

class H049TrustedInputError(RuntimeError):pass
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def required(p):
    if not p.is_file() or p.is_symlink():raise H049TrustedInputError('H049_GT_REQUIRED: '+p.name)
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError) as e:raise H049TrustedInputError('H049_GT_INVALID: '+p.name) from e
def candidate_json(p):
    try:v=json.loads(p.read_text()) if p.is_file() and not p.is_symlink() else None;return v if isinstance(v,dict) else None
    except (OSError,ValueError):return None
def equal(a,b):
    if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
    if type(a) in (int,float) and type(b) in (int,float):return abs(a-b)<=1e-9
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b
def body(value):
    return {k:value[k] for k in ['ids','total','label','config','banner']} if isinstance(value,dict) and {'ids','total','label','config','banner'}<=set(value) else None
def ok(command):return isinstance(command,dict) and command.get('returncode')==0
def records(value,key):return value.get(key) if isinstance(value,dict) and isinstance(value.get(key),list) else []
def returncode(value):return value.get('returncode') if isinstance(value,dict) else None
def inside(path,parent):
    try:return Path(path).resolve().is_relative_to(Path(parent).resolve())
    except (TypeError,ValueError):return False
def grade(workspace_path,transcript=None):
    root=Path(workspace_path);gt=root/'gt';expected=required(gt/'expected.json');manifest=required(gt/'trusted_manifest.json')
    for rel,digest in manifest['files'].items():
        p=gt/rel
        if not p.is_file() or p.is_symlink():raise H049TrustedInputError('H049_GT_REQUIRED: '+rel)
        if sha(p)!=digest:raise H049TrustedInputError('H049_GT_SHA_MISMATCH: '+rel)
    contract=required(gt/'artifact_contract.json');protected=required(gt/'protected_sha256.json');evidence=required(gt/'evidence_requirements.json');runtime=required(gt/'runtime_contract.json')['interpreters']
    cases=required(gt/'business_oracle.json')['cases'];data=required(gt/'private_data.json');truth={c['id']:c['expected'] for c in cases}
    if [c['id'] for c in cases]!=expected['business_case_ids']:raise H049TrustedInputError('H049_ORACLE_INVALID')
    source={rel:sha(root/rel) for rel in contract['mutable'] if (root/rel).is_file() and not (root/rel).is_symlink()}
    parsed=[]
    for rel in contract['required_sources']:
        p=root/rel;valid=p.is_file() and not p.is_symlink()
        if valid and p.suffix=='.py':
            try:ast.parse(p.read_text(encoding='utf-8'))
            except (SyntaxError,ValueError,UnicodeError):valid=False
        if valid and p.suffix=='.toml':
            import tomllib
            try:tomllib.loads(p.read_text())
            except (ValueError,UnicodeError):valid=False
        parsed.append(valid)
    changed=[rel for rel,digest in protected.items() if not (root/rel).is_file() or (root/rel).is_symlink() or sha(root/rel)!=digest]
    permitted=set(protected)|set(contract['mutable']);extra=[]
    for p in root.rglob('*'):
        rel=p.relative_to(root)
        if rel.parts[0] in {'gt','results'} or '__pycache__' in rel.parts or p.suffix=='.pyc':continue
        if p.is_symlink() or p.is_file() and rel.as_posix() not in permitted:extra.append(rel.as_posix())
    report=candidate_json(root/contract['reports']['matrix']);matrix_valid=bool(report) and report.get('schema')==contract['matrix_schema'] and isinstance(report.get('versions'),list)
    notes=root/contract['reports']['notes'];notes_valid=notes.is_file() and not notes.is_symlink() and len(notes.read_text(encoding='utf-8',errors='replace').strip())>=80
    delivery=.3*sum(parsed)/len(parsed)+.4*float(not changed and not extra)+.15*float(matrix_valid)+.15*float(notes_valid)
    directory=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not directory:raise H049TrustedInputError('H049_RULE_EVIDENCE_DIR_REQUIRED')
    derived=Path(directory);public_cases=required(gt/'protected_inputs/fixtures/configs.json')['cases'];public_data=required(gt/'protected_inputs/fixtures/records.json')
    combined=[{'id':c['id'],'config':c['config']} for c in cases]+[{'id':'public:'+c['id'],'config':c['config'],'records':public_data,'entry':i<2} for i,c in enumerate(public_cases)]
    collect_ns=runpy.run_path(str(gt/'private_matrix.py'));business=[];boundaries=[];public_checks=[];artifacts=[]
    with tempfile.TemporaryDirectory(prefix='h049-independent-install-') as temp:
        temp=Path(temp);stage=temp/'candidate';stage.mkdir()
        for rel in protected:
            target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(gt/'protected_inputs'/rel,target)
        for rel,digest in source.items():
            target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/rel,target)
            if sha(target)!=digest:raise H049TrustedInputError('H049_CANDIDATE_STAGING_FAILED')
        previous_cache={key:os.environ.get(key) for key in ['PIP_CACHE_DIR','XDG_CACHE_HOME']}
        os.environ['PIP_CACHE_DIR']=str(temp/'pip-cache');os.environ['XDG_CACHE_HOME']=str(temp/'xdg-cache')
        try:matrix=collect_ns['collect'](stage,combined,data,runtime,temp/'matrix')
        except collect_ns['TrustedRuntimeError'] as error:raise H049TrustedInputError(str(error)) from error
        finally:
            for key,value in previous_cache.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
        defaults=required(gt/'protected_inputs/project/src/batchstamp/resources/defaults.json');banner=(gt/'protected_inputs/project/src/batchstamp/resources/banner.txt').read_text().rstrip('\n');resource_truth={'defaults':defaults,'banner':banner}
        for version in expected['interpreter_versions']:
            found=[v for v in matrix['versions'] if v['version']==version]
            if len(found)!=1:raise H049TrustedInputError('H049_MATRIX_VERSION_INVALID')
            v=found[0]
            for c in cases:
                for module in evidence['api_modules']:
                    rows=[r for r in v['api'] if r['id']==c['id'] and r['module']==module]
                    returned_correct=len(rows)==1 and ok(rows[0]['command']) and equal(body(rows[0]['result']),truth[c['id']])
                    observation=rows[0].get('input_observation') if len(rows)==1 else None
                    inputs_unchanged=isinstance(observation,dict) and observation.get('records_unchanged') is True and observation.get('config_unchanged') is True
                    business.append({'version':version,'id':c['id'],'module':module,'returned_correct':returned_correct,'inputs_unchanged':inputs_unchanged,'passed':returned_correct and inputs_unchanged})
            origin=v.get('origin_result') or {}
            checks={'build':ok(v['build']),'install':ok(v.get('install')),'src_members':v['src_members_match'],'resource_members':v['resource_members_match'],
                    'new_origin':inside(origin.get('package'),v['target']),'legacy_origin':inside(origin.get('legacy'),v['target']),
                    'resource_api':equal(v.get('resources_result'),resource_truth),'zip_resources':equal(v.get('zip_resources_result'),resource_truth),
                    'checkout_legacy':False,
                    'public_tests':ok(v['public_tests']),'distribution_version':origin.get('version')=='2.0.0'}
            try:checkout_body=json.loads(v['checkout_legacy']['stdout']) if ok(v['checkout_legacy']) else None
            except ValueError:checkout_body=None
            checks['checkout_legacy']=ok(v['checkout_legacy']) and equal(body(checkout_body),truth[cases[0]['id']])
            for kind in evidence['entry_kinds']:
                subset=[r for r in v['entries'] if r['kind']==kind and not r['id'].startswith('public:')]
                checks[kind]=len(subset)==2 and all(ok(r['command']) and equal(body(r['result']),truth[r['id']]) for r in subset)
            invalid=[]
            for item in v['invalid_inputs']:
                command=item['command']
                try:error=json.loads(command['stderr']) if command else None
                except ValueError:error=None
                invalid.append(bool(command) and command['returncode']==2 and command['stdout'].strip()=='' and error=={'error':'invalid_input'})
            checks['invalid_exit']=len(invalid)==4 and all(invalid)
            boundaries.extend({'version':version,'key':key,'passed':bool(checks[key])} for key in contract['boundary_labels'])
            if v['wheel']:
                target=derived/'built-wheels'/version/Path(v['wheel']).name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(v['wheel'],target);artifacts.append({'path':target.relative_to(derived).as_posix(),'sha256':sha(target)})
            reported=[p for p in (report.get('versions',[]) if report else []) if isinstance(p,dict) and p.get('version')==version]
            for cid in evidence['public_case_ids']:
                for module in evidence['api_modules']:
                    actual=[r for r in v['api'] if r['id']=='public:'+cid and r['module']==module]
                    stated=[r for r in records(reported[0],'api') if isinstance(r,dict) and r.get('id')==cid and r.get('module')==module] if len(reported)==1 else []
                    matched=len(stated)==len(actual)==1 and equal(body(stated[0].get('result')),body(actual[0].get('result'))) and returncode(stated[0].get('command'))==returncode(actual[0].get('command'))
                    public_checks.append({'version':version,'id':cid,'kind':module,'passed':matched})
            for cid in evidence['public_case_ids'][:2]:
                for kind in evidence['entry_kinds']:
                    actual=[r for r in v['entries'] if r['id']=='public:'+cid and r['kind']==kind]
                    stated=[r for r in records(reported[0],'entries') if isinstance(r,dict) and r.get('id')==cid and r.get('kind')==kind] if len(reported)==1 else []
                    matched=len(stated)==len(actual)==1 and equal(body(stated[0].get('result')),body(actual[0].get('result'))) and returncode(stated[0].get('command'))==returncode(actual[0].get('command'))
                    public_checks.append({'version':version,'id':cid,'kind':kind,'passed':matched})
        persisted_matrix=matrix
    wheel_checks=[]
    evidence_score=0.0
    if report:
        expected_input={r:protected[r] for r in ['fixtures/configs.json','fixtures/records.json']}
        evidence_score=.4*float(report.get('source_sha256')==source and report.get('input_sha256')==expected_input)
        evidence_score+=.4*sum(c['passed'] for c in public_checks)/28
        wheel_bind=[]
        for version in expected['interpreter_versions']:
            found=[v for v in report.get('versions',[]) if isinstance(v,dict) and v.get('version')==version];passed=False
            if len(found)==1 and isinstance(found[0].get('preserved_wheel'),dict):
                item=found[0]['preserved_wheel'];rel=item.get('path','');p=root/rel if isinstance(rel,str) else root
                if isinstance(rel,str) and rel.startswith('results/install_artifacts/') and inside(p,root/'results') and p.is_file() and not p.is_symlink() and sha(p)==item.get('sha256')==found[0].get('wheel_sha256'):
                    verification=runpy.run_path(str(gt/'wheel_evidence.py'))['verify'](p,root,source)
                    passed=verification['valid_source_agreement'];wheel_checks.append({'version':version,'path':rel,**verification})
            wheel_bind.append(passed)
        evidence_score+=.2*sum(wheel_bind)/2
    result={'business_correctness':sum(c['passed'] for c in business)/40,'boundary_cases':sum(c['passed'] for c in boundaries)/32,'delivery_integrity':delivery,'evidence_binding':evidence_score}
    result['overall_score']=sum(result[k]*w for k,w in expected['weights'].items())
    witness={'schema':'h049-independent-build-install-witness/v1','source_sha256':source,'gt_manifest_sha256':sha(gt/'trusted_manifest.json'),'fixed_denominators':{'business':40,'boundary':32,'public_replay':28},
             'business_checks':business,'boundary_checks':boundaries,'public_replay_checks':public_checks,'actual_matrix':persisted_matrix,'preserved_artifacts':artifacts,'delivered_wheel_source_checks':wheel_checks,'protected_changes':changed,'extra_paths':extra,'rule_result':result,
             'scope':'actual dual-interpreter author build/install/import/CLI observations, not Harness/Judge/final score'}
    (derived/'h049-install-witness.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2)+'\n');return result
