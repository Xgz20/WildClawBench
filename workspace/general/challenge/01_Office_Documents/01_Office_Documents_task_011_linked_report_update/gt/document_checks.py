"""Observe actual native KPI slots, period tables, notes and editable chart data."""
from collections import defaultdict
from decimal import Decimal as D
import io as bytes_io,json,re,zipfile
import xml.etree.ElementTree as E
C='{http://schemas.openxmlformats.org/drawingml/2006/chart}'
def inline_number(text,default_unit,io):
    text=io['clean'](text);m=re.fullmatch(r'([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(万元|元|%|CNY)?',text)
    return (io['number'](m[1]),m[2] or default_unit) if m else (None,default_unit)
def unique_slots(slots,truth,io):
    observations={};checks={}
    for identity,node in truth['artifact_nodes'].items():
        if identity not in slots:continue
        values=slots[identity];checks[identity]=bool(values and all(io['match'](io['scalar'](v['value'],v['unit'],node['unit']),node['after']) for v in values))
        observations[identity]={'value':io['scalar'](values[0]['value'],values[0]['unit'],node['unit']) if checks[identity] else None,
            'unit':node['unit'],'locator':values[0]['locator'],'locators':[v['locator'] for v in values],
            'slots':values,'actual_values_consistent':checks[identity]}
    return checks,observations
def kpi_tokens(text):
    # Stop at the next visible KPI id; dates/months in the label are not values.
    return re.findall(r'(K\d{2})\s*((?:(?!K\d{2}).)*?)([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(万元|元|%|CNY)',text,re.S)
def period_claim(text,period,io):
    pattern=r'(?:第二季度|Q2)' if period=='q2' else r'(?:1\s*(?:至|-|—|~)\s*9\s*月|前三季度|累计)'
    found=[]
    for m in re.finditer(pattern+r'[^。;；\n]{0,35}?((?:为)?[正负+-]?)\s*([0-9,]+(?:\.\d+)?)\s*(万元|元)',io['clean'](text),re.I):
        n=io['number'](m[2]);sign=-1 if '负' in m[1] or '-' in m[1] else 1
        if n is not None:found.append(n*sign*(10000 if m[3]=='万元' else 1))
    return found
def semantics(word_paragraphs,ppt_records,truth,io):
    observed={};checks={}
    def put(identity,value,locators,valid):
        node=truth['qualitative_after'];checks[identity]=bool(valid);observed[identity]={'value':value,'locator':locators[0] if locators else '',
            'locators':locators,'observable_constraint_matches':bool(valid),'unit':'direction_or_constraint'}
    p10=word_paragraphs.get('P10',[]);p20=word_paragraphs.get('P20',[]);p21=word_paragraphs.get('P21',[])
    texts=' '.join(p['text'] for p in p10);percents=re.findall(r'([+-]?[0-9]+(?:\.[0-9]+)?)\s*%',texts)
    good=bool(p10 and any(io['match'](v,'.11') for v in percents) and any(io['match'](v,'8.18') for v in percents)
        and not re.search(r'(?:收入同比|经营利润同比)\s*(?:仍|目前|本期|为)?\s*(?:下降|略降|减少|为负)',texts))
    put('word/paragraph/P10',{'revenue_yoy':'positive','op_yoy':'positive'} if good else None,[p['locator'] for p in p10],good)
    for artifact,items in [('word',p20),('pptx',[r for r in ppt_records if r.get('context')=='speaker_notes' and re.search('第二季度|Q2',r.get('text',''),re.I)])]:
        q=[v for p in items for v in period_claim(p['text'],'q2',io)];y=[v for p in items for v in period_claim(p['text'],'ytd',io)]
        good=bool(q and y and all(v==-30000 for v in q) and all(v==40000 for v in y))
        # Notes can state signs without repeating the amount; bind both period labels and directions.
        if artifact=='pptx' and not q and not y:
            joined=' '.join(p['text'] for p in items)
            good=bool(items and re.search(r'Q2现金(?:净额)?(?:为)?负',joined) and re.search(r'1至9月现金(?:净额)?(?:为)?正',joined))
        put(artifact+'/cash-direction',{'q2':'negative','ytd':'positive'} if good else None,[p['locator'] for p in items],good)
    items=[r for r in ppt_records if r.get('context')=='slide' and '收入同比' in r.get('text','') and 'K02' not in r.get('text','')
        and re.search(r'[0-9]\s*%|微增|增长|上升|略降|下降|减少|为负',r.get('text',''))]
    def revenue_current(p):
        text=p['text'];directions=list(re.finditer(r'微增|增长|上升|略降|下降|减少|为负',text))
        return any(io['match'](v,'.11') for v in re.findall(r'([+-]?[0-9]+(?:\.[0-9]+)?)\s*%',text)) and (not directions or directions[-1][0] in {'微增','增长','上升'})
    good=bool(items and all(revenue_current(p) for p in items))
    put('pptx/revenue-direction','positive' if good else None,[p['locator'] for p in items],good)
    values=[]
    for p in p21:
        values.extend(D(v.replace(',',''))*(10000 if unit=='万元' else 1) for v,unit in re.findall(r'([0-9,]+(?:\.\d+)?)\s*(万元|元)',p['text']))
    good=bool(values and all(v==420000 for v in values) and all(re.search(r'时点|期末|月末|快照',p['text']) for p in p21))
    put('word/paragraph/P21','420000' if good else None,[p['locator'] for p in p21],good)
    return checks,observed
