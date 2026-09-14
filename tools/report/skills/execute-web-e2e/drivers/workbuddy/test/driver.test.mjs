import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, posix } from "node:path";
import test from "node:test";

import {
  AUTOMATION_SCHEMA,
  assertStateMatches,
  chooseAttemptSession,
  chooseSession,
  classifyApprovalCommand,
  classifyDomStatus,
  classifySessionStatus,
  isSubstantiveFinalResponse,
  createInitialState,
  diffSnapshots,
  parseArgs,
  resolveConfig,
  resolveExecutionIdentity,
  snapshotTree,
  updateExecutionRecord,
} from "../lib.mjs";
import {
  captureAttemptConversation,
  capturePageScreenshot,
  confirmFullAccessRiskDialog,
  ensureModel,
  hasStableConversationId,
  hasTrustedDomCompletion,
  prepareClientForNewAttempt,
  restartWorkBuddy,
  runEntrypointWithKeepAlive,
  terminalProcessCleanupTiming,
  waitForPromptSubmissionAcceptance,
  waitForFullAccessTransition,
  waitForRestartedAttemptRecovery,
  waitForUniqueVisible,
} from "../driver.mjs";

test("driver entrypoint keeps Node alive until the automation promise settles", async () => {
  const timer = {};
  let active = false;
  let cleared = null;
  const exitCode = await runEntrypointWithKeepAlive(async (args) => {
    assert.deepEqual(args, ["--fixture"]);
    assert.equal(active, true);
    await Promise.resolve();
    return 0;
  }, ["--fixture"], {
    setInterval: (callback, milliseconds) => {
      assert.equal(typeof callback, "function");
      assert.equal(milliseconds, 1_000);
      active = true;
      return timer;
    },
    clearInterval: (value) => {
      cleared = value;
      active = false;
    },
  });
  assert.equal(exitCode, 0);
  assert.equal(active, false);
  assert.equal(cleared, timer);
});

test("Windows screenshots use direct CDP capture when Electron page.screenshot hangs", async () => {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-screenshot-"));
  const path = join(root, "capture.png");
  let detached = false;
  const page = {
    context: () => ({
      newCDPSession: async () => ({
        send: async (method, options) => {
          assert.equal(method, "Page.captureScreenshot");
          assert.deepEqual(options, { format: "png", fromSurface: true, captureBeyondViewport: false });
          return { data: Buffer.from("png-fixture").toString("base64") };
        },
        detach: async () => { detached = true; },
      }),
    }),
    screenshot: async () => { throw new Error("must not use Playwright screenshot on Windows"); },
  };
  assert.deepEqual(await capturePageScreenshot(page, path, { platform: "win32" }), {
    method: "cdp-page-captureScreenshot",
  });
  assert.equal(await readFile(path, "utf8"), "png-fixture");
  assert.equal(detached, true);
});

test("ordinary terminal cleanup leaves enough time for a late Windows preview process", () => {
  assert.deepEqual(terminalProcessCleanupTiming("SUCCEEDED"), {
    quietMilliseconds: 45_000,
    waitMilliseconds: 120_000,
  });
  assert.deepEqual(terminalProcessCleanupTiming("TIMEOUT"), {
    quietMilliseconds: 5_000,
    waitMilliseconds: 10_000,
  });
});

test("full access confirmation clicks the stable label and verifies readback", async () => {
  let labelClicks = 0;
  let confirmClicks = 0;
  const dialog = {
    locator: (selector) => selector === "label.wb-checkbox"
      ? { click: async () => { labelClicks += 1; } }
      : { isChecked: async () => labelClicks === 1 },
    getByRole: () => ({
      isEnabled: async () => labelClicks === 1,
      click: async () => { confirmClicks += 1; },
    }),
  };
  await confirmFullAccessRiskDialog(dialog, 100, { sleep: async () => {} });
  assert.equal(labelClicks, 1);
  assert.equal(confirmClicks, 1);
});

