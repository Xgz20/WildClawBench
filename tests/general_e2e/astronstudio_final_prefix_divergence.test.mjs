import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import {deriveFinalPrefix,FINAL_PREFIX_PROFILE} from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-final-prefix-divergence.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
function fixture(){
 const id={batch_id:'batch',unit_id:'unit',task_id:'task',attempt_id:'attempt'};
 const session={thread_id:'thread',turn_id:'turn',session_id:'sdk',cwd:'/workspace',verified:true,native_status:'completed'};
 const final=Buffer.from('Native prefix\n'),full='Native prefix and full SDK continuation';
 const state={identity:id,session,phase:'COMPLETED',execution:{business_status:'completed'},prompt:{send_status:'sent',sha256:sha('prompt')},
  send:{dispatch_attempt_count:1},evidence:{final_response_sha256:sha(final)}};
 const sdk=Buffer.from([{type:'session_meta',payload:{id:'sdk',cwd:'/workspace'}},
  {type:'event_msg',payload:{type:'task_started',turn_id:'turn'}},{type:'event_msg',payload:{type:'user_message',message:'prompt'}},
  {type:'response_item',payload:{type:'message',id:'message',role:'assistant',content:[{type:'output_text',text:full}],internal_chat_message_metadata_passthrough:{turn_id:'turn'}}},
  {type:'event_msg',payload:{type:'task_complete',turn_id:'turn',last_agent_message:full}}].map(JSON.stringify).join('\n')+'\n');
 const native={thread_id:'thread',turn_id:'turn',latest_turn_id:'turn',turn_state:'completed',role:'assistant',is_streaming:0,
  message_id:'assistant:message',assistant_message_id:'assistant:message',text:'Native prefix',cwd:'/workspace'};
 return{state,final,sdk,native,index:{identity:id,session,canonical_source_policy:{id:'bound-native-sdk-canonical/v1'}}};
}
const derive=f=>deriveFinalPrefix(Buffer.from(JSON.stringify(f.state)),f.index,f.sdk,f.native,f.final);
test('prefix divergence retains the native response without upgrading it to the SDK answer',()=>{
 const f=fixture(),before=Buffer.from(f.final),p=derive(f);
 assert.equal(p.profile,FINAL_PREFIX_PROFILE);assert.equal(p.sdk_final_not_substituted,true);
 assert.equal(p.native_projection_preserved,true);assert.equal(p.scoreability,'unchanged-contract-evidence-policy');
 assert.deepEqual(f.final,before);assert.equal(p.original_final_sha256,sha(before));
});
test('unknown message binding, active projections, non-prefix bodies and extra sends are rejected',()=>{
 for(const patch of [{latest_turn_id:'other'},{is_streaming:1},{message_id:'assistant:other'},{cwd:'/other'}]){
  const f=fixture();Object.assign(f.native,patch);assert.throws(()=>derive(f),/NATIVE_UNBOUND|SDK_MESSAGE_UNBOUND/);
 }
 const different=fixture();different.native.text='unrelated';different.final=Buffer.from('unrelated\n');
 different.state.evidence.final_response_sha256=sha(different.final);assert.throws(()=>derive(different),/NOT_STRICT_PREFIX/);
 const twice=fixture();twice.state.send.dispatch_attempt_count=2;assert.throws(()=>derive(twice),/STATE_UNBOUND/);
 const modified=fixture();modified.final=Buffer.from('changed');assert.throws(()=>derive(modified),/ORIGINAL_FINAL_DRIFT/);
});
