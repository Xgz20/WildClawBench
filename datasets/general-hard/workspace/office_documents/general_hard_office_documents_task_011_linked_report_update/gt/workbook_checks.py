"""Resolve business tables by native labels, then test actual formulas with Office."""
from decimal import Decimal as D
import re

METRICS=['REV','COGS','OPEX','OCF','AR']
GROUP=['REV','COGS','GP','OPEX','OP','OCF','AR','GP_MARGIN','OP_MARGIN','OCF_REV']
COMP=['REV_YOY','GP_YOY','OP_YOY','AR_YOY','OCF_DIFF']
def tables(book,io):
    schemas={
      'raw':({'fact_id':['fact_id','事实ID'],'year':['year','年份'],'month':['month','月份'],'period':['period','期间'],**{m:[m] for m in METRICS}},'period',r'202[56]-0[1-9]'),
      'group':({'group_id':['group_id','分组ID'],**{m:[m] for m in GROUP}},'group_id',r'202[56]-(?:Q[123]|YTD)'),
      'compare':({'period_id':['period_id','比较期间'],**{m:[m] for m in COMP}},'period_id',r'Q[123]|YTD')}
    return {k:io['logical_rows'](book,*v) for k,v in schemas.items()}
def node_cells(table_set,truth):
    out={}
    for identity in truth['source_nodes']:
        kind,row,metric=identity.split('/');record=table_set[kind]['rows'].get(row)
        out[identity]=record['cells'].get(metric) if record else None
    return out
def business(values):
    groups={};comp={}
    for year in [2025,2026]:
        for q in [1,2,3,0]:
            tag=f'Q{q}' if q else 'YTD';months=range((q-1)*3+1,q*3+1) if q else range(1,10)
            periods=[f'{year}-{m:02}' for m in months]
            v={m:sum((values[f'raw/{p}/{m}'] for p in periods),D(0)) if m!='AR' else values[f'raw/{periods[-1]}/{m}'] for m in METRICS}
            v['GP']=v['REV']-v['COGS'];v['OP']=v['GP']-v['OPEX'];v.update(GP_MARGIN=v['GP']/v['REV'],OP_MARGIN=v['OP']/v['REV'],OCF_REV=v['OCF']/v['REV'])
            groups[f'{year}-{tag}']=v
    for tag in ['Q1','Q2','Q3','YTD']:
        a,b=groups['2025-'+tag],groups['2026-'+tag];comp[tag]={m+'_YOY':b[m]/a[m]-1 for m in ['REV','GP','OP','AR']};comp[tag]['OCF_DIFF']=b['OCF']-a['OCF']
    return {**values,**{f'group/{g}/{m}':v for g,r in groups.items() for m,v in r.items()},**{f'compare/{g}/{m}':v for g,r in comp.items() for m,v in r.items()}}
def baseline(original,calculated,truth,contract,io):
    raw_tables=tables(original,io);calc_tables=tables(calculated,io);cells=node_cells(raw_tables,truth);calc=node_cells(calc_tables,truth)
    checks={};observations={};formulas={}
    for identity,node in truth['source_nodes'].items():
        cell=cells.get(identity);actual=calc.get(identity);wanted=truth['corrected_model']['nodes'][identity]['value']
        numeric=bool(cell and actual and actual.get('type')=='n' and io['match'](actual['value'],wanted,str(max(D('1e-8'),abs(D(wanted))*D('1e-12')))))
        if node['kind']=='source':numeric=numeric and cell.get('type')=='n' and 'formula' not in cell
        else:formulas[identity]=bool(cell and str(cell.get('formula','')).strip())
        checks[identity]=numeric
        if cell:observations[identity]={'file':contract['files']['workbook'],'locator':cell['locator'],'value':actual.get('value') if actual else None,
            'unit':'ratio' if any(x in identity for x in ['MARGIN','_YOY','OCF_REV']) else 'CNY','formula':cell.get('formula')}
    scope={}
    scope_table=io['logical_rows'](original,{'item':['项目'],'content':['内容或数值'],'note':['口径说明']},'item',r'.+')
    for name,row in scope_table['rows'].items():
        if row:scope[name]=[(row['cells'].get('content') or {}).get('value')]
    protected_scope={k:len(scope.get(k,[]))==1 and io['canon'](scope[k][0])==io['canon'](v) for k,v in contract['scope_values'].items()}
    identities=all(set(raw_tables[k]['rows'])==set(calc_tables[k]['rows']) for k in raw_tables)
    identity_rows={}
    for year in [2025,2026]:
        for month in range(1,10):
            row=raw_tables['raw']['rows'].get(f'{year}-{month:02}')
            value=lambda k:(row['cells'].get(k) or {}).get('value') if row else None
            identity_rows[f'{year}-{month:02}']=bool(row and io['clean'](value('fact_id'))==f'F{year}-{month:02}' and io['number'](value('year'))==year and io['number'](value('month'))==month)
    return {'checks':checks,'observations':observations,'formula_presence':formulas,'cells':cells,'table_origins':{k:v['origins'] for k,v in raw_tables.items()},
        'scope':protected_scope,'identities':identity_rows,'table_consistency':identities,'duplicate_ids':{k:v['duplicates'] for k,v in raw_tables.items()}}
