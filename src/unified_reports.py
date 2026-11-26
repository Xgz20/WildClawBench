"""Verified, offline General comparison reports for CLI and desktop executions.

This is an explicit source adapter, not a synthetic General E2E submission.
The canonical report Skill supplies score statistics and existing renderers.
"""
from collections import defaultdict
from datetime import datetime, timezone
import copy
import hashlib
import json
import math
from pathlib import Path
import uuid

from .e2e.common import digest, file_sha256, read_json, atomic_json
from .e2e import general_reports as general
from .e2e.round_reports import aggregate_case
from .e2e.store import controller_lock
from .utils.task_parser import parse_task_md
from .utils.eval_provenance import _path_tree_sha256
from .e2e.artifacts import inventory

SPEC = 'wildclawbench.unified-report-spec/v1'
SNAPSHOT = 'wildclawbench.unified-report-snapshot/v1'
REPORT = 'wildclawbench.unified-general-report/v1'
CONTRACT_FIELDS = ('task_id', 'prompt', 'automated_checks', 'llm_judge_rubric',
                   'rubric_criteria', 'grading_type', 'grading_weights', 'judge_evidence', 'env', 'skills', 'warmup')


def describe():
    _, script = general.report_module()
    return {'schema': SPEC, 'snapshot_schema': SNAPSHOT, 'report_schema': REPORT,
            'adapter_sha256': file_sha256(Path(__file__)), 'report_skill_sha256': file_sha256(script),
            'renderer_sha256': file_sha256(Path(general.__file__)),
            'round_aggregation_sha256': file_sha256(Path(__file__).parent / 'e2e/round_reports.py'),
            'task_parser_sha256': file_sha256(Path(__file__).parent / 'utils/task_parser.py')}


def checked(ref, roots):
    path = Path(ref['path'])
    resolved = path.resolve()
    if not path.is_absolute() or '..' in path.parts or path.is_symlink() or not any(resolved.is_relative_to(Path(root).resolve()) for root in roots):
        raise ValueError('REPORT_SOURCE_PATH_INVALID')
    for root in roots:
        root = Path(root).absolute()
        if path.is_relative_to(root):
            current = root
            for part in path.relative_to(root).parts:
                current /= part
                if current.is_symlink():
                    raise ValueError('REPORT_SOURCE_SYMLINK')
            break
    else:
        raise ValueError('REPORT_SOURCE_PATH_INVALID')
    if not path.is_file() or file_sha256(path) != ref['sha256']:
        raise ValueError('REPORT_SOURCE_DRIFT')
    return path


def content(ref, roots):
    raw = checked(ref, roots).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('REPORT_SOURCE_DRIFT')
    return raw.decode('utf-8-sig')


def document(ref, roots):
    value = json.loads(content(ref, roots))
    if not isinstance(value, dict):
        raise ValueError('REPORT_SOURCE_OBJECT_REQUIRED')
    return value


def contract(task):
    value = {key: task.get(key) for key in CONTRACT_FIELDS}
    # The parser returns all keys; old frozen JSON may omit empty defaults.
    for key in ('automated_checks', 'llm_judge_rubric', 'grading_type', 'env', 'skills', 'warmup'):
        value[key] = value[key] or ''
    for key in ('rubric_criteria',):
        value[key] = value[key] or []
    for key in ('grading_weights', 'judge_evidence'):
        value[key] = value[key] or {}
    if not value['task_id'] or not isinstance(value['prompt'], str) or not value['prompt'].strip():
        raise ValueError('REPORT_FROZEN_TASK_MISSING')
    return value


def observation(value=None, basis='not collected'):
    known = type(value) in (int, float) and math.isfinite(value) and value >= 0
    return {'value': value if known else None, 'known_subtotal': value if known else None,
            'complete': known, 'status': 'complete' if known else 'unavailable',
            'coverage': {'known': 1 if known else 0, 'total': 1, 'unit': 'task_run'}, 'basis': basis}


