from pathlib import Path
import hashlib,json,os,runpy

def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt'
    def private(name):
        with (gt/name).open(encoding='utf-8') as f:return json.load(f)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    truth=private('expected.json');claims=private('business_oracle.json');contract=private('artifact_contract.json');protected=private('protected_sha256.json');requirements=private('evidence_requirements.json');binding=private('scoring_contract.json')
    if truth['status']!='native_sources_verified_before_reference' or not requirements['semantic_judge'] or len(claims['claims'])!=19 or len(claims['unknown_groups'])!=4:raise ValueError('H015 private source contract invalid')
    for name,digest in binding['private_sha256'].items():
        if sha(gt/name)!=digest:raise ValueError('H015 private contract/helper drift: '+name)
    io=runpy.run_path(str(gt/'artifact_io.py'));checks=runpy.run_path(str(gt/'business_checks.py'));model=runpy.run_path(str(gt/'business_model.py'));prose=runpy.run_path(str(gt/'prose_observations.py'));render_helper=runpy.run_path(str(gt/'render_checks.py'));office=io['OFFICE'];mean=io['mean']
    for name in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):raise RuntimeError('H015 managed scoring runtime missing: '+name)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());render_lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']).read_text())
    office['validate_office_lock'](lock);office['validate_office_render_lock'](render_lock)
    if render_lock['office_runtime']!=lock or set(office['office_render_lock_formats'](render_lock))!={'docx','pptx'}:raise RuntimeError('H015 requires matching explicit both-format render lock')
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H015 derived evidence must be outside frozen Workspace')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==v['sha256'] for name,v in protected.items())
    errors={};objects={};book=None;original=None;word=None;deck=None;index=None;recalc=None;renders={}
    empty=lambda:{'historical':{},'cash':{},'nodes':{},'inputs':{},'metadata':[]}
    observations={kind:empty() for kind in ['book','word','deck']};paras={kind:[] for kind in ['word','deck']}
    def attempt(kind,action):
        try:return action()
        except io['CandidateError'] as e:errors[kind]=str(e);return None
        except office['OfficeRuntimeError'] as e:
            if e.code not in io['CONTENT_ERRORS']:raise
            errors[kind]=e.code;return None
    def read_book():
        nonlocal original,recalc
        p=root/contract['files']['workbook'];original=io['observe'](io['workbook'](p,contract)['grids'],contract)
        recalc=office['recalculate_xlsx'](p,lock,derived/'baseline-options',timeout_seconds=90)
        return io['workbook'](recalc['path'],contract)
    book=attempt('workbook',read_book);objects['workbook']=book is not None
    if book:observations['book']=io['observe'](book['grids'],contract)
    word=attempt('word',lambda:io['word'](root/contract['files']['word']));objects['word']=word is not None
    if word:
        observations['word']=io['observe'](io['word_grids'](word),contract)
        paras['word']=[p for p in word['paragraphs'] if p['parent_cell'] is None]
        for key,values in prose['prose_history'](paras['word'],contract,io).items():
            target=observations['word']['historical'].setdefault(key,{})
            for field,entries in values.items():target.setdefault(field,[]).extend(entries)
        checks['merge_prose'](observations['word'],io['prose_cash'](paras['word'],contract))
        renders['word']=attempt('word_render',lambda:render_helper['render'](root/contract['files']['word'],render_lock,derived/'memo-render',[p['text'] for p in word['paragraphs']],'word',io))
    deck=attempt('deck',lambda:io['deck'](root/contract['files']['deck']));objects['deck']=deck is not None
    if deck:
        observations['deck']=io['observe'](deck['grids'],contract);paras['deck']=deck['paragraphs']
        checks['merge_prose'](observations['deck'],io['prose_cash'](paras['deck'],contract))
        renders['deck']=attempt('deck_render',lambda:render_helper['render'](root/contract['files']['deck'],render_lock,derived/'deck-render',[p['text'] for p in deck['paragraphs']],'pptx',io))
    index=attempt('evidence',lambda:io['json_file'](root/contract['files']['evidence']));objects['evidence']=index is not None
    recommendations=checks['recommendation_checks'](io['recommendations'](paras['word'],contract),io['recommendations'](paras['deck'],contract),index,observations['book'],truth,io,contract)
    cases=list(contract['required_original_cases'])
    if recommendations['selected'] in {'A_phase1','A_deferred'}:cases.append(recommendations['selected'])
    cash=model['cash_model'](truth)
    sums=checks['summary'](observations['book'],cash,cases,contract['required_cash_summary'],io,contract)
    ns=checks['nodes'](observations['book'],cash,cases,io,contract)
    hist=checks['history'](observations['word'],truth,io,contract)
    word_cash=checks['summary'](observations['word'],cash,cases,contract['word_cash_summary'],io,contract)
    deck_cash=checks['summary'](observations['deck'],cash,cases,contract['deck_cash_summary'],io,contract)
    # When extra named rows are supplied, their recognized quantitative claims must also agree.
    optional={kind:{case:{field:checks['equal'](entries,cash[case][field],io,contract,field) for field,entries in values.items() if field in cash[case]} for case,values in obs['cash'].items() if case in cash} for kind,obs in observations.items()}
    optional_score=mean(checks['average_rows'](v,io) for v in optional.values())
    native_comparison=mean([checks['average_rows'](word_cash,io),checks['average_rows'](deck_cash,io),optional_score])
    correctness=.4*checks['average_rows'](sums,io)+.25*mean(ns.values())+.2*checks['average_rows'](hist,io)+.1*native_comparison+.05*recommendations['score']
    cap_reason=None
    if any(recommendations['primary'][kind] in {'A','B'} for kind in ['word','deck']):
        correctness=min(correctness,.5);cap_reason='explicit current original A/B recommendation violates the known cash floor'
    elif len({v for v in recommendations['primary'].values() if v is not None})>1:
        correctness=min(correctness,.75);cap_reason='explicit current recommendations conflict across deliverables'
    source_check=checks['input_parameters'](original or empty(),truth,io,contract)
    response={'score':0.,'cases':[]}
    if book:response=attempt('input_response',lambda:checks['responses'](root/contract['files']['workbook'],original,truth,model,cases,io,contract,lock,derived/'input-responses')) or response
    boundary=.65*response['score']+.2*mean(ns.values())+.15*mean(source_check.values())
    word_fit=bool(word and not word['pending_revisions'] and renders.get('word') and renders['word']['basic_fit'])
    deck_fit=bool(deck and deck['slide_count']==contract['native_deck_slide_count'] and not deck['hidden'] and renders.get('deck') and renders['deck']['page_count']==6 and renders['deck']['basic_fit'])
    cases_complete=all(case in observations['book']['cash'] for case in cases)
    evidence=checks['evidence_checks'](index,root,word,deck,book,truth,io,contract) if index is not None else {'score':0.,'citations':[]}
    nodes_complete=all(key in observations['book']['nodes'] for key in ns)
    index_complete=bool(evidence['citations'] and all(evidence.get('source_coverage',{}).values()) and all(evidence.get('target_coverage',{}).values()))
    delivery=float(all(objects.values()) and cases_complete and nodes_complete and word_fit and deck_fit and index_complete and intact)
    scores={'business_correctness':correctness,'boundary_cases':boundary*intact,'delivery_integrity':delivery*intact,'evidence_binding':evidence['score']*intact}
    if not any(objects.values()):scores={k:0. for k in scores}
    scores['overall_score']=sum(scores[k]*v for k,v in contract['checkpoint_weights'].items())
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H015 score out of bounds')
    report={'schema_version':'h015-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'parsed_outputs':objects,
      'cash_summary_checks':sums,'cash_node_checks':ns,'historical_word_checks':hist,'word_cash_checks':word_cash,'deck_cash_checks':deck_cash,
      'optional_claim_checks':optional,'recommendation_checks':recommendations,'editable_inputs':source_check,'input_responses':response,
      'evidence_index':evidence,'business_correctness_cap_reason':cap_reason,'delivery_checks':{'word_editable_and_visible':word_fit,'deck_six_editable_pages':deck_fit,'modeled_cases_complete':cases_complete,'cash_nodes_complete':nodes_complete,'index_complete':index_complete},
      'table_metadata':{k:v['metadata'] for k,v in observations.items()},'baseline_recalculation':recalc,'office_renders':renders,
      'limit':'Bounded native numbers, dates, case identity, cash input response and citation existence only. Independent Judge must assess full inference, causality, permission, unknowns, approval claims, any charts and actual readability. Rule 1.0 is not task correctness or a semantic score.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h015-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2,default=str);f.write('\n')
    return scores
