#!/usr/bin/env node
// Native project registration only. No task/thread/composer/send operation.
import {createHash,randomUUID} from 'node:crypto';
import {readFile,writeFile,open,realpath,mkdir,rename,rm} from 'node:fs/promises';
import {join,dirname,resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {resolveExecutionConfig,parseArgs as executionArgs,isBlockingActiveSession} from './execute_astronstudio_macos.mjs';
import {queryNativeSessions,queryExactProjectsForWorkspace} from './lib/astronstudio-state.mjs';
import {CdpClient,discoverMainTarget,addWorkspace,waitForExactProjectIdentity,resetOwnedProjectPathForm} from './lib/astronstudio-cdp.mjs';
import {probeAstronStudio} from './probe_astronstudio_macos.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
const require=(value,code)=>{if(!value)throw Error('NATIVE_PROJECT_PREPARATION_'+code);};
const json=async p=>JSON.parse(await readFile(p));

export function parseProjectPreparationArgs(args){
  const result={unitRoot:'',runConfig:'',queueId:'',output:'',timeoutMs:30000};
  const keys={'--unit-root':'unitRoot','--run-config':'runConfig','--queue-id':'queueId','--output':'output','--timeout-ms':'timeoutMs'};
  for(let i=0;i<args.length;i++){if(args[i]==='--help')return {help:true};const key=keys[args[i]];require(key&&args[i+1]&&!args[i+1].startsWith('--'),'ARGUMENT');result[key]=key==='timeoutMs'?Number(args[++i]):args[++i];}
  require(result.unitRoot&&result.runConfig&&/^[A-Za-z0-9._-]+$/.test(result.queueId)&&result.output,'ARGUMENT');
  require(Number.isInteger(result.timeoutMs)&&result.timeoutMs>0&&result.timeoutMs<=180000,'TIMEOUT');return result;
}

export async function prepareNativeProjects(options,overrides={}){
  const deps={resolveExecutionConfig,queryNativeSessions,queryExactProjectsForWorkspace,probeAstronStudio,discoverMainTarget,
    connect:(url,timeout)=>CdpClient.connect(url,timeout),addWorkspace,waitForExactProjectIdentity,resetOwnedProjectPathForm,...overrides};
  const unit=await realpath(resolve(options.unitRoot)),manifestPath=join(unit,'manifest.json'),manifestBytes=await readFile(manifestPath),manifest=JSON.parse(manifestBytes);
  const queue=await json(join(unit,'.general-e2e/queues',options.queueId,'queue-state.json'));
  const queueLock=await json(join(unit,'.general-e2e/queues',options.queueId,'worker.lock')).catch(error=>{if(error.code==='ENOENT')return null;throw error;});
  if(queueLock){let alive=true;try{process.kill(Number(queueLock.pid),0);}catch(error){if(error.code==='ESRCH')alive=false;else throw error;}require(!alive,'QUEUE_OWNER_ACTIVE');}
  require(queue.configuration?.manifest_sha256===hash(manifestBytes)
    &&JSON.stringify(queue.configuration.task_ids)===JSON.stringify(manifest.task_ids),'FROZEN_SCOPE');
  const config=await deps.resolveExecutionConfig(executionArgs(['--unit-root',unit,'--task-id',manifest.task_ids[0],'--run-config',options.runConfig]));
  require(queue.configuration.run_config_digest===config.runConfig.config_digest,'FROZEN_CONFIG');
  const output=resolve(options.output);await mkdir(dirname(output),{recursive:true});
  try{await open(output,'wx').then(h=>h.close());}catch{throw Error('NATIVE_PROJECT_PREPARATION_OUTPUT_EXISTS');}
  const audit={schema_version:'wildclawbench.astronstudio-native-project-preparation/v1',status:'RUNNING',queue_id:options.queueId,
    identity:{batch_id:manifest.batch_id,unit_id:manifest.unit_id},manifest_sha256:hash(manifestBytes),run_config_digest:config.runConfig.config_digest,
    ordered_task_ids:manifest.task_ids,projects:[],prompt_send_calls:0,new_task_calls:0,app_restart_calls:0,page_reload_calls:0};
  const save=async()=>{audit.updated_at=new Date().toISOString();const tmp=output+'.tmp-'+process.pid;await writeFile(tmp,JSON.stringify(audit,null,2)+'\n');await rename(tmp,output);};
  const idle=async()=>{const rows=await deps.queryNativeSessions(config.stateDatabase);require(!rows.some(isBlockingActiveSession),'NATIVE_NOT_IDLE');};
  const verify=async()=>{await idle();const p=await deps.probeAstronStudio({appPath:config.appPath,stateDb:config.stateDatabase,endpoint:config.endpoint,endpointExplicit:true,output:null,configOutput:null,timeoutMs:10000},{databaseValidationScope:'runtime'});
    require(p.ready,'PROBE');const c=p.frozen_run_config;require(c.harness.client_version===config.runConfig.harness.client_version
      &&c.tested_model.display_name===config.expectedModel&&c.tested_model.reasoning_display===config.expectedReasoning
      &&c.tested_model.permission_display===config.expectedPermission
      &&JSON.stringify(c.tested_model.custom_mapping||null)===JSON.stringify(config.runConfig.tested_model.custom_mapping||null),'MODEL_DRIFT');};
  let lock,client;const lockPath=join(unit,'.general-e2e/astronstudio-ui.lock'),token=randomUUID();
  try{
    await verify();lock=await open(lockPath,'wx',0o600);await lock.writeFile(JSON.stringify({pid:process.pid,token,kind:'native-project-preparation',started_at:new Date().toISOString()})+'\n');
    await save();const target=await deps.discoverMainTarget(config.endpoint,options.timeoutMs);client=await deps.connect(target.webSocketDebuggerUrl,options.timeoutMs);
    for(const id of manifest.task_ids){
      await idle();const task=manifest.tasks.find(t=>t.task_id===id);require(task,'TASK');const workspace=await realpath(join(unit,task.workspace.path));
      const rel=relative(join(unit,'execution/tasks',id),workspace);require(rel&&!isAbsolute(rel)&&!rel.startsWith('..'),'WORKSPACE');
      let rows=await deps.queryExactProjectsForWorkspace(config.stateDatabase,workspace);require(rows.length<=1,'PROJECT_AMBIGUOUS');let created=false;
      if(!rows.length){await deps.addWorkspace(client,workspace,options.timeoutMs);await deps.waitForExactProjectIdentity(config.stateDatabase,workspace,options.timeoutMs);rows=await deps.queryExactProjectsForWorkspace(config.stateDatabase,workspace);created=true;}
      require(rows.length===1&&rows[0].workspace_root===workspace,'PROJECT_BINDING');
      audit.projects.push({task_id:id,workspace,project_id:rows[0].project_id,created});await save();
      // A native mutation can persist the project but leave its own error
      // form mounted. Clear only this just-certified full path, not the next
      // task's path or any unknown draft, before continuing the frozen order.
      if(created)await deps.resetOwnedProjectPathForm(client,workspace);
    }
    await verify();audit.status='PASS';await save();return audit;
  }catch(error){audit.status='NEEDS_ATTENTION';audit.error=String(error.message||error);await save();throw error;}
  finally{if(client)client.close();if(lock){await lock.close();const owner=await json(lockPath).catch(()=>null);if(owner?.token===token)await rm(lockPath);}}
}

const invoked=process.argv[1]?resolve(process.argv[1]):null;
if(invoked===fileURLToPath(import.meta.url)){
  try{const o=parseProjectPreparationArgs(process.argv.slice(2));if(o.help)console.log('prepare native projects only: --unit-root ABS --run-config ABS --queue-id ID --output NEW_JSON; requires real native idle; sends no Prompt and creates no task');
    else console.log(JSON.stringify(await prepareNativeProjects(o)));}
  catch(e){console.error(e.message);process.exitCode=2;}
}
