"""H032 public semantic field normalization; inherited portable native readers."""
from pathlib import Path,PurePosixPath
import copy,json,math,re,runpy,unicodedata
_BASE=runpy.run_path(str(Path(__file__).resolve().with_name('native_base.py')))
_HEADERS=runpy.run_path(str(Path(__file__).resolve().with_name('native_headers.py')))
CandidateError=_BASE['CandidateError'];TrustedEvidenceError=_BASE['TrustedEvidenceError']
read_book=_BASE['read_book'];read_docx=_BASE['read_docx'];quote_match=_BASE['quote_match'];resolve_pointer=_BASE['resolve_pointer'];pointer_overlaps=_BASE['pointer_overlaps'];sha=_BASE['sha']
def text(value):return isinstance(value,str) and bool(value.strip())
def norm(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str('' if value is None else value))).casefold()
def rich(value):
    if text(value):return True
    if isinstance(value,dict):return bool(value) and any(rich(v) for v in value.values())
    if isinstance(value,list):return bool(value) and any(rich(v) for v in value)
    return False
def strict_json(path):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise CandidateError('duplicate JSON field: '+key)
            result[key]=value
        return result
    try:value=json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(CandidateError('non-JSON number: '+v)))
    except (OSError,ValueError,UnicodeError) as exc:raise CandidateError('bibliography must be readable strict UTF-8 JSON: '+str(exc)) from exc
    if not isinstance(value,dict):raise CandidateError('bibliography root must be object')
    return value
def candidate_path(root,relative):
    root=Path(root).resolve();parts=PurePosixPath(relative)
    if parts.is_absolute() or any(p in ('','.','..') for p in parts.parts):raise CandidateError('unsafe candidate relative path')
    path=root/relative
    if not path.is_file() or path.is_symlink() or root not in path.resolve().parents:raise CandidateError('candidate artifact missing/unsafe: '+relative)
    if path.stat().st_size>64*1024*1024:raise TrustedEvidenceError('UNSUPPORTED_ARTIFACT_CAPACITY: legal artifact exceeds bounded reader capacity; no hidden ability size limit')
    return path
ALIASES={
 'schema_version':['模式版本'],'documents':['文献文件','资料文件','文献'],'claims':['断言','结论核查'],'citations':['引文','证据定位'],'field_map':['字段映射'],
 'document_id':['文献ID','文件ID','报告ID'],'file':['文件','文件路径','来源文件'],'title':['标题','题名'],'authors':['作者'],'work_id':['工作ID','工作身份'],'version':['版本','所读版本'],
 'claim_id':['断言ID','结论ID','核查ID'],'input_ref':['原断言','输入对应','原始编号','原断言编号'],'assessment_target':['被评估命题','判断对象','评估对象'],'kind':['类型','命题类型'],'text':['文本','内容'],
 'verdict':['判定','结论标签','结论'],'rationale':['理由','判断理由','论证','核查说明'],'comparison':['比较口径','比较','条件记录'],'limitations':['限制','边界','限制说明'],
 'citation_id':['引文ID','引用ID'],'locator':['定位','位置'],'quote':['短引','引文原文','原文'],'supports_fields':['目标字段','关联字段'],'relation':['关系'],'reviewed_scope':['checked_scope','已查范围','核查范围'],
 'physical_page':['物理页'],'physical_page_1_based':['物理页码'],'pages':['物理页范围'],'section':['章节'],'paragraph':['段落'],'table':['表'],'lines':['行范围'],
 'metric':['指标'],'quantity':['量','量项'],'value':['值','数值'],'unit':['单位'],'denominator':['分母'],'report':['报告','文献'],'arm':['实验臂','组别'],'task':['任务'],'split':['划分'],'condition':['条件'],'state':['状态'],'components':['子命题']}
