from pathlib import Path
import collections
import csv
import datetime
import hashlib
import importlib.util
import json
import os
import re
import unicodedata
import zipfile

class H058TrustedError(RuntimeError):pass
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def trusted(p):
    if not p.is_file() or p.is_symlink():raise H058TrustedError('H058_GT_REQUIRED: '+p.name)
    try:return json.loads(p.read_text())
    except (ValueError,OSError) as e:raise H058TrustedError('H058_GT_INVALID: '+p.name) from e
def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',str(value)) if not c.isspace() and not unicodedata.category(c).startswith('P'))
def ids(value):return [s.strip() for s in re.split(r'[;；,，\s]+',str(value)) if s.strip()]
def count(value):return len(re.sub(r'\s','',value))
def tokens(value):return re.findall(r'#([\w\u3400-\u9fff]+)',value)
def parse_doc(path,Document,qn):
    doc=Document(path);lines=[]
    for p in doc.element.body.iter(qn('w:p')):
        pieces=[]
        for t in p.iter(qn('w:t')):
            ancestors=list(t.iterancestors());run=next((x for x in ancestors if x.tag==qn('w:r')),None)
            hidden=False
            if run is not None:
                prop=run.find(qn('w:rPr'))
                hidden=prop is not None and any(prop.find(qn('w:'+k)) is not None and prop.find(qn('w:'+k)).get(qn('w:val'),'true') not in ['0','false'] for k in ['vanish','webHidden'])
            if not hidden:pieces.append(t.text or '')
        if ''.join(pieces).strip():lines.append(''.join(pieces).strip())
    blocks={};current=None;field=None
    for line in lines:
        marker=re.fullmatch(r'【(T[1-3]|P[1-3][1-3])】',line)
        if marker:
            current={};blocks.setdefault(marker[1],[]).append(current);field=None;continue
        if current is None:continue
        match=re.match(r'^(主题名|论点|依据|释义|关联|边界|主题|渠道|标题|正文|标签|引文|适配)\s*[:：](.*)$',line)
        if match:field=match[1];current.setdefault(field,[]).append(match[2].strip())
        elif field:current[field].append(line)
    return {k:[{f:'\n'.join(values).strip() for f,values in block.items()} for block in rows] for k,rows in blocks.items()},lines
def csv_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames
        if not fields or len(fields)!=len(set(fields)):raise ValueError('CSV duplicate/empty header')
        rows=list(reader)
    if len(rows)>1000:raise ValueError('CSV row limit')
    return rows
def date_value(value):
    if isinstance(value,datetime.datetime):return value.date()
    if isinstance(value,datetime.date):return value
    if isinstance(value,str):
        try:return datetime.date.fromisoformat(value)
        except ValueError:return None
    return None
def parse_calendar(workbook,aliases,get_column_letter):
    records=[]
    for sheet in workbook.worksheets:
        if sheet.sheet_state!='visible':continue
        if sheet.max_row>3000 or sheet.max_column>100:raise H058TrustedError('H058_SUPPORTED_CALENDAR_PROFILE_LIMIT_UNASSESSED: native worksheet beyond3000rows or100columns, no candidate score')
        mapping=None
        for row in sheet.iter_rows():
            if sheet.row_dimensions[row[0].row].hidden:continue
            visible=[cell for cell in row if not sheet.column_dimensions[get_column_letter(cell.column)].hidden and cell.number_format!=';;;']
            found={aliases[str(c.value).strip()]:c.column-1 for c in visible if str(c.value).strip() in aliases}
            if set(found)==set(aliases.values()):mapping=found;continue
            if mapping:
                values={k:row[index].value for k,index in mapping.items()}
                if values.get('content_id') is None:continue
                values['sheet']=sheet.title;values['row']=row[0].row;records.append(values)
    return records
