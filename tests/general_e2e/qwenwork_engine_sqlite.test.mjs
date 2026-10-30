import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import test from 'node:test';
import {QWEN_ENGINE_PROFILE,verifyQwenEngineEvidence} from '../../tools/report/e2e-shared/qwenwork-native-state/engine-sqlite.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
import {fixture} from './fixtures/qwenwork/engine-evidence.mjs';
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

import {selectQwenSessionForAttempt} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/session-state.mjs';
import {verifyQwenSessionPromptEvidence} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs';
test('session selection retains the authoritative engine route through recovery projection',async()=>{
 const row={session_id:'host',conversation_id:'chat',sub_chat_id:'sub',local_project_id:'project',cwd:'/work',native_status:'running',stream_id:'stream',created_at_ms:1000,sub_chat_ext:JSON.stringify({engineSessionBindingV1:{engineId:'opencode'}})};
 const selected=selectQwenSessionForAttempt({sessions:[row],workspace:'/work',nativeBinding:{session_id:'host',conversation_id:'chat',sub_chat_id:'sub',local_project_id:'project'}});
 assert.equal(selected.sub_chat_ext,row.sub_chat_ext);
 await assert.rejects(verifyQwenSessionPromptEvidence({traceRoot:'/unused',session:selected,prompt:{sha256:sha('prompt')}}),/ENGINE_PROFILE_CONTEXT_REQUIRED/);
});
