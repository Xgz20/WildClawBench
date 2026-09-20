import { createHash } from "node:crypto";

import {
  WORKBUDDY_RUNTIME_API_SCHEMA,
  WORKBUDDY_RUNTIME_API_SOURCE_KIND,
  buildWorkBuddyRuntimeSnapshot,
} from "../../vendor/e2e-shared/workbuddy-evidence/runtime-api.mjs";

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u;

function assertString(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} 必须是非空字符串`);
  return value;
}

function assertId(value, label) {
  const id = assertString(value, label);
  if (!SAFE_ID.test(id) || id === "." || id === ".." || /^[A-Za-z]:/u.test(id)) {
    throw new Error(`${label} 不是安全的运行时 ID`);
  }
  return id;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function requestPrompt(request) {
  return (Array.isArray(request?.userMessage?.content) ? request.userMessage.content : [])
    .filter((item) => item?.type === "text")
    .map((item) => String(item.text || ""))
    .join("");
}

function finalResponse(request) {
  return (Array.isArray(request?.assistantMessage?.content) ? request.assistantMessage.content : [])
    .filter((item) => item?.type === "text" && String(item.text || "").trim())
    .map((item) => String(item.text))
    .at(-1) || null;
}

function runtimeCompleteness(request) {
  const classify = (value) => {
    const normalized = String(value || "").toLowerCase();
    if (["completed", "complete", "success", "succeeded", "done", "finished"].includes(normalized)) return "success";
    if (["failed", "failure", "error", "errored", "cancelled", "canceled", "aborted", "interrupted"].includes(normalized)) return "failure";
    return "running";
  };
  const missing = [];
  if (classify(request?.userMessage?.state) !== "success") missing.push(`user_message_terminal_state:${request?.userMessage?.state || "missing"}`);
  if (classify(request?.assistantMessage?.state) !== "success") missing.push(`assistant_message_terminal_state:${request?.assistantMessage?.state || "missing"}`);
  if (classify(request?.state) !== "success") missing.push(`request_terminal_state:${request?.state || "missing"}`);
  if (!finalResponse(request)) missing.push("final_response");
  return { status: missing.length === 0 ? "complete" : "partial", missing };
}

async function evaluateRuntime(client, body, argument = undefined) {
  const serialized = argument === undefined ? "undefined" : JSON.stringify(argument);
  const expression = `(async (__arg) => {${body}\n})(${serialized})`;
  return client.evaluate(expression);
}

export async function listWorkBuddyRuntimeConversations(client) {
  const result = await evaluateRuntime(client, `
    if (!window.wb?.conversations?.list) throw new Error('WorkBuddy runtime conversations.list unavailable');
    let listed;
    try {
      if (window.wb.conversations.ensureList) {
        await window.wb.conversations.ensureList('local', { page: 1, size: 100 });
      }
      listed = await window.wb.conversations.list({ page: 1, size: 100 });
    } catch { listed = await window.wb.conversations.list(); }
    const current = window.wb.conversations.current;
    const currentId = window.wb.conversations.currentId || null;
    let currentInfo = current?.info || null;
    if (!currentInfo && currentId && window.wb.conversations.get) {
      try { currentInfo = (await window.wb.conversations.get(currentId))?.info || null; } catch {}
    }
    return {
      ...listed,
      currentId,
      currentInfo,
    };
  `);
  if (!result || !Array.isArray(result.items)) throw new Error("WorkBuddy runtime conversations.list 返回无效数据");
  const items = [...result.items];
  if (result.currentInfo?.id && !items.some((item) => item.id === result.currentInfo.id)) items.push(result.currentInfo);
  return { ...result, items };
}

export async function getWorkBuddyRuntimeConversation(client, conversationId) {
  const id = assertId(conversationId, "conversationId");
  const result = await evaluateRuntime(client, `
    const id = __arg.id;
    const conversation = await window.wb.conversations.get(id);
    if (!conversation?.requestEntries) throw new Error('WorkBuddy runtime requestEntries unavailable');
    const requestEntries = await conversation.requestEntries();
    return { conversation: conversation.info || null, requestEntries };
  `, { id });
  if (!result?.requestEntries || !Array.isArray(result.requestEntries.requests)) {
    throw new Error("WorkBuddy runtime requestEntries 返回无效数据");
  }
  return result;
}

export async function snapshotWorkBuddyRuntimeBaseline(client, workspace) {
  const listed = await listWorkBuddyRuntimeConversations(client);
  const exact = listed.items.filter((item) => item?.space?.cwd === workspace);
  const requestIds = {};
  for (const item of exact) {
    const id = assertId(item.id, "baseline conversationId");
    try {
      const loaded = await getWorkBuddyRuntimeConversation(client, id);
      requestIds[id] = loaded.requestEntries.requests.map((request) => assertId(request.id, "baseline requestId"));
    } catch {
      requestIds[id] = [];
    }
  }
  return {
    workspace,
    captured_at: new Date().toISOString(),
    conversations: exact.map((item) => ({
      id: item.id,
      updatedAt: item.updatedAt ?? item.updated_at ?? null,
      observedAt: Math.max(
        Number(item.updatedAt ?? item.updated_at ?? 0),
        Number(item.lastActivityAt ?? item.last_activity_at ?? 0),
      ) || null,
      lifecycle: item.lifecycle ?? null,
      state: item.state ?? null,
    })),
    request_ids: requestIds,
  };
}

export async function selectWorkBuddyRuntimeBinding({
  client,
  workspace,
  baseline,
  boundConversationId = null,
  boundRequestId = null,
  promptSha256 = null,
}) {
  const listed = await listWorkBuddyRuntimeConversations(client);
  const exact = listed.items.filter((item) => item?.space?.cwd === workspace);
  const old = new Map((baseline?.conversations || []).map((item) => [item.id, Number(item.updatedAt || 0)]));
  const oldRequestIds = baseline?.request_ids || {};
  let candidates = boundConversationId
    ? exact.filter((item) => item.id === assertId(boundConversationId, "bound conversationId"))
    : exact.filter((item) => (
      !old.has(item.id)
      || Number(item.updatedAt || item.updated_at || item.lastActivityAt || 0) > old.get(item.id)
      || (Array.isArray(oldRequestIds[item.id]) && oldRequestIds[item.id].length === 0)
    ));
  if (candidates.length !== 1) {
    return { binding: null, ambiguous: candidates.length > 1, match_count: candidates.length };
  }
  const listedConversation = candidates[0];
  const conversationId = assertId(listedConversation.id, "conversationId");
  const runtime = await getWorkBuddyRuntimeConversation(client, conversationId);
  if (runtime.requestEntries.historyReady !== true || runtime.requestEntries.hasOlder === true) {
    throw new Error("WORKBUDDY_RUNTIME_HISTORY_INCOMPLETE");
  }
  const conversation = { ...listedConversation, ...(runtime.conversation || {}) };
  const oldRequests = new Set(baseline?.request_ids?.[conversationId] || []);
  const requests = runtime.requestEntries.requests.filter((request) => {
    if (boundRequestId && request.id !== assertId(boundRequestId, "bound requestId")) return false;
    if (!boundRequestId && oldRequests.has(request.id)) return false;
    if (promptSha256 && sha256(requestPrompt(request)) !== promptSha256) return false;
    return true;
  });
  if (requests.length !== 1) {
    return { binding: null, ambiguous: requests.length > 1, match_count: requests.length };
  }
  const request = requests[0];
  const snapshot = buildWorkBuddyRuntimeSnapshot({
    conversation,
    request,
    requestEntries: runtime.requestEntries,
    capturedAt: new Date().toISOString(),
  });
  const status = request.state || request.assistantMessage?.state || conversation.lifecycle || conversation.state || "unknown";
  const terminal = (value) => {
    const normalized = String(value || "").toLowerCase();
    if (["completed", "complete", "success", "succeeded", "done", "finished", "idle"].includes(normalized)) return "success";
    if (["failed", "failure", "error", "errored", "cancelled", "canceled", "aborted", "interrupted"].includes(normalized)) return "failure";
    if (["created", "pending", "queued", "running", "working", "streaming", "processing", "active"].includes(normalized)) return "running";
    return "unknown";
  };
  const assistantState = request.assistantMessage?.state || "";
  return {
    ambiguous: false,
    match_count: 1,
    binding: {
      source_kind: WORKBUDDY_RUNTIME_API_SOURCE_KIND,
      runtime_snapshot: snapshot,
      session_snapshot: {
        conversation_id: conversationId,
        cwd: conversation.space?.cwd || null,
        status,
        updated_at_ms: Number(conversation.updatedAt || conversation.updated_at || conversation.lastActivityAt || 0) || null,
      },
      history: {
        source_kind: WORKBUDDY_RUNTIME_API_SOURCE_KIND,
        binding: {
          conversation_id: conversationId,
          request_id: request.id,
          request_state: { raw: String(request.state || "") },
          workspace_history_key: null,
          source_kind: WORKBUDDY_RUNTIME_API_SOURCE_KIND,
        },
        runtime_terminal: {
          request_state: terminal(request.state),
          user_message_state: terminal(request.userMessage?.state),
          assistant_message_state: terminal(assistantState),
          conversation_state: terminal(conversation.state),
          conversation_lifecycle: terminal(conversation.lifecycle),
        },
        prompt: { content: requestPrompt(request), sha256: sha256(requestPrompt(request)) },
        completeness: runtimeCompleteness(request),
        final_response: finalResponse(request),
        request,
        conversation,
        resources: null,
      },
      artifacts: [],
    },
  };
}

export function runtimeApiSourceInfo() {
  return { schema_version: WORKBUDDY_RUNTIME_API_SCHEMA, source_kind: WORKBUDDY_RUNTIME_API_SOURCE_KIND };
}
