import { randomUUID } from 'node:crypto';
import { mkdir, open, readFile, realpath, rename, unlink, writeFile } from 'node:fs/promises';
import { homedir, hostname } from 'node:os';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { artifact, assertIdle, ax, captureNative, command, digest, iso, jsonBytes, requireValue,
  runtimeIdentity, runtimeStatus, sha, verifyBinding, COMPONENT_VERSION } from './index.mjs';
import { fillPrompt, newTask, selectWorkspace, sendOnce } from './ui.mjs';

export const STATE_SCHEMA = 'wildclawbench.general-e2e-execution-state/v1';
export async function atomicJson(path, value) {
  const temporary = path + '.tmp-' + randomUUID();
  const file = await open(temporary, 'wx', 0o600);
  try { await file.writeFile(jsonBytes(value)); await file.sync(); } finally { await file.close(); }
  await rename(temporary, path);
}
export async function inside(root, path) {
  requireValue(typeof path === 'string' && path && !isAbsolute(path)
    && !path.split(/[\\/]/u).some(part => !part || part === '.' || part === '..'), 'INPUT_PATH_INVALID');
  const lexical = resolve(root, path), actual = await realpath(lexical);
  requireValue(actual === lexical && actual.startsWith(root + '/'), 'INPUT_PATH_OUTSIDE_UNIT');
  return actual;
}
export async function loadTask({ unitRoot, taskId, runConfig }) {
  unitRoot = await realpath(resolve(unitRoot));
  requireValue(/^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(taskId || ''), 'TASK_ID_INVALID');
  const [manifestBytes, configBytes] = await Promise.all([readFile(join(unitRoot, 'manifest.json')), readFile(runConfig)]);
  const manifest = JSON.parse(manifestBytes), config = JSON.parse(configBytes);
  const { config_digest, ...payload } = config;
  requireValue(config_digest === digest(payload) && config.schema_version === 'wildclawbench.general-e2e-loomy-run-config/v1', 'RUN_CONFIG_INVALID');
  requireValue(manifest.manifest_kind === 'execution' && manifest.schema_id === 'urn:wildclawbench:schema:general-e2e:package-manifest:v1'
    && manifest.unit?.harness?.id === 'loomy' && manifest.unit.harness.platform === 'macos-arm64', 'MANIFEST_UNSUPPORTED');
  requireValue(['spark-x2.6', 'Spark-X2.6', 'Spark-X2.6 正式版'].includes(manifest.unit.model?.requested_id)
    && manifest.unit.model?.reasoning_effort === 'high', 'REQUESTED_MODEL_UNSUPPORTED');
  const tasks = manifest.tasks.filter(row => row.task_id === taskId);
  requireValue(tasks.length === 1 && manifest.task_ids.includes(taskId), 'TASK_SCOPE_INVALID');
  const task = tasks[0];
  const [workspace, promptPath, taskRoot] = await Promise.all([
    inside(unitRoot, task.workspace.path), inside(unitRoot, task.prompt.path), inside(unitRoot, 'execution/tasks/' + taskId),
  ]);
  const promptBytes = await readFile(promptPath);
  requireValue(sha(promptBytes) === task.prompt.sent_sha256 && promptBytes.length > 0, 'PROMPT_HASH_MISMATCH');
  const control = join(taskRoot, 'automation', 'loomy');
  await mkdir(control, { recursive: true, mode: 0o700 });
  requireValue(await realpath(control) === control, 'CONTROL_PATH_UNSAFE');
  return { unitRoot, taskId, taskRoot, workspace, promptPath, prompt: promptBytes.toString('utf8'), manifest, config,
    control, statePath: join(control, 'automation-state.json'), journalPath: join(control, 'dispatch-journal.json'),
    locks: { manifest: sha(manifestBytes), config: sha(configBytes), prompt: sha(promptBytes) } };
}

