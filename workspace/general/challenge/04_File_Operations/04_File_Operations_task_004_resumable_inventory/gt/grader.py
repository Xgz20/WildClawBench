from pathlib import Path
import csv,hashlib,json,os,runpy,time,unicodedata
W={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def grade(**kwargs):
    root=Path(kwargs.get('workspace_path') or '/tmp_workspace');gt=root/'gt';trusted=json.loads((gt/'trusted_files.json').read_text())
    for name,h in trusted.items():
        p=gt/name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise RuntimeError('H038_TRUSTED_CONTEXT_MISSING_OR_DRIFT: '+name)
    evidence=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not evidence or not Path(evidence).is_dir():raise RuntimeError('H038_RULE_EVIDENCE_CONTEXT_UNAVAILABLE')
    io=runpy.run_path(str(gt/'native_io.py'));expected=json.loads((gt/'expected.json').read_text());protected=json.loads((gt/'protected_sha256.json').read_text());bykey={s['key']:s for s in expected['sources']}
    rows=None;report=None
    def safe(p):return p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
    try:
        p=root/'results/manifest.tsv'
        if safe(p):rows=io['read_manifest'](p)
    except (ValueError,UnicodeError,OSError,csv.Error):pass
    try:
        p=root/'results/recovery.json'
        if safe(p):
            d=io['read_json'](p)
            if isinstance(d,dict):report=d
    except (ValueError,UnicodeError,OSError):pass
    grouped={}
    for r in rows or []:grouped.setdefault(io['nfc'](r.get('key','')),[]).append(r)
    valid={k:rs[0] for k,rs in grouped.items() if k in bykey and len(rs)==1};paths={}
    for key,r in valid.items():
        p=io['path_value'](r.get('archive_path'))
        if p:paths.setdefault(p,[]).append(key)
    business=[]
    for key,s in bykey.items():
        r=valid.get(key)
        if r is None:business.append(0.);continue
        rel=io['path_value'](r.get('archive_path'));checks=[io['path_value'](r.get('source_path'),'source')==s['source_path'],r.get('sha256','').lower()==s['sha256'],io['number'](r.get('bytes'))==s['bytes'],r.get('status')=='verified',bool(rel)]
        p=root/'results'/rel if rel else root/'nonexistent-h038';copyok=bool(rel) and len(paths.get(rel,[]))==1 and p.is_file() and not p.is_symlink() and p.resolve().is_relative_to((root/'results/archive').resolve()) and io['digest'](p)==s['sha256']
        business.append(.4*sum(checks)/len(checks)+.6*float(copyok))
    actual_archive={unicodedata.normalize('NFC',p.relative_to(root/'results').as_posix()) for p in (root/'results/archive').rglob('*') if p.is_file() or p.is_symlink()} if (root/'results/archive').exists() and not(root/'results/archive').is_symlink() else set()
    extras=max(sum(len(rs) for k,rs in grouped.items() if k not in bykey),max(0,len(actual_archive)-60))
    business_score=sum(business)/(60+extras)
    actual={}
    for folder in ('source_tree','partial_archive'):
        if (root/folder).is_symlink():actual[folder]='SYMLINK';continue
        for p in (root/folder).rglob('*') if (root/folder).exists() else []:
            if p.is_file() and not p.is_symlink():actual[io['nfc'](p.relative_to(root).as_posix())]=io['digest'](p)
            elif p.is_symlink():actual[io['nfc'](p.relative_to(root).as_posix())]='SYMLINK'
    for name in ('state.json','manifest.tsv','operation_contract.md'):
        p=root/name
        if safe(p):actual[name]=io['digest'](p)
    preservation=actual==protected
    report_scores=[];file_records={};rfiles=report.get('files',[]) if report else [];rfiles=rfiles if isinstance(rfiles,list) else []
    for r in rfiles:
        if isinstance(r,dict) and isinstance(r.get('key'),str):file_records.setdefault(io['nfc'](r['key']),[]).append(r)
    for e in expected['recovery']['files']:
        rs=file_records.get(e['key'],[])
        if len(rs)!=1:report_scores.append(0.);continue
        r=rs[0];report_scores.append(sum([r.get('resolution')==e['resolution'],r.get('initial_copy_state')==e['initial_copy_state'],io['number'](r.get('initial_index_row_count'))==e['initial_index_row_count']])/3)
    initial=report.get('initial',{}) if report else {};initial=initial if isinstance(initial,dict) else {};final=report.get('final',{}) if report else {};final=final if isinstance(final,dict) else {}
    initial_score=sum(io['normalize'](initial.get(k),k)==io['normalize'](v,k) for k,v in expected['recovery']['initial'].items())/len(expected['recovery']['initial']);final_score=sum((final.get(k) is v if isinstance(v,bool) else io['normalize'](final.get(k),k)==io['normalize'](v,k)) for k,v in expected['recovery']['final'].items())/len(expected['recovery']['final'])
    report_truth=.6*sum(report_scores)/60+.3*initial_score+.1*final_score
    if preservation:
        probe=runpy.run_path(str(gt/'recovery_probe.py'))['probe'](root,expected,protected);replay_score=probe['score']
    else:
        # The known input-preservation error owns this failure; an invalid source
        # context cannot establish replay ability or cause a second deduction.
        p=Path(evidence)/('h038-probe-not-assessed-'+str(time.time_ns())+'.json');p.write_text(json.dumps({'status':'not_assessed_candidate_input_drift','candidate_content_tree_sha256':io['tree_sha'](root,True),'replay_ability':'unknown','root_error_owner':'delivery_integrity','neutral_dependent_opportunity':True}));replay_score=1.
    boundary=.3*report_truth+.7*replay_score
    integrity=.6*float(preservation)+.2*float(rows is not None)+.2*float(report is not None)
    bindings=[]
    for e in expected['recovery']['files']:
        rs=file_records.get(e['key'],[])
        if len(rs)!=1:continue
        r=rs[0];h=r.get('source_sha256');a=r.get('initial_archive_sha256','MISSING');bindings.append(isinstance(h,str) and h.lower()==e['source_sha256'] and (a is None if e['initial_archive_sha256'] is None else isinstance(a,str) and a.lower()==e['initial_archive_sha256']))
    input_hashes=report.get('input_sha256',{}) if report else {};input_hashes=input_hashes if isinstance(input_hashes,dict) else {};hashes=[isinstance(input_hashes.get(n),str) and input_hashes[n].lower()==h for n,h in protected.items()];evidence_score=.7*(sum(bindings)/len(bindings) if bindings else 0)+.3*sum(hashes)/len(hashes)
    scores={'business_correctness':business_score,'boundary_cases':boundary,'delivery_integrity':integrity,'evidence_binding':evidence_score};scores['overall_score']=sum(scores[k]*v for k,v in W.items());return scores
