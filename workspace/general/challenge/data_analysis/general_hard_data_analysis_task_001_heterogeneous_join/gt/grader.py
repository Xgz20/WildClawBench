from pathlib import Path
import hashlib,json,os,runpy

def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    def load(name):return json.loads((gt/name).read_text(encoding='utf-8'))
    binding=load('scoring_contract.json')
    for name,digest in binding['private_sha256'].items():
        if sha(gt/name)!=digest:raise ValueError('H017 private contract/helper drift: '+name)
    expected=load('expected.json');protected=load('protected_sha256.json');contract=load('runtime_contract.json')
    if expected['status']!='native_source_two_path_verified' or len(expected['targets'])!=120 or len(expected['sources'])!=146:raise ValueError('H017 invalid source oracle')
    office=runpy.run_path(str(gt/'office_runtime.py'));io=runpy.run_path(str(gt/'xlsx_observations.py'));checks=runpy.run_path(str(gt/'join_checks.py'))
    for name in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):raise RuntimeError('H017 managed scoring runtime missing: '+name)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());office['validate_office_lock'](lock)
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H017 derived evidence must be outside frozen Workspace')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    errors={};book=None;original=None;recalc=None;audit=None;parsed={};obs=None
    def path(name):
        p=root/'results'/name
        if (root/'results').is_symlink() or not p.is_file() or p.is_symlink() or p.stat().st_size>5242880 or p.resolve().parent!=root/'results':raise io['CandidateError']('missing, unsafe or oversized '+name)
        return p
    def attempt(name,action):
        try:value=action();parsed[name]=True;return value
        except io['CandidateError'] as error:errors[name]=str(error);parsed[name]=False;return None
        except office['OfficeRuntimeError'] as error:
            if error.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[name]=error.code;parsed[name]=False;return None
    def workbook():
        nonlocal original,recalc
        p=path('aligned.xlsx');office['_clean_package'](p.read_bytes());original=io['read_book'](p)
        recalc=office['recalculate_xlsx'](p,lock,derived/'alignment-recalculation',timeout_seconds=90)
        return io['read_book'](recalc['path'])
    book=attempt('workbook',workbook);audit=attempt('audit',lambda:io['read_csv'](path('join_audit.csv'),contract['audit_columns']))
    scores=dict.fromkeys(['business_correctness','boundary_cases','delivery_integrity','evidence_binding'],0.)
    cap=None
    if book is not None:
        # Recalculated values are authoritative; original style/row/sheet visibility remains binding.
        by_sheet={s['name']:s for s in original}
        for sheet in book:
            source=by_sheet.get(sheet['name'])
            if source is None:raise RuntimeError('trusted Office unexpectedly changed worksheet identities')
            for pos,cell in sheet['cells'].items():cell['visible']=cell['visible'] and source['cells'].get(pos,{'visible':source['state']=='visible'})['visible']
        targets=io['discover'](book,contract['target_aliases'],'target');unmatched=io['discover'](book,contract['unmatched_aliases'],'unmatched')
        obs=checks['inspect'](targets,unmatched,audit,expected,io)
        scores['business_correctness']=obs['correctness'];scores['boundary_cases']=obs['boundary']*intact
        critical=obs['delivery_checks']
        if not critical['original_target_fields'] or not critical['visible_outputs'] or not critical['unique_targets']:
            scores['business_correctness']=min(scores['business_correctness'],.5);cap='original target fields, unique target set or visibility violated'
        scores['delivery_integrity']=float(all(parsed.values()) and all(critical.values()))*intact
        scores['evidence_binding']=obs['evidence']*intact
    scores={k:round(v,12) for k,v in scores.items()};scores['overall_score']=round(sum(scores[k]*v for k,v in binding['checkpoint_weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H017 score out of bounds')
    report={'schema_version':'h017-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'parsed_outputs':parsed,'observations':obs,'office_recalculation':recalc,'business_cap_reason':cap,
      'native_formula_errors':{s['name']:s['errors'] for s in book or [] if s['errors']},
      'limit':'Automated native target values, full link multiplicity, unmatched sets and actual row locators. Basic hidden-row/cell checks are not a full visual usability review. Real external actions require bound execution traces; workbook prose does not prove execution. Rule 1.0 is not measured L2 difficulty or Harness performance.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h017-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    return scores
