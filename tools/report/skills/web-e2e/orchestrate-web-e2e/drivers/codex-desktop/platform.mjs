import * as systemPath from "node:path";
import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";
import { discoverDesktopApp } from "../../vendor/e2e-shared/desktop-app-discovery/index.mjs";
import { CODEX_DESKTOP_APP_PROFILE } from "../../vendor/e2e-shared/desktop-app-discovery/profiles.mjs";

export const MACOS_CODEX_APP_PATH = "/Applications/ChatGPT.app";

export function defaultCodexAppPath(platform = process.platform) {
  return platform === "win32" ? "" : MACOS_CODEX_APP_PATH;
}

export async function resolveCodexAppPath(requestedPath, endpoint, overrides = {}) {
  const platform = overrides.platform || process.platform;
  const discovery = await discoverDesktopApp({
    profile: CODEX_DESKTOP_APP_PROFILE,
    requestedPath: requestedPath || "",
    endpoint,
    platform,
    environment: overrides.environment || process.env,
  }, overrides);
  return discovery.path;
}

export async function discoverCodexApp(requestedPath, endpoint, overrides = {}) {
  const platform = overrides.platform || process.platform;
  return discoverDesktopApp({
    profile: CODEX_DESKTOP_APP_PROFILE,
    requestedPath: requestedPath || "",
    endpoint,
    platform,
    environment: overrides.environment || process.env,
  }, overrides);
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
