const finalizeAstronStudioExecution=(options,overrides={})=>finalizeWithLiveGuard(options,{runtimeSafetyGuard:async()=>({fixture:true,blockers:[]}),...overrides});
// Synthetic integration fixture only: no UI, native app, model or scoring calls.
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { rejectionFixture } from './native-start-rejection.mjs';
import { executeSingleTask } from '../../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';
import { finalizeAstronStudioExecution as finalizeWithLiveGuard } from '../../../tools/report/skills/general-e2e/collect-general-e2e/scripts/finalize_astronstudio_execution.mjs';

const root=process.argv[2],taskRoot=join(root,'execution/tasks/task');
const f=rejectionFixture(join(taskRoot,'workspace'));
if (process.argv[3] === '--idle-prewarm') {
  const runtime=f.data.provider_session_runtime[0];runtime.status='running';
  runtime.resume_cursor_json='{"emptyPrewarm":true,"threadId":"prewarm-session"}';
  runtime.runtime_payload_json=JSON.stringify({cwd:f.config.candidateWorkspace,activeTurnId:null,lastError:null,emptyPrewarmDispatch:null,lastRuntimeEvent:'session.state.changed'});
}
Object.assign(f.state,{schema_version:'wildclawbench.general-e2e-astronstudio-execution-state/v1',task_root:taskRoot});
f.state.prompt.path=join(taskRoot,'PROMPT.md');
await mkdir(f.config.candidateWorkspace,{recursive:true});await mkdir(join(root,'receipts'));
await writeFile(f.state.prompt.path,'Create the requested deliverables.');
Object.assign(f.config,{unitRoot:root,controlRoot:join(root,'control'),stateFile:join(root,'control/state.json'),recordFile:join(root,'control/record.json'),
  task:{task_id:'task'},manifest:{schema_id:'urn:wildclawbench:schema:general-e2e:package-manifest:v1',schema_version:1,manifest_kind:'execution',batch_id:'batch',unit_id:'astronstudio-macos',dataset:f.state.dataset,
    task_ids:['task'],tasks:[{task_id:'task',prompt:{path:'execution/tasks/task/PROMPT.md',sent_sha256:f.state.prompt.sha256},workspace:{path:'execution/tasks/task/workspace'}}],
    unit:{harness:{id:'astronstudio',platform:'macos'},model:{requested_id:'Spark-X2.6',reasoning_effort:'high'}}},
  resume:true,observeOnce:true,resolveNativeStartRejection:true,timeoutMs:1000,endpoint:'http://localhost:9240'});
Object.assign(f.config.runConfig,{config_digest:'config',harness:{client_version:'3.6.0'},control:{endpoint:f.config.endpoint},tested_model:{display_name:'Spark-X2.6',reasoning_display:'High',permission_display:'完全访问'}});
await mkdir(f.config.controlRoot);await writeFile(f.config.stateFile,JSON.stringify(f.state));
await writeFile(f.config.recordFile,JSON.stringify({identity:f.state.identity,prompt:f.state.prompt}));
await executeSingleTask(f.config,{probeAstronStudio:async()=>({ready:true,failed_checks:[],app:{version:'3.6.0'},cdp:{endpoint:f.config.endpoint},frozen_run_config:f.config.runConfig,state_database:{active_or_pending_session_count:0}}),queryNativeStartRejection:async()=>f.data,now:()=> '2026-11-06T07:00:00.000Z',clickSend:()=>{throw Error('no send');}});
await writeFile(join(root,'manifest.json'),JSON.stringify(f.config.manifest));
const cleanup={schema_version:'wildclawbench.general-e2e-task-process-cleanup/v1',supported:true,platform:'darwin',success:true,quiet_window_milliseconds:0,quiet_observed_milliseconds:0,late_process_detected:false,before:{supported:true,targets:[],seed_pids:[],root_pids:[]},termination_attempts:[],after:{supported:true,targets:[],seed_pids:[],root_pids:[]}};
await finalizeAstronStudioExecution({unitRoot:root,stateFile:f.config.stateFile,traceIndex:'',resourceMetrics:'',candidatePolicy:'',stabilityMilliseconds:0,processQuietMilliseconds:0,processWaitMilliseconds:0},{terminateProcesses:async()=>cleanup});
console.log(JSON.stringify({unit:root,record:join(root,'evidence/tasks/task/original/execution-record.json')}));
