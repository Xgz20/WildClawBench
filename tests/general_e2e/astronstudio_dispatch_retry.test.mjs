import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath} from 'node:fs/promises';
import {join,relative} from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {assertUnacceptedDispatch,hash,archiveDispatchAttempt,verifyDispatchHumanAuthority} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-dispatch-retry.mjs';
const emptyTables=['projection_turns','projection_thread_messages','projection_thread_sessions','projection_pending_interactions',
  'provider_runtime_open_turns','provider_session_runtime','provider_runtime_events','queued_turn_promotions'];
function boundary() {
  const old={phase:'NEEDS_ATTENTION',prompt:{send_status:'uncertain'},send:{dispatch_attempt_count:1,pre_send_route_thread_id:'route',post_send_route_thread_id:'route'},
    session:{verified:false,thread_id:null,turn_id:null,session_id:null},execution:{error:{code:'NATIVE_IDENTITY_UNAVAILABLE_AFTER_SEND'}}};
  const data={...Object.fromEntries(emptyTables.map(t=>[t,[]])),projection_threads:[{thread_id:'route',latest_turn_id:null,project_id:'p'}],
    projection_projects:[{project_id:'p',workspace_root:'/fixture/workspace'}],orchestration_events:[{sequence:1,event_type:'thread.created'}],
    orchestration_command_receipts:[{status:'accepted',aggregate_id:'route',result_sequence:1}],
    orchestration_event_deliveries:[{thread_id:'route',state:'succeeded',completed_at:'2026-11-06T00:00:00Z',claim_owner:null,event_sequence:1}]};
  return {old,data};
}
test('a human-authorized unaccepted dispatch retains its original click counter',()=>{
  const {old,data}=boundary();const p=assertUnacceptedDispatch(old,data,'/fixture/workspace');
  assert.equal(p.original_send_counter_preserved,1);assert.equal(old.prompt.send_status,'uncertain');
});
for(const table of emptyTables)test('late or pending native source blocks recovery: '+table,()=>{
  const {old,data}=boundary();data[table]=[{}];assert.throws(()=>assertUnacceptedDispatch(old,data,'/fixture/workspace'),/LATE_NATIVE_ACCEPTANCE/);
});
for(const kind of ['foreign','verified','pending-command'])test('rejects '+kind,()=>{
  const {old,data}=boundary();if(kind==='foreign')data.projection_projects[0].workspace_root='/other';
  if(kind==='verified')old.session.verified=true;if(kind==='pending-command')data.orchestration_event_deliveries[0].state='pending';
  assert.throws(()=>assertUnacceptedDispatch(old,data,'/fixture/workspace'),/FRAMEWORK_DISPATCH_RETRY_/);
});
const canonical=v=>JSON.stringify(v.map(e=>Object.fromEntries(Object.entries(e).sort(([a],[b])=>a.localeCompare(b)))));
async function archiveFixture(t) {
  const unit=await realpath(await mkdtemp(join(tmpdir(),'dispatch-retry-'))),id='task',newId=randomUUID();
  t.after(async()=>{spawnSync(process.env.GENERAL_E2E_PYTHON||'python3',['-c','import os,sys;from pathlib import Path;[(os.chflags(p,0) if hasattr(os,"chflags") else None) for p in Path(sys.argv[1]).rglob("*") if p.is_file()]',unit]);await rm(unit,{recursive:true,force:true});});
  const controls=join(unit,'.general-e2e/execution',id),workspace=join(unit,'execution/tasks/task/workspace');await mkdir(controls,{recursive:true});await mkdir(workspace,{recursive:true});
  const input=Buffer.from('pristine\n');await writeFile(join(workspace,'input.txt'),input,{mode:0o644});
  const entries=[{path:'input.txt',kind:'file',mode:'0644',size:input.length,sha256:hash(input)}];
  const manifest={tasks:[{task_id:id,workspace:{path:'execution/tasks/task/workspace',entries}}]};
  const raw=Buffer.from(JSON.stringify(manifest));await writeFile(join(unit,'manifest.json'),raw);
  const old={identity:{batch_id:'batch',unit_id:'unit',task_id:id,attempt_id:'old'},phase:'NEEDS_ATTENTION',prompt:{send_status:'uncertain'},send:{dispatch_attempt_count:1},session:{verified:false}};
  const oldRaw=Buffer.from(JSON.stringify(old)),record=Buffer.from(JSON.stringify({identity:old.identity}));
  await writeFile(join(controls,'automation-state.json'),oldRaw);await writeFile(join(controls,'execution-record.json'),record);
  const humanPath=join(unit,'human.json'),human=Buffer.from('direct human authorization');await writeFile(humanPath,human);
  const auth={schema_version:'general-e2e.unaccepted-dispatch-retry-authorization/v1',cleanup_authorized:true,retry_authorized:true,
    task_id:id,new_attempt_id:newId,old_attempt_id:'old',batch_id:'batch',unit_id:'unit',unit_manifest_sha256:hash(raw),
    old_state_sha256:hash(oldRaw),old_record_sha256:hash(record),old_workspace_sha256:hash(Buffer.from(canonical(entries))),human_source:{path:humanPath,sha256:hash(human)}};
  const root=join(unit,'.general-e2e/framework-dispatch-recoveries',id,newId);await mkdir(root,{recursive:true});
  const authPath=join(root,'authorization.json');await writeFile(authPath,JSON.stringify(auth));
  return {unit,root,authPath,workspace,controls,oldRaw};
}
test('immutable archive survives subsequent selected-workspace changes and leaves old state unchanged',async t=>{
  const f=await archiveFixture(t);const result=await archiveDispatchAttempt(f.unit,f.authPath);
  assert.equal(result.status,'ARCHIVED');assert.deepEqual(await readFile(join(f.controls,'automation-state.json')),f.oldRaw);
  await writeFile(join(f.workspace,'input.txt'),'new selected attempt output');
  assert.equal((await archiveDispatchAttempt(f.unit,f.authPath,true)).status,'VERIFIED');
});
test('changed candidate cannot be relabeled as pristine before the retry',async t=>{
  const f=await archiveFixture(t);await writeFile(join(f.workspace,'input.txt'),'unexpected write');
  await assert.rejects(archiveDispatchAttempt(f.unit,f.authPath),/WORKSPACE_/);
});

