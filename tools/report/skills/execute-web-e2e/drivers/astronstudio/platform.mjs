import { spawn } from "node:child_process";
import { access, realpath, stat } from "node:fs/promises";
import { homedir } from "node:os";
import * as systemPath from "node:path";

export const MACOS_APP_PATH = "/Applications/AStudio.app";
export const WINDOWS_EXECUTABLE_NAMES = Object.freeze([
  "AStudio.exe",
  "AstronStudio.exe",
  "Acode.exe",
]);
export const WINDOWS_REGISTRY_KEYS = Object.freeze([
  "HKCU\\Software\\AStudio",
  "HKCU\\Software\\AstronStudio",
  "HKCU\\Software\\Acode",
]);

function runCapture(command, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const { allowFailure = false, capture: _capture = true, ...spawnOptions } = options;
    const child = spawn(command, args, {
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

function parseRegistryInstallLocation(stdout) {
  const match = String(stdout || "").match(/^\s*InstallLocation\s+REG_\w+\s+(.+?)\s*$/imu);
  return match?.[1]?.trim() || null;
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

export function defaultAstronAppPath(platform = process.platform) {
  return platform === "win32" ? "" : MACOS_APP_PATH;
}

export function defaultAstronSessionDb(home = homedir(), pathApi = systemPath) {
  return pathApi.join(home, ".acode", "acode", "userdata", "state.sqlite");
}

export async function resolveAstronAppPath(requestedPath = "", overrides = {}) {
  const platform = overrides.platform || process.platform;
  const pathApi = overrides.pathApi || (platform === "win32" ? systemPath.win32 : systemPath);
  const realpathPath = overrides.realpathPath || realpath;
  const statPath = overrides.statPath || stat;
  const runCommand = overrides.runCommand || runCapture;
  const environment = overrides.environment || process.env;

  if (platform !== "win32") {
    const candidate = requestedPath || MACOS_APP_PATH;
    const resolved = await realpathPath(systemPath.resolve(candidate));
    await access(systemPath.join(resolved, "Contents", "Resources", "app.asar"));
    return resolved;
  }

  if (requestedPath) {
    const explicit = await findWindowsExecutable(requestedPath, { pathApi, realpathPath, statPath });
    if (!explicit) {
      throw new Error(`--app-path 未指向受支持的 AstronStudio 安装目录或主程序：${requestedPath}`);
    }
    return explicit;
  }

  const candidates = [];
  for (const registryKey of WINDOWS_REGISTRY_KEYS) {
    const result = await runCommand("reg.exe", ["query", registryKey, "/v", "InstallLocation"], {
      capture: true,
      allowFailure: true,
    }).catch(() => ({ code: null, stdout: "", stderr: "" }));
    if (result.code === 0) {
      const installLocation = parseRegistryInstallLocation(result.stdout);
      if (installLocation) candidates.push(installLocation);
    }
  }
  const localAppData = environment.LOCALAPPDATA || "";
  if (localAppData) {
    for (const directoryName of ["AStudio", "AstronStudio", "Acode"]) {
      candidates.push(pathApi.join(localAppData, "Programs", directoryName));
    }
  }

  const seen = new Set();
  for (const candidate of candidates) {
    const key = normalizeWindowsPath(candidate);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const executable = await findWindowsExecutable(candidate, { pathApi, realpathPath, statPath });
    if (executable) return executable;
  }
  throw new Error(
    "未找到 AstronStudio Windows 主程序；请确认 HKCU\\Software\\AStudio\\InstallLocation 可用，或显式传入 --app-path <AStudio.exe或安装目录>",
  );
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

  const frontmost = await runCommand(
    "/usr/bin/osascript",
    ["-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
    { capture: true, allowFailure: true },
  );
  const registry = await runCommand(
    "/usr/sbin/ioreg",
    ["-n", "Root", "-d1"],
    { capture: true, allowFailure: true },
  );
  const frontmostApplication = frontmost.code === 0 ? frontmost.stdout.trim() : "unknown";
  const lockMatch = registry.stdout.match(/"IOConsoleLocked"\s*=\s*(Yes|No)/);
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
    const script = `Get-CimInstance Win32_Process | Where-Object { @('AStudio.exe','AstronStudio.exe','Acode.exe') -contains $_.Name } | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress`;
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
    const matches = processes.filter((item) => {
      const executablePath = normalizeWindowsPath(item.ExecutablePath);
      const exactExecutable = executablePath && executablePath === expectedPath;
      const commandMatches = normalizeWindowsPath(windowsCommandExecutable(item.CommandLine)) === expectedPath;
      return (exactExecutable || commandMatches) && !/(?:^|\s)--type=/iu.test(String(item.CommandLine || ""));
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

  const result = await runCommand(
    "/usr/bin/osascript",
    ["-e", 'tell application "System Events" to get unix id of first application process whose bundle identifier is "cn.xfyun.acode"'],
    { capture: true, allowFailure: true },
  );
  const pid = Number(result.stdout.trim());
  if (result.code !== 0 || !Number.isInteger(pid) || pid <= 0) return null;
  const command = await runCommand("/bin/ps", ["-p", String(pid), "-o", "command="], {
    capture: true,
    allowFailure: true,
  });
  return {
    pid,
    bundle_id: "cn.xfyun.acode",
    command: command.stdout.trim() || null,
    platform: "darwin",
    captured_at: new Date().toISOString(),
  };
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
    "/usr/bin/osascript",
    ["-e", 'tell application id "cn.xfyun.acode" to quit'],
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
    ["-TERM", String(processInfo.pid)],
    { allowFailure: true, capture: true },
  );
}

export async function launchAstron(appPath, port, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const runCommand = overrides.runCommand || runCapture;
  const launchDetached = overrides.launchDetached || spawnDetached;
  const debugArgs = ["--remote-debugging-address=127.0.0.1", `--remote-debugging-port=${port}`];
  if (platform === "win32") return launchDetached(appPath, debugArgs);
  return runCommand(
    "/usr/bin/open",
    ["-na", appPath, "--args", ...debugArgs],
    { allowFailure: true, capture: true },
  );
}
