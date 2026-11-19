from pathlib import Path
import hashlib,json,os,runpy,unicodedata
W={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def grade(**kwargs):
    root=Path(kwargs.get('workspace_path') or '/tmp_workspace');gt=root/'gt';trusted=json.loads((gt/'trusted_files.json').read_text())
    for name,digest in trusted.items():
        p=gt/name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise RuntimeError('H039_TRUSTED_CONTEXT_MISSING_OR_DRIFT: '+name)
    io=runpy.run_path(str(gt/'native_io.py'));expected=json.loads((gt/'expected.json').read_text());oracle=json.loads((gt/'business_oracle.json').read_text());protected=json.loads((gt/'protected_sha256.json').read_text());restored=root/'results/restored';files={}
    baseline=json.loads((gt/'original_usability_evidence.json').read_text())
    if baseline.get('release_id')!=expected['release_id'] or not baseline.get('original_restored_unchanged') or len(baseline.get('cases',[]))!=7 or not all(c.get('passed') is True for c in baseline['cases']) or any(baseline['original_restored_sha256'].get(p)!=v['sha256'] for p,v in expected['expected_files'].items()):raise RuntimeError('H039_TRUSTED_ORIGINAL_USABILITY_EVIDENCE_INVALID')
    if restored.is_dir() and not restored.is_symlink() and restored.resolve().is_relative_to(root.resolve()):
        for p in restored.rglob('*'):
            if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(restored.resolve()):files[io['nfc'](p.relative_to(restored).as_posix())]=p.read_bytes()
    hashes={k:hashlib.sha256(v).hexdigest() for k,v in files.items()};hashset=set(hashes.values());audit=None;handoff=None;target_observations=[]
    def target_evidence(kind,identity,reported,expected_target,expected_sha):
        target=io['relative'](reported);actual_sha=hashes.get(target)
        if target is None:status='invalid_reported_target'
        elif actual_sha==expected_sha:status='verified_actual_target'
        elif target==expected_target:
            # The independently scored artifact is already missing/misplaced/
            # changed. Do not turn its canonical mapping into a second loss.
            # This is explicitly unknown, never a claim of target verification.
            status='not_assessed_artifact_mismatch'
        else:status='invalid_reported_target'
        target_observations.append({'kind':kind,'identity':identity,'reported_target':target,'expected_target':expected_target,'actual_sha256':actual_sha,'expected_sha256':expected_sha,'status':status})
        return status!='invalid_reported_target'
    def safe(p):return p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
    try:
        p=root/'results/restore_audit.json'
        if safe(p):
            a=io['read'](p)
            if isinstance(a,dict):audit=a
    except (ValueError,UnicodeError,OSError):pass
    try:
        p=root/'results/handoff.md'
        if safe(p):handoff=io['summary'](p)
    except (ValueError,UnicodeError,OSError):pass
    selected=audit.get('selected_parts',[]) if audit else [];selected=selected if isinstance(selected,list) else [];eligible=[]
    for spec in oracle['parts']:
        rs=[r for r in selected if isinstance(r,dict) and r.get('part_id')==spec['part_id']]
        eligible.append(len(rs)==1 and io['relative'](rs[0].get('path'),'input')==spec['path'] and isinstance(rs[0].get('sha256'),str) and rs[0]['sha256'].lower()==spec['sha256'])
    content=sum(h in hashset for h in oracle['release_payload_sha256'].values())/(40+max(0,len(files)-46));version_checks=[(audit or {}).get('release_id')==expected['release_id'],io['version']((audit or {}).get('version'))==io['version'](expected['version'])];business=.75*content+.25*(sum(eligible)+sum(version_checks))/5
    root_valid='index.html' in files
    notechecks=[]
    for name,h in oracle['notes_original_sha256'].items():
        target='user_notes/'+name
        # A single misplaced wrapper belongs to the layout opportunity. Preserve
        # independent credit for original bytes rather than charge it twice.
        notechecks.append(hashes.get(target)==h if root_valid else h in hashset)
    rows,errors=io['graph'](files);actual_edges={io['edge_key'](r) for r in rows if r['status']=='resolved'};required_edges=[]
    note_targets={'user_notes/'+n['path']:n['sha256'] for n in expected['notes']}
    for edge in expected['resources']:
        source=edge['source'];source_expected=expected['expected_files'][source]['sha256']
        if edge['target'] in note_targets and hashes.get(edge['target'])!=note_targets[edge['target']]:continue
        if hashes.get(source)==source_expected:required_edges.append(io['edge_key'](edge))
    original_kernel=all(hashes.get(p)==expected['expected_files'][p]['sha256'] for p in ('index.html','assets/js/app.js','assets/js/catalog-data.js'))
    placements=[{'release_path':p,'expected_target':expected['release_to_target'][p],'expected_sha256':h,'actual_sha256':hashes.get(expected['release_to_target'][p]),'status':'verified_position' if hashes.get(expected['release_to_target'][p])==h else 'invalid_position' if h in hashset else 'not_assessed_missing_original_bytes'} for p,h in oracle['release_payload_sha256'].items()]
    layout_ok=root_valid and original_kernel and all(p in files for p in expected['release_to_target'].values()) and all(k in actual_edges for k in required_edges) and all(r['status']!='invalid_position' for r in placements)
    # Broken references emitted only by changed-content sources are owned by
    # content/note byte checks; intact sources' local edges must all resolve.
    conflicts=audit.get('conflicts',[]) if audit else [];conflicts=conflicts if isinstance(conflicts,list) else [];cchecks=[]
    for e in expected['conflicts']:
        cchecks.append(any(isinstance(r,dict) and io['relative'](r.get('release_path'))==e['release_path'] and io['relative'](r.get('retained_user_path'))==e['retained_user_path'] and io['relative'](r.get('release_saved_as'))==e['release_saved_as'] and r.get('kind')==e['kind'] for r in conflicts))
    boundary=.4*float(all(notechecks))+.4*float(layout_ok)+.2*sum(cchecks)/2
    actual={}
    for folder in ('parts','existing_notes'):
        if (root/folder).is_symlink():actual[folder]='SYMLINK';continue
        for p in (root/folder).rglob('*') if (root/folder).exists() else []:
            if safe(p):actual[io['nfc'](p.relative_to(root).as_posix())]=hashlib.sha256(p.read_bytes()).hexdigest()
            elif p.is_symlink():actual[io['nfc'](p.relative_to(root).as_posix())]='SYMLINK'
    if safe(root/'release_manifest.json'):actual['release_manifest.json']=hashlib.sha256((root/'release_manifest.json').read_bytes()).hexdigest()
    summary_checks=[]
    for k,v in expected['summary'].items():summary_checks.append((io['number']((handoff or {}).get(k))==v) if isinstance(v,int) else (handoff or {}).get(k)==v)
    integrity=.6*float(actual==protected)+.15*float(audit is not None)+.10*float(bool(handoff))+.15*sum(summary_checks)/len(summary_checks)
    evidence=[];members=audit.get('members',[]) if audit else [];members=members if isinstance(members,list) else []
    for e in oracle['release_members']:
        rs=[r for r in members if isinstance(r,dict) and io['relative'](r.get('release_path'))==e['path']]
        if len(rs)!=1:evidence.append(False);continue
        r=rs[0];ids=r.get('part_ids',[]);ids={ids} if isinstance(ids,str) else set(x for x in ids if isinstance(x,str)) if isinstance(ids,list) else set();valid_ids={s['part_id'] for s in e['sources']};target_bound=target_evidence('release',e['path'],r.get('target_path'),expected['release_to_target'][e['path']],e['sha256']);evidence.append(isinstance(r.get('sha256'),str) and r['sha256'].lower()==e['sha256'] and io['number'](r.get('bytes'))==e['bytes'] and bool(ids) and ids<=valid_ids and target_bound)
    required={io['edge_key'](r) for r in expected['resources']};reported={io['edge_key'](r) for r in io['flatten']((audit or {}).get('resource_checks')) if r.get('status')=='resolved'};edge_binding=len(required&reported)/max(len(required|reported),1);input_hashes=(audit or {}).get('input_sha256',{});input_hashes=input_hashes if isinstance(input_hashes,dict) else {};inputs=sum(isinstance(input_hashes.get(k),str) and input_hashes[k].lower()==h for k,h in protected.items())/len(protected)
    old=oracle['old_archive'];excluded=(audit or {}).get('excluded_parts',[]);excluded=excluded if isinstance(excluded,list) else [];exclusion=any(isinstance(r,dict) and io['relative'](r.get('path'),'input')==old['path'] and r.get('release_id')==old['release_id'] and isinstance(r.get('reason'),str) and bool(r['reason'].strip()) for r in excluded)
    note_rows=(audit or {}).get('notes',[]);note_rows=note_rows if isinstance(note_rows,list) else [];note_bindings=[]
    for e in expected['notes']:
        rs=[r for r in note_rows if isinstance(r,dict) and io['relative'](r.get('source_path'),'input')=='existing_notes/'+e['path']]
        target_bound=target_evidence('note',e['path'],rs[0].get('target_path'),'user_notes/'+e['path'],e['sha256']) if len(rs)==1 else False
        note_bindings.append(len(rs)==1 and isinstance(rs[0].get('sha256'),str) and rs[0]['sha256'].lower()==e['sha256'] and io['number'](rs[0].get('bytes'))==e['bytes'] and target_bound)
    binding=.4*sum(evidence)/40+.2*sum(note_bindings)/6+.2*edge_binding+.1*inputs+.1*float(exclusion)
    observations={'schema_version':'h039.path-byte-target-binding/v2','candidate_code_executed':False,'placements':placements,'target_observations':target_observations,'neutrality':'Canonical reported targets with already-scored artifact mismatch are not_assessed, not verified; fabricated alternate targets are false.'}
    evidence_dir=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if evidence_dir:
        destination=Path(evidence_dir)/'path-byte-target-bindings.json';destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'h039_binding_observation_status_counts':{status:sum(r['status']==status for r in target_observations) for status in sorted({r['status'] for r in target_observations})},'candidate_code_executed':False},ensure_ascii=False))
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':integrity,'evidence_binding':binding};scores['overall_score']=sum(scores[k]*v for k,v in W.items());return scores
