import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, writeFile, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { deriveRuntimeInterruption, verifyRuntimeInterruption, RUNTIME_INTERRUPTION_PROFILE,
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
