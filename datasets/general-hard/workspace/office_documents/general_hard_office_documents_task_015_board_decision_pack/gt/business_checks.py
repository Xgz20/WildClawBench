from pathlib import Path
from decimal import Decimal
import json,re

def equal(entries,want,io,contract,field):
    if not entries:return False
    def ok(x):
        got=x.get('observed')
        if isinstance(want,list):return got in want
        if want is None:return got is None
        if isinstance(want,bool):return got is want
        if isinstance(want,str) and field in {'minimum_date','first_violation'}:return got==want
        if got is None or isinstance(got,bool):return False
        try:return abs(Decimal(str(got))-Decimal(str(want)))<=Decimal(contract['ratio_tolerance'] if field in io['RATIOS'] else contract['money_tolerance_cny'])
        except (ValueError,TypeError,ArithmeticError):return False
    return all(ok(e) for e in entries)

def summary(observed,model,cases,fields,io,c):
    return {case:{field:equal(observed.get('cash',{}).get(case,{}).get(field),model[case][field],io,c,field) for field in fields} for case in cases}
def nodes(observed,model,cases,io,c):
    return {case+'/'+r['date']:equal(observed.get('nodes',{}).get(case+'/'+r['date'],{}).get('balance_cny'),r['balance_cny'],io,c,'balance_cny') for case in cases for r in model[case]['rows']}
def history(observed,truth,io,c):
    return {identity:{field:equal(observed.get('historical',{}).get(identity,{}).get(field),truth['historical_metrics'][identity][field],io,c,field) for field in fields} for identity,fields in c['historical_required'].items()}
def average_rows(d,io):return io['mean'](io['mean'](v.values()) for v in d.values())

def input_parameters(original,truth,io,c):
    wants={'initial_cash_cny':truth['cash']['initial_cny'],'floor_cny':truth['cash']['floor_cny']}
    return {key:equal(original.get('inputs',{}).get(key),value,io,c,key) for key,value in wants.items()}

def responses(source,original,truth,model,cases,io,contract,lock,derived):
    office=io['OFFICE'];records=[]
    for spec in contract['response_specs']:
        param=spec['parameter'];inputs=original.get('inputs',{}).get(param,[]);edits={};invalid=[]
        for e in inputs:
            raw=io['scalar'](e.get('stored_value',e.get('value')),'initial_cash_cny',contract=contract)
            if not e.get('sheet') or not e.get('cell') or e.get('formula') or raw in {None,0} or e.get('observed') is None:
                invalid.append(e.get('locator'));continue
            factor=Decimal(str(e['observed']))/raw
            if factor<=0:invalid.append(e.get('locator'));continue
            value=Decimal(spec['value'])/factor
            edits[(e['sheet'],e['cell'])]={'sheet':e['sheet'],'cell':e['cell'],'value':str(value)}
        if not edits or invalid:
            records.append({'name':spec['name'],'parameter':param,'score':0.,'reason':'missing or ambiguous editable numeric parameter','invalid':invalid});continue
        changes=list(edits.values());prepared=office['prepare_xlsx_counterfactual'](source,changes,derived/spec['name']/'prepared')
        office['verify_xlsx_counterfactual'](source,prepared['path'],prepared['audit'])
        recalc=office['recalculate_xlsx'](prepared['path'],lock,derived/spec['name']/'recalculated',timeout_seconds=90)
        observed=io['observe'](io['workbook'](recalc['path'],contract)['grids'],contract)
        changed=model['cash_model'](truth,initial=spec['value'] if param=='initial_cash_cny' else None,floor=spec['value'] if param=='floor_cny' else None)
        sums=summary(observed,changed,cases,contract['required_cash_summary'],io,contract);ns=nodes(observed,changed,cases,io,contract)
        # Credit dependency only where this input is expected to change the output.
        baseline=model['cash_model'](truth);affected_summary={case:{field:ok for field,ok in fields.items() if changed[case][field]!=baseline[case][field]} for case,fields in sums.items()}
        old_nodes={case+'/'+r['date']:r['balance_cny'] for case in cases for r in baseline[case]['rows']}
        new_nodes={case+'/'+r['date']:r['balance_cny'] for case in cases for r in changed[case]['rows']}
        affected_nodes={key:ok for key,ok in ns.items() if new_nodes[key]!=old_nodes[key]}
        affected=[v for fields in affected_summary.values() for v in fields.values()]+list(affected_nodes.values())
        if not affected:raise ValueError('private input response has no affected result')
        score=io['mean'](affected)
        records.append({'name':spec['name'],'parameter':param,'changes':changes,'score':score,'summary':sums,'nodes':ns,'affected_summary':affected_summary,'affected_nodes':affected_nodes,'affected_check_count':len(affected),'prepared':prepared,'recalculation':recalc})
    return {'score':io['mean'](r['score'] for r in records),'cases':records,'limit':'actual cash model response only; no automatic re-optimization of recommendation required'}

