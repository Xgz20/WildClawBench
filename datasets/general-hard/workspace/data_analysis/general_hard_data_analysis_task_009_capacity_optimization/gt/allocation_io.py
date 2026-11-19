"""Visible semantic tables; recompute the proposed plan, never match a matrix."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import json,re,runpy
_api=runpy.run_path(str(Path(__file__).with_name('xlsx_observations.py')))
CandidateError=_api['CandidateError'];read_book=_api['read_book'];canon=_api['canon'];blank=_api['blank']
FIELDS={
'decisions':['plant_id','sku_id','units'],
'allocations':['plant_id','sku_id','units','production_cost','transport_cost','setup_cost','line_total','line_active'],
'products':['sku_id','priority','demand_units','minimum_service','served_units','unmet_units'],
'plant_results':['plant_id','used_units','unit_capacity','unit_slack','used_labour','labour_capacity','labour_slack','active','activation_cost'],
'material_results':['material_id','used_units','available_units','slack'],
'demand':['sku_id','sku_name','priority','demand_units','minimum_service','destination'],
'plants':['plant_id','plant_name','unit_capacity','labour_capacity'],
'routes':['plant_id','sku_id','eligible','max_units','min_batch','labour_per_unit'],
'materials':['material_id','available_units'],
'recipes':['sku_id','material_id','units_per_item'],
'costs':['plant_id','sku_id','variable_cost','transport_cost','line_setup_fee','plant_activation_fee'],
'controls':['control','value']}
CN={'plant_id':['工厂ID','工厂编号'],'plant_name':['工厂名称'],'sku_id':['商品ID','商品编号'],'sku_name':['商品名称'],'units':['分配数量','交付数量','生产件数'],'production_cost':['变动生产费','生产费用'],'transport_cost':['运输费','运输单价'],'setup_cost':['路线开线费'],'line_total':['路线总费用'],'line_active':['路线启用'],'priority':['优先级'],'demand_units':['需求件数'],'minimum_service':['最低服务量'],'served_units':['已交付件数'],'unmet_units':['缺口件数'],'used_units':['已用数量'],'unit_capacity':['件数产能'],'unit_slack':['件数余量'],'used_labour':['已用工时'],'labour_capacity':['工时产能'],'labour_slack':['工时余量'],'active':['工厂启用'],'activation_cost':['工厂启动费用'],'material_id':['物料ID','物料编号'],'available_units':['可用数量'],'slack':['余量'],'destination':['目的地'],'eligible':['路线可用'],'max_units':['路线最大量'],'min_batch':['最小批量'],'labour_per_unit':['单件工时'],'units_per_item':['单件耗料'],'variable_cost':['变动成本单价'],'line_setup_fee':['开线费单价'],'plant_activation_fee':['工厂启动费单价'],'control':['控制项'],'value':['控制值']}
ALIASES={canon(alias):key for key in set(sum(FIELDS.values(),[])) for alias in [key,*CN.get(key,[])]}
MONEY_MAP={'production_cost':'production_cents','transport_cost':'transport_cents','setup_cost':'setup_cents','line_total':'line_total_cents','activation_cost':'activation_cents','total_cost':'total_cents','budget':'budget_cents','budget_slack':'budget_slack_cents'}
def equal(actual,want):
    if isinstance(want,bool):return actual in ([True,1,'true','TRUE','1'] if want else [False,0,'false','FALSE','0'])
    if isinstance(want,(int,float,Decimal)) or isinstance(want,str) and re.fullmatch(r'[+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?',want):
        if isinstance(actual,bool) or blank(actual):return False
        try:return Decimal(str(actual)).is_finite() and abs(Decimal(str(actual))-Decimal(str(want)))<=Decimal('0.000001')
        except InvalidOperation:return False
    return actual==want
def tables(book,kind,minimal=True):
    needed=set(FIELDS[kind]);candidates=[]
    for sheet in book:
        grid=defaultdict(dict)
        for (r,c),cell in sheet['cells'].items():grid[r][c]=cell
        heads=[];all_headers=[];seen=set()
        for r,cells in grid.items():
            blocks=[];block=[];previous=None
            for c,cell in sorted(cells.items()):
                if blank(cell['value']) or cell.get('merged_from'):continue
                if previous is not None and c>previous+1:blocks.append(block);block=[]
                block.append((c,cell));previous=c
            if block:blocks.append(block)
            for block in blocks:
                if sum(ALIASES.get(canon(cell['value'])) is not None for _,cell in block)>=2:all_headers.append((r,block[0][0],block[-1][0]))
            # The whole row fallback admits genuine empty spacer columns when
            # required fields remain unique; contiguous blocks admit side-by-side tables.
            for block in blocks+[[(c,cell) for c,cell in sorted(cells.items()) if not blank(cell['value']) and not cell.get('merged_from')]]:
                by=defaultdict(list)
                for c,cell in block:
                    key=ALIASES.get(canon(cell['value']))
                    if key:by[key].append(c)
                if not needed<=set(by) or any(len(by[k])!=1 for k in needed):continue
                columns={k:by[k][0] for k in needed};signature=(r,tuple(sorted(columns.items())))
                if signature in seen:continue
                seen.add(signature);lo=min(columns.values());hi=max(columns.values());extra=sum(lo<=c<=hi for c,_ in block)-len(needed);heads.append((r,columns,extra,lo,hi))
        for r,cols,extra,lo,hi in heads:
            end=min((nr for nr,left,right in all_headers if nr>r and left<=hi and right>=lo),default=50001);rows=[]
            for rn,cells in sorted(grid.items()):
                if not r<rn<end:continue
                row={k:cells.get(c,{}).get('value') for k,c in cols.items()}
                if kind=='controls':valid=isinstance(row['control'],str) and re.fullmatch(r'[a-z][a-z0-9_]*',row['control'])
                else:valid=all(isinstance(row[k],str) and re.fullmatch({'plant_id':r'[ABC]','sku_id':r'S\d\d','material_id':r'M[12]'}[k],row[k]) for k in cols if k in {'plant_id','sku_id','material_id'})
                if not valid:continue
                row.update(_sheet=sheet['name'],_row=rn,_columns=cols,_cells={k:cells.get(c,{}) for k,c in cols.items()},_visible=all(grid[r][c].get('visible') and cells.get(c,{'visible':True}).get('visible') for c in cols.values()))
                rows.append(row)
            if rows:candidates.append((extra,rows))
    if not candidates:return []
    best=min(n for n,_ in candidates)
    return [row for n,part in candidates if not minimal or n==best for row in part]
def identity(kind,row):
    keys={'decisions':['plant_id','sku_id'],'allocations':['plant_id','sku_id'],'routes':['plant_id','sku_id'],'costs':['plant_id','sku_id'],'recipes':['sku_id','material_id']}.get(kind,['sku_id'] if kind in ['products','demand'] else ['plant_id'] if kind in ['plants','plant_results'] else ['material_id'] if kind in ['materials','material_results'] else ['control'])
    return tuple(row[k] for k in keys)
def quantities(book,source):
    rows=tables(book,'decisions');by=defaultdict(list)
    for row in rows:by[identity('allocations',row)].append(row)
    required={(r['plant_id'],r['sku_id']) for r in source['routes']}
    if set(by)!=required or any(len(v)!=1 for v in by.values()):raise CandidateError('Allocation must visibly cover exactly36 unique plant/SKU routes including zero and unavailable routes')
    result={}
    for key,part in by.items():
        row=part[0]
        if not row['_visible']:raise CandidateError('Allocation output is hidden')
        try:value=Decimal(str(row['units']))
        except InvalidOperation as exc:raise CandidateError('Non-numeric route quantity') from exc
        if isinstance(row['units'],bool) or not value.is_finite() or value!=value.to_integral_value() or abs(value)>1000000:raise CandidateError('Route quantity must be finite exact integer; never round a fraction')
        result[key]=int(value)
    return result
def raw_inventory(book,data):
    checks={}
    for kind in ['demand','plants','routes','materials','recipes','costs']:
        rows=tables(book,kind,False)
        for record in data[kind]:
            key=identity(kind,record);checks[kind+'/'+str(key)]=any(row['_visible'] and all(equal(row.get(k),record[k]) for k in FIELDS[kind]) for row in rows)
    return {'checks':checks,'complete':all(checks.values())}
def controls_for(evaluation,data):
    c=evaluation['controls'];result={MONEY_MAP_REVERSE.get(k,k):Decimal(v)/100 if k.endswith('_cents') else v for k,v in c.items()}
    result.update(all_hard_constraints_satisfied=evaluation['feasible'],total_delivered=sum(r['units'] for r in evaluation['allocations']),full_demand_total=sum(r['demand_units'] for r in data['demand']),unit_capacity_total=sum(r['unit_capacity'] for r in data['plants']))
    result['full_service_unit_bound_gap']=max(result['full_demand_total']-result['unit_capacity_total'],0)
    return result
MONEY_MAP_REVERSE={v:k for k,v in MONEY_MAP.items()}
def observed_controls(book):
    by=defaultdict(list)
    for row in tables(book,'controls'):by[row['control']].append(row)
    return by
def observe(book,evaluation,data):
    wanted={'allocations':evaluation['allocations'],'products':evaluation['products'],'plant_results':evaluation['plants'],'material_results':evaluation['materials']};checks={};counts={}
    for s in book:checks['errors/'+s['name']]=not s['errors']
    for kind,records in wanted.items():
        actual=tables(book,kind);counts[kind]=len(actual);by=defaultdict(list)
        for row in actual:by[identity(kind,row)].append(row)
        checks[kind+'/identity_set']=set(by)=={identity(kind,r) for r in records}
        for want in records:
            key=identity(kind,want);matches=by[key];prefix=kind+'/'+str(key);checks[prefix+'/unique']=len(matches)==1;row=matches[0] if len(matches)==1 else {};checks[prefix+'/visible']=bool(row.get('_visible'))
            for field in FIELDS[kind]:
                source=MONEY_MAP.get(field,field);value=Decimal(want[source])/100 if source.endswith('_cents') else want[source];checks[prefix+'/'+field]=equal(row.get(field),value)
    controls=observed_controls(book)
    for key,value in controls_for(evaluation,data).items():matches=controls[key];checks['controls/'+key]=len(matches)==1 and matches[0]['_visible'] and equal(matches[0]['value'],value)
    mean=lambda xs:sum(xs)/len(xs) if xs else 0
    return {'checks':checks,'scores':{kind:mean([v for k,v in checks.items() if k.startswith(kind+'/')]) for kind in list(wanted)+['controls']},'table_counts':counts,'complete':all(checks.values())}
def read_decision(path,evaluation,data):
    text=Path(path).read_text(encoding='utf-8-sig');checks={};facts={}
    names=list(controls_for(evaluation,data))[:11]+['certificate_kind','full_demand_units','source_file','source_locator']
    names+=['combined_supply_units','min_material_coefficient_per_item','finished_units_upper_bound','minimum_total_unmet_bound','available_factory_units','material_id','required_material_units','available_material_units','material_shortage_units']
    for key in set(names):
        found=re.findall(r'(?m)^\s*'+key+r'\s*[:：]\s*(.*?)\s*$',text);facts[key]=found[0] if len(found)==1 else None
    own=controls_for(evaluation,data)
    report_checks={key:equal(facts.get(key),value) for key,value in own.items() if key in names and key not in {'all_hard_constraints_satisfied'}}
    total=sum(r['demand_units'] for r in data['demand']);capacity=sum(p['unit_capacity'] for p in data['plants']);supply=sum(m['available_units'] for m in data['materials']);per_sku=defaultdict(int)
    for row in data['recipes']:per_sku[row['sku_id']]+=row['units_per_item']
    minimum=min(per_sku.values());kind=facts['certificate_kind'];checks['full_demand_units']=equal(facts['full_demand_units'],total);checks['source_file']=facts['source_file']=='capacity.xlsx';locator=facts['source_locator'] or ''
    if kind=='combined_material':
        upper=supply//minimum;checks.update(kind_valid=minimum>0 and total>upper,combined_supply=equal(facts['combined_supply_units'],supply),coefficient=equal(facts['min_material_coefficient_per_item'],minimum),upper=equal(facts['finished_units_upper_bound'],upper),unmet_bound=equal(facts['minimum_total_unmet_bound'],max(total-upper,0)),source_locator=all(k in locator for k in ['M1','M2','S01','S12']) and any(k in locator for k in ['单件耗料','recipes','配方']))
    elif kind=='factory_units':checks.update(kind_valid=total>capacity,available=equal(facts['available_factory_units'],capacity),unmet_bound=equal(facts['minimum_total_unmet_bound'],max(total-capacity,0)),source_locator=all(k in locator for k in ['A','B','C']) and any(k in locator for k in ['工厂','plants']))
    elif kind=='material_requirement':
        material=next((r for r in data['materials'] if r['material_id']==facts['material_id']),None);recipe={r['sku_id']:r['units_per_item'] for r in data['recipes'] if r['material_id']==facts['material_id']}
        if material and len(recipe)==12:
            required=sum(r['demand_units']*recipe[r['sku_id']] for r in data['demand']);available=material['available_units'];checks.update(kind_valid=required>available,required=equal(facts['required_material_units'],required),available=equal(facts['available_material_units'],available),shortage=equal(facts['material_shortage_units'],required-available),source_locator=facts['material_id'] in locator and all(k in locator for k in ['S01','S12']) and any(k in locator for k in ['单件耗料','recipes','配方']))
        else:checks['kind_valid']=False
    else:checks['kind_valid']=False
    sources=all(n in text for n in ['demand.csv','capacity.xlsx','costs.csv','constraints.md']);mean=lambda xs:sum(xs)/len(xs) if xs else 0
    return {'facts':facts,'report_checks':report_checks,'certificate_checks':checks,'report_score':mean(list(report_checks.values())),'certificate_score':float(all(checks.values())),'sources_named':sources,'complete':all(report_checks.values()) and all(checks.values()) and sources,'limit':'Verifies the plan-disclosed amounts, one source-derived full-demand impossibility certificate and named sources. Free prose, solver claims and mathematical proof of cost optimality are not inferred from keywords.'}