async function withRegisteredPreparation(f,kind='valid') {
  const old=JSON.parse(await readFile(join(f.controls,'automation-state.json')));
  Object.assign(old,{task_root:join(f.unit,'execution/tasks/task'),dataset:{id:'d',digest:'digest'},run_config:{config_digest:'config'}});
  const manifest=JSON.parse(await readFile(join(f.unit,'manifest.json'))),promptSha='a'.repeat(64);
  manifest.tasks.push({task_id:'owner',workspace:{path:'execution/tasks/owner/workspace',entries:[]},prompt:{sent_sha256:promptSha}});
  const manifestBytes=Buffer.from(JSON.stringify(manifest));await writeFile(join(f.unit,'manifest.json'),manifestBytes);
  const cwd=join(f.unit,'execution/tasks/owner/workspace');
  const native={thread_id:'thread',turn_id:'turn',latest_turn_id:'turn',session_id:'sid',cwd,status:'completed',turn_state:'completed',session_status:'ready',active_turn_id:null};
  const owner={identity:{batch_id:'batch',unit_id:'unit',task_id:'owner',attempt_id:'owner-attempt'},dataset:old.dataset,run_config:old.run_config,
    phase:'COMPLETED',candidate_workspace:cwd,execution:{business_status:'completed',finished_at:'2026-11-11T00:00:00Z'},
    prompt:{sha256:promptSha,send_status:'sent'},send:{dispatch_attempt_count:1},session:{...native,verified:true}};
  if(kind==='foreign-owner')owner.identity.unit_id='foreign';
  const ownerBytes=Buffer.from(JSON.stringify(owner)),prefix='completed-ui-owner-'+randomUUID();
  const proof={profile:'bound-completed-own-unit-ui-navigation/v1',status:'OWNERSHIP_VERIFIED',target_task_id:'task',owner_task_id:'owner',native,
    source_state_path:join(f.unit,'.general-e2e/execution/owner/automation-state.json'),source_state_snapshot:prefix+'.state.json',source_state_sha256:hash(ownerBytes),
    prompt_send_calls:0,dispatch_authorized:false,requires_fresh_visible_probe:true};
  if(kind==='bad-sha')proof.source_state_sha256='b'.repeat(64);
  if(kind==='foreign-target')proof.target_task_id='other';
  await writeFile(join(f.controls,prefix+'.state.json'),ownerBytes);await writeFile(join(f.controls,prefix+'.proof.json'),JSON.stringify(proof));
  const visible={profile:'owned-native-visible-send/v1',status:'PASS',identity:{batch_id:'batch',unit_id:'unit',task_id:'task'},run_config_digest:'config',
    original_process_identity_reverified:true,changed:true,before:{visibility:'hidden'},after:{visibility:'visible'},
    prompt_send_calls:0,app_restart_calls:0,native_open_calls:1,page_bring_to_front_calls:1};
  await writeFile(join(f.controls,'native-visibility-'+randomUUID()+'.json'),JSON.stringify(visible));
  const oldRaw=Buffer.from(JSON.stringify(old));await writeFile(join(f.controls,'automation-state.json'),oldRaw);
  const auth=JSON.parse(await readFile(f.authPath));Object.assign(auth,{old_state_sha256:hash(oldRaw),unit_manifest_sha256:hash(manifestBytes)});await writeFile(f.authPath,JSON.stringify(auth));
  return prefix;
}
test('failed-dispatch archive preserves and revalidates registered UI preparation source closure',async t=>{
  const f=await archiveFixture(t),prefix=await withRegisteredPreparation(f);assert.equal((await archiveDispatchAttempt(f.unit,f.authPath)).status,'ARCHIVED');
  const m=JSON.parse(await readFile(join(f.root,'archive-manifest.json')));assert.ok(m.entries.some(e=>e.archive_path==='failed-control/'+prefix+'.state.json'));
  assert.equal((await archiveDispatchAttempt(f.unit,f.authPath,true)).status,'VERIFIED');
});
for(const kind of ['foreign-owner','bad-sha','foreign-target'])test('registered preparation archive rejects '+kind,async t=>{
  const f=await archiveFixture(t);await withRegisteredPreparation(f,kind);await assert.rejects(archiveDispatchAttempt(f.unit,f.authPath),/PREPARATION_OWNER_/);
});

