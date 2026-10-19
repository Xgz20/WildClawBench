import test from 'node:test';import assert from 'node:assert/strict';
import vm from 'node:vm';
import {verifyRecordedConfiguration,aStudioCatalogModelId,aStudioGatewayCatalogProjection,aStudioTransportProfileForSource,readAStudioRpcTransport,waitForAStudioRpcReady,waitForAStudioClickTransport,aStudioNativeObservationEligible,connectAStudioNativeObservation,aStudioProjectUiExpression,aStudioProjectNavigationExpression,waitForAStudioReload,traceAStudioPreparation,waitForAStudioProjectBinding,waitForAStudioFrozenUi,waitForAStudioForeground,readAStudioForegroundPid,aStudioForegroundCheck,waitForAStudioSendFocus,dispatchAStudioOnce,aStudioSendEventsExpression,withAStudioSendEvents,clickAStudioStableTarget,aStudioConfigurationFields,aStudioCdpBudget,aStudioDomSubmitExpression,aStudioAcceptanceState} from '../../eval_memory_e2e/native/astronstudio.mjs';
import {requestHash} from '../../eval_memory_e2e/native/common.mjs';
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
test('a transient pre-click disconnect waits for stable open and presses only once',async()=>{
  let tick=0,reads=0;const events=[],sequence=[false,true,true];
  const result=await clickAStudioStableTarget({send:async(_,v)=>events.push(v)},'p','/w',{
    read:async()=>({ready:true,thread_id:'owned',x:1,y:2}),pause:async()=>{},
    beforePress:()=>waitForAStudioClickTransport(async()=>({ready:sequence[reads++],identities:[{host:'owned'}]}),{
      maxWaitMs:100,now:()=>tick,pause:async()=>{tick+=20}})});
  assert.equal(result.clicked,true);assert.equal(reads,3);assert.equal(events.filter(e=>e.type==='mousePressed').length,1);
});
test('pre-click wait expiry leaves zero presses and the legacy zero-wait policy remains unchanged',async()=>{
  let tick=0,reads=0;const read=async()=>{reads++;return {ready:false,state:'connecting'}};
  const old=await waitForAStudioClickTransport(read,{maxWaitMs:0,now:()=>tick});assert.equal(old.ready,false);assert.equal(reads,1);
  const events=[];const result=await clickAStudioStableTarget({send:async(_,v)=>events.push(v)},'p','/w',{
    read:async()=>({ready:true,thread_id:'owned',x:1,y:2}),pause:async()=>{},
    beforePress:()=>waitForAStudioClickTransport(read,{maxWaitMs:100,now:()=>tick,pause:async()=>{tick+=50}})});
  assert.equal(result.clicked,false);assert.equal(result.rpc.transport_wait_expired,true);assert.equal(events.some(e=>e.type==='mousePressed'),false);
  await assert.rejects(()=>waitForAStudioClickTransport(read,{maxWaitMs:Infinity}),/WAIT_POLICY/);
});
function sentObservation() {
  const config={app_version:'3.5.0',model_display:'GLM-5.2',reasoning:'High',permissions:'完全访问',account_fingerprint:'a'.repeat(64),memory_settings:{primary:{enabled:false}}};
  const request={mode:'native',harness:'AstronStudio',action:'execute_step',transport_action:'observe',expected_config:config};
  return {request,state:{phase:'invoked',thread_id:'12345678-1234-1234-1234-123456789abc',requestHash:requestHash(request),
    config,click_result:{clicked:true},click_returned_at:'2026-10-19T03:00:00.000Z'}};
}
test('native-only observation requires the exact sent intent and cannot become a first send',()=>{
  const original=sentObservation();assert.equal(aStudioNativeObservationEligible(original.request,original.state),true);
  for(const change of [x=>x.request.transport_action='dispatch',x=>x.request.mode='fixture',x=>x.request.harness='Codex',
    x=>x.state.phase='prepared',x=>x.state.phase='invoking',x=>x.state.phase='pre_send_rejected',
    x=>x.state.click_result.clicked=false,x=>x.state.requestHash='other',x=>x.state.thread_id='unverified',x=>x.state.click_returned_at='unknown']) {
    const value=structuredClone(original);change(value);assert.equal(aStudioNativeObservationEligible(value.request,value.state),false);
  }
});
test('native observation uses dispatch account evidence without UI or auth calls and rejects config drift',async()=>{
  const {state}=sentObservation();const calls=[];const deps={checkEnvironment:async()=>calls.push('environment'),
    readIdentity:()=>{calls.push('identity');return {pid:42,version:'3.5.0'}},
    readMemory:()=>{calls.push('memory');return structuredClone(state.config.memory_settings)}};
  const live=await connectAStudioNativeObservation(state,deps);
  assert.equal(live.client,null);assert.equal(live.observation_evidence.current_account_rechecked,false);
  assert.equal(live.observation_evidence.account_identity_basis,'verified-dispatch-auth-session-uid');
  assert.deepEqual(calls,['environment','identity','memory']);
  await assert.rejects(()=>connectAStudioNativeObservation(state,{...deps,readIdentity:()=>({pid:42,version:'other'})}),/NATIVE_CONFIG_DRIFT/);
  await assert.rejects(()=>connectAStudioNativeObservation(state,{...deps,readMemory:()=>({primary:{enabled:true}})}),/NATIVE_CONFIG_DRIFT/);
});
test('the opt-in native acceptance window does not change the legacy identity budget',()=>{
  const now=Date.now(),state={phase:'invoked',click_returned_at:new Date(now-31000).toISOString()};
  assert.equal(aStudioAcceptanceState(state,now),'unconfirmed');assert.equal(aStudioAcceptanceState(state,now,120),'pending');
  assert.equal(aStudioAcceptanceState(state,now+120000,120),'unconfirmed');
});
const projectReady=()=>({thread_id:'new',editor_count:1,editor_empty:true,workspace_count:1,workspace_path:'/owned',
  dialog_count:0,blocking_count:0,stable_ui:true,pristine:true,projects:[{project_id:'target',workspace_root:'/owned'}]});
