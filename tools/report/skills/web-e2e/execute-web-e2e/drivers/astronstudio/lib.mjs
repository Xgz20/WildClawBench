import { spawn } from "node:child_process";
import { access, mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";

import {
  AUTOMATION_SCHEMA,
  EXECUTION_SCHEMA,
  PERMISSION_MODES,
  RESUMABLE_PHASES,
  TERMINAL_PHASES,
  assertStateMatches as assertBaseStateMatches,
  atomicWriteJson,
  chooseAttemptSession,
  classifyApprovalCommand,
  classifyDomStatus,
  classifySessionStatus,
  createInitialState as createBaseInitialState,
  diffSnapshots,
  isSubstantiveFinalResponse,
  parseArgs as parseBaseArgs,
  readJsonIfExists,
  resolveConfig as resolveBaseConfig,
  resolveExecutionIdentity as resolveBaseExecutionIdentity,
  snapshotTree,
  transitionState,
  updateExecutionRecord as updateBaseExecutionRecord,
} from "../workbuddy/lib.mjs";
import {
  defaultAstronAppPath,
  defaultAstronSessionDb,
  discoverAstronApp,
  validateAstronAppPath,
} from "./platform.mjs";

export {
  AUTOMATION_SCHEMA,
  EXECUTION_SCHEMA,
  PERMISSION_MODES,
  RESUMABLE_PHASES,
  TERMINAL_PHASES,
  atomicWriteJson,
  chooseAttemptSession,
  classifyApprovalCommand,
  classifyDomStatus,
  classifySessionStatus,
  diffSnapshots,
  isSubstantiveFinalResponse,
  readJsonIfExists,
  snapshotTree,
  transitionState,
};

export const DRIVER_VERSION = "1.12.13";
export const DEFAULT_APP_PATH = defaultAstronAppPath();
export const DEFAULT_BUNDLE_ID = "cn.xfyun.acode";
export const DEFAULT_ENDPOINT = "http://127.0.0.1:9240";
export const DEFAULT_SESSION_DB = defaultAstronSessionDb();
export const ASTRONSTUDIO_PROFILE = Object.freeze({
  id: "astronstudio",
  displayName: "AstronStudio",
  driverVersion: DRIVER_VERSION,
  controlBackend: "electron-cdp+astudio-project-picker+sidebar-manual-path",
});

function optionWasProvided(argv, name) {
  return argv.some((value) => value === name);
}

export function parseArgs(argv) {
  const parsed = parseBaseArgs(argv);
  if (!optionWasProvided(argv, "--app-path")) parsed.appPath = DEFAULT_APP_PATH;
  if (!optionWasProvided(argv, "--endpoint")) parsed.endpoint = DEFAULT_ENDPOINT;
  if (!optionWasProvided(argv, "--session-db")) parsed.sessionDb = DEFAULT_SESSION_DB;
  return parsed;
}

export async function resolveConfig(parsed, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const appDiscovery = await discoverAstronApp(
    parsed.appPathExplicit ? parsed.appPath : "",
    { ...overrides, platform, endpoint: parsed.endpoint },
  );
  const appPath = appDiscovery.path;
  return resolveBaseConfig(
    { ...parsed, appPath, appDiscovery },
    {
      resolveAppPath: async (value) => value,
      validateAppPath: async (value) => validateAstronAppPath(value, platform),
    },
  );
}

export async function resolveExecutionIdentity(config) {
  return resolveBaseExecutionIdentity(config, ASTRONSTUDIO_PROFILE);
}

export function createInitialState(config, identity, initialSnapshot) {
  const state = createBaseInitialState(config, identity, initialSnapshot, ASTRONSTUDIO_PROFILE);
  state.session.turn_id = null;
  state.session.dom_baseline_conversation_captured_at = null;
  state.session.route_confirmation = null;
  return state;
}

export function assertStateMatches(state, config, identity) {
  return assertBaseStateMatches(state, config, identity, ASTRONSTUDIO_PROFILE);
}

export async function updateExecutionRecord(config, identityInfo, update) {
  return updateBaseExecutionRecord(config, identityInfo, update, ASTRONSTUDIO_PROFILE);
}

let nodeSqlitePromise;

async function loadNodeSqlite() {
  if (!nodeSqlitePromise) {
    nodeSqlitePromise = import("node:sqlite").catch(() => null);
  }
  return nodeSqlitePromise;
}

function sqliteCliPath(platform = process.platform) {
  return platform === "win32" ? "sqlite3.exe" : "/usr/bin/sqlite3";
}

export async function sqliteBackendStatus(overrides = {}) {
  const loadSqlite = overrides.loadNodeSqlite || loadNodeSqlite;
  const sqliteModule = await loadSqlite();
  if (typeof sqliteModule?.DatabaseSync === "function") {
    return { available: true, backend: "node:sqlite", command: null, error: null };
  }
  const command = overrides.sqliteCommand || sqliteCliPath(overrides.platform);
  const runCommand = overrides.runCommand || runCapture;
  try {
    await runCommand(command, ["--version"]);
    return { available: true, backend: "sqlite3-cli", command, error: null };
  } catch (error) {
    return {
      available: false,
      backend: "unavailable",
      command,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function querySqlite(snapshotDb, query, overrides = {}) {
  const loadSqlite = overrides.loadNodeSqlite || loadNodeSqlite;
  const sqliteModule = await loadSqlite();
  if (typeof sqliteModule?.DatabaseSync === "function") {
    const database = new sqliteModule.DatabaseSync(snapshotDb, { readOnly: true });
    try {
      return database.prepare(query).all();
    } finally {
      database.close();
    }
  }
  const command = overrides.sqliteCommand || sqliteCliPath(overrides.platform);
  const runCommand = overrides.runCommand || runCapture;
  const result = await runCommand(command, ["-readonly", "-json", snapshotDb, query]);
  return result.stdout.trim() ? JSON.parse(result.stdout) : [];
}

const SQLITE_SNAPSHOT_COPY_SCRIPT = fileURLToPath(new URL("./sqlite-snapshot-copy.mjs", import.meta.url));
const SQLITE_SNAPSHOT_COPY_TIMEOUT_MILLISECONDS = 120_000;

export function copySqliteSnapshot(source, destination, overrides = {}) {
  const spawnProcess = overrides.spawnProcess || spawn;
  const executable = overrides.execPath || process.execPath;
  const script = overrides.copyScript || SQLITE_SNAPSHOT_COPY_SCRIPT;
  const timeoutMilliseconds = overrides.copyTimeoutMilliseconds
    || SQLITE_SNAPSHOT_COPY_TIMEOUT_MILLISECONDS;

  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawnProcess(executable, [script, source, destination], {
      stdio: ["ignore", "ignore", "pipe"],
      windowsHide: true,
    });
    let stderr = "";
    let settled = false;
    let timedOut = false;
    child.stderr?.on("data", (chunk) => {
      if (stderr.length < 8192) stderr += chunk;
    });
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMilliseconds);

    const settle = (error = null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) rejectPromise(error);
      else resolvePromise();
    };
    child.once("error", (error) => settle(error));
    child.once("exit", (code, signal) => {
      if (timedOut) {
        const error = new Error(`AstronStudio 状态库快照复制超过 ${timeoutMilliseconds} 毫秒，已终止隔离复制进程`);
        error.code = "ASTRON_SNAPSHOT_TIMEOUT";
        settle(error);
        return;
      }
      if (code !== 0) {
        settle(new Error(`AstronStudio 状态库快照复制失败（退出码 ${code ?? "unknown"}，信号 ${signal || "none"}）：${stderr.trim() || "无错误输出"}`));
        return;
      }
      settle();
    });
  });
}

