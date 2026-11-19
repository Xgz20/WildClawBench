"""Disposable native OOXML test fixtures, including intentionally corrupt caches/packages.
The three logical spreadsheets remain artifact-tool authored and byte-frozen.
"""
from pathlib import Path
from collections import defaultdict
import argparse,copy,csv,hashlib,io,json,os,re,runpy,shutil,time,zipfile
from lxml import etree as E
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
POSITIVES=['reference','renamed_sheets','reversed_rows','reversed_columns','shifted_table','chinese_headers','numeric_text','correct_formulas_wrong_cache','merged_reasons','audit_bom_reorder','extra_notes']
NEGATIVES=['wrong_money_unit','minutes_as_hours','budget_instead_actual','project_fallback','nearest_month','leading_zero_collision','name_join','first_duplicate','dedup_equal_values','sum_multiple','drop_target','duplicate_target','extra_target','original_field_changed','blank_as_zero','zero_as_blank','negative_as_positive','wrong_status','drop_unused_source','drop_unmatched_target','drop_audit_link','wrong_source_row','wrong_target_row','wrong_basis','wrong_audit_amount','duplicate_audit','hidden_sheet','hidden_row','hidden_column','hidden_format','missing_workbook','bad_zip','missing_csv','invalid_csv','input_changed']
NEGATIVES+=['positional_copy','wrong_formula_correct_cache','formula_divide_by_zero']
SEMANTIC=[];INFRA=['missing_GT','missing_helper','helper_drift','missing_runtime','runtime_drift']
CASES=POSITIVES+NEGATIVES+SEMANTIC+INFRA
import sys
parser=argparse.ArgumentParser(description="H017 frozen-source author controls on disposable native packages")
parser.add_argument('--case',action='append');parser.add_argument('--office-lock',type=Path);parser.add_argument('--output-dir',type=Path);parser.add_argument('--dataset-workspace',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--list-cases',action='store_true')
args=parser.parse_args()
if args.list_cases:
    print(json.dumps({'count':len(CASES),'positive':POSITIVES,'negative':NEGATIVES,'infrastructure':INFRA}));sys.exit(0)
if not args.office_lock or not args.output_dir:parser.error('Office lock and external new output directory required')
if args.case and not set(args.case)<=set(CASES):parser.error('unknown case')
ROOT=args.dataset_workspace.resolve();qa=args.output_dir.resolve()
if qa==ROOT or ROOT in qa.parents:parser.error('output directory must be outside dataset Workspace')
qa.mkdir(parents=True,exist_ok=False);frozen=qa/'source';shutil.copytree(ROOT/'gt',frozen/'gt',ignore=shutil.ignore_patterns('reference','__pycache__'));shutil.copytree(ROOT/'exec',frozen/'exec');shutil.copytree(ROOT/'gt/reference/results',frozen/'reference')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(qa/'source-binding.json').write_text(json.dumps({p.relative_to(frozen).as_posix():sha(p) for p in frozen.rglob('*') if p.is_file()},indent=2)+'\n');shutil.copyfile(__file__,qa/'control-script.py')
expected=json.loads((frozen/'gt/expected.json').read_text());contract=json.loads((frozen/'gt/runtime_contract.json').read_text());targets={t['target_id']:t for t in expected['targets']};sources={s['source_id']:s for s in expected['sources']};edges=defaultdict(list)
for edge in expected['edges']:edges[edge['target_id']].append(sources[edge['source_id']])
base_lock=args.office_lock.resolve()

def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def cell(root,col,row):
    addr=col+str(row)
    found=root.find('.//'+X+'c[@r="'+addr+'"]')
    if found is not None:return found
    data=root.find(X+'sheetData');r=data.find(X+'row[@r="'+str(row)+'"]')
    if r is None:r=E.SubElement(data,X+'row',r=str(row))
    return E.SubElement(r,X+'c',r=addr)
def put(root,col,row,value,formula=None,cache=None):
    c=cell(root,col,row)
    for child in list(c):c.remove(child)
    c.attrib.pop('t',None)
    if formula is not None:
        E.SubElement(c,X+'f').text=formula;E.SubElement(c,X+'v').text=str(value if cache is None else cache)
    elif isinstance(value,str):
        c.set('t','inlineStr');t=E.SubElement(E.SubElement(c,X+'is'),X+'t');t.text=value;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    elif value is not None:E.SubElement(c,X+'v').text=str(value)
    return c
FIELDS={'status':'F','match_count':'G','amount_cny':'H','hours':'I','count':'J'}
def set_target(doc,tid,**fields):
    row=5+int(tid[1:])
    for key,value in fields.items():put(doc,FIELDS.get(key,key),row,value)
def rewrite(path,name,audit):
    with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
    main=E.fromstring(parts['xl/worksheets/sheet1.xml']);un=E.fromstring(parts['xl/worksheets/sheet2.xml']);book=E.fromstring(parts['xl/workbook.xml']);styles=E.fromstring(parts['xl/styles.xml'])
    if name=='renamed_sheets':
        for i,s in enumerate(book.find(X+'sheets')):s.set('name',['业务明细','待核对记录'][i])
        for r in audit:
            if r['target_id']:r['target_sheet']='业务明细'
    elif name=='reversed_rows':
        data=main.find(X+'sheetData');old=[n for n in data if int(n.get('r'))>=6];mapping={}
        for n in old:data.remove(n)
        for new,n in enumerate(reversed(old),6):
            prior=int(n.get('r'));mapping[prior]=new;n.set('r',str(new))
            for c in n:c.set('r',re.sub(r'\d+$',str(new),c.get('r')))
            data.append(n)
        for r in audit:
            if r['target_id']:r['target_row']=str(mapping[int(r['target_row'])])
    elif name=='reversed_columns':
        for row in main.find(X+'sheetData'):
            if int(row.get('r'))<5:continue
            for c in row:
                m=re.fullmatch(r'([A-J])(\d+)',c.get('r'));c.set('r',chr(75-(ord(m[1])-65)-1)+m[2])
            row[:]=sorted(row,key=lambda c:c.get('r'))
    elif name=='shifted_table':
        for row in main.find(X+'sheetData'):
            rn=int(row.get('r'));row.set('r',str(rn+3))
            for c in row:
                m=re.fullmatch(r'([A-J])(\d+)',c.get('r'));c.set('r',chr(ord(m[1])+2)+str(rn+3))
        for r in audit:
            if r['target_id']:r['target_row']=str(int(r['target_row'])+3)
    elif name=='chinese_headers':
        titles=['目标ID','项目编号','合同编号','服务月份','项目名称','状态','匹配条数','发生金额(元)','工时(小时)','记录数']
        for i,title in enumerate(titles):put(main,chr(65+i),5,title)
        for i,title in enumerate(['对象类型','记录ID','原因']):put(un,chr(65+i),5,title)
    elif name in {'numeric_text','correct_formulas_wrong_cache'}:
        for t in expected['targets']:
            rn=5+int(t['target_id'][1:])
            for field in ['match_count','amount_cny','hours','count']:
                value=t[field]
                if value is None:continue
                if name=='numeric_text':put(main,FIELDS[field],rn,str(value))
                else:put(main,FIELDS[field],rn,value,formula=str(value)+'+0',cache=999)
    elif name=='merged_reasons':
        merges=E.SubElement(un,X+'mergeCells',count='2')
        for a,b in [(6,11),(18,23)]:
            E.SubElement(merges,X+'mergeCell',ref='C'+str(a)+':C'+str(b))
            for row in range(a+1,b+1):put(un,'C',row,None)
    elif name=='extra_notes':put(main,'A',130,'备注：输出保留未匹配记录。')
    elif name=='positional_copy':
        tid=next(tid for tid,ss in edges.items() if targets[tid]['status']=='matched' and ss[0]['source_sheet']=='南区导出');s=edges[tid][0]
        native=runpy.run_path(str(frozen/'gt/xlsx_observations.py'))['read_book'](frozen/'exec/sources.xlsx');grid=next(sheet for sheet in native if sheet['name']==s['source_sheet'])['cells'];rn=s['source_row']
        set_target(main,tid,amount_cny=grid[rn,6]['value'],hours=grid[rn,7]['value'],count=grid[rn,8]['value'])
    elif name in {'wrong_formula_correct_cache','formula_divide_by_zero'}:put(main,'H',6,targets['T0001']['amount_cny'],formula='1+0' if name=='wrong_formula_correct_cache' else '1/0',cache=targets['T0001']['amount_cny'])
    elif name in {'wrong_money_unit','minutes_as_hours','budget_instead_actual'}:
        tid='T0001';field='hours' if name=='minutes_as_hours' else 'amount_cny';value=targets[tid][field]*(60 if field=='hours' else 1000)
        if name=='budget_instead_actual':value=9017
        set_target(main,tid,**{field:value})
        for r in audit:
            if r['target_id']==tid:r[field]=str(value)
    elif name in {'project_fallback','nearest_month','leading_zero_collision','name_join'}:
        tid={'project_fallback':'T0098','nearest_month':'T0109','leading_zero_collision':'T0097','name_join':'T0103'}[name];t=targets[tid]
        if name=='project_fallback':s=next(s for s in expected['sources'] if s['contract_id']==t['contract_id'] and s['month']==t['month'])
        elif name=='nearest_month':s=next(s for s in expected['sources'] if s['project_id']==t['project_id'])
        elif name=='leading_zero_collision':s=edges['T0001'][0]
        else:s=next(s for s in expected['sources'] if s['name']==t['original']['name'] and s['project_id'])
        set_target(main,tid,status='matched',match_count=1,**{k:s[k] for k in ['amount_cny','hours','count']})
        for r in audit:
            if r['target_id']==tid:r.update(source_id=s['source_id'],source_sheet=s['source_sheet'],source_row=str(s['source_row']),match_basis='project_month',status='matched',**{k:'' if s[k] is None else str(s[k]) for k in ['amount_cny','hours','count']})
    elif name in {'first_duplicate','dedup_equal_values','sum_multiple'}:
        tid={'first_duplicate':'T0071','dedup_equal_values':'T0080','sum_multiple':'T0072'}[name];s=edges[tid][0]
        if name=='sum_multiple':set_target(main,tid,**{k:sum(v[k] or 0 for v in edges[tid]) for k in ['amount_cny','hours','count']})
        else:
            set_target(main,tid,status='matched',match_count=1,**{k:s[k] for k in ['amount_cny','hours','count']});audit[:]=[r for r in audit if r['target_id']!=tid or r['source_id']==s['source_id']]
    elif name in {'drop_target','duplicate_target','extra_target'}:
        data=main.find(X+'sheetData');r=data.find(X+'row[@r="15"]')
        if name=='drop_target':data.remove(r)
        else:
            clone=copy.deepcopy(r);clone.set('r','126')
            for c in clone:c.set('r',re.sub(r'\d+$','126',c.get('r')))
            data.append(clone)
            if name=='extra_target':put(main,'A',126,'T9999')
    elif name=='original_field_changed':put(main,'B',6,1)
    elif name=='blank_as_zero':
        for tid,field in [('T0117','hours'),('T0118','amount_cny'),('T0119','count')]:set_target(main,tid,**{field:0})
    elif name=='zero_as_blank':set_target(main,'T0116',amount_cny=None,hours=None,count=None)
    elif name=='negative_as_positive':set_target(main,'T0115',amount_cny=200)
    elif name=='wrong_status':set_target(main,'T0098',status='matched')
    elif name in {'drop_unused_source','drop_unmatched_target'}:
        data=un.find(X+'sheetData');rows=[n for n in data if int(n.get('r'))>=6];chosen=[24] if name=='drop_unused_source' else list(range(12,18))
        for row in rows:
            if int(row.get('r')) in chosen:data.remove(row)
    elif name=='hidden_sheet':book.find(X+'sheets')[0].set('state','hidden')
    elif name=='hidden_row':main.find(X+'sheetData/'+X+'row[@r="15"]').set('hidden','1')
    elif name=='hidden_column':
        cols=main.find(X+'cols')
        if cols is None:cols=E.SubElement(main,X+'cols')
        E.SubElement(cols,X+'col',min='8',max='8',hidden='1',width='20',customWidth='1')
    elif name=='hidden_format':
        nf=styles.find(X+'numFmts')
        if nf is None:nf=E.SubElement(styles,X+'numFmts')
        E.SubElement(nf,X+'numFmt',numFmtId='777',formatCode=';;;');nf.set('count',str(len(nf)));xfs=styles.find(X+'cellXfs');n=len(xfs);xf=copy.deepcopy(xfs[0]);xf.set('numFmtId','777');xf.set('applyNumberFormat','1');xfs.append(xf);xfs.set('count',str(len(xfs)))
        cell(main,'H',6).set('s',str(n))
    parts['xl/worksheets/sheet1.xml']=E.tostring(main,xml_declaration=True,encoding='UTF-8',standalone=True);parts['xl/worksheets/sheet2.xml']=E.tostring(un,xml_declaration=True,encoding='UTF-8',standalone=True);parts['xl/workbook.xml']=E.tostring(book,xml_declaration=True,encoding='UTF-8',standalone=True);parts['xl/styles.xml']=E.tostring(styles,xml_declaration=True,encoding='UTF-8',standalone=True)
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for n,b in parts.items():z.writestr(n,b)
results=[]
for name in CASES:
    if args.case and name not in args.case:continue
    target=qa/name;w=target/'workspace';shutil.copytree(frozen/'exec',w);shutil.copytree(frozen/'gt',w/'gt');shutil.copytree(frozen/'reference',w/'results')
    os.environ['GENERAL_E2E_OFFICE_LOCK']=str(base_lock);os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(target/'derived')
    with (w/'results/join_audit.csv').open(encoding='utf-8',newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    if name not in INFRA:
        rewrite(w/'results/aligned.xlsx',name,rows)
        if name=='drop_audit_link':rows=rows[1:]
        if name=='wrong_source_row':
            for r in rows:
                if r['source_id']:r['source_row']=str(int(r['source_row'])+1)
        if name=='wrong_target_row':
            for r in rows:
                if r['target_id']:r['target_row']=str(int(r['target_row'])+1)
        if name=='wrong_basis':
            for r in rows:
                if r['match_basis']=='project_month':r['match_basis']='contract_month'
        if name=='wrong_audit_amount':rows[0]['amount_cny']='123456'
        if name=='duplicate_audit':rows.append(dict(rows[0]))
        if name=='audit_bom_reorder':rows.reverse();fields=list(reversed(fields))
        with (w/'results/join_audit.csv').open('w',encoding='utf-8-sig' if name=='audit_bom_reorder' else 'utf-8',newline='') as f:writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        if name=='missing_workbook':(w/'results/aligned.xlsx').unlink()
        if name=='bad_zip':(w/'results/aligned.xlsx').write_text('bad ZIP')
        if name=='missing_csv':(w/'results/join_audit.csv').unlink()
        if name=='invalid_csv':(w/'results/join_audit.csv').write_text('wrong,header\nx,y\n')
        if name=='input_changed':(w/'mapping_rules.md').write_text('changed')
    else:
        if name=='missing_GT':(w/'gt/expected.json').unlink()
        if name=='missing_helper':(w/'gt/xlsx_observations.py').unlink()
        if name=='helper_drift':
            with (w/'gt/xlsx_observations.py').open('a') as f:f.write('\n# deliberate drift\n')
        if name=='missing_runtime':os.environ.pop('GENERAL_E2E_OFFICE_LOCK')
        if name=='runtime_drift':
            lock=json.loads(base_lock.read_text());lock['executable_sha256']='0'*64;lp=target/'bad-runtime.json';dump(lp,lock);os.environ['GENERAL_E2E_OFFICE_LOCK']=str(lp)
    before={p.relative_to(w).as_posix():sha(p) for p in w.rglob('*') if p.is_file()}
    try:scores=runpy.run_path(str(w/'gt/grader.py'))['grade'](w)
    except (FileNotFoundError,ValueError,RuntimeError) as error:
        if name not in INFRA:raise
        output={'kind':'evaluation_error','score':None,'exception':type(error).__name__,'code':getattr(error,'code',None),'message':str(error)};ok=True
    else:
        if name in INFRA:raise AssertionError('infrastructure incorrectly returned scores '+name)
        output={'kind':'scores','scores':scores};ok=scores['overall_score']<1. if name in NEGATIVES else scores['overall_score']==1.
    after={p.relative_to(w).as_posix():sha(p) for p in w.rglob('*') if p.is_file() and '__pycache__' not in p.parts};assert before==after,name
    row={'name':name,'status':'PASS' if ok else 'FAIL','kind':'positive' if name in POSITIVES else 'negative' if name in NEGATIVES else 'semantic' if name in SEMANTIC else 'infrastructure','result':output,'workspace_unchanged':True};results.append(row);dump(target/'validation.json',row);print(json.dumps(row),flush=True)
dump(qa/'validation.json',{'status':'PASS' if all(r['status']=='PASS' for r in results) else 'FAIL','results':results,'source_binding_sha256':sha(qa/'source-binding.json')});assert all(r['status']=='PASS' for r in results),str(qa)
