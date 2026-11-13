import assert from 'node:assert/strict';
import test from 'node:test';
import {isVerifiedCompletedUiOwner} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';

function fixture() {
  const task={task_id:'owner',workspace:{path:'execution/tasks/owner/workspace'},prompt:{sent_sha256:'a'.repeat(64)}};
  const cwd='/unit/execution/tasks/owner/workspace';
  const config={unitRoot:'/unit',candidateWorkspace:'/unit/execution/tasks/next/workspace',manifest:{batch_id:'b',unit_id:'u',dataset:{id:'d',digest:'x'}},runConfig:{config_digest:'c'}};
  const native={thread_id:'thread',turn_id:'turn',latest_turn_id:'turn',session_id:'sid',cwd,status:'completed',turn_state:'completed',session_status:'ready',active_turn_id:null};
  const state={identity:{batch_id:'b',unit_id:'u',task_id:'owner',attempt_id:'original-attempt'},dataset:{id:'d',digest:'x'},phase:'COMPLETED',candidate_workspace:cwd,
    execution:{business_status:'completed',finished_at:'2026-11-11T10:00:00Z'},run_config:{config_digest:'c'},
    prompt:{sha256:'a'.repeat(64),send_status:'sent'},send:{dispatch_attempt_count:1},
    session:{thread_id:'thread',turn_id:'turn',session_id:'sid',cwd,verified:true}};
  return {config,native,task,state};
}
test('only the exact completed sent turn in this unit owns the hidden-control route',()=>{
  const f=fixture();assert.equal(isVerifiedCompletedUiOwner(f.config,f.native,f.task,f.state),true);
});
for(const [name,mutate] of [
  ['new turn',f=>f.native.latest_turn_id='new'],['active turn',f=>f.native.active_turn_id='turn'],
  ['running runtime',f=>f.native.session_status='running'],['foreign unit',f=>f.state.identity.unit_id='foreign'],
  ['changed Prompt',f=>f.state.prompt.sha256='b'.repeat(64)],['changed config',f=>f.state.run_config.config_digest='new'],
  ['unverified session',f=>f.state.session.verified=false],['changed session',f=>f.native.session_id='other'],
  ['wrong Workspace',f=>f.native.cwd='/other'],['same target already used',f=>f.config.candidateWorkspace=f.native.cwd],
  ['unknown send',f=>f.state.prompt.send_status='uncertain'],['multiple dispatch',f=>f.state.send.dispatch_attempt_count=2],
  ['failed task',f=>f.state.phase='FAILED'],['missing end',f=>f.state.execution.finished_at=null],
  ['missing native identity',f=>f.native.session_id=null],['missing attempt',f=>delete f.state.identity.attempt_id],
])test('completed UI ownership rejects '+name,()=>{const f=fixture();mutate(f);assert.equal(isVerifiedCompletedUiOwner(f.config,f.native,f.task,f.state),false);});
