"""Distinguish available daily hours from explicitly allocated order hours."""
import hashlib
TASK='02_Office_task_026_work_order_labor_reconciliation'
CONTRACT='b5016c9afb626a69a114f943b24d5a2172317ff37a1e8a6ef58c921d1ead60b2'
SOURCE='fc8e2651f671b067faf87528bf508ff559454cefda43bb9ae6a08e1010587ac9'
PROFILE='work-order-explicit-column-roles/v1'
def marker(contract,sha):
    if contract.get('task_id')==TASK and sha==CONTRACT and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE:
        return {'profile':PROFILE,'contract_sha256':CONTRACT,'source_sha256':SOURCE}
    return None
HELPER=r'''
LOOKUP.update({norm(header):key for header,key in [
    ('出勤总人时','labor'),('检验数合计','units'),('缺陷数合计','defects'),
    ('排期工时偏差','deviation'),('缺陷率超限','flags'),('问题与待核清项','issue'),('问题描述','issue')]})

def _ge2e_work_order_mapping(values,order_table,mapping):
    explicit={norm(v) for v in ['分摊工时','工单实际工时','分摊实际工时','工单分摊人时','实际分摊人时','allocatedhours','actualhours']}
    available={norm(v) for v in ['可分摊生产工时','可分摊工时','可分摊h','可分摊人时']}
    if order_table and any(norm(v) in explicit for v in values):
        return {i:('available' if key=='actual' and norm(values[i]) in available else key) for i,key in mapping.items()}
    return mapping

def _ge2e_work_order_event_table(headers):
    names={norm(v) for v in headers}
    return bool(names & {norm(v) for v in ['事件ID','非生产事件ID','事件编号']}) and not any(field(v) in {'wo','labor','available','allocated_total','plan_total'} for v in headers)

def _ge2e_order_day_projection(record,headers,values):
    if not any(k in record for k in ['labor','available','nonprod']):return None
    fields={'date','dept','labor','ot','headcount','nonprod','available','plan_total','allocated_total','ot_rate','_loc'}
    day={k:v for k,v in record.items() if k in fields}
    flags=[]
    for header,value in zip(headers,values):
        if norm(header) in {norm(v) for v in ['加班超限','加班工时超限','产线日状态','线日状态']}:
            label=flag_value(value,header)
            if label:flags.append(label)
    if flags:day['flags']='；'.join(dict.fromkeys(flags))
    return day
'''
def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('work_order_table_role_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},manifest['digests']['contract_sha256'])
    if expected is None or frozen!=expected:raise ValueError('WORK_ORDER_TABLE_ROLE_PROFILE_MISMATCH')
    anchor='                mapping={i:column_field(v,order_table) for i,v in enumerate(vals) if column_field(v,order_table)}'
    if current.count(anchor)!=1:raise ValueError('WORK_ORDER_TABLE_ROLE_SOURCE_SPAN')
    effective=current.replace(anchor,anchor+'\n                mapping=_ge2e_work_order_mapping(vals,order_table,mapping)')+HELPER
    replacements=[
        ('                    orders.append(rec)',"                    orders.append(rec)\n                    projected=_ge2e_order_day_projection(rec,headers,vals)\n                    if projected is not None:days.append(projected)"),
        ("                elif rec.get('date') and rec.get('dept') and any(k in rec for k in ('labor','nonprod','available')):days.append(rec)",
         "                elif rec.get('date') and rec.get('dept') and any(k in rec for k in ('labor','nonprod','available')):\n                    if _ge2e_work_order_event_table(headers):texts.append({'at':rec['_loc'],'text':json.dumps({'role':'candidate_event_detail','headers':headers,'values':vals},ensure_ascii=False,default=str)})\n                    else:days.append(rec)"),
        ("    days+= [r for r in orders if any(k in r for k in ('labor','available','nonprod'))]", "    # Order/day display fields were projected by extract; never merge order-level values into day totals.\n    days+= []"),
    ]
    for old,new in replacements:
        if effective.count(old)!=1:raise ValueError('WORK_ORDER_TABLE_GRAIN_SOURCE_SPAN')
        effective=effective.replace(old,new)
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,'task_id':TASK,
        'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_decisions_assigned':False,
        'reason':'仅按明确表头区分工单分摊工时、产线日总量和非生产事件明细。日投影不携带工单数值/工单异常；事件原行完整保留供取证。单独旧可分摊列保持原行为；不比较数值择优，不改任何单元格、原金额/工时公式、对象、异常判据、分母、封顶或90/10。'}
    if prior:receipt['prior_correction']=prior
    return effective,receipt
