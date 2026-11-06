#!/usr/bin/env node
// Explicit human-authorized recovery. It clears one owned draft and prepares
// one independent attempt; it never sends a Prompt or restarts the Harness.
import {readFile,writeFile,mkdir,open,rm,realpath,access,lstat} from 'node:fs/promises';
import {join,resolve,relative} from 'node:path';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {parseArgs,resolveExecutionConfig,initializeFrameworkDispatchRetry,isBlockingActiveSession} from './execute_astronstudio_macos.mjs';
import {parseBatchArgs,resolveBatchPlan,assertQueueIdentity,acquireWorkerLock,persistQueue} from './run_astronstudio_macos_batch.mjs';
import {queryNativeSessions} from './lib/astronstudio-state.mjs';
import {queryNativeStartRejection} from './lib/astronstudio-start-rejection.mjs';
import {probeAstronStudio} from './probe_astronstudio_macos.mjs';
import {CdpClient,discoverMainTarget,readUiConfiguration,renderExpectedPrompt,currentThreadId} from './lib/astronstudio-cdp.mjs';
import {readDispatchAuthorization,verifyDispatchHumanAuthority,assertUnacceptedDispatch,archiveDispatchAttempt,verifyFrameworkDispatchRecoveries,hash,requireRetry as check} from './lib/astronstudio-dispatch-retry.mjs';