VERDICTS={'supported':'supported','支持':'supported','有支持':'supported','refuted':'refuted','反驳':'refuted','被反驳':'refuted','insufficient':'insufficient','证据不足':'insufficient','未定':'insufficient'}
KINDS={'fact':'fact','事实':'fact','事实命题':'fact','evidence_sufficiency':'evidence_sufficiency','证据充分性':'evidence_sufficiency','元命题':'evidence_sufficiency','compound':'compound','复合命题':'compound','合取':'compound','other_explicit':'other_explicit'}
def verdict_observation(value):return _HEADERS['verdict_observation'](value,VERDICTS)
def verdict(value):return verdict_observation(value)['value']
def native_verdict_conflicts(rows,identity):return _HEADERS['verdict_conflicts'](rows,identity,VERDICTS)
def relation(value):return {'supports':'supports','支持':'supports','refutes':'refutes','反驳':'refutes','qualifies':'qualifies','限定':'qualifies','限制':'qualifies'}.get(norm(value))
def target_kind(value):
    if isinstance(value,dict):return KINDS.get(norm(value.get('kind')))
    if not isinstance(value,str):return None
    direct=KINDS.get(norm(value))
    if direct:return direct
    # A native cell may explicitly prefix its proposition with its logical kind.
    # Read only the bounded label before a colon, never keywords in the argument.
    match=re.match(r'^\s*([^:：]+)\s*[:：]\s*\S',value)
    if not match:return None
    prefix=norm(match[1]);aliases={**KINDS,'充分性':'evidence_sufficiency','复合':'compound'}
    return aliases.get(prefix)
