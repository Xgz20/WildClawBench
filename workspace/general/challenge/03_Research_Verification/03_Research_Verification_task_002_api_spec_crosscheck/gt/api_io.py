"""Offline H028 readers and typed comparisons; no candidate writes or networking.

Only frozen public aliases are accepted. Protocol identifiers, quotations and
Base64 are deliberately not case-folded. Reference answers are never read here.
"""
from __future__ import annotations
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
MISSING=object()

class CandidateError(ValueError):pass
class TrustedEvidenceError(RuntimeError):pass

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def norm(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC','' if value is None else str(value))).casefold()
def textnorm(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value))).strip()
def mean(values):
    values=list(values)
    return sum(values)/len(values) if values else 0.

def parse_value(value):
    if not isinstance(value,str):return value
    text=value.strip()
    if text.startswith(('[' ,'{')) or text in {'null','true','false'}:
        try:return json.loads(text)
        except ValueError:pass
    return value

def unknown(value):
    return value is None or isinstance(value,str) and norm(value) in {'','null','unknown','not_documented','notstated','notreported','n/a','na','未知','未注明','未规定','文档未说明','未说明','未披露','不详','—','–'}

def number(value):
    if isinstance(value,bool) or value is None:return None
    try:
        result=float(str(value).replace(',','').strip())
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None

def integer(value):
    value=number(value)
    return int(value) if value is not None and value.is_integer() else None

def citations(value):
    value=parse_value(value)
    if isinstance(value,list):return [str(x).strip() for x in value if str(x).strip()]
    return [] if value is None else [x for x in re.split(r'[,;，；|\s]+',str(value).strip()) if x]

def candidate_path(root,relative,limit=5242880):
    root=Path(root).resolve();path=root/relative
    if not path.is_file() or path.is_symlink() or root not in path.resolve().parents:raise CandidateError('missing/unsafe candidate file: '+relative)
    if path.stat().st_size>limit:raise CandidateError('candidate file exceeds delivery limit: '+relative)
    return path

def read_ledger(path):
    try:value=json.loads(Path(path).read_text(encoding='utf-8'))
    except (ValueError,UnicodeError) as exc:raise CandidateError('sources.json must be UTF-8 JSON') from exc
    if not isinstance(value,dict):raise CandidateError('sources.json must be an object')
    return value

def _column(address):
    result=0
    for char in re.match('[A-Z]+',address).group():result=result*26+ord(char)-64
    return result

