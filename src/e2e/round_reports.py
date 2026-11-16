"""Derived case-first multi-round views; frozen per-round rows remain authoritative."""
from collections import Counter, defaultdict
import copy
import math


def _mean(values):
    values = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)]
    return sum(values) / len(values) if values else None


def _sum_metric(observations):
    known = [row.get('known_subtotal') for row in observations if row.get('known_subtotal') is not None]
    complete = bool(observations) and all(row.get('complete') for row in observations)
    totals = [row.get('coverage', {}).get('total') for row in observations]
    return {'value': sum(row['value'] for row in observations) if complete else None,
        'known_subtotal': sum(known) if known else None, 'complete': complete,
        'status': 'complete' if complete else 'partial' if known else 'unavailable',
        'coverage': {'known': sum(row.get('coverage', {}).get('known', 0) for row in observations),
                     'total': sum(totals) if all(value is not None for value in totals) else None,
                     'unit': observations[0].get('coverage', {}).get('unit', 'unknown') if observations else 'unknown'}}


def aggregate_case(rounds, unit_id):
    row = copy.deepcopy(rounds[0])
    valid = [value for value in rounds if value['score_status'] == 'valid' and _mean([value.get('total_score')]) is not None]
    row.update(unit_id=unit_id, run_id=unit_id + '::' + row['task_id'], rounds=copy.deepcopy(rounds),
        total_score=_mean([value['total_score'] for value in valid]),
        score_status='valid' if valid else 'evaluation_error' if any(value['score_status'] == 'evaluation_error' for value in rounds) else 'unscored',
        round_coverage={'total': len(rounds), 'valid': len(valid),
            'evaluation_error': sum(value['score_status'] == 'evaluation_error' for value in rounds),
            'unscored': sum(value['score_status'] == 'unscored' for value in rounds)},
        scoring_attempt_id=None, execution_attempt_id=None)
    row['execution_status'] = next((value['execution_status'] for value in rounds if value['execution_status'] != 'completed'), 'completed')
    row['evidence_completeness'] = 'complete' if all(value.get('evidence_completeness') == 'complete' for value in rounds) else 'partial'
    models = {value.get('model', {}).get('actual_id') for value in rounds if not value.get('lineage', {}).get('execution_not_dispatched')}
    if len(models) != 1 or None in models:
        row['model'] = {**row['model'], 'actual_id': None, 'verification_status': 'unavailable'}
    row['resource'] = {key: _sum_metric([value['resource'][key] for value in rounds]) for key in row['resource']}
    tools = Counter()
    for value in rounds:
        tools.update(value.get('tool_calls', {}).get('by_tool', {}))
    row['tool_calls'] = {'status': 'complete' if all(value.get('tool_calls', {}).get('status') == 'complete' for value in rounds) else 'partial',
        'total': sum(value['tool_calls']['total'] for value in rounds) if all(value.get('tool_calls', {}).get('total') is not None for value in rounds) else None,
        'by_tool': dict(tools)}
    points = defaultdict(list)
    for value in valid:
        for key, score in value.get('checkpoints', {}).get('values', {}).items():
            points[key].append(score)
    row['checkpoints'] = {'values': {key: _mean(values) for key, values in points.items()}, 'sources': [],
        'aggregation': 'valid-round-mean', 'round_source_count': len(rounds)}
    row['lineage'] = {'source_batch_id': row['lineage'].get('source_batch_id'), 'source_unit_id': row['lineage'].get('source_unit_id'),
        'score_operation_id': row['lineage'].get('score_operation_id'), 'round_aggregation': 'case-valid-rounds/v1',
        'execution_attempt_ids': [value.get('execution_attempt_id') for value in rounds],
        'scoring_attempt_ids': [value.get('scoring_attempt_id') for value in rounds],
        'execution_not_dispatched': all(value.get('lineage', {}).get('execution_not_dispatched') for value in rounds)}
    return row