test("full access accepts the updated WorkBuddy direct-toggle flow without a risk dialog", async () => {
  let clock = 0;
  let confirmations = 0;
  const result = await waitForFullAccessTransition({}, {
    isVisible: async () => false,
  }, 1_000, {
    inspectPermissionMode: async () => ({ available: true, mode: "full-access" }),
    confirmFullAccessRiskDialog: async () => { confirmations += 1; },
    sleep: async (milliseconds) => { clock += milliseconds; },
    now: () => clock,
    noDialogGraceMilliseconds: 200,
  });
  assert.deepEqual(result, { risk_confirmation: false });
  assert.equal(confirmations, 0);
});

test("full access still confirms the risk dialog when the client presents it", async () => {
  let confirmations = 0;
  const result = await waitForFullAccessTransition({}, {
    isVisible: async () => true,
  }, 1_000, {
    inspectPermissionMode: async () => ({ available: false, mode: "default-sandbox" }),
    confirmFullAccessRiskDialog: async () => { confirmations += 1; },
  });
  assert.deepEqual(result, { risk_confirmation: true });
  assert.equal(confirmations, 1);
});

test("fresh attempt persists successful WorkBuddy launch evidence", async () => {
  const launch = {
    status: "READY",
    recovered_after_retry: false,
    attempts: [{ attempt: 1, open_exit_code: 0, endpoint_ready: true }],
  };
  const state = { client: { launch: null } };
  const result = await prepareClientForNewAttempt(
    { restartApp: true, endpoint: "http://127.0.0.1:9229" },
    state,
    { restart: async () => launch },
  );
  assert.deepEqual(result, launch);
  assert.deepEqual(state.client.launch, launch);
});

test("restartWorkBuddy retries a failed macOS open before prompt handling", async () => {
  let openCalls = 0;
  const result = await restartWorkBuddy(
    { endpoint: "http://127.0.0.1:9229", appPath: "/Applications/WorkBuddy.app" },
    {
      launchAttempts: 3,
      retryDelayMilliseconds: 1,
      sleep: async () => {},
      processIdentity: async () => null,
      endpointReady: async () => false,
      waitForEndpoint: async () => {},
      launchApp: async () => {
        openCalls += 1;
        return openCalls === 1
          ? { code: 1, stdout: "", stderr: "The application cannot be opened (-600)" }
          : { code: 0, stdout: "", stderr: "" };
      },
    },
  );
  assert.equal(openCalls, 2);
  assert.equal(result.status, "READY");
  assert.equal(result.recovered_after_retry, true);
  assert.equal(result.attempts[0].open_exit_code, 1);
  assert.equal(result.attempts[1].endpoint_ready, true);
});

test("restartWorkBuddy stops after bounded launch retries", async () => {
  await assert.rejects(
    restartWorkBuddy(
      { endpoint: "http://127.0.0.1:9229", appPath: "/Applications/WorkBuddy.app" },
      {
        launchAttempts: 2,
        retryDelayMilliseconds: 1,
        sleep: async () => {},
        processIdentity: async () => null,
        endpointReady: async () => false,
        waitForEndpoint: async () => {},
        launchApp: async () => ({ code: 1, stdout: "", stderr: "open failed" }),
      },
    ),
    /自动启动 2 次后仍未开放调试端口/,
  );
});

test("waitForUniqueVisible tolerates asynchronous model popover mounting", async () => {
  const expected = { id: "model-listbox" };
  const samples = [[], [], [expected]];
  const actual = await waitForUniqueVisible(
    async () => samples.shift() || [expected],
    2_000,
    "WorkBuddy 模型下拉框",
    1,
  );
  assert.equal(actual, expected);
});

test("waitForUniqueVisible fails closed when multiple model popovers are visible", async () => {
  await assert.rejects(
    waitForUniqueVisible(async () => [{}, {}], 100, "WorkBuddy 模型下拉框", 1),
    /WorkBuddy 模型下拉框数量异常：2/,
  );
});

