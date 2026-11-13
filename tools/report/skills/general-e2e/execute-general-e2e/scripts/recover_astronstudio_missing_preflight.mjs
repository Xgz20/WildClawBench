#!/usr/bin/env node
// Exact 0.14.81 preflight rejection recovery. No project, task, Prompt or send.
import {createHash, randomUUID} from 'node:crypto';
import {readFile, writeFile, mkdir, open, lstat, readdir, readlink, realpath, rm} from 'node:fs/promises';
import {join, resolve, relative, isAbsolute, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseBatchArgs, resolveBatchPlan, acquireWorkerLock, persistQueue} from './run_astronstudio_macos_batch.mjs';
import {queryNativeSessions, queryExactProjectsForWorkspace} from './lib/astronstudio-state.mjs';
import {isBlockingActiveSession} from './execute_astronstudio_macos.mjs';
import {CdpClient, discoverMainTarget} from './lib/astronstudio-cdp.mjs';

export const ORIGINAL_DRIVER_SHA256 = 'a1c3ed41c9aceb9ccc96843e626b927c608d0de53adc7fd089c323322b9d4fc8';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const require = (ok, code) => {if (!ok) throw Error('MISSING_PREFLIGHT_' + code);};
const json = async path => JSON.parse(await readFile(path, 'utf8'));

export function validateMissingPreflightRow(queue, taskId) {
  const rows = queue.tasks.filter(t => t.task_id === taskId);
  require(rows.length === 1 && queue.phase === 'NEEDS_ATTENTION', 'QUEUE_STATE');
  const row = rows[0];
  require(row.phase === 'NEEDS_ATTENTION' && row.error?.code === 'DRIVER_STATE_MISSING'
    && row.driver_exit_code === 2 && row.selected_attempt_id === null
    && row.dispatch_attempt_count === 0 && !(row.attempts || []).length
    && Object.values(row.session || {}).every(v => v === null), 'NOT_EXACT_ZERO_SEND');
  const last = queue.history.filter(e => e.task_id === taskId).at(-1);
  require(last?.event === 'TASK_DISPATCH_RETURNED' && last.driver_exit_code === 2
    && last.attempt_id === null && last.task_phase === 'NEEDS_ATTENTION', 'DISPATCH_HISTORY');
  return row;
}

async function verifyInitialTree(root, expected) {
  require(await realpath(root) === root, 'WORKSPACE_LINK');
  const actual = [];
  async function walk(directory, prefix='') {
    for (const name of (await readdir(directory)).sort()) {
      const path=join(directory,name), rel=prefix?prefix+'/'+name:name, info=await lstat(path);
      const entry={path:rel,mode:(info.mode&0o777).toString(8).padStart(4,'0')};
      if(info.isSymbolicLink()) {entry.kind='symlink';entry.target=await readlink(path);}
      else if(info.isDirectory()) entry.kind='directory';
      else {require(info.isFile(),'WORKSPACE_TYPE');entry.kind='file';const bytes=await readFile(path);entry.size=bytes.length;entry.sha256=sha(bytes);}
      actual.push(entry);if(entry.kind==='directory') await walk(path,rel);
    }
  }
  await walk(root);
  const canonical=v=>JSON.stringify(v.map(e=>Object.fromEntries(Object.entries(e).sort())).sort((a,b)=>a.path.localeCompare(b.path)));
  require(canonical(actual)===canonical(expected),'INITIAL_WORKSPACE_CHANGED');
  return sha(Buffer.from(canonical(actual)));
}

