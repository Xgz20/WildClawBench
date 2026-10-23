import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { FINAL_RECAPTURE_INPUT, FINAL_RECAPTURE_PROFILE } from '../../../tools/report/e2e-shared/general-resource-supplements/astronstudio-terminal-final-recapture.mjs';
export const digest = bytes => createHash('sha256').update(bytes).digest('hex');
export const pretty = value => Buffer.from(JSON.stringify(value, null, 2) + '\n');
export function recaptureFixture(state = null) {
  const prompt = 'Do the task.\n', old = 'Checking the final state.', final = 'Done.';
  const s = structuredClone(state ?? { identity: { batch_id: 'batch', unit_id: 'unit', task_id: 'task', attempt_id: 'attempt' },
    phase: 'COMPLETED', execution: { business_status: 'completed' },
    send: { dispatch_attempt_count: 1 }, prompt: { sha256: digest(Buffer.from(prompt)), send_status: 'sent' },
    session: { thread_id: 'thread', turn_id: 'turn', session_id: 'session', cwd: '/synthetic/workspace', verified: true, native_status: 'completed' } });
  s.client = { ...s.client, custom_model_binding: { config_id: 'config', execution_revision: 3,
    configured_model_name: 'model', native_binding_verified: true, reasoning_effort: 'high' },
    workspace_selection: { project_id: 'project' } };
  s.evidence = { ...s.evidence, final_response_sha256: digest(Buffer.from(old + '\n')) };
  const { thread_id: thread, turn_id: turn, session_id: session, cwd } = s.session;
  const time = n => `2026-09-18T00:00:${String(n).padStart(2, '0')}.000Z`;
  const r = (type, payload, n) => ({ timestamp: time(n), type, payload });
  const message = (id, text) => ({ type: 'message', role: 'assistant', id, content: [{ type: 'output_text', text }] });
  const sdk = [r('session_meta', { id: session, cwd }, 0), r('event_msg', { type: 'task_started', turn_id: turn }, 1),
    r('turn_context', { turn_id: turn, cwd, model: 'custom/Y29uZmln/3/bW9kZWw', effort: 'high' }, 1),
    r('event_msg', { type: 'user_message', message: prompt }, 2),
    r('event_msg', { type: 'agent_message', message: old }, 3), r('response_item', message('old', old), 3),
    r('event_msg', { type: 'agent_message', message: final }, 9),
    r('response_item', message('final', final), 9),
    r('event_msg', { type: 'task_complete', turn_id: turn, last_agent_message: final, duration_ms: 9000 }, 10)];
  const event = (sequence, type, payload, itemId = null) => {
    const at = time(type === 'turn.completed' ? 10 : itemId === 'final' ? 9 : sequence);
    const e = { type, eventId: 'event-' + sequence, threadId: thread, turnId: turn,
      createdAt: at, lifecycleGeneration: 'life', providerRefs: { providerThreadId: session, providerTurnId: turn },
      ...(itemId ? { itemId } : {}), payload };
    return { sequence, event_id: e.eventId, thread_id: thread, turn_id: turn, lifecycle_generation: 'life',
      event_type: type, event_json: JSON.stringify(e), persisted_at: at };
  };
  const itemPayload = (type, item) => ({ itemType: type, status: 'completed', data: { threadId: session, turnId: turn, item } });
  const provider = [event(1, 'turn.started', {}),
    event(2, 'item.completed', itemPayload('user_message', { type: 'userMessage', id: 'user', content: [{ type: 'text', text: prompt }] }), 'user'),
    event(3, 'item.completed', itemPayload('assistant_message', { type: 'agentMessage', id: 'old', text: old }), 'old'),
    event(4, 'item.completed', itemPayload('assistant_message', { type: 'agentMessage', id: 'final', text: final }), 'final'),
    event(5, 'turn.completed', { state: 'completed' })];
  const messages = [['old', old], ['final', final]].map(([id, text], i) => ({ message_id: 'assistant:' + id,
    thread_id: thread, turn_id: turn, role: 'assistant', text, is_streaming: 0, sequence: i + 1 }));
  return { originalState: s, originalFinal: Buffer.from(old + '\n'), sdk, provider, messages,
    binding: { thread_id: thread, latest_turn_id: turn, session_id: session, workspace_root: cwd, project_id: 'project' },
    turn: { thread_id: thread, turn_id: turn, state: 'completed', completed_at: time(10), assistant_message_id: 'assistant:final' },
    candidateBefore: [], candidateAfter: [] };
}
export async function writeRecaptureInput(root, data, review = Buffer.from('Reviewed strict profile.\n')) {
  await mkdir(join(root, 'inputs'), { recursive: true });
  const values = { original_state: pretty(data.originalState), original_record: pretty({ identity: data.originalState.identity }),
    original_final: data.originalFinal, native_binding: pretty(data.binding), native_turn: pretty(data.turn), native_messages: pretty(data.messages),
    provider_rows: Buffer.from(data.provider.map(row => JSON.stringify(row)).join('\n') + '\n'),
    sdk: Buffer.from(data.sdk.map(row => JSON.stringify(row)).join('\n') + '\n'), candidate_tree: pretty(data.candidateBefore),
    authorization: pretty({ status: 'GRANTED', profile: FINAL_RECAPTURE_PROFILE, source: 'synthetic explicit human approval',
      scope: 'strict profile', review_sha256: digest(review) }), authorization_review: review };
  const sources = {};
  for (const [role, bytes] of Object.entries(values)) {
    const path = 'inputs/' + role + (['original_final', 'authorization_review'].includes(role) ? '.md' : '.json');
    await writeFile(join(root, path), bytes); sources[role] = { path, sha256: digest(bytes), size: bytes.length };
  }
  const manifest = { schema_version: FINAL_RECAPTURE_INPUT, profile: FINAL_RECAPTURE_PROFILE,
    created_at: '2026-09-18T00:00:11.000Z', sources };
  const path = join(root, 'input-manifest.json'); await writeFile(path, pretty(manifest)); return path;
}
