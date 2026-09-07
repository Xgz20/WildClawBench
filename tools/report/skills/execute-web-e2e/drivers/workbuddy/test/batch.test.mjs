import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { snapshotTree } from "../lib.mjs";

import {
  QUEUE_SCHEMA,
  assertQueueState,
  buildExecutionReceipt,
  buildDriverArgs,
  canAdvanceTask,
  createQueueState,
  parseBatchArgs,
  recordReceiptIntegrityFailure,
  recordManualIntervention,
  recordTaskOrchestrationFailure,
  recordWorkerInterruption,
  resolveQueuePlan,
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
});

test("batch accepts a dynamic WorkBuddy model and forwards it to the driver", () => {
  const args = parseBatchArgs([
    "--harness-root", "/tmp/batch", "--run-id", "hy3", "--task-id", "task-a", "--model", "Hy3",
  ]);
  assert.equal(args.model, "Hy3");
  const driverArgs = buildDriverArgs(args, { taskRoot: "/tmp/task-a" }, 0);
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
  assert.deepEqual(state.tasks.map((task) => task.phase), ["PENDING", "PENDING"]);
  assert.equal(state.requested_ui_model, null);
  assert.equal(state.requested_permission_mode, "current");
  assert.equal(state.runtime.driver, null);
  assert.doesNotThrow(() => assertQueueState(state, plan, args));
  state.tasks.reverse();
  assert.throws(() => assertQueueState(state, plan, args), /task_ids/);
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
  const recoveryArgs = buildDriverArgs(args, task, 0, { phase: "INFRA_FAILED" });
  assert.equal(recoveryArgs.includes("--resume"), true);
  assert.equal(recoveryArgs.includes("--retry-pre-send-failure"), true);
  assert.deepEqual(
    recoveryArgs.slice(recoveryArgs.indexOf("--post-cancel-quiescence-seconds"), recoveryArgs.indexOf("--post-cancel-quiescence-seconds") + 2),
    ["--post-cancel-quiescence-seconds", "5"],
  );
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
  state.runtime.driver = { pid: 456, task_id: "task-a" };
  recordWorkerInterruption(state, "SIGTERM", { pid: 456 });
  assert.equal(state.phase, "INTERRUPTED");
  assert.equal(state.tasks[0].phase, "RUNNING");
  assert.equal(state.runtime.interrupt_signal, "SIGTERM");
  assert.equal(state.history.at(-1).event, "WORKER_INTERRUPTED");
  assert.equal(state.history.at(-1).driver_pid, 456);
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

test("execution receipt rejects runtime-only directories excluded from the content hash", async () => {
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
  assert.equal(receipt.integrity.no_excluded_runtime_directories, false);
  assert.equal(receipt.integrity.valid, false);
  assert.deepEqual(receipt.tasks[0].workspace.excluded_runtime_directories, [".vite"]);
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
