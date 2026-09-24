import assert from "node:assert/strict";
import { test } from "node:test";
import { verifyRecoveredDispatchAcknowledgement } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/doubaowork/collector.mjs";
import { sha256Text, summarizePromptReadback } from "../../tools/report/e2e-shared/doubaowork/lib.mjs";

function fixture() {
  const workspace = "/task/workspace", prompt = "original prompt", readback = summarizePromptReadback(prompt), request = "a2e34a61-9c0d-4e01-a1b0-714cdeaaa001";
  const config = { runtime_type: 2, client_option: { workspace }, agent_task_param: { workspace, runtime_type: 2 } };
  const user = { conversation_id: "123", message_id: "456", user_type: 1, status: 1, final_status: { message: "Success" },
    ext: { reply_unique_key: request, conversation_init_option: '{"project_id":"789"}', general_task_param: JSON.stringify(config) },
    content_blocks_v2: [{ block_type: 10000, content: { text_block: { text: prompt } } }] };
  const snapshot = { schema: "wildclawbench.doubaowork-runtime-messages/v1", source: "native-im.useMessageStore.getState",
    observed_at: "2026-09-24T00:01:00Z", conversation_id: "123", maps: { messageMap: { "456": user } } };
  const journal = { workspace, client: { project_id_sha256: sha256Text("789") }, session: { conversation_id: "123", native_request_session_id: request },
    prompt: { readback_sha256: readback.sha256, readback_bytes: readback.bytes }, timing: { sent_at: "2026-09-24T00:00:00Z" },
    send: { acceptance_source: "native-im-user-acknowledgement-observed-during-recovery", accepted_at: snapshot.observed_at,
      dispatch_started_at: "2026-09-24T00:00:00Z", click_returned_at: null,
      recovery_ack: { conversation_id: "123", user_message_id: "456", native_request_session_id: request, observed_at: snapshot.observed_at } } };
  const native = { conversation_id: "123", user_message_id: "456", native_request_session_id: request };
  const seal = () => { snapshot.payload_sha256 = sha256Text(JSON.stringify({ conversation_id: "123", maps: snapshot.maps })); return snapshot; };
  return { snapshot, journal, native, user, seal };
}

test("Recovered native acknowledgement is independently verified for formal collection", () => {
  const f = fixture();
  assert.equal(verifyRecoveredDispatchAcknowledgement(f.seal(), f.journal, f.native).click_returned_at, null);
  delete f.user.ext.reply_unique_key; f.journal.send.recovery_ack.native_request_session_id = null;
  assert.match(verifyRecoveredDispatchAcknowledgement(f.seal(), f.journal, f.native).source, /native-im/);
});

test("Recovered collection rejects modified acknowledgement identity, source and time", () => {
  for (const change of [f => f.user.final_status.message = "Pending", f => f.user.content_blocks_v2[0].content.text_block.text = "other",
    f => f.journal.send.recovery_ack.user_message_id = "other", f => f.native.native_request_session_id = "other",
    f => f.journal.send.accepted_at = "2026-09-24T00:02:00Z", f => f.journal.timing.sent_at = "2026-09-24T00:00:01Z",
    f => f.journal.send.acceptance_source = "manual", f => f.journal.send.click_returned_at = "2026-09-24T00:00:00Z"]) {
    const f = fixture(); change(f);
    assert.throws(() => verifyRecoveredDispatchAcknowledgement(f.seal(), f.journal, f.native), /DOUBAOWORK_/);
  }
});
