import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,access,realpath} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {prepareNativeProjects} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/prepare_astronstudio_native_projects.mjs';

async function fixture(){
  const root=await realpath(await mkdtemp(join(tmpdir(),'native-project-prep-')));const tasks=['first','second'];
  for(const id of tasks)await mkdir(join(root,'execution/tasks',id,'workspace'),{recursive:true});
  const manifest={batch_id:'batch',unit_id:'unit',task_ids:tasks,tasks:tasks.map(task_id=>({task_id,workspace:{path:'execution/tasks/'+task_id+'/workspace'}}))};
  const bytes=Buffer.from(JSON.stringify(manifest));await writeFile(join(root,'manifest.json'),bytes);const q=join(root,'.general-e2e/queues/queue');await mkdir(q,{recursive:true});
  await writeFile(join(q,'queue-state.json'),JSON.stringify({configuration:{manifest_sha256:createHash('sha256').update(bytes).digest('hex'),task_ids:tasks,run_config_digest:'digest'}}));
  const config={runConfig:{config_digest:'digest',harness:{client_version:'3.6.0'},tested_model:{}},stateDatabase:'fixture',appPath:'fixture',endpoint:'fixture',expectedModel:'Spark-X2.6',expectedReasoning:'High',expectedPermission:'完全访问'};
  const registered=new Map([[join(root,'execution/tasks/first/workspace'),{project_id:'existing',workspace_root:join(root,'execution/tasks/first/workspace')}]]),calls=[];
  const probe={ready:true,frozen_run_config:{harness:{client_version:'3.6.0'},tested_model:{display_name:'Spark-X2.6',reasoning_display:'High',permission_display:'完全访问'}}};
  const deps={resolveExecutionConfig:async()=>config,queryNativeSessions:async()=>[],probeAstronStudio:async()=>probe,
    discoverMainTarget:async()=>({webSocketDebuggerUrl:'fixture'}),connect:async()=>({close:()=>calls.push('close')}),
    queryExactProjectsForWorkspace:async(_db,w)=>registered.has(w)?[registered.get(w)]:[],
    addWorkspace:async(_c,w)=>{calls.push(w);registered.set(w,{project_id:'created',workspace_root:w});},waitForExactProjectIdentity:async()=>{},};
  return{root,q,config,probe,registered,calls,deps,options:{unitRoot:root,runConfig:'fixture',queueId:'queue',output:join(root,'audit.json'),timeoutMs:1000}};
}

test('native project preparation preserves full frozen order and never calls task/composer/send',async()=>{
  const f=await fixture();try{const a=await prepareNativeProjects(f.options,f.deps);assert.equal(a.status,'PASS');assert.deepEqual(a.projects.map(p=>p.task_id),['first','second']);
    assert.deepEqual(a.projects.map(p=>p.created),[false,true]);assert.equal(a.prompt_send_calls,0);assert.equal(a.new_task_calls,0);assert.equal(a.page_reload_calls,0);
    assert.equal(f.calls.filter(x=>x!=='close').length,1);await assert.rejects(access(join(f.root,'.general-e2e/astronstudio-ui.lock')));
  }finally{await rm(f.root,{recursive:true,force:true});}
});

for(const kind of ['active','drift','ambiguous','owner'])test('native project prep fails closed for '+kind,async()=>{
  const f=await fixture();try{
    if(kind==='active')f.deps.queryNativeSessions=async()=>[{status:'running',active_turn_id:'native'}];
    if(kind==='drift')f.probe.frozen_run_config.tested_model.display_name='other';
    if(kind==='ambiguous')f.deps.queryExactProjectsForWorkspace=async()=>[{project_id:'a'},{project_id:'b'}];
    if(kind==='owner')await writeFile(join(f.q,'worker.lock'),JSON.stringify({pid:process.pid}));
    await assert.rejects(prepareNativeProjects(f.options,f.deps),/NATIVE_PROJECT_PREPARATION_/);assert.equal(f.calls.some(x=>x.includes('/workspace')),false);
    if(kind==='owner')await access(join(f.q,'worker.lock'));
  }finally{await rm(f.root,{recursive:true,force:true});}
});
