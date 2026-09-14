import assert from "node:assert/strict";
import test from "node:test";

import {
  attemptSessionCaptureTimeout,
  chooseQwenAttemptSession,
  capturePageScreenshot,
  handleExpectedApprovals,
  hasStableConversationId,
  inspectApprovalPanels,
  inspectPendingAttention,
  inspectUserQuestions,
  isQwenWorkMainPageDescriptor,
  nextScreenshotPath,
  openQwenProjectConversation,
  qwenStopControlLocator,
  qwenProjectSidebarLabel,
  recordTerminalProcessCleanup,
  rememberSession,
  restartQwenWork,
  terminalProcessCleanupTiming,
  userQuestionsMatch,
  validateAbandonmentConnection,
  validateUserQuestionAbandonmentState,
  waitForUniqueVisible,
  withOperationTimeout,
} from "../driver.mjs";
import {
  createInitialState,
  DEFAULT_APP_PATH,
  DEFAULT_ENDPOINT,
  DEFAULT_SESSION_DB,
  parseArgs,
} from "../lib.mjs";

test("QwenWork session 捕获在慢写库客户端上至少等待六十秒", () => {
  assert.equal(attemptSessionCaptureTimeout(5000), 60000);
  assert.equal(attemptSessionCaptureTimeout(120000), 120000);
});

test("QwenWork 参数默认使用独立应用、CDP 端口和状态库", () => {
  const parsed = parseArgs(["--probe"]);
  assert.equal(parsed.appPath, DEFAULT_APP_PATH);
  assert.equal(parsed.endpoint, DEFAULT_ENDPOINT);
  assert.equal(parsed.sessionDb, DEFAULT_SESSION_DB);
});

test("QwenWork automation state 使用独立 Driver profile", () => {
  const state = createInitialState(
    {
      appPath: DEFAULT_APP_PATH,
      endpoint: DEFAULT_ENDPOINT,
      sessionDb: DEFAULT_SESSION_DB,
      workspace: "/tmp/task",
      candidateWorkspace: "/tmp/task/workspace",
      promptFile: "/tmp/task/PROMPT.md",
      promptSha256: "abc",
      promptBytes: 3,
      model: "",
      permissionMode: "current",
    },
    { batchId: "batch", taskId: "task", harness: { id: "qwenwork" }, model: {} },
    { sha256: "initial", entries: [] },
  );
  assert.equal(state.driver.id, "qwenwork");
  assert.equal(state.driver.version, "1.10.10");
});

test("QwenWork 问卷停止参数必须与恢复模式组合", () => {
  assert.throws(() => parseArgs(["--probe", "--abandon-user-question"]), /必须与 --resume/);
  assert.equal(parseArgs(["--probe", "--resume", "--abandon-user-question"]).abandonUserQuestion, true);
});

test("QwenWork 问卷停止只接受完整稳定身份和同一 cwd", () => {
  const workspace = "C:\\tasks\\one";
  const state = {
    phase: "NEEDS_ATTENTION",
    pending_interaction: { type: "user-question", questions: [{ title: "视觉风格", prompt: "请选择" }] },
    session: {
      conversation_id: "chat",
      session_id: "session",
      local_project_id: "project",
      cwd: workspace,
    },
  };
  assert.doesNotThrow(() => validateUserQuestionAbandonmentState(state, workspace));
  assert.throws(
    () => validateUserQuestionAbandonmentState({ ...state, session: { ...state.session, session_id: null } }, workspace),
    /缺少稳定身份/,
  );
  assert.throws(() => validateUserQuestionAbandonmentState(state, "C:\\tasks\\other"), /cwd/);
});

test("QwenWork 问卷停止要求当前交互与已持久化摘要完全一致", () => {
  const expected = [{ title: "视觉风格", pagination: "1 / 3", prompt: "请选择风格" }];
  assert.equal(userQuestionsMatch(expected, [{ ...expected[0] }]), true);
  assert.equal(userQuestionsMatch(expected, [{ ...expected[0], prompt: "请选择技术" }]), false);
});

