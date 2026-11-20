"""Typed CSV audit checks against actual nodes, independent of claimed success."""
from pathlib import Path
from collections import defaultdict
import csv,io,re,unicodedata

ALIASES={'sourceid':'source_id','源编号':'source_id','源单元':'source_id','sourcepages':'source_pages','源页':'source_pages','源页码':'source_pages',
 'sourcelocator':'source_locator','源定位':'source_locator','targetlocator':'target_locator','目标节点':'target_locator','目标定位':'target_locator',
 'status':'status','状态':'status','issue':'issue','问题':'issue','缺损说明':'issue'}
REQUIRED={'source_id','source_pages','source_locator','target_locator','status','issue'}
def key(value):return re.sub(r'[\s_\-]','',unicodedata.normalize('NFKC',str(value or ''))).casefold()
def read_ledger(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1_048_576:return {},{'parseable':False,'reason':'missing/unsafe/oversized CSV'}
    try:
        reader=csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig')));headers=reader.fieldnames or []
        mapped=[ALIASES.get(key(name)) for name in headers];duplicate={name for name in mapped if name and mapped.count(name)>1}
        rows=list(reader)
    except (OSError,UnicodeError,csv.Error):return {},{'parseable':False,'reason':'invalid UTF-8 CSV'}
    fields={name for name in mapped if name and name not in duplicate};grouped=defaultdict(list);unknown=[]
    for raw in rows:
        normalized={field:raw.get(header,'') for header,field in zip(headers,mapped) if field in fields}
        identity=str(normalized.get('source_id','')).strip().upper()
        if not re.fullmatch(r'(?:S|H|T|F)\d{2}',identity):unknown.append(identity);continue
        grouped[identity].append(normalized)
    values={identity:items[0] for identity,items in grouped.items() if len(items)==1}
    return values,{'parseable':True,'row_count':len(rows),'fields':sorted(fields),'duplicate_fields':sorted(duplicate),
        'duplicate_ids':sorted(identity for identity,items in grouped.items() if len(items)>1),'unknown_ids':unknown,
        'schema_complete':fields==REQUIRED and not duplicate}

def pages(value):
    text=unicodedata.normalize('NFKC',str(value or '')).replace('第','').replace('页','')
    text=re.sub(r'(\d)\s*(?:-|–|—|至|\.\.)\s*(\d)',r'\1-\2',text)
    result=set()
    for token in re.split(r'[,;、|\s]+',text.strip()):
        if not token:continue
        match=re.fullmatch(r'(\d+)\s*(?:-|–|—|至|\.\.)\s*(\d+)',token)
        if match:
            start,end=map(int,match.groups())
            if not 1<=start<=end<=6:return set()
            result.update(range(start,end+1))
        elif token.isdigit() and 1<=int(token)<=6:result.add(int(token))
        else:return set()
    return result

def target_nodes(value,document):
    result=[]
    if document is None:return result
    for raw in re.split(r'[;；|\n]+',str(value or '')):
        token=unicodedata.normalize('NFKC',raw).strip()
        token=re.sub(r'^.*?converted\.docx[#/]','',token,flags=re.I)
        token=re.sub(r'^word/document\.xml[#/]','',token,flags=re.I)
        token=re.sub(r'^word/footnotes\.xml[#/]','',token,flags=re.I)
        token=re.sub(r'\s+','',token).lower()
        if token in document['nodes']:result.append(token)
        elif token in document['notes']:result.append(token)
    return list(dict.fromkeys(result))

def evaluate(rows,metadata,document,analysis,expected):
    checks={};expected_ids={u['source_id'] for u in expected['audit_units']}
    for unit in expected['audit_units']:
        identity=unit['source_id'];row=rows.get(identity,{})
        source_pages=pages(row.get('source_pages'))
        source_ref=str(row.get('source_locator',''))
        refs=re.findall(r'source\.pdf#page\s*:\s*(\d+)\s*/\s*([SHTF]\d{2})',unicodedata.normalize('NFKC',source_ref),re.I)
        source_ok={(int(p),name.upper()) for p,name in refs}=={(p,identity) for p in unit['source_pages']}
        targets=target_nodes(row.get('target_locator'),document)
        if identity.startswith('T'):
            covered=set()
            for target in targets:
                lookup=target
                if lookup in (document or {}).get('nodes',{}) and document['nodes'][lookup].get('parent_cell'):lookup=document['nodes'][lookup]['parent_cell']
                covered.update((analysis or {}).get('node_fields',{}).get(lookup,{}).get(identity,set()))
            table=expected['tables'][identity];col=1 if identity in {'T01','T02'} else 0
            fields={(r[col],c) for r in table['rows'] for c in range(len(table['columns']))}
            target_score=len(covered&fields)/len(fields)
        else:
            matches=[target for target in targets if identity in (analysis or {}).get('node_units',{}).get(target,set())]
            target_score=float(bool(matches) and len(matches)==len(targets))
        status=key(row.get('status'))
        status={'converted':'converted','已转换':'converted','完整':'converted','partial':'partial','部分':'partial','missing':'missing','缺失':'missing'}.get(status)
        complete=bool((analysis or {}).get('full_units',{}).get(identity))
        present=bool(targets)
        issue=bool(str(row.get('issue','')).strip())
        truthful=(status=='converted' and complete and not issue or status=='partial' and not complete and present and issue
                  or status=='missing' and not complete and not present and issue)
        checks[identity]={'row_present':float(bool(row)),'source_pages':float(source_pages==set(unit['source_pages'])),
            'source_locator':float(source_ok),'target_locator':target_score,'truthful_status':float(truthful)}
    extras=set(rows)-expected_ids
    complete=bool(metadata.get('parseable') and metadata.get('schema_complete') and metadata.get('row_count')==len(expected_ids)
        and set(rows)==expected_ids and not metadata.get('duplicate_ids') and not metadata.get('unknown_ids') and not extras)
    return checks,complete
