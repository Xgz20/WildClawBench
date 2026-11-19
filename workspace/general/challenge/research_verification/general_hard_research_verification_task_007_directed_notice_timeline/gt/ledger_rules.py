"""Facts-free, bounded H033 ledger mechanics. No answer roster or count threshold."""
import json, re, math
from datetime import datetime, date, timezone,timedelta
from urllib.parse import urlsplit,unquote

class ContractError(RuntimeError): pass
class CandidateError(ValueError): pass
def sha(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()
def strict_json(path):
    if path.is_symlink() or not path.is_file():raise CandidateError('missing/unsafe JSON')
    if path.stat().st_size>8_000_000:raise ContractError('NEEDS_LEDGER_REVIEW: legal JSON exceeds bounded parser size')
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise CandidateError('duplicate JSON key: '+k)
            d[k]=v
        return d
    try:
        result=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(CandidateError('nonfinite JSON')))
        stack=[(result,0)];count=0
        while stack:
            item,depth=stack.pop();count+=1
            if depth>96 or count>300000:raise ContractError('NEEDS_LEDGER_REVIEW: bounded JSON depth/node limit')
            if isinstance(item,dict):stack.extend((v,depth+1) for v in item.values())
            elif isinstance(item,list):stack.extend((v,depth+1) for v in item)
        return result
    except (ValueError,UnicodeError,OSError) as e:raise CandidateError(str(e)) from e
    except RecursionError as e:raise ContractError('NEEDS_LEDGER_REVIEW: JSON parser nesting limit') from e
def pointer(root,p):
    if p=='':return root
    if not isinstance(p,str) or not p.startswith('/') or re.search(r'~(?![01])',p):raise CandidateError('invalid RFC6901 pointer')
    node=root
    for raw in p[1:].split('/'):
        key=raw.replace('~1','/').replace('~0','~')
        if isinstance(node,list):
            if not re.fullmatch(r'0|[1-9][0-9]*',key):raise CandidateError('noncanonical array pointer')
            i=int(key)
            if i>=len(node):raise CandidateError('array pointer missing')
            node=node[i]
        elif isinstance(node,dict) and key in node:node=node[key]
        else:raise CandidateError('pointer missing')
    return node
def schema_errors(value,schema):
    """Only the explicitly inventoried public schema vocabulary; unknown keyword fails trusted contract."""
    allowed={'$schema','$id','$defs','$ref','type','properties','required','additionalProperties','items','enum','const','minimum','oneOf','anyOf','description','title'}
    count=[0]
    def check(v,s,p,depth=0):
        count[0]+=1
        if depth>96 or count[0]>200000:raise ContractError('NEEDS_LEDGER_REVIEW: bounded schema validation limit')
        if set(s)-allowed:raise ContractError('unsupported trusted JSON schema keyword: '+repr(set(s)-allowed))
        if '$ref' in s:
            ref=s['$ref']
            if not ref.startswith('#/'):raise ContractError('only local trusted schema refs supported')
            try:target=pointer(schema,ref[1:])
            except CandidateError as e:raise ContractError('broken trusted schema ref') from e
            return check(v,target,p,depth+1)
        out=[]
        types=s.get('type');types=types if isinstance(types,list) else [types] if types else []
        valid={'object':isinstance(v,dict),'array':isinstance(v,list),'string':isinstance(v,str),'null':v is None,'boolean':type(v) is bool,'integer':type(v) is int,'number':type(v) is int or type(v) is float and math.isfinite(v)}
        if types and not any(valid.get(t,False) for t in types):return [{'path':p,'rule':'type','expected':types}]
        if 'const' in s and (type(v)!=type(s['const']) or v!=s['const']):out.append({'path':p,'rule':'const'})
        if 'enum' in s and not any(type(v)==type(x) and v==x for x in s['enum']):out.append({'path':p,'rule':'enum'})
        if 'minimum' in s and type(v) in (int,float) and v<s['minimum']:out.append({'path':p,'rule':'minimum'})
        if isinstance(v,dict):
            for k in s.get('required',[]):
                if k not in v:out.append({'path':p+'/'+k,'rule':'required'})
            props=s.get('properties',{})
            for k,child in v.items():
                if k in props:out+=check(child,props[k],p+'/'+k.replace('~','~0').replace('/','~1'),depth+1)
                elif s.get('additionalProperties') is False:out.append({'path':p+'/'+k,'rule':'additionalProperties'})
        if isinstance(v,list) and 'items' in s:
            for i,child in enumerate(v):out+=check(child,s['items'],p+'/'+str(i),depth+1)
        for op in ('anyOf','oneOf'):
            if op in s:
                hits=sum(not check(v,choice,p,depth+1) for choice in s[op])
                if (op=='anyOf' and hits==0) or (op=='oneOf' and hits!=1):out.append({'path':p,'rule':op})
        return out
    return check(value,schema,'')