def probe_cases(truth):
    values={k:D(v['value']) for k,v in truth['corrected_model']['nodes'].items() if k.startswith('raw/')}
    drivers={e['source_node']:values[e['source_node']]+D(delta) for e,delta in zip(truth['corrections'],[19003,-17011,13007,23009,33000,-7001,-11003,9001])}
    all_months={k:v+D((i+1)*131-4000) for i,(k,v) in enumerate(sorted(values.items()))}
    boundary={'raw/2026-06/OCF':values['raw/2026-06/OCF']+30000,'raw/2026-02/AR':D(99000000),
        'raw/2026-04/AR':D(88000000),'raw/2026-08/AR':D(77000000),'raw/2026-09/AR':D(0)}
    return [('approved_drivers',drivers),('all_monthly_inputs',all_months),('zero_cash_and_balance_snapshot',boundary)]
def responses(source,lock,derived,base,truth,contract,io):
    baseline_values={k:D(v['value']) for k,v in truth['corrected_model']['nodes'].items() if k.startswith('raw/')};wanted_base=business(baseline_values);out=[]
    if not all(base['cells'].get(k) for k in baseline_values):return {'cases':[],'score':0.,'reason':'source table incomplete'}
    if not all(base['cells'][k].get('type')=='n' and 'formula' not in base['cells'][k] and io['number'](base['cells'][k].get('value')) is not None for k in baseline_values):
        return {'cases':[],'score':0.,'reason':'source fields must remain literal native numeric inputs'}
    if not all(base['formula_presence'].values()):return {'cases':[],'score':0.,'reason':'formula outputs incomplete'}
    for tag,changes in probe_cases(truth):
        edits=[{'sheet':base['cells'][k]['sheet'],'cell':base['cells'][k]['cell'],'value':str(v)} for k,v in changes.items()]
        variant=io['OFFICE']['prepare_xlsx_counterfactual'](source,edits,derived/tag/'variant')
        result=io['OFFICE']['recalculate_xlsx'](variant['path'],lock,derived/tag/'calculated')
        observed=node_cells(tables(io['workbook'](result['path']),io),truth);expected=business({**baseline_values,**changes})
        checks={k:bool(observed[k] and io['match'](observed[k]['value'],v,str(max(D('1e-8'),abs(v)*D('1e-12'))))) for k,v in expected.items() if truth['source_nodes'][k]['kind']=='formula'}
        affected=[k for k in checks if abs(expected[k]-wanted_base[k])>D('1e-10')];stable=[k for k in checks if k not in affected]
        out.append({'case':tag,'changed_source_nodes':list(changes),'affected_formula_nodes':affected,'checks':checks,
            'affected_score':io['mean'](checks[k] for k in affected),'stable_score':io['mean'](checks[k] for k in stable) if stable else 1.,
            'variant':variant,'recalculation':result})
    return {'cases':out,'score':io['mean'](r['affected_score']*r['stable_score'] for r in out),
        'covered_changed_formula_nodes':sorted({k for r in out for k in r['affected_formula_nodes']})}
