import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { parseBoundNativeLog, readBoundNativeLogBundle, verifyArchivedNativeLog, sha256, NATIVE_LOG_BUNDLE_SCHEMA }
  from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-native-provider-log.mjs';

const state = { phase: 'COMPLETED', identity: { batch_id: 'batch', unit_id: 'unit', task_id: 'task', attempt_id: 'attempt' },
  session: { verified: true, thread_id: 'thread', turn_id: 'turn', session_id: 'session', cwd: '/synthetic/workspace' } };
const fixture = () => [
  { id: 'start', kind: 'notification', threadId: 'thread', turnId: 'turn', providerThreadId: 'session',
    lifecycleGeneration: 'life', method: 'turn/started', createdAt: '2026-01-01T00:00:00.000Z', payload: { turn: { id: 'turn', status: 'inProgress' } } },
  { id: 'end', kind: 'notification', threadId: 'thread', turnId: 'turn', providerThreadId: 'session',
    lifecycleGeneration: 'life', method: 'turn/completed', createdAt: '2026-01-01T00:00:01.000Z', payload: { turn: { id: 'turn', status: 'completed', error: null } } },
];
const bytes = events => Buffer.from(events.map(e => `[${e.createdAt}] NTIVE: ${JSON.stringify(e)}`).join('\n') + '\n');
test('exact original log identity and boundaries produce a derived view, not DB sequences', () => {
  const raw = bytes(fixture()), value = parseBoundNativeLog(raw, state);
  assert.equal(value.native_line_count, 2);
  assert.equal(value.lifecycle_generation, 'life');
  assert.equal(value.rows[0].raw_ref, 'raw/astronstudio-native-provider-notifications.log#L1');
  assert.deepEqual(value.original_bytes, raw);
});
for (const [name, mutate, code] of [
  ['other thread', x => { x[0].threadId = 'other'; }, 'NATIVE_LOG_IDENTITY_MISMATCH'],
  ['other turn', x => { x[0].turnId = 'other'; }, 'NATIVE_LOG_IDENTITY_MISMATCH'],
  ['other provider session', x => { x[0].providerThreadId = 'other'; }, 'NATIVE_LOG_IDENTITY_MISMATCH'],
  ['unknown event kind', x => { x[0].kind = 'request'; }, 'NATIVE_LOG_KIND_UNKNOWN'],
  ['duplicate event id', x => { x[1].id = x[0].id; }, 'NATIVE_LOG_EVENT_ID_INVALID'],
  ['mixed lifecycle', x => { x[1].lifecycleGeneration = 'other'; }, 'NATIVE_LOG_LIFECYCLE_AMBIGUOUS'],
  ['missing lifecycle', x => { delete x[0].lifecycleGeneration; delete x[1].lifecycleGeneration; }, 'NATIVE_LOG_LIFECYCLE_AMBIGUOUS'],
  ['missing completed boundary', x => { x.pop(); }, 'NATIVE_LOG_TERMINAL_BOUNDARY_MISSING'],
  ['unknown method', x => { x[0].method = 'item/unknown'; }, 'NATIVE_LOG_METHOD_UNKNOWN'],
  ['wrong turn payload', x => { x[0].payload.turn.id = 'other'; }, 'NATIVE_LOG_TURN_IDENTITY_MISMATCH'],
  ['terminal contradicts completed state', x => { x[1].payload.turn.status = 'error'; }, 'NATIVE_LOG_TERMINAL_CONFLICT'],
  ['backward timestamp', x => { x[1].createdAt = '2025-01-01T00:00:00.000Z'; }, 'NATIVE_LOG_TIME_INVALID'],
]) test(name, () => { const x = fixture(); mutate(x); assert.throws(() => parseBoundNativeLog(bytes(x), state), { message: code }); });
test('unknown item content and mismatched native item id fail closed', () => {
  const x = fixture();
  x.splice(1, 0, { ...x[0], id: 'item', method: 'item/started', itemId: 'i', payload: { item: { id: 'i', type: 'unknownNewType' } } });
  assert.throws(() => parseBoundNativeLog(bytes(x), state), /NATIVE_LOG_ITEM_TYPE_UNKNOWN/u);
  x[1].payload.item = { id: 'different', type: 'commandExecution' };
  assert.throws(() => parseBoundNativeLog(bytes(x), state), /NATIVE_LOG_ITEM_IDENTITY_MISMATCH/u);
});
test('auxiliary gateway telemetry is preserved without using it as lifecycle proof', () => {
  const x = fixture(); x.splice(1, 0, { ...x[0], id: 'usage', method: 'turn.gateway-usage.updated', lifecycleGeneration: null });
  const parsed = parseBoundNativeLog(bytes(x), state);
  assert.equal(parsed.native_line_count, 3); assert.equal(parsed.rows.length, 2);
  assert.equal(parsed.lifecycle_generation, 'life');
});
test('unknown original log prefix is not silently reinterpreted', () => {
  assert.throws(() => parseBoundNativeLog(Buffer.from(bytes(fixture()).toString().replace('NTIVE:', 'CANON:')), state), /NATIVE_LOG_FORMAT_UNKNOWN/u);
});
test('bundle verifies immutable attempt, raw bytes, provenance, and state SHA', async () => {
  const root = await mkdtemp(join(tmpdir(), 'native-log-bundle-'));
  try {
    const stateBytes = Buffer.from(JSON.stringify(state)), raw = bytes(fixture());
    const provenance = Buffer.from(JSON.stringify({ selected_lines: 2, selected_bytes_sha256: sha256(raw),
      sources: [{ source_path: '/synthetic/events.log', captured_source_sha256: 'a'.repeat(64), captured_size: raw.length, selected_original_line_numbers: [5, 6] }] }));
    await writeFile(join(root, 'native.log'), raw); await writeFile(join(root, 'provenance.json'), provenance);
    const manifest = { schema_version: NATIVE_LOG_BUNDLE_SCHEMA, identity: state.identity, session: state.session,
      execution_state_sha256: sha256(stateBytes), native_log: { path: 'native.log', sha256: sha256(raw), size: raw.length },
      provenance: { path: 'provenance.json', sha256: sha256(provenance), size: provenance.length } };
    const path = join(root, 'manifest.json'); await writeFile(path, JSON.stringify(manifest));
    assert.equal((await readBoundNativeLogBundle(path, state, stateBytes)).native_line_count, 2);
    await assert.rejects(readBoundNativeLogBundle(path, state, Buffer.from('other')), /NATIVE_LOG_EXECUTION_STATE_SHA_MISMATCH/u);
    await writeFile(join(root, 'native.log'), Buffer.from('tamper'));
    await assert.rejects(readBoundNativeLogBundle(path, state, stateBytes), /NATIVE_LOG_ARTIFACT_SHA_MISMATCH/u);
    const index = { native_provider_log_profile: { id: 'bound-native-provider-log/v1', runtime_turn_projection_event_count: 0,
      comparison_rows_are_database_sequences: false }, canonical_source_policy: { id: 'bound-native-sdk-canonical/v1' },
      raw_event_range: { first_sequence: 1, last_sequence: 2, event_count: 2 }, raw_trace: [] };
    await assert.rejects(verifyArchivedNativeLog(index, state, stateBytes, root), /NATIVE_LOG_PROFILE_INVALID/u);
  } finally { await rm(root, { recursive: true, force: true }); }
});
