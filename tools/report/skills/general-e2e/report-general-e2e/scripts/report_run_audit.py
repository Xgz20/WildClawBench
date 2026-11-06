"""Validate explicit administrator run observations without changing scores/times.

The ledger supplements the return packages. It does not replace collection or
native-context verification, and hash agreement is not proof of an unseen event.
Only the explicitly evidenced native intervals contribute to an observed peak.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import report_failure_policy
import report_native_interruption_policy

SCHEMA = 'wildclawbench.general-e2e-report-run-audit/v1'


def require(value, detail):
    if not value:
        raise ValueError('REPORT_RUN_AUDIT_INVALID: ' + detail)


def stamp(value):
    require(isinstance(value, str), 'timestamp required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('REPORT_RUN_AUDIT_INVALID: timestamp') from exc
    require(result.tzinfo is not None, 'timestamp timezone required')
    return result


def checked_file(path, expected=None):
    path = Path(path).absolute()
    require(not any(item.is_symlink() for item in (path, *path.parents)), 'symlink evidence')
    require(path.is_file(), 'evidence missing: ' + str(path))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns, before.st_ino) ==
            (after.st_size, after.st_mtime_ns, after.st_ino), 'evidence changed')
    value = digest.hexdigest()
    require(expected is None or value == expected, 'evidence SHA mismatch: ' + str(path))
    return path, value, after.st_size


def overlap(intervals):
    """Half-open native intervals; touching endpoints do not overlap."""
    events = [(stamp(row[key]), delta) for row in intervals
              for key, delta in [('started_at', 1), ('finished_at', -1)]
              if stamp(row['finished_at']) > stamp(row['started_at'])]
    active = peak = 0
    for _, delta in sorted(events):
        active += delta
        peak = max(peak, active)
    return peak if intervals else None


def load(path, data, node=None):
    path, source_sha, _ = checked_file(path)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == source_sha, 'ledger changed')
    ledger = json.loads(raw)
    require(ledger.get('schema_version') == SCHEMA, 'schema')
    require(ledger.get('batch_id') == data['batch_id'], 'batch')
    require({key: ledger.get('dataset', {}).get(key) for key in ('id', 'digest')} ==
            {key: data['dataset'].get(key) for key in ('id', 'digest')}, 'dataset')
    declared = ledger.get('units')
    known_units = {unit['unit_id'] for unit in data['units']}
    require(isinstance(declared, list) and len(declared) == len(known_units) and
            {unit.get('unit_id') for unit in declared} == known_units, 'unit scope')
    evidence = {}

    def refs(items, allow_empty=False):
        require(isinstance(items, list) and items, 'native evidence references required')
        result = []
        for item in items:
            require(isinstance(item, dict) and isinstance(item.get('path'), str) and
                    isinstance(item.get('sha256'), str) and len(item['sha256']) == 64, 'evidence reference')
            file = Path(item['path'])
            file = file if file.is_absolute() else path.parent / file
            cache_key = (str(file.absolute()), item['sha256'])
            if cache_key not in evidence:
                checked, digest, size = checked_file(file, item['sha256'])
                require(size > 0 or allow_empty, 'empty native evidence')
                evidence[cache_key] = {'path': str(checked), 'sha256': digest, 'size': size}
            require(evidence[cache_key]['size'] > 0 or allow_empty, 'empty native evidence')
            result.append(dict(evidence[cache_key]))
        return result

    normalized = []
    for unit in declared:
        unit_id = unit['unit_id']
        rows = [row for row in data['tasks'] if row['unit_id'] == unit_id]
        by_id = {row['task_id']: row for row in rows}
        bindings = unit.get('task_bindings')
        require(isinstance(bindings, list) and [x.get('task_id') for x in bindings] ==
                [row['task_id'] for row in rows], 'full ordered task scope')
        for binding in bindings:
            row = by_id[binding['task_id']]
            require(binding.get('execution_attempt_id') == row['execution_attempt_id'] and
                    binding.get('scoring_attempt_id') == row['scoring_attempt_id'], 'selected attempt binding')
        output = {'unit_id': unit_id, 'task_bindings': copy.deepcopy(bindings)}
        for phase, attempt_key in [('execution', 'execution_attempt_id'), ('scoring', 'scoring_attempt_id')]:
            value = unit.get(phase)
            require(isinstance(value, dict), 'phase observations required')
            configured = value.get('configured_slots')
            require(type(configured) is int and 1 <= configured <= 8, 'configured slots')
            require(isinstance(value.get('method'), str) and bool(value['method'].strip()), 'observation method')
            configuration_evidence = refs(value.get('configuration_evidence'))
            intervals = value.get('intervals')
            require(isinstance(intervals, list), 'interval list')
            seen, accepted = set(), []
            for interval in intervals:
                task_id = interval.get('task_id')
                require(task_id in by_id and task_id not in seen, 'duplicate or unknown native interval')
                seen.add(task_id)
                row = by_id[task_id]
                require(row[attempt_key] is not None and interval.get('attempt_id') == row[attempt_key],
                        'native interval selected attempt')
                if phase == 'scoring':
                    require(not row.get('judge') or row['judge'].get('protocol') == 'codex-agent-judge-v1',
                            'not a native Codex judging interval')
                start, end = stamp(interval.get('started_at')), stamp(interval.get('finished_at'))
                require(end >= start, 'reversed native interval')
                if phase == 'execution':
                    require(stamp(row['execution_started_at']) <= start <= end <=
                            stamp(row['execution_finished_at']), 'native interval outside execution')
                accepted.append({'task_id': task_id, 'attempt_id': interval['attempt_id'],
                                 'started_at': interval['started_at'], 'finished_at': interval['finished_at'],
                                 'evidence': refs(interval.get('evidence'))})
            peak = overlap(accepted)
            require(peak is None or peak <= configured, 'observed peak exceeds configuration')
            reason = value.get('missing_reason')
            require(len(accepted) == len(rows) or isinstance(reason, str) and bool(reason.strip()),
                    'partial native interval coverage requires reason')
            output[phase] = {'configured_slots': configured, 'method': value['method'],
                             'configuration_evidence': configuration_evidence, 'intervals': accepted,
                             'observed_peak': peak, 'interval_coverage': {'known': len(accepted), 'total': len(rows)},
                             'coverage_status': 'complete' if len(accepted) == len(rows) else 'partial',
                             'missing_reason': reason if len(accepted) != len(rows) else None}
        holds = unit.get('controller_holds', [])
        require(isinstance(holds, list), 'controller holds')
        output['controller_holds'] = []
        for hold in holds:
            start, end = stamp(hold.get('started_at')), stamp(hold.get('finished_at'))
            duration = hold.get('duration_seconds')
            require(type(duration) in (int, float) and math.isfinite(duration) and duration >= 0 and
                    abs((end - start).total_seconds() - duration) < .000001, 'hold timing')
            require(hold.get('native_processes_paused') is False, 'unsupported native process pause')
            affected = hold.get('task_ids')
            require(isinstance(affected, list) and affected and len(affected) == len(set(affected)) and
                    set(affected) <= set(by_id), 'hold task scope')
            for task_id in affected:
                row = by_id[task_id]
                left, right = stamp(row['execution_started_at']), stamp(row['execution_finished_at'])
                require((start < right and end > left) if duration else left <= start <= right,
                        'hold outside affected execution')
            output['controller_holds'].append({'started_at': hold['started_at'], 'finished_at': hold['finished_at'],
                'duration_seconds': duration, 'task_ids': list(affected), 'native_processes_paused': False,
                'evidence': refs(hold.get('evidence'))})
        if 'failure_zero_decisions' in unit:
            output['failure_zero_decisions'] = report_failure_policy.normalize(
                unit['failure_zero_decisions'], rows, refs, node=node)
        if 'native_interruption_zero_policy' in unit:
            output.setdefault('failure_zero_decisions', []).extend(report_native_interruption_policy.normalize(
                unit['native_interruption_zero_policy'], rows, refs, node=node))
        require(len({item['task_id'] for item in output.get('failure_zero_decisions', [])}) ==
                len(output.get('failure_zero_decisions', [])), 'duplicate failure policy task')
        normalized.append(output)
    return {'schema_version': SCHEMA, 'source_sha256': source_sha, 'source_path': str(path),
            'basis': 'Explicit administrator native-interval audit; source hashes and selected full scope verified. '
                     'Observed peaks are recomputed from listed intervals, not configured slots. '
                     'Partial coverage is a lower bound, not proof of full utilization or simultaneous HTTP requests.',
            'units': normalized, 'evidence': list(evidence.values())}


def prepare(data, args):
    source = getattr(args, 'run_audit', None)
    if not source:
        return False
    audit = load(source, data, node=getattr(args, 'node', None))
    data['run_audit'] = audit
    report_failure_policy.prepare(data, audit)
    data['lineage']['run_audit_source_sha256'] = audit['source_sha256']
    return True


def stage(data, output_root):
    audit = data.get('run_audit')
    if not audit:
        return []
    checked_file(audit['source_path'], audit['source_sha256'])
    for item in audit['evidence']:
        checked_file(item['path'], item['sha256'])
    target = Path(output_root) / 'data/run-audit.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    data['lineage']['run_audit_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    return [target]


def notes(data, labels):
    output = report_failure_policy.notes(data)
    for unit in data.get('run_audit', {}).get('units', []):
        label = labels[unit['unit_id']]
        parts = []
        for key, name in [('execution', '执行'), ('scoring', '评分')]:
            value = unit[key]
            coverage = value['interval_coverage']
            peak = '未知' if value['observed_peak'] is None else str(value['observed_peak'])
            qualifier = '，仅为已知区间下限' if value['coverage_status'] == 'partial' else ''
            parts.append(f"{name}配置{value['configured_slots']}，原生区间重叠峰值{peak}"
                         f"（区间覆盖{coverage['known']}/{coverage['total']}{qualifier}）")
        output.append(f"运行审计：{label}：{'；'.join(parts)}。区间重叠不表示始终满载或同时HTTP请求。")
        for hold in unit['controller_holds']:
            output.append(f"计时说明：{label}的控制审阅暂停{hold['duration_seconds']:.6f}秒"
                          f"（{hold['started_at']}至{hold['finished_at']}）；相关流程耗时包含该期间的控制等待。"
                          "被测原生进程未暂停。原流程数值保留，原生任务耗时独立统计。")
    return output


def attach_notes(data, views, labels):
    extra = notes(data, labels)
    for name in ('总览', '效率对比'):
        view = views[name]
        view['notes'].extend(extra)


def audit_markdown(data):
    audit = data.get('run_audit')
    if not audit:
        return []
    labels = data['presentation']['unit_labels']
    lines = ['## 运行编排与控制介入', '', *notes(data, labels), '',
             '以上是明确提供的管理员运行审计；按所列原生区间复算峰值。缺失区间保持未知，'
             '配置值不能代替实际并发。评分、原始流程耗时及原生任务耗时均未由此重写。', '',
             f"运行审计输入SHA-256：`{audit['source_sha256']}`。规范化审计见`data/run-audit.json`。", '',
             '来源文件保留原路径、大小和SHA；本报告不复制原生裁判思考正文。', '']
    for unit in audit['units']:
        for decision in unit.get('failure_zero_decisions', []):
            lines += [f"- 失败策略0分：{labels[unit['unit_id']]} / {decision['task_id']}；"
                      f"execution attempt `{decision['execution_attempt_id']}`。原Rubric仍未评分，非伪造valid评分。"]
        for phase in ('execution', 'scoring'):
            value = unit[phase]
            lines += [f"- {labels[unit['unit_id']]} / {phase}：{value['method']}"]
            if value['missing_reason']:
                lines += ['  缺失说明：' + value['missing_reason']]
        for hold in unit['controller_holds']:
            lines += [f"- {labels[unit['unit_id']]} 控制等待涉及：" + '、'.join(hold['task_ids'])]
    lines += ['', *[f"- `{item['path']}`；{item['size']} bytes；SHA-256 `{item['sha256']}`"
                     for item in audit['evidence']], '']
    return lines
