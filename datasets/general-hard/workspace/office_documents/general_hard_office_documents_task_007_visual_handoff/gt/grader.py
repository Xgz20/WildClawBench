"""Native revision and typed visual binding checks; image meaning requires independent review."""
from pathlib import Path
import hashlib,json,os,runpy,re

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def mean(values):return sum(values)/len(values) if values else 0.

def evaluate(root,expected,*,regions_filename='constructed_regions.json'):
    root=Path(root).resolve();gt=root/'gt';contract=read(gt/'artifact_contract.json');oracle=read(gt/'business_oracle.json')
    counterexamples=read(gt/'counterexamples.json');evidence_contract=read(gt/'evidence_requirements.json');evidence_index=read(gt/'evidence_index.json')['records']
    protected=read(gt/'protected_sha256.json');visuals={item['id']:item for item in read(gt/regions_filename)['regions']}
    io=runpy.run_path(str(gt/'structured_io.py'));native=runpy.run_path(str(gt/'native_docx.py'));canon=native['canon']
    cases={item['id']:item for item in expected['cases']}
    if set(cases)!={f'V{i:02d}' for i in range(1,9)} or set(visuals)!=set(cases):raise ValueError('H007 private oracle incomplete')
    if expected['source_sha256']!=protected['handoff.docx']:raise ValueError('H007 physical source binding mismatch')
    if evidence_contract.get('full_credit_iou')!=.3 or any(item['source_sha256']!=protected[item['source']] for item in evidence_index.values()):
        raise ValueError('H007 private evidence contract mismatch')
    intact=all((root/name).is_file() and not (root/name).is_symlink() and sha(root/name)==digest for name,digest in protected.items())
    document=None;document_error=None
    try:document=native['read_document'](root/contract['document'])
    except (native['CandidateDocumentError'],OSError) as exc:document_error=str(exc)
    paragraphs=native['main_paragraphs'](document) if document else []
    tables=[b for b in document['blocks'] if b['kind']=='table'] if document else []
    source=expected['source_paragraphs']
    prefixes={'current_window':['正式交接窗口'],'owner_pair':['准备责任岗'],
              'customer_promise':['通知客户时承诺','依赖项未完成'],'handoff_note':['交接说明'],
              'archive_note':['归档说明'],'record_retention':['发布记录保存期'],'history_window':['演练回放时间']}
    def paragraph(identity):
        named=[p for p in paragraphs if identity in p['bookmarks']]
        if named:return named[0] if len(named)==1 else None
        targets=[p for p in paragraphs if any(canon(p['text']).startswith(canon(prefix)) for prefix in prefixes.get(identity,[]))]
        return targets[0] if len(targets)==1 else None
    def equal_paragraph(identity,wanted):
        actual=paragraph(identity)
        return actual is not None and canon(actual['text'])==canon(wanted)
    def row(label):
        if len(tables)!=1:return None
        found=[r for r in tables[0]['rows'] if r and canon(r[0]['text'])==canon(label)]
        return found[0] if len(found)==1 else None
    native_checks={};native_details={}
    for identity,case in cases.items():
        kind=case['action'];value=False
        if kind in ('replace','replace_span','delete_span','reject_out_of_scope'):
            value=equal_paragraph(case['target'],case['expected_text'])
        elif kind=='replace_cell':
            actual=row('复核材料');value=actual is not None and len(actual)==4 and canon(actual[2]['text'])==canon(case['new'])
        elif kind=='retain':
            actual=row('回执归档');value=actual is not None and [canon(c['text']) for c in actual]==[canon(t) for t in case['expected_row']]
        elif kind=='insert_after':
            p=paragraph(case['target']);word=case['new'];value=False
            if p:
                if canon(p['text'])==canon(case['source_text']+word):value=True
                elif canon(p['text'])==canon(case['source_text']):
                    index=paragraphs.index(p);value=index+1<len(paragraphs) and canon(paragraphs[index+1]['text'])==canon(word)
        elif kind=='reorder':
            keys=[native['step_value'](p) for p in paragraphs]
            expected_clean=[canon(value.split(' ',1)[1]) for value in case['expected_steps']]
            selected=[(number,canon(text)) for number,text in keys if canon(text) in expected_clean]
            order=[text for _,text in selected]==expected_clean
            numbering=[number for number,_ in selected]==[1,2,3,4]
            value=.5*order+.5*numbering;native_details['step_order']=order;native_details['step_numbering']=numbering
        native_checks[identity]=float(value)
    rows,metadata=io['load_ledger'](root/contract['ledger'],contract)
    ledger_checks={};bindings={}
    for identity,case in cases.items():
        item=rows.get(identity,{});expected_action=io['action_name'](case['action'],contract);actual_action=io['action_name'](item.get('action'),contract)
        values=io['declared_values_ok'](item,case,source)
        ledger_checks[identity]={'action':actual_action==expected_action,
            'target':io['target_ok'](item.get('target_ref'),case,source),'decision':io['decision_ok'](item,expected_action,actual_action),**values}
        visual=visuals[identity];name=visual['image']
        known_image=io['image_name'](item.get('image'))==name
        digest=known_image and str(item.get('source_image_sha256','')).strip().lower()==protected['annotated_pages/'+name]
        alternatives=[]
        if identity=='V05':
            r=visual['target_bbox'];alternatives.append([r[0],r[1],r[0]+(r[2]-r[0])*.2,r[3]])
        bind={'image':float(known_image),'source_sha256':float(digest),
              'annotation_region':io['region_score'](item.get('annotation_region'),visual['annotation_bbox']) if known_image else 0.,
              'target_region':io['region_score'](item.get('target_region'),visual['target_bbox'],alternatives) if known_image else 0.}
        if 'landing_bbox' in visual:bind['destination_region']=io['destination_score'](item.get('destination_region'),visual) if known_image else 0.
        bindings[identity]=bind
    native_score=mean(list(native_checks.values()));ledger_score=mean([mean(list(item.values())) for item in ledger_checks.values()])
    business=.75*native_score+.25*ledger_score
    boundaries={
      'same_window_text':mean([native_checks['V01'],equal_paragraph('history_window',source['history_window'])]),
      'owner_not_backup':native_checks['V02'],
      'delete_only_selected_sentence':native_checks['V03'],
      'cross_row_arrow':mean([native_checks['V04'],native_checks['V05']]),
      'cancelled_proposal_not_applied':mean([native_checks['V05'],ledger_checks['V05']['action'],ledger_checks['V05']['decision']]),
      'insert_at_selected_note':mean([native_checks['V06'],equal_paragraph('archive_note',source['archive_note'])]),
      'real_order_and_numbering':mean([native_details.get('step_order',False),native_details.get('step_numbering',False)]),
      'scope_beats_outside_proposal':mean([native_checks['V08'],ledger_checks['V08']['action'],ledger_checks['V08']['decision']])}
    boundary=mean(list(boundaries.values()))
    if set(counterexamples['boundary_groups'])!=set(boundaries):raise ValueError('H007 counterexample coverage mismatch')
    expected_blocks=expected['expected_blocks']
    actual_blocks=[]
    for block in document['blocks'] if document else []:
        if block['kind']=='table':actual_blocks.append({'kind':'table','rows':[[canon(c['text']) for c in r] for r in block['rows']]})
        else:
            number,text=native['step_value'](block)
            if number is not None and any(canon(text)==canon(source[f'step{i}'].split(' ',1)[1]) for i in range(1,5)):
                actual_blocks.append({'kind':'paragraph','text':canon(str(number)+' '+text)})
            else:actual_blocks.append({'kind':'paragraph','text':canon(block['text'])})
    wanted_blocks=[{'kind':'paragraph','text':canon(b['text'])} if b['kind']=='paragraph' else {'kind':'table','rows':[[canon(c) for c in r] for r in b['rows']]} for b in expected_blocks]
    # An inline appendix at the selected paragraph is equivalent to a separate warning paragraph.
    inline=[]
    for block in actual_blocks:
        if block.get('text')==canon(source['handoff_note']+cases['V06']['new']):
            inline.extend([{'kind':'paragraph','text':canon(source['handoff_note'])},{'kind':'paragraph','text':canon(cases['V06']['new'])}])
        else:inline.append(block)
    scope_protection=inline==wanted_blocks
    complete=metadata.get('parseable') and metadata.get('entry_count')==8 and set(rows)==set(cases) and not metadata.get('conflicts') and not metadata.get('unknown')
    if complete:
        for item in rows.values():
            complete &= set(contract['required_fields'])<=set(item['_present'])
            complete &= isinstance(item.get('image'),str) and isinstance(item.get('source_image_sha256'),str) and bool(re.fullmatch(r'[0-9a-fA-F]{64}',str(item.get('source_image_sha256'))))
            complete &= isinstance(item.get('target_ref'),(str,dict)) and isinstance(item.get('explanation'),str)
            complete &= io['action_name'](item.get('action'),contract) is not None
            complete &= io['region_box'](item.get('annotation_region')) is not None and io['region_box'](item.get('target_region')) is not None
    descriptions=mean([isinstance(rows.get(identity,{}).get('explanation'),str) and bool(rows[identity]['explanation'].strip()) for identity in cases])
    def page_setup(value):
        size=value.get('pgSz',{});margins=value.get('pgMar',{});columns=value.get('cols',{})
        return {'size':{key:int(size.get(key,default)) for key,default in [('w',12240),('h',15840)]},
            'orientation':size.get('orient','portrait'),
            'margins':{key:int(margins.get(key,default)) for key,default in [('top',1440),('bottom',1440),('left',1440),('right',1440),('header',720),('footer',720),('gutter',0)]},
            'columns':{'num':int(columns.get('num',1)),'space':int(columns.get('space',720))}}
    expected_page_setup=page_setup(expected['source_page_setup'])
    frame=False
    if document:
        try:frame=bool(len(tables)==1 and len(tables[0]['rows'])==3 and all(len(r)==4 for r in tables[0]['rows'])
                   and page_setup(document['page_setup'])==expected_page_setup and not any(canon(t) for t in document['header_footer_text']))
        except (ValueError,TypeError):frame=False
    # Selected font/color/size checks cover all expected visible native paragraphs; full layout is Judge work.
    style_by_text={canon(b['text']):b['segments'][0]['format'] for b in expected['source_format']['blocks'] if b['kind']=='paragraph' and b['segments']}
    for case in cases.values():
        if 'source_text' in case and 'expected_text' in case:style_by_text[canon(case['expected_text'])]=style_by_text.get(canon(case['source_text']),{})
    base_style=style_by_text[canon(source['handoff_note'])]
    style_by_text[canon(cases['V06']['new'])]=base_style;style_by_text[canon(source['handoff_note']+cases['V06']['new'])]=base_style
    for i,text in enumerate(cases['V07']['expected_steps'],1):style_by_text[canon(text)]=style_by_text[canon(source['step1'])]
    font_checks=[]
    def font(value):
        key=canon(value).casefold()
        return 'heiti' if key in {'heitisc','stheiti','黑体简','黑体'} else key
    def same_font(actual,wanted):
        return font(actual.get('font'))==font(wanted.get('font')) and actual.get('sz')==wanted.get('sz') and bool(actual.get('b'))==bool(wanted.get('b')) and bool(actual.get('i'))==bool(wanted.get('i')) and actual.get('color')==wanted.get('color')
    for p in paragraphs:
        number,text=native['step_value'](p);key=canon((str(number)+' '+text) if number is not None else p['text'])
        expected_style=style_by_text.get(key)
        if expected_style is None:continue
        for segment in p['segments']:
            actual=segment['format']
            font_checks.append(same_font(actual,expected_style))
    if len(tables)==1:
        source_table=next(b for b in expected['source_format']['blocks'] if b['kind']=='table')
        if len(tables[0]['rows'])==len(source_table['rows']):
            for actual_row,source_row in zip(tables[0]['rows'],source_table['rows']):
                if len(actual_row)!=len(source_row):font_checks.append(False);continue
                for actual_cell,source_cell in zip(actual_row,source_row):
                    original=[s['format'] for p in source_cell['paragraphs'] for s in p['segments']]
                    for p in actual_cell['paragraphs']:
                        for segment in p['segments']:font_checks.append(bool(original) and same_font(segment['format'],original[0]))
    selected_format=frame and bool(font_checks) and all(font_checks)
    delivery=mean([float(selected_format),float(bool(complete)),float(scope_protection),descriptions,float(intact)]) if document or metadata.get('parseable') else 0.
    evidence=mean([mean(list(item.values())) for item in bindings.values()])
    if not intact:boundary=delivery=evidence=0.
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence}
    scores['overall_score']=min(1.,sum(scores[key]*weight for key,weight in oracle['checkpoint_weights'].items()))
    observation={'schema_version':'h007-rule-observations/v1','scores':scores,'native_checks':native_checks,'native_details':native_details,
      'ledger_checks':ledger_checks,'boundary_groups':boundaries,'bindings':bindings,'ledger_metadata':metadata,
      'document_error':document_error,'native_frame':frame,'selected_format':selected_format,'scope_protection':scope_protection,
      'input_unchanged':intact,'ledger_schema_complete':bool(complete),'description_presence':descriptions,
      'output_sha256':{name:sha(root/contract[name]) if (root/contract[name]).is_file() else None for name in ('document','ledger')},
      'actual_blocks':actual_blocks,'semantic_limit':'No image-language interpretation or complete native layout proof. Approved independent annotations and a separate semantic Judge remain necessary.'}
    output=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if output:
        path=Path(output);path.mkdir(parents=True,exist_ok=True)
        with (path/'h007-analysis.json').open('x',encoding='utf-8') as handle:json.dump(observation,handle,ensure_ascii=False,indent=2);handle.write('\n')
    else:print(json.dumps(observation,ensure_ascii=False))
    return {'scores':scores,'observations':observation}

