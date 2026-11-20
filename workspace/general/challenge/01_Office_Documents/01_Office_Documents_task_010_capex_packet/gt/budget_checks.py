"""Source-faithful native budget checks and independently computed input responses."""
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP,localcontext

D=Decimal
def rounded(value):
    with localcontext() as context:
        context.prec=100
        return value.quantize(D('.01'),rounding=ROUND_HALF_UP)
def table_set(book,contract,io):
    return {kind:io['logical_table'](book,headers,{'lines':'line_id','phases':'phase','options':'option_id'}[kind],
        {'lines':r'P[0-9]+-(?:CL|FAN)','phases':r'P[0-9]+','options':r'.{1,64}'}[kind]) for kind,headers in contract['tables'].items()}
def choice_of(tables,ids,io):
    return {identity:io['clean']((tables['lines']['rows'].get(identity) or {}).get('values',{}).get('vendor')).upper() for identity in ids}
def bool_value(v):
    if isinstance(v,bool):return v
    if str(v).casefold() in {'1','true','是','有效','可用'}:return True
    if str(v).casefold() in {'0','false','否','无效','不可用'}:return False
    return None

def baseline_checks(tables,expected,oracle,contract,io):
    ids=contract['line_ids'];choice=choice_of(tables,ids,io);identity=''.join(choice.values())
    case=next((c for c in expected['all_options'] if c['option_id']==identity),None)
    source_checks={};line_checks={};phase_checks={};phase_components={}
    for line_id in ids:
        p,e=line_id.split('-');vendor=choice[line_id];q=expected['quotes'].get(vendor,{}).get(e)
        row=tables['lines']['rows'].get(line_id);values=row['values'] if row else {}
        wanted={'phase':p,'equipment':e,'quantity':expected['phases'][p]['quantities'][e]}
        if q:
            wanted.update(threshold=q['threshold'],unit_low=q['low'],unit_high=q['high'],
                equipment_tax_factor='1.13' if expected['quotes'][vendor]['equipment_tax_basis']=='exclusive' else '1',
                installation_unit=q['installation_net'],installation_tax_factor='1.06',
                maintenance_unit=oracle['financial_basis']['maintenance_net'][e],maintenance_tax_factor='1.06',crew_days_per_unit=q['crew_days_per_unit'])
        checks={k:io['clean'](values.get(k)).upper()==v if k in {'phase','equipment'} else
            bool(row and io['numeric_cell'](row['cells'].get(k)) and io['match'](values.get(k),v)) for k,v in wanted.items()}
        source_checks[line_id]={'checks':checks,'pass':bool(q and all(checks.values()))}
        group=case['phases'][p]['groups'][e] if case else None
        line_checks[line_id]=bool(row and group and all(io['numeric_cell'](row['cells'].get(k)) and io['match'](values.get(k),group[k]) for k in ['equipment_gross','installation_gross','maintenance_gross','crew_days']))
    for p in ['P1','P2']:
        row=tables['phases']['rows'].get(p);values=row['values'] if row else {};wanted={}
        if case:
            wanted={k:case['phases'][p][k] for k in ['equipment_gross','installation_gross','freight_gross','contingency','capex','maintenance_gross','other_opex','opex','total_cash']}
            wanted.update(freight_a='1200',freight_b='1000',freight_c='800',contingency_rate='.05',
                capex_limit=expected['phases'][p]['capex_limit'],opex_limit=expected['phases'][p]['opex_limit'],
                capex_headroom=D(expected['phases'][p]['capex_limit'])-D(case['phases'][p]['capex']),
                opex_headroom=D(expected['phases'][p]['opex_limit'])-D(case['phases'][p]['opex']))
        checks={k:bool(row and io['numeric_cell'](row['cells'].get(k)) and io['match'](values.get(k),v)) for k,v in wanted.items()}
        phase_components[p]=checks;phase_checks[p]=bool(checks and all(checks.values()))
    options=[];seen_choices=set()
    for row in tables['options']['rows'].values():
        if not row:options.append(False);continue
        values=row['values'];selection=''.join(io['clean'](values.get(k)).upper() for k in ['p1_cl','p1_fan','p2_cl','p2_fan'])
        truth=next((c for c in expected['all_options'] if c['option_id']==selection),None)
        amounts={f'{p.lower()}_{kind}':truth['phases'][p][kind] for p in ['P1','P2'] for kind in ['capex','opex']} if truth else {}
        if truth:amounts['total_cash']=truth['total_cash']
        good=bool(truth and all(io['numeric_cell'](row['cells'].get(k)) and io['match'](values.get(k),v) for k,v in amounts.items())
            and bool_value(values.get('eligible')) is truth['eligible'] and io['clean'](values.get('reason')))
        options.append(good)
        if good and truth['eligible']:seen_choices.add(selection)
    coverage=[identity in seen_choices,bool(seen_choices-{identity})]
    option_score=.7*io['mean'](options)+.3*io['mean'](coverage)
    minimum=identity==expected['recommended']['option_id']
    quote_checks={line_id:bool(choice[line_id] in expected['quotes'] and expected['quotes'][choice[line_id]]['valid_through']>=expected['phases'][line_id.split('-')[0]]['order_date']) for line_id in ids}
    return {'choice':choice,'case_id':identity,'case':case,'source_checks':source_checks,'line_checks':line_checks,
        'phase_checks':phase_checks,'phase_components':phase_components,'option_checks':options,'option_coverage':coverage,
        'option_score':option_score,'minimum_selection':minimum,'quote_checks':quote_checks}

