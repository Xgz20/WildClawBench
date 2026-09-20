#!/usr/bin/env node

import { access, mkdir, open, readdir, realpath, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  discoverDesktopApp,
  inspectMacDesktopAppProcess,
} from "../../vendor/e2e-shared/desktop-app-discovery/index.mjs";
import {
  WORKBUDDY_APP_PROFILE,
} from "../../vendor/e2e-shared/desktop-app-discovery/profiles.mjs";
import {
  runCapture,
} from "../../vendor/e2e-shared/desktop-runtime/process.mjs";

export const WORKBUDDY_MACOS_APP_PROFILE = Object.freeze({
  ...WORKBUDDY_APP_PROFILE,
  id: "workbuddy-macos",
});

export const WORKBUDDY_MACOS_INSTALLATION_VARIANTS = Object.freeze([
  Object.freeze({
    id: "workbuddy-macos-5.5.3-electron",
    client_versions: Object.freeze(["5.5.3"]),
    executable_name: "Electron",
  }),
  Object.freeze({
    id: "workbuddy-macos-5.5.6-electron",
    client_versions: Object.freeze(["5.5.6"]),
    executable_name: "Electron",
  }),
]);

export const WORKBUDDY_PROBE_SCHEMA = "wildclawbench.general-e2e-workbuddy-macos-probe/v1";
export const WORKBUDDY_PROBE_VERSION = "0.1.0";
export const DEFAULT_SESSION_DB = join(
  homedir(),
  "Library",
  "Application Support",
  "WorkBuddy",
  "codebuddy-sessions.vscdb",
);
export const DEFAULT_EXTENSION_DATA_ROOT = join(
  homedir(),
  "Library",
  "Application Support",
  "WorkBuddyExtension",
  "Data",
);
export const DEFAULT_EXTENSION_LOG_ROOT = join(
  homedir(),
  "Library",
  "Application Support",
  "WorkBuddyExtension",
  "Logs",
  "VSCode",
);
export const DEFAULT_APP_LOG_ROOT = join(
  homedir(),
  "Library",
  "Application Support",
  "WorkBuddy",
  "logs",
);

function usage() {
  return `WorkBuddy General E2E macOS 只读探针

用法：
  node drivers/workbuddy/probe.mjs [选项]

选项：
  --app-path <WorkBuddy.app>      可选；显式路径优先，否则按公共 Profile 发现
  --session-db <vscdb>           默认 WorkBuddy codebuddy-sessions.vscdb
  --extension-data-root <目录>   默认 WorkBuddyExtension/Data
  --extension-log-root <目录>    默认 WorkBuddyExtension/Logs/VSCode
  --app-log-root <目录>          默认 WorkBuddy/logs
  --endpoint <http://127.0.0.1:端口> 可选；仅在已运行进程匹配时读取 CDP 元数据
  --output <probe.json>          可选；新建结果，拒绝覆盖
  --timeout-ms <毫秒>            CDP 读取超时，默认 2000
  -h, --help                     显示帮助

探针不会启动、退出或重启 WorkBuddy，不选择 Workspace/模型/权限，不打开 UI，
也不发送 Prompt。它只读取安装、进程、SQLite 会话索引和历史/日志布局元数据。`;
}

function positiveInteger(value, field) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`${field} 必须是正整数`);
  return parsed;
}

function validateEndpoint(value) {
  let endpoint;
  try {
    endpoint = new URL(value);
  } catch {
    throw new Error(`CDP endpoint 无效：${value}`);
  }
  if (
    endpoint.protocol !== "http:"
    || !new Set(["127.0.0.1", "localhost", "[::1]"]).has(endpoint.hostname)
    || endpoint.username
    || endpoint.password
    || endpoint.pathname !== "/"
    || endpoint.search
    || endpoint.hash
    || !endpoint.port
  ) {
    throw new Error("CDP endpoint 必须是带显式端口的 loopback http 根地址");
  }
  return endpoint.origin;
}