def read_book(path):
    """Read native values/visibility/editability; formulas require Office first."""
    try:
        with zipfile.ZipFile(path) as archive:
            def xml(name):return ET.fromstring(archive.read(name))
            strings=[]
            if 'xl/sharedStrings.xml' in archive.namelist():strings=[''.join(n.itertext()) for n in xml('xl/sharedStrings.xml').findall(S+'si')]
            styles=[]
            if 'xl/styles.xml' in archive.namelist():
                tree=xml('xl/styles.xml');formats={int(n.get('numFmtId')):n.get('formatCode','') for n in tree.findall(S+'numFmts/'+S+'numFmt')}
                fonts=list(tree.find(S+'fonts') or []);fills=list(tree.find(S+'fills') or [])
                for node in tree.findall(S+'cellXfs/'+S+'xf'):
                    fmt=formats.get(int(node.get('numFmtId','0')),'');font=fonts[int(node.get('fontId','0'))] if fonts else None;fill=fills[int(node.get('fillId','0'))] if fills else None
                    size=font.find(S+'sz') if font is not None else None;color=font.find(S+'color') if font is not None else None;fg=fill.find(S+'patternFill/'+S+'fgColor') if fill is not None else None
                    hidden=fmt.replace(' ','')==';;;' or size is not None and float(size.get('val','11'))<=0
                    if color is not None and color.get('rgb'):
                        rgb=color.get('rgb')[-6:].upper();background=fg.get('rgb','')[-6:].upper() if fg is not None else ''
                        hidden=hidden or rgb==background or rgb=='FFFFFF' and background in {'','FFFFFF'}
                    protection=node.find(S+'protection')
                    styles.append({'visible':not hidden,'locked':protection is None or protection.get('locked','1') not in {'0','false'}})
            relationships={n.get('Id'):posixpath.normpath(posixpath.join('xl',n.get('Target',''))) if not n.get('Target','').startswith('/') else n.get('Target').lstrip('/') for n in xml('xl/_rels/workbook.xml.rels')}
            result=[]
            for sheet in xml('xl/workbook.xml').findall(S+'sheets/'+S+'sheet'):
                tree=xml(relationships[sheet.get(R+'id')]);cells={};hidden_columns=set();protected=tree.find(S+'sheetProtection')
                sheet_protected=protected is not None and protected.get('sheet','1') not in {'0','false'}
                for column in tree.findall(S+'cols/'+S+'col'):
                    if column.get('hidden') in {'1','true'} or column.get('width')=='0':hidden_columns.update(range(int(column.get('min')),int(column.get('max'))+1))
                for row in tree.findall(S+'sheetData/'+S+'row'):
                    visible=row.get('hidden') not in {'1','true'} and row.get('ht')!='0'
                    for cell in row.findall(S+'c'):
                        address=cell.get('r');column=_column(address);rownum=int(re.search(r'\d+',address).group());node=cell.find(S+'v');value=node.text if node is not None else None;kind=cell.get('t')
                        style=styles[int(cell.get('s','0'))] if styles else {'visible':True,'locked':True}
                        if kind=='inlineStr':value=''.join(cell.find(S+'is').itertext()) if cell.find(S+'is') is not None else ''
                        elif kind=='s':value=strings[int(value)]
                        elif kind=='b':value=value=='1'
                        elif kind not in {'str','e','d'} and value is not None:
                            value=float(value);value=int(value) if value.is_integer() else value
                        cells[(rownum,column)]={'value':value,'visible':sheet.get('state','visible')=='visible' and visible and column not in hidden_columns and style['visible'],'editable':not sheet_protected or not style['locked'],'formula':cell.find(S+'f') is not None,'address':address}
                result.append({'name':sheet.get('name'),'state':sheet.get('state','visible'),'cells':cells})
            return result
    except (zipfile.BadZipFile,KeyError,ET.ParseError,ValueError,TypeError,IndexError,AttributeError,OverflowError) as exc:raise CandidateError('invalid native XLSX package: '+str(exc)) from exc

def _put(target,path,value):
    keys=path.split('.') if isinstance(path,str) else path
    for key in keys[:-1]:
        if key not in target:target[key]={}
        if not isinstance(target[key],dict):raise CandidateError('conflicting native subfield paths')
        target=target[key]
    target[keys[-1]]=value

def _topic_values(value,catalog):
    """Explicit ten-topic objects, including nested field identifiers."""
    result=[]
    def walk(node,prefix=''):
        if not isinstance(node,dict):return
        for key,item in node.items():
            path=(prefix+'.'+str(key)).strip('.')
            match=next((f for f in catalog if path==f['field_id'] or norm(path)==norm(f['label_zh'])),None)
            if match:result.append((match['field_id'],item))
            else:walk(item,path)
    walk(value)
    return result

