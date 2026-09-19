import { execFile as execFileCallback } from "node:child_process";
import { createHash } from "node:crypto";
import { lstat, realpath, stat } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

async function runCommand(command, args, overrides = {}) {
  if (overrides.runCommand) return overrides.runCommand(command, args);
  try {
    const result = await execFile(command, args, {
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
      env: { ...process.env, LC_ALL: "C", LANG: "C" },
    });
    return { code: 0, stdout: result.stdout, stderr: result.stderr };
  } catch (error) {
    return {
      code: Number.isInteger(error?.code) ? error.code : null,
      stdout: String(error?.stdout || ""),
      stderr: String(error?.stderr || error?.message || error),
    };
  }
}

export function parseMacProcessTable(stdout) {
  const output = [];
  const pattern = /^\s*(\d+)\s+(\d+)\s+(\d+)\s+([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+(.+?)\s*$/u;
  for (const line of String(stdout || "").split(/\r?\n/u)) {
    if (!line.trim()) continue;
    const match = line.match(pattern);
    if (!match) throw new Error(`无法解析 macOS 进程表行：${line.slice(0, 160)}`);
    output.push({
      pid: Number(match[1]),
      parent_pid: Number(match[2]) || null,
      process_group_id: Number(match[3]) || null,
      process_start_identity: match[4].replace(/\s+/gu, " "),
      executable_path: match[5],
    });
  }
  return output;
}

export function parseMacCwdRecords(stdout) {
  const output = [];
  let current = null;
  let currentDescriptor = null;
  for (const line of String(stdout || "").split(/\r?\n/u)) {
    if (!line) continue;
    const field = line[0];
    const value = line.slice(1);
    if (field === "p") {
      if (current?.cwd) output.push(current);
      current = { pid: Number(value), command_name: null, cwd: null };
      currentDescriptor = null;
    } else if (field === "c" && current) {
      current.command_name = value;
    } else if (field === "f" && current) {
      currentDescriptor = value;
    } else if (field === "n" && current && currentDescriptor === "cwd") {
      current.cwd = value;
    }
  }
  if (current?.cwd) output.push(current);
  return output.filter((item) => Number.isSafeInteger(item.pid) && item.pid > 0 && isAbsolute(item.cwd));
}

function processIdentityFingerprint(item) {
  return sha256(JSON.stringify({
    pid: item.pid,
    process_start_identity: item.process_start_identity,
    process_group_id: item.process_group_id,
    executable_path: item.executable_path,
  }));
}

function isPathWithin(candidateWorkspace, cwd) {
  if (!isAbsolute(candidateWorkspace) || !isAbsolute(cwd)) return false;
  const child = relative(resolve(candidateWorkspace), resolve(cwd));
  return child === "" || (child !== ".." && !child.startsWith(`..${sep}`) && !isAbsolute(child));
}

function normalizeProcess(item) {
  const processItem = {
    pid: Number(item.pid ?? item.ProcessId),
    parent_pid: Number(item.parent_pid ?? item.ParentProcessId) || null,
    process_group_id: Number(item.process_group_id ?? item.ProcessGroupId) || null,
    process_start_identity: String(item.process_start_identity ?? item.ProcessStartIdentity ?? "").trim(),
    executable_path: String(item.executable_path ?? item.ExecutablePath ?? "").trim(),
    command_name: item.command_name ? String(item.command_name) : null,
    cwd: item.cwd && isAbsolute(String(item.cwd)) ? resolve(String(item.cwd)) : null,
  };
  if (Number.isSafeInteger(processItem.pid) && processItem.pid > 0
      && processItem.process_start_identity && processItem.executable_path) {
    processItem.identity_fingerprint = processIdentityFingerprint(processItem);
  } else {
    processItem.identity_fingerprint = null;
  }
  return processItem;
}

export function selectDoubaoCandidateProcesses(processes, candidateWorkspace, { excludedPids = [] } = {}) {
  if (!isAbsolute(candidateWorkspace)) {
    throw new Error(`候选 workspace 必须是绝对路径：${candidateWorkspace}`);
  }
  const workspace = resolve(candidateWorkspace);
  const excluded = new Set(excludedPids.map(Number));
  const normalized = (processes || [])
    .map(normalizeProcess)
    .filter((item) => Number.isSafeInteger(item.pid) && item.pid > 0 && !excluded.has(item.pid));
  const byPid = new Map(normalized.map((item) => [item.pid, item]));
  const workspaceSeeds = normalized.filter((item) => item.cwd && isPathWithin(workspace, item.cwd));
  for (const seed of workspaceSeeds) {
    if (!seed.identity_fingerprint) {
      throw new Error(`候选进程 ${seed.pid} 缺少启动时间或可执行文件身份，拒绝清理`);
    }
  }
  const targetPids = new Set(workspaceSeeds.map((item) => item.pid));
  let changed = true;
  while (changed) {
    changed = false;
    for (const item of normalized) {
      if (!targetPids.has(item.pid) && item.parent_pid && targetPids.has(item.parent_pid)) {
        if (!item.identity_fingerprint) {
          throw new Error(`候选子进程 ${item.pid} 缺少启动时间或可执行文件身份，拒绝清理`);
        }
        targetPids.add(item.pid);
        changed = true;
      }
    }
  }
  const depthOf = (item) => {
    let depth = 0;
    let parentPid = item.parent_pid;
    const visited = new Set([item.pid]);
    while (parentPid && targetPids.has(parentPid) && !visited.has(parentPid)) {
      visited.add(parentPid);
      depth += 1;
      parentPid = byPid.get(parentPid)?.parent_pid ?? null;
    }
    return depth;
  };
  const targets = normalized
    .filter((item) => targetPids.has(item.pid))
    .map((item) => ({
      pid: item.pid,
      parent_pid: item.parent_pid,
      process_group_id: item.process_group_id,
      process_start_identity: item.process_start_identity,
      executable_path: item.executable_path,
      command_name: item.command_name,
      cwd: item.cwd,
      matched_by_workspace_cwd: workspaceSeeds.some((seed) => seed.pid === item.pid),
      descendant_depth: depthOf(item),
      identity_fingerprint: item.identity_fingerprint,
    }))
    .sort((left, right) => left.pid - right.pid);
  const rootPids = targets
    .filter((item) => !item.parent_pid || !targetPids.has(item.parent_pid))
    .map((item) => item.pid)
    .sort((left, right) => left - right);
  return {
    workspace_seed_pids: workspaceSeeds.map((item) => item.pid).sort((left, right) => left - right),
    root_pids: rootPids,
    targets,
  };
}

async function inspectOrdinaryWorkspace(candidateWorkspace) {
  if (!isAbsolute(candidateWorkspace)) throw new Error("候选 workspace 必须是绝对路径");
  const requestedPath = resolve(candidateWorkspace);
  const info = await lstat(requestedPath);
  if (!info.isDirectory() || info.isSymbolicLink()) {
    throw new Error(`候选 workspace 不是普通目录：${requestedPath}`);
  }
  const canonicalPath = await realpath(requestedPath);
  if (canonicalPath !== requestedPath) {
    throw new Error(`候选 workspace 路径含符号链接祖先：${requestedPath}`);
  }
  const identity = await stat(canonicalPath);
  return {
    requested_path: requestedPath,
    canonical_path: canonicalPath,
    device: String(identity.dev),
    inode: String(identity.ino),
  };
}

export async function readMacProcessInventory(overrides = {}) {
  const processArgs = ["-axo", "pid=,ppid=,pgid=,lstart=,comm="];
  const beforeResult = await runCommand("/bin/ps", processArgs, overrides);
  if (beforeResult.code !== 0) {
    throw new Error(`无法读取 macOS 进程身份：${beforeResult.stderr || `退出码 ${beforeResult.code}`}`);
  }
  const cwdResult = await runCommand("/usr/sbin/lsof", ["-nP", "-Fpcfn", "-d", "cwd"], overrides);
  if (cwdResult.code !== 0) {
    throw new Error(`无法读取 macOS 进程 cwd：${cwdResult.stderr || `退出码 ${cwdResult.code}`}`);
  }
  const afterResult = await runCommand("/bin/ps", processArgs, overrides);
  if (afterResult.code !== 0) {
    throw new Error(`无法复核 macOS 进程身份：${afterResult.stderr || `退出码 ${afterResult.code}`}`);
  }
  const beforeByPid = new Map(parseMacProcessTable(beforeResult.stdout).map((item) => [item.pid, item]));
  const cwdByPid = new Map(parseMacCwdRecords(cwdResult.stdout).map((item) => [item.pid, item]));
  return parseMacProcessTable(afterResult.stdout)
    .filter((item) => {
      const before = beforeByPid.get(item.pid);
      return before
        && before.process_group_id === item.process_group_id
        && before.process_start_identity === item.process_start_identity
        && before.executable_path === item.executable_path;
    })
    .map((item) => normalizeProcess({
      ...item,
      command_name: cwdByPid.get(item.pid)?.command_name ?? null,
      cwd: cwdByPid.get(item.pid)?.cwd ?? null,
    }));
}

export async function readMacProcessIdentity(pid, overrides = {}) {
  const inventory = await readMacProcessInventory(overrides);
  return inventory.find((item) => item.pid === Number(pid)) ?? null;
}

export async function snapshotDoubaoCandidateProcesses(candidateWorkspace, overrides = {}) {
  const platform = overrides.platform || process.platform;
  if (platform !== "darwin") {
    return {
      supported: false,
      workspace: null,
      workspace_seed_pids: [],
      root_pids: [],
      targets: [],
      reason: "DoubaoWork candidate process cleanup currently supports macOS only",
    };
  }
  const workspace = await inspectOrdinaryWorkspace(candidateWorkspace);
  const readInventory = overrides.readInventory || (() => readMacProcessInventory(overrides));
  const inventory = await readInventory();
  return {
    supported: true,
    captured_at: new Date().toISOString(),
    workspace,
    ...selectDoubaoCandidateProcesses(inventory, workspace.canonical_path, {
      excludedPids: overrides.excludedPids || [process.pid, process.ppid],
    }),
  };
}

function sameProcessIdentity(expected, actual) {
  if (!actual) return false;
  const normalized = normalizeProcess(actual);
  return expected.pid === normalized.pid
    && expected.identity_fingerprint === normalized.identity_fingerprint;
}

function sameWorkspaceIdentity(expected, actual) {
  return Boolean(expected && actual
    && expected.canonical_path === actual.canonical_path
    && String(expected.device) === String(actual.device)
    && String(expected.inode) === String(actual.inode));
}

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

export async function cleanupDoubaoCandidateProcesses(candidateWorkspace, overrides = {}) {
  const platform = overrides.platform || process.platform;
  if (platform !== "darwin") {
    return {
      supported: false,
      success: false,
      error_code: "UNSUPPORTED_PLATFORM",
      before: null,
      termination_attempts: [],
      after: null,
    };
  }
  const snapshot = overrides.snapshot || ((workspace) => snapshotDoubaoCandidateProcesses(workspace, overrides));
  const readInventory = overrides.readInventory || (() => readMacProcessInventory(overrides));
  const readIdentity = overrides.readIdentity || ((pid) => readMacProcessIdentity(pid, overrides));
  const readWorkspaceIdentity = overrides.readWorkspaceIdentity
    || (overrides.snapshot
      ? async () => before.workspace
      : () => inspectOrdinaryWorkspace(candidateWorkspace));
  const sendSignal = overrides.sendSignal || ((pid, signal) => process.kill(pid, signal));
  const wait = overrides.sleep || sleep;
  const now = overrides.now || (() => Date.now());
  const termGraceMilliseconds = Math.max(0, overrides.termGraceMilliseconds ?? 500);
  const killGraceMilliseconds = Math.max(0, overrides.killGraceMilliseconds ?? 500);
  const quietMilliseconds = Math.max(0, overrides.quietMilliseconds ?? 1000);
  const waitMilliseconds = Math.max(quietMilliseconds, overrides.waitMilliseconds ?? 5000);
  const before = await snapshot(candidateWorkspace);
  if (before.supported !== true) {
    return {
      supported: false,
      success: false,
      error_code: "UNSUPPORTED_PLATFORM",
      before,
      termination_attempts: [],
      after: before,
    };
  }
  const terminationAttempts = [];
  const identityErrors = [];
  const attempted = new Set();
  const blockedPids = new Set();
  const verifiedPids = new Set();
  const trackedTargets = new Map();
  const seenPidFingerprints = new Map();
  let workspaceIdentityValid = true;
  let lastWorkspaceIdentity = before.workspace;

  const recordIdentityError = (error) => {
    const key = JSON.stringify(error);
    if (!identityErrors.some((item) => JSON.stringify(item) === key)) identityErrors.push(error);
  };
  const mergeSnapshotTargets = (processSnapshot) => {
    if (!sameWorkspaceIdentity(before.workspace, processSnapshot.workspace)) {
      workspaceIdentityValid = false;
      lastWorkspaceIdentity = processSnapshot.workspace;
      recordIdentityError({
        code: "WORKSPACE_IDENTITY_CHANGED",
        expected_device: before.workspace?.device ?? null,
        expected_inode: before.workspace?.inode ?? null,
        observed_device: processSnapshot.workspace?.device ?? null,
        observed_inode: processSnapshot.workspace?.inode ?? null,
      });
      return;
    }
    lastWorkspaceIdentity = processSnapshot.workspace;
    for (const target of processSnapshot.targets) {
      const previousFingerprint = seenPidFingerprints.get(target.pid);
      if (previousFingerprint && previousFingerprint !== target.identity_fingerprint) {
        blockedPids.add(target.pid);
        recordIdentityError({
          pid: target.pid,
          code: "PID_IDENTITY_CHANGED",
          expected_identity: previousFingerprint,
          observed_identity: target.identity_fingerprint,
        });
        continue;
      }
      if (blockedPids.has(target.pid)) continue;
      seenPidFingerprints.set(target.pid, target.identity_fingerprint);
      if (!trackedTargets.has(target.pid)) trackedTargets.set(target.pid, target);
    }
  };
  mergeSnapshotTargets(before);

  const verifyWorkspaceIdentity = async () => {
    let actual;
    try {
      actual = await readWorkspaceIdentity();
    } catch (error) {
      workspaceIdentityValid = false;
      recordIdentityError({
        code: "WORKSPACE_IDENTITY_UNAVAILABLE",
        error: error instanceof Error ? error.message : String(error),
      });
      return false;
    }
    lastWorkspaceIdentity = actual;
    if (sameWorkspaceIdentity(before.workspace, actual)) return true;
    workspaceIdentityValid = false;
    recordIdentityError({
      code: "WORKSPACE_IDENTITY_CHANGED",
      expected_device: before.workspace?.device ?? null,
      expected_inode: before.workspace?.inode ?? null,
      observed_device: actual?.device ?? null,
      observed_inode: actual?.inode ?? null,
    });
    return false;
  };

  const noSuppliedIdentity = Symbol("no-supplied-identity");
  const inspectTrackedTarget = async (target, suppliedIdentity = noSuppliedIdentity) => {
    if (blockedPids.has(target.pid)) return { status: "blocked", target, actual: null };
    const actual = suppliedIdentity === noSuppliedIdentity
      ? await readIdentity(target.pid)
      : suppliedIdentity;
    if (!actual) return { status: "exited", target, actual: null };
    const normalizedActual = normalizeProcess(actual);
    if (!sameProcessIdentity(target, normalizedActual)) {
      blockedPids.add(target.pid);
      recordIdentityError({
        pid: target.pid,
        code: "PID_IDENTITY_CHANGED",
        expected_identity: target.identity_fingerprint,
        observed_identity: normalizedActual.identity_fingerprint,
      });
      return { status: "identity-changed", target, actual: normalizedActual };
    }
    if (!verifiedPids.has(target.pid)) {
      blockedPids.add(target.pid);
      recordIdentityError({
        pid: target.pid,
        code: "PROCESS_OWNERSHIP_UNVERIFIED",
        expected_workspace: before.workspace.canonical_path,
        observed_cwd: normalizedActual.cwd,
      });
      return { status: "ownership-unverified", target, actual: normalizedActual };
    }
    return { status: "alive", target, actual: normalizedActual };
  };

  const inspectTrackedTargets = async () => {
    const actualByPid = new Map();
    if (overrides.readIdentity) {
      for (const target of trackedTargets.values()) {
        actualByPid.set(target.pid, await readIdentity(target.pid));
      }
    } else {
      const inventory = await readInventory();
      for (const item of inventory) actualByPid.set(item.pid, item);
    }
    const resultsByPid = new Map();
    for (const target of trackedTargets.values()) {
      if (blockedPids.has(target.pid)) {
        resultsByPid.set(target.pid, { status: "blocked", target, actual: null });
        continue;
      }
      const actual = actualByPid.get(target.pid) ?? null;
      if (!actual) {
        resultsByPid.set(target.pid, { status: "exited", target, actual: null });
        continue;
      }
      const normalizedActual = normalizeProcess(actual);
      if (!sameProcessIdentity(target, normalizedActual)) {
        blockedPids.add(target.pid);
        recordIdentityError({
          pid: target.pid,
          code: "PID_IDENTITY_CHANGED",
          expected_identity: target.identity_fingerprint,
          observed_identity: normalizedActual.identity_fingerprint,
        });
        resultsByPid.set(target.pid, {
          status: "identity-changed",
          target,
          actual: normalizedActual,
        });
        continue;
      }
      resultsByPid.set(target.pid, { status: "identity-confirmed", target, actual: normalizedActual });
    }

    let changed = true;
    while (changed) {
      changed = false;
      for (const item of resultsByPid.values()) {
        if (item.status !== "identity-confirmed") continue;
        if (verifiedPids.has(item.target.pid)) {
          item.status = "alive";
          changed = true;
          continue;
        }
        if (item.target.matched_by_workspace_cwd
            && item.actual.cwd
            && isPathWithin(before.workspace.canonical_path, item.actual.cwd)) {
          verifiedPids.add(item.target.pid);
          item.status = "alive";
          changed = true;
          continue;
        }
        const parent = resultsByPid.get(item.actual.parent_pid);
        if (parent?.status === "alive" && verifiedPids.has(parent.target.pid)) {
          verifiedPids.add(item.target.pid);
          item.status = "alive";
          changed = true;
        }
      }
    }
    for (const item of resultsByPid.values()) {
      if (item.status !== "identity-confirmed") continue;
      blockedPids.add(item.target.pid);
      recordIdentityError({
        pid: item.target.pid,
        code: "PROCESS_OWNERSHIP_UNVERIFIED",
        expected_workspace: before.workspace.canonical_path,
        observed_cwd: item.actual.cwd,
        observed_parent_pid: item.actual.parent_pid,
      });
      item.status = "ownership-unverified";
    }
    return [...resultsByPid.values()];
  };

  const terminateTargets = async (trackedResults, signal, detectedLate = false) => {
    const ordered = trackedResults
      .filter((item) => item.status === "alive")
      .map((item) => item.target)
      .sort((left, right) => right.descendant_depth - left.descendant_depth || right.pid - left.pid);
    for (const target of ordered) {
      const key = `${target.identity_fingerprint}:${signal}`;
      if (attempted.has(key) || blockedPids.has(target.pid)) continue;
      attempted.add(key);
      if (!await verifyWorkspaceIdentity()) break;
      const inspected = await inspectTrackedTarget(target);
      if (inspected.status === "exited") {
        terminationAttempts.push({
          pid: target.pid,
          signal,
          detected_late: detectedLate,
          result: "already-exited",
          expected_identity: target.identity_fingerprint,
          observed_identity: null,
        });
        continue;
      }
      if (inspected.status !== "alive") {
        terminationAttempts.push({
          pid: target.pid,
          signal,
          detected_late: detectedLate,
          result: inspected.status === "ownership-unverified"
            ? "refused-ownership-unverified"
            : "refused-identity-changed",
          expected_identity: target.identity_fingerprint,
          observed_identity: inspected.actual?.identity_fingerprint ?? null,
        });
        continue;
      }
      try {
        await sendSignal(target.pid, signal);
        terminationAttempts.push({
          pid: target.pid,
          signal,
          detected_late: detectedLate,
          result: "signaled",
          expected_identity: target.identity_fingerprint,
          observed_identity: inspected.actual.identity_fingerprint,
        });
      } catch (error) {
        if (error?.code === "ESRCH") {
          terminationAttempts.push({
            pid: target.pid,
            signal,
            detected_late: detectedLate,
            result: "already-exited",
            expected_identity: target.identity_fingerprint,
            observed_identity: inspected.actual.identity_fingerprint,
          });
          continue;
        }
        recordIdentityError({
          pid: target.pid,
          code: "SIGNAL_FAILED",
          error: error instanceof Error ? error.message : String(error),
        });
        terminationAttempts.push({
          pid: target.pid,
          signal,
          detected_late: detectedLate,
          result: "signal-failed",
          expected_identity: target.identity_fingerprint,
          observed_identity: inspected.actual.identity_fingerprint,
        });
      }
    }
  };

  await terminateTargets(await inspectTrackedTargets(), "SIGTERM");
  if (termGraceMilliseconds > 0) await wait(termGraceMilliseconds);
  let after = await snapshot(candidateWorkspace);
  mergeSnapshotTargets(after);
  let trackedResults = await inspectTrackedTargets();
  if (trackedResults.some((item) => item.status === "alive")) {
    await terminateTargets(trackedResults, "SIGKILL");
    if (killGraceMilliseconds > 0) await wait(killGraceMilliseconds);
    after = await snapshot(candidateWorkspace);
    mergeSnapshotTargets(after);
    trackedResults = await inspectTrackedTargets();
  }

  const deadline = now() + waitMilliseconds;
  const hasTrackedResidue = () => trackedResults.some((item) => item.status === "alive");
  let quietSince = hasTrackedResidue() || after.targets.length ? null : now();
  let lateProcessDetected = false;
  while (now() < deadline) {
    if (!hasTrackedResidue() && !after.targets.length
        && quietSince !== null && now() - quietSince >= quietMilliseconds) break;
    await wait(Math.min(250, Math.max(1, deadline - now())));
    after = await snapshot(candidateWorkspace);
    mergeSnapshotTargets(after);
    trackedResults = await inspectTrackedTargets();
    if (hasTrackedResidue() || after.targets.length) {
      lateProcessDetected ||= quietSince !== null;
      quietSince = null;
      await terminateTargets(trackedResults, "SIGTERM", true);
      if (termGraceMilliseconds > 0) await wait(termGraceMilliseconds);
      after = await snapshot(candidateWorkspace);
      mergeSnapshotTargets(after);
      trackedResults = await inspectTrackedTargets();
      if (hasTrackedResidue() || after.targets.length) {
        await terminateTargets(trackedResults, "SIGKILL", true);
        if (killGraceMilliseconds > 0) await wait(killGraceMilliseconds);
        after = await snapshot(candidateWorkspace);
        mergeSnapshotTargets(after);
        trackedResults = await inspectTrackedTargets();
      }
    }
    if (!hasTrackedResidue() && !after.targets.length && quietSince === null) quietSince = now();
  }
  const quietObservedMilliseconds = quietSince === null ? 0 : Math.max(0, now() - quietSince);
  const success = identityErrors.length === 0
    && workspaceIdentityValid
    && !hasTrackedResidue()
    && after.targets.length === 0
    && quietObservedMilliseconds >= quietMilliseconds;
  return {
    supported: true,
    success,
    error_code: success
      ? null
      : !workspaceIdentityValid
        ? "WORKSPACE_IDENTITY_VERIFICATION_FAILED"
        : identityErrors.length
          ? "PROCESS_IDENTITY_VERIFICATION_FAILED"
          : hasTrackedResidue()
            ? "PROCESS_RESIDUE_REMAINS"
            : after.targets.length
              ? "PROCESS_RESIDUE_REMAINS"
              : "QUIET_WINDOW_INCOMPLETE",
    quiet_window_milliseconds: quietMilliseconds,
    quiet_observed_milliseconds: quietObservedMilliseconds,
    late_process_detected: lateProcessDetected,
    before,
    termination_attempts: terminationAttempts,
    identity_errors: identityErrors,
    locked_workspace_identity: before.workspace,
    observed_workspace_identity: lastWorkspaceIdentity,
    tracked_residue: trackedResults
      .filter((item) => item.status === "alive")
      .map((item) => item.target),
    after,
  };
}