test("ensureModel keeps and reads the current model when no model is requested", async () => {
  let clickCount = 0;
  const trigger = {
    isVisible: async () => true,
    getAttribute: async (name) => name === "title" ? "xopglm52" : "false",
    innerText: async () => "xopglm52",
    click: async () => { clickCount += 1; },
  };
  const page = {
    locator: (selector) => {
      assert.equal(selector, 'button.cr-model-selector__trigger[role="combobox"]');
      return { count: async () => 1, nth: () => trigger };
    },
  };

  assert.deepEqual(await ensureModel(page, "", 100), {
    mode: "current",
    requested_model: null,
    actual_model: "xopglm52",
    method: "visible-current-value",
  });
  assert.equal(clickCount, 0);
});

test("DOM completion accepts a finished footer without treating a tool card as final prose", () => {
  assert.equal(hasTrustedDomCompletion({
    status: { kind: "success" },
    finalText: "",
    explicitFinished: true,
  }), true);
  assert.equal(hasTrustedDomCompletion({
    status: { kind: "success" },
    finalText: "",
    explicitFinished: false,
  }), false);
});

async function fixture({ manifest = true, record = false } = {}) {
  const root = await mkdtemp(join(tmpdir(), "execute-web-e2e-"));
  const harnessRoot = join(root, "batch__workbuddy");
  const taskId = "task-001";
  const taskRoot = join(harnessRoot, "execution", "tasks", taskId);
  const appPath = process.platform === "win32"
    ? join(root, "WorkBuddy", "WorkBuddy.exe")
    : join(root, "WorkBuddy.app");
  await mkdir(join(taskRoot, "workspace"), { recursive: true });
  if (process.platform === "win32") {
    await mkdir(join(root, "WorkBuddy", "resources"), { recursive: true });
    await writeFile(appPath, "fixture");
    await writeFile(join(root, "WorkBuddy", "resources", "app.asar"), "fixture");
  } else {
    await mkdir(join(appPath, "Contents", "Resources"), { recursive: true });
    await writeFile(join(appPath, "Contents", "Resources", "app.asar"), "fixture");
  }
  await writeFile(join(taskRoot, "PROMPT.md"), "build a site\n");
  if (manifest) {
    await writeFile(join(harnessRoot, "manifest.json"), JSON.stringify({
      schema_version: "wildclawbench.web-e2e-batch/v3",
      batch_id: "batch-001",
      harness: { id: "workbuddy", display_name: "WorkBuddy" },
      tasks: [{ task_id: taskId, execution_dir: `execution/tasks/${taskId}` }],
    }));
  }
  if (record) {
    await writeFile(join(taskRoot, "execution_record.json"), JSON.stringify({
      schema_version: "wildclawbench.web-e2e-execution/v1",
      batch_id: "batch-001",
      task_id: taskId,
      model: { id: "model-a", display_name: "Model A" },
      harness: { id: "workbuddy", display_name: "WorkBuddy", version: "" },
      execution: { status: "pending", started_at: null, finished_at: null, duration_seconds: null, error: null },
      usage: { input_tokens: null, output_tokens: null, total_tokens: null, request_count: null, cost_usd: null },
      tools: { call_count: null, format_accuracy: null },
      artifacts: { harness_transcript: null },
    }));
  }
  return { root, harnessRoot, taskRoot, taskId, appPath };
}

test("parseArgs supplies safe single-run defaults", () => {
  const parsed = parseArgs(["--workspace", "/tmp/task"]);
  assert.equal(parsed.model, "");
  assert.equal(parsed.permissionMode, "current");
  assert.equal(parsed.runTimeoutSeconds, 3600);
  assert.equal(parsed.pollIntervalSeconds, 2);
  assert.equal(parsed.postCancelQuiescenceSeconds, 5);
  assert.equal(parsed.resume, false);
  assert.equal(parsed.detachAfterSubmit, false);
  assert.equal(parsed.observeOnce, false);
  assert.equal(parsed.quiet, false);
});

