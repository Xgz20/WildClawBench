import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  QUEUE_SCHEMA,
  assertQueueIdentity,
  createQueueState,
  parseBatchArgs,
  resolveBatchPlan,
  runQueue,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/run_astronstudio_macos_batch.mjs";

const TASK_IDS = [
  "01_Productivity_Flow_task_001",
  "02_Code_Intelligence_task_001",
  "03_Social_Interaction_task_001",
  "04_Content_Creation_task_001",
  "06_Safety_Alignment_task_001",
];

async function fixture(taskIds = TASK_IDS, extraArgs = []) {
  const unitRoot = await mkdtemp(join(tmpdir(), "general-e2e-batch-test-"));
  const manifest = {
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1",
    schema_version: 1,
    manifest_kind: "execution",
    batch_id: "general-g4-03-fixture",
    unit_id: "astronstudio-macos-x86-64",
    dataset: { id: "general-custom60-v1", digest: "a".repeat(64) },
    task_ids: taskIds,
    tasks: taskIds.map((taskId) => ({ task_id: taskId })),
    unit: {
      harness: { id: "astronstudio", platform: "macos-x86-64", version: "3.3.1" },
      task_ids: taskIds,
    },
  };
  const runConfig = {
    config_digest: "b".repeat(64),
    control: { execution_concurrency: 3, maximum_execution_concurrency: 8 },
  };
  const runConfigPath = join(unitRoot, "run-config.json");
  await writeFile(join(unitRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  await writeFile(runConfigPath, `${JSON.stringify(runConfig, null, 2)}\n`, "utf8");
  const args = parseBatchArgs([
    "--unit-root", unitRoot,
    "--run-config", runConfigPath,
    "--queue-id", "g4-03-test",
    ...extraArgs,
  ]);
  return { unitRoot, runConfigPath, args, plan: await resolveBatchPlan(args) };
}

function automation(plan, taskId, attemptId, phase = "RUNNING") {
  const failed = phase === "FAILED";
  return {
    schema_version: "wildclawbench.general-e2e-astronstudio-execution-state/v1",
    identity: {
      batch_id: plan.manifest.batch_id,
      unit_id: plan.manifest.unit_id,
      task_id: taskId,
      attempt_id: attemptId,
    },
    phase,
    send: { dispatch_attempt_count: 1 },
    session: {
      thread_id: `thread-${taskId}`,
      turn_id: `turn-${taskId}`,
      session_id: `session-${taskId}`,
      cwd: join(plan.unitRoot, "execution", "tasks", taskId, "workspace"),
    },
    execution: {
      started_at: "2026-09-18T01:00:00.000Z",
      finished_at: new Set(["COMPLETED", "FAILED"]).has(phase)
        ? "2026-09-18T01:01:00.000Z"
        : null,
      business_status: failed ? "cancelled" : (phase === "COMPLETED" ? "completed" : null),
      error: failed ? { code: "ASTRONSTUDIO_TURN_INTERRUPTED", message: "client restarted" } : null,
    },
  };
}

async function writeAutomation(plan, taskId, value) {
  const root = join(plan.unitRoot, ".general-e2e", "execution", taskId);
  await mkdir(root, { recursive: true });
  await writeFile(join(root, "automation-state.json"), `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

test("batch CLI defaults to three slots, accepts eight, and rejects nine", () => {
  const base = [
    "--unit-root", "/tmp/unit",
    "--run-config", "/tmp/config.json",
    "--queue-id", "queue",
  ];
  assert.equal(parseBatchArgs(base).runSlots, 3);
  assert.equal(parseBatchArgs([...base, "--run-slots", "8"]).runSlots, 8);
  assert.throws(() => parseBatchArgs([...base, "--run-slots", "9"]), /1–8/u);
  assert.throws(
    () => parseBatchArgs([...base, "--task-id", "same", "--task-id", "same"]),
    /不能重复/u,
  );
});

test("five tasks fill three slots and dynamically refill in manifest order", async () => {
  const current = await fixture();
  const calls = [];
  const observations = new Map();
  try {
    const result = await runQueue(current.plan, current.args, {
      sleep: async () => {},
      runTask: async (taskId, operation, activeSessionIds) => {
        calls.push({ taskId, operation, activeSessionIds: [...activeSessionIds] });
        if (operation === "dispatch") {
          await writeAutomation(
            current.plan,
            taskId,
            automation(current.plan, taskId, `attempt-${taskId}`, "RUNNING"),
          );
        } else {
          const count = (observations.get(taskId) || 0) + 1;
          observations.set(taskId, count);
          const threshold = taskId === TASK_IDS[0] || taskId === TASK_IDS[4] ? 1 : 2;
          await writeAutomation(
            current.plan,
            taskId,
            automation(
              current.plan,
              taskId,
              `attempt-${taskId}`,
              count >= threshold ? "COMPLETED" : "RUNNING",
            ),
          );
        }
        return { code: 0, signal: null };
      },
    });

    assert.equal(result.schema_version, QUEUE_SCHEMA);
    assert.equal(result.phase, "COMPLETED");
    const dispatches = calls.filter((item) => item.operation === "dispatch");
    assert.deepEqual(dispatches.map((item) => item.taskId), TASK_IDS);
    assert.deepEqual(dispatches.map((item) => item.activeSessionIds), [
      [],
      [`session-${TASK_IDS[0]}`],
      [`session-${TASK_IDS[0]}`, `session-${TASK_IDS[1]}`],
      [`session-${TASK_IDS[1]}`, `session-${TASK_IDS[2]}`],
      [`session-${TASK_IDS[3]}`],
    ]);
    assert.deepEqual(result.tasks.map((item) => item.dispatch_attempt_count), [1, 1, 1, 1, 1]);
    assert.deepEqual(result.tasks.map((item) => item.attempts.length), [1, 1, 1, 1, 1]);
    assert.equal(result.history.filter((item) => item.event === "TASK_DISPATCH_REQUESTED").length, 5);
    const receipt = JSON.parse(await readFile(current.plan.queueReceiptFile, "utf8"));
    assert.equal(receipt.ui_slots, 1);
    assert.equal(receipt.run_slots, 3);
    assert.equal(receipt.integrity.valid, true);
    assert.equal(receipt.integrity.no_duplicate_dispatch, true);
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("worker-loss recovery observes original attempts without redispatch", async () => {
  const current = await fixture(TASK_IDS.slice(0, 2));
  const calls = [];
  try {
    const state = createQueueState(current.plan, "2026-09-18T01:00:00.000Z");
    state.phase = "RUNNING";
    state.current_task_id = TASK_IDS[0];
    state.active_task_ids = TASK_IDS.slice(0, 2);
    state.runtime.worker_pid = 424242;
    state.runtime.worker_started_at = "2026-09-18T01:00:01.000Z";
    for (const taskId of TASK_IDS.slice(0, 2)) {
      const task = state.tasks.find((item) => item.task_id === taskId);
      task.phase = "RUNNING";
      task.started_at = "2026-09-18T01:00:02.000Z";
      await writeAutomation(
        current.plan,
        taskId,
        automation(current.plan, taskId, `attempt-${taskId}`, "RUNNING"),
      );
    }
    await mkdir(current.plan.queueRoot, { recursive: true });
    await writeFile(current.plan.queueStateFile, `${JSON.stringify(state, null, 2)}\n`, "utf8");

    const resumed = await runQueue(current.plan, { ...current.args, resume: true }, {
      pid: 525252,
      isProcessAlive: () => false,
      sleep: async () => {},
      runTask: async (taskId, operation) => {
        calls.push({ taskId, operation });
        assert.equal(operation, "observe");
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, `attempt-${taskId}`, "COMPLETED"),
        );
        return { code: 0, signal: null };
      },
    });
    assert.equal(resumed.phase, "COMPLETED");
    assert.deepEqual(calls, TASK_IDS.slice(0, 2).map((taskId) => ({ taskId, operation: "observe" })));
    const loss = resumed.history.find((item) => item.event === "WORKER_PROCESS_LOST");
    assert.deepEqual(loss.active_task_ids, TASK_IDS.slice(0, 2));
    assert.equal(resumed.tasks.every((item) => item.attempts.length === 1), true);
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("needs-attention preserves identities of other active tasks", async () => {
  const current = await fixture(TASK_IDS.slice(0, 3));
  try {
    const result = await runQueue(current.plan, current.args, {
      sleep: async () => {},
      runTask: async (taskId, operation) => {
        const phase = operation === "observe" && taskId === TASK_IDS[0]
          ? "NEEDS_ATTENTION"
          : "RUNNING";
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, `attempt-${taskId}`, phase),
        );
        return { code: phase === "NEEDS_ATTENTION" ? 3 : 0, signal: null };
      },
    });
    assert.equal(result.phase, "NEEDS_ATTENTION");
    assert.deepEqual(result.active_task_ids, TASK_IDS.slice(1, 3));
    assert.equal(result.tasks[0].dispatch_attempt_count, 1);
    assert.equal(result.tasks[1].phase, "RUNNING");
    assert.equal(result.tasks[2].phase, "RUNNING");
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("terminal failure drains active tasks and blocks undispatched work by default", async () => {
  const current = await fixture(TASK_IDS.slice(0, 4));
  const dispatches = [];
  try {
    const result = await runQueue(current.plan, current.args, {
      sleep: async () => {},
      runTask: async (taskId, operation) => {
        if (operation === "dispatch") dispatches.push(taskId);
        const phase = operation === "dispatch"
          ? "RUNNING"
          : (taskId === TASK_IDS[0] ? "FAILED" : "COMPLETED");
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, `attempt-${taskId}`, phase),
        );
        return { code: phase === "FAILED" ? 2 : 0, signal: null };
      },
    });
    assert.equal(result.phase, "FAILED");
    assert.deepEqual(dispatches, TASK_IDS.slice(0, 3));
    assert.equal(result.current_task_id, TASK_IDS[0]);
    assert.deepEqual(result.active_task_ids, []);
    assert.equal(result.tasks[3].phase, "PENDING");
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("continue-on-terminal-failure completes remaining work and reports failures", async () => {
  const current = await fixture(TASK_IDS.slice(0, 4), ["--continue-on-terminal-failure"]);
  try {
    const result = await runQueue(current.plan, current.args, {
      sleep: async () => {},
      runTask: async (taskId, operation) => {
        const phase = operation === "dispatch"
          ? "RUNNING"
          : (taskId === TASK_IDS[0] ? "FAILED" : "COMPLETED");
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, `attempt-${taskId}`, phase),
        );
        return { code: phase === "FAILED" ? 2 : 0, signal: null };
      },
    });
    assert.equal(result.phase, "COMPLETED_WITH_FAILURES");
    assert.equal(result.tasks[3].phase, "COMPLETED");
    const receipt = JSON.parse(await readFile(current.plan.queueReceiptFile, "utf8"));
    assert.equal(receipt.integrity.valid, true);
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("resume refuses an implicit attempt replacement", async () => {
  const current = await fixture(TASK_IDS.slice(0, 1));
  try {
    const state = createQueueState(current.plan, "2026-09-18T01:00:00.000Z");
    state.phase = "RUNNING";
    state.active_task_ids = [TASK_IDS[0]];
    state.current_task_id = TASK_IDS[0];
    state.runtime.worker_pid = 424242;
    state.tasks[0].phase = "RUNNING";
    state.tasks[0].selected_attempt_id = "attempt-original";
    state.tasks[0].attempts = [{
      attempt_id: "attempt-original",
      state_path: state.tasks[0].execution_state_path,
      registered_at: "2026-09-18T01:00:00.000Z",
      selected: true,
    }];
    await writeAutomation(
      current.plan,
      TASK_IDS[0],
      automation(current.plan, TASK_IDS[0], "attempt-replacement", "COMPLETED"),
    );
    await mkdir(current.plan.queueRoot, { recursive: true });
    await writeFile(current.plan.queueStateFile, `${JSON.stringify(state, null, 2)}\n`, "utf8");
    await assert.rejects(
      runQueue(current.plan, { ...current.args, resume: true }, {
        isProcessAlive: () => false,
        runTask: async () => ({ code: 0, signal: null }),
      }),
      /ATTEMPT_SWITCH_REQUIRES_NEW_QUEUE/u,
    );
    const queue = JSON.parse(await readFile(current.plan.queueStateFile, "utf8"));
    assert.equal(queue.phase, "FAILED");
    assert.equal(queue.tasks[0].selected_attempt_id, "attempt-original");
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("queue digest rejects changed concurrency and task scope", async () => {
  const current = await fixture(TASK_IDS.slice(0, 2));
  try {
    const state = createQueueState(current.plan, "2026-09-18T01:00:00.000Z");
    const changedConcurrencyPlan = await resolveBatchPlan({ ...current.args, runSlots: 2 });
    assert.throws(() => assertQueueIdentity(state, changedConcurrencyPlan), /queue_digest/u);

    const changedScopePlan = await resolveBatchPlan({ ...current.args, taskIds: [TASK_IDS[0]] });
    assert.throws(() => assertQueueIdentity(state, changedScopePlan), /queue_digest/u);
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});
