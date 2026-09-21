import { access, copyFile, lstat, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, isAbsolute, join, resolve } from "node:path";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";

export const QWENWORK_GENERAL_DRIVER_VERSION = "0.3.0";
export const QWENWORK_SESSION_QUERY = String.raw`
SELECT
  chats.id AS conversation_id,
  sub_chats.id AS sub_chat_id,
  sub_chats.name AS sub_chat_name,
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
export const QWENWORK_PROJECT_QUERY = String.raw`
SELECT
  id AS project_id,
  name AS project_name,
  json_extract(root_paths, '$[0]') AS cwd,
  CASE WHEN updated_at < 100000000000
    THEN updated_at * 1000 ELSE updated_at END AS updated_at_ms
FROM local_projects
WHERE deleted_at IS NULL
ORDER BY updated_at DESC, id ASC;
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

async function copyIfPresent(source, target, copy = copyFile) {
  try {
    await copy(source, target);
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

function fileSignature(info) {
  if (!info) return null;
  return {
    dev: Number(info.dev || 0),
    ino: Number(info.ino || 0),
    size: Number(info.size || 0),
    mtimeMs: Number(info.mtimeMs || 0),
    mode: Number(info.mode || 0),
  };
}

function sameFileSignature(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

async function readFileSignature(path, statFile) {
  try {
    return fileSignature(await statFile(path));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

async function defaultWriterCheck(sessionDb) {
  try {
    const result = await runCapture(
      "/usr/sbin/lsof",
      ["-F", "pcfn", "--", sessionDb, `${sessionDb}-wal`, `${sessionDb}-shm`],
      { capture: true, allowFailure: true },
    );
    // lsof cannot expose SQLite's lock mode portably. Any holder is therefore
    // treated as an active/unknown writer and blocks immutable reads.
    return Boolean(String(result.stdout || "").trim());
  } catch {
    // Fail closed when the writer check itself is unavailable.
    return null;
  }
}

function immutableSqliteUri(path) {
  return `file:${encodeURI(path)}?immutable=1`;
}

async function querySnapshot(sessionDb, query, overrides = {}) {
  await access(sessionDb);
  const runQuery = overrides.query || defaultSqliteQuery;
  const makeTemp = overrides.mkdtemp || mkdtemp;
  const remove = overrides.rm || rm;
  const copy = overrides.copyFile || copyFile;
  const statFile = overrides.lstat || lstat;
  const writerCheck = overrides.writerCheck || defaultWriterCheck;
  const sidecars = [`${sessionDb}-wal`, `${sessionDb}-shm`];
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotRoot = await makeTemp(join(tmpdir(), "qwenwork-general-probe-"));
    const snapshotDb = join(snapshotRoot, basename(sessionDb));
    try {
      const before = {
        main: await readFileSignature(sessionDb, statFile),
        wal: await readFileSignature(sidecars[0], statFile),
        shm: await readFileSignature(sidecars[1], statFile),
      };
      if (!before.main) throw new Error("QWENWORK_DB_MAIN_MISSING");
      const hasSidecar = Boolean(before.wal || before.shm);
      const writer = await writerCheck(sessionDb);
      if (writer === null) throw new Error("QWENWORK_DB_WRITER_STATE_UNKNOWN");

      // Copy the main file and whatever WAL/SHM files existed in the same
      // source snapshot. Never create, remove, or checkpoint sidecars in the
      // user's database directory.
      await copy(sessionDb, snapshotDb);
      if (before.wal) await copyIfPresent(sidecars[0], `${snapshotDb}-wal`, copy);
      if (before.shm) await copyIfPresent(sidecars[1], `${snapshotDb}-shm`, copy);

      const after = {
        main: await readFileSignature(sessionDb, statFile),
        wal: await readFileSignature(sidecars[0], statFile),
        shm: await readFileSignature(sidecars[1], statFile),
      };
      if (!sameFileSignature(before.main, after.main)
        || !sameFileSignature(before.wal, after.wal)
        || !sameFileSignature(before.shm, after.shm)) {
        throw new Error("QWENWORK_DB_SNAPSHOT_SOURCE_CHANGED");
      }

      // A sidecar-free WAL main file is only safe through SQLite's immutable
      // URI after no process holds the database. Active WAL/SHM snapshots use
      // ordinary read-only mode so SQLite consumes the copied sidecars.
      if (writer) throw new Error("QWENWORK_DB_WRITER_PRESENT");
      const queryDatabase = !hasSidecar && !writer
        ? immutableSqliteUri(snapshotDb)
        : snapshotDb;
      const quickCheck = await runQuery(queryDatabase, "PRAGMA quick_check;");
      const result = String(quickCheck[0]?.quick_check || quickCheck[0]?.integrity_check || "").trim();
      if (result !== "ok") throw new Error(`QWENWORK_DB_QUICK_CHECK_FAILED: ${result || "empty"}`);
      return await runQuery(queryDatabase, query);
    } catch (error) {
      lastError = error;
    } finally {
      await remove(snapshotRoot, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`QWENWORK_DB_SNAPSHOT_FAILED: ${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

export { querySnapshot };

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
    sqlite_backend: overrides.sqliteBackend || "sqlite3-readonly-snapshot",
    ...summarizeQwenSessions(rows),
  };
}
