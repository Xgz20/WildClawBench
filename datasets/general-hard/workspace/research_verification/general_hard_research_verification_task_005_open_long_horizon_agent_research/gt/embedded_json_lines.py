"""Facts-free deterministic JSON string-array source decoding; never runs code.

The caller supplies exact bytes of one independently acquired HTML script node.
Array entries remain literal JSON strings: HTML entities are never decoded a
second time. Source-file byte equivalence needs an explicit reconstruction
policy and an independently meaningful SHA, not a guessed final newline.
"""
import hashlib
import json
import re

class EmbeddedJSONError(RuntimeError):pass

def sha(data):return hashlib.sha256(data).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False)
def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=value
    return result
def tokens(pointer):
    if not isinstance(pointer,str) or pointer and not pointer.startswith('/') or re.search(r'~(?![01])',pointer):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_POINTER: strict RFC6901 pointer required')
    return [] if pointer=='' else [p.replace('~1','/').replace('~0','~') for p in pointer[1:].split('/')]
def at(value,pointer):
    for key in tokens(pointer):
        if isinstance(value,dict) and key in value:value=value[key]
        elif isinstance(value,list) and len(key)<=6 and re.fullmatch(r'0|[1-9][0-9]*',key) and int(key)<len(value):value=value[int(key)]
        else:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_FIELD: requested actual JSON node absent')
    return value
def setting(locator,name,*aliases,default=None):
    decoded=locator.get('decoded',{})
    if not isinstance(decoded,dict):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_LOCATOR: decoded settings must be object')
    values=[obj[key] for obj in (locator,decoded) for key in (name,*aliases) if key in obj]
    if not values:return default
    try:equal=all(canonical(v)==canonical(values[0]) for v in values)
    except (ValueError,TypeError,RecursionError) as exc:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_LOCATOR: non-JSON settings') from exc
    if not equal:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_LOCATOR: contradictory aliases')
    return values[0]
def line_range(locator,count):
    value=setting(locator,'lines','line_range')
    if value is None:
        first=setting(locator,'start_line','line_start');last=setting(locator,'end_line','line_end',default=first)
        if first is not None:value=[first,last]
    raw_range=setting(locator,'rawLines_range',default={})
    if not isinstance(raw_range,dict):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_LINES: raw array range must be object')
    for key in ('start_index_0based','end_index_0based_inclusive'):
        declared=setting(locator,key)
        if key in raw_range and declared is not None and (type(declared) is not type(raw_range[key]) or declared!=raw_range[key]):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_LINES: contradictory raw array range aliases')
    raw_first=setting(locator,'start_index_0based',default=raw_range.get('start_index_0based'));raw_last=setting(locator,'end_index_0based_inclusive',default=raw_range.get('end_index_0based_inclusive',raw_first))
    raw=None
    if raw_first is not None:
        if type(raw_first) is not int or type(raw_last) is not int:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_LINES: integral raw array indices required')
        raw=[raw_first+1,raw_last+1]
    if isinstance(value,str):
        match=re.fullmatch(r'\s*L?([1-9][0-9]*)\s*(?:[-:]\s*L?([1-9][0-9]*))?\s*',value,re.I)
        if match:value=[int(match[1]),int(match[2] or match[1])]
    if type(value) is int:value=[value,value]
    if isinstance(value,dict):value=[value.get('start'),value.get('end',value.get('start'))]
    if raw is not None:
        if value is not None and canonical(value)!=canonical(raw):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_LINES: source lines and array indices disagree')
        value=raw
    if not isinstance(value,list) or len(value)!=2 or any(type(v) is not int for v in value):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_LINES: explicit1-based closed line range required')
    first,last=value
    return (first,last,1<=first<=last<=count)

