from pathlib import Path
import hashlib,json,os,runpy,zipfile

class CandidateError(ValueError):pass

def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    def load(name):return json.loads((gt/name).read_text(encoding='utf-8'))
    binding=load('scoring_contract.json')
    for name,digest in binding['private_sha256'].items():
        if sha(gt/name)!=digest:raise ValueError('H016 private contract/helper drift: '+name)
    expected=load('expected.json');original=load('original_graph.json');protected=load('protected_sha256.json')
    if expected['status']!='independently_read_clean_original_before_reference' or len(expected['headings'])!=26:raise ValueError('H016 source contract invalid')
    office=runpy.run_path(str(gt/'office_runtime.py'));graph=runpy.run_path(str(gt/'candidate_graph.py'));checks=runpy.run_path(str(gt/'structure_checks.py'));renderer=runpy.run_path(str(gt/'render_checks.py'));mean=checks['mean']
    for name in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):raise RuntimeError('H016 managed scoring runtime missing: '+name)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());rlock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']).read_text())
    office['validate_office_lock'](lock);office['validate_office_render_lock'](rlock)
    if rlock['office_runtime']!=lock or 'docx' not in office['office_render_lock_formats'](rlock):raise RuntimeError('H016 matching Word render lock required')
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H016 derived evidence must be outside frozen Workspace')
    intact=all((root/n).is_file() and not (root/n).is_symlink() and sha(root/n)==digest for n,digest in protected.items())
    errors={};parsed={};g=None;render=None;obs=None;log=None;readme=None
    def path(name):
        p=root/'results'/name
        if not p.is_file() or p.is_symlink() or p.stat().st_size>32*1024*1024 or p.resolve().parent!=(root/'results').resolve():raise CandidateError('missing or unsafe output '+name)
        return p
    def attempt(name,action):
        try:value=action();parsed[name]=True;return value
        except (CandidateError,graph['GraphError'],zipfile.BadZipFile) as e:errors[name]=str(e);parsed[name]=False;return None
        except office['OfficeRuntimeError'] as e:
            if e.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[name]=e.code;parsed[name]=False;return None
    def docx():
        p=path('repaired.docx');office['_inspect_docx_render_package'](p.read_bytes())
        return graph['read_graph'](p,expected['protected']['paragraphs'])
    def jsonfile():
        try:return json.loads(path('repair_log.json').read_text(encoding='utf-8'))
        except (json.JSONDecodeError,UnicodeDecodeError) as e:raise CandidateError('invalid repair_log.json') from e
    def mdfile():
        try:return path('readme.md').read_text(encoding='utf-8')
        except UnicodeDecodeError as e:raise CandidateError('invalid readme.md') from e
    g=attempt('word',docx);log=attempt('log',jsonfile);readme=attempt('readme',mdfile)
    if g:
        obs=checks['observe'](g,expected)
        render=attempt('word_render',lambda:renderer['render'](path('repaired.docx'),rlock,derived/'word-render',office,expected,original))
    evidence=checks['log_checks'](log,None,g,expected,obs) if log is not None and obs else {'score':0.,'coverage':{}}
    explain=bool(readme and ('更新' in readme or 'updat' in readme.lower()) and ('目录' in readme or 'TOC' in readme.upper()) and ('域' in readme or 'field' in readme.lower()) and ('打开' in readme or 'open' in readme.lower()))
    scores=dict.fromkeys(['business_correctness','boundary_cases','delivery_integrity','evidence_binding'],0.)
    cap=None
    if obs:
        s=obs['scores'];r=render or {}
        visible=lambda key:mean(r.get(key,{}).values())
        scores['business_correctness']=.35*s['headings']*visible('heading_visible')+.1*s['steps']+.2*s['toc']*visible('toc_page_checks')+.15*s['captions']*visible('caption_visible')+.2*s['references']*visible('reference_visible')
        preservation=obs['preservation']
        scores['boundary_cases']=mean(preservation.values())*intact
        if not all(preservation.values()):scores['business_correctness']=min(scores['business_correctness'],.5);cap='protected content, order, comments, edit state or visibility changed'
        scores['delivery_integrity']=float(all(parsed.values()) and all(preservation.values()) and bool(render and render['basic_fit']) and explain)*intact
        scores['evidence_binding']=evidence['score']*intact
    scores={k:round(v,12) for k,v in scores.items()}
    scores['overall_score']=round(sum(scores[k]*v for k,v in binding['checkpoint_weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H016 score out of bounds')
    report={'schema_version':'h016-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'parsed_outputs':parsed,'structural_checks':obs,'office_render':render,'repair_log':evidence,'readme_update_instructions':explain,'business_cap_reason':cap,
      'limit':'Bounded native structural, protection, actual field rendering and locator observations only. Rule 1.0 is not independent semantic correctness, Word GUI testing, four-Harness calibration or measured L4 difficulty.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h016-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    return scores
