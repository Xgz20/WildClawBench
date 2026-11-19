"""H012 native business checks with retained independent visual GT and explicit infrastructure errors."""
from pathlib import Path
import hashlib,json,os,re,runpy
import pdfplumber
from pypdf import PdfReader
def private(p):return json.loads(Path(p).read_text())
def grade(root):
    root=Path(root).resolve();gt=root/'gt'
    expected=private(gt/'expected.json');gate=private(gt/'annotation_status.json');visual=private(gt/'visual_regions.json')
    contract=private(gt/'artifact_contract.json');oracle=private(gt/'business_oracle.json');protected=private(gt/'protected_sha256.json')
    boundaries_contract=private(gt/'counterexamples.json');evidence_contract=private(gt/'evidence_requirements.json')
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    if (expected['status']!='approved_after_two_blind_model_reviews' or expected['source_sha256']!=protected
        or sha(gt/'expected.json')!=oracle['expected_sha256'] or sha(gt/'annotation_status.json')!=expected['annotation_status_sha256']
        or gate['status']!='approved' or gate['received_reviewers']!=2 or gate['human_expert_review'] is not False
        or sha(gt/'reviews/reconciliation.json')!=gate['reconciliation_sha256'] or sha(gt/'visual_regions.json')!=gate['visual_regions_sha256']
        or visual['status']!='approved' or gate['input_sha256']!=protected or not evidence_contract['required_observations']):
        raise ValueError('H012 private annotation/oracle binding mismatch')
    reviewers=gate['reviewers']
    if len(reviewers)!=2 or len({r['reviewer_id'] for r in reviewers})!=2 or len({r['path'] for r in reviewers})!=2:raise ValueError('H012 requires two retained reviewers')
    for reviewer in reviewers:
        p=gt/reviewer['path']
        if p.is_symlink() or gt.resolve() not in p.resolve().parents or sha(p)!=reviewer['sha256']:raise ValueError('H012 raw review binding mismatch')
        record=private(p)
        if record['review_type']!='independent_model_review' or record['human_expert'] is not False or record['input_sha256']!=protected:raise ValueError('H012 review scope mismatch')
        images=record['actual_images_viewed']
        if len(images)!=5 or {v['file'] for v in images}!={k for k in protected if k.endswith('.png')}:raise ValueError('H012 actual image coverage incomplete')
        if any(v['viewed'] is not True or v['sha256']!=protected[v['file']] for v in images):raise ValueError('H012 actual image binding mismatch')
        if len(record['records'])!=17 or {r['revision_id'] for r in record['records']}!={f'R{i:02d}' for i in range(1,18)}:raise ValueError('H012 review coverage incomplete')
    for file,digest in contract['private_helper_sha256'].items():
        if sha(gt/file)!=digest:raise ValueError('H012 private helper drift: '+file)
    io=runpy.run_path(str(gt/'structured_io.py'));mean=io['mean'];canon=io['canon'];office=io['OFFICE']
    cases={c['revision_id']:c for c in expected['cases']};regions={r['revision_id']:r for r in visual['regions']}
    if set(cases)!=set(regions) or len(cases)!=17:raise ValueError('H012 private task coverage mismatch')
    for k in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_RULE_EVIDENCE_DIR']:
        if not os.environ.get(k):raise RuntimeError('H012 managed runtime requirement missing: '+k)
    lock=private(os.environ['GENERAL_E2E_OFFICE_LOCK']);render_lock=private(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK'])
    office['validate_office_lock'](lock);office['validate_office_render_lock'](render_lock)
    if 'docx' not in office['office_render_lock_formats'](render_lock) or render_lock['office_runtime']!=lock:raise RuntimeError('H012 requires matching Word rendering lock')
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if derived==root or root in derived.parents:raise RuntimeError('H012 derived evidence must remain outside frozen Workspace')
    intact=all((root/k).is_file() and not (root/k).is_symlink() and sha(root/k)==v for k,v in protected.items())
    errors={};objects={};matrix={};uncertain={};meta={};sections={};render=None;recalculation=None
    def attempt(name,action):
        try:return action()
        except io['CandidateError'] as e:errors[name]=str(e);return None
        except office['OfficeRuntimeError'] as e:
            if e.code not in io['CONTENT_ERRORS']:raise
            errors[name]=e.code;return None
    def matrix_read():
        nonlocal recalculation
        path=root/contract['files']['matrix'];book=io['workbook'](path)
        if any(c.get('formula') for rows in book['rows'].values() for cells in rows.values() for c in cells.values()):
            recalculation=office['recalculate_xlsx'](path,lock,derived/'matrix-recalculation');path=Path(recalculation['path'])
        return io['matrix'](path,contract)
    found=attempt('matrix',matrix_read);objects['matrix']=found is not None
    if found:matrix,meta=found
    value=attempt('uncertain',lambda:io['load_json'](root/contract['files']['uncertain']));objects['uncertain']=value is not None
    uncertain,unique=io['list_records'](value)
    model=attempt('document',lambda:io['word'](root/contract['files']['document']));objects['document']=model is not None
    if model:sections=io['document_sections'](model)
    def word_render():
        receipt=office['render_docx_pdf'](root/contract['files']['document'],render_lock,derived/'document-render',timeout_seconds=90)
        pages=[];outside=[];chars=[]
        with pdfplumber.open(receipt['path']) as pdf:
            for number,page in enumerate(pdf.pages,1):
                pages.append(page.extract_text() or '')
                for c in page.chars:
                    if not c['text'].strip():continue
                    if c['x0']<-.75 or c['x1']>page.width+.75 or c['top']<-.75 or c['bottom']>page.height+.75:outside.append({'page':number,'text':c['text']})
                    else:chars.append(c['text'])
        text=canon(''.join(chars));native=[p['text'] for p in model['paragraphs'] if canon(p['text'])]
        visible=[canon(t) in text for t in native]
        return {'pdf':str(receipt['path']),'receipt':receipt['audit'],'page_count':len(PdfReader(receipt['path']).pages),
            'native_text_visible':visible,'missing_native_text':[v for v,ok in zip(native,visible) if not ok],
            'out_of_page':outside[:30],'basic_fit':bool(visible and all(visible) and not outside),'pages_text':pages,
            'limit':'Bound PDF text/page bounds only. Full visual readability and actual image interpretation require independent Judge.'}
    if model:render=attempt('document_render',word_render)
    def find_doc(identity,section):
        c=cases[identity]
        return [row for row in sections.get(section,[]) if re.search(r'\b'+c['clause_id']+r'\b',row['text'],re.I)]
    def text_ok(v,c,field):
        if field=='proposed_text' and c['revision_id']=='R04':
            return io['blank'](v) or (not re.search(r'\d',io['clean'](v)) and ('unknown' in canon(v) or any(t in io['clean'](v) for t in ['未知','不清','不可','…','?'])))
        return io['business_text'](v,c[field],contract['text_anchors'][c['revision_id']+':'+field])
    def condition_ok(v,c):
        if c['revision_id']=='R16':return io['blank'](v) or any(t in canon(v) for t in ['unknown','未知','不清','不可判读','未决'])
        if not c['condition']:return io['blank'](v)
        return io['business_text'](v,c['condition'],oracle['condition_anchors'][c['revision_id']])
    row_checks={};bindings={};doc_checks={};unknown_checks={}
    for identity,c in cases.items():
        row=matrix.get(identity) or {};st=io['status'](row.get('status'),contract)
        adopted=(io['business_text'](row.get('adopted_text'),c['adopted_text'],contract['text_anchors'][identity+':proposed_text']) if c['status']=='confirmed' else io['blank'](row.get('adopted_text')))
        row_checks[identity]={'status':st==c['status'],'clause':io['clean'](row.get('clause_id')).upper()==c['clause_id'],
            'base':text_ok(row.get('base_text'),c,'base_text'),'proposal':text_ok(row.get('proposed_text'),c,'proposed_text'),
            'adopted_only_when_confirmed':bool(row) and adopted,'condition':bool(row) and condition_ok(row.get('condition'),c),
            'rule_ids':bool(io['rule_names'](row.get('rule_ids')) & set(c['rule_ids']))}
        bindings[identity]=io['evidence_score'](row.get('evidence'),regions[identity],contract)
        section='execution' if c['status']=='confirmed' else 'conditional' if c['status']=='conditional' else 'nonexecution'
        records=find_doc(identity,section);elsewhere=[v for name in sections if name!=section for v in find_doc(identity,name)]
        correct=bool(len(records)==1 and not elsewhere)
        content=re.sub(r'\b[RC]\d{2}\b','',records[0]['text'],flags=re.I) if records else ''
        if c['status']=='confirmed':correct &= io['business_text'](content,c['adopted_text'],contract['text_anchors'][identity+':proposed_text'])
        if c['condition'] and c['status'] in {'confirmed','conditional'}:
            correct &= all(any(canon(a) in canon(content) for a in group) for group in oracle['condition_anchors'][identity])
        if c['status']=='conditional':correct &= io['business_text'](content,c['proposed_text'],contract['text_anchors'][identity+':proposed_text'])
        doc_checks[identity]=bool(correct)
    for identity,required in oracle['uncertain_required_fields'].items():
        row=uncertain.get(identity) or {};c=cases[identity];fields=io['field_names'](row.get('unknown_fields'),contract)
        permitted=set(required)|({'condition_met'} if identity=='R16' else set())
        visible=row.get('visible_text');visible_ok=text_ok(visible,c,'proposed_text')
        missing_values=all(io['blank'](row.get(k)) for k in ['proposed_amount'] if identity=='R04')
        if identity=='R10' and 'confirmation_b' in row:missing_values &= row['confirmation_b'] is None or io['blank'](row['confirmation_b'])
        if identity=='R16':
            if 'condition' in row:missing_values &= condition_ok(row['condition'],c)
            if 'condition_met' in row:missing_values &= row['condition_met'] is None or io['blank'](row['condition_met'])
        evidence=io['evidence_score'](row.get('evidence'),regions[identity],contract)
        unknown_checks[identity]={'field_scope':set(required)<=fields<=permitted,'visible_text':visible_ok,
            'no_guessed_value':bool(missing_values),'reason':bool(io['clean'](row.get('reason'))),'next_action':bool(io['clean'](row.get('next_action'))),
            'regional_evidence':evidence['score']}
    def correct(ids):return mean(all(row_checks[k].values()) and doc_checks[k] for k in ids)
    boundaries={
        'archive_not_local':correct(['R02']),'black_strike_not_red_cancel':correct(['R03']),
        'cancelled_red_proposals':correct(['R05','R14']),'reject_with_stamps':correct(['R06']),
        'missing_b':correct(['R07']),'double_choice':correct(['R08']),'blank_choice':correct(['R11']),
        'condition_unmet':correct(['R09']),'condition_met_scope':correct(['R13']),
        'unreadable_amount':mean([correct(['R04']),mean(unknown_checks['R04'].values())]),
        'obscured_b':mean([correct(['R10']),mean(unknown_checks['R10'].values())]),
        'unknown_condition':mean([correct(['R16']),mean(unknown_checks['R16'].values())]),
        'old_unsigned_not_executing':mean(not find_doc(k,'execution') for k in oracle['nonexecuting_ids']) if model else 0.}
    if set(boundaries)!=set(boundaries_contract['boundaries']):raise ValueError('H012 boundary contract mismatch')
    correctness=.55*mean(mean(v.values()) for v in row_checks.values())+.30*mean(doc_checks.values())+.15*mean(mean(v.values()) for v in unknown_checks.values())
    unknown_scope=unique and set(uncertain)==set(oracle['uncertain_required_fields'])
    complete=bool(set(matrix)==set(cases) and not meta.get('duplicate_ids') and all(matrix.values()))
    native=bool(model and not model['pending_revisions'] and render and render['basic_fit'])
    delivery=mean([mean(objects.values()),complete,unknown_scope,native,intact])
    binding=mean([mean(v['score'] for v in bindings.values()),mean(v['regional_evidence'] for v in unknown_checks.values())])
    scores={'business_correctness':correctness,'boundary_cases':mean(boundaries.values())*intact,'delivery_integrity':delivery*intact,'evidence_binding':binding*intact}
    if not any(objects.values()):scores={k:0. for k in scores}
    scores['overall_score']=sum(scores[k]*w for k,w in oracle['checkpoint_weights'].items())
    if any(not 0<=v<=1 for v in scores.values()):raise ValueError('H012 rule score out of bounds')
    report={'schema_version':'h012-rule-observations/v1','scores':scores,'input_unchanged':intact,'candidate_errors':errors,'parsed_outputs':objects,
        'matrix_checks':row_checks,'matrix_metadata':meta,'native_sections':sections,'native_checks':doc_checks,
        'unknown_checks':unknown_checks,'unknown_scope_exact':unknown_scope,'boundary_groups':boundaries,'regional_bindings':bindings,
        'document_render':render,'matrix_recalculation':recalculation,
        'limit':'Rule-side bounded state/value/native/coordinate checks. Not independent semantic scoring, image-read proof, human expert review, Harness results or measured difficulty.'}
    derived.mkdir(parents=True,exist_ok=True)
    with (derived/'h012-analysis.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,default=str);f.write('\n')
    return scores
