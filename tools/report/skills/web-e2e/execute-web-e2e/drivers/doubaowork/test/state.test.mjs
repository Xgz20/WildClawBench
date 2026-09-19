import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  assertAttemptState,
  atomicWriteAttemptState,
  bindConversation,
  confirmModel,
  confirmPermission,
  confirmWorkspaceReadback,
  createAttemptState,
  decideResume,
  findNewConversationCandidate,
  persistBeforeDispatch,
  readAttemptState,
  recordDispatchStart,
  recordPreSendBaselines,
  recordPromptAccepted,
  recordSendIntent,
  transitionAttempt,
} from "../state.mjs";

const TIMES = {
  prepared: "2026-09-19T08:00:00.000Z",
  client: "2026-09-19T08:00:01.000Z",
  workspace: "2026-09-19T08:00:02.000Z",
  permission: "2026-09-19T08:00:03.000Z",
  model: "2026-09-19T08:00:04.000Z",
  intent: "2026-09-19T08:00:05.000Z",
  dispatch: "2026-09-19T08:00:06.000Z",
  accepted: "2026-09-19T08:00:07.000Z",
};

function preparedState(now = TIMES.prepared) {
  return createAttemptState({
    attemptId: "attempt-fixture",
    batchId: "batch-fixture",
    taskId: "task-fixture",
    workspace: "/Users/fixture/debug/task/workspace",
    promptFile: "/Users/fixture/debug/task/prompt.md",
    prompt: "fixture prompt",
    baselineConversationIds: ["11111111111111111"],
    baselineSessionDirectoryIds: ["11111111111111111"],
    now,
  });
}

function readyState() {
  const state = preparedState();
  transitionAttempt(state, "CLIENT_READY", {}, TIMES.client);
  confirmWorkspaceReadback(state, "~/debug/task/workspace", "/Users/fixture", TIMES.workspace);
  confirmPermission(state, "按需确认", TIMES.permission);
  confirmModel(state, "自动 高", TIMES.model);
  recordPreSendBaselines(state, {
    conversationIds: ["11111111111111111"],
    sessionDirectoryIds: ["11111111111111111"],
  }, TIMES.model);
  recordSendIntent(state, TIMES.intent);
  return state;
}

test("发送前必须完成 workspace、权限和模型回读", () => {
  const state = preparedState();
  assert.throws(() => recordSendIntent(state, TIMES.intent), /MODEL_CONFIRMED/);
  transitionAttempt(state, "CLIENT_READY", {}, TIMES.client);
  assert.throws(
    () => confirmWorkspaceReadback(state, "~/wrong/workspace", "/Users/fixture", TIMES.workspace),
    /不一致/,
  );
  confirmWorkspaceReadback(state, "~/debug/task/workspace", "/Users/fixture", TIMES.workspace);
  confirmPermission(state, "按需确认", TIMES.permission);
  confirmModel(state, "自动 高", TIMES.model);
  recordPreSendBaselines(state, {
    conversationIds: ["11111111111111111"],
    sessionDirectoryIds: ["11111111111111111"],
  }, TIMES.model);
  recordSendIntent(state, TIMES.intent);
  assert.equal(state.phase, "READY_TO_SEND");
  assert.equal(state.send.dispatch_attempt_count, 0);
  assert.equal(Object.hasOwn(state.prompt, "plaintext"), false);
});

test("dispatch attempt 在 UI click 前原子落盘且禁止第二次发送", async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-state-"));
  context.after(async () => {
    const { rm } = await import("node:fs/promises");
    await rm(root, { recursive: true, force: true });
  });
  const stateFile = join(root, "automation_state.json");
  const state = readyState();
  await persistBeforeDispatch(stateFile, state, TIMES.dispatch);
  const disk = JSON.parse(await readFile(stateFile, "utf8"));
  assert.equal(disk.phase, "READY_TO_SEND");
  assert.equal(disk.send.dispatch_attempt_count, 1);
  assert.equal(disk.send.dispatch_started_at, TIMES.dispatch);
  assert.throws(() => recordDispatchStart(state, TIMES.dispatch), /第二次发送/);
});

test("dispatch journal 写盘失败后保持禁止发送", async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-state-failure-"));
  context.after(async () => {
    const { rm } = await import("node:fs/promises");
    await rm(root, { recursive: true, force: true });
  });
  const state = readyState();
  await assert.rejects(
    () => persistBeforeDispatch(join(root, "automation_state.json"), state, TIMES.dispatch, {
      writeFile: async () => {
        throw new Error("fixture write failed");
      },
    }),
    /fixture write failed/,
  );
  assert.equal(state.send.dispatch_attempt_count, 1);
  assert.equal(decideResume(state).allow_send, false);
});

