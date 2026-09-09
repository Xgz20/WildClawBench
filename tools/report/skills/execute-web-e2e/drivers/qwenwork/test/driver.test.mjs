import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseQwenAttemptSession,
  hasStableConversationId,
  inspectPendingAttention,
  openQwenProjectConversation,
  qwenStopControlLocator,
  qwenProjectSidebarLabel,
  restartQwenWork,
  waitForUniqueVisible,
} from "../driver.mjs";
import {
  createInitialState,
  DEFAULT_APP_PATH,
  DEFAULT_ENDPOINT,
  DEFAULT_SESSION_DB,
  parseArgs,
} from "../lib.mjs";

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
  assert.equal(state.driver.version, "1.9.7");
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

test("QwenWork 只在待处理面板或对话框中识别授权按钮", async () => {
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
  assert.match(requestedContainer, /pending-sandbox-panel/);
  assert.match(requestedContainer, /role="dialog"/);
  assert.equal(requestedRole, "button");
});

test("QwenWork 停止按钮兼容 1.0.4 无无障碍名称的圆角方形图标", () => {
  const expected = {};
  const page = {
    locator(selector) {
      assert.match(selector, /aria-label\*="停止"/);
      assert.match(selector, /aria-label\*="Stop"/);
      assert.match(selector, /path\[d\^="M3 10\.2556C3 7\.15979"\]/);
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
      run: async (command) => {
        if (command === "/usr/bin/open") launched = true;
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

test("唯一可见元素等待器拒绝歧义", async () => {
  await assert.rejects(
    waitForUniqueVisible(async () => [{}, {}], 5, "测试控件", 1),
    /数量异常：2/,
  );
});
