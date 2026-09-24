import assert from "node:assert/strict";
import { test } from "node:test";
import { operateNativeObserver, normalizeNativeToolEvents } from "../../tools/report/e2e-shared/doubaowork/runtime-tools.mjs";

function fixture() {
  const workspace = "/private/fixture/workspace", context = { cwd: workspace, instanceId: "instance", sandboxId: "sandbox",
    sendContext: { conversationId: "123" }, rememberedToolCallIds: new Set(["call"]), legacyExecutionState: { phase: "terminal" } };
  const manager = { options: {}, debugStreaming: false, setDebugStreaming(v) { this.debugStreaming = v; },
    getCurrentConnectionId: () => "connection", executionContextRegistry: { contextsBySandboxId: new Map([["sandbox", context]]) },
    resultLedger: { finalizedByKey: new Map() }, toolCallPipeline: { dispatcher: { hasActiveDelivery: () => false } } };
  return { workspace, manager, registry: { get: () => ({ execution: { sseRuntime: { managerValue: manager } } }) },
    cfg: { profileSha: "a".repeat(64), attemptId: "attempt", workspace }, context };
}

test("Native debug sink records exact input/result and restores the original native configuration", () => {
  const previous = globalThis.window; globalThis.window = {};
  const f = fixture();
  try {
    const installed = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "install" });
    const at = Date.now(), output = { status: "success", content: "ok", toolCallId: "call" };
    f.manager.options.onToolCallDebugEvent({ phase: "started", toolCallId: "call", toolName: "Bash", input: { command: "pwd" }, option: { agent_id: "agent" }, instanceId: "instance", sendContext: f.context.sendContext, ts: at });
    f.manager.options.onToolCallDebugEvent({ phase: "settled", toolCallId: "call", toolName: "Bash", output, status: "success", instanceId: "instance", sendContext: f.context.sendContext, ts: at });
    f.manager.resultLedger.finalizedByKey.set("instance::call", { toolCallId: "call", toolName: "Bash", instanceId: "instance", result: output,
      sseIdentity: { agentId: "agent" }, uploadState: "uploaded", cachedAtMs: at });
    const snapshot = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "collect", agentId: "agent", restore: true });
    const normalized = normalizeNativeToolEvents(snapshot, { attemptId: "attempt", workspace: f.workspace, agentId: "agent", conversationId: "123", sentAt: installed.installed_at, finishedAt: new Date(at).toISOString() });
    assert.equal(normalized.known_subtotal, 1);
    assert.deepEqual(normalized.events[0].input, { command: "pwd" });
    assert.equal(f.manager.debugStreaming, false);
    assert.equal(Object.hasOwn(f.manager.options, "onToolCallDebugEvent"), false);
    assert.equal(window.__wcbDoubaoNativeTools, undefined);
    for (const mutate of [s => s.events.pop(), s => s.events.reverse(), s => s.events.push(s.events[0]),
      s => s.events[0].native_cwd = "/other", s => s.ledger[0].result.content = "changed", s => s.overflow = true,
      s => s.ledger[0].uploadState = "uploading", s => s.events[0].observed_at = "invalid"]) {
      const copy = structuredClone(snapshot); mutate(copy);
      assert.throws(() => normalizeNativeToolEvents(copy, { attemptId: "attempt", workspace: f.workspace, agentId: "agent", sentAt: installed.installed_at, finishedAt: new Date(at).toISOString() }), /NATIVE_TOOL_/);
    }
  } finally { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; }
});

test("Scoped native observers isolate workspaces and reject an existing disabled debug owner", () => {
  const previous = globalThis.window; globalThis.window = {};
  const f = fixture();
  try {
    f.manager.options.onToolCallDebugEvent = () => {};
    assert.throws(() => operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "install" }), /OWNER_CONFLICT/);
    assert.equal(f.manager.debugStreaming, false);
    delete f.manager.options.onToolCallDebugEvent;
    operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "install" });
    operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "install", attemptId: "other", workspace: "/private/other" });
    f.manager.options.onToolCallDebugEvent({ phase: "started", toolCallId: "call", toolName: "Read", input: { file_path: "/fixture" }, instanceId: "instance", ts: Date.now() });
    const other = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "discard-unsent", attemptId: "other", workspace: "/private/other", restore: true });
    assert.equal(other.events.length, 0); assert.equal(f.manager.debugStreaming, true);
    const own = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "collect", restore: true });
    assert.equal(own.events.length, 1); assert.equal(f.manager.debugStreaming, false);
  } finally { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; }
});