def canonicalize(value,field_map=None):
    aliases={norm(name):key for key,names in ALIASES.items() for name in (key,*names)}
    for displayed,canonical in (field_map or {}).items():
        if isinstance(displayed,str) and isinstance(canonical,str):
            if norm(canonical) in aliases:aliases[norm(displayed)]=aliases[norm(canonical)]
            elif displayed in ALIASES:aliases[norm(canonical)]=displayed
            else:aliases[norm(displayed)]=canonical
    if isinstance(value,list):return [canonicalize(v,field_map) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        canonical=aliases.get(norm(key),key)
        if canonical in result:raise CandidateError('ambiguous equivalent duplicate JSON fields: '+str(canonical))
        result[canonical]=canonicalize(item,field_map)
    return result
def normalize_bibliography(raw):
    mapping=raw.get('field_map',raw.get('字段映射',{}));mapping=mapping if isinstance(mapping,dict) else {}
    return canonicalize(raw,mapping)
def canonical_pointer(pointer,field_map=None):
    tokens=_BASE['pointer_tokens'](pointer);aliases={norm(name):key for key,names in ALIASES.items() for name in (key,*names)}
    for left,right in (field_map or {}).items():
        if isinstance(left,str) and isinstance(right,str):
            if norm(right) in aliases:aliases[norm(left)]=aliases[norm(right)]
            elif left in ALIASES:aliases[norm(right)]=left
            else:aliases[norm(left)]=right
    return '/'+('/'.join(str(aliases.get(norm(t),t)).replace('~','~0').replace('/','~1') for t in tokens))
def original_ref(value,expected_ids):
    if isinstance(value,dict):
        for key in ('id','claim_id','input_ref','ordinal','编号','序号'):
            if key in value:return original_ref(value[key],expected_ids)
        return None
    if isinstance(value,str):
        if value in expected_ids:return value
        stripped=value.strip()
        if stripped in expected_ids:return stripped
        if re.fullmatch(r'[0-9]+',stripped):value=int(stripped)
        else:return None
    if type(value) is int and 1<=value<=len(expected_ids):return expected_ids[value-1]
    return None
MATRIX_FIELDS=('claim_id','input_ref','assessment_target','verdict','rationale','comparison','limitations','citation_id','quote','locator','report','document_id','file','version','metric','quantity','value','unit','denominator','arm','task','split','condition','state','historical_verdict','evidence_context','source_context','derived_value','derived_context','comparison_notes')
def native_header_fields(value,aliases=None):
    aliases=aliases or {norm(name):key for key,names in ALIASES.items() for name in (key,*names)}
    return tuple(field for field in _HEADERS['header_fields'](value,aliases) if field in MATRIX_FIELDS)
def native_record(values,mapping):
    try:return _HEADERS['make_record'](values,mapping,VERDICTS)
    except _HEADERS['NativeHeaderError'] as exc:raise TrustedEvidenceError(str(exc)) from exc
def extract_matrix(book,expected_ids,field_map=None):
    aliases={norm(name):key for key,names in ALIASES.items() for name in (key,*names)};records=[];unmapped=[]
    for left,right in (field_map or {}).items():
        if isinstance(left,str) and isinstance(right,str):
            if norm(right) in aliases:aliases[norm(left)]=aliases[norm(right)]
            elif left in ALIASES:aliases[norm(right)]=left
    for sheet in book:
        for r in {r for r,c in sheet['cells']}:
            values=[cell['value'] for (rr,c),cell in sorted(sheet['cells'].items()) if rr==r and cell['visible'] and cell['editable']]
            if len(values)!=2:continue
            for canonical,displayed in (values,values[::-1]):
                if isinstance(canonical,str) and canonical in ALIASES and isinstance(displayed,str) and displayed.strip():
                    key=norm(displayed)
                    if key in aliases and aliases[key]!=canonical:raise TrustedEvidenceError('UNSUPPORTED_NATIVE_FIELD_MAP: conflicting explicit semantic header mapping')
                    aliases[key]=canonical
    for sheet in book:
        cells={(r,c):cell for (r,c),cell in sheet['cells'].items() if cell['visible'] and cell['editable']}
        for r1,c1,r2,c2 in sheet.get('merged_ranges',[]):
            owner=cells.get((r1,c1))
            if owner:
                for r in range(r1,r2+1):
                    for c in range(c1,c2+1):cells.setdefault((r,c),dict(owner,merged_from=owner['address']))
        for transpose in (False,True):
            grid={(c,r) if transpose else (r,c):cell for (r,c),cell in cells.items()};rows=sorted({r for r,c in grid});headers=[]
            if len(rows)*max(1,len(grid))>10000000:raise TrustedEvidenceError('UNSUPPORTED_NATIVE_LAYOUT_CAPACITY: bounded matrix mapping work exceeded')
            for r in rows:
                mapping={c:fields for (rr,c),cell in grid.items() if rr==r and (fields:=native_header_fields(cell['value'],aliases))}
                meanings={field for fields in mapping.values() for field in fields}
                if meanings & {'claim_id','input_ref'} and len(meanings)>=2:headers.append((r,mapping))
            for i,(header,mapping) in enumerate(headers):
                stop=headers[i+1][0] if i+1<len(headers) else max(rows,default=header)+1;current=None
                for r in range(header+1,stop):
                    parsed=native_record({c:grid[(r,c)]['value'] for c in mapping if (r,c) in grid},mapping);record=parsed['record'];identity=record.get('input_ref',record.get('claim_id'))
                    if text(identity) or type(identity) is int:current=identity
                    elif current is not None:record['input_ref']=current
                    if current is None:continue
                    if any(rich(v) for key,v in record.items() if key not in ('claim_id','input_ref')):
                        records.append({**parsed,'origin':{'sheet':sheet['name'],'row':r,'transposed':transpose,'cells':[grid[(r,c)]['address'] for c in mapping if (r,c) in grid],'header_fields':{str(c):list(fields) for c,fields in mapping.items()}}})
    visible=[cell['value'] for sheet in book for cell in sheet['cells'].values() if cell['visible'] and cell['editable']]
    if not records and any(original_ref(v,expected_ids) for v in visible):raise TrustedEvidenceError('UNSUPPORTED_NATIVE_LAYOUT: visible original-claim identities but clear layout not mapped')
    return {'records':records,'unmapped':unmapped,'boundary':'Actual native logical rows only; no fixed English headers, cells or sheet names'}
def docx_explicit_rows(docx,expected_ids):
    result=[]
    if not isinstance(docx,dict):return result
    aliases={norm(name):key for key,names in ALIASES.items() for name in (key,*names)}
    for table in docx.get('tables',[]):
        for index,row in enumerate(table):
            mapping={i:fields for i,value in enumerate(row) if (fields:=native_header_fields(value,aliases))}
            if not {field for fields in mapping.values() for field in fields} & {'claim_id','input_ref'}:continue
            for values in table[index+1:]:
                parsed=native_record({i:values[i] for i in mapping if i<len(values)},mapping);record=parsed['record']
                if original_ref(record.get('input_ref',record.get('claim_id')),expected_ids):result.append({**parsed,'origin':{'kind':'actual_DOCX_table'}})
    return result
