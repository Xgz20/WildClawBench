import test from 'node:test';
import assert from 'node:assert/strict';
import {assertMemoryPreSendRetry} from '../../eval_memory_e2e/native/common.mjs';
const qwen=()=>({phase:'PREPARING',prompt:{send_status:'not_sent'},send:{dispatch_attempt_count:0,state:'not_reserved',reservation_id:null,invoking_at:null,returned_at:null},session:{verified:false}});
const doubao=()=>({phase:'INFRA_FAILED',error:{code:'DEVELOPMENT_PRE_SEND_FAILED'},send:{dispatch_attempt_count:0,intent_persisted_at:null,dispatch_started_at:null,click_returned_at:null,accepted_at:null},session:{},timing:{}});
test('explicit memory retry admits only a proven zero-send preparation',()=>{
  assert.equal(assertMemoryPreSendRetry('QwenWork',qwen()),true);
  assert.equal(assertMemoryPreSendRetry('DoubaoWork',doubao()),true);
});
test('a native intent, reservation, invoking boundary or identity always blocks retry',()=>{
  for(const [harness,make] of [['QwenWork',qwen],['DoubaoWork',doubao]]){
    for(const mutate of [j=>j.send.dispatch_attempt_count=1,j=>j.session.conversation_id='accepted',
      j=>j.session.verified=true,j=>{if(harness==='QwenWork')j.send.reservation_id='reserved';else j.send.intent_persisted_at='time'},
      j=>{if(harness==='QwenWork')j.prompt.send_status='intent_persisted';else j.send.dispatch_started_at='time'}]){
      const j=make();mutate(j);assert.throws(()=>assertMemoryPreSendRetry(harness,j),/REJECTED/);
    }
  }
  assert.throws(()=>assertMemoryPreSendRetry('WorkBuddy',qwen()),/NOT_SUPPORTED/);
});
