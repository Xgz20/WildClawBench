// Confirm physical runtime interruption, never an operator cancellation or score.
import { createHash } from 'node:crypto';
import { readFile, lstat, realpath } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { analyzeRollout, ROLLOUT_PATH } from './astronstudio-rollout.mjs';

export const RUNTIME_INTERRUPTION_PROFILE = 'bound-native-runtime-interruption/v1';
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
    && state.session?.native_status === 'interrupted';
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
  const ends = rows.filter(r => r.event_type === 'turn.completed');
  ensure(ends.length === 1, 'PROVIDER_TERMINAL_AMBIGUOUS');
  const row = ends[0], event = row.event, raw = event?.raw?.payload;
  ensure(row.thread_id === session.thread_id && row.turn_id === session.turn_id
    && event.threadId === session.thread_id && event.turnId === session.turn_id
    && event.providerRefs?.providerThreadId === session.session_id
    && event.providerRefs?.providerTurnId === session.turn_id
    && event.payload?.state === 'interrupted' && raw?.threadId === session.session_id
    && raw.turn?.id === session.turn_id && raw.turn.status === 'interrupted'
    && raw.turn.error === null && raw.turn.completedAt === terminals[0].payload.completed_at
    && raw.turn.durationMs === terminals[0].payload.duration_ms, 'PROVIDER_SDK_MISMATCH');
  ensure(Number.isFinite(Date.parse(state.execution.finished_at))
    && Date.parse(state.execution.finished_at) >= Date.parse(terminals[0].timestamp), 'CLOCK_INVALID');
  return { profile: RUNTIME_INTERRUPTION_PROFILE, identity: state.identity,
    session: Object.fromEntries(['thread_id', 'turn_id', 'session_id', 'cwd'].map(k => [k, session[k]])),
    source_state_sha256: sha(stateBytes), sdk_sha256: sha(sdkBytes), provider_sha256: sha(providerBytes),
    native_binding_sha256: sha(Buffer.from(JSON.stringify(stable(nativeBinding)))),
    prompt_sha256: state.prompt.sha256, native_termination_origin: 'runtime',
    sdk_terminal_at: terminals[0].timestamp, sdk_duration_ms: terminals[0].payload.duration_ms,
    provider_terminal_sequence: row.sequence, cancellation_confirmed: true,
    human_cancellation_inferred: false, scoreability_changed: false, original_state_modified: false };
}

export async function verifyRuntimeInterruption(index, stateBytes, traceRoot, execution = undefined) {
  const paths = [RUNTIME_INTERRUPTION_STATE, RUNTIME_INTERRUPTION_NATIVE, RUNTIME_INTERRUPTION_PROOF];
  const bindings = index.binding_evidence ?? [];
  if (!index.runtime_interruption_profile && !bindings.some(r => paths.includes(r.path))) return null;
  ensure(index.runtime_interruption_profile?.id === RUNTIME_INTERRUPTION_PROFILE, 'DECLARATION_INVALID');
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
  ensure(same(proof, expected), 'PROOF_DRIFT');
  if (execution) ensure(same(execution.identity, proof.identity)
    && execution.execution.business_status === 'cancelled', 'RECORD_MISMATCH');
  return proof;
}
