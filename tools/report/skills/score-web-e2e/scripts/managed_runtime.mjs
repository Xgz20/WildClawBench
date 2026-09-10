#!/usr/bin/env node
import { spawn, execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { loadCandidateArtifact, verifyWorkspace } from "./workspace-integrity.mjs";

const RUNTIME_SCHEMA = "wildclawbench.web-e2e-scoring-runtime/v1";
export const RUNTIME_PORT_OVERRIDE_SCHEMA = "wildclawbench.web-e2e-runtime-port-override/v1";
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROCESS_WRAPPER_FILE = path.join(SCRIPT_DIR, "managed-process-worker.mjs");
const PORT_CONFLICT_PATTERNS = [
  /EADDRINUSE/i,
  /address\s+already\s+in\s+use/i,
  /port\s+[^\r\n]*already\s+in\s+use/i,
  /端口[^\r\n]*(?:占用|已被使用|正在使用)/i,
];

function taskPaths(taskRoot) {
  const root = fs.realpathSync(path.resolve(taskRoot));
  return {
    root,
    candidate: path.join(root, "workspace"),
    privateRoot: path.join(root, "private-scoring"),
    lockFile: path.join(root, "private-scoring", "candidate_artifact.json"),
    runtime: path.join(root, "private-scoring", "runtime-workspace"),
    stateFile: path.join(root, "private-scoring", "runtime-state.json"),
    logRoot: path.join(root, "private-scoring", "runtime-logs"),
    portOverrideFile: path.join(root, "private-scoring", "runtime-port-override.json"),
  };
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function loadJson(filename) {
  const value = JSON.parse(fs.readFileSync(filename, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error(`JSON 顶层必须是对象：${filename}`);
  return value;
}

function writeJson(filename, value) {
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  const temporary = `${filename}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  fs.renameSync(temporary, filename);
}

function candidateCheck(paths, stage) {
  const lock = loadCandidateArtifact(paths.lockFile);
  return { lock, check: verifyWorkspace(paths.candidate, lock.expected_sha256, stage) };
}

function validateRuntimeState(state, lock) {
  if (state.schema_version !== RUNTIME_SCHEMA
    || state.task_id !== lock.task_id
    || state.candidate_sha256 !== lock.expected_sha256) {
    throw new Error("runtime-state.json 与当前候选产物身份不一致");
  }
}

function loadPortOverrideAudit(paths, lock) {
  if (!fs.existsSync(paths.portOverrideFile)) {
    return {
      schema_version: RUNTIME_PORT_OVERRIDE_SCHEMA,
      task_id: lock.task_id,
      candidate_sha256: lock.expected_sha256,
      overrides: [],
    };
  }
  const audit = loadJson(paths.portOverrideFile);
  if (audit.schema_version !== RUNTIME_PORT_OVERRIDE_SCHEMA
    || audit.task_id !== lock.task_id
    || audit.candidate_sha256 !== lock.expected_sha256
    || !Array.isArray(audit.overrides)) {
    throw new Error("runtime-port-override.json 与当前候选产物身份不一致");
  }
  return audit;
}

function makeUserWritable(root) {
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const filename = path.join(root, entry.name);
    if (entry.isSymbolicLink()) continue;
    if (entry.isDirectory()) makeUserWritable(filename);
    const mode = fs.lstatSync(filename).mode & 0o777;
    fs.chmodSync(filename, mode | 0o200 | (entry.isDirectory() ? 0o100 : 0));
  }
  const mode = fs.lstatSync(root).mode & 0o777;
  fs.chmodSync(root, mode | 0o300);
}

export function prepareRuntime(taskRoot) {
  const paths = taskPaths(taskRoot);
  const before = candidateCheck(paths, "prepare-runtime:before-copy");
  const priorPortOverrides = loadPortOverrideAudit(paths, before.lock).overrides;
  if (fs.existsSync(paths.runtime)) throw new Error(`评分运行时副本已存在，拒绝覆盖：${paths.runtime}`);
  try {
    fs.cpSync(paths.candidate, paths.runtime, { recursive: true, dereference: false, errorOnExist: true, force: false });
    const runtimeCopy = verifyWorkspace(paths.runtime, before.lock.expected_sha256, "prepare-runtime:copy");
    makeUserWritable(paths.runtime);
    const after = candidateCheck(paths, "prepare-runtime:after-copy");
    const state = {
      schema_version: RUNTIME_SCHEMA,
      task_id: before.lock.task_id,
      created_at: new Date().toISOString(),
      runtime_workspace: "private-scoring/runtime-workspace",
      candidate_sha256: before.lock.expected_sha256,
      candidate_checks: [before.check, after.check],
      port_overrides: priorPortOverrides,
      runtime_copy_check: runtimeCopy,
      service: null,
      cleanup: null,
    };
    writeJson(paths.stateFile, state);
    return { paths, state };
  } catch (error) {
    if (fs.existsSync(paths.runtime)) fs.rmSync(paths.runtime, { recursive: true });
    candidateCheck(paths, "prepare-runtime:failed-cleanup");
    throw error;
  }
}

function validatePort(value, label) {
  if (!/^\d+$/.test(String(value))) throw new Error(`${label} 必须是 1..65535 的整数`);
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) throw new Error(`${label} 必须是 1..65535 的整数`);
  return parsed;
}

function pathInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative !== "" && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

function resolveCandidateStaticRoot(paths, raw) {
  const relative = String(raw || ".").trim() || ".";
  if (path.isAbsolute(relative) || relative.split(/[\\/]+/).includes("..")) {
    throw new Error("--root 必须是 workspace 内的相对目录");
  }
  const declared = path.resolve(paths.candidate, relative);
  if (!fs.existsSync(declared)) throw new Error(`静态站点目录不存在：${relative}`);
  const info = fs.lstatSync(declared);
  if (info.isSymbolicLink() || !info.isDirectory()) {
    throw new Error("--root 必须是 workspace 内的普通目录");
  }
  const candidateRoot = fs.realpathSync(paths.candidate);
  const canonical = fs.realpathSync(declared);
  if (canonical !== candidateRoot && !pathInside(candidateRoot, canonical)) {
    throw new Error("--root 不能越过 workspace 边界");
  }
  return {
    filename: canonical,
    relative: path.relative(candidateRoot, canonical).split(path.sep).join("/") || ".",
  };
}

function resolveRuntimeSourceFile(paths, raw) {
  const relative = String(raw || "");
  if (!relative || path.isAbsolute(relative) || relative.split(/[\\/]+/).includes("..")) {
    throw new Error("端口补丁文件必须是 runtime-workspace 内的相对路径");
  }
  const declared = path.resolve(paths.runtime, relative);
  if (!fs.existsSync(declared)) throw new Error(`端口补丁文件不存在：${relative}`);
  const runtimeRoot = fs.realpathSync(paths.runtime);
  const canonical = fs.realpathSync(declared);
  if (!pathInside(runtimeRoot, canonical) || !fs.lstatSync(canonical).isFile()) {
    throw new Error("端口补丁文件必须是 runtime-workspace 内的普通文件");
  }
  return { filename: canonical, relative: path.relative(runtimeRoot, canonical).split(path.sep).join("/") };
}

function resolveConflictEvidence(paths, state, raw) {
  const recorded = String(state.service?.stderr || "");
  if (!recorded) throw new Error("失败服务没有记录端口冲突日志");
  const expected = path.resolve(paths.root, recorded);
  const requested = path.resolve(paths.root, String(raw || recorded));
  if (requested !== expected || !fs.existsSync(expected) || fs.lstatSync(expected).isSymbolicLink()) {
    throw new Error("端口冲突证据必须是受管启动记录的 stderr 日志");
  }
  const canonicalLogs = fs.realpathSync(paths.logRoot);
  const canonicalEvidence = fs.realpathSync(expected);
  if (!pathInside(canonicalLogs, canonicalEvidence) || !fs.lstatSync(canonicalEvidence).isFile()) {
    throw new Error("端口冲突证据必须位于 private-scoring/runtime-logs 内");
  }
  return { filename: canonicalEvidence, relative: path.relative(paths.root, canonicalEvidence).split(path.sep).join("/") };
}

export function overrideRuntimePort(taskRoot, relativeFile, fromValue, toValue, evidenceFile = "") {
  const paths = taskPaths(taskRoot);
  const beforeCandidate = candidateCheck(paths, "port-override:before");
  const fromPort = validatePort(fromValue, "--from-port");
  const toPort = validatePort(toValue, "--to-port");
  if (fromPort === toPort) throw new Error("新端口必须与冲突端口不同");
  if (!fs.existsSync(paths.runtime) || !fs.existsSync(paths.stateFile)) {
    throw new Error("端口补丁前必须先 prepare 运行时副本，并通过受管 start 留下冲突证据");
  }
  const state = loadJson(paths.stateFile);
  validateRuntimeState(state, beforeCandidate.lock);
  if (state.service?.pid && processIdentity(Number(state.service.pid))) {
    throw new Error(`评分服务仍在运行，不能修改运行时副本：PID ${state.service.pid}`);
  }
  if (state.service?.status !== "START_FAILED_STOPPED") {
    throw new Error("只有受管启动因端口冲突失败并完成精确清理后，才允许端口补丁");
  }
  const attemptedUrl = new URL(validateLoopbackUrl(String(state.service.expected_url || "")));
  const attemptedPort = validatePort(attemptedUrl.port || (attemptedUrl.protocol === "https:" ? 443 : 80), "失败服务端口");
  if (attemptedPort !== fromPort) throw new Error("--from-port 与受管启动失败时使用的端口不一致");

  const evidence = resolveConflictEvidence(paths, state, evidenceFile);
  const evidenceBytes = fs.readFileSync(evidence.filename);
  const evidenceText = evidenceBytes.toString("utf8");
  const portPattern = new RegExp(`(^|\\D)${fromPort}(?!\\d)`);
  if (!PORT_CONFLICT_PATTERNS.some((pattern) => pattern.test(evidenceText)) || !portPattern.test(evidenceText)) {
    throw new Error(`受管启动日志不能证明端口 ${fromPort} 冲突`);
  }

  const source = resolveRuntimeSourceFile(paths, relativeFile);
  const beforeBytes = fs.readFileSync(source.filename);
  const beforeText = beforeBytes.toString("utf8");
  if (!Buffer.from(beforeText, "utf8").equals(beforeBytes)) throw new Error("端口补丁文件必须是有效 UTF-8 文本");
  const numericToken = new RegExp(`(?<!\\d)${fromPort}(?!\\d)`, "g");
  const matches = [...beforeText.matchAll(numericToken)];
  if (matches.length !== 1) {
    throw new Error(`端口补丁要求旧端口在目标文件中唯一匹配，实际 ${matches.length} 处`);
  }
  const afterText = beforeText.replace(numericToken, String(toPort));
  const afterBytes = Buffer.from(afterText, "utf8");
  const audit = loadPortOverrideAudit(paths, beforeCandidate.lock);
  const evidenceSnapshot = path.join(paths.logRoot, `port-conflict-${String(audit.overrides.length + 1).padStart(3, "0")}.log`);
  if (fs.existsSync(evidenceSnapshot)) throw new Error(`端口冲突证据快照已存在，拒绝覆盖：${evidenceSnapshot}`);
  const mode = fs.statSync(source.filename).mode & 0o777;
  const temporary = `${source.filename}.port-override-${process.pid}`;
  fs.writeFileSync(temporary, afterBytes, { mode });
  fs.writeFileSync(evidenceSnapshot, evidenceBytes, { mode: 0o600 });
  fs.renameSync(temporary, source.filename);

  const afterCandidate = candidateCheck(paths, "port-override:after");
  const event = {
    recorded_at: new Date().toISOString(),
    runtime_created_at: state.created_at,
    conflict: {
      service_status: state.service.status,
      attempted_url: attemptedUrl.href,
      command: state.service.command,
      source_log_path: evidence.relative,
      evidence_path: path.relative(paths.root, evidenceSnapshot).split(path.sep).join("/"),
      evidence_sha256: sha256(evidenceBytes),
    },
    patch: {
      file: source.relative,
      from_port: fromPort,
      to_port: toPort,
      occurrence_count: 1,
      method: "single-numeric-token-replacement",
      before_sha256: sha256(beforeBytes),
      after_sha256: sha256(afterBytes),
    },
  };
  audit.overrides.push(event);
  writeJson(paths.portOverrideFile, audit);
  state.port_overrides = audit.overrides;
  state.candidate_checks.push(beforeCandidate.check, afterCandidate.check);
  writeJson(paths.stateFile, state);
  return { paths, state };
}

function processCwd(pid) {
  if (process.platform === "linux") {
    try {
      return fs.realpathSync(`/proc/${pid}/cwd`);
    } catch {
      return null;
    }
  }
  try {
    const output = execFileSync("/usr/sbin/lsof", ["-a", "-p", String(pid), "-d", "cwd", "-Fn"], { encoding: "utf8" });
    const row = output.split(/\r?\n/).find((line) => line.startsWith("n"));
    return row ? fs.realpathSync(row.slice(1)) : null;
  } catch {
    return null;
  }
}

export function processIdentity(pid, overrides = {}) {
  if (!Number.isInteger(pid) || pid <= 0) return null;
  const platform = overrides.platform || process.platform;
  const runSync = overrides.execFileSync || execFileSync;
  const probePid = overrides.probePid || ((value) => process.kill(value, 0));
  try {
    probePid(pid);
  } catch (error) {
    if (error?.code !== "EPERM") return null;
  }
  if (platform === "win32") {
    const script = `$process = Get-CimInstance Win32_Process -Filter "ProcessId = ${pid}"; if ($process) { $process | Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine | ConvertTo-Json -Compress }`;
    const output = runSync(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      { encoding: "utf8" },
    ).trim();
    if (!output) return null;
    const info = JSON.parse(output);
    if (Number(info.ProcessId) !== pid || !info.CreationDate || !info.CommandLine) {
      throw new Error(`无法读取评分服务 Windows 进程身份：PID ${pid}`);
    }
    return {
      pid,
      pgid: pid,
      started_at_text: String(info.CreationDate),
      command: String(info.CommandLine),
      cwd: null,
      executable_path: info.ExecutablePath || null,
      process_group_mode: "windows-process-tree",
    };
  }
  const output = runSync("/bin/ps", ["-p", String(pid), "-o", "pgid=,stat=,lstart=,command="], { encoding: "utf8" }).trim();
  const match = output.match(/^(\d+)\s+(\S+)\s+(.{24})\s+(.+)$/);
  if (!match) throw new Error(`无法读取评分服务进程身份：PID ${pid}`);
  if (match[2].startsWith("Z")) return null;
  return {
    pid,
    pgid: Number(match[1]),
    started_at_text: match[3].trim(),
    command: match[4],
    cwd: processCwd(pid),
    process_group_mode: "posix-process-group",
  };
}

export function processTerminationInvocation(identity, { force = false, platform = process.platform } = {}) {
  if (platform === "win32") {
    return {
      command: "taskkill.exe",
      args: ["/PID", String(identity.pid), "/T", ...(force ? ["/F"] : [])],
    };
  }
  return { signal: force ? "SIGKILL" : "SIGTERM", pid: -identity.pgid };
}

export function windowsCommandIncludesPath(commandLine, expectedPath) {
  const normalize = (value) => String(value || "")
    .replaceAll("/", "\\")
    .toLowerCase();
  const expected = normalize(expectedPath);
  return Boolean(expected) && normalize(commandLine).includes(expected);
}

export function terminateProcessIdentity(identity, force = false) {
  const invocation = processTerminationInvocation(identity, { force });
  if (invocation.command) {
    try {
      return execFileSync(invocation.command, invocation.args, { encoding: "utf8" });
    } catch (error) {
      if (!processIdentity(identity.pid)) return "";
      if (!force) return error instanceof Error ? error.message : String(error);
      throw error;
    }
  }
  process.kill(invocation.pid, invocation.signal);
  return "";
}

function validateLoopbackUrl(raw) {
  const url = new URL(raw);
  if (!new Set(["127.0.0.1", "localhost", "::1"]).has(url.hostname)) throw new Error("评分站点 URL 必须使用本机回环地址");
  return url.href;
}

async function waitForUrl(url, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { redirect: "manual" });
      if (response.status > 0) return response.status;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
  }
  throw new Error(`评分服务未在时限内就绪：${url}${lastError ? ` (${lastError})` : ""}`);
}

export async function startManagedService(taskRoot, command, expectedUrl, { useCandidate = false } = {}) {
  if (!Array.isArray(command) || !command.length || command.some((item) => !String(item))) throw new Error("评分服务命令不能为空");
  const paths = taskPaths(taskRoot);
  const { lock, check } = candidateCheck(paths, "start-service");
  const state = fs.existsSync(paths.stateFile) ? loadJson(paths.stateFile) : {
    schema_version: RUNTIME_SCHEMA,
    task_id: lock.task_id,
    created_at: new Date().toISOString(),
    runtime_workspace: null,
    candidate_sha256: lock.expected_sha256,
    candidate_checks: [],
    port_overrides: loadPortOverrideAudit(paths, lock).overrides,
    service: null,
    cleanup: null,
  };
  validateRuntimeState(state, lock);
  if (state.service?.pid && processIdentity(Number(state.service.pid))) throw new Error(`评分服务仍在运行：PID ${state.service.pid}`);
  const cwd = useCandidate ? paths.root : paths.runtime;
  if (!useCandidate && !fs.existsSync(paths.runtime)) throw new Error("启动可写服务前必须先 prepare 运行时副本");
  const url = validateLoopbackUrl(expectedUrl);
  fs.mkdirSync(paths.logRoot, { recursive: true });
  const stdoutPath = path.join(paths.logRoot, "site.stdout.log");
  const stderrPath = path.join(paths.logRoot, "site.stderr.log");
  const stdout = fs.openSync(stdoutPath, "w", 0o600);
  const stderr = fs.openSync(stderrPath, "w", 0o600);
  const serviceId = randomUUID();
  const launchCommand = process.platform === "win32"
    ? [
      process.execPath,
      PROCESS_WRAPPER_FILE,
      "--service-id",
      serviceId,
      "--",
      ...command.map(String),
    ]
    : command.map(String);
  let child;
  try {
    child = spawn(String(launchCommand[0]), launchCommand.slice(1), {
      cwd,
      detached: true,
      stdio: ["ignore", stdout, stderr],
    });
  } finally {
    fs.closeSync(stdout);
    fs.closeSync(stderr);
  }
  child.unref();
  let identity = null;
  try {
    await new Promise((resolvePromise, rejectPromise) => {
      child.once("spawn", resolvePromise);
      child.once("error", rejectPromise);
    });
    state.candidate_checks.push(check);
    state.service = {
      status: "STARTING",
      pid: child.pid,
      pgid: null,
      process_started_at_text: null,
      cwd: useCandidate ? "." : "private-scoring/runtime-workspace",
      command: command.map(String),
      service_id: serviceId,
      process_group_mode: process.platform === "win32" ? "windows-process-tree" : "posix-process-group",
      expected_url: url,
      started_at: new Date().toISOString(),
      stdout: "private-scoring/runtime-logs/site.stdout.log",
      stderr: "private-scoring/runtime-logs/site.stderr.log",
    };
    writeJson(paths.stateFile, state);
    identity = processIdentity(child.pid);
    const windowsIdentityMismatch = process.platform === "win32"
      && (!windowsCommandIncludesPath(identity?.command, PROCESS_WRAPPER_FILE) || !identity.command.includes(serviceId));
    const posixIdentityMismatch = process.platform !== "win32" && identity?.cwd !== fs.realpathSync(cwd);
    if (!identity || identity.pgid !== child.pid || windowsIdentityMismatch || posixIdentityMismatch) {
      throw new Error("无法确认评分服务的独立进程组或 cwd，已拒绝托管");
    }
    state.service.pgid = identity.pgid;
    state.service.process_started_at_text = identity.started_at_text;
    writeJson(paths.stateFile, state);
    state.service.http_status = await waitForUrl(url);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    if (child.exitCode !== null || child.signalCode !== null) throw new Error("评分服务在就绪检查期间退出");
    if (!assertManagedIdentity(paths, state.service)) throw new Error("评分服务在就绪检查期间退出");
    state.service.status = "RUNNING";
    state.service.ready_at = new Date().toISOString();
    writeJson(paths.stateFile, state);
  } catch (error) {
    try {
      if (state.service?.pid === child.pid && fs.existsSync(paths.stateFile)) {
        await stopManagedService(taskRoot, { expectedFailure: true });
      } else if (identity?.pid === child.pid && identity.pgid === child.pid) {
        terminateProcessIdentity(identity, false);
        if (!(await waitForExit(identity.pid, 5_000))) terminateProcessIdentity(identity, true);
      } else if (child.pid) {
        child.kill("SIGTERM");
      }
    } catch (cleanupError) {
      error.message = `${error.message}；启动失败后的精确清理也失败：${cleanupError.message}`;
    }
    throw error;
  }
  return { paths, state };
}

function assertManagedIdentity(paths, service) {
  const identity = processIdentity(Number(service.pid));
  if (!identity) return null;
  const expectedCwd = fs.realpathSync(service.cwd === "." ? paths.root : paths.runtime);
  const expectedExecutable = path.basename(String(service.command?.[0] || ""));
  const processGroupMode = process.platform === "win32" ? "windows-process-tree" : "posix-process-group";
  const platformIdentityMismatch = process.platform === "win32"
    ? (!service.service_id
      || !windowsCommandIncludesPath(identity.command, PROCESS_WRAPPER_FILE)
      || !identity.command.includes(service.service_id))
    : identity.cwd !== expectedCwd;
  if (identity.pgid !== Number(service.pgid)
    || identity.started_at_text !== service.process_started_at_text
    || identity.process_group_mode !== processGroupMode
    || platformIdentityMismatch
    || (process.platform === "win32"
      ? !identity.command.toLowerCase().includes(expectedExecutable.toLowerCase())
      : !identity.command.includes(expectedExecutable))) {
    throw new Error(`PID ${service.pid} 的身份、进程组或 cwd 已变化，拒绝终止`);
  }
  return identity;
}

async function waitForExit(pid, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!processIdentity(pid)) return true;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  return !processIdentity(pid);
}

export async function stopManagedService(taskRoot, { expectedFailure = false } = {}) {
  const paths = taskPaths(taskRoot);
  const state = loadJson(paths.stateFile);
  const lock = loadCandidateArtifact(paths.lockFile);
  validateRuntimeState(state, lock);
  if (!state.service?.pid) return { paths, state };
  const identity = assertManagedIdentity(paths, state.service);
  const stopStartedAt = new Date().toISOString();
  if (identity) {
    terminateProcessIdentity(identity, false);
    if (!(await waitForExit(identity.pid, 5_000))) {
      const secondIdentity = assertManagedIdentity(paths, state.service);
      if (secondIdentity) terminateProcessIdentity(secondIdentity, true);
      if (!(await waitForExit(identity.pid, 2_000))) throw new Error(`评分服务无法停止：PID ${identity.pid}`);
    }
  }
  state.service.status = expectedFailure ? "START_FAILED_STOPPED" : "STOPPED";
  state.service.stop_started_at = stopStartedAt;
  state.service.stopped_at = new Date().toISOString();
  state.service.cleanup = {
    pid: state.service.pid,
    pgid: state.service.pgid,
    process_group_mode: state.service.process_group_mode || "posix-process-group",
    exact_identity_verified: Boolean(identity),
  };
  state.candidate_checks.push(candidateCheck(paths, "stop-service").check);
  writeJson(paths.stateFile, state);
  return { paths, state };
}

export function cleanRuntime(taskRoot) {
  const paths = taskPaths(taskRoot);
  const state = loadJson(paths.stateFile);
  const lock = loadCandidateArtifact(paths.lockFile);
  validateRuntimeState(state, lock);
  if (state.service?.pid && processIdentity(Number(state.service.pid))) throw new Error(`评分服务仍在运行，不能清理运行时副本：PID ${state.service.pid}`);
  const before = candidateCheck(paths, "clean-runtime:before");
  if (fs.existsSync(paths.runtime)) fs.rmSync(paths.runtime, { recursive: true });
  const after = candidateCheck(paths, "clean-runtime:after");
  state.candidate_checks.push(before.check, after.check);
  state.cleanup = { runtime_workspace_removed: !fs.existsSync(paths.runtime), cleaned_at: new Date().toISOString() };
  writeJson(paths.stateFile, state);
  return { paths, state };
}

function parseArgs(argv) {
  const command = argv[0] || "";
  const values = {
    command,
    taskRoot: ".",
    port: "4173",
    spaFallback: false,
    childCommand: [],
    file: "",
    fromPort: "",
    toPort: "",
    evidence: "",
    root: ".",
  };
  let index = 1;
  for (; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--") {
      values.childCommand = argv.slice(index + 1);
      break;
    }
    if (token === "--task-root") values.taskRoot = argv[++index] || "";
    else if (token === "--url") values.url = argv[++index] || "";
    else if (token === "--port") values.port = argv[++index] || "";
    else if (token === "--file") values.file = argv[++index] || "";
    else if (token === "--from-port") values.fromPort = argv[++index] || "";
    else if (token === "--to-port") values.toPort = argv[++index] || "";
    else if (token === "--evidence") values.evidence = argv[++index] || "";
    else if (token === "--root") values.root = argv[++index] || "";
    else if (token === "--spa-fallback") values.spaFallback = true;
    else throw new Error(`未知参数：${token}`);
  }
  return values;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  let result;
  if (args.command === "prepare") result = prepareRuntime(args.taskRoot);
  else if (args.command === "port-override") {
    result = overrideRuntimePort(args.taskRoot, args.file, args.fromPort, args.toPort, args.evidence);
  }
  else if (args.command === "start-static") {
    if (!/^\d+$/.test(args.port) || Number(args.port) < 1 || Number(args.port) > 65535) throw new Error("--port 必须是 1..65535 的整数");
    const paths = taskPaths(args.taskRoot);
    const staticRoot = resolveCandidateStaticRoot(paths, args.root);
    const command = [process.execPath, path.join(SCRIPT_DIR, "serve_static.mjs"), "--root", staticRoot.filename, "--host", "127.0.0.1", "--port", args.port];
    if (args.spaFallback) command.push("--spa-fallback");
    result = await startManagedService(args.taskRoot, command, `http://127.0.0.1:${args.port}/`, { useCandidate: true });
    result.state.service.static_root = `workspace/${staticRoot.relative === "." ? "" : staticRoot.relative}`.replace(/\/$/, "");
    writeJson(result.paths.stateFile, result.state);
  } else if (args.command === "start") {
    if (!args.url) throw new Error("start 必须提供 --url");
    result = await startManagedService(args.taskRoot, args.childCommand, args.url);
  } else if (args.command === "stop") result = await stopManagedService(args.taskRoot);
  else if (args.command === "clean") result = cleanRuntime(args.taskRoot);
  else if (args.command === "status") {
    const paths = taskPaths(args.taskRoot);
    result = { paths, state: loadJson(paths.stateFile), process: null };
    if (result.state.service?.pid) result.process = processIdentity(Number(result.state.service.pid));
  } else throw new Error(`未知命令：${args.command || "未提供"}`);
  process.stdout.write(`${JSON.stringify(result.state, null, 2)}\n`);
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`FAIL: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
  });
}