def word_checks(model,truth,contract,io):
    slots=defaultdict(list);paragraphs=defaultdict(list);notes=defaultdict(list)
    for p in model['paragraphs']:
        m=re.match(r'\[(P\d+)\]',io['clean'](p['text']))
        if m:paragraphs[m[1]].append(p)
        if p['parent_cell'] is None:
            for kid,label,value,unit in kpi_tokens(p['text']):slots['word/kpi/'+kid].append({'value':value,'unit':unit,'locator':p['locator'],'references':p['references']})
    for note in model['notes'].values():
        m=re.search(r'\[(F\d{2})\]',note['text'])
        if m:notes[m[1]].append(note)
    for table in model['tables']:
        value_cols=[]
        for row in table['rows']:
            for i,cell in enumerate(row['cells']):
                if io['key'](cell['text']) in {'结果','修订后','新值','当前值','修订后金额'}:value_cols=[i]
            for cell in row['cells']:
                m=re.match(r'K\d{2}(?=\s|[^0-9]|$)',io['clean'](cell['text']))
                if not m:continue
                identity='word/kpi/'+m[0]
                if identity not in truth['artifact_nodes']:continue
                unit_cells=[c['text'] for c in row['cells'] if io['clean'](c['text']) in ['万元','%','元','CNY']]
                if len(unit_cells)!=1:continue
                values=[]
                for i,c in enumerate(row['cells']):
                    if value_cols and i not in value_cols:continue
                    n,u=inline_number(c['text'],unit_cells[0],io)
                    if n is not None:values.append({'value':n,'unit':u,'locator':c['locator'],'references':c['references']})
                if len(values)==1:slots[identity].extend(values)
        # Quarterly business table: logical period and named numeric fields.
        for start,row in enumerate(table['rows']):
            headers={};period=None
            for i,c in enumerate(row['cells']):
                k=io['key'](c['text'])
                if k in {'期间','period','季度'}:period=i
                for metric in ['REV','GP','OP','OCF','AR']:
                    if k in {io['key'](metric),io['key'](metric+'万元')}:headers[metric]=i
            if period is not None and len(headers)==5:
                for data in table['rows'][start+1:]:
                    cells=data['cells'];tag=io['clean'](cells[period]['text']) if len(cells)>period else ''
                    if tag not in ['Q1','Q2','Q3','YTD']:continue
                    for metric,col in headers.items():
                        if col<len(cells):
                            cell=cells[col];n,u=inline_number(cell['text'],'万元',io)
                            slots[f'word/quarter/{tag}/{metric}'].append({'value':n,'unit':u,'locator':cell['locator']})
            # Baseline-period table can be independently reordered or share a year-comparison view.
            yearcols=[i for i,c in enumerate(row['cells']) if re.search(r'2025.*(?:1.*9|基期)',io['clean'](c['text']))]
            metriccols=[i for i,c in enumerate(row['cells']) if io['key'](c['text']) in {'口径','metric','指标','2025年1至9月基期指标'}]
            if yearcols and not metriccols:metriccols=yearcols[:1];yearcols=[]
            if metriccols:
                valuecols=[i for i in yearcols if i not in metriccols] or [i for i,c in enumerate(row['cells']) if io['key'](c['text']) in {'金额万元','金额','结果'}]
                if len(valuecols)==1:
                    for data in table['rows'][start+1:]:
                        cells=data['cells'];mi,vi=metriccols[0],valuecols[0]
                        if max(mi,vi)>=len(cells):continue
                        metric=io['clean'](cells[mi]['text'])
                        if metric in ['REV','COGS','GP','OPEX','OP']:
                            cell=cells[vi];n,u=inline_number(cell['text'],'万元',io);slots['word/basis/'+metric].append({'value':n,'unit':u,'locator':cell['locator']})
    for note in notes.get('F01',[]):
        for value in re.findall(r'收入\s*([0-9,.]+)\s*万元',note['text']):slots['word/footnote/F01'].append({'value':value,'unit':'万元','locator':note['locator']})
    checks,observed=unique_slots(slots,truth,io)
    expected=[k for k in truth['artifact_nodes'] if k.startswith('word/')]
    checks={k:checks.get(k,False) for k in expected}
    for k,v in observed.items():
        v['file']=contract['files']['word'];v['aliases']=[k.split('/')[-1]] if '/kpi/' in k or '/footnote/' in k else []
        # A shared native paragraph can contain several scalar KPI slots. Its visible
        # P id is a valid locator; before/after/unit still distinguish each slot.
        v['aliases'].extend(pid for pid,items in paragraphs.items() if any(p['locator'] in v['locators'] for p in items))
    links={}
    f01={n['locator'] for n in notes.get('F01',[])};f02={n['locator'] for n in notes.get('F02',[])}
    links['F01_to_K02']=bool(f01 and slots['word/kpi/K02'] and all(any(r['note_locator'] in f01 for r in s.get('references',[])) for s in slots['word/kpi/K02']))
    links['F02_to_P90']=bool(f02 and paragraphs.get('P90') and all(any(r['note_locator'] in f02 for r in p['references']) for p in paragraphs['P90']))
    # Necessary observable facts permit equivalent wording. Full protected meaning
    # and negation are intentionally adjudicated by the independent semantic Judge.
    limits=['1至9月','第四季度','所得税','财务费用','完整利润表','净利润','未提供']
    links['F02_text']=bool(notes.get('F02') and all(all(io['canon'](word) in io['canon'](n['text']) for word in limits) for n in notes['F02']))
    protection={}
    for kid,tokens in contract['protected_word_elements'].items():
        protection[kid]=bool(paragraphs.get(kid) and all(all(io['canon'](v) in io['canon'](p['text']) for v in tokens) for p in paragraphs[kid]))
    return {'checks':checks,'observations':observed,'paragraphs':dict(paragraphs),'notes':dict(notes),'links':links,'protection':protection}
