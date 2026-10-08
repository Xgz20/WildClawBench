import assert from "node:assert/strict";
import test from "node:test";
import { operateDispatcherObserver, DISPATCHER_SOURCE_SHA256 } from "../../tools/report/e2e-shared/doubaowork/runtime-dispatcher.mjs";
import { assertNativeToolActivityAllowed, taskToolDeliveries, normalizeNativeToolEvents } from "../../tools/report/e2e-shared/doubaowork/runtime-tools.mjs";

function fixture(t) {
  t.mock.timers.enable({ apis: ["Date", "setInterval"], now: Date.parse("2026-10-06T00:00:00Z") });
  t.after(() => { delete globalThis.__wcbDoubaoDispatcherObserver; });
  let delegated = 0;
  const value = {}, error = new Error("native failure");
  const manager = { destroyed: false, records: new Map(), pending: new Set(), current: new Map(), currentCallIds: new WeakMap(),
    dispatch(request) { delegated++; if (request.id === "throws") throw error; return value; } };
  const owner = { cwd: "/task", instanceId: "sandbox", sendContext: { conversationId: "123" } };
  const store = { contextsBySandboxId: new Map([["sandbox", owner]]) };
  const cfg = { workspace: "/task", attemptId: "attempt", profileSha: DISPATCHER_SOURCE_SHA256 };
  const call = (operation, extra = {}) => operateDispatcherObserver.call(manager, store, { ...cfg, operation, ...extra });
  const dispatch = (id = "call", input = { command: "pwd" }) => manager.dispatch({ id, name: "Bash", input, sandboxId: "sandbox" }, null,
    { track: "agent", agentId: "agent", conversationId: "123", owner }, { cwd: owner.cwd, sandboxId: "sandbox", sendContext: owner.sendContext });
  const options = { attemptId: "attempt", workspace: "/task", agentId: "agent", conversationId: "123", sentAt: new Date().toISOString() };
  return { manager, store, owner, cfg, call, dispatch, value, error, options, delegated: () => delegated };
}

test("pending read or shell delivery is visible before any file is created; own delivery blocks completion", t => {
  const f = fixture(t), aborter = {};
  f.manager.pending.add("sandbox::read"); f.manager.current.set(JSON.stringify(["agent", "conversation:123", "agent"]), aborter);
  f.manager.currentCallIds.set(aborter, "read");
  const activity = f.call("activity");
  assert.equal(activity.active.length, 1); assert.equal(activity.active[0].native_cwd, "/task");
  assert.throws(() => assertNativeToolActivityAllowed(activity), /UNREGISTERED_TOOL/);
  const peer = { conversation_id: "123", native_request_session_id: "agent", workspace: "/task" };
  assert.doesNotThrow(() => assertNativeToolActivityAllowed(activity, [peer], { initialized: true, active: [{ session_id: "agent", conversation_ids: ["123"] }] }));
  assert.equal(taskToolDeliveries(activity, { workspace: "/task", conversationId: "123" }).length, 1);
  f.store.contextsBySandboxId.clear();
  const unknown = f.call("activity");
  assert.equal(unknown.active.length, 1); assert.equal(unknown.active[0].context_verified, false);
  assert.equal(taskToolDeliveries(unknown, { workspace: "/other", conversationId: "456" }).length, 1);
  assert.throws(() => assertNativeToolActivityAllowed(unknown, [peer]), /SCOPE_UNVERIFIED/);
});

test("orphan current entry and admission uploads cannot be silently treated as idle", t => {
  const f = fixture(t);
  f.manager.current.set('["agent","conversation:123","agent"]', {});
  assert.throws(() => f.call("activity"), /CURRENT_NOT_ACCOUNTED/);
  f.manager.current.clear();
  f.manager.records.set("sandbox::call", { uploadState: "uploading", request: { id: "call", sandboxId: "sandbox" },
    context: { owner: f.owner, agentId: "agent", conversationId: "123" } });
  assert.equal(f.call("activity").active.length, 1);
  f.manager.records.get("sandbox::call").uploadState = "uploaded";
  assert.deepEqual(f.call("activity").active, []);
  f.manager.destroyed = true;
  assert.throws(() => f.call("activity"), /RUNTIME_UNSUPPORTED/);
});

