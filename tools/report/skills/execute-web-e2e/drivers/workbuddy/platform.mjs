import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { access, realpath, stat } from "node:fs/promises";
import { homedir } from "node:os";
import * as systemPath from "node:path";

export const MACOS_APP_PATH = "/Applications/WorkBuddy.app";
export const MACOS_BUNDLE_ID = "com.tencent.workbuddy.mac";
export const WINDOWS_EXECUTABLE_NAMES = Object.freeze(["WorkBuddy.exe", "CodeBuddy.exe"]);

let nodeSqlitePromise;

function runCapture(command, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const { allowFailure = false, capture: _capture = true, ...spawnOptions } = options;
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"], ...spawnOptions });
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

function spawnDetached(command, args) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      detached: true,
      stdio: "ignore",
      windowsHide: false,
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

async function findWindowsExecutable(candidate, dependencies) {
  const { pathApi, realpathPath, statPath } = dependencies;
  if (await isFile(candidate, statPath)) {
    if (!WINDOWS_EXECUTABLE_NAMES.some((name) => name.toLowerCase() === pathApi.basename(candidate).toLowerCase())) {
      return null;
    }
    return realpathPath(candidate);
  }
  if (!(await isDirectory(candidate, statPath))) return null;
  for (const executableName of WINDOWS_EXECUTABLE_NAMES) {
    const executable = pathApi.join(candidate, executableName);
    if (await isFile(executable, statPath)) return realpathPath(executable);
  }
  return null;
}

function parsePowerShellJson(stdout) {
  const text = String(stdout || "").trim();
  if (!text || text === "null") return [];
  const parsed = JSON.parse(text);
  return Array.isArray(parsed) ? parsed : [parsed];
}

const WINDOWS_PROCESS_SNAPSHOT_SCRIPT = `
Get-CimInstance Win32_Process |
  Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine |
  ConvertTo-Json -Compress
`;

function windowsCommandReferencesPath(commandLine, candidateWorkspace) {
  const command = normalizeWindowsPath(commandLine).replace(/\\+/gu, "\\");
  const workspace = normalizeWindowsPath(candidateWorkspace).replace(/\\+/gu, "\\");
  if (!command || !workspace) return false;
  let index = command.indexOf(workspace);
  while (index >= 0) {
    const trailing = command[index + workspace.length] || "";
    if (!trailing || /[\\\s"']/u.test(trailing)) return true;
    index = command.indexOf(workspace, index + 1);
  }
  return false;
}

export function selectCandidateWorkspaceProcesses(processes, candidateWorkspace, {
  excludedPids = [],
  taskRoot = null,
  includeSessionHost = false,
} = {}) {
  if (!systemPath.win32.isAbsolute(candidateWorkspace)) {
    throw new Error(`候选 workspace 必须是 Windows 绝对路径：${candidateWorkspace}`);
  }
  const excluded = new Set(excludedPids.map(Number));
  const normalized = (processes || []).map((item) => ({
    pid: Number(item.ProcessId),
    parent_pid: Number(item.ParentProcessId) || null,
    name: String(item.Name || ""),
    executable_path: item.ExecutablePath ? String(item.ExecutablePath) : null,
    command_line: item.CommandLine ? String(item.CommandLine) : null,
  })).filter((item) => Number.isInteger(item.pid) && item.pid > 0 && !excluded.has(item.pid));
  const byPid = new Map(normalized.map((item) => [item.pid, item]));
  if (includeSessionHost && (!taskRoot || !systemPath.win32.isAbsolute(taskRoot))) {
    throw new Error(`清理 WorkBuddy 会话宿主需要 Windows 绝对 task 根：${taskRoot || "<empty>"}`);
  }
  const workspaceSeedPids = new Set(normalized
    .filter((item) => windowsCommandReferencesPath(item.command_line, candidateWorkspace))
    .map((item) => item.pid));
  const sessionHosts = includeSessionHost ? normalized.filter((item) => {
    const commandLine = String(item.command_line || "");
    return WINDOWS_EXECUTABLE_NAMES.some((name) => name.toLowerCase() === item.name.toLowerCase())
      && /(?:^|\s)--serve(?:\s|$)/iu.test(commandLine)
      && /(?:^|\s)--session-id(?:\s|=|$)/iu.test(commandLine)
      && windowsCommandReferencesPath(commandLine, taskRoot);
  }) : [];
  if (sessionHosts.length > 1) {
    throw new Error(`检测到 ${sessionHosts.length} 个与 ${taskRoot} 匹配的 WorkBuddy 会话宿主，拒绝清理不唯一进程`);
  }
  const sessionHostPids = new Set(sessionHosts.map((item) => item.pid));
  const seedPids = new Set([...workspaceSeedPids, ...sessionHostPids]);
  const targetPids = new Set(seedPids);
  let changed = true;
  while (changed) {
    changed = false;
    for (const item of normalized) {
      if (!targetPids.has(item.pid) && item.parent_pid && targetPids.has(item.parent_pid)) {
        targetPids.add(item.pid);
        changed = true;
      }
    }
  }
  const rootPids = [...seedPids].filter((pid) => {
    let parentPid = byPid.get(pid)?.parent_pid;
    const visited = new Set();
    while (parentPid && !visited.has(parentPid)) {
      if (seedPids.has(parentPid)) return false;
      visited.add(parentPid);
      parentPid = byPid.get(parentPid)?.parent_pid;
    }
    return true;
  });
  return {
    seed_pids: [...seedPids].sort((left, right) => left - right),
    workspace_seed_pids: [...workspaceSeedPids].sort((left, right) => left - right),
    session_host_pids: [...sessionHostPids].sort((left, right) => left - right),
    root_pids: rootPids.sort((left, right) => left - right),
    targets: normalized
      .filter((item) => targetPids.has(item.pid))
      .map((item) => ({
        pid: item.pid,
        parent_pid: item.parent_pid,
        name: item.name,
        executable_path: item.executable_path,
        matched_by_workspace: workspaceSeedPids.has(item.pid),
        matched_by_session_host: sessionHostPids.has(item.pid),
      }))
      .sort((left, right) => left.pid - right.pid),
  };
}

export async function candidateWorkspaceProcessSnapshot(candidateWorkspace, overrides = {}) {
  const platform = overrides.platform || process.platform;
  if (platform !== "win32") {
    return { supported: false, seed_pids: [], root_pids: [], targets: [] };
  }
  const runCommand = overrides.runCommand || runCapture;
  const result = await runCommand(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", WINDOWS_PROCESS_SNAPSHOT_SCRIPT],
    { capture: true, allowFailure: true },
  );
  if (result.code !== 0) {
    throw new Error(`无法读取 Windows 候选进程表：${String(result.stderr || `退出码 ${result.code}`).trim()}`);
  }
  let processes;
  try {
    processes = parsePowerShellJson(result.stdout);
  } catch (error) {
    throw new Error(`Windows 候选进程表不是有效 JSON：${error instanceof Error ? error.message : String(error)}`);
  }
  return {
    supported: true,
    ...selectCandidateWorkspaceProcesses(processes, candidateWorkspace, {
      excludedPids: overrides.excludedPids || [process.pid],
      taskRoot: overrides.taskRoot || null,
      includeSessionHost: overrides.includeSessionHost === true,
    }),
  };
}

export async function terminateCandidateWorkspaceProcesses(candidateWorkspace, overrides = {}) {
  const platform = overrides.platform || process.platform;
  if (platform !== "win32") {
    return {
      supported: false,
      success: true,
      before: { seed_pids: [], workspace_seed_pids: [], session_host_pids: [], root_pids: [], targets: [] },
      termination_attempts: [],
      after: { seed_pids: [], workspace_seed_pids: [], session_host_pids: [], root_pids: [], targets: [] },
    };
  }
  const runCommand = overrides.runCommand || runCapture;
  const snapshot = async () => candidateWorkspaceProcessSnapshot(candidateWorkspace, {
    ...overrides,
    runCommand,
  });
  const before = await snapshot();
  const terminationAttempts = [];
  const attemptedPids = new Set();
  const terminateRoots = async (processSnapshot, detectedLate = false) => {
    for (const pid of processSnapshot.root_pids) {
      if (attemptedPids.has(pid)) continue;
      attemptedPids.add(pid);
      const result = await runCommand(
        "taskkill.exe",
        ["/PID", String(pid), "/T", "/F"],
        { allowFailure: true, capture: true },
      ).catch((error) => ({ code: null, stdout: "", stderr: error instanceof Error ? error.message : String(error) }));
      terminationAttempts.push({
        pid,
        detected_late: detectedLate,
        exit_code: result.code,
        error: result.code === 0 ? null : String(result.stderr || `退出码 ${result.code}`).trim(),
      });
    }
  };
  await terminateRoots(before);
  let after = await snapshot();
  const wait = overrides.sleep || ((milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds)));
  const now = overrides.now || (() => Date.now());
  const requestedWaitMilliseconds = Math.max(0, overrides.waitMilliseconds ?? 5000);
  const quietMilliseconds = Math.max(0, overrides.quietMilliseconds ?? Math.min(1000, requestedWaitMilliseconds));
  const waitMilliseconds = Math.max(quietMilliseconds, requestedWaitMilliseconds);
  const startedAt = now();
  const deadline = startedAt + waitMilliseconds;
  let quietSince = after.targets.length ? null : now();
  let lateProcessDetected = false;
  while (now() < deadline) {
    if (!after.targets.length && quietSince !== null && now() - quietSince >= quietMilliseconds) break;
    await wait(Math.min(250, Math.max(1, deadline - now()), Math.max(1, quietMilliseconds)));
    after = await snapshot();
    if (after.targets.length) {
      lateProcessDetected ||= quietSince !== null;
      quietSince = null;
      await terminateRoots(after, true);
      after = await snapshot();
    }
    if (!after.targets.length && quietSince === null) quietSince = now();
  }
  const quietObservedMilliseconds = quietSince === null ? 0 : Math.max(0, now() - quietSince);
  return {
    supported: true,
    success: after.targets.length === 0 && quietObservedMilliseconds >= quietMilliseconds,
    quiet_window_milliseconds: quietMilliseconds,
    quiet_observed_milliseconds: quietObservedMilliseconds,
    late_process_detected: lateProcessDetected,
    before: {
      seed_pids: before.seed_pids,
      workspace_seed_pids: before.workspace_seed_pids,
      session_host_pids: before.session_host_pids,
      root_pids: before.root_pids,
      targets: before.targets,
    },
    termination_attempts: terminationAttempts,
    after: {
      seed_pids: after.seed_pids,
      workspace_seed_pids: after.workspace_seed_pids,
      session_host_pids: after.session_host_pids,
      root_pids: after.root_pids,
      targets: after.targets,
    },
  };
}

function registryInstallCandidates(entries, pathApi) {
  const candidates = [];
  for (const entry of entries) {
    if (entry.InstallLocation) candidates.push(String(entry.InstallLocation).trim());
    if (entry.DisplayIcon) candidates.push(String(entry.DisplayIcon).trim().replace(/,\d+$/u, "").replace(/^"|"$/gu, ""));
    const uninstall = String(entry.UninstallString || "").trim();
    const executable = uninstall.startsWith('"')
      ? uninstall.slice(1, uninstall.indexOf('"', 1))
      : uninstall.split(/\s+/u, 1)[0];
    if (executable) candidates.push(pathApi.dirname(executable));
  }
  return candidates;
}

export function defaultWorkBuddyAppPath(platform = process.platform) {
  return platform === "win32" ? "" : MACOS_APP_PATH;
}

export function defaultWorkBuddySessionDb(home = homedir(), pathApi = systemPath, overrides = {}) {
  const platform = overrides.platform || process.platform;
  if (platform === "win32") return pathApi.join(home, ".workbuddy", "workbuddy.db");
  return pathApi.join(home, "Library", "Application Support", "WorkBuddy", "codebuddy-sessions.vscdb");
}

export async function resolveWorkBuddyAppPath(requestedPath = "", overrides = {}) {
  const platform = overrides.platform || process.platform;
  const pathApi = overrides.pathApi || (platform === "win32" ? systemPath.win32 : systemPath);
  const realpathPath = overrides.realpathPath || realpath;
  const statPath = overrides.statPath || stat;
  const runCommand = overrides.runCommand || runCapture;
  const environment = overrides.environment || process.env;

  if (platform !== "win32") {
    const resolved = await realpathPath(systemPath.resolve(requestedPath || MACOS_APP_PATH));
    await access(systemPath.join(resolved, "Contents", "Resources", "app.asar"));
    return resolved;
  }

  if (requestedPath) {
    const explicit = await findWindowsExecutable(requestedPath, { pathApi, realpathPath, statPath });
    if (!explicit) throw new Error(`--app-path 未指向受支持的 WorkBuddy 安装目录或主程序：${requestedPath}`);
    return explicit;
  }

  const candidates = [];
  const registryScript = `
Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -match '^WorkBuddy(?:\\s|$)' } |
  Select-Object InstallLocation,DisplayIcon,UninstallString |
  ConvertTo-Json -Compress
`;
  const registry = await runCommand(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", registryScript],
    { capture: true, allowFailure: true },
  ).catch(() => ({ code: null, stdout: "", stderr: "" }));
  if (registry.code === 0) {
    try {
      candidates.push(...registryInstallCandidates(parsePowerShellJson(registry.stdout), pathApi));
    } catch {
      // A malformed registry response must not suppress deterministic path discovery.
    }
  }
  const localAppData = environment.LOCALAPPDATA || pathApi.join(homedir(), "AppData", "Local");
  candidates.push(pathApi.join(localAppData, "Programs", "WorkBuddy"));

  const seen = new Set();
  for (const candidate of candidates) {
    const key = normalizeWindowsPath(candidate);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const executable = await findWindowsExecutable(candidate, { pathApi, realpathPath, statPath });
    if (executable) return executable;
  }
  throw new Error(
    "未找到 WorkBuddy Windows 主程序；请确认当前用户已安装 WorkBuddy，或显式传入 --app-path <WorkBuddy.exe或安装目录>",
  );
}

export async function validateWorkBuddyAppPath(appPath, platform = process.platform) {
  if (platform === "win32") {
    const name = systemPath.win32.basename(appPath).toLowerCase();
    if (!WINDOWS_EXECUTABLE_NAMES.some((candidate) => candidate.toLowerCase() === name)) {
      throw new Error(`WorkBuddy Windows 主程序名称不受支持：${appPath}`);
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

export async function workBuddyGuiSessionStatus(overrides = {}) {
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
  const frontmost = await runCommand(
    "/usr/bin/osascript",
    ["-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
    { capture: true, allowFailure: true },
  );
  const registry = await runCommand("/usr/sbin/ioreg", ["-n", "Root", "-d1"], { capture: true, allowFailure: true });
  const frontmostApplication = frontmost.code === 0 ? frontmost.stdout.trim() : "unknown";
  const lockMatch = registry.stdout.match(/"IOConsoleLocked"\s*=\s*(Yes|No)/u);
  const screenLocked = lockMatch ? lockMatch[1] === "Yes" : null;
  return {
    frontmost_application: frontmostApplication,
    screen_locked: screenLocked,
    lock_source: lockMatch ? "ioreg.IOConsoleLocked" : "frontmost-application-fallback",
    unlocked: screenLocked === null
      ? frontmost.code === 0 && frontmostApplication.toLowerCase() !== "loginwindow"
      : !screenLocked,
  };
}

export async function workBuddyAppVersion(appPath, overrides = {}) {
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

export async function workBuddyProcessIdentity(appPath, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    const script = `Get-CimInstance Win32_Process | Where-Object { @('WorkBuddy.exe','CodeBuddy.exe') -contains $_.Name } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress`;
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
    if (matches.length > 1) throw new Error(`检测到 ${matches.length} 个与 ${appPath} 匹配的 WorkBuddy 主进程，拒绝选择不唯一 PID`);
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

  const result = await runCommand(
    "/usr/bin/osascript",
    ["-e", `tell application "System Events" to get unix id of first application process whose bundle identifier is "${MACOS_BUNDLE_ID}"`],
    { capture: true, allowFailure: true },
  );
  const pid = Number(result.stdout.trim());
  if (result.code !== 0 || !Number.isInteger(pid) || pid <= 0) return null;
  const command = await runCommand("/bin/ps", ["-p", String(pid), "-o", "command="], { capture: true, allowFailure: true });
  return {
    pid,
    bundle_id: MACOS_BUNDLE_ID,
    command: command.stdout.trim() || null,
    platform: "darwin",
    captured_at: new Date().toISOString(),
  };
}

export async function gracefulQuitWorkBuddy(processInfo, overrides = {}) {
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
    "/usr/bin/osascript",
    ["-e", `tell application id "${MACOS_BUNDLE_ID}" to quit`],
    { allowFailure: true, capture: true },
  );
}

export async function terminateWorkBuddyProcess(processInfo, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  if (platform === "win32") {
    return runCommand("taskkill.exe", ["/PID", String(processInfo.pid), "/T", "/F"], { allowFailure: true, capture: true });
  }
  return runCommand("/bin/kill", ["-TERM", String(processInfo.pid)], { allowFailure: true, capture: true });
}

export async function launchWorkBuddy(appPath, port, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  const launchDetached = overrides.launchDetached || spawnDetached;
  const debugArgs = ["--remote-debugging-address=127.0.0.1", `--remote-debugging-port=${port}`];
  if (platform === "win32") return launchDetached(appPath, debugArgs);
  return runCommand("/usr/bin/open", ["-na", appPath, "--args", ...debugArgs], { allowFailure: true, capture: true });
}

async function loadNodeSqlite() {
  if (!nodeSqlitePromise) nodeSqlitePromise = import("node:sqlite").catch(() => null);
  return nodeSqlitePromise;
}

function normalizeSessionRow(row) {
  return {
    conversationId: row.conversationId || row.id || "",
    cwd: row.cwd || "",
    status: row.status || "",
    createdAt: Number(row.createdAt ?? row.created_at ?? 0) || null,
    updatedAt: Number(row.updatedAt ?? row.updated_at ?? row.lastActivityAt ?? row.last_activity_at ?? 0) || null,
    model: row.model || null,
    permissionMode: row.permissionMode || row.permission_mode || null,
    thoughtLevel: row.thoughtLevel || row.thought_level || null,
  };
}

function queryWithNodeSqlite(sqliteModule, sessionDb) {
  const database = new sqliteModule.DatabaseSync(sessionDb, { readOnly: true });
  try {
    const tables = new Set(database.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((row) => row.name));
    if (tables.has("sessions")) {
      const rows = database.prepare(`
        SELECT id AS conversationId, cwd, status, created_at AS createdAt,
          updated_at AS updatedAt, last_activity_at AS lastActivityAt,
          model, permission_mode AS permissionMode, thought_level AS thoughtLevel
        FROM sessions WHERE deleted_at IS NULL
      `).all();
      return { backend: "node:sqlite", schema: "sessions", sessions: rows.map(normalizeSessionRow) };
    }
    if (tables.has("ItemTable")) {
      const sessions = [];
      for (const row of database.prepare("SELECT CAST(value AS TEXT) AS value FROM ItemTable").all()) {
        try {
          const parsed = JSON.parse(row.value);
          if (parsed && typeof parsed === "object" && parsed.conversationId) sessions.push(normalizeSessionRow(parsed));
        } catch {
          // Ignore unrelated/corrupt rows; exact cwd and conversation matching remains mandatory.
        }
      }
      return { backend: "node:sqlite", schema: "item-table", sessions };
    }
    throw new Error("WorkBuddy 数据库缺少 sessions 或 ItemTable 表");
  } finally {
    database.close();
  }
}

const PYTHON_QUERY_SCRIPT = String.raw`
import json, pathlib, sqlite3, sys
db_path = pathlib.Path(sys.argv[1]).resolve()
database = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
database.row_factory = sqlite3.Row
tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if "sessions" in tables:
    rows = [dict(row) for row in database.execute("""
        SELECT id AS conversationId, cwd, status, created_at AS createdAt,
          updated_at AS updatedAt, last_activity_at AS lastActivityAt,
          model, permission_mode AS permissionMode, thought_level AS thoughtLevel
        FROM sessions WHERE deleted_at IS NULL
    """)]
    result = {"schema": "sessions", "sessions": rows}
elif "ItemTable" in tables:
    sessions = []
    for row in database.execute("SELECT CAST(value AS TEXT) AS value FROM ItemTable"):
        try:
            value = json.loads(row["value"])
            if isinstance(value, dict) and value.get("conversationId"):
                sessions.append(value)
        except Exception:
            pass
    result = {"schema": "item-table", "sessions": sessions}
else:
    raise RuntimeError("WorkBuddy 数据库缺少 sessions 或 ItemTable 表")
database.close()
print(json.dumps(result, ensure_ascii=False))
`;

async function queryWithPython(sessionDb, runCommand) {
  const attempts = [
    { command: "py.exe", args: ["-3", "-c", PYTHON_QUERY_SCRIPT, sessionDb], backend: "python-sqlite3:py-3" },
    { command: "python.exe", args: ["-c", PYTHON_QUERY_SCRIPT, sessionDb], backend: "python-sqlite3:python" },
  ];
  const errors = [];
  for (const attempt of attempts) {
    const result = await runCommand(attempt.command, attempt.args, { capture: true, allowFailure: true })
      .catch((error) => ({ code: null, stdout: "", stderr: error instanceof Error ? error.message : String(error) }));
    if (result.code === 0) {
      const parsed = JSON.parse(result.stdout.trim());
      return {
        backend: attempt.backend,
        schema: parsed.schema,
        sessions: (parsed.sessions || []).map(normalizeSessionRow),
      };
    }
    errors.push(`${attempt.command}: ${String(result.stderr || `退出码 ${result.code}`).trim()}`);
  }
  throw new Error(`Windows 无可用的只读 SQLite 后端：${errors.join("；")}`);
}

async function queryWithMacosCli(sessionDb, runCommand) {
  const result = await runCommand(
    "/usr/bin/sqlite3",
    ["-readonly", "-json", sessionDb, "SELECT CAST(value AS TEXT) AS value FROM ItemTable"],
    { capture: true },
  );
  const rows = result.stdout.trim() ? JSON.parse(result.stdout) : [];
  const sessions = [];
  for (const row of rows) {
    try {
      const value = JSON.parse(row.value);
      if (value && typeof value === "object" && value.conversationId) sessions.push(normalizeSessionRow(value));
    } catch {
      // Ignore unrelated/corrupt rows; exact cwd and conversation matching remains mandatory.
    }
  }
  return { backend: "sqlite3-cli", schema: "item-table", sessions };
}

export async function queryWorkBuddySessionSnapshot(sessionDb, overrides = {}) {
  await access(sessionDb);
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  const sqliteModule = await (overrides.loadNodeSqlite || loadNodeSqlite)();
  if (typeof sqliteModule?.DatabaseSync === "function") return queryWithNodeSqlite(sqliteModule, sessionDb);
  if (platform === "win32") return queryWithPython(sessionDb, runCommand);
  return queryWithMacosCli(sessionDb, runCommand);
}

export async function queryWorkBuddySessions(sessionDb, overrides = {}) {
  return (await queryWorkBuddySessionSnapshot(sessionDb, overrides)).sessions;
}

export async function workBuddySqliteBackendStatus(overrides = {}) {
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

export function workBuddySessionDbExists(sessionDb) {
  return existsSync(sessionDb);
}
