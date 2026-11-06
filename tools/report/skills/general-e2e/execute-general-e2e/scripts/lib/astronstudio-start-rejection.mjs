import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { withStateSnapshot, querySnapshot, STATE_SNAPSHOT_TABLES, START_REJECTION_TABLES } from './astronstudio-state.mjs';

export const START_REJECTION_PROFILE = 'bound-native-unsubmitted-start-rejection/v1';
const digest = text => createHash('sha256').update(text).digest('hex');
const sql = text => `'${String(text).replaceAll("'", "''")}'`;
const assert = (ok, code) => { if (!ok) throw new Error(`NATIVE_START_REJECTION_${code}`); };
const one = (rows, code) => { assert(rows?.length === 1, code); return rows[0]; };

// Every row comes from one integrity-checked snapshot. No provider operation,
// UI action, cancellation or replay is performed by this reader.
export async function queryNativeStartRejection(database, state, overrides = {}) {
  const thread = state.send?.post_send_route_thread_id;
  assert(thread && thread === state.send?.pre_send_route_thread_id, 'ROUTE');
  return withStateSnapshot(database, async snapshot => {
    const data = {};
    for (const table of [...STATE_SNAPSHOT_TABLES, ...START_REJECTION_TABLES]) {
      const where = table === 'projection_projects'
        ? `project_id IN (SELECT project_id FROM projection_threads WHERE thread_id=${sql(thread)})`
        : table === 'orchestration_events' ? `stream_id=${sql(thread)}`
        : table === 'orchestration_command_receipts' ? `aggregate_id=${sql(thread)}`
        : `thread_id=${sql(thread)}`;
      data[table] = await querySnapshot(snapshot, `SELECT * FROM ${table} WHERE ${where}`, overrides);
    }
    return data;
  }, overrides, [...STATE_SNAPSHOT_TABLES, ...START_REJECTION_TABLES]);
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
  assert(session.thread_id === route && session.status === 'error' && !session.active_turn_id
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
  assert(data.provider_runtime_events?.every(row => row.thread_id === route && !row.turn_id
    && row.event_type === 'account.rate-limits.updated'), 'PROVIDER_ACTIVITY');
  const runtime = one(data.provider_session_runtime, 'RUNTIME');
  const cursor = JSON.parse(runtime.resume_cursor_json || '{}');
  const runtimePayload = JSON.parse(runtime.runtime_payload_json || '{}');
  assert(runtime.thread_id === route && runtime.status === 'stopped' && cursor.emptyPrewarm === true
    && !runtimePayload.activeTurnId && resolve(runtimePayload.cwd || '') === resolve(config.candidateWorkspace), 'PREWARM');
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
    && payload.detail === session.last_error
    && payload.detail.includes('ACode turn submission did not complete within 20000ms.')
    && payload.detail.includes('/Applications/AStudio.app/Contents/Resources/app.asar/'), 'FAILURE_BINDING');
  const delivery = one(data.orchestration_event_deliveries.filter(row => row.event_sequence === request.sequence), 'DELIVERY');
  assert(delivery.consumer_name === 'provider-command-reactor.v1' && delivery.thread_id === route
    && delivery.state === 'succeeded' && delivery.submission_state === 'not-submitted-v1'
    && delivery.attempt_count === 1 && !delivery.claim_owner && !delivery.claim_expires_at
    && delivery.completed_at === activity.createdAt && session.updated_at === activity.createdAt
    && Date.parse(activity.createdAt) > Date.parse(message.created_at), 'SETTLEMENT');
  assert(data.orchestration_event_deliveries.every(row => row.state === 'succeeded'
    && !row.claim_owner && !row.claim_expires_at), 'OTHER_DELIVERY');
  return { profile: START_REJECTION_PROFILE, thread_id: route, project_id: project.project_id,
    message_id: message.message_id, request_sequence: request.sequence, request_command_id: request.command_id,
    failed_at: activity.createdAt, error: payload.detail, prompt_sha256: state.prompt.sha256,
    native_turn_id: null, native_sdk_session_id: null, pending_dispatches: 0,
    failure_origin: 'harness-native-turn-start', framework_prompt_delivery_verified: true,
    retry_performed: false, cancellation_performed: false };
}
