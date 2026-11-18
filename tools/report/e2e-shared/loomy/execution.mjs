import { randomUUID } from 'node:crypto';
import { mkdir, open, readFile, realpath, rename, unlink, writeFile } from 'node:fs/promises';
import { homedir, hostname } from 'node:os';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { artifact, assertArchivedFailuresIdle, assertIdle, assertNativeActivity, ax, captureNative, captureNativeHttpFailure, command, currentOwnedRuntime, digest, iso, jsonBytes, requireValue,
  runtimeIdentity, runtimeStatus, statusUrl, sha, uiConfiguration, verifyBinding, verifyNativeLengthFailure, verifyNativeTerminalFailure,
  abortedQuestionReceipts, nativeTerminalFailureKind, waitNativeActivity, COMPONENT_VERSION } from './index.mjs';
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

export async function sourceRepair(context, journal, path) {
  if (!path) {
    requireValue(journal.version === COMPONENT_VERSION && context.config.version === COMPONENT_VERSION,
      'SOURCE_VERSION_CHANGED_EXPLICIT_REPAIR_REQUIRED');
    return;
  }
  const absolute = resolve(path);
  requireValue(absolute.startsWith(join(context.unitRoot, '.general-e2e/source-repairs') + '/')
    && await realpath(absolute) === absolute, 'SOURCE_REPAIR_PATH_INVALID');
  const bytes = await readFile(absolute), proof = JSON.parse(bytes);
  requireValue(proof.profile === 'loomy-source-compatible-repair/v1' && proof.new_component_version === COMPONENT_VERSION
    && proof.old_component_version === context.config.version && proof.manifest_sha256 === context.locks.manifest
    && proof.config_sha256 === context.locks.config, 'SOURCE_REPAIR_INPUT_MISMATCH');
  requireValue(Array.isArray(proof.archives) && proof.archives.length >= 3
    && Object.values(proof.critical_ui_sources || {}).length >= 2
    && Object.values(proof.critical_ui_sources).every(row => row.old_sha256 === row.new_sha256), 'SOURCE_REPAIR_UI_CHANGED');
  for (const name of ['index.mjs', 'ui.mjs', 'execution.mjs', 'batch.mjs', 'collection.mjs', 'verification.mjs', 'native-state.py', 'macos-ax.swift']) {
    requireValue(sha(await readFile(new URL('./' + name, import.meta.url))) === proof.new_source_hashes?.[name], 'SOURCE_REPAIR_RUNNING_SOURCE_MISMATCH');
  }
  for (const row of proof.archives) {
    const data = Buffer.from(row.bytes_base64, 'base64');
    requireValue(sha(data) === row.sha256 && data.length === row.size, 'SOURCE_REPAIR_ARCHIVE_DRIFT');
  }
  const registered = journal.source_repair_registrations?.find(row => row.sha256 === sha(bytes)
    && row.attempt_id === journal.identity.attempt_id && row.dispatch_attempt_count === 0
    && row.component_version === (journal.dispatch_driver_version || journal.version) && journal.sent_at && Date.parse(row.at) <= Date.parse(journal.sent_at));
  const registeredFirstDispatch = registered && proof.unstarted_task_ids?.includes(context.taskId)
    && (journal.dispatch_driver_version || journal.version) === proof.new_component_version;
  if (journal.dispatch_attempt_count === 1 && !registeredFirstDispatch) {
    requireValue(proof.armed_attempts?.[context.taskId] === journal.identity.attempt_id, 'SOURCE_REPAIR_ARMED_SCOPE_MISMATCH');
    const previous = proof.archives.find(row => row.role === 'journal:' + context.taskId);
    requireValue(previous, 'SOURCE_REPAIR_PRIOR_JOURNAL_MISSING');
    const old = JSON.parse(Buffer.from(previous.bytes_base64, 'base64'));
    requireValue(old.identity.attempt_id === journal.identity.attempt_id && old.dispatch_attempt_count === 1
      && digest(old.input_locks) === digest(context.locks), 'SOURCE_REPAIR_ATTEMPT_REPLACED');
  } else if (journal.dispatch_attempt_count === 0) {
    requireValue(proof.unstarted_task_ids?.includes(context.taskId), 'SOURCE_REPAIR_UNSTARTED_SCOPE_MISMATCH');
    journal.source_repair_registrations ??= [];
    if (!journal.source_repair_registrations.some(row => row.sha256 === sha(bytes))) journal.source_repair_registrations.push({
      sha256: sha(bytes), at: new Date().toISOString(), attempt_id: journal.identity.attempt_id,
      dispatch_attempt_count: 0, component_version: COMPONENT_VERSION,
    });
  }
  const descriptor = artifact(relative(context.unitRoot, absolute), bytes);
  journal.source_repairs ??= [];
  if (!journal.source_repairs.some(row => row.sha256 === descriptor.sha256)) journal.source_repairs.push(descriptor);
  journal.observer_version = COMPONENT_VERSION;
}

