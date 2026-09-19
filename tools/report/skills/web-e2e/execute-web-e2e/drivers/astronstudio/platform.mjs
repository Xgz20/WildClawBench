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
  ASTRONSTUDIO_APP_PROFILE,
} from "../../vendor/e2e-shared/desktop-app-discovery/profiles.mjs";

export const MACOS_APP_PATH = "/Applications/AStudio.app";
export const WINDOWS_EXECUTABLE_NAMES = Object.freeze([
  "AStudio.exe",
  "AstronStudio.exe",
  "Acode.exe",
]);
export const HOST_CONTROL_ENVIRONMENT_PREFIXES = Object.freeze(["CODEX_", "CHATGPT_"]);
export const HOST_IPC_ENVIRONMENT_NAMES = Object.freeze([
  "ELECTRON_RUN_AS_NODE",
  "NODE_CHANNEL_FD",
  "NODE_UNIQUE_ID",
]);

export function sanitizeAstronLaunchEnvironment(environment = process.env) {
  const sanitized = { ...environment };
  const removedVariables = [];
  const explicitNames = new Set(HOST_IPC_ENVIRONMENT_NAMES.map((name) => name.toUpperCase()));
  for (const name of Object.keys(sanitized)) {
    const normalized = name.toUpperCase();
    if (
      HOST_CONTROL_ENVIRONMENT_PREFIXES.some((prefix) => normalized.startsWith(prefix))
      || explicitNames.has(normalized)
    ) {
      delete sanitized[name];
      removedVariables.push(name);
    }
  }
  removedVariables.sort((left, right) => left.localeCompare(right));
  return { environment: sanitized, removedVariables };
}

