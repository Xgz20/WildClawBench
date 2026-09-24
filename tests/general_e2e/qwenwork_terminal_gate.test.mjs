import assert from 'node:assert/strict';import{test}from'node:test';
import{verifyQwenNativeTerminal}from'../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/terminal-gate.mjs';
const rows=reason=>[{type:'turn.started',turn_id:'main',data:{is_subagent:false}},{type:'turn.finished',turn_id:'main',data:{reason}}];
const state=(business='completed',native='completed')=>({phase:business==='completed'?'COMPLETED':'FAILED',execution:{business_status:business,cancellation_confirmed:business==='cancelled'},extensions:{qwenwork:{native_status:native}}});
test('Native cancellation is accepted only with consistent database state, explicit stop proof and abort log',()=>{
 assert.equal(verifyQwenNativeTerminal(state('cancelled','cancelled'),rows('abort')).business_status,'cancelled');
 for(const bad of [state(),state('cancelled','completed'),{...state('cancelled','cancelled'),execution:{business_status:'cancelled',cancellation_confirmed:false}}]){
  assert.throws(()=>verifyQwenNativeTerminal(bad,rows('abort')),/TERMINAL_MISMATCH/);
 }
 assert.throws(()=>verifyQwenNativeTerminal(state('cancelled','cancelled'),rows('end_turn')),/TERMINAL_MISMATCH/);
});
test('Tool errors do not imply a final failure; unknown reason and subagent finishes cannot establish completion',()=>{
 assert.equal(verifyQwenNativeTerminal(state(),[...rows('end_turn'),{type:'tool.finished',data:{status:'error'}}]).verified,true);
 assert.throws(()=>verifyQwenNativeTerminal(state(),rows('unknown')),/TERMINAL_MISMATCH/);
 const incomplete=rows('end_turn');incomplete[1].turn_id='child';assert.throws(()=>verifyQwenNativeTerminal(state(),incomplete),/FINISH_UNVERIFIED/);
 assert.throws(()=>verifyQwenNativeTerminal(state(),[...rows('end_turn'),rows('end_turn')[1]]),/FINISH_UNVERIFIED/);
});
test('Declared native final failure must agree with the native finish reason and error class',()=>{
 const failed=state('infrastructure_error','failed');failed.execution.error={code:'QWENWORK_NATIVE_FAILURE'};
 assert.equal(verifyQwenNativeTerminal(failed,rows('error')).verified,true);
 assert.throws(()=>verifyQwenNativeTerminal(failed,rows('completed')),/TERMINAL_MISMATCH/);
 assert.throws(()=>verifyQwenNativeTerminal(state(),rows('error')),/TERMINAL_MISMATCH/);
});
