import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { access } from "node:fs/promises";
import { homedir } from "node:os";
import * as systemPath from "node:path";
import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";
import {
  discoverDesktopApp,
  inspectMacDesktopAppProcess,
} from "../../vendor/e2e-shared/desktop-app-discovery/index.mjs";
import {
  QWENWORK_APP_PROFILE,
} from "../../vendor/e2e-shared/desktop-app-discovery/profiles.mjs";

export const MACOS_APP_PATH = "/Applications/QwenWorkCN.app";
export const MACOS_BUNDLE_ID = "cn.qwenwork.desktop.mac";
export const WINDOWS_EXECUTABLE_NAMES = Object.freeze(["QwenWorkCN.exe", "QwenWork.exe"]);

let nodeSqlitePromise;

function spawnDetached(command, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      detached: true,
      stdio: "ignore",
      windowsHide: false,
      ...options,
    });
    child.once("error", rejectPromise);
    child.once("spawn", () => {
      const pid = child.pid;
      child.unref();
      resolvePromise({ code: 0, stdout: "", stderr: "", pid });
    });
  });
}

function normalizeWindowsPath(value) {
  return String(value || "")
    .trim()
    .replace(/^"|"$/gu, "")
    .replaceAll("/", "\\")
    .replace(/\\+$/u, "")
    .toLowerCase();
}

function windowsCommandExecutable(commandLine) {
  const value = String(commandLine || "").trim();
  if (!value) return "";
  if (value.startsWith('"')) {
    const closingQuote = value.indexOf('"', 1);
    return closingQuote > 1 ? value.slice(1, closingQuote) : "";
  }
  return value.split(/\s+/u, 1)[0];
}

function parsePowerShellJson(stdout) {
  const text = String(stdout || "").trim();
  if (!text || text === "null") return [];
  const parsed = JSON.parse(text);
  return Array.isArray(parsed) ? parsed : [parsed];
}

export function defaultQwenWorkAppPath(platform = process.platform) {
  return platform === "win32" ? "" : MACOS_APP_PATH;
}

export function defaultQwenWorkSessionDb(home = homedir(), pathApi = systemPath, overrides = {}) {
  const platform = overrides.platform || process.platform;
  if (platform === "win32") return pathApi.join(home, "AppData", "Roaming", "QwenWorkCN", "data", "agents.db");
  return pathApi.join(home, "Library", "Application Support", "QwenWorkCN", "data", "agents.db");
}

export async function resolveQwenWorkAppPath(requestedPath = "", overrides = {}) {
  const platform = overrides.platform || process.platform;
  const discovery = await discoverDesktopApp({
    profile: QWENWORK_APP_PROFILE,
    requestedPath,
    platform,
    endpoint: overrides.endpoint || null,
    environment: overrides.environment || process.env,
    home: overrides.home || homedir(),
  }, overrides);
  return discovery.path;
}

export async function discoverQwenWorkApp(requestedPath = "", overrides = {}) {
  const platform = overrides.platform || process.platform;
  return discoverDesktopApp({
    profile: QWENWORK_APP_PROFILE,
    requestedPath,
    platform,
    endpoint: overrides.endpoint || null,
    environment: overrides.environment || process.env,
    home: overrides.home || homedir(),
  }, overrides);
}

export async function validateQwenWorkAppPath(appPath, platform = process.platform) {
  if (platform === "win32") {
    const name = systemPath.win32.basename(appPath).toLowerCase();
    if (!WINDOWS_EXECUTABLE_NAMES.some((candidate) => candidate.toLowerCase() === name)) {
      throw new Error(`QwenWork Windows 主程序名称不受支持：${appPath}`);
    }
    await access(appPath);
    await access(systemPath.win32.join(systemPath.win32.dirname(appPath), "resources", "app.asar"));
    return;
  }
  await access(systemPath.join(appPath, "Contents", "Resources", "app.asar"));
}

