"""Display-only decimal rounding consistent with Excel numeric formats."""

from decimal import Decimal, ROUND_HALF_UP, localcontext
from collections import Counter
import math


def fixed_number(value, digits=2, *, grouping=False, multiplier=1):
    number = Decimal(str(value)) * multiplier
    with localcontext() as context:
        context.prec = max(28, number.adjusted() + digits + 2)
        quantum = Decimal(1).scaleb(-digits)
        if isinstance(value, float) and math.isfinite(value):
            # Aggregation can put an exact decimal half-tie one or two binary
            # ULPs below its boundary (86.525 -> 86.52499999999999). Correct
            # only that machine-precision ambiguity for display. Explicit
            # Decimal/string inputs and materially sub-boundary values remain
            # exact, and the stored score/resource values are never changed.
            half = quantum / 2
            steps = (number / half).to_integral_value(rounding=ROUND_HALF_UP)
            boundary = steps * half
            tolerance = Decimal(str(math.ulp(value))) * abs(multiplier) * 2
            if steps % 2 and abs(number - boundary) <= tolerance:
                number = boundary
        rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
    return format(rounded, f"{',' if grouping else ''}.{digits}f")


def apply_pending_review(data, presentation):
    """Explicit display alias for null evaluation errors; never change a score."""
    declared = data.get('display_overrides', {}).get('pending_review', [])
    if not declared:
        return presentation
    if not isinstance(declared, list):
        raise ValueError('REPORT_PENDING_REVIEW_CONFIG_INVALID')
    selected = {}
    for entry in declared:
        if (not isinstance(entry, dict) or not isinstance(entry.get('task_id'), str)
                or not isinstance(entry.get('reason'), str) or not entry['reason'].strip()):
            raise ValueError('REPORT_PENDING_REVIEW_CONFIG_INVALID')
        matches = [row for row in data['tasks'] if row['task_id'] == entry['task_id']
                   and (entry.get('unit_id') is None or row['unit_id'] == entry['unit_id'])]
        if not matches:
            raise ValueError('REPORT_PENDING_REVIEW_TASK_UNKNOWN')
        for row in matches:
            key = (row['unit_id'], row['task_id'])
            if key in selected:
                raise ValueError('REPORT_PENDING_REVIEW_DUPLICATE')
            if (row['score_status'] != 'evaluation_error' or row['total_score'] is not None
                    or row['execution_status'] != 'completed'):
                raise ValueError('REPORT_PENDING_REVIEW_REQUIRES_COMPLETED_NULL_ERROR')
            selected[key] = entry['reason'].strip()
    counts = Counter(row['score_status'] for row in data['tasks'])
    valid_zero = sum(row['score_status'] == 'valid' and row['total_score'] == 0 for row in data['tasks'])
    other_errors = counts['evaluation_error'] - len(selected)
    coverage = presentation['score_coverage']
    old_note = coverage['note']
    coverage.update(pending_review_count=len(selected), pending_review=[
        {'unit_id': unit, 'task_id': task, 'reason': reason, 'source_score_status': 'evaluation_error'}
        for (unit, task), reason in sorted(selected.items())])
    coverage['note'] = (f"本版保留{len(data['tasks'])}项任务运行：{counts['valid']}项有效、{len(selected)}项待核验、"
                        f"{other_errors}项其他评测异常、{counts['unscored']}项未评分。"
                        f"均分仅使用有效成绩，包含{valid_zero}项真实零分；待核验项总分保留空值，不补零、不进入均分。")
    if not coverage.get('valid_task_sets_identical', True):
        coverage['note'] += '各单元有效题目子集不同，不作完整评测集排名。'
    overview = presentation['tables']['总览']
    overview['notes'] = [coverage['note'] if note == old_note else note for note in overview['notes']]
    anomaly_index = overview['headers'].index('评测异常数')
    if other_errors == 0 and not any(row['execution_status'] == 'infrastructure_error' for row in data['tasks']):
        overview['headers'][anomaly_index] = '待核验数'
    else:
        overview['headers'][anomaly_index] = '评测异常/待核验数'
    comparison = presentation['case_comparison']
    for (unit, task), reason in selected.items():
        label = presentation['unit_labels'][unit]
        note = f'待核验：{task}；{reason}。总分保留空值，不补零。'
        overview['notes'].append(note)
        comparison['notes'].append(note)
        column = comparison['headers'].index(label + ' 得分')
        for row in comparison['rows']:
            if row[1] == task and isinstance(row[column], str):
                row[column] = row[column].replace('（evaluation_error）', '（待核验）')
        sheet = presentation['score_details'][presentation['score_detail_sheet_names'][unit]]
        status = sheet['headers'].index('评分状态')
        for row in sheet['rows']:
            if row[1] == task:
                if row[sheet['headers'].index('总得分')] is not None:
                    raise ValueError('REPORT_PENDING_REVIEW_NON_NULL_PRESENTATION')
                row[status] = '待核验（' + reason + '）'
        sheet['notes'].insert(0, note)
    return presentation
