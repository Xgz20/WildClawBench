import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { verifyAgentCubeNative } from '../../tools/report/skills/general-e2e/collect-general-e2e/scripts/lib/agentcube-native-verification.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');

async function fixture(t) {
  const unitRoot = await mkdtemp(join(tmpdir(), 'wcb-agentcube-proof-'));
  t.after(() => rm(unitRoot, { recursive: true, force: true }));
  const traceRoot = join(unitRoot, 'trace');
  await mkdir(join(traceRoot, 'raw'), { recursive: true });
  await mkdir(join(traceRoot, 'bindings'), { recursive: true });
  const cwd = 'C:\\ProgramData\\WGUI\\workspace\\project';
  const identity = { batch_id: 'b', unit_id: 'u', task_id: 't', attempt_id: 'a' };
  const prompt = 'fixture task';
  const rows = [
    { type: 'session_meta', payload: { id: 'native', cwd } },
    { type: 'turn_context', payload: { turn_id: 'turn', cwd, model: 'spark-x2.6', effort: 'high' } },
    { type: 'event_msg', payload: { type: 'user_message', message: prompt } },
    { type: 'response_item', payload: { type: 'function_call', call_id: 'call', name: 'write', arguments: '{"file":"answer"}' } },
    { type: 'response_item', payload: { type: 'function_call_output', call_id: 'call', output: 'ok' } },
    { type: 'event_msg', payload: { type: 'task_complete', turn_id: 'turn', last_agent_message: 'done' } },
  ];
  const transcript = [
    { type: 'tool_call', tool: { call_id: 'call', name: 'write', arguments: { file: 'answer' } } },
    { type: 'tool_result', tool: { call_id: 'call', result: 'ok' } },
  ];
  const raw = Buffer.from(rows.map(row => JSON.stringify(row)).join('\n') + '\n');
  const state = { schema: 'wildclawbench.agentcube-execution-proof/v1', identity,
    unit: { backend: 'agentcube', harness: 'astronstudio', model: 'spark-x2.6', reasoning_effort: 'high' },
    report: { schema_version: 2, status: 'completed' }, prompt_sha256: sha(prompt),
    native_binding: { session: { cwd }, raw_sha256: sha(raw) },
    process_cleanup: { schema: 'wildclawbench.agentcube-process-cleanup/v1', phase: 'completed',
      supported: true, success: true, before: [], after: [], root_pid: null, disposition: 'already_exited',
      workspace: cwd, quiet_observed_milliseconds: 5000 } };
  const record = { identity, session: { cwd, verified: true, thread_id: null, session_id: 'native', turn_id: 'turn' },
    model: { requested_id: 'spark-x2.6', actual_id: 'spark-x2.6', reasoning_effort: 'high' },
    prompt: { sha256: sha(prompt) }, evidence: { final_response_path: 'final.md' } };
  const index = { identity, adapter: { id: 'agentcube-astudio-native' },
    raw_trace: [{ path: 'raw/rollout.jsonl', sha256: sha(raw), size: raw.length }],
    transcript: { path: 'transcript.jsonl' }, calls: [{ call_id: 'call' }] };
  await writeFile(join(traceRoot, 'raw/rollout.jsonl'), raw);
  await writeFile(join(unitRoot, 'final.md'), 'done');
  async function verify() {
    const stateBytes = Buffer.from(JSON.stringify(state));
    await writeFile(join(traceRoot, 'bindings/execution-proof.json'), stateBytes);
    await writeFile(join(traceRoot, 'transcript.jsonl'), transcript.map(row => JSON.stringify(row)).join('\n'));
    return verifyAgentCubeNative({ unitRoot, traceRoot, stateBytes, index, record });
  }
  async function rewriteRaw() {
    const bytes = Buffer.from(rows.map(row => JSON.stringify(row)).join('\n') + '\n');
    state.native_binding.raw_sha256 = sha(bytes);
    Object.assign(index.raw_trace[0], { sha256: sha(bytes), size: bytes.length });
    await writeFile(join(traceRoot, 'raw/rollout.jsonl'), bytes);
  }
  return { state, record, transcript, rows, rewriteRaw, verify };
}

