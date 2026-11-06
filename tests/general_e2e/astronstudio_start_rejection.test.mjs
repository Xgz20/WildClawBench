import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { verifyNativeStartRejection } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-start-rejection.mjs';
import { executeSingleTask, parseArgs } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
function fixture(workspace = '/tmp/subject/workspace') {
  const prompt = 'Create the requested deliverables.';
  const created = '2026-11-06T06:28:17.904Z', failed = '2026-11-06T06:29:11.361Z';
  const error = 'ACode turn submission did not complete within 20000ms. at /Applications/AStudio.app/Contents/Resources/app.asar/apps/server/dist/index.mjs:119910:9';
  const model = { provider: 'acode', model: 'spark-x2.6', options: { reasoningEffort: 'high' } };
  const state = { phase: 'NEEDS_ATTENTION', identity: { batch_id: 'batch', unit_id: 'astronstudio-macos', task_id: 'task', attempt_id: 'original' },
    dataset: { id: 'dataset', digest: 'f'.repeat(64) }, driver: { id: 'astronstudio-macos', version: '0.4.18' },
    run_config: { config_digest: 'config' }, candidate_workspace: workspace,
    prompt: { sha256: sha(prompt), send_status: 'uncertain', sent_at: '2026-11-06T06:28:17.703Z' },
    session: { verified: false, thread_id: null, turn_id: null, session_id: null, baseline: [] },
    send: { dispatch_attempt_count: 1, pre_send_route_thread_id: 'thread', post_send_route_thread_id: 'thread',
      dispatch_armed_at: '2026-11-06T06:28:17.703Z', dispatch_completed_at: '2026-11-06T06:28:18.343Z' },
    client: { version: '3.6.0', model: 'Spark-X2.6', reasoning: 'High',
      workspace_selection: { project_id: 'project', thread_id: 'thread', path: workspace } },
    execution: { flow_profile: 'prompt-send-to-controller-terminal/v1', error: { code: 'PROMPT_SEND_UNCERTAIN' } },
    evidence: {}, human_assistance: { operation_count: 0 }, history: [] };
  const event = (sequence, type, payload, extra = {}) => ({ sequence, event_type: type, stream_id: 'thread', actor_kind: 'client', payload_json: JSON.stringify(payload), ...extra });
  const data = { projection_threads: [{ thread_id: 'thread', project_id: 'project', latest_turn_id: null, runtime_mode: 'full-access', model_selection_json: JSON.stringify(model) }],
    projection_projects: [{ project_id: 'project', workspace_root: workspace }],
    projection_thread_sessions: [{ thread_id: 'thread', status: 'error', last_error: error, updated_at: failed }],
    projection_thread_messages: [{ message_id: 'message', thread_id: 'thread', role: 'user', text: prompt, source: 'native', dispatch_origin: 'user', dispatch_mode: 'queue', created_at: created, sequence: 10 }],
    projection_turns: [], projection_pending_interactions: [], provider_runtime_open_turns: [], queued_turn_promotions: [], provider_runtime_events: [],
    provider_session_runtime: [{ thread_id: 'thread', status: 'stopped', resume_cursor_json: '{"emptyPrewarm":true}', runtime_payload_json: JSON.stringify({ cwd: workspace, activeTurnId: null }) }],
    orchestration_events: [event(10, 'thread.message-sent', { messageId: 'message', text: prompt }, { command_id: 'command', event_id: 'sent' }),
      event(11, 'thread.turn-start-requested', { threadId: 'thread', messageId: 'message', requestCommandId: 'command', createdAt: created, modelSelection: model, runtimeMode: 'full-access' }, { command_id: 'command', causation_event_id: 'sent' }),
      event(12, 'thread.activity-appended', { activity: { id: 'provider-start-failed:11:1', kind: 'provider.turn.start.failed', turnId: null, createdAt: failed,
        payload: { messageId: 'message', requestCommandId: 'command', requestCreatedAt: created, eventSequence: 11, preparationTerminal: true, settlementStatus: 'rejected', submissionState: 'not-sent', detail: error } } })],
    orchestration_command_receipts: [{ command_id: 'command', aggregate_id: 'thread', aggregate_kind: 'thread', status: 'accepted', error: null, result_sequence: 11, accepted_at: created, command_fingerprint: 'a'.repeat(64) }],
    orchestration_event_deliveries: [{ consumer_name: 'provider-command-reactor.v1', event_sequence: 11, thread_id: 'thread', state: 'succeeded', submission_state: 'not-submitted-v1', attempt_count: 1, completed_at: failed }] };
  const config = { candidateWorkspace: workspace, promptSha256: sha(prompt), expectedPermission: '完全访问', expectedModel: 'Spark-X2.6', expectedReasoning: 'High', runConfig: { tested_model: {} } };
  return { state, data, config };
}

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
    const f=fixture(join(root,'workspace'));
    Object.assign(f.config,{unitRoot:root,controlRoot:join(root,'control'),stateFile:join(root,'control/state.json'),recordFile:join(root,'control/record.json'),
      task:{task_id:'task'},manifest:{batch_id:'batch',unit_id:'astronstudio-macos',unit:{harness:{platform:'macos'},model:{requested_id:'Spark-X2.6'}}},
      resume:true,observeOnce:true,resolveNativeStartRejection:true,timeoutMs:1000,endpoint:'http://localhost:9240'});
    Object.assign(f.config.runConfig,{config_digest:'config',harness:{client_version:'3.6.0'},control:{endpoint:f.config.endpoint},
      tested_model:{display_name:'Spark-X2.6',reasoning_display:'High',permission_display:'完全访问'}});
    await mkdir(f.config.controlRoot); const original=JSON.stringify(f.state)+'\n',oldRecord='{"original":true}\n';
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
  } finally { await rm(root,{recursive:true,force:true}); }
});
