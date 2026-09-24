import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { captureQwenSessionSnapshot, verifyQwenSessionSnapshot } from '../../tools/report/e2e-shared/qwenwork-native-state/index.mjs';
import { verifyQwenNativeTerminal } from '../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/terminal-gate.mjs';
import { buildQwenStrictResourceMetrics } from '../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/native-normalizer.mjs';
import { QWENWORK_MACOS_1_2_0_TOKEN_PROFILE } from '../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/token-profile.mjs';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function seal(snapshot) { const { payload_sha256, ...payload } = snapshot; return { ...payload, payload_sha256: sha(JSON.stringify(payload)) }; }
async function fixture(t) {
 const root=await realpath(await mkdtemp(join(tmpdir(),'qwen-interruption-')));t.after(()=>rm(root,{recursive:true,force:true}));
 const db=join(root,'agents.db'),workspace=join(root,'workspace');await mkdir(workspace);
 const quote=s=>"'"+s.replaceAll("'","''")+"'";
 execFileSync('/usr/bin/sqlite3',[db,`CREATE TABLE local_projects(id TEXT,name TEXT,root_paths TEXT);
 CREATE TABLE projects(id TEXT,path TEXT);
 CREATE TABLE chats(id TEXT,local_project_id TEXT,project_id TEXT,worktree_path TEXT,ext TEXT,deleted_at TEXT);
 CREATE TABLE sub_chats(id TEXT,chat_id TEXT,name TEXT,session_id TEXT,stream_id TEXT,model_level TEXT,updated_at INT,created_at INT);
 INSERT INTO local_projects VALUES('project','fixture',${quote(JSON.stringify([workspace]))});
 INSERT INTO chats VALUES('chat','project',NULL,NULL,'{"taskStatus":"interrupted"}',NULL);
 INSERT INTO sub_chats VALUES('sub','chat','task','session-native',NULL,'flash',1,1);`]);
 const state={phase:'FAILED',session:{session_id:'session-native',cwd:workspace},execution:{business_status:'infrastructure_error',error:{code:'QWENWORK_INTERRUPTED'},finished_at:new Date(Date.now()-1000).toISOString(),duration_seconds:7},
  extensions:{qwenwork:{native_status:'interrupted',conversation_id:'chat',sub_chat_id:'sub',local_project_id:'project'}}};
 return {db,workspace,state};
}
test('A readonly SQLite snapshot corroborates interruption without synthesizing a native finish',async t=>{
 const f=await fixture(t),before=await readFile(f.db),snapshot=await captureQwenSessionSnapshot({databasePath:f.db,sessionId:'session-native',workspace:f.workspace});
 assert.equal(sha(await readFile(f.db)),sha(before));assert.equal(verifyQwenSessionSnapshot(snapshot,f.state).native_status,'interrupted');
 const rows=[{type:'turn.started',turn_id:'native-turn',data:{is_subagent:false}}];
 const proof=verifyQwenNativeTerminal(f.state,rows,{nativeSnapshot:snapshot});assert.equal(proof.finish_reason,null);assert.equal(proof.native_finish_present,false);assert.equal(rows.length,1);
 assert.throws(()=>verifyQwenNativeTerminal(f.state,rows),/SNAPSHOT_REQUIRED/);
 const success=structuredClone(f.state);success.phase='COMPLETED';success.execution.business_status='completed';
 assert.throws(()=>verifyQwenNativeTerminal(success,rows,{nativeSnapshot:snapshot}),/FINISH_UNVERIFIED/);
 for(const change of [x=>x.record.native_status='completed',x=>x.record.stream_id='still-active',x=>x.record.cwd='/other',x=>x.record.sub_chat_id='other',x=>x.method='copy-live-db',x=>x.observed_at='2000-01-01T00:00:00Z']){
  const bad=structuredClone(snapshot);change(bad);assert.throws(()=>verifyQwenSessionSnapshot(seal(bad),f.state),/SNAPSHOT_/);
 }
});
test('Missing native finish withholds resource totals and agent duration while preserving verified subtotals',()=>{
 const state={identity:{batch_id:'b',unit_id:'u',task_id:'t',attempt_id:'a'},execution:{business_status:'infrastructure_error',error:{code:'QWENWORK_INTERRUPTED'},duration_seconds:7},extensions:{qwenwork:{native_terminal_reconciliation:{mode:'native-interruption-without-finish',verified:true}}}};
 const rows=[{type:'turn.started',turn_id:'turn',data:{}},{type:'model.request.started',turn_id:'turn',request_id:'r1'},
  {type:'model.response.completed',turn_id:'turn',request_id:'r1',data:{provider:'qoder',input_tokens:100,output_tokens:20,cache_read_input_tokens:80}},
  {type:'model.request.started',turn_id:'turn',request_id:'r2'},{type:'tool.requested',turn_id:'turn',tool_call_id:'call'}];
 const metrics=buildQwenStrictResourceMetrics({state,segmentRows:rows,sources:[{path:'raw/events',sha256:'a'.repeat(64),size:1}],collectedAt:new Date().toISOString(),tokenProfile:QWENWORK_MACOS_1_2_0_TOKEN_PROFILE});
 assert.equal(metrics.metrics.timing.agent_duration_seconds.value,null);assert.equal(metrics.metrics.requests.request_count.value,null);assert.equal(metrics.metrics.tools.call_count.value,null);assert.equal(metrics.metrics.usage.total_tokens.value,null);
 assert.deepEqual(metrics.collection.known_subtotals,{request_count:2,call_count:1,input_tokens:100,output_tokens:20,cache_read_input_tokens:80,total_tokens:120});
 assert.equal(metrics.collection.coverage.request_count.total,null);assert.equal(metrics.collection.coverage.input_tokens.total,null);
 const orphaned=structuredClone(rows);orphaned[2].request_id='unknown-request';
 const orphanMetrics=buildQwenStrictResourceMetrics({state,segmentRows:orphaned,sources:[],collectedAt:new Date().toISOString(),tokenProfile:QWENWORK_MACOS_1_2_0_TOKEN_PROFILE});
 assert.equal(orphanMetrics.collection.known_subtotals.total_tokens,undefined);
 const wrongProfile=buildQwenStrictResourceMetrics({state,segmentRows:rows,sources:[],collectedAt:new Date().toISOString(),tokenProfile:{id:'unknown'}});
 assert.equal(wrongProfile.collection.known_subtotals.total_tokens,undefined);
 state.execution.duration_seconds=null;
 const missingDuration=buildQwenStrictResourceMetrics({state,segmentRows:rows,sources:[],collectedAt:new Date().toISOString()});
 assert.equal(missingDuration.metrics.timing.duration_seconds.value,null);
 delete state.extensions.qwenwork.native_terminal_reconciliation;
 assert.throws(()=>buildQwenStrictResourceMetrics({state,segmentRows:rows,sources:[],collectedAt:new Date().toISOString()}),/FINISH_COUNT/);
});
