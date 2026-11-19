"""Read candidate fields independently of sheet names, order or prose style."""
from collections import defaultdict
import json
import re
import unicodedata


def header(value):return re.sub(r'[\s_()（）]','',unicodedata.normalize('NFKC',str(value or ''))).lower()


def normalized(key,value,contract):
    text='' if value is None else str(value).strip()
    kind={'mandatory':'mandatory_aliases','draft_status':'draft_aliases','coverage':'coverage_aliases','certificate_status':'cert_aliases'}.get(key)
    if kind:
        aliases={name.lower():canonical for name,canonical in contract[kind].items()}
        return aliases.get(text.lower(),text)
    return text


def workbook_rows(projection,contract):
    sheets=defaultdict(lambda:defaultdict(dict))
    for line in projection['text'].splitlines():
        record=json.loads(line); locator=record['locator']
        if '!' not in locator:continue
        name,address=locator.rsplit('!',1); match=re.fullmatch(r'([A-Z]+)([0-9]+)',address)
        if match:sheets[name][int(match[2])][match[1]]=record.get('value')
    aliases={header(alias):key for key,values in contract['field_aliases'].items() for alias in values}
    observations=defaultdict(lambda:defaultdict(list))
    tables=0
    for sheet,rows in sheets.items():
        for number,cells in sorted(rows.items()):
            mapping={}; ambiguous=set()
            for column,value in cells.items():
                key=aliases.get(header(value))
                if key:
                    if key in mapping:ambiguous.add(key)
                    mapping[key]=column
            for key in ambiguous:mapping.pop(key)
            if 'req_id' not in mapping or len(mapping)<2:continue
            tables+=1
            for row_number,values in sorted(rows.items()):
                if row_number<=number:continue
                identity=str(values.get(mapping['req_id']) or '').strip().upper()
                if not re.fullmatch(r'R[0-9]{3}',identity):continue
                for key,column in mapping.items():
                    if key=='req_id':continue
                    observations[identity][key].append((normalized(key,values.get(column),contract),f'{sheet}!{column}{row_number}'))
    result={}; conflicts={}
    for identity,fields in observations.items():
        result[identity]={'req_id':identity,'_present':set(),'_locators':{}}
        for key,items in fields.items():
            values={value for value,_ in items}
            if len(values)==1:
                result[identity][key]=items[0][0];result[identity]['_present'].add(key);result[identity]['_locators'][key]=[location for _,location in items]
            else:conflicts.setdefault(identity,[]).append(key)
    return result,{'tables':tables,'conflicting_fields':conflicts}


