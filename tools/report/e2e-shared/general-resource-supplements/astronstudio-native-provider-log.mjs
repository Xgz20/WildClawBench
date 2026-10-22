import { createHash } from 'node:crypto';
import { lstat, readFile, realpath } from 'node:fs/promises';
import { dirname, isAbsolute, relative, resolve } from 'node:path';

export const NATIVE_LOG_BUNDLE_SCHEMA = 'wildclawbench.astronstudio-native-provider-log-bundle/v1';
const RAW_PATH = 'raw/astronstudio-native-provider-notifications.log';
const TYPES = new Map([['turn/started', 'turn.started'], ['turn/completed', 'turn.completed'],
  ['item/started', 'item.started'], ['item/completed', 'item.completed'],
  ['thread/tokenUsage/updated', 'thread.token-usage.updated']]);
const IGNORED = new Set(['item/reasoning/summaryTextDelta', 'item/agentMessage/delta',
  'turn.gateway-usage.updated', 'item/reasoning/summaryPartAdded']);
const ITEM_TYPES = new Set(['reasoning', 'userMessage', 'agentMessage', 'commandExecution',
  'fileChange', 'mcpToolCall', 'dynamicToolCall', 'webSearch', 'imageView', 'plan',
  'contextCompaction', 'collabAgentSpawn', 'collabAgentInteraction', 'collabAgentWait',
  'collabAgentClose', 'collabAgentResume']);
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const ensure = (ok, code) => { if (!ok) throw Error(code); };

export function parseBoundNativeLog(bytes, state) {
  ensure(state.phase === 'COMPLETED', 'NATIVE_LOG_COMPLETED_STATE_REQUIRED');
  ensure(state.session?.verified === true, 'NATIVE_LOG_STATE_NOT_BOUND');
  const lines = bytes.toString('utf8').trimEnd().split('\n');
  ensure(lines.length > 0 && lines[0], 'NATIVE_LOG_EMPTY');
  const rows = [], seen = new Set(), lifecycles = new Set(), methods = {};
  let previousTime = -Infinity;
  for (const [i, line] of lines.entries()) {
    const match = /^\[([^\]]+)\] NTIVE: (.+)$/u.exec(line);
    ensure(match, 'NATIVE_LOG_FORMAT_UNKNOWN');
    const event = JSON.parse(match[2]);
    ensure(event.kind === 'notification', 'NATIVE_LOG_KIND_UNKNOWN');
    ensure(event.threadId === state.session.thread_id && event.turnId === state.session.turn_id
      && event.providerThreadId === state.session.session_id, 'NATIVE_LOG_IDENTITY_MISMATCH');
    ensure(typeof event.id === 'string' && event.id.length > 0 && !seen.has(event.id), 'NATIVE_LOG_EVENT_ID_INVALID');
    const at = Date.parse(event.createdAt);
    ensure(Number.isFinite(at) && at >= previousTime, 'NATIVE_LOG_TIME_INVALID');
    previousTime = at; seen.add(event.id);
    methods[event.method] = (methods[event.method] || 0) + 1;
    const type = TYPES.get(event.method);
    if (!type) {
      ensure(IGNORED.has(event.method), 'NATIVE_LOG_METHOD_UNKNOWN');
      continue;
    }
    lifecycles.add(event.lifecycleGeneration);
    if (type.startsWith('item.')) {
      ensure(event.payload?.item && event.itemId === event.payload.item.id, 'NATIVE_LOG_ITEM_IDENTITY_MISMATCH');
      ensure(ITEM_TYPES.has(event.payload.item.type), 'NATIVE_LOG_ITEM_TYPE_UNKNOWN');
    }
    if (type.startsWith('turn.')) {
      ensure(event.payload?.turn?.id === state.session.turn_id, 'NATIVE_LOG_TURN_IDENTITY_MISMATCH');
      if (type === 'turn.completed' && state.phase === 'COMPLETED') {
        ensure(event.payload.turn.status === 'completed' && !event.payload.turn.error, 'NATIVE_LOG_TERMINAL_CONFLICT');
      }
    }
    // This is a comparison view. The ordinal is the retained original log line,
    // never an assertion about a missing runtime database sequence.
    rows.push({ sequence: i + 1, raw_line: i + 1, raw_ref: `${RAW_PATH}#L${i + 1}`,
      event_id: event.id, thread_id: event.threadId, turn_id: event.turnId,
      lifecycle_generation: event.lifecycleGeneration, event_type: type, persisted_at: match[1],
      event: { id: event.id, type, threadId: event.threadId, turnId: event.turnId,
        createdAt: event.createdAt, itemId: event.itemId ?? null,
        providerRefs: { providerThreadId: event.providerThreadId },
        payload: type.startsWith('item.') ? { data: { item: event.payload.item } } : event.payload } });
  }
  ensure(lifecycles.size === 1 && typeof [...lifecycles][0] === 'string' && [...lifecycles][0], 'NATIVE_LOG_LIFECYCLE_AMBIGUOUS');
  ensure(methods['turn/started'] === 1 && methods['turn/completed'] === 1, 'NATIVE_LOG_TERMINAL_BOUNDARY_MISSING');
  return { rows, lifecycle_generation: [...lifecycles][0], native_line_count: lines.length,
    methods, raw_path: RAW_PATH, original_bytes: bytes };
}

