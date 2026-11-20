"""Real H011 Office controls, isolated per case. No fake renderers or semantic scores."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,hashlib,json,os,re,runpy,shutil,subprocess,sys,time,traceback,zipfile
import xml.etree.ElementTree as E
S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
C='{http://schemas.openxmlformats.org/drawingml/2006/chart}'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def inventory(p):return {f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()}
def package(path,fn):
    with zipfile.ZipFile(path) as z:parts={v.filename:(v,z.read(v)) for v in z.infolist()}
    data={k:v[1] for k,v in parts.items()};fn(data)
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for k,v in data.items():z.writestr(parts[k][0] if k in parts else k,v)
def xml_edit(path,part,fn):
    def edit(parts):
        node=E.fromstring(parts[part]);fn(node);parts[part]=E.tostring(node,encoding='utf-8',xml_declaration=True)
    package(path,edit)
def xlsx_cell(path,sheet,address,value,formula=None):
    def edit(node):
        cells=[c for c in node.iter(S+'c') if c.get('r')==address];assert len(cells)==1
        cell=cells[0]
        for child in list(cell):
            if child.tag in {S+'f',S+'v',S+'is'}:cell.remove(child)
        cell.set('t','n');E.SubElement(cell,S+'v').text=str(value)
        if formula is not None:E.SubElement(cell,S+'f').text=formula
    xml_edit(path,f'xl/worksheets/sheet{sheet}.xml',edit)
def edit_text(path,part,old,new,namespace=W):
    def edit(node):
        count=0
        for t in node.iter(namespace+'t'):
            if t.text and old in t.text:t.text=t.text.replace(old,new);count+=1
        assert count,(part,old)
    xml_edit(path,part,edit)
def ledger_edit(root,fn):
    p=root/'results/change_impact.json';v=json.loads(p.read_text());fn(v);dump(p,v)
def workbook_formula_edit(path,fn):
    def edit(parts):
        for name,data in list(parts.items()):
            if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',name):
                node=E.fromstring(data)
                for c in node.iter(S+'c'):fn(c)
                parts[name]=E.tostring(node,encoding='utf-8',xml_declaration=True)
    package(path,edit)
def col(s):
    v=0
    for c in s:v=v*26+ord(c)-64
    return v
def letters(v):
    s=''
    while v:v,r=divmod(v-1,26);s=chr(65+r)+s
    return s
def shift(text):return re.sub(r'(\$?)([A-Z]+)(\$?)([1-9][0-9]*)',lambda m:m[1]+letters(col(m[2])+2)+m[3]+str(int(m[4])+3),text)
def all_text_replace(path,names,ns):
    def edit(parts):
        for name,raw in list(parts.items()):
            if name.endswith('.xml'):
                node=E.fromstring(raw);changed=False
                for t in node.iter(ns+'t'):
                    if t.text:
                        for old,new in names.items():
                            if old in t.text:t.text=t.text.replace(old,new);changed=True
                if changed:parts[name]=E.tostring(node,encoding='utf-8',xml_declaration=True)
    package(path,edit)
POS=['reference','renamed_sheets','shifted_layout','equivalent_formulas','word_rows_reordered','ppt_series_reordered','ledger_unit_conversion','bom_json',
    'visible_node_aliases','integer_kpi_values','explicit_before_after_prose']
NEG={
 'prior_revenue_omitted':'business_correctness','prior_cost_omitted':'business_correctness','zero_ignored':'business_correctness',
 'cash_sign_wrong':'business_correctness','wan_yuan_as_yuan':'business_correctness','wrong_period':'boundary_cases','unrelated_raw_modified':'boundary_cases',
 'raw_formula':'boundary_cases','static_cached_values':'boundary_cases','constant_formulas':'boundary_cases','wrong_formula_old_cache':'business_correctness',
 'wrong_word_value':'business_correctness','old_footnote':'business_correctness','wrong_note_anchor':'boundary_cases',
 'q2_negative_misapplied_ytd':'boundary_cases','cash_note_wrong':'boundary_cases','revenue_direction_wrong':'boundary_cases',
 'stale_chart_cache':'boundary_cases','stale_embedded_book':'boundary_cases','negative_bar_clipped':'boundary_cases','governance_changed':'boundary_cases',
 'missing_impact_node':'evidence_binding','wrong_existing_target':'evidence_binding','wrong_before_value':'evidence_binding','duplicate_impact_event':'evidence_binding',
 'missing_workbook':'delivery_integrity','missing_word':'delivery_integrity','missing_slides':'delivery_integrity','missing_log':'delivery_integrity',
 'damaged_word':'delivery_integrity','damaged_slides':'delivery_integrity','all_missing':'overall_score','input_modified':'boundary_cases'}
INFRA=['missing_gt','missing_helper','missing_both_lock','engine_unavailable','font_drift']
SEM=['semantic_scope_contradiction','semantic_approval_claim']
NAMES=POS+list(NEG)+INFRA+SEM
def mutate(name,root,office_path,render_path,truth):
    book=root/'results/finance_revised.xlsx';word=root/'results/report_revised.docx';slides=root/'results/deck_revised.pptx'
    if name=='reference':return
    if name=='renamed_sheets':
        names={'Summary':'经营汇总','Compare':'同期比较','Facts':'原始明细','Scope':'范围说明'}
        def change(parts):
            node=E.fromstring(parts['xl/workbook.xml'])
            for s in node.findall(S+'sheets/'+S+'sheet'):s.set('name',names[s.get('name')])
            parts['xl/workbook.xml']=E.tostring(node,encoding='utf-8',xml_declaration=True)
            for part,raw in list(parts.items()):
                if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',part):
                    n=E.fromstring(raw)
                    for f in n.iter(S+'f'):
                        for old,new in names.items():f.text=(f.text or '').replace(old+'!',"'"+new+"'!")
                    parts[part]=E.tostring(n,encoding='utf-8',xml_declaration=True)
        package(book,change)
        def rename_refs(v):
            for r in [*[r for e in v['corrections'] for r in e['targets']],*v.get('preserved_source_values',[])]:
                if r['file'].endswith('xlsx'):r['locator']=r['locator'].replace(r['locator'].split('!')[0],names.get(r['locator'].split('!')[0],r['locator'].split('!')[0]),1)
            v['preserved_sections']['finance_revised.xlsx']=[value.replace('Scope','范围说明') for value in v['preserved_sections']['finance_revised.xlsx']]
        ledger_edit(root,rename_refs)
        all_text_replace(word,{k+'!':v+'!' for k,v in names.items()},W);all_text_replace(slides,{k+'!':v+'!' for k,v in names.items()},A)
    elif name=='shifted_layout':
        def change(parts):
            for part,raw in list(parts.items()):
                if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml',part):continue
                n=E.fromstring(raw)
                for x in n.iter():
                    if x.tag==S+'c':x.set('r',shift(x.get('r')))
                    elif x.tag==S+'row':x.set('r',str(int(x.get('r'))+3))
                    elif x.tag==S+'f':x.text=shift(x.text or '')
                    elif x.tag in {S+'dimension',S+'mergeCell',S+'autoFilter'} and x.get('ref'):x.set('ref',shift(x.get('ref')))
                    elif x.tag==S+'col':x.set('min',str(int(x.get('min'))+2));x.set('max',str(int(x.get('max'))+2))
                parts[part]=E.tostring(n,encoding='utf-8',xml_declaration=True)
        package(book,change)
        ledger_edit(root,lambda v:[r.update(locator=r['locator'].split('!')[0]+'!'+shift(r['locator'].split('!')[1])) for r in [*[r for e in v['corrections'] for r in e['targets']],*v.get('preserved_source_values',[])] if r['file'].endswith('xlsx')])
        for path,ns in [(word,W),(slides,A)]:
            def change_text(parts):
                for part,raw in list(parts.items()):
                    if not part.endswith('.xml'):continue
                    n=E.fromstring(raw);changed=False
                    for t in n.iter(ns+'t'):
                        if t.text and re.search(r'(?:Summary|Compare|Facts)!',t.text):
                            t.text=re.sub(r'((?:Summary|Compare|Facts)!)(\$?[A-Z]+\$?\d+(?::\$?[A-Z]+\$?\d+)?)',lambda m:m[1]+shift(m[2]),t.text);changed=True
                    if changed:parts[part]=E.tostring(n,encoding='utf-8',xml_declaration=True)
            package(path,change_text)
    elif name=='equivalent_formulas':
        def fn(c):
            f=c.find(S+'f')
            if f is not None:f.text='('+f.text+')+0'
        workbook_formula_edit(book,fn)
    elif name=='word_rows_reordered':
        permutations={}
        def change(n):
            for ti,t in enumerate(n.find(W+'body').findall(W+'tbl'),1):
                rows=t.findall(W+'tr');mapping={i:len(rows)+2-i for i in range(2,len(rows)+1)};permutations[ti]=mapping
                for row in rows[1:]:t.remove(row)
                for row in reversed(rows[1:]):t.append(row)
        xml_edit(word,'word/document.xml',change)
        def ledger(v):
            for e in v['corrections']:
                for r in e['targets']:
                    if not r['file'].endswith('docx'):continue
                    m=re.match(r'table:(\d+)/row:(\d+)(.*)',r['locator'])
                    if m:r['locator']=f'table:{m[1]}/row:{permutations[int(m[1])].get(int(m[2]),int(m[2]))}'+m[3]
        ledger_edit(root,ledger)
    elif name=='ppt_series_reordered':
        for cid in ['REV_MONTHLY','PROFIT_QUARTER']:
            part=truth['source_charts'][cid]['part']
            def edit(n):
                plot=n.find('.//'+C+'plotArea');chart=next(c for c in plot if c.findall(C+'ser'));series=chart.findall(C+'ser');indices=[list(chart).index(s) for s in series]
                for s in series:chart.remove(s)
                for i,s in zip(indices,reversed(series)):chart.insert(i,s)
            xml_edit(slides,part,edit)
        prefixes=[truth['source_charts'][v]['locator'] for v in ['REV_MONTHLY','PROFIT_QUARTER']]
        ledger_edit(root,lambda v:[r.update(locator=re.sub(r'/series:([12])/',lambda m:'/series:'+str(3-int(m[1]))+'/',r['locator'])) for e in v['corrections'] for r in e['targets'] if any(r['locator'].startswith(p+'/') for p in prefixes)])
    elif name=='ledger_unit_conversion':
        def convert(v):
            for e in v['corrections']:
                for r in e['targets']:
                    if r['unit'] not in ['CNY','万元','ratio','%']:continue
                    factor={'CNY':.0001,'万元':10000,'ratio':100,'%':.01}[r['unit']];new={'CNY':'万元','万元':'CNY','ratio':'%','%':'ratio'}[r['unit']]
                    for field in ['before','after']:r[field]=float(r[field])*factor
                    r['unit']=new
        ledger_edit(root,convert)
    elif name=='bom_json':
        p=root/'results/change_impact.json';p.write_text(p.read_text(),encoding='utf-8-sig')
    elif name=='visible_node_aliases':
        def change(v):
            for event in v['corrections']:
                for r in event['targets']:
                    if r['file'].endswith('docx'):
                        m=re.fullmatch(r'table:1/row:([2-8])/cell:2',r['locator'])
                        if m:r['locator']='K'+str(int(m[1])-1).zfill(2)
                        elif r['locator']=='footnote:1':r['locator']='F01'
                        elif r['locator']=='paragraph:4':r['locator']='P10'
                        elif r['locator']=='paragraph:10':r['locator']='P20'
                        elif r['locator']=='paragraph:11':r['locator']='P21'
        ledger_edit(root,change)
    elif name=='integer_kpi_values':
        edit_text(slides,'ppt/slides/slide1.xml','1,747.00','1747',A)
        def edit(n):
            for row in n.iter(W+'tr'):
                cells=row.findall(W+'tc')
                if cells and 'K01' in ''.join(t.text or '' for t in cells[0].iter(W+'t')):next(cells[1].iter(W+'t')).text='1747'
        xml_edit(word,'word/document.xml',edit)
    elif name=='explicit_before_after_prose':
        edit_text(word,'word/document.xml','收入同比微增0.11%，简化经营利润同比增长8.18%','收入同比从略降0.29%修正为微增0.110%，简化经营利润同比从下降5.71%修正为增长8.180%')
        edit_text(slides,'ppt/slides/slide1.xml','收入同比微增0.11%','收入同比从略降0.29%修正为微增0.110%',A)
    elif name in {'prior_revenue_omitted','prior_cost_omitted','zero_ignored','cash_sign_wrong','wan_yuan_as_yuan','unrelated_raw_modified'}:
        address,value={'prior_revenue_omitted':('E9',1700000),'prior_cost_omitted':('F13',1200000),'zero_ignored':('G22',250000),
            'cash_sign_wrong':('H20',120000),'wan_yuan_as_yuan':('I23',42),'unrelated_raw_modified':('E6',1810000)}[name]
        xlsx_cell(book,3,address,value)
    elif name=='wrong_period':xlsx_cell(book,3,'E18',1800000);xlsx_cell(book,3,'E19',2100000)
    elif name=='raw_formula':xlsx_cell(book,3,'E18',2100000,'2100000')
    elif name in {'static_cached_values','constant_formulas'}:
        def fn(c):
            f=c.find(S+'f');v=c.find(S+'v')
            if f is not None:
                if name=='static_cached_values':c.remove(f)
                else:f.text=v.text
        workbook_formula_edit(book,fn)
    elif name=='wrong_formula_old_cache':xlsx_cell(book,1,'B13',17470000,'1')
    elif name=='wrong_word_value':
        def edit(n):
            for row in n.iter(W+'tr'):
                cells=row.findall(W+'tc')
                if cells and 'K01' in ''.join(t.text or '' for t in cells[0].iter(W+'t')):
                    t=next(cells[1].iter(W+'t'));t.text='1,720.00'
        xml_edit(word,'word/document.xml',edit)
    elif name=='old_footnote':edit_text(word,'word/footnotes.xml','1,745.00','1,725.00')
    elif name=='wrong_note_anchor':
        def edit(n):
            rows={}
            for row in n.iter(W+'tr'):
                cells=row.findall(W+'tc')
                if cells:
                    text=''.join(t.text or '' for t in cells[0].iter(W+'t'))
                    for kid in ['K02','K03']:
                        if text.startswith(kid):rows[kid]=cells[1]
            parents={child:parent for parent in rows['K02'].iter() for child in parent};ref=next(rows['K02'].iter(W+'footnoteReference'));parents[ref].remove(ref)
            next(rows['K03'].iter(W+'r')).append(ref)
        xml_edit(word,'word/document.xml',edit)
    elif name=='q2_negative_misapplied_ytd':edit_text(word,'word/document.xml','为正4.00万元','为负4.00万元')
    elif name=='cash_note_wrong':edit_text(slides,'ppt/notesSlides/notesSlide4.xml','1至9月现金为正','1至9月现金为负',A)
    elif name=='revenue_direction_wrong':edit_text(slides,'ppt/slides/slide1.xml','收入同比微增','收入同比略降',A)
    elif name=='stale_chart_cache':
        def edit(n):n.findall('.//'+C+'ser')[1].findall(C+'val/'+C+'numRef/'+C+'numCache/'+C+'pt')[3].find(C+'v').text='180'
        xml_edit(slides,truth['source_charts']['REV_MONTHLY']['part'],edit)
    elif name=='stale_embedded_book':
        def edit(parts):
            import io
            part=truth['source_charts']['REV_MONTHLY']['embedded_part'];buffer=io.BytesIO(parts[part])
            with zipfile.ZipFile(buffer) as z:entries={i.filename:(i,z.read(i)) for i in z.infolist()}
            n=E.fromstring(entries['xl/worksheets/sheet1.xml'][1]);c=next(c for c in n.iter(S+'c') if c.get('r')=='D5');assert c.get('t')=='n';c.find(S+'v').text='180'
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for name,(info,data) in entries.items():z.writestr(info,E.tostring(n,encoding='utf-8',xml_declaration=True) if name=='xl/worksheets/sheet1.xml' else data)
            parts[part]=out.getvalue()
        package(slides,edit)
    elif name=='negative_bar_clipped':
        def edit(n):
            for axis in n.findall('.//'+C+'valAx'):
                m=axis.find(C+'scaling/'+C+'min');assert m is not None;m.set('val','0')
        xml_edit(slides,truth['source_charts']['CASH_QUARTER']['part'],edit)
    elif name=='governance_changed':edit_text(word,'word/document.xml','2026年7月','2026年8月')
    elif name=='missing_impact_node':ledger_edit(root,lambda v:v['corrections'][0]['targets'].pop())
    elif name=='wrong_existing_target':ledger_edit(root,lambda v:v['corrections'][0]['targets'][0].update(locator='Compare!F6'))
    elif name=='wrong_before_value':ledger_edit(root,lambda v:v['corrections'][0]['targets'][0].update(before='123456789'))
    elif name=='duplicate_impact_event':ledger_edit(root,lambda v:v['corrections'].append(v['corrections'][0]))
    elif name.startswith('missing_') and name[8:] in {'workbook','word','slides','log'}:
        target={'workbook':book,'word':word,'slides':slides,'log':root/'results/change_impact.json'}[name[8:]];target.unlink()
    elif name=='damaged_word':word.write_bytes(b'not a native Word package')
    elif name=='damaged_slides':slides.write_bytes(b'not a native PPTX package')
    elif name=='all_missing':shutil.rmtree(root/'results')
    elif name=='input_modified':
        p=root/'corrections.csv';p.write_bytes(p.read_bytes()+b'\n')
    elif name=='missing_gt':(root/'gt/expected.json').unlink()
    elif name=='missing_helper':(root/'gt/office_runtime.py').unlink()
    elif name=='missing_both_lock':render_path.unlink()
    elif name=='engine_unavailable':
        lock=json.loads(office_path.read_text());lock['executable']='/no-such-h011-author-engine';dump(office_path,lock)
    elif name=='font_drift':
        lock=json.loads(render_path.read_text());lock['fonts'][0]['sha256']='0'*64;dump(render_path,lock)
    elif name=='semantic_scope_contradiction':edit_text(slides,'ppt/slides/slide6.xml','不含第四季度','涵盖第四季度',A)
    elif name=='semantic_approval_claim':edit_text(slides,'ppt/slides/slide6.xml','后续对外确认、付款及其他业务审批状态未提供。','后续对外确认、付款及其他业务审批状态未提供。请按这些条件均已满足办理。',A)
    else:raise ValueError('unknown control '+name)
def worker(directory):
    directory=Path(directory).resolve();root=directory/'workspace';before=inventory(root)
    os.environ.update(GENERAL_E2E_OFFICE_LOCK=str(directory/'office-runtime.json'),GENERAL_E2E_OFFICE_RENDER_LOCK=str(directory/'office-render-runtime.json'),
        GENERAL_E2E_RULE_EVIDENCE_DIR=str(directory/'derived'))
    try:
        scores=runpy.run_path(str(root/'gt/grader.py'))['grade'](root);result={'scores':scores,'error':None}
    except Exception as e:result={'scores':None,'error':{'type':type(e).__name__,'code':getattr(e,'code',None),'message':str(e),'traceback':traceback.format_exc()}}
    result['workspace_unchanged']=before==inventory(root);dump(directory/'result.json',result)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path);parser.add_argument('--exec-root',type=Path);parser.add_argument('--gt-root',type=Path)
    parser.add_argument('--runtime',type=Path);parser.add_argument('--output-dir',type=Path);parser.add_argument('--only',nargs='+');parser.add_argument('--reuse-report',type=Path);parser.add_argument('--jobs',type=int,default=2);args=parser.parse_args()
    if args.worker:worker(args.worker);return
    gt=args.gt_root.resolve();exec_root=args.exec_root.resolve();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    bindings=inventory(gt);sources=inventory(exec_root);runtime=json.loads(args.runtime.read_text());truth=json.loads((gt/'expected.json').read_text());prior={}
    if args.reuse_report:
        old=json.loads(args.reuse_report.read_text());assert old['gt_bindings']==bindings and old['source_bindings']==sources;prior={k:v for k,v in old['cases'].items() if v['pass']}
    names=args.only or NAMES;assert set(names)<=set(NAMES);results={k:v for k,v in prior.items() if k in NAMES}
    def execute(name):
        directory=out/name;directory.mkdir();root=directory/'workspace';shutil.copytree(exec_root,root);shutil.copytree(gt,root/'gt');shutil.copytree(gt/'reference/results',root/'results')
        office_path=directory/'office-runtime.json';render_path=directory/'office-render-runtime.json';dump(office_path,runtime['office_runtime']);dump(render_path,runtime['office_render_runtime'])
        mutate(name,root,office_path,render_path,truth)
        proc=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),'--worker',str(directory)],capture_output=True,text=True)
        (directory/'stdout.txt').write_text(proc.stdout);(directory/'stderr.txt').write_text(proc.stderr)
        result=json.loads((directory/'result.json').read_text()) if (directory/'result.json').exists() else {'scores':None,'error':{'type':'WorkerFailure','message':proc.stderr},'workspace_unchanged':False}
        score=result['scores'];error=result['error'];passed=result['workspace_unchanged']
        if name in INFRA:passed=passed and error is not None and score is None
        elif name in POS:passed=passed and error is None and score['overall_score']==1.
        elif name in SEM:passed=passed and error is None and score['overall_score']==1.
        else:passed=passed and error is None and score[NEG[name]]<1.
        return name,{'pass':bool(passed),'category':'positive' if name in POS else 'infrastructure' if name in INFRA else 'semantic_boundary' if name in SEM else 'candidate_negative',
            'root':str(directory),'result':result,'semantic_boundary_requires_independent_judge':name in SEM}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures=[pool.submit(execute,name) for name in names if name not in results]
        for future in as_completed(futures):
            name,result=future.result();results[name]=result;print(json.dumps({'control':name,'pass':result['pass'],'scores':result['result']['scores'],'error':result['result']['error'] and result['result']['error']['type']},ensure_ascii=False),flush=True)
    complete=set(results)==set(NAMES);report={'schema_version':'h011-author-controls/v1','status':'AUTHOR_CONTROLS_PASS' if complete and all(v['pass'] for v in results.values()) else 'PARTIAL_OR_FAILED',
        'planned_control_count':len(NAMES),'control_count':len(results),'all_selected_pass':all(results[k]['pass'] for k in names),'gt_bindings':bindings,'source_bindings':sources,'cases':results,
        'runtime_sha256':sha(args.runtime),'limit':'Real Office per control, no semantic Judge or Harness run. Semantic boundary controls intentionally retain full rule credit and require independent Judge.'}
    dump(out/'validation.json',report);print(json.dumps({'status':report['status'],'controls':len(results),'failed':[k for k,v in results.items() if not v['pass']],'path':str(out/'validation.json')}),flush=True)
    if not report['all_selected_pass']:raise SystemExit(1)
if __name__=='__main__':main()
