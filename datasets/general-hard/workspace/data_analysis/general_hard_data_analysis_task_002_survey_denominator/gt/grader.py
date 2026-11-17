"""Automated source-grounded survey scoring with managed Office evidence."""
from pathlib import Path
import hashlib,json,os,runpy

def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    load=lambda name:json.loads((gt/name).read_text(encoding='utf-8'))
    binding=load('scoring_contract.json')
    for name,digest in binding['private_sha256'].items():
        if sha(gt/name)!=digest:raise ValueError('H018 private contract/helper drift: '+name)
    expected=load('expected.json');contract=load('runtime_contract.json');protected=load('protected_sha256.json')
    if expected['status']!='native_source_two_path_verified' or len(expected['cleaned'])!=240 or expected['statistics']['kept_respondents']!=185 or contract['grading_type']!='automated':raise ValueError('H018 invalid oracle/runtime contract')
    io=runpy.run_path(str(gt/'survey_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));checks=runpy.run_path(str(gt/'business_checks.py'));response=runpy.run_path(str(gt/'response_checks.py'));reporter=runpy.run_path(str(gt/'report_checks.py'));mean=checks['mean']
    for name in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):raise RuntimeError('H018 managed scoring runtime missing: '+name)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());rlock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']).read_text());office['validate_office_lock'](lock);office['validate_office_render_lock'](rlock)
    if rlock['office_runtime']!=lock or 'docx' not in office['office_render_lock_formats'](rlock):raise RuntimeError('H018 matching Word render context required')
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H018 derived evidence must be outside frozen Workspace')
    intact=all((root/n).is_file() and not (root/n).is_symlink() and sha(root/n)==digest for n,digest in protected.items())
    errors={};parsed={};original=None;recalculation=None;book=None;word=None;audits=None;observations=None;render=None;risks=[];responses={'score':0.,'status':'workbook_missing','cases':[]}
    def attempt(name,action):
        try:value=action();parsed[name]=True;return value
        except (io['CandidateError'],io['WORD']['CandidateWordError']) as error:errors[name]=str(error);parsed[name]=False;return None
        except office['OfficeRuntimeError'] as error:
            if error.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[name]=error.code;parsed[name]=False;return None
    def read_book():
        nonlocal original,recalculation
        p=io['candidate_path'](root,'analysis.xlsx');office['_clean_package'](p.read_bytes());original=io['XLSX']['read_book'](p);recalculation=office['recalculate_xlsx'](p,lock,derived/'baseline',timeout_seconds=90);calculated=io['XLSX']['read_book'](recalculation['path']);source={s['name']:s for s in original}
        for s in calculated:
            if s['name'] not in source:raise RuntimeError('trusted Office unexpectedly changed worksheet identities')
            for pos,cell in s['cells'].items():cell['visible']=cell['visible'] and source[s['name']]['cells'].get(pos,{'visible':source[s['name']]['state']=='visible'})['visible']
        return calculated
    def read_word():
        nonlocal risks
        p=io['candidate_path'](root,'summary.docx');office['_inspect_docx_render_package'](p.read_bytes());obj=io['read_word'](p);risks=reporter['visibility_risks'](p,io['WORD']);return obj
    book=attempt('workbook',read_book);word=attempt('word',read_word);audits=attempt('exclusions',lambda:io['csv_rows'](io['candidate_path'](root,'exclusions.csv'),contract['exclusion_fields']))
    word_checks=attempt('word_facts',lambda:reporter['word_checks'](word,expected,contract,io)) or reporter['word_checks'](None,expected,contract,io);audit_checks=checks['exclusion_checks'](audits,expected,io)
    if word is not None:render=attempt('word_render',lambda:reporter['render'](io['candidate_path'](root,'summary.docx'),rlock,derived/'word-render',office,word_checks['texts'],io))
    word_fit=bool(word and not word['pending_revisions'] and not risks and render and render['basic_fit'])
    scores=dict.fromkeys(['business_correctness','boundary_cases','delivery_integrity','evidence_binding'],0.);cap=None
    if book is not None:
        observations=checks['observe'](book,expected,contract,io)
        responses=response['responses'](io['candidate_path'](root,'analysis.xlsx'),original,book,observations,expected,contract,io,checks,office,lock,derived/'responses')
        scores['business_correctness']=.35*observations['summary']['score']+.25*observations['record_score']+.2*observations['flag_score']+.2*word_checks['score']
        scores['boundary_cases']=(.55*responses['score']+.25*mean(observations['exception_groups'].values())+.2*audit_checks['score'])*intact
        critical=observations['raw_set_complete'] and observations['model_set_complete'] and all(observations['raw_checks'].values()) and observations['visible']
        if not critical or word is not None and not word_fit:scores['business_correctness']=min(scores['business_correctness'],.5);cap='raw record identity/content or basic output visibility violated'
        scores['delivery_integrity']=float(all(parsed.values()) and critical and observations['data_complete'] and observations['summary']['complete'] and responses['score']==1. and responses.get('driver_visible',False) and audit_checks['exact'] and all(audit_checks['rows'].values()) and word_checks['complete'] and word_fit)*intact
        scores['evidence_binding']=(.75*audit_checks['locators']+.25*mean(word_checks['quotes'].values()))*intact
    scores={k:round(v,12) for k,v in scores.items()};scores['overall_score']=round(sum(scores[k]*v for k,v in binding['checkpoint_weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H018 score out of bounds')
    # Tables carry parser-only cell objects; compact these in the persistent evidence.
    if observations:
        observations={k:v for k,v in observations.items() if k!='model_rows'}
        observations['summary']={k:v for k,v in observations['summary'].items() if k!='rows'}
    word_checks={k:v for k,v in word_checks.items() if k!='texts'}
    report={'schema_version':'h018-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'parsed_outputs':parsed,'survey_checks':observations,'report_checks':word_checks,'exclusion_checks':audit_checks,'formula_responses':responses,'office_baseline':recalculation,'office_word_render':render,'word_visibility_risks':risks,'business_cap_reason':cap,'limit':'Automated bounded source/data/formula/provenance and basic native visibility only. No full semantic/visual Judge, real Harness execution or measured L2 difficulty.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h018-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    return scores
