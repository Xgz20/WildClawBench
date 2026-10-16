import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {DatabaseSync} from 'node:sqlite';
import {realpath,stat} from 'node:fs/promises';
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
export async function clickAStudioStableTarget(client,prompt,workspace,{read=()=>inspectSendTarget(client,prompt,workspace),pause=()=>new Promise(ok=>setTimeout(ok,100)),attempts=10}={}) {
  let target=await read();if(!target.ready)return {clicked:false,mouse_press_count:0,...target};
  const threadId=target.thread_id;
  for(let i=0;i<attempts;i++) {
    await client.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:target.x,y:target.y,button:'none',buttons:0});
    await pause();const next=await read();
    if(!next.ready||next.thread_id!==threadId)return {clicked:false,mouse_press_count:0,reason:'target-or-route-changed-after-hover',target:next};
    if(next.x===target.x&&next.y===target.y) {
      const final=await read();
      if(!final.ready||final.thread_id!==threadId||final.x!==next.x||final.y!==next.y)return {clicked:false,mouse_press_count:0,reason:'target-not-stable-before-press'};
      await client.send('Input.dispatchMouseEvent',{type:'mousePressed',x:final.x,y:final.y,button:'left',buttons:1,clickCount:1});
      await client.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:final.x,y:final.y,button:'left',buttons:0,clickCount:1});
      return {clicked:true,mouse_press_count:1,thread_id:threadId,x:final.x,y:final.y,method:'stable-native-mouse-events'};
    }
    target=next;
  }
  return {clicked:false,mouse_press_count:0,reason:'target-remained-unstable'};
}
export async function dispatchAStudioOnce(state,click,persist) {
  state.phase='invoking';await persist(state);
  const result=await click();
  if(typeof result?.clicked!=='boolean')throw Error('ASTUDIO_SEND_RESULT_UNVERIFIED');
  state.click_result=result;
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
  throw Error('ASTUDIO_FROZEN_UI_NOT_READY');
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
export function verifyRecordedConfiguration(bytes,session,frozen) {
  const rows=bytes.toString('utf8').trim().split(/\r?\n/).map(line=>JSON.parse(line));
  const contexts=rows.filter(row=>row.type==='turn_context'&&row.payload?.turn_id===session.turn_id).map(row=>row.payload);
  if(contexts.length!==1)throw Error('ASTUDIO_NATIVE_CONFIGURATION_UNBOUND');
  const value=contexts[0];let model=value.model;
  if(typeof model==='string'&&model.startsWith('builtin/')){
    const encoded=model.slice(8);if(!/^[A-Za-z0-9_-]+$/.test(encoded))throw Error('ASTUDIO_NATIVE_MODEL_ENCODING');
    const decoded=Buffer.from(encoded,'base64url');if(decoded.toString('base64url')!==encoded)throw Error('ASTUDIO_NATIVE_MODEL_ENCODING');
    model=decoded.toString('utf8');
  }
  if(typeof model!=='string'||model.toLowerCase()!==frozen.model_display.toLowerCase()
    ||String(value.effort).toLowerCase()!==String(frozen.reasoning).toLowerCase()
    ||value.cwd!==session.cwd)throw Error('ASTUDIO_NATIVE_CONFIGURATION_MISMATCH');
  if(!['完全访问','Full access'].includes(frozen.permissions)||value.approval_policy!=='never'
    ||value.sandbox_policy?.type!=='danger-full-access')throw Error('ASTUDIO_NATIVE_PERMISSION_UNVERIFIED');
  return {client_model_id:value.model,decoded_model_id:model,effort:value.effort,
    approval_policy:value.approval_policy,sandbox_type:value.sandbox_policy.type,source:'exact-native-turn-context'};
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
    verifyConfig(config,null);return {client,ui,config,pid:Number(pids[0]),config_basis:frozen
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
  if(!session?.session_id||!session.turn_id||session.turn_id===state.previous_turn_id)return bindReply(ctx,request,
    {...baseReply(request,live.config),status:'active',reason:'等待原发送的原生身份；不重新发送。'});
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
  const nativeConfiguration=verifyRecordedConfiguration(rollout.bytes,session,state.config);
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
          const hydrated=await waitForAStudioFrozenUi(()=>readUiConfiguration(live.client),live.config,pendingRoute);
          await artifact(ctx,'configuration-hydration',{thread_id:pendingRoute,observations:hydrated.observations,model_changed_by_controller:false});
        }
        route=await currentThreadId(live.client);
      }else if(request.session_action==='continue') {
        const previous=rows.filter(s=>s.session_id===request.previous_native?.session_id&&s.cwd===request.workspace);
        route=await currentThreadId(live.client);
        if(previous.length!==1||route!==previous[0].thread_id)throw Error('ASTUDIO_CONTINUATION_ROUTE_CHANGED');
      }else throw Error('ASTUDIO_RESTART_NOT_ADMITTED');
      state={requestHash:requestHash(request),phase:'prepared',config:live.config,thread_id:route,
        previous_turn_id:rows.find(s=>s.thread_id===route)?.turn_id??null};await saveState(ctx,state);
      await fillPrompt(live.client,request.prompt,30000);
      await ensureSendTargetReady(live.client,request.prompt,request.workspace);
      const preSend=await waitForAStudioFrozenUi(()=>readUiConfiguration(live.client),live.config,route);
      await artifact(ctx,'pre-send-configuration',{thread_id:route,ui:preSend.ui,config_basis:live.config_basis,model_changed_by_controller:false});
      const clicked=await dispatchAStudioOnce(state,()=>clickAStudioStableTarget(live.client,request.prompt,request.workspace),value=>saveState(ctx,value));
      if(!clicked.clicked)return bindReply(ctx,request,{...baseReply(request,live.config),status:'needs_attention',reason:'发送前检查返回未点击成功，停止在原生发送之前。'},{click_result:clicked,prompt_sent:false});
      return observe(ctx,request,live,state);
    });
  }finally{live.client.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{console.log(JSON.stringify(await runAstronStudio(await stdinRequest())))}catch(error){console.error(error.stack||error);process.exitCode=2}
}