def response_rows(projection,contract):
    records=[json.loads(line) for line in projection['text'].splitlines()]
    statuses=defaultdict(list); bodies=defaultdict(list); locators=defaultdict(list)
    current=None
    aliases=contract['coverage_aliases']; choices='|'.join(sorted((re.escape(key) for key in aliases),key=len,reverse=True))
    for record in records:
        text=unicodedata.normalize('NFKC',record.get('text','')).strip()
        if record['locator'].startswith('table:'):continue
        identity=re.search(r'(?<![A-Za-z0-9])(R[0-9]{3})(?![A-Za-z0-9])',text,re.I)
        state=re.search(r'(?:覆盖结论|coverage)\s*[:：]\s*('+choices+r')(?=$|[\]\s)）;；。,.，])',text,re.I)
        if identity and state:
            current=identity[1].upper(); statuses[current].append(normalized('coverage',state[1],contract));locators[current].append(record['locator'])
        elif current and text and not re.match(r'^(?:依据|来源|证据)\s*[:：]',text):
            # A new page/group title is not a response paragraph.
            if not re.match(r'^技术响应(?:核对稿|\s+R[0-9])',text):bodies[current].append(text)
    tables=defaultdict(lambda:defaultdict(dict))
    for record in records:
        match=re.fullmatch(r'table:([0-9]+)/row:([0-9]+)/cell:([0-9]+)',record['locator'])
        if match:tables[match[1]][int(match[2])][int(match[3])]=record.get('text','')
    table_aliases={'reqid':'req_id','需求id':'req_id','需求编号':'req_id','coverage':'coverage','覆盖结论':'coverage','最终覆盖':'coverage',
                  'response':'response','响应正文':'response','响应':'response'}
    for table,rows in tables.items():
        for number,cells in sorted(rows.items()):
            mapping={};ambiguous=set()
            for column,value in cells.items():
                key=table_aliases.get(header(value))
                if key:
                    if key in mapping:ambiguous.add(key)
                    mapping[key]=column
            for key in ambiguous:mapping.pop(key)
            if not {'req_id','coverage'}<=set(mapping):continue
            for row_number,values in sorted(rows.items()):
                identity=str(values.get(mapping['req_id'],'')).strip().upper()
                if row_number<=number or not re.fullmatch(r'R[0-9]{3}',identity):continue
                statuses[identity].append(normalized('coverage',values.get(mapping['coverage']),contract));locators[identity].append(f'table:{table}/row:{row_number}')
                body=values.get(mapping.get('response'))
                if body:bodies[identity].append(body)
    result={}
    for identity,values in statuses.items():
        unique=set(values)
        result[identity]={'coverage':next(iter(unique)) if len(unique)==1 else None,'body':'\n'.join(bodies[identity]),'locators':locators[identity]}
    return result


def gap_rows(text,contract):
    records=defaultdict(list);schemas=[];invalid=False;mapping=None;header_width=None
    for line in text.splitlines():
        if not line.strip().startswith('|'):
            mapping=None
            continue
        cells=[item.strip() for item in line.strip().strip('|').split('|')]
        lowered=[item.lower() for item in cells]
        if 'req_id' in lowered:
            candidate={key:lowered.index(key) for key in contract['gap_columns'] if lowered.count(key)==1}
            if not {'req_id','coverage'}<=set(candidate) or not {'missing_evidence','proposed_action'}&set(candidate):
                mapping=None
                continue
            mapping=candidate
            header_width=len(cells)
            schemas.append(set(mapping)==set(contract['gap_columns']));continue
        if mapping is None or all(re.fullmatch(r'[:\- ]*',value) for value in cells):continue
        if 'req_id' in mapping and mapping['req_id']<len(cells):
            identity=cells[mapping['req_id']].upper()
            if not re.fullmatch(r'R[0-9]{3}',identity):continue
            row={key:cells[index] if index<len(cells) else '' for key,index in mapping.items()}
            row['coverage']=normalized('coverage',row.get('coverage'),contract)
            if len(cells)!=header_width:invalid=True
            records[identity].append(row)
    return {identity:items[0] for identity,items in records.items() if len(items)==1}, bool(schemas and all(schemas) and not invalid and all(len(items)==1 for items in records.values()))


def parse_refs(value,field,contract):
    text='' if value is None else str(value).strip()
    if text.lower() in {item.lower() for item in contract['empty_markers']}:return set()
    default={'requirement_refs':('requirements.docx',r'R[0-9]{3}'),'draft_refs':('response.docx',r'D[0-9]{3}'),
             'fact_refs':('response.docx',r'F[0-9]{3}'),'certificate_refs':('certificates.pdf',r'C[0-9]{2}'),
             'revised_refs':('results/response_revised.docx',r'R[0-9]{3}')}[field]
    found=set()
    for value in re.split(r'[;；,，\n]+',text):
        token=value.strip().replace('\\','/')
        if token.startswith('/tmp_workspace/'):token=token[len('/tmp_workspace/'):]
        if token.startswith('./'):token=token[2:]
        if re.fullmatch(default[1],token,re.I):found.add((default[0],token.upper()));continue
        match=re.fullmatch(re.escape(default[0])+'#('+default[1]+')',token,re.I)
        if not match:return None
        found.add((default[0],match[1].upper()))
    return found
