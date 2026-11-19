"""Business checks by public paragraph/table identity, never author XML offsets."""
from datetime import datetime
import re

def mean(values):
    values=list(values)
    return sum(values)/len(values) if values else 0.
def canon(text):return re.sub(r'\s+','',text or '')
def date(text):
    try:return datetime.fromisoformat(text.replace('Z','+00:00'))
    except (ValueError,AttributeError):return None

def observe(g,e):
    ps={p['id']:p for p in g['paragraphs'] if p['id']};fs=g['fields'];tables={t['id']:t for t in g['tables']}
    protected=e['protected'];headings={h['paragraph_id']:h for h in e['headings']}
    text_checks={pid:pid in ps and ps[pid]['static_text']==text for pid,text in protected['paragraphs'].items()}
    data_checks={tid:tid in tables and tables[tid]['rows']==rows and not tables[tid]['invalid_merges'] for tid,rows in protected['tables'].items()}
    comments=[]
    for old in protected['comments']:
        matches=[c for c in g['comments'] if all(c[k]==old[k] for k in ['author','text','done','range','anchor_text']) and date(c['date']) is not None and date(c['date'])==date(old['date']) and len(c['references'])==1 and len(c['markers']['start'])==len(c['markers']['end'])==1 and c['references'][0]['paragraph']==old['range']['end']['paragraph']]
        comments.append(len(matches)==1)
    extra=[p for p in g['paragraphs'] if not p['id'] and not p['in_table'] and not p['toc'] and canon(p['text'])]
    # All public nodes must remain top-level prose; moving whole headings to tables is a boundary violation.
    preservation={'paragraphs':all(text_checks.values()),'tables':all(data_checks.values()) and len(g['tables'])==6,
      'order':g['body_order']==protected['body_order'],'comments':all(comments) and len(g['comment_relationships'])==1,
      'no_added_business_prose':not extra,'no_pending_revisions':not g['pending_revisions'],
      'public_nodes_in_body':all(not p['in_table'] for p in ps.values()),'visible_runs':not any(p['visibility_risks'] for p in g['paragraphs'])}
    preservation['public_bookmark_ranges']=all(pid in ps and g['bookmarks'].get(pid,{}).get('end_paragraph')==pid and g['bookmarks'][pid]['end']>g['bookmarks'][pid]['start'] for pid in protected['paragraphs'])
    preservation['native_field_roles']=all(f['kind'] in {'TOC','PAGEREF','SEQ','REF','HYPERLINK'} for f in fs) and all(f['paragraph'] in {t['caption_paragraph'] for t in e['tables']} for f in fs if f['kind']=='SEQ') and all(f['paragraph'] in {r['paragraph'] for r in e['references']} for f in fs if f['kind']=='REF')
    hs={};numbered=[]
    for pid,h in headings.items():
        p=ps.get(pid,{})
        role=p.get('style_type')=='paragraph' and p.get('style_outline')==h['level'] and p.get('effective_outline')==h['level']
        numbering=not p.get('label') if h['appendix'] else p.get('label')==h['label'] and p.get('num_level')==h['level'] and p.get('num_format')=='decimal'
        hs[pid]={'role':bool(role),'numbering':bool(numbering)}
        if not h['appendix']:numbered.append(p.get('num_id'))
    heading_chain=len(set(numbered))==1 and numbered[0] not in {None,'0'}
    steps={s['paragraph_id']:bool(ps.get(s['paragraph_id'],{}).get('number')==s['number'] and ps.get(s['paragraph_id'],{}).get('num_format')=='decimal') for s in e['steps']}
    step_ids={ps.get(s['paragraph_id'],{}).get('num_id') for s in e['steps']};step_chain=len(step_ids)==1 and None not in step_ids and '0' not in step_ids and not step_ids.intersection(numbered)
    caption={}
    for i,t in enumerate(e['tables'],1):
        fields=[f for f in fs if f['paragraph']==t['caption_paragraph'] and f['kind']=='SEQ'];out=tables.get(t['id'],{})
        caption[t['id']]=bool(len(fields)==1 and fields[0].get('sequence_name')=='table' and fields[0].get('computed')==str(i) and '\\r' not in [x.lower() for x in fields[0]['tokens']] and '\\c' not in [x.lower() for x in fields[0]['tokens']] and out.get('caption_paragraph')==t['caption_paragraph'])
    refs={}
    for r in e['references']:
        fields=[f for f in fs if f['paragraph']==r['paragraph'] and f['kind']=='REF']
        refs[r['paragraph']]=bool(len(fields)==1 and fields[0]['target_exists'] and fields[0]['target_paragraph']==r['target_paragraph'] and fields[0].get('computed')==r['computed'] and fields[0].get('target_table')==r['target_table'])
    toc_fields=[f for f in fs if f['kind']=='TOC'];toc_parent=toc_fields[0]['start'] if len(toc_fields)==1 else None
    instruction=toc_fields[0]['instruction'] if toc_fields else ''
    depth=bool(re.search(r'\\o\s+"?1-3"?',instruction,re.I))
    # Equivalent custom-style lists may express all three levels with \\t.
    custom=re.search(r'\\t\s+"([^"]+)"',instruction,re.I)
    if custom:
        tokens=custom[1].split(',');mapped={tokens[i]:tokens[i+1] for i in range(0,len(tokens)-1,2)}
        depth=all(mapped.get(ps.get(pid,{}).get('style_id'))==str(h['level']+1) or mapped.get(g['styles'].get(ps.get(pid,{}).get('style_id'),{}).get('name'))==str(h['level']+1) for pid,h in headings.items())
    links=[l for l in g['hyperlinks'] if l['toc']];page_fields=[f for f in fs if f['kind']=='PAGEREF' and f['toc_parent_start']==toc_parent and toc_parent is not None]
    toc_links={};toc_pages={}
    for pid,h in headings.items():
        want=canon(h['label']+' '+h['title'])
        same=[l for l in links if canon(l['text'])==want]
        toc_links[pid]=len(same)==1 and g['bookmarks'].get(same[0]['anchor'],{}).get('paragraph')==pid and g['bookmarks'].get(same[0]['anchor'],{}).get('end') is not None
        pagerefs=[f for f in page_fields if f['target_paragraph']==pid and f['target_exists']]
        toc_pages[pid]=len(pagerefs)==1
    toc={'native_single':len(toc_fields)==1,'depth_three':depth,'link_checks':toc_links,'page_target_checks':toc_pages,
      'exact_entries':len(links)==26 and len(page_fields)==26}
    scores={'headings':.8*mean(mean(x.values()) for x in hs.values())+.2*heading_chain,
      'steps':.8*mean(steps.values())+.2*step_chain,'captions':mean(caption.values()),'references':mean(refs.values()),
      'toc':.15*toc['native_single']+.15*depth+.3*mean(toc_links.values())+.3*mean(toc_pages.values())+.1*toc['exact_entries']}
    return {'scores':scores,'headings':hs,'heading_chain':heading_chain,'steps':steps,'step_chain':step_chain,'captions':caption,'references':refs,'toc':toc,
      'preservation':preservation,'paragraph_checks':text_checks,'table_checks':data_checks,'comment_checks':comments,'extra_prose':[p['text'] for p in extra]}