async function withPreSendHistory(f,kind='valid') {
  const current=JSON.parse(await readFile(join(f.controls,'automation-state.json'))),promptSha=hash(Buffer.from('frozen prompt'));
  const prefix=[{phase:'PENDING',event:'ATTEMPT_CREATED'},{phase:'FAILED',event:'PRE_SEND_DRIVER_ERROR'}];
  Object.assign(current,{candidate_workspace:f.workspace,task_root:join(f.workspace,'..'),dataset:{id:'dataset',digest:'a'.repeat(64)},run_config:{config_digest:'config'}});
  current.prompt.sha256=promptSha;
  const previous={...structuredClone(current),phase:'FAILED',prompt:{sha256:promptSha,send_status:'not_sent'},
    send:{dispatch_attempt_count:0,dispatch_armed_at:null,dispatch_completed_at:null},
    session:{verified:false,thread_id:null,turn_id:null,session_id:null},
    execution:{business_status:'infrastructure_error',error:{code:'PRE_SEND_DRIVER_ERROR'}},history:prefix};
  if(kind==='prior-sent')previous.send.dispatch_attempt_count=1;
  if(kind==='other-attempt')previous.identity.attempt_id='foreign';
  const previousBytes=Buffer.from(JSON.stringify(previous)),digest=hash(previousBytes);
  const previousRecord=Buffer.from(JSON.stringify({identity:previous.identity,phase:'FAILED'}));
  const folder=join(f.controls,'pre-send-failures'),statePath=join(folder,digest+'.json'),recordPath=join(folder,digest+'.execution-record.json');
  await mkdir(folder);await writeFile(statePath,previousBytes,{mode:0o600});await writeFile(recordPath,previousRecord,{mode:0o600});
  const event={phase:'PENDING',event:'ZERO_SEND_PREPARATION_RESUMED',previous_state_sha256:digest,
    previous_state_path:relative(f.unit,statePath),previous_record_path:relative(f.unit,recordPath),previous_record_sha256:hash(previousRecord)};
  current.history=[...structuredClone(prefix),event,{phase:'NEEDS_ATTENTION',event:'NATIVE_IDENTITY_UNAVAILABLE_AFTER_SEND'}];
  if(kind==='foreign-path')event.previous_state_path='outside.json';
  if(kind==='changed-history-prefix')current.history[0].event='changed';
  if(kind==='state-sha')await writeFile(statePath,previousBytes.toString()+' ');
  if(kind==='record-sha')await writeFile(recordPath,previousRecord.toString()+' ');
  if(kind==='unregistered-file')await writeFile(join(folder,'unknown.json'),'unregistered');
  const bytes=Buffer.from(JSON.stringify(current));await writeFile(join(f.controls,'automation-state.json'),bytes);
  const auth=JSON.parse(await readFile(f.authPath));auth.old_state_sha256=hash(bytes);await writeFile(f.authPath,JSON.stringify(auth));
  return {digest,statePath,recordPath,previousBytes,previousRecord,currentBytes:bytes};
}

