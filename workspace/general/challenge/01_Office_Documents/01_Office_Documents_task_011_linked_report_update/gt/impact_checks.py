"""Bind every logical impact to actual candidate values and current artifact locations."""
from collections import defaultdict
import json,re
def directions(value):
    aliases={'正':'positive','增长':'positive','负':'negative','下降':'negative','零':'zero'}
    if isinstance(value,dict):return {k:directions(v) for k,v in value.items()}
    return aliases.get(value,value) if isinstance(value,str) else value
def location_matches(text,observation,io):
    text=io['clean'](text)
    if not text:return False
    choices=[observation.get('locator',''),*observation.get('locators',[]),*observation.get('aliases',[])]
    for choice in choices:
        if text==choice:return True
        if '!' in text and '!' in choice:
            sheet,address=text.rsplit('!',1);cs,ca=choice.rsplit('!',1);sheet=sheet.strip("'").replace("''", "'");address=address.replace('$','').upper()
            if sheet==cs and ':' not in address and address==ca:return True
        # Core native chart locators include plot and val; the task's concise point locator is equivalent.
        normalized=re.sub(r'/plot:\d+','',text).replace('/val/point:','/point:')
        if normalized==choice:return True
    return False
def check_log(ledger,truth,oracle,observations,contract,io):
    records=ledger.get('corrections');event_rows={};duplicates=[]
    if isinstance(records,list) and len(records)<=32:
        for r in records:
            if not isinstance(r,dict):continue
            kid=io['clean'](r.get('correction_id'))
            if kid in event_rows:duplicates.append(kid);event_rows[kid]=None
            else:event_rows[kid]=r
    results={};all_supported=[]
    for index,change in enumerate(truth['corrections'],2):
        kid=change['correction_id'];record=event_rows.get(kid) or {};source=record.get('source');source=source if isinstance(source,dict) else {}
        source_ok=(io['output_path'](source.get('file'))=='corrections.csv' and io['clean'](source.get('locator')) in {f'row:{index}',kid,'#'+kid}
            and io['clean'](source.get('period'))==change['period'] and io['clean'](source.get('metric')).upper()==change['metric']
            and io['match'](io['scalar'](source.get('old_value'),source.get('old_unit'),'CNY'),change['expected_old'])
            and io['match'](io['scalar'](source.get('new_value'),source.get('new_unit'),'CNY'),change['new_cny'])
            and io['match'](source.get('normalized_new_cny'),change['new_cny']))
        targets=record.get('targets');targets=targets if isinstance(targets,list) and len(targets)<=512 else []
        used=set();matches={};actual_bound={}
        for identity in oracle['per_correction_affected_nodes'][kid]:
            node=oracle['complete_graph'][identity];actual=observations.get(identity);matches[identity]=False;actual_bound[identity]=False
            if not actual:continue
            # P21's period-end balance is a scalar CNY observation inside a prose
            # constraint node. It has the same currency equivalence as table values.
            balance=identity=='word/paragraph/P21'
            numeric=node['kind'] in {'source','formula','artifact_value'} or balance
            before=node['value'] if node['kind'] in {'source','formula'} else node['before']
            after=truth['corrected_model']['nodes'][identity]['value'] if node['kind'] in {'source','formula'} else node['after']
            unit='CNY' if balance else actual.get('unit')
            for n,entry in enumerate(targets):
                if n in used or not isinstance(entry,dict):continue
                if io['output_path'](entry.get('file'))!=actual['file'] or not location_matches(entry.get('locator'),actual,io):continue
                if numeric:
                    tol='1e-8' if unit=='ratio' else '.005'
                    # Preserve the original author reference's generic constraint
                    # unit while accepting explicit CNY, yuan and wan-yuan records.
                    entry_unit='CNY' if balance and entry.get('unit')=='direction_or_constraint' else entry.get('unit')
                    good=io['match'](io['scalar'](entry.get('before'),entry_unit,unit),before,tol) and io['match'](io['scalar'](entry.get('after'),entry_unit,unit),after,tol)
                    bound=io['match'](io['scalar'](entry.get('after'),entry_unit,unit),actual.get('value'),tol)
                elif identity=='pptx/chart/CASH_QUARTER/axis':
                    claim=entry.get('after');claim=claim if isinstance(claim,dict) else {}
                    minimum=io['number'](claim.get('axis_min',claim.get('axis_min_maximum')))
                    good=isinstance(entry.get('before'),dict) and io['match'](entry['before'].get('axis_min'),0) and (minimum is not None and minimum<=-3 or claim.get('auto_axis_allowed') is True)
                    bound=actual.get('value') is not None
                else:
                    good=directions(entry.get('before'))==directions(before) and directions(entry.get('after'))==directions(after)
                    bound=directions(actual.get('value'))==directions(after)
                if good:
                    used.add(n);matches[identity]=True;actual_bound[identity]=bool(bound);break
        supported=bool(targets) and len(used)==len(targets);all_supported.append(supported)
        results[kid]={'source':bool(source_ok),'coverage':matches,'actual_binding':actual_bound,'no_unsupported_or_duplicate_targets':supported,
            'expected_count':len(matches),'provided_count':len(targets),'matched_count':len(used)}
    score=io['mean'](.15*r['source']+.65*io['mean'](r['coverage'][k] and r['actual_binding'][k] for k in r['coverage'])+.20*r['no_unsupported_or_duplicate_targets'] for r in results.values())
    if duplicates:score=0.
    return {'score':score,'events':results,'duplicate_events':duplicates,
        'limit':'Scalar/location and constrained direction bindings only; independent Judge evaluates the full prose reasoning and visual evidence.'}
