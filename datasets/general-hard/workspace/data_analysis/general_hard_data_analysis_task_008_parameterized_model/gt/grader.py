"""Source-first salary, marginal commission, cumulative-refund and live-case checks."""
from pathlib import Path
import hashlib,json,os,re,runpy
def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt';load=lambda n:json.loads((gt/n).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();mean=lambda xs:sum(xs)/len(xs) if xs else 0.
    contract=load('scoring_contract.json')
    if sha(gt/'grader.py')!=contract['grading_source_sha256']:raise ValueError('H024 grader source drift')
    for name,want in contract['private_sha256'].items():
        if sha(gt/name)!=want:raise ValueError('H024 private scoring drift '+name)
    expected=load('expected.json');records=load('source_records.json');protected=load('protected_sha256.json')
    if set(expected['scenarios'])!={'1','2','3'} or len(expected['comparisons'])!=9 or sum(len(records[k]) for k in ['employees','attendance','sales','refunds'])!=192:raise ValueError('H024 incomplete private oracle')
    probes=[('growth_september_cap',2,'2026-09','commission_cap',2100),('guardrail_september_zero_cap',3,'2026-09','commission_cap',0),('base_july_rate',1,'2026-07','rate1',.02)]
    variants={name:load('scenarios/'+name+'/expected.json') for name,*_ in probes}
    io=runpy.run_path(str(gt/'model_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'))
    for key in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(key):raise RuntimeError('H024 missing managed runtime '+key)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());office['validate_office_lock'](lock)
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H024 derived evidence must be outside frozen Workspace')
    intact=all((root/name).is_file() and not(root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    errors={};inventory=None;native=None;baseline=None;validation=None;responses=[];cap=None
    def candidate(name):
        p=root/'results'/name
        if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=5*1024*1024:raise io['CandidateError']('missing, empty or oversized '+name)
        return p
    def attempt(label,action):
        try:return action()
        except (io['CandidateError'],UnicodeError) as exc:errors[label]=str(exc);return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[label]=exc.code;return None
    def read_baseline():
        nonlocal inventory,native
        source=candidate('compensation_model.xlsx');office['_clean_package'](source.read_bytes());inventory=io['raw_inventory'](source,records)
        native=office['recalculate_xlsx'](source,lock,derived/'baseline',timeout_seconds=120)
        return io['observe'](native['path'],expected,1)
    baseline=attempt('model',read_baseline)
    if baseline is not None:
        validation=attempt('validation',lambda:io['read_validation'](candidate('validation.md'),expected,variants,candidate('compensation_model.xlsx'),records))
    else:attempt('validation_presence',lambda:candidate('validation.md'))
    if baseline is not None and intact:
        source=candidate('compensation_model.xlsx');selectors=io['selector_targets'](source)
        if len(selectors)>8:raise RuntimeError('H024 more than eight equivalent native selectors require manual binding; no ability zero')
        cases=[('selector_2',2,None,None,None,expected),('selector_3',3,None,None,None,expected)]+[(name,sid,month,field,value,variants[name]) for name,sid,month,field,value in probes]
        for name,sid,month,field,value,want in cases:
            targets=io['parameter_targets'](source,records,sid,month,field) if field else [None]
            if len(targets)>8:raise RuntimeError('H024 more than eight equivalent literal parameter copies require manual binding; no ability zero')
            truth=io['truth_map'](want,sid);prior=io['truth_map'](expected,sid if field else 1)
            affected=[key for key,v in truth.items() if key not in prior or v!=prior[key]]
            numeric=[key for key in affected if key.rsplit('/',1)[-1] in set(io['METRICS'])|{'commission_before','commission_after','current_clawback','commission_raw'}]
            if not affected or not numeric:raise ValueError('H024 inert source-level probe '+name)
            trials=[]
            for selector_index,selector in enumerate(selectors):
                for target_index,target in enumerate(targets):
                    edits=[{k:selector[k] for k in ['sheet','cell']}|{'value':sid}]
                    if target:edits.append({k:target[k] for k in ['sheet','cell']}|{'value':value})
                    folder=derived/name/str(selector_index)/str(target_index);prepared=office['prepare_xlsx_counterfactual'](source,edits,folder/'prepared');office['verify_xlsx_counterfactual'](source,prepared['path'],prepared['audit'])
                    calc=office['recalculate_xlsx'](prepared['path'],lock,folder/'calculated',timeout_seconds=120);obs=io['observe'](calc['path'],want,sid);checks=obs['checks']
                    changed=mean([checks.get(key,False) for key in affected]);numeric_score=mean([checks.get(key,False) for key in numeric]);unaffected=all(v for key,v in checks.items() if key not in affected)
                    trials.append({'selector':selector,'parameter':target,'prepared':prepared,'recalculation':calc,'observation':obs,'changed_score':changed,'numeric_response':numeric_score,'unaffected_correct':unaffected,'score':changed*unaffected})
            best=max(trials,key=lambda t:t['score']) if trials else None
            responses.append({'name':name,'scenario_id':sid,'affected_keys':affected,'numeric_keys':numeric,'trials':trials,'score':best['score'] if best else 0.,'numeric_response':best['numeric_response'] if best else 0.})
    b=baseline['scores'] if baseline else {};business=.45*b.get('payroll',0)+.35*b.get('retro',0)+.20*b.get('comparisons',0)
    focused=[]
    if baseline:
        # Tiers on both sides, half-cent monthly rounding, capped-origin refund,
        # later original-month recovery, zero attendance and negative salary.
        for key,v in baseline['checks'].items():
            if key.startswith('payroll/') and any("'"+emp+"'" in key for emp in ['E01','E03','E04','E05','E06','E07','E09','E10','E12']):focused.append(v)
            elif key.startswith('retro/') and any("'"+emp+"'" in key for emp in ['E09','E10','E12']):focused.append(v)
    audit=io['audit_score'](inventory,expected) if inventory else 0.;response=mean([r['score'] for r in responses]) if len(responses)==5 else 0.
    boundary=.2*audit+.2*mean(focused)+.6*response
    if not baseline or not intact or not inventory or not inventory['complete']:
        business=min(business,.5);boundary=0.;cap='missing native baseline, changed protected source or incomplete visible literal source/parameters'
    elif not any(r['numeric_response'] for r in responses if r['name'] in variants):
        business=min(business,.5);cap='no numerical business response to any of three actual native parameter changes'
    integrity=float(intact and inventory is not None and inventory['complete'] and baseline is not None and baseline['complete'] and validation is not None and validation['complete'] and response==1.)
    binding=(.6*(validation['score'] if validation else 0)+.4*float(inventory is not None and inventory['complete']))*intact
    scores={k:round(v,12) for k,v in {'business_correctness':business,'boundary_cases':boundary*intact,'delivery_integrity':integrity,'evidence_binding':binding}.items()}
    scores['overall_score']=round(sum(scores[k]*w for k,w in contract['weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H024 score range')
    report={'schema_version':'h024-native-compensation-rule/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'raw_inventory':{k:v for k,v in (inventory or {}).items() if k!='audit'},'baseline':baseline,'office_baseline':native,'validation':validation,'responses':responses,'business_cap_reason':cap,'source_audit_score':audit,'response_score':response,'limit':'Source-backed numerical, visible-table and native-input-response checks only; no payroll expert review, full visual quality, real Harness/model scores or measured difficulty.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h024-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    return scores
