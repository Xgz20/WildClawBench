import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  clickNewTask,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs";
import {
  withStateSnapshot,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs";
import {
  EXECUTION_RECORD_SCHEMA,
  classifyNativeState,
  executeSingleTask,
  isBlockingActiveSession,
  parseArgs,
  selectRouteBoundSession,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs";

const TASK_ID = "02_Code_Intelligence_task_001_temperature_cli_fix";

class FakeElement {
  constructor(text = "") {
    this.innerText = text;
    this.textContent = text;
    this.clickCount = 0;
  }

  getBoundingClientRect() {
    return { width: 20, height: 20 };
  }

  click() {
    this.clickCount += 1;
  }
}

async function fixture() {
  const unitRoot = await mkdtemp(join(tmpdir(), "general-e2e-execute-test-"));
  const candidateWorkspace = join(unitRoot, "execution", "tasks", TASK_ID, "workspace");
  const controlRoot = join(unitRoot, ".general-e2e", "execution", TASK_ID);
  await mkdir(candidateWorkspace, { recursive: true });
  return {
    unitRoot,
    controlRoot,
    stateFile: join(controlRoot, "automation-state.json"),
    recordFile: join(controlRoot, "execution-record.json"),
    finalResponseFile: join(controlRoot, "final-response.md"),
    candidateWorkspace,
    promptPath: join(unitRoot, "execution", "tasks", TASK_ID, "PROMPT.md"),
    prompt: "请修复温度换算程序。",
    promptSha256: "a".repeat(64),
    taskRoot: join(unitRoot, "execution", "tasks", TASK_ID),
    task: { task_id: TASK_ID, timeout_seconds: 300 },
    manifest: {
      batch_id: "general-g2-02-test",
      unit_id: "astronstudio-macos",
      dataset: { id: "general-custom60-v1", digest: "b".repeat(64) },
      unit: {
        harness: { id: "astronstudio", platform: "macos-x86-64", version: "3.3.1" },
        model: { requested_id: "GLM-5.2", reasoning_effort: "high" },
        execution_mode: "automatic",
      },
    },
    runConfigPath: join(unitRoot, "run-config.json"),
    runConfig: {
      config_digest: "c".repeat(64),
      harness: { client_version: "3.3.1" },
      control: { endpoint: "http://127.0.0.1:9240" },
      tested_model: {
        display_name: "GLM-5.2",
        reasoning_display: "High",
        permission_display: "完全访问",
      },
    },
    stateDatabase: join(unitRoot, "state.sqlite"),
    endpoint: "http://127.0.0.1:9240",
    appPath: "/Applications/AStudio.app",
    expectedModel: "GLM-5.2",
    expectedReasoning: "High",
    expectedPermission: "完全访问",
    runTimeoutSeconds: 300,
    timeoutMs: 100,
    pollIntervalMs: 1,
    identityTimeoutMs: 120_000,
    resume: false,
    detachAfterSubmit: false,
    observeOnce: false,
  };
}

function nativeSession(state = "running") {
  return {
    thread_id: "thread-1",
    turn_id: "turn-1",
    latest_turn_id: "turn-1",
    session_id: "provider-session-1",
    cwd: null,
    status: state === "completed" ? "completed" : "running",
    turn_state: state,
    session_status: state === "completed" ? "ready" : "running",
    active_turn_id: state === "completed" ? null : "turn-1",
    updated_at_ms: state === "completed" ? 3 : 2,
    error: null,
  };
}

function probeReport(config) {
  return {
    ready: true,
    failed_checks: [],
    state_database: { active_or_pending_session_count: 0 },
    frozen_run_config: {
      harness: { client_version: config.runConfig.harness.client_version },
      control: { endpoint: config.endpoint },
      tested_model: { ...config.runConfig.tested_model },
    },
  };
}

function commonDependencies(config, sessions, clickCounter) {
  const client = { close() {} };
  let queryIndex = 0;
  let clock = Date.parse("2026-09-17T15:00:00.000Z");
  return {
    probeAstronStudio: async () => probeReport(config),
    discoverMainTarget: async () => ({ webSocketDebuggerUrl: "ws://page" }),
    connectCdp: async () => client,
    prepareExecutionUi: async () => ({
      task: { thread_id: "thread-1" },
      workspace: { method: "exact-path-selection", path: config.candidateWorkspace },
      ui: { model: "GLM-5.2", reasoning: "High", permission: "完全访问" },
    }),
    fillPrompt: async () => ({ editor_count: 1, matches: true }),
    clickSend: async () => {
      clickCounter.count += 1;
      return { clicked: true, count: 1, thread_id: "thread-1" };
    },
    currentThreadId: async () => "thread-1",
    queryNativeSessions: async () => {
      const value = sessions[Math.min(queryIndex, sessions.length - 1)];
      queryIndex += 1;
      return value.map((item) => ({ ...item, cwd: config.candidateWorkspace }));
    },
    queryFinalResponse: async () => "已经完成温度换算程序修复。",
    sleep: async () => {},
    now: () => {
      const value = new Date(clock).toISOString();
      clock += 1_000;
      return value;
    },
    nowMilliseconds: () => clock,
  };
}

test("CLI requires resume for observation and keeps identity timeout bounded", () => {
  assert.throws(() => parseArgs(["--observe-once"]), /--observe-once/u);
  assert.throws(
    () => parseArgs([
      "--unit-root", "/tmp/unit",
      "--task-id", TASK_ID,
      "--run-config", "/tmp/config.json",
      "--identity-timeout-ms", "119999",
    ]),
    /120000/u,
  );
  assert.equal(parseArgs([
    "--unit-root", "/tmp/unit",
    "--task-id", TASK_ID,
    "--run-config", "/tmp/config.json",
    "--resume",
    "--observe-once",
  ]).observeOnce, true);
  assert.equal(parseArgs([
    "--unit-root", "/tmp/unit",
    "--task-id", TASK_ID,
    "--run-config", "/tmp/config.json",
    "--detach-after-submit",
    "--managed-run-slots", "8",
  ]).managedRunSlots, 8);
  assert.throws(() => parseArgs([
    "--unit-root", "/tmp/unit",
    "--task-id", TASK_ID,
    "--run-config", "/tmp/config.json",
    "--detach-after-submit",
    "--managed-run-slots", "9",
  ]), /1–8/u);
});

test("managed dispatch rejects an active session outside the frozen queue", async () => {
  const config = await fixture();
  const clickCounter = { count: 0 };
  try {
    const dependencies = commonDependencies(
      config,
      [[{ ...nativeSession("running"), session_id: "foreign-session", thread_id: "foreign-thread" }]],
      clickCounter,
    );
    await assert.rejects(
      executeSingleTask({
        ...config,
        detachAfterSubmit: true,
        managedRunSlots: 3,
        allowedActiveSessionIds: ["registered-session"],
      }, dependencies),
      /不属于当前队列的活动 session：foreign-session/u,
    );
    assert.equal(clickCounter.count, 0);
  } finally {
    await rm(config.unitRoot, { recursive: true, force: true });
  }
});

test("global new-task action wins over many per-workspace new-thread actions", async () => {
  const globalNewTask = new FakeElement("新建任务");
  const workspaceActions = Array.from({ length: 50 }, () => new FakeElement());
  const context = {
    Element: FakeElement,
    getComputedStyle: () => ({ visibility: "visible", display: "flex" }),
    location: { hash: "#/existing-thread" },
    document: {
      querySelectorAll(selector) {
        if (selector === "button") return [globalNewTask, ...workspaceActions];
        if (selector === 'button[data-testid="new-thread-button"]') return workspaceActions;
        return [];
      },
    },
  };
  const client = {
    async evaluate(source) {
      return Function(...Object.keys(context), `return ${source}`)(...Object.values(context));
    },
  };

  assert.deepEqual(await clickNewTask(client), { clicked: true, count: 1 });
  assert.equal(globalNewTask.clickCount, 1);
  assert.equal(workspaceActions.reduce((total, item) => total + item.clickCount, 0), 0);
});

test("state snapshot retries with backoff after an inconsistent copy", async () => {
  const root = await mkdtemp(join(tmpdir(), "general-e2e-state-retry-test-"));
  const source = join(root, "state.sqlite");
  const waits = [];
  let queryCount = 0;
  class FakeDatabaseSync {
    prepare(sql) {
      assert.equal(sql, "PRAGMA quick_check;");
      return {
        all() {
          queryCount += 1;
          return [{ quick_check: queryCount === 1 ? "database disk image is malformed" : "ok" }];
        },
      };
    }

    close() {}
  }
  const sqliteModule = { DatabaseSync: FakeDatabaseSync };
  try {
    await writeFile(source, "database placeholder", "utf8");
    const value = await withStateSnapshot(
      source,
      (snapshot) => readFile(snapshot, "utf8"),
      {
        attempts: 2,
        loadNodeSqlite: async () => sqliteModule,
        sleep: async (milliseconds) => waits.push(milliseconds),
      },
    );
    assert.equal(value, "database placeholder");
    assert.equal(queryCount, 2);
    assert.deepEqual(waits, [100]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("route binding requires exact cwd plus thread turn and provider session", () => {
  const state = {
    send: { pre_send_route_thread_id: "thread-1", post_send_route_thread_id: "thread-1" },
    session: { baseline: [] },
  };
  const ready = { ...nativeSession(), cwd: "/tmp/workspace" };
  assert.equal(
    selectRouteBoundSession([ready], state, "/tmp/workspace", "thread-1").session.session_id,
    "provider-session-1",
  );
  assert.equal(
    selectRouteBoundSession([{ ...ready, cwd: "/tmp/other" }], state, "/tmp/workspace", "thread-1").session,
    null,
  );
  assert.equal(
    selectRouteBoundSession([{ ...ready, session_id: null }], state, "/tmp/workspace", "thread-1").session,
    null,
  );
});

test("a completed native turn is terminal even when the task only returns prose", () => {
  assert.deepEqual(
    classifyNativeState({ turn_state: "completed", status: "ready", active_turn_id: null }),
    { kind: "completed", businessStatus: "completed" },
  );
});

test("managed dispatch ignores stale ready sessions without an active turn", () => {
  assert.equal(isBlockingActiveSession({ status: "ready", active_turn_id: null }), false);
  assert.equal(isBlockingActiveSession({ status: "created", active_turn_id: null }), false);
  assert.equal(isBlockingActiveSession({ status: "running", active_turn_id: null }), true);
  assert.equal(isBlockingActiveSession({ status: "ready", active_turn_id: "turn-active" }), true);
  assert.equal(isBlockingActiveSession({ status: "needs_attention", active_turn_id: null }), true);
});

test("fresh execution dispatches exactly once and binds all native identities", async () => {
  const config = await fixture();
  const clickCounter = { count: 0 };
  try {
    const dependencies = commonDependencies(
      config,
      [[], [nativeSession("running")], [nativeSession("completed")]],
      clickCounter,
    );
    const result = await executeSingleTask(config, dependencies);
    assert.equal(result.phase, "COMPLETED");
    assert.equal(clickCounter.count, 1);
    assert.equal(result.send.dispatch_attempt_count, 1);
    assert.equal(result.prompt.send_status, "sent");
    assert.deepEqual(
      {
        thread_id: result.session.thread_id,
        turn_id: result.session.turn_id,
        session_id: result.session.session_id,
        cwd: result.session.cwd,
        verified: result.session.verified,
      },
      {
        thread_id: "thread-1",
        turn_id: "turn-1",
        session_id: "provider-session-1",
        cwd: config.candidateWorkspace,
        verified: true,
      },
    );
    const record = JSON.parse(await readFile(config.recordFile, "utf8"));
    assert.equal(record.schema_id, EXECUTION_RECORD_SCHEMA);
    assert.equal(record.phase, "COMPLETED");
    assert.equal(record.execution.business_status, "completed");
    assert.equal(record.evidence.completeness, "partial");
    assert.equal(record.evidence.final_response_path.endsWith("final-response.md"), true);
    assert.equal(await readFile(config.finalResponseFile, "utf8"), "已经完成温度换算程序修复。\n");
  } finally {
    await rm(config.unitRoot, { recursive: true, force: true });
  }
});

test("task timeout_seconds does not stop AstronStudio before its native terminal state", async () => {
  const config = await fixture();
  const clickCounter = { count: 0 };
  try {
    // A one-second dataset value must not become the Harness execution
    // deadline. The fake clock is already beyond it while the native turn is
    // still running, then the next observation reaches completed.
    config.task.timeout_seconds = 1;
    config.runTimeoutSeconds = 1;
    const dependencies = commonDependencies(
      config,
      [[], [nativeSession("running")], [nativeSession("running")], [nativeSession("completed")]],
      clickCounter,
    );
    dependencies.nowMilliseconds = () => Date.parse("2026-09-17T15:00:00.000Z") + 120_000;
    const result = await executeSingleTask(config, dependencies);
    assert.equal(result.phase, "COMPLETED");
    assert.equal(result.execution.business_status, "completed");
    assert.equal(result.execution.deadline_at, null);
    assert.equal(result.history.some((item) => item.event === "EXECUTION_DEADLINE_REACHED"), false);
  } finally {
    await rm(config.unitRoot, { recursive: true, force: true });
  }
});

test("resume observes the same attempt without a second prompt dispatch", async () => {
  const config = await fixture();
  const clickCounter = { count: 0 };
  try {
    const first = commonDependencies(config, [[], [nativeSession("running")]], clickCounter);
    const detached = await executeSingleTask({ ...config, detachAfterSubmit: true }, first);
    assert.equal(detached.phase, "RUNNING");
    assert.equal(clickCounter.count, 1);

    const resumedDependencies = commonDependencies(
      config,
      [[nativeSession("completed")]],
      clickCounter,
    );
    resumedDependencies.clickSend = async () => {
      throw new Error("resume must not dispatch");
    };
    const resumed = await executeSingleTask(
      { ...config, resume: true, observeOnce: true },
      resumedDependencies,
    );
    assert.equal(resumed.phase, "COMPLETED");
    assert.equal(resumed.identity.attempt_id, detached.identity.attempt_id);
    assert.equal(resumed.send.dispatch_attempt_count, 1);
    assert.equal(clickCounter.count, 1);
  } finally {
    await rm(config.unitRoot, { recursive: true, force: true });
  }
});

test("terminal observation retries a transient state snapshot failure without redispatch", async () => {
  const config = await fixture();
  const clickCounter = { count: 0 };
  try {
    const dependencies = commonDependencies(
      config,
      [[], [nativeSession("running")], [nativeSession("completed")]],
      clickCounter,
    );
    const originalQuery = dependencies.queryNativeSessions;
    let calls = 0;
    dependencies.queryNativeSessions = async () => {
      calls += 1;
      if (calls === 3) throw new Error("database disk image is malformed");
      return originalQuery();
    };

    const result = await executeSingleTask(config, dependencies);
    assert.equal(result.phase, "COMPLETED");
    assert.equal(result.send.dispatch_attempt_count, 1);
    assert.equal(clickCounter.count, 1);
    assert.equal(
      result.history.some((item) => item.event === "NATIVE_STATE_READ_RETRY"),
      true,
    );
  } finally {
    await rm(config.unitRoot, { recursive: true, force: true });
  }
});

test("an ambiguous dispatch error stops without retrying", async () => {
  const config = await fixture();
  const clickCounter = { count: 0 };
  try {
    const dependencies = commonDependencies(config, [[]], clickCounter);
    dependencies.clickSend = async () => {
      clickCounter.count += 1;
      throw new Error("transport disconnected");
    };
    let clockCalls = 0;
    dependencies.nowMilliseconds = () => {
      clockCalls += 1;
      return clockCalls === 1 ? 0 : 200_000;
    };
    const result = await executeSingleTask(config, dependencies);
    assert.equal(result.phase, "NEEDS_ATTENTION");
    assert.equal(result.prompt.send_status, "uncertain");
    assert.equal(result.send.dispatch_attempt_count, 1);
    assert.equal(clickCounter.count, 1);
    assert.equal(result.execution.error.code, "PROMPT_SEND_UNCERTAIN");
  } finally {
    await rm(config.unitRoot, { recursive: true, force: true });
  }
});
