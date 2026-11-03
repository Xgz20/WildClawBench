#!/usr/bin/env node
// Explicitly authorized new attempt; never replay an uncertain original send.
import {createHash,randomUUID} from "node:crypto";
import {execFile as callbackExec} from "node:child_process";
import {promisify} from "node:util";
import {mkdir,open,readFile,realpath,lstat,writeFile,rename,unlink,readdir} from "node:fs/promises";
import {hostname} from "node:os";
import {join,relative,resolve,dirname} from "node:path";
import {fileURLToPath} from "node:url";
import {resolveWorkBuddyBatchInvocation,verifyWorkBuddyQueueRepairs} from "./batch.mjs";
import {assertWorkBuddyExecutionReadiness,assertWorkBuddyNativeIdle} from "./execute.mjs";
import {inspectWorkBuddyMacos,parseArgs as probeArgs} from "./probe.mjs";
import {getWorkBuddyRuntimeConversation} from "./runtime-binding.mjs";
import {validateCancelledReview,validateServiceErrorReview} from "./park-terminal-review.mjs";
import {discoverWorkBuddyMainTarget,WorkBuddyCdpClient} from "./ui.mjs";
const execFile=promisify(callbackExec),sha=b=>createHash("sha256").update(b).digest("hex"),json=v=>Buffer.from(JSON.stringify(v,null,2)+"\n");
const requireOk=(x,c)=>{if(!x)throw Error("WORKBUDDY_AUTHORIZED_RETRY_"+c)};
async function plain(path){requireOk(await realpath(path)===resolve(path)&&(await lstat(path)).isFile(),"UNSAFE_FILE");return readFile(path)}
async function persist(path,value){const tmp=path+"."+randomUUID()+".tmp";await writeFile(tmp,json(value),{flag:"wx",mode:0o600});await rename(tmp,path)}
async function inventory(root){const rows=[];async function walk(p,rel=""){for(const e of await readdir(p,{withFileTypes:true})){const f=join(p,e.name),r=rel+e.name,s=await lstat(f);requireOk(!s.isSymbolicLink(),"WORKSPACE_SYMLINK_REQUIRES_REVIEW");if(e.isDirectory()){rows.push({path:r,kind:"directory",mode:s.mode&0o777});await walk(f,r+"/")}else{requireOk(e.isFile(),"WORKSPACE_SPECIAL_FILE");const b=await readFile(f);rows.push({path:r,kind:"file",sha256:sha(b),size:b.length,mode:s.mode&0o777})}}}await walk(root);return rows.sort((a,b)=>a.path.localeCompare(b.path))}
export function validateRetryAuthorization(m,q){
  requireOk(m.schema_version==="wildclawbench.workbuddy-authorized-terminal-retry/v1"
    &&m.user_authorization?.trim()&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/.test(m.new_attempt_id||"")&&m.new_attempt_id!==m.old_attempt_id,"EXPLICIT_AUTHORIZATION_REQUIRED");
  const row=q.tasks.find(t=>t.task_id===m.task_id),review=(q.terminal_reviews||[]).find(r=>r.task_id===m.task_id&&r.attempt_id===m.old_attempt_id);
  requireOk(row?.attempt_id===m.old_attempt_id&&row.phase==="NEEDS_ATTENTION"&&row.dispatch_attempt_count===1
    &&review?.native_terminal_observed===true,"CANCELLED_REVIEW_REQUIRED");return {row,review};
}
export async function retryTerminalReview(manifestPath,{resume=false}={}){
  const mb=await plain(resolve(manifestPath)),m=JSON.parse(mb),cfg=await resolveWorkBuddyBatchInvocation(m.original_argv.slice(2));
  const root=cfg.root,config=cfg.configs.find(c=>c.task.task_id===m.task_id);requireOk(config,"TASK_UNKNOWN");
  const output=resolve(m.output_root),rel=relative(root,output);requireOk(rel.startsWith(".general-e2e/authorized-retries/")&&!rel.split("/").includes(".."),"OUTPUT_INVALID");
  const qp=join(root,".general-e2e/queues/workbuddy",cfg.batch.queueId+".json"),qb=await plain(qp),q=JSON.parse(qb);
  const owner=q.last_owner;requireOk(owner?.host===hostname()&&owner.pid===m.expected_owner_pid,"OWNER_UNKNOWN");
  try{process.kill(owner.pid,0);throw Error("WORKBUDDY_AUTHORIZED_RETRY_OWNER_ACTIVE")}catch(e){if(e.code!=="ESRCH")throw e}
  const held=[];let client;
  try{
    for(const path of [join(root,".general-e2e/queues/workbuddy/owner-lock.json"),config.uiLockFile]){const f=await open(path,"wx",0o600),st=await f.stat();held.push({f,path,st});await f.writeFile(json({pid:process.pid,host:hostname(),kind:"authorized-new-attempt"}))}
    for(const c of cfg.configs){try{await lstat(c.lockFile);throw Error("WORKBUDDY_AUTHORIZED_RETRY_ATTEMPT_LOCK_EXISTS")}catch(e){if(e.code!=="ENOENT")throw e}}
    const report=await inspectWorkBuddyMacos({...probeArgs([]),appPath:config.appPath,sessionDb:config.sessionDb,extensionDataRoot:config.dataRoot,endpoint:config.endpoint,timeoutMs:10000});
    assertWorkBuddyExecutionReadiness(report,config.endpoint);assertWorkBuddyNativeIdle(report);
    requireOk(report.application.version===cfg.manifest.unit.harness.version,"HARNESS_VERSION_DRIFT");
    const tp=join(output,"transaction.json");let tx;
    if(resume){tx=JSON.parse(await plain(tp));requireOk(tx.manifest_sha256===sha(mb),"MANIFEST_CHANGED");if(tx.status==="COMMITTED")return tx;}
    else{
      requireOk(sha(qb)===m.queue_sha256,"QUEUE_CHANGED");await verifyWorkBuddyQueueRepairs(root,q);
      const {row,review}=validateRetryAuthorization(m,q);
      const old={...q.frozen},current={...cfg.frozen};for(const k of ["driver_sha256","batch_sha256","ui_sha256"]){delete old[k];delete current[k]}
      requireOk(JSON.stringify(old)===JSON.stringify(current),"FROZEN_SCOPE_CHANGED");
      const jb=await plain(config.journalFile),sb=await plain(config.stateFile),journal=JSON.parse(jb),state=JSON.parse(sb);
      const target=await discoverWorkBuddyMainTarget(config.endpoint,10000);client=await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl,10000);
      const loaded=await getWorkBuddyRuntimeConversation(client,row.conversation_id);
      const sdkRef=review.artifacts.find(r=>r.path.endsWith("/native.jsonl")),sdk=await plain(join(root,sdkRef.path));requireOk(sha(sdk)===sdkRef.sha256,"SDK_DRIFT");
      const validate=review.profile==="workbuddy-native-service-error-503-terminal-review/v1"?validateServiceErrorReview:validateCancelledReview;
      const proof=validate({row,journal,state,loaded,sdkRows:sdk.toString().trim().split(/\r?\n/u).map(JSON.parse),promptSha256:config.promptSha256});
      await mkdir(dirname(output),{recursive:true});requireOk(await realpath(dirname(output))===dirname(output),"OUTPUT_ALIAS");await mkdir(output);
      const ws=await inventory(config.candidateWorkspace),control=await inventory(config.controlRoot);
      tx={status:"PREPARED",manifest_sha256:sha(mb),original_queue_sha256:sha(qb),old_attempt_id:m.old_attempt_id,new_attempt_id:m.new_attempt_id,
        task_id:m.task_id,workspace_inventory:ws,control_inventory:control,original_review:review,native_proof:proof,queue:q};
      for(const [n,b]of [["authorization.json",mb],["original-queue.json",qb],["native-before.json",json(loaded)],["original-journal.json",jb],["original-state.json",sb]])await writeFile(join(output,n),b,{flag:"wx",mode:0o444});
      await persist(tp,tx);
    }
    const archiveWorkspace=join(output,"original-workspace"),archiveControl=join(output,"original-control"),staged=join(output,"fresh-workspace");
    if(tx.status==="PREPARED"){
      requireOk(sha(json(await inventory(config.candidateWorkspace)))===sha(json(tx.workspace_inventory)),"WORKSPACE_DRIFT");
      const script=fileURLToPath(new URL("../../scripts/restore_workbuddy_initial_workspace.py",import.meta.url));
      const restore=await execFile(m.python||"/usr/bin/python3",[script,"--unit-root",root,"--task-id",m.task_id,"--target",staged],{maxBuffer:1024*1024});
      tx.restore=JSON.parse(restore.stdout);tx.fresh_workspace_inventory=await inventory(staged);tx.status="RESTORED_STAGING";await persist(tp,tx);
    }
    if(tx.status==="RESTORED_STAGING"){
      if(await lstat(archiveWorkspace).catch(()=>null))requireOk(sha(json(await inventory(archiveWorkspace)))===sha(json(tx.workspace_inventory)),"ARCHIVE_WORKSPACE_DRIFT");
      else{requireOk(sha(json(await inventory(config.candidateWorkspace)))===sha(json(tx.workspace_inventory)),"WORKSPACE_DRIFT");await rename(config.candidateWorkspace,archiveWorkspace)}
      if(await lstat(archiveControl).catch(()=>null))requireOk(sha(json(await inventory(archiveControl)))===sha(json(tx.control_inventory)),"ARCHIVE_CONTROL_DRIFT");
      else{requireOk(sha(json(await inventory(config.controlRoot)))===sha(json(tx.control_inventory)),"CONTROL_DRIFT");await rename(config.controlRoot,archiveControl)}
      tx.status="ORIGINAL_ARCHIVED";await persist(tp,tx);
    }
    if(tx.status==="ORIGINAL_ARCHIVED"){
      if(await lstat(staged).catch(()=>null))await rename(staged,config.candidateWorkspace);
      requireOk(sha(json(await inventory(config.candidateWorkspace)))===sha(json(tx.fresh_workspace_inventory)),"FRESH_WORKSPACE_DRIFT");
      await mkdir(config.controlRoot,{recursive:true});tx.status="NEW_WORKSPACE_READY";await persist(tp,tx);
    }
    if(tx.status==="NEW_WORKSPACE_READY"){
      if(!tx.proposed_queue){
      const state=structuredClone(tx.queue),row=state.tasks.find(t=>t.task_id===m.task_id),oldPrefix=relative(root,config.controlRoot)+"/",newPrefix=relative(root,archiveControl)+"/";
      const relocations=[];for(const repair of state.source_repairs||[])for(const ref of repair.artifacts||[])if(ref.path.startsWith(oldPrefix)){const old=ref.path;ref.path=newPrefix+ref.path.slice(oldPrefix.length);relocations.push({old_path:old,new_path:ref.path,sha256:ref.sha256})}
      state.terminal_reviews=state.terminal_reviews.filter(r=>r.task_id!==m.task_id||r.attempt_id!==m.old_attempt_id);
      const proof={schema_version:"wildclawbench.workbuddy-authorized-terminal-retry-proof/v1",task_id:m.task_id,old_attempt_id:m.old_attempt_id,new_attempt_id:m.new_attempt_id,
        user_authorization:m.user_authorization,original_review:tx.original_review,original_queue_sha256:tx.original_queue_sha256,relocations,original_attempt_preserved:true,new_prompts_sent:0};
      const proofPath=join(output,"retry-proof.json");if(!await lstat(proofPath).catch(()=>null))await writeFile(proofPath,json(proof),{flag:"wx",mode:0o444});else requireOk(sha(await plain(proofPath))===sha(json(proof)),"PROOF_DRIFT");
      const artifacts=[];for(const n of ["authorization.json","original-queue.json","native-before.json","original-journal.json","original-state.json","retry-proof.json"]){const path=join(output,n),b=await plain(path);artifacts.push({path:relative(root,path),sha256:sha(b),size:b.length})}
      const pointer={schema_version:"wildclawbench.workbuddy-authorized-retry-case/v1",task_id:m.task_id,
        old_attempt_id:m.old_attempt_id,new_attempt_id:m.new_attempt_id,sources:artifacts};
      const pointerPath=join(config.controlRoot,"authorized-retry.json");
      if(!await lstat(pointerPath).catch(()=>null))await writeFile(pointerPath,json(pointer),{flag:"wx",mode:0o444});
      else requireOk(sha(await plain(pointerPath))===sha(json(pointer)),"CASE_POINTER_DRIFT");
      state.authorized_retries=[...(state.authorized_retries||[]),{task_id:m.task_id,old_attempt_id:m.old_attempt_id,new_attempt_id:m.new_attempt_id,artifacts}];
      Object.assign(row,{attempt_id:m.new_attempt_id,phase:"PENDING",dispatch_attempt_count:0,conversation_id:null,request_id:null,cwd:null,started_at:null,dispatch_started_at:null,finished_at:null,native_started_at:null,native_finished_at:null,error:null,exit_code:null});delete row.pre_send_recovery;
      state.frozen=cfg.frozen;state.frozen_sha256=cfg.digest;state.phase="PENDING";state.active_task_ids=[];
      state.events.push({event:"EXPLICITLY_AUTHORIZED_TERMINAL_RETRY",at:new Date().toISOString(),task_id:m.task_id,old_attempt_id:m.old_attempt_id,new_attempt_id:m.new_attempt_id,proof:relative(root,proofPath)});
      tx.proposed_queue=state;await persist(tp,tx);
      }
      const state=tx.proposed_queue;
      const current=sha(await plain(qp));if(current===tx.original_queue_sha256){await persist(qp,state)}else requireOk(current===sha(json(state)),"QUEUE_CHANGED_BEFORE_COMMIT");
      tx.status="COMMITTED";tx.committed_at=new Date().toISOString();await persist(tp,tx);
    }
    return {status:tx.status,task_id:m.task_id,old_attempt_id:m.old_attempt_id,new_attempt_id:m.new_attempt_id,new_prompts_sent:0,proof_root:output};
  }finally{await client?.close();for(const {f,path,st}of held.reverse()){await f.close();const cur=await lstat(path).catch(()=>null);if(cur?.ino===st.ino&&cur.dev===st.dev)await unlink(path)}}
}
if(process.argv[1]&&await realpath(resolve(process.argv[1])).catch(()=>null)===await realpath(fileURLToPath(import.meta.url))){const i=process.argv.indexOf("--manifest");if(i<0)throw Error("usage: retry-terminal-review.mjs --manifest ABS [--resume]");retryTerminalReview(process.argv[i+1],{resume:process.argv.includes("--resume")}).then(r=>console.log(JSON.stringify(r,null,2))).catch(e=>{console.error(e.stack);process.exitCode=1})}