export async function lease(path) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const value = { pid: process.pid, host: hostname(), instance_id: randomUUID(), acquired_at: new Date().toISOString() };
  const bytes = jsonBytes(value);
  const file = await open(path, 'wx', 0o600).catch(error => { throw Error(error.code === 'EEXIST' ? 'LOOMY_OWNER_LOCK_EXISTS:' + path : error.message); });
  try { await file.writeFile(bytes); await file.sync(); } finally { await file.close(); }
  return async () => {
    requireValue((await readFile(path)).equals(bytes), 'OWNER_LOCK_CHANGED');
    await unlink(path);
  };
}

export function checkNativeModel(binding) {
  requireValue(binding.user.parsed.model?.providerID === 'imodel'
    && binding.user.parsed.model?.modelID === 'spark-x2.6'
    && binding.user.parsed.variant === 'high', 'ACCEPTED_MODEL_OR_EFFORT_MISMATCH');
  requireValue(binding.messages.filter(row => row.session_id === binding.root.id && row.parsed.role === 'assistant')
    .every(row => row.parsed.providerID === 'imodel' && row.parsed.modelID === 'spark-x2.6'), 'ASSISTANT_MODEL_MISMATCH');
}

export function buildState(context, journal) {
  const session = journal.session;
  const finished = ['COMPLETED', 'FAILED'].includes(journal.phase);
  return { schema_version: STATE_SCHEMA,
    driver: { id: 'loomy-macos-general', version: COMPONENT_VERSION, harness: 'loomy', platform: 'macos-arm64' },
    identity: journal.identity, dataset: { id: context.manifest.dataset.id, digest: context.manifest.dataset.digest },
    phase: journal.phase, task_root: context.taskRoot, candidate_workspace: context.workspace,
    prompt: { path: context.promptPath, sha256: context.locks.prompt, send_status: journal.send_status, sent_at: journal.sent_at ?? null },
    send: { dispatch_attempt_count: journal.dispatch_attempt_count },
    session: { thread_id: session?.id ?? null, turn_id: session?.user_message_id ?? null, session_id: session?.id ?? null,
      cwd: session ? context.workspace : null, verified: Boolean(session), binding_evidence: session?.binding_evidence ?? [] },
    execution: { business_status: finished ? journal.business_status : null, started_at: journal.sent_at ?? null,
      finished_at: finished ? journal.finished_at : null,
      duration_seconds: finished && journal.sent_at ? (Date.parse(journal.finished_at) - Date.parse(journal.sent_at)) / 1000 : null,
      error: finished ? journal.native_error ?? null : null, cancellation_confirmed: null },
    human_assistance: { mode: 'automatic', operation_count: 0, semantic_intervention_count: 0 },
    extensions: { client: { version: context.config.client.version, model: 'spark-x2.6', reasoning_effort: 'high',
      model_verification_status: session ? 'verified' : 'unverified', model_identity_kind: 'native-opencode-user-model-and-variant',
      model_evidence_sha256: session?.binding_evidence?.[0]?.sha256 ?? null },
      loomy: { profile: 'loomy-opencode-sqlite/v1', runtime: context.config.runtime,
        final_message_id: journal.final_message_id ?? null, native_finished_at: journal.native_finished_at ?? null,
        attention: journal.attention ?? null, journal_path: relative(context.unitRoot, context.journalPath),
        workspace_selection: journal.workspace_selection ?? null } } };
}

export async function verifyRuntime(config) {
  const observed = await runtimeIdentity({ pid: config.process.pid, executable_path: config.process.executable_path }, config.runtime.database);
  requireValue(digest(observed) === digest(config.runtime), 'RUNTIME_IDENTITY_CHANGED');
  return runtimeStatus(config.runtime);
}

async function saveState(context, journal) {
  await atomicJson(context.journalPath, journal);
  const state = buildState(context, journal);
  await atomicJson(context.statePath, state);
  return state;
}

