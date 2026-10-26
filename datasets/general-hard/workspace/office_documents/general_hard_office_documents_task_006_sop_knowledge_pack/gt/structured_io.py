"""Read typed CSV and native DOCX tables, preserving partial fields and locations."""
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import csv,json,re,unicodedata,zipfile
import xml.etree.ElementTree as ET

def key(value):return re.sub(r'[\s_()（）]','',unicodedata.normalize('NFKC',str(value or ''))).casefold()
def text(value):return unicodedata.normalize('NFKC',str(value or '')).strip()
def tokens(value):return [v.strip() for v in re.split(r'[;；,，\n]+',text(value)) if v.strip()]

def norm(field,value,contract):
    value=text(value)
    if field in ('ack_hours','inspection_workdays','payment_workdays'):
        try:return str(Decimal(value).normalize()) if Decimal(value).is_finite() else value
        except InvalidOperation:return value
    category={'route':'routes','clock_state':'clocks','next_owner':'roles','approval_owner':'roles','execution_owner':'roles'}.get(field)
    if category:
        aliases={key(k):v for k,v in contract[category].items()}
        return aliases.get(key(value),value)
    if field in ('clearance_roles','forbidden_steps','steps','source_refs'):
        if value.casefold() in {v.casefold() for v in contract['empty_markers']}:return []
        category={'clearance_roles':'roles','forbidden_steps':'forbidden','steps':'steps'}.get(field)
        aliases={key(k):v for k,v in contract[category].items()} if category else {}
        result=[aliases.get(key(v),v) if category else reference(v) for v in tokens(value)]
        return result if field=='steps' else sorted(set(result))
    return value

def reference(value):
    value=text(value).replace('\\','/')
    for prefix in ('/tmp_workspace/','./'):
        if value.startswith(prefix):value=value[len(prefix):]
    return value

def headers(cells,contract):
    aliases={key(alias):field for field,values in contract['field_aliases'].items() for alias in values}
    out={};ambiguous=set()
    for column,value in cells.items():
        field=aliases.get(key(value))
        if field:
            if field in out:ambiguous.add(field)
            out[field]=column
    for field in ambiguous:out.pop(field)
    return out,sorted(ambiguous)

def merged(observations):
    rows={};conflicts={}
    for identity,fields in observations.items():
        row={'incident_id':identity,'_present':[],'_locations':{}}
        for field,values in fields.items():
            distinct={json.dumps(value,ensure_ascii=False,sort_keys=True) for value,_ in values}
            if len(distinct)==1:
                row[field]=values[0][0];row['_present'].append(field);row['_locations'][field]=[location for _,location in values]
            else:conflicts.setdefault(identity,[]).append(field)
        rows[identity]=row
    return rows,conflicts

def csv_rows(path,contract):
    with path.open(encoding='utf-8-sig',newline='') as handle:records=list(csv.reader(handle))
    if not records:return {},{'schema':False,'error':'empty CSV'}
    mapping,ambiguous=headers(dict(enumerate(records[0])),contract)
    observations=defaultdict(lambda:defaultdict(list));invalid=[];counts=defaultdict(int)
    for line,values in enumerate(records[1:],2):
        if not any(v.strip() for v in values):continue
        identity=text(values[mapping['incident_id']]).upper() if 'incident_id' in mapping and mapping['incident_id']<len(values) else ''
        if not re.fullmatch(r'I[0-9]{2}',identity):invalid.append(line);continue
        counts[identity]+=1
        for field,column in mapping.items():
            if field!='incident_id' and column<len(values):observations[identity][field].append((norm(field,values[column],contract),{'line':line}))
        if len(values)!=len(records[0]):invalid.append(line)
    rows,conflicts=merged(observations)
    return rows,{'schema':set(mapping)==set(contract['required_csv']) and not ambiguous and not invalid and not conflicts,
                 'columns':sorted(mapping),'ambiguous_headers':ambiguous,'invalid_lines':invalid,'conflicts':conflicts,'row_counts':dict(counts)}

