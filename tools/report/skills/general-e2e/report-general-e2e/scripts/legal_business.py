"""Legal business acceptance derived from sealed scores and explicit human reviews."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
import re

STATUSES = {'unreviewed': '待复核', 'none': '已复核无严重错误', 'present': '发现严重错误'}
VERDICTS = {'accepted': '通过', 'pending_review': '待复核', 'serious_error': '严重错误未通过',
            'quality_below_threshold': '质量分未达标', 'unscored': '未评分',
            'execution_incomplete': '执行未完成', 'evaluation_error': '评测异常',
            'not_selected': '未纳入本次运行'}

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def number(value):
    return type(value) in (int, float) and math.isfinite(value)

def validate_policy(policy):
    scope = policy.get('dataset', {})
    tasks, categories = scope.get('tasks', []), scope.get('categories', [])
    if (policy.get('schema_version') != 'wildclawbench.legal-acceptance-policy/v1'
            or not re.fullmatch(r'[0-9a-f]{64}', str(scope.get('digest', '')))
            or len(tasks) != scope.get('task_count') or len({t['task_id'] for t in tasks}) != len(tasks)
            or Counter(t['category'] for t in tasks) != {c['id']: c['task_count'] for c in categories}
            or policy.get('round_policy') != 'all-observed-rounds'
            or not number(policy.get('quality_threshold')) or not 0 <= policy['quality_threshold'] <= 1
            or len(policy.get('metrics', [])) != 7
            or abs(sum(m['weight'] for m in policy['metrics']) - 1) > 1e-9):
        raise ValueError('LEGAL_POLICY_INVALID')

def validate_review(review, policy, policy_sha):
    if review.get('policy_sha256') != policy_sha:
        raise ValueError('LEGAL_REVIEW_POLICY_MISMATCH')
    if (not re.fullmatch(r'[0-9a-f]{64}', str(review.get('score_sha256', '')))
            or review.get('status') not in STATUSES
            or not review.get('execution_attempt_id') or not review.get('scoring_attempt_id')
            or not review.get('task_id')):
        raise ValueError('LEGAL_REVIEW_BINDING_INVALID')
    actor = review.get('reviewer') or {}
    if not actor.get('id') or not isinstance(actor.get('name'), str) or not actor['name'].strip():
        raise ValueError('LEGAL_REVIEW_REVIEWER_REQUIRED')
    try:
        stamp = datetime.fromisoformat(str(review.get('reviewed_at', '')).replace('Z', '+00:00'))
        if stamp.tzinfo is None: raise ValueError()
    except ValueError as error:
        raise ValueError('LEGAL_REVIEW_TIME_INVALID') from error
    errors = review.get('error_types', [])
    evidence = review.get('evidence', [])
    if (not isinstance(errors, list) or any(not isinstance(e, str) for e in errors) or len(errors) != len(set(errors))
            or any(e not in policy['serious_error_types'] for e in errors)
            or review['status'] != 'present' and errors
            or review['status'] == 'present' and not errors):
        raise ValueError('LEGAL_REVIEW_ERROR_TYPES_INVALID')
    if not isinstance(evidence, list) or any(not isinstance(e, dict)
            or not isinstance(e.get('path'), str) or not e['path'].strip()
            or not isinstance(e.get('locator'), str) or not e['locator'].strip() for e in evidence):
        raise ValueError('LEGAL_REVIEW_EVIDENCE_INVALID')
    if review['status'] != 'unreviewed' and not evidence:
        raise ValueError('LEGAL_REVIEW_EVIDENCE_REQUIRED')

def _rounds(row):
    return [child for value in row.get('rounds', []) for child in _rounds(value)] if row.get('rounds') else [row]

def build(data, policy, reviews, labels, policy_sha):
    if not policy or data.get('dataset', {}).get('id') != policy.get('dataset', {}).get('id'):
        if reviews: raise ValueError('LEGAL_REVIEWS_WITHOUT_POLICY')
        return None
    validate_policy(policy)
    if data['dataset'].get('digest') != policy['dataset']['digest']:
        raise ValueError('LEGAL_DATASET_SCOPE_DRIFT')
    scope = policy['dataset']; task_index = {t['task_id']: t for t in scope['tasks']}
    flattened = [child for row in data['tasks'] for child in _rounds(row)]
    bindings = {r.get('lineage', {}).get('score_sha256'): r for r in flattened if r.get('lineage', {}).get('score_sha256')}
    latest = {}
    for review in reviews:
        validate_review(review, policy, policy_sha)
        row = bindings.get(review['score_sha256'])
        if not row or any(review[k] != row.get(k) for k in ('task_id', 'execution_attempt_id', 'scoring_attempt_id')):
            raise ValueError('LEGAL_REVIEW_SOURCE_MISMATCH')
        key = (review['score_sha256'], str(review['reviewer']['id']))
        stamp = datetime.fromisoformat(review['reviewed_at'].replace('Z', '+00:00'))
        previous = datetime.fromisoformat(latest[key]['reviewed_at'].replace('Z', '+00:00')) if key in latest else None
        if previous == stamp and review != latest[key]:
            raise ValueError('LEGAL_REVIEW_CONFLICT')
        if previous is None or stamp > previous: latest[key] = review
    units, cases, categories, metrics = [], [], [], []
    for unit in data['units']:
        uid = unit['unit_id']; source_rows = [r for r in data['tasks'] if r['unit_id'] == uid]
        observed = {r['task_id']: r for r in source_rows}
        if len(observed) != len(source_rows): raise ValueError('LEGAL_DUPLICATE_CASE_RESULT')
        if set(observed) - set(task_index): raise ValueError('LEGAL_TASK_OUTSIDE_SCOPE')
        unit_cases = []
        for task in scope['tasks']:
            row = observed.get(task['task_id']); rounds = _rounds(row) if row else []
            records = [r for child in rounds for (sha, _), r in latest.items()
                       if sha == child.get('lineage', {}).get('score_sha256')]
            states = []
            for child in rounds:
                selected = [r for r in records if r['score_sha256'] == child.get('lineage', {}).get('score_sha256')]
                states.append('present' if any(r['status'] == 'present' for r in selected) else
                              'none' if selected and all(r['status'] == 'none' for r in selected) else 'unreviewed')
            status = 'present' if 'present' in states else 'none' if states and all(s == 'none' for s in states) else 'unreviewed'
            if not row: verdict = 'not_selected'
            elif any(r.get('score_status') == 'evaluation_error' or r.get('execution_status') == 'infrastructure_error' for r in rounds): verdict = 'evaluation_error'
            elif any(r.get('execution_status') != 'completed' for r in rounds): verdict = 'execution_incomplete'
            elif any(r.get('score_status') != 'valid' or not number(r.get('total_score')) for r in rounds): verdict = 'unscored'
            elif status == 'present': verdict = 'serious_error'
            elif any(Decimal(str(r['total_score'])) < Decimal(str(policy['quality_threshold'])) for r in rounds): verdict = 'quality_below_threshold'
            elif status != 'none': verdict = 'pending_review'
            else: verdict = 'accepted'
            values = {}
            for metric in policy['metrics']:
                found = [r.get('checkpoints', {}).get('values', {}).get(metric['key']) if r.get('score_status') == 'valid' else None for r in rounds]
                values[metric['key']] = sum(found) / len(found) if found and all(number(v) for v in found) else None
            roles = {r['reviewer'].get('role') for r in records if r['status'] != 'unreviewed'}
            entry = {'unit_id': uid, **task, 'quality_score': row.get('total_score') if row and row.get('score_status') == 'valid' else None,
                     'acceptance_status': verdict, 'review_status': status, 'round_count': len(rounds),
                     'error_types': sorted({e for r in records if r['status'] == 'present' for e in r['error_types']}),
                     'reviews': records, 'metrics': values,
                     'dual_role_review': len({str(r['reviewer']['id']) for r in records}) >= 2 and {'legal', 'evaluation'} <= roles}
            unit_cases.append(entry);cases.append(entry)
        accepted = sum(c['acceptance_status'] == 'accepted' for c in unit_cases)
        reviewed = sum(c['round_count'] > 0 and c['review_status'] != 'unreviewed' for c in unit_cases)
        critical = sum(c['review_status'] == 'present' for c in unit_cases)
        quality = [c['quality_score'] for c in unit_cases if number(c['quality_score'])]
        group = []
        for category in scope['categories']:
            selected = [c for c in unit_cases if c['category'] == category['id']]
            scores = [c['quality_score'] for c in selected if number(c['quality_score'])]
            passed = sum(c['acceptance_status'] == 'accepted' for c in selected)
            summary = {'unit_id':uid, **category, 'valid_scores':len(scores), 'quality_mean':sum(scores)/len(scores) if scores else None,
                       'quality_min':min(scores) if scores else None, 'accepted':passed, 'acceptance_rate':passed/category['task_count'],
                       'pending_review':sum(c['acceptance_status']=='pending_review' for c in selected),
                       'not_selected':sum(c['acceptance_status']=='not_selected' for c in selected),
                       'serious_errors_known':sum(c['review_status']=='present' for c in selected),
                       'target_met':passed >= policy['category_target']}
            categories.append(summary);group.append(summary)
        units.append({'unit_id':uid,'label':labels.get(uid,uid),'dataset_tasks':scope['task_count'],'selected_tasks':len(observed),
                      'valid_scores':len(quality),'quality_mean':sum(quality)/len(quality) if quality else None,
                      'score_coverage':len(quality)/scope['task_count'],'accepted':accepted,'acceptance_rate':accepted/scope['task_count'],
                      'reviewed_cases':reviewed,'pending_review':sum(c['acceptance_status']=='pending_review' for c in unit_cases),
                      'serious_errors_known':critical,'serious_errors_total':critical if reviewed==scope['task_count'] else None,
                      'serious_error_type_counts':dict(Counter(e for c in unit_cases for e in c['error_types'])),
                      'not_selected':sum(c['acceptance_status']=='not_selected' for c in unit_cases),
                      'dataset_target_met':accepted>=policy['dataset_target'] and all(c['target_met'] for c in group)})
        for metric in policy['metrics']:
            known = [c['metrics'][metric['key']] for c in unit_cases if number(c['metrics'][metric['key']])]
            metrics.append({'unit_id':uid, **metric, 'mean':sum(known)/len(known) if known else None,
                            'known':len(known),'total':scope['task_count']})
    return {'schema_version':'wildclawbench.legal-business-report/v1','policy':policy,'policy_sha256':policy_sha,
            'review_snapshot_sha256':digest(reviews),'units':units,'categories':categories,'metrics':metrics,'cases':cases,
            'scope':{'dataset_tasks':scope['task_count'],'observed_unique_tasks':len({r['task_id'] for r in data['tasks']})},
            'semantics':'质量分保持原值；业务验收按全部冻结用例计分母。未复核不通过，未知严重错误总数为空；多轮逐轮复核；角色为用户声明。'}

def attach(data, presentation, references, table):
    if data.get('resource_round_view'): return presentation
    policy = references.get('legal_acceptance_policy')
    result = build(data, policy, data.get('legal_reviews', []), presentation['unit_labels'],
                   references.get('sources', {}).get('legal_acceptance_policy.json'))
    if result is None:return presentation
    data['legal_business'] = result
    labels = presentation['unit_labels']; pct=lambda v: v*100 if number(v) else None
    note=[policy['notice'],result['semantics'],'覆盖及验收通过率分母来自冻结发布版本30题；不同单元分别统计，不混合排名。',
          '政策SHA256：'+result['policy_sha256']+'；复核快照SHA256：'+result['review_snapshot_sha256']]
    tables = {
      '法律业务验收':table(['单元','质量均分','评分覆盖(N/30)','业务通过数/30','业务通过率(%)','待复核','未纳入本次运行','已复核发现严重错误','严重错误总数(未知显示—)','复核覆盖/30','整集建议目标'],
        [[u['label'],pct(u['quality_mean']),f"{u['valid_scores']}/{u['dataset_tasks']}",f"{u['accepted']}/{u['dataset_tasks']}",pct(u['acceptance_rate']),u['pending_review'],u['not_selected'],u['serious_errors_known'],u['serious_errors_total'],f"{u['reviewed_cases']}/{u['dataset_tasks']}",'达到' if u['dataset_target_met'] else '未达到/未完成'] for u in result['units']], notes=note[:]),
      '法律分类验收':table(['单元','分类','质量均分','最低质量分','评分覆盖','通过数/分类总题数','业务通过率(%)','待复核','未纳入','已复核严重错误','每类建议目标'],
        [[labels[c['unit_id']],c['name'],pct(c['quality_mean']),pct(c['quality_min']),f"{c['valid_scores']}/{c['task_count']}",f"{c['accepted']}/{c['task_count']}",pct(c['acceptance_rate']),c['pending_review'],c['not_selected'],c['serious_errors_known'],'达到' if c['target_met'] else '未达到/未完成'] for c in result['categories']], notes=note[:]),
      '法律七项质量指标':table(['单元','指标','总分占比(%)','指标均分','有效覆盖/30'],
        [[labels[m['unit_id']],m['name'],m['weight']*100,pct(m['mean']),f"{m['known']}/{m['total']}"] for m in result['metrics']],notes=['各指标取原检查点值，缺失保持空，不用总分替代，不重复加权计分。']),
      '法律严重错误复核':table(['单元','分类','用例','质量分','业务验收状态','严重错误复核','严重错误类型','证据定位','复核人/声明角色','复核时间','双角色复核声明'],
        [[labels[c['unit_id']],next(x['name'] for x in policy['dataset']['categories'] if x['id']==c['category']),c['task_id'],pct(c['quality_score']),VERDICTS[c['acceptance_status']],STATUSES[c['review_status']],
          '；'.join(policy['serious_error_types'][e] for e in c['error_types']),
          '\n'.join(e['path']+'：'+e['locator'] for r in c['reviews'] for e in r['evidence']),
          '；'.join(r['reviewer']['name']+'/'+r['reviewer'].get('role','unspecified') for r in c['reviews']),
          '；'.join(r['reviewed_at'] for r in c['reviews']), '完整' if c['dual_role_review'] else '待补充'] for c in result['cases']],notes=note[:])}
    presentation['tables'].update(tables)
    presentation['sheet_order'][1:1]=list(tables)
    return presentation
