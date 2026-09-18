#!/usr/bin/env node

import { createHash } from "node:crypto";
import { copyFile, mkdir, mkdtemp, open, readFile, realpath, rm, stat } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  COMPONENT_NAME as DESKTOP_RUNTIME_NAME,
  COMPONENT_VERSION as DESKTOP_RUNTIME_VERSION,
  runCapture,
} from "../vendor/e2e-shared/desktop-runtime/process.mjs";

export const PROBE_SCHEMA = "wildclawbench.general-e2e-astronstudio-probe/v1";
export const RUN_CONFIG_SCHEMA = "wildclawbench.general-e2e-astronstudio-run-config/v1";
export const PROBE_VERSION = "0.1.0";
export const DEFAULT_APP_PATH = "/Applications/AStudio.app";
export const DEFAULT_BUNDLE_ID = "cn.xfyun.acode";
export const DEFAULT_ENDPOINT = "http://127.0.0.1:9240";
export const DEFAULT_STATE_DB = join(
  homedir(),
  ".acode",
  "acode",
  "userdata",
  "state.sqlite",
);
const SKILL_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

const REQUIRED_STATE_TABLES = Object.freeze([
  "projection_thread_sessions",
  "projection_threads",
]);
const READ_ONLY_OPERATIONS = Object.freeze([
  "read-skill-and-component-metadata",
  "read-os-version",
  "read-app-bundle",
  "read-process-identity",
  "read-gui-session",
  "read-listening-ports",
  "read-devtools-active-port",
  "http-get-cdp-metadata",
  "cdp-runtime-evaluate-readonly",
  "copy-state-database-snapshot",
  "query-state-database-snapshot",
  "read-dependency-versions",
]);

function usage() {
  return `AstronStudio General E2E macOS 只读探针

用法：
  node scripts/probe_astronstudio_macos.mjs [选项]

选项：
  --app-path <AStudio.app>         默认 /Applications/AStudio.app
  --state-db <state.sqlite>        默认 ~/.acode/acode/userdata/state.sqlite
  --endpoint <http://127.0.0.1:端口> 显式指定本机 CDP；省略时按进程参数、有效 DevToolsActivePort、9240 探测
  --output <probe.json>            新建探针结果；已存在时拒绝覆盖
  --config-output <config.json>    仅 PASS 时新建冻结运行配置；已存在时拒绝覆盖
  --timeout-ms <毫秒>              单次 CDP 请求超时，默认 2000
  -h, --help                       显示帮助

探针不会启动或退出 AStudio，不选择项目/模型，不打开菜单，不填写编辑器，也不发送 Prompt。`;
}

function parsePositiveInteger(value, field) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`${field} 必须是正整数`);
  return parsed;
}

export function parseArgs(argv) {
  const config = {
    appPath: DEFAULT_APP_PATH,
    stateDb: DEFAULT_STATE_DB,
    endpoint: null,
    endpointExplicit: false,
    output: null,
    configOutput: null,
    timeoutMs: 2000,
    help: false,
  };
  const valued = new Map([
    ["--app-path", "appPath"],
    ["--state-db", "stateDb"],
    ["--endpoint", "endpoint"],
    ["--output", "output"],
    ["--config-output", "configOutput"],
    ["--timeout-ms", "timeoutMs"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") {
      config.help = true;
      continue;
    }
    const key = valued.get(arg);
    if (!key) throw new Error(`未知选项：${arg}`);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
    index += 1;
    config[key] = key === "timeoutMs" ? parsePositiveInteger(value, arg) : value;
    if (key === "endpoint") config.endpointExplicit = true;
  }
  if (!config.help) {
    if (!config.stateDb) throw new Error("无法从 HOME 推导状态库；请指定 --state-db");
    if (config.endpoint) config.endpoint = validateEndpoint(config.endpoint).origin;
  }
  return config;
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
    throw new Error("CDP endpoint 必须是带显式端口的本机 http 根地址");
  }
  return endpoint;
}

function isoOrNull(value) {
  if (!Number.isFinite(value)) return null;
  return new Date(value).toISOString();
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.keys(value).sort().map((key) => [key, stableValue(value[key])]),
  );
}

function digestJson(value) {
  return sha256(JSON.stringify(stableValue(value)));
}

export function calculateRunConfigDigest(value) {
  const {
    config_digest_algorithm: _algorithm,
    config_digest: _digest,
    ...payload
  } = value;
  return digestJson(payload);
}

function commandVersion(result) {
  if (!result || result.code !== 0) return null;
  return String(result.stdout || result.stderr || "").trim().split(/\r?\n/u)[0] || null;
}

