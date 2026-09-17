import { createHash } from "node:crypto";
import { readFile, readdir, lstat, realpath } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { empty, parseAstron, parseWorkBuddy, parseQwen } from "./parsers.mjs";
import { inspectQwenRuntime } from "./qwen-profile.mjs";

const MAX_BYTES = 64 * 1024 * 1024;
const safeId = (id) => typeof id === "string" && /^[a-zA-Z0-9_-]{8,100}$/u.test(id);
const samePath = (a, b) => process.platform === "win32" ? resolve(a).toLowerCase() === resolve(b).toLowerCase() : resolve(a) === resolve(b);

async function readTrace(file, root) {
  const info = await lstat(file);
  if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_BYTES) throw new Error("UNSAFE_OR_OVERSIZED_TRACE");
  const rel = relative(await realpath(root), await realpath(file));
  if (rel.startsWith("..") || rel === "") throw new Error("TRACE_OUTSIDE_ROOT");
  const bytes = await readFile(file);
  if (bytes.length > MAX_BYTES) throw new Error("OVERSIZED_TRACE");
  const rows = bytes.toString("utf8").split(/\r?\n/u).filter(line => line.trim()).map(line => JSON.parse(line));
  return { rows, bytes: bytes.length, source: { root: "harness-data", path: rel.replaceAll("\\", "/"), sha256: createHash("sha256").update(bytes).digest("hex") } };
}

async function find(root, levels, filename) {
  const matches = []; let visited = 0;
  async function walk(dir, remaining) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      if (++visited > 25000) throw new Error("TRACE_DISCOVERY_LIMIT");
      const path = join(dir, entry.name);
      if (entry.isFile() && filename(entry.name)) matches.push(path);
      if (remaining > 0 && entry.isDirectory()) await walk(path, remaining - 1);
    }
  }
  await walk(root, levels);
  return matches;
}

export function astronSessionRoots(home, sessionDb) {
  const roots = [join(home, ".acode", "sessions")];
  if (typeof sessionDb === "string" && sessionDb.trim()) {
    // Windows AStudio keeps state.sqlite under "AStudio Data/userdata" and
    // native rollouts under the adjacent acode-home-overlay directory.
    roots.push(join(dirname(dirname(resolve(sessionDb))), "acode-home-overlay", "sessions"));
  }
  return [...new Set(roots.map(root => resolve(root)))];
}

export async function findAstronTrace(home, sessionDb, sessionId) {
  const matches = [];
  for (const root of astronSessionRoots(home, sessionDb)) {
    let info;
    try { info = await lstat(root); }
    catch (error) {
      if (error?.code === "ENOENT") continue;
      throw error;
    }
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("UNSAFE_TRACE_ROOT");
    for (const file of await find(root, 3, name => name.endsWith(`-${sessionId}.jsonl`))) {
      matches.push({ file, root });
    }
  }
  if (matches.length !== 1) throw new Error("AMBIGUOUS_TRACE");
  return matches[0];
}

function assertCwd(rows, cwd, selector) {
  const paths = rows.map(selector).filter(Boolean);
  if (!paths.length || paths.some(p => !samePath(p, cwd))) throw new Error("TRACE_CWD_MISMATCH");
}

export async function collectLocalMetrics(input) {
  const { harness, state, workspace, sessionDb, home = homedir() } = input;
  const session = state.session || {};
  let result, sources = [], sessionId;
  if (harness === "astronstudio") {
    const thread = session.conversation_id, turn = session.turn_id;
    if (!safeId(thread) || !safeId(turn)) throw new Error("MISSING_STABLE_SESSION");
    const { queryResourceIdentity } = await import("../astronstudio/lib.mjs");
    const identity = await queryResourceIdentity(sessionDb, thread, turn);
    sessionId = identity.nativeId;
    if (!safeId(sessionId) || !samePath(identity.cwd, workspace)) throw new Error("SESSION_IDENTITY_MISMATCH");
    const { file, root } = await findAstronTrace(home, sessionDb, sessionId);
    const trace = await readTrace(file, root);
    assertCwd(trace.rows.filter(r => r.type === "session_meta"), workspace, r => r.payload?.cwd);
    result = parseAstron(trace.rows, turn);
    sources = [trace.source];
  } else if (harness === "workbuddy") {
    sessionId = session.conversation_id || session.dom_conversation_id;
    if (!safeId(sessionId)) throw new Error("MISSING_STABLE_SESSION");
    const root = join(home, ".workbuddy", "projects");
    const files = await find(root, 1, name => name === `${sessionId}.jsonl`);
    if (files.length !== 1) throw new Error("AMBIGUOUS_TRACE");
    const trace = await readTrace(files[0], root);
    assertCwd(trace.rows, workspace, r => r.cwd);
    if (trace.rows.some(r => r.sessionId && r.sessionId !== sessionId)) throw new Error("SESSION_IDENTITY_MISMATCH");
    result = parseWorkBuddy(trace.rows); sources = [trace.source];
  } else if (harness === "qwenwork") {
    sessionId = session.session_id;
    if (!safeId(sessionId)) throw new Error("MISSING_STABLE_SESSION");
    const root = join(home, ".qwenworkcn");
    const transcripts = await find(join(root, "projects"), 1, name => name === `${sessionId}.jsonl`);
    if (transcripts.length !== 1) throw new Error("AMBIGUOUS_TRACE");
    const transcript = await readTrace(transcripts[0], root);
    assertCwd(transcript.rows, workspace, r => r.cwd);
    if (transcript.rows.some(r => r.sessionId && r.sessionId !== sessionId)) throw new Error("SESSION_IDENTITY_MISMATCH");
    // 项目目录由已校验的原生会话反查，不遍历其他题目的日志内容。
    const project = relative(join(root, "projects"), transcripts[0]).split(/[\\/]/u)[0];
    const segments = await find(join(root, "logs", "sessions", project, sessionId, "segments"), 0, n => n.endsWith(".jsonl"));
    if (!segments.length || segments.length > 100) throw new Error("INVALID_SEGMENT_COUNT");
    const traces = []; let totalBytes = 0;
    for (const file of segments.sort()) {
      totalBytes += (await lstat(file)).size;
      if (totalBytes > 2 * MAX_BYTES) throw new Error("TOTAL_TRACE_SIZE_LIMIT");
      traces.push(await readTrace(file, root));
    }
    const runtimeIdentity = await inspectQwenRuntime(input.appPath || state.client?.app_path, state.client?.version, transcript.rows);
    result = parseQwen(traces.flatMap(t => t.rows), { runtimeIdentity });
    sources = [transcript.source, ...traces.map(t => t.source)];
  } else return empty("UNSUPPORTED_HARNESS");
  result.collection.sources = sources;
  result.collection.collected_at = new Date().toISOString();
  result.collection.session_id = sessionId;
  result.collection.attempt_id = state.attempt_id;
  return result;
}
