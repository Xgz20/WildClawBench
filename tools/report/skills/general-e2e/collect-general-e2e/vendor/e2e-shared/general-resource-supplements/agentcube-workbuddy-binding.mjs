import { createHash } from 'node:crypto';
import { win32, resolve, relative, isAbsolute } from 'node:path';
import { readFile, lstat } from 'node:fs/promises';
import { createNativeResourceMetricParsers } from '../resource-metrics/native-parsers.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const ensure=(ok,code)=>{if(!ok)throw Error(code)};
const textOf=v=>typeof v==='string'?v:Array.isArray(v)?v.filter(x=>['text','input_text','output_text'].includes(x.type)).map(x=>x.text||'').join(''):'';
const pathEqual=(a,b)=>typeof a==='string'&&typeof b==='string'&&win32.normalize(a).toLowerCase()===win32.normalize(b).toLowerCase();
const time=v=>typeof v==='number'?new Date(v).toISOString():typeof v==='string'&&!Number.isNaN(Date.parse(v))?new Date(v).toISOString():null;
const modelKey=v=>String(v||'').trim().toLowerCase().replace(/[ _]/g,'-');
export const ADAPTER='agentcube-workbuddy-native';

function bindPrompt(user, prompt, product) {
  const nativePrompt = textOf(user.content);
  const wrappers = [...nativePrompt.matchAll(/<user_query>([\s\S]*?)<\/user_query>/g)];
  const wrapped = wrappers.length === 1 && nativePrompt.trimEnd().endsWith('</user_query>');
  const actual = wrapped ? wrappers[0][1] : nativePrompt;
  const normalize = text => text.replace(/\r\n/g, '\n').trim();
  const expected = normalize(prompt);
  const observed = normalize(actual);
  let kind = 'workbuddy-user-query';
  let droppedLinefeeds;
  if (observed !== expected) {
    // WorkBuddy 5.9.3 can collapse consecutive linefeeds in the native text block.
    // Keep nonempty line boundaries, the single-line task, and every other character exact.
    const sections = expected.split(/\n+任务：\n+/);
    const collapsed = wrapped && product.product_version === '5.9.3'
      && Array.isArray(user.content) && user.content.length === 1 && user.content[0].type === 'input_text'
      && nativePrompt.startsWith('<system-reminder data-role="user-context">')
      && sections.length === 2 && sections[0].startsWith('工作区公开指令（AGENTS.md）：\n')
      && sections[1] && !/[\r\n]/.test(sections[1])
      && expected.replace(/\n{2,}/g, '\n') === observed;
    ensure(collapsed, 'WORKBUDDY_PROMPT_MISMATCH');
    kind = 'workbuddy-user-query-inline-context-blank-lines-collapsed';
    droppedLinefeeds = expected.length - observed.length;
  }
  return {kind, native_message_sha256: sha(Buffer.from(nativePrompt)),
    decoded_text_sha256: sha(Buffer.from(actual)),
    ...(droppedLinefeeds === undefined ? {} : {dropped_linefeeds: droppedLinefeeds})};
}

