import { access, readdir, realpath, stat } from "node:fs/promises";
import { homedir } from "node:os";
import * as systemPath from "node:path";
import { promisify } from "node:util";
import { execFile } from "node:child_process";

export const COMPONENT_NAME = "desktop-app-discovery";
export const COMPONENT_VERSION = "1.1.0";
export const DISCOVERY_SCHEMA = "wildclawbench.desktop-app-discovery/v1";

const execFileAsync = promisify(execFile);
const TIERS = Object.freeze([
  "running_process",
  "system_registration",
  "standard_directory",
]);

export class DesktopAppDiscoveryError extends Error {
  constructor(code, message, candidatesChecked = []) {
    super(message);
    this.name = "DesktopAppDiscoveryError";
    this.code = code;
    this.candidatesChecked = candidatesChecked;
  }
}

async function defaultRunCommand(command, args, options = {}) {
  try {
    const result = await execFileAsync(command, args, {
      encoding: "utf8",
      windowsHide: true,
      maxBuffer: 4 * 1024 * 1024,
      ...options,
    });
    return { code: 0, stdout: result.stdout || "", stderr: result.stderr || "" };
  } catch (error) {
    if (options.allowFailure) {
      return {
        code: Number.isInteger(error?.code) ? error.code : null,
        stdout: String(error?.stdout || ""),
        stderr: String(error?.stderr || error?.message || ""),
      };
    }
    throw error;
  }
}

function cleanCandidate(value) {
  return String(value || "")
    .trim()
    .replace(/^"|"$/gu, "")
    .replace(/,\d+$/u, "")
    .trim();
}

function normalizeWindowsPath(value) {
  return cleanCandidate(value)
    .replaceAll("/", "\\")
    .replace(/\\+$/u, "")
    .toLowerCase();
}

export function sameDesktopAppPath(left, right, platform = process.platform) {
  if (platform === "win32") {
    return Boolean(normalizeWindowsPath(left))
      && normalizeWindowsPath(left) === normalizeWindowsPath(right);
  }
  return Boolean(cleanCandidate(left)) && cleanCandidate(left) === cleanCandidate(right);
}

function parseJsonRows(stdout) {
  const text = String(stdout || "").trim();
  if (!text || text === "null") return [];
  const value = JSON.parse(text);
  return Array.isArray(value) ? value : [value];
}

function compareVersionNames(left, right) {
  const leftParts = String(left).match(/\d+/gu)?.map(Number) || [];
  const rightParts = String(right).match(/\d+/gu)?.map(Number) || [];
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const difference = (rightParts[index] || 0) - (leftParts[index] || 0);
    if (difference !== 0) return difference;
  }
  return String(right).localeCompare(String(left));
}

async function isFile(path, statPath) {
  try {
    return (await statPath(path)).isFile();
  } catch {
    return false;
  }
}

async function isDirectory(path, statPath) {
  try {
    return (await statPath(path)).isDirectory();
  } catch {
    return false;
  }
}

function macBundleRoot(value) {
  const normalized = cleanCandidate(value);
  const match = normalized.match(/^(.*?\.app)(?:\/Contents\/MacOS\/[^/]+)?$/u);
  return match?.[1] || normalized;
}

async function readMacPlistValue(appPath, key, runCommand, environment) {
  const plist = systemPath.join(appPath, "Contents", "Info.plist");
  const plistBuddy = environment.WCB_APP_DISCOVERY_PLISTBUDDY_BIN || "/usr/libexec/PlistBuddy";
  const first = await runCommand(
    plistBuddy,
    ["-c", `Print :${key}`, plist],
    { capture: true, allowFailure: true },
  ).catch(() => ({ code: null, stdout: "" }));
  if (first.code === 0 && String(first.stdout || "").trim()) return String(first.stdout).trim();
  const plutil = environment.WCB_MACOS_PLUTIL_BIN
    || environment.WCB_APP_DISCOVERY_PLUTIL_BIN
    || "/usr/bin/plutil";
  const second = await runCommand(
    plutil,
    ["-extract", key, "raw", "-o", "-", plist],
    { capture: true, allowFailure: true },
  ).catch(() => ({ code: null, stdout: "" }));
  return second.code === 0 ? String(second.stdout || "").trim() || null : null;
}