def _labels(value, replacements):
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [_labels(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _labels(item, replacements) for key, item in value.items()}
    return value


def group_round_report(core, data):
    """Keep round observations separate from equal-weight case scores and physical resources."""
    from .common import digest
    grouped, raw_rows, grouped_units = defaultdict(list), [], []
    for unit in data['units']:
        source = unit['source']
        key = (str(source['score_operation_id']), source['unit_id'])
        grouped[key].append(unit)
    cases = []
    for (score_id, source_unit), units in grouped.items():
        target_id = 's' + score_id + '-u' + digest(source_unit)[:16]
        round_rows = []
        for unit in units:
            for original in data['tasks']:
                if original['unit_id'] == unit['unit_id']:
                    row = copy.deepcopy(original)
                    row.update(unit_id=target_id, run_index=unit['source']['run_index'],
                               run_id=target_id + '::r' + str(unit['source']['run_index']) + '::' + original['task_id'])
                    round_rows.append(row)
        by_case = defaultdict(list)
        for row in round_rows:
            by_case[row['task_id']].append(row)
        unit_cases = [aggregate_case(sorted(values, key=lambda row: row['run_index']), target_id) for values in by_case.values()]
        summary = core.unit_summary(unit_cases, {**units[0], 'unit_id': target_id})
        summary.update(scorer=units[0]['scorer'], source={**units[0]['source'], 'run_indices': sorted(unit['source']['run_index'] for unit in units),
            'agent_invocation_count': sum(unit['source']['agent_invocation_count'] for unit in units)})
        summary['round_score'] = core.score_summary(round_rows)
        summary['resources'] = core.resource_summary(round_rows)
        summary['timing'] = core.timing_summary(round_rows)
        grouped_units.append(summary); cases.extend(unit_cases); raw_rows.extend(round_rows)
    data.update(schema_version='wildclawbench.platform-general-report/v2', units=grouped_units, tasks=cases, rounds=raw_rows)
    data['scope'].update(unit_count=len(grouped_units), case_result_count=len(cases), task_run_count=len(raw_rows), score_observation_count=len(raw_rows))
    physical = {}
    for row in raw_rows:
        physical.setdefault((row['lineage'].get('source_batch_id'), row['lineage'].get('source_unit_id'), row['execution_attempt_id']), row)
    data['scope']['unique_execution_count'] = len(physical)
    data['overall'] = {'score': core.score_summary(cases), 'round_score': core.score_summary(raw_rows),
        'categories': core.grouped_score(cases, 'category'), 'difficulties': core.grouped_score(cases, 'difficulty'),
        'judge_groups': core.judge_groups(cases), 'resources': core.resource_summary(list(physical.values())),
        'timing': core.timing_summary(list(physical.values()))}
    data['semantics'].update(aggregation='case-valid-rounds/v1',
        score_denominator='先对每题有效轮次求均分，再对用例均分等权汇总；有效零分保留，异常和未评分不补零。',
        resources='被测端资源依据原执行轮次统计；同一执行的多个评分版本在全局资源总量中去重。')
    refs = core.report_views.load_references()
    views = core.report_views.build_views(data, refs)
    raw_data = {**data, 'tasks': raw_rows, 'resource_round_view': True}
    raw_views = core.report_views.build_views(raw_data, refs)
    names = {value: views['unit_labels'][key] for key, value in raw_views['unit_labels'].items()}
    # Scoring dimensions use case means; timing, token and tool statistics use original rounds.
    for name in ['效率对比', '工具调用对比']:
        views['tables'][name] = _labels(raw_views['tables'][name], names)
    overall, raw_overall = views['tables']['总览'], _labels(raw_views['tables']['总览'], names)
    for index, row in enumerate(overall['rows']):
        row[9:] = raw_overall['rows'][index][9:]
    overall['cell_annotations'] = raw_overall.get('cell_annotations', {})
    overall['coverage_table'] = raw_overall.get('coverage_table')
    for view in views['tables'].values():
        view.setdefault('notes', []).append('多轮评分先按用例汇总；资源与耗时使用原执行轮次，缺失不补零。')
    replacements = {}
    for unit in grouped_units:
        profile = unit['scorer']; old = views['unit_labels'][unit['unit_id']]
        agent = {'codex': 'Codex CLI', 'deepseek-harness': 'DSH CLI'}.get(profile.get('harness'), profile.get('harness') or '未记录')
        replacements[old] = old.split('〔')[0] + ' · ' + agent + '/' + str(profile.get('model') or '未记录') + ' · ' + str(profile.get('reasoning_effort') or '未记录') + ' · 评分#' + str(unit['source']['score_operation_id'])
    data['presentation'] = _labels(views, replacements)
    return data
