import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";

import {
  READ_ONLY_DOM_EXPRESSION,
  RUN_CONFIG_SCHEMA,
  buildProbeReport,
  calculateRunConfigDigest,
  inspectCdp,
  inspectGui,
  inspectStateDatabase,
  parseArgs,
  probeAstronStudio,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/probe_astronstudio_macos.mjs";

function passingObservation() {
  return {
    implementation: {
      skill_name: "execute-general-e2e",
      skill_version: "0.2.0",
      implementation_status: "interface_only",
      source_revision: "1".repeat(40),
      distribution: "built-skill-package",
      components: [{ name: "desktop-runtime", version: "1.0.0", content_sha256: "b".repeat(64) }],
    },
    environment: {
      platform: "darwin",
      product_name: "macOS",
      product_version: "26.6.2",
      build_version: "25G83",
      architecture: "x86_64",
    },
    app: {
      installed: true,
      path: "/Applications/AStudio.app",
      executable_path: "/Applications/AStudio.app/Contents/MacOS/AStudio",
      bundle_id: "cn.xfyun.acode",
      version: "3.3.1",
      bundle_identity_verified: true,
    },
    process: {
      running: true,
      identity_verified: true,
      pid: 123,
      ppid: 1,
      executable_path: "/Applications/AStudio.app/Contents/MacOS/AStudio",
      started_at: "2026-09-17T09:08:13.000Z",
      command_sha256: "a".repeat(64),
      remote_debugging_port: 9240,
      listening_ports: [9240],
    },
    gui: {
      frontmost_application: "AStudio",
      screen_locked: false,
      lock_source: "ioreg.IOConsoleLocked",
      unlocked: true,
    },
    devtools_active_port: {
      path: "/tmp/DevToolsActivePort",
      exists: true,
      port: 9240,
      modified_at: "2026-09-17T09:08:14.000Z",
      valid_for_process: true,
      status: "current",
    },
    cdp: {
      ready: true,
      endpoint: "http://127.0.0.1:9240",
      endpoint_source: "process-command",
      owned_by_main_process: true,
      browser: "Chrome/140",
      protocol_version: "1.3",
      page_target_count: 1,
      page_title: "AStudio",
      page_url_scheme: "acode:",
      model: {
        value: "Spark X2.5",
        reasoning_display: "High",
        source: "cdp-visible-model-trigger",
        verified: true,
        reasoning_verified: true,
        visible_match_count: 1,
      },
      permission: {
        display: "完全访问",
        source: "cdp-visible-permission-trigger",
        verified: true,
        disabled: false,
        visible_match_count: 1,
      },
      attempts: [],
    },
    state_database: {
      path: "/tmp/state.sqlite",
      readable: true,
      source_open_mode: "copy-only",
      snapshot_backend: "node:sqlite",
      snapshot_attempts: 1,
      integrity: "ok",
      table_count: 2,
      missing_required_tables: [],
      schema_ready: true,
      latest_persisted_model: {
        provider: "acode",
        model: "spark-x2.5",
        reasoning_effort: "high",
        runtime_mode: "full-access",
        updated_at: "2026-09-17T09:08:14.000Z",
        source: "state-db-latest-updated-thread",
        current_ui_verified: false,
      },
      active_or_pending_session_count: 0,
      source_size_bytes: 1024,
      source_modified_at_before_probe: "2026-09-17T09:08:14.000Z",
      error: null,
    },
    dependencies: {
      node: { available: true, version: "v24.14.0", executable: "/usr/local/bin/node", websocket_api: true },
      python: { available: true, version: "Python 3.8.3", command: "python3", error: null },
      sqlite: { node_sqlite_available: true, cli: { available: true } },
      docker: { available: true, version: "Docker version 29.6.1", command: "docker", error: null },
      codex: { available: true, version: "codex-cli 0.145.0", command: "codex", error: null },
      required_for_probe: { node: true, state_database_backend: true },
      recorded_for_later_stages: ["python", "docker", "codex"],
    },
  };
}

test("a complete read-only observation freezes a single-slot run config", () => {
  const report = buildProbeReport(passingObservation(), "2026-09-17T10:00:00.000Z");
  assert.equal(report.status, "PASS");
  assert.equal(report.ready, true);
  assert.deepEqual(report.failed_checks, []);
  assert.equal(report.frozen_run_config.schema_version, RUN_CONFIG_SCHEMA);
  assert.equal(report.frozen_run_config.control.execution_concurrency, 1);
  assert.equal(report.frozen_run_config.frozen_at, "2026-09-17T10:00:00.000Z");
  assert.equal(report.frozen_run_config.tested_model.display_name, "Spark X2.5");
  assert.match(report.frozen_run_config.config_digest, /^[0-9a-f]{64}$/u);
  assert.equal(
    calculateRunConfigDigest(report.frozen_run_config),
    report.frozen_run_config.config_digest,
  );
  const changed = structuredClone(report.frozen_run_config);
  changed.tested_model.display_name = "Another model";
  assert.notEqual(calculateRunConfigDigest(changed), report.frozen_run_config.config_digest);
  assert.equal(report.action_audit.prompt_send_attempted, false);
  assert.equal(report.action_audit.app_restart_attempted, false);
});

test("an unknown macOS lock state fails closed", async () => {
  const runCommand = async (command) => {
    if (command === "/usr/bin/osascript") {
      return { code: 0, stdout: "AStudio\n", stderr: "" };
    }
    return { code: 1, stdout: "", stderr: "ioreg unavailable" };
  };
  const result = await inspectGui(runCommand);
  assert.equal(result.frontmost_application, "AStudio");
  assert.equal(result.screen_locked, null);
  assert.equal(result.lock_source, null);
  assert.equal(result.unlocked, false);
});

test("a persisted model cannot replace current UI model and reasoning readback", () => {
  const observation = passingObservation();
  observation.cdp = {
    ...observation.cdp,
    ready: false,
    endpoint: null,
    owned_by_main_process: false,
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
  };
  const report = buildProbeReport(observation);
  assert.equal(report.status, "NEEDS_ATTENTION");
  assert.equal(report.frozen_run_config, null);
  assert(report.failed_checks.includes("CDP_NOT_READY"));
  assert(report.failed_checks.includes("MODEL_NOT_READ_FROM_UI"));
  assert(report.failed_checks.includes("REASONING_NOT_READ_FROM_UI"));
});

test("the CDP expression only reads visible model and permission controls", () => {
  assert.match(READ_ONLY_DOM_EXPRESSION, /querySelectorAll/u);
  assert.doesNotMatch(READ_ONLY_DOM_EXPRESSION, /\.click\s*\(/u);
  assert.doesNotMatch(READ_ONLY_DOM_EXPRESSION, /composer|submit|send message|发送消息/iu);
  assert.doesNotMatch(READ_ONLY_DOM_EXPRESSION, /innerHTML\s*=/u);
});

test("the CLI rejects non-loopback and credential-bearing CDP endpoints", () => {
  assert.throws(() => parseArgs(["--endpoint", "https://127.0.0.1:9240"]), /本机 http 根地址/u);
  assert.throws(() => parseArgs(["--endpoint", "http://192.0.2.1:9240"]), /本机 http 根地址/u);
  assert.throws(() => parseArgs(["--endpoint", "http://user:pass@127.0.0.1:9240"]), /本机 http 根地址/u);
  assert.equal(
    parseArgs(["--endpoint", "http://127.0.0.1:9240/"]).endpoint,
    "http://127.0.0.1:9240",
  );
  assert.equal(
    parseArgs(["--endpoint", "http://127.0.0.1:9240"]).endpointExplicit,
    true,
  );
});

test("CDP must be owned by the main process and expose an AStudio page", async () => {
  const config = parseArgs(["--endpoint", "http://127.0.0.1:9240"]);
  const processInfo = { remote_debugging_port: 9240 };
  const activePort = { valid_for_process: true, port: 9240 };
  const fetchImpl = async (url) => ({
    ok: true,
    json: async () => url.endsWith("/json/version")
      ? { Browser: "Chrome/140", webSocketDebuggerUrl: "ws://browser" }
      : [
        { type: "page", title: "Voice HUD", url: "acode://app/voice-hud.html", webSocketDebuggerUrl: "ws://voice" },
        { type: "page", title: "AStudio", url: "acode://app/index.html#/thread", webSocketDebuggerUrl: "ws://page" },
      ],
  });
  const evaluateDom = async () => ({
    model_count: 1,
    model_text: "Spark X2.5\nHigh",
    permission_count: 1,
    permission_text: "完全访问",
    permission_disabled: false,
  });
  const ready = await inspectCdp(config, processInfo, activePort, [9240], {
    fetchImpl,
    evaluateDom,
  });
  assert.equal(ready.ready, true);
  assert.equal(ready.model.value, "Spark X2.5");
  assert.equal(ready.model.reasoning_display, "High");

  const wrongOwner = await inspectCdp(config, processInfo, activePort, [], {
    fetchImpl,
    evaluateDom,
  });
  assert.equal(wrongOwner.ready, false);
  assert.match(wrongOwner.attempts[0].error, /不属于/u);

  const noAStudioPage = await inspectCdp(config, processInfo, activePort, [9240], {
    fetchImpl: async (url) => ({
      ok: true,
      json: async () => url.endsWith("/json/version")
        ? { Browser: "Chrome/140", webSocketDebuggerUrl: "ws://browser" }
        : [{ type: "page", title: "Example", url: "https://example.invalid/", webSocketDebuggerUrl: "ws://page" }],
    }),
    evaluateDom,
  });
  assert.equal(noAStudioPage.ready, false);
  assert.match(noAStudioPage.attempts[0].error, /AstronStudio 主页面数量异常/u);
});

test("the state database is copied and queried without opening the source for writes", async () => {
  const root = await mkdtemp(join(tmpdir(), "general-e2e-probe-test-"));
  const databasePath = join(root, "state.sqlite");
  try {
    const database = new DatabaseSync(databasePath);
    database.exec(`
CREATE TABLE projection_thread_sessions(
  thread_id TEXT PRIMARY KEY,
  active_turn_id TEXT,
  status TEXT
);
CREATE TABLE projection_pending_interactions(thread_id TEXT, status TEXT);
CREATE TABLE provider_runtime_open_turns(thread_id TEXT);
CREATE TABLE projection_threads(
  thread_id TEXT PRIMARY KEY,
  model_selection_json TEXT,
  runtime_mode TEXT,
  updated_at TEXT,
  deleted_at TEXT
);
INSERT INTO projection_threads VALUES(
  'thread-1',
  '{"provider":"acode","model":"spark-x2.5","options":{"reasoningEffort":"high"}}',
  'full-access',
  '2026-09-17T10:00:00.000Z',
  NULL
);
`);
    database.close();
    const result = await inspectStateDatabase(databasePath);
    assert.equal(result.readable, true);
    assert.equal(result.source_open_mode, "copy-only");
    assert.equal(result.integrity, "ok");
    assert.equal(result.latest_persisted_model.model, "spark-x2.5");
    assert.equal(result.latest_persisted_model.reasoning_effort, "high");
    assert.equal(result.active_or_pending_session_count, 0);
    const verify = new DatabaseSync(databasePath, { readOnly: true });
    assert.equal(verify.prepare("SELECT count(*) AS value FROM projection_threads").get().value, 1);
    verify.close();
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("probe orchestration has no mutating callback and preserves read-only audit", async () => {
  const observation = passingObservation();
  const calls = [];
  const report = await probeAstronStudio(
    {
      appPath: observation.app.path,
      stateDb: observation.state_database.path,
      endpoint: observation.cdp.endpoint,
      endpointExplicit: true,
      timeoutMs: 100,
    },
    {
      capturedAt: "2026-09-17T10:00:00.000Z",
      inspectImplementation: async () => { calls.push("implementation"); return observation.implementation; },
      inspectEnvironment: async () => { calls.push("environment"); return observation.environment; },
      inspectApp: async () => { calls.push("app"); return observation.app; },
      inspectProcess: async () => { calls.push("process"); return observation.process; },
      inspectGui: async () => { calls.push("gui"); return observation.gui; },
      listeningPorts: async () => { calls.push("ports"); return [9240]; },
      inspectActivePortFile: async () => { calls.push("active-port"); return observation.devtools_active_port; },
      inspectStateDatabase: async () => { calls.push("database"); return observation.state_database; },
      inspectDependencies: async () => { calls.push("dependencies"); return observation.dependencies; },
      inspectCdp: async () => { calls.push("cdp-read"); return observation.cdp; },
    },
  );
  assert.deepEqual(calls.sort(), [
    "active-port",
    "app",
    "cdp-read",
    "database",
    "dependencies",
    "environment",
    "gui",
    "implementation",
    "ports",
    "process",
  ]);
  assert.equal(report.ready, true);
  assert.equal(report.action_audit.ui_click_attempted, false);
  assert.equal(report.action_audit.composer_access_attempted, false);
  assert.equal(report.action_audit.prompt_send_attempted, false);
});
