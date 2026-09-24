import { isAbsolute, join, resolve } from "node:path";

import { querySnapshot, QWENWORK_SESSION_QUERY, QWENWORK_PROJECT_QUERY } from "../../vendor/e2e-shared/qwenwork-native-state/index.mjs";
export { querySnapshot, QWENWORK_SESSION_QUERY, QWENWORK_PROJECT_QUERY };

export const QWENWORK_GENERAL_DRIVER_VERSION = "0.3.12";
export function defaultQwenWorkSessionDatabase(home = process.env.HOME) {
  if (!home) throw new Error("QWENWORK_HOME_UNAVAILABLE");
  return join(home, "Library", "Application Support", "QwenWorkCN", "data", "agents.db");
}

export function classifyQwenSessionStatus(rawStatus, streamId = null) {
  if (streamId) return { kind: "running", business_status: "running", native_status: String(rawStatus || "running") };
  const nativeStatus = String(rawStatus || "").trim();
  const normalized = nativeStatus.toLowerCase().replace(/[\s_-]+/gu, "");
  if (["completed", "complete", "succeeded", "success", "finished", "done"].includes(normalized)) {
    return { kind: "terminal", business_status: "completed", native_status: nativeStatus };
  }
  if (["failed", "failure", "error", "errored"].includes(normalized)) {
    return { kind: "terminal", business_status: "execution_error", native_status: nativeStatus };
  }
  if (["cancelled", "canceled", "aborted", "terminated", "stopped"].includes(normalized)) {
    return { kind: "terminal", business_status: "cancelled", native_status: nativeStatus };
  }
  if (["interrupted"].includes(normalized)) {
    return { kind: "terminal", business_status: "interrupted", native_status: nativeStatus };
  }
  if (["running", "working", "inprogress", "pending", "active", "streaming", "processing", "executing", "started", "starting", "queued"].includes(normalized)) {
    return { kind: "running", business_status: "running", native_status: nativeStatus };
  }
  return {
    kind: nativeStatus ? "unknown" : "missing",
    business_status: null,
    native_status: nativeStatus || null,
  };
}

function normalizeSession(row) {
  const rawCwd = typeof row?.cwd === "string" ? row.cwd.trim() : "";
  const session = {
    conversation_id: row?.conversation_id || null,
    sub_chat_id: row?.sub_chat_id || null,
    sub_chat_name: row?.sub_chat_name || null,
    session_id: row?.session_id || null,
    local_project_id: row?.local_project_id || null,
    cwd: rawCwd && isAbsolute(rawCwd) ? resolve(rawCwd) : null,
    native_status: row?.native_status || null,
    stream_id: row?.stream_id || null,
    model_level: row?.model_level || null,
    updated_at_ms: Number.isSafeInteger(Number(row?.updated_at_ms)) ? Number(row.updated_at_ms) : null,
    created_at_ms: Number.isSafeInteger(Number(row?.created_at_ms)) ? Number(row.created_at_ms) : null,
  };
  return { ...session, classification: classifyQwenSessionStatus(session.native_status, session.stream_id) };
}

function snapshotKey(session) {
  return [session.session_id, session.sub_chat_id, session.conversation_id].find(Boolean) || null;
}

