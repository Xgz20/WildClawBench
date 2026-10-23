import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";
import { copySnapshotFile, configureSnapshotReader } from "../../vendor/e2e-shared/sqlite-snapshot/index.mjs";
import { createHash } from "node:crypto";

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
          AND NOT COALESCE((
            -- AStudio can leave an unmapped token-usage notification in its
            -- open-turn ledger. Only discard a resource-only orphan proven
            -- older than the exact completed head; unknown/activity evidence
            -- and malformed clocks remain blocking.
            sessions.status = 'ready'
            AND latest_turn.turn_id = threads.latest_turn_id
            AND latest_turn.state = 'completed'
            AND julianday(latest_turn.completed_at) IS NOT NULL
            AND julianday(open_turn.updated_at) IS NOT NULL
            AND julianday(open_turn.updated_at) <= julianday(latest_turn.completed_at)
            AND NOT EXISTS (
              SELECT 1 FROM projection_turns AS mapped
              WHERE mapped.thread_id = open_turn.thread_id AND mapped.turn_id = open_turn.turn_id
            )
            AND EXISTS (
              SELECT 1 FROM provider_runtime_events AS usage
              WHERE usage.thread_id = open_turn.thread_id AND usage.turn_id = open_turn.turn_id
                AND usage.event_type = 'thread.token-usage.updated'
            )
            AND NOT EXISTS (
              SELECT 1 FROM provider_runtime_events AS activity
              WHERE activity.thread_id = open_turn.thread_id AND activity.turn_id = open_turn.turn_id
                AND (activity.event_type IS NULL OR activity.event_type <> 'thread.token-usage.updated'
                  OR julianday(activity.persisted_at) IS NULL
                  OR julianday(activity.persisted_at) > julianday(latest_turn.completed_at))
            )
          ), 0)
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

export const SESSION_SNAPSHOT_TABLES = Object.freeze([
  "projection_turns", "projection_threads", "projection_projects",
  "projection_thread_sessions", "projection_pending_interactions",
  "provider_runtime_open_turns", "provider_session_runtime", "provider_runtime_events",
]);
export const STATE_SNAPSHOT_TABLES = Object.freeze([
  ...SESSION_SNAPSHOT_TABLES, "projection_thread_messages",
]);

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
    await copySnapshotFile(source, destination);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

