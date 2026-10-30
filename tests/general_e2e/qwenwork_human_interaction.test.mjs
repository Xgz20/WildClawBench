import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import test from 'node:test';
import {validateQwenCleanupCancellation} from '../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/human-interaction.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
const source=value=>({value,bytes:Buffer.from(JSON.stringify(value,null,2)+'\n')});
function fixture(){
 const paths=['/private/tmp/test'],identity={task_id:'task',execution_attempt_id:'attempt',host_session_id:'host',native_session_id:'native'};
 const before=source({task_id:'task',execution_attempt_id:'attempt',native_session_id:'native',native_pending_tool:{call_id:'call',native_part_id:'part'}});
 const authorization=source({schema_version:'wildclawbench.qwenwork-native-ui-interaction-authorization/v1',identity,action:'cancel-cleanup',authorization_source:'direct-user-question-reply-in-control-chat',user_answer:'Cancel cleanup',approved_targets:paths,native_call_id:'call',native_part_id:'part',prompt_resend_allowed:false,before_pending_sha256:sha(before.bytes)});
 const pre=JSON.stringify({type:'tool',tool:'qw-builtin_host_safe_delete',callID:'call',state:{status:'running',input:{items:paths.map(path=>({path}))}}});
 const post=JSON.stringify({type:'tool',tool:'qw-builtin_host_safe_delete',callID:'call',state:{status:'error',input:{items:paths.map(path=>({path}))},error:JSON.stringify({results:paths.map(path=>({path,status:'failed',errorCode:'PATH_NOT_AUTHORIZED'}))},null,2).replaceAll('\n','\\n')}});
 const invocation=source({native_call_id:'call',pre_click_native_part_data:pre,pre_click_native_part_sha256:sha(pre),ui_targets:paths,prompt_dispatch_operations:0});
 const receipt=source({schema_version:'wildclawbench.qwenwork-native-ui-interaction-receipt/v1',identity,action:'cancel-cleanup',native_call_id:'call',native_part_id:'part',approved_targets:paths,authorization:authorization.value,authorization_sha256:sha(authorization.bytes),invocation:invocation.value,invocation_sha256:sha(invocation.bytes),post_click_native_part_data:post,post_click_native_part_sha256:sha(post),prompt_dispatch_operations:0,human_assistance:{mode:'human_assisted',operation_count:1,semantic_intervention_count:0}});
 const state={identity:{task_id:'task',attempt_id:'attempt'},session:{session_id:'host'},human_assistance:{mode:'automatic',operation_count:0,semantic_intervention_count:0}};
 const nativeEvidence={host:{record:{session_id:'host',sub_chat_ext:JSON.stringify({engineSessionBindingV1:{nativeSessionId:'native'}})}},native:{parts:[{id:'part',session_id:'native',data:post}]}};
 return {receipt,authorization,invocation,before,state,nativeEvidence};
}
test('explicit user cancellation counts one mechanical intervention without modifying execution source',()=>{const f=fixture(),original=JSON.stringify(f.state);assert.deepEqual(validateQwenCleanupCancellation(f),{mode:'human_assisted',operation_count:1,semantic_intervention_count:0});assert.equal(JSON.stringify(f.state),original);});
for(const [name,change,error] of [
 ['missing direct user authority',f=>f.authorization.value.authorization_source='agent-assumption',/EXPLICIT_USER_CANCEL/],
 ['changed authorization bytes',f=>f.authorization.bytes=Buffer.from('drift'),/SOURCE_DIGEST/],
 ['foreign task',f=>f.state.identity.task_id='other',/IDENTITY/],
 ['foreign native root',f=>f.nativeEvidence.host.record.sub_chat_ext=JSON.stringify({engineSessionBindingV1:{nativeSessionId:'other'}}),/NATIVE_SESSION/],
 ['foreign native result',f=>f.nativeEvidence.native.parts[0].data+=' ',/NATIVE_TERMINAL/],
 ['different targets',f=>f.receipt.value.approved_targets=['/private/tmp/other'],/TARGET_SCOPE/],
 ['attempted prompt resend',f=>f.receipt.value.prompt_dispatch_operations=1,/INTERVENTION_SCOPE/],
 ['duplicate manual accounting',f=>f.state.human_assistance.operation_count=1,/BASE_ASSISTANCE/],
])test(`cancellation receipt rejects ${name}`,()=>{const f=fixture();change(f);assert.throws(()=>validateQwenCleanupCancellation(f),error);});
