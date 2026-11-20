"""Bounded visible semantic tables and real literal input bindings for H024."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import json,re,runpy
_api=runpy.run_path(str(Path(__file__).with_name('xlsx_observations.py')))
CandidateError=_api['CandidateError'];read_book=_api['read_book'];canon=_api['canon'];blank=_api['blank']
METRICS=['base_pay','allowance','earned_commission','clawback','net_commission','total_pay']
FIELDS={
'payroll':['scenario_id','employee_id','month','paid_fraction','gross_sales','commission_raw']+METRICS,
'retro':['scenario_id','employee_id','original_month','pay_month','original_gross','refund_before','refund_through','eligible_before','eligible_after','commission_before','commission_after','current_clawback'],
'comparisons':['scenario_id','scenario_name','month']+METRICS+['delta_'+k for k in METRICS],
'employees':['employee_id','employee_name','base_monthly_salary'],
'attendance':['attendance_id','employee_id','month','paid_days','standard_days'],
'sales':['sale_id','employee_id','month','amount','status'],
'refunds':['refund_id','employee_id','refund_month','original_sale_id','amount','status'],
'parameters':['scenario_id','scenario_name','month','salary_multiplier','tier1_limit','tier2_limit','rate1','rate2','rate3','commission_cap','full_allowance']}
CN={'scenario_id':['情景编号','情景ID'],'scenario_name':['情景名称'],'employee_id':['员工ID','员工编号'],'employee_name':['员工姓名'],'month':['月份'],'paid_fraction':['出勤比例'],'gross_sales':['有效销售额','原月销售额'],'commission_raw':['未舍入提成'],'base_pay':['底薪'],'allowance':['补贴'],'earned_commission':['正向提成'],'clawback':['回扣','当月回扣'],'net_commission':['净提成'],'total_pay':['测算工资','工资合计'],'original_month':['原销售月','原月'],'pay_month':['发薪月','截至月'],'original_gross':['原月总销售'],'refund_before':['前期累计退款'],'refund_through':['截至本期累计退款'],'eligible_before':['退款前计提基数'],'eligible_after':['退款后计提基数'],'commission_before':['退款前封顶提成'],'commission_after':['退款后封顶提成'],'current_clawback':['本月追溯回扣'],'base_monthly_salary':['原月薪'],'attendance_id':['考勤ID'],'paid_days':['计薪天数'],'standard_days':['标准天数'],'sale_id':['销售ID'],'amount':['金额'],'status':['状态'],'refund_id':['退款ID'],'refund_month':['退款月'],'original_sale_id':['原销售ID'],'salary_multiplier':['月薪系数'],'tier1_limit':['第一阶梯边界'],'tier2_limit':['第二阶梯边界'],'rate1':['第一档提成率'],'rate2':['第二档提成率'],'rate3':['第三档提成率'],'commission_cap':['提成封顶'],'full_allowance':['满勤月补贴'],'decision':['处理结果','处理判定']}
for key in METRICS:CN['delta_'+key]=['较Base'+x for x in CN[key]]+['较基准'+x for x in CN[key]]
ALIASES={canon(alias):key for key in set(sum(FIELDS.values(),[]))|{'decision'} for alias in [key,*CN.get(key,[])]}
SELECTOR={canon(v) for v in ['active_scenario_id','scenario_selector','查看情景编号','活动情景编号','情景选择编号']}
NUMERIC={'amount','paid_days','standard_days','base_monthly_salary','scenario_id','salary_multiplier','tier1_limit','tier2_limit','rate1','rate2','rate3','commission_cap','full_allowance'}
def equal(a,b):
    if isinstance(b,(int,float)) or isinstance(b,str) and re.fullmatch(r'[+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?',b):
        if isinstance(a,bool) or blank(a):return False
        try:return Decimal(str(a)).is_finite() and abs(Decimal(str(a))-Decimal(str(b)))<=Decimal('0.000001')
        except InvalidOperation:return False
    return a==b
def tables(book,kind,minimal=True):
    needed=set(FIELDS[kind]);candidates=[]
    for sheet in book:
        grid=defaultdict(dict)
        for (r,c),cell in sheet['cells'].items():grid[r][c]=cell
        heads=[]
        for r,cells in grid.items():
            blocks=[];block=[];previous=None
            for c,cell in sorted(cells.items()):
                if blank(cell['value']) or cell.get('merged_from'):continue
                if previous is not None and c>previous+1:blocks.append(block);block=[]
                block.append((c,cell));previous=c
            if block:blocks.append(block)
            for block in blocks:
                by=defaultdict(list)
                for c,cell in block:
                    key=ALIASES.get(canon(cell['value']))
                    if key:by[key].append(c)
                if needed<=set(by) and all(len(by[k])==1 for k in needed):heads.append((r,{k:by[k][0] for k in needed},len(block)-len(needed),by))
        any_headers={r for r,cells in grid.items() if sum(ALIASES.get(canon(cell['value'])) is not None for cell in cells.values() if not cell.get('merged_from'))>=3}
        for r,cols,extra,by in heads:
            end=min((n for n in any_headers if n>r),default=50001);rows=[]
            for rn,cells in sorted(grid.items()):
                if not r<rn<end:continue
                row={k:cells.get(c,{}).get('value') for k,c in cols.items()}
                idkey={'sales':'sale_id','refunds':'refund_id','attendance':'attendance_id','parameters':'scenario_id','comparisons':'scenario_id'}.get(kind,'employee_id')
                ident=row.get(idkey)
                valid=equal(ident,1) or equal(ident,2) or equal(ident,3) if idkey=='scenario_id' else isinstance(ident,str) and re.fullmatch(r'[EASR]\d{2,3}',ident)
                if not valid:continue
                if 'decision' in by:row['decision']=cells.get(by['decision'][0],{}).get('value')
                row.update(_sheet=sheet['name'],_row=rn,_columns=cols,_cells={k:cells.get(c,{}) for k,c in cols.items()},_visible=all(grid[r][c].get('visible') and cells.get(c,{'visible':True}).get('visible') for c in cols.values()))
                rows.append(row)
            if rows:candidates.append((extra,rows))
    if not candidates:return []
    best=min(n for n,_ in candidates)
    return [row for n,part in candidates if not minimal or n==best for row in part]
def identity(kind,row):
    if kind=='payroll':return (row['scenario_id'],row['employee_id'],row['month'])
    if kind=='retro':return (row['scenario_id'],row['employee_id'],row['original_month'],row['pay_month'])
    return (row['scenario_id'],row['month'])
def wants(expected,sid):return {**{k:[dict(r,scenario_id=sid) for r in expected['scenarios'][str(sid)][k]] for k in ['payroll','retro']},'comparisons':expected['comparisons']}
def truth_map(expected,sid):
    return {kind+'/'+str(identity(kind,row))+'/'+field:row[field] for kind,rows in wants(expected,sid).items() for row in rows for field in FIELDS[kind]}
def observe(path,expected,sid):
    book=read_book(path);checks={};counts={}
    for s in book:checks['errors/'+s['name']]=not s['errors']
    for kind,wanted in wants(expected,sid).items():
        actual=tables(book,kind);counts[kind]=len(actual);by=defaultdict(list)
        for row in actual:by[identity(kind,row)].append(row)
        checks[kind+'/identity_set']=set(by)=={identity(kind,r) for r in wanted}
        for want in wanted:
            key=identity(kind,want);matches=by[key];prefix=kind+'/'+str(key);checks[prefix+'/unique']=len(matches)==1;row=matches[0] if len(matches)==1 else {}
            checks[prefix+'/visible']=bool(row.get('_visible'))
            for field in FIELDS[kind]:checks[prefix+'/'+field]=equal(row.get(field),want[field])
    mean=lambda xs:sum(xs)/len(xs) if xs else 0
    return {'checks':checks,'scores':{kind:mean([v for key,v in checks.items() if key.startswith(kind+'/')]) for kind in ['payroll','retro','comparisons']},'complete':all(checks.values()),'table_counts':counts}
def matching_literal(row,record,kind):
    if not row['_visible'] or any(not equal(row.get(k),record[k]) for k in FIELDS[kind]):return False
    return all(not row['_cells'][k].get('formula') and (k not in NUMERIC or isinstance(row.get(k),(int,float)) and not isinstance(row.get(k),bool)) for k in FIELDS[kind])
def raw_inventory(path,records):
    book=read_book(path);checks={};audit={}
    for kind in ['employees','attendance','sales','refunds','parameters']:
        rows=tables(book,kind,False)
        for index,record in enumerate(records[kind]):
            matches=[r for r in rows if matching_literal(r,record,kind)];checks[kind+'/'+str(index)]=bool(matches)
        # Extra or damaged records are not silently treated as an intact source.
        checks[kind+'/no_unknown_rows']=all(any(matching_literal(row,record,kind) for record in records[kind]) for row in rows if all(not row['_cells'][k].get('formula') for k in FIELDS[kind]))
        if kind in ['sales','refunds']:
            idkey='sale_id' if kind=='sales' else 'refund_id'
            for row in rows:
                key=(kind,row[idkey]);value=row.get('decision');audit.setdefault(key,[]).append(value)
    return {'checks':checks,'complete':all(checks.values()),'audit':audit}
def audit_score(inventory,expected):
    groups=defaultdict(list);cn={'posted':['已计入','已确认'],'not_posted':['未确认','状态排除'],'outside_period':['季度外','期间外']}
    for want in expected['source_audit']:
        values=inventory['audit'].get((want['source'],want['record_id']),[]);good=bool(values) and all(v==want['decision'] or canon(v) in {canon(x) for x in cn[want['decision']]} for v in values);groups[want['decision']].append(good)
    mean=lambda xs:sum(xs)/len(xs) if xs else 0
    return mean([mean(v) for v in groups.values()])
def parameter_targets(path,records,sid,month,field):
    record=next(r for r in records['parameters'] if r['scenario_id']==sid and r['month']==month)
    return [{'sheet':r['_sheet'],'cell':r['_cells'][field]['cell'],'old_value':r[field]} for r in tables(read_book(path),'parameters',False) if matching_literal(r,record,'parameters')]
def selector_targets(path):
    out=[]
    for s in read_book(path):
        for (r,c),cell in s['cells'].items():
            target=s['cells'].get((r,c+1),{})
            if canon(cell['value']) in SELECTOR and cell['visible'] and target.get('visible') and not target.get('formula') and equal(target.get('value'),1):out.append({'sheet':s['name'],'cell':target['cell'],'old_value':1})
    return out
def read_validation(path,expected,variants,book_path,records):
    text=Path(path).read_text(encoding='utf-8-sig');facts={}
    for key in ['test_id','scenario_id','month','field','old_value','new_value','metric','before','after','restored','parameter_input','result_locator']:
        values=re.findall(r'(?m)^\s*'+key+r'\s*[:：]\s*(.*?)\s*$',text);facts[key]=values[0] if len(values)==1 else None
    name=facts['test_id'];specs={'growth_september_cap':(2,'2026-09','commission_cap',2100),'guardrail_september_zero_cap':(3,'2026-09','commission_cap',0),'base_july_rate':(1,'2026-07','rate1',.02)}
    checks={'known_test':name in specs,'sources':all(n in text for n in ['payroll.xlsx','policy.md','scenario_inputs.json'])}
    if name in specs:
        sid,month,field,new=specs[name];old=next(p[field] for p in records['parameters'] if p['scenario_id']==sid and p['month']==month);metric=facts['metric']
        checks.update({'scenario':equal(facts['scenario_id'],sid),'month':facts['month']==month,'field':facts['field']==field,'old':equal(facts['old_value'],old),'new':equal(facts['new_value'],new),'metric':metric in METRICS})
        if metric in METRICS:
            base=next(r[metric] for r in expected['comparisons'] if r['scenario_id']==sid and r['month']==month);after=next(r[metric] for r in variants[name]['comparisons'] if r['scenario_id']==sid and r['month']==month)
            checks.update(before=equal(facts['before'],base),after=equal(facts['after'],after),restored=equal(facts['restored'],base),effective=not equal(base,after))
            def location(value):
                match=re.fullmatch(r"'?(.+?)'?!(\$?[A-Z]+\$?[1-9]\d*)",value or '')
                return (match[1].replace("''","'"),match[2].replace('$','')) if match else None
            targets=parameter_targets(book_path,records,sid,month,field);checks['parameter_locator']=location(facts['parameter_input']) in {(t['sheet'],t['cell']) for t in targets}
            rows=tables(read_book(book_path),'comparisons');checks['result_locator']=location(facts['result_locator']) in {(r['_sheet'],r['_cells'][metric]['cell']) for r in rows if equal(r['scenario_id'],sid) and r['month']==month}
    return {'checks':checks,'score':sum(checks.values())/len(checks),'complete':all(checks.values()),'facts':facts,'limit':'Checks a reported monthly test against source truth and bound native inputs/results. Actual execution is independently replayed; open prose quality is not judged.'}