def merge_prose(observed,prose):
    for case,values in prose.items():
        target=observed['cash'].setdefault(case,{})
        for field,entries in values.items():target.setdefault(field,[]).extend(entries)

def json_recommendation(value,io,c):
    result=[]
    def visit(node):
        if isinstance(node,dict):
            for k,v in node.items():
                if io['canon'](k) in {'selectedoption','selectedcase','推荐方案','本轮建议','选择方案','recommendation'} and isinstance(v,str):
                    found=io['case_id'](v,c)
                    if found:result.append(found)
                else:visit(v)
        elif isinstance(node,list):
            for v in node:visit(v)
    visit(value);return result

def recommendation_checks(word_rows,deck_rows,json_value,cash_observed,truth,io,c):
    sources={'word':[r['case_id'] for r in word_rows],'deck':[r['case_id'] for r in deck_rows],'evidence':json_recommendation(json_value,io,c)}
    safe=set(truth['cash']['admissible_recommendations']);primary={k:v[0] if v else None for k,v in sources.items()}
    approved={k:bool(v) and all(x in safe for x in v) for k,v in sources.items()}
    chosen=primary['word'];agreement=chosen is not None and all(v==chosen for v in primary.values())
    # The original plans remain mandatory. A chosen allowed adjustment also needs a numeric model.
    modeled=chosen in {'C'} or chosen in {'A_phase1','A_deferred'} and chosen in cash_observed.get('cash',{})
    return {'primary':primary,'all_explicit':sources,'safe':approved,'agreement':agreement,'selected_adjustment_modeled':modeled,
            'score':io['mean']([*approved.values(),agreement,modeled]),'selected':chosen}

