import test from 'node:test';import assert from 'node:assert/strict';
import {verifyRecordedConfiguration} from '../../eval_memory_e2e/native/astronstudio.mjs';
const session={turn_id:'owned-turn',cwd:'/tmp/owned'};
const frozen={model_display:'Spark-X2.5',reasoning:'High',permissions:'完全访问'};
const context=()=>({turn_id:'owned-turn',cwd:'/tmp/owned',model:'builtin/'+Buffer.from('spark-x2.5').toString('base64url'),effort:'high',approval_policy:'never',sandbox_policy:{type:'danger-full-access'}});
const bytes=value=>Buffer.from(JSON.stringify({type:'turn_context',payload:value})+'\n');
test('AStudio observation binds configuration from the exact native turn when the UI hides controls',()=>{
  assert.equal(verifyRecordedConfiguration(bytes(context()),session,frozen).decoded_model_id,'spark-x2.5');
});
test('a different native turn, model, reasoning or permission cannot close a memory step',()=>{
  for(const change of [x=>x.turn_id='other',x=>x.model='other-model',x=>x.effort='low',x=>x.cwd='/other',x=>x.sandbox_policy.type='workspace-write']){
    const value=context();change(value);assert.throws(()=>verifyRecordedConfiguration(bytes(value),session,frozen));
  }
});
