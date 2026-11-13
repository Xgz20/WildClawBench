import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { assertNativeActivity, captureNative, PROFILE, sha, statusUrl, verifyBinding } from '../../tools/report/e2e-shared/loomy/index.mjs';
import { checkNativeModel, buildState } from '../../tools/report/e2e-shared/loomy/execution.mjs';
import { normalizeTrace, resourceMetrics } from '../../tools/report/e2e-shared/loomy/collection.mjs';

const prompt = '仅处理本题 workspace。';
test('Loomy status requests preserve the exact workspace directory and loopback owner scope', () => {
  const url = statusUrl({ endpoint: 'http://127.0.0.1:5072' }, '/fixture/work space');
  assert.equal(url.pathname, '/session/status'); assert.equal(url.searchParams.get('directory'), '/fixture/work space');
  assert.throws(() => statusUrl({ endpoint: 'https://example.org' }, '/fixture'));
  assert.throws(() => statusUrl({ endpoint: 'http://127.0.0.1:5072' }, 'relative'));
});
test('Loomy global activity admits only registered peers and their same-directory descendants', () => {
  const native = { session_index: [{ id: 'parent', parent_id: null, directory: '/one' }, { id: 'child', parent_id: 'parent', directory: '/one' }],
    session_activity: [{ session_id: 'parent', status: 'active_or_unknown' }, { session_id: 'child', status: 'active_or_unknown' }] };
  assert.throws(() => assertNativeActivity(native));
  assert.doesNotThrow(() => assertNativeActivity(native, ['parent']));
  native.session_index[1].directory = '/foreign';
  assert.throws(() => assertNativeActivity(native, ['parent']));
  assert.throws(() => assertNativeActivity({}));
});
function fixture({ tool = true, child = false } = {}) {
  const session = (id, parent_id = null) => ({ id, parent_id, directory: '/fixture/workspace', version: 'fixture', time_created: 1000, time_updated: 2000 });
  const message = (id, session_id, data, time_created = 1000) => ({ id, session_id, time_created, time_updated: 2000, data: JSON.stringify(data) });
  const part = (id, message_id, data, session_id = 'ses_root', time_created = 1000) => ({ id, message_id, session_id, time_created, time_updated: 2000, data: JSON.stringify(data) });
  const native = { profile: PROFILE, snapshot: { method: 'readonly-source-sqlite-online-backup' },
    sessions: [session('ses_root')],
    messages: [message('msg_user', 'ses_root', { role: 'user', model: { providerID: 'imodel', modelID: 'spark-x2.6' }, variant: 'high', time: { created: 1000 } }),
      message('msg_final', 'ses_root', { role: 'assistant', providerID: 'imodel', modelID: 'spark-x2.6', finish: 'stop', time: { created: 1100, completed: 2000 } }, 1100)],
    parts: [part('part_user', 'msg_user', { type: 'text', text: prompt }), part('part_final', 'msg_final', { type: 'text', text: '已完成。' }, 'ses_root', 1900)] };
  if (tool) native.parts.push(part('part_tool', 'msg_final', { type: 'tool', tool: 'read', callID: 'call_read', state: { status: 'completed', input: { path: 'input.txt' }, output: '原文', time: { start: 1200, end: 1300 } } }, 'ses_root', 1200));
  if (child) {
    native.sessions.push(session('ses_child', 'ses_root'));
    native.messages.push(message('msg_child_user', 'ses_child', { role: 'user' }), message('msg_child_final', 'ses_child', { role: 'assistant', finish: 'stop', time: { completed: 2100 } }));
    native.parts.push(part('part_child_user', 'msg_child_user', { type: 'text', text: '内部委派' }, 'ses_child'), part('part_child_final', 'msg_child_final', { type: 'text', text: '子任务回复' }, 'ses_child', 2100));
  }
  return native;
}
const options = { workspace: '/fixture/workspace', prompt, baseline: [], sessionId: 'ses_root', terminal: true };
function state() { return { identity: { batch_id: 'batch', unit_id: 'loomy-macos', task_id: 'task', attempt_id: 'attempt' },
  phase: 'COMPLETED', session: { thread_id: 'ses_root', turn_id: 'msg_user', session_id: 'ses_root', cwd: options.workspace },
  execution: { duration_seconds: 1.2 } }; }

test('Loomy binds the exact native prompt, root session, model and high variant', () => {
  const result = verifyBinding(fixture(), options); checkNativeModel(result);
  assert.equal(result.user.id, 'msg_user'); assert.equal(result.final.id, 'msg_final');
  for (const edit of [n => { n.sessions[0].directory = '/other'; }, n => { n.parts[0].data = JSON.stringify({ type: 'text', text: 'different' }); },
    n => { n.messages[0].data = JSON.stringify({ role: 'user', model: { providerID: 'imodel', modelID: 'spark-x2.6' }, variant: 'low' }); },
    n => { n.parts.push({ ...n.parts[0] }); }, n => { n.parts[0].session_id = 'ses_foreign'; }]) {
    const native = fixture(); edit(native);
    assert.throws(() => { checkNativeModel(verifyBinding(native, options)); });
  }
  assert.throws(() => verifyBinding(fixture(), { ...options, baseline: ['ses_root'] }));
});

