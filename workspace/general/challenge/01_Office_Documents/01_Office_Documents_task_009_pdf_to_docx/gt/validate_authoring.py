"""Real native/Writer controls on disposable synthetic copies; no model scoring."""
from pathlib import Path
from copy import deepcopy
import argparse,csv,hashlib,json,os,re,runpy,shutil,zipfile
from lxml import etree

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def text(node):return ''.join(n.text or '' for n in node.iter(W+'t'))
def rewrite(path,operation):
    with zipfile.ZipFile(path) as archive:parts={item.filename:archive.read(item) for item in archive.infolist()}
    operation(parts)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():archive.writestr(name,data)
def xml_edit(path,operation):
    def edit(parts):
        root=etree.fromstring(parts['word/document.xml']);operation(root)
        parts['word/document.xml']=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    rewrite(path,edit)
def set_text(node,value):
    leaves=list(node.iter(W+'t'));assert leaves
    leaves[0].text=value
    for leaf in leaves[1:]:leaf.text=''
def row_of(root,uid):
    found=[r for r in root.findall('.//'+W+'tr') if any(text(c)==uid for c in r.findall(W+'tc'))]
    assert len(found)==1,(uid,len(found));return found[0]
def paragraph(root,uid):
    found=[p for p in root.findall('.//'+W+'body/'+W+'p') if text(p).startswith('['+uid+']')]
    assert len(found)==1;return found[0]
def ledger(path,operation):
    with path.open(encoding='utf-8-sig',newline='') as handle:reader=csv.DictReader(handle);fields=reader.fieldnames;rows=list(reader)
    operation(rows)
    with path.open('w',encoding='utf-8',newline='') as handle:writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(rows)
def change_ledger(ws,identity,**values):
    ledger(ws/'results/conversion_audit.csv',lambda rows:next(r for r in rows if r['source_id']==identity).update(values))
def doc(ws):return ws/'results/converted.docx'

def split_t02(ws):
    def operation(root):
        table=row_of(root,'R01').getparent();a=deepcopy(table);b=deepcopy(table)
        for tr in list(a.findall(W+'tr'))[11:]:a.remove(tr)
        for tr in list(b.findall(W+'tr'))[2:11]:b.remove(tr)
        first=list(b.findall(W+'tr'))[2].find(W+'tc')
        merge=first.find(W+'tcPr/'+W+'vMerge');assert merge is not None;merge.set(W+'val','restart')
        original=row_of(root,'R07').find(W+'tc');newp=deepcopy(original.find(W+'p'))
        set_text(newp,'追加复核（续）')
        for p in first.findall(W+'p'):first.remove(p)
        first.append(newp)
        parent=table.getparent();index=parent.index(table);parent.remove(table);parent.insert(index,a);parent.insert(index+1,b)
    xml_edit(doc(ws),operation)
    def refs(rows):
        for row in rows:
            if row['source_id']=='T02':row['target_locator']='table:2;table:3'
            elif row['source_id']=='T03':row['target_locator']='table:4'
            elif row['source_id']=='T04':row['target_locator']='table:5'
    ledger(ws/'results/conversion_audit.csv',refs)

