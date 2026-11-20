"""Partial typed-field reads and native ID blocks; not a Vietnamese semantic parser."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,InvalidOperation
from datetime import date,datetime
import csv,json,re,unicodedata

def clean(value):return unicodedata.normalize('NFKC','' if value is None else str(value)).strip()
def key(value):return re.sub(r'[\s_()（）]','',clean(value)).casefold()
def canon(value):return ''.join(c for c in clean(value).casefold() if not c.isspace() and not unicodedata.category(c).startswith('P'))
def decision(value):return {'applied':'applied','采用':'applied','已采用':'applied','notapplied':'not_applied','未采纳':'not_applied','拒绝':'not_applied','待授权':'not_applied','未采用':'not_applied','unchanged':'unchanged','无意见保持':'unchanged','保持':'unchanged','无修改':'unchanged'}.get(canon(value),clean(value))
def tokens(value):
    if key(value) in {'','n/a','na','无','不适用','-','[]'}:return []
    return [v.strip() for v in re.split(r'[;；,，\n]+',clean(value)) if v.strip()]
def number(value):
    if isinstance(value,bool) or value is None:return None
    text=clean(value).replace('\u00a0','').replace(' ','')
    if not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)*',text):return None
    if re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+',text):text=text.replace('.','')
    elif re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+',text):text=text.replace(',','')
    elif ',' in text and '.' in text:
        if text.rfind('.')>text.rfind(','):text=text.replace(',','')
        else:text=text.replace('.','').replace(',','.')
    elif ',' in text:text=text.replace(',','.')
    try:value=Decimal(text)
    except InvalidOperation:return None
    return value if value.is_finite() else None
def date_value(value):
    text=clean(value)
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%Y/%m/%d','%Y年%m月%d日'):
        try:return datetime.strptime(text,fmt).date().isoformat()
        except ValueError:pass
    return None
def normalize_fact(field,value,wanted,contract):
    if isinstance(wanted,bool):
        if isinstance(value,bool):return value
        if isinstance(value,(int,float)) and value in (0,1):return bool(value)
        aliases={'true':True,'是':True,'允许':True,'false':False,'否':False,'不允许':False,'0':False,'1':True}
        return aliases.get(key(value),('invalid_boolean',str(value)))
    if isinstance(wanted,(int,float)):
        suffixes={'amount':['CNY','人民币','RMB','元'],'first_response_work_hours':['工作小时','giờ làm việc','hours'],
                  'handling_work_days':['工作日','ngày làm việc','days']}.get(field,[])
        text=clean(value)
        for suffix in suffixes:
            if text.casefold().endswith(suffix.casefold()):text=text[:-len(suffix)].strip();break
        value=number(text)
        return float(value) if value is not None else ('invalid_number',text)
    if field in ('start_date','end_date'):return date_value(value)
    if wanted=='unknown' and value is None:return 'unknown'
    for canonical,aliases in contract['enum_aliases'].items():
        if key(value) in {key(v) for v in aliases}:return canonical
    return clean(value)
def normalize_facts(value,expected,contract):
    if not isinstance(value,dict):return {},['facts_json is not an object']
    aliases={key(k):k for k in contract['fact_schema']};aliases.update({key(v):k for k,v in contract['fact_schema'].items()})
    grouped=defaultdict(list);unknown=[]
    for name,raw in value.items():
        field=aliases.get(key(name))
        if field not in expected:unknown.append(str(name));continue
        grouped[field].append(normalize_fact(field,raw,expected[field],contract))
    out={}
    for field,values in grouped.items():
        if all(v==values[0] for v in values):out[field]=values[0]
    return out,unknown
def references(value,contract):
    out=[]
    for text in tokens(value):
        text=text.replace('\\','/')
        if text.startswith('/tmp_workspace/'):text=text[len('/tmp_workspace/'):]
        if ':' in text and '#' not in text:
            prefix,identity=text.split(':',1);source=contract['source_codes'].get(prefix.upper())
            if source:out.append(source+'#'+identity.upper());continue
        if '#' not in text:return None
        source,identity=text.split('#',1)
        if source.startswith('./'):source=source[2:]
        out.append(source+'#'+identity.upper())
    return sorted(set(out))
def headers(cells,contract):
    names={key(alias):field for field,aliases in contract['field_aliases'].items() for alias in aliases}
    result={};ambiguous=set()
    for column,text in cells.items():
        field=names.get(key(text))
        if field:
            if field in result:ambiguous.add(field)
            result[field]=column
    for field in ambiguous:result.pop(field)
    return result,ambiguous
def merge(observations):
    out={};conflicts={}
    for identity,fields in observations.items():
        row={'_present':[],'_locations':{}}
        for field,values in fields.items():
            serialized={json.dumps(v,ensure_ascii=False,sort_keys=True) for v,_ in values}
            if len(serialized)==1:row[field]=values[0][0];row['_present'].append(field);row['_locations'][field]=[loc for _,loc in values]
            else:conflicts.setdefault(identity,[]).append(field)
        out[identity]=row
    return out,conflicts
def csv_rows(path,contract):
    with Path(path).open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
    if not rows:return {},{'schema':False,'error':'empty CSV'}
    mapping,ambiguous=headers(dict(enumerate(rows[0])),contract);values=defaultdict(lambda:defaultdict(list));invalid=[]
    for line,row in enumerate(rows[1:],2):
        if not any(cell.strip() for cell in row):continue
        identity=clean(row[mapping['sentence_id']]).upper() if 'sentence_id' in mapping and mapping['sentence_id']<len(row) else ''
        if not re.fullmatch(r'S[0-9]{2}',identity):invalid.append(line);continue
        for field,column in mapping.items():
            if field=='sentence_id' or column>=len(row):continue
            value=row[column]
            if field=='decision':value=decision(value)
            if field in ('comment_id','review_ref'):value='' if not tokens(value) else clean(value)
            if field=='comment_id':value=value.upper()
            if field=='facts_json':
                def unique(pairs):
                    result={}
                    for name,item in pairs:
                        if name in result:raise ValueError('duplicate fact key')
                        result[name]=item
                    return result
                try:value=json.loads(value,object_pairs_hook=unique)
                except (ValueError,TypeError):value=None
            if field=='term_ids':value=sorted(set(t.upper() for t in tokens(value)))
            if field=='source_refs':value=references(value,contract)
            values[identity][field].append((value,{'line':line}))
        if len(row)!=len(rows[0]):invalid.append(line)
    out,conflicts=merge(values)
    return out,{'schema':set(mapping)==set(contract['alignment_columns']) and not ambiguous and not invalid and not conflicts,
                'columns':sorted(mapping),'invalid_lines':invalid,'conflicts':conflicts}
def id_blocks(document,prefix):
    grouped=defaultdict(list);locations=defaultdict(list);current=None;partial=[];anchors=defaultdict(set);chapter=None
    pattern=re.compile(r'^\[?('+prefix+r'[0-9]{2})\]?\s*(.*)$',re.I|re.S)
    def finish():
        nonlocal partial
        if current and partial:grouped[current].append('\n'.join(partial))
        partial=[]
    for block in document['blocks']:
        if block['kind']=='table':continue
        match=pattern.match(clean(block['text']))
        if match:
            finish();current=match[1].upper();remainder=match[2].strip()
            anchors[current].update([current,clean(block['text'])])
            if chapter:anchors[current].add(chapter)
            # A heading may also carry the related S ID, e.g. [R01] S01.
            if prefix=='R' and re.fullmatch(r'S[0-9]{2}',remainder,re.I):remainder=''
            if remainder:partial.append(remainder)
            locations[current].append(block['locator']);continue
        if re.search(r'heading\s*1',block.get('style',''),re.I):finish();current=None;chapter=clean(block['text'])
        elif current and block['text'].strip():partial.append(block['text']);locations[current].append(block['locator'])
    finish()
    # Native ID/body tables are an equivalent layout.
    chapter=None;table_chapters={}
    for block in document['blocks']:
        if block['kind']=='paragraph' and re.search(r'heading\s*1',block.get('style',''),re.I):chapter=clean(block['text'])
        elif block['kind']=='table':table_chapters[block['locator']]=chapter
    fallback=[]
    for table in [b for b in document['blocks'] if b['kind']=='table']:
        if not table['rows']:continue
        first={i:key(c['text']) for i,c in enumerate(table['rows'][0])}
        ids=[i for i,name in first.items() if name in {'sentenceid','句id','句编号','句子编号','条款编号','mãcâu','macau','mãđiềukhoản','điềukhoản','commentid','意见编号'}]
        strong=[i for i,name in first.items() if re.search(r'final|revised|修订后|最终|hiệuchỉnh|đãchỉnhsửa|saukhichỉnhsửa',name)]
        bodies=strong if len(strong)==1 else [i for i,name in first.items() if name in {'正文','越文正文','中文说明','text','body','nộidung','noidung','nộidungtiếngviệt','说明','reasonzh'}]
        if len(ids)!=1 or len(bodies)!=1:
            fallback.append(table);continue
        for row in table['rows'][1:]:
            identity=clean(row[ids[0]]['text']).upper()
            if re.fullmatch(prefix+r'[0-9]{2}',identity):
                grouped[identity].append(row[bodies[0]]['text']);locations[identity].append(table['locator']);anchors[identity].add(identity)
                if table_chapters.get(table['locator']):anchors[identity].add(table_chapters[table['locator']])
    # Unambiguous two-cell ID/body rows need no particular header wording.
    # Explicitly identified prose takes priority over an unrelated two-column appendix.
    explicit=set(grouped)
    for table in fallback:
        for row in table['rows']:
            cells=[(i,clean(cell['text'])) for i,cell in enumerate(row)]
            identities=[(i,text.strip('[]【】').upper()) for i,text in cells if re.fullmatch(r'[\[【]?'+prefix+r'[0-9]{2}[\]】]?',text,re.I)]
            if len(identities)!=1:continue
            column,identity=identities[0];other=[text for i,text in cells if i!=column and text]
            if len(other)!=1 or identity in explicit:continue
            grouped[identity].append(other[0]);locations[identity].append(table['locator']);anchors[identity].add(identity)
            if table_chapters.get(table['locator']):anchors[identity].add(table_chapters[table['locator']])
    out={}
    for identity,texts in grouped.items():
        unique={canon(t) for t in texts}
        if len(unique)==1:out[identity]={'text':texts[0],'locators':locations[identity],'anchors':sorted(anchors[identity])}
    return out,{'conflicts':[identity for identity,values in grouped.items() if len({canon(v) for v in values})>1]}
def bound_output_ref(value,filename,block):
    text=clean(value).replace('\\','/')
    for prefix in ('/tmp_workspace/','./','results/'):
        if text.startswith(prefix):text=text[len(prefix):]
    if '#' not in text:return False
    source,anchor=text.split('#',1)
    return source==filename and bool(block) and canon(anchor) in {canon(v) for v in block.get('anchors',[])}
def review_table(document,contract):
    values=defaultdict(lambda:defaultdict(list))
    for table in [b for b in document['blocks'] if b['kind']=='table']:
        mapping=None
        for number,row in enumerate(table['rows'],1):
            cells={i:cell['text'] for i,cell in enumerate(row)};candidate,_=headers(cells,contract)
            if 'comment_id' in candidate and len(candidate)>1:mapping=candidate;continue
            if not mapping:continue
            identity=clean(cells.get(mapping['comment_id'])).upper()
            if not re.fullmatch(r'R[0-9]{2}',identity):continue
            for field,column in mapping.items():
                if field=='comment_id' or column not in cells:continue
                value=cells[column]
                if field=='decision':value=decision(value)
                if field=='sentence_id':value=clean(value).upper()
                if field=='source_refs':value=references(value,contract)
                values[identity][field].append((value,{'locator':table['locator']+f'/row:{number}'}))
    rows,conflicts=merge(values);return rows,{'conflicts':conflicts}