const SESSION_QUERY = `
WITH latest_turn AS (
  SELECT turns.*
  FROM projection_turns AS turns
  INNER JOIN projection_threads AS threads
    ON threads.thread_id = turns.thread_id
   AND threads.latest_turn_id = turns.turn_id
  INNER JOIN projection_projects AS projects
    ON projects.project_id = threads.project_id
  WHERE turns.checkpoint_turn_count IS NULL
)
SELECT
  sessions.thread_id AS conversationId,
  projects.workspace_root AS cwd,
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
  END AS status,
  sessions.status AS sessionStatus,
  sessions.active_turn_id AS activeTurnId,
  latest_turn.turn_id AS turnId,
  latest_turn.state AS turnState,
  latest_turn.termination_origin AS terminationOrigin,
  threads.model_selection_json AS modelSelectionJson,
  sessions.last_error AS lastError,
  COALESCE(latest_turn.completed_at, latest_turn.started_at, latest_turn.requested_at, sessions.updated_at) AS updatedAtIso
FROM projection_thread_sessions AS sessions
INNER JOIN projection_threads AS threads ON threads.thread_id = sessions.thread_id
INNER JOIN projection_projects AS projects ON projects.project_id = threads.project_id
LEFT JOIN latest_turn ON latest_turn.thread_id = sessions.thread_id
WHERE threads.deleted_at IS NULL AND projects.deleted_at IS NULL
ORDER BY updatedAtIso DESC, sessions.thread_id ASC;
`;

