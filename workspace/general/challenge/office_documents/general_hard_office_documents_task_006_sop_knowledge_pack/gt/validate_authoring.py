"""Reusable author controls; no model/Harness scores or semantic Judge claims."""
from pathlib import Path
import argparse,copy,csv,hashlib,json,os,runpy,shutil,zipfile
import xml.etree.ElementTree as ET

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def patch_doc(path,operation):
    with zipfile.ZipFile(path) as archive:files=[(item,archive.read(item.filename)) for item in archive.infolist()]
    out=[]
    for item,data in files:
        if item.filename=='word/document.xml':
            tree=ET.fromstring(data);operation(tree);data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
        out.append((item,data))
    with zipfile.ZipFile(path,'w') as archive:
        for item,data in out:archive.writestr(item,data)

def set_cell(root,identity,header,value):
    found=False
    for table in root.findall('.//'+W+'tbl'):
        rows=table.findall(W+'tr')
        labels=[''.join(n.text or '' for n in cell.iter(W+'t')) for cell in rows[0].findall(W+'tc')]
        if header not in labels:continue
        column=labels.index(header)
        for row in rows[1:]:
            cells=row.findall(W+'tc')
            if ''.join(n.text or '' for n in cells[0].iter(W+'t'))!=identity:continue
            cell=cells[column]
            for child in list(cell):
                if child.tag!=W+'tcPr':cell.remove(child)
            p=ET.SubElement(cell,W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text=value;found=True
    assert found,(identity,header)

def main():
    p=argparse.ArgumentParser();p.add_argument('--exec-root',required=True,type=Path);p.add_argument('--gt-root',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=False)
    root=a.output_dir;controls={};grader=runpy.run_path(str(a.gt_root/'grader.py'))['evaluate']
    def make(name):
        ws=root/name/'workspace';shutil.copytree(a.exec_root,ws);shutil.copytree(a.gt_root,ws/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copytree(a.gt_root/'reference/results',ws/'results');return ws
    def change_csv(ws,fn):
        path=ws/'results/coverage.csv'
        with path.open(encoding='utf-8-sig',newline='') as h:reader=csv.DictReader(h);columns=list(reader.fieldnames);rows=list(reader)
        columns,rows=fn(columns,rows)
        with path.open('w',encoding='utf-8-sig',newline='') as h:
            writer=csv.DictWriter(h,fieldnames=columns,lineterminator='\n',extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    def cell(ws,identity,**fields):
        def mutate(columns,rows):
            for row in rows:
                if row['incident_id']==identity:row.update(fields)
            return columns,rows
        change_csv(ws,mutate)
    def run(name,mutation=lambda ws:None,kind='negative'):
        ws=make(name);mutation(ws);evidence=root/name/'evidence';os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(evidence)
        before={str(path.relative_to(ws)):digest(path) for path in ws.rglob('*') if path.is_file()}
        try:r=grader(ws)
        except FileNotFoundError as exc:
            if kind!='infrastructure':raise
            controls[name]={'status':'expected_evaluation_error','error_type':type(exc).__name__};return
        if kind=='infrastructure':raise AssertionError('missing private GT must not become zero score')
        after={str(path.relative_to(ws)):digest(path) for path in ws.rglob('*') if path.is_file()}
        assert before==after,(name,'grader changed candidate Workspace')
        scores=r['scores'];assert all(0<=value<=1 for value in scores.values())
        if kind=='positive':assert abs(scores['overall_score']-1)<1e-12,(name,scores)
        else:assert scores['overall_score']<1,(name,scores)
        controls[name]={'scores':scores,'boundary_groups':r['observations']['boundary_groups'],
           'case_checks':r['observations']['case_checks'],'workspace_unchanged':True,'semantic_judge_run':False}
        return r
    run('reference',kind='positive')
    def equivalent(ws):
        contract=json.loads((a.gt_root/'artifact_contract.json').read_text(encoding='utf-8'))
        def mutate(columns,rows):
            for row in rows:
                for field in ('clearance_roles','forbidden_steps','source_refs'):row[field]=';'.join(reversed(row[field].split(';')))
                row['ack_hours']='4.0';row['route']=next(k for k,v in contract['routes'].items() if v==row['route'] and k!=v)
                row['operator_ref']='operator.docx#办理清单';row['supervisor_ref']='supervisor.docx#时限清单;supervisor.docx#权限清单'
            names={col:contract['field_aliases'][col][-1] for col in columns}
            return [names[col] for col in reversed(columns)],[{names[col]:value for col,value in row.items()} for row in reversed(rows)]
        change_csv(ws,mutate)
        for filename,replacements in [('operator.docx',{'OP-CASES':'办理清单'}),('supervisor.docx',{'SV-CASES':'权限清单','SV-CLOCK':'时限清单'})]:
            def operation(tree):
                for node in tree.iter(W+'t'):
                    for old,new in replacements.items():node.text=(node.text or '').replace(old,new)
                for table in tree.findall('.//'+W+'tbl'):
                    rows=table.findall(W+'tr')
                    # Preserve header; reverse business rows without assuming a table ordinal.
                    for row in rows[1:]:table.remove(row)
                    for row in reversed(rows[1:]):table.append(row)
            patch_doc(ws/'results'/filename,operation)
    run('equivalent_bom_aliases_order_and_sections',equivalent,'positive')
    def split_tables(ws):
        for filename in ('operator.docx','supervisor.docx'):
            def operation(tree):
                body=tree.find(W+'body')
                for table in list(body.findall(W+'tbl')):
                    rows=table.findall(W+'tr')
                    if len(rows)!=11:continue
                    other=copy.deepcopy(table)
                    for row in other.findall(W+'tr')[1:6]:other.remove(row)
                    for row in rows[6:]:table.remove(row)
                    body.insert(list(body).index(table)+1,other)
            patch_doc(ws/'results'/filename,operation)
    run('equivalent_split_native_tables',split_tables,'positive')
    def reorder_columns(ws):
        for filename in ('operator.docx','supervisor.docx'):
            def operation(tree):
                for row in tree.findall('.//'+W+'tr'):
                    cells=row.findall(W+'tc')
                    for cell in cells:row.remove(cell)
                    for cell in reversed(cells):row.append(cell)
            patch_doc(ws/'results'/filename,operation)
    run('equivalent_native_column_order',reorder_columns,'positive')
    def parallel(ws,steps):cell(ws,'I07',steps=steps)
    run('equivalent_parallel_reports',lambda w:parallel(w,'REG;DOC;PRIV_HOLD;SAFE_HOLD;PRIV_ISOLATE;PRIV_REPORT;SAFE_REPORT;JOINT_COORD'),'positive')
    run('legacy_response_clock',lambda w:cell(w,'I01',ack_hours='48'))
    run('latest_file_overrides_finance',lambda w:cell(w,'I01',payment_workdays='1'))
    def systemic_old_policy(ws):
        def mutate(columns,rows):
            for row in rows:row.update(ack_hours='48',inspection_workdays='1',payment_workdays='3')
            return columns,rows
        change_csv(ws,mutate)
        def operation(tree):
            for identity in ['I%02d'%n for n in range(1,11)]:
                for field,value in [('首响工作小时','48'),('验收工作日','1'),('资金工作日','3')]:set_cell(tree,identity,field,value)
        patch_doc(ws/'results/supervisor.docx',operation)
    r=run('systemic_legacy_clock_policy',systemic_old_policy)
    assert r['scores']['business_correctness']<.75 and r['scores']['overall_score']<.9
    run('amount_5000_owned_by_ops',lambda w:cell(w,'I02',approval_owner='OPS',next_owner='OPS'))
    def wrong_executor(ws):
        cell(ws,'I01',execution_owner='OPS');patch_doc(ws/'results/supervisor.docx',lambda t:set_cell(t,'I01','资金执行岗','OPS'))
    run('approval_is_not_execution',wrong_executor)
    run('receipt_is_not_inspection',lambda w:cell(w,'I04',route='ready_finance',next_owner='FE',clock_state='running',steps='REG;DOC;RECV;VERIFY_APPR;HANDOFF_FIN'))
    run('delete_safety_exception',lambda w:cell(w,'I05',route='ready_finance',clock_state='running',clearance_roles='N/A',steps='REG;DOC;RECV;INSPECT;VERIFY_APPR;VERIFY_BANK;HANDOFF_FIN'))
    run('joint_clearance_only_one',lambda w:cell(w,'I07',clearance_roles='QA'))
    run('reverse_dependency',lambda w:parallel(w,'REG;DOC;SAFE_REPORT;SAFE_HOLD;PRIV_HOLD;PRIV_ISOLATE;PRIV_REPORT;JOINT_COORD'))
    run('restart_existing_clock',lambda w:cell(w,'I05',clock_state='not_started',steps='REG;DOC;SAFE_HOLD;SAFE_REPORT;RESET_CLOCK'))
    run('stop_customer_response_clock',lambda w:cell(w,'I06',ack_hours='0'))
    run('duplicate_new_case',lambda w:cell(w,'I08',route='request_documents',clock_state='not_started',steps='REG;DOC;NEW_CASE;REQUEST_DOCS'))
    run('withdrawal_closes_without_fc',lambda w:cell(w,'I09',next_owner='CS',steps='REG;DOC;CLOSE_WITHOUT_FIN'))
    run('unverified_current_account',lambda w:cell(w,'I10',route='ready_finance',next_owner='FE',clock_state='running'))
    run('premature_payment_step',lambda w:cell(w,'I02',steps='REG;DOC;RECV;INSPECT;REQUEST_FIN_APPROVAL;PAY_BEFORE_GATE'))
    run('missing_forbidden_control',lambda w:cell(w,'I08',forbidden_steps='OPS_PAY;DELETE_AUDIT;CLAIM_PAID'))
    def wrong_doc(ws):patch_doc(ws/'results/operator.docx',lambda t:set_cell(t,'I05','办理路线','转财务执行'))
    run('csv_correct_docx_wrong',wrong_doc)
    def remove_column(ws,column):change_csv(ws,lambda cols,rows:([k for k in cols if k!=column],rows))
    r=run('missing_description_column',lambda w:remove_column(w,'explanation'))
    assert abs(r['scores']['business_correctness']-1)<1e-12
    r=run('missing_clearance_column',lambda w:remove_column(w,'clearance_roles'))
    assert not r['observations']['case_checks']['I01']['csv.clearance_roles'] and r['observations']['case_checks']['I01']['csv.route']
    run('existing_unrelated_section',lambda w:cell(w,'I01',operator_ref='operator.docx#OP-FLOW'))
    run('unrelated_real_sources',lambda w:cell(w,'I07',source_refs='manuals/06_compliance.docx#CO99'))
    run('missing_operator',lambda w:(w/'results/operator.docx').unlink())
    run('damaged_supervisor',lambda w:(w/'results/supervisor.docx').write_bytes(b'not office'))
    run('missing_coverage',lambda w:(w/'results/coverage.csv').unlink())
    run('all_outputs_missing',lambda w:shutil.rmtree(w/'results'))
    run('protected_source_changed',lambda w:(w/'authority.yaml').write_bytes((w/'authority.yaml').read_bytes()+b'\n'))
    run('missing_gt',lambda w:(w/'gt/expected.json').unlink(),'infrastructure')
    run('missing_grading_helper',lambda w:(w/'gt/native_text.py').unlink(),'infrastructure')
    # Intentional semantic boundary control: typed fields remain correct despite false prose.
    ws=make('semantic_only_false_paid_prose')
    def false_prose(tree):
        body=tree.find(W+'body');p=ET.Element(W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text='I05已经退款，安全风险已由运营解除。'
        body.insert(1,p)
    patch_doc(ws/'results/operator.docx',false_prose)
    os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(root/'semantic_only_false_paid_prose/evidence')
    result=grader(ws);assert abs(result['scores']['overall_score']-1)<1e-12
    controls['semantic_only_false_paid_prose']={'scores':result['scores'],'expected':'Independent semantic Judge must reject unsupported payment/release; rule is not a prose oracle.','semantic_judge_run':False}
    assertions={
      'amount_5000_owned_by_ops':('I02','csv.approval_owner'),
      'approval_is_not_execution':('I01','supervisor.execution_owner'),
      'receipt_is_not_inspection':('I04','csv.path'),
      'joint_clearance_only_one':('I07','csv.clearance_roles'),
      'reverse_dependency':('I07','csv.path'),
      'csv_correct_docx_wrong':('I05','operator.route')}
    for name,(identity,field) in assertions.items():assert not controls[name]['case_checks'][identity][field],(name,identity,field)
    bindings={str(path.relative_to(a.gt_root)):digest(path) for path in sorted(a.gt_root.rglob('*')) if path.is_file() and path.name!='authoring_validation.json' and '__pycache__' not in path.parts and path.suffix!='.pyc'}
    report={'schema_version':'h006-author-controls/v1','status':'PASS','control_count':len(controls),'controls':controls,'gt_bindings':bindings,
        'limit':'Local rule author controls. No independent semantic Judge, second-expert review, four-client execution or difficulty calibration.'}
    (root/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','controls':len(controls),'scores':{name:value.get('scores',value) for name,value in controls.items()}},ensure_ascii=False))

if __name__=='__main__':main()
