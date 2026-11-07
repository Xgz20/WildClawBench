"""Complete the original declared unknown/not-applicable wording review."""
from copy import deepcopy
import hashlib
import escrow_problem_review as problem

PROFILE = 'escrow-status-equivalence-review/v5'
HELPER = r'''
def _ge2e_escrow_marker(table,field,row,want):
    original_table,originals,original_row=_GE2E_ESCROW_ROWS[id(row)]
    if original_table!=table:raise RuntimeError('RULE_REVIEW_MARKER_ROW_IDENTITY_INVALID')
    return _rr_decide({'kind':'escrow-unknown-marker-equivalence','table':table,'field':field,
        'original_row':original_row,'candidate_value':original_row.get(field),
        'expected_original_marker':normalized(want),
        'instruction':'Decide only whether this original candidate field explicitly expresses the stated unknown/not-applicable marker. Do not infer the answer from GT facts or replace candidate content. A mixed statement about another amount does not itself resolve this field; ambiguous wording remains unresolved.'})
'''


def effective_source(manifest, original, current, prior):
    if manifest.get('runtime', {}).get('rule_review_profile') != PROFILE:
        return current, prior
    projection = deepcopy(manifest)
    projection['runtime']['rule_review_profile'] = problem.PROFILE
    effective, receipt = problem.effective_source(projection, original, current, prior)
    old = "                        diagnostic['review_required'].append(f'非数值标记可能等价：{name}/{field}={value}；需按公开语义复核')"
    if effective.count(old) != 1:
        raise ValueError('ESCROW_MARKER_REVIEW_SOURCE_SPAN_MISMATCH')
    effective = effective.replace(old, '                        ok=_ge2e_escrow_marker(name,field,row,want)', 1)
    effective = effective.replace(problem.PROFILE, PROFILE) + HELPER
    receipt['correction_id'] = PROFILE
    receipt['effective_source_sha256'] = hashlib.sha256(effective.encode()).hexdigest()
    receipt['reason'] += ' 同时把原规则明确声明的非数值未知/不适用用语交独立裁判按原对象复核；不把参考事实补给候选，不改变原比较或权重。'
    return effective, receipt
