import { createHash, randomUUID } from "node:crypto";
import { isAbsolute } from "node:path";

const PROFILE = "doubaowork-local-tool-debug-sink/v1";

// Inspect only the already initialized background runtime. Loading a module or
// calling an initializer, exporter, injector, permission or tool API is forbidden.
async function backendCall(browser, operation, value) {
  const pages = browser.contexts().flatMap(c => c.pages()).filter(p => {
    try { const u = new URL(p.url()); return ["chrome:", "doubaowork:"].includes(u.protocol) && u.hostname === "doubaowork-background"; }
    catch { return false; }
  });
  if (pages.length !== 1) throw new Error("DOUBAOWORK_BACKGROUND_TARGET_AMBIGUOUS");
  const cdp = await pages[0].context().newCDPSession(pages[0]), group = `wcb-native-tools-${randomUUID()}`;
  try {
    const root = await cdp.send("Runtime.evaluate", { objectGroup: group, expression: `(() => {
      if (!document.body?.textContent?.includes("不可见的页面")) throw new Error("DOUBAOWORK_BACKGROUND_NOT_READY");
      const chunks = window["@flow-web/desktop:stable"];
      if (!Array.isArray(chunks)) throw new Error("DOUBAOWORK_BACKGROUND_LOADER_UNAVAILABLE");
      let require;
      const item = [["wcb-native-reader-" + crypto.randomUUID()], {}, r => { require = r; }];
      chunks.push(item); if (chunks.at(-1) === item) chunks.pop();
      const source = String(require?.m?.[955025] || "");
      if (!source.includes("local-file-local-tools-sse-wiring.ts") || !source.includes("resultLedger")) throw new Error("DOUBAOWORK_BACKGROUND_PROFILE_UNSUPPORTED");
      return { entry: require(955025).default, source };
    })()` });
    if (root.exceptionDetails || !root.result?.objectId) throw new Error("DOUBAOWORK_BACKGROUND_PROFILE_UNAVAILABLE");
    const rootProps = await cdp.send("Runtime.getProperties", { objectId: root.result.objectId, ownProperties: true });
    const entry = rootProps.result.find(p => p.name === "entry")?.value;
    const source = rootProps.result.find(p => p.name === "source")?.value?.value;
    if (entry?.type !== "function" || typeof source !== "string") throw new Error("DOUBAOWORK_BACKGROUND_ENTRY_UNAVAILABLE");
    const profileSha = createHash("sha256").update(source).digest("hex");
    const props = await cdp.send("Runtime.getProperties", { objectId: entry.objectId });
    const scope = props.internalProperties?.find(p => p.name === "[[Scopes]]")?.value;
    if (!scope?.objectId) throw new Error("DOUBAOWORK_BACKGROUND_SCOPES_UNAVAILABLE");
    const scopes = await cdp.send("Runtime.getProperties", { objectId: scope.objectId });
    const matches = [];
    for (const s of scopes.result.filter(p => p.value?.description?.startsWith("Closure"))) {
      const variables = await cdp.send("Runtime.getProperties", { objectId: s.value.objectId });
      const registry = variables.result.find(p => p.name === "G0")?.value, token = variables.result.find(p => p.name === "DN")?.value;
      if (registry?.objectId && token?.objectId) matches.push({ registry, token });
    }
    if (matches.length !== 1) throw new Error("DOUBAOWORK_BACKGROUND_RUNTIME_AMBIGUOUS");
    const { registry, token } = matches[0];
    const result = await cdp.send("Runtime.callFunctionOn", {
      objectId: registry.objectId, objectGroup: group, returnByValue: true, awaitPromise: true,
      arguments: [{ objectId: token.objectId }, { value: { ...value, operation, profileSha } }],
      functionDeclaration: operateNativeObserver.toString(),
    });
    if (result.exceptionDetails || !result.result?.value) throw new Error(`DOUBAOWORK_BACKGROUND_OPERATION_FAILED: ${result.exceptionDetails?.exception?.description || operation}`);
    return result.result.value;
  } finally {
    await cdp.send("Runtime.releaseObjectGroup", { objectGroup: group }).catch(() => {});
    await cdp.detach();
  }
}

