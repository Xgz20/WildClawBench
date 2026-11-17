from pathlib import Path
import collections
import datetime
import hashlib
import importlib.util
import json
import math
import os
import re
import unicodedata
import zipfile

class H059TrustedError(RuntimeError):pass
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
    if not p.is_file() or p.is_symlink():raise H059TrustedError('H059_GT_REQUIRED: '+p.name)
    try:return json.loads(p.read_text())
    except (ValueError,OSError) as error:raise H059TrustedError('H059_GT_INVALID: '+p.name) from error
def norm(value):return ''.join(c for c in unicodedata.normalize('NFKC',str(value)) if not c.isspace() and not unicodedata.category(c).startswith('P'))
def unknown(value):return value is None or isinstance(value,str) and value.strip().lower() in {'','unknown','null','未知','未提供'}
def num(value):
    if type(value) in (float,int):return float(value) if math.isfinite(value) else None
    if isinstance(value,str):
        try:
            result=float(value.strip());return result if math.isfinite(result) else None
        except ValueError:return None
    return None
def rate_number(value):
    if isinstance(value,str):
        value=value.strip()
        if value.endswith('%'):
            parsed=num(value[:-1]);return parsed/100 if parsed is not None else None
    return num(value)
def boolean(value):
    if type(value) is bool:return value
    if isinstance(value,str):value=value.strip().casefold()
    if value in [1,'1','true','是','yes']:return True
    if value in [0,'0','false','否','no']:return False
    return None
def date(value):
    if isinstance(value,datetime.datetime):return value.date().isoformat()
    if isinstance(value,datetime.date):return value.isoformat()
    if isinstance(value,str):
        try:return datetime.date.fromisoformat(value.strip()).isoformat()
        except ValueError:return None
    return None
def parent(value):return None if unknown(value) or str(value).strip().lower()=='none' else str(value).strip()
def as_of(value):
    if not isinstance(value,str):return None
    text=unicodedata.normalize('NFKC',value).strip()
    if text.endswith('Asia/Shanghai'):text=text[:-len('Asia/Shanghai')].strip()
    text=text.replace('年','-').replace('月','-').replace('日',' ')
    try:
        result=datetime.datetime.fromisoformat(text)
        return result if result.tzinfo else result.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    except ValueError:return None
def visible_doc(path,Document,qn):
    doc=Document(path);lines=[]
    for p in doc.element.body.iter(qn('w:p')):
        values=[]
        for t in p.iter(qn('w:t')):
            run=next((a for a in t.iterancestors() if a.tag==qn('w:r')),None);hidden=False
            if run is not None:
                prop=run.find(qn('w:rPr'))
                hidden=prop is not None and any(prop.find(qn('w:'+k)) is not None and prop.find(qn('w:'+k)).get(qn('w:val'),'true') not in ['0','false'] for k in ['vanish','webHidden'])
            if not hidden:values.append(t.text or '')
        if ''.join(values).strip():lines.append(''.join(values).strip())
    return '\n'.join(lines)
def tables(book,aliases,get_column_letter):
    result={'sources':[],'metrics':[],'supports':[]}
    for sheet in book.worksheets:
        if sheet.sheet_state!='visible':continue
        # Pinned openpyxl sparse cells: formatting at row3001 or later does not
        # force a dense max_row rectangle or an undocumented layout cutoff.
        rows=collections.defaultdict(dict)
        for (r,c),cell in sheet._cells.items():
            if cell.value is None or sheet.row_dimensions[r].hidden or sheet.column_dimensions[get_column_letter(c)].hidden or cell.number_format==';;;':continue
            rows[r][c]=cell
        mapping=None;kind=None
        for r,cells in sorted(rows.items()):
            found={aliases[str(cell.value).strip()]:c for c,cell in cells.items() if str(cell.value).strip() in aliases}
            detected='metrics' if 'metric_id' in found else 'supports' if 'claim_id' in found else 'sources' if 'source_id' in found else None
            if detected and len(found)>=2:mapping=found;kind=detected;continue
            if mapping:
                value={key:cells[col].value if col in cells else None for key,col in mapping.items()}
                key={'sources':'source_id','metrics':'metric_id','supports':'claim_id'}[kind]
                if unknown(value.get(key)):continue
                value['_sheet']=sheet.title;value['_row']=r;value['_coordinates']={key:get_column_letter(col)+str(r) for key,col in mapping.items()};result[kind].append(value)
    return result
