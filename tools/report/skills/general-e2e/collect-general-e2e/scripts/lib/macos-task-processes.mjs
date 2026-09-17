import { createHash } from "node:crypto";
import { basename, isAbsolute, relative, resolve, sep } from "node:path";
import { realpath } from "node:fs/promises";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";

const PROCESS_LINE = /^\s*(\d+)\s+(\d+)\s+(\S{3})\s+(\S{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})\s+(.*)$/u;

function sha256(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function inside(root, candidate) {
  const rel = relative(root, candidate);
  return rel === "" || (!rel.startsWith(`..${sep}`) && rel !== ".." && !isAbsolute(rel));
}

function commandName(command) {
  const text = String(command || "").trim();
  if (!text) return "unknown";
  if (text.startsWith('"')) {
    const end = text.indexOf('"', 1);
    if (end > 1) return basename(text.slice(1, end));
  }
  return basename(text.split(/\s+/u, 1)[0]);
}

export function commandReferencesWorkspace(command, workspace) {
  const text = String(command || "");
  if (!text || !workspace) return false;
  let index = text.indexOf(workspace);
  while (index >= 0) {
    const before = index === 0 ? "" : text[index - 1];
    const after = text[index + workspace.length] || "";
    const beforeBoundary = !before || /[\s"'=:(]/u.test(before);
    const afterBoundary = !after || /[\s"'/:),;]/u.test(after);
    if (beforeBoundary && afterBoundary) return true;
    index = text.indexOf(workspace, index + 1);
  }
  return false;
}

export function parseDarwinProcessTable(stdout) {
  const rows = [];
  for (const line of String(stdout || "").split(/\r?\n/u)) {
    if (!line.trim()) continue;
    const match = line.match(PROCESS_LINE);
    if (!match) continue;
    const pid = Number(match[1]);
    const parentPid = Number(match[2]);
    if (!Number.isSafeInteger(pid) || pid <= 0 || !Number.isSafeInteger(parentPid)) continue;
    const command = match[8];
    rows.push({
      pid,
      parent_pid: parentPid > 0 ? parentPid : null,
      started_at: `${match[3]} ${match[4]} ${match[5]} ${match[6]} ${match[7]}`,
      command,
      command_name: commandName(command),
      command_sha256: sha256(command),
    });
  }
  return rows;
}

export function parseDarwinLsofCwd(stdout, workspace) {
  const result = new Set();
  let pid = null;
  for (const line of String(stdout || "").split(/\r?\n/u)) {
    if (line.startsWith("p")) {
      const value = Number(line.slice(1));
      pid = Number.isSafeInteger(value) && value > 0 ? value : null;
    } else if (line.startsWith("n") && pid) {
      const candidate = line.slice(1);
      if (candidate && inside(workspace, resolve(candidate))) result.add(pid);
    }
  }
  return result;
}

function ancestorPids(processes, pid) {
  const byPid = new Map(processes.map((item) => [item.pid, item]));
  const result = new Set([pid, 1]);
  let current = byPid.get(pid)?.parent_pid;
  while (current && !result.has(current)) {
    result.add(current);
    current = byPid.get(current)?.parent_pid;
  }
  return result;
}

function publicProcess(item, seedKinds, targets) {
  return {
    pid: item.pid,
    parent_pid: item.parent_pid,
    command_name: item.command_name,
    started_at: item.started_at,
    command_sha256: item.command_sha256,
    matched_by_command: seedKinds.get(item.pid)?.has("command") || false,
    matched_by_cwd: seedKinds.get(item.pid)?.has("cwd") || false,
    descendant_of_seed: !seedKinds.has(item.pid) && targets.has(item.pid),
  };
}

export function selectDarwinTaskProcesses(processes, workspace, options = {}) {
  if (!String(workspace || "").startsWith("/")) {
    throw new Error(`TASK_WORKSPACE_NOT_ABSOLUTE: ${workspace}`);
  }
  const excluded = new Set(options.excludedPids || []);
  const cwdPids = new Set(options.cwdPids || []);
  const normalized = (processes || []).filter((item) => Number.isSafeInteger(item?.pid) && item.pid > 0);
  const byPid = new Map(normalized.map((item) => [item.pid, item]));
  const seedKinds = new Map();
  const addSeed = (pid, kind) => {
    if (excluded.has(pid) || !byPid.has(pid)) return;
    if (!seedKinds.has(pid)) seedKinds.set(pid, new Set());
    seedKinds.get(pid).add(kind);
  };
  for (const item of normalized) {
    if (commandReferencesWorkspace(item.command, workspace)) addSeed(item.pid, "command");
  }
  for (const pid of cwdPids) addSeed(pid, "cwd");

  const targets = new Set(seedKinds.keys());
  let changed = true;
  while (changed) {
    changed = false;
    for (const item of normalized) {
      if (!excluded.has(item.pid) && !targets.has(item.pid)
          && item.parent_pid && targets.has(item.parent_pid)) {
        targets.add(item.pid);
        changed = true;
      }
    }
  }
  const rootPids = [...targets].filter((pid) => {
    let parentPid = byPid.get(pid)?.parent_pid;
    const visited = new Set();
    while (parentPid && !visited.has(parentPid)) {
      if (targets.has(parentPid)) return false;
      visited.add(parentPid);
      parentPid = byPid.get(parentPid)?.parent_pid;
    }
    return true;
  }).sort((left, right) => left - right);
  return {
    seed_pids: [...seedKinds.keys()].sort((left, right) => left - right),
    root_pids: rootPids,
    targets: normalized
      .filter((item) => targets.has(item.pid))
      .map((item) => publicProcess(item, seedKinds, targets))
      .sort((left, right) => left.pid - right.pid),
  };
}

async function processTable(runCommand) {
  const result = await runCommand(
    "/bin/ps",
    ["-axo", "pid=,ppid=,lstart=,command="],
    { capture: true, allowFailure: true },
  );
  if (result.code !== 0) {
    throw new Error(`TASK_PROCESS_TABLE_FAILED: ${String(result.stderr || `exit=${result.code}`).trim()}`);
  }
  return parseDarwinProcessTable(result.stdout);
}

async function cwdProcessIds(workspace, runCommand) {
  const result = await runCommand(
    "/usr/sbin/lsof",
    ["-n", "-P", "-F", "pcn", "-a", "-d", "cwd", "+D", workspace],
    { capture: true, allowFailure: true },
  );
  if (![0, 1].includes(result.code)) {
    throw new Error(`TASK_PROCESS_CWD_SCAN_FAILED: ${String(result.stderr || `exit=${result.code}`).trim()}`);
  }
  return parseDarwinLsofCwd(result.stdout, workspace);
}

export async function snapshotDarwinTaskProcesses(candidateWorkspace, overrides = {}) {
  const platform = overrides.platform || process.platform;
  if (platform !== "darwin") {
    throw new Error(`TASK_PROCESS_CLEANUP_PLATFORM_UNSUPPORTED: ${platform}`);
  }
  const runCommand = overrides.runCommand || runCapture;
  const workspace = await (overrides.realpathPath || realpath)(candidateWorkspace);
  const processes = await processTable(runCommand);
  const cwdPids = await cwdProcessIds(workspace, runCommand);
  const excluded = new Set([
    ...ancestorPids(processes, process.pid),
    ...(overrides.excludedPids || []),
  ]);
  return {
    supported: true,
    platform: "darwin",
    workspace,
    ...selectDarwinTaskProcesses(processes, workspace, {
      cwdPids,
      excludedPids: [...excluded],
    }),
  };
}

function sameProcessIdentity(expected, actual) {
  return Boolean(actual)
    && expected.pid === actual.pid
    && expected.started_at === actual.started_at
    && expected.command_sha256 === actual.command_sha256;
}

function targetDepth(target, byPid) {
  let depth = 0;
  let parentPid = target.parent_pid;
  const visited = new Set();
  while (parentPid && !visited.has(parentPid) && byPid.has(parentPid)) {
    visited.add(parentPid);
    depth += 1;
    parentPid = byPid.get(parentPid).parent_pid;
  }
  return depth;
}

export async function terminateDarwinTaskProcesses(candidateWorkspace, overrides = {}) {
  const snapshot = overrides.snapshot
    || ((workspace) => snapshotDarwinTaskProcesses(workspace, overrides));
  const runCommand = overrides.runCommand || runCapture;
  const wait = overrides.sleep
    || ((milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds)));
  const now = overrides.now || (() => Date.now());
  const quietMilliseconds = Math.max(0, Number(overrides.quietMilliseconds ?? 5_000));
  const waitMilliseconds = Math.max(quietMilliseconds, Number(overrides.waitMilliseconds ?? 15_000));
  const termGraceMilliseconds = Math.max(0, Number(overrides.termGraceMilliseconds ?? 1_000));
  const attempts = [];
  const attempted = new Set();

  const signal = overrides.signalProcess || (async (identity, signalName) => {
    const table = await processTable(runCommand);
    const actual = table.find((item) => item.pid === identity.pid) || null;
    if (!sameProcessIdentity(identity, actual)) {
      return { identity_matched: false, exit_code: null, error: "process identity changed or exited" };
    }
    const result = await runCommand(
      "/bin/kill",
      [signalName === "SIGKILL" ? "-KILL" : "-TERM", String(identity.pid)],
      { capture: true, allowFailure: true },
    ).catch((error) => ({ code: null, stdout: "", stderr: error instanceof Error ? error.message : String(error) }));
    return {
      identity_matched: true,
      exit_code: result.code,
      error: result.code === 0 ? null : String(result.stderr || `exit=${result.code}`).trim(),
    };
  });

  const terminateSnapshot = async (value, late) => {
    const byPid = new Map(value.targets.map((item) => [item.pid, item]));
    const ordered = [...value.targets].sort((left, right) => {
      const depth = targetDepth(right, byPid) - targetDepth(left, byPid);
      return depth || right.pid - left.pid;
    });
    for (const target of ordered) {
      const key = `${target.pid}:${target.started_at}:${target.command_sha256}`;
      if (attempted.has(key)) continue;
      attempted.add(key);
      const term = await signal(target, "SIGTERM");
      attempts.push({
        pid: target.pid,
        started_at: target.started_at,
        command_sha256: target.command_sha256,
        signal: "SIGTERM",
        detected_late: late,
        ...term,
      });
    }
    if (ordered.length && termGraceMilliseconds) await wait(termGraceMilliseconds);
    const remaining = await snapshot(candidateWorkspace);
    const remainingByPid = new Map(remaining.targets.map((item) => [item.pid, item]));
    for (const target of ordered) {
      const actual = remainingByPid.get(target.pid);
      if (!sameProcessIdentity(target, actual)) continue;
      const killed = await signal(target, "SIGKILL");
      attempts.push({
        pid: target.pid,
        started_at: target.started_at,
        command_sha256: target.command_sha256,
        signal: "SIGKILL",
        detected_late: late,
        ...killed,
      });
    }
  };

  const before = await snapshot(candidateWorkspace);
  await terminateSnapshot(before, false);
  let after = await snapshot(candidateWorkspace);
  const startedAt = now();
  const deadline = startedAt + waitMilliseconds;
  let quietSince = after.targets.length ? null : now();
  let lateProcessDetected = false;
  while (now() < deadline) {
    if (!after.targets.length && quietSince !== null && now() - quietSince >= quietMilliseconds) break;
    await wait(Math.min(250, Math.max(1, deadline - now())));
    after = await snapshot(candidateWorkspace);
    if (after.targets.length) {
      lateProcessDetected ||= quietSince !== null;
      quietSince = null;
      await terminateSnapshot(after, true);
      after = await snapshot(candidateWorkspace);
    }
    if (!after.targets.length && quietSince === null) quietSince = now();
  }
  const quietObservedMilliseconds = quietSince === null ? 0 : Math.max(0, now() - quietSince);
  return {
    schema_version: "wildclawbench.general-e2e-task-process-cleanup/v1",
    supported: true,
    platform: "darwin",
    success: after.targets.length === 0 && quietObservedMilliseconds >= quietMilliseconds,
    quiet_window_milliseconds: quietMilliseconds,
    quiet_observed_milliseconds: quietObservedMilliseconds,
    late_process_detected: lateProcessDetected,
    before,
    termination_attempts: attempts,
    after,
  };
}
