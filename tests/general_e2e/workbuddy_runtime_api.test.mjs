import assert from "node:assert/strict";
import test from "node:test";

import {
  buildWorkBuddyRuntimeSnapshot,
  loadWorkBuddyRuntimeConversation,
} from "../../eval_general_e2e/adapters/workbuddy/runtime-api.mjs";
import { normalizeWorkBuddyConversation } from "../../eval_general_e2e/adapters/workbuddy/native-history.mjs";
import { buildWorkBuddyExecutionState } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/state.mjs";

const identity = {
  batch_id: "batch-runtime",
  unit_id: "unit-runtime",
  task_id: "task-runtime",
  attempt_id: "attempt-runtime",
};

function fixture() {
  const conversation = {
    id: "767b5a15-60d4-4ffe-97c7-c663b79c207b",
    title: "runtime fixture",
    state: "idle",
    lifecycle: "completed",
    space: { type: "local", cwd: "/tmp/workbuddy-runtime-fixture" },
    updatedAt: 1789913249110,
    lastActivityAt: 1789913248896,
  };
  const request = {
    id: "req-1789913211484001",
    traceId: "da13e17eaf8448958b38d22c0c0a6584",
    timestamp: 1789913212279,
    userMessage: {
      type: "text",
      content: [{ type: "text", text: "创建 fixture 文件\n" }],
      state: "completed",
    },
    assistantMessage: {
      type: "text",
      content: [{
        sessionUpdate: "tool_call_update",
        messageId: "message-1",
        toolCallId: "call-1",
        status: "completed",
        rawInput: { file_path: "/tmp/workbuddy-runtime-fixture/a.txt", content: "ok" },
        title: "Write",
        type: "tool",
        rawOutput: { type: "text", text: "created" },
        _meta: { "codebuddy.ai/toolName": "Write" },
      }, {
        type: "text",
        text: "已完成",
        messageId: "message-1",
      }],
      state: "completed",
    },
    state: "completed",
    usage: {},
    finishTimestamp: 1789913248885,
    completedAt: 1789913248896,
  };
  return buildWorkBuddyRuntimeSnapshot({
    conversation,
    request,
    requestEntries: {
      requests: [request],
      entries: [
        { kind: "request-message", requestId: request.id, role: "user" },
        { kind: "request-message", requestId: request.id, role: "assistant" },
      ],
      totalRequests: 1,
      historyReady: true,
      historyKnownEmpty: false,
    },
    capturedAt: "2026-09-20T00:00:00.000Z",
  });
}

test("WorkBuddy runtime snapshot normalizes prompt, tool pair, final response and unavailable usage", () => {
  const loaded = loadWorkBuddyRuntimeConversation({
    snapshot: fixture(),
    sourceArtifact: { path: "/tmp/runtime-binding.json", sha256: "a".repeat(64), size: 1 },
  });
  const normalized = normalizeWorkBuddyConversation(loaded, { identity, redacted: true });
  assert.equal(normalized.completeness.status, "complete");
  assert.equal(normalized.prompt.content, "创建 fixture 文件\n");
  assert.equal(normalized.final_response, "已完成");
  assert.deepEqual(normalized.events.map((event) => event.type), [
    "user_message", "tool_call", "tool_result", "assistant_message",
  ]);
  assert.equal(normalized.calls.length, 1);
  assert.equal(normalized.calls[0].call_id, "call-1");
  assert.equal(normalized.resources.primary_request.total_tokens.value, null);
  assert.equal(normalized.resources.primary_request.total_tokens.status, "unavailable");
});

test("WorkBuddy runtime snapshot keeps an incomplete request fail-closed", () => {
  const snapshot = fixture();
  snapshot.request.state = "running";
  snapshot.request.assistantMessage.state = "running";
  const loaded = loadWorkBuddyRuntimeConversation({ snapshot });
  const normalized = normalizeWorkBuddyConversation(loaded, { identity });
  assert.equal(normalized.completeness.status, "partial");
  assert.ok(normalized.completeness.missing.includes("request_terminal_state:running"));
});

test("WorkBuddy 5.5.6 active/idle conversation with completed request is terminal", () => {
  const snapshot = fixture();
  snapshot.conversation.state = "idle";
  snapshot.conversation.lifecycle = "active";
  const loaded = loadWorkBuddyRuntimeConversation({ snapshot });
  const normalized = normalizeWorkBuddyConversation(loaded, { identity });
  const state = buildWorkBuddyExecutionState({
    identity,
    dataset: { id: "dataset", digest: "d".repeat(64) },
    taskRoot: "/tmp/workbuddy-runtime-fixture",
    candidateWorkspace: "/tmp/workbuddy-runtime-fixture",
    prompt: {
      path: "/tmp/workbuddy-runtime-fixture/PROMPT.md",
      sha256: normalized.prompt.sha256,
      send_status: "sent",
      sent_at: "2026-09-20T00:00:00.000Z",
    },
    send: { dispatch_attempt_count: 1 },
    sessionSnapshot: {
      conversation_id: loaded.conversation_id,
      cwd: loaded.workspace,
      status: "completed",
    },
    history: {
      ...normalized,
      binding: {
        ...normalized.binding,
        source_kind: "workbuddy-runtime-api",
      },
      runtime_terminal: {
        request_state: "success",
        user_message_state: "success",
        assistant_message_state: "success",
        conversation_state: "success",
        conversation_lifecycle: "running",
      },
    },
    bindingEvidence: [{ path: "binding.json", sha256: "a".repeat(64), size: 1 }],
  });
  assert.equal(state.phase, "COMPLETED");
});
