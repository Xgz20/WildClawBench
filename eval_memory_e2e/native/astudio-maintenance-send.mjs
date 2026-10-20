/* One diagnostic UI send, with durable no-replay intent and native OS guards. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {discoverMainTarget,readUiConfiguration,fillPrompt,currentThreadId} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';
import {WorkBuddyCdpClient} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
import {queryNativeSessions,queryProjectForThread} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';
import {assertNativeContinuationBinding,inspectBoundContinuation} from './astudio-bound-continuation.mjs';
import {isBlockingActiveSession} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';
import {clickAStudioStableTarget,dispatchAStudioOnce,withAStudioSendEvents,readAStudioRpcTransport,
  waitForAStudioClickTransport,waitForAStudioSendFocus,aStudioForegroundCheck} from './astronstudio.mjs';
import {memoryPython} from './machine.mjs';
const root=path.resolve(process.argv[2]),read=file=>JSON.parse(fs.readFileSync(root+'/'+file));
const plan=read('diagnostic-plan.json'),prepared=read('ui-preparation-completed.json'),boundary=read('frozen-boundary.json');
const mode=process.argv[3]??'trigger',prefix=mode==='recall-bound'?'recall2-':mode==='recall'?'recall-':'ui-';
if(!['trigger','recall','recall-bound'].includes(mode))throw Error('ASTUDIO_MAINTENANCE_SEND_MODE');
const resumePrepared=process.argv[4]==='resume-prepared';
const view=JSON.parse(fs.readFileSync(plan.scope));
const check=(ok,reason)=>{if(!ok)throw Error(reason)};
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
const senderPath=fileURLToPath(import.meta.url),senderSha=sha(fs.readFileSync(senderPath));
const output=name=>root+'/'+(mode!=='trigger'?name.replace(/^ui-/,prefix):name);
const publish=(name,value)=>fs.writeFileSync(output(name),JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});
check(plan.contract==='astudio-automatic-formation-diagnostic/v1'&&view.diagnostic_only===true
  &&(!fs.existsSync(output('ui-send-intent.json'))||resumePrepared),'ASTUDIO_MAINTENANCE_SEND_OBSERVE_ONLY');
if(resumePrepared){
  const state=read('recall2-send-state.json'),failure=read('recall2-preparation-failed.json');
  check(mode==='recall-bound'&&state.phase==='prepared'&&failure.status==='KNOWN_ZERO_INPUT_AND_ZERO_SEND'
    &&!fs.existsSync(output('ui-send-dom-events.json'))&&!fs.existsSync(output('ui-send-result.json')),'ASTUDIO_MAINTENANCE_UNSAFE_RESUME');
}
if(mode!=='trigger')check(read('cycle-observer-result.json').status==='CYCLE_COMPLETED','ASTUDIO_MAINTENANCE_CYCLE_NOT_DONE');
let expectedBinding;
if(mode==='recall-bound'){
  const rejected=read('recall-send-state.json'),events=read('recall-send-dom-events.json'),saved=read('readback-native-binding-snapshot.json');
  check(rejected.phase==='pre_send_rejected'&&rejected.click_result?.clicked===false&&rejected.click_result.mouse_press_count===0
    &&events.event_count===0&&events.dropped_events===0,'ASTUDIO_MAINTENANCE_PRIOR_SEND_NOT_ZERO');
  expectedBinding={thread_id:prepared.result.workspace.thread_id,workspace:prepared.workspace,project_id:prepared.result.workspace.project_id,
    session_id:saved.session.session_id,previous_turn_id:saved.session.turn_id};
}
process.env.TMPDIR=root+'/control/ui-tmp';
function attest(){
  return JSON.parse(execFileSync(memoryPython(),[path.resolve('eval_memory_e2e/astudio_scope.py'),'attest','--scope',plan.scope,
    '--boundary-json',JSON.stringify(boundary)],{encoding:'utf8',timeout:30000}));
}
const initial=attest(),mainPid=initial.launch_identity.pid;
check(initial.status==='PASS'&&execFileSync('/usr/sbin/lsof',['-nP','-iTCP:9240','-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim()===String(mainPid),
  'ASTUDIO_MAINTENANCE_SEND_OWNER');
const sessions=await queryNativeSessions(view.paths.astudio_db);
check(!sessions.some(isBlockingActiveSession),'ASTUDIO_MAINTENANCE_FRONT_REQUEST_ACTIVE');
const readBinding=async()=>({sessions:await queryNativeSessions(view.paths.astudio_db),projects:await queryProjectForThread(view.paths.astudio_db,expectedBinding.thread_id)});
if(expectedBinding)assertNativeContinuationBinding(await readBinding(),expectedBinding);
const target=await discoverMainTarget('http://127.0.0.1:9240',30000),client=await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl,30000);
try{
  const ui=await readUiConfiguration(client),thread=await currentThreadId(client);
  check(thread===prepared.result.workspace.thread_id&&ui.model==='GLM-5.2'&&ui.reasoning==='High'&&ui.permission==='完全访问',
    'ASTUDIO_MAINTENANCE_SEND_ROUTE_OR_CONFIG');
  const prompt=mode!=='trigger'?read('recall-plan.json').prompt:plan.ui_probe_prompt;
  const operation='op-'+sha(plan.experiment_id+'\0'+mode+'\0'+prompt+'\0'+prepared.workspace);
  const newIntent={at:new Date().toISOString(),operation_id:operation,thread_id:thread,workspace:prepared.workspace,
    prompt,prompt_sha256:sha(prompt),sender_source:{path:senderPath,sha256:senderSha},
    main_pid:mainPid,model:'GLM-5.2',reasoning:'High',permissions:'完全访问',formal20:false,
    ...(expectedBinding?{zero_send_recovery_of:read('recall-send-intent.json').operation_id,native_binding:expectedBinding}:{} )};
  if(resumePrepared){
    const old=read('recall2-send-intent.json');
    check(old.operation_id===operation&&old.prompt_sha256===sha(prompt)&&old.thread_id===thread&&old.workspace===prepared.workspace,
      'ASTUDIO_MAINTENANCE_RESUME_INTENT_DRIFT');
    publish('ui-send-code-recovery.json',{at:new Date().toISOString(),original_intent_sha256:sha(fs.readFileSync(output('ui-send-intent.json'))),
      original_source:old.sender_source,new_source:newIntent.sender_source,reason:'Known no-input preparation failure; retain exact existing draft, no previous click or native turn.'});
  }else publish('ui-send-intent.json',newIntent);
  const state=resumePrepared?read('recall2-send-state.json'):{operation_id:operation,thread_id:thread,phase:'prepared'};
  const persist=value=>fs.writeFileSync(output('ui-send-state.json'),JSON.stringify(value,null,2)+'\n',{mode:0o600});
  persist(state);
  if(expectedBinding)check((await inspectBoundContinuation(client,prompt,expectedBinding,readBinding)).ready,'ASTUDIO_MAINTENANCE_EXISTING_DRAFT_CHANGED');
  else await fillPrompt(client,prompt,30000);
  const focus=()=>waitForAStudioSendFocus(mainPid,{maxWaitMs:60000,readDocument:()=>client.evaluate('({focused:document.hasFocus(),visible:document.visibilityState==="visible"})')});
  const result=await withAStudioSendEvents(client,operation,thread,()=>dispatchAStudioOnce(state,()=>clickAStudioStableTarget(client,prompt,prepared.workspace,{
    ...(expectedBinding?{read:()=>inspectBoundContinuation(client,prompt,expectedBinding,readBinding)}:{}),
    beforeMove:focus,finalFocus:()=>aStudioForegroundCheck(mainPid),beforePress:async()=>{
      check(sha(fs.readFileSync(senderPath))===senderSha,'ASTUDIO_MAINTENANCE_SENDER_DRIFT');
      publish('ui-send-os-before-press.json',attest());
      return waitForAStudioClickTransport(()=>readAStudioRpcTransport(client),{maxWaitMs:30000});
    }}),persist),evidence=>publish('ui-send-dom-events.json',evidence));
  publish('ui-send-result.json',{at:new Date().toISOString(),operation_id:operation,result,prompt_resend_authorized:false});
  console.log(JSON.stringify({status:result.clicked?'SENT_OBSERVE_ONLY':'PRE_SEND_REJECTED',operation_id:operation,result}));
}finally{client.close()}