test('archive preserves hash-bound zero-send history in both frozen control copy and immutable ZIP',async t=>{
  const f=await archiveFixture(t),h=await withPreSendHistory(f);const result=await archiveDispatchAttempt(f.unit,f.authPath);
  assert.equal(result.status,'ARCHIVED');
  assert.deepEqual(await readFile(join(f.root,'failed-control/pre-send-failures',h.digest+'.json')),h.previousBytes);
  assert.deepEqual(await readFile(join(f.root,'failed-control/pre-send-failures',h.digest+'.execution-record.json')),h.previousRecord);
  assert.deepEqual(await readFile(join(f.controls,'automation-state.json')),h.currentBytes);
  const manifest=JSON.parse(await readFile(join(f.root,'archive-manifest.json')));
  assert.equal(manifest.pre_send_failure_history.length,1);
  assert.ok(manifest.entries.some(row=>row.archive_path==='failed-control/pre-send-failures/'+h.digest+'.json'));
  await writeFile(join(f.workspace,'input.txt'),'new selected output');
  assert.equal((await archiveDispatchAttempt(f.unit,f.authPath,true)).status,'VERIFIED');
});
for(const kind of ['prior-sent','other-attempt','foreign-path','changed-history-prefix','state-sha','record-sha','unregistered-file'])
test('pre-send history rejects '+kind+' without dropping original records',async t=>{
  const f=await archiveFixture(t),h=await withPreSendHistory(f,kind);
  await assert.rejects(archiveDispatchAttempt(f.unit,f.authPath),/PRE_SEND_HISTORY_|UNEXPECTED_CONTROL_FILES/);
  assert.deepEqual(await readFile(join(f.controls,'automation-state.json')),h.currentBytes);
});

async function standingFixture(t) {
  const root=await realpath(await mkdtemp(join(tmpdir(),'standing-dispatch-authority-')));t.after(()=>rm(root,{recursive:true,force:true}));
  const policy={schema_version:'general70-human-conditional-failure-disposition/v1',context_task:'original-task',
    question_item_id:'original-policy-question',human_statement:'框架问题修复后可以独立重试',
    conditions:{proven_framework_cause:'repair framework, preserve original, retry in independent attempt'}};
  const boundary={schema_version:'general-e2e.framework-dispatch-retry-human-statement/v1',human_classification:'evaluation-framework-send-failure',
    task_id:'boundary-example',question_item_id:'boundary-question',human_statement:'没有送达是框架发送故障，清理后重试',cleanup_authorized:true,retry_authorized:true};
  const refs=[];for(const [name,value] of [['policy',policy],['boundary',boundary]]){const p=join(root,name+'.json'),bytes=Buffer.from(JSON.stringify(value));await writeFile(p,bytes);refs.push({path:p,sha256:hash(bytes)});}
  const h={schema_version:'general-e2e.standing-framework-retry-application/v1',derived_application:true,task_id:'new-task',old_attempt_id:'new-old-attempt',
    cleanup_authorized:true,retry_authorized:true,human_statement:policy.human_statement,question_item_id:policy.question_item_id,
    boundary_context_task:boundary.task_id,boundary_statement:boundary.human_statement,boundary_question_item_id:boundary.question_item_id,
    applied_boundary:'no-native-prompt-acceptance-owned-draft-restored',standing_policy:refs[0],boundary_policy:refs[1]};
  const source=join(root,'application.json');
  const save=async()=>{const bytes=Buffer.from(JSON.stringify(h));await writeFile(source,bytes);return {task_id:h.task_id,old_attempt_id:h.old_attempt_id,human_source:{path:source,sha256:hash(bytes)}};};
  return {h,save,policy,boundary,refs};
}
test('standing application preserves original human context and explicitly labels controller derivation',async t=>{
  const f=await standingFixture(t);const a=await verifyDispatchHumanAuthority(await f.save());
  assert.equal(a.profile,'standing-human-framework-policy-applied-to-certified-unaccepted-dispatch');assert.equal(a.files.length,2);
  assert.equal(JSON.parse(a.files[0].bytes).context_task,'original-task');assert.equal(JSON.parse(a.files[1].bytes).task_id,'boundary-example');
});
for(const kind of ['changed-source','wrong-context','fabricated-question','unresolved-boundary'])test('standing authority rejects '+kind,async t=>{
  const f=await standingFixture(t);
  if(kind==='changed-source')await writeFile(f.refs[0].path,'changed');
  if(kind==='wrong-context')f.h.boundary_context_task='pretend-new-task';
  if(kind==='fabricated-question')f.h.question_item_id='a-new-human-answer-that-never-happened';
  if(kind==='unresolved-boundary')f.h.applied_boundary='unknown-message-or-possibly-active-turn';
  await assert.rejects(verifyDispatchHumanAuthority(await f.save()),/FRAMEWORK_DISPATCH_RETRY_/);
});
