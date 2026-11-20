"""Real Office author controls; semantic examples are expectations, not fabricated Judge results."""
from pathlib import Path
import argparse,csv,hashlib,json,os,shutil,subprocess,sys,time,zipfile
import xml.etree.ElementTree as ET

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def inventory(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
def csv_change(path,action,bom=False):
    with path.open(newline='') as f:
        reader=csv.DictReader(f);columns=reader.fieldnames;rows=list(reader)
    action(rows)
    if bom:columns=list(reversed(columns))+['note'];rows=[dict(x,note='handoff') for x in rows]
    with path.open('w',newline='',encoding='utf-8-sig' if bom else 'utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=columns,lineterminator='\r\n' if bom else '\n');writer.writeheader();writer.writerows(rows)
def word_change(path,action):
    with zipfile.ZipFile(path) as z:
        members=[(i,z.read(i.filename)) for i in z.infolist()]
    root=ET.fromstring(dict((i.filename,b) for i,b in members)['word/document.xml']);action(root)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for info,data in members:z.writestr(info,ET.tostring(root,encoding='utf-8',xml_declaration=True) if info.filename=='word/document.xml' else data)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path);parser.add_argument('--runtime-lock',required=True,type=Path);args=parser.parse_args()
    source=args.source_root.resolve();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    lock=json.loads(args.runtime_lock.read_text());dump(out/'office.json',lock['office_runtime']);dump(out/'render.json',lock['office_render_runtime'])
    cases=[('reference','positive'),('csv_reordered_bom_extra_column','positive'),('word_topic_order','positive'),
      ('wrong_upload_total_route','negative'),('refund_boundary_wrong_route','negative'),('per_file_boundary_wrong_route','negative'),
      ('wrong_locale','negative'),('missing_reply','negative'),('duplicate_reply','negative'),('empty_reply','negative'),
      ('wrong_source','negative'),('nonexistent_source','negative'),('missing_FAQ','negative'),('missing_word','negative'),('corrupt_word','negative'),('hidden_word_body','negative'),('input_changed','negative'),
      ('semantic_refund_promise','semantic_only'),('semantic_unknown_zero','semantic_only'),('semantic_wrong_stable','semantic_only'),('semantic_same_ids_garbage','semantic_only'),
      ('missing_GT','infrastructure'),('missing_helper','infrastructure'),('missing_runtime','infrastructure'),('render_lock_drift','infrastructure')]
    reports=[]
    for name,kind in cases:
        case=out/name;case.mkdir();work=case/'workspace'
        shutil.copytree(source/'exec',work);shutil.copytree(source/'gt',work/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copytree(source/'gt/reference/results',work/'results')
        cp=work/'results/case_replies.csv';en=work/'results/faq_en.docx'
        def row_action(identity,key,value):return lambda rows:next(r for r in rows if r['case_id']==identity).__setitem__(key,value)
        if name=='csv_reordered_bom_extra_column':csv_change(cp,lambda rows:rows.reverse(),True)
        if name=='word_topic_order':
            def reorder(root):
                body=root.find(W+'body');paras=body.findall(W+'p');assert len(paras)==39
                chunks=[paras[i:i+3] for i in range(3,39,3)]
                for p in paras[3:]:body.remove(p)
                index=list(body).index(body.find(W+'sectPr'))
                for p in [p for chunk in reversed(chunks) for p in chunk]:body.insert(index,p);index+=1
            word_change(en,reorder)
        changes={'wrong_upload_total_route':('C02','decision','supported'),'refund_boundary_wrong_route':('C12','decision','standard_policy_not_met'),
                 'per_file_boundary_wrong_route':('C13','decision','supported'),'wrong_locale':('C12','locale','zh'),
                 'empty_reply':('C04','reply',''),'wrong_source':('C02','source_refs','release_notes.md#F12'),'nonexistent_source':('C02','source_refs','release_notes.md#F99'),
                 'semantic_refund_promise':('C12','reply','An immediate full refund is guaranteed and has already been approved. It will arrive within two business days.'),
                 'semantic_unknown_zero':('C18','reply','Số tiền hoàn đã được xác nhận là 0 CNY; mọi đơn mua qua đại lý đều không được hoàn tiền.')}
        if name in changes:csv_change(cp,row_action(*changes[name]))
        if name=='missing_reply':csv_change(cp,lambda rows:rows.pop())
        if name=='duplicate_reply':csv_change(cp,lambda rows:rows.append(dict(rows[2])))
        if name=='missing_FAQ':
            def remove(root):
                body=root.find(W+'body');paras=body.findall(W+'p')
                for p in paras[24:27]:body.remove(p)
            word_change(en,remove)
        if name=='missing_word':(work/'results/faq_vi.docx').unlink()
        if name=='corrupt_word':(work/'results/faq_zh.docx').write_bytes(b'not-a-docx')
        if name=='hidden_word_body':
            def hide(root):
                for p in root.find(W+'body').iter(W+'p'):
                    for run in p.findall(W+'r'):
                        props=run.find(W+'rPr')
                        if props is None:props=ET.Element(W+'rPr');run.insert(0,props)
                        ET.SubElement(props,W+'vanish')
            word_change(en,hide)
        if name=='input_changed':(work/'release_notes.md').write_text('altered source')
        if name=='semantic_wrong_stable':
            def wrong(root):
                para=root.find(W+'body').findall(W+'p')[4];texts=list(para.iter(W+'t'));texts[0].text='3.2.1 is the current stable release on every platform. All accounts are already enrolled.'
                for node in texts[1:]:node.text=''
            word_change(en,wrong)
        if name=='semantic_same_ids_garbage':
            def garbage(root):
                ps=root.find(W+'body').findall(W+'p')
                for i in range(4,39,3):
                    ts=list(ps[i].iter(W+'t'));ts[0].text='NoriDesk support text without any usable policy answer.'
                    for node in ts[1:]:node.text=''
            word_change(en,garbage)
        if name=='missing_GT':(work/'gt/expected.json').unlink()
        if name=='missing_helper':(work/'gt/artifact_io.py').unlink()
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','GENERAL_E2E_OFFICE_LOCK':str(out/'office.json'),'GENERAL_E2E_OFFICE_RENDER_LOCK':str(out/'render.json'),'GENERAL_E2E_RULE_EVIDENCE_DIR':str(case/'derived')}
        if name=='missing_runtime':env.pop('GENERAL_E2E_OFFICE_RENDER_LOCK')
        if name=='render_lock_drift':
            bad=json.loads((out/'render.json').read_text());bad['fonts'][0]['sha256']='0'*64;dump(case/'bad-render.json',bad);env['GENERAL_E2E_OFFICE_RENDER_LOCK']=str(case/'bad-render.json')
        before=inventory(work);start=time.monotonic()
        command=[sys.executable,'-B','-c',"from pathlib import Path; import json,runpy,sys; r=Path(sys.argv[1]); print(json.dumps(runpy.run_path(str(r/'gt/grader.py'))['grade'](r)))",str(work)]
        result=subprocess.run(command,env=env,text=True,capture_output=True,timeout=600)
        (case/'stdout.txt').write_text(result.stdout);(case/'stderr.txt').write_text(result.stderr)
        unchanged=inventory(work)==before
        if kind=='infrastructure':
            assert result.returncode!=0 and unchanged,(name,result.stdout,result.stderr[-1000:]);scores=None
        else:
            assert result.returncode==0,(name,result.stderr[-1800:])
            scores=json.loads(result.stdout);assert unchanged,name
            if kind in {'positive','semantic_only'}:assert scores['overall_score']==1.,(name,scores)
            else:assert scores['overall_score']<1.,(name,scores)
        rec={'name':name,'kind':kind,'scores':scores,'returncode':result.returncode,'workspace_unchanged':unchanged,'elapsed_seconds':round(time.monotonic()-start,3),
             'semantic_judge_score':None,'semantic_expected':0. if kind=='semantic_only' else None,
             'grader_sha256':sha(source/'gt/grader.py'),'input_inventory_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()}
        dump(case/'result.json',rec);reports.append(rec);print(json.dumps({'name':name,'kind':kind,'score':scores and scores['overall_score'],'ok':True}),flush=True)
    summary={'status':'AUTHOR_CONTROLS_PASS','cases':reports,'counts':{kind:sum(r['kind']==kind for r in reports) for kind in ['positive','negative','semantic_only','infrastructure']},
             'limit':'Actual Word/PDF and CSV author controls. Semantic-only fixtures verify the declared rule boundary; expected semantic failures are not independent Judge scores or Harness results.'}
    dump(out/'validation.json',summary)
if __name__=='__main__':main()