export async function observe(context, journal, allowedSessionIds = []) {
  requireValue(journal.dispatch_attempt_count === 1, 'OBSERVE_REQUIRES_ARMED_ATTEMPT');
  const status = await verifyRuntime(context.config);
  const native = await captureNative({ database: context.config.runtime.database, workspace: context.workspace,
    sessionId: journal.session?.id, python: context.config.python });
  const candidates = native.sessions.filter(row => row.parent_id === null && !journal.baseline.includes(row.id));
  if (candidates.length === 0) {
    assertIdle(status, allowedSessionIds);
    journal.phase = 'NEEDS_ATTENTION'; journal.send_status = 'uncertain'; journal.attention = 'NATIVE_ACCEPTANCE_NOT_YET_OBSERVED';
    return saveState(context, journal);
  }
  const binding = verifyBinding(native, { workspace: context.workspace, prompt: context.prompt,
    baseline: journal.baseline, sessionId: journal.session?.id });
  checkNativeModel(binding);
  assertIdle(status, [...allowedSessionIds, ...binding.session_ids]);
  requireValue(binding.user.time_created >= Date.parse(journal.sent_at) - 2000, 'NATIVE_USER_PREDATES_DISPATCH');
  if (!journal.session) {
    const bindingBytes = jsonBytes({ profile: 'loomy-native-dispatch-binding/v1', identity: journal.identity,
      prompt_sha256: context.locks.prompt, baseline_session_ids: journal.baseline, sent_at: journal.sent_at,
      native, runtime_status: status, process: context.config.process, runtime: context.config.runtime });
    const path = join(context.control, 'session-binding.json');
    await writeFile(path, bindingBytes, { flag: 'wx', mode: 0o600 });
    journal.session = { id: binding.root.id, user_message_id: binding.user.id,
      binding_evidence: [artifact(relative(context.unitRoot, path), bindingBytes)] };
  }
  journal.send_status = 'sent'; journal.phase = 'RUNNING'; journal.attention = null;
  const idle = binding.session_ids.every(id => !status[id] || status[id].type === 'idle');
  if (idle && binding.final?.parsed.error) {
    journal.phase = 'FAILED'; journal.business_status = 'candidate_error';
    journal.native_error = { code: 'LOOMY_NATIVE_MODEL_ERROR', message: JSON.stringify(binding.final.parsed.error) };
  } else if (idle && binding.final?.parsed.finish === 'stop') {
    verifyBinding(native, { workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline,
      sessionId: journal.session.id, terminal: true });
    journal.phase = 'COMPLETED'; journal.business_status = 'completed';
  }
  if (['COMPLETED', 'FAILED'].includes(journal.phase)) {
    journal.finished_at = new Date().toISOString();
    journal.final_message_id = binding.final.id;
    journal.native_finished_at = iso(binding.final.parsed.time?.completed);
    const bytes = jsonBytes({ native, runtime_status: status, observed_at: journal.finished_at });
    const path = join(context.control, 'native-terminal.json');
    try { await writeFile(path, bytes, { flag: 'wx', mode: 0o600 }); }
    catch (error) { if (error.code !== 'EEXIST') throw error; throw Error('LOOMY_TERMINAL_ALREADY_FROZEN'); }
    journal.terminal_evidence = artifact(relative(context.unitRoot, path), bytes);
  }
  return saveState(context, journal);
}

