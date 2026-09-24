import { createHash, randomUUID } from "node:crypto";

const PROFILE = "doubaowork-native-checkpoint-lifecycle/v1";
const sha = value => createHash("sha256").update(value).digest("hex");

async function callObserver(page, config) {
  const cdp = await page.context().newCDPSession(page), group = `wcb-lifecycle-${randomUUID()}`;
  try {
    const object = await cdp.send("Runtime.evaluate", { objectGroup: group, expression: `(() => {
      let require; const chunks = window["@flow-web/desktop:stable"];
      if (!Array.isArray(chunks)) throw new Error("CHECKPOINT_LOADER_UNAVAILABLE");
      const item = [["wcb-lifecycle-" + crypto.randomUUID()], {}, r => { require = r; }];
      chunks.push(item); if (chunks.at(-1) === item) chunks.pop();
      const source = String(require.m[238525] || "");
      if (!source.includes("receiveTimestamp:o=Date.now()") || !source.includes("queryMessageId")
          || !source.includes("eventInstanceId") || !source.includes("perf_mark")) throw new Error("CHECKPOINT_CLOCK_PROFILE_UNSUPPORTED");
      const registry = require(37476);
      const services = [...new Set([registry.XQ(), registry.ne()].filter(c => c.serviceContainer.isBound("chatIMService"))
        .map(c => c.serviceContainer.get("chatIMService")))];
      const checkpoints = [...new Set(services.map(s => s.getTaskService().checkpointService))];
      const stores = [...new Set(checkpoints.map(s => s.store))];
      if (stores.length !== 1 || typeof stores[0].getState !== "function" || typeof stores[0].subscribe !== "function") throw new Error("CHECKPOINT_STORE_AMBIGUOUS");
      const owned = window.__wcbDoubaoLifecycleObserver?.releaseHooks?.find(h => h.checkpoint === checkpoints[0]
        && h.wrapper === checkpoints[0].removeMainTaskData && String(h.original).includes("removeMainTaskData"));
      if (checkpoints.length !== 1 || (!owned && !String(checkpoints[0].removeMainTaskData).includes("removeMainTaskData"))) throw new Error("CHECKPOINT_RELEASE_PROFILE_UNSUPPORTED");
      return { stores, checkpoints, source };
    })()` });
    if (object.exceptionDetails || !object.result.objectId) throw new Error("DOUBAOWORK_LIFECYCLE_PROFILE_UNAVAILABLE");
    const properties = await cdp.send("Runtime.getProperties", { objectId: object.result.objectId, ownProperties: true });
    const source = properties.result.find(p => p.name === "source")?.value?.value;
    if (typeof source !== "string") throw new Error("DOUBAOWORK_LIFECYCLE_SOURCE_UNAVAILABLE");
    const result = await cdp.send("Runtime.callFunctionOn", { objectId: object.result.objectId, objectGroup: group, returnByValue: true,
      arguments: [{ value: { ...config, profileSha: sha(source) } }], functionDeclaration: operateLifecycleObserver.toString() });
    if (result.exceptionDetails || !result.result.value) throw new Error(`DOUBAOWORK_LIFECYCLE_OBSERVER_FAILED: ${result.exceptionDetails?.exception?.description || config.operation}`);
    return result.result.value;
  } finally { await cdp.send("Runtime.releaseObjectGroup", { objectGroup: group }).catch(() => {}); await cdp.detach(); }
}

