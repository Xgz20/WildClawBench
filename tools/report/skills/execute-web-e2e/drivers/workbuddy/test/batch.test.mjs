import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { snapshotTree } from "../lib.mjs";

import {
  DEFAULT_RUN_SLOTS,
  MAX_RUN_SLOTS,
  QUEUE_SCHEMA,
  QUEUE_STATE_REVISION,
  assertQueueState,
  buildExecutionReceipt,
  buildDriverArgs,
  canAutomaticallyResumeAttention,
  canAdvanceTask,
  createQueueState,
  migrateQueueState,
  parseBatchArgs,
  refreshQueueSlots,
  recordReceiptIntegrityFailure,
  recordManualIntervention,
  recordTaskOrchestrationFailure,
  recordWorkerInterruption,
  recordWorkerStart,
  resolveQueuePlan,
  selectPendingTaskIndexes,
} from "../batch.mjs";

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-batch-"));
  const tasks = [
    { task_id: "task-a", task_name: "A", difficulty: "L1", execution_dir: "execution/tasks/task-a" },
    { task_id: "task-b", task_name: "B", difficulty: "L1", execution_dir: "execution/tasks/task-b" },
  ];
  for (const task of tasks) {
    const taskRoot = join(root, task.execution_dir);
    await mkdir(join(taskRoot, "workspace"), { recursive: true });
    await writeFile(join(taskRoot, "PROMPT.md"), `build ${task.task_id}\n`);
  }
  await writeFile(join(root, "manifest.json"), JSON.stringify({
    schema_version: "wildclawbench.web-e2e-batch/v3",
    batch_id: "batch-001",
    harness: { id: "workbuddy", display_name: "WorkBuddy" },
    tasks,
  }));
  return root;
}

test("parseBatchArgs preserves explicit task order", () => {
  const args = parseBatchArgs([
    "--harness-root", "/tmp/batch",
    "--run-id", "l1-test",
    "--task-id", "task-b",
    "--task-id", "task-a",
    "--model", "均衡",
    "--permission-mode", "full-access",
  ]);
  assert.deepEqual(args.taskIds, ["task-b", "task-a"]);
  assert.equal(args.model, "均衡");
  assert.equal(args.permissionMode, "full-access");
  assert.equal(args.continueOnTerminalFailure, false);
  assert.equal(args.postCancelQuiescenceSeconds, 5);
  assert.equal(args.runSlots, DEFAULT_RUN_SLOTS);
  assert.equal(args.runSlotsExplicit, false);
});

test("batch accepts one to eight run slots and rejects invalid values", () => {
  const base = ["--harness-root", "/tmp/batch", "--run-id", "slots", "--task-id", "task-a"];
  assert.equal(parseBatchArgs([...base, "--run-slots", "1"]).runSlots, 1);
  assert.equal(parseBatchArgs([...base, "--run-slots", String(MAX_RUN_SLOTS)]).runSlots, MAX_RUN_SLOTS);
  assert.equal(parseBatchArgs([...base, "--run-slots", "1"]).runSlotsExplicit, true);
  for (const value of ["0", "9", "1.5", "nope"]) {
    assert.throws(() => parseBatchArgs([...base, "--run-slots", value]), /run-slots/);
  }
});

test("batch accepts a dynamic WorkBuddy model and forwards it to the driver", () => {
  const args = parseBatchArgs([
    "--harness-root", "/tmp/batch", "--run-id", "hy3", "--task-id", "task-a", "--model", "Hy3",
  ]);
  assert.equal(args.model, "Hy3");
  const driverArgs = buildDriverArgs(args, { taskRoot: "/tmp/task-a" }, 0);
  assert.equal(driverArgs.includes("--quiet"), true);
  const modelIndex = driverArgs.indexOf("--model");
  assert.deepEqual(driverArgs.slice(modelIndex, modelIndex + 2), ["--model", "Hy3"]);
});

test("batch keeps the current WorkBuddy model when model is omitted", () => {
  const args = parseBatchArgs([
    "--harness-root", "/tmp/batch", "--run-id", "current", "--task-id", "task-a",
  ]);
  assert.equal(args.model, "");
  const driverArgs = buildDriverArgs(args, { taskRoot: "/tmp/task-a" }, 0);
  assert.equal(driverArgs.includes("--model"), false);
});

