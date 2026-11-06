import {createHash} from 'node:crypto';
import {readFile,realpath} from 'node:fs/promises';
import {isAbsolute,join,resolve,relative} from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
export const FRAMEWORK_DISPATCH_AUTH = 'general-e2e.unaccepted-dispatch-retry-authorization/v1';
export const hash = b => createHash('sha256').update(b).digest('hex');
export const requireRetry = (ok,code) => {if(!ok)throw new Error('FRAMEWORK_DISPATCH_RETRY_'+code);};
export function assertUnacceptedDispatch(old, data, workspace) {
  requireRetry(old.phase==='NEEDS_ATTENTION'&&old.prompt?.send_status==='uncertain'
    &&old.send?.dispatch_attempt_count===1&&old.session?.verified===false
    &&!old.session.thread_id&&!old.session.turn_id&&!old.session.session_id
    &&['NATIVE_IDENTITY_UNAVAILABLE_AFTER_SEND','PROMPT_SEND_UNCERTAIN'].includes(old.execution?.error?.code),'ORIGINAL_NOT_ELIGIBLE');
  const route=old.send.post_send_route_thread_id;
  requireRetry(route&&route===old.send.pre_send_route_thread_id,'ROUTE');
  for(const table of ['projection_turns','projection_thread_messages','projection_thread_sessions',
    'projection_pending_interactions','provider_runtime_open_turns','provider_session_runtime',
    'provider_runtime_events','queued_turn_promotions'])requireRetry(Array.isArray(data[table])&&!data[table].length,'LATE_NATIVE_ACCEPTANCE:'+table);
  requireRetry(data.projection_threads?.length===1&&data.projection_threads[0].thread_id===route
    &&data.projection_threads[0].latest_turn_id===null&&data.projection_projects?.length===1
    &&data.projection_projects[0].workspace_root===workspace
    &&data.projection_projects[0].project_id===data.projection_threads[0].project_id,'PROJECT');
  const events=data.orchestration_events;
  requireRetry(Array.isArray(events)&&events.length>=1&&events.every(e=>['thread.created','thread.meta-updated'].includes(e.event_type)),'OTHER_NATIVE_COMMAND');
  const receipts=data.orchestration_command_receipts, deliveries=data.orchestration_event_deliveries;
  requireRetry(receipts?.length===events.length&&receipts.every(r=>r.status==='accepted'
    &&r.aggregate_id===route&&events.some(e=>e.sequence===r.result_sequence)),'COMMAND_RECEIPT');
  requireRetry(deliveries?.length===events.length&&deliveries.every(d=>d.thread_id===route&&d.state==='succeeded'
    &&!d.claim_owner&&d.completed_at&&events.some(e=>e.sequence===d.event_sequence)),'PENDING_DELIVERY');
  return {profile:'human-authorized-unaccepted-dispatch/v1',route,model_turns:0,native_messages:0,
    original_send_counter_preserved:1,root_cause:'human-classified-framework-send-failure'};
}
export async function readDispatchAuthorization(path) {
  requireRetry(isAbsolute(path)&&await realpath(path)===path,'AUTH_PATH');
  const bytes=await readFile(path),auth=JSON.parse(bytes);
  requireRetry(auth.schema_version===FRAMEWORK_DISPATCH_AUTH&&auth.cleanup_authorized===true&&auth.retry_authorized===true,'HUMAN_AUTH_REQUIRED');
  for(const k of ['task_id','queue_id','batch_id','unit_id','old_attempt_id','new_attempt_id'])requireRetry(/^[A-Za-z0-9_.-]+$/.test(auth[k]||''),'IDENTITY:'+k);
  requireRetry(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(auth.new_attempt_id)&&auth.new_attempt_id!==auth.old_attempt_id,'NEW_ATTEMPT');
  for(const k of ['old_state_sha256','old_record_sha256','old_workspace_sha256','unit_manifest_sha256','run_config_digest','queue_digest','queue_state_sha256'])requireRetry(/^[0-9a-f]{64}$/.test(auth[k]||''),'SHA:'+k);
  requireRetry(isAbsolute(auth.human_source?.path||'')&&/^[0-9a-f]{64}$/.test(auth.human_source?.sha256||''),'HUMAN_SOURCE');
  return {auth,bytes,sha256:hash(bytes)};
}
// A standing policy application is controller-authored and labelled as such.
// It preserves both original human statements and their original task context;
// it must never be presented as a new per-task answer from the human.
export async function verifyDispatchHumanAuthority(auth) {
  const bytes=await readFile(auth.human_source.path);requireRetry(hash(bytes)===auth.human_source.sha256,'HUMAN_SOURCE_SHA');
  const h=JSON.parse(bytes);
  requireRetry(h.retry_authorized===true&&h.cleanup_authorized===true&&h.task_id===auth.task_id
    &&h.old_attempt_id===auth.old_attempt_id&&h.human_statement&&h.question_item_id,'HUMAN_SCOPE');
  if(h.derived_application!==true)return {profile:'direct-specific-human-framework-retry',files:[]};
  requireRetry(h.schema_version==='general-e2e.standing-framework-retry-application/v1'
    &&h.applied_boundary==='no-native-prompt-acceptance-owned-draft-restored','STANDING_APPLICATION_PROFILE');
  const sources=[];
  for(const [key,name] of [['standing_policy','standing-policy.json'],['boundary_policy','boundary-policy.json']]) {
    const ref=h[key];requireRetry(isAbsolute(ref?.path||'')&&/^[0-9a-f]{64}$/.test(ref?.sha256||''),'STANDING_SOURCE');
    const raw=await readFile(ref.path);requireRetry(hash(raw)===ref.sha256,'STANDING_SOURCE_SHA');sources.push({name,bytes:raw,value:JSON.parse(raw)});
  }
  const policy=sources[0].value,boundary=sources[1].value;
  requireRetry(policy.schema_version==='general70-human-conditional-failure-disposition/v1'
    &&policy.conditions?.proven_framework_cause==='repair framework, preserve original, retry in independent attempt'
    &&policy.human_statement===h.human_statement&&policy.question_item_id===h.question_item_id,'STANDING_POLICY');
  requireRetry(boundary.schema_version==='general-e2e.framework-dispatch-retry-human-statement/v1'
    &&boundary.human_classification==='evaluation-framework-send-failure'&&boundary.cleanup_authorized===true
    &&boundary.retry_authorized===true&&boundary.task_id===h.boundary_context_task
    &&boundary.human_statement===h.boundary_statement&&boundary.question_item_id===h.boundary_question_item_id,'HUMAN_DEFINED_BOUNDARY');
  return {profile:'standing-human-framework-policy-applied-to-certified-unaccepted-dispatch',files:sources.map(({name,bytes})=>({name,bytes}))};
}
export async function archiveDispatchAttempt(unitRoot, authorizationPath, verifyOnly=false) {
  const argv=[fileURLToPath(new URL('../snapshot_framework_dispatch.py',import.meta.url)),
    '--unit-root',unitRoot,'--authorization',authorizationPath];
  if(verifyOnly)argv.push('--verify-only');
  const r=await new Promise((done,fail)=>{const p=spawn(process.env.GENERAL_E2E_PYTHON||'python3',argv,{stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});let out='',err='';
    p.stdout.setEncoding('utf8').on('data',v=>out+=v);p.stderr.setEncoding('utf8').on('data',v=>err+=v);p.once('error',fail);p.once('exit',code=>done({code,out,err}));});
  requireRetry(r.code===0,'ARCHIVE:'+r.err.slice(-1800));return JSON.parse(r.out);
}
export async function verifyFrameworkDispatchRecoveries(unitRoot,state,cache=new Set()) {
  for(const row of state.tasks)for(const tx of row.framework_dispatch_recoveries||[]) {
    requireRetry(tx.task_id===row.task_id&&tx.new_attempt_id&&tx.authorization_sha256&&tx.receipt_sha256,'QUEUE_TRANSACTION');
    const root=join(unitRoot,'.general-e2e/framework-dispatch-recoveries',row.task_id,tx.new_attempt_id);
    requireRetry(await realpath(root)===root,'RECOVERY_PATH');
    const receiptBytes=await readFile(join(root,'receipt.json')),receipt=JSON.parse(receiptBytes);
    requireRetry(hash(receiptBytes)===tx.receipt_sha256&&receipt.authorization_sha256===tx.authorization_sha256
      &&receipt.old_attempt_id===tx.old_attempt_id&&receipt.new_attempt_id===tx.new_attempt_id
      &&receipt.schema_version==='general-e2e.unaccepted-dispatch-retry-receipt/v1','RECEIPT');
    for(const source of receipt.sources||[]) {
      requireRetry(typeof source.path==='string'&&!isAbsolute(source.path)&&!source.path.split('/').includes('..'),'SOURCE_PATH');
      const p=resolve(root,source.path);requireRetry(await realpath(p)===p&&relative(root,p)&&!relative(root,p).startsWith('..'),'SOURCE_ESCAPE');
      const b=await readFile(p);requireRetry(hash(b)===source.sha256&&b.length===source.size,'SOURCE_SHA');
    }
    requireRetry(hash(await readFile(join(root,'authorization.json')))===tx.authorization_sha256,'CACHED_AUTH');
    if(!cache.has(tx.receipt_sha256)) {await archiveDispatchAttempt(unitRoot,join(root,'authorization.json'),true);cache.add(tx.receipt_sha256);}
    const old=row.attempts.find(a=>a.attempt_id===tx.old_attempt_id),next=row.attempts.find(a=>a.attempt_id===tx.new_attempt_id);
    requireRetry(old&&next&&next.previous_attempt_id===old.attempt_id&&next.authorization_sha256===tx.authorization_sha256
      &&old.state_sha256===receipt.old_state_sha256,'ATTEMPT_LINEAGE');
  }
}
