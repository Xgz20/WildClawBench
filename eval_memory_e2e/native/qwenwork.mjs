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
  baseReply,bindReply,verifyConfig,stdinRequest,assertMemoryPreSendRetry,readQwenMemoryOperationUi} from './common.mjs';
import {execFileSync} from 'node:child_process';
import {MACHINE_PATHS,memoryPython} from './machine.mjs';

/** QwenWork 1.3.1 SDK projection: preserve native rows, derive a transcript.
 * Never generate a legacy native JSONL or write the source database.
 */

const QUERY=String.raw`import sys,json,sqlite3,base64
from pathlib import Path
p=Path(sys.argv[1]);s=json.loads(sys.argv[2])
if p.resolve()!=p: raise ValueError('QWEN_SQLITE_SOURCE_SYMLINK')
c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
c.execute('pragma query_only=on');c.execute('BEGIN')
identity=c.execute('''SELECT sc.id sub_chat_id,sc.chat_id conversation_id,sc.session_id,ch.local_project_id,
COALESCE(json_extract(lp.root_paths,'$[0]'),pr.path,ch.worktree_path) cwd,
sc.stream_id,json_extract(ch.ext,'$.taskStatus') native_status
FROM sub_chats sc JOIN chats ch ON ch.id=sc.chat_id
LEFT JOIN local_projects lp ON lp.id=ch.local_project_id LEFT JOIN projects pr ON pr.id=ch.project_id
WHERE sc.id=? AND sc.chat_id=? AND sc.session_id=? AND ch.deleted_at IS NULL''',
(s['sub_chat_id'],s['conversation_id'],s['session_id'])).fetchall()
if len(identity)!=1: raise ValueError('QWEN_SQLITE_IDENTITY_COUNT')
def serial(row):
 d=dict(row)
 for k,v in d.items():
  if isinstance(v,bytes):
   try:d[k]=v.decode('utf8')
   except UnicodeDecodeError:d[k]={'encoding':'base64','data':base64.b64encode(v).decode()}
 return d
messages=[serial(r) for r in c.execute('SELECT * FROM messages WHERE sub_chat_id=? ORDER BY sequence,id',(s['sub_chat_id'],))]
trajectory=[serial(r) for r in c.execute('SELECT * FROM agent_trajectory_log WHERE sub_chat_id=? ORDER BY seq,id',(s['sub_chat_id'],))]
if len(messages)>2000 or len(trajectory)>20000: raise ValueError('QWEN_SQLITE_EVIDENCE_BUDGET')
print(json.dumps({'source_kind':'qwen-native-sqlite-sdk-projection/v1','identity':dict(identity[0]),'messages':messages,'trajectory':trajectory},ensure_ascii=False))
c.rollback();c.close()`;

export function normalizeQwenSqliteSnapshot(snapshot,session,promptSha) {
  if(snapshot?.source_kind!=='qwen-native-sqlite-sdk-projection/v1')throw Error('QWEN_SQLITE_SOURCE_KIND');
  for(const key of ['session_id','sub_chat_id','conversation_id','local_project_id','cwd'])
    if(!session[key]||snapshot.identity?.[key]!==session[key])throw Error('QWEN_SQLITE_IDENTITY_MISMATCH:'+key);
  if(!Array.isArray(snapshot.messages)||!Array.isArray(snapshot.trajectory))throw Error('QWEN_SQLITE_SOURCE_SHAPE');
  const rows=snapshot.messages.map(m=>{
    if(m.sub_chat_id!==session.sub_chat_id||m.chat_id!==session.conversation_id||!m.message_id
      ||!['user','assistant'].includes(m.role))throw Error('QWEN_SQLITE_MESSAGE_IDENTITY');
    const parts=JSON.parse(m.parts),metadata=JSON.parse(m.metadata||'{}');
    if(!Array.isArray(parts)||metadata.sessionId!==session.session_id)throw Error('QWEN_SQLITE_MESSAGE_METADATA');
    return {type:m.role,uuid:m.message_id,sessionId:session.session_id,cwd:session.cwd,
      message:{content:parts},native_metadata:metadata,source_kind:snapshot.source_kind};
  });
  const users=rows.filter(r=>r.type==='user'&&r.message.content.some(p=>p.type==='text'&&typeof p.text==='string'&&sha(p.text)===promptSha));
  if(users.length!==1)throw Error('QWEN_SQLITE_PROMPT_MATCH_COUNT:'+users.length);
  if(new Set(rows.map(r=>r.uuid)).size!==rows.length)throw Error('QWEN_SQLITE_MESSAGE_ID_REUSED');
  for(const e of snapshot.trajectory)if(e.sub_chat_id!==session.sub_chat_id)throw Error('QWEN_SQLITE_TRAJECTORY_IDENTITY');
  return {rows,user:users[0],terminal:snapshot.identity.native_status==='completed'&&!snapshot.identity.stream_id
    &&snapshot.trajectory.some(e=>e.event_type==='turn_end')};
}

