import assert from 'node:assert/strict';
import test from 'node:test';
import { verifyNativeMainAssignment, verifyTrajectoryPrompt } from '../../tools/report/e2e-shared/doubaowork/bound-evidence.mjs';
import { summarizePromptReadback } from '../../tools/report/e2e-shared/doubaowork/lib.mjs';
const prompt='Frozen original prompt\n任务：比较公开资料。\n';
const text='# Assignment\n- Agent ID: m_main\n- Role: main\n- Assigned by: user\n- Created: 2026-11-05T05:40:48.558598274Z\n\n> append-only: 每个 turn 的需求按时间戳追加在下方，最新在末尾。\n\n## [2026-11-05T05:40:48.558598274Z] 需求\n'+prompt;
const cfg={agentId:'m_main',expectedHash:summarizePromptReadback(prompt).sha256};
test('MOA main assignment binds the exact original prompt and a single user-assigned native main agent',()=>{
 const proof=verifyNativeMainAssignment(Buffer.from(text),cfg);
 assert.equal(proof.status,'verified');assert.equal(proof.user_event_count,0);
 for(const bad of [text.replace('m_main','m_other'),text.replace('Role: main','Role: subagent'),text.replace('Assigned by: user','Assigned by: assistant'),
   text+'\n## [2026-11-05T06:00:00.000Z] 需求\nanother prompt',text.replace('比较公开资料','替换答案'),text.replace('## [2026-11-05T05:40:48','## [2026-11-05T05:41:48')]) {
  assert.throws(()=>verifyNativeMainAssignment(Buffer.from(bad),cfg),/ASSIGNMENT_UNBOUND/);
 }
 // The legacy trajectory check remains strict; no bare missing-prompt bypass.
 assert.throws(()=>verifyTrajectoryPrompt([],cfg.expectedHash,{sourceBytes:Buffer.from('assistant data')}),/PROMPT_MISMATCH/);
 assert.throws(()=>verifyTrajectoryPrompt([{kind:'user_message',content:'other'}],cfg.expectedHash,{sourceBytes:Buffer.from(text)}),/PROMPT_MISMATCH/);
});
