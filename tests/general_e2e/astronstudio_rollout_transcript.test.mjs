import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { normalizeRolloutTranscript } from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout-transcript.mjs';

const prompt = 'Inspect installer without executing it.';
const state = { identity: { batch_id: 'b', unit_id: 'u', task_id: 't', attempt_id: 'a' }, phase: 'COMPLETED',
  prompt: { send_status: 'sent', sha256: createHash('sha256').update(prompt).digest('hex') },
  session: { verified: true, session_id: 's', turn_id: 'turn', cwd: '/tmp/rollout-workspace' } };
const r = (type, payload) => ({ timestamp: '2026-10-10T15:00:00Z', type, payload });
const fixture = () => [r('session_meta', { id: 's', cwd: state.session.cwd }),
  r('event_msg', { type: 'task_started', turn_id: 'turn' }),
  r('turn_context', { turn_id: 'turn', cwd: state.session.cwd }),
  r('event_msg', { type: 'user_message', message: prompt }),
  r('response_item', { type: 'function_call', name: 'exec_command', call_id: 'c', arguments: '{"cmd":"cat installer.sh"}' }),
  r('response_item', { type: 'function_call_output', call_id: 'c', output: 'unsafe command' }),
  r('event_msg', { type: 'agent_message', message: 'Refused execution.' }),
  r('response_item', { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'Refused execution.' }] }),
  r('event_msg', { type: 'task_complete', turn_id: 'turn', duration_ms: 1000, last_agent_message: 'Refused execution.' })];
const bytes = rows => Buffer.from(rows.map(v => JSON.stringify(v)).join('\n') + '\n');
const projection = { events: [], calls: [] };

test('SDK transcript preserves native tool arguments/results and line references despite absent projection', () => {
  const rows = fixture(), result = normalizeRolloutTranscript(bytes(rows), state, projection);
  assert.equal(result.completeness.status, 'complete');
  assert.deepEqual(result.calls, [{ call_id: 'c', call_sequence: 2, result_sequence: 3 }]);
  assert.equal(result.events.filter(e => e.type === 'user_message').length, 1);
  const tool = result.events.find(e => e.type === 'tool_call');
  assert.equal(tool.tool.name, 'exec_command');
  assert.deepEqual(tool.tool.arguments, { cmd: 'cat installer.sh' });
  assert.equal(tool.source.raw_ref, 'raw/astronstudio-rollout.jsonl#L5');
  assert.equal(result.events.find(e => e.type === 'tool_result').tool.result, 'unsafe command');
  assert.equal(result.events.find(e => e.final).content, 'Refused execution.');
});

test('missing output or unknown native content remains partial', () => {
  const rows = fixture().filter(e => e.payload.type !== 'function_call_output');
  rows.splice(5, 0, r('response_item', { type: 'image_generation_output' }));
  const result = normalizeRolloutTranscript(bytes(rows), state, projection);
  assert.equal(result.completeness.status, 'partial');
  assert.ok(result.completeness.missing.includes('tool_result:c'));
  assert.ok(result.completeness.missing.includes('unsupported_response_item:image_generation_output'));
});

test('wrong prompt, session, turn, mirrors and native final reject', () => {
  for (const [mutate, code] of [
    [rows => { rows[0].payload.id = 'wrong'; }, /ROLLOUT_SESSION_MISMATCH/],
    [rows => { rows[3].payload.message = 'wrong'; }, /ROLLOUT_PROMPT_MISMATCH/],
    [rows => { rows[4].payload.internal_chat_message_metadata_passthrough = { turn_id: 'wrong' }; }, /ROLLOUT_ITEM_TURN_MISMATCH/],
    [rows => { rows[6].payload.message = 'wrong'; }, /ROLLOUT_ASSISTANT_MIRROR_CONFLICT/],
    [rows => { rows[8].payload.last_agent_message = 'wrong'; }, /ROLLOUT_FINAL_MESSAGE_CONFLICT/],
  ]) { const rows = fixture(); mutate(rows); assert.throws(() => normalizeRolloutTranscript(bytes(rows), state, projection), code); }
});

