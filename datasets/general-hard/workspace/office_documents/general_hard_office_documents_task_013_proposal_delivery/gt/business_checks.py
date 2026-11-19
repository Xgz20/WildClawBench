"""Independent oracle comparisons and actual native-source perturbations for H013."""
from decimal import Decimal
from pathlib import Path
from collections import defaultdict
import copy,json,re
def all_values(entries,wanted,io,contract,*,kind='numeric'):
    if not entries:return False
    if kind=='status':return all(io['state'](e['value'],contract)==wanted for e in entries)
    if kind=='check':return all(io['canon'](e['value']) in {io['canon'](v) for v in contract['check_aliases'][wanted]} for e in entries)
    return all(io['scalar_ok'](e['value'],wanted,contract['numeric_tolerance']) for e in entries)
def values(observed,truth,contract,io,fields=None):
    rows={}
    for pair,c in truth['cases'].items():
        actual=observed['metrics'].get(pair,{})
        rows[pair]={k:all_values(actual.get(k),c['values'][k],io,contract) for k in (fields or c['values'])}
        for field in set(rows[pair])&set(contract['integer_fields']):
            rows[pair][field] &= bool(actual.get(field)) and all(io['number'](e['value']) is not None and io['number'](e['value'])==Decimal(c['values'][field]) for e in actual[field])
    return rows
def states(observed,truth,contract,io):
    rows={}
    for pair,c in truth['cases'].items():
        actual=observed['metrics'].get(pair,{})
        rows[pair]={k:all_values(actual.get(k),v['status'],io,contract,kind='check') for k,v in c['checks'].items()}
        rows[pair]['status']=all_values(actual.get('status'),c['status'],io,contract,kind='status')
    return rows
def recommendations(actual,truth,contract,io):
    out={}
    for site,reco in truth['recommendations'].items():
        row=actual.get(site,{})
        out[site]={'option':all_values(row.get('selected_option'),reco['option_id'],io,contract,kind='scalar'),
            'status':all_values(row.get('status'),reco['status'],io,contract,kind='status')}
        for key in ['gross_total','budget_margin']:out[site][key]=all_values(row.get(key),truth['cases'][reco['pair']]['values'][key],io,contract)
    return out
def source_records(truth,contract):
    records={}
    for kind,plural in [('site','sites'),('option','options')]:
        for row in truth['inputs'][plural]:
            identity=kind+':'+row[kind+'_id']
            for field in contract['source_fields_by_kind'][kind]:records[(identity,field)]=row[field]
    for name,value in truth['inputs']['parameters'].items():records[('parameter:'+name,'value')]=value
    return records
def source_checks(observed,truth,contract,io):
    checks={};owners={}
    for (identity,field),wanted in source_records(truth,contract).items():
        entries=observed['sources'].get(identity,{}).get(field,[]);numeric=not isinstance(wanted,bool) and io['number'](wanted) is not None
        literal={ (e.get('sheet'),e.get('cell')):e for e in entries if e.get('type')=='n' and not e.get('formula') and e.get('sheet') and e.get('cell')}
        checks[identity+'/'+field]={'values':all_values(entries,wanted,io,contract,kind='scalar'),'numeric_input':not numeric or bool(literal)}
        owners[(identity,field)]=list(literal.values()) if checks[identity+'/'+field]['values'] else []
    return checks,owners
def response_plan(truth):
    plans=[('price_and_tax',[('option:A','module_price_ex_vat','1037'),('parameter:vat_services','value','.075'),('parameter:drainage_cny_m2','value','47')]),
        ('ceiling_grid_and_area',[('site:S1','annual_target_kwh','79000')]),
        ('budget_and_load',[('site:S1','budget_gross_cny','500000'),('site:S2','verified_load_kg_m2','30'),('site:S3','budget_gross_cny','175000')])]
    all_changes=[]
    for s in truth['inputs']['sites']:
        for k in ['usable_area_m2','verified_load_kg_m2','max_dc_kwp','annual_target_kwh','yield_kwh_kwp','shading_factor','budget_gross_cny']:
            if s[k] is None:continue
            delta=Decimal('-.05') if k=='shading_factor' else Decimal('1.5') if k=='max_dc_kwp' else Decimal(177) if k=='annual_target_kwh' else Decimal(1234) if k=='budget_gross_cny' else Decimal(7)
            all_changes.append(('site:'+s['site_id'],k,str(Decimal(s[k])+delta)))
    for o in truth['inputs']['options']:
        for k in ['module_kwp','module_area_m2','performance_factor','load_metal_kg_m2','load_flat_kg_m2','module_price_ex_vat','mount_metal_cny_m2','mount_flat_cny_m2','installation_cny_kwp']:
            delta=Decimal('.05') if k=='module_kwp' else Decimal('.1') if k=='module_area_m2' else Decimal('-.02') if k=='performance_factor' else Decimal(1) if k.startswith('load_') else Decimal(37)
            all_changes.append(('option:'+o['option_id'],k,str(Decimal(o[k])+delta)))
    for k,value in truth['inputs']['parameters'].items():
        new=Decimal(value)+Decimal('.02') if k.startswith('vat_') else Decimal(11) if k=='inverter_block_kwp' else Decimal(value)+137
        all_changes.append(('parameter:'+k,'value',str(new)))
    return plans+[('all_numeric_drivers',all_changes)]
