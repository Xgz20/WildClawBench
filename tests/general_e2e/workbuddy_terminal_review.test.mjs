import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { validateCancelledReview } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/park-terminal-review.mjs";
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