def grade(workspace_path,transcript=None):
    root=Path(workspace_path);gt=root/'gt';manifest=trusted(gt/'trusted_manifest.json')
    for rel,digest in manifest['files'].items():
        p=gt/rel
        if not p.is_file() or p.is_symlink():raise H058TrustedError('H058_GT_REQUIRED: '+rel)
        if sha(p)!=digest:raise H058TrustedError('H058_GT_SHA_MISMATCH: '+rel)
    expected=trusted(gt/'expected.json');oracle=trusted(gt/'business_oracle.json');contract=trusted(gt/'artifact_contract.json');protected=trusted(gt/'protected_sha256.json');rules=trusted(gt/'protected_inputs/channel_rules.json');evidence=trusted(gt/'evidence_requirements.json')
    runtime=trusted(gt/'runtime_contract.json')
    try:
        import docx,openpyxl,pypdf
        from docx import Document
        from docx.oxml.ns import qn
        from docx.opc.exceptions import PackageNotFoundError
        from openpyxl.utils import get_column_letter
        from openpyxl.utils.exceptions import InvalidFileException
        from lxml.etree import XMLSyntaxError
    except ImportError as error:raise H058TrustedError('H058_DEPENDENCY_REQUIRED: '+str(error)) from error
    for name,version in [('python-docx',docx.__version__),('openpyxl',openpyxl.__version__),('pypdf',pypdf.__version__)]:
        if runtime['libraries'][name]!=version:raise H058TrustedError('H058_DEPENDENCY_VERSION: '+name)
    spec=importlib.util.spec_from_file_location('h058_office_runtime',gt/'office_runtime.py');office=importlib.util.module_from_spec(spec);spec.loader.exec_module(office)
    office_lock=trusted(gt/'office-runtime-lock.json');render_lock=trusted(gt/'office-render-lock.json')
    try:office.validate_office_lock(office_lock);office.validate_office_render_lock(render_lock)
    except office.OfficeRuntimeError as error:raise H058TrustedError('H058_RUNTIME_REQUIRED: '+str(error)) from error
    directory=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not directory:raise H058TrustedError('H058_EVIDENCE_DIR_REQUIRED')
    derived=Path(directory);derived.mkdir(parents=True,exist_ok=True)
    paths={k:root/v for k,v in contract['deliverables'].items()};parsed={k:False for k in paths};errors={};blocks={};lines=[];citations=[];calendar=[];native={}
    for key,path in paths.items():
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size>5*1024*1024:raise ValueError('candidate file missing/unsafe/too large')
            if key=='campaign':
                blocks,lines=parse_doc(path,Document,qn)
                native[key]=office.render_docx_pdf(path,render_lock,derived/'campaign-render')
                pdf=Path(native[key]['path'])
                pdf_text='\n'.join(p.extract_text() or '' for p in pypdf.PdfReader(pdf).pages)
                native['campaign_visible_ids']={cid:cid in pdf_text for cid in expected['content_ids']}
            elif key=='citations':citations=csv_rows(path)
            else:
                native[key]=office.recalculate_xlsx(path,office_lock,derived/'calendar-office')
                workbook=openpyxl.load_workbook(derived/'calendar-office/recalculated.xlsx',data_only=True)
                calendar=parse_calendar(workbook,contract['calendar_aliases'],get_column_letter)
            parsed[key]=True
        except office.OfficeRuntimeError as error:
            candidate_codes={'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED','OFFICE_RENDER_FAILED','OFFICE_RECALC_FAILED'}
            if error.code not in candidate_codes:raise H058TrustedError('H058_OFFICE_OPERATION_FAILED: '+str(error)) from error
            errors[key]={'type':type(error).__name__,'detail':str(error)}
        except (OSError,ValueError,KeyError,TypeError,csv.Error,zipfile.BadZipFile,PackageNotFoundError,InvalidFileException,XMLSyntaxError) as error:
            errors[key]={'type':type(error).__name__,'detail':str(error)}
    sources={s['source_id']:s for s in oracle['sources']};by_content=collections.defaultdict(list)
    for row in citations:
        if isinstance(row,dict):by_content[row.get('content_id')].append(row)
    def citation_valid(row):
        try:
            s=sources[row['source_id']];start=int(row['line_start']);end=int(row['line_end']);quote=norm(row['quote'])
            return (row['author'] in [s['author']]+s['author_aliases'] and row['version_id']==s['version_id'] and 1<=start<=end<=len(s['lines']) and len(quote)>=8 and quote in norm(''.join(s['lines'][start-1:end])))
        except (KeyError,TypeError,ValueError):return False
    citation_checks=[{'citation_id':r.get('citation_id'),'content_id':r.get('content_id'),'valid':citation_valid(r)} for r in citations]
    business=[];boundary=[];bindings=[];channel={x['channel_id']:x for x in rules['channels']};selected_sources=set()
    for cid in expected['content_ids']:
        found=blocks.get(cid,[]);copy=found[0] if len(found)==1 else {};rows=by_content[cid];body=copy.get('正文','');valid_rows=[r for r in rows if citation_valid(r)]
        declared=ids(copy.get('引文',''));row_ids=[r.get('citation_id') for r in rows];quoted=re.findall('“([^”]+)”',body)
        schema=bool(copy) and all(k in copy for k in ['主题','渠道','标题','正文','标签','引文','适配']) and copy.get('主题')=='T'+cid[1] and copy.get('渠道')=='C'+cid[2]
        facts=bool(rows) and len(valid_rows)==len(rows)
        actual_quotes=bool(quoted) and all(any(norm(q)==norm(r.get('quote','')) for r in valid_rows) for q in quoted) and all(norm(r['quote']) in norm(body) for r in valid_rows)
        graph=bool(declared) and len(row_ids)==len(set(row_ids)) and set(declared)==set(row_ids) and all(row_ids.count(x)==1 for x in declared)
        for key,passed in [('copy_schema',schema),('citation_fact',facts),('quoted_text',actual_quotes),('citation_graph',graph)]:business.append({'id':cid,'key':key,'passed':bool(passed)})
        if facts:selected_sources.update(r['source_id'] for r in valid_rows)
        r=channel['C'+cid[2]];tag_list=tokens(copy.get('标签',''));paragraphs=[p for p in body.split('\n') if p.strip()]
        if cid[2]=='1':structure=len(paragraphs)>=3
        elif cid[2]=='2':structure=len(paragraphs)>=2 and (all(x in body for x in ['1.','2.']) or all(x in body for x in ['1、','2、']) or all(x in body for x in ['①','②'])) and ('？' in paragraphs[-1] or '?' in paragraphs[-1]) if paragraphs else False
        else:structure=len(paragraphs)>=3 and all(any(label in body for label in options) for options in [['画面：','画面:','镜头：','镜头:'],['口播：','口播:','旁白：','旁白:'],['互动：','互动:','提问：','提问:']])
        checks={'body_length':r['body_min']<=count(body)<=r['body_max'],'title_length':r['title_min']<=count(copy.get('标题',''))<=r['title_max'],'channel_structure':structure,
                'tags_and_brand':len(tag_list)==len(set(tag_list))==r['tag_count'] and not any(word in body+copy.get('标题','') for word in rules['forbidden_expressions'])}
        boundary.extend({'id':cid,'key':key,'passed':bool(value)} for key,value in checks.items())
        hash_bound=bool(rows) and all(r.get('source_id') in sources and r.get('source_sha256')==sources[r['source_id']]['sha256'] for r in rows)
        locator_bound=bool(rows) and bool(copy) and all(r.get('campaign_locator')==cid+':正文' and norm(r.get('quote','')) in norm(body) for r in rows)
        bindings.append({'id':cid,'source_sha256':hash_bound,'campaign_locator':locator_bound})
    for tid in expected['theme_ids']:
        found=blocks.get(tid,[]);theme=found[0] if len(found)==1 else {}
        fields=all(theme.get(k) for k in ['主题名','论点','依据','释义','关联','边界'])
        references=re.findall(r'(S0[1-8]):L(\d+)-L(\d+)',theme.get('依据',''))
        resolved={s for s,a,b in references if 1<=int(a)<=int(b)<=len(sources[s]['lines'])}
        used={r['source_id'] for cid in expected['content_ids'] if cid[1]==tid[1] for r in by_content[cid] if citation_valid(r)}
        business.extend([{'id':tid,'key':'theme_fields','passed':bool(fields)},{'id':tid,'key':'theme_sources','passed':len(resolved)>=2 and len(used)>=2 and used<=resolved}])
        bodies=[norm(re.sub('“[^”]+”','',blocks.get('P'+tid[1]+str(i),[{}])[0].get('正文',''))) for i in [1,2,3]]
        distinct=all(a and b and not a.startswith(b) and not b.startswith(a) for i,a in enumerate(bodies) for b in bodies[i+1:])
        boundary.append({'id':tid,'key':'not_identical_or_prefix','passed':distinct})
    business.append({'id':'campaign','key':'six_sources','passed':len(selected_sources)>=6})
    days=collections.Counter(date_value(r.get('suggested_date')) for r in calendar);channel_days=collections.Counter((date_value(r.get('suggested_date')),r.get('channel_id')) for r in calendar)
    planning=rules['planning'];start=datetime.date.fromisoformat(planning['start']);end=datetime.date.fromisoformat(planning['end']);calendar_graph=[]
    for cid in expected['content_ids']:
        rows=[r for r in calendar if r.get('content_id')==cid];row=rows[0] if len(rows)==1 else {};day=date_value(row.get('suggested_date'))
        planned=day is not None and start<=day<=end and row.get('slot') in planning['slots'] and row.get('status')==planning['status'] and days[day]<=planning['max_per_day'] and channel_days[(day,row.get('channel_id'))]<=planning['max_per_channel_day']
        boundary.append({'id':cid,'key':'one_time_plan','passed':bool(planned)})
        expected_refs={r.get('citation_id') for r in by_content[cid]}
        calendar_graph.append(bool(row) and row.get('theme_id')=='T'+cid[1] and row.get('channel_id')=='C'+cid[2] and isinstance(row.get('owner'),str) and bool(row['owner'].strip()) and set(ids(row.get('citation_ids','')))==expected_refs and bool(expected_refs))
    changed=[rel for rel,digest in protected.items() if not (root/rel).is_file() or (root/rel).is_symlink() or sha(root/rel)!=digest]
    csv_shape=all(set(evidence['csv_fields'])<=set(r) for r in citations) and bool(citations)
    visible=all(native.get('campaign_visible_ids',{}).get(cid,False) for cid in expected['content_ids'])
    delivery=.35*sum(parsed.values())/3+.25*float(not changed)+.25*(sum(calendar_graph)/9 if len(calendar)==9 else 0)+.15*float(csv_shape and visible)
    result={'business_correctness':sum(x['passed'] for x in business)/43,'boundary_cases':sum(x['passed'] for x in boundary)/48,'delivery_integrity':delivery,
            'evidence_binding':sum(float(x['source_sha256'])+float(x['campaign_locator']) for x in bindings)/18}
    result['overall_score']=sum(result[k]*w for k,w in expected['weights'].items())
    witness={'schema':'h058-native-rule-witness/v1','rule_result':result,'fixed_denominators':{'business':43,'boundary':48,'evidence':18},'business_checks':business,'boundary_checks':boundary,
             'evidence_bindings':bindings,'citation_checks':citation_checks,'calendar_graph':calendar_graph,'parsed':parsed,'candidate_errors':errors,'protected_changes':changed,
             'native_operations':native,'candidate_sha256':{k:sha(p) for k,p in paths.items() if p.is_file() and not p.is_symlink()},'gt_manifest_sha256':sha(gt/'trusted_manifest.json'),
             'semantic_boundary':'Rules check source strings/author/version/structure/graphs only; actual theme support, interpretation and adaptation require independent semantic Judge.',
             'scope':'author managed rule observations; no Harness/Judge/finalize; derived hashes prove custody only'}
    (derived/'h058-rule-witness.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2,default=str)+'\n')
    return result
