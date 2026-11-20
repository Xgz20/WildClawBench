"""Disposable native control fixtures; logical reference artifacts remain frozen.
These mutations test scoring equivalence, not new user-facing artifact authoring.
"""
from pathlib import Path
import argparse,copy,csv,hashlib,io,json,os,re,runpy,shutil,sys,zipfile
import xml.etree.ElementTree as E
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def mutate(path,part,fn):
    with zipfile.ZipFile(path) as z:parts=[(i,z.read(i.filename)) for i in z.infolist()]
    root=E.fromstring(next(b for i,b in parts if i.filename==part));fn(root)
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for info,data in parts:z.writestr(info,E.tostring(root,encoding='utf-8',xml_declaration=True) if info.filename==part else data)
def sheet(w,index,fn):mutate(w/'results/comparison.xlsx','xl/worksheets/sheet'+str(index)+'.xml',fn)
def cell(root,addr):return next(c for c in root.iter(X+'c') if c.get('r')==addr)
def put(root,addr,value,formula=False):
    c=cell(root,addr)
    for n in list(c):
        if n.tag in {X+'f',X+'v',X+'is'}:c.remove(n)
    c.attrib.pop('t',None)
    if formula:E.SubElement(c,X+'f').text=str(value).lstrip('=')
    elif isinstance(value,str):c.set('t','inlineStr');E.SubElement(E.SubElement(c,X+'is'),X+'t').text=value
    elif value is not None:E.SubElement(c,X+'v').text=str(value)
def literal_formula(value):return '""' if value is None else '"'+value.replace('"','""')+'"' if isinstance(value,str) else str(value)
def metric_static(w,formula=False):
    def patch(root):
        for row,want in enumerate(EXPECTED['baseline'],6):
            for col,key in zip('DEFGHIJ',CONTRACT['metric_fields']):
                value='n/a' if want[key] is None else want[key];put(root,col+str(row),literal_formula(value) if formula else value,formula)
    sheet(w,1,patch)
def stale_caches(w):
    def patch(root):
        for c in root.iter(X+'c'):
            if c.find(X+'f') is not None:
                c.set('t','e')
                for n in list(c.findall(X+'v')):c.remove(n)
                E.SubElement(c,X+'v').text='#VALUE!'
    for i in range(1,4):sheet(w,i,patch)
def source_formulas(w):
    def patch(root):
        for c in list(root.iter(X+'c')):
            if not re.fullmatch(r'[C-I](?:[6-9]|1[0-4])',c.get('r','')):continue
            v=c.find(X+'v')
            if v is None or v.text is None:continue
            text=v.text;put(root,c.get('r'),'('+text+')+0',True);c=cell(root,c.get('r'));E.SubElement(c,X+'v').text='999'
    sheet(w,2,patch)
def renamed(w):
    names={'指标':'对标结果','数据':'生效来源','重述':'更正登记'}
    mutate(w/'results/comparison.xlsx','xl/workbook.xml',lambda d:[s.set('name',names[s.get('name')]) for s in d.find(X+'sheets')])
    def patch(root):
        for f in root.iter(X+'f'):
            for a,b in names.items():f.text=(f.text or '').replace("'"+a+"'!","'"+b+"'!").replace(a+'!',b+'!')
    for i in range(1,4):sheet(w,i,patch)
