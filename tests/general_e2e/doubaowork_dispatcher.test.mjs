import assert from "node:assert/strict";
import test from "node:test";
import { operateDispatcherObserver, DISPATCHER_SOURCE_SHA256, MERGED_DISPATCHER_SOURCE_SHA256, dispatcherProfileForSource } from "../../tools/report/e2e-shared/doubaowork/runtime-dispatcher.mjs";
import { assertNativeToolActivityAllowed, taskToolDeliveries, normalizeNativeToolEvents } from "../../tools/report/e2e-shared/doubaowork/runtime-tools.mjs";
import { normalizeVerifiedNonSuccessToolSubset } from "../../tools/report/e2e-shared/doubaowork/bound-evidence.mjs";

function fixture(t, withConsumer = false, sourceSha = DISPATCHER_SOURCE_SHA256) {
  t.mock.timers.enable({ apis: ["Date", "setInterval"], now: Date.parse("2026-10-06T00:00:00Z") });
  t.after(() => { delete globalThis.__wcbDoubaoDispatcherObserver; });
  let delegated = 0;
  const value = {}, error = new Error("native failure");
  const manager = { destroyed: false, records: new Map(), pending: new Set(), current: new Map(), currentCallIds: new WeakMap(),
    reportAdmissionFailure() { return value; },
    dispatch(request) { delegated++; if (request.id === "throws") throw error; return value; } };
  const owner = { cwd: "/task", instanceId: "sandbox", sendContext: { conversationId: "123" } };
  const store = { contextsBySandboxId: new Map([["sandbox", owner]]) };
  const cfg = { workspace: "/task", attemptId: "attempt", profileSha: sourceSha };
  const listeners = new Set();
  const service = withConsumer ? { subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    getConnectionState() { return { state: "open" }; } } : null;
  const call = (operation, extra = {}) => operateDispatcherObserver.call(manager, store, { ...cfg, operation, ...extra }, service);
  const receive = (id = "call", input = { command: "pwd" }, agent = "agent") => {
    for (const fn of listeners) fn({ type: "TOOL_CALL", sandboxId: "sandbox", toolCall: { id, name: "Bash", input, option: { agent_id: agent } } });
  };
  const dispatch = (id = "call", input = { command: "pwd" }) => {
    receive(id, input);
    return manager.dispatch({ id, name: "Bash", input, sandboxId: "sandbox" }, null,
      { track: "agent", agentId: "agent", conversationId: "123", owner }, { cwd: owner.cwd, sandboxId: "sandbox", sendContext: owner.sendContext });
  };
  const options = { attemptId: "attempt", workspace: "/task", agentId: "agent", conversationId: "123", sentAt: new Date().toISOString() };
  return { manager, store, owner, cfg, call, dispatch, receive, service, listeners, value, error, options, delegated: () => delegated };
}

test('merged runtime source keeps exact consumer-witness binding and rejects a different source',t=>{
  const f=fixture(t,true,MERGED_DISPATCHER_SOURCE_SHA256);
  f.call('install');f.dispatch();
  f.manager.records.set('sandbox::call',{finalizedAt:Date.now(),uploadState:'uploaded',request:{id:'call',name:'Bash'},
    result:{text:'ok'},context:{owner:f.owner,agentId:'agent',conversationId:'123'}});
  const snapshot=f.call('collect',{agentId:'agent',restore:true}),options={...f.options,finishedAt:new Date().toISOString()};
  assert.equal(normalizeNativeToolEvents(snapshot,options).status,'complete-for-protocol');
  const wrong=structuredClone(snapshot);wrong.consumer_witness.source_sha256=DISPATCHER_SOURCE_SHA256;
  assert.throws(()=>normalizeNativeToolEvents(wrong,options),/CONSUMER_WITNESS/);
  assert.equal(dispatcherProfileForSource(MERGED_DISPATCHER_SOURCE_SHA256).module,985448);
  assert.throws(()=>dispatcherProfileForSource('unknown'),/SOURCE_UNVERIFIED/);
});

