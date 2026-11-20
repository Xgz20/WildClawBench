"""End-to-end actual Office controls for rule equivalence, business failures and infrastructure boundaries."""
from pathlib import Path
import argparse,csv,hashlib,json,os,re,shutil,subprocess,sys,time,zipfile
import xml.etree.ElementTree as ET

S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def inventory(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
def mutate(path,action):
    with zipfile.ZipFile(path) as z:parts=[(i,z.read(i.filename)) for i in z.infolist()]
    raw={i.filename:b for i,b in parts};trees={name:ET.fromstring(raw[name]) for name in ['xl/workbook.xml','xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml']}
    strings=[]
    if 'xl/sharedStrings.xml' in raw:strings=[''.join(n.text or '' for n in x.iter(S+'t')) for x in ET.fromstring(raw['xl/sharedStrings.xml']).findall(S+'si')]
    def value(cell):
        if cell.get('t')=='inlineStr':return ''.join(n.text or '' for n in cell.iter(S+'t'))
        v=cell.find(S+'v');text=v.text if v is not None else ''
        return strings[int(text)] if cell.get('t')=='s' else text
    def put(cell,val,formula=False,general=False):
        for n in list(cell):cell.remove(n)
        if general:cell.set('s','0')
        if formula:cell.set('t','n');ET.SubElement(cell,S+'f').text=str(val)
        elif isinstance(val,(float,int)) and not isinstance(val,bool):cell.set('t','n');ET.SubElement(cell,S+'v').text=str(val)
        else:cell.set('t','inlineStr');ET.SubElement(ET.SubElement(cell,S+'is'),S+'t').text=str(val)
    def row(tree,identity):return next(r for r in tree.findall(S+'sheetData/'+S+'row') if any(value(c)==identity for c in r.findall(S+'c')))
    def cell(tree,identity,letter):return next(c for c in row(tree,identity).findall(S+'c') if re.match('[A-Z]+',c.get('r'))[0]==letter)
    action(trees,value,put,row,cell)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for info,b in parts:z.writestr(info,ET.tostring(trees[info.filename],encoding='utf-8',xml_declaration=True) if info.filename in trees else b)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case-root',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path);args=parser.parse_args()
    root=args.case_root.resolve();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    active=read(root/'authoring/active_inputs.json');source=Path(active['exec_root']);cached=next((root/'qa/grader-baseline-v1/derived/recalculated').glob('*.xlsx'))
    scenarios=[('reference','positive'),('static_manual_intervals','positive'),('chinese_headers_renamed_reordered','positive'),('literal_percent_values','positive'),
      ('fraction_units','positive'),('people_instead_of_thousands','positive'),('pixel_and_expanded_regions','positive'),('records_in_columns','positive'),
      ('annotator_a_intervals','positive'),('annotator_b_intervals','positive'),('consistent_duplicate_view','positive'),
      ('wrong_axis','negative'),('wrong_rate_unit','negative'),('stack_top_as_new','negative'),('cumulative_as_weekly','negative'),('overprecise_week','negative'),
      ('false_significance_denial','negative'),('pillar_ratio_as_rate_ratio','negative'),('uninformative_interval','negative'),('unrelated_region','negative'),('wrong_source','negative'),
      ('hidden_claim_row','negative'),('hidden_reading_sheet','negative'),('missing_findings','negative'),('malformed_utf8_findings','negative'),('missing_workbook','negative'),('corrupt_workbook','negative'),
      ('actual_formula_error','negative'),('conflicting_duplicate_view','negative'),('modified_input','negative'),
      ('semantic_false_explanation','semantic_only'),('semantic_unsupported_exactness','semantic_only'),
      ('missing_GT','infrastructure'),('helper_drift','infrastructure'),('missing_runtime','infrastructure'),('engine_drift','infrastructure')]
    reports=[]
    for name,kind in scenarios:
        case=out/name;case.mkdir();work=case/'workspace';shutil.copytree(source,work);shutil.copytree(root/'gt',work/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copytree(root/'gt/reference/results',work/'results')
        book=work/'results/claims_review.xlsx'
        if name not in {'reference','actual_formula_error'}:
            shutil.copyfile(cached,book)
            mutate(book,lambda trees,value,put,row,cell:[c.remove(f) for tree in trees.values() for c in tree.iter(S+'c') for f in list(c.findall(S+'f'))])
        def edit(trees,value,put,row,cell):
            claims=trees['xl/worksheets/sheet1.xml'];readings=trees['xl/worksheets/sheet2.xml'];wb=trees['xl/workbook.xml']
            changes={'wrong_axis':('R02','E','left'),'wrong_rate_unit':('R04','F','人'),'stack_top_as_new':('R05','G',290),
              'cumulative_as_weekly':('R13','G',220),'overprecise_week':('R13','G',59.999),'pillar_ratio_as_rate_ratio':('R20','G',2),
              'uninformative_interval':('R01','G',0),'wrong_source':('R03','I','chart_pages/chart_D.png'),
              'unrelated_region':('R03','J',json.dumps({'coordinate_system':'normalized','boxes':[[0,0,.04,.04]]}))}
            if name in changes:
                identity,letter,val=changes[name];put(cell(readings,identity,letter),val)
                second={'stack_top_as_new':310,'cumulative_as_weekly':230,'overprecise_week':60.001,'pillar_ratio_as_rate_ratio':2.6,'uninformative_interval':25}
                if name in second:put(cell(readings,identity,'H'),second[name])
            if name=='false_significance_denial':put(cell(claims,'C08','B'),'refuted')
            if name=='hidden_claim_row':row(claims,'C03').set('hidden','1')
            if name=='hidden_reading_sheet':wb.findall(S+'sheets/'+S+'sheet')[1].set('state','hidden')
            if name=='actual_formula_error':put(cell(readings,'R13','G'),'1/0',formula=True)
            if name in {'literal_percent_values','fraction_units'}:
                for identity in ['R02','R04',*[f'R{i:02}' for i in range(14,20)]]:
                    for letter in ['G','H']:
                        c=cell(readings,identity,letter);v=float(value(c))
                        put(c,str(v*100)+'%' if name=='literal_percent_values' else v,general=True)
                    if name=='fraction_units':put(cell(readings,identity,'F'),'比例')
            if name=='people_instead_of_thousands':
                for identity in ['R01','R03','R11','R12','R13']:
                    for letter in ['G','H']:
                        c=cell(readings,identity,letter);put(c,float(value(c))*1000,general=True)
                    put(cell(readings,identity,'F'),'人')
            if name=='pixel_and_expanded_regions':
                for tree,letter in [(claims,'H'),(readings,'J')]:
                    for r in tree.findall(S+'sheetData/'+S+'row'):
                        if int(r.get('r'))<6:continue
                        c=next(c for c in r.findall(S+'c') if re.match('[A-Z]+',c.get('r'))[0]==letter);obj=json.loads(value(c));new=[]
                        for x0,y0,x1,y1 in obj['boxes']:new.append([max(0,x0-.008)*1467,max(0,y0-.008)*960,min(1,x1+.008)*1467,min(1,y1+.008)*960])
                        put(c,json.dumps({'coordinate_system':'pixel','boxes':new}))
            if name.startswith('annotator_'):
                who='a' if name=='annotator_a_intervals' else 'b';annotations=read(root/f'independent-review/{who}/image_reading_{who}.json')
                for rec in annotations['readings']:
                    for letter,key in [('G','lower'),('H','upper')]:put(cell(readings,rec['reading_id'],letter),rec[key]/100 if rec['unit']=='%' else rec[key],general=rec['unit']!='%')
                    put(cell(readings,rec['reading_id'],'F'),rec['unit']);put(cell(readings,rec['reading_id'],'E'),rec['axis'])
            if name=='chinese_headers_renamed_reordered':
                aliases={'claim_id':'主张编号','decision':'判定','chart':'图号','reading_ids':'关联读数','reason':'解释','limits':'限制','source_file':'来源图','source_regions':'区域证据',
                         'reading_id':'读数编号','metric':'指标','period':'时点','axis':'坐标轴','unit':'单位','lower':'下界','upper':'上界','basis':'计算依据'}
                for sh,new in zip(wb.findall(S+'sheets/'+S+'sheet'),['Audit','Readings']):sh.set('name',new)
                for tree in [claims,readings]:
                    header=next(r for r in tree.findall(S+'sheetData/'+S+'row') if r.get('r')=='5')
                    for c in header.findall(S+'c'):put(c,aliases[value(c)])
                    parent=tree.find(S+'sheetData');data=[r for r in parent if int(r.get('r'))>=6]
                    for r in data:parent.remove(r)
                    for index,r in enumerate(reversed(data),6):
                        r.set('r',str(index))
                        for c in r.findall(S+'c'):c.set('r',re.match('[A-Z]+',c.get('r'))[0]+str(index))
                        parent.append(r)
            if name=='records_in_columns':
                for tree in [claims,readings]:
                    parent=tree.find(S+'sheetData');old=list(parent);new={}
                    def letters(n):
                        result=''
                        while n:n,k=divmod(n-1,26);result=chr(65+k)+result
                        return result
                    for r in old:
                        if int(r.get('r'))<5:continue
                        for c in list(r.findall(S+'c')):
                            col=0
                            for char in re.match('[A-Z]+',c.get('r'))[0]:col=col*26+ord(char)-64
                            new_row=col+4;new_col=int(r.get('r'))-4;c.set('r',letters(new_col)+str(new_row));new.setdefault(new_row,[]).append(c)
                        parent.remove(r)
                    for number,cells in sorted(new.items()):
                        r=ET.SubElement(parent,S+'row',{'r':str(number),'ht':'85','customHeight':'1'})
                        for c in cells:r.append(c)
            if name in {'consistent_duplicate_view','conflicting_duplicate_view'}:
                parent=claims.find(S+'sheetData');old=row(claims,'C06');copy=ET.fromstring(ET.tostring(old));copy.set('r','20')
                for c in copy.findall(S+'c'):c.set('r',re.match('[A-Z]+',c.get('r'))[0]+'20')
                if name=='conflicting_duplicate_view':put(next(c for c in copy.findall(S+'c') if c.get('r')=='B20'),'supported')
                parent.append(copy)
            if name in {'semantic_false_explanation','semantic_unsupported_exactness'}:
                for identity in [f'C{i:02}' for i in range(1,9)]:put(cell(claims,identity,'E'),'图形已证明所有主张都成立，已确认所有原值和显著因果。' if name=='semantic_false_explanation' else 'W5实际人数已经精确确认60000人且误差为0，误差线重叠证明差异不显著。')
        if name not in {'reference','static_manual_intervals','missing_workbook','corrupt_workbook'}:mutate(book,edit)
        if name=='missing_findings':(work/'results/findings.md').unlink()
        if name=='malformed_utf8_findings':(work/'results/findings.md').write_bytes(b'\xff\xfe\x00')
        if name=='missing_workbook':book.unlink()
        if name=='corrupt_workbook':book.write_bytes(b'not an XLSX')
        if name=='modified_input':
            p=work/'chart_pages/chart_A.png';p.write_bytes(p.read_bytes()+b'changed')
        if name=='missing_GT':(work/'gt/expected.json').unlink()
        if name=='helper_drift':
            p=work/'gt/artifact_io.py';p.write_text(p.read_text()+'\n# drift\n')
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','GENERAL_E2E_OFFICE_LOCK':str(root/'qa/runtime/office.json'),'GENERAL_E2E_RULE_EVIDENCE_DIR':str(case/'derived')}
        if name=='missing_runtime':env.pop('GENERAL_E2E_OFFICE_LOCK')
        if name=='engine_drift':
            lock=read(root/'qa/runtime/office.json');lock['executable_sha256']='0'*64;dump(case/'bad-office.json',lock);env['GENERAL_E2E_OFFICE_LOCK']=str(case/'bad-office.json')
        before=inventory(work);started=time.monotonic()
        result=subprocess.run([sys.executable,'-B','-c',"from pathlib import Path; import json,runpy,sys; r=Path(sys.argv[1]); print(json.dumps(runpy.run_path(str(r/'gt/grader.py'))['grade'](r)))",str(work)],env=env,text=True,capture_output=True,timeout=600)
        (case/'stdout.txt').write_text(result.stdout);(case/'stderr.txt').write_text(result.stderr);unchanged=before==inventory(work)
        assert unchanged,name
        if kind=='infrastructure':assert result.returncode!=0,(name,result.stdout);scores=None
        else:
            assert result.returncode==0,(name,result.stderr[-2500:]);scores=json.loads(result.stdout)
            if kind in {'positive','semantic_only'}:assert abs(scores['overall_score']-1.)<1e-10,(name,scores)
            else:assert scores['overall_score']<1.-1e-10,(name,scores)
        record={'name':name,'kind':kind,'scores':scores,'returncode':result.returncode,'workspace_unchanged':unchanged,'grader_sha256':sha(root/'gt/grader.py'),
            'artifact_contract_sha256':sha(root/'gt/artifact_contract.json'),'elapsed_seconds':round(time.monotonic()-started,3),'candidate_semantic_score':None,
            'semantic_expected':0. if kind=='semantic_only' else None,'input_inventory_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()}
        dump(case/'result.json',record);reports.append(record);print(json.dumps({'name':name,'kind':kind,'score':scores and scores['overall_score'],'ok':True}),flush=True)
    summary={'status':'AUTHOR_CONTROLS_PASS','cases':reports,'counts':{k:sum(r['kind']==k for r in reports) for k in ['positive','negative','semantic_only','infrastructure']},
       'scope':'Actual complete rule executions and native Office recomputation. Positive equivalence controls establish the automatic component, not full semantic/layout quality. Semantic-only failures are source-grounded expectations, not fabricated independent Judge scores.'}
    dump(out/'validation.json',summary)
if __name__=='__main__':main()
