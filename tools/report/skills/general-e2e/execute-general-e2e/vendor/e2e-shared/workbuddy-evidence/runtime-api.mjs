import { createHash } from "node:crypto";

export const WORKBUDDY_RUNTIME_API_SOURCE_KIND = "workbuddy-runtime-api";
export const WORKBUDDY_RUNTIME_API_SCHEMA =
  "wildclawbench.workbuddy-runtime-api-snapshot/v1";

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u;

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

function textFromContent(content) {
  if (!Array.isArray(content)) return "";
  return content
    .filter((item) => item?.type === "text")
    .map((item) => String(item.text || ""))
    .join("");
}

function requestPrompt(request) {
  return textFromContent(request?.userMessage?.content);
}

function toolName(item) {
  return String(
    item?._meta?.["codebuddy.ai/toolName"]
      || item?.title
      || item?.toolName
      || "tool",
  );
}

function toolResult(item) {
  return item?.rawOutput ?? item?.output ?? item?.result ?? null;
}

function messageExtra(request, conversationId) {
  return {
    requestId: request.id,
    traceId: request.traceId || request.conversationRequestId || null,
    responseId: request.assistantMessage?.content?.find((item) => item?.messageId)?.messageId || null,
    conversationId,
  };
}

function runtimeMessages(snapshot) {
  const request = assertObject(snapshot.request, "runtime.request");
  const conversationId = assertId(snapshot.conversation?.id, "runtime.conversation.id");
  const requestId = assertId(request.id, "runtime.request.id");
  const extra = messageExtra(request, conversationId);
  const messages = [];
  const messageIds = [];
  const add = (suffix, role, content, metadata = {}) => {
    const id = `${requestId}-${suffix}`;
    assertId(id, "runtime message id");
    messageIds.push(id);
    messages.push({
      id,
      metadata: { id, role, isComplete: ["complete", "completed", "success", "succeeded"].includes(
        role === "user" ? request.userMessage?.state : request.assistantMessage?.state
      ), ...metadata },
      envelope: { id, role, message: { role, content }, extra },
      message: { role, content },
      extra,
      source_ref: "raw/workbuddy-runtime/runtime-binding.json",
      artifact: null,
    });
  };

  const userMessage = assertObject(request.userMessage, "runtime.request.userMessage");
  add("user", "user", Array.isArray(userMessage.content) ? userMessage.content : []);
  const assistantContent = Array.isArray(request.assistantMessage?.content)
    ? request.assistantMessage.content : [];
  let toolIndex = 0;
  let textIndex = 0;
  for (const item of assistantContent) {
    if (item?.type === "text") {
      add(`assistant-text-${textIndex++}`, "assistant", [item]);
      continue;
    }
    if (item?.type !== "tool" && item?.sessionUpdate !== "tool_call_update") {
      add(`unsupported-${textIndex++}`, "assistant", [item]);
      continue;
    }
    const callId = assertId(item.toolCallId, "runtime toolCallId");
    const name = toolName(item);
    add(`assistant-tool-${toolIndex}`, "assistant", [{
      type: "tool-call",
      toolCallId: callId,
      toolName: name,
      args: item.rawInput ?? item.input ?? null,
    }]);
    add(`tool-result-${toolIndex}`, "tool", [{
      type: "tool-result",
      toolCallId: callId,
      toolName: name,
      result: {
        status: item.status || "unknown",
        success: ["completed", "success"].includes(item.status) ? true
          : ["failed", "error", "cancelled"].includes(item.status) ? false : null,
        rawOutput: toolResult(item),
        toolInfo: [],
      },
    }]);
    toolIndex += 1;
  }
  if (messages.length < 2) throw new Error("runtime request 缺少 user/assistant 消息");
  return { messages, messageIds };
}

/**
 * Convert a serialised window.wb.conversations.get(id).requestEntries() result
 * into the common WorkBuddy loaded conversation shape. The runtime payload is
 * preserved by the caller as a raw binding artifact; this function only adds
 * deterministic message envelopes for the shared normalizer.
 */
export function loadWorkBuddyRuntimeConversation({ snapshot, sourceArtifact = null }) {
  assertObject(snapshot, "runtime snapshot");
  if (snapshot.schema_version !== WORKBUDDY_RUNTIME_API_SCHEMA) {
    throw new Error("WORKBUDDY_RUNTIME_SCHEMA_UNSUPPORTED");
  }
  if (snapshot.source_kind !== WORKBUDDY_RUNTIME_API_SOURCE_KIND) {
    throw new Error("WORKBUDDY_RUNTIME_SOURCE_KIND_MISMATCH");
  }
  const conversation = assertObject(snapshot.conversation, "runtime.conversation");
  const conversationId = assertId(conversation.id, "runtime conversation id");
  const request = assertObject(snapshot.request, "runtime.request");
  const requestId = assertId(request.id, "runtime request id");
  const space = assertObject(conversation.space, "runtime conversation.space");
  const workspace = assertString(space.cwd, "runtime conversation.space.cwd");
  const built = runtimeMessages({ ...snapshot, conversation, request });
  const normalizedRequest = {
    ...request,
    messages: built.messageIds,
    state: request.state || "unknown",
    startedAt: request.timestamp || null,
  };
  const conversationIndex = {
    id: conversationId,
    requests: [normalizedRequest],
    messages: built.messages.map((item) => item.metadata),
  };
  const workspaceIndex = {
    conversations: [conversation],
  };
  const artifact = sourceArtifact || null;
  return {
    source_kind: WORKBUDDY_RUNTIME_API_SOURCE_KIND,
    data_root: null,
    workspace,
    workspace_history_key: null,
    history_directory: null,
    conversation_id: conversationId,
    request_id: requestId,
    conversation,
    request: normalizedRequest,
    messages: built.messages,
    workspace_index: workspaceIndex,
    conversation_index: conversationIndex,
    source_refs: {
      workspace_index: "raw/workbuddy-runtime/runtime-binding.json",
      conversation_index: "raw/workbuddy-runtime/runtime-binding.json",
      messages: built.messages.map(() => "raw/workbuddy-runtime/runtime-binding.json"),
    },
    source_artifacts: {
      runtime: artifact,
    },
  };
}

export function runtimePromptSha256(snapshot) {
  return sha256(requestPrompt(snapshot?.request));
}

export function runtimeRequestPrompt(snapshot) {
  return requestPrompt(snapshot?.request);
}

export function buildWorkBuddyRuntimeSnapshot({ conversation, request, requestEntries, capturedAt }) {
  assertObject(conversation, "conversation");
  assertObject(request, "request");
  assertObject(requestEntries, "requestEntries");
  return {
    schema_version: WORKBUDDY_RUNTIME_API_SCHEMA,
    source_kind: WORKBUDDY_RUNTIME_API_SOURCE_KIND,
    captured_at: capturedAt || new Date().toISOString(),
    conversation,
    request,
    request_entries: requestEntries,
    prompt_sha256: runtimePromptSha256({ request }),
  };
}