async function readArtifact(root, item) {
  ensure(item && typeof item.path === 'string' && !isAbsolute(item.path), 'NATIVE_LOG_ARTIFACT_PATH_INVALID');
  const path = resolve(root, item.path);
  ensure(relative(root, path) && !relative(root, path).startsWith('..'), 'NATIVE_LOG_ARTIFACT_PATH_INVALID');
  ensure((await lstat(path)).isFile() && !(await lstat(path)).isSymbolicLink(), 'NATIVE_LOG_ARTIFACT_NOT_REGULAR');
  const realRoot = await realpath(root), realPath = await realpath(path);
  ensure(relative(realRoot, realPath) && !relative(realRoot, realPath).startsWith('..'), 'NATIVE_LOG_ARTIFACT_PATH_INVALID');
  const bytes = await readFile(path);
  ensure(item.sha256 === sha256(bytes) && item.size === bytes.length, 'NATIVE_LOG_ARTIFACT_SHA_MISMATCH');
  return bytes;
}

function assertBundleIdentity(manifest, state, stateBytes) {
  ensure(manifest.schema_version === NATIVE_LOG_BUNDLE_SCHEMA, 'NATIVE_LOG_BUNDLE_SCHEMA_UNSUPPORTED');
  for (const key of ['batch_id', 'unit_id', 'task_id', 'attempt_id']) ensure(manifest.identity?.[key] === state.identity?.[key], 'NATIVE_LOG_ATTEMPT_MISMATCH');
  for (const key of ['thread_id', 'turn_id', 'session_id', 'cwd']) ensure(manifest.session?.[key] === state.session?.[key], 'NATIVE_LOG_SESSION_MISMATCH');
  ensure(manifest.execution_state_sha256 === sha256(stateBytes), 'NATIVE_LOG_EXECUTION_STATE_SHA_MISMATCH');
}

function comparisonViewBytes(parsed) {
  return Buffer.from(JSON.stringify({ profile: 'bound-native-provider-log-comparison/v1',
    database_sequences_available: false, rows: parsed.rows }, null, 2) + '\n');
}

function assertProvenance(provenance, nativeBytes, parsed) {
  ensure(provenance.selected_bytes_sha256 === sha256(nativeBytes), 'NATIVE_LOG_PROVENANCE_SHA_MISMATCH');
  ensure(provenance.selected_lines === parsed.native_line_count, 'NATIVE_LOG_PROVENANCE_COUNT_MISMATCH');
  ensure(Array.isArray(provenance.sources) && provenance.sources.length > 0
    && provenance.sources.every(s => typeof s.source_path === 'string'
      && /^[a-f0-9]{64}$/u.test(s.captured_source_sha256)
      && Number.isInteger(s.captured_size) && s.captured_size > 0
      && Array.isArray(s.selected_original_line_numbers)
      && s.selected_original_line_numbers.every(n => Number.isInteger(n) && n > 0))
    && provenance.sources.reduce((n, s) => n + s.selected_original_line_numbers.length, 0) === parsed.native_line_count,
  'NATIVE_LOG_PROVENANCE_INVALID');
}

