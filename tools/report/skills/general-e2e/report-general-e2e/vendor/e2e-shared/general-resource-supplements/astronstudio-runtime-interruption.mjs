// Confirm physical runtime interruption, never an operator cancellation or score.
import { createHash } from 'node:crypto';
import { readFile, lstat, realpath } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { analyzeRollout, ROLLOUT_PATH } from './astronstudio-rollout.mjs';

export const RUNTIME_INTERRUPTION_PROFILE = 'bound-native-runtime-interruption/v1';
export const RUNTIME_INTERRUPTION_MISSING_PROFILE = 'bound-native-runtime-interruption-missing-projection/v1';
export const RUNTIME_INTERRUPTION_RECONCILED_PROFILE = 'bound-native-runtime-reconciled-interruption/v1';
export const RUNTIME_INTERRUPTION_STALE_SESSION_PROFILE = 'bound-native-runtime-interruption-stale-session/v1';
export const RUNTIME_INTERRUPTION_STATE = 'bindings/runtime-interruption-original-state.json';
export const RUNTIME_INTERRUPTION_NATIVE = 'bindings/runtime-interruption-native-binding.json';
export const RUNTIME_INTERRUPTION_PROOF = 'bindings/runtime-interruption-proof.json';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const ensure = (ok, code) => { if (!ok) throw Error('RUNTIME_INTERRUPTION_' + code); };
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])])) : value;
const same = (a, b) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));
export function runtimeInterruptionCandidate(state) {
  return state?.phase === 'FAILED' && state.execution?.business_status === 'cancelled'
    && (state.session?.native_status === 'interrupted'
      || state.session?.native_status === 'running' && state.execution?.error?.code === 'ASTRONSTUDIO_TURN_INTERRUPTED');
}

function reconciledInterruption(binding, state, terminal, rows) {
  const records = binding.restart_reconciliations;
  if (!records) return false;
  ensure(Array.isArray(records) && records.length === 1, 'RECONCILIATION_AMBIGUOUS');
  const record = records[0], receipt = record.receipt, payload = record.payload;
  const thread = state.session.thread_id;
  const command = `restart-reconcile:${thread}:${record.occurred_at}`;
  ensure(record.event_type === 'thread.session-set' && record.aggregate_kind === 'thread'
    && record.stream_id === thread && record.actor_kind === 'client'
    && record.command_id === command && record.correlation_id === command
    && record.causation_event_id === null && record.metadata?.persistedEventSchemaVersion === 1
    && Number.isSafeInteger(record.sequence) && record.sequence > 0 && typeof record.event_id === 'string'
    && payload?.threadId === thread && payload.session?.threadId === thread
    && payload.session.status === 'interrupted' && payload.session.activeTurnId === null
    && payload.session.lastError === null && payload.session.providerName === 'acode'
    && typeof payload.session.runtimeMode === 'string' && payload.session.runtimeMode
    && payload.session.updatedAt === record.occurred_at && binding.completed_at === record.occurred_at,
  'RECONCILIATION_EVENT_UNBOUND');
  ensure(receipt?.command_id === command && receipt.aggregate_kind === 'thread'
    && receipt.aggregate_id === thread && receipt.accepted_at === record.occurred_at
    && receipt.status === 'accepted' && receipt.error === null
    && receipt.result_sequence === record.sequence && receipt.fingerprint_version === 1
    && /^[a-f0-9]{64}$/.test(receipt.command_fingerprint ?? ''), 'RECONCILIATION_RECEIPT_UNBOUND');
  const time = Date.parse(record.occurred_at);
  ensure(Number.isFinite(time) && time >= Date.parse(terminal.timestamp)
    && time <= Date.parse(state.execution.finished_at), 'RECONCILIATION_CLOCK_INVALID');
  const permitted = new Set(['turn.started', 'item.started', 'item.completed', 'item.updated',
    'content.delta', 'thread.token-usage.updated', 'turn.gateway-usage.updated', 'turn.tasks.updated']);
  ensure(rows.length > 0 && binding.runtime_turn_event_count === rows.length
    && rows.every(row => permitted.has(row.event_type) && row.thread_id === thread
      && row.turn_id === state.session.turn_id && row.event?.type === row.event_type
      && row.event.threadId === thread && row.event.turnId === state.session.turn_id
      && (!row.event.providerRefs?.providerThreadId || row.event.providerRefs.providerThreadId === state.session.session_id)
      && (!row.event.providerRefs?.providerTurnId || row.event.providerRefs.providerTurnId === state.session.turn_id)),
  'RECONCILIATION_PARTIAL_PROJECTION_UNBOUND');
  return record;
}