test("发送接受后只能进入 PROMPT_SENT 并继续观察", () => {
  const state = readyState();
  recordDispatchStart(state, TIMES.dispatch);
  recordPromptAccepted(state, {}, TIMES.accepted);
  assert.equal(state.phase, "PROMPT_SENT");
  assert.equal(state.timing.sent_at, TIMES.dispatch);
  assert.deepEqual(decideResume(state), {
    action: "needs-attention",
    allow_send: false,
    reason: "send-status-uncertain",
  });
});

test("READY_TO_SEND 的发送临界区按落盘计数区分", () => {
  const safe = readyState();
  assert.deepEqual(decideResume(safe), {
    action: "dispatch-once",
    allow_send: true,
    reason: "dispatch-start-not-persisted",
  });
  recordDispatchStart(safe, TIMES.dispatch);
  assert.equal(decideResume(safe).action, "needs-attention");
  assert.equal(decideResume(safe).allow_send, false);
});

test("发送后只在 UI 新 ID 与原生 session 目录唯一一致时绑定", () => {
  const state = readyState();
  recordDispatchStart(state, TIMES.dispatch);
  const candidate = findNewConversationCandidate(
    state,
    ["11111111111111111", "22222222222222222"],
    ["22222222222222222"],
  );
  assert.deepEqual(candidate, { status: "unique", conversation_id: "22222222222222222" });
  assert.deepEqual(decideResume(state, {
    visibleConversationIds: ["11111111111111111", "22222222222222222"],
    sessionDirectoryIds: ["22222222222222222"],
  }), {
    action: "bind-and-observe",
    allow_send: false,
    reason: "one-new-ui-and-session-directory-id",
    conversation_id: "22222222222222222",
  });
  assert.equal(findNewConversationCandidate(
    state,
    ["22222222222222222", "33333333333333333"],
    ["22222222222222222", "33333333333333333"],
  ).status, "ambiguous");
  assert.equal(findNewConversationCandidate(
    state,
    ["11111111111111111", "22222222222222222"],
    ["11111111111111111", "33333333333333333"],
  ).status, "mismatch");
  assert.equal(findNewConversationCandidate(
    state,
    ["11111111111111111", "22222222222222222", "33333333333333333"],
    ["11111111111111111", "22222222222222222"],
  ).status, "ambiguous");
});

test("状态拒绝非法时间、发送时间错配和发送前 session 绑定", () => {
  assert.throws(() => preparedState("invalid"), /无效状态时间/);
  const state = readyState();
  assert.throws(() => bindConversation(state, {
    conversationId: "22222222222222222",
    sessionDirectoryId: "22222222222222222",
  }), /发送尝试/);
  recordDispatchStart(state, TIMES.dispatch);
  recordPromptAccepted(state, {}, TIMES.accepted);
  state.timing.sent_at = TIMES.accepted;
  assert.throws(() => assertAttemptState(state), /sent_at 必须等于/);
});

test("绑定原生 session 后仍保持 cwd/turn 未验证并禁止重发", () => {
  const state = readyState();
  recordDispatchStart(state, TIMES.dispatch);
  recordPromptAccepted(state, {}, TIMES.accepted);
  bindConversation(state, {
    conversationId: "22222222222222222",
    sessionDirectoryId: "22222222222222222",
    evidence: [{ kind: "session-directory", sha256: "a".repeat(64) }],
  }, "2026-09-19T08:00:08.000Z");
  assert.equal(state.session.binding_status, "tentative");
  assert.equal(state.session.turn_id, null);
  assert.equal(state.session.native_cwd, null);
  assert.deepEqual(decideResume(state, {
    visibleConversationIds: ["22222222222222222"],
    sessionDirectoryIds: ["22222222222222222"],
  }), {
    action: "observe-only",
    allow_send: false,
    reason: "persisted-session-reconfirmed",
  });
  assert.equal(decideResume(state, {
    visibleConversationIds: [],
    sessionDirectoryIds: ["22222222222222222"],
  }).action, "needs-attention");
});

test("state 读取拒绝符号链接，普通文件可 round-trip", async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-state-file-"));
  context.after(async () => {
    const { rm } = await import("node:fs/promises");
    await rm(root, { recursive: true, force: true });
  });
  const stateFile = join(root, "state", "automation_state.json");
  const state = readyState();
  await atomicWriteAttemptState(stateFile, state);
  assert.equal((await readAttemptState(stateFile)).attempt_id, "attempt-fixture");
  const link = join(root, "state-link.json");
  await symlink(stateFile, link);
  await assert.rejects(() => readAttemptState(link), /普通文件/);
  await mkdir(join(root, "directory-state"));
  await assert.rejects(() => readAttemptState(join(root, "directory-state")), /普通文件/);
});
