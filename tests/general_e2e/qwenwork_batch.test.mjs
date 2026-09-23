import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  acquireQwenQueueOwner,
  activeSessionArgs,
  parseBatchArgs,
  runQwenWorkBatch,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/batch.mjs";

// Queue contract used by these tests: runQwenWorkBatch(argv, { execute, sleep })
// invokes the single-task Driver with --task-id/--attempt-id and persists each
// attempt under .general-e2e/execution/<task-id>/qwenwork/.

const QUEUE_TASKS = ["one", "two", "three", "four", "five"];
const PROBE = "probe.json";

test("QwenWork queue recovers only an explicitly verified stale owner and archives it", async () => {
  const root = await mkdtemp(join(tmpdir(), "qwenwork-owner-"));
  const path = join(root, "owner-lock.json");
  const previous = { schema_version: "wildclawbench.general-e2e-qwenwork-queue-owner/v1",
    owner_id: "old-owner", queue_id: "queue-fixture", frozen_sha256: "a".repeat(64),
    pid: 101, host: "fixture-host", process_start_identity: "old-start", acquired_at: "2026-09-23T00:00:00Z" };
  try {
    await writeFile(path, `${JSON.stringify(previous)}\n`);
    const current = await acquireQwenQueueOwner(path, {
      queueId: "queue-fixture", frozenSha256: "a".repeat(64), recoverStale: true,
    }, { hostname: "fixture-host", pid: 202, ownerId: "new-owner",
      processStartIdentity: async (pid) => pid === 202 ? "new-start" : "old-start",
      processAlive: async () => false });
    assert.equal(current.recovered.reason, "pid-not-running");
    assert.deepEqual(JSON.parse(await readFile(current.recovered.archive_path, "utf8")), previous);
    assert.equal(JSON.parse(await readFile(path, "utf8")).owner_id, "new-owner");
    await current.release();
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("QwenWork queue owner recovery refuses an active owner and any attempt lock", async () => {
  const root = await mkdtemp(join(tmpdir(), "qwenwork-owner-"));
  const path = join(root, "owner-lock.json");
  const attemptLock = join(root, "attempt.lock");
  const previous = { schema_version: "wildclawbench.general-e2e-qwenwork-queue-owner/v1",
    owner_id: "old-owner", queue_id: "queue-fixture", frozen_sha256: "a".repeat(64),
    pid: 101, host: "fixture-host", process_start_identity: "old-start", acquired_at: "2026-09-23T00:00:00Z" };
  const options = { queueId: "queue-fixture", frozenSha256: "a".repeat(64),
    recoverStale: true, attemptLocks: [attemptLock] };
  const overrides = { hostname: "fixture-host", pid: 202, ownerId: "new-owner",
    processStartIdentity: async (pid) => pid === 202 ? "new-start" : "old-start" };
  try {
    await writeFile(path, `${JSON.stringify(previous)}\n`);
    await assert.rejects(acquireQwenQueueOwner(path, options,
      { ...overrides, processAlive: async () => true }), /STILL_ACTIVE_OR_UNVERIFIABLE/u);
    await writeFile(attemptLock, "fixture");
    await assert.rejects(acquireQwenQueueOwner(path, options,
      { ...overrides, processAlive: async () => false }), /ATTEMPT_LOCK_BLOCKS_QUEUE_RECOVERY/u);
    assert.deepEqual(JSON.parse(await readFile(path, "utf8")), previous);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("queue observation allow-list retains only sent queue-owned attention bindings", () => {
  const args = activeSessionArgs({ tasks: [
    { phase: "RUNNING", dispatch_attempt_count: 1, session_id: "session-a", conversation_id: "conversation-a" },
    { phase: "NEEDS_ATTENTION", dispatch_attempt_count: 1, session_id: "session-b", conversation_id: "conversation-b" },
    { phase: "NEEDS_ATTENTION", dispatch_attempt_count: 0, session_id: "stale-unsent" },
    { phase: "PENDING", dispatch_attempt_count: 0, session_id: null },
  ] });
  assert.deepEqual(args, [
    "--allowed-active-session-id", "session-a", "--allowed-active-conversation-id", "conversation-a",
    "--allowed-active-session-id", "session-b", "--allowed-active-conversation-id", "conversation-b",
  ]);
});

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function taskRoot(root, taskId) {
  return join(root, "execution", "tasks", taskId);
}

function controlRoot(root, taskId) {
  return join(root, ".general-e2e", "execution", taskId, "qwenwork");
}

async function writeJson(path, value) {
  await mkdir(join(path, ".."), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function fixture(taskIds = QUEUE_TASKS) {
  const root = await mkdtemp(join(tmpdir(), "qwenwork-queue-"));
  const prompt = "fixture prompt";
  const tasks = [];
  for (const taskId of taskIds) {
    const relative = `execution/tasks/${taskId}`;
    await mkdir(join(root, relative, "workspace"), { recursive: true });
    await writeFile(join(root, relative, "PROMPT.md"), prompt, "utf8");
    tasks.push({
      task_id: taskId,
      prompt: {
        path: `${relative}/PROMPT.md`,
        source_sha256: sha256(prompt),
        sent_sha256: sha256(prompt),
      },
      workspace: { path: `${relative}/workspace` },
    });
  }
  await writeJson(join(root, "manifest.json"), {
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1",
    schema_version: 1,
    manifest_kind: "execution",
    batch_id: "qwen-batch-fixture",
    unit_id: "qwenwork-macos-x86-64",
    dataset: { id: "general-custom60-v1", digest: "d".repeat(64) },
    unit: {
      harness: { id: "qwenwork", platform: "macos-x86-64", version: "1.0.6" },
      task_ids: taskIds,
      model: { requested_id: "keep-current" },
    },
    task_ids: taskIds,
    tasks,
  });
  const probePath = join(root, PROBE);
  const probe = {
    schema_version: "wildclawbench.general-e2e-qwenwork-readonly-probe/v1",
    probed_at: "2026-09-22T06:00:00.000Z",
    driver: { harness: "qwenwork", platform: "macos" },
    app: { bundle_id: "cn.qwenwork.desktop.mac", identity_verified: true },
    ready_for_read_only_mapping: true,
    native_state: { database: { quick_check: "ok", active_or_pending_count: 0 } },
    operations_performed: ["read-only-native-state"],
  };
  await writeJson(probePath, probe);
  const probeSha = sha256(`${JSON.stringify(probe, null, 2)}\n`);
  const args = [
    "--unit-root", root,
    "--queue-id", "qwen-fixture",
    "--endpoint", "http://127.0.0.1:9250",
    "--session-db", join(root, "agents.db"),
    "--trace-root", join(root, ".qwenworkcn"),
    "--probe", probePath,
    "--probe-sha256", probeSha,
  ];
  return { root, args, probePath, taskIds };
}

function journal(root, taskId, attemptId, phase, {
  dispatchAttemptCount = 1,
  sendStatus = "sent",
  finished = phase === "COMPLETED" || phase === "FAILED",
  nativeStartedAt = null,
  nativeFinishedAt = null,
} = {}) {
  const cwd = join(taskRoot(root, taskId), "workspace");
  const startedAt = "2026-09-22T06:00:01.000Z";
  const finishedAt = finished ? "2026-09-22T06:00:11.000Z" : null;
  const sessionId = `session-${taskId}`;
  return {
    schema_version: "wildclawbench.general-e2e-qwenwork-attempt-journal/v1",
    identity: {
      batch_id: "qwen-batch-fixture",
      unit_id: "qwenwork-macos-x86-64",
      task_id: taskId,
      attempt_id: attemptId,
    },
    phase,
    attention: phase === "NEEDS_ATTENTION"
      ? { code: "QWENWORK_SESSION_PROMPT_UNVERIFIED", message: "fixture attention" }
      : null,
    prompt: {
      path: join(taskRoot(root, taskId), "PROMPT.md"),
      sha256: sha256("fixture prompt"),
      send_status: sendStatus,
      sent_at: startedAt,
    },
    send: { dispatch_attempt_count: dispatchAttemptCount },
    workspace: {
      requested_path: cwd,
      confirmed_path: cwd,
      local_project_id: `project-${taskId}`,
    },
    session: {
      session_id: sessionId,
      conversation_id: `conversation-${taskId}`,
      sub_chat_id: `sub-chat-${taskId}`,
      local_project_id: `project-${taskId}`,
      cwd,
      verified: true,
    },
    execution_state: {
      identity: { task_id: taskId, attempt_id: attemptId },
      phase,
      execution: {
        started_at: startedAt,
        finished_at: finishedAt,
        error: null,
      },
      session: { session_id: sessionId, cwd },
    },
    execution: {
      started_at: startedAt,
      finished_at: finishedAt,
      error: null,
    },
    native: {
      started_at: nativeStartedAt,
      finished_at: nativeFinishedAt,
    },
  };
}

async function writeJournal(root, taskId, attemptId, phase, options = {}) {
  const path = join(controlRoot(root, taskId), "dispatch-journal.json");
  await writeJson(path, journal(root, taskId, attemptId, phase, options));
  return path;
}

async function identityFrom(argv) {
  const configPath = argv[argv.indexOf("--config") + 1];
  const config = JSON.parse(await readFile(configPath, "utf8"));
  return config.identity;
}

test("QwenWork queue defaults to three slots and dynamically refills five tasks", async () => {
  const f = await fixture();
  const calls = [];
  const observations = new Map();
  let active = 0;
  let maximum = 0;
  try {
    const execute = async (argv) => {
      const identity = await identityFrom(argv);
      const taskId = identity.task_id;
      const attemptId = identity.attempt_id;
      const resume = argv.includes("--resume");
      calls.push({ taskId, attemptId, resume });
      if (!resume) {
        active += 1;
        maximum = Math.max(maximum, active);
        await writeJournal(f.root, taskId, attemptId, "RUNNING", {
          nativeStartedAt: new Date(1000 * (active + 1)).toISOString(),
        });
        return 4;
      }
      const count = (observations.get(taskId) || 0) + 1;
      observations.set(taskId, count);
      const complete = taskId === "one" || count >= 2;
      if (complete) {
        active -= 1;
        await writeJournal(f.root, taskId, attemptId, "COMPLETED", {
          nativeStartedAt: new Date(1000 * (QUEUE_TASKS.indexOf(taskId) + 1)).toISOString(),
          nativeFinishedAt: new Date(1000 * (QUEUE_TASKS.indexOf(taskId) + 11)).toISOString(),
        });
        return 0;
      }
      await writeJournal(f.root, taskId, attemptId, "RUNNING");
      return 4;
    };
    const result = await runQwenWorkBatch(f.args, { execute, sleep: async () => {} });
    assert.equal(result.phase, "COMPLETED");
    assert.equal(result.frozen.run_slots, 3);
    assert.equal(maximum, 3);
    assert.deepEqual(calls.filter((call) => !call.resume).map((call) => call.taskId), QUEUE_TASKS);
    assert.ok(result.events.some((event) => event.event === "TASK_DISPATCH_RETURNED"
      && event.completed_before_dispatch > 0));
    const receipt = JSON.parse(await readFile(result.receipt_file, "utf8"));
    assert.equal(receipt.run_slots, 3);
    assert.equal(receipt.integrity.no_duplicate_dispatch, true);
    assert.equal(receipt.integrity.dynamic_refill_observed, true);
    assert.equal(receipt.integrity.valid, true);
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

test("QwenWork queue resumes an attention task with the same attempt and never resends", async () => {
  const f = await fixture(["one", "two"]);
  const calls = [];
  let first = true;
  try {
    const execute = async (argv) => {
      const identity = await identityFrom(argv);
      const taskId = identity.task_id;
      const attemptId = identity.attempt_id;
      const resume = argv.includes("--resume");
      calls.push({ taskId, attemptId, resume });
      if (!resume && first) {
        first = false;
        await writeJournal(f.root, taskId, attemptId, "NEEDS_ATTENTION", {
          sendStatus: "uncertain",
        });
        return 3;
      }
      await writeJournal(f.root, taskId, attemptId, "COMPLETED");
      return 0;
    };
    const firstResult = await runQwenWorkBatch(f.args, { execute });
    assert.equal(firstResult.phase, "NEEDS_ATTENTION");
    assert.deepEqual(firstResult.tasks.map((task) => task.phase), ["NEEDS_ATTENTION", "PENDING"]);
    const resumed = await runQwenWorkBatch([...f.args, "--resume"], { execute });
    assert.equal(resumed.phase, "COMPLETED");
    assert.deepEqual(calls.filter((call) => !call.resume).map((call) => call.taskId), ["one", "two"]);
    assert.equal(calls[1].resume, true);
    assert.equal(calls[1].attemptId, calls[0].attemptId);
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

test("QwenWork queue recovers a stale owner only with a fresh idle probe and original attempt", async () => {
  const f = await fixture(["one"]);
  let first = true;
  const calls = [];
  try {
    const execute = async (argv) => {
      const identity = await identityFrom(argv);
      calls.push({ attemptId: identity.attempt_id, resume: argv.includes("--resume") });
      if (first) {
        first = false;
        await writeJournal(f.root, identity.task_id, identity.attempt_id, "NEEDS_ATTENTION",
          { sendStatus: "uncertain" });
        return 3;
      }
      await writeJournal(f.root, identity.task_id, identity.attempt_id, "COMPLETED");
      return 0;
    };
    const attention = await runQwenWorkBatch(f.args, { execute });
    assert.equal(attention.phase, "NEEDS_ATTENTION");
    const ownerPath = join(f.root, ".general-e2e", "queues", "qwenwork", "owner-lock.json");
    await writeJson(ownerPath, {
      schema_version: "wildclawbench.general-e2e-qwenwork-queue-owner/v1",
      owner_id: "stale-owner", queue_id: "qwen-fixture", frozen_sha256: attention.frozen_sha256,
      pid: 101, host: "fixture-host", process_start_identity: "old-start",
      acquired_at: "2026-09-23T00:00:00Z",
    });
    const probe = JSON.parse(await readFile(f.probePath, "utf8"));
    probe.probed_at = new Date().toISOString();
    probe.app.cdp = { ready: true, browser_identity_present: true };
    await writeJson(f.probePath, probe);
    const args = [...f.args];
    args[args.indexOf("--probe-sha256") + 1] = sha256(`${JSON.stringify(probe, null, 2)}\n`);
    const resumed = await runQwenWorkBatch([...args, "--resume", "--recover-stale-owner"], {
      execute,
      ownerOverrides: { hostname: "fixture-host", pid: 202, ownerId: "new-owner",
        processStartIdentity: async (pid) => pid === 202 ? "new-start" : "old-start",
        processAlive: async () => false },
    });
    assert.equal(resumed.phase, "COMPLETED");
    assert.ok(resumed.events.some((event) => event.event === "QUEUE_STALE_OWNER_RECOVERED"));
    assert.deepEqual(calls, [
      { attemptId: calls[0].attemptId, resume: false },
      { attemptId: calls[0].attemptId, resume: true },
    ]);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("QwenWork queue never converts an attention-only queue into COMPLETED", async () => {
  const f = await fixture(["one"]);
  try {
    let first = true;
    const execute = async (argv) => {
      const identity = await identityFrom(argv);
      if (first) {
        first = false;
        await writeJournal(f.root, identity.task_id, identity.attempt_id, "NEEDS_ATTENTION", { sendStatus: "uncertain" });
        return 3;
      }
      await writeJournal(f.root, identity.task_id, identity.attempt_id, "COMPLETED");
      return 0;
    };
    const attention = await runQwenWorkBatch(f.args, { execute });
    assert.equal(attention.phase, "NEEDS_ATTENTION");
    const completed = await runQwenWorkBatch([...f.args, "--resume"], { execute });
    assert.equal(completed.phase, "COMPLETED");
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

test("QwenWork queue freezes run slots and rejects config and attempt drift on resume", async () => {
  const f = await fixture(["one"]);
  try {
    const execute = async (argv) => {
      const identity = await identityFrom(argv);
      await writeJournal(f.root, identity.task_id, identity.attempt_id, "COMPLETED");
      return 0;
    };
    const result = await runQwenWorkBatch(f.args, { execute });
    assert.equal(result.phase, "COMPLETED");
    await assert.rejects(
      runQwenWorkBatch([...f.args, "--run-slots", "2", "--resume"], { execute }),
      /CONFIG_DRIFT|QUEUE_CONFIG_DRIFT/u,
    );

    const journalPath = join(controlRoot(f.root, "one"), "dispatch-journal.json");
    const current = JSON.parse(await readFile(journalPath, "utf8"));
    current.identity.attempt_id = "foreign-attempt";
    await writeJson(journalPath, current);
    await assert.rejects(
      runQwenWorkBatch([...f.args, "--resume"], { execute }),
      /ATTEMPT_DRIFT|QUEUE_ATTEMPT_DRIFT|IDENTITY_MISMATCH/u,
    );
    assert.throws(() => parseBatchArgs([...f.args, "--run-slots", "9"]), /1–8/u);
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

test("QwenWork queue keeps native timing unavailable separate from valid execution", async () => {
  const f = await fixture(["one"]);
  try {
    const execute = async (argv) => {
      const identity = await identityFrom(argv);
      await writeJournal(f.root, identity.task_id, identity.attempt_id, "COMPLETED");
      return 0;
    };
    const result = await runQwenWorkBatch(f.args, { execute });
    const receipt = JSON.parse(await readFile(result.receipt_file, "utf8"));
    assert.equal(receipt.integrity.valid, true);
    assert.equal(receipt.native_interval_coverage.known, 0);
    assert.equal(receipt.native_interval_coverage.total, 1);
    assert.equal(receipt.concurrency_evidence.status, "INSUFFICIENT_EVIDENCE");
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

test("QwenWork queue prepares all projects before its first prompt dispatch", async () => {
  const f = await fixture(["one", "two", "three"]);
  const calls = [];
  try {
    const execute = async (argv) => {
      const identity = await identityFrom(argv);
      const prepareOnly = argv.includes("--prepare-only");
      calls.push({ task: identity.task_id, prepareOnly, resume: argv.includes("--resume") });
      await writeJournal(f.root, identity.task_id, identity.attempt_id,
        prepareOnly ? "READY_TO_DISPATCH" : "COMPLETED",
        prepareOnly ? { dispatchAttemptCount: 0, sendStatus: "intent_persisted", finished: false } : {});
      return 0;
    };
    const result = await runQwenWorkBatch([...f.args, "--preprepare-projects", "--skip-clarifications", "--require-token-exposure"], { execute });
    assert.equal(result.phase, "COMPLETED");
    assert.equal(result.frozen.clarification_policy, "skip-question-card");
    assert.equal(JSON.parse(await readFile(result.tasks[0].config_path, "utf8")).control.clarification_policy,
      "skip-question-card");
    assert.equal(result.frozen.require_token_usage_exposure, true);
    assert.equal(JSON.parse(await readFile(result.tasks[0].config_path, "utf8")).control.require_token_usage_exposure,
      true);
    assert.deepEqual(calls.map((row) => [row.task, row.prepareOnly]), [
      ["one", true], ["two", true], ["three", true],
      ["one", false], ["two", false], ["three", false],
    ]);
    assert.ok(calls.slice(3).every((row) => row.resume));
    assert.deepEqual(result.tasks.map((row) => row.dispatch_attempt_count), [1, 1, 1]);
  } finally {
    await rm(f.root, { recursive: true, force: true });
  }
});

for (const phase of ["DISPATCH_UNCERTAIN", "PREPARING"]) {
  test(`QwenWork queue pauses ${phase} and resumes only its original attempt before refill`, async () => {
    const f = await fixture(["one", "two"]);
    const calls = [];
    try {
      const execute = async (argv) => {
        const identity = await identityFrom(argv);
        const resume = argv.includes("--resume");
        calls.push({ task: identity.task_id, attempt: identity.attempt_id, resume });
        const interrupted = calls.length === 1;
        await writeJournal(f.root, identity.task_id, identity.attempt_id, interrupted ? phase : "COMPLETED", {
          sendStatus: interrupted ? "uncertain" : "sent",
          dispatchAttemptCount: interrupted && phase === "PREPARING" ? 0 : 1,
        });
        return interrupted ? 1 : 0;
      };
      const first = await runQwenWorkBatch(f.args, { execute });
      assert.equal(first.phase, "NEEDS_ATTENTION");
      assert.deepEqual(first.tasks.map((row) => row.phase), ["NEEDS_ATTENTION", "PENDING"]);
      assert.equal(calls.length, 1);
      await assert.rejects(readFile(first.receipt_file), { code: "ENOENT" });
      const resumed = await runQwenWorkBatch([...f.args, "--resume"], { execute });
      assert.equal(resumed.phase, "COMPLETED");
      assert.deepEqual(calls.map((row) => [row.task, row.resume]), [["one", false], ["one", true], ["two", false]]);
      assert.equal(calls[0].attempt, calls[1].attempt);
    } finally { await rm(f.root, { recursive: true, force: true }); }
  });
}

test("unresolved sending intent never publishes a completion receipt after resume", async () => {
  const f = await fixture(["one"]);
  try {
    const execute = async (argv) => {
      const identity = await identityFrom(argv);
      await writeJournal(f.root, identity.task_id, identity.attempt_id, "DISPATCH_UNCERTAIN", { sendStatus: "uncertain" });
      return 3;
    };
    const first = await runQwenWorkBatch(f.args, { execute });
    const resumed = await runQwenWorkBatch([...f.args, "--resume"], { execute });
    assert.equal(first.phase, "NEEDS_ATTENTION");
    assert.equal(resumed.phase, "NEEDS_ATTENTION");
    await assert.rejects(readFile(resumed.receipt_file), { code: "ENOENT" });
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("legacy completed queue with a nonterminal journal is rejected without rewriting its receipt", async () => {
  const f = await fixture(["one"]);
  try {
    const result = await runQwenWorkBatch(f.args, { execute: async (argv) => {
      const identity = await identityFrom(argv);
      await writeJournal(f.root, identity.task_id, identity.attempt_id, "COMPLETED");
      return 0;
    } });
    const receipt = await readFile(result.receipt_file);
    await writeJournal(f.root, "one", result.tasks[0].attempt_id, "DISPATCH_UNCERTAIN", { sendStatus: "uncertain" });
    await assert.rejects(runQwenWorkBatch([...f.args, "--resume"]), /TERMINAL_TASK_MISMATCH/u);
    assert.deepEqual(await readFile(result.receipt_file), receipt);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("a disconnected Driver pauses a stale RUNNING journal and explicit resume clears only that infrastructure error", async () => {
  const f = await fixture(["one"]);
  let calls = 0;
  try {
    const execute = async (argv) => {
      calls += 1;
      const identity = await identityFrom(argv);
      if (calls === 2) return 1; // CDP disappeared before the Driver could update its journal.
      await writeJournal(f.root, identity.task_id, identity.attempt_id, calls === 1 ? "RUNNING" : "COMPLETED");
      return 0;
    };
    const paused = await runQwenWorkBatch(f.args, { execute });
    assert.equal(paused.phase, "NEEDS_ATTENTION");
    assert.match(paused.tasks[0].driver_error, /DRIVER_EXIT/u);
    assert.equal(calls, 2);
    const resumed = await runQwenWorkBatch([...f.args, "--resume"], { execute });
    assert.equal(resumed.phase, "COMPLETED");
    assert.equal(resumed.tasks[0].driver_error, null);
    assert.equal(resumed.tasks[0].attempt_id, paused.tasks[0].attempt_id);
    assert.equal(calls, 3);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});
