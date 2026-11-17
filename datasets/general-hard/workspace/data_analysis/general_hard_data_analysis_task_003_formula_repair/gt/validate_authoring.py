"""Native QA mutations only; the two logical workbooks are artifact-tool authored."""
from pathlib import Path
import argparse,copy,hashlib,json,os,runpy,shutil,time,zipfile
import xml.etree.ElementTree as E
P=argparse.ArgumentParser(description="H019 disposable author controls; not model/Harness evaluation")
P.add_argument('--cases',nargs='*');P.add_argument('--case',action='append');P.add_argument('--kind',choices=['positive','negative','infrastructure']);P.add_argument('--list','--list-cases',action='store_true')
P.add_argument('--office-lock',type=Path);P.add_argument('--output-dir',type=Path);P.add_argument('--dataset-workspace',type=Path,default=Path(__file__).resolve().parents[1])
args=P.parse_args();R=args.dataset_workspace.resolve();args.cases=args.cases or args.case
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();io=runpy.run_path(str(R/'gt/leave_io.py'));oracle=json.loads((R/'gt/expected.json').read_text());source=io['snapshot'](R/'exec/leave_model.xlsx')
def mutate(w,part,fun):
 p=w/'results/leave_model_repaired.xlsx'
 with zipfile.ZipFile(p) as z:items=[(i,z.read(i.filename)) for i in z.infolist()]
 doc=E.fromstring(next(b for i,b in items if i.filename==part));fun(doc)
 with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
  for i,b in items:z.writestr(i,E.tostring(doc,encoding='utf-8',xml_declaration=True) if i.filename==part else b)
def sheet(w,n,fun):mutate(w,'xl/worksheets/sheet'+str(n)+'.xml',fun)
def cell(d,addr):return next(c for c in d.iter(X+'c') if c.get('r')==addr)
def setf(d,addr,text):
 c=cell(d,addr);c.attrib.pop('t',None)
 for n in list(c):
  if n.tag in {X+'f',X+'v',X+'is'}:c.remove(n)
 E.SubElement(c,X+'f').text=text.lstrip('=')
def setv(d,addr,value):
 c=cell(d,addr);c.attrib.pop('t',None)
 for n in list(c):
  if n.tag in {X+'f',X+'v',X+'is'}:c.remove(n)
 if value is None:return
 if isinstance(value,str):c.set('t','inlineStr');E.SubElement(E.SubElement(c,X+'is'),X+'t').text=value
 else:E.SubElement(c,X+'v').text=str(value)
def replace(w,col,fn):
 def edit(d):
  for r in range(6,18):setf(d,col+str(r),fn(r,cell(d,col+str(r)).find(X+'f').text))
 sheet(w,1,edit)
def rebind(w):
 p=w/'results/formula_changes.md';text=p.read_text();cur=io['snapshot'](w/'results/leave_model_repaired.xlsx');new={s['name']:s for s in cur['sheets']}
 lines=[]
 for line in text.splitlines():
  f=[x.strip().strip('`') for x in line.strip().strip('|').split('|')]
  if len(f)==4 and f[0] in {'AsOfDate','Leave!E6','Leave!F6','Leave!G6','Leave!H6'}:
   f[2]=cur['names']['AsOfDate'] if f[0]=='AsOfDate' else '='+new['Leave']['cells'][f[0].split('!')[1]]['formula'];line='| '+' | '.join(f)+' |'
  lines.append(line)
 p.write_text('\n'.join(lines)+'\n')
def caches(w,remove=False):
 def edit(d):
  for c in d.iter(X+'c'):
   if c.find(X+'f') is not None:
    for v in list(c.findall(X+'v')):c.remove(v)
    if not remove:E.SubElement(c,X+'v').text='999'
 for n in [1,2,3]:sheet(w,n,edit)
