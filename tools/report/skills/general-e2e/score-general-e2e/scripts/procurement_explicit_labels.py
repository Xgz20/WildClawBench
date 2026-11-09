"""Recognize explicit procurement labels; never interpret ambiguous totals."""
import hashlib

TASK='02_Office_task_015_procurement_reconciliation'
CONTRACT='64ba6743b737870353efc5aebec923ae82f018b6d8bf36583709b142d5515a34'
SOURCE='7117b998478660abcb33c78c87074e0f0e89b496cfb7beb632e37a61432c979b'
LEGACY_BASE='5dbc6a6431a8dd4c4692e28fbe52051d7599a4038ab5aae347712e6ff4f4d561'
PREVIOUS_BASE='b1f84cb81347e51f0c00f10881fa1c63141e06537687922e2367d0e69cc677f7'
BASE='b2ea6ca9c67a605e6ec95322a9d952d7bf7321488a5507ec3347a25fe79e26e2'
LEGACY_PROFILE='procurement-explicit-order-count-labels/v1'
PREVIOUS_PROFILE='procurement-explicit-order-count-labels/v2'
SECTION_BASE_PROFILE='procurement-explicit-order-count-labels/v3'
PROFILE='procurement-explicit-order-count-labels/v4'
BRIDGE='''

# Exact public synonyms only. Ambiguous matching and grand totals remain unknown.
_ge2e_proc_original_category=category
def category(name,grid):
    if norm(name)==norm('无单入库'):
        return 'orphan'
    return _ge2e_proc_original_category(name,grid)
for _ge2e_proc_key,_ge2e_proc_labels in {
    'qty':['数量差异订单','数量差异订单笔数'],
    'amount':['金额差异订单','金额差异订单笔数'],
    'orphan_amount':['无单入库金额合计'],
}.items():
    SUMMARY_LABELS[_ge2e_proc_key].extend(_ge2e_proc_labels)
'''


# Preserve the workbook's literal subtotal and check it against its own visible operands.
SECTION_BRIDGE=r'''
_ge2e_prior_procurement_matrix_view = _pl_matrix_view
def _pl_matrix_view(tables,records,metrics,numeric,truth,*args):
    converted,expected,locations,audit=_ge2e_prior_procurement_matrix_view(tables,records,metrics,numeric,truth,*args)
    headers=('核对类别','笔数','金额差额（元）','差额方向说明','占比','备注')
    labels=('采购订单总数','入库记录总数','匹配成功订单','数量差异订单','金额差异订单','未入库订单','无对应订单入库')
    for source,view in zip(tables,converted):
        if source['kind']!='summary' or source['sheet']!=view['sheet']:continue
        raw=source['rows']
        for i,head in enumerate(raw):
            if tuple(head['values'])!=headers:continue
            rows=raw[i+1:i+9]
            if len(rows)!=8 or [r['row'] for r in rows]!=list(range(head['row']+1,head['row']+9)):continue
            values=[r['values'] for r in rows]
            if (any(len(v)!=6 for v in values) or tuple(v[0] for v in values[:7])!=labels
                    or values[2][5]!='有对应入库记录的采购订单'
                    or values[-1][0]!='合计' or values[-1][5]!='各类笔数与金额合计'
                    or any(r.get('hidden_columns') for r in [head,*rows])):continue
            counts=[number(v[1]) for v in values[:7]]
            money=[number(v[2]) for v in values[4:7]]
            if (any(n is None or n!=n.to_integral_value() for n in counts)
                    or any(n is None for n in money)
                    or any(values[j][2] is not None for j in range(4))
                    or any(number(values[-1][j]) is not None for j in (3,4))
                    or any(number(values[-1][j]) is None for j in (1,2))):continue
            selected={rows[2]['row'],rows[-1]['row']}
            if any(sum(r['row']==n for r in view['rows'])!=1 for n in selected):continue
            projected=[]
            for source_row,column,key,value in [(rows[2],1,'matched',None),
                    (rows[-1],1,'ps_literal_section_count',sum(counts)),
                    (rows[-1],2,'ps_literal_section_amount',sum(money))]:
                label=f'_ps/{key}/{column}'
                SUMMARY_LABELS.setdefault(key,[]).append(label)
                if value is not None:expected[key]=value
                if column==2:MONEY_KEYS.add(key)
                number_at=source_row['values'][column]
                projected.append({'row':source_row['row'],'values':[label,number_at]})
                loc=source['sheet']+'!'+get_column_letter(column+1)+str(source_row['row'])
                locations[(source['sheet'],source_row['row'],label)]={'value_location':loc,'extraction_profile':'procurement-literal-section-subtotal/v1'}
                audit.append({'location':loc,'subject':key,'field':headers[column],'key':key,
                              'expected_unavailable':False})
            view['rows']=[r for r in view['rows'] if r['row'] not in selected]+projected
    return converted,expected,locations,audit
'''

def marker(contract,contract_sha,*,profile=None):
    profile=PROFILE if profile is None else profile
    bases={LEGACY_PROFILE:LEGACY_BASE,PREVIOUS_PROFILE:PREVIOUS_BASE,SECTION_BASE_PROFILE:BASE,PROFILE:BASE}
    if profile not in bases:return None
    if (contract.get('task_id')==TASK and contract_sha==CONTRACT
        and hashlib.sha256(contract.get('automated_checks','').encode()).hexdigest()==SOURCE):
        return {'profile':profile,'contract_sha256':CONTRACT,'source_sha256':SOURCE,'base_effective_source_sha256':bases[profile]}
    return None

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('procurement_explicit_labels_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest.get('identity',{}).get('task_id'),'automated_checks':original},manifest.get('digests',{}).get('contract_sha256'),profile=frozen.get('profile'))
    if expected is None or frozen!=expected or hashlib.sha256(current.encode()).hexdigest()!=expected['base_effective_source_sha256']:
        raise ValueError('PROCUREMENT_EXPLICIT_LABEL_PROFILE_MISMATCH')
    effective=current+BRIDGE+(SECTION_BRIDGE if frozen["profile"]==PROFILE else "")
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':frozen['profile'],
             'task_id':TASK,'contract_sha256':CONTRACT,'original_source_sha256':SOURCE,
             'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),'candidate_rewritten':False,
             'numeric_decisions_assigned':False,
             'reason':'仅识别无单入库工作表与数量/金额差异订单笔数、无单入库金额合计的明确同义名称；只读取候选原单元格，不补ID、值或参考事实。匹配成功、合计等含义未定汇总继续触发原未决门禁，原数字算法、分母和80/20不变。'}
    if frozen['profile']==PROFILE:
        receipt['reason'] += ' 对明确说明有对应入库记录的匹配订单以及指定汇总区段的逐列字面合计使用原计分组；只比较原单元格和本段操作数，不将重叠计数合计视为独立订单数。'
    if prior:receipt['prior_correction']=prior
    return effective,receipt
