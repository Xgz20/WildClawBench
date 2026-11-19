"""Actual locked-Office probes of summary dependence on declared source/markers."""
from collections import defaultdict
import re
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def location_edit(loc,value,io,marker=False):
    cell=loc['cell']
    if cell.get('merged_from') and tuple(cell['merged_from'])!=(loc['row'],loc['col']):raise RuntimeError('H018 merged logical intervention target is not independently addressable')
    col=loc['col'];letters=''
    while col:col,rem=divmod(col-1,26);letters=chr(65+rem)+letters
    return {'sheet':loc['sheet'],'cell':letters+str(loc['row']),'value':value}
def evaluate_summary(book,wanted,spec,expected,contract,io,checks):
    fake={**expected,'baseline':wanted};observed=checks['summary'](book,fake,contract,io);affected=set(spec['affected_keys']);a=[];unaffected=[]
    for mid,fields in observed['checks'].items():
        for key,ok in fields.items():(a if mid+'/'+key in affected else unaffected).append(ok)
    return {'score':mean(a)*all(unaffected),'checks':observed['checks'],'affected_count':len(a),'unaffected_unchanged':all(unaffected)}
def responses(source,original,baseline,observations,expected,contract,io,checks,office,lock,derived):
    if not observations['data_complete'] or not observations['summary']['complete']:
        return {'score':0.,'status':'baseline_data_or_summary_invalid','cases':[]}
    for row in observations['model_rows']:
        for loc in row['locations'].values():
            if loc['cell'].get('merged_from'):raise RuntimeError('H018 merged marker value requires an independently addressable intervention profile')
    required={w['stratum']:w['weight'] for w in expected['weights']};groups=io['weight_groups'](baseline,contract['weight_aliases'],set(required));original_sheets={s['name']:s for s in original};candidates=[];unsupported=[]
    for group in groups:
        by_id=defaultdict(list)
        for row in group['rows']:by_id[io['norm'](row['stratum'])].append(row)
        if not all(len(by_id[k])==1 and io['equal'](by_id[k][0]['weight'],v,1e-9) for k,v in required.items()):continue
        locations={k:by_id[k][0]['_locations']['weight'] for k in required};literal=True
        for key,loc in locations.items():
            cell=original_sheets[loc['sheet']]['cells'].get((loc['row'],loc['col']),{})
            if cell.get('formula') or io['number'](cell.get('value')) is None or not isinstance(cell.get('value'),(int,float)) or isinstance(cell.get('value'),bool):literal=False
        (candidates if literal else unsupported).append({'locations':locations,'visible':all(by_id[k][0]['_visible'] for k in required)})
    if not candidates:
        if unsupported:raise RuntimeError('H018 editable weight source uses an unsupported intervention representation')
        return {'score':0.,'status':'editable_weight_inputs_missing_or_wrong','cases':[]}
    cases=[];trials=[];chosen=None
    def run(spec,locations,tag):
        edits={}
        if spec['drop_flags']:
            selected=set(spec['drop_flags'])
            for row in observations['model_rows']:
                if row['record_id'] not in selected:continue
                for key in expected['cleaned'][0]['flags']:
                    edit=location_edit(row['locations'][key],0,io,marker=True);identity=edit['sheet'],edit['cell']
                    if identity in edits and edits[identity]!=edit:raise RuntimeError('H018 ambiguous marker intervention')
                    edits[identity]=edit
        else:
            for key,value in spec['weights'].items():
                if value!=required[key]:
                    edit=location_edit(locations[key],value,io);edits[edit['sheet'],edit['cell']]=edit
        if not edits:raise ValueError('H018 private response has no edits')
        changes=list(edits.values());parent=source;steps=[];marker=bool(spec['drop_flags'])
        for i,start in enumerate(range(0,len(changes),100),1):
            function=office['prepare_xlsx_marker_intervention' if marker else 'prepare_xlsx_counterfactual'];prepared=function(parent,changes[start:start+100],derived/tag/('step-'+str(i).zfill(3)))
            office['verify_xlsx_marker_intervention' if marker else 'verify_xlsx_counterfactual'](parent,prepared['path'],prepared['audit']);steps.append(prepared);parent=prepared['path']
        result=office['recalculate_xlsx'](parent,lock,derived/tag/'calculated',timeout_seconds=90);book=io['XLSX']['read_book'](result['path']);assessment=evaluate_summary(book,spec['expected'],spec,expected,contract,io,checks)
        return {'name':spec['name'],'score':assessment['score'],'intervention_cells':len(changes),'marker_intervention':marker,'checks':assessment,'prepared_steps':steps,'recalculation':result}
    first=expected['response_specs'][0]
    chosen_visible=False
    for n,candidate in enumerate(candidates):
        locations=candidate['locations']
        trial=run(first,locations,'driver-'+str(n)+'-'+first['name']);trials.append(trial)
        if trial['score']==1.:chosen=locations;chosen_visible=candidate['visible'];cases.append(trial);break
    if chosen is None:
        best=max(trials,key=lambda r:r['score']);return {'score':best['score']/len(expected['response_specs']),'status':'no_weight_source_drives_all_expected_outputs','cases':[best],'driver_trials':trials}
    for spec in expected['response_specs'][1:]:cases.append(run(spec,chosen,spec['name']))
    return {'score':mean(c['score'] for c in cases),'status':'completed','cases':cases,'driver_trials':trials,'driver_visible':chosen_visible,'editable_weight_locations':{k:{n:v for n,v in loc.items() if n!='cell'} for k,loc in chosen.items()}}