export function checkNativeModel(binding) {
  requireValue(binding.user.parsed.model?.providerID === 'imodel'
    && binding.user.parsed.model?.modelID === 'spark-x2.6'
    && binding.user.parsed.model.variant === 'high', 'ACCEPTED_MODEL_OR_EFFORT_MISMATCH');
  requireValue(binding.messages.filter(row => row.session_id === binding.root.id && row.parsed.role === 'assistant')
    .every(row => row.parsed.providerID === 'imodel' && row.parsed.modelID === 'spark-x2.6' && row.parsed.variant === 'high'), 'ASSISTANT_MODEL_MISMATCH');
}

export function buildState(context, journal) {
  const session = journal.session;
  const finished = ['COMPLETED', 'FAILED'].includes(journal.phase);
  return { schema_version: STATE_SCHEMA,
    driver: { id: 'loomy-macos-general', version: journal.dispatch_driver_version || journal.version, harness: 'loomy', platform: 'macos-arm64' },
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
    human_assistance: journal.human_assistance || { mode: 'automatic', operation_count: 0, semantic_intervention_count: 0 },
    extensions: { client: { version: context.config.client.version, model: 'spark-x2.6', reasoning_effort: 'high',
      model_verification_status: session ? 'verified' : 'unverified', model_identity_kind: 'native-opencode-user-model-and-variant',
      model_evidence_sha256: session?.binding_evidence?.[0]?.sha256 ?? null },
      loomy: { profile: 'loomy-opencode-sqlite/v1', runtime: context.config.runtime,
        runtime_rebindings: journal.runtime_rebindings || [],
        runtime_absence_before_dispatch: journal.runtime_absence_before_dispatch || null,
        ...(journal.native_http_failure ? { native_http_failure: journal.native_http_failure } : {}),
        ...(journal.native_length_failure ? { native_length_failure: journal.native_length_failure } : {}),
        ...(journal.native_terminal_failure ? { native_terminal_failure: journal.native_terminal_failure } : {}),
        final_message_id: journal.final_message_id ?? null, native_finished_at: journal.native_finished_at ?? null,
        attention: journal.attention ?? null, journal_path: relative(context.unitRoot, context.journalPath),
        source_repairs: journal.source_repairs || [], observer_version: journal.observer_version || journal.version,
        workspace_selection: journal.workspace_selection ?? null } } };
}

export async function verifyRuntime(config, workspace = null) {
  const observed = await runtimeIdentity({ pid: config.process.pid, executable_path: config.process.executable_path }, config.runtime.database);
  requireValue(digest(observed) === digest(config.runtime), 'RUNTIME_IDENTITY_CHANGED');
  return runtimeStatus(config.runtime, workspace);
}

