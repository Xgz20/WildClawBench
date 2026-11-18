"""Read explicit Office015 count labels and signed subtotals in the frozen v6 rules."""

import hashlib

import procurement_annotation_formula as annotation
import procurement_explicit_labels as labels

PROFILE = 'procurement-explicit-signed-summary/v1'


def marker(contract, contract_sha, dataset):
    if any(dataset.get(key) != value for key, value in annotation.DATASET.items()):
        return None
    if labels.marker(contract, contract_sha) is None:
        return None
    return {'profile': PROFILE, 'contract_sha256': labels.CONTRACT,
            'source_sha256': labels.SOURCE, 'base_effective_source_sha256': annotation.BASE}


BRIDGE = r'''

_pss_counts = {
    '已匹配订单笔数': 'matched',
    '匹配且数量、金额均一致笔数': 'clean',
    '其中：仅金额差异笔数': 'price_only',
    '其中：数量与金额同时差异笔数': 'both',
    '无对应订单的入库笔数': 'orphan',
    '无对应订单的入库金额合计': 'orphan_amount',
}
_pss_subtotals = {
    '数量差异合计(入库-采购)': ('正为多入、负为少入，单位：件', 'pss_quantity_net'),
    '金额正差异合计(多入)': ('入库金额>采购金额的部分合计', 'pss_amount_positive'),
    '金额负差异合计(少入)': ('入库金额<采购金额的部分合计', 'pss_amount_negative'),
}
MONEY_KEYS.update({'pss_amount_positive', 'pss_amount_negative'})

class _PssClaim(str):
    def __new__(cls, label, key):
        claim = super().__new__(cls, label)
        claim.key = key
        return claim

_pss_previous_summary_key = summary_key
def summary_key(value):
    if isinstance(value, _PssClaim):
        return value.key
    return _pss_previous_summary_key(value)

def _pss_deltas(records, numeric, truth, kind, field):
    rows = records[kind]
    if len(rows) != len(truth[kind]) or {row['id'] for row in rows} != set(truth[kind]):
        return None
    values = [number(row['values'].get(field)) for row in rows]
    if any(value is None for value in values):
        return None
    direction = numeric['categories'][kind]['direction']
    return [direction * value for value in values]

_pss_previous_view = _pl_matrix_view
def _pl_matrix_view(tables, records, metrics, numeric, truth, *args):
    converted, expected, locations, audit = _pss_previous_view(tables, records, metrics, numeric, truth, *args)
    for index, table in enumerate(converted):
        if table['kind'] != 'summary':
            continue
        rows = table['rows']
        headings = [row for row in rows if tuple(row['values']) == ('指标', '数值', '口径 / 核对说明')]
        if len(headings) != 1 or headings[0].get('hidden_columns'):
            continue
        quantity = _pss_deltas(records, numeric, truth, 'qty', 'dq')
        money = _pss_deltas(records, numeric, truth, 'amount', 'da')
        totals = {
            'pss_quantity_net': None if quantity is None else sum(quantity, Decimal(0)),
            'pss_amount_positive': None if money is None else sum((value for value in money if value > 0), Decimal(0)),
            'pss_amount_negative': None if money is None else sum((value for value in money if value < 0), Decimal(0)),
        }
        projected = []
        for row in rows:
            values = row['values']
            if row['row'] <= headings[0]['row'] or len(values) != 3 or number(values[1]) is None or number(values[2]) is not None:
                projected.append(row)
                continue
            label, value, note = values
            key = _pss_counts.get(label)
            if label in _pss_subtotals and note == _pss_subtotals[label][0]:
                key = _pss_subtotals[label][1]
                expected[key] = totals[key]
            if key is None:
                projected.append(row)
                continue
            projected.append({**row, 'values': [_PssClaim(label, key), value]})
            location = table['sheet'] + '!B' + str(row['row'])
            locations[(table['sheet'], row['row'], label)] = {'value_location': location}
            audit.append({'location': location, 'key': key, 'label': label,
                          'profile': 'procurement-explicit-signed-summary/v1'})
        converted[index] = {**table, 'rows': projected}
    return converted, expected, locations, audit
'''


def effective_source(manifest, original, current, prior):
    frozen = manifest.get('runtime', {}).get('procurement_signed_summary_profile')
    if frozen is None:
        return current, prior
    contract = {'task_id': manifest['identity']['task_id'], 'automated_checks': original}
    expected = marker(contract, manifest['digests']['contract_sha256'], manifest['dataset'])
    base = prior or {}
    if base.get('correction_id') == annotation.PROFILE:
        base = base.get('prior_correction', {})
    if (frozen != expected or base.get('correction_id') != labels.PROFILE
            or base.get('effective_source_sha256') != annotation.BASE
            or hashlib.sha256(current.encode()).hexdigest() != (prior or {}).get('effective_source_sha256')):
        raise ValueError('PROCUREMENT_SIGNED_SUMMARY_PROFILE_MISMATCH')
    effective = current + BRIDGE
    receipt = {
        'schema_version': 'wildclawbench.general-e2e-rule-source-correction/v1',
        'correction_id': PROFILE, 'task_id': labels.TASK,
        'contract_sha256': labels.CONTRACT, 'original_source_sha256': labels.SOURCE,
        'effective_source_sha256': hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten': False, 'numeric_decisions_assigned': False,
        'rubric_and_weights_changed': False, 'prior_correction': prior,
        'reason': '从明确的汇总表头和原单元格读取计数、数量净差及金额正负小计，沿原汇总计分分组和容差比较，未识别的数字仍阻断。',
    }
    return effective, receipt