const WINDOWS_GUI_STATUS_SCRIPT = `
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class WcbQwenDesktop {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll", SetLastError = true)] public static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint desiredAccess);
  [DllImport("user32.dll", SetLastError = true)] public static extern bool SwitchDesktop(IntPtr desktop);
  [DllImport("user32.dll", SetLastError = true)] public static extern bool CloseDesktop(IntPtr desktop);
}
'@
$handle = [WcbQwenDesktop]::GetForegroundWindow()
[uint32]$foregroundPid = 0
if ($handle -ne [IntPtr]::Zero) { [void][WcbQwenDesktop]::GetWindowThreadProcessId($handle, [ref]$foregroundPid) }
$name = if ($foregroundPid -gt 0) { (Get-Process -Id $foregroundPid -ErrorAction SilentlyContinue).ProcessName } else { $null }
$inputDesktop = [WcbQwenDesktop]::OpenInputDesktop(0, $false, 0x0100)
$desktopSwitchable = $false
if ($inputDesktop -ne [IntPtr]::Zero) {
  try { $desktopSwitchable = [WcbQwenDesktop]::SwitchDesktop($inputDesktop) }
  finally { [void][WcbQwenDesktop]::CloseDesktop($inputDesktop) }
}
$locked = (-not $desktopSwitchable) -or ($name -match '^(LockApp|LogonUI)$')
[pscustomobject]@{
  frontmost_application = $(if ($name) { $name } else { 'unknown' })
  screen_locked = $locked
  unlocked = ([Environment]::UserInteractive -and $desktopSwitchable -and -not $locked)
  lock_source = 'user32.OpenInputDesktop+SwitchDesktop'
} | ConvertTo-Json -Compress
`;

export async function qwenWorkGuiSessionStatus(overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    const result = await runCommand(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", WINDOWS_GUI_STATUS_SCRIPT],
      { capture: true, allowFailure: true },
    ).catch((error) => ({ code: null, stdout: "", stderr: error instanceof Error ? error.message : String(error) }));
    if (result.code !== 0) {
      return {
        frontmost_application: "unknown",
        screen_locked: null,
        lock_source: "windows-gui-probe-failed",
        unlocked: false,
        error: String(result.stderr || "").trim() || "PowerShell 图形会话探测失败",
      };
    }
    try {
      const parsed = JSON.parse(result.stdout.trim());
      return {
        frontmost_application: parsed.frontmost_application || "unknown",
        screen_locked: typeof parsed.screen_locked === "boolean" ? parsed.screen_locked : null,
        lock_source: parsed.lock_source || "user32.GetForegroundWindow",
        unlocked: parsed.unlocked === true,
      };
    } catch (error) {
      return {
        frontmost_application: "unknown",
        screen_locked: null,
        lock_source: "windows-gui-probe-invalid-json",
        unlocked: false,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }
  const registry = await runCommand(
    "/usr/sbin/ioreg",
    ["-n", "Root", "-d1"],
    { capture: true, allowFailure: true },
  );
  const lockMatch = registry.stdout.match(/"IOConsoleLocked"\s*=\s*(Yes|No)/u);
  const screenLocked = lockMatch ? lockMatch[1] === "Yes" : null;
  return {
    frontmost_application: "unknown",
    screen_locked: screenLocked,
    lock_source: lockMatch ? "ioreg.IOConsoleLocked" : "ioreg-unavailable",
    unlocked: screenLocked === false,
  };
}

export async function qwenWorkAppVersion(appPath, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  const command = platform === "win32" ? "powershell.exe" : "/usr/bin/defaults";
  const args = platform === "win32"
    ? [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      "& { param([string]$AppPath) (Get-Item -LiteralPath $AppPath).VersionInfo.ProductVersion }",
      appPath,
    ]
    : ["read", systemPath.join(appPath, "Contents", "Info"), "CFBundleShortVersionString"];
  const result = await runCommand(command, args, { capture: true, allowFailure: true })
    .catch(() => ({ code: null, stdout: "" }));
  return result.code === 0 ? result.stdout.trim() || "unknown" : "unknown";
}

export async function qwenWorkProcessIdentity(appPath, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    const script = `Get-CimInstance Win32_Process | Where-Object { @('QwenWorkCN.exe','QwenWork.exe') -contains $_.Name } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress`;
    const result = await runCommand(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      { capture: true, allowFailure: true },
    ).catch(() => ({ code: null, stdout: "" }));
    if (result.code !== 0) return null;
    let processes;
    try {
      processes = parsePowerShellJson(result.stdout);
    } catch {
      return null;
    }
    const expectedPath = normalizeWindowsPath(appPath);
    const executableMatches = processes.filter((item) => {
      const executablePath = normalizeWindowsPath(item.ExecutablePath);
      return (executablePath && executablePath === expectedPath)
        || normalizeWindowsPath(windowsCommandExecutable(item.CommandLine)) === expectedPath;
    });
    const matchingPids = new Set(executableMatches
      .map((item) => Number(item.ProcessId))
      .filter((pid) => Number.isInteger(pid) && pid > 0));
    const matches = executableMatches.filter((item) => {
      const commandLine = String(item.CommandLine || "");
      const parentPid = Number(item.ParentProcessId);
      const isSameExecutableChild = Number.isInteger(parentPid) && matchingPids.has(parentPid);
      return !isSameExecutableChild && !/(?:^|\s)--type=/iu.test(commandLine);
    });
    if (matches.length > 1) throw new Error(`检测到 ${matches.length} 个与 ${appPath} 匹配的 QwenWork 主进程，拒绝选择不唯一 PID`);
    const processInfo = matches[0];
    const pid = Number(processInfo?.ProcessId);
    if (!Number.isInteger(pid) || pid <= 0) return null;
    return {
      pid,
      executable_path: processInfo.ExecutablePath || appPath,
      command: processInfo.CommandLine || null,
      platform: "win32",
      captured_at: new Date().toISOString(),
    };
  }
  return inspectMacDesktopAppProcess({
    profile: QWENWORK_APP_PROFILE,
    appPath,
  }, { ...overrides, runCommand });
}

