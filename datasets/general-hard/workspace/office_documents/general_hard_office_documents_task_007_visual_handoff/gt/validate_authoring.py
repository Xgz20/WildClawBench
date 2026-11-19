"""Author controls use approved GT when present, retaining explicit pending-review negatives."""
from pathlib import Path
from copy import deepcopy
import argparse,hashlib,json,os,runpy,shutil,zipfile
import xml.etree.ElementTree as ET

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def text(node):return ''.join(t.text or '' for t in node.iter(W+'t'))
def set_text(node,value):
    leaves=list(node.iter(W+'t'));assert leaves;leaves[0].text=value
    for leaf in leaves[1:]:leaf.text=''
def edit_doc(path,operation):
    with zipfile.ZipFile(path) as archive:members=[(info,archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(path,'w') as archive:
        for info,data in members:
            if info.filename=='word/document.xml':
                tree=ET.fromstring(data);operation(tree);data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            archive.writestr(info,data)
def bookmarked(tree,name):
    found=[p for p in tree.findall('.//'+W+'body/'+W+'p') if any(n.get(W+'name')==name for n in p.iter(W+'bookmarkStart'))]
    assert len(found)==1,(name,len(found));return found[0]
def cell(tree,row_label,column):
    found=[row for row in tree.findall('.//'+W+'tr') if row.findall(W+'tc') and text(row.findall(W+'tc')[0])==row_label]
    assert len(found)==1;return found[0].findall(W+'tc')[column]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exec-root',required=True,type=Path);parser.add_argument('--gt-root',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path);args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=False)
    source=args.exec_root;gt=args.gt_root;approved=(gt/'expected.json').is_file()
    expected=json.loads((gt/('expected.json' if approved else 'author_expected.json')).read_text(encoding='utf-8'))
    grader=runpy.run_path(str(gt/'grader.py'));controls={}
    def make(name):
        ws=args.output_dir/name/'workspace';shutil.copytree(source,ws);shutil.copytree(gt,ws/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copytree(gt/'reference/results',ws/'results');return ws
    def ledger(ws,operation):
        path=ws/'results/visual_changes.json';obj=json.loads(path.read_text(encoding='utf-8'));operation(obj['changes'])
        path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def change(ws,identity,**fields):
        ledger(ws,lambda rows:next(row for row in rows if row['annotation_id']==identity).update(fields))
    def doc(ws,operation):edit_doc(ws/'results/handoff_revised.docx',operation)
    def run(name,operation=lambda ws:None,kind='negative'):
        ws=make(name);operation(ws);os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(args.output_dir/name/'evidence')
        before={str(path.relative_to(ws)):sha(path) for path in ws.rglob('*') if path.is_file()}
        try:
            if approved:
                scores=grader['grade'](ws)
                result={'scores':scores,'observations':json.loads((args.output_dir/name/'evidence/h007-analysis.json').read_text(encoding='utf-8'))}
            else:result=grader['evaluate'](ws,expected)
        except FileNotFoundError as exc:
            assert kind=='infrastructure';controls[name]={'error_type':type(exc).__name__,'expected':'evaluation error, not zero'};return
        if kind=='infrastructure':raise AssertionError('missing GT/helper must not become a score')
        assert before=={str(path.relative_to(ws)):sha(path) for path in ws.rglob('*') if path.is_file()}
        scores=result['scores'];assert all(0<=v<=1 for v in scores.values())
        if kind=='positive':assert abs(scores['overall_score']-1)<1e-12,(name,scores,result['observations'])
        else:assert scores['overall_score']<1,(name,scores)
        controls[name]={'scores':scores,'native_checks':result['observations']['native_checks'],
            'native_details':result['observations']['native_details'],'ledger_checks':result['observations']['ledger_checks'],
            'workspace_unchanged':True}
        return result
    run('author_reference',kind='positive')
    if approved:
        def independent_regions(ws,identity):
            record=json.loads((ws/'gt/reviews'/f'{identity}.json').read_text(encoding='utf-8'))
            rows=[]
            protected=json.loads((ws/'gt/protected_sha256.json').read_text(encoding='utf-8'))
            for item in record['annotations']:
                decision=item['decision']['status'] if isinstance(item['decision'],dict) else item['decision']
                if decision=='adopt':decision='applied'
                if decision in {'reject','reject_out_of_scope'}:decision='not_adopted'
                row={'annotation_id':item['annotation_id'],'image':item['image'],'action':item['action'],
                    'decision':decision,'target_ref':item['target_ref'],'before':item['before'],'after':item['after'],
                    'annotation_region':{'space':'pixel','bbox':item['annotation_bbox']},
                    'target_region':{'space':'pixel','bbox':item['target_bbox']},
                    'source_image_sha256':protected['annotated_pages/'+item['image']],
                    'explanation':item['reason']}
                if 'destination_bbox' in item:row['destination_region']={'space':'pixel','bbox':item['destination_bbox']}
                rows.append(row)
            (ws/'results/visual_changes.json').write_text(json.dumps({'changes':rows},ensure_ascii=False),encoding='utf-8')
        for identity in ['reviewer_a','reviewer_b']:
            run('equivalent_'+identity+'_regions',lambda ws,identity=identity:independent_regions(ws,identity),'positive')
    def alternate_ledger(ws):
        def operation(rows):
            rows.reverse()
            for row in rows:
                row['annotation_id']=str(int(row['annotation_id'][1:]));row['source_image_sha256']=row['source_image_sha256'].upper();row.pop('decision')
                row['image']='annotated_pages/'+row['image']
                for key in ('annotation_region','target_region','destination_region'):
                    if key in row:
                        b=row[key]['bbox'];row[key]={'space':'normalized','bbox':[b[0]/1600,b[1]/1300,b[2]/1600,b[3]/1300]}
        ledger(ws,operation)
    run('equivalent_normalized_regions_and_order',alternate_ledger,'positive')
    def xywh_polygon(ws):
        def operation(rows):
            for row in rows:
                b=row['annotation_region']['bbox'];row['annotation_region']={'space':'pixel','format':'xywh','bbox':[b[0],b[1],b[2]-b[0],b[3]-b[1]]}
                b=row['target_region']['bbox'];row['target_region']={'space':'pixel','polygon':[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]]}
        ledger(ws,operation)
    run('equivalent_xywh_and_polygon_regions',xywh_polygon,'positive')
    def no_bookmarks(ws):
        def operation(tree):
            for p in tree.findall('.//'+W+'body/'+W+'p'):
                for n in list(p):
                    if n.tag in (W+'bookmarkStart',W+'bookmarkEnd'):p.remove(n)
        doc(ws,operation)
    run('equivalent_native_without_source_bookmarks',no_bookmarks,'positive')
    def inline(ws):
        def operation(tree):
            body=tree.find(W+'body');p=bookmarked(tree,'handoff_note');following=list(body)[list(body).index(p)+1]
            set_text(p,text(p)+text(following));body.remove(following)
        doc(ws,operation)
    run('equivalent_inline_warning',inline,'positive')
    def automatic_numbering(ws):
        def operation(tree):
            for i in range(1,5):
                p=bookmarked(tree,'step'+str(i));set_text(p,text(p).split(' ',1)[1]);props=p.find(W+'pPr')
                if props is None:props=ET.Element(W+'pPr');p.insert(0,props)
                style=ET.SubElement(props,W+'pStyle');style.set(W+'val','ListNumber')
        doc(ws,operation)
    run('equivalent_native_automatic_numbering',automatic_numbering,'positive')
    def explicit_defaults(ws):
        def operation(tree):
            section=tree.find(W+'body/'+W+'sectPr');section.find(W+'pgSz').set(W+'orient','portrait');section.find(W+'cols').set(W+'num','1')
        doc(ws,operation)
    run('equivalent_explicit_page_defaults',explicit_defaults,'positive')
    run('equivalent_null_for_deleted_text',lambda ws:change(ws,'V03',after=None),'positive')
    run('ledger_correct_document_unchanged',lambda ws:shutil.copyfile(source/'handoff.docx',ws/'results/handoff_revised.docx'))
    run('global_window_replacement',lambda ws:doc(ws,lambda tree:set_text(bookmarked(tree,'history_window'),'演练回放时间为周二10:30。已完成记录不得改写。')))
    run('backup_changed_with_primary',lambda ws:doc(ws,lambda tree:set_text(bookmarked(tree,'owner_pair'),'准备责任岗为值班小组B；后备岗为值班小组B。')))
    def delete_whole(ws):
        def operation(tree):tree.find(W+'body').remove(bookmarked(tree,'customer_promise'))
        doc(ws,operation)
    run('delete_whole_paragraph_not_selected_sentence',delete_whole)
    def wrong_row(ws):
        def operation(tree):set_text(cell(tree,'复核材料',2),'16:00');set_text(cell(tree,'回执归档',2),'17:30')
        doc(ws,operation)
    run('nearest_row_not_arrow_target',wrong_row)
    run('cancelled_proposal_applied',lambda ws:doc(ws,lambda tree:set_text(cell(tree,'回执归档',2),'17:30')))
    def wrong_note(ws):
        def operation(tree):
            body=tree.find(W+'body');p=bookmarked(tree,'handoff_note');inserted=list(body)[list(body).index(p)+1];body.remove(inserted)
            after=bookmarked(tree,'archive_note');body.insert(list(body).index(after)+1,inserted)
        doc(ws,operation)
    run('warning_added_to_similar_archive_note',wrong_note)
    def numbers_only(ws):
        def operation(tree):
            body=tree.find(W+'body');a=bookmarked(tree,'step2');b=bookmarked(tree,'step3');first=min(list(body).index(a),list(body).index(b))
            body.remove(a);body.remove(b);set_text(a,'2 通知协作岗位。');set_text(b,'3 核对依赖回执。');body.insert(first,a);body.insert(first+1,b)
        doc(ws,operation)
    run('step_order_unchanged',numbers_only)
    def stale_numbers(ws):
        def operation(tree):set_text(bookmarked(tree,'step3'),'3 核对依赖回执。');set_text(bookmarked(tree,'step2'),'2 通知协作岗位。')
        doc(ws,operation)
    run('step_order_correct_numbers_stale',stale_numbers)
    def outside_delete(ws):
        def operation(tree):tree.find(W+'body').remove(bookmarked(tree,'record_retention'))
        doc(ws,operation)
    run('outside_scope_deletion',outside_delete)
    run('retained_document_but_false_delete_record',lambda ws:change(ws,'V08',action='delete',decision='applied',after=''))
    run('wrong_source_image',lambda ws:change(ws,'V04',image='page_01.png'))
    run('wrong_source_sha',lambda ws:change(ws,'V01',source_image_sha256='0'*64))
    def whole_regions(ws):
        ledger(ws,lambda rows:[row.update(annotation_region={'space':'pixel','bbox':[0,0,1600,1300]},target_region={'space':'pixel','bbox':[0,0,1600,1300]}) for row in rows])
    run('whole_image_regions_not_target_evidence',whole_regions)
    run('wrong_region_same_word_other_row',lambda ws:change(ws,'V04',target_region={'space':'pixel','bbox':[490,470,555,500]}))
    run('wrong_move_destination',lambda ws:change(ws,'V07',destination_region={'space':'pixel','bbox':[70,390,450,430]}))
    def wrong_table_font(ws):
        def operation(tree):
            c=cell(tree,'复核材料',2);run=c.find(W+'p/'+W+'r');props=run.find(W+'rPr')
            if props is None:props=ET.SubElement(run,W+'rPr')
            size=props.find(W+'sz')
            if size is None:size=ET.SubElement(props,W+'sz')
            size.set(W+'val','40')
        doc(ws,operation)
    run('changed_table_value_font',wrong_table_font)
    def no_description(ws):ledger(ws,lambda rows:[row.pop('explanation') for row in rows])
    result=run('missing_explanations',no_description);assert result['scores']['business_correctness']==1
    run('missing_deleted_after_field',lambda ws:ledger(ws,lambda rows:next(row for row in rows if row['annotation_id']=='V03').pop('after')))
    run('missing_native_document',lambda ws:(ws/'results/handoff_revised.docx').unlink())
    run('damaged_native_document',lambda ws:(ws/'results/handoff_revised.docx').write_bytes(b'not Word'))
    def no_package_contract(ws):
        path=ws/'results/handoff_revised.docx'
        with zipfile.ZipFile(path) as archive:parts=[(info,archive.read(info.filename)) for info in archive.infolist() if info.filename not in {'[Content_Types].xml','_rels/.rels'}]
        with zipfile.ZipFile(path,'w') as archive:
            for info,data in parts:archive.writestr(info,data)
    run('missing_native_package_contract',no_package_contract)
    run('missing_ledger',lambda ws:(ws/'results/visual_changes.json').unlink())
    result=run('all_outputs_missing',lambda ws:shutil.rmtree(ws/'results'));assert result['scores']['overall_score']==0
    run('protected_input_changed',lambda ws:(ws/'edit_scope.md').write_bytes((ws/'edit_scope.md').read_bytes()+b'\n'))
    run('missing_private_contract',lambda ws:(ws/'gt/artifact_contract.json').unlink(),'infrastructure')
    run('missing_native_helper',lambda ws:(ws/'gt/native_docx.py').unlink(),'infrastructure')
    ws=make('pending_review_gate')
    (ws/'gt/annotation_status.json').write_text(json.dumps({'status':'awaiting_independent_annotations','received':0}),encoding='utf-8')
    try:grader['grade'](ws)
    except ValueError as exc:controls['pending_review_gate']={'expected':'evaluation error','error':str(exc)}
    else:raise AssertionError('pending review was promoted to a score')
    status={'status':'approved','received':2,'input_sha256':json.loads((gt/'protected_sha256.json').read_text()),'reviewers':[]}
    (ws/'gt/annotation_status.json').write_text(json.dumps(status),encoding='utf-8')
    try:grader['grade'](ws)
    except ValueError as exc:controls['status_flag_without_review_records']={'expected':'evaluation error','error':str(exc)}
    else:raise AssertionError('self-asserted review flags without actual records were accepted')
    if approved:
        def gate_negative(name,operation,rebind=False):
            ws=make(name);operation(ws)
            if rebind:
                status_path=ws/'gt/annotation_status.json';status=json.loads(status_path.read_text(encoding='utf-8'))
                for reviewer in status['reviewers']:reviewer['sha256']=sha(ws/'gt'/reviewer['path'])
                status['reconciliation']['sha256']=sha(ws/'gt'/status['reconciliation']['path'])
                status_path.write_text(json.dumps(status),encoding='utf-8')
                expected_path=ws/'gt/expected.json';value=json.loads(expected_path.read_text(encoding='utf-8'))
                value['annotation_status_sha256']=sha(status_path);expected_path.write_text(json.dumps(value),encoding='utf-8')
            try:grader['grade'](ws)
            except (ValueError,FileNotFoundError) as exc:controls[name]={'expected':'evaluation error, not capability zero','error_type':type(exc).__name__,'error':str(exc)}
            else:raise AssertionError('invalid approved annotation gate accepted: '+name)
        def edit_json(path,operation):
            value=json.loads(path.read_text(encoding='utf-8'));operation(value);path.write_text(json.dumps(value),encoding='utf-8')
        gate_negative('raw_review_changed_sha',lambda ws:edit_json(ws/'gt/reviews/reviewer_a.json',lambda v:v.update(annotator='forged')))
        gate_negative('raw_input_sha_wrong_after_reindex',lambda ws:edit_json(ws/'gt/reviews/reviewer_a.json',lambda v:v['input_sha256'].update({'handoff.docx':'0'*64})),True)
        gate_negative('model_record_claims_human_after_reindex',lambda ws:edit_json(ws/'gt/reviews/reviewer_a.json',lambda v:v.update(human_expert=True)),True)
        gate_negative('actual_pixels_not_read_after_reindex',lambda ws:edit_json(ws/'gt/reviews/reviewer_a.json',lambda v:v['images_read'][0].update(actually_viewed=False)),True)
        gate_negative('unresolved_reconciliation_after_reindex',lambda ws:edit_json(ws/'gt/reviews/reconciliation.json',lambda v:v.update(unresolved_ids=['V07'])),True)
        gate_negative('approved_regions_changed',lambda ws:edit_json(ws/'gt/visual_regions.json',lambda v:v['regions'][0].update(target_bbox=[0,0,1600,1300])))
        gate_negative('missing_actual_second_annotation',lambda ws:(ws/'gt/reviews/reviewer_b.json').unlink())
    for name,identity in [('nearest_row_not_arrow_target','V04'),('cancelled_proposal_applied','V05'),('warning_added_to_similar_archive_note','V06'),('outside_scope_deletion','V08')]:
        assert controls[name]['native_checks'][identity]==0,(name,identity)
    report={'schema_version':'h007-author-controls/v1','status':'AUTHOR_CONTROLS_PASS' if approved else 'AUTHOR_CONTROLS_PASS_REVIEW_PENDING','control_count':len(controls),
       'controls':controls,'independent_annotations_received':2 if approved else 0,'review_kind':'independent_model_review' if approved else None,'human_expert':False,
       'gt_bindings':{str(path.relative_to(gt)):sha(path) for path in sorted(gt.rglob('*')) if path.is_file() and path.name!='authoring_validation.json' and '__pycache__' not in path.parts},
       'limit':'Author rule controls; approved GT has two retained model annotations and author reconciliation. No independent semantic score, actual Harness result or empirical calibration.'}
    (args.output_dir/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'controls':len(controls),'scores':{name:value.get('scores',value) for name,value in controls.items()}},ensure_ascii=False))

if __name__=='__main__':main()