test("resolveQueuePlan matches manifest tasks by exact id", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root,
    "--run-id", "l1-test",
    "--task-id", "task-b",
    "--task-id", "task-a",
  ]);
  const plan = await resolveQueuePlan(args);
  assert.deepEqual(plan.tasks.map((task) => task.taskId), ["task-b", "task-a"]);
  assert.ok(plan.queueStateFile.endsWith("execution/.execute-web-e2e/queues/l1-test/queue_state.json"));
  assert.ok(plan.lockFile.endsWith("execution/.execute-web-e2e/workbuddy-ui.lock"));
});

test("resolveQueuePlan rejects duplicate and unknown task ids", async () => {
  const root = await fixture();
  await assert.rejects(resolveQueuePlan(parseBatchArgs([
    "--harness-root", root, "--run-id", "x", "--task-id", "task-a", "--task-id", "task-a",
  ])), /不能重复/);
  await assert.rejects(resolveQueuePlan(parseBatchArgs([
    "--harness-root", root, "--run-id", "x", "--task-id", "missing",
  ])), /不存在任务/);
});

test("queue state identity and ordered tasks are immutable on resume", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root,
    "--run-id", "l1-test",
    "--task-id", "task-a",
    "--task-id", "task-b",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  assert.equal(state.schema_version, QUEUE_SCHEMA);
  assert.equal(state.revision, QUEUE_STATE_REVISION);
  assert.equal(state.ui_slots, 1);
  assert.equal(state.run_slots, 3);
  assert.equal(state.available_run_slots, 3);
  assert.deepEqual(state.tasks.map((task) => task.phase), ["PENDING", "PENDING"]);
  assert.equal(state.requested_ui_model, null);
  assert.equal(state.requested_permission_mode, "current");
  assert.equal(state.runtime.driver, null);
  assert.doesNotThrow(() => assertQueueState(state, plan, args));
  state.tasks.reverse();
  assert.throws(() => assertQueueState(state, plan, args), /task_ids/);
});

test("legacy queue migration preserves one run slot and freezes it on resume", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root, "--run-id", "legacy", "--task-id", "task-a", "--task-id", "task-b",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  delete state.revision;
  delete state.ui_slots;
  delete state.run_slots;
  delete state.active_task_ids;
  delete state.available_run_slots;
  for (const task of state.tasks) {
    delete task.dispatched_at;
    delete task.last_observed_at;
    delete task.observation_count;
  }
  assert.equal(migrateQueueState(state), true);
  assert.equal(state.revision, QUEUE_STATE_REVISION);
  assert.equal(state.ui_slots, 1);
  assert.equal(state.run_slots, 1);
  assert.equal(state.available_run_slots, 1);
  assert.doesNotThrow(() => assertQueueState(state, plan, args));
  const changed = parseBatchArgs([
    "--harness-root", root, "--run-id", "legacy", "--task-id", "task-a", "--task-id", "task-b",
    "--run-slots", "3",
  ]);
  assert.throws(() => assertQueueState(state, plan, changed), /run_slots/);
});

test("scheduler fills three background slots and backfills after out-of-order completion", () => {
  const state = {
    run_slots: 3,
    tasks: ["a", "b", "c", "d"].map((task_id) => ({ task_id, phase: "PENDING" })),
  };
  refreshQueueSlots(state);
  assert.deepEqual(selectPendingTaskIndexes(state), [0, 1, 2]);
  state.tasks[0].phase = "RUNNING";
  state.tasks[1].phase = "RUNNING";
  state.tasks[2].phase = "RUNNING";
  refreshQueueSlots(state);
  assert.deepEqual(state.active_task_ids, ["a", "b", "c"]);
  assert.equal(state.available_run_slots, 0);
  assert.deepEqual(selectPendingTaskIndexes(state), []);
  state.tasks[1].phase = "SUCCEEDED";
  refreshQueueSlots(state);
  assert.deepEqual(state.active_task_ids, ["a", "c"]);
  assert.deepEqual(selectPendingTaskIndexes(state), [3]);
  assert.deepEqual(selectPendingTaskIndexes(state, true), []);
});