SETS={'carrier':'carriers','document':'documents','matter':'matters','claim':'claims','action':'actions','unknown':'unknowns','relation':'relations','discovery':'discovery_observations'}
def graph_checks(data):
    errors=[];indexes={};citations={};pointers=[]
    def error(path,rule):errors.append({'path':path,'rule':rule})
    for kind,seq in SETS.items():
        index={}
        for i,row in enumerate(data.get(seq,[])):
            if not isinstance(row,dict):continue
            ident=row.get(kind+'_id');path='/'+seq+'/'+str(i)
            if not isinstance(ident,str) or not ident.strip() or ident in index:error(path,'missing_or_duplicate_'+kind+'_id')
            else:index[ident]=row
        indexes[kind]=index
    for i,s in enumerate(data.get('carriers',[])):
        if not isinstance(s,dict):continue
        for j,c in enumerate(s.get('citations',[])):
            if not isinstance(c,dict):continue
            cid=c.get('citation_id');p=f'/carriers/{i}/citations/{j}'
            if not isinstance(cid,str) or not cid.strip() or cid in citations:error(p,'missing_or_duplicate_global_CID')
            else:citations[cid]=(s,c,p)
            if c.get('carrier_id',s.get('carrier_id'))!=s.get('carrier_id'):error(p,'citation_carrier_mismatch')
            if not c.get('quote','').strip():error(p,'empty_quote')
            targets=c.get('supports_fields',[])
            if not targets:error(p,'empty_support_targets')
            for target in targets:
                try:
                    pointer(data,target)
                    if re.match(r'^/carriers/\d+/citations(?:/|$)',target):raise CandidateError('self supporting citation')
                    pointers.append({'citation_id':cid,'pointer':target})
                except CandidateError:error(p,'unresolved_or_self_support_pointer:'+str(target))
    def ref(kind,ident,path):
        if ident not in indexes.get(kind,{}):error(path,'unresolved_'+kind+':'+str(ident))
    def visit(v,p=''):
        if isinstance(v,dict):
            if 'entity_type' in v and 'entity_id' in v:ref(v['entity_type'],v['entity_id'],p)
            # additionalProperties is public and intentional. Only canonical
            # graph-bearing slots are traversed; arbitrary extension objects
            # do not acquire reserved graph semantics from a coincident key.
            if p=='':descend=set(SETS.values())
            elif re.fullmatch(r'/(?:claims|actions|matters)/\d+',p):descend={'conditions','date_fields','entity_refs'}
            elif re.fullmatch(r'/documents/\d+',p):descend={'date_fields'}
            elif re.fullmatch(r'/carriers/\d+',p):descend={'citations'}
            elif re.fullmatch(r'/relations/\d+',p):descend={'from','to'}
            elif re.fullmatch(r'/unknowns/\d+',p):descend={'entity_refs'}
            else:descend=set()
            top=re.fullmatch(r'/([a-z_]+)/\d+',p)
            main_fields={'carriers':{'parent_carrier_ids'},'documents':{'carrier_ids','identity_or_version_citation_ids'},'matters':{'document_ids','claim_ids'},'claims':{'citation_ids'},'actions':{'matter_id','citation_ids','prerequisite_claim_or_action_ids','exclusion_claim_or_action_ids'},'relations':{'claim_ids','citation_ids'}}
            fields=main_fields.get(top.group(1),set()) if top else {'citation_ids'} if re.fullmatch(r'/(?:documents|actions|claims|matters)/\d+/(?:date_fields|conditions)/\d+',p) else {'supports_claim_ids'} if re.fullmatch(r'/carriers/\d+/citations/\d+',p) else set()
            for k,x in v.items():
                if k not in fields:
                    if k in descend:visit(x,p+'/'+k)
                    continue
                if k in ('citation_ids','identity_or_version_citation_ids') and isinstance(x,list):
                    for cid in x:
                        if cid not in citations:error(p+'/'+k,'unresolved_CID:'+str(cid))
                elif k=='supports_claim_ids' and isinstance(x,list):
                    for ident in x:ref('claim',ident,p+'/'+k)
                elif k in ('carrier_ids','parent_carrier_ids','document_ids','claim_ids') and isinstance(x,list):
                    kind={'carrier_ids':'carrier','parent_carrier_ids':'carrier','document_ids':'document','claim_ids':'claim'}[k]
                    for ident in x:ref(kind,ident,p+'/'+k)
                elif k=='matter_id' and p.startswith('/actions/'):ref('matter',x,p+'/'+k)
                elif k in ('prerequisite_claim_or_action_ids','exclusion_claim_or_action_ids') and isinstance(x,list):
                    for ident in x:
                        if ident not in indexes['claim'] and ident not in indexes['action']:error(p+'/'+k,'unresolved_claim_or_action:'+str(ident))
                if k in descend:visit(x,p+'/'+k)
        elif isinstance(v,list):
            for i,x in enumerate(v):visit(x,p+'/'+str(i))
    visit(data)
    return {'passed':not errors,'errors':errors,'indexes':indexes,'citations':citations,'targets':pointers}

