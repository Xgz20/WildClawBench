"""Canonical General report metrics over verified platform headless-score jobs."""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from datetime import datetime, timezone
import copy
import html
import json
from pathlib import Path
import re
import shutil
import uuid

from .common import E2EError, atomic_json, digest, file_sha256, inside, load_script, read_json, identifier
from .engine import load_batch, verify_ready
from .handoff import export_scoring_context
from .headless import _check_files
from .store import BatchStore, controller_lock
from .trace import normalize_rollout, resource_metrics, ADAPTER

REPORT_SCHEMA = 'wildclawbench.platform-general-report/v1'
SCORE_TABLES = {'总览', '分类对比', '难度对比', 'Agent能力对比', '模态对比'}


@lru_cache(maxsize=1)
def report_module():
    root = Path(__file__).resolve().parents[2]
    script = root / 'tools/report/skills/general-e2e/report-general-e2e/scripts/report_general_e2e.py'
    return load_script(script, 'platform_canonical_general_report'), script


def _copy(source, destination):
    shutil.copytree(source, destination, copy_function=shutil.copyfile, symlinks=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))


def _source_row(core, source, item, task, original_unit, result, target):
    row_result = next((row for row in result['executions'] if row['execution_key'] == item['key']), None)
    source_work = Path(row_result['work_root']) if row_result else None
    if source_work and (source_work / 'context/handoff.json').is_file():
        state = read_json(source_work.parent / 'control/state.json')
        if state.get('immutable'):
            _check_files(source_work, state['immutable'])
        _copy(source_work / 'context/unit', target / 'unit')
        handoff = read_json(source_work / 'context/handoff.json')
        record_relative = str(Path(handoff['execution_record']).relative_to('unit'))
    elif item['phase'] == 'COMPLETED':
        repo = Path(__file__).resolve().parents[2]
        context = export_scoring_context(Path(result['source_batch_root']), item['key'], target / 'unscored-context',
                                        verification_skill=repo / 'tools/report/skills/general-e2e/collect-general-e2e')
        _copy(Path(context['context_root']) / 'unit', target / 'unit')
        record_relative = str(Path(context['execution_record']).relative_to('unit'))
    else:
        return _unavailable_row(core, item, task, original_unit, row_result)
    unit_manifest = read_json(target / 'unit/manifest.json')
    unit = unit_manifest['unit']
    record_file = target / 'unit' / record_relative
    record = read_json(record_file)
    execution_dir = target / 'scoring/execution-records'
    execution_dir.mkdir(parents=True)
    shutil.copyfile(record_file, execution_dir / (item['task_id'] + '.json'))
    score_path = None
    score = None
    if row_result and row_result.get('score_path'):
        original_score = Path(row_result['score_path'])
        if file_sha256(original_score) != row_result['score_sha256']:
            raise E2EError('REPORT_SCORE_DRIFT')
        attempt = target / 'scoring/attempts' / row_result['scoring_attempt_id']
        _copy(original_score.parent, attempt)
        score_path = attempt / original_score.name
        score = read_json(score_path)
        if file_sha256(score_path) != row_result['score_sha256']:
            raise E2EError('REPORT_SCORE_COPY_DRIFT')
    score_status = row_result['status'] if row_result and score else 'unscored'
    submission = {
        'task_id': item['task_id'], 'execution_attempt_id': item['attempt_id'],
        'execution_status': record['execution']['business_status'], 'score_status': score_status,
        'scoring_attempt_id': score['identity']['attempt_id'] if score else None,
        'judge_protocol': (score.get('judge') or {}).get('protocol') if score else None,
        'score_path': str(score_path.relative_to(target / 'scoring')) if score else None,
        'score_sha256': file_sha256(score_path) if score else None,
    }
    # This is a separate, truthful adapter manifest, not an unvalidated Skill return package.
    origin = {'schema': 'wildclawbench.platform-score-source/v1',
              'identity': {'batch_id': unit_manifest['batch_id'], 'unit_id': unit_manifest['unit_id']},
              'source_result_sha256': source['result_sha256'], 'original_execution_identity': record['identity']}
    atomic_json(target / 'source-manifest.json', origin)
    atomic_json(target / 'verification-receipt.json', {'schema': 'wildclawbench.platform-score-verification/v1',
                 'score_sha256': submission['score_sha256'], 'verification': row_result.get('verification') if row_result else None})
    atomic_json(target / 'submission-view.json', {'schema': 'wildclawbench.platform-score-submission/v1',
                 'dataset': record['dataset'], 'tasks': [submission]})
    selected = {'root': target, 'unit': unit, 'package_manifest': origin,
                'submission': {'dataset': record['dataset']}, 'package_id': 'score-job-' + source['id'],
                'package_manifest_path': target / 'source-manifest.json',
                'import_receipt_path': target / 'verification-receipt.json', 'submission_path': target / 'submission-view.json'}
    task_meta = next(row for row in unit_manifest['tasks'] if row['task_id'] == item['task_id'])
    row = core.build_task_row(selected, task_meta, submission)
    _native_resource_projection(core, row, record, target)
    if row_result and not score:
        row.update(score_status='evaluation_error', invalid_reason=row_result.get('error'),
                   evaluation={'status': 'evaluation_error', 'error': row_result.get('error')})
    row['source_execution'] = {'batch_id': result['batch_id'], 'unit_id': item['unit_id'],
                               'run_index': item['run_index'], 'attempt_id': item['attempt_id']}
    if item.get("preprocess_receipt"):
        row["preprocessing"] = item["preprocess_receipt"]
    return row