test("QwenWork 仅在原 CDP 不可达且主进程缺失时允许临时恢复端口", async () => {
  const state = {
    phase: "NEEDS_ATTENTION",
    pending_interaction: { type: "user-question", questions: [{ prompt: "请选择" }] },
    client: { endpoint: DEFAULT_ENDPOINT },
    session: {
      conversation_id: "chat",
      session_id: "session",
      local_project_id: "project",
      cwd: "C:\\tasks\\one",
    },
  };
  const config = {
    workspace: "C:\\tasks\\one",
    endpoint: "http://127.0.0.1:9251",
    appPath: DEFAULT_APP_PATH,
    restartApp: true,
  };
  assert.deepEqual(
    await validateAbandonmentConnection(config, state, {
      endpointReady: async () => false,
      processIdentity: async () => null,
    }),
    {
      overridden: true,
      original_endpoint: DEFAULT_ENDPOINT,
      recovery_endpoint: "http://127.0.0.1:9251",
      reason: "original-cdp-unreachable-and-qwenwork-process-absent",
    },
  );
  await assert.rejects(
    validateAbandonmentConnection(config, state, {
      endpointReady: async (endpoint) => endpoint === DEFAULT_ENDPOINT,
      processIdentity: async () => null,
    }),
    /仍可核对/,
  );
  const resumedState = {
    ...state,
    recovery_connection: {
      overridden: true,
      original_endpoint: DEFAULT_ENDPOINT,
      recovery_endpoint: "http://127.0.0.1:9251",
      reason: "original-cdp-unreachable-and-qwenwork-process-absent",
    },
  };
  assert.equal((await validateAbandonmentConnection(
    { ...config, restartApp: false },
    resumedState,
    {
      endpointReady: async (endpoint) => endpoint === "http://127.0.0.1:9251",
      processIdentity: async () => ({ pid: 123 }),
    },
  )).resumed, true);
  assert.equal((await validateAbandonmentConnection(
    { ...config, restartApp: false },
    state,
    {
      endpointReady: async (endpoint) => endpoint === "http://127.0.0.1:9251",
      processIdentity: async () => ({ pid: 123 }),
    },
  )).adopted, true);
});

test("QwenWork 终态查询不覆盖已捕获的稳定会话身份", () => {
  const state = {
    session: {
      conversation_id: "conversation-a",
      sub_chat_id: "sub-chat-a",
      session_id: "session-a",
      local_project_id: "project-a",
      project_name: "Project A",
      conversation_name: "Conversation A",
      cwd: "C:\\tasks\\a",
      raw_status: "running",
      stream_id: "stream-a",
      model_level: "flash",
      updated_at_ms: 100,
    },
  };
  rememberSession(state, {
    conversationId: "conversation-a",
    sessionId: "session-a",
    status: "completed",
    streamId: null,
    updatedAt: 200,
  });
  assert.equal(state.session.stream_id, "stream-a");
  assert.equal(state.session.sub_chat_id, "sub-chat-a");
  assert.equal(state.session.local_project_id, "project-a");
  assert.equal(state.session.cwd, "C:\\tasks\\a");
  assert.equal(state.session.raw_status, "completed");
  assert.equal(state.session.updated_at_ms, 200);
});

test("QwenWork 重复终态观察为截图分配唯一证据路径", () => {
  const first = nextScreenshotPath("output", [], "10-succeeded.png");
  const second = nextScreenshotPath("output", [first], "10-succeeded.png");
  const third = nextScreenshotPath("output", [first, second], "10-succeeded.png");
  assert.match(first, /10-succeeded\.png$/);
  assert.match(second, /10-succeeded-2\.png$/);
  assert.match(third, /10-succeeded-3\.png$/);
  assert.equal(new Set([first, second, third]).size, 3);
});