def responses(source,original,truth,contract,io,model,lock,derived):
    source_checks_,owners=source_checks(original,truth,contract,io);office=io['OFFICE'];results=[];covered=set();expected_coverage=set()
    full_numeric=source_records(truth,contract)
    for name,logical in response_plan(truth):
        # Keep duplicate source literals coherent; split whole logical facts into <=100-cell variants.
        batches=[];current=[];size=0
        for identity,field,value in logical:
            cells=owners.get((identity,field),[])
            if not cells:continue
            if len(cells)>100:continue
            if size+len(cells)>100:batches.append(current);current=[];size=0
            current.append((identity,field,value,cells));size+=len(cells)
        if current:batches.append(current)
        for part,batch in enumerate(batches,1):
            inputs=copy.deepcopy(truth['inputs']);changes=[]
            for identity,field,value,cells in batch:
                kind,key=identity.split(':',1)
                if kind=='parameter':inputs['parameters'][key]=value
                else:next(r for r in inputs['sites' if kind=='site' else 'options'] if r[kind+'_id']==key)[field]=value
                changes.extend({'sheet':c['sheet'],'cell':c['cell'],'value':value} for c in cells)
            expected=model['solve'](inputs);case_dir=derived/(name+'-'+str(part))
            prepared=office['prepare_xlsx_counterfactual'](source,changes,case_dir/'prepared')
            office['verify_xlsx_counterfactual'](source,prepared['path'],prepared['audit'])
            recalc=office['recalculate_xlsx'](prepared['path'],lock,case_dir/'recalculated',timeout_seconds=90)
            actual=io['observe'](io['grids'](io['workbook'](recalc['path'])),contract)
            numeric=values(actual,expected,contract,io);constraints=states(actual,expected,contract,io)
            changed=[]
            for pair,c in expected['cases'].items():
                for field,value in c['values'].items():
                    if abs(Decimal(value)-Decimal(truth['cases'][pair]['values'][field]))>Decimal('.000001'):
                        changed.append(pair+'/'+field)
                        if numeric[pair][field]:covered.add(pair+'/'+field)
            results.append({'name':name,'part':part,'logical_fields':[(i,f,v) for i,f,v,_ in batch],'prepared':prepared,'recalculated':recalc,
                'numeric_checks':numeric,'constraint_checks':constraints,'changed_numeric_nodes':changed,
                'score':io['mean']([io['mean'](io['mean'](v.values()) for v in numeric.values()),io['mean'](io['mean'](v.values()) for v in constraints.values())])})
    # Fixed inapplicable zeros need no numeric-input change; all nonzero computational nodes do.
    expected_coverage={pair+'/'+field for pair,c in truth['cases'].items() for field,value in c['values'].items() if Decimal(value)!=0}
    quality=io['mean'](r['score'] for r in results)
    coverage=len(covered&expected_coverage)/len(expected_coverage)
    return {'score':quality*coverage,'quality':quality,'coverage':coverage,'required_nonzero_nodes':len(expected_coverage),'covered_nonzero_nodes':len(covered&expected_coverage),
        'cases':results,'limit':'Actual numeric-source responses; recommendation selector snapshots are not required to optimize new scenarios.'}
def exceptions_check(actual,metadata,oracle,index,contract,io):
    expected={ (r['site_id'],r['option_id'],r['rule_id']):r for r in oracle['exceptions']};checks={};bindings={}
    for key,wanted in expected.items():
        row=actual.get(key) or {};st=io['canon'](row.get('status'));state=st in ({'fail','失败','不满足'} if wanted['status']=='fail' else {'unknown','未知','待核实','未核实'})
        values_={field:bool(row) and io['scalar_ok'](row.get(field),wanted[field],contract['numeric_tolerance']) for field in ['observed','limit']}
        checks['/'.join(key)]={'status':state,**values_,'next_action':bool(io['clean'](row.get('next_action')))}
        anchor=io['source_anchor'](row.get('source_file'),row.get('source_locator'),wanted['accepted_source_anchors'],index)
        rule=io['clean'](row.get('rule_source'));rule_ok=bool(row) and (not rule or rule==wanted['rule_anchor'] or rule==wanted['rule_anchor'].replace('#','/'))
        bindings['/'.join(key)]={'actual_source':anchor,'claim_values':all(values_.values()),'optional_rule_source':rule_ok}
    exact=set(actual)==set(expected) and not metadata.get('duplicates')
    return {'checks':checks,'bindings':bindings,'exact_set':exact,'score':.85*io['mean'](io['mean'](v.values()) for v in checks.values())+.15*exact,
        'binding_score':io['mean'](io['mean'](v.values()) for v in bindings.values())}
