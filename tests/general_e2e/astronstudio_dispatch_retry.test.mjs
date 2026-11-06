import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {assertUnacceptedDispatch,hash,archiveDispatchAttempt} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-dispatch-retry.mjs';
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
  await assert.rejects(archiveDispatchAttempt(f.unit,f.authPath),/WORKSPACE_SHA|WORKSPACE_DRIFT/);
});