def baseline_static(w,asformula=False):
 def edit(d):
  for row in oracle['scenarios'][0]['expected']:
   for col,key in zip('EFGH',['complete_years','base_days','entitled_days','status']):
    value=row[key]
    if asformula:setf(d,col+str(row['row']),'""' if value is None else '"'+value+'"' if isinstance(value,str) else str(value))
    else:setv(d,col+str(row['row']),value)
 sheet(w,1,edit)
 if asformula:rebind(w)
def helper(w):
 def edit(d):
  c=cell(d,'E6');f=c.find(X+'f').text;row=d.find(X+'sheetData/'+X+'row[@r="6"]');h=cell(d,'J6');setf(d,'J6',f);setf(d,'E6','J6')
 sheet(w,1,edit);rebind(w)
def name(w,text):mutate(w,'xl/workbook.xml',lambda d:setattr(next(n for n in d.iter(X+'definedName') if n.get('name')=='AsOfDate'),'text',text))
def report_edit(w,a,b):
 p=w/'results/formula_changes.md';s=p.read_text();assert a in s,a;p.write_text(s.replace(a,b,1))
def missing(w,n):(w/n).unlink()
def source_invalid(w):
 (w/'policy.md').write_text((w/'policy.md').read_text()+'\nchanged\n')
def wrong_formula_cache(w,formula):
 sheet(w,1,lambda d:setattr(cell(d,'E6').find(X+'f'),'text',formula));rebind(w)
def drift_lock(w):
 p=w.parent/'bad-office-lock.json';d=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());d['executable_sha256']='0'*64;p.write_text(json.dumps(d));os.environ['GENERAL_E2E_OFFICE_LOCK']=str(p)
def style_defaults(w):
 def edit(d):
  for a in d.iter(X+'alignment'):a.attrib.update({'horizontal':'general','wrapText':'false','shrinkToFit':'0','indent':'0','textRotation':'0'}) if a.get('horizontal','general')=='general' else a.attrib.update({'wrapText':'false','shrinkToFit':'0','indent':'0','textRotation':'0'})
  for b in d.iter(X+'border'):b.attrib.update({'diagonalUp':'false','diagonalDown':'0'})
  for xf in d.findall(X+'cellXfs/'+X+'xf'):
   p=xf.find(X+'protection')
   if p is None:E.SubElement(xf,X+'protection',locked='true',hidden='false')
  for f in d.iter(X+'font'):
   E.SubElement(f,X+'family',val='2');E.SubElement(f,X+'i',val='false')
 mutate(w,'xl/styles.xml',edit)
def openpyxl_roundtrip(w):
 import openpyxl
 p=w/'results/leave_model_repaired.xlsx';wb=openpyxl.load_workbook(p);wb.save(p)
