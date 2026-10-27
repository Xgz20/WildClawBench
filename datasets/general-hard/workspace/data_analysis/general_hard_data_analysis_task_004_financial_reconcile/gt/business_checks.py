"""Bounded financial facts and source provenance, independent of author coordinates."""
from collections import defaultdict
import re
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def metrics(book,expected,contract,io,original=None,formula_only=False):
    records=io['records'](book,contract,'metric');by=defaultdict(list)
    for row in records:by[io['identity'](row,contract)].append(row)
    wanted={(r['company_id'],r['period_year'],r['metric_id']):r for r in expected};checks={};formula_checks={};visible_checks={};original_map={s['name']:s for s in original or book};duplicates=[]
    for key,hits in by.items():
        groups=[r['_group'] for r in hits]
        if len(groups)!=len(set(groups)):duplicates.append('/'.join(map(str,key)))
    def formula(row,field):
        loc=row['_locations'][field];return original_map.get(loc['sheet'],{}).get('cells',{}).get((loc['row'],loc['col']),{}).get('formula',False)
    for key,want in wanted.items():
        hits=by.get(key,[]);tag='/'.join(map(str,key));checks[tag]={};formula_checks[tag]={};visible_checks[tag]={}
        for field in contract['metric_fields']:
            selected=[r for r in hits if formula(r,field)] if formula_only else hits
            shown=[r for r in selected if r['_visible']];selected=shown or selected
            def correct(r):
                value=r[field]
                if field=='status':value=io['status'](value)
                if field=='reason':value=io['reason'](value,contract)
                return io['equal'](value,want[field],1e-7 if field=='change_pp' else 1e-9,nullable=field in {'numerator_wan','denominator_wan'})
            checks[tag][field]=bool(selected) and all(correct(r) for r in selected)
            formula_checks[tag][field]=any(formula(r,field) and r['_visible'] for r in hits)
            visible_checks[tag][field]=bool(shown)
    identity=set(by)==set(wanted) and not duplicates;score=mean(v for fields in checks.values() for v in fields.values())
    return {'score':score,'checks':checks,'formula_checks':formula_checks,'formula_score':mean(v for fields in formula_checks.values() for v in fields.values()),'identity_complete':identity,'duplicate_keys':duplicates,'visible':all(v for fields in visible_checks.values() for v in fields.values()),'complete':identity and all(all(v.values()) for v in checks.values()),'records_seen':len(records),'unique_records':len(by)}
def data(book,expected,contract,io):
    records=io['records'](book,contract,'data');by=defaultdict(list)
    for row in records:by[io['identity'](row,contract,False)].append(row)
    checks={};good={};visible={}
    for want in expected:
        key=(want['company_id'],want['period_year']);tag='/'.join(map(str,key));rows=by.get(key,[])
        def correct(row,field):
            value=int(row[field]) if field=='scope_comparable' and isinstance(row[field],bool) else row[field]
            return io['equal'](value,want[field],1e-6,nullable=True)
        full=[r for r in rows if all(correct(r,f) for f in contract['data_fields'])];good[key]=full
        checks[tag]={f:any(correct(r,f) for r in rows) for f in contract['data_fields']};visible[tag]=any(r['_visible'] for r in full)
    return {'score':mean(v for row in checks.values() for v in row.values()),'checks':checks,'complete':all(good.values()),'visible':all(visible.values()),'candidates':good,'candidate_rows':sum(map(len,good.values()))}
def revisions(grids,expected,contract,io,word=False):
    fields=['restatement_id','old_value_wan','new_value_wan','difference_wan'];rows=io['discover'](grids,contract['aliases'],fields,lambda r:bool(re.search(r'R-[A-Z]\d{2}',str(r.get('restatement_id','')))));by=defaultdict(list)
    for row in rows:
        matches=set(re.findall(r'R-[A-Z]\d{2}',str(row['restatement_id'])));key=next(iter(matches)) if len(matches)==1 else 'INVALID';by[key].append(row)
    checks={};visible=True
    for wanted in expected:
        hits=by.get(wanted['restatement_id'],[]);checks[wanted['restatement_id']]={k:bool(hits) and all(io['equal'](r[k],wanted[k],1e-6) for r in hits) for k in fields[1:]};visible &= any(r['_visible'] for r in hits)
    exact=set(by)=={r['restatement_id'] for r in expected};return {'checks':checks,'score':mean(v for d in checks.values() for v in d.values()),'complete':exact and all(all(d.values()) for d in checks.values()),'visible':visible}
def sources(rows,expected,contract,io):
    by=defaultdict(list)
    for row in rows or []:
        field=io['canon'](row['field']);field=field[:-3] if field.endswith('wan') else field;name=next((k for k in contract['data_fields'] if io['canon'](k)==field),field);by[io['company'](row['company_id']),io['year'](row['period_year']),name].append(row)
    checks={};locators={};wanted_keys=set()
    for want in expected:
        key=(want['company_id'],want['period_year'],want['field']);wanted_keys.add(key);hits=by.get(key,[]);row=hits[0] if len(hits)==1 else {};tag='/'.join(map(str,key));tests={}
        for field in ['reported_value','effective_value_wan']:
            if field=='reported_value' and want[field]=='未披露':tests[field]=row.get(field,'').strip()=='未披露'
            else:tests[field]=bool(row) and io['equal'](row[field],io['number'](want[field]) if field=='reported_value' else want[field],1e-6,nullable=field=='effective_value_wan')
        tests['unit']=bool(row) and row['unit'].strip().replace('人民币','').replace('RMB','').replace('CNY','').strip()==want['unit']
        locator_ids=set(re.findall(r'[ABC]\d{4}-(?:BS|IS|CF|CP|SC)\d{2}',row.get('locator','')))
        location=bool(row) and io['source_path'](row['source_file'],statement=True)==want['source_file'] and locator_ids=={want['locator']}
        if want['restatement_id']:
            adjustment=bool(row) and row['restatement_id'].strip()==want['restatement_id'] and io['source_path'](row['adjustment_source'])=='restatements.csv' and set(re.findall(r'R-[A-Z]\d{2}',row['adjustment_locator']))=={want['restatement_id']}
        else:adjustment=bool(row) and all(io['blank'](row[k]) for k in ['restatement_id','adjustment_source','adjustment_locator'])
        checks[tag]=tests;locators[tag]={'source':location,'revision':adjustment}
    exact=set(by)==wanted_keys and all(len(v)==1 for v in by.values()) and len(rows or [])==63
    return {'score':mean(v for row in checks.values() for v in row.values()),'binding_score':mean(v for row in locators.values() for v in row.values()),'checks':checks,'locators':locators,'exact':exact,'complete':exact and all(all(row.values()) for row in checks.values()) and all(all(row.values()) for row in locators.values()),'actual_rows':len(rows or [])}
