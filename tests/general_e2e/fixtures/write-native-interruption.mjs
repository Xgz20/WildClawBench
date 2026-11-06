// Closed synthetic native interruption; no real app, process cleanup or model.
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { deriveRuntimeInterruption, RUNTIME_INTERRUPTION_STATE, RUNTIME_INTERRUPTION_NATIVE, RUNTIME_INTERRUPTION_PROOF }
  from '../../../tools/report/e2e-shared/general-resource-supplements/astronstudio-runtime-interruption.mjs';
import { finalizeAstronStudioExecution } from '../../../tools/report/skills/general-e2e/collect-general-e2e/scripts/finalize_astronstudio_execution.mjs';
const root=process.argv[2],missing=process.argv[3]==='--missing-provider',watchdog=process.argv[3]==='--watchdog';
const hash=b=>createHash('sha256').update(b).digest('hex'),json=v=>Buffer.from(JSON.stringify(v)+'\n');
const id={batch_id:'fixture-batch',unit_id:'astronstudio-macos',task_id:'interrupted-task',attempt_id:'original'};
const task=join(root,'execution/tasks',id.task_id),workspace=join(task,'workspace'),trace=join(root,'source-trace');
await mkdir(workspace,{recursive:true});await mkdir(join(trace,'raw'),{recursive:true});await mkdir(join(trace,'bindings'));await mkdir(join(root,'receipts'));
const prompt=Buffer.from('Do the synthetic task.\n');await writeFile(join(task,'PROMPT.md'),prompt);await writeFile(join(workspace,'answer.txt'),'partial candidate\n');
const state={schema_version:'wildclawbench.general-e2e-astronstudio-execution-state/v1',identity:id,dataset:{id:'fixture-dataset',digest:'1'.repeat(64)},phase:'FAILED',task_root:task,candidate_workspace:workspace,
  prompt:{path:join(task,'PROMPT.md'),sha256:hash(prompt),send_status:'sent',sent_at:'2026-09-18T00:00:01Z'},send:{dispatch_attempt_count:1},
  session:{thread_id:'native-thread',turn_id:'native-turn',session_id:'native-session',cwd:workspace,verified:true,native_status:'interrupted'},
  client:{version:'3.6.0',model:'Spark-X2.6',reasoning:'High'},execution:{business_status:'cancelled',started_at:'2026-09-18T00:00:01Z',finished_at:'2026-09-18T00:00:10Z',duration_seconds:9,agent_duration_seconds:null,error:{code:'ASTRONSTUDIO_TURN_INTERRUPTED',message:'interrupted'}},evidence:{},human_assistance:{mode:'automatic',operation_count:0,semantic_intervention_count:0}};
const watchdogMessage='最后失败工具 Ran command，失败原因：command not found；308 秒无进展。任务已失败。';
if(watchdog){state.execution.business_status='candidate_error';state.execution.error={code:'ASTRONSTUDIO_TURN_ERROR',message:watchdogMessage};state.session.native_status='running';}
const stateBytes=json(state),session=state.session;
const sdk=Buffer.from([{type:'session_meta',payload:{id:session.session_id,cwd:workspace}},{type:'event_msg',payload:{type:'task_started',turn_id:session.turn_id}},
  {type:'event_msg',payload:{type:'user_message',message:prompt.toString()}},{type:'event_msg',timestamp:'2026-09-18T00:00:08.000Z',payload:{type:'turn_aborted',turn_id:session.turn_id,reason:'interrupted',completed_at:1789689608,duration_ms:7000}}].map(JSON.stringify).join('\n')+'\n');
const provider=missing?Buffer.alloc(0):json({sequence:1,event_type:'turn.completed',thread_id:session.thread_id,turn_id:session.turn_id,event:{threadId:session.thread_id,turnId:session.turn_id,
  providerRefs:{providerThreadId:session.session_id,providerTurnId:session.turn_id},payload:{state:watchdog?'failed':'interrupted',...(watchdog?{errorMessage:watchdogMessage}:{})},raw:{payload:{threadId:session.session_id,turn:{id:session.turn_id,status:'interrupted',error:null,completedAt:1789689608,durationMs:7000}}}}});