export function parseArgs(argv) {
  const values = {
    appPath: "",
    sessionDb: DEFAULT_SESSION_DB,
    extensionDataRoot: DEFAULT_EXTENSION_DATA_ROOT,
    extensionLogRoot: DEFAULT_EXTENSION_LOG_ROOT,
    appLogRoot: DEFAULT_APP_LOG_ROOT,
    endpoint: "",
    output: "",
    timeoutMs: 2000,
    help: false,
  };
  const valued = new Map([
    ["--app-path", "appPath"],
    ["--session-db", "sessionDb"],
    ["--extension-data-root", "extensionDataRoot"],
    ["--extension-log-root", "extensionLogRoot"],
    ["--app-log-root", "appLogRoot"],
    ["--endpoint", "endpoint"],
    ["--output", "output"],
    ["--timeout-ms", "timeoutMs"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") {
      values.help = true;
      continue;
    }
    const key = valued.get(arg);
    if (!key) throw new Error(`未知选项：${arg}`);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
    values[key] = key === "timeoutMs" ? positiveInteger(value, arg) : value;
    index += 1;
  }
  if (values.endpoint) values.endpoint = validateEndpoint(values.endpoint);
  return values;
}

async function pathMetadata(path, expectedType = "either") {
  try {
    const canonical = await realpath(resolve(path));
    const info = await stat(canonical);
    const type = info.isDirectory() ? "directory" : info.isFile() ? "file" : "other";
    const typeMatches = expectedType === "either" || expectedType === type;
    return {
      path: canonical,
      exists: true,
      type,
      type_matches: typeMatches,
      size: info.size,
      modified_at: info.mtime.toISOString(),
      error: typeMatches ? null : `expected ${expectedType}, got ${type}`,
    };
  } catch (error) {
    return {
      path: resolve(path),
      exists: false,
      type: null,
      type_matches: false,
      size: null,
      modified_at: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function parseSessionRows(stdout) {
  const text = String(stdout || "").trim();
  if (!text) return [];
  const rows = JSON.parse(text);
  if (!Array.isArray(rows)) throw new Error("sqlite3 会话查询结果不是数组");
  const sessions = [];
  for (const row of rows) {
    try {
      const value = JSON.parse(String(row?.value || ""));
      if (!value || typeof value !== "object" || typeof value.conversationId !== "string") continue;
      sessions.push({
        conversation_id: value.conversationId,
        cwd: typeof value.cwd === "string" ? value.cwd : null,
        status: typeof value.status === "string" ? value.status : null,
        created_at_ms: Number.isFinite(value.createdAt) ? value.createdAt : null,
        updated_at_ms: Number.isFinite(value.updatedAt) ? value.updatedAt : null,
      });
    } catch {
      // Ignore unrelated or corrupt ItemTable rows. Exact native binding later
      // requires a unique conversation id + cwd match.
    }
  }
  return sessions;
}

export async function queryWorkBuddySessions(sessionDb, overrides = {}) {
  const runCommand = overrides.runCommand || runCapture;
  const metadata = await pathMetadata(sessionDb, "file");
  if (!metadata.exists || !metadata.type_matches) {
    return { status: "unavailable", backend: "sqlite3-readonly", metadata, sessions: [], error: metadata.error };
  }
  const result = await runCommand(
    overrides.sqliteBin || "/usr/bin/sqlite3",
    [
      "-readonly",
      "-json",
      metadata.path,
      "SELECT CAST(value AS TEXT) AS value FROM ItemTable WHERE key LIKE 'session:%' ORDER BY key;",
    ],
    { capture: true, allowFailure: true },
  ).catch((error) => ({ code: null, stdout: "", stderr: error instanceof Error ? error.message : String(error) }));
  if (result.code !== 0) {
    return {
      status: "unavailable",
      backend: "sqlite3-readonly",
      metadata,
      sessions: [],
      error: String(result.stderr || `sqlite3 exit ${result.code}`).trim(),
    };
  }
  try {
    return {
      status: "observed",
      backend: "sqlite3-readonly",
      snapshot_semantics: "single read transaction; source database is not modified",
      metadata,
      sessions: parseSessionRows(result.stdout),
      error: null,
    };
  } catch (error) {
    return {
      status: "unavailable",
      backend: "sqlite3-readonly",
      metadata,
      sessions: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function directoryNames(path) {
  try {
    return (await readdir(path, { withFileTypes: true }))
      .filter((item) => item.isDirectory() && !item.isSymbolicLink())
      .map((item) => item.name);
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
}

export async function inspectHistoryLayout(dataRoot) {
  const metadata = await pathMetadata(dataRoot, "directory");
  if (!metadata.exists || !metadata.type_matches) {
    return {
      status: "unavailable",
      metadata,
      account_directory_count: 0,
      workspace_history_count: 0,
      conversation_directory_count: 0,
      message_file_count: 0,
    };
  }
  let workspaceHistoryCount = 0;
  let conversationDirectoryCount = 0;
  let messageFileCount = 0;
  const accountDirectories = await directoryNames(metadata.path);
  for (const account of accountDirectories) {
    const vscodeRoot = join(metadata.path, account, "VSCode");
    const identityRoots = [vscodeRoot];
    for (const identity of await directoryNames(vscodeRoot)) identityRoots.push(join(vscodeRoot, identity));
    for (const identityRoot of identityRoots) {
      const historyRoot = join(identityRoot, "history");
      for (const workspaceKey of await directoryNames(historyRoot)) {
        workspaceHistoryCount += 1;
        const workspaceRoot = join(historyRoot, workspaceKey);
        for (const conversationId of await directoryNames(workspaceRoot)) {
          conversationDirectoryCount += 1;
          const messagesRoot = join(workspaceRoot, conversationId, "messages");
          try {
            const files = await readdir(messagesRoot, { withFileTypes: true });
            messageFileCount += files.filter((item) => item.isFile() && !item.name.startsWith(".") && item.name.endsWith(".json")).length;
          } catch (error) {
            if (error?.code !== "ENOENT") throw error;
          }
        }
      }
    }
  }
  return {
    status: "observed",
    metadata,
    account_directory_count: accountDirectories.length,
    workspace_history_count: workspaceHistoryCount,
    conversation_directory_count: conversationDirectoryCount,
    message_file_count: messageFileCount,
  };
}

async function inspectLogRoot(path) {
  const metadata = await pathMetadata(path, "directory");
  if (!metadata.exists || !metadata.type_matches) {
    return { status: "unavailable", metadata, run_directory_count: 0, latest_run_directory: null };
  }
  const directories = (await directoryNames(metadata.path)).sort();
  return {
    status: "observed",
    metadata,
    run_directory_count: directories.length,
    latest_run_directory: directories.at(-1) || null,
  };
}

function remoteDebuggingEndpoint(command) {
  const match = String(command || "").match(/(?:^|\s)--remote-debugging-port(?:=|\s+)(\d+)(?:\s|$)/u);
  if (!match) return null;
  const port = Number(match[1]);
  return Number.isInteger(port) && port > 0 && port <= 65535 ? `http://127.0.0.1:${port}` : null;
}

async function fetchJson(url, timeoutMs, fetchImpl = fetch) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function inspectCdp({ processInfo, endpoint, timeoutMs }, overrides = {}) {
  if (!processInfo) {
    return { status: "not_probed", endpoint: endpoint || null, reason: "workbuddy-not-running", version: null, targets: [] };
  }
  const inferred = remoteDebuggingEndpoint(processInfo.command);
  const selected = endpoint || inferred;
  if (!selected) {
    return { status: "unavailable", endpoint: null, reason: "running-process-has-no-verified-debug-port", version: null, targets: [] };
  }
  const origin = validateEndpoint(selected);
  try {
    const fetcher = overrides.fetchJson || fetchJson;
    const [version, targets] = await Promise.all([
      fetcher(`${origin}/json/version`, timeoutMs, overrides.fetchImpl),
      fetcher(`${origin}/json/list`, timeoutMs, overrides.fetchImpl),
    ]);
    return {
      status: "observed",
      endpoint: origin,
      endpoint_source: endpoint ? "explicit" : "process-command",
      reason: null,
      version: {
        browser: version?.Browser || null,
        protocol_version: version?.["Protocol-Version"] || null,
      },
      targets: Array.isArray(targets)
        ? targets.map((item) => ({ id: item?.id || null, type: item?.type || null, url: item?.url || null }))
        : [],
    };
  } catch (error) {
    return {
      status: "unavailable",
      endpoint: origin,
      endpoint_source: endpoint ? "explicit" : "process-command",
      reason: error instanceof Error ? error.message : String(error),
      version: null,
      targets: [],
    };
  }
}

async function commandValue(command, args, runCommand) {
  const result = await runCommand(command, args, { capture: true, allowFailure: true })
    .catch((error) => ({ code: null, stdout: "", stderr: error instanceof Error ? error.message : String(error) }));
  return result.code === 0 ? String(result.stdout || "").trim() || null : null;
}

export function identifyWorkBuddyMacosInstallation(discovery) {
  const executableName = basename(String(discovery?.executable_path || ""));
  if (executableName === "Electron") {
    // The version is evidence for compatibility reporting, not an identity
    // gate. WorkBuddy releases may keep the same Electron bundle layout while
    // changing their client version; runtime/UI/source gates decide whether
    // the driver can proceed.
    return "workbuddy-macos-electron";
  }
  if (!WORKBUDDY_APP_PROFILE.macos.executableNames.includes(executableName)) {
    throw new Error(
      `unsupported WorkBuddy macOS executable: ${executableName || "unavailable"}`,
    );
  }
  return "shared-profile";
}

export function classifyWorkBuddyMacosCompatibility(discovery) {
  const installationVariant = identifyWorkBuddyMacosInstallation(discovery);
  const version = String(discovery?.version || "");
  const knownVariant = WORKBUDDY_MACOS_INSTALLATION_VARIANTS.find(
    (item) => item.executable_name === basename(String(discovery?.executable_path || ""))
      && item.client_versions.includes(version),
  );
  return {
    installation_variant: installationVariant,
    observed_version: version || null,
    compatibility_status: knownVariant ? "verified" : "unverified_version",
    known_variant: knownVariant?.id || null,
  };
}

export async function inspectWorkBuddyMacos(options, overrides = {}) {
  const runCommand = overrides.runCommand || runCapture;
  const now = overrides.now || (() => new Date());
  const discovery = await (overrides.discoverDesktopApp || discoverDesktopApp)({
    profile: WORKBUDDY_MACOS_APP_PROFILE,
    requestedPath: options.appPath || "",
    platform: "darwin",
    environment: overrides.environment || process.env,
    home: overrides.home || homedir(),
  }, { ...overrides, runCommand });
  const compatibility = classifyWorkBuddyMacosCompatibility(discovery);
  const processInfo = await (overrides.inspectProcess || inspectMacDesktopAppProcess)({
    profile: WORKBUDDY_MACOS_APP_PROFILE,
    appPath: discovery.path,
  }, { ...overrides, runCommand });
  const [architecture, osVersion, sessionIndex, history, extensionLogs, appLogs, cdp] = await Promise.all([
    commandValue("/usr/bin/file", [discovery.executable_path], runCommand),
    commandValue("/usr/bin/sw_vers", ["-productVersion"], runCommand),
    queryWorkBuddySessions(options.sessionDb, { ...overrides, runCommand }),
    inspectHistoryLayout(options.extensionDataRoot),
    inspectLogRoot(options.extensionLogRoot),
    inspectLogRoot(options.appLogRoot),
    inspectCdp({ processInfo, endpoint: options.endpoint, timeoutMs: options.timeoutMs }, overrides),
  ]);
  const sourceReady = sessionIndex.status === "observed" && history.status === "observed";
  const controlReady = Boolean(processInfo) && cdp.status === "observed";
  return {
    schema_version: WORKBUDDY_PROBE_SCHEMA,
    probe_version: WORKBUDDY_PROBE_VERSION,
    mode: "read-only",
    status: discovery.identity_verified && sourceReady ? "PASS" : "PARTIAL",
    readiness: controlReady ? "READY_FOR_CONTROL_REVIEW" : "DISCOVERED_NOT_CONNECTED",
    captured_at: now().toISOString(),
    platform: { id: "macos", product_version: osVersion, architecture },
    application: { ...discovery, ...compatibility },
    process: processInfo ? { running: true, ...processInfo } : { running: false },
    cdp,
    native_sources: {
      session_index: sessionIndex,
      history,
      extension_logs: extensionLogs,
      application_logs: appLogs,
    },
    capabilities: {
      app_identity: discovery.identity_verified === true,
      process_identity: Boolean(processInfo),
      cdp_metadata: cdp.status === "observed",
      native_conversation_id: sessionIndex.sessions.length > 0,
      native_workspace_binding: sessionIndex.sessions.some((item) => Boolean(item.cwd)),
      native_terminal_status: sessionIndex.sessions.some((item) => Boolean(item.status)),
      native_history: history.message_file_count > 0,
      native_usage: history.message_file_count > 0,
      prompt_send: false,
      finalization: false,
    },
    limitations: [
      "Probe evidence is read-only and does not prove prompt submission, recovery, or finalization.",
      "Formal collect/trace-index/provenance and process cleanup remain dependent on COMMON CB-B.",
    ],
  };
}

async function writeExclusive(path, value) {
  const target = resolve(path);
  await mkdir(dirname(target), { recursive: true });
  const handle = await open(target, "wx");
  try {
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`, "utf8");
  } finally {
    await handle.close();
  }
  return target;
}

async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  for (const path of [options.sessionDb, options.extensionDataRoot]) await access(resolve(path)).catch(() => {});
  const result = await inspectWorkBuddyMacos(options);
  if (options.output) await writeExclusive(options.output, result);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

const isMain = process.argv[1]
  && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url));
if (isMain) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.stack || error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
