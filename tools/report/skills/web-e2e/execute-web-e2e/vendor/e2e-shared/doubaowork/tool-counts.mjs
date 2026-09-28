// Count native invocation identities independently of process-content completeness.
import { normalizeRuntimeMessages } from './runtime-messages.mjs';
import { normalizeNativeToolEvents } from './runtime-tools.mjs';
import { readFile, lstat } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
const ensure=(ok,code)=>{if(!ok)throw Error(code)};
const hash=b=>createHash('sha256').update(b).digest('hex');
export function countBoundTools({execution,state,index,transcript,runtime,journal,nativeSnapshot}) {
  ensure(execution.execution.business_status==='completed'&&state.phase==='COMPLETED','EXECUTION_NOT_COMPLETED');
  ensure(JSON.stringify(execution.identity)===JSON.stringify(state.identity),'STATE_IDENTITY');
  ensure(nativeSnapshot.profile_sha256===journal.native_tool_observer.profile_sha256,'TOOL_PROFILE');
  const native=normalizeRuntimeMessages(runtime,journal);
  ensure(native.terminal==='completed'&&native.conversation_id===runtime.conversation_id,'NATIVE_TERMINAL');
  const local=normalizeNativeToolEvents(nativeSnapshot,{attemptId:execution.identity.attempt_id,workspace:journal.workspace,
    agentId:native.native_request_session_id,conversationId:native.conversation_id,sentAt:journal.timing.sent_at,finishedAt:native.finished_at});
  const starts=local.events.filter(e=>e.phase==='started');
  const localMap=new Map(starts.map(e=>[e.tool_call_id,e]));
  ensure(localMap.size===starts.length,'DUPLICATE_LOCAL_CALL');
  const calls=transcript.filter(e=>e.type==='tool_call');
  const normalized=new Map(calls.map(e=>[e.tool.call_id,e]));
  ensure(normalized.size===calls.length&&normalized.size===index.calls.length,'NORMALIZED_CALL_SET');
  for(const [id,e] of localMap)ensure(normalized.get(id)?.tool.name===e.tool_name,'LOCAL_CALL_NOT_IN_BOUND_TRANSCRIPT');
  const localNames=new Set(starts.map(e=>e.tool_name));
  const assistant=Object.values(runtime.maps.messageMap).find(m=>m.message_id===native.reply_message_id);
  ensure(assistant&&assistant.content_blocks_v2.every(b=>b.is_finish===true),'NATIVE_BLOCKS_UNFINISHED');
  const ids=new Set(), remote=[], localDisplays={};
  const supported=new Set(['text_block','thinking_block','elapsed_block','file_operation_block','local_file_block','generic_tool_block','link_reader_block','search_query_result_block','pc_event_block']);
  for(const [i,b] of assistant.content_blocks_v2.entries()) {
    for(const [name,v] of Object.entries(b.content||{}))ensure(supported.has(name)||(v===null||v===''),'UNKNOWN_NATIVE_BLOCK');
    const key=['generic_tool_block','link_reader_block','search_query_result_block'].find(k=>b.content?.[k]);
    if(!key)continue;
    ensure(typeof b.block_id==='string'&&b.block_id,'NATIVE_BLOCK_ID_MISSING');
    ensure(!ids.has(b.block_id),'NATIVE_BLOCK_ID_DUPLICATE');ids.add(b.block_id);
    const detail=b.content[key];
    const name=key==='search_query_result_block'?'general_search':detail.tool_name;
    ensure(typeof name==='string'&&name,'NATIVE_TOOL_NAME_MISSING');
    if(localNames.has(name)){localDisplays[name]=(localDisplays[name]||0)+1;continue;}
    ensure(['web.fetch','calculator','general_search','tool_search','TaskOutput'].includes(name),'REMOTE_TOOL_PROFILE_UNSUPPORTED');
    remote.push({id_namespace:'native-im-content-block',native_id:b.block_id,tool_name:name,
      native_message_id:native.reply_message_id,native_block_type:key,source_ref:`trace/raw/runtime-messages.json#/maps/messageMap/${native.reply_message_id}/content_blocks_v2/${i}`,
      url:typeof detail.url==='string'?detail.url:null,
      queries:Array.isArray(detail.queries)?detail.queries:null,provider_call_id:null,
      count_only:true,arguments_or_results_synthesized:false});
  }
  for(const [name,n] of Object.entries(localDisplays))ensure(n<=starts.filter(e=>e.tool_name===name).length,'LOCAL_DISPLAY_EXCEEDS_LEDGER');
  const providerRemote=[...normalized].filter(([id])=>!localMap.has(id)).map(([,e])=>e.tool);
  const blockNames=new Set(remote.map(t=>t.tool_name));
  const providerOnly=providerRemote.filter(t=>!blockNames.has(t.name));
  ensure(providerOnly.every(t=>['present_files'].includes(t.name)), 'UNMATCHED_PROVIDER_TOOL_PROFILE');
  const crossChecks=[];
  for(const name of blockNames) {
    const existing=providerRemote.filter(t=>t.name===name), blocks=remote.filter(t=>t.tool_name===name);
    ensure(existing.length<=blocks.length,'PROVIDER_CALLS_EXCEED_NATIVE_BLOCKS:'+name);
    if(name==='web.fetch'){
      const urls=new Map();for(const b of blocks)urls.set(b.url,(urls.get(b.url)||0)+1);
      for(const t of existing){const u=t.arguments?.url;ensure(typeof u==='string'&&(urls.get(u)||0)>0,'WEB_FETCH_URL_BINDING');urls.set(u,urls.get(u)-1);}
    }
    crossChecks.push({tool_name:name,trajectory_calls:existing.length,native_blocks:blocks.length,
      missing_from_normalized_trajectory:blocks.length-existing.length});
  }
  const catalog=[...starts.map(e=>({id_namespace:'native-local-tool-call',native_id:e.tool_call_id,tool_name:e.tool_name,
    source_ref:`trace/raw/native-tools.json#/events/${e.raw_event_index}`,count_only:false})),
    ...providerOnly.map(t=>({id_namespace:'native-trajectory-call',native_id:t.call_id,tool_name:t.name,
      source_ref:`trace/transcript.jsonl#event=${normalized.get(t.call_id).event_id}`,count_only:false})),...remote];
  const byTool={};for(const e of catalog)byTool[e.tool_name]=(byTool[e.tool_name]||0)+1;
  return {status:'complete',basis:'deduplicated bound local protocol call IDs plus unique native remote invocation block IDs; trace order and result-content coverage are independent',
    total:catalog.length,by_tool:Object.fromEntries(Object.entries(byTool).sort()),original_normalized_count:normalized.size,
    additional_calls:catalog.length-normalized.size,local_calls:starts.length,provider_only_calls:providerOnly.length,remote_calls:remote.length,
    original_process_trace_status:index.completeness.status,original_process_missing:index.completeness.missing,
    cross_checks:crossChecks,catalog};
}