async function verifyMacCandidate(rawCandidate, profile, dependencies) {
  const { realpathPath, statPath, runCommand, environment } = dependencies;
  const configuration = profile.macos;
  const bundleCandidate = macBundleRoot(rawCandidate);
  if (!(await isDirectory(bundleCandidate, statPath))) {
    throw new Error("application bundle does not exist");
  }
  const canonical = await realpathPath(bundleCandidate);
  for (const relativePath of configuration.requiredRelativePaths || []) {
    if (!(await isFile(systemPath.join(canonical, relativePath), statPath))) {
      throw new Error(`required application file is missing: ${relativePath}`);
    }
  }
  const bundleId = await readMacPlistValue(canonical, "CFBundleIdentifier", runCommand, environment);
  if (!bundleId || !(configuration.bundleIds || []).includes(bundleId)) {
    throw new Error(`bundle identifier mismatch: ${bundleId || "unavailable"}`);
  }
  let executablePath = null;
  for (const name of configuration.executableNames || []) {
    const candidate = systemPath.join(canonical, "Contents", "MacOS", name);
    if (await isFile(candidate, statPath)) {
      executablePath = await realpathPath(candidate);
      break;
    }
  }
  if (!executablePath) {
    const observedExecutable = cleanCandidate(rawCandidate);
    if (observedExecutable.includes(".app/Contents/MacOS/") && await isFile(observedExecutable, statPath)) {
      executablePath = await realpathPath(observedExecutable);
    }
  }
  if (!executablePath) {
    throw new Error("supported application executable was not found");
  }
  const version = await readMacPlistValue(canonical, "CFBundleShortVersionString", runCommand, environment);
  return {
    path: canonical,
    executable_path: executablePath,
    bundle_id: bundleId,
    version,
    identity_verified: true,
  };
}

async function findWindowsExecutable(rawCandidate, profile, dependencies) {
  const { pathApi, realpathPath, statPath, readDirectory } = dependencies;
  const configuration = profile.windows;
  const candidate = cleanCandidate(rawCandidate);
  if (!candidate) return null;
  if (await isFile(candidate, statPath)) {
    const supported = configuration.executableNames.some(
      (name) => name.toLowerCase() === pathApi.basename(candidate).toLowerCase(),
    );
    return supported ? realpathPath(candidate) : null;
  }
  if (!(await isDirectory(candidate, statPath))) return null;
  for (const name of configuration.executableNames) {
    const executable = pathApi.join(candidate, name);
    if (await isFile(executable, statPath)) return realpathPath(executable);
  }
  if (!configuration.allowVersionSubdirectories) return null;
  let children = [];
  try {
    children = (await readDirectory(candidate, { withFileTypes: true }))
      .filter((item) => item.isDirectory())
      .map((item) => item.name)
      .sort(compareVersionNames);
  } catch {
    return null;
  }
  for (const child of children) {
    for (const name of configuration.executableNames) {
      const executable = pathApi.join(candidate, child, name);
      if (await isFile(executable, statPath)) return realpathPath(executable);
    }
  }
  return null;
}

async function verifyWindowsCandidate(rawCandidate, profile, dependencies) {
  const executable = await findWindowsExecutable(rawCandidate, profile, dependencies);
  if (!executable) throw new Error("supported executable was not found");
  const { pathApi, statPath, runCommand } = dependencies;
  for (const relativePath of profile.windows.requiredRelativePaths || []) {
    const required = pathApi.join(pathApi.dirname(executable), ...relativePath.split("/"));
    if (!(await isFile(required, statPath))) {
      throw new Error(`required application file is missing: ${relativePath}`);
    }
  }
  const script = [
    "$ErrorActionPreference = 'Stop'",
    "$AppPath = $args[0]",
    "$Version = (Get-Item -LiteralPath $AppPath).VersionInfo.ProductVersion",
    "if ($Version) { [Console]::Out.Write($Version) }",
  ].join("; ");
  const versionResult = await runCommand(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", script, executable],
    { capture: true, allowFailure: true },
  ).catch(() => ({ code: null, stdout: "" }));
  return {
    path: executable,
    executable_path: executable,
    bundle_id: null,
    version: versionResult.code === 0 ? String(versionResult.stdout || "").trim() || null : null,
    identity_verified: true,
  };
}