const SESSION_SUMMARY_QUERY = `
SELECT COUNT(*) AS totalCount,
  SUM(CASE WHEN sessions.status IN ('running','needs_attention','pending','starting')
    OR sessions.active_turn_id IS NOT NULL THEN 1 ELSE 0 END) AS activeCount
FROM projection_thread_sessions AS sessions
;
`;

async function querySnapshot(snapshotDb, overrides = {}) {
  // AStudio state.sqlite can exceed several GB after long-lived use. A full
  // quick_check scans every row and turns the read-only probe into an
  // unbounded operation; bounded quick_check still validates the snapshot
  // header and a sample of each table before the identity query.
  const snapshotSize = (await stat(snapshotDb)).size;
  if (snapshotSize > 256 * 1024 * 1024) {
    const schemaRows = await querySqlite(snapshotDb, `
      SELECT COUNT(*) AS table_count
      FROM sqlite_master
      WHERE type = 'table'
        AND name IN (
          'projection_projects', 'projection_threads',
          'projection_thread_sessions', 'projection_turns',
          'projection_pending_interactions', 'provider_runtime_open_turns'
        );
    `, overrides);
    if (Number(schemaRows[0]?.table_count || 0) !== 6) {
      throw new Error("AstronStudio 状态库快照缺少必需投影表");
    }
  } else {
    const integrityRows = await querySqlite(snapshotDb, "PRAGMA quick_check(1);", overrides);
    const integrity = Object.values(integrityRows[0] || {})[0];
    if (integrity !== "ok") {
      throw new Error(`AstronStudio 状态库快照校验失败：${integrity || "无结果"}`);
    }
  }
  const workspaceFilter = overrides.workspaceRoot
    ? `\n  AND projects.workspace_root = '${String(overrides.workspaceRoot).replaceAll("'", "''")}'`
    : "";
  const query = SESSION_QUERY
    .replace("WHERE turns.checkpoint_turn_count IS NULL", `WHERE turns.checkpoint_turn_count IS NULL${workspaceFilter}`)
    .replace("ORDER BY updatedAtIso DESC, sessions.thread_id ASC;", `${workspaceFilter}\nORDER BY updatedAtIso DESC, sessions.thread_id ASC;`);
  const rows = await querySqlite(snapshotDb, query, overrides);
  return rows.map((row) => ({
    ...row,
    updatedAt: Date.parse(row.updatedAtIso || "") || 0,
    createdAt: Date.parse(row.updatedAtIso || "") || 0,
  }));
}

async function querySnapshotSummary(snapshotDb, overrides = {}) {
  const rows = await querySqlite(snapshotDb, SESSION_SUMMARY_QUERY, overrides);
  const row = rows[0] || {};
  return { totalCount: Number(row.totalCount) || 0, activeCount: Number(row.activeCount) || 0 };
}

