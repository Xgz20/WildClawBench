import { createHash, randomUUID } from "node:crypto";

export const DISPATCHER_PROFILE = "doubaowork-tool-dispatch-observer/v1";
export const DISPATCHER_SOURCE_SHA256 = "40941282dd34f9ff7b5a0c5b399913f97c5b92a03eca90072c8f1b279c004baa";

// Read the initialized 2.31.10 dispatcher and context store. Never call the
// cleanup/initializer, a tool, a permission API, or a result upload function.
export async function dispatcherCall(browser, operation, value) {
  const pages = browser.contexts().flatMap(c => c.pages()).filter(p => {
    try { const u = new URL(p.url()); return ["chrome:", "doubaowork:"].includes(u.protocol) && u.hostname === "doubaowork-background"; }
    catch { return false; }
  });
  if (pages.length !== 1) throw new Error("DOUBAOWORK_BACKGROUND_TARGET_AMBIGUOUS");
  const cdp = await pages[0].context().newCDPSession(pages[0]), group = `wcb-dispatch-${randomUUID()}`;
  async function properties(objectId) { return (await cdp.send("Runtime.getProperties", { objectId, ownProperties: true })).result; }
  async function closureVariables(objectId, description) {
    const props = await cdp.send("Runtime.getProperties", { objectId });
    const scopes = props.internalProperties?.find(p => p.name === "[[Scopes]]")?.value?.objectId;
    if (!scopes) throw new Error("DOUBAOWORK_DISPATCH_SCOPES_UNAVAILABLE");
    const matches = (await properties(scopes)).filter(p => p.value?.description === description);
    if (matches.length !== 1) throw new Error("DOUBAOWORK_DISPATCH_CLOSURE_AMBIGUOUS");
    return properties(matches[0].value.objectId);
  }
  try {
    const root = await cdp.send("Runtime.evaluate", { objectGroup: group, expression: `(() => {
      const chunks = window["@flow-web/desktop:stable"];
      if (!Array.isArray(chunks)) throw new Error("DISPATCH_LOADER_UNAVAILABLE");
      let require; const item = [["wcb-dispatch-" + crypto.randomUUID()], {}, r => { require = r; }];
      chunks.push(item); if (chunks.at(-1) === item) chunks.pop();
      const source = String(require?.m?.[168088] || "");
      if (!source.includes("ToolCall consumer is already started") || !source.includes("local-file-local-tools-sse-wiring.ts")) throw new Error("DISPATCH_PROFILE_UNSUPPORTED");
      return { entry: require(168088).default, source };
    })()` });
    if (root.exceptionDetails || !root.result?.objectId) throw new Error("DOUBAOWORK_DISPATCH_PROFILE_UNAVAILABLE");
    const props = await properties(root.result.objectId);
    const source = props.find(p => p.name === "source")?.value?.value;
    const entry = props.find(p => p.name === "entry")?.value;
    if (typeof source !== "string" || createHash("sha256").update(source).digest("hex") !== DISPATCHER_SOURCE_SHA256
      || entry?.type !== "function") throw new Error("DOUBAOWORK_DISPATCH_SOURCE_UNVERIFIED");
    const variables = await closureVariables(entry.objectId, "Closure (168088)");
    const cleanup = variables.find(p => p.name === "f")?.value, holder = variables.find(p => p.name === "bb")?.value;
    if (cleanup?.type !== "function" || !holder?.objectId) throw new Error("DOUBAOWORK_DISPATCH_NOT_INITIALIZED");
    const cleanupVariables = await closureVariables(cleanup.objectId, "Closure (wI)");
    const dispatcher = cleanupVariables.find(p => p.name === "e")?.value;
    const store = await cdp.send("Runtime.callFunctionOn", { objectId: holder.objectId, objectGroup: group,
      functionDeclaration: "function(){ return this.current?.store; }", returnByValue: false });
    if (!dispatcher?.objectId || store.exceptionDetails || !store.result?.objectId) throw new Error("DOUBAOWORK_DISPATCH_NOT_INITIALIZED");
    const result = await cdp.send("Runtime.callFunctionOn", { objectId: dispatcher.objectId, objectGroup: group, returnByValue: true,
      arguments: [{ objectId: store.result.objectId }, { value: { ...value, operation, profileSha: DISPATCHER_SOURCE_SHA256 } }],
      functionDeclaration: operateDispatcherObserver.toString() });
    if (result.exceptionDetails || !result.result?.value) throw new Error(`DOUBAOWORK_DISPATCH_OBSERVER_FAILED: ${result.exceptionDetails?.exception?.description || operation}`);
    return result.result.value;
  } finally { await cdp.send("Runtime.releaseObjectGroup", { objectGroup: group }).catch(() => {}); await cdp.detach(); }
}