function resourceMirror(row, state, sdk) {
  const e=row.event, raw=e?.raw, payload=raw?.payload, s=state.session;
  const fields={input_tokens:'inputTokens',cached_input_tokens:'cachedInputTokens',output_tokens:'outputTokens',
    reasoning_output_tokens:'reasoningOutputTokens',total_tokens:'totalTokens'};
  if (row.event_type!=='thread.token-usage.updated' || e?.type!=='thread.token-usage.updated'
    || row.thread_id!==s.thread_id || row.turn_id!==s.turn_id || e.threadId!==s.thread_id || e.turnId!==s.turn_id
    || e.providerRefs?.providerThreadId!==s.session_id || e.providerRefs?.providerTurnId!==s.turn_id
    || raw?.source!=='acode' || raw.method!=='thread/tokenUsage/updated'
    || payload?.threadId!==s.session_id || payload.turnId!==s.turn_id
    || Object.keys(e.payload ?? {}).join(',')!=='usage') return false;
  const total=payload.tokenUsage?.total,last=payload.tokenUsage?.last,usage=e.payload.usage;
  const converted = value => value && Object.keys(value).length===5
    ? Object.fromEntries(Object.entries(fields).map(([key,camel])=>[key,value[camel]])) : null;
  const a=converted(total),b=converted(last);
  const valid = v => v && Object.values(v).every(n => Number.isSafeInteger(n) && n>=0)
    && v.total_tokens===v.input_tokens+v.output_tokens && v.cached_input_tokens<=v.input_tokens
    && v.reasoning_output_tokens<=v.output_tokens;
  if (!valid(a) || !valid(b)) return false;
  if (!sdk.some(r=>r.type==='event_msg' && r.payload?.type==='token_count'
    && same(r.payload.info?.total_token_usage,a) && same(r.payload.info?.last_token_usage,b))) return false;
  return usage.totalProcessedTokens===total.totalTokens && usage.totalInputTokens===total.inputTokens
    && usage.totalCachedInputTokens===total.cachedInputTokens && usage.totalOutputTokens===total.outputTokens
    && usage.totalReasoningOutputTokens===total.reasoningOutputTokens && usage.lastUsedTokens===last.totalTokens
    && usage.lastInputTokens===last.inputTokens && usage.lastCachedInputTokens===last.cachedInputTokens
    && usage.lastOutputTokens===last.outputTokens && usage.lastReasoningOutputTokens===last.reasoningOutputTokens;
}

