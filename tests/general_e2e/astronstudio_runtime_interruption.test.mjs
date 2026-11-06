import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, writeFile, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { deriveRuntimeInterruption, verifyRuntimeInterruption, RUNTIME_INTERRUPTION_PROFILE,
  RUNTIME_INTERRUPTION_MISSING_PROFILE,
  RUNTIME_INTERRUPTION_RECONCILED_PROFILE,
  RUNTIME_INTERRUPTION_STALE_SESSION_PROFILE,
  RUNTIME_WATCHDOG_FAILURE_PROFILE,
  RUNTIME_INTERRUPTION_STATE, RUNTIME_INTERRUPTION_NATIVE, RUNTIME_INTERRUPTION_PROOF }
  from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-runtime-interruption.mjs';
const hash = b => createHash('sha256').update(b).digest('hex');
const bytes = value => Buffer.from(JSON.stringify(value));
function fixture() {
  const identity = { batch_id:'b', unit_id:'u', task_id:'t', attempt_id:'attempt' };
  const session = { thread_id:'thread', turn_id:'turn', session_id:'sdk', cwd:'/fixture/workspace',
    verified:true, native_status:'interrupted' };
  const state = { identity, session, phase:'FAILED', execution:{ business_status:'cancelled', finished_at:'2026-11-06T00:00:00Z' },
    prompt:{ send_status:'sent', sha256:hash('frozen prompt') }, send:{ dispatch_attempt_count:1 } };
  const index = { identity, session, canonical_source_policy:{ id:'bound-native-sdk-canonical/v1' } };
  const sdk = [{ type:'session_meta', payload:{ id:'sdk', cwd:session.cwd } },
    { type:'event_msg', timestamp:'2026-11-05T12:00:00Z', payload:{ type:'task_started', turn_id:'turn' } },
    { type:'event_msg', payload:{ type:'user_message', message:'frozen prompt' } },
    { type:'event_msg', timestamp:'2026-11-05T12:00:20Z', payload:{ type:'turn_aborted', turn_id:'turn', reason:'interrupted',
      completed_at:1793880020, duration_ms:20000 } }];
  const provider = [{ sequence:1, event_type:'turn.completed', thread_id:'thread', turn_id:'turn', event:{ threadId:'thread',
    turnId:'turn', providerRefs:{ providerThreadId:'sdk', providerTurnId:'turn' }, payload:{ state:'interrupted' },
    raw:{ payload:{ threadId:'sdk', turn:{ id:'turn', status:'interrupted', error:null, completedAt:1793880020, durationMs:20000 } } } } }];
  const native = { turn_state:'interrupted', termination_origin:'runtime', latest_turn_id:'turn', session_status:'interrupted',
    active_turn_id:null, pending_count:0, cwd:session.cwd, completed_at:'2026-11-05T12:00:21Z' };
  return { state, index, sdk, provider, native };
}
const lines = rows => Buffer.from(rows.map(JSON.stringify).join('\n')+'\n');
const derive = f => deriveRuntimeInterruption(bytes(f.state), f.index, lines(f.sdk), lines(f.provider), f.native);
test('native watchdog failure keeps candidate_error and its tool error while proving the exact SDK stop',()=>{
  const f=fixture(),message='最后失败工具 Ran command，失败原因：command not found；308 秒无进展。任务已失败。';
  f.state.execution.business_status='candidate_error';f.state.execution.error={code:'ASTRONSTUDIO_TURN_ERROR',message};f.state.session.native_status='running';
  Object.assign(f.native,{turn_state:'error',session_status:'error',runtime_status:'stopped',last_runtime_event:'turn.completed',last_runtime_event_at:f.native.completed_at,last_error:message});
  f.provider[0].event.payload={state:'failed',errorMessage:message};
  const original=bytes(f.state),proof=derive(f);assert.equal(proof.profile,RUNTIME_WATCHDOG_FAILURE_PROFILE);
  assert.equal(proof.original_business_status,'candidate_error');assert.equal(proof.sdk_interruption_confirmed,true);assert.deepEqual(bytes(f.state),original);
  f.native.runtime_status='running';assert.throws(()=>derive(f),/WATCHDOG_FAILURE_UNBOUND/);
  f.native.runtime_status='stopped';f.provider[0].event.payload.errorMessage='foreign';assert.throws(()=>derive(f),/PROVIDER_SDK_MISMATCH/);
  f.provider=[];f.native.runtime_turn_event_count=0;
  assert.equal(deriveRuntimeInterruption(bytes(f.state),f.index,lines(f.sdk),Buffer.alloc(0),f.native).provider_terminal_sequence,null);
});
test('failed interrupted turn can retain a stale running session field without rewriting original state', () => {
  const f=fixture();f.state.session.native_status='running';f.state.execution.error={code:'ASTRONSTUDIO_TURN_INTERRUPTED'};
  const original=bytes(f.state),proof=derive(f);
  assert.equal(proof.profile,RUNTIME_INTERRUPTION_STALE_SESSION_PROFILE);
  assert.equal(proof.state_session_projection.original_native_status,'running');
  assert.equal(proof.cancellation_confirmed,true);assert.equal(proof.original_state_modified,false);
  assert.equal(proof.scoreability_changed,false);assert.deepEqual(bytes(f.state),original);
  delete f.state.execution.error;assert.throws(()=>derive(f),/STATE_UNBOUND/);
  const active=fixture();active.state.phase='RUNNING';active.state.execution.business_status=null;
  assert.throws(()=>derive(active),/STATE_UNBOUND/);
});
function reconciledFixture() {
  const f=fixture(),time=f.native.completed_at,command=`restart-reconcile:thread:${time}`;
  f.provider=[{sequence:1,event_type:'turn.started',thread_id:'thread',turn_id:'turn',
    event:{type:'turn.started',threadId:'thread',turnId:'turn',providerRefs:{providerThreadId:'sdk',providerTurnId:'turn'}}}];
  f.native.runtime_turn_event_count=1;
  f.native.restart_reconciliations=[{sequence:2,event_id:'native-restart-event',aggregate_kind:'thread',stream_id:'thread',
    event_type:'thread.session-set',occurred_at:time,command_id:command,correlation_id:command,causation_event_id:null,
    actor_kind:'client',metadata:{persistedEventSchemaVersion:1},payload:{threadId:'thread',session:{threadId:'thread',
      status:'interrupted',providerName:'acode',runtimeMode:'full-access',activeTurnId:null,lastError:null,updatedAt:time}},
    receipt:{command_id:command,aggregate_kind:'thread',aggregate_id:'thread',accepted_at:time,result_sequence:2,
      status:'accepted',error:null,fingerprint_version:1,command_fingerprint:'a'.repeat(64)}}];
  return f;
}
test('native restart reconciliation confirms stopped failure but retains the missing provider terminal', () => {
  const f=reconciledFixture(),proof=derive(f);
  assert.equal(proof.profile,RUNTIME_INTERRUPTION_RECONCILED_PROFILE);
  assert.equal(proof.provider_terminal_sequence,null);
  assert.equal(proof.provider_projection.status,'partial-before-native-restart-reconciliation');
  assert.equal(proof.provider_projection.fabricated_rows,0);
  assert.equal(proof.cancellation_confirmed,true);
  assert.equal(proof.human_cancellation_inferred,false);
  assert.equal(proof.scoreability_changed,false);
  assert.equal(proof.native_reconciliation.sequence,2);
  const absent=reconciledFixture();delete absent.native.restart_reconciliations;
  assert.throws(()=>derive(absent),/PROVIDER_TERMINAL_AMBIGUOUS/);
  const patches=[
    f=>f.native.restart_reconciliations.push(structuredClone(f.native.restart_reconciliations[0])),
    f=>f.native.restart_reconciliations[0].payload.session.status='running',
    f=>f.native.restart_reconciliations[0].payload.session.activeTurnId='turn',
    f=>f.native.restart_reconciliations[0].stream_id='foreign',
    f=>f.native.restart_reconciliations[0].command_id='user-interrupt',
    f=>f.native.restart_reconciliations[0].receipt.result_sequence=3,
    f=>f.native.restart_reconciliations[0].receipt.status='rejected',
    f=>f.native.restart_reconciliations[0].receipt.command_fingerprint='invalid',
    f=>f.native.runtime_turn_event_count=2,
    f=>f.provider[0].event.turnId='foreign',
    f=>f.provider[0].event_type=f.provider[0].event.type='unknown.lifecycle',
  ];
  for(const patch of patches){const changed=reconciledFixture();patch(changed);assert.throws(()=>derive(changed),/RECONCILIATION_/);}
  const contradiction=reconciledFixture();contradiction.provider.push(fixture().provider[0]);
  contradiction.provider.at(-1).event.payload.state='completed';
  assert.throws(()=>derive(contradiction),/PROVIDER_SDK_MISMATCH/);
});
test('a missing provider projection is explicitly partial and needs verified zero native turn rows', () => {
  const f=fixture();f.native.runtime_turn_event_count=0;
  const p=deriveRuntimeInterruption(bytes(f.state),f.index,lines(f.sdk),Buffer.alloc(0),f.native);
  assert.equal(p.profile,RUNTIME_INTERRUPTION_MISSING_PROFILE);
  assert.equal(p.provider_terminal_sequence,null);assert.equal(p.provider_projection.evidence_completeness,'partial');
  for (const count of [undefined,1,null]) {
    assert.throws(()=>deriveRuntimeInterruption(bytes(f.state),f.index,lines(f.sdk),Buffer.alloc(0),
      {...f.native,runtime_turn_event_count:count}),/PROVIDER_TERMINAL_AMBIGUOUS/);
  }
  assert.throws(()=>deriveRuntimeInterruption(bytes(f.state),f.index,lines(f.sdk),Buffer.from('{}\n'),f.native),/PROVIDER_TERMINAL_AMBIGUOUS/);
});
test('resource-only mirrors cannot stand for activity and must match the complete original SDK usage', () => {
  const f=fixture(),total={input_tokens:10,cached_input_tokens:5,output_tokens:2,reasoning_output_tokens:0,total_tokens:12};
  f.sdk.splice(-1,0,{type:'event_msg',payload:{type:'token_count',info:{total_token_usage:total,last_token_usage:total}}});
  const usage={totalTokens:12,inputTokens:10,cachedInputTokens:5,outputTokens:2,reasoningOutputTokens:0};
  const row={sequence:1,event_type:'thread.token-usage.updated',thread_id:'thread',turn_id:'turn',event:{type:'thread.token-usage.updated',
    threadId:'thread',turnId:'turn',providerRefs:{providerThreadId:'sdk',providerTurnId:'turn'},
    raw:{source:'acode',method:'thread/tokenUsage/updated',payload:{threadId:'sdk',turnId:'turn',tokenUsage:{total:usage,last:usage}}},
    payload:{usage:{totalProcessedTokens:12,totalInputTokens:10,totalCachedInputTokens:5,totalOutputTokens:2,totalReasoningOutputTokens:0,
      lastUsedTokens:12,lastInputTokens:10,lastCachedInputTokens:5,lastOutputTokens:2,lastReasoningOutputTokens:0}}}};
  f.native.runtime_turn_event_count=1;
  const proof=deriveRuntimeInterruption(bytes(f.state),f.index,lines(f.sdk),lines([row]),f.native);
  assert.equal(proof.profile,RUNTIME_INTERRUPTION_MISSING_PROFILE);
  assert.equal(proof.provider_projection.status,'verified-resource-only-at-collection');
  assert.equal(proof.provider_terminal_sequence,null);
  const wrong=structuredClone(row);wrong.event.payload.usage.totalInputTokens=11;
  assert.throws(()=>deriveRuntimeInterruption(bytes(f.state),f.index,lines(f.sdk),lines([wrong]),f.native),/PROVIDER_TERMINAL_AMBIGUOUS/);
  const activity=structuredClone(row);activity.event_type='item.started';
  assert.throws(()=>deriveRuntimeInterruption(bytes(f.state),f.index,lines(f.sdk),lines([activity]),f.native),/PROVIDER_TERMINAL_AMBIGUOUS/);
});
test('runtime interruption needs independently matching SQL, original SDK and provider terminal identities', () => {
  const f = fixture(), proof = derive(f);
  assert.equal(proof.cancellation_confirmed,true); assert.equal(proof.native_termination_origin,'runtime');
  assert.equal(proof.human_cancellation_inferred,false); assert.equal(proof.scoreability_changed,false);
  for (const patch of [{ termination_origin:'client' },{ latest_turn_id:'other' },{ active_turn_id:'turn' },
    { pending_count:1 },{ cwd:'/other' },{ session_status:'running' }]) {
    assert.throws(()=>derive({ ...fixture(),native:{ ...f.native,...patch } }),/NATIVE_NOT_TERMINAL/);
  }
  const foreign=fixture();foreign.provider[0].event.providerRefs.providerThreadId='foreign';
  assert.throws(()=>derive(foreign),/PROVIDER_SDK_MISMATCH/);
  const human=fixture();human.sdk.at(-1).payload.reason='user';assert.throws(()=>derive(human),/SDK_NOT_INTERRUPTED/);
  const duplicate=fixture();duplicate.sdk.push(duplicate.sdk.at(-1));assert.throws(()=>derive(duplicate),/SDK_NOT_INTERRUPTED/);
  const sentTwice=fixture();sentTwice.state.send.dispatch_attempt_count=2;assert.throws(()=>derive(sentTwice),/STATE_UNBOUND/);
});
test('archived failure confirmation rejects changed state, missing evidence, changed proof and mixed source bytes', async () => {
  const root=await mkdtemp(join(tmpdir(),'runtime-interruption-test-'));
  try {
    const f=fixture(), proof=derive(f), state=bytes(f.state), index=structuredClone(f.index);
    const sources=[[RUNTIME_INTERRUPTION_STATE,state],[RUNTIME_INTERRUPTION_NATIVE,bytes(f.native)],
      [RUNTIME_INTERRUPTION_PROOF,bytes(proof)],['raw/astronstudio-rollout.jsonl',lines(f.sdk)],
      ['raw/astronstudio-provider-events.jsonl',lines(f.provider)]];
    index.runtime_interruption_profile={id:RUNTIME_INTERRUPTION_PROFILE};index.raw_trace=[];index.binding_evidence=[];
    for (const [path,body] of sources) { const out=join(root,path);await mkdir(join(out,'..'),{recursive:true});await writeFile(out,body);
      (path.startsWith('raw/')?index.raw_trace:index.binding_evidence).push({path,size:body.length,sha256:hash(body)}); }
    const result=await verifyRuntimeInterruption(index,state,root);assert.deepEqual(result,proof);
    await assert.rejects(verifyRuntimeInterruption(index,bytes({...f.state,phase:'COMPLETED'}),root),/STATE_DRIFT/);
    const missing=structuredClone(index);missing.binding_evidence.pop();await assert.rejects(verifyRuntimeInterruption(missing,state,root),/ARTIFACT_AMBIGUOUS/);
    const proofPath=join(root,RUNTIME_INTERRUPTION_PROOF);await writeFile(proofPath,bytes({...proof,scoreability_changed:true}));
    await assert.rejects(verifyRuntimeInterruption(index,state,root),/ARTIFACT_DRIFT/);
    const changed=await readFile(proofPath), reference=index.binding_evidence.find(r=>r.path===RUNTIME_INTERRUPTION_PROOF);
    reference.sha256=hash(changed);reference.size=changed.length;
    await assert.rejects(verifyRuntimeInterruption(index,state,root),/PROOF_DRIFT/);
  } finally { await rm(root,{recursive:true,force:true}); }
});