export async function readBoundNativeLogBundle(manifestPath, state, stateBytes) {
  const manifestBytes = await readFile(manifestPath);
  const manifest = JSON.parse(manifestBytes.toString('utf8'));
  assertBundleIdentity(manifest, state, stateBytes);
  const root = dirname(resolve(manifestPath));
  const nativeBytes = await readArtifact(root, manifest.native_log);
  const provenanceBytes = await readArtifact(root, manifest.provenance);
  const provenance = JSON.parse(provenanceBytes.toString('utf8'));
  const parsed = parseBoundNativeLog(nativeBytes, state);
  assertProvenance(provenance, nativeBytes, parsed);
  const comparisonBytes = comparisonViewBytes(parsed);
  const bindingArtifacts = [
    { path: 'bindings/native-provider-log-manifest.json', bytes: manifestBytes },
    { path: 'bindings/native-provider-log-provenance.json', bytes: provenanceBytes },
    { path: 'bindings/native-provider-log-comparison.json', bytes: comparisonBytes },
  ];
  return { ...parsed, binding_artifacts: bindingArtifacts };
}

export async function verifyArchivedNativeLog(index, state, stateBytes, root) {
  const profile = index.native_provider_log_profile;
  ensure(profile?.id === 'bound-native-provider-log/v1'
    && profile.runtime_turn_projection_event_count === 0
    && profile.comparison_rows_are_database_sequences === false
    && index.canonical_source_policy?.id === 'bound-native-sdk-canonical/v1'
    && !Object.hasOwn(index, 'raw_event_range')
    && index.raw_trace?.length === 2
    && index.raw_trace.some(a => a.path === 'raw/astronstudio-rollout.jsonl'), 'NATIVE_LOG_PROFILE_INVALID');
  const raw = index.raw_trace?.find(a => a.path === RAW_PATH);
  ensure(raw, 'NATIVE_LOG_ORIGINAL_MISSING');
  const nativeBytes = await readArtifact(root, raw);
  const bindings = index.binding_evidence ?? [];
  const get = name => {
    const matches = bindings.filter(a => a.path === name);
    ensure(matches.length === 1, 'NATIVE_LOG_BINDING_ARTIFACT_MISSING');
    return readArtifact(root, matches[0]);
  };
  const manifest = JSON.parse((await get('bindings/native-provider-log-manifest.json')).toString('utf8'));
  assertBundleIdentity(manifest, state, stateBytes);
  ensure(manifest.native_log?.sha256 === sha256(nativeBytes) && manifest.native_log.size === nativeBytes.length, 'NATIVE_LOG_ARTIFACT_SHA_MISMATCH');
  const provenanceBytes = await get('bindings/native-provider-log-provenance.json');
  ensure(manifest.provenance?.sha256 === sha256(provenanceBytes), 'NATIVE_LOG_PROVENANCE_SHA_MISMATCH');
  const parsed = parseBoundNativeLog(nativeBytes, state);
  assertProvenance(JSON.parse(provenanceBytes.toString('utf8')), nativeBytes, parsed);
  ensure(profile.native_notification_count === parsed.native_line_count
    && index.session.lifecycle_generation === parsed.lifecycle_generation, 'NATIVE_LOG_PROFILE_INVALID');
  ensure(sha256(await get('bindings/native-provider-log-comparison.json')) === sha256(comparisonViewBytes(parsed)), 'NATIVE_LOG_COMPARISON_VIEW_MISMATCH');
  return parsed;
}
