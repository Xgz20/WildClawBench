import {createHash} from 'node:crypto';
import {readFile,writeFile,mkdir,mkdtemp,rename,rm} from 'node:fs/promises';
import {join,dirname,relative} from 'node:path';
import {captureQwenEngineEvidence,verifyQwenEngineEvidence,QWEN_ENGINE_PROFILE} from '../../vendor/e2e-shared/qwenwork-native-state/engine-sqlite.mjs';
import {buildQwenCallIndex,RESOURCE_SCHEMA} from './native-normalizer.mjs';
import {flowTiming} from '../../vendor/e2e-shared/resource-metrics/flow-timing.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
const bytes=x=>Buffer.from(JSON.stringify(x,null,2)+'\n');
const lines=x=>Buffer.from(x.map(v=>JSON.stringify(v)).join('\n')+'\n');
const artifact=(path,b,extra={})=>({path,sha256:sha(b),size:b.length,...extra});
const iso=x=>Number.isFinite(x)?new Date(x).toISOString():null;
export function normalizeQwenEngineTrace(evidence,{state,prompt}) {
 const session={...state.session,...Object.fromEntries(['conversation_id','sub_chat_id','local_project_id'].map(k=>[k,state.extensions.qwenwork[k]]))};
 const verified=verifyQwenEngineEvidence(evidence,{session,prompt,terminal:true});
 const root=verified.root.id, messages=new Map(verified.messages.map(x=>[x.id,x]));
 const events=[];const source=(line)=>({adapter:QWEN_ENGINE_PROFILE,raw_ref:`raw/native-part-rows.jsonl#L${line}`,redacted:false});
 const append=(value)=>events.push({schema_id:'urn:wildclawbench:schema:general-e2e:transcript-event:v1',schema_version:1,identity:state.identity,role:null,content:null,...value});
 const textParts=new Map();
 for (const [i,row] of verified.parts.entries()) {
  const part=row.parsed,message=messages.get(row.message_id),isChild=row.session_id!==root;
  const common={event_id:row.id,occurred_at:iso(part.time?.start??row.time_created),native_session_id:row.session_id,native_message_id:row.message_id,is_subagent:isChild,source:source(i+1)};
  if(part.type==='text' && !part.ignored && !part.synthetic){const list=textParts.get(row.message_id)||[];list.push({row,common});textParts.set(row.message_id,list);}
  else if(part.type==='tool'){
   const call=part.callID,tool=part.tool,result=part.state;
   if(!call||!tool||!['completed','error'].includes(result?.status))throw Error('QWEN_ENGINE_TOOL_RESULT_INVALID');
   append({...common,type:'tool_call',role:'assistant',tool:{call_id:call,name:tool,arguments:result.input??null,status:'unknown'}});
   append({...common,event_id:row.id+'-result',occurred_at:iso(result.time?.end??row.time_updated),type:'tool_result',role:'user',tool:{call_id:call,result:result.status==='error'?result.error??result.output??null:result.output??null,status:result.status==='error'||Number.isInteger(result.metadata?.exit)&&result.metadata.exit!==0?'error':'success',native_outcome:result.status,...(Number.isInteger(result.metadata?.exit)?{exit_code:result.metadata.exit}:{})}});
  }else append({...common,type:'status',native_type:part.type,native_status:part.type});
 }
 for(const [id,parts] of textParts){const m=messages.get(id),rootUser=m.session_id===root&&m.parsed.role==='user';append({...parts[0].common,event_id:id+'-text',occurred_at:iso(m.parsed.role==='assistant'?m.parsed.time?.completed??m.time_updated:m.time_created),type:m.parsed.role==='user'?'user_message':'assistant_message',role:m.parsed.role,content:rootUser?prompt.content:parts.map(p=>p.row.parsed.text).join('\n'),native_message_part_ids:parts.map(p=>p.row.id)});}
 events.sort((a,b)=>Date.parse(a.occurred_at)-Date.parse(b.occurred_at)||a.event_id.localeCompare(b.event_id));
 events.forEach((x,i)=>x.sequence=i);
 const last=events.filter(x=>x.type==='assistant_message').at(-1);
 if(last?.native_session_id!==root||last?.native_message_id!==verified.final_message.id||!last.content?.trim())throw Error('QWEN_ENGINE_FINAL_RESPONSE_AMBIGUOUS');
 const calls=buildQwenCallIndex(events);
 return {events,calls,final_response:last.content,native_root_session_id:root,
   native_event_count:verified.parts.length+verified.parts.filter(x=>x.parsed.type==='tool').length,
   filtered_native_event_count:[...textParts.values()].reduce((n,x)=>n+x.length-1,0)};
}
export function buildQwenEngineResources({state,sources,calls,collectedAt}) {
 const names=['input_tokens','output_tokens','total_tokens','cache_read_input_tokens','cache_creation_input_tokens','reasoning_output_tokens','request_count','request_attempt_count','call_count','duration_seconds','agent_duration_seconds'];
 const refs=sources.map(x=>x.path),unavailable=(note)=>({value:null,status:'unavailable',basis:note});
 const flow=flowTiming(state.prompt.sent_at,state.execution.finished_at);
 if(flow.value!==state.execution.duration_seconds)throw Error('QWEN_ENGINE_FLOW_TIMING_MISMATCH');
 const coverage=Object.fromEntries(names.map(x=>[x,{known:0,total:null,unit:x==='call_count'?'tool_call':'model_response'}]));
 coverage.call_count={known:calls.length,total:calls.length,unit:'tool_call'};coverage.duration_seconds={known:1,total:1,unit:'attempt'};
 return {schema_id:RESOURCE_SCHEMA,schema_version:1,identity:state.identity,collection:{collector:QWEN_ENGINE_PROFILE,version:'1.0.0',status:'partial',collected_at:collectedAt,sources,warnings:['QWEN_ENGINE_TOKEN_SEMANTICS_UNVERIFIED','QWEN_ENGINE_REQUEST_SEMANTICS_UNVERIFIED'],excluded_scope:['judge-usage','control-usage','unobserved-http-retries','client-background-services'],coverage,metric_sources:Object.fromEntries(names.map(x=>[x,refs]))},metrics:{usage:Object.fromEntries(names.slice(0,6).map(x=>[x,unavailable('Native engine token totals retained as raw evidence; semantics not admitted')])),requests:{request_count:unavailable('Assistant messages are not independently verified model requests'),request_attempt_count:unavailable('HTTP attempts unavailable')},tools:{call_count:{value:calls.length,status:'observed',basis:'Unique bound native tool parts with terminal results; includes linked child sessions'}},timing:{duration_seconds:flow,agent_duration_seconds:unavailable('No admitted native end-to-end agent timing profile')}}};
}
export async function collectQwenEngineEvidence({state,bindingSources,journalSource,configSource,unitRoot,outputRoot,redacted=false}) {
 if(redacted)throw Error('QWEN_ENGINE_LIVE_REDACTION_PROFILE_UNSUPPORTED');
 const config=configSource?.value,journal=journalSource.value;
 if(!config||config.config_digest!==journal.config_digest||config.identity.task_id!==state.identity.task_id)throw Error('QWEN_ENGINE_FROZEN_CONFIG_INVALID');
 const promptBytes=await readFile(state.prompt.path);if(sha(promptBytes)!==state.prompt.sha256)throw Error('QWEN_ENGINE_FROZEN_PROMPT_DRIFT');
 const prompt={sha256:state.prompt.sha256,content:promptBytes.toString('utf8')};
 const original=journal.session.prompt_evidence,b=await readFile(original.transcript_path);
 if(sha(b)!==original.transcript_sha256||b.length!==original.transcript_size)throw Error('QWEN_ENGINE_PRIOR_PROMPT_PROOF_DRIFT');
 const session={...state.session,...Object.fromEntries(['conversation_id','sub_chat_id','local_project_id'].map(k=>[k,state.extensions.qwenwork[k]]))};
 const old=JSON.parse(b);const oldBinding=verifyQwenEngineEvidence(old,{session,prompt});
 const evidence=await captureQwenEngineEvidence({sessionDatabase:config.client.session_db,session,prompt,terminal:true});
 const latest=verifyQwenEngineEvidence(evidence,{session,prompt,terminal:true});
 if(oldBinding.binding.nativeSessionId!==latest.binding.nativeSessionId)throw Error('QWEN_ENGINE_NATIVE_SESSION_REPLACED');
 const normalized=normalizeQwenEngineTrace(evidence,{state,prompt});
 const files=new Map([['raw/native-engine-snapshot.json',bytes(evidence)],['raw/native-part-rows.jsonl',lines(evidence.native.parts)],['raw/native-message-rows.jsonl',lines(evidence.native.messages)],['raw/prior-prompt-evidence.json',b],['raw/dispatch-journal.json',journalSource.bytes],['raw/frozen-config.json',configSource.bytes]]);
 const raw=[...files].map(([p,v])=>artifact(p,v));const bindings=bindingSources.map((x,i)=>artifact(`bindings/${i+1}-session-binding.json`,x.bytes));bindings.forEach((x,i)=>files.set(x.path,bindingSources[i].bytes));
 state.extensions.qwenwork.native_terminal_reconciliation={mode:QWEN_ENGINE_PROFILE,verified:true,native_root_session_id:normalized.native_root_session_id};
 state.extensions.client={...(state.extensions.client||{}),model:journal.configuration?.model?.actual_model??null,model_verification_status:'verified',model_identity_kind:'client-ui-option',model_evidence_sha256:journalSource.sha256,native_engine:'opencode',native_model_id:latest.route.modelId};
 const finalBytes=Buffer.from(normalized.final_response,'utf8');
 state.extensions.evidence={...(state.extensions.evidence||{}),final_response_path:relative(unitRoot,join(outputRoot,'execution/final-response.md')).split('\\').join('/'),final_response_sha256:sha(finalBytes)};
 const stateBytes=bytes(state),transcript=lines(normalized.events);
 const index={schema_id:'urn:wildclawbench:schema:general-e2e:trace-index:v2',schema_version:2,identity:state.identity,adapter:{id:QWEN_ENGINE_PROFILE,version:'1.0.0',source:'qwenwork-native-scoped-sqlite-export'},session:{thread_id:null,turn_id:null,session_id:state.session.session_id,cwd:state.session.cwd,lifecycle_generation:null},transcript:artifact('transcript.jsonl',transcript,{event_count:normalized.events.length}),raw_trace:raw,binding_evidence:bindings,normalization:{native_event_count:normalized.native_event_count,normalized_event_count:normalized.events.length,filtered_native_event_count:normalized.filtered_native_event_count,source_native_part_count:evidence.native.parts.length,native_event_count_basis:'Native part content atoms; terminal tools have invocation and result; exact-concatenated text parts count as filtered grouping',compatibility_profiles:['general-e2e-transcript-event-v1',QWEN_ENGINE_PROFILE]},completeness:{status:'complete',omitted_event_count:0,missing:[],scope:'Bound parent and recursively linked native child sessions; every native part retained as stored',native_output_truncation_count:latest.parts.filter(x=>x.parsed.state?.metadata?.truncated===true).length},calls:normalized.calls};
 const indexBytes=bytes(index),sources=[artifact('execution/automation-state.json',stateBytes),artifact('trace/trace-index.json',indexBytes),...[...raw,...bindings].map(x=>({...x,path:'trace/'+x.path}))];
 const resource=buildQwenEngineResources({state,sources,calls:normalized.calls,collectedAt:new Date().toISOString()});
 const stage=await mkdtemp(join(dirname(outputRoot),'.qwen-engine-collect-'));
 try {for(const [p,v] of files){const target=join(stage,'trace',p);await mkdir(dirname(target),{recursive:true});await writeFile(target,v,{flag:'wx',mode:0o600});}
 for(const [p,v] of [['execution/automation-state.json',stateBytes],['execution/final-response.md',finalBytes],['trace/transcript.jsonl',transcript],['trace/trace-index.json',indexBytes],['resource-metrics.json',bytes(resource)]]){const target=join(stage,p);await mkdir(dirname(target),{recursive:true});await writeFile(target,v,{flag:'wx',mode:0o600});}await rename(stage,outputRoot);
 }catch(error){await rm(stage,{recursive:true,force:true});throw error;}
 return {status:'PASS',output_root:outputRoot,state_file:join(outputRoot,'execution/automation-state.json'),trace_index:join(outputRoot,'trace/trace-index.json'),resource_metrics:join(outputRoot,'resource-metrics.json'),identity:state.identity,trace:index,resource};
}
