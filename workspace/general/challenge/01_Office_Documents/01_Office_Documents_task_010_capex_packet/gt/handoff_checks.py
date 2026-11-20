"""Actual native handoff facts, valid dates and evidence nodes, not prose judging."""
from datetime import date,timedelta
from collections import defaultdict
import re

def mapping(value):return value if isinstance(value,dict) else {}
def records(value):return value if isinstance(value,list) else []
def date_value(value):
    if not isinstance(value,str):return None
    m=re.fullmatch(r'\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?(?:\s*[（(]周.[)）])?\s*',value)
    if not m:return None
    try:return date(*map(int,m.groups())).isoformat()
    except ValueError:return None

def schedule_check(schedule,choice,expected,ids):
    checks={};used=defaultdict(list)
    for identity in ids:
        p,e=identity.split('-');vendor=choice.get(identity);quote=expected['quotes'].get(vendor)
        raw=schedule.get(identity);days=[date_value(v) for v in raw] if isinstance(raw,list) else []
        phase=expected['phases'][p];wanted=phase['quantities'][e]*quote[e]['crew_days_per_unit'] if quote else None
        valid=bool(quote and days and None not in days and len(days)==wanted and len(set(days))==len(days))
        if valid:
            start=date.fromisoformat(phase['start']);end=date.fromisoformat(phase['end']);allowed=[]
            while start<=end:
                if start.weekday()<5 and start.isoformat() not in phase['blackouts']:allowed.append(start.isoformat())
                start+=timedelta(days=1)
            ready=(date.fromisoformat(phase['order_date'])+timedelta(days=quote['lead_days'])).isoformat()
            valid=all(d in allowed and d>=ready for d in days)
            if valid:
                indexes=[allowed.index(d) for d in days];valid=indexes==list(range(indexes[0],indexes[0]+len(indexes)))
            for d in days:used[d].append(identity)
        checks[identity]=valid
    for values in used.values():
        if len(values)>1:
            for identity in values:checks[identity]=False
    return checks

def source_ref(ref,root,io):
    if not isinstance(ref,str):return False
    ref=ref.removeprefix('/tmp_workspace/');file,sep,fragment=ref.partition('#')
    if file not in {'constraints.md','baseline.xlsx','quotes/quote_A.pdf','quotes/quote_B.pdf','quotes/quote_C.pdf'} or not (root/file).is_file():return False
    if file=='constraints.md':return bool(re.fullmatch(r'C0[1-5]',fragment) and '## '+fragment in (root/file).read_text())
    if file.startswith('quotes/'):
        vendor=file[-5];return bool(re.fullmatch(r'page:1(?:/Q'+vendor+r'-0[1-7])?',fragment))
    if file=='baseline.xlsx':
        m=re.fullmatch(r'(Assets|Energy)/(?:rows?:)?(\d+)(?:-(\d+))?',fragment)
        if not m:return False
        low=int(m[2]);high=int(m[3] or m[2]);return 6<=low<=high<= (17 if m[1]=='Assets' else 10)
    return False

def quoted_refs(refs,p,vendor,root,io,section='C01'):
    refs=[r.removeprefix('/tmp_workspace/') if isinstance(r,str) else r for r in records(refs)]
    return bool(refs and all(source_ref(r,root,io) for r in refs)
        and any(r.startswith(f'quotes/quote_{vendor}.pdf#page:1') for r in refs)
        and 'constraints.md#'+section in refs)