async function verifyCandidate(rawCandidate, profile, platform, dependencies) {
  if (platform === "win32") return verifyWindowsCandidate(rawCandidate, profile, dependencies);
  if (platform === "darwin") return verifyMacCandidate(rawCandidate, profile, dependencies);
  throw new DesktopAppDiscoveryError(
    "UNSUPPORTED_PLATFORM",
    `desktop application discovery does not support platform: ${platform}`,
  );
}

function expandPathTemplate(value, context, pathApi) {
  const expanded = String(value || "")
    .replaceAll("{home}", context.home || "")
    .replaceAll("{localAppData}", context.localAppData || "")
    .replaceAll("{programFiles}", context.programFiles || "")
    .replaceAll("{programFilesX86}", context.programFilesX86 || "");
  if (!expanded || /\{[^}]+\}/u.test(expanded)) return null;
  return pathApi.normalize(expanded);
}

async function macRunningCandidates(profile, dependencies) {
  const rows = [];
  const result = await dependencies.runCommand(
    dependencies.environment.WCB_MACOS_PS_BIN || "/bin/ps",
    ["-axo", "pid=,comm="],
    { capture: true, allowFailure: true },
  ).catch(() => ({ code: null, stdout: "" }));
  if (result.code !== 0) return rows;
  const executableNames = new Set(profile.macos.executableNames || []);
  for (const line of String(result.stdout || "").split(/\r?\n/u)) {
    const match = line.match(/^\s*(\d+)\s+(.+?)\s*$/u);
    if (!match) continue;
    const pid = Number(match[1]);
    const executable = match[2];
    if (!Number.isInteger(pid) || pid <= 0) continue;
    if (!executable.includes(".app/Contents/MacOS/")) continue;
    if (!executableNames.has(systemPath.basename(executable))) continue;
    rows.push({ path: executable, source: "running_process", pid });
  }
  return rows;
}

async function macRegistrationCandidates(profile, dependencies) {
  const rows = [];
  for (const bundleId of profile.macos.bundleIds || []) {
    const spotlight = await dependencies.runCommand(
      dependencies.environment.WCB_APP_DISCOVERY_MDFIND_BIN || "/usr/bin/mdfind",
      [`kMDItemCFBundleIdentifier == '${bundleId.replaceAll("'", "\\'")}'`],
      { capture: true, allowFailure: true },
    ).catch(() => ({ code: null, stdout: "" }));
    if (spotlight.code === 0) {
      for (const path of String(spotlight.stdout || "").split(/\r?\n/u).map((item) => item.trim()).filter(Boolean)) {
        rows.push({ path, source: "macos_spotlight" });
      }
    }
  }
  return rows;
}

function parseMacProcessRows(stdout) {
  const rows = [];
  for (const line of String(stdout || "").split(/\r?\n/u)) {
    const match = line.match(/^\s*(\d+)\s+(\d+)\s+(.+?)\s*$/u);
    if (!match) continue;
    const pid = Number(match[1]);
    const ppid = Number(match[2]);
    if (!Number.isInteger(pid) || pid <= 0 || !Number.isInteger(ppid) || ppid < 0) continue;
    rows.push({ pid, ppid, executable_path: match[3] });
  }
  return rows;
}

