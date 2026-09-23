import test from "node:test";
import assert from "node:assert/strict";

import { ensureQwenTokenUsage } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/token-launch.mjs";
import {
  readQwenTokenProcess,
  sameQwenTokenProcess,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/token-process.mjs";

const APP_PATH = "/Applications/QwenWorkCN.app";
const OPTIONS = {
  appPath: APP_PATH,
  sessionDb: "/private/tmp/qwenwork-token-test/agents.db",
  traceRoot: "/private/tmp/qwenwork-token-test/trace",
  endpoint: "http://127.0.0.1:9250",
};

function probe(active = 0) {
  return {
    app: { path: APP_PATH, identity_verified: true, bundle_id: "cn.qwenwork.desktop.mac",
      version: "1.2.0", cdp: { ready: true, browser_identity_present: true } },
    native_state: { database: { quick_check: "ok", active_or_pending_count: active } },
    runtime: { identity: { runtime_sha256: "a".repeat(64) } },
  };
}

const original = { pid: 101, executable_path: `${APP_PATH}/Contents/MacOS/QwenWorkCN`,
  process_start_identity: "old-start", command_sha256: "a".repeat(64), token_usage_exposed: false };
const launched = { ...original, pid: 202, process_start_identity: "new-start",
  command_sha256: "b".repeat(64), token_usage_exposed: true };

test("Token launch refuses an active session before touching the client", async () => {
  let touched = false;
  await assert.rejects(ensureQwenTokenUsage(OPTIONS, {
    probe: async () => probe(1),
    listener: async () => { touched = true; return original; },
    signal: async () => { touched = true; return { code: 0 }; },
  }), /PREFLIGHT_NOT_IDLE_OR_VERIFIED/u);
  assert.equal(touched, false);
});

test("Token launch reuses an already exposed verified listener", async () => {
  let touched = false;
  const result = await ensureQwenTokenUsage(OPTIONS, {
    probe: async () => probe(), listener: async () => launched,
    signal: async () => { touched = true; return { code: 0 }; },
    launch: async () => { touched = true; return { code: 0 }; },
  });
  assert.equal(result.status, "ALREADY_EXPOSED");
  assert.equal(result.restarted, false);
  assert.equal(touched, false);
});

test("Token launch stops only the frozen process and verifies the new exposed client", async () => {
  let state = "old";
  const signals = [];
  const result = await ensureQwenTokenUsage(OPTIONS, {
    probe: async () => probe(),
    listener: async () => state === "old" ? original : state === "new" ? launched : null,
    process: async (pid) => pid === original.pid && state === "old" ? original : null,
    signal: async (pid, kind) => { signals.push([pid, kind]); state = "stopped"; return { code: 0 }; },
    launch: async () => { state = "new"; return { code: 0 }; },
  });
  assert.equal(result.status, "EXPOSED");
  assert.equal(result.stop_method, "TERM");
  assert.equal(result.after.pid, launched.pid);
  assert.deepEqual(signals, [[original.pid, "TERM"]]);
});

test("Token launch refuses a reused PID rather than escalating to KILL", async () => {
  let identity = original;
  const signals = [];
  await assert.rejects(ensureQwenTokenUsage(OPTIONS, {
    probe: async () => probe(), listener: async () => identity,
    process: async () => identity,
    signal: async (pid, kind) => {
      signals.push([pid, kind]);
      identity = { ...original, process_start_identity: "different-start" };
      return { code: 0 };
    },
  }), /PROCESS_IDENTITY_DRIFT/u);
  assert.deepEqual(signals, [[original.pid, "TERM"]]);
});

test("exact listener inspection never infers token exposure from an unrelated command", async () => {
  const runCommand = async (_command, args) => {
    if (args.includes("lstart=")) return { code: 0, stdout: "Wed Sep 23 13:00:00 2026\n" };
    if (args.includes("command=")) return { code: 0, stdout: `${APP_PATH}/Contents/MacOS/QwenWorkCN --remote-debugging-port=9250\n` };
    if (args.includes("pid=")) return { code: 0, stdout: "101\n" };
    return { code: 0, stdout: "PID COMMAND\n101 QODERCN_EXPOSE_TOKEN_USAGE=1\n" };
  };
  const identity = await readQwenTokenProcess(101, { appPath: APP_PATH, port: 9250, runCommand });
  assert.equal(identity.token_usage_exposed, true);
  assert.equal(sameQwenTokenProcess(identity, { ...identity, pid: 102 }), false);
  await assert.rejects(readQwenTokenProcess(101, { appPath: APP_PATH, port: 9240, runCommand }),
    /PROCESS_IDENTITY_MISMATCH/u);
});

test("process inspection treats exit during ps reads as absent but keeps live identity mismatch closed", async () => {
  const runCommand = async (_command, args) => {
    if (args.includes("lstart=")) return { code: 0, stdout: "Wed Sep 23 13:00:00 2026\n" };
    if (args.includes("command=")) return { code: 0, stdout: "\n" };
    if (args.includes("pid=")) return { code: 1, stdout: "" };
    return { code: 0, stdout: "PID COMMAND\n" };
  };
  assert.equal(await readQwenTokenProcess(101, { appPath: APP_PATH, port: 9250, runCommand }), null);
});
