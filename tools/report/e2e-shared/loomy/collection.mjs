import { mkdir, mkdtemp, readFile, realpath, rename, rm, writeFile, lstat } from 'node:fs/promises';
import { dirname, join, relative, resolve } from 'node:path';
import { artifact, captureNative, currentOwnedRuntime, iso, jsonBytes, PROFILE, requireValue, runtimeStatus, sha, verifyBinding, verifyNativeHttpFailure, verifyNativeLengthFailure, verifyNativeTerminalFailure, COMPONENT_VERSION } from './index.mjs';
import { applyJournalRuntime, buildState, checkNativeModel, lease, loadTask, verifyRuntime } from './execution.mjs';

const lines = rows => Buffer.from(rows.map(row => JSON.stringify(row)).join('\n') + '\n');
const metric = (value, basis, status = 'observed') => ({ value, status, basis });
const unavailable = basis => metric(null, basis, 'unavailable');

export function normalizeTrace(native, { state, prompt, baseline, nativeFailure = null, nativeLengthFailure = null, nativeTerminalFailure = null }) {
  const binding = verifyBinding(native, { workspace: state.session.cwd, prompt, baseline,
    sessionId: state.session.session_id, terminal: state.phase === 'COMPLETED' });
  checkNativeModel(binding);
  if (state.phase === 'COMPLETED') requireValue(!binding.final.parsed.error, 'COMPLETED_NATIVE_ERROR_CONFLICT');
  const httpFailure = nativeFailure && verifyNativeHttpFailure(nativeFailure, { native, workspace: state.session.cwd,
    prompt, baseline, sessionId: state.session.session_id, identity: state.identity });
  const lengthFailure = nativeLengthFailure && verifyNativeLengthFailure(nativeLengthFailure, { native, workspace: state.session.cwd,
    prompt, baseline, sessionId: state.session.session_id, identity: state.identity });
  const terminalFailure = nativeTerminalFailure && verifyNativeTerminalFailure(nativeTerminalFailure, { native, workspace: state.session.cwd,
    prompt, baseline, sessionId: state.session.session_id, identity: state.identity });
  if (state.phase === 'FAILED') requireValue((binding.final?.parsed.error || httpFailure
    && digestError(httpFailure.error) === digestError(state.execution.error) || lengthFailure
    && digestError(lengthFailure.error) === digestError(state.execution.error) || terminalFailure
    && digestError(terminalFailure.error) === digestError(state.execution.error)) && state.execution.business_status === 'candidate_error', 'NATIVE_FAILURE_UNPROVED');
  requireValue(!binding.parts.some(row => row.parsed.type === 'tool' && row.parsed.tool === 'question')
    || terminalFailure && terminalFailure.question_terminations.length > 0, 'HUMAN_QUESTION_REQUIRES_INTERVENTION_RECEIPT');
  if (terminalFailure) requireValue(digestError(state.human_assistance) === digestError(terminalFailure.human_assistance)
    && digestError(state.execution.error) === digestError(terminalFailure.error), 'TERMINAL_FAILURE_HUMAN_ASSISTANCE_MISMATCH');
  const messages = new Map(binding.messages.map(row => [row.id, row]));
  const events = [], grouped = new Map(), missing = [], callIds = new Set();
  const append = value => events.push({ schema_id: 'urn:wildclawbench:schema:general-e2e:transcript-event:v1', schema_version: 1,
    identity: state.identity, role: null, content: null, ...value });
  let nativeAtoms = 0;
  for (const [position, row] of binding.parts.entries()) {
    const part = row.parsed, message = messages.get(row.message_id);
    nativeAtoms++;
    const common = { event_id: row.id, occurred_at: iso(part.time?.start ?? row.time_created),
      native_session_id: row.session_id, native_message_id: row.message_id,
      is_subagent: row.session_id !== binding.root.id,
      source: { adapter: PROFILE, raw_ref: 'raw/native-part-rows.jsonl#L' + (position + 1), redacted: false } };
    if (binding.client_context_part_ids.includes(row.id)) {
      append({ ...common, type: 'status',
        native_type: row.id === binding.full_access_context_part_id ? 'client-full-access-context' : 'client-memory-context',
        native_role: 'user', content: part.text });
    } else if (part.type === 'text' && !part.synthetic && !part.ignored) {
      requireValue(typeof part.text === 'string' && ['user', 'assistant'].includes(message.parsed.role), 'NATIVE_TEXT_INVALID');
      const values = grouped.get(row.message_id) || []; values.push({ row, common }); grouped.set(row.message_id, values);
    } else if (part.type === 'tool') {
      requireValue(typeof part.callID === 'string' && part.callID && typeof part.tool === 'string' && part.tool
        && !callIds.has(part.callID), 'NATIVE_TOOL_ID_INVALID_OR_DUPLICATED');
      callIds.add(part.callID);
      append({ ...common, type: 'tool_call', role: 'assistant',
        tool: { call_id: part.callID, name: part.tool, arguments: part.state?.input ?? null, status: 'unknown' } });
      if (['completed', 'error'].includes(part.state?.status)) {
        nativeAtoms++;
        const failed = part.state.status === 'error' || Number.isInteger(part.state.metadata?.exit) && part.state.metadata.exit !== 0;
        append({ ...common, event_id: row.id + '-result', occurred_at: iso(part.state.time?.end ?? row.time_updated),
          type: 'tool_result', role: 'user', tool: { call_id: part.callID,
            result: part.state.status === 'error' ? part.state.error ?? part.state.output ?? null : part.state.output ?? null,
            status: failed ? 'error' : 'success', native_outcome: part.state.status } });
      } else missing.push('nonterminal-tool:' + part.callID);
    } else {
      const known = ['reasoning', 'step-start', 'step-finish', 'snapshot', 'patch', 'file', 'agent', 'subtask', 'retry', 'compaction', 'text'].includes(part.type);
      if (!known) missing.push('unsupported-native-part:' + part.type);
      append({ ...common, type: 'status', role: message.parsed.role, native_type: part.type,
        content: typeof part.text === 'string' ? part.text : null });
    }
  }
  for (const [id, values] of grouped) {
    const message = messages.get(id), role = message.parsed.role;
    const child = message.session_id !== binding.root.id;
    append({ ...values[0].common, event_id: id + '-text',
      occurred_at: iso(role === 'assistant' ? message.parsed.time?.completed ?? message.time_updated : message.time_created),
      type: child ? 'status' : role === 'user' ? 'user_message' : 'assistant_message', role,
      ...(child ? { native_type: 'subagent_message' } : {}),
      content: values.map(item => item.row.parsed.text).join(''), native_message_part_ids: values.map(item => item.row.id) });
  }
  for (const [position, message] of binding.messages.entries()) if (message.parsed.error) {
    nativeAtoms++;
    append({ event_id: message.id + '-error', occurred_at: iso(message.time_updated), type: 'error', role: 'assistant',
      content: JSON.stringify(message.parsed.error), native_session_id: message.session_id, native_message_id: message.id,
      source: { adapter: PROFILE, raw_ref: 'raw/native-message-rows.jsonl#L' + (position + 1), redacted: false } });
  }
  for (const [position, row] of (httpFailure?.errors || []).entries()) {
    nativeAtoms++;
    append({ event_id: binding.final.id + '-http-error-' + position, occurred_at: row.occurred_at, type: 'error', role: 'assistant',
      content: JSON.stringify({ name: row.error.name, statusCode: row.error.statusCode, responseBody: row.error.responseBody }),
      native_session_id: binding.root.id, native_message_id: binding.final.id,
      source: { adapter: PROFILE, raw_ref: 'raw/native-http-failure.json#/source_lines/' + position, redacted: false } });
  }
  if (lengthFailure) {
    nativeAtoms++;
    append({ event_id: binding.final.id + '-length-failure', occurred_at: iso(binding.final.parsed.time.completed),
      type: 'error', role: 'assistant', content: JSON.stringify(lengthFailure.error),
      native_session_id: binding.root.id, native_message_id: binding.final.id,
      source: { adapter: PROFILE, raw_ref: 'raw/native-length-failure.json', redacted: false } });
  }
  if (terminalFailure && !binding.final.parsed.error) {
    nativeAtoms++;
    append({ event_id: binding.final.id + '-terminal-failure', occurred_at: iso(binding.final.parsed.time.completed),
      type: 'error', role: 'assistant', content: JSON.stringify(terminalFailure.error),
      native_session_id: binding.root.id, native_message_id: binding.final.id,
      source: { adapter: PROFILE, raw_ref: 'raw/native-terminal-failure.json', redacted: false } });
  }
  const filtered = [...grouped.values()].reduce((count, rows) => count + rows.length - 1, 0);
  events.sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at) || (a.event_id < b.event_id ? -1 : a.event_id > b.event_id ? 1 : 0));
  events.forEach((event, index) => { event.sequence = index; });
  const calls = new Map();
  for (const event of events) if (event.tool?.call_id) {
    const id = event.tool.call_id, row = calls.get(id) || { call_id: id, call_sequence: null, result_sequence: null };
    const key = event.type === 'tool_call' ? 'call_sequence' : 'result_sequence';
    requireValue(row[key] === null, 'DUPLICATE_NORMALIZED_TOOL_EVENT'); row[key] = event.sequence; calls.set(id, row);
  }
  requireValue(events.length > 0 && nativeAtoms === events.length + filtered, 'NORMALIZATION_CONSERVATION_FAILED');
  const final = events.find(event => event.type === 'assistant_message' && event.native_message_id === binding.final?.id
    && event.native_session_id === binding.root.id);
  if (state.phase === 'COMPLETED') requireValue(final?.content?.trim(), 'FINAL_RESPONSE_MISSING');
  return { events, calls: [...calls.values()], final_response: final?.content ?? null,
    native_event_count: nativeAtoms, filtered_native_event_count: filtered, missing, binding };
}
const digestError = value => JSON.stringify(value);

