import test from 'node:test';import assert from 'node:assert/strict';
import {normalizeQwenSqliteSnapshot} from '../../eval_memory_e2e/native/qwenwork.mjs';
import {sha} from '../../eval_memory_e2e/native/common.mjs';
const session={session_id:'s',sub_chat_id:'sub',conversation_id:'chat',local_project_id:'p',cwd:'/owned'};
const snapshot=()=>({source_kind:'qwen-native-sqlite-sdk-projection/v1',identity:{...session,native_status:'completed',stream_id:null},
  messages:[{sub_chat_id:'sub',chat_id:'chat',message_id:'native-user',role:'user',parts:JSON.stringify([{type:'text',text:'owned prompt'}]),metadata:JSON.stringify({source:'sdk-projection',sessionId:'s'})},
    {sub_chat_id:'sub',chat_id:'chat',message_id:'native-assistant',role:'assistant',parts:JSON.stringify([{type:'text',text:'result'}]),metadata:JSON.stringify({sessionId:'s'})}],
  trajectory:[{sub_chat_id:'sub',event_type:'turn_end'}]});
test('native SQLite projection binds original IDs/prompt/cwd and does not claim a legacy JSONL source',()=>{
  const value=normalizeQwenSqliteSnapshot(snapshot(),session,sha('owned prompt'));
  assert.equal(value.user.uuid,'native-user');assert.equal(value.terminal,true);
  assert.equal(value.rows[0].source_kind,'qwen-native-sqlite-sdk-projection/v1');
});
test('another workspace/session/prompt, duplicate user and foreign trajectory are rejected',()=>{
  for(const change of [s=>s.identity.cwd='/other',s=>s.identity.session_id='other',s=>s.messages[0].metadata='{}',
    s=>s.messages[0].parts='[{"type":"text","text":"other"}]',s=>s.messages.push({...s.messages[0]}),
    s=>s.trajectory[0].sub_chat_id='other']){
    const s=snapshot();change(s);assert.throws(()=>normalizeQwenSqliteSnapshot(s,session,sha('owned prompt')));
  }
});
test('a running stream or absent native end event cannot prove completion',()=>{
  for(const change of [s=>s.identity.stream_id='active',s=>s.trajectory=[]]){
    const s=snapshot();change(s);assert.equal(normalizeQwenSqliteSnapshot(s,session,sha('owned prompt')).terminal,false);
  }
});
