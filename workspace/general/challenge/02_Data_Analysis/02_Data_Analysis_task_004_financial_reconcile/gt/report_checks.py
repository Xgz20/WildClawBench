"""Native report facts; full financial interpretation belongs to the independent Judge."""
from collections import defaultdict
import re
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def paragraph_records(model,contract,io):
    rows=[];labels={'value':['value','数值','指标值','比率'],'rank':['rank','名次','排名','第'],'change_pp':['change_pp','变化百分点','变化','变动','较上年变化']}
    numeric=r'(?:不适用|n/a|[+\-−]?(?:\d[\d,]*)(?:\.\d+)?\s*(?:%|％|倍|个百分点|百分点|pp)?)'
    for p in model['paragraphs']:
        if p['parent_cell'] is not None:continue
        text=p['text'];year=re.search(r'\b(202[345])(?:年|\b)',text);company=re.search(r'(?:company_id\s*[:=]\s*)?\b([ABC])(?:公司|\b)',text,re.I);metrics=[k for k,a in contract['metric_aliases'].items() if any(alias.lower() in text.lower() for alias in a)]
        if not year or not company or len(metrics)!=1:continue
        row={'company_id':company[1].upper(),'period_year':int(year[1]),'metric_id':metrics[0],'_locations':{},'_visible':True}
        for field,names in labels.items():
            m=re.search(r'(?:'+ '|'.join(re.escape(s) for s in sorted(names,key=len,reverse=True))+r')\s*[:=：为]?\s*('+numeric+')',text,re.I)
            if m:row[field]=m[1];row['_locations'][field]={'header':field,'cell':{'locator':p['locator']}}
        if {'value','rank'}<=set(row):rows.append(row)
    return rows
def facts(model,expected,contract,io,checks):
    if model is None:return {'score':0.,'checks':{},'revisions':{},'complete':False,'texts':[]}
    grids=io['grids_word'](model);rows=io['records'](grids,contract,'metric',word=True)+paragraph_records(model,contract,io);by=defaultdict(list)
    for row in rows:by[io['identity'](row,contract)].append(row)
    results={}
    for want in expected['baseline']:
        key=(want['company_id'],want['period_year'],want['metric_id']);hits=by.get(key,[]);tests={}
        for field in ['value','rank']+(['change_pp'] if want['period_year']==2025 else []):
            selected=[r for r in hits if field in r];percent_header=lambda r:'%' in str(r['_locations'][field]['header']) or '百分' in str(r['_locations'][field]['header'])
            tests[field]=bool(selected) and all(io['equal'](r[field],want[field],.00005001 if field=='value' else .005001 if field=='change_pp' else 0,word_rate=field=='value',percent_header=percent_header(r)) for r in selected)
        results['/'.join(map(str,key))]=tests
    revisions=checks['revisions'](grids,expected['restatements'],contract,io,word=True)
    # Unambiguous one-revision paragraphs are another valid native presentation.
    for want in expected['restatements']:
        for p in model['paragraphs']:
            text=p['text']
            if p['parent_cell'] is not None or set(re.findall(r'R-[A-Z]\d{2}',text))!={want['restatement_id']}:continue
            tests={}
            for field,terms in [('old_value_wan',['old_value_wan','原值']),('new_value_wan',['new_value_wan','生效值','新值']),('difference_wan',['difference_wan','差额'])]:
                m=re.search('(?:'+'|'.join(terms)+r')\s*[:=：为]?\s*([+\-−]?\d[\d,]*(?:\.\d+)?)',text,re.I);tests[field]=bool(m and io['equal'](m[1],want[field],1e-6))
            if all(tests.values()):revisions['checks'][want['restatement_id']]=tests
    revisions['complete']=all(all(v.values()) for v in revisions['checks'].values());revisions['score']=mean(v for fields in revisions['checks'].values() for v in fields.values())
    texts=[p['text'] for p in model['paragraphs']];score=.85*mean(v for fields in results.values() for v in fields.values())+.15*revisions['score'];complete=all(all(v.values()) for v in results.values()) and revisions['complete']
    return {'score':score,'checks':results,'revisions':revisions,'complete':complete,'texts':texts,'limit':'Core numeric/rank/change and revision facts; applicability explanations and contradictory prose remain semantic Judge work.'}
