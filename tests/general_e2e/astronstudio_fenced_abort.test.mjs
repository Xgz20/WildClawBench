import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {rejectionFixture} from './fixtures/native-start-rejection.mjs';
import {verifyNativeStartRejection,FENCED_ABORT_REJECTION_PROFILE} from '../../tools/report/e2e-shared/astronstudio-start-rejection/index.mjs';
import {readAdapterAttestation,PRETRANSPORT_ABORT_SOURCE,ADAPTER_ATTESTATION} from '../../tools/report/e2e-shared/astronstudio-start-rejection/adapter-attestation.mjs';

function fixture(){
 const f=rejectionFixture(),runtime=f.data.provider_session_runtime[0];
 f.state.client.version='3.6.4';
 const detail=f.data.projection_thread_sessions[0].last_error.replace('ACode','Acode');
 f.data.projection_thread_sessions[0].last_error=detail;
 const failed=JSON.parse(f.data.orchestration_events[2].payload_json);failed.activity.payload.detail=detail;
 f.data.orchestration_events[2].payload_json=JSON.stringify(failed);
 runtime.status='running';runtime.provider_name='acode';runtime.adapter_key='acode';runtime.runtime_mode='full-access';
 runtime.lifecycle_generation='epoch';runtime.resume_cursor_json=JSON.stringify({threadId:'sdk',emptyPrewarm:true});
 runtime.runtime_payload_json=JSON.stringify({activeTurnId:null,contextRecovery:null,cwd:f.config.candidateWorkspace,
  emptyPrewarmDispatch:null,inlineVisualTool:true,lastError:null,lastRuntimeEvent:'session.state.changed',
  lastRuntimeEventAt:'2026-11-06T06:28:30Z',lifecycleGeneration:'epoch',model:'spark-x2.6',
  modelSelection:JSON.parse(f.data.projection_threads[0].model_selection_json),providerOptions:{acode:{}},workspaceKind:'project'});
 f.data.orchestration_event_deliveries[0].submission_state='possibly-submitted-v1';
 f.data.native_adapter_source={schema_version:ADAPTER_ATTESTATION,app_path:'/Applications/AStudio.app',
  asar_size:194202339,asar_inode:'12345',asar_modified_at:'2026-11-01T00:00:00Z',observed_at:'2026-11-06T06:30:00Z',
  server_entry:'apps/server/dist/index.mjs',server_entry_sha256:PRETRANSPORT_ABORT_SOURCE,
  main_process:{pid:7,started_at:'2026-11-02T00:00:00Z',executable_path:'/Applications/AStudio.app/Contents/MacOS/AStudio',command_sha256:'c'.repeat(64)},
  asar_header_sha256:'b'.repeat(64),source_executed:false,native_files_modified:false};
 return f;
}
const verify=f=>verifyNativeStartRejection(f.data,f.state,f.config);
test('the source-attested fenced callback preserves the conservative ledger and assigns no score',()=>{
 const f=fixture(),before=JSON.stringify(f),proof=verify(f);
 assert.equal(proof.profile,FENCED_ABORT_REJECTION_PROFILE);
 assert.equal(proof.original_submission_ledger_state,'possibly-submitted-v1');
 assert.equal(proof.submission_ledger_modified,false);assert.equal(proof.native_turn_id,null);
 assert.equal('score' in proof,false);assert.equal(JSON.stringify(f),before);
});
test('unknown sources, unsafe clocks, live turns and unclosed state remain rejected',()=>{
 const cases=[
  f=>delete f.data.native_adapter_source,
  f=>{f.data.native_adapter_source.server_entry_sha256='0'.repeat(64);},
  f=>{f.data.native_adapter_source.asar_modified_at='2026-11-07T00:00:00Z';},
  f=>{f.data.native_adapter_source.source_executed=true;},
  f=>{delete f.data.native_adapter_source.main_process;},
  f=>{f.data.native_adapter_source.main_process.started_at='2026-11-07T00:00:00Z';},
  f=>{f.state.client.version='3.6.0';},
  f=>{f.data.projection_turns.push({turn_id:'late-model-turn'});},
  f=>{f.data.projection_pending_interactions.push({status:'pending'});},
  f=>{f.data.orchestration_event_deliveries[0].state='inflight';},
  f=>{f.data.orchestration_event_deliveries[0].claim_owner='live';},
  f=>{const p=JSON.parse(f.data.provider_session_runtime[0].runtime_payload_json);p.activeTurnId='live';f.data.provider_session_runtime[0].runtime_payload_json=JSON.stringify(p);},
  f=>{const p=JSON.parse(f.data.provider_session_runtime[0].runtime_payload_json);p.unknownField=null;f.data.provider_session_runtime[0].runtime_payload_json=JSON.stringify(p);},
  f=>{f.data.provider_session_runtime[0].resume_cursor_json=JSON.stringify({threadId:'sdk',emptyPrewarm:false});},
  f=>{f.data.orchestration_events[2].payload_json=JSON.stringify({activity:{kind:'provider.turn.start.failed',payload:{detail:'unrelated timeout'}}});},
 ];
 for(const [i,change] of cases.entries()){const f=fixture();change(f);assert.throws(()=>verify(f),undefined,`case ${i}`);}
});
test('attestation does not execute or accept an unknown native archive',async()=>{
 const root=await mkdtemp(join(tmpdir(),'fenced-asar-'));
 try {await mkdir(join(root,'Contents/Resources'),{recursive:true});await writeFile(join(root,'Contents/Resources/app.asar'),'unknown');
  assert.equal(await readAdapterAttestation(root),null);assert.equal(await readAdapterAttestation(undefined),null);
 }finally{await rm(root,{recursive:true,force:true});}
});
