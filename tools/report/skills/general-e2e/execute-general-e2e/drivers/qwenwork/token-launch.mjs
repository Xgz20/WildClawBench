#!/usr/bin/env node

import { mkdir, realpath, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";
import { buildReadOnlyProbe } from "./probe.mjs";
import {
  QWEN_TOKEN_USAGE_ENV_NAME,
  QWEN_TOKEN_USAGE_ENV_VALUE,
  readQwenTokenListener,
  readQwenTokenProcess,
  sameQwenTokenProcess,
} from "./token-process.mjs";

const sleep = (milliseconds) => new Promise((done) => setTimeout(done, milliseconds));

function loopbackPort(endpoint) {
  const url = new URL(endpoint);
  if (!new Set(["127.0.0.1", "localhost", "::1"]).has(url.hostname)
      || url.protocol !== "http:" || !url.port) {
    throw new Error("QWEN_TOKEN_ENDPOINT_NOT_LOOPBACK");
  }
  return { endpoint: url.origin, port: Number(url.port) };
}

function assertSafeProbe(probe, expectedPath) {
  if (probe?.app?.path !== expectedPath || probe.app?.identity_verified !== true
      || probe.app?.bundle_id !== "cn.qwenwork.desktop.mac"
      || probe.app?.cdp?.ready !== true
      || probe.app?.cdp?.browser_identity_present !== true
      || probe.native_state?.database?.quick_check !== "ok"
      || probe.native_state?.database?.active_or_pending_count !== 0) {
    throw new Error("QWEN_TOKEN_LAUNCH_PREFLIGHT_NOT_IDLE_OR_VERIFIED");
  }
}

export async function ensureQwenTokenUsage(options, overrides = {}) {
  const { endpoint, port } = loopbackPort(options.endpoint);
  const appPath = resolve(options.appPath);
  const deps = {
    probe: (config) => buildReadOnlyProbe(config),
    listener: () => readQwenTokenListener({ appPath, port }),
    process: (pid) => readQwenTokenProcess(pid, { appPath, port }),
    signal: (pid, kind) => runCapture("/bin/kill", [kind === "KILL" ? "-KILL" : "-TERM", String(pid)],
      { capture: true, allowFailure: true }),
    launch: () => runCapture("/usr/bin/open", ["-na", appPath,
      "--env", `${QWEN_TOKEN_USAGE_ENV_NAME}=${QWEN_TOKEN_USAGE_ENV_VALUE}`,
      "--args", "--remote-debugging-address=127.0.0.1", `--remote-debugging-port=${port}`],
    { capture: true, allowFailure: true }),
    sleep,
    now: () => Date.now(),
    ...overrides,
  };
  const probeConfig = {
    appPath, sessionDb: resolve(options.sessionDb), traceRoot: resolve(options.traceRoot),
    endpoint, onlineSnapshot: true,
  };
  const beforeProbe = await deps.probe(probeConfig);
  assertSafeProbe(beforeProbe, appPath);
  const before = await deps.listener();
  if (!before) throw new Error("QWEN_TOKEN_LISTENER_MISSING");
  if (before.token_usage_exposed) {
    return { status: "ALREADY_EXPOSED", restarted: false, app_version: beforeProbe.app.version,
      runtime_sha256: beforeProbe.runtime?.identity?.runtime_sha256 || null, before, after: before };
  }
  const recheck = async () => {
    const current = await deps.process(before.pid);
    if (!sameQwenTokenProcess(before, current)) throw new Error("QWEN_TOKEN_PROCESS_CHANGED_BEFORE_SIGNAL");
    return current;
  };
  const stopped = async () => {
    const current = await deps.process(before.pid);
    const listener = await deps.listener();
    if (current && !sameQwenTokenProcess(before, current)) throw new Error("QWEN_TOKEN_PROCESS_IDENTITY_DRIFT");
    if (listener && !sameQwenTokenProcess(before, listener)) throw new Error("QWEN_TOKEN_LISTENER_CHANGED_DURING_STOP");
    return !current && !listener;
  };
  const waitStopped = async (milliseconds) => {
    const deadline = deps.now() + milliseconds;
    while (deps.now() < deadline) {
      if (await stopped()) return true;
      await deps.sleep(250);
    }
    return stopped();
  };
  await recheck();
  const term = await deps.signal(before.pid, "TERM");
  if (term.code !== 0) throw new Error("QWEN_TOKEN_TERM_FAILED");
  let stopMethod = "TERM";
  if (!(await waitStopped(5_000))) {
    await recheck();
    const killed = await deps.signal(before.pid, "KILL");
    if (killed.code !== 0 || !(await waitStopped(10_000))) throw new Error("QWEN_TOKEN_KILL_FAILED");
    stopMethod = "KILL_AFTER_TERM_TIMEOUT";
  }
  const launched = await deps.launch();
  if (launched.code !== 0) throw new Error("QWEN_TOKEN_LAUNCH_FAILED");
  const deadline = deps.now() + 30_000;
  let after = null;
  while (deps.now() < deadline) {
    after = await deps.listener();
    if (after) break;
    await deps.sleep(250);
  }
  if (!after || after.pid === before.pid || !after.token_usage_exposed) {
    throw new Error("QWEN_TOKEN_NEW_CLIENT_NOT_EXPOSED");
  }
  const afterProbe = await deps.probe(probeConfig);
  assertSafeProbe(afterProbe, appPath);
  if (afterProbe.app.version !== beforeProbe.app.version
      || afterProbe.runtime?.identity?.runtime_sha256 !== beforeProbe.runtime?.identity?.runtime_sha256) {
    throw new Error("QWEN_TOKEN_RUNTIME_CHANGED_DURING_RESTART");
  }
  return {
    status: "EXPOSED", restarted: true, stop_method: stopMethod,
    app_version: afterProbe.app.version,
    runtime_sha256: afterProbe.runtime?.identity?.runtime_sha256 || null,
    before, after,
  };
}

function parseArgs(argv) {
  const options = { endpoint: "http://127.0.0.1:9250" };
  const names = new Map([
    ["--app-path", "appPath"], ["--session-db", "sessionDb"],
    ["--trace-root", "traceRoot"], ["--endpoint", "endpoint"], ["--output", "output"],
  ]);
  for (let index = 0; index < argv.length; index += 2) {
    const key = names.get(argv[index]);
    if (!key || !argv[index + 1]) throw new Error("QWEN_TOKEN_LAUNCH_ARGS_INVALID");
    options[key] = argv[index + 1];
  }
  for (const key of ["appPath", "sessionDb", "traceRoot", "output"]) {
    if (!isAbsolute(options[key] || "")) throw new Error(`QWEN_TOKEN_LAUNCH_PATH_INVALID: ${key}`);
  }
  loopbackPort(options.endpoint);
  return options;
}

async function main(argv) {
  if (argv.includes("--help")) {
    console.log("QwenWork Token 开关安全启动：node token-launch.mjs --app-path PATH --session-db PATH --trace-root PATH --endpoint http://127.0.0.1:9250 --output NEW_JSON。只在无活动任务时重启精确 9250 监听进程；不修改全局环境。");
    return;
  }
  const options = parseArgs(argv);
  const output = resolve(options.output);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, JSON.stringify({ status: "STARTED", started_at: new Date().toISOString() }) + "\n",
    { flag: "wx", mode: 0o600 });
  try {
    const result = await ensureQwenTokenUsage(options);
    await writeFile(output, JSON.stringify({ ...result, completed_at: new Date().toISOString() }, null, 2) + "\n");
    console.log(JSON.stringify({ status: result.status, restarted: result.restarted,
      before_pid: result.before.pid, after_pid: result.after.pid, output }));
  } catch (error) {
    await writeFile(output, JSON.stringify({ status: "NEEDS_ATTENTION", failed_at: new Date().toISOString(),
      error: error instanceof Error ? error.message : String(error) }, null, 2) + "\n");
    throw error;
  }
}

if (process.argv[1] && await realpath(resolve(process.argv[1])) === await realpath(fileURLToPath(import.meta.url))) {
  main(process.argv.slice(2)).catch((error) => { console.error(error.message); process.exitCode = 1; });
}
