"""Retain the original, unscored request for safe formula-cache evaluation."""
import hashlib,re
from pathlib import Path
import zipfile,posixpath
import xml.etree.ElementTree as ET

TASK='03_Data_Analysis_task_007_promotion_discounts_sales_margin'
CONTRACT='d9dc7cbb2f558326a419ccc40318761b83f50e45b8c91fec3e97077562cd336b'
SOURCE='b0e0cabf28c9edba2e8ac6eee88f8b8b0f528fa75cbab843c8ab98a8b1962a88'
DATASET={'id':'general-custom70-v6','digest':'20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'}
PREFIX='候选公式缺缓存，需评测方安全只读求值后再判，不按业务0分：'

def evidence(rt,attempt,manifest,contract,task):
    if (contract.get('task_id')!=TASK or manifest.get('dataset')!=DATASET
        or manifest.get('digests',{}).get('contract_sha256')!=CONTRACT
        or hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()!=SOURCE
        or manifest.get('runtime',{}).get('promotion_formula_value_profile') is not None
        or task.get('thread') is not None or task.get('score') is not None
        or any((attempt/p).exists() for p in ['score.json','rule-component.json','semantic'])):
        raise ValueError('PROMOTION_CACHE_FAILURE_IDENTITY_INVALID')
    request_path=attempt/'worker/request.json';request=rt._read_json(request_path)
    result=rt._read_json(attempt/'worker/result.json');audit=rt._read_json(attempt/'rule-audit.json')
    error=result.get('error',{});message=error.get('message','')
    if (hashlib.sha256(request.get('automated_checks','').encode()).hexdigest()!=SOURCE
        or result.get('ok') is not False or result.get('result') is not None
        or error.get('type')!='GradingIndeterminate' or not isinstance(message,str) or not message.startswith(PREFIX)
        or audit.get('identity')!=manifest['identity'] or audit.get('status')!='failed'
        or audit.get('runtime_workspace',{}).get('drifted') is not False
        or audit.get('worker',{}).get('return_code')!=1 or audit.get('worker',{}).get('timed_out') is not False
        or audit.get('worker',{}).get('request_sha256')!=rt._sha256_file(request_path)
        or audit.get('worker',{}).get('process_tree_cleanup',{}).get('remaining') is not False
        or audit.get('worker',{}).get('worker_pid')!=result.get('worker',{}).get('pid')):
        raise ValueError('PROMOTION_CACHE_FAILURE_SIGNATURE_INVALID')
    locations=message[len(PREFIX):].split(',')
    if not 0<len(locations)<=20 or len(locations)!=len(set(locations)) or any(not re.fullmatch(r'[^!]+![A-Z]{1,3}[1-9]\d*',p) for p in locations):
        raise ValueError('PROMOTION_CACHE_FAILURE_LOCATIONS_INVALID')
    relative=Path('results')/'促销毛利分析.xlsx'
    candidate=attempt/manifest['paths']['candidate_original']/relative
    runtime=attempt/manifest['runtime']['workspace_argument']/relative
    if candidate.is_symlink() or runtime.is_symlink() or rt._sha256_file(candidate)!=rt._sha256_file(runtime):
        raise ValueError('PROMOTION_CACHE_FAILURE_WORKBOOK_DRIFT')
    needed={}
    for location in locations:
        sheet,cell=location.rsplit('!',1);needed.setdefault(sheet,set()).add(cell)
    ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    relation='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    with zipfile.ZipFile(candidate) as z:
        paths={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        sheets=ET.fromstring(z.read('xl/workbook.xml')).find(ns+'sheets');verified=set()
        for sheet in sheets:
            name=sheet.attrib['name']
            if name not in needed:continue
            target=paths[sheet.attrib[relation]];part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            with z.open(part) as stream:
                for event,cell in ET.iterparse(stream,events=['end']):
                    if cell.tag!=ns+'c':continue
                    address=cell.attrib.get('r');value=cell.find(ns+'v')
                    if address in needed[name]:
                        if cell.find(ns+'f') is None or value is not None and value.text is not None:
                            raise ValueError('PROMOTION_CACHE_FAILURE_CELL_NOT_UNCACHED_FORMULA')
                        verified.add(name+'!'+address)
                        if set(locations)<=verified:break
                    cell.clear()
        if verified!=set(locations):raise ValueError('PROMOTION_CACHE_FAILURE_CELLS_MISSING')
    return result
