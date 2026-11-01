"""Explicit current-period metric labels and leading list bullets in Office002."""
import hashlib

TASK = '02_Office_task_002_html_report_quadrant_ppt'
CONTRACT_SHA = '7500a0ecb8e3071b25880b74b0464b2fbe5c805fc730caa8f9ce2e1d4df1fad3'
SOURCE_SHA = '9be11b175636ff50b7d2a1b588665c4f2c0c4e9a787d4d2a4ebee81846cec958'
DATASET = {'id': 'general-custom116-v1', 'digest': '8a066c60dfb1b45403b5b792f9cd6264a5ee639e9cd263b8dc0acfc2031dcb01'}
PROFILE = 'quadrant-current-metric-labels/v1'
REPLACEMENTS = (
    ("    return re.sub(r'(?<=\\d),(?=\\d{3}(?:\\D|$))', '', norm(text))",
     "    return re.sub(r'(?m)^\\s*[●•▪◦]\\s*', '', re.sub(r'(?<=\\d),(?=\\d{3}(?:\\D|$))', '', norm(text)))"),
    ("        reverse = re.fullmatch(r'\\s*('+QUANTITY+r')\\s*[:：=、/\\-—]*\\s*', before)",
     "        reverse = re.fullmatch(r'\\s*('+QUANTITY+r')\\s*(?:(?:本季度|本季|本期|当前)\\s*)?[:：=、/\\-—]*\\s*', before)"),
    ("r'(?:预算执行率|执行率|已支付(?:比例|占比)?)'",
     "r'(?:预算执行率|执行率|已支付(?:比例|占比)?|已执行预算)'"),
    ("('Q3', 'commit', r'(?:已)?承诺(?:资金)?(?:占比|比例|率)', 74, 'percent')",
     "('Q3', 'commit', r'(?:(?:已)?承诺(?:资金)?(?:占比|比例|率)|已承诺未(?:全额)?支付)', 74, 'percent')"),
)


def marker(contract, contract_sha, dataset):
    if (contract.get('task_id') == TASK and contract_sha == CONTRACT_SHA
            and {key: dataset.get(key) for key in DATASET} == DATASET
            and hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest() == SOURCE_SHA):
        return {'profile': PROFILE, 'contract_sha256': CONTRACT_SHA, 'source_sha256': SOURCE_SHA}
    return None


def effective_source(manifest, original, current, prior):
    frozen = manifest.get('runtime', {}).get('quadrant_metric_layout_profile')
    if frozen is None:
        return current, prior
    expected = marker({'task_id': manifest['identity']['task_id'], 'automated_checks': original},
                      manifest['digests']['contract_sha256'], manifest['dataset'])
    if expected is None or frozen != expected:
        raise ValueError('QUADRANT_METRIC_LAYOUT_PROFILE_MISMATCH')
    effective = current
    for old, new in REPLACEMENTS:
        if effective.count(old) != 1:
            raise ValueError('QUADRANT_METRIC_LAYOUT_SOURCE_MISMATCH')
        effective = effective.replace(old, new)
    receipt = {'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1', 'correction_id': PROFILE,
        'task_id': TASK, 'contract_sha256': CONTRACT_SHA, 'original_source_sha256': SOURCE_SHA,
        'effective_source_sha256': hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten': False, 'numeric_decisions_assigned': False,
        'reason': '仅去除行首圆点列表符号，接受数值与指标间的本季/本期等当前限定和已执行预算、已承诺未支付等明确标签；原局部数值绑定、上期/目标/预测排除、单位/时期、可见性、真实数值、区域分配与权重均不变。'}
    if prior:
        receipt['prior_correction'] = prior
    return effective, receipt
