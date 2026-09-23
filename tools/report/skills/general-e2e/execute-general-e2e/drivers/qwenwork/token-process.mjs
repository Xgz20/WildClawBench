import { createHash } from "node:crypto";
import { join, resolve } from "node:path";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";

export const QWEN_TOKEN_USAGE_ENV_NAME = "QODERCN_EXPOSE_TOKEN_USAGE";
export const QWEN_TOKEN_USAGE_ENV_VALUE = "1";

function commandSha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function expectedExecutable(appPath) {
  return join(resolve(appPath), "Contents", "MacOS", "QwenWorkCN");
}

export async function readQwenTokenProcess(pid, { appPath, port, runCommand = runCapture } = {}) {
  if (!Number.isSafeInteger(pid) || pid <= 0) throw new Error("QWEN_TOKEN_PROCESS_PID_INVALID");
  const [started, commandResult, environmentResult] = await Promise.all([
    runCommand("/bin/ps", ["-p", String(pid), "-o", "lstart="], { capture: true, allowFailure: true }),
    runCommand("/bin/ps", ["-p", String(pid), "-o", "command="], { capture: true, allowFailure: true }),
    runCommand("/bin/ps", ["eww", "-p", String(pid)], { capture: true, allowFailure: true }),
  ]);
  if (started.code !== 0 && commandResult.code !== 0) return null;
  if (started.code !== 0 || commandResult.code !== 0 || environmentResult.code !== 0) {
    throw new Error("QWEN_TOKEN_PROCESS_INSPECTION_INCOMPLETE");
  }
  const startIdentity = String(started.stdout || "").trim();
  const command = String(commandResult.stdout || "").trim();
  const executable = expectedExecutable(appPath);
  if (!startIdentity || !command.startsWith(`${executable} `)
      || !command.split(/\s+/u).includes(`--remote-debugging-port=${port}`)) {
    throw new Error("QWEN_TOKEN_PROCESS_IDENTITY_MISMATCH");
  }
  const exposure = String(environmentResult.stdout || "")
    .match(/(?:^|\s)QODERCN_EXPOSE_TOKEN_USAGE=([^\s]+)/u);
  return {
    pid,
    executable_path: executable,
    process_start_identity: startIdentity,
    command_sha256: commandSha256(command),
    token_usage_exposed: exposure?.[1] === QWEN_TOKEN_USAGE_ENV_VALUE,
  };
}

export async function readQwenTokenListener({ appPath, port, runCommand = runCapture } = {}) {
  const result = await runCommand("/usr/sbin/lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-t"],
    { capture: true, allowFailure: true });
  if (result.code === 1 && !String(result.stdout || "").trim()) return null;
  if (result.code !== 0) throw new Error("QWEN_TOKEN_LISTENER_INSPECTION_FAILED");
  const lines = String(result.stdout || "").trim().split(/\r?\n/u).filter(Boolean);
  if (lines.length !== 1 || !/^\d+$/u.test(lines[0])) {
    throw new Error(`QWEN_TOKEN_LISTENER_NOT_UNIQUE: ${lines.length}`);
  }
  const identity = await readQwenTokenProcess(Number(lines[0]), { appPath, port, runCommand });
  if (!identity) throw new Error("QWEN_TOKEN_LISTENER_PROCESS_MISSING");
  return identity;
}

export function sameQwenTokenProcess(left, right) {
  return Boolean(left && right)
    && left.pid === right.pid
    && left.process_start_identity === right.process_start_identity
    && left.command_sha256 === right.command_sha256;
}