def _native_resource_projection(core, row, record, target):
    """Supplement reporting only; original execution, resource and score bytes stay sealed."""
    unit = target / 'unit'
    original = inside(unit, record['resource_metrics_path']) if record.get('resource_metrics_path') else None
    if original is None:
        return
    base = read_json(original)
    if base.get('collection', {}).get('collector') != ADAPTER:
        return
    index_file = inside(unit, record['evidence']['trace_index_path'])
    index = read_json(index_file)
    if index['identity'] != record['identity'] or len(index['raw_trace']) != 1:
        raise E2EError('REPORT_NATIVE_RESOURCE_IDENTITY')
    ref = index['raw_trace'][0]
    raw = inside(index_file.parent, ref['path'])
    if file_sha256(raw) != ref['sha256'] or raw.stat().st_size != ref['size']:
        raise E2EError('REPORT_NATIVE_RESOURCE_DRIFT')
    task = record['identity']['task_id']
    prompt = (unit / 'execution/tasks' / task / 'PROMPT.md').read_text(encoding='utf-8')
    binding = normalize_rollout(raw, identity=record['identity'], prompt=prompt,
        guest_cwd=record['session']['cwd'], requested_model=record['model']['requested_id'],
        requested_effort=record['model'].get('reasoning_effort'), report=read_json(original.parent / 'metadata/report.json'))
    for key in ('session_id', 'turn_id', 'cwd'):
        if binding['session'][key] != record['session'][key] or index['session'][key] != record['session'][key]:
            raise E2EError('REPORT_NATIVE_RESOURCE_SESSION')
    if not binding.get('native_resources') and not binding.get('native_resource_error'):
        return
    metrics = resource_metrics(record['identity'], binding, base['collection']['sources'])
    changes = {}
    for field in [*metrics['metrics']['usage'], *metrics['metrics']['requests']]:
        observed = core.metric_observation(metrics, field)
        changes[field] = {'before': row['resource'][field], 'after': observed}
        row['resource'][field] = observed
    supplement = {'schema': 'wildclawbench.platform-native-resource-supplement/v1',
        'identity': record['identity'], 'original_resource_sha256': file_sha256(original),
        'trace_index_sha256': file_sha256(index_file), 'raw_rollout_sha256': file_sha256(raw),
        'metrics': metrics, 'changes': changes}
    sidecar = target / 'report-resource-supplement.json'
    atomic_json(sidecar, supplement)
    row['lineage']['platform_native_resource_supplement'] = {'path': str(sidecar), 'sha256': file_sha256(sidecar),
        'profile': (binding.get('native_resources') or {}).get('parser', {}).get('profile'),
        'original_resource_sha256': supplement['original_resource_sha256'], 'raw_rollout_sha256': supplement['raw_rollout_sha256']}


