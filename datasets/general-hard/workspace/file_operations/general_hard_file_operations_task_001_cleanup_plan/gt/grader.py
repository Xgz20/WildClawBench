"""H035 deterministic rules. Infrastructure failures intentionally propagate."""
from pathlib import Path
import hashlib, json, runpy, unicodedata

WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def grade(**kwargs):
    root=Path(kwargs.get('workspace_path') or '/tmp_workspace');gt=root/'gt'
    manifest=json.loads((gt/'trusted_files.json').read_text(encoding='utf-8'))
    for name,digest in manifest.items():
        p=gt/name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('H035_TRUSTED_CONTEXT_MISSING_OR_DRIFT: '+name)
    io=runpy.run_path(str(gt/'native_io.py'));read=io['read_json'];number=io['number'];npath=io['npath']
    oracle=read(gt/'business_oracle.json');expected=read(gt/'expected.json');protected=read(gt/'protected_sha256.json')
    byid={r['file_id']:r for r in expected['rows']};source={r['file_id']:r for r in oracle['files']};blocks=oracle['blocks']
    planpath=root/'results/cleanup_plan.json';reportpath=root/'results/report.md'
    def safe_file(p):return p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
    plan=None;report=None
    try:
        if safe_file(planpath):
            candidate=read(planpath)
            if isinstance(candidate,dict):plan=candidate
    except (ValueError,UnicodeError,OSError):pass
    try:
        if safe_file(reportpath):report=io['report_summary'](reportpath)
    except (ValueError,UnicodeError,OSError):pass
    actual={}
    tree=root/'sandbox_tree'
    if tree.exists():
        for p in tree.rglob('*'):
            if p.is_file() and not p.is_symlink():actual[unicodedata.normalize('NFC',p.relative_to(root).as_posix())]=hashlib.sha256(p.read_bytes()).hexdigest()
            elif p.is_symlink():actual[unicodedata.normalize('NFC',p.relative_to(root).as_posix())]='SYMLINK'
    for name in ('protection_rules.json','usage_snapshot.json'):
        p=root/name
        if safe_file(p):actual[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    protection=float(actual==protected)
    rows=plan.get('files',[]) if plan else []
    if not isinstance(rows,list):rows=[]
    grouped={}
    for row in rows:
        if isinstance(row,dict) and isinstance(row.get('file_id'),str):grouped.setdefault(row['file_id'],[]).append(row)
    valid={fid:vs[0] for fid,vs in grouped.items() if fid in byid and len(vs)==1}
    def located(fid,row):return npath(row.get('path'))==byid[fid]['path'] and row.get('sha256')==byid[fid]['sha256']
    # Each file is one opportunity. Missing/duplicate/wrong identity consumes that opportunity once.
    business=[]
    for fid,exp in byid.items():
        row=valid.get(fid)
        if not row or not located(fid,row):business.append(0.);continue
        occupancy=(number(row.get('allocated_known_bytes'))==exp['allocated_known_bytes'] and row.get('allocation_complete') is exp['allocation_complete'])
        business.append(.25+.45*float(io['decision'](row.get('decision'))==exp['decision'])+.30*float(occupancy))
    extras=sum(len(vs) for fid,vs in grouped.items() if fid not in byid)+sum(not isinstance(r,dict) or not isinstance(r.get('file_id'),str) for r in rows)
    business_score=sum(business)/(80+extras)
    if not plan:
        boundary=0.;evidence=0.
    else:
        summary=plan.get('summary',{});summary=summary if isinstance(summary,dict) else {}
        declared_clean={fid for fid,row in valid.items() if io['decision'](row.get('decision'))=='cleanable'}
        selected_blocks=[b for b in blocks if set(b['holders'])<=declared_clean and not b['external_pin']]
        releasable=None if any(b['bytes'] is None for b in selected_blocks) else sum(b['bytes'] for b in selected_blocks)
        complete_inventory=len(rows)==80 and len(valid)==80
        correct_classes=complete_inventory and all(io['decision'](valid[fid].get('decision'))==exp['decision'] for fid,exp in byid.items())
        # Dependent opportunities are neutral when upstream inventory/classification
        # is wrong. Their root error belongs to business, not a second deduction.
        release_ok=(summary.get('cleanable_set_freeable_bytes','MISSING') is None if releasable is None else number(summary.get('cleanable_set_freeable_bytes'))==releasable) if correct_classes else True
        numeric=[number(summary.get('file_count'))==80 if complete_inventory else True,number(summary.get('known_allocated_union_bytes'))==expected['summary']['known_allocated_union_bytes'],number(summary.get('unknown_block_count'))==expected['summary']['unknown_block_count'],release_ok]
        # Singleton arithmetic is evaluated only on delivered correctly located rows, so omission is not charged twice.
        alone=[]
        for fid,row in valid.items():
            if not located(fid,row):continue
            exp=byid[fid]['freeable_if_alone_bytes']
            alone.append(row.get('freeable_if_alone_bytes','MISSING') is None if exp is None else number(row.get('freeable_if_alone_bytes'))==exp)
        states=[io['pending'](plan.get('confirmation')),plan.get('executed') is False,plan.get('selected_file_ids')==[],io['pending'](summary.get('confirmation')),summary.get('executed') is False]
        links=[]
        for fid,row in valid.items():
            if source[fid]['role']=='external_shortcut' and located(fid,row):links.append(row.get('follow_target') is False and row.get('target_allocated_bytes','MISSING') is None)
        boundary=.5*sum(numeric)/4+.2*(sum(alone)/len(alone) if alone else 0)+.2*sum(states)/len(states)+.1*(sum(links)/len(links) if links else 0)
        ev=[]
        for fid,row in valid.items():
            if not located(fid,row):continue
            e=row.get('evidence',{});e=e if isinstance(e,dict) else {}
            ev.append(e.get('usage_file_id')==fid and e.get('rule_id')==byid[fid]['rule_id'])
        hashes=plan.get('input_sha256',{});hashes=hashes if isinstance(hashes,dict) else {}
        bindings=[hashes.get(n)==protected[n] for n in ('protection_rules.json','usage_snapshot.json')]
        evidence=.7*(sum(ev)/len(ev) if ev else 0)+.2*sum(bindings)/2+.1*float(plan.get('snapshot_id')==oracle['rules']['snapshot_id'])
    usable_plan=float(plan is not None);usable_report=float(bool(report) and safe_file(reportpath))
    consistency=0.
    if report:
        # The report owns its factual mirror opportunity. A wrong plan number
        # is charged by boundary only; a correct report is not charged again.
        summary=expected['summary']
        facts=[]
        for key in ('file_count','known_allocated_union_bytes','unknown_block_count','cleanable_set_freeable_bytes'):
            a,b=summary.get(key,'MISSING'),report.get(key,'MISSING')
            facts.append(a is None and b in (None,'unknown','未知') or number(a) is not None and number(a)==number(b))
        facts += [io['pending'](report.get('confirmation'))==io['pending'](summary.get('confirmation')) and 'confirmation' in report and 'confirmation' in summary, report.get('executed') is summary.get('executed') and 'executed' in report and 'executed' in summary]
        consistency=sum(facts)/len(facts)
    integrity=.5*protection+.2*usable_plan+.15*usable_report+.15*consistency
    scores={'business_correctness':business_score,'boundary_cases':boundary,'delivery_integrity':integrity,'evidence_binding':evidence}
    scores['overall_score']=sum(scores[k]*v for k,v in WEIGHTS.items())
    return scores
