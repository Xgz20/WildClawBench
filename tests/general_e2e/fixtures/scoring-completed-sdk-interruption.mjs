// Synthetic proof/transport only; no native app, provider, GT or Judge.
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {normalizeRolloutTranscript} from '../../../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout-transcript.mjs';
import {deriveRuntimeInterruption,RUNTIME_INTERRUPTION_STATE,RUNTIME_INTERRUPTION_NATIVE,RUNTIME_INTERRUPTION_PROOF}
 from '../../../tools/report/e2e-shared/general-resource-supplements/astronstudio-runtime-interruption.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex'),json=v=>JSON.stringify(v)+'\n';
const [recordFile,cwd]=process.argv.slice(2),execution=JSON.parse(await readFile(recordFile,'utf8'));
const prompt='frozen prompt',final='retained SDK final';
const session={thread_id:'thread',turn_id:'turn',session_id:'sdk',cwd,verified:true,native_status:'interrupted'};
const state={identity:execution.identity,phase:'FAILED',session,client:{version:'3.6.4'},
 prompt:{send_status:'sent',sha256:sha(prompt)},send:{dispatch_attempt_count:1},
 execution:{business_status:'cancelled',finished_at:'2026-11-05T12:00:30Z',error:{code:'ASTRONSTUDIO_TURN_INTERRUPTED',message:'native runtime interruption'}}};
const metadata={turn_id:'turn'};
const rows=[{type:'session_meta',payload:{id:'sdk',cwd}},
 {type:'event_msg',timestamp:'2026-11-05T12:00:01Z',payload:{type:'task_started',turn_id:'turn'}},
 {type:'turn_context',payload:{turn_id:'turn',cwd}},
 {type:'event_msg',payload:{type:'user_message',message:prompt}},
 {type:'response_item',payload:{type:'function_call',name:'bash',call_id:'call',arguments:'{"command":"true"}',internal_chat_message_metadata_passthrough:metadata}},
 {type:'response_item',payload:{type:'function_call_output',call_id:'call',output:'Exit code: 0\nOutput: synthetic\n',internal_chat_message_metadata_passthrough:metadata}},
 {type:'response_item',payload:{type:'message',id:'final',role:'assistant',content:[{type:'output_text',text:final}],internal_chat_message_metadata_passthrough:metadata}},
 {type:'event_msg',timestamp:'2026-11-05T12:00:21Z',payload:{type:'task_complete',turn_id:'turn',duration_ms:20000,last_agent_message:final}}];
const sdk=Buffer.from(rows.map(JSON.stringify).join('\n')+'\n'),provider=Buffer.alloc(0),stateBytes=Buffer.from(json(state));
const native={turn_state:'interrupted',termination_origin:'runtime',latest_turn_id:'turn',session_status:'interrupted',
 active_turn_id:null,pending_count:0,cwd,completed_at:'2026-11-05T12:00:25Z',runtime_status:'stopped',
 runtime_active_turn_id:null,runtime_resume_thread_id:'sdk',runtime_cwd:cwd,last_error:null,
 runtime_lifecycle_generation:'epoch',runtime_payload_lifecycle_generation:'epoch',
 last_runtime_event:'provider.stopRuntimeSession',last_runtime_event_at:'2026-11-05T12:00:27Z',runtime_observed_at:'2026-11-05T12:00:28Z',runtime_turn_event_count:0};
const normalized=normalizeRolloutTranscript(sdk,state,null,{sourcePolicy:'bound-native-sdk'});
const transcript=Buffer.from(normalized.events.map(JSON.stringify).join('\n')+'\n');
const ref=(path,b)=>({path,sha256:sha(b),size:b.length});
const index={schema_id:'urn:wildclawbench:schema:general-e2e:trace-index:v1',schema_version:1,identity:execution.identity,
 adapter:{id:'astronstudio-provider-runtime-events'},session,canonical_source_policy:{id:'bound-native-sdk-canonical/v1'},
 transcript:{...ref('transcript.jsonl',transcript),event_count:normalized.events.length},
 raw_trace:[ref('raw/astronstudio-rollout.jsonl',sdk),ref('raw/astronstudio-provider-events.jsonl',provider)],binding_evidence:[],
 completeness:{status:'partial',omitted_event_count:0,missing:['runtime-provider-turn-projection-unavailable','native-runtime-interruption-after-sdk-completion']}};
const proof=deriveRuntimeInterruption(stateBytes,index,sdk,provider,native);index.runtime_interruption_profile={id:proof.profile};
const files={'transcript.jsonl':transcript.toString(),'raw/astronstudio-rollout.jsonl':sdk.toString(),'raw/astronstudio-provider-events.jsonl':''};
for(const [path,b] of [[RUNTIME_INTERRUPTION_STATE,stateBytes],[RUNTIME_INTERRUPTION_NATIVE,Buffer.from(json(native))],[RUNTIME_INTERRUPTION_PROOF,Buffer.from(json(proof))]]){
 files[path]=b.toString();index.binding_evidence.push(ref(path,b));
}
execution.phase='FAILED';execution.harness={id:'astronstudio',version:'3.6.4'};execution.session=session;execution.prompt=state.prompt;
execution.execution=state.execution;execution.evidence={completeness:'partial',missing:index.completeness.missing,final_response_path:null};
console.log(JSON.stringify({execution,index,files,prompt,proof}));
