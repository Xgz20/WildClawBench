import { createHash } from "node:crypto";
import { isAbsolute, join, normalize } from "node:path";

export const DRIVER_VERSION = "0.2.0";
export const PROBE_SCHEMA = "wildclawbench.doubaowork-readonly-probe/v1";
export const NATIVE_EVIDENCE_SCHEMA = "wildclawbench.doubaowork-native-evidence/v1";
export const DEFAULT_APP_PATH = "/Applications/DoubaoWork.app";
export const DEFAULT_BUNDLE_ID = "com.work.pc.doubao";
export const DEFAULT_ENDPOINT = "http://127.0.0.1:9260";
export const CHAT_HOSTNAME = "doubaowork-chat";
export const CHAT_PROTOCOLS = new Set(["doubaowork:", "chrome:"]);

export function sha256Text(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

export function parseLoopbackEndpoint(value) {
  const endpoint = new URL(value);
  const loopbackHosts = new Set(["127.0.0.1", "localhost", "[::1]"]);
  if (endpoint.protocol !== "http:"
      || !loopbackHosts.has(endpoint.hostname)
      || !endpoint.port
      || endpoint.username
      || endpoint.password
      || endpoint.pathname !== "/"
      || endpoint.search
      || endpoint.hash) {
    throw new Error("CDP endpoint 必须是带显式端口、无凭据和附加路径的 loopback HTTP 地址");
  }
  return endpoint;
}

export function parseConversationId(urlValue) {
  let url;
  try {
    url = new URL(urlValue);
  } catch {
    return null;
  }
  if (!CHAT_PROTOCOLS.has(url.protocol) || url.hostname !== CHAT_HOSTNAME) return null;
  const match = url.pathname.match(/^\/chat\/([0-9]+)\/?$/);
  return match?.[1] ?? null;
}

export function isDoubaoWorkChatTarget(target) {
  const url = typeof target === "string" ? target : target?.url;
  if (typeof url !== "string") return false;
  if (typeof target === "object" && target?.type && target.type !== "page") return false;
  try {
    const parsed = new URL(url);
    return CHAT_PROTOCOLS.has(parsed.protocol) && parsed.hostname === CHAT_HOSTNAME;
  } catch {
    return false;
  }
}

export function selectUniqueChatTarget(targets) {
  const matches = targets.filter(isDoubaoWorkChatTarget);
  if (matches.length !== 1) {
    throw new Error(`必须恰好发现一个 DoubaoWork chat target，实际为 ${matches.length}`);
  }
  return matches[0];
}

export function validateSessionId(value) {
  if (typeof value !== "string" || !/^[0-9]{1,64}$/.test(value)) {
    throw new Error("DoubaoWork session ID 必须是 1–64 位数字，禁止目录猜测或任意 UUID");
  }
  return value;
}

export function normalizeWorkspaceReadback(displayValue, userHome) {
  if (typeof displayValue !== "string" || displayValue.includes("\0") || displayValue.includes("\n")) {
    throw new Error("客户端 workspace 回读不是单行路径");
  }
  const trimmed = displayValue.trim();
  let expanded = trimmed;
  if (trimmed.startsWith("~/")) {
    expanded = join(userHome, trimmed.slice(2));
  } else if (trimmed === "~" || trimmed.startsWith("~")) {
    throw new Error("只允许展开客户端回读开头的 ~/，不解释其他 shell 缩写");
  }
  if (!isAbsolute(expanded)) throw new Error("客户端 workspace 回读必须是绝对路径或 ~/ 前缀路径");
  return normalize(expanded);
}

export function workspaceReadbackMatches(displayValue, expectedPath, userHome) {
  if (!isAbsolute(expectedPath)) throw new Error("期望 workspace 必须是绝对路径");
  return normalizeWorkspaceReadback(displayValue, userHome) === normalize(expectedPath);
}

export function classifyDomObservation(observation = {}) {
  if (observation.visibleError) return { kind: "failure-candidate", trusted: false };
  if (observation.userQuestion) return { kind: "needs-attention", trusted: false };
  if (observation.stopControlVisible || observation.running) return { kind: "running", trusted: false };
  if (observation.finalAssistantVisible && observation.replyActionsVisible) {
    return { kind: "ui-completion-candidate", trusted: false };
  }
  return { kind: "unknown", trusted: false };
}

export function unavailableUsage(reason) {
  const basis = reason || "DoubaoWork 当前原生证据未提供可验证 usage";
  const metric = () => ({ value: null, status: "unavailable", basis });
  return {
    input_tokens: metric(),
    output_tokens: metric(),
    total_tokens: metric(),
    cache_read_input_tokens: metric(),
    cache_creation_input_tokens: metric(),
    reasoning_output_tokens: metric(),
    request_count: metric(),
    request_attempt_count: metric(),
  };
}

export function summarizeTarget(target) {
  const url = new URL(target.url);
  const conversationId = parseConversationId(target.url);
  return {
    type: target.type ?? null,
    protocol: url.protocol,
    hostname: url.hostname,
    path_kind: conversationId ? "chat-with-numeric-id" : "other",
    conversation_id_sha256: conversationId ? sha256Text(conversationId) : null,
    conversation_id_length: conversationId?.length ?? null,
  };
}