def sections(path):
    """Table to actual visible heading/bookmark ancestry; an unrelated title is insufficient."""
    w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    with zipfile.ZipFile(path) as archive:
        doc=ET.fromstring(archive.read('word/document.xml'))
        styles=ET.fromstring(archive.read('word/styles.xml')) if 'word/styles.xml' in archive.namelist() else None
    levels={}
    if styles is not None:
        for style in styles.findall(w+'style'):
            outline=style.find(w+'pPr/'+w+'outlineLvl');name=style.find(w+'name')
            match=re.search(r'heading\s*([1-9])',style.get(w+'styleId','')+' '+(name.get(w+'val','') if name is not None else ''),re.I)
            if outline is not None and re.fullmatch(r'[0-9]',outline.get(w+'val','')):levels[style.get(w+'styleId')]=int(outline.get(w+'val'))
            elif match:levels[style.get(w+'styleId')]=int(match[1])-1
    current={};last_paragraph=None;table_anchors={};number=0
    def walk(parent):
        for node in parent:
            if node.tag in (w+'p',w+'tbl'):yield node
            elif node.tag in (w+'sdt',w+'sdtContent',w+'customXml'):yield from walk(node)
    for node in walk(doc.find(w+'body')):
        if node.tag==w+'p':
            value=''.join(n.text or '' for n in node.iter(w+'t')).strip()
            style=node.find(w+'pPr/'+w+'pStyle');level=levels.get(style.get(w+'val')) if style is not None else None
            outline=node.find(w+'pPr/'+w+'outlineLvl')
            if outline is not None and re.fullmatch(r'[0-9]',outline.get(w+'val','')):level=int(outline.get(w+'val'))
            if level is not None and value:
                current={k:v for k,v in current.items() if k<level};current[level]=value
            marks=[n.get(w+'name') for n in node.iter(w+'bookmarkStart') if n.get(w+'name')]
            last_paragraph=[*marks,value] if value else marks
        else:
            number+=1;anchors=set(current.values())|set(last_paragraph or [])
            table_anchors[number]=sorted(anchors|{v.split()[0] for v in anchors if v.split()})
    return table_anchors

def docx_rows(projection,path,contract):
    tables=defaultdict(lambda:defaultdict(dict));table_anchors=sections(path)
    for line in projection['text'].splitlines():
        record=json.loads(line);match=re.fullmatch(r'table:([0-9]+)/row:([0-9]+)/cell:([0-9]+)',record['locator'])
        if match:tables[int(match[1])][int(match[2])][int(match[3])]=record['text']
    observations=defaultdict(lambda:defaultdict(list));found=0
    for number,rows in tables.items():
        mapping=None;header_line=None
        for line,values in sorted(rows.items()):
            candidate,_=headers(values,contract)
            if 'incident_id' in candidate and len(candidate)>1:mapping=candidate;header_line=line;found+=1;continue
            if not mapping or line<=header_line:continue
            identity=text(values.get(mapping['incident_id'])).upper()
            if not re.fullmatch(r'I[0-9]{2}',identity):continue
            for field,column in mapping.items():
                if field!='incident_id' and column in values:
                    observations[identity][field].append((norm(field,values[column],contract),
                      {'locator':f'table:{number}/row:{line}/cell:{column}','anchors':table_anchors.get(number,[])}))
    rows,conflicts=merged(observations)
    return rows,{'tables':found,'conflicts':conflicts}

def bound_fields(value,filename,row,required):
    refs=tokens(value);anchors=set()
    for ref in refs:
        ref=reference(ref)
        if ref.startswith('results/'):ref=ref[len('results/'):]
        if '#' not in ref:return False
        source,anchor=ref.split('#',1)
        if source!=filename or not anchor.strip():return False
        anchors.add(anchor.strip())
    if not anchors:return False
    matched=set()
    for field in required:
        for location in row.get('_locations',{}).get(field,[]):
            matched.update(anchors&set(location['anchors']))
    # Every reference must point at at least one real required field, and each field must be covered.
    return matched==anchors and all(any(anchors&set(loc['anchors']) for loc in row.get('_locations',{}).get(field,[])) for field in required)
