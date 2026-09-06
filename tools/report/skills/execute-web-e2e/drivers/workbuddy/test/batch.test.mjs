import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  QUEUE_SCHEMA,
  assertQueueState,
  buildDriverArgs,
  createQueueState,
  parseBatchArgs,
  recordTaskOrchestrationFailure,
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
  assert.equal(state.requested_permission_mode, "current");
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
