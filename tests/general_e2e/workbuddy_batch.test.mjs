import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  parseBatchArgs,
  runWorkBuddyBatch,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/batch.mjs";

async function fixture(task_ids = ["one", "two", "three"]) {
  const root = await realpath(await mkdtemp(join(tmpdir(), "workbuddy-queue-")));
  const prompt = "fixture";
  const tasks = [];
  for (const task_id of task_ids) {
    const path = `execution/tasks/${task_id}`;
    await mkdir(join(root, path, "workspace"), { recursive: true });
    await writeFile(join(root, path, "PROMPT.md"), prompt);
    tasks.push({ task_id, prompt: { path: `${path}/PROMPT.md`, sent_sha256: createHash("sha256").update(prompt).digest("hex") }, workspace: { path: `${path}/workspace` } });
  }
  await writeFile(join(root, "manifest.json"), JSON.stringify({ schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1", manifest_kind: "execution", batch_id: "b", unit_id: "u", dataset: { id: "d", digest: "d".repeat(64) }, unit: { harness: { id: "workbuddy", platform: "macos" }, model: { requested_id: "fixture" } }, task_ids, tasks }));
  const calls = [];
  const args = ["--unit-root", root, "--queue-id", "serial", "--endpoint", "http://127.0.0.1:9229", "--expected-permission", "default-sandbox"];
  let clock = Date.parse("2026-09-21T06:00:00.000Z");
  const nativeStarts = new Map();
  const writeAttempt = async (task, attempt, phase) => {
    const control = join(root, ".general-e2e", "execution", task, "workbuddy");
    const conversation = `conversation-${task}`;
    const cwd = join(root, "execution", "tasks", task, "workspace");
    clock += 1_000;
    if (!nativeStarts.has(task)) nativeStarts.set(task, clock - 250);
    await writeFile(join(control, "dispatch-journal.json"), JSON.stringify({
      identity: { task_id: task, attempt_id: attempt },
      phase,
      prompt: { sent_at: new Date(clock - 500).toISOString() },
      send: { dispatch_attempt_count: 1 },
      native: { conversation_id: conversation, request_id: `request-${task}`, cwd },
      execution: { started_at: new Date(clock - 500).toISOString(), error: null },
      history: [{ phase, at: new Date(clock).toISOString() }],
    }));
    await writeFile(join(control, "execution-state.json"), JSON.stringify({
      phase,
      session: { session_id: conversation, cwd },
      execution: { finished_at: phase === "COMPLETED" ? new Date(clock).toISOString() : null, error: null },
    }));
    await writeFile(join(control, "native-binding.json"), JSON.stringify({
      identity: { task_id: task, attempt_id: attempt },
      workspace: cwd,
      conversation_id: conversation,
      request_id: `request-${task}`,
      runtime_snapshot: {
        request: {
          timestamp: nativeStarts.get(task),
          completedAt: phase === "COMPLETED" ? clock : null,
        },
      },
    }));
  };
  const execute = async (argv) => {
    const task = argv[argv.indexOf("--task-id") + 1];
    const attempt = argv[argv.indexOf("--attempt-id") + 1];
    calls.push({ task, attempt, resume: argv.includes("--resume") });
    await writeAttempt(task, attempt, "COMPLETED");
    return 0;
  };
  return { root, calls, args, execute, writeAttempt };
}

test("WorkBuddy serial queue freezes scope and resumes without dispatching completed tasks", async () => {
  const f = await fixture();
  try {
    const first = await runWorkBuddyBatch(f.args, { execute: f.execute });
    assert.equal(first.phase, "COMPLETED");
    assert.deepEqual(f.calls.map((x) => x.task), ["one", "two", "three"]);
    assert.equal(new Set(first.tasks.map((x) => x.attempt_id)).size, 3);
    await runWorkBuddyBatch([...f.args, "--resume"], { execute: f.execute });
    assert.equal(f.calls.length, 3);
    await assert.rejects(runWorkBuddyBatch([...f.args, "--resume", "--expected-model", "different"], { execute: f.execute }), /CONFIG_DRIFT/u);
    const path = join(f.root, ".general-e2e/execution/one/workbuddy/dispatch-journal.json");
    await writeFile(path, JSON.stringify({ identity: { attempt_id: "different" }, phase: "COMPLETED" }));
    await assert.rejects(runWorkBuddyBatch([...f.args, "--resume"], { execute: f.execute }), /ATTEMPT_DRIFT/u);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("WorkBuddy queue stops on uncertain send and resumes only the reserved attempt", async () => {
  const f = await fixture();
  try {
    let firstCall = true;
    const execute = async (args) => {
      await f.execute(args);
      if (firstCall) {
        firstCall = false;
        const path = join(f.root, ".general-e2e/execution/one/workbuddy/dispatch-journal.json");
        const journal = JSON.parse(await readFile(path));
        journal.phase = "NEEDS_ATTENTION";
        await writeFile(path, JSON.stringify(journal));
        return 3;
      }
      return 0;
    };
    const first = await runWorkBuddyBatch(f.args, { execute });
    assert.equal(first.phase, "NEEDS_ATTENTION");
    assert.deepEqual(first.tasks.map((x) => x.phase), ["NEEDS_ATTENTION", "PENDING", "PENDING"]);
    const resumed = await runWorkBuddyBatch([...f.args, "--resume"], { execute });
    assert.equal(resumed.phase, "COMPLETED");
    assert.equal(f.calls[1].resume, true);
    assert.equal(f.calls[1].attempt, f.calls[0].attempt);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("WorkBuddy queue defaults to three background slots and refills after a terminal task", async () => {
  const f = await fixture(["one", "two", "three", "four", "five"]);
  const observations = new Map();
  let active = 0;
  let maximum = 0;
  try {
    const execute = async (argv) => {
      const task = argv[argv.indexOf("--task-id") + 1];
      const attempt = argv[argv.indexOf("--attempt-id") + 1];
      const resume = argv.includes("--resume");
      f.calls.push({ task, attempt, resume });
      if (!resume) {
        active += 1;
        maximum = Math.max(maximum, active);
        await f.writeAttempt(task, attempt, "RUNNING");
        return 4;
      }
      const count = (observations.get(task) || 0) + 1;
      observations.set(task, count);
      const shouldComplete = task === "one" || count >= 2;
      if (shouldComplete) {
        active -= 1;
        await f.writeAttempt(task, attempt, "COMPLETED");
        return 0;
      }
      await f.writeAttempt(task, attempt, "RUNNING");
      return 4;
    };
    const result = await runWorkBuddyBatch(f.args, { execute, sleep: async () => {} });
    assert.equal(result.phase, "COMPLETED");
    assert.equal(result.frozen.run_slots, 3);
    assert.equal(maximum, 3);
    const dispatches = f.calls.filter((call) => !call.resume).map((call) => call.task);
    assert.deepEqual(dispatches, ["one", "two", "three", "four", "five"]);
    const fourth = result.events.find((event) => event.event === "TASK_DISPATCH_RETURNED" && event.task_id === "four");
    assert.ok(fourth.completed_before_dispatch > 0);
    const receipt = JSON.parse(await readFile(result.receipt_file, "utf8"));
    assert.equal(receipt.run_slots, 3);
    assert.equal(receipt.observed_max_concurrency, 3);
    assert.equal(receipt.native_observed_max_concurrency, 3);
    assert.deepEqual(receipt.native_interval_coverage, { known: 5, total: 5, unit: "task" });
    assert.equal(receipt.integrity.no_duplicate_dispatch, true);
    assert.equal(receipt.integrity.dynamic_refill_observed, true);
    assert.equal(receipt.integrity.valid, true);
    assert.equal(receipt.concurrency_evidence.status, "PASS");
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("WorkBuddy completed queue remains valid when short tasks do not overlap natively", async () => {
  const f = await fixture();
  try {
    const result = await runWorkBuddyBatch(f.args, { execute: f.execute });
    const receipt = JSON.parse(await readFile(result.receipt_file, "utf8"));
    assert.equal(receipt.integrity.valid, true);
    assert.equal(receipt.native_observed_max_concurrency, 1);
    assert.equal(receipt.integrity.observed_requested_concurrency, false);
    assert.equal(receipt.concurrency_evidence.status, "INSUFFICIENT_EVIDENCE");
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("WorkBuddy queue keeps native timing unavailable separate and rejects binding drift", async () => {
  const f = await fixture(["one"]);
  try {
    const bindingPath = join(f.root, ".general-e2e/execution/one/workbuddy/native-binding.json");
    const executeWithoutBinding = async (argv) => {
      const code = await f.execute(argv);
      await rm(bindingPath);
      return code;
    };
    const result = await runWorkBuddyBatch(f.args, { execute: executeWithoutBinding });
    const noTiming = JSON.parse(await readFile(result.receipt_file, "utf8"));
    assert.equal(noTiming.integrity.valid, true);
    assert.equal(noTiming.native_interval_coverage.known, 0);
    assert.equal(noTiming.concurrency_evidence.status, "INSUFFICIENT_EVIDENCE");

    await f.writeAttempt("one", result.tasks[0].attempt_id, "COMPLETED");
    const binding = JSON.parse(await readFile(bindingPath, "utf8"));
    binding.request_id = "foreign-request";
    await writeFile(bindingPath, JSON.stringify(binding));
    await assert.rejects(
      runWorkBuddyBatch([...f.args, "--resume"], { execute: f.execute }),
      /BINDING_DRIFT/u,
    );
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("WorkBuddy queue freezes run slots and rejects a changed concurrency on resume", async () => {
  const f = await fixture();
  try {
    await runWorkBuddyBatch(f.args, { execute: f.execute });
    await assert.rejects(
      runWorkBuddyBatch([...f.args, "--run-slots", "2", "--resume"], { execute: f.execute }),
      /CONFIG_DRIFT/u,
    );
    assert.throws(() => parseBatchArgs([...f.args, "--run-slots", "9"]), /1–8/u);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});