export async function recountArchivedTools({stateFile, traceIndex}) {
 const state=JSON.parse(await readFile(stateFile,'utf8'));
 const index=JSON.parse(await readFile(traceIndex,'utf8')),base=dirname(resolve(traceIndex));
 ensure(JSON.stringify(index.identity)===JSON.stringify(state.identity),'COUNT_STATE_IDENTITY');
 async function bound(relativePath){
  const entries=[...index.raw_trace,...(index.binding_evidence||[]),index.transcript].filter(x=>x.path===relativePath);
  ensure(entries.length===1,'COUNT_SOURCE_AMBIGUOUS');
  const path=resolve(base,relativePath);ensure(path.startsWith(base+sep),'COUNT_SOURCE_PATH');
  const info=await lstat(path);ensure(info.isFile()&&!info.isSymbolicLink(),'COUNT_SOURCE_FILE');
  const bytes=await readFile(path);ensure(bytes.length===entries[0].size&&hash(bytes)===entries[0].sha256,'COUNT_SOURCE_DRIFT');return bytes;
 }
 const runtime=JSON.parse(await bound('raw/runtime-messages.json'));
 const nativeSnapshot=JSON.parse(await bound('raw/native-tools.json'));
 const journal=JSON.parse(await bound('bindings/dispatch-journal.json'));
 const transcript=(await bound(index.transcript.path)).toString('utf8').split('\n').filter(x=>x.trim()).map(JSON.parse);
 return countBoundTools({execution:{identity:state.identity,execution:state.execution},state,index,transcript,runtime,journal,nativeSnapshot});
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
 const args=process.argv.slice(2);ensure(args.length===4&&args[0]==='--state-file'&&args[2]==='--trace-index','COUNT_USAGE');
 recountArchivedTools({stateFile:args[1],traceIndex:args[3]}).then(result=>console.log(JSON.stringify(result))).catch(error=>{console.error(error.message);process.exitCode=1});
}
