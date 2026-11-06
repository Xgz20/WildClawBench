import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { dirname, join, relative, isAbsolute } from 'node:path';
import { lstat, readFile, realpath } from 'node:fs/promises';
export const START_REJECTION_PROFILE = 'bound-native-unsubmitted-start-rejection/v1';
export const IDLE_PREWARM_REJECTION_PROFILE = 'bound-native-unsubmitted-start-rejection-idle-prewarm/v1';
const digest = text => createHash('sha256').update(text).digest('hex');
const assert = (ok, code) => { if (!ok) throw new Error(`NATIVE_START_REJECTION_${code}`); };
const one = (rows, code) => { assert(rows?.length === 1, code); return rows[0]; };
function unavailableRateNotice(row, route) {
  if (row.thread_id !== route || row.turn_id || row.event_type !== 'account.rate-limits.updated') return false;
  try {
    const event=JSON.parse(row.event_json), outer=event.payload?.rateLimits;
    const rates=outer && Object.keys(outer).length===1 && outer.rateLimits
      ? outer.rateLimits : outer;
    return event.type === row.event_type && rates &&
      ['primary','secondary','credits','individualLimit','planType','rateLimitReachedType'].every(key=>rates[key] === null);
  } catch { return false; }
}
function prewarmSetupNotice(row, route, runtime, cursor) {
  if (unavailableRateNotice(row, route)) return true;
  if(row.thread_id!==route || row.turn_id) return false;
  try {
    const event=JSON.parse(row.event_json),raw=event.raw;
    if(event.provider!=='acode'||event.threadId!==route||event.turnId
      ||!runtime.lifecycle_generation||event.lifecycleGeneration!==runtime.lifecycle_generation) return false;
    if(event.type==='session.state.changed'&&row.event_type===event.type) {
      return Object.keys(raw?.payload||{}).length===0 &&
        (raw.method==='session/connecting'&&event.payload?.state==='starting'
        ||raw.method==='session/ready'&&event.payload?.state==='ready');
    }
    if(event.type==='mcp.status.updated'&&row.event_type===event.type) {
      const value=event.payload?.status,source=raw?.payload;
      if(raw?.method!=='mcpServer/startupStatus/updated'
        ||event.providerRefs?.providerThreadId!==cursor.threadId||source?.threadId!==cursor.threadId
        ||value?.name!=='acode_apps'||source.name!==value.name||source.failureReason!==null)return false;
      if(value.state==='failed')return source.status==='failed'&&source.error===value.error
        &&typeof value.error==='string'&&value.error.startsWith('MCP client for `acode_apps` timed out after 30 seconds.');
      return value.state==='ready'&&source.status==='ready'&&source.error===null
        &&Object.keys(value).sort().join(',')==='name,state'
        &&Object.keys(source).sort().join(',')==='error,failureReason,name,status,threadId';
    }
    return false;
  } catch {return false;}
}