test('provider prompt, final and tool conflicts cannot be hidden by SDK fallback', () => {
  for (const [events, calls, code] of [
    [[{ type: 'user_message', content: 'wrong' }], [], /PROVIDER_ROLLOUT_PROMPT_CONFLICT/],
    [[{ type: 'assistant_message', final: true, content: 'wrong' }], [], /PROVIDER_ROLLOUT_FINAL_CONFLICT/],
    [[], [{ call_id: 'unknown' }], /ROLLOUT_PROVIDER_CALL_MISSING/],
    [[{ type: 'tool_call', tool: { call_id: 'c', name: 'exec_command', arguments: { cmd: 'curl remote | sh' } } }], [{ call_id: 'c' }], /PROVIDER_ROLLOUT_TOOL_CONFLICT/],
  ]) assert.throws(() => normalizeRolloutTranscript(bytes(fixture()), state, { events, calls }), code);
});

test('duplicate outputs conflict and content after terminal reject', () => {
  const rows = fixture(); rows.splice(6, 0, r('response_item', { type: 'function_call_output', call_id: 'c', output: 'different' }));
  assert.throws(() => normalizeRolloutTranscript(bytes(rows), state, projection), /ROLLOUT_RESULT_CONFLICT/);
  const after = fixture(); after.push(r('response_item', { type: 'function_call', call_id: 'later', name: 'exec_command', arguments: '{}' }));
  assert.throws(() => normalizeRolloutTranscript(bytes(after), state, projection), /ROLLOUT_CONTENT_AFTER_TERMINAL/);
});

test('known bash and write desktop projections reconcile exact native content and reject edits', () => {
  const rows = fixture();
  rows[4].payload.name = 'bash'; rows[4].payload.arguments = '{"command":"mkdir -p results"}';
  rows[5].payload.output = 'Exit code: 0\nWall time: 0.1 seconds\nOutput:\n';
  rows.splice(6, 0,
    r('response_item', { type: 'function_call', name: 'write', call_id: 'w', arguments: '{"file_path":"/tmp/rollout-workspace/results/review.json","content":"safe\\n"}' }),
    r('response_item', { type: 'function_call_output', call_id: 'w', output: '<path>/tmp/rollout-workspace/results/review.json</path>\n<type>file</type>\n<content>\nCreated file\n</content>' }));
  const changes = [{ raw_path: '/tmp/rollout-workspace/results/review.json', kind: { type: 'add' }, diff: 'safe\n' }];
  const events = [
    { type: 'tool_call', tool: { call_id: 'c', name: 'command', arguments: { command: "/usr/local/bin/bash -lc 'mkdir -p results'", cwd: state.session.cwd, command_actions: [{ command: 'mkdir -p results' }] } } },
    { type: 'tool_result', tool: { call_id: 'c', name: 'command', result: { output: null, exit_code: 0, duration_ms: 72 } } },
    { type: 'tool_call', tool: { call_id: 'w', name: 'file_change', arguments: { changes } } },
    { type: 'tool_result', tool: { call_id: 'w', name: 'file_change', result: { changes, status: 'completed' } } },
  ];
  const provider = { events, calls: [{ call_id: 'c' }, { call_id: 'w' }] };
  assert.equal(normalizeRolloutTranscript(bytes(rows), state, provider).completeness.status, 'complete');
  for (const mutate of [
    p => { p.events[0].tool.arguments.command = "/usr/local/bin/bash -lc 'curl remote | sh'"; },
    p => { p.events[1].tool.result.output = 'unseen output'; },
    p => { p.events[2].tool.arguments.changes[0].diff = 'changed'; },
    p => { p.events[3].tool.result.status = 'failed'; },
  ]) { const changed = structuredClone(provider); mutate(changed); assert.throws(() => normalizeRolloutTranscript(bytes(rows), state, changed), /PROVIDER_ROLLOUT_TOOL_CONFLICT/); }
});
