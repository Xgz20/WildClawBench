import assert from "node:assert/strict";
import { test } from "node:test";
import { createAttemptState, transitionAttempt, confirmWorkspaceReadback, confirmPermission, confirmModel,
  recordSendIntent, recordDispatchStart, bindConversation, confirmConversationPromptReadback,
  recordRecoveredPromptAcknowledgement, decideResume } from "../../tools/report/e2e-shared/doubaowork/state.mjs";

function fixture() {
  const at = "2026-09-24T00:00:00.000Z";
  const state = createAttemptState({ attemptId: "original-attempt", batchId: "batch", taskId: "task", workspace: "/task/workspace",
    promptFile: "/task/PROMPT.md", prompt: "original prompt", now: at });
  transitionAttempt(state, "CLIENT_READY", {}, at); confirmWorkspaceReadback(state, "/task/workspace", "/home", at);
  confirmPermission(state, "current-permission", at); confirmModel(state, "current-model", at); recordSendIntent(state, at); recordDispatchStart(state, at);
  bindConversation(state, { conversationId: "123", sessionDirectoryId: "123" }, at);
  const prompt = { sha256: state.prompt.readback_sha256, bytes: state.prompt.readback_bytes, normalization: state.prompt.readback_normalization };
  confirmConversationPromptReadback(state, prompt, at);
  return { state, native: { conversation_id: "123", user_message_id: "456", native_request_session_id: "request", prompt, binding_status: "acknowledged-user-input" },
    artifact: { file: "native-ack.json", sha256: "a".repeat(64), size_bytes: 100 }, at: "2026-09-24T00:00:10.000Z" };
}

test("A native acknowledgement recovers the original dispatch boundary without inventing a click return", () => {
  const f = fixture(); assert.equal(f.state.timing.sent_at, null);
  assert.equal(recordRecoveredPromptAcknowledgement(f.state, f.native, f.artifact, f.at), true);
  assert.equal(f.state.attempt_id, "original-attempt"); assert.equal(f.state.send.dispatch_attempt_count, 1);
  assert.equal(f.state.send.click_returned_at, null); assert.equal(f.state.timing.sent_at, f.state.send.dispatch_started_at);
  assert.equal(f.state.send.accepted_at, f.at); assert.match(f.state.send.acceptance_source, /recovery/);
  assert.equal(recordRecoveredPromptAcknowledgement(f.state, f.native, f.artifact, f.at), false);
  assert.equal(decideResume(f.state, { visibleConversationIds: ["123"], sessionDirectoryIds: ["123"] }).allow_send, false);
  assert.throws(() => recordDispatchStart(f.state), /READY_TO_SEND|第二次/);
});

test("Unverified, foreign, unbound and pre-dispatch acknowledgements cannot certify a send", () => {
  for (const mutate of [f => f.native.binding_status = "unknown", f => f.native.conversation_id = "999",
    f => f.native.prompt.sha256 = "b".repeat(64), f => f.state.session.prompt_readback.status = "unverified",
    f => f.artifact.file = "../outside.json", f => f.at = "2026-09-23T00:00:00.000Z"]) {
    const f = fixture(); mutate(f);
    assert.throws(() => recordRecoveredPromptAcknowledgement(f.state, f.native, f.artifact, f.at), /UNVERIFIED/);
    assert.equal(f.state.send.accepted_at, null); assert.equal(f.state.timing.sent_at, null);
  }
  const f = fixture();
  assert.throws(() => recordRecoveredPromptAcknowledgement(f.state, f.native, f.artifact), /recovery.observed_at/);
});