export function verifyNativeStartRejection(data, state, config) {
  assert(state.phase === 'NEEDS_ATTENTION' && state.session?.verified === false
    && !state.session.thread_id && !state.session.turn_id && !state.session.session_id
    && state.send?.dispatch_attempt_count === 1 && state.prompt?.send_status === 'uncertain'
    && ['NATIVE_IDENTITY_UNAVAILABLE_AFTER_SEND', 'PROMPT_SEND_UNCERTAIN'].includes(state.execution?.error?.code), 'STATE');
  assert(!config.runConfig?.tested_model?.custom_mapping && config.expectedPermission === '完全访问', 'CONFIG_PROFILE');
  const route = state.send.post_send_route_thread_id;
  assert(route && route === state.send.pre_send_route_thread_id && state.session.baseline?.length === 0, 'ROUTE');
  const thread = one(data.projection_threads, 'THREAD');
  const project = one(data.projection_projects, 'PROJECT');
  const session = one(data.projection_thread_sessions, 'SESSION');
  const message = one(data.projection_thread_messages, 'MESSAGE');
  assert(thread.thread_id === route && !thread.deleted_at && !thread.latest_turn_id
    && thread.project_id === project.project_id && !project.deleted_at
    && resolve(project.workspace_root) === resolve(config.candidateWorkspace)
    && state.client?.workspace_selection?.project_id === project.project_id
    && state.client.workspace_selection.thread_id === route
    && resolve(state.client.workspace_selection.path) === resolve(config.candidateWorkspace), 'WORKSPACE');
  const readyProjection = session.status === 'ready' && session.last_error === null;
  assert(session.thread_id === route && (session.status === 'error' || readyProjection) && !session.active_turn_id
    && !session.provider_session_id && !session.provider_thread_id, 'SESSION_TERMINAL');
  assert(message.thread_id === route && message.role === 'user' && message.source === 'native'
    && message.dispatch_origin === 'user' && message.dispatch_mode === 'queue'
    && !message.turn_id && !message.is_streaming && digest(message.text) === state.prompt.sha256
    && state.prompt.sha256 === config.promptSha256
    && Date.parse(message.created_at) >= Date.parse(state.send.dispatch_armed_at)
    && Date.parse(message.created_at) <= Date.parse(state.send.dispatch_completed_at), 'PROMPT');
  for (const table of ['projection_turns', 'projection_pending_interactions', 'provider_runtime_open_turns', 'queued_turn_promotions']) {
    assert(data[table]?.length === 0, 'ACTIVITY_' + table);
  }
  const runtime = one(data.provider_session_runtime, 'RUNTIME');
  const cursor = JSON.parse(runtime.resume_cursor_json || '{}');
  const runtimePayload = JSON.parse(runtime.runtime_payload_json || '{}');
  assert(data.provider_runtime_events?.every(row => prewarmSetupNotice(row, route, runtime, cursor)), 'PROVIDER_ACTIVITY');
  const mcpReady=data.provider_runtime_events.filter(row=>row.event_type==='mcp.status.updated'
    &&JSON.parse(row.event_json).payload?.status?.state==='ready');
  for(const ready of mcpReady) {
    const readyEvent=JSON.parse(ready.event_json);
    assert(Number.isSafeInteger(ready.sequence)&&Number.isFinite(Date.parse(readyEvent.createdAt))
      &&data.provider_runtime_events.some(previous=>Number.isSafeInteger(previous.sequence)&&previous.sequence<ready.sequence
        &&previous.event_type==='mcp.status.updated'&&prewarmSetupNotice(previous,route,runtime,cursor)
        &&JSON.parse(previous.event_json).payload?.status?.state==='failed'
        &&Date.parse(JSON.parse(previous.event_json).createdAt)<=Date.parse(readyEvent.createdAt)), 'MCP_READY_WITHOUT_BOUND_TIMEOUT');
  }
  const idlePrewarm = ['running', 'ready'].includes(runtime.status)
    && ['session.state.changed', 'provider.session.starting'].includes(runtimePayload.lastRuntimeEvent)
    && runtimePayload.activeTurnId === null && runtimePayload.lastError === null
    && runtimePayload.emptyPrewarmDispatch === null
    && typeof cursor.threadId === 'string' && cursor.threadId.length > 0;
  assert(runtime.thread_id === route && (runtime.status === 'stopped' || idlePrewarm) && cursor.emptyPrewarm === true
    && !runtimePayload.activeTurnId && resolve(runtimePayload.cwd || '') === resolve(config.candidateWorkspace), 'PREWARM');
  assert(!readyProjection || idlePrewarm, 'READY_PROJECTION_PREWARM');
  const events = data.orchestration_events.map(row => ({ ...row, payload: JSON.parse(row.payload_json) }));
  const request = one(events.filter(row => row.event_type === 'thread.turn-start-requested'), 'REQUEST');
  const sent = one(events.filter(row => row.event_type === 'thread.message-sent'), 'MESSAGE_EVENT');
  assert(request.stream_id === route && request.actor_kind === 'client'
    && request.payload.threadId === route && request.payload.messageId === message.message_id
    && request.command_id === sent.command_id && request.causation_event_id === sent.event_id
    && request.payload.requestCommandId === request.command_id
    && request.payload.createdAt === message.created_at && sent.payload.text === message.text
    && sent.payload.messageId === message.message_id && sent.sequence === message.sequence, 'REQUEST_BINDING');
  const model = request.payload.modelSelection;
  assert(model?.provider === 'acode' && model.model === config.expectedModel.toLowerCase()
    && model.options?.reasoningEffort === config.expectedReasoning.toLowerCase()
    && request.payload.runtimeMode === 'full-access' && thread.runtime_mode === 'full-access'
    && JSON.stringify(JSON.parse(thread.model_selection_json)) === JSON.stringify(model), 'MODEL');
  const receipt = one(data.orchestration_command_receipts.filter(row => row.command_id === request.command_id), 'RECEIPT');
  assert(receipt.aggregate_id === route && receipt.aggregate_kind === 'thread' && receipt.status === 'accepted'
    && receipt.error === null && receipt.result_sequence === request.sequence
    && receipt.accepted_at === message.created_at && /^[a-f0-9]{64}$/.test(receipt.command_fingerprint), 'RECEIPT_BINDING');
  const failure = one(events.filter(row => row.event_type === 'thread.activity-appended'
    && row.payload.activity?.kind === 'provider.turn.start.failed'), 'FAILURE');
  const activity = failure.payload.activity; const payload = activity.payload;
  assert(activity.id === `provider-start-failed:${request.sequence}:1` && activity.turnId === null
    && payload.messageId === message.message_id && payload.requestCommandId === request.command_id
    && payload.eventSequence === request.sequence && payload.requestCreatedAt === message.created_at
    && payload.preparationTerminal === true && payload.settlementStatus === 'rejected'
    && payload.submissionState === 'not-sent'
    && typeof payload.detail === 'string' && (readyProjection || payload.detail === session.last_error)
    && payload.detail.includes('ACode turn submission did not complete within 20000ms.')
    && payload.detail.includes('/Applications/AStudio.app/Contents/Resources/app.asar/'), 'FAILURE_BINDING');
  const delivery = one(data.orchestration_event_deliveries.filter(row => row.event_sequence === request.sequence), 'DELIVERY');
  assert(delivery.consumer_name === 'provider-command-reactor.v1' && delivery.thread_id === route
    && delivery.state === 'succeeded' && delivery.submission_state === 'not-submitted-v1'
    && delivery.attempt_count === 1 && !delivery.claim_owner && !delivery.claim_expires_at
    && delivery.completed_at === activity.createdAt
    && (readyProjection ? Date.parse(session.updated_at) < Date.parse(activity.createdAt) : session.updated_at === activity.createdAt)
    && Date.parse(activity.createdAt) > Date.parse(message.created_at), 'SETTLEMENT');
  assert(data.orchestration_event_deliveries.every(row => row.state === 'succeeded'
    && !row.claim_owner && !row.claim_expires_at), 'OTHER_DELIVERY');
  if (readyProjection) {
    const errorEvent=one(events.filter(row=>row.event_type==='thread.session-set'
      && row.command_id?.startsWith(`provider-start-failed:${request.sequence}:1:session:v1:`)), 'ERROR_EVENT');
    const nativeError=errorEvent.payload.session;
    assert(nativeError?.threadId===route && nativeError.status==='error' && nativeError.providerName==='acode'
      && nativeError.activeTurnId===null && nativeError.lastError===payload.detail
      && nativeError.updatedAt===activity.createdAt, 'ERROR_EVENT_BINDING');
    for (const event of [failure,errorEvent]) {
      const accepted=one(data.orchestration_command_receipts.filter(row=>row.command_id===event.command_id),'ERROR_RECEIPT');
      assert(event.actor_kind==='client' && event.correlation_id===event.command_id
        && accepted.aggregate_id===route && accepted.aggregate_kind==='thread'
        && accepted.status==='accepted' && accepted.error===null && accepted.result_sequence===event.sequence
        && accepted.accepted_at===activity.createdAt && /^[a-f0-9]{64}$/.test(accepted.command_fingerprint)
        && event.command_id.endsWith(':'+accepted.command_fingerprint),'ERROR_RECEIPT_BINDING');
    }
  }
  return { profile: idlePrewarm ? IDLE_PREWARM_REJECTION_PROFILE : START_REJECTION_PROFILE,
    ...(mcpReady.length?{prewarm_mcp_recovered_without_model_turn:true,prewarm_mcp_ready_sequences:mcpReady.map(row=>row.sequence)}:{}),
    ...(idlePrewarm ? { prewarm_runtime_status: runtime.status, prewarm_provider_session_id: cursor.threadId,
      prewarm_only: true, active_model_turn_id: null, native_projection_status: session.status,
      native_projection_updated_at: session.updated_at, native_projection_stale: readyProjection } : {}),
    thread_id: route, project_id: project.project_id,
    message_id: message.message_id, request_sequence: request.sequence, request_command_id: request.command_id,
    failed_at: activity.createdAt, error: payload.detail, prompt_sha256: state.prompt.sha256,
    native_turn_id: null, native_sdk_session_id: null, pending_dispatches: 0,
    failure_origin: 'harness-native-turn-start', framework_prompt_delivery_verified: true,
    retry_performed: false, cancellation_performed: false };
}

