import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { verifyNativeStartRejection } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-start-rejection.mjs';
import { executeSingleTask, parseArgs } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';
import { readFrozenStartRejection } from '../../tools/report/e2e-shared/astronstudio-start-rejection/index.mjs';
import { finalizeAstronStudioExecution, verifyAstronStudioCollection } from '../../tools/report/skills/general-e2e/collect-general-e2e/scripts/finalize_astronstudio_execution.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
import { rejectionFixture as fixture } from './fixtures/native-start-rejection.mjs';

test('verified native rejection preserves absence of model execution and does not determine a score', () => {
  const f = fixture(); const result = verifyNativeStartRejection(f.data, f.state, f.config);
  assert.equal(result.failure_origin, 'harness-native-turn-start');
  assert.equal(result.native_turn_id, null); assert.equal(result.native_sdk_session_id, null);
  assert.equal(result.pending_dispatches, 0); assert.equal('score' in result, false);
  assert.equal(f.state.phase, 'NEEDS_ATTENTION');
});
for (const [name, change] of [
  ['changed prompt', f => f.data.projection_thread_messages[0].text += 'changed'],
  ['foreign workspace', f => f.data.projection_projects[0].workspace_root = '/foreign'],
  ['already started turn', f => f.data.projection_turns.push({ turn_id: 'late' })],
  ['pending input', f => f.data.projection_pending_interactions.push({ status: 'pending' })],
  ['queued promotion', f => f.data.queued_turn_promotions.push({ message_id: 'message' })],
  ['provider activity', f => f.data.provider_runtime_events.push({ thread_id: 'thread', event_type: 'turn.started', turn_id: 'turn' })],
  ['live provider runtime', f => f.data.provider_session_runtime[0].status = 'running'],
  ['uncertain delivery', f => f.data.orchestration_event_deliveries[0].state = 'uncertain'],
  ['submitted request', f => f.data.orchestration_event_deliveries[0].submission_state = 'submitted-v1'],
  ['duplicate message', f => f.data.projection_thread_messages.push({ ...f.data.projection_thread_messages[0] })],
  ['wrong accepted receipt', f => f.data.orchestration_command_receipts[0].result_sequence = 12],
  ['model drift', f => f.config.expectedModel = 'other'],
  ['failure not rejected', f => { const row=f.data.orchestration_events[2];const p=JSON.parse(row.payload_json);p.activity.payload.settlementStatus='retryable';row.payload_json=JSON.stringify(p); }],
]) test(`reject ${name} without changing the original attempt`, () => {
  const f = fixture(); change(f); const before=JSON.stringify(f.state);
  assert.throws(() => verifyNativeStartRejection(f.data, f.state, f.config), /NATIVE_START_REJECTION_/);
  assert.equal(JSON.stringify(f.state), before);
});

test('resolution flag requires observation and forbids dispatch/retry', () => {
  const base=['--unit-root','/unit','--task-id','task','--run-config','/config','--resolve-native-start-rejection'];
  assert.throws(() => parseArgs(base), /只允许/);
  assert.throws(() => parseArgs([...base,'--resume','--observe-once','--retry-pre-send-failure']), /只允许/);
  assert.equal(parseArgs([...base,'--resume','--observe-once']).resolveNativeStartRejection,true);
});

