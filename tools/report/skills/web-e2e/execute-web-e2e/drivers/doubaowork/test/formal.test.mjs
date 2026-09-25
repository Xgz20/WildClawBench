import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { assessDoubaoNativeWebFinalization } from "../finalizer.mjs";
import { projectWebMetrics } from "../formal.mjs";
import { publishFrozenTransaction } from "../publication.mjs";
import { snapshotTree } from "../../workbuddy/lib.mjs";
const hash = b => createHash("sha256").update(b).digest("hex");
function fixture() {
  return { state: { scene: "web", send: { dispatch_attempt_count: 1 }, workspace: "/fixture/task", identity: {},
    session: { prompt_readback: { status: "verified" }, conversation_id: "123", native_request_session_id: "native-request" } },
    native: { terminal: "completed", finished_at: "2026-09-25T00:00:00.000Z", conversation_id: "123", native_cwd: "/fixture/task", native_request_session_id: "native-request" },
    observation: { native_frontend_activity: { initialized: true, active: [] }, native_background_activity: { initialized: true, active: [] }, binding: { status: "verified" }, classification: { trusted: true }, ui: { current_conversation_id: "123",
      stop_control_count: 0, bound_conversation_busy_count: 0, visible_dialog_count: 0, user_question_count: 0, approval_count: 0,
      native_confirmation_unknown_count: 0, bound_native_confirmation_pending: false, bound_tool_delivery_active: false } },
    cleanup: { supported: true, success: true, tracked_residue: [], after: { targets: [] }, quiet_window_milliseconds: 2000, quiet_observed_milliseconds: 2001 },
    candidate: { frozen: true, sha256: "a".repeat(64) } };
}
test("Formal Web gate rejects missing native binding, active delivery, cleanup and candidate drift", () => {
  assert.equal(assessDoubaoNativeWebFinalization(fixture()).integrity.valid, true);
  for (const mutate of [f => f.native.native_cwd += "/foreign", f => f.native.conversation_id = "456", f => f.native.terminal = "running",
    f => f.observation.classification.trusted = false, f => f.observation.ui.bound_tool_delivery_active = true,
    f => delete f.observation.ui.native_confirmation_unknown_count, f => f.cleanup.after.targets.push({ pid: 10 }),
    f => f.cleanup.quiet_observed_milliseconds = 1, f => f.candidate.frozen = false]) {
    const f = fixture(); mutate(f); assert.equal(assessDoubaoNativeWebFinalization(f).integrity.valid, false);
  }
});
test("Web metrics keep unavailable token totals and distinguish tool subtotal and native timing", () => {
  const proof = { journal: { timing: { sent_at: "2026-09-25T00:00:00Z" } }, native: { agent_duration_seconds: 4,
    raw_terminal: { profile: "native-im-api-history/v1" }, sources: {} }, lifecycle: null, unknownBlocks: [], remoteCoverageVerified: false };
  const metrics = projectWebMetrics(proof, 3);
  assert.equal(metrics.usage.total_tokens, null); assert.equal(metrics.usage.request_count, null);
  assert.equal(metrics.duration_seconds, null); assert.equal(metrics.execution.agent_duration_seconds, 4);
  assert.equal(metrics.tools.call_count, null); assert.equal(metrics.collection.known_subtotals.call_count, 3);
  assert.equal(metrics.collection.tool_coverage.denominator, null);
});
async function transactionFixture(t) {
  const root = await mkdtemp(join(tmpdir(), "doubao-web-publication-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  // macOS /var -> /private/var must be canonical to exercise the production gate.
  const { realpath } = await import("node:fs/promises"); const canonical = await realpath(root);
  const output = join(canonical, "control"); await mkdir(output); await mkdir(join(canonical, "workspace"));
  await writeFile(join(canonical, "workspace/index.html"), "candidate");
  await writeFile(join(output, "raw.json"), "frozen"); await writeFile(join(output, "journal.json"), "bound");
  const txn = { schema: "wildclawbench.doubaowork-web-publication/v1", harness_root: canonical, attempt_id: "one",
    candidate_path: "workspace", candidate_sha256: (await snapshotTree(join(canonical, "workspace"))).sha256,
    prerequisites: [{ path: "control/journal.json", sha256: hash("bound") }],
    files: [{ path: "evidence/frozen.json", staged_path: "control/raw.json", sha256: hash("frozen") },
      { path: "execution-receipt.json", staged_path: "control/raw.json", sha256: hash("frozen") }] };
  await writeFile(join(output, "formal-transaction.json"), JSON.stringify(txn)); return { root: canonical, output, txn };
}
test("Interrupted publication resumes frozen bytes without overwriting an existing evidence file", async t => {
  const f = await transactionFixture(t); await mkdir(join(f.root, "evidence"));
  await writeFile(join(f.root, "evidence/frozen.json"), "frozen");
  await publishFrozenTransaction(f.output);
  assert.equal(await readFile(join(f.root, "execution-receipt.json"), "utf8"), "frozen");
});
test("Publication rejects changed candidate and conflicting target before creating a receipt", async t => {
  const f = await transactionFixture(t); await writeFile(join(f.root, "workspace/index.html"), "changed");
  await assert.rejects(() => publishFrozenTransaction(f.output), /CANDIDATE_DRIFT/);
  await assert.rejects(() => readFile(join(f.root, "execution-receipt.json")), { code: "ENOENT" });
  await writeFile(join(f.root, "workspace/index.html"), "candidate"); await mkdir(join(f.root, "evidence"));
  await writeFile(join(f.root, "evidence/frozen.json"), "foreign");
  await assert.rejects(() => publishFrozenTransaction(f.output), /TARGET_CONFLICT/);
});

test("Concurrent formalization admits only fully bound other-task activity", () => {
  const f = fixture();
  f.observation.native_frontend_activity.active = [{ session_id: "peer-request", conversation_ids: ["789"] }];
  f.observation.native_background_activity.active = [{ context_verified: true, native_request_session_id: "peer-request",
    conversation_ids: ["789"], native_cwd: "/peer/task", tool_call_id: "tool" }];
  const peer = { conversation_id: "789", native_request_session_id: "peer-request", workspace: "/peer/task" };
  assert.equal(assessDoubaoNativeWebFinalization({ ...f, allowedBackgroundPeers: [peer] }).integrity.valid, true);
  assert.equal(assessDoubaoNativeWebFinalization(f).integrity.valid, false);
  f.observation.native_background_activity.active[0].native_cwd = "/foreign/task";
  assert.equal(assessDoubaoNativeWebFinalization({ ...f, allowedBackgroundPeers: [peer] }).integrity.valid, false);
  f.observation.native_background_activity.active[0].native_cwd = "/peer/task";
  f.observation.native_frontend_activity.active[0].session_id = "foreign-request";
  assert.equal(assessDoubaoNativeWebFinalization({ ...f, allowedBackgroundPeers: [peer] }).integrity.valid, false);
});
