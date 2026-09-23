#!/usr/bin/env node

import { access, lstat, mkdir, readFile, readdir, realpath, rename, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  discoverDesktopApp,
} from "../../vendor/e2e-shared/desktop-app-discovery/index.mjs";
import {
  QWENWORK_APP_PROFILE,
} from "../../vendor/e2e-shared/desktop-app-discovery/profiles.mjs";
import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";

import {
  defaultQwenWorkSessionDatabase,
  inspectQwenSessionDatabase,
  QWENWORK_GENERAL_DRIVER_VERSION,
} from "./session-state.mjs";
import {
  inspectDriverRuntimeIdentity,
  matchDriverRuntimeProfile,
} from "./runtime-profile.mjs";

export const QWENWORK_PROBE_SCHEMA = "wildclawbench.general-e2e-qwenwork-readonly-probe/v1";
const MAX_TRANSCRIPT_BYTES = 32 * 1024 * 1024;
const MAX_DISCOVERY_FILES = 5000;

function usage() {
  return `QwenWork macOS General E2E read-only probe

Usage:
  node drivers/qwenwork/probe.mjs [options]

Options:
  --app-path <path>       Explicit QwenWork app bundle
  --session-db <path>     agents.db path
  --trace-root <path>     QwenWork native trace root
  --endpoint <url>        Loopback CDP endpoint to inspect; default http://127.0.0.1:9250
  --output <path>         Optional JSON report path
  --replace               Replace an existing output file atomically
  --online-snapshot      Managed queue probe: use SQLite's consistent online backup
  -h, --help              Show this help

This command never launches/restarts QwenWork, changes a project/model/permission,
or sends a prompt. UI controls are intentionally not inspected without a desktop slot.
`;
}