def extract_records(book,contract):
    """Discover row tables, record subcolumns/subrows and ten topic objects.

    Identifiers and public column meanings are anchors; no Sheet/coordinate map.
    Ambiguous duplicates are retained for the comparison layer, never selected.
    """
    aliases={norm(a):key for key,values in contract['public_schema']['column_aliases'].items() for a in [key]+values}
    aliases.update({norm(x):'subfield' for x in ['subfield','leaf','leaf_id','path','子字段','子字段名','子字段路径']})
    catalog=contract['field_catalog'];field_alias={norm(a):f['field_id'] for f in catalog for a in [f['field_id'],f['label_zh']]}
    facts={f['field_id']:[] for f in catalog};vectors={};headers=[]
    for sheet in book:
        cells=sheet['cells'];rows=sorted({r for r,c in cells});found=[]
        for row in rows:
            raw={c:o['value'] for (r,c),o in cells.items() if r==row};mapped={c:aliases.get(norm(v)) for c,v in raw.items()}
            anchors=[(c,k) for c,k in mapped.items() if k in {'field_id','vector_id'}]
            if not anchors and 'topic_id' in mapped.values() and 'value' in mapped.values():anchors=[(c,k) for c,k in mapped.items() if k=='topic_id']
            for anchor,kind in anchors:
                # A single header may host fact and signature tables side by side.
                others=[c for c,k in anchors if c!=anchor];lo=max([c+1 for c in others if c<anchor]+[1]);hi=min([c for c in others if c>anchor]+[max(raw,default=anchor)+1])
                mapping={};extras={}
                for c,v in raw.items():
                    if not lo<=c<hi:continue
                    key=mapped[c]
                    if key and key not in mapping:mapping[key]=c
                    elif v is not None and str(v).strip():extras[str(v).strip()]=c
                if kind=='vector_id' and not {'md5_hex','signa_base64','signa_urlencoded'}<=set(mapping):continue
                if kind!='vector_id' and 'value' not in mapping and not extras:continue
                found.append((row,kind,mapping,extras));headers.append({'sheet':sheet['name'],'row':row,'kind':kind})
        for row,kind,mapping,extras in found:
            end=min([r for r,k,m,e in found if r>row]+[max(rows,default=row)+1]);last_field=None
            header_ok=all(cells[(row,c)]['visible'] and cells[(row,c)]['editable'] for c in mapping.values())
            for rr in range(row+1,end):
                values={k:parse_value(cells.get((rr,c),{}).get('value')) for k,c in mapping.items()}
                original_id=values.get(kind);field=field_alias.get(norm(original_id)) if kind=='field_id' else None;subfield=values.get('subfield')
                if kind=='field_id' and field is None and isinstance(original_id,str):
                    for f in catalog:
                        if original_id.startswith(f['field_id']+'.'):field=f['field_id'];subfield=original_id[len(field)+1:];break
                if kind=='field_id' and field is None and original_id is None and subfield and last_field:field=last_field
                if kind=='field_id' and field is None:continue
                if kind=='vector_id' and (not isinstance(original_id,str) or not re.fullmatch('SIG-0[1-3]',original_id)):continue
                if kind=='topic_id' and (not isinstance(original_id,str) or not re.fullmatch('T\d\d',original_id)):continue
                actual_cells=[cells[(rr,c)] for c in set(mapping.values())|set(extras.values()) if (rr,c) in cells]
                metadata={k:v for k,v in values.items() if k not in {'field_id','vector_id','value','subfield'}}
                metadata.update(_visible=header_ok and all(c['visible'] for c in actual_cells),_editable=all(c['editable'] for c in actual_cells),_location={'sheet':sheet['name'],'row':rr})
                if kind=='vector_id':vectors.setdefault(original_id,[]).append(dict(metadata,**values));continue
                if kind=='topic_id':
                    for field,item in _topic_values(values.get('value'),catalog):
                        m=dict(metadata)
                        if isinstance(item,dict) and 'value' in item:m.update({k:v for k,v in item.items() if k!='value'});item=item['value']
                        facts[field].append(dict(m,value=item))
                    continue
                last_field=field
                value=values.get('value',MISSING)
                if subfield:
                    container={};_put(container,str(subfield),value);value=container
                    for metakey in ('status','unit'):
                        metaval=metadata.get(metakey)
                        if metaval is not None and not isinstance(metaval,dict):
                            nested={};_put(nested,str(subfield),metaval);metadata[metakey]=nested
                elif extras:
                    container={};spec=next(f for f in catalog if f['field_id']==field);shape=spec['value_shape']
                    if isinstance(shape,list):shape=shape[0]
                    allowed=set(shape) if isinstance(shape,dict) else {'action','code','data','desc','sid'} if field=='response.envelope_types' else set()
                    for key,c in extras.items():
                        item=cells.get((rr,c),{}).get('value');key=re.sub(r'^(?:value\.|值\.)','',key)
                        if key.split('.')[0] in allowed and (item is not None or value is MISSING or value is None):_put(container,key,parse_value(item))
                    if container:
                        if value is MISSING or value is None:value=container
                        elif isinstance(value,dict):value,bad=_merge(value,container);metadata['_extraction_conflict']=bad
                facts[field].append(dict(metadata,value=value))
    return facts,vectors,headers

