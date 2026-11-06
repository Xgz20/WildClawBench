import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath} from 'node:fs/promises';
import {join} from 'node:path';
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