test('the serialized project observation reads the visible route and full workspace path without mutations',()=>{
  const editor={getClientRects:()=>[1],innerText:''},workspace={getClientRects:()=>[1],getAttribute:()=>'/owned'};
  const document={querySelectorAll:s=>s.includes('composer-editor')?[editor]:s.includes('workspace-picker')?[workspace]:[]};
  const value=vm.runInNewContext(aStudioProjectUiExpression(),{document,location:{hash:'#/owned-thread'},getComputedStyle:()=>({visibility:'visible'})});
  assert.equal(value.thread_id,'owned-thread');assert.equal(value.workspace_path,'/owned');assert.equal(value.editor_empty,true);
});
test('workspace hydration refreshes the current route and accepts only exact native project binding',async()=>{
  let i=0;const ready=projectReady(),old={...ready,thread_id:'old',projects:[{project_id:'previous',workspace_root:'/previous'}]};
  const result=await waitForAStudioProjectBinding(async()=>i++===0?old:ready,'/owned','target',{attempts:2,pause:async()=>{}});
  assert.equal(result.observation.thread_id,'new');assert.equal(result.observations.length,2);
  await assert.rejects(()=>waitForAStudioProjectBinding(async()=>old,'/owned','target',{attempts:2,pause:async()=>{}}),/NOT_READY/);
});
test('project hydration never adopts a draft, another directory, a modal, active work or unstable UI',async()=>{
  for(const mutate of [x=>x.editor_empty=false,x=>x.workspace_path='/other',x=>x.dialog_count=1,x=>x.blocking_count=1,
    x=>x.projects.push({project_id:'duplicate',workspace_root:'/owned'}),x=>x.stable_ui=false,x=>x.pristine=false]) {
    const value=projectReady();mutate(value);
    await assert.rejects(()=>waitForAStudioProjectBinding(async()=>value,'/owned','target',{attempts:1,pause:async()=>{}}));
  }
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

function navigationDom(change=()=>{}) {
  let clicks=0;
  const visible={getClientRects:()=>[1]};
  const button={...visible,disabled:false,closest:()=>null,getAttribute:()=>'在 测试 中新建任务',
    getBoundingClientRect:()=>({x:20,y:20,width:30,height:20}),contains:e=>e===button,click:()=>clicks++};
  const motion={inert:false,getAttribute:()=>null};
  const row={closest:()=>motion,querySelectorAll:()=>[button]};
  const editor={...visible,innerText:''},workspace={...visible,getAttribute:()=>'/owned'};
  const env={document:{querySelectorAll:s=>s.includes('composer-editor')?[editor]:s.includes('workspace-picker')?[workspace]:s.includes('data-project-hover-anchor')?[row]:[],elementFromPoint:()=>button},
    location:{hash:'#/owned-thread'},getComputedStyle:()=>({visibility:'visible'}),innerWidth:500,innerHeight:500};
  change({env,editor,workspace,motion,row,button});return {env,clicks:()=>clicks};
}
test('exact project navigation clicks only its new-task button and rechecks safety atomically',()=>{
  const project='12345678-1234-1234-1234-123456789abc';
  for(const mutate of [null,x=>x.editor.innerText='draft',x=>x.env.location.hash='#/other',x=>x.motion.inert=true,
    x=>x.button.disabled=true,x=>x.row.querySelectorAll=()=>[x.button,x.button],x=>x.env.document.elementFromPoint=()=>({})]) {
    const dom=navigationDom(mutate??(()=>{}));
    const result=vm.runInNewContext(aStudioProjectNavigationExpression(project,'/owned','owned-thread','click'),dom.env);
    assert.equal(dom.clicks(),mutate?0:1);assert.equal(result.clicked,!mutate);
  }
  assert.throws(()=>aStudioProjectNavigationExpression('unsafe-selector','/owned','owned-thread','click'),/NAVIGATION_POLICY/);
});
test('preparation diagnostics retain the failed CDP call and callsite without payloads or replay',async()=>{
  let calls=0;const records=[];
  const client={send:async()=>{calls++;throw Error('timeout SECRET')},evaluate(expression){return this.send('Runtime.evaluate',{expression})}};
  await assert.rejects(()=>traceAStudioPreparation(client,c=>c.evaluate('SECRET_PAYLOAD'),async r=>records.push(r)),/timeout/);
  assert.equal(calls,1);assert.equal(records.length,1);assert.equal(records[0].commands[0].status,'failed');
  assert.equal(records[0].commands[0].method,'Runtime.evaluate');assert.equal(records[0].commands[0].expression_sha256.length,64);
  assert.equal(records[0].commands[0].call_site.length>0,true);assert.equal(JSON.stringify(records).includes('SECRET'),false);
  assert.equal(records[0].prompt_sent,false);
});

test('an idle projection reload runs once and waits through context replacement using only reads',async()=>{
  let reloaded=0,reads=0,tick=0;const methods=[];
  const client={send:async method=>{methods.push(method);return {frameTree:{frame:{id:'main',loaderId:reloaded?'new':'old'}}}},
    evaluate:async expression=>{assert.equal(expression,'document.readyState === "complete"');if(++reads===1)throw Error('Inspected target navigated or closed');return true;}};
  const result=await waitForAStudioReload(client,async()=>{reloaded++;return {native:'result'}},{maxWaitMs:50,now:()=>tick,pause:async()=>{tick+=10}});
  assert.equal(reloaded,1);assert.equal(reads,2);assert.equal(result.evidence.loader_id,'new');assert.equal(result.evidence.reload_count,1);
  assert.deepEqual(new Set(methods),new Set(['Page.getFrameTree']));
});
test('reload observation never repeats navigation on deadline, foreign frame or unknown error',async()=>{
  for(const mode of ['stale','foreign','unknown']){
    let reloads=0,tick=0;
    const client={send:async()=>({frameTree:{frame:{id:mode==='foreign'&&reloads?'other':'main',loaderId:mode==='stale'||!reloads?'old':'new'}}}),
      evaluate:async()=>{throw Error('unclassified failure')}};
    await assert.rejects(()=>waitForAStudioReload(client,async()=>{reloads++},{maxWaitMs:20,now:()=>tick,pause:async()=>{tick+=10}}));
    assert.equal(reloads,1);
  }
});
test('project binding uses an elapsed control budget even when native reads are slow',async()=>{
  let tick=0,reads=0;const value={...projectReady(),stable_ui:false};
  await assert.rejects(()=>waitForAStudioProjectBinding(async()=>{reads++;tick+=40;return value},'/owned','target',{
    attempts:150,maxWaitMs:30,now:()=>tick,pause:async()=>{}}),/NOT_READY/);
  assert.equal(reads,1);
});

function eventDom(){
  const queue=[],listeners=new Map();
  const element=name=>({getClientRects:()=>[1],addEventListener:(t,fn,c)=>{assert.equal(c,true);listeners.set(name+':'+t,fn)},
    removeEventListener:(t,fn,c)=>{assert.equal(listeners.get(name+':'+t),fn);assert.equal(c,true);listeners.delete(name+':'+t)}});
  const form=element('form'),button={...element('button'),form},editor={...element('editor'),closest:()=>form};
  const env=vm.createContext({document:{querySelectorAll:s=>s.includes('composer-editor')?[editor]:[button]},
    location:{hash:'#/owned-thread'},getComputedStyle:()=>({visibility:'visible'}),queueMicrotask:fn=>queue.push(fn)});
  return {listeners,env,client:{evaluate:async expression=>vm.runInContext(expression,env)},emit:(name,type,{earlyMicrotask=false}={})=>{
    const event={isTrusted:true,defaultPrevented:false};listeners.get(name+':'+type)?.(event);
    if(earlyMicrotask)while(queue.length)queue.shift()();event.defaultPrevented=true;
    while(queue.length)queue.shift()();
  }};
}
test('passive send evidence records click and submit without altering the send or retaining listeners',async()=>{
  const dom=eventDom(),evidence=[];let sends=0;const op='op-'+'a'.repeat(64);
  const result=await withAStudioSendEvents(dom.client,op,'owned-thread',async()=>{sends++;dom.emit('button','click');dom.emit('form','submit');return {clicked:true}},async r=>evidence.push(r));
  assert.equal(result.clicked,true);assert.equal(sends,1);assert.equal(dom.listeners.size,0);
  assert.deepEqual(Array.from(evidence[0].events,e=>e.type),['click','submit']);assert.equal(evidence[0].events[0].default_prevented_after_dispatch,true);
  assert.equal(evidence[0].intercepted,false);assert.equal(evidence[0].dropped_events,0);
});
test('passive event cleanup never retries an unknown send and does not remove a foreign observer',async()=>{
  const dom=eventDom();let sends=0,recorded=0;const op='op-'+'b'.repeat(64);
  await assert.rejects(()=>withAStudioSendEvents(dom.client,op,'owned-thread',async()=>{sends++;throw Error('unknown click result')},async()=>recorded++),/unknown click/);
  assert.equal(sends,1);assert.equal(recorded,1);assert.equal(dom.listeners.size,0);
  await dom.client.evaluate(aStudioSendEventsExpression(op,'owned-thread','install'));
  await assert.rejects(()=>dom.client.evaluate(aStudioSendEventsExpression('op-'+'c'.repeat(64),'owned-thread','take')),/OWNER_UNVERIFIED/);
  assert.equal(dom.listeners.size,6);
  await dom.client.evaluate(aStudioSendEventsExpression(op,'owned-thread','take'));assert.equal(dom.listeners.size,0);
});

test('send focus waits for the same foreground owner and a focused visible renderer without activating it',async()=>{
  let tick=0,reads=0;const pids=[99,99,42,42,42,42];let documents=0;
  const result=await waitForAStudioSendFocus(42,{maxWaitMs:100,read:()=>pids[reads++],
    readDocument:async()=>{documents++;return {focused:true,visible:true}},now:()=>tick,pause:async()=>{tick+=10}});
  assert.equal(result.ready,true);assert.equal(result.observations.length,3);assert.equal(documents,2);
});
test('a foreign or unknown foreground and an unfocused renderer expire without admitting a send',async()=>{
  for(const [pid,document] of [[99,{focused:true,visible:true}],[NaN,{focused:true,visible:true}],
    [42,{focused:false,visible:true}],[42,{focused:true,visible:false}]]){
    let tick=0;const result=await waitForAStudioSendFocus(42,{maxWaitMs:20,read:()=>pid,readDocument:async()=>document,
      now:()=>tick,pause:async()=>{tick+=10}});
    assert.equal(result.ready,false);
  }
  assert.equal(aStudioForegroundCheck(42,()=>NaN).ready,false);
  assert.equal((await waitForAStudioSendFocus(42,{maxWaitMs:0,read:()=>42})).ready,true);
});
test('losing foreground after the final target read prevents the press and waits for a fresh verified target',async()=>{
  const events=[];let checks=0;
  const result=await clickAStudioStableTarget({send:async(_,v)=>events.push(v)},'p','/w',{
    read:async()=>({ready:true,thread_id:'owned',x:1,y:2}),beforeMove:async()=>({ready:true}),
    finalFocus:()=>aStudioForegroundCheck(42,()=>++checks===1?99:42),pause:async()=>{}});
  assert.equal(result.clicked,true);assert.equal(result.foreground_losses.length,1);
  assert.equal(events.filter(e=>e.type==='mousePressed').length,1);assert.equal(result.final_foreground.foreground_pid,42);
});
test('no hover or press occurs while focus is unavailable and a changed route after waiting is rejected',async()=>{
  for(const changedRoute of [false,true]){
    const events=[];let reads=0;
    const result=await clickAStudioStableTarget({send:async(_,v)=>events.push(v)},'p','/w',{
      read:async()=>({ready:true,thread_id:++reads>1&&changedRoute?'other':'owned',x:1,y:2}),
      beforeMove:async()=>({ready:changedRoute}),pause:async()=>{}});
    assert.equal(result.clicked,false);assert.equal(events.length,0);
  }
});

test('new CDP budgets are explicit and invalid values fail before any connection',()=>{
  assert.equal(aStudioCdpBudget({}),10000);assert.equal(aStudioCdpBudget({cdp_timeout_ms:30000}),30000);
  for(const cdp_timeout_ms of [0,4999,60001,Infinity,'30000'])assert.throws(()=>aStudioCdpBudget({cdp_timeout_ms}),/CDP_TIMEOUT_POLICY/);
});

test('event snapshots read final default prevention even if a microtask ran before bubbling handlers',async()=>{
  const dom=eventDom();let captured;
  await withAStudioSendEvents(dom.client,'op-'+'d'.repeat(64),'owned-thread',async()=>dom.emit('form','submit',{earlyMicrotask:true}),async raw=>captured=raw);
  assert.equal(captured.events[0].default_prevented_at_capture,false);
  assert.equal(captured.events[0].default_prevented_after_dispatch,true);assert.equal(dom.listeners.size,0);
});
