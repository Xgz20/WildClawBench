/** Memory episodes delegate each new-session step to the native General engine. */
import {pathToFileURL} from 'node:url';
import {join,dirname,basename} from 'node:path';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {chromium} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/doubaowork/node_modules/playwright-core/index.mjs';
import {runProbe} from '../../tools/report/e2e-shared/doubaowork/probe.mjs';
import {readNativeToolActivity,normalizeNativeToolEvents} from '../../tools/report/e2e-shared/doubaowork/runtime-tools.mjs';
import {inspectPage,assertNoConflictingActivity,selectConfigurationReadback,startDevelopmentRun,resumeDevelopmentRun,retryPreSendDevelopmentRun} from '../../tools/report/e2e-shared/doubaowork/controller.mjs';
import {normalizeRuntimeMessages} from '../../tools/report/e2e-shared/doubaowork/runtime-messages.mjs';
import {context,sha,requestHash,readJson,saveState,artifact,baseReply,bindReply,verifyConfig,withUiLock,stdinRequest,ensureLocalRuntimeMode,assertMemoryPreSendRetry} from './common.mjs';
const ENDPOINT='http://127.0.0.1:9260',APP='/Applications/DoubaoWork.app';
const CAPABILITIES=['new'];
async function mainPage(browser) {
  const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>/^(?:doubaowork|chrome):\/\/doubaowork-chat\//.test(p.url()));
  if(pages.length!==1)throw Error('DOUBAO_MAIN_PAGE_AMBIGUOUS');return pages[0];
}
async function readUiConfiguration(page,projectName) {
  const controls=await page.getByTestId('chat_input').evaluate(root=>[...root.querySelectorAll('button')].map(e=>({
    visible:Boolean(e.getClientRects().length),testid:e.getAttribute('data-testid'),aria_label:e.getAttribute('aria-label'),
    title:e.title,text:(e.innerText||e.textContent||'').trim().replace(/\s+/g,' ')})));
  return selectConfigurationReadback(controls,projectName);
}
async function ownedArtifact(folder,reference) {
  if(!reference?.file||basename(reference.file)!==reference.file)throw Error('DOUBAO_ARTIFACT_REFERENCE_INVALID');
  const bytes=await readFile(join(folder,reference.file));
  if(sha(bytes)!==reference.sha256)throw Error('DOUBAO_ARTIFACT_DRIFT');return bytes;
}
export async function runDoubaoWork(request) {
  const ctx=await context(request,'DoubaoWork');let state;
  try{state=await readJson(ctx.stateFile)}catch(e){if(e.code!=='ENOENT')throw e}
  if(state&&state.requestHash!==requestHash(request))throw Error('DOUBAO_MEMORY_REQUEST_DRIFT');
  const probe=await runProbe({endpoint:ENDPOINT,appPath:APP},{connect:(...args)=>chromium.connectOverCDP(...args)});
  if(probe.status!=='passed')throw Error('DOUBAO_READ_ONLY_PREFLIGHT_FAILED');
  const browser=await chromium.connectOverCDP(ENDPOINT,{timeout:10000});
  try {
    const page=await mainPage(browser);
    const uid=await page.evaluate(async()=> (await window._aha_api.account.getCurrentUser())?.uid??null);
    if(!uid)throw Error('DOUBAO_ACCOUNT_UNVERIFIED');
    let activity;
    try{activity=await readNativeToolActivity(browser)}catch(error){
      return await bindReply(ctx,request,{...baseReply(request,state?.config??{app_version:probe.app.version,model_display:'unobservable',permissions:'unobservable',underlying_model:null,account_fingerprint:sha(String(uid))}),
        status:'needs_attention',reason:'原生工具活动 profile 未核验，停止在发送之前。'}, {general_probe:probe,native_profile_error:error.message,prompt_sent:false});
    }
    const version=activity.native_client_version||probe.app.version;
    const fixed=state?.config??request.expected_config;
    if(fixed&&(fixed.account_fingerprint!==sha(String(uid))||fixed.app_version!==version||fixed.renderer_profile_sha256!==activity.profile_sha256))throw Error('DOUBAO_CLIENT_CONFIG_DRIFT');
    const projectName='WCB-MEM-'+sha(request.workspace).slice(0,14);
    const outputDir=join(ctx.control,'general-step'),generalStateFile=join(outputDir,'automation_state.json');
    if(request.action==='prepare_namespace'&&state?.phase==='namespace_prepared')return await bindReply(ctx,request,
      {...baseReply(request,state.config),status:'completed',background_settled:true,admission:state.admission},{general_probe:probe,native_activity:activity});
    if(request.action==='prepare_namespace'&&request.required_capabilities.some(k=>!CAPABILITIES.includes(k)))return await bindReply(ctx,request,
      {...baseReply(request,fixed??{app_version:version,model_display:'unobservable',permissions:'unobservable',account_fingerprint:sha(String(uid))}),status:'needs_attention',reason:'continue／restart 尚未验收。'});
    if(request.action==='execute_step'&&request.session_action!=='new')throw Error('DOUBAO_SESSION_ACTION_NOT_ADMITTED');
    if(request.action==='execute_step'&&state&&!['observe','retry_pre_send'].includes(request.transport_action))throw Error('DOUBAO_DUPLICATE_DISPATCH');
    if(request.action==='execute_step'&&!state&&request.transport_action!=='dispatch')throw Error('DOUBAO_ACCEPTANCE_UNKNOWN_NO_REDISPATCH');
    return await withUiLock(ctx,request,async()=>{
      execFileSync('/usr/bin/open',['-a',APP]);await page.bringToFront();
      // The workbench can hide project and permission controls in a narrow
      // composer. Collapse the inspected pane before requiring exact readback.
      const workbench=page.getByRole('button',{name:'收起侧边工作台',exact:true});
      if(await workbench.count()>1)throw Error('DOUBAO_WORKBENCH_CONTROL_AMBIGUOUS');
      if(await workbench.count()===1&&await workbench.isVisible()){
        await artifact(ctx,'layout-intent',{action:'collapse-side-workbench',prompt_sent:false});
        await workbench.click();
      }
      const settings=page.getByTestId('settings_modal');
      if(await settings.count()&&await settings.isVisible()){
        if(!(await settings.innerText()).startsWith('管理记忆'))throw Error('DOUBAO_FOREIGN_DIALOG');
        await settings.getByTestId('setting-modal-close').evaluate(e=>e.click());
      }
      if(request.action==='prepare_namespace') {
        if(activity.active.length||activity.pending_count)throw Error('DOUBAO_NATIVE_ACTIVITY_PRESENT');
        const observation=await inspectPage(page);assertNoConflictingActivity(observation.snapshot);
        await mkdir(request.workspace,{recursive:true});
        const mode=page.getByTestId('chat_input_action_mode');const original=(await mode.innerText()).trim();
        state??={requestHash:requestHash(request),phase:'preparing_namespace',original_runtime_mode:original};await saveState(ctx,state);
        await ensureLocalRuntimeMode(page, value=>artifact(ctx,'runtime-mode-intent',value));
      }
      const configPath=join(ctx.control,'general-step-config.json');let general;
      if(!state?.configPath) {
        const prompt=request.prompt??'命名空间准备，不发送本段占位文本。';
        const promptFile=join(dirname(request.workspace),'.memory-'+request.operation_id.slice(-16)+'.prompt.txt');
        await writeFile(promptFile,prompt,{flag:'wx'});
        general={scene:'general',taskRoot:dirname(request.workspace),workspace:request.workspace,candidateWorkspace:request.workspace,
          promptFile,prompt,promptSha256:sha(prompt),promptBytes:Buffer.byteLength(prompt),batchId:ctx.manifest.batch_id,
          taskId:request.episode_id+'_'+request.step_id,requestedModel:fixed?.model_display??null,requestedPermissionMode:'current',
          expectedAppVersion:probe.app.version,captureNativeTools:true,captureNativeLifecycle:true,
          manifestSha256:sha(await readFile(join(ctx.root,'manifest.json'))),
          frozenIdentity:{scene:'memory-step-general-native',operation_id:request.operation_id,namespace:request.namespace,
            workspace:request.workspace,prompt_sha256:request.prompt_sha256}};
        await writeFile(configPath,JSON.stringify(general,null,2),{flag:'wx'});
        state={...state,requestHash:requestHash(request),phase:request.action==='prepare_namespace'?'preparing_namespace':'general-step-started',config:fixed,configPath};
        await saveState(ctx,state);
      }else general=await readJson(configPath);
      const previous=await readJson(generalStateFile).catch(e=>{if(e.code==='ENOENT')return null;throw e});
      if(request.transport_action==='retry_pre_send'){
        assertMemoryPreSendRetry('DoubaoWork',previous);
        if(activity.active.length||activity.pending_count)throw Error('DOUBAO_RETRY_REQUIRES_NATIVE_IDLE');
        await artifact(ctx,'zero-send-retry-proof',{journal:previous,prompt_sha256:request.prompt_sha256,unknown_send_replay_allowed:false});
      }
      if(request.transport_action==='observe'&&request.action==='execute_step'&&(!previous||previous.send.dispatch_attempt_count===0))return await bindReply(ctx,request,
        {...baseReply(request,fixed),status:'needs_attention',reason:'旧操作没有已接受发送，观察入口不启动首次发送。'},{general_state:previous,prompt_sent:false});
      const options={scene:'general',taskRoot:general.taskRoot,outputDir,projectName,endpoint:ENDPOINT,appPath:APP,observeSeconds:8,
        prepareOnly:request.action==='prepare_namespace',validateTask:async()=>general,
        validateResume:async old=>{if(JSON.stringify(old.prepared)!==JSON.stringify(general.frozenIdentity)||old.prompt.sha256!==general.promptSha256)throw Error('DOUBAO_GENERAL_STEP_DRIFT')},
        connect:(...args)=>chromium.connectOverCDP(...args)};
      if(request.action==='prepare_namespace'&&previous&&request.transport_action!=='retry_pre_send')throw Error('DOUBAO_NAMESPACE_PREPARATION_INCOMPLETE_NO_RESEND');
      if(request.transport_action==='retry_pre_send')await retryPreSendDevelopmentRun(options);
      else if(previous)await resumeDevelopmentRun(options);else await startDevelopmentRun(options);
      const native=await readJson(generalStateFile);
      if(request.action==='prepare_namespace') {
        const ui=await readUiConfiguration(page,projectName);
        const config={app_version:version,installed_version:probe.app.version,renderer_profile_sha256:activity.profile_sha256,
          model_display:ui.model,model_observation:'native product UI tier; underlying model not exposed',permissions:ui.permission,
          underlying_model:null,account_fingerprint:sha(String(uid)),runtime_mode:'本地电脑'};verifyConfig(config,request.expected_config);
        const admission={account_policy:'current_signed_in_account',test_scope_only:true,precondition_verified:true,
          capabilities:CAPABILITIES,isolation:'shared_account_cold_first',global_memory_reset_verified:false,precondition_scope:'verified_local_project_only'};
        state={...state,phase:'namespace_prepared',config,admission};await saveState(ctx,state);
        return await bindReply(ctx,request,{...baseReply(request,config),status:'completed',background_settled:true,admission},
          {general_probe:probe,native_activity:activity,general_preparation:native,prompt_sent:false});
      }
      const reply=baseReply(request,fixed);
      if(!native.native_observation?.artifact?.file)return await bindReply(ctx,request,{...reply,status:native.error?.code&&native.error.code!=='NATIVE_COMPLETED_AWAITING_COLLECTION'?'needs_attention':'active',
        reason:native.error?.message||'等待已绑定原生请求终态；不重发。'},{general_state:native});
      const raw=JSON.parse((await ownedArtifact(outputDir,native.native_observation.artifact)).toString('utf8'));
      const normalized=normalizeRuntimeMessages(raw,native);
      if(normalized.terminal!=='completed'||normalized.native_cwd!==request.workspace)return await bindReply(ctx,request,
        {...reply,status:'needs_attention',reason:'原生请求未正常完成或目录未核验。'},{general_state:native,native_terminal:normalized.terminal});
      if(native.actual.model!==fixed.model_display||native.actual.permission_mode!==fixed.permissions)throw Error('DOUBAO_NATIVE_MODEL_PERMISSION_DRIFT');
      const tools=JSON.parse((await ownedArtifact(outputDir,native.native_observation.native_tools_artifact)).toString('utf8'));
      const toolProof=normalizeNativeToolEvents(tools,{attemptId:native.attempt_id,workspace:request.workspace,
        agentId:normalized.native_request_session_id,conversationId:native.session.conversation_id,
        sentAt:native.timing.sent_at,finishedAt:native.native_observation.equivalent_finished_at||normalized.finished_at||new Date().toISOString()});
      if(toolProof.status!=='complete-for-protocol')throw Error('DOUBAO_NATIVE_TOOL_COVERAGE_INCOMPLETE');
      reply.native={session_id:native.session.conversation_id,turn_id:normalized.reply_message_id,cwd:normalized.native_cwd};
      state.firstTerminalObservedAt??=Date.now();await saveState(ctx,state);
      const seconds=(Date.now()-state.firstTerminalObservedAt)/1000;
      if(seconds<request.memory_wait_seconds)return await bindReply(ctx,request,{...reply,status:'active',reason:'等待本轮即时行为观察窗；后台记忆形成未证明。'});
      reply.status='completed';reply.memory_observation={status:'unobservable',wait_seconds:seconds};
      reply.final_response=await artifact(ctx,'response',(await ownedArtifact(outputDir,native.native_observation.final_reply)).toString('utf8'));
      reply.trace=await artifact(ctx,'trace',{source_kind:'doubaowork-native-step',runtime_messages:raw,native_tools:tools,general_state:native});
      return await bindReply(ctx,request,reply,{general_state:native,prompt_binding_status:'verified',tool_coverage:toolProof,
        native_timing:{agent_duration_seconds:normalized.agent_duration_seconds??null}});
    });
  }finally{await browser.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{console.log(JSON.stringify(await runDoubaoWork(await stdinRequest())))}catch(error){console.error(error.stack||error);process.exitCode=2}
}
