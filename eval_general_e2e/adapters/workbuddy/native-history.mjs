import { createHash } from "node:crypto";
import { lstat, readFile, readdir, realpath, stat } from "node:fs/promises";
import { basename, dirname, join, relative, resolve } from "node:path";

export const WORKBUDDY_HISTORY_ADAPTER_ID = "workbuddy-native-history";
export const WORKBUDDY_HISTORY_ADAPTER_VERSION = "0.1.0";
export const WORKBUDDY_HISTORY_OBSERVATION_SCHEMA =
  "wildclawbench.workbuddy-native-history-observation/v1";
export const GENERAL_RESOURCE_SCHEMA =
  "urn:wildclawbench:schema:general-e2e:resource-metrics:v1";
export const GENERAL_TRANSCRIPT_EVENT_SCHEMA =
  "urn:wildclawbench:schema:general-e2e:transcript-event:v1";

const SUCCESS_STATES = new Set(["complete", "completed", "success", "succeeded", "done", "finished"]);
const FAILURE_STATES = new Set(["failed", "failure", "error", "errored", "cancelled", "canceled", "aborted", "interrupted"]);
const RUNNING_STATES = new Set(["created", "pending", "queued", "running", "working", "streaming", "processing", "active"]);

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assertObject(value, label) {
  if (!isObject(value)) throw new Error(`${label} 必须是 JSON 对象`);
  return value;
}

