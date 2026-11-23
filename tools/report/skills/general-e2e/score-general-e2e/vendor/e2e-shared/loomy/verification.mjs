import { SEND_GUARD_PROFILE } from './index.mjs';
import { requireFullAccess } from '../desktop-gui/formal-permission.mjs';
// Replays archived evidence only; never contacts a running desktop client.
import { lstat, readFile, realpath } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { artifact, assertNativeActivity, digest, isAbsentRuntime, jsonBytes, PROFILE, requireValue, sameRuntimeInstallation, statusUrl, sha, verifyBinding } from './index.mjs';
import { normalizeTrace, resourceMetrics } from './collection.mjs';
import { checkNativeModel } from './execution.mjs';
import { assertConfiguration, assertSendGuard, registeredWorkspaceItems } from './ui.mjs';

export async function readArchivedHttpFailure(recordPath, runtime) {
  requireValue(isAbsolute(recordPath), 'ARCHIVED_FAILURE_PATH_NOT_ABSOLUTE');
  const path = resolve(recordPath);
  const evidenceRoot = dirname(path);
  const unitRoot = resolve(evidenceRoot, '../../../..');
  const read = async target => {
    requireValue(await realpath(target) === target && (await lstat(target)).isFile(), 'ARCHIVED_FAILURE_UNSAFE_FILE');
    return readFile(target);
  };
  const recordBytes = await read(path);
  const record = JSON.parse(recordBytes);
  const identity = record.identity;
  const expected = join(unitRoot, 'evidence/tasks', identity.task_id, identity.attempt_id, 'execution-record.json');
  requireValue(path === expected && record.harness?.id === 'loomy' && record.phase === 'FAILED'
    && record.execution?.error?.code === 'LOOMY_NATIVE_HTTP_ERROR' && record.session?.verified
    && record.failure_evidence?.schema === 'verified-failed-output-evidence/v1', 'ARCHIVED_FAILURE_RECORD_INVALID');
  const receiptBytes = await read(join(unitRoot, 'receipts/collect-evidence-receipt.json'));
  const receipt = JSON.parse(receiptBytes);
  requireValue(receipt.schema_id === 'urn:wildclawbench:schema:general-e2e:receipt:v1'
    && receipt.stage === 'collect-evidence' && receipt.integrity?.valid === true
    && receipt.scope?.batch_id === identity.batch_id && receipt.scope?.unit_id === identity.unit_id
    && receipt.tasks?.some(row => row.task_id === identity.task_id && row.attempt_id === identity.attempt_id), 'ARCHIVED_FAILURE_RECEIPT_INVALID');
  const assertHash = (target, bytes, artifacts) => {
    const rows = artifacts.filter(row => row.path === relative(unitRoot, target));
    requireValue(rows.length === 1 && rows[0].sha256 === sha(bytes) && rows[0].size === bytes.length,
      'ARCHIVED_FAILURE_HASH_MISMATCH');
  };
  assertHash(path, recordBytes, receipt.artifacts);
  const manifestPath = join(evidenceRoot, 'evidence-manifest.json');
  const manifestBytes = await read(manifestPath);
  assertHash(manifestPath, manifestBytes, receipt.artifacts);
  const manifest = JSON.parse(manifestBytes);
  requireValue(digest(manifest.identity) === digest(identity), 'ARCHIVED_FAILURE_MANIFEST_INVALID');
  const traceRoot = join(evidenceRoot, 'trace');
  const indexPath = join(traceRoot, 'trace-index.json');
  const statePath = join(evidenceRoot, 'execution/automation-state.json');
  const [indexBytes, stateBytes] = await Promise.all([read(indexPath), read(statePath)]);
  assertHash(indexPath, indexBytes, manifest.artifacts);
  assertHash(statePath, stateBytes, manifest.artifacts);
  const index = JSON.parse(indexBytes), state = JSON.parse(stateBytes);
  for (const row of [index.transcript, ...index.raw_trace, ...index.binding_evidence]) {
    const target = resolve(traceRoot, row.path);
    requireValue(target.startsWith(traceRoot + '/'), 'ARCHIVED_FAILURE_UNSAFE_FILE');
    assertHash(target, await read(target), manifest.artifacts);
  }
  const source = state.extensions?.loomy;
  requireValue(digest(state.identity) === digest(identity) && state.phase === 'FAILED'
    && digest(state.execution?.error) === digest(record.execution.error)
    && state.session?.session_id === record.session.session_id && state.session.cwd === record.session.cwd
    && source?.native_http_failure && source.runtime.database === runtime.database
    && source.runtime.binary_sha256 === runtime.binary_sha256 && source.runtime.executable === runtime.executable,
    'ARCHIVED_FAILURE_RUNTIME_MISMATCH');
  const normalized = await verifyArchivedLoomy(index, state, traceRoot);
  const final = normalized?.binding.final;
  requireValue(final?.id === source.final_message_id && final.session_id === state.session.session_id,
    'ARCHIVED_FAILURE_TERMINAL_INVALID');
  return { session_id: final.session_id, directory: state.session.cwd, last_message_id: final.id,
    last_message_sha256: sha(final.data), completed_at: final.parsed.time.completed,
    execution_record: artifact(path, recordBytes), collect_receipt_sha256: sha(receiptBytes),
    evidence_manifest_sha256: sha(manifestBytes) };
}

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
  const failureBytes = journal.native_http_failure && await bytes('raw/native-http-failure.json');
  const lengthBytes = journal.native_length_failure && await bytes('raw/native-length-failure.json');
  const terminalFailureBytes = journal.native_terminal_failure && await bytes('raw/native-terminal-failure.json');
  if (terminalFailureBytes) {
    requiredRaw.push('raw/native-terminal-failure.json');
    requireValue(sha(terminalFailureBytes) === journal.native_terminal_failure.sha256 && terminalFailureBytes.length === journal.native_terminal_failure.size
      && digest(state.extensions?.loomy?.native_terminal_failure) === digest(journal.native_terminal_failure)
      && index.raw_trace.some(row => row.path === 'raw/native-terminal-failure.json'), 'ARCHIVE_TERMINAL_FAILURE_HASH_MISMATCH');
  }
  if (lengthBytes) {
    requiredRaw.push('raw/native-length-failure.json');
    requireValue(sha(lengthBytes) === journal.native_length_failure.sha256 && lengthBytes.length === journal.native_length_failure.size
      && digest(state.extensions?.loomy?.native_length_failure) === digest(journal.native_length_failure)
      && index.raw_trace.some(row => row.path === 'raw/native-length-failure.json'), 'ARCHIVE_LENGTH_FAILURE_HASH_MISMATCH');
  }
  if (failureBytes) {
    requiredRaw.push('raw/native-http-failure.json');
    requireValue(sha(failureBytes) === journal.native_http_failure.sha256 && failureBytes.length === journal.native_http_failure.size,
      'ARCHIVE_HTTP_FAILURE_HASH_MISMATCH');
    requireValue(index.raw_trace.some(row => row.path === 'raw/native-http-failure.json'), 'ARCHIVE_HTTP_FAILURE_SOURCE_MISSING');
  }
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
    if (isAbsentRuntime(row.previous) && Date.parse(row.observed_at) >= Date.parse(journal.sent_at)) {
      const absence = journal.runtime_absence_before_dispatch;
      requireValue(absence?.dispatch_attempt_count === 0 && absence.attempt_id === journal.identity.attempt_id
        && digest(absence.app_process) === digest(config.process)
        && Date.parse(absence.observed_at) <= Date.parse(journal.sent_at), 'ARCHIVE_COLD_START_ABSENCE_UNPROVED');
      assertNativeActivity(absence.native, [], config.archived_http_failures);
    }
    runtimeChain.push(row.current);
  }
  const effectiveRuntime = journal.runtime_binding || config.runtime;
  requireValue(digest(effectiveRuntime) === digest(runtimeChain.at(-1)), 'ARCHIVE_RUNTIME_BINDING_MISMATCH');
  if (failureBytes) {
    const failure = JSON.parse(failureBytes);
    requireValue(digest(failure.observed_runtime) === digest(effectiveRuntime)
      && runtimeChain.some(row => digest(row) === digest(failure.original_runtime))
      && digest(state.extensions.loomy.runtime) === digest(effectiveRuntime), 'ARCHIVE_HTTP_FAILURE_RUNTIME_MISMATCH');
  }
  requireValue(config_digest === digest(payload) && config.client.version === '0.9.39'
    && (config.runtime.health_version === '1.14.22' || isAbsentRuntime(config.runtime))
    && config.transport === 'macos-native-accessibility'
    && sha(await bytes('raw/frozen-run-config.json')) === journal.input_locks.config, 'ARCHIVE_RUN_CONFIG_INVALID');
  requireValue(['preserve-workspace-policy', 'require-full-access'].includes(config.permission_policy) && Array.isArray(journal.history)
    && index.raw_trace.length === requiredRaw.length + journal.history.length + (journal.source_repairs || []).length, 'ARCHIVE_PREPARATION_SCOPE_INVALID');
  if (config.permission_policy === 'require-full-access') {
    requireValue(config.configuration?.permission_label === '完全访问', 'ARCHIVE_FULL_ACCESS_POLICY_MISMATCH');
  }
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
  const readback = ui.get('workspace-full-path-readback');
  requireValue(selection?.full_path_verified === true && selection.workspace === state.session.cwd
    && selection.selection_method === 'native-ui-menu-exact-full-path'
    && readback?.nodes && (version[0] > 0 || version[1] > 1 || version[1] === 1 && version[2] >= 12
      ? registeredWorkspaceItems(readback, state.session.cwd).length === 1
      : readback.nodes.filter(node => node.help === state.session.cwd).length === 1),
    'ARCHIVE_WORKSPACE_SELECTION_MISMATCH');
  const taskConfig = { ...config, configuration: { ...config.configuration, permission_label: selection.configuration.permission_label } };
  const requiresSendGuards = config.send_guard_profile === SEND_GUARD_PROFILE;
  if (requiresSendGuards) {
    requireValue(config.permission_policy === 'require-full-access'
      && digest(selection.full_access_gate) === digest(requireFullAccess('loomy', selection.configuration.permission_label, 'workspace-selected')),
    'ARCHIVE_WORKSPACE_FULL_ACCESS_MISMATCH');
    for (const [event, dispatched] of [['before-send-intent', false], ['physical-send-guard', true]]) {
      const proof = ui.get(event);
      const verified = assertSendGuard(proof?.observed, config, state.session.cwd, promptBytes.toString('utf8'), dispatched);
      const observedAt = Date.parse(journal.history.find(row => row.event === event)?.at);
      const sentAt = Date.parse(journal.sent_at);
      requireValue(digest(proof?.full_access_gate) === digest(verified)
        && (dispatched ? observedAt >= sentAt && Boolean(journal.click_returned_at) : observedAt <= sentAt),
      'ARCHIVE_SEND_GUARD_EVIDENCE_MISMATCH');
    }
  }
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
  if (!terminalFailureBytes) requireValue(state.human_assistance.mode === 'automatic' && state.human_assistance.operation_count === 0
    && state.human_assistance.semantic_intervention_count === 0, 'ARCHIVE_HUMAN_INTERVENTION_UNSUPPORTED');
  else requireValue(digest(state.human_assistance) === digest(driver.human_assistance)
    && digest(state.human_assistance) === digest(journal.human_assistance), 'ARCHIVE_TERMINAL_HUMAN_COUNTS_MISMATCH');
  const prompt = promptBytes.toString('utf8');
  const baselineBytes = await bytes('raw/pre-send-native-baseline.json'), baseline = JSON.parse(baselineBytes);
  requireValue(sha(baselineBytes) === journal.baseline_evidence.sha256 && baselineBytes.length === journal.baseline_evidence.size
    && digest(baseline.session_index.map(row => row.id)) === digest(journal.baseline)
    && state.prompt.sent_at === journal.sent_at && Date.parse(baseline.observed_at) <= Date.parse(journal.sent_at), 'ARCHIVE_PRE_SEND_BASELINE_MISMATCH');
  assertNativeActivity(baseline, journal.allowed_session_ids, config.archived_http_failures);
  const normalized = normalizeTrace(native, { state, prompt, baseline: journal.baseline, nativeFailure: failureBytes && JSON.parse(failureBytes),
    nativeLengthFailure: lengthBytes && JSON.parse(lengthBytes), nativeTerminalFailure: terminalFailureBytes && JSON.parse(terminalFailureBytes) });
  if (lengthBytes) requireValue(digest(JSON.parse(lengthBytes).runtime) === digest(effectiveRuntime), 'ARCHIVE_LENGTH_RUNTIME_MISMATCH');
  if (terminalFailureBytes) {
    const proof = JSON.parse(terminalFailureBytes);
    requireValue(digest(proof.observed_runtime) === digest(effectiveRuntime)
      && runtimeChain.some(row => digest(row) === digest(proof.original_runtime)), 'ARCHIVE_TERMINAL_RUNTIME_MISMATCH');
  }
  if (requiresSendGuards) {
    requireValue(normalized.binding.root.time_created >= Date.parse(journal.sent_at)
      && normalized.binding.user.time_created >= normalized.binding.root.time_created, 'ARCHIVE_NATIVE_SESSION_PREDATES_DISPATCH');
    requireValue(normalized.binding.full_access_context_part_id, 'ARCHIVE_NATIVE_ACCESS_CONTEXT_MISSING');
  }
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
  const version = value.collection.version?.split('.').map(Number);
  requireValue(version?.length === 3 && version.every(Number.isSafeInteger)
    && value.collection.version === index.adapter.version, 'ARCHIVE_RESOURCE_VERSION_INVALID');
  const legacy = version[0] === 0 && (version[1] < 1 || version[1] === 1 && version[2] <= 21);
  requireValue(legacy || value.collection.native_usage_profile === 'loomy-opencode-recorded-usage/v1', 'ARCHIVE_RESOURCE_PROFILE_INVALID');
  const expected = resourceMetrics({ state, normalized, sources: value.collection.sources, legacy });
  requireValue(digest(value.metrics) === digest(expected.metrics) && digest(value.collection.coverage) === digest(expected.collection.coverage)
    && value.collection.status === expected.collection.status
    && digest(value.collection.warnings) === digest(expected.collection.warnings), 'ARCHIVE_RESOURCE_REPLAY_MISMATCH');
  if (!legacy) requireValue(digest(value.collection.known_subtotals) === digest(expected.collection.known_subtotals)
    && digest(value.collection.native_usage_reconciliation) === digest(expected.collection.native_usage_reconciliation),
  'ARCHIVE_NATIVE_USAGE_REPLAY_MISMATCH');
}