export async function qwenSqlitePromptEvidence(ctx,session,prompt) {
  const bytes=execFileSync(memoryPython(),
    ['-c',QUERY,MACHINE_PATHS.qwen_db,JSON.stringify(session)],
    {timeout:15000,maxBuffer:25*1024*1024});
  const snapshot=JSON.parse(bytes),normalized=normalizeQwenSqliteSnapshot(snapshot,session,prompt.sha256);
  const sourcePath=await artifact(ctx,'sqlite-native-snapshot',snapshot);
  const transcript=normalized.rows.map(r=>JSON.stringify(r)).join('\n')+'\n';
  const transcriptPath=await artifact(ctx,'sqlite-derived-transcript',transcript);
  return {verified:true,prompt_sha256:prompt.sha256,match_count:1,
    transcript_path:transcriptPath,transcript_sha256:sha(transcript),transcript_size:Buffer.byteLength(transcript),
    source_kind:snapshot.source_kind,source_snapshot_path:sourcePath,source_snapshot_sha256:sha(JSON.stringify(snapshot,null,2)+'\n'),
    native_user_message_id:normalized.user.uuid,native_terminal_verified:normalized.terminal};
}

const ENDPOINT='http://127.0.0.1:9250',DB=MACHINE_PATHS.qwen_db;
const TRACE=MACHINE_PATHS.qwen_trace;
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
  const dialog=page.locator('[role=dialog]').filter({has:page.getByText(/^(?:意识模式|全局记忆)$/)});
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
    const frozen=state?.config??request.expected_config;
    const observed=await readQwenMemoryOperationUi({transportAction:request.transport_action,frozen},()=>readQwenUiConfiguration(page));
    const ui=observed.ui;
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
      const live=await createLiveDependencies(cfg);
      try {
        if(probe.app.version==='1.3.1')live.dependencies.verifySessionPrompt=(session,prompt)=>qwenSqlitePromptEvidence(ctx,session,prompt);
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
        if(journal.phase!=='COMPLETED')return await bindReply(ctx,request,{...reply,status:'active',reason:'General 原生观察仍未结束；恢复同一发送。'},{general_journal:journal,configuration_basis:observed.basis});
        const terminal=await readQwenMemoryOperationUi({transportAction:request.transport_action,frozen,terminal:true},()=>readQwenUiConfiguration(livePage));
        if(terminal.ui.model.actual_model!==config.model_display||terminal.ui.permission.confirmed_mode!==config.permissions)throw Error('QWEN_MEMORY_TERMINAL_CONFIG_DRIFT');
        const evidence=await live.dependencies.verifySessionPrompt(journal.session,cfg.prompt);
        if(evidence.source_kind&&evidence.native_terminal_verified!==true)throw Error('QWEN_SQLITE_NATIVE_TERMINAL_UNVERIFIED');
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
        reply.trace=evidence.source_kind?await artifact(ctx,'trace',{source_kind:evidence.source_kind,
          native_snapshot:await readJson(evidence.source_snapshot_path),derived_transcript:rows}):await artifact(ctx,'trace',raw);
        return await bindReply(ctx,request,reply,{general_journal:journal,transcript_evidence:evidence,native_turn_identity_kind:'user_message_uuid',prompt_binding_status:'verified',configuration_basis:terminal.basis,terminal_ui_configuration:terminal.ui});
      }finally{await live.browser.close()}
    });
  }finally{await browser.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{console.log(JSON.stringify(await runQwenWork(await stdinRequest())))}catch(error){console.error(error.stack||error);process.exitCode=2}
}
