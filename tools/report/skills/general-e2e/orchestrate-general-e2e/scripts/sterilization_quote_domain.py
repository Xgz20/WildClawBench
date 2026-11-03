"""Source-bound quote fields; distinguish explicit country from transport endpoint."""
from pathlib import Path
import hashlib,json,re
TASK='02_Office_task_024_sterilization_quote'
CONTRACT='e9bc066864701efbba218bb1b3adf2547471d5ee17f95a7b84dbe4b32f69c83c'
SOURCE='785e6831505ba1d0fdc341bc36bfc716e2931ab173888ef3dcd4f2617f94d2c8'
PROFILE='sterilization-quote-field-domain/v2'
HEADINGS={'Estimated transit time':'transit','Est. total delivery time*':'elapsed','Validity of rate':'validity'}
def marker(contract,sha,dataset):
    if (contract.get('task_id')==TASK and sha==CONTRACT and dataset.get('id')=='general-custom70-v2'
        and dataset.get('digest')=='001016f24b4bc20f96733592ea4aabe6a3b8e1e5bfd0dbc9052254ea36430c0e'
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE):
        return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE}
    return None
COUNTRY_OLD="""    destination=book.kv(r'^(destinationcountry|destination|目的地国家|目的国|目的地)$')
    if not destination:
        for r in visible:
            if re.fullmatch(r'(destinationcountry|destination|目的地国家|目的国|目的地)',norm(r['value'])):
                destination += [c for c in book.rows.get((r['sheet'],r['row']+1),[]) if c['col']==r['col']]"""
HELPER=r'''
def _ge2e_quote_country_values(book):
    # Prefer a field which explicitly declares its domain, never a country value
    # selected for matching GT. All explicit country statements remain compared.
    explicit=[];labels=[]
    for row in book.rows.values():
        for i,label in enumerate(row):
            if norm(label['value']) in {'destinationcountry','countryofdestination','目的地国家','目的国'}:
                labels.append(label)
                right=[c for c in row[i+1:] if c['value'] is not None]
                if right and norm(right[0]['value']) in {'destinationcountry','countryofdestination','目的地国家','目的国'}:right=[]
                explicit += right[:1] if right else [c for c in book.rows.get((label['sheet'],label['row']+1),[]) if c['col']==label['col']]
    if labels:return explicit
    result=book.kv(r'^(destination|目的地)$')
    if not result:
        for row in book.rows.values():
            for label in row:
                if norm(label['value']) in {'destination','目的地'}:
                    result += [c for c in book.rows.get((label['sheet'],label['row']+1),[]) if c['col']==label['col']]
    return result
'''
def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('sterilization_quote_layout_profile')
    if (frozen or {}).get('profile')!=PROFILE:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'],manifest['dataset'])
    if frozen!=expected or expected is None:raise ValueError('QUOTE_DOMAIN_PROFILE_MISMATCH')
    anchor="    return next((k for k,rx in PATTERNS.items() if re.fullmatch(rx,s)),None)"
    aliases={re.sub(r'[\s\W_]+','',k.lower()):v for k,v in HEADINGS.items()}
    if current.count(anchor)!=1 or current.count(COUNTRY_OLD)!=1:raise ValueError('QUOTE_DOMAIN_SOURCE_SPAN')
    # Original built-in aliases retain precedence.
    end=" or {'esttotalinclgoodsusd': 'grand', 'estimateddeliveryfromorder': 'elapsed', 'ratevalidity': 'validity'}.get(s)"
    if current.count(anchor+end)!=1:raise ValueError('QUOTE_DOMAIN_ORIGINAL_ALIASES')
    effective=current.replace(anchor+end,anchor+end+' or '+repr(aliases)+'.get(s)').replace(COUNTRY_OLD,'    destination=_ge2e_quote_country_values(book)')+HELPER
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,'task_id':TASK,
        'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_decisions_assigned':False,'equivalent_headings':HEADINGS,
        'reason':'识别三项明确等价表头；目的国优先读取显式国家域的横向/下方值，保留所有国家声明，不按值是否正确择优。泛运输端点不覆盖显式国家。原金额、时间、有效期比较、全部重大事件限分及60/40不变。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt

def validate_blocker(attempt,m,contract,b):
    if marker(contract,m['digests']['contract_sha256'],m['dataset']) is None:raise ValueError('QUOTE_DOMAIN_FAILURE_UNREGISTERED')
    if (b.get('schema_version')!='local-scoring-infrastructure-blocker/v1' or b.get('code')!='FROZEN_RULE_EXTRACTION_MISMATCH'
        or b.get('standard_score_created') is not False or b.get('total_score') is not None
        or b.get('identity')!={k:m['identity'][k] for k in ['batch_id','execution_attempt_id','scoring_attempt_id','task_id','unit_id']}
        or (attempt/'score.json').exists() or b.get('semantic_review',{}).get('imported') is not False):raise ValueError('QUOTE_DOMAIN_BLOCKER_INVALID')
    failures=b.get('field_label_failures',[])
    if len(failures)!=3 or {r.get('label_cell',{}).get('value') for r in failures}!=set(HEADINGS):raise ValueError('QUOTE_DOMAIN_BLOCKER_FIELDS')
    for name,expected in b.get('frozen_file_sha256',{}).items():
        path=Path(attempt)/name
        if path.is_symlink() or not path.resolve().is_relative_to(Path(attempt).resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('QUOTE_DOMAIN_BLOCKER_DRIFT')
    draft=b['semantic_review'];path=Path(attempt)/draft['path']
    if path.is_symlink() or not path.resolve().is_relative_to(Path(attempt).resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=draft['sha256']:raise ValueError('QUOTE_DOMAIN_DRAFT_DRIFT')
    worker=json.loads((Path(attempt)/'worker/result.json').read_text())
    if worker.get('raw_result',{}).get('diagnostics')!=b.get('worker_diagnostics_unchanged'):raise ValueError('QUOTE_DOMAIN_DIAGNOSTIC_DRIFT')
    import io,openpyxl
    base=Path(attempt)/m['paths']['candidate_original'];candidates=list(base.rglob('Q9749821-revised_including_transport.xlsx'))
    if len(candidates)!=1:raise ValueError('QUOTE_DOMAIN_CANDIDATE')
    w=openpyxl.load_workbook(io.BytesIO(candidates[0].read_bytes()),data_only=False,keep_links=False)
    try:
        cells=[r['label_cell'] for r in failures]+[c for r in failures for c in r['visible_value_cells']]+[b['destination_failure']['candidate_country_cell']]
        for c in cells:
            if w[c['sheet']][c['cell']].value!=c['value']:raise ValueError('QUOTE_DOMAIN_CELL_DRIFT')
    finally:w.close()
    return True