const json=async p=>JSON.parse(await readFile(p,'utf8'));
const exists=async p=>{try{await access(p);return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}};
const alive=pid=>{try{process.kill(pid,0);return true;}catch(e){if(e.code==='ESRCH')return false;throw e;}};
const writeOnce=async(p,b)=>{if(await exists(p)){check(hash(await readFile(p))===hash(b),'ARTIFACT_DRIFT');return;}await writeFile(p,b,{flag:'wx',mode:0o400});};
const encoded=o=>Buffer.from(JSON.stringify(o,null,2)+'\n');
async function ownedDirectory(unit,target) {
  check(relative(unit,target)&&!relative(unit,target).startsWith('..'),'DIRECTORY_SCOPE');let current=unit;
  for(const part of relative(unit,target).split('/')) {current=join(current,part);
    if(await exists(current)){const s=await lstat(current);check(s.isDirectory()&&!s.isSymbolicLink(),'DIRECTORY_SYMLINK');}
    else await mkdir(current);
  }
}
export async function recoverUnacceptedDispatch(options,overrides={}) {
  const api={queryNativeSessions,queryNativeStartRejection,probeAstronStudio,discoverMainTarget,
    connect:(url)=>CdpClient.connect(url),readUiConfiguration,currentThreadId,archiveDispatchAttempt,...overrides};
  const authorization=await readDispatchAuthorization(resolve(options.authorization)),{auth}=authorization;
  const unit=await realpath(resolve(options.unitRoot));
  const queuePath=join(unit,'.general-e2e/queues',auth.queue_id,'queue-state.json');
  const qbytes=await readFile(queuePath),queue=JSON.parse(qbytes);
  const batchArgs=parseBatchArgs(['--unit-root',unit,'--run-config',options.runConfig,'--queue-id',auth.queue_id,
    '--run-slots',String(queue.configuration.run_slots),'--continue-on-terminal-failure','--resume']);
  const plan=await resolveBatchPlan(batchArgs);assertQueueIdentity(queue,plan);
  for(const k of ['batch_id','unit_id','queue_id','queue_digest'])check(queue.identity[k]===auth[k],'QUEUE_BINDING:'+k);
  check(plan.frozen.manifest_sha256===auth.unit_manifest_sha256&&plan.frozen.run_config_digest===auth.run_config_digest,'FROZEN_CONFIG');
  const row=queue.tasks.find(t=>t.task_id===auth.task_id);check(row,'TASK');
  check([auth.old_attempt_id,auth.new_attempt_id].includes(row.selected_attempt_id),'SELECTED_ATTEMPT_DRIFT');
  const config=await resolveExecutionConfig(parseArgs(['--unit-root',unit,'--task-id',auth.task_id,'--run-config',options.runConfig]));
  const root=join(unit,'.general-e2e/framework-dispatch-recoveries',auth.task_id,auth.new_attempt_id);
  const worker=await acquireWorkerLock(plan.workerLockFile,true,alive);
  let uiLock,client;const uiLockPath=join(unit,'.general-e2e/astronstudio-ui.lock'),token=randomUUID();
  try {
    if(await exists(join(root,'receipt.json'))) {
      const bytes=await readFile(join(root,'receipt.json')),receipt=JSON.parse(bytes);
      check(receipt.authorization_sha256===authorization.sha256,'EXISTING_RECEIPT_AUTH');
      await api.archiveDispatchAttempt(unit,join(root,'authorization.json'),true);
      const state=await json(config.stateFile);
      if(state.identity.attempt_id===auth.new_attempt_id&&row.selected_attempt_id===auth.new_attempt_id) {
        check(row.framework_dispatch_recoveries?.some(t=>t.receipt_sha256===hash(bytes)),'EXISTING_LINEAGE');
        await verifyFrameworkDispatchRecoveries(unit,queue);
        return {status:'ALREADY_PREPARED_OBSERVE_EXISTING_ATTEMPT',new_attempt_id:auth.new_attempt_id,prompt_send_calls:0};
      }
    } else check(hash(qbytes)===auth.queue_state_sha256&&row.selected_attempt_id===auth.old_attempt_id,'OLD_QUEUE_SHA');
    const oldBytes=await readFile(config.stateFile),recordBytes=await readFile(config.recordFile),old=JSON.parse(oldBytes);
    const newPending=old.identity.attempt_id===auth.new_attempt_id&&old.phase==='PENDING'&&old.send.dispatch_attempt_count===0;
    if(!newPending)check(hash(oldBytes)===auth.old_state_sha256&&hash(recordBytes)===auth.old_record_sha256,'OLD_STATE_SHA');
    const authority=await verifyDispatchHumanAuthority(auth);
    check(row.selected_attempt_id===auth.old_attempt_id&&hash(qbytes)===auth.queue_state_sha256,'PARTIAL_QUEUE_DRIFT');
    await ownedDirectory(unit,root);check(await realpath(root)===root,'RECOVERY_SYMLINK');
    await writeOnce(join(root,'authorization.json'),authorization.bytes);
    for(const source of authority.files)await writeOnce(join(root,source.name),source.bytes);
    await writeOnce(join(root,'queue-before.json'),qbytes);
    const original=newPending?await json(join(root,'failed-control/automation-state.json')):old;
    const idle=async()=>check(!(await api.queryNativeSessions(config.stateDatabase)).some(isBlockingActiveSession),'NATIVE_ACTIVE');
    const verifyNative=async()=>{await idle();const snapshot=await api.queryNativeStartRejection(config.stateDatabase,original);
      assertUnacceptedDispatch(original,snapshot,config.candidateWorkspace);return snapshot;};
    const snapshot=await verifyNative();
    const probe=await api.probeAstronStudio({appPath:config.appPath,stateDb:config.stateDatabase,endpoint:config.endpoint,
      endpointExplicit:true,output:null,configOutput:null,timeoutMs:10000},{databaseValidationScope:'runtime'});
    check(probe.ready,'PROBE');const f=probe.frozen_run_config;
    check(f.harness.client_version===config.runConfig.harness.client_version
      &&f.tested_model.display_name===config.expectedModel&&f.tested_model.reasoning_display===config.expectedReasoning
      &&f.tested_model.permission_display===config.expectedPermission,'CONFIG_DRIFT');
    uiLock=await open(uiLockPath,'wx',0o600);await uiLock.writeFile(JSON.stringify({pid:process.pid,token,kind:'authorized-unaccepted-dispatch-recovery'})+'\n');
    const target=await api.discoverMainTarget(config.endpoint,10000);client=await api.connect(target.webSocketDebuggerUrl);
    check(await api.currentThreadId(client)===original.send.post_send_route_thread_id,'UI_ROUTE');
    const uiConfig=await api.readUiConfiguration(client,config.stateDatabase);
    check(uiConfig.model===config.expectedModel&&uiConfig.reasoning===config.expectedReasoning
      &&uiConfig.permission===config.expectedPermission,'UI_CONFIG_DRIFT');
    const readUi=()=>client.evaluate(`(() => {const es=Array.from(document.querySelectorAll('[data-testid="composer-editor"]')).filter(e=>e.getBoundingClientRect().width>0);const e=es[0];return{route:location.hash,count:es.length,text:e?.innerText?.trim(),chips:e?Array.from(e.querySelectorAll('[role="link"][contenteditable="false"]')).map(c=>({title:c.getAttribute('title'),display:c.innerText})):[],workspace:Array.from(document.querySelectorAll('[data-testid="workspace-picker-trigger"],[data-testid="project-picker-trigger"]')).filter(e=>e.getBoundingClientRect().width>0).map(e=>e.getAttribute('title')),dialogs:Array.from(document.querySelectorAll('[role="dialog"],[role="alertdialog"],[aria-modal="true"]')).filter(e=>e.getBoundingClientRect().width>0).length}})()`);
    let ui=await readUi();check(ui.count===1&&ui.dialogs===0&&ui.workspace.length===1&&ui.workspace[0]===config.candidateWorkspace,'UI_SCOPE');
    const cleanupPath=join(root,'cleanup.json');
    if(await exists(cleanupPath)) {
      const previous=await json(cleanupPath);check(previous.authorization_sha256===authorization.sha256
        &&previous.original_route===original.send.post_send_route_thread_id&&ui.text===''&&ui.chips.length===0,'CLEANUP_RESUME');
    } else {
      check(renderExpectedPrompt(config.prompt.trim(),ui.chips)?.trim()===ui.text,'FOREIGN_DRAFT');
      await writeOnce(join(root,'native-before.json'),encoded(snapshot));await writeOnce(join(root,'ui-before.json'),encoded(ui));
      await api.archiveDispatchAttempt(unit,join(root,'authorization.json'),await exists(join(root,'archive-manifest.json')));
      await verifyNative();
      const selected=await client.evaluate(`(() => {const e=document.querySelector('[data-testid="composer-editor"]');if(location.hash!==${JSON.stringify(ui.route)}||e?.innerText?.trim()!==${JSON.stringify(ui.text)})return false;e.focus();const r=document.createRange();r.selectNodeContents(e);const s=getSelection();s.removeAllRanges();s.addRange(r);return document.activeElement===e;})()`);
      check(selected,'DRAFT_CHANGED');
      await client.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace'});
      await client.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace'});
      const after=await readUi();check(after.route===ui.route&&after.text===''&&after.chips.length===0&&after.dialogs===0,'CLEAR_NOT_VERIFIED');
      await writeOnce(cleanupPath,encoded({authorization_sha256:authorization.sha256,original_route:original.send.post_send_route_thread_id,
        before:ui,after,prompt_send_calls:0,page_reload_calls:0,app_restart_calls:0,at:new Date().toISOString()}));
    }
    await writeOnce(join(root,'native-after.json'),encoded(await verifyNative()));
    const receiptPath=join(root,'receipt.json');let receipt,receiptBytes;
    if(await exists(receiptPath)){receiptBytes=await readFile(receiptPath);receipt=JSON.parse(receiptBytes);}
    else {
      const sources=[];for(const name of ['authorization.json','human-source.json','queue-before.json','native-before.json','ui-before.json','cleanup.json','native-after.json','archive-manifest.json','failed-attempt.zip']) {
        const bytes=await readFile(join(root,name));sources.push({path:name,sha256:hash(bytes),size:bytes.length});}
      for(const {name} of authority.files){const bytes=await readFile(join(root,name));sources.push({path:name,sha256:hash(bytes),size:bytes.length});}
      receipt={schema_version:'general-e2e.unaccepted-dispatch-retry-receipt/v1',authorization_sha256:authorization.sha256,
        old_attempt_id:auth.old_attempt_id,new_attempt_id:auth.new_attempt_id,old_state_sha256:auth.old_state_sha256,
        old_record_sha256:auth.old_record_sha256,receipt_relative_path:relative(unit,receiptPath),sources,
        profile:'human-authorized-unaccepted-dispatch/v1',authority_profile:authority.profile,prompt_send_calls:0,initial_workspace_retained_verified:true,
        initial_workspace_verification_profile:(await json(join(root,'archive-manifest.json'))).initial_office_metadata
          ?'canonical-cwm-only-initial-input/v2':'exact-initial-workspace'};
      receiptBytes=encoded(receipt);await writeOnce(receiptPath,receiptBytes);
    }
    if(!newPending)await initializeFrameworkDispatchRetry(config,{...receipt,receipt_sha256:hash(receiptBytes)});
    const previous=row.attempts.find(a=>a.attempt_id===auth.old_attempt_id);check(previous,'OLD_REGISTERED_ATTEMPT');
    previous.selected=false;previous.state_path=relative(unit,join(root,'failed-control/automation-state.json'));
    previous.state_sha256=auth.old_state_sha256;previous.dispatch_attempt_count=1;
    previous.disposition='FRAMEWORK_SEND_FAILURE_NO_NATIVE_ACCEPTANCE';
    row.selected_attempt_id=auth.new_attempt_id;
    row.attempts.push({attempt_id:auth.new_attempt_id,state_path:row.execution_state_path,registered_at:new Date().toISOString(),
      selected:true,previous_attempt_id:auth.old_attempt_id,authorization_sha256:authorization.sha256});
    row.framework_dispatch_recoveries??=[];row.framework_dispatch_recoveries.push({task_id:auth.task_id,
      old_attempt_id:auth.old_attempt_id,new_attempt_id:auth.new_attempt_id,authorization_sha256:authorization.sha256,
      receipt_sha256:hash(receiptBytes),status:'ADOPTED'});
    Object.assign(row,{phase:'PENDING',started_at:null,finished_at:null,dispatch_attempt_count:0,error:null,
      session:{thread_id:null,turn_id:null,session_id:null,cwd:null}});
    queue.phase='NEEDS_ATTENTION';queue.error='FRAMEWORK_DISPATCH_RETRY_PREPARED_RESUME_REQUIRED';
    queue.history.push({at:new Date().toISOString(),event:'AUTHORIZED_UNACCEPTED_DISPATCH_RETRY_PREPARED',task_id:auth.task_id,
      old_attempt_id:auth.old_attempt_id,new_attempt_id:auth.new_attempt_id,authorization_sha256:authorization.sha256,receipt_sha256:hash(receiptBytes)});
    await persistQueue(plan,queue);
    return {status:'PREPARED',old_attempt_id:auth.old_attempt_id,new_attempt_id:auth.new_attempt_id,prompt_send_calls:0,
      receipt_path:receiptPath,receipt_sha256:hash(receiptBytes)};
  } finally {
    client?.close();if(uiLock){await uiLock.close();if((await json(uiLockPath)).token===token)await rm(uiLockPath);}
    await worker.release();
  }
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try{const a={};for(let i=2;i<process.argv.length;i+=2){const key={'--unit-root':'unitRoot','--run-config':'runConfig','--authorization':'authorization'}[process.argv[i]];check(key&&process.argv[i+1],'ARGUMENT');a[key]=process.argv[i+1];}
    check(a.unitRoot&&a.runConfig&&a.authorization,'ARGUMENTS_REQUIRED');console.log(JSON.stringify(await recoverUnacceptedDispatch(a),null,2));}
  catch(e){console.error(e.stack||e.message);process.exitCode=2;}
}
