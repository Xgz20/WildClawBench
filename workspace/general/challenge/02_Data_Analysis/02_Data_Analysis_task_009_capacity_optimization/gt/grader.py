"""Recompute any integer plan against frozen source capacities and optimum bounds."""
from pathlib import Path
import hashlib,json,os,runpy
def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt';load=lambda n:json.loads((gt/n).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();mean=lambda xs:sum(xs)/len(xs) if xs else 0.
    contract=load('scoring_contract.json')
    if sha(gt/'grader.py')!=contract['grading_source_sha256']:raise ValueError('H025 grader source drift')
    for name,want in contract['private_sha256'].items():
        if sha(gt/name)!=want:raise ValueError('H025 private scoring drift '+name)
    data=load('source_records.json');oracle=load('expected.json');protected=load('protected_sha256.json')
    if len(data['routes'])!=36 or sum(len(data[k]) for k in ['demand','plants','routes','materials','recipes','costs'])!=113:raise ValueError('H025 incomplete source oracle')
    io=runpy.run_path(str(gt/'allocation_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));evaluate=runpy.run_path(str(gt/'feasibility.py'))['evaluate']
    for key in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(key):raise RuntimeError('H025 missing managed runtime '+key)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());office['validate_office_lock'](lock);derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H025 derived evidence must be outside frozen Workspace')
    intact=all((root/name).is_file() and not(root/name).is_symlink() and sha(root/name)==value for name,value in protected.items())
    errors={};native=None;inventory=None;evaluation=None;observation=None;decision=None;cap=None;priority_scores=[];cost_score=0.
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
    def model():
        nonlocal native,inventory,evaluation
        path=candidate('allocation.xlsx');office['_clean_package'](path.read_bytes());native=office['recalculate_xlsx'](path,lock,derived/'baseline',timeout_seconds=120);book=io['read_book'](native['path'])
        if any(e['error'] in {'#NAME?','#SPILL!','#CALC!'} for sheet in book for e in sheet['errors']):raise RuntimeError('H025 formula compatibility requires manual review; no ability zero')
        quantities=io['quantities'](book,data);evaluation=evaluate(data,quantities);inventory=io['raw_inventory'](book,data)
        if evaluation['feasible'] and tuple(evaluation['objective'])<tuple(oracle['optimal_objective']):raise ValueError('H025 feasible candidate improves frozen optimum: oracle contradiction requires review, never candidate zero')
        return io['observe'](book,evaluation,data)
    observation=attempt('allocation',model)
    if evaluation is not None:decision=attempt('decision',lambda:io['read_decision'](candidate('decision.md'),evaluation,data))
    else:attempt('decision_presence',lambda:candidate('decision.md'))
    if evaluation:
        gap=evaluation['objective'][:3];best=oracle['optimal_gap_vector'];prior_equal=True
        for i in range(3):
            demand=sum(r['demand_units'] for r in data['demand'] if r['priority']==i+1);denominator=max(demand-best[i],1);score=max(0.,min(1.,1-max(gap[i]-best[i],0)/denominator)) if prior_equal else 0.;priority_scores.append(score);prior_equal=prior_equal and gap[i]==best[i]
        if gap==best:
            budget=runpy.run_path(str(gt/'feasibility.py'))['cents'](data['budget']);span=max(budget-oracle['optimal_total_cents'],1);cost_score=max(0.,min(1.,1-max(evaluation['controls']['total_cents']-oracle['optimal_total_cents'],0)/span))
    priority=sum(score*w for score,w in zip(priority_scores,[.5,.3,.2]))
    b=observation['scores'] if observation else {};accounting=.35*b.get('allocations',0)+.25*b.get('products',0)+.15*b.get('plant_results',0)+.10*b.get('material_results',0)+.15*b.get('controls',0)
    business=.65*priority+.20*cost_score+.15*accounting
    feasible=bool(evaluation and evaluation['feasible']);certificate=decision['certificate_score'] if decision else 0.;boundary=.6*float(feasible)+.4*certificate
    if not feasible:business=min(business,.25);cap='no complete feasible integer plan'
    if not intact or not inventory or not inventory['complete']:
        business=min(business,.5);boundary=0.;cap='protected input changed or incomplete preserved raw source records'
    integrity=float(intact and feasible and inventory is not None and inventory['complete'] and observation is not None and observation['complete'] and decision is not None and decision['complete'])
    binding=(.4*float(inventory is not None and inventory['complete'])+.3*(decision['report_score'] if decision else 0)+.3*float(decision is not None and decision['certificate_score']==1 and decision['sources_named']))*intact
    scores={k:round(v,12) for k,v in {'business_correctness':business,'boundary_cases':boundary*intact,'delivery_integrity':integrity,'evidence_binding':binding}.items()};scores['overall_score']=round(sum(scores[k]*w for k,w in contract['weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H025 score range')
    report={'schema_version':'h025-integer-allocation-rule/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'office_baseline':native,'raw_inventory':inventory,'actual_plan':evaluation,'observation':observation,'decision':decision,'priority_scores':priority_scores,'conditional_cost_score':cost_score,'accounting_score':accounting,'business_cap_reason':cap,'reference_matrix_consumed':False,'candidate_formula_model_required':False,'limit':'Exact source constraints, strict-priority and conditional cost gap, visible self-accounting and one source impossibility certificate. Not expert review, unrestricted prose/solver claims, full visual score or real Harness performance.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h025-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    return scores