const transcript=Buffer.from('{"event":"fixture"}\n'),ref=(path,b)=>({path,sha256:hash(b),size:b.length});
const index={schema_id:'urn:wildclawbench:schema:general-e2e:trace-index:v1',schema_version:1,identity:id,session:{thread_id:session.thread_id,turn_id:session.turn_id,session_id:session.session_id,cwd:workspace},
  transcript:ref('transcript.jsonl',transcript),raw_trace:[ref('raw/astronstudio-provider-events.jsonl',provider),ref('raw/astronstudio-rollout.jsonl',sdk)],binding_evidence:[],canonical_source_policy:{id:'bound-native-sdk-canonical/v1'},completeness:{status:'partial',omitted_event_count:0,missing:['native-runtime-interruption']}};
const native={turn_state:'interrupted',termination_origin:'runtime',latest_turn_id:session.turn_id,session_status:'interrupted',active_turn_id:null,pending_count:0,cwd:workspace,completed_at:'2026-09-18T00:00:09Z',...(missing?{runtime_turn_event_count:0}:{})};
if(watchdog)Object.assign(native,{turn_state:'error',session_status:'error',runtime_status:'stopped',last_runtime_event:'turn.completed',last_runtime_event_at:native.completed_at,last_error:watchdogMessage});
const proof=deriveRuntimeInterruption(stateBytes,index,sdk,provider,native);index.runtime_interruption_profile={id:proof.profile};
for(const[path,b]of[[RUNTIME_INTERRUPTION_STATE,stateBytes],[RUNTIME_INTERRUPTION_NATIVE,json(native)],[RUNTIME_INTERRUPTION_PROOF,json(proof)]]){await writeFile(join(trace,path),b);index.binding_evidence.push(ref(path,b));}
await writeFile(join(trace,'transcript.jsonl'),transcript);await writeFile(join(trace,'raw/astronstudio-provider-events.jsonl'),provider);await writeFile(join(trace,'raw/astronstudio-rollout.jsonl'),sdk);await writeFile(join(trace,'trace-index.json'),json(index));await writeFile(join(root,'state.json'),stateBytes);
await writeFile(join(root,'manifest.json'),json({schema_id:'urn:wildclawbench:schema:general-e2e:package-manifest:v1',manifest_kind:'execution',batch_id:id.batch_id,unit_id:id.unit_id,dataset:state.dataset,task_ids:[id.task_id],
  tasks:[{task_id:id.task_id,prompt:{path:'execution/tasks/'+id.task_id+'/PROMPT.md',sent_sha256:hash(prompt)},workspace:{path:'execution/tasks/'+id.task_id+'/workspace'}}],unit:{harness:{id:'astronstudio',platform:'macos',version:'3.6.0'},model:{requested_id:'Spark-X2.6',reasoning_effort:'high'}}}));
const cleanup={schema_version:'wildclawbench.general-e2e-task-process-cleanup/v1',supported:true,platform:'darwin',success:true,quiet_window_milliseconds:0,quiet_observed_milliseconds:0,late_process_detected:false,before:{supported:true,targets:[],seed_pids:[],root_pids:[]},termination_attempts:[],after:{supported:true,targets:[],seed_pids:[],root_pids:[]}};
await finalizeAstronStudioExecution({unitRoot:root,stateFile:join(root,'state.json'),traceIndex:join(trace,'trace-index.json'),resourceMetrics:'',candidatePolicy:'',stabilityMilliseconds:0,processQuietMilliseconds:0,processWaitMilliseconds:0},{terminateProcesses:async()=>cleanup});
console.log(JSON.stringify({unit:root,record:join(root,'evidence/tasks',id.task_id,id.attempt_id,'execution-record.json')}));