// This function runs inside the target's background JS world. The debug callback
// observes native dispatch; it cannot dispatch, approve, retry or change tools.
export function operateNativeObserver(token, cfg) {
  const profile = "doubaowork-local-tool-debug-sink/v1", key = "__wcbDoubaoNativeTools";
  const ledgerPolicy = "uploaded-ledger-observed-within-native-ttl/v1";
  const runtime = this.get(token), manager = runtime?.execution?.sseRuntime?.managerValue;
  if (!manager || !(manager.resultLedger?.finalizedByKey instanceof Map)
      || !(manager.executionContextRegistry?.contextsBySandboxId instanceof Map)
      || typeof manager.setDebugStreaming !== "function") throw new Error("NATIVE_TOOL_RUNTIME_UNSUPPORTED");
  if (cfg.operation === "activity") {
    const dispatcher = manager.toolCallPipeline?.dispatcher;
    if (!(dispatcher?.current instanceof Map) || !(dispatcher.pending instanceof Set)
        || typeof dispatcher.hasActiveDelivery !== "function") throw new Error("NATIVE_TOOL_ACTIVITY_UNSUPPORTED");
    const contexts = [...new Set(manager.executionContextRegistry.contextsBySandboxId.values())];
    if (contexts.length > 1000 || dispatcher.current.size > 1000 || dispatcher.pending.size > 1000) throw new Error("NATIVE_TOOL_ACTIVITY_LIMIT");
    // Enumerate the dispatcher itself: a delivery can outlive its context and
    // foreground task. Never mistake a missing registry row for an idle runtime.
    const active = [...dispatcher.current].map(([key, delivery]) => {
      let identity;
      try { identity = JSON.parse(key); } catch { throw new Error("NATIVE_TOOL_ACTIVITY_IDENTITY_INVALID"); }
      if (!Array.isArray(identity) || identity.length !== 3 || identity.some(v => typeof v !== "string")) throw new Error("NATIVE_TOOL_ACTIVITY_IDENTITY_INVALID");
      const matches = contexts.filter(c => c.instanceId === delivery?.entry?.sandboxId);
      const c = matches.length === 1 ? matches[0] : null;
      const ids = [identity[1], c?.legacyExecutionState?.scopeKey, delivery?.entry?.sandboxScopeKey]
        .map(scope => /^conversation:([0-9]{1,64})$/u.exec(scope || "")?.[1]);
      ids.push(c?.sendContext?.conversationId, delivery?.entry?.sendContext?.conversationId);
      return { instance_id: delivery?.entry?.sandboxId ?? null, native_cwd: c?.cwd ?? null,
        sandbox_id: c?.sandboxId ?? null, native_request_session_id: identity[0] === "agent" ? identity[2] : null,
        tool_call_id: delivery?.toolCallId ?? null, context_verified: matches.length === 1,
        conversation_ids: [...new Set(ids.filter(id => typeof id === "string" && /^[1-9][0-9]{0,63}$/u.test(id)))] };
    });
    // Replaced or settling deliveries may remain in pending after leaving current.
    if (dispatcher.pending.size !== active.length) throw new Error("NATIVE_TOOL_ACTIVITY_PENDING_UNACCOUNTED");
    return { schema: "wildclawbench.doubaowork-native-tool-activity/v1", initialized: true, profile,
      profile_sha256: cfg.profileSha, source: "dispatcher.current+pending+executionContextRegistry",
      observed_at: new Date().toISOString(), pending_count: dispatcher.pending.size, active };
  }
  const contextFor = instanceId => {
    const candidates = [...new Set(manager.executionContextRegistry.contextsBySandboxId.values())].filter(c => c.instanceId === instanceId);
    if (candidates.length !== 1) return null;
    return candidates[0];
  };
  const clone = value => value === undefined ? null : JSON.parse(JSON.stringify(value, (k, v) =>
    ["signature", "authorization", "authorization_id", "access_token", "fetch_token"].includes(k.toLowerCase()) ? "[REDACTED_SECRET]" : v));
  let root = window[key];
  if (root && (root.manager !== manager || root.profileSha !== cfg.profileSha || root.profile !== profile
      || root.ledgerPolicy !== ledgerPolicy)) throw new Error("NATIVE_TOOL_OBSERVER_RUNTIME_CHANGED");
  if (cfg.operation === "install") {
    if (!root) {
      if (manager.options.onToolCallDebugEvent && !manager.debugStreaming) throw new Error("NATIVE_TOOL_DEBUG_SINK_OWNER_CONFLICT");
      root = { profile, profileSha: cfg.profileSha, ledgerPolicy, manager, originalSink: manager.options.onToolCallDebugEvent,
        originalDebug: manager.debugStreaming, hadSink: Object.hasOwn(manager.options, "onToolCallDebugEvent"), observers: new Map() };
      // Read uploaded records while the native 30-minute cache still holds them.
      // Never refresh native timestamps or retain records for unobserved calls.
      root.captureLedger = () => {
        const observedAt = Date.now();
        for (const o of root.observers.values()) {
          try {
            if (manager.options.onToolCallDebugEvent !== root.sink || !manager.debugStreaming) throw new Error("NATIVE_TOOL_OBSERVER_REPLACED_OR_DISABLED");
            if (manager.resultLedger.finalizedByKey.size >= 1000) o.ledger_at_capacity = true;
            for (const record of manager.resultLedger.finalizedByKey.values()) {
              const id = JSON.stringify([record.instanceId, record.toolCallId]);
              if (!o.observed_calls.has(id) || record.uploadState !== "uploaded") continue;
              const row = clone(record), previous = o.ledger_samples.get(id);
              const immutable = r => JSON.stringify({ ...r, cachedAtMs: null });
              if (previous) {
                if (immutable(previous.row) !== immutable(row)) throw new Error("NATIVE_TOOL_RETAINED_LEDGER_CONFLICT");
                continue;
              }
              if (!Number.isFinite(row.cachedAtMs) || row.cachedAtMs > observedAt
                  || observedAt - row.cachedAtMs > 1800000) throw new Error("NATIVE_TOOL_LEDGER_NOT_OBSERVED_WITHIN_TTL");
              const sample = { observed_at_ms: observedAt, row };
              const bytes = new TextEncoder().encode(JSON.stringify(sample)).byteLength;
              if (o.bytes + bytes > 32 * 1024 * 1024 || o.ledger_samples.size >= 5000) { o.overflow = true; continue; }
              o.bytes += bytes; o.ledger_samples.set(id, sample);
            }
          } catch (e) {
            const error = String(e.message || e);
            if (!o.errors.includes(error) && o.errors.length < 100) o.errors.push(error);
          }
        }
      };
      root.sink = event => {
        const originalResult = root.originalSink?.call(manager.options, event);
        // Observer failures must not enter the native tool execution path.
        try {
          const context = contextFor(event.instanceId);
          if (!context) { for (const o of root.observers.values()) o.unknown_context_events += 1; return originalResult; }
          for (const o of root.observers.values()) {
            if (context.cwd !== o.workspace) continue;
            try {
              const row = { phase: event.phase, tool_call_id: event.toolCallId, tool_name: event.toolName,
                input: clone(event.input), output: clone(event.output), status: event.status ?? null,
                native_agent_id: event.option?.agent_id ?? null, agent_type: event.option?.agent_type ?? null,
                instance_id: event.instanceId, sandbox_id: context.sandboxId, native_cwd: context.cwd,
                conversation_id: event.sendContext?.conversationId ?? null, local_message_id: event.sendContext?.localMessageId ?? null,
                observed_at: new Date(event.ts).toISOString(), connection_id: manager.getCurrentConnectionId() };
              const size = new TextEncoder().encode(JSON.stringify(row)).byteLength;
              if (o.bytes + size > 32 * 1024 * 1024 || o.events.length >= 10000) { o.overflow = true; continue; }
              o.bytes += size; o.events.push(row);
              o.observed_calls.add(JSON.stringify([row.instance_id, row.tool_call_id]));
            } catch (e) { o.errors.push(String(e.message || e)); }
          }
        } catch (e) { for (const o of root.observers.values()) o.errors.push(String(e.message || e)); }
        return originalResult;
      };
      manager.options.onToolCallDebugEvent = root.sink;
      manager.setDebugStreaming(true);
      window[key] = root;
      root.ledgerTimer = setInterval(root.captureLedger, 1000);
      root.ledgerTimer.unref?.();
    }
    if (root.observers.has(cfg.attemptId) || [...root.observers.values()].some(o => o.workspace === cfg.workspace)) throw new Error("NATIVE_TOOL_OBSERVER_ALREADY_EXISTS");
    const observer = { attempt_id: cfg.attemptId, workspace: cfg.workspace, installed_at: new Date().toISOString(),
      events: [], bytes: 0, errors: [], unknown_context_events: 0, overflow: false,
      observed_calls: new Set(), ledger_samples: new Map(), ledger_at_capacity: false };
    root.observers.set(cfg.attemptId, observer);
    return { installed: true, attempt_id: cfg.attemptId, installed_at: observer.installed_at, profile, profile_sha256: cfg.profileSha };
  }
  if (!root || !root.observers.has(cfg.attemptId)) return { status: "unavailable", reason: "native-observer-not-installed", attempt_id: cfg.attemptId };
  if (manager.options.onToolCallDebugEvent !== root.sink || !manager.debugStreaming) throw new Error("NATIVE_TOOL_OBSERVER_REPLACED_OR_DISABLED");
  const o = root.observers.get(cfg.attemptId);
  if (o.workspace !== cfg.workspace) throw new Error("NATIVE_TOOL_OBSERVER_WORKSPACE_DRIFT");
  if (cfg.operation === "discard-unsent") {
    if (o.events.length) throw new Error("NATIVE_TOOL_OBSERVER_HAS_EVENTS");
  } else if (cfg.operation !== "collect") throw new Error("NATIVE_TOOL_OBSERVER_OPERATION_INVALID");
  root.captureLedger();
  const ledgerSamples = [...o.ledger_samples.values()].filter(s => s.row.sseIdentity?.agentId === cfg.agentId).map(clone);
  const retained = new Map(ledgerSamples.map(s => [JSON.stringify([s.row.instanceId, s.row.toolCallId]), s.row]));
  for (const r of manager.resultLedger.finalizedByKey.values()) {
    if (cfg.agentId && r.sseIdentity?.agentId === cfg.agentId) {
      const id = JSON.stringify([r.instanceId, r.toolCallId]);
      if (!retained.has(id)) retained.set(id, clone(r));
    }
  }
  const ledger = [...retained.values()];
  const contexts = [...new Set(manager.executionContextRegistry.contextsBySandboxId.values())]
    .filter(c => c.cwd === o.workspace).map(c => ({ cwd: c.cwd, instance_id: c.instanceId, sandbox_id: c.sandboxId,
      send_context: clone(c.sendContext), remembered_tool_call_ids: [...c.rememberedToolCallIds],
      remembered_limit: 500, legacy_execution_state: clone(c.legacyExecutionState),
      active_delivery: manager.toolCallPipeline.dispatcher.hasActiveDelivery(c.instanceId) }));
  const snapshot = { schema: "wildclawbench.doubaowork-native-tool-events/v1", profile, profile_sha256: cfg.profileSha,
    attempt_id: o.attempt_id, workspace: o.workspace, native_agent_id: cfg.agentId ?? null,
    installed_at: o.installed_at, collected_at: new Date().toISOString(), events: o.events.map(clone), ledger,
    contexts, overflow: o.overflow, errors: [...o.errors], unknown_context_events: o.unknown_context_events,
    ledger_retention_ms: 1800000, ledger_capacity: 1000, ledger_at_capacity: o.ledger_at_capacity,
    ledger_observation_policy: ledgerPolicy, ledger_samples: ledgerSamples,
    redaction: { removed_provider_fields: ["signature", "authorization", "authorization_id", "access_token", "fetch_token"] },
    status: "captured-not-normalized" };
  if (cfg.restore) {
    root.observers.delete(cfg.attemptId);
    if (!root.observers.size) {
      clearInterval(root.ledgerTimer);
      if (root.hadSink) manager.options.onToolCallDebugEvent = root.originalSink;
      else delete manager.options.onToolCallDebugEvent;
      manager.setDebugStreaming(root.originalDebug);
      delete window[key];
    }
    snapshot.observer_restored = true;
  }
  return snapshot;
}