def materials(source, item, task):
    original_task = item['task_file']['sha256']
    if source['kind'] == 'cli':
        value = document(item['provenance_file'], source['roots'])
        if value.get('provenance_status') != 'complete' or value.get('task_id') != item['task_id']:
            raise ValueError('REPORT_MATERIAL_IDENTITY_MISSING')
        cached = task.get('_contract_provenance')
        if cached and cached != value:
            raise ValueError('REPORT_CLI_PROVENANCE_MISMATCH')
        original_task = value.get('task_sha256')
        result = {key: value.get(key) for key in ('workspace_exec_sha256', 'ground_truth_sha256')}
    else:
        result = {}
        for key, spec in item.get('materials', {}).items():
            root = Path(spec['path'])
            if root.is_symlink() or not any(root.resolve().is_relative_to(Path(base).resolve()) for base in source['roots']):
                raise ValueError('REPORT_SOURCE_PATH_INVALID')
            actual = inventory(root)
            expected = spec['entries']
            if {(entry['path'].rstrip('/'), entry['kind']) for entry in actual} != {(entry['path'].rstrip('/'), entry['kind']) for entry in expected}:
                raise ValueError('REPORT_MATERIAL_DRIFT')
            for entry in expected:
                if entry['kind'] == 'file':
                    checked({'path': str(root / entry['path']), 'sha256': entry['sha256']}, source['roots'])
                elif entry['kind'] == 'symlink':
                    raise ValueError('REPORT_SOURCE_SYMLINK')
            result[key] = _path_tree_sha256(root)
    if set(result) != {'workspace_exec_sha256', 'ground_truth_sha256'} or any(
            not isinstance(value, str) or len(value) != 64 for value in [*result.values(), original_task]):
        raise ValueError('REPORT_MATERIAL_IDENTITY_MISSING')
    return result, original_task


