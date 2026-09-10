#!/usr/bin/env node
import { spawn } from "node:child_process";
import { createHash, randomBytes, randomUUID } from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  processIdentity,
  terminateProcessIdentity,
  windowsCommandIncludesPath,
} from "./managed_runtime.mjs";
import { loadCandidateArtifact, verifyWorkspace } from "./workspace-integrity.mjs";

export const SCREENSHOT_RECEIVER_SCHEMA = "wildclawbench.web-e2e-screenshot-receiver/v1";
const SCRIPT_FILE = fs.realpathSync(fileURLToPath(import.meta.url));
const ACTIVE_STATUSES = new Set(["STARTING", "RUNNING"]);
const TERMINAL_STATUSES = new Set(["COMPLETED", "STOPPED", "TIMED_OUT", "FAILED", "LOST"]);
const DEFAULT_TIMEOUT_MS = 300_000;
const DEFAULT_MAX_BYTES = 20 * 1024 * 1024;

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sleep(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
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

function pathInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative !== "" && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

function taskPaths(taskRoot) {
  const root = fs.realpathSync(path.resolve(taskRoot));
  const privateRoot = path.join(root, "private-scoring");
  if (!fs.existsSync(privateRoot) || fs.lstatSync(privateRoot).isSymbolicLink() || !fs.lstatSync(privateRoot).isDirectory()) {
    throw new Error(`评分私有目录缺失或不安全：${privateRoot}`);
  }
  return {
    root,
    candidate: path.join(root, "workspace"),
    markerFile: path.join(root, ".web-e2e-scoring-ready"),
    privateRoot,
    lockFile: path.join(privateRoot, "candidate_artifact.json"),
    evidenceRoot: path.join(privateRoot, "evidence"),
    stateFile: path.join(privateRoot, "screenshot-receiver-state.json"),
    logRoot: path.join(privateRoot, "runtime-logs"),
    stdoutFile: path.join(privateRoot, "runtime-logs", "screenshot-receiver.stdout.log"),
    stderrFile: path.join(privateRoot, "runtime-logs", "screenshot-receiver.stderr.log"),
  };
}

function candidateCheck(paths, stage) {
  const lock = loadCandidateArtifact(paths.lockFile);
  if (!fs.existsSync(paths.markerFile) || fs.lstatSync(paths.markerFile).isSymbolicLink()) {
    throw new Error("截图接收器只能用于带 .web-e2e-scoring-ready 的受管评分任务");
  }
  const marker = fs.readFileSync(paths.markerFile, "utf8").split(/\r?\n/).filter(Boolean);
  if (marker.length !== 2 || marker[0] !== lock.batch_id || marker[1] !== lock.task_id) {
    throw new Error("候选冻结文件与评分就绪标记不一致");
  }
  return { lock, check: verifyWorkspace(paths.candidate, lock.expected_sha256, stage) };
}

function validateInteger(raw, label, minimum, maximum) {
  if (!/^\d+$/.test(String(raw))) throw new Error(`${label} 必须是 ${minimum}..${maximum} 的整数`);
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${label} 必须是 ${minimum}..${maximum} 的整数`);
  }
  return value;
}

function imageFormatForName(raw) {
  const filename = String(raw || "");
  if (!filename
    || filename !== path.basename(filename)
    || filename.includes("\\")
    || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.(?:png|jpe?g)$/i.test(filename)) {
    throw new Error("--filename 必须是安全的 PNG/JPEG 文件名，不能包含目录");
  }
  const extension = path.extname(filename).toLowerCase();
  return {
    filename,
    format: extension === ".png" ? "png" : "jpeg",
    contentType: extension === ".png" ? "image/png" : "image/jpeg",
  };
}

export function detectImageFormat(bytes) {
  if (bytes.length >= 8
    && bytes.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return "png";
  if (bytes.length >= 4
    && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
    && bytes[bytes.length - 2] === 0xff && bytes[bytes.length - 1] === 0xd9) return "jpeg";
  return null;
}

function ensureEvidenceOutput(paths, filename) {
  if (!fs.existsSync(paths.evidenceRoot)) fs.mkdirSync(paths.evidenceRoot, { recursive: true, mode: 0o700 });
  const info = fs.lstatSync(paths.evidenceRoot);
  if (info.isSymbolicLink() || !info.isDirectory()) throw new Error("private-scoring/evidence 必须是普通目录");
  const privateCanonical = fs.realpathSync(paths.privateRoot);
  const evidenceCanonical = fs.realpathSync(paths.evidenceRoot);
  if (!pathInside(privateCanonical, evidenceCanonical)) throw new Error("截图证据目录越过 private-scoring 边界");
  const output = path.join(evidenceCanonical, filename);
  if (fs.existsSync(output)) throw new Error(`截图证据已存在，拒绝覆盖：private-scoring/evidence/${filename}`);
  return output;
}

function validateState(state, lock) {
  if (state.schema_version !== SCREENSHOT_RECEIVER_SCHEMA
    || state.task_id !== lock.task_id
    || state.candidate_sha256 !== lock.expected_sha256
    || !state.receiver_id
    || (!ACTIVE_STATUSES.has(state.status) && !TERMINAL_STATUSES.has(state.status))) {
    throw new Error("screenshot-receiver-state.json 与当前候选产物身份不一致");
  }
}

function safeProcessIdentity(pid) {
  try {
    return processIdentity(Number(pid));
  } catch (error) {
    try {
      process.kill(Number(pid), 0);
    } catch (probeError) {
      if (probeError?.code !== "EPERM") return null;
    }
    throw new Error(`无法可靠读取截图接收器进程身份：PID ${pid}：${error instanceof Error ? error.message : String(error)}`);
  }
}

function assertReceiverIdentity(paths, state) {
  const identity = safeProcessIdentity(state.pid);
  if (!identity) return null;
  const mismatches = [];
  if (identity.pgid !== Number(state.pgid)) mismatches.push("pgid");
  if (identity.started_at_text !== state.process_started_at_text) mismatches.push("started_at");
  if (process.platform === "win32") {
    if (identity.process_group_mode !== "windows-process-tree") mismatches.push("process_group_mode");
    if (state.process_group_mode && state.process_group_mode !== "windows-process-tree") mismatches.push("saved_process_group_mode");
    if (!windowsCommandIncludesPath(identity.command, paths.root)) mismatches.push("task_root");
  } else if (identity.cwd !== paths.root) mismatches.push("cwd");
  if (process.platform === "win32"
    ? !windowsCommandIncludesPath(identity.command, SCRIPT_FILE)
    : !identity.command.includes(SCRIPT_FILE)) mismatches.push("script");
  if (!identity.command.includes("serve")) mismatches.push("command");
  if (!identity.command.includes(state.receiver_id)) mismatches.push("receiver_id");
  if (mismatches.length) {
    if (TERMINAL_STATUSES.has(state.status)) return null;
    throw new Error(`PID ${state.pid} 的截图接收器身份、进程组或 cwd 已变化，拒绝终止：${mismatches.join(",")}`);
  }
  return identity;
}

function inspectReceiverState(paths, lock) {
  let state = loadJson(paths.stateFile);
  validateState(state, lock);
  try {
    return { state, identity: assertReceiverIdentity(paths, state) };
  } catch (error) {
    const latest = loadJson(paths.stateFile);
    validateState(latest, lock);
    if (latest.receiver_id === state.receiver_id && TERMINAL_STATUSES.has(latest.status)) {
      state = latest;
      return { state, identity: assertReceiverIdentity(paths, state) };
    }
    throw error;
  }
}

async function waitForExit(pid, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!safeProcessIdentity(pid)) return true;
    await sleep(100);
  }
  return !safeProcessIdentity(pid);
}

function notStartedState(paths, lock) {
  return {
    schema_version: SCREENSHOT_RECEIVER_SCHEMA,
    task_id: lock.task_id,
    candidate_sha256: lock.expected_sha256,
    status: "NOT_STARTED",
    state_file: path.relative(paths.root, paths.stateFile).split(path.sep).join("/"),
  };
}

export async function startReceiver(taskRoot, options) {
  const paths = taskPaths(taskRoot);
  const before = candidateCheck(paths, "screenshot-receiver:start");
  const image = imageFormatForName(options.filename);
  const port = validateInteger(options.port ?? "0", "--port", 0, 65535);
  const timeoutMs = validateInteger(options.timeoutMs ?? DEFAULT_TIMEOUT_MS, "--timeout-ms", 100, 600_000);
  const maxBytes = validateInteger(options.maxBytes ?? DEFAULT_MAX_BYTES, "--max-bytes", 8, 100 * 1024 * 1024);
  ensureEvidenceOutput(paths, image.filename);

  if (fs.existsSync(paths.stateFile)) {
    const { identity } = inspectReceiverState(paths, before.lock);
    if (identity) throw new Error(`已有截图接收器进程仍在运行：PID ${identity.pid}`);
  }

  const receiverId = randomUUID();
  const token = randomBytes(24).toString("hex");
  fs.mkdirSync(paths.logRoot, { recursive: true, mode: 0o700 });
  const stdout = fs.openSync(paths.stdoutFile, "a", 0o600);
  const stderr = fs.openSync(paths.stderrFile, "a", 0o600);
  let child;
  try {
    child = spawn(process.execPath, [
      SCRIPT_FILE,
      "serve",
      "--task-root", paths.root,
      "--receiver-id", receiverId,
      "--filename", image.filename,
      "--port", String(port),
      "--timeout-ms", String(timeoutMs),
      "--max-bytes", String(maxBytes),
    ], {
      cwd: paths.root,
      detached: true,
      env: { ...process.env, WCB_SCREENSHOT_RECEIVER_TOKEN: token },
      stdio: ["ignore", stdout, stderr],
    });
  } finally {
    fs.closeSync(stdout);
    fs.closeSync(stderr);
  }
  child.unref();
  await new Promise((resolvePromise, rejectPromise) => {
    child.once("spawn", resolvePromise);
    child.once("error", rejectPromise);
  });

  let startupError = null;
  try {
    const deadline = Date.now() + 5_000;
    while (Date.now() < deadline) {
      if (fs.existsSync(paths.stateFile)) {
        const state = loadJson(paths.stateFile);
        if (state.receiver_id === receiverId) {
          validateState(state, before.lock);
          if (state.status === "RUNNING") {
            assertReceiverIdentity(paths, state);
            return { paths, state };
          }
          if (state.status === "FAILED") throw new Error(`截图接收器启动失败：${state.error || "未知错误"}`);
        }
      }
      if (!safeProcessIdentity(child.pid)) break;
      await sleep(50);
    }
  } catch (error) {
    startupError = error;
  }

  let cleanupError = null;
  const identity = safeProcessIdentity(child.pid);
  const startupIdentityMatches = identity
    && identity.pgid === child.pid
    && (process.platform === "win32" ? windowsCommandIncludesPath(identity.command, paths.root) : identity.cwd === paths.root)
    && (process.platform === "win32"
      ? windowsCommandIncludesPath(identity.command, SCRIPT_FILE)
      : identity.command.includes(SCRIPT_FILE));
  if (startupIdentityMatches) {
    terminateProcessIdentity(identity, false);
    if (!(await waitForExit(identity.pid, 2_000))) {
      const remaining = safeProcessIdentity(identity.pid);
      if (remaining
        && remaining.pgid === identity.pgid
        && remaining.started_at_text === identity.started_at_text
        && (process.platform === "win32" ? windowsCommandIncludesPath(remaining.command, paths.root) : remaining.cwd === paths.root)
        && (process.platform === "win32"
          ? windowsCommandIncludesPath(remaining.command, SCRIPT_FILE)
          : remaining.command.includes(SCRIPT_FILE))) {
        terminateProcessIdentity(remaining, true);
      }
      if (!(await waitForExit(identity.pid, 2_000))) {
        cleanupError = `截图接收器启动失败后仍未退出：PID ${identity.pid}`;
      }
    }
  }
  const logTail = fs.existsSync(paths.stderrFile)
    ? fs.readFileSync(paths.stderrFile, "utf8").trim().split(/\r?\n/).slice(-3).join(" | ")
    : "";
  if (startupError) {
    if (logTail) startupError.message = `${startupError.message}：${logTail}`;
    if (cleanupError) startupError.message = `${startupError.message}；${cleanupError}`;
    throw startupError;
  }
  if (cleanupError) throw new Error(cleanupError);
  throw new Error(`截图接收器未在 5 秒内就绪${logTail ? `：${logTail}` : ""}`);
}

export function receiverStatus(taskRoot) {
  const paths = taskPaths(taskRoot);
  const lock = loadCandidateArtifact(paths.lockFile);
  if (!fs.existsSync(paths.stateFile)) return { paths, state: notStartedState(paths, lock), process: null };
  const inspected = inspectReceiverState(paths, lock);
  const state = inspected.state;
  const identity = inspected.identity;
  if (!identity && ACTIVE_STATUSES.has(state.status)) {
    state.status = "LOST";
    state.upload_url = null;
    state.ended_at = new Date().toISOString();
    state.error = "记录的截图接收器进程已不存在";
    writeJson(paths.stateFile, state);
  }
  return { paths, state, process: identity };
}

export async function stopReceiver(taskRoot) {
  const paths = taskPaths(taskRoot);
  const lock = loadCandidateArtifact(paths.lockFile);
  if (!fs.existsSync(paths.stateFile)) return { paths, state: notStartedState(paths, lock), process: null };
  const inspected = inspectReceiverState(paths, lock);
  const state = inspected.state;
  let identity = inspected.identity;
  const exactIdentityVerified = Boolean(identity);
  if (identity) {
    terminateProcessIdentity(identity, false);
    if (!(await waitForExit(identity.pid, 5_000))) {
      identity = assertReceiverIdentity(paths, state);
      if (identity) terminateProcessIdentity(identity, true);
      if (!(await waitForExit(Number(state.pid), 2_000))) throw new Error(`截图接收器无法停止：PID ${state.pid}`);
    }
  }
  if (ACTIVE_STATUSES.has(state.status)) state.status = "STOPPED";
  state.upload_url = null;
  state.ended_at ||= new Date().toISOString();
  state.cleanup = {
    pid: state.pid,
    pgid: state.pgid,
    process_group_mode: state.process_group_mode || "posix-process-group",
    exact_identity_verified: exactIdentityVerified,
    stopped_at: new Date().toISOString(),
  };
  state.candidate_checks ||= [];
  state.candidate_checks.push(candidateCheck(paths, "screenshot-receiver:stop").check);
  writeJson(paths.stateFile, state);
  return { paths, state, process: null };
}

function responseJson(response, status, value) {
  const body = `${JSON.stringify(value)}\n`;
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
    "connection": "close",
  });
  response.end(body);
}

async function serveReceiver(args) {
  const token = String(process.env.WCB_SCREENSHOT_RECEIVER_TOKEN || "");
  if (!/^[a-f0-9]{48}$/.test(token)) throw new Error("截图接收器缺少一次性令牌");
  if (!/^[a-f0-9-]{36}$/i.test(args.receiverId)) throw new Error("截图接收器 ID 无效");
  const paths = taskPaths(args.taskRoot);
  const before = candidateCheck(paths, "screenshot-receiver:worker-start");
  const image = imageFormatForName(args.filename);
  const output = ensureEvidenceOutput(paths, image.filename);
  const port = validateInteger(args.port, "--port", 0, 65535);
  const timeoutMs = validateInteger(args.timeoutMs, "--timeout-ms", 100, 600_000);
  const maxBytes = validateInteger(args.maxBytes, "--max-bytes", 8, 100 * 1024 * 1024);
  const identity = processIdentity(process.pid);
  const identityMismatch = process.platform === "win32"
    ? !windowsCommandIncludesPath(identity?.command, paths.root)
    : identity?.cwd !== paths.root;
  if (!identity || identity.pgid !== process.pid || identityMismatch) {
    throw new Error("无法确认截图接收器的独立进程组或 cwd");
  }
  const state = {
    schema_version: SCREENSHOT_RECEIVER_SCHEMA,
    task_id: before.lock.task_id,
    candidate_sha256: before.lock.expected_sha256,
    receiver_id: args.receiverId,
    status: "STARTING",
    pid: process.pid,
    pgid: identity.pgid,
    process_group_mode: identity.process_group_mode,
    process_started_at_text: identity.started_at_text,
    cwd: ".",
    filename: image.filename,
    format: image.format,
    content_type: image.contentType,
    max_bytes: maxBytes,
    timeout_ms: timeoutMs,
    token_sha256: sha256(token),
    upload_url: null,
    started_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + timeoutMs).toISOString(),
    stdout: "private-scoring/runtime-logs/screenshot-receiver.stdout.log",
    stderr: "private-scoring/runtime-logs/screenshot-receiver.stderr.log",
    candidate_checks: [before.check],
  };
  writeJson(paths.stateFile, state);

  let receiving = false;
  let finished = false;
  const sockets = new Set();
  const uploadPath = `/screenshot/${token}`;
  const server = http.createServer((request, response) => {
    if (request.method !== "POST" || request.url !== uploadPath) {
      responseJson(response, 404, { error: "not_found" });
      return;
    }
    if (finished || receiving) {
      responseJson(response, 409, { error: "receiver_busy_or_completed" });
      return;
    }
    const contentType = String(request.headers["content-type"] || "").split(";", 1)[0].trim().toLowerCase();
    if (contentType !== image.contentType) {
      responseJson(response, 415, { error: `content_type_must_be_${image.contentType}` });
      return;
    }
    const declaredLength = request.headers["content-length"];
    if (declaredLength !== undefined && (!/^\d+$/.test(declaredLength) || Number(declaredLength) > maxBytes)) {
      responseJson(response, 413, { error: "payload_too_large", max_bytes: maxBytes });
      request.resume();
      return;
    }

    receiving = true;
    const chunks = [];
    let size = 0;
    let rejected = false;
    request.on("data", (chunk) => {
      if (rejected) return;
      size += chunk.length;
      if (size > maxBytes) {
        rejected = true;
        chunks.length = 0;
        responseJson(response, 413, { error: "payload_too_large", max_bytes: maxBytes });
      } else chunks.push(chunk);
    });
    request.on("aborted", () => { receiving = false; });
    request.on("error", () => { receiving = false; });
    request.on("end", () => {
      if (rejected) {
        receiving = false;
        return;
      }
      const bytes = Buffer.concat(chunks);
      if (detectImageFormat(bytes) !== image.format) {
        receiving = false;
        responseJson(response, 415, { error: "image_signature_extension_and_content_type_must_match" });
        return;
      }
      try {
        state.candidate_checks.push(candidateCheck(paths, "screenshot-receiver:before-save").check);
        fs.writeFileSync(output, bytes, { flag: "wx", mode: 0o600 });
        state.candidate_checks.push(candidateCheck(paths, "screenshot-receiver:after-save").check);
        state.status = "COMPLETED";
        state.upload_url = null;
        state.received_at = new Date().toISOString();
        state.ended_at = state.received_at;
        state.output = {
          path: `private-scoring/evidence/${image.filename}`,
          bytes: bytes.length,
          sha256: sha256(bytes),
          format: image.format,
          content_type: image.contentType,
        };
        finished = true;
        receiving = false;
        writeJson(paths.stateFile, state);
        response.once("finish", () => {
          clearTimeout(timer);
          closeServer(0);
        });
        responseJson(response, 201, state.output);
      } catch (error) {
        state.status = "FAILED";
        state.upload_url = null;
        state.error = error instanceof Error ? error.message : String(error);
        state.ended_at = new Date().toISOString();
        finished = true;
        receiving = false;
        writeJson(paths.stateFile, state);
        response.once("finish", () => {
          clearTimeout(timer);
          closeServer(2);
        });
        responseJson(response, 500, { error: state.error });
      }
    });
  });
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
  });
  server.on("error", (error) => {
    finished = true;
    clearTimeout(timer);
    state.status = "FAILED";
    state.upload_url = null;
    state.error = error instanceof Error ? error.message : String(error);
    state.ended_at = new Date().toISOString();
    writeJson(paths.stateFile, state);
    process.exitCode = 2;
  });

  function closeServer(exitCode) {
    for (const socket of sockets) socket.destroy();
    server.close(() => { process.exitCode = exitCode; });
  }

  const timer = setTimeout(() => {
    if (finished) return;
    finished = true;
    state.status = "TIMED_OUT";
    state.upload_url = null;
    state.error = `在 ${timeoutMs}ms 内未收到有效截图`;
    state.ended_at = new Date().toISOString();
    writeJson(paths.stateFile, state);
    closeServer(3);
  }, timeoutMs);

  const stopForSignal = () => {
    if (finished) return;
    finished = true;
    clearTimeout(timer);
    state.status = "STOPPED";
    state.upload_url = null;
    state.ended_at = new Date().toISOString();
    writeJson(paths.stateFile, state);
    closeServer(0);
  };
  process.once("SIGTERM", stopForSignal);
  process.once("SIGINT", stopForSignal);

  await new Promise((resolvePromise, rejectPromise) => {
    server.once("listening", resolvePromise);
    server.once("error", rejectPromise);
    server.listen(port, "127.0.0.1");
  });
  const address = server.address();
  if (!address || typeof address === "string" || address.address !== "127.0.0.1") {
    throw new Error("截图接收器未绑定到 127.0.0.1");
  }
  state.status = "RUNNING";
  state.port = address.port;
  state.upload_url = `http://127.0.0.1:${address.port}${uploadPath}`;
  state.ready_at = new Date().toISOString();
  writeJson(paths.stateFile, state);

  await new Promise((resolvePromise) => server.once("close", resolvePromise));
  clearTimeout(timer);
}

function parseArgs(argv) {
  const values = {
    command: argv[0] || "",
    taskRoot: ".",
    receiverId: "",
    filename: "",
    port: "0",
    timeoutMs: String(DEFAULT_TIMEOUT_MS),
    maxBytes: String(DEFAULT_MAX_BYTES),
  };
  for (let index = 1; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--task-root") values.taskRoot = argv[++index] || "";
    else if (token === "--receiver-id") values.receiverId = argv[++index] || "";
    else if (token === "--filename") values.filename = argv[++index] || "";
    else if (token === "--port") values.port = argv[++index] || "";
    else if (token === "--timeout-ms") values.timeoutMs = argv[++index] || "";
    else if (token === "--max-bytes") values.maxBytes = argv[++index] || "";
    else throw new Error(`未知参数：${token}`);
  }
  return values;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  let result;
  if (args.command === "start") result = await startReceiver(args.taskRoot, args);
  else if (args.command === "status") result = receiverStatus(args.taskRoot);
  else if (args.command === "stop") result = await stopReceiver(args.taskRoot);
  else if (args.command === "serve") {
    await serveReceiver(args);
    return;
  } else throw new Error(`未知命令：${args.command || "未提供"}`);
  process.stdout.write(`${JSON.stringify(result.state, null, 2)}\n`);
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`FAIL: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
  });
}
