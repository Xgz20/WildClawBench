// Read-only proof over frozen execution bytes. Never edits a trace or judges a rubric.
import {readFile,lstat,realpath} from 'node:fs/promises';
import {resolve,relative,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {normalizeRuntimeMessages} from './runtime-messages.mjs';
import {verifyNativeMainAssignment} from './bound-evidence.mjs';
import {verifyMoaSdkProtocol,countMoaSdkTools} from './moa-sdk-protocol.mjs';
import {reconcileNativeSearchDisplays,reconcileNativeGuiDisplays,reconcileNativePlatformNotices} from './search-displays.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const check=(v,msg)=>{if(!v)throw Error('MOA_PRESENTATION_PROOF_INVALID: '+msg);};
export async function verifyFrozenPresentation(root,execution){
 root=await realpath(root);
 async function read(name){
  check(typeof name==='string'&&!isAbsolute(name),'relative source');
  const path=resolve(root,name),rel=relative(root,path);check(rel&&!rel.startsWith('..'),'source scope');
  const st=await lstat(path);check(st.isFile()&&!st.isSymbolicLink()&&await realpath(path)===path,'regular source');
  return readFile(path);
 }
 const index=JSON.parse(await read('trace-index.json'));
 check(execution.harness?.id==='doubaowork'&&execution.phase==='COMPLETED'
  &&execution.execution?.business_status==='completed'&&execution.evidence?.completeness==='partial','execution');
 check(['batch_id','unit_id','task_id','attempt_id'].every(k=>execution.identity[k]===index.identity[k]),'identity');
 check(index.completeness?.status==='partial'&&index.completeness.omitted_event_count===0
  &&index.completeness.missing?.length===1&&index.completeness.missing[0]==='unmapped-native-message-block','only display mapping may be missing');
 const refs=[index.transcript,...index.raw_trace,...(index.binding_evidence||[])],files=new Map();
 for(const r of refs){const b=await read(r.path);check(b.length===r.size&&sha(b)===r.sha256,'source SHA '+r.path);files.set(r.path,b);}
 const required=name=>{check(files.has(name),'missing '+name);return files.get(name);};
 const j=JSON.parse(required('bindings/dispatch-journal.json')),runtime=JSON.parse(required('raw/runtime-messages.json'));
 check(j.attempt_id===execution.identity.attempt_id&&j.identity.task_id===execution.identity.task_id
  &&j.send.dispatch_attempt_count===1&&j.scene==='general','journal');
 const native=normalizeRuntimeMessages(runtime,j);
 check(native.terminal==='completed'&&native.native_cwd===execution.session.cwd
  &&native.conversation_id===execution.session.session_id&&native.reply_message_id===execution.session.turn_id
  &&native.prompt.sha256===execution.prompt.sha256,'primary native binding');
 const original=JSON.parse(required('raw/native-moa-sdk-protocol.json'));
 const assignment=verifyNativeMainAssignment(required('raw/native-assignment.md'),{
  agentId:original.native_source.agent_id,expectedHash:j.prompt.readback_sha256});
 const protocol=verifyMoaSdkProtocol({trajectoryBytes:required('raw/trajectory.jsonl'),assignmentProof:assignment,
  snapshot:JSON.parse(required('raw/native-tools.json')),journal:j,source:original.native_source});
 check(JSON.stringify(original.calls)===JSON.stringify(protocol.calls),'call proof');
 check(original.attachments.length===protocol.attachments.length,'media set');
 for(const [i,a]of original.attachments.entries()){
  const expected=protocol.attachments[i];
  check(a.status===undefined&&expected.availability===undefined&&a.call_id===expected.call_id
   &&a.result_line===expected.result_line&&a.image_index===expected.image_index&&a.url_sha256===expected.url_sha256
   &&a.native_image_reference===expected.native_image_reference
   &&JSON.stringify(a.resolution??null)===JSON.stringify(expected.resolution??null),'complete media binding');
  const b=required(a.path);check(b.length===a.size&&sha(b)===a.sha256,'media bytes');
 }
 const events=required(index.transcript.path).toString('utf8').split('\n').filter(x=>x.trim()).map(JSON.parse);
 const users=events.filter(e=>e.type==='user_message'),finals=events.filter(e=>e.type==='assistant_message');
 check(users.length===1&&sha(Buffer.from(users[0].content))===execution.prompt.sha256
  &&finals.at(-1)?.content===native.final_text,'transcript prompt/final');
 const final=new TextDecoder('utf-8',{fatal:true}).decode(await read('final-response-bound.txt'));
 check(final===native.final_text||final===native.final_text+'\n','bound final response');
 countMoaSdkTools(protocol,events,index);
 const modelEvents=protocol.calls.flatMap(c=>[
  {kind:'assistant_tool_call',call_id:c.call_id,tool_name:c.name,arguments:c.arguments},
  {kind:'tool_result',call_id:c.call_id,content:events.find(e=>e.type==='tool_result'&&e.tool.call_id===c.call_id)?.tool.result}]);
 const assistant=Object.values(runtime.maps.messageMap).find(m=>m.message_id===native.reply_message_id);
 const supported=new Set(['text_block','thinking_block','elapsed_block','file_operation_block','local_file_block','generic_tool_block']);
 const unknown=(assistant.content_blocks_v2||[]).filter(b=>Object.entries(b.content||{}).some(([k,v])=>!supported.has(k)&&!(k==='pc_event_block'&&v==='')));
 const search=reconcileNativeSearchDisplays(unknown,modelEvents),gui=reconcileNativeGuiDisplays(unknown,protocol),
  notices=reconcileNativePlatformNotices(unknown);
 const all=[...search.matched_block_ids,...gui.matched_block_ids,...notices.matched_block_ids],matched=new Set(all);
 check(matched.size===all.length&&unknown.length>0&&unknown.every(b=>matched.has(b.block_id)),'unresolved or duplicated native display');
 return {profile:'bound-native-moa-presentation-completeness/v1',record_origin:'deterministic derived proof; original execution and trace remain partial and unchanged',
  identity:execution.identity,original_evidence_completeness:execution.evidence.completeness,original_missing:execution.evidence.missing,
  native_sdk_sha256:protocol.source_sha256,native_call_count:protocol.calls.length,verified_media_count:protocol.attachments.length,
  search_projection:search,gui_projection:gui,platform_notices:notices,all_display_blocks_accounted:true,
  interpretation:'SDK arguments/results are authoritative; placeholder labels never establish empty search results; notices add no tool events'};
}
if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url){
 const [root,record]=process.argv.slice(2);
 verifyFrozenPresentation(root,JSON.parse(await readFile(record))).then(x=>console.log(JSON.stringify(x))).catch(e=>{console.error(e.message);process.exitCode=1;});
}