test("queue permission mode is immutable after it is recorded", async () => {
  const root = await fixture();
  const currentArgs = parseBatchArgs([
    "--harness-root", root, "--run-id", "permission-test", "--task-id", "task-a",
  ]);
  const plan = await resolveQueuePlan(currentArgs);
  const state = createQueueState(plan, currentArgs);
  const fullAccessArgs = parseBatchArgs([
    "--harness-root", root, "--run-id", "permission-test", "--task-id", "task-a",
    "--permission-mode", "full-access",
  ]);
  assert.throws(() => assertQueueState(state, plan, fullAccessArgs), /requested_permission_mode/);
  delete state.requested_permission_mode;
  assert.doesNotThrow(() => assertQueueState(state, plan, fullAccessArgs));
});

test("batch pre-send retry requires resume", () => {
  const base = ["--harness-root", "/tmp/batch", "--run-id", "retry", "--task-id", "task-a"];
  assert.throws(() => parseBatchArgs([...base, "--retry-pre-send-failure"]), /必须与 --resume 一起使用/);
  assert.equal(parseBatchArgs([...base, "--resume", "--retry-pre-send-failure"]).retryPreSendFailure, true);
});

test("batch only forwards retry flags to tasks with an existing automation state", () => {
  const args = parseBatchArgs([
    "--harness-root", "/tmp/batch", "--run-id", "retry", "--task-id", "task-a",
    "--resume", "--retry-pre-send-failure",
  ]);
  const task = { taskRoot: "/tmp/batch/execution/tasks/task-a" };
  const freshArgs = buildDriverArgs(args, task, 1, null);
  assert.equal(freshArgs.includes("--resume"), false);
  assert.equal(freshArgs.includes("--retry-pre-send-failure"), false);
  assert.equal(freshArgs.includes("--detach-after-submit"), true);
  const recoveryArgs = buildDriverArgs(args, task, 0, { phase: "INFRA_FAILED" });
  assert.equal(recoveryArgs.includes("--resume"), true);
  assert.equal(recoveryArgs.includes("--retry-pre-send-failure"), true);
  assert.equal(recoveryArgs.includes("--detach-after-submit"), true);
  assert.equal(recoveryArgs.includes("--observe-once"), false);
  assert.deepEqual(
    recoveryArgs.slice(recoveryArgs.indexOf("--post-cancel-quiescence-seconds"), recoveryArgs.indexOf("--post-cancel-quiescence-seconds") + 2),
    ["--post-cancel-quiescence-seconds", "5"],
  );
});

test("active conversations are observed once without resending the prompt", () => {
  const args = parseBatchArgs([
    "--harness-root", "/tmp/batch", "--run-id", "observe", "--task-id", "task-a", "--resume",
  ]);
  const driverArgs = buildDriverArgs(args, { taskRoot: "/tmp/task-a" }, 0, { phase: "RUNNING" });
  assert.equal(driverArgs.includes("--resume"), true);
  assert.equal(driverArgs.includes("--observe-once"), true);
  assert.equal(driverArgs.includes("--detach-after-submit"), false);
  assert.equal(driverArgs.includes("--retry-pre-send-failure"), false);
});

test("only transient observation interruptions resume without manual approval", () => {
  assert.equal(canAutomaticallyResumeAttention({
    phase: "NEEDS_ATTENTION",
    history: [{ phase: "NEEDS_ATTENTION", reason: "driver-interrupted" }],
  }), true);
  assert.equal(canAutomaticallyResumeAttention({
    phase: "NEEDS_ATTENTION",
    history: [{ phase: "NEEDS_ATTENTION", reason: "client-disconnected" }],
  }), true);
  assert.equal(canAutomaticallyResumeAttention({
    phase: "NEEDS_ATTENTION",
    history: [{ phase: "NEEDS_ATTENTION", reason: "visible-approval" }],
  }), false);
});

test("batch only restarts WorkBuddy on resume when explicitly requested", () => {
  assert.throws(() => parseBatchArgs([
    "--harness-root", "/tmp/batch", "--run-id", "restart", "--task-id", "task-a",
    "--restart-app-on-resume",
  ]), /必须与 --resume 一起使用/);
  const args = parseBatchArgs([
    "--harness-root", "/tmp/batch", "--run-id", "restart", "--task-id", "task-a",
    "--resume", "--restart-app-on-resume",
  ]);
  const task = { taskRoot: "/tmp/batch/execution/tasks/task-a" };
  assert.equal(buildDriverArgs(args, task, 0, null).includes("--restart-app"), false);
  assert.equal(buildDriverArgs(args, task, 0, { phase: "RUNNING" }).includes("--restart-app"), true);
});