def change_layout(w,mode):
    from openpyxl.formula.tokenizer import Tokenizer
    mapping={r:6+((r-6)//3)*3+2-(r-6)%3 for r in range(6,33)} if mode=='rows' else {}
    def point(addr):
        m=re.fullmatch(r'(\$?)([A-Z]+)(\$?)(\d+)',addr)
        if not m:return addr
        col=0
        for c in m[2]:col=col*26+ord(c)-64
        row=int(m[4]);col=11-col if mode=='cols' and 1<=col<=10 else col+2 if mode=='shift' else col;row=mapping.get(row,row) if mode=='rows' else row+3 if mode=='shift' else row;letters=''
        while col:col,x=divmod(col-1,26);letters=chr(65+x)+letters
        return m[1]+letters+m[3]+str(row)
    def formula(text):
        tokens=Tokenizer('='+text).items
        for token in tokens:
            if token.subtype!='RANGE' or '!' in token.value:continue
            ends=token.value.split(':');new=[point(x) for x in ends]
            if len(new)==2 and re.sub(r'\d','',new[0])==re.sub(r'\d','',new[1]) and int(re.search(r'\d+',new[0])[0])>int(re.search(r'\d+',new[1])[0]):new.reverse()
            token.value=':'.join(new)
        return ''.join(t.value for t in tokens)
    def patch(root):
        data=root.find(X+'sheetData')
        for row in data:
            r=int(row.get('r'));row.set('r',str(mapping.get(r,r) if mode=='rows' else r+3 if mode=='shift' else r))
            for c in row:
                c.set('r',point(c.get('r')))
                f=c.find(X+'f')
                if f is not None:f.text=formula(f.text or '')
            row[:]=sorted(row,key=lambda c:len(re.match(r'[A-Z]+',c.get('r'))[0])*1000+sum(ord(x) for x in re.match(r'[A-Z]+',c.get('r'))[0]))
        data[:]=sorted(data,key=lambda r:int(r.get('r')))
        dimension=root.find(X+'dimension')
        if dimension is not None:dimension.set('ref','A1:L35' if mode=='shift' else 'A1:J32')
        cols=root.find(X+'cols')
        if cols is not None:
            for col in cols:col.set('width','30')
    sheet(w,1,patch)
def chinese(w):
    def patch(root):
        mapping={a:next((x for x in values if re.search('[\u4e00-\u9fff]',x)),a) for a,values in CONTRACT['aliases'].items()}
        by={IO['canon'](a):key for key,values in CONTRACT['aliases'].items() for a in values}
        for c in list(root.iter(X+'c')):
            texts=c.findall('.//'+X+'t')
            if c.get('r','').endswith('5') and texts:
                k=by.get(IO['canon'](''.join(t.text or '' for t in texts)))
                if k:put(root,c.get('r'),mapping[k])
    for i in range(1,4):sheet(w,i,patch)
def chinese_values(w):
    metrics={'revenue_yoy':'收入同比','roe':'归母ROE','cash_to_profit':'经营现金与归母利润比'};words={'ok':'正常','not_comparable':'不可比','missing_base':'上年收入未披露','scope_change':'收入同比范围变更','zero_profit':'现金比率分母为0','missing_cash':'经营现金流未披露'}
    def patch(root):
        for c in list(root.iter(X+'c')):
            if re.fullmatch(r'C(?:[6-9]|[12]\d|3[0-2])',c.get('r','')):
                value=''.join(t.text or '' for t in c.iter(X+'t'))
                if value in metrics:put(root,c.get('r'),metrics[value])
        for f in root.iter(X+'f'):
            for a,b in words.items():f.text=(f.text or '').replace('"'+a+'"','"'+b+'"')
    sheet(w,1,patch)
def split_metric_tables(w):
    from openpyxl.formula.tokenizer import Tokenizer
    mapping={r:r+6*((r-6)//9) for r in range(6,33)}
    def patch(root):
        data=root.find(X+'sheetData');header=copy.deepcopy(data.find(X+'row[@r="5"]'))
        for row in data:
            old=int(row.get('r'));new=mapping.get(old,old);row.set('r',str(new))
            for c in row:
                c.set('r',re.sub(r'\d+$',str(new),c.get('r')));f=c.find(X+'f')
                if f is not None:
                    tokens=Tokenizer('='+f.text).items
                    for t in tokens:
                        if t.subtype=='RANGE' and '!' not in t.value:t.value=re.sub(r'(\$?[A-Z]+\$?)(\d+)',lambda m:m[1]+str(mapping.get(int(m[2]),int(m[2]))),t.value)
                    f.text=''.join(t.value for t in tokens)
        for r in [20,35]:
            n=copy.deepcopy(header);n.set('r',str(r))
            for c in n:c.set('r',re.sub(r'\d+$',str(r),c.get('r')))
            data.append(n)
        data[:]=sorted(data,key=lambda r:int(r.get('r')))
    sheet(w,1,patch)
def snapshot_metric(w):
    def patch(root):
        data=root.find(X+'sheetData');old=list(data)
        for row in old:
            r=int(row.get('r'))
            if r<5:continue
            n=copy.deepcopy(row);n.set('r',str(r+40))
            for c in n:
                addr=re.sub(r'\d+$',str(r+40),c.get('r'));c.set('r',addr)
                if c.find(X+'f') is not None:
                    field=CONTRACT['metric_fields'][ord(re.match(r'[A-Z]',addr)[0])-68];want=EXPECTED['baseline'][r-6][field]
                    for x in list(c):c.remove(x)
                    c.attrib.pop('t',None)
                    if isinstance(want,str) or want is None:c.set('t','inlineStr');E.SubElement(E.SubElement(c,X+'is'),X+'t').text=want if want is not None else 'n/a'
                    else:E.SubElement(c,X+'v').text=str(want)
            data.append(n)
        dimension=root.find(X+'dimension')
        if dimension is not None:dimension.set('ref','A1:J72')
    sheet(w,1,patch)
def source_snapshot_first(w):
    def data_patch(root):
        data=root.find(X+'sheetData')
        for row in list(data):
            r=int(row.get('r'))
            if 5<=r<=14:
                n=copy.deepcopy(row);n.set('r',str(r+20))
                for c in n:c.set('r',re.sub(r'\d+$',str(r+20),c.get('r')))
                data.append(n)
        dimension=root.find(X+'dimension')
        if dimension is not None:dimension.set('ref','A1:I34')
    sheet(w,2,data_patch)
    def model_patch(root):
        for f in root.iter(X+'f'):
            f.text=re.sub(r"('数据'!\$?[A-Z]+\$?)(\d+)(?::(\$?[A-Z]+\$?)(\d+))?",lambda m:m[1]+str(int(m[2])+20)+(':'+m[3]+str(int(m[4])+20) if m[3] else ''),f.text or '')
    sheet(w,1,model_patch)
def company_names(w):
    labels={'A':'青川实业','B':'北辰服务','C':'澄星制造'}
    def patch(root):
        for c in list(root.iter(X+'c')):
            if re.fullmatch(r'A(?:[6-9]|[12]\d|3[0-2])',c.get('r','')):
                text=''.join(t.text or '' for t in c.iter(X+'t'))
                if text in labels:put(root,c.get('r'),labels[text])
    for i in [1,2]:sheet(w,i,patch)
def csv_variant(w,kind):
    p=w/'results/sources.csv';reader=csv.DictReader(p.open(encoding='utf-8-sig',newline=''));headers=reader.fieldnames;rows=list(reader)
    if kind=='reorder':headers=list(reversed(headers));rows.reverse()
    elif kind=='file':rows[0]['source_file']='statements/B_disclosure_2024.md'
    elif kind=='locator':rows[0]['locator']='A2023-IS02'
    elif kind=='revision':next(r for r in rows if r['company_id']=='A' and r['period_year']=='2025' and r['field']=='prior_revenue').update(restatement_id='',adjustment_source='',adjustment_locator='')
    elif kind=='reported':rows[0]['reported_value']='999'
    elif kind=='duplicate':rows.append(dict(rows[0]))
    elif kind=='missing':rows.pop()
    with p.open('w',encoding='utf-8-sig' if kind=='reorder' else 'utf-8',newline='') as f:writer=csv.DictWriter(f,fieldnames=headers);writer.writeheader();writer.writerows(rows)
def word_patch(w,kind):
    def patch(root):
        body=root.find(W+'body')
        if kind=='prose':
            for t in list(body.findall(W+'tbl')):
                header=[''.join(n.text or '' for n in c.iter(W+'t')) for c in t.find(W+'tr')]
                if header[:3]==['公司','年度','指标']:body.remove(t)
            for r in EXPECTED['baseline']:
                value='n/a' if r['value'] is None else f"{r['value']*100:.4f}%";rank='n/a' if r['rank'] is None else r['rank'];change='n/a' if r['change_pp'] is None else f"{r['change_pp']:.4f}";p=E.Element(W+'p');E.SubElement(E.SubElement(p,W+'r'),W+'t').text=f"{r['company_id']} {r['period_year']} {r['metric_id']}: value={value}; rank={rank}; change_pp={change}";body.insert(len(body)-1,p)
        elif kind=='merged':
            t=body.find(W+'tbl')
            for i,row in enumerate(t.findall(W+'tr')[1:]):
                c=row.findall(W+'tc')[1];pr=c.find(W+'tcPr');E.SubElement(pr,W+'vMerge',{W+'val':'restart' if i==0 else 'continue'})
                if i:
                    for x in list(c):
                        if x.tag!=W+'tcPr':c.remove(x)
                    E.SubElement(c,W+'p')
        elif kind=='wrong_value':
            n=next(n for n in body.iter(W+'t') if n.text=='18.41%');n.text='8.41%'
        elif kind=='hidden':
            for run in body.iter(W+'r'):
                pr=run.find(W+'rPr')
                if pr is None:pr=E.SubElement(run,W+'rPr')
                E.SubElement(pr,W+'vanish')
        elif kind=='false_claim':
            p=E.Element(W+'p');E.SubElement(E.SubElement(p,W+'r'),W+'t').text='三项比率已证明青川实业综合投资价值必然最好，未来回款必然增长，本结论已经真实审计并通过审批。';body.insert(len(body)-1,p)
    mutate(w/'results/memo.docx','word/document.xml',patch)
def shared_source(w,scope=False):
    def patch(root):
        targets=['I9','I10','I11'] if scope else ['C7','C8'];anchor=targets[0];expression='IF(B9=2024,0,1)' if scope else 'IF(B7=2024,146000,162000)'
        for addr in targets:
            c=cell(root,addr)
            for f in list(c.findall(X+'f')):c.remove(f)
            f=E.SubElement(c,X+'f',t='shared',si='0')
            if addr==anchor:f.set('ref',anchor+':'+targets[-1]);f.text=expression
    sheet(w,2,patch)
def drift_font(w):
    p=w.parent/'bad-render-lock.json';lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']).read_text());lock['fonts'][0]['sha256']='0'*64;dump(p,lock);os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']=str(p)
def missing(w,name):(w/name).unlink()
CASES={
 'reference':('positive',lambda w:None),'renamed_sheets':('positive',renamed),'reordered_metric_rows':('positive',lambda w:change_layout(w,'rows')),'reordered_metric_columns':('positive',lambda w:change_layout(w,'cols')),'shifted_metric_table':('positive',lambda w:change_layout(w,'shift')),'chinese_headers':('positive',chinese),'scalar_source_formulas':('positive',source_formulas),'wrong_caches_correct_formulas':('positive',stale_caches),'csv_bom_reordered':('positive',lambda w:csv_variant(w,'reorder')),'metric_snapshot_view':('positive',snapshot_metric),'source_snapshot_first':('positive',source_snapshot_first),'company_name_aliases':('positive',company_names),'word_record_paragraphs':('positive',lambda w:word_patch(w,'prose')),'word_merged_year':('positive',lambda w:word_patch(w,'merged')),
 'unit_thousandfold':('negative',lambda w:sheet(w,2,lambda d:put(d,'C7',146000000))), 'disclosure_as_report_year':('negative',lambda w:sheet(w,1,lambda d:[put(d,'B'+str(r),2024+(r-6)//9) for r in range(6,33)])), 'consolidated_profit':('negative',lambda w:sheet(w,2,lambda d:put(d,'D9',5600))), 'total_equity':('negative',lambda w:sheet(w,2,lambda d:put(d,'G11',65000))), 'closing_equity_only':('negative',lambda w:sheet(w,1,lambda d:put(d,'E27',"'数据'!G8",True))), 'stale_revision':('negative',lambda w:sheet(w,2,lambda d:put(d,'C7',144000))), 'fixed_next_year_base':('negative',lambda w:sheet(w,1,lambda d:put(d,'E24','146000',True))), 'missing_as_zero':('negative',lambda w:sheet(w,2,lambda d:put(d,'E13',0))), 'valid_zero_as_na':('negative',lambda w:sheet(w,1,lambda d:put(d,'F11','"n/a"',True))), 'negative_cash_abs':('negative',lambda w:sheet(w,2,lambda d:put(d,'E8',3240))), 'tie_ordinal':('negative',lambda w:sheet(w,1,lambda d:put(d,'G29','3',True))), 'parent_cash_flow':('negative',lambda w:sheet(w,2,lambda d:put(d,'E7',4500))), 'static_model':('negative',metric_static),'constant_formula_model':('negative',lambda w:metric_static(w,True)), 'wrong_formula_good_cache':('negative',lambda w:sheet(w,1,lambda d:setattr(cell(d,'F24').find(X+'f'),'text','999'))), 'formula_error_good_cache':('negative',lambda w:sheet(w,1,lambda d:setattr(cell(d,'F24').find(X+'f'),'text','1/0'))), 'missing_metric':('negative',lambda w:sheet(w,1,lambda d:d.find(X+'sheetData').remove(d.find(X+'sheetData/'+X+'row[@r="6"]')))), 'hidden_metrics':('negative',lambda w:mutate(w/'results/comparison.xlsx','xl/workbook.xml',lambda d:d.find(X+'sheets')[0].set('state','hidden'))), 'source_file_wrong':('negative',lambda w:csv_variant(w,'file')), 'source_locator_wrong':('negative',lambda w:csv_variant(w,'locator')), 'source_revision_missing':('negative',lambda w:csv_variant(w,'revision')), 'reported_value_wrong':('negative',lambda w:csv_variant(w,'reported')), 'source_duplicate':('negative',lambda w:csv_variant(w,'duplicate')), 'source_missing':('negative',lambda w:csv_variant(w,'missing')), 'word_value_wrong':('negative',lambda w:word_patch(w,'wrong_value')), 'word_hidden':('negative',lambda w:word_patch(w,'hidden')), 'missing_book':('negative',lambda w:missing(w,'results/comparison.xlsx')), 'bad_book':('negative',lambda w:(w/'results/comparison.xlsx').write_bytes(b'not-xlsx')), 'missing_word':('negative',lambda w:missing(w,'results/memo.docx')), 'missing_sources':('negative',lambda w:missing(w,'results/sources.csv')), 'input_changed':('negative',lambda w:(w/'metrics_definition.md').write_text((w/'metrics_definition.md').read_text()+'\nchanged\n')),
 'chinese_metric_values':('positive',chinese_values),'split_year_metric_tables':('positive',split_metric_tables),
 'unsupported_claim':('semantic',lambda w:word_patch(w,'false_claim')),
 'missing_GT':('infrastructure',lambda w:missing(w,'gt/expected.json')), 'helper_drift':('infrastructure',lambda w:(w/'gt/financial_io.py').write_text((w/'gt/financial_io.py').read_text()+'\n# drift\n')), 'missing_office_context':('infrastructure',lambda w:os.environ.pop('GENERAL_E2E_OFFICE_LOCK')), 'font_drift':('infrastructure',drift_font),'shared_numeric_source':('capability',lambda w:shared_source(w)), 'shared_scope_source':('capability',lambda w:shared_source(w,True))}
P=argparse.ArgumentParser(description='H020 independent disposable author control runner, not model scoring');P.add_argument('--case',action='append');P.add_argument('--kind',choices=['positive','negative','semantic','infrastructure','capability']);P.add_argument('--list-cases',action='store_true');P.add_argument('--dataset-workspace',type=Path,default=Path(__file__).resolve().parents[1]);P.add_argument('--office-lock',type=Path);P.add_argument('--render-lock',type=Path);P.add_argument('--output-dir',type=Path);args=P.parse_args()
if args.list_cases:print(json.dumps({n:k for n,(k,_) in CASES.items()}));raise SystemExit
if not args.office_lock or not args.render_lock or not args.output_dir:P.error('explicit Office/render locks and external new output directory required')
BASE=args.dataset_workspace.resolve();out=args.output_dir.resolve()
if out==BASE or BASE in out.parents:P.error('output directory must be outside dataset Workspace')
names=args.case or [n for n,(kind,_) in CASES.items() if args.kind is None or kind==args.kind]
if not set(names)<=set(CASES):P.error('unknown case')
out.mkdir(parents=True,exist_ok=False);frozen=out/'source';shutil.copytree(BASE/'exec',frozen/'exec');shutil.copytree(BASE/'gt',frozen/'gt',ignore=shutil.ignore_patterns('__pycache__'));shutil.copyfile(__file__,out/'control-script.py');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();dump(out/'source-binding.json',{p.relative_to(frozen).as_posix():sha(p) for p in frozen.rglob('*') if p.is_file()});EXPECTED=json.loads((frozen/'gt/expected.json').read_text());CONTRACT=json.loads((frozen/'gt/runtime_contract.json').read_text());IO=runpy.run_path(str(frozen/'gt/financial_io.py'));CHECKS=runpy.run_path(str(frozen/'gt/business_checks.py'));results=[]
for name in names:
    kind,action=CASES[name];case=out/name;w=case/'workspace';shutil.copytree(frozen/'exec',w);shutil.copytree(frozen/'gt',w/'gt',ignore=shutil.ignore_patterns('reference','__pycache__'));shutil.copytree(frozen/'gt/reference/results',w/'results');os.environ['GENERAL_E2E_OFFICE_LOCK']=str(args.office_lock.resolve());os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']=str(args.render_lock.resolve());os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(case/'derived');action(w);before={p.relative_to(w).as_posix():sha(p) for p in w.rglob('*') if p.is_file()};scores=None;error=None;baseline_valid=None
    try:scores=runpy.run_path(str(w/'gt/grader.py'))['grade'](w)
    except Exception as exc:error={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)}
    if kind=='capability':
        books=[p for p in [case/'derived/baseline/recalculated.xlsx'] if p.is_file()]
        if len(books)==1:baseline_valid=CHECKS['metrics'](IO['XLSX']['read_book'](books[0]),EXPECTED['baseline'],CONTRACT,IO)['complete']
    after={p.relative_to(w).as_posix():sha(p) for p in w.rglob('*') if p.is_file() and '__pycache__' not in p.parts};ok=scores is not None and scores['overall_score']==1. if kind in {'positive','semantic'} else scores is not None and scores['overall_score']<1. if kind=='negative' else error is not None and scores is None
    if name=='constant_formula_model' and scores is not None:
        observation=json.loads((case/'derived/h020-analysis.json').read_text());ok=ok and observation['metrics']['complete'] and len(observation['formula_responses']['cases'])==5 and observation['formula_responses']['score']==0. and scores['business_correctness']==.5
    if kind=='capability':ok=ok and baseline_valid is True and bool(error) and error['code'] in {'OFFICE_NUMERIC_INTERVENTION_UNSUPPORTED','OFFICE_MARKER_INTERVENTION_UNSUPPORTED'}
    result={'name':name,'kind':kind,'passed':bool(ok and before==after),'scores':scores,'error':error,'workspace_unchanged':before==after,'correct_baseline_before_unsupported':baseline_valid,'path':str(case),'independent_semantic_score':None,'expected_Judge_zero_not_executed':kind=='semantic'};results.append(result);dump(case/'validation.json',result);print(json.dumps(result),flush=True)
report={'status':'PASS' if all(r['passed'] for r in results) else 'FAIL','results':results};dump(out/'validation.json',report);assert report['status']=='PASS',out
