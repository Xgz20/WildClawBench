import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import { configureMoaBackend, isMoaBackend, validateMoaListener, validateMoaBackendProof, MOA_SOURCE_SHA256 } from '../../tools/report/e2e-shared/doubaowork/runtime-moa.mjs';
import { isSupportedDispatcherSource, DISPATCHER_SOURCE_SHA256, operateDispatcherObserver } from '../../tools/report/e2e-shared/doubaowork/runtime-dispatcher.mjs';
import { readNativeActivity, assertNativeActivityAllowed } from '../../tools/report/e2e-shared/doubaowork/runtime-activity.mjs';
import { normalizeNativeToolEvents } from '../../tools/report/e2e-shared/doubaowork/runtime-tools.mjs';
import { installNativeLifecycleObserver } from '../../tools/report/e2e-shared/doubaowork/runtime-lifecycle.mjs';

const appPath = '/Applications/DoubaoWork.app';
function identity() { return { pid: 101, parentPid: 100, address: '127.0.0.1:9261',
  command: appPath + '/Contents/Helpers/DoubaoWork Browser.app/Contents/Frameworks/DoubaoWork Browser Framework.framework/Versions/147.0/Helpers/DoubaoWork Browser Helper.app/Contents/MacOS/DoubaoWork Browser Helper --type=utility --utility-sub-type=jsrt.mojom.Service',
  target: { type: 'node', url: 'aha-runtime', title: 'aha-runtime [pid: 101]', webSocketDebuggerUrl: 'ws://127.0.0.1:9261/ws/abcdef-123456-abcdef' } }; }
test('MOA configuration is explicit, version-bound, and leaves legacy backends untouched', () => {
  const b = {}; assert.equal(configureMoaBackend(b, { app: { version: '2.31.10' }, uiEndpoint: 'http://127.0.0.1:9260' }), false);
  assert.equal(isMoaBackend(b), false);
  assert.throws(() => configureMoaBackend(b, { app: { version: '2.35.15' }, uiEndpoint: 'http://example.org:9260' }), /LOOPBACK_PORTS/);
  assert.equal(configureMoaBackend(b, { app: { version: '2.35.15' }, uiEndpoint: 'http://127.0.0.1:9260' }), true);
  assert.equal(isMoaBackend(b), true);
  assert.equal(isSupportedDispatcherSource(DISPATCHER_SOURCE_SHA256), true);
  assert.equal(isSupportedDispatcherSource(MOA_SOURCE_SHA256), true);
  assert.equal(isSupportedDispatcherSource('0'.repeat(64)), false);
});
test('MOA listener accepts only the exact loopback worker, its browser parent and inspector target', () => {
  assert.doesNotThrow(() => validateMoaListener(identity(), 100, appPath));
  for (const patch of [{ parentPid: 999 }, { address: '*:9261' }, { command: '/tmp/fake --type=utility --utility-sub-type=jsrt.mojom.Service' },
    { target: { ...identity().target, title: 'aha-runtime [pid: 999]' } },
    { target: { ...identity().target, webSocketDebuggerUrl: 'ws://external.example/ws/abcdef' } }]) {
    assert.throws(() => validateMoaListener({ ...identity(), ...patch }, 100, appPath), /MOA_/);
  }
});
function backendProof() {
  return { profile: 'doubaowork-moa-2.35.15-inspector/v1', worker_id: 'entry-moa', worker_source_sha256: MOA_SOURCE_SHA256,
    endpoint: 'http://127.0.0.1:9261', source_verification: 'live-debugger-script-sha256',
    script_url: 'https://resource.sandbox.invalid/local_webcontents/apps/entry-moa/main.js', worker_pid: 101, browser_pid: 100,
    worker_start_identity: 'Thu Nov 5 12:00:00 2026', browser_start_identity: 'Thu Nov 5 11:59:00 2026',
    worker_command_sha256: 'a'.repeat(64), browser_command_sha256: 'b'.repeat(64), inspector_target_id: 'abcdef-123456-abcdef-123456' };
}
test('New source SHA alone never admits an archived MOA capture', () => {
  const p = backendProof();
  assert.doesNotThrow(() => validateMoaBackendProof(p));
  for (const value of [null, { ...p, worker_source_sha256: '0'.repeat(64) }, { ...p, endpoint: 'http://external.example' },
    { ...p, worker_pid: 100 }, { ...p, worker_command_sha256: null }, { ...p, source_verification: 'assumed' }]) {
    assert.throws(() => validateMoaBackendProof(value), /BACKEND_PROOF_INVALID/);
  }
});