function assertString(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} 必须是非空字符串`);
  return value;
}

function numeric(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function stableSum(values) {
  return values.reduce((total, value) => total + value, 0);
}

function parseStoredJson(value, label) {
  if (isObject(value)) return value;
  if (typeof value !== "string") throw new Error(`${label} 不是 JSON 字符串`);
  try {
    return assertObject(JSON.parse(value), label);
  } catch (error) {
    if (String(error?.message || "").startsWith(`${label} `)) throw error;
    throw new Error(`${label} 不是有效 JSON：${error instanceof Error ? error.message : String(error)}`);
  }
}

async function readJson(path, label = path) {
  let value;
  try {
    value = JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    throw new Error(`${label} 读取失败：${error instanceof Error ? error.message : String(error)}`);
  }
  return assertObject(value, label);
}

async function isDirectory(path) {
  try {
    const info = await lstat(path);
    return info.isDirectory() && !info.isSymbolicLink();
  } catch {
    return false;
  }
}

async function childDirectories(path) {
  try {
    return (await readdir(path, { withFileTypes: true }))
      .filter((item) => item.isDirectory() && !item.isSymbolicLink())
      .map((item) => item.name)
      .sort();
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
}

export function workBuddyWorkspaceHistoryKey(workspace) {
  const absolute = resolve(assertString(workspace, "workspace"));
  // WorkBuddy 5.5.3 uses the MD5 of the absolute workspace path as its
  // history directory key. This is a native layout identifier, not a
  // security digest.
  return createHash("md5").update(absolute).digest("hex");
}

export function classifyWorkBuddyState(rawState) {
  const raw = String(rawState || "").trim();
  const normalized = raw.toLowerCase().replace(/[\s_-]+/gu, "");
  if (SUCCESS_STATES.has(normalized)) return { kind: "success", raw };
  if (FAILURE_STATES.has(normalized)) return { kind: "failure", raw };
  if (RUNNING_STATES.has(normalized)) return { kind: "running", raw };
  return { kind: raw ? "unknown" : "missing", raw };
}

export async function findWorkBuddyWorkspaceHistory({ dataRoot, workspace }) {
  const canonicalDataRoot = await realpath(resolve(assertString(dataRoot, "dataRoot")));
  const canonicalWorkspace = await realpath(resolve(assertString(workspace, "workspace")));
  const historyKey = workBuddyWorkspaceHistoryKey(canonicalWorkspace);
  const candidates = [];
  for (const accountDirectory of await childDirectories(canonicalDataRoot)) {
    const vscodeRoot = join(canonicalDataRoot, accountDirectory, "VSCode");
    const direct = join(vscodeRoot, "history", historyKey);
    if (await isDirectory(direct)) candidates.push(direct);
    for (const identityDirectory of await childDirectories(vscodeRoot)) {
      const nested = join(vscodeRoot, identityDirectory, "history", historyKey);
      if (await isDirectory(nested)) candidates.push(nested);
    }
  }
  const unique = [...new Set(await Promise.all(candidates.map((item) => realpath(item))))];
  if (unique.length !== 1) {
    throw new Error(`WORKBUDDY_HISTORY_AMBIGUOUS: expected=1 actual=${unique.length} key=${historyKey}`);
  }
  return {
    data_root: canonicalDataRoot,
    workspace: canonicalWorkspace,
    workspace_history_key: historyKey,
    history_directory: unique[0],
  };
}

function chooseExact(items, id, label) {
  const matches = items.filter((item) => isObject(item) && item.id === id);
  if (matches.length !== 1) throw new Error(`${label} 绑定不唯一：expected=1 actual=${matches.length}`);
  return matches[0];
}

function safeLogicalRef(kind, id = "") {
  if (kind === "workspace") return "raw/workbuddy-history/workspace-index.json";
  if (kind === "conversation") return "raw/workbuddy-history/conversation-index.json";
  return `raw/workbuddy-history/messages/${id}.json`;
}

export async function loadWorkBuddyConversation({
  dataRoot,
  workspace,
  conversationId,
  requestId,
}) {
  assertString(conversationId, "conversationId");
  assertString(requestId, "requestId");
  const located = await findWorkBuddyWorkspaceHistory({ dataRoot, workspace });
  const workspaceIndexPath = join(located.history_directory, "index.json");
  const workspaceIndex = await readJson(workspaceIndexPath, "WorkBuddy workspace index");
  const conversation = chooseExact(workspaceIndex.conversations || [], conversationId, "conversationId");
  const conversationDirectory = join(located.history_directory, conversationId);
  if (!(await isDirectory(conversationDirectory))) {
    throw new Error(`WorkBuddy conversation 目录不存在：${conversationId}`);
  }
  const conversationIndexPath = join(conversationDirectory, "index.json");
  const conversationIndex = await readJson(conversationIndexPath, "WorkBuddy conversation index");
  const request = chooseExact(conversationIndex.requests || [], requestId, "requestId");
  const indexedMessages = new Map();
  for (const item of conversationIndex.messages || []) {
    if (!isObject(item) || typeof item.id !== "string") throw new Error("WorkBuddy message index 含无效条目");
    if (indexedMessages.has(item.id)) throw new Error(`WorkBuddy message id 重复：${item.id}`);
    indexedMessages.set(item.id, item);
  }
  if (!Array.isArray(request.messages) || request.messages.length === 0) {
    throw new Error(`WorkBuddy request ${requestId} 没有消息引用`);
  }
  const seen = new Set();
  const messages = [];
  for (const messageId of request.messages) {
    assertString(messageId, "request.messages[]");
    if (seen.has(messageId)) throw new Error(`WorkBuddy request 消息引用重复：${messageId}`);
    seen.add(messageId);
    const metadata = indexedMessages.get(messageId);
    if (!metadata) throw new Error(`WorkBuddy request 引用了不存在的消息：${messageId}`);
    const messagePath = join(conversationDirectory, "messages", `${messageId}.json`);
    const envelope = await readJson(messagePath, `WorkBuddy message ${messageId}`);
    if (envelope.id !== messageId) throw new Error(`WorkBuddy message id 不匹配：${messageId}`);
    if (envelope.role !== metadata.role) throw new Error(`WorkBuddy message role 不匹配：${messageId}`);
    const message = parseStoredJson(envelope.message, `WorkBuddy message payload ${messageId}`);
    const extra = parseStoredJson(envelope.extra || {}, `WorkBuddy message extra ${messageId}`);
    if (message.role !== envelope.role) throw new Error(`WorkBuddy inner role 不匹配：${messageId}`);
    if (extra.requestId && extra.requestId !== requestId) {
      throw new Error(`WorkBuddy message requestId 不匹配：${messageId}`);
    }
    messages.push({
      id: messageId,
      metadata,
      envelope,
      message,
      extra,
      source_ref: safeLogicalRef("message", messageId),
    });
  }
  return {
    ...located,
    conversation_id: conversationId,
    request_id: requestId,
    conversation,
    request,
    messages,
    workspace_index: workspaceIndex,
    conversation_index: conversationIndex,
    source_refs: {
      workspace_index: safeLogicalRef("workspace"),
      conversation_index: safeLogicalRef("conversation"),
      messages: messages.map((item) => item.source_ref),
    },
  };
}

function metricObservation(rows, field, { unit, basis, status = "observed" }) {
  const values = rows.map((row) => numeric(row?.[field]));
  const known = values.filter((value) => value !== null);
  const total = rows.length;
  const knownSubtotal = stableSum(known);
  return {
    value: total > 0 && known.length === total ? knownSubtotal : null,
    status: total === 0 || known.length === 0
      ? "unavailable"
      : known.length === total ? status : "partial",
    basis,
    known_subtotal: knownSubtotal,
    coverage: { known: known.length, total, unit },
  };
}

function exactMetric(value, basis, unit = "conversation_request") {
  return {
    value,
    status: "observed",
    basis,
    known_subtotal: value,
    coverage: { known: 1, total: 1, unit },
  };
}

function unavailableMetric(basis, total = 1, unit = "conversation_request") {
  return {
    value: null,
    status: "unavailable",
    basis,
    known_subtotal: 0,
    coverage: { known: 0, total, unit },
  };
}

function toolStatus(result) {
  const rawStatus = String(result?.status || result?.result?.status || "").trim();
  if (result?.success === true || SUCCESS_STATES.has(rawStatus.toLowerCase())) return "success";
  if (result?.success === false || FAILURE_STATES.has(rawStatus.toLowerCase())) return "error";
  return "unknown";
}

function linkedUsageRows(messages) {
  const rows = [];
  for (const item of messages) {
    for (const content of item.message.content || []) {
      const usage = content?.result?.result?.usage;
      if (isObject(usage)) rows.push(usage);
    }
  }
  return rows;
}

function nativeToolOutcomes(messages) {
  const outcomes = [];
  for (const item of messages) {
    for (const content of item.message.content || []) {
      if (content?.type !== "tool-result") continue;
      outcomes.push({
        call_id: content.toolCallId || null,
        name: content.toolName || null,
        status: toolStatus(content.result),
        source_ref: item.source_ref,
        scope: "conversation",
      });
      for (const nested of content?.result?.result?.toolInfo || []) {
        outcomes.push({
          call_id: nested?.toolCallId || null,
          name: nested?.name || null,
          status: toolStatus({ status: nested?.executeStatus }),
          source_ref: item.source_ref,
          scope: "linked-child",
        });
      }
    }
  }
  return outcomes;
}

export function buildWorkBuddyResourceObservation(loaded, normalizedEvents = []) {
  const primaryRows = [loaded.request?.usage || {}];
  const linkedRows = linkedUsageRows(loaded.messages);
  const outcomes = nativeToolOutcomes(loaded.messages);
  const primaryToolCalls = normalizedEvents.filter((item) => item.type === "tool_call").length;
  const primary = {
    input_tokens: metricObservation(primaryRows, "inputTokens", {
      unit: "request", basis: "WorkBuddy conversation index request.usage.inputTokens",
    }),
    output_tokens: metricObservation(primaryRows, "outputTokens", {
      unit: "request", basis: "WorkBuddy conversation index request.usage.outputTokens",
    }),
    total_tokens: metricObservation(primaryRows, "totalTokens", {
      unit: "request", basis: "WorkBuddy conversation index request.usage.totalTokens",
    }),
    cache_read_input_tokens: unavailableMetric(
      "WorkBuddy conversation index request usage does not expose cache-read tokens",
    ),
    cache_creation_input_tokens: unavailableMetric(
      "WorkBuddy conversation index request usage does not expose cache-write tokens",
    ),
    reasoning_output_tokens: unavailableMetric(
      "WorkBuddy native history does not expose reasoning output tokens",
    ),
    request_count: exactMetric(1, "One exact WorkBuddy native request is bound"),
    request_attempt_count: unavailableMetric(
      "WorkBuddy native history does not expose transport-level request attempts or retries",
    ),
    call_count: exactMetric(primaryToolCalls, "Unique top-level tool-call content blocks in the bound request"),
    duration_seconds: unavailableMetric("WorkBuddy request index exposes startedAt but no request completion timestamp"),
    agent_duration_seconds: unavailableMetric("WorkBuddy native history exposes no verified agent-duration field"),
  };
  const linked = {
    input_tokens: metricObservation(linkedRows, "inputTokens", {
      unit: "linked_usage", basis: "Linked tool-result usage.inputTokens", status: "partial",
    }),
    output_tokens: metricObservation(linkedRows, "outputTokens", {
      unit: "linked_usage", basis: "Linked tool-result usage.outputTokens", status: "partial",
    }),
    total_tokens: metricObservation(linkedRows, "totalTokens", {
      unit: "linked_usage", basis: "Linked tool-result usage.totalTokens", status: "partial",
    }),
    cache_read_input_tokens: metricObservation(linkedRows, "cacheTokens", {
      unit: "linked_usage", basis: "Linked tool-result usage.cacheTokens", status: "partial",
    }),
    cache_creation_input_tokens: metricObservation(linkedRows, "cachedWriteTokens", {
      unit: "linked_usage", basis: "Linked tool-result usage.cachedWriteTokens", status: "partial",
    }),
    cache_miss_input_tokens: metricObservation(linkedRows, "cachedMissTokens", {
      unit: "linked_usage", basis: "Linked tool-result usage.cachedMissTokens", status: "partial",
    }),
    credit: metricObservation(linkedRows, "credit", {
      unit: "linked_usage", basis: "Linked tool-result usage.credit; settlement semantics are not yet verified", status: "unverified",
    }),
  };
  const cacheConsistency = linkedRows.map((row) => {
    const input = numeric(row.inputTokens);
    const hit = numeric(row.cacheTokens);
    const miss = numeric(row.cachedMissTokens);
    return input !== null && hit !== null && miss !== null ? input === hit + miss : null;
  });
  return {
    schema_version: WORKBUDDY_HISTORY_OBSERVATION_SCHEMA,
    adapter: { id: WORKBUDDY_HISTORY_ADAPTER_ID, version: WORKBUDDY_HISTORY_ADAPTER_VERSION },
    scope: "bound-conversation-request",
    primary_request: primary,
    linked_tool_usage: linked,
    cache_semantics: {
      formula: "inputTokens = cacheTokens + cachedMissTokens",
      checks: cacheConsistency,
      all_observed_checks_pass: cacheConsistency.length > 0
        && cacheConsistency.every((value) => value === true),
    },
    tool_outcomes: outcomes,
    exclusions: [
      "judge-usage",
      "control-usage",
      "unobserved-http-retries",
      "unlinked-child-agents",
      "linked-tool-usage-from-primary-resource-metrics",
    ],
  };
}

function source(adapterRef, redacted) {
  return { adapter: WORKBUDDY_HISTORY_ADAPTER_ID, raw_ref: adapterRef, redacted };
}

export function normalizeWorkBuddyConversation(loaded, { identity, redacted = false } = {}) {
  assertObject(identity, "identity");
  for (const field of ["batch_id", "unit_id", "task_id", "attempt_id"]) {
    assertString(identity[field], `identity.${field}`);
  }
  const events = [];
  const calls = new Map();
  const missing = [];
  let sequence = 0;
  let finalResponse = null;
  let promptText = null;
  for (const item of loaded.messages) {
    if (item.metadata.isComplete !== true) missing.push(`incomplete_message:${item.id}`);
    const contentBlocks = Array.isArray(item.message.content) ? item.message.content : [];
    if (contentBlocks.length === 0) missing.push(`empty_message:${item.id}`);
    for (let contentIndex = 0; contentIndex < contentBlocks.length; contentIndex += 1) {
      const block = contentBlocks[contentIndex];
      const eventId = `${item.id}:${contentIndex}`;
      const base = {
        schema_id: GENERAL_TRANSCRIPT_EVENT_SCHEMA,
        schema_version: 1,
        identity,
        event_id: eventId,
        sequence,
        occurred_at: null,
        source: source(item.source_ref, redacted),
        native: {
          conversation_id: loaded.conversation_id,
          request_id: loaded.request_id,
          message_id: item.id,
          trace_id: item.extra.traceId || null,
          response_id: item.extra.responseId || null,
        },
      };
      if (block?.type === "text" && item.message.role === "user") {
        const text = String(block.text || "");
        events.push({ ...base, type: "user_message", role: "user", content: text });
        if (promptText === null) promptText = text;
      } else if (block?.type === "text" && item.message.role === "assistant") {
        const text = String(block.text || "");
        events.push({ ...base, type: "assistant_message", role: "assistant", content: text });
        if (text.trim()) finalResponse = text;
      } else if (block?.type === "tool-call" && item.message.role === "assistant") {
        const callId = assertString(block.toolCallId, `toolCallId ${item.id}`);
        const call = calls.get(callId) || { call_id: callId, call_sequence: null, result_sequence: null };
        if (call.call_sequence !== null) throw new Error(`WorkBuddy tool call id 重复：${callId}`);
        call.call_sequence = sequence;
        calls.set(callId, call);
        events.push({
          ...base,
          type: "tool_call",
          role: "assistant",
          content: null,
          tool: {
            call_id: callId,
            name: assertString(block.toolName, `toolName ${item.id}`),
            arguments: block.args ?? null,
            result: null,
            status: "unknown",
          },
        });
      } else if (block?.type === "tool-result" && item.message.role === "tool") {
        const callId = assertString(block.toolCallId, `tool result call id ${item.id}`);
        const call = calls.get(callId) || { call_id: callId, call_sequence: null, result_sequence: null };
        if (call.result_sequence !== null) throw new Error(`WorkBuddy tool result id 重复：${callId}`);
        call.result_sequence = sequence;
        calls.set(callId, call);
        events.push({
          ...base,
          type: "tool_result",
          role: null,
          content: null,
          tool: {
            call_id: callId,
            name: assertString(block.toolName, `tool result name ${item.id}`),
            arguments: null,
            result: block.result ?? null,
            status: toolStatus(block.result),
          },
        });
      } else {
        missing.push(`unsupported_content:${item.id}:${String(block?.type || "missing")}`);
        events.push({
          ...base,
          type: "status",
          role: null,
          content: `unsupported WorkBuddy content type: ${String(block?.type || "missing")}`,
        });
      }
      sequence += 1;
    }
  }
  for (const call of calls.values()) {
    if (call.call_sequence === null) missing.push(`tool_call:${call.call_id}`);
    if (call.result_sequence === null) missing.push(`tool_result:${call.call_id}`);
  }
  const requestState = classifyWorkBuddyState(loaded.request.state);
  if (requestState.kind !== "success") missing.push(`request_terminal_state:${requestState.raw || "missing"}`);
  if (promptText === null) missing.push("user_prompt");
  if (finalResponse === null) missing.push("final_response");
  const uniqueMissing = [...new Set(missing)].sort();
  const resources = buildWorkBuddyResourceObservation(loaded, events);
  return {
    schema_version: WORKBUDDY_HISTORY_OBSERVATION_SCHEMA,
    adapter: { id: WORKBUDDY_HISTORY_ADAPTER_ID, version: WORKBUDDY_HISTORY_ADAPTER_VERSION },
    binding: {
      workspace: loaded.workspace,
      workspace_history_key: loaded.workspace_history_key,
      conversation_id: loaded.conversation_id,
      request_id: loaded.request_id,
      request_state: requestState,
    },
    prompt: {
      content: promptText,
      sha256: promptText === null ? null : createHash("sha256").update(promptText).digest("hex"),
    },
    final_response: finalResponse,
    events,
    calls: [...calls.values()].sort((left, right) => (left.call_sequence ?? Number.MAX_SAFE_INTEGER) - (right.call_sequence ?? Number.MAX_SAFE_INTEGER)),
    normalization: {
      native_message_count: loaded.messages.length,
      normalized_event_count: events.length,
      filtered_native_event_count: 0,
      compatibility_profiles: ["workbuddy-native-history-5.5.3"],
    },
    completeness: {
      status: uniqueMissing.length === 0 ? "complete" : "partial",
      omitted_event_count: 0,
      missing: uniqueMissing,
    },
    resources,
  };
}

function metricFromObservation(metric) {
  return { value: metric.value, status: metric.status, basis: metric.basis };
}

export function toGeneralResourceMetrics({
  identity,
  observation,
  sourceArtifact,
  collectedAt = new Date().toISOString(),
}) {
  assertObject(identity, "identity");
  assertObject(observation, "observation");
  assertObject(sourceArtifact, "sourceArtifact");
  const primary = observation.primary_request;
  assertObject(primary, "observation.primary_request");
  const fields = [
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_output_tokens",
    "request_count",
    "request_attempt_count",
    "call_count",
    "duration_seconds",
    "agent_duration_seconds",
  ];
  const coverage = Object.fromEntries(fields.map((field) => [field, primary[field].coverage]));
  const knownSubtotals = Object.fromEntries(fields
    .filter((field) => new Set(["partial", "unverified"]).has(primary[field].status))
    .map((field) => [field, primary[field].known_subtotal]));
  const metricSources = Object.fromEntries(fields.map((field) => [
    field,
    [`${sourceArtifact.path}#/resources/primary_request/${field}`],
  ]));
  const statuses = fields.map((field) => primary[field].status);
  const collectionStatus = statuses.every((status) => status === "observed")
    ? "complete"
    : statuses.every((status) => status === "unavailable") ? "unavailable" : "partial";
  return {
    schema_id: GENERAL_RESOURCE_SCHEMA,
    schema_version: 1,
    identity,
    collection: {
      collector: "workbuddy-native-history-resource-adapter",
      version: WORKBUDDY_HISTORY_ADAPTER_VERSION,
      status: collectionStatus,
      collected_at: collectedAt,
      sources: [sourceArtifact],
      warnings: [
        "Primary request history does not expose cache-read, cache-write, reasoning, or verified duration metrics.",
        "Linked tool usage and credit are preserved in adapter evidence but excluded from primary resource totals.",
      ],
      excluded_scope: observation.exclusions,
      coverage,
      known_subtotals: knownSubtotals,
      metric_sources: metricSources,
    },
    metrics: {
      usage: {
        input_tokens: metricFromObservation(primary.input_tokens),
        output_tokens: metricFromObservation(primary.output_tokens),
        total_tokens: metricFromObservation(primary.total_tokens),
        cache_read_input_tokens: metricFromObservation(primary.cache_read_input_tokens),
        cache_creation_input_tokens: metricFromObservation(primary.cache_creation_input_tokens),
        reasoning_output_tokens: metricFromObservation(primary.reasoning_output_tokens),
      },
      requests: {
        request_count: metricFromObservation(primary.request_count),
        request_attempt_count: metricFromObservation(primary.request_attempt_count),
      },
      tools: { call_count: metricFromObservation(primary.call_count) },
      timing: {
        duration_seconds: metricFromObservation(primary.duration_seconds),
        agent_duration_seconds: metricFromObservation(primary.agent_duration_seconds),
      },
    },
  };
}

export async function inspectWorkBuddyHistoryArtifact(path) {
  const info = await stat(path);
  if (!info.isFile()) throw new Error(`WorkBuddy history artifact 不是文件：${path}`);
  return {
    path: basename(path),
    sha256: createHash("sha256").update(await readFile(path)).digest("hex"),
    size: info.size,
  };
}

export function logicalSourceRoot(loaded) {
  const fromData = relative(loaded.data_root, loaded.history_directory).split("/");
  return fromData.length >= 2
    ? `<ACCOUNT>/VSCode/<IDENTITY>/history/${loaded.workspace_history_key}`
    : `<HISTORY>/${loaded.workspace_history_key}`;
}
