import { spawn } from "node:child_process";
import { access, realpath, stat } from "node:fs/promises";
import * as systemPath from "node:path";

export const MACOS_CODEX_APP_PATH = "/Applications/ChatGPT.app";
export const WINDOWS_CODEX_EXECUTABLE_NAMES = Object.freeze(["ChatGPT.exe", "Codex.exe"]);

function runCapture(command, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const { allowFailure = false, ...spawnOptions } = options;
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"], ...spawnOptions });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", rejectPromise);
    child.once("exit", (code) => {
      if (code === 0 || allowFailure) resolvePromise({ code, stdout, stderr });
      else rejectPromise(new Error(`${command} 执行失败（退出码 ${code}）：${stderr.trim()}`));
    });
  });
}

function normalizeWindowsPath(value) {
  return String(value || "").trim().replace(/^"|"$/g, "").replaceAll("/", "\\").toLowerCase();
}

async function isFile(path, statPath) {
  try {
    return (await statPath(path)).isFile();
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function isDirectory(path, statPath) {
  try {
    return (await statPath(path)).isDirectory();
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function resolveWindowsExecutable(candidate, dependencies) {
  const { pathApi, realpathPath, statPath } = dependencies;
  if (await isFile(candidate, statPath)) {
    return WINDOWS_CODEX_EXECUTABLE_NAMES.some((name) => name.toLowerCase() === pathApi.basename(candidate).toLowerCase())
      ? realpathPath(candidate)
      : null;
  }
  if (!(await isDirectory(candidate, statPath))) return null;
  for (const name of WINDOWS_CODEX_EXECUTABLE_NAMES) {
    const executable = pathApi.join(candidate, name);
    if (await isFile(executable, statPath)) return realpathPath(executable);
  }
  return null;
}

function parseWindowsProcesses(stdout) {
  const value = String(stdout || "").trim();
  if (!value || value === "null") return [];
  const parsed = JSON.parse(value);
  return Array.isArray(parsed) ? parsed : [parsed];
}

export function defaultCodexAppPath(platform = process.platform) {
  return platform === "win32" ? "" : MACOS_CODEX_APP_PATH;
}

export async function resolveCodexAppPath(requestedPath, endpoint, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const pathApi = overrides.pathApi || (platform === "win32" ? systemPath.win32 : systemPath);
  const realpathPath = overrides.realpathPath || realpath;
  const statPath = overrides.statPath || stat;
  const runCommand = overrides.runCommand || runCapture;
  const environment = overrides.environment || process.env;

  if (platform !== "win32") {
    const candidate = requestedPath || MACOS_CODEX_APP_PATH;
    const resolved = await realpathPath(systemPath.resolve(candidate));
    await access(systemPath.join(resolved, "Contents", "Info.plist"));
    return resolved;
  }
  if (requestedPath) {
    const explicit = await resolveWindowsExecutable(requestedPath, { pathApi, realpathPath, statPath });
    if (!explicit) throw new Error(`--app-path 未指向受支持的 Codex Desktop 主程序或安装目录：${requestedPath}`);
    return explicit;
  }

  const port = new URL(endpoint).port || "9230";
  const script = `Get-CimInstance Win32_Process | Where-Object { @('ChatGPT.exe','Codex.exe') -contains $_.Name -and $_.CommandLine -match '--remote-debugging-port=${port}(?:\\s|$)' } | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress`;
  const processResult = await runCommand(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", script],
    { allowFailure: true },
  ).catch(() => ({ code: null, stdout: "" }));
  if (processResult.code === 0) {
    let processes = [];
    try {
      processes = parseWindowsProcesses(processResult.stdout);
    } catch {
      processes = [];
    }
    const executablePaths = [...new Set(processes.map((item) => normalizeWindowsPath(item.ExecutablePath)).filter(Boolean))];
    if (executablePaths.length > 1) {
      throw new Error(`检测到 ${executablePaths.length} 个使用 CDP ${port} 的 Codex Desktop 主程序，必须显式传入 --app-path`);
    }
    const discovered = processes.find((item) => item.ExecutablePath)?.ExecutablePath;
    if (discovered) {
      const executable = await resolveWindowsExecutable(discovered, { pathApi, realpathPath, statPath });
      if (executable) return executable;
    }
  }

  const localAppData = environment.LOCALAPPDATA || "";
  if (localAppData) {
    for (const directory of ["ChatGPT", "Codex"]) {
      const executable = await resolveWindowsExecutable(
        pathApi.join(localAppData, "Programs", directory),
        { pathApi, realpathPath, statPath },
      );
      if (executable) return executable;
    }
  }
  throw new Error("未找到正在使用目标 CDP 端口的 Codex Desktop Windows 主程序；请显式传入 --app-path <ChatGPT.exe或Codex.exe>");
}

export async function codexAppVersion(appPath, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    const escapedAppPath = String(appPath).replaceAll("'", "''");
    const script = [
      "$ErrorActionPreference = 'Stop'",
      `$AppPath = '${escapedAppPath}'`,
      "$Version = (Get-Item -LiteralPath $AppPath).VersionInfo.ProductVersion",
      "if ([string]::IsNullOrWhiteSpace($Version)) { exit 1 }",
      "[Console]::Out.Write($Version)",
    ].join("; ");
    const result = await runCommand(
      "powershell.exe",
      [
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        Buffer.from(script, "utf16le").toString("base64"),
      ],
      { allowFailure: true },
    );
    if (result.code !== 0 || !result.stdout.trim()) throw new Error(`无法读取 Codex Desktop 版本：${appPath}`);
    return result.stdout.trim();
  }
  const result = await runCommand(
    "/usr/libexec/PlistBuddy",
    ["-c", "Print :CFBundleShortVersionString", systemPath.join(appPath, "Contents", "Info.plist")],
  );
  return result.stdout.trim();
}

export function folderHelperInvocation({ platform = process.platform, driverDir, bundleId, appPath, project, timeoutSeconds }) {
  if (platform === "win32") {
    return {
      command: "powershell.exe",
      args: [
        "-NoProfile",
        "-NonInteractive",
        "-STA",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        systemPath.join(driverDir, "select-folder.ps1"),
        "-AppPath",
        appPath,
        "-Folder",
        project,
        "-TimeoutSeconds",
        String(timeoutSeconds),
      ],
    };
  }
  return {
    command: "/usr/bin/xcrun",
    args: ["swift", systemPath.join(driverDir, "select-folder.swift"), bundleId, project, String(timeoutSeconds)],
  };
}

export function runFolderHelper(options, overrides = {}) {
  const runCommand = overrides.runCommand || runCapture;
  const invocation = folderHelperInvocation(options);
  return runCommand(invocation.command, invocation.args).then((result) => JSON.parse(result.stdout));
}