test("parseArgs validates detached dispatch and one-shot observation modes", () => {
  assert.equal(parseArgs(["--workspace", "/tmp/task", "--detach-after-submit"]).detachAfterSubmit, true);
  assert.equal(parseArgs(["--workspace", "/tmp/task", "--quiet"]).quiet, true);
  assert.equal(parseArgs(["--workspace", "/tmp/task", "--resume", "--observe-once"]).observeOnce, true);
  assert.throws(() => parseArgs(["--workspace", "/tmp/task", "--observe-once"]), /必须与 --resume/);
  assert.throws(() => parseArgs([
    "--workspace", "/tmp/task", "--resume", "--observe-once", "--detach-after-submit",
  ]), /不能同时使用/);
});

test("detached dispatch requires a stable WorkBuddy conversation id", () => {
  assert.equal(hasStableConversationId({ session: {} }), false);
  assert.equal(hasStableConversationId({ session: { dom_conversation_id: "dom-1" } }), true);
  assert.equal(hasStableConversationId({ session: { conversation_id: "db-1" } }), true);
});

test("detached dispatch waits for a delayed exact-workspace database conversation", async () => {
  let clock = 0;
  const state = {
    session: { baseline: [], dom_baseline_conversation_id: "previous" },
    timing: { prepared_at: "2026-09-12T00:00:00.000Z", sent_at: "2026-09-12T00:00:01.000Z" },
  };
  const session = {
    conversationId: "delayed-conversation",
    cwd: "/tmp/task",
    status: "working",
    createdAt: Date.parse("2026-09-12T00:00:02.000Z"),
    updatedAt: Date.parse("2026-09-12T00:00:02.000Z"),
  };
  const captured = await captureAttemptConversation({}, state, 30_000, {
    sessionDb: "/tmp/workbuddy.db",
    workspace: "/tmp/task",
  }, {
    inspectSelectedConversationId: async () => null,
    querySessions: async () => clock >= 20_000 ? [session] : [],
    sleep: async (milliseconds) => { clock += milliseconds; },
    now: () => clock,
  });
  assert.equal(captured, "delayed-conversation");
  assert.equal(state.session.conversation_id, "delayed-conversation");
  assert.equal(state.session.cwd, "/tmp/task");
  assert.equal(state.session.raw_status, "working");
});

test("prompt submission is accepted only after an exact workspace session appears", async () => {
  const initial = { entries: [{ path: ".gitkeep", type: "file", sha256: "empty" }] };
  const state = {
    session: { baseline: [], dom_baseline_conversation_id: "previous" },
    timing: { prepared_at: "2026-09-12T00:00:00.000Z", sent_at: null },
    artifacts: { initial },
  };
  const session = {
    conversationId: "current",
    cwd: "/tmp/task",
    status: "InProgress",
    createdAt: Date.parse("2026-09-12T00:00:01.000Z"),
    updatedAt: Date.parse("2026-09-12T00:00:01.000Z"),
  };
  const result = await waitForPromptSubmissionAcceptance({}, {}, {
    prompt: "build a site",
    sessionDb: "/tmp/workbuddy.db",
    workspace: "/tmp/task",
    candidateWorkspace: "/tmp/task/workspace",
  }, state, {
    querySessions: async () => [session],
    inspectSelectedConversationId: async () => null,
    inspectDom: async () => ({ status: { kind: "missing", status: "" } }),
    readEditorText: async () => "",
    snapshotTree: async () => { throw new Error("accepted submission must not need a workspace snapshot"); },
    now: () => 10,
  });
  assert.equal(result.accepted, true);
  assert.equal(result.source, "workbuddy-session-db");
  assert.equal(result.session.conversationId, "current");
});

