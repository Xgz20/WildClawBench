import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import vm from "node:vm";

import {
  clickNewTask,
  clickSidebarToggle,
  clickProjectsTab,
  clickSend,
  ensureSendTargetReady,
  fillPrompt,
  renderExpectedPrompt,
  shouldOpenExactProjectConversation,
  reloadIdleProjectProjection,
  waitForExactProjectIdentity,
  createFreshTask,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs";
import {
  withStateSnapshot,
  STATE_SNAPSHOT_TABLES,
  queryPristineThread,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs";
import {
  EXECUTION_RECORD_SCHEMA,
  classifyNativeState,
  executeSingleTask,
  isBlockingActiveSession,
  isRetryablePreSendFailure,
  parseArgs,
  selectRouteBoundSession,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/execute_astronstudio_macos.mjs";

const TASK_ID = "02_Code_Intelligence_task_001_temperature_cli_fix";

test("General sidebar recovery recognizes 3.5 and rejects duplicate toggles", async () => {
  let clicked=0;
  class Element { closest(){return null;} getBoundingClientRect(){return {width:10,height:10};} }
  const button=Object.assign(new Element(),{getAttribute:()=>"Toggle Sidebar",click:()=>clicked++});
  let buttons=[button];
  const client={evaluate:expression=>vm.runInNewContext(expression,{Element,getComputedStyle:()=>({visibility:"visible",display:"block"}),document:{querySelectorAll:()=>buttons}})};
  assert.equal((await clickSidebarToggle(client)).clicked,true);assert.equal(clicked,1);
  buttons=[button,button];assert.equal((await clickSidebarToggle(client)).clicked,false);assert.equal(clicked,1);
});

test("General sidebar recovery prefers the reachable task action over the seam rail", async () => {
  let actionClicks=0,railClicks=0;
  class Element { closest(){return null;} contains(){return false;} getBoundingClientRect(){return {x:10,y:10,width:20,height:20};} }
  const make=(label,rail,click)=>Object.assign(new Element(),{getAttribute:name=>name==='aria-label'?label:name==='data-sidebar'&&rail?'rail':null,click});
  const action=make('切换任务侧边栏',false,()=>actionClicks++);
  const covered=make('切换任务侧边栏',false,()=>{throw new Error('covered action');});
  const rail=make('Toggle Sidebar',true,()=>railClicks++);
  rail.getBoundingClientRect=()=>({x:30,y:10,width:20,height:20});
  covered.getBoundingClientRect=()=>({x:100,y:10,width:20,height:20});
  let buttons=[covered,rail,action];
  const client={evaluate:expression=>vm.runInNewContext(expression,{Element,getComputedStyle:()=>({visibility:'visible',display:'block'}),document:{querySelectorAll:()=>buttons,elementFromPoint:x=>x===110?{}:x===40?rail:action}})};
  assert.equal((await clickSidebarToggle(client)).clicked,true);assert.equal(actionClicks,1);assert.equal(railClicks,0);
  buttons=[action,action,rail];assert.equal((await clickSidebarToggle(client)).clicked,false);assert.equal(actionClicks,1);
});

test("project creation clicks the unique sidebar tab and never a same-name project group", async () => {
  let tabClicks = 0, groupClicks = 0;
  class Element {
    closest() { return null; }
    getBoundingClientRect() { return { width: 10, height: 10 }; }
  }
  const tab = Object.assign(new Element(), { innerText: "项目", click: () => tabClicks++ });
  const group = Object.assign(new Element(), { innerText: "项目", click: () => groupClicks++ });
  const picker = Object.assign(new Element(), { querySelectorAll: () => [tab] });
  const client = { evaluate: expression => vm.runInNewContext(expression, {
    Element, getComputedStyle: () => ({ visibility: "visible", display: "block" }),
    document: { querySelectorAll: selector => selector === ".sidebar-segmented-picker" ? [picker] : [tab, group] },
  }) };
  assert.equal((await clickProjectsTab(client)).clicked, true);
  assert.equal(tabClicks, 1); assert.equal(groupClicks, 0);
  picker.querySelectorAll = () => [tab, Object.assign(new Element(), { innerText: "Projects", click: () => tabClicks++ })];
  await assert.rejects(clickProjectsTab(client), /不唯一/u);
  assert.equal(tabClicks, 1); assert.equal(groupClicks, 0);
});

test("workspace trigger without a visible absolute path uses exact native project routing", () => {
  assert.equal(shouldOpenExactProjectConversation({ count: 0, path: null }), true);
  assert.equal(shouldOpenExactProjectConversation({ count: 1, path: null }), true);
  assert.equal(shouldOpenExactProjectConversation({ count: 1, path: "/tmp/workspace" }), false);
  assert.equal(shouldOpenExactProjectConversation({ count: 2, path: null }), false);
});

test("an empty composer on a previous conversation is not a fresh task route", async () => {
  let reads = 0;
  const client = { evaluate: async (expression) => {
    if (expression.includes("buttons[0].click()")) return { clicked: true, count: 1 };
    return { thread_id: ++reads < 3 ? "previous-conversation" : "new-conversation",
      editor_count: 1, editor_text: "" };
  } };
  const result = await createFreshTask(client, 1_000);
  assert.equal(result.thread_id, "new-conversation");
});

test("reusable blank routes require a native thread without messages, turns, sessions or pending interactions", async () => {
  const root = await mkdtemp(join(tmpdir(), "general-pristine-thread-"));
  const file = join(root, "state.sqlite");
  const { DatabaseSync } = await import("node:sqlite");
  const db = new DatabaseSync(file);
  try {
    db.exec(`CREATE TABLE projection_threads(thread_id TEXT, latest_turn_id TEXT, deleted_at TEXT);
CREATE TABLE projection_thread_messages(thread_id TEXT);
CREATE TABLE projection_turns(thread_id TEXT);
CREATE TABLE projection_thread_sessions(thread_id TEXT);
CREATE TABLE projection_pending_interactions(thread_id TEXT,status TEXT);
INSERT INTO projection_threads VALUES('empty',NULL,NULL),('old',NULL,NULL);
INSERT INTO projection_thread_messages VALUES('old');`);
    assert.equal(await queryPristineThread(file, "empty"), true);
    assert.equal(await queryPristineThread(file, "old"), false);
    assert.equal(await queryPristineThread(file, "missing"), false);
    db.exec("INSERT INTO projection_pending_interactions VALUES('empty','pending');");
    assert.equal(await queryPristineThread(file, "empty"), false);
  } finally { db.close(); await rm(root, { recursive: true, force: true }); }
});

test("project registration waits for its exact native identity and rejects ambiguity", async () => {
  let reads = 0;
  assert.equal(await waitForExactProjectIdentity("/db", "/workspace", 1_000, {
    queryExactProjectsForWorkspace: async () => ++reads === 1 ? [] : [{ project_id: "exact-project" }],
  }), "exact-project");
  await assert.rejects(waitForExactProjectIdentity("/db", "/workspace", 1_000, {
    queryExactProjectsForWorkspace: async () => [{ project_id: "one" }, { project_id: "two" }],
  }), /身份不唯一/u);
  await assert.rejects(waitForExactProjectIdentity("/db", "/workspace", 1, {
    queryExactProjectsForWorkspace: async () => [],
  }), /原生项目登记.*超时/u);
});

test("project projection reload requires native idle and an empty unblocked editor", async () => {
  for (const current of [
    { native: [{ status: "running" }], ui: { editor_count: 1, empty: true, dialogs: 0, stops: 0 } },
    { native: [], ui: { editor_count: 1, empty: false, dialogs: 0, stops: 0 } },
    { native: [], ui: { editor_count: 1, empty: true, dialogs: 1, stops: 0 } },
    { native: [], ui: { editor_count: 1, empty: true, dialogs: 0, stops: 1 } },
  ]) {
    const calls = [];
    const client = { evaluate: async () => current.ui, send: async (method) => calls.push(method) };
    await assert.rejects(reloadIdleProjectProjection(client, "/state.sqlite", {
      queryNativeSessions: async () => current.native,
    }), /活动任务|草稿|弹窗/u);
    assert.deepEqual(calls, []);
  }
  const calls = [];
  await reloadIdleProjectProjection({
    evaluate: async () => ({ editor_count: 1, empty: true, dialogs: 0, stops: 0 }),
    send: async (method) => calls.push(method),
  }, "/state.sqlite", { queryNativeSessions: async () => [{ status: "completed", active_turn_id: null }] });
  assert.deepEqual(calls, ["Page.reload"]);
  let reads = 0;
  let nativeReads = 0;
  const appeared = [];
  await assert.rejects(reloadIdleProjectProjection({
    evaluate: async () => ({ editor_count: ++reads === 1 ? 0 : 1, empty: true, dialogs: 0, stops: 0 }),
    send: async (method) => appeared.push(method),
  }, "/state.sqlite", { queryNativeSessions: async () => ++nativeReads === 1 ? [] : [{ status: "running" }] }),
  /刷新前出现活动任务/u);
  assert.deepEqual(appeared, []);
});

class FakeElement {
  constructor(text = "") {
    this.innerText = text;
    this.textContent = text;
    this.clickCount = 0;
  }

  getBoundingClientRect() {
    return { width: 20, height: 20 };
  }

  closest() { return null; }

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
    app: { version: config.runConfig.harness.client_version },
    cdp: { endpoint: config.endpoint },
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
      ui: { thread_id: "thread-1", model: "GLM-5.2", reasoning: "High", permission: "完全访问" },
    }),
    fillPrompt: async () => ({ editor_count: 1, matches: true }),
    ensureSendTargetReady: async () => ({ ready: true, count: 1 }),
    waitForThreadStreamLease: async ({ threadId }) => ({
      threadId, leaseId: "lease-1", admittedAt: Date.parse("2026-09-17T15:00:00Z"),
    }),
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

test("URL chips preserve full frozen links during composer readback", async () => {
  const prompt = "参考 https://flk.npc.gov.cn/detail?id=1 和 https://www.gov.cn/a";
  const chips = [
    { title: "https://flk.npc.gov.cn/detail?id=1", display: "flk.npc.gov.cn/detail?id=1" },
    { title: "https://www.gov.cn/a", display: "gov.cn/a" },
  ];
  const rendered = "参考 flk.npc.gov.cn/detail?id=1 和 gov.cn/a";
  assert.equal(renderExpectedPrompt(prompt, chips), rendered);
  assert.equal(renderExpectedPrompt(prompt, [{ title: "https://other.example/a", display: "other.example/a" }]), null);
  assert.equal(renderExpectedPrompt(prompt, [{ title: "file:///tmp/secret", display: "secret" }]), null);

  let evaluations = 0;
  const sends = [];
  const client = {
    evaluate: async () => {
      evaluations += 1;
      return evaluations === 1
        ? { ready: true, count: 1 }
        : { thread_id: "thread-1", editor_count: 1, editor_text: rendered, link_chips: chips };
    },
    send: async (...args) => sends.push(args),
  };
  const result = await fillPrompt(client, prompt, 100);
  assert.equal(result.matches, true);
  assert.equal(result.link_chip_count, 2);
  assert.equal("editor_text" in result, false);
  assert.deepEqual(sends.map(([method]) => method), ["Input.insertText"]);
});

test("composer mismatch diagnostics do not echo draft content", async () => {
  let reads = 0;
  const client = {
    evaluate: async () => reads++ === 0
      ? { ready: true, count: 1 }
      : { thread_id: "thread-1", editor_count: 1, editor_text: "PRIVATE_DRAFT_VALUE", link_chips: [] },
    send: async () => {},
  };
  await assert.rejects(
    fillPrompt(client, "expected text", 1),
    (error) => !error.message.includes("PRIVATE_DRAFT_VALUE")
      && error.message.includes("editor_length"),
  );
});

test("send uses one CDP mouse click after exact UI validation", async () => {
  const calls = [];
  let reads = 0;
  const client = {
    evaluate: async (expression) => {
      if (reads++ === 0) {
        assert.match(expression, /expectedPrompt/u);
        assert.match(expression, /expectedWorkspace/u);
        return { ready: true, count: 1, x: 14, y: 28, thread_id: "before" };
      }
      return { thread_id: "after", editor_count: 1, editor_text: "" };
    },
    send: async (method, params) => calls.push({ method, params }),
  };
  const result = await clickSend(client, "prompt", "/tmp/target-workspace");
  assert.equal(result.clicked, true);
  assert.equal(result.thread_id, "after");
  assert.deepEqual(calls.map((item) => item.params.type),
    ["mouseMoved", "mousePressed", "mouseReleased"]);
  assert.equal(calls.filter((item) => item.params.type === "mousePressed").length, 1);
});

test("unsafe send UI never dispatches a mouse event", async () => {
  const calls = [];
  const client = {
    evaluate: async () => ({
      ready: false, count: 1, prompt_matches: true,
      workspace_matches: false, dialog_count: 0,
    }),
    send: async (...args) => calls.push(args),
  };
  const result = await clickSend(client, "prompt", "/tmp/target-workspace");
  assert.equal(result.clicked, false);
  assert.equal(result.workspace_matches, false);
  assert.deepEqual(calls, []);
});

test("pre-arm check moves away from a preview card and requires an unobscured send target", async () => {
  const calls = [];
  let reads = 0;
  const client = {
    evaluate: async () => {
      reads += 1;
      return reads === 1
        ? { width: 1344, height: 810 }
        : { ready: true, count: 1, x: 1200, y: 535, thread_id: "thread-1" };
    },
    send: async (method, params) => calls.push({ method, params }),
  };
  const ready = await ensureSendTargetReady(client, "prompt", "/tmp/target-workspace");
  assert.equal(ready.ready, true);
  assert.deepEqual(calls.map(({ params }) => params.type), ["mouseMoved"]);
  assert.equal(calls[0].params.x, 806);
  assert.equal(calls[0].params.y, 100);
});

test("pre-arm check fails before mouse press when the send button remains obscured", async () => {
  const calls = [];
  const client = {
    evaluate: async (expression) => expression.includes("innerWidth")
      ? { width: 1344, height: 810 }
      : { ready: false, count: 1, reason: "send-button-obscured" },
    send: async (method, params) => calls.push({ method, params }),
  };
  await assert.rejects(
    ensureSendTargetReady(client, "prompt", "/tmp/target-workspace"),
    /send-button-obscured/u,
  );
  assert.deepEqual(calls.map(({ params }) => params.type), ["mouseMoved"]);
});

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
  const hiddenNewTask = new FakeElement("新建任务");
  hiddenNewTask.closest = () => ({ inert: true });
  const workspaceActions = Array.from({ length: 50 }, () => new FakeElement());
  const context = {
    Element: FakeElement,
    getComputedStyle: () => ({ visibility: "visible", display: "flex" }),
    location: { hash: "#/existing-thread" },
    document: {
      querySelectorAll(selector) {
        if (selector === "button") return [globalNewTask, hiddenNewTask, ...workspaceActions];
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
  assert.equal(hiddenNewTask.clickCount, 0);
  assert.equal(workspaceActions.reduce((total, item) => total + item.clickCount, 0), 0);
});

test("state snapshot retries with backoff after an inconsistent copy", async () => {
  const root = await mkdtemp(join(tmpdir(), "general-e2e-state-retry-test-"));
  const source = join(root, "state.sqlite");
  const waits = [];
  let queryCount = 0;
  class FakeDatabaseSync {
    constructor(_path, options) { assert.deepEqual(options, { readOnly: true }); }
    exec(sql) { assert.equal(sql, "PRAGMA cache_size=-65536; PRAGMA mmap_size=2147483648;"); }
    prepare(sql) {
      assert.match(sql, /^PRAGMA quick_check\("[a-z_]+"\);$/u);
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
    assert.equal(queryCount, 1 + STATE_SNAPSHOT_TABLES.length);
    assert.deepEqual(waits, [100]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("snapshot validation cannot be disabled or point at an unknown table", async () => {
  for (const tables of [[], ["unknown_table"]]) {
    await assert.rejects(withStateSnapshot("unused", () => assert.fail("operation ran"), {}, tables), /非空、已知/u);
  }
});

test("a missing queried table blocks the operation on a real SQLite snapshot", async () => {
  const { DatabaseSync } = await import("node:sqlite");
  const root = await mkdtemp(join(tmpdir(), "general-e2e-state-scope-test-"));
  try {
    const source = join(root, "state.sqlite");
    const db = new DatabaseSync(source);
    db.exec("CREATE TABLE projection_projects(project_id TEXT);");
    db.close();
    let invoked = false;
    await assert.rejects(withStateSnapshot(source, () => { invoked = true; }, { attempts: 1 }, ["projection_threads"]), /no such table/u);
    assert.equal(invoked, false);
    assert.equal(await withStateSnapshot(source, () => "checked", {}, ["projection_projects"]), "checked");
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

test("completed status waits for its bound final without freezing commentary or redispatching", async () => {
  const config=await fixture(), clicks={count:0};
  try {
    const dependencies=commonDependencies(config,[[],[nativeSession('running')],[nativeSession('completed')],[nativeSession('completed')]],clicks);
    let reads=0;
    dependencies.queryTerminalFinalResponse=async()=>++reads===1
      ? {ready:false,text:'',reason:'bound_terminal_message_not_materialized'}
      : {ready:true,text:'bound final',message_id:'final',source:'completed-turn.assistant_message_id'};
    const result=await executeSingleTask(config,dependencies);
    assert.equal(result.phase,'COMPLETED');assert.equal(clicks.count,1);assert.equal(reads,2);
    assert.ok(result.history.some(row=>row.event==='TERMINAL_FINAL_RESPONSE_PENDING'));
    assert.equal(await readFile(config.finalResponseFile,'utf8'),'bound final\n');
  } finally {await rm(config.unitRoot,{recursive:true,force:true});}
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

test("stream admission failure stops before arming a Prompt send", async () => {
  const config = await fixture();
  const clickCounter = { count: 0 };
  try {
    const dependencies = commonDependencies(config, [[]], clickCounter);
    dependencies.waitForThreadStreamLease = async () => {
      throw new Error("stream unavailable");
    };
    const result = await executeSingleTask(config, dependencies);
    assert.equal(result.phase, "FAILED");
    assert.equal(result.execution.business_status, "infrastructure_error");
    assert.equal(result.execution.error.code, "PRE_SEND_DRIVER_ERROR");
    assert.equal(result.prompt.send_status, "not_sent");
    assert.equal(result.send.dispatch_attempt_count, 0);
    assert.equal(clickCounter.count, 0);
  } finally {
    await rm(config.unitRoot, { recursive: true, force: true });
  }
});

test("obscured send target fails before persisting a send intent", async () => {
  const config = await fixture();
  const clickCounter = { count: 0 };
  try {
    const dependencies = commonDependencies(config, [[]], clickCounter);
    dependencies.ensureSendTargetReady = async () => {
      throw new Error("send-button-obscured");
    };
    const result = await executeSingleTask(config, dependencies);
    assert.equal(result.phase, "FAILED");
    assert.equal(result.execution.business_status, "infrastructure_error");
    assert.equal(result.execution.error.code, "PRE_SEND_DRIVER_ERROR");
    assert.equal(result.prompt.send_status, "not_sent");
    assert.equal(result.send.dispatch_attempt_count, 0);
    assert.equal(result.history.some((item) => item.event === "PROMPT_DISPATCH_ARMED"), false);
    assert.equal(clickCounter.count, 0);
  } finally {
    await rm(config.unitRoot, { recursive: true, force: true });
  }
});

test("explicit zero-send recovery preserves failure bytes and the attempt, and sends once", async () => {
  const config = await fixture();
  const clicks = { count: 0 };
  try {
    const first = commonDependencies(config, [[]], clicks);
    first.prepareExecutionUi = async () => { throw new Error("project projection missing"); };
    const failed = await executeSingleTask(config, first);
    const oldBytes = await readFile(config.stateFile, "utf8");
    assert.equal(isRetryablePreSendFailure(failed), true);
    const result = await executeSingleTask({ ...config, resume: true, retryPreSendFailure: true },
      commonDependencies(config, [[], [], [nativeSession()], [nativeSession("completed")]], clicks));
    assert.equal(result.identity.attempt_id, failed.identity.attempt_id);
    assert.equal(result.phase, "COMPLETED");
    assert.equal(result.send.dispatch_attempt_count, 1);
    assert.equal(clicks.count, 1);
    const audit = result.history.find((item) => item.event === "ZERO_SEND_PREPARATION_RESUMED");
    assert.equal(await readFile(join(config.unitRoot, audit.previous_state_path), "utf8"), oldBytes);
    assert.equal(result.history.some((item) => item.event === "PRE_SEND_DRIVER_ERROR"), true);
    const again = await executeSingleTask({ ...config, resume: true }, commonDependencies(config, [[]], clicks));
    assert.equal(again.phase, "COMPLETED");
    assert.equal(clicks.count, 1);
    await assert.rejects(executeSingleTask({ ...config, resume: true, retryPreSendFailure: true },
      commonDependencies(config, [[]], clicks)), /非零发送/u);
  } finally { await rm(config.unitRoot, { recursive: true, force: true }); }
});

test("zero-send recovery rejects native activity and any persisted dispatch boundary", async () => {
  const config = await fixture();
  const clicks = { count: 0 };
  try {
    const deps = commonDependencies(config, [[]], clicks);
    deps.prepareExecutionUi = async () => { throw new Error("project projection missing"); };
    const failed = await executeSingleTask(config, deps);
    const original = await readFile(config.stateFile, "utf8");
    for (const change of [
      { send: { ...failed.send, dispatch_attempt_count: 1 } },
      { send: { ...failed.send, dispatch_armed_at: "2026-09-17T15:00:00Z" } },
      { prompt: { ...failed.prompt, send_status: "uncertain" } },
      { history: [...failed.history, { event: "PROMPT_DISPATCH_ARMED" }] },
    ]) assert.equal(isRetryablePreSendFailure({ ...failed, ...change }), false);
    await assert.rejects(executeSingleTask({ ...config, resume: true, retryPreSendFailure: true },
      commonDependencies(config, [[nativeSession()]], clicks)), /原生空闲/u);
    assert.equal(await readFile(config.stateFile, "utf8"), original);
    assert.equal(clicks.count, 0);
  } finally { await rm(config.unitRoot, { recursive: true, force: true }); }
});

test("managed startup restores configuration controls only from a bound queue-owned route", async () => {
  const config = await fixture();
  config.managedRunSlots = 3;
  config.allowedActiveSessionIds = ["provider-session-1"];
  const clicks = { count: 0 };
  try {
    const deps = commonDependencies(config, [[nativeSession()], [], []], clicks);
    let probes = 0;
    let navigated = 0;
    deps.probeAstronStudio = async () => ++probes === 1 ? {
      ...probeReport(config), ready: false,
      failed_checks: ["MODEL_NOT_READ_FROM_UI", "REASONING_NOT_READ_FROM_UI", "PERMISSION_NOT_READ_FROM_UI"],
    } : probeReport(config);
    deps.createFreshTask = async () => { navigated++; };
    deps.prepareExecutionUi = async () => { throw new Error("test stops before a send"); };
    const result = await executeSingleTask(config, deps);
    assert.equal(navigated, 1);
    assert.equal(probes, 2);
    assert.equal(result.send.dispatch_attempt_count, 0);
    assert.equal(clicks.count, 0);
  } finally { await rm(config.unitRoot, { recursive: true, force: true }); }
});

test("hidden configuration controls cannot bypass physical failures or foreign sessions", async () => {
  for (const physicalFailure of [false, true]) {
    const config = await fixture();
    config.managedRunSlots = 3;
    config.allowedActiveSessionIds = ["different-session"];
    const clicks = { count: 0 };
    let navigated = 0;
    try {
      const deps = commonDependencies(config, [[nativeSession()]], clicks);
      deps.probeAstronStudio = async () => ({ ...probeReport(config), ready: false,
        failed_checks: ["MODEL_NOT_READ_FROM_UI", ...(physicalFailure ? ["STATE_DATABASE_OWNER_NOT_VERIFIED"] : [])] });
      deps.createFreshTask = async () => { navigated++; };
      await assert.rejects(executeSingleTask(config, deps), /未知活动|探针未通过/u);
      assert.equal(navigated, 0);
      assert.equal(clicks.count, 0);
    } finally { await rm(config.unitRoot, { recursive: true, force: true }); }
  }
});

test("a bound task can be observed when completed-task UI hides configuration controls", async () => {
  const config = await fixture();
  const clicks = { count: 0 };
  try {
    const started = await executeSingleTask({ ...config, detachAfterSubmit: true },
      commonDependencies(config, [[], [nativeSession()]], clicks));
    assert.equal(started.phase, "RUNNING");
    const deps = commonDependencies(config, [[nativeSession("completed")]], clicks);
    deps.probeAstronStudio = async () => ({ ...probeReport(config), ready: false,
      failed_checks: ["MODEL_NOT_READ_FROM_UI", "REASONING_NOT_READ_FROM_UI", "PERMISSION_NOT_READ_FROM_UI"] });
    const observed = await executeSingleTask({ ...config, resume: true, observeOnce: true }, deps);
    assert.equal(observed.phase, "COMPLETED");
    assert.equal(observed.identity.attempt_id, started.identity.attempt_id);
    assert.equal(clicks.count, 1);
  } finally { await rm(config.unitRoot, { recursive: true, force: true }); }
});
