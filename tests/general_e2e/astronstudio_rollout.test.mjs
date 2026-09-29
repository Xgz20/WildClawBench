import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { analyzeRollout, createRolloutSupplement, verifyRolloutSupplement } from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const state={identity:{batch_id:'b',unit_id:'u',task_id:'t',attempt_id:'a'},phase:'COMPLETED',harness:{id:'astronstudio'},
  prompt:{send_status:'sent',sha256:sha('task prompt')},session:{session_id:'s',turn_id:'t1',cwd:'/task',verified:true}};
const usage=n=>({input_tokens:10*n,cached_input_tokens:4*n,output_tokens:2*n,reasoning_output_tokens:n,total_tokens:12*n});
const event=(type,payload)=>({type,payload});
const token=(total,last=1)=>event('event_msg',{type:'token_count',info:{total_token_usage:usage(total),last_token_usage:usage(last)}});
function fixture(){return [
  event('session_meta',{id:'s',cwd:'/task'}),
  event('event_msg',{type:'task_started',turn_id:'old'}),token(2,2),
  event('response_item',{type:'function_call',call_id:'old',name:'read',arguments:'{}'}),
  event('event_msg',{type:'task_started',turn_id:'t1'}),event('turn_context',{turn_id:'t1',cwd:'/task'}),
  event('event_msg',{type:'user_message',message:'task prompt'}),
  event('response_item',{type:'function_call',call_id:'read',name:'read',arguments:'{"path":"a"}'}),
  event('response_item',{type:'function_call_output',call_id:'read',output:'content'}),
  event('response_item',{type:'function_call',call_id:'bash',name:'bash',arguments:'{"command":"cat a"}'}),
  event('response_item',{type:'function_call',call_id:'exec',name:'exec_command',arguments:'{}'}),
  event('response_item',{type:'custom_tool_call',call_id:'write',name:'write',input:'content'}),
  event('response_item',{type:'tool_search_call',call_id:'search',id:'search',execution:'client',status:'completed',arguments:{query:'browser'}}),
  event('response_item',{type:'tool_search_output',call_id:'search',tools:[]}),token(3),token(3),token(4),
  event('event_msg',{type:'task_complete',turn_id:'t1'}),
];}
const bytes=rows=>Buffer.from(rows.map(JSON.stringify).join('\n')+'\n');
test('rollout keeps real names, includes native tool search, excludes results and prior turns',()=>{
  const r=analyzeRollout(bytes(fixture()),state);
  assert.deepEqual(r.tool_counts.by_tool,{read:1,bash:1,exec_command:1,write:1,tool_search:1});
  assert.equal(r.tool_counts.total,5);assert.equal(r.metrics.requests.request_count.value,2);
  assert.equal(r.usage_reconciliation.repeated_snapshots,1);assert.equal(r.metrics.requests.request_attempt_count.value,null);
  assert.equal(r.usage_reconciliation.summed_usage.total_tokens,24);
});
test('rollout deduplicates exact call replays but rejects same ID with different name/arguments',()=>{
  const rows=fixture();rows.splice(9,0,structuredClone(rows[7]));assert.equal(analyzeRollout(bytes(rows),state).tool_counts.total,5);
  rows[9].payload.name='write';assert.throws(()=>analyzeRollout(bytes(rows),state),/CALL_ID_CONFLICT/);
});
for(const [label,change,code] of [
  ['session',r=>r[0].payload.id='other',/SESSION_MISMATCH/],
  ['cwd',r=>r[5].payload.cwd='/other',/CWD_MISMATCH/],
  ['prompt',r=>r[6].payload.message='another task',/PROMPT_MISMATCH/],
  ['turn',r=>r[7].payload.internal_chat_message_metadata_passthrough={turn_id:'other'},/ITEM_TURN_MISMATCH/],
  ['terminal',r=>r.pop(),/NOT_TERMINAL/],
  ['unknown builtin',r=>r[7].payload.type='new_provider_call',/TYPE_UNSUPPORTED/],
])test('rollout rejects '+label+' drift',()=>{const rows=fixture();change(rows);assert.throws(()=>analyzeRollout(bytes(rows),state),code);});
test('unreconciled usage does not publish a complete request total',()=>{
  const rows=fixture();rows[16]=token(5);const r=analyzeRollout(bytes(rows),state);
  assert.equal(r.metrics.requests.request_count.value,null);assert.equal(r.collection.known_subtotals.request_count,2);
  assert.equal(r.tool_counts.total,5);
});
test('failed native terminal retains tool call intents without inventing successes',()=>{
  const rows=fixture();rows[17]=event('event_msg',{type:'error',message:'native turn failed'});
  assert.equal(analyzeRollout(bytes(rows),{...state,phase:'FAILED'}).tool_counts.total,5);
});
test('immutable rollout supplement recomputes and rejects raw/summary tampering',async()=>{
  const root=await mkdtemp(join(tmpdir(),'astron-rollout-test-'));
  try{
    const ep=join(root,'execution.json'),sp=join(root,'state.json'),rp=join(root,'rollout.jsonl'),out=join(root,'supplement');
    await writeFile(ep,JSON.stringify(state));await writeFile(sp,JSON.stringify(state));await writeFile(rp,bytes(fixture()));
    const r=await createRolloutSupplement({executionRecord:ep,stateFile:sp,rolloutFile:rp,outputDir:out});assert.equal(r.tool_counts.total,5);
    assert.equal((await verifyRolloutSupplement({directory:out,executionRecord:ep})).status,'PASS');
    await assert.rejects(createRolloutSupplement({executionRecord:ep,stateFile:sp,rolloutFile:rp,outputDir:out}),/EXISTS/);
    const native=join(out,'raw/astronstudio-rollout.jsonl');await writeFile(native,(await readFile(native)).toString().replace('"read"','"edit"'));
    await assert.rejects(verifyRolloutSupplement({directory:out,executionRecord:ep}),/SHA_MISMATCH/);
  }finally{await rm(root,{recursive:true,force:true});}
});
