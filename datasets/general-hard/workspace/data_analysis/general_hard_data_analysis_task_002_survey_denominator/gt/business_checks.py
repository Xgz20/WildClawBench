"""Source-grounded survey state, complete typed flags, and exclusion provenance."""
from collections import defaultdict,Counter
import re
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def summary(book,expected,contract,io):
    aliases=contract['summary_aliases'];fields=['raw_num','raw_den','raw_rate','weighted_num','weighted_den','weighted_rate'];keys={io['canon'](m['metric_id']):m['metric_id'] for m in expected['metrics']}
    rows=io['flatten'](io['discover'](book,aliases,['metric_id',*fields],id_field='metric_id',id_test=lambda v:io['canon'](v) in keys));grouped=defaultdict(list)
    for row in rows:grouped[keys[io['canon'](row['metric_id'])]].append(row)
    checks={mid:{field:bool(grouped[mid]) and all(io['equal'](row[field],values[field],expected['tolerance']['workbook_numeric'] if field not in {'raw_num','raw_den'} else 0) for row in grouped[mid]) for field in fields} for mid,values in expected['baseline'].items()}
    visible=bool(rows) and all(r['_visible'] for r in rows)
    return {'checks':checks,'score':mean(mean(c.values()) for c in checks.values()),'visible':visible,'rows':rows,'complete':all(all(v.values()) for v in checks.values())}
def observe(book,expected,contract,io):
    originals={r['record_id']:r for r in expected['cleaned']};kept={rid:r for rid,r in originals.items() if r['keep']};raw_groups=io['discover'](book,contract['raw_aliases'],list(contract['raw_aliases']),id_field='record_id',id_test=lambda v:bool(re.fullmatch(r'S\d+',io['norm'](v))));raw_rows=io['flatten'](raw_groups);raw_by_id=defaultdict(list)
    for row in raw_rows:raw_by_id[io['norm'](row['record_id'])].append(row)
    raw_checks={};selection={}
    for rid,truth in originals.items():
        rows=raw_by_id.get(rid,[])
        raw_checks[rid]=bool(rows) and all(all(io['raw_equal'](row[k],truth['raw'][k],k) for k in expected['source_headers']) for row in rows)
        selection[rid]=bool(rows) and all(io['bit'](row['keep'],truth['keep']) and str(row['reason'] or '').strip().lower()==truth['reason'] and io['norm'](row['related_record_id'])==truth['related_record_id'] for row in rows)
    raw_set=set(raw_by_id)==set(originals)
    model_rows=io['models'](book,contract,expected);model_by_id=defaultdict(list)
    for row in model_rows:model_by_id[row['record_id']].append(row)
    model_checks={};identities={};weights={s['stratum']:s['weight'] for s in expected['weights']}
    for rid,truth in kept.items():
        rows=model_by_id.get(rid,[])
        model_checks[rid]={k:bool(rows) and all(io['bit'](row['flags'].get(k),v) for row in rows) for k,v in truth['flags'].items()}
        identities[rid]=bool(rows) and all(io['norm'](row['respondent_id'])==truth['respondent_norm'] and io['norm'](row['stratum'])==truth['stratum_norm'] and io['equal'](row['weight'],weights[truth['stratum_norm']],1e-9) for row in rows)
    model_set=set(model_by_id)==set(kept)
    sums=summary(book,expected,contract,io)
    visible=bool(raw_rows and model_rows) and all(r['_visible'] for r in raw_rows) and all(r['visible'] for r in model_rows) and sums['visible']
    # Keep exception groups separate from the many straightforward source rows.
    groups={}
    for reason in sorted({r['reason'] for r in expected['cleaned']}):
        ids=[rid for rid,r in originals.items() if r['reason']==reason];groups['record/'+(reason or 'kept')]=mean(selection[rid] for rid in ids)
    for q in ['Q1','Q2','Q3','Q4']:
        for state in sorted({r['question_states'][q] for r in kept.values()}):
            ids=[rid for rid,r in kept.items() if r['question_states'][q]==state];fields=[k for k in next(iter(kept.values()))['flags'] if k.lower().startswith(q.lower()+'_')]
            groups[q+'/'+state]=mean(all(model_checks[rid][f] for f in fields) for rid in ids)
    record_score=.65*mean(selection.values())+.35*mean(raw_checks.values())
    flag_score=.85*mean(mean(v.values()) for v in model_checks.values())+.15*mean(identities.values())
    exact=raw_set and model_set and all(raw_checks.values()) and all(selection.values()) and all(identities.values()) and all(all(v.values()) for v in model_checks.values())
    return {'summary':sums,'record_score':record_score,'flag_score':flag_score,'exception_groups':groups,'raw_checks':raw_checks,'selection_checks':selection,'model_flag_checks':model_checks,'model_identity_checks':identities,'raw_set_complete':raw_set,'model_set_complete':model_set,'visible':visible,'data_complete':exact,'raw_physical_rows':len(raw_rows),'raw_unique_records':len(raw_by_id),'model_physical_representations':len(model_rows),'model_unique_records':len(model_by_id),'model_rows':model_rows}
def exclusion_checks(rows,expected,io):
    if rows is None:return {'score':0.,'locators':0.,'exact':False,'rows':{}}
    def stage(v):return 'record' if str(v).strip().lower()=='record' else io['norm'](v)
    by_id=defaultdict(list)
    for row in rows:by_id[stage(row['stage']),io['norm'](row['record_id'])].append(row)
    checks={};locators={}
    for truth in expected['exclusions']:
        key=truth['stage'],truth['record_id'];hits=by_id.get(key,[]);row=hits[0] if len(hits)==1 else None
        checks['/'.join(key)]=bool(row and io['norm'](row['respondent_id'])==truth['respondent_id'] and str(row['reason']).strip().lower()==truth['reason'] and io['norm'](row['related_record_id'])==truth['related_record_id'])
        locators['/'.join(key)]=bool(row and io['equal'](row['source_row'],truth['source_row']) and io['norm'](row['related_record_id'])==truth['related_record_id'])
    exact=set(by_id)=={(r['stage'],r['record_id']) for r in expected['exclusions']} and all(len(v)==1 for v in by_id.values()) and len(rows)==len(expected['exclusions'])
    return {'score':mean(checks.values())*exact,'locators':mean(locators.values())*exact,'exact':exact,'rows':checks,'locator_checks':locators,'actual_rows':len(rows)}