def refine_grid(ws):
    def operation(root):
        for table in root.iter(W+'tbl'):
            grid=table.find(W+'tblGrid');old=list(grid)
            for c in old:grid.remove(c)
            for c in old:
                width=int(c.get(W+'w'));assert width%2==0
                for _ in range(2):item=deepcopy(c);item.set(W+'w',str(width//2));grid.append(item)
            for cell in table.findall(W+'tr/'+W+'tc'):
                cp=cell.find(W+'tcPr');span=cp.find(W+'gridSpan')
                if span is None:span=etree.SubElement(cp,W+'gridSpan');span.set(W+'val','1')
                span.set(W+'val',str(int(span.get(W+'val'))*2))
    xml_edit(doc(ws),operation)

def note_ids(ws):
    mapping={'1':'106','2':'101','3':'145','4':'120','5':'102','6':'177'}
    def operation(parts):
        for name in ['word/document.xml','word/footnotes.xml']:
            root=etree.fromstring(parts[name])
            for node in root.iter():
                if node.tag in {W+'footnoteReference',W+'footnote'} and node.get(W+'id') in mapping:node.set(W+'id',mapping[node.get(W+'id')])
            parts[name]=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    rewrite(doc(ws),operation)
    ledger(ws/'results/conversion_audit.csv',lambda rows:[row.update(target_locator='footnote:'+mapping[row['target_locator'].split(':')[1]]) for row in rows if row['source_id'].startswith('F')])

def local_widths(ws):
    refine_grid(ws)
    def operation(root):
        cells=row_of(root,'R04').findall(W+'tc')
        cells[2].find(W+'tcPr/'+W+'gridSpan').set(W+'val','1')
        cells[3].find(W+'tcPr/'+W+'gridSpan').set(W+'val','3')
    xml_edit(doc(ws),operation)

def one_local_split(ws):
    refine_grid(ws)
    def operation(root):
        row=row_of(root,'R04');cell=row.findall(W+'tc')[2]
        cell.find(W+'tcPr/'+W+'gridSpan').set(W+'val','1')
        extra=deepcopy(cell);set_text(extra,'');cell.addnext(extra)
    xml_edit(doc(ws),operation)

def paragraph_equivalence(ws):
    def operation(root):
        p=paragraph(root,'S01');q=deepcopy(p);value=text(p);cut=len(value)//2;set_text(p,value[:cut]);set_text(q,value[cut:]);p.addnext(q)
        a=paragraph(root,'S10');b=paragraph(root,'S11');set_text(a,text(a)+' '+text(b));b.getparent().remove(b)
    xml_edit(doc(ws),operation)
    # Read actual physical indices, not expected source values, to construct
    # this equivalent author's audit. Source labels stay unchanged.
    with zipfile.ZipFile(doc(ws)) as archive:root=etree.fromstring(archive.read('word/document.xml'))
    source={};index=0;current=None
    expected=json.loads((ws/'gt/expected.json').read_text())
    for node in root.find(W+'body'):
        if node.tag!=W+'p':current=None;continue
        index+=1;value=text(node);ids=re.findall(r'\[(S\d{2})\]',value)
        exact=next((key for key,record in expected['paragraphs'].items() if key=='S00' or key.startswith('H') if value==record['text']),None)
        if exact:source[exact]=[f'paragraph:{index}'];current=None
        elif ids:
            for key in ids:source.setdefault(key,[]).append(f'paragraph:{index}')
            current=ids[-1]
        elif value.startswith('[T'):current=None
        elif value.strip() and current:source[current].append(f'paragraph:{index}')
    ledger(ws/'results/conversion_audit.csv',lambda rows:[row.update(target_locator=';'.join(source[row['source_id']])) for row in rows if row['source_id'] in source])

def csv_equivalence(ws):
    path=ws/'results/conversion_audit.csv'
    with path.open(encoding='utf-8',newline='') as handle:rows=list(csv.DictReader(handle))
    aliases={'source_id':'源编号','source_pages':'源页','source_locator':'源定位','target_locator':'目标节点','status':'状态','issue':'问题'}
    fields=list(reversed(list(aliases.values())))
    with path.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for row in reversed(rows):
            row['source_pages']=row['source_pages'].replace('2;3','2-3');row['status']='已转换';row['target_locator']='converted.docx#'+row['target_locator']
            writer.writerow({aliases[key]:value for key,value in row.items()})

def wrong_columns(ws):
    def operation(root):
        for index in range(1,19):
            cells=row_of(root,f'R{index:02d}').findall(W+'tc');a,b=cells[2],cells[3]
            left=[deepcopy(n) for n in a if n.tag!=W+'tcPr'];right=[deepcopy(n) for n in b if n.tag!=W+'tcPr']
            for cell in [a,b]:
                for n in list(cell):
                    if n.tag!=W+'tcPr':cell.remove(n)
            a.extend(right);b.extend(left)
    xml_edit(doc(ws),operation)

def move_note(ws,kind):
    def operation(root):
        if kind=='cell':a=row_of(root,'R04').findall(W+'tc')[3];b=row_of(root,'R05').findall(W+'tc')[3]
        else:a=paragraph(root,'S13');b=paragraph(root,'S14')
        ref=next(a.iter(W+'footnoteReference'));run=ref.getparent();run.getparent().remove(run)
        (b if b.tag==W+'p' else b.find(W+'p')).append(run)
    xml_edit(doc(ws),operation)

def unmerge_m05(ws):
    def operation(root):
        row=row_of(root,'M05');cell=row.findall(W+'tc')[1];row.remove(cell)
        for width in [142,80,210]:
            new=deepcopy(cell);cp=new.find(W+'tcPr');cp.remove(cp.find(W+'gridSpan'));cp.find(W+'tcW').set(W+'w',str(width*20));row.append(new)
    xml_edit(doc(ws),operation)

def plain_notes(ws):
    def operation(parts):
        root=etree.fromstring(parts['word/document.xml']);body=root.find(W+'body');notes=etree.fromstring(parts['word/footnotes.xml'])
        for ref in list(root.iter(W+'footnoteReference')):ref.getparent().remove(ref)
        for note in notes:
            if int(note.get(W+'id'))>0:
                for p in note.findall(W+'p'):body.insert(len(body)-1,deepcopy(p))
        parts['word/document.xml']=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    rewrite(doc(ws),operation)

def body_order_wrong(ws):
    def operation(root):
        p=paragraph(root,'S12');parent=p.getparent();parent.remove(p);paragraph(root,'S14').addnext(p)
    xml_edit(doc(ws),operation)
def mutate_text(ws,uid,old,new,column=5):
    def operation(root):
        cell=row_of(root,uid).findall(W+'tc')[column];set_text(cell,text(cell).replace(old,new))
    xml_edit(doc(ws),operation)
def bad_font(ws):
    def operation(root):
        for run in row_of(root,'R13').findall(W+'tc')[3].iter(W+'r'):
            if run.find(W+'footnoteReference') is not None:continue
            props=run.find(W+'rPr')
            if props is None:props=etree.SubElement(run,W+'rPr')
            item=props.find(W+'sz')
            if item is None:item=etree.SubElement(props,W+'sz')
            item.set(W+'val','12')
    xml_edit(doc(ws),operation)
def too_wide(ws):
    def operation(root):
        table=row_of(root,'R01').getparent()
        for col in table.find(W+'tblGrid'):col.set(W+'w',str(int(col.get(W+'w'))*2))
        for cell in table.findall(W+'tr/'+W+'tc'):
            width=cell.find(W+'tcPr/'+W+'tcW');width.set(W+'w',str(int(width.get(W+'w'))*2))
    xml_edit(doc(ws),operation)

def image_substitution(ws):
    from docx import Document
    from docx.shared import Mm
    import pypdfium2
    document=Document();section=document.sections[0]
    section.page_width=Mm(210);section.page_height=Mm(297)
    section.left_margin=section.right_margin=section.top_margin=section.bottom_margin=Mm(10)
    folder=ws.parent/'image-fixture';folder.mkdir()
    pdf=pypdfium2.PdfDocument(ws/'source.pdf')
    for index in range(len(pdf)):
        page=pdf[index];bitmap=page.render(scale=1.);image=bitmap.to_pil();path=folder/f'page-{index}.png';image.save(path)
        p=document.add_paragraph();p.paragraph_format.space_after=0;p.add_run().add_picture(str(path),width=Mm(185))
        if index+1<len(pdf):document.add_page_break()
        bitmap.close();page.close()
    pdf.close();document.save(doc(ws))

def hidden_text(ws):
    def operation(root):
        for run in root.iter(W+'r'):
            props=run.find(W+'rPr')
            if props is None:props=etree.SubElement(run,W+'rPr')
            etree.SubElement(props,W+'vanish')
    xml_edit(doc(ws),operation)

def missing_opc(ws):
    rewrite(doc(ws),lambda parts:[parts.pop(name) for name in ['[Content_Types].xml','_rels/.rels']])
def missing_audit_header(ws):
    path=ws/'results/conversion_audit.csv'
    with path.open(encoding='utf-8',newline='') as handle:reader=csv.DictReader(handle);rows=list(reader);fields=reader.fieldnames
    fields.remove('target_locator')
    with path.open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exec-root',required=True,type=Path);parser.add_argument('--gt-root',required=True,type=Path)
    parser.add_argument('--render-lock',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--native-only',action='store_true');args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=False)
    n=runpy.run_path(str(args.gt_root/'native_checks.py'));expected=json.loads((args.gt_root/'expected.json').read_text())
    controls={}
    cases=[('reference',lambda ws:None,'positive'),('csv_bom_aliases_ranges',csv_equivalence,'positive'),
      ('native_continuation_tables',split_t02,'positive'),('arbitrary_note_package_ids',note_ids,'positive'),
      ('finer_column_grid',refine_grid,'positive'),('paragraph_split_and_merge',paragraph_equivalence,'positive'),
      ('row_local_column_widths',local_widths,'positive'),('one_local_split_preserves_other_rows',one_local_split,'negative'),
      ('same_text_wrong_numeric_columns',wrong_columns,'negative'),('same_price_wrong_note_row',lambda ws:move_note(ws,'cell'),'negative'),
      ('same_amount_wrong_note_paragraph',lambda ws:move_note(ws,'paragraph'),'negative'),('text_right_horizontal_merge_lost',unmerge_m05,'negative'),
      ('plain_note_list',plain_notes,'negative'),('source_paragraph_order',body_order_wrong,'negative'),
      ('wrong_single_amount',lambda ws:mutate_text(ws,'R13','105.00','999.00',4),'negative'),
      ('unknown_not_zero',lambda ws:mutate_text(ws,'X06','未提供','0',3),'negative'),
      ('audit_wrong_actual_node',lambda ws:change_ledger(ws,'T02',target_locator='table:1'),'negative'),
      ('audit_one_piece_not_whole_table',lambda ws:(split_t02(ws),change_ledger(ws,'T02',target_locator='table:2')),'negative'),
      ('wrong_source_page',lambda ws:change_ledger(ws,'F06',source_pages='4'),'negative'),
      ('wrong_source_locator',lambda ws:change_ledger(ws,'F06',source_locator='source.pdf#page:5/S14'),'negative'),
      ('too_small_price',bad_font,'render_negative'),('table_outside_page',too_wide,'render_negative'),
      ('page_images_not_native',image_substitution,'negative'),('native_text_hidden',hidden_text,'render_negative'),
      ('missing_native_opc',missing_opc,'negative'),('missing_audit_target_header',missing_audit_header,'negative'),
      ('missing_word',lambda ws:doc(ws).unlink(),'negative'),('damaged_word',lambda ws:doc(ws).write_bytes(b'not Word'),'negative'),
      ('missing_csv',lambda ws:(ws/'results/conversion_audit.csv').unlink(),'negative'),
      ('all_missing',lambda ws:shutil.rmtree(ws/'results'),'negative'),
      ('input_modified',lambda ws:(ws/'layout_contract.json').write_bytes((ws/'layout_contract.json').read_bytes()+b'\n'),'negative'),
      ('missing_gt',lambda ws:(ws/'gt/expected.json').unlink(),'infrastructure'),
      ('missing_helper',lambda ws:(ws/'gt/word_model.py').unlink(),'infrastructure')]
    for name,operation,kind in cases:
        root=args.output_dir/name;ws=root/'workspace';shutil.copytree(args.exec_root,ws)
        shutil.copytree(args.gt_root,ws/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copytree(args.gt_root/'reference/results',ws/'results')
        operation(ws);before={str(p.relative_to(ws)):sha(p) for p in ws.rglob('*') if p.is_file()}
        os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']=str(args.render_lock);os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(root/'evidence')
        if args.native_only:
            if kind=='infrastructure':continue
            try:observed=n['analyze'](n['read_document'](doc(ws)),expected)
            except n['CandidateWordError']:observed=None
            if kind=='positive':assert observed and all(observed['full_units'].values()),(name,observed)
            report={'kind':kind,'native_all_units':bool(observed and all(observed['full_units'].values())),
                'native_notes':(observed or {}).get('note_checks'), 'native_table_scores':(observed or {}).get('table_scores')}
        else:
            grader=runpy.run_path(str(ws/'gt/grader.py'))
            try:scores=grader['grade'](ws)
            except (FileNotFoundError,RuntimeError,ValueError) as exc:
                if kind!='infrastructure':raise
                report={'kind':kind,'error_type':type(exc).__name__,'error':str(exc),'score_created':False}
            else:
                if kind=='infrastructure':raise AssertionError('missing GT/helper silently scored: '+name)
                if kind=='positive':assert abs(scores['overall_score']-1)<1e-12,(name,scores)
                else:assert scores['overall_score']<1,(name,scores)
                if name=='all_missing':assert scores['overall_score']==0.
                observation=json.loads((root/'evidence/h009-analysis.json').read_text())
                if name=='same_price_wrong_note_row':assert observation['native']['note_checks']['F02']['attachment']==0
                if name=='same_amount_wrong_note_paragraph':assert observation['native']['note_checks']['F06']['attachment']==0
                if name=='one_local_split_preserves_other_rows':
                    checks=observation['native']['table_values']['T02']
                    assert all(checks[f'6:{c}']==1 for c in range(6)),checks
                    assert observation['native']['table_scores']['T02']>.9
                report={'kind':kind,'scores':scores,'native_notes':observation['native'].get('note_checks'),
                    'render_status':(observation['render'] or {}).get('status'),'render_fit':(observation['render'] or {}).get('basic_fit'),
                    'render_small_text':(observation['render'] or {}).get('small_text_count'),'render_outside':(observation['render'] or {}).get('out_of_page_count')}
        after={str(p.relative_to(ws)):sha(p) for p in ws.rglob('*') if p.is_file()};assert before==after,name
        report['workspace_unchanged']=True;controls[name]=report
        (root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'control':name,'status':'pass','score':report.get('scores',{}).get('overall_score')},ensure_ascii=False),flush=True)
    summary={'schema_version':'h009-author-controls/v1','status':'NATIVE_PROBES_PASS' if args.native_only else 'AUTHOR_CONTROLS_PASS',
        'control_count':len(controls),'controls':controls,
        'gt_bindings':{str(p.relative_to(args.gt_root)):sha(p) for p in sorted(args.gt_root.rglob('*')) if p.is_file() and p.name!='authoring_validation.json' and '__pycache__' not in p.parts},
        'limit':'Author controls, not actual Harness or independent semantic scores. Native-only probes do not prove actual render behavior.'}
    (args.output_dir/'validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':summary['status'],'controls':len(controls)},ensure_ascii=False))
if __name__=='__main__':main()
