import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp,mkdir,writeFile,readFile,readdir,access,rm,realpath } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { identifyOwnedDraft,prepareZeroSendUi } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/prepare_astronstudio_zero_send_ui.mjs';
import { preSendInfrastructureFailure } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/run_astronstudio_macos_batch.mjs';

const state=()=>({identity:{task_id:'task'},phase:'FAILED',execution:{business_status:'infrastructure_error',error:{code:'PRE_SEND_DRIVER_ERROR'}},prompt:{send_status:'not_sent',sent_at:null},send:{dispatch_attempt_count:0,dispatch_armed_at:null,dispatch_completed_at:null},session:{verified:false},history:[]});
const ui=()=>({count:1,dialogs:[],text:'exact frozen prompt',chips:[],workspace:['/tmp/owned']});
const candidate=()=>({task_id:'task',prompt:'exact frozen prompt',workspace:'/tmp/owned',state:state()});
test('only an exact zero-send draft in its own workspace can be selected',()=>{
  const c=candidate();assert.equal(identifyOwnedDraft(ui(),[c]),c);
  assert.equal(identifyOwnedDraft({...ui(),text:''},[c]),null);
});
test('unknown, duplicated or foreign drafts are preserved',()=>{
  assert.throws(()=>identifyOwnedDraft({...ui(),text:'foreign draft'},[candidate()]),/NOT_UNIQUE/);
  assert.throws(()=>identifyOwnedDraft(ui(),[candidate(),candidate()]),/NOT_UNIQUE/);
  assert.throws(()=>identifyOwnedDraft({...ui(),workspace:['/tmp/foreign']},[candidate()]),/WORKSPACE/);
  assert.throws(()=>identifyOwnedDraft({...ui(),dialogs:['dialog']},[candidate()]),/BLOCKED/);
});
test('armed, accepted or uncertain attempts can never authorize draft clearing',()=>{
  for(const edit of [s=>s.send.dispatch_attempt_count=1,s=>s.send.dispatch_armed_at='now',s=>s.prompt.send_status='uncertain',s=>s.session.verified=true,s=>s.session.thread_id='accepted',s=>s.history.push({event:'PROMPT_DISPATCH_ARMED'})]){
    const c=candidate();edit(c.state);assert.throws(()=>identifyOwnedDraft(ui(),[c]),/NOT_ZERO_SEND/);
  }
});
test('preparation failures block refilling separately from candidate failures',()=>{
  assert.equal(preSendInfrastructureFailure({phase:'FAILED',dispatch_attempt_count:0,error:{code:'PRE_SEND_DRIVER_ERROR'}}),true);
  assert.equal(preSendInfrastructureFailure({phase:'FAILED',dispatch_attempt_count:1,error:{code:'PRE_SEND_DRIVER_ERROR'}}),false);
  assert.equal(preSendInfrastructureFailure({phase:'FAILED',dispatch_attempt_count:0,error:{code:'CANDIDATE_ERROR'}}),false);
});

for(const foreign of [false,true]) test(foreign?'foreign draft never gets a key event and is not exported':'owned draft clearing preserves state and only emits Backspace',async()=>{
  const root=await realpath(await mkdtemp(join(tmpdir(),'bound-zero-send-')));
  try{
    const prompt='exact frozen prompt',workspace=join(root,'workspace'),control=join(root,'.general-e2e/execution/task');
    await mkdir(workspace);await mkdir(control,{recursive:true});await writeFile(join(root,'PROMPT.md'),prompt);
    await writeFile(join(root,'manifest.json'),JSON.stringify({batch_id:'batch',unit_id:'unit',tasks:[{task_id:'task',prompt:{path:'PROMPT.md',sha256:createHash('sha256').update(prompt).digest('hex')},workspace:{path:'workspace'}}]}));
    const source=state();source.identity={batch_id:'batch',unit_id:'unit',task_id:'task',attempt_id:'original'};
    const statePath=join(control,'automation-state.json');await writeFile(statePath,JSON.stringify(source));const before=await readFile(statePath);
    const audit=join(root,'audit'),keys=[];let reads=0,closed=false;
    const client={evaluate:async()=>++reads===1?{...ui(),route:'#/thread',workspace:[workspace],text:foreign?'foreign private draft':prompt}:reads===2?true:{route:'#/thread',text:'',chips:0},send:async(_name,value)=>keys.push(value.key),close:()=>closed=true};
    const options={unitRoot:root,stateDatabase:'synthetic',endpoint:'synthetic',auditDir:audit};
    const deps={queryNativeSessions:async()=>[],queryPristineThread:async()=>true,queryProjectForThread:async()=>[{project_id:'project',workspace_root:workspace}],discoverMainTarget:async()=>({webSocketDebuggerUrl:'synthetic'}),connect:async()=>client,createFreshTask:async()=>({thread_id:'fresh'})};
    if(foreign){await assert.rejects(prepareZeroSendUi(options,deps),/NOT_UNIQUE/);assert.deepEqual(keys,[]);for(const f of await readdir(audit))assert.ok(!(await readFile(join(audit,f),'utf8')).includes('foreign private draft'));}
    else{const proof=await prepareZeroSendUi(options,deps);assert.equal(proof.status,'PASS');assert.equal(proof.formal_send_calls,0);assert.deepEqual(keys,['Backspace','Backspace']);assert.equal((await readdir(audit)).length,2);}
    assert.deepEqual(await readFile(statePath),before);assert.equal(closed,true);await assert.rejects(access(join(root,'.general-e2e/astronstudio-ui.lock')));
  }finally{await rm(root,{recursive:true,force:true});}
});
