import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const DRIVER_DIR = realpathSync(join(dirname(fileURLToPath(import.meta.url)), ".."));
process.env.WCB_WEB_E2E_BATCH_PROFILE = "qwenwork";
const {
  buildDriverArgs,
  canAutomaticallyResumeAttention,
  parseBatchArgs,
  recordWorkerInterruption,
  recordWorkerStart,
} = await import(`../../workbuddy/batch.mjs?qwenwork-recovery=${Date.now()}`);

test("QwenWork batch worker defaults to three background run slots and caps at eight", () => {
  const help = spawnSync(process.execPath, [join(DRIVER_DIR, "batch.mjs"), "--help"], { encoding: "utf8" });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /QwenWork Web E2E 后台并发队列 Worker/);
  assert.match(help.stdout, /--run-slots <1\.\.8>/);
  assert.match(help.stdout, /Agent 并发数，默认：3；UI 始终单路/);

  for (const [runSlots, expectedError] of [
    ["0", /--run-slots 必须是正数/],
    ["9", /--run-slots 必须是 1 到 8 的整数/],
    ["1.5", /--run-slots 必须是 1 到 8 的整数/],
  ]) {
    const invalid = spawnSync(process.execPath, [
      join(DRIVER_DIR, "batch.mjs"),
      "--harness-root", "/tmp/not-used",
      "--run-id", "test",
      "--task-id", "task-001",
      "--run-slots", runSlots,
    ], { encoding: "utf8" });
    assert.equal(invalid.status, 1);
    assert.match(invalid.stderr, expectedError);
  }
});

test("QwenWork resumes the same conversation without resending after a worker handoff", () => {
  const args = parseBatchArgs([
    "--harness-root", "/tmp/batch",
    "--run-id", "recovery",
    "--task-id", "task-a",
    "--run-slots", "1",
    "--resume",
  ]);
  const driverArgs = buildDriverArgs(
    args,
    { taskRoot: "/tmp/batch/execution/tasks/task-a" },
    0,
    { phase: "RUNNING", attempt_id: "attempt-1" },
  );
  assert.equal(driverArgs.includes("--resume"), true);
  assert.equal(driverArgs.includes("--observe-once"), true);
  assert.equal(driverArgs.includes("--detach-after-submit"), false);
  assert.equal(canAutomaticallyResumeAttention({
    phase: "NEEDS_ATTENTION",
    history: [{ phase: "NEEDS_ATTENTION", reason: "driver-interrupted" }],
  }), true);

  const state = {
    phase: "RUNNING",
    current_index: 0,
    runtime: {
      worker: { pid: 101, hostname: "old-host", started_at: "2026-09-09T00:00:00.000Z" },
      driver: { pid: 202, task_id: "task-a" },
    },
    tasks: [{ task_id: "task-a", phase: "RUNNING", attempt_id: "attempt-1" }],
    history: [],
  };
  recordWorkerInterruption(state, "SIGTERM", { pid: 202 });
  state.runtime.worker = null;
  recordWorkerStart(state, { resume: true, pid: 303, workerHostname: "new-host" });
  assert.equal(state.tasks[0].attempt_id, "attempt-1");
  assert.deepEqual(state.history.map((entry) => entry.event), ["WORKER_INTERRUPTED", "WORKER_RESUMED"]);
  assert.equal(state.history[0].worker_pid, 101);
  assert.equal(state.history[1].worker_pid, 303);
  assert.equal(state.history[1].previous_worker_pid, 101);
  assert.equal(state.history[1].previous_interrupt_signal, "SIGTERM");
});
