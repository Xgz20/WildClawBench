"""Field-scoped display equivalence; no relaxation of business values or ranges."""
import hashlib

PROFILE = 'data-table-field-representations/v1'
DATASET = {'id': 'general-custom116-v1', 'digest': '8a066c60dfb1b45403b5b792f9cd6264a5ee639e9cd263b8dc0acfc2031dcb01'}
REGISTRY = {
    '03_Data_Analysis_task_008_payment_channel_settlement_reserves': (
        'd24c2f9152a4d3a4ba182c6f2321f46563343aeafa05b2365250b5334d2ad119',
        '8792b29a8de3c4d0421e9307a70ada938b71b5ee71d57d4d20015fe18cbfce0e', 'voucher'),
    '03_Data_Analysis_task_011_new_customer_purchase_funnel_retention': (
        '50e3fb1e71018debf5fa997dbe265698f6416b1f0fc95fc18a9915e6340b17da',
        '4b3597be18542b845df74d74fc35894c757986a6f6ba31ad25140b5dd519731c', 'date'),
    '03_Data_Analysis_task_012_learning_product_activation_retention': (
        'e063747f5444ee7c608320f9009addabcf24891a96ba376c173bd3c8dd24caea',
        '4b3597be18542b845df74d74fc35894c757986a6f6ba31ad25140b5dd519731c', 'learning_steps'),
    '03_Data_Analysis_task_014_ecommerce_multitouch_attribution_refund_roi': (
        '67b32ce66d7c41d56a7ca7adcbd5f2232487f481215f356258eceb40f6dd7a20',
        '11aeb5b4a953a0c3d85bd77ff7d0c744c621f33db0782b5671534f3650a12853', 'attribution'),
    '03_Data_Analysis_task_015_b2b_long_cycle_conversion_mature_cohorts': (
        '091bd036cb90cc65cd4a01a8f85ecdb1ec3f3c856866b1833ecf92b008cbc7f3',
        'f52f9a1b6dcc14cb7c84251f55f64cd3fd9fc9153d91dd2a4be0fe9e443ffebb', 'attribution'),
    '03_Data_Analysis_task_016_store_campaign_cost_allocation_comparability': (
        '403c92931dc9df259068ba721d0b226580868ae41fd09c928abe756d06f7c3c8',
        'aae6017d35b3207d4afffdf1554d175527729465acbdea35f7c7312e7967f350', 'redemption'),
}
HELPER = '''

def _ge2e_field_representation(a,b,field):
    if _GE2E_REPRESENTATION_KIND=='learning_steps' and field=='步骤名称':
        aliases={'有效学习':'学习','测验通过':'测验'}
        if str(a).strip() in aliases:return aliases[str(a).strip()]==str(b).strip()
    if _GE2E_REPRESENTATION_KIND=='voucher' and field=='凭证状态' and str(a).strip()=='已核凭证':
        return str(b).strip()=='已提供'
    if _GE2E_REPRESENTATION_KIND=='date' and field=='起点日期':
        from datetime import date,datetime,timedelta
        if not isinstance(b,str) or not re.fullmatch(r'\\d{4}-\\d{2}-\\d{2}',b):return None
        try:
            value=a if isinstance(a,(date,datetime)) else datetime.fromisoformat(str(a).strip())
            if isinstance(value,datetime):
                if value.tzinfo is not None and value.utcoffset()!=timedelta(hours=8):return None
                value=value.date()
            return value.isoformat()==b
        except (TypeError,ValueError):return None
    if field=='归因状态' and _GE2E_REPRESENTATION_KIND in {'attribution','redemption'}:
        aliases={'已归因':'触点归因'}
        if _GE2E_REPRESENTATION_KIND=='redemption':aliases['核销渠道']='核销码优先'
        if str(a).strip() in aliases:return aliases[str(a).strip()]==str(b).strip()
    return None
'''


def marker(contract, contract_sha, dataset):
    task = contract.get('task_id')
    entry = REGISTRY.get(task)
    if (entry and contract_sha == entry[0] and {key: dataset.get(key) for key in DATASET} == DATASET
            and hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest() == entry[1]):
        return {'profile': PROFILE, 'contract_sha256': entry[0], 'source_sha256': entry[1], 'kind': entry[2]}
    return None


def effective_source(manifest, original, current, prior):
    frozen = manifest.get('runtime', {}).get('data_table_representation_profile')
    if frozen is None:
        return current, prior
    task = manifest['identity']['task_id']
    expected = marker({'task_id': task, 'automated_checks': original}, manifest['digests']['contract_sha256'], manifest['dataset'])
    if expected is None or frozen != expected:
        raise ValueError('DATA_TABLE_REPRESENTATION_PROFILE_MISMATCH')
    if expected['kind'] == 'voucher':
        replacements = [('                    ok=field in ar and cmp(ar.get(field),er[field])',
            "                    represented=_ge2e_field_representation(ar.get(field),er[field],field) if cmp is same else None\n                    ok=field in ar and (represented if represented is not None else cmp(ar.get(field),er[field]))")]
    elif expected['kind'] in ('date', 'learning_steps'):
        replacements = [
            ('def eq(a,b):', "def eq(a,b,field=''):\n    represented=_ge2e_field_representation(a,b,field)\n    if represented is not None:return represented"),
            ('].get(f),r[f]) for f in fields)', '].get(f),r[f],f) for f in fields)'),
            ('eq(rr[0].get(f),r[f])', 'eq(rr[0].get(f),r[f],f)'),
        ]
    else:
        replacements = [('def equal(a,b,field=\'\'):', "def equal(a,b,field=''):\n    represented=_ge2e_field_representation(a,b,field)\n    if represented is not None:return represented")]
    effective = current
    for old, new in replacements:
        if effective.count(old) != 1:
            raise ValueError('DATA_TABLE_REPRESENTATION_SOURCE_MISMATCH')
        effective = effective.replace(old, new)
    effective += '\nimport re\n_GE2E_REPRESENTATION_KIND = ' + repr(expected['kind']) + '\n' + HELPER
    receipt = {'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1', 'correction_id': PROFILE,
        'task_id': task, 'contract_sha256': expected['contract_sha256'], 'original_source_sha256': expected['source_sha256'],
        'effective_source_sha256': hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten': False, 'numeric_decisions_assigned': False,
        'reason': '仅在起点日期列接受同一北京时间日期的有效日期/时间表示；学习题步骤名称接受公开口径的有效学习、测验通过；仅在归因状态列识别已归因=触点归因及核销渠道=核销码优先；仅在凭证状态列识别已核凭证=已提供。未知归因不与缺客户编号/无合格触点合并，达成不与完整观察合并；原范围、逐行比较、数值精度、缺口、原分档及权重不变。'}
    if prior:
        receipt['prior_correction'] = prior
    return effective, receipt
