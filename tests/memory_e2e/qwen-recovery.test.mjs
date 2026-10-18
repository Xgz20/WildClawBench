import test from 'node:test';import assert from 'node:assert/strict';
import {assertMemoryQwenRecoveryOwner,recoverMemoryQwenLock} from '../../eval_memory_e2e/native/recover-qwen-lock.mjs';
test('Qwen Memory recovery requires the exact original lock and a verifiably dead process',()=>{
  const owner={schema_version:'wildclawbench.general-e2e-qwenwork-attempt-lock/v1',owner_id:'owned',attempt_id:'a01',state_file:'/native/journal',process_start_identity:'original'};
  const input={expected_owner_id:'owned'},cfg={identity:{attempt_id:'a01'},state_file:'/native/journal'};
  assert.doesNotThrow(()=>assertMemoryQwenRecoveryOwner(owner,input,cfg,{verifiable:true,stale:true,active:false}));
  for(const status of [{verifiable:false,stale:true},{verifiable:true,stale:false},{verifiable:true,stale:true,active:true}])
    assert.throws(()=>assertMemoryQwenRecoveryOwner(owner,input,cfg,status));
  for(const change of [{owner_id:'foreign'},{state_file:'/other'},{process_start_identity:null}])
    assert.throws(()=>assertMemoryQwenRecoveryOwner({...owner,...change},input,cfg,{verifiable:true,stale:true,active:false}));
});
test('recovery rejects a foreign root or invalid owner before filesystem access',async()=>{
  await assert.rejects(()=>recoverMemoryQwenLock({root:'/Users/gzx/.codex',expected_owner_id:'foreign'}),/SCOPE/);
});
