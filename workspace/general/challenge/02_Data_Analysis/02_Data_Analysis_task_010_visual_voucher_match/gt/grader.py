"""H026 frozen-source four-component automatic check; semantic meaning is separate."""
from pathlib import Path
from collections import defaultdict
import csv,hashlib,json,os,runpy


def grade(workspace):
    root=Path(workspace).resolve();gt=root/'gt'
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    load=lambda n:json.loads((gt/n).read_text(encoding='utf-8'))
    mean=lambda xs:sum(xs)/len(xs) if xs else 0.
    contract=load('scoring_contract.json')
    if sha(gt/'grader.py')!=contract['grading_source_sha256']:raise ValueError('H026 grader source drift')
    for name,want in contract['private_sha256'].items():
        if sha(gt/name)!=want:raise ValueError('H026 private scoring drift '+name)
    oracle=load('expected.json');protected=load('protected_sha256.json');regions=load('visual_regions.json');reconciliation=load('annotation_reconciliation.json')
    if (oracle.get('status')!='APPROVED_AFTER_TWO_INDEPENDENT_MODEL_READS' or reconciliation.get('open_annotation_issues') not in (0,[]) or
        len(oracle['images'])!=12 or len(oracle['voucher_groups'])!=9 or len(oracle['ledger_decisions'])!=18 or len(oracle['proposals'])!=7 or
        len(protected)!=14 or oracle['source_sha256']!=protected or oracle['annotation_reconciliation_sha256']!=sha(gt/'annotation_reconciliation.json')):
        raise ValueError('H026 missing, incomplete or inconsistent accepted source truth')
    io=runpy.run_path(str(gt/'voucher_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'))
    for name in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(name):raise RuntimeError('H026 missing managed runtime '+name)
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text(encoding='utf-8'));office['validate_office_lock'](lock)
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H026 derived evidence must be outside frozen Workspace')
    intact=all((root/name).is_file() and not(root/name).is_symlink() and sha(root/name)==want for name,want in protected.items())
    errors={};native=None;book=None;proposal_doc=None;visual_doc=None;inventory=None
    def candidate(name):
        p=root/'results'/name
        if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=5*1024*1024:raise io['CandidateError']('missing, empty or oversized '+name)
        return p
    def attempt(label,action):
        try:return action()
        except (io['CandidateError'],UnicodeError) as exc:errors[label]=str(exc);return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[label]=exc.code;return None
    def write_report(scores,details):
        report={'schema_version':'h026-voucher-rule-analysis/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'office_baseline':native,'details':details,'semantic_meaning_checked':False,'human_expert_review':False,'formula_count_threshold':None,'candidate_input_response_required':False,'limits':['Automatic result uses reconciled source fields, exact economic keys, row actions, pending and approval flags.','Visual evidence score is mechanical SHA/dimension/region binding; meaningful observations and stamp relationships require the separate semantic Judge.','Pending current book amounts are retained for measurement, not confirmed expenses or applied adjustments.']}
        derived.mkdir(parents=True,exist_ok=True)
        with (derived/'h026-analysis.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
        return scores
    if not intact:
        return write_report({k:0. for k in [*contract['weights'],'overall_score']},{'reason':'one or more of the14 protected inputs changed or missing; every automatic component is zero'})
    def workbook():
        nonlocal native
        native=office['recalculate_xlsx'](candidate('voucher_match.xlsx'),lock,derived/'baseline',timeout_seconds=120)
        result=io['read_book'](native['path'])
        if any(e['error'] in {'#NAME?','#SPILL!','#CALC!'} for s in result for e in s['errors']):
            raise RuntimeError('H026 formula-engine compatibility needs review; never convert to candidate ability zero')
        return result
    book=attempt('workbook',workbook)
    proposal_doc=attempt('adjustment_proposal',lambda:io['read_json'](candidate('adjustment_proposal.json')))
    visual_doc=attempt('visual_evidence',lambda:io['read_json'](candidate('visual_evidence.json')))
    tables={kind:io['tables'](book,kind) if book else [] for kind in ['images','ledger','groups','summary']}
    if book:
        source=list(csv.DictReader((root/'ledger.csv').read_text(encoding='utf-8-sig').splitlines()))
        if len(source)!=18:raise ValueError('H026 protected source ledger count contradiction')
        inventory=io['source_inventory'](book,source)
    image_by=defaultdict(list);ledger_by=defaultdict(list);group_by=defaultdict(list)
    for row in tables['images']:image_by[io['file_name'](row['file'])].append(row)
    for row in tables['ledger']:ledger_by[io['text'](row['entry_id'])].append(row)
    for row in tables['groups']:group_by[io['key'](row)].append(row)
    expected_images={r['file']:r for r in oracle['images']};expected_ledger={r['entry_id']:r for r in oracle['ledger_decisions']};expected_groups={io['key'](r):r for r in oracle['voucher_groups']}
    checks={'images':{},'ledger':{},'groups':{},'summary':{},'proposals':{},'pending_items':{}}
    def singleton(by,k):
        rows=by.get(k,[])
        return rows[0] if len(rows)==1 and rows[0].get('_visible',True) else {}
    def equivalent(a,b,field,date1904=False):
        if field in {'printed_amount','handwritten_amount','ledger_amount','target_amount','proposed_delta','effective_amount','delta_amount'}:
            return io['money'](a)==io['money'](b) and (not io['null'](a) if b is not None else io['null'](a))
        if field in {'has_handwritten_correction','approval_crossed_out'}:return io['boolean'](a) is b
        if field=='business_date':return io['date_value'](a,date1904)==b
        if field in {'direction','status_selection','approval_location','correction_status','scope_status','match_status','action','state'}:return io['enum'](a,field)==io['enum'](b,field)
        return io['text'](a)==io['text'](b)
    image_correct={}
    for filename,want in expected_images.items():
        row=singleton(image_by,filename)
        own={field:equivalent(row.get(field),want[field],field,row.get('_date1904',False)) for field in io['FIELDS']['images'] if field!='file'}
        own['unique_visible']=bool(row);checks['images'][filename]=own;image_correct[filename]=all(own.values())
    ledger_correct={}
    for eid,want in expected_ledger.items():
        row=singleton(ledger_by,eid)
        own={field:equivalent(row.get(field),want['amount'] if field=='ledger_amount' else want[field],field,row.get('_date1904',False)) for field in [*io['KEY_FIELDS'],'ledger_amount','scope_status','match_status','canonical_entry_id','action','target_amount','proposed_delta']}
        actual_files=io['source_files'](row.get('source_files'));expected_files=sorted(want['voucher_files'])
        if want['scope_status']!='eligible':
            # Excluded rows may cite only same-five-field-key images for audit.
            allowed={im['file'] for im in oracle['images'] if io['key'](im)==io['key'](want)}
            own['source_files']=actual_files is not None and set(actual_files)<=allowed
        else:own['source_files']=actual_files==expected_files
        own['unique_visible']=bool(row);checks['ledger'][eid]=own;ledger_correct[eid]=all(own.values())
    group_correct={}
    for k,want in expected_groups.items():
        row=singleton(group_by,k)
        own={field:equivalent(row.get(field),want[field],field) for field in ['state','effective_amount','canonical_entry_id']}
        if want['state']=='void':own['effective_amount']=io['null'](row.get('effective_amount')) or io['money'](row.get('effective_amount'))=='0.00'
        own['source_files']=io['source_files'](row.get('source_files'))==sorted(want['voucher_files']);own['unique_visible']=bool(row)
        checks['groups']['|'.join(k)]=own;group_correct[k]=all(own.values())
    workbook_summary,summary_unique=io['summary_values'](tables['summary'])
    checks['summary']['workbook']=io['summary_checks'](workbook_summary,oracle['summary'])
    json_summary=proposal_doc.get('summary',{}) if proposal_doc else {}
    checks['summary']['json']=io['summary_checks'](json_summary,oracle['summary'])
    actual_proposals=proposal_doc.get('proposals',[]) if proposal_doc else []
    if not isinstance(actual_proposals,list):actual_proposals=[]
    proposal_by=defaultdict(list)
    def proposal_id(row):return (io['text'](row.get('entry_id')),io['key'](row),io['enum'](row.get('action')))
    for row in actual_proposals:
        if isinstance(row,dict):proposal_by[proposal_id(row)].append(row)
    proposal_correct={}
    for want in oracle['proposals']:
        pid=proposal_id(want);rows=proposal_by.get(pid,[]);row=rows[0] if len(rows)==1 else {}
        own={'unique':len(rows)==1 and 'entry_id' in row,'delta_amount':equivalent(row.get('delta_amount'),want['delta_amount'],'delta_amount'),'target_amount':equivalent(row.get('target_amount'),want['target_amount'],'target_amount'),'source_files':io['source_files'](row.get('source_files'))==sorted(want['source_files']),'approval_flags':io['approval_ok'](row)}
        checks['proposals'][str(pid)]=own;proposal_correct[pid]=all(own.values())
    exact_proposals=(len(actual_proposals)==7 and len(proposal_by)==7 and all(proposal_correct.values()))
    expected_pending=[]
    for row in oracle['ledger_decisions']:
        if row['action']=='hold':expected_pending.append({'kind':'ledger_hold','entry_id':row['entry_id'],'key':{f:row[f] for f in io['KEY_FIELDS']},'source_files':row['voucher_files']})
    for row in oracle['voucher_groups']:
        if row['state']=='pending' and not row['eligible_entry_ids']:expected_pending.append({'kind':'unbooked_pending','entry_id':None,'key':{f:row[f] for f in io['KEY_FIELDS']},'source_files':row['voucher_files']})
    actual_pending=proposal_doc.get('pending_items',[]) if proposal_doc else []
    if not isinstance(actual_pending,list):actual_pending=[]
    pending_by=defaultdict(list)
    def pending_id(row):return io['text'](row.get('entry_id')),io['key'](row)
    for row in actual_pending:
        if isinstance(row,dict):pending_by[pending_id(row)].append(row)
    for want in expected_pending:
        pid=pending_id(want);rows=pending_by.get(pid,[]);row=rows[0] if len(rows)==1 else {};kind=row.get('kind',row.get('type',want['kind']))
        checks['pending_items'][str(pid)]=len(rows)==1 and 'entry_id' in row and (not ('kind' in row and 'type' in row) or io['enum'](row['kind'])==io['enum'](row['type'])) and io['enum'](kind)==want['kind'] and io['source_files'](row.get('source_files'))==sorted(want['source_files']) and isinstance(row.get('reason'),str) and bool(row['reason'].strip())
    exact_pending=len(actual_pending)==5 and len(pending_by)==5 and all(checks['pending_items'].values())
    proposal_score=.75*mean(list(proposal_correct.values()))+.25*mean(list(checks['pending_items'].values()))
    # Extra/duplicate money or pending items are not erased by a mean over only the oracle rows.
    if len(actual_proposals)!=7 or len(proposal_by)!=7:proposal_score*=min(1.,7/max(len(actual_proposals),len(proposal_by),7))*.5
    if len(actual_pending)!=5 or len(pending_by)!=5:proposal_score*=.75
    top_approval=io['approval_ok'](proposal_doc)
    if not top_approval:proposal_score*=.5
    shape_checks={kind:set(by)==set(expected) and all(len(rows)==1 and rows[0]['_visible'] for rows in by.values()) for kind,by,expected in [('images',image_by,expected_images),('ledger',ledger_by,expected_ledger),('groups',group_by,expected_groups)]}
    for kind in ['ledger','groups']:shape_checks[kind+'_reasons']=bool(tables[kind]) and all(isinstance(row.get('reason'),str) and row['reason'].strip() for row in tables[kind])
    shape_checks['summary']=summary_unique and all(k in workbook_summary for k in io['CORE_SUMMARY'])
    json_structure=bool(proposal_doc and top_approval and len(actual_proposals)==7 and all(isinstance(p,dict) and all(f in p for f in ['action','entry_id','delta_amount','target_amount','source_files','reason']) and io['key'](p) and io['approval_ok'](p) and isinstance(p['reason'],str) and p['reason'].strip() for p in actual_proposals) and len(actual_pending)==5 and all(isinstance(p,dict) and 'entry_id' in p and io['key'](p) and 'source_files' in p and (not ('kind' in p and 'type' in p) or io['enum'](p['kind'])==io['enum'](p['type'])) and isinstance(p.get('reason'),str) and p['reason'].strip() for p in actual_pending) and all(k in json_summary for k in io['CORE_SUMMARY']))
    visual=io['visual_binding'](visual_doc,regions)
    unsafe=io['unsafe_claims'](proposal_doc or {})+io['unsafe_claims'](workbook_summary)
    image_score=mean(list(image_correct.values()));ledger_score=mean(list(ledger_correct.values()));group_score=mean(list(group_correct.values()));summary_score=mean([*checks['summary']['workbook'].values(),*checks['summary']['json'].values()])
    # Complete record identities are required; extras cannot be hidden behind correct expected subsets.
    if not shape_checks['images']:image_score*=.5
    if not shape_checks['ledger']:ledger_score*=.5
    if not shape_checks['groups']:group_score*=.5
    business=.25*image_score+.35*ledger_score+.10*group_score+.05*summary_score+.25*proposal_score
    def imgs(*ns):return all(image_correct[f'vouchers/voucher_{n:02d}.png'] for n in ns)
    def led(*ids):return all(ledger_correct['L'+str(n).zfill(3)] for n in ids)
    def grp(cp):return all(v for k,v in group_correct.items() if k[1]==cp) and any(k[1]==cp for k in group_correct)
    def prop(*ids):return all(all(proposal_correct.get(proposal_id(p),False) for p in oracle['proposals'] if p['entry_id']==eid) for eid in ids)
    pending_summary=all(checks['summary'][surface][field] for surface in ['workbook','json'] for field in ['unresolved_book_amount','unresolved_entry_count','unbooked_pending_group_count'])
    boundaries={
      'void_priority':imgs(1,2) and grp('CP-001') and led(1,2) and prop('L001','L002'),
      'duplicate_copies_and_unbooked_create':imgs(3,4,11) and grp('CP-002') and grp('CP-007') and led(3,4) and prop('L004',None),
      'local_correction_and_first_posted':imgs(5,6) and grp('CP-003') and led(6,7) and prop('L006','L007'),
      'O0_identity_and_unmatched':imgs(7,8) and grp('CP-004') and led(9,10,16),
      'pending_and_cross_counterparty':imgs(9,12) and grp('CP-005') and grp('CP-013') and led(11,12,15) and exact_pending and pending_summary,
      'real_zero_and_timestamp':imgs(10) and grp('CP-006') and led(13,14) and prop('L013'),
      'scope_exclusions':led(5,8,17,18) and not any(isinstance(p,dict) and p.get('entry_id') in {'L005','L008','L017','L018'} for p in actual_proposals),
      'approval_pending_not_applied':top_approval and exact_proposals and exact_pending and not unsafe}
    boundary=mean(list(boundaries.values()))
    delivery=.25*float(book is not None and not any(s['errors'] for s in book))+.25*float(all(shape_checks.values()) and inventory is not None and inventory['complete'])+.25*float(json_structure)+.25*float(visual['complete'])
    evidence=visual['score']
    if unsafe:
        business=min(business,.25);delivery=0.;boundaries['approval_pending_not_applied']=False;boundary=mean(list(boundaries.values()))
    scores={k:round(v,12) for k,v in {'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence}.items()}
    scores['overall_score']=round(sum(scores[k]*weight for k,weight in contract['weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H026 automatic score out of range')
    return write_report(scores,{'table_counts':{k:len(v) for k,v in tables.items()},'record_correctness':{'images':image_correct,'ledger':ledger_correct,'groups':{'|'.join(k):v for k,v in group_correct.items()}},'checks':checks,'shape_checks':shape_checks,'raw_inventory':inventory,'component_scores':{'images':image_score,'ledger':ledger_score,'groups':group_score,'summary':summary_score,'proposals_and_pending':proposal_score},'boundary_groups':boundaries,'proposal_count':len(actual_proposals),'pending_item_count':len(actual_pending),'json_structure':json_structure,'unsafe_claim_paths':unsafe,'visual_binding':visual})