def _merge(a,b):
    if a is MISSING:return b,False
    if isinstance(a,dict) and isinstance(b,dict):
        result=dict(a);conflict=False
        for k,v in b.items():result[k],bad=_merge(result.get(k,MISSING),v);conflict=conflict or bad
        return result,conflict
    if type(a) is type(b) and a==b:return a,False
    return a,True

def combine_rows(rows,field,contract):
    if not rows:return {'value':MISSING,'status':None,'unit':None,'conflict':False,'metadata_conflicts':[],'rows':[]}
    is_set=next(f['value_type'] for f in contract['field_catalog'] if f['field_id']==field)=='record_set'
    value=MISSING;conflict=False;status=None;unit=None;metadata_conflicts=[]
    for row in rows:
        conflict=conflict or row.get('_extraction_conflict',False)
        item=row.get('value',MISSING)
        if is_set:
            if isinstance(item,dict):item=[item]
            if isinstance(item,list):
                if value is MISSING:value=[]
                if isinstance(value,list):value.extend(item)
                else:conflict=True
            else:conflict=True
        else:value,bad=_merge(value,item);conflict=conflict or bad
        for key in ('status','unit'):
            present=row.get(key)
            if present is None:continue
            current=status if key=='status' else unit
            if current is None:current=present
            elif isinstance(current,dict) and isinstance(present,dict):current,bad=_merge(current,present);conflict=conflict or bad
            elif norm(current)!=norm(present):metadata_conflicts.append(key)
            if key=='status':status=current
            else:unit=current
    return {'value':value,'status':status,'unit':unit,'conflict':conflict,'metadata_conflicts':metadata_conflicts,'rows':rows}

def enum_value(value,path,contract):
    schema=contract['public_schema'];mapping=schema['enum_field_vocabulary'];vocab=mapping.get(path)
    if vocab is None and path.startswith('response.envelope_types.'):vocab=mapping.get('response.envelope_types.*')
    if vocab is None:return value
    permitted=schema['enum_vocabulary'][vocab]
    for canonical in permitted:
        alternatives=[canonical]+schema['enum_aliases'].get(canonical,[])
        # Parameter names are protocol tokens. apiKey has explicitly published aliases.
        sensitive=vocab=='signing_terms' and canonical in {'appid','ts','signa','path','sorted_query'}
        if any(value==x if sensitive else norm(value)==norm(x) for x in alternatives):return canonical
    return value

def _unit_number(value,unit,path):
    if isinstance(value,str):
        match=re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([^\d\s].*)?\s*',value)
        if match:
            value=number(match.group(1));unit=match.group(2) or unit
    value=number(value)
    if value is None:return None
    if isinstance(unit,dict):unit=unit.get(path.split('.')[-1])
    if unit is None or unit=='':return value
    if not isinstance(unit,str):return None
    u=norm(unit).replace('per','/');units={
        'audio.sample_rate':{'hz':1,'赫兹':1,'khz':1000,'千赫兹':1000},
        'audio.bit_depth':{'bit':1,'bits':1,'bit/sample':1,'bits/sample':1,'位':1,'byte':8,'bytes':8,'字节':8},
        'audio.channels':{'channel':1,'channels':1,'声道':1},
        'cadence.recommended_interval':{'ms':1,'毫秒':1,'s':1000,'seconds':1000,'秒':1000},
        'cadence.recommended_chunk':{'b':1,'byte':1,'bytes':1,'字节':1,'bit':.125,'bits':.125,'位':.125,'kib':1024,'kb':1000},
        'audio.idle_timeout.threshold_seconds':{'s':1,'秒':1,'seconds':1,'ms':.001,'毫秒':.001},
        'ip_whitelist.rules.propagation_minutes_approx':{'min':1,'minute':1,'minutes':1,'分钟':1,'s':1/60,'秒':1/60,'seconds':1/60}}
    allowed=units.get(path)
    return value*allowed[u] if allowed is not None and u in allowed else value if allowed is None else None