def quote_check(row,source):
    bound=row.get('source_sha256')==source['sha256']
    try:
        first=num(row['line_start']);last=num(row['line_end'])
        if first is None or last is None or not first.is_integer() or not last.is_integer():raise ValueError('physical line must be an integer')
        a=int(first);b=int(last);quote=norm(row['quote'])
        line_ok=1<=a<=b<=len(source['lines']);quote_ok=line_ok and len(quote)>=8 and quote in norm(''.join(source['lines'][a-1:b]))
        return bound,quote_ok,line_ok
    except (KeyError,ValueError,TypeError):return bound,False,False
def grade(workspace_path,transcript=None):
    root=Path(workspace_path);gt=root/'gt';manifest=load(gt/'trusted_manifest.json')
    for rel,digest in manifest['files'].items():
        p=gt/rel
        if not p.is_file() or p.is_symlink():raise H059TrustedError('H059_GT_REQUIRED: '+rel)
        if sha(p)!=digest:raise H059TrustedError('H059_GT_SHA_MISMATCH: '+rel)
    oracle=load(gt/'business_oracle.json');expected=load(gt/'expected.json');contract=load(gt/'artifact_contract.json');protected=load(gt/'protected_sha256.json');runtime=load(gt/'runtime_contract.json')
    try:
        import docx,openpyxl,pypdf
        from docx import Document
        from docx.oxml.ns import qn
        from docx.opc.exceptions import PackageNotFoundError
        from openpyxl.utils import get_column_letter
        from openpyxl.utils.exceptions import InvalidFileException
        from lxml.etree import XMLSyntaxError
    except ImportError as error:raise H059TrustedError('H059_DEPENDENCY_REQUIRED: '+str(error)) from error
    for name,version in [('python-docx',docx.__version__),('openpyxl',openpyxl.__version__),('pypdf',pypdf.__version__)]:
        if version!=runtime['libraries'][name]:raise H059TrustedError('H059_DEPENDENCY_VERSION: '+name)
    spec=importlib.util.spec_from_file_location('h059_office',gt/'office_runtime.py');office=importlib.util.module_from_spec(spec);spec.loader.exec_module(office)
    office_lock=load(gt/'office-runtime-lock.json');render_lock=load(gt/'office-render-lock.json')
    try:office.validate_office_lock(office_lock);office.validate_office_render_lock(render_lock)
    except office.OfficeRuntimeError as error:raise H059TrustedError('H059_RUNTIME_REQUIRED: '+str(error)) from error
    directory=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not directory:raise H059TrustedError('H059_EVIDENCE_DIR_REQUIRED')
    derived=Path(directory);derived.mkdir(parents=True,exist_ok=True);native={};errors={};parsed={k:False for k in contract['deliverables']};data={'sources':[],'metrics':[],'supports':[]};brief='';pdf_text='';uncertainties={}
    paths={key:root/value for key,value in contract['deliverables'].items()}
    for key,p in paths.items():
        try:
            if not p.is_file() or p.is_symlink() or p.stat().st_size>5*1024*1024:raise ValueError('candidate file missing/unsafe/above public attachment limit')
            if key=='brief':
                brief=visible_doc(p,Document,qn);native[key]=office.render_docx_pdf(p,render_lock,derived/'brief-render');pdf_text='\n'.join(page.extract_text() or '' for page in pypdf.PdfReader(native[key]['path']).pages)
            elif key=='evidence':
                native[key]=office.recalculate_xlsx(p,office_lock,derived/'evidence-office');book=openpyxl.load_workbook(native[key]['path'],data_only=True)
                data=tables(book,contract['aliases'],get_column_letter)
            else:
                uncertainties=json.loads(p.read_text());
                if not isinstance(uncertainties,dict):raise ValueError('uncertainties must be an object')
            parsed[key]=True
        except office.OfficeRuntimeError as error:
            candidate={'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED','OFFICE_RENDER_FAILED','OFFICE_RECALC_FAILED'}
            if error.code not in candidate:raise H059TrustedError('H059_OFFICE_OPERATION_FAILED: '+str(error)) from error
            errors[key]={'type':type(error).__name__,'detail':str(error)}
        except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,PackageNotFoundError,InvalidFileException,XMLSyntaxError) as error:errors[key]={'type':type(error).__name__,'detail':str(error)}
    business=[];boundary=[];evidence=[];groups=oracle['groups'];source_records={};metric_records={}
    def one(records,key,value):
        found=[r for r in records if r.get(key)==value];return found[0] if len(found)==1 else {}
    for sid,truth in oracle['sources'].items():
        row=one(data['sources'],'source_id',sid);source_records[sid]=row
        kind_alias={'厂商官方公告':'official_claim','媒体转述':'media_repost','聚合转载':'aggregate_repost','旧闻转载':'old_repost','个人观点':'user_opinion','观点转述':'opinion_repost'}
        checks={'parent':bool(row) and parent(row.get('parent_id'))==truth['parent_id'],'origin':row.get('origin_id')==truth['origin_id'],
            'published_date':date(row.get('published_date'))==truth['published_date'],'event_date':date(row.get('event_date'))==truth['event_date'],
            'kind':kind_alias.get(row.get('source_kind'),row.get('source_kind'))==truth['source_kind'],'in_week':boolean(row.get('in_week')) is truth['in_week']}
        business.extend({'id':sid,'key':key,'passed':bool(value)} for key,value in checks.items())
        cited=[r for r in data['supports'] if r.get('source_id')==sid]
        if all(key in row for key in ['quote','line_start','line_end','source_sha256']):cited=cited+[row]
        values=[quote_check(r,truth) for r in cited]
        evidence.extend({'id':sid,'key':key,'passed':bool(values) and all(v[index] for v in values)} for index,key in enumerate(['source_sha256','original_quote','actual_line_range']))
    for group in groups:
        members=group['members'];chosen=[source_records[s].get('event_id') for s in members];other={source_records[s].get('event_id') for s in oracle['sources'] if s not in members}
        partition=all(isinstance(x,str) and x.strip() for x in chosen) and len(set(chosen))==1 and chosen[0] not in other
        business.append({'id':group['root'],'key':'event_partition','passed':bool(partition)})
        independence=all(num(source_records[s].get('independent_roots'))==1 for s in members)
        boundary.append({'id':group['root'],'key':'independent_roots','passed':independence})
    status_alias={'可计算':'defined','0分母':'zero_denominator','比例无定义':'zero_denominator','缺分母':'missing_denominator','未知分母':'missing_denominator'}
    for mid,truth in oracle['metrics'].items():
        row=one(data['metrics'],'metric_id',mid);metric_records[mid]=row;observed_status=status_alias.get(row.get('rate_status'),row.get('rate_status'))
        denominator_ok=unknown(row.get('denominator')) if truth['denominator']=='unknown' else num(row.get('denominator'))==float(truth['denominator'])
        identity=bool(row) and row.get('source_id')==truth['source_id'] and row.get('platform')==truth['platform'] and date(row.get('window_start'))==truth['window_start'] and date(row.get('window_end'))==truth['window_end'] and row.get('numerator_kind')==truth['numerator_kind'] and num(row.get('numerator'))==truth['numerator'] and row.get('denominator_kind')==truth['denominator_kind'] and denominator_ok
        value=rate_number(row.get('rate'));rate_ok=observed_status==truth['status'] and (value is not None and abs(value-float(truth['value']))<=expected['rate_tolerance']+1e-12 if truth['status']=='defined' else value is None and (unknown(row.get('rate')) or row.get('rate')=='undefined'))
        business.extend([{'id':mid,'key':'metric_identity','passed':bool(identity)},{'id':mid,'key':'rate_value_status','passed':bool(row) and bool(rate_ok)}])
        boundary.append({'id':mid,'key':'paid_unknown','passed':bool(row) and unknown(row.get('paid_conversions'))})
    for sid in ['S04','S05']:boundary.append({'id':sid,'key':'old_event_not_weekly','passed':date(source_records[sid].get('event_date'))=='2026-07-15' and boolean(source_records[sid].get('in_week')) is False})
    for a,b in oracle['noncomparable_pairs']:boundary.append({'id':a+'|'+b,'key':'not_directly_comparable','passed':boolean(metric_records[a].get('pair_comparable')) is False and boolean(metric_records[b].get('pair_comparable')) is False})
    boundary.append({'id':'M05','key':'observed_zero_not_unknown','passed':num(metric_records['M05'].get('denominator'))==0 and metric_records['M05'].get('rate_status') in ['zero_denominator','0分母','比例无定义'] and rate_number(metric_records['M05'].get('rate')) is None})
    boundary.append({'id':'M06','key':'unknown_not_zero','passed':bool(metric_records['M06']) and unknown(metric_records['M06'].get('denominator')) and metric_records['M06'].get('rate_status') in ['missing_denominator','缺分母','未知分母'] and rate_number(metric_records['M06'].get('rate')) is None})
    issues=uncertainties.get('issues') if isinstance(uncertainties.get('issues'),list) else []
    for kind,refs in oracle['question_kind_refs'].items():
        found=[r for r in issues if isinstance(r,dict) and r.get('question_kind')==kind]
        passed=bool(found) and all(isinstance(r.get('source_refs'),list) and all(isinstance(x,str) for x in r['source_refs']) and bool(set(r['source_refs'])&set(refs)) and str(r.get('status')).lower() in ['unknown','未知'] and all(isinstance(r.get(k),str) and bool(r[k].strip()) for k in ['issue_id','question','next_check']) for r in found)
        boundary.append({'id':kind,'key':'bounded_unknown_record','passed':passed})
    graph=[]
    for group in groups:
        rows=[r for r in data['supports'] if r.get('source_id') in group['members']]
        passed=bool(rows) and all(isinstance(r.get('claim_id'),str) and bool(r['claim_id'].strip()) and isinstance(r.get('statement'),str) and bool(r['statement'].strip()) and isinstance(r.get('evidence_level'),str) and bool(r['evidence_level'].strip()) and isinstance(r.get('brief_locator'),str) and bool(norm(r['brief_locator'])) and norm(r['brief_locator']) in norm(brief) and norm(r['brief_locator']) in norm(pdf_text) and norm(r['claim_id']) in norm(brief) for r in rows)
        graph.append({'root':group['root'],'passed':passed})
    source_ids=set(oracle['sources']);metric_ids=set(oracle['metrics']);raw_ids_ok=all(r.get('source_id') in source_ids for r in data['sources']+data['supports']) and all(r.get('metric_id') in metric_ids for r in data['metrics'])
    asof_ok=as_of(uncertainties.get('as_of'))==as_of(oracle['as_of'])
    issues_valid=all(isinstance(r,dict) and all(isinstance(r.get(k),str) and bool(r[k].strip()) for k in ['issue_id','question_kind','status','question','next_check']) and isinstance(r.get('source_refs'),list) and all(isinstance(x,str) and x in source_ids|metric_ids for x in r['source_refs']) for r in issues)
    json_ok=asof_ok and isinstance(uncertainties.get('scope'),str) and bool(uncertainties['scope'].strip()) and issues_valid and len({r['issue_id'] for r in issues})==len(issues)>=6
    changed=[rel for rel,digest in protected.items() if not (root/rel).is_file() or (root/rel).is_symlink() or sha(root/rel)!=digest]
    delivery=.35*sum(parsed.values())/3+.25*float(not changed)+.25*sum(x['passed'] for x in graph)/4+.15*float(json_ok and raw_ids_ok)
    result={'business_correctness':sum(x['passed'] for x in business)/64,'boundary_cases':sum(x['passed'] for x in boundary)/22,'delivery_integrity':delivery,'evidence_binding':sum(x['passed'] for x in evidence)/24}
    result['overall_score']=sum(result[key]*weight for key,weight in expected['weights'].items())
    assert len(business)==64 and len(boundary)==22 and len(evidence)==24
    witness={'schema':'h059-native-rule-witness/v1','rule_result':result,'business_checks':business,'boundary_checks':boundary,'evidence_checks':evidence,'cross_product_graph':graph,
        'fixed_denominators':{'business':64,'boundary':22,'evidence':24},'parsed':parsed,'candidate_errors':errors,'protected_changes':changed,'native_operations':native,'observed_tables':data,
        'candidate_sha256':{key:sha(p) for key,p in paths.items() if p.is_file() and not p.is_symlink()},'gt_manifest_sha256':sha(gt/'trusted_manifest.json'),
        'semantic_boundary':'Objective origin/date/count/rate and literal quote bindings only. Real claim support, hierarchy, audience relevance and next-check meaning require semantic Judge; source IDs are not semantic proof.',
        'scope':'actual managed author rule/native Office observations, not Harness/Judge/hybrid final; hashes only prove custody'}
    (derived/'h059-rule-witness.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2,default=str)+'\n');return result