test('MOA uses the original consumer/dispatch/upload algorithm, with no invented tool events', () => {
  const workspace = '/private/fixture/moa', context = { cwd: workspace, instanceId: 'sandbox', sandboxId: 'sandbox', sendContext: { conversationId: '123' } };
  let nativeCalls = 0; const dispatcher = { destroyed: false, pending: new Set(), current: new Map(), currentCallIds: new WeakMap(),
    records: new Map(), dispatch() { nativeCalls++; return 'native-return'; }, reportAdmissionFailure() {} };
  const store = { contextsBySandboxId: new Map([['sandbox', context]]) }, listeners = new Set();
  const service = { subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }, getConnectionState: () => ({ state: 'connected' }) };
  const cfg = { operation: 'install', attemptId: 'moa-attempt', workspace, profileSha: MOA_SOURCE_SHA256 };
  const installed = operateDispatcherObserver.call(dispatcher, store, cfg, service);
  const request = { id: 'call', name: 'Bash', sandboxId: 'sandbox', input: { command: 'pwd' }, option: { agent_id: 'agent' } };
  for (const receive of listeners) receive({ type: 'TOOL_CALL', sandboxId: 'sandbox', toolCall: request });
  assert.equal(dispatcher.dispatch(request, null, { track: 'agent', agentId: 'agent', conversationId: '123', owner: context }, context), 'native-return');
  const finalizedAt = Date.now();
  dispatcher.records.set('sandbox::call', { request, result: { content: [{ type: 'text', text: 'ok' }], isError: false }, uploadState: 'uploaded',
    finalizedAt, context: { track: 'agent', agentId: 'agent', conversationId: '123', owner: context } });
  const snapshot = operateDispatcherObserver.call(dispatcher, store, { ...cfg, operation: 'collect', agentId: 'agent', restore: true }, service);
  snapshot.native_backend = backendProof();
  const binding = { attemptId: cfg.attemptId, workspace, agentId: 'agent', conversationId: '123', sentAt: installed.installed_at,
    finishedAt: new Date(finalizedAt + 1000).toISOString() };
  assert.equal(nativeCalls, 1); assert.equal(listeners.size, 0); assert.equal(snapshot.observer_restored, true);
  const result = normalizeNativeToolEvents(snapshot, binding);
  assert.equal(result.status, 'complete-for-protocol'); assert.equal(result.known_subtotal, 1);
  assert.equal(snapshot.events.length, 2); assert.equal(snapshot.ledger.length, 1);
  const missing = structuredClone(snapshot); delete missing.native_backend;
  assert.throws(() => normalizeNativeToolEvents(missing, binding), /BACKEND_PROOF_INVALID/);
  const wrong = structuredClone(snapshot); wrong.consumer_witness.source_sha256 = DISPATCHER_SOURCE_SHA256;
  assert.throws(() => normalizeNativeToolEvents(wrong, binding), /CONSUMER_WITNESS_INVALID/);
});

test('The actual injected lifecycle expression parses before touching a native runtime', async () => {
  let parsed = false;
  const session = { async send(method, args) {
    if (method === 'Runtime.evaluate') { new vm.Script(args.expression); parsed = true; return { exceptionDetails: { text: 'fixture-stop' }, result: {} }; }
    return {};
  }, async detach() {} };
  await assert.rejects(installNativeLifecycleObserver({ context: () => ({ newCDPSession: async () => session }) },
    { attemptId: 'fixture', workspace: '/workspace', prompt: 'fixture' }), /fixture-stop/);
  assert.equal(parsed, true);
});

async function activityFixture({ modern = false, collision = false, table = {}, bound = true, marker = true } = {}) {
  const previous = globalThis.window;
  const service = { getTaskService: () => ({ mainTaskService: { tasks: table }, checkpointService: {
    getMainTaskData: () => ({ sentMessages: { x: { extra: { conversation_id: '123' } } } }) } }) };
  const container = { serviceContainer: { isBound: () => bound, get: () => service } };
  const module = modern ? { AJ: () => container, zo: () => container } : { XQ: () => container, ne: () => container };
  const require = () => module;
  require.m = { [modern ? 'MBp' : 37476]: marker ? function() { return 'Resource controller of GLOBAL_STORE not found'; } : function() {} };
  const chunks = []; chunks.push = function(value) { Array.prototype.push.call(this, value); value[2](require); return this.length; };
  const key = modern ? 'chunk_@flow-web/desktop' : '@flow-web/desktop:stable'; globalThis.window = { [key]: chunks };
  if (collision) globalThis.window[modern ? '@flow-web/desktop:stable' : 'chunk_@flow-web/desktop'] = [];
  try { const value = await readNativeActivity({ evaluate: fn => fn() }); assert.equal(chunks.length, 0); return value; }
  finally { globalThis.window = previous; }
}
for (const modern of [false, true]) test('Native activity retains exact session/conversation binding: ' + (modern ? '2.35' : 'legacy'), async () => {
  const value = await activityFixture({ modern, table: { task: { sessionId: 'request' } } });
  assert.equal(value.initialized, true); assert.equal(value.active.length, 1);
  assert.doesNotThrow(() => assertNativeActivityAllowed(value, ['123'], ['request']));
  assert.throws(() => assertNativeActivityAllowed(value), /UNREGISTERED_NATIVE_ACTIVITY/);
});
test('Unknown namespaces, modules, missing initialization and changed task containers do not become idle', async () => {
  await assert.rejects(activityFixture({ modern: true, collision: true }), /PROFILE_UNAVAILABLE/);
  await assert.rejects(activityFixture({ modern: true, marker: false }), /PROFILE_UNSUPPORTED/);
  await assert.rejects(activityFixture({ modern: true, table: new Map() }), /TASK_STORE_UNSUPPORTED/);
  const missing = await activityFixture({ modern: true, bound: false });
  assert.throws(() => assertNativeActivityAllowed(missing), /ACTIVITY_UNVERIFIED/);
});