def compare_field(field,record,truth,contract):
    """Leaf observations then one mean per field, independent of other fields."""
    leaves=[]
    def fail_all(expected,path,reason):
        if isinstance(expected,dict):
            for key,v in expected.items():fail_all(v,path+'.'+key,reason)
        elif isinstance(expected,list):
            for i,v in enumerate(expected):fail_all(v,path+'['+str(i)+']',reason)
        else:leaves.append({'path':path,'passed':False,'reason':reason,'expected':expected})
    def walk(actual,expected,path,status):
        if isinstance(actual,dict) and 'value' in actual and set(actual)<={'value','status','unit','requirement_strength','citation_ids'}:
            status=actual.get('status',status);actual=actual['value']
        if isinstance(expected,dict):
            if not isinstance(actual,dict):fail_all(expected,path,'missing/incorrect record shape');return
            extras=set(actual)-set(expected)
            if extras:fail_all(expected,path,'unexpected record keys: '+','.join(sorted(extras)));return
            for key,v in expected.items():walk(actual.get(key,MISSING),v,path+'.'+key,status.get(key) if isinstance(status,dict) else status)
            return
        if isinstance(expected,list):
            if isinstance(actual,str):actual=parse_value(actual)
            if not isinstance(actual,list):fail_all(expected,path,'missing/incorrect array shape');return
            if path in {'handshake.required_query','errors.selected_map'}:
                key='name' if path=='handshake.required_query' else 'code';groups={}
                for item in actual:
                    if isinstance(item,dict):groups.setdefault(str(item.get(key)),[]).append(item)
                expected_keys={str(item[key]) for item in expected}
                if set(groups)-expected_keys or sum(len(v) for v in groups.values())!=len(actual):fail_all(expected,path,'unexpected/malformed record-set members');return
                for item in expected:
                    matches=groups.get(str(item[key]),[])
                    if len(matches)!=1:fail_all(item,path+'['+str(item[key])+']','record set key missing/duplicated')
                    else:
                        # [] vocabulary path is separate from observation key path.
                        for k,v in item.items():walk(matches[0].get(k,MISSING),v,path+'[].'+k,status)
                return
            if len(actual)>len(expected):fail_all(expected,path,'extra array members');return
            ordered=path=='signature.base_string.ordered_terms'
            if not ordered:
                actual=sorted(actual,key=lambda x:str(enum_value(x,path,contract)))
                expected=sorted(expected,key=lambda x:str(x))
            for index,v in enumerate(expected):walk(actual[index] if index<len(actual) else MISSING,v,path+('['+str(index)+']' if ordered else ''),status)
            return
        if actual is MISSING:passed=False;reason='required leaf missing';observed=None
        elif expected is None:
            passed=unknown(actual) and norm(status) in {'not_documented','mixed','未知','文档未说明','未规定'};reason='explicit unknown and status' if passed else 'null must be explicit unknown; zero is a real value';observed=actual
        elif isinstance(expected,bool):
            observed=actual
            if isinstance(actual,str) and path!='end.payload.end':
                for boolean,aliases in contract['public_schema']['boolean_aliases'].items():
                    if norm(actual) in {norm(x) for x in aliases}:observed=boolean=='true';break
            passed=type(observed) is bool and observed is expected;reason='boolean semantic value (integer 1/0 is not boolean)'
        elif isinstance(expected,(int,float)):
            observed=_unit_number(actual,record.get('unit'),path);passed=observed is not None and math.isclose(observed,expected,rel_tol=1e-9,abs_tol=1e-9);reason='numeric value in declared equivalent units'
        else:
            # Empty separator is a known empty string and must not enter unknown().
            basepath=re.sub(r'\[\d+\]$','',path);observed=enum_value(actual,basepath,contract)
            if path.startswith('connection.endpoint.') and isinstance(observed,str):
                observed=observed.rstrip('/')
                if observed=='ws[s]://rtasr.xfyun.cn/v1/ws':observed=expected
            if path=='optional.punc.filter_value' or path.endswith(('.unauthorized_code','.code')):
                if not isinstance(observed,bool) and integer(observed) is not None:observed=str(integer(observed))
            passed=type(observed) is str and observed==expected;reason='exact typed value or frozen discrete alias'
        leaves.append({'path':path,'expected':expected,'observed':observed,'passed':passed,'reason':reason})
    if record['conflict']:fail_all(truth['value'],field,'conflicting duplicate field values')
    else:walk(record['value'],truth['value'],field,record['status'])
    return {'score':mean(int(x['passed']) for x in leaves),'leaves':leaves,'locations':[r['_location'] for r in record['rows']],'conflict':record['conflict']}

