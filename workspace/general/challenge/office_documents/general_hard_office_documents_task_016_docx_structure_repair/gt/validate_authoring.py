from pathlib import Path
import copy,hashlib,json,os,runpy,shutil,sys,time,zipfile
from lxml import etree as E
import argparse
parser=argparse.ArgumentParser(description="H016 portable author controls; actual Office rendering on disposable copies")
parser.add_argument('--office-lock',type=Path);parser.add_argument('--render-lock',type=Path);parser.add_argument('--output-dir',type=Path)
parser.add_argument('--dataset-workspace',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--case',action='append',default=[]);parser.add_argument('--list-cases',action='store_true')
args=parser.parse_args()
NAMES=['reference','renamed_ids','split_runs','simple_fields','sdt_toc','merged_equal_cells','stale_native_caches','white_on_dark','omit_optional_initials','white_on_white']+['defect_'+str(i).zfill(2) for i in range(1,13)]+['changed_prose','zero_for_blank','lost_comments','moved_comment_anchor','resolved_comment','hidden_heading','static_fields','added_business_prose','missing_docx','bad_zip','invalid_log','false_locators','missing_readme','input_changed','false_GUI_claim']
if args.list_cases:
    print(json.dumps({'cases':NAMES,'count':len(NAMES)}));sys.exit(0)
if not all([args.office_lock,args.render_lock,args.output_dir]):parser.error('Office lock, render lock and external empty output directory are required')
ROOT=args.dataset_workspace.resolve();qa=args.output_dir.resolve();W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
if qa==ROOT or ROOT in qa.parents:parser.error('output directory must be outside the dataset Workspace')
if not set(args.case)<=set(NAMES):parser.error('unknown control case')
qa.mkdir(parents=True,exist_ok=False)
snapshot=qa/'frozen-author-input';shutil.copytree(ROOT/'gt',snapshot/'gt',ignore=shutil.ignore_patterns('reference','__pycache__'));shutil.copytree(ROOT/'exec',snapshot/'exec');shutil.copytree(ROOT/'gt/reference/results',snapshot/'reference')
os.environ['GENERAL_E2E_OFFICE_LOCK']=str(args.office_lock.resolve());os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']=str(args.render_lock.resolve())
e=json.loads((ROOT/'gt/expected.json').read_text())
with zipfile.ZipFile(ROOT/'exec/damaged_styles.docx') as z:damaged=E.fromstring(z.read('word/document.xml'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def rewrite(path,fn):
    with zipfile.ZipFile(path) as z:data={n:z.read(n) for n in z.namelist()}
    roots={n:E.fromstring(data[n]) for n in ['word/document.xml','word/styles.xml','word/numbering.xml','word/comments.xml']}
    fn(roots)
    for n,r in roots.items():data[n]=E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for n,b in data.items():z.writestr(n,b)
def paragraph(root,pid):return next(p for p in root.iter(W+'p') if any(n.get(W+'name')==pid for n in p.iter(W+'bookmarkStart')))
def restore_defect(roots,number):
    d=e['defects'][number-1];doc=roots['word/document.xml'];pid=d['source_paragraph_id'];p=paragraph(doc,pid) if pid else None;bad=paragraph(damaged,pid) if pid else None
    if number in [1,2,3,4,5,6]:
        pr=p.find(W+'pPr');p.replace(pr,copy.deepcopy(bad.find(W+'pPr')))
    elif number in [7,8,9,10]:
        if number==7:target=next(n for n in doc.iter(W+'instrText') if n.text.strip().startswith('TOC'));other=next(n for n in damaged.iter(W+'instrText') if n.text.strip().startswith('TOC'))
        else:target=next(p.iter(W+'instrText'));other=next(bad.iter(W+'instrText'))
        target.text=other.text
    elif number==11:
        start=next(n for n in p.iter(W+'bookmarkStart') if n.get(W+'name')=='CAP_T04');ident=start.get(W+'id');end=next(n for n in p.iter(W+'bookmarkEnd') if n.get(W+'id')==ident);start.getparent().remove(start);end.getparent().remove(end)
    elif number==12:
        link=next(n for n in doc.iter(W+'hyperlink') if n.get(W+'anchor')=='P0090');link.set(W+'anchor','P0079')
def equiv(roots):
    for part in roots.values():
        for n in part.iter():
            if n.tag==W+'style':n.set(W+'styleId','x_'+n.get(W+'styleId'))
            if n.tag in {W+'pStyle',W+'rStyle',W+'basedOn',W+'next',W+'link'}:n.set(W+'val','x_'+n.get(W+'val'))
            if n.tag==W+'abstractNum':n.set(W+'abstractNumId',str(int(n.get(W+'abstractNumId'))+1000))
            if n.tag==W+'abstractNumId':n.set(W+'val',str(int(n.get(W+'val'))+1000))
            if n.tag==W+'num':n.set(W+'numId',str(int(n.get(W+'numId'))+1000))
            if n.tag==W+'numId' and n.get(W+'val')!='0':n.set(W+'val',str(int(n.get(W+'val'))+1000))
            if n.tag in {W+'bookmarkStart',W+'bookmarkEnd',W+'comment',W+'commentRangeStart',W+'commentRangeEnd',W+'commentReference'}:n.set(W+'id',str(int(n.get(W+'id'))+2000))
            if n.tag==W+'bookmarkStart' and n.get(W+'name','').startswith('CAP_'):n.set(W+'name','Alias_'+n.get(W+'name'))
            if n.tag==W+'instrText' and n.text and 'CAP_' in n.text:n.text=n.text.replace('CAP_','Alias_CAP_')
            if n.tag==W+'comment':n.set(W+'date',n.get(W+'date').replace('08:00:00Z','16:00:00+08:00').replace('09:00:00Z','17:00:00+08:00').replace('10:00:00Z','18:00:00+08:00').replace('11:00:00Z','19:00:00+08:00').replace('12:00:00Z','20:00:00+08:00').replace('13:00:00Z','21:00:00+08:00'))
def split_runs(roots):
    for r in list(roots['word/document.xml'].iter(W+'r')):
        ts=r.findall(W+'t')
        if len(ts)==1 and len(ts[0].text or '')>4:
            t=ts[0];text=t.text;t.text=text[:len(text)//2];new=copy.deepcopy(r);new.find(W+'t').text=text[len(text)//2:];r.addnext(new)
def simple_fields(roots):
    for p in roots['word/document.xml'].iter(W+'p'):
        children=list(p);i=0
        while i<len(children):
            n=children[i];char=n.find(W+'fldChar')
            if char is None or char.get(W+'fldCharType')!='begin':i+=1;continue
            j=i+1
            while j<len(children) and not any(x.get(W+'fldCharType')=='end' for x in children[j].iter(W+'fldChar')):j+=1
            group=children[i:j+1];instruction=''.join(x.text or '' for n in group for x in n.iter(W+'instrText'))
            if instruction.strip().split()[0] not in {'SEQ','REF','PAGEREF'}:i+=1;continue
            simple=E.Element(W+'fldSimple',{W+'instr':instruction});separated=False
            for n in group:
                chars=list(n.iter(W+'fldChar'))
                if any(x.get(W+'fldCharType')=='separate' for x in chars):separated=True;continue
                if chars or not separated:continue
                simple.append(copy.deepcopy(n))
            p.insert(p.index(group[0]),simple)
            for n in group:p.remove(n)
            i=j+1

def sdt(roots):
    body=roots['word/document.xml'].find(W+'body');nodes=list(body);indices=[i for i,n in enumerate(nodes) if any('TOC ' in (x.text or '') for x in n.iter(W+'instrText'))];start=indices[0];end=start+27
    # TOC has a start paragraph, 26 entries and one end paragraph.
    chosen=nodes[start:end+1];s=E.Element(W+'sdt');content=E.SubElement(s,W+'sdtContent');body.insert(start,s)
    for n in chosen:body.remove(n);content.append(n)
def merge_cells(roots):
    t=next(t for t in roots['word/document.xml'].iter(W+'tbl') if t.find(W+'tblPr/'+W+'tblCaption').get(W+'val')=='T02')
    rows=t.findall(W+'tr')
    for i in [1,2,3]:
        cell=rows[i].findall(W+'tc')[3];pr=cell.find(W+'tcPr');E.SubElement(pr,W+'vMerge',{W+'val':'restart' if i==1 else 'continue'})
        if i>1:
            for n in cell.iter(W+'t'):n.text=''
def mutate_text(roots):next(paragraph(roots['word/document.xml'],'P0116').iter(W+'t')).text='R03已经批准。'
def moved_anchor(roots):
    doc=roots['word/document.xml'];n=next(doc.iter(W+'commentRangeStart'));n.set(W+'id','0');n.getparent().remove(n);paragraph(doc,'P0014').insert(1,n)
def hidden(roots):
    p=paragraph(roots['word/document.xml'],'P0029')
    for r in p.iter(W+'r'):
        pr=r.find(W+'rPr')
        if pr is None:pr=E.SubElement(r,W+'rPr')
        E.SubElement(pr,W+'vanish')
def static_fields(roots):
    doc=roots['word/document.xml']
    for p in doc.iter(W+'p'):
        for r in list(p):
            if r.tag==W+'r' and (r.find(W+'fldChar') is not None or r.find(W+'instrText') is not None):p.remove(r)
def extra_prose(roots):
    p=E.SubElement(roots['word/document.xml'].find(W+'body'),W+'p');r=E.SubElement(p,W+'r');E.SubElement(r,W+'t').text='R03已经批准。'
def wrong_values(roots):
    t=next(t for t in roots['word/document.xml'].iter(W+'tbl') if t.find(W+'tblPr/'+W+'tblCaption').get(W+'val')=='T03');cells=t.findall(W+'tr')[5].findall(W+'tc');next(cells[2].iter(W+'t'),None)
    p=cells[2].find(W+'p');r=E.SubElement(p,W+'r');E.SubElement(r,W+'t').text='0'
def remove_comments(roots):
    for n in list(roots['word/document.xml'].iter()):
        if n.tag in {W+'commentRangeStart',W+'commentRangeEnd',W+'commentReference'}:n.getparent().remove(n)
def resolved(roots):next(roots['word/comments.xml'].iter(W+'comment')).set(W+'done','1')
def stale_cache(roots):
    doc=roots['word/document.xml']
    for p in doc.iter(W+'p'):
        instr=''.join(n.text or '' for n in p.iter(W+'instrText'))
        if instr.strip().startswith(('SEQ','REF')):
            sep=False
            for n in p.iter():
                if n.tag==W+'fldChar':sep=n.get(W+'fldCharType')=='separate' if n.get(W+'fldCharType')!='end' else False
                if sep and n.tag==W+'t':n.text='99'
def white_on_dark(roots):
    p=paragraph(roots['word/document.xml'],'P0029');pr=p.find(W+'pPr');E.SubElement(pr,W+'shd',{W+'fill':'152D42'})
    for r in p.iter(W+'r'):
        rp=r.find(W+'rPr')
        if rp is None:rp=E.SubElement(r,W+'rPr')
        color=rp.find(W+'color')
        if color is None:color=E.SubElement(rp,W+'color')
        color.set(W+'val','FFFFFF')
def omit_initials(roots):
    for c in roots['word/comments.xml'].iter(W+'comment'):c.attrib.pop(W+'initials',None)
def white_on_white(roots):
    white_on_dark(roots);p=paragraph(roots['word/document.xml'],'P0029');p.find(W+'pPr/'+W+'shd').set(W+'fill','FFFFFF')
cases=[('reference',None,'positive'),('renamed_ids',equiv,'positive'),('split_runs',split_runs,'positive'),('simple_fields',simple_fields,'positive'),('sdt_toc',sdt,'positive'),('merged_equal_cells',merge_cells,'positive'),('stale_native_caches',stale_cache,'positive'),('white_on_dark',white_on_dark,'positive'),('omit_optional_initials',omit_initials,'positive'),('white_on_white',white_on_white,'negative')]
cases += [('defect_'+str(i).zfill(2),lambda roots,i=i:restore_defect(roots,i),'negative') for i in range(1,13)]
cases += [('changed_prose',mutate_text,'negative'),('zero_for_blank',wrong_values,'negative'),('lost_comments',remove_comments,'negative'),('moved_comment_anchor',moved_anchor,'negative'),('resolved_comment',resolved,'negative'),('hidden_heading',hidden,'negative'),('static_fields',static_fields,'negative'),('added_business_prose',extra_prose,'negative'),('missing_docx',None,'negative'),('bad_zip',None,'negative'),('invalid_log',None,'negative'),('false_locators',None,'negative'),('missing_readme',None,'negative'),('input_changed',None,'negative'),('false_GUI_claim',None,'semantic_counterexample')]
selection=set(args.case);rows=[]
for name,fn,kind in cases:
    if selection and name not in selection:continue
    target=qa/name;w=target/'workspace';shutil.copytree(snapshot/'exec',w);shutil.copytree(snapshot/'gt',w/'gt');shutil.copytree(snapshot/'reference',w/'results')
    p=w/'results/repaired.docx'
    if fn:rewrite(p,fn)
    if name=='missing_docx':p.unlink()
    if name=='bad_zip':p.write_text('not a docx')
    if name=='invalid_log':(w/'results/repair_log.json').write_text('{broken')
    if name=='false_locators':
        log=json.loads((w/'results/repair_log.json').read_text())
        for row in log['repairs']:row['source_locator']=row['result_locator']='不存在的节点'
        dump(w/'results/repair_log.json',log)
    if name=='missing_readme':(w/'results/readme.md').unlink()
    if name=='input_changed':(w/'protected_content.json').write_text('{}')
    if name=='false_GUI_claim':
        with (w/'results/readme.md').open('a') as f:f.write('\n已在Microsoft Word桌面版完成所有GUI更新并在四个客户端验证完全兼容，无须继续检查。\n')
    before={x.relative_to(w).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in w.rglob('*') if x.is_file()}
    os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(target/'derived')
    scores=runpy.run_path(str(w/'gt/grader.py'))['grade'](w)
    after={x.relative_to(w).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in w.rglob('*') if x.is_file() and '__pycache__' not in x.parts}
    assert before==after,name
    ok=scores['overall_score']==1. if kind!='negative' else scores['overall_score']<1.
    row={'name':name,'kind':kind,'status':'PASS' if ok else 'FAIL','scores':scores,'workspace_unchanged':True};rows.append(row);dump(target/'validation.json',row);print(json.dumps(row),flush=True)
dump(qa/'validation.json',{'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL','cases':rows,'limit':'Author controls, not model/Harness evaluation or independent semantic grading.'})
assert all(r['status']=='PASS' for r in rows),str(qa)
