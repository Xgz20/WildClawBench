import { createHash } from 'node:crypto';
const sha = value => createHash('sha256').update(value).digest('hex');
export function rejectionFixture(workspace = '/tmp/subject/workspace') {
  const prompt = 'Create the requested deliverables.';
  const created = '2026-11-06T06:28:17.904Z', failed = '2026-11-06T06:29:11.361Z';
  const error = 'ACode turn submission did not complete within 20000ms. at /Applications/AStudio.app/Contents/Resources/app.asar/apps/server/dist/index.mjs:119910:9';
  const model = { provider: 'acode', model: 'spark-x2.6', options: { reasoningEffort: 'high' } };
  const state = { phase: 'NEEDS_ATTENTION', identity: { batch_id: 'batch', unit_id: 'astronstudio-macos', task_id: 'task', attempt_id: 'original' },
    dataset: { id: 'dataset', digest: 'f'.repeat(64) }, driver: { id: 'astronstudio-macos', version: '0.4.18' },
    run_config: { config_digest: 'config' }, candidate_workspace: workspace,
    prompt: { sha256: sha(prompt), send_status: 'uncertain', sent_at: '2026-11-06T06:28:17.703Z' },
    session: { verified: false, thread_id: null, turn_id: null, session_id: null, baseline: [] },
    send: { dispatch_attempt_count: 1, pre_send_route_thread_id: 'thread', post_send_route_thread_id: 'thread',
      dispatch_armed_at: '2026-11-06T06:28:17.703Z', dispatch_completed_at: '2026-11-06T06:28:18.343Z' },
    client: { version: '3.6.0', model: 'Spark-X2.6', reasoning: 'High', permission: '完全访问',
      workspace_selection: { project_id: 'project', thread_id: 'thread', path: workspace } },
    execution: { flow_profile: 'prompt-send-to-controller-terminal/v1', error: { code: 'PROMPT_SEND_UNCERTAIN' } },
    evidence: {}, human_assistance: { operation_count: 0 }, history: [] };
  const event = (sequence, type, payload, extra = {}) => ({ sequence, event_type: type, stream_id: 'thread', actor_kind: 'client', payload_json: JSON.stringify(payload), ...extra });
  const data = { projection_threads: [{ thread_id: 'thread', project_id: 'project', latest_turn_id: null, runtime_mode: 'full-access', model_selection_json: JSON.stringify(model) }],
    projection_projects: [{ project_id: 'project', workspace_root: workspace }],
    projection_thread_sessions: [{ thread_id: 'thread', status: 'error', last_error: error, updated_at: failed }],
    projection_thread_messages: [{ message_id: 'message', thread_id: 'thread', role: 'user', text: prompt, source: 'native', dispatch_origin: 'user', dispatch_mode: 'queue', created_at: created, sequence: 10 }],
    projection_turns: [], projection_pending_interactions: [], provider_runtime_open_turns: [], queued_turn_promotions: [], provider_runtime_events: [],
    provider_session_runtime: [{ thread_id: 'thread', status: 'stopped', resume_cursor_json: '{"emptyPrewarm":true}', runtime_payload_json: JSON.stringify({ cwd: workspace, activeTurnId: null }) }],
    orchestration_events: [event(10, 'thread.message-sent', { messageId: 'message', text: prompt }, { command_id: 'command', event_id: 'sent' }),
      event(11, 'thread.turn-start-requested', { threadId: 'thread', messageId: 'message', requestCommandId: 'command', createdAt: created, modelSelection: model, runtimeMode: 'full-access' }, { command_id: 'command', causation_event_id: 'sent' }),
      event(12, 'thread.activity-appended', { activity: { id: 'provider-start-failed:11:1', kind: 'provider.turn.start.failed', turnId: null, createdAt: failed,
        payload: { messageId: 'message', requestCommandId: 'command', requestCreatedAt: created, eventSequence: 11, preparationTerminal: true, settlementStatus: 'rejected', submissionState: 'not-sent', detail: error } } })],
    orchestration_command_receipts: [{ command_id: 'command', aggregate_id: 'thread', aggregate_kind: 'thread', status: 'accepted', error: null, result_sequence: 11, accepted_at: created, command_fingerprint: 'a'.repeat(64) }],
    orchestration_event_deliveries: [{ consumer_name: 'provider-command-reactor.v1', event_sequence: 11, thread_id: 'thread', state: 'succeeded', submission_state: 'not-submitted-v1', attempt_count: 1, completed_at: failed }] };
  const config = { candidateWorkspace: workspace, promptSha256: sha(prompt), expectedPermission: '完全访问', expectedModel: 'Spark-X2.6', expectedReasoning: 'High', runConfig: { tested_model: {} } };
  return { state, data, config };
}