test("instrumentation delegates once, preserves return/throw, records distinct real timestamps and restores", t => {
  const f = fixture(t), original = f.manager.dispatch;
  f.call("install");
  assert.equal(f.dispatch(), f.value); assert.equal(f.delegated(), 1);
  t.mock.timers.tick(2000);
  f.manager.records.set("sandbox::call", { finalizedAt: Date.now(), uploadState: "uploaded", request: { id: "call", name: "Bash" },
    result: { text: "ok", access_token: "secret" }, context: { owner: f.owner, agentId: "agent", conversationId: "123" } });
  t.mock.timers.tick(1000);
  const snapshot = f.call("collect", { agentId: "agent", restore: true });
  assert.equal(snapshot.events.length, 2);
  assert.equal(Date.parse(snapshot.events[1].observed_at) - Date.parse(snapshot.events[0].observed_at), 2000);
  assert.equal(snapshot.events[1].output.access_token, "[REDACTED_SECRET]");
  assert.equal(f.manager.dispatch, original); assert.equal(globalThis.__wcbDoubaoDispatcherObserver, undefined);
  assert.equal(normalizeNativeToolEvents(snapshot, { ...f.options, finishedAt: new Date().toISOString() }).known_subtotal, 1);
  const invalid = structuredClone(snapshot); invalid.profile_sha256 = "a".repeat(64);
  assert.throws(() => normalizeNativeToolEvents(invalid, { ...f.options, finishedAt: new Date().toISOString() }), /IDENTITY_MISMATCH/);
  f.call("install");
  assert.throws(() => f.dispatch("throws"), e => e === f.error);
  assert.equal(f.delegated(), 2);
  const failed = f.call("collect", { agentId: "agent", restore: true });
  assert.throws(() => normalizeNativeToolEvents(failed, { ...f.options, sentAt: failed.installed_at, finishedAt: new Date().toISOString() }), /EVENT_SCOPE_INVALID/);
});

test("late results first seen after TTL and unobserved history never become complete records", t => {
  const f = fixture(t);
  f.call("install"); f.dispatch();
  const finalizedAt = Date.now();
  t.mock.timers.tick(1800001);
  f.manager.records.set("sandbox::call", { finalizedAt, uploadState: "uploaded", request: { id: "call", name: "Bash" },
    result: {}, context: { owner: f.owner, agentId: "agent", conversationId: "123" } });
  const snapshot = f.call("collect", { agentId: "agent", restore: true });
  assert.ok(snapshot.errors.includes("DISPATCH_LEDGER_CLOCK_INVALID"));
  assert.throws(() => normalizeNativeToolEvents(snapshot, { ...f.options, finishedAt: new Date().toISOString() }), /CAPTURE_INCOMPLETE/);
});

test("previously witnessed results survive TTL while changed retained results remain conflicting", t => {
  const f = fixture(t);
  f.call("install"); f.dispatch();
  f.manager.records.set("sandbox::call", { finalizedAt: Date.now(), uploadState: "uploaded", request: { id: "call", name: "Bash" },
    result: { text: "ok" }, context: { owner: f.owner, agentId: "agent", conversationId: "123" } });
  t.mock.timers.tick(1000);
  const first = f.call("collect", { agentId: "agent" });
  t.mock.timers.tick(1800001);
  const later = f.call("collect", { agentId: "agent" });
  assert.deepEqual(later.errors, []);
  assert.equal(later.ledger_samples[0].observed_at_ms, first.ledger_samples[0].observed_at_ms);
  assert.equal(normalizeNativeToolEvents(later, { ...f.options, finishedAt: new Date().toISOString() }).known_subtotal, 1);
  f.manager.records.get("sandbox::call").result.text = "changed";
  const conflict = f.call("collect", { agentId: "agent", restore: true });
  assert.ok(conflict.errors.includes("DISPATCH_LEDGER_CONFLICT"));
});
