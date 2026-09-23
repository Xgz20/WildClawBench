import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { access, realpath, stat } from "node:fs/promises";
import { dirname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";
import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";
import { assertNoSymlinkPath } from "./journal.mjs";

export const QWEN_PATH_ENCODING = "qoder-ascii-prefix-djb2-xor/v1";

// Inspect the installed SDK's pure encoding implementation without executing it.
// Obfuscated identifier names and client versions are not admission criteria.
export function inspectQwenProjectEncoding(source) {
  const expression = /function ([\w$]+)\(([\w$]+)\)\{let ([\w$]+)=\2\.replace\(\/\[\^a-zA-Z0-9\]\/g,"-"\);if\(\3\.length<=([\w$]+)\)return \3;let ([\w$]+)=Math\.abs\(([\w$]+)\(\2\)\)\.toString\(36\);return`\$\{\3\.slice\(0,\4\)\}-\$\{\5\}`\}/gu;
  const matches = [...source.matchAll(expression)];
  if (matches.length !== 1) return { verified: false, reason: "encoding-function-not-unique-or-changed" };
  const [, name, , , limitName, , hashName] = matches[0];
  const escape = (value) => value.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const hash = new RegExp(`function ${escape(hashName)}\\(([\\w$]+)\\)\\{let ([\\w$]+)=5381;for\\(let ([\\w$]+)=0;\\3<\\1\\.length;\\3\\+\\+\\)\\2=33\\*\\2\\^\\1\\.charCodeAt\\(\\3\\);return \\2\\}`, "u");
  const limits = [...source.matchAll(new RegExp(`\\b${escape(limitName)}=(\\d+)(?=[,;}])`, "gu"))];
  if (!hash.test(source) || limits.length !== 1 || Number(limits[0][1]) < 1 || Number(limits[0][1]) > 240) {
    return { verified: false, reason: "encoding-hash-or-prefix-unverified" };
  }
  return { verified: true, algorithm: QWEN_PATH_ENCODING, prefix_chars: Number(limits[0][1]),
    source_sha256: createHash("sha256").update(source).digest("hex"), function_name: name };
}

export function qwenProjectDirectoryName(workspace, encoding) {
  if (!isAbsolute(workspace || "") || workspace.includes("\0")) throw new Error("QWENWORK_PATH_NOT_ABSOLUTE");
  if (encoding?.verified !== true || encoding.algorithm !== QWEN_PATH_ENCODING
      || !Number.isSafeInteger(encoding.prefix_chars) || encoding.prefix_chars < 1 || encoding.prefix_chars > 240) {
    throw new Error("QWENWORK_PATH_ENCODING_UNVERIFIED");
  }
  const encoded = workspace.replace(/[^a-zA-Z0-9]/g, "-");
  if (encoded.length <= encoding.prefix_chars) return encoded;
  let hash = 5381;
  for (let index = 0; index < workspace.length; index += 1) hash = 33 * hash ^ workspace.charCodeAt(index);
  return `${encoded.slice(0, encoding.prefix_chars)}-${Math.abs(hash).toString(36)}`;
}

function inside(root, path) {
  const rel = relative(resolve(root), resolve(path));
  return rel === "" || (rel !== ".." && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

export function planQwenExecutionPaths(config, encoding, { nameMax = 255, pathMax = 1024 } = {}) {
  if (![nameMax, pathMax].every((value) => Number.isSafeInteger(value) && value > 0)) {
    throw new Error("QWENWORK_PATH_LIMITS_UNVERIFIED");
  }
  if (!inside(config.task_root, config.candidate_workspace) || !inside(config.task_root, config.prompt.path)) {
    throw new Error("QWENWORK_PATH_OUTSIDE_TASK");
  }
  const workspace = resolve(config.candidate_workspace);
  const traceRoot = resolve(config.client.trace_root);
  const directoryName = qwenProjectDirectoryName(workspace, encoding);
  // Reserves are filename byte budgets, not invented native session IDs.
  const paths = [
    ["task", config.task_root], ["workspace", workspace], ["prompt", config.prompt.path],
    ["state", config.state_file], ["evidence", config.evidence_root],
    ["state-temporary", `${config.state_file}.tmp-${"p".repeat(10)}-${"u".repeat(36)}`],
    ["state-lock-archive", `${config.state_file}.lock.stale-${"u".repeat(64)}.json`],
    ["native-transcript-budget", join(traceRoot, "projects", directoryName, `${"s".repeat(249)}.jsonl`)],
    ["native-segment-budget", join(traceRoot, "logs", "sessions", directoryName, "s".repeat(255), "segments", "f".repeat(255))],
    ["native-temp-budget", join(traceRoot, "tmp", directoryName, "images", "s".repeat(255))],
  ];
  const checked = paths.map(([kind, value]) => {
    if (!isAbsolute(value || "") || value.includes("\0")) throw new Error(`QWENWORK_PATH_INVALID: ${kind}`);
    const path = resolve(value);
    const bytes = Buffer.byteLength(path, "utf8");
    const components = path.slice(parse(path).root.length).split(sep);
    const componentBytes = Math.max(...components.map((part) => Buffer.byteLength(part, "utf8")));
    // PATH_MAX includes the trailing NUL; NAME_MAX excludes it.
    if (bytes >= pathMax || componentBytes > nameMax) {
      throw new Error(`QWENWORK_PATH_BUDGET_EXCEEDED: ${kind}; path=${bytes}+1/${pathMax}; component=${componentBytes}/${nameMax}; use a shorter unit/trace root before sending`);
    }
    return { kind, path, bytes, maximum_component_bytes: componentBytes };
  });
  return { schema_version: "wildclawbench.general-e2e-qwenwork-path-preflight/v1", verified: true,
    encoding, workspace, trace_root: traceRoot, native_project_directory: directoryName,
    native_project_component_bytes: Buffer.byteLength(directoryName), name_max_bytes: nameMax,
    path_max_bytes_including_nul: pathMax, reserved_session_component_bytes: 255,
    reserved_segment_filename_bytes: 255, paths: checked };
}

export async function preflightQwenExecutionPaths(config, encoding, overrides = {}) {
  // Pure length checks precede filesystem calls, lock creation and CDP access.
  const planned = planQwenExecutionPaths(config, encoding);
  for (const path of [config.task_root, config.candidate_workspace, config.prompt.path,
    config.state_file, config.evidence_root, config.client.trace_root]) await assertNoSymlinkPath(path);
  for (const { path } of planned.paths) await assertNoSymlinkPath(path);
  const workspace = await realpath(config.candidate_workspace);
  const taskRoot = await realpath(config.task_root);
  const traceRoot = await realpath(config.client.trace_root);
  if (workspace !== resolve(config.candidate_workspace) || taskRoot !== resolve(config.task_root)
      || traceRoot !== resolve(config.client.trace_root)) throw new Error("QWENWORK_PATH_CANONICAL_MISMATCH");
  if (!(await stat(workspace)).isDirectory() || !(await stat(traceRoot)).isDirectory()) {
    throw new Error("QWENWORK_PATH_DIRECTORY_REQUIRED");
  }
  await access(workspace, constants.R_OK | constants.W_OK | constants.X_OK);
  await access(traceRoot, constants.R_OK | constants.W_OK | constants.X_OK);
  for (const { path } of planned.paths) {
    let parent = dirname(path);
    for (;;) {
      try {
        if (!(await stat(parent)).isDirectory()) throw new Error("QWENWORK_PATH_PARENT_NOT_DIRECTORY");
        await access(parent, constants.W_OK | constants.X_OK);
        break;
      } catch (error) {
        if (error.code !== "ENOENT" || dirname(parent) === parent) throw error;
        parent = dirname(parent);
      }
    }
  }
  const run = overrides.runCommand || runCapture;
  const readLimit = async (root, name) => {
    const result = await run("/usr/bin/getconf", [name, root], { capture: true });
    const value = Number(result.stdout.trim());
    if (!Number.isSafeInteger(value) || value < 1) throw new Error("QWENWORK_PATH_LIMITS_UNVERIFIED");
    return value;
  };
  const roots = [...new Set([workspace, traceRoot])];
  const limits = await Promise.all(roots.map(async (root) => ({ root,
    name_max: await readLimit(root, "NAME_MAX"), path_max: await readLimit(root, "PATH_MAX") })));
  const result = planQwenExecutionPaths(config, encoding, {
    nameMax: Math.min(...limits.map((row) => row.name_max)), pathMax: Math.min(...limits.map((row) => row.path_max)),
  });
  return { ...result, filesystem_limits: limits, checked_at: new Date().toISOString() };
}
