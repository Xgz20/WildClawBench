import { createHash } from "node:crypto";
import { lstat, readFile, readdir, realpath } from "node:fs/promises";
import { basename, dirname, join, relative, resolve } from "node:path";

export const COMPONENT_NAME = "resource-metrics";
export const COMPONENT_VERSION = "1.0.0";
export const DEFAULT_MAX_TRACE_BYTES = 64 * 1024 * 1024;

export function isSafeNativeId(id) {
  return typeof id === "string" && /^[a-zA-Z0-9_-]{8,100}$/u.test(id);
}

export function sameNativePath(left, right, platform = process.platform) {
  const normalizedLeft = resolve(left);
  const normalizedRight = resolve(right);
  return platform === "win32"
    ? normalizedLeft.toLowerCase() === normalizedRight.toLowerCase()
    : normalizedLeft === normalizedRight;
}

export async function readTrace(file, root, { maximumBytes = DEFAULT_MAX_TRACE_BYTES } = {}) {
  const info = await lstat(file);
  if (!info.isFile() || info.isSymbolicLink() || info.size > maximumBytes) {
    throw new Error("UNSAFE_OR_OVERSIZED_TRACE");
  }
  // Windows can lstat/read a path longer than MAX_PATH while realpath(file)
  // reports ENOENT. Resolve the trusted parent; lstat already rejected a
  // symbolic link at the file leaf.
  const resolvedRoot = await realpath(root);
  const resolvedParent = await realpath(dirname(file));
  const rel = relative(resolvedRoot, join(resolvedParent, basename(file)));
  if (rel.startsWith("..") || rel === "") throw new Error("TRACE_OUTSIDE_ROOT");
  const bytes = await readFile(file);
  if (bytes.length > maximumBytes) throw new Error("OVERSIZED_TRACE");
  const rows = bytes.toString("utf8")
    .split(/\r?\n/u)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
  return {
    rows,
    bytes: bytes.length,
    source: {
      root: "harness-data",
      path: rel.replaceAll("\\", "/"),
      sha256: createHash("sha256").update(bytes).digest("hex"),
    },
  };
}

export async function findTraceFiles(root, levels, filename, { maximumEntries = 25_000 } = {}) {
  const matches = [];
  let visited = 0;
  async function walk(directory, remaining) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      visited += 1;
      if (visited > maximumEntries) throw new Error("TRACE_DISCOVERY_LIMIT");
      const candidate = join(directory, entry.name);
      if (entry.isFile() && filename(entry.name)) matches.push(candidate);
      if (remaining > 0 && entry.isDirectory()) await walk(candidate, remaining - 1);
    }
  }
  await walk(root, levels);
  return matches;
}

export function assertTraceWorkspace(rows, workspace, selector, { platform = process.platform } = {}) {
  const paths = rows.map(selector).filter(Boolean);
  if (!paths.length || paths.some((value) => !sameNativePath(value, workspace, platform))) {
    throw new Error("TRACE_CWD_MISMATCH");
  }
}

export function astronSessionRoots(home, sessionDb) {
  const roots = [join(home, ".acode", "sessions")];
  if (typeof sessionDb === "string" && sessionDb.trim()) {
    roots.push(join(dirname(dirname(resolve(sessionDb))), "acode-home-overlay", "sessions"));
  }
  return [...new Set(roots.map((root) => resolve(root)))];
}

export async function findAstronTrace(home, sessionDb, sessionId) {
  const matches = [];
  for (const root of astronSessionRoots(home, sessionDb)) {
    let info;
    try {
      info = await lstat(root);
    } catch (error) {
      if (error?.code === "ENOENT") continue;
      throw error;
    }
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("UNSAFE_TRACE_ROOT");
    for (const file of await findTraceFiles(root, 3, (name) => name.endsWith(`-${sessionId}.jsonl`))) {
      matches.push({ file, root });
    }
  }
  if (matches.length !== 1) throw new Error("AMBIGUOUS_TRACE");
  return matches[0];
}