def _row(source, item, core):
    roots = source['roots']
    task_path = checked(item['task_file'], roots)
    task = document(item['task_file'], roots) if item['task_format'] == 'cli-json' else parse_task_md(task_path, raw=content(item['task_file'], roots))
    if str(task.get('metric_profile', '')).startswith('web-'):
        raise ValueError('REPORT_GENERAL_REQUIRED')
    definition = contract(task)
    if definition['task_id'] != item['task_id']:
        raise ValueError('REPORT_TASK_IDENTITY_MISMATCH')
    material_hashes, original_task = materials(source, item, task)
    files = [item['task_file'], *item.get('files', [])]
    if item.get('provenance_file'):
        files.append(item['provenance_file'])
    for ref in files:
        checked(ref, roots)
    state, score, judge = item['score_status'], None, None
    if state == 'valid':
        receipt = document(item['score_file'], roots)
        if source['kind'] == 'cli':
            if receipt.get('schema') == 'wildclawbench.cli-score/v1' and not item.get('input_manifest'):
                raise ValueError('REPORT_CLI_SCORING_INPUT_MISSING')
            if item.get('input_manifest'):
                manifest = document(item['input_manifest'], roots)
                if receipt.get('source_manifest_sha256') != digest(manifest):
                    raise ValueError('REPORT_CLI_SCORING_INPUT_MISMATCH')
                matches = [entry for entry in manifest.get('files', []) if entry.get('path') == 'task.json']
                if len(matches) != 1 or matches[0].get('sha256') != item['task_file']['sha256']:
                    raise ValueError('REPORT_CLI_FROZEN_TASK_MISMATCH')
            scores = receipt.get('scores') if receipt.get('schema') == 'wildclawbench.cli-score/v1' else receipt
            grading = scores.get('_grading') or {}
            if scores.get('error') or scores.get('llm_error') or grading.get('status') in {'failed', 'evaluator_failed'}:
                raise ValueError('REPORT_CLI_SCORE_INVALID')
            if str(grading.get('llm_notes', '')).lstrip().startswith('judge failed:'):
                raise ValueError('REPORT_CLI_SCORE_INVALID')
            score = scores.get('overall_score')
            judge = {'protocol': grading.get('protocol'), 'receipt_schema': receipt.get('schema', 'legacy-cli-score'),
                     **{key: receipt.get('config', {}).get(key) for key in ('harness', 'model', 'reasoning_effort')}}
        else:
            if (receipt.get('identity', {}).get('task_id') != item['task_id']
                    or receipt.get('execution', {}).get('attempt_id') != item['execution_attempt_id']
                    or receipt.get('result', {}).get('valid') is not True
                    or receipt.get('evaluation', {}).get('status') != 'completed'):
                raise ValueError('REPORT_E2E_SCORE_IDENTITY_MISMATCH')
            score = receipt['result'].get('total_score')
            judge = receipt.get('judge')
            if item.get('scoring_attempt_id') and receipt['identity'].get('attempt_id') != item['scoring_attempt_id']:
                raise ValueError('REPORT_E2E_SCORE_IDENTITY_MISMATCH')
            original_dataset = source['dataset'].get('original')
            if original_dataset and receipt.get('dataset') != original_dataset:
                raise ValueError('REPORT_DATASET_VERSION_MISMATCH')
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1 or score != item['total_score']:
            raise ValueError('REPORT_SCORE_VALUE_MISMATCH')
        files.append(item['score_file'])
        if definition['grading_type'] == 'automated' or receipt.get('scoring', {}).get('method') == 'rules':
            judge = {'protocol': 'not-required', 'model': None, 'reasoning_effort': None}
    elif state not in {'unscored', 'evaluation_error'} or item.get('total_score') is not None:
        raise ValueError('REPORT_SCORE_STATE_INVALID')
    meta = item.get('metadata') or {}
    resource = {field: core.metric_observation(None, field) for field, _, _ in core.RESOURCE_FIELDS}
    # Only explicit original execution fields are used, never judge usage or a
    # native duration inferred from the orchestration duration.
    for field, value in (item.get('resources') or {}).items():
        if field in resource:
            resource[field] = observation(value, source['kind'] + ' frozen execution receipt')
    row = {'run_id': source['id'] + '::r' + str(item['run_index']) + '::' + item['task_id'],
        'unit_id': source['id'], 'task_id': item['task_id'], 'task_name': meta.get('name') or item['task_id'],
        'category': meta.get('category') or task.get('category') or 'unknown',
        'difficulty': meta.get('difficulty'), 'modality': meta.get('modality') or task.get('modality'),
        'execution_mode': 'automatic', 'harness': source['harness'], 'model': source['model'],
        'human_assistance': {'mode': 'automatic'}, 'execution_attempt_id': item['execution_attempt_id'],
        'execution_phase': item.get('execution_phase'), 'execution_status': item['execution_status'],
        'execution_error': item.get('execution_error'), 'execution_started_at': None, 'execution_finished_at': None,
        'timing_clock_comparable': False, 'evidence_completeness': item.get('evidence_completeness', 'partial'),
        'score_status': state, 'scoring_attempt_id': item.get('scoring_attempt_id'), 'judge': judge,
        'components': None, 'evaluation': None, 'total_score': score, 'invalid_reason': item.get('error'),
        'resource_collection_status': 'partial' if any(value['complete'] for value in resource.values()) else 'unavailable',
        'resource': resource, 'checkpoints': {'values': {}, 'sources': []},
        'tool_calls': {'status': 'unavailable', 'total': None, 'by_tool': {}},
        'task_definition': {'task_id': item['task_id'], 'status': 'complete', 'prompt': definition['prompt'],
            'task_sha256': item['task_file']['sha256'], 'source_task_sha256': original_task,
            'contract_sha256': digest(definition), 'materials': material_hashes,
            'rubric': definition['llm_judge_rubric'], 'automated_checks': definition['automated_checks']},
        'run_index': item['run_index'], 'execution_version': item.get('execution_version', 1),
        'score_version': item.get('score_version'),
        'lineage': {**item.get('lineage', {}), 'source_kind': source['kind'], 'source_id': source['id'],
            'source_batch_id': source['id'].split('-s')[0], 'source_unit_id': source['id'],
            'score_operation_id': source['id'], 'contract_sha256': digest(definition), 'materials': material_hashes, 'files': files}}
    return row


