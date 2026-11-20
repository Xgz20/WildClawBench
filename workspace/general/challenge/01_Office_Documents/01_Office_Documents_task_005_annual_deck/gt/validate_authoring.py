"""Real-Office author controls, never a Harness run or a semantic score."""
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
import argparse,csv,hashlib,io,json,os,re,runpy,shutil,tempfile,zipfile
import xml.etree.ElementTree as E

P='{http://schemas.openxmlformats.org/presentationml/2006/main}'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
C='{http://schemas.openxmlformats.org/drawingml/2006/chart}'
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def parts(path):
    with zipfile.ZipFile(path) as archive:return {name:archive.read(name) for name in archive.namelist()}
def write(path,content):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,value in content.items():archive.writestr(name,value)
def rounded(value):return str(Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
def alter_ledger(path,changes=None,drop_header=None,equivalent=False):
    with path.open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.DictReader(handle))
    fields=list(rows[0])
    if changes:
        for row in rows:
            if row['kpi_id'] in changes:row['value']=changes[row['kpi_id']]
    if drop_header:fields.remove(drop_header)
    if equivalent:
        fields=list(reversed(fields));rows=list(reversed(rows))
        for row in rows:
            row['source_cells']=re.sub(r'([A-Z]+)(\d+)',lambda m:'$'+m[1].lower()+'$'+m[2],row['source_cells'])
            row['slide']=row['slide']+'.0';row['kpi_id']=row['kpi_id'].lower()
    with path.open('w',encoding='utf-8-sig' if equivalent else 'utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

def alter_metrics(path,changes,truth,is_word=False):
    content=parts(path);namespace=W if is_word else A
    for name,raw in list(content.items()):
        if not (name=='word/document.xml' if is_word else re.fullmatch(r'ppt/slides/slide\d+\.xml',name)):continue
        root=E.fromstring(raw);nodes=list(root.iter(namespace+'t'));texts=[node.text or '' for node in nodes]
        for identity,new in changes.items():
            old=next(item['value'] for item in truth['kpis'] if item['kpi_id']==identity)
            formats=[old,format(Decimal(old),',.2f')]
            for index,text in enumerate(texts):
                if not re.search(r'(?<![A-Za-z0-9])'+identity+r'(?!\d)',text):continue
                for node in nodes[index:index+4]:
                    changed=False
                    for value in formats:
                        if value in (node.text or ''):node.text=node.text.replace(value,format(Decimal(new),',.2f') if ',' in value else new,1);changed=True;break
                    if changed:break
        content[name]=E.tostring(root,encoding='utf-8',xml_declaration=True)
    write(path,content)

def alter_pptx(path,variant):
    content=parts(path)
    if variant in {'wrong_embedded_formula_correct_cache','equivalent_formula','wrong_embedded_literal'}:
        name=next(name for name in content if name.endswith('.xlsx'))
        with zipfile.ZipFile(io.BytesIO(content[name])) as archive:book={key:archive.read(key) for key in archive.namelist()}
        sheet=next(key for key in book if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',key))
        root=E.fromstring(book[sheet]);cell=next(cell for cell in root.iter(S+'c') if cell.get('r')=='B2')
        cached=cell.find(S+'v');assert cached is not None and float(cached.text)==160
        if variant=='wrong_embedded_literal':cached.text='999'
        else:E.SubElement(cell,S+'f').text='80*2' if variant=='equivalent_formula' else '1+1'
        book[sheet]=E.tostring(root,encoding='utf-8',xml_declaration=True)
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            for key,value in book.items():archive.writestr(key,value)
        content[name]=buffer.getvalue()
    elif variant=='wrong_chart_cache':
        name=next(name for name in content if re.fullmatch(r'ppt/(?:slides/)?charts/chart\d+\.xml',name))
        root=E.fromstring(content[name]);node=root.find(f'.//{C}ser/{C}val/{C}numRef/{C}numCache/{C}pt/{C}v')
        assert node is not None;node.text='999';content[name]=E.tostring(root,encoding='utf-8',xml_declaration=True)
    else:
        for name,raw in list(content.items()):
            if not re.fullmatch(r'ppt/slides/slide\d+\.xml',name):continue
            root=E.fromstring(raw);tree=root.find(f'{P}cSld/{P}spTree')
            if variant=='font_too_small':
                for node in root.iter():
                    if node.tag in {A+'rPr',A+'defRPr',A+'endParaRPr'} and node.get('sz'):node.set('sz','1000')
            elif variant=='text_overflow' and name.endswith('slide2.xml'):
                for shape in tree.findall(P+'sp'):
                    if 'K01' in ''.join(x.text or '' for x in shape.iter(A+'t')):
                        transform=shape.find(f'{P}spPr/{A}xfrm');transform.find(A+'off').set('x','12500000');break
            elif variant=='equivalent_order':
                drawings=[x for x in tree if x.tag in {P+'sp',P+'graphicFrame',P+'pic'}]
                for node in drawings:tree.remove(node)
                for node in reversed(drawings):tree.append(node)
            content[name]=E.tostring(root,encoding='utf-8',xml_declaration=True)
    write(path,content)

def rasterize(path,pdf_path):
    import pdfplumber
    content=parts(path)
    with pdfplumber.open(pdf_path) as document:
        for index,page in enumerate(document.pages,1):
            name=f'ppt/slides/slide{index}.xml';root=E.fromstring(content[name]);tree=root.find(f'{P}cSld/{P}spTree')
            for child in list(tree):
                if child.tag in {P+'sp',P+'graphicFrame',P+'pic'}:tree.remove(child)
            picture=E.fromstring(f'''<p:pic xmlns:p="{P[1:-1]}" xmlns:a="{A[1:-1]}" xmlns:r="{R}"><p:nvPicPr><p:cNvPr id="9001" name="author-control-raster"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rRaster"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="12192000" cy="6858000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>''')
            tree.append(picture);content[name]=E.tostring(root,encoding='utf-8',xml_declaration=True)
            rel=f'ppt/slides/_rels/slide{index}.xml.rels';rels=E.fromstring(content[rel])
            E.SubElement(rels,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',{'Id':'rRaster','Type':R+'/image','Target':f'../media/raster-{index}.png'})
            E.register_namespace('','http://schemas.openxmlformats.org/package/2006/relationships')
            content[rel]=E.tostring(rels,encoding='utf-8',xml_declaration=True)
            image=page.to_image(resolution=96).original;buffer=io.BytesIO();image.save(buffer,format='PNG');content[f'ppt/media/raster-{index}.png']=buffer.getvalue()
    types=E.fromstring(content['[Content_Types].xml'])
    if not any(node.get('Extension')=='png' for node in types):E.SubElement(types,'{http://schemas.openxmlformats.org/package/2006/content-types}Default',{'Extension':'png','ContentType':'image/png'})
    E.register_namespace('','http://schemas.openxmlformats.org/package/2006/content-types')
    content['[Content_Types].xml']=E.tostring(types,encoding='utf-8',xml_declaration=True);write(path,content)

def validate(exec_root,gt_root,office_lock,render_lock,output,selected=None):
    truth=json.loads((gt_root/'expected.json').read_text(encoding='utf-8'));raw=json.loads((gt_root/'source_facts.json').read_text(encoding='utf-8'))
    grader=runpy.run_path(str(gt_root/'grader.py'))['evaluate'];output.mkdir(parents=True,exist_ok=False)
    variants=['reference','equivalent_order','equivalent_formula','zero_override','unit_mismatch','mean_of_rates','include_future_invoices','include_day30',
      'ledger_only_correct','wrong_chart_cache','wrong_embedded_formula_correct_cache','wrong_embedded_literal','rasterized_slides','font_too_small','text_overflow',
      'missing_description_header','wrong_evidence','missing_pptx','missing_ledger','missing_notes','missing_all','corrupt_pptx','changed_input','missing_gt']
    all_variants=list(variants)
    if selected:
        assert set(selected)<=set(variants),'unknown author control'
        variants=[variant for variant in variants if variant in selected or variant=='reference' and 'rasterized_slides' in selected]
    results={};reference_pdf=None
    with tempfile.TemporaryDirectory(prefix='h005-author-controls-') as temporary:
        base=Path(temporary)
        for variant in variants:
            case=base/variant;shutil.copytree(exec_root,case);shutil.copytree(gt_root,case/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copytree(gt_root/'reference/results',case/'results')
            ppt=case/'results/annual.pptx';ledger=case/'results/evidence.csv';notes=case/'results/notes.docx'
            changes={}
            if variant=='zero_override':changes={'K01':'3740.00'}
            elif variant=='unit_mismatch':changes={'K04':'11940000.00'}
            elif variant=='mean_of_rates':changes={'K07':rounded(sum(Decimal(str(row[2]))/Decimal(str(row[1]))*100 for row in raw['operations'])/12)}
            elif variant=='include_future_invoices':
                factors={'万元':Decimal(1),'元':Decimal('.0001')}
                changes={'K10':rounded(sum(Decimal(str(row[3]))*factors[row[4]] for row in raw['receivables'])/sum(Decimal(str(row[2]))*factors[row[4]] for row in raw['receivables'])*100)}
            elif variant=='include_day30':changes={'K11':'125.00'}
            elif variant=='ledger_only_correct':
                changes={'K01':'1.00'};alter_metrics(ppt,changes,truth);alter_metrics(notes,changes,truth,True);changes={}
            if changes:
                alter_ledger(ledger,changes);alter_metrics(ppt,changes,truth);alter_metrics(notes,changes,truth,True)
            if variant in {'equivalent_order','equivalent_formula','wrong_chart_cache','wrong_embedded_formula_correct_cache','wrong_embedded_literal','font_too_small','text_overflow'}:
                alter_pptx(ppt,variant)
            if variant=='equivalent_order':alter_ledger(ledger,equivalent=True)
            if variant=='rasterized_slides':rasterize(ppt,reference_pdf)
            if variant=='missing_description_header':alter_ledger(ledger,drop_header='method')
            if variant=='wrong_evidence':
                with ledger.open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
                rows[0]['source_cells']='财务月度!A1'
                with ledger.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            for name,path in [('missing_pptx',ppt),('missing_ledger',ledger),('missing_notes',notes)]:
                if variant==name or variant=='missing_all':path.unlink()
            if variant=='corrupt_pptx':ppt.write_bytes(b'not a presentation')
            if variant=='changed_input':(case/'metrics.xlsx').write_bytes((case/'metrics.xlsx').read_bytes()+b'changed')
            if variant=='missing_gt':(case/'gt/expected.json').unlink()
            derived=output/variant;derived.mkdir()
            os.environ.update(GENERAL_E2E_OFFICE_LOCK=str(office_lock),GENERAL_E2E_OFFICE_RENDER_LOCK=str(render_lock),GENERAL_E2E_RULE_EVIDENCE_DIR=str(derived))
            try:scores=grader(case)
            except FileNotFoundError:
                if variant!='missing_gt':raise
                results[variant]={'status':'evaluation_error','score':None,'error':'FileNotFoundError'};continue
            observation=json.loads((derived/'h005-analysis.json').read_text(encoding='utf-8'))
            if variant in {'reference','equivalent_order','equivalent_formula'}:assert abs(scores['overall_score']-1)<1e-9,(variant,scores)
            else:assert scores['overall_score']<1-1e-9,(variant,scores)
            if variant=='wrong_embedded_formula_correct_cache':
                assert observation['chart_checks'][0]['score']==1 and observation['chart_checks'][0]['editable']<1
            if variant=='font_too_small':assert not observation['font_pass']
            if variant=='text_overflow':assert not observation['fit_pass']
            if variant=='missing_description_header':assert abs(scores['business_correctness']-1)<1e-9
            if variant=='reference':reference_pdf=derived/'presentation/rendered.pdf'
            results[variant]={'scores':scores,'editable_score':observation['editable_data_score'],'font_pass':observation['font_pass'],'fit_pass':observation['fit_pass']}
            print(json.dumps({'variant':variant,'rule_score':scores['overall_score']}),flush=True)
    hashes={path.relative_to(gt_root).as_posix():sha(path) for path in gt_root.rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.name!='authoring_validation.json'}
    return {'schema_version':'h005-author-validation/v1','status':'PASS' if set(variants)==set(all_variants) else 'PARTIAL','controls':results,'gt_sha256':hashes,
        'limit':'Actual locked Office and author rule controls; not independent semantic/expert review, Harness run, hybrid total or difficulty calibration.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exec-root',required=True,type=Path);parser.add_argument('--gt-root',required=True,type=Path)
    parser.add_argument('--office-lock',required=True,type=Path);parser.add_argument('--render-lock',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--variant',action='append')
    args=parser.parse_args();report=validate(args.exec_root,args.gt_root,args.office_lock,args.render_lock,args.output_dir,args.variant)
    (args.gt_root/'authoring_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'controls':len(report['controls'])}))
