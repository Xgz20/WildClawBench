// Retain conflicting native/SDK finals. This profile never repairs an answer.
import { createHash } from 'node:crypto';
import { readFile, lstat, realpath } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { analyzeRollout, ROLLOUT_PATH } from './astronstudio-rollout.mjs';
export const FINAL_PREFIX_PROFILE='bound-native-final-prefix-divergence/v1';
export const FINAL_PREFIX_STATE='bindings/final-prefix-original-state.json';
export const FINAL_PREFIX_NATIVE='bindings/final-prefix-native-projection.json';
export const FINAL_PREFIX_TEXT='bindings/final-prefix-original-response.txt';
export const FINAL_PREFIX_PROOF='bindings/final-prefix-divergence-proof.json';
export const FINAL_SUFFIX_PROFILE='bound-native-final-suffix-divergence/v1';
export const FINAL_SUFFIX_STATE='bindings/final-suffix-original-state.json';
export const FINAL_SUFFIX_NATIVE='bindings/final-suffix-native-projection.json';
export const FINAL_SUFFIX_TEXT='bindings/final-suffix-original-response.txt';
export const FINAL_SUFFIX_PROOF='bindings/final-suffix-divergence-proof.json';
const sha=b=>createHash('sha256').update(b).digest('hex');
const ensure=(ok,code)=>{if(!ok)throw Error('FINAL_PREFIX_'+code);};
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'
  ?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
function deriveFinalFragment(stateBytes,index,sdkBytes,native,finalBytes,suffix){
 const state=JSON.parse(stateBytes),s=state.session;
 ensure(state.phase==='COMPLETED'&&state.execution.business_status==='completed'&&s.verified===true
  &&s.native_status==='completed'&&state.prompt.send_status==='sent'&&state.send.dispatch_attempt_count===1,'STATE_UNBOUND');
 ensure(same(index.identity,state.identity)&&['thread_id','turn_id','session_id','cwd'].every(k=>index.session?.[k]===s[k])
  &&index.canonical_source_policy?.id==='bound-native-sdk-canonical/v1','INDEX_UNBOUND');
 ensure(sha(finalBytes)===state.evidence.final_response_sha256,'ORIGINAL_FINAL_DRIFT');
 ensure(native?.thread_id===s.thread_id&&native.turn_id===s.turn_id&&native.latest_turn_id===s.turn_id
  &&native.turn_state==='completed'&&native.role==='assistant'&&native.is_streaming===0
  &&native.message_id===native.assistant_message_id&&typeof native.text==='string'
  &&finalBytes.toString('utf8')===native.text+'\n'&&resolve(native.cwd)===resolve(s.cwd),'NATIVE_UNBOUND');
 analyzeRollout(sdkBytes,state);
 const rows=sdkBytes.toString('utf8').split('\n').filter(x=>x.trim()).map(JSON.parse);
 const complete=rows.filter(r=>r.type==='event_msg'&&r.payload?.type==='task_complete'&&r.payload.turn_id===s.turn_id);
 ensure(complete.length===1&&typeof complete[0].payload.last_agent_message==='string','SDK_NOT_COMPLETED');
 const final=complete[0].payload.last_agent_message;
 const messages=rows.filter(r=>r.type==='response_item'&&r.payload?.type==='message'&&r.payload.role==='assistant'
  &&'assistant:'+r.payload.id===native.message_id);
 ensure(messages.length===1&&messages[0].payload.internal_chat_message_metadata_passthrough?.turn_id===s.turn_id,'SDK_MESSAGE_UNBOUND');
 const content=messages[0].payload.content;
 ensure(Array.isArray(content)&&content.every(x=>x.type==='output_text'&&typeof x.text==='string')
  &&content.map(x=>x.text).join('')===final,'SDK_FINAL_MISMATCH');
 ensure(native.text.length>0&&final.length>native.text.length
  &&(suffix?final.endsWith(native.text):final.startsWith(native.text)),suffix?'NOT_STRICT_SUFFIX':'NOT_STRICT_PREFIX');
 return {profile:suffix?FINAL_SUFFIX_PROFILE:FINAL_PREFIX_PROFILE,identity:state.identity,session:Object.fromEntries(['thread_id','turn_id','session_id','cwd'].map(k=>[k,s[k]])),
  source_state_sha256:sha(stateBytes),sdk_sha256:sha(sdkBytes),native_projection_sha256:sha(Buffer.from(JSON.stringify(canonical(native)))),
  original_final_sha256:sha(finalBytes),native_text_length:native.text.length,sdk_text_length:final.length,
  sdk_final_sha256:sha(Buffer.from(final)),native_message_id:native.message_id,native_projection_preserved:true,
  sdk_final_not_substituted:true,scoreability:'unchanged-contract-evidence-policy',scoring_rules_changed:false};
}
export function deriveFinalPrefix(...args){return deriveFinalFragment(...args,false);}
export function deriveFinalSuffix(...args){return deriveFinalFragment(...args,true);}
export async function verifyFinalPrefix(index,stateBytes,traceRoot,execution=undefined){
 const refs=index.binding_evidence??[];
 const prefixNames=[FINAL_PREFIX_STATE,FINAL_PREFIX_NATIVE,FINAL_PREFIX_TEXT,FINAL_PREFIX_PROOF];
 const suffixNames=[FINAL_SUFFIX_STATE,FINAL_SUFFIX_NATIVE,FINAL_SUFFIX_TEXT,FINAL_SUFFIX_PROOF];
 const suffix=Boolean(index.native_final_suffix_divergence_profile||refs.some(r=>suffixNames.includes(r.path)));
 if(!suffix&&!index.native_final_prefix_divergence_profile&&!refs.some(r=>prefixNames.includes(r.path)))return null;
 const names=suffix?suffixNames:prefixNames;
 ensure(suffix?index.native_final_suffix_divergence_profile?.id===FINAL_SUFFIX_PROFILE
  &&!index.native_final_prefix_divergence_profile&&!refs.some(r=>prefixNames.includes(r.path))
  :index.native_final_prefix_divergence_profile?.id===FINAL_PREFIX_PROFILE,'DECLARATION_INVALID');
 async function bound(path){
  const matches=[...(index.raw_trace??[]),...refs].filter(r=>r.path===path);ensure(matches.length===1,'ARTIFACT_AMBIGUOUS');
  const file=resolve(traceRoot,path),info=await lstat(file);
  ensure(file.startsWith(resolve(traceRoot)+sep)&&info.isFile()&&!info.isSymbolicLink()&&info.size<=64*1024*1024,'ARTIFACT_INVALID');
  ensure((await realpath(file)).startsWith((await realpath(traceRoot))+sep),'ARTIFACT_ESCAPE');
  const b=await readFile(file);ensure(b.length===matches[0].size&&sha(b)===matches[0].sha256,'ARTIFACT_DRIFT');return b;
 }
 const original=await bound(names[0]);ensure(original.equals(stateBytes),'STATE_DRIFT');
 const native=JSON.parse(await bound(names[1])),final=await bound(names[2]),sdk=await bound(ROLLOUT_PATH);
 const proof=JSON.parse(await bound(names[3]));ensure(same(proof,deriveFinalFragment(original,index,sdk,native,final,suffix)),'PROOF_DRIFT');
 ensure(index.completeness?.status==='partial'&&index.completeness.missing?.includes(suffix?'native-final-suffix-divergence':'native-final-prefix-divergence'),'NOT_EXPLICIT_PARTIAL');
 if(execution)ensure(same(execution.identity,proof.identity)&&execution.execution.business_status==='completed','RECORD_MISMATCH');
 return proof;
}