def table_records(records):
    tables=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
    for r in records:
        if r.get('context')!='slide_table':continue
        m=re.match(r'(.+/table:\d+)/row:(\d+)/cell:(\d+)/',r['locator'])
        if m:tables[m[1]][int(m[2])][int(m[3])].append(r)
    return {k:[ [{'text':' '.join(p['text'] for p in ps),'locator':ps[0]['locator']} for _,ps in sorted(cells.items())] for _,cells in sorted(rows.items())] for k,rows in tables.items()}
def ppt_checks(path,records,truth,contract,io,lock,derived):
    slots=defaultdict(list);chart_models={};chart_integrity={};chart_errors=[];embedded_results=[]
    for r in records:
        if r.get('context')!='slide':continue
        for kid,label,value,unit in kpi_tokens(r.get('text','')):slots['pptx/kpi/'+kid].append({'value':value,'unit':unit,'locator':r['locator']})
    for loc,rows in table_records(records).items():
        for i,headers in enumerate(rows):
            yearcols={year:[c for c,v in enumerate(headers) if str(year) in v['text']] for year in [2025,2026]}
            metriccols=[c for c,v in enumerate(headers) if io['key'](v['text']) in {'口径','metric','指标'}]
            if not metriccols or any(len(v)!=1 for v in yearcols.values()):continue
            for row in rows[i+1:]:
                mi=metriccols[0]
                if mi>=len(row):continue
                metric=io['clean'](row[mi]['text'])
                if metric not in ['REV','COGS','GP','OPEX','OP']:continue
                for year,cols in yearcols.items():
                    col=cols[0]
                    if col<len(row):
                        n,u=inline_number(row[col]['text'],'万元',io);slots[f'pptx/basis/{year}/{metric}'].append({'value':n,'unit':u,'locator':row[col]['locator']})
    cached_books={}
    with zipfile.ZipFile(path) as archive:
        for chart in [r for r in records if r.get('context')=='chart']:
            xml=E.fromstring(archive.read(chart['part']));series=[]
            for si,s in enumerate(xml.findall('.//'+C+'ser')):
                name=''.join(n.text or '' for n in s.findall(C+'tx/'+C+'v')) or ''.join(n.text or '' for n in s.findall(C+'tx/'+C+'strRef/'+C+'strCache/'+C+'pt/'+C+'v'))
                cats=[n.text or '' for n in s.findall(C+'cat/'+C+'strRef/'+C+'strCache/'+C+'pt/'+C+'v')]
                vals=[n.text for n in s.findall(C+'val/'+C+'numRef/'+C+'numCache/'+C+'pt/'+C+'v')]
                if not vals:vals=[n.text for n in s.findall(C+'val/'+C+'numLit/'+C+'pt/'+C+'v')]
                if not cats:cats=[n.text or '' for n in s.findall(C+'cat/'+C+'strLit/'+C+'pt/'+C+'v')]
                series.append({'index':si,'name':name,'categories':cats,'values':vals,'xml':s})
            names=[io['canon'](s['name']) for s in series]
            matches=[identity for identity,c in truth['corrected_model']['charts'].items() if sorted(names)==sorted(io['canon'](s['name']) for s in c['series'])]
            if len(matches)!=1:continue
            identity=matches[0]
            if identity in chart_models:chart_integrity[identity]=False;chart_errors.append('duplicate '+identity);continue
            wanted=truth['corrected_model']['charts'][identity];matched=[];embedded_ok=True
            books=[r for r in records if r.get('context')=='embedded_workbook' and r['locator'].startswith(chart['locator']+'/')]
            if len(books)!=1:embedded_ok=False;book=None
            else:
                part=books[0]['part']
                if part not in cached_books:
                    try:
                        extracted=io['OFFICE']['extract_embedded_xlsx'](path,part,derived/f'embedded-{len(cached_books)+1}'/'source')
                        result=io['OFFICE']['recalculate_xlsx'](extracted['path'],lock,derived/f'embedded-{len(cached_books)+1}'/'calculated')
                        cached_books[part]=io['workbook'](result['path']);embedded_results.append({'extraction':extracted,'recalculation':result})
                    except io['CandidateError'] as e:cached_books[part]=None;chart_errors.append(str(e))
                book=cached_books[part];embedded_ok=book is not None
            for wi,w in enumerate(wanted['series']):
                choices=[s for s in series if io['canon'](s['name'])==io['canon'](w['name'])]
                if len(choices)!=1:embedded_ok=False;continue
                s=choices[0];categories=s['categories'];embedded_ok=embedded_ok and categories==wanted['categories'] and len(s['values'])==len(w['values'])
                for pi,category in enumerate(wanted['categories']):
                    value=s['values'][pi] if pi<len(s['values']) and categories==wanted['categories'] else None
                    loc=chart['locator']+f'/series:{s["index"]+1}/point:{pi}'
                    slots[f'pptx/chart/{identity}/{wi}/{pi}'].append({'value':value,'unit':'万元','locator':loc})
                for role,refkind,expected_values in [('cat','strRef',wanted['categories']),('val','numRef',w['values'])]:
                    ref=s['xml'].find(C+role+'/'+C+refkind+'/'+C+'f')
                    m=re.fullmatch(r"(?:'((?:[^']|'')+)'|([^!]+))!(\$?[A-Z]+\$?\d+):(\$?[A-Z]+\$?\d+)",ref.text or '') if ref is not None else None
                    if not m or book is None:embedded_ok=False;continue
                    sheet=m[1].replace("''", "'") if m[1] else m[2];lo=io['coordinate'](m[3].replace('$',''));hi=io['coordinate'](m[4].replace('$',''))
                    if not lo or not hi or (lo[0]!=hi[0] and lo[1]!=hi[1]):embedded_ok=False;continue
                    actual=[]
                    for row in range(lo[0],hi[0]+1):
                        for col in range(lo[1],hi[1]+1):actual.append(book['rows'].get(sheet,{}).get(row,{}).get(col,{}).get('value'))
                    embedded_ok=embedded_ok and len(actual)==len(expected_values) and all((io['clean'](a)==str(b) if role=='cat' else io['match'](a,b,'1e-8')) for a,b in zip(actual,expected_values))
                    if role=='val':embedded_ok=embedded_ok and len(actual)==len(s['values']) and all(io['match'](a,b,'1e-8') for a,b in zip(actual,s['values']))
                matched.append({'name':s['name'],'categories':categories,'values':s['values']})
            mins=[io['number'](v.get('val')) for v in xml.findall('.//'+C+'valAx/'+C+'scaling/'+C+'min')]
            axis_ok=not mins or all(v is not None and v<=-3 for v in mins)
            chart_models[identity]={'locator':chart['locator'],'series':matched,'axis_min':mins,'cash_axis_ok':axis_ok,'embedded_ok':bool(embedded_ok)}
            chart_integrity[identity]=bool(embedded_ok)
    checks,observed=unique_slots(slots,truth,io)
    expected=[k for k in truth['artifact_nodes'] if k.startswith('pptx/')];checks={k:checks.get(k,False) for k in expected}
    for k,v in observed.items():v['file']=contract['files']['slides'];v['aliases']=[k.split('/')[-1]] if '/kpi/' in k else []
    cash=chart_models.get('CASH_QUARTER',{});cash_visible=bool(cash.get('cash_axis_ok') and checks.get('pptx/chart/CASH_QUARTER/0/1'))
    observed['pptx/chart/CASH_QUARTER/axis']={'file':contract['files']['slides'],'locator':cash.get('locator',''),
        'locators':[cash['locator']] if cash else [],'value':{'axis_min_maximum':-3,'auto_axis_allowed':True} if cash_visible else None,'unit':'direction_or_constraint'}
    visible=' '.join(r.get('text','') for r in records if r.get('context')=='slide')
    protected={key:all(io['canon'](v) in io['canon'](visible) for v in values) for key,values in contract['protected_slide_elements'].items()}
    return {'checks':checks,'observations':observed,'charts':chart_models,'chart_integrity':{k:chart_integrity.get(k,False) for k in truth['source_charts']},
        'chart_errors':chart_errors,'embedded_results':embedded_results,'protection':protected,'cash_axis_ok':cash_visible}
