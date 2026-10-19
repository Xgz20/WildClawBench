import test from 'node:test';import assert from 'node:assert/strict';
import vm from 'node:vm';
import {verifyRecordedConfiguration,aStudioCatalogModelId,aStudioGatewayCatalogProjection,aStudioTransportProfileForSource,readAStudioRpcTransport,waitForAStudioRpcReady,waitForAStudioFrozenUi,waitForAStudioForeground,dispatchAStudioOnce,clickAStudioStableTarget,aStudioConfigurationFields,aStudioDomSubmitExpression,aStudioAcceptanceState} from '../../eval_memory_e2e/native/astronstudio.mjs';
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
test('an offline RPC transport prevents a mouse press even when the send point is stable',async()=>{
  const events=[];const result=await clickAStudioStableTarget({send:async(_,v)=>events.push(v)},'p','/w',{
    read:async()=>({ready:true,thread_id:'owned',x:1,y:2}),beforePress:async()=>({ready:false,open_count:0}),pause:async()=>{}});
  assert.equal(result.clicked,false);assert.equal(result.mouse_press_count,0);assert.equal(events.some(x=>x.type==='mousePressed'),false);
});
test('a target that moves during the asynchronous RPC check is never pressed',async()=>{
  const events=[];let moved=false;
  const result=await clickAStudioStableTarget({send:async(_,v)=>events.push(v)},'p','/w',{
    read:async()=>({ready:true,thread_id:'owned',x:moved?20:1,y:2}),beforePress:async()=>{moved=true;return {ready:true}},pause:async()=>{}});
  assert.equal(result.clicked,false);assert.equal(events.some(x=>x.type==='mousePressed'),false);
});
test('RPC readiness requires consecutive observations of the same live connection identity',async()=>{
  const ready=id=>({ready:true,identities:[{server_instance:id}]});let i=0;
  const sequence=[{ready:false},ready('old'),ready('new'),ready('new')];
  const result=await waitForAStudioRpcReady(async()=>sequence[i++],{attempts:4,pause:async()=>{}});
  assert.equal(result.samples,4);
  await assert.rejects(()=>waitForAStudioRpcReady(async()=>({ready:false}),{attempts:2,pause:async()=>{}}),/TRANSPORT_NOT_READY/);
});
test('the transport getter read rejects offline and unknown states and never returns the auth token',async()=>{
  for(const state of ['open','connecting','closed','authentication-required','unknown']) {
    function getter(){return state}
    const profile={url:'acode://app/assets/already-loaded.js',getter:'h',getter_source:String(getter),sha256:'verified-source'};
    const client={evaluate:async expression=>{
      assert.equal(expression.includes('new WebSocket'),false);assert.equal(expression.includes('queryObjects'),false);
      return vm.runInNewContext(expression.replace(/await import\([^)]*\)/,'__loadedModule'),{
        __loadedModule:{h:getter},URL,window:{desktopBridge:{getWsUrl:async()=>'ws://127.0.0.1:1234/?token=PRIVATE_AUTH'}}});
    }};
    if(state==='unknown'){await assert.rejects(()=>readAStudioRpcTransport(client,{readProfile:async()=>profile}),/STATE_UNVERIFIED/);continue}
    const observed=await readAStudioRpcTransport(client,{readProfile:async()=>profile});
    assert.equal(observed.ready,state==='open');assert.equal(JSON.stringify(observed).includes('PRIVATE_AUTH'),false);
  }
  assert.throws(()=>aStudioTransportProfileForSource('unknown-source','acode://app/assets/with-selector-DcLfjZsV.js'),/SOURCE_UNVERIFIED/);
  assert.throws(()=>aStudioTransportProfileForSource('unknown-source','https://other.invalid/asset.js'),/SOURCE_UNVERIFIED/);
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
const aliasFrozen={model_display:'GLM-5.2',reasoning:'High',permissions:'完全访问',account_fingerprint:'owned-account'};
const aliasCatalog=()=>({source_kind:'astudio-scoped-model-catalog/v1',account_fingerprint:'owned-account',account_scope_hash:'owned-scope',
  catalog:{schemaVersion:1,accountScopeHash:'owned-scope',fetchedAt:'2026-10-19T03:02:52.885Z',models:[{name:'GLM-5.2',slug:'xopglm52'}]}});
test('gateway catalog projection binds the auth account and omits profile credentials and model instructions',()=>{
  const raw={version:1,accountHash:'owned-account',refreshedAt:1792379073816,
    builtins:{models:[{slug:'xopglm52',display_name:'GLM-5.2',base_instructions:'PRIVATE INSTRUCTIONS'}]},customProfiles:[{apiKey:'SECRET'}]};
  const projection=aStudioGatewayCatalogProjection(raw,'owned-account');
  assert.equal(aStudioCatalogModelId(projection,'owned-account','GLM-5.2'),'xopglm52');
  assert.equal(JSON.stringify(projection).includes('SECRET'),false);assert.equal(JSON.stringify(projection).includes('PRIVATE'),false);
  assert.throws(()=>aStudioGatewayCatalogProjection(raw,'another-account'),/SCOPE_UNVERIFIED/);
});
test('AStudio verifies a UI model alias only through its exact account-scoped catalog mapping',()=>{
  const value={...context(),model:'builtin/'+Buffer.from('xopglm52').toString('base64url')};
  assert.throws(()=>verifyRecordedConfiguration(bytes(value),session,aliasFrozen),/CONFIGURATION_MISMATCH/);
  const proof=verifyRecordedConfiguration(bytes(value),session,aliasFrozen,aliasCatalog());
  assert.equal(proof.decoded_model_id,'xopglm52');assert.equal(proof.model_identity_basis,'account-scoped-catalog-name-to-slug');
});
test('another account, catalog scope, ambiguous name or unrelated slug cannot admit an alias',()=>{
  const value={...context(),model:'xopglm52'};
  for(const change of [p=>p.account_fingerprint='other',p=>p.catalog.accountScopeHash='other',
    p=>p.catalog.models.push({name:'GLM-5.2',slug:'other'}),p=>p.catalog.models[0].slug='other',p=>p.catalog.fetchedAt='invalid']) {
    const proof=aliasCatalog();change(proof);assert.throws(()=>verifyRecordedConfiguration(bytes(value),session,aliasFrozen,proof));
  }
  assert.throws(()=>aStudioCatalogModelId(aliasCatalog().catalog,'other','GLM-5.2'),/SCOPE_UNVERIFIED/);
});
test('a native ID equal to the UI label cannot bypass a different catalog slug',()=>{
  assert.throws(()=>verifyRecordedConfiguration(bytes({...context(),model:'GLM-5.2'}),session,aliasFrozen,aliasCatalog()),/CONFIGURATION_MISMATCH/);
});
test('catalog aliases preserve the turn, cwd, reasoning and permission checks',()=>{
  for(const change of [v=>v.turn_id='other',v=>v.cwd='/other',v=>v.effort='low',v=>v.approval_policy='on-request',v=>v.sandbox_policy={type:'workspace-write'}]) {
    const value={...context(),model:'xopglm52'};change(value);
    assert.throws(()=>verifyRecordedConfiguration(bytes(value),session,aliasFrozen,aliasCatalog()));
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
