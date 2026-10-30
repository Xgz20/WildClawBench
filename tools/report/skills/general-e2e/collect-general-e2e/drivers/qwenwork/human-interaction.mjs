import {createHash} from 'node:crypto';
const sha=x=>createHash('sha256').update(x).digest('hex');
const require=(condition,message)=>{if(!condition)throw Error('QWEN_HUMAN_INTERACTION_'+message);};
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function validateQwenCleanupCancellation({receipt,authorization,invocation,before,state,nativeEvidence}) {
  const r=receipt.value,a=authorization.value,i=invocation.value,b=before.value;
  require(r.schema_version==='wildclawbench.qwenwork-native-ui-interaction-receipt/v1'
    && a.schema_version==='wildclawbench.qwenwork-native-ui-interaction-authorization/v1','SCHEMA_INVALID');
  require(r.action==='cancel-cleanup'&&a.action===r.action
    &&a.authorization_source==='direct-user-question-reply-in-control-chat'
    &&typeof a.user_answer==='string'&&a.user_answer.trim(),'EXPLICIT_USER_CANCEL_REQUIRED');
  require(r.authorization_sha256===sha(authorization.bytes)&&r.invocation_sha256===sha(invocation.bytes)
    &&a.before_pending_sha256===sha(before.bytes)&&equal(r.authorization,a)&&equal(r.invocation,i),'SOURCE_DIGEST_MISMATCH');
  const identity=a.identity;
  require(equal(r.identity,identity)&&identity.task_id===state.identity.task_id
    &&identity.execution_attempt_id===state.identity.attempt_id
    &&identity.host_session_id===state.session.session_id
    &&b.task_id===identity.task_id&&b.execution_attempt_id===identity.execution_attempt_id
    &&b.native_session_id===identity.native_session_id,'IDENTITY_MISMATCH');
  const host=nativeEvidence.host.record,binding=JSON.parse(host.sub_chat_ext).engineSessionBindingV1;
  require(binding.nativeSessionId===identity.native_session_id&&host.session_id===identity.host_session_id,'NATIVE_SESSION_MISMATCH');
  require(r.native_call_id===a.native_call_id&&r.native_part_id===a.native_part_id
    &&i.native_call_id===a.native_call_id&&b.native_pending_tool.call_id===a.native_call_id
    &&b.native_pending_tool.native_part_id===a.native_part_id,'CALL_IDENTITY_MISMATCH');
  const pre=JSON.parse(i.pre_click_native_part_data),post=JSON.parse(r.post_click_native_part_data);
  require(sha(i.pre_click_native_part_data)===i.pre_click_native_part_sha256
    &&sha(r.post_click_native_part_data)===r.post_click_native_part_sha256,'NATIVE_DATA_DIGEST_MISMATCH');
  const matches=nativeEvidence.native.parts.filter(x=>x.id===a.native_part_id&&x.session_id===identity.native_session_id);
  require(matches.length===1&&sha(matches[0].data)===r.post_click_native_part_sha256,'NATIVE_TERMINAL_RESULT_MISMATCH');
  const targets=a.approved_targets;
  require(Array.isArray(targets)&&targets.length>0&&new Set(targets).size===targets.length
    &&targets.every(x=>typeof x==='string'&&x.startsWith('/'))
    &&equal(r.approved_targets,targets)&&equal(i.ui_targets,targets)
    &&equal(pre.state?.input?.items?.map(x=>x.path),targets)
    &&equal(post.state?.input?.items?.map(x=>x.path),targets),'TARGET_SCOPE_MISMATCH');
  require(pre.type==='tool'&&post.type==='tool'&&pre.tool==='qw-builtin_host_safe_delete'
    &&post.tool===pre.tool&&pre.callID===a.native_call_id&&post.callID===a.native_call_id
    &&pre.state.status==='running'&&post.state.status==='error','CANCELLATION_NOT_CONFIRMED');
  let result;try{result=JSON.parse(post.state.error);}catch{try{result=JSON.parse(post.state.error.replace(/\\n/gu,'\n'));}catch{throw Error('QWEN_HUMAN_INTERACTION_NATIVE_DENIAL_INVALID');}}
  require(Array.isArray(result?.results)&&result.results.length===targets.length
    &&equal(result.results.map(x=>x.path),targets)
    &&result.results.every(x=>x.status==='failed'&&x.errorCode==='PATH_NOT_AUTHORIZED'),'NATIVE_DENIAL_INVALID');
  require(r.prompt_dispatch_operations===0&&i.prompt_dispatch_operations===0&&a.prompt_resend_allowed===false
    &&r.human_assistance?.mode==='human_assisted'&&r.human_assistance.operation_count===1
    &&r.human_assistance.semantic_intervention_count===0,'INTERVENTION_SCOPE_INVALID');
  require(state.human_assistance?.mode==='automatic'&&state.human_assistance.operation_count===0
    &&state.human_assistance.semantic_intervention_count===0,'BASE_ASSISTANCE_UNSUPPORTED');
  return {mode:'human_assisted',operation_count:1,semantic_intervention_count:0};
}
