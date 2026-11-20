"""Author rule controls with actual DOCX/CSV mutations; no semantic Judge claims."""
from pathlib import Path
from copy import deepcopy
import argparse,csv,hashlib,json,os,runpy,shutil,unicodedata,zipfile
import xml.etree.ElementTree as ET

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word_text(p):return ''.join(n.text or '' for n in p.iter(W+'t'))
def set_text(p,text):
    leaves=list(p.iter(W+'t'));assert leaves;leaves[0].text=text
    for n in leaves[1:]:n.text=''
def patch_doc(path,operation):
    with zipfile.ZipFile(path) as archive:members=[(info,archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(path,'w') as archive:
        for info,data in members:
            if info.filename=='word/document.xml':
                tree=ET.fromstring(data);operation(tree);data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            archive.writestr(info,data)
def paragraph(tree,identity):
    found=[p for p in tree.findall('.//'+W+'body/'+W+'p') if any(n.get(W+'name')==identity for n in p.iter(W+'bookmarkStart'))]
    assert len(found)==1;return found[0]

def main():
    p=argparse.ArgumentParser();p.add_argument('--exec-root',required=True,type=Path);p.add_argument('--gt-root',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path)
    a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=False);gt=a.gt_root;grader=runpy.run_path(str(gt/'grader.py'))['evaluate'];controls={}
    truth=json.loads((gt/'expected.json').read_text(encoding='utf-8'));contract=json.loads((gt/'artifact_contract.json').read_text(encoding='utf-8'))
    source=json.loads((gt/'source_annotations.json').read_text(encoding='utf-8'))['data'];draft={r['sentence_id']:r['draft_vi'] for r in source['sentences']}
    def make(name):
        ws=a.output_dir/name/'workspace';shutil.copytree(a.exec_root,ws);shutil.copytree(gt,ws/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copytree(gt/'reference/results',ws/'results');return ws
    def ledger(ws,operation):
        path=ws/'results/alignment.csv'
        with path.open(encoding='utf-8-sig',newline='') as h:r=csv.DictReader(h);fields=list(r.fieldnames);rows=list(r)
        fields,rows=operation(fields,rows)
        with path.open('w',encoding='utf-8-sig',newline='') as h:w=csv.DictWriter(h,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
    def change(ws,identity,**fields):
        def operation(names,rows):
            next(row for row in rows if row['sentence_id']==identity).update(fields);return names,rows
        ledger(ws,operation)
    def facts(ws,identity,**values):
        def operation(names,rows):
            row=next(row for row in rows if row['sentence_id']==identity);data=json.loads(row['facts_json']);data.update(values);row['facts_json']=json.dumps(data,ensure_ascii=False);return names,rows
        ledger(ws,operation)
    def vi(ws,identity,value):patch_doc(ws/'results/final_vi.docx',lambda tree:set_text(paragraph(tree,identity),value))
    def run(name,mutation=lambda ws:None,kind='negative'):
        ws=make(name);mutation(ws);os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(a.output_dir/name/'evidence')
        before={str(path.relative_to(ws)):sha(path) for path in ws.rglob('*') if path.is_file()}
        try:result=grader(ws)
        except FileNotFoundError as error:
            assert kind=='infrastructure';controls[name]={'expected':'evaluation error','error_type':type(error).__name__};return
        if kind=='infrastructure':raise AssertionError('missing private dependency silently produced a score')
        assert before=={str(path.relative_to(ws)):sha(path) for path in ws.rglob('*') if path.is_file()}
        scores=result['scores'];assert all(0<=v<=1 for v in scores.values())
        if kind in ('positive','semantic_boundary'):assert abs(scores['overall_score']-1)<1e-12,(name,scores,result['observations'])
        else:assert scores['overall_score']<1,(name,scores)
        controls[name]={'scores':scores,'native_literals':result['observations']['native_literal_checks'],
          'business_parts':result['observations']['business_parts'],'workspace_unchanged':True,
          'semantic_status':'not_run','kind':kind}
        if kind=='semantic_boundary':controls[name]['expected_semantics']='Separate Judge must reject actual role/polarity contradiction; rule is not complete translation proof.'
        return result
    run('reference',kind='positive')
    def equivalent_fields(ws):
        def operation(names,rows):
            for row in rows:
                row['decision']=row['decision'].upper();row['term_ids']=';'.join(reversed(row['term_ids'].split(';')))
                if not row['term_ids']:row['term_ids']='N/A'
                if not row['comment_id']:row['comment_id']='N/A';row['review_ref']='N/A'
                values=json.loads(row['facts_json']);label=next(r for r in truth['sentences'] if r['sentence_id']==row['sentence_id'])
                converted={}
                for key,value in values.items():
                    if isinstance(value,bool):value=int(value)
                    elif value=='unknown':value=None
                    elif key=='amount':value='80.000 CNY'
                    elif key=='first_response_work_hours':value='4工作小时'
                    elif key=='handling_work_days':value='2 ngày làm việc'
                    elif key in ('start_date','end_date'):value='/'.join(reversed(value.split('-')))
                    converted[contract['fact_schema'][key]]=value
                row['facts_json']=json.dumps(converted,ensure_ascii=False)
            labels={name:contract['field_aliases'][name][-1] for name in names}
            return [labels[name] for name in reversed(names)],[{labels[key]:value for key,value in row.items()} for row in reversed(rows)]
        ledger(ws,operation)
    run('equivalent_bom_chinese_fields_numbers_dates_null_unknown',equivalent_fields,'positive')
    def nfd(ws):
        for name in ('final_vi.docx','review_zh.docx'):
            def operation(tree):
                for node in tree.iter(W+'t'):node.text=unicodedata.normalize('NFD',node.text or '')
            patch_doc(ws/'results'/name,operation)
    run('equivalent_nfd_accents',nfd,'positive')
    def rephrase(ws):
        vi(ws,'S03','Giá trị dịch vụ cho mỗi đợt là tám mươi nghìn CNY, chưa bao gồm thuế; không đổi đơn vị tiền tệ hoặc quy đổi theo tỷ giá.')
        vi(ws,'S04','Dịch vụ bắt đầu vào ngày 1 tháng 11 năm 2026 và kết thúc vào ngày 31 tháng 10 năm 2027.')
        vi(ws,'S05','Phản hồi đầu tiên phải được thực hiện trong bốn giờ làm việc kể từ khi đăng ký tiếp nhận yêu cầu lần này.')
        vi(ws,'S06','Thời hạn xử lý là hai ngày làm việc kể từ khi đã nhận đủ tài liệu cần thiết, không tính trước từ lần tiếp nhận đầu tiên.')
        vi(ws,'S11','Có tổng cộng mười bảy hạng mục, trong đó ba hạng mục chờ xác minh; số hạng mục hoàn thành là mười bốn.')
        vi(ws,'S13','Linh là người liên hệ dự phòng; lịch trực giữ nguyên.')
    run('equivalent_vietnamese_numeral_words_and_date_phrasing',rephrase,'positive')
    def table_layout(ws):
        def operation(tree):
            body=tree.find(W+'body');paragraphs={n.get(W+'name'):p for p in body.findall(W+'p') for n in p.iter(W+'bookmarkStart')}
            entries=[(identity,word_text(paragraphs[identity])) for identity in sorted(paragraphs) if identity.startswith('S')]
            for node in list(body):
                if node.tag==W+'p' and (any(n.get(W+'name','').startswith('S') for n in node.iter(W+'bookmarkStart')) or word_text(node).strip().startswith('[S')):body.remove(node)
            table=ET.Element(W+'tbl')
            for row in [['sentence_id','nội dung'],*reversed(entries)]:
                tr=ET.SubElement(table,W+'tr')
                for value in row:
                    tc=ET.SubElement(tr,W+'tc');p=ET.SubElement(tc,W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text=value
            body.insert(len(list(body))-1,table)
        patch_doc(ws/'results/final_vi.docx',operation)
    run('equivalent_native_id_body_table_reordered',table_layout,'positive')
    def alternative_table_headers(ws):
        table_layout(ws)
        def operation(tree):
            header=tree.find('.//'+W+'tbl/'+W+'tr');cells=header.findall(W+'tc')
            set_text(cells[0],'Điều khoản gốc');set_text(cells[1],'Nội dung sau khi chỉnh sửa theo ý kiến')
        patch_doc(ws/'results/final_vi.docx',operation)
    run('equivalent_native_table_other_vietnamese_headers',alternative_table_headers,'positive')
    def comparison_table(ws):
        table_layout(ws)
        def operation(tree):
            table=tree.find('.//'+W+'tbl');rows=table.findall(W+'tr')
            set_text(rows[0].findall(W+'tc')[1],'Nội dung đã chỉnh sửa')
            for index,row in enumerate(rows):
                cell=ET.Element(W+'tc');p=ET.SubElement(cell,W+'p');r=ET.SubElement(p,W+'r')
                identity=word_text(row.findall(W+'tc')[0]);ET.SubElement(r,W+'t').text='Nguyên văn' if index==0 else draft[identity]
                row.insert(1,cell)
        patch_doc(ws/'results/final_vi.docx',operation)
    run('equivalent_explicit_final_column_beside_original',comparison_table,'positive')
    run('ledger_correct_native_amount_wrong',lambda ws:vi(ws,'S03',draft['S03']))
    def wrong_amount_everywhere(ws):facts(ws,'S03',amount=80000000);vi(ws,'S03',draft['S03'])
    run('extra_thousand_group',wrong_amount_everywhere)
    run('malformed_native_amount_separator',lambda ws:vi(ws,'S03','Giá trị dịch vụ cho mỗi đợt là 80..000 CNY, chưa bao gồm thuế.'))
    def wrong_currency(ws):facts(ws,'S03',currency='VND');vi(ws,'S03','Giá trị dịch vụ cho mỗi đợt là 80.000 VND, chưa bao gồm thuế.')
    run('currency_changed',wrong_currency)
    def extend_date(ws):facts(ws,'S04',end_date='2027-11-30');change(ws,'S04',decision='applied');vi(ws,'S04','Thời hạn dịch vụ bắt đầu từ ngày 01/11/2026 và kết thúc vào ngày 30/11/2027.')
    run('unapproved_date_extension',extend_date)
    run('native_work_days_instead_of_hours',lambda ws:vi(ws,'S05',draft['S05']))
    def natural_hours(ws):facts(ws,'S06',handling_work_days=1,clock_origin='intake_registration');change(ws,'S06',decision='applied');vi(ws,'S06','Thời hạn xử lý là 24 giờ theo lịch kể từ khi tiếp nhận lần đầu.')
    run('calendar_hours_and_wrong_origin',natural_hours)
    run('wrong_subject_declarations',lambda ws:facts(ws,'S02',materials_provider_id='SUP-01',materials_checker_id='CLI-01'))
    run('prohibition_removed_in_fact_record',lambda ws:facts(ws,'S07',release_before_trial_allowed=True))
    run('raw_data_allowed_in_fact_record',lambda ws:facts(ws,'S08',external_raw_customer_data_allowed=True))
    run('oral_acceptance_in_fact_record',lambda ws:facts(ws,'S09',acceptance_written=False,acceptance_parties='SUP-01',oral_or_single_side_acceptance=True))
    run('term_drift_in_actual_vietnamese',lambda ws:vi(ws,'S10',draft['S10']))
    def counts_pending_completed(ws):facts(ws,'S11',completed=17);vi(ws,'S11','Có tổng cộng 17 hạng mục, trong đó 3 hạng mục chờ xác minh; số hạng mục hoàn thành là 17.')
    run('pending_counted_as_completed',counts_pending_completed)
    run('unknown_marked_completed',lambda ws:facts(ws,'S16',receipt_status='completed',acceptance_status='completed',closure_status='completed'))
    run('real_send_claim_in_facts',lambda ws:facts(ws,'S12',actual_send_allowed=True,notification_output='sent'))
    run('native_backup_changed',lambda ws:vi(ws,'S13','Người liên hệ dự phòng là Minh; lịch trực không thay đổi.'))
    def review_wrong(ws):
        def operation(tree):
            for row in tree.findall('.//'+W+'tr'):
                cells=row.findall(W+'tc')
                if cells and word_text(cells[0])=='R04':set_text(cells[2],'采用')
        patch_doc(ws/'results/review_zh.docx',operation)
    run('csv_correct_native_review_decision_wrong',review_wrong)
    run('unrelated_real_source_refs',lambda ws:change(ws,'S01',source_refs='baseline_zh.docx#S02'))
    run('wrong_existing_final_sentence_ref',lambda ws:change(ws,'S01',final_ref='final_vi.docx#S02'))
    run('wrong_existing_review_ref',lambda ws:change(ws,'S04',review_ref='review_zh.docx#R03'))
    def missing_description(ws):ledger(ws,lambda names,rows:([n for n in names if n!='explanation_zh'],rows))
    result=run('missing_description_column',missing_description);assert result['scores']['business_correctness']==1
    def missing_fact(ws):
        def operation(names,rows):
            row=next(r for r in rows if r['sentence_id']=='S16');value=json.loads(row['facts_json']);value.pop('closure_status');row['facts_json']=json.dumps(value);return names,rows
        ledger(ws,operation)
    run('missing_fact_not_known_unknown',missing_fact)
    run('duplicate_json_fact_keys',lambda ws:change(ws,'S03',facts_json='{"amount":80000000,"amount":80000,"currency":"CNY","amount_unit":"per_batch","tax_basis":"excluded"}'))
    run('missing_native_final',lambda ws:(ws/'results/final_vi.docx').unlink())
    run('damaged_native_final',lambda ws:(ws/'results/final_vi.docx').write_bytes(b'bad Word'))
    def fake_package(ws):
        path=ws/'results/final_vi.docx'
        with zipfile.ZipFile(path) as archive:parts={name:archive.read(name) for name in archive.namelist() if name not in {'[Content_Types].xml','_rels/.rels'}}
        with zipfile.ZipFile(path,'w') as archive:
            for name,data in parts.items():archive.writestr(name,data)
    run('xml_text_without_valid_word_package',fake_package)
    run('missing_chinese_review',lambda ws:(ws/'results/review_zh.docx').unlink())
    run('missing_alignment',lambda ws:(ws/'results/alignment.csv').unlink())
    result=run('all_outputs_missing',lambda ws:shutil.rmtree(ws/'results'));assert result['scores']['overall_score']==0
    run('source_baseline_changed',lambda ws:(ws/'baseline_zh.docx').write_bytes((ws/'baseline_zh.docx').read_bytes()+b'\n'))
    run('missing_private_gt',lambda ws:(ws/'gt/expected.json').unlink(),'infrastructure')
    run('missing_native_helper',lambda ws:(ws/'gt/native_docx.py').unlink(),'infrastructure')
    run('semantic_only_roles_reversed_with_same_names',lambda ws:vi(ws,'S02',draft['S02']),'semantic_boundary')
    run('semantic_only_prohibition_missing_same_literals',lambda ws:vi(ws,'S07',draft['S07']),'semantic_boundary')
    report={'schema_version':'h008-author-validation/v1','status':'PASS','control_count':len(controls),'controls':controls,
       'gt_bindings':{str(path.relative_to(gt)):sha(path) for path in sorted(gt.rglob('*')) if path.is_file() and path.name!='authoring_validation.json' and '__pycache__' not in path.parts},
       'limit':'Author rule controls and literal extraction. No independent bilingual expert review, actual semantic Judge, four-client run or calibrated difficulty.'}
    (a.output_dir/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','controls':len(controls),'scores':{name:row.get('scores',row) for name,row in controls.items()}},ensure_ascii=False))
if __name__=='__main__':main()
