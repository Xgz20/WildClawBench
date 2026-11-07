"""Keep fixed-field deduplication; review dynamic problem labels per object."""
from copy import deepcopy
import hashlib
import escrow_grouped_review as grouped

PROFILE = 'escrow-status-equivalence-review/v4'


def effective_source(manifest, original, current, prior):
    if manifest.get('runtime', {}).get('rule_review_profile') != PROFILE:
        return current, prior
    projection = deepcopy(manifest)
    projection['runtime']['rule_review_profile'] = grouped.PROFILE
    effective, receipt = grouped.effective_source(projection, original, current, prior)
    before = grouped.INDEX
    after = before.replace('    _GE2E_ESCROW_ROWS={}\n',
                           '    _GE2E_ESCROW_ROWS={}\n    from copy import deepcopy as _escrow_snapshot\n')
    after = after.replace(
        '                    _GE2E_ESCROW_GROUPS.setdefault((_table,_field,_literal),set()).add(_location)',
        "                    _key=(_table,_field,_literal)+((_location,) if _field=='问题类别' else ())\n"
        '                    _GE2E_ESCROW_GROUPS.setdefault(_key,set()).add(_location)')
    after = after.replace('_GE2E_ESCROW_ROWS[id(_row)]=(_table,originals)',
                          '_GE2E_ESCROW_ROWS[id(_row)]=(_table,originals,_escrow_snapshot(_row))')
    changes = [
        (before, after),
        ('table,originals=_GE2E_ESCROW_ROWS[id(row)]',
         'table,originals,original_row=_GE2E_ESCROW_ROWS[id(row)]'),
        ('key=(table,field,literal)',
         "key=(table,field,literal)+((original_row['_candidate_location'],) if field=='问题类别' else ())"),
        ('locations=sorted(_GE2E_ESCROW_GROUPS[(table,field,literal)])',
         'locations=sorted(_GE2E_ESCROW_GROUPS[key])'),
        ("'allowed_original_states':sorted(v for v in allowed if v)}",
         "'allowed_original_states':sorted(v for v in allowed if v)}\n"
         "    if field=='问题类别':payload['original_row']=original_row"),
    ]
    for old, new in changes:
        if effective.count(old) != 1:
            raise ValueError('ESCROW_PROBLEM_REVIEW_SOURCE_SPAN_MISMATCH')
        effective = effective.replace(old, new, 1)
    effective = effective.replace(grouped.PROFILE, PROFILE)
    receipt['correction_id'] = PROFILE
    receipt['effective_source_sha256'] = hashlib.sha256(effective.encode()).hexdigest()
    receipt['grouping'] = 'problem-category: logical-table/field/location/full-original-row; other fixed fields: original v3 grouping'
    receipt['reason'] = ('动态问题类别按原对象完整上下文独立复核，避免不同原因强制共享一个词义映射；'
                         '固定语义字段仍按原v3去重并保留全部位置。原始行在任何映射前复制，'
                         '不猜判、不采样、不提高10000上下文上限，不改数值规则、候选或权重。')
    return effective, receipt