def _unavailable_row(core, item, task, unit, outcome):
    error = (outcome or {}).get('error')
    scoring_error = error if not (outcome or {}).get('execution_not_ready') else None
    execution_error = item.get('error')
    frozen_input_failure = (item['phase'] == 'FAILED' and not item.get('dispatch_armed_at')
        and not item.get('session_id') and isinstance(execution_error, dict)
        and execution_error.get('code') == 'E2EError'
        and execution_error.get('message') == 'FROZEN_TASK_INPUT_DRIFT')
    preprocessing = item.get("preprocess_receipt")
    preprocess_failure = preprocessing and preprocessing.get("status") == "failed" and not item.get("dispatch_armed_at")
    status = ('cancelled' if item['phase'] == 'CANCELLED' else
              'infrastructure_error' if frozen_input_failure or preprocess_failure else 'unknown')
    if (outcome or {}).get('execution_not_ready') and error == 'CONTROLLER_EXECUTION_INCOMPLETE: task_timeout':
        status = 'timeout'
    reason = error
    if reason is None and isinstance(execution_error, dict):
        reason = execution_error.get('message') or execution_error.get('code')
    return {'run_id': unit['unit_id'] + '::' + task['task_id'], 'unit_id': unit['unit_id'],
            'task_id': task['task_id'], 'task_name': task.get('name'), 'category': task.get('category'),
            'difficulty': task.get('difficulty'), 'modality': task.get('modality'), 'execution_mode': 'automatic',
            'harness': {'id': unit['harness'], 'platform': 'unknown', 'version': None},
            'model': {'requested_id': unit['model'], 'actual_id': None, 'reasoning_effort': unit.get('reasoning_effort'),
                      'verification_status': 'unavailable'}, 'human_assistance': {'mode': 'automatic'},
            'execution_attempt_id': item['attempt_id'], 'execution_phase': item['phase'],
            'execution_status': status,
            'execution_error': execution_error, 'execution_started_at': None, 'execution_finished_at': None,
            'timing_clock_comparable': False, 'evidence_completeness': 'unavailable',
            'score_status': 'evaluation_error' if scoring_error else 'unscored', 'scoring_attempt_id': None,
            'judge': None, 'components': None,
            'evaluation': {'status': 'evaluation_error', 'error': scoring_error} if scoring_error else None,
            'total_score': None, 'invalid_reason': reason, 'resource_collection_status': 'unavailable',
            'resource': {field: core.metric_observation(None, field) for field, _, _ in core.RESOURCE_FIELDS},
            'checkpoints': core.report_views.checkpoints(None, None, core.resolve_file, core.sha256_file),
            'tool_calls': {'status': 'unavailable', 'total': None, 'by_tool': {}},
            'task_definition': {'task_id': task['task_id'], 'status': 'unavailable', 'sources': []},
            **({"preprocessing": preprocessing} if preprocessing else {}),
            'lineage': {'source_unit_id': unit['unit_id'], 'source_execution_state': item['key'],
                        'execution_not_dispatched': bool(frozen_input_failure or preprocess_failure)}}


def normalize_presentation(data):
    p = data['presentation']
    p['tables']['用例对比明细'] = p['case_comparison']
    p['sheet_order'].append('用例对比明细')
    for name in p['score_detail_order']:
        p['tables'][name] = p['score_details'][name]
        p['sheet_order'].append(name)
    if any(task.get("preprocessing") for task in data["tasks"]):
        rows = []
        for task in data["tasks"]:
            receipt = task.get("preprocessing")
            recipe = receipt["recipe"] if receipt else None
            rows.append([task["unit_id"], task["task_name"] or task["task_id"],
                         f"#{recipe['version_id']} · v{recipe['version']}" if recipe else "原始环境",
                         {"passed": "通过", "failed": "失败", "running": "未收口"}.get(receipt["status"], "—") if receipt else "—",
                         receipt["recipe_sha256"] if receipt else None])
        p["tables"]["环境预处理"] = {"headers": ["单元", "用例", "方案版本", "状态", "配置 SHA-256"], "rows": rows}
        p["sheet_order"].append("环境预处理")
    resource_rows = []
    for task in data['tasks']:
        for field, observation in task['resource'].items():
            coverage = observation['coverage']
            resource_rows.append([task['run_id'], field, data['overall']['resources'][field]['label'],
                observation['status'], observation['value'], observation['known_subtotal'], observation['complete'],
                coverage['known'], coverage['total'], coverage['unit'], observation.get('basis'),
                task['resource_collection_status'], task['score_status']])
    exceptions = [[row['run_id'], row['execution_status'], row['score_status'], row.get('invalid_reason'),
                   row['evidence_completeness'], (row.get('judge') or {}).get('protocol'), row['scoring_attempt_id'],
                   '计入能力均值，真实零分保留' if row['score_status'] == 'valid' else '不进入能力均值，不补零']
                  for row in data['tasks'] if row['score_status'] != 'valid' or row['execution_status'] != 'completed']
    audit = {'headers': ['运行ID', '字段', '指标', '来源状态', '完整值', '已知小计', '完整覆盖', '原生已知', '原生分母', '原生单位', '依据', '采集状态', '评分状态'],
             'rows': resource_rows, 'formats': {'4': '#,##0.000', '5': '#,##0.000'},
             'notes': ['空值不补零，资源来自原执行，评分模型用量独立记录。所有维度保留有效/涉及样本数。'],
             'exceptions_table': {'title': '评测异常与未评分', 'headers': ['运行ID', '执行状态', '评分状态', '无效原因', '证据完整性', '裁判协议', '评分attempt', '分母处理'], 'rows': exceptions},
             'dimension_table': {'title': '维度有效样本覆盖', 'headers': ['模型@Harness', '对比表', '维度', '有效样本数', '涉及样本数'], 'rows': p['dimension_coverage']},
             'identity_table': {'title': '单元身份与裁判协议', 'headers': ['Unit', '模型@Harness', '配置模型', 'Harness 身份', '裁判分组'], 'rows': p['unit_metadata']},
             'lineage_table': {'title': '输入谱系（完整 SHA）', 'headers': ['评分操作', '原执行批次', '原单元', '原run', '评分回执SHA', '执行manifestSHA'],
                 'rows': [[source['id'], source.get('batch_id'), source['unit_id'], source['run_index'], source['result_sha256'], source.get('batch_manifest_sha256')] for source in data['lineage']['selected_sources']]}}
    p['tables']['资源覆盖与异常'] = audit
    p['sheet_order'].append('资源覆盖与异常')
    labels = {'coverage_table': '统计覆盖', 'timing_table': '任务耗时对比'}
    def bits(view):
        return {key: copy.deepcopy(view[key]) for key in ['headers', 'rows', 'formats', 'cell_annotations', 'layout', 'unit_scores', 'notes'] if key in view}
    def children(view, prefix=''):
        output = []
        for key, child in view.items():
            if isinstance(child, dict) and 'headers' in child and 'rows' in child:
                title = prefix + (child.get('title') or labels.get(key, key))
                output.append({'title': title, 'view': bits(child)})
                output.extend(children(child, title + ' / '))
        return output
    for view in p['tables'].values():
        blocks = []
        if view.get('layout') == 'grouped_tools':
            offset = 0
            for group in view['groups']:
                child = bits(group)
                annotations = {}
                for row in range(len(group['rows'])):
                    for col in range(len(group['headers'])):
                        value = view.get('cell_annotations', {}).get(f'{offset + row}:{col}')
                        if value: annotations[f'{row}:{col}'] = value
                child['cell_annotations'] = annotations
                blocks.append({'title': group['title'], 'view': child})
                offset += len(group['rows'])
        else:
            blocks.append({'title': None, 'view': bits(view)})
        blocks.extend(children(view))
        view['render_blocks'] = blocks