export function analyzeWorkBuddy(bytes, input) {
  const {identity,prompt,guest_cwd:cwd,requested_model:model,requested_max_mode:maxMode=false,report,product_report:product}=input;
  ensure(report?.schema_version===2&&report.status==='completed','WORKBUDDY_CONTROLLER_TERMINAL_UNVERIFIED');
  ensure(product?.product_report===true&&pathEqual(product.workflow?.workspace,cwd)&&product.workflow.model===model,'WORKBUDDY_WORKSPACE_OR_MODEL_SELECTION_MISMATCH');
  const rows=bytes.toString('utf8').replace(/^\uFEFF/,'').split(/\r?\n/).map((line,i)=>({line:i+1,text:line})).filter(x=>x.text.trim()).map(x=>({line:x.line,value:JSON.parse(x.text)}));
  const messages=rows.filter(x=>x.value.type==='message'&&['user','assistant'].includes(x.value.role));
  const users=messages.filter(x=>x.value.role==='user'&&!x.value.providerData?.isMeta&&!x.value.providerData?.isCompactInternal);
  ensure(users.length===1,'WORKBUDDY_SINGLE_TASK_BINDING_AMBIGUOUS');
  const user=users[0].value;
  const promptTransport=bindPrompt(user,prompt,product);
  const scoped=rows.filter(x=>['message','function_call','function_call_result','model-usage'].includes(x.value.type));
  const sessions=new Set(scoped.map(x=>x.value.sessionId).filter(Boolean));
  ensure(sessions.size===1&&scoped.filter(x=>x.value.type!=='model-usage').every(x=>x.value.sessionId&&pathEqual(x.value.cwd,cwd)),'WORKBUDDY_NATIVE_IDENTITY_MISMATCH');
  for(const {value:r} of scoped.filter(x=>x.value.type==='model-usage')){
    const baggage=new Map(String(r._meta?.baggage||'').split(',').filter(Boolean).map(part=>{const at=part.indexOf('=');return [part.slice(0,at).trim(),decodeURIComponent(part.slice(at+1).trim())]}));
    ensure(pathEqual(r.cwd,cwd)&&(r.sessionId===[...sessions][0]||baggage.get('codebuddy.session_id')===[...sessions][0]),'WORKBUDDY_USAGE_SESSION_MISMATCH');
  }
  const requestIds=new Set(scoped.map(x=>x.value.providerData?.conversationRequestId).filter(Boolean));
  ensure(requestIds.size===1,'WORKBUDDY_NATIVE_REQUEST_AMBIGUOUS');
  const session={session_id:[...sessions][0],turn_id:[...requestIds][0],thread_id:null,cwd:user.cwd,lifecycle_generation:null};
  const modelNames=new Set(scoped.map(x=>x.value.providerData?.requestModelName||x.value.providerData?.model).filter(Boolean));
  ensure(modelNames.size===1,'WORKBUDDY_NATIVE_MODEL_AMBIGUOUS');const actualModel=[...modelNames][0];
  if(!['auto','极致'].includes(modelKey(model)))ensure(modelKey(actualModel)===modelKey(model),'WORKBUDDY_TESTED_MODEL_MISMATCH');
  // Max is a product switch, not AStudio reasoning. The controller must retain its readback.
  const diagnostics=input.diagnostics;
  ensure(diagnostics?.max_mode===maxMode&&diagnostics.model===model&&pathEqual(diagnostics.workspace,cwd),'WORKBUDDY_MAX_MODE_UNVERIFIED');
  let terminal=null;
  for(const row of rows){const r=row.value;if(row.line<users[0].line)continue;
    if(['finish','task_finished','task-completed'].includes(r.type))terminal=row;
    else if(r.type==='function_call')terminal=null;
    else if(r.type==='message'&&r.role==='assistant'&&r.status==='completed')terminal=row;
  }
  ensure(terminal,'WORKBUDDY_NATIVE_TERMINAL_MISSING');
  const assistants=messages.filter(x=>x.value.role==='assistant'&&x.line>users[0].line);
  const final=assistants.at(-1);ensure(final&&textOf(final.value.content).trim(),'WORKBUDDY_NATIVE_FINAL_MISSING');
  const events=[],calls=new Map(),results=new Map(),missing=[];let filtered=0;
  const rawName='raw/'+input.raw_name;
  function emit(row,type,extra){events.push({schema_id:'urn:wildclawbench:schema:general-e2e:transcript-event:v1',schema_version:1,identity,event_id:'native-L'+row.line,sequence:events.length,occurred_at:time(row.value.timestamp),type,source:{adapter:ADAPTER,raw_ref:rawName+'#L'+row.line,redacted:false},...extra})}
  for(const row of rows){const r=row.value;
    if(r.type==='message'&&r.role==='user'&&r.providerData?.isCompactInternal===true){
      ensure(r.id&&r.providerData.agent==='cli'&&r.providerData.skipRun===false&&r.providerData.startsNewUserRequest!==true&&r.providerData.conversationRequestId===session.turn_id,'WORKBUDDY_COMPACTION_BINDING_INVALID');
      emit(row,'status',{content:'client_compaction_context',native_status:r});
    }else if(r.type==='message'&&['user','assistant'].includes(r.role))emit(row,r.role==='user'?'user_message':'assistant_message',{role:r.role,content:textOf(r.content)});
    else if(r.type==='function_call'){
      ensure(typeof r.callId==='string'&&r.callId&&typeof r.name==='string'&&r.name&&!calls.has(r.callId),'WORKBUDDY_NATIVE_CALL_DUPLICATE');let args=r.arguments;
      if(typeof args==='string'){try{args=JSON.parse(args)}catch{}}
      calls.set(r.callId,{call_id:r.callId,call_sequence:events.length});emit(row,'tool_call',{tool:{call_id:r.callId,name:r.name,arguments:args}});
    }else if(r.type==='function_call_result'){
      const id=r.callId||r.toolCallId;ensure(id&&!results.has(id),'WORKBUDDY_NATIVE_RESULT_DUPLICATE');results.set(id,events.length);
      emit(row,'tool_result',{tool:{call_id:id,result:r.content??r.output??r.result,status:r.isError?'error':'unknown'},content:textOf(r.content??r.output??r.result)});
    }else if(r.type==='model-usage')emit(row,'usage',{usage:r.providerData?.usage});
    else if(['finish','task_finished','task-completed'].includes(r.type))emit(row,'status',{content:r.type,native_status:r});
    else filtered++;
  }
  if([...calls.keys()].some(id=>results.has(id)&&results.get(id)<calls.get(id).call_sequence))missing.push('native-tool-order-invalid');
  if([...calls.keys()].some(id=>!results.has(id))||[...results.keys()].some(id=>!calls.has(id)))missing.push('native-tool-trajectory-incomplete');
  // This profile binds a fresh AgentCube task directly to its primary raw log;
  // it does not pretend that a desktop runtime snapshot was observed.
  const metricRows=rows.map(({value})=>{
    const r=structuredClone(value),pd=r.providerData;if(!pd?.messageId)return r;
    const raw=pd.rawUsage,usage=pd.usage;
    if(!raw){delete pd.usage;return r;}
    ensure([raw.prompt_tokens,raw.completion_tokens,raw.total_tokens].every(v=>Number.isSafeInteger(v)&&v>=0)
      &&raw.total_tokens===raw.prompt_tokens+raw.completion_tokens,'WORKBUDDY_RAW_USAGE_INVALID');
    if(usage)ensure(usage.inputTokens===raw.prompt_tokens&&usage.outputTokens===raw.completion_tokens&&usage.totalTokens===raw.total_tokens,'WORKBUDDY_RAW_USAGE_MISMATCH');
    pd.usage={requests:1,inputTokens:raw.prompt_tokens,outputTokens:raw.completion_tokens,totalTokens:raw.total_tokens,
      ...(raw.prompt_tokens_details?.cached_tokens!=null?{inputTokensDetails:[{cached_tokens:raw.prompt_tokens_details.cached_tokens}]}:{}),
      ...(raw.completion_tokens_details?.reasoning_tokens!=null?{outputTokensDetails:[{reasoning_tokens:raw.completion_tokens_details.reasoning_tokens}]}:{})};
    return r;
  });
  const parsed=createNativeResourceMetricParsers({schemaVersion:'wildclawbench.agentcube-workbuddy-resource/v1',version:'0.1.0',scope:'bound-primary-conversation',excludedScope:['unobserved-http-retries','unlinked-child-agents']}).parseWorkBuddy(metricRows.filter(r=>!(r.type==='message'&&r.role==='user'&&r.providerData?.isCompactInternal===true)));
  const fields={usage:{},requests:{},tools:{}};for(const [group,keys] of Object.entries({usage:['input_tokens','output_tokens','total_tokens','cache_read_input_tokens','cache_creation_input_tokens','reasoning_output_tokens'],requests:['request_count','request_attempt_count'],tools:['call_count']})){
    for(const key of keys){const value=(group==='tools'?parsed.tools:parsed.usage)[key]??null;fields[group][key]={value,status:value===null?'unavailable':parsed.collection.metrics[key]?.status||'observed',basis:parsed.collection.metrics[key]?.basis||'bound native WorkBuddy JSONL'};}
  }
  const started=time(user.timestamp),ended=time(terminal.value.timestamp);const duration=started&&ended?Date.parse(ended)-Date.parse(started):null;
  ensure(duration===null||duration>=0,'WORKBUDDY_NATIVE_CLOCK_INVALID');
  fields.timing={duration_seconds:{value:duration===null?null:duration/1000,status:duration===null?'unavailable':'observed',basis:'native bound user record to native terminal; excludes scoring'},agent_duration_seconds:{value:null,status:'unavailable',basis:'native request start clock is not supplied by JSONL'}};
  return {schema:'wildclawbench.agentcube-workbuddy-native-binding/v1',adapter:ADAPTER,identity,session,actual_model:actualModel,native_model:actualModel,reasoning_effort:null,max_mode:maxMode,
    prompt_sha256:sha(Buffer.from(prompt)),prompt_transport:promptTransport,
    raw_sha256:sha(bytes),user_line:users[0].line,terminal_line:terminal.line,native_event_count:rows.length,filtered_native_event_count:filtered,events,calls:[...calls.values()].map(call=>({...call,result_sequence:results.get(call.call_id)??null})),missing,
    final_response:textOf(final.value.content),native_duration_ms:null,native_started_at:started,native_finished_at:ended,
    native_resources:{metrics:fields,collection:{coverage:{},known_subtotals:parsed.collection.known_subtotals||{},warnings:parsed.collection.warnings||[]}},
    controller_binding:{product_report:Object.fromEntries(["schema_version","session_id","product_version","product_report","workflow","native_files"].filter(key=>key in product).map(key=>[key,product[key]])),diagnostics:Object.fromEntries(["completion_signal","workspace","model","mode","max_mode","answer_chars","answer_source"].filter(key=>key in diagnostics).map(key=>[key,diagnostics[key]])),report}};
}

