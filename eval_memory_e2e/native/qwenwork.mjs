import {pathToFileURL} from 'node:url';
import {join} from 'node:path';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {chromium} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/node_modules/playwright-core/index.mjs';
import {buildReadOnlyProbe,parseProbeArgs} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/probe.mjs';
import {calculateQwenCanaryConfigDigest,loadQwenCanaryConfig,createLiveDependencies,runQwenGeneralAttempt,
  QWENWORK_CANARY_CONFIG_SCHEMA} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs';
import {chooseQwenWorkMainPage,readQwenUiConfiguration,ensureQwenNewTaskView,openQwenProjectByName,
  confirmQwenWorkspaceProject} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/ui.mjs';
import {queryQwenProjectRows} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/session-state.mjs';
import {context,sha,requestHash,readJson,saveState,artifact,withUiLock,requireGui,
  baseReply,bindReply,verifyConfig,stdinRequest,assertMemoryPreSendRetry} from './common.mjs';

const ENDPOINT='http://127.0.0.1:9250',DB='/Users/gzx/Library/Application Support/QwenWorkCN/data/agents.db';
const TRACE='/Users/gzx/.qwenworkcn';
const CAPABILITIES=['new'];
async function authUid(page) {
  return page.evaluate(async()=>{
    const id=Date.now()+Math.floor(Math.random()*1000);
    const response=await new Promise((ok,no)=>{
      const timer=setTimeout(()=>no(Error('QWEN_ACCOUNT_QUERY_TIMEOUT')),4000);
      window.electronTRPC.onMessage(m=>{if(m.id===id){clearTimeout(timer);ok(m)}});
      window.electronTRPC.sendMessage({method:'request',operation:{id,type:'query',path:'auth.authCheck',input:undefined,context:{}}});
    });
    return response.result?.data?.json?.userId??null;
  });
}
async function closeSettings(page) {
  const dialog=page.locator('[role=dialog]').filter({has:page.getByText('意识模式',{exact:true})});
  if(await dialog.count()) {
    await page.evaluate(()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true})));
    await dialog.waitFor({state:'hidden',timeout:5000});
  }
}
export async function runQwenWork(request) {
  const ctx=await context(request,'QwenWork');let state;
  try{state=await readJson(ctx.stateFile)}catch(e){if(e.code!=='ENOENT')throw e}
  await requireGui();
  const probe=await buildReadOnlyProbe(parseProbeArgs(['--endpoint',ENDPOINT]));
  if(probe.execution_environment?.verified!==true)throw Error('QWEN_ENVIRONMENT_UNVERIFIED');
  const probePath=await artifact(ctx,'native-probe',probe),probeSha=sha(await readFile(probePath));
  const browser=await chromium.connectOverCDP(ENDPOINT,{timeout:10000});
  let config;
  try {
    const page=await chooseQwenWorkMainPage(browser,10000);
    const uid=await authUid(page);if(!uid)throw Error('QWEN_ACCOUNT_ID_UNAVAILABLE');
    let ui;try{ui=await readQwenUiConfiguration(page)}catch{ui=null}
    const frozen=state?.config??request.expected_config;
    config={app_version:probe.app.version,model_display:ui?.model.actual_model??frozen?.model_display,
      permissions:ui?.permission.confirmed_mode??frozen?.permissions,underlying_model:null,account_fingerprint:sha(String(uid))};
    verifyConfig(config,request.expected_config);
    if(state&&state.requestHash!==requestHash(request))throw Error('QWEN_MEMORY_REQUEST_DRIFT');
    if(request.action==='prepare_namespace') {
      if(request.required_capabilities.some(k=>!CAPABILITIES.includes(k)))return await bindReply(ctx,request,{...baseReply(request,config),status:'needs_attention',reason:'该任务链需要尚未验收的 continue 或 restart 能力。'});
      if(probe.native_state.database.active_or_pending_count!==0)throw Error('QWEN_NOT_IDLE');
      if((await queryQwenProjectRows(DB)).some(p=>p.cwd===request.workspace))throw Error('QWEN_NAMESPACE_NOT_FRESH');
      if(!state)await saveState(ctx,{requestHash:requestHash(request),phase:'namespace_prepared',config});
      return await bindReply(ctx,request,{...baseReply(request,config),status:'completed',background_settled:true,
        admission:{account_policy:'current_signed_in_account',test_scope_only:true,precondition_verified:true,capabilities:CAPABILITIES,
          isolation:'shared_account_cold_first',global_memory_reset_verified:false,precondition_scope:'fresh_workspace_only'}},
        {general_probe:probe,account_identity_method:'native auth.authCheck userId -> sha256'});
    }
    if(state&&!['observe','retry_pre_send'].includes(request.transport_action))throw Error('QWEN_DUPLICATE_DISPATCH');
    if(!state&&request.transport_action!=='dispatch')throw Error('QWEN_ACCEPTANCE_UNKNOWN_NO_REDISPATCH');
    if(request.session_action!=='new')throw Error('QWEN_SESSION_ACTION_NOT_ADMITTED');
    return await withUiLock(ctx,request,async()=>{
      await closeSettings(page);
      const configPath=join(ctx.control,'general-step-config.json');
      if(!state) {
        const promptPath=join(ctx.control,'prompt.txt');await writeFile(promptPath,request.prompt,{flag:'wx'});
        await mkdir(join(ctx.control,'general-evidence'),{recursive:true});
        const raw={schema_version:QWENWORK_CANARY_CONFIG_SCHEMA,config_digest_algorithm:'sha256-canonical-json/v1',
          identity:{batch_id:ctx.manifest.batch_id,unit_id:request.episode_id,task_id:request.step_id+'-'+request.operation_id.slice(-10),attempt_id:'a01'},
          dataset:{id:ctx.manifest.dataset_id,digest:ctx.manifest.dataset_sha256},task_root:ctx.root,candidate_workspace:request.workspace,
          prompt:{path:promptPath,sha256:request.prompt_sha256},state_file:join(ctx.control,'general-journal.json'),evidence_root:join(ctx.control,'general-evidence'),
          client:{endpoint:ENDPOINT,bundle_id:'cn.qwenwork.desktop.mac',platform:'macos',session_db:DB,trace_root:TRACE},
          control:{desktop_slot_id:'memory-ui-single-slot',probe_path:probePath,probe_sha256:probeSha,probe_max_age_seconds:900,
            model_policy:'keep-current',permission_policy:'keep-current',create_new_project:true,live_execution_authorized:true,
            clarification_policy:'manual',sensitive_output_policy:'manual',timeout_ms:30000}};
        raw.config_digest=calculateQwenCanaryConfigDigest(raw);
        await writeFile(configPath,JSON.stringify(raw,null,2),{flag:'wx'});
        state={requestHash:requestHash(request),phase:'prepared',config,configPath};await saveState(ctx,state);
      }
      const existingJournal=await readJson(join(ctx.control,'general-journal.json')).catch(e=>{if(e.code==='ENOENT')return null;throw e});
      if(request.transport_action==='retry_pre_send'){
        assertMemoryPreSendRetry('QwenWork',existingJournal);
        if(probe.native_state.database.active_or_pending_count!==0)throw Error('QWEN_RETRY_REQUIRES_NATIVE_IDLE');
        await artifact(ctx,'zero-send-retry-proof',{journal:existingJournal,prompt_sha256:request.prompt_sha256,unknown_send_replay_allowed:false});
      }
      if(request.transport_action==='observe'&&(!existingJournal||existingJournal.send.dispatch_attempt_count===0)) {
        return await bindReply(ctx,request,{...baseReply(request,config),status:'needs_attention',
          reason:'该旧操作未形成发送；观察入口不会替它启动第一次发送。保留旧证据，在新批次验证修复。'},
          {general_journal:existingJournal,zero_send_verified:existingJournal?.send.dispatch_attempt_count===0,prompt_sent:false});
      }
      const cfg=await loadQwenCanaryConfig(configPath,{requireLiveAuthorization:true,resume:Boolean(existingJournal),
        ...(existingJournal?{resumeProbePath:probePath,resumeProbeSha256:probeSha}:{})});
      cfg.resume=Boolean(existingJournal);
      cfg.observe_once=true;
      const live=await createLiveDependencies(cfg);
      try {
        const livePage=await chooseQwenWorkMainPage(live.browser,10000);
        const originalPrepare=live.dependencies.prepareUi;
        live.dependencies.prepareUi=async()=>{
          const projects=await queryQwenProjectRows(DB);
          const existing=projects.filter(p=>p.cwd===request.workspace);
          let prepared;
          if(existing.length) {
            const project=confirmQwenWorkspaceProject({projects,workspace:request.workspace});
            const names=projects.map(p=>p.project_name).filter(Boolean);
            await ensureQwenNewTaskView(livePage,30000,project.project_name,names);
            await openQwenProjectByName(livePage,project.project_name,30000,names);
            prepared={project,configuration:await readQwenUiConfiguration(livePage)};
          }else prepared=await originalPrepare();
          if(prepared.configuration.model.actual_model!==config.model_display||prepared.configuration.permission.confirmed_mode!==config.permissions)throw Error('QWEN_MEMORY_CONFIG_DRIFT_BEFORE_SEND');
          return prepared;
        };
        state.phase='general-step-started';await saveState(ctx,state);
        const result=await runQwenGeneralAttempt(cfg,live.dependencies);
        const journal=result.journal;
        const reply=baseReply(request,config);
        if(journal.phase==='NEEDS_ATTENTION'||journal.phase==='FAILED')return await bindReply(ctx,request,
          {...reply,status:'needs_attention',reason:journal.attention?.message||journal.phase},{general_journal:journal});
        if(journal.phase!=='COMPLETED')return await bindReply(ctx,request,{...reply,status:'active',reason:'General 原生观察仍未结束；恢复同一发送。'},{general_journal:journal});
        const evidence=await live.dependencies.verifySessionPrompt(journal.session,cfg.prompt);
        const raw=await readFile(evidence.transcript_path,'utf8');
        if(sha(raw)!==evidence.transcript_sha256)return await bindReply(ctx,request,
          {...reply,status:'active',reason:'原生轨迹尾部仍在更新，等待稳定快照，不重发。'},{transcript_evidence:evidence});
        const rows=raw.trim().split(/\r?\n/).map(line=>JSON.parse(line));
        const users=rows.filter(r=>r.type==='user'&&r.message?.content?.some(p=>p.type==='text'&&sha(p.text)===request.prompt_sha256));
        if(users.length!==1||!users[0].uuid)throw Error('QWEN_NATIVE_USER_TURN_ID_UNVERIFIED');
        reply.native={session_id:journal.session.session_id,turn_id:users[0].uuid,cwd:request.workspace};
        state.firstTerminalObservedAt??=Date.now();await saveState(ctx,state);
        const seconds=(Date.now()-state.firstTerminalObservedAt)/1000;
        if(seconds<request.memory_wait_seconds)return await bindReply(ctx,request,{...reply,status:'active',reason:'等待即时行为观察窗；尚未证明后台记忆形成。'});
        reply.status='completed';reply.memory_observation={status:'unobservable',wait_seconds:seconds};
        reply.final_response=await artifact(ctx,'response',rows.filter(r=>r.type==='assistant').at(-1)?.message?.content?.filter(p=>p.type==='text').map(p=>p.text).join('\n')??'');
        reply.trace=await artifact(ctx,'trace',raw);
        return await bindReply(ctx,request,reply,{general_journal:journal,transcript_evidence:evidence,native_turn_identity_kind:'user_message_uuid',prompt_binding_status:'verified'});
      }finally{await live.browser.close()}
    });
  }finally{await browser.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{console.log(JSON.stringify(await runQwenWork(await stdinRequest())))}catch(error){console.error(error.stack||error);process.exitCode=2}
}
