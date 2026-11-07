"""Group repeated status wording, preserving every original occurrence location."""
from copy import deepcopy
import hashlib
import escrow_state_review as v1
import escrow_grouped_review_v2 as v2

PROFILE='escrow-status-equivalence-review/v3'
ERROR_KIND='declared-review-discovery-context-limit-repair/v1'

def matches(contract,contract_sha=None):return v1.matches(contract,contract_sha)

INDEX=r'''
    global _GE2E_ESCROW_GROUPS, _GE2E_ESCROW_REVIEWED, _GE2E_ESCROW_ROWS
    _GE2E_ESCROW_GROUPS={}
    _GE2E_ESCROW_REVIEWED={}
    _GE2E_ESCROW_ROWS={}
    for _table,_rows in actual.items():
        for _row in _rows:
            originals={}
            for _field in STATE_FIELDS.intersection(_row):
                _literal=normalized(_row[_field])
                if _literal and _literal not in known_states[_field]:
                    _location=_row.get('_candidate_location')
                    if not _location:raise RuntimeError('RULE_REVIEW_STATUS_LOCATION_MISSING')
                    originals[_field]=_literal
                    _GE2E_ESCROW_GROUPS.setdefault((_table,_field,_literal),set()).add(_location)
            _GE2E_ESCROW_ROWS[id(_row)]=(_table,originals)
'''

def effective_source(manifest,original,current,prior):
    import escrow_problem_review
    if manifest.get('runtime',{}).get('rule_review_profile')==escrow_problem_review.PROFILE:
        return escrow_problem_review.effective_source(manifest,original,current,prior)
    if manifest.get('runtime',{}).get('rule_review_profile')==v2.PROFILE:
        return v2.effective_source(manifest,original,current,prior)
    if manifest.get('runtime',{}).get('rule_review_profile')!=PROFILE:return current,prior
    projection=deepcopy(manifest);projection['runtime']['rule_review_profile']=v1.PROFILE
    effective,receipt=v1.effective_source(projection,original,current,prior)
    anchor="    known_states={field:{normalized(row.get(field)) for rows in expected.values() for row in rows if field in row} for field in STATE_FIELDS}"
    old="    payload={'field':field,'original_row':row,'allowed_original_states':sorted(v for v in allowed if v)}"
    new="""    table,originals=_GE2E_ESCROW_ROWS[id(row)]
    literal=originals[field]
    key=(table,field,literal)
    if key in _GE2E_ESCROW_REVIEWED:
        choice=_GE2E_ESCROW_REVIEWED[key]
        return row[field] if choice=='__keep_literal_known_distinct__' else choice
    locations=sorted(_GE2E_ESCROW_GROUPS[(table,field,literal)])
    payload={'field':field,'table':table,'original_literal':literal,
        'all_occurrence_locations':locations,'occurrences_complete':True,
        'allowed_original_states':sorted(v for v in allowed if v)}"""
    if effective.count(anchor)!=1 or effective.count(old)!=1:raise ValueError('ESCROW_GROUPED_REVIEW_SOURCE_SPAN_MISMATCH')
    effective=effective.replace(anchor,anchor+INDEX).replace(old,new).replace(v1.PROFILE,PROFILE)
    effective=effective.replace("    if state.get('mode')=='discover':return row[field]",
        "    if state.get('mode')=='discover':\n        _GE2E_ESCROW_REVIEWED[key]='__keep_literal_known_distinct__'\n        return row[field]")
    effective=effective.replace("    return row[field] if selected[0]=='__keep_literal_known_distinct__' else selected[0]",
        "    _GE2E_ESCROW_REVIEWED[key]=selected[0]\n    return row[field] if selected[0]=='__keep_literal_known_distinct__' else selected[0]")
    receipt['correction_id']=PROFILE;receipt['effective_source_sha256']=hashlib.sha256(effective.encode()).hexdigest()
    receipt['grouping']='logical-table/field/original-literal; all locations retained without sampling'
    receipt['reason']='只对同逻辑表同字段同原词去重复核，保留完整原始出现位置；独立裁判须覆盖全部使用，歧义保留null，原比较、原值、分母及权重不变，10000资源上限不提高。'
    return effective,receipt

def validate_choices(request,decisions):return v1.validate_choices(request,decisions)
