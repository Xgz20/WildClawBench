import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { runWorkBuddyBatch } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/batch.mjs";

async function fixture() {
  const root = await realpath(await mkdtemp(join(tmpdir(), "workbuddy-queue-")));
  const task_ids = ["one", "two", "three"];
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
  const execute = async (argv) => {
    const task = argv[argv.indexOf("--task-id") + 1];
    const attempt = argv[argv.indexOf("--attempt-id") + 1];
    calls.push({ task, attempt, resume: argv.includes("--resume") });
    const path = join(root, ".general-e2e", "execution", task, "workbuddy", "dispatch-journal.json");
    await writeFile(path, JSON.stringify({ identity: { attempt_id: attempt }, phase: "COMPLETED" }));
    return 0;
  };
  return { root, calls, args, execute };
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