def formulaedit(w,col,fn):replace(w,col,fn);rebind(w)
cases={
 'reference':('positive',lambda w:None),
 'bad_caches':('positive',lambda w:caches(w)),
 'no_caches':('positive',lambda w:caches(w,True)),
 'helper_formula':('positive',helper),
 'floor_equivalent':('positive',lambda w:formulaedit(w,'G',lambda r,f:f.replace(f'INT(F{r}*D{r}/HalfUnit)*HalfUnit',f'FLOOR(F{r}*D{r},HalfUnit)'))),
 'year_comparison_equivalent':('positive',lambda w:formulaedit(w,'E',lambda r,f:f.replace(f'IF(AsOfDate<DATE(YEAR(AsOfDate),MONTH(C{r}),DAY(C{r})),1,0)',f'IF(DATE(YEAR(AsOfDate),MONTH(C{r}),DAY(C{r}))>AsOfDate,1,0)'))),
 'name_unquoted':('positive',lambda w:(name(w,'Control!$B$3'),rebind(w))),
 'openpyxl_roundtrip':('positive',openpyxl_roundtrip),
 'explicit_style_defaults':('positive',style_defaults),
 'unchanged_old_model':('negative',lambda w:shutil.copyfile(R/'exec/leave_model.xlsx',w/'results/leave_model_repaired.xlsx')),
 'literal_baseline':('negative',lambda w:baseline_static(w)),
 'constant_formula_baseline':('negative',lambda w:baseline_static(w,True)),
 'fixed_date_formula':('negative',lambda w:formulaedit(w,'E',lambda r,f:f.replace('AsOfDate','DATE(2026,2,28)'))),
 'wrong_asof_name':('negative',lambda w:(name(w,"'Control'!$B$4"),rebind(w))),
 'year_subtraction':('negative',lambda w:formulaedit(w,'E',lambda r,f:f.replace(f'-IF(AsOfDate<DATE(YEAR(AsOfDate),MONTH(C{r}),DAY(C{r})),1,0)',''))),
 'days_36525':('negative',lambda w:formulaedit(w,'E',lambda r,f:f'IF(H{r}="待核验","",IF(H{r}="未入职",0,INT((AsOfDate-C{r})/365.25)))')),
 'leap_on_feb28':('negative',lambda w:formulaedit(w,'E',lambda r,f:f.replace(f'DATE(YEAR(AsOfDate),MONTH(C{r}),DAY(C{r}))',f'DATE(YEAR(AsOfDate),MONTH(C{r}),MIN(DAY(C{r}),DAY(DATE(YEAR(AsOfDate),MONTH(C{r})+1,0))))'))),
 'inclusive_bands':('negative',lambda w:formulaedit(w,'F',lambda r,f:f.replace('<Threshold','<=Threshold'))),
 'round_nearest_half':('negative',lambda w:formulaedit(w,'G',lambda r,f:f.replace(f'INT(F{r}*D{r}/HalfUnit)',f'ROUND(F{r}*D{r}/HalfUnit,0)'))),
 'zero_fte_fallback':('negative',lambda w:formulaedit(w,'G',lambda r,f:f.replace(f'*D{r}/',f'*IF(D{r}=0,1,D{r})/'))),
 'missing_date_zero':('negative',lambda w:formulaedit(w,'E',lambda r,f:f.replace('"待核验",""','"待核验",0'))),
 'future_as_normal':('negative',lambda w:formulaedit(w,'H',lambda r,f:f.replace('"未入职"','"正常"'))),
 'hardcoded_bands':('negative',lambda w:formulaedit(w,'F',lambda r,f:f.replace('ThresholdMid','10').replace('ThresholdHigh','20').replace('DaysLow','5').replace('DaysMid','10').replace('DaysHigh','15'))),
 'fte_ignored':('negative',lambda w:formulaedit(w,'G',lambda r,f:f.replace(f'*D{r}/','/'))),
 'employee_modified':('negative',lambda w:sheet(w,3,lambda d:setv(d,'D6',.5))),
 'parameter_modified':('negative',lambda w:sheet(w,2,lambda d:setv(d,'B4',46200))),
 'non_target_formula_modified':('negative',lambda w:sheet(w,1,lambda d:setf(d,'G3','SUM(G6:G17)+0'))),
 'hidden_output':('negative',lambda w:sheet(w,1,lambda d:d.find(X+'sheetData/'+X+'row[@r="6"]').set('hidden','1'))),
 'missing_name':('negative',lambda w:mutate(w,'xl/workbook.xml',lambda d:d.find(X+'definedNames').remove(next(n for n in d.iter(X+'definedName') if n.get('name')=='HalfUnit')))),
 'missing_book':('negative',lambda w:missing(w,'results/leave_model_repaired.xlsx')),
 'missing_report':('negative',lambda w:missing(w,'results/formula_changes.md')),
 'invalid_book':('negative',lambda w:(w/'results/leave_model_repaired.xlsx').write_bytes(b'not a workbook')),
 'wrong_before_binding':('negative',lambda w:report_edit(w,'AsOfDate | `\'Control\'!$B$4`','AsOfDate | `Control!$B$3`')),
 'wrong_after_binding':('negative',lambda w:report_edit(w,' | R-years |',' | R-date |')),
 'report_wrong_value':('negative',lambda w:report_edit(w,'E002 | 2026-02-28 | 1 | 5 | 3.5','E002 | 2026-02-28 | 1 | 5 | 4.0')),
 'report_duplicate_row':('negative',lambda w:report_edit(w,'| E001 | 2026-02-28 | 0 | 0 | 0.0 | 正常 |','| E001 | 2026-02-28 | 0 | 0 | 0.0 | 正常 |\n| E001 | 2026-02-28 | 0 | 0 | 0.0 | 正常 |')),
 'report_wrong_date':('negative',lambda w:report_edit(w,'E001 | 2028-02-29','E001 | 2028-02-28')),
 'input_modified':('negative',source_invalid),
 'wrong_formula_good_cache':('negative',lambda w:wrong_formula_cache(w,'999')),
 'formula_error_good_cache':('negative',lambda w:wrong_formula_cache(w,'1/0')),
 'missing_gt':('infrastructure',lambda w:missing(w,'gt/expected.json')),
 'helper_drift':('infrastructure',lambda w:(w/'gt/leave_io.py').write_text((w/'gt/leave_io.py').read_text()+'\n#drift\n')),
 'missing_office_lock':('infrastructure',lambda w:os.environ.pop('GENERAL_E2E_OFFICE_LOCK')),
 'office_lock_drift':('infrastructure',drift_lock),
}
if args.list:print('\n'.join(cases));raise SystemExit
if not args.office_lock or not args.output_dir:P.error('explicit --office-lock and new external --output-dir required')
names=args.cases or [n for n,(kind,_) in cases.items() if args.kind is None or kind==args.kind]
if not set(names)<=set(cases):P.error('unknown case')
out=args.output_dir.resolve()
if out==R or R in out.parents:P.error('output directory must be outside dataset Workspace')
out.mkdir(parents=True,exist_ok=False);validation=[];origin=R;frozen=out/'source'
shutil.copytree(R/'exec',frozen/'exec');shutil.copytree(R/'gt',frozen/'gt',ignore=shutil.ignore_patterns('__pycache__'))
(out/'source-binding.json').write_text(json.dumps({p.relative_to(frozen).as_posix():sha(p) for p in frozen.rglob('*') if p.is_file()},indent=2)+'\n');shutil.copyfile(__file__,out/'control-script.py');R=frozen
os.environ['GENERAL_E2E_OFFICE_LOCK']=str(args.office_lock.resolve())
for n in names:
 kind,action=cases[n];case=out/n;w=case/'workspace';shutil.copytree(R/'exec',w);shutil.copytree(R/'gt',w/'gt',ignore=shutil.ignore_patterns('reference','__pycache__'));shutil.copytree(R/'gt/reference/results',w/'results');os.environ['GENERAL_E2E_OFFICE_LOCK']=str(args.office_lock.resolve());os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(case/'derived');action(w);before={p.relative_to(w).as_posix():sha(p) for p in w.rglob('*') if p.is_file()};scores=None;error=None
 try:scores=runpy.run_path(str(w/'gt/grader.py'))['grade'](w)
 except Exception as ex:error={'type':type(ex).__name__,'message':str(ex)}
 after={p.relative_to(w).as_posix():sha(p) for p in w.rglob('*') if p.is_file() and '__pycache__' not in p.parts};ok=(scores is not None and scores['overall_score']==1.) if kind=='positive' else (scores is not None and scores['overall_score']<1.) if kind=='negative' else error is not None and scores is None
 row={'name':n,'kind':kind,'passed':ok and before==after,'scores':scores,'error':error,'workspace_unchanged':before==after,'root':str(case)};validation.append(row);(case/'validation.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');print(json.dumps(row,ensure_ascii=False),flush=True)
report={'status':'PASS' if all(v['passed'] for v in validation) else 'FAIL','cases':validation};(out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');assert report['status']=='PASS',out
