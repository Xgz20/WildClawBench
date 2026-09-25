import { test } from "node:test";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createBatchState, nextTaskAction, selectBatchTaskAction, summarizeBatchConcurrency, parseBatchArgs, planFor, assertStateMatches } from "../batch.mjs";

const ids = ["07_Website_Generation_task_fixture_1", "07_Website_Generation_task_fixture_2", "07_Website_Generation_task_fixture_3"];
async function fixture(t) {
  const raw = await mkdtemp(join(tmpdir(), "doubao-web-batch-"));
  const { realpath } = await import("node:fs/promises"); const root = await realpath(raw);
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const id of ids) {
    await mkdir(join(root, "execution", "tasks", id, "workspace"), { recursive: true });
    await writeFile(join(root, "execution", "tasks", id, "PROMPT.md"), `Build ${id}.\n`);
    await writeFile(join(root, "execution", "tasks", id, "workspace", ".gitkeep"), "");
  }
  const manifest = { schema_version: "wildclawbench.web-e2e-batch/v3", batch_id: "fixture", harness: { id: "doubaowork" },
    tasks: ids.map(id => ({ task_id: id, execution_dir: `execution/tasks/${id}`, prompt_file: `execution/tasks/${id}/PROMPT.md` })) };
  await writeFile(join(root, "manifest.json"), JSON.stringify(manifest));
  return root;
}

test("Batch freezes exactly the manifest task order and resumes without treating produced files as initial input", async t => {
  const root = await fixture(t);
  const args = parseBatchArgs(["--harness-root", root, "--run-id", "fixture-run", "--run-slots", "1"]);
  const plan = await planFor(args), state = createBatchState(plan, args);
  assert.equal(plan.tasks.length, 3); assert.equal(state.tasks.length, 3);
  assertStateMatches(state, plan, args);
  await writeFile(join(root, "execution", "tasks", ids[0], "workspace", "generated.html"), "<h1>done</h1>");
  const resumedArgs = parseBatchArgs(["--harness-root", root, "--run-id", "fixture-run", "--resume"]);
  const resumed = await planFor(resumedArgs);
  assert.equal(resumed.tasks[0].initial_sha256, null);
  assertStateMatches(state, resumed, resumedArgs);
  state.tasks[1].prompt_sha256 = "f".repeat(64);
  assert.throws(() => assertStateMatches(state, resumed, resumedArgs), /TASK_PLAN_DRIFT/);
});

test("A recorded launch or single send never becomes a second dispatch on resume", () => {
  const tasks = ids.map(task_id => ({ task_id, phase: "PENDING" }));
  const state = { tasks };
  assert.deepEqual(nextTaskAction(state, {}), { action: "dispatch", task_id: ids[0] });
  tasks[0].phase = "DISPATCHING";
  assert.equal(nextTaskAction(state, {}).reason, "LAUNCH_INTENT_WITHOUT_JOURNAL");
  const journal = { [ids[0]]: { send: { dispatch_attempt_count: 1 } } };
  assert.equal(nextTaskAction(state, journal).action, "resume");
  tasks[0].phase = "NEEDS_ATTENTION";
  assert.equal(nextTaskAction(state, journal).action, "pause");
  tasks[0].phase = "SUCCEEDED";
  assert.deepEqual(nextTaskAction(state, journal), { action: "dispatch", task_id: ids[1] });
  tasks[1].phase = "SUCCEEDED"; tasks[2].phase = "SUCCEEDED";
  assert.equal(nextTaskAction(state, journal).action, "receipt");
});

test("Batch rejects unsupported slots and unsafe or incomplete identity", () => {
  const base = ["--harness-root", "/tmp/harness", "--run-id", "a"];
  assert.throws(() => parseBatchArgs([...base, "--run-slots", "4"]), /CONFIG_INVALID/);
  assert.throws(() => parseBatchArgs(["--harness-root", "/tmp/harness", "--run-id", "../other"]), /CONFIG_INVALID/);
  assert.throws(() => parseBatchArgs(["--harness-root", "/tmp/harness"]), /CONFIG_INVALID/);
});