// Portable replay of a frozen rejection. The original uncertain state and
// native rows are retained; a derived FAILED state cannot certify itself.
export async function readFrozenStartRejection(unitRoot, state, record = null) {
  if (record && state.evidence?.native_start_rejection) assert(record.evidence?.native_start_rejection, 'RECORD_PROOF_REQUIRED');
  const binding = record?.evidence?.native_start_rejection || state.evidence?.native_start_rejection;
  if (!binding) {
    assert(state.execution?.error?.code !== 'ASTRONSTUDIO_NATIVE_START_REJECTED', 'PROOF_REQUIRED');
    return null;
  }
  const root = await realpath(unitRoot);
  const read = async (path, boundary) => {
    const local = relative(boundary, path);
    assert(local && !isAbsolute(local) && local !== '..' && !local.startsWith('../'), 'PROOF_PATH');
    const info = await lstat(path);
    assert(info.isFile() && !info.isSymbolicLink() && info.size <= 64 * 1024 * 1024
      && await realpath(path) === path, 'PROOF_FILE');
    return readFile(path);
  };
  assert(typeof binding.path === 'string' && !isAbsolute(binding.path), 'PROOF_PATH');
  const path = resolve(root, binding.path), bytes = await read(path, root);
  assert(digest(bytes) === binding.sha256
    && binding.sha256 === state.evidence?.native_start_rejection?.sha256, 'PROOF_SHA');
  const proof = JSON.parse(bytes);
  assert([START_REJECTION_PROFILE, IDLE_PREWARM_REJECTION_PROFILE].includes(proof.profile)
    && JSON.stringify(proof.identity) === JSON.stringify(state.identity), 'PROOF_IDENTITY');
  assert(Array.isArray(proof.files) && proof.files.length === 3
    && [...proof.files.map(row => row.path)].sort().join('|') === 'native-snapshot.json|original-execution-record.json|original-state.json', 'PROOF_SOURCES');
  const files = [{ path: 'proof.json', bytes }]; const sources = {};
  for (const row of proof.files) {
    const value = await read(join(dirname(path), row.path), dirname(path));
    assert(digest(value) === row.sha256 && value.length === row.size, 'SOURCE_SHA');
    files.push({ path: row.path, bytes: value }); sources[row.path] = JSON.parse(value);
  }
  const original = sources['original-state.json'], oldRecord = sources['original-execution-record.json'];
  assert(JSON.stringify(original.identity) === JSON.stringify(state.identity)
    && JSON.stringify(oldRecord.identity) === JSON.stringify(state.identity)
    && original.prompt.sha256 === state.prompt.sha256
    && oldRecord.prompt.sha256 === state.prompt.sha256
    && original.candidate_workspace === state.candidate_workspace, 'ORIGINAL_BINDING');
  const replay = verifyNativeStartRejection(sources['native-snapshot.json'], original, {
    candidateWorkspace: state.candidate_workspace, promptSha256: state.prompt.sha256,
    expectedPermission: state.client.permission, expectedModel: state.client.model,
    expectedReasoning: state.client.reasoning, runConfig: {},
  });
  for (const [key, value] of Object.entries(replay)) assert(JSON.stringify(proof[key]) === JSON.stringify(value), 'REPLAY_' + key);
  assert(state.phase === 'FAILED' && state.execution.business_status === 'candidate_error'
    && state.execution.error?.code === 'ASTRONSTUDIO_NATIVE_START_REJECTED'
    && state.execution.error.message === replay.error && state.execution.native_rejected_at === replay.failed_at
    && state.prompt.send_status === 'sent' && state.send.dispatch_attempt_count === 1
    && state.session.verified === false && state.session.thread_id === replay.thread_id
    && state.session.turn_id === null && state.session.session_id === null
    && state.session.cwd === state.candidate_workspace, 'DERIVED_STATE');
  if (record) assert(JSON.stringify(record.identity) === JSON.stringify(state.identity)
    && record.prompt.sha256 === state.prompt.sha256 && record.phase === 'FAILED'
    && record.execution.business_status === 'candidate_error' && record.session.verified === false
    && record.session.turn_id === null && record.session.session_id === null, 'RECORD_BINDING');
  return { proof, binding, files };
}
