import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  parseBatchArgs,
  runWorkBuddyBatch,
  resolveWorkBuddyBatchInvocation,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/batch.mjs";
import { recoverWorkBuddyQueue } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/recover-queue.mjs";

const digest = value => createHash("sha256").update(value).digest("hex");

test("WorkBuddy batch API imports from stdin without interpreting '-' as an executable path", () => {
  const target = new URL("../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/batch.mjs", import.meta.url).href;
  const child = spawnSync(process.execPath, ["--input-type=module", "-"], {
    input: `import {resolveWorkBuddyBatchInvocation} from ${JSON.stringify(target)};console.log(typeof resolveWorkBuddyBatchInvocation);`, encoding: "utf8",
  });
  assert.equal(child.status, 0, child.stderr);
  assert.equal(child.stdout.trim(), "function");
});

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

test("preflight failure without a journal stops before the next task and is never completion or redispatch", async () => {
  const f = await fixture();
  try {
    let calls = 0;
    const execute = async () => { calls++; return 2; };
    const result = await runWorkBuddyBatch(f.args, { execute });
    assert.equal(result.phase, "NEEDS_ATTENTION");
    assert.equal(calls, 1);
    assert.deepEqual(result.tasks.map(t => t.phase), ["DISPATCHING", "PENDING", "PENDING"]);
    const resumed = await runWorkBuddyBatch([...f.args, "--resume"], { execute });
    assert.equal(resumed.phase, "NEEDS_ATTENTION");
    assert.equal(calls, 1);
    await assert.rejects(readFile(result.receipt_file, "utf8"), { code: "ENOENT" });
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

test("zero-send preparation failure stops refill while accepted tasks drain to terminal", async () => {
  const f = await fixture(["one", "two", "broken", "never"]);
  try {
    const execute = async argv => {
      const task = argv[argv.indexOf("--task-id") + 1], attempt = argv[argv.indexOf("--attempt-id") + 1];
      f.calls.push({ task, resume: argv.includes("--resume") });
      if (task === "broken") {
        await writeFile(join(f.root, ".general-e2e/execution/broken/workbuddy/dispatch-journal.json"), JSON.stringify({
          identity: { task_id: task, attempt_id: attempt }, phase: "FAILED", send: { dispatch_attempt_count: 0 },
          native: {}, execution: { error: { code: "WORKBUDDY_PRE_SEND_DRIVER_ERROR" } },
        }));
        return 2;
      }
      await f.writeAttempt(task, attempt, argv.includes("--resume") ? "COMPLETED" : "RUNNING");
      return argv.includes("--resume") ? 0 : 4;
    };
    const result = await runWorkBuddyBatch(f.args, { execute, sleep: async () => {} });
    assert.equal(result.phase, "NEEDS_ATTENTION");
    assert.deepEqual(result.tasks.map(t => t.phase), ["COMPLETED", "COMPLETED", "FAILED", "PENDING"]);
    assert.equal(f.calls.filter(c => c.task === "broken").length, 1);
    assert.equal(f.calls.some(c => c.task === "never"), false);
    await assert.rejects(readFile(result.receipt_file), { code: "ENOENT" });
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

async function recoveryFixture() {
  const f = await fixture(["sent", "broken", "pending"]);
  const manifestPath = join(f.root, "manifest.json"), unit = JSON.parse(await readFile(manifestPath));
  for (const task of unit.tasks) task.workspace.entries = [];
  await writeFile(manifestPath, JSON.stringify(unit));
  const execute = async argv => {
    const task = argv[argv.indexOf("--task-id") + 1], attempt = argv[argv.indexOf("--attempt-id") + 1];
    if (task !== "broken") return f.execute(argv);
    const root = join(f.root, "execution/tasks", task), workspace = join(root, "workspace");
    const j = { schema_version: "wildclawbench.general-e2e-workbuddy-dispatch-journal/v1",
      identity: { batch_id: "b", unit_id: "u", task_id: task, attempt_id: attempt }, dataset: unit.dataset,
      phase: "FAILED", task_root: root, candidate_workspace: workspace,
      prompt: { path: join(root, "PROMPT.md"), sha256: digest("fixture"), send_status: "not_sent", sent_at: null },
      send: { dispatch_attempt_count: 0, dispatch_armed_at: null, dispatch_returned_at: null }, native: { baseline: null },
      expected_ui: { workspace, model: "fixture", permission: "default-sandbox" }, runtime: { endpoint: "http://127.0.0.1:9229" },
      verified_ui: null, execution: { error: { code: "WORKBUDDY_PRE_SEND_DRIVER_ERROR", message: "WorkBuddy 新建任务按钮数量异常：0" } },
      history: [{ event: "PRE_SEND_DRIVER_ERROR", phase: "FAILED" }] };
    await writeFile(join(f.root, ".general-e2e/execution/broken/workbuddy/dispatch-journal.json"), JSON.stringify(j));
    return 2;
  };
  const first = await runWorkBuddyBatch(f.args, { execute });
  const queuePath = first.state_file, queue = JSON.parse(await readFile(queuePath));
  delete queue.frozen.batch_sha256; delete queue.frozen.ui_sha256;
  queue.frozen_sha256 = digest(JSON.stringify(queue.frozen));
  await writeFile(queuePath, JSON.stringify(queue));
  const ownerPath = join(dirname(queuePath), "owner-lock.json");
  await writeFile(ownerPath, JSON.stringify({ pid: 999999, host: hostname(), queue_id: "serial", started_at: "fixture" }));
  const entry = fileURLToPath(new URL("../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/batch.mjs", import.meta.url));
  const config = await resolveWorkBuddyBatchInvocation(f.args);
  const recovery = { schema_version: "wildclawbench.workbuddy-zero-send-queue-repair/v1", reason: "Repair native UI preparation only",
    original_argv: [process.execPath, entry, ...f.args], original_batch_sha256: digest(await readFile(entry)),
    queue_sha256: digest(await readFile(queuePath)), expected_owner_pid: 999999, retry_task_ids: ["broken"],
    replacement_sources: Object.fromEntries(["driver_sha256", "batch_sha256", "ui_sha256"].map(k => [k, config.frozen[k]])),
    output_root: join(f.root, ".general-e2e/queue-repairs/test") };
  const recoveryPath = join(f.root, "recovery.json"); await writeFile(recoveryPath, JSON.stringify(recovery));
  return { ...f, queuePath, ownerPath, recoveryPath, recovery, first,
    dependencies: { inspectOwner: async () => ({ exited: true }), verifyIdle: async () => ({ verified: true, process: { pid: 123, started_at: "fixed" } }) } };
}

test("explicit dead-owner zero-send recovery preserves accepted attempts and original evidence", async () => {
  const f = await recoveryFixture();
  try {
    const sent = await readFile(join(f.root, ".general-e2e/execution/sent/workbuddy/dispatch-journal.json"));
    const originalQueue = await readFile(f.queuePath);
    const result = await recoverWorkBuddyQueue(f.recoveryPath, f.dependencies);
    assert.equal(result.status, "RECOVERED"); assert.equal(result.new_prompts_sent, 0);
    const queue = JSON.parse(await readFile(f.queuePath));
    assert.deepEqual(queue.tasks.map(t => t.phase), ["COMPLETED", "PENDING", "PENDING"]);
    assert.deepEqual(await readFile(join(f.recovery.output_root, "original-queue.json")), originalQueue);
    assert.deepEqual(await readFile(join(f.root, ".general-e2e/execution/sent/workbuddy/dispatch-journal.json")), sent);
    assert.equal((await recoverWorkBuddyQueue(f.recoveryPath, { ...f.dependencies, resume: true })).idempotent, true);
    const resumed = await runWorkBuddyBatch([...f.args, "--resume"], { execute: f.execute });
    assert.equal(resumed.phase, "COMPLETED");
    assert.deepEqual(f.calls.map(c => c.task), ["sent", "broken", "pending"]);
    const original = queue.source_repairs[0].artifacts.find(x => x.path.endsWith("broken/dispatch-journal.json"));
    await writeFile(join(f.root, original.path), "changed");
    await assert.rejects(runWorkBuddyBatch([...f.args, "--resume"], { execute: f.execute }), /RECOVERY_ORIGINAL_INVALID|REPAIR_ARTIFACT_DRIFT|Unexpected token/u);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("queue recovery refuses active owners, unverified native idle and armed sends", async () => {
  for (const scenario of ["active", "busy", "armed"]) {
    const f = await recoveryFixture();
    try {
      const queue = await readFile(f.queuePath), owner = await readFile(f.ownerPath);
      const deps = { ...f.dependencies };
      if (scenario === "active") deps.inspectOwner = async () => ({ exited: false });
      if (scenario === "busy") deps.verifyIdle = async () => ({ verified: false });
      if (scenario === "armed") {
        const path = join(f.root, ".general-e2e/execution/broken/workbuddy/dispatch-journal.json");
        const j = JSON.parse(await readFile(path)); j.send.dispatch_armed_at = "armed"; await writeFile(path, JSON.stringify(j));
      }
      await assert.rejects(recoverWorkBuddyQueue(f.recoveryPath, deps), /OWNER_EXIT_UNVERIFIED|FRESH_IDLE_REQUIRED|NOT_REGISTERED_ZERO_SEND_FAILURE/u);
      assert.deepEqual(await readFile(f.queuePath), queue); assert.deepEqual(await readFile(f.ownerPath), owner);
    } finally { await rm(f.root, { recursive: true, force: true }); }
  }
});

test("interrupted journal archival resumes the same recovery without restoring or resending old attempts", async () => {
  const f = await recoveryFixture();
  try {
    const before = await readFile(f.queuePath);
    await assert.rejects(recoverWorkBuddyQueue(f.recoveryPath, { ...f.dependencies,
      afterArchive: async () => { throw new Error("injected archival interruption"); } }), /injected archival interruption/u);
    assert.deepEqual(await readFile(f.queuePath), before);
    await assert.rejects(readFile(join(f.root, ".general-e2e/execution/broken/workbuddy/dispatch-journal.json")), { code: "ENOENT" });
    const saved = await readFile(join(f.recovery.output_root, "original-attempts/broken/dispatch-journal.json"));
    const result = await recoverWorkBuddyQueue(f.recoveryPath, { ...f.dependencies, resume: true });
    assert.equal(result.status, "RECOVERED"); assert.equal(result.new_prompts_sent, 0);
    assert.deepEqual(await readFile(join(f.recovery.output_root, "original-attempts/broken/dispatch-journal.json")), saved);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("a recovery interrupted after queue commit only finishes its receipt", async () => {
  const f = await recoveryFixture();
  try {
    await assert.rejects(recoverWorkBuddyQueue(f.recoveryPath, { ...f.dependencies,
      afterQueueCommit: async () => { throw new Error("injected postcommit interruption"); } }), /injected postcommit interruption/u);
    const committed = await readFile(f.queuePath);
    const result = await recoverWorkBuddyQueue(f.recoveryPath, { ...f.dependencies, resume: true });
    assert.equal(result.status, "RECOVERED"); assert.equal(result.new_prompts_sent, 0);
    assert.deepEqual(await readFile(f.queuePath), committed);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("a normally released queue owner is recovered from its frozen queue identity without fabricating a lock", async () => {
  const f = await recoveryFixture();
  try {
    const owner = JSON.parse(await readFile(f.ownerPath));
    await rm(f.ownerPath);
    const q = JSON.parse(await readFile(f.queuePath)); q.last_owner = owner;
    await writeFile(f.queuePath, JSON.stringify(q));
    const m = JSON.parse(await readFile(f.recoveryPath)); m.queue_sha256 = digest(await readFile(f.queuePath));
    await writeFile(f.recoveryPath, JSON.stringify(m));
    const result = await recoverWorkBuddyQueue(f.recoveryPath, f.dependencies);
    assert.equal(result.status, "RECOVERED");
    assert.deepEqual(JSON.parse(await readFile(join(f.recovery.output_root, "owner-record.from-queue.json"))), owner);
    await assert.rejects(readFile(join(f.recovery.output_root, "owner-lock.original.json")), { code: "ENOENT" });
    await assert.rejects(readFile(f.ownerPath), { code: "ENOENT" });
  } finally { await rm(f.root, { recursive: true, force: true }); }
});

test("repeated zero-send preparation recovery preserves and relocates the complete prior proof chain", async () => {
  const f = await recoveryFixture();
  try {
    await recoverWorkBuddyQueue(f.recoveryPath, f.dependencies);
    const proofPath = join(f.root, ".general-e2e/execution/broken/workbuddy/zero-send-recovery.json");
    const firstProofBytes = await readFile(proofPath), firstProof = JSON.parse(firstProofBytes);
    const oldJournal = JSON.parse(await readFile(join(f.root, firstProof.original_journal.path)));
    oldJournal.execution.error.message = "WORKBUDDY_UI_ERROR_BOUNDARY: native error page requires verified idle recovery";
    oldJournal.pre_send_recovery = firstProof;
    await writeFile(join(f.root, ".general-e2e/execution/broken/workbuddy/dispatch-journal.json"), JSON.stringify(oldJournal));
    const q = JSON.parse(await readFile(f.queuePath)); q.phase = "NEEDS_ATTENTION"; q.tasks[1].phase = "FAILED";
    q.tasks[1].error = oldJournal.execution.error; await writeFile(f.queuePath, JSON.stringify(q));
    const second = { ...f.recovery, queue_sha256: digest(await readFile(f.queuePath)),
      output_root: join(f.root, ".general-e2e/queue-repairs/test-second") };
    const secondPath = join(f.root, "recovery-second.json"); await writeFile(secondPath, JSON.stringify(second));
    const result = await recoverWorkBuddyQueue(secondPath, f.dependencies);
    assert.equal(result.status, "RECOVERED"); assert.equal(result.new_prompts_sent, 0);
    const archive = join(second.output_root, "original-case-recovery/broken/zero-send-recovery.json");
    assert.deepEqual(await readFile(archive), firstProofBytes);
    const nextProof = JSON.parse(await readFile(proofPath));
    assert.equal(nextProof.prior_sources.length, 2);
    const config = await resolveWorkBuddyBatchInvocation(f.args);
    const broken = config.configs.find(c => c.task.task_id === "broken");
    assert.equal(broken.zeroSendRecovery.sources.length, 4);
    const resumed = await runWorkBuddyBatch([...f.args, "--resume"], { execute: f.execute });
    assert.equal(resumed.phase, "COMPLETED");
    assert.deepEqual(f.calls.map(c => c.task), ["sent", "broken", "pending"]);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});