export function deriveRuntimeInterruption(stateBytes, index, sdkBytes, providerBytes, nativeBinding) {
  const state = JSON.parse(stateBytes), session = state.session;
  ensure(runtimeInterruptionCandidate(state) && session.verified === true
    && state.prompt.send_status === 'sent' && state.send.dispatch_attempt_count === 1, 'STATE_UNBOUND');
  ensure(same(index.identity, state.identity)
    && ['thread_id', 'turn_id', 'session_id', 'cwd'].every(k => index.session?.[k] === session[k])
    && index.canonical_source_policy?.id === 'bound-native-sdk-canonical/v1', 'INDEX_UNBOUND');
  ensure(nativeBinding?.turn_state === 'interrupted' && nativeBinding.termination_origin === 'runtime'
    && nativeBinding.latest_turn_id === session.turn_id && nativeBinding.session_status === 'interrupted'
    && nativeBinding.active_turn_id === null && nativeBinding.pending_count === 0
    && resolve(nativeBinding.cwd) === resolve(session.cwd)
    && Number.isFinite(Date.parse(nativeBinding.completed_at)), 'NATIVE_NOT_TERMINAL');
  analyzeRollout(sdkBytes, state);
  const sdk = sdkBytes.toString('utf8').split('\n').filter(x => x.trim()).map(JSON.parse);
  const terminals = sdk.filter(r => r.type === 'event_msg'
    && ['task_complete', 'turn_aborted'].includes(r.payload?.type) && r.payload.turn_id === session.turn_id);
  ensure(terminals.length === 1 && terminals[0].payload.type === 'turn_aborted'
    && terminals[0].payload.reason === 'interrupted', 'SDK_NOT_INTERRUPTED');
  const rows = providerBytes.toString('utf8').split('\n').filter(x => x.trim()).map(JSON.parse);
  const absent = providerBytes.length === 0 && rows.length === 0;
  const resourceOnly = rows.length>0 && nativeBinding.runtime_turn_event_count===rows.length
    && rows.every(row=>resourceMirror(row,state,sdk));
  const ends = rows.filter(r => r.event_type === 'turn.completed');
  const reconciliation = !absent && !resourceOnly && ends.length === 0
    ? reconciledInterruption(nativeBinding, state, terminals[0], rows) : false;
  const missingTerminal = absent || resourceOnly || Boolean(reconciliation);
  ensure(missingTerminal ? nativeBinding.runtime_turn_event_count === rows.length : ends.length === 1, 'PROVIDER_TERMINAL_AMBIGUOUS');
  const row = ends[0], event = row?.event, raw = event?.raw?.payload;
  if (!missingTerminal) ensure(row.thread_id === session.thread_id && row.turn_id === session.turn_id
    && event.threadId === session.thread_id && event.turnId === session.turn_id
    && event.providerRefs?.providerThreadId === session.session_id
    && event.providerRefs?.providerTurnId === session.turn_id
    && event.payload?.state === 'interrupted' && raw?.threadId === session.session_id
    && raw.turn?.id === session.turn_id && raw.turn.status === 'interrupted'
    && raw.turn.error === null && raw.turn.completedAt === terminals[0].payload.completed_at
    && raw.turn.durationMs === terminals[0].payload.duration_ms, 'PROVIDER_SDK_MISMATCH');
  ensure(Number.isFinite(Date.parse(state.execution.finished_at))
    && Date.parse(state.execution.finished_at) >= Date.parse(terminals[0].timestamp), 'CLOCK_INVALID');
  const staleSession = session.native_status === 'running';
  return { profile: staleSession ? RUNTIME_INTERRUPTION_STALE_SESSION_PROFILE
      : reconciliation ? RUNTIME_INTERRUPTION_RECONCILED_PROFILE
      : missingTerminal ? RUNTIME_INTERRUPTION_MISSING_PROFILE : RUNTIME_INTERRUPTION_PROFILE, identity: state.identity,
    session: Object.fromEntries(['thread_id', 'turn_id', 'session_id', 'cwd'].map(k => [k, session[k]])),
    source_state_sha256: sha(stateBytes), sdk_sha256: sha(sdkBytes), provider_sha256: sha(providerBytes),
    native_binding_sha256: sha(Buffer.from(JSON.stringify(stable(nativeBinding)))),
    prompt_sha256: state.prompt.sha256, native_termination_origin: 'runtime',
    sdk_terminal_at: terminals[0].timestamp, sdk_duration_ms: terminals[0].payload.duration_ms,
    provider_terminal_sequence: row?.sequence ?? null, cancellation_confirmed: true,
    ...(missingTerminal ? { provider_projection: { status:reconciliation?'partial-before-native-restart-reconciliation'
      :absent?'absent-at-collection':'verified-resource-only-at-collection',
      verified_turn_event_count:rows.length, evidence_completeness:'partial', fabricated_rows:0,
      basis:reconciliation?'same readonly SQL snapshot; explicit native restart-reconcile session event and accepted receipt close the exact interrupted head; provider terminal event remains missing'
        :absent?'same readonly SQL snapshot and zero-byte original projection':'same readonly SQL count; every row is a metric-only mirror matching original SDK total/last usage' } } : {}),
    ...(reconciliation ? { native_reconciliation: { sequence:reconciliation.sequence, event_id:reconciliation.event_id,
      command_id:reconciliation.command_id, occurred_at:reconciliation.occurred_at,
      command_fingerprint:reconciliation.receipt.command_fingerprint } } : {}),
    ...(staleSession ? { state_session_projection: { original_native_status:'running',
      verified_native_status:'interrupted', original_turn_error_code:state.execution.error.code,
      original_state_preserved:true, evidence_completeness:'partial' } } : {}),
    human_cancellation_inferred: false, scoreability_changed: false, original_state_modified: false };
}