export function resourceMetrics({ state, normalized, sources }) {
  const nativeStart = normalized.binding.user.parsed.time?.created ?? normalized.binding.user.time_created;
  const nativeEnd = normalized.binding.final?.parsed.time?.completed;
  const nativeElapsed = Number.isSafeInteger(nativeStart) && Number.isSafeInteger(nativeEnd) && nativeEnd >= nativeStart
    ? (nativeEnd - nativeStart) / 1000 : null;
  const tokens = ['input_tokens', 'output_tokens', 'total_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'reasoning_output_tokens'];
  const names = [...tokens, 'request_count', 'request_attempt_count', 'call_count', 'duration_seconds', 'agent_duration_seconds'];
  const coverage = Object.fromEntries(names.map(name => [name, { known: 0, total: null, unit: 'model_response' }]));
  coverage.call_count = { known: normalized.calls.length, total: normalized.calls.length, unit: 'tool_call' };
  coverage.duration_seconds = { known: 1, total: 1, unit: 'attempt' };
  coverage.agent_duration_seconds = { known: nativeElapsed === null ? 0 : 1, total: 1, unit: 'attempt' };
  return { schema_id: 'urn:wildclawbench:schema:general-e2e:resource-metrics:v1', schema_version: 1, identity: state.identity,
    collection: { collector: PROFILE, version: COMPONENT_VERSION, status: 'partial', collected_at: new Date().toISOString(), sources,
      warnings: ['LOOMY_TOKEN_SEMANTICS_NOT_ADMITTED', 'LOOMY_MODEL_REQUEST_SEMANTICS_NOT_ADMITTED',
        ...(state.human_assistance?.operation_count === null ? ['LOOMY_ABORT_HUMAN_ASSISTANCE_COUNTS_UNAVAILABLE'] : [])],
      excluded_scope: ['judge_usage', 'control_usage', 'unobserved_http_retries', 'unrelated_client_sessions'], coverage,
      metric_sources: Object.fromEntries(names.map(name => [name, sources.map(row => row.path)])) },
    metrics: { usage: Object.fromEntries(tokens.map(name => [name, unavailable('Original OpenCode token fields retained; provider/cache semantics not admitted')])),
      requests: { request_count: unavailable('Assistant message count is not a verified model request count'),
        request_attempt_count: unavailable('HTTP attempt count is not exposed') },
      tools: { call_count: metric(normalized.calls.length, 'Unique bound native tool call IDs, including linked child sessions') },
      timing: { duration_seconds: metric(state.execution.duration_seconds, 'Controller prompt dispatch to observed native terminal; same controller clock'),
        agent_duration_seconds: nativeElapsed === null ? unavailable('Missing or reversed native message timestamps')
          : metric(nativeElapsed, 'Bound first user created to final root assistant completed; same OpenCode runtime clock', 'inferred') } } };
}

export async function collectTask(options) {
  const context = await loadTask(options), release = await lease(join(context.control, 'collector.lock'));
  try {
    const [journalBytes, originalStateBytes] = await Promise.all([readFile(context.journalPath), readFile(context.statePath)]);
    const journal = JSON.parse(journalBytes), originalState = JSON.parse(originalStateBytes);
    applyJournalRuntime(context, journal);
    requireValue(['COMPLETED', 'FAILED'].includes(originalState.phase) && journal.dispatch_attempt_count === 1
      && journal.send_status === 'sent' && JSON.stringify(journal.input_locks) === JSON.stringify(context.locks), 'COLLECT_EXECUTION_NOT_FROZEN');
    requireValue(sha(jsonBytes(buildState(context, journal))) === sha(originalStateBytes), 'COLLECT_DRIVER_STATE_CHANGED');
    const collectionRuntime = await currentOwnedRuntime(context.config);
    const statuses = await runtimeStatus(collectionRuntime, context.workspace);
    const currentNative = await captureNative({ database: context.config.runtime.database, sessionId: journal.session.id, python: context.config.python });
    const terminalBytes = await readFile(join(context.unitRoot, journal.terminal_evidence.path));
    requireValue(sha(terminalBytes) === journal.terminal_evidence.sha256 && terminalBytes.length === journal.terminal_evidence.size, 'TERMINAL_EVIDENCE_CHANGED');
    const terminal = JSON.parse(terminalBytes), native = terminal.native;
    const failureBytes = journal.native_http_failure && await readFile(join(context.unitRoot, journal.native_http_failure.path));
    if (failureBytes) requireValue(sha(failureBytes) === journal.native_http_failure.sha256
      && failureBytes.length === journal.native_http_failure.size, 'HTTP_FAILURE_PROOF_CHANGED');
    const lengthBytes = journal.native_length_failure && await readFile(join(context.unitRoot, journal.native_length_failure.path));
    if (lengthBytes) requireValue(sha(lengthBytes) === journal.native_length_failure.sha256
      && lengthBytes.length === journal.native_length_failure.size, 'LENGTH_FAILURE_PROOF_CHANGED');
    const terminalFailureBytes = journal.native_terminal_failure && await readFile(join(context.unitRoot, journal.native_terminal_failure.path));
    if (terminalFailureBytes) requireValue(sha(terminalFailureBytes) === journal.native_terminal_failure.sha256
      && terminalFailureBytes.length === journal.native_terminal_failure.size, 'TERMINAL_FAILURE_PROOF_CHANGED');
    const normalized = normalizeTrace(native, { state: originalState, prompt: context.prompt, baseline: journal.baseline,
      nativeFailure: failureBytes && JSON.parse(failureBytes), nativeLengthFailure: lengthBytes && JSON.parse(lengthBytes),
      nativeTerminalFailure: terminalFailureBytes && JSON.parse(terminalFailureBytes) });
    requireValue(currentNative.sessions.every(row => !statuses[row.id] || statuses[row.id].type === 'idle'), 'COLLECT_NATIVE_STILL_ACTIVE');
    requireValue(normalized.binding.final?.id === journal.final_message_id, 'COLLECT_FINAL_MESSAGE_CHANGED');
    const baselineBytes = await readFile(join(context.unitRoot, journal.baseline_evidence.path));
    requireValue(sha(baselineBytes) === journal.baseline_evidence.sha256 && baselineBytes.length === journal.baseline_evidence.size, 'PRE_SEND_BASELINE_CHANGED');
    const content = snapshot => JSON.stringify({ messages: snapshot.messages.map(({ id, session_id, data }) => ({ id, session_id, data })),
      parts: snapshot.parts.map(({ id, message_id, session_id, data }) => ({ id, message_id, session_id, data })) });
    const scope = new Set(native.sessions.map(row => row.id));
    const measuredCurrent = { messages: currentNative.messages.filter(row => scope.has(row.session_id)), parts: currentNative.parts.filter(row => scope.has(row.session_id)) };
    requireValue(content(native) === content(measuredCurrent), 'NATIVE_CONTENT_CHANGED_AFTER_TERMINAL');
    requireValue(currentNative.sessions.filter(row => !scope.has(row.id)).every(row => row.time_created > Date.parse(journal.finished_at)), 'PRE_TERMINAL_SESSION_OMITTED');
    const outputRoot = resolve(options.outputRoot || join(context.unitRoot, '.general-e2e/collection/loomy', context.taskId, journal.identity.attempt_id));
    requireValue(outputRoot.startsWith(join(context.unitRoot, '.general-e2e/collection') + '/'), 'COLLECTION_OUTPUT_OUTSIDE_SCOPE');
    await mkdir(dirname(outputRoot), { recursive: true, mode: 0o700 });
    requireValue(await realpath(dirname(outputRoot)) === dirname(outputRoot), 'COLLECTION_OUTPUT_SYMLINK');
    try { await lstat(outputRoot); throw Error('LOOMY_COLLECTION_OUTPUT_EXISTS'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    const state = structuredClone(originalState);
    const files = new Map([['raw/native-scoped-snapshot.json', jsonBytes(native)], ['raw/native-part-rows.jsonl', lines(native.parts)],
      ['raw/native-message-rows.jsonl', lines(native.messages)], ['raw/driver-state.json', originalStateBytes],
      ['raw/dispatch-journal.json', journalBytes], ['raw/sent-prompt.txt', Buffer.from(context.prompt)],
      ['raw/frozen-run-config.json', await readFile(options.runConfig)],
      ['raw/terminal-evidence.json', terminalBytes], ['raw/pre-send-native-baseline.json', baselineBytes],
      ['raw/current-scoped-snapshot.json', jsonBytes({ native: currentNative, runtime: collectionRuntime, runtime_status: statuses })]]);
    if (failureBytes) files.set('raw/native-http-failure.json', failureBytes);
    if (lengthBytes) files.set('raw/native-length-failure.json', lengthBytes);
    if (terminalFailureBytes) files.set('raw/native-terminal-failure.json', terminalFailureBytes);
    for (const [i, receipt] of journal.history.entries()) {
      const bytes = await readFile(join(context.unitRoot, receipt.path));
      requireValue(sha(bytes) === receipt.sha256 && bytes.length === receipt.size, 'UI_PREPARATION_EVIDENCE_CHANGED');
      requireValue(/^[a-z-]+$/u.test(receipt.event), 'UI_PREPARATION_EVENT_INVALID');
      files.set(`raw/ui-preparation/${i}-${receipt.event}.json`, bytes);
    }
    for (const [i, repair] of (journal.source_repairs || []).entries()) {
      const bytes = await readFile(join(context.unitRoot, repair.path));
      requireValue(sha(bytes) === repair.sha256 && bytes.length === repair.size, 'SOURCE_REPAIR_RECEIPT_CHANGED');
      files.set(`raw/source-repairs/${i + 1}.json`, bytes);
    }
    const bindings = [];
    for (const [i, row] of state.session.binding_evidence.entries()) {
      const bytes = await readFile(join(context.unitRoot, row.path));
      requireValue(sha(bytes) === row.sha256 && bytes.length === row.size, 'DISPATCH_BINDING_CHANGED');
      const proof = JSON.parse(bytes), binding = verifyBinding(proof.native, { workspace: context.workspace, prompt: context.prompt,
        baseline: journal.baseline, sessionId: journal.session.id });
      checkNativeModel(binding);
      requireValue(proof.identity.attempt_id === journal.identity.attempt_id && proof.prompt_sha256 === context.locks.prompt, 'DISPATCH_BINDING_IDENTITY_CHANGED');
      const path = `bindings/${i + 1}-session-binding.json`; files.set(path, bytes); bindings.push(artifact(path, bytes));
    }
    const finalBytes = normalized.final_response === null ? null : Buffer.from(normalized.final_response);
    if (finalBytes && state.phase === 'COMPLETED') state.extensions.evidence = {
      final_response_path: relative(context.unitRoot, join(outputRoot, 'execution/final-response.md')), final_response_sha256: sha(finalBytes) };
    const stateBytes = jsonBytes(state), transcript = lines(normalized.events);
    const raw = [...files].filter(([path]) => path.startsWith('raw/')).map(([path, bytes]) => artifact(path, bytes));
    const index = { schema_id: 'urn:wildclawbench:schema:general-e2e:trace-index:v2', schema_version: 2, identity: state.identity,
      adapter: { id: PROFILE, version: COMPONENT_VERSION, source: 'loomy-bound-readonly-opencode-session-subtree' },
      session: { thread_id: state.session.thread_id, turn_id: state.session.turn_id, session_id: state.session.session_id,
        cwd: state.session.cwd, lifecycle_generation: null },
      transcript: artifact('transcript.jsonl', transcript, { event_count: normalized.events.length }), raw_trace: raw, binding_evidence: bindings,
      normalization: { native_event_count: normalized.native_event_count, normalized_event_count: normalized.events.length,
        filtered_native_event_count: normalized.filtered_native_event_count, compatibility_profiles: ['general-e2e-transcript-event-v1', PROFILE] },
      completeness: { status: normalized.missing.length ? 'partial' : 'complete', omitted_event_count: 0, missing: normalized.missing }, calls: normalized.calls };
    const indexBytes = jsonBytes(index), sources = [artifact('execution/automation-state.json', stateBytes),
      artifact('trace/trace-index.json', indexBytes), ...[...raw, ...bindings].map(row => ({ ...row, path: 'trace/' + row.path }))];
    const resource = resourceMetrics({ state, normalized, sources });
    const stage = await mkdtemp(join(dirname(outputRoot), '.loomy-collection-'));
    try {
      for (const [path, bytes] of files) { const target = join(stage, 'trace', path); await mkdir(dirname(target), { recursive: true }); await writeFile(target, bytes, { flag: 'wx', mode: 0o600 }); }
      const outputs = [['execution/automation-state.json', stateBytes], ['trace/transcript.jsonl', transcript], ['trace/trace-index.json', indexBytes], ['resource-metrics.json', jsonBytes(resource)]];
      if (finalBytes) outputs.push(['execution/final-response.md', finalBytes]);
      for (const [path, bytes] of outputs) { const target = join(stage, path); await mkdir(dirname(target), { recursive: true }); await writeFile(target, bytes, { flag: 'wx', mode: 0o600 }); }
      await rename(stage, outputRoot);
    } catch (error) { await rm(stage, { recursive: true, force: true }); throw error; }
    return { status: 'PASS', output_root: outputRoot, state_file: join(outputRoot, 'execution/automation-state.json'),
      trace_index: join(outputRoot, 'trace/trace-index.json'), resource_metrics: join(outputRoot, 'resource-metrics.json'), identity: state.identity };
  } finally { await release(); }
}
