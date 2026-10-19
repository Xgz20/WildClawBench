import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, rm, writeFile, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync, spawnSync } from 'node:child_process';
import test from 'node:test';
import { createQueueState, parseBatchArgs, resolveBatchPlan, runQueue, synchronizeTaskFromAutomation }
  from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/run_astronstudio_macos_batch.mjs';
import { executeSingleTask } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs';

const helper = fileURLToPath(new URL('../../tools/report/skills/general-e2e/execute-general-e2e/scripts/prepare_quota_retry.py', import.meta.url));
const single = new URL('../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs', import.meta.url).href;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const jsonBytes = value => Buffer.from(JSON.stringify(value, null, 2) + '\n');
const writeJson = async (path, value) => { await mkdir(dirname(path), { recursive: true }); await writeFile(path, jsonBytes(value)); };
const readJson = async path => JSON.parse(await readFile(path, 'utf8'));
const ids = ['successful-task', 'quota-task', 'pending-task'];
const quotaMessage = 'unexpected status 402 Payment Required: astron_points_exhausted, url: http://127.0.0.1:12345/v1/responses';
const exists = async path => access(path).then(() => true, () => false);

async function fixture() {
  const unitRoot = await mkdtemp(join(tmpdir(), 'general-quota-recovery-'));
  const prompt = 'Write the requested result in the workspace.';
  const initial = Buffer.from('pristine input\n');
  const tasks = ids.map((task_id, order) => ({ task_id, order,
    prompt: { path: `execution/tasks/${task_id}/PROMPT.md`, sent_sha256: sha(prompt) },
    workspace: { path: `execution/tasks/${task_id}/workspace`, entries: [
      { path: 'input.txt', kind: 'file', mode: '0644', size: initial.length, sha256: sha(initial) }] } }));
  const manifest = { schema_id: 'urn:wildclawbench:schema:general-e2e:package-manifest:v1', schema_version: 1,
    manifest_kind: 'execution', batch_id: 'arbitrary-batch', unit_id: 'arbitrary-unit',
    dataset: { id: 'fixture-dataset', digest: 'a'.repeat(64) }, task_ids: ids, tasks,
    unit: { harness: { id: 'astronstudio', version: '3.5.0', platform: 'macos-arm64' },
      model: { requested_id: 'GLM-5.2', reasoning_effort: 'high' }, execution_mode: 'automatic' } };
  await writeJson(join(unitRoot, 'manifest.json'), manifest);
  for (const task of tasks) {
    await mkdir(join(unitRoot, task.workspace.path), { recursive: true });
    await writeFile(join(unitRoot, task.prompt.path), prompt);
    await writeFile(join(unitRoot, task.workspace.path, 'input.txt'), initial, { mode: 0o644 });
  }
  const archive = join(unitRoot, 'execution.zip');
  execFileSync('python3', ['-c', `import pathlib,sys,zipfile
r=pathlib.Path(sys.argv[1])
with zipfile.ZipFile(sys.argv[2],'w') as z:
 for p in [r/'manifest.json',*sorted((r/'execution').rglob('*'))]:
  if p.is_file(): z.write(p,'fixture/'+p.relative_to(r).as_posix())
`, unitRoot, archive]);
  const runConfig = { config_digest: 'b'.repeat(64), harness: { client_version: '3.5.0' },
    control: { endpoint: 'http://127.0.0.1:9240', execution_concurrency: 3, maximum_execution_concurrency: 8 },
    tested_model: { display_name: 'GLM-5.2', reasoning_display: 'High', permission_display: '完全访问' } };
  const runConfigPath = join(unitRoot, 'run-config.json');
  await writeJson(runConfigPath, runConfig);
  const args = parseBatchArgs(['--unit-root', unitRoot, '--run-config', runConfigPath, '--queue-id', 'original-queue']);
  const plan = await resolveBatchPlan(args);
  const cfg = taskId => {
    const task = tasks.find(task => task.task_id === taskId);
    const controlRoot = join(unitRoot, '.general-e2e/execution', taskId);
    return { unitRoot, manifest, manifestPath: join(unitRoot, 'manifest.json'), task,
      taskRoot: dirname(join(unitRoot, task.prompt.path)), candidateWorkspace: join(unitRoot, task.workspace.path),
      prompt, promptPath: join(unitRoot, task.prompt.path), promptSha256: sha(prompt),
      runConfig, runConfigPath, controlRoot, stateFile: join(controlRoot, 'automation-state.json'),
      recordFile: join(controlRoot, 'execution-record.json'), finalResponseFile: join(controlRoot, 'final-response.md'),
      stateDatabase: join(unitRoot, 'state.sqlite'), appPath: '/Applications/AStudio.app', endpoint: runConfig.control.endpoint,
      expectedModel: 'GLM-5.2', expectedReasoning: 'High', expectedPermission: '完全访问',
      timeoutMs: 100, identityTimeoutMs: 120000, pollIntervalMs: 1,
      managedRunSlots: 3, allowedActiveSessionIds: [], resume: false, detachAfterSubmit: true, observeOnce: false };
  };
  const source = (taskId, phase, attemptId) => ({
    schema_version: 'wildclawbench.general-e2e-astronstudio-execution-state/v1',
    driver: { id: 'astronstudio-macos', version: 'fixture' },
    identity: { batch_id: manifest.batch_id, unit_id: manifest.unit_id, task_id: taskId, attempt_id: attemptId },
    dataset: manifest.dataset, phase, candidate_workspace: cfg(taskId).candidateWorkspace,
    run_config: { config_digest: runConfig.config_digest },
    prompt: { sha256: sha(prompt), send_status: 'sent', sent_at: '2026-10-19T00:00:00Z' },
    send: { dispatch_attempt_count: 1, dispatch_armed_at: '2026-10-19T00:00:00Z', dispatch_completed_at: '2026-10-19T00:00:00Z' },
    session: { verified: true, thread_id: 'old-thread-' + taskId, turn_id: 'old-turn-' + taskId,
      session_id: 'old-session-' + taskId, cwd: cfg(taskId).candidateWorkspace },
    client: { version: '3.5.0', model: 'GLM-5.2', reasoning: 'High', permission: '完全访问' },
    execution: { business_status: phase === 'COMPLETED' ? 'completed' : 'candidate_error',
      started_at: '2026-10-19T00:00:00Z', finished_at: '2026-10-19T00:01:00Z', duration_seconds: 60,
      error: phase === 'FAILED' ? { code: 'ASTRONSTUDIO_TURN_ERROR', message: quotaMessage } : null },
    evidence: {}, human_assistance: { mode: 'automatic', operation_count: 0, semantic_intervention_count: 0 }, history: [] });
  const successful = source(ids[0], 'COMPLETED', 'successful-original-attempt');
  const failed = source(ids[1], 'FAILED', 'old-quota-attempt');
  for (const state of [successful, failed]) {
    await writeJson(cfg(state.identity.task_id).stateFile, state);
    await writeJson(cfg(state.identity.task_id).recordFile, { identity: state.identity, phase: state.phase, execution: state.execution });
  }
  await writeFile(join(cfg(ids[0]).candidateWorkspace, 'result.txt'), 'successful frozen result');
  await writeFile(join(cfg(ids[1]).candidateWorkspace, 'input.txt'), 'changed by failed attempt');
  await writeFile(join(cfg(ids[1]).candidateWorkspace, 'partial.txt'), 'failed partial output');
  const queue = createQueueState(plan);
  synchronizeTaskFromAutomation(plan, queue.tasks[0], successful);
  synchronizeTaskFromAutomation(plan, queue.tasks[1], failed);
  queue.phase = 'NEEDS_ATTENTION';
  await writeJson(plan.queueStateFile, queue);
  const auth = JSON.parse(execFileSync('python3', [helper, '--describe-authorization', '--unit-root', unitRoot,
    '--queue-id', args.queueId, '--task-id', ids[1], '--execution-package', archive], { encoding: 'utf8' }));
  Object.assign(auth, { authorized_by: 'synthetic human', authorization_reference: 'test-only explicit approval',
    reason: 'Quota restored; retry only the failed task once', quota_restored: true, retry_authorized: true });
  const authPath = join(unitRoot, 'authorization.json');
  await writeJson(authPath, auth);
  return { unitRoot, args, plan, manifest, runConfig, cfg, failed, successful, auth, authPath, source };
}

