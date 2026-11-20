"""Real-Office acceptance of benign variants, business negatives and infrastructure boundaries."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,copy,csv,hashlib,io,json,os,re,runpy,shutil,subprocess,sys,traceback,zipfile
import xml.etree.ElementTree as ET
GT=Path(__file__).resolve().parent;BASE=GT.parent
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
REL='{http://schemas.openxmlformats.org/package/2006/relationships}';DOCREL='http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
read=lambda p:json.loads(p.read_text())
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}
def package(path,fn):
    with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
    fn(parts)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in parts.items():z.writestr(n,b)
def xml(path,part,fn):
    def patch(parts):
        node=ET.fromstring(parts[part]);fn(node);parts[part]=ET.tostring(node,encoding='utf-8',xml_declaration=True)
    package(path,patch)
def point(address):
    m=re.fullmatch(r'([A-Z]+)(\d+)',address);c=0
    for v in m[1]:c=c*26+ord(v)-64
    return int(m[2]),c
def cell_text(c):
    if c.get('t')=='inlineStr':return ''.join(v.text or '' for v in c.iter(X+'t'))
    if c.get('t')=='str':return c.findtext(X+'v') or ''
    return ''
def column(c):
    s=''
    while c:c,r=divmod(c-1,26);s=chr(65+r)+s
    return s
def cell(node,address,value,*,formula=False):
    c=node.find(f'.//{X}c[@r="{address}"]')
    if c is None:
        row,col=point(address);parent=node.find(f'.//{X}row[@r="{row}"]');assert parent is not None;c=ET.SubElement(parent,X+'c',{'r':address})
    for child in list(c):c.remove(child)
    if formula:c.set('t','n');ET.SubElement(c,X+'f').text=str(value).removeprefix('=');ET.SubElement(c,X+'v').text='0'
    elif isinstance(value,bool):c.set('t','b');ET.SubElement(c,X+'v').text='1' if value else '0'
    elif isinstance(value,(int,float)):c.set('t','n');ET.SubElement(c,X+'v').text=str(value)
    else:c.set('t','inlineStr');s=ET.SubElement(c,X+'is');ET.SubElement(s,X+'t').text='' if value is None else str(value)
def merge_ids(node,col_letter):
    merges=node.find(X+'mergeCells')
    if merges is None:merges=ET.SubElement(node,X+'mergeCells')
    for start in [6,9,12]:
        ET.SubElement(merges,X+'mergeCell',{'ref':f'{col_letter}{start}:{col_letter}{start+2}'})
        for r in [start+1,start+2]:
            c=node.find(f'.//{X}c[@r="{col_letter}{r}"]')
            if c is not None:
                for child in list(c):c.remove(child)
                c.set('t','n')
    merges.set('count',str(len(merges)))
def rewrite_formula(text,context,*,shift=False,rowmap=None):
    pattern=r"(?:(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))!)?(\$?)([A-Z]{1,3})(\$?)([1-9][0-9]*)"
    def replace(m):
        sheet=m[1] or m[2] or context;prefix=("'"+m[1]+"'!" if m[1] else m[2]+'!' if m[2] else '')
        row=int(m[6]);col=point(m[4]+'1')[1]
        if shift:row+=2;col+=1
        elif sheet=='Model':row=rowmap.get(row,row)
        return prefix+m[3]+column(col)+m[5]+str(row)
    return re.sub(pattern,replace,text or '')
def mutate(name,root):
    results=root/'results';book=results/'quote.xlsx';word=results/'proposal.docx';email=results/'customer_email.md';exceptions=results/'exceptions.csv'
    contract=read(root/'gt/artifact_contract.json');truth=read(root/'gt/expected.json')
    model_part='xl/worksheets/sheet2.xml';quote_part='xl/worksheets/sheet1.xml';inputs_part='xl/worksheets/sheet3.xml'
    if name=='reference':return
    if name=='renamed_sheets':
        def change(parts):
            names={'Quote':'报价汇总','Model':'工程与计价','Inputs':'给定参数'};wb=ET.fromstring(parts['xl/workbook.xml'])
            for s in wb.findall(X+'sheets/'+X+'sheet'):s.set('name',names[s.get('name')])
            parts['xl/workbook.xml']=ET.tostring(wb)
            for part in [quote_part,model_part,inputs_part]:
                n=ET.fromstring(parts[part])
                for f in n.iter(X+'f'):
                    for old,new in names.items():f.text=(f.text or '').replace("'"+old+"'!","'"+new+"'!").replace(old+'!',"'"+new+"'!")
                parts[part]=ET.tostring(n)
        package(book,change);return
    if name=='shifted_grid':
        def change(parts):
            for part,context in [(quote_part,'Quote'),(model_part,'Model'),(inputs_part,'Inputs')]:
                n=ET.fromstring(parts[part])
                for row in n.findall(X+'sheetData/'+X+'row'):
                    row.set('r',str(int(row.get('r'))+2))
                    for c in row.findall(X+'c'):
                        r,col=point(c.get('r'));c.set('r',column(col+1)+str(r+2))
                        for f in c.findall(X+'f'):f.text=rewrite_formula(f.text,context,shift=True)
                for d in n.findall(X+'dimension'):d.set('ref',rewrite_formula(d.get('ref'),context,shift=True))
                parts[part]=ET.tostring(n)
        package(book,change);return
    if name=='chinese_headers':
        aliases={k:v[-1] for k,v in contract['field_aliases'].items()};aliases.update({k:v[-1] for k,v in contract['source_field_aliases'].items()});aliases.update(parameter_id='参数编号',value='数值')
        def change(parts):
            changed=0
            for part,header_rows in [(quote_part,[5,19]),(model_part,[5]),(inputs_part,[5,14,23])]:
                n=ET.fromstring(parts[part])
                for r in header_rows:
                    for c in n.findall(f'.//{X}row[@r="{r}"]/{X}c'):
                        t=cell_text(c)
                        if t in aliases:cell(n,c.get('r'),aliases[t]);changed+=1
                parts[part]=ET.tostring(n)
            assert changed>=30,changed
        package(book,change);return
    if name=='reordered_model_rows':
        rowmap={r:20-r for r in range(6,15)}
        def change(parts):
            for part,context in [(quote_part,'Quote'),(model_part,'Model')]:
                n=ET.fromstring(parts[part])
                for f in n.iter(X+'f'):f.text=rewrite_formula(f.text,context,rowmap=rowmap)
                if context=='Model':
                    data=n.find(X+'sheetData')
                    for row in data:
                        old=int(row.get('r'));new=rowmap.get(old,old);row.set('r',str(new))
                        for c in row.findall(X+'c'):
                            rr,col=point(c.get('r'));c.set('r',column(col)+str(rowmap.get(rr,rr)))
                    data[:]=sorted(data,key=lambda r:int(r.get('r')))
                parts[part]=ET.tostring(n)
        package(book,change);return
    if name=='transposed_sites':
        def change(parts):
            n=ET.fromstring(parts[inputs_part]);data=n.find(X+'sheetData');old={c.get('r'):copy.deepcopy(c) for row in data for c in row.findall(X+'c')};site_fields=list(truth['inputs']['sites'][0])[1:]
            for row in list(data):
                if 5<=int(row.get('r'))<=8:data.remove(row)
            for r in range(40,54):ET.SubElement(data,X+'row',{'r':str(r)})
            for i,label in enumerate(['field_id','unit','S1','S2','S3']):cell(n,column(i+1)+'40',label)
            mapping={}
            for i,field in enumerate(site_fields,41):
                cell(n,'A'+str(i),field)
                for j,site in enumerate(truth['inputs']['sites'],3):
                    old_address=column(site_fields.index(field)+2)+str(6+j-3);new_address=column(j)+str(i);c=copy.deepcopy(old[old_address]);c.set('r',new_address);data.find(X+f'row[@r="{i}"]').append(c);mapping[old_address]=new_address
            parts[inputs_part]=ET.tostring(n)
            for part in [model_part,quote_part]:
                node=ET.fromstring(parts[part])
                for f in node.iter(X+'f'):
                    def replace(m):return "'Inputs'!$"+re.sub(r'\d+$','',mapping[m[1]+m[2]])+'$'+re.search(r'\d+$',mapping[m[1]+m[2]])[0] if m[1]+m[2] in mapping else m[0]
                    f.text=re.sub(r"'Inputs'!\$([A-Z]+)\$([0-9]+)",replace,f.text or '')
                parts[part]=ET.tostring(node)
        package(book,change);return
    if name=='long_model':
        def change(parts):
            wb=ET.fromstring(parts['xl/workbook.xml']);sheets=wb.find(X+'sheets')
            for s in sheets:
                if s.get('name')=='Model':s.set('state','hidden')
            ET.SubElement(sheets,X+'sheet',{'name':'计算明细','sheetId':'40','{'+DOCREL.removesuffix('/')+'}id':'rIdLong'})
            parts['xl/workbook.xml']=ET.tostring(wb);rels=ET.fromstring(parts['xl/_rels/workbook.xml.rels']);ET.SubElement(rels,REL+'Relationship',{'Id':'rIdLong','Type':DOCREL+'worksheet','Target':'worksheets/long.xml'});parts['xl/_rels/workbook.xml.rels']=ET.tostring(rels)
            ct=ET.fromstring(parts['[Content_Types].xml']);ET.SubElement(ct,'{http://schemas.openxmlformats.org/package/2006/content-types}Override',{'PartName':'/xl/worksheets/long.xml','ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
            serialized=ET.tostring(ct,encoding='unicode');serialized=re.sub(r'<(/?)ns[0-9]+:',r'<\1',serialized);serialized=re.sub(r'xmlns:ns[0-9]+=',r'xmlns=',serialized);parts['[Content_Types].xml']=serialized.encode()
            n=ET.Element(X+'worksheet');data=ET.SubElement(n,X+'sheetData');ET.SubElement(data,X+'row',{'r':'1'})
            for i,label in enumerate(['site_id','option_id','metric','value'],1):cell(n,column(i)+'1',label)
            fields=list(next(iter(truth['cases'].values()))['values'])+list(next(iter(truth['cases'].values()))['checks'])+['status'];r=2
            for source_row,c in enumerate(truth['cases'].values(),6):
                for field in fields:
                    ET.SubElement(data,X+'row',{'r':str(r)})
                    for col,value in [('A',c['site_id']),('B',c['option_id']),('C',field)]:cell(n,col+str(r),value)
                    cell(n,'D'+str(r),"'Model'!"+column(3+fields.index(field))+str(source_row),formula=True);r+=1
            parts['xl/worksheets/long.xml']=ET.tostring(n)
        package(book,change);return
    if name=='merged_xlsx_ids':xml(book,quote_part,lambda n:merge_ids(n,'A'));xml(book,model_part,lambda n:merge_ids(n,'A'));return
    if name in {'reordered_word_rows','merged_word_ids'}:
        def f(n):
            tables=n.findall('.//'+W+'body/'+W+'tbl')
            for t in tables[:2]:
                rows=t.findall(W+'tr')
                if name=='reordered_word_rows':
                    for row in rows[1:]:t.remove(row)
                    for row in reversed(rows[1:]):t.append(row)
                else:
                    for start in [1,4,7]:
                        for j in range(3):
                            c=rows[start+j].find(W+'tc');pr=c.find(W+'tcPr')
                            if pr is None:pr=ET.Element(W+'tcPr');c.insert(0,pr)
                            ET.SubElement(pr,W+'vMerge',{W+'val':'restart' if j==0 else 'continue'})
                            if j:
                                for p in c.findall(W+'p'):c.remove(p)
                                ET.SubElement(c,W+'p')
        xml(word,'word/document.xml',f);return
    if name=='prose_email':
        labels={'feasible':'可行','conditional':'附条件','infeasible':'不可行'}
        email.write_text('\n'.join(f'{s} 推荐{r["option_id"]} {labels[r["status"]]}，含税基础额{truth["cases"][r["pair"]]["values"]["gross_total"]}，预算余量{truth["cases"][r["pair"]]["values"]["budget_margin"]}。' for s,r in truth['recommendations'].items())+'\n仅保存草稿；S3荷载/腐蚀/修复费未知，补贴未知不抵减。');return
    if name in {'source_locator_site','source_locator_physical','missing_optional_rule_source','wrong_existing_locator','wrong_exception_value','wrong_exception_status','duplicate_exception','missing_exception','extra_exception','missing_next_action','bom_csv'}:
        if name=='bom_csv':exceptions.write_bytes(b'\xef\xbb\xbf'+exceptions.read_bytes());return
        with exceptions.open(newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
        index=read(root/'gt/evidence_index.json')['records']
        if name=='source_locator_site':
            for r in rows:r['source_locator']=r['site_id']
        if name=='source_locator_physical':
            for r in rows:r['source_locator']=index[r['source_file']+'#'+r['source_locator']]['physical_locator']
        if name=='missing_optional_rule_source':
            for r in rows:r['rule_source']=''
        if name=='wrong_existing_locator':rows[0]['source_locator']='Q12'
        if name=='wrong_exception_value':rows[0]['observed']='true'
        if name=='wrong_exception_status':rows[-1]['status']='pass'
        if name=='duplicate_exception':rows[-1]=dict(rows[0])
        if name=='missing_exception':rows.pop()
        if name=='extra_exception':r=dict(rows[0]);r['option_id']='A';rows.append(r)
        if name=='missing_next_action':rows[0]['next_action']=''
        with exceptions.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
        return
    if name in {'equivalent_round','structural_literal_zeros','static_model_cache','constant_model_formulas','wrong_formula_old_cache','floor_modules','double_shading','wrong_flat_load','wrong_replacement_area','wrong_permission','omit_inverter','omit_cable','omit_isolation','omit_adhesion','omit_corrosion','wrong_vat','wrong_half_cent','subsidy_deduction','unknown_load_zero','missing_source_parameter'}:
        def f(n):
            headers={cell_text(c):point(c.get('r'))[1] for c in n.findall(f'.//{X}row[@r="5"]/{X}c')};assert {'area_m2','cost_module','gross_total'}<=set(headers),headers
            def at(field,row):return column(headers[field])+str(row)
            if name=='equivalent_round':
                for row in range(6,15):
                    for field,subtotal,taxrow in [('tax_goods','subtotal_goods',34),('tax_construction','subtotal_construction',35),('tax_services','subtotal_services',36)]:cell(n,at(field,row),f"ROUND({at(subtotal,row)}*'Inputs'!$B${taxrow},2)",formula=True)
            elif name in {'static_model_cache','constant_model_formulas','structural_literal_zeros'}:
                for row,c in enumerate(truth['cases'].values(),6):
                    entries={**c['values'],**{k:v['status'] for k,v in c['checks'].items()},'status':c['status']}
                    for field,value in entries.items():
                        if name=='structural_literal_zeros' and value!='0':continue
                        try:number=float(value)
                        except (ValueError,TypeError):
                            if name=='static_model_cache':cell(n,at(field,row),value)
                            continue
                        cell(n,at(field,row),number,formula=name=='constant_model_formulas')
            else:
                edits={'floor_modules':('module_count',6,"ROUNDDOWN('Inputs'!$G$6/('Inputs'!$C$15*'Inputs'!$H$6*'Inputs'!$E$15*'Inputs'!$I$6),0)"),
                    'double_shading':('module_count',12,"ROUNDUP('Inputs'!$G$8/('Inputs'!$C$15*'Inputs'!$H$8*'Inputs'!$E$15*'Inputs'!$I$8*'Inputs'!$I$8),0)"),
                    'wrong_flat_load':('design_load_kg_m2',9,"'Inputs'!$F$15"),'wrong_replacement_area':('replacement_area_m2',10,at('area_m2',10)),
                    'wrong_permission':('REPLACEMENT',7,'"pass"'),'omit_inverter':('cost_inverter',6,'0'),'omit_cable':('cost_cable',6,'0'),'omit_isolation':('cost_isolation',6,'0'),
                    'omit_adhesion':('cost_adhesion',8,'0'),'omit_corrosion':('cost_corrosion',12,'0'),
                    'wrong_vat':('tax_construction',9,f"ROUND({at('subtotal_construction',9)}*'Inputs'!$B$34,2)"),
                    'wrong_half_cent':('tax_construction',9,'4724.77'),'subsidy_deduction':('gross_total',6,f"SUM({at('subtotal_goods',6)}:{at('tax_services',6)})-10000"),
                    'wrong_formula_old_cache':('cost_module',6,'0')}
                if name in edits:
                    field,row,formula=edits[name];address=at(field,row)
                    if name=='wrong_formula_old_cache':n.find(f'.//{X}c[@r="{address}"]/{X}f').text='0'
                    else:cell(n,address,formula,formula=True)
        if name=='unknown_load_zero':xml(book,inputs_part,lambda n:cell(n,'D8',0))
        elif name=='missing_source_parameter':xml(book,inputs_part,lambda n:cell(n,'A28','not_declared_design_fee'))
        else:xml(book,model_part,f)
        return
    if name in {'word_wrong_price','word_wrong_recommendation','word_missing_requirement','word_hidden_text','semantic_unproven_approval'}:
        def f(n):
            if name=='word_wrong_price':
                t=n.findall('.//'+W+'body/'+W+'tbl')[1];c=t.findall(W+'tr')[1].findall(W+'tc')[3];next(c.iter(W+'t')).text='270,146.00'
            elif name=='word_wrong_recommendation':
                for t in n.iter(W+'t'):
                    if t.text=='S2 推荐B 可行':t.text='S2 推荐A 可行'
            elif name=='word_missing_requirement':
                t=n.findall('.//'+W+'body/'+W+'tbl')[2]
                for r in list(t.findall(W+'tr')):
                    if ''.join(v.text or '' for v in r.iter(W+'t')).startswith('Q04'):t.remove(r)
            elif name=='word_hidden_text':
                for r in n.iter(W+'r'):
                    pr=r.find(W+'rPr')
                    if pr is None:pr=ET.Element(W+'rPr');r.insert(0,pr)
                    ET.SubElement(pr,W+'vanish')
            else:
                body=n.find(W+'body');p=ET.Element(W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text='S3现场荷载和腐蚀核验均已完成通过，修复费已确定为零，可直接批准施工。';body.insert(len(body)-1,p)
        xml(word,'word/document.xml',f);return
    if name=='semantic_invented_subsidy':email.write_text(email.read_text()+'\n已明确获得补贴120000元，无需再确认补贴资格。\n');return
    if name.startswith('missing_') and name[8:] in {'quote','word','email','exceptions'}:
        {'quote':book,'word':word,'email':email,'exceptions':exceptions}[name[8:]].unlink();return
    if name=='corrupt_quote':book.write_bytes(b'not XLSX');return
    if name=='malformed_csv':exceptions.write_text('site_id,option_id\nS1,A\n');return
    if name=='all_missing':shutil.rmtree(results);return
    if name=='tampered_input':p=root/'options.csv';p.write_text(p.read_text()+'\nchanged');return
    if name=='missing_gt':(root/'gt/expected.json').unlink();return
    if name=='helper_drift':p=root/'gt/word_model.py';p.write_text(p.read_text()+'\n# drift\n');return
    if name=='wrong_gt_digest':p=root/'gt/business_oracle.json';d=read(p);d['expected_sha256']='0'*64;dump(p,d);return
    if name in {'missing_runtime','render_lock_mismatch'}:return
    raise ValueError('unknown control '+name)
def child(root):
    try:dump(root.parent/'result.json',{'kind':'scores','scores':runpy.run_path(str(root/'gt/grader.py'))['grade'](root)})
    except Exception as e:dump(root.parent/'result.json',{'kind':'evaluation_error','type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc(),'score':None})
def main():
    p=argparse.ArgumentParser();p.add_argument('--child',type=Path);p.add_argument('--output-dir',type=Path);p.add_argument('--select',nargs='*');p.add_argument('--jobs',type=int,default=2);args=p.parse_args()
    if args.child:child(args.child);return
    positive=['reference','renamed_sheets','shifted_grid','chinese_headers','reordered_model_rows','transposed_sites','long_model','merged_xlsx_ids','reordered_word_rows','merged_word_ids','prose_email','source_locator_site','source_locator_physical','missing_optional_rule_source','equivalent_round','structural_literal_zeros','bom_csv']
    negative={**{n:('boundary_cases',group) for n,group in {'floor_modules':'minimum_module_ceiling','double_shading':'minimum_module_ceiling','wrong_flat_load':'roof_type_load','wrong_replacement_area':'whole_roof_replacement','wrong_permission':'replacement_permission','omit_inverter':'mandatory_electrical_bom','omit_cable':'mandatory_electrical_bom','omit_isolation':'mandatory_electrical_bom','omit_adhesion':'adhesion_and_corrosion_fees','omit_corrosion':'adhesion_and_corrosion_fees','wrong_vat':'separate_tax_rounding','wrong_half_cent':'separate_tax_rounding','subsidy_deduction':'no_subsidy_deduction','unknown_load_zero':'unknown_not_zero','wrong_existing_locator':'actual_source_binding','word_wrong_price':'cross_artifact_consistency','word_wrong_recommendation':'cross_artifact_consistency'}.items()},
        **{n:('boundary_cases',None) for n in ['static_model_cache','constant_model_formulas','missing_source_parameter']},
        **{n:('business_correctness',None) for n in ['wrong_formula_old_cache','wrong_exception_value','wrong_exception_status','missing_next_action']},
        **{n:('delivery_integrity',None) for n in ['duplicate_exception','missing_exception','extra_exception','word_missing_requirement','word_hidden_text','missing_quote','missing_word','missing_email','missing_exceptions','corrupt_quote','malformed_csv','all_missing','tampered_input']}}
    infrastructure=['missing_gt','helper_drift','wrong_gt_digest','missing_runtime','render_lock_mismatch'];semantics=['semantic_unproven_approval','semantic_invented_subsidy']
    all_names=positive+list(negative)+infrastructure+semantics;names=args.select or all_names;assert set(names)<=set(all_names)
    out=args.output_dir.resolve();out.mkdir(parents=True);runtime=read(BASE/'qa/runtime/runtime-lock.json');dump(out/'office.json',runtime['office_runtime']);dump(out/'render.json',runtime['office_render_runtime'])
    def run(name):
        case=out/name;case.mkdir();workspace=case/'workspace';shutil.copytree(BASE/'exec',workspace);shutil.copytree(GT,workspace/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copytree(GT/'reference/results',workspace/'results');unmodified=inventory(workspace);mutate(name,workspace);before=inventory(workspace)
        if name not in {'reference','missing_runtime','render_lock_mismatch'}:assert unmodified!=before,'control did not mutate its fixture: '+name
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','GENERAL_E2E_OFFICE_LOCK':str(out/'office.json'),'GENERAL_E2E_OFFICE_RENDER_LOCK':str(out/'render.json'),'GENERAL_E2E_RULE_EVIDENCE_DIR':str(case/'derived')}
        if name=='missing_runtime':env.pop('GENERAL_E2E_OFFICE_RENDER_LOCK')
        if name=='render_lock_mismatch':bad=copy.deepcopy(runtime['office_render_runtime']);bad['office_runtime']['version']='wrong';dump(case/'bad-render.json',bad);env['GENERAL_E2E_OFFICE_RENDER_LOCK']=str(case/'bad-render.json')
        completed=subprocess.run([str(BASE.parent/'h005/qa/existing-worker/venv/bin/python'),str(GT/'validate_authoring.py'),'--child',str(workspace)],env=env,text=True,capture_output=True,timeout=480)
        (case/'stdout.txt').write_text(completed.stdout);(case/'stderr.txt').write_text(completed.stderr);assert completed.returncode==0,(name,completed.stderr)
        result=read(case/'result.json');unchanged=inventory(workspace)==before;assert unchanged,name
        if name in infrastructure:ok=result['kind']=='evaluation_error' and result['score'] is None
        elif result['kind']!='scores':ok=False
        elif name in positive+semantics:ok=all(abs(v-1)<1e-10 for v in result['scores'].values())
        else:
            key,group=negative[name];ok=result['scores'][key]<1
            if group:ok &= read(case/'derived/h013-analysis.json')['boundary_groups'][group]<1
            if name in {'static_model_cache','constant_model_formulas'}:ok &= read(case/'derived/h013-analysis.json')['input_responses']['score']<1
            if name=='all_missing':ok &= all(v==0 for v in result['scores'].values())
        row={'name':name,'pass':ok,'kind':result['kind'],'scores':result.get('scores'),'workspace_unchanged':unchanged,'semantic_only':name in semantics,'infrastructure':name in infrastructure};dump(case/'validation.json',row);print(json.dumps(row,ensure_ascii=False),flush=True);return row
    rows=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for future in as_completed([pool.submit(run,n) for n in names]):rows.append(future.result())
    report={'status':'AUTHOR_CONTROLS_PASS' if all(r['pass'] for r in rows) else 'FAIL','count':len(rows),'full_matrix':set(names)==set(all_names),'positive_count':len(set(names)&set(positive)),'negative_count':len(set(names)&set(negative)),'infrastructure_count':len(set(names)&set(infrastructure)),'semantic_only_count':len(set(names)&set(semantics)),'cases':rows,'source_gt_sha256':inventory(GT),'source_exec_sha256':inventory(BASE/'exec'),
        'control_scope_summary':f'{len(positive)}合法表达、{len(negative)}候选负例、{len(infrastructure)}基础设施门禁和{len(semantics)}规则仍满分的语义专用反例；均为作者验收。','limit':'Actual locked Office author controls, not independent semantic grading, real Harness scores or measured difficulty.'}
    dump(out/'validation.json',report)
    if not all(r['pass'] for r in rows):raise SystemExit(1)
if __name__=='__main__':main()
