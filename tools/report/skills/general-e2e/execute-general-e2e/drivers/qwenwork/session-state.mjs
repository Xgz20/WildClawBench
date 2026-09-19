import { access, copyFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";

export const QWENWORK_GENERAL_DRIVER_VERSION = "0.1.0";
export const QWENWORK_SESSION_QUERY = String.raw`
SELECT
  chats.id AS conversation_id,
  sub_chats.id AS sub_chat_id,
  sub_chats.session_id AS session_id,
  chats.local_project_id AS local_project_id,
  COALESCE(
    json_extract(local_projects.root_paths, '$[0]'),
    projects.path,
    chats.worktree_path
  ) AS cwd,
  CASE
    WHEN sub_chats.stream_id IS NOT NULL THEN 'running'
    WHEN json_extract(chats.ext, '$.taskStatus') IS NOT NULL
      THEN json_extract(chats.ext, '$.taskStatus')
    ELSE 'ready'
  END AS native_status,
  sub_chats.stream_id AS stream_id,
  sub_chats.model_level AS model_level,
  CASE WHEN sub_chats.updated_at < 100000000000
    THEN sub_chats.updated_at * 1000 ELSE sub_chats.updated_at END AS updated_at_ms,
  CASE WHEN sub_chats.created_at < 100000000000
    THEN sub_chats.created_at * 1000 ELSE sub_chats.created_at END AS created_at_ms
FROM sub_chats
INNER JOIN chats ON chats.id = sub_chats.chat_id
LEFT JOIN local_projects ON local_projects.id = chats.local_project_id
LEFT JOIN projects ON projects.id = chats.project_id
WHERE chats.deleted_at IS NULL
ORDER BY sub_chats.updated_at DESC, sub_chats.id ASC;
`;

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
  const session = {
    conversation_id: row?.conversation_id || null,
    sub_chat_id: row?.sub_chat_id || null,
    session_id: row?.session_id || null,
    local_project_id: row?.local_project_id || null,
    cwd: row?.cwd ? resolve(String(row.cwd)) : null,
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
  const candidates = normalized.filter((session) => {
    if (session.local_project_id !== nativeBinding.local_project_id) return false;
    const key = snapshotKey(session);
    const previous = key ? baselineMap.get(key) : null;
    if (previous != null) return Number(session.updated_at_ms || 0) > previous;
    return Number(session.updated_at_ms || session.created_at_ms || 0) >= Math.floor(sentAtMs / 1000) * 1000;
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

async function copyIfPresent(source, target) {
  try {
    await copyFile(source, target);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function defaultSqliteQuery(database, sql) {
  const result = await runCapture(
    "/usr/bin/sqlite3",
    ["-readonly", "-json", database, sql],
    { capture: true },
  );
  return result.stdout.trim() ? JSON.parse(result.stdout) : [];
}

export async function inspectQwenSessionDatabase(sessionDb, overrides = {}) {
  await access(sessionDb);
  const query = overrides.query || defaultSqliteQuery;
  const makeTemp = overrides.mkdtemp || mkdtemp;
  const remove = overrides.rm || rm;
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotRoot = await makeTemp(join(tmpdir(), "qwenwork-general-probe-"));
    const snapshotDb = join(snapshotRoot, basename(sessionDb));
    try {
      await copyFile(sessionDb, snapshotDb);
      await copyIfPresent(`${sessionDb}-wal`, `${snapshotDb}-wal`);
      await copyIfPresent(`${sessionDb}-shm`, `${snapshotDb}-shm`);
      const quickCheck = await query(snapshotDb, "PRAGMA quick_check;");
      const result = String(quickCheck[0]?.quick_check || quickCheck[0]?.integrity_check || "").trim();
      if (result !== "ok") throw new Error(`QWENWORK_DB_QUICK_CHECK_FAILED: ${result || "empty"}`);
      const rows = await query(snapshotDb, QWENWORK_SESSION_QUERY);
      return {
        readable: true,
        quick_check: "ok",
        sqlite_backend: overrides.sqliteBackend || "sqlite3-readonly-snapshot",
        ...summarizeQwenSessions(rows),
      };
    } catch (error) {
      lastError = error;
    } finally {
      await remove(snapshotRoot, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`QWENWORK_DB_SNAPSHOT_FAILED: ${lastError instanceof Error ? lastError.message : String(lastError)}`);
}