function driver(f, counter, options = {}) {
  let sent = false;
  let clock = Date.parse('2026-10-19T01:00:00Z');
  const old = { ...f.failed.session, latest_turn_id: f.failed.session.turn_id,
    status: 'error', turn_state: 'error', active_turn_id: null, updated_at_ms: 1 };
  const dependencies = {
    probeAstronStudio: async () => ({ ready: true, failed_checks: [], app: { version: '3.5.0' },
      cdp: { endpoint: f.runConfig.control.endpoint }, state_database: { active_or_pending_session_count: 0 },
      frozen_run_config: f.runConfig }),
    queryNativeSessions: async () => [old, ...(sent ? [{ thread_id: 'retry-thread', turn_id: 'retry-turn',
      latest_turn_id: 'retry-turn', session_id: 'retry-session', cwd: f.cfg(ids[1]).candidateWorkspace,
      status: 'completed', turn_state: 'completed', active_turn_id: null, updated_at_ms: 100 }] : [])],
    discoverMainTarget: async () => ({ webSocketDebuggerUrl: 'ws://synthetic' }),
    connectCdp: async () => ({ close() {} }),
    prepareExecutionUi: async () => ({ ui: { thread_id: 'retry-thread' }, workspace: { method: 'synthetic' } }),
    fillPrompt: async () => {
      assert.equal(await readFile(join(f.cfg(ids[1]).candidateWorkspace, 'input.txt'), 'utf8'), 'pristine input\n');
      assert.equal(await exists(join(f.cfg(ids[1]).candidateWorkspace, 'partial.txt')), false);
    },
    waitForThreadStreamLease: async () => ({ threadId: 'retry-thread', leaseId: 'lease', admittedAt: clock }),
    ensureSendTargetReady: async () => {},
    clickSend: async () => { counter.count += 1; sent = true; return { clicked: true, thread_id: 'retry-thread' }; },
    currentThreadId: async () => 'retry-thread',
    queryFinalResponse: async () => 'Synthetic completed retry.',
    sleep: async () => {}, now: () => new Date(clock += 1000).toISOString(), nowMilliseconds: () => clock += 250,
    ...options,
  };
  return { dependencies, accept: () => { sent = true; } };
}