def log_checks(log,source,result,e,observations):
    rows=log.get('repairs') if isinstance(log,dict) else None
    if not isinstance(rows,list) or not 1<=len(rows)<=100:return {'score':0.,'coverage':{},'valid_rows':[]}
    def matched(locator,d):
        if not isinstance(locator,str):return False
        pid=d['source_paragraph_id'];target=d['target_key'];want=[]
        if pid:want.append(pid)
        h=next((h for h in e['headings'] if h['key']==target),None)
        if h:want.append(h['title'])
        if target in {'T03','T04','T05'}:want.extend([target,next(t['title'] for t in e['tables'] if t['id']==target)])
        if target=='contents':want.extend(['TOC','目录'])
        if d['kind']=='toc_wrong_existing_anchor':return bool(('TOC' in locator.upper() or '目录' in locator) and any(w in locator for w in want))
        return any(w in locator for w in want)
    valid=[];coverage={}
    def repaired(d):
        pid=d['source_paragraph_id'];kind=d['kind'];o=observations
        if kind.startswith('heading') or kind=='outline_override':return all(o['headings'].get(pid,{}).values()) and o['heading_chain']
        if kind=='procedure_restart':return all(o['steps'].values()) and o['step_chain']
        if kind.startswith('toc'):return abs(o['scores']['toc']-1.)<1e-10
        if kind.startswith('caption'):return all(o['captions'].values())
        if kind=='wrong_existing_reference':return o['references'].get(pid,False)
        if kind=='missing_caption_bookmark':return o['references'].get('P0086',False)
        return False
    for row in rows:
        if not isinstance(row,dict):valid.append(False);continue
        valid.append(bool(str(row.get('source_file','')).split('/')[-1]=='damaged_styles.docx' and str(row.get('result_file','')).split('/')[-1]=='repaired.docx' and isinstance(row.get('action'),str) and len(row['action'].strip())>=8 and isinstance(row.get('preservation'),str) and len(row['preservation'].strip())>=4))
    for d in e['defects']:
        coverage[d['defect_id']]=repaired(d) and any(ok and matched(row.get('source_locator'),d) and matched(row.get('result_locator'),d) for row,ok in zip(rows,valid))
    return {'score':mean(coverage.values())*all(valid),'coverage':coverage,'valid_rows':valid,
      'limit':'Locator existence and actual repaired nodes checked; action accuracy and claimed tool execution require independent Judge.'}