async function readCommandVersion(command, args, runCommand = runCapture) {
  try {
    const result = await runCommand(command, args, { capture: true, allowFailure: true });
    return {
      available: result.code === 0,
      version: commandVersion(result),
      command,
      error: result.code === 0 ? null : String(result.stderr || "").trim() || `exit ${result.code}`,
    };
  } catch (error) {
    return {
      available: false,
      version: null,
      command,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function inspectEnvironment(runCommand = runCapture) {
  const [productVersion, buildVersion, architecture] = await Promise.all([
    readCommandVersion("/usr/bin/sw_vers", ["-productVersion"], runCommand),
    readCommandVersion("/usr/bin/sw_vers", ["-buildVersion"], runCommand),
    readCommandVersion("/usr/bin/uname", ["-m"], runCommand),
  ]);
  return {
    platform: process.platform,
    product_name: process.platform === "darwin" ? "macOS" : null,
    product_version: productVersion.version,
    build_version: buildVersion.version,
    architecture: architecture.version,
  };
}

async function readJsonIfPresent(path) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

async function inspectImplementation() {
  const metadata = await readJsonIfPresent(join(SKILL_ROOT, "skill-metadata.json"));
  const bundled = await readJsonIfPresent(join(SKILL_ROOT, "bundled-components.json"));
  const components = Array.isArray(bundled?.components)
    ? bundled.components.map((item) => ({
      name: typeof item?.name === "string" ? item.name : null,
      version: typeof item?.version === "string" ? item.version : null,
      content_sha256: typeof item?.content_sha256 === "string" ? item.content_sha256 : null,
    }))
    : [{
      name: DESKTOP_RUNTIME_NAME,
      version: DESKTOP_RUNTIME_VERSION,
      content_sha256: null,
    }];
  return {
    skill_name: metadata?.name || "execute-general-e2e",
    skill_version: metadata?.version || null,
    implementation_status: metadata?.implementation_status || null,
    source_revision: typeof bundled?.source_revision === "string" ? bundled.source_revision : null,
    distribution: bundled ? "built-skill-package" : "repository-source",
    components,
  };
}

async function inspectApp(appPath, runCommand = runCapture) {
  const resolvedPath = await realpath(resolve(appPath));
  const appAsar = join(resolvedPath, "Contents", "Resources", "app.asar");
  const asarStat = await stat(appAsar);
  if (!asarStat.isFile()) throw new Error(`AstronStudio app.asar 不存在：${appAsar}`);
  const [versionResult, bundleResult] = await Promise.all([
    runCommand(
      "/usr/bin/defaults",
      ["read", join(resolvedPath, "Contents", "Info"), "CFBundleShortVersionString"],
      { capture: true, allowFailure: true },
    ),
    runCommand(
      "/usr/bin/defaults",
      ["read", join(resolvedPath, "Contents", "Info"), "CFBundleIdentifier"],
      { capture: true, allowFailure: true },
    ),
  ]);
  const version = versionResult.code === 0 ? versionResult.stdout.trim() : null;
  const bundleId = bundleResult.code === 0 ? bundleResult.stdout.trim() : null;
  return {
    installed: true,
    path: resolvedPath,
    executable_path: join(resolvedPath, "Contents", "MacOS", "AStudio"),
    bundle_id: bundleId,
    version,
    bundle_identity_verified: bundleId === DEFAULT_BUNDLE_ID,
  };
}

function parseDebugPort(command) {
  const match = String(command || "").match(/(?:^|\s)--remote-debugging-port(?:=|\s+)(\d+)(?=\s|$)/u);
  if (!match) return null;
  const port = Number(match[1]);
  return Number.isInteger(port) && port > 0 && port <= 65535 ? port : null;
}

async function inspectProcess(app, runCommand = runCapture) {
  const pidResult = await runCommand(
    "/usr/bin/osascript",
    ["-e", `tell application "System Events" to get unix id of first application process whose bundle identifier is "${DEFAULT_BUNDLE_ID}"`],
    { capture: true, allowFailure: true },
  );
  const pid = Number(pidResult.stdout.trim());
  if (pidResult.code !== 0 || !Number.isInteger(pid) || pid <= 0) {
    return { running: false, identity_verified: false, pid: null };
  }
  const readPs = async (format) => {
    const result = await runCommand("/bin/ps", ["-p", String(pid), "-o", format], {
      capture: true,
      allowFailure: true,
    });
    return result.code === 0 ? result.stdout.trim() : "";
  };
  const [ppidText, startedText, executable, command] = await Promise.all([
    readPs("ppid="),
    readPs("lstart="),
    readPs("comm="),
    readPs("command="),
  ]);
  const expectedExecutable = await realpath(app.executable_path);
  let actualExecutable = executable;
  try {
    actualExecutable = await realpath(executable);
  } catch {
    // Keep the observed value so identity verification fails closed.
  }
  const startedAtEpoch = Date.parse(startedText);
  return {
    running: true,
    identity_verified: actualExecutable === expectedExecutable,
    pid,
    ppid: Number(ppidText) || null,
    executable_path: actualExecutable || null,
    started_at: isoOrNull(startedAtEpoch),
    command_sha256: command ? sha256(command) : null,
    remote_debugging_port: parseDebugPort(command),
  };
}

export async function inspectGui(runCommand = runCapture) {
  const [frontmost, registry] = await Promise.all([
    runCommand(
      "/usr/bin/osascript",
      ["-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
      { capture: true, allowFailure: true },
    ),
    runCommand("/usr/sbin/ioreg", ["-n", "Root", "-d1"], {
      capture: true,
      allowFailure: true,
    }),
  ]);
  const frontmostApplication = frontmost.code === 0 ? frontmost.stdout.trim() : "unknown";
  const lockMatch = registry.stdout.match(/"IOConsoleLocked"\s*=\s*(Yes|No)/u);
  const screenLocked = lockMatch ? lockMatch[1] === "Yes" : null;
  return {
    frontmost_application: frontmostApplication,
    screen_locked: screenLocked,
    lock_source: lockMatch ? "ioreg.IOConsoleLocked" : null,
    unlocked: screenLocked === false,
  };
}

async function listeningPorts(pid, runCommand = runCapture) {
  if (!pid) return [];
  const result = await runCommand(
    "/usr/sbin/lsof",
    ["-nP", "-a", "-p", String(pid), "-iTCP", "-sTCP:LISTEN", "-Fn"],
    { capture: true, allowFailure: true },
  );
  if (result.code !== 0) return [];
  const ports = [];
  for (const line of result.stdout.split(/\r?\n/u)) {
    if (!line.startsWith("n")) continue;
    const match = line.match(/:(\d+)$/u);
    if (match) ports.push(Number(match[1]));
  }
  return [...new Set(ports)].sort((left, right) => left - right);
}

export async function inspectActivePortFile(processInfo) {
  const activePortPath = join(
    homedir(),
    ".acode",
    "acode",
    "electron",
    "DevToolsActivePort",
  );
  try {
    const [fileStat, text] = await Promise.all([
      stat(activePortPath),
      readFile(activePortPath, "utf8"),
    ]);
    const [portText] = text.split(/\r?\n/u);
    const port = Number(portText);
    const processStarted = Date.parse(processInfo.started_at || "");
    const fresh = Number.isFinite(processStarted) && fileStat.mtimeMs >= processStarted;
    return {
      path: activePortPath,
      exists: true,
      port: Number.isInteger(port) && port > 0 && port <= 65535 ? port : null,
      modified_at: fileStat.mtime.toISOString(),
      valid_for_process: Boolean(fresh && port),
      status: fresh && port ? "current" : "stale_or_invalid",
    };
  } catch (error) {
    return {
      path: activePortPath,
      exists: false,
      port: null,
      modified_at: null,
      valid_for_process: false,
      status: error?.code === "ENOENT" ? "missing" : "unreadable",
      error: error?.code === "ENOENT" ? null : (error instanceof Error ? error.message : String(error)),
    };
  }
}

function endpointCandidates(config, processInfo, activePort) {
  const candidates = [];
  const add = (endpoint, source) => {
    if (!endpoint || candidates.some((item) => item.endpoint === endpoint)) return;
    candidates.push({ endpoint, source });
  };
  if (config.endpointExplicit) add(config.endpoint, "explicit");
  if (!config.endpointExplicit && processInfo.remote_debugging_port) {
    add(`http://127.0.0.1:${processInfo.remote_debugging_port}`, "process-command");
  }
  if (!config.endpointExplicit && activePort.valid_for_process) {
    add(`http://127.0.0.1:${activePort.port}`, "devtools-active-port-current-process");
  }
  if (!config.endpointExplicit) add(DEFAULT_ENDPOINT, "default");
  return candidates;
}

async function fetchJson(url, timeoutMs, fetchImpl = fetch) {
  const response = await fetchImpl(url, {
    method: "GET",
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export const READ_ONLY_DOM_EXPRESSION = `(() => {
  const visible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
  };
  const modelSelector = 'button[aria-label="切换模型和推理设置"], button[aria-label="Change model and reasoning"]';
  const models = Array.from(document.querySelectorAll(modelSelector)).filter(visible);
  const permissions = Array.from(document.querySelectorAll('button.runtime-permission-trigger')).filter(visible);
  return {
    model_count: models.length,
    model_text: models.length === 1 ? (models[0].innerText || "").trim() : null,
    permission_count: permissions.length,
    permission_text: permissions.length === 1 ? (permissions[0].innerText || "").trim() : null,
    permission_disabled: permissions.length === 1 ? Boolean(permissions[0].disabled) : null
  };
})()`;

async function evaluateReadOnlyDom(webSocketUrl, timeoutMs, WebSocketImpl = globalThis.WebSocket) {
  if (typeof WebSocketImpl !== "function") throw new Error("当前 Node.js 不提供 WebSocket API");
  const socket = new WebSocketImpl(webSocketUrl);
  return new Promise((resolvePromise, rejectPromise) => {
    let settled = false;
    const timer = setTimeout(() => settle(new Error("CDP 只读 DOM 回读超时")), timeoutMs);
    const settle = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { socket.close(); } catch { /* ignore close races */ }
      if (error) rejectPromise(error);
      else resolvePromise(value);
    };
    socket.addEventListener("error", () => settle(new Error("CDP WebSocket 连接失败")), { once: true });
    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({
        id: 1,
        method: "Runtime.evaluate",
        params: {
          expression: READ_ONLY_DOM_EXPRESSION,
          returnByValue: true,
          awaitPromise: false,
          userGesture: false,
        },
      }));
    }, { once: true });
    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (message.id !== 1) return;
      if (message.error) {
        settle(new Error(`CDP Runtime.evaluate 失败：${message.error.message || "unknown"}`));
        return;
      }
      settle(null, message.result?.result?.value || null);
    });
  });
}

function normalizeModelDom(value) {
  const lines = String(value?.model_text || "")
    .split(/\r?\n/u)
    .map((item) => item.trim())
    .filter(Boolean);
  const model = value?.model_count === 1 && lines[0] ? lines[0] : null;
  const reasoning = model && lines.length > 1 ? lines.slice(1).join(" ") : null;
  const permission = value?.permission_count === 1 && String(value.permission_text || "").trim()
    ? String(value.permission_text).trim()
    : null;
  return {
    model: {
      value: model,
      reasoning_display: reasoning,
      source: "cdp-visible-model-trigger",
      verified: Boolean(model),
      reasoning_verified: Boolean(reasoning),
      visible_match_count: Number(value?.model_count) || 0,
    },
    permission: {
      display: permission,
      source: "cdp-visible-permission-trigger",
      verified: Boolean(permission),
      disabled: typeof value?.permission_disabled === "boolean" ? value.permission_disabled : null,
      visible_match_count: Number(value?.permission_count) || 0,
    },
  };
}

export async function inspectCdp(config, processInfo, activePort, ownedPorts, overrides = {}) {
  const fetchImpl = overrides.fetchImpl || fetch;
  const evaluateDom = overrides.evaluateDom || evaluateReadOnlyDom;
  const attempts = [];
  for (const candidate of endpointCandidates(config, processInfo, activePort)) {
    const endpointUrl = validateEndpoint(candidate.endpoint);
    const port = Number(endpointUrl.port);
    const attempt = {
      endpoint: candidate.endpoint,
      source: candidate.source,
      ready: false,
      owned_by_main_process: ownedPorts.includes(port),
      error: null,
    };
    attempts.push(attempt);
    try {
      const version = await fetchJson(`${candidate.endpoint}/json/version`, config.timeoutMs, fetchImpl);
      const targets = await fetchJson(`${candidate.endpoint}/json/list`, config.timeoutMs, fetchImpl);
      const pages = Array.isArray(targets) ? targets.filter((item) => item?.type === "page") : [];
      const mainPages = pages.filter((item) => {
        if (!/^AStudio$/iu.test(String(item.title || "").trim())) return false;
        try {
          const url = new URL(String(item.url || ""));
          return url.protocol === "acode:" && url.host === "app" && url.pathname === "/index.html";
        } catch {
          return false;
        }
      });
      if (mainPages.length !== 1) {
        throw new Error(`AstronStudio 主页面数量异常：${mainPages.length}`);
      }
      const target = mainPages[0];
      if (!version?.webSocketDebuggerUrl && !version?.Browser) throw new Error("缺少 CDP browser identity");
      if (!target?.webSocketDebuggerUrl) throw new Error("缺少 AstronStudio page target");
      if (!attempt.owned_by_main_process) throw new Error("CDP 端口不属于已核对的 AStudio 主进程");
      const dom = normalizeModelDom(
        await evaluateDom(target.webSocketDebuggerUrl, config.timeoutMs, overrides.WebSocketImpl),
      );
      attempt.ready = true;
      return {
        ready: true,
        endpoint: candidate.endpoint,
        endpoint_source: candidate.source,
        owned_by_main_process: true,
        browser: typeof version.Browser === "string" ? version.Browser : null,
        protocol_version: typeof version["Protocol-Version"] === "string"
          ? version["Protocol-Version"]
          : null,
        page_target_count: pages.length,
        page_title: target.title,
        page_url_scheme: target.url ? new URL(target.url).protocol : null,
        model: dom.model,
        permission: dom.permission,
        attempts,
      };
    } catch (error) {
      attempt.error = error instanceof Error ? error.message : String(error);
    }
  }
  return {
    ready: false,
    endpoint: null,
    endpoint_source: null,
    owned_by_main_process: false,
    browser: null,
    protocol_version: null,
    page_target_count: null,
    page_title: null,
    page_url_scheme: null,
    model: {
      value: null,
      reasoning_display: null,
      source: null,
      verified: false,
      reasoning_verified: false,
      visible_match_count: 0,
    },
    permission: {
      display: null,
      source: null,
      verified: false,
      disabled: null,
      visible_match_count: 0,
    },
    attempts,
  };
}

async function loadNodeSqlite() {
  return import("node:sqlite").catch(() => null);
}

async function copyIfPresent(source, destination) {
  try {
    await copyFile(source, destination);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

function whitelistPersistedModel(row) {
  if (!row?.model_selection_json) return null;
  let selection;
  try {
    selection = JSON.parse(row.model_selection_json);
  } catch {
    return null;
  }
  return {
    provider: typeof selection.provider === "string" ? selection.provider : null,
    model: typeof selection.model === "string" ? selection.model : null,
    reasoning_effort: typeof selection.options?.reasoningEffort === "string"
      ? selection.options.reasoningEffort
      : null,
    runtime_mode: typeof row.runtime_mode === "string" ? row.runtime_mode : null,
    updated_at: typeof row.updated_at === "string" ? row.updated_at : null,
    source: "state-db-latest-updated-thread",
    current_ui_verified: false,
  };
}

const ACTIVE_SESSION_COUNT_QUERY = `
SELECT COUNT(DISTINCT sessions.thread_id) AS active_or_pending_count
FROM projection_thread_sessions AS sessions
WHERE sessions.active_turn_id IS NOT NULL
  OR sessions.status IN ('starting', 'running', 'pending', 'needs_attention')
  OR EXISTS (
    SELECT 1 FROM projection_pending_interactions AS pending
    WHERE pending.thread_id = sessions.thread_id AND pending.status = 'pending'
  )
  OR EXISTS (
    SELECT 1 FROM provider_runtime_open_turns AS open_turn
    WHERE open_turn.thread_id = sessions.thread_id
  );
`;

async function querySnapshotWithNodeSqlite(snapshotPath, sqliteModule) {
  const database = new sqliteModule.DatabaseSync(snapshotPath, { readOnly: true });
  try {
    const quickRows = database.prepare("PRAGMA quick_check;").all();
    const quickCheck = String(Object.values(quickRows[0] || {})[0] || "");
    const tableRows = database.prepare(
      "SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name;",
    ).all();
    const tables = tableRows.map((row) => String(row.name));
    const missingTables = REQUIRED_STATE_TABLES.filter((name) => !tables.includes(name));
    let latest = null;
    let activeOrPendingSessionCount = null;
    if (!missingTables.includes("projection_threads")) {
      latest = database.prepare(`
SELECT model_selection_json, runtime_mode, updated_at
FROM projection_threads
WHERE deleted_at IS NULL
  AND model_selection_json IS NOT NULL
  AND trim(model_selection_json) <> ''
ORDER BY updated_at DESC
LIMIT 1;
`).get();
    }
    if (
      !missingTables.includes("projection_thread_sessions")
      && tables.includes("projection_pending_interactions")
      && tables.includes("provider_runtime_open_turns")
    ) {
      activeOrPendingSessionCount = Number(
        database.prepare(ACTIVE_SESSION_COUNT_QUERY).get()?.active_or_pending_count,
      );
    }
    return {
      integrity: quickCheck,
      table_count: tables.length,
      missing_required_tables: missingTables,
      latest_persisted_model: whitelistPersistedModel(latest),
      active_or_pending_session_count: Number.isInteger(activeOrPendingSessionCount)
        ? activeOrPendingSessionCount
        : null,
    };
  } finally {
    database.close();
  }
}

async function querySnapshotWithCli(snapshotPath, runCommand = runCapture) {
  const integrityResult = await runCommand(
    "/usr/bin/sqlite3",
    ["-readonly", snapshotPath, "PRAGMA quick_check;"],
    { capture: true, allowFailure: false },
  );
  const tablesResult = await runCommand(
    "/usr/bin/sqlite3",
    ["-readonly", "-json", snapshotPath, "SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name;"],
    { capture: true, allowFailure: false },
  );
  const tables = JSON.parse(tablesResult.stdout || "[]").map((row) => String(row.name));
  const missingTables = REQUIRED_STATE_TABLES.filter((name) => !tables.includes(name));
  let latest = null;
  let activeOrPendingSessionCount = null;
  if (!missingTables.includes("projection_threads")) {
    const latestResult = await runCommand(
      "/usr/bin/sqlite3",
      ["-readonly", "-json", snapshotPath, `
SELECT model_selection_json, runtime_mode, updated_at
FROM projection_threads
WHERE deleted_at IS NULL
  AND model_selection_json IS NOT NULL
  AND trim(model_selection_json) <> ''
ORDER BY updated_at DESC
LIMIT 1;`],
      { capture: true, allowFailure: false },
    );
    latest = JSON.parse(latestResult.stdout || "[]")[0] || null;
  }
  if (
    !missingTables.includes("projection_thread_sessions")
    && tables.includes("projection_pending_interactions")
    && tables.includes("provider_runtime_open_turns")
  ) {
    const activeResult = await runCommand(
      "/usr/bin/sqlite3",
      ["-readonly", "-json", snapshotPath, ACTIVE_SESSION_COUNT_QUERY],
      { capture: true, allowFailure: false },
    );
    activeOrPendingSessionCount = Number(
      JSON.parse(activeResult.stdout || "[]")[0]?.active_or_pending_count,
    );
  }
  return {
    integrity: integrityResult.stdout.trim(),
    table_count: tables.length,
    missing_required_tables: missingTables,
    latest_persisted_model: whitelistPersistedModel(latest),
    active_or_pending_session_count: Number.isInteger(activeOrPendingSessionCount)
      ? activeOrPendingSessionCount
      : null,
  };
}

export async function inspectStateDatabase(stateDb, overrides = {}) {
  const statePath = await realpath(resolve(stateDb));
  const sourceStat = await stat(statePath);
  if (!sourceStat.isFile()) throw new Error(`状态库不是文件：${statePath}`);
  const sqliteModule = await (overrides.loadNodeSqlite || loadNodeSqlite)();
  const backend = typeof sqliteModule?.DatabaseSync === "function" ? "node:sqlite" : "sqlite3-cli";
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const snapshotRoot = await mkdtemp(join(tmpdir(), "general-e2e-astudio-state-"));
    const snapshotPath = join(snapshotRoot, "state.sqlite");
    try {
      await copyFile(statePath, snapshotPath);
      await copyIfPresent(`${statePath}-wal`, `${snapshotPath}-wal`);
      await copyIfPresent(`${statePath}-shm`, `${snapshotPath}-shm`);
      const query = backend === "node:sqlite"
        ? await querySnapshotWithNodeSqlite(snapshotPath, sqliteModule)
        : await querySnapshotWithCli(snapshotPath, overrides.runCommand || runCapture);
      if (query.integrity !== "ok") throw new Error(`快照 quick_check=${query.integrity || "empty"}`);
      return {
        path: statePath,
        readable: true,
        source_open_mode: "copy-only",
        snapshot_backend: backend,
        snapshot_attempts: attempt,
        integrity: query.integrity,
        table_count: query.table_count,
        missing_required_tables: query.missing_required_tables,
        schema_ready: query.missing_required_tables.length === 0,
        latest_persisted_model: query.latest_persisted_model,
        active_or_pending_session_count: query.active_or_pending_session_count,
        source_size_bytes: sourceStat.size,
        source_modified_at_before_probe: sourceStat.mtime.toISOString(),
        error: null,
      };
    } catch (error) {
      lastError = error;
    } finally {
      await rm(snapshotRoot, { recursive: true, force: true }).catch(() => {});
    }
  }
  return {
    path: statePath,
    readable: false,
    source_open_mode: "copy-only",
    snapshot_backend: backend,
    snapshot_attempts: 3,
    integrity: null,
    table_count: null,
    missing_required_tables: [...REQUIRED_STATE_TABLES],
    schema_ready: false,
    latest_persisted_model: null,
    active_or_pending_session_count: null,
    source_size_bytes: sourceStat.size,
    source_modified_at_before_probe: sourceStat.mtime.toISOString(),
    error: lastError instanceof Error ? lastError.message : String(lastError),
  };
}

async function inspectDependencies(runCommand = runCapture, loadSqlite = loadNodeSqlite) {
  const [python, sqliteCli, docker, codex, sqliteModule] = await Promise.all([
    readCommandVersion("python3", ["--version"], runCommand),
    readCommandVersion("/usr/bin/sqlite3", ["--version"], runCommand),
    readCommandVersion("docker", ["--version"], runCommand),
    readCommandVersion("codex", ["--version"], runCommand),
    loadSqlite(),
  ]);
  return {
    node: {
      available: true,
      version: process.version,
      executable: process.execPath,
      websocket_api: typeof globalThis.WebSocket === "function",
    },
    python,
    sqlite: {
      node_sqlite_available: typeof sqliteModule?.DatabaseSync === "function",
      cli: sqliteCli,
    },
    docker,
    codex,
    required_for_probe: {
      node: true,
      state_database_backend: typeof sqliteModule?.DatabaseSync === "function" || sqliteCli.available,
    },
    recorded_for_later_stages: ["python", "docker", "codex"],
  };
}

function failedChecks(observation) {
  const checks = [
    ["PLATFORM_NOT_MACOS", observation.environment.platform === "darwin"],
    ["APP_NOT_VERIFIED", observation.app.installed && observation.app.bundle_identity_verified && Boolean(observation.app.version)],
    ["PROCESS_NOT_VERIFIED", observation.process.running && observation.process.identity_verified],
    ["GUI_LOCKED_OR_UNKNOWN", observation.gui.unlocked === true],
    ["CDP_NOT_READY", observation.cdp.ready && observation.cdp.owned_by_main_process],
    ["STATE_DATABASE_NOT_READY", observation.state_database.readable && observation.state_database.integrity === "ok" && observation.state_database.schema_ready],
    ["MODEL_NOT_READ_FROM_UI", observation.cdp.model.verified],
    ["REASONING_NOT_READ_FROM_UI", observation.cdp.model.reasoning_verified],
    ["PERMISSION_NOT_READ_FROM_UI", observation.cdp.permission.verified],
    ["NODE_NOT_READY", observation.dependencies.required_for_probe.node],
    ["SQLITE_BACKEND_NOT_READY", observation.dependencies.required_for_probe.state_database_backend],
  ];
  return checks.filter(([, passed]) => !passed).map(([code]) => code);
}

export function buildFrozenRunConfig(observation) {
  const config = {
    schema_version: RUN_CONFIG_SCHEMA,
    contract_version: "general-e2e-contract-v1",
    frozen_at: observation.captured_at,
    implementation: observation.implementation,
    platform: {
      os: observation.environment.product_name,
      version: observation.environment.product_version,
      build: observation.environment.build_version,
      architecture: observation.environment.architecture,
    },
    harness: {
      id: "astronstudio",
      app_path: observation.app.path,
      bundle_id: observation.app.bundle_id,
      client_version: observation.app.version,
      process_executable: observation.process.executable_path,
    },
    control: {
      backend: "electron-cdp",
      endpoint: observation.cdp.endpoint,
      endpoint_source: observation.cdp.endpoint_source,
      ui_slots: 1,
      execution_concurrency: 3,
      maximum_execution_concurrency: 8,
    },
    state_database: {
      path: observation.state_database.path,
      snapshot_backend: observation.state_database.snapshot_backend,
      required_tables: [...REQUIRED_STATE_TABLES],
    },
    tested_model: {
      display_name: observation.cdp.model.value,
      reasoning_display: observation.cdp.model.reasoning_display,
      permission_display: observation.cdp.permission.display,
      verification: "cdp-visible-current-value",
    },
    dependencies: observation.dependencies,
    execution_policy: {
      prompt_send_enabled_by_probe: false,
      app_restart_enabled_by_probe: false,
      initial_concurrency: 3,
    },
  };
  return {
    ...config,
    config_digest_algorithm: "sha256-canonical-json/v1",
    config_digest: calculateRunConfigDigest(config),
  };
}

export function buildProbeReport(observation, capturedAt = new Date().toISOString()) {
  const completeObservation = { ...observation, captured_at: capturedAt };
  const failures = failedChecks(observation);
  const status = failures.length ? "NEEDS_ATTENTION" : "PASS";
  return {
    schema_version: PROBE_SCHEMA,
    probe_version: PROBE_VERSION,
    captured_at: capturedAt,
    status,
    ready: status === "PASS",
    failed_checks: failures,
    implementation: observation.implementation,
    environment: observation.environment,
    app: observation.app,
    process: observation.process,
    gui: observation.gui,
    devtools_active_port: observation.devtools_active_port,
    cdp: observation.cdp,
    state_database: observation.state_database,
    dependencies: observation.dependencies,
    action_audit: {
      policy: "read_only",
      allowed_operations: [...READ_ONLY_OPERATIONS],
      app_start_attempted: false,
      app_restart_attempted: false,
      app_quit_attempted: false,
      ui_click_attempted: false,
      workspace_selection_attempted: false,
      model_selection_attempted: false,
      composer_access_attempted: false,
      prompt_send_attempted: false,
      source_database_write_attempted: false,
    },
    frozen_run_config: status === "PASS" ? buildFrozenRunConfig(completeObservation) : null,
  };
}

async function safeObservation(label, fallback, operation) {
  try {
    return await operation();
  } catch (error) {
    return {
      ...fallback,
      error: `${label}: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

export async function probeAstronStudio(config, overrides = {}) {
  const runCommand = overrides.runCommand || runCapture;
  const environment = await safeObservation("environment", {
    platform: process.platform,
    product_name: null,
    product_version: null,
    build_version: null,
    architecture: null,
  }, () => (overrides.inspectEnvironment || inspectEnvironment)(runCommand));
  const implementation = await safeObservation("implementation", {
    skill_name: "execute-general-e2e",
    skill_version: null,
    implementation_status: null,
    source_revision: null,
    distribution: "unknown",
    components: [],
  }, () => (overrides.inspectImplementation || inspectImplementation)());
  const app = await safeObservation("app", {
    installed: false,
    path: resolve(config.appPath),
    executable_path: null,
    bundle_id: null,
    version: null,
    bundle_identity_verified: false,
  }, () => (overrides.inspectApp || inspectApp)(config.appPath, runCommand));
  const processInfo = await safeObservation("process", {
    running: false,
    identity_verified: false,
    pid: null,
  }, () => (overrides.inspectProcess || inspectProcess)(app, runCommand));
  const [gui, ports, activePort, stateDatabase, dependencies] = await Promise.all([
    safeObservation("gui", {
      frontmost_application: "unknown",
      screen_locked: null,
      lock_source: null,
      unlocked: false,
    }, () => (overrides.inspectGui || inspectGui)(runCommand)),
    (overrides.listeningPorts || listeningPorts)(processInfo.pid, runCommand).catch(() => []),
    safeObservation("DevToolsActivePort", {
      path: null,
      exists: false,
      port: null,
      modified_at: null,
      valid_for_process: false,
      status: "unreadable",
    }, () => (overrides.inspectActivePortFile || inspectActivePortFile)(processInfo)),
    safeObservation("state database", {
      path: resolve(config.stateDb),
      readable: false,
      integrity: null,
      schema_ready: false,
      latest_persisted_model: null,
    }, () => (overrides.inspectStateDatabase || inspectStateDatabase)(config.stateDb, overrides)),
    safeObservation("dependencies", {
      required_for_probe: { node: true, state_database_backend: false },
    }, () => (overrides.inspectDependencies || inspectDependencies)(runCommand, overrides.loadNodeSqlite || loadNodeSqlite)),
  ]);
  const cdp = await safeObservation("cdp", {
    ready: false,
    endpoint: null,
    endpoint_source: null,
    owned_by_main_process: false,
    model: {
      value: null,
      reasoning_display: null,
      source: null,
      verified: false,
      reasoning_verified: false,
    },
    permission: { display: null, source: null, verified: false },
    attempts: [],
  }, () => (overrides.inspectCdp || inspectCdp)(
    config,
    processInfo,
    activePort,
    ports,
    overrides,
  ));
  return buildProbeReport({
    implementation,
    environment,
    app,
    process: { ...processInfo, listening_ports: ports },
    gui,
    devtools_active_port: activePort,
    cdp,
    state_database: stateDatabase,
    dependencies,
  }, overrides.capturedAt || new Date().toISOString());
}

async function writeNewJson(path, value) {
  const target = resolve(path);
  await mkdir(dirname(target), { recursive: true });
  const handle = await open(target, "wx", 0o644);
  try {
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`, "utf8");
  } finally {
    await handle.close();
  }
  return target;
}

export async function main(argv = process.argv.slice(2), overrides = {}) {
  let config;
  try {
    config = parseArgs(argv);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    console.error(usage());
    return 2;
  }
  if (config.help) {
    console.log(usage());
    return 0;
  }
  if (process.platform !== "darwin" && !overrides.allowNonDarwin) {
    console.error("本入口只支持 AstronStudio macOS 探针；Windows 将由 G5-01 的原生入口实现");
    return 2;
  }
  try {
    const report = await probeAstronStudio(config, overrides);
    if (config.output) await writeNewJson(config.output, report);
    if (config.configOutput) {
      if (!report.frozen_run_config) {
        throw new Error("探针未通过，拒绝写入冻结运行配置");
      }
      await writeNewJson(config.configOutput, report.frozen_run_config);
    }
    console.log(JSON.stringify(report, null, 2));
    return report.ready ? 0 : 3;
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return 2;
  }
}

let invokedPath = process.argv[1] ? resolve(process.argv[1]) : null;
let modulePath = fileURLToPath(import.meta.url);
try {
  if (invokedPath) invokedPath = await realpath(invokedPath);
  modulePath = await realpath(modulePath);
} catch {
  // The normal comparison below still fails closed when either path disappears.
}
if (invokedPath && invokedPath === modulePath) {
  process.exitCode = await main();
}
