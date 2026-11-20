from pathlib import Path
import hashlib,json,runpy,unicodedata
W={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def grade(**kwargs):
    root=Path(kwargs.get('workspace_path') or '/tmp_workspace');gt=root/'gt';trusted=json.loads((gt/'trusted_files.json').read_text())
    for name,h in trusted.items():
        p=gt/name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise RuntimeError('H037_TRUSTED_CONTEXT_MISSING_OR_DRIFT: '+name)
    io=runpy.run_path(str(gt/'native_io.py'));exp=json.loads((gt/'expected.json').read_text());protected=json.loads((gt/'protected_sha256.json').read_text());byid={r['member_id']:r for r in exp['members']}
    def safe(p):return p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
    audit=None;p=root/'results/extract_audit.json'
    try:
        if safe(p):
            a=io['read'](p)
            if isinstance(a,dict):audit=a
    except (ValueError,UnicodeError,OSError):pass
    rows=audit.get('members',[]) if audit else [];rows=rows if isinstance(rows,list) else []
    groups={};extras=0
    for r in rows:
        if isinstance(r,dict) and isinstance(r.get('member_id'),str):groups.setdefault(r['member_id'],[]).append(r)
        else:extras+=1
    extras+=sum(len(rs) for mid,rs in groups.items() if mid not in byid)
    valid={mid:rs[0] for mid,rs in groups.items() if mid in byid and len(rs)==1}
    business=[];variants={}
    for mid,e in byid.items():
        r=valid.get(mid)
        if r is None:business.append(0.);continue
        options=[e,*[{**e,**alt} for alt in e.get('allowed_alternatives',[])]]
        matches=[v for v in options if r.get('action')==v['action'] and r.get('reason_code')==v['reason_code']]
        match=next((v for v in matches if r.get('actual_state')==v['actual_state']),matches[0] if matches else None)
        variants[mid]=match or e
        business.append(.6*float(match is not None)+.4*float(io['path_value'](r.get('target_path'))==e['target_path']))
    bscore=sum(business)/(len(byid)+extras)
    actual={}
    for p in (root/'archives').rglob('*') if (root/'archives').exists() else []:
        if p.is_file() and not p.is_symlink():actual[unicodedata.normalize('NFC',p.relative_to(root).as_posix())]=hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_symlink():actual[unicodedata.normalize('NFC',p.relative_to(root).as_posix())]='SYMLINK'
    if safe(root/'extraction_policy.md'):actual['extraction_policy.md']=hashlib.sha256((root/'extraction_policy.md').read_bytes()).hexdigest()
    preservation=float(actual==protected)
    staging=root/'results/staging';actual_files={}
    if staging.is_dir() and not staging.is_symlink():
        for p in staging.rglob('*'):
            if p.is_file() or p.is_symlink():
                rel=unicodedata.normalize('NFC',p.relative_to(root/'results').as_posix());actual_files[rel]=hashlib.sha256(p.read_bytes()).hexdigest() if safe(p) else 'UNSAFE'
    physical=[actual_files.get(path)==h for path,h in exp['expected_files'].items()]
    for e in exp['members']:
        if e['action'] in ('directory','expand'):
            p=root/'results'/e['target_path'];physical.append(p.is_dir() and not p.is_symlink() and p.resolve().is_relative_to(staging.resolve()))
    extra_files=len(set(actual_files)-set(exp['expected_files']));pscore=sum(physical)/(len(physical)+extra_files)
    observations=[]
    for mid,r in valid.items():
        e=byid[mid];v=variants[mid]
        checks=[io['number'](r.get(k))==e[k] for k in ('member_index','depth','declared_bytes','compressed_bytes')]
        checks.append(r.get('actual_state')==v['actual_state'])
        checks.append(r.get('actual_bytes','MISSING') is None if v['actual_bytes'] is None else io['number'](r.get('actual_bytes'))==v['actual_bytes'])
        checks.append(r.get('sha256','MISSING') is None if v['sha256'] is None else io['hex_equal'](r.get('sha256'),v['sha256']))
        observations.append(sum(checks)/len(checks))
    uv=audit.get('unvisited_containers',[]) if audit else [];uv=uv if isinstance(uv,list) else []
    declared_uv={(r.get('member_id'),r.get('reason_code')) for r in uv if isinstance(r,dict) and isinstance(r.get('member_id'),str) and isinstance(r.get('reason_code'),str)}
    required_uv={(r['member_id'],r['reason_code']) for r in exp['unvisited_containers']}
    statechecks=[audit is not None and audit.get('executed') is False,declared_uv==required_uv]
    boundary=.60*pscore+.30*(sum(observations)/len(observations) if observations else 0)+.10*sum(statechecks)/2
    containment=not any(p.name not in {'archives','extraction_policy.md','results','gt'} for p in root.iterdir())
    if (root/'results').exists():containment=containment and not any(p.name not in {'staging','extract_audit.json'} for p in (root/'results').iterdir())
    integrity=.6*preservation+.2*float(audit is not None)+.2*float(containment)
    bindings=[]
    for mid,r in valid.items():
        e=byid[mid];checks=[r.get('container_id')==e['container_id'],io['path_value'](r.get('top_archive'),'source')==e['top_archive'],io['hex_equal'](r.get('archive_sha256'),e['archive_sha256']),io['hex_equal'](r.get('raw_name_hex'),e['raw_name_hex']),io['nfc'](r.get('decoded_name'))==e['decoded_name']]
        bindings.append(sum(checks)/len(checks))
    source_hashes=audit.get('input_sha256',{}) if audit else {};source_hashes=source_hashes if isinstance(source_hashes,dict) else {}
    source_bindings=[io['hex_equal'](source_hashes.get(n),h) for n,h in protected.items()]
    evidence=.8*(sum(bindings)/len(bindings) if bindings else 0)+.2*sum(source_bindings)/len(source_bindings)
    scores={'business_correctness':bscore,'boundary_cases':boundary,'delivery_integrity':integrity,'evidence_binding':evidence};scores['overall_score']=sum(scores[k]*v for k,v in W.items());return scores