def model(tables,original,oracle,io,overrides=None):
    overrides=overrides or {};outputs={};line_values={};phase_values={}
    def val(row,k):
        if not row:return None
        cell=row['cells'].get(k);leaf=io['driver'](original,cell)
        for locator in ([leaf['locator']] if leaf else [])+([cell['locator']] if cell else []):
            if locator in overrides:return D(str(overrides[locator]))
        return io['number'](row['values'].get(k))
    for identity,row in tables['lines']['rows'].items():
        if not row:continue
        keys=['quantity','threshold','unit_low','unit_high','equipment_tax_factor','installation_unit','installation_tax_factor','maintenance_unit','maintenance_tax_factor','crew_days_per_unit']
        v={k:val(row,k) for k in keys}
        if any(x is None or x<0 for x in v.values()):continue
        q=v['quantity'];unit=v['unit_high'] if q>=v['threshold'] else v['unit_low']
        values={'equipment_gross':rounded(q*unit*v['equipment_tax_factor']),
            'installation_gross':rounded(q*v['installation_unit']*v['installation_tax_factor']),
            'maintenance_gross':rounded(q*v['maintenance_unit']*v['maintenance_tax_factor']),
            'crew_days':q*v['crew_days_per_unit']}
        line_values[identity]=values
        for k,value in values.items():outputs[f'lines/{identity}/{k}']=value
    for p in ['P1','P2']:
        row=tables['phases']['rows'].get(p);groups=[p+'-CL',p+'-FAN']
        if not row or any(identity not in line_values for identity in groups):continue
        eq=sum(line_values[id]['equipment_gross'] for id in groups);install=sum(line_values[id]['installation_gross'] for id in groups)
        maintenance=sum(line_values[id]['maintenance_gross'] for id in groups)
        vendors={io['clean'](tables['lines']['rows'][id]['values']['vendor']).upper() for id in groups}
        if not vendors<={'A','B','C'}:continue
        rates={v:val(row,'freight_'+v.lower()) for v in vendors};reserve_rate=val(row,'contingency_rate')
        other=val(row,'other_opex');caps={k:val(row,k+'_limit') for k in ['capex','opex']}
        if any(v is None for v in [*rates.values(),reserve_rate,other,*caps.values()]):continue
        freight=sum(rates.values());reserve=rounded((eq+install+freight)*reserve_rate)
        capex=eq+install+freight+reserve;opex=maintenance+other
        values={'equipment_gross':eq,'installation_gross':install,'freight_gross':freight,'contingency':reserve,
            'capex':capex,'maintenance_gross':maintenance,'opex':opex,'total_cash':capex+opex,
            'capex_headroom':caps['capex']-capex,'opex_headroom':caps['opex']-opex}
        phase_values[p]=values
        for k,value in values.items():outputs[f'phases/{p}/{k}']=value
    return outputs