def compare_vector(rows,truth):
    results={};unique=len(rows)==1;row=rows[0] if unique else {}
    for key in ('md5_hex','signa_base64','signa_urlencoded'):
        actual=row.get(key);expected=truth[key];passed=False
        if isinstance(actual,str):
            if key=='md5_hex':passed=bool(re.fullmatch('[0-9a-fA-F]{32}',actual)) and actual.lower()==expected
            elif key=='signa_base64':passed=actual==expected
            else:
                # Only percent-hex case is normalized; no decoding or URLsafe conversion.
                canonical=lambda s:re.sub('%[0-9a-fA-F]{2}',lambda m:m.group().upper(),s)
                passed=canonical(actual)==canonical(expected)
        results[key]={'passed':bool(unique and passed),'observed':actual,'expected':expected}
    return {'score':mean(int(v['passed']) for v in results.values()),'checks':results,'unique':unique}

def _trusted_path(root,relative):
    if not isinstance(relative,str) or '\\' in relative or PurePosixPath(relative).is_absolute() or any(p in {'','..','.'} for p in relative.split('/')):raise TrustedEvidenceError('unsafe research bundle path')
    path=root/relative
    if not path.is_file() or path.is_symlink() or root not in path.resolve().parents:raise TrustedEvidenceError('research bundle file missing/unsafe: '+relative)
    return path

def load_bundle(ledger):
    root_env=os.environ.get('GENERAL_E2E_RESEARCH_SOURCE_BUNDLE');digest=os.environ.get('GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256')
    if not root_env or not digest:raise TrustedEvidenceError('managed independent research bundle context missing')
    root=Path(root_env).resolve();path=_trusted_path(root,'manifest.json')
    if sha(path)!=digest:raise TrustedEvidenceError('research manifest SHA drift')
    try:manifest=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError) as exc:raise TrustedEvidenceError('invalid trusted manifest') from exc
    if not isinstance(manifest,dict) or not isinstance(manifest.get('sources'),list) or not isinstance(manifest.get('candidate_input_status'),str) or manifest.get('candidate_input_status') not in {'valid','missing_ledger','invalid_ledger'}:raise TrustedEvidenceError('research manifest contract invalid')
    if manifest.get('errors') and (manifest['candidate_input_status']=='valid' or manifest['sources']):raise TrustedEvidenceError('research collector reported unresolved errors')
    source_rows=ledger.get('sources',[]) if ledger else [];source_rows=source_rows if isinstance(source_rows,list) else []
    ledgermap={s.get('source_id'):s for s in source_rows if isinstance(s,dict) and isinstance(s.get('source_id'),str)};byid={}
    for source in manifest['sources']:
        if not isinstance(source,dict) or not isinstance(source.get('status'),str) or source.get('status') not in {'acquired','not_requested','candidate_invalid'}:raise TrustedEvidenceError('source acquisition status invalid')
        sid=source.get('source_id')
        if not isinstance(sid,str) or sid in byid:raise TrustedEvidenceError('duplicate/missing bundle source ID')
        if ledger is not None and manifest['candidate_input_status']=='valid':
            row=ledgermap.get(sid)
            if row is None or source.get('url')!=row.get('url') or source.get('citations')!=row.get('citations'):raise TrustedEvidenceError('research bundle / candidate ledger binding drift: '+sid)
        if source['status']=='acquired':
            paths={}
            for part in ('body','text','projection','receipt'):
                p=_trusted_path(root,source.get(part+'_path'))
                if not isinstance(source.get(part+'_sha256'),str) or sha(p)!=source[part+'_sha256']:raise TrustedEvidenceError('research '+part+' SHA drift: '+sid)
                paths[part]=p
            try:projection=json.loads(paths['projection'].read_text(encoding='utf-8'));receipt=json.loads(paths['receipt'].read_text(encoding='utf-8'))
            except (ValueError,UnicodeError) as exc:raise TrustedEvidenceError('invalid trusted source projection/receipt') from exc
            if projection.get('schema_version')!='wildclawbench.research-source-text/v1' or projection.get('source_sha256')!=source['body_sha256'] or projection.get('complete') is not True or not isinstance(projection.get('records'),list) or not projection.get('engine'):raise TrustedEvidenceError('source extraction incomplete/unbound: '+sid)
            if receipt.get('requested_url')!=source['url'] or receipt.get('final_url')!=source.get('final_url') or receipt.get('body_sha256')!=source['body_sha256']:raise TrustedEvidenceError('source receipt identity drift: '+sid)
            source=dict(source,_text=projection,_body=paths['body'].read_bytes())
        byid[sid]=source
    if ledger is not None and manifest['candidate_input_status']=='valid':
        statuses={'read_full','read_excerpt'}
        selected={sid for sid,s in ledgermap.items() if isinstance(s.get('access_status'),str) and s.get('access_status') in statuses or bool(s.get('citations'))}
        if set(byid)!=selected:raise TrustedEvidenceError('research selected source set binding drift')
    return manifest,byid