test("consumer witness reconciles inbound calls, actual dispatch and native uploaded results without changing dispatch", t => {
  const f = fixture(t, true), original = f.manager.dispatch;
  f.call("install");
  assert.equal(f.listeners.size, 1);
  f.receive(); // A native replay must not add a second logical call.
  assert.equal(f.dispatch(), f.value);
  assert.equal(f.delegated(), 1);
  f.manager.records.set("sandbox::call", { finalizedAt: Date.now(), uploadState: "uploaded", request: { id: "call", name: "Bash" },
    result: { text: "ok" }, context: { owner: f.owner, agentId: "agent", conversationId: "123" } });
  const snapshot = f.call("collect", { agentId: "agent", restore: true });
  const options = { ...f.options, finishedAt: new Date().toISOString() };
  const result = normalizeNativeToolEvents(snapshot, options);
  assert.equal(result.status, "complete-for-protocol");
  assert.equal(result.scope, "bound-native-local-tool-consumer-and-dispatch");
  assert.equal(snapshot.consumer_witness.received_calls.length, 1);
  assert.equal(f.listeners.size, 0);
  assert.equal(f.manager.dispatch, original);
  const legacy = structuredClone(snapshot); delete legacy.consumer_witness;
  assert.equal(normalizeNativeToolEvents(legacy, options).status, "partial");
  const interrupted = structuredClone(snapshot);
  interrupted.ledger.push({ ...interrupted.ledger[0], toolCallId: "failed", uploadState: "failed" });
  const subset = normalizeVerifiedNonSuccessToolSubset(interrupted, options, { nonSuccessVerified: true });
  assert.equal(subset.status, "partial");
  assert.equal(subset.dropped_failed_upload_count, 1);
  const overflow = structuredClone(snapshot); overflow.overflow = true;
  assert.equal(normalizeVerifiedNonSuccessToolSubset(overflow, options).status, "partial");
  const diagnostic = structuredClone(snapshot); diagnostic.errors = ["DISPATCH_CONSUMER_BINDING_UNVERIFIED"];
  const retained = normalizeVerifiedNonSuccessToolSubset(diagnostic, options);
  assert.equal(retained.status, "partial");
  assert.equal(retained.known_subtotal, 1);
  assert.equal(retained.capture_incomplete, true);
  assert.equal(diagnostic.consumer_witness.received_calls.length, 1);
  diagnostic.errors.push("other-error");
  assert.throws(() => normalizeVerifiedNonSuccessToolSubset(diagnostic, options), /CAPTURE_INCOMPLETE/);
  for (const change of [
    s => { s.consumer_witness.received_calls = []; },
    s => { s.consumer_witness.received_calls[0].input = { command: "other" }; },
    s => { s.consumer_witness.received_calls[0].native_agent_id = "other"; },
    s => { s.consumer_witness.received_calls[0].sandbox_id = "other"; },
    s => { s.consumer_witness.received_calls[0].observed_at = new Date(Date.now() + 1).toISOString(); },
    s => { s.consumer_witness.unbound_agent_event_count = 1; },
    s => { s.consumer_witness.source_sha256 = "a".repeat(64); },
  ]) {
    const invalid = structuredClone(snapshot); change(invalid);
    assert.throws(() => normalizeNativeToolEvents(invalid, options), /CONSUMER/);
  }
});

test("admission-only or unbound inbound calls cannot establish complete absence evidence", t => {
  const f = fixture(t, true); f.call("install"); f.receive();
  assert.throws(() => f.call("discard-unsent", { restore: true }), /UNSENT_HAS_EVENTS/);
  const snapshot = f.call("collect", { agentId: "agent", restore: true });
  assert.throws(() => normalizeNativeToolEvents(snapshot, { ...f.options, finishedAt: new Date().toISOString() }), /CONSUMER_COVERAGE/);
  f.call("install"); f.receive("unbound", {}, "other-agent");
  const unbound = f.call("collect", { agentId: "agent", restore: true });
  assert.equal(unbound.consumer_witness.unbound_agent_event_count, 1);
  assert.throws(() => normalizeNativeToolEvents(unbound, { ...f.options, finishedAt: new Date().toISOString() }), /CONSUMER_WITNESS/);
});

test("a missing Agent ID needs the actual native admission refusal and never becomes a dispatched call", t => {
  const f = fixture(t, true), original = f.manager.reportAdmissionFailure;
  f.call("install"); f.receive("rejected", { command: "pwd" }, null);
  const request = { sandboxId: "sandbox", id: "rejected", name: "Bash" };
  const refusal = { result: { isError: true, error_code: "missing_agent_id_on_agent_route", content: [{ type: "text", text: "native refusal" }] } };
  assert.equal(f.manager.reportAdmissionFailure(request, refusal), f.value);
  assert.equal(f.delegated(), 0);
  const snapshot = f.call("collect", { agentId: "agent", restore: true });
  assert.equal(f.manager.reportAdmissionFailure, original);
  const options = { ...f.options, finishedAt: new Date().toISOString() };
  const normalized = normalizeNativeToolEvents(snapshot, options);
  assert.equal(normalized.status, "complete-for-protocol");
  assert.equal(normalized.known_subtotal, 1);
  assert.equal(normalized.events[0].native_agent_id, null);
  assert.equal(normalized.events[1].admission_rejected, true);
  assert.deepEqual(normalized.events[1].output, refusal.result);
  for (const change of [s => { s.consumer_witness.admission_rejections = []; },
    s => { s.consumer_witness.admission_rejections[0].source = "inferred"; },
    s => { s.consumer_witness.admission_rejections[0].result.error_code = "guessed"; },
    s => { s.events[1].output = { ...s.events[1].output, error_code: "other" }; }]) {
    const invalid = structuredClone(snapshot); change(invalid);
    assert.throws(() => normalizeNativeToolEvents(invalid, options), /NATIVE_TOOL_/);
  }
});

test("consumer replacement, release and ambiguous native route fail closed", t => {
  const f = fixture(t, true); f.call("install");
  assert.throws(() => operateDispatcherObserver.call(f.manager, f.store,
    { ...f.cfg, operation: "collect", agentId: "agent" }, { ...f.service }), /RUNTIME_CHANGED/);
  f.store.contextsBySandboxId.clear(); f.receive();
  const unknown = f.call("collect", { agentId: "agent", restore: true });
  assert.equal(unknown.unknown_context_events, 1);
  assert.throws(() => normalizeNativeToolEvents(unknown, { ...f.options, finishedAt: new Date().toISOString() }), /CAPTURE_INCOMPLETE/);
  f.call("install"); f.service.getConnectionState = () => ({ state: "released" });
  const released = f.call("collect", { agentId: "agent", restore: true });
  assert.ok(released.errors.includes("DISPATCH_CONSUMER_RELEASED"));
});

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