async function queryWithNodeSqlite(databasePath, sql, sqliteModule) {
  const database = new sqliteModule.DatabaseSync(databasePath, { readOnly: true });
  try {
    configureSnapshotReader(database);
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

export async function withStateSnapshot(stateDatabase, operation, overrides = {}, tables = STATE_SNAPSHOT_TABLES) {
  if (!Array.isArray(tables) || !tables.length || tables.some((table) => ![...STATE_SNAPSHOT_TABLES, "custom_model_configs"].includes(table))) {
    throw new Error("快照必须声明非空、已知的读取表范围");
  }
  const source = resolve(stateDatabase);
  const attempts = overrides.attempts || 3;
  const wait = overrides.sleep || sleep;
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const root = await mkdtemp(join(tmpdir(), "general-e2e-astudio-execute-"));
    const snapshot = join(root, "state.sqlite");
    try {
      await copySnapshotFile(source, snapshot);
      await copyIfPresent(`${source}-wal`, `${snapshot}-wal`);
      await copyIfPresent(`${source}-shm`, `${snapshot}-shm`);
      // High-frequency observations validate every complete table they read.
      // Probe and formal trace archival retain their whole-database check.
      for (const table of tables) {
        const integrityRows = await querySnapshot(snapshot, `PRAGMA quick_check("${table}");`, overrides);
        const integrity = String(Object.values(integrityRows[0] || {})[0] || "");
        if (integrityRows.length !== 1 || integrity !== "ok") throw new Error(`状态库快照 ${table} quick_check=${integrity || "empty"}`);
      }
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
    overrides, SESSION_SNAPSHOT_TABLES,
  );
}

// No credential value, credential reference, endpoint, or complete config is returned.
export async function queryCustomModelConfigurations(stateDatabase, overrides = {}) {
  return withStateSnapshot(stateDatabase, async (snapshot) => {
    const rows = await querySnapshot(snapshot, `SELECT config_id, owner_scope,
      json_extract(payload_json,'$.ownerScope') AS payload_owner_scope,
      json_extract(payload_json,'$.id') AS stored_config_id,
      json_extract(payload_json,'$.displayName') AS display_name,
      json_extract(payload_json,'$.model') AS model,
      json_extract(payload_json,'$.protocol') AS protocol,
      json_extract(payload_json,'$.defaultReasoning') AS default_reasoning,
      json_extract(payload_json,'$.reasoningMode') AS reasoning_mode,
      json_extract(payload_json,'$.executionRevision') AS execution_revision,
      json_extract(payload_json,'$.lifecycle') AS lifecycle,
      json_extract(payload_json,'$.credentialRef') IS NOT NULL AS has_credential,
      json_extract(payload_json,'$.lastTest.revision') AS test_revision,
      json_extract(payload_json,'$.lastTest.status') AS test_status,
      json_extract(payload_json,'$.lastTest.httpStatus') AS test_http_status,
      json_extract(payload_json,'$.lastTest.requestedReasoning') AS test_reasoning
      FROM custom_model_configs;`, overrides);
    return rows.map(row => {
      if (row.stored_config_id !== row.config_id || row.owner_scope !== row.payload_owner_scope) {
        throw new Error("CUSTOM_CONFIG_STORED_IDENTITY_MISMATCH");
      }
      const { owner_scope, payload_owner_scope, stored_config_id, test_revision,
        test_status, test_http_status, test_reasoning, ...publicFields } = row;
      return { ...publicFields,
        owner_scope_sha256: createHash("sha256").update(owner_scope).digest("hex"),
        last_test: { revision: test_revision, status: test_status,
          httpStatus: test_http_status, requestedReasoning: test_reasoning } };
    });
  }, overrides, ["custom_model_configs"]);
}

export async function queryNativeCustomModelBinding(stateDatabase, threadId, overrides = {}) {
  return withStateSnapshot(stateDatabase, async (snapshot) => {
    const rows = await querySnapshot(snapshot, `SELECT threads.model_selection_json,
      runtime.resume_cursor_json FROM projection_threads AS threads
      JOIN provider_session_runtime AS runtime ON runtime.thread_id = threads.thread_id
      WHERE threads.thread_id = ${sqlString(threadId)} AND threads.deleted_at IS NULL;`, overrides);
    if (rows.length !== 1) throw new Error("NATIVE_CUSTOM_BINDING_NOT_UNIQUE");
    const selection = JSON.parse(rows[0].model_selection_json);
    const raw = JSON.parse(rows[0].resume_cursor_json)?.customModelBinding;
    if (!raw) throw new Error("NATIVE_CUSTOM_BINDING_MISSING");
    return { selection: { provider: selection.provider, model: selection.model,
      options: { reasoningEffort: selection.options?.reasoningEffort },
      customModel: { configId: selection.customModel?.configId,
        executionRevision: selection.customModel?.executionRevision } },
    binding: { configId: raw.configId, revision: raw.revision, kernelProviderId: raw.kernelProviderId,
      model: raw.model, effort: raw.effort, protocol: raw.protocol,
      ownerScopeSha256: createHash("sha256").update(String(raw.ownerScope || "")).digest("hex") } };
  }, overrides, ["projection_threads", "provider_session_runtime"]);
}

export async function queryPristineThread(stateDatabase, threadId, overrides = {}) {
  const rows = await withStateSnapshot(stateDatabase, (snapshot) => querySnapshot(snapshot, `
SELECT threads.thread_id, threads.latest_turn_id,
  (SELECT COUNT(*) FROM projection_thread_messages WHERE thread_id = threads.thread_id) AS message_count,
  (SELECT COUNT(*) FROM projection_turns WHERE thread_id = threads.thread_id) AS turn_count,
  (SELECT COUNT(*) FROM projection_thread_sessions WHERE thread_id = threads.thread_id) AS session_count,
  (SELECT COUNT(*) FROM projection_pending_interactions WHERE thread_id = threads.thread_id AND status = 'pending') AS pending_count
FROM projection_threads AS threads
WHERE threads.thread_id = ${sqlString(threadId)} AND threads.deleted_at IS NULL;
`, overrides), overrides, ["projection_threads", "projection_thread_messages", "projection_turns",
    "projection_thread_sessions", "projection_pending_interactions"]);
  return rows.length === 1 && rows[0].latest_turn_id === null
    && ["message_count", "turn_count", "session_count", "pending_count"].every((key) => rows[0][key] === 0);
}

export async function queryExactProjectsForWorkspace(stateDatabase, workspace, overrides = {}) {
  return withStateSnapshot(stateDatabase, (snapshot) => querySnapshot(snapshot, `
SELECT project_id, workspace_root
FROM projection_projects
WHERE workspace_root = ${sqlString(workspace)} AND deleted_at IS NULL;
`, overrides), overrides, ["projection_projects"]);
}

export async function queryProjectForThread(stateDatabase, threadId, overrides = {}) {
  return withStateSnapshot(stateDatabase, (snapshot) => querySnapshot(snapshot, `
SELECT projects.project_id, projects.workspace_root
FROM projection_threads AS threads
JOIN projection_projects AS projects ON projects.project_id = threads.project_id
WHERE threads.thread_id = ${sqlString(threadId)}
  AND threads.deleted_at IS NULL AND projects.deleted_at IS NULL;
`, overrides), overrides, ["projection_threads", "projection_projects"]);
}

export async function queryTerminalFinalResponse(stateDatabase, threadId, turnId, overrides = {}) {
  if (!threadId || !turnId) return { ready: false, text: "", reason: "missing_identity" };
  return withStateSnapshot(stateDatabase, async (snapshot) => {
    const rows = await querySnapshot(snapshot, `
SELECT turns.assistant_message_id AS terminal_message_id,
  messages.message_id, messages.text, messages.role, messages.is_streaming
FROM projection_turns AS turns
LEFT JOIN projection_thread_messages AS messages
  ON messages.message_id = turns.assistant_message_id
  AND messages.thread_id = turns.thread_id AND messages.turn_id = turns.turn_id
WHERE turns.thread_id = ${sqlString(threadId)}
  AND turns.turn_id = ${sqlString(turnId)} AND turns.state = 'completed'
  AND turns.checkpoint_turn_count IS NULL;
`, overrides);
    const row = rows[0];
    if (rows.length !== 1 || typeof row?.terminal_message_id !== "string"
      || !row.terminal_message_id || row.message_id !== row.terminal_message_id
      || row.role !== "assistant" || row.is_streaming !== 0 || typeof row.text !== "string") {
      return { ready: false, text: "", reason: "bound_terminal_message_not_materialized" };
    }
    return { ready: true, text: row.text.trim(), message_id: row.message_id,
      source: "completed-turn.assistant_message_id" };
  }, overrides, ["projection_turns", "projection_thread_messages"]);
}

export async function queryFinalResponse(stateDatabase, threadId, turnId, overrides = {}) {
  return (await queryTerminalFinalResponse(stateDatabase, threadId, turnId, overrides)).text;
}

export async function readPrompt(path) {
  return readFile(path, "utf8");
}