export async function installNativeToolObserver(browser, { attemptId, workspace }) {
  if (!isAbsolute(workspace) || !attemptId) throw new Error("NATIVE_TOOL_OBSERVER_INPUT_INVALID");
  return backendCall(browser, "install", { attemptId, workspace });
}
export const readNativeToolActivity = browser => backendCall(browser, "activity", {});

export function assertNativeToolActivityAllowed(activity, peers = [], frontend) {
  if (activity?.initialized !== true || !Array.isArray(activity.active)) throw new Error("DOUBAOWORK_TOOL_ACTIVITY_UNVERIFIED");
  for (const row of activity.active) {
    if (row.context_verified !== true || row.conversation_ids?.length !== 1 || !isAbsolute(row.native_cwd || "")
        || !row.native_request_session_id || !row.tool_call_id) throw new Error("DOUBAOWORK_TOOL_ACTIVITY_SCOPE_UNVERIFIED");
    const matches = peers.filter(peer => peer.conversation_id === row.conversation_ids[0] && peer.workspace === row.native_cwd
      && peer.native_request_session_id === row.native_request_session_id);
    if (matches.length !== 1) throw new Error("DOUBAOWORK_UNREGISTERED_TOOL_DELIVERY");
    const peer = matches[0];
    if (frontend?.initialized !== true || !frontend.active?.some(task =>
      task.session_id === peer.native_request_session_id && task.conversation_ids?.includes(peer.conversation_id))) throw new Error("DOUBAOWORK_ORPHAN_TOOL_DELIVERY");
  }
}