def responses(source,original,tables,expected,oracle,contract,io,lock,derived):
    baseline=model(tables,original,oracle,io);ids=contract['line_ids'];tests=[]
    observed_baseline={}
    for label in baseline:
        typ,identity,field=label.split('/')
        observed_baseline[label]=(tables[typ]['rows'].get(identity) or {}).get('values',{}).get(field)
    proposals=[('p1_quantity_tier','lines','P1-CL','quantity',D(2)),('p2_quantity_tier','lines','P2-FAN','quantity',D(2)),
        ('equipment_tax','lines','P1-FAN','equipment_tax_factor',None),('maintenance_rate','lines','P2-CL','maintenance_unit',None),
        ('price_tier_threshold','lines','P1-CL','threshold',None),('equipment_unit_price','lines','P2-CL','unit_low',None),
        ('installation_rate','lines','P1-CL','installation_unit',None),('installation_tax','lines','P2-CL','installation_tax_factor',None),
        ('maintenance_tax','lines','P2-FAN','maintenance_tax_factor',None),
        ('contingency_rounding','phases','P2','contingency_rate',None)]
    phase=tables['phases']['rows'].get('P1');vendors=[io['clean']((tables['lines']['rows'].get(id) or {}).get('values',{}).get('vendor')).upper() for id in ids[:2]]
    vendors=sorted(set(v for v in vendors if v in 'ABC' and v))
    proposals.append(('phase_freight','phases','P1','freight_'+vendors[0].lower() if vendors else 'freight_a',None))
    for name,kind,identity,field,new in proposals:
        row=tables[kind]['rows'].get(identity);cell=row['cells'].get(field) if row else None;leaf=io['driver'](original,cell)
        current=io['number'](cell.get('value')) if cell else None
        if new is None and current is not None:new=current+({'equipment_tax_factor':D('.01'),'maintenance_unit':D(50),'contingency_rate':D('.025'),
            'threshold':D(1),'unit_low':D('123.45'),'installation_unit':D('37.25'),'installation_tax_factor':D('.01'),'maintenance_tax_factor':D('.01')}.get(field,D(200)))
        if leaf is None or new is None:
            tests.append({'name':name,'pass':False,'reason':'no observable editable numeric input'});continue
        changes=[{'sheet':leaf['sheet'],'cell':leaf['cell'],'value':str(new)}]
        wanted=model(tables,original,oracle,io,{leaf['locator']:new})
        changed={k:v for k,v in wanted.items() if k in baseline and v!=baseline[k]}
        if not changed:
            tests.append({'name':name,'pass':False,'reason':'no independently expected output response'});continue
        variant=io['OFFICE']['prepare_xlsx_counterfactual'](source,changes,derived/name/'variant')
        result=io['OFFICE']['recalculate_xlsx'](variant['path'],lock,derived/name/'calculated')
        observed=table_set(io['workbook'](result['path']),contract,io);checks={}
        for label,value in wanted.items():
            typ,id,k=label.split('/');actual=(observed[typ]['rows'].get(id) or {}).get('values',{}).get(k)
            # Isolate the response from unrelated baseline errors, which the
            # independent financial oracle scores separately.
            checks[label]=io['match'](actual,value if label in changed else observed_baseline.get(label))
        tests.append({'name':name,'pass':bool(changed and all(checks.get(k,False) for k in changed) and all(checks.values())),
            'changes':changes,'expected_changed':changed,'checks':checks,'original_source_sha256':variant['audit']['source_sha256']})
    return tests