export async function inspectMacDesktopAppProcess({ profile, appPath } = {}, overrides = {}) {
  if (!profile?.id || !appPath) throw new TypeError("profile and appPath are required");
  const runCommand = overrides.runCommand || defaultRunCommand;
  const statPath = overrides.statPath || stat;
  const realpathPath = overrides.realpathPath || realpath;
  const canonicalAppPath = await realpathPath(macBundleRoot(appPath));
  const expectedExecutables = new Set();
  for (const executableName of profile.macos?.executableNames || []) {
    const executablePath = systemPath.join(canonicalAppPath, "Contents", "MacOS", executableName);
    if (await isFile(executablePath, statPath)) {
      expectedExecutables.add(await realpathPath(executablePath));
    }
  }
  if (expectedExecutables.size === 0) return null;

  const result = await runCommand(
    overrides.psBin || "/bin/ps",
    ["-axo", "pid=,ppid=,comm="],
    { capture: true, allowFailure: true },
  ).catch(() => ({ code: null, stdout: "" }));
  if (result.code !== 0) return null;
  const matching = [];
  for (const item of parseMacProcessRows(result.stdout)) {
    let executablePath = item.executable_path;
    try {
      executablePath = await realpathPath(executablePath);
    } catch {
      continue;
    }
    if (expectedExecutables.has(executablePath)) matching.push({ ...item, executable_path: executablePath });
  }
  const matchingPids = new Set(matching.map((item) => item.pid));
  const roots = matching.filter((item) => !matchingPids.has(item.ppid));
  if (roots.length > 1) {
    throw new DesktopAppDiscoveryError(
      "AMBIGUOUS_RUNNING_PROCESS",
      `multiple ${profile.displayName} root processes match ${canonicalAppPath}`,
      roots.map((item) => ({
        path: item.executable_path,
        source: "running_process",
        status: "valid",
        resolved_path: canonicalAppPath,
        pid: item.pid,
        ppid: item.ppid,
        error: null,
      })),
    );
  }
  const processInfo = roots[0];
  if (!processInfo) return null;
  const [commandResult, startedResult] = await Promise.all([
    runCommand(
      overrides.psBin || "/bin/ps",
      ["-p", String(processInfo.pid), "-o", "command="],
      { capture: true, allowFailure: true },
    ).catch(() => ({ code: null, stdout: "" })),
    runCommand(
      overrides.psBin || "/bin/ps",
      ["-p", String(processInfo.pid), "-o", "lstart="],
      { capture: true, allowFailure: true },
    ).catch(() => ({ code: null, stdout: "" })),
  ]);
  const startedAtEpoch = startedResult.code === 0
    ? Date.parse(String(startedResult.stdout || "").trim())
    : Number.NaN;
  return {
    pid: processInfo.pid,
    ppid: processInfo.ppid,
    executable_path: processInfo.executable_path,
    bundle_id: profile.macos?.bundleIds?.[0] || null,
    command: commandResult.code === 0 ? String(commandResult.stdout || "").trim() || null : null,
    started_at: Number.isFinite(startedAtEpoch) ? new Date(startedAtEpoch).toISOString() : null,
    platform: "darwin",
    captured_at: new Date().toISOString(),
  };
}

function windowsPowerShellLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

async function windowsRunningCandidates(profile, dependencies, endpoint) {
  const names = profile.windows.executableNames.map(windowsPowerShellLiteral).join(",");
  const port = endpoint ? new URL(endpoint).port : "";
  const portClause = port
    ? ` -and $_.CommandLine -match '(?:--remote-debugging-port=${port}|--remote-debugging-port\\s+${port})(?:\\s|$)'`
    : "";
  const script = `Get-CimInstance Win32_Process | Where-Object { @(${names}) -contains $_.Name${portClause} } | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress`;
  const result = await dependencies.runCommand(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", script],
    { capture: true, allowFailure: true },
  ).catch(() => ({ code: null, stdout: "" }));
  if (result.code !== 0) return [];
  try {
    return parseJsonRows(result.stdout)
      .filter((item) => item.ExecutablePath)
      .map((item) => ({
        path: String(item.ExecutablePath),
        source: "running_process",
        pid: Number(item.ProcessId) || null,
      }));
  } catch {
    return [];
  }
}

function parseRegistryValue(stdout, valueName = null) {
  const escaped = valueName
    ? valueName.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")
    : "\\(Default\\)";
  const match = String(stdout || "").match(new RegExp(`^\\s*${escaped}\\s+REG_\\w+\\s+(.+?)\\s*$`, "imu"));
  return match?.[1]?.trim() || null;
}

function uninstallCandidates(entries, pattern, pathApi) {
  const rows = [];
  for (const entry of entries) {
    if (!pattern.test(String(entry.DisplayName || "").trim())) continue;
    if (entry.InstallLocation) rows.push(String(entry.InstallLocation).trim());
    if (entry.DisplayIcon) rows.push(cleanCandidate(entry.DisplayIcon));
    const uninstall = String(entry.UninstallString || "").trim();
    const executable = uninstall.startsWith('"')
      ? uninstall.slice(1, uninstall.indexOf('"', 1))
      : uninstall.split(/\s+/u, 1)[0];
    if (executable) rows.push(pathApi.dirname(executable));
  }
  return rows;
}