export function selectQwenSessionForAttempt({
  sessions,
  workspace,
  nativeBinding = {},
  baseline = [],
  sentAt = null,
}) {
  if (!Array.isArray(sessions)) throw new TypeError("sessions must be an array");
  const expectedWorkspace = resolve(workspace);
  const normalized = sessions.map(normalizeSession).filter((session) => session.cwd === expectedWorkspace);
  const nativeFields = ["session_id", "sub_chat_id", "conversation_id"];
  const specified = nativeFields.filter((field) => nativeBinding[field]);
  if (specified.length) {
    const matches = normalized.filter((session) => specified.every((field) => session[field] === nativeBinding[field]));
    if (matches.length > 1) throw new Error("QWENWORK_SESSION_BINDING_AMBIGUOUS");
    return matches[0] || null;
  }

  // A new send may be discovered only inside an already captured exact local
  // project. Workspace+recency alone is not a stable identity.
  if (!nativeBinding.local_project_id) return null;
  const baselineMap = new Map(baseline.map((entry) => [
    entry.session_id || entry.sub_chat_id || entry.conversation_id,
    Number(entry.updated_at_ms || 0),
  ]).filter(([key]) => key));
  const sentAtMs = sentAt ? Date.parse(sentAt) : 0;
  if (!Number.isFinite(sentAtMs) || sentAtMs <= 0) return null;
  const candidates = normalized.filter((session) => {
    if (session.local_project_id !== nativeBinding.local_project_id) return false;
    const key = snapshotKey(session);
    const previous = key ? baselineMap.get(key) : null;
    // Updating an old conversation after dispatch is not proof that it belongs
    // to this attempt. Fresh binding accepts only a stable native identity that
    // was absent from the complete pre-send baseline.
    if (previous != null) return false;
    return Number(session.created_at_ms || 0) >= Math.floor(sentAtMs / 1000) * 1000;
  });
  if (candidates.length > 1) throw new Error("QWENWORK_NEW_SESSION_AMBIGUOUS");
  return candidates[0] || null;
}

export function summarizeQwenSessions(rows) {
  const sessions = rows.map(normalizeSession);
  const nativeStatuses = {};
  const businessStatuses = {};
  for (const session of sessions) {
    const native = session.native_status || "<missing>";
    nativeStatuses[native] = (nativeStatuses[native] || 0) + 1;
    const business = session.classification.business_status || "unknown";
    businessStatuses[business] = (businessStatuses[business] || 0) + 1;
  }
  return {
    session_count: sessions.length,
    active_or_pending_count: sessions.filter((session) => session.classification.kind === "running").length,
    stable_identity_coverage: {
      session_id: sessions.filter((session) => session.session_id).length,
      conversation_id: sessions.filter((session) => session.conversation_id).length,
      sub_chat_id: sessions.filter((session) => session.sub_chat_id).length,
      local_project_id: sessions.filter((session) => session.local_project_id).length,
      cwd: sessions.filter((session) => session.cwd).length,
    },
    native_status_counts: nativeStatuses,
    business_status_counts: businessStatuses,
  };
}

export function buildQwenGeneralSessionBinding(session, bindingEvidence) {
  const normalized = normalizeSession(session);
  const evidence = Array.isArray(bindingEvidence) ? bindingEvidence : [];
  const verified = Boolean(normalized.session_id && normalized.cwd && evidence.length);
  return {
    thread_id: null,
    turn_id: null,
    session_id: normalized.session_id,
    cwd: normalized.cwd,
    verified,
    binding_evidence: evidence,
  };
}

export async function queryQwenSessionRows(sessionDb, overrides = {}) {
  const rows = await querySnapshot(sessionDb, QWENWORK_SESSION_QUERY, overrides);
  return rows.map(normalizeSession);
}

export async function queryQwenProjectRows(sessionDb, overrides = {}) {
  const rows = await querySnapshot(sessionDb, QWENWORK_PROJECT_QUERY, overrides);
  return rows.map((row) => {
    const rawCwd = typeof row?.cwd === "string" ? row.cwd.trim() : "";
    return {
      project_id: row?.project_id || null,
      project_name: row?.project_name || null,
      cwd: rawCwd && isAbsolute(rawCwd) ? resolve(rawCwd) : null,
      updated_at_ms: Number.isFinite(Number(row?.updated_at_ms)) ? Number(row.updated_at_ms) : null,
    };
  });
}

export async function inspectQwenSessionDatabase(sessionDb, overrides = {}) {
  const rows = await querySnapshot(sessionDb, QWENWORK_SESSION_QUERY, overrides);
  return {
    readable: true,
    quick_check: "ok",
    sqlite_backend: overrides.sqliteBackend || (overrides.consistentOnlineBackup
      ? "sqlite3-online-backup"
      : "sqlite3-readonly-snapshot"),
    ...summarizeQwenSessions(rows),
  };
}
