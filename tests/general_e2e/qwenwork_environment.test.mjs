import assert from 'node:assert/strict';
import { test } from 'node:test';
import { inspectMacGuiSession, assertMacGuiReady } from '../../tools/report/e2e-shared/desktop-gui/macos.mjs';
import { inspectLoopbackEndpoint, inspectQwenExecutionEnvironment, assertQwenExecutionEnvironment } from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/environment.mjs';
import { gui, environment } from './fixtures/qwenwork/environment.mjs';

const row = () => ({ IORegistryEntryName: 'Root', IOConsoleLocked: false,
  IOConsoleUsers: [{ kCGSSessionOnConsoleKey: true, kCGSessionLoginDoneKey: true, kCGSSessionUserIDKey: 501 }] });
const inspect = root => inspectMacGuiSession({ platform: 'darwin', effectiveUid: 501,
  readRegistry: async () => root, readConsoleUid: async () => 501 });
test('GUI gate requires one logged-in console session owned by this user and an explicit unlocked state', async () => {
  assertMacGuiReady(await inspect(row()));
  assertMacGuiReady(await inspect([row()]));
  for (const change of [r => r.IOConsoleLocked = true, r => delete r.IOConsoleLocked,
    r => r.IOConsoleLocked = 'No', r => r.IOConsoleUsers = [],
    r => r.IOConsoleUsers.push({ ...r.IOConsoleUsers[0] }),
    r => r.IOConsoleUsers[0].kCGSessionLoginDoneKey = false,
    r => r.IOConsoleUsers[0].kCGSSessionUserIDKey = 502]) {
    const root = row(); change(root);
    assert.throws(() => assertMacGuiReady(root), /GUI_LOCKED_OR_UNVERIFIED/);
    const observed = await inspect(root);
    assert.equal(observed.unlocked, false);
    assert.throws(() => assertMacGuiReady(observed), /GUI_LOCKED_OR_UNVERIFIED/);
  }
  const failed = await inspectMacGuiSession({ platform: 'darwin', readRegistry: async () => { throw Error('read error'); } });
  assert.equal(failed.error, 'GUI_INSPECTION_FAILED');
  assert.equal(failed.unlocked, false);
});

test('CDP requires an actual browser WebSocket on the exact loopback endpoint', async () => {
  for (const websocket of [null, 'ws://remote:9250/devtools/browser/id', 'ws://127.0.0.1:9251/devtools/browser/id',
    'ws://127.0.0.1:9250/devtools/page/id', 'http://127.0.0.1:9250/devtools/browser/id']) {
    const actual = await inspectLoopbackEndpoint('http://127.0.0.1:9250', { fetch: async () => ({ ok: true, status: 200,
      json: async () => ({ Browser: 'Chrome', webSocketDebuggerUrl: websocket }) }) });
    assert.equal(actual.ready, false);
  }
  const good = await inspectLoopbackEndpoint('http://127.0.0.1:9250', { fetch: async () => ({ ok: true, status: 200,
    json: async () => ({ Browser: 'Chrome', webSocketDebuggerUrl: 'ws://127.0.0.1:9250/devtools/browser/verified-id' }) }) });
  assert.equal(good.ready, true);
});

test('Locked or foreign-listener environments are rejected before reading CDP', async () => {
  let listenerCalls = 0, endpointCalls = 0;
  const config = { appPath: '/Applications/QwenWorkCN.app', endpoint: 'http://127.0.0.1:9250' };
  const hooks = { inspectGui: async () => ({ ...gui(), unlocked: false, screen_locked: true }),
    inspectListener: async () => { listenerCalls++; throw Error('QWEN_TOKEN_PROCESS_IDENTITY_MISMATCH'); },
    inspectEndpoint: async () => { endpointCalls++; return environment().cdp; } };
  const locked = await inspectQwenExecutionEnvironment(config, hooks);
  assert.equal(locked.verified, false); assert.equal(listenerCalls, 0); assert.equal(endpointCalls, 0);
  const foreign = await inspectQwenExecutionEnvironment(config, { ...hooks, inspectGui: async () => gui() });
  assert.equal(foreign.verified, false); assert.equal(listenerCalls, 1); assert.equal(endpointCalls, 0);
});

test('Live environment refuses process reuse, command drift and a different installation', () => {
  const frozen = environment(); assertQwenExecutionEnvironment(environment(), frozen);
  for (const mutate of [e => e.listener.pid++, e => e.listener.process_start_identity = 'new-start',
    e => e.listener.command_sha256 = 'b'.repeat(64), e => e.app_path = '/other/QwenWorkCN.app']) {
    const current = environment(); mutate(current);
    assert.throws(() => assertQwenExecutionEnvironment(current, frozen), /ENVIRONMENT_CHANGED/);
  }
});
