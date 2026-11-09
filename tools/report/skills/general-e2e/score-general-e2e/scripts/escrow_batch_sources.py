"""Resolve only declared settlement origins corroborated by the unchanged public input."""
import hashlib

TASK = "03_Data_Analysis_task_010_contract_escrow_refund_reconciliation"
CONTRACT = "c93e50e83a8ac8eb9d6ba9e02510a762952b4011e8495c763073029a42bfff75"
PROFILE = "escrow-declared-settlement-source-index/v1"

BRIDGE = r'''
def _escrow_declared_batch_source_index(base, rows):
    from hashlib import sha256
    source=base/'托收服务结算.xlsx'
    if (source.is_symlink() or not source.is_file()
            or sha256(source.read_bytes()).hexdigest()!='93fd20bf692b0ab1ee9a9a98fd3ac7b916a6073be7d608b117a1e689e7481515'):
        raise ValueError('原公开结算表版本无法核实')
    batch_fields=('批次号','账户','渠道','币种')
    fields=set(batch_fields)|{'结算流水号'}
    origins={}
    book=openpyxl.load_workbook(source,data_only=True,read_only=True)
    try:
        for sheet in book:
            columns=None
            for line,values in enumerate(sheet.values,1):
                if fields<=set(values):
                    if any(values.count(k)!=1 for k in fields):raise ValueError('原结算表表头歧义')
                    columns={k:values.index(k) for k in fields}
                    continue
                if columns is None:continue
                identity=normalized(values[columns['结算流水号']])
                batch=tuple(normalized(values[columns[k]]) for k in batch_fields)
                if identity and all(batch):origins[(source.name,sheet.title,line)]=(batch,identity)
    finally:
        book.close()
    batches=defaultdict(set)
    counts=Counter()
    for row in rows:
        if normalized(row.get('类型'))!='结算' or normalized(row.get('处理状态'))!='纳入':
            continue
        locations_in_cell=locations(row.get('来源定位'))
        if len(locations_in_cell)!=1:raise ValueError('结算来源索引行必须定位单个原始记录')
        origin=next(iter(locations_in_cell))
        binding=origins.get(origin)
        if binding is None or normalized(row.get('业务编号'))!=binding[1]:
            raise ValueError('候选结算来源索引流水与原始位置冲突')
        batches[binding[0]].add(origin)
        counts[origin]+=1
        if counts[origin]!=1:raise ValueError('候选结算来源索引同一原始位置重复')
    return batches

def _escrow_expand_declared_batch_source(value,row,index_cells,base,source_rows,cache,audit):
    from hashlib import sha256
    parts=[p.strip() for p in re.split(r'[;；\n]',str(value or '')) if p.strip()]
    if not parts:return locations(value,index_cells)
    declared=re.fullmatch(r'…另([1-9]\d*)处（见来源索引）',parts[-1])
    if declared:
        parts.pop()
    elif re.fullmatch(r'[^|]+\.xlsx\|[^|]+\|[1-9]\d*\.\.\.',parts[-1]):
        parts[-1]=parts[-1][:-3]
    else:
        return locations(value,index_cells)
    if not cache:
        cache.append(_escrow_declared_batch_source_index(base,source_rows))
    batch=tuple(normalized(row.get(k)) for k in ('批次号','账户','渠道','币种'))
    visible_sets=[locations(part,index_cells) for part in parts]
    explicit=set().union(*visible_sets)
    chosen=cache[0].get(batch,set())
    if (not explicit or len(explicit)!=len(parts) or any(len(s)!=1 for s in visible_sets)
            or not all(batch) or not explicit < chosen
            or (declared and len(chosen-explicit)!=int(declared[1]))):
        raise ValueError('省略声明与候选原来源索引或公开批次归属无法唯一对齐')
    audit['expanded_claim_count']+=1
    audit['source_locations_count']+=len(chosen)
    if len(audit['examples'])<3:
        audit['examples'].append({'batch':batch,'visible':len(explicit),'resolved':len(chosen),
                                  'candidate_index_locations_sha256':sha256(json.dumps(sorted(chosen),ensure_ascii=False).encode()).hexdigest()})
    return chosen
'''


def marker(contract, contract_sha):
    if contract.get("task_id") != TASK or contract_sha != CONTRACT:
        return None
    return {"profile": PROFILE, "contract_sha256": CONTRACT,
            "source_sha256": hashlib.sha256(contract["automated_checks"].encode()).hexdigest()}


def effective_source(manifest, original, current, prior):
    frozen = manifest.get("runtime", {}).get("escrow_declared_batch_sources_profile")
    if frozen is None:
        return current, prior
    expected = marker({"task_id": manifest["identity"]["task_id"], "automated_checks": original},
                      manifest["digests"]["contract_sha256"])
    anchor = "    index_cells={r['_source_ref']:r.get('来源定位') for r in actual['来源索引'] if '_source_ref' in r}\n"
    locate = "gotloc=locations(row.get('来源'),index_cells)"
    if expected is None or frozen != expected or current.count(anchor) != 1 or current.count(locate) != 1:
        raise ValueError("ESCROW_DECLARED_BATCH_SOURCE_PROFILE_MISMATCH")
    current = current.replace(anchor, anchor + """    _escrow_batch_index_cache=[]
    _escrow_batch_index_audit={'expanded_claim_count':0,'source_locations_count':0,'examples':[]}
    diagnostic['declared_settlement_source_index']=_escrow_batch_index_audit
""", 1)
    current = current.replace(locate, """gotloc=(_escrow_expand_declared_batch_source(
                        row.get('来源'),row,index_cells,base,actual['来源索引'],_escrow_batch_index_cache,_escrow_batch_index_audit)
                        if name=='结算银行核对' else locations(row.get('来源'),index_cells))""", 1)
    effective = current + BRIDGE
    receipt = {"schema_version": "wildclawbench.general-e2e-rule-source-correction/v1",
               "correction_id": PROFILE, "task_id": TASK, "contract_sha256": CONTRACT,
               "original_source_sha256": expected["source_sha256"],
               "effective_source_sha256": hashlib.sha256(effective.encode()).hexdigest(),
               "candidate_rewritten": False, "numeric_decisions_assigned": False,
               "reason": "按候选来源索引的纳入记录、原公开结算表物理行、流水号和四字段批次身份验证省略；不用GT补候选引用，不把重复或范围外行补入批次。"}
    if prior:
        receipt["prior_correction"] = prior
    return effective, receipt
