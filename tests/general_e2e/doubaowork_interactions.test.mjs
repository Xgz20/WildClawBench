import assert from "node:assert/strict";
import { test } from "node:test";
import { inspectNativeAuthorizationHistory, summarizePendingConfirmations } from "../../tools/report/e2e-shared/doubaowork/interactions.mjs";
import { assertNoConflictingActivity, canAcceptNativeCompletion, classifyDevelopmentObservation } from "../../tools/report/e2e-shared/doubaowork/controller.mjs";
import { sha256Text } from "../../tools/report/e2e-shared/doubaowork/lib.mjs";

const base = { stop_control_count: 0, busy_conversation_count: 0, busy_conversation_ids: [], bound_conversation_busy_count: 0,
  visible_dialog_count: 0, user_question_count: 0, approval_count: 0, visible_error_count: 0 };
test("A native pending marker blocks new sends even for a registered peer; only bound readback pauses", () => {
  const facts = [{ id: "123", pending_confirmation: true }, { id: "123", pending_confirmation: true }, { id: "456", pending_confirmation: false }];
  const summary = summarizePendingConfirmations(facts, "123");
  assert.deepEqual(summary, { conversation_ids: ["123"], count: 1, unknown_count: 0, bound_pending: true });
  assert.equal(summarizePendingConfirmations(facts, "456").bound_pending, false);
  assert.equal(summarizePendingConfirmations([{ id: null, pending_confirmation: true }], "123").unknown_count, 1);
  assert.throws(() => assertNoConflictingActivity({ ...base, native_confirmation_count: 1 }, ["123"]), /拒绝/);
  assert.throws(() => assertNoConflictingActivity({ ...base, native_confirmation_unknown_count: 1 }), /拒绝/);
  const blocked = { ...base, bound_native_confirmation_pending: true };
  assert.equal(canAcceptNativeCompletion(blocked, { terminal: "completed" }), false);
  assert.equal(classifyDevelopmentObservation(blocked).kind, "needs-attention");
});

function fixture() {
  const requestId = "bound-request";
  const card = { block_type: 10080, is_finish: false, content: { quick_reply_block: { scene: 2, status: 1,
    items: [1010, 1011].map(action_type => ({ action_type, schema_payload: JSON.stringify({ agent_id: requestId, tool_call_id: "call" }) })) } } };
  const snapshot = { schema: "wildclawbench.doubaowork-runtime-messages/v1", source: "native-im.useMessageStore.getState",
    conversation_id: "123", maps: { messageMap: {}, localMessageMap: { reply: { user_type: 2, content_blocks_v2: [card] } } } };
  const seal = () => { snapshot.payload_sha256 = sha256Text(JSON.stringify({ conversation_id: snapshot.conversation_id, maps: snapshot.maps })); return snapshot; };
  return { requestId, snapshot, card, seal };
}
test("Native permission history is retained after resolution, without retaining callback secrets", () => {
  const f = fixture();
  const pending = inspectNativeAuthorizationHistory(f.seal(), f.requestId);
  assert.equal(pending.length, 2); assert.equal(pending[0].block_finished, false);
  assert.equal(Object.hasOwn(pending[0], "schema_payload"), false);
  f.card.is_finish = true; f.card.content.quick_reply_block.status = 2;
  f.snapshot.maps.messageMap = f.snapshot.maps.localMessageMap; f.snapshot.maps.localMessageMap = {};
  assert.equal(inspectNativeAuthorizationHistory(f.seal(), f.requestId).length, 2);
});
test("Forged, foreign and unsupported confirmation evidence fails closed", () => {
  for (const alter of [f => f.card.content.quick_reply_block.scene = 999,
    f => f.card.content.quick_reply_block.items[0].schema_payload = "not-json",
    f => f.requestId = "other-request"]) {
    const f = fixture(); alter(f); assert.throws(() => inspectNativeAuthorizationHistory(f.seal(), f.requestId), /DOUBAOWORK_/);
  }
  const f = fixture(); f.seal(); f.snapshot.payload_sha256 = "wrong";
  assert.throws(() => inspectNativeAuthorizationHistory(f.snapshot, f.requestId), /SOURCE_INVALID/);
  assert.throws(() => inspectNativeAuthorizationHistory(f.seal(), null), /SOURCE_INVALID/);
  f.card.content.quick_reply_block.items = [{ action_type: 1, text: "ordinary suggestion" }];
  assert.deepEqual(inspectNativeAuthorizationHistory(f.seal(), f.requestId), []);
});