def render_blocks(view):
    return view.get('render_blocks') or [{'title': None, 'view': view}]


def score_value(view, row, col, value):
    if view.get('layout') == 'case_compare' and col >= 10:
        scores = view.get('unit_scores', [])
        if row < len(scores) and col - 10 < len(scores[row]):
            number = scores[row][col - 10]
            return number * 100 if number is not None else None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def build_report(definition: dict, staging: Path):
    core, script = report_module()
    task_rows, units, sources, task_definitions = [], [], [], {}
    dataset = None
    seen_sources = set()
    for source in definition['sources']:
        identifier(str(source['id']), 'score_operation_id')
        if type(source['run_index']) is not int or source['run_index'] < 1:
            raise E2EError('REPORT_RUN_INDEX_INVALID')
        source_key = (source['id'], source['unit_id'], source['run_index'])
        if source_key in seen_sources:
            raise E2EError('REPORT_UNIT_SELECTION_DUPLICATE')
        seen_sources.add(source_key)
        result_file = Path(source['result_file'])
        if file_sha256(result_file) != source['result_sha256']:
            raise E2EError('REPORT_SCORING_SOURCE_DRIFT')
        result = read_json(result_file)
        if result.get('schema') != 'wildclawbench.headless-score-set/v1' or result['summary']['containers_held']:
            raise E2EError('REPORT_SCORE_JOB_NOT_TERMINAL')
        batch = Path(result['source_batch_root'])
        manifest = load_batch(batch)
        if digest(manifest) != result['batch_manifest_sha256']:
            raise E2EError('REPORT_EXECUTION_MANIFEST_DRIFT')
        original_unit = next((row for row in manifest['units'] if row['unit_id'] == source['unit_id']), None)
        if original_unit is None or original_unit['scene'] != 'general':
            raise E2EError('REPORT_GENERAL_UNIT_REQUIRED')
        items = [item for item in BatchStore(batch).rows()
                 if item['unit_id'] == source['unit_id'] and item['run_index'] == source['run_index']]
        if not items:
            raise E2EError('REPORT_UNIT_SCOPE_EMPTY')
        report_unit_id = 's' + str(source['id']) + '-r' + str(source['run_index']) + '-' + digest(source['unit_id'])[:16]
        rows = []
        unit = None
        for item in items:
            target = staging / '.sources' / report_unit_id / item['task_id']
            target.mkdir(parents=True)
            task = next(task for task in manifest['tasks'] if task['task_id'] == item['task_id'])
            if task['scene'] != 'general':
                raise E2EError('REPORT_GENERAL_UNIT_REQUIRED')
            frozen_dataset = task.get('dataset') or {}
            if dataset is None:
                dataset = frozen_dataset
            elif any(dataset.get(key) != frozen_dataset.get(key) for key in ['id', 'digest']):
                raise E2EError('REPORT_DATASET_VERSION_MISMATCH')
            if item['phase'] == 'COMPLETED':
                verify_ready(batch, item, manifest)
            row = _source_row(core, source, item, task, original_unit, result, target)
            if (target / 'unit/manifest.json').exists():
                frozen_unit = read_json(target / 'unit/manifest.json')
                if dataset is None:
                    dataset = frozen_unit['dataset']
                elif any(dataset.get(key) != frozen_unit['dataset'].get(key) for key in ['id', 'digest']):
                    raise E2EError('REPORT_DATASET_VERSION_MISMATCH')
                unit = frozen_unit['unit']
            definition_sha = digest({key: row.get('task_definition', {}).get(key) for key in ['task_sha256', 'contract_sha256']})
            if row.get('task_definition', {}).get('status') == 'complete':
                if item['task_id'] in task_definitions and task_definitions[item['task_id']] != definition_sha:
                    raise E2EError('REPORT_TASK_CONTRACT_CONFLICT')
                task_definitions[item['task_id']] = definition_sha
            row['lineage']['source_batch_id'] = result['batch_id']
            row['lineage']['score_operation_id'] = source['id']
            row['unit_id'] = report_unit_id
            row['run_id'] = report_unit_id + '::' + item['task_id']
            rows.append(row)
        if unit is None:
            unit = {'unit_id': report_unit_id, 'harness': rows[0]['harness'], 'model': rows[0]['model'], 'execution_mode': 'automatic'}
        unit = {**unit, 'unit_id': report_unit_id, 'task_ids': [row['task_id'] for row in rows]}
        summary = core.unit_summary(rows, unit)
        if original_unit['harness']=='workbuddy': summary['execution_options']={'max_mode':original_unit.get('max_mode',False)}
        summary['scorer'] = {key: result['config'].get(key) for key in ['harness', 'model', 'reasoning_effort', 'concurrency', 'timeout_seconds', 'api_format', 'image_id']}
        summary['source'] = {'batch_id': result['batch_id'], 'unit_id': source['unit_id'], 'run_index': source['run_index'],
                             'score_operation_id': source['id'], 'agent_invocation_count': sum(bool(row.get('agent_used')) for row in result['executions'] if row['unit_id'] == source['unit_id'] and row['run_index'] == source['run_index'])}
        units.append(summary)
        task_rows.extend(rows)
        sources.append({**source, 'result_file': 'score-operation://' + source['id'] + '/result.json', 'batch_manifest_sha256': result['batch_manifest_sha256']})
    if not task_rows:
        raise E2EError('REPORT_SELECTION_EMPTY')
    unique = list(dict.fromkeys(row['task_id'] for row in task_rows))
    data = {'schema_version': REPORT_SCHEMA, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'title': definition.get('name') or '通用场景端到端自动化评测报告', 'batch_id': definition['id'],
            'dataset': dataset or {'id': 'unavailable', 'digest': None},
            'scope': {'unique_task_count': len(unique), 'task_run_count': len(task_rows), 'unit_count': len(units), 'task_ids': unique},
            'units': units, 'tasks': task_rows,
            'overall': {'score': core.score_summary(task_rows), 'categories': core.grouped_score(task_rows, 'category'),
                        'difficulties': core.grouped_score(task_rows, 'difficulty'), 'judge_groups': core.judge_groups(task_rows),
                        'resources': core.resource_summary(task_rows), 'timing': core.timing_summary(task_rows)},
            'lineage': {'adapter_schema': 'wildclawbench.platform-score-source/v1', 'selected_sources': sources,
                        'report_skill_entry_sha256': file_sha256(script),
                        'report_views_entry_sha256': file_sha256(Path(core.report_views.__file__)),
                        'adapter_entry_sha256': file_sha256(Path(__file__)),
                        'report_reference_sha256': digest(core.report_views.load_references())},
            'semantics': {'score_denominator': '均值仅含有效成绩；真实零分保留；异常、未评分不补零。',
                          'resources': '被测端资源只取原执行回执；评分智能体用量不混入被测端指标。',
                          'unit_scope': '保留每个已选单元的全部冻结任务；题目范围不同不能作单因果排名。'}}
    data['presentation'] = core.report_views.build_views(data, core.report_views.load_references())
    unique_executions = {(row['lineage'].get('source_batch_id'), row['lineage'].get('source_unit_id'), row['execution_attempt_id']) for row in task_rows}
    data['scope']['unique_execution_count'] = len(unique_executions)
    if len(unique_executions) < len(task_rows):
        note = '本报告包含同一执行的独立评分版本；各单元复用原执行资源，不代表新增的被测端消耗。'
        data['semantics']['execution_reuse'] = note
        data['presentation']['tables']['总览']['notes'].insert(0, note)
    if definition.get('group_rounds'):
        from .round_reports import group_round_report
        data = group_round_report(core, data)
        units = data['units']
    configuration = []
    for unit in units:
        profile = unit['scorer']
        configuration.append([unit['unit_id'], data['presentation']['unit_labels'][unit['unit_id']],
            unit['source']['batch_id'], unit['source']['score_operation_id'], profile['harness'], profile['model'],
            profile['reasoning_effort'], profile.get('concurrency'), profile.get('timeout_seconds'), profile.get('image_id'), unit['source']['agent_invocation_count']])
    data['presentation']['tables']['评分配置'] = {
        'headers': ['报告单元ID', '被测模型@Harness', '原执行批次', '评分操作', '评分Harness', '评分模型', '推理强度', '评分并发数', '评分超时（秒）', '评分镜像SHA', '实际模型评分任务数'],
        'rows': configuration, 'formats': {},
        'notes': ['评分 Harness 与被测 Harness 分开记录。纯自动规则任务不调用评分模型；规则与语义组件均按原冻结契约验分。']}
    if definition.get('group_rounds'):
        data['presentation']['tables']['分轮明细'] = {
            'headers': ['比较单元', '用例ID', '用例轮次', '执行状态', '评分状态', '本轮总分', '执行尝试', '评分尝试', '检查点原始值'],
            'rows': [[data['presentation']['unit_labels'][row['unit_id']], row['task_id'], row['run_index'], row['execution_status'],
                      row['score_status'], row['total_score'] * 100 if row['total_score'] is not None else None,
                      row['execution_attempt_id'], row.get('scoring_attempt_id'), json.dumps(row.get('checkpoints', {}).get('values', {}), ensure_ascii=False)] for row in data['rounds']],
            'formats': {'5': '0.00'}, 'notes': ['原逐轮证据与分数独立保留；主比较表按用例汇总有效轮次，不覆盖冻结评分。']}
        data['presentation']['sheet_order'].append('分轮明细')
    normalize_presentation(data)
    data['presentation']['sheet_order'].append('评分配置')
    _relative_lineage(data, staging)
    return data


