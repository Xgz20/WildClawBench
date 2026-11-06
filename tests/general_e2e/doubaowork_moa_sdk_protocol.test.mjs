import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { MOA_SOURCE_SHA256 } from '../../tools/report/e2e-shared/doubaowork/runtime-moa.mjs';
import { verifyMoaSdkProtocol, countMoaSdkTools, fetchMoaSdkAttachments, parseMacSystemHttpsProxy } from '../../tools/report/e2e-shared/doubaowork/moa-sdk-protocol.mjs';
const sha=s=>createHash('sha256').update(s).digest('hex');
function fixture(rows) {
 const installed='2026-11-05T00:00:00.000Z';
 const snapshot={schema:'wildclawbench.doubaowork-native-tool-events/v1',profile:'doubaowork-tool-dispatch-observer/v1',
  profile_sha256:MOA_SOURCE_SHA256,attempt_id:'attempt',workspace:'/workspace',native_agent_id:'request',installed_at:installed,
  collected_at:'2026-11-05T00:00:03.000Z',events:[],ledger:[],contexts:[],errors:[],overflow:false,unknown_context_events:0,ledger_at_capacity:false,
  consumer_witness:{schema:'wildclawbench.doubaowork-local-tool-consumer-witness/v1',source_sha256:MOA_SOURCE_SHA256,installed_at:installed,
   received_calls:[],admission_rejections:[],unbound_agent_event_count:0},
  native_backend:{profile:'doubaowork-moa-2.35.15-inspector/v1',worker_id:'entry-moa',worker_source_sha256:MOA_SOURCE_SHA256,
   worker_pid:10,browser_pid:9,worker_start_identity:'worker start',browser_start_identity:'browser start',
   worker_command_sha256:'a'.repeat(64),browser_command_sha256:'b'.repeat(64),inspector_target_id:'12345678-1234-1234-1234-123456789012',
   endpoint:'http://127.0.0.1:9261',source_verification:'live-debugger-script-sha256',script_url:'https://resource.sandbox.invalid/local_webcontents/apps/entry-moa/main.js'}};
 const trajectoryBytes=Buffer.from(rows.map(JSON.stringify).join('\n')+'\n');
 return {trajectoryBytes,snapshot,assignmentProof:{status:'verified',source:'native-main-assignment/v1',agent_id:'m_main',assignment_sha256:'c'.repeat(64)},
  journal:{scene:'general',client:{version:'2.35.15'},attempt_id:'attempt',workspace:'/workspace',send:{dispatch_attempt_count:1},
   timing:{sent_at:'2026-11-05T00:00:01.000Z'},native_observation:{finished_at:'2026-11-05T00:00:02.000Z'},
   session:{conversation_id:'123',native_request_session_id:'request',prompt_readback:{status:'verified'}}},
  source:{kind:'doubaowork-session-trajectory',relative_path:'123/agents/m_main/system/trajectory.jsonl',agent_id:'m_main',sha256:sha(trajectoryBytes)}};
}
const call={role:'assistant',content:null,tool_calls:[{id:'call',type:'function',function:{name:'Bash',arguments:{command:'pwd'}}}]};
const result={role:'tool',tool_call_id:'call',content:'native stdout'};
test('media retrieval only reuses an already enabled loopback system proxy',()=>{
 assert.equal(parseMacSystemHttpsProxy('HTTPSEnable : 0'),null);
 assert.equal(parseMacSystemHttpsProxy('HTTPSEnable : 1\nHTTPSProxy : 127.0.0.1\nHTTPSPort : 7897'),'http://127.0.0.1:7897');
 assert.throws(()=>parseMacSystemHttpsProxy('HTTPSEnable : 1\nHTTPSProxy : other-host\nHTTPSPort : 7897'),/SYSTEM_PROXY_UNVERIFIED/);
});
test('SDK protocol uses original invocation IDs and results; an inactive JS observer does not zero the total',()=>{
 const p=verifyMoaSdkProtocol(fixture([call,result]));assert.equal(p.calls.length,1);assert.equal(p.legacy_js_observer.observed_deliveries,0);
 const transcript=[{type:'tool_call',tool:{call_id:'call',name:'Bash',arguments:{command:'pwd'}}},{type:'tool_result',tool:{call_id:'call',result:'native stdout'}}];
 assert.equal(countMoaSdkTools(p,transcript,{calls:[{}],completeness:{status:'complete'}}).total,1);
 transcript[1].tool.result='fabricated';assert.throws(()=>countMoaSdkTools(p,transcript,{calls:[{}],completeness:{status:'complete'}}),/NORMALIZED_CALL_DRIFT/);
});
test('SDK binding rejects missing results, duplicate calls, a foreign native session and unrelated media origins',()=>{
 assert.throws(()=>verifyMoaSdkProtocol(fixture([call])),/MISSING_RESULT/);
 assert.throws(()=>verifyMoaSdkProtocol(fixture([call,call,result])),/CALL_INVALID/);
 const bad=fixture([call,result]);bad.source.relative_path='other/agents/m_main/system/trajectory.jsonl';assert.throws(()=>verifyMoaSdkProtocol(bad),/SOURCE_DRIFT/);
 assert.throws(()=>verifyMoaSdkProtocol(fixture([call,{...result,image_link_list:['https://127.0.0.1/private']}])) ,/MEDIA_ORIGIN_UNVERIFIED/);
 const p=verifyMoaSdkProtocol(fixture([call,{...result,image_link_list:['https://p3-flow-sign.byteimg.com/a']}])) ;
 assert.equal(p.attachments[0].call_id,'call');assert.equal(p.attachments[0].image_index,0);
});
test('a native empty presentation acknowledgement remains null and does not imply success',()=>{
 const presentation=structuredClone(call);presentation.tool_calls[0].function={name:'present_files',arguments:{artifacts:[]}};
 const empty={role:'tool',tool_call_id:'call'};
 const p=verifyMoaSdkProtocol(fixture([presentation,empty]));assert.equal(p.calls[0].result_kind,'native-empty-presentation-ack');
 const transcript=[{type:'tool_call',tool:{call_id:'call',name:'present_files',arguments:{artifacts:[]}}},{type:'tool_result',tool:{call_id:'call',result:null,status:'unknown'}}];
 assert.equal(countMoaSdkTools(p,transcript,{calls:[{}],completeness:{status:'complete'}}).total,1);
 assert.throws(()=>verifyMoaSdkProtocol(fixture([call,empty])),/RESULT_INVALID/);
 assert.throws(()=>verifyMoaSdkProtocol(fixture([presentation,{...empty,is_error:true}])),/RESULT_INVALID/);
});
test('native media retrieval verifies type and bytes and refuses an unapproved redirect',async()=>{
 const original=globalThis.fetch;
 const protocol={attachments:[{url:'https://p3-flow-sign.byteimg.com/a',url_sha256:'a',call_id:'call',result_line:2,image_index:0}]};
 try {
  globalThis.fetch=async()=>new Response(Buffer.from([137,80,78,71,13,10,26,10,0]),{headers:{'content-type':'image/png'}});
  const files=await fetchMoaSdkAttachments(protocol,{disableSystemProxy:true});assert.equal(files.length,1);assert.equal(files[0].mime_type,'image/png');assert.equal(files[0].url,undefined);
  globalThis.fetch=async()=>new Response('html',{headers:{'content-type':'text/html'}});
  await assert.rejects(fetchMoaSdkAttachments(protocol,{disableSystemProxy:true}),/MEDIA_TYPE_UNVERIFIED/);
  globalThis.fetch=async()=>new Response(null,{status:302,headers:{location:'https://127.0.0.1/private'}});
  await assert.rejects(fetchMoaSdkAttachments(protocol,{disableSystemProxy:true}),/MEDIA_REDIRECT_UNVERIFIED/);
 } finally {globalThis.fetch=original;}
});
