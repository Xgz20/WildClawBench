import { access, copyFile, lstat, mkdtemp, rm, readFile, realpath } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, isAbsolute } from "node:path";
import { createHash } from "node:crypto";
import { runCapture } from "../desktop-runtime/process.mjs";
export const COMPONENT_VERSION = "1.0.0";
const SNAPSHOT_RETRY_LIMIT = 8;
const SNAPSHOT_RETRY_BACKOFF_MS = 25;
const sha = value => createHash("sha256").update(value).digest("hex");
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
    // lsof cannot expose SQLite's lock mode portably. A holder is therefore
    // treated as an active/unknown writer. Active WAL/SHM snapshots can still
    // be queried from a copied three-file snapshot after source stability is
    // verified; sidecar-free snapshots remain blocked while held.
    return Boolean(String(result.stdout || "").trim());
  } catch {
    // Fail closed when the writer check itself is unavailable.
    return null;
  }
}

function immutableSqliteUri(path) {
  return `file:${encodeURI(path)}?immutable=1`;
}

async function defaultOnlineBackup(source, target) {
  // SQLite owns the read transaction while copying WAL frames. Copying the
  // three live files separately cannot guarantee that they belong to one
  // committed snapshot when QwenWork is writing continuously.
  const script = String.raw`
import pathlib
import sqlite3
import sys

source_path, target_path = sys.argv[1:]
with sqlite3.connect(pathlib.Path(source_path).as_uri() + "?mode=ro", uri=True, timeout=5) as source:
    with sqlite3.connect(target_path, timeout=5) as target:
        source.backup(target, pages=0, sleep=0.05)
`;
  await runCapture("/usr/bin/python3", ["-c", script, source, target], { capture: true });
}

export async function querySnapshot(sessionDb, query, overrides = {}) {
  await access(sessionDb);
  const runQuery = overrides.query || defaultSqliteQuery;
  const makeTemp = overrides.mkdtemp || mkdtemp;
  const remove = overrides.rm || rm;
  const copy = overrides.copyFile || copyFile;
  const statFile = overrides.lstat || lstat;
  const writerCheck = overrides.writerCheck || defaultWriterCheck;
  const onlineBackup = overrides.onlineBackup || defaultOnlineBackup;
  const sidecars = [`${sessionDb}-wal`, `${sessionDb}-shm`];
  let lastError = null;
  for (let attempt = 1; attempt <= SNAPSHOT_RETRY_LIMIT; attempt += 1) {
    const snapshotRoot = await makeTemp(join(tmpdir(), "qwenwork-general-probe-"));
    const snapshotDb = join(snapshotRoot, basename(sessionDb));
    try {
      if (overrides.consistentOnlineBackup === true) {
        await onlineBackup(sessionDb, snapshotDb);
        const snapshotUri = immutableSqliteUri(snapshotDb);
        const quickCheck = await runQuery(snapshotUri, "PRAGMA quick_check;");
        const result = String(quickCheck[0]?.quick_check || quickCheck[0]?.integrity_check || "").trim();
        if (result !== "ok") throw new Error(`QWENWORK_DB_QUICK_CHECK_FAILED: ${result || "empty"}`);
        const rows = await runQuery(snapshotUri, query);
        if (overrides.captureEvidence === true) {
          const bytes = await readFile(snapshotDb);
          return { rows, snapshot: { method: "readonly-source-sqlite-online-backup", quick_check: result,
            query_sha256: sha(query), database_path: await realpath(sessionDb),
            snapshot_sha256: sha(bytes), snapshot_size: bytes.length, observed_at: new Date().toISOString() } };
        }
        return rows;
      }
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
      const sourceChanged = !sameFileSignature(before.main, after.main)
        || !sameFileSignature(before.wal, after.wal)
        || !sameFileSignature(before.shm, after.shm);
      if (sourceChanged) {
        throw new Error("QWENWORK_DB_SNAPSHOT_SOURCE_CHANGED");
      }

      // A sidecar-free WAL main file is only safe through SQLite's immutable
      // URI after no process holds the database. Active WAL/SHM snapshots use
      // ordinary read-only mode so SQLite consumes the copied sidecars.
      if (writer && !hasSidecar) throw new Error("QWENWORK_DB_WRITER_PRESENT");
      const queryDatabase = !hasSidecar && !writer
        ? immutableSqliteUri(snapshotDb)
        : snapshotDb;
      const quickCheck = await runQuery(queryDatabase, "PRAGMA quick_check;");
      const result = String(quickCheck[0]?.quick_check || quickCheck[0]?.integrity_check || "").trim();
      if (result !== "ok") throw new Error(`QWENWORK_DB_QUICK_CHECK_FAILED: ${result || "empty"}`);
      return await runQuery(queryDatabase, query);
    } catch (error) {
      lastError = error;
      if (attempt < SNAPSHOT_RETRY_LIMIT) {
        await new Promise((resolvePromise) => setTimeout(resolvePromise, SNAPSHOT_RETRY_BACKOFF_MS));
      }
    } finally {
      await remove(snapshotRoot, { recursive: true, force: true }).catch(() => {});
    }
  }
  throw new Error(`QWENWORK_DB_SNAPSHOT_FAILED: ${lastError instanceof Error ? lastError.message : String(lastError)}`);
}


