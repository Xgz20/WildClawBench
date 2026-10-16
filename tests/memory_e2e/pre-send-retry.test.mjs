import test from 'node:test';
import assert from 'node:assert/strict';
import {assertMemoryPreSendRetry,readQwenMemoryOperationUi} from '../../eval_memory_e2e/native/common.mjs';
test('an already sent Qwen observation does not wait for hidden composer settings',async()=>{
  let calls=0;const result=await readQwenMemoryOperationUi({transportAction:'observe',frozen:{model_display:'frozen'}},async()=>{calls++;throw Error('hidden controls');});
  assert.equal(calls,0);assert.equal(result.basis,'frozen_pre_send_pending_terminal_readback');assert.equal(result.ui,null);
});
test('Qwen dispatch still reads the current UI configuration',async()=>{
  let calls=0;const ui={model:{actual_model:'frozen'}};
  const result=await readQwenMemoryOperationUi({transportAction:'dispatch',frozen:{model_display:'frozen'}},async()=>{calls++;return ui;});
  assert.equal(calls,1);assert.equal(result.ui,ui);assert.equal(result.basis,'live_ui');
});
test('Qwen terminal evidence cannot substitute a frozen configuration for missing controls',async()=>{
  await assert.rejects(()=>readQwenMemoryOperationUi({transportAction:'observe',frozen:{model_display:'frozen'},terminal:true},async()=>{throw Error('terminal controls unavailable')}),/terminal controls unavailable/);
});
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