function queueDependencies(f, d, calls) {
  return { sleep: async () => {}, runTask: async (taskId, operation, active, authPath) => {
    calls.push({ taskId, operation });
    if (taskId === ids[0]) throw new Error('A successful task must never be run again');
    if (taskId === ids[2]) {
      assert.equal(operation, 'dispatch');
      const completed = f.source(taskId, 'COMPLETED', 'pending-first-attempt');
      await writeJson(f.cfg(taskId).stateFile, completed);
      await writeJson(f.cfg(taskId).recordFile, { identity: completed.identity });
    } else {
      await executeSingleTask({ ...f.cfg(taskId), resume: true,
        observeOnce: operation === 'observe', retryPreSendFailure: operation === 'retry-pre-send',
        quotaRetryAuthorization: ['retry-quota', 'retry-pre-send'].includes(operation) ? authPath : null }, d.dependencies);
    }
    return { code: 0, signal: null };
  } };
}

test('authorized retry continues the same queue and preserves successful and failed evidence', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    const before = await readFile(f.cfg(ids[0]).stateFile);
    const successfulRecord = await readFile(f.cfg(ids[0]).recordFile);
    const successfulPrompt = await readFile(f.cfg(ids[0]).promptPath);
    const successfulResult = await readFile(join(f.cfg(ids[0]).candidateWorkspace, 'result.txt'));
    const oldState = await readFile(f.cfg(ids[1]).stateFile);
    const args = { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath };
    const result = await runQueue(f.plan, args, queueDependencies(f, d, calls));
    assert.equal(result.phase, 'COMPLETED');
    assert.equal(result.identity.queue_digest, f.plan.queueDigest);
    assert.equal(result.tasks[1].selected_attempt_id, f.auth.new_attempt_id);
    assert.deepEqual(result.tasks[1].attempts.map(a => [a.attempt_id, a.selected]), [[f.auth.old_attempt_id, false], [f.auth.new_attempt_id, true]]);
    assert.equal(counter.count, 1);
    const newState = await readJson(f.cfg(ids[1]).stateFile);
    assert.equal(newState.prompt.sha256, f.failed.prompt.sha256);
    assert.equal(newState.human_assistance.operation_count, 1);
    assert.equal(newState.human_assistance.semantic_intervention_count, 0);
    assert.deepEqual(calls.filter(c => c.operation === 'dispatch').map(c => c.taskId), [ids[2]]);
    assert.deepEqual(await readFile(f.cfg(ids[0]).stateFile), before);
    assert.deepEqual(await readFile(f.cfg(ids[0]).recordFile), successfulRecord);
    assert.deepEqual(await readFile(f.cfg(ids[0]).promptPath), successfulPrompt);
    assert.deepEqual(await readFile(join(f.cfg(ids[0]).candidateWorkspace, 'result.txt')), successfulResult);
    const archive = join(f.unitRoot, '.general-e2e/quota-recoveries', ids[1], f.auth.new_attempt_id);
    assert.deepEqual(await readFile(join(archive, 'failed-control/automation-state.json')), oldState);
    assert.equal(await readFile(join(archive, 'failed-workspace/partial.txt'), 'utf8'), 'failed partial output');
    const receipt = await readJson(f.plan.queueReceiptFile);
    assert.equal(receipt.integrity.valid, true);
    assert.equal(receipt.integrity.no_duplicate_dispatch, true);
    const count = calls.length;
    await runQueue(f.plan, args, queueDependencies(f, d, calls));
    await runQueue(f.plan, { ...f.args, resume: true }, queueDependencies(f, d, calls));
    assert.equal(calls.length, count);
    assert.equal(counter.count, 1);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('worker loss after accepted retry is observed without sending again', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    const dependencies = queueDependencies(f, d, calls);
    const original = dependencies.runTask;
    dependencies.runTask = async (...args) => {
      const result = await original(...args);
      if (args[1] === 'retry-quota') throw new Error('synthetic worker loss after accepted send');
      return result;
    };
    await assert.rejects(runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath }, dependencies), /worker loss/u);
    assert.equal(counter.count, 1);
    const result = await runQueue(f.plan, { ...f.args, resume: true }, queueDependencies(f, d, calls));
    assert.equal(result.phase, 'COMPLETED');
    assert.equal(counter.count, 1);
    assert.equal(result.tasks[1].attempts.length, 2);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('old queue receipts are archived before a recovery completes', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    const previous = jsonBytes({ identity: f.plan.identity, phase: 'COMPLETED_WITH_FAILURES', original: true });
    await writeFile(f.plan.queueReceiptFile, previous);
    const result = await runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath }, queueDependencies(f, d, calls));
    assert.equal(result.phase, 'COMPLETED');
    const archive = result.tasks[1].quota_recoveries[0].previous_queue_receipt;
    assert.equal(archive.sha256, sha(previous));
    assert.deepEqual(await readFile(join(f.unitRoot, archive.path)), previous);
    assert.equal((await readJson(f.plan.queueReceiptFile)).integrity.valid, true);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('changed cached approval is rejected even when the queue already completed', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    const result = await runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath }, queueDependencies(f, d, calls));
    const cached = join(f.unitRoot, result.tasks[1].quota_recoveries[0].authorization_path);
    await writeFile(cached, Buffer.concat([await readFile(cached), Buffer.from(' ')]));
    await assert.rejects(runQueue(f.plan, { ...f.args, resume: true }, queueDependencies(f, d, calls)), /QUOTA_AUTHORIZATION_CACHE_SHA/u);
    assert.equal(counter.count, 1);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('process loss before send resumes the prepared new attempt with one send', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    const dependencies = queueDependencies(f, d, calls);
    dependencies.runTask = async (taskId, operation, active, authPath) => {
      assert.equal(operation, 'retry-quota');
      const config = { ...f.cfg(taskId), resume: true, quotaRetryAuthorization: authPath };
      const script = `import {executeSingleTask} from ${JSON.stringify(single)};
const c=JSON.parse(process.argv[1]);
const old=JSON.parse(process.argv[2]);
await executeSingleTask(c,{
 probeAstronStudio:async()=>({ready:true,failed_checks:[],app:{version:'3.5.0'},cdp:{endpoint:c.endpoint},state_database:{active_or_pending_session_count:0},frozen_run_config:c.runConfig}),
 queryNativeSessions:async()=>[{...old.session,latest_turn_id:old.session.turn_id,status:'error',turn_state:'error',active_turn_id:null}],
 discoverMainTarget:async()=>({webSocketDebuggerUrl:'ws://synthetic'}),connectCdp:async()=>({close(){}}),
 prepareExecutionUi:async()=>process.exit(77)
});`;
      const child = spawnSync(process.execPath, ['--input-type=module', '-e', script, JSON.stringify(config), JSON.stringify(f.failed)], { encoding: 'utf8' });
      assert.equal(child.status, 77, child.stderr);
      return { code: 77, signal: null };
    };
    const paused = await runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath }, dependencies);
    assert.equal(paused.phase, 'NEEDS_ATTENTION');
    const pending = await readJson(f.cfg(ids[1]).stateFile);
    assert.equal(pending.identity.attempt_id, f.auth.new_attempt_id);
    assert.equal(pending.send.dispatch_attempt_count, 0);
    const result = await runQueue(f.plan, { ...f.args, resume: true }, queueDependencies(f, d, calls));
    assert.equal(result.phase, 'COMPLETED');
    assert.equal(result.tasks[1].attempts.length, 2);
    assert.equal(counter.count, 1);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('uncertain retry sends are reconciled from their native identity, never resent', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    d.dependencies.clickSend = async () => { counter.count += 1; d.accept(); throw new Error('synthetic response loss after native acceptance'); };
    const result = await runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath }, queueDependencies(f, d, calls));
    assert.equal(result.phase, 'COMPLETED');
    assert.equal(counter.count, 1);
    await runQueue(f.plan, { ...f.args, resume: true }, queueDependencies(f, d, calls));
    assert.equal(counter.count, 1);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('an authorized retry with a zero-send UI failure resumes the same new attempt', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    const prepare = d.dependencies.prepareExecutionUi;
    d.dependencies.prepareExecutionUi = async () => { throw new Error('synthetic UI not ready before send'); };
    const dependencies = queueDependencies(f, d, calls);
    const failed = await runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath }, dependencies);
    assert.equal(failed.phase, 'NEEDS_ATTENTION');
    assert.equal(counter.count, 0);
    const newId = (await readJson(f.cfg(ids[1]).stateFile)).identity.attempt_id;
    d.dependencies.prepareExecutionUi = prepare;
    const completed = await runQueue(f.plan, { ...f.args, resume: true, retryPreSendTaskId: ids[1] }, dependencies);
    assert.equal(completed.phase, 'COMPLETED');
    assert.equal(completed.tasks[1].selected_attempt_id, newId);
    assert.equal(completed.tasks[1].attempts.length, 2);
    assert.equal(counter.count, 1);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('an unconfirmed send waits and later binds the same retry without another click', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    d.dependencies.clickSend = async () => { counter.count += 1; throw new Error('synthetic unknown send result'); };
    const dependencies = queueDependencies(f, d, calls);
    const paused = await runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath }, dependencies);
    assert.equal(paused.phase, 'NEEDS_ATTENTION');
    assert.equal(counter.count, 1);
    const stillPaused = await runQueue(f.plan, { ...f.args, resume: true }, dependencies);
    assert.equal(stillPaused.phase, 'NEEDS_ATTENTION');
    assert.equal(counter.count, 1);
    d.accept(); // Simulate delayed native acceptance becoming observable.
    const completed = await runQueue(f.plan, { ...f.args, resume: true }, dependencies);
    assert.equal(completed.phase, 'COMPLETED');
    assert.equal(counter.count, 1);
    assert.equal(completed.tasks[1].selected_attempt_id, f.auth.new_attempt_id);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('unexpected native acceptance blocks sending even if the local pending state says zero sends', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    const dependencies = queueDependencies(f, d, calls);
    // Stop after creating the authorized retry, before any send intent.
    d.dependencies.prepareExecutionUi = async () => { throw new Error('synthetic pre-send setup failure'); };
    await runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath }, dependencies);
    const state = await readJson(f.cfg(ids[1]).stateFile);
    assert.equal(state.send.dispatch_attempt_count, 0);
    // Reconstruct the exact pre-UI pending checkpoint to model a lost local
    // checkpoint while a native turn became visible independently.
    state.phase = 'PENDING'; state.execution.error = null;
    await writeJson(f.cfg(ids[1]).stateFile, state);
    d.accept(); counter.count = 1;
    await assert.rejects(runQueue(f.plan, { ...f.args, resume: true }, dependencies), /QUOTA_UNREGISTERED_NATIVE_TURN/u);
    assert.equal(counter.count, 1);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('a second quota failure needs a new authorization, not replay of the old approval', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [];
  const d = driver(f, counter, { queryNativeSessions: async () => [
    { ...f.failed.session, latest_turn_id: f.failed.session.turn_id, status: 'error', turn_state: 'error', active_turn_id: null, updated_at_ms: 1 },
    ...(counter.count ? [{ thread_id: 'retry-thread', turn_id: 'retry-turn', latest_turn_id: 'retry-turn', session_id: 'retry-session',
      cwd: f.cfg(ids[1]).candidateWorkspace, status: 'error', turn_state: 'error', active_turn_id: null, updated_at_ms: 100, error: quotaMessage }] : []),
  ] });
  try {
    const args = { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath };
    const first = await runQueue(f.plan, args, queueDependencies(f, d, calls));
    assert.equal(first.phase, 'NEEDS_ATTENTION');
    assert.equal(first.tasks[2].phase, 'PENDING');
    assert.equal(calls.some(call => call.operation === 'dispatch'), false);
    const second = await runQueue(f.plan, args, queueDependencies(f, d, calls));
    assert.equal(second.phase, 'NEEDS_ATTENTION');
    assert.equal(second.tasks[1].attempts.length, 2);
    assert.equal(counter.count, 1);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('recovery waits for already accepted peers and only observes them', async () => {
  const f = await fixture(), counter = { count: 0 }, calls = [], d = driver(f, counter);
  try {
    const peer = f.source(ids[2], 'RUNNING', 'original-inflight-attempt');
    peer.execution.business_status = null; peer.execution.finished_at = null;
    await writeJson(f.cfg(ids[2]).stateFile, peer);
    await writeJson(f.cfg(ids[2]).recordFile, { identity: peer.identity });
    const state = await readJson(f.plan.queueStateFile);
    synchronizeTaskFromAutomation(f.plan, state.tasks[2], peer);
    await writeJson(f.plan.queueStateFile, state);
    const args = { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath };
    const paused = await runQueue(f.plan, args, { runTask: async (taskId, operation) => {
      assert.equal(taskId, ids[2]); assert.equal(operation, 'observe'); return { code: 0 };
    } });
    assert.equal(paused.phase, 'NEEDS_ATTENTION');
    assert.equal(counter.count, 0);
    assert.equal(await readFile(join(f.cfg(ids[1]).candidateWorkspace, 'partial.txt'), 'utf8'), 'failed partial output');
    const dependencies = queueDependencies(f, d, calls), original = dependencies.runTask;
    dependencies.runTask = async (taskId, operation, ...rest) => {
      if (taskId === ids[2]) {
        assert.equal(operation, 'observe');
        const completed = f.source(taskId, 'COMPLETED', 'original-inflight-attempt');
        await writeJson(f.cfg(taskId).stateFile, completed); return { code: 0 };
      }
      return original(taskId, operation, ...rest);
    };
    const result = await runQueue(f.plan, { ...f.args, resume: true }, dependencies);
    assert.equal(result.phase, 'COMPLETED');
    assert.equal(result.tasks[2].selected_attempt_id, 'original-inflight-attempt');
    assert.equal(result.tasks[2].attempts.length, 1);
    assert.equal(counter.count, 1);
  } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
});

test('unapproved, drifted or wrong-target authorizations do not dispatch or alter workspaces', async () => {
  for (const change of [a => { a.retry_authorized = false; }, a => { a.quota_restored = false; },
    a => { a.old_state_sha256 = '0'.repeat(64); }, a => { a.old_workspace_sha256 = '0'.repeat(64); },
    a => { a.queue_digest = '0'.repeat(64); }, a => { a.task_id = ids[0]; },
    a => { a.execution_package.sha256 = '0'.repeat(64); }]) {
    const f = await fixture();
    try {
      const old = await readFile(f.cfg(ids[1]).stateFile);
      const workspace = await readFile(join(f.cfg(ids[1]).candidateWorkspace, 'input.txt'));
      const altered = structuredClone(f.auth); change(altered); await writeJson(f.authPath, altered);
      await assert.rejects(runQueue(f.plan, { ...f.args, resume: true, retryQuotaTaskId: ids[1], quotaRetryAuthorization: f.authPath },
        { runTask: async () => { throw new Error('Unexpected dispatch'); } }));
      assert.deepEqual(await readFile(f.cfg(ids[1]).stateFile), old);
      assert.deepEqual(await readFile(join(f.cfg(ids[1]).candidateWorkspace, 'input.txt')), workspace);
    } finally { await rm(f.unitRoot, { recursive: true, force: true }); }
  }
});
