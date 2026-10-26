"""Candidate observations. Field/order/layout choices do not supply business GT."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import csv,io,json,math,posixpath,re,unicodedata

def clean(value):return unicodedata.normalize('NFKC','' if value is None else str(value)).strip()
def header(value):return re.sub(r'[\s_（）()]','',clean(value)).lower()

def ledger(path,contract):
    if not path.is_file() or path.is_symlink():return {},{'parseable':False,'complete':False}
    text=path.read_text(encoding='utf-8-sig')
    try:
        dialect=csv.Sniffer().sniff(text[:10000],delimiters=',;\t')
    except csv.Error:dialect=csv.excel
    try:rows=list(csv.reader(io.StringIO(text,newline=''),dialect))
    except csv.Error:return {},{'parseable':False,'complete':False}
    if not rows or len(rows)>contract['max_csv_rows']+1:return {},{'parseable':False,'complete':False}
    aliases={header(alias):key for key,values in contract['fields'].items() for alias in values}
    mapping={};ambiguous=set()
    for index,name in enumerate(rows[0]):
        key=aliases.get(header(name))
        if key:
            if key in mapping:ambiguous.add(key)
            mapping[key]=index
    for key in ambiguous:mapping.pop(key)
    if 'kpi_id' not in mapping:return {},{'parseable':True,'complete':False,'present_fields':sorted(mapping)}
    observations=defaultdict(lambda:defaultdict(list));counts=defaultdict(int)
    for row in rows[1:]:
        identity=clean(row[mapping['kpi_id']]) if mapping['kpi_id']<len(row) else ''
        identity=next((item for item in contract['required_ids'] if item.lower()==identity.lower()),identity)
        if not identity:continue
        counts[identity]+=1
        for key,index in mapping.items():
            if key!='kpi_id':observations[identity][key].append(clean(row[index]) if index<len(row) else '')
    result={}
    for identity,fields in observations.items():
        result[identity]={key:values[0] for key,values in fields.items() if len(set(values))==1}
    complete=set(contract['fields'])<=set(mapping) and set(contract['required_ids'])<=set(result) and all(counts[x]==1 and all(result[x].get(field,'')!='' for field in contract['fields'] if field!='kpi_id') for x in contract['required_ids'])
    return result,{'parseable':True,'complete':complete,'present_fields':sorted(mapping),'duplicate_ids':[x for x,v in counts.items() if v>1]}

def scalar(value,unit,wanted):
    text=clean(value).replace(',','')
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(万元|千元|元|%|ratio)?',text,re.I)
    if not match:return None
    try:number=Decimal(match[1])
    except InvalidOperation:return None
    source=clean(unit) or match[2] or wanted
    if source.lower() in {'ratio','percent'}:source=source.lower()
    if not number.is_finite():return None
    if wanted=='%':
        if source in {'ratio','比率','小数'}:return float(number*100)
        return float(number) if source in {'%','percent','百分比'} else None
    if wanted=='ratio':
        if source in {'ratio','比率','小数'}:return float(number)
        return float(number/100) if source in {'%','percent','百分比'} else None
    factors={'万元':Decimal(10000),'千元':Decimal(1000),'元':Decimal(1)}
    return float(number*factors[source]/factors[wanted]) if source in factors and wanted in factors else None

def matches(value,expected,tolerance):return value is not None and math.isfinite(value) and abs(value-float(expected))<=tolerance

def page_number(value):
    try:
        number=Decimal(clean(value))
        return int(number) if number.is_finite() and number>0 and number==number.to_integral_value() else None
    except (InvalidOperation,ValueError):return None

def metric_values(text,items):
    text=clean(text);result={}
    for item in items:
        match=re.search(r'(?<![A-Za-z0-9])'+item['kpi_id']+r'(?!\d)',text,re.I)
        if not match:continue
        tail=text[match.end():match.end()+420]
        tail=re.split(r'(?<![A-Za-z0-9])K\d{2}(?!\d)',tail,maxsplit=1)[0]
        unit=r'%' if item['unit']=='%' else r'万元|千元|元'
        number=re.search(r'([+-]?\d[\d,]*(?:\.\d+)?)\s*('+unit+r')',tail)
        if number:
            result[item['kpi_id']]=scalar(number[1],number[2],item['unit']);continue
        # A native table may put units in its header. Keep this observation
        # separate from required unit/schema delivery compliance.
        number=re.search(r'[+-]?\d[\d,]*\.\d{1,8}',tail)
        if number:result[item['kpi_id']]=scalar(number[0],item['unit'],item['unit'])
    return result

def pdf_metric_values(page,items):
    """Bind numbers by glyph geometry so chart axes do not enter a KPI column."""
    anchors=[]
    for item in items:
        for match in page.search(r'(?<![A-Za-z0-9])'+item['kpi_id']+r'(?!\d)',regex=True,case=False,return_chars=False):
            anchors.append({'id':item['kpi_id'],'unit':item['unit'],**match})
    if not anchors:return {}
    filtered=[]
    for identity in {anchor['id'] for anchor in anchors}:
        choices=[a for a in anchors if a['id']==identity];descriptive=[]
        for anchor in choices:
            left=max(0,min(page.width,anchor['x1']+.5));right=min(page.width,left+150)
            top=max(0,anchor['top']-2);bottom=min(page.height,anchor['bottom']+2)
            if left<right and top<bottom:
                following=page.crop((left,top,right,bottom)).extract_text() or ''
                if re.search(r'[A-Za-z0-9\u4e00-\u9fff]',following):descriptive.append(anchor)
        filtered.extend(descriptive or choices)
    anchors=filtered
    candidates=[]
    for match in page.search(r'([+-]?\d[\d,]*(?:\.\d+)?)\s*(万元|千元|元|%|％)',regex=True,return_chars=False):
        value=re.fullmatch(r'([+-]?\d[\d,]*(?:\.\d+)?)\s*(万元|千元|元|%|％)',clean(match['text']))
        if value:candidates.append({**match,'number':value[1],'unit':value[2]})
    explicit=list(candidates)
    for match in page.search(r'[+-]?\d[\d,]*\.\d{2,8}',regex=True,return_chars=False):
        if any(match['x0']>=other['x0']-.1 and match['x1']<=other['x1']+.1 and abs(match['top']-other['top'])<2 for other in explicit):continue
        candidates.append({**match,'number':clean(match['text']),'unit':None})
    def distance(anchor,value):
        return math.hypot(value['x0']-anchor['x0'],1.5*(value['top']-anchor['top']))
    owned=defaultdict(list)
    for value in candidates:
        eligible=anchors
        if not eligible:continue
        winner=min(eligible,key=lambda a:distance(a,value))
        owned[winner['id']].append((distance(winner,value),scalar(value['number'],value['unit'] or winner['unit'],winner['unit'])))
    return {identity:min(values,key=lambda value:value[0])[1] for identity,values in owned.items() if values}

def editable_value_present(text,value,wanted,tolerance=.0051):
    if value is None:return False
    clean_text=clean(text)
    for match in re.finditer(r'([+-]?\d[\d,]*(?:\.\d+)?)\s*(万元|千元|元|%|％)',clean_text):
        if matches(scalar(match[1],match[2],wanted),value,tolerance):return True
    for match in re.finditer(r'[+-]?\d[\d,]*\.\d{2,8}',clean_text):
        if matches(scalar(match[0],wanted,wanted),value,tolerance):return True
    return False

def pdf_aging_values(page):
    patterns={'A07-future':r'未到期','A07-0-30':r'0\s*(?:至|-|~)\s*30\s*天',
              'A07-31-60':r'31\s*(?:至|-|~)\s*60\s*天','A07-over60':r'(?:大于\s*60\s*天|>\s*60\s*天|61\s*天以上)'}
    anchors=[]
    for identity,pattern in patterns.items():
        found=page.search(pattern,regex=True,return_chars=False)
        if found:anchors.append({'id':identity,**min(found,key=lambda x:x['top'])})
    if not anchors:return {}
    unit=re.search(r'(?:未收余额|金额|单位)\s*[（(]?\s*(万元|千元|元)',clean(page.extract_text() or ''))
    unit=unit[1] if unit else '万元'
    candidates=[]
    for value in page.search(r'[+-]?\d[\d,]*(?:\.\d+)?',regex=True,return_chars=False):
        if value['top']<min(a['top'] for a in anchors)-2:continue
        if any(value['x0']>=a['x0']-.1 and value['x1']<=a['x1']+.1 and abs(value['top']-a['top'])<3 for a in anchors):continue
        candidates.append(value)
    def distance(a,v):return math.hypot(v['x0']-a['x0'],10*(v['top']-a['top']))
    owned=defaultdict(list)
    for value in candidates:
        a=min(anchors,key=lambda a:distance(a,value))
        owned[a['id']].append((distance(a,value),scalar(value['text'],unit,'万元')))
    return {identity:min(values,key=lambda x:x[0])[1] for identity,values in owned.items() if values}

def unpack_records(projection):return [json.loads(line) for line in projection['text'].splitlines()]

def slide_texts(records):
    pages=defaultdict(list)
    for row in records:
        if row.get('context') not in {'slide','slide_table','chart_text'}:continue
        match=re.match(r'slide:(\d+)/',row['locator'])
        if match and row.get('text'):pages[int(match[1])].append(row['text'])
    return {page:'\n'.join(parts) for page,parts in pages.items()}

def chart_groups(records):
    groups=[]
    for row in records:
        if row.get('context')!='chart' or 'part' not in row:continue
        prefix=row['locator'];series=[]
        for item in records:
            if item.get('context')!='chart_series' or not item['locator'].startswith(prefix+'/'):continue
            anchor=item['locator'];points=[x for x in records if x.get('context')=='chart_stored_point' and x['locator'].startswith(anchor+'/val/')]
            categories=[x for x in records if x.get('context')=='chart_stored_point' and x['locator'].startswith(anchor+'/cat/')]
            references=next((x['formulas'] for x in records if x['locator']==anchor+'/val'),[])
            values={x['index']:x.get('value') for x in points}
            vector=[values.get(i) for i in range(max(values,default=-1)+1)]
            category_map={x['index']:x.get('value') for x in categories}
            series.append({'prefix':anchor,'values':vector,'categories':[category_map[i] for i in sorted(category_map)],
                           'formula':references[0] if len(references)==1 else None})
        workbooks=[x for x in records if x.get('context')=='embedded_workbook' and x['locator'].startswith(prefix+'/') and x.get('content_status')=='stored_cells']
        groups.append({'prefix':prefix,'page':int(re.match(r'slide:(\d+)',prefix)[1]),'series':series,
                       'workbook_parts':sorted({x['part'] for x in workbooks}),'part':row['part']})
    return groups

def formula_cells(formula):
    if not isinstance(formula,str):return None
    match=re.fullmatch(r"(?:'((?:[^']|'')+)'|([^'!]+))!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?",formula.strip(),re.I)
    if not match:return None
    sheet=(match[1].replace("''", "'") if match[1] is not None else match[2]);c1,c2=match[3],match[5] or match[3]
    r1,r2=int(match[4]),int(match[6] or match[4])
    def column(text):
        number=0
        for char in text.upper():number=number*26+ord(char)-64
        return number
    left,right=column(c1),column(c2)
    if r1<1 or r2<r1 or right<left or (r2-r1+1)*(right-left+1)>2000:return None
    def label(value):
        text=''
        while value:value,rest=divmod(value-1,26);text=chr(65+rest)+text
        return text
    return [f'{sheet}!{label(c)}{r}' for r in range(r1,r2+1) for c in range(left,right+1)]

def source_cells(text,limit=2000):
    references=set()
    for part in re.split(r'[;；\n]+',clean(text)):
        part=part.strip()
        for prefix in ('/tmp_workspace/metrics.xlsx#','metrics.xlsx#'):
            if part.startswith(prefix):part=part[len(prefix):]
        cells=formula_cells(part)
        if cells is None:return None
        references.update(cells)
        if len(references)>limit:return None
    return references

def workbook_values(projection):
    rows=unpack_records(projection)
    return {row['locator']:row.get('value') for row in rows if '!' in row['locator']}
