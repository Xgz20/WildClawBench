import test from 'node:test';
import assert from 'node:assert/strict';
import {requestedModelReady} from '../../eval_memory_e2e/native/workbuddy.mjs';
const history=(state,name)=>({request:{requestedModel:name===null?null:{name}},runtime_terminal:{request_state:state}});
test('incomplete requested-model metadata remains observable without becoming an accepted final config',()=>{
  assert.equal(requestedModelReady(history('running',null),'model-x'),false);
  assert.equal(requestedModelReady(history('running','initial-placeholder'),'model-x'),false);
  assert.equal(requestedModelReady(history('running','model-x'),'model-x'),true);
});
test('a completed request must name the exact frozen model',()=>{
  assert.equal(requestedModelReady(history('success','model-x'),'model-x'),true);
  assert.throws(()=>requestedModelReady(history('success',null),'model-x'),/MISMATCH/);
  assert.throws(()=>requestedModelReady(history('success','other-model'),'model-x'),/MISMATCH/);
});
test('the custom-local wire mapping is admitted only by a verified private unit',()=>{
  assert.throws(()=>requestedModelReady(history('success','custom-local:xopglm52'),'xopglm52'),/MISMATCH/);
  assert.equal(requestedModelReady(history('success','custom-local:xopglm52'),'xopglm52',true),true);
  assert.throws(()=>requestedModelReady(history('success','glm-5.2'),'xopglm52',true),/MISMATCH/);
  assert.throws(()=>requestedModelReady(history('success','custom-local:other'),'xopglm52',true),/MISMATCH/);
});
