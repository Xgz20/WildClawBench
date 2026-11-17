"""Offline actual-PDF physical-page evidence; source identities come from frozen data."""
from pathlib import Path,PurePosixPath
import hashlib,json,re,runpy,unicodedata

class TrustedEvidenceError(RuntimeError):pass
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def norm(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value))).strip()
def _json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def safe_source_path(root,relative):
    if not isinstance(relative,str) or not relative or '\\' in relative or PurePosixPath(relative).is_absolute() or any(p in ('','.','..') for p in relative.split('/')):raise TrustedEvidenceError('H032 trusted original relative path invalid')
    root=Path(root).resolve();path=root/relative
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:raise TrustedEvidenceError('H032 trusted original missing/unsafe: '+relative)
    return path
def extract_pdf(path):
    try:import pypdf
    except ImportError as exc:raise TrustedEvidenceError('H032 PDF extractor pypdf missing') from exc
    package=Path(pypdf.__file__).resolve().parent
    package_files={p.relative_to(package).as_posix():sha(p) for p in sorted(package.rglob('*.py')) if p.is_file()}
    engine={'name':'pypdf','version':pypdf.__version__,'module':str(pypdf.__file__),'module_sha256':sha(pypdf.__file__),'package_python_tree_sha256':hashlib.sha256(json.dumps(package_files,sort_keys=True).encode()).hexdigest()}
    try:
        reader=pypdf.PdfReader(str(path));pages=[]
        if reader.is_encrypted:raise TrustedEvidenceError('UNSUPPORTED_PDF_ENCRYPTION')
        for index,page in enumerate(reader.pages,1):
            text=page.extract_text()
            if not isinstance(text,str) or not text.strip():raise TrustedEvidenceError('UNSUPPORTED_PDF_TEXT: physical page not faithfully extractable: '+str(index))
            pages.append({'physical_page':index,'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
        if not pages:raise TrustedEvidenceError('H032 original PDF has no physical pages')
        return {'source_sha256':sha(path),'engine':engine,'pages':pages,'network_used':False,'code_executed':False,'boundary':'Actual physical-page text; no image-pixel, scientific-role or reading-behavior claim'}
    except TrustedEvidenceError:raise
    except Exception as exc:raise TrustedEvidenceError('H032 trusted PDF extraction failed: '+str(exc)) from exc
def load_sources(gt):
    gt=Path(gt);protected=_json(gt/'protected_sha256.json');manifest=_json(gt/'reference_source_manifest.json');root=gt/'source_originals'
    for name,digest in protected.items():
        path=safe_source_path(root,name)
        if sha(path)!=digest:raise TrustedEvidenceError('H032 independent original SHA drift: '+name)
    reports={};by_file={}
    for row in manifest.get('reports',[]):
        file='papers/'+row['file_name'];path=safe_source_path(root,file)
        if protected.get(file)!=row.get('sha256'):raise TrustedEvidenceError('H032 source registry SHA mismatch')
        projection=extract_pdf(path)
        if len(projection['pages'])!=row.get('physical_pages'):raise TrustedEvidenceError('H032 physical page count differs from frozen source')
        report=dict(row,file=file,projection=projection);reports[row['report_id']]=report;by_file[file]=report
    for row in manifest.get('verified_original_PDF_short_quotes',[]):
        source=reports.get(row.get('report_id'));page=row.get('physical_page_1_based')
        if source is None or type(page) is not int or not 1<=page<=len(source['projection']['pages']):raise TrustedEvidenceError('H032 source oracle page anchor invalid')
        if norm(row.get('short_quote','')) not in norm(source['projection']['pages'][page-1]['text']):raise TrustedEvidenceError('H032 source oracle short quote not in actual original physical page: '+str(row.get('evidence_id')))
    return {'reports':reports,'by_file':by_file,'source_manifest_sha256':sha(gt/'reference_source_manifest.json'),'protected_sha256':sha(gt/'protected_sha256.json'),'source_anchor_count':len(manifest.get('verified_original_PDF_short_quotes',[]))}

def physical_pages(locator):
    if not isinstance(locator,dict):return None
    value=next((locator[k] for k in ('physical_page_1_based','physical_page_1based','physical_page','page','pages','physical_pages','page_range') if k in locator),None)
    if isinstance(value,dict):value=[value.get('start'),value.get('end',value.get('start'))]
    if isinstance(value,str):
        value=re.sub(r'^\s*(?:物理页码?|物理第|第)','',value).strip();value=re.sub(r'页\s*$','',value);value=value.replace('至','-')
        match=re.fullmatch(r'\s*(?:p(?:age)?\.?\s*)?([1-9][0-9]*)\s*(?:[-–:]\s*([1-9][0-9]*))?\s*',value,re.I)
        if match:value=int(match[1]) if match[2] is None else [int(match[1]),int(match[2])]
    if type(value) is int:return [value] if value>=1 else None
    if isinstance(value,list) and value and all(type(v) is int and v>=1 for v in value):
        if len(value)==2 and value[1]>=value[0]:return list(range(value[0],value[1]+1))
        return value if len(set(value))==len(value) else None
    return None
def reviewed_scope(source,locator):
    if source is None:return {'valid':False,'reason':'reviewed document does not bind independent original'}
    pages=physical_pages(locator)
    if not pages:
        if isinstance(locator,dict) and any(isinstance(locator.get(k),str) and locator[k].strip() for k in ('scope','text','reason','checked_scope')):raise TrustedEvidenceError('UNSUPPORTED_REVIEWED_SCOPE_PROSE: preserve legal explanation for semantic position mapping; no silent0')
        return {'valid':False,'reason':'no concrete physical reviewed-page range'}
    if any(page>len(source['projection']['pages']) for page in pages):return {'valid':False,'reason':'reviewed page outside actual original'}
    return {'valid':True,'file':source['file'],'source_sha256':source['sha256'],'physical_pages':pages,'scope_truth':'Only declared checked positions bind; actual reading and absence meaning still require Judge'}
def _selection(text,locator):
    lines=text.splitlines();selected=text;kind='physical_page';detail={}
    if 'lines' in locator or 'line_range' in locator:
        value=locator.get('lines',locator.get('line_range'))
        if not isinstance(value,list) or len(value)!=2 or any(type(v) is not int for v in value):raise TrustedEvidenceError('UNSUPPORTED_PDF_LOCATOR: explicit line range representation')
        first,last=value
        if first<1 or last<first or last>len(lines):return '',{'kind':'out_of_range_lines'}
        return '\n'.join(lines[first-1:last]),{'kind':'actual_physical_page_lines','lines':[first,last]}
    requested=next((locator[k] for k in ('section','heading','table','caption','appendix') if k in locator),None)
    if requested is not None:
        if not isinstance(requested,str):raise TrustedEvidenceError('UNSUPPORTED_PDF_LOCATOR: clear section/table/caption text required')
        needle=norm(requested).casefold();hits=[i for i,line in enumerate(lines) if needle==norm(line).casefold() or norm(line).casefold().startswith(needle+':') or norm(line).casefold().startswith(needle+'.') or norm(line).casefold().startswith(needle+' ')]
        if len(hits)>1:raise TrustedEvidenceError('UNSUPPORTED_PDF_LOCATOR: repeated section label needs an explicit line/paragraph range')
        if not hits:return '',{'kind':'actual_section_absent','section':requested}
        start=hits[0];end=next((i for i in range(start+1,len(lines)) if re.match(r'^\s*(?:Table\s+[A-Za-z0-9]+|Appendix\s+[A-Za-z0-9]+|[0-9]+\.?\s+[A-Z])',lines[i])),len(lines));selected='\n'.join(lines[start:end]);kind='actual_section';detail={'section':requested,'line_range':[start+1,end]}
    paragraph=locator.get('paragraph')
    if paragraph is not None:
        if type(paragraph) is int:
            blocks=[part for part in re.split(r'\n\s*\n',selected) if part.strip()]
            if len(blocks)<=1 and paragraph>1:raise TrustedEvidenceError('UNSUPPORTED_PDF_PARAGRAPH_SEGMENTATION: faithful paragraph boundaries unavailable; use actual heading/line context')
            selected=blocks[paragraph-1] if 1<=paragraph<=len(blocks) else '';kind+=':paragraph';detail['paragraph']=paragraph
        elif isinstance(paragraph,str):
            matches=[line for line in selected.splitlines() if norm(paragraph) in norm(line)]
            selected='\n'.join(matches);kind+=':actual_paragraph_anchor';detail['paragraph_anchor']=paragraph
        else:raise TrustedEvidenceError('UNSUPPORTED_PDF_LOCATOR: paragraph representation')
    return selected,{'kind':kind,**detail}
def resolve_citation(source,citation,quote_match):
    if source is None:return {'resolved':False,'reason':'document does not bind a frozen local original'}
    if not isinstance(citation,dict) or not isinstance(citation.get('quote'),str) or not citation['quote'].strip():return {'resolved':False,'reason':'missing short quote'}
    locator=citation.get('locator');pages=physical_pages(locator)
    if not pages:return {'resolved':False,'reason':'actual physical page required; printed label alone is not enough'}
    all_pages=source['projection']['pages']
    if any(page>len(all_pages) for page in pages):return {'resolved':False,'reason':'physical page outside this original version'}
    chunks=[];positions=[]
    for page in pages:
        selected,position=_selection(all_pages[page-1]['text'],locator);chunks.append(selected);positions.append({'physical_page':page,**position})
    actual='\n'.join(chunks);matched=bool(actual) and quote_match(citation['quote'],actual)
    return {'resolved':bool(matched),'reason':'short quote at actual original physical page/context' if matched else 'quote absent at actual requested physical page/context','source_file':source['file'],'source_sha256':source['sha256'],'report_id':source['report_id'],'work_id':source['work_id'],'read_version':source['version'],'physical_pages':pages,'selected_text':actual,'selected_text_sha256':hashlib.sha256(actual.encode()).hexdigest(),'selected_positions':positions,'evidence_origin':'independent-original-PDF-physical-pages','normalization':'Actual raw page text preserved; conservative formatting only; no other page/file/version fallback'}
