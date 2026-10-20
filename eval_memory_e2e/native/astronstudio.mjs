import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {DatabaseSync} from 'node:sqlite';
import {realpath,stat,readFile,mkdir} from 'node:fs/promises';
import {discoverMainTarget, readUiConfiguration, prepareExecutionUi, fillPrompt, ensureSendTargetReady,
  inspectSendTarget, currentThreadId, clickSidebarToggle, PROJECT_NEW_TASK_LABEL} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';
import {WorkBuddyCdpClient as CdpClient} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
import {queryNativeSessions, withStateSnapshot,queryPristineThread,queryProjectForThread,queryExactProjectsForWorkspace} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';
import {isBlockingActiveSession, classifyNativeState} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';
import {readRolloutFile,analyzeRollout} from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout.mjs';
import {context, sha, requestHash, readJson, saveState, artifact, withUiLock, requireGui,
  baseReply, bindReply, verifyConfig, stdinRequest,assertMemoryFilesystemBoundary,assertNoLinks} from './common.mjs';

import {MACHINE_PATHS,memoryPython} from './machine.mjs';
let ASTUDIO_PATHS=MACHINE_PATHS,DB=MACHINE_PATHS.astudio_db;
export function selectAStudioPaths(profile,root) {
  const scope=profile.astudio_scope;
  if(!scope)return MACHINE_PATHS;
  if(scope.contract!=='astudio-case-memory-unit/v1'||scope.batch_root!==root
    ||!scope.paths?.runtime?.startsWith(MACHINE_PATHS.debug+'/')
    ||scope.paths.acode!==scope.paths.runtime+'/source-home'
    ||scope.paths.desktop!==scope.paths.runtime+'/desktop'
    ||scope.paths.overlay!==scope.paths.desktop+'/acode-home-overlay'
    ||scope.paths.astudio_db!==scope.paths.desktop+'/userdata/state.sqlite')throw Error('ASTUDIO_UNIT_PATHS_UNVERIFIED');
  return {...MACHINE_PATHS,...scope.paths};
}
export function aStudioBoundaryListener(proof,pid) {
  if(proof?.status!=='PASS'||!Number.isSafeInteger(proof.launch_identity?.pid)||proof.launch_identity.pid!==pid)
    throw Error('ASTUDIO_BOUNDARY_LISTENER_MISMATCH');
  return true;
}
export function aStudioRolloutPathAllowed(path,paths=ASTUDIO_PATHS) {
  return [paths.acode,paths.overlay].some(home=>typeof home==='string'&&path.startsWith(home+'/'));
}
export async function configureAStudioControllerTmp(ctx,profile) {
  if(!profile.astudio_scope)return null;
  if(!ctx.control.startsWith(ctx.root+'/.native/AstronStudio/'))throw Error('ASTUDIO_CONTROLLER_TMP_SCOPE');
  const directory=ctx.control+'/controller-tmp';
  await mkdir(directory,{recursive:true,mode:0o700});await assertNoLinks(directory);
  // These SQLite snapshots contain prior prompts. Keep even crash leftovers in
  // the protected controller tree, separate from the app's allowed TMPDIR.
  process.env.TMPDIR=directory;return directory;
}
const ENDPOINT='http://127.0.0.1:9240';
const CAPABILITIES=['new','continue'];
export function aStudioConfigurationFields(ui,frozen=null) {
  return {model_display:frozen?frozen.model_display:ui.model,
    reasoning:frozen?frozen.reasoning:ui.reasoning,permissions:frozen?frozen.permissions:ui.permission};
}
export async function clickAStudioStableTarget(client,prompt,workspace,{read=()=>inspectSendTarget(client,prompt,workspace),beforeMove=null,beforePress=async()=>({ready:true}),finalFocus=()=>({ready:true}),pause=()=>new Promise(ok=>setTimeout(ok,100)),attempts=10}={}) {
  let target=await read();if(!target.ready)return {clicked:false,mouse_press_count:0,...target};
  const threadId=target.thread_id,focusLosses=[];
  for(let i=0;i<attempts;i++) {
    if(beforeMove){
      const focus=await beforeMove();if(focus?.ready!==true)return {clicked:false,mouse_press_count:0,reason:'foreground-not-ready-before-hover',focus};
      const beforeHover=await read();
      if(!beforeHover.ready||beforeHover.thread_id!==threadId)return {clicked:false,mouse_press_count:0,reason:'target-or-route-changed-during-focus-wait'};
      target=beforeHover;
    }
    await client.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:target.x,y:target.y,button:'none',buttons:0});
    await pause();const next=await read();
    if(!next.ready||next.thread_id!==threadId)return {clicked:false,mouse_press_count:0,reason:'target-or-route-changed-after-hover',target:next};
    if(next.x===target.x&&next.y===target.y) {
      const final=await read();
      if(!final.ready||final.thread_id!==threadId||final.x!==next.x||final.y!==next.y)return {clicked:false,mouse_press_count:0,reason:'target-not-stable-before-press'};
      const rpc=await beforePress();
      if(rpc?.ready!==true)return {clicked:false,mouse_press_count:0,reason:rpc?.focus?.ready===false?'foreground-not-ready-before-press':'rpc-transport-not-ready-before-press',rpc};
      const afterRpc=await read();
      if(!afterRpc.ready||afterRpc.thread_id!==threadId||afterRpc.x!==final.x||afterRpc.y!==final.y)
        return {clicked:false,mouse_press_count:0,reason:'target-changed-after-rpc-read'};
      // No async work between this native foreground read and the mouse press.
      const lastFocus=finalFocus();
      if(lastFocus?.ready!==true){focusLosses.push(lastFocus);await pause();continue;}
      await client.send('Input.dispatchMouseEvent',{type:'mousePressed',x:final.x,y:final.y,button:'left',buttons:1,clickCount:1});
      await client.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:final.x,y:final.y,button:'left',buttons:0,clickCount:1});
      return {clicked:true,mouse_press_count:1,thread_id:threadId,x:final.x,y:final.y,method:'stable-native-mouse-events',
        final_foreground:lastFocus,foreground_losses:focusLosses};
    }
    target=next;
  }
  return {clicked:false,mouse_press_count:0,reason:focusLosses.length?'foreground-remained-unstable':'target-remained-unstable',foreground_losses:focusLosses};
}
const ASTUDIO_TRANSPORT_PROFILES=Object.freeze([Object.freeze({
  url:'acode://app/assets/with-selector-DcLfjZsV.js',
  sha256:'b6350faa1efd5faa42907b2a52497b356d6a4d6ab9f07d034364d89d01a0d537',
  getter:'h',getter_source:'function Os(){return Ts}',event:'astudio:ws-transport-state',
}),Object.freeze({
  // Installed 3.5.0 arm64 on 2026-10-20: loaded ES module equals ASAR bytes.
  // Os is a pure Ts getter, exported as h; Es writes Ts and emits the event.
  url:'acode://app/assets/with-selector-DJgh1YYs.js',
  sha256:'29a96dbbed30c8034ade2365ca9c4b2269919a8060853efac82c9a221ebe7e6b',
  getter:'h',getter_source:'function Os(){return Ts}',event:'astudio:ws-transport-state',source_witness:true,
}),Object.freeze({
  // AStudio 3.5.2 arm64: installed ASAR and loaded ES module were compared.
  // Os only reads Ts; Es updates Ts and emits the same transport-state event.
  url:'acode://app/assets/with-selector-DAVYFJ8l.js',
  sha256:'1aae52e9227ee61fdd9c460b2d25aae1a50ad0b825628379d356f10e727b3fbf',
  getter:'h',getter_source:'function Os(){return Ts}',event:'astudio:ws-transport-state',
  source_witness:true,
})]);
export function verifyAStudioTransportWitness(source) {
  if(source.split('function Os(){return Ts}').length!==2
    ||!source.includes('Os as h,')||!source.includes('bs=`astudio:ws-transport-state`')
    ||!source.includes('function Es(e){Ts=e,')
    ||!source.includes('window.dispatchEvent(new CustomEvent(bs,{detail:{state:e}}))'))throw Error('ASTUDIO_RPC_SOURCE_WITNESS_UNVERIFIED');
  return true;
}
export function aStudioTransportProfileForSource(source,url) {
  const profile=ASTUDIO_TRANSPORT_PROFILES.find(p=>p.url===url&&sha(source)===p.sha256);
  if(!profile)throw Error('ASTUDIO_RPC_SOURCE_UNVERIFIED');
  if(profile.source_witness)verifyAStudioTransportWitness(source);
  return profile;
}
async function loadedAStudioTransportProfile(client) {
  const scripts=[];
  const listener=e=>{const m=JSON.parse(String(e.data));
    if(m.method==='Debugger.scriptParsed'&&ASTUDIO_TRANSPORT_PROFILES.some(p=>p.url===m.params.url)&&m.params.isModule)scripts.push(m.params)};
  client.socket.addEventListener('message',listener);
  try {
    await client.send('Debugger.enable');
    if(scripts.length!==1)throw Error('ASTUDIO_RPC_LOADED_MODULE_UNVERIFIED');
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
export async function waitForAStudioClickTransport(read,{maxWaitMs=0,now=Date.now,pause=()=>new Promise(ok=>setTimeout(ok,200))}={}) {
  if(!Number.isFinite(maxWaitMs)||maxWaitMs<0||maxWaitMs>60000)throw Error('ASTUDIO_PRE_CLICK_WAIT_POLICY');
  const started=now();let previous=null,samples=0;
  for(;;) {
    const observed=await read();samples++;
    const identity=observed?.ready===true?JSON.stringify(observed.identities):null;
    if(identity&&(maxWaitMs===0||identity===previous))return {...observed,samples,waited_ms:now()-started};
    if(now()-started>=maxWaitMs)return {...observed,ready:false,samples,waited_ms:now()-started,transport_wait_expired:true};
    previous=identity;await pause();
  }
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
export function aStudioSendEventsExpression(operationId,threadId,action) {
  if(!/^op-[a-f0-9]{64}$/u.test(operationId)||!['install','take'].includes(action))throw Error('ASTUDIO_SEND_OBSERVER_POLICY');
  return `(()=>{
    const key='__wcbMemoryAStudioSendEvents',id=${JSON.stringify(operationId)},thread=${JSON.stringify(threadId)},action=${JSON.stringify(action)};
    if(action==='take'){
      const saved=globalThis[key];if(!saved||saved.id!==id)throw Error('ASTUDIO_SEND_OBSERVER_OWNER_UNVERIFIED');
      for(const [element,type,listener] of saved.listeners)element.removeEventListener(type,listener,true);
      for(const [row,event] of saved.eventRefs)row.default_prevented_after_dispatch=event.defaultPrevented;
      delete globalThis[key];return {events:saved.events,event_count:saved.event_count,dropped_events:Math.max(0,saved.event_count-saved.events.length),thread_id:thread,observed_route:location.hash,
        button_connected:saved.button?.isConnected??null,form_connected:saved.form?.isConnected??null,
        source:'passive-dom-event-listeners',intercepted:false};
    }
    if(globalThis[key])throw Error('ASTUDIO_SEND_OBSERVER_BUSY');
    const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
    const buttons=[...document.querySelectorAll('button[type="submit"][aria-label="发送消息"],button[type="submit"][aria-label="Send message"]')].filter(visible).filter(e=>!e.disabled);
    const editors=[...document.querySelectorAll('[data-testid="composer-editor"]')].filter(visible);
    const button=buttons.length===1?buttons[0]:null,form=button?.form;
    if(decodeURIComponent(location.hash.match(/^#\\/([^/?#]+)/u)?.[1]||'')!==thread||!form||editors.length!==1||editors[0].closest('form')!==form)throw Error('ASTUDIO_SEND_OBSERVER_TARGET_UNVERIFIED');
    const saved={id,events:[],eventRefs:[],listeners:[],event_count:0,button,form};
    for(const [element,types] of [[button,['pointerdown','pointerup','mousedown','mouseup','click']],[form,['submit']]])for(const type of types){
      const listener=event=>{
        const row={type,trusted:event.isTrusted,observed_at:Date.now(),default_prevented_at_capture:event.defaultPrevented};
        saved.event_count++;if(saved.events.length<32){saved.events.push(row);saved.eventRefs.push([row,event]);}
      };
      element.addEventListener(type,listener,true);saved.listeners.push([element,type,listener]);
    }
    globalThis[key]=saved;return {installed:true,thread_id:thread,intercepted:false};
  })()`;
}
export async function withAStudioSendEvents(client,operationId,threadId,send,record) {
  const installed=await client.evaluate(aStudioSendEventsExpression(operationId,threadId,'install'));
  if(installed?.installed!==true)throw Error('ASTUDIO_SEND_OBSERVER_NOT_INSTALLED');
  try{return await send();}
  finally {
    let evidence;
    try {evidence=await client.evaluate(aStudioSendEventsExpression(operationId,threadId,'take'));}
    catch(error){evidence={status:'unavailable',error_sha256:sha(error.message),observer_may_remain:true};}
    await record(evidence);
  }
}
export function readAStudioForegroundPid(){return Number(execFileSync('/usr/bin/osascript',
  ['-l','JavaScript','-e','ObjC.import("AppKit"); Number($.NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier);'],
  {encoding:'utf8',timeout:3000}).trim());}
export function aStudioForegroundCheck(pid,read=readAStudioForegroundPid){
  const current=read();return {ready:Number.isSafeInteger(current)&&current===pid,expected_pid:pid,foreground_pid:Number.isSafeInteger(current)?current:null};
}
export async function waitForAStudioSendFocus(pid,{maxWaitMs=60000,read=readAStudioForegroundPid,readDocument=async()=>({focused:true,visible:true}),now=Date.now,pause=()=>new Promise(ok=>setTimeout(ok,200))}={}) {
  if(!Number.isFinite(maxWaitMs)||maxWaitMs<0||maxWaitMs>120000)throw Error('ASTUDIO_FOCUS_WAIT_POLICY');
  const started=now(),observations=[];let stable=0;
  do {
    const before=aStudioForegroundCheck(pid,read);
    const document=before.ready?await readDocument():null;
    const after=aStudioForegroundCheck(pid,read);
    const ready=before.ready&&after.ready&&document?.focused===true&&document?.visible===true;
    observations.push({before,after,document});stable=ready?stable+1:0;
    if(stable>=2||ready&&maxWaitMs===0)return {ready:true,waited_ms:now()-started,observations};
    if(now()-started>=maxWaitMs)break;
    await pause();
  }while(now()-started<maxWaitMs);
  return {ready:false,reason:'foreground-wait-expired',waited_ms:now()-started,observations};
}
export async function waitForAStudioForeground(pid,{attempts=30,read=readAStudioForegroundPid,pause=()=>new Promise(ok=>setTimeout(ok,100))}={}) {
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
export function aStudioDomSubmitExpression(prompt,workspace,threadId,{requireFocus=false}={}) {
  return `(()=>{
    const expected=${JSON.stringify(prompt.trim().replaceAll('\r\n','\n'))},cwd=${JSON.stringify(workspace)},thread=${JSON.stringify(threadId)};
    const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
    const route=location.hash.match(/^#\\/([^/?#]+)/u)?.[1];
    const editors=[...document.querySelectorAll('[data-testid="composer-editor"]')].filter(visible);
    const workspaces=[...document.querySelectorAll('[data-testid="workspace-picker-trigger"], [data-testid="project-picker-trigger"]')].filter(visible);
    const buttons=[...document.querySelectorAll('button[type="submit"][aria-label="发送消息"], button[type="submit"][aria-label="Send message"]')].filter(visible).filter(e=>!e.disabled);
    if(${requireFocus?'(!document.hasFocus()||document.visibilityState!=="visible")||':''}decodeURIComponent(route||'')!==thread||editors.length!==1||workspaces.length!==1||buttons.length!==1
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
export async function waitForAStudioProjectBinding(read,workspace,projectId,{attempts=150,maxWaitMs=30000,now=Date.now,pause=()=>new Promise(ok=>setTimeout(ok,200))}={}) {
  const observations=[],started=now();
  for(let i=0;i<attempts;i++) {
    const value=await read();observations.push(value);
    if(value.blocking_count||value.dialog_count||value.editor_count>1||value.workspace_count>1||value.projects.length>1
      ||value.editor_count===1&&!value.editor_empty||value.workspace_path&&value.workspace_path!==workspace){
      const error=Error('ASTUDIO_PROJECT_BINDING_CONFLICT');error.observations=observations;throw error;
    }
    const native=value.projects[0];
    if(value.stable_ui&&value.editor_count===1&&value.editor_empty&&value.workspace_path===workspace
      &&value.pristine&&native?.project_id===projectId&&native.workspace_root===workspace)return {observation:value,observations};
    if(now()-started>=maxWaitMs)break;
    await pause();
  }
  const error=Error('ASTUDIO_PROJECT_BINDING_NOT_READY');error.observations=observations;throw error;
}
export function aStudioProjectUiExpression() {
  return `(()=>{const v=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
      const editors=[...document.querySelectorAll('[data-testid="composer-editor"]')].filter(v);
      const workspaces=[...document.querySelectorAll('[data-testid="workspace-picker-trigger"],[data-testid="project-picker-trigger"]')].filter(v);
      return {thread_id:decodeURIComponent(location.hash.match(/^#\\/([^/?#]+)/u)?.[1]||''),editor_count:editors.length,
        editor_empty:editors.length===1&&editors[0].innerText.trim()==='',workspace_count:workspaces.length,
        workspace_path:workspaces.length===1?workspaces[0].getAttribute('title'):null,
        dialog_count:[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].filter(v).length}})()`;
}
export function aStudioProjectNavigationExpression(projectId,workspace,threadId,action='inspect') {
  if(!/^[a-f0-9-]{36}$/i.test(projectId)||!['inspect','scroll','click'].includes(action))throw Error('ASTUDIO_PROJECT_NAVIGATION_POLICY');
  return `(()=>{
    const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
    const route=decodeURIComponent(location.hash.match(/^#\\/([^/?#]+)/u)?.[1]||'');
    const editors=[...document.querySelectorAll('[data-testid="composer-editor"]')].filter(visible);
    const workspaces=[...document.querySelectorAll('[data-testid="workspace-picker-trigger"],[data-testid="project-picker-trigger"]')].filter(visible);
    const unsafe=route!==${JSON.stringify(threadId)}||editors.length!==1||editors[0].innerText.trim()!==''
      ||workspaces.length!==1||workspaces[0].getAttribute('title')!==${JSON.stringify(workspace)}
      ||[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].some(visible)
      ||[...document.querySelectorAll('button[aria-label]')].filter(visible).some(e=>/^(?:停止生成|Stop generating)$/iu.test(e.getAttribute('aria-label')||''));
    if(unsafe)return {clicked:false,ready:false,reason:'navigation-safety-changed'};
    const rows=[...document.querySelectorAll('[data-project-hover-anchor="${projectId}"]')];
    const row=rows.length===1?rows[0]:null,motion=row?.closest('[data-slot="sidebar-content-motion"]');
    if(!row||!motion)return {clicked:false,ready:false,reason:'project-row-unverified',row_count:rows.length};
    if(motion.inert||motion.getAttribute('aria-hidden')==='true')return {clicked:false,ready:false,sidebar_hidden:true};
    if(${JSON.stringify(action)}==='scroll'){row.scrollIntoView({block:'center',inline:'nearest'});return {scrolled:true};}
    const buttons=[...row.querySelectorAll('button[aria-label]')].filter(e=>${PROJECT_NEW_TASK_LABEL}.test((e.getAttribute('aria-label')||'').trim()));
    const button=buttons.length===1?buttons[0]:null;
    if(!button||button.disabled||button.closest('[inert]')||!visible(button))return {clicked:false,ready:false,reason:'project-new-task-unverified',button_count:buttons.length};
    const rect=button.getBoundingClientRect(),x=rect.x+rect.width/2,y=rect.y+rect.height/2,hit=document.elementFromPoint(x,y);
    if(x<=0||x>=innerWidth||y<=0||y>=innerHeight||!hit||!button.contains(hit))return {clicked:false,ready:false,reason:'project-new-task-occluded'};
    if(${JSON.stringify(action)}==='click'){button.click();return {clicked:true,method:'exact-project-new-task',project_id:${JSON.stringify(projectId)},previous_thread_id:route};}
    return {ready:true,x,y};
  })()`;
}
export async function waitForAStudioReload(client,reload,{maxWaitMs=30000,now=Date.now,pause=()=>new Promise(ok=>setTimeout(ok,200))}={}) {
  if(!Number.isFinite(maxWaitMs)||maxWaitMs<0||maxWaitMs>60000)throw Error('ASTUDIO_RELOAD_WAIT_POLICY');
  const frame=async()=>{
    const value=(await client.send('Page.getFrameTree')).frameTree?.frame;
    if(!value?.id||!value.loaderId)throw Error('ASTUDIO_RELOAD_FRAME_UNVERIFIED');
    return value;
  };
  const before=await frame();const result=await reload();const started=now();let samples=0;
  do {
    const current=await frame();samples++;
    if(current.id!==before.id)throw Error('ASTUDIO_RELOAD_TARGET_CHANGED');
    if(current.loaderId!==before.loaderId) {
      let ready=false;
      try {ready=await client.evaluate('document.readyState === "complete"');}
      catch(error){if(!/^(?:Inspected target navigated or closed|Execution context was destroyed\.?|Cannot find context with specified id)$/u.test(error.message))throw error;}
      const after=await frame();
      if(after.id!==before.id)throw Error('ASTUDIO_RELOAD_TARGET_CHANGED');
      if(ready&&after.loaderId===current.loaderId)return {result,evidence:{frame_id:before.id,previous_loader_id:before.loaderId,
        loader_id:after.loaderId,samples,waited_ms:now()-started,reload_count:1,prompt_sent:false}};
    }
    if(now()-started>=maxWaitMs)break;
    await pause();
  }while(now()-started<maxWaitMs);
  throw Error('ASTUDIO_RELOAD_NOT_READY');
}
export async function traceAStudioPreparation(client,prepare,record,{now=Date.now}={}) {
  const commands=[];const started=now();
  const traced=new Proxy(client,{get(target,key,receiver){
    if(key!=='send')return Reflect.get(target,key,receiver);
    return async(method,params={})=>{
      const command={method,started_ms:now()-started,call_site:new Error().stack.split('\n').slice(2,6),
        ...(typeof params.expression==='string'?{expression_sha256:sha(params.expression)}:{})};
      commands.push(command);
      try {
        let result;
        if(method==='Page.reload'){
          const settled=await waitForAStudioReload(traced,()=>target.send(method,params));
          command.reload_observation=settled.evidence;result=settled.result;
        }else result=await target.send(method,params);
        command.status='completed';return result;
      }
      catch(error){command.status='failed';command.error_sha256=sha(error.message);throw error;}
      finally{command.duration_ms=now()-started-command.started_ms;}
    };
  }});
  try {const result=await prepare(traced);await record({status:'completed',duration_ms:now()-started,commands,prompt_sent:false});return result;}
  catch(error){await record({status:'failed',duration_ms:now()-started,commands,error_sha256:sha(error.message),prompt_sent:false});throw error;}
}
async function prepareAStudioExecutionUi(ctx,client,config) {
  try{return await prepareExecutionUi(client,config)}catch(error) {
    if(error.message!=='AstronStudio 延迟出现的项目路径与原生路由不一致')throw error;
    const projects=await queryExactProjectsForWorkspace(DB,config.candidateWorkspace);
    if(projects.length!==1)throw Error('ASTUDIO_TARGET_PROJECT_AMBIGUOUS');
    const readUi=()=>client.evaluate(aStudioProjectUiExpression());
    const readBinding=async()=>{
      const before=await readUi();const native=before.thread_id?await queryProjectForThread(DB,before.thread_id):[];
      const pristine=before.thread_id?await queryPristineThread(DB,before.thread_id):false;
      const blocking=(await queryNativeSessions(DB)).filter(isBlockingActiveSession).length;
      const after=await readUi();return {...after,projects:native,pristine,blocking_count:blocking,stable_ui:JSON.stringify(before)===JSON.stringify(after)};
    };
    let recovered;
    try {
      const before=await readBinding();
      if(!before.stable_ui||!before.pristine||before.blocking_count||before.dialog_count||before.editor_count!==1
        ||!before.editor_empty||before.workspace_count!==1||before.workspace_path!==config.candidateWorkspace)throw Error('ASTUDIO_PROJECT_NAVIGATION_UNSAFE');
      if(before.projects.length!==1||before.projects[0].project_id!==projects[0].project_id||before.projects[0].workspace_root!==config.candidateWorkspace){
        const expression=action=>aStudioProjectNavigationExpression(projects[0].project_id,config.candidateWorkspace,before.thread_id,action);
        let point=await client.evaluate(expression('inspect'));
        if(point.sidebar_hidden){const opened=await clickSidebarToggle(client);if(!opened.clicked)throw Error('ASTUDIO_PROJECT_SIDEBAR_UNVERIFIED');}
        const scrolled=await client.evaluate(expression('scroll'));if(!scrolled.scrolled)throw Error('ASTUDIO_PROJECT_SCROLL_UNVERIFIED');
        point=await client.evaluate(expression('inspect'));if(!point.ready)throw Error('ASTUDIO_PROJECT_NAVIGATION_TARGET_UNVERIFIED');
        await client.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:point.x,y:point.y,button:'none',buttons:0});
        const safe=await readBinding();
        if(JSON.stringify(safe)!==JSON.stringify(before))throw Error('ASTUDIO_PROJECT_NAVIGATION_STATE_CHANGED');
        await artifact(ctx,'project-navigation-intent',{project_id:projects[0].project_id,workspace:config.candidateWorkspace,before,prompt_sent:false});
        const clicked=await client.evaluate(expression('click'));
        await artifact(ctx,'project-navigation-result',{...clicked,prompt_sent:false});
        if(!clicked.clicked)throw Error('ASTUDIO_PROJECT_NAVIGATION_REJECTED');
      }
      recovered=await waitForAStudioProjectBinding(readBinding,config.candidateWorkspace,projects[0].project_id);
    }catch(failure) {
      await artifact(ctx,'project-binding-failure',{initial_error:error.message,error:failure.message,observations:failure.observations??[]});throw failure;
    }
    await artifact(ctx,'project-binding-recovered',{initial_error:error.message,...recovered,prompt_sent:false});
    const ui=await readUiConfiguration(client);
    if(ui.model_count!==1||ui.model!==config.expectedModel)throw Error('AstronStudio 当前模型不匹配：'+ui.model+' vs '+config.expectedModel);
    if(ui.reasoning!==config.expectedReasoning)throw Error('AstronStudio 当前推理强度不匹配：'+ui.reasoning+' vs '+config.expectedReasoning);
    if(ui.permission_count!==1||ui.permission!==config.expectedPermission)throw Error('ASTUDIO_PROJECT_PERMISSION_MISMATCH');
    return {task:{thread_id:recovered.observation.thread_id,editor_count:1,editor_empty:true},workspace:recovered.observation,ui};
  }
}
export function readMemoryConfiguration(){
  const code=`import json,tomllib,sys
from pathlib import Path
result={}
for name,root in [('primary',sys.argv[1]),('overlay',sys.argv[2])]:
 p=Path(root)/'config.toml'
 if p.resolve()!=p: raise ValueError('AStudio config path must not be a symlink')
 d=tomllib.loads(p.read_text()); m=d.get('memories',{})
 result[name]={'enabled':d.get('features',{}).get('memories',False),'generate_memories':m.get('generate_memories',True),'use_memories':m.get('use_memories',True),'dedicated_tools':m.get('dedicated_tools',False),'extract_model':m.get('extract_model'),'consolidation_model':m.get('consolidation_model')}
print(json.dumps(result))`;
  return JSON.parse(execFileSync(memoryPython(),['-c',code,ASTUDIO_PATHS.acode,ASTUDIO_PATHS.overlay],{encoding:'utf8',timeout:5000}));
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
  const source=(ASTUDIO_PATHS.desktop??MACHINE_PATHS.acode+'/acode')+'/userdata/model-gateway/catalog-'+live.config.account_fingerprint+'.json';
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
function aStudioRuntimeIdentity() {
  const pids=[...new Set(execFileSync('/usr/sbin/lsof',['-nP','-iTCP:9240','-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim().split(/\s+/))];
  if(pids.length!==1||!execFileSync('/bin/ps',['-p',pids[0],'-o','command='],{encoding:'utf8'}).startsWith('/Applications/AStudio.app/Contents/MacOS/AStudio '))throw Error('ASTUDIO_LISTENER_OWNER');
  const version=execFileSync('/usr/libexec/PlistBuddy',['-c','Print :CFBundleShortVersionString','/Applications/AStudio.app/Contents/Info.plist'],{encoding:'utf8'}).trim();
  return {pid:Number(pids[0]),version};
}
export function aStudioNativeObservationEligible(request,state) {
  return request?.mode==='native'&&request.harness==='AstronStudio'&&request.action==='execute_step'&&request.transport_action==='observe'
    &&state?.phase==='invoked'&&state.click_result?.clicked===true&&typeof state.click_returned_at==='string'&&Number.isFinite(Date.parse(state.click_returned_at))
    &&/^[a-f0-9-]{36}$/i.test(state.thread_id??'')&&/^[a-f0-9]{64}$/.test(state.config?.account_fingerprint??'')
    &&state.config.account_fingerprint===request.expected_config?.account_fingerprint
    &&state.requestHash===requestHash(request);
}
export async function connectAStudioNativeObservation(state,{checkEnvironment=requireGui,readIdentity=aStudioRuntimeIdentity,readMemory=readMemoryConfiguration}={}) {
  await checkEnvironment();const identity=await readIdentity();
  const config={...state.config,app_version:identity.version,memory_settings:await readMemory()};
  verifyConfig(config,state.config);
  return {client:null,config,pid:identity.pid,account_scope_hash:config.account_fingerprint,
    config_basis:'verified-dispatch-config-pending-native-turn-verification',
    observation_evidence:{observation_transport:'native-state-and-rollout-only',
      account_identity_basis:'verified-dispatch-auth-session-uid',current_account_rechecked:false}};
}
export function aStudioCdpBudget(profile) {
  const value=profile.cdp_timeout_ms??10000;
  if(!Number.isInteger(value)||value<5000||value>60000)throw Error('ASTUDIO_CDP_TIMEOUT_POLICY');
  return value;
}
async function connect(frozen=null,observeOnly=false,{activate=false,timeoutMs=10000,record=async()=>{}}={}) {
  await requireGui();const {pid,version}=aStudioRuntimeIdentity();
  if(activate){
    execFileSync('/usr/bin/open',['-a','/Applications/AStudio.app']);
    await record({stage:'connect-foreground',...(await waitForAStudioForeground(pid)),prompt_sent:false});
  }
  const target=await discoverMainTarget(ENDPOINT,4000);
  const client=await CdpClient.connect(target.webSocketDebuggerUrl,timeoutMs);
  const stage=async(name,read)=>{
    const started=Date.now();await record({stage:name,status:'started',at:new Date().toISOString(),prompt_sent:false});
    try {const result=await read();await record({stage:name,status:'completed',duration_ms:Date.now()-started,prompt_sent:false});return result;}
    catch(error){await record({stage:name,status:'failed',duration_ms:Date.now()-started,error_sha256:sha(error.message),prompt_sent:false});throw error;}
  };
  try {
    if(activate)await client.send('Page.bringToFront');
    const ui=await stage('connect-ui',()=>readUiConfiguration(client));
    const uid=await stage('connect-auth',()=>client.evaluate(`(async()=>{const u=new URL(await window.desktopBridge.getWsUrl());u.protocol=u.protocol==='wss:'?'https:':'http:';u.pathname='/api/astron-auth/session';const r=await fetch(u,{signal:AbortSignal.timeout(6000)});if(!r.ok)throw Error('auth unavailable');const j=await r.json();return j.session?.uid??null})()`));
    if(!uid)throw Error('ASTUDIO_ACCOUNT_UNVERIFIED');
    const config={app_version:version,...aStudioConfigurationFields(ui,frozen),
      memory_settings:readMemoryConfiguration(),
      underlying_model:null,account_fingerprint:sha(String(uid))};
    verifyConfig(config,null);return {client,ui,config,pid,
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
  const roots=[ASTUDIO_PATHS.overlay+'/sessions',ASTUDIO_PATHS.acode+'/sessions'];
  const matches=[];
  for(const root of roots) {
    if(!await stat(root).catch(()=>null))continue;
    const canonical=await realpath(root);if(!aStudioRolloutPathAllowed(canonical))throw Error('ASTUDIO_ROLLOUT_ROOT_OUTSIDE_TARGET');
    try {matches.push(...execFileSync('rg',['--files','-g','*'+session.session_id+'.jsonl',root],{encoding:'utf8',maxBuffer:1048576}).trim().split('\n').filter(Boolean));}
    catch(error){if(error.status!==1)throw error}
  }
  const unique=[...new Set(await Promise.all(matches.map(p=>realpath(p))))];
  if(unique.length!==1||!aStudioRolloutPathAllowed(unique[0]))throw Error('ASTUDIO_ROLLOUT_NOT_UNIQUE');
  const raw=await readRolloutFile(unique[0]);
  const analysis=analyzeRollout(raw.bytes,{phase:'COMPLETED',prompt:{send_status:'sent',sha256:promptSha},
    session:{...session,verified:true}});
  return {...raw,source_path:unique[0],analysis};
}
async function observe(ctx,request,live,state) {
  verifyConfig(live.config,state.config);
  const bind=(reply,extra={})=>bindReply(ctx,request,reply,{...live.observation_evidence,...extra});
  const rows=await queryNativeSessions(DB);
  const session=rows.find(s=>s.thread_id===state.thread_id&&s.cwd===request.workspace);
  if(!session?.session_id||!session.turn_id||session.turn_id===state.previous_turn_id){
    const waitSeconds=ctx.manifest.profiles.AstronStudio.native_acceptance_wait_seconds??30;
    if(!Number.isInteger(waitSeconds)||waitSeconds<30||waitSeconds>600)throw Error('ASTUDIO_ACCEPTANCE_WAIT_POLICY');
    const acceptance=aStudioAcceptanceState(state,Date.now(),waitSeconds);
    return bind({...baseReply(request,live.config),status:acceptance==='pending'?'active':'needs_attention',
      reason:acceptance==='pending'?'等待原发送的原生身份；不重新发送。':'原生发送接受未确认，保留原意图并暂停派发；后续只能观察。'},
      {native_acceptance:acceptance,click_result:state.click_result??null,task_deadline:null,prompt_resend_authorized:false});
  }
  state.native={session_id:session.session_id,turn_id:session.turn_id,cwd:session.cwd};
  const classification=classifyNativeState(session);
  await saveState(ctx,state);
  const reply={...baseReply(request,live.config),native:state.native};
  if(classification.kind==='running')return bind({...reply,status:'active',reason:'原生 turn 尚未结束。'},{native_session:session});
  if(classification.kind!=='completed')return bind({...reply,
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
  if(seconds<request.memory_wait_seconds)return bind({...reply,status:'active',reason:'等待本轮明确声明的即时行为观察窗；不宣称长期记忆已形成。'});
  reply.status='completed';reply.memory_observation={status:'unobservable',wait_seconds:seconds};
  reply.final_response=await artifact(ctx,'response',trace.messages.filter(m=>m.role==='assistant').map(m=>m.text||'').filter(Boolean).join('\n\n'));
  reply.trace=await artifact(ctx,'trace',rollout.bytes.toString('utf8'));
  return bind(reply,{native_session:session,prompt_binding_status:'verified',memory_observation:reply.memory_observation,
    native_projection:trace,raw_rollout:{source_path:rollout.source_path,sha256:rollout.sha256,size:rollout.size},
    resource_metrics:rollout.analysis,native_configuration:nativeConfiguration,config_basis:live.config_basis});
}
export async function runAstronStudio(request) {
  const ctx=await context(request,'AstronStudio');let state;
  ASTUDIO_PATHS=selectAStudioPaths(ctx.manifest.profiles.AstronStudio,ctx.root);DB=ASTUDIO_PATHS.astudio_db;
  await configureAStudioControllerTmp(ctx,ctx.manifest.profiles.AstronStudio);
  try{state=await readJson(ctx.stateFile)}catch(e){if(e.code!=='ENOENT')throw e}
  if(state&&state.requestHash!==requestHash(request))throw Error('ASTUDIO_MEMORY_REQUEST_DRIFT');
  const live=aStudioNativeObservationEligible(request,state)?await connectAStudioNativeObservation(state)
    :await withUiLock(ctx,request,()=>connect(state?.config??request.expected_config,Boolean(state&&request.transport_action==='observe'),{
      activate:!state&&request.transport_action==='dispatch',timeoutMs:aStudioCdpBudget(ctx.manifest.profiles.AstronStudio),
      record:value=>artifact(ctx,'connection-stage',value)}));
  try {
    verifyConfig(live.config,request.expected_config);
    if(state&&state.requestHash!==requestHash(request))throw Error('ASTUDIO_MEMORY_REQUEST_DRIFT');
    if(request.action==='prepare_namespace') {
      if(ctx.manifest.profiles.AstronStudio.memory_protocol?.requires_enabled_memory===true){
        const configs=Object.values(live.config.memory_settings);
        if(ctx.manifest.profiles.AstronStudio.memory_protocol.automatic_generation_compatible===false
          && configs.some(c=>c.generate_memories!==false))return bindReply(ctx,request,
          {...baseReply(request,live.config),status:'needs_attention',reason:'外层OS隔离与本机原生自动整理沙箱不兼容，自动生成未准入；不得发送Prompt。'},
          {precondition:'automatic_generation_sandbox_not_admitted',prompt_sent:false});
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
          isolation:ctx.manifest.profiles.AstronStudio.astudio_scope?'verified_namespace':'shared_account_cold_first',
          global_memory_reset_verified:false,precondition_scope:ctx.manifest.profiles.AstronStudio.astudio_scope?'os_enforced_case_repeat_unit':'fresh_workspace_only'}},{native_sessions_baseline:rows.length,account_identity_method:'native astron-auth session uid -> sha256'});
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
          await traceAStudioPreparation(live.client,client=>prepareAStudioExecutionUi(ctx,client,{candidateWorkspace:request.workspace,stateDatabase:DB,timeoutMs:30000,
            expectedModel:live.config.model_display,expectedReasoning:live.config.reasoning,expectedPermission:live.config.permissions}),
            value=>artifact(ctx,'ui-preparation-diagnostics',value));
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
      const waitSeconds=ctx.manifest.profiles.AstronStudio.pre_click_rpc_wait_seconds??0;
      if(!Number.isInteger(waitSeconds)||waitSeconds<0||waitSeconds>60)throw Error('ASTUDIO_PRE_CLICK_WAIT_POLICY');
      const focusSeconds=ctx.manifest.profiles.AstronStudio.pre_click_focus_wait_seconds??0;
      if(!Number.isInteger(focusSeconds)||focusSeconds<0||focusSeconds>120)throw Error('ASTUDIO_FOCUS_WAIT_POLICY');
      const waitFocus=async()=>{
        const focus=await waitForAStudioSendFocus(live.pid,{maxWaitMs:focusSeconds*1000,
          readDocument:()=>live.client.evaluate('({focused:document.hasFocus(),visible:document.visibilityState === "visible"})')});
        await artifact(ctx,'send-focus-check',focus);return focus;
      };
      const finalFocus=()=>aStudioForegroundCheck(live.pid);
      const beforePress=async()=>{
        const rpc=await waitForAStudioClickTransport(()=>readAStudioRpcTransport(live.client),{maxWaitMs:waitSeconds*1000});
        if(!rpc.ready)return rpc;
        const focus=await waitFocus();
        if(focus.ready){
          const proof=assertMemoryFilesystemBoundary(request,ctx.manifest.profiles.AstronStudio);
          if(proof){
            aStudioBoundaryListener(proof,live.pid);
            ctx.memoryBoundary=proof;await artifact(ctx,'os-boundary-before-press',proof);
          }
        }
        return {...rpc,ready:focus.ready,focus};
      };
      const clicked=await withAStudioSendEvents(live.client,request.operation_id,route,()=>dispatchAStudioOnce(state,async()=>{
        const rpc=await beforePress();
        if(!rpc.ready)return {clicked:false,mouse_press_count:0,reason:rpc.focus?.ready===false?'foreground-not-ready':'rpc-transport-not-ready',rpc};
        if(method==='dom_submit_click'){
          const focus=finalFocus();if(!focus.ready)return {clicked:false,mouse_press_count:0,reason:'foreground-not-ready-before-dom-click',focus};
          return live.client.evaluate(aStudioDomSubmitExpression(request.prompt,request.workspace,route,{requireFocus:true}));
        }
        return clickAStudioStableTarget(live.client,request.prompt,request.workspace,{beforePress,beforeMove:waitFocus,finalFocus});
      },value=>saveState(ctx,value)),value=>artifact(ctx,'send-dom-events',value));
      await artifact(ctx,'send-result',{method,result:clicked,native_acceptance_verified:false});
      if(!clicked.clicked)return bindReply(ctx,request,{...baseReply(request,live.config),status:'needs_attention',reason:'发送前检查返回未点击成功，停止在原生发送之前。'},{click_result:clicked,prompt_sent:false});
      return observe(ctx,request,live,state);
    });
  }finally{live.client?.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{console.log(JSON.stringify(await runAstronStudio(await stdinRequest())))}catch(error){console.error(error.stack||error);process.exitCode=2}
}