export function applyJournalRuntime(context, journal) {
  if (journal.runtime_binding) context.config = { ...context.config, runtime: journal.runtime_binding };
}
async function recordNativeHttpFailure(context, journal, runtime, native) {
  if (journal.native_http_failure) return JSON.parse(await readFile(join(context.unitRoot, journal.native_http_failure.path), 'utf8'));
  const proof = await captureNativeHttpFailure(context, journal, runtime, native);
  if (!proof) return null;
  const bytes = jsonBytes(proof), path = join(context.control, 'native-http-failure.json');
  await writeFile(path, bytes, { flag: 'wx', mode: 0o600 });
  journal.native_http_failure = artifact(relative(context.unitRoot, path), bytes);
  return proof;
}
export async function refreshRuntime(context, journal, allowedSessionIds = []) {
  applyJournalRuntime(context, journal);
  const previous = context.config.runtime;
  let current;
  try {
    const until = Date.now() + 5000;
    do {
      try { current = await currentOwnedRuntime(context.config); break; }
      catch (error) { if (error.message !== 'LOOMY_RUNTIME_STARTING' || Date.now() >= until) throw error; }
      await delay(100);
    } while (true);
  }
  catch (error) {
    if (!['LOOMY_RUNTIME_NOT_RUNNING', 'LOOMY_RUNTIME_STARTING'].includes(error.message)) throw error;
    if (journal.dispatch_attempt_count === 0) {
      const native = await waitNativeActivity({ database: previous.database, python: context.config.python,
        archivedFailures: context.config.archived_http_failures });
      requireValue(sha(await readFile(previous.executable)) === previous.binary_sha256, 'LAZY_RUNTIME_BINARY_CHANGED');
      journal.runtime_absence_before_dispatch = { observed_at: journal.runtime_absence_before_dispatch?.observed_at || new Date().toISOString(), native,
        app_process: context.config.process, dispatch_attempt_count: 0, attempt_id: journal.identity.attempt_id,
        policy: 'normal-client-first-dispatch-starts-runtime; no-extra-prompt' };
      return false;
    }
    if (journal.runtime_absence_before_dispatch && !journal.session) return false;
    if (error.message === 'LOOMY_RUNTIME_STARTING' && journal.runtime_binding) return false;
    throw error;
  }
  if (digest(previous) !== digest(current)) {
    const native = await captureNative({ database: current.database, workspace: journal.dispatch_attempt_count === 1 ? context.workspace : null,
      sessionId: journal.session?.id, python: context.config.python });
    const lazyStart = journal.runtime_absence_before_dispatch && !journal.session && journal.sent_at
      && journal.runtime_absence_before_dispatch.attempt_id === journal.identity.attempt_id
      && Date.parse(journal.runtime_absence_before_dispatch.observed_at) <= Date.parse(journal.sent_at);
    if (journal.dispatch_attempt_count === 1 && !lazyStart) {
      let binding;
      try { binding = verifyBinding(native, { workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline,
        sessionId: journal.session?.id, terminal: true }); }
      catch (error) {
        binding = verifyBinding(native, { workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline, sessionId: journal.session?.id });
        if (error.message !== 'LOOMY_NATIVE_FINAL_NOT_COMPLETE') throw error;
        if (nativeTerminalFailureKind(binding)) await recordNativeTerminalFailure(context, journal, current, native, await runtimeStatus(current, context.workspace), previous);
        else if (binding.final?.parsed.finish === 'length') await recordNativeLengthFailure(context, journal, current, native, await runtimeStatus(current, context.workspace));
        else if (!await recordNativeHttpFailure(context, journal, current, native)) throw error;
      }
      checkNativeModel(binding);
      const statuses = await runtimeStatus(current, context.workspace);
      requireValue(binding.session_ids.every(id => !statuses[id] || statuses[id].type === 'idle'), 'RUNTIME_REBIND_NATIVE_STILL_ACTIVE');
    } else if (journal.dispatch_attempt_count === 0) assertNativeActivity(native, allowedSessionIds, context.config.archived_http_failures);
    journal.runtime_rebindings = [...(journal.runtime_rebindings || []), { observed_at: new Date().toISOString(),
      previous, current, native, policy: journal.native_http_failure ? 'same-main-app-binary-database; bound-native-http-failure-idle'
        : lazyStart ? 'same-main-app-binary-database; initial-dispatch-after-recorded-absence'
        : 'same-main-app-binary-database; armed-execution-native-complete-only' }];
  }
  journal.runtime_binding = current;
  context.config = { ...context.config, runtime: current };
  return true;
}

