"""Synthetic PV decision and quote rules from native-source inputs, not real engineering advice."""
from decimal import Decimal,ROUND_CEILING,ROUND_HALF_UP,localcontext
from fractions import Fraction
def decimal_quote(site,option,p):
    D=lambda v:Decimal(str(v));up=lambda v:int(v.to_integral_value(rounding=ROUND_CEILING));cent=lambda v:v.quantize(D('.01'),rounding=ROUND_HALF_UP)
    n=up(D(site['annual_target_kwh'])/(D(option['module_kwp'])*D(site['yield_kwh_kwp'])*D(option['performance_factor'])*D(site['shading_factor'])))
    kw=D(n)*D(option['module_kwp']);area=D(n)*D(option['module_area_m2']);inverters=up(kw/D(p['inverter_block_kwp']))
    replacement=D(site['usable_area_m2']) if option['requires_replacement'] else D(0)
    values={'module_count':D(n),'dc_kwp':kw,'area_m2':area,'design_load_kg_m2':D(option['load_'+site['roof_type']+'_kg_m2']),
        'annual_energy_kwh':kw*D(site['yield_kwh_kwp'])*D(option['performance_factor'])*D(site['shading_factor']),
        'inverter_count':D(inverters),'replacement_area_m2':replacement,
        'cost_module':D(n)*D(option['module_price_ex_vat']),'cost_inverter':D(inverters)*D(p['inverter_unit_ex_vat']),
        'cost_cable':D(n)*D(p['cable_per_module_ex_vat']),'cost_isolation':D(p['isolation_per_site_ex_vat']),
        'cost_mounting':area*D(option['mount_'+site['roof_type']+'_cny_m2']),'cost_installation':kw*D(option['installation_cny_kwp']),
        'cost_replacement':replacement*D(p['replacement_roof_cny_m2']),'cost_drainage':replacement*D(p['drainage_cny_m2']),
        'cost_design':D(p['design_per_site_ex_vat']),'cost_inspection':D(p['inspection_per_site_ex_vat']),
        'cost_adhesion':D(p['adhesion_acceptance_ex_vat']) if option['adhesion_required'] else D(0),
        'cost_corrosion':D(p['corrosion_review_ex_vat']) if site['corrosion_evidence']!='not_required' else D(0)}
    values['subtotal_goods']=sum(values[k] for k in ['cost_module','cost_inverter','cost_cable','cost_isolation'])
    values['subtotal_construction']=sum(values[k] for k in ['cost_mounting','cost_installation','cost_replacement','cost_drainage'])
    values['subtotal_services']=sum(values[k] for k in ['cost_design','cost_inspection','cost_adhesion','cost_corrosion'])
    for group in ['goods','construction','services']:values['tax_'+group]=cent(values['subtotal_'+group]*D(p['vat_'+group]))
    values['gross_total']=sum(values[k] for k in ['subtotal_goods','subtotal_construction','subtotal_services','tax_goods','tax_construction','tax_services'])
    values['budget_margin']=D(site['budget_gross_cny'])-values['gross_total']
    return values
