import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import test from 'node:test';
import {QWEN_ENGINE_PROFILE,verifyQwenEngineEvidence} from '../../tools/report/e2e-shared/qwenwork-native-state/engine-sqlite.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
function fixture(){
 const session={session_id:'host',conversation_id:'chat',sub_chat_id:'sub',local_project_id:'project',cwd:'/work'};
 const binding={version:1,engineId:'opencode',hostSessionId:'host',subChatId:'sub',workingDirectory:'/work',executionLocationKey:'local',storageNamespace:'/native.db',nativeSessionId:'root'};
 const snapshot={method:'readonly-source-sqlite-online-backup',quick_check:'ok',snapshot_sha256:'a'.repeat(64),query_sha256:'b'.repeat(64),database_path:'/native.db'};
 const evidence={profile:QWEN_ENGINE_PROFILE,host:{record:{...session,stream_id:null,native_status:'ready',sub_chat_ext:JSON.stringify({engineSessionBindingV1:binding,modelExecutionRouteV2:{version:2,engineId:'opencode',modelId:'flash',modeKey:'flash'}})},inputs:[{chat_id:'chat',sub_chat_id:'sub',state:'consumed',message_id:'input',content:JSON.stringify({params:{chatId:'chat',subChatId:'sub',userMessageId:'input',prompt:''}})}],messages:[{role:'user',message_id:'input',parts:JSON.stringify([{type:'text',text:'prompt'}])}],snapshot},native:{snapshot,sessions:[{id:'root',parent_id:null,directory:'/work',version:'1.18.18-26102004'}],messages:[{id:'user',session_id:'root',time_created:1,data:JSON.stringify({role:'user'})},{id:'assistant',session_id:'root',time_created:2,data:JSON.stringify({role:'assistant',finish:'stop',time:{completed:3}})}],parts:[{id:'part',message_id:'user',session_id:'root',data:JSON.stringify({type:'text',text:'<workspace_context>\n/work\n</workspace_context>\nprompt'})}]}};
 return {evidence,options:{session,prompt:{sha256:sha('prompt')},terminal:true}};
}
test('new engine binds host admission, user bytes, native subtree and terminal message',()=>{const {evidence,options}=fixture();assert.equal(verifyQwenEngineEvidence(evidence,options).match_count,1);});
for(const [label,mutate,error] of [
 ['wrong host',e=>e.host.record.session_id='other',/HOST_BINDING/],
 ['wrong prompt',e=>e.host.messages[0].parts='[{"type":"text","text":"other"}]',/PROMPT/],
 ['native prompt changed',e=>e.native.parts[0].data='{"type":"text","text":"other"}',/NATIVE_PROMPT/],
 ['second user',e=>e.native.messages.push({...e.native.messages[0],id:'user2'}),/USER_MESSAGE_COUNT/],
 ['foreign child',e=>e.native.sessions.push({id:'child',parent_id:'root',directory:'/other'}),/CHILD_SCOPE/],
 ['unrelated session',e=>e.native.sessions.push({id:'unrelated',parent_id:null,directory:'/work'}),/CHILD_SCOPE/],
 ['live stream',e=>e.host.record.stream_id='active',/HOST_NOT_COMPLETE/],
 ['no final',e=>e.native.messages[1].data='{"role":"assistant"}',/FINAL_MESSAGE/],
 ['unfinished tool',e=>e.native.parts.push({id:'tool',message_id:'assistant',session_id:'root',data:'{"type":"tool","state":{"status":"running"}}'}),/TOOL_NOT_TERMINAL/],
 ['unknown runtime',e=>e.native.sessions[0].version='future',/SESSION_BINDING/],
 ['cross-session part',e=>e.native.parts[0].session_id='foreign',/PART_SCOPE/],
 ['unknown snapshot',e=>e.native.snapshot={...e.native.snapshot,method:'copy'},/SNAPSHOT_PROVENANCE/],
]) test(`engine evidence rejects ${label}`,()=>{const {evidence,options}=fixture();mutate(evidence);assert.throws(()=>verifyQwenEngineEvidence(evidence,options),error);});
