"""Standalone H027 readers. Candidate errors score; trusted evidence errors abort.

No network, model calls, repository imports, or writes to a candidate Workspace.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

class CandidateError(ValueError):
    pass

class TrustedEvidenceError(RuntimeError):
    pass

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', '' if value is None else str(value))).casefold()

def textnorm(value):
    value = unicodedata.normalize('NFKC', str(value)).replace('\u00ad', '')
    value = re.sub(r'-\s*\n\s*(?=[a-z])', '', value)
    return re.sub(r'\s+', ' ', value).strip()

def unknown(value):
    if value is None:return True
    v=norm(value)
    return v in {'', 'unknown', 'notstated', 'notreported', 'n/a', 'na', 'null', '未知', '未注明', '未披露', '未说明', '不详', '—', '–'} or bool(re.match(r'^(?:unknown|notstated|notreported|n/a|na)(?:[(:：;；,，]|$)',v)) or any(v.startswith(x) for x in ('未知','未注明','未披露','未说明','不详'))

def number(value):
    if isinstance(value, bool) or unknown(value):
        return None
    try:
        result = float(str(value).replace(',', '').replace('，', '').strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None

def integer(value):
    value = number(value)
    return int(value) if value is not None and value.is_integer() else None

def date(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()[:10]
    value = str(value or '').strip()
    for pattern in ('%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日', '%B %d, %Y', '%b %d, %Y'):
        try:
            return dt.datetime.strptime(value[:10] if pattern == '%Y-%m-%d' else value, pattern).date().isoformat()
        except ValueError:
            pass
    return value

def unit_factor(value):
    u = norm(value).replace('_', '').replace('-', '').replace('当量', '').replace('equivalent', '')
    if 'reo' not in u:
        return None
    if any(s in u for s in ('million', '百万')):
        return 1000000.
    if any(s in u for s in ('万', '10000')):
        return 10000.
    if any(s in u for s in ('thousand', '千')):
        return 1000.
    return 1. if any(s in u for s in ('tonne', 'ton', '吨', 'treo')) else None

def metric(value, contract):
    for key, aliases in contract['metrics'].items():
        if norm(value) in {norm(x) for x in [key] + aliases}:
            return key
    return None

def relation(value):
    v = norm(value)
    return {'约等于':'approximately_equal', '≈':'approximately_equal', '~':'approximately_equal', 'approximatelyequal':'approximately_equal', 'approximately_equal':'approximately_equal', '大于':'>', '小于':'<', '等于':'=', '＞':'>', '＜':'<', '≤':'<=', '≥':'>='}.get(v, v)

def citations(value):
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if value is None:
        return []
    v = str(value).strip()
    if v.startswith('['):
        try:
            return citations(json.loads(v))
        except (ValueError, TypeError):
            pass
    return [x for x in re.split(r'[,;，；|\s]+', v) if x]

def candidate_path(root, relative, limit=5242880):
    p = Path(root) / relative
    if not p.is_file() or p.is_symlink() or Path(root).resolve() not in p.resolve().parents:
        raise CandidateError('missing/unsafe candidate file: ' + relative)
    if p.stat().st_size > limit:
        raise CandidateError('candidate file exceeds delivery limit: ' + relative)
    return p

def read_ledger(path):
    try:
        v = json.loads(Path(path).read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise CandidateError('source ledger is not UTF-8 JSON') from exc
    if not isinstance(v, dict):
        raise CandidateError('source ledger must be an object')
    return v

def _col(cell):
    value = 0
    for char in re.match(r'[A-Z]+', cell).group():
        value = value * 26 + ord(char) - 64
    return value

def read_book(path):
    """Read native cached values and structural visibility, not workbook coordinates."""
    try:
        with zipfile.ZipFile(path) as z:
            def xml(name):
                return ET.fromstring(z.read(name))
            strings=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                strings=[''.join(n.itertext()) for n in xml('xl/sharedStrings.xml').findall(S+'si')]
            styles=[];formats={}
            if 'xl/styles.xml' in z.namelist():
                st=xml('xl/styles.xml')
                formats={int(n.get('numFmtId')):n.get('formatCode','') for n in st.findall(S+'numFmts/'+S+'numFmt')}
                fonts=list(st.find(S+'fonts') or []);fills=list(st.find(S+'fills') or [])
                for x in st.findall(S+'cellXfs/'+S+'xf'):
                    fmtid=int(x.get('numFmtId','0'));fmt=formats.get(fmtid,'')
                    font=fonts[int(x.get('fontId','0'))] if fonts else None
                    size=font.find(S+'sz') if font is not None else None
                    color=font.find(S+'color') if font is not None else None
                    fill=fills[int(x.get('fillId','0'))] if fills else None
                    fg=fill.find(S+'patternFill/'+S+'fgColor') if fill is not None else None
                    invisible=fmt.replace(' ','')==';;;' or size is not None and float(size.get('val','11'))<=0
                    if color is not None and color.get('rgb') and (color.get('rgb','')[-6:].upper()=='FFFFFF' and (fg is None or fg.get('rgb','')[-6:].upper()=='FFFFFF') or fg is not None and fg.get('rgb')==color.get('rgb')):
                        invisible=True
                    isdate=fmtid in set(range(14,23))|set(range(45,48)) or bool(re.search(r'[yd]',re.sub(r'"[^"]*"|\[[^]]*\]','',fmt),re.I))
                    styles.append({'visible':not invisible,'date':isdate})
            rels={n.get('Id'):posixpath.normpath(posixpath.join('xl',n.get('Target','').lstrip('/'))) if not n.get('Target','').startswith('/') else n.get('Target').lstrip('/') for n in xml('xl/_rels/workbook.xml.rels')}
            result=[]
            wb=xml('xl/workbook.xml')
            date1904=wb.find(S+'workbookPr') is not None and wb.find(S+'workbookPr').get('date1904') in {'1','true'}
            for sheet in wb.findall(S+'sheets/'+S+'sheet'):
                tree=xml(rels[sheet.get(R+'id')]);cells={}
                hidden_cols=set()
                for c in tree.findall(S+'cols/'+S+'col'):
                    if c.get('hidden') in {'1','true'} or c.get('width')=='0':
                        hidden_cols.update(range(int(c.get('min')),int(c.get('max'))+1))
                for row in tree.findall(S+'sheetData/'+S+'row'):
                    rowvisible=row.get('hidden') not in {'1','true'} and row.get('ht')!='0'
                    for c in row.findall(S+'c'):
                        address=c.get('r');col=_col(address);rownum=int(re.search(r'\d+',address).group())
                        v=c.find(S+'v');value=v.text if v is not None else None
                        typ=c.get('t');style=styles[int(c.get('s','0'))] if styles else {'visible':True,'date':False}
                        if typ=='inlineStr':value=''.join(c.find(S+'is').itertext()) if c.find(S+'is') is not None else ''
                        elif typ=='s':value=strings[int(value)]
                        elif typ=='b':value=value=='1'
                        elif typ=='d':value=dt.datetime.fromisoformat(value.replace('Z','+00:00')) if value else None
                        elif typ not in {'str','e'} and value is not None:
                            value=float(value);value=int(value) if value.is_integer() else value
                            if style['date']:
                                value=(dt.datetime(1904,1,1) if date1904 else dt.datetime(1899,12,30))+dt.timedelta(days=value)
                        cells[(rownum,col)]={'value':value,'visible':sheet.get('state','visible')=='visible' and rowvisible and col not in hidden_cols and style['visible'],'formula':c.find(S+'f') is not None,'address':address}
                result.append({'name':sheet.get('name'),'cells':cells,'state':sheet.get('state','visible')})
            return result
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, TypeError, IndexError, AttributeError) as exc:
        raise CandidateError('invalid native XLSX package: '+str(exc)) from exc

def extract_tables(book, contract):
    aliases={norm(alias):key for key,values in contract['aliases'].items() for alias in [key]+values}
    tables={key:[] for key in contract['xlsx_tables']};headers={key:[] for key in tables}
    for sheet in book:
        rows={r for r,c in sheet['cells']}
        found=[]
        for r in sorted(rows):
            cells={c:aliases.get(norm(o['value'])) for (rr,c),o in sheet['cells'].items() if rr==r}
            for name,fields in contract['xlsx_tables'].items():
                if not set(fields)<=set(cells.values()):continue
                anchor={'versions':'version','rankings':'rank','shares':'share_value','revisions':'delta'}[name]
                for a in [c for c,k in cells.items() if k==anchor]:
                    mapping={key:min((c for c,k in cells.items() if k==key),key=lambda c:abs(c-a)) for key in fields}
                    found.append((r,name,mapping))
                    headers[name].append({'sheet':sheet['name'],'row':r,'visible':all(sheet['cells'][(r,c)]['visible'] for c in mapping.values())})
        for r,name,mapping in found:
            end=min([rr for rr,_,_ in found if rr>r]+[max(rows,default=r)+1])
            for rr in range(r+1,end):
                values={k:sheet['cells'].get((rr,c),{}).get('value') for k,c in mapping.items()}
                if not any(v is not None and str(v).strip() for v in values.values()):continue
                identity={'versions':['report_year'],'rankings':['report_year','metric','rank'],'shares':['report_year','metric'],'revisions':['statistical_year','country']}[name]
                if not all(values[k] is not None for k in identity):continue
                if integer(values.get('statistical_year') if name=='revisions' else values.get('report_year')) is None:continue
                values['_visible']=all(sheet['cells'].get((rr,c),{'visible':True})['visible'] for c in mapping.values()) and all(h['visible'] for h in headers[name] if h['sheet']==sheet['name'] and h['row']==r)
                values['_location']={'sheet':sheet['name'],'row':rr}
                tables[name].append(values)
    return tables,headers

def _trusted_path(root, relative):
    if not isinstance(relative,str) or '\\' in relative or PurePosixPath(relative).is_absolute() or any(p in {'','..','.'} for p in relative.split('/')):
        raise TrustedEvidenceError('unsafe research bundle path')
    p=root/relative
    if not p.is_file() or p.is_symlink() or root not in p.resolve().parents:
        raise TrustedEvidenceError('research bundle file missing/unsafe: '+relative)
    return p

def load_bundle(ledger):
    root_env=os.environ.get('GENERAL_E2E_RESEARCH_SOURCE_BUNDLE');digest=os.environ.get('GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256')
    if not root_env or not digest:
        raise TrustedEvidenceError('managed independent research bundle context missing')
    root=Path(root_env).resolve();manifest=_trusted_path(root,'manifest.json')
    if sha(manifest)!=digest:
        raise TrustedEvidenceError('research manifest SHA drift')
    try:m=json.loads(manifest.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError) as exc:raise TrustedEvidenceError('invalid trusted manifest') from exc
    if not isinstance(m.get('sources'),list) or m.get('candidate_input_status') not in {'valid','missing_ledger','invalid_ledger'}:
        raise TrustedEvidenceError('research manifest contract invalid')
    if m.get('errors') and (m['candidate_input_status']=='valid' or m['sources']):
        raise TrustedEvidenceError('research collector reported unresolved errors')
    byid={};ledger_sources=ledger.get('sources',[]) if ledger else []
    if not isinstance(ledger_sources,list):ledger_sources=[]
    ledgermap={s.get('source_id'):s for s in ledger_sources if isinstance(s,dict) and isinstance(s.get('source_id'),str)}
    for source in m['sources']:
        if not isinstance(source,dict) or source.get('status') not in {'acquired','not_requested','candidate_invalid'}:
            raise TrustedEvidenceError('source acquisition status invalid')
        sid=source.get('source_id')
        if not isinstance(sid,str) or sid in byid:raise TrustedEvidenceError('duplicate/missing bundle source ID')
        if ledger is not None and m['candidate_input_status']=='valid':
            ls=ledgermap.get(sid)
            if ls is None or source.get('url')!=ls.get('url') or source.get('citations')!=ls.get('citations'):
                raise TrustedEvidenceError('research bundle / candidate ledger binding drift: '+sid)
        if source['status']=='acquired':
            paths={}
            for part in ('body','text','projection','receipt'):
                path=_trusted_path(root,source.get(part+'_path'));expected=source.get(part+'_sha256')
                if not isinstance(expected,str) or sha(path)!=expected:
                    raise TrustedEvidenceError('research '+part+' SHA drift: '+sid)
                paths[part]=path
            try:
                text=json.loads(paths['projection'].read_text(encoding='utf-8'));receipt=json.loads(paths['receipt'].read_text(encoding='utf-8'))
            except (ValueError,UnicodeError) as exc:raise TrustedEvidenceError('invalid trusted source projection/receipt') from exc
            if text.get('schema_version')!='wildclawbench.research-source-text/v1' or text.get('source_sha256')!=source['body_sha256'] or text.get('complete') is not True or not isinstance(text.get('records'),list) or not text.get('engine'):
                raise TrustedEvidenceError('source extraction incomplete/unbound: '+sid)
            if receipt.get('requested_url')!=source['url'] or receipt.get('final_url')!=source.get('final_url'):
                raise TrustedEvidenceError('source receipt identity drift: '+sid)
            source=dict(source,_text=text,_plain=paths['text'].read_text(encoding='utf-8'),_is_pdf=paths['body'].read_bytes().lstrip().startswith(b'%PDF-'))
        byid[sid]=source
    if ledger is not None and m['candidate_input_status']=='valid':
        policy=m.get('policy',{})
        statuses=policy.get('collect_statuses',['read_full','read_excerpt']) if isinstance(policy,dict) else ['read_full','read_excerpt']
        selected={sid for sid,s in ledgermap.items() if s.get('access_status') in statuses or bool(s.get('citations'))}
        if set(byid)!=selected:raise TrustedEvidenceError('research selected source set binding drift')
    return m,byid

def resolve_citation(source,citation):
    if not source or source['status']!='acquired':return False,'source not independently acquired'
    if not isinstance(citation,dict) or not isinstance(citation.get('quote'),str) or not citation['quote'].strip() or not isinstance(citation.get('locator'),dict):return False,'missing locator/quote'
    locator=citation['locator'];records=source['_text']['records'];media=source.get('media_type','').lower()
    full='\n'.join(str(r.get('text','')) for r in records)
    selected=None
    if 'page' in locator:
        page=integer(locator['page'])
        if page is None or page<1:return False,'invalid PDF page'
        selected='\n'.join(str(r.get('text','')) for r in records if integer(r.get('locator',{}).get('page'))==page)
    elif source.get('_is_pdf') or 'pdf' in media:
        return False,'PDF citation requires actual PDF page'
    elif 'lines' in locator:
        limits=locator['lines'];lines=full.splitlines()
        if not isinstance(limits,list) or len(limits)!=2 or any(integer(v) is None for v in limits):return False,'invalid line locator'
        first,last=map(integer,limits)
        if first<1 or last<first or last>len(lines):return False,'line locator outside source'
        selected='\n'.join(lines[first-1:last])
    elif 'heading' in locator and isinstance(locator['heading'],str) and locator['heading'].strip():
        heading=textnorm(locator['heading']);flat=textnorm(full)
        start=flat.find(heading)
        if start<0:return False,'heading not present in source'
        # Static HTML projection preserves heading text, not a trustworthy DOM tree.
        # Resolve the actual heading plus following source span; section hierarchy
        # and whether the quote supports the business claim remain Judge work.
        selected=flat[start:]
    if not selected:return False,'locator does not resolve to source text'
    quote=textnorm(citation['quote']);selected=textnorm(selected)
    # Whitespace and PDF line-wrap normalization only; no semantic fuzzy matching.
    if quote in selected:return True,'exact normalized quote at locator'
    parts=[x.strip() for x in re.split(r'(?:\.{3}|…+|\[\.\.\.\])',quote) if x.strip()]
    if len(parts)>1:
        offset=0
        for part in parts:
            pos=selected.find(part,offset)
            if pos<0:return False,'quote fragment not at locator'
            offset=pos+len(part)
        return True,'ordered verbatim fragments at locator'
    return False,'quote not at locator'