test("timeout can only advance after cancellation and workspace quiescence", () => {
  assert.equal(canAdvanceTask({ phase: "SUCCEEDED" }), true);
  assert.equal(canAdvanceTask({ phase: "INFRA_FAILED" }, false), false);
  assert.equal(canAdvanceTask({ phase: "INFRA_FAILED" }, true), true);
  assert.equal(canAdvanceTask({ phase: "TIMEOUT", timeout: null }, true), false);
  assert.equal(canAdvanceTask({
    phase: "TIMEOUT",
    timeout: { cancellation_confirmed: true, quiescence: { stable: false } },
  }, true), false);
  assert.equal(canAdvanceTask({
    phase: "TIMEOUT",
    timeout: { cancellation_confirmed: true, quiescence: { stable: true } },
  }, true), true);
});

test("worker interruption keeps the current task recoverable and records the exact driver", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root, "--run-id", "interrupt", "--task-id", "task-a",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  state.phase = "RUNNING";
  state.current_index = 0;
  state.tasks[0].phase = "RUNNING";
  state.runtime.worker = { pid: 123, hostname: "test-host", started_at: "2026-09-09T00:00:00.000Z" };
  state.runtime.driver = { pid: 456, task_id: "task-a" };
  recordWorkerInterruption(state, "SIGTERM", { pid: 456 });
  assert.equal(state.phase, "INTERRUPTED");
  assert.equal(state.tasks[0].phase, "RUNNING");
  assert.equal(state.runtime.interrupt_signal, "SIGTERM");
  assert.equal(state.history.at(-1).event, "WORKER_INTERRUPTED");
  assert.equal(state.history.at(-1).worker_pid, 123);
  assert.equal(state.history.at(-1).driver_pid, 456);

  state.runtime.worker = null;
  recordWorkerStart(state, { resume: true, pid: 789, workerHostname: "test-host" });
  assert.equal(state.history.at(-1).event, "WORKER_RESUMED");
  assert.equal(state.history.at(-1).worker_pid, 789);
  assert.equal(state.history.at(-1).previous_worker_pid, 123);
  assert.equal(state.history.at(-1).previous_interrupt_signal, "SIGTERM");
  assert.equal(state.history.at(-1).stale_ui_lock_recovered, false);
});

test("manual intervention is audited without bypassing terminal detection", async () => {
  assert.throws(() => parseBatchArgs([
    "--harness-root", "/tmp/batch", "--run-id", "manual", "--task-id", "task-a",
    "--mark-manual", "task-a",
  ]), /必须与 --resume 一起使用/);
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root, "--run-id", "manual", "--task-id", "task-a", "--resume",
    "--mark-manual", "task-a",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  state.phase = "NEEDS_ATTENTION";
  state.tasks[0].phase = "NEEDS_ATTENTION";
  const automation = { phase: "NEEDS_ATTENTION", history: [{ phase: "NEEDS_ATTENTION", reason: "visible-approval" }] };
  recordManualIntervention(state, "task-a", automation);
  assert.equal(state.tasks[0].phase, "NEEDS_ATTENTION");
  assert.equal(state.tasks[0].manual_interventions.length, 1);
  assert.equal(state.history.at(-1).event, "MANUAL_INTERVENTION_MARKED");
  assert.equal(state.history.at(-1).reason, "visible-approval");
});

