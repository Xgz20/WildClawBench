import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { validateManagedPeers } from "../managed-peers.mjs";
const sha = x => createHash("sha256").update(x).digest("hex");
function fixture() {
  const ownTaskId = "task2", runId = "run1", batchId = "batch1", manifestSha = "a".repeat(64);
  const journal = { attempt_id: "attempt1", scene: "web", identity: { task_id: "task1", batch_id: batchId },
    client: { manifest_sha256: manifestSha, version: "2.31.6" },
    prepared: { mode: "web-native-batch-task/v1", run_id: runId }, workspace: "/task1",
    actual: { model: "自动 高" }, send: { dispatch_attempt_count: 1 },
    session: { prompt_readback: { status: "verified" }, conversation_id: "123", native_request_session_id: "11111111-1111-4111-8111-111111111111" } };
  const queue = { schema: "wildclawbench.doubaowork-web-batch/v1", run_id: runId, manifest_sha256: manifestSha,
    model: "自动 高", client_version: "2.31.6", tasks: [
      { task_id: "task1", phase: "RUNNING", task_root: "/task1", attempt_id_sha256: sha("attempt1") },
      { task_id: ownTaskId, phase: "DISPATCHING", task_root: "/task2" }] };
  return { queue, ownTaskId, journals: { task1: journal }, manifestSha, runId, batchId };
}
test("Only exact queued, bound native peers may occupy the background", () => {
  const f = fixture();
  assert.deepEqual(validateManagedPeers(f).peers, [{ task_id: "task1", conversation_id: "123", native_request_session_id: "11111111-1111-4111-8111-111111111111", workspace: "/task1" }]);
  for (const mutate of [x => x.journals.task1.session.native_request_session_id = null,
    x => x.journals.task1.workspace = "/other", x => x.queue.tasks[0].attempt_id_sha256 = sha("other"),
    x => x.queue.model = "other", x => x.journals.task1.send.dispatch_attempt_count = 2,
    x => x.journals.task1.prepared.run_id = "other"]) {
    const next = fixture(); mutate(next); assert.throws(() => validateManagedPeers(next), /PEER_UNBOUND/);
  }
});
