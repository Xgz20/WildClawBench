import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { runCapture } from "../desktop-runtime/process.mjs";
import { copySnapshotFile, configureSnapshotReader } from "../sqlite-snapshot/index.mjs";
import { createHash } from "node:crypto";
import {closedStructuredGatewayLedger} from './structured-ledger.mjs';

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
LEFT JOIN projection_projects AS projects ON projects.project_id = threads.project_id
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
export const START_REJECTION_TABLES = Object.freeze([
  "orchestration_events", "orchestration_command_receipts", "orchestration_event_deliveries",
  "queued_turn_promotions",
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
    return await copySnapshotFile(source, destination);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
    return null;
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

export async function querySnapshot(databasePath, sql, overrides = {}) {
  const sqliteModule = await (overrides.loadNodeSqlite || loadNodeSqlite)();
  if (typeof sqliteModule?.DatabaseSync === "function") {
    return queryWithNodeSqlite(databasePath, sql, sqliteModule);
  }
  return queryWithCli(databasePath, sql, overrides.runCommand || runCapture);
}

export async function withStateSnapshot(stateDatabase, operation, overrides = {}, tables = STATE_SNAPSHOT_TABLES) {
  if (!Array.isArray(tables) || !tables.length || tables.some((table) => ![...STATE_SNAPSHOT_TABLES, ...START_REJECTION_TABLES, "custom_model_configs"].includes(table))) {
    throw new Error("快照必须声明非空、已知的读取表范围");
  }
  const source = resolve(stateDatabase);
  const attempts = overrides.attempts || 3;
  const wait = overrides.sleep || sleep;
  const startedAt = new Date().toISOString();
  const monotonicNs = process.hrtime.bigint().toString();
  const retries = [];
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    let root;
    let stage = "create_snapshot";
    const started = performance.now();
    const metrics = { snapshot_started_at: startedAt, snapshot_monotonic_ns: monotonicNs,
      snapshot_attempt: attempt, snapshot_retries: retries };
    try {
      root = await mkdtemp(join(tmpdir(), "general-e2e-astudio-execute-"));
      const snapshot = join(root, "state.sqlite");
      const copyStarted = performance.now();
      stage = "copy_main";
      const copy = await copySnapshotFile(source, snapshot);
      metrics.copy_method = copy.method;
      metrics.sqlite_main_bytes = (await stat(snapshot)).size;
      stage = "copy_wal";
      const wal = await copyIfPresent(`${source}-wal`, `${snapshot}-wal`);
      metrics.sqlite_wal_bytes = wal ? (await stat(`${snapshot}-wal`)).size : null;
      stage = "copy_shm";
      await copyIfPresent(`${source}-shm`, `${snapshot}-shm`);
      metrics.copy_ms = performance.now() - copyStarted;
      const checkStarted = performance.now();
      stage = "quick_check";
      // High-frequency observations validate every complete table they read.
      // Probe and formal trace archival retain their whole-database check.
      for (const table of tables) {
        const integrityRows = await querySnapshot(snapshot, `PRAGMA quick_check("${table}");`, overrides);
        const integrity = String(Object.values(integrityRows[0] || {})[0] || "");
        if (integrityRows.length !== 1 || integrity !== "ok") throw new Error(`状态库快照 ${table} quick_check=${integrity || "empty"}`);
      }
      metrics.quick_check_ms = performance.now() - checkStarted;
      stage = "query";
      return await operation(snapshot, overrides, metrics);
    } catch (error) {
      lastError = error;
      const { snapshot_retries, ...partial } = metrics;
      retries.push({ ...partial, stage, elapsed_ms: performance.now() - started,
        error_code: error?.code ?? error?.name ?? null, reason: String(error?.message ?? error).slice(0, 256) });
    } finally {
      if (root) await rm(root, { recursive: true, force: true }).catch(() => {});
    }
    if (attempt < attempts) await wait(100 * attempt);
  }
  const error = new Error(
    `读取 AstronStudio 状态库快照失败：${lastError instanceof Error ? lastError.message : String(lastError)}`,
  );
  error.snapshot_metrics = { snapshot_started_at: startedAt, snapshot_monotonic_ns: monotonicNs, snapshot_retries: retries };
  throw error;
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

async function readNativeSessionsSnapshot(snapshot, overrides) {
      const sessions=(await querySnapshot(snapshot, SESSION_QUERY, overrides)).map(normalizeNativeSession);
      for(const session of sessions) {
        if(session.status!=='running'||session.active_turn_id||!['completed','error','interrupted'].includes(session.turn_state)
          ||!['ready','error','interrupted'].includes(session.session_status)) continue;
        const key=sqlString(session.thread_id),turn=sqlString(session.turn_id);
        const runtime=await querySnapshot(snapshot,`SELECT * FROM provider_session_runtime WHERE thread_id=${key}`,overrides);
        if(runtime.length!==1||runtime[0].status!=='stopped') continue;
        const ledger=await querySnapshot(snapshot,`SELECT * FROM provider_runtime_open_turns WHERE thread_id=${key}`,overrides);
        const events=await querySnapshot(snapshot,`SELECT * FROM provider_runtime_events WHERE thread_id=${key} AND turn_id=${turn} ORDER BY sequence`,overrides);
        const proof=closedMetricTail(session,runtime[0],ledger,events);
        if(proof){session.status=session.turn_state;session.closed_metric_tail=proof;}
      }
      return sessions;
}

export async function queryNativeSessions(stateDatabase, overrides = {}) {
  return withStateSnapshot(stateDatabase,
    snapshot => readNativeSessionsSnapshot(snapshot, overrides), overrides, SESSION_SNAPSHOT_TABLES);
}

export async function withQueueObservationSnapshot(stateDatabase, observe, overrides = {}) {
  const source = resolve(stateDatabase);
  const outcome = await withStateSnapshot(source, async (snapshot, _options, metrics) => {
    const started = performance.now();
    const sessions = await readNativeSessionsSnapshot(snapshot, overrides);
    metrics.sessions_query_ms = performance.now() - started;
    let messagesVerified;
    const assertSource = path => {
      if (resolve(path) !== source) throw Error("ASTUDIO_OBSERVATION_SNAPSHOT_SOURCE_MISMATCH");
    };
    // Snapshot retries must never replay observers that already wrote task state.
    try {
      const result = await observe({
        queryNativeSessions: async path => {
          assertSource(path);
          return sessions;
        },
        queryTerminalFinalResponse: async (path, threadId, turnId) => {
          assertSource(path);
          messagesVerified ??= (async () => {
            const checkStarted = performance.now();
            const rows = await querySnapshot(snapshot, 'PRAGMA quick_check("projection_thread_messages");', overrides);
            metrics.messages_check_ms = performance.now() - checkStarted;
            if (rows.length !== 1 || Object.values(rows[0])[0] !== "ok") {
              throw Error("ASTUDIO_OBSERVATION_SNAPSHOT_MESSAGES_INVALID");
            }
          })();
          await messagesVerified;
          const queryStarted = performance.now();
          try {
            return await readTerminalFinalResponseSnapshot(snapshot, threadId, turnId, overrides);
          } finally {
            metrics.final_query_ms = (metrics.final_query_ms ?? 0) + performance.now() - queryStarted;
          }
        },
      }, metrics, snapshot);
      return { result };
    } catch (error) {
      return { error };
    }
  }, overrides, SESSION_SNAPSHOT_TABLES);
  if ("error" in outcome) throw outcome.error;
  return outcome.result;
}

export async function queryNativeRuntimeSafety(stateDatabase, overrides = {}) {
  return withStateSnapshot(stateDatabase, async snapshot => {
    const sessions = await readNativeSessionsSnapshot(snapshot, overrides);
    // The normal session view deliberately omits deleted/missing projects.
    // Such an omission must not turn an orphan native writer into idle proof.
    const orphanSessions = await querySnapshot(snapshot, `
      SELECT s.thread_id, s.status, s.active_turn_id
      FROM projection_thread_sessions s
      LEFT JOIN projection_threads t ON t.thread_id=s.thread_id
      LEFT JOIN projection_projects p ON p.project_id=t.project_id
      WHERE (t.thread_id IS NULL OR t.deleted_at IS NOT NULL
        OR p.project_id IS NULL OR p.deleted_at IS NOT NULL)
        AND (s.active_turn_id IS NOT NULL OR s.status IN ('starting','running'))`, overrides);
    const pending = await querySnapshot(snapshot, `
      SELECT thread_id, COUNT(*) AS pending_count
      FROM projection_pending_interactions WHERE status='pending' GROUP BY thread_id`, overrides);
    const orphanRows = await querySnapshot(snapshot, `
      SELECT o.* FROM provider_runtime_open_turns o
      LEFT JOIN projection_thread_sessions s ON s.thread_id=o.thread_id
      LEFT JOIN projection_threads t ON t.thread_id=o.thread_id
      LEFT JOIN projection_projects p ON p.project_id=t.project_id
      WHERE s.thread_id IS NULL OR t.thread_id IS NULL OR t.deleted_at IS NOT NULL
        OR p.project_id IS NULL OR p.deleted_at IS NOT NULL`, overrides);
    const orphanTurns = [], settledLedgers = [];
    for (const row of orphanRows) {
      let proof = null;
      if (String(row.thread_id).startsWith('structured-')) {
        const key = sqlString(row.thread_id);
        const anchors = {};
        for (const [name, table] of [['threads','projection_threads'],['sessions','projection_thread_sessions'],
          ['runtime','provider_session_runtime'],['pending','projection_pending_interactions']]) {
          anchors[name] = (await querySnapshot(snapshot, `SELECT COUNT(*) AS n FROM ${table} WHERE thread_id=${key}`, overrides))[0]?.n;
        }
        const events = await querySnapshot(snapshot, `SELECT * FROM provider_runtime_events WHERE thread_id=${key} ORDER BY sequence`, overrides);
        proof = closedStructuredGatewayLedger(row, events, anchors);
      }
      if (proof) settledLedgers.push(proof);
      else orphanTurns.push({thread_id:row.thread_id, turn_id:row.turn_id});
    }
    return { sessions, orphan_sessions: orphanSessions, pending_interactions: pending, orphan_turns: orphanTurns,
      settled_structured_ledgers: settledLedgers };
  }, overrides, SESSION_SNAPSHOT_TABLES);
}

export function closedMetricTail(session,runtime,ledgers,events) {
  try {
    const cursor=JSON.parse(runtime.resume_cursor_json),payload=JSON.parse(runtime.runtime_payload_json);
    const end=Date.parse(session.completed_at);
    if(session.active_turn_id||session.latest_turn_id!==session.turn_id||runtime.status!=='stopped'
      ||cursor.threadId!==session.session_id||payload.activeTurnId!==null
      ||!(payload.lastRuntimeEvent==='turn.completed'&&Date.parse(payload.lastRuntimeEventAt)===end
        ||payload.lastRuntimeEvent==='provider.stopRuntimeSession'&&Date.parse(payload.lastRuntimeEventAt)>=end)
      ||!Number.isFinite(end)||!ledgers.length) return null;
    const accepted=[];
    for(const ledger of ledgers){
      const updated=Date.parse(ledger.updated_at),first=ledger.first_sequence;
      if(ledger.turn_id!==session.turn_id||!Number.isSafeInteger(first)||first<=0||!Number.isFinite(updated))return null;
      const tail=events.filter(row=>row.sequence>=first);
      if(!tail.length)return null;
      const ends=events.filter(row=>row.event_type==='turn.completed');
      for(const row of ends.length?tail:events){
        const e=JSON.parse(row.event_json),at=Date.parse(e.createdAt),persisted=Date.parse(row.persisted_at);
        if(!['thread.token-usage.updated','turn.gateway-usage.updated'].includes(row.event_type)
          ||e.type!==row.event_type||e.provider!=='acode'||e.threadId!==session.thread_id||e.turnId!==session.turn_id
          ||e.providerRefs?.providerThreadId!==session.session_id||e.providerRefs?.providerTurnId!==session.turn_id
          ||!Number.isFinite(at)||!Number.isFinite(persisted)||(row.sequence>=first&&at<end)||persisted<at||persisted>updated)return null;
        if(e.raw?.source!=='acode')return null;
        if(row.event_type==='turn.gateway-usage.updated'&&(e.raw.method!=='turn.gateway-usage.updated'
          ||e.payload?.complete!==true||!Array.isArray(e.payload.requests)))return null;
        if(row.event_type==='thread.token-usage.updated'&&e.raw.method!=='thread/tokenUsage/updated')return null;
        if(row.sequence>=first)accepted.push(row.sequence);
      }
      if(ends.length>1||ends.length===1&&ends[0].sequence>=first)return null;
      if(ends.length){
        const e=JSON.parse(ends[0].event_json);
        if(e.threadId!==session.thread_id||e.turnId!==session.turn_id
          ||e.providerRefs?.providerThreadId!==session.session_id||e.providerRefs?.providerTurnId!==session.turn_id
          ||e.raw?.payload?.threadId!==session.session_id||e.raw.payload.turn?.id!==session.turn_id
          ||!['completed','interrupted','failed','error'].includes(e.raw.payload.turn.status)
          ||e.payload?.state!==(session.turn_state==='error'?'failed':session.turn_state)
          ||Date.parse(e.createdAt)!==end)return null;
      }
      // Consumed provider events may have been pruned. Only a fully typed
      // metric remainder, alongside the exact SQL/runtime terminal, qualifies.
    }
    return {profile:'closed-native-metric-tail/v1',turn_id:session.turn_id,
      provider_session_id:session.session_id,metric_sequences:[...new Set(accepted)],
      native_terminal_preserved:true,raw_rows_deleted:false};
  }catch{return null;}
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

async function readTerminalFinalResponseSnapshot(snapshot, threadId, turnId, overrides) {
  if (!threadId || !turnId) return { ready: false, text: "", reason: "missing_identity" };
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
}

export async function queryTerminalFinalResponse(stateDatabase, threadId, turnId, overrides = {}) {
  if (!threadId || !turnId) return { ready: false, text: "", reason: "missing_identity" };
  return withStateSnapshot(stateDatabase,
    snapshot => readTerminalFinalResponseSnapshot(snapshot, threadId, turnId, overrides),
    overrides, ["projection_turns", "projection_thread_messages"]);
}

export async function queryFinalResponse(stateDatabase, threadId, turnId, overrides = {}) {
  return (await queryTerminalFinalResponse(stateDatabase, threadId, turnId, overrides)).text;
}

export async function readPrompt(path) {
  return readFile(path, "utf8");
}
