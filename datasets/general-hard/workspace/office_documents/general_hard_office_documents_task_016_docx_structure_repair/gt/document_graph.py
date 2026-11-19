"""Native structural observations, with semantic owner nodes and independent numbering state."""
from pathlib import Path
from collections import defaultdict
import hashlib,io,json,re,zipfile
import xml.etree.ElementTree as E
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R='{http://schemas.openxmlformats.org/package/2006/relationships}'
def canon(s):return re.sub(r'\s+','',s or '')
def _v(node,tag,default=None):
    n=node.find(W+tag) if node is not None else None
    return n.get(W+'val',default) if n is not None else default
def _properties(p):
    out={}
    if p is None:return out
    val=_v(p,'outlineLvl')
    if val is not None:out['outline']=int(val)
    np=p.find(W+'numPr')
    if np is not None:
        v=_v(np,'numId');l=_v(np,'ilvl')
        if v is not None:out['num_id']=v
        if l is not None:out['num_level']=int(l)
    return out
def read_graph(path):
    path=Path(path)
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>5000 or sum(i.file_size for i in z.infolist())>100_000_000:raise ValueError('unsafe Word package size or duplicate parts')
        def xml(name):
            raw=z.read(name)
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('XML entities unsupported')
            return E.fromstring(raw)
        doc=xml('word/document.xml');styles_root=xml('word/styles.xml');num_root=xml('word/numbering.xml')
        styles={n.get(W+'styleId'):{'base':_v(n,'basedOn'),'type':n.get(W+'type'),'properties':_properties(n.find(W+'pPr')),'name':_v(n,'name')} for n in styles_root.findall(W+'style')}
        def style(s,seen=()):
            if s in seen:raise ValueError('cyclic style inheritance')
            row=styles.get(s,{})
            return {**(style(row['base'],seen+(s,)) if row.get('base') else {}),**row.get('properties',{})}
        abstracts={}
        def level(n):return {'start':int(_v(n,'start','1')),'format':_v(n,'numFmt','decimal'),'text':_v(n,'lvlText','%1'),'restart':int(_v(n,'lvlRestart')) if _v(n,'lvlRestart') is not None else None}
        for n in num_root.findall(W+'abstractNum'):abstracts[n.get(W+'abstractNumId')]={int(x.get(W+'ilvl')):level(x) for x in n.findall(W+'lvl')}
        nums={}
        for n in num_root.findall(W+'num'):
            levels={k:dict(v) for k,v in abstracts.get(_v(n,'abstractNumId'),{}).items()}
            for override in n.findall(W+'lvlOverride'):
                i=int(override.get(W+'ilvl'));full=override.find(W+'lvl')
                if full is not None:levels[i]=level(full)
                start=_v(override,'startOverride')
                if start is not None:levels.setdefault(i,{'format':'decimal','text':'%1','restart':None})['start']=int(start)
            nums[n.get(W+'numId')]={'abstract_id':_v(n,'abstractNumId'),'levels':levels}
        body=doc.find(W+'body');parent={c:p for p in body.iter() for c in p};p_records=[];bookmarks={};bookmark_end={};fields=[];stack=[];text_tokens=[];links=[];comment_ranges={};comment_refs=[];sequence=0
        def simple_parent(n):
            cur=parent.get(n)
            while cur is not None:
                if cur.tag==W+'fldSimple':return cur
                if cur.tag==W+'p':break
                cur=parent.get(cur)
            return None
        for number,p in enumerate(body.iter(W+'p'),1):
            ids=[n.get(W+'name') for n in p.iter(W+'bookmarkStart') if re.fullmatch(r'P\d{4}',n.get(W+'name',''))]
            if len(ids)>1:raise ValueError('ambiguous public paragraph anchor')
            pid=ids[0] if ids else None;pr=p.find(W+'pPr');sid=_v(pr,'pStyle','Normal');sp=style(sid);props={**sp,**_properties(pr)}
            rec={'id':pid,'ordinal':number,'style_id':sid,'style_type':styles.get(sid,{}).get('type'),'style_outline':sp.get('outline'),'effective_outline':props.get('outline'),'num_id':props.get('num_id'),'num_level':props.get('num_level',0),'text':'','static_text':'','toc':any(f['instruction'].strip().upper().startswith('TOC') for f in stack)}
            for n in p.iter():
                sequence+=1
                if n.tag==W+'bookmarkStart':
                    name=n.get(W+'name')
                    if name in bookmarks:raise ValueError('duplicate bookmark name')
                    bookmarks[name]={'id':n.get(W+'id'),'paragraph':pid,'start':sequence,'start_offset':len(rec['text'])}
                elif n.tag==W+'bookmarkEnd':bookmark_end[n.get(W+'id')]=sequence
                elif n.tag==W+'fldChar':
                    kind=n.get(W+'fldCharType')
                    if kind=='begin':stack.append({'instruction':'','cache':'','paragraph':pid,'paragraph_ordinal':number,'start':sequence,'separate':False})
                    elif kind=='separate':
                        if not stack:raise ValueError('unbalanced field separator')
                        stack[-1]['separate']=True
                    elif kind=='end':
                        if not stack:raise ValueError('unbalanced field end')
                        f=stack.pop();f['end']=sequence;fields.append(f)
                elif n.tag==W+'instrText':
                    if not stack:raise ValueError('field instruction outside field')
                    stack[-1]['instruction']+=n.text or ''
                elif n.tag==W+'fldSimple':
                    fields.append({'instruction':n.get(W+'instr',''),'cache':''.join(t.text or '' for t in n.iter(W+'t')),'paragraph':pid,'paragraph_ordinal':number,'start':sequence,'end':sequence+sum(1 for _ in n.iter())-1,'separate':True,'simple':True})
                    if n.get(W+'instr','').strip().upper().startswith('TOC'):rec['toc']=True
                elif n.tag in {W+'t',W+'tab',W+'br'}:
                    value=n.text or '' if n.tag==W+'t' else '\t' if n.tag==W+'tab' else '\n'
                    rec['text']+=value;text_tokens.append((sequence,value,pid))
                    if not stack and simple_parent(n) is None:rec['static_text']+=value
                    for f in stack:
                        if f['separate']:f['cache']+=value
                    if any(f['instruction'].strip().upper().startswith('TOC') for f in stack):rec['toc']=True
                elif n.tag==W+'hyperlink':
                    links.append({'anchor':n.get(W+'anchor'),'text':''.join(x.text or '' for x in n.iter(W+'t')),'paragraph':pid,'toc':any(f['instruction'].strip().upper().startswith('TOC') for f in stack)})
                elif n.tag==W+'commentRangeStart':comment_ranges.setdefault(n.get(W+'id'),{})['start']={'paragraph':pid,'offset':len(rec['text'])}
                elif n.tag==W+'commentRangeEnd':comment_ranges.setdefault(n.get(W+'id'),{})['end']={'paragraph':pid,'offset':len(rec['text'])}
                elif n.tag==W+'commentReference':comment_refs.append({'id':n.get(W+'id'),'paragraph':pid,'offset':len(rec['text'])})
            p_records.append(rec)
        if stack:raise ValueError('unclosed complex field')
        for b in bookmarks.values():
            b['end']=bookmark_end.get(b['id']);b['range_text']=''.join(text for at,text,_ in text_tokens if b['end'] is not None and b['start']<at<b['end'])
        states=defaultdict(dict)
        for p in p_records:
            identifier=p['num_id'];level_no=p['num_level'];definition=nums.get(identifier,{}).get('levels',{}).get(level_no)
            if not definition or identifier=='0':p.update(number=None,label=None,num_format=None);continue
            levels=nums[identifier]['levels'];s=states[identifier];s[level_no]=definition.get('start',1) if level_no not in s else s[level_no]+1
            for deeper in list(s):
                if deeper>level_no:
                    restart=levels.get(deeper,{}).get('restart')
                    if restart is None or restart!=0 and level_no==restart-1:del s[deeper]
            label=re.sub(r'%([1-9])',lambda m:str(s.get(int(m[1])-1,0)),definition['text'])
            p.update(number=s[level_no],label=label,num_format=definition['format'])
        for f in sorted(fields,key=lambda x:x['start']):
            tokens=re.findall(r'"[^"]*"|\S+',f['instruction'].strip());f['tokens']=tokens;f['kind']=tokens[0].upper() if tokens else ''
        seq=defaultdict(int)
        for f in sorted(fields,key=lambda x:x['start']):
            if f['kind']=='SEQ':
                name=f['tokens'][1].casefold();tokens=f['tokens']
                reset=next((tokens[i+1] for i,t in enumerate(tokens[:-1]) if t.casefold()=='\\r'),None)
                if reset is not None:seq[name]=int(reset)
                elif '\\c' not in [t.casefold() for t in tokens]:seq[name]+=1
                f['sequence_name']=name;f['computed']=str(seq[name])
        p_by_id={p['id']:p for p in p_records if p['id']};tables=[];body_order=[];last_p=None
        for node in body:
            if node.tag==W+'p':
                ids=[n.get(W+'name') for n in node.iter(W+'bookmarkStart') if re.fullmatch(r'P\d{4}',n.get(W+'name',''))]
                if ids:body_order.append(ids[0]);last_p=ids[0]
            elif node.tag==W+'tbl':
                pr=node.find(W+'tblPr');tid=_v(pr,'tblCaption');rows=[[''.join(t.text or '' for t in c.iter(W+'t')) for c in r.findall(W+'tc')] for r in node.findall(W+'tr')]
                owned=[f for f in fields if f['paragraph']==last_p and f['kind']=='SEQ'];tables.append({'id':tid,'title':_v(pr,'tblDescription'),'rows':rows,'caption_paragraph':last_p,'sequence_fields':owned})
                body_order.append('table:'+str(tid));last_p=None
        for f in fields:
            if f['kind'] in {'REF','PAGEREF'}:
                f['target']=f['tokens'][1] if len(f['tokens'])>1 else None;target=bookmarks.get(f['target']);f['target_exists']=bool(target and target['end'] is not None);f['target_paragraph']=target['paragraph'] if target else None
                if f['kind']=='REF' and target:
                    f['computed']=p_by_id.get(target['paragraph'],{}).get('label') if any(t.casefold() in {'\\n','\\w'} for t in f['tokens']) else target['range_text']
                    contained=[q for q in fields if q['kind']=='SEQ' and target['end'] is not None and target['start']<q['start']<q['end']<target['end']]
                    if not any(t.casefold() in {'\\n','\\w'} for t in f['tokens']) and len(contained)==1 and target['range_text'].strip()==contained[0]['cache'].strip():f['computed']=contained[0]['computed']
                    f['target_sequence_fields']=[q['paragraph'] for q in contained]
                    f['target_table']=next((t['id'] for t in tables if t['caption_paragraph']==target['paragraph']),None)
        comments=[];comment_relationships=[]
        if 'word/_rels/document.xml.rels' in names:
            comment_relationships=[dict(n.attrib) for n in xml('word/_rels/document.xml.rels') if n.get('Type','').endswith('/comments')]
        if 'word/comments.xml' in names:
            for c in xml('word/comments.xml').findall(W+'comment'):
                cid=c.get(W+'id');rng=comment_ranges.get(cid,{});start=rng.get('start');end=rng.get('end');text='\n'.join(''.join(t.text or '' for t in p.iter(W+'t')) for p in c.findall(W+'p'))
                anchored=None
                if start and end and start['paragraph']==end['paragraph']:
                    p=p_by_id.get(start['paragraph']);anchored=p['text'][start['offset']:end['offset']] if p else None
                comments.append({'id':cid,'author':c.get(W+'author'),'initials':c.get(W+'initials'),'date':c.get(W+'date'),'text':text,'done':c.get(W+'done','0') in {'1','true'},'range':rng,'anchor_text':anchored,'references':[r for r in comment_refs if r['id']==cid]})
        return {'schema_version':'h016-native-graph/v1','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'paragraphs':p_records,'styles':styles,'numbering':nums,'bookmarks':bookmarks,'fields':fields,'tables':tables,'comments':comments,'comment_relationships':comment_relationships,'hyperlinks':links,'body_order':body_order}
