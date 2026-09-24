import assert from "node:assert/strict";
import { test } from "node:test";
import { operateNativeObserver, assertNativeToolActivityAllowed, taskToolDeliveries } from "../../tools/report/e2e-shared/doubaowork/runtime-tools.mjs";

function fixture() {
  const context = { cwd: "/private/fixture/one", instanceId: "sandbox", sandboxId: "sandbox",
    legacyExecutionState: { scopeKey: "conversation:123" } };
  const delivery = { entry: { sandboxId: "sandbox", sandboxScopeKey: "conversation:123" }, toolCallId: "call" };
  const dispatcher = { current: new Map([[JSON.stringify(["agent", "conversation:123", "request"]), delivery]]),
    pending: new Set(["sandbox::call"]), hasActiveDelivery: id => id === "sandbox" };
  const manager = { resultLedger: { finalizedByKey: new Map() },
    executionContextRegistry: { contextsBySandboxId: new Map([["sandbox", context]]) },
    toolCallPipeline: { dispatcher }, setDebugStreaming() { throw Error("read must not install observer"); } };
  const read = () => operateNativeObserver.call({ get: () => ({ execution: { sseRuntime: { managerValue: manager } } }) },
    null, { operation: "activity", profileSha: "a".repeat(64) });
  const peer = { workspace: context.cwd, conversation_id: "123", native_request_session_id: "request" };
  const frontend = { initialized: true, active: [{ session_id: "request", conversation_ids: ["123"] }] };
  return { context, delivery, dispatcher, manager, read, peer, frontend };
}

test("Background activity is read without an observer and blocks an orphan after foreground completion", () => {
  const f = fixture(), activity = f.read();
  assert.equal(activity.active.length, 1);
  assert.equal(activity.pending_count, 1);
  assert.equal(activity.active[0].native_request_session_id, "request");
  assert.throws(() => assertNativeToolActivityAllowed(activity), /UNREGISTERED_TOOL_DELIVERY/);
  assert.throws(() => assertNativeToolActivityAllowed(activity, [f.peer], { initialized: true, active: [] }), /ORPHAN_TOOL_DELIVERY/);
  assert.equal(taskToolDeliveries(activity, { workspace: f.context.cwd, conversationId: "123" }).length, 1);
  assert.equal(f.dispatcher.current.size, 1);
  assert.equal(f.manager.options, undefined);
});

test("Only the registered peer with exact directory, request and active foreground identity is allowed", () => {
  const f = fixture(), activity = f.read();
  assert.doesNotThrow(() => assertNativeToolActivityAllowed(activity, [f.peer], f.frontend));
  for (const patch of [{ workspace: "/private/fixture/one-other" }, { conversation_id: "124" }, { native_request_session_id: "old" }]) {
    assert.throws(() => assertNativeToolActivityAllowed(activity, [{ ...f.peer, ...patch }], f.frontend), /UNREGISTERED_TOOL_DELIVERY/);
  }
  for (const task of [{ session_id: "old", conversation_ids: ["123"] }, { session_id: "request", conversation_ids: ["124"] }]) {
    assert.throws(() => assertNativeToolActivityAllowed(activity, [f.peer], { initialized: true, active: [task] }), /ORPHAN_TOOL_DELIVERY/);
  }
  assert.throws(() => assertNativeToolActivityAllowed(activity, [f.peer, f.peer], f.frontend), /UNREGISTERED_TOOL_DELIVERY/);
  assert.deepEqual(taskToolDeliveries(activity, { workspace: "/other", conversationId: "456" }), []);
  assert.equal(taskToolDeliveries(activity, { workspace: f.peer.workspace, conversationId: "456" }).length, 1);
});

test("A delivery remains visible when its context is gone or ambiguous", () => {
  for (const change of [f => f.manager.executionContextRegistry.contextsBySandboxId.clear(),
    f => f.manager.executionContextRegistry.contextsBySandboxId.set("duplicate", { ...f.context }),
    f => { f.context.sendContext = { conversationId: "456" }; }]) {
    const f = fixture(); change(f); const activity = f.read();
    assert.equal(activity.active.length, 1);
    assert.throws(() => assertNativeToolActivityAllowed(activity, [f.peer], f.frontend), /SCOPE_UNVERIFIED/);
    assert.equal(taskToolDeliveries(activity, { workspace: "/other", conversationId: "789" }).length, 1);
  }
});

test("Unsupported identities and unaccounted pending deliveries fail closed", () => {
  const f = fixture();
  f.dispatcher.pending.add("replaced::call");
  assert.throws(f.read, /PENDING_UNACCOUNTED/);
  f.dispatcher.current.clear();
  assert.throws(f.read, /PENDING_UNACCOUNTED/);
  f.dispatcher.pending.clear();
  assert.deepEqual(f.read().active, []);
  f.dispatcher.current.set("invalid", f.delivery);
  assert.throws(f.read, /IDENTITY_INVALID/);
  f.dispatcher.current = {};
  assert.throws(f.read, /UNSUPPORTED/);
});
