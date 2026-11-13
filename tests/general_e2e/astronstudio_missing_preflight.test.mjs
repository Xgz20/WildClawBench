import assert from 'node:assert/strict';
import test from 'node:test';
import {validateMissingPreflightRow} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/recover_astronstudio_missing_preflight.mjs';

const fixture=()=>({phase:'NEEDS_ATTENTION',tasks:[{task_id:'t',phase:'NEEDS_ATTENTION',
  error:{code:'DRIVER_STATE_MISSING'},driver_exit_code:2,selected_attempt_id:null,
  dispatch_attempt_count:0,attempts:[],session:{thread_id:null,turn_id:null,session_id:null,cwd:null}}],
  history:[{event:'TASK_DISPATCH_RETURNED',task_id:'t',driver_exit_code:2,attempt_id:null,task_phase:'NEEDS_ATTENTION'}]});
test('only exact preflight failure without an attempt is eligible',()=>{
  const q=fixture();assert.equal(validateMissingPreflightRow(q,'t'),q.tasks[0]);
});
for(const [name,mutate] of [
  ['armed send',q=>q.tasks[0].dispatch_attempt_count=1],
  ['selected attempt',q=>q.tasks[0].selected_attempt_id='accepted-attempt'],
  ['native session',q=>q.tasks[0].session.session_id='native-session'],
  ['prior attempt',q=>q.tasks[0].attempts.push({attempt_id:'old'})],
  ['different error',q=>q.tasks[0].error.code='PROMPT_SEND_UNCERTAIN'],
  ['unmatched history',q=>q.history[0].attempt_id='unknown'],
  ['running queue',q=>q.phase='RUNNING'],
])test('recovery rejects '+name,()=>{const q=fixture();mutate(q);assert.throws(()=>validateMissingPreflightRow(q,'t'),/MISSING_PREFLIGHT_/);});
