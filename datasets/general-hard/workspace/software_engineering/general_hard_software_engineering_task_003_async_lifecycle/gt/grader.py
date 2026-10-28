"""H043: execute independent protocol tests against only frozen delivered source.
No patch-string matching, reference-code oracle, network, real providers or Judge.
"""
from pathlib import Path
import hashlib,json,os,sys,subprocess,shutil,re

class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mean(v):
    v=list(v);return sum(v)/len(v) if v else 0.
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def safe(root,name):
    p=root/name
    return p if not p.is_symlink() and p.is_file() and root in p.resolve().parents else None
def read_report(p):
    if p is None:return None
    if p.stat().st_size>4_000_000:raise TrustedEvidenceError('NEEDS_REPORT_REVIEW: legal report exceeds bounded reader')
    try:return p.read_text(encoding='utf-8-sig')
    except UnicodeError:return None
def grade(transcript=None,workspace_path=None,**kwargs):
    if not workspace_path:raise TrustedEvidenceError('candidate workspace context missing')
    root=Path(workspace_path).resolve();gt=Path(__file__).resolve().parent
    try:binding=json.loads((gt/'scoring_contract.json').read_text());expected=json.loads((gt/'expected.json').read_text());protected=json.loads((gt/'protected_sha256.json').read_text())
    except (OSError,ValueError) as e:raise TrustedEvidenceError('required private contract/oracle unavailable') from e
    if binding.get('weights')!=WEIGHTS or not binding.get('private_sha256'):raise TrustedEvidenceError('trusted weights/hash bindings invalid')
    for name,h in binding['private_sha256'].items():
        if name=='scoring_contract.json' or name.startswith('/') or '\\' in name or any(x in ('','.','..') for x in name.split('/')):raise TrustedEvidenceError('unsafe private binding')
        p=safe(gt,name)
        if p is None or sha(p)!=h:raise TrustedEvidenceError('private material missing/drift: '+name)
    if sys.version_info<(3,11):raise TrustedEvidenceError('trusted Python3.11+ runtime required')
    for name in ('asyncio','unittest','subprocess','collections'):
        try:__import__(name)
        except ImportError as e:raise TrustedEvidenceError('trusted standard-library dependency missing: '+name) from e
    opportunities=expected.get('opportunities');ids=[x['id'] for x in opportunities] if isinstance(opportunities,list) else []
    if len(ids)!=10 or len(set(ids))!=10 or sum(x['owner']=='business_correctness' for x in opportunities)!=5 or sum(x['owner']=='boundary_cases' for x in opportunities)!=5:raise TrustedEvidenceError('independent opportunity baseline invalid')
    envdir=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not envdir or Path(envdir).is_symlink():raise TrustedEvidenceError('managed derived context absent')
    evidence=Path(envdir).resolve()
    if any(evidence==p or evidence in p.parents or p in evidence.parents for p in (root,gt)):raise TrustedEvidenceError('derived context overlaps inputs')
    evidence.mkdir(parents=True,exist_ok=True);target=evidence/'rule-observations.json'
    if target.exists():raise TrustedEvidenceError('fresh derived context required')
    # Compile only trusted helpers before candidate import: missing/corrupt test
    # infrastructure cannot become an implementation zero.
    for name in ('hidden_tests/run_oracle.py','hidden_tests/test_lifecycle.py','trusted_project/__init__.py','trusted_project/resources.py'):
        try:compile((gt/name).read_bytes(),str(gt/name),'exec')
        except (OSError,SyntaxError) as e:raise TrustedEvidenceError('trusted test/helper invalid: '+name) from e
    source=safe(root,'project/worker.py');source_hash=sha(source) if source else None
    actual=None;execution={'stage':'candidate_source_missing_or_unsafe','source_sha256':source_hash,'command':None,'returncode':None,'tests_attempted':0};rows={};copy_hash=None
    if source:
        if source.stat().st_size>4_000_000:raise TrustedEvidenceError('NEEDS_SOURCE_REVIEW: legal source exceeds bounded execution input')
        program=evidence/'program';(program/'project').mkdir(parents=True,exist_ok=False)
        for n in ('__init__.py','resources.py'):shutil.copyfile(gt/'trusted_project'/n,program/'project'/n)
        shutil.copyfile(source,program/'project/worker.py');assert sha(program/'project/worker.py')==source_hash
        results=evidence/'test-results.json';command=[sys.executable,'-I','-B',str(gt/'hidden_tests/run_oracle.py'),'--program',str(program),'--output',str(results)]
        child_env={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','TMPDIR','TMP','TEMP','LANG','LC_ALL')};child_env['PYTHONDONTWRITEBYTECODE']='1'
        try:completed=subprocess.run(command,cwd=program,env=child_env,capture_output=True,timeout=60)
        except subprocess.TimeoutExpired as e:
            (evidence/'tests.stdout.log').write_bytes(e.stdout or b'');(evidence/'tests.stderr.log').write_bytes(e.stderr or b'');write(evidence/'execution-pending.json',{'source_sha256':source_hash,'command':command,'timeout_seconds':60,'actual_timeout':True,'tests_not_fabricated':'Results unavailable or partial; no fake passes or ability zero','stdout_sha256':sha(evidence/'tests.stdout.log'),'stderr_sha256':sha(evidence/'tests.stderr.log')})
            raise TrustedEvidenceError('NEEDS_EXECUTION_REVIEW: supervised candidate process exceeded liveness protection; no fabricated unexecuted results') from e
        (evidence/'tests.stdout.log').write_bytes(completed.stdout);(evidence/'tests.stderr.log').write_bytes(completed.stderr)
        if not results.is_file():raise TrustedEvidenceError('independent runner produced no structured receipt; inspect actual command/returncode')
        try:actual=json.loads(results.read_text())
        except (ValueError,UnicodeError) as e:raise TrustedEvidenceError('independent execution receipt invalid') from e
        copy_hash=sha(program/'project/worker.py')
        if actual.get('schema_version')!='h043-independent-execution/v1' or actual.get('source_sha256')!=source_hash or actual.get('source_after_sha256')!=copy_hash:raise TrustedEvidenceError('execution source binding mismatch')
        tests_hash={n:sha(gt/'hidden_tests'/n) for n in ('run_oracle.py','test_lifecycle.py')}
        if actual.get('test_files_sha256')!=tests_hash:raise TrustedEvidenceError('execution test binding mismatch')
        cases=actual.get('cases',[])
        if actual.get('tests_attempted')!=10 or {x.get('id') for x in cases}!=set(ids) or len(cases)!=10:raise TrustedEvidenceError('independent runner case inventory missing; no fabricated results')
        if completed.returncode not in (0,1) or (completed.returncode==0)!=bool(actual.get('passed')):raise TrustedEvidenceError('runner returncode/result mismatch')
        rows={x['id']:x for x in cases}
        execution={'stage':'actual_candidate_execution','source_sha256':source_hash,'source_copy_after_sha256':copy_hash,'source_copy_unchanged':copy_hash==source_hash,'trusted_test_sha256':tests_hash,'command':command,'cwd':str(program),'returncode':completed.returncode,'stdout_sha256':sha(evidence/'tests.stdout.log'),'stderr_sha256':sha(evidence/'tests.stderr.log'),'structured_results_sha256':sha(results),'tests_attempted':actual['tests_attempted'],'scenario_executed_count':sum(bool(x.get('scenario_executed')) for x in cases),'scope':'Actual tests, never candidate self-report or patch text matching.'}
        # A candidate may fail; the trusted test bytes must not drift.
        for name,h in binding['private_sha256'].items():
            if sha(gt/name)!=h:raise TrustedEvidenceError('trusted material drift during execution: '+name)
    input_checks={name:bool(safe(root,name) and sha(root/name)==h) for name,h in protected.items()}
    allowed=set(protected)|{'project/worker.py'};unauthorized=[]
    for p in root.rglob('*'):
        rel=p.relative_to(root)
        if 'gt'==rel.parts[0] or 'results'==rel.parts[0] or '__pycache__' in rel.parts or p.suffix=='.pyc':continue
        if p.is_file() and rel.as_posix() not in allowed:unauthorized.append(rel.as_posix())
    reports={n:read_report(safe(root,'results/'+n)) for n in ('tests.txt','lifecycle.md')};readability={n:isinstance(text,str) and bool(text.strip()) for n,text in reports.items()}
    current_report_binding=bool(source_hash and readability['tests.txt'] and re.search(r'(?<![0-9a-f])'+source_hash+r'(?![0-9a-f])',reports['tests.txt'].lower()))
    scores={owner:mean(float(bool(rows.get(x['id'],{}).get('passed'))) for x in opportunities if x['owner']==owner) for owner in ('business_correctness','boundary_cases')}
    protection=.8*mean(input_checks.values())+.2*float(not unauthorized)
    scores['delivery_integrity']=.7*protection+.3*mean(readability.values())
    independent_binding=actual is not None and copy_hash==source_hash
    scores['evidence_binding']=.5*float(independent_binding)+.5*float(current_report_binding)
    scores['overall_score']=sum(scores[k]*w for k,w in WEIGHTS.items())
    observations={'schema_version':'h043-rule-observations/v1','status':'ACTUAL_INDEPENDENT_EXECUTION_COMPLETED' if actual else 'CANDIDATE_PRIMARY_SOURCE_UNAVAILABLE','reviewer_kind':'model','human_expert':False,'scores':scores,'owner_denominators':{'business_correctness':5,'boundary_cases':5},'case_scores':{x['id']:{'owner':x['owner'],'score':float(bool(rows.get(x['id'],{}).get('passed'))),'observed':rows.get(x['id']),'not_executed_reason':None if x['id'] in rows else 'candidate primary source absent/unsafe'} for x in opportunities},'execution':execution,'input_checks':input_checks,'unauthorized_new_files':unauthorized,'report_readability':readability,'current_candidate_report_hash_binding':current_report_binding,'independent_execution_binding':independent_binding,'protected_inputs_do_not_gate_business_tests':True,'private_contract_sha256':sha(gt/'scoring_contract.json'),'source_first_expected_sha256':sha(gt/'expected.json'),'source_copy_notes':'Only worker.py is delivered code in this execution copy; __init__/resources come from trusted originals. Names and internals are free.','actual_candidate_Harness_execution':False,'Judge_or_hybrid_score':None,'limits':['Observed in-memory contract scenarios only; not proof of all interleavings, real services, performance, or Harness availability.','Report readability and source binding are mechanical; prose semantic quality is not independently scored.']}
    write(target,observations);return scores