export async function verifyRuntimeInterruption(index, stateBytes, traceRoot, execution = undefined) {
  const paths = [RUNTIME_INTERRUPTION_STATE, RUNTIME_INTERRUPTION_NATIVE, RUNTIME_INTERRUPTION_PROOF];
  const bindings = index.binding_evidence ?? [];
  if (!index.runtime_interruption_profile && !bindings.some(r => paths.includes(r.path))) return null;
  ensure([RUNTIME_INTERRUPTION_PROFILE, RUNTIME_INTERRUPTION_MISSING_PROFILE,
    RUNTIME_INTERRUPTION_RECONCILED_PROFILE, RUNTIME_INTERRUPTION_STALE_SESSION_PROFILE]
    .includes(index.runtime_interruption_profile?.id), 'DECLARATION_INVALID');
  async function bound(path) {
    const refs = [...(index.raw_trace ?? []), ...bindings].filter(r => r.path === path);
    ensure(refs.length === 1, 'ARTIFACT_AMBIGUOUS');
    const full = resolve(traceRoot, path);
    ensure(full.startsWith(resolve(traceRoot) + sep), 'ARTIFACT_ESCAPE');
    const info = await lstat(full); ensure(info.isFile() && !info.isSymbolicLink()
      && info.size <= 64 * 1024 * 1024, 'ARTIFACT_INVALID');
    ensure((await realpath(full)).startsWith((await realpath(traceRoot)) + sep), 'ARTIFACT_ESCAPE');
    const bytes = await readFile(full);
    ensure(bytes.length === refs[0].size && sha(bytes) === refs[0].sha256, 'ARTIFACT_DRIFT');
    return bytes;
  }
  const original = await bound(RUNTIME_INTERRUPTION_STATE);
  ensure(original.equals(stateBytes), 'STATE_DRIFT');
  const native = JSON.parse(await bound(RUNTIME_INTERRUPTION_NATIVE));
  const proof = JSON.parse(await bound(RUNTIME_INTERRUPTION_PROOF));
  const sdk = await bound(ROLLOUT_PATH), provider = await bound('raw/astronstudio-provider-events.jsonl');
  const expected = deriveRuntimeInterruption(original, index, sdk, provider, native);
  ensure(index.runtime_interruption_profile.id === expected.profile, 'PROFILE_MISMATCH');
  ensure(same(proof, expected), 'PROOF_DRIFT');
  if (execution) ensure(same(execution.identity, proof.identity)
    && execution.execution.business_status === 'cancelled', 'RECORD_MISMATCH');
  return proof;
}
