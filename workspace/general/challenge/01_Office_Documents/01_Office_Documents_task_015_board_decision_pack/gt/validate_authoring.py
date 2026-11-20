"""Real Office controls on independent frozen workspaces; preserve every result and source binding."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,copy,hashlib,io,json,os,re,shutil,subprocess,sys,tempfile,time,traceback,zipfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}';P='{http://schemas.openxmlformats.org/presentationml/2006/main}';A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def inventory(root):return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
def package(path,fn):
    with zipfile.ZipFile(path) as z:parts={n:z.read(n) for n in z.namelist()}
    fn(parts)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in parts.items():z.writestr(n,b)
def xml(path,part,fn):
    def change(parts):
        node=ET.fromstring(parts[part]);fn(node);parts[part]=ET.tostring(node,encoding='utf-8',xml_declaration=True)
    package(path,change)
def column(index):
    out=''
    while index:index,r=divmod(index-1,26);out=chr(65+r)+out
    return out
def point(address):
    m=re.fullmatch(r'([A-Z]+)(\d+)',address);index=0
    for char in m[1]:index=index*26+ord(char)-64
    return int(m[2]),index
def cell(node,address,value,formula=False):
    c=node.find(f'.//{X}c[@r="{address}"]')
    if c is None:
        r,_=point(address);row=node.find(f'.//{X}row[@r="{r}"]')
        if row is None:row=ET.SubElement(node.find(X+'sheetData'),X+'row',{'r':str(r)})
        c=ET.SubElement(row,X+'c',{'r':address})
    for child in list(c):c.remove(child)
    if formula:
        c.set('t','n');ET.SubElement(c,X+'f').text=str(value).removeprefix('=');ET.SubElement(c,X+'v').text='0'
    elif isinstance(value,(int,float)):
        c.set('t','n');ET.SubElement(c,X+'v').text=str(value)
    else:
        c.set('t','inlineStr');ET.SubElement(ET.SubElement(c,X+'is'),X+'t').text='' if value is None else str(value)
def actual_cell_text(node,shared):
    typ=node.get('t');v=node.findtext(X+'v')
    if typ=='s':return shared[int(v)]
    if typ=='inlineStr':return ''.join(x.text or '' for x in node.iter(X+'t'))
    return v
def shift_refs(text):
    def change(m):
        _,c=point(m[2]+'1');return m[1]+column(c+1)+m[3]+str(int(m[4])+2)
    return re.sub(r'(?<![A-Za-z0-9_])(\$?)([A-Z]{1,3})(\$?)([1-9][0-9]*)',change,text or '')
def rewrite_evidence(root,fn):
    path=root/'results/evidence.json';d=load(path)
    def visit(node):
        if isinstance(node,dict):
            if node.get('file')=='options.xlsx' and 'locator' in node:node['locator']=fn(node['locator'])
            for v in node.values():visit(v)
        elif isinstance(node,list):
            for v in node:visit(v)
    visit(d);dump(path,d)
def rewrite_word(path,fn):
    def change(n):
        for p in n.iter(W+'p'):
            texts=list(p.iter(W+'t'))
            if not texts:continue
            old=''.join(t.text or '' for t in texts);new=fn(old)
            if new!=old:
                texts[0].text=new
                for t in texts[1:]:t.text=''
    xml(path,'word/document.xml',change)
def rewrite_deck(path,fn):
    def change(parts):
        for name in list(parts):
            if not re.fullmatch(r'ppt/slides/slide\d+\.xml',name):continue
            n=ET.fromstring(parts[name])
            for p in n.iter(A+'p'):
                texts=list(p.iter(A+'t'))
                if not texts:continue
                old=''.join(t.text or '' for t in texts);new=fn(old)
                if new!=old:
                    texts[0].text=new
                    for t in texts[1:]:t.text=''
            parts[name]=ET.tostring(n)
    package(path,change)
def change_recommendation(root,chosen,unsafe=False):
    results=root/'results';word=results/'memo.docx';deck=results/'deck.pptx';book=results/'options.xlsx'
    if chosen=='A_phase1':
        lead='建议本轮先审批A仅首阶段续费与回款分层试点，费用2.5万元。按专项账户给定计划最低5.5万元，期末12万元。第二阶段不启动，支出仍待批准。C与A附条件延期也可选，收益未知，不主张唯一ROI最优。'
        detail='建议A仅首阶段验证续费与回款分层，费用2.5万元，最低余额5.5万元，第二阶段不启动。C仍可选，支出待批准，收益未知。'
        decision='拟议先审批A 仅首阶段试点';cash='费用2.5万元。专项账户最低5.5万元，期末12万元。当前计划满足每节点5万元底线，第二阶段不启动。'
    elif chosen=='A_deferred':
        lead='建议本轮先审批A第二阶段延期安排，首阶段2.5万元，第二阶段3.5万元延期至12月16日。给定计划最低5.5万元、期末8.5万元。第二阶段须12月15日实际到账、复核剩余节点并取得第二阶段批准，任何一项未满足就不启动。收益未知，C与A仅首阶段仍可选。'
        detail='建议A第二阶段延期到12月16日，当前计划最低5.5万元、期末8.5万元。实际到账、后续节点复核及第二阶段批准尚未满足时不得启动，不宣称唯一ROI最优。'
        decision='拟议先审批A 第二阶段延期';cash='首阶段2.5万元，第二阶段3.5万元延期12月16日。计划最低5.5万元，期末8.5万元。第二阶段仍须12月15日实际到账、后续节点复核和批准。'
    elif unsafe:
        lead='建议本轮先审批A原排期，按原日期支付两个阶段。费用6万元，期末8.5万元，所以可立即实施，无须检查月内节点。'
        detail='建议A原排期直接实施。';decision='拟议先审批A 原排期';cash='原日期两阶段直接实施，忽略中间节点。'
    else:raise ValueError(chosen)
    def wf(s):
        if s.startswith('建议本轮先审批C'):return lead
        if s.startswith('建议C先补齐'):return detail
        if s.startswith('审批前确认本轮仅选C'):return '审批前确认本轮仅选'+chosen+'，仍须满足现金与批准条件。'
        return s
    rewrite_word(word,wf)
    def pf(s):
        if s=='拟议先审批C 数据与渠道核验':return decision
        if s.startswith('费用2万元。专项账户最低6万元'):return cash
        if s.startswith('拟议先审批C。财务经理'):return decision+'。财务经理逐节点核对收支，试点负责人办理对应首阶段或延期条件，未满足则暂停新增支出。'
        if s=='A仅首阶段或附条件延期也可选。':return 'C及其它允许的A安排也可选。'
        return s
    rewrite_deck(deck,pf)
    xml(book,'xl/worksheets/sheet1.xml',lambda n:cell(n,'B14',chosen))
    xml(book,'xl/worksheets/sheet1.xml',lambda n:cell(n,'A16',detail))
    d=load(results/'evidence.json');d['selected_option']=chosen
    for e in d['conclusions']:
        if e['conclusion_id']=='REC-C':e.update(conclusion_id='REC-'+chosen,claim=detail,reason='在给定现金、权限与待批准条件下提出此建议。')
    dump(results/'evidence.json',d)

def mutate(name,root):
    results=root/'results';book=results/'options.xlsx';word=results/'memo.docx';deck=results/'deck.pptx';evidence=results/'evidence.json'
    if name=='reference':return
    if name=='renamed_sheets':
        names={'Decision':'管理层比较','Cash':'节点现金','Operations':'经营计算','Inputs':'模型参数'}
        def change(parts):
            node=ET.fromstring(parts['xl/workbook.xml'])
            for s in node.findall(X+'sheets/'+X+'sheet'):s.set('name',names[s.get('name')])
            parts['xl/workbook.xml']=ET.tostring(node)
            for part in list(parts):
                if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml',part):continue
                n=ET.fromstring(parts[part])
                for f in n.iter(X+'f'):
                    for old,new in names.items():f.text=(f.text or '').replace("'"+old+"'!","'"+new+"'!").replace(old+'!',"'"+new+"'!")
                parts[part]=ET.tostring(n)
        package(book,change);rewrite_evidence(root,lambda s:__import__('functools').reduce(lambda v,kv:v.replace(kv[0],kv[1]),names.items(),s));return
    if name=='shifted_grid':
        def change(parts):
            for part in list(parts):
                if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml',part):continue
                n=ET.fromstring(parts[part])
                for row in n.findall(X+'sheetData/'+X+'row'):
                    row.set('r',str(int(row.get('r'))+2))
                    for c in row.findall(X+'c'):c.set('r',shift_refs(c.get('r')))
                for f in n.iter(X+'f'):f.text=shift_refs(f.text)
                for el in n.iter():
                    for key in ['ref','sqref','topLeftCell']:
                        if key in el.attrib:el.set(key,shift_refs(el.get(key)))
                parts[part]=ET.tostring(n)
        package(book,change);rewrite_evidence(root,shift_refs);return
    if name=='chinese_headers':
        c=load(root/'gt/artifact_contract.json');aliases={k:v[-1] for k,v in c['field_aliases'].items()}
        def change(parts):
            shared=[''.join(x.itertext()) for x in ET.fromstring(parts['xl/sharedStrings.xml'])] if 'xl/sharedStrings.xml' in parts else []
            for part in list(parts):
                if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml',part):continue
                n=ET.fromstring(parts[part])
                for cellnode in list(n.iter(X+'c')):
                    value=actual_cell_text(cellnode,shared)
                    if value in aliases:cell(n,cellnode.get('r'),aliases[value])
                parts[part]=ET.tostring(n)
        package(book,change);return
    if name=='input_units_wan':
        def change(parts):
            n=ET.fromstring(parts['xl/worksheets/sheet4.xml'])
            for address,value in [('F6','期初现金 万元'),('G6',30),('F7','现金底线 万元'),('G7',5)]:cell(n,address,value)
            parts['xl/worksheets/sheet4.xml']=ET.tostring(n)
            for part in list(parts):
                if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml',part):continue
                n=ET.fromstring(parts[part])
                for f in n.iter(X+'f'):
                    for address in ['G6','G7']:f.text=(f.text or '').replace("'Inputs'!$"+address[0]+'$'+address[1:],"('Inputs'!$"+address[0]+'$'+address[1:]+'*10000)')
                parts[part]=ET.tostring(n)
        package(book,change);return
    if name=='english_choice':
        rewrite_word(word,lambda s:'We recommend option C. It costs CNY 20000. The special-account plan has minimum cash of CNY 60000 and ending cash of CNY 125000. Approval is pending and benefits remain unknown.' if s.startswith('建议本轮先审批C') else 'We recommend option C to verify the data before a larger commitment. Safe allowed A variants remain available, subject to their conditions.' if s.startswith('建议C先补齐') else s)
        rewrite_deck(deck,lambda s:s.replace('拟议先审批C','Recommend option C'));return
    if name=='wide_cash_nodes':
        def change(parts):
            wb=ET.fromstring(parts['xl/workbook.xml']);sheets=wb.find(X+'sheets')
            for s in sheets:
                if s.get('name')=='Cash':s.set('state','hidden')
            ET.SubElement(sheets,X+'sheet',{'name':'CashWide','sheetId':'99','{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':'rIdCashWide'})
            parts['xl/workbook.xml']=ET.tostring(wb)
            relns='{http://schemas.openxmlformats.org/package/2006/relationships}';rel=ET.fromstring(parts['xl/_rels/workbook.xml.rels'])
            ET.SubElement(rel,relns+'Relationship',{'Id':'rIdCashWide','Type':'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet','Target':'worksheets/cash-wide.xml'});parts['xl/_rels/workbook.xml.rels']=ET.tostring(rel)
            ns='{http://schemas.openxmlformats.org/package/2006/content-types}';ct=ET.fromstring(parts['[Content_Types].xml'])
            ET.SubElement(ct,ns+'Override',{'PartName':'/xl/worksheets/cash-wide.xml','ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
            raw=ET.tostring(ct,encoding='unicode');raw=re.sub(r'<(/?)ns[0-9]+:',r'<\1',raw);raw=re.sub(r'xmlns:ns[0-9]+=',r'xmlns=',raw);parts['[Content_Types].xml']=raw.encode()
            n=ET.Element(X+'worksheet');cols=ET.SubElement(n,X+'cols');ET.SubElement(cols,X+'col',{'min':'1','max':'4','width':'22','customWidth':'1'});ET.SubElement(n,X+'sheetData')
            cell(n,'A1','事件现金 CNY元')
            for j,h in enumerate(['date','A','B','C'],1):cell(n,column(j)+'3',h)
            truth=load(root/'gt/expected.json')
            for i,row in enumerate(truth['cash']['timelines']['BASE']['rows']):
                r=i+4;cell(n,'A'+str(r),row['date'])
                for j,base in enumerate([20,34,48],2):cell(n,column(j)+str(r),"'Cash'!F"+str(base+i),True)
            parts['xl/worksheets/cash-wide.xml']=ET.tostring(n)
        package(book,change);rewrite_evidence(root,lambda s:s.replace('Cash case_id','CashWide case_id'));return
    if name in {'equivalent_formulas','static_workbook','constant_formulas'}:
        def change(parts):
            for part in list(parts):
                if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml',part):continue
                n=ET.fromstring(parts[part])
                for c in n.iter(X+'c'):
                    f=c.find(X+'f')
                    if f is None:continue
                    if name=='static_workbook':c.remove(f)
                    elif name=='constant_formulas':
                        value=c.findtext(X+'v') or ''
                        f.text='"'+value.replace('"','""')+'"' if c.get('t')=='str' else 'TRUE()' if c.get('t')=='b' and value=='1' else 'FALSE()' if c.get('t')=='b' else value or '0'
                    else:
                        m=re.fullmatch(r'SUM\(C(\d+):E\1\)',f.text or '')
                        if m:f.text='C'+m[1]+'+D'+m[1]+'+E'+m[1]
                parts[part]=ET.tostring(n)
        package(book,change);return
    if name in {'A_phase1','A_deferred','unsafe_A_original'}:change_recommendation(root,'A' if name=='unsafe_A_original' else name,unsafe=name=='unsafe_A_original');return
    if name=='reordered_word_rows':
        def change(n):
            for tab in n.findall('.//'+W+'body/'+W+'tbl')[:3]:
                rows=tab.findall(W+'tr')
                for row in rows[1:]:tab.remove(row)
                for row in reversed(rows[1:]):tab.append(row)
        xml(word,'word/document.xml',change);return
    if name=='index_layout_and_nonprivate_ids':
        d=load(evidence)
        for i,e in enumerate(d['conclusions']):e['conclusion_id']='statement-'+str(i)
        dump(evidence,{'selected_case':d['selected_option'],'items':d['conclusions'],'provenance':d['source_files']});return
    if name=='word_cash_prose':
        truth=load(root/'gt/expected.json')
        def change(n):
            body=n.find(W+'body');tab=body.findall(W+'tbl')[2];index=list(body).index(tab);body.remove(tab)
            for i,case in enumerate(['A','B','C','A_phase1','A_deferred']):
                v=truth['cash']['timelines'][case];label={'A':'A原排期','B':'B原排期','C':'C','A_phase1':'A仅首阶段','A_deferred':'A第二阶段延期'}[case]
                text=f"{label}：最低余额{v['minimum_cny']}元，最低日期{v['minimum_dates'][0]}，期末余额{v['end_cash_cny']}元，最大底线缺口{v['maximum_floor_gap_cny']}元。"
                p=ET.Element(W+'p');ET.SubElement(ET.SubElement(p,W+'r'),W+'t').text=text;body.insert(index+i,p)
        xml(word,'word/document.xml',change);return
    if name=='word_history_prose':
        truth=load(root/'gt/expected.json')
        def change(n):
            body=n.find(W+'body');tables=body.findall(W+'tbl')[:2]
            for tab in tables:
                index=list(body).index(tab);which=0 if tab is tables[0] else 1;body.remove(tab)
                ids=['2025/ALL','2026/ALL'] if which==0 else ['2026/'+c for c in ['direct','platform','dealer','renewal']]
                for i,key in enumerate(ids):
                    v=truth['historical_metrics'][key];year,ch=key.split('/');label={'ALL':'公司','direct':'直销','platform':'平台','dealer':'经销','renewal':'续费'}[ch]
                    text=f"{year}年Q3 {label}：收入{float(v['revenue_cny'])/10000:.2f}万元；毛利{float(v['gross_profit_cny'])/10000:.2f}万元；加权毛利率{float(v['gross_margin'])*100:.2f}%。"
                    if ch=='ALL':text+=f"期间收款{float(v['receipts_cny'])/10000:.2f}万元；收款收入比{float(v['receipts_revenue_ratio'])*100:.2f}%。"
                    p=ET.Element(W+'p');ET.SubElement(ET.SubElement(p,W+'r'),W+'t').text=text;body.insert(index+i,p)
        xml(word,'word/document.xml',change);return
    if name=='quoted_unsafe_discussion':
        def change(n):
            p=ET.Element(W+'p');ET.SubElement(ET.SubElement(p,W+'r'),W+'t').text='对“建议B”的讨论仅用于反驳，不代表本轮建议。'
            n.find(W+'body').insert(1,p)
        xml(word,'word/document.xml',change);return
    if name=='wrong_weighted_margin':
        def change(n):
            tab=n.find(W+'body').findall(W+'tbl')[0];cellnode=tab.findall(W+'tr')[3].findall(W+'tc')[2]
            nodes=list(cellnode.iter(W+'t'));nodes[0].text='33.00%'
            for t in nodes[1:]:t.text=''
        xml(word,'word/document.xml',change);return
    if name=='profit_scope_wrong':rewrite_word(word,lambda s:'净利润 万元' if s=='毛利 万元' else s);return
    if name=='wrong_period':rewrite_word(word,lambda s:s.replace('2026年Q3','2026年Q2'));return
    if name=='A_end_balance_as_minimum':xml(book,'xl/worksheets/sheet1.xml',lambda n:cell(n,'B7','D7',True));return
    if name=='unconfirmed_120000_to_B':
        def change(n):
            f=n.find(f'.//{X}c[@r="F36"]/{X}f');f.text='('+f.text+')+120000'
        xml(book,'xl/worksheets/sheet2.xml',change);return
    if name=='monthly_only_nodes':
        def change(n):
            for r in range(6,90):
                if (r-6)%14 not in {0,5,9,13}:
                    for col in ['B','C','D','E','F','G','H']:cell(n,col+str(r),None)
        xml(book,'xl/worksheets/sheet2.xml',change);return
    if name=='wrong_formula_old_cache':
        xml(book,'xl/worksheets/sheet2.xml',lambda n:setattr(n.find(f'.//{X}c[@r="F30"]/{X}f'),'text','1/0'));return
    if name=='hardcoded_floor':
        def change(n):
            for r in range(6,90):cell(n,'G'+str(r),50000)
        xml(book,'xl/worksheets/sheet2.xml',change);return
    if name=='deck_disagrees_recommendation':rewrite_deck(deck,lambda s:s.replace('拟议先审批C','拟议先审批B'));return
    if name=='deck_safe_choice_disagrees':rewrite_deck(deck,lambda s:s.replace('拟议先审批C','拟议先审批A仅首阶段'));return
    if name=='deck_five_pages':xml(deck,'ppt/presentation.xml',lambda n:n.find(P+'sldIdLst').remove(n.find(P+'sldIdLst')[-1]));return
    if name=='deck_hidden_comparison':xml(deck,'ppt/slides/slide5.xml',lambda n:n.set('show','0'));return
    if name=='word_hidden_content':
        def change(n):
            for r in n.iter(W+'r'):
                props=r.find(W+'rPr')
                if props is None:props=ET.Element(W+'rPr');r.insert(0,props)
                ET.SubElement(props,W+'vanish')
        xml(word,'word/document.xml',change);return
    if name.startswith('missing_') and name.removeprefix('missing_') in {'word','workbook','deck','evidence','all'}:
        targets={'word':word,'workbook':book,'deck':deck,'evidence':evidence}
        for key,p in targets.items():
            if name=='missing_all' or key==name.removeprefix('missing_'):p.unlink()
        return
    if name=='invalid_evidence':evidence.write_text('{broken');return
    if name=='invalid_source_locator':
        d=load(evidence)
        for e in d['conclusions']:
            for s in e['sources']:
                if s['file']=='decision_constraints.md':s['locator']='D99'
        dump(evidence,d);return
    if name=='changed_protected_input':
        p=root/'decision_constraints.md';p.write_text(p.read_text()+'\nCHANGED\n');return
    if name=='semantic_price_causality':rewrite_word(word,lambda s:s.replace('G04-b 未知 公司全部失单75%由价格造成','G04-b 支持 公司全部失单75%由价格造成'));return
    if name=='semantic_missing_as_none':rewrite_word(word,lambda s:s.replace('G04-d 未知 原因缺失的10条全部未提到价格','G04-d 支持 原因缺失的10条全部未提到价格'));return
    if name=='semantic_sample_purchase':rewrite_word(word,lambda s:s.replace('G05-b 未知 总体80%会购买','G05-b 支持 总体80%会购买'));return
    if name=='semantic_benefits_known_zero':rewrite_word(word,lambda s:s.replace('增量收益未核实。','三方案真实收益均为0，未计收益即已知零。'));return
    if name=='unauthorized_B_delay':
        import datetime
        date=(datetime.date(2026,12,29)-datetime.date(1899,12,30)).days
        xml(book,'xl/worksheets/sheet4.xml',lambda n:[cell(n,address,date) for address in ['B23','B24']]);return
    if name=='semantic_already_approved':rewrite_word(word,lambda s:s.replace('三项尚未发生，不能写成已经满足。','三项已经全部满足，资金已到账且第二阶段审批已完成。'));return
    if name=='semantic_irrelevant_existing_source':
        d=load(evidence)
        for e in d['conclusions']:
            for s in e['sources']:
                if s['file']=='decision_constraints.md':s['locator']='D01'
        dump(evidence,d);return
    if name=='missing_gt':(root/'gt/expected.json').unlink();return
    if name=='missing_helper':(root/'gt/business_model.py').unlink();return
    if name=='private_helper_drift':
        p=root/'gt/artifact_io.py';p.write_text(p.read_text()+'\n# drift\n');return
    if name in {'missing_engine','font_drift'}:return
    raise ValueError('unknown control '+name)

POSITIVES=['reference','renamed_sheets','shifted_grid','chinese_headers','equivalent_formulas','A_phase1','A_deferred','reordered_word_rows','index_layout_and_nonprivate_ids','word_cash_prose','input_units_wan','english_choice','wide_cash_nodes','word_history_prose','quoted_unsafe_discussion']
NEGATIVES=['wrong_weighted_margin','profit_scope_wrong','wrong_period','A_end_balance_as_minimum','unconfirmed_120000_to_B','monthly_only_nodes','wrong_formula_old_cache','hardcoded_floor','static_workbook','constant_formulas','unsafe_A_original','deck_disagrees_recommendation','deck_safe_choice_disagrees','deck_five_pages','deck_hidden_comparison','word_hidden_content','missing_word','missing_workbook','missing_deck','missing_evidence','missing_all','invalid_evidence','invalid_source_locator','changed_protected_input','unauthorized_B_delay']
SEMANTIC=['semantic_price_causality','semantic_missing_as_none','semantic_already_approved','semantic_irrelevant_existing_source','semantic_sample_purchase','semantic_benefits_known_zero']
INFRA=['missing_gt','missing_helper','private_helper_drift','missing_engine','font_drift']
CHILD='''from pathlib import Path
import json,runpy,sys,traceback
root=Path(sys.argv[1]);out=Path(sys.argv[2])
try:
 values=runpy.run_path(str(root/'gt/grader.py'))['grade'](root)
 result={'kind':'scores','scores':values}
except Exception as e:
 result={'kind':'exception','type':type(e).__name__,'message':str(e)}
 traceback.print_exc()
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\\n')
'''
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cases',nargs='*');ap.add_argument('--workers',type=int,default=2)
    ap.add_argument('--office-lock',type=Path);ap.add_argument('--render-lock',type=Path);ap.add_argument('--output-dir',type=Path);ap.add_argument('--list-cases',action='store_true');args=ap.parse_args()
    if args.list_cases:
        print(json.dumps({'positive':POSITIVES,'negative':NEGATIVES,'semantic_only':SEMANTIC,'infrastructure':INFRA},ensure_ascii=False,indent=2));return
    assert 1<=args.workers<=4
    office_path=args.office_lock or Path(os.environ.get('GENERAL_E2E_OFFICE_LOCK',str(ROOT/'qa/office-lock.json')))
    render_path=args.render_lock or Path(os.environ.get('GENERAL_E2E_OFFICE_RENDER_LOCK',str(ROOT/'qa/native-reference-001/office-render-lock.json')))
    if not office_path.is_file() or not render_path.is_file():raise ValueError('provide --office-lock and --render-lock with probed Office and both-format font locks')
    selected=args.cases or POSITIVES+NEGATIVES+SEMANTIC+INFRA
    assert all(n in POSITIVES+NEGATIVES+SEMANTIC+INFRA for n in selected)
    base=ROOT/'qa' if (ROOT/'authoring').is_dir() else Path(tempfile.gettempdir())
    qa=args.output_dir or base/('h015-candidate-controls-'+str(time.time_ns()));qa.mkdir(parents=True,exist_ok=False);(qa/'child.py').write_text(CHILD)
    shutil.copytree(ROOT/'gt',qa/'source-gt',ignore=shutil.ignore_patterns('reference','__pycache__'))
    shutil.copytree(ROOT/'exec',qa/'source-exec');shutil.copytree(ROOT/'gt/reference/results',qa/'source-results')
    shutil.copyfile(Path(__file__),qa/'control-script.py')
    source_binding={p.name:sha(p) for p in (ROOT/'gt').iterdir() if p.is_file()};dump(qa/'source-binding.json',source_binding)
    def run(name):
        dest=qa/name;work=dest/'workspace';work.mkdir(parents=True)
        for p in (qa/'source-exec').iterdir():shutil.copyfile(p,work/p.name)
        shutil.copytree(qa/'source-gt',work/'gt');shutil.copytree(qa/'source-results',work/'results')
        mutate(name,work);before=inventory(work);env=os.environ.copy()
        office=office_path;render=render_path
        if name=='missing_engine':
            d=load(office);d['executable']=str(dest/'no-such-office');dump(dest/'office.json',d);office=dest/'office.json'
        if name=='font_drift':
            d=load(render);d['fonts'][0]['sha256']='0'*64;dump(dest/'render.json',d);render=dest/'render.json'
        env.update(GENERAL_E2E_OFFICE_LOCK=str(office),GENERAL_E2E_OFFICE_RENDER_LOCK=str(render),GENERAL_E2E_RULE_EVIDENCE_DIR=str(dest/'derived'))
        start=time.monotonic()
        proc=subprocess.run([sys.executable,str(qa/'child.py'),str(work),str(dest/'result.json')],env=env,cwd=work,capture_output=True,text=True,timeout=240)
        (dest/'stdout.txt').write_text(proc.stdout);(dest/'stderr.txt').write_text(proc.stderr)
        result=load(dest/'result.json');unchanged=before==inventory(work)
        expected='exception' if name in INFRA else 'one' if name in POSITIVES+SEMANTIC else 'less_than_one'
        score=result.get('scores',{}).get('overall_score')
        accepted=unchanged and ((expected=='exception' and result['kind']=='exception') or (expected=='one' and score==1.) or (expected=='less_than_one' and isinstance(score,(int,float)) and score<1.))
        observations=load(dest/'derived/h015-analysis.json') if (dest/'derived/h015-analysis.json').exists() else None
        if name=='missing_all':accepted=accepted and score==0.
        if name in {'static_workbook','constant_formulas','hardcoded_floor'}:accepted=accepted and observations['input_responses']['score']<1.
        if name in {'static_workbook','constant_formulas'}:accepted=accepted and observations['input_responses']['score']==0. and observations['scores']['business_correctness']==1.
        if name in {'missing_word','missing_workbook','missing_deck','missing_evidence','invalid_evidence','word_hidden_content','deck_hidden_comparison','deck_five_pages','monthly_only_nodes'}:accepted=accepted and observations['scores']['delivery_integrity']==0.
        if name in {'unsafe_A_original','deck_disagrees_recommendation'}:accepted=accepted and observations['scores']['business_correctness']<=.5
        if name=='changed_protected_input':accepted=accepted and observations['input_unchanged'] is False and score==.55
        if name in {'missing_evidence','invalid_evidence'}:accepted=accepted and observations['scores']['evidence_binding']==0.
        if name=='wrong_formula_old_cache':accepted=accepted and result['kind']=='scores'
        if name=='unauthorized_B_delay':accepted=accepted and observations['cash_summary_checks']['B']['cash_feasible'] is False and any(not ok for key,ok in observations['cash_node_checks'].items() if key.startswith('B/'))
        if name in INFRA:
            wanted={'missing_gt':('FileNotFoundError','expected.json'),'missing_helper':('FileNotFoundError','business_model.py'),'private_helper_drift':('ValueError','private contract/helper drift'),'missing_engine':('OfficeRuntimeError','OFFICE_EXECUTABLE_UNAVAILABLE'),'font_drift':('OfficeRuntimeError','OFFICE_RENDER_FONT_DRIFT')}[name]
            accepted=accepted and result.get('type')==wanted[0] and wanted[1] in result.get('message','')
        record={'name':name,'expected':expected,'status':'PASS' if accepted else 'FAIL','result':result,'workspace_unchanged':unchanged,'duration_seconds':round(time.monotonic()-start,3),'source_binding':source_binding}
        dump(dest/'validation.json',record);print(json.dumps({'name':name,'status':record['status'],'score':score,'exception':result.get('type')}),flush=True);return record
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(run,n):n for n in selected}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as e:
                traceback.print_exc();results.append({'name':futures[future],'status':'HARNESS_ERROR','message':str(e)})
    final={'status':'AUTHOR_CONTROLS_PASS' if all(r['status']=='PASS' for r in results) else 'AUTHOR_CONTROLS_REVIEW','total':len(results),'results':results,'qa':str(qa),
           'limit':'author rules/negative controls only; semantic cases intentionally retain rule 1.0 and need independent Judge; no semantic score, Harness score or measured difficulty'}
    dump(qa/'validation.json',final)
    if (ROOT/'authoring').is_dir():(ROOT/'qa/latest-candidate-controls.txt').write_text(str(qa)+'\n')
    print(json.dumps({'status':final['status'],'total':len(results),'qa':str(qa)}),flush=True)
if __name__=='__main__':main()
