"""Equivalent public headers and complete cell evidence for the exact news task."""
from __future__ import annotations
import hashlib

PROFILE='news-equivalent-headers-complete-cells/v1'
TASK='02_Office_task_003_news_event_multifile_extract'
CONTRACT_SHA='9abde6d34ad22e5fcf142618a7cfd3662c12eb8a0ca0de24930f361dbfda30fc'
SOURCE_SHA='af8be0f177e7d9e160a03a104562f2e34be9097f5acbbe5e3c30e7c8c00282a5'


def marker(contract,contract_sha):
    if (contract.get('task_id')==TASK and contract_sha==CONTRACT_SHA
            and hashlib.sha256(contract.get('automated_checks','').encode('utf-8')).hexdigest()==SOURCE_SHA):
        return {'profile':PROFILE,'contract_sha256':CONTRACT_SHA,'source_sha256':SOURCE_SHA,
            'per_file_bytes':4*1024*1024,'total_bytes':16*1024*1024,'truncation_allowed':False}
    return None


BRIDGE=r'''
_ge2e_news_aliases={
 'canonical_entity_or_topic':['规范主体/主题'],
 'citation_anchors':['片段锚点（≤80字）','片段锚点'],
 'alias_seen':['实际出现名称/别名'],
 'source_section':['来源章节/位置','章节/位置','来源章节/栏目'],
 'first_mention_order':['首次提及顺序'],
 'merged_source_count':['报道片段合计'],
 'evidence_snippet':['排除内容（短片段）'],
 'notes':['说明'],
 'item_id':['序号'],
}
for _ge2e_field,_ge2e_aliases in _ge2e_news_aliases.items():
    COLUMNS[_ge2e_field]=COLUMNS[_ge2e_field]+[a for a in _ge2e_aliases if a not in COLUMNS[_ge2e_field]]

def read_workbook(data):
    cached=openpyxl.load_workbook(BytesIO(data),data_only=True,read_only=False,keep_links=False)
    formulas=openpyxl.load_workbook(BytesIO(data),data_only=False,read_only=False,keep_links=False)
    try:
        raw=[];wide_total=False
        for ws in cached:
            if ws.max_row>4000 or ws.max_column>120:
                raise EvidenceError('Workbook dimensions exceed complete cell evidence capacity; review required')
            table=[]
            for row in ws.iter_rows():
                if not any(c.value is not None or formulas[ws.title][c.coordinate].value is not None for c in row):continue
                cells=[]
                for cell in row:
                    formula=formulas[ws.title][cell.coordinate]
                    cells.append({'cell':cell.coordinate,'value':cell.value,'data_type':cell.data_type,
                        'number_format':cell.number_format,
                        'formula':formula.value if formula.data_type=='f' else None})
                table.append({'row':row[0].row,'cells':cells})
            raw.append({'sheet':ws.title,'rows':table,'merged_ranges':[str(r) for r in ws.merged_cells.ranges]})
            if norm(ws.title) in {norm(n) for n in SHEETS['category_summary']}:
                for row in list(ws.iter_rows(values_only=True))[:15]:
                    headings=[str(v or '') for v in row]
                    dated=[v for v in headings if re.fullmatch(r'20\d{2}[-/]\d{2}[-/]\d{2}\s*事件数',v)]
                    if (len(dated)>=2 and any(norm(v)==norm('合计') for v in headings)
                            and not any(norm(v) in {norm(a) for a in COLUMNS['event_count']} for v in headings)):
                        wide_total=True
        previous=list(COLUMNS['event_count'])
        try:
            if wide_total:COLUMNS['event_count']=previous+['合计']
            result=_ge2e_news_original_read_workbook(data)
        finally:COLUMNS['event_count']=previous
        for rows in result.values():
            for row in rows:
                value=row.get('source_file')
                if not isinstance(value,str):continue
                relative=value.replace('\\','/').strip()
                if relative.startswith('/tmp_workspace/input/'):relative=relative[len('/tmp_workspace/input/'):]
                while relative.startswith('./'):relative=relative[2:]
                if relative.startswith('input/'):relative=relative[6:]
                if relative.startswith('/') or '://' in relative or '..' in relative.split('/'):continue
                matches=[p for p in FROZEN_CONTEXT['source_texts'] if p==relative or p.endswith('/'+relative)]
                if len(matches)==1:row['source_file']=matches[0]
        # Complete physical cells retain extra columns, formulas/cache state and
        # every source locator; no workbook bytes or business values are written.
        result['_complete_workbook_cells']=raw
        return result
    finally:
        cached.close();formulas.close()
'''


def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('news_workbook_layout_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest.get('identity',{}).get('task_id'),'automated_checks':original},
        manifest.get('digests',{}).get('contract_sha256'))
    if expected is None or frozen!=expected:raise ValueError('NEWS_WORKBOOK_LAYOUT_PROFILE_MISMATCH')
    declaration='def read_workbook(data):'
    old="    if any(len(s)>19000 for s in serialized.values()) or sum(map(len,serialized.values()))>72000:"
    if current.count(declaration)!=1 or current.count(old)!=1:raise ValueError('NEWS_WORKBOOK_LAYOUT_SOURCE_SPAN_MISMATCH')
    current=current.replace(declaration,'def _ge2e_news_original_read_workbook(data):')
    current=current.replace(old,"    if any(len(s.encode('utf-8'))>4194304 for s in serialized.values()) or sum(len(s.encode('utf-8')) for s in serialized.values())>16777216:")
    current+=BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':TASK,'contract_sha256':CONTRACT_SHA,'original_source_sha256':SOURCE_SHA,
        'effective_source_sha256':hashlib.sha256(current.encode('utf-8')).hexdigest(),
        'original_workbook_rewritten':False,'business_values_invented':False,'evidence_budget':expected,
        'reason':'仅适配公开允许的等价表头及显式双日期合计布局，并在原六份取证材料内保全全部物理单元格、公式/缓存和位置；原比较、分母、权重不变，资源上限明确扩大以完整取证，超过仍失败且不截断。'}
    if prior:receipt['prior_correction']=prior
    return current,receipt
