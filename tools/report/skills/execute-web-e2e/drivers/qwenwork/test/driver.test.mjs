import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseQwenAttemptSession,
  hasStableConversationId,
  inspectPendingAttention,
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
  assert.equal(state.driver.version, "1.9.3");
});

test("QwenWork 只有同时捕获 chat 和稳定内核 session 才允许后台恢复", () => {
  assert.equal(hasStableConversationId({ session: { conversation_id: "chat", session_id: null } }), false);
  assert.equal(hasStableConversationId({ session: { conversation_id: "chat", session_id: "session" } }), true);
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

test("唯一可见元素等待器拒绝歧义", async () => {
  await assert.rejects(
    waitForUniqueVisible(async () => [{}, {}], 5, "测试控件", 1),
    /数量异常：2/,
  );
});
