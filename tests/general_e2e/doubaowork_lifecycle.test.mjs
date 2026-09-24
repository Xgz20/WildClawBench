import assert from "node:assert/strict";
import { test } from "node:test";
import { operateLifecycleObserver, normalizeNativeLifecycle } from "../../tools/report/e2e-shared/doubaowork/runtime-lifecycle.mjs";
import { inspectNativeResourceObservations } from "../../tools/report/e2e-shared/doubaowork/resource-observations.mjs";

test("Passive native lifecycle subscription retains the original finish event after the task is removed", () => {
  const previous = globalThis.window; globalThis.window = {};
  const listeners = new Set(), store = { subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); } };
  const host = { stores: [store] }, cfg = { attemptId: "a", workspace: "/task/workspace", prompt: "prompt\n", profileSha: "a".repeat(64) };
  try {
    const installed = operateLifecycleObserver.call(host, { ...cfg, operation: "install" });
    const now = Date.now(), sample = { querySendTimestamp: now, receiveTimestamp: now,
      queryMessageId: "user", answerId: "reply", taskId: "request", eventInstanceId: "request:async:1:1", marks: [{ evName: "task_finish" }] };
    const state = { mainTaskDataMap: { request: { sentMessages: { user: { extra: { message_id: "user", text: "prompt", config: { workspace: cfg.workspace } } } },
      receivedMessages: { reply: { extra: { message_id: "reply", conversation_id: "123", local_info: { perf_mark_samples: [sample] } } } } } } };
    for (const fn of listeners) { fn(state); fn(state); fn({ mainTaskDataMap: {} }); }
    const snapshot = operateLifecycleObserver.call(host, { ...cfg, operation: "collect", restore: true });
    assert.equal(snapshot.samples.length, 1); assert.equal(snapshot.observer_restored, true); assert.equal(listeners.size, 0);
    const options = { attemptId: "a", workspace: cfg.workspace, profileSha: cfg.profileSha, sentAt: installed.installed_at,
      native: { native_request_session_id: "request", conversation_id: "123", user_message_id: "user", reply_message_id: "reply" } };
    assert.equal(normalizeNativeLifecycle(snapshot, options).status, "observed");
    for (const mutate of [s => s.samples[0].conversation_id = "other", s => s.samples[0].sample.answerId = "other",
      s => s.profile_sha256 = "other", s => s.installed_at = "unknown", s => s.samples[0].sample.receiveTimestamp = now - 10000]) {
      const changed = structuredClone(snapshot); mutate(changed);
      assert.throws(() => normalizeNativeLifecycle(changed, options), /DOUBAOWORK_LIFECYCLE_/);
    }
    assert.equal(normalizeNativeLifecycle({ ...snapshot, samples: [] }, options).status, "unavailable");
  } finally { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; }
});

test("An observer ignores foreign workspaces and refuses ambiguous requests for its own prompt", () => {
  const previous = globalThis.window; globalThis.window = {};
  const listeners = new Set(), store = { subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); } };
  const host = { stores: [store] }, cfg = { attemptId: "a", workspace: "/task", prompt: "prompt", profileSha: "b".repeat(64) };
  const task = workspace => ({ sentMessages: { user: { extra: { message_id: "user", text: "prompt", workspace } } } });
  try {
    operateLifecycleObserver.call(host, { ...cfg, operation: "install" });
    for (const fn of listeners) fn({ mainTaskDataMap: { foreign: task("/elsewhere") } });
    assert.equal(operateLifecycleObserver.call(host, { ...cfg, operation: "collect" }).native_request_session_id, null);
    for (const fn of listeners) fn({ mainTaskDataMap: { one: task("/task"), two: task("/task") } });
    assert.deepEqual(operateLifecycleObserver.call(host, { ...cfg, operation: "collect", restore: true }).errors, ["LIFECYCLE_REQUEST_AMBIGUOUS"]);
  } finally { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; }
});

test("Context occupancy and subscription display never become token consumption or money", () => {
  const runtime = { maps: { messageMap: { reply: { message_id: "reply", conversation_id: "123", ext: {
    context_window_usage: '{"messages":1000,"system_prompt":100,"total_window_size":256000}',
    commerce_usage_data_v1: '{"summary":{"label":"消耗","value":"2.13"},"items":[{"label":"本轮消耗豆包订阅","value":"2.13"}]}',
  } } } } };
  const result = inspectNativeResourceObservations(runtime, { reply_message_id: "reply", conversation_id: "123" });
  assert.equal(result.context_window.usable_as_input_or_total_tokens, false);
  assert.equal(result.subscription.unit, null); assert.equal(result.subscription.display_value, "2.13");
  assert.equal(result.token_accounting.status, "unavailable"); assert.equal(result.model_requests.status, "unavailable");
  runtime.maps.messageMap.reply.ext.token_usage = '{"input_tokens":100}';
  const candidate = inspectNativeResourceObservations(runtime, { reply_message_id: "reply", conversation_id: "123" });
  assert.equal(candidate.token_accounting.status, "unavailable"); assert.equal(candidate.token_accounting.candidates.length, 1);
});

test("Final SDK data mutated in place is captured before native deletion and the native method is restored", () => {
  const previous = globalThis.window; globalThis.window = {};
  let state = { mainTaskDataMap: {} }, calls = 0;
  const store = { getState: () => state, subscribe: () => () => {} };
  const checkpoint = { store, removeMainTaskData(id) { calls++; delete state.mainTaskDataMap[id]; return "native-result"; } };
  const original = checkpoint.removeMainTaskData, host = { stores: [store], checkpoints: [checkpoint] };
  const cfg = { attemptId: "a", workspace: "/task", prompt: "prompt", profileSha: "c".repeat(64) };
  try {
    operateLifecycleObserver.call(host, { ...cfg, operation: "install" });
    state.mainTaskDataMap.request = { sentMessages: { u: { extra: { message_id: "u" } } }, receivedMessages: {} };
    operateLifecycleObserver.call(host, { ...cfg, operation: "bind", nativeRequestId: "request" });
    const now = Date.now();
    state.mainTaskDataMap.request.receivedMessages.r = { extra: { message_id: "r", conversation_id: "123", local_info: { perf_mark_samples: [{
      querySendTimestamp: now, receiveTimestamp: now, queryMessageId: "u", answerId: "r", taskId: "request",
      eventInstanceId: "finish", marks: [{ evName: "task_finish" }],
    }] } } };
    assert.equal(checkpoint.removeMainTaskData("request"), "native-result");
    assert.equal(calls, 1);
    const snapshot = operateLifecycleObserver.call(host, { ...cfg, operation: "collect", restore: true });
    assert.equal(snapshot.samples.length, 1); assert.equal(checkpoint.removeMainTaskData, original);
  } finally { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; }
});
