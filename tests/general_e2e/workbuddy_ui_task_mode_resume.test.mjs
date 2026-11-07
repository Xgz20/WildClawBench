import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir, hostname } from 'node:os';
import { join } from 'node:path';
import { assertAssistantHomepage, assertOriginalRefresh, isTaskModeReady, resumeWorkBuddyTaskMode }
  from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/resume-ui-task-mode.mjs';

const sha = b => createHash('sha256').update(b).digest('hex');
const bytes = x => JSON.stringify(x,null,2)+'\n';
const assistant = {app_error_boundary:false,workspace_picker_count:0,workspace_provider_count:0,workspace_path:null,
  selected_conversation_id:null,editor_count:1,editor_nonempty_count:0,busy_control_count:0,
  model_count:1,model:'快速',permission_count:1,permission:'default-sandbox'};
const taskUi = {...assistant,workspace_picker_count:1,workspace_provider_count:1,workspace_path:'',model:'xopglm52',permission:'full-access'};
const config = {expectedModel:'xopglm52',expectedPermission:'full-access'};
const markers = {assistant_home:true,new_task_count:1};

async function fixture() {
  const root=await realpath(await mkdtemp(join(tmpdir(),'wb-task-view-')));
  const audit=join(root,'.general-e2e/ui-recoveries/one');await mkdir(audit,{recursive:true});
  await mkdir(join(root,'.general-e2e/queues/workbuddy'),{recursive:true});
  const invocationPath=join(root,'invocation.json');await writeFile(invocationPath,bytes({argv:['node','original-batch','--queue-id','q']}));
  const owner={host:hostname(),pid:123456,queue_id:'q'};
  const queue={phase:'NEEDS_ATTENTION',last_owner:owner,tasks:[{phase:'FAILED',dispatch_attempt_count:0}]};
  const queuePath=join(root,'.general-e2e/queues/workbuddy/q.json');await writeFile(queuePath,bytes(queue));
  const native={idle:{verified:true},application:{path:'/Applications/WorkBuddy.app',version:'5.9.3'},
    process:{pid:17,started_at:'same',command_sha256:'same'},sessions:[{conversation_id:'old',cwd:'/old'}]};
  const original={schema_version:'wildclawbench.workbuddy-native-ui-recovery/v1',status:'NEEDS_ATTENTION',
    error:'WORKBUDDY_UI_RECOVERY_REFRESH_NOT_VERIFIED_DO_NOT_REPEAT',invocation_sha256:sha(await readFile(invocationPath)),
    refresh_attempt_count:1,refresh_returned:{clicked:true},prompt_send_count:0,before_ui:{app_error_boundary:true},
    first_native_idle:native,owner_source:'persisted-queue-owner',owner_queue_sha256:sha(await readFile(queuePath))};
  const originalPath=join(audit,'recovery.json');await writeFile(originalPath,bytes(original));
  let current={...assistant},nav=0,reads=0;
  const options={invocationPath,auditRoot:audit,expectedOwnerPid:owner.pid};
  const deps={resolveInvocation:async()=>({root,batch:{queueId:'q'},configs:[{...config,lockFile:join(root,'absent-lock')}] }),
    assertDead:async()=>{},inspectIdle:async()=>structuredClone(native),connect:async()=>({close(){}}),
    readUi:async()=>{reads++;return {...current};},readMarkers:async()=>markers,
    navigate:async()=>{nav++;current={...taskUi};},observationMs:0,sleep:async()=>{}};
  return {root,audit,options,deps,native,original,originalPath,queuePath,get nav(){return nav;},get reads(){return reads;},
    set current(x){current=x;},cleanup:()=>rm(root,{recursive:true,force:true})};
}

