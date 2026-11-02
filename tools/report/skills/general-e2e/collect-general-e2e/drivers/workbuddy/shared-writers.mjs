#!/usr/bin/env node
// Read-only ownership evidence. Never closes a document or kills a process.
import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import { createHash } from "node:crypto";
import { lstat, readFile, realpath, writeFile } from "node:fs/promises";
import { resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
const execFile = promisify(execFileCallback);
const sha = value => createHash("sha256").update(value).digest("hex");

export function parseProcesses(text) {
  const rows = new Map();
  for (const line of text.split(/\r?\n/u).filter(x => x.trim())) {
    const m = line.match(/^\s*(\d+)\s+(\d+)\s+([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+(.*)$/u);
    if (!m || rows.has(Number(m[1]))) throw new Error("WORKBUDDY_WRITER_PS_INVALID");
    rows.set(Number(m[1]), { pid: Number(m[1]), ppid: Number(m[2]), started_at: new Date(m[3] + " UTC").toISOString(),
      command: m[4], command_sha256: sha(m[4]) });
  }
  return rows;
}
export function parseOpenFiles(text) {
  const records = []; let pid = null, descriptor = null;
  for (const line of text.split(/\r?\n/u).filter(Boolean)) {
    const key = line[0], value = line.slice(1);
    if (key === "p") { pid = Number(value); descriptor = null; if (!Number.isSafeInteger(pid) || pid <= 0) throw new Error("WORKBUDDY_WRITER_LSOF_PID_INVALID"); }
    else if (key === "f") { if (!pid) throw new Error("WORKBUDDY_WRITER_LSOF_ORDER_INVALID"); descriptor = { pid, fd: value, access: null, path: null }; records.push(descriptor); }
    else if (key === "a" && descriptor) descriptor.access = value.trim();
    else if (key === "n" && descriptor && descriptor.path == null) descriptor.path = value;
    else throw new Error("WORKBUDDY_WRITER_LSOF_FIELD_INVALID");
  }
  if (records.some(r => !r.path)) throw new Error("WORKBUDDY_WRITER_LSOF_PATH_MISSING");
  return records;
}
export function classifySharedWriters({ probe, workspace, before, after, handles }) {
  const root = before.get(probe.process?.pid), finalRoot = after.get(probe.process?.pid);
  if (probe.application?.bundle_id !== "com.tencent.workbuddy.mac" || probe.application?.identity_verified !== true
      || !root || !finalRoot || root.started_at !== probe.process.started_at || root.command !== probe.process.command
      || finalRoot.started_at !== root.started_at || finalRoot.command_sha256 !== root.command_sha256) throw new Error("WORKBUDDY_WRITER_APP_IDENTITY_CHANGED");
  const belongs = row => {
    const seen = new Set();
    while (row && !seen.has(row.pid)) {
      if (row.pid === root.pid) return true;
      seen.add(row.pid); row = before.get(row.ppid);
    }
    return false;
  };
  const shared = [], unknown = [];
  for (const handle of handles.filter(h => /^\d/u.test(h.fd) && !["r", "w", "u"].includes(h.access))) {
    unknown.push({ ...handle, reason: "access-mode-unavailable" });
  }
  for (const handle of handles.filter(h => /^\d/u.test(h.fd) && ["w", "u"].includes(h.access))) {
    if (handle.path !== workspace && !handle.path.startsWith(workspace + sep)) throw new Error("WORKBUDDY_WRITER_HANDLE_OUTSIDE_WORKSPACE");
    const owner = before.get(handle.pid), current = after.get(handle.pid);
    if (!owner || !current || owner.started_at !== current.started_at || owner.command_sha256 !== current.command_sha256) throw new Error("WORKBUDDY_WRITER_PID_CHANGED");
    const prefix = probe.application.path + "/Contents/Resources/app.asar.unpacked/node_modules/@tencent/tencent-docs-ai-engine/bin/";
    const knownEngine = owner.command.startsWith(prefix) && /^darwin-(?:arm64|x64)\/editor_sdk(?:\s|$)/u.test(owner.command.slice(prefix.length));
    const row = { ...handle, owner: { pid: owner.pid, ppid: owner.ppid, started_at: owner.started_at, command_sha256: owner.command_sha256 },
      belongs_to_verified_app: belongs(owner), known_shared_editor_engine: knownEngine };
    if (row.belongs_to_verified_app && knownEngine) shared.push(row); else unknown.push(row);
  }
  return { schema_version: "wildclawbench.workbuddy-shared-workspace-writers/v1",
    status: unknown.length ? "NEEDS_ATTENTION_UNKNOWN_WRITER" : shared.length ? "DEFER_FINALIZATION_UNTIL_HARNESS_SHUTDOWN" : "NO_SHARED_MUTABLE_WORKSPACE_HANDLES",
    workspace, app_process: { pid: root.pid, started_at: root.started_at, command_sha256: root.command_sha256 },
    shared_mutable_handles: shared, unknown_mutable_handles: unknown,
    workspace_or_processes_modified: false, note: "An open read/write handle is a potential writer, not proof of a business-content edit. Existing full-tree quiescence and immutable verification remain mandatory." };
}
export async function inspectSharedWriters({ workspace, appProbe, output }) {
  const root = await realpath(resolve(workspace));
  if (root !== resolve(workspace) || !(await lstat(root)).isDirectory()) throw new Error("WORKBUDDY_WRITER_WORKSPACE_INVALID");
  const probeBytes = await readFile(appProbe), probe = JSON.parse(probeBytes);
  const processArgs = ["-axo", "pid=,ppid=,lstart=,command="];
  const options = { timeout: 10000, maxBuffer: 8 * 1024 * 1024, env: { ...process.env, LC_ALL: "C", TZ: "UTC" } };
  const first = await execFile("/bin/ps", processArgs, options);
  let files;
  try { files = { ...(await execFile("/usr/sbin/lsof", ["-nP", "+D", root, "-F", "pfan"], options)), exit_code: 0 }; }
  catch (e) { if (e.code !== 1 || e.killed) throw e; files = { stdout: e.stdout, stderr: e.stderr, exit_code: 1 }; }
  const second = await execFile("/bin/ps", processArgs, options);
  const result = classifySharedWriters({ probe, workspace: root, before: parseProcesses(first.stdout), after: parseProcesses(second.stdout), handles: parseOpenFiles(files.stdout) });
  result.captured_at = new Date().toISOString(); result.app_probe_sha256 = sha(probeBytes);
  result.lsof = files;
  if (files.stderr?.trim() && result.status === "NO_SHARED_MUTABLE_WORKSPACE_HANDLES") result.status = "NEEDS_ATTENTION_LSOF_COVERAGE";
  await writeFile(output, JSON.stringify(result, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  return { status: result.status, shared_mutable_handles: result.shared_mutable_handles.length, unknown_mutable_handles: result.unknown_mutable_handles.length, output };
}
if (process.argv[1] && await realpath(resolve(process.argv[1])).catch(() => null) === await realpath(fileURLToPath(import.meta.url))) {
  const args = process.argv.slice(2), get = key => args[args.indexOf(key) + 1];
  if (!["--workspace", "--app-probe", "--output"].every(key => args.includes(key))) throw new Error("usage: shared-writers.mjs --workspace ABS --app-probe FROZEN_JSON --output NEW_JSON");
  inspectSharedWriters({ workspace: get("--workspace"), appProbe: get("--app-probe"), output: get("--output") })
    .then(result => console.log(JSON.stringify(result, null, 2))).catch(error => { console.error(error.message); process.exitCode = 1; });
}
