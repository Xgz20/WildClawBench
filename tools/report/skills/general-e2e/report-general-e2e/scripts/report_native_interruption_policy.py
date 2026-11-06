"""Replay a native interruption and apply a separate, explicit human zero policy.

The policy changes the end-to-end disposition, never the source cause or Rubric.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import shutil
import subprocess


def require(value, detail):
    if not value:
        raise ValueError('REPORT_INTERRUPTION_POLICY_INVALID: ' + detail)


def normalize(policy_reference, rows, refs, node=None):
    policy_ref = refs([policy_reference])[0]
    human = json.loads(Path(policy_ref['path']).read_bytes())
    require(human.get('schema_version') == 'general70-human-native-interruption-zero-policy/v1'
            and isinstance(human.get('human_statement'), str) and bool(human['human_statement'].strip())
            and bool(human.get('question_item_id'))
            and human.get('includes_future_same_round_native_interruptions') is True,
            'explicit standing native interruption instruction')
    require(isinstance(human.get('current_task_ids'), list) and isinstance(human.get('harness_scope'), list), 'policy scope')
    output = []
    for row in rows:
        if row.get('execution_status') != 'cancelled':
            continue
        require(row.get('total_score') is None and row.get('score_status') == 'unscored', 'selected unscored interruption')
        lineage = row['lineage']
        record_ref = refs([{'path': lineage['source_execution_record'], 'sha256': lineage['execution_record_sha256']}])[0]
        record = json.loads(Path(record_ref['path']).read_bytes())
        identity = record.get('identity', {})
        require(identity.get('task_id') == row['task_id'] and identity.get('attempt_id') == row['execution_attempt_id']
                and identity.get('unit_id') == lineage.get('source_unit_id', row['unit_id'])
                and identity.get('batch_id') == human.get('batch_id')
                and record.get('dataset', {}).get('id') == human.get('dataset_id')
                and record.get('harness', {}).get('id') in human['harness_scope'], 'selected source identity')
        require(record.get('phase') == 'FAILED' and record.get('execution', {}).get('business_status') == 'cancelled'
                and record.get('session', {}).get('verified') is True
                and all(record['session'].get(key) for key in ['thread_id', 'turn_id', 'session_id', 'cwd'])
                and record.get('candidate', {}).get('drift_status') == 'stable', 'collected native cancellation')
        require(record['harness']['id'] == 'astronstudio', 'native replay adapter unavailable for this Harness')
        unit = Path(lineage['source_unit_root']).absolute()
        index_path = unit / record['evidence']['trace_index_path']
        state_path = Path(record_ref['path']).parent / 'execution/automation-state.json'
        executable = node or shutil.which('node')
        require(executable, 'Node required for native interruption replay')
        module = Path(__file__).resolve().parents[1] / 'vendor/e2e-shared/general-resource-supplements/astronstudio-runtime-interruption.mjs'
        program = (f'import{{verifyRuntimeInterruption}}from{json.dumps(module.as_uri())};'
                   'import{readFile}from"node:fs/promises";import{dirname,join}from"node:path";'
                   'const[i,s,r]=process.argv.slice(1);const index=JSON.parse(await readFile(i));'
                   'const record=JSON.parse(await readFile(r));const proof=await verifyRuntimeInterruption(index,await readFile(s),dirname(i),record);'
                   'if(!proof||proof.cancellation_confirmed!==true)throw Error("verified native interruption required");'
                   'console.log(JSON.stringify({profile:proof.profile,native_termination_origin:proof.native_termination_origin,'
                   'sdk_terminal_at:proof.sdk_terminal_at,evidence:[{path:i},{path:s},...index.raw_trace.map(v=>({path:join(dirname(i),v.path),sha256:v.sha256})),'
                   '...(index.binding_evidence||[]).map(v=>({path:join(dirname(i),v.path),sha256:v.sha256}))]}));')
        result = subprocess.run([str(executable), '--input-type=module', '-e', program,
                                 str(index_path), str(state_path), record_ref['path']], capture_output=True, text=True, timeout=30)
        require(result.returncode == 0, 'closed native interruption replay failed: ' + result.stderr[-500:])
        native = json.loads(result.stdout)
        # Index/state SHA come from the already verified imported evidence tree;
        # capture and bind them explicitly in the normalized policy ledger too.
        evidence = []
        for item in native['evidence']:
            if 'sha256' not in item:
                item['sha256'] = hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
            evidence.append(item)
        native_refs = refs(evidence, allow_empty=True)
        output.append({'unit_id': row['unit_id'], 'task_id': row['task_id'],
            'execution_attempt_id': row['execution_attempt_id'], 'failure_policy_score': 0.0, 'rubric_score': None,
            'basis': 'explicit-human-policy/native-interruption', 'cause_assignment': 'preserved; no inference from the zero policy',
            'native_profile': native['profile'], 'native_termination_origin': native['native_termination_origin'],
            'sdk_terminal_at': native['sdk_terminal_at'], 'evidence': [policy_ref, record_ref, *native_refs]})
    return output