def fraction_quote(site,option,p):
    """Separate rational path with a different cost grouping and integer rounding implementation."""
    F=lambda v:Fraction(str(v));ceil=lambda f:-(-f.numerator//f.denominator)
    count=ceil(F(site['annual_target_kwh'])/F(site['yield_kwh_kwp'])/F(site['shading_factor'])/F(option['performance_factor'])/F(option['module_kwp']))
    physical={'module_count':F(count),'dc_kwp':F(option['module_kwp'])*count,'area_m2':F(option['module_area_m2'])*count}
    physical['annual_energy_kwh']=physical['dc_kwp']*F(option['performance_factor'])*F(site['shading_factor'])*F(site['yield_kwh_kwp'])
    physical['inverter_count']=F(ceil(physical['dc_kwp']/F(p['inverter_block_kwp'])))
    physical['design_load_kg_m2']=F(option[{'flat':'load_flat_kg_m2','metal':'load_metal_kg_m2'}[site['roof_type']]])
    physical['replacement_area_m2']=F(site['usable_area_m2']) if option['requires_replacement'] else F(0)
    goods={'module':F(option['module_price_ex_vat'])*count,'inverter':F(p['inverter_unit_ex_vat'])*physical['inverter_count'],
        'cable':F(p['cable_per_module_ex_vat'])*count,'isolation':F(p['isolation_per_site_ex_vat'])}
    construction={'mounting':F(option['mount_flat_cny_m2'] if site['roof_type']=='flat' else option['mount_metal_cny_m2'])*physical['area_m2'],
        'installation':F(option['installation_cny_kwp'])*physical['dc_kwp'],
        'replacement':F(p['replacement_roof_cny_m2'])*physical['replacement_area_m2'],'drainage':F(p['drainage_cny_m2'])*physical['replacement_area_m2']}
    services={'design':F(p['design_per_site_ex_vat']),'inspection':F(p['inspection_per_site_ex_vat']),
        'adhesion':F(p['adhesion_acceptance_ex_vat'])*int(option['adhesion_required']),
        'corrosion':F(p['corrosion_review_ex_vat'])*int(site['corrosion_evidence']!='not_required')}
    result=dict(physical)
    for group,items in [('goods',goods),('construction',construction),('services',services)]:
        result.update({'cost_'+key:value for key,value in items.items()});subtotal=sum(items.values());tax=subtotal*F(p['vat_'+group])
        cents=tax*100;rounded=(cents.numerator*2+cents.denominator)//(2*cents.denominator)
        result['subtotal_'+group]=subtotal;result['tax_'+group]=Fraction(rounded,100)
    result['gross_total']=sum(result['subtotal_'+g]+result['tax_'+g] for g in ['goods','construction','services'])
    result['budget_margin']=F(site['budget_gross_cny'])-result['gross_total'];return result
def check_matrix(site,option,v):
    def check(value,limit,ok,unknown=False,applicable=True):return {'status':'not_applicable' if not applicable else 'unknown' if unknown else 'pass' if ok else 'fail','observed':value,'limit':limit}
    checks={'AREA':check(v['area_m2'],site['usable_area_m2'],v['area_m2']<=Decimal(str(site['usable_area_m2']))),
      'LOAD':check(v['design_load_kg_m2'],site['verified_load_kg_m2'],False if site['load_status']!='verified' else v['design_load_kg_m2']<=Decimal(str(site['verified_load_kg_m2'])),unknown=site['load_status']!='verified'),
      'GRID':check(v['dc_kwp'],site['max_dc_kwp'],v['dc_kwp']<=Decimal(str(site['max_dc_kwp']))),
      'REPLACEMENT':check(site['replacement_allowed'],True,site['replacement_allowed'] is True,applicable=option['requires_replacement']),
      'BUDGET':check(v['gross_total'],site['budget_gross_cny'],v['budget_margin']>=0),
      'ADHESION':check(site['adhesion_evidence'],'verified',site['adhesion_evidence']=='verified',unknown=site['adhesion_evidence']=='unverified',applicable=option['adhesion_required']),
      'CORROSION':check(site['corrosion_evidence'],'verified',site['corrosion_evidence']=='verified',unknown=site['corrosion_evidence']=='unverified',applicable=site['corrosion_evidence']!='not_required'),
      'REPAIR_SCOPE':check(site['roof_repair_cost'],'confirmed_scope_and_cost',site['roof_repair_cost'] is not None,unknown=site['roof_repair_cost'] is None,applicable=site['roof_repair_cost']!='not_required')}
    states={c['status'] for c in checks.values()};status='infeasible' if 'fail' in states else 'conditional' if 'unknown' in states else 'feasible'
    return status,checks
def solve(inputs):
    cases={};recommendations={};exceptions=[]
    for site in inputs['sites']:
        for option in inputs['options']:
            v=decimal_quote(site,option,inputs['parameters']);independent=fraction_quote(site,option,inputs['parameters'])
            assert set(v)==set(independent)
            for key,value in v.items():assert Fraction(value)==independent[key],(site['site_id'],option['option_id'],key,value,independent[key])
            n=int(v['module_count']);step=Decimal(str(option['module_kwp']))*Decimal(str(site['yield_kwh_kwp']))*Decimal(str(option['performance_factor']))*Decimal(str(site['shading_factor']))
            assert v['annual_energy_kwh']>=Decimal(str(site['annual_target_kwh'])) and (n-1)*step<Decimal(str(site['annual_target_kwh']))
            status,checks=check_matrix(site,option,v);identity=site['site_id']+'-'+option['option_id'];cases[identity]={'site_id':site['site_id'],'option_id':option['option_id'],'status':status,'values':v,'checks':checks}
            for rule,row in checks.items():
                if row['status'] in {'fail','unknown'}:exceptions.append({'site_id':site['site_id'],'option_id':option['option_id'],'rule_id':rule,**row})
        rows=[c for c in cases.values() if c['site_id']==site['site_id']];eligible=[c for c in rows if c['status']=='feasible'] or [c for c in rows if c['status']=='conditional']
        choice=min(eligible,key=lambda c:(c['values']['gross_total'],c['option_id'])) if eligible else None
        recommendations[site['site_id']]={'option_id':choice['option_id'] if choice else None,'status':choice['status'] if choice else 'no_recommendation','pair':site['site_id']+'-'+choice['option_id'] if choice else None}
    return {'cases':cases,'recommendations':recommendations,'exceptions':exceptions}