test("execution receipt validates full manifest scope and task identities", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root, "--run-id", "receipt", "--task-id", "task-a", "--task-id", "task-b",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  state.phase = "COMPLETED";
  for (const task of plan.tasks) {
    await mkdir(join(task.taskRoot, "..", ".execute-web-e2e", task.taskId), { recursive: true });
    await writeFile(task.automationStateFile, JSON.stringify({
      identity: { batch_id: "batch-001", task_id: task.taskId, harness_id: "workbuddy" },
      attempt_id: `attempt-${task.taskId}`,
      phase: "SUCCEEDED",
      driver: { id: "workbuddy", version: "1.6.1" },
      client: { version: "5.5.3" },
      requested_ui_model: null,
      model_selection: { mode: "current", requested_model: null, actual_model: "xopglm52", method: "visible-current-value" },
      requested_permission_mode: "current",
      permission_selection: { requested_mode: "current", confirmed_mode: "default-sandbox", method: "visible-current-value" },
      prompt_sha256: "a".repeat(64),
      prompt_bytes: 10,
      timing: { started_at: "2026-09-06T00:00:00.000Z", sent_at: "2026-09-06T00:00:01.000Z", finished_at: "2026-09-06T00:00:02.000Z" },
      artifacts: { initial: { sha256: "b".repeat(64) }, final: await snapshotTree(join(task.taskRoot, "workspace")) },
      evidence: { terminal_source: "test", screenshots: [] },
      error: null,
    }));
    await writeFile(task.executionRecordFile, JSON.stringify({
      batch_id: "batch-001",
      task_id: task.taskId,
      model: { id: "xopglm52", display_name: "xopglm52" },
      harness: { id: "workbuddy", version: "5.5.3" },
      execution: { status: "completed" },
    }));
  }
  const receipt = await buildExecutionReceipt(plan, state);
  assert.equal(receipt.integrity.valid, true);
  assert.equal(receipt.integrity.models_match, true);
  assert.equal(receipt.integrity.workspaces_match_final, true);
  assert.equal(receipt.scope.matches_manifest, true);
  assert.deepEqual(receipt.tasks.map((task) => task.task_id), ["task-a", "task-b"]);
  assert.equal(receipt.tasks[0].model_selection.mode, "current");
  assert.equal(receipt.tasks[0].model_selection.requested_model, null);
  assert.equal(receipt.tasks[0].model_selection.actual_model, "xopglm52");
  assert.deepEqual(receipt.model, { id: "xopglm52", display_name: "xopglm52" });
  assert.equal(receipt.tasks[0].permission_mode, "default-sandbox");
  assert.ok(receipt.tasks[0].evidence.automation_state.startsWith("execution/tasks/.execute-web-e2e/"));
  assert.equal(receipt.tasks[0].workspace.receipt_check_matches_final, true);
});

test("execution receipt fails closed when a terminal workspace drifts", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root, "--run-id", "receipt-drift", "--task-id", "task-a", "--task-id", "task-b",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  state.phase = "COMPLETED";
  for (const task of plan.tasks) {
    await mkdir(join(task.taskRoot, "..", ".execute-web-e2e", task.taskId), { recursive: true });
    const final = await snapshotTree(join(task.taskRoot, "workspace"));
    await writeFile(task.automationStateFile, JSON.stringify({
      identity: { batch_id: "batch-001", task_id: task.taskId, harness_id: "workbuddy" },
      attempt_id: `attempt-${task.taskId}`,
      phase: "SUCCEEDED",
      driver: { id: "workbuddy", version: "1.6.1" },
      client: { version: "5.5.3" },
      requested_ui_model: null,
      model_selection: { mode: "current", requested_model: null, actual_model: "xopglm52" },
      prompt_sha256: "a".repeat(64),
      prompt_bytes: 10,
      artifacts: { initial: final, final },
      evidence: { terminal_source: "test", screenshots: [] },
    }));
    await writeFile(task.executionRecordFile, JSON.stringify({
      batch_id: "batch-001", task_id: task.taskId, model: { id: "xopglm52", display_name: "xopglm52" }, harness: { id: "workbuddy" }, execution: { status: "completed" },
    }));
  }
  await writeFile(join(plan.tasks[0].taskRoot, "workspace", "late.txt"), "drift");
  const receipt = await buildExecutionReceipt(plan, state);
  assert.equal(receipt.integrity.valid, false);
  assert.equal(receipt.integrity.workspaces_match_final, false);
  assert.equal(receipt.tasks[0].workspace.receipt_check_matches_final, false);
});

