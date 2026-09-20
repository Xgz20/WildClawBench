import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { lstat, mkdir, open, readFile, readdir, realpath, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";
import {
  WORKBUDDY_RUNTIME_API_SOURCE_KIND,
  loadWorkBuddyRuntimeConversation,
} from "./runtime-api.mjs";

export const WORKBUDDY_HISTORY_ADAPTER_ID = "workbuddy-native-history";
export const WORKBUDDY_HISTORY_ADAPTER_VERSION = "0.2.0";
export const WORKBUDDY_HISTORY_OBSERVATION_SCHEMA =
  "wildclawbench.workbuddy-native-history-observation/v1";
export const GENERAL_RESOURCE_SCHEMA =
  "urn:wildclawbench:schema:general-e2e:resource-metrics:v1";
export const GENERAL_TRANSCRIPT_EVENT_SCHEMA =
  "urn:wildclawbench:schema:general-e2e:transcript-event:v1";
export const GENERAL_TRACE_INDEX_SCHEMA =
  "urn:wildclawbench:schema:general-e2e:trace-index:v2";
export const GENERAL_TRACE_INDEX_VERSION = 2;

const SUCCESS_STATES = new Set(["complete", "completed", "success", "succeeded", "done", "finished"]);
const FAILURE_STATES = new Set(["failed", "failure", "error", "errored", "cancelled", "canceled", "aborted", "interrupted"]);
const RUNNING_STATES = new Set(["created", "pending", "queued", "running", "working", "streaming", "processing", "active"]);
const SAFE_NATIVE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u;
const TOOL_SUCCESS_STATES = new Set(["success", "succeeded"]);
const TOOL_FAILURE_STATES = new Set(["failed", "failure", "error", "errored"]);

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

export function assertSafeWorkBuddyNativeId(value, label) {
  const id = assertString(value, label);
  if (!SAFE_NATIVE_ID.test(id) || id === "." || id === ".." || /^[A-Za-z]:/u.test(id)) {
    throw new Error(`${label} 不是安全的原生 ID 段`);
  }
  return id;
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

function isInside(root, target) {
  const value = relative(root, target);
  return value === "" || (!value.startsWith("..") && !isAbsolute(value));
}

async function assertTrustedPath(root, target, expectedType, label) {
  const canonicalRoot = await realpath(resolve(root));
  const lexicalTarget = resolve(target);
  if (!isInside(canonicalRoot, lexicalTarget)) throw new Error(`${label} 越出已验证 history 根`);
  const segments = relative(canonicalRoot, lexicalTarget).split(/[\\/]+/u).filter(Boolean);
  let current = canonicalRoot;
  for (const segment of segments) {
    current = join(current, segment);
    const info = await lstat(current);
    if (info.isSymbolicLink()) throw new Error(`${label} 路径包含符号链接：${current}`);
  }
  const info = await lstat(lexicalTarget);
  if (expectedType === "file" && !info.isFile()) throw new Error(`${label} 不是普通文件`);
  if (expectedType === "directory" && !info.isDirectory()) throw new Error(`${label} 不是目录`);
  const canonicalTarget = await realpath(lexicalTarget);
  if (!isInside(canonicalRoot, canonicalTarget)) throw new Error(`${label} 解析后越出已验证 history 根`);
  return { root: canonicalRoot, path: canonicalTarget };
}

function sameFileSnapshot(left, right) {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.size === right.size
    && left.mtimeNs === right.mtimeNs
    && left.ctimeNs === right.ctimeNs;
}

async function readJsonSnapshot(path, label, trustedRoot) {
  const verified = await assertTrustedPath(trustedRoot, path, "file", label);
  let handle;
  try {
    handle = await open(verified.path, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW || 0));
    const before = await handle.stat({ bigint: true });
    const bytes = await handle.readFile();
    const after = await handle.stat({ bigint: true });
    if (!sameFileSnapshot(before, after) || BigInt(bytes.length) !== after.size) {
      throw new Error("文件在读取期间发生变化");
    }
    let value;
    try {
      value = JSON.parse(bytes.toString("utf8"));
    } catch (error) {
      throw new Error(`不是有效 JSON：${error instanceof Error ? error.message : String(error)}`);
    }
    return {
      value: assertObject(value, label),
      artifact: {
        path: verified.path,
        sha256: createHash("sha256").update(bytes).digest("hex"),
        size: bytes.length,
        modified_at: new Date(Number(after.mtimeNs / 1_000_000n)).toISOString(),
      },
    };
  } catch (error) {
    throw new Error(`${label} 读取失败：${error instanceof Error ? error.message : String(error)}`);
  } finally {
    await handle?.close().catch(() => {});
  }
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
  const normalized = raw.toLowerCase();
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
  const verifiedCandidates = [];
  for (const item of candidates) {
    verifiedCandidates.push((await assertTrustedPath(
      canonicalDataRoot,
      item,
      "directory",
      "WorkBuddy workspace history",
    )).path);
  }
  const unique = [...new Set(verifiedCandidates)];
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
  assertSafeWorkBuddyNativeId(conversationId, "conversationId");
  assertSafeWorkBuddyNativeId(requestId, "requestId");
  const located = await findWorkBuddyWorkspaceHistory({ dataRoot, workspace });
  const workspaceIndexPath = join(located.history_directory, "index.json");
  const workspaceIndexSnapshot = await readJsonSnapshot(
    workspaceIndexPath,
    "WorkBuddy workspace index",
    located.history_directory,
  );
  const workspaceIndex = workspaceIndexSnapshot.value;
  const conversation = chooseExact(workspaceIndex.conversations || [], conversationId, "conversationId");
  const conversationDirectory = join(located.history_directory, conversationId);
  await assertTrustedPath(
    located.history_directory,
    conversationDirectory,
    "directory",
    "WorkBuddy conversation 目录",
  );
  const conversationIndexPath = join(conversationDirectory, "index.json");
  const conversationIndexSnapshot = await readJsonSnapshot(
    conversationIndexPath,
    "WorkBuddy conversation index",
    located.history_directory,
  );
  const conversationIndex = conversationIndexSnapshot.value;
  const request = chooseExact(conversationIndex.requests || [], requestId, "requestId");
  const indexedMessages = new Map();
  for (const item of conversationIndex.messages || []) {
    if (!isObject(item)) throw new Error("WorkBuddy message index 含无效条目");
    assertSafeWorkBuddyNativeId(item.id, "WorkBuddy message id");
    if (indexedMessages.has(item.id)) throw new Error(`WorkBuddy message id 重复：${item.id}`);
    indexedMessages.set(item.id, item);
  }
  if (!Array.isArray(request.messages) || request.messages.length === 0) {
    throw new Error(`WorkBuddy request ${requestId} 没有消息引用`);
  }
  const seen = new Set();
  const messages = [];
  for (const messageId of request.messages) {
    assertSafeWorkBuddyNativeId(messageId, "request.messages[]");
    if (seen.has(messageId)) throw new Error(`WorkBuddy request 消息引用重复：${messageId}`);
    seen.add(messageId);
    const metadata = indexedMessages.get(messageId);
    if (!metadata) throw new Error(`WorkBuddy request 引用了不存在的消息：${messageId}`);
    const messagePath = join(conversationDirectory, "messages", `${messageId}.json`);
    const messageSnapshot = await readJsonSnapshot(
      messagePath,
      `WorkBuddy message ${messageId}`,
      located.history_directory,
    );
    const envelope = messageSnapshot.value;
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
      artifact: messageSnapshot.artifact,
    });
  }
  return {
    source_kind: "workbuddy-native-history",
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
    source_artifacts: {
      workspace_index: workspaceIndexSnapshot.artifact,
      conversation_index: conversationIndexSnapshot.artifact,
      messages: messages.map((item) => item.artifact),
    },
  };
}

