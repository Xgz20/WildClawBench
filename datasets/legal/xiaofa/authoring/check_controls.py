"""Author controls for scoring mechanics, NOT legal gold answers or model evaluation.

Run with Python + python-docx + Pillow. Candidate code is never executed.
"""
from pathlib import Path
import contextlib, copy, io, json, runpy, shutil, tempfile, zipfile
import xml.etree.ElementTree as ET
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

ROOT=Path(__file__).resolve().parents[4]
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def rewrite_zip(path, member, transform):
    with zipfile.ZipFile(path) as z: files={n:z.read(n) for n in z.namelist()}
    files[member]=transform(files[member])
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items():z.writestr(n,b)

def positive_artifact(root, spec, oracle):
    p=root/spec['path'];p.parent.mkdir(parents=True,exist_ok=True);kind=spec.get('kind',p.suffix[1:])
    if kind=='docx':
        original=oracle.get('unchanged_doc_body',{}).get(spec['path'])
        d=Document(root/original) if original else Document()
        if not original:d.add_paragraph('评分机制正例占位文本，不是本题法律参考文书。'*30)
        for _ in range(spec.get('tables',0)):d.add_table(rows=2,cols=2)
        if spec.get('comments') and not original:
            for i in range(spec['comments']):d.add_comment(d.paragraphs[0].runs,text=f'C{i:02} 可编辑审查意见',author='control')
        elif spec.get('comments') and 'comment_update' not in oracle:
            for i in range(spec['comments']):d.add_comment(d.paragraphs[i+1].runs,text=f'C{i:02} 可编辑审查意见',author='control')
        if spec.get('tracked'):
            para=d.add_paragraph()
            for name,text in [('del','旧文'),('ins','新文')]:
                node=OxmlElement('w:'+name);node.set(qn('w:id'),'11' if name=='ins' else '10');node.set(qn('w:author'),'control')
                run=OxmlElement('w:r');t=OxmlElement('w:t' if name=='ins' else 'w:delText');t.text=text;run.append(t);node.append(run);para._p.append(node)
        d.save(p)
        if 'comment_update' in oracle and spec['path']==oracle['comment_update']['target']:
            rewrite_zip(p,'word/comments.xml',lambda b:b.replace('20%'.encode(),'30%'.encode()).replace('80%'.encode(),'70%'.encode()))
    elif kind=='png':Image.new('RGB',(30,30),'white').save(p)
    elif kind=='pdf':p.write_bytes(b'%PDF-1.4\n%%EOF\n')
    elif kind=='json':p.write_text('{}')
    else:p.write_text('评分机制正例占位文本，不是本题法律参考文书。'*30)

def main():
    rows=[];assertions=0
    for work in sorted((ROOT/'workspace/legal/xiaofa').glob('*/*')):
        if not work.is_dir():continue
        with tempfile.TemporaryDirectory(prefix='xiaofa-controls-') as tmp:
            r=Path(tmp);shutil.copytree(work/'exec',r,dirs_exist_ok=True);shutil.copytree(work/'gt',r/'gt')
            o=json.loads((r/'gt/oracle.json').read_text());module=runpy.run_path(str(r/'gt/grader.py'));fn=module['grade']
            def grade():
                with contextlib.redirect_stdout(io.StringIO()):return fn(r)
            empty=grade();assert empty['fact_accuracy']==0 and empty['delivery_integrity']==0 and empty['evidence_binding']==0 and empty['input_preservation']==1;assertions+=1
            ans={'facts':copy.deepcopy(o['facts']),'sources':{k:[{'file':v[0],'locator':'M01或题内原始对应位置'}] for k,v in o['fact_sources'].items()},'input_sha256':o['input_hashes'].copy()}
            p=r/'results/facts.json';p.parent.mkdir(exist_ok=True)
            def save():p.write_text(json.dumps(ans,ensure_ascii=False))
            for s in o['deliverables']:positive_artifact(r,s,o)
            for target,origin in o.get('copies',{}).items():
                q=r/target;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(r/origin,q)
            save();good=grade();assert good['overall_score']==1,(work.name,good);assertions+=1
            key=next(iter(ans['facts']));old=ans['facts'][key];ans['facts'][key]={'invalid':'wrong value'};save();wrong=grade();assert wrong['fact_accuracy']<1;assertions+=1;ans['facts'][key]=old
            source=next(iter(ans['input_sha256']));ans['input_sha256'][source]='0'*64
            for k,refs in ans['sources'].items():refs[0]['file']='nonexistent.txt'
            save();assert grade()['evidence_binding']==0;assertions+=1
            ans['input_sha256']=o['input_hashes'].copy();ans['sources']={k:[{'file':v[0],'locator':'M01'}] for k,v in o['fact_sources'].items()};save()
            original=r/next(iter(o['input_hashes']));blob=original.read_bytes();original.write_bytes(blob+b'changed');assert grade()['input_preservation']==0;assertions+=1;original.write_bytes(blob)
            target=r/o['deliverables'][0]['path'];blob=target.read_bytes();target.write_bytes(b'');assert grade()['delivery_integrity']<1;assertions+=1;target.write_bytes(blob)
            gt=r/'gt/oracle.json';blob=gt.read_bytes();gt.unlink()
            try:grade()
            except FileNotFoundError:pass
            else:raise AssertionError('missing GT became a candidate score')
            assertions+=1;gt.write_bytes(blob)
            if o.get('unchanged_doc_body'):
                name=next(iter(o['unchanged_doc_body']));q=r/name;d=Document(q);d.add_paragraph('未授权新增正文');d.save(q);assert grade()['delivery_integrity']<1;assertions+=1
            if o.get('comment_update'):
                positive_artifact(r,next(s for s in o['deliverables'] if s['kind']=='docx'),o)
                q=r/o['comment_update']['target'];rewrite_zip(q,'word/comments.xml',lambda b:b.replace('30%'.encode(),'20%'.encode()));assert grade()['delivery_integrity']<1;assertions+=1
            # Invalid JSON must not raise an infrastructure error.
            p.write_text('{');assert grade()['fact_accuracy']==0;assertions+=1
            rows.append({'task_id':work.name,'status':'passed','scope':'mechanics_only_not_legal_semantic_gold'})
    eq=module['equal'];assert not eq(True,1) and not eq(float('nan'),1) and not eq([1,1],[1]);assertions+=3
    result={'schema_version':1,'task_count':len(rows),'assertions':assertions,'status':'passed','limitations':'Positive artifacts are structural test doubles, not legal reference answers. No real Agent run or LLM judging performed.','tasks':rows}
    (ROOT/'datasets/legal/xiaofa/evidence/control_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='tasks'},ensure_ascii=False))

if __name__=='__main__':main()