test("Periodic uploaded-ledger observations survive native TTL eviction without refreshing timestamps", t => {
  const previous = globalThis.window; globalThis.window = {};
  t.after(() => { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; });
  const start = Date.parse("2026-09-24T00:00:00Z");
  t.mock.timers.enable({ apis: ["Date", "setInterval"], now: start });
  const f = fixture(), at = Date.now(), output = { status: "success", content: "ok" };
  const installed = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "install" });
  for (const phase of ["started", "settled"]) f.manager.options.onToolCallDebugEvent({ phase, toolCallId: "call", toolName: "Read",
    input: { file_path: "file" }, output, option: { agent_id: "agent" }, instanceId: "instance", sendContext: f.context.sendContext, ts: at });
  const nativeRow = { toolCallId: "call", toolName: "Read", instanceId: "instance", result: output,
    sseIdentity: { agentId: "agent" }, uploadState: "uploaded", cachedAtMs: at };
  f.manager.resultLedger.finalizedByKey.set("instance::call", nativeRow);
  // A different agent's record is never retained by this observer.
  f.manager.resultLedger.finalizedByKey.set("other::call", { ...nativeRow, instanceId: "other", sseIdentity: { agentId: "other" } });
  t.mock.timers.tick(1000);
  const timer = window.__wcbDoubaoNativeTools.ledgerTimer;
  f.manager.resultLedger.finalizedByKey.clear();
  t.mock.timers.tick(31 * 60 * 1000);
  const snapshot = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "collect", agentId: "agent", restore: true });
  const opts = { attemptId: "attempt", workspace: f.workspace, agentId: "agent", conversationId: "123",
    sentAt: installed.installed_at, finishedAt: new Date().toISOString() };
  assert.equal(normalizeNativeToolEvents(snapshot, opts).known_subtotal, 1);
  assert.equal(snapshot.ledger.length, 1);
  assert.equal(snapshot.ledger_samples[0].observed_at_ms, start + 1000);
  assert.equal(snapshot.ledger[0].cachedAtMs, start);
  assert.equal(nativeRow.cachedAtMs, start);
  assert.equal(window.__wcbDoubaoNativeTools, undefined);
  assert.ok(timer);
  for (const mutate of [s => s.ledger_samples = [], s => s.ledger_samples[0].observed_at_ms = start - 1,
    s => s.ledger_samples[0].observed_at_ms = Date.now() + 1,
    s => s.ledger_samples[0].observed_at_ms = start + 1800001,
    s => s.ledger_samples[0].row.result.content = "tampered", s => s.ledger_retention_ms *= 2,
    s => s.ledger_observation_policy = "unknown"]) {
    const copy = JSON.parse(JSON.stringify(snapshot)); mutate(copy);
    assert.throws(() => normalizeNativeToolEvents(copy, opts), /NATIVE_TOOL_LEDGER/);
  }
  const legacy = structuredClone(snapshot); delete legacy.ledger_observation_policy; delete legacy.ledger_samples;
  assert.throws(() => normalizeNativeToolEvents(legacy, opts), /NATIVE_TOOL_LEDGER_INVALID/);
});

test("A ledger row first seen after TTL expiry cannot be certified by rolling capture", t => {
  const previous = globalThis.window; globalThis.window = {};
  t.after(() => { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; });
  t.mock.timers.enable({ apis: ["Date", "setInterval"], now: Date.parse("2026-09-24T00:00:00Z") });
  const f = fixture(), at = Date.now(), output = { content: "ok" };
  const installed = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "install" });
  for (const phase of ["started", "settled"]) f.manager.options.onToolCallDebugEvent({ phase, toolCallId: "call", toolName: "Read",
    input: { file_path: "file" }, output, instanceId: "instance", ts: at });
  t.mock.timers.tick(1800001);
  f.manager.resultLedger.finalizedByKey.set("instance::call", { toolCallId: "call", toolName: "Read", instanceId: "instance",
    result: output, sseIdentity: { agentId: "agent" }, uploadState: "uploaded", cachedAtMs: at });
  const snapshot = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "collect", agentId: "agent", restore: true });
  assert.deepEqual(snapshot.errors, ["NATIVE_TOOL_LEDGER_NOT_OBSERVED_WITHIN_TTL"]);
  assert.equal(snapshot.ledger_samples.length, 0);
  assert.throws(() => normalizeNativeToolEvents(snapshot, { attemptId: "attempt", workspace: f.workspace, agentId: "agent",
    sentAt: installed.installed_at, finishedAt: new Date().toISOString() }), /CAPTURE_INCOMPLETE/);
});

test("Rolling capture retains conflicting uploaded results and restores the timer and native sink", t => {
  const previous = globalThis.window; globalThis.window = {};
  t.after(() => { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; });
  const callbacks = new Set(), cleared = [];
  t.mock.method(globalThis, "setInterval", callback => { callbacks.add(callback); return callback; });
  t.mock.method(globalThis, "clearInterval", callback => { callbacks.delete(callback); cleared.push(callback); });
  const f = fixture(), at = Date.now(), output = { content: "original" };
  let forwarded = 0; f.manager.options.onToolCallDebugEvent = () => { forwarded++; }; f.manager.debugStreaming = true;
  const original = f.manager.options.onToolCallDebugEvent;
  operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "install" });
  operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "install", attemptId: "other", workspace: "/other" });
  for (const phase of ["started", "settled"]) f.manager.options.onToolCallDebugEvent({ phase, toolCallId: "call", toolName: "Read",
    input: { file_path: "file" }, output, instanceId: "instance", ts: at });
  const row = { toolCallId: "call", toolName: "Read", instanceId: "instance", result: output,
    sseIdentity: { agentId: "agent" }, uploadState: "uploaded", cachedAtMs: at };
  f.manager.resultLedger.finalizedByKey.set("instance::call", row);
  for (const callback of callbacks) callback();
  row.result = { content: "changed" };
  const snapshot = operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "collect", agentId: "agent", restore: true });
  assert.deepEqual(snapshot.errors, ["NATIVE_TOOL_RETAINED_LEDGER_CONFLICT"]);
  assert.equal(snapshot.ledger_samples[0].row.result.content, "original");
  assert.equal(forwarded, 2); assert.equal(callbacks.size, 1); assert.equal(cleared.length, 0);
  operateNativeObserver.call(f.registry, null, { ...f.cfg, operation: "discard-unsent", attemptId: "other", workspace: "/other", restore: true });
  assert.equal(callbacks.size, 0); assert.equal(cleared.length, 1);
  assert.equal(f.manager.options.onToolCallDebugEvent, original); assert.equal(f.manager.debugStreaming, true);
});