export function loadWorkBuddyRuntimeBinding({ value, sourceArtifact }) {
  return loadWorkBuddyRuntimeConversation({
    snapshot: value.runtime_snapshot || value,
    sourceArtifact,
  });
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
  const rawStatus = String(result?.status || result?.result?.status || "").trim().toLowerCase();
  if (result?.success === true) return "success";
  if (result?.success === false) return "error";
  const exitCode = result?.exit_code ?? result?.exitCode ?? result?.result?.exit_code ?? result?.result?.exitCode;
  if (typeof exitCode === "number" && Number.isInteger(exitCode)) return exitCode === 0 ? "success" : "error";
  if (TOOL_SUCCESS_STATES.has(rawStatus)) return "success";
  if (TOOL_FAILURE_STATES.has(rawStatus)) return "error";
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
          status: toolStatus({
            status: nested?.executeStatus,
            success: nested?.success,
            exitCode: nested?.exitCode ?? nested?.exit_code,
          }),
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
      native_event_count: events.length,
      normalized_event_count: events.length,
      filtered_native_event_count: 0,
      compatibility_profiles: loaded.source_kind === WORKBUDDY_RUNTIME_API_SOURCE_KIND
        ? ["workbuddy-runtime-api"]
        : ["workbuddy-native-history-5.5.3"],
    },
    completeness: {
      status: uniqueMissing.length === 0 ? "complete" : "partial",
      omitted_event_count: 0,
      missing: uniqueMissing,
    },
    resources,
  };
}

function portableArtifactPath(value, label, prefix = null) {
  assertString(value, label);
  if ((prefix !== null && !value.startsWith(`${prefix}/`)) || value.includes("\\")
      || value.split("/").some((part) => !part || part === "." || part === ".." || part.includes(":"))) {
    throw new Error(`${label} 不是安全的相对路径`);
  }
  return value;
}