export async function querySessions(sessionDb = DEFAULT_SESSION_DB, overrides = {}) {
  await access(sessionDb);
  const copySnapshot = overrides.copySnapshot || copySqliteSnapshot;
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotDir = await mkdtemp(join(tmpdir(), "astudio-state-snapshot-"));
    const snapshotDb = join(snapshotDir, "state.sqlite");
    try {
      await copySnapshot(sessionDb, snapshotDb, overrides);
      return await querySnapshot(snapshotDb, overrides);
    } catch (error) {
      lastError = error;
      if (error?.code === "ASTRON_SNAPSHOT_TIMEOUT") break;
    } finally {
      await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`读取 AstronStudio 状态库失败：${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

export async function querySessionSummary(sessionDb = DEFAULT_SESSION_DB, overrides = {}) {
  await access(sessionDb);
  const copySnapshot = overrides.copySnapshot || copySqliteSnapshot;
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotDir = await mkdtemp(join(tmpdir(), "astudio-state-summary-"));
    const snapshotDb = join(snapshotDir, "state.sqlite");
    try {
      await copySnapshot(sessionDb, snapshotDb, overrides);
      return await querySnapshotSummary(snapshotDb, overrides);
    } catch (error) {
      lastError = error;
      if (error?.code === "ASTRON_SNAPSHOT_TIMEOUT") break;
    } finally {
      await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`读取 AstronStudio 状态库失败：${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

export function isQuiescentThreadEvidence(evidence, threadId) {
  if (!threadId || evidence?.thread_id !== threadId) return false;
  return evidence.session_status === "ready"
    && evidence.active_turn_id === null
    && evidence.runtime_status === "stopped"
    && typeof evidence.lifecycle_generation === "string" && evidence.lifecycle_generation.length > 0
    && ["completed", "interrupted", "error", "cancelled"].includes(evidence.latest_turn_state)
    && Number.isFinite(Date.parse(evidence.latest_turn_completed_at || ""))
    && Number.isInteger(evidence.open_turn_count) && evidence.open_turn_count > 0
    && evidence.unclosed_open_turn_count === 0
    && evidence.nonterminal_turn_count === 0
    && evidence.pending_interaction_count === 0;
}

// A stopped runtime can retain an old open-turn projection after all native
// turns have finished. Only this positive, same-thread proof permits restart;
// absent tables, unknown lifecycle state or any live/pending turn remain blocked.
export async function queryQuiescentThreadEvidence(sessionDb, threadId, overrides = {}) {
  const snapshotDir = await mkdtemp(join(tmpdir(), "astudio-quiescent-snapshot-"));
  const snapshotDb = join(snapshotDir, "state.sqlite");
  try {
    await (overrides.copySnapshot || copySqliteSnapshot)(sessionDb, snapshotDb, overrides);
    const rows = await querySqlite(snapshotDb, `
SELECT s.thread_id, s.status AS session_status, s.active_turn_id,
  r.status AS runtime_status, r.lifecycle_generation,
  t.state AS latest_turn_state, t.completed_at AS latest_turn_completed_at,
  (SELECT COUNT(*) FROM provider_runtime_open_turns o
    WHERE o.thread_id=s.thread_id) AS open_turn_count,
  (SELECT COUNT(*) FROM provider_runtime_open_turns o
    LEFT JOIN projection_turns ot ON ot.thread_id=o.thread_id AND ot.turn_id=o.turn_id
    WHERE o.thread_id=s.thread_id AND (ot.state IS NULL OR ot.completed_at IS NULL
      OR ot.state NOT IN ('completed','interrupted','error','cancelled'))) AS unclosed_open_turn_count,
  (SELECT COUNT(*) FROM projection_turns nt WHERE nt.thread_id=s.thread_id
    AND nt.checkpoint_turn_count IS NULL AND (nt.state IS NULL OR nt.completed_at IS NULL
      OR nt.state NOT IN ('completed','interrupted','error','cancelled'))) AS nonterminal_turn_count,
  (SELECT COUNT(*) FROM projection_pending_interactions pi
    WHERE pi.thread_id=s.thread_id AND pi.status='pending') AS pending_interaction_count
FROM projection_thread_sessions s
JOIN projection_threads th ON th.thread_id=s.thread_id
JOIN projection_turns t ON t.thread_id=s.thread_id AND t.turn_id=th.latest_turn_id
JOIN provider_session_runtime r ON r.thread_id=s.thread_id
WHERE s.thread_id=${sqlStringLiteral(threadId)};
`, overrides);
    return rows.length === 1 && isQuiescentThreadEvidence(rows[0], threadId) ? rows[0] : null;
  } finally {
    await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
  }
}

function sqlStringLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

export async function queryProjectEvidence(sessionDb, workspace, threadId = null, overrides = {}) {
  const snapshotDir = await mkdtemp(join(tmpdir(), "astudio-project-snapshot-"));
  const snapshotDb = join(snapshotDir, "state.sqlite");
  try {
    await (overrides.copySnapshot || copySqliteSnapshot)(sessionDb, snapshotDb, overrides);
    const projects = await querySqlite(snapshotDb, `SELECT project_id, workspace_root
FROM projection_projects WHERE workspace_root=${sqlStringLiteral(workspace)} AND deleted_at IS NULL;`, overrides);
    const threads = threadId ? await querySqlite(snapshotDb, `
SELECT t.thread_id, t.latest_turn_id, p.project_id, p.workspace_root,
 (SELECT COUNT(*) FROM projection_thread_messages m WHERE m.thread_id=t.thread_id) AS message_count,
 (SELECT COUNT(*) FROM projection_turns v WHERE v.thread_id=t.thread_id) AS turn_count,
 (SELECT COUNT(*) FROM projection_thread_sessions s WHERE s.thread_id=t.thread_id) AS session_count,
 (SELECT COUNT(*) FROM projection_pending_interactions i WHERE i.thread_id=t.thread_id AND i.status='pending') AS pending_count
FROM projection_threads t JOIN projection_projects p ON t.project_id=p.project_id
WHERE t.thread_id=${sqlStringLiteral(threadId)} AND t.deleted_at IS NULL AND p.deleted_at IS NULL;`, overrides) : [];
    return { projects, threads };
  } finally {
    await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
  }
}

// 精确 thread/turn 映射到原生会话；不从最近会话或 UI 标题猜测。
export async function queryResourceIdentity(sessionDb, threadId, turnId, overrides = {}) {
  const snapshotDir = await mkdtemp(join(tmpdir(), "astudio-resource-snapshot-"));
  const snapshotDb = join(snapshotDir, "state.sqlite");
  try {
    await (overrides.copySnapshot || copySqliteSnapshot)(sessionDb, snapshotDb, overrides);
    const rows = await querySqlite(snapshotDb, `
SELECT runtime.resume_cursor_json AS cursor, projects.workspace_root AS cwd
FROM provider_session_runtime AS runtime
JOIN projection_threads AS threads ON threads.thread_id = runtime.thread_id
JOIN projection_projects AS projects ON projects.project_id = threads.project_id
WHERE runtime.thread_id = ${sqlStringLiteral(threadId)}
AND EXISTS (SELECT 1 FROM projection_turns AS turns
  WHERE turns.thread_id = runtime.thread_id AND turns.turn_id = ${sqlStringLiteral(turnId)});
`, overrides);
    if (rows.length !== 1) throw new Error("AMBIGUOUS_NATIVE_SESSION");
    return { nativeId: JSON.parse(rows[0].cursor).threadId, cwd: rows[0].cwd };
  } finally {
    await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
  }
}

async function queryFinalResponseSnapshot(snapshotDb, threadId, turnId, overrides = {}) {
  const threadPredicate = `thread_id = ${sqlStringLiteral(threadId)}`;
  const turnPredicate = turnId ? `AND turn_id = ${sqlStringLiteral(turnId)}` : "";
  const query = `
SELECT text
FROM projection_thread_messages
WHERE ${threadPredicate}
  ${turnPredicate}
  AND role = 'assistant'
  AND is_streaming = 0
  AND trim(text) <> ''
ORDER BY sequence DESC, updated_at DESC, message_id DESC
LIMIT 1;
`;
  const rows = await querySqlite(snapshotDb, query, overrides);
  return typeof rows[0]?.text === "string" ? rows[0].text.trim() : "";
}

export async function queryFinalResponse(sessionDb, threadId, turnId = null, overrides = {}) {
  await access(sessionDb);
  if (!threadId) return "";
  const copySnapshot = overrides.copySnapshot || copySqliteSnapshot;
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotDir = await mkdtemp(join(tmpdir(), "astudio-state-snapshot-"));
    const snapshotDb = join(snapshotDir, "state.sqlite");
    try {
      await copySnapshot(sessionDb, snapshotDb, overrides);
      return await queryFinalResponseSnapshot(snapshotDb, threadId, turnId, overrides);
    } catch (error) {
      lastError = error;
      if (error?.code === "ASTRON_SNAPSHOT_TIMEOUT") break;
    } finally {
      await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`读取 AstronStudio 最终回复失败：${lastError instanceof Error ? lastError.message : String(lastError)}`);
}