export async function executeTask(options) {
  const context = await loadTask(options);
  const releaseOwner = await lease(join(context.control, 'owner.lock'));
  let journal;
  try {
    try { journal = JSON.parse(await readFile(context.journalPath, 'utf8')); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (journal) {
      requireValue(options.resume === true, 'ATTEMPT_EXISTS_USE_RESUME');
      requireValue(digest(journal.input_locks) === digest(context.locks), 'FROZEN_INPUT_CHANGED');
      requireValue(journal.identity.task_id === context.taskId && journal.identity.batch_id === context.manifest.batch_id
        && journal.identity.unit_id === context.manifest.unit_id, 'JOURNAL_IDENTITY_CHANGED');
      if (['COMPLETED', 'FAILED'].includes(journal.phase)) return { state_file: context.statePath, state: buildState(context, journal) };
      // A resumed controller never sends, including after an uncertain click.
      requireValue(journal.dispatch_attempt_count === 1, 'ZERO_SEND_ATTEMPT_NEEDS_EXPLICIT_PREPARATION_RECOVERY');
    } else {
      requireValue(!options.resume, 'RESUME_WITHOUT_ATTEMPT');
      const baseline = await captureNative({ database: context.config.runtime.database, python: context.config.python });
      journal = { schema_version: 'wildclawbench.general-e2e-loomy-dispatch-journal/v1', version: COMPONENT_VERSION,
        identity: { batch_id: context.manifest.batch_id, unit_id: context.manifest.unit_id, task_id: context.taskId, attempt_id: 'loomy-' + randomUUID() },
        input_locks: context.locks, phase: 'PENDING', dispatch_attempt_count: 0, send_status: 'not_sent',
        baseline: baseline.session_index.map(row => row.id), history: [] };
      await saveState(context, journal);
      const releaseUi = await lease(join(homedir(), '.local/state/wildclawbench/ui-locks/loomy-' + context.config.process.pid + '.lock'));
      try {
        assertIdle(await verifyRuntime(context.config), options.allowedSessionIds || []);
        const existing = await captureNative({ database: context.config.runtime.database, workspace: context.workspace, python: context.config.python });
        requireValue(existing.sessions.length === 0, 'WORKSPACE_ALREADY_HAS_NATIVE_SESSION');
        const save = async (label, snapshot) => {
          const path = join(context.control, String(journal.history.length).padStart(4, '0') + '-' + label + '.json');
          const bytes = jsonBytes(snapshot); await writeFile(path, bytes, { flag: 'wx', mode: 0o600 });
          journal.history.push({ at: new Date().toISOString(), event: label, ...artifact(relative(context.unitRoot, path), bytes) });
          await atomicJson(context.journalPath, journal);
        };
        await newTask(context.config, save);
        journal.workspace_selection = await selectWorkspace(context.config, context.workspace, save);
        const taskConfig = { ...context.config, configuration: { ...context.config.configuration,
          permission_label: journal.workspace_selection.configuration.permission_label } };
        await fillPrompt(taskConfig, context.prompt, save);
        assertIdle(await verifyRuntime(context.config), options.allowedSessionIds || []);
        const finalBaseline = await captureNative({ database: context.config.runtime.database, workspace: context.workspace, python: context.config.python });
        requireValue(finalBaseline.sessions.length === 0, 'WORKSPACE_SESSION_APPEARED_BEFORE_SEND');
        journal.baseline = finalBaseline.session_index.map(row => row.id);
        journal.sent_at = new Date().toISOString();
        journal.send_status = 'intent_persisted'; journal.dispatch_attempt_count = 1;
        await saveState(context, journal);
        try { await sendOnce(taskConfig, context.prompt); journal.click_returned_at = new Date().toISOString(); }
        catch (error) { journal.click_error = error.message; journal.send_status = 'uncertain'; }
        await saveState(context, journal);
      } finally { await releaseUi(); }
    }
    const bindingDeadline = Date.now() + (options.identityTimeoutMs || 120000);
    do {
      const state = await observe(context, journal, options.allowedSessionIds || []);
      if (['COMPLETED', 'FAILED'].includes(state.phase) || options.observeOnce
        || journal.session && options.detachAfterSubmit || !journal.session && Date.now() >= bindingDeadline) {
        return { state_file: context.statePath, state };
      }
      await delay(options.pollIntervalMs || 1000);
    } while (true); // There is no candidate task deadline.
  } catch (error) {
    if (journal && !['COMPLETED', 'FAILED'].includes(journal.phase)) {
      journal.phase = 'NEEDS_ATTENTION'; journal.attention = error.message;
      if (journal.dispatch_attempt_count === 1 && journal.send_status !== 'sent') journal.send_status = 'uncertain';
      await saveState(context, journal);
    }
    throw error;
  } finally { await releaseOwner(); }
}