function artifactFromBytes(path, bytes, extra = {}) {
  return {
    path,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    size: bytes.length,
    ...extra,
  };
}

function transcriptBytes(normalized) {
  assertObject(normalized, "normalized");
  if (!Array.isArray(normalized.events) || normalized.events.length === 0) {
    throw new Error("WORKBUDDY_TRANSCRIPT_EMPTY");
  }
  return Buffer.from(`${normalized.events.map((event) => JSON.stringify(event)).join("\n")}\n`, "utf8");
}

function sourceArtifactList(loaded) {
  if (loaded?.source_kind === WORKBUDDY_RUNTIME_API_SOURCE_KIND) {
    const runtime = loaded.source_artifacts?.runtime;
    if (!runtime) throw new Error("WORKBUDDY_RUNTIME_SOURCE_ARTIFACT_MISSING");
    return [{ source: runtime, path: "raw/workbuddy-runtime/runtime-binding.json" }];
  }
  const source = loaded?.source_artifacts;
  if (!isObject(source) || !source.workspace_index || !source.conversation_index
      || !Array.isArray(source.messages) || source.messages.length === 0) {
    throw new Error("WORKBUDDY_NATIVE_SOURCE_ARTIFACTS_INCOMPLETE");
  }
  return [
    { source: source.workspace_index, path: "raw/workbuddy-history/workspace-index.json" },
    { source: source.conversation_index, path: "raw/workbuddy-history/conversation-index.json" },
    ...source.messages.map((item) => {
      const id = assertSafeWorkBuddyNativeId(
        basename(String(item.path || "")).replace(/\.json$/u, ""),
        "WorkBuddy message artifact id",
      );
      return { source: item, path: `raw/workbuddy-history/messages/${id}.json` };
    }),
  ];
}

async function readStableArtifact(source, label) {
  assertObject(source, label);
  const sourcePath = resolve(assertString(source.path, `${label}.path`));
  const info = await lstat(sourcePath);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`${label} 不是普通文件`);
  const bytes = await readFile(sourcePath);
  const actual = artifactFromBytes(source.path, bytes);
  if (actual.sha256 !== source.sha256 || actual.size !== source.size) {
    throw new Error(`${label} 在采集期间发生变化`);
  }
  return bytes;
}

async function writeNewArtifact(root, artifactPath, bytes) {
  const relativePath = portableArtifactPath(artifactPath, "artifact.path");
  const destination = join(root, relativePath);
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, bytes, { flag: "wx" });
  return artifactFromBytes(relativePath, bytes);
}

/**
 * Build the public CB-B trace-index v2 envelope from a normalized WorkBuddy
 * request. Native thread/lifecycle values remain null when WorkBuddy does not
 * expose them; this function never infers terminal/cwd/usage values.
 */
export function buildWorkBuddyTraceIndex({
  identity,
  loaded,
  normalized,
  transcriptArtifact,
  rawTrace,
  bindingEvidence,
  lifecycleGeneration = null,
  adapterSource = "WorkBuddy native history (read-only)",
}) {
  assertObject(identity, "identity");
  assertObject(loaded, "loaded");
  assertObject(normalized, "normalized");
  assertObject(transcriptArtifact, "transcriptArtifact");
  if (!Array.isArray(rawTrace) || rawTrace.length === 0) throw new Error("WORKBUDDY_RAW_TRACE_EMPTY");
  if (!Array.isArray(bindingEvidence) || bindingEvidence.length === 0) {
    throw new Error("WORKBUDDY_BINDING_EVIDENCE_EMPTY");
  }
  const sessionId = assertSafeWorkBuddyNativeId(loaded.conversation_id, "conversation_id");
  const requestId = assertSafeWorkBuddyNativeId(loaded.request_id, "request_id");
  const cwd = resolve(assertString(loaded.workspace, "loaded.workspace"));
  const events = normalized.events;
  const nativeEventCount = Number.isSafeInteger(normalized.normalization?.native_event_count)
    ? normalized.normalization.native_event_count : events.length;
  if (nativeEventCount < 1 || events.length < 1) throw new Error("WORKBUDDY_TRANSCRIPT_EMPTY");
  if (normalized.normalization?.normalized_event_count !== events.length) {
    throw new Error("WORKBUDDY_NORMALIZATION_COUNT_MISMATCH");
  }
  return {
    schema_id: GENERAL_TRACE_INDEX_SCHEMA,
    schema_version: GENERAL_TRACE_INDEX_VERSION,
    identity,
    adapter: {
      id: WORKBUDDY_HISTORY_ADAPTER_ID,
      version: WORKBUDDY_HISTORY_ADAPTER_VERSION,
      source: adapterSource,
    },
    session: {
      thread_id: null,
      turn_id: requestId,
      session_id: sessionId,
      cwd,
      lifecycle_generation: lifecycleGeneration,
    },
    transcript: { ...transcriptArtifact, path: "transcript.jsonl", event_count: events.length },
    raw_trace: rawTrace,
    raw_event_range: { first_sequence: 0, last_sequence: nativeEventCount - 1, event_count: nativeEventCount },
    normalization: {
      native_event_count: nativeEventCount,
      normalized_event_count: events.length,
      filtered_native_event_count: normalized.normalization?.filtered_native_event_count || 0,
      compatibility_profiles: normalized.normalization?.compatibility_profiles || ["workbuddy-native-history-5.5.3"],
    },
    completeness: normalized.completeness,
    calls: normalized.calls,
    binding_evidence: bindingEvidence,
  };
}

