"""Isolated native OOXML/CSV corruption and equivalence fixtures; source assets never edited."""
from pathlib import Path
from collections import defaultdict
import argparse,copy,csv,hashlib,json,os,re,runpy,shutil,time,zipfile
from lxml import etree as E
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
POSITIVES=['reference','renamed_sheets','reordered_rows_columns','shifted_tables','chinese_headers','long_markers','combined_raw_model','transposed_weights','source_weight_snapshot_first','formula_markers_bad_caches','zero_formula_dependencies','equivalent_formulas','word_rows_runs','word_merged_denominator','audit_bom_reordered']
NEGATIVES=['physical_last_row','invalid_latest_replaces','wrong_tie_id','ignore_routing','drop_person_on_question_missing','missing_as_zero','multi_duplicate_count','none_with_other','denominator_total','denominator_cross_question','weighted_is_raw','stratum_not_normalized','rate_times_weight','static_summary','constant_formulas','wrong_formula_correct_cache','divide_by_zero','zero_weight_rate_zero','false_exclusion_row','missing_quote','word_wrong_percentage','raw_timestamp_changed','drop_raw_row','extra_model_record','duplicate_exclusion','missing_question_exclusion','missing_record_exclusion','false_related_record','hidden_summary','hidden_model','hidden_word','missing_book','bad_book','missing_word','bad_word','missing_csv','bad_csv','input_changed']
NEGATIVES+=['quote_unit_removed','quote_polarity_changed']
INFRA=['missing_GT','missing_helper','helper_drift','missing_office','missing_fonts','office_drift','shared_marker_capability','text_weight_intervention_capability','merged_marker_capability'];CASES=POSITIVES+NEGATIVES+INFRA
import sys
parser=argparse.ArgumentParser(description="H018 author case controls on independent native copies")
parser.add_argument('--case',action='append');parser.add_argument('--office-lock',type=Path);parser.add_argument('--render-lock',type=Path);parser.add_argument('--output-dir',type=Path);parser.add_argument('--dataset-workspace',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--list-cases',action='store_true')
args=parser.parse_args()
if args.list_cases:
 print(json.dumps({'positive':POSITIVES,'negative':NEGATIVES,'infrastructure':INFRA,'count':len(CASES)}));sys.exit(0)
if not args.office_lock or not args.render_lock or not args.output_dir:parser.error('Office/render locks and a new external output directory required')
if args.case and not set(args.case)<=set(CASES):parser.error('unknown control')
ROOT=args.dataset_workspace.resolve();qa=args.output_dir.resolve()
if qa==ROOT or ROOT in qa.parents:parser.error('output directory must be outside dataset Workspace')
qa.mkdir(parents=True,exist_ok=False);frozen=qa/'source';shutil.copytree(ROOT/'gt',frozen/'gt',ignore=shutil.ignore_patterns('reference','__pycache__'));shutil.copytree(ROOT/'exec',frozen/'exec');shutil.copytree(ROOT/'gt/reference/results',frozen/'reference');shutil.copyfile(__file__,qa/'control-script.py');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();dump=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
dump(qa/'source-binding.json',{p.relative_to(frozen).as_posix():sha(p) for p in frozen.rglob('*') if p.is_file()});truth=json.loads((frozen/'gt/expected.json').read_text());byid={r['record_id']:r for r in truth['cleaned']};kept=sorted((r for r in truth['cleaned'] if r['keep']),key=lambda r:r['record_id']);raw_row={r['record_id']:i+6 for i,r in enumerate(truth['cleaned'])};model_row={r['record_id']:i+6 for i,r in enumerate(kept)};flag_keys=list(kept[0]['flags']);baseline=truth['baseline'];contract=json.loads((frozen/'gt/runtime_contract.json').read_text())
def col(c):
 s=''
 while c:c,r=divmod(c-1,26);s=chr(65+r)+s
 return s
def cell(doc,c,r):
 address=col(c)+str(r);found=doc.find('.//'+X+'c[@r="'+address+'"]')
 if found is not None:return found
 data=doc.find(X+'sheetData');row=data.find(X+'row[@r="'+str(r)+'"]')
 if row is None:row=E.SubElement(data,X+'row',r=str(r))
 return E.SubElement(row,X+'c',r=address)
def put(doc,c,r,value,formula=None,cache=None,style=None):
 n=cell(doc,c,r)
 for child in list(n):n.remove(child)
 n.attrib.pop('t',None)
 if style is not None:n.set('s',style)
 if formula is not None:E.SubElement(n,X+'f').text=formula;E.SubElement(n,X+'v').text=str(value if cache is None else cache)
 elif isinstance(value,str):
  n.set('t','inlineStr');t=E.SubElement(E.SubElement(n,X+'is'),X+'t');t.text=value;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
 elif value is not None:E.SubElement(n,X+'v').text=str(int(value)) if isinstance(value,bool) else str(value)
 return n
fields=['raw_num','raw_den','raw_rate','weighted_num','weighted_den','weighted_rate']
def set_metric(doc,mid,field,value,formula=None,cache=None):return put(doc,4+fields.index(field),6+next(i for i,m in enumerate(truth['metrics']) if m['metric_id']==mid),value,formula,cache)
def rewrite_book(path,name):
 with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
 docs={n:E.fromstring(parts[n]) for n in ['xl/workbook.xml','xl/_rels/workbook.xml.rels','xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml','xl/worksheets/sheet3.xml','xl/worksheets/sheet4.xml']};s,m,raw,weights=[docs['xl/worksheets/sheet'+str(i)+'.xml'] for i in range(1,5)]
 if name=='renamed_sheets':
  mapping={'汇总':'结果','题级底稿':'标记模型','清洗记录':'提交审计','权重':'参数'}
  for sheet in docs['xl/workbook.xml'].find(X+'sheets'):sheet.set('name',mapping[sheet.get('name')])
  for doc in [s,m,raw,weights]:
   for n in doc.iter(X+'f'):
    for old,new in mapping.items():n.text=(n.text or '').replace(old,new)
 elif name=='reordered_rows_columns':
  # Reverse only the summary view; driver/model coordinates remain meaningful.
  data=s.find(X+'sheetData');rows=[r for r in data if int(r.get('r'))>=6]
  for r in rows:data.remove(r)
  for rn,row in enumerate(reversed(rows),6):
   row.set('r',str(rn))
   for c in row:
    match=re.fullmatch(r'([A-I])(\d+)',c.get('r'));c.set('r',col(10-(ord(match[1])-64))+str(rn))
   data.append(row)
  # Static formula references moved by reconstruction from business metric IDs.
  for rn,metric in enumerate(reversed(truth['metrics']),6):
   vals=[metric['metric_id'],metric['question_id'],metric['label'],*[baseline[metric['metric_id']][k] for k in fields]]
   for c,value in enumerate(reversed(vals),1):put(s,c,rn,value,formula=str(value)+'+0' if isinstance(value,(int,float)) else None)
  # All numeric summary cells must still react. Copy original formulas, then translate local references.
  old=E.fromstring(parts['xl/worksheets/sheet1.xml'])
  for rn,i in enumerate(reversed(range(6,14)),6):
   for oldc in range(4,10):
    formula=cell(old,oldc,i).find(X+'f').text
    formula=re.sub(r'\b([D-I])'+str(i)+r'\b',lambda x:col(10-(ord(x[1])-64))+str(rn),formula)
    put(s,10-oldc,rn,0,formula=formula)
  for c,title in enumerate(reversed(['metric_id','question_id','指标',*fields]),1):put(s,c,5,title)
 elif name=='shifted_tables':
  for row in s.find(X+'sheetData'):
   oldr=int(row.get('r'));row.set('r',str(oldr+3))
   for c in row:
    mt=re.fullmatch(r'([A-I])(\d+)',c.get('r'));c.set('r',chr(ord(mt[1])+2)+str(oldr+3))
    f=c.find(X+'f')
    if f is not None:f.text=re.sub(r'\b([D-I])(\d+)\b',lambda q:chr(ord(q[1])+2)+str(int(q[2])+3),f.text)
 elif name=='chinese_headers':
  roles=[(s,contract['summary_aliases']),(m,contract['model_aliases']),(raw,contract['raw_aliases']),(weights,contract['weight_aliases'])]
  known=[['metric_id','question_id','label',*fields],['record_id','respondent_id','stratum','weight',*flag_keys],truth['source_headers']+['keep','reason','related_record_id'],['stratum','weight']]
  for (doc,aliases),keys in zip(roles,known):
   for c,key in enumerate(keys,1):put(doc,c,5,aliases[key][-1])
 elif name in {'long_markers','combined_raw_model'}:
  data=m.find(X+'sheetData')
  if name=='long_markers':
   for n in list(data):data.remove(n)
   headers=['record_id','respondent_id','stratum','weight','marker_key','marker_value']
   for c,label in enumerate(headers,1):put(m,c,5,label)
   rn=6
   for record in kept:
    for field in flag_keys:
     vals=[record['record_id'],record['respondent_norm'],record['stratum_norm'],None,field,record['flags'][field]]
     for c,value in enumerate(vals,1):put(m,c,rn,value)
     put(m,4,rn,0,formula="INDEX('权重'!$B$6:$B$9,MATCH(C"+str(rn)+",'权重'!$A$6:$A$9,0))");rn+=1
   end=rn-1
   for i,metric in enumerate(truth['metrics'],6):
    nf,df=metric['numerator_flag'],metric['denominator_flag']
    fs=[f'SUMIFS(\'题级底稿\'!$F$6:$F${end},\'题级底稿\'!$E$6:$E${end},"{nf}")',f'SUMIFS(\'题级底稿\'!$F$6:$F${end},\'题级底稿\'!$E$6:$E${end},"{df}")',f'IF(E{i}=0,"n/a",D{i}/E{i})',f'SUMPRODUCT((\'题级底稿\'!$E$6:$E${end}="{nf}")*\'题级底稿\'!$D$6:$D${end}*\'题级底稿\'!$F$6:$F${end})',f'SUMPRODUCT((\'题级底稿\'!$E$6:$E${end}="{df}")*\'题级底稿\'!$D$6:$D${end}*\'题级底稿\'!$F$6:$F${end})',f'IF(H{i}=0,"n/a",G{i}/H{i})']
    for c,f in enumerate(fs,4):put(s,c,i,0,formula=f)
  else:
   for c,key in enumerate(['weight',*flag_keys],14):put(raw,c,5,'q2_sat_flag' if key=='q2_sat' else key)
   for record in truth['cleaned']:
    rn=raw_row[record['record_id']];put(raw,14,rn,0,formula=f'IF(K{rn}=1,INDEX(\'权重\'!$B$6:$B$9,MATCH(UPPER(TRIM(D{rn})),\'权重\'!$A$6:$A$9,0)),0)')
    for c,key in enumerate(flag_keys,15):put(raw,c,rn,record['flags'][key])
   flagcol={key:col(i+15) for i,key in enumerate(flag_keys)}
   for i,metric in enumerate(truth['metrics'],6):
    nf,df=flagcol[metric['numerator_flag']],flagcol[metric['denominator_flag']]
    fs=[f"SUM('清洗记录'!${nf}$6:${nf}$245)",f"SUM('清洗记录'!${df}$6:${df}$245)",f'IF(E{i}=0,"n/a",D{i}/E{i})',f"SUMPRODUCT('清洗记录'!$N$6:$N$245,'清洗记录'!${nf}$6:${nf}$245)",f"SUMPRODUCT('清洗记录'!$N$6:$N$245,'清洗记录'!${df}$6:${df}$245)",f'IF(H{i}=0,"n/a",G{i}/H{i})']
    for c,f in enumerate(fs,4):put(s,c,i,0,formula=f)
   sheets=docs['xl/workbook.xml'].find(X+'sheets')
   for node in list(sheets):
    if node.get('name')=='题级底稿':sheets.remove(node)
   rels=docs['xl/_rels/workbook.xml.rels']
   for n in list(rels):
    if n.get('Target','').endswith('sheet2.xml'):rels.remove(n)
   parts['[Content_Types].xml']=parts['[Content_Types].xml'].replace(b'<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>',b'')
   parts.pop('xl/worksheets/sheet2.xml',None);docs.pop('xl/worksheets/sheet2.xml')
  put(s,2,3,0,formula="SUM('清洗记录'!$K$6:$K$245)")
 elif name=='transposed_weights':
  data=weights.find(X+'sheetData')
  for n in list(data):data.remove(n)
  put(weights,1,5,'stratum');put(weights,1,6,'weight')
  for c,r in enumerate(truth['weights'],2):put(weights,c,5,r['stratum']);put(weights,c,6,r['weight'])
  # The corresponding native lookup is by the stratum header row.
  for rn in range(6,191):put(m,4,rn,0,formula=f"INDEX('权重'!$B$6:$E$6,1,MATCH(C{rn},'权重'!$B$5:$E$5,0))")
 elif name=='source_weight_snapshot_first':
  key='xl/worksheets/sheet5.xml';docs[key]=copy.deepcopy(weights);book=docs['xl/workbook.xml'];entry=E.Element(X+'sheet',name='原始权重快照',sheetId='5');entry.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id','rIdSnapshot');book.find(X+'sheets').insert(0,entry)
  E.SubElement(docs['xl/_rels/workbook.xml.rels'],'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',Id='rIdSnapshot',Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet',Target='worksheets/sheet5.xml');parts['[Content_Types].xml']=parts['[Content_Types].xml'].replace(b'</Types>',b'<Override PartName="/xl/worksheets/sheet5.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
 elif name=='shared_marker_capability':
  for rn in [6,7]:
   n=put(m,5,rn,999,formula='1+0' if rn==6 else None);f=n.find(X+'f')
   if f is None:f=E.Element(X+'f');n.insert(0,f)
   f.set('t','shared');f.set('si','0')
   if rn==6:f.set('ref','E6:E7')
 elif name=='text_weight_intervention_capability':
  for rn,record in enumerate(truth['weights'],6):put(weights,2,rn,str(record['weight']))
  for rn in range(6,191):put(m,4,rn,0,formula=f"VALUE(INDEX('权重'!$B$6:$B$9,MATCH(C{rn},'权重'!$A$6:$A$9,0)))")
 elif name=='merged_marker_capability':
  merges=E.SubElement(m,X+'mergeCells',count='1');E.SubElement(merges,X+'mergeCell',ref='F6:G6');put(m,7,6,None)
 elif name in {'formula_markers_bad_caches','zero_formula_dependencies'}:
  for rn,record in enumerate(kept,6):
   for c,field in enumerate(flag_keys,5):
    value=record['flags'][field];formula=f"IF('清洗记录'!K{raw_row[record['record_id']]}=1,{value},0)"
    if name=='zero_formula_dependencies' and field=='q4_yes' and value==0 and record['flags']['q1_yes']==1:formula='1-F'+str(rn)
    put(m,c,rn,value,formula=formula,cache=999)
 elif name=='equivalent_formulas':
  for node in s.iter(X+'f'):
   if node.text.startswith('SUM('):node.text='SUMPRODUCT('+node.text[4:-1]+')'
 elif name in {'physical_last_row','invalid_latest_replaces','wrong_tie_id'}:
  chosen={'physical_last_row':next(r for r in truth['cleaned'] if r['reason']=='superseded'),'invalid_latest_replaces':byid['S0221'],'wrong_tie_id':byid['S0032']}[name];rid=chosen['record_id'];put(raw,11,raw_row[rid],1);put(raw,12,raw_row[rid],None);put(raw,13,raw_row[rid],None)
 elif name in {'ignore_routing','drop_person_on_question_missing','missing_as_zero','multi_duplicate_count','none_with_other'}:
  if name=='ignore_routing':record=next(r for r in kept if r['question_states']['Q2']=='ineligible_skip');field='q2_valid';value=1
  elif name=='drop_person_on_question_missing':record=next(r for r in kept if r['question_states']['Q2']=='missing');put(raw,11,raw_row[record['record_id']],0);record=record;field='q4_valid';value=0
  elif name=='missing_as_zero':record=next(r for r in kept if r['question_states']['Q1']=='missing');field='q1_valid';value=1
  elif name=='multi_duplicate_count':record=next(r for r in kept if r['raw']['q3_barriers']=='A;A;B' and r['flags']['q3_A']);field='q3_A';value=2
  else:record=next(r for r in kept if r['question_states']['Q3']=='invalid_multi');field='q3_valid';value=1
  put(m,5+flag_keys.index(field),model_row[record['record_id']],value)
 elif name in {'denominator_total','denominator_cross_question','weighted_is_raw','rate_times_weight'}:
  if name=='denominator_total':
   for row in range(6,14):put(s,5,row,185,formula='185+0')
  elif name=='denominator_cross_question':put(s,5,13,170,formula='E6')
  elif name=='weighted_is_raw':
   for row in range(6,14):put(s,9,row,0,formula='F'+str(row))
  else:put(s,9,7,0,formula='F7*0.75')
 elif name in {'static_summary','constant_formulas'}:
  for i,metric in enumerate(truth['metrics'],6):
   for c,key in enumerate(fields,4):put(s,c,i,baseline[metric['metric_id']][key],formula=str(baseline[metric['metric_id']][key])+'+0' if name=='constant_formulas' else None)
 elif name=='stratum_not_normalized':
  record=next(r for r in kept if r['raw']['stratum']!=r['stratum_norm']);put(m,4,model_row[record['record_id']],0)
 elif name=='wrong_formula_correct_cache':set_metric(s,'Q1_yes','raw_rate',baseline['Q1_yes']['raw_rate'],formula='1/185',cache=baseline['Q1_yes']['raw_rate'])
 elif name=='divide_by_zero':set_metric(s,'Q1_yes','raw_rate',baseline['Q1_yes']['raw_rate'],formula='1/0',cache=baseline['Q1_yes']['raw_rate'])
 elif name=='zero_weight_rate_zero':
  for row in range(6,14):put(s,9,row,0,formula=f'IFERROR(G{row}/H{row},0)')
 elif name=='raw_timestamp_changed':put(raw,3,6,'2026-09-01T05:01:00Z')
 elif name=='drop_raw_row':raw.find(X+'sheetData').remove(raw.find(X+'sheetData/'+X+'row[@r="6"]'))
 elif name=='extra_model_record':
  old=m.find(X+'sheetData/'+X+'row[@r="6"]');new=copy.deepcopy(old);new.set('r','191')
  for c in new:c.set('r',re.sub(r'\d+$','191',c.get('r')))
  m.find(X+'sheetData').append(new);put(m,1,191,'S9999')
 elif name in {'hidden_summary','hidden_model'}:docs['xl/workbook.xml'].find(X+'sheets')[0 if name=='hidden_summary' else 1].set('state','hidden')
 for n,doc in docs.items():parts[n]=E.tostring(doc,xml_declaration=True,encoding='UTF-8',standalone=True)
 with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for n,raw in parts.items():z.writestr(n,raw)
def rewrite_word(path,name):
 if name not in {'word_rows_runs','word_merged_denominator','missing_quote','word_wrong_percentage','hidden_word','quote_unit_removed','quote_polarity_changed'}:return
 with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
 doc=E.fromstring(parts['word/document.xml']);body=doc.find(W+'body');tables=list(body.iter(W+'tbl'))
 if name=='word_rows_runs':
  table=tables[0];rows=table.findall(W+'tr')[1:]
  for row in rows:table.remove(row)
  for row in reversed(rows):table.append(row)
  for r in list(doc.iter(W+'r')):
   texts=r.findall(W+'t')
   if len(texts)==1 and len(texts[0].text or '')>4:
    text=texts[0].text;clone=copy.deepcopy(r);texts[0].text=text[:len(text)//2];clone.find(W+'t').text=text[len(text)//2:];r.addnext(clone)
 elif name=='word_merged_denominator':
  rows=tables[0].findall(W+'tr')
  for i in range(3,8):
   c=rows[i].findall(W+'tc')[3];pr=c.find(W+'tcPr')
   if pr is None:pr=E.SubElement(c,W+'tcPr')
   E.SubElement(pr,W+'vMerge',{W+'val':'restart' if i==3 else 'continue'})
   if i>3:
    for t in c.iter(W+'t'):t.text=''
 elif name=='missing_quote':
  for p in list(body.findall(W+'p')):
   if 'R-scope' in ''.join(t.text or '' for t in p.iter(W+'t')):body.remove(p)
 elif name in {'quote_unit_removed','quote_polarity_changed'}:
  for p in doc.iter(W+'p'):
   text=''.join(t.text or '' for t in p.iter(W+'t'))
   if name=='quote_unit_removed' and 'R-multi' in text:
    for t in p.iter(W+'t'):t.text=(t.text or '').replace('100%','100')
   if name=='quote_polarity_changed' and 'R-scope' in text:
    for t in p.iter(W+'t'):t.text=(t.text or '').replace('不能证明总体无偏','能证明总体无偏')
 elif name=='word_wrong_percentage':next(tables[0].findall(W+'tr')[1].findall(W+'tc')[5].iter(W+'t')).text='99.9%'
 elif name=='hidden_word':
  for r in doc.iter(W+'r'):
   pr=r.find(W+'rPr')
   if pr is None:pr=E.SubElement(r,W+'rPr')
   E.SubElement(pr,W+'vanish')
 parts['word/document.xml']=E.tostring(doc,xml_declaration=True,encoding='UTF-8',standalone=True)
 with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for n,raw in parts.items():z.writestr(n,raw)
results=[]
for name in CASES:
 if args.case and name not in args.case:continue
 target=qa/name;w=target/'workspace';shutil.copytree(frozen/'exec',w);shutil.copytree(frozen/'gt',w/'gt');shutil.copytree(frozen/'reference',w/'results')
 os.environ['GENERAL_E2E_OFFICE_LOCK']=str(args.office_lock.resolve());os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']=str(args.render_lock.resolve());os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']=str(target/'derived')
 if name not in INFRA or name.endswith('_capability'):
  rewrite_book(w/'results/analysis.xlsx',name);rewrite_word(w/'results/summary.docx',name)
  with (w/'results/exclusions.csv').open(encoding='utf-8',newline='') as f:reader=csv.DictReader(f);csvfields=reader.fieldnames;rows=list(reader)
  if name=='false_exclusion_row':
   for r in rows:r['source_row']=str(int(r['source_row'])+1)
  if name=='false_related_record':
   for r in rows:
    if r['reason']=='superseded':r['related_record_id']='S0001'
  if name=='duplicate_exclusion':rows.append(dict(rows[0]))
  if name=='missing_question_exclusion':rows=[r for r in rows if not (r['stage']=='Q3' and r['reason']=='ineligible_skip')]
  if name=='missing_record_exclusion':rows=[r for r in rows if r['stage']!='record']
  if name=='audit_bom_reordered':rows.reverse();csvfields=list(reversed(csvfields))
  with (w/'results/exclusions.csv').open('w',encoding='utf-8-sig' if name=='audit_bom_reordered' else 'utf-8',newline='') as f:writer=csv.DictWriter(f,fieldnames=csvfields,lineterminator='\n');writer.writeheader();writer.writerows(rows)
  for label,file in [('missing_book','analysis.xlsx'),('missing_word','summary.docx'),('missing_csv','exclusions.csv')]:
   if name==label:(w/'results'/file).unlink()
  if name=='bad_book':(w/'results/analysis.xlsx').write_text('bad ZIP')
  if name=='bad_word':(w/'results/summary.docx').write_text('bad ZIP')
  if name=='bad_csv':(w/'results/exclusions.csv').write_text('wrong,header\na,b\n')
  if name=='input_changed':(w/'weights.csv').write_text('stratum,weight\nA,99\n')
 else:
  if name=='missing_GT':(w/'gt/expected.json').unlink()
  if name=='missing_helper':(w/'gt/business_checks.py').unlink()
  if name=='helper_drift':
   with (w/'gt/business_checks.py').open('a') as f:f.write('\n# drift\n')
  if name=='missing_office':os.environ.pop('GENERAL_E2E_OFFICE_LOCK')
  if name=='missing_fonts':os.environ.pop('GENERAL_E2E_OFFICE_RENDER_LOCK')
  if name=='office_drift':
   lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text());lock['executable_sha256']='0'*64;dump(target/'bad-lock.json',lock);os.environ['GENERAL_E2E_OFFICE_LOCK']=str(target/'bad-lock.json')
 before={p.relative_to(w).as_posix():sha(p) for p in w.rglob('*') if p.is_file()}
 try:scores=runpy.run_path(str(w/'gt/grader.py'))['grade'](w)
 except (FileNotFoundError,ValueError,RuntimeError) as error:
  if name not in INFRA:raise
  result={'kind':'evaluation_error','score':None,'exception':type(error).__name__,'code':getattr(error,'code',None),'message':str(error)};ok=True
 else:
  if name in INFRA:raise AssertionError('infrastructure returned scores '+name)
  result={'kind':'scores','scores':scores};ok=scores['overall_score']==1. if name in POSITIVES else scores['overall_score']<1.
 after={p.relative_to(w).as_posix():sha(p) for p in w.rglob('*') if p.is_file() and '__pycache__' not in p.parts};assert before==after,name
 row={'name':name,'status':'PASS' if ok else 'FAIL','kind':'positive' if name in POSITIVES else 'negative' if name in NEGATIVES else 'infrastructure','result':result,'workspace_unchanged':True};results.append(row);dump(target/'validation.json',row);print(json.dumps(row),flush=True)
dump(qa/'validation.json',{'status':'PASS' if all(r['status']=='PASS' for r in results) else 'FAIL','results':results,'source_binding_sha256':sha(qa/'source-binding.json')});assert all(r['status']=='PASS' for r in results),str(qa)