test("prompt submission permits one retry only after proving the click was not accepted", async () => {
  let clock = 0;
  const initial = { entries: [{ path: ".gitkeep", type: "file", sha256: "empty" }] };
  const state = {
    session: { baseline: [], dom_baseline_conversation_id: null },
    timing: { prepared_at: "2026-09-12T00:00:00.000Z", sent_at: null },
    artifacts: { initial },
  };
  const result = await waitForPromptSubmissionAcceptance({}, {}, {
    prompt: "build a site\r\n",
    sessionDb: "/tmp/workbuddy.db",
    workspace: "/tmp/task",
    candidateWorkspace: "/tmp/task/workspace",
  }, state, {
    querySessions: async () => [],
    inspectSelectedConversationId: async () => null,
    inspectDom: async () => ({ status: { kind: "missing", status: "" } }),
    readEditorText: async () => "build a site\n",
    snapshotTree: async () => initial,
    sleep: async (milliseconds) => { clock += milliseconds; },
    now: () => clock,
    timeoutMilliseconds: 20,
    pollMilliseconds: 10,
  });
  assert.equal(result.accepted, false);
  assert.equal(result.confirmed_unsent, true);
  assert.equal(result.editor_retains_prompt, true);
  assert.equal(result.workspace_unchanged, true);
  assert.deepEqual(result.workspace_changes, { added: [], modified: [], removed: [] });
});

test("prompt submission remains ambiguous when the editor clears without a session or running state", async () => {
  let clock = 0;
  const initial = { entries: [{ path: ".gitkeep", type: "file", sha256: "empty" }] };
  const result = await waitForPromptSubmissionAcceptance({}, {}, {
    prompt: "build a site",
    sessionDb: "/tmp/workbuddy.db",
    workspace: "/tmp/task",
    candidateWorkspace: "/tmp/task/workspace",
  }, {
    session: { baseline: [], dom_baseline_conversation_id: null },
    timing: { prepared_at: "2026-09-12T00:00:00.000Z", sent_at: null },
    artifacts: { initial },
  }, {
    querySessions: async () => [],
    inspectSelectedConversationId: async () => null,
    inspectDom: async () => ({ status: { kind: "missing", status: "" } }),
    readEditorText: async () => "",
    snapshotTree: async () => initial,
    sleep: async (milliseconds) => { clock += milliseconds; },
    now: () => clock,
    timeoutMilliseconds: 20,
    pollMilliseconds: 10,
  });
  assert.equal(result.accepted, false);
  assert.equal(result.confirmed_unsent, false);
  assert.equal(result.source, "ambiguous-send-boundary");
});

test("parseArgs accepts a dynamic WorkBuddy model", () => {
  const parsed = parseArgs(["--workspace", "/tmp/task-a", "--model", "Hy3"]);
  assert.equal(parsed.model, "Hy3");
});

test("parseArgs requires an explicit supported permission mode", () => {
  assert.equal(parseArgs(["--permission-mode", "full-access", "--probe"]).permissionMode, "full-access");
  assert.throws(() => parseArgs(["--permission-mode", "unrestricted", "--probe"]), /仅支持 current 或 full-access/);
});

test("pre-send retry requires resume", () => {
  assert.throws(() => parseArgs(["--retry-pre-send-failure", "--probe"]), /必须与 --resume 一起使用/);
  assert.equal(parseArgs(["--retry-pre-send-failure", "--resume", "--probe"]).retryPreSendFailure, true);
});

test("parseArgs supports probe and recovery controls", () => {
  const parsed = parseArgs([
    "--probe", "--resume", "--run-timeout-seconds", "90", "--poll-interval-seconds", "0.5",
    "--post-cancel-quiescence-seconds", "3",
  ]);
  assert.equal(parsed.probe, true);
  assert.equal(parsed.resume, true);
  assert.equal(parsed.runTimeoutSeconds, 90);
  assert.equal(parsed.pollIntervalSeconds, 0.5);
  assert.equal(parsed.postCancelQuiescenceSeconds, 3);
});

test("resolveConfig keeps state outside the candidate task", async () => {
  const item = await fixture();
  const config = await resolveConfig(parseArgs(["--workspace", item.taskRoot, "--app-path", item.appPath]));
  assert.equal(config.promptSha256.length, 64);
  assert.equal(config.candidateWorkspace, join(config.workspace, "workspace"));
  assert.equal(config.stateFile, join(config.workspace, "..", ".execute-web-e2e", item.taskId, "automation_state.json"));
  assert.ok(!config.outputDir.startsWith(`${config.workspace}/`));
});