export async function gracefulQuitQwenWork(processInfo, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    const script = "& { param([int]$ProcessId) $process = Get-Process -Id $ProcessId -ErrorAction Stop; if (-not $process.CloseMainWindow()) { exit 3 } }";
    return runCommand(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script, String(processInfo.pid)],
      { capture: true, allowFailure: true },
    );
  }
  return runCommand(
    "/bin/kill",
    ["-TERM", String(processInfo.pid)],
    { allowFailure: true, capture: true },
  );
}

export async function terminateQwenWorkProcess(processInfo, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    return runCommand("taskkill.exe", ["/PID", String(processInfo.pid), "/T", "/F"], { allowFailure: true, capture: true });
  }
  return runCommand("/bin/kill", ["-KILL", String(processInfo.pid)], { allowFailure: true, capture: true });
}

export const QWEN_TOKEN_USAGE_ENV_NAME = "QODERCN_EXPOSE_TOKEN_USAGE";
export const QWEN_TOKEN_USAGE_ENV_VALUE = "1";

export function qwenWorkLaunchEnvironment(environment = process.env) {
  return {
    ...environment,
    [QWEN_TOKEN_USAGE_ENV_NAME]: QWEN_TOKEN_USAGE_ENV_VALUE,
  };
}

export async function launchQwenWork(appPath, port, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  const launchDetached = overrides.launchDetached || spawnDetached;
  const debugArgs = ["--remote-debugging-address=127.0.0.1", `--remote-debugging-port=${port}`];
  const environment = qwenWorkLaunchEnvironment(overrides.environment || process.env);
  // Token 暴露开关与 CDP 参数都由 Driver 注入到新客户端进程；不修改控制 Harness 的全局环境。
  const envArgs = ["--env", `${QWEN_TOKEN_USAGE_ENV_NAME}=${QWEN_TOKEN_USAGE_ENV_VALUE}`];
  if (platform === "win32") return launchDetached(appPath, debugArgs, { env: environment });
  return runCommand("/usr/bin/open", ["-na", appPath, ...envArgs, "--args", ...debugArgs], { allowFailure: true, capture: true });
}

async function loadNodeSqlite() {
  if (!nodeSqlitePromise) nodeSqlitePromise = import("node:sqlite").catch(() => null);
  return nodeSqlitePromise;
}

const PYTHON_QUERY_SCRIPT = String.raw`
import json, pathlib, sqlite3, sys
db_path = pathlib.Path(sys.argv[1]).resolve()
database = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
database.row_factory = sqlite3.Row
rows = [dict(row) for row in database.execute(sys.argv[2])]
database.close()
print(json.dumps(rows, ensure_ascii=False))
`;

