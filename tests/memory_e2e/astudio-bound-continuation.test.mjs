import test from 'node:test';
import assert from 'node:assert/strict';
import {assertNativeContinuationBinding,staleRunningProjectionHasTerminalWitness,verifiedBlockingSessions} from '../../eval_memory_e2e/native/astudio-bound-continuation.mjs';
const expected={thread_id:'ui-1',session_id:'native-1',previous_turn_id:'turn-1',workspace:'/synthetic/unit/work',project_id:'project-1'};
function fixture(){return {sessions:[{thread_id:'ui-1',session_id:'native-1',turn_id:'turn-1',latest_turn_id:'turn-1',cwd:expected.workspace,
  status:'completed',turn_state:'completed',session_status:'ready',active_turn_id:null}],projects:[{project_id:'project-1',workspace_root:expected.workspace}]}}
test('hidden workspace continuation requires the exact completed native session and project',()=>{
  const value=fixture();assert.deepEqual(assertNativeContinuationBinding(value,expected),{session:value.sessions[0],project:value.projects[0]});
});
test('foreign cwd, session, turn, project and active work never admit a continuation',()=>{
  for(const [key,value] of [['cwd','/other/work'],['session_id','other'],['turn_id','new-turn'],['latest_turn_id','new-turn'],['active_turn_id','active'],['status','running'],['session_status','starting']]){
    const data=fixture();data.sessions[0][key]=value;assert.throws(()=>assertNativeContinuationBinding(data,expected));
  }
  for(const key of ['project_id','workspace_root']){const data=fixture();data.projects[0][key]='foreign';assert.throws(()=>assertNativeContinuationBinding(data,expected));}
});
test('missing or duplicate native bindings are rejected rather than adopting another route',()=>{
  for(const key of ['sessions','projects']){
    const missing=fixture();missing[key]=[];assert.throws(()=>assertNativeContinuationBinding(missing,expected));
    const duplicate=fixture();duplicate[key].push({...duplicate[key][0]});assert.throws(()=>assertNativeContinuationBinding(duplicate,expected));
  }
});
test('a stale running projection is idle only with the exact completed latest native turn',()=>{
  const row={...fixture().sessions[0],status:'running',completed_at:'2026-10-21T00:00:00Z',error:null};
  const events=[{type:'event_msg',payload:{type:'task_started',turn_id:'turn-1'}},{type:'event_msg',payload:{type:'task_complete',turn_id:'turn-1'}}];
  assert.equal(staleRunningProjectionHasTerminalWitness(row,events),true);
  for(const [key,value] of [['active_turn_id','new'],['turn_state','running'],['session_status','running'],['completed_at',null],['error','failed'],['latest_turn_id','new']])
    assert.equal(staleRunningProjectionHasTerminalWitness({...row,[key]:value},events),false);
  assert.equal(staleRunningProjectionHasTerminalWitness(row,events.slice(0,1)),false);
  assert.equal(staleRunningProjectionHasTerminalWitness(row,[...events,{type:'event_msg',payload:{type:'task_started',turn_id:'new'}}]),false);
  const binding={...fixture(),sessions:[row],terminal_events:events};
  assert.equal(assertNativeContinuationBinding(binding,expected).session.status,'running');
  assert.throws(()=>assertNativeContinuationBinding({...binding,terminal_events:events.slice(0,1)},expected));
});
test('active work and non-evaluation workspaces remain blocking without opening their rollouts',async()=>{
  const active={...fixture().sessions[0],status:'running',turn_state:'running'};
  const foreign={...fixture().sessions[0],status:'running',completed_at:'2026-10-21T00:00:00Z',cwd:'/ordinary-user-project'};
  const proof=await verifiedBlockingSessions([active,foreign],{},[expected.workspace],()=>true);
  assert.deepEqual(proof,{blocking:[active,foreign],terminal:[]});
});
