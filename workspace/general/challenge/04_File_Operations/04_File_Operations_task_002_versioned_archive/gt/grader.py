"""H036 automated rules; candidate errors score, missing trusted context raises."""
from pathlib import Path
import hashlib,json,runpy,unicodedata
W={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def grade(**kwargs):
    root=Path(kwargs.get('workspace_path') or '/tmp_workspace');gt=root/'gt'
    trusted=json.loads((gt/'trusted_files.json').read_text())
    for name,h in trusted.items():
        p=gt/name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise RuntimeError('H036_TRUSTED_CONTEXT_MISSING_OR_DRIFT: '+name)
    helper=runpy.run_path(str(gt/'native_io.py'));exp=json.loads((gt/'expected.json').read_text());protected=json.loads((gt/'protected_sha256.json').read_text());byid={r['source_id']:r for r in exp['rows']}
    def safe(p):
        return p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
    rows=None;exceptions=None
    try:
        if safe(root/'results/manifest.csv'):rows=helper['manifest'](root/'results/manifest.csv')
    except (ValueError,UnicodeError,OSError,csv_error()):pass
    try:
        if safe(root/'results/exceptions.md'):exceptions=helper['exception_records'](root/'results/exceptions.md')
    except (ValueError,UnicodeError,OSError):pass
    grouped={}
    for row in rows or []:grouped.setdefault(row.get('source_id',''),[]).append(row)
    valid={sid:rs[0] for sid,rs in grouped.items() if sid in byid and len(rs)==1}
    def meta_checks(row,e):
        return [helper['normalize'](row.get('business_area'))==e['business_area'],helper['normalize'](row.get('document_id'))==e['document_id'],helper['version'](row.get('version'))==helper['version'](e['version']),row.get('state')==e['state'],helper['instant'](row.get('issued_at'))==helper['instant'](e['issued_at']),row.get('reason_code')==e['reason_code']]
    business=[]
    for sid,e in byid.items():
        row=valid.get(sid)
        if row is None:business.append(0.);continue
        if e['selection']=='unknown':checks=[helper['unknown'](row.get(k)) for k in ('business_area','document_id','version','state','issued_at')]+[row.get('reason_code')==e['reason_code']]
        else:checks=meta_checks(row,e)
        business.append(.5*sum(checks)/len(checks)+.5*float(row.get('selection')==e['selection']))
    extras=sum(len(rs) for sid,rs in grouped.items() if sid not in byid)
    bscore=sum(business)/(48+extras)
    actual={}
    for p in (root/'incoming').rglob('*') if (root/'incoming').exists() else []:
        if p.is_file() and not p.is_symlink():actual[unicodedata.normalize('NFC',p.relative_to(root).as_posix())]=hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_symlink():actual[unicodedata.normalize('NFC',p.relative_to(root).as_posix())]='SYMLINK'
    for name in ('filing_rules.md','protected.json'):
        p=root/name
        if safe(p):actual[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    preservation=float(actual==protected)
    archive=root/'results/archive';filemap={};hashpaths={}
    if archive.is_dir() and not archive.is_symlink():
        for p in archive.rglob('*'):
            if p.is_file() or p.is_symlink():
                rel=unicodedata.normalize('NFC',p.relative_to(root/'results').as_posix());h=hashlib.sha256(p.read_bytes()).hexdigest() if safe(p) else 'UNSAFE'
                filemap[rel]=h;hashpaths.setdefault(h,[]).append(rel)
    semantic_parents={}
    for sid,row in valid.items():
        rel=helper['path_value'](row.get('archive_path'),'archive')
        if rel:
            semantic_parents.setdefault(str(Path(rel).parent),set()).add((byid[sid]['business_area'],byid[sid]['selection']))
    expected_groups={}
    for e in exp['rows']:expected_groups.setdefault(e['sha256'],[]).append(e['source_id'])
    physical=[]
    for h,sids in expected_groups.items():
        # One independent content opportunity; a missing manifest row is owned
        # by business and does not by itself fail an existing correct archive.
        paths=hashpaths.get(h,[]);ok=len(paths)==1
        delivered=[valid[sid] for sid in sids if sid in valid]
        if delivered:
            declared=[helper['path_value'](r.get('archive_path'),'archive') for r in delivered]
            ok=ok and all(p in paths for p in declared)
            if len(delivered)==len(sids):
                primaries=[r['source_id'] for r in delivered if not r.get('duplicate_of')]
                ok=ok and len(primaries)==1 and all(not r.get('duplicate_of') if r['source_id'] in primaries else r.get('duplicate_of') in primaries for r in delivered)
            ok=ok and all(len(semantic_parents.get(str(Path(p).parent),set()))==1 for p in declared if p)
        physical.append(float(ok))
    unexpected=sum(len(ps) for h,ps in hashpaths.items() if h not in expected_groups)
    archive_score=sum(physical)/(33+unexpected)
    typechecks=[row.get('detected_format')==byid[sid]['detected_format'] for sid,row in valid.items()]
    exception_pairs=set();false_pairs=set();required={tuple(p) for p in exp['exception_pairs']}
    for r in exceptions or []:
        kind=r.get('kind');detail=r.get('detail');source_ids=helper['ids'](r.get('source_ids'))
        if not isinstance(kind,str) or not isinstance(detail,str) or not detail.strip():continue
        for sid in source_ids:
            pair=(kind,sid)
            if pair in required:exception_pairs.add(pair)
            elif kind in {'extension_mismatch','name_collision','version_conflict','unknown_item'}:false_pairs.add(pair)
    exception_score=len(exception_pairs)/(len(required)+len(false_pairs))
    boundary=.65*archive_score+.15*(sum(typechecks)/len(typechecks) if typechecks else 0)+.20*exception_score
    integrity=.6*preservation+.2*float(rows is not None)+.2*float(exceptions is not None and bool(exceptions))
    bindings=[]
    for sid,row in valid.items():
        e=byid[sid];bindings.append(helper['path_value'](row.get('source_path'),'source')==e['source_path'] and isinstance(row.get('sha256'),str) and row['sha256'].lower()==e['sha256'])
    evidence=sum(bindings)/len(bindings) if bindings else 0.
    scores={'business_correctness':bscore,'boundary_cases':boundary,'delivery_integrity':integrity,'evidence_binding':evidence};scores['overall_score']=sum(scores[k]*v for k,v in W.items());return scores
def csv_error():
    import csv
    return csv.Error