async function recordNativeLengthFailure(context, journal, runtime, native, status) {
  if (journal.native_length_failure) return verifyNativeLengthFailure(JSON.parse(await readFile(join(context.unitRoot, journal.native_length_failure.path))),
    { native, workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline, sessionId: journal.session.id, identity: journal.identity });
  const binding = verifyBinding(native, { workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline, sessionId: journal.session?.id });
  const proof = { profile: 'loomy-native-output-length-failure/v1', identity: journal.identity, prompt_sha256: context.locks.prompt,
    session_id: binding.root.id, final_message_id: binding.final.id, runtime, runtime_status: status,
    observed_at: new Date().toISOString(), runtime_status_scope: { directory: context.workspace, endpoint: statusUrl(runtime, context.workspace).href } };
  const verified = verifyNativeLengthFailure(proof, { native, workspace: context.workspace, prompt: context.prompt,
    baseline: journal.baseline, sessionId: binding.root.id, identity: journal.identity });
  const bytes = jsonBytes(proof), path = join(context.control, 'native-length-failure.json');
  await writeFile(path, bytes, { flag: 'wx', mode: 0o600 }); journal.native_length_failure = artifact(relative(context.unitRoot, path), bytes);
  return verified;
}
async function recordNativeTerminalFailure(context, journal, runtime, native, status, originalRuntime = runtime) {
  if (journal.native_terminal_failure) return verifyNativeTerminalFailure(JSON.parse(await readFile(join(context.unitRoot, journal.native_terminal_failure.path))),
    { native, workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline, sessionId: journal.session.id, identity: journal.identity });
  const binding = verifyBinding(native, { workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline, sessionId: journal.session?.id });
  const kind = nativeTerminalFailureKind(binding);
  const proof = { profile: 'loomy-native-terminal-failure/v1', kind, identity: journal.identity, prompt_sha256: context.locks.prompt,
    session_id: binding.root.id, final_message_id: binding.final.id, original_runtime: originalRuntime, observed_runtime: runtime,
    runtime_status: status, observed_at: new Date().toISOString(),
    runtime_status_scope: { directory: context.workspace, endpoint: statusUrl(runtime, context.workspace).href },
    question_terminations: abortedQuestionReceipts(binding),
    human_assistance: { mode: 'automatic', operation_count: kind === 'aborted' ? null : 0, semantic_intervention_count: kind === 'aborted' ? null : 0 } };
  const verified = verifyNativeTerminalFailure(proof, { native, workspace: context.workspace, prompt: context.prompt,
    baseline: journal.baseline, sessionId: binding.root.id, identity: journal.identity });
  const bytes = jsonBytes(proof), path = join(context.control, 'native-terminal-failure.json');
  await writeFile(path, bytes, { flag: 'wx', mode: 0o600 }); journal.native_terminal_failure = artifact(relative(context.unitRoot, path), bytes);
  journal.human_assistance = verified.human_assistance; return verified;
}

async function saveState(context, journal) {
  await atomicJson(context.journalPath, journal);
  const state = buildState(context, journal);
  await atomicJson(context.statePath, state);
  return state;
}

