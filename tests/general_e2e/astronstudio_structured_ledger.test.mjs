import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import test from 'node:test';
import {closedStructuredGatewayLedger} from '../../tools/report/e2e-shared/astronstudio-runtime/structured-ledger.mjs';
import {queryNativeRuntimeSafety} from '../../tools/report/e2e-shared/astronstudio-runtime/state.mjs';
import {nativeSafetyBlockers} from '../../tools/report/e2e-shared/astronstudio-runtime/guard.mjs';

function fixture() {
  const thread = 'structured-11111111-1111-4111-8111-111111111111';
  const turn = '22222222-2222-4222-8222-222222222222';
  const request = {requestId:'44444444-4444-4444-8444-444444444444', routeId:'builtin/model',
    modelSource:'builtin', requestedModel:'model', status:'started'};
  const completed = {...request, status:'completed', effectiveModel:'model', responseId:'response',
    requestKind:'turn', usage:{inputTokens:12,outputTokens:3,cachedInputTokens:4}};
  const payloads = [
    {billingAccountId:'synthetic-account',complete:false,requests:[request]},
    {billingAccountId:'synthetic-account',complete:false,requests:[completed]},
    {billingAccountId:'synthetic-account',complete:true,requests:[]},
  ];
  const rows = payloads.map((payload,index) => {
    const id = `55555555-5555-4555-8555-55555555555${index}`;
    const event = {modelSource:'builtin',modelUsageSource:'gateway',eventId:id,provider:'acode',threadId:thread,
      createdAt:`2026-11-17T13:00:0${index}.000Z`,turnId:turn,
      providerRefs:{providerThreadId:'33333333-3333-4333-8333-333333333333',providerTurnId:turn},
      raw:{source:'acode',method:'turn.gateway-usage.updated',payload:structuredClone(payload)},
      type:'turn.gateway-usage.updated',payload:structuredClone(payload)};
    return {sequence:10+index,event_id:id,thread_id:thread,turn_id:turn,lifecycle_generation:null,
      event_type:event.type,event_json:JSON.stringify(event),persisted_at:`2026-11-17T13:00:0${index}.100Z`};
  });
  return {ledger:{thread_id:thread,turn_id:turn,first_sequence:10,updated_at:'2026-11-17T13:00:02.200Z'},
    rows,anchors:{threads:0,sessions:0,runtime:0,pending:0}};
}
const proof = f => closedStructuredGatewayLedger(f.ledger,f.rows,f.anchors);
function edit(f,index,change) {
  const event=JSON.parse(f.rows[index].event_json);change(event);f.rows[index].event_json=JSON.stringify(event);
}

test('a complete one-shot gateway ledger retains provenance without inferring a candidate terminal',()=>{
  const f=fixture(),before=JSON.stringify(f),result=proof(f);
  assert.equal(result.profile,'closed-structured-gateway-ledger/v1');
  assert.equal(result.request_count,1);assert.equal(result.candidate_terminal_inferred,false);
  assert.equal(result.native_rows_modified,false);assert.equal(result.evidence.length,3);
  assert.match(result.evidence[0].event_sha256,/^[0-9a-f]{64}$/);
  assert.equal(JSON.stringify(f),before);assert.ok(!JSON.stringify(result).includes('synthetic-account'));
});