def analyze(ledger,word_rows,html_rows,word_blocks,html_blocks,choice,expected,contract,root,io):
    ids=contract['line_ids'];ledger=mapping(ledger);totals=mapping(ledger.get('phase_totals'));selected=mapping(ledger.get('selected_vendors'))
    budget_checks={}
    for kind,rows in [('application',word_rows),('plan',html_rows)]:
        for p in ['P1','P2']:
            row=rows.get(p);values=mapping(row.get('values')) if row else {}
            wanted=expected['recommended']['phases'][p]
            budget_checks[kind+'/'+p]=all(io['match'](values.get(k),wanted[k]) for k in ['capex','opex','total_cash'])
    for p in ['P1','P2']:
        values=mapping(totals.get(p));wanted=expected['recommended']['phases'][p]
        budget_checks['ledger/'+p]=all(io['match'](values.get(k),wanted[k]) for k in ['capex','opex','total_cash'])
    budget_checks['ledger/selection']=set(selected)==set(ids) and all(io['clean'](selected.get(id)).upper()==choice.get(id) for id in ids)
    claimed_schedule={};schedule_duplicates=[];reference_checks=[]
    for raw in records(ledger.get('schedule')):
        row=mapping(raw);identity=io['clean'](row.get('line_id')).upper()
        if identity in claimed_schedule:schedule_duplicates.append(identity)
        claimed_schedule[identity]=row.get('work_dates')
        reference_checks.append(quoted_refs(row.get('source_refs'),identity.split('-')[0],choice.get(identity),root,io))
    for identity in schedule_duplicates:claimed_schedule[identity]=None
    word_schedule=io['schedules'](word_blocks);html_schedule=io['schedules'](html_blocks)
    schedules={'ledger':claimed_schedule,'application':word_schedule,'plan':html_schedule};schedule_checks={}
    for kind,rows in schedules.items():
        checks=schedule_check(rows,choice,expected,ids)
        for id in ids:
            other=claimed_schedule.get(id);actual=rows.get(id)
            checks[id]=checks[id] and bool(isinstance(other,list) and isinstance(actual,list)
                and [date_value(v) for v in actual]==[date_value(v) for v in other])
        schedule_checks[kind]=checks
    unknowns=mapping(ledger.get('unknowns'));gates=mapping(ledger.get('gates'))
    unknown_checks={k:k in unknowns and unknowns[k] is None for k in ['new_equipment_kwh','annual_savings','payback_years']}
    gate_checks={k:io['key'](gates.get(k)) in {'pending','待确认','待审批','未完成'} for k in ['supplier_approval','p1_acceptance','p2_release']}
    next_check=bool(isinstance(unknowns.get('next_checks'),str) and len(unknowns['next_checks'].strip())>=8)
    claim_pattern=r'(?:年度(?:节约|节省)(?:额|金额)?|(?:投资)?回收期|新设备(?:实测)?能耗)\s*(?:[=:：]|为|约)?\s*[¥￥]?\s*[0-9]'
    unsupported={kind:bool(re.search(claim_pattern,'\n'.join(blocks))) for kind,blocks in [('application',word_blocks),('plan',html_blocks)]}
    exclusions={};exclusion_refs=[]
    for raw in records(ledger.get('quote_exclusions')):
        row=mapping(raw);identity=(io['clean'](row.get('phase')).upper(),io['clean'](row.get('vendor')).upper())
        if identity in exclusions:exclusions[identity]=None
        else:exclusions[identity]=row
    for p,v in [('P2','A'),('P1','C'),('P2','C')]:
        row=exclusions.get((p,v));exclusion_refs.append(bool(row and quoted_refs(row.get('source_refs'),p,v,root,io,'C02')))
    return {'budget_checks':budget_checks,'schedule_checks':schedule_checks,'schedule_sources':schedules,
        'schedule_reference_checks':reference_checks,'unknown_checks':unknown_checks,'gate_checks':gate_checks,'next_check_present':next_check,
        'unsupported_numeric_claims':unsupported,'exclusion_checks':[bool(exclusions.get(k) and io['clean'](exclusions[k].get('reason'))) for k in [('P2','A'),('P1','C'),('P2','C')]],
        'exclusion_reference_checks':exclusion_refs,'scope_ok':set(claimed_schedule)==set(ids) and set(totals)=={'P1','P2'} and set(exclusions)=={('P2','A'),('P1','C'),('P2','C')}}

