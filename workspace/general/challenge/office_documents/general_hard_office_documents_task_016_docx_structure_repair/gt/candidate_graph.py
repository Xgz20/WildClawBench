"""Native structural observations, with semantic owner nodes and independent numbering state."""
from pathlib import Path
from collections import defaultdict
import hashlib,io,json,re,zipfile
import xml.etree.ElementTree as E
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R='{http://schemas.openxmlformats.org/package/2006/relationships}'
class GraphError(ValueError):pass
def integer(value,label):
    try:return int(value)
    except (ValueError,TypeError) as e:raise GraphError('invalid integer '+label) from e
def canon(s):return re.sub(r'\s+','',s or '')
def _v(node,tag,default=None):
    n=node.find(W+tag) if node is not None else None
    return n.get(W+'val',default) if n is not None else default
def _properties(p):
    out={}
    if p is None:return out
    val=_v(p,'outlineLvl')
    if val is not None:out['outline']=integer(val,'outline')
    np=p.find(W+'numPr')
    if np is not None:
        v=_v(np,'numId');l=_v(np,'ilvl')
        if v is not None:out['num_id']=v
        if l is not None:out['num_level']=integer(l,'num level')
    return out
def read_graph(path,public_ids=None):
    path=Path(path)
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>5000 or sum(i.file_size for i in z.infolist())>100_000_000:raise GraphError('unsafe Word package size or duplicate parts')
        def xml(name):
            try:raw=z.read(name)
            except KeyError as e:raise GraphError('missing required Word part '+name) from e
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise GraphError('XML entities unsupported')
            try:return E.fromstring(raw)
            except E.ParseError as e:raise GraphError('invalid XML '+name) from e
        doc=xml('word/document.xml');styles_root=xml('word/styles.xml') if 'word/styles.xml' in names else E.Element(W+'styles');num_root=xml('word/numbering.xml') if 'word/numbering.xml' in names else E.Element(W+'numbering')
        if sum(1 for _ in doc.iter())>400000:raise GraphError('Word node limit')
        styles={n.get(W+'styleId'):{'base':_v(n,'basedOn'),'type':n.get(W+'type'),'properties':_properties(n.find(W+'pPr')),'name':_v(n,'name')} for n in styles_root.findall(W+'style')}
        if len(styles)!=len(styles_root.findall(W+'style')):raise GraphError('duplicate style id')
        style_nodes={n.get(W+'styleId'):n for n in styles_root.findall(W+'style')}
        def run_props(pr):
            if pr is None:return {}
            out={}
            for key in ['vanish','webHidden']:
                x=pr.find(W+key)
                if x is not None:out[key]=x.get(W+'val','1').casefold() not in {'0','false','off'}
            for key in ['color','sz']:
                x=pr.find(W+key)
                if x is not None:out[key]=x.get(W+'val')
            return out
        defaults=run_props(styles_root.find(W+'docDefaults/'+W+'rPrDefault/'+W+'rPr'))
        def style_run(s,seen=()):
            if s in seen:raise GraphError('cyclic run style')
            n=style_nodes.get(s)
            if n is None:return {}
            base=_v(n,'basedOn')
            return {**(style_run(base,seen+(s,)) if base else {}),**run_props(n.find(W+'rPr'))}
        def style(s,seen=()):
            if s in seen:raise GraphError('cyclic style inheritance')
            row=styles.get(s,{})
            return {**(style(row['base'],seen+(s,)) if row.get('base') else {}),**row.get('properties',{})}
        abstracts={}
        def level(n):return {'start':integer(_v(n,'start','1'),'level start'),'format':_v(n,'numFmt','decimal'),'text':_v(n,'lvlText','%1'),'restart':integer(_v(n,'lvlRestart'),'level restart') if _v(n,'lvlRestart') is not None else None}
        for n in num_root.findall(W+'abstractNum'):
            key=n.get(W+'abstractNumId')
            if key in abstracts:raise GraphError('duplicate abstract numbering id')
            abstracts[key]={integer(x.get(W+'ilvl'),'level id'):level(x) for x in n.findall(W+'lvl')}
        nums={}
        for n in num_root.findall(W+'num'):
            levels={k:dict(v) for k,v in abstracts.get(_v(n,'abstractNumId'),{}).items()}
            for override in n.findall(W+'lvlOverride'):
                i=integer(override.get(W+'ilvl'),'override level');full=override.find(W+'lvl')
                if full is not None:levels[i]=level(full)
                start=_v(override,'startOverride')
                if start is not None:levels.setdefault(i,{'format':'decimal','text':'%1','restart':None})['start']=integer(start,'start override')
            if n.get(W+'numId') in nums:raise GraphError('duplicate numbering id')
            nums[n.get(W+'numId')]={'abstract_id':_v(n,'abstractNumId'),'levels':levels}
        body=doc.find(W+'body')
        if body is None:raise GraphError('missing Word body')
        parent={c:p for p in body.iter() for c in p};p_records=[];bookmarks={};bookmark_end={};bookmark_end_paragraph={};fields=[];stack=[];text_tokens=[];links=[];comment_ranges={};comment_refs=[];sequence=0;comment_markers=defaultdict(lambda:{'start':[],'end':[]});bookmark_ids=set()
        public=set(public_ids) if public_ids is not None else None
        is_public=lambda name:name in public if public is not None else bool(re.fullmatch(r'P\d{4}',name or ''))
        def ancestor(n,tag):
            cur=parent.get(n)
            while cur is not None:
                if cur.tag==W+tag:return cur
                cur=parent.get(cur)
            return None
        def simple_parent(n):
            cur=parent.get(n)
            while cur is not None:
                if cur.tag==W+'fldSimple':return cur
                cur=parent.get(cur)
            return None
        for number,p in enumerate(body.iter(W+'p'),1):
            ids=[n.get(W+'name') for n in p.iter(W+'bookmarkStart') if is_public(n.get(W+'name'))]
            if len(ids)>1:raise GraphError('ambiguous public paragraph anchor')
            pid=ids[0] if ids else None;pr=p.find(W+'pPr');sid=_v(pr,'pStyle','Normal');sp=style(sid);props={**sp,**_properties(pr)}
            rec={'id':pid,'ordinal':number,'style_id':sid,'style_type':styles.get(sid,{}).get('type'),'style_outline':sp.get('outline'),'effective_outline':props.get('outline'),'num_id':props.get('num_id'),'num_level':props.get('num_level',0),'text':'','static_text':'','in_table':ancestor(p,'tbl') is not None,'toc':any(f['instruction'].strip().upper().startswith('TOC') for f in stack)}
            rec['visibility_risks']=[]
            outer=ancestor(p,'fldSimple')
            if outer is not None and outer.get(W+'instr','').strip().upper().startswith('TOC'):rec['toc']=True
            for n in p.iter():
                sequence+=1
                if n.tag==W+'bookmarkStart':
                    name=n.get(W+'name')
                    if name in bookmarks:raise GraphError('duplicate bookmark name')
                    if n.get(W+'id') in bookmark_ids:raise GraphError('duplicate bookmark id')
                    bookmark_ids.add(n.get(W+'id'))
                    bookmarks[name]={'id':n.get(W+'id'),'paragraph':pid,'start':sequence,'start_offset':len(rec['text'])}
                elif n.tag==W+'bookmarkEnd':
                    if n.get(W+'id') in bookmark_end:raise GraphError('duplicate bookmark end')
                    bookmark_end[n.get(W+'id')]=sequence
                    bookmark_end_paragraph[n.get(W+'id')]=pid
                elif n.tag==W+'fldChar':
                    kind=n.get(W+'fldCharType')
                    if kind=='begin':stack.append({'instruction':'','cache':'','paragraph':pid,'paragraph_ordinal':number,'start':sequence,'separate':False,'toc_parent_start':next((q['start'] for q in stack if q['instruction'].strip().upper().startswith('TOC')),None)})
                    elif kind=='separate':
                        if not stack:raise GraphError('unbalanced field separator')
                        stack[-1]['separate']=True
                    elif kind=='end':
                        if not stack:raise GraphError('unbalanced field end')
                        f=stack.pop();f['end']=sequence;fields.append(f)
                elif n.tag==W+'instrText':
                    if not stack:raise GraphError('field instruction outside field')
                    stack[-1]['instruction']+=n.text or ''
                elif n.tag==W+'fldSimple':
                    fields.append({'instruction':n.get(W+'instr',''),'cache':''.join(t.text or '' for t in n.iter(W+'t')),'paragraph':pid,'paragraph_ordinal':number,'start':sequence,'end':sequence+sum(1 for _ in n.iter())-1,'separate':True,'simple':True,'toc_parent_start':next((q['start'] for q in stack if q['instruction'].strip().upper().startswith('TOC')),None)})
                    if n.get(W+'instr','').strip().upper().startswith('TOC'):rec['toc']=True
                elif n.tag in {W+'t',W+'tab',W+'br'}:
                    value=n.text or '' if n.tag==W+'t' else '\t' if n.tag==W+'tab' else '\n'
                    if value.strip():
                        run=ancestor(n,'r');rp=run.find(W+'rPr') if run is not None else None;rs=_v(rp,'rStyle')
                        visible={**defaults,**style_run(sid),**style_run(rs),**run_props(rp)}
                        shading=p.find(W+'pPr/'+W+'shd');cell=ancestor(n,'tc')
                        if shading is None and cell is not None:shading=cell.find(W+'tcPr/'+W+'shd')
                        fill=shading.get(W+'fill','auto').upper() if shading is not None else 'AUTO'
                        white_on_blank=str(visible.get('color','')).upper()=='FFFFFF' and fill in {'AUTO','FFFFFF','NIL'}
                        if visible.get('vanish') or visible.get('webHidden') or white_on_blank or integer(visible.get('sz','22'),'font size')<12:rec['visibility_risks'].append(value)
                    rec['text']+=value;text_tokens.append((sequence,value,pid))
                    if not stack and simple_parent(n) is None:rec['static_text']+=value
                    for f in stack:
                        if f['separate']:f['cache']+=value
                    if any(f['instruction'].strip().upper().startswith('TOC') for f in stack):rec['toc']=True
                elif n.tag==W+'hyperlink':
                    links.append({'anchor':n.get(W+'anchor'),'text':''.join(x.text or '' for x in n.iter(W+'t')),'paragraph':pid,'toc':any(f['instruction'].strip().upper().startswith('TOC') for f in stack)})
                elif n.tag==W+'commentRangeStart':
                    point={'paragraph':pid,'offset':len(rec['text'])};comment_ranges.setdefault(n.get(W+'id'),{})['start']=point;comment_markers[n.get(W+'id')]['start'].append(point)
                elif n.tag==W+'commentRangeEnd':
                    point={'paragraph':pid,'offset':len(rec['text'])};comment_ranges.setdefault(n.get(W+'id'),{})['end']=point;comment_markers[n.get(W+'id')]['end'].append(point)
                elif n.tag==W+'commentReference':comment_refs.append({'id':n.get(W+'id'),'paragraph':pid,'offset':len(rec['text'])})
            p_records.append(rec)
        if stack:raise GraphError('unclosed complex field')
        for b in bookmarks.values():
            b['end']=bookmark_end.get(b['id']);b['range_text']=''.join(text for at,text,_ in text_tokens if b['end'] is not None and b['start']<at<b['end'])
            b['end_paragraph']=bookmark_end_paragraph.get(b['id'])
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
                if len(f['tokens'])<2 or f['tokens'][1].startswith('\\'):raise GraphError('missing SEQ identifier')
                name=f['tokens'][1].casefold();tokens=f['tokens']
                reset=next((tokens[i+1] for i,t in enumerate(tokens[:-1]) if t.casefold()=='\\r'),None)
                if reset is not None:seq[name]=integer(reset,'SEQ reset')
                elif '\\c' not in [t.casefold() for t in tokens]:seq[name]+=1
                f['sequence_name']=name;f['computed']=str(seq[name])
        p_by_id={p['id']:p for p in p_records if p['id']};tables=[];body_order=[];last_p=None
        def block_nodes(container):
            for node in container:
                if node.tag in {W+'p',W+'tbl'}:yield node
                elif node.tag==W+'sdt':
                    content=node.find(W+'sdtContent')
                    if content is not None:yield from block_nodes(content)
                elif node.tag in {W+'customXml',W+'ins',W+'del'}:yield from block_nodes(node)
        for node in block_nodes(body):
            if node.tag==W+'p':
                ids=[n.get(W+'name') for n in node.iter(W+'bookmarkStart') if is_public(n.get(W+'name'))]
                if ids:body_order.append(ids[0]);last_p=ids[0]
            elif node.tag==W+'tbl':
                pr=node.find(W+'tblPr');tid=_v(pr,'tblCaption');rows=[];previous={};invalid_merges=[]
                for ri,row in enumerate(node.findall(W+'tr')):
                    values=['']*integer(_v(row.find(W+'trPr'),'gridBefore','0'),'grid before');current={};col=len(values)
                    for cell in row.findall(W+'tc'):
                        cp=cell.find(W+'tcPr');span=integer(_v(cp,'gridSpan','1'),'cell span')
                        if not 1<=span<=100:raise GraphError('cell span limit')
                        text=''.join(t.text or '' for t in cell.iter(W+'t'));merge=cp.find(W+'vMerge') if cp is not None else None
                        if merge is not None and merge.get(W+'val','continue')!='restart':
                            prior=previous.get(col)
                            if prior is None or text not in {'',prior}:invalid_merges.append([ri,col])
                            text=prior if prior is not None else text
                        for j in range(span):values.append(text);current[col+j]=text
                        col+=span
                    rows.append(values);previous=current
                owned=[f for f in fields if f['paragraph']==last_p and f['kind']=='SEQ'];tables.append({'id':tid,'title':_v(pr,'tblDescription'),'rows':rows,'caption_paragraph':last_p,'sequence_fields':owned,'invalid_merges':invalid_merges})
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
            seen_comments=set();resolved={}
            if 'word/commentsExtended.xml' in names:
                for n in xml('word/commentsExtended.xml'):
                    attrs={k.rsplit('}',1)[-1]:v for k,v in n.attrib.items()}
                    resolved[attrs.get('paraId')]=attrs.get('done','0').casefold() in {'1','true','on'}
            for c in xml('word/comments.xml').findall(W+'comment'):
                cid=c.get(W+'id');rng=comment_ranges.get(cid,{});start=rng.get('start');end=rng.get('end');text='\n'.join(''.join(t.text or '' for t in p.iter(W+'t')) for p in c.findall(W+'p'))
                if cid in seen_comments:raise GraphError('duplicate comment id')
                seen_comments.add(cid)
                anchored=None
                if start and end and start['paragraph']==end['paragraph']:
                    p=p_by_id.get(start['paragraph']);anchored=p['text'][start['offset']:end['offset']] if p else None
                comments.append({'id':cid,'author':c.get(W+'author'),'initials':c.get(W+'initials'),'date':c.get(W+'date'),'text':text,'done':c.get(W+'done','0') in {'1','true'},'range':rng,'anchor_text':anchored,'references':[r for r in comment_refs if r['id']==cid],'markers':comment_markers.get(cid,{'start':[],'end':[]})})
                comments[-1]['done']=comments[-1]['done'] or any(resolved.get(v,False) for n in c.iter(W+'p') for k,v in n.attrib.items() if k.endswith('}paraId'))
        for f in fields:
            if f['kind']=='HYPERLINK' and f['toc_parent_start'] is not None:
                target=next((f['tokens'][i+1].strip('"') for i,t in enumerate(f['tokens'][:-1]) if t.casefold()=='\\l'),None)
                if target:links.append({'anchor':target,'text':f['cache'],'paragraph':f['paragraph'],'toc':True,'native_field':True})
        pending=sum(1 for n in body.iter() if n.tag in {W+'ins',W+'del',W+'moveFrom',W+'moveTo',W+'pPrChange',W+'rPrChange'})
        return {'schema_version':'h016-candidate-graph/v1','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'paragraphs':p_records,'styles':styles,'numbering':nums,'bookmarks':bookmarks,'fields':fields,'tables':tables,'comments':comments,'comment_relationships':comment_relationships,'hyperlinks':links,'body_order':body_order,'pending_revisions':pending}