def _relative_lineage(value, root):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str) and item.startswith(str(root)):
                value[key] = str(Path(item).relative_to(root))
            else:
                _relative_lineage(item, root)
    elif isinstance(value, list):
        for item in value:
            _relative_lineage(item, root)


def cell_text(value, number_format=None):
    if value is None:
        return '-'
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        core, _ = report_module()
        from report_display import fixed_number
        fmt = number_format or ('0.00' if isinstance(value, float) else '0')
        decimals = len(fmt.split('.', 1)[1].split('%')[0]) if '.' in fmt else 0
        return fixed_number(value, decimals, grouping=',' in fmt, multiplier=100 if '%' in fmt else 1) + ('%' if '%' in fmt else '')
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def markdown(data):
    out = ['# ' + html.escape(data['title']), '', '数据集：' + str(data['dataset'].get('id')), '',
           '均值只含有效成绩；异常与未评分保留空值，真实零分计入。', '']
    def table(view):
        rows = [view['headers'], ['---'] * len(view['headers']), *view['rows']]
        for n, row in enumerate(rows):
            cells = []
            for col, value in enumerate(row):
                text = cell_text(value, view.get('formats', {}).get(str(col))) if n > 1 else str(value)
                cells.append(html.escape(text).replace('|', '\\|').replace('\n', '<br>'))
            out.append('| ' + ' | '.join(cells) + ' |')
        out.append('')
    for name in data['presentation']['sheet_order']:
        view = data['presentation']['tables'][name]
        out += ['## ' + name, '']
        for block in render_blocks(view):
            if block['title']: out.extend(['### ' + block['title'], ''])
            table(block['view'])
            if block['title']:
                out.extend('- ' + note for note in block['view'].get('notes', []))
                out.append('')
        for note in view.get('notes', []):
            out.append('- ' + note)
        out.append('')
    return '\n'.join(out)