test('resume publishes same-attempt failed terminal and archives original bytes without any send', async () => {
  const root=await mkdtemp(join(tmpdir(),'native-start-rejection-'));
  try {
    const taskRoot=join(root,'execution/tasks/task');
    const f=fixture(join(taskRoot,'workspace'));
    f.state.schema_version='wildclawbench.general-e2e-astronstudio-execution-state/v1';
    f.state.task_root=taskRoot;f.state.prompt.path=join(taskRoot,'PROMPT.md');
    await mkdir(f.config.candidateWorkspace,{recursive:true});
    await mkdir(join(root,'receipts'));await writeFile(f.state.prompt.path,'Create the requested deliverables.');
    Object.assign(f.config,{unitRoot:root,controlRoot:join(root,'control'),stateFile:join(root,'control/state.json'),recordFile:join(root,'control/record.json'),
      task:{task_id:'task'},manifest:{schema_id:'urn:wildclawbench:schema:general-e2e:package-manifest:v1',schema_version:1,manifest_kind:'execution',batch_id:'batch',unit_id:'astronstudio-macos',dataset:f.state.dataset,
        task_ids:['task'],tasks:[{task_id:'task',prompt:{path:'execution/tasks/task/PROMPT.md',sent_sha256:f.state.prompt.sha256},workspace:{path:'execution/tasks/task/workspace'}}],
        unit:{harness:{id:'astronstudio',platform:'macos'},model:{requested_id:'Spark-X2.6',reasoning_effort:'high'}}},
      resume:true,observeOnce:true,resolveNativeStartRejection:true,timeoutMs:1000,endpoint:'http://localhost:9240'});
    Object.assign(f.config.runConfig,{config_digest:'config',harness:{client_version:'3.6.0'},control:{endpoint:f.config.endpoint},
      tested_model:{display_name:'Spark-X2.6',reasoning_display:'High',permission_display:'完全访问'}});
    await mkdir(f.config.controlRoot); const original=JSON.stringify(f.state)+'\n',oldRecord=JSON.stringify({original:true,identity:f.state.identity,prompt:f.state.prompt})+'\n';
    await writeFile(f.config.stateFile,original);await writeFile(f.config.recordFile,oldRecord);
    const result=await executeSingleTask(f.config,{probeAstronStudio:async()=>({ready:true,failed_checks:[],app:{version:'3.6.0'},cdp:{endpoint:f.config.endpoint},frozen_run_config:f.config.runConfig,state_database:{active_or_pending_session_count:0}}),
      queryNativeStartRejection:async()=>f.data,now:()=> '2026-11-06T07:00:00.000Z',clickSend:()=>{throw Error('must not send');},connectCdp:()=>{throw Error('must not navigate');}});
    assert.equal(result.phase,'FAILED');assert.equal(result.identity.attempt_id,'original');assert.equal(result.send.dispatch_attempt_count,1);
    assert.equal(result.session.verified,false);assert.equal(result.session.turn_id,null);
    const proofPath=join(root,result.evidence.native_start_rejection.path);const proof=JSON.parse(await readFile(proofPath));
    assert.equal(await readFile(join(proofPath,'../original-state.json'),'utf8'),original);
    assert.equal(await readFile(join(proofPath,'../original-execution-record.json'),'utf8'),oldRecord);
    assert.equal(proof.native_turn_id,null);assert.equal(proof.retry_performed,false);
    assert.equal(JSON.parse(await readFile(f.config.recordFile)).evidence.native_start_rejection.sha256,sha(await readFile(proofPath)));
    assert.equal((await readFrozenStartRejection(root,result)).files.length,4);
    await assert.rejects(readFrozenStartRejection(root,result,{evidence:{}}),/RECORD_PROOF_REQUIRED/);
    await writeFile(join(root,'manifest.json'),JSON.stringify(f.config.manifest));
    const cleanup={schema_version:'wildclawbench.general-e2e-task-process-cleanup/v1',supported:true,platform:'darwin',success:true,
      quiet_window_milliseconds:0,quiet_observed_milliseconds:0,late_process_detected:false,
      before:{supported:true,targets:[],seed_pids:[],root_pids:[]},termination_attempts:[],after:{supported:true,targets:[],seed_pids:[],root_pids:[]}};
    const closed=await finalizeAstronStudioExecution({unitRoot:root,stateFile:f.config.stateFile,traceIndex:'',resourceMetrics:'',candidatePolicy:'',
      stabilityMilliseconds:0,processQuietMilliseconds:0,processWaitMilliseconds:0},{terminateProcesses:async()=>cleanup});
    const record=JSON.parse(await readFile(join(root,'evidence/tasks/task/original/execution-record.json')));
    assert.equal(record.session.verified,false);assert.equal(record.session.turn_id,null);
    assert.equal(record.evidence.completeness,'partial');assert.equal(record.resource_metrics_path,null);
    assert.ok(record.evidence.native_start_rejection.path.startsWith('evidence/tasks/task/original/'));
    await verifyAstronStudioCollection({unitRoot:root,taskId:'task'});
    const archived=join(root,record.evidence.native_start_rejection.path);
    const proofBefore=await readFile(archived);await writeFile(archived,proofBefore.toString().replace('harness-native-turn-start','framework'));
    await assert.rejects(readFrozenStartRejection(root,result,record),/PROOF_SHA/);
  } finally { await rm(root,{recursive:true,force:true}); }
});