test("Formal batch resume binds task, complete manifest, Prompt and run ID without accepting single-task mode", async t => {
  const root = await fixture(t);
  const args = parseBatchArgs(["--harness-root", root, "--run-id", "fixture-run"]);
  const plan = await planFor(args);
  const task = plan.tasks[0];
  const state = { workspace: task.task_root, prepared: { mode: "web-native-batch-task/v1", initial: { sha256: task.initial_sha256 },
    run_id: args.runId, task_ids: ids }, client: { manifest_sha256: plan.manifestSha256 },
    prompt: { sha256: task.prompt_sha256 }, identity: { task_id: task.task_id, batch_id: plan.manifest.batch_id } };
  const { validateFormalResume } = await import("../formal.mjs");
  assert.equal((await validateFormalResume(state)).taskId, ids[0]);
  state.prepared.task_ids = [ids[0]];
  await assert.rejects(() => validateFormalResume(state), /FROZEN_INPUT_DRIFT/);
  state.prepared.task_ids = ids; state.prepared.mode = "web-native-single/v1";
  await assert.rejects(() => validateFormalResume(state), /SINGLE_TASK_ONLY/);
});

test("Concurrent selector waits for exact peer binding and refills after completion", () => {
  const tasks = ids.map((task_id, i) => ({ task_id, phase: i === 0 ? "RUNNING" : "PENDING", attempt_id_sha256: i === 0 ? hashAttempt("a") : null }));
  const state = { tasks };
  const first = { send: { dispatch_attempt_count: 1 }, attempt_id: "a",
    session: { prompt_readback: { status: "verified" }, conversation_id: "123", native_request_session_id: null } };
  const journals = { [ids[0]]: first };
  assert.equal(selectBatchTaskAction(state, journals, 3).action, "resume");
  first.session.native_request_session_id = "11111111-1111-4111-8111-111111111111";
  assert.deepEqual(selectBatchTaskAction(state, journals, 3), { action: "dispatch", task_id: ids[1] });
  tasks[1].phase = "RUNNING"; tasks[1].attempt_id_sha256 = hashAttempt("b");
  journals[ids[1]] = { ...first, attempt_id: "b", session: { ...first.session, conversation_id: "789", native_request_session_id: "22222222-2222-4222-8222-222222222222" } };
  assert.deepEqual(selectBatchTaskAction(state, journals, 3), { action: "dispatch", task_id: ids[2] });
  tasks[0].phase = "SUCCEEDED"; tasks[2].phase = "RUNNING"; tasks[2].attempt_id_sha256 = hashAttempt("c");
  journals[ids[2]] = { ...first, attempt_id: "c", session: { ...first.session, conversation_id: "1213", native_request_session_id: "33333333-3333-4333-8333-333333333333" } };
  assert.deepEqual(selectBatchTaskAction(state, journals, 3, 1), { action: "resume", task_id: ids[2] });
  tasks[1].phase = "SUCCEEDED"; tasks[2].phase = "SUCCEEDED";
  assert.equal(selectBatchTaskAction(state, journals, 3).action, "receipt");
});
function hashAttempt(value) { return createHash("sha256").update(value).digest("hex"); }

test("Concurrency receipt separates scheduler occupancy from native agent overlap", () => {
  const rows = [
    { task_id: "a", prompt_sent_at: "2026-09-25T00:00:00Z", slot_released_at: "2026-09-25T00:00:10Z", native_started_at: "2026-09-25T00:00:01Z", native_finished_at: "2026-09-25T00:00:08Z" },
    { task_id: "b", prompt_sent_at: "2026-09-25T00:00:04Z", slot_released_at: "2026-09-25T00:00:12Z", native_started_at: "2026-09-25T00:00:05Z", native_finished_at: "2026-09-25T00:00:11Z" },
    { task_id: "c", prompt_sent_at: "2026-09-25T00:00:12Z", slot_released_at: "2026-09-25T00:00:18Z", native_started_at: "2026-09-25T00:00:13Z", native_finished_at: "2026-09-25T00:00:17Z" },
  ];
  const proof = summarizeBatchConcurrency(rows, 3);
  assert.equal(proof.scheduling_occupancy.value, 2);
  assert.equal(proof.native_agent_overlap.value, 2);
  rows[2].native_finished_at = null;
  const partial = summarizeBatchConcurrency(rows, 3);
  assert.equal(partial.native_agent_overlap.value, null);
  assert.equal(partial.native_agent_overlap.known_lower_bound, 2);
});