test('Loomy rejects unfinished tools and linked child sessions as completed', () => {
  const native = fixture(); native.parts[2].data = JSON.stringify({ type: 'tool', tool: 'read', callID: 'call_read', state: { status: 'running' } });
  assert.throws(() => verifyBinding(native, options), /TOOL_NOT_TERMINAL/);
  const child = fixture({ child: true }); child.messages.at(-1).data = JSON.stringify({ role: 'assistant' });
  assert.throws(() => verifyBinding(child, options), /CHILD_NOT_TERMINAL/);
});

test('Loomy conserves text/tool atoms and never substitutes a child final for the root final', () => {
  const result = normalizeTrace(fixture({ child: true }), { state: state(), prompt, baseline: [] });
  assert.equal(result.final_response, '已完成。');
  assert.equal(result.events.filter(row => row.type === 'user_message').length, 1);
  assert.equal(result.events.filter(row => row.type === 'assistant_message').length, 1);
  assert.equal(result.calls.length, 1);
  assert.equal(result.events[result.calls[0].call_sequence].tool.arguments.path, 'input.txt');
  assert.equal(result.events[result.calls[0].result_sequence].tool.result, '原文');
  assert.equal(result.native_event_count, result.events.length + result.filtered_native_event_count);
  assert.ok(result.events.some(row => row.is_subagent && row.native_type === 'subagent_message'));
});

test('Loomy retains unknown part coverage and refuses unaudited human question answers', () => {
  const native = fixture({ tool: false });
  native.parts.push({ ...native.parts[1], id: 'part_unknown', data: JSON.stringify({ type: 'new-unknown-part' }) });
  assert.deepEqual(normalizeTrace(native, { state: state(), prompt, baseline: [] }).missing, ['unsupported-native-part:new-unknown-part']);
  const question = fixture(); const tool = JSON.parse(question.parts[2].data); tool.tool = 'question'; question.parts[2].data = JSON.stringify(tool);
  assert.throws(() => normalizeTrace(question, { state: state(), prompt, baseline: [] }), /INTERVENTION_RECEIPT/);
});

test('Loomy resources expose proved tool zero and leave unadmitted token/request fields null', () => {
  const current = state(), normalized = normalizeTrace(fixture({ tool: false }), { state: current, prompt, baseline: [] });
  const value = resourceMetrics({ state: current, normalized, sources: [] });
  assert.equal(value.metrics.tools.call_count.value, 0); assert.equal(value.metrics.tools.call_count.status, 'observed');
  for (const row of Object.values(value.metrics.usage)) { assert.equal(row.value, null); assert.equal(row.status, 'unavailable'); }
  assert.equal(value.metrics.requests.request_count.value, null);
  assert.equal(value.metrics.timing.duration_seconds.value, 1.2);
  assert.equal(value.metrics.timing.agent_duration_seconds.value, 1);
});

test('Loomy reads an online backup without exporting another session or credential table', async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'loomy-native-test-'))), database = join(root, 'native.db');
  try {
    const sql = `import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
c.executescript("""CREATE TABLE session(id TEXT PRIMARY KEY,parent_id TEXT,directory TEXT,version TEXT,time_created INTEGER,time_updated INTEGER);
CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,data TEXT,time_created INTEGER,time_updated INTEGER);
CREATE TABLE part(id TEXT PRIMARY KEY,message_id TEXT,session_id TEXT,data TEXT,time_created INTEGER,time_updated INTEGER);
CREATE TABLE credential(value TEXT);
INSERT INTO credential VALUES('DO_NOT_EXPORT_CREDENTIALS');
INSERT INTO session VALUES('ses_root',NULL,'/fixture/workspace','fixture',1,2);
INSERT INTO session VALUES('ses_child','ses_root','/fixture/workspace','fixture',1,2);
INSERT INTO session VALUES('ses_other',NULL,'/private/unrelated','fixture',1,2);
INSERT INTO message VALUES('msg_other','ses_other','private unrelated content',1,2);
""")
c.commit();c.close()`;
    const created = spawnSync('python3', ['-c', sql, database], { encoding: 'utf8' }); assert.equal(created.status, 0, created.stderr);
    const before = sha(await readFile(database));
    const result = await captureNative({ database, sessionId: 'ses_root' });
    assert.deepEqual(result.sessions.map(row => row.id), ['ses_child', 'ses_root']);
    assert.equal(result.snapshot.quick_check, 'ok');
    assert.equal(sha(await readFile(database)), before);
    assert.ok(!JSON.stringify(result).includes('DO_NOT_EXPORT_CREDENTIALS'));
    assert.ok(!JSON.stringify(result).includes('/private/unrelated'));
  } finally { await rm(root, { recursive: true, force: true }); }
});