def compact(value):return re.sub(r'\s+','',value or '')
def url_allowed(url,entries):
    allowed=set(entries['allowed_discovery_domains']);identity={urlsplit(x['url']).path for x in entries['identity_only_pages']}
    try:
        v=urlsplit(url);port=v.port;host=(v.hostname or '').rstrip('.')
        return v.scheme in ('https','http') and not v.username and not v.password and host in allowed and (host!='www.hbu.edu.cn' or unquote(v.path) in identity)
    except (ValueError,TypeError):return False
def iso_shape(value,precision):
    if value is None:return True
    if not isinstance(value,str):return False
    shapes={'year':r'\d{4}','month':r'\d{4}-\d{2}','date':r'\d{4}-\d{2}-\d{2}','minute':r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?','second':r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?'}
    if precision in ('range','mixed'):
        return any(iso_shape(value,k) for k in shapes) or iso_shape(value,'daily_recurrence')
    if precision=='daily_recurrence':
        m=re.fullmatch(r'(\d{2}):(\d{2})(?::(\d{2}))?',value)
        return bool(m and int(m.group(1))<24 and int(m.group(2))<60 and int(m.group(3) or 0)<60)
    if precision=='unknown':return value is None
    if precision not in shapes:return False
    if not re.fullmatch(shapes[precision],value):return False
    try:
        if precision=='year':return 1<=int(value)<=9999
        if precision=='month':date.fromisoformat(value+'-01')
        else:datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:return False
    return True
def calendar_value(value,zone):
    if not isinstance(value,str) or 'T' not in value:return value
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:return value
    known={'Asia/Shanghai':timezone(timedelta(hours=8)),'UTC':timezone.utc,'GMT':timezone.utc}
    if zone in known:return parsed.astimezone(known[zone]).isoformat()
    if zone is not None:raise ContractError('NEEDS_DATE_REVIEW: legal timezone conversion outside bounded calendar subset')
    return value
