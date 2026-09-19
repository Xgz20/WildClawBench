import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { lstat, open, readdir, realpath } from "node:fs/promises";
import { isAbsolute, join, relative, resolve } from "node:path";

import { queryWorkBuddySessions } from "./probe.mjs";

const SAFE_NATIVE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u;

function assertSafeId(value, label) {
  const id = String(value || "");
  if (!SAFE_NATIVE_ID.test(id) || id === "." || id === ".." || /^[A-Za-z]:/u.test(id)) {
    throw new Error(`${label} 不是安全的原生 ID 段`);
  }
  return id;
}

function isInside(root, target) {
  const value = relative(root, target);
  return value === "" || (!value.startsWith("..") && !isAbsolute(value));
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

async function assertTrustedPath(root, target, expectedType, label) {
  const canonicalRoot = await realpath(resolve(root));
  const lexicalTarget = resolve(target);
  if (!isInside(canonicalRoot, lexicalTarget)) throw new Error(`${label} 越出 history 根`);
  let current = canonicalRoot;
  for (const segment of relative(canonicalRoot, lexicalTarget).split(/[\\/]+/u).filter(Boolean)) {
    current = join(current, segment);
    const info = await lstat(current);
    if (info.isSymbolicLink()) throw new Error(`${label} 路径包含符号链接`);
  }
  const info = await lstat(lexicalTarget);
  if (expectedType === "file" && !info.isFile()) throw new Error(`${label} 不是普通文件`);
  if (expectedType === "directory" && !info.isDirectory()) throw new Error(`${label} 不是目录`);
  const canonicalTarget = await realpath(lexicalTarget);
  if (!isInside(canonicalRoot, canonicalTarget)) throw new Error(`${label} 解析后越出 history 根`);
  return canonicalTarget;
}

function sameSnapshot(left, right) {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.size === right.size
    && left.mtimeNs === right.mtimeNs
    && left.ctimeNs === right.ctimeNs;
}

async function readStableJson(path, root, label) {
  const trusted = await assertTrustedPath(root, path, "file", label);
  let handle;
  try {
    handle = await open(trusted, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW || 0));
    const before = await handle.stat({ bigint: true });
    const bytes = await handle.readFile();
    const after = await handle.stat({ bigint: true });
    if (!sameSnapshot(before, after) || BigInt(bytes.length) !== after.size) {
      throw new Error(`${label} 在读取期间发生变化`);
    }
    const value = JSON.parse(bytes.toString("utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`${label} 必须是 JSON 对象`);
    }
    return {
      value,
      artifact: {
        path: trusted,
        sha256: createHash("sha256").update(bytes).digest("hex"),
        size: bytes.length,
        modified_at: new Date(Number(after.mtimeNs / 1_000_000n)).toISOString(),
      },
    };
  } finally {
    await handle?.close().catch(() => {});
  }
}

function workspaceKey(workspace) {
  return createHash("md5").update(resolve(workspace)).digest("hex");
}

async function findHistoryRoot(dataRoot, workspace) {
  const root = await realpath(resolve(dataRoot));
  const key = workspaceKey(await realpath(resolve(workspace)));
  const candidates = [];
  for (const account of await childDirectories(root)) {
    const vscodeRoot = join(root, account, "VSCode");
    const identityRoots = [vscodeRoot];
    for (const identity of await childDirectories(vscodeRoot)) identityRoots.push(join(vscodeRoot, identity));
    for (const identityRoot of identityRoots) {
      const candidate = join(identityRoot, "history", key);
      try {
        candidates.push(await assertTrustedPath(root, candidate, "directory", "WorkBuddy workspace history"));
      } catch (error) {
        if (error?.code !== "ENOENT") {
          const message = error instanceof Error ? error.message : String(error);
          if (!/ENOENT|no such file/iu.test(message)) throw error;
        }
      }
    }
  }
  const unique = [...new Set(candidates)];
  if (unique.length !== 1) {
    throw new Error(`WORKBUDDY_HISTORY_AMBIGUOUS: expected=1 actual=${unique.length} key=${key}`);
  }
  return { root: unique[0], key };
}

function parseStoredObject(value, label) {
  const parsed = typeof value === "string" ? JSON.parse(value) : value;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${label} 不是对象`);
  return parsed;
}

function chooseExact(items, id, label) {
  const matches = (Array.isArray(items) ? items : []).filter((item) => item?.id === id);
  if (matches.length !== 1) throw new Error(`${label} 绑定不唯一：${matches.length}`);
  return matches[0];
}

async function loadConversationEvidence(dataRoot, workspace, conversationId, requestId = null) {
  assertSafeId(conversationId, "conversationId");
  if (requestId) assertSafeId(requestId, "requestId");
  const history = await findHistoryRoot(dataRoot, workspace);
  const workspaceSnapshot = await readStableJson(join(history.root, "index.json"), history.root, "workspace index");
  const conversation = chooseExact(workspaceSnapshot.value.conversations, conversationId, "conversationId");
  const conversationRoot = join(history.root, conversationId);
  await assertTrustedPath(history.root, conversationRoot, "directory", "conversation 目录");
  const indexSnapshot = await readStableJson(join(conversationRoot, "index.json"), history.root, "conversation index");
  const requests = Array.isArray(indexSnapshot.value.requests) ? indexSnapshot.value.requests : [];
  for (const request of requests) assertSafeId(request?.id, "requestId");
  if (!requestId) {
    return {
      history,
      conversation,
      requests,
      artifacts: [workspaceSnapshot.artifact, indexSnapshot.artifact],
    };
  }
  const request = chooseExact(requests, requestId, "requestId");
  const metadataById = new Map();
  for (const metadata of indexSnapshot.value.messages || []) {
    const id = assertSafeId(metadata?.id, "messageId");
    if (metadataById.has(id)) throw new Error(`messageId 重复：${id}`);
    metadataById.set(id, metadata);
  }
  if (!Array.isArray(request.messages) || request.messages.length === 0) {
    throw new Error("绑定 request 没有消息引用");
  }
  const seen = new Set();
  const messages = [];
  const artifacts = [workspaceSnapshot.artifact, indexSnapshot.artifact];
  for (const rawId of request.messages) {
    const messageId = assertSafeId(rawId, "request messageId");
    if (seen.has(messageId)) throw new Error(`request messageId 重复：${messageId}`);
    seen.add(messageId);
    const metadata = metadataById.get(messageId);
    if (!metadata) throw new Error(`request 引用了不存在的 messageId：${messageId}`);
    const snapshot = await readStableJson(
      join(conversationRoot, "messages", `${messageId}.json`),
      history.root,
      `message ${messageId}`,
    );
    const envelope = snapshot.value;
    if (envelope.id !== messageId || envelope.role !== metadata.role) {
      throw new Error(`message envelope 不匹配：${messageId}`);
    }
    const message = parseStoredObject(envelope.message, `message payload ${messageId}`);
    const extra = parseStoredObject(envelope.extra || {}, `message extra ${messageId}`);
    if (message.role !== envelope.role || (extra.requestId && extra.requestId !== requestId)) {
      throw new Error(`message request/role 不匹配：${messageId}`);
    }
    messages.push({ metadata, envelope, message, extra });
    artifacts.push(snapshot.artifact);
  }
  const missing = [];
  let prompt = null;
  let finalResponse = null;
  const calls = new Map();
  for (const item of messages) {
    if (item.metadata.isComplete !== true) missing.push(`incomplete:${item.envelope.id}`);
    const blocks = Array.isArray(item.message.content) ? item.message.content : [];
    if (blocks.length === 0) missing.push(`empty:${item.envelope.id}`);
    for (const block of blocks) {
      if (block?.type === "text" && item.message.role === "user" && prompt === null) {
        prompt = String(block.text || "");
      } else if (block?.type === "text" && item.message.role === "assistant") {
        if (String(block.text || "").trim()) finalResponse = String(block.text);
      } else if (block?.type === "tool-call" && item.message.role === "assistant") {
        const callId = assertSafeId(block.toolCallId, "toolCallId");
        const row = calls.get(callId) || { call: false, result: false };
        if (row.call) throw new Error(`toolCallId 重复：${callId}`);
        row.call = true;
        calls.set(callId, row);
      } else if (block?.type === "tool-result" && item.message.role === "tool") {
        const callId = assertSafeId(block.toolCallId, "toolResultId");
        const row = calls.get(callId) || { call: false, result: false };
        if (row.result) throw new Error(`toolResultId 重复：${callId}`);
        row.result = true;
        calls.set(callId, row);
      } else {
        missing.push(`unsupported:${item.envelope.id}:${String(block?.type || "missing")}`);
      }
    }
  }
  for (const [callId, pair] of calls) {
    if (!pair.call || !pair.result) missing.push(`tool-pair:${callId}`);
  }
  if (prompt === null) missing.push("prompt");
  if (finalResponse === null) missing.push("final_response");
  return {
    history,
    conversation,
    request,
    messages,
    artifacts,
    prompt: {
      content: prompt,
      sha256: prompt === null ? null : createHash("sha256").update(prompt).digest("hex"),
    },
    final_response: finalResponse,
    completeness: {
      status: missing.length === 0 ? "complete" : "partial",
      missing: [...new Set(missing)].sort(),
    },
  };
}

export async function snapshotWorkBuddyNativeBaseline({ sessionDb, dataRoot, workspace }, overrides = {}) {
  const result = await (overrides.querySessions || queryWorkBuddySessions)(sessionDb, overrides);
  if (result.status && result.status !== "observed") {
    throw new Error(`WorkBuddy session index 不可读：${result.error || result.status}`);
  }
  const sessions = result.sessions || [];
  const canonicalWorkspace = await realpath(resolve(workspace));
  const exact = sessions.filter((item) => resolve(String(item.cwd || "")) === canonicalWorkspace);
  const requestIds = {};
  for (const session of exact) {
    const conversationId = assertSafeId(session.conversation_id, "baseline conversationId");
    try {
      const loaded = await loadConversationEvidence(dataRoot, canonicalWorkspace, conversationId);
      requestIds[conversationId] = loaded.requests.map((item) => item.id).sort();
    } catch (error) {
      if (!/AMBIGUOUS|不存在|ENOENT|no such file/iu.test(error instanceof Error ? error.message : String(error))) {
        throw error;
      }
      requestIds[conversationId] = [];
    }
  }
  return {
    workspace: canonicalWorkspace,
    sessions: exact.map((item) => ({
      conversation_id: item.conversation_id,
      updated_at_ms: item.updated_at_ms,
      status: item.status,
    })),
    request_ids: requestIds,
  };
}

export async function selectWorkBuddyNativeBinding({
  sessionDb,
  dataRoot,
  workspace,
  baseline,
  boundConversationId = null,
  boundRequestId = null,
}, overrides = {}) {
  const query = overrides.querySessions || queryWorkBuddySessions;
  const result = await query(sessionDb, overrides);
  if (result.status && result.status !== "observed") {
    throw new Error(`WorkBuddy session index 不可读：${result.error || result.status}`);
  }
  const canonicalWorkspace = await realpath(resolve(workspace));
  const exact = (result.sessions || []).filter((item) => resolve(String(item.cwd || "")) === canonicalWorkspace);
  let candidates;
  if (boundConversationId) {
    const safe = assertSafeId(boundConversationId, "bound conversationId");
    candidates = exact.filter((item) => item.conversation_id === safe);
  } else {
    const old = new Map((baseline.sessions || []).map((item) => [item.conversation_id, Number(item.updated_at_ms || 0)]));
    candidates = exact.filter((item) => (
      !old.has(item.conversation_id)
      || Number(item.updated_at_ms || 0) > old.get(item.conversation_id)
    ));
  }
  if (candidates.length !== 1) {
    return { binding: null, ambiguous: candidates.length > 1, match_count: candidates.length };
  }
  const session = candidates[0];
  const conversationId = assertSafeId(session.conversation_id, "conversationId");
  const conversationEvidence = await loadConversationEvidence(dataRoot, canonicalWorkspace, conversationId);
  const oldRequests = new Set(baseline.request_ids?.[conversationId] || []);
  const requestCandidates = boundRequestId
    ? conversationEvidence.requests.filter((item) => item.id === assertSafeId(boundRequestId, "bound requestId"))
    : conversationEvidence.requests.filter((item) => !oldRequests.has(item.id));
  if (requestCandidates.length !== 1) {
    return { binding: null, ambiguous: requestCandidates.length > 1, match_count: requestCandidates.length };
  }
  const requestId = requestCandidates[0].id;
  const loaded = await loadConversationEvidence(dataRoot, canonicalWorkspace, conversationId, requestId);
  return {
    ambiguous: false,
    match_count: 1,
    binding: {
      session_snapshot: session,
      history: {
        binding: {
          conversation_id: conversationId,
          request_id: requestId,
          request_state: {
            raw: String(loaded.request.state || ""),
          },
          workspace_history_key: loaded.history.key,
        },
        prompt: loaded.prompt,
        completeness: loaded.completeness,
        final_response: loaded.final_response,
        request: loaded.request,
        conversation: loaded.conversation,
        resources: null,
      },
      artifacts: loaded.artifacts,
    },
  };
}
