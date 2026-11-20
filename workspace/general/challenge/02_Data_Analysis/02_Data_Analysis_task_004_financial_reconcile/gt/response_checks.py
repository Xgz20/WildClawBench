"""Native Office experiments on independently verified effective data identities."""
def responses(source,original,observed,data,expected,contract,io,checks,office,lock,derived):
    if not observed['complete'] or not observed['visible'] or observed['formula_score']!=1. or not data['complete']:return {'score':0.,'status':'baseline_or_formulas_invalid','cases':[],'drivers_visible':False}
    cases=[]
    def edit(location,value):
        cell=location['cell']
        if cell.get('merged_from'):raise RuntimeError('H020 logical source is merged and not independently addressable')
        col=location['col'];letters=''
        while col:col,rem=divmod(col-1,26);letters=chr(65+rem)+letters
        return {'sheet':location['sheet'],'cell':letters+str(location['row']),'value':value}
    for spec in expected['response_specs']:
        if len(spec['edits'])!=1:raise ValueError('H020 private source probe contract changed')
        change=spec['edits'][0];rows=data['candidates'][change['company_id'],change['period_year']]
        if len(rows)>contract['case_limits']['max_driver_trials_per_case']:raise RuntimeError('H020 source-view search exceeds declared runtime capacity')
        trials=[];chosen=None
        for n,row in enumerate(sorted(rows,key=lambda r:not r['_visible'])):
            location=row['_locations'][change['field']];changes=[edit(location,change['value'])];directory=derived/spec['name']/('source-'+str(n));prepare='prepare_xlsx_marker_intervention' if spec['marker'] else 'prepare_xlsx_numeric_intervention';verify='verify_xlsx_marker_intervention' if spec['marker'] else 'verify_xlsx_numeric_intervention'
            prepared=office[prepare](source,changes,directory/'prepared');office[verify](source,prepared['path'],prepared['audit']);calculated=office['recalculate_xlsx'](prepared['path'],lock,directory/'calculated',timeout_seconds=90);book=io['XLSX']['read_book'](calculated['path']);assessment=checks['metrics'](book,spec['expected'],contract,io,original,formula_only=True)
            affected=set(spec['affected_keys']);changed=[];unchanged=[]
            for key,fields in assessment['checks'].items():
                for field,ok in fields.items():(changed if key+'/'+field in affected else unchanged).append(ok)
            if not changed:raise ValueError('H020 expected source probe has no affected fields')
            score=checks['mean'](changed)*all(unchanged)*assessment['identity_complete'];trial={'name':spec['name'],'score':score,'affected_fields':len(changed),'unaffected_correct':all(unchanged),'visible_driver':row['_visible'],'source_location':{k:v for k,v in location.items() if k!='cell'},'assessment':assessment,'prepared':prepared,'recalculation':calculated};trials.append(trial)
            if score==1.:chosen=trial;break
        best=chosen or max(trials,key=lambda t:t['score']);cases.append({**best,'driver_trials':trials})
    return {'score':checks['mean'](r['score'] for r in cases),'status':'completed','cases':cases,'drivers_visible':all(r['visible_driver'] for r in cases)}
