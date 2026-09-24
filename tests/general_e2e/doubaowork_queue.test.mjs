import assert from "node:assert/strict";
import { test } from "node:test";
import { decideQueueTaskAction, runSerialQueue, selectQueueAction, summarizeQueueConcurrency } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/doubaowork/batch.mjs";

test("Queue never repeats a dispatch whose journal is missing or uncertain", () => {
  assert.equal(decideQueueTaskAction({ phase: "PENDING" }, null), "dispatch");
  assert.equal(decideQueueTaskAction({ phase: "DISPATCHING" }, null), "pause");
  assert.equal(decideQueueTaskAction({ phase: "DISPATCHING" }, { send: { dispatch_attempt_count: 0 } }), "pause");
  assert.equal(decideQueueTaskAction({ phase: "PENDING" }, { send: { dispatch_attempt_count: 1 } }), "reject-existing-attempt");
});

test("Queue follows original attempt and requires native completion", () => {
  const row = { phase: "RUNNING", attempt_id: "a" }, journal = { attempt_id: "a", send: { dispatch_attempt_count: 1 } };
  assert.equal(decideQueueTaskAction(row, journal), "observe");
  assert.equal(decideQueueTaskAction(row, { ...journal, attempt_id: "b" }), "reject-attempt-drift");
  assert.equal(decideQueueTaskAction(row, { ...journal, native_observation: { terminal: "completed" } }), "complete");
});

test("Prepared recovery requires the original confirmed unsent attempt", () => {
  const journal = { attempt_id: "a", prepared_project: true, phase: "WORKSPACE_CONFIRMED",
    send: { dispatch_attempt_count: 0, intent_persisted_at: null } };
  assert.equal(decideQueueTaskAction({ phase: "PREPARING" }, journal), "prepared");
  assert.equal(decideQueueTaskAction({ phase: "PREPARED", attempt_id: "a" }, journal), "dispatch-prepared");
  for (const changed of [null, { ...journal, attempt_id: "b" }, { ...journal, phase: "NEEDS_ATTENTION" },
    { ...journal, send: { dispatch_attempt_count: 1 } },
    { ...journal, send: { dispatch_attempt_count: 0, intent_persisted_at: "persisted" } }]) {
    assert.equal(decideQueueTaskAction({ phase: "PREPARED", attempt_id: "a" }, changed), "pause");
  }
  // A crash after dispatch intent never makes an unsent journal eligible for another send.
  assert.equal(decideQueueTaskAction({ phase: "DISPATCHING", attempt_id: "a" }, journal), "pause");
});

test("Prepared rows fill available slots; uncertain dispatch blocks replenishment", () => {
  const rows = [{ task_id: "1", phase: "RUNNING" }, { task_id: "2", phase: "PREPARED" }];
  assert.deepEqual(selectQueueAction(rows, 3), { task_id: "2", action: "dispatch-prepared" });
  assert.deepEqual(selectQueueAction(rows, 1), { task_id: "1", action: "observe" });
  rows[0].phase = "DISPATCHING";
  assert.deepEqual(selectQueueAction(rows, 3), { task_id: "1", action: "observe" });
});

test("Unadmitted concurrency is rejected before reading a unit or touching the client", async () => {
  await assert.rejects(runSerialQueue({ queueId: "fixture", runSlots: 4 }), /CONCURRENCY_NOT_ADMITTED/);
  await assert.rejects(runSerialQueue({ queueId: "fixture", runSlots: 1, expectedPermission: "current" }), /EXPLICIT_PERMISSION_REQUIRED/);
});

test("Queue fills in manifest order, replenishes released slots, and observes uncertain dispatches first", () => {
  const rows = [1, 2, 3, 4, 5].map(i => ({ task_id: String(i), phase: "PENDING" }));
  assert.deepEqual(selectQueueAction(rows, 3), { task_id: "1", action: "dispatch" });
  rows[0].phase = "RUNNING"; rows[1].phase = "RUNNING"; rows[2].phase = "RUNNING";
  assert.equal(selectQueueAction(rows, 3).action, "observe");
  rows[0].phase = "NATIVE_COMPLETED";
  assert.deepEqual(selectQueueAction(rows, 3), { task_id: "4", action: "dispatch" });
  rows[3].phase = "DISPATCHING";
  assert.deepEqual(selectQueueAction(rows, 3), { task_id: "4", action: "observe" });
});

test("Native overlap uses native intervals, not configured slots or polling occupancy", () => {
  const rows = [0, 1, 2].map((n) => ({ task_id: String(n), prompt_sent_at: new Date(n * 1000).toISOString(), slot_released_at: new Date(10000).toISOString(),
    native_started_at: new Date(n * 1000).toISOString(), native_finished_at: new Date((n + 1) * 1000).toISOString() }));
  const summary = summarizeQueueConcurrency(rows, 3);
  assert.equal(summary.scheduling_occupancy.value, 3);
  assert.equal(summary.native_agent_overlap.value, 1);
  rows[0].native_started_at = null;
  assert.equal(summarizeQueueConcurrency(rows, 3).native_agent_overlap.value, null);
});