test("execution receipt records policy-declared runtime directories without invalidating source integrity", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root, "--run-id", "receipt-runtime-dir", "--task-id", "task-a", "--task-id", "task-b",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  state.phase = "COMPLETED";
  for (const task of plan.tasks) {
    await mkdir(join(task.taskRoot, "..", ".execute-web-e2e", task.taskId), { recursive: true });
    const final = await snapshotTree(join(task.taskRoot, "workspace"));
    await writeFile(task.automationStateFile, JSON.stringify({
      identity: { batch_id: "batch-001", task_id: task.taskId, harness_id: "workbuddy" },
      attempt_id: `attempt-${task.taskId}`,
      phase: "SUCCEEDED",
      requested_ui_model: null,
      model_selection: { mode: "current", requested_model: null, actual_model: "xopglm52" },
      artifacts: { initial: final, final },
    }));
    await writeFile(task.executionRecordFile, JSON.stringify({
      batch_id: "batch-001", task_id: task.taskId, model: { id: "xopglm52", display_name: "xopglm52" }, harness: { id: "workbuddy" }, execution: { status: "completed" },
    }));
  }
  await mkdir(join(plan.tasks[0].taskRoot, "workspace", ".vite"));
  await writeFile(join(plan.tasks[0].taskRoot, "workspace", ".vite", "cache.json"), "runtime");
  const receipt = await buildExecutionReceipt(plan, state);
  assert.equal(receipt.integrity.workspaces_match_final, true);
  assert.equal(receipt.integrity.no_forbidden_directories, true);
  assert.equal(receipt.integrity.valid, true);
  assert.equal(receipt.runtime_directory_policy.schema_version, "wildclawbench.web-e2e-runtime-directory-policy/v1");
  assert.deepEqual(receipt.tasks[0].workspace.ignored_runtime_directories, [".vite"]);
  assert.deepEqual(receipt.tasks[0].workspace.forbidden_directories, []);
});

test("execution receipt still rejects forbidden candidate directories", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root, "--run-id", "receipt-forbidden-dir", "--task-id", "task-a", "--task-id", "task-b",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  state.phase = "COMPLETED";
  for (const task of plan.tasks) {
    await mkdir(join(task.taskRoot, "..", ".execute-web-e2e", task.taskId), { recursive: true });
    const final = await snapshotTree(join(task.taskRoot, "workspace"));
    await writeFile(task.automationStateFile, JSON.stringify({
      identity: { batch_id: "batch-001", task_id: task.taskId, harness_id: "workbuddy" },
      attempt_id: `attempt-${task.taskId}`,
      phase: "SUCCEEDED",
      requested_ui_model: null,
      model_selection: { mode: "current", requested_model: null, actual_model: "xopglm52" },
      artifacts: { initial: final, final },
    }));
    await writeFile(task.executionRecordFile, JSON.stringify({
      batch_id: "batch-001", task_id: task.taskId, model: { id: "xopglm52", display_name: "xopglm52" }, harness: { id: "workbuddy" }, execution: { status: "completed" },
    }));
  }
  await mkdir(join(plan.tasks[0].taskRoot, "workspace", ".git"));
  const receipt = await buildExecutionReceipt(plan, state);
  assert.equal(receipt.integrity.workspaces_match_final, true);
  assert.equal(receipt.integrity.no_forbidden_directories, false);
  assert.equal(receipt.integrity.valid, false);
  assert.deepEqual(receipt.tasks[0].workspace.forbidden_directories, [".git"]);
});

test("an invalid completion receipt always downgrades the queue to failed", () => {
  const state = {
    phase: "COMPLETED",
    history: [],
    error: null,
  };
  const changed = recordReceiptIntegrityFailure(state, {
    integrity: { valid: false, workspaces_match_final: false },
  });
  assert.equal(changed, true);
  assert.equal(state.phase, "FAILED");
  assert.match(state.error, /完整性检查失败/);
  assert.equal(state.history.at(-1).event, "EXECUTION_RECEIPT_INTEGRITY_FAILED");
});

test("queue persists orchestration errors instead of leaving a task running", async () => {
  const root = await fixture();
  const args = parseBatchArgs([
    "--harness-root", root, "--run-id", "worker-error", "--task-id", "task-a",
  ]);
  const plan = await resolveQueuePlan(args);
  const state = createQueueState(plan, args);
  const queueTask = state.tasks[0];
  queueTask.phase = "RUNNING";
  recordTaskOrchestrationFailure(state, queueTask, plan.tasks[0], 0, new Error("missing state"), { code: 2 });
  assert.equal(state.phase, "FAILED");
  assert.equal(queueTask.phase, "WORKER_ERROR");
  assert.equal(queueTask.driver_exit_code, 2);
  assert.equal(state.history.at(-1).event, "TASK_ORCHESTRATION_FAILED");
});