// Serialized into the renderer: all dependencies must be local. Wrap dispatch
// only to copy its actual invocation; delegate once and preserve its return.
// Results are copied after native upload, while still within the native TTL.
export function operateDispatcherObserver(store, cfg) {
  const profile = "doubaowork-tool-dispatch-observer/v1", key = "__wcbDoubaoDispatcherObserver";
  if (this.destroyed !== false || !(this.records instanceof Map) || !(this.pending instanceof Set)
    || !(this.current instanceof Map) || !(this.currentCallIds instanceof WeakMap)
    || !(store?.contextsBySandboxId instanceof Map) || typeof this.dispatch !== "function") throw new Error("DISPATCH_RUNTIME_UNSUPPORTED");
  const dispatcher = this;
  const activity = () => {
    if (dispatcher.pending.size > 1000 || dispatcher.current.size > 1000 || dispatcher.records.size > 1000) throw new Error("DISPATCH_ACTIVITY_LIMIT");
    const active = [], accounted = new Set();
    for (const id of dispatcher.pending) {
      const split = typeof id === "string" ? id.lastIndexOf("::") : -1;
      if (split < 1) throw new Error("DISPATCH_PENDING_ID_INVALID");
      const sandboxId = id.slice(0, split), callId = id.slice(split + 2), context = store.contextsBySandboxId.get(sandboxId);
      const matches = [...dispatcher.current].filter(([, aborter]) => dispatcher.currentCallIds.get(aborter) === callId);
      let identity = null;
      if (matches.length === 1) { try { identity = JSON.parse(matches[0][0]); } catch {} accounted.add(matches[0][0]); }
      const conversation = context?.sendContext?.conversationId;
      const verified = Array.isArray(identity) && identity.length === 3 && identity[0] === "agent"
        && typeof conversation === "string" && identity[1] === `conversation:${conversation}`
        && typeof context?.cwd === "string" && context.cwd.startsWith("/") && typeof identity[2] === "string" && Boolean(identity[2]);
      active.push({ sandbox_id: sandboxId, instance_id: context?.instanceId || sandboxId, tool_call_id: callId,
        native_request_session_id: identity?.[0] === "agent" ? identity[2] : null, native_cwd: context?.cwd ?? null,
        conversation_ids: conversation ? [conversation] : [], context_verified: Boolean(verified) });
    }
    // Uploads from admission failure need not have entered dispatch/pending.
    for (const [id, r] of dispatcher.records) if (r.uploadState === "uploading" && !dispatcher.pending.has(id)) {
      const context = r.context?.owner;
      active.push({ sandbox_id: r.request?.sandboxId ?? null, instance_id: context?.instanceId ?? null,
        tool_call_id: r.request?.id ?? null, native_request_session_id: r.context?.agentId ?? null,
        native_cwd: context?.cwd ?? null, conversation_ids: r.context?.conversationId ? [r.context.conversationId] : [],
        context_verified: Boolean(context?.cwd && r.context?.agentId && r.context?.conversationId === context?.sendContext?.conversationId) });
    }
    if (accounted.size !== dispatcher.current.size) throw new Error("DISPATCH_CURRENT_NOT_ACCOUNTED");
    return { schema: "wildclawbench.doubaowork-native-tool-activity/v1", initialized: true, profile, profile_sha256: cfg.profileSha,
      source: "ToolCallManager.pending+current+records.uploadState", observed_at: new Date().toISOString(),
      pending_count: dispatcher.pending.size, active };
  };
  if (cfg.operation === "activity") return activity();
  let root = globalThis[key];
  if (root && (root.manager !== dispatcher || root.store !== store || root.profileSha !== cfg.profileSha)) throw new Error("DISPATCH_OBSERVER_RUNTIME_CHANGED");
  const clone = value => value === undefined ? null : JSON.parse(JSON.stringify(value, (k, v) =>
    /^(signature|authorization|authorization_id|access_token|fetch_token|runtimeSecrets|signedEnvelope)$/i.test(k) ? "[REDACTED_SECRET]" : v));
  const noteError = (o, error) => { const message = String(error.message || error); if (!o.errors.includes(message) && o.errors.length < 100) o.errors.push(message); };
  if (cfg.operation === "install") {
    if (!cfg.attemptId || typeof cfg.workspace !== "string" || !cfg.workspace.startsWith("/")) throw new Error("DISPATCH_OBSERVER_INPUT_INVALID");
    if (!root) {
      root = { manager: dispatcher, store, profileSha: cfg.profileSha, observers: new Map(), original: dispatcher.dispatch,
        descriptor: Object.getOwnPropertyDescriptor(dispatcher, "dispatch") };
      root.capture = () => {
        for (const o of root.observers.values()) try {
          if (dispatcher.dispatch !== root.wrapper) throw new Error("DISPATCH_OBSERVER_REPLACED");
          if (dispatcher.records.size >= 1000) o.ledger_at_capacity = true;
          for (const [id, r] of dispatcher.records) {
            const start = o.calls.get(id); if (!start || r.uploadState !== "uploaded") continue;
            const now = Date.now();
            if (!Number.isFinite(r.finalizedAt) || r.finalizedAt < Date.parse(start.observed_at)
              || r.finalizedAt > now || now - r.finalizedAt > 1800000) throw new Error("DISPATCH_LEDGER_CLOCK_INVALID");
            if (r.context?.agentId !== start.native_agent_id || r.context?.conversationId !== start.conversation_id
              || r.context?.owner?.cwd !== o.workspace || r.request?.id !== start.tool_call_id || r.request?.name !== start.tool_name) throw new Error("DISPATCH_RESULT_BINDING_MISMATCH");
            const row = { toolCallId: r.request.id, toolName: r.request.name, instanceId: start.instance_id,
              sseIdentity: { agentId: r.context.agentId }, uploadState: "uploaded", cachedAtMs: r.finalizedAt, result: clone(r.result) };
            const previous = o.ledger.get(id);
            if (previous) { if (JSON.stringify(previous.row) !== JSON.stringify(row)) throw new Error("DISPATCH_LEDGER_CONFLICT"); continue; }
            const event = { ...start, phase: "settled", observed_at: new Date(r.finalizedAt).toISOString(),
              input: undefined, output: row.result, status: r.result?.isError ? "error" : "success" };
            const bytes = new TextEncoder().encode(JSON.stringify(row)).byteLength * 2;
            if (o.bytes + bytes > 32 * 1024 * 1024) { o.overflow = true; continue; }
            o.bytes += bytes; o.ledger.set(id, { observed_at_ms: now, row }); o.events.push(event);
          }
        } catch (error) { noteError(o, error); }
      };
      root.wrapper = function (...args) {
        const [request, , context, data] = args;
        // This instrumentation cannot interfere with native dispatch success or failure.
        for (const o of root.observers.values()) try {
          if (data?.cwd !== o.workspace && context?.owner?.cwd !== o.workspace) continue;
          const id = `${request?.sandboxId}::${request?.id}`;
          if (dispatcher.pending.has(id) || dispatcher.records.has(id)) continue;
          if (!request?.id || !request.name || context?.track !== "agent" || !context.agentId
            || !context.conversationId || context.owner?.cwd !== o.workspace || data?.cwd !== o.workspace
            || context.conversationId !== data?.sendContext?.conversationId) throw new Error("DISPATCH_CALL_BINDING_UNVERIFIED");
          if (o.calls.has(id)) throw new Error("DISPATCH_DUPLICATE_CALL");
          const event = { phase: "started", tool_call_id: request.id, tool_name: request.name, input: clone(request.input),
            instance_id: data.sandboxId, sandbox_id: request.sandboxId, native_cwd: data.cwd, native_agent_id: context.agentId,
            conversation_id: context.conversationId, local_message_id: data.sendContext?.localMessageId ?? null, observed_at: new Date().toISOString() };
          const bytes = new TextEncoder().encode(JSON.stringify(event)).byteLength;
          if (o.calls.size >= 5000 || o.bytes + bytes > 32 * 1024 * 1024) { o.overflow = true; continue; }
          o.bytes += bytes; o.calls.set(id, event); o.events.push(event);
        } catch (error) { noteError(o, error); }
        return Reflect.apply(root.original, this, args);
      };
      dispatcher.dispatch = root.wrapper; globalThis[key] = root;
      root.timer = setInterval(root.capture, 1000); root.timer.unref?.();
    }
    if (root.observers.has(cfg.attemptId) || [...root.observers.values()].some(o => o.workspace === cfg.workspace)) throw new Error("DISPATCH_OBSERVER_ALREADY_EXISTS");
    const o = { attempt_id: cfg.attemptId, workspace: cfg.workspace, installed_at: new Date().toISOString(),
      calls: new Map(), ledger: new Map(), events: [], errors: [], bytes: 0, overflow: false, ledger_at_capacity: false };
    root.observers.set(cfg.attemptId, o);
    return { installed: true, installed_at: o.installed_at, attempt_id: cfg.attemptId, profile, profile_sha256: cfg.profileSha };
  }
  if (!root?.observers.has(cfg.attemptId)) throw new Error("DISPATCH_OBSERVER_MISSING");
  const o = root.observers.get(cfg.attemptId);
  if (cfg.workspace !== o.workspace || dispatcher.dispatch !== root.wrapper) throw new Error("DISPATCH_OBSERVER_BINDING_CHANGED");
  if (cfg.operation !== "collect" && cfg.operation !== "discard-unsent") throw new Error("DISPATCH_OPERATION_INVALID");
  if (cfg.operation === "discard-unsent" && o.events.length) throw new Error("DISPATCH_UNSENT_HAS_EVENTS");
  root.capture();
  const current = activity();
  if (current.active.some(r => r.context_verified !== true || r.native_cwd === o.workspace)) throw new Error("DISPATCH_TASK_STILL_ACTIVE");
  const samples = [...o.ledger.values()].filter(s => s.row.sseIdentity.agentId === cfg.agentId).map(clone);
  const result = { schema: "wildclawbench.doubaowork-native-tool-events/v1", profile, profile_sha256: cfg.profileSha,
    attempt_id: o.attempt_id, workspace: o.workspace, native_agent_id: cfg.agentId ?? null,
    installed_at: o.installed_at, collected_at: new Date().toISOString(),
    events: o.events.filter(e => e.native_agent_id === cfg.agentId).map(clone), ledger: samples.map(s => s.row), ledger_samples: samples,
    contexts: [], overflow: o.overflow, errors: [...o.errors], unknown_context_events: 0, ledger_at_capacity: o.ledger_at_capacity,
    ledger_retention_ms: 1800000, ledger_capacity: 1000, ledger_observation_policy: "uploaded-ledger-observed-within-native-ttl/v1",
    status: "captured-not-normalized" };
  if (cfg.restore) {
    root.observers.delete(cfg.attemptId);
    if (!root.observers.size) {
      clearInterval(root.timer);
      if (root.descriptor) Object.defineProperty(dispatcher, "dispatch", root.descriptor); else delete dispatcher.dispatch;
      delete globalThis[key];
    }
    result.observer_restored = true;
  }
  return result;
}