/**
 * Copy one verified WorkBuddy history request into a CB-B trace directory.
 * The returned bundle can be passed directly to the common finalizer after a
 * caller adds the CB-A state artifact to resource provenance. No native
 * terminal, cwd, retry, credit, or cleanup value is synthesized here.
 */
export async function collectWorkBuddyGeneralEvidence({
  identity,
  loaded,
  normalized = normalizeWorkBuddyConversation(loaded, { identity, redacted: true }),
  outputRoot,
  bindingSources,
  lifecycleGeneration = null,
  writeResourceMetrics = false,
  collectedAt = new Date().toISOString(),
}) {
  const traceRoot = resolve(assertString(outputRoot, "outputRoot"));
  await mkdir(traceRoot, { recursive: true });
  const transcript = transcriptBytes(normalized);
  const transcriptArtifact = await writeNewArtifact(traceRoot, "transcript.jsonl", transcript);
  const rawTrace = [];
  for (const item of sourceArtifactList(loaded)) {
    const bytes = await readStableArtifact(item.source, `WorkBuddy ${item.path}`);
    rawTrace.push(await writeNewArtifact(traceRoot, item.path, bytes));
  }
  if (!Array.isArray(bindingSources) || bindingSources.length === 0) {
    throw new Error("WORKBUDDY_BINDING_SOURCES_EMPTY");
  }
  const bindingEvidence = [];
  for (const [index, item] of bindingSources.entries()) {
    assertObject(item, `bindingSources[${index}]`);
    const source = item.source || item;
    const target = item.target || `bindings/source-${index + 1}.json`;
    const relativeTarget = portableArtifactPath(target, `bindingSources[${index}].target`, "bindings");
    const bytes = await readStableArtifact(source, `WorkBuddy binding source ${index + 1}`);
    bindingEvidence.push(await writeNewArtifact(traceRoot, relativeTarget, bytes));
  }
  const index = buildWorkBuddyTraceIndex({
    identity,
    loaded,
    normalized,
    transcriptArtifact,
    rawTrace,
    bindingEvidence,
    lifecycleGeneration,
  });
  const indexBytes = Buffer.from(`${JSON.stringify(index, null, 2)}\n`, "utf8");
  const traceIndexArtifact = await writeNewArtifact(traceRoot, "trace-index.json", indexBytes);
  const resourceMetrics = toGeneralResourceMetrics({
    identity,
    observation: normalized.resources,
    sourceArtifact: traceIndexArtifact,
    collectedAt,
  });
  if (writeResourceMetrics) {
    await writeFile(join(traceRoot, "resource-metrics.json"), `${JSON.stringify(resourceMetrics, null, 2)}\n`, { flag: "wx" });
  }
  return {
    trace_root: traceRoot,
    trace_index: index,
    trace_index_artifact: traceIndexArtifact,
    transcript_artifact: transcriptArtifact,
    raw_trace: rawTrace,
    binding_evidence: bindingEvidence,
    resource_metrics: resourceMetrics,
    resource_metrics_path: writeResourceMetrics ? join(traceRoot, "resource-metrics.json") : null,
  };
}

function metricFromObservation(metric) {
  return {
    value: metric.value,
    status: metric.status,
    basis: metric.basis,
    known_subtotal: metric.known_subtotal,
    coverage: metric.coverage,
  };
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
  const snapshot = await readJsonSnapshot(path, "WorkBuddy history artifact", dirname(resolve(path)));
  return {
    path: basename(path),
    sha256: snapshot.artifact.sha256,
    size: snapshot.artifact.size,
  };
}

export function logicalSourceRoot(loaded) {
  const fromData = relative(loaded.data_root, loaded.history_directory).split("/");
  return fromData.length >= 2
    ? `<ACCOUNT>/VSCode/<IDENTITY>/history/${loaded.workspace_history_key}`
    : `<HISTORY>/${loaded.workspace_history_key}`;
}