def workbook_ref(ref,phase,table,ledger_values,io):
    if not isinstance(ref,str) or not table:return False
    ref=ref.removeprefix('budget.xlsx#');m=re.fullmatch(r"(?:'((?:[^']|'')+)'|([^!]+))!(\$?[A-Z]+\$?[1-9][0-9]*)(?::(\$?[A-Z]+\$?[1-9][0-9]*))?",ref)
    if not m:return False
    sheet=m[1].replace("''", "'") if m[1] else m[2]
    lo=io['coordinate'](m[3].replace('$',''));hi=io['coordinate']((m[4] or m[3]).replace('$',''))
    if sheet!=table['sheet'] or lo[0]>hi[0] or lo[1]>hi[1]:return False
    cells=[table['cells'].get(k) for k in ['phase','capex','opex','total_cash']]
    return all(c and lo[0]<=c['row']<=hi[0] and lo[1]<=c['col']<=hi[1] for c in cells) and all(io['match'](table['values'].get(k),ledger_values.get(k)) for k in ['capex','opex','total_cash'])

def word_ref(ref,row,ledger_values,model,io):
    if not isinstance(ref,str) or not row:return False
    tokens=[t.strip().removeprefix('application.docx#') for t in ref.split(';')];selected=[]
    for token in tokens:
        if token in model['nodes']:
            node=model['nodes'][token]
            if node['kind']=='table':selected.extend(c['text'] for r in node['rows'] for c in r['cells'])
            elif node['kind']=='cell':selected.append(node['text'])
            elif node['kind']=='paragraph':selected.append(node['text'])
        else:
            m=re.fullmatch(r'(table:[0-9]+)/row:([0-9]+)',token)
            table=model['nodes'].get(m[1]) if m else None
            if table and 1<=int(m[2])<=len(table['rows']):selected.extend(c['text'] for c in table['rows'][int(m[2])-1]['cells'])
            else:return False
    blob=io['canon'](' '.join(selected));values=mapping(row['values'])
    return io['canon'](values.get('phase')) in blob and all(io['match'](values.get(k),ledger_values.get(k)) and io['canon'](values.get(k)) in blob for k in ['capex','opex','total_cash'])

def html_ref(ref,row,ledger_values,io):
    if not isinstance(ref,str) or not row:return False
    ref=ref.removeprefix('plan.html');m=re.fullmatch(r'#([A-Za-z][\w-]*)(?:/tbody/tr:([1-9][0-9]*))?',ref)
    if not m or row['table']['attrs'].get('id')!=m[1]:return False
    # Resolve actual tbody row numbers independently of header depth and spans.
    body_row=row['table'].get('body_rows',{}).get(row['physical_row'],row['physical_row']-1)
    if m[2] and int(m[2])!=body_row:return False
    return all(io['match'](mapping(row['values']).get(k),ledger_values.get(k)) for k in ['capex','opex','total_cash'])

def evidence(ledger,tables,word_rows,html_rows,word_model,choice,root,io):
    ledger=mapping(ledger);totals=mapping(ledger.get('phase_totals'));evidence_rows={}
    for raw in records(ledger.get('evidence')):
        row=mapping(raw);p=io['clean'](row.get('phase')).upper()
        evidence_rows[p]=None if p in evidence_rows else row
    checks={}
    for p in ['P1','P2']:
        row=evidence_rows.get(p) or {};values=mapping(totals.get(p));refs=[r.removeprefix('/tmp_workspace/') if isinstance(r,str) else r for r in records(row.get('source_refs'))]
        checks[p]={'budget_node':workbook_ref(row.get('budget_ref'),p,tables['phases']['rows'].get(p),values,io),
            'application_node':bool(word_model and word_ref(row.get('application_ref'),word_rows.get(p),values,word_model,io)),
            'html_node':html_ref(row.get('html_ref'),html_rows.get(p),values,io),
            'sources':bool(refs and all(source_ref(r,root,io) for r in refs) and 'constraints.md#C03' in refs
                and any(r.startswith('baseline.xlsx#Assets/') for r in refs)
                and all(any(r.startswith(f'quotes/quote_{v}.pdf#page:1') for r in refs) for v in {choice.get(p+'-CL'),choice.get(p+'-FAN')}))}
    return checks