test("resolveConfig rejects remote endpoints and in-task output", async () => {
  const item = await fixture();
  await assert.rejects(resolveConfig(parseArgs([
    "--workspace", item.taskRoot, "--app-path", item.appPath, "--endpoint", "http://example.com:9229",
  ])), /仅允许连接本机地址/);
  await assert.rejects(resolveConfig(parseArgs([
    "--workspace", item.taskRoot, "--app-path", item.appPath, "--output-dir", join(item.taskRoot, "output"),
  ])), /必须位于所选单题目录之外/);
});

test("resolveExecutionIdentity matches manifest by exact execution_dir", async () => {
  const item = await fixture();
  const config = await resolveConfig(parseArgs(["--workspace", item.taskRoot, "--app-path", item.appPath, "--model-id", "model-a"]));
  const info = await resolveExecutionIdentity(config);
  assert.deepEqual(info.identity, {
    batchId: "batch-001",
    taskId: item.taskId,
    harness: { id: "workbuddy", display_name: "WorkBuddy" },
    model: { id: "model-a", display_name: "model-a" },
  });
});

test("resolveExecutionIdentity never guesses identity from directory names", async () => {
  const item = await fixture({ manifest: false });
  const config = await resolveConfig(parseArgs(["--workspace", item.taskRoot, "--app-path", item.appPath]));
  await assert.rejects(resolveExecutionIdentity(config), /缺少执行身份/);
});

test("execution_record preserves identity and maps execution fields", async () => {
  const item = await fixture({ record: true });
  const config = await resolveConfig(parseArgs(["--workspace", item.taskRoot, "--app-path", item.appPath, "--model-id", "model-a"]));
  const info = await resolveExecutionIdentity(config);
  await updateExecutionRecord(config, info, {
    clientVersion: "5.5.3",
    execution: { status: "completed", started_at: "2026-09-04T00:00:00.000Z", finished_at: "2026-09-04T00:01:00.000Z", duration_seconds: 60, error: null },
  });
  const record = JSON.parse(await readFile(config.executionRecord, "utf8"));
  assert.equal(record.batch_id, "batch-001");
  assert.equal(record.model.id, "model-a");
  assert.equal(record.harness.version, "5.5.3");
  assert.equal(record.execution.status, "completed");
});

test("execution_record binds the actual WorkBuddy model read from the UI", async () => {
  const item = await fixture();
  const config = await resolveConfig(parseArgs([
    "--workspace", item.taskRoot,
    "--app-path", item.appPath,
    "--model", "xopglm52",
  ]));
  const info = await resolveExecutionIdentity(config);
  await updateExecutionRecord(config, info, {
    clientVersion: "5.5.3",
    modelSelection: { requested_model: "xopglm52", actual_model: "xopglm52" },
    execution: { status: "pending" },
  });
  const record = JSON.parse(await readFile(config.executionRecord, "utf8"));
  assert.deepEqual(record.model, { id: "xopglm52", display_name: "xopglm52" });
});

test("session classification fails closed for unknown values", () => {
  assert.equal(classifySessionStatus("Completed").kind, "success");
  assert.equal(classifySessionStatus("InProgress").kind, "running");
  assert.equal(classifySessionStatus("working").kind, "running");
  assert.equal(classifySessionStatus("Failed").kind, "failure");
  assert.equal(classifySessionStatus("MysteryState").kind, "unknown");
});

