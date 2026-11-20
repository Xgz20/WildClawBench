from pathlib import Path
import hashlib, json, os, subprocess, sys
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
EDITABLE=('project/api.py','project/store.ts','project/view.ts')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def equal(a,b):
    # Contract objects may contain harmless extra fields; arrays are exact ordered obligations.
    if isinstance(b,bool) or b is None:return type(a)==type(b) and a==b
    if isinstance(b,(int,float)):return isinstance(a,(int,float)) and not isinstance(a,bool) and a==b
    if isinstance(b,dict):return isinstance(a,dict) and all(k in a and equal(a[k],v) for k,v in b.items())
    if isinstance(b,list):return isinstance(a,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return isinstance(a,type(b)) and a==b

def grade(**kwargs):
    root=Path(kwargs.get('workspace_path') or '/tmp_workspace');gt=root/'gt'
    path=gt/'trusted_files.json'
    if not path.is_file() or path.is_symlink():raise RuntimeError('H050_TRUSTED_CONTEXT_MISSING_OR_DRIFT: trusted_files.json')
    for rel,digest in read(path).items():
        p=gt/rel
        if not p.is_file() or p.is_symlink() or sha(p)!=digest:raise RuntimeError('H050_TRUSTED_CONTEXT_MISSING_OR_DRIFT: '+rel)
    runtime=read(gt/'runtime_contract.json');node=Path(runtime['node']['path'])
    if not node.is_file() or sha(node)!=runtime['node']['sha256']:raise RuntimeError('H050_NODE_RUNTIME_UNAVAILABLE_OR_DRIFT_UNASSESSED')
    context=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not context:raise RuntimeError('H050_RULE_EVIDENCE_CONTEXT_REQUIRED')
    derived=Path(context)/'actual-replay';derived.mkdir(parents=True,exist_ok=False)
    def safe(p):return p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
    captured=derived/'captured';(captured/'project').mkdir(parents=True)
    sources={}
    for rel in EDITABLE:
        p=root/rel;raw=p.read_bytes() if safe(p) else b''
        (captured/rel).write_bytes(raw);sources[rel]=hashlib.sha256(raw).hexdigest()
    original=gt/'source_originals';cases=read(gt/'unit_cases.json');expected=read(gt/'expected.json')
    if len(cases)!=len(expected) or len({c['case_id'] for c in cases})!=len(cases):raise RuntimeError('H050_TRUSTED_CASE_ID_COLLISION')
    request={'units':cases,'fixture':read(original/'fixtures/records.json'),'scenarios':read(original/'fixtures/public_scenarios.json'),
             'fixture_sha256':sha(original/'fixtures/records.json'),'scenarios_sha256':sha(original/'fixtures/public_scenarios.json')}
    request_path=derived/'request.json';response_path=derived/'response.json';request_path.write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n')
    command=[str(node),'--experimental-vm-modules','--disable-warning=ExperimentalWarning',str(original/'engine.mjs'),str(captured),str(request_path),str(response_path),sys.executable]
    invocation={'argv':command,'cwd':str(derived),'timeout_seconds':runtime['child_timeout_seconds'],'OS_sandbox_claimed':False,'actual_worker_python':sys.version,'unit_truth_sha256':sha(gt/'expected.json')}
    (derived/'invocation.json').write_text(json.dumps(invocation,indent=2)+'\n')
    try:r=subprocess.run(command,cwd=derived,capture_output=True,text=True,encoding='utf-8',timeout=runtime['child_timeout_seconds'],env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR','PYTHONUTF8'}})
    except subprocess.TimeoutExpired as exc:
        (derived/'incomplete.json').write_text(json.dumps({'status':'unassessed_infrastructure_timeout','candidate_zero':False})+'\n')
        raise RuntimeError('H050_REPLAY_TIMEOUT_UNASSESSED_NO_CANDIDATE_ZERO') from exc
    (derived/'stdout.log').write_text(r.stdout);(derived/'stderr.log').write_text(r.stderr)
    if r.returncode or not response_path.is_file():raise RuntimeError('H050_REPLAY_INFRASTRUCTURE_FAILED_UNASSESSED: '+str(r.returncode))
    replay=read(response_path)
    if replay.get('unassessed'):raise RuntimeError('H050_PROFILE_OR_REPLAY_UNASSESSED_NO_CANDIDATE_ZERO: '+json.dumps(replay.get('infrastructure') or [x for x in replay.get('units',[]) + replay.get('scenarios',[]) if x['status'] in ('unassessed','profile_unsupported')],ensure_ascii=False))
    if replay.get('sources_sha256')!=sources:raise RuntimeError('H050_REPLAY_BINDING_INVALID')
    actual={x['case_id']:x for x in replay['units']}
    if set(actual)!=set(expected) or len(actual)!=len(replay['units']):raise RuntimeError('H050_REPLAY_UNITS_INCOMPLETE_UNASSESSED')
    observations=[]
    for c in cases:
        a=actual[c['case_id']];ok=a['status']=='completed' and a.get('inputs_unchanged') is True and equal(a.get('output'),expected[c['case_id']])
        observations.append({'case_id':c['case_id'],'kind':c['kind'],'group':c['group'],'status':a['status'],'correct':ok})
    scores={key:sum(x['correct'] for x in observations if x['group']==group)/sum(x['group']==group for x in observations) for key,group in [('business_correctness','business'),('boundary_cases','boundary')]}
    protected=read(gt/'protected_sha256.json');observed={}
    for p in root.rglob('*'):
        rel=p.relative_to(root).as_posix()
        if rel.split('/')[0] in {'gt','results'} or rel in EDITABLE:continue
        if p.is_symlink():observed[rel]='SYMLINK'
        elif p.is_file():observed[rel]=sha(p)
    protected_ok=observed==protected
    report=None
    try:
        p=root/'results/scenarios.json'
        if safe(p):
            v=read(p)
            if isinstance(v,dict):report=v
    except (ValueError,OSError,UnicodeError):pass
    scores['delivery_integrity']=.8*float(protected_ok)+.2*float(report is not None)
    report=report or {};checks=[]
    def hx(a,b):return isinstance(a,str) and a.lower()==b
    checks += [report.get('schema_version')==replay['schema_version'],report.get('profile')==replay['profile']]
    reported_sources=report.get('sources_sha256') if isinstance(report.get('sources_sha256'),dict) else {}
    checks += [hx(reported_sources.get(k),v) for k,v in sources.items()]
    for k in ('engine_sha256','api_probe_sha256','profile_sha256','fixture_sha256','scenarios_sha256'):checks.append(hx(report.get(k),replay[k]))
    reported_node=report.get('node') if isinstance(report.get('node'),dict) else {}
    checks.extend([reported_node.get('version')==replay['node']['version'],hx(reported_node.get('sha256'),replay['node']['sha256'])])
    rows=report.get('scenarios') if isinstance(report.get('scenarios'),list) else []
    factual=[]
    for wanted in replay['scenarios']:
        selected=[x for x in rows if isinstance(x,dict) and x.get('case_id')==wanted['case_id']]
        factual.append(len(selected)==1 and equal(selected[0],wanted))
    scores['evidence_binding']=.4*sum(checks)/len(checks)+.6*sum(factual)/len(factual)
    scores['overall_score']=sum(scores[k]*w for k,w in WEIGHTS.items())
    summary={'schema_version':'h050-rule-observations/v1','scores':scores,'source_sha256':sources,'units':observations,'protected_inputs_intact':protected_ok,'report_binding_checks':checks,'fixed_public_scenario_factual_checks':factual,'composed_scenario_status':[x['status'] for x in replay['scenarios']],
             'scope':'actual pure Python and synchronous TS function replay; no real browser/DOM/Harness/Judge/human-expert claim','no_duplicate_downstream_scoring':'API,Store-with-oracle-responses,View-with-source-snapshots are disjoint; composed replay is evidence only','elapsed_not_capability_gate':True}
    (derived/'scoring-observations.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'h050_actual_scores':scores,'failed_unit_ids':[x['case_id'] for x in observations if not x['correct']],'factual_report':factual}))
    return scores
