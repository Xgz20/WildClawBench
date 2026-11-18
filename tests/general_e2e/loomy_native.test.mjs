import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { assertNativeActivity, captureNative, COMPONENT_VERSION, digest, EMPTY_MEMORY_CONTEXT, isAbsentRuntime, jsonBytes, parseNativeHttpError, PROFILE, sameRuntimeInstallation, sha, statusUrl, verifyBinding, verifyNativeHttpFailure } from '../../tools/report/e2e-shared/loomy/index.mjs';
import { checkNativeModel, buildState, loadTask, sourceRepair } from '../../tools/report/e2e-shared/loomy/execution.mjs';
import { runBatch } from '../../tools/report/e2e-shared/loomy/batch.mjs';
import { normalizeTrace, resourceMetrics } from '../../tools/report/e2e-shared/loomy/collection.mjs';

const prompt = '仅处理本题 workspace。';
test('Loomy cold start binds the measured binary version without inventing a live runtime', () => {
  const absent = { state: 'absent', pid: null, ppid: 10, executable: '/app/opencode', started_at: null,
    binary_sha256: 'a'.repeat(64), endpoint: null, database: '/native.db', database_owned: false,
    health_version: null, binary_version: '1.14.22' };
  const live = { ppid: 10, executable: absent.executable, binary_sha256: absent.binary_sha256,
    database: absent.database, database_owned: true, health_version: '1.14.22' };
  assert.equal(isAbsentRuntime(absent), true); assert.equal(sameRuntimeInstallation(absent, live), true);
  for (const change of [{ endpoint: 'http://127.0.0.1:1' }, { database_owned: true }, { health_version: '1.14.22' }, { binary_version: 'unknown' }]) {
    assert.equal(isAbsentRuntime({ ...absent, ...change }), false);
    assert.equal(sameRuntimeInstallation({ ...absent, ...change }, live), false);
  }
  for (const change of [{ ppid: 20 }, { binary_sha256: 'b'.repeat(64) }, { database: '/foreign.db' }, { health_version: 'unknown' }, { database_owned: false }]) {
    assert.equal(sameRuntimeInstallation(absent, { ...live, ...change }), false);
  }
});
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
test('Loomy admits an archived failure only while its exact native head is unchanged', () => {
  const proof = { session_id: 'ses_old', directory: '/prior/workspace', last_message_id: 'msg_failed',
    last_message_sha256: 'a'.repeat(64), completed_at: 1000 };
  const old = { ...proof, parent_id: null, last_role: 'assistant', finish: null, has_error: false,
    pending_tool_count: 0, status: 'active_or_unknown' };
  const native = row => ({ session_index: [{ id: 'ses_old', parent_id: null, directory: proof.directory }],
    session_activity: [row] });
  assert.throws(() => assertNativeActivity(native(old)), /FOREIGN_OR_UNSETTLED/);
  assert.doesNotThrow(() => assertNativeActivity(native(old), [], [proof]));
  for (const change of [{ last_message_sha256: 'b'.repeat(64) }, { last_message_id: 'msg_new' },
    { directory: '/other/workspace' }, { completed_at: 1001 }, { pending_tool_count: 1 }]) {
    assert.throws(() => assertNativeActivity(native({ ...old, ...change }), [], [proof]), /ARCHIVED_FAILURE_HEAD_CHANGED/);
  }
  const child = { id: 'ses_child', parent_id: 'ses_old', directory: proof.directory };
  const withChild = native(old);
  withChild.session_index.push(child);
  withChild.session_activity.push({ ...child, session_id: child.id, status: 'active_or_unknown' });
  assert.throws(() => assertNativeActivity(withChild, [], [proof]), /FOREIGN_OR_UNSETTLED/);
});
function fixture({ tool = true, child = false } = {}) {
  const session = (id, parent_id = null) => ({ id, parent_id, directory: '/fixture/workspace', version: 'fixture', time_created: 1000, time_updated: 2000 });
  const message = (id, session_id, data, time_created = 1000) => ({ id, session_id, time_created, time_updated: 2000, data: JSON.stringify(data) });
  const part = (id, message_id, data, session_id = 'ses_root', time_created = 1000) => ({ id, message_id, session_id, time_created, time_updated: 2000, data: JSON.stringify(data) });
  const native = { profile: PROFILE, snapshot: { method: 'readonly-source-sqlite-online-backup' },
    sessions: [session('ses_root')],
    messages: [message('msg_user', 'ses_root', { role: 'user', model: { providerID: 'imodel', modelID: 'spark-x2.6', variant: 'high' }, time: { created: 1000 } }),
      message('msg_final', 'ses_root', { role: 'assistant', providerID: 'imodel', modelID: 'spark-x2.6', variant: 'high', finish: 'stop', time: { created: 1100, completed: 2000 } }, 1100)],
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
test('Loomy admits a bound primary 502 with an empty completed head, preserving failure and error atoms', () => {
  const native = fixture({ tool: false }); native.parts = native.parts.filter(row => row.id !== 'part_final');
  const final = JSON.parse(native.messages[1].data); delete final.finish; native.messages[1].data = JSON.stringify(final);
  const runtime = { ppid: 10, executable: '/app/opencode', binary_sha256: 'a'.repeat(64), database: '/native.db', database_owned: true, health_version: '1.14.22' };
  const error = { name: 'AI_APICallError', url: 'https://loomyad.xunfei.cn/api/v1/chat/completions', statusCode: 502,
    requestBodyValues: { model: 'spark-x2.6', messages: [{ role: 'user', content: [{ type: 'text', text: prompt }] }] } };
  const encodeLine = value => Buffer.from('ERROR 1970-01-01T00:00:01 +1ms service=llm providerID=imodel modelID=spark-x2.6 session.id=ses_root small=false agent=loomy mode=primary error=' + JSON.stringify({ error: value }) + ' trailing=retained');
  const bytes = encodeLine(error), current = state(); current.phase = 'FAILED';
  current.execution.business_status = 'candidate_error'; current.execution.error = { code: 'LOOMY_NATIVE_HTTP_ERROR', message: 'Native primary model HTTP 502 after provider retries' };
  const proof = { profile: 'loomy-native-primary-http-failure/v1', identity: current.identity, prompt_sha256: sha(Buffer.from(prompt)),
    session_id: 'ses_root', final_message_id: 'msg_final', original_runtime: runtime, observed_runtime: { ...runtime },
    observed_at: '1970-01-01T00:00:03Z', runtime_status: {},
    source_lines: [{ bytes_base64: bytes.toString('base64'), sha256: sha(bytes), size: bytes.length, line_number: 1 }] };
  const scope = { ...options, identity: current.identity, native };
  assert.equal(verifyNativeHttpFailure(proof, scope).error.code, 'LOOMY_NATIVE_HTTP_ERROR');
  const normalized = normalizeTrace(native, { state: current, prompt, baseline: [], nativeFailure: proof });
  assert.equal(normalized.final_response, null); assert.equal(normalized.events.filter(row => row.type === 'error').length, 1);
  assert.throws(() => normalizeTrace(native, { state: current, prompt, baseline: [] }), /UNPROVED/);
  for (const mutate of [p => { p.session_id = 'ses_foreign'; }, p => { p.runtime_status.ses_root = { type: 'busy' }; },
    p => { p.observed_runtime.binary_sha256 = 'b'.repeat(64); }, p => { p.source_lines[0].sha256 = 'b'.repeat(64); }]) {
    const changed = structuredClone(proof); mutate(changed); assert.throws(() => verifyNativeHttpFailure(changed, scope));
  }
  assert.equal(parseNativeHttpError(encodeLine({ ...error, statusCode: 402 }).toString()), null);
  assert.equal(parseNativeHttpError(bytes.toString().replace('agent=loomy', 'agent=memory_extraction')), null);
  const changed = structuredClone(proof), wrong = encodeLine({ ...error, requestBodyValues: { ...error.requestBodyValues, messages: [{ role: 'user', content: 'another task' }] } });
  changed.source_lines[0] = { bytes_base64: wrong.toString('base64'), sha256: sha(wrong), size: wrong.length, line_number: 1 };
  assert.throws(() => verifyNativeHttpFailure(changed, scope), /BINDING_INVALID/);
});
function state() { return { identity: { batch_id: 'batch', unit_id: 'loomy-macos', task_id: 'task', attempt_id: 'attempt' },
  phase: 'COMPLETED', session: { thread_id: 'ses_root', turn_id: 'msg_user', session_id: 'ses_root', cwd: options.workspace },
  execution: { duration_seconds: 1.2 } }; }

test('Loomy binds the exact native prompt, root session, model and high variant', () => {
  const result = verifyBinding(fixture(), options); checkNativeModel(result);
  assert.equal(result.user.id, 'msg_user'); assert.equal(result.final.id, 'msg_final');
  for (const edit of [n => { n.sessions[0].directory = '/other'; }, n => { n.parts[0].data = JSON.stringify({ type: 'text', text: 'different' }); },
    n => { n.messages[0].data = JSON.stringify({ role: 'user', model: { providerID: 'imodel', modelID: 'spark-x2.6', variant: 'low' } }); },
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

test('Loomy batch preserves the first preparation failure without resuming a zero-send attempt', async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'loomy-queue-test-')));
  try {
    const taskId = 'task-one', taskRoot = join(root, 'execution/tasks', taskId);
    await mkdir(join(taskRoot, 'workspace'), { recursive: true });
    await writeFile(join(taskRoot, 'prompt.txt'), prompt);
    const manifest = { schema_id: 'urn:wildclawbench:schema:general-e2e:package-manifest:v1', manifest_kind: 'execution',
      batch_id: 'batch', unit_id: 'loomy-macos', dataset: { id: 'fixture', digest: 'a'.repeat(64) }, task_ids: [taskId],
      unit: { harness: { id: 'loomy', platform: 'macos-arm64' }, model: { requested_id: 'spark-x2.6', reasoning_effort: 'high' } },
      tasks: [{ task_id: taskId, workspace: { path: 'execution/tasks/' + taskId + '/workspace' },
        prompt: { path: 'execution/tasks/' + taskId + '/prompt.txt', sent_sha256: sha(Buffer.from(prompt)) } }] };
    const config = { schema_version: 'wildclawbench.general-e2e-loomy-run-config/v1', execution_concurrency: 3 };
    config.config_digest = digest(config);
    await writeFile(join(root, 'manifest.json'), jsonBytes(manifest)); await writeFile(join(root, 'run-config.json'), jsonBytes(config));
    let calls = 0;
    const queue = await runBatch({ unitRoot: root, runConfig: join(root, 'run-config.json'), queueId: 'test', runSlots: 1 }, {
      executeTask: async options => {
        calls++; if (options.resume) throw Error('UNEXPECTED_ZERO_SEND_RESUME');
        const context = await loadTask(options);
        const journal = { version: '0.1.1', identity: { batch_id: 'batch', unit_id: 'loomy-macos', task_id: taskId, attempt_id: 'original' },
          input_locks: context.locks, phase: 'NEEDS_ATTENTION', dispatch_attempt_count: 0, send_status: 'not_sent', history: [] };
        await writeFile(context.journalPath, jsonBytes(journal));
        throw Error('ORIGINAL_PRE_SEND_FAILURE');
      },
    });
    assert.equal(calls, 1); assert.equal(queue.phase, 'NEEDS_ATTENTION');
    assert.equal(queue.tasks[0].error, 'ORIGINAL_PRE_SEND_FAILURE');
    assert.equal(queue.tasks[0].dispatch_attempt_count, 0); assert.equal(queue.tasks[0].attempt_id, 'original');
    assert.deepEqual(queue.tasks[0].error_history.map(row => row.message), ['ORIGINAL_PRE_SEND_FAILURE']);
    const context = await loadTask({ unitRoot: root, taskId, runConfig: join(root, 'run-config.json') });
    context.config.client = { version: '0.9.39' }; context.config.runtime = {};
    const journal = JSON.parse(await readFile(context.journalPath));
    assert.equal(buildState(context, journal).driver.version, '0.1.1');
  } finally { await rm(root, { recursive: true, force: true }); }
});


test('Loomy retains its native memory prefix separately from the exact frozen task', () => {
  const native = fixture();
  native.parts.unshift({ ...native.parts[0], id: 'part_memory', data: JSON.stringify({ type: 'text', text: EMPTY_MEMORY_CONTEXT }) });
  const binding = verifyBinding(native, options); checkNativeModel(binding);
  assert.deepEqual(binding.client_context_part_ids, ['part_memory']);
  const normalized = normalizeTrace(native, { state: state(), prompt, baseline: [] });
  assert.equal(normalized.events.filter(row => row.type === 'user_message').length, 1);
  assert.equal(normalized.events.find(row => row.type === 'user_message').content, prompt);
  assert.equal(normalized.events.find(row => row.native_type === 'client-memory-context').content, EMPTY_MEMORY_CONTEXT);
  native.parts[0].data = JSON.stringify({ type: 'text', text: 'unrecognized prefix' });
  assert.throws(() => verifyBinding(native, options), /PROMPT_MISMATCH/);
});

test('Loomy source repair requires exact frozen inputs and never resets an armed send counter', async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'loomy-repair-test-')));
  try {
    const context = { unitRoot: root, taskId: 'task', config: { version: '0.1.2' },
      locks: { manifest: 'a'.repeat(64), config: 'b'.repeat(64), prompt: 'c'.repeat(64) } };
    const journal = { version: '0.1.2', identity: { task_id: 'task', attempt_id: 'original' },
      dispatch_attempt_count: 1, input_locks: context.locks };
    await assert.rejects(sourceRepair(context, structuredClone(journal), null), /EXPLICIT_REPAIR_REQUIRED/);
    const hashes = {};
    for (const name of ['index.mjs', 'ui.mjs', 'execution.mjs', 'batch.mjs', 'collection.mjs', 'verification.mjs', 'native-state.py', 'macos-ax.swift'])
      hashes[name] = sha(await readFile(new URL('../../tools/report/e2e-shared/loomy/' + name, import.meta.url)));
    const archive = (role, value) => { const bytes = jsonBytes(value); return { role, sha256: sha(bytes), size: bytes.length, bytes_base64: bytes.toString('base64') }; };
    const proof = { profile: 'loomy-source-compatible-repair/v1', old_component_version: '0.1.2', new_component_version: COMPONENT_VERSION,
      manifest_sha256: context.locks.manifest, config_sha256: context.locks.config,
      armed_attempts: { task: 'original' }, unstarted_task_ids: [], new_source_hashes: hashes,
      critical_ui_sources: Object.fromEntries(['ui.mjs', 'macos-ax.swift'].map(name => [name, { old_sha256: hashes[name], new_sha256: hashes[name] }])),
      archives: [archive('journal:task', journal), archive('state:task', {}), archive('queue', {})] };
    const path = join(root, '.general-e2e/source-repairs/repair.json'); await mkdir(join(root, '.general-e2e/source-repairs'), { recursive: true });
    await writeFile(path, jsonBytes(proof));
    const repaired = structuredClone(journal); await sourceRepair(context, repaired, path);
    assert.equal(repaired.dispatch_attempt_count, 1); assert.equal(repaired.identity.attempt_id, 'original');
    assert.equal(repaired.version, '0.1.2'); assert.equal(repaired.observer_version, COMPONENT_VERSION);
    proof.unstarted_task_ids = ['later']; await writeFile(path, jsonBytes(proof));
    const later = { version: COMPONENT_VERSION, identity: { task_id: 'later', attempt_id: 'first-dispatch' },
      dispatch_attempt_count: 0, input_locks: context.locks };
    await sourceRepair({ ...context, taskId: 'later' }, later, path);
    later.dispatch_attempt_count = 1; later.sent_at = new Date(Date.now() + 1).toISOString();
    await sourceRepair({ ...context, taskId: 'later' }, later, path);
    assert.equal(later.dispatch_attempt_count, 1); assert.equal(later.source_repair_registrations.length, 1);
    proof.config_sha256 = '0'.repeat(64); await writeFile(path, jsonBytes(proof));
    await assert.rejects(sourceRepair(context, structuredClone(journal), path), /INPUT_MISMATCH/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