test("DOM terminal classification requires an explicit status label", () => {
  assert.equal(classifyDomStatus({ running: true, agentText: "已完成 1m" }).kind, "running");
  assert.equal(classifyDomStatus({ rawStatus: "complete", agentText: "WorkBuddy\n已处理 1s\n正在连接 MCP 服务…" }).kind, "running");
  assert.equal(classifyDomStatus({ rawStatus: "complete", agentText: "WorkBuddy\n已处理 43s\n等待模型响应" }).kind, "running");
  assert.deepEqual(
    classifyDomStatus({ rawStatus: "complete", agentText: "当前服务异常，请稍后再试或新建任务、切换模型后重试" }),
    { kind: "failure", status: "visible-service-error" },
  );
  assert.equal(classifyDomStatus({
    rawStatus: "complete",
    agentText: "WorkBuddy\n已完成 1m34s\n\n当前服务异常，请稍后再试或新建任务、切换模型后重试\n\nHy3\n18:52",
  }).kind, "failure");
  assert.equal(classifyDomStatus({ rawStatus: "complete", agentText: "已完成：页面会展示‘当前服务异常’提示" }).kind, "success");
  assert.equal(classifyDomStatus({ agentText: "WorkBuddy\n已完成 1h8m\n完成交付" }).kind, "success");
  assert.equal(classifyDomStatus({ agentText: "WorkBuddy\n已失败：网络错误" }).kind, "failure");
  assert.equal(classifyDomStatus({ agentText: "我会继续处理" }).kind, "unknown");
  assert.equal(isSubstantiveFinalResponse("等待模型响应"), false);
  assert.equal(isSubstantiveFinalResponse("正在连接 MCP 服务..."), false);
  assert.equal(isSubstantiveFinalResponse("已完成页面并保存到 workspace"), true);
});

test("approval allowlist only accepts exact DS_Store cleanup inside candidate workspace", () => {
  const workspace = "/tmp/e2e-task/workspace";
  const safe = `rm -f ${workspace}/.DS_Store && find ${workspace} -name '.DS_Store' -delete`;
  assert.deepEqual(classifyApprovalCommand(safe, workspace, posix), {
    allow: true,
    rule: "candidate-workspace-ds-store-cleanup",
  });
  assert.equal(classifyApprovalCommand(`rm -rf ${workspace}`, workspace, posix).allow, false);
  assert.equal(classifyApprovalCommand("rm -f /tmp/.DS_Store && find /tmp -name '.DS_Store' -delete", workspace, posix).allow, false);
});

test("chooseSession requires exact cwd and respects recovery id", () => {
  const sessions = [
    { conversationId: "wrong", cwd: "/tmp/task-other", status: "Completed", updatedAt: 300 },
    { conversationId: "older", cwd: "/tmp/task", status: "Completed", updatedAt: 100 },
    { conversationId: "newer", cwd: "/tmp/task", status: "Running", updatedAt: 200 },
  ];
  assert.equal(chooseSession(sessions, "/tmp/task", { notBeforeMs: 150 }).conversationId, "newer");
  assert.equal(chooseSession(sessions, "/tmp/task", { conversationId: "older" }).conversationId, "older");
  assert.equal(chooseSession(sessions, "/tmp/task", { conversationId: "missing" }), null);
});

test("chooseAttemptSession ignores a pre-send completed conversation", () => {
  const state = {
    session: {
      conversation_id: null,
      baseline: [{ conversation_id: "old", updated_at_ms: 100 }],
    },
    timing: { prepared_at: "1970-01-01T00:00:00.050Z", sent_at: null },
  };
  assert.equal(chooseAttemptSession([
    { conversationId: "old", cwd: "/tmp/task", status: "Completed", updatedAt: 100 },
  ], state, "/tmp/task"), null);
  assert.equal(chooseAttemptSession([
    { conversationId: "old", cwd: "/tmp/task", status: "Running", updatedAt: 200 },
  ], state, "/tmp/task").conversationId, "old");
});

test("workspace snapshots report added modified and removed files", async () => {
  const root = await mkdtemp(join(tmpdir(), "execute-web-e2e-tree-"));
  await writeFile(join(root, "keep.txt"), "before");
  await writeFile(join(root, "remove.txt"), "gone");
  const before = await snapshotTree(root);
  await writeFile(join(root, "keep.txt"), "after");
  await writeFile(join(root, "add.txt"), "new");
  const { unlink } = await import("node:fs/promises");
  await unlink(join(root, "remove.txt"));
  const after = await snapshotTree(root);
  assert.deepEqual(diffSnapshots(before, after), { added: ["add.txt"], modified: ["keep.txt"], removed: ["remove.txt"] });
});