test('controller-closed AStudio requires an observed quiet period', async t => {
  const value = await fixture(t);
  assert.equal((await value.verify()).native_tool_calls, 1);
  value.state.process_cleanup.quiet_observed_milliseconds = 4999;
  await assert.rejects(value.verify(), /CLEANUP_UNVERIFIED/);
});

test('explicit process cleanup binds its root identity', async t => {
  const value = await fixture(t);
  Object.assign(value.state.process_cleanup, { root_pid: 123, disposition: 'stopped_owned_tree',
    before: [{ pid: 123, name: 'AStudio.exe', path: 'C:\\Programs\\AStudio\\AStudio.exe', created: 'observed' }] });
  assert.equal((await value.verify()).verified, true);
  value.state.process_cleanup.before[0].name = 'unrelated.exe';
  await assert.rejects(value.verify(), /PROCESS_ROOT_INVALID/);
});

test('missing normalized native tool events cannot pass collection', async t => {
  const value = await fixture(t);
  value.transcript.pop();
  await assert.rejects(value.verify(), /TOOL_COVERAGE_MISMATCH/);
});

test('requested and observed model must match independently', async t => {
  const value = await fixture(t);
  value.state.unit.model = 'different-model';
  await assert.rejects(value.verify(), /MODEL_BINDING_MISMATCH/);
});

test('unproven empty process observations cannot pass as cleanup', async t => {
  const value = await fixture(t);
  delete value.state.process_cleanup.disposition;
  await assert.rejects(value.verify(), /PROCESS_ROOT_INVALID/);
});

test('MCP end metadata must bind to the canonical call and result', async t => {
  const value = await fixture(t);
  value.rows[3].payload.name = 'mcp__acode_apps__connector_sites__manage_site';
  value.rows[3].payload.arguments = '{"operation":"create"}';
  Object.assign(value.transcript[0].tool, { name: value.rows[3].payload.name, arguments: { operation: 'create' } });
  const end = { type: 'event_msg', payload: { type: 'mcp_tool_call_end', call_id: 'call',
    invocation: { server: 'acode_apps', tool: 'manage_site', arguments: { operation: 'create' } }, result: { Ok: {} } } };
  value.rows.push(end);
  await value.rewriteRaw();
  assert.equal((await value.verify()).native_tool_calls, 1);
  end.payload.invocation.arguments.operation = 'delete';
  await value.rewriteRaw();
  await assert.rejects(value.verify(), /MCP_INVOCATION_MISMATCH/);
});

test('single pasted prompt is independently decoded and its native bytes stay bound', async t => {
  const value = await fixture(t);
  const message = `<pasted_text>\n${JSON.stringify([{ text: 'fixture task' }])}\n</pasted_text>`;
  value.rows[2].payload.message = message;
  value.state.native_binding.prompt_transport = { kind: 'astudio-single-pasted-text-json',
    native_message_sha256: sha(message), decoded_text_sha256: sha('fixture task') };
  await value.rewriteRaw();
  assert.equal((await value.verify()).verified, true);
  value.state.native_binding.prompt_transport.native_message_sha256 = sha('different');
  await assert.rejects(value.verify(), /PROMPT_MISMATCH/);
});

test('pasted prompt rejects extra content, entries, fields and changed text', async t => {
  const value = await fixture(t);
  for (const [entries, prefix, suffix] of [
    [[{ text: 'different' }], '', ''],
    [[{ text: 'fixture task' }, { text: 'extra' }], '', ''],
    [[{ text: 'fixture task', file: 'extra' }], '', ''],
    [[{ text: 'fixture task' }], 'extra\n', ''],
    [[{ text: 'fixture task' }], '', '\nextra'],
  ]) {
    const message = `${prefix}<pasted_text>\n${JSON.stringify(entries)}\n</pasted_text>${suffix}`;
    value.rows[2].payload.message = message;
    value.state.native_binding.prompt_transport = { kind: 'astudio-single-pasted-text-json',
      native_message_sha256: sha(message), decoded_text_sha256: sha(entries[0].text) };
    await value.rewriteRaw();
    await assert.rejects(value.verify(), /PROMPT_MISMATCH/);
  }
});