export async function captureQwenSessionSnapshot({ databasePath, sessionId, workspace }) {
  if (!isAbsolute(databasePath || "") || !isAbsolute(workspace || "") || !/^[A-Za-z0-9_-]+$/u.test(sessionId || "")) {
    throw Error("QWENWORK_NATIVE_SNAPSHOT_INPUT_INVALID");
  }
  const before = await lstat(databasePath);
  if (!before.isFile() || before.isSymbolicLink()) throw Error("QWENWORK_NATIVE_SNAPSHOT_DATABASE_UNSAFE");
  const { rows, snapshot } = await querySnapshot(databasePath, QWENWORK_SESSION_QUERY,
    { consistentOnlineBackup: true, captureEvidence: true });
  const after = await lstat(databasePath);
  if (before.dev !== after.dev || before.ino !== after.ino) throw Error("QWENWORK_NATIVE_SNAPSHOT_DATABASE_REPLACED");
  const matches = rows.filter(row => row.session_id === sessionId);
  if (matches.length !== 1 || matches[0].cwd !== workspace) throw Error("QWENWORK_NATIVE_SNAPSHOT_SESSION_AMBIGUOUS");
  const payload = { schema: "wildclawbench.qwenwork-native-session-snapshot/v1", ...snapshot,
    database_identity: { dev: after.dev, ino: after.ino }, record: matches[0] };
  return { ...payload, payload_sha256: sha(JSON.stringify(payload)) };
}

export function verifyQwenSessionSnapshot(snapshot, state) {
  if (!snapshot || snapshot.schema !== "wildclawbench.qwenwork-native-session-snapshot/v1") throw Error("QWENWORK_NATIVE_SNAPSHOT_REQUIRED");
  const { payload_sha256: digest, ...payload } = snapshot;
  if (sha(JSON.stringify(payload)) !== digest || snapshot.query_sha256 !== sha(QWENWORK_SESSION_QUERY)
      || snapshot.method !== "readonly-source-sqlite-online-backup" || snapshot.quick_check !== "ok"
      || !isAbsolute(snapshot.database_path || "") || !/^[a-f0-9]{64}$/u.test(snapshot.snapshot_sha256 || "")
      || !Number.isSafeInteger(snapshot.snapshot_size) || snapshot.snapshot_size <= 0
      || !Number.isFinite(Date.parse(snapshot.observed_at))
      || !Number.isFinite(Date.parse(state.execution.finished_at))
      || Date.parse(snapshot.observed_at) < Date.parse(state.execution.finished_at)
      || Date.parse(snapshot.observed_at) > Date.now()) throw Error("QWENWORK_NATIVE_SNAPSHOT_PROVENANCE_INVALID");
  const row = snapshot.record, expected = state.extensions?.qwenwork;
  if (!row || row.session_id !== state.session.session_id || row.cwd !== state.session.cwd
      || row.conversation_id !== expected.conversation_id || row.sub_chat_id !== expected.sub_chat_id
      || row.local_project_id !== expected.local_project_id || row.stream_id !== null
      || row.native_status !== expected.native_status) throw Error("QWENWORK_NATIVE_SNAPSHOT_BINDING_MISMATCH");
  return row;
}