test('activity, incomplete delivery, missing history, identity conflicts and unknown shapes remain blocking',()=>{
  const changes = [
    f=>{f.ledger.thread_id='ordinary-thread';},
    f=>{f.ledger.first_sequence=11;},
    f=>{f.ledger.updated_at='invalid';},
    f=>{f.ledger.updated_at='2026-11-17T13:00:01.900Z';},
    f=>{f.rows.shift();},
    f=>{f.rows.pop();},
    f=>{f.rows[1].sequence=10;},
    f=>{f.rows[1].lifecycle_generation='live-generation';},
    f=>{f.rows[1].event_type='item.started';},
    f=>{f.rows[1].event_json='{}';},
    f=>edit(f,2,e=>{e.payload.complete=false;e.raw.payload.complete=false;}),
    f=>edit(f,2,e=>{e.payload.requests=[{status:'started'}];e.raw.payload.requests=e.payload.requests;}),
    f=>edit(f,1,e=>{e.payload.requests[0].status='started';e.raw.payload.requests[0].status='started';}),
    f=>edit(f,1,e=>{e.raw.payload.requests[0].status='failed';}),
    f=>edit(f,1,e=>{e.raw.payload.requests[0].unknownActivity=true;}),
    f=>edit(f,1,e=>{e.payload.requests[0].usage.inputTokens=-1;}),
    f=>edit(f,1,e=>{e.payload.requests[0].usage={};e.raw.payload.requests[0].usage={};}),
    f=>edit(f,1,e=>{e.providerRefs.providerThreadId='66666666-6666-4666-8666-666666666666';}),
    f=>edit(f,1,e=>{e.providerRefs.providerTurnId='66666666-6666-4666-8666-666666666666';}),
    f=>edit(f,1,e=>{e.turnId='other';}),
    f=>edit(f,1,e=>{e.unknownActivity=true;}),
    f=>edit(f,1,e=>{e.payload.billingAccountId='different';}),
    ...['threads','sessions','runtime','pending'].map(key=>f=>{f.anchors[key]=1;}),
  ];
  for(const [index,change] of changes.entries()) {
    const f=fixture();change(f);assert.equal(proof(f),null,`negative case ${index}`);
  }
});

test('the global readonly guard separates settled accounting from real orphan activity',async()=>{
  const root=await mkdtemp(join(tmpdir(),'astudio-structured-ledger-')),file=join(root,'state.sqlite');
  const db=new DatabaseSync(file),f=fixture();
  try {
    db.exec(`CREATE TABLE projection_threads(thread_id TEXT,project_id TEXT,latest_turn_id TEXT,deleted_at TEXT);
      CREATE TABLE projection_projects(project_id TEXT,workspace_root TEXT,deleted_at TEXT);
      CREATE TABLE projection_turns(row_id INTEGER,thread_id TEXT,turn_id TEXT,state TEXT,termination_origin TEXT,requested_at TEXT,started_at TEXT,completed_at TEXT,checkpoint_turn_count INTEGER);
      CREATE TABLE projection_thread_sessions(thread_id TEXT,status TEXT,active_turn_id TEXT,last_error TEXT,updated_at TEXT);
      CREATE TABLE projection_pending_interactions(thread_id TEXT,status TEXT);
      CREATE TABLE provider_session_runtime(thread_id TEXT,status TEXT,runtime_payload_json TEXT,resume_cursor_json TEXT);
      CREATE TABLE provider_runtime_open_turns(thread_id TEXT,turn_id TEXT,first_sequence INTEGER,updated_at TEXT);
      CREATE TABLE provider_runtime_events(sequence INTEGER,event_id TEXT,thread_id TEXT,turn_id TEXT,lifecycle_generation TEXT,event_type TEXT,event_json TEXT,persisted_at TEXT);`);
    db.prepare('INSERT INTO provider_runtime_open_turns VALUES(?,?,?,?)').run(...Object.values(f.ledger));
    const insert=db.prepare('INSERT INTO provider_runtime_events VALUES(?,?,?,?,?,?,?,?)');
    for(const row of f.rows)insert.run(...Object.values(row));
    const sha=async()=>createHash('sha256').update(await readFile(file)).digest('hex');
    const before=await sha(),settled=await queryNativeRuntimeSafety(file);
    assert.equal(settled.orphan_turns.length,0);assert.equal(settled.settled_structured_ledgers.length,1);
    assert.equal(nativeSafetyBlockers(settled).length,0);assert.equal(await sha(),before);
    db.prepare('INSERT INTO projection_pending_interactions VALUES(?,?)').run(f.ledger.thread_id,'pending');
    const pending=await queryNativeRuntimeSafety(file);
    assert.equal(pending.settled_structured_ledgers.length,0);assert.equal(pending.orphan_turns.length,1);
    assert.ok(nativeSafetyBlockers(pending).length>=2);
    db.exec('DELETE FROM projection_pending_interactions');
    const extra={...f.rows[2],sequence:13,event_type:'item.started'};insert.run(...Object.values(extra));
    const unknown=await queryNativeRuntimeSafety(file);
    assert.equal(unknown.settled_structured_ledgers.length,0);assert.equal(unknown.orphan_turns.length,1);
  } finally {db.close();await rm(root,{recursive:true,force:true});}
});