// Runs inside the native renderer. Observe store updates and copy a bound
// checkpoint before the SDK removes it; delegate the exact native call once.
// Never send/cancel a task or change native message content.
export function operateLifecycleObserver(cfg) {
  const key = "__wcbDoubaoLifecycleObserver", profile = "doubaowork-native-checkpoint-lifecycle/v1";
  let root = window[key];
  if (root && (root.profile_sha256 !== cfg.profileSha || root.stores.length !== this.stores.length
      || root.stores.some((s, i) => s !== this.stores[i]))) throw new Error("LIFECYCLE_STORE_CHANGED");
  const normalized = text => text.replace(/\r\n/g, "\n").replace(/\n+$/u, "");
  const matches = (value, observer) => {
    let prompt = false, workspace = false, count = 0;
    const stack = [[value, 0]];
    while (stack.length && ++count < 20000) {
      const [v, depth] = stack.pop(); if (depth > 20) continue;
      if (typeof v === "string") {
        prompt ||= normalized(v) === observer.prompt; workspace ||= v === observer.workspace;
        if (v.length < 4 * 1024 * 1024 && /^[\[{]/u.test(v)) try { stack.push([JSON.parse(v), depth + 1]); } catch {}
      } else if (v && typeof v === "object") for (const child of Object.values(v)) stack.push([child, depth + 1]);
    }
    return prompt && workspace;
  };
  if (cfg.operation === "install") {
    if (!root) {
      root = { profile_sha256: cfg.profileSha, stores: this.stores, observers: new Map(), subscriptions: [], releaseHooks: [], notifications: 0 };
      const receive = (state, previous) => {
        root.notifications += 1;
        for (const o of root.observers.values()) try {
          for (const [id, task] of Object.entries({ ...previous?.mainTaskDataMap, ...state.mainTaskDataMap })) {
            if (o.native_request_session_id && id !== o.native_request_session_id) {
              if (matches(task.sentMessages, o)) throw new Error("LIFECYCLE_REQUEST_AMBIGUOUS");
              continue;
            }
            if (!o.native_request_session_id && !matches(task.sentMessages, o)) continue;
            o.native_request_session_id = id;
            const sent = Object.values(task.sentMessages || {}).map(m => m.extra).filter(Boolean);
            const received = Object.values(task.receivedMessages || {}).map(m => m.extra).filter(Boolean);
            o.last_shape = { sent_keys: sent.map(m => Object.keys(m)), received_keys: received.map(m => Object.keys(m)), stage: task.stage };
            for (const m of received) for (const sample of m.local_info?.perf_mark_samples || []) {
              if (!sample.eventInstanceId || !Array.isArray(sample.marks)) continue;
              const query = sent.find(s => s.message_id === sample.queryMessageId);
              if (!query || sample.taskId !== id || sample.answerId !== m.message_id) throw new Error("LIFECYCLE_SAMPLE_SCOPE_MISMATCH");
              const row = { native_request_session_id: id, conversation_id: m.conversation_id,
                user_message_id: query.message_id, reply_message_id: m.message_id,
                sample: { querySendTimestamp: sample.querySendTimestamp, queryMessageId: sample.queryMessageId,
                  receiveTimestamp: sample.receiveTimestamp, taskId: sample.taskId, taskStage: sample.taskStage,
                  answerId: sample.answerId, eventInstanceId: sample.eventInstanceId,
                  marks: sample.marks.map(mark => ({ evName: mark.evName, evType: mark.evType, occurrenceIndex: mark.occurrenceIndex,
                    numeric_tags: Object.fromEntries(Object.entries(mark.tags || {}).filter(([k, v]) => k.length < 80
                      && !/secret|password|authorization|access.?token|fetch.?token/i.test(k)
                      && (typeof v === "number" && Number.isFinite(v) || typeof v === "string" && /^\d+(\.\d+)?$/u.test(v)))) })) } };
              const bytes = JSON.stringify(row), previous = o.samples.get(sample.eventInstanceId);
              if (previous && previous !== bytes) throw new Error("LIFECYCLE_SAMPLE_CONFLICT");
              if (o.samples.size >= 1024 && !previous) throw new Error("LIFECYCLE_SAMPLE_LIMIT");
              o.samples.set(sample.eventInstanceId, bytes);
            }
          }
        } catch (error) { if (!o.errors.includes(error.message)) o.errors.push(error.message); }
      };
      root.subscriptions = root.stores.map(store => store.subscribe(receive));
      if (root.subscriptions.some(fn => typeof fn !== "function")) throw new Error("LIFECYCLE_SUBSCRIPTION_UNSUPPORTED");
      for (const checkpoint of this.checkpoints || []) {
        const descriptor = Object.getOwnPropertyDescriptor(checkpoint, "removeMainTaskData");
        const original = checkpoint.removeMainTaskData;
        const wrapper = function (...args) {
          try { receive(this.store.getState()); } catch (error) { for (const o of root.observers.values()) o.errors.push(error.message); }
          return Reflect.apply(original, this, args);
        };
        checkpoint.removeMainTaskData = wrapper;
        root.releaseHooks.push({ checkpoint, descriptor, original, wrapper });
      }
      root.receive = receive; window[key] = root;
    }
    if (root.observers.has(cfg.attemptId) || [...root.observers.values()].some(o => o.workspace === cfg.workspace)) throw new Error("LIFECYCLE_OBSERVER_ALREADY_EXISTS");
    const o = { attempt_id: cfg.attemptId, workspace: cfg.workspace, prompt: normalized(cfg.prompt), installed_at: new Date().toISOString(),
      native_request_session_id: null, samples: new Map(), errors: [], last_shape: null };
    root.observers.set(cfg.attemptId, o);
    return { installed: true, installed_at: o.installed_at, profile, profile_sha256: cfg.profileSha };
  }
  if (!root || !root.observers.has(cfg.attemptId)) return { status: "unavailable", reason: "observer-not-installed" };
  const o = root.observers.get(cfg.attemptId);
  if (o.workspace !== cfg.workspace) throw new Error("LIFECYCLE_WORKSPACE_DRIFT");
  if (cfg.operation === "bind") {
    if (!cfg.nativeRequestId || o.native_request_session_id && o.native_request_session_id !== cfg.nativeRequestId) throw new Error("LIFECYCLE_REQUEST_BINDING_DRIFT");
    o.native_request_session_id = cfg.nativeRequestId; o.bound_at = new Date().toISOString();
    for (const store of root.stores) root.receive(store.getState());
    return { bound: true, native_request_session_id: o.native_request_session_id, bound_at: o.bound_at };
  }
  if (cfg.operation !== "collect") throw new Error("LIFECYCLE_OPERATION_INVALID");
  const snapshot = { schema: "wildclawbench.doubaowork-native-lifecycle/v1", profile, profile_sha256: root.profile_sha256,
    attempt_id: o.attempt_id, workspace: o.workspace, installed_at: o.installed_at, collected_at: new Date().toISOString(),
    native_request_session_id: o.native_request_session_id, samples: [...o.samples.values()].map(s => JSON.parse(s)),
    errors: [...o.errors], diagnostics: o.last_shape, bound_at: o.bound_at ?? null,
    store_update_notifications: root.notifications, clock_source: "native SDK 238525 perf mark receiveTimestamp=Date.now()" };
  if (cfg.restore) {
    root.observers.delete(cfg.attemptId);
    if (!root.observers.size) {
      for (const hook of root.releaseHooks) {
        if (hook.checkpoint.removeMainTaskData !== hook.wrapper) throw new Error("LIFECYCLE_RELEASE_HOOK_REPLACED");
        if (hook.descriptor) Object.defineProperty(hook.checkpoint, "removeMainTaskData", hook.descriptor);
        else delete hook.checkpoint.removeMainTaskData;
      }
      for (const unsubscribe of root.subscriptions) unsubscribe(); delete window[key];
    }
    snapshot.observer_restored = true;
  }
  return snapshot;
}

export const installNativeLifecycleObserver = (page, config) => callObserver(page, { ...config, operation: "install" });
export const bindNativeLifecycleObserver = (page, config) => callObserver(page, { ...config, operation: "bind" });
export const collectNativeLifecycleObserver = (page, config) => callObserver(page, { ...config, operation: "collect" });

export function normalizeNativeLifecycle(snapshot, { attemptId, workspace, native, sentAt, profileSha }) {
  if (snapshot?.schema !== "wildclawbench.doubaowork-native-lifecycle/v1" || snapshot.profile !== PROFILE
      || snapshot.attempt_id !== attemptId || snapshot.workspace !== workspace || snapshot.profile_sha256 !== profileSha
      || ![snapshot.installed_at, snapshot.collected_at, sentAt].every(t => Number.isFinite(Date.parse(t)))) throw new Error("DOUBAOWORK_LIFECYCLE_IDENTITY_OR_CAPTURE_INVALID");
  if (snapshot.errors.length) return { status: "unavailable", reason: "native-lifecycle-capture-errors", errors: snapshot.errors };
  const samples = snapshot.samples.filter(row => row.sample?.marks?.some(m => m.evName === "task_finish"));
  if (!samples.length) return { status: "unavailable", reason: "native-finish-event-not-captured" };
  if (snapshot.native_request_session_id !== native.native_request_session_id) throw new Error("DOUBAOWORK_LIFECYCLE_IDENTITY_OR_CAPTURE_INVALID");
  for (const row of samples) {
    const s = row.sample;
    if (row.conversation_id !== native.conversation_id || row.user_message_id !== native.user_message_id
        || row.reply_message_id !== native.reply_message_id || s.taskId !== native.native_request_session_id
        || s.queryMessageId !== native.user_message_id || s.answerId !== native.reply_message_id
        || !s.marks.some(m => m.evName === "task_finish") || !Number.isFinite(s.receiveTimestamp)
        || !Number.isFinite(s.querySendTimestamp) || s.receiveTimestamp < s.querySendTimestamp
        || s.receiveTimestamp < Date.parse(sentAt) || Date.parse(snapshot.installed_at) > Date.parse(sentAt)
        || s.receiveTimestamp > Date.parse(snapshot.collected_at)) throw new Error("DOUBAOWORK_LIFECYCLE_BINDING_INVALID");
  }
  const finishes = new Set(samples.map(row => row.sample.receiveTimestamp));
  if (finishes.size !== 1) throw new Error("DOUBAOWORK_LIFECYCLE_FINISH_CONFLICT");
  const [finished] = finishes;
  return { status: "observed", finished_at: new Date(finished).toISOString(), duration_seconds: (finished - Date.parse(sentAt)) / 1000,
    source: "native-checkpoint.receivedMessages.extra.local_info.perf_mark_samples.task_finish.receiveTimestamp" };
}
