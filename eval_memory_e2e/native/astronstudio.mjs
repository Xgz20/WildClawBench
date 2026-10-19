import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {DatabaseSync} from 'node:sqlite';
import {realpath,stat,readFile} from 'node:fs/promises';
import {discoverMainTarget, readUiConfiguration, prepareExecutionUi, fillPrompt, ensureSendTargetReady,
  inspectSendTarget, currentThreadId} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';
import {WorkBuddyCdpClient as CdpClient} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
import {queryNativeSessions, withStateSnapshot} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';
import {isBlockingActiveSession, classifyNativeState} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';
import {readRolloutFile,analyzeRollout} from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout.mjs';
import {context, sha, requestHash, readJson, saveState, artifact, withUiLock, requireGui,
  baseReply, bindReply, verifyConfig, stdinRequest} from './common.mjs';

const DB='/Users/gzx/.acode/acode/userdata/state.sqlite';
const ENDPOINT='http://127.0.0.1:9240';
const CAPABILITIES=['new','continue'];
export function aStudioConfigurationFields(ui,frozen=null) {
  return {model_display:frozen?frozen.model_display:ui.model,
    reasoning:frozen?frozen.reasoning:ui.reasoning,permissions:frozen?frozen.permissions:ui.permission};
}
export async function clickAStudioStableTarget(client,prompt,workspace,{read=()=>inspectSendTarget(client,prompt,workspace),beforePress=async()=>({ready:true}),pause=()=>new Promise(ok=>setTimeout(ok,100)),attempts=10}={}) {
  let target=await read();if(!target.ready)return {clicked:false,mouse_press_count:0,...target};
  const threadId=target.thread_id;
  for(let i=0;i<attempts;i++) {
    await client.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:target.x,y:target.y,button:'none',buttons:0});
    await pause();const next=await read();
    if(!next.ready||next.thread_id!==threadId)return {clicked:false,mouse_press_count:0,reason:'target-or-route-changed-after-hover',target:next};
    if(next.x===target.x&&next.y===target.y) {
      const final=await read();
      if(!final.ready||final.thread_id!==threadId||final.x!==next.x||final.y!==next.y)return {clicked:false,mouse_press_count:0,reason:'target-not-stable-before-press'};
      const rpc=await beforePress();
      if(rpc?.ready!==true)return {clicked:false,mouse_press_count:0,reason:'rpc-transport-not-ready-before-press',rpc};
      const afterRpc=await read();
      if(!afterRpc.ready||afterRpc.thread_id!==threadId||afterRpc.x!==final.x||afterRpc.y!==final.y)
        return {clicked:false,mouse_press_count:0,reason:'target-changed-after-rpc-read'};
      await client.send('Input.dispatchMouseEvent',{type:'mousePressed',x:final.x,y:final.y,button:'left',buttons:1,clickCount:1});
      await client.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:final.x,y:final.y,button:'left',buttons:0,clickCount:1});
      return {clicked:true,mouse_press_count:1,thread_id:threadId,x:final.x,y:final.y,method:'stable-native-mouse-events'};
    }
    target=next;
  }
  return {clicked:false,mouse_press_count:0,reason:'target-remained-unstable'};
}
const ASTUDIO_TRANSPORT_PROFILE=Object.freeze({
  url:'acode://app/assets/with-selector-DcLfjZsV.js',
  sha256:'b6350faa1efd5faa42907b2a52497b356d6a4d6ab9f07d034364d89d01a0d537',
  getter:'h',getter_source:'function Os(){return Ts}',event:'astudio:ws-transport-state',
});
export function aStudioTransportProfileForSource(source,url) {
  if(url!==ASTUDIO_TRANSPORT_PROFILE.url||sha(source)!==ASTUDIO_TRANSPORT_PROFILE.sha256)throw Error('ASTUDIO_RPC_SOURCE_UNVERIFIED');
  return ASTUDIO_TRANSPORT_PROFILE;
}
async function loadedAStudioTransportProfile(client) {
  const scripts=[];
  const listener=e=>{const m=JSON.parse(String(e.data));
    if(m.method==='Debugger.scriptParsed'&&m.params.url===ASTUDIO_TRANSPORT_PROFILE.url&&m.params.isModule)scripts.push(m.params)};
  client.socket.addEventListener('message',listener);
  try {
    await client.send('Debugger.enable');
    if(!scripts.length)throw Error('ASTUDIO_RPC_LOADED_MODULE_UNVERIFIED');
    const {scriptSource}=await client.send('Debugger.getScriptSource',{scriptId:scripts.at(-1).scriptId});
    return aStudioTransportProfileForSource(scriptSource,scripts.at(-1).url);
  } finally {client.socket.removeEventListener('message',listener);await client.send('Debugger.disable').catch(()=>{})}
}
export async function readAStudioRpcTransport(client,{readProfile=loadedAStudioTransportProfile}={}) {
  const profile=await readProfile(client);
  // Import only the exact, already-loaded ES module verified above. Read its
  // existing state getter; do not construct sockets, invoke RPCs or enumerate the heap.
  return client.evaluate(`(async()=>{
    const module=await import(${JSON.stringify(profile.url)}),getter=module[${JSON.stringify(profile.getter)}];
    if(typeof getter!=='function'||String(getter)!==${JSON.stringify(profile.getter_source)})throw Error('ASTUDIO_RPC_GETTER_UNVERIFIED');
    const state=getter(),host=new URL(await window.desktopBridge.getWsUrl()).host;
    if(state!==null&&!['connecting','open','closed','incompatible','authentication-required','disposed'].includes(state))throw Error('ASTUDIO_RPC_STATE_UNVERIFIED');
    return {source:'installed-renderer-transport-state',state,ready:state==='open',
      identities:[{host,source_url:${JSON.stringify(profile.url)},source_sha256:${JSON.stringify(profile.sha256)}}]};
  })()`);
}
export async function waitForAStudioRpcReady(read,{attempts=300,pause=()=>new Promise(ok=>setTimeout(ok,200))}={}) {
  let previous=null,last=null;
  for(let i=0;i<attempts;i++) {
    last=await read();
    const identity=last?.ready===true?JSON.stringify(last.identities):null;
    if(identity&&identity===previous)return {ready:true,samples:i+1,observation:last};
    previous=identity;await pause();
  }
  const error=Error('ASTUDIO_RPC_TRANSPORT_NOT_READY');error.observation=last;throw error;
}
export async function dispatchAStudioOnce(state,click,persist) {
  state.phase='invoking';await persist(state);
  const result=await click();
  if(typeof result?.clicked!=='boolean')throw Error('ASTUDIO_SEND_RESULT_UNVERIFIED');
  state.click_result=result;
  state.click_returned_at=new Date().toISOString();
  state.phase=result.clicked?'invoked':'pre_send_rejected';await persist(state);
  return result;
}
export async function waitForAStudioForeground(pid,{attempts=30,read=()=>Number(execFileSync('/usr/bin/osascript',
  ['-l','JavaScript','-e','ObjC.import("AppKit"); Number($.NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier);'],
  {encoding:'utf8',timeout:3000}).trim()),pause=()=>new Promise(ok=>setTimeout(ok,100))}={}) {
  for(let i=0;i<attempts;i++){if(await read()===pid)return {pid,verified:true,attempts:i+1};await pause();}
  throw Error('ASTUDIO_FOREGROUND_OWNER_UNVERIFIED');
}
export async function waitForAStudioFrozenUi(read,expected,threadId,{attempts=150,pause=()=>new Promise(ok=>setTimeout(ok,200))}={}) {
  const observations=[];
  for(let i=0;i<attempts;i++) {
    const ui=await read();
    if(ui.thread_id!==threadId)throw Error('ASTUDIO_PENDING_CONFIG_ROUTE_CHANGED');
    observations.push({model:ui.model,reasoning:ui.reasoning,permission:ui.permission});
    if(ui.model_count===1&&ui.model===expected.model_display&&ui.reasoning===expected.reasoning
      &&ui.permission_count===1&&ui.permission===expected.permissions)return {ui,observations};
    await pause();
  }
  const error=Error('ASTUDIO_FROZEN_UI_NOT_READY');error.observations=observations;throw error;
}
export function aStudioAcceptanceState(state,now=Date.now(),waitSeconds=30) {
  if(!['invoked','invoking'].includes(state.phase))return 'not_started';
  const start=Date.parse(state.click_returned_at||'');
  return Number.isFinite(start)&&now-start<waitSeconds*1000?'pending':'unconfirmed';
}
export function aStudioDomSubmitExpression(prompt,workspace,threadId) {
  return `(()=>{
    const expected=${JSON.stringify(prompt.trim().replaceAll('\r\n','\n'))},cwd=${JSON.stringify(workspace)},thread=${JSON.stringify(threadId)};
    const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
    const route=location.hash.match(/^#\\/([^/?#]+)/u)?.[1];
    const editors=[...document.querySelectorAll('[data-testid="composer-editor"]')].filter(visible);
    const workspaces=[...document.querySelectorAll('[data-testid="workspace-picker-trigger"], [data-testid="project-picker-trigger"]')].filter(visible);
    const buttons=[...document.querySelectorAll('button[type="submit"][aria-label="发送消息"], button[type="submit"][aria-label="Send message"]')].filter(visible).filter(e=>!e.disabled);
    if(decodeURIComponent(route||'')!==thread||editors.length!==1||workspaces.length!==1||buttons.length!==1
      ||(editors[0].innerText||'').trim().replaceAll('\\r\\n','\\n')!==expected||workspaces[0].getAttribute('title')!==cwd
      ||[...document.querySelectorAll('[role="dialog"], [aria-modal="true"]')].some(visible))return {clicked:false,reason:'atomic-send-precondition-changed'};
    const button=buttons[0],form=button.form,rect=button.getBoundingClientRect(),hit=document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2);
    if(!form||editors[0].closest('form')!==form||!form.checkValidity()||!hit||!button.contains(hit))return {clicked:false,reason:'submit-form-or-hit-unverified'};
    const events=[];
    const capture=e=>events.push({type:e.type,trusted:e.isTrusted,default_prevented:e.defaultPrevented});
    button.addEventListener('click',capture,true);form.addEventListener('submit',capture,true);
    try {button.click();return {clicked:true,thread_id:thread,method:'verified-dom-submit-click',dom_events:events};}
    finally{button.removeEventListener('click',capture,true);form.removeEventListener('submit',capture,true);}
  })()`;
}
async function waitForRecordedUi(ctx,client,expected,route,stage) {
  try{return await waitForAStudioFrozenUi(()=>readUiConfiguration(client),expected,route);}
  catch(error){await artifact(ctx,'configuration-failure',{stage,thread_id:route,expected,
    error:error.message,observations:error.observations??[],model_changed_by_controller:false});throw error;}
}
export function readMemoryConfiguration(){
  const code=`import json,tomllib
from pathlib import Path
result={}
for name,root in [('primary','/Users/gzx/.acode'),('overlay','/Users/gzx/.acode/acode/acode-home-overlay')]:
 p=Path(root)/'config.toml'
 if p.resolve()!=p: raise ValueError('AStudio config path must not be a symlink')
 d=tomllib.loads(p.read_text()); m=d.get('memories',{})
 result[name]={'enabled':d.get('features',{}).get('memories',False),'generate_memories':m.get('generate_memories',True),'use_memories':m.get('use_memories',True),'dedicated_tools':m.get('dedicated_tools',False),'extract_model':m.get('extract_model'),'consolidation_model':m.get('consolidation_model')}
print(json.dumps(result))`;
  return JSON.parse(execFileSync(process.env.MEMORY_E2E_PYTHON||'/usr/local/bin/python3.11',['-c',code],{encoding:'utf8',timeout:5000}));
}
export function aStudioCatalogModelId(catalog,accountScopeHash,displayName) {
  if(catalog?.schemaVersion!==1||catalog.accountScopeHash!==accountScopeHash
    ||!Array.isArray(catalog.models)||!Number.isFinite(Date.parse(catalog.fetchedAt)))throw Error('ASTUDIO_MODEL_CATALOG_SCOPE_UNVERIFIED');
  const matches=catalog.models.filter(m=>typeof m.name==='string'&&m.name.toLowerCase()===displayName.toLowerCase());
  if(matches.length!==1||typeof matches[0].slug!=='string'||!matches[0].slug.trim())throw Error('ASTUDIO_MODEL_CATALOG_ALIAS_AMBIGUOUS');
  return matches[0].slug;
}
export function aStudioGatewayCatalogProjection(raw,accountFingerprint) {
  if(raw?.version!==1||raw.accountHash!==accountFingerprint||!Number.isFinite(raw.refreshedAt)
    ||!Array.isArray(raw.builtins?.models))throw Error('ASTUDIO_MODEL_CATALOG_SCOPE_UNVERIFIED');
  return {schemaVersion:1,accountScopeHash:raw.accountHash,fetchedAt:new Date(raw.refreshedAt).toISOString(),
    models:raw.builtins.models.map(m=>({slug:m.slug,name:m.display_name}))};
}
async function modelCatalogEvidence(ctx,live,saved=null) {
  const source='/Users/gzx/.acode/acode/userdata/model-gateway/catalog-'+live.config.account_fingerprint+'.json';
  let bytes,proof=saved;
  if(saved) {
    if(saved.source_kind!=='astudio-scoped-model-catalog/v1'||saved.account_fingerprint!==live.config.account_fingerprint
      ||saved.account_scope_hash!==live.account_scope_hash||typeof saved.snapshot_path!=='string'
      ||!saved.snapshot_path.startsWith(ctx.control+'/')||await realpath(saved.snapshot_path)!==saved.snapshot_path)throw Error('ASTUDIO_MODEL_CATALOG_PROOF_DRIFT');
    bytes=await readFile(saved.snapshot_path);
    if(sha(bytes)!==saved.sha256)throw Error('ASTUDIO_MODEL_CATALOG_PROOF_DRIFT');
  } else {
    let before;try{before=await stat(source)}catch(e){if(e.code==='ENOENT')return null;throw e}
    if(!before.isFile()||before.size>1048576||await realpath(source)!==source)throw Error('ASTUDIO_MODEL_CATALOG_SOURCE_UNVERIFIED');
    const sourceBytes=await readFile(source);const after=await stat(source);
    if(before.size!==after.size||before.mtimeMs!==after.mtimeMs)throw Error('ASTUDIO_MODEL_CATALOG_UNSTABLE');
    const projection=aStudioGatewayCatalogProjection(JSON.parse(sourceBytes),live.config.account_fingerprint);
    aStudioCatalogModelId(projection,live.account_scope_hash,live.config.model_display);
    bytes=Buffer.from(JSON.stringify(projection,null,2)+'\n');
    proof={source_kind:'astudio-scoped-model-catalog/v1',source_path:source,account_fingerprint:live.config.account_fingerprint,
      account_scope_hash:live.account_scope_hash,source_sha256:sha(sourceBytes),sha256:sha(bytes),snapshot_path:await artifact(ctx,'model-catalog',bytes.toString('utf8'))};
  }
  const catalog=JSON.parse(bytes);
  aStudioCatalogModelId(catalog,live.account_scope_hash,live.config.model_display);
  return {...proof,catalog};
}
export function verifyRecordedConfiguration(bytes,session,frozen,modelCatalog=null) {
  const rows=bytes.toString('utf8').trim().split(/\r?\n/).map(line=>JSON.parse(line));
  const contexts=rows.filter(row=>row.type==='turn_context'&&row.payload?.turn_id===session.turn_id).map(row=>row.payload);
  if(contexts.length!==1)throw Error('ASTUDIO_NATIVE_CONFIGURATION_UNBOUND');
  const value=contexts[0];let model=value.model;
  if(typeof model==='string'&&model.startsWith('builtin/')){
    const encoded=model.slice(8);if(!/^[A-Za-z0-9_-]+$/.test(encoded))throw Error('ASTUDIO_NATIVE_MODEL_ENCODING');
    const decoded=Buffer.from(encoded,'base64url');if(decoded.toString('base64url')!==encoded)throw Error('ASTUDIO_NATIVE_MODEL_ENCODING');
    model=decoded.toString('utf8');
  }
  let expectedModel=frozen.model_display,modelIdentityBasis='exact-display-id';
  if(modelCatalog) {
    if(modelCatalog.source_kind!=='astudio-scoped-model-catalog/v1'
      ||!frozen.account_fingerprint||modelCatalog.account_fingerprint!==frozen.account_fingerprint)throw Error('ASTUDIO_MODEL_CATALOG_ACCOUNT_MISMATCH');
    expectedModel=aStudioCatalogModelId(modelCatalog.catalog,modelCatalog.account_scope_hash,frozen.model_display);
    modelIdentityBasis='account-scoped-catalog-name-to-slug';
  }
  if(typeof model!=='string'||model.toLowerCase()!==expectedModel.toLowerCase()
    ||String(value.effort).toLowerCase()!==String(frozen.reasoning).toLowerCase()
    ||value.cwd!==session.cwd)throw Error('ASTUDIO_NATIVE_CONFIGURATION_MISMATCH');
  if(!['完全访问','Full access'].includes(frozen.permissions)||value.approval_policy!=='never'
    ||value.sandbox_policy?.type!=='danger-full-access')throw Error('ASTUDIO_NATIVE_PERMISSION_UNVERIFIED');
  return {client_model_id:value.model,decoded_model_id:model,effort:value.effort,
    approval_policy:value.approval_policy,sandbox_type:value.sandbox_policy.type,source:'exact-native-turn-context',
    model_identity_basis:modelIdentityBasis,model_catalog:modelIdentityBasis==='exact-display-id'?null:modelCatalog};
}
async function connect(frozen=null,observeOnly=false) {
  await requireGui();
  const pids=[...new Set(execFileSync('/usr/sbin/lsof',['-nP','-iTCP:9240','-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim().split(/\s+/))];
  if(pids.length!==1||!execFileSync('/bin/ps',['-p',pids[0],'-o','command='],{encoding:'utf8'}).startsWith('/Applications/AStudio.app/Contents/MacOS/AStudio '))throw Error('ASTUDIO_LISTENER_OWNER');
  const target=await discoverMainTarget(ENDPOINT,4000);
  const client=await CdpClient.connect(target.webSocketDebuggerUrl,10000);
  try {
    const ui=await readUiConfiguration(client);
    const uid=await client.evaluate(`(async()=>{const u=new URL(await window.desktopBridge.getWsUrl());u.protocol=u.protocol==='wss:'?'https:':'http:';u.pathname='/api/astron-auth/session';const r=await fetch(u);if(!r.ok)throw Error('auth unavailable');const j=await r.json();return j.session?.uid??null})()`);
    if(!uid)throw Error('ASTUDIO_ACCOUNT_UNVERIFIED');
    const version=execFileSync('/usr/libexec/PlistBuddy',['-c','Print :CFBundleShortVersionString','/Applications/AStudio.app/Contents/Info.plist'],{encoding:'utf8'}).trim();
    const config={app_version:version,...aStudioConfigurationFields(ui,frozen),
      memory_settings:readMemoryConfiguration(),
      underlying_model:null,account_fingerprint:sha(String(uid))};
    verifyConfig(config,null);return {client,ui,config,pid:Number(pids[0]),
      account_scope_hash:sha(String(uid)),config_basis:frozen
      ?observeOnly?'frozen_pre_send_pending_native_turn_verification':'frozen_request_pending_target_ui_verification':'live_ui'};
  }catch(error){client.close();throw error}
}
async function traceFor(session,promptSha) {
  return withStateSnapshot(DB,async snapshot=>{
    const db=new DatabaseSync(snapshot,{readOnly:true});
    try {
      const messages=db.prepare('SELECT * FROM projection_thread_messages WHERE thread_id=? AND turn_id=? ORDER BY sequence,created_at').all(session.thread_id,session.turn_id);
      if(messages.filter(m=>m.role==='user'&&sha(m.text||'')===promptSha).length!==1)throw Error('ASTUDIO_PROMPT_NATIVE_MISMATCH');
      return {source_kind:'astronstudio-native-projection',session,messages};
    }finally{db.close()}
  },{},['projection_thread_messages']);
}
async function rawRollout(session,promptSha) {
  if(!/^[a-f0-9-]{36}$/i.test(session.session_id))throw Error('ASTUDIO_ROLLOUT_SESSION_ID');
  const roots=['/Users/gzx/.acode/acode/acode-home-overlay/sessions','/Users/gzx/.acode/sessions'];
  const matches=[];
  for(const root of roots) {
    if(!await stat(root).catch(()=>null))continue;
    const canonical=await realpath(root);if(!canonical.startsWith('/Users/gzx/.acode/'))throw Error('ASTUDIO_ROLLOUT_ROOT_OUTSIDE_TARGET');
    try {matches.push(...execFileSync('rg',['--files','-g','*'+session.session_id+'.jsonl',root],{encoding:'utf8',maxBuffer:1048576}).trim().split('\n').filter(Boolean));}
    catch(error){if(error.status!==1)throw error}
  }
  const unique=[...new Set(await Promise.all(matches.map(p=>realpath(p))))];
  if(unique.length!==1||!unique[0].startsWith('/Users/gzx/.acode/'))throw Error('ASTUDIO_ROLLOUT_NOT_UNIQUE');
  const raw=await readRolloutFile(unique[0]);
  const analysis=analyzeRollout(raw.bytes,{phase:'COMPLETED',prompt:{send_status:'sent',sha256:promptSha},
    session:{...session,verified:true}});
  return {...raw,source_path:unique[0],analysis};
}
async function observe(ctx,request,live,state) {
  verifyConfig(live.config,state.config);
  const rows=await queryNativeSessions(DB);
  const session=rows.find(s=>s.thread_id===state.thread_id&&s.cwd===request.workspace);
  if(!session?.session_id||!session.turn_id||session.turn_id===state.previous_turn_id){
    const acceptance=aStudioAcceptanceState(state);
    return bindReply(ctx,request,{...baseReply(request,live.config),status:acceptance==='pending'?'active':'needs_attention',
      reason:acceptance==='pending'?'等待原发送的原生身份；不重新发送。':'原生发送接受未确认，保留原意图并暂停派发；后续只能观察。'},
      {native_acceptance:acceptance,click_result:state.click_result??null,task_deadline:null,prompt_resend_authorized:false});
  }
  state.native={session_id:session.session_id,turn_id:session.turn_id,cwd:session.cwd};
  const classification=classifyNativeState(session);
  await saveState(ctx,state);
  const reply={...baseReply(request,live.config),native:state.native};
  if(classification.kind==='running')return bindReply(ctx,request,{...reply,status:'active',reason:'原生 turn 尚未结束。'},{native_session:session});
  if(classification.kind!=='completed')return bindReply(ctx,request,{...reply,
    status:session.status==='interrupted'?'infrastructure_error':'needs_attention',
    reason:session.status==='interrupted'?'原生 turn 中断，记忆阶段不可评；原因未确认，保留终态且不重发。':'原生 turn 未正常完成；保留终态，不重发。'},
    {native_session:session});
  const trace=await traceFor(session,request.prompt_sha256);
  const rollout=await rawRollout(session,request.prompt_sha256);
  const catalog=await modelCatalogEvidence(ctx,live,state.model_catalog_evidence??null);
  if(catalog&&!state.model_catalog_evidence){state.model_catalog_evidence=catalog;state.model_catalog_capture_basis='post-dispatch-observation';await saveState(ctx,state)}
  const nativeConfiguration=verifyRecordedConfiguration(rollout.bytes,session,state.config,catalog);
  state.firstTerminalObservedAt??=Date.now();await saveState(ctx,state);
  const seconds=(Date.now()-state.firstTerminalObservedAt)/1000;
  if(seconds<request.memory_wait_seconds)return bindReply(ctx,request,{...reply,status:'active',reason:'等待本轮明确声明的即时行为观察窗；不宣称长期记忆已形成。'});
  reply.status='completed';reply.memory_observation={status:'unobservable',wait_seconds:seconds};
  reply.final_response=await artifact(ctx,'response',trace.messages.filter(m=>m.role==='assistant').map(m=>m.text||'').filter(Boolean).join('\n\n'));
  reply.trace=await artifact(ctx,'trace',rollout.bytes.toString('utf8'));
  return bindReply(ctx,request,reply,{native_session:session,prompt_binding_status:'verified',memory_observation:reply.memory_observation,
    native_projection:trace,raw_rollout:{source_path:rollout.source_path,sha256:rollout.sha256,size:rollout.size},
    resource_metrics:rollout.analysis,native_configuration:nativeConfiguration,config_basis:live.config_basis});
}
export async function runAstronStudio(request) {
  const ctx=await context(request,'AstronStudio');let state;
  try{state=await readJson(ctx.stateFile)}catch(e){if(e.code!=='ENOENT')throw e}
  const live=await connect(state?.config??request.expected_config,Boolean(state&&request.transport_action==='observe'));
  try {
    verifyConfig(live.config,request.expected_config);
    if(state&&state.requestHash!==requestHash(request))throw Error('ASTUDIO_MEMORY_REQUEST_DRIFT');
    if(request.action==='prepare_namespace') {
      if(ctx.manifest.profiles.AstronStudio.memory_protocol?.requires_enabled_memory===true){
        const configs=Object.values(live.config.memory_settings);
        if(configs.some(c=>c.enabled!==true||c.use_memories!==true
          ||request.learning?.mode==='automatic'&&c.generate_memories!==true))return bindReply(ctx,request,
          {...baseReply(request,live.config),status:'needs_attention',reason:'AStudio 记忆配置未满足本批条件，停止在评测 Prompt 发送之前。'},
          {precondition:'memory_configuration_not_ready',prompt_sent:false});
      }
      if(request.required_capabilities.some(k=>!CAPABILITIES.includes(k)))return bindReply(ctx,request,{...baseReply(request,live.config),status:'needs_attention',reason:'该任务链的客户端重启尚未验收。'});
      const rows=await queryNativeSessions(DB);
      if(rows.some(isBlockingActiveSession)||rows.some(s=>s.cwd===request.workspace))throw Error('ASTUDIO_NAMESPACE_NOT_IDLE_OR_FRESH');
      if(!state)await saveState(ctx,{requestHash:requestHash(request),config:live.config,phase:'namespace_prepared'});
      return bindReply(ctx,request,{...baseReply(request,live.config),status:'completed',background_settled:true,
        admission:{account_policy:'current_signed_in_account',test_scope_only:true,precondition_verified:true,capabilities:CAPABILITIES,
          isolation:'shared_account_cold_first',global_memory_reset_verified:false,precondition_scope:'fresh_workspace_only'}},{native_sessions_baseline:rows.length,account_identity_method:'native astron-auth session uid -> sha256'});
    }
    if(state){if(request.transport_action!=='observe')throw Error('ASTUDIO_DUPLICATE_DISPATCH');
      if(state.phase==='pre_send_rejected')return bindReply(ctx,request,{...baseReply(request,live.config),status:'needs_attention',reason:'发送函数明确返回未点击成功；保留零发送检查结果，不自动重试。'},{click_result:state.click_result,prompt_sent:false});
      return await observe(ctx,request,live,state)}
    if(request.transport_action==='observe')throw Error('ASTUDIO_ACCEPTANCE_UNKNOWN_NO_REDISPATCH');
    return await withUiLock(ctx,request,async()=>{
      execFileSync('/usr/bin/open',['-a','/Applications/AStudio.app']);
      await live.client.send('Page.bringToFront');
      await artifact(ctx,'foreground-owner',await waitForAStudioForeground(live.pid));
      const rows=await queryNativeSessions(DB);if(rows.some(isBlockingActiveSession))throw Error('ASTUDIO_NOT_IDLE');
      await artifact(ctx,'rpc-ready-before-navigation',await waitForAStudioRpcReady(()=>readAStudioRpcTransport(live.client)));
      let route;
      if(request.session_action==='new') {
        try {
          await prepareExecutionUi(live.client,{candidateWorkspace:request.workspace,stateDatabase:DB,timeoutMs:30000,
            expectedModel:live.config.model_display,expectedReasoning:live.config.reasoning,expectedPermission:live.config.permissions});
        } catch(error) {
          if(!/^AstronStudio 当前(?:模型|推理强度)不匹配：/.test(error.message))throw error;
          // This error is raised only after the General engine verifies the new
          // native project/thread/cwd. Wait for hydration; never select a model.
          const pendingRoute=await currentThreadId(live.client);
          const hydrated=await waitForRecordedUi(ctx,live.client,live.config,pendingRoute,'after-navigation');
          await artifact(ctx,'configuration-hydration',{thread_id:pendingRoute,observations:hydrated.observations,model_changed_by_controller:false});
        }
        route=await currentThreadId(live.client);
      }else if(request.session_action==='continue') {
        const previous=rows.filter(s=>s.session_id===request.previous_native?.session_id&&s.cwd===request.workspace);
        route=await currentThreadId(live.client);
        if(previous.length!==1||route!==previous[0].thread_id)throw Error('ASTUDIO_CONTINUATION_ROUTE_CHANGED');
      }else throw Error('ASTUDIO_RESTART_NOT_ADMITTED');
      state={requestHash:requestHash(request),phase:'prepared',config:live.config,thread_id:route,
        previous_turn_id:rows.find(s=>s.thread_id===route)?.turn_id??null,
        model_catalog_evidence:await modelCatalogEvidence(ctx,live),model_catalog_capture_basis:'pre-dispatch'};await saveState(ctx,state);
      await fillPrompt(live.client,request.prompt,30000);
      await ensureSendTargetReady(live.client,request.prompt,request.workspace);
      const preSend=await waitForRecordedUi(ctx,live.client,live.config,route,'before-send');
      await artifact(ctx,'pre-send-configuration',{thread_id:route,ui:preSend.ui,config_basis:live.config_basis,model_changed_by_controller:false});
      await artifact(ctx,'rpc-ready-before-send',await waitForAStudioRpcReady(()=>readAStudioRpcTransport(live.client)));
      const method=ctx.manifest.profiles.AstronStudio.send_method??'native_mouse';
      if(!['native_mouse','dom_submit_click'].includes(method))throw Error('ASTUDIO_SEND_METHOD_NOT_ADMITTED');
      const clicked=await dispatchAStudioOnce(state,async()=>{
        const rpc=await readAStudioRpcTransport(live.client);
        if(!rpc.ready)return {clicked:false,mouse_press_count:0,reason:'rpc-transport-not-ready',rpc};
        return method==='dom_submit_click'?live.client.evaluate(aStudioDomSubmitExpression(request.prompt,request.workspace,route))
          :clickAStudioStableTarget(live.client,request.prompt,request.workspace,{beforePress:()=>readAStudioRpcTransport(live.client)});
      },value=>saveState(ctx,value));
      await artifact(ctx,'send-result',{method,result:clicked,native_acceptance_verified:false});
      if(!clicked.clicked)return bindReply(ctx,request,{...baseReply(request,live.config),status:'needs_attention',reason:'发送前检查返回未点击成功，停止在原生发送之前。'},{click_result:clicked,prompt_sent:false});
      return observe(ctx,request,live,state);
    });
  }finally{live.client.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{console.log(JSON.stringify(await runAstronStudio(await stdinRequest())))}catch(error){console.error(error.stack||error);process.exitCode=2}
}