export async function observe(context, journal, allowedSessionIds = []) {
  requireValue(journal.dispatch_attempt_count === 1, 'OBSERVE_REQUIRES_ARMED_ATTEMPT');
  if (!await refreshRuntime(context, journal, allowedSessionIds)) {
    journal.phase = journal.session ? 'RUNNING' : 'NEEDS_ATTENTION'; journal.attention = 'WAITING_FOR_NORMAL_CLIENT_RUNTIME_START';
    if (!journal.session) journal.send_status = 'uncertain'; return saveState(context, journal);
  }
  const status = await verifyRuntime(context.config, context.workspace);
  const native = await captureNative({ database: context.config.runtime.database, workspace: context.workspace,
    sessionId: journal.session?.id, python: context.config.python });
  const candidates = native.sessions.filter(row => row.parent_id === null && !journal.baseline.includes(row.id));
  const users = candidates.length === 1 ? native.messages.filter(row => row.session_id === candidates[0].id && JSON.parse(row.data).role === 'user') : [];
  const texts = users.length === 1 ? native.parts.filter(row => row.message_id === users[0].id && JSON.parse(row.data).type === 'text') : [];
  if (candidates.length === 0 || candidates.length === 1 && (users.length === 0 || users.length === 1 && !texts.some(row => JSON.parse(row.data).text === context.prompt))) {
    journal.phase = 'NEEDS_ATTENTION'; journal.send_status = 'uncertain'; journal.attention = 'NATIVE_ACCEPTANCE_NOT_YET_OBSERVED';
    return saveState(context, journal);
  }
  const binding = verifyBinding(native, { workspace: context.workspace, prompt: context.prompt,
    baseline: journal.baseline, sessionId: journal.session?.id });
  checkNativeModel(binding);
  requireValue(!binding.parts.some(row => row.parsed.type === 'tool' && row.parsed.tool === 'question'
    && !['completed', 'error'].includes(row.parsed.state?.status)), 'PENDING_QUESTION_REQUIRES_INTERVENTION');
  assertIdle(status, [...allowedSessionIds, ...binding.session_ids]);
  requireValue(binding.user.time_created >= Date.parse(journal.sent_at) - 2000, 'NATIVE_USER_PREDATES_DISPATCH');
  if (!journal.session) {
    const bindingBytes = jsonBytes({ profile: 'loomy-native-dispatch-binding/v1', identity: journal.identity,
      prompt_sha256: context.locks.prompt, baseline_session_ids: journal.baseline, sent_at: journal.sent_at,
      pre_send_baseline_sha256: journal.baseline_evidence.sha256, allowed_session_ids: journal.allowed_session_ids,
      runtime_status_scope: { directory: context.workspace, endpoint: statusUrl(context.config.runtime, context.workspace).href },
      native, runtime_status: status, process: context.config.process, runtime: context.config.runtime });
    const path = join(context.control, 'session-binding.json');
    await writeFile(path, bindingBytes, { flag: 'wx', mode: 0o600 });
    journal.session = { id: binding.root.id, user_message_id: binding.user.id,
      binding_evidence: [artifact(relative(context.unitRoot, path), bindingBytes)] };
  }
  journal.send_status = 'sent'; journal.phase = 'RUNNING'; journal.attention = null;
  const idle = binding.session_ids.every(id => !status[id] || status[id].type === 'idle');
  if (idle && !binding.final?.parsed.finish && !binding.final?.parsed.error) await recordNativeHttpFailure(context, journal, context.config.runtime, native);
  if (idle && binding.final?.parsed.finish === 'length') {
    const verified = await recordNativeLengthFailure(context, journal, context.config.runtime, native, status);
    journal.phase = 'FAILED'; journal.business_status = 'candidate_error'; journal.native_error = verified.error;
  } else if (idle && nativeTerminalFailureKind(binding)) {
    const verified = await recordNativeTerminalFailure(context, journal, context.config.runtime, native, status);
    journal.phase = 'FAILED'; journal.business_status = 'candidate_error'; journal.native_error = verified.error;
  } else if (idle && (binding.final?.parsed.error || journal.native_http_failure)) {
    journal.phase = 'FAILED'; journal.business_status = 'candidate_error';
    const proof = journal.native_http_failure && JSON.parse(await readFile(join(context.unitRoot, journal.native_http_failure.path), 'utf8'));
    journal.native_error = proof ? { code: 'LOOMY_NATIVE_HTTP_ERROR', message: 'Native primary model HTTP '
      + (await import('./index.mjs')).parseNativeHttpError(Buffer.from(proof.source_lines.at(-1).bytes_base64, 'base64').toString('utf8')).error.statusCode + ' after provider retries' }
      : { code: 'LOOMY_NATIVE_MODEL_ERROR', message: JSON.stringify(binding.final.parsed.error) };
  } else if (idle && binding.final?.parsed.finish === 'stop') {
    verifyBinding(native, { workspace: context.workspace, prompt: context.prompt, baseline: journal.baseline,
      sessionId: journal.session.id, terminal: true });
    journal.phase = 'COMPLETED'; journal.business_status = 'completed';
  }
  if (['COMPLETED', 'FAILED'].includes(journal.phase)) {
    journal.finished_at = new Date().toISOString();
    journal.final_message_id = binding.final.id;
    journal.native_finished_at = iso(binding.final.parsed.time?.completed);
    const bytes = jsonBytes({ native, runtime_status: status, observed_at: journal.finished_at,
      runtime_status_scope: { directory: context.workspace, endpoint: statusUrl(context.config.runtime, context.workspace).href } });
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
  let journal, shouldPrepare = false;
  try {
    try { journal = JSON.parse(await readFile(context.journalPath, 'utf8')); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (journal) {
      requireValue(options.resume === true, 'ATTEMPT_EXISTS_USE_RESUME');
      requireValue(digest(journal.input_locks) === digest(context.locks), 'FROZEN_INPUT_CHANGED');
      requireValue(journal.identity.task_id === context.taskId && journal.identity.batch_id === context.manifest.batch_id
        && journal.identity.unit_id === context.manifest.unit_id, 'JOURNAL_IDENTITY_CHANGED');
      if (['COMPLETED', 'FAILED'].includes(journal.phase)) {
        const state = JSON.parse(await readFile(context.statePath, 'utf8'));
        requireValue(digest(state.identity) === digest(journal.identity) && state.phase === journal.phase, 'TERMINAL_STATE_IDENTITY_CHANGED');
        return { state_file: context.statePath, state };
      }
      await sourceRepair(context, journal, options.sourceRepairManifest);
      if (journal.dispatch_attempt_count === 0 && options.retryPreSendFailure) {
        requireValue(journal.send_status === 'not_sent' && !journal.sent_at, 'ZERO_SEND_RECOVERY_REQUIRES_NO_INTENT');
        const target = await captureNative({ database: context.config.runtime.database, workspace: context.workspace, python: context.config.python });
        requireValue(target.sessions.length === 0, 'ZERO_SEND_RECOVERY_NATIVE_SESSION_EXISTS');
        const previous = await Promise.all([context.journalPath, context.statePath, ...journal.history.map(row => join(context.unitRoot, row.path))].map(async path => {
          const bytes = await readFile(path); return { ...artifact(relative(context.unitRoot, path), bytes), bytes_base64: bytes.toString('base64') };
        }));
        await ax(context.config.ax_helper, context.config.process.pid, 'activate');
        const snapshot = await ax(context.config.ax_helper, context.config.process.pid), ui = uiConfiguration(snapshot);
        requireValue(ui.model_label === context.config.configuration.model_label && ['', context.prompt].includes(ui.composer.value), 'ZERO_SEND_RECOVERY_DRAFT_OR_MODEL_CHANGED');
        if (ui.composer.value) {
          requireValue(journal.history.at(-1)?.event === 'prompt-readback' && journal.workspace_selection?.workspace === context.workspace,
            'ZERO_SEND_RECOVERY_OWN_DRAFT_UNPROVED');
          const { act } = await import('./index.mjs');
          await act(context.config, ui.composer, 'set-value', { value: '' });
          requireValue(uiConfiguration(await ax(context.config.ax_helper, context.config.process.pid)).composer.value === '', 'ZERO_SEND_RECOVERY_DRAFT_NOT_CLEARED');
        }
        journal.pre_send_recoveries = [...(journal.pre_send_recoveries || []), { at: new Date().toISOString(), originals: previous,
          ui_before: snapshot, prompt_dispatches: 0 }];
        journal.history = []; journal.history_prefix = 'recovery-' + journal.pre_send_recoveries.length + '-';
        journal.phase = 'PENDING'; journal.attention = null; shouldPrepare = true;
      } else requireValue(journal.dispatch_attempt_count === 1, 'ZERO_SEND_ATTEMPT_NEEDS_EXPLICIT_PREPARATION_RECOVERY');
    } else {
      requireValue(!options.resume, 'RESUME_WITHOUT_ATTEMPT');
      const baseline = await captureNative({ database: context.config.runtime.database, python: context.config.python });
      journal = { schema_version: 'wildclawbench.general-e2e-loomy-dispatch-journal/v1', version: COMPONENT_VERSION,
        identity: { batch_id: context.manifest.batch_id, unit_id: context.manifest.unit_id, task_id: context.taskId, attempt_id: 'loomy-' + randomUUID() },
        input_locks: context.locks, phase: 'PENDING', dispatch_attempt_count: 0, send_status: 'not_sent',
        baseline: baseline.session_index.map(row => row.id), history: [] };
      await sourceRepair(context, journal, options.sourceRepairManifest);
      await saveState(context, journal);
      shouldPrepare = true;
    }
    if (shouldPrepare) {
      const releaseUi = await lease(join(homedir(), '.local/state/wildclawbench/ui-locks/loomy-' + context.config.process.pid + '.lock'));
      try {
        let runtimeReady = await refreshRuntime(context, journal, options.allowedSessionIds || []);
        await saveState(context, journal);
        if (runtimeReady) assertIdle(await verifyRuntime(context.config), options.allowedSessionIds || []);
        await waitNativeActivity({ database: context.config.runtime.database, python: context.config.python,
          allowed: options.allowedSessionIds || [], archivedFailures: context.config.archived_http_failures });
        const existing = await captureNative({ database: context.config.runtime.database, workspace: context.workspace, python: context.config.python });
        requireValue(existing.sessions.length === 0, 'WORKSPACE_ALREADY_HAS_NATIVE_SESSION');
        const save = async (label, snapshot) => {
          const path = join(context.control, (journal.history_prefix || '') + String(journal.history.length).padStart(4, '0') + '-' + label + '.json');
          const bytes = jsonBytes(snapshot); await writeFile(path, bytes, { flag: 'wx', mode: 0o600 });
          journal.history.push({ at: new Date().toISOString(), event: label, ...artifact(relative(context.unitRoot, path), bytes) });
          await atomicJson(context.journalPath, journal);
        };
        await newTask(context.config, save);
        journal.workspace_selection = await selectWorkspace(context.config, context.workspace, save);
        const taskConfig = { ...context.config, configuration: { ...context.config.configuration,
          permission_label: journal.workspace_selection.configuration.permission_label } };
        await fillPrompt(taskConfig, context.prompt, save);
        runtimeReady = await refreshRuntime(context, journal, options.allowedSessionIds || []);
        if (runtimeReady) assertIdle(await verifyRuntime(context.config), options.allowedSessionIds || []);
        const finalBaseline = await waitNativeActivity({ database: context.config.runtime.database, python: context.config.python,
          allowed: options.allowedSessionIds || [], archivedFailures: context.config.archived_http_failures });
        if (runtimeReady) await assertArchivedFailuresIdle(context.config.runtime, context.config.archived_http_failures);
        requireValue(!finalBaseline.session_index.some(row => row.directory === context.workspace), 'WORKSPACE_SESSION_APPEARED_BEFORE_SEND');
        journal.baseline = finalBaseline.session_index.map(row => row.id);
        const baselinePath = join(context.control, (journal.history_prefix || '') + 'pre-send-native-baseline.json'), baselineBytes = jsonBytes(finalBaseline);
        await writeFile(baselinePath, baselineBytes, { flag: 'wx', mode: 0o600 });
        journal.baseline_evidence = artifact(relative(context.unitRoot, baselinePath), baselineBytes);
        journal.allowed_session_ids = options.allowedSessionIds || [];
        journal.sent_at = new Date().toISOString();
        journal.dispatch_driver_version = COMPONENT_VERSION;
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
      journal.errors = [...(journal.errors || []), { at: new Date().toISOString(), message: error.message,
        phase: journal.phase, dispatch_attempt_count: journal.dispatch_attempt_count }];
      journal.initial_attention ??= error.message;
      journal.phase = 'NEEDS_ATTENTION'; journal.attention = error.message;
      if (journal.dispatch_attempt_count === 1 && journal.send_status !== 'sent') journal.send_status = 'uncertain';
      await saveState(context, journal);
    }
    throw error;
  } finally { await releaseOwner(); }
}
