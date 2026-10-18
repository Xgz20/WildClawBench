import test from 'node:test';import assert from 'node:assert/strict';
import vm from 'node:vm';
import {verifyRecordedConfiguration,waitForAStudioFrozenUi,waitForAStudioForeground,dispatchAStudioOnce,clickAStudioStableTarget,aStudioConfigurationFields,aStudioDomSubmitExpression,aStudioAcceptanceState} from '../../eval_memory_e2e/native/astronstudio.mjs';
const session={turn_id:'owned-turn',cwd:'/tmp/owned'};
const frozen={model_display:'Spark-X2.5',reasoning:'High',permissions:'完全访问'};
const context=()=>({turn_id:'owned-turn',cwd:'/tmp/owned',model:'builtin/'+Buffer.from('spark-x2.5').toString('base64url'),effort:'high',approval_policy:'never',sandbox_policy:{type:'danger-full-access'}});
const bytes=value=>Buffer.from(JSON.stringify({type:'turn_context',payload:value})+'\n');
test('AStudio separates the frozen request from another view default and still reads the initial live configuration',()=>{
  const ui={model:'Auto',reasoning:'Low',permission:'ask'};
  assert.deepEqual(aStudioConfigurationFields(ui,frozen),frozen);
  assert.deepEqual(aStudioConfigurationFields(ui),{model_display:'Auto',reasoning:'Low',permissions:'ask'});
  assert.throws(()=>verifyRecordedConfiguration(bytes({...context(),model:'other-model'}),session,frozen));
});
test('AStudio rechecks the send point after hover and presses the stable point only once',async()=>{
  const events=[];let reads=0;const first={ready:true,thread_id:'owned',x:100,y:100},moved={...first,y:180};
  const result=await clickAStudioStableTarget({send:async(_,event)=>events.push(event)},'prompt','/workspace',{read:async()=>++reads===1?first:moved,pause:async()=>{}});
  assert.equal(result.clicked,true);assert.equal(events.filter(e=>e.type==='mousePressed').length,1);
  assert.equal(events.find(e=>e.type==='mousePressed').y,180);assert.equal(events.find(e=>e.type==='mousePressed').buttons,1);
});
test('AStudio never presses a send target that disappears or changes route after hover',async()=>{
  for(const changed of [{ready:false},{ready:true,thread_id:'other',x:100,y:100}]){
    const events=[];let reads=0;
    const result=await clickAStudioStableTarget({send:async(_,event)=>events.push(event)},'prompt','/workspace',{read:async()=>++reads===1?{ready:true,thread_id:'owned',x:100,y:100}:changed,pause:async()=>{}});
    assert.equal(result.clicked,false);assert.equal(events.filter(e=>e.type==='mousePressed').length,0);
  }
});
test('AStudio rejects a final layout shift before any mouse press',async()=>{
  const events=[];let reads=0;
  const result=await clickAStudioStableTarget({send:async(_,event)=>events.push(event)},'prompt','/workspace',{read:async()=>({ready:true,thread_id:'owned',x:100,y:++reads===3?180:100}),pause:async()=>{}});
  assert.equal(result.clicked,false);assert.equal(events.filter(e=>e.type==='mousePressed').length,0);
});
test('a false AStudio click result is a recorded pre-send rejection, never a dispatched operation',async()=>{
  const phases=[],state={};let calls=0;
  const result=await dispatchAStudioOnce(state,async()=>{calls++;return {clicked:false,ready:false,reason:'obscured'}},async s=>phases.push(s.phase));
  assert.equal(result.clicked,false);assert.equal(calls,1);assert.deepEqual(phases,['invoking','pre_send_rejected']);
});
test('an unknown AStudio click outcome remains invoking and cannot be replayed',async()=>{
  const phases=[],state={};let calls=0;
  await assert.rejects(()=>dispatchAStudioOnce(state,async()=>{calls++;throw Error('transport lost')},async s=>phases.push(s.phase)),/transport lost/);
  assert.equal(calls,1);assert.equal(state.phase,'invoking');assert.deepEqual(phases,['invoking']);
});
test('a returned AStudio click is recorded once without claiming native acceptance',async()=>{
  const phases=[],state={};let calls=0;
  await dispatchAStudioOnce(state,async()=>{calls++;return {clicked:true}},async s=>phases.push(s.phase));
  assert.equal(calls,1);assert.deepEqual(phases,['invoking','invoked']);assert.equal(state.native,undefined);
});
test('AStudio UI preparation waits for the verified native application to activate',async()=>{
  let calls=0;const result=await waitForAStudioForeground(42,{attempts:2,read:async()=>++calls===1?99:42,pause:async()=>{}});
  assert.equal(result.verified,true);assert.equal(calls,2);
});
test('another or unknown foreground owner never admits AStudio UI preparation',async()=>{
  for(const value of [99,NaN,null])await assert.rejects(()=>waitForAStudioForeground(42,{attempts:2,read:async()=>value,pause:async()=>{}}),/OWNER_UNVERIFIED/);
});
test('AStudio waits for the frozen model after navigation without changing model settings',async()=>{
  let calls=0;const ready={thread_id:'new-thread',model_count:1,model:'Spark-X2.5',reasoning:'High',permission_count:1,permission:'完全访问'};
  const result=await waitForAStudioFrozenUi(async()=>++calls===1?{...ready,model:'Auto'}:ready,frozen,'new-thread',{attempts:2,pause:async()=>{}});
  assert.equal(calls,2);assert.equal(result.observations[0].model,'Auto');assert.equal(result.ui.model,'Spark-X2.5');
});
test('AStudio hydration cannot accept another route or permission',async()=>{
  const ready={thread_id:'new-thread',model_count:1,model:'Spark-X2.5',reasoning:'High',permission_count:1,permission:'完全访问'};
  await assert.rejects(()=>waitForAStudioFrozenUi(async()=>({...ready,thread_id:'other'}),frozen,'new-thread',{attempts:2,pause:async()=>{}}),/ROUTE_CHANGED/);
  await assert.rejects(()=>waitForAStudioFrozenUi(async()=>({...ready,permission:'ask'}),frozen,'new-thread',{attempts:2,pause:async()=>{}}),/NOT_READY/);
});
test('AStudio observation binds configuration from the exact native turn when the UI hides controls',()=>{
  assert.equal(verifyRecordedConfiguration(bytes(context()),session,frozen).decoded_model_id,'spark-x2.5');
});
test('a different native turn, model, reasoning or permission cannot close a memory step',()=>{
  for(const change of [x=>x.turn_id='other',x=>x.model='other-model',x=>x.effort='low',x=>x.cwd='/other',x=>x.sandbox_policy.type='workspace-write']){
    const value=context();change(value);assert.throws(()=>verifyRecordedConfiguration(bytes(value),session,frozen));
  }
});
function domSubmitFixture({prompt='owned prompt',route='#/owned',foreignForm=false,obscured=false}={}) {
  let clicks=0;const listeners=new Map(),visible={getClientRects:()=>[{}]};
  const form={checkValidity:()=>true,addEventListener:(k,f)=>listeners.set(k,f),removeEventListener:k=>listeners.delete(k)};
  const editor={...visible,innerText:prompt,closest:()=>foreignForm?{}:form};
  const workspace={...visible,getAttribute:()=>'/owned'};
  const button={...visible,form,disabled:false,getBoundingClientRect:()=>({left:1,top:1,width:20,height:20}),contains:e=>e===button,
    addEventListener:(k,f)=>listeners.set(k,f),removeEventListener:k=>listeners.delete(k),
    click:()=>{clicks++;for(const type of ['click','submit'])listeners.get(type)?.({type,isTrusted:false,defaultPrevented:false})}};
  const document={elementFromPoint:()=>obscured?{}:button,querySelectorAll:s=>s.includes('composer-editor')?[editor]:s.includes('workspace-picker')?[workspace]:s.includes('button[type')?[button]:[]};
  const result=vm.runInNewContext(aStudioDomSubmitExpression('owned prompt','/owned','owned'),{document,location:{hash:route},getComputedStyle:()=>({visibility:'visible'})});
  return {result,clicks,listeners};
}
test('AStudio DOM send checks form ownership and records a single click/submit without claiming native acceptance',()=>{
  const {result,clicks,listeners}=domSubmitFixture();assert.equal(clicks,1);assert.equal(result.clicked,true);
  assert.equal(result.dom_events.map(e=>e.type).join(','),'click,submit');assert.equal(listeners.size,0);
  assert.equal(result.native,undefined);
});
test('AStudio atomic DOM send cannot click after prompt/route drift, a foreign form or an obscured target',()=>{
  for(const options of [{prompt:'different'},{route:'#/other'},{foreignForm:true},{obscured:true}]) {
    const {result,clicks}=domSubmitFixture(options);assert.equal(result.clicked,false);assert.equal(clicks,0);
  }
});
test('AStudio identity wait is separate from model execution and old unknown sends are never replayed',()=>{
  const now=Date.now(),state={phase:'invoked',click_returned_at:new Date(now-1000).toISOString()};
  assert.equal(aStudioAcceptanceState(state,now),'pending');
  assert.equal(aStudioAcceptanceState(state,now+30000),'unconfirmed');
  assert.equal(aStudioAcceptanceState({phase:'invoked'},now),'unconfirmed');
  assert.equal(aStudioAcceptanceState({phase:'prepared'},now),'not_started');
});