async function queryWithNodeSqlite(sqliteModule, sessionDb, sql) {
  const database = new sqliteModule.DatabaseSync(sessionDb, { readOnly: true });
  try {
    return database.prepare(sql).all();
  } finally {
    database.close();
  }
}

async function queryWithPython(sessionDb, sql, runCommand) {
  const attempts = [
    { command: "py.exe", args: ["-3", "-c", PYTHON_QUERY_SCRIPT, sessionDb, sql], backend: "python-sqlite3:py-3" },
    { command: "python.exe", args: ["-c", PYTHON_QUERY_SCRIPT, sessionDb, sql], backend: "python-sqlite3:python" },
  ];
  const errors = [];
  for (const attempt of attempts) {
    const result = await runCommand(attempt.command, attempt.args, { capture: true, allowFailure: true })
      .catch((error) => ({ code: null, stdout: "", stderr: error instanceof Error ? error.message : String(error) }));
    if (result.code === 0) return { backend: attempt.backend, rows: JSON.parse(result.stdout.trim() || "[]") };
    errors.push(`${attempt.command}: ${String(result.stderr || `退出码 ${result.code}`).trim()}`);
  }
  throw new Error(`Windows 无可用的只读 SQLite 后端：${errors.join("；")}`);
}

export async function queryQwenWorkSqlite(sessionDb, sql, overrides = {}) {
  await access(sessionDb);
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  const sqliteModule = await (overrides.loadNodeSqlite || loadNodeSqlite)();
  if (typeof sqliteModule?.DatabaseSync === "function") {
    return { backend: "node:sqlite", rows: await queryWithNodeSqlite(sqliteModule, sessionDb, sql) };
  }
  if (platform === "win32") return queryWithPython(sessionDb, sql, runCommand);
  const result = await runCommand("/usr/bin/sqlite3", ["-readonly", "-json", sessionDb, sql], { capture: true });
  return { backend: "sqlite3-cli", rows: result.stdout.trim() ? JSON.parse(result.stdout) : [] };
}

export async function qwenWorkSqliteBackendStatus(overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  const sqliteModule = await (overrides.loadNodeSqlite || loadNodeSqlite)();
  if (typeof sqliteModule?.DatabaseSync === "function") {
    return { available: true, backend: "node:sqlite", command: null, error: null };
  }
  if (platform === "win32") {
    for (const candidate of [
      { command: "py.exe", args: ["-3", "-c", "import sqlite3"], backend: "python-sqlite3:py-3" },
      { command: "python.exe", args: ["-c", "import sqlite3"], backend: "python-sqlite3:python" },
    ]) {
      const result = await runCommand(candidate.command, candidate.args, { capture: true, allowFailure: true })
        .catch(() => ({ code: null, stderr: "" }));
      if (result.code === 0) return { available: true, backend: candidate.backend, command: candidate.command, error: null };
    }
    return { available: false, backend: null, command: null, error: "未找到 node:sqlite、py -3 或 python SQLite 后端" };
  }
  const result = await runCommand("/usr/bin/sqlite3", ["--version"], { capture: true, allowFailure: true })
    .catch((error) => ({ code: null, stderr: error instanceof Error ? error.message : String(error) }));
  return result.code === 0
    ? { available: true, backend: "sqlite3-cli", command: "/usr/bin/sqlite3", error: null }
    : { available: false, backend: null, command: "/usr/bin/sqlite3", error: String(result.stderr || "sqlite3 不可用").trim() };
}

export function qwenWorkSessionDbExists(sessionDb) {
  return existsSync(sessionDb);
}

export function qwenWorkFolderHelperInvocation({
  platform = process.platform,
  driverDir,
  bundleId = MACOS_BUNDLE_ID,
  appPath,
  folder,
  timeoutSeconds,
}) {
  const pathApi = platform === "win32" ? systemPath.win32 : systemPath;
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
        pathApi.join(driverDir, "select-folder.ps1"),
        "-AppPath",
        appPath,
        "-Folder",
        folder,
        "-TimeoutSeconds",
        String(timeoutSeconds),
      ],
    };
  }
  return {
    command: "/usr/bin/swift",
    args: [pathApi.join(driverDir, "select-folder.swift"), bundleId, folder, String(timeoutSeconds)],
  };
}