test("QwenWork 只有同时捕获 chat 和稳定内核 session 才允许后台恢复", () => {
  assert.equal(hasStableConversationId({ session: { conversation_id: "chat", session_id: null } }), false);
  assert.equal(hasStableConversationId({ session: { conversation_id: "chat", session_id: "session" } }), true);
});

test("QwenWork 项目恢复只匹配侧栏标签，不混入新任务项目选择器", () => {
  const calls = [];
  const expected = {};
  const page = {
    locator(selector) {
      calls.push(["locator", selector]);
      return {
        getByText(value, options) {
          calls.push(["getByText", value, options]);
          return expected;
        },
      };
    },
  };
  assert.equal(qwenProjectSidebarLabel(page, "project-a"), expected);
  assert.deepEqual(calls, [
    ["locator", '[data-slot="collapsible-menu-item-label"]'],
    ["getByText", "project-a", { exact: true }],
  ]);
});

test("QwenWork 客户端重启后按原 conversation ID 打开侧栏会话", async () => {
  let currentUrl = "file:///QwenWork/index.html?windowId=main";
  const conversation = {
    isVisible: async () => true,
    click: async () => {
      currentUrl = "file:///QwenWork/index.html?windowId=main&chat=chat-1";
    },
  };
  const conversationCollection = {
    count: async () => 1,
    nth: () => conversation,
  };
  const projectContainer = {
    getByRole: (role, options) => {
      assert.equal(role, "button");
      assert.deepEqual(options, { name: "conversation-a", exact: true });
      return conversationCollection;
    },
  };
  const projectGroup = {
    count: async () => 1,
    locator: (selector) => {
      assert.equal(selector, "xpath=parent::*");
      return projectContainer;
    },
  };
  const expander = {
    count: async () => 1,
    getAttribute: async () => "true",
  };
  const projectLabel = {
    isVisible: async () => true,
    locator: (selector) => {
      if (selector === 'xpath=ancestor::*[@data-slot="collapsible-menu-item"][1]') return projectGroup;
      if (selector === "xpath=ancestor::button[1]") return expander;
      throw new Error(`unexpected selector: ${selector}`);
    },
  };
  const projectLabels = {
    count: async () => 1,
    nth: () => projectLabel,
  };
  const page = {
    url: () => currentUrl,
    locator: (selector) => {
      assert.equal(selector, '[data-slot="collapsible-menu-item-label"]');
      return {
        getByText: (value, options) => {
          assert.equal(value, "project-a");
          assert.deepEqual(options, { exact: true });
          return projectLabels;
        },
      };
    },
  };
  const opened = await openQwenProjectConversation(page, {
    projectName: "project-a",
    conversationName: "conversation-a",
    conversationId: "chat-1",
  }, 100);
  assert.equal(opened.opened, true);
  assert.equal(opened.method, "project-sidebar-existing-conversation");
  assert.equal(opened.conversation_id, "chat-1");
});

test("QwenWork 可捕获发送后同一秒创建的 session", () => {
  const workspace = "/tmp/task";
  const state = {
    session: { local_project_id: "project-1", baseline: [] },
    timing: {
      prepared_at: "2026-09-09T05:28:27.530Z",
      sent_at: "2026-09-09T05:28:32.232Z",
    },
  };
  const session = chooseQwenAttemptSession([
    {
      conversationId: "chat-1",
      subChatId: "sub-chat-1",
      sessionId: "session-1",
      localProjectId: "project-1",
      cwd: workspace,
      createdAt: Date.parse("2026-09-09T05:28:32.000Z"),
      updatedAt: Date.parse("2026-09-09T05:28:32.000Z"),
    },
  ], state, workspace);
  assert.equal(session?.sessionId, "session-1");
});