def score_column(name, header, col):
    if name == '总览':
        return col == 1
    return col > 0 and (name in SCORE_TABLES or any(word in header for word in ['得分', '平均分', '总分'])) and '分差' not in header


def xlsx(data, destination):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.comments import Comment
    book = Workbook(); book.remove(book.active); used = set()
    for name in data['presentation']['sheet_order']:
        view = data['presentation']['tables'][name]
        title = re.sub(r'[\\/*?:\[\]]', '_', name)[:31]; base = title; serial = 1
        while title.casefold() in used:
            serial += 1; title = base[:27] + '_' + str(serial)
        used.add(title.casefold()); sheet = book.create_sheet(title); offset = 1; max_columns = 1
        for block in render_blocks(view):
            matrix = block['view']; max_columns = max(max_columns, len(matrix['headers']))
            if block['title']:
                sheet.cell(offset, 1, block['title']).font = Font(bold=True, color='334155'); offset += 1
            header_row = offset
            for col, label in enumerate(matrix['headers'], 1):
                cell = sheet.cell(header_row, col, label); cell.font = Font(color='FFFFFF', bold=True); cell.fill = PatternFill('solid', fgColor='334155')
            for index, row in enumerate(matrix['rows']):
                r = header_row + index + 1
                for c, value in enumerate(row, 1):
                    if isinstance(value, str) and len(value) > 32700: value = value[:32650] + '…（节选，完整内容见报告 JSON）'
                    cell = sheet.cell(r, c, '-' if value is None else value)
                    if isinstance(cell.value, str): cell.data_type = 's'
                    cell.alignment = Alignment(vertical='top', wrap_text=True)
                    if isinstance(value, (int, float)) and not isinstance(value, bool): cell.number_format = matrix.get('formats', {}).get(str(c - 1), '0.00' if isinstance(value, float) else '#,##0')
                    observed = score_value(matrix, index, c - 1, value)
                    eligible = score_column(name, matrix['headers'][c - 1], c - 1) or matrix.get('layout') == 'case_compare' and 10 <= c - 1 < 10 + len(matrix.get('unit_scores', [[]])[index])
                    if eligible and observed is not None:
                        color = 'DCFCE7' if observed >= 90 else 'DBEAFE' if observed >= 70 else 'FEF3C7' if observed >= 50 else 'FEE2E2';cell.fill = PatternFill('solid', fgColor=color)
                    annotation = matrix.get('cell_annotations', {}).get(f'{index}:{c - 1}')
                    if annotation and annotation.get('status') == 'partial':
                        cell.fill = PatternFill('solid', fgColor='FFFBE6');cell.comment = Comment('部分统计/已知小计：' + json.dumps(annotation.get('coverage', {}), ensure_ascii=False), 'AStudio Eval')
                sheet.row_dimensions[r].height = 54 if any(isinstance(v, str) and len(v) > 60 for v in row) else 24
            end = header_row + len(matrix['rows'])
            if offset == 1 or not sheet.auto_filter.ref:
                sheet.auto_filter.ref = f'A{header_row}:{sheet.cell(max(header_row, end), len(matrix["headers"])).column_letter}{max(header_row, end)}';sheet.freeze_panes = f'B{header_row + 1}'
            offset = end + 3
            if block['title']:
                for note in matrix.get('notes', []):
                    sheet.cell(offset, 1, note);sheet.cell(offset, 1).alignment = Alignment(wrap_text=True);sheet.row_dimensions[offset].height = 48;offset += 1
        for c in range(1, max_columns + 1): sheet.column_dimensions[sheet.cell(1, c).column_letter].width = 34 if c == 1 else 24
        for note in view.get('notes', []):
            sheet.cell(offset, 1, note);sheet.merge_cells(start_row=offset, start_column=1, end_row=offset, end_column=max(2, max_columns));sheet.cell(offset, 1).alignment = Alignment(wrap_text=True, vertical='top');sheet.row_dimensions[offset].height = 48;offset += 1
    book.save(destination)