def prepare(spec):
    if spec.get('schema') != SPEC or not spec.get('units'):
        raise ValueError('REPORT_REQUEST_INVALID')
    core, _ = general.report_module()
    units, seen, definitions, dataset, expected_tasks = [], set(), {}, None, None
    for source in spec['units']:
        if source['id'] in seen or source['kind'] not in {'cli', 'e2e'}:
            raise ValueError('REPORT_SOURCE_DUPLICATE')
        seen.add(source['id'])
        identity = {'id': source['dataset'].get('id'), 'release': source['dataset'].get('release')}
        if not identity['id']:
            raise ValueError('REPORT_DATASET_IDENTITY_MISSING')
        if dataset is not None and dataset != identity:
            raise ValueError('REPORT_DATASET_VERSION_MISMATCH')
        dataset = identity
        rows, keys = [], set()
        for item in source['rows']:
            key = (item['task_id'], item['run_index'])
            if key in keys or type(item['run_index']) is not int or item['run_index'] < 1:
                raise ValueError('REPORT_ROUND_DUPLICATE_OR_INVALID')
            keys.add(key)
            row = _row(source, item, core)
            fingerprint = digest({'definition': row['task_definition']['source_task_sha256'],
                'contract': row['task_definition']['contract_sha256'], 'materials': row['task_definition']['materials']})
            if row['task_id'] in definitions and definitions[row['task_id']] != fingerprint:
                raise ValueError('REPORT_TASK_RUBRIC_OR_MATERIAL_MISMATCH: ' + row['task_id'])
            definitions[row['task_id']] = fingerprint
            rows.append(row)
        tasks = sorted({row['task_id'] for row in rows})
        if not tasks or (expected_tasks is not None and expected_tasks != tasks):
            raise ValueError('REPORT_TASK_SCOPE_MISMATCH')
        expected_tasks = tasks
        units.append({'id': source['id'], 'kind': source['kind'], 'label': source['label'],
            'dataset': source['dataset'], 'harness': source['harness'], 'model': source['model'],
            'scorer': source['scorer'], 'selection': source['selection'], 'rows': rows})
    dataset = {**dataset, 'digest': digest(definitions), 'identity_mode': 'selected-frozen-contracts-and-materials/v1'}
    result = {'schema': SNAPSHOT, 'name': spec['name'], 'dataset': dataset, 'units': units,
              'task_ids': expected_tasks, 'reader': describe(), 'aggregation': 'case-valid-rounds/v1'}
    if not any(row['score_status'] == 'valid' for unit in units for row in unit['rows']):
        raise ValueError('REPORT_NO_VALID_SCORES')
    result['snapshot_sha256'] = digest(result)
    return result


def validate_snapshot(snapshot):
    value = copy.deepcopy(snapshot)
    checksum = value.pop('snapshot_sha256', None)
    if value.get('schema') != SNAPSHOT or checksum != digest(value):
        raise ValueError('REPORT_SNAPSHOT_DRIFT')
    if value.get('aggregation') != 'case-valid-rounds/v1':
        raise ValueError('REPORT_AGGREGATION_INVALID')
    if not value.get('units') or len({unit['id'] for unit in value['units']}) != len(value['units']):
        raise ValueError('REPORT_SOURCE_DUPLICATE')
    definitions = {}
    for unit in value['units']:
        if set(value['task_ids']) != {row['task_id'] for row in unit['rows']}:
            raise ValueError('REPORT_TASK_SCOPE_MISMATCH')
        seen = set()
        for row in unit['rows']:
            key = row['task_id'], row['run_index']
            if key in seen or type(row['run_index']) is not int or row['run_index'] < 1 or row['unit_id'] != unit['id']:
                raise ValueError('REPORT_ROUND_DUPLICATE_OR_INVALID')
            seen.add(key)
            definition = row['task_definition']
            fingerprint = digest({'definition': definition['source_task_sha256'],
                'contract': definition['contract_sha256'], 'materials': definition['materials']})
            if row['task_id'] in definitions and definitions[row['task_id']] != fingerprint:
                raise ValueError('REPORT_TASK_RUBRIC_OR_MATERIAL_MISMATCH')
            definitions[row['task_id']] = fingerprint
            if row['score_status'] == 'valid':
                number = row['total_score']
                if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 1:
                    raise ValueError('REPORT_SCORE_VALUE_MISMATCH')
            elif row['score_status'] not in {'unscored', 'evaluation_error'} or row['total_score'] is not None:
                raise ValueError('REPORT_SCORE_STATE_INVALID')
    if value['dataset']['digest'] != digest(definitions):
        raise ValueError('REPORT_DATASET_VERSION_MISMATCH')
    return value


def _table(headers, rows, formats=None, notes=None):
    return {'headers': headers, 'rows': rows, 'formats': formats or {}, 'notes': notes or []}


