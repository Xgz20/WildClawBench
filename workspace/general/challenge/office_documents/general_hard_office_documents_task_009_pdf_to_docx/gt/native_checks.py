"""Source-key alignment; does not assume fixed Word indices or note package IDs."""
from pathlib import Path
from collections import Counter,defaultdict
from decimal import Decimal,InvalidOperation
import re,runpy

WORD=runpy.run_path(str(Path(__file__).with_name('word_model.py')))
read_document=WORD['read_document'];CandidateWordError=WORD['CandidateWordError'];canon=WORD['canon']
def mean(values):return sum(values)/len(values) if values else 0.
def equal(actual,wanted,repeat=False):
    a,b=canon(actual),canon(wanted)
    if a==b:return True
    if re.fullmatch(r'[ARMX]\d{2}',b,re.I):return a.upper()==b.upper()
    if repeat:
        a=re.sub(r'\(续\)$','',a)
        if a==b or b and a==b*(len(a)//len(b)):return True
    number=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
    if re.fullmatch(number,a) and re.fullmatch(number,b):
        try:return Decimal(a)==Decimal(b)
        except InvalidOperation:return False
    return False

def expand_expected(table):
    rows=len(table['header_rows'])+len(table['rows']);cols=len(table['columns']);matrix=[[None]*cols for _ in range(rows)]
    for anchor in table['anchors']:
        for r in range(anchor['row'],anchor['row']+anchor['rowspan']):
            for c in range(anchor['column'],anchor['column']+anchor['colspan']):matrix[r][c]=anchor
    return matrix

def analyze(document,expected):
    nodes=document['nodes'];parts=[];row_lookup={};tables_by_source=defaultdict(list)
    expected_matrices={identity:expand_expected(table) for identity,table in expected['tables'].items()}
    for identity,table in expected['tables'].items():
        keycol=1 if identity in {'T01','T02'} else 0
        for index,row in enumerate(table['rows']):row_lookup[row[keycol].upper()]=(identity,len(table['header_rows'])+index)
    data_cells=set();row_occurrences=Counter();unexpected_rows=[];part_cells={};table_rows_by_source=defaultdict(lambda:defaultdict(set))
    for table in document['tables']:
        anchors={a['locator']:a for a in table['anchors']};current=None;pending=[]
        for row in table['rows']:
            ids={canon(c['text']).upper() for c in row['cells'] if re.fullmatch(r'[ARMX]\d{2}',canon(c['text']),re.I)}
            known=ids&set(row_lookup)
            if len(known)==1:
                uid=next(iter(known));identity,source_row=row_lookup[uid];row_occurrences[uid]+=1
                if current is None or current['source_id']!=identity or any(canon(c['text']) for p in pending for c in p['cells']):
                    current={'source_id':identity,'table':table['number'],'locator':table['locator'],'header_candidates':pending,
                        'data_rows':[],'anchors':anchors,'native_table':table}
                    parts.append(current);tables_by_source[identity].append(current)
                current['data_rows'].append({'row':row,'uid':uid,'source_row':source_row});pending=[]
                for cell in row['cells']:data_cells.add(cell['locator'])
                table_rows_by_source[table['locator']][identity].add(uid)
            else:
                if ids:unexpected_rows.append({'table':table['number'],'row':row['index'],'ids':sorted(ids)})
                pending.append(row)
    table_values={};header_values={};merge_checks={};numeric_checks={};source_orders={};caption_checks={};unexpected_merges={}
    contexts=defaultdict(list);part_positions=[];unit_rows=defaultdict(set);node_rows=defaultdict(lambda:defaultdict(set));node_fields=defaultdict(lambda:defaultdict(set))
    for identity,table in expected['tables'].items():
        matrix=expected_matrices[identity];h=len(table['header_rows']);cols=len(table['columns'])
        data_scores={f'{r}:{c}':0. for r in range(h,len(matrix)) for c in range(cols)}
        header_scores={f'{r}:{c}':0. for r in range(h) for c in range(cols)}
        merge_states={(a['row'],a['column']):{'anchor':a,'valid_rows':set(),'headers':[]} for a in table['anchors'] if a['rowspan']>1 or a['colspan']>1}
        observed_uids=[];extra_shapes=[]
        for part in tables_by_source[identity]:
            observed_uids.extend(r['uid'] for r in part['data_rows'])
            part_positions.append((part['data_rows'][0]['row']['position']-.5,identity))
            all_rows=part['header_candidates']+[r['row'] for r in part['data_rows']]
            used={cell['anchor'] for row in all_rows for cell in row['cells']}
            # Native column grids may contain finer subdivisions than visible
            # cells. Normalize using actual cell edges, not declared grid count.
            edges=sorted({value for key in used for value in (part['anchors'][key]['column'],part['anchors'][key]['column']+part['anchors'][key]['colspan'])})
            if len(edges)!=cols+1:
                patterns=Counter()
                for row in all_rows:
                    ids={c['anchor'] for c in row['cells']}
                    candidates=tuple(sorted({value for key in ids for value in (part['anchors'][key]['column'],part['anchors'][key]['column']+part['anchors'][key]['colspan'])}))
                    if len(candidates)==cols+1:patterns[candidates]+=1
                if patterns:edges=list(patterns.most_common(1)[0][0])
                elif part['native_table']['declared_columns'] and part['native_table']['declared_columns']%cols==0:
                    factor=part['native_table']['declared_columns']//cols;edges=[1+i*factor for i in range(cols+1)]
            column_ok=len(edges)==cols+1
            part['column_ok']=column_ok;part['edges']=edges
            if not column_ok:continue
            row_intervals={}
            for row in all_rows:
                ordered=list(dict.fromkeys(c['anchor'] for c in row['cells']))
                if len(ordered)==cols:
                    # Same visible column count/order can have row-local grid
                    # refinements or widths. Those do not merge source cells.
                    row_intervals[row['index']]={key:(i,i+1) for i,key in enumerate(ordered)}
                else:
                    row_intervals[row['index']]={key:(edges.index(part['anchors'][key]['column']),edges.index(part['anchors'][key]['column']+part['anchors'][key]['colspan']))
                        for key in ordered if part['anchors'][key]['column'] in edges and part['anchors'][key]['column']+part['anchors'][key]['colspan'] in edges}
            def cell_at(row,column):
                for cell in row['cells']:
                    anchor=part['anchors'][cell['anchor']]
                    if cell['anchor'] not in row_intervals[row['index']]:continue
                    start,end=row_intervals[row['index']][cell['anchor']]
                    if start<=column<end:return anchor
                return None
            header_mapping={};quality={}
            for row in part['header_candidates']:
                scores=[mean([float(equal((cell_at(row,c) or {}).get('text',''),matrix[r][c]['text'],matrix[r][c]['rowspan']>1)) for c in range(cols)]) for r in range(h)]
                best=max(range(h),key=lambda r:scores[r])
                if scores[best]>.45 and scores[best]>quality.get(best,-1):header_mapping[best]=row;quality[best]=scores[best]
            mapped_rows={row['index']:r for r,row in header_mapping.items()}
            mapped_rows.update({item['row']['index']:item['source_row'] for item in part['data_rows']})
            for r,row in header_mapping.items():
                for cell in row['cells']:data_cells.add(cell['locator'])
                for c in range(cols):header_scores[f'{r}:{c}']=max(header_scores[f'{r}:{c}'],float(equal((cell_at(row,c) or {}).get('text',''),matrix[r][c]['text'],matrix[r][c]['rowspan']>1)))
            for item in part['data_rows']:
                r=item['source_row'];row=item['row'];unit_rows[identity].add(item['uid'])
                node_rows[part['locator']][identity].add(item['uid'])
                node_fields[part['locator']][identity].update((item['uid'],c) for c in range(cols))
                for c in range(cols):
                    anchor=cell_at(row,c);wanted=matrix[r][c]
                    score=float(anchor is not None and equal(anchor['text'],wanted['text'],wanted['rowspan']>1))
                    if row_occurrences[item['uid']]!=1:score=0.
                    data_scores[f'{r}:{c}']=max(data_scores[f'{r}:{c}'],score)
                for cell in row['cells']:
                    node_rows[cell['locator']][identity].add(item['uid'])
            actual_shapes=set()
            for key in used:
                anchor=part['anchors'][key]
                rows=tuple(sorted(mapped_rows[r] for r in mapped_rows if anchor['row']<=r<anchor['row']+anchor['rowspan']))
                intervals=[mapping[key] for r,mapping in row_intervals.items() if r in mapped_rows and key in mapping]
                columns=tuple(sorted({c for start,end in intervals for c in range(start,end)}))
                if rows and columns and not anchor.get('invalid_merge'):actual_shapes.add((rows,columns))
                data_targets=[r for r in part['data_rows'] if anchor['row']<=r['row']['index']<anchor['row']+anchor['rowspan']]
                if data_targets:
                    context={'table':identity,'records':sorted({r['uid'] for r in data_targets}),'columns':list(columns)}
                    for member in anchor['members']:contexts[member].append(context)
                    for member in anchor['members']:
                        node_fields[member][identity].update((uid,c) for uid in context['records'] for c in context['columns'])
            source_rows=set(mapped_rows.values())
            permitted_shapes=set()
            for source_anchor in table['anchors']:
                covered=tuple(r for r in range(source_anchor['row'],source_anchor['row']+source_anchor['rowspan']) if r in source_rows)
                if source_anchor['row']<h:covered=tuple(range(source_anchor['row'],source_anchor['row']+source_anchor['rowspan']))
                columns=tuple(range(source_anchor['column'],source_anchor['column']+source_anchor['colspan']))
                if covered:permitted_shapes.add((covered,columns))
            for rows,columns in actual_shapes-permitted_shapes:
                if len(rows)>1 or len(columns)>1:extra_shapes.append({'word_table':part['table'],'source_rows':list(rows),'source_columns':list(columns)})
            for anchor in table['anchors']:
                if anchor['rowspan']==1 and anchor['colspan']==1:continue
                covered=tuple(r for r in range(anchor['row'],anchor['row']+anchor['rowspan']) if r in source_rows)
                if not covered:continue
                # Missing header rows are a loss; continuation cuts only apply
                # to data groups, never erase the source's header hierarchy.
                if anchor['row']<h:covered=tuple(range(anchor['row'],anchor['row']+anchor['rowspan']))
                columns=tuple(range(anchor['column'],anchor['column']+anchor['colspan']))
                state=merge_states[(anchor['row'],anchor['column'])];valid=(covered,columns) in actual_shapes
                if anchor['row']<h:state['headers'].append(float(valid))
                elif valid:state['valid_rows'].update(covered)
            part['header_mapping']={str(k):row['index'] for k,row in header_mapping.items()}
            part['mapped_rows']=mapped_rows
        expected_uids=[row[1] if identity in {'T01','T02'} else row[0] for row in table['rows']]
        source_orders[identity]=float(observed_uids==expected_uids)
        caption_checks[identity]=float(any(canon(table['caption']) in canon(p['text']) and identity in p['text'].upper() for p in document['paragraphs']))
        table_values[identity]=data_scores;header_values[identity]=header_scores
        merge_checks[identity]=[min(state['headers']) if state['anchor']['row']<h and len(state['headers'])==len(tables_by_source[identity]) and state['headers']
            else 0. if state['anchor']['row']<h else len(state['valid_rows'])/state['anchor']['rowspan'] for state in merge_states.values()]
        unexpected_merges[identity]=extra_shapes
        if identity=='T02':
            for r in range(h,len(matrix)):
                for c in [2,3,4]:numeric_checks[f'{r}:{c}']=data_scores[f'{r}:{c}']

    # Source paragraphs may be split across native paragraphs, or several
    # source paragraphs may share a native paragraph. Preserve their order and
    # actual character offsets for note attachments instead of fixed indices.
    body_events=[];source_texts=defaultdict(list);node_units=defaultdict(set);segments=defaultdict(list);extra=[]
    for p in document['paragraphs']:
        cell=p['parent_cell']
        if cell in data_cells:continue
        text=p['text'];matches=list(re.finditer(r'\[(S\d{2})\]',text,re.I))
        if matches:
            if text[:matches[0].start()].strip():extra.append(text[:matches[0].start()])
            for i,match in enumerate(matches):
                identity=match[1].upper();end=matches[i+1].start() if i+1<len(matches) else len(text)
                if identity in expected['paragraphs']:body_events.append({'position':p['position']+match.start()/max(1,len(text))*.1,'id':identity,'text':text[match.end():end],'node':p['locator'],'start':match.start(),'end':end})
            continue
        exact=next((identity for identity,record in expected['paragraphs'].items() if canon(text)==canon(record['text'])),None)
        if exact:body_events.append({'position':p['position'],'id':exact,'text':text,'node':p['locator'],'start':0,'end':len(text)});continue
        is_caption=any(canon(t['caption']) in canon(text) for t in expected['tables'].values())
        if is_caption:body_events.append({'position':p['position'],'id':None,'caption':True,'text':text,'node':p['locator']});continue
        if text.strip():body_events.append({'position':p['position'],'id':None,'text':text,'node':p['locator'],'start':0,'end':len(text)})
    body_events.extend({'position':position,'id':identity,'table':True} for position,identity in part_positions)
    body_events.sort(key=lambda r:r['position']);observed_order=[];open_unit=None
    for event in body_events:
        identity=event['id']
        if identity:
            if not event.get('table'):
                source_texts[identity].append(event['text']);node_units[event['node']].add(identity)
                segments[event['node']].append({'id':identity,'start':event.get('start',0),'end':event.get('end',len(event['text']))})
            if not observed_order or observed_order[-1]!=identity:observed_order.append(identity)
            open_unit=None if event.get('table') or identity.startswith('H') else identity
        elif event.get('caption'):open_unit=None
        elif open_unit:
            source_texts[open_unit].append(event['text']);node_units[event['node']].add(open_unit)
            segments[event['node']].append({'id':open_unit,'start':0,'end':len(event['text'])})
        else:extra.append(event['text'])
    paragraph_checks={};id_checks={}
    for identity,wanted in expected['paragraphs'].items():
        actual=''.join(source_texts.get(identity,[]));a,b=canon(actual),canon(wanted['text'])
        paragraph_checks[identity]=1. if a==b else .5 if b and b in a else 0.
        if identity.startswith('S') and identity!='S00':id_checks[identity]=float(any(re.search(r'\['+identity+r'\]',p['text'],re.I) for p in document['paragraphs']))
    positions={identity:i for i,identity in enumerate(observed_order)}
    order_checks=[float(a in positions and b in positions and positions[a]<positions[b]) for a,b in zip(expected['body_order'],expected['body_order'][1:])]
    note_matches=defaultdict(list);note_labels={}
    for key,note in document['notes'].items():
        if note['kind']!='footnote' or note['type']!='normal':continue
        labels=set(re.findall(r'\[(F\d{2})\]',note['text'],re.I));labels={s.upper() for s in labels}
        if len(labels)==1:
            identity=next(iter(labels));note_matches[identity].append(note);note_labels[key]=identity
        elif not labels:
            matches=[n['id'] for n in expected['footnotes'] if equal(note['text'],n['text'])]
            if len(matches)==1:note_matches[matches[0]].append(note);note_labels[key]=matches[0]
    references=defaultdict(list)
    for p in document['paragraphs']:
        for ref in p['references']:
            location={'node':p['locator'],'available':ref['available']}
            if p['parent_cell'] in contexts:
                location['contexts']=contexts[p['parent_cell']]
            else:
                source=next((s['id'] for s in segments[p['locator']] if s['start']<=ref['offset']<=s['end']),None)
                location['paragraph']=source
            references[ref['note_locator']].append(location)
    note_checks={};note_nodes={}
    for wanted in expected['footnotes']:
        identity=wanted['id'];candidates=note_matches.get(identity,[]);text_ok=attachment_ok=label_ok=False
        if len(candidates)==1:
            note=candidates[0];key=note['locator'];note_nodes[identity]=key
            text_ok=equal(note['text'],wanted['text']);label_ok=bool(re.search(r'\['+identity+r'\]',note['text'],re.I))
            refs=references.get(key,[]);target=wanted['target'];correct=[]
            for ref in refs:
                if 'paragraph' in target:ok=ref.get('paragraph')==target['paragraph'] and ref['available']
                else:ok=ref['available'] and any(c['table']==target['table'] and c['records']==[target['record']] and c['columns']==[target['column']] for c in ref.get('contexts',[]))
                correct.append(ok)
            attachment_ok=len(correct)==1 and all(correct)
            node_units[key].add(identity)
        note_checks[identity]={'text':float(text_ok),'attachment':float(attachment_ok),'source_label':float(label_ok),
            'package_locator':note_nodes.get(identity),'actual_reference_count':len(references.get(note_nodes.get(identity,''),[]))}
    # Promote precise paragraph membership to physical parent cells. Audit
    # table coverage is kept as row-ID sets so one continuation piece cannot
    # masquerade as the entire logical source table.
    for p in document['paragraphs']:
        if p['parent_cell']:node_units[p['parent_cell']].update(node_units[p['locator']])
    editable=bool(any(p['text'].strip() for p in document['paragraphs']))
    table_scores={identity:.8*mean(list(table_values[identity].values()))+.2*mean(list(header_values[identity].values())) for identity in expected['tables']}
    full_units={identity:paragraph_checks[identity]==1 and (identity not in id_checks or id_checks[identity]==1) for identity in expected['paragraphs']}
    for identity in expected['tables']:
        full_units[identity]=table_scores[identity]==1 and all(merge_checks[identity]) and not unexpected_merges[identity] and bool(source_orders[identity]) and bool(caption_checks[identity])
    for identity,row in note_checks.items():full_units[identity]=all(row[key]==1 for key in ['text','attachment','source_label'])
    return {'table_values':table_values,'table_headers':header_values,'table_scores':table_scores,'merge_checks':merge_checks,'unexpected_merges':unexpected_merges,
        'numeric_checks':numeric_checks,'source_row_orders':source_orders,'caption_checks':caption_checks,
        'paragraph_checks':paragraph_checks,'paragraph_id_checks':id_checks,'observed_body_order':observed_order,
        'order_checks':order_checks,'note_checks':note_checks,'full_units':full_units,'editable_native_text':editable,
        'duplicate_records':sorted(uid for uid,count in row_occurrences.items() if count>1),'unexpected_rows':unexpected_rows,
        'body_extra_text_count':len(extra),'node_units':dict(node_units),'node_rows':{k:dict(v) for k,v in node_rows.items()},
        'node_fields':{k:dict(v) for k,v in node_fields.items()},
        'expected_rows':{identity:{row[1] if identity in {'T01','T02'} else row[0] for row in table['rows']} for identity,table in expected['tables'].items()},
        'native_part_summary':[{'source_id':p['source_id'],'word_table':p['table'],'records':[r['uid'] for r in p['data_rows']],
            'column_grid_normalized':p['column_ok'],'physical_grid_edges':p['edges']} for p in parts]}