class _Html(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.headings=[];self.anchors={};self.tables=[];self.table=None;self.row=None;self.cell=None;self.heading=None;self.ignore=0
    def text_offset(self):return sum(len(x) for x in self.parts)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in {'script','style','noscript'}:self.ignore+=1
        if self.ignore:return
        if tag in {'p','div','li','br','table','tr','td','th','pre','h1','h2','h3','h4','h5','h6'}:self.parts.append('\n' if tag not in {'td','th'} else ' ')
        if attrs.get('id'):self.anchors[attrs['id']]=self.text_offset()
        if re.fullmatch('h[1-6]',tag):self.heading={'level':int(tag[1]),'start':self.text_offset(),'parts':[],'id':attrs.get('id')}
        if tag=='table':self.table={'start':self.text_offset(),'rows':[],'heading':self.headings[-1]['text'] if self.headings else ''}
        if tag=='tr' and self.table is not None:self.row=[]
        if tag in {'td','th'} and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.ignore:return
        self.parts.append(data)
        if self.heading is not None:self.heading['parts'].append(data)
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript'}:self.ignore=max(0,self.ignore-1);return
        if self.ignore:return
        if re.fullmatch('h[1-6]',tag) and self.heading is not None:
            self.heading['text']=textnorm(''.join(self.heading.pop('parts'))).lstrip('# ').strip();self.headings.append(self.heading);self.heading=None
        if tag in {'td','th'} and self.cell is not None:self.row.append(textnorm(''.join(self.cell)));self.cell=None
        if tag=='tr' and self.table is not None and self.row is not None:self.table['rows'].append(self.row);self.row=None
        if tag=='table' and self.table is not None:self.table['end']=self.text_offset();self.tables.append(self.table);self.table=None
        if tag in {'p','div','li','tr','pre','h1','h2','h3','h4','h5','h6'}:self.parts.append('\n')

def _quote_match(quote,text,table=False):
    # Markdown pipes only denote cell boundaries. Content punctuation/numbers/case remain.
    def clean(value):
        value=textnorm(value)
        if table:value=re.sub(r'\|',' ',value);value=re.sub(r'\s+','',value)
        return value
    quote=clean(quote);text=clean(text)
    if quote and quote in text:return True
    parts=[s for s in re.split(r'(?:\.{3}|…+|\[\.\.\.\])',quote) if s]
    if len(parts)<2:return False
    offset=0
    for part in parts:
        pos=text.find(part,offset)
        if pos<0:return False
        offset=pos+len(part)
    return True

def resolve_citation(source,citation):
    if not source or source['status']!='acquired':return False,'source not independently acquired'
    if not isinstance(citation,dict) or not isinstance(citation.get('quote'),str) or not citation['quote'].strip() or not isinstance(citation.get('locator'),dict):return False,'missing locator/quote'
    locator=citation['locator'];projection=source['_text']['records'];full='\n'.join(str(r.get('text','')) for r in projection);selected=None;table=False
    html='html' in source.get('media_type','').lower() or source['_body'].lstrip().lower().startswith((b'<!doctype html',b'<html'))
    parser=None
    if html:
        try:parser=_Html();parser.feed(source['_body'].decode('utf-8-sig'));parser.close()
        except (ValueError,UnicodeError):return False,'source HTML cannot be located'
        full=''.join(parser.parts)
    start=0;end=len(full)
    if 'heading' in locator:
        if not isinstance(locator['heading'],str):return False,'invalid heading locator'
        title=textnorm(locator['heading']).lstrip('# ').strip()
        if parser:
            matches=[h for h in parser.headings if h['text']==title]
            if not matches:return False,'heading not present in source'
            if len(matches)>1 and not locator.get('anchor'):return False,'heading is ambiguous; provide anchor'
            heading=matches[0];start=heading['start'];end=min([h['start'] for h in parser.headings if h['start']>start and h['level']<=heading['level']]+[len(full)])
        else:
            start=full.find(title)
            if start<0:return False,'heading not present in source'
    if 'anchor' in locator:
        if not parser:return False,'anchor requires HTML'
        anchor=urllib.parse.unquote(str(locator['anchor']).lstrip('#'))
        if anchor not in parser.anchors:return False,'anchor not present in source'
        start=parser.anchors[anchor];end=min([h['start'] for h in parser.headings if h['start']>start]+[len(full)])
    row_locator=locator.get('table_row',locator.get('row'))
    if 'table' in locator or row_locator is not None or 'cell' in locator:
        if not parser:return False,'logical table locator requires HTML'
        tables=[t for t in parser.tables if t['start']>=start and t['start']<end]
        requested=locator.get('table')
        if isinstance(requested,dict):row_locator=requested.get('row',requested.get('table_row',row_locator));requested=requested.get('index',requested.get('heading'))
        if requested is not None and not isinstance(requested,(str,int,float)):return False,'invalid logical table locator'
        if integer(requested) is not None:
            index=integer(requested);tables=tables[index-1:index] if index>0 else []
        elif isinstance(requested,str) and requested.strip():tables=[t for t in tables if textnorm(requested) in {textnorm(t['heading']),textnorm(' '.join(t['rows'][0])) if t['rows'] else ''}]
        rows=[r for t in tables for r in t['rows']]
        if row_locator is not None:
            if isinstance(row_locator,(int,float)) and 'table_row' not in locator:
                index=integer(row_locator);rows=rows[index-1:index] if index and index>0 else []
            else:rows=[r for r in rows if str(row_locator) in r or any(textnorm(row_locator)==textnorm(c) for c in r)]
        if not rows:return False,'logical table/row does not resolve'
        if 'cell' in locator:
            cell=locator['cell']
            if isinstance(cell,int) and not isinstance(cell,bool) and cell>0:rows=[[r[cell-1]] for r in rows if len(r)>=cell]
            elif isinstance(cell,str):
                columns=[i for t in tables if t['rows'] for i,v in enumerate(t['rows'][0]) if textnorm(v)==textnorm(cell)]
                rows=[[r[c]] for r in rows for c in sorted(set(columns)) if len(r)>c]
            else:return False,'invalid logical cell locator'
            if not rows:return False,'logical cell does not resolve'
        selected='\n'.join(' | '.join(r) for r in rows);table=True
    elif 'lines' in locator:
        limits=locator['lines'];lines=full.splitlines()
        if not isinstance(limits,list) or len(limits)!=2 or any(integer(v) is None for v in limits):return False,'invalid line locator'
        first,last=map(integer,limits)
        if first<1 or last<first or last>len(lines):return False,'line locator outside source'
        selected='\n'.join(lines[first-1:last])
    elif 'page' in locator:
        page=integer(locator['page']);selected='\n'.join(str(r.get('text','')) for r in projection if integer(r.get('locator',{}).get('page'))==page) if page and page>0 else ''
    elif 'heading' in locator or 'anchor' in locator:selected=full[start:end]
    if not selected:return False,'locator does not resolve to source text'
    return (True,'verbatim normalized quote at actual locator') if _quote_match(citation['quote'],selected,table) else (False,'quote not at locator')
