import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  QUEUE_SCHEMA,
  assertQueueIdentity,
  parseBatchArgs,
  resolveBatchPlan,
  runQueue,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/run_astronstudio_macos_batch.mjs";

const TASK_IDS = [
  "01_Research_task_001",
  "02_Code_Intelligence_task_001",
  "04_Content_Creation_task_001",
];

async function fixture(taskIds = TASK_IDS) {
  const unitRoot = await mkdtemp(join(tmpdir(), "general-e2e-batch-test-"));
  const manifest = {
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1",
    schema_version: 1,
    manifest_kind: "execution",
    batch_id: "general-g2-06-fixture",
    unit_id: "astronstudio-macos-x86-64",
    dataset: { id: "general-custom60-v1", digest: "a".repeat(64) },
    task_ids: taskIds,
    tasks: taskIds.map((taskId) => ({ task_id: taskId })),
    unit: {
      harness: { id: "astronstudio", platform: "macos-x86-64", version: "3.3.1" },
      task_ids: taskIds,
    },
  };
  const runConfig = { config_digest: "b".repeat(64) };
  const runConfigPath = join(unitRoot, "run-config.json");
  await writeFile(join(unitRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  await writeFile(runConfigPath, `${JSON.stringify(runConfig, null, 2)}\n`, "utf8");
  const args = parseBatchArgs([
    "--unit-root", unitRoot,
    "--run-config", runConfigPath,
    "--queue-id", "g2-06-test",
  ]);
  return { unitRoot, runConfigPath, args, plan: await resolveBatchPlan(args) };
}

function automation(plan, taskId, attemptId, phase = "COMPLETED") {
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

test("batch CLI freezes serial execution and rejects unverified concurrency", () => {
  assert.throws(
    () => parseBatchArgs([
      "--unit-root", "/tmp/unit",
      "--run-config", "/tmp/config.json",
      "--queue-id", "queue",
      "--run-slots", "3",
    ]),
    /MAC-08/u,
  );
  assert.throws(
    () => parseBatchArgs([
      "--unit-root", "/tmp/unit",
      "--run-config", "/tmp/config.json",
      "--queue-id", "queue",
      "--task-id", "same",
      "--task-id", "same",
    ]),
    /不能重复/u,
  );
});

test("three tasks run in manifest order with one dispatch per explicit attempt", async () => {
  const current = await fixture();
  const calls = [];
  try {
    const result = await runQueue(current.plan, current.args, {
      runTask: async (taskId, resume) => {
        calls.push({ taskId, resume });
        await writeAutomation(current.plan, taskId, automation(
          current.plan,
          taskId,
          `attempt-${calls.length}`,
        ));
        return { code: 0, signal: null };
      },
    });
    assert.equal(result.schema_version, QUEUE_SCHEMA);
    assert.equal(result.phase, "COMPLETED");
    assert.deepEqual(calls, TASK_IDS.map((taskId) => ({ taskId, resume: false })));
    assert.deepEqual(result.tasks.map((item) => item.dispatch_attempt_count), [1, 1, 1]);
    assert.deepEqual(result.tasks.map((item) => item.attempts.length), [1, 1, 1]);
    const receipt = JSON.parse(await readFile(current.plan.queueReceiptFile, "utf8"));
    assert.equal(receipt.integrity.valid, true);
    assert.equal(receipt.integrity.no_duplicate_dispatch, true);
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("resume reuses the same nonterminal attempt before dispatching the next task", async () => {
  const current = await fixture(TASK_IDS.slice(0, 2));
  const calls = [];
  try {
    const first = await runQueue(current.plan, current.args, {
      runTask: async (taskId, resume) => {
        calls.push({ taskId, resume });
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, "attempt-stable", "RUNNING"),
        );
        return { code: 4, signal: null };
      },
    });
    assert.equal(first.phase, "NEEDS_ATTENTION");
    assert.equal(first.current_task_id, TASK_IDS[0]);
    assert.equal(calls.length, 1);

    const resumedArgs = { ...current.args, resume: true };
    const resumed = await runQueue(current.plan, resumedArgs, {
      runTask: async (taskId, resume) => {
        calls.push({ taskId, resume });
        const attemptId = taskId === TASK_IDS[0] ? "attempt-stable" : "attempt-next";
        await writeAutomation(current.plan, taskId, automation(current.plan, taskId, attemptId));
        return { code: 0, signal: null };
      },
    });
    assert.equal(resumed.phase, "COMPLETED");
    assert.deepEqual(calls, [
      { taskId: TASK_IDS[0], resume: false },
      { taskId: TASK_IDS[0], resume: true },
      { taskId: TASK_IDS[1], resume: false },
    ]);
    assert.equal(resumed.tasks[0].selected_attempt_id, "attempt-stable");
    assert.equal(resumed.tasks[0].attempts.length, 1);
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("a native client interruption is a trusted failure and blocks the next task", async () => {
  const current = await fixture(TASK_IDS.slice(0, 2));
  const calls = [];
  try {
    const result = await runQueue(current.plan, current.args, {
      runTask: async (taskId, resume) => {
        calls.push({ taskId, resume });
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, "attempt-interrupted", "FAILED"),
        );
        return { code: 2, signal: null };
      },
    });
    assert.equal(result.phase, "FAILED");
    assert.deepEqual(calls, [{ taskId: TASK_IDS[0], resume: false }]);
    assert.equal(result.tasks[0].error.code, "ASTRONSTUDIO_TURN_INTERRUPTED");
    assert.equal(result.tasks[1].phase, "PENDING");
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("resume refuses an implicit attempt replacement", async () => {
  const current = await fixture(TASK_IDS.slice(0, 1));
  try {
    await runQueue(current.plan, current.args, {
      runTask: async (taskId) => {
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, "attempt-original", "RUNNING"),
        );
        return { code: 4, signal: null };
      },
    });
    await writeAutomation(
      current.plan,
      TASK_IDS[0],
      automation(current.plan, TASK_IDS[0], "attempt-replacement", "COMPLETED"),
    );
    await assert.rejects(
      runQueue(current.plan, { ...current.args, resume: true }, { runTask: async () => ({ code: 0 }) }),
      /ATTEMPT_SWITCH_REQUIRES_NEW_QUEUE/u,
    );
    const queue = JSON.parse(await readFile(current.plan.queueStateFile, "utf8"));
    assert.equal(queue.phase, "FAILED");
    assert.equal(queue.tasks[0].selected_attempt_id, "attempt-original");
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});

test("queue digest rejects changed task scope and stale worker locks recover only on resume", async () => {
  const current = await fixture(TASK_IDS.slice(0, 1));
  try {
    await runQueue(current.plan, current.args, {
      runTask: async (taskId) => {
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, "attempt-stale", "RUNNING"),
        );
        return { code: 4, signal: null };
      },
    });
    await mkdir(current.plan.queueRoot, { recursive: true });
    await writeFile(
      current.plan.workerLockFile,
      `${JSON.stringify({ pid: 424242, token: "stale" })}\n`,
      "utf8",
    );
    const resumed = await runQueue(current.plan, { ...current.args, resume: true }, {
      pid: 525252,
      isProcessAlive: () => false,
      runTask: async (taskId, resume) => {
        assert.equal(resume, true);
        await writeAutomation(
          current.plan,
          taskId,
          automation(current.plan, taskId, "attempt-stale", "COMPLETED"),
        );
        return { code: 0, signal: null };
      },
    });
    assert.equal(resumed.runtime.recovered_stale_lock, true);
    assert.equal(resumed.history.some((item) => item.event === "WORKER_PROCESS_LOST"), true);

    const changedArgs = {
      ...current.args,
      taskIds: [TASK_IDS[0]],
      continueOnTerminalFailure: true,
    };
    const changedPlan = await resolveBatchPlan(changedArgs);
    assert.throws(() => assertQueueIdentity(resumed, changedPlan), /queue_digest/u);
  } finally {
    await rm(current.unitRoot, { recursive: true, force: true });
  }
});