export function taskToolDeliveries(activity, { workspace, conversationId }) {
  if (activity?.initialized !== true || !Array.isArray(activity.active)) throw new Error("DOUBAOWORK_TOOL_ACTIVITY_UNVERIFIED");
  return activity.active.filter(row => row.native_cwd === workspace || row.conversation_ids?.includes(conversationId)
    || row.context_verified !== true || row.conversation_ids?.length !== 1 || !isAbsolute(row.native_cwd || "")
    || !row.native_request_session_id || !row.tool_call_id);
}
export async function collectNativeToolObserver(browser, { attemptId, workspace, agentId, restore = false, unsent = false }) {
  return backendCall(browser, unsent ? "discard-unsent" : "collect", { attemptId, workspace, agentId, restore });
}

export function normalizeNativeToolEvents(snapshot, { attemptId, workspace, agentId, conversationId, sentAt, finishedAt }) {
  if (snapshot?.schema !== "wildclawbench.doubaowork-native-tool-events/v1" || snapshot.profile !== PROFILE
      || snapshot.attempt_id !== attemptId || snapshot.workspace !== workspace || snapshot.native_agent_id !== agentId) throw new Error("NATIVE_TOOL_EVIDENCE_IDENTITY_MISMATCH");
  if (![snapshot.installed_at, snapshot.collected_at, sentAt, finishedAt].every(t => Number.isFinite(Date.parse(t)))
      || Date.parse(finishedAt) < Date.parse(sentAt)) throw new Error("NATIVE_TOOL_CAPTURE_TIME_INVALID");
  if (snapshot.overflow || snapshot.errors.length || snapshot.unknown_context_events || snapshot.ledger_at_capacity
      || Date.parse(snapshot.installed_at) > Date.parse(sentAt)
      || snapshot.contexts.some(c => c.active_delivery || c.remembered_tool_call_ids.length >= c.remembered_limit)) throw new Error("NATIVE_TOOL_CAPTURE_INCOMPLETE");
  const ledger = new Map();
  const sampleTimes = new Map();
  if (snapshot.ledger_observation_policy !== undefined) {
    if (snapshot.ledger_observation_policy !== "uploaded-ledger-observed-within-native-ttl/v1"
        || snapshot.ledger_retention_ms !== 1800000 || !Array.isArray(snapshot.ledger_samples)) throw new Error("NATIVE_TOOL_LEDGER_POLICY_INVALID");
    for (const sample of snapshot.ledger_samples) {
      const r = sample.row, at = sample.observed_at_ms;
      if (!r?.toolCallId || sampleTimes.has(r.toolCallId) || !Number.isFinite(at)
          || at < Date.parse(snapshot.installed_at) || at < Date.parse(sentAt) || at > Date.parse(snapshot.collected_at)
          || !Number.isFinite(r.cachedAtMs) || r.cachedAtMs > at || at - r.cachedAtMs > snapshot.ledger_retention_ms) throw new Error("NATIVE_TOOL_LEDGER_OBSERVATION_INVALID");
      sampleTimes.set(r.toolCallId, sample);
    }
  }
  for (const r of snapshot.ledger) {
    const sample = sampleTimes.get(r.toolCallId);
    const observedAt = snapshot.ledger_observation_policy ? sample?.observed_at_ms : Date.parse(snapshot.collected_at);
    if (r.sseIdentity?.agentId !== agentId || r.uploadState !== "uploaded" || !r.toolCallId || ledger.has(r.toolCallId)
        || !Number.isFinite(r.cachedAtMs) || !Number.isFinite(observedAt) || r.cachedAtMs > observedAt
        || observedAt - r.cachedAtMs > snapshot.ledger_retention_ms
        || (sample && JSON.stringify(sample.row) !== JSON.stringify(r))) throw new Error("NATIVE_TOOL_LEDGER_INVALID");
    ledger.set(r.toolCallId, r);
  }
  if (snapshot.ledger_observation_policy && sampleTimes.size !== ledger.size) throw new Error("NATIVE_TOOL_LEDGER_COVERAGE_INCOMPLETE");
  const starts = new Map(), results = new Map(), events = [];
  for (const [index, e] of snapshot.events.entries()) {
    if (e.native_cwd !== workspace || !e.tool_call_id || !e.tool_name || !ledger.has(e.tool_call_id)) throw new Error("NATIVE_TOOL_EVENT_SCOPE_INVALID");
    const row = ledger.get(e.tool_call_id);
    if (row.toolName !== e.tool_name || row.instanceId !== e.instance_id || (e.native_agent_id && e.native_agent_id !== agentId)
        || (conversationId && e.conversation_id && e.conversation_id !== conversationId)
        || !Number.isFinite(Date.parse(e.observed_at))
        || Date.parse(e.observed_at) < Date.parse(sentAt) || Date.parse(e.observed_at) > Date.parse(finishedAt)) throw new Error("NATIVE_TOOL_EVENT_BINDING_MISMATCH");
    const map = e.phase === "started" ? starts : e.phase === "settled" ? results : null;
    if (!map || map.has(e.tool_call_id) || (e.phase === "settled" && !starts.has(e.tool_call_id))) throw new Error("NATIVE_TOOL_EVENT_ORDER_OR_DUPLICATE");
    if (e.phase === "started" && e.input === null) throw new Error("NATIVE_TOOL_INPUT_MISSING");
    if (e.phase === "settled" && JSON.stringify(e.output) !== JSON.stringify(row.result)) throw new Error("NATIVE_TOOL_RESULT_LEDGER_MISMATCH");
    map.set(e.tool_call_id, index); events.push({ ...e, raw_event_index: index });
  }
  if (starts.size !== ledger.size || results.size !== ledger.size) throw new Error("NATIVE_TOOL_LEDGER_COVERAGE_INCOMPLETE");
  return { events, calls: [...starts.keys()].map(id => ({ call_id: id, start_index: starts.get(id), result_index: results.get(id) })),
    known_subtotal: ledger.size, scope: "bound-native-agent-local-tool-protocol", status: "complete-for-protocol" };
}
