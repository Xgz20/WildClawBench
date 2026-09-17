import { copyFile, mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";

const SESSION_QUERY = `
WITH latest_turn AS (
  SELECT ranked.*
  FROM (
    SELECT
      turns.*,
      ROW_NUMBER() OVER (
        PARTITION BY turns.thread_id
        ORDER BY
          CASE WHEN turns.turn_id = threads.latest_turn_id THEN 0 ELSE 1 END,
          turns.requested_at DESC,
          turns.row_id DESC
      ) AS row_rank
    FROM projection_turns AS turns
    INNER JOIN projection_threads AS threads ON threads.thread_id = turns.thread_id
    WHERE turns.checkpoint_turn_count IS NULL
  ) AS ranked
  WHERE ranked.row_rank = 1
)
SELECT
  sessions.thread_id AS thread_id,
  projects.workspace_root AS cwd,
  threads.latest_turn_id AS latest_turn_id,
  latest_turn.turn_id AS turn_id,
  latest_turn.state AS turn_state,
  latest_turn.termination_origin AS termination_origin,
  latest_turn.requested_at AS requested_at,
  latest_turn.started_at AS started_at,
  latest_turn.completed_at AS completed_at,
  sessions.status AS session_status,
  sessions.active_turn_id AS active_turn_id,
  sessions.last_error AS last_error,
  sessions.updated_at AS session_updated_at,
  runtime.resume_cursor_json AS resume_cursor_json,
  CASE
    WHEN EXISTS (
      SELECT 1 FROM projection_pending_interactions AS pending
      WHERE pending.thread_id = sessions.thread_id AND pending.status = 'pending'
    ) THEN 'needs_attention'
    WHEN sessions.active_turn_id IS NOT NULL
      OR sessions.status IN ('starting', 'running')
      OR EXISTS (
        SELECT 1 FROM provider_runtime_open_turns AS open_turn
        WHERE open_turn.thread_id = sessions.thread_id
      ) THEN 'running'
    WHEN latest_turn.state IS NOT NULL THEN latest_turn.state
    ELSE sessions.status
  END AS status
FROM projection_thread_sessions AS sessions
INNER JOIN projection_threads AS threads ON threads.thread_id = sessions.thread_id
INNER JOIN projection_projects AS projects ON projects.project_id = threads.project_id
LEFT JOIN latest_turn ON latest_turn.thread_id = sessions.thread_id
LEFT JOIN provider_session_runtime AS runtime ON runtime.thread_id = sessions.thread_id
WHERE threads.deleted_at IS NULL AND projects.deleted_at IS NULL
ORDER BY COALESCE(
  latest_turn.completed_at,
  latest_turn.started_at,
  latest_turn.requested_at,
  sessions.updated_at
) DESC, sessions.thread_id ASC;
`;

let sqliteModulePromise;

async function loadNodeSqlite() {
  if (!sqliteModulePromise) sqliteModulePromise = import("node:sqlite").catch(() => null);
  return sqliteModulePromise;
}

function sqlString(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

async function copyIfPresent(source, destination) {
  try {
    await copyFile(source, destination);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

async function queryWithNodeSqlite(databasePath, sql, sqliteModule) {
  const database = new sqliteModule.DatabaseSync(databasePath, { readOnly: true });
  try {
    return database.prepare(sql).all();
  } finally {
    database.close();
  }
}

async function queryWithCli(databasePath, sql, runCommand = runCapture) {
  const result = await runCommand(
    "/usr/bin/sqlite3",
    ["-readonly", "-json", databasePath, sql],
    { capture: true, allowFailure: false },
  );
  return result.stdout.trim() ? JSON.parse(result.stdout) : [];
}

async function querySnapshot(databasePath, sql, overrides = {}) {
  const sqliteModule = await (overrides.loadNodeSqlite || loadNodeSqlite)();
  if (typeof sqliteModule?.DatabaseSync === "function") {
    return queryWithNodeSqlite(databasePath, sql, sqliteModule);
  }
  return queryWithCli(databasePath, sql, overrides.runCommand || runCapture);
}

export async function withStateSnapshot(stateDatabase, operation, overrides = {}) {
  const source = resolve(stateDatabase);
  const attempts = overrides.attempts || 3;
  const wait = overrides.sleep || sleep;
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const root = await mkdtemp(join(tmpdir(), "general-e2e-astudio-execute-"));
    const snapshot = join(root, "state.sqlite");
    try {
      await copyFile(source, snapshot);
      await copyIfPresent(`${source}-wal`, `${snapshot}-wal`);
      await copyIfPresent(`${source}-shm`, `${snapshot}-shm`);
      const integrityRows = await querySnapshot(snapshot, "PRAGMA quick_check;", overrides);
      const integrity = String(Object.values(integrityRows[0] || {})[0] || "");
      if (integrity !== "ok") throw new Error(`状态库快照 quick_check=${integrity || "empty"}`);
      return await operation(snapshot, overrides);
    } catch (error) {
      lastError = error;
    } finally {
      await rm(root, { recursive: true, force: true }).catch(() => {});
    }
    if (attempt < attempts) await wait(100 * attempt);
  }
  throw new Error(
    `读取 AstronStudio 状态库快照失败：${lastError instanceof Error ? lastError.message : String(lastError)}`,
  );
}

function parseSessionId(cursor) {
  if (typeof cursor !== "string" || !cursor.trim()) return null;
  try {
    const value = JSON.parse(cursor);
    return typeof value?.threadId === "string" && value.threadId.trim()
      ? value.threadId.trim()
      : null;
  } catch {
    return null;
  }
}

function timestampMilliseconds(...values) {
  for (const value of values) {
    const parsed = Date.parse(String(value || ""));
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

export function normalizeNativeSession(row) {
  return {
    thread_id: typeof row?.thread_id === "string" ? row.thread_id : null,
    turn_id: typeof row?.turn_id === "string" ? row.turn_id : null,
    latest_turn_id: typeof row?.latest_turn_id === "string" ? row.latest_turn_id : null,
    session_id: parseSessionId(row?.resume_cursor_json),
    cwd: typeof row?.cwd === "string" ? resolve(row.cwd) : null,
    status: typeof row?.status === "string" ? row.status : null,
    turn_state: typeof row?.turn_state === "string" ? row.turn_state : null,
    session_status: typeof row?.session_status === "string" ? row.session_status : null,
    active_turn_id: typeof row?.active_turn_id === "string" ? row.active_turn_id : null,
    termination_origin: typeof row?.termination_origin === "string" ? row.termination_origin : null,
    requested_at: typeof row?.requested_at === "string" ? row.requested_at : null,
    started_at: typeof row?.started_at === "string" ? row.started_at : null,
    completed_at: typeof row?.completed_at === "string" ? row.completed_at : null,
    updated_at: typeof row?.session_updated_at === "string" ? row.session_updated_at : null,
    updated_at_ms: timestampMilliseconds(
      row?.completed_at,
      row?.started_at,
      row?.requested_at,
      row?.session_updated_at,
    ),
    error: typeof row?.last_error === "string" && row.last_error.trim()
      ? row.last_error.trim()
      : null,
  };
}

export async function queryNativeSessions(stateDatabase, overrides = {}) {
  return withStateSnapshot(
    stateDatabase,
    async (snapshot) => (await querySnapshot(snapshot, SESSION_QUERY, overrides))
      .map(normalizeNativeSession),
    overrides,
  );
}

export async function queryFinalResponse(stateDatabase, threadId, turnId, overrides = {}) {
  if (!threadId || !turnId) return "";
  return withStateSnapshot(stateDatabase, async (snapshot) => {
    const rows = await querySnapshot(snapshot, `
SELECT text
FROM projection_thread_messages
WHERE thread_id = ${sqlString(threadId)}
  AND turn_id = ${sqlString(turnId)}
  AND role = 'assistant'
  AND is_streaming = 0
  AND trim(text) <> ''
ORDER BY sequence DESC, updated_at DESC, message_id DESC
LIMIT 1;
`, overrides);
    return typeof rows[0]?.text === "string" ? rows[0].text.trim() : "";
  }, overrides);
}

export async function readPrompt(path) {
  return readFile(path, "utf8");
}