def standalone_html(data):
    payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>端到端评测报告</title>
<style>body{font:14px system-ui;margin:32px;color:#1e293b;background:#f8fafc}section{background:white;padding:24px;margin:24px 0;border-radius:12px}.scroll{overflow:auto}table{border-collapse:collapse;min-width:800px;width:100%}td,th{padding:10px;border:1px solid #e2e8f0;max-width:460px;white-space:pre-wrap;overflow-wrap:anywhere}th{background:#e2e8f0;cursor:pointer;position:sticky;top:0}small{color:#64748b}svg{max-width:100%;height:auto}p{line-height:1.7}</style>
<h1 id="title"></h1><p id="scope"></p><main id="report"></main><script>const DATA=''' + payload + ''';
document.querySelector('#title').textContent=DATA.title;document.querySelector('#scope').textContent=DATA.dataset.id+' · '+(DATA.schema_version?.endsWith('/v2')?DATA.scope.unit_count+' 个比较对象 · '+DATA.scope.unique_execution_count+' 次原执行 · '+DATA.scope.task_run_count+' 项逐轮评分':DATA.scope.unit_count+' 个单元 · '+DATA.scope.task_run_count+' 项任务运行')+'。异常/未评分不补零。点击表头可排序。';
const SCORE=new Set(['总览','分类对比','难度对比','Agent能力对比','模态对比']);
function text(value,fmt){if(value===null||value===undefined)return '-';if(typeof value!=='number')return String(value);const digits=fmt&&fmt.includes('.')?fmt.split('.')[1].replace('%','').length:Number.isInteger(value)?0:2;return new Intl.NumberFormat('zh-CN',{minimumFractionDigits:digits,maximumFractionDigits:digits,useGrouping:!!fmt&&fmt.includes(',')}).format(fmt&&fmt.includes('%')?value*100:value)+(fmt&&fmt.includes('%')?'%':'')}
function renderTable(name,view,parent){const wrap=document.createElement('div');wrap.className='scroll';const table=document.createElement('table');wrap.append(table);parent.append(wrap);let rows=view.rows.slice(),direction=1;function draw(){table.replaceChildren();const head=document.createElement('tr');view.headers.forEach((label,col)=>{const th=document.createElement('th');th.textContent=label;th.onclick=()=>{direction*=-1;rows.sort((a,b)=>{const val=row=>view.layout==='case_compare'&&col>=10&&col-10<(view.unit_scores?.[view.rows.indexOf(row)]?.length??0)?view.unit_scores[view.rows.indexOf(row)][col-10]:row[col];const left=val(a),right=val(b);if(left==null&&right==null)return 0;if(left==null)return 1;if(right==null)return -1;return direction*(typeof left==='number'&&typeof right==='number'?left-right:String(left).localeCompare(String(right),'zh-CN',{numeric:true}))});draw()};head.append(th)});table.append(head);rows.forEach(row=>{const tr=document.createElement('tr');row.forEach((value,col)=>{const td=document.createElement('td');td.textContent=text(value,view.formats?.[col]);const originalIndex=view.rows.indexOf(row),actual=view.layout==='case_compare'&&col>=10&&col-10<(view.unit_scores?.[originalIndex]?.length??0)?view.unit_scores[originalIndex][col-10]==null?null:view.unit_scores[originalIndex][col-10]*100:typeof value==='number'?value:null;if(actual!==null&&col>0&&((view.layout==='case_compare'&&col>=10&&col-10<(view.unit_scores?.[originalIndex]?.length??0))||(name==='总览'?col===1:(SCORE.has(name)||/得分|平均分|总分/.test(view.headers[col]))))&&!/分差/.test(view.headers[col]))td.style.background=actual>=90?'#dcfce7':actual>=70?'#dbeafe':actual>=50?'#fef3c7':'#fee2e2';const annotation=view.cell_annotations?.[view.rows.indexOf(row)+':'+col];if(annotation?.status==='partial'){td.style.background='#fffbe6';td.title='部分统计/已知小计'}tr.append(td)});table.append(tr)})}draw()}
function chart(name,view,parent){if(!SCORE.has(name))return;const points=[];view.rows.forEach(row=>row.forEach((value,c)=>{if(c>0&&typeof value==='number'&&(name!=='总览'||c===1))points.push([String(row[0])+' · '+view.headers[c],value])}));if(!points.length)return;const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 1000 '+(points.length*32+20));points.forEach(([label,value],i)=>{const t=document.createElementNS(ns,'text');t.setAttribute('x','0');t.setAttribute('y',i*32+22);t.textContent=label.length>50?label.slice(0,50)+'…':label;svg.append(t);const bar=document.createElementNS(ns,'rect');bar.setAttribute('x','540');bar.setAttribute('y',i*32+7);bar.setAttribute('height','20');bar.setAttribute('width',Math.max(0,value)*4);bar.setAttribute('fill','#6366f1');svg.append(bar);const n=document.createElementNS(ns,'text');n.setAttribute('x',545+Math.max(0,value)*4);n.setAttribute('y',i*32+22);n.textContent=value.toFixed(2);svg.append(n)});parent.append(svg)}
for(const name of DATA.presentation.sheet_order){const view=DATA.presentation.tables[name],s=document.createElement('section'),h=document.createElement('h2');h.textContent=name;s.append(h);chart(name,view,s);for(const block of view.render_blocks??[{title:null,view}]){if(block.title){const h=document.createElement('h3');h.textContent=block.title;s.append(h)}renderTable(block.title?block.title:name,block.view,s);if(block.title)for(const note of block.view.notes??[]){const p=document.createElement('p');p.textContent=note;s.append(p)}}for(const note of view.notes??[]){const p=document.createElement('p');p.textContent=note;s.append(p)}document.querySelector('#report').append(s)}
</script></html>'''


def generate_report(definition: dict, output: Path):
    with controller_lock(output.parent / ('.' + output.name + '-control')):
        return _generate_report(definition, output)


def _generate_report(definition: dict, output: Path):
    request_sha = digest(definition)
    if (output / 'report-manifest.json').is_file():
        receipt = read_json(output / 'report-manifest.json')
        if receipt['request_sha256'] != request_sha:
            raise E2EError('REPORT_REQUEST_DRIFT')
        for artifact in receipt['artifacts'].values():
            if file_sha256(inside(output, artifact['path'])) != artifact['sha256']:
                raise E2EError('REPORT_ARTIFACT_DRIFT')
        return receipt
    if output.exists() and any(output.iterdir()):
        raise E2EError('REPORT_DESTINATION_NOT_EMPTY')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name('.' + output.name + '.building-' + uuid.uuid4().hex)
    stage.mkdir()
    try:
        data = build_report(definition, stage)
        atomic_json(stage / 'report.json', data)
        (stage / 'report.md').write_text(markdown(data), encoding='utf-8')
        (stage / 'report.html').write_text(standalone_html(data), encoding='utf-8')
        xlsx(data, stage / 'report.xlsx')
        receipt = {'schema': 'wildclawbench.platform-general-report-receipt/v1', 'request_sha256': request_sha,
                   'report_id': definition['id'], 'scope': data['scope'],
                   'artifacts': {kind: {'path': 'report.' + kind, 'sha256': file_sha256(stage / ('report.' + kind)),
                                        'bytes': (stage / ('report.' + kind)).stat().st_size}
                                 for kind in ['json', 'md', 'html', 'xlsx']}}
        atomic_json(stage / 'report-manifest.json', receipt)
        if output.exists(): output.rmdir()
        stage.rename(output)
        return receipt
    except BaseException:
        # Preserve failed preparation for diagnosis; never publish a partial final report.
        raise