def grade(root):
    root=Path(root);gt=root/'gt';review=read(gt/'annotation_status.json')
    if review.get('status')!='approved' or review.get('received')!=2:raise ValueError('H007 independent annotation gate not satisfied')
    protected=read(gt/'protected_sha256.json')
    if review.get('input_sha256')!=protected:raise ValueError('H007 independent annotation input binding mismatch')
    reviewers=review.get('reviewers',[])
    if len(reviewers)!=2 or len({item.get('reviewer_id') for item in reviewers})!=2 or len({item.get('path') for item in reviewers})!=2:
        raise ValueError('H007 two distinct independent annotation records required')
    def bound_record(item):
        if not isinstance(item.get('path'),str):raise ValueError('H007 annotation record path missing')
        path=gt/item['path'];resolved=path.resolve()
        if path.is_symlink() or gt.resolve() not in resolved.parents or sha(path)!=item.get('sha256'):
            raise ValueError('H007 independent annotation record binding mismatch')
        return read(path)
    for item in reviewers:
        record=bound_record(item)
        if item.get('kind') not in {'independent_model_annotation','human_annotation'} or record.get('annotator')!=item.get('reviewer_id'):
            raise ValueError('H007 annotation identity/type mismatch')
        if record.get('input_sha256')!=protected:raise ValueError('H007 raw annotation input binding mismatch')
        if item['kind']=='independent_model_annotation' and (record.get('review_kind')!='independent_model_review' or record.get('human_expert') is not False):
            raise ValueError('H007 model annotations must not claim human expertise')
        images=record.get('images_read',[])
        if len(images)!=3 or {Path(row.get('image','')).name for row in images}!={'page_01.png','page_02.png','page_03.png'}:
            raise ValueError('H007 actual image review coverage incomplete')
        for image in images:
            name='annotated_pages/'+Path(image['image']).name
            if image.get('sha256')!=protected[name] or not (image.get('actually_viewed') is True or image.get('actual_visual_read') is True):
                raise ValueError('H007 actual image review binding mismatch')
        aliases=read(gt/'artifact_contract.json')['ids'];normalize=runpy.run_path(str(gt/'structured_io.py'))['canon']
        names={normalize(key):value for key,value in aliases.items()}
        annotations=record.get('annotations',[])
        if len(annotations)!=8 or {names.get(normalize(row.get('annotation_id'))) for row in annotations}!={f'V{i:02d}' for i in range(1,9)}:
            raise ValueError('H007 independent annotation coverage incomplete')
    reconciliation=bound_record(review.get('reconciliation',{}))
    if set(reconciliation.get('approved_ids',[]))!={f'V{i:02d}' for i in range(1,9)} or reconciliation.get('unresolved_ids')!=[]:
        raise ValueError('H007 annotation disagreements unresolved')
    visual=read(gt/'visual_regions.json')
    if visual.get('status')!='approved':raise ValueError('H007 reviewed visual region GT missing')
    expected=read(gt/'expected.json')
    if expected.get('review_status')!='approved':raise ValueError('H007 approved GT missing')
    if expected.get('annotation_status_sha256')!=sha(gt/'annotation_status.json'):raise ValueError('H007 approved GT review binding mismatch')
    if expected.get('visual_regions_sha256')!=sha(gt/'visual_regions.json'):raise ValueError('H007 approved GT visual region binding mismatch')
    return evaluate(root,expected,regions_filename='visual_regions.json')['scores']
