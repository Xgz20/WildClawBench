import { spawn } from "node:child_process";
import { access, copyFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

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
  resolveAstronAppPath,
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

export const DRIVER_VERSION = "1.10.1";
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
  const appPath = await resolveAstronAppPath(parsed.appPath, { ...overrides, platform });
  return resolveBaseConfig(
    { ...parsed, appPath },
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
  return createBaseInitialState(config, identity, initialSnapshot, ASTRONSTUDIO_PROFILE);
}

export function assertStateMatches(state, config, identity) {
  return assertBaseStateMatches(state, config, identity, ASTRONSTUDIO_PROFILE);
}

export async function updateExecutionRecord(config, identityInfo, update) {
  return updateBaseExecutionRecord(config, identityInfo, update, ASTRONSTUDIO_PROFILE);
}

function runCapture(command, args) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", rejectPromise);
    child.once("exit", (code) => {
      if (code === 0) resolvePromise({ stdout, stderr });
      else rejectPromise(new Error(`${command} 执行失败（退出码 ${code}）：${stderr.trim()}`));
    });
  });
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

async function copyIfPresent(source, destination) {
  try {
    await copyFile(source, destination);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

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

async function querySnapshot(snapshotDb, overrides = {}) {
  const integrityRows = await querySqlite(snapshotDb, "PRAGMA quick_check;", overrides);
  const integrity = Object.values(integrityRows[0] || {})[0];
  if (integrity !== "ok") {
    throw new Error(`AstronStudio 状态库快照校验失败：${integrity || "无结果"}`);
  }
  const rows = await querySqlite(snapshotDb, SESSION_QUERY, overrides);
  return rows.map((row) => ({
    ...row,
    updatedAt: Date.parse(row.updatedAtIso || "") || 0,
    createdAt: Date.parse(row.updatedAtIso || "") || 0,
  }));
}

export async function querySessions(sessionDb = DEFAULT_SESSION_DB, overrides = {}) {
  await access(sessionDb);
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotDir = await mkdtemp(join(tmpdir(), "astudio-state-snapshot-"));
    const snapshotDb = join(snapshotDir, "state.sqlite");
    try {
      await copyFile(sessionDb, snapshotDb);
      await copyIfPresent(`${sessionDb}-wal`, `${snapshotDb}-wal`);
      await copyIfPresent(`${sessionDb}-shm`, `${snapshotDb}-shm`);
      return await querySnapshot(snapshotDb, overrides);
    } catch (error) {
      lastError = error;
    } finally {
      await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`读取 AstronStudio 状态库失败：${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

function sqlStringLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
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
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotDir = await mkdtemp(join(tmpdir(), "astudio-state-snapshot-"));
    const snapshotDb = join(snapshotDir, "state.sqlite");
    try {
      await copyFile(sessionDb, snapshotDb);
      await copyIfPresent(`${sessionDb}-wal`, `${snapshotDb}-wal`);
      await copyIfPresent(`${sessionDb}-shm`, `${snapshotDb}-shm`);
      return await queryFinalResponseSnapshot(snapshotDb, threadId, turnId, overrides);
    } catch (error) {
      lastError = error;
    } finally {
      await rm(snapshotDir, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`读取 AstronStudio 最终回复失败：${lastError instanceof Error ? lastError.message : String(lastError)}`);
}