export async function recoverMissingPreflight(options) {
  const args=parseBatchArgs(['--unit-root',options.unitRoot,'--run-config',options.runConfig,
    '--queue-id',options.queueId,'--run-slots','3','--continue-on-terminal-failure','--resume']);
  const plan=await resolveBatchPlan(args), before=await readFile(plan.queueStateFile), queue=JSON.parse(before);
  require(queue.identity.queue_digest===plan.queueDigest,'QUEUE_DIGEST');
  const row=validateMissingPreflightRow(queue,options.taskId), task=plan.manifest.tasks.find(t=>t.task_id===options.taskId);
  require(task,'TASK');
  require(sha(await readFile(options.originalDriver))===ORIGINAL_DRIVER_SHA256,'ORIGINAL_DRIVER_SOURCE');
  const failure=await readFile(options.failureLog), text=failure.toString('utf8').trim();
  require(/^AstronStudio 存在不属于当前队列的活动 session：[0-9a-z-]+(?:,[0-9a-z-]+)*$/u.test(text),'ORIGINAL_FAILURE_SIGNATURE');
  const control=join(plan.unitRoot,'.general-e2e/execution',options.taskId);
  for(const name of ['automation-state.json','execution-record.json','final-response.md','driver.lock']) {
    let exists=false;try{await lstat(join(control,name));exists=true;}catch(e){if(e.code!=='ENOENT')throw e;}
    require(!exists,'TARGET_CONTROL_EXISTS');
  }
  const lock=await acquireWorkerLock(plan.workerLockFile,false), uiPath=join(plan.unitRoot,'.general-e2e/astronstudio-ui.lock');
  let uiLock,client;
  const receipt={schema_version:'wildclawbench.astronstudio-missing-preflight-recovery/v1',status:'PREPARING',
    queue_id:options.queueId,task_id:options.taskId,original_queue_sha256:sha(before),
    original_driver_sha256:ORIGINAL_DRIVER_SHA256,failure_log_sha256:sha(failure),
    prompt_send_calls:0,new_task_calls:0,new_project_calls:0,workspace_files_changed:false,at:new Date().toISOString()};
  const output=resolve(options.output);
  try {
    uiLock=await open(uiPath,'wx',0o600);await uiLock.writeFile(JSON.stringify({pid:process.pid,kind:'missing-preflight-recovery'}));
    const workspace=resolve(plan.unitRoot,task.workspace.path);
    const initialTree=await verifyInitialTree(workspace,task.workspace.entries);
    const sessions=await queryNativeSessions(plan.runConfig.state_database.path);
    require(!sessions.some(isBlockingActiveSession),'NATIVE_NOT_GLOBAL_IDLE');
    require(!sessions.some(s=>s.cwd===workspace),'TARGET_NATIVE_SESSION_EXISTS');
    require((await queryExactProjectsForWorkspace(plan.runConfig.state_database.path,workspace)).length===0,'TARGET_NATIVE_PROJECT_EXISTS');
    const target=await discoverMainTarget(plan.runConfig.control.endpoint,10000);client=await CdpClient.connect(target.webSocketDebuggerUrl);
    const ui=await client.evaluate(`(()=>{const visible=e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0;const es=[...document.querySelectorAll('[data-testid="composer-editor"]')].filter(visible);return {route:location.hash,editors:es.length,text:es[0]?.innerText?.trim()??null,chips:es[0]?.querySelectorAll('[role="link"][contenteditable="false"]').length??null,dialogs:[...document.querySelectorAll('[role="dialog"],[role="alertdialog"],[aria-modal="true"]')].filter(visible).length};})()`);
    require(ui.editors===1&&ui.text===''&&ui.chips===0&&ui.dialogs===0,'UNKNOWN_UI_OR_DRAFT');
    require(!(await queryNativeSessions(plan.runConfig.state_database.path)).some(isBlockingActiveSession),'LATE_NATIVE_ACTIVITY');
    require(sha(await readFile(plan.queueStateFile))===sha(before),'QUEUE_CHANGED');
    const archive=join(plan.queueRoot,'missing-preflight-recoveries',randomUUID());await mkdir(archive,{recursive:true});
    await writeFile(join(archive,'original-queue-state.json'),before,{flag:'wx',mode:0o600});
    await writeFile(join(archive,'original-driver-stderr.log'),failure,{flag:'wx',mode:0o600});
    Object.assign(receipt,{archive,initial_workspace_tree_sha256:initialTree,native_global_idle:true,
      target_native_project_count:0,target_native_session_count:0,ui_empty:true,ui_route:ui.route});
    await mkdir(dirname(output),{recursive:true});
    await writeFile(output,JSON.stringify(receipt,null,2)+'\n',{flag:'wx',mode:0o600});
    row.phase='PENDING';row.error=null;row.started_at=null;row.finished_at=null;row.driver_exit_code=null;
    queue.phase='PENDING';queue.error=null;queue.current_task_id=null;queue.active_task_ids=[];
    queue.history.push({at:new Date().toISOString(),event:'STRICT_MISSING_PREFLIGHT_ZERO_SEND_RECOVERED',task_id:options.taskId,
      original_queue_sha256:sha(before),recovery_receipt:output,recovery_script_sha256:sha(await readFile(fileURLToPath(import.meta.url)))});
    await persistQueue(plan,queue);
    receipt.status='RECOVERED';receipt.recovered_queue_sha256=sha(await readFile(plan.queueStateFile));
    // The preparation receipt stays immutable; publish completion separately.
    await writeFile(output+'.completed.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx',mode:0o600});
    return receipt;
  } finally {
    client?.close();if(uiLock){await uiLock.close();require((await json(uiPath)).pid===process.pid,'UI_LOCK_OWNER');await rm(uiPath);}
    await lock.release();
  }
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const options={},keys={'--unit-root':'unitRoot','--run-config':'runConfig','--queue-id':'queueId','--task-id':'taskId',
    '--failure-log':'failureLog','--original-driver':'originalDriver','--output':'output'};
  try{for(let i=2;i<process.argv.length;i+=2){const key=keys[process.argv[i]];require(key&&process.argv[i+1],'ARGUMENT');options[key]=process.argv[i+1];}
    require(Object.values(keys).every(k=>options[k]),'ARGUMENT');console.log(JSON.stringify(await recoverMissingPreflight(options),null,2));}
  catch(e){console.error(e.message);process.exitCode=2;}
}
