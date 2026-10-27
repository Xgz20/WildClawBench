"""Real Office author controls. Reuse only previously passed controls with identical GT."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,hashlib,json,os,re,runpy,shutil,subprocess,sys,zipfile
import xml.etree.ElementTree as ET

S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def inventory(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
def package(path,change):
    with zipfile.ZipFile(path) as z:parts={i.filename:(i,z.read(i)) for i in z.infolist()}
    raw={name:data for name,(info,data) in parts.items()};change(raw)
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in raw.items():z.writestr(parts[name][0] if name in parts else name,data)
def xlsx_cells(path,sheet,changes,formulas=None):
    def edit(parts):
        node=ET.fromstring(parts[f'xl/worksheets/sheet{sheet}.xml'])
        for cell in node.iter(S+'c'):
            address=cell.get('r')
            if address in changes:
                for child in list(cell):
                    if child.tag in {S+'v',S+'f',S+'is'}:cell.remove(child)
                value=changes[address]
                if isinstance(value,str) and not re.fullmatch(r'[+-]?[0-9.]+',value):
                    cell.set('t','inlineStr');ET.SubElement(ET.SubElement(cell,S+'is'),S+'t').text=value
                else:cell.set('t','n');ET.SubElement(cell,S+'v').text=str(value)
            if formulas and address in formulas:
                f=cell.find(S+'f')
                if f is None:f=ET.SubElement(cell,S+'f')
                f.text=formulas[address]
        parts[f'xl/worksheets/sheet{sheet}.xml']=ET.tostring(node,encoding='utf-8',xml_declaration=True)
    package(path,edit)
def word_edit(path,fn):
    def edit(parts):
        node=ET.fromstring(parts['word/document.xml']);fn(node);parts['word/document.xml']=ET.tostring(node,encoding='utf-8',xml_declaration=True)
    package(path,edit)
def replace_word(path,old,new):
    def edit(node):
        for text in node.iter(W+'t'):
            if text.text:text.text=text.text.replace(old,new)
    word_edit(path,edit)
def set_cell(cell,text):
    for child in list(cell):
        if child.tag!=W+'tcPr':cell.remove(child)
    for line in text.split('\n'):
        p=ET.SubElement(cell,W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text=line
def set_schedule(root,changes):
    p=root/'results/assumptions.json';ledger=json.loads(p.read_text())
    for row in ledger['schedule']:
        if row['line_id'] in changes:row['work_dates']=changes[row['line_id']]
    dump(p,ledger)
    def edit(node):
        tables=node.find(W+'body').findall(W+'tbl');table=tables[1]
        for row in table.findall(W+'tr')[1:]:
            cells=row.findall(W+'tc');identity=''.join(t.text or '' for t in cells[0].iter(W+'t'))
            if identity in changes:set_cell(cells[3],'\n'.join(changes[identity]))
    word_edit(root/'results/application.docx',edit)
    html=root/'results/plan.html';text=html.read_text()
    for identity,dates in changes.items():
        pattern=r'(<tr><td>'+identity+r'</td><td>[^<]*</td><td>[^<]*</td><td>)(.*?)(</td></tr>)'
        text,count=re.subn(pattern,lambda m:m[1]+'<br>'.join(dates)+m[3],text,flags=re.S);assert count==1
    html.write_text(text)
def ledger_edit(root,fn):
    p=root/'results/assumptions.json';value=json.loads(p.read_text());fn(value);dump(p,value)
def column(c):
    n=0
    for x in c:n=n*26+ord(x)-64
    return n
def letters(n):
    s=''
    while n:n,r=divmod(n-1,26);s=chr(65+r)+s
    return s
def shift_address(text):return re.sub(r'(\$?)([A-Z]+)(\$?[1-9][0-9]*)',lambda m:m[1]+letters(column(m[2])+1)+m[3],text)

NAMES=['reference','renamed_sheets','shifted_columns','alternate_valid_schedule','chinese_html_headers_and_cell_paragraphs',
 'combined_recommended_alternative_tables','absolute_canonical_source_refs','linked_numeric_driver',
 'html_spans_and_header_rows',
 'double_tax_B','cross_phase_tier','duplicate_freight','missing_p2_freight','training_capitalized','contingency_truncated',
 'expired_C_as_firm','nonminimal_valid_selection','wrong_word_budget_ledger_correct','wrong_html_budget_ledger_correct',
 'wrong_actual_budget_node','wrong_actual_word_node','wrong_source_quote','overlapping_shared_crew','blackout_date','weekend_date',
 'unknown_zero','gate_confirmed','unsupported_word_savings','unsupported_html_payback','duplicate_json_key',
 'static_cached_values','wrong_formula_correct_old_cache','hardcoded_tier_threshold','hidden_html_budget',
 'empty_word','missing_budget','missing_word','missing_html','missing_ledger','damaged_budget','damaged_word','all_missing',
 'extra_unauthorized_phase','input_modified','missing_gt','missing_helper','missing_render_lock','engine_unavailable','font_drift']
POSITIVES=set(NAMES[:9]);ERRORS=set(NAMES[-5:])
def mutate(name,root,office_lock,render_lock):
    budget=root/'results/budget.xlsx';word=root/'results/application.docx';html=root/'results/plan.html'
    if name=='reference':pass
    elif name=='renamed_sheets':
        names={'Summary':'决策汇总','Lines':'组明细','Fees':'费率','Options':'备选'}
        def edit(parts):
            wb=ET.fromstring(parts['xl/workbook.xml'])
            for sheet in wb.findall(S+'sheets/'+S+'sheet'):sheet.set('name',names[sheet.get('name')])
            parts['xl/workbook.xml']=ET.tostring(wb,encoding='utf-8',xml_declaration=True)
            for part in list(parts):
                if part.startswith('xl/worksheets/') and part.endswith('.xml'):
                    node=ET.fromstring(parts[part])
                    for f in node.iter(S+'f'):
                        for old,new in names.items():f.text=(f.text or '').replace(old+'!',"'"+new+"'!")
                    parts[part]=ET.tostring(node,encoding='utf-8',xml_declaration=True)
        package(budget,edit)
        for old,new in names.items():replace_word(word,old,new)
        text=html.read_text()
        for old,new in names.items():text=text.replace(old,new)
        html.write_text(text)
        ledger_edit(root,lambda v:[r.update(budget_ref=r['budget_ref'].replace('Summary',"'决策汇总'")) for r in v['evidence']])
    elif name=='shifted_columns':
        def edit(parts):
            for part in list(parts):
                if not(part.startswith('xl/worksheets/') and part.endswith('.xml')):continue
                node=ET.fromstring(parts[part])
                for element in node.iter():
                    if element.tag==S+'c':element.set('r',shift_address(element.get('r')))
                    elif element.tag==S+'f':element.text=shift_address(element.text or '')
                    elif element.tag==S+'col':
                        for field in ['min','max']:element.set(field,str(int(element.get(field))+1))
                    for attr in ['ref','sqref','activeCell','topLeftCell']:
                        if attr in element.attrib:element.set(attr,shift_address(element.get(attr)))
                parts[part]=ET.tostring(node,encoding='utf-8',xml_declaration=True)
        package(budget,edit);ledger_edit(root,lambda v:[r.update(budget_ref=shift_address(r['budget_ref'])) for r in v['evidence']])
    elif name=='alternate_valid_schedule':set_schedule(root,{
        'P1-FAN':['2026-12-07','2026-12-08','2026-12-09','2026-12-10'],
        'P1-CL':['2026-12-11','2026-12-16','2026-12-17','2026-12-18','2026-12-21','2026-12-22'],
        'P2-FAN':['2027-03-01','2027-03-02','2027-03-03'],
        'P2-CL':['2027-03-04','2027-03-05','2027-03-10','2027-03-11']})
    elif name=='chinese_html_headers_and_cell_paragraphs':
        text=html.read_text()
        for a,b in [('phase','阶段'),('capex','资本申请（CNY）'),('opex','费用申请（元）'),('total_cash','总现金（CNY元）')]:text=text.replace('<th>'+a+'</th>','<th>'+b+'</th>')
        text=re.sub(r'<td>(.*?)</td>',r'<td><p>\1</p></td>',text,flags=re.S);html.write_text(text)
        p=root/'results/assumptions.json';p.write_text('\ufeff'+p.read_text())
    elif name=='combined_recommended_alternative_tables':
        truth=json.loads((root/'gt/expected.json').read_text());alt=truth['base_feasible'][1]
        alternate=[[p,*[alt['phases'][p][k] for k in ['capex','opex','total_cash']]] for p in ['P1','P2']]
        def edit(node):
            table=node.find(W+'body').findall(W+'tbl')[0];rows=table.findall(W+'tr');template=ET.fromstring(ET.tostring(rows[1]))
            for i,row in enumerate(rows):
                cells=row.findall(W+'tc');new=ET.fromstring(ET.tostring(cells[0]));set_cell(new,'方案' if i==0 else '推荐')
                row.insert(list(row).index(cells[0]),new)
            for values in alternate:
                row=ET.fromstring(ET.tostring(template))
                for cell,value in zip(row.findall(W+'tc'),values):set_cell(cell,str(value))
                new=ET.fromstring(ET.tostring(row.findall(W+'tc')[0]));set_cell(new,'替代');row.insert(0,new);table.append(row)
            grid=table.find(W+'tblGrid')
            for child in list(grid):grid.remove(child)
            widths=[1134,1020,2381,2381,2438]
            for width in widths:ET.SubElement(grid,W+'gridCol',{W+'w':str(width)})
            for row in table.findall(W+'tr'):
                for cell,width in zip(row.findall(W+'tc'),widths):
                    props=cell.find(W+'tcPr')
                    if props is None:props=ET.SubElement(cell,W+'tcPr')
                    size=props.find(W+'tcW')
                    if size is None:size=ET.SubElement(props,W+'tcW')
                    size.attrib.update({W+'w':str(width),W+'type':'dxa'})
        word_edit(word,edit)
        text=html.read_text();m=re.search(r'<table [^>]*id="recommended".*?</table>',text,re.S);assert m
        table=m[0].replace('<thead><tr>','<thead><tr><th>方案</th>',1)
        table=table.replace('<tbody><tr>','<tbody><tr><td>推荐</td>',1).replace('</tr><tr>','</tr><tr><td>推荐</td>')
        addition=''.join('<tr><td>替代</td>'+''.join('<td>'+str(v)+'</td>' for v in values)+'</tr>' for values in alternate)
        table=table.replace('</tbody>',addition+'</tbody>');html.write_text(text[:m.start()]+table+text[m.end():])
    elif name=='absolute_canonical_source_refs':
        def edit(value):
            for field in ['schedule','quote_exclusions','evidence']:
                for row in value[field]:row['source_refs']=['/tmp_workspace/'+v for v in row['source_refs']]
        ledger_edit(root,edit)
    elif name=='html_spans_and_header_rows':
        mutate('combined_recommended_alternative_tables',root,office_lock,render_lock)
        text=html.read_text().replace('<thead><tr><th>方案</th>','<thead><tr><th colspan="5">推荐申请预算</th></tr><tr><th>方案</th>',1)
        for label in ['推荐','替代']:
            text=text.replace('<tr><td>'+label+'</td><td>P1','<tr><td rowspan="2">'+label+'</td><td>P1',1)
            text=text.replace('<tr><td>'+label+'</td><td>P2','<tr><td>P2',1)
        html.write_text(text)
    elif name=='linked_numeric_driver':
        def edit(parts):
            node=ET.fromstring(parts['xl/worksheets/sheet3.xml']);row=node.find(S+'sheetData/'+S+'row[@r="6"]')
            cell=ET.SubElement(row,S+'c',{'r':'H6','t':'n'});ET.SubElement(cell,S+'v').text='3'
            header=node.find(S+'sheetData/'+S+'row[@r="5"]');label=ET.SubElement(header,S+'c',{'r':'H5','t':'inlineStr'})
            ET.SubElement(ET.SubElement(label,S+'is'),S+'t').text='P1 CL quantity'
            dimension=node.find(S+'dimension')
            if dimension is not None:dimension.set('ref','A1:H7')
            parts['xl/worksheets/sheet3.xml']=ET.tostring(node,encoding='utf-8',xml_declaration=True)
        package(budget,edit);xlsx_cells(budget,2,{}, {'E6':'Fees!H6'})
    elif name=='double_tax_B':xlsx_cells(budget,2,{'I8':'1.13','I9':'1.13'})
    elif name=='cross_phase_tier':xlsx_cells(budget,2,{'F8':2})
    elif name=='duplicate_freight':xlsx_cells(budget,1,{}, {'G6':'D6*2'})
    elif name=='missing_p2_freight':xlsx_cells(budget,1,{'G7':0})
    elif name=='training_capitalized':xlsx_cells(budget,1,{}, {'J6':'SUM(B6:C6,G6,I6)+L6','M6':'K6'})
    elif name=='contingency_truncated':xlsx_cells(budget,1,{}, {'I7':'ROUNDDOWN(SUM(B7:C7,G7)*H7,0)'})
    elif name=='expired_C_as_firm':xlsx_cells(budget,2,{'D6':'C','F6':2,'G6':18100,'H6':16800,'J6':1000,'N6':1})
    elif name=='nonminimal_valid_selection':xlsx_cells(budget,2,{'D6':'B','F6':4,'G6':20100,'H6':19000,'I6':1,'J6':1100})
    elif name=='wrong_word_budget_ledger_correct':
        def edit(node):set_cell(node.find(W+'body').findall(W+'tbl')[0].findall(W+'tr')[1].findall(W+'tc')[1],'99,779.41')
        word_edit(word,edit)
    elif name=='wrong_html_budget_ledger_correct':html.write_text(html.read_text().replace('74,061.55','74,060.55',1))
    elif name=='wrong_actual_budget_node':ledger_edit(root,lambda v:v['evidence'][0].update(budget_ref='Summary!A7:R7'))
    elif name=='wrong_actual_word_node':ledger_edit(root,lambda v:v['evidence'][0].update(application_ref='table:1/row:3'))
    elif name=='wrong_source_quote':ledger_edit(root,lambda v:v['evidence'][0].update(source_refs=['baseline.xlsx#Assets/rows:6-17','constraints.md#C03','quotes/quote_B.pdf#page:1']))
    elif name=='overlapping_shared_crew':set_schedule(root,{'P1-FAN':['2026-12-07','2026-12-08','2026-12-09','2026-12-10']})
    elif name in {'blackout_date','weekend_date'}:set_schedule(root,{'P1-CL':['2026-12-07','2026-12-08','2026-12-09','2026-12-10','2026-12-11','2026-12-14' if name=='blackout_date' else '2026-12-12']})
    elif name=='unknown_zero':ledger_edit(root,lambda v:v['unknowns'].update(annual_savings=0))
    elif name=='gate_confirmed':ledger_edit(root,lambda v:v['gates'].update(p1_acceptance='approved'))
    elif name=='unsupported_word_savings':replace_word(word,'新设备能耗、年度节约额及投资回收期均未提供','年度节约额：103320元，投资回收期：1.7年')
    elif name=='unsupported_html_payback':html.write_text(html.read_text().replace('新设备能耗、年度节约额及回收期均未提供','投资回收期：1.7年'))
    elif name=='duplicate_json_key':
        p=root/'results/assumptions.json';p.write_text(p.read_text().replace('"annual_savings": null','"annual_savings": 100,"annual_savings": null'))
    elif name=='static_cached_values':
        def edit(parts):
            for part in list(parts):
                if part.startswith('xl/worksheets/') and part.endswith('.xml'):
                    node=ET.fromstring(parts[part])
                    for cell in node.iter(S+'c'):
                        f=cell.find(S+'f')
                        if f is not None:cell.remove(f)
                    parts[part]=ET.tostring(node,encoding='utf-8',xml_declaration=True)
        package(budget,edit)
    elif name=='wrong_formula_correct_old_cache':xlsx_cells(budget,2,{}, {'O6':'ROUND(E6*G6*I6,2)'})
    elif name=='hardcoded_tier_threshold':xlsx_cells(budget,2,{}, {'O6':'ROUND(E6*IF(E6>=3,H6,G6)*I6,2)'})
    elif name=='hidden_html_budget':html.write_text(html.read_text().replace('<table id="recommended"','<table hidden id="recommended"',1))
    elif name=='empty_word':
        def edit(node):
            body=node.find(W+'body')
            for child in list(body):
                if child.tag!=W+'sectPr':body.remove(child)
            ET.SubElement(body,W+'p')
        word_edit(word,edit)
    elif name.startswith('missing_') and name in {'missing_budget','missing_word','missing_html','missing_ledger'}:
        (root/'results'/dict(missing_budget='budget.xlsx',missing_word='application.docx',missing_html='plan.html',missing_ledger='assumptions.json')[name]).unlink()
    elif name in {'damaged_budget','damaged_word'}:(budget if name=='damaged_budget' else word).write_bytes(b'not an Office package')
    elif name=='all_missing':shutil.rmtree(root/'results');(root/'results').mkdir()
    elif name=='extra_unauthorized_phase':ledger_edit(root,lambda v:v['phase_totals'].update(P3={'capex':1000,'opex':0,'total_cash':1000}))
    elif name=='input_modified':(root/'constraints.md').write_text((root/'constraints.md').read_text()+'\nchanged input\n')
    elif name=='missing_gt':(root/'gt/expected.json').unlink()
    elif name=='missing_helper':(root/'gt/budget_checks.py').unlink()
    elif name=='missing_render_lock':render_lock=root.parent/'absent-render-lock.json'
    elif name=='engine_unavailable':
        value=json.loads(office_lock.read_text());value['executable']=str(root.parent/'absent-soffice');office_lock=root.parent/'broken-office-lock.json';dump(office_lock,value)
    elif name=='font_drift':
        value=json.loads(render_lock.read_text());p=root.parent/'changed-font.ttf';p.write_bytes(b'changed font')
        value['fonts'][0]['path']=str(p);render_lock=root.parent/'broken-render-lock.json';dump(render_lock,value)
    else:raise ValueError(name)
    return office_lock,render_lock

def child(case):
    workspace=case/'workspace';before=inventory(workspace)
    result={'workspace_unchanged':None}
    try:result['scores']=runpy.run_path(str(workspace/'gt/grader.py'))['grade'](workspace)
    except Exception as exc:result['error']={'type':type(exc).__name__,'message':str(exc)}
    result['workspace_unchanged']=before==inventory(workspace);dump(case/'result.json',result)

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-one',type=Path);p.add_argument('--exec-root',type=Path);p.add_argument('--gt-root',type=Path)
    p.add_argument('--office-lock',type=Path);p.add_argument('--render-lock',type=Path);p.add_argument('--output-dir',type=Path)
    p.add_argument('--only',nargs='+');p.add_argument('--reuse-report',type=Path);p.add_argument('--jobs',type=int,default=2);args=p.parse_args()
    if args.run_one:child(args.run_one);return
    args.output_dir.mkdir(parents=True,exist_ok=False)
    bindings=inventory(args.gt_root);bindings.pop('authoring_validation.json',None)
    source_bindings=inventory(args.exec_root);results={}
    if args.reuse_report:
        prior=json.loads(args.reuse_report.read_text());assert prior['gt_bindings']==bindings and prior['source_bindings']==source_bindings
        assert prior['status'] in {'PARTIAL_AUTHOR_CONTROLS_PASS','AUTHOR_CONTROLS_PASS'};results.update(prior['controls'])
    names=args.only or NAMES;assert set(names)<=set(NAMES)
    def run(name):
        case=args.output_dir/name;case.mkdir();workspace=case/'workspace'
        shutil.copytree(args.exec_root,workspace);shutil.copytree(args.gt_root,workspace/'gt',ignore=shutil.ignore_patterns('__pycache__','authoring_validation.json'))
        shutil.copytree(args.gt_root/'reference/results',workspace/'results')
        office_lock,render_lock=mutate(name,workspace,args.office_lock,args.render_lock)
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','GENERAL_E2E_OFFICE_LOCK':str(office_lock),
          'GENERAL_E2E_OFFICE_RENDER_LOCK':str(render_lock),'GENERAL_E2E_RULE_EVIDENCE_DIR':str(case/'derived')}
        process=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--run-one',str(case)],env=env,capture_output=True,text=True,timeout=240)
        (case/'stdout.log').write_text(process.stdout);(case/'stderr.log').write_text(process.stderr)
        assert process.returncode==0,(name,process.stderr)
        result=json.loads((case/'result.json').read_text());assert result['workspace_unchanged'],name
        if name in ERRORS:
            assert 'scores' not in result and 'error' in result,(name,result)
            if name in {'missing_gt','missing_helper','missing_render_lock'}:assert result['error']['type']=='FileNotFoundError',(name,result)
            else:
                assert result['error']['type']=='OfficeRuntimeError',(name,result)
                assert ('OFFICE_EXECUTABLE_UNAVAILABLE' if name=='engine_unavailable' else 'OFFICE_RENDER_FONT_DRIFT') in result['error']['message'],(name,result)
        else:
            assert 'error' not in result,(name,result)
            score=result['scores']['overall_score']
            assert (score==1. if name in POSITIVES else score<1.),(name,result)
            if name=='all_missing':assert score==0.
            observation=json.loads((case/'derived/h010-analysis.json').read_text())
            if name=='hardcoded_tier_threshold':assert not next(v for v in observation['input_responses'] if v['name']=='price_tier_threshold')['pass']
            if name=='wrong_word_budget_ledger_correct':assert not observation['handoff']['budget_checks']['application/P1'] and observation['handoff']['budget_checks']['ledger/P1']
            result['observed_checkpoint_details']=str(case/'derived/h010-analysis.json')
        result['qa_root']=str(case);return name,result
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures=[pool.submit(run,name) for name in names if name not in results]
        for future in as_completed(futures):
            name,result=future.result();results[name]=result;print(json.dumps({'case':name,'scores':result.get('scores'),'error':result.get('error')}),flush=True)
    complete=set(results)==set(NAMES)
    report={'schema_version':'h010-author-controls/v1','status':'AUTHOR_CONTROLS_PASS' if complete else 'PARTIAL_AUTHOR_CONTROLS_PASS',
        'control_count':len(results),'planned_control_count':len(NAMES),'controls':results,'gt_bindings':bindings,'source_bindings':source_bindings,
        'limit':'Actual Office per control; reused controls only when every GT/source byte is identical. Author rule scores, not independent semantic scores or Harness runs.'}
    dump(args.output_dir/'validation.json',report);print(json.dumps({'status':report['status'],'count':len(results)}),flush=True)

if __name__=='__main__':main()
