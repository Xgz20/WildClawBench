"""H011: independent source corrections, native propagation and a bound impact ledger."""
from pathlib import Path
import hashlib,json,os,runpy
def private(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def grade(root):
    root=Path(root).resolve();gt=root/'gt'
    truth=private(gt/'expected.json');oracle=private(gt/'business_oracle.json');contract=private(gt/'artifact_contract.json')
    protected=private(gt/'protected_sha256.json');verification=private(gt/'source_verification.json')
    counterexamples=private(gt/'counterexamples.json');evidence=private(gt/'evidence_requirements.json')
    if (truth['status']!='native_sources_verified_before_reference' or verification['status']!='pass'
        or protected!=truth['source_sha256'] or verification['source_files']!=protected
        or hashlib.sha256((gt/'expected.json').read_bytes()).hexdigest()!=oracle['source_numeric_truth_sha256']
        or len(truth['source_nodes'])!=190 or len(truth['artifact_nodes'])!=92 or len(oracle['all_affected_nodes'])!=143
        or not counterexamples['boundaries'] or not evidence['required_observations']):raise ValueError('H011 private contracts disagree')
    for name,digest in contract['private_helper_sha256'].items():
        if hashlib.sha256((gt/name).read_bytes()).hexdigest()!=digest:raise ValueError('H011 private helper drift: '+name)
    io=runpy.run_path(str(gt/'common_io.py'));workbook=runpy.run_path(str(gt/'workbook_checks.py'))
    documents=runpy.run_path(str(gt/'document_checks.py'));impact=runpy.run_path(str(gt/'impact_checks.py'));render=runpy.run_path(str(gt/'render_checks.py'))
    if not all(os.environ.get(k) for k in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']):
        raise RuntimeError('H011 requires managed Office and explicit dual-format render locks')
    lock=private(os.environ['GENERAL_E2E_OFFICE_LOCK']);render_lock=private(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']);office=io['OFFICE']
    office['validate_office_lock'](lock);office['validate_office_render_lock'](render_lock)
    if office['office_render_lock_formats'](render_lock)!=('docx','pptx') or render_lock['office_runtime']!=lock:raise RuntimeError('H011 requires matching both-format lock')
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('derived evidence must be outside frozen Workspace')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and io['sha'](root/name)==digest for name,digest in protected.items())
    errors={};objects={};wb=None;word=None;ppt=None;records=[];ledger={};probes={'cases':[],'score':0.};renders={};recalculation=None
    def candidate_step(name,action):
        try:return action()
        except io['CandidateError'] as e:errors[name]=str(e);return None
        except office['OfficeRuntimeError'] as e:
            if e.code not in io['CONTENT_ERRORS']:raise
            errors[name]=e.code;return None
    def read_workbook():
        nonlocal recalculation
        path=root/contract['files']['workbook'];original=io['workbook'](path)
        recalculation=office['recalculate_xlsx'](path,lock,derived/'baseline-workbook')
        return workbook['baseline'](original,io['workbook'](recalculation['path']),truth,contract,io)
    wb=candidate_step('workbook',read_workbook);objects['workbook']=wb is not None
    if wb:
        probes=candidate_step('input_responses',lambda:workbook['responses'](root/contract['files']['workbook'],lock,derived/'input-responses',wb,truth,contract,io)) or {'cases':[],'score':0.}
    word_model=candidate_step('word',lambda:io['word'](root/contract['files']['word']))
    if word_model:
        word=documents['word_checks'](word_model,truth,contract,io)
        renders['word']=candidate_step('word_render',lambda:render['render'](root/contract['files']['word'],render_lock,derived/'word-render',
            [p['text'] for p in word_model['paragraphs']]+[n['text'] for n in word_model['notes'].values()],'word',io))
    objects['word']=word_model is not None
    raw_records=candidate_step('slides',lambda:io['pptx'](root/contract['files']['slides']))
    if raw_records:
        hidden=[r['locator'] for r in raw_records if r.get('hidden')]
        records=[r for r in raw_records if not any(r['locator']==h or r['locator'].startswith(h+'/') for h in hidden)]
        ppt=candidate_step('slide_data',lambda:documents['ppt_checks'](root/contract['files']['slides'],records,truth,contract,io,lock,derived/'slides'))
        renders['slides']=candidate_step('slides_render',lambda:render['render'](root/contract['files']['slides'],render_lock,derived/'slides-render',
            [r['text'] for r in records if r.get('context') in {'slide','slide_table'} and r.get('text')],'slides',io))
    objects['slides']=ppt is not None
    ledger=candidate_step('impact_log',lambda:io['json_object'](root/contract['files']['impact_log']));objects['impact_log']=ledger is not None
    semantic,semantic_observed=documents['semantics'](word['paragraphs'] if word else {},records,truth,io)
    observations={**(wb['observations'] if wb else {}),**(word['observations'] if word else {}),**(ppt['observations'] if ppt else {}),**semantic_observed}
    for identity,node in semantic_observed.items():
        node['file']=contract['files']['word' if identity.startswith('word/') else 'slides']
        node['aliases']=[identity.split('/')[-1]] if '/paragraph/' in identity else ['P20'] if identity=='word/cash-direction' else []
    # Axis is a constrained native observation separate from prose direction heuristics.
    semantic['pptx/chart/CASH_QUARTER/axis']=bool(ppt and ppt['cash_axis_ok'])
    binding=impact['check_log'](ledger or {},truth,oracle,observations,contract,io)
    get=lambda identity:bool(wb and wb['checks'].get(identity))
    corrected_sources=io['mean'](get(e['source_node']) for e in truth['corrections'])
    formula_values=io['mean'](get(k) for k,n in truth['source_nodes'].items() if n['kind']=='formula')
    word_values=io['mean']((word['checks'].get(k,False) if word else False) for k in truth['artifact_nodes'] if k.startswith('word/'))
    slide_values=io['mean']((ppt['checks'].get(k,False) if ppt else False) for k in truth['artifact_nodes'] if k.startswith('pptx/'))
    correctness=.20*corrected_sources+.30*formula_values+.25*word_values+.25*slide_values
    preservation=io['mean']([io['mean'](get(k) for k in truth['protected_source_nodes']),
        io['mean'](wb['scope'].values()) if wb else 0.,io['mean'](wb['identities'].values()) if wb else 0.,
        io['mean'](word['protection'].values()) if word else 0.,io['mean'](ppt['protection'].values()) if ppt else 0.])
    links=io['mean'](word['links'].values()) if word else 0.;editable=io['mean'](ppt['chart_integrity'].values()) if ppt else 0.
    boundaries=.45*probes['score']+.20*preservation+.10*links+.15*editable+.10*io['mean'](semantic.values())
    native_formulas=io['mean'](wb['formula_presence'].values()) if wb else 0.
    render_fit=io['mean'](bool(renders.get(k) and renders[k]['basic_fit']) for k in ['word','slides'])
    delivery=.25*io['mean'](objects.values())+.25*io['mean']([native_formulas,editable])+.35*render_fit+.15*intact
    scores={'business_correctness':correctness,'boundary_cases':boundaries*intact,'delivery_integrity':delivery*intact,'evidence_binding':binding['score']*intact}
    if not any(objects.values()):scores={k:0. for k in scores}
    scores['overall_score']=sum(scores[k]*weight for k,weight in oracle['checkpoint_weights'].items())
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H011 score out of range')
    report={'schema_version':'h011-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'parsed_outputs':objects,
        'numeric_groups':{'approved_source_values':corrected_sources,'formula_values':formula_values,'word_values':word_values,'slide_values':slide_values},
        'workbook':wb,'word':word,'slides':ppt,'semantic_observables':semantic,'native_observations':observations,'input_responses':probes,
        'impact_binding':binding,'renders':renders,'baseline_recalculation':recalculation,
        'limit':'Author rule observations are not hybrid semantic scores. Independent Judge must assess full prose direction, unsupported claims, protected meaning and actual visual usability.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h011-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2,default=str);f.write('\n')
    return scores
