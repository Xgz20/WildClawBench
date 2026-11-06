"""Explicit human failure-zero policy, kept separate from frozen Rubric scores.

Startup rejection decisions and explicitly authorized native interruptions are
separate policies. Neither turns unknown sends or grading errors into zeros.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


def require(value, detail):
    if not value:
        raise ValueError('REPORT_FAILURE_POLICY_INVALID: ' + detail)


def normalize(items, rows, refs, node=None):
    require(isinstance(items, list), 'decision list')
    by_id = {row['task_id']: row for row in rows}
    seen, output = set(), []
    for item in items:
        task = item.get('task_id')
        require(task in by_id and task not in seen, 'duplicate or out-of-scope decision')
        seen.add(task)
        row = by_id[task]
        require(item.get('execution_attempt_id') == row['execution_attempt_id']
                and row.get('total_score') is None and row.get('score_status') == 'unscored',
                'only selected unscored failure can receive policy zero')
        references = refs([item.get('decision'), item.get('human_policy')])
        decision, human = [json.loads(Path(ref['path']).read_bytes()) for ref in references]
        if human.get('derived_application') is True:
            parent_ref = refs([human.get('source_policy')])[0]
            parent = json.loads(Path(parent_ref['path']).read_bytes())
            require(parent.get('schema_version') == 'general70-human-conditional-failure-disposition/v1'
                    and parent.get('derived_application') is not True
                    and human.get('source_context_task') == parent.get('context_task')
                    and human.get('human_statement') == parent.get('human_statement')
                    and human.get('question_item_id') == parent.get('question_item_id')
                    and human.get('conditions') == parent.get('conditions')
                    and human.get('application_basis') == 'ongoing-round-generic-conditional-failure-rule'
                    and human.get('batch_id') == decision.get('identity', {}).get('batch_id'),
                    'inherited human policy application provenance')
            references.append(parent_ref)
        require(decision.get('schema_version') == 'general70-authorized-failure-zero-decision/v1'
                and decision.get('classification') == 'proven-harness-native-start-failure'
                and type(decision.get('failure_policy_score')) in (int, float)
                and decision['failure_policy_score'] == 0
                and decision.get('rubric_score') is None and decision.get('score_valid') is False
                and decision.get('scope') == [task], 'explicit failure-zero decision')
        require(human.get('schema_version') == 'general70-human-conditional-failure-disposition/v1'
                and human.get('context_task') == task and bool(human.get('human_statement'))
                and bool(human.get('question_item_id'))
                and bool(human.get('conditions', {}).get('proven_non_framework_failure'))
                and bool(human.get('conditions', {}).get('unresolved_attribution')),
                'direct human conditional policy provenance')
        lineage = row['lineage']
        record_ref = refs([{'path': lineage['source_execution_record'],
                            'sha256': lineage['execution_record_sha256']}])[0]
        record = json.loads(Path(record_ref['path']).read_bytes())
        require(record.get('identity') == decision.get('identity')
                and record['identity']['task_id'] == task
                and record['identity']['attempt_id'] == row['execution_attempt_id']
                and record['identity']['unit_id'] == lineage.get('source_unit_id', row['unit_id'])
                and record.get('phase') == 'FAILED'
                and record.get('execution', {}).get('business_status') == 'candidate_error'
                and record.get('candidate', {}).get('drift_status') == 'stable'
                and record.get('execution', {}).get('error', {}).get('code') == 'ASTRONSTUDIO_NATIVE_START_REJECTED',
                'selected collected native failure')
        binding = record.get('evidence', {}).get('native_start_rejection', {})
        require(binding.get('sha256') == decision.get('native_failure_proof', {}).get('sha256')
                and record.get('prompt', {}).get('sha256') == decision.get('prompt_sha256'),
                'decision native proof binding')
        unit = Path(lineage['source_unit_root']).absolute()
        # The formal evidence root is the parent of execution-record.json.
        state = Path(record_ref['path']).parent / 'execution/automation-state.json'
        executable = node or shutil.which('node')
        require(executable, 'Node required for frozen native proof replay')
        module = Path(__file__).resolve().parents[1] / 'vendor/e2e-shared/astronstudio-start-rejection/index.mjs'
        program = (f'import {{readFrozenStartRejection}} from {json.dumps(module.as_uri())};'
                   'import{readFile}from"node:fs/promises";import{dirname,join}from"node:path";'
                   'const[u,s,r]=process.argv.slice(1);const record=JSON.parse(await readFile(r));'
                   'const result=await readFrozenStartRejection(u,JSON.parse(await readFile(s)),record);'
                   'console.log(JSON.stringify(result.files.map(f=>({path:join(dirname(join(u,record.evidence.native_start_rejection.path)),f.path),'
                   'sha256:(f.path==="proof.json"?result.binding.sha256:result.proof.files.find(v=>v.path===f.path).sha256)}))));')
        result = subprocess.run([str(executable), '--input-type=module', '-e', program, str(unit), str(state), record_ref['path']],
                                capture_output=True, text=True, timeout=30)
        require(result.returncode == 0, 'frozen native proof replay failed: ' + result.stderr[-500:])
        native_refs = refs(json.loads(result.stdout))
        output.append({'unit_id': row['unit_id'], 'task_id': task,
                       'execution_attempt_id': row['execution_attempt_id'],
                       'failure_policy_score': 0.0, 'rubric_score': None,
                       'basis': 'explicit-human-policy/native-unsubmitted-start-rejection',
                       'evidence': [*references, record_ref, *native_refs]})
    return output


def prepare(data, audit):
    decisions = [decision for unit in audit['units'] for decision in unit.get('failure_zero_decisions', [])]
    if not decisions:
        return
    by_id = {(row['unit_id'], row['task_id']): row for row in decisions}
    for row in data['tasks']:
        policy = by_id.get((row['unit_id'], row['task_id']))
        row['failure_policy_score'] = policy['failure_policy_score'] if policy else None
        row['e2e_score'] = 0.0 if policy else row.get('total_score') if row['score_status'] == 'valid' else None
        row['e2e_score_basis'] = policy['basis'] if policy else 'frozen-rubric' if row['score_status'] == 'valid' else 'unknown'
    data['failure_score_policy'] = {'decisions': decisions,
        'rubric_scores_unchanged': True, 'unconfirmed_execution_failures_remain_null': True,
        'human_authorization_basis': 'Explicit administrator record of direct human instruction; no cryptographic human identity claim.'}


def notes(data):
    policy = data.get('failure_score_policy')
    if not policy:
        return []
    return [f"失败计零口径：{len(policy['decisions'])}项已核验的启动拒绝或原生中断按用户明确政策计端到端0分。"
            'Rubric分、valid状态和能力维度均保留原值；其他未评分/评测异常保持未知。'
            '总览另列含策略零分的端到端均分和计分覆盖，不能把该口径当成纯模型能力排名。']


def attach_views(data, views, labels):
    if not data.get('failure_score_policy'):
        return False
    overview = views['总览']
    overview['headers'][1] = 'Rubric平均分'
    start = len(overview['headers'])
    overview['headers'] += ['端到端均分(含策略零分)', '失败策略零分数', '端到端已计分数']
    overview['formats'][str(start)] = '0.00'
    by_label = {label: unit for unit, label in labels.items()}
    for values in overview['rows']:
        rows = [row for row in data['tasks'] if row['unit_id'] == by_label[values[0]]]
        known = [row['e2e_score'] for row in rows if row['e2e_score'] is not None]
        values += [100 * sum(known) / len(known) if known else None,
                   sum(row['failure_policy_score'] is not None for row in rows), len(known)]
    detail = [[labels[row['unit_id']], row['task_id'],
               None if row['total_score'] is None else 100 * row['total_score'], row['score_status'],
               None if row['failure_policy_score'] is None else 100 * row['failure_policy_score'],
               None if row['e2e_score'] is None else 100 * row['e2e_score'],
               {'explicit-human-policy/native-unsubmitted-start-rejection':'用户规则：启动失败计零',
                'explicit-human-policy/native-interruption':'用户规则：原生中断计零',
                'frozen-rubric':'冻结Rubric评分', 'unknown':'未评分/待核验'}.get(row['e2e_score_basis'], row['e2e_score_basis'])]
              for row in data['tasks']]
    views['端到端计分'] = {'headers': ['模型@Harness', '完整任务ID', 'Rubric得分', 'Rubric评分状态', '失败策略分', '端到端得分', '计分依据'],
                         'rows': detail, 'formats': {'2': '0.00', '4': '0.00', '5': '0.00'}, 'notes': notes(data)}
    return True
