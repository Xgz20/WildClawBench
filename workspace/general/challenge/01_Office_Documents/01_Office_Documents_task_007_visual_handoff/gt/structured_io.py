"""Typed edit records and geometry; natural-language explanations remain semantic."""
from pathlib import Path
import json,math,re,unicodedata

def canon(value):
    text=unicodedata.normalize('NFKC',str(value or ''))
    return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith('P')).casefold()
def load_ledger(path,contract):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1_048_576:return {},{'parseable':False,'error':'missing/unsafe/oversized ledger'}
    try:raw=json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,UnicodeError,json.JSONDecodeError):return {},{'parseable':False,'error':'not valid UTF-8 JSON'}
    entries=raw.get('changes') if isinstance(raw,dict) else raw
    if not isinstance(entries,list):return {},{'parseable':False,'error':'changes must be an array'}
    aliases={canon(key):value for key,value in contract['ids'].items()};grouped={};unknown=[]
    for row in entries:
        if not isinstance(row,dict):unknown.append('non-object');continue
        identity=aliases.get(canon(row.get('annotation_id')))
        if identity is None:unknown.append(str(row.get('annotation_id')));continue
        grouped.setdefault(identity,[]).append(row)
    rows={};conflicts=[]
    for identity,items in grouped.items():
        if len(items)!=1:conflicts.append(identity);continue
        row=dict(items[0]);row['_present']=sorted(items[0]);rows[identity]=row
    return rows,{'parseable':True,'entry_count':len(entries),'unknown':unknown,'conflicts':conflicts}
def action_name(value,contract):return {canon(key):value for key,value in contract['action_aliases'].items()}.get(canon(value))
def decision_ok(row,expected_action,actual_action=None):
    wanted='retained' if expected_action=='retain' else 'rejected' if expected_action=='reject_out_of_scope' else 'applied'
    if 'decision' not in row:
        if actual_action is None:return False
        inferred='retained' if actual_action=='retain' else 'rejected' if actual_action=='reject_out_of_scope' else 'applied'
        return inferred==wanted
    aliases={'applied':'applied','adopt':'applied','采用':'applied','已修改':'applied','retained':'retained','retain':'retained','keep':'retained','保留':'retained',
        'rejectedoutofscope':'rejected','rejectoutofscope':'rejected','reject':'rejected','notadopted':'rejected','拒绝越界':'rejected','未采纳':'rejected','rejected':'rejected'}
    actual=aliases.get(canon(row['decision']))
    return actual==wanted
def image_name(value):return str(value or '').replace('\\','/').split('/')[-1]
def numeric(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
def region_box(value,width=1600,height=1300):
    if isinstance(value,list):value={'bbox':value,'space':'pixel'}
    if not isinstance(value,dict):return None
    space=canon(value.get('space',value.get('coordinate_space','pixel')))
    if space not in {'pixel','pixels','pixelxyxy','normalized','normalizedxyxy'}:return None
    polygon=value.get('polygon')
    if polygon is not None:
        if not isinstance(polygon,list) or len(polygon)<3 or not all(isinstance(p,list) and len(p)==2 and all(numeric(n) for n in p) for p in polygon):return None
        box=[min(p[0] for p in polygon),min(p[1] for p in polygon),max(p[0] for p in polygon),max(p[1] for p in polygon)]
    else:
        box=value.get('bbox')
        if not isinstance(box,list) or len(box)!=4 or not all(numeric(n) for n in box):return None
        box=list(box)
        if canon(value.get('format','xyxy'))=='xywh':box=[box[0],box[1],box[0]+box[2],box[1]+box[3]]
        elif canon(value.get('format','xyxy'))!='xyxy':return None
    if space.startswith('normalized'):box=[box[0]*width,box[1]*height,box[2]*width,box[3]*height]
    if not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height:return None
    return box
def area(box):return max(0,box[2]-box[0])*max(0,box[3]-box[1])
def overlap(a,b):
    if a is None or b is None:return 0.
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return intersection/(area(a)+area(b)-intersection) if intersection else 0.
def region_score(value,expected,alternatives=()):
    box=region_box(value)
    if box is None or area(box)>.65*1600*1300:return 0.
    return min(1.,max([overlap(box,expected),*[overlap(box,other) for other in alternatives]])/.3)
def destination_score(value,visual):
    box=region_box(value)
    if box is None or area(box)>60_000 or box[3]-box[1]>120:return 0.
    tip=visual['arrow_polyline'][-1]
    close=box[0]-12<=tip[0]<=box[2]+12 and box[1]-12<=tip[1]<=box[3]+12
    return float(close and overlap(box,visual['landing_bbox'])>0)
def ref_texts(value):
    if isinstance(value,str):return [value]
    if not isinstance(value,dict):return []
    return [str(value[key]) for key in ('bookmark','original_text','paragraph_text','selected_text','table_row','row_label','column',
        'before_paragraph','moved_object','moved_paragraph','destination_before_original_text','destination_after_original_text') if key in value]
def target_ok(value,case,source_paragraphs):
    texts=[canon(v) for v in ref_texts(value)];joined=''.join(texts);identity=case['target']
    if case['action']=='replace_cell':return '复核材料' in joined and ('截止时间' in joined or 'deadline' in joined)
    if case['action']=='retain':return '回执归档' in joined or canon(identity) in texts
    if case['action']=='reorder':
        moved=canon('step3') in texts or any('核对依赖回执' in t for t in texts)
        landing=canon('step2') in texts or any('通知协作岗位' in t for t in texts)
        return moved and landing
    if canon(identity) in texts:return True
    aliases={
      'current_window':['正式交接窗口',source_paragraphs['current_window']],
      'owner_pair':['准备责任岗',source_paragraphs['owner_pair']],
      'customer_promise':['通知客户时承诺当日一定结案',source_paragraphs['customer_promise']],
      'handoff_note':['交接说明',source_paragraphs['handoff_note']],
      'record_retention':['发布记录保存期',source_paragraphs['record_retention']]}.get(identity,[])
    return any(canon(candidate)==text for candidate in aliases for text in texts)
def sequence_text(value):
    if isinstance(value,list):return ''.join(canon(re.sub(r'^\s*[1-9][0-9]*[\s.、)）]+','',unicodedata.normalize('NFKC',str(item)))) for item in value)
    return canon(value)
def declared_values_ok(row,case,source_paragraphs):
    kind=case['action'];before=[];after=[]
    if kind in ('replace','replace_span','delete_span'):
        before=[case['old'],case['source_text']];after=[case.get('new',''),case['expected_text']]
    elif kind=='replace_cell':before=[case['old']];after=[case['new']]
    elif kind=='retain':before=[case['expected_row'],case['expected_row'][0],case['expected_row'][2]];after=list(before)
    elif kind=='insert_after':before=[case['source_text']];after=[case['new'],case['source_text']+case['new']]
    elif kind=='reorder':before=[case['source_steps']];after=[case['expected_steps']]
    elif kind=='reject_out_of_scope':before=[case['source_text']];after=list(before)
    def match(key,choices):
        if key not in row:return False
        if row[key] is None:return kind=='delete_span' and key=='after'
        if isinstance(row[key],list):return any(isinstance(choice,list) and sequence_text(row[key])==sequence_text(choice) for choice in choices)
        return any((canon(row[key])==canon(choice)) if not isinstance(choice,list) else canon(row[key]) in {canon(''.join(choice)),sequence_text(choice)} for choice in choices)
    return {'before':match('before',before),'after':match('after',after)}