const same=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));
function stable(v){return Array.isArray(v)?v.map(stable):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v}
async function readInside(root,path){
  ensure(typeof path==='string'&&!path.includes('\\'),'WORKBUDDY_ARCHIVE_PATH_INVALID');const full=resolve(root,path),rel=relative(resolve(root),full);
  ensure(rel&&!rel.startsWith('..')&&!isAbsolute(rel),'WORKBUDDY_ARCHIVE_PATH_ESCAPE');
  let current=resolve(root);for(const part of rel.split('/')){current=resolve(current,part);ensure(!(await lstat(current)).isSymbolicLink(),'WORKBUDDY_ARCHIVE_LINK')}
  ensure((await lstat(full)).isFile(),'WORKBUDDY_ARCHIVE_FILE');return readFile(full);
}
export async function verifyAgentCubeWorkBuddy({unitRoot,traceRoot,index,stateBytes,record}){
 const state=JSON.parse(stateBytes),bound=state.native_binding;
 ensure(state.schema==='wildclawbench.agentcube-execution-proof/v1'&&state.unit?.harness==='workbuddy'&&state.unit?.backend==='agentcube'&&index.adapter?.id===ADAPTER,'WORKBUDDY_ARCHIVE_PROFILE');
 ensure(same(state.identity,index.identity)&&same(state.identity,record.identity)&&same(bound.identity,state.identity),'WORKBUDDY_ARCHIVE_IDENTITY');
 ensure(sha(await readInside(traceRoot,'bindings/execution-proof.json'))===sha(stateBytes),'WORKBUDDY_ARCHIVE_PROOF');
 ensure(index.raw_trace?.length===1,'WORKBUDDY_ARCHIVE_PRIMARY_TRACE');const ref=index.raw_trace[0],raw=await readInside(traceRoot,ref.path);
 ensure(sha(raw)===ref.sha256&&raw.length===ref.size,'WORKBUDDY_ARCHIVE_RAW_DRIFT');
 const prompt=(await readInside(unitRoot,`execution/tasks/${record.identity.task_id}/PROMPT.md`)).toString('utf8');
 const replay=analyzeWorkBuddy(raw,{identity:state.identity,prompt,guest_cwd:bound.session.cwd,requested_model:state.unit.model,requested_max_mode:state.unit.max_mode||false,report:state.report,...bound.controller_binding,raw_name:ref.path.split('/').at(-1)});
 ensure(!replay.missing.length&&same(replay.session,bound.session)&&replay.actual_model===bound.actual_model&&replay.max_mode===bound.max_mode&&replay.raw_sha256===bound.raw_sha256&&replay.prompt_sha256===state.prompt_sha256,'WORKBUDDY_ARCHIVE_BINDING');
 ensure(same(replay.prompt_transport,bound.prompt_transport),'WORKBUDDY_ARCHIVE_PROMPT_TRANSPORT');
 const transcript=(await readInside(traceRoot,index.transcript.path));ensure(sha(transcript)===index.transcript.sha256&&transcript.length===index.transcript.size,'WORKBUDDY_ARCHIVE_TRANSCRIPT_DRIFT');
 const events=transcript.toString('utf8').split(/\r?\n/).filter(x=>x.trim()).map(JSON.parse);ensure(same(events,replay.events)&&same(index.calls,replay.calls),'WORKBUDDY_ARCHIVE_TRANSCRIPT_REPLAY');
 const final=(await readInside(unitRoot,record.evidence.final_response_path)).toString('utf8');ensure(final===replay.final_response,'WORKBUDDY_ARCHIVE_FINAL_DRIFT');
 const cleanup=state.process_cleanup;ensure(cleanup?.schema==='wildclawbench.agentcube-process-cleanup/v1'&&cleanup.phase==='completed'&&cleanup.success===true&&cleanup.supported===true&&cleanup.platform==='win32'&&cleanup.after?.length===0&&cleanup.quiet_observed_milliseconds>=5000&&pathEqual(cleanup.workspace,bound.session.cwd),'WORKBUDDY_ARCHIVE_CLEANUP');
 return {status:'PASS',adapter:ADAPTER};
}