def build(snapshot):
    frozen = validate_snapshot(snapshot)
    core, _ = general.report_module()
    units, tasks, rounds, overview, categories, difficulties, details, resources, lineage, configurations = [], [], [], [], [], [], [], [], [], []
    for source in frozen['units']:
        by_task = defaultdict(list)
        for row in source['rows']:
            by_task[row['task_id']].append(row)
        cases = [aggregate_case(sorted(values, key=lambda row: row['run_index']), source['id']) for values in by_task.values()]
        stats = core.score_summary(cases)
        model = source['model']
        model_label = model.get('actual_id') or str(model.get('requested_id') or '未知模型') + '（配置值，未回读）'
        label = source['label']
        protocols = sorted({(row.get('judge') or {}).get('protocol') or '未记录' for row in source['rows'] if row['score_status'] == 'valid'})
        configurations.append([label, source['kind'], source['scorer'].get('harness'), source['scorer'].get('model'),
            source['scorer'].get('reasoning_effort'), source['scorer'].get('transport'), ' / '.join(protocols), source['dataset'].get('release'), source['id']])
        units.append({'unit_id': source['id'], 'label': label, 'kind': source['kind'], 'harness': source['harness'],
            'model': model, 'scorer': source['scorer'], 'source': source['selection'], 'score': stats})
        tasks.extend(cases);rounds.extend(source['rows'])
        overview.append([label, stats['mean_score'] * 100 if stats['mean_score'] is not None else None,
            len(cases), stats['valid_score_count'], stats['evaluation_error_count'], stats['unscored_count'],
            len(source['rows']), model_label, model.get('reasoning_effort'), source['harness']['id'], source['kind']])
        for target, field in ((categories, 'category'), (difficulties, 'difficulty')):
            for group in core.grouped_score(cases, field):
                target.append([label, group['mean_score'] * 100 if group['mean_score'] is not None else None,
                    group[field], group['frozen_task_run_count'], group['valid_score_count']])
        for row in source['rows']:
            details.append([label, row['task_id'], row['run_index'], row['execution_status'], row['score_status'],
                row['total_score'] * 100 if row['total_score'] is not None else None,
                row['execution_version'], row['score_version'], row['execution_attempt_id'], row['scoring_attempt_id'], row['invalid_reason']])
            for ref in row['lineage']['files']:
                lineage.append([source['id'], row['task_id'], row['run_index'], ref['path'], ref['sha256']])
        for field, entry in core.resource_summary(source['rows']).items():
            resources.append([label, entry['label'], entry['total'], entry['known_subtotal'], entry['status'],
                              entry['coverage']['known'], entry['coverage']['total']])
    views = {
        '总览': _table(['比较对象', '总平均分 / 100', '用例数', '有效用例', '评分异常用例', '未评分用例', '原执行轮次', '模型', '被测推理强度', 'Harness', '执行方式'], overview, {'1': '0.00'},
            ['每题先对有效轮次求均分，再对有效用例等权平均。有效零分保留；异常、未评分不补零。',
             '比较对象的模型、Harness 和裁判均独立保留；来源覆盖不同，不作单因果归因。',
             '同一原执行可被不同评分组复用；各组资源只作对照，不跨评分组相加。']),
        '分类对比': _table(['比较对象', '均分 / 100', '分类', '涉及用例', '有效用例'], categories, {'1': '0.00'}),
        '难度对比': _table(['比较对象', '均分 / 100', '难度', '涉及用例', '有效用例'], difficulties, {'1': '0.00'}),
        '分轮明细': _table(['比较对象', '用例ID', '轮次', '执行状态', '评分状态', '本轮总分 / 100', '执行版本', '评分版本', '执行尝试', '评分尝试', '异常说明'], details, {'5': '0.00'}),
        '资源覆盖': _table(['比较对象', '指标', '完整总量', '已知小计', '状态', '完整轮次', '涉及轮次'], resources,
            notes=['只使用原执行回执中的显式字段，缺失资源与细分能力不推测、不补零。']),
        '来源索引': _table(['来源ID', '用例ID', '轮次', '原产物路径', 'SHA-256'], lineage),
        '评分配置': _table(['比较对象', '执行方式', '评分Harness', '配置评分模型', '推理强度', '评分通道', '实际裁判协议', '数据集发行', '来源ID'], configurations,
            notes=['此表保留评分配置，不表示纯规则任务也调用了模型；逐轮实际裁判身份保留于 JSON。']),
    }
    matrix = []
    by_case = {(row['unit_id'], row['task_id']): row for row in tasks}
    for task_id in frozen['task_ids']:
        values = [by_case[(unit['unit_id'], task_id)]['total_score'] for unit in units]
        known = [score for score in values if score is not None]
        matrix.append([task_id, *[score * 100 if score is not None else None for score in values],
                       (max(known) - min(known)) * 100 if len(known) > 1 else None])
    views['用例对比'] = _table(['用例ID', *[unit['label'] for unit in units], '最大分差'], matrix,
        {str(index): '0.00' for index in range(1, len(units)+2)}, ['无效或缺席成绩保持空值；只有至少两个有效成绩时计算分差。'])
    # Preserve the familiar order while rendering every artifact from one data source.
    order = ['总览', '分类对比', '难度对比', '用例对比', '分轮明细', '评分配置', '资源覆盖', '来源索引']
    return {'schema_version': REPORT, 'title': frozen['name'], 'generated_at': datetime.now(timezone.utc).isoformat(),
        'dataset': frozen['dataset'], 'scope': {'unique_task_count': len(frozen['task_ids']), 'task_ids': frozen['task_ids'],
            'task_run_count': len(rounds), 'unit_count': len(units), 'case_result_count': len(tasks),
            'unique_execution_count': len({(row['lineage']['source_kind'], row['execution_attempt_id'], row['task_id']) for row in rounds})},
        'units': units, 'tasks': tasks, 'rounds': rounds, 'overall': {'score': {key: value for key, value in core.score_summary(tasks).items()
            if key not in {'mean_score', 'score_sum', 'score_denominator'}}},
        'presentation': {'sheet_order': order, 'tables': views},
        'lineage': {'snapshot_sha256': snapshot['snapshot_sha256'], 'reader': frozen['reader']},
        'semantics': {'aggregation': 'case-valid-rounds/v1', 'cross_units': '比较对象分别计算成绩，不跨模型/Harness/裁判协议混算全局平均分。',
            'dataset_identity': '所选冻结题面、Rubric 及执行/私有评分素材的内容指纹；原数据集发行身份分别保留在来源快照。'}}