test("QwenWork 以发送前基线识别精确项目中时间戳提前的 session", () => {
  const workspace = "/tmp/task";
  const state = {
    session: { local_project_id: "project-1", baseline: [] },
    timing: {
      prepared_at: "2026-09-09T05:28:27.530Z",
      sent_at: "2026-09-09T05:28:32.232Z",
    },
  };
  const session = chooseQwenAttemptSession([
    {
      conversationId: "chat-1",
      subChatId: "sub-chat-1",
      sessionId: "session-1",
      localProjectId: "project-1",
      cwd: workspace,
      createdAt: Date.parse("2026-09-09T05:28:31.000Z"),
      updatedAt: Date.parse("2026-09-09T05:28:31.000Z"),
    },
  ], state, workspace);
  assert.equal(session?.sessionId, "session-1");
});

test("QwenWork session 捕获限定当前项目且不复用未变化的基线会话", () => {
  const workspace = "/tmp/task";
  const baselineTime = Date.parse("2026-09-09T05:28:30.000Z");
  const state = {
    session: {
      local_project_id: "project-1",
      baseline: [{ conversation_id: "old-chat", sub_chat_id: "old-sub-chat", updated_at_ms: baselineTime }],
    },
    timing: {
      prepared_at: "2026-09-09T05:28:27.530Z",
      sent_at: "2026-09-09T05:28:32.232Z",
    },
  };
  const session = chooseQwenAttemptSession([
    {
      conversationId: "other-project-chat",
      subChatId: "other-project-sub-chat",
      sessionId: "other-project-session",
      localProjectId: "project-2",
      cwd: workspace,
      updatedAt: Date.parse("2026-09-09T05:28:40.000Z"),
    },
    {
      conversationId: "old-chat",
      subChatId: "old-sub-chat",
      sessionId: "old-session",
      localProjectId: "project-1",
      cwd: workspace,
      updatedAt: baselineTime,
    },
    {
      conversationId: "new-chat",
      subChatId: "new-sub-chat",
      sessionId: "new-session",
      localProjectId: "project-1",
      cwd: workspace,
      updatedAt: Date.parse("2026-09-09T05:28:32.000Z"),
    },
  ], state, workspace);
  assert.equal(session?.sessionId, "new-session");
});

test("QwenWork 兼容原生 pending-interaction 授权容器", async () => {
  let requestedContainer = "";
  let requestedRole = "";
  const buttons = [
    {
      isVisible: async () => true,
      innerText: async () => "允许",
      getAttribute: async () => null,
    },
  ];
  const page = {
    locator(selector) {
      requestedContainer = selector;
      return {
        getByRole(role) {
          requestedRole = role;
          return {
            count: async () => buttons.length,
            nth: (index) => buttons[index],
          };
        },
      };
    },
  };
  assert.deepEqual(await inspectPendingAttention(page), ["允许"]);
  assert.match(requestedContainer, /data-pending-interaction-id/);
  assert.match(requestedContainer, /pending-sandbox-panel/);
  assert.match(requestedContainer, /role="dialog"/);
  assert.equal(requestedRole, "button");
});

