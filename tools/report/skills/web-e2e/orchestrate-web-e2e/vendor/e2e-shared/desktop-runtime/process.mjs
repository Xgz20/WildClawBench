import { spawn } from "node:child_process";

export const COMPONENT_NAME = "desktop-runtime";
export const COMPONENT_VERSION = "1.0.1";

export function runCapture(command, args, options = {}, overrides = {}) {
  const spawnProcess = overrides.spawnProcess || spawn;
  return new Promise((resolvePromise, rejectPromise) => {
    const { allowFailure = false, capture: _capture = true, ...spawnOptions } = options;
    const child = spawnProcess(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
      ...spawnOptions,
    });
    // A multibyte UTF-8 character can span arbitrary pipe chunks. Decode only
    // after stdio closes; exit can precede the last stdout/stderr data event.
    const stdoutChunks = [];
    const stderrChunks = [];
    child.stdout?.on("data", (chunk) => { stdoutChunks.push(Buffer.from(chunk)); });
    child.stderr?.on("data", (chunk) => { stderrChunks.push(Buffer.from(chunk)); });
    child.once("error", rejectPromise);
    child.once("close", (code) => {
      const stdout = Buffer.concat(stdoutChunks).toString("utf8");
      const stderr = Buffer.concat(stderrChunks).toString("utf8");
      if (code === 0 || allowFailure) resolvePromise({ code, stdout, stderr });
      else rejectPromise(new Error(`${command} 执行失败（退出码 ${code}）：${stderr.trim()}`));
    });
  });
}

export async function isFile(path, statPath) {
  try {
    return (await statPath(path)).isFile();
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

export async function isDirectory(path, statPath) {
  try {
    return (await statPath(path)).isDirectory();
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}