def raw_atoms_match(d):
    raw=compact(d.get('raw_text'));precision=d.get('precision')
    starts=[x for x in (d.get('normalized_start'),d.get('normalized_end')) if x is not None]
    if not starts:return precision=='unknown' or bool(raw)
    if not raw:return False
    # Validate only visible year/month/day/time atoms. Context may supply an absent year.
    explicit_years=re.findall(r'(?<!\d)(\d{4})(?:年|[-/.]|(?!\d))',raw)
    mds=[(int(m),int(day)) for m,day in re.findall(r'(\d{1,2})月(\d{1,2})日?',raw)]
    mds += [(int(m),int(day)) for _,m,day in re.findall(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',raw)]
    months=[int(m) for m in re.findall(r'(\d{1,2})月',raw)]
    months += [int(m) for m in re.findall(r'\d{4}[-/.](\d{1,2})(?:[-/.]\d{1,2})?',raw)]
    inherited_month=None
    for match in re.finditer(r'(?:(\d{1,2})月)?(\d{1,2})日',raw):
        if match.group(1):inherited_month=int(match.group(1))
        if inherited_month is not None:mds.append((inherited_month,int(match.group(2))))
    time_raw=re.sub(r'\s*([:：])\s*',r'\1',d.get('raw_text') or '')
    times=[(int(h),int(m),int(s or 0)) for h,m,s in re.findall(r'(?<!\d)(\d{1,2})[:：](\d{2})(?:[:：](\d{2}))?',time_raw)]
    times += [(int(h),int(m or 0),0) for h,m in re.findall(r'(\d{1,2})[时点](?:(\d{1,2})分?)?',raw)]
    for v in starts:
        if not iso_shape(v,precision):return False
        observed=calendar_value(v,d.get('timezone'))
        if explicit_years and observed[:4] not in explicit_years:return False
        if re.match(r'^\d{4}-\d{2}',observed) and months and int(observed[5:7]) not in months:return False
        if re.match(r'^\d{4}-\d{2}-\d{2}',observed) and not mds:
            if re.search(r'\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|[一二三四五六七八九十〇零两]+月',raw,re.I):raise ContractError('NEEDS_DATE_REVIEW: legal raw calendar notation outside bounded numeric subset')
            return False
        if re.match(r'^\d{4}-\d{2}-\d{2}',observed) and mds and (int(observed[5:7]),int(observed[8:10])) not in mds:return False
        if 'T' in v:
            match=re.match(r'(\d{2}):(\d{2})(?::(\d{2}))?',observed.split('T',1)[1]);h,m,s=(int(x or 0) for x in match.groups())
            if (h,m,s) not in times:return False
            if precision=='second' and not re.search(r'\d{1,2}[:：]\d{2}[:：]\d{2}|\d+秒',time_raw):return False
        elif precision=='daily_recurrence':
            t=tuple(int(x) for x in v.split(':'));t=t+(0,)*(3-len(t))
            if t not in times:return False
        if precision=='date' and 'T' in v:return False
    return True

def date_scope_checks(data,entries,window,graph):
    groups={'precision_and_raw':[],'date_roles_and_publication_window':[],'personal_unknown':[],'URL_scope':[],'date_evidence_binding':[]};errors=[];dates=[]
    def add(group,path,passed,detail):
        groups[group].append(bool(passed))
        if not passed:errors.append({'path':path,'rule':detail,'group':group})
    for i,s in enumerate(data.get('carriers',[])):
        if not isinstance(s,dict):continue
        for field in ('url','final_url'):
            u=s.get(field)
            if u is None:continue
            valid=url_allowed(u,entries)
            add('URL_scope',f'/carriers/{i}/{field}',valid,'outside_public_URL_scope')
    for seq in ('documents','actions'):
        for i,row in enumerate(data.get(seq,[])):
            if not isinstance(row,dict):continue
            publication=[]
            if seq=='actions':add('personal_unknown',f'/{seq}/{i}/personal_status',row.get('personal_status')=='unknown','fabricated_personal_status')
            for j,d in enumerate(row.get('date_fields',[])):
                if not isinstance(d,dict):continue
                p=f'/{seq}/{i}/date_fields/{j}';dates.append({'path':p,'date':d})
                precision=d.get('precision');start=d.get('normalized_start');end=d.get('normalized_end');raw=d.get('raw_text');role=d.get('role')
                valid=raw_atoms_match(d)
                if start and end and precision!='daily_recurrence':
                    if re.match(r'^\d{4}-\d{2}-\d{2}',start) and re.match(r'^\d{4}-\d{2}-\d{2}',end):
                        # Mixed day/time precision does not invent an end-of-day clock.
                        if 'T' not in start or 'T' not in end:valid=valid and end[:10]>=start[:10]
                        else:
                            try:
                                a=datetime.fromisoformat(start.replace('Z','+00:00'));b=datetime.fromisoformat(end.replace('Z','+00:00'))
                                if (a.tzinfo is None)==(b.tzinfo is None):valid=valid and b>=a
                            except ValueError:valid=False
                    elif len(start)==len(end):valid=valid and end>=start
                if d.get('timezone_basis')=='unknown' and d.get('timezone') is not None:valid=False
                if d.get('timezone_basis')=='source_explicit' and not re.search(r'UTC|GMT|北京时间|东八区|[+]0?8(?::?00)?|Z\b',str(raw),re.I):
                    # A timezone may be documented by another cited source; leave that semantic question to Judge.
                    pass
                add('precision_and_raw',p,valid,'raw_normalized_atoms_or_precision_mismatch')
                roles={'webpage_publication','body_signoff','attachment_version','source_access','other','unknown'} if seq=='documents' else {'action_opens','action_deadline','action_window','system_unavailable','other','unknown'}
                add('date_roles_and_publication_window',p,role in roles,'date_role_wrong_entity')
                if role=='webpage_publication' and start:
                    try:publication.append(calendar_value(start,window['timezone'])[:10])
                    except ValueError:publication.append('invalid')
                cids=d.get('citation_ids',[]);bound=bool(cids) if raw is not None else True;quotes=[]
                for cid in cids:
                    item=graph['citations'].get(cid)
                    if item is None:bound=False;continue
                    c=item[1]
                    quotes.append(c.get('quote',''))
                    if not any(p==t or p.startswith(t+'/') or t.startswith(p+'/') or f'/{seq}/{i}'==t for t in c.get('supports_fields',[])):bound=False
                if raw:
                    # Short quotes may jointly support a date object. Preserve each original;
                    # compare visible numeric atoms, not punctuation spelling of a range.
                    rq=compact(raw);cq=compact(' '.join(quotes))
                    if rq not in cq:
                        atoms=re.findall(r'\d+(?:[:：]\d+)*',rq)
                        quote_atoms=re.findall(r'\d+(?:[:：]\d+)*',cq)
                        bound=bound and bool(atoms) and all(x in quote_atoms for x in atoms)
                add('date_evidence_binding',p,bound,'date_raw_atoms_or_target_not_bound_to_declared_CID')
            if seq=='documents':
                state=row.get('publication_window_status');kind=row.get('document_kind')
                if kind=='attachment':valid=state=='not_a_notice'
                elif not publication:valid=state=='unknown'
                elif any(len(x)!=10 for x in publication):valid=state=='unknown'
                else:
                    ins=[window['start_inclusive'][:10]<=x<window['end_exclusive'][:10] for x in publication]
                    valid=state==('in_window' if all(ins) else 'out_of_window' if not any(ins) else 'unknown')
                add('date_roles_and_publication_window',f'/{seq}/{i}',valid,'window_not_bound_to_webpage_publication')
    return {'groups':{k:bool(v) and all(v) for k,v in groups.items()},'errors':errors,'dates':dates,'semantic_role_precision_scope_limits':'Literal atoms and entity role mechanics only. Actual source date role, applicability, identity and latest effective version require independent Judge.'}
