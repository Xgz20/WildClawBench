import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  classifyDomObservation,
  isDoubaoWorkChatTarget,
  normalizeWorkspaceReadback,
  parseConversationId,
  parseLoopbackEndpoint,
  selectUniqueChatTarget,
  summarizeTarget,
  unavailableUsage,
  validateSessionId,
  workspaceReadbackMatches,
} from "../lib.mjs";

test("只接受带显式端口的 loopback CDP endpoint", () => {
  assert.equal(parseLoopbackEndpoint("http://127.0.0.1:9260").origin, "http://127.0.0.1:9260");
  assert.throws(() => parseLoopbackEndpoint("https://127.0.0.1:9260"), /loopback/);
  assert.throws(() => parseLoopbackEndpoint("http://example.com:9260"), /loopback/);
  assert.throws(() => parseLoopbackEndpoint("http://127.0.0.1"), /loopback/);
  assert.throws(() => parseLoopbackEndpoint("http://127.0.0.1:9260/json/list"), /loopback/);
});

test("兼容 discovery 与 Playwright 两种 chat scheme 并拒绝多 target", async () => {
  const targets = JSON.parse(await readFile(new URL("fixtures/probe-targets.json", import.meta.url), "utf8"));
  const selected = selectUniqueChatTarget(targets);
  assert.equal(parseConversationId(selected.url), "12345678901234567");
  assert.equal(isDoubaoWorkChatTarget("chrome://doubaowork-chat/chat/12345678901234567"), true);
  assert.equal(isDoubaoWorkChatTarget({ type: "other", url: "doubaowork://doubaowork-chat/" }), false);
  assert.throws(() => selectUniqueChatTarget([...targets, {
    type: "page",
    url: "chrome://doubaowork-chat/chat/76543210987654321",
  }]), /实际为 2/);
});

test("target 摘要不保存真实 conversation ID", () => {
  const summary = summarizeTarget({ type: "page", url: "chrome://doubaowork-chat/chat/12345678901234567" });
  assert.equal(summary.path_kind, "chat-with-numeric-id");
  assert.equal(summary.conversation_id_length, 17);
  assert.equal(Object.values(summary).includes("12345678901234567"), false);
});

test("workspace 回读只展开开头的 ~/ 并做完整路径比较", () => {
  assert.equal(
    normalizeWorkspaceReadback("~/debug/task/workspace", "/Users/fixture"),
    "/Users/fixture/debug/task/workspace",
  );
  assert.equal(
    workspaceReadbackMatches("~/debug/task/workspace", "/Users/fixture/debug/task/workspace", "/Users/fixture"),
    true,
  );
  assert.throws(() => normalizeWorkspaceReadback("~fixture/task", "/Users/fixture"), /只允许展开/);
  assert.throws(() => normalizeWorkspaceReadback("workspace", "/Users/fixture"), /绝对路径/);
});

test("DOM 完成只标为不可信候选", () => {
  assert.deepEqual(
    classifyDomObservation({ finalAssistantVisible: true, replyActionsVisible: true }),
    { kind: "ui-completion-candidate", trusted: false },
  );
  assert.deepEqual(
    classifyDomObservation({ stopControlVisible: true }),
    { kind: "running", trusted: false },
  );
});

test("缺失 usage 保持 null 而不是零", () => {
  const usage = unavailableUsage("fixture");
  assert.equal(usage.total_tokens.value, null);
  assert.equal(usage.total_tokens.status, "unavailable");
  assert.equal(usage.request_count.value, null);
});

test("session ID 只接受原生数字 ID", () => {
  assert.equal(validateSessionId("12345678901234567"), "12345678901234567");
  assert.throws(() => validateSessionId("task-id"), /数字/);
  assert.throws(() => validateSessionId("../../escape"), /数字/);
});
