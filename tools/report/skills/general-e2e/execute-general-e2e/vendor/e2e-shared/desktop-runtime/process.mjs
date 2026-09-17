import { spawn } from "node:child_process";

export const COMPONENT_NAME = "desktop-runtime";
export const COMPONENT_VERSION = "1.0.0";

export function runCapture(command, args, options = {}, overrides = {}) {
  const spawnProcess = overrides.spawnProcess || spawn;
  return new Promise((resolvePromise, rejectPromise) => {
    const { allowFailure = false, capture: _capture = true, ...spawnOptions } = options;
    const child = spawnProcess(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
      ...spawnOptions,
    });
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (chunk) => { stdout += chunk; });
    child.stderr?.on("data", (chunk) => { stderr += chunk; });
    child.once("error", rejectPromise);
    child.once("exit", (code) => {
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