def generate(snapshot, output):
    output = Path(output)
    with controller_lock(output.parent / ('.' + output.name + '-control')):
        return _generate(snapshot, output)


def _generate(snapshot, output):
    validate_snapshot(snapshot)
    checksum = snapshot['snapshot_sha256']
    if (output / 'report-manifest.json').is_file():
        receipt = read_json(output / 'report-manifest.json')
        if receipt['snapshot_sha256'] != checksum:
            raise ValueError('REPORT_REQUEST_DRIFT')
        for artifact in receipt['artifacts'].values():
            if file_sha256(output / artifact['path']) != artifact['sha256']:
                raise ValueError('REPORT_ARTIFACT_DRIFT')
        return receipt
    if output.exists() and any(output.iterdir()):
        raise ValueError('REPORT_DESTINATION_NOT_EMPTY')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name('.' + output.name + '.building-' + uuid.uuid4().hex)
    staging.mkdir()
    data = build(snapshot)
    atomic_json(staging / 'report.json', data)
    atomic_json(staging / 'source-snapshot.json', snapshot)
    (staging / 'report.md').write_text(general.markdown(data), encoding='utf-8')
    (staging / 'report.html').write_text(general.standalone_html(data), encoding='utf-8')
    general.xlsx(data, staging / 'report.xlsx')
    artifacts = {kind: {'path': name, 'sha256': file_sha256(staging / name), 'bytes': (staging / name).stat().st_size}
        for kind, name in [('json', 'report.json'), ('md', 'report.md'), ('html', 'report.html'), ('xlsx', 'report.xlsx'), ('snapshot', 'source-snapshot.json')]}
    receipt = {'schema': 'wildclawbench.unified-report-receipt/v1', 'snapshot_sha256': checksum,
               'scope': data['scope'], 'artifacts': artifacts}
    atomic_json(staging / 'report-manifest.json', receipt)
    if output.exists():
        output.rmdir()
    staging.rename(output)
    return receipt
