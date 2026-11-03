import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { validateCancelledReview, validateServiceErrorReview } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/park-terminal-review.mjs";
const hash = value => createHash("sha256").update(value).digest("hex");
function fixture() {
  const identity = { task_id: "task", attempt_id: "attempt" }, workspace = "/unit/execution/task/workspace";
  const row = { ...identity, phase: "NEEDS_ATTENTION", dispatch_attempt_count: 1, conversation_id: "session", request_id: "request", cwd: workspace };
  return { row, journal: { identity, phase: "NEEDS_ATTENTION", send: { dispatch_attempt_count: 1 }, prompt: { sha256: hash("frozen"), send_status: "sent" } },
    state: { identity, phase: "NEEDS_ATTENTION" }, promptSha256: hash("frozen"), loaded: { conversation: { id: "session", space: { cwd: workspace }, state: "idle" },
      requestEntries: { requests: [{ id: "request", state: "cancelled", finishTimestamp: 2000,
        userMessage: { state: "completed", content: [{ type: "text", text: "frozen" }] }, assistantMessage: { state: "completed" } }] } },
    sdkRows: [{ type: "message", role: "user", sessionId: "session", cwd: workspace, content: [{ type: "input_text", text: "<user_query>frozen</user_query>" }] },
      { type: "message", role: "assistant", id: "cancel-message", sessionId: "session", cwd: workspace, timestamp: 2001,
        content: [{ type: "output_text", text: "Interrupted by user" }],
        providerData: { skipRun: true, conversationRequestId: "request", error: { message: "Interrupted by user" } } }] };
}
test("native cancellation review proves only terminality and never authors a score or cancellation origin", () => {
  const proof = validateCancelledReview(fixture());
  assert.equal(proof.native_terminal_observed, true);
  assert.equal(proof.cancellation_origin, "unresolved");
  assert.equal(proof.execution_completed, false);
  assert.equal(proof.score_admitted, false);
  assert.equal(proof.prompt_replayed, false);
});
test("active, foreign and mismatched cancellation evidence cannot be parked", () => {
  for (const change of [
    f => { f.loaded.requestEntries.requests[0].state = "streaming"; },
    f => { f.loaded.conversation.state = "working"; },
    f => { f.sdkRows[1].sessionId = "foreign"; },
    f => { f.sdkRows[1].timestamp = 10000; },
    f => { f.journal.prompt.sha256 = hash("different"); },
    f => { f.journal.send.dispatch_attempt_count = 2; },
  ]) { const f = fixture(); change(f); assert.throws(() => validateCancelledReview(f)); }
});
function serviceFixture() {
  const f = fixture(), message = "503 The system is busy, please try again later. (model-request/session)";
  f.loaded.conversation.state = "error";
  f.loaded.requestEntries.historyReady = true; f.loaded.requestEntries.hasOlder = false;
  const r = f.loaded.requestEntries.requests[0]; r.state = "error"; r.assistantMessage.state = "error"; r.traceId = "trace";
  r.terminalError = { statusCode: 503, bizCode: 10310, category: "network", requestId: "request", traceId: "trace", details: message };
  const last = f.sdkRows.at(-1); last.timestamp = 5000; last.content[0].text = message;
  last.providerData.agent = "cli"; last.providerData.error = { status: 503, code: 10310, message,
    isNetworkError: false, isStreamTimeout: false, isRetryable: false };
  return f;
}
test("an exact native 503 service error may be parked without a score or retry", () => {
  const proof = validateServiceErrorReview(serviceFixture());
  assert.equal(proof.profile, "workbuddy-native-service-error-503-terminal-review/v1");
  assert.equal(proof.native_terminal_observed, true);
  assert.equal(proof.execution_completed, false); assert.equal(proof.score_admitted, false);
  assert.equal(proof.retry_authorized, false); assert.equal(proof.prompt_replayed, false);
  assert.equal(proof.sdk_terminal_timestamp, 5000); assert.equal(proof.runtime_finish_timestamp, 2000);
});
test("service review refuses running requests, quota errors, changed messages and foreign scope", () => {
  for (const change of [
    f => { f.loaded.requestEntries.requests[0].state = "streaming"; },
    f => { f.loaded.requestEntries.requests[0].terminalError.statusCode = 429; },
    f => { f.loaded.requestEntries.requests[0].terminalError.details = "other"; },
    f => { f.sdkRows.at(-1).providerData.error.code = 402; },
    f => { f.sdkRows.at(-1).providerData.conversationRequestId = "foreign"; },
    f => { f.sdkRows.at(-1).timestamp = 1000; },
    f => { f.sdkRows.at(-1).content[0].text = "fabricated"; },
  ]) { const f = serviceFixture(); change(f); assert.throws(() => validateServiceErrorReview(f)); }
});
test("rehydrated 503 errors require exact persisted code, status and message without inventing category", () => {
  const f = serviceFixture(), error = f.loaded.requestEntries.requests[0].terminalError;
  delete error.category; error.code = 0; error.message = error.details;
  error.raw = JSON.stringify({ code: 0, message: error.message,
    data: { code: 10310, statusCode: 503, details: error.details } });
  assert.equal(validateServiceErrorReview(f).service_error.status, 503);
  assert.equal(error.category, undefined);
  const wrong = structuredClone(f); wrong.loaded.requestEntries.requests[0].terminalError.raw = JSON.stringify({ code: 0, data: { code: 402, statusCode: 503 } });
  assert.throws(() => validateServiceErrorReview(wrong), /SERVICE_RUNTIME_ERROR_INVALID/);
  const foreign = structuredClone(f); foreign.loaded.requestEntries.requests[0].terminalError.category = "policy";
  assert.throws(() => validateServiceErrorReview(foreign), /SERVICE_RUNTIME_ERROR_INVALID/);
});
