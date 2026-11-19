"""H013 quote/constraint/handoff checks. Full recommendation meaning needs an independent Judge."""
from pathlib import Path
import hashlib,json,os,runpy,re
def private(p):return json.loads(Path(p).read_text())
def grade(root):
    root=Path(root).resolve();gt=root/'gt';truth=private(gt/'expected.json');oracle=private(gt/'business_oracle.json');contract=private(gt/'artifact_contract.json')
    protected=private(gt/'protected_sha256.json');verification=private(gt/'source_verification.json');index=private(gt/'evidence_index.json')['records']
    counter=private(gt/'counterexamples.json');requirements=private(gt/'evidence_requirements.json')
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    if (truth['status']!='native_sources_verified_before_reference' or sha(gt/'expected.json')!=oracle['expected_sha256']
        or truth['source_sha256']!=protected or verification['source_sha256']!=protected or truth['numeric_value_count']!=243
        or len(truth['cases'])!=9 or len(oracle['exceptions'])!=17 or not requirements['semantic_judge']
        or any(row['source_sha256']!=protected[row['file']] for row in index.values())):raise ValueError('H013 private contracts disagree')
    for name,digest in contract['private_helper_sha256'].items():
        if sha(gt/name)!=digest:raise ValueError('H013 private helper drift: '+name)
    io=runpy.run_path(str(gt/'artifact_io.py'));logic=runpy.run_path(str(gt/'business_checks.py'));model=runpy.run_path(str(gt/'business_model.py'));render_helper=runpy.run_path(str(gt/'render_checks.py'));office=io['OFFICE'];mean=io['mean']
    for k in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(k):raise RuntimeError('H013 managed scoring runtime missing: '+k)
    lock=private(os.environ['GENERAL_E2E_OFFICE_LOCK']);render_lock=private(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK'])
    office['validate_office_lock'](lock);office['validate_office_render_lock'](render_lock)
    if render_lock['office_runtime']!=lock or 'docx' not in office['office_render_lock_formats'](render_lock):raise RuntimeError('H013 requires matching Word render lock')
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H013 derived evidence must be outside frozen Workspace')
    intact=all((root/n).is_file() and not (root/n).is_symlink() and sha(root/n)==v for n,v in protected.items())
    errors={};objects={};book=None;original=None;word=None;email_text='';email_reco={};exrows={};exmeta={};recalc=None;render=None
    empty=lambda:{'metrics':{},'sources':{},'recommendations':{},'table_metadata':[]}
    observed=empty();word_observed=empty();word_reco={};response={'score':0.,'quality':0.,'coverage':0.,'cases':[]}
    def attempt(name,action):
        try:return action()
        except io['CandidateError'] as e:errors[name]=str(e);return None
        except office['OfficeRuntimeError'] as e:
            if e.code not in io['CONTENT_ERRORS']:raise
            errors[name]=e.code;return None
    def read_quote():
        nonlocal recalc,original
        path=root/contract['files']['quote'];original=io['observe'](io['grids'](io['workbook'](path)),contract)
        recalc=office['recalculate_xlsx'](path,lock,derived/'baseline-quote',timeout_seconds=90)
        return io['observe'](io['grids'](io['workbook'](recalc['path'])),contract)
    book=attempt('quote',read_quote);objects['quote']=book is not None
    if book:
        observed=book
        response=attempt('formula_responses',lambda:logic['responses'](root/contract['files']['quote'],original,truth,contract,io,model,lock,derived/'input-responses')) or response
    word=attempt('proposal',lambda:io['word'](root/contract['files']['proposal']));objects['proposal']=word is not None
    if word:
        word_observed=io['observe'](io['word_grids'](word),contract)
        word_reco=io['prose_recommendations']([p for p in word['paragraphs'] if p['parent_cell'] is None],contract)
        for identity,fields in word_observed['recommendations'].items():
            target=word_reco.setdefault(identity,{})
            for key,entries in fields.items():target.setdefault(key,[]).extend(entries)
        render=attempt('proposal_render',lambda:render_helper['render'](root/contract['files']['proposal'],render_lock,derived/'proposal-render',[p['text'] for p in word['paragraphs']],'word',io))
    mail=attempt('customer_email',lambda:io['email'](root/contract['files']['email'],contract));objects['email']=mail is not None
    if mail:email_text,email_reco=mail
    ex=attempt('exceptions',lambda:io['exceptions'](root/contract['files']['exceptions'],contract));objects['exceptions']=ex is not None
    if ex:exrows,exmeta=ex
    numeric=logic['values'](observed,truth,contract,io);constraints=logic['states'](observed,truth,contract,io)
    sources,_=logic['source_checks'](original or empty(),truth,contract,io)
    word_numeric=logic['values'](word_observed,truth,contract,io,contract['word_required_numeric_fields'])
    word_status={pair:logic['all_values'](word_observed['metrics'].get(pair,{}).get('status'),c['status'],io,contract,kind='status') for pair,c in truth['cases'].items()}
    recos={kind:logic['recommendations'](r,truth,contract,io) for kind,r in [('quote',observed['recommendations']),('word',word_reco),('email',email_reco)]}
    exceptions=logic['exceptions_check'](exrows,exmeta,oracle,index,contract,io)
    avg_rows=lambda rows:mean(mean(v.values()) for v in rows.values())
    quantities=avg_rows(numeric);decisions=avg_rows(constraints);word_values=mean([avg_rows(word_numeric),mean(word_status.values())]);reco_score=mean(avg_rows(v) for v in recos.values())
    correctness=.55*quantities+.15*decisions+.15*word_values+.10*reco_score+.05*exceptions['score']
    def fields(keys,pairs=None):return mean(numeric[p][k] for p in (pairs or truth['cases']) for k in keys)
    def check(name,pairs=None):return mean(constraints[p][name] for p in (pairs or truth['cases']))
    source_score=avg_rows(sources)
    boundaries={
        'minimum_module_ceiling':fields(['module_count','inverter_count']),
        'capacity_and_area':mean([fields(['dc_kwp','area_m2']),check('AREA'),check('GRID')]),
        'roof_type_load':mean([fields(['design_load_kg_m2']),check('LOAD')]),
        'replacement_permission':check('REPLACEMENT'),
        'whole_roof_replacement':fields(['replacement_area_m2','cost_replacement','cost_drainage'],['S1-B','S2-B','S3-B']),
        'mandatory_electrical_bom':fields(['cost_module','cost_inverter','cost_cable','cost_isolation']),
        'adhesion_and_corrosion_fees':fields(['cost_adhesion','cost_corrosion']),
        'separate_tax_rounding':fields(['tax_goods','tax_construction','tax_services']),
        'known_gross_budget':mean([fields(['gross_total','budget_margin']),check('BUDGET')]),
        'unknown_not_zero':mean([mean(all(sources.get('site:S3/'+key,{}).values()) for key in ['verified_load_kg_m2','load_status','corrosion_evidence','roof_repair_cost']),check('LOAD',['S3-A','S3-B','S3-C']),check('REPAIR_SCOPE',['S3-A','S3-B','S3-C'])]),
        'hard_failure_priority':mean(constraints[p]['status'] for p,c in truth['cases'].items() if c['status']=='infeasible'),
        'conditional_recommendation':mean(recos[k]['S3']['status'] and recos[k]['S3']['option'] for k in recos),
        'no_subsidy_deduction':fields(['gross_total']),
        'cross_artifact_consistency':mean([word_values,reco_score,exceptions['score']]),
        'actual_source_binding':exceptions['binding_score']}
    if set(boundaries)!=set(counter['boundary_groups']):raise ValueError('H013 private boundary map mismatch')
    boundary=.5*response['score']+.2*source_score+.3*mean(boundaries.values())
    qtexts={identity:[] for identity in truth['requirements']}
    if word:
        # Match public requirement IDs in actual editable Word table rows or labelled paragraphs.
        for t in word['tables']:
            for row in t['rows']:
                text=' '.join(c['text'] for c in row['cells'])
                for identity in qtexts:
                    if re.search(r'\b'+identity+r'\b',text):qtexts[identity].append(text)
        for p in word['paragraphs']:
            if p['parent_cell'] is not None:continue
            for identity in qtexts:
                if re.match(r'^\s*'+identity+r'\b',p['text']):qtexts[identity].append(p['text'])
    requirement_presence={k:bool(v) and all('待填写' not in t for t in v) for k,v in qtexts.items()}
    complete_pairs=set(observed['metrics'])==set(truth['cases'])
    complete_recos=all(set(r)==set(truth['recommendations']) for r in [observed['recommendations'],word_reco,email_reco])
    native_editable=bool(word and not word['pending_revisions'] and render and render['basic_fit'])
    delivery=mean([mean(objects.values()),complete_pairs,complete_recos,exceptions['exact_set'],mean(requirement_presence.values()),native_editable,intact])
    scores={'business_correctness':correctness,'boundary_cases':boundary*intact,'delivery_integrity':delivery*intact,'evidence_binding':exceptions['binding_score']*intact}
    if not any(objects.values()):scores={k:0. for k in scores}
    scores['overall_score']=sum(scores[k]*w for k,w in oracle['checkpoint_weights'].items())
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H013 score out of bounds')
    report={'schema_version':'h013-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'parsed_outputs':objects,
        'numeric_checks':numeric,'constraint_checks':constraints,'source_checks':sources,'word_numeric_checks':word_numeric,'word_status':word_status,
        'recommendation_checks':recos,'exceptions':exceptions,'boundary_groups':boundaries,'requirement_presence':requirement_presence,
        'table_metadata':{'quote':observed['table_metadata'],'word':word_observed['table_metadata']},'input_responses':response,
        'baseline_recalculation':recalc,'proposal_render':render,
        'limit':'Bounded native values/states/IDs/source/response checks only. Independent Judge must assess complete reasons, unknown costs/subsidies, unsupported actual approvals and real readability; no semantic score is manufactured.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h013-analysis.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,default=str);f.write('\n')
    return scores