def evidence_checks(value,root,word,deck,book,truth,io,contract):
    if not isinstance(value,(dict,list)):return {'score':0.,'citations':[],'reason':'missing or invalid index'}
    source_names={'operations.xlsx','interviews.docx','market_notes.pdf','decision_constraints.md'}
    targets={'memo.docx','options.xlsx','deck.pptx'};source_text={}
    source_word=io['word'](root/'interviews.docx')
    source_text['interviews.docx']='\n'.join(p['text'] for p in source_word['paragraphs'])
    source_text['decision_constraints.md']=(root/'decision_constraints.md').read_text()
    source_text['market_notes.pdf']='\n'.join(str(x.get('text','')) for x in io['projection'](root/'market_notes.pdf'))
    source_book=io['workbook'](root/'operations.xlsx',contract)
    source_cells={r['locator']:r.get('value') for r in source_book['records'] if '!' in r['locator']}
    source_sheets=source_book['sheet_states'];word_text='\n'.join(p['text'] for p in word['paragraphs']) if word else ''
    deck_text='\n'.join(p['text'] for p in deck['paragraphs']) if deck else ''
    candidate_records=book['records'] if book else []
    citations=[];all_strings=[]
    def visit(node):
        if isinstance(node,str):all_strings.append(node)
        elif isinstance(node,list):
            for n in node:visit(n)
        elif isinstance(node,dict):
            name=next((node[k] for k in node if io['canon'](k) in {'file','sourcefile','path','文件','源文件','来源文件','产物'} and isinstance(node[k],str)),None)
            loc=next((node[k] for k in node if io['canon'](k) in {'locator','sourcelocator','location','位置','定位','源定位'} and isinstance(node[k],str)),None)
            if name and loc:
                filename=io['clean'](name).removeprefix('/tmp_workspace/').removeprefix('results/');valid=False;kind='unknown'
                if filename in source_names:
                    kind='source'
                    if filename=='operations.xlsx':
                        anchors=re.findall(r"(?:'?([^!;]+)'?)!([A-Z]+\d+)(?::([A-Z]+\d+))?",loc)
                        valid=bool(anchors) and all(sheet.strip(" '") in source_sheets and sheet.strip(" '")+'!'+cell in source_cells for sheet,cell,_ in anchors)
                    elif filename=='interviews.docx':
                        ids=re.findall(r'\b[IG]\d\d\b',loc)
                        valid=bool(ids) and all(x in source_text[filename] for x in ids)
                    elif filename=='decision_constraints.md':
                        ids=re.findall(r'\bD\d\d\b',loc);valid=bool(ids) and all(x in source_text[filename] for x in ids)
                    else:
                        pages=re.findall(r'(?:page|页)\s*(\d+)',loc,re.I);ids=re.findall(r'\bM\d\d\b',loc)
                        valid=bool(pages or ids) and all(p=='1' for p in pages) and all(x in source_text[filename] for x in ids)
                    excerpt=next((v for k,v in node.items() if io['canon'](k) in {'excerpt','quote','引文','原文'} and isinstance(v,str)),None)
                    if excerpt and filename in source_text:valid=valid and io['canon'](excerpt) in io['canon'](source_text[filename])
                elif filename in targets:
                    kind='deliverable'
                    if filename=='memo.docx' and word:
                        if loc in word['nodes']:valid=True
                        else:
                            parts=[io['canon'](p) for p in re.split(r'[/;；]',loc) if len(io['canon'](p))>1]
                            valid=bool(parts) and all(p in io['canon'](word_text) for p in parts)
                    elif filename=='deck.pptx' and deck:
                        pages=re.findall(r'(?:slide|页|幻灯片)\s*:?\s*(\d+)',loc,re.I)
                        valid=bool(pages) and all(1<=int(n)<=deck['slide_count'] for n in pages)
                    elif filename=='options.xlsx' and book:
                        anchors=re.findall(r"(?:'?([^!;]+)'?)!([A-Z]+\d+)(?::([A-Z]+\d+))?",loc)
                        if anchors:valid=all(any(r.get('locator')==sheet.strip(" '")+'!'+cell for r in candidate_records) for sheet,cell,_ in anchors)
                        else:
                            clauses=[s.strip() for s in loc.split(';')]
                            valid=all(any(sheet in clause for sheet in book['sheet_states']) for clause in clauses)
                            for clause in clauses:
                                m=re.search(r'case_id\s+([A-Za-z0-9_]+)',clause)
                                if m:valid=valid and m[1] in io['observe'](book['grids'],contract)['cash']
                citations.append({'file':filename,'locator':loc,'kind':kind,'valid':valid})
            for v in node.values():visit(v)
    visit(value)
    known=citations
    source_coverage={name:any(x['valid'] and x['file']==name for x in known) for name in source_names}
    target_coverage={name:any(x['valid'] and x['file']==name for x in known) for name in targets}
    groups=set(re.findall(r'\bG0[1-6]\b',' '.join(all_strings)))
    for i in map(int,re.findall(r'\bI(0[1-9]|1[0-2])\b',' '.join(all_strings))):groups.add('G'+str((i+1)//2).zfill(2))
    score=.4*io['mean'](x['valid'] for x in known)+.25*io['mean'](source_coverage.values())+.2*io['mean'](target_coverage.values())+.15*len(groups)/6 if known else 0.
    return {'score':score,'citations':citations,'source_coverage':source_coverage,'target_coverage':target_coverage,'public_groups':sorted(groups),
            'limit':'existence, quotation and index coverage only; semantic support and wrong existing nodes require independent Judge'}
