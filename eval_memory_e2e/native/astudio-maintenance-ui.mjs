/* Create one fresh native UI session in an existing diagnostic unit. No send. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {discoverMainTarget,prepareExecutionUi,readUiConfiguration} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';
import {WorkBuddyCdpClient} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
import {memoryPython} from './machine.mjs';
const root=path.resolve(process.argv[2]),plan=JSON.parse(fs.readFileSync(root+'/diagnostic-plan.json'));
const boundary=JSON.parse(fs.readFileSync(root+'/frozen-boundary.json'));
const view=JSON.parse(fs.readFileSync(plan.scope));
const check=(ok,reason)=>{if(!ok)throw Error(reason)};
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const publish=(name,value)=>fs.writeFileSync(root+'/'+name,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});
check(plan.contract==='astudio-automatic-formation-diagnostic/v1'&&view.contract==='astudio-memory-unit-continuation/v1'
  &&view.diagnostic_only===true&&plan.unit_id===view.unit_id&&!fs.existsSync(root+'/ui-preparation-intent.json'),
  'ASTUDIO_MAINTENANCE_ALREADY_INVOKED_OR_WRONG_UNIT');
const python=memoryPython(),helper=path.resolve('eval_memory_e2e/astudio_scope.py');
const proof=JSON.parse(execFileSync(python,[helper,'attest','--scope',plan.scope,'--boundary-json',JSON.stringify(boundary)],{encoding:'utf8',timeout:30000}));
const owner=execFileSync('/usr/sbin/lsof',['-nP','-iTCP:9240','-sTCP:LISTEN','-t'],{encoding:'utf8'}).trim();
check(proof.status==='PASS'&&owner===String(proof.launch_identity.pid),'ASTUDIO_MAINTENANCE_OS_OWNER');
const controllerTmp=root+'/control/ui-tmp';fs.mkdirSync(controllerTmp,{recursive:true,mode:0o700});process.env.TMPDIR=controllerTmp;
const workspace=view.paths.runtime+'/maintenance-workspace-'+plan.experiment_id.slice(0,8);
if(fs.existsSync(workspace))check(fs.realpathSync(workspace)===workspace&&fs.readdirSync(workspace).length===0,'ASTUDIO_MAINTENANCE_WORKSPACE_NOT_EMPTY');
else fs.mkdirSync(workspace,{mode:0o700});
const target=await discoverMainTarget('http://127.0.0.1:9240',30000);
const client=await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl,30000);
try{
  const ui=await readUiConfiguration(client);
  check(ui.model==='GLM-5.2'&&ui.reasoning==='High'&&ui.permission==='完全访问','ASTUDIO_MAINTENANCE_FROZEN_UI');
  publish('ui-preparation-intent.json',{at:new Date().toISOString(),operation_id:crypto.randomUUID(),scope_sha256:hash(fs.readFileSync(plan.scope)),
    main_pid:proof.launch_identity.pid,workspace,ui_prompts_sent:0,boundary_proof:proof});
  try{
    const result=await prepareExecutionUi(client,{stateDatabase:view.paths.astudio_db,candidateWorkspace:workspace,timeoutMs:30000,
      expectedModel:'GLM-5.2',expectedReasoning:'High',expectedPermission:'完全访问'});
    publish('ui-preparation-completed.json',{at:new Date().toISOString(),workspace,result,ui_prompts_sent:0});
    console.log(JSON.stringify({status:'PREPARED',thread_id:result.workspace.thread_id,workspace,ui_prompts_sent:0}));
  }catch(error){publish('ui-preparation-failed.json',{at:new Date().toISOString(),reason:String(error.stack||error),ui_prompts_sent:0});throw error}
}finally{client.close()}