def decode(script_bytes,locator,origin):
    if not isinstance(script_bytes,bytes) or len(script_bytes)>20*1024*1024:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_BODY: bounded original script bytes required')
    encoding=setting(locator,'encoding',default='json-string-array')
    if encoding!='json-string-array':raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_ENCODING: only explicit JSON string-array decoding is supported')
    separator=setting(locator,'line_separator');terminal=setting(locator,'terminal_newline')
    if separator not in ('\n','\r\n') or type(terminal) is not bool:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_RECONSTRUCTION: explicit LF/CRLF separator and boolean terminal_newline required')
    pointer=setting(locator,'json_pointer','JSONPointer','raw_lines_json_pointer')
    try:
        value=json.loads(script_bytes.decode('utf-8',errors='strict'),object_pairs_hook=unique,parse_constant=lambda c:(_ for _ in ()).throw(ValueError(c)))
    except (ValueError,TypeError,UnicodeError,RecursionError) as exc:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_DATA: actual script is not strict UTF-8 JSON') from exc
    entries=at(value,pointer)
    if not isinstance(entries,list) or len(entries)>100000 or any(not isinstance(v,str) or '\n' in v or '\r' in v for v in entries):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_ARRAY: actual pointer must contain bounded separate literal string lines')
    bindings=setting(locator,'bindings',default=[])
    if not isinstance(bindings,list):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_BINDINGS: list required')
    checks=[]
    for binding in bindings:
        if not isinstance(binding,dict) or 'equals' not in binding:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_BINDINGS: pointer and expected actual JSON value required')
        actual=at(value,binding.get('json_pointer'))
        checks.append({'json_pointer':binding['json_pointer'],'actual':actual,'declared':binding['equals'],'matches':canonical(actual)==canonical(binding['equals'])})
    try:
        pieces=[(entry+(separator if i<len(entries)-1 or terminal else '')).encode('utf-8',errors='strict') for i,entry in enumerate(entries)]
    except UnicodeError as exc:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_UNICODE: unpaired surrogate in original string') from exc
    raw=b''.join(pieces)
    if len(raw)>64*1024*1024:raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_BUDGET: reconstructed source too large')
    actual_sha=sha(raw);expected_sha=setting(locator,'decoded_sha256','reconstructed_source_sha256')
    if expected_sha is not None and (not isinstance(expected_sha,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',expected_sha)):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_SHA: full SHA256 required')
    blob=setting(locator,'blob_sha');blob_pointer=setting(locator,'blob_sha_json_pointer')
    if blob_pointer is not None:
        actual_blob_field=at(value,blob_pointer)
        if blob is not None and actual_blob_field!=blob:checks.append({'json_pointer':blob_pointer,'actual':actual_blob_field,'declared':blob,'matches':False})
        blob=actual_blob_field
    blob_actual=None;blob_algorithm=None
    if blob is not None:
        if not isinstance(blob,str) or not re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})',blob):raise EmbeddedJSONError('UNSUPPORTED_EMBEDDED_JSON_BLOB: full SHA1/SHA256 Git blob identifier required')
        blob_algorithm='sha1' if len(blob)==40 else 'sha256';blob_actual=hashlib.new(blob_algorithm,b'blob '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()
    first,last,inside=line_range(locator,len(entries));start=sum(map(len,pieces[:first-1])) if inside else None;end=sum(map(len,pieces[:last])) if inside else None
    selected=raw[start:end].decode('utf-8') if inside else ''
    failures=[]
    if not inside:failures.append('source line range outside actual string array')
    if any(not c['matches'] for c in checks):failures.append('actual same-script JSON binding differs')
    if expected_sha is not None and expected_sha.lower()!=actual_sha:failures.append('declared reconstructed SHA256 differs from actual deterministic bytes')
    if blob is not None and blob.lower()!=blob_actual:failures.append('declared Git blob differs from actual deterministic bytes')
    return {'selected_text':selected,'selected_text_sha256':sha(selected.encode('utf-8')),'decoded_line_range':[first,last],'raw_array_index_range_0based':[first-1,last-1],'decoded_byte_span':[start,end],'binding_failures':failures,'same_script_bindings':checks,'lineage':{**origin,'json_pointer':pointer,'encoding':encoding,'encoded_script_sha256':sha(script_bytes),'decoded_sha256':actual_sha,'decoded_bytes':len(raw),'decoded_line_count':len(entries),'reconstruction':{'line_separator':separator,'terminal_newline':terminal,'policy':'Only declared deterministic reconstruction; raw-file byte equivalence additionally requires independent source equality evidence'},'decoded_sha256_declared':expected_sha,'decoded_sha256_verified':None if expected_sha is None else expected_sha.lower()==actual_sha,'git_blob_sha':blob_actual,'git_blob_algorithm':blob_algorithm,'git_blob_verified':None if blob is None else blob.lower()==blob_actual,'code_executed':False,'network_get_performed_for_decoding':False,'HTML_entity_decoded':False},'selected_lines':[{'line':i+1,'raw_array_index_0based':i,'text':entries[i],'literal_string_sha256':sha(entries[i].encode('utf-8'))} for i in range(first-1,last)] if inside else []}
