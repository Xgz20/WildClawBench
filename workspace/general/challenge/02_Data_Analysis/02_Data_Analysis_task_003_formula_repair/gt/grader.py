"""Deterministic formula-repair checks with independent GT and actual Office probes."""
from pathlib import Path
import hashlib,json,os,runpy

def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt';load=lambda n:json.loads((gt/n).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    contract=load('scoring_contract.json')
    for name,digest in contract['private_sha256'].items():
        if sha(gt/name)!=digest:raise ValueError('H019 private helper/contract drift: '+name)
    expected=load('expected.json');template=load('template_snapshot.json');protected=load('protected_sha256.json');runtime=load('runtime_contract.json')
    if expected['status']!='independent_native_two_path_verified' or len(expected['records'])!=12 or len(expected['scenarios'])!=6 or runtime['grading_type']!='automated':raise ValueError('H019 invalid private oracle/runtime')
    io=runpy.run_path(str(gt/'leave_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'))
    for n in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(n):raise RuntimeError('H019 missing managed runtime '+n)
    load_path=Path(os.environ['GENERAL_E2E_OFFICE_LOCK']);lock=json.loads(load_path.read_text());office['validate_office_lock'](lock)
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H019 derived artifacts must be outside frozen Workspace')
    intact=all((root/n).is_file() and not (root/n).is_symlink() and sha(root/n)==v for n,v in protected.items());errors={};current=None;baseline=None;recalculation=None;responses=[];scope={};text='';formulas={};report=io['report']('',template,None,expected)
    def candidate(name):
        p=root/'results'/name
        if not p.is_file() or p.is_symlink() or p.stat().st_size>5*1024*1024 or not p.stat().st_size:raise io['CandidateError']('missing, empty or oversized '+name)
        return p
    def attempt(label,action):
        try:return action()
        except (io['CandidateError'],UnicodeError) as error:
            # Private contracts were checked before this boundary; only candidate parsing occurs here.
            errors[label]=str(error);return None
        except office['OfficeRuntimeError'] as error:
            if error.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[label]=error.code;return None
    def book():
        nonlocal recalculation,baseline
        p=candidate('leave_model_repaired.xlsx');office['_clean_package'](p.read_bytes());obj=io['snapshot'](p)
        recalculation=office['recalculate_xlsx'](p,lock,derived/'baseline',timeout_seconds=90);baseline=io['values'](recalculation['path'],expected['scenarios'][0]);return obj
    current=attempt('workbook',book)
    def read_report():
        return candidate('formula_changes.md').read_text(encoding='utf-8-sig')
    text=attempt('report',read_report)
    if text is not None:report=io['report'](text,template,current,expected)
    if current is not None:
        scope=io['preservation'](current,template);leave=next((s for s in current['sheets'] if s['name']=='Leave'),{'cells':{}})
        for r in range(6,18):
            for col in 'EFGH':formulas[col+str(r)]=leave['cells'].get(col+str(r),{}).get('formula') is not None
        if baseline['complete'] and all(formulas.values()) and all(scope.values()) and baseline['visible']:
            for spec in expected['scenarios'][1:]:
                p=candidate('leave_model_repaired.xlsx');prepared=office['prepare_xlsx_counterfactual'](p,spec['changes'],derived/spec['name']/'prepared');office['verify_xlsx_counterfactual'](p,prepared['path'],prepared['audit'])
                result=office['recalculate_xlsx'](prepared['path'],lock,derived/spec['name']/'calculated',timeout_seconds=90);observed=io['values'](result['path'],spec)
                by_id={r['employee_id']:r for r in expected['scenarios'][0]['expected']};affected=[]
                for row in spec['expected']:
                    for key in ['complete_years','base_days','entitled_days','status']:
                        if not io['equal'](row[key],by_id[row['employee_id']][key],1e-9):affected.append(row['employee_id']+'/'+key)
                if not io['equal'](spec['total_days'],expected['scenarios'][0]['total_days'],1e-9):affected.append('total_days')
                if not affected:raise ValueError('H019 private probe has no changed business outputs')
                unchanged=[v for k,v in observed['checks'].items() if k not in affected]
                changed_score=sum(observed['checks'][k] for k in affected)/len(affected)
                response=changed_score*all(unchanged)
                responses.append({'name':spec['name'],'prepared':prepared,'recalculation':result,'observations':observed,'affected_keys':affected,'unaffected_correct':all(unchanged),'response_score':response})
    mean=lambda items:sum(items)/len(items) if items else 0.
    formula_score=mean(list(formulas.values()));response_score=mean([r['response_score'] for r in responses]) if len(responses)==5 else 0.
    scores={'business_correctness':.65*(baseline['score'] if baseline else 0.)+.2*formula_score+.15*report['facts_score'],'boundary_cases':response_score*intact,'delivery_integrity':0.,'evidence_binding':report['binding_score']*intact}
    preserve=bool(scope and all(scope.values()));cap=None
    if not intact or not preserve or not baseline or not baseline['visible']:
        scores['business_correctness']=min(scores['business_correctness'],.5);cap='source/scope/visibility preservation violation';scores['boundary_cases']=0.
    if len(responses)==5 and response_score==0.:
        scores['business_correctness']=min(scores['business_correctness'],.5);cap='no changed business result responds correctly to any of the five probes'
    scores['delivery_integrity']=float(current is not None and text is not None and preserve and intact and all(formulas.values()) and baseline['complete'] and baseline['visible'] and response_score==1. and report['complete'])
    scores={k:round(v,12) for k,v in scores.items()};scores['overall_score']=round(sum(scores[k]*w for k,w in contract['checkpoint_weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H019 score out of bounds')
    result={'schema_version':'h019-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'scope_checks':scope,'formula_cells':formulas,'baseline':baseline,'office_baseline':recalculation,'responses':responses,'report':report,'business_cap_reason':cap,'limit':'Bounded automated native data, formula dependence, template preservation and report-source binding only. No human expert, full visual/semantic Judge or real Harness run; L3 is unvalidated design estimate.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h019-analysis.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    return scores
