"""Source-bound warranty table transport repair; business decisions stay original."""
from __future__ import annotations

import hashlib

TASK = '02_Office_task_010_warranty_recovery_allocation'
CONTRACT_SHA = '40d185a0f2261364dcf5b16ad49f675757e565bc77422a5de57291ed0bf5d661'
SOURCE_SHA = '34482414d200065795ccb168971c9c9c25ae80999be0cd926b2e0aa3bef48c1b'
DATASET = {'id': 'general-custom116-v1', 'digest': '8a066c60dfb1b45403b5b792f9cd6264a5ee639e9cd263b8dc0acfc2031dcb01'}
PROFILE = 'warranty-recovery-equivalent-headings/v1'

REPLACEMENTS = (
    (" 'ratio':['责任比例'", " 'ratio':['政策责任比例','责任比例'"),
    (" 'already':['已追偿金额'", " 'already':['已追偿','已追偿金额'"),
    (" 'current':['本次可追偿金额'", " 'current':['本次金额','本次可追偿金额'"),
    (" 'note':['分摊说明'", " 'note':['分摊及合同依据说明','分摊说明'"),
    (" 'review':['不可追偿或待核查'", " 'review':['待核查事项','不可追偿或待核查'"),
    ("                if key and key not in cols:cols[key]=c",
     "                if key and (key not in cols or (key=='cost' and _warranty_allocated_cost_header(raw) and not _warranty_allocated_cost_header(cells.cell(ws.title,ws.cell(ri,cols[key]).coordinate)))):cols[key]=c"),
)
HELPER = '''

def _warranty_allocated_cost_header(value):
    # Raw repair cost and allocated supplier cost may coexist. Only an explicit
    # allocated heading takes precedence; never substitute a private oracle value.
    name=re.sub(r'(?:人民币元|元)$', '', norm(value))
    return name in {'分摊维修成本','分摊成本','供应商维修成本'}
'''


def marker(contract, contract_sha, dataset):
    if (contract.get('task_id') == TASK and contract_sha == CONTRACT_SHA
            and {key: dataset.get(key) for key in DATASET} == DATASET
            and hashlib.sha256(contract.get('automated_checks', '').encode()).hexdigest() == SOURCE_SHA):
        return {'profile': PROFILE, 'contract_sha256': CONTRACT_SHA, 'source_sha256': SOURCE_SHA}
    return None


def effective_source(manifest, original, current, prior):
    frozen = manifest.get('runtime', {}).get('warranty_recovery_layout_profile')
    if frozen is None:
        return current, prior
    expected = marker({'task_id': manifest['identity']['task_id'], 'automated_checks': original},
                      manifest['digests']['contract_sha256'], manifest['dataset'])
    if expected is None or frozen != expected or current != original:
        raise ValueError('WARRANTY_LAYOUT_PROFILE_MISMATCH')
    effective = current
    for old, new in REPLACEMENTS:
        if effective.count(old) != 1:
            raise ValueError('WARRANTY_LAYOUT_SOURCE_MISMATCH')
        effective = effective.replace(old, new)
    effective += HELPER
    receipt = {
        'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1',
        'correction_id': PROFILE, 'task_id': TASK, 'contract_sha256': CONTRACT_SHA,
        'original_source_sha256': SOURCE_SHA,
        'effective_source_sha256': hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten': False, 'numeric_decisions_assigned': False,
        'reason': '识别公开允许的本次金额、政策责任比例、已追偿及完整依据表头；同表同时含维修原成本和明确分摊成本时优先读取分摊成本。保留原公式求值、对象范围、责任资格、金额、汇总比较、分母、严重错误限分及87/13权重，不代填任何业务值。',
    }
    if prior:
        receipt['prior_correction'] = prior
    return effective, receipt
