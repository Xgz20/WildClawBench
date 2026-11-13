// Replays archived evidence only; never contacts a running desktop client.
import { readFile, realpath } from 'node:fs/promises';
import { isAbsolute, join, resolve } from 'node:path';
import { assertNativeActivity, digest, jsonBytes, PROFILE, requireValue, sameRuntimeInstallation, statusUrl, sha, verifyBinding } from './index.mjs';
import { normalizeTrace, resourceMetrics } from './collection.mjs';
import { checkNativeModel } from './execution.mjs';
import { assertConfiguration } from './ui.mjs';

export async function verifyArchivedLoomy(index, state, traceRoot) {
  if (index.adapter?.id !== PROFILE) {
    requireValue(state.driver?.harness !== 'loomy', 'TRACE_ADAPTER_MISMATCH');
    return null;
  }
  requireValue(state.driver?.harness === 'loomy' && state.driver.platform === 'macos-arm64'
    && digest(index.identity) === digest(state.identity), 'ARCHIVE_IDENTITY_MISMATCH');
  traceRoot = await realpath(traceRoot);
  const bytes = async path => {
    requireValue(typeof path === 'string' && !isAbsolute(path) && !path.includes('\\')
      && path.split('/').every(part => part && part !== '.' && part !== '..'), 'ARCHIVE_PATH_INVALID');
    const target = resolve(traceRoot, path);
    requireValue(await realpath(target) === target && target.startsWith(traceRoot + '/'), 'ARCHIVE_PATH_UNSAFE');
    return readFile(target);
  };
  const requiredRaw = ['raw/native-scoped-snapshot.json', 'raw/native-part-rows.jsonl', 'raw/native-message-rows.jsonl',
    'raw/driver-state.json', 'raw/dispatch-journal.json', 'raw/sent-prompt.txt', 'raw/frozen-run-config.json', 'raw/terminal-evidence.json', 'raw/pre-send-native-baseline.json'];
  const version = index.adapter.version.split('.').map(Number);
  if (version[0] > 0 || version[1] > 1 || version[1] === 1 && version[2] >= 5) requiredRaw.push('raw/current-scoped-snapshot.json');
  requireValue(requiredRaw.every(path => index.raw_trace.some(row => row.path === path))
    && index.binding_evidence.length === 1, 'ARCHIVE_SOURCE_SCOPE_INVALID');
  const load = async path => JSON.parse((await bytes(path)).toString('utf8'));
  const [native, journal, driver, config, terminal, promptBytes, transcript] = await Promise.all([
    load('raw/native-scoped-snapshot.json'), load('raw/dispatch-journal.json'), load('raw/driver-state.json'),
    load('raw/frozen-run-config.json'), load('raw/terminal-evidence.json'),
    bytes('raw/sent-prompt.txt'), bytes(index.transcript.path),
  ]);
  const { config_digest, ...payload } = config;
  for (const recovery of journal.pre_send_recoveries || []) {
    requireValue(recovery.prompt_dispatches === 0 || recovery.prompt_dispatches === undefined, 'ARCHIVE_PRE_SEND_RECOVERY_DISPATCH_MISMATCH');
    for (const original of recovery.originals) {
      const data = Buffer.from(original.bytes_base64, 'base64');
      requireValue(sha(data) === original.sha256 && data.length === original.size, 'ARCHIVE_PRE_SEND_RECOVERY_DRIFT');
    }
  }
  const runtimeChain = [config.runtime];
  for (const row of journal.runtime_rebindings || []) {
    requireValue(digest(row.previous) === digest(runtimeChain.at(-1))
      && sameRuntimeInstallation(row.previous, row.current), 'ARCHIVE_RUNTIME_REBIND_MISMATCH');
    runtimeChain.push(row.current);
  }
  const effectiveRuntime = journal.runtime_binding || config.runtime;
  requireValue(digest(effectiveRuntime) === digest(runtimeChain.at(-1)), 'ARCHIVE_RUNTIME_BINDING_MISMATCH');
  requireValue(config_digest === digest(payload) && config.client.version === '0.9.39'
    && config.runtime.health_version === '1.14.22'
    && config.transport === 'macos-native-accessibility'
    && sha(await bytes('raw/frozen-run-config.json')) === journal.input_locks.config, 'ARCHIVE_RUN_CONFIG_INVALID');
  requireValue(config.permission_policy === 'preserve-workspace-policy' && Array.isArray(journal.history)
    && index.raw_trace.length === requiredRaw.length + journal.history.length + (journal.source_repairs || []).length, 'ARCHIVE_PREPARATION_SCOPE_INVALID');
  for (const [i, receipt] of (journal.source_repairs || []).entries()) {
    const path = `raw/source-repairs/${i + 1}.json`, source = await bytes(path), repair = JSON.parse(source);
    requireValue(index.raw_trace.some(row => row.path === path) && sha(source) === receipt.sha256
      && source.length === receipt.size && repair.profile === 'loomy-source-compatible-repair/v1'
      && repair.manifest_sha256 === journal.input_locks.manifest && repair.config_sha256 === journal.input_locks.config,
      'ARCHIVE_SOURCE_REPAIR_MISMATCH');
    for (const old of repair.archives) {
      const data = Buffer.from(old.bytes_base64, 'base64');
      requireValue(sha(data) === old.sha256 && data.length === old.size, 'ARCHIVE_SOURCE_REPAIR_ORIGINAL_DRIFT');
    }
  }
  const ui = new Map();
  for (const [i, receipt] of journal.history.entries()) {
    requireValue(/^[a-z-]+$/u.test(receipt.event) && (!ui.has(receipt.event) || receipt.event.startsWith('promotional-')), 'ARCHIVE_PREPARATION_EVENT_INVALID');
    const path = `raw/ui-preparation/${i}-${receipt.event}.json`, source = await bytes(path);
    requireValue(index.raw_trace.some(row => row.path === path) && sha(source) === receipt.sha256
      && source.length === receipt.size, 'ARCHIVE_PREPARATION_HASH_MISMATCH');
    ui.set(receipt.event, JSON.parse(source));
  }
  const selection = journal.workspace_selection;
  requireValue(selection?.full_path_verified === true && selection.workspace === state.session.cwd
    && selection.selection_method === 'native-ui-menu-exact-full-path'
    && ui.get('workspace-full-path-readback')?.nodes?.filter(node => node.help === state.session.cwd).length === 1,
    'ARCHIVE_WORKSPACE_SELECTION_MISMATCH');
  const taskConfig = { ...config, configuration: { ...config.configuration, permission_label: selection.configuration.permission_label } };
  const prepared = ui.get('prompt-readback');
  requireValue(prepared?.pid === config.process.pid && prepared.frontmost_pid === config.process.pid,
    'ARCHIVE_PREPARATION_PROCESS_MISMATCH');
  requireValue(assertConfiguration(prepared, taskConfig).composer.value === promptBytes.toString('utf8'), 'ARCHIVE_PREPARED_PROMPT_MISMATCH');
  requireValue(digest(driver.identity) === digest(state.identity) && digest(journal.identity) === digest(state.identity)
    && driver.phase === state.phase && journal.phase === state.phase
    && digest(driver.execution) === digest(state.execution) && digest(driver.session) === digest(state.session)
    && journal.dispatch_attempt_count === 1 && state.send.dispatch_attempt_count === 1
    && journal.send_status === 'sent' && state.prompt.send_status === 'sent'
    && sha(promptBytes) === state.prompt.sha256 && sha(promptBytes) === journal.input_locks.prompt, 'ARCHIVE_DISPATCH_MISMATCH');
  requireValue(state.human_assistance.mode === 'automatic' && state.human_assistance.operation_count === 0
    && state.human_assistance.semantic_intervention_count === 0, 'ARCHIVE_HUMAN_INTERVENTION_UNSUPPORTED');
  const prompt = promptBytes.toString('utf8');
  const baselineBytes = await bytes('raw/pre-send-native-baseline.json'), baseline = JSON.parse(baselineBytes);
  requireValue(sha(baselineBytes) === journal.baseline_evidence.sha256 && baselineBytes.length === journal.baseline_evidence.size
    && digest(baseline.session_index.map(row => row.id)) === digest(journal.baseline)
    && state.prompt.sent_at === journal.sent_at && Date.parse(baseline.observed_at) <= Date.parse(journal.sent_at), 'ARCHIVE_PRE_SEND_BASELINE_MISMATCH');
  assertNativeActivity(baseline, journal.allowed_session_ids);
  const normalized = normalizeTrace(native, { state, prompt, baseline: journal.baseline });
  const old = verifyBinding(terminal.native, { workspace: state.session.cwd, prompt, baseline: journal.baseline,
    sessionId: state.session.session_id, terminal: state.phase === 'COMPLETED' });
  checkNativeModel(old);
  requireValue(normalized.binding.final?.id === journal.final_message_id && old.final?.id === journal.final_message_id
    && terminal.observed_at === state.execution.finished_at
    && terminal.runtime_status_scope?.directory === state.session.cwd
    && terminal.runtime_status_scope?.endpoint === statusUrl(effectiveRuntime, state.session.cwd).href
    && normalized.binding.session_ids.every(id => !terminal.runtime_status[id] || terminal.runtime_status[id].type === 'idle'), 'ARCHIVE_NATIVE_TERMINAL_MISMATCH');
  const content = snapshot => digest({ messages: snapshot.messages.map(({ id, session_id, data }) => ({ id, session_id, data })),
    parts: snapshot.parts.map(({ id, message_id, session_id, data }) => ({ id, message_id, session_id, data })) });
  requireValue(content(native) === content(terminal.native), 'ARCHIVE_NATIVE_CONTENT_CHANGED');
  requireValue((await bytes('raw/native-part-rows.jsonl')).equals(Buffer.from(native.parts.map(row => JSON.stringify(row)).join('\n') + '\n'))
    && (await bytes('raw/native-message-rows.jsonl')).equals(Buffer.from(native.messages.map(row => JSON.stringify(row)).join('\n') + '\n')), 'ARCHIVE_NATIVE_ROW_EXPORT_MISMATCH');
  requireValue(transcript.equals(Buffer.from(normalized.events.map(row => JSON.stringify(row)).join('\n') + '\n'))
    && digest(index.calls) === digest(normalized.calls)
    && index.normalization.native_event_count === normalized.native_event_count
    && index.normalization.normalized_event_count === normalized.events.length
    && index.normalization.filtered_native_event_count === normalized.filtered_native_event_count
    && digest(index.completeness.missing) === digest(normalized.missing), 'ARCHIVE_TRACE_REPLAY_MISMATCH');
  requireValue(index.completeness.status === (normalized.missing.length ? 'partial' : 'complete')
    && index.completeness.omitted_event_count === 0, 'ARCHIVE_COMPLETENESS_MISMATCH');
  for (const row of index.binding_evidence) {
    const proof = await load(row.path);
    requireValue(digest(proof.identity) === digest(state.identity) && proof.prompt_sha256 === sha(promptBytes)
      && digest(proof.process) === digest(config.process) && runtimeChain.some(runtime => digest(proof.runtime) === digest(runtime))
      && proof.pre_send_baseline_sha256 === sha(baselineBytes)
      && digest(proof.allowed_session_ids) === digest(journal.allowed_session_ids)
      && proof.runtime_status_scope?.directory === state.session.cwd
      && proof.runtime_status_scope?.endpoint === statusUrl(proof.runtime, state.session.cwd).href, 'ARCHIVE_INITIAL_BINDING_MISMATCH');
    const first = verifyBinding(proof.native, { workspace: state.session.cwd, prompt, baseline: journal.baseline, sessionId: state.session.session_id });
    checkNativeModel(first);
    requireValue(first.user.id === normalized.binding.user.id, 'ARCHIVE_NATIVE_USER_REPLACED');
  }
  if (state.phase === 'COMPLETED') requireValue(state.extensions.evidence?.final_response_sha256 === sha(Buffer.from(normalized.final_response)), 'ARCHIVE_FINAL_RESPONSE_MISMATCH');
  if (requiredRaw.includes('raw/current-scoped-snapshot.json')) {
    const live = await load('raw/current-scoped-snapshot.json'), scope = new Set(native.sessions.map(row => row.id));
    requireValue(sameRuntimeInstallation(effectiveRuntime, live.runtime)
      && live.native.sessions.every(row => !live.runtime_status[row.id] || live.runtime_status[row.id].type === 'idle'), 'ARCHIVE_COLLECTION_RUNTIME_MISMATCH');
    const content = snapshot => digest({ messages: snapshot.messages.map(({ id, session_id, data }) => ({ id, session_id, data })),
      parts: snapshot.parts.map(({ id, message_id, session_id, data }) => ({ id, message_id, session_id, data })) });
    requireValue(content(native) === content({ messages: live.native.messages.filter(row => scope.has(row.session_id)),
      parts: live.native.parts.filter(row => scope.has(row.session_id)) })
      && live.native.sessions.filter(row => !scope.has(row.id)).every(row => row.time_created > Date.parse(state.execution.finished_at)), 'ARCHIVE_POST_TERMINAL_SCOPE_MISMATCH');
  }
  return normalized;
}

export async function verifyLoomyResources(value, state, index, traceRoot) {
  if (index.adapter?.id !== PROFILE) return;
  const normalized = await verifyArchivedLoomy(index, state, traceRoot);
  const expected = resourceMetrics({ state, normalized, sources: value.collection.sources });
  requireValue(digest(value.metrics) === digest(expected.metrics) && digest(value.collection.coverage) === digest(expected.collection.coverage)
    && value.collection.status === expected.collection.status
    && digest(value.collection.warnings) === digest(expected.collection.warnings), 'ARCHIVE_RESOURCE_REPLAY_MISMATCH');
}