async function windowsRegistrationCandidates(profile, dependencies) {
  const rows = [];
  for (const item of profile.windows.productRegistryKeys || []) {
    const result = await dependencies.runCommand(
      "reg.exe",
      ["query", item.key, "/v", item.value],
      { capture: true, allowFailure: true },
    ).catch(() => ({ code: null, stdout: "" }));
    const value = result.code === 0 ? parseRegistryValue(result.stdout, item.value) : null;
    if (value) rows.push({ path: value, source: "windows_product_registry", registry_key: item.key });
  }
  for (const executableName of profile.windows.executableNames || []) {
    for (const hive of ["HKCU", "HKLM"]) {
      for (const view of ["Software", "Software\\WOW6432Node"]) {
        const key = `${hive}\\${view}\\Microsoft\\Windows\\CurrentVersion\\App Paths\\${executableName}`;
        const result = await dependencies.runCommand(
          "reg.exe",
          ["query", key, "/ve"],
          { capture: true, allowFailure: true },
        ).catch(() => ({ code: null, stdout: "" }));
        const value = result.code === 0 ? parseRegistryValue(result.stdout) : null;
        if (value) rows.push({ path: value, source: "windows_app_paths", registry_key: key });
      }
    }
  }
  if (profile.windows.uninstallDisplayNamePattern) {
    const script = String.raw`
$roots = @(
  'Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'Registry::HKEY_CURRENT_USER\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'Registry::HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'Registry::HKEY_LOCAL_MACHINE\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$roots | ForEach-Object { Get-ItemProperty -Path $_ -ErrorAction SilentlyContinue } |
  Select-Object DisplayName,InstallLocation,DisplayIcon,UninstallString |
  ConvertTo-Json -Compress
`;
    const result = await dependencies.runCommand(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      { capture: true, allowFailure: true },
    ).catch(() => ({ code: null, stdout: "" }));
    if (result.code === 0) {
      try {
        const pattern = new RegExp(profile.windows.uninstallDisplayNamePattern, "iu");
        for (const path of uninstallCandidates(parseJsonRows(result.stdout), pattern, dependencies.pathApi)) {
          rows.push({ path, source: "windows_uninstall_registry" });
        }
      } catch {
        // Malformed registry JSON is audit noise, not permission to guess a path.
      }
    }
  }
  return rows;
}

async function candidatesForTier(tier, profile, platform, context, dependencies, overrides) {
  const injected = overrides.candidatesByTier?.[tier];
  if (Array.isArray(injected)) return injected.map((item) => (
    typeof item === "string" ? { path: item, source: tier } : item
  ));
  if (tier === "running_process") {
    return platform === "win32"
      ? windowsRunningCandidates(profile, dependencies, context.endpoint)
      : macRunningCandidates(profile, dependencies);
  }
  if (tier === "system_registration") {
    return platform === "win32"
      ? windowsRegistrationCandidates(profile, dependencies)
      : macRegistrationCandidates(profile, dependencies);
  }
  const configuration = platform === "win32" ? profile.windows : profile.macos;
  return (configuration.standardPaths || [])
    .map((path) => expandPathTemplate(path, context, dependencies.pathApi))
    .filter(Boolean)
    .map((path) => ({ path, source: "standard_directory" }));
}

function discoveryContext(platform, environment, home, endpoint) {
  const pathApi = platform === "win32" ? systemPath.win32 : systemPath;
  return {
    endpoint,
    home,
    localAppData: environment.LOCALAPPDATA || pathApi.join(home, "AppData", "Local"),
    programFiles: environment.ProgramFiles || environment.PROGRAMFILES || "",
    programFilesX86: environment["ProgramFiles(x86)"] || environment.PROGRAMFILES_X86 || "",
  };
}

function candidateKey(value, platform) {
  return platform === "win32" ? normalizeWindowsPath(value) : String(value);
}