export function parseProbeArgs(argv) {
  const output = {
    appPath: "",
    sessionDb: defaultQwenWorkSessionDatabase(homedir()),
    traceRoot: join(homedir(), ".qwenworkcn"),
    endpoint: "http://127.0.0.1:9250",
    output: "",
    replace: false,
    onlineSnapshot: false,
    help: false,
  };
  const valued = new Map([
    ["--app-path", "appPath"],
    ["--session-db", "sessionDb"],
    ["--trace-root", "traceRoot"],
    ["--endpoint", "endpoint"],
    ["--output", "output"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") output.help = true;
    else if (arg === "--replace") output.replace = true;
    else if (arg === "--online-snapshot") output.onlineSnapshot = true;
    else {
      const key = valued.get(arg);
      if (!key) throw new Error(`unknown option: ${arg}`);
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} requires a value`);
      output[key] = value;
      index += 1;
    }
  }
  const endpoint = new URL(output.endpoint);
  if (!new Set(["127.0.0.1", "localhost", "::1"]).has(endpoint.hostname)) {
    throw new Error("--endpoint must use a loopback host");
  }
  output.endpoint = endpoint.origin;
  output.sessionDb = resolve(output.sessionDb);
  output.traceRoot = resolve(output.traceRoot);
  if (output.output) output.output = resolve(output.output);
  return output;
}

async function countTraceFiles(root) {
  const pending = [root];
  let transcriptFileCount = 0;
  let segmentFileCount = 0;
  let inspectedFileCount = 0;
  const transcriptVersions = new Set();
  const warnings = [];
  while (pending.length) {
    const current = pending.pop();
    const entries = await readdir(current, { withFileTypes: true });
    for (const entry of entries) {
      const path = join(current, entry.name);
      if (entry.isSymbolicLink()) {
        warnings.push("TRACE_SYMBOLIC_LINK_SKIPPED");
        continue;
      }
      if (entry.isDirectory()) {
        pending.push(path);
        continue;
      }
      if (!entry.isFile() || !entry.name.endsWith(".jsonl")) continue;
      inspectedFileCount += 1;
      if (inspectedFileCount > MAX_DISCOVERY_FILES) throw new Error("QWENWORK_TRACE_FILE_LIMIT_EXCEEDED");
      if (path.includes(`${join(root, "projects")}/`)) {
        transcriptFileCount += 1;
        const info = await lstat(path);
        if (info.size > MAX_TRANSCRIPT_BYTES) {
          warnings.push("TRANSCRIPT_TOO_LARGE_FOR_VERSION_INSPECTION");
          continue;
        }
        const lines = (await readFile(path, "utf8")).split(/\r?\n/u).filter(Boolean);
        for (const line of lines) {
          try {
            const row = JSON.parse(line);
            if (typeof row.version === "string" && row.version) transcriptVersions.add(row.version);
          } catch {
            warnings.push("TRANSCRIPT_JSON_LINE_INVALID");
          }
        }
      } else if (path.includes(`${join(root, "logs", "sessions")}/`) && path.includes("/segments/")) {
        segmentFileCount += 1;
      }
    }
  }
  return {
    root_exists: true,
    transcript_file_count: transcriptFileCount,
    segment_file_count: segmentFileCount,
    discovered_jsonl_count: inspectedFileCount,
    transcript_versions: [...transcriptVersions].sort(),
    warnings: [...new Set(warnings)],
  };
}

export async function inspectQwenTraceMetadata(traceRoot) {
  const info = await lstat(traceRoot);
  if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("QWENWORK_TRACE_ROOT_INVALID");
  return countTraceFiles(traceRoot);
}

export async function inspectQwenProcess(executablePath, overrides = {}) {
  const capture = overrides.runCapture || runCapture;
  const result = await capture(
    "/bin/ps",
    ["-axo", "pid=,ppid=,lstart=,command="],
    { capture: true, allowFailure: true },
  );
  const rows = result.code === 0 ? result.stdout.split(/\r?\n/u) : [];
  const matches = rows.filter((line) => line.includes(executablePath) && !/(?:^|\s)--type=/u.test(line));
  const processes = matches.map((line) => {
    const pid = Number(line.trim().match(/^(\d+)/u)?.[1]);
    return { pid: Number.isInteger(pid) && pid > 0 ? pid : null, executable_path: executablePath };
  }).filter((entry) => entry.pid != null);
  return {
    running: processes.length > 0,
    unique_main_process: processes.length === 1,
    process_count: processes.length,
    processes,
  };
}

export async function inspectLoopbackEndpoint(endpoint, overrides = {}) {
  const request = overrides.fetch || fetch;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await request(`${endpoint}/json/version`, { signal: controller.signal });
    if (!response.ok) return { ready: false, status: response.status, browser_identity_present: false };
    const payload = await response.json();
    return {
      ready: Boolean(payload.webSocketDebuggerUrl || payload.Browser),
      status: response.status,
      browser_identity_present: Boolean(payload.Browser),
    };
  } catch {
    return { ready: false, status: null, browser_identity_present: false };
  } finally {
    clearTimeout(timer);
  }
}

async function inspectArchitecture(executablePath, overrides = {}) {
  const capture = overrides.runCapture || runCapture;
  const result = await capture("/usr/bin/file", [executablePath], { capture: true, allowFailure: true });
  const value = String(result.stdout || "");
  const architectures = ["arm64", "x86_64"].filter((architecture) => value.includes(architecture));
  return { architectures, universal: architectures.length > 1 };
}

export async function buildReadOnlyProbe(config, overrides = {}) {
  const discover = overrides.discoverDesktopApp || discoverDesktopApp;
  const inspectTrace = overrides.inspectTrace || inspectQwenTraceMetadata;
  const inspectDatabase = overrides.inspectDatabase || inspectQwenSessionDatabase;
  const inspectRuntime = overrides.inspectRuntime || inspectDriverRuntimeIdentity;
  const inspectProcess = overrides.inspectProcess || inspectQwenProcess;
  const inspectEndpoint = overrides.inspectEndpoint || inspectLoopbackEndpoint;
  const inspectExecutable = overrides.inspectArchitecture || inspectArchitecture;

  const discovery = await discover({
    profile: QWENWORK_APP_PROFILE,
    requestedPath: config.appPath || "",
    endpoint: null,
    platform: "darwin",
  });
  const [trace, database, processInfo, endpoint, architecture] = await Promise.all([
    inspectTrace(config.traceRoot),
    inspectDatabase(config.sessionDb, { consistentOnlineBackup: config.onlineSnapshot === true }),
    inspectProcess(discovery.executable_path),
    inspectEndpoint(config.endpoint),
    inspectExecutable(discovery.executable_path),
  ]);
  const runtime = await inspectRuntime({
    appPath: discovery.path,
    clientVersion: discovery.version,
    transcriptVersions: trace.transcript_versions,
    platform: "darwin",
  });
  const normalizationProfile = matchDriverRuntimeProfile(runtime);
  const warnings = [...trace.warnings];
  if (!normalizationProfile) warnings.push("QWENWORK_RUNTIME_PROFILE_UNVERIFIED");
  if (database.active_or_pending_count > 0) warnings.push("QWENWORK_ACTIVE_SESSION_PRESENT");
  if (!endpoint.ready) warnings.push("QWENWORK_CDP_NOT_AVAILABLE");
  return {
    schema_version: QWENWORK_PROBE_SCHEMA,
    driver: {
      id: "qwenwork",
      version: QWENWORK_GENERAL_DRIVER_VERSION,
      harness: "qwenwork",
      platform: "macos",
      mode: "read-only-native-probe",
    },
    probed_at: new Date().toISOString(),
    ready_for_read_only_mapping: Boolean(
      discovery.identity_verified
      && database.readable
      && database.quick_check === "ok"
      && trace.root_exists
    ),
    ready_for_automated_execution: false,
    execution_blockers: [
      "desktop-exclusive-slot-not-assigned",
      "ui-controls-not-inspected-by-read-only-probe",
      "submit-resume-live-smoke-not-run",
      "formal-collect-awaits-common-cb-b",
    ],
    app: {
      path: discovery.path,
      executable_path: discovery.executable_path,
      discovery_source: discovery.source,
      identity_verified: discovery.identity_verified,
      bundle_id: discovery.bundle_id,
      version: discovery.version,
      architecture,
      process: processInfo,
      cdp: endpoint,
    },
    native_state: {
      session_database: config.sessionDb,
      database,
      trace,
    },
    runtime: {
      identity: runtime,
      normalization_profile: normalizationProfile,
      token_metrics_admission: normalizationProfile ? "profile-matched" : "unverified-null",
    },
    warnings: [...new Set(warnings)],
    operations_performed: [
      "application-discovery",
      "process-list-read",
      "loopback-cdp-status-read",
      "sqlite-snapshot-read",
      "trace-metadata-read",
      "runtime-identity-read",
    ],
    operations_not_performed: [
      "launch-or-restart-client",
      "focus-or-change-ui",
      "select-project-or-workspace",
      "change-model-or-permissions",
      "send-prompt",
      "stop-session",
    ],
  };
}

async function writeJsonAtomic(path, value, replace) {
  await mkdir(dirname(path), { recursive: true });
  if (!replace) {
    await access(path).then(() => { throw new Error(`output already exists: ${path}`); }).catch((error) => {
      if (error?.code !== "ENOENT") throw error;
    });
  }
  const temporary = `${path}.tmp-${process.pid}`;
  try {
    await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
    await rename(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

export async function main(argv) {
  const args = parseProbeArgs(argv);
  if (args.help) {
    process.stdout.write(usage());
    return null;
  }
  const report = await buildReadOnlyProbe(args);
  if (args.output) await writeJsonAtomic(args.output, report, args.replace);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  return report;
}

const entryPath = process.argv[1] ? await realpath(process.argv[1]).catch(() => null) : null;
const isMain = entryPath === await realpath(fileURLToPath(import.meta.url));
if (isMain) {
  main(process.argv.slice(2)).catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
    process.exitCode = 1;
  });
}
