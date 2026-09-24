import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import { access, lstat, realpath } from "node:fs/promises";
import { constants } from "node:fs";
import { isAbsolute, join, parse, resolve } from "node:path";
import { defaultNativeRoots } from "./platform.mjs";

const execFile = promisify(execFileCallback);

export function assessPathBudget(path, { nameMax, pathMax }) {
  if (!isAbsolute(path || "") || /[\u0000-\u001f\u007f]/u.test(path)) throw new Error("DOUBAOWORK_PATH_CHARACTERS_UNSAFE");
  if (![nameMax, pathMax].every(n => Number.isInteger(n) && n > 0)) throw new Error("DOUBAOWORK_FILESYSTEM_LIMIT_UNKNOWN");
  const absolute = resolve(path), bytes = Buffer.byteLength(absolute);
  if (bytes + 1 > pathMax) throw new Error("DOUBAOWORK_PATH_MAX_EXCEEDED");
  if (absolute.split("/").some(part => Buffer.byteLength(part) > nameMax)) throw new Error("DOUBAOWORK_NAME_MAX_EXCEEDED");
  return { path: absolute, utf8_bytes: bytes, path_max_bytes_including_nul: pathMax, name_max_bytes: nameMax };
}

async function inspectChain(path) {
  const absolute = resolve(path), root = parse(absolute).root;
  let current = root, lastDirectory = root, targetExists = false;
  for (const part of absolute.slice(root.length).split("/").filter(Boolean)) {
    current = join(current, part);
    let st;
    try { st = await lstat(current); } catch (e) { if (["ENOENT", "ENAMETOOLONG"].includes(e.code)) break; throw e; }
    if (st.isSymbolicLink()) throw new Error("DOUBAOWORK_PATH_SYMLINK_REJECTED");
    if (!st.isDirectory() && current !== absolute) throw new Error("DOUBAOWORK_PATH_PARENT_NOT_DIRECTORY");
    if (st.isDirectory()) lastDirectory = current;
    if (current === absolute) targetExists = true;
  }
  if (await realpath(lastDirectory) !== lastDirectory) throw new Error("DOUBAOWORK_PATH_CANONICAL_DRIFT");
  return { ancestor: lastDirectory, exists: targetExists };
}

export async function preflightDoubaoPaths({ workspace, promptFile, outputDir, nativeRoot = defaultNativeRoots().sessions_root }, overrides = {}) {
  if ((overrides.platform ?? process.platform) !== "darwin") throw new Error("DOUBAOWORK_PATH_PREFLIGHT_REQUIRES_MACOS");
  for (const value of [workspace, promptFile, outputDir, nativeRoot]) {
    if (!isAbsolute(value || "") || /[\u0000-\u001f\u007f]/u.test(value)) throw new Error("DOUBAOWORK_PATH_CHARACTERS_UNSAFE");
  }
  const query = overrides.readLimit || (async (name, path) => {
    const { stdout } = await execFile("/usr/bin/getconf", [name, path], { timeout: 5000, maxBuffer: 1024 });
    if (!/^\d+\s*$/u.test(stdout)) throw new Error("DOUBAOWORK_FILESYSTEM_LIMIT_UNKNOWN");
    return Number(stdout.trim());
  });
  const checks = [], cache = new Map();
  const check = async (path, role, writable) => {
    const chain = await inspectChain(path);
    let limits = cache.get(chain.ancestor);
    if (!limits) { limits = { nameMax: await query("NAME_MAX", chain.ancestor), pathMax: await query("PATH_MAX", chain.ancestor) }; cache.set(chain.ancestor, limits); }
    const budget = assessPathBudget(path, limits);
    if (writable) await access(chain.ancestor, constants.W_OK | constants.X_OK);
    checks.push({ role, ...budget, existing_ancestor: chain.ancestor });
    return { ...chain, limits };
  };
  const ws = await check(workspace, "candidate-workspace", true);
  if (!ws.exists || !(await lstat(workspace)).isDirectory()) throw new Error("DOUBAOWORK_WORKSPACE_MISSING");
  const prompt = await check(promptFile, "prepared-prompt", false);
  if (!prompt.exists || !(await lstat(promptFile)).isFile()) throw new Error("DOUBAOWORK_PROMPT_MISSING");
  const output = await check(outputDir, "control-root", true);
  if (output.exists && !(await lstat(outputDir)).isDirectory()) throw new Error("DOUBAOWORK_CONTROL_ROOT_NOT_DIRECTORY");
  await check(join(outputDir, "trajectory-observations", `0255-${"f".repeat(64)}.jsonl`), "longest-known-control-artifact", true);
  const native = await check(nativeRoot, "native-session-root", true);
  // Session IDs are constrained by validateSessionId (1–64 digits); reserve
  // the filesystem's full component budget for a native agent directory.
  await check(join(nativeRoot, "9".repeat(64), "agents", "a".repeat(native.limits.nameMax), "system", "trajectory.jsonl"), "native-session-path-reservation", true);
  return { policy: "doubaowork-darwin-known-path-byte-budget/v1", status: "verified", checked_at: new Date().toISOString(),
    checks, scope: "prepared roots, known controller artifacts, native session path; future arbitrary candidate outputs remain subject to collection validation" };
}
