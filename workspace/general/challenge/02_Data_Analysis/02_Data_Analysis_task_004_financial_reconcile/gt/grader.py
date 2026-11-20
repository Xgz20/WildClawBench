"""Hybrid task's deterministic financial component; no semantic Judge is invoked here."""
from pathlib import Path
import hashlib,json,os,runpy
def grade(workspace):
    root=Path(workspace).resolve();g=root/'gt';load=lambda n:json.loads((g/n).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();binding=load('scoring_contract.json')
    for name,digest in binding['private_sha256'].items():
        if sha(g/name)!=digest:raise ValueError('H020 private helper or contract drift: '+name)
    e=load('expected.json');contract=load('runtime_contract.json');protected=load('protected_sha256.json')
    if e['status']!='input_two_path_decimal_fraction_sql_verified' or len(e['baseline'])!=27 or len(e['sources'])!=63 or contract['grading_type']!='hybrid':raise ValueError('H020 private financial contract invalid')
    io=runpy.run_path(str(g/'financial_io.py'));checks=runpy.run_path(str(g/'business_checks.py'));response=runpy.run_path(str(g/'response_checks.py'));reporter=runpy.run_path(str(g/'report_checks.py'));display=runpy.run_path(str(g/'office_report_helper.py'));office=runpy.run_path(str(g/contract['office_helper']));mean=checks['mean']
    for name in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):raise RuntimeError('H020 managed runtime missing '+name)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());render_lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']).read_text());office['validate_office_lock'](lock);office['validate_office_render_lock'](render_lock)
    if render_lock['office_runtime']!=lock or 'docx' not in office['office_render_lock_formats'](render_lock):raise RuntimeError('H020 matching native Word renderer required')
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H020 derived evidence must be outside frozen Workspace')
    intact=all((root/n).is_file() and not (root/n).is_symlink() and sha(root/n)==digest for n,digest in protected.items());errors={};parsed={};original=None;calculation=None;render=None;risks=[]
    def attempt(label,action):
        try:value=action();parsed[label]=True;return value
        except io['CandidateError'] as error:errors[label]=str(error);parsed[label]=False;return None
        except office['OfficeRuntimeError'] as error:
            if error.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[label]=error.code;parsed[label]=False;return None
    def read_book():
        nonlocal original,calculation
        p=io['candidate_path'](root,'comparison.xlsx');office['_clean_package'](p.read_bytes());original=io['formula_coverage'](p,io['XLSX']['read_book'](p));calculation=office['recalculate_xlsx'](p,lock,derived/'baseline',timeout_seconds=90);book=io['XLSX']['read_book'](calculation['path']);original_sheets={s['name']:s for s in original}
        for s in book:
            if s['name'] not in original_sheets:raise RuntimeError('trusted Office changed sheet identity')
            for pos,cell in s['cells'].items():cell['visible'] &= original_sheets[s['name']]['cells'].get(pos,{'visible':original_sheets[s['name']]['state']=='visible'})['visible']
        return book
    def read_word():
        nonlocal risks
        p=io['candidate_path'](root,'memo.docx');office['_inspect_docx_render_package'](p.read_bytes());model=io['read_word'](p)
        try:risks=display['visibility_risks'](p,io['WORD'])
        except io['WORD']['CandidateWordError'] as error:raise io['CandidateError'](str(error)) from error
        return model
    book=attempt('workbook',read_book);word=attempt('word',read_word);csv=attempt('sources',lambda:io['csv_rows'](io['candidate_path'](root,'sources.csv'),contract['source_fields']));word_checks=reporter['facts'](word,e,contract,io,checks);source_checks=checks['sources'](csv,e['sources'],contract,io)
    if word is not None:render=attempt('word_render',lambda:display['render'](io['candidate_path'](root,'memo.docx'),render_lock,derived/'word-render',office,word_checks['texts'],{'canon':io['render_canon']}))
    word_fit=bool(word and not word['pending_revisions'] and not risks and render and render['basic_fit']);observed=None;data=None;revisions=None;responses={'score':0.,'status':'workbook_missing','cases':[],'drivers_visible':False};cap=None
    scores={'business_correctness':.25*word_checks['score'],'boundary_cases':0.,'delivery_integrity':0.,'evidence_binding':(.6*source_checks['binding_score']+.4*source_checks['score'])*float(source_checks['exact'])*intact}
    if book is not None:
        observed=checks['metrics'](book,e['baseline'],contract,io,original);data=checks['data'](book,e['data'],contract,io);revisions=checks['revisions'](book,e['restatements'],contract,io);responses=response['responses'](io['candidate_path'](root,'comparison.xlsx'),original,observed,data,e,contract,io,checks,office,lock,derived/'responses')
        scores['business_correctness']+=.45*observed['score']+.2*data['score']+.1*revisions['score']
        boundary=[]
        for c,y,m,reason in e['incomparable_slots']:
            fields=observed['checks']['/'.join(map(str,(c,y,m)))];boundary.extend(fields[k] for k in ['value','rank','change_pp','status','reason'])
        for key,fields in [('C/2023/roe',['value','rank','status']),('B/2023/cash_to_profit',['value','rank','status']),('A/2025/cash_to_profit',['numerator_wan','value','status']),('A/2024/revenue_yoy',['numerator_wan']),('A/2025/revenue_yoy',['denominator_wan']),('B/2023/roe',['numerator_wan']),('B/2025/roe',['rank']),('C/2025/roe',['rank'])]:boundary.extend(observed['checks'][key][f] for f in fields)
        scores['boundary_cases']=(.8*responses['score']+.2*mean(boundary))*intact
        critical=observed['identity_complete'] and observed['visible'] and data['complete'] and data['visible']
        if not critical or word is not None and not word_fit:scores['business_correctness']=min(scores['business_correctness'],.5);cap='metric identity, effective input source or native visibility invalid'
        if len(responses['cases'])==5 and (responses['score']==0 or not responses['drivers_visible']):scores['business_correctness']=min(scores['business_correctness'],.5);cap='no verified changed business response or actual editable driver hidden'
        if observed['formula_score']==0.:scores['business_correctness']=min(scores['business_correctness'],.5);cap='metric model is entirely static'
        scores['delivery_integrity']=float(all(parsed.values()) and critical and observed['complete'] and observed['formula_score']==1. and revisions['complete'] and revisions['visible'] and responses['score']==1. and responses['drivers_visible'] and word_fit and word_checks['complete'] and source_checks['complete'])*intact
    if not intact:scores['business_correctness']=min(scores['business_correctness'],.5);cap='frozen input changed'
    scores={k:round(v,12) for k,v in scores.items()};scores['overall_score']=round(sum(scores[k]*weight for k,weight in binding['checkpoint_weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H020 automated score out of bounds')
    data={k:v for k,v in data.items() if k!='candidates'} if data else None;word_checks={k:v for k,v in word_checks.items() if k!='texts'}
    observation={'schema_version':'h020-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'parsed_outputs':parsed,'metrics':observed,'effective_data':data,'revisions':revisions,'sources':source_checks,'word':word_checks,'formula_responses':responses,'office_baseline':calculation,'office_word_render':render,'word_visibility_risks':risks,'business_cap_reason':cap,'limit':'Automatic native facts/source/formula/visibility only. Independent semantic rubric required; no real Harness or measured L3/discrimination result.'};derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h020-analysis.json').open('x',encoding='utf-8') as f:json.dump(observation,f,ensure_ascii=False,indent=2);f.write('\n')
    return scores