function spawnDetached(command, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      detached: true,
      stdio: "ignore",
      windowsHide: false,
      env: options.environment || process.env,
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
    .replace(/^"|"$/g, "")
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

export function defaultAstronAppPath(platform = process.platform) {
  return platform === "win32" ? "" : MACOS_APP_PATH;
}

export function astronSessionDbCandidates(home = homedir(), pathApi = systemPath, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const environment = overrides.environment || process.env;
  const candidates = [pathApi.join(home, ".acode", "acode", "userdata", "state.sqlite")];

  if (platform === "win32") {
    const localAppData = environment.LOCALAPPDATA || pathApi.join(home, "AppData", "Local");
    candidates.push(pathApi.join(
      localAppData,
      "Programs",
      "AStudio Data",
      "userdata",
      "state.sqlite",
    ));
  }

  return [...new Set(candidates)];
}

export function defaultAstronSessionDb(home = homedir(), pathApi = systemPath, overrides = {}) {
  const existsPath = overrides.existsPath || existsSync;
  const candidates = astronSessionDbCandidates(home, pathApi, overrides);
  return candidates.find((candidate) => existsPath(candidate)) || candidates[0];
}

export async function resolveAstronAppPath(requestedPath = "", overrides = {}) {
  const platform = overrides.platform || process.platform;
  const discovery = await discoverDesktopApp({
    profile: ASTRONSTUDIO_APP_PROFILE,
    requestedPath,
    platform,
    endpoint: overrides.endpoint || null,
    environment: overrides.environment || process.env,
    home: overrides.home || homedir(),
  }, overrides);
  return discovery.path;
}

export async function discoverAstronApp(requestedPath = "", overrides = {}) {
  const platform = overrides.platform || process.platform;
  return discoverDesktopApp({
    profile: ASTRONSTUDIO_APP_PROFILE,
    requestedPath,
    platform,
    endpoint: overrides.endpoint || null,
    environment: overrides.environment || process.env,
    home: overrides.home || homedir(),
  }, overrides);
}

export async function validateAstronAppPath(appPath, platform = process.platform) {
  if (platform === "win32") {
    const name = systemPath.win32.basename(appPath).toLowerCase();
    if (!WINDOWS_EXECUTABLE_NAMES.some((candidate) => candidate.toLowerCase() === name)) {
      throw new Error(`AstronStudio Windows 主程序名称不受支持：${appPath}`);
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
public static class WcbDesktop {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll", SetLastError = true)] public static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint desiredAccess);
  [DllImport("user32.dll", SetLastError = true)] public static extern bool SwitchDesktop(IntPtr desktop);
  [DllImport("user32.dll", SetLastError = true)] public static extern bool CloseDesktop(IntPtr desktop);
}
'@
$handle = [WcbDesktop]::GetForegroundWindow()
[uint32]$foregroundPid = 0
if ($handle -ne [IntPtr]::Zero) { [void][WcbDesktop]::GetWindowThreadProcessId($handle, [ref]$foregroundPid) }
$name = if ($foregroundPid -gt 0) { (Get-Process -Id $foregroundPid -ErrorAction SilentlyContinue).ProcessName } else { $null }
$inputDesktop = [WcbDesktop]::OpenInputDesktop(0, $false, 0x0100)
$desktopSwitchable = $false
if ($inputDesktop -ne [IntPtr]::Zero) {
  try { $desktopSwitchable = [WcbDesktop]::SwitchDesktop($inputDesktop) }
  finally { [void][WcbDesktop]::CloseDesktop($inputDesktop) }
}
$locked = (-not $desktopSwitchable) -or ($name -match '^(LockApp|LogonUI)$')
[pscustomobject]@{
  frontmost_application = $(if ($name) { $name } else { 'unknown' })
  screen_locked = $locked
  unlocked = ([Environment]::UserInteractive -and $desktopSwitchable -and -not $locked)
  lock_source = 'user32.OpenInputDesktop+SwitchDesktop'
} | ConvertTo-Json -Compress
`;

export async function astronGuiSessionStatus(overrides = {}) {
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
  const lockMatch = registry.stdout.match(/"IOConsoleLocked"\s*=\s*(Yes|No)/);
  const screenLocked = lockMatch ? lockMatch[1] === "Yes" : null;
  return {
    frontmost_application: "unknown",
    screen_locked: screenLocked,
    lock_source: lockMatch ? "ioreg.IOConsoleLocked" : "ioreg-unavailable",
    unlocked: screenLocked === false,
  };
}

export async function astronAppVersion(appPath, overrides = {}) {
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

function parseWindowsProcesses(stdout) {
  const text = String(stdout || "").trim();
  if (!text || text === "null") return [];
  const parsed = JSON.parse(text);
  return Array.isArray(parsed) ? parsed : [parsed];
}

export async function astronProcessIdentity(appPath, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    const script = `Get-CimInstance Win32_Process | Where-Object { @('AStudio.exe','AstronStudio.exe','Acode.exe') -contains $_.Name } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress`;
    const result = await runCommand(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      { capture: true, allowFailure: true },
    ).catch(() => ({ code: null, stdout: "" }));
    if (result.code !== 0) return null;
    let processes;
    try {
      processes = parseWindowsProcesses(result.stdout);
    } catch {
      return null;
    }
    const expectedPath = normalizeWindowsPath(appPath);
    const executableMatches = processes.filter((item) => {
      const executablePath = normalizeWindowsPath(item.ExecutablePath);
      const exactExecutable = executablePath && executablePath === expectedPath;
      const commandMatches = normalizeWindowsPath(windowsCommandExecutable(item.CommandLine)) === expectedPath;
      return exactExecutable || commandMatches;
    });
    const matchingPids = new Set(executableMatches
      .map((item) => Number(item.ProcessId))
      .filter((pid) => Number.isInteger(pid) && pid > 0));
    const matches = executableMatches.filter((item) => {
      const commandLine = String(item.CommandLine || "");
      const parentPid = Number(item.ParentProcessId);
      const isSameExecutableChild = Number.isInteger(parentPid) && matchingPids.has(parentPid);
      const isElectronChild = /(?:^|\s)--type=/iu.test(commandLine);
      const isNodeRuntimeChild = /(?:^|\s)(?:--max-old-space-size(?:=|\s)|-e(?:\s|$))/iu.test(commandLine);
      return !isSameExecutableChild && !isElectronChild && !isNodeRuntimeChild;
    });
    if (matches.length > 1) {
      throw new Error(`检测到 ${matches.length} 个与 ${appPath} 匹配的 AstronStudio 主进程，拒绝选择不唯一 PID`);
    }
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
    profile: ASTRONSTUDIO_APP_PROFILE,
    appPath,
  }, { ...overrides, runCommand });
}

export async function gracefulQuitAstron(processInfo, overrides = {}) {
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

export async function terminateAstronProcess(processInfo, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    return runCommand(
      "taskkill.exe",
      ["/PID", String(processInfo.pid), "/T", "/F"],
      { allowFailure: true, capture: true },
    );
  }
  return runCommand(
    "/bin/kill",
    ["-KILL", String(processInfo.pid)],
    { allowFailure: true, capture: true },
  );
}

export async function launchAstron(appPath, port, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  const launchDetached = overrides.launchDetached || spawnDetached;
  const debugArgs = ["--remote-debugging-address=127.0.0.1", `--remote-debugging-port=${port}`];
  if (platform === "win32") {
    const launchEnvironment = sanitizeAstronLaunchEnvironment(overrides.environment || process.env);
    const result = await launchDetached(appPath, debugArgs, {
      environment: launchEnvironment.environment,
    });
    return {
      ...result,
      environment_preparation: {
        strategy: "remove-host-control-and-node-ipc-variables",
        removed_variables: launchEnvironment.removedVariables,
      },
    };
  }
  return runCommand(
    "/usr/bin/open",
    ["-na", appPath, "--args", ...debugArgs],
    { allowFailure: true, capture: true },
  );
}