test("QwenWork 从原生高危授权卡片严格提取命令且不列入自动批准", async () => {
  const command = "/bin/rm -rf /tmp/qwen-approval-target.test";
  let requestedPanelSelector = "";
  let requestedCommandSelector = "";
  const commandNode = {
    isVisible: async () => true,
    getAttribute: async (name) => name === "title" ? command : null,
    innerText: async () => "不应优先读取此文本",
  };
  const panel = {
    isVisible: async () => true,
    locator(selector) {
      requestedCommandSelector = selector;
      return {
        count: async () => 1,
        nth: () => commandNode,
      };
    },
    getByRole(role) {
      assert.equal(role, "button");
      return { allInnerTexts: async () => ["拒绝", "允许"] };
    },
  };
  const page = {
    locator(selector) {
      requestedPanelSelector = selector;
      return {
        count: async () => 1,
        nth: () => panel,
      };
    },
  };
  const approvals = await inspectApprovalPanels(page, "/tmp/candidate/workspace");
  assert.match(requestedPanelSelector, /data-pending-interaction-id/);
  assert.match(requestedCommandSelector, /font-family/);
  assert.deepEqual(approvals, [{
    command,
    buttons: ["拒绝", "允许"],
    classification: { allow: false, rule: null },
  }]);

  let approvalButtonRequested = false;
  panel.getByRole = (role, options) => {
    assert.equal(role, "button");
    if (options) approvalButtonRequested = true;
    return { allInnerTexts: async () => ["拒绝", "允许"] };
  };
  const result = await handleExpectedApprovals(
    page,
    { candidateWorkspace: "/tmp/candidate/workspace" },
    { evidence: { approvals: [] } },
  );
  assert.equal(result.handled, false);
  assert.equal(approvalButtonRequested, false);
});

test("QwenWork 停止按钮兼容 1.0.4 无无障碍名称的圆角方形图标", () => {
  const expected = {};
  const page = {
    locator(selector) {
      assert.match(selector, /aria-label\*="停止"/);
      assert.match(selector, /aria-label\*="Stop"/);
      assert.match(selector, /path\[d\^="M3 10\.2556C3 7\.15979"\]/);
      assert.match(selector, /:not\(\[disabled\]\)/);
      assert.match(selector, /:not\(\[aria-disabled="true"\]\)/);
      return expected;
    },
  };
  assert.equal(qwenStopControlLocator(page), expected);
});

test("QwenWork 重启前拒绝打断活动任务", async () => {
  let mutationCalled = false;
  await assert.rejects(
    restartQwenWork(
      { endpoint: DEFAULT_ENDPOINT, appPath: DEFAULT_APP_PATH, sessionDb: DEFAULT_SESSION_DB },
      {
        processIdentity: async () => ({ pid: 123, command: `${DEFAULT_APP_PATH}/Contents/MacOS/QwenWorkCN` }),
        endpointReady: async () => true,
        querySessions: async () => [{ streamId: "stream", status: "running" }],
        run: async () => {
          mutationCalled = true;
          return { code: 0, stdout: "", stderr: "" };
        },
      },
    ),
    /活动任务/,
  );
  assert.equal(mutationCalled, false);
});

test("QwenWork 主进程和端口均已崩溃时允许重启并保留活动 session", async () => {
  let launched = false;
  const launch = await restartQwenWork(
    { endpoint: DEFAULT_ENDPOINT, appPath: DEFAULT_APP_PATH, sessionDb: DEFAULT_SESSION_DB },
    {
      processIdentity: async () => (launched
        ? { pid: 456, command: `${DEFAULT_APP_PATH}/Contents/MacOS/QwenWorkCN` }
        : null),
      endpointReady: async () => launched,
      querySessions: async () => [{ streamId: "stream", status: "running" }],
      launchApp: async () => {
        launched = true;
        return { code: 0, stdout: "", stderr: "" };
      },
      waitForEndpoint: async () => {},
      sleep: async () => {},
      launchAttempts: 1,
    },
  );
  assert.equal(launch.status, "READY");
  assert.equal(launch.stop.pid, null);
  assert.equal(launch.attempts.length, 1);
  assert.equal(launch.attempts[0].endpoint_ready, true);
});