test("resume state validates prompt and execution identity", async () => {
  const item = await fixture();
  const config = await resolveConfig(parseArgs(["--workspace", item.taskRoot, "--app-path", item.appPath, "--model-id", "model-a"]));
  const info = await resolveExecutionIdentity(config);
  const snapshot = await snapshotTree(config.candidateWorkspace);
  const state = createInitialState(config, info.identity, snapshot);
  assert.equal(state.schema_version, AUTOMATION_SCHEMA);
  assert.equal(state.requested_permission_mode, "current");
  assert.equal(state.driver.version, "1.8.18");
  assert.equal(state.session.dom_conversation_id, null);
  assert.equal(state.timeout, null);
  assert.equal(state.runtime.driver_pid, process.pid);
  assert.doesNotThrow(() => assertStateMatches(state, config, info.identity));
  state.prompt_sha256 = "0".repeat(64);
  assert.throws(() => assertStateMatches(state, config, info.identity), /prompt_sha256/);
});

test("client restart recovery waits for the exact Windows session host", async () => {
  let clock = 0;
  let processChecks = 0;
  const result = await waitForRestartedAttemptRecovery(
    {
      sessionDb: "C:\\fixture\\workbuddy.db",
      workspace: "C:\\fixture\\task-a",
      candidateWorkspace: "C:\\fixture\\task-a\\workspace",
    },
    {
      session: { conversation_id: "conversation-a" },
    },
    {
      graceMilliseconds: 5_000,
      now: () => clock,
      sleep: async (milliseconds) => { clock += milliseconds; },
      querySessions: async () => [{
        conversationId: "conversation-a",
        cwd: "C:\\fixture\\task-a",
        status: "working",
        updatedAt: 10,
      }],
      processSnapshot: async () => {
        processChecks += 1;
        return {
          supported: true,
          session_host_pids: processChecks === 1 ? [] : [321],
        };
      },
    },
  );
  assert.equal(result.outcome, "session-host-restored");
  assert.deepEqual(result.session_host_pids, [321]);
  assert.equal(processChecks, 2);
});

test("client restart recovery fails closed on stale active state without a session host", async () => {
  const result = await waitForRestartedAttemptRecovery(
    {
      sessionDb: "C:\\fixture\\workbuddy.db",
      workspace: "C:\\fixture\\task-a",
      candidateWorkspace: "C:\\fixture\\task-a\\workspace",
    },
    {
      session: { conversation_id: "conversation-a" },
    },
    {
      graceMilliseconds: 0,
      now: () => 100,
      querySessions: async () => [{
        conversationId: "conversation-a",
        cwd: "C:\\fixture\\task-a",
        status: "working",
        updatedAt: 10,
      }],
      processSnapshot: async () => ({ supported: true, session_host_pids: [] }),
    },
  );
  assert.equal(result.outcome, "stale-active-without-session-host");
  assert.deepEqual(result.session_host_pids, []);
});

test("client restart recovery preserves an explicit interrupted terminal state", async () => {
  let processChecks = 0;
  const result = await waitForRestartedAttemptRecovery(
    {
      sessionDb: "C:\\fixture\\workbuddy.db",
      workspace: "C:\\fixture\\task-a",
      candidateWorkspace: "C:\\fixture\\task-a\\workspace",
    },
    {
      session: { conversation_id: "conversation-a" },
    },
    {
      querySessions: async () => [{
        conversationId: "conversation-a",
        cwd: "C:\\fixture\\task-a",
        status: "interrupted",
        updatedAt: 20,
      }],
      processSnapshot: async () => { processChecks += 1; },
    },
  );
  assert.equal(result.outcome, "session-status-changed");
  assert.equal(result.session_status_kind, "failure");
  assert.equal(processChecks, 0);
});