test('empty assistant homepage is distinguished from a wrong task model',()=>{
  assert.doesNotThrow(()=>assertAssistantHomepage(assistant,markers));
  assert.equal(isTaskModeReady(taskUi,config),true);
  for(const delta of [{workspace_picker_count:1},{editor_nonempty_count:1},{busy_control_count:1},{selected_conversation_id:'used'},
    {model:'other'},{permission:'full-access'},{app_error_boundary:true}])
    assert.throws(()=>assertAssistantHomepage({...assistant,...delta},markers));
  assert.throws(()=>assertAssistantHomepage(assistant,{...markers,new_task_count:2}));
});
test('read-only admission performs no navigation and creates no new receipt',async()=>{
  const f=await fixture();try{const r=await resumeWorkBuddyTaskMode({...f.options,verifyOnly:true},f.deps);
    assert.equal(r.status,'PASS_READ_ONLY_TASK_MODE_ADMISSION');assert.equal(f.nav,0);
    await assert.rejects(readFile(join(f.audit,'task-mode-resume.json')),/ENOENT/);
  }finally{await f.cleanup();}
});
test('one first-party new-task entry restores task configuration without changing old bytes',async()=>{
  const f=await fixture();try{const original=await readFile(f.originalPath),queue=await readFile(f.queuePath);
    const r=await resumeWorkBuddyTaskMode(f.options,f.deps);assert.equal(r.status,'PASS_UI_RECOVERED_WITHOUT_PROMPT');assert.equal(f.nav,1);
    assert.deepEqual(await readFile(f.originalPath),original);assert.deepEqual(await readFile(f.queuePath),queue);
    const proof=JSON.parse(await readFile(r.receipt));assert.equal(proof.refresh_attempt_count,1);assert.equal(proof.prompt_send_count,0);
    assert.equal(proof.model_selection_actions,0);assert.equal(proof.permission_changes,0);
    const saved=await readFile(r.receipt);const again=await resumeWorkBuddyTaskMode(f.options,f.deps);
    assert.equal(again.idempotent,true);assert.equal(f.nav,1);assert.deepEqual(await readFile(r.receipt),saved);
  }finally{await f.cleanup();}
});
test('original refresh must have a confirmed single click and exact invocation',async()=>{
  const f=await fixture();try{for(const delta of [{refresh_attempt_count:2},{refresh_returned:null},{prompt_send_count:1},{status:'PREFLIGHT'},
    {before_ui:{app_error_boundary:false}},{invocation_sha256:'different'}])
    assert.throws(()=>assertOriginalRefresh({...f.original,...delta},f.original.invocation_sha256));
  }finally{await f.cleanup();}
});
test('owner still alive rejects before browser connection',async()=>{
  const f=await fixture();try{let connections=0;f.deps.assertDead=async()=>{throw Error('owner alive');};f.deps.connect=async()=>{connections++;};
    await assert.rejects(resumeWorkBuddyTaskMode(f.options,f.deps),/owner alive/);assert.equal(connections,0);assert.equal(f.nav,0);
  }finally{await f.cleanup();}
});
test('changed native session set rejects without navigation',async()=>{
  const f=await fixture();try{f.deps.inspectIdle=async()=>({...f.native,sessions:[...f.native.sessions,{conversation_id:'foreign',cwd:'/foreign'}]});
    await assert.rejects(resumeWorkBuddyTaskMode(f.options,f.deps),/NATIVE_IDENTITY_OR_SESSION_DRIFT/);assert.equal(f.nav,0);
  }finally{await f.cleanup();}
});
test('new activity between readback and navigation rejects',async()=>{
  const f=await fixture();try{let n=0;f.deps.inspectIdle=async()=>{n++;return {...f.native,idle:{verified:n===1}};};
    await assert.rejects(resumeWorkBuddyTaskMode(f.options,f.deps),/PRE_NAVIGATION_NATIVE_DRIFT/);assert.equal(f.nav,0);
  }finally{await f.cleanup();}
});
test('task-view model drift is rejected rather than switching a selector',async()=>{
  const f=await fixture();try{f.current={...taskUi,model:'different'};
    await assert.rejects(resumeWorkBuddyTaskMode(f.options,f.deps),/NOT_REGISTERED_EMPTY_ASSISTANT_HOME/);assert.equal(f.nav,0);
  }finally{await f.cleanup();}
});
test('an armed navigation is observed on resume and never repeated',async()=>{
  const f=await fixture();try{f.deps.navigate=async()=>{};
    await assert.rejects(resumeWorkBuddyTaskMode(f.options,f.deps),/TASK_VIEW_NOT_VERIFIED/);
    const p=join(f.audit,'task-mode-resume.json');assert.equal(JSON.parse(await readFile(p)).new_task_navigation_count,1);
    let repeated=0;f.deps.navigate=async()=>{repeated++;};
    await assert.rejects(resumeWorkBuddyTaskMode(f.options,f.deps),/TASK_VIEW_NOT_VERIFIED/);assert.equal(repeated,0);
    f.current={...taskUi};const r=await resumeWorkBuddyTaskMode(f.options,f.deps);assert.equal(r.status,'PASS_UI_RECOVERED_WITHOUT_PROMPT');assert.equal(repeated,0);
  }finally{await f.cleanup();}
});