test("QwenWork 识别问卷型用户输入且不点击任何选项", async () => {
  let clicks = 0;
  const valueLocator = (value) => ({
    innerText: async () => value,
    first() { return this; },
  });
  const container = {
    isVisible: async () => true,
    locator(selector) {
      if (selector === '[data-slot="user-question-header"] span') return valueLocator("视觉风格");
      if (selector === '[data-slot="user-question-pagination"]') return valueLocator("1 / 3");
      if (selector === '[data-slot="user-question-questions"]') return valueLocator("这个原型希望是哪种视觉风格？");
      throw new Error(`unexpected selector: ${selector}`);
    },
    click: async () => { clicks += 1; },
  };
  const page = {
    locator(selector) {
      assert.equal(selector, '[data-slot="user-question"]');
      return {
        count: async () => 1,
        nth: () => container,
      };
    },
  };

  assert.deepEqual(await inspectUserQuestions(page), [{
    title: "视觉风格",
    pagination: "1 / 3",
    prompt: "这个原型希望是哪种视觉风格？",
  }]);
  assert.equal(clicks, 0);
});

test("QwenWork Windows 主页面识别兼容中文标题和 hash windowId", () => {
  assert.equal(isQwenWorkMainPageDescriptor({
    title: "千问办公",
    url: "file:///C:/Apps/QwenWorkCN/resources/app.asar/out/renderer/index.html#windowId=main",
  }), true);
  assert.equal(isQwenWorkMainPageDescriptor({
    title: "千问办公",
    url: "file:///C:/Apps/QwenWorkCN/resources/app.asar/out/renderer/voice-overlay.html",
  }), false);
});

test("QwenWork Windows 截图使用直接 CDP Page.captureScreenshot", async () => {
  const calls = [];
  let detached = false;
  const page = {
    context() {
      return {
        async newCDPSession(actualPage) {
          assert.equal(actualPage, page);
          return {
            async send(method, params) {
              calls.push([method, params]);
              return { data: Buffer.from("png-fixture").toString("base64") };
            },
            async detach() { detached = true; },
          };
        },
      };
    },
  };
  const target = new URL("./screenshot-fixture.png", import.meta.url);
  const result = await capturePageScreenshot(page, target, { platform: "win32" });
  assert.equal(result.method, "cdp-page-captureScreenshot");
  assert.equal(calls[0][0], "Page.captureScreenshot");
  assert.equal(detached, true);
  await import("node:fs/promises").then(({ rm }) => rm(target, { force: true }));
});

test("QwenWork Windows CDP 操作超时后失败关闭", async () => {
  await assert.rejects(
    withOperationTimeout(new Promise(() => {}), 5, "截图测试"),
    /截图测试超过 5 毫秒未返回/,
  );
});

test("QwenWork 终态进程收口为普通终态保留完整安静窗口", () => {
  assert.deepEqual(terminalProcessCleanupTiming("SUCCEEDED"), {
    quietMilliseconds: 45_000,
    waitMilliseconds: 120_000,
  });
  assert.deepEqual(terminalProcessCleanupTiming("TIMEOUT"), {
    quietMilliseconds: 5_000,
    waitMilliseconds: 10_000,
  });
});

test("QwenWork 超时终态复用同一份进程清理证据", () => {
  const timeoutState = { timeout: { cancellation_confirmed: true } };
  const cleanup = { supported: true, success: true, before: {}, after: {} };
  assert.equal(recordTerminalProcessCleanup(timeoutState, "TIMEOUT", cleanup), cleanup);
  assert.equal(timeoutState.terminal_process_cleanup, cleanup);
  assert.equal(timeoutState.timeout.process_cleanup, cleanup);

  const failedState = { timeout: {} };
  const failedCleanup = { supported: true, success: false, error: "still running" };
  recordTerminalProcessCleanup(failedState, "TIMEOUT", failedCleanup);
  assert.equal(failedState.timeout.process_cleanup, failedCleanup);

  const successState = {};
  recordTerminalProcessCleanup(successState, "SUCCEEDED", cleanup);
  assert.equal(successState.terminal_process_cleanup, cleanup);
  assert.equal(successState.timeout, undefined);
});

test("唯一可见元素等待器拒绝歧义", async () => {
  await assert.rejects(
    waitForUniqueVisible(async () => [{}, {}], 5, "测试控件", 1),
    /数量异常：2/,
  );
});