async function evaluateCandidates(candidates, profile, platform, dependencies, audit) {
  const valid = [];
  const canonicalSeen = new Set();
  const inputSeen = new Set();
  for (const item of candidates) {
    const rawPath = cleanCandidate(item?.path);
    const inputKey = candidateKey(rawPath, platform);
    if (!rawPath || inputSeen.has(inputKey)) continue;
    inputSeen.add(inputKey);
    const row = {
      path: rawPath,
      source: item?.source || "unknown",
      status: "invalid",
      resolved_path: null,
      error: null,
    };
    audit.push(row);
    try {
      const verified = await verifyCandidate(rawPath, profile, platform, dependencies);
      row.status = "valid";
      row.resolved_path = verified.path;
      const canonicalKey = candidateKey(verified.path, platform);
      if (!canonicalSeen.has(canonicalKey)) {
        canonicalSeen.add(canonicalKey);
        valid.push({ ...verified, source: row.source });
      }
    } catch (error) {
      row.error = error instanceof Error ? error.message : String(error);
    }
  }
  return valid;
}

export async function verifyDesktopAppPath({ profile, path, platform = process.platform }, overrides = {}) {
  if (!profile?.id || !path) throw new TypeError("profile and path are required");
  const pathApi = overrides.pathApi || (platform === "win32" ? systemPath.win32 : systemPath);
  const dependencies = {
    pathApi,
    realpathPath: overrides.realpathPath || realpath,
    statPath: overrides.statPath || stat,
    readDirectory: overrides.readDirectory || readdir,
    runCommand: overrides.runCommand || defaultRunCommand,
    environment: overrides.environment || process.env,
  };
  return verifyCandidate(path, profile, platform, dependencies);
}

export async function discoverDesktopApp({
  profile,
  requestedPath = "",
  platform = process.platform,
  endpoint = null,
  environment = process.env,
  home = homedir(),
} = {}, overrides = {}) {
  if (!profile?.id || !profile?.displayName) throw new TypeError("a desktop application profile is required");
  if (!new Set(["darwin", "win32"]).has(platform)) {
    throw new DesktopAppDiscoveryError(
      "UNSUPPORTED_PLATFORM",
      `${profile.displayName} discovery does not support platform: ${platform}`,
    );
  }
  const platformProfile = platform === "win32" ? profile.windows : profile.macos;
  if (!platformProfile) {
    throw new DesktopAppDiscoveryError(
      "PROFILE_PLATFORM_UNSUPPORTED",
      `${profile.displayName} profile does not support platform: ${platform}`,
    );
  }
  const pathApi = overrides.pathApi || (platform === "win32" ? systemPath.win32 : systemPath);
  const dependencies = {
    pathApi,
    realpathPath: overrides.realpathPath || realpath,
    statPath: overrides.statPath || stat,
    readDirectory: overrides.readDirectory || readdir,
    runCommand: overrides.runCommand || defaultRunCommand,
    environment,
  };
  const context = discoveryContext(platform, environment, home, endpoint);
  const audit = [];
  const buildResult = (verified) => ({
    schema_version: DISCOVERY_SCHEMA,
    component_version: COMPONENT_VERSION,
    profile_id: profile.id,
    platform,
    path: verified.path,
    executable_path: verified.executable_path,
    source: verified.source,
    identity_verified: verified.identity_verified === true,
    bundle_id: verified.bundle_id || null,
    version: verified.version || null,
    candidates_checked: audit,
    discovered_at: new Date().toISOString(),
  });

  if (requestedPath) {
    const valid = await evaluateCandidates(
      [{ path: requestedPath, source: "explicit" }],
      profile,
      platform,
      dependencies,
      audit,
    );
    if (valid.length !== 1) {
      throw new DesktopAppDiscoveryError(
        "EXPLICIT_PATH_INVALID",
        `--app-path is not a verified ${profile.displayName} installation: ${requestedPath}`,
        audit,
      );
    }
    return buildResult(valid[0]);
  }

  for (const tier of TIERS) {
    const candidates = await candidatesForTier(
      tier,
      profile,
      platform,
      context,
      dependencies,
      overrides,
    );
    const valid = await evaluateCandidates(candidates, profile, platform, dependencies, audit);
    if (valid.length > 1) {
      throw new DesktopAppDiscoveryError(
        "AMBIGUOUS_INSTALLATION",
        `${profile.displayName} discovery found ${valid.length} verified installations at ${tier}; pass --app-path explicitly`,
        audit,
      );
    }
    if (valid.length === 1) return buildResult(valid[0]);
  }
  throw new DesktopAppDiscoveryError(
    "APPLICATION_NOT_FOUND",
    `no verified ${profile.displayName} installation was found; pass --app-path explicitly`,
    audit,
  );
}
