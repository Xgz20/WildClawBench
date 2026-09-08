import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, readdir, realpath, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import { CANDIDATE_ARTIFACT_SCHEMA, TREE_HASH_ALGORITHM, snapshotWorkspace } from "../../../scripts/workspace-integrity.mjs";

import {
  buildSubmissionControl,
  initialize,
  markComplete,
  markTimeout,
  preflight,
  prepareRetry,
  recordProject,
  recordThread,
  recordWait,
  resume,
  status,
} from "../../../scripts/scoring-control.mjs";

async function writeJson(filename, value) {
  await mkdir(join(filename, ".."), { recursive: true });
  await writeFile(filename, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function fixture(taskIds = ["task-1"], modelMode = "explicit") {
  const root = await mkdtemp(join(tmpdir(), "web-e2e-scoring-control-"));
  const tasks = taskIds.map((taskId) => ({
    task_id: taskId,
    task_name: taskId,
    metric_profile: "artifactsbench-web-v1",
    task_sha256: `${taskId}-task-hash`,
    workspace_exec_sha256: `${taskId}-workspace-hash`,
  }));
  await writeJson(join(root, "manifest.json"), {
    batch_id: "batch-1",
    metric_profile: "artifactsbench-web-v1",
    scoring_skill: {
      schema_version: "wildclawbench.web-e2e-score-skill/v1",
      name: "score-web-e2e",
      version: "4.4.0",
      supported_metric_profiles: ["web-e2e-detailed-v1", "artifactsbench-web-v1"],
      task_score_schema: "wildclawbench.web-e2e-task-score/v1",
    },
    harness: { id: "workbuddy", display_name: "WorkBuddy" },
    tasks,
  });
  const receiptTasks = [];
  for (const entry of tasks) {
    const modelSelection = {
      mode: modelMode,
      requested_model: modelMode === "explicit" ? "xopglm52" : null,
      actual_model: "xopglm52",
      method: "test-readback",
    };
    const taskRoot = join(root, "score", "tasks", entry.task_id);
    const executionWorkspace = join(root, "execution", "tasks", entry.task_id, "workspace");
    await mkdir(executionWorkspace, { recursive: true });
    await mkdir(join(taskRoot, "workspace"), { recursive: true });
    await mkdir(join(taskRoot, "private-scoring"), { recursive: true });
    await writeFile(join(executionWorkspace, "index.html"), `<main>${entry.task_id}</main>`, "utf8");
    await writeFile(join(taskRoot, "workspace", "index.html"), `<main>${entry.task_id}</main>`, "utf8");
    const frozen = snapshotWorkspace(executionWorkspace).sha256;
    await writeJson(join(taskRoot, "private-scoring", "task_contract.json"), {
      metric_profile: "artifactsbench-web-v1",
      identity: { batch_id: "batch-1", task_id: entry.task_id, model: { id: "xopglm52", display_name: "xopglm52" }, harness: { id: "workbuddy" } },
    });
    await writeJson(join(taskRoot, "private-scoring", "candidate_artifact.json"), {
      schema_version: CANDIDATE_ARTIFACT_SCHEMA,
      hash_algorithm: TREE_HASH_ALGORITHM,
      batch_id: "batch-1",
      task_id: entry.task_id,
      harness_id: "workbuddy",
      model: { id: "xopglm52", display_name: "xopglm52" },
      model_selection: modelSelection,
      expected_sha256: frozen,
      attempt_id: `attempt-${entry.task_id}`,
    });
    await writeFile(join(taskRoot, ".web-e2e-scoring-ready"), `batch-1\n${entry.task_id}\n`, "utf8");
    receiptTasks.push({
      task_id: entry.task_id,
      attempt_id: `attempt-${entry.task_id}`,
      model_selection: modelSelection,
      workspace: { final_sha256: frozen },
    });
  }
  await writeJson(join(root, "execution-receipt.json"), {
    schema_version: "wildclawbench.web-e2e-execution-receipt/v1",
    batch_id: "batch-1",
    harness: { id: "workbuddy" },
    model: { id: "xopglm52", display_name: "xopglm52" },
    tasks: receiptTasks,
    integrity: { valid: true },
  });
  const receiptRaw = await readFile(join(root, "execution-receipt.json"), "utf8");
  const receiptSha256 = createHash("sha256").update(receiptRaw).digest("hex");
  for (const entry of tasks) {
    const lockFile = join(root, "score", "tasks", entry.task_id, "private-scoring", "candidate_artifact.json");
    const lock = JSON.parse(await readFile(lockFile, "utf8"));
    lock.execution_receipt = { sha256: receiptSha256 };
    await writeJson(lockFile, lock);
  }
  return root;
}

async function scoreSkillFixture(version = "4.4.0", profiles = ["web-e2e-detailed-v1", "artifactsbench-web-v1"]) {
  const root = await mkdtemp(join(tmpdir(), "score-web-e2e-skill-"));
  await writeJson(join(root, "skill-metadata.json"), {
    schema_version: "wildclawbench.web-e2e-score-skill/v1",
    name: "score-web-e2e",
    version,
    supported_metric_profiles: profiles,
    task_score_schema: "wildclawbench.web-e2e-task-score/v1",
  });
  await mkdir(join(root, "scripts"), { recursive: true });
  await writeFile(join(root, "scripts", "build_submission.mjs"), `
import fs from "node:fs";
import path from "node:path";
export function buildSubmission(packageRoot) {
  const manifest = JSON.parse(fs.readFileSync(path.join(packageRoot, "manifest.json"), "utf8"));
  const tasks = manifest.tasks.map((entry) => JSON.parse(fs.readFileSync(path.join(packageRoot, "score", "tasks", entry.task_id, "private-scoring", "task_score.json"), "utf8")));
  return {
    schema_version: "wildclawbench.web-e2e-submission/v1",
    batch_id: manifest.batch_id,
    source_revision: manifest.source_revision ?? null,
    metric_profile: manifest.metric_profile,
    created_at: new Date().toISOString(),
    unit: { model_id: "xopglm52", harness_id: "workbuddy" },
    task_ids: manifest.tasks.map((entry) => entry.task_id),
    candidate_artifacts: manifest.tasks.map((entry) => ({ task_id: entry.task_id, checked_at: new Date().toISOString(), valid: true })),
    tasks,
  };
}
`, "utf8");
  return root;
}

async function registerTask(root, task, registrationMethod = "create-local-project-dialog") {
  return recordProject(root, task.task_id, {
    projectId: `project-${task.task_id}`,
    projectPath: task.score_dir,
    hostId: "local",
    desktopVersion: "26.901.51231",
    registrationMethod,
  });
}

async function passPreflight(root, options = {}) {
  return preflight(root, {
    taskId: options.taskId,
    desktopVersion: "26.901.51231",
    scoreSkillDir: options.scoreSkillDir || await scoreSkillFixture(),
    allowRendererBridge: options.allowRendererBridge || false,
  });
}

async function writeValidScore(root, taskId) {
  const privateRoot = join(root, "score", "tasks", taskId, "private-scoring");
  await mkdir(join(privateRoot, "evidence"), { recursive: true });
  await writeFile(join(privateRoot, "evidence", "actions.md"), "browser actions", "utf8");
  const candidate = await (async () => JSON.parse(await readFile(join(privateRoot, "candidate_artifact.json"), "utf8")))();
  await writeJson(join(privateRoot, "task_score.json"), {
    schema_version: "wildclawbench.web-e2e-task-score/v1",
    identity: { batch_id: "batch-1", task_id: taskId, model: { id: "xopglm52", display_name: "xopglm52" }, harness: { id: "workbuddy" } },
    provenance: {
      task_sha256: `${taskId}-task-hash`,
      workspace_exec_sha256: `${taskId}-workspace-hash`,
      candidate_workspace_sha256: candidate.expected_sha256,
    },
    execution: { status: "completed" },
    metric_profile: "artifactsbench-web-v1",
    evaluation: { criteria: [{ evidence: [{ path: "evidence/actions.md" }] }] },
  });
}

async function recordCompletedWait(root, taskId, sequence = 1, cursor = `cursor-${sequence}`, now) {
  return recordWait(root, taskId, {
    waitSequence: sequence,
    waitCursor: cursor,
    waitStatus: "COMPLETED",
  }, { now });
}

test("init defaults to three scoring slots and assigns immutable per-task ports", async () => {
  const root = await fixture(["task-1", "task-2"]);
  const { state } = await initialize(root, ["task-2", "task-1"]);
  assert.equal(state.score_slots, 3);
  assert.equal(state.schema_revision, 4);
  assert.equal(state.score_port_base, 4173);
  assert.deepEqual(state.tasks.map((task) => task.scoring_port), [4173, 4174]);
  assert.equal(state.score_timeout_seconds, 7200);
  assert.equal(state.max_retries, 1);
  assert.equal(state.submission.status, "PENDING");
  assert.deepEqual(state.tasks.map((task) => task.task_id), ["task-2", "task-1"]);
  assert.match(await readFile(state.tasks[0].scoring_prompt_file, "utf8"), /\$score-web-e2e/);
  assert.match(await readFile(state.tasks[0].scoring_prompt_file, "utf8"), /独占本地评分端口 4173/);
  await assert.rejects(() => initialize(root, ["task-1", "task-2"]), /任务范围或顺序不可变/);
});

test("init supports explicit serial scoring and keeps slots and port base immutable", async () => {
  const root = await fixture(["task-1", "task-2"]);
  const { state } = await initialize(root, [], { scoreSlots: 1, scorePortBase: 5100 });
  assert.equal(state.score_slots, 1);
  assert.equal(state.score_port_base, 5100);
  assert.deepEqual(state.tasks.map((task) => task.scoring_port), [5100, 5101]);
  assert.equal((await initialize(root)).state.score_slots, 1);
  await assert.rejects(() => initialize(root, [], { scoreSlots: 3 }), /score_slots 不可变/);
  await assert.rejects(() => initialize(root, [], { scorePortBase: 5101 }), /score_port_base 不可变/);
});

test("init rejects a scoring port range that exceeds 65535", async () => {
  const root = await fixture(["task-1", "task-2"]);
  await assert.rejects(() => initialize(root, [], { scorePortBase: 65535 }), /无法为 2 个任务分配独立端口/);
});

test("init accepts at most eight scoring slots", async () => {
  const acceptedRoot = await fixture();
  assert.equal((await initialize(acceptedRoot, [], { scoreSlots: 8 })).state.score_slots, 8);
  const rejectedRoot = await fixture();
  await assert.rejects(() => initialize(rejectedRoot, [], { scoreSlots: 9 }), /scoreSlots 必须是 1\.\.8/);
});

test("init accepts a Harness model that was preconfigured and only read back", async () => {
  const root = await fixture(["task-1"], "current");
  const { state } = await initialize(root);
  assert.equal(state.tasks[0].task_id, "task-1");
  assert.equal(state.tasks[0].phase, "PENDING_PROJECT");
});

test("project mapping requires the exact scoring directory", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await assert.rejects(() => recordProject(root, "task-1", {
    projectId: "project-1",
    projectPath: root,
    hostId: "local",
    desktopVersion: "26.901.51231",
    registrationMethod: "create-local-project-dialog",
  }), /评分目录不一致/);
  const scoreDir = await realpath(state.tasks[0].score_dir);
  const result = await registerTask(root, { ...state.tasks[0], score_dir: scoreDir });
  assert.equal(result.next_task.project_id, "project-task-1");
});

test("preflight checks Desktop, registration mode, score Skill version and metric profile", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0], "renderer-bridge");
  const skillRoot = await scoreSkillFixture();
  await assert.rejects(() => passPreflight(root, { scoreSkillDir: skillRoot }), /allow-renderer-bridge/);
  const result = await passPreflight(root, { scoreSkillDir: skillRoot, allowRendererBridge: true });
  assert.equal(result.preflight.status, "PASSED");
  assert.equal(result.preflight.metric_profile, "artifactsbench-web-v1");
  assert.equal(result.preflight.score_skill.version, "4.4.0");
});

test("preflight rejects an installed scoring Skill version mismatch", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  const skillRoot = await scoreSkillFixture("3.2.0");
  await assert.rejects(
    () => passPreflight(root, { scoreSkillDir: skillRoot }),
    /评分 Skill 版本不一致/,
  );
});

test("preflight rejects a Desktop version change and unsupported metric profile", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  const skillRoot = await scoreSkillFixture("4.4.0", ["web-e2e-detailed-v1"]);
  await assert.rejects(() => preflight(root, {
    desktopVersion: "26.902.0",
    scoreSkillDir: skillRoot,
  }), /Desktop 版本.*不一致/);
  await assert.rejects(() => preflight(root, {
    desktopVersion: "26.901.51231",
    scoreSkillDir: skillRoot,
  }), /不支持 metric_profile/);
});

test("recordThread is blocked until the current task passes preflight", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await assert.rejects(() => recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" }), /必须先通过.*preflight/);
});

test("score_slots one prevents a second active scoring thread", async () => {
  const root = await fixture(["task-1", "task-2"]);
  const { state } = await initialize(root, [], { scoreSlots: 1 });
  for (const task of state.tasks) {
    await registerTask(root, task);
  }
  const skillRoot = await scoreSkillFixture();
  await passPreflight(root, { taskId: "task-1", scoreSkillDir: skillRoot });
  await passPreflight(root, { taskId: "task-2", scoreSkillDir: skillRoot });
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await assert.rejects(() => recordThread(root, "task-2", { threadId: "thread-2", hostId: "local" }), /score_slots=1/);
});

test("preflight is isolated per task and an explicit task can start out of order", async () => {
  const root = await fixture(["task-1", "task-2"]);
  const { state } = await initialize(root);
  for (const task of state.tasks) await registerTask(root, task);
  const skillRoot = await scoreSkillFixture();
  const second = await passPreflight(root, { taskId: "task-2", scoreSkillDir: skillRoot });
  assert.equal(second.tasks[0].preflight.status, "PENDING");
  assert.equal(second.tasks[1].preflight.status, "PASSED");
  const first = await passPreflight(root, { taskId: "task-1", scoreSkillDir: skillRoot });
  assert.equal(first.tasks[0].preflight.status, "PASSED");
  assert.equal(first.tasks[1].preflight.status, "PASSED");
  assert.equal(first.preflight.task_id, "task-1");
  const started = await recordThread(root, "task-2", { threadId: "thread-2", hostId: "local" });
  assert.equal(started.tasks[1].phase, "SCORING");
});

test("three tasks can score concurrently while the fourth waits for a released slot", async () => {
  const root = await fixture(["task-1", "task-2", "task-3", "task-4"]);
  const { state } = await initialize(root, [], { scoreTimeoutSeconds: 60 });
  const skillRoot = await scoreSkillFixture();
  for (const task of state.tasks) {
    await registerTask(root, task);
    await passPreflight(root, { taskId: task.task_id, scoreSkillDir: skillRoot });
  }
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" }, { now: "2099-09-08T00:00:00.000Z" });
  await recordThread(root, "task-2", { threadId: "thread-2", hostId: "local" }, { now: "2099-09-08T00:00:10.000Z" });
  const three = await recordThread(root, "task-3", { threadId: "thread-3", hostId: "local" }, { now: "2099-09-08T00:00:20.000Z" });
  assert.equal(three.active_score_tasks.length, 3);
  assert.equal(three.available_score_slots, 0);
  assert.deepEqual(three.active_score_tasks.map((task) => task.scoring_port), [4173, 4174, 4175]);
  assert.deepEqual(three.active_score_tasks.map((task) => task.deadline_at), [
    "2099-09-08T00:01:00.000Z",
    "2099-09-08T00:01:10.000Z",
    "2099-09-08T00:01:20.000Z",
  ]);
  assert.deepEqual(three.recommended_actions.map((action) => action.type), [
    "WAIT_EXISTING_THREAD",
    "WAIT_EXISTING_THREAD",
    "WAIT_EXISTING_THREAD",
  ]);
  await assert.rejects(
    () => recordThread(root, "task-4", { threadId: "thread-4", hostId: "local" }),
    /score_slots=3/,
  );

  await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-task-1",
    waitStatus: "RUNNING",
  }, { now: "2099-09-08T00:00:30.000Z" });
  const cursors = await recordWait(root, "task-2", {
    waitSequence: 1,
    waitCursor: "cursor-task-2",
    waitStatus: "POLL_TIMEOUT",
  }, { now: "2099-09-08T00:00:31.000Z" });
  assert.equal(cursors.recommended_actions.find((action) => action.task_id === "task-1").after_cursor, "cursor-task-1");
  assert.equal(cursors.recommended_actions.find((action) => action.task_id === "task-1").next_wait_sequence, 2);
  assert.equal(cursors.recommended_actions.find((action) => action.task_id === "task-2").after_cursor, "cursor-task-2");
  assert.equal(cursors.recommended_actions.find((action) => action.task_id === "task-2").next_wait_sequence, 2);

  const paused = await recordWait(root, "task-2", {
    waitSequence: 2,
    waitCursor: "cursor-task-2-failed",
    waitStatus: "FAILED",
    waitError: "browser failed",
  }, { now: "2099-09-08T00:00:32.000Z" });
  assert.deepEqual(paused.recommended_actions.map((action) => action.type), [
    "PREPARE_RETRY",
    "WAIT_EXISTING_THREAD",
    "WAIT_EXISTING_THREAD",
  ]);
  assert.ok(!paused.recommended_actions.some((action) => action.task_id === "task-4"));
});

test("an out-of-order completion backfills the fourth task and builds submission once", async () => {
  const root = await fixture(["task-1", "task-2", "task-3", "task-4"]);
  const { state } = await initialize(root);
  const skillRoot = await scoreSkillFixture();
  for (const task of state.tasks) {
    await registerTask(root, task);
    await passPreflight(root, { taskId: task.task_id, scoreSkillDir: skillRoot });
  }
  for (const taskId of ["task-1", "task-2", "task-3"]) {
    await recordThread(root, taskId, { threadId: `thread-${taskId}`, hostId: "local" });
  }
  await recordCompletedWait(root, "task-2");
  await writeValidScore(root, "task-2");
  const released = await markComplete(root, "task-2");
  assert.equal(released.available_score_slots, 1);
  assert.ok(released.recommended_actions.some((action) => action.type === "CREATE_THREAD" && action.task_id === "task-4"));
  await recordThread(root, "task-4", { threadId: "thread-task-4", hostId: "local" });

  for (const taskId of ["task-4", "task-1", "task-3"]) {
    await recordCompletedWait(root, taskId);
    await writeValidScore(root, taskId);
    await markComplete(root, taskId);
  }
  const completed = await status(root);
  assert.equal(completed.phase, "COMPLETED");
  assert.equal(completed.submission.status, "COMPLETED");
  assert.equal(completed.submission.attempt_count, 1);
  assert.deepEqual(completed.tasks.map((task) => task.phase), ["COMPLETED", "COMPLETED", "COMPLETED", "COMPLETED"]);
  const repeated = await markComplete(root, "task-2");
  assert.equal(repeated.submission.attempt_count, 1);
});

test("recordThread rejects reused thread IDs and duplicate active scoring ports", async () => {
  const root = await fixture(["task-1", "task-2", "task-3"]);
  const { state } = await initialize(root);
  const skillRoot = await scoreSkillFixture();
  for (const task of state.tasks) {
    await registerTask(root, task);
    await passPreflight(root, { taskId: task.task_id, scoreSkillDir: skillRoot });
  }
  await recordThread(root, "task-1", { threadId: "shared-thread", hostId: "local" });
  await assert.rejects(
    () => recordThread(root, "task-2", { threadId: "shared-thread", hostId: "local" }),
    /threadId 已被其他任务使用/,
  );

  const stateFile = join(root, "score", ".orchestrate-web-e2e", "scoring-automation-state.json");
  const persisted = JSON.parse(await readFile(stateFile, "utf8"));
  persisted.tasks[1].scoring_port = persisted.tasks[0].scoring_port;
  await writeJson(stateFile, persisted);
  await assert.rejects(
    () => recordThread(root, "task-2", { threadId: "thread-2", hostId: "local" }),
    /评分端口 4173 已被活动任务占用/,
  );
});

test("markComplete does not release a slot while runtime-workspace remains", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordCompletedWait(root, "task-1");
  await writeValidScore(root, "task-1");
  const privateRoot = join(root, "score", "tasks", "task-1", "private-scoring");
  await writeJson(join(privateRoot, "runtime-state.json"), {
    schema_version: "wildclawbench.web-e2e-scoring-runtime/v1",
    task_id: "task-1",
    candidate_sha256: state.tasks[0].candidate_integrity.expected_sha256,
    service: { status: "RUNNING" },
  });
  await assert.rejects(() => markComplete(root, "task-1"), /评分服务未进入可信终态/);
  await writeJson(join(privateRoot, "runtime-state.json"), {
    schema_version: "wildclawbench.web-e2e-scoring-runtime/v1",
    task_id: "task-1",
    candidate_sha256: state.tasks[0].candidate_integrity.expected_sha256,
    service: { status: "STOPPED" },
  });
  await mkdir(join(privateRoot, "runtime-workspace"), { recursive: true });
  await assert.rejects(() => markComplete(root, "task-1"), /运行时副本尚未清理.*禁止释放槽位/);
  assert.equal((await status(root)).tasks[0].phase, "SCORING");
  await rm(join(privateRoot, "runtime-workspace"), { recursive: true });
  await writeJson(join(privateRoot, "screenshot-receiver-state.json"), {
    schema_version: "wildclawbench.web-e2e-screenshot-receiver/v1",
    task_id: "task-1",
    candidate_sha256: state.tasks[0].candidate_integrity.expected_sha256,
    status: "RUNNING",
  });
  await assert.rejects(() => markComplete(root, "task-1"), /截图接收器未进入可信终态/);
  await writeJson(join(privateRoot, "screenshot-receiver-state.json"), {
    schema_version: "wildclawbench.web-e2e-screenshot-receiver/v1",
    task_id: "task-1",
    candidate_sha256: state.tasks[0].candidate_integrity.expected_sha256,
    status: "COMPLETED",
  });
  const completed = await markComplete(root, "task-1");
  assert.equal(completed.phase, "COMPLETED");
});

test("revision 3 state resumes with one slot and preserves its legacy prompt", async () => {
  const root = await fixture(["task-1", "task-2"]);
  const { state } = await initialize(root, [], { scoreSlots: 1 });
  const stateFile = join(root, "score", ".orchestrate-web-e2e", "scoring-automation-state.json");
  const legacy = JSON.parse(await readFile(stateFile, "utf8"));
  legacy.schema_revision = 3;
  delete legacy.score_port_base;
  for (const task of legacy.tasks) {
    delete task.scoring_port;
    delete task.scoring_prompt_port_bound;
    delete task.preflight;
    const prompt = (await readFile(task.scoring_prompt_file, "utf8"))
      .split("\n")
      .filter((line) => !line.includes("独占本地评分端口"))
      .join("\n");
    await writeFile(task.scoring_prompt_file, prompt, "utf8");
    task.scoring_prompt_sha256 = createHash("sha256").update(prompt).digest("hex");
  }
  await writeJson(stateFile, legacy);

  const resumed = await resume(root);
  assert.equal(resumed.score_slots, 1);
  assert.deepEqual(resumed.tasks.map((task) => task.scoring_port), [4173, 4173]);
  assert.ok(resumed.tasks.every((task) => task.preflight.status === "PENDING"));
  const reinitialized = await initialize(root);
  assert.equal(reinitialized.state.score_slots, 1);
  assert.doesNotMatch(await readFile(state.tasks[0].scoring_prompt_file, "utf8"), /独占本地评分端口/);
  await assert.rejects(() => initialize(root, [], { scoreSlots: 3 }), /score_slots 不可变/);
});

test("valid task score completes one task and advances to the next", async () => {
  const root = await fixture(["task-1", "task-2"]);
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordCompletedWait(root, "task-1");
  await writeValidScore(root, "task-1");
  const result = await markComplete(root, "task-1");
  assert.equal(result.tasks[0].phase, "COMPLETED");
  assert.equal(result.next_task.task_id, "task-2");
  assert.equal((await status(root)).phase, "PREPARED");
});

test("invalid execution receipt blocks scoring initialization", async () => {
  const root = await fixture();
  const receipt = JSON.parse(await readFile(join(root, "execution-receipt.json"), "utf8"));
  receipt.integrity.valid = false;
  await writeJson(join(root, "execution-receipt.json"), receipt);
  await assert.rejects(() => initialize(root), /integrity.valid/);
});

test("preflight rejects execution workspace drift and persists the failure", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await writeFile(join(root, "execution", "tasks", "task-1", "workspace", "index.html"), "drift", "utf8");
  await assert.rejects(() => passPreflight(root), /候选产物发生漂移/);
  const current = await status(root);
  assert.equal(current.phase, "NEEDS_ATTENTION");
  assert.equal(current.tasks[0].phase, "FAILED");
  assert.equal(current.preflight.status, "FAILED");
});

test("preflight rejects any execution receipt rewrite after candidate lock creation", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  const receiptFile = join(root, "execution-receipt.json");
  const receipt = JSON.parse(await readFile(receiptFile, "utf8"));
  receipt.rewritten_after_freeze = true;
  await writeJson(receiptFile, receipt);
  await assert.rejects(() => passPreflight(root), /candidate_artifact\.json 与执行回执不一致/);
  const current = await status(root);
  assert.equal(current.phase, "NEEDS_ATTENTION");
  assert.equal(current.tasks[0].phase, "FAILED");
});

test("markComplete rejects score workspace changes", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordCompletedWait(root, "task-1");
  await writeValidScore(root, "task-1");
  await writeFile(join(root, "score", "tasks", "task-1", "workspace", "index.html"), "modified by scorer", "utf8");
  await assert.rejects(() => markComplete(root, "task-1"), /候选产物发生漂移/);
  assert.equal((await status(root)).tasks[0].phase, "FAILED");
});

test("wait cursor survives a control restart and duplicate observations are idempotent", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-1",
    waitStatus: "RUNNING",
  });
  const restarted = await resume(root);
  assert.equal(restarted.recommended_action.type, "WAIT_EXISTING_THREAD");
  assert.equal(restarted.recommended_action.thread_id, "thread-1");
  assert.equal(restarted.recommended_action.after_cursor, "cursor-1");
  assert.equal(restarted.recommended_action.next_wait_sequence, 2);
  const duplicate = await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-1",
    waitStatus: "RUNNING",
  });
  assert.equal(duplicate.tasks[0].attempts[0].wait_count, 1);
  await assert.rejects(() => recordWait(root, "task-1", {
    waitSequence: 3,
    waitCursor: "cursor-3",
    waitStatus: "POLL_TIMEOUT",
  }), /waitSequence 应为 2/);
});

test("poll timeout is distinct from scoring deadline timeout", async () => {
  const root = await fixture();
  const { state } = await initialize(root, [], { scoreTimeoutSeconds: 60 });
  await registerTask(root, state.tasks[0]);
  const skillRoot = await scoreSkillFixture();
  await passPreflight(root, { scoreSkillDir: skillRoot });
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" }, { now: "2026-09-07T00:00:00.000Z" });
  const polling = await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-1",
    waitStatus: "POLL_TIMEOUT",
  }, { now: "2026-09-07T00:00:30.000Z" });
  assert.equal(polling.tasks[0].phase, "SCORING");
  const timedOut = await markTimeout(root, "task-1", { now: "2026-09-07T00:01:01.000Z" });
  assert.equal(timedOut.tasks[0].phase, "TIMED_OUT");
  assert.equal(timedOut.recommended_action.type, "WAIT_FOR_TIMED_OUT_THREAD_TERMINAL");
  await assert.rejects(() => prepareRetry(root, "task-1", "deadline test"), /终态尚未确认/);
  await recordWait(root, "task-1", {
    waitSequence: 2,
    waitCursor: "cursor-2",
    waitStatus: "INTERRUPTED",
    waitError: "test interruption",
  }, { now: "2026-09-07T00:01:02.000Z" });
  const retry = await prepareRetry(root, "task-1", "deadline test");
  assert.equal(retry.tasks[0].retry_count, 1);
  assert.equal(retry.tasks[0].phase, "PROJECT_REGISTERED");
  assert.equal(retry.recommended_action.type, "RUN_PREFLIGHT");
  await passPreflight(root, { scoreSkillDir: skillRoot });
  const second = await recordThread(root, "task-1", { threadId: "thread-2", hostId: "local" });
  assert.equal(second.tasks[0].attempts.length, 2);
  assert.equal(second.tasks[0].attempts[1].attempt_number, 2);
  assert.equal(second.tasks[0].thread_id, "thread-2");
});

test("failed attempts archive partial scoring outputs and emit a structured error receipt", async () => {
  const root = await fixture();
  const preparedPrivateRoot = join(root, "score", "tasks", "task-1", "private-scoring");
  await mkdir(join(preparedPrivateRoot, "fixtures"), { recursive: true });
  await writeFile(join(preparedPrivateRoot, "fixtures", "expected-layout.json"), "{}\n", "utf8");
  const { state } = await initialize(root);
  const originalWorkspace = snapshotWorkspace(join(root, "score", "tasks", "task-1", "workspace")).sha256;
  await registerTask(root, state.tasks[0]);
  const skillRoot = await scoreSkillFixture();
  await passPreflight(root, { scoreSkillDir: skillRoot });
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-failed",
    waitStatus: "FAILED",
    waitError: "browser crashed",
  });

  const privateRoot = join(root, "score", "tasks", "task-1", "private-scoring");
  await writeJson(join(privateRoot, "score_input.json"), { partial: true });
  await writeJson(join(privateRoot, "task_score.json"), { incomplete: true });
  await mkdir(join(privateRoot, "runtime-workspace"), { recursive: true });
  await writeFile(join(privateRoot, "runtime-workspace", "generated.txt"), "runtime copy", "utf8");
  await writeJson(join(privateRoot, "runtime-state.json"), {
    schema_version: "wildclawbench.web-e2e-scoring-runtime/v1",
    task_id: "task-1",
    candidate_sha256: state.tasks[0].candidate_integrity.expected_sha256,
    service: { status: "STOPPED" },
  });
  await mkdir(join(privateRoot, "evidence"), { recursive: true });
  await writeFile(join(privateRoot, "evidence", "partial.md"), "partial browser evidence", "utf8");

  const retry = await prepareRetry(root, "task-1", "retry after browser crash");
  const archivedAttempt = retry.tasks[0].attempts[0];
  assert.equal(retry.tasks[0].phase, "PROJECT_REGISTERED");
  assert.equal(retry.tasks[0].retry_count, 1);
  assert.equal(archivedAttempt.error_receipt.schema_version, "wildclawbench.web-e2e-scoring-attempt-error/v1");
  assert.match(archivedAttempt.error_receipt.sha256, /^[a-f0-9]{64}$/);
  const receipt = JSON.parse(await readFile(join(root, archivedAttempt.error_receipt.path), "utf8"));
  assert.equal(receipt.attempt.terminal_status, "FAILED");
  assert.equal(receipt.attempt.wait_cursor, "cursor-failed");
  assert.equal(receipt.retry.next_attempt_number, 2);
  assert.equal(receipt.failure.task_error, "browser crashed");
  assert.ok(receipt.archive.entries.some((entry) => entry.path === "score_input.json"));
  assert.ok(receipt.archive.entries.some((entry) => entry.path === "task_score.json"));
  assert.ok(receipt.archive.entries.some((entry) => entry.path === "runtime-workspace/generated.txt"));
  assert.ok(receipt.archive.entries.some((entry) => entry.path === "fixtures/expected-layout.json"));
  assert.deepEqual((await readdir(privateRoot)).sort(), ["candidate_artifact.json", "fixtures", "task_contract.json"]);
  assert.equal(await readFile(join(privateRoot, "fixtures", "expected-layout.json"), "utf8"), "{}\n");
  assert.equal(snapshotWorkspace(join(root, "score", "tasks", "task-1", "workspace")).sha256, originalWorkspace);

  await passPreflight(root, { scoreSkillDir: skillRoot });
  const second = await recordThread(root, "task-1", { threadId: "thread-2", hostId: "local" });
  assert.equal(second.tasks[0].attempts.length, 2);
  assert.equal(second.tasks[0].attempts[1].attempt_number, 2);
});

test("prepareRetry refuses to archive active scoring runtimes", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-failed",
    waitStatus: "FAILED",
    waitError: "failed while runtimes were active",
  });
  const privateRoot = join(root, "score", "tasks", "task-1", "private-scoring");
  const candidateSha256 = state.tasks[0].candidate_integrity.expected_sha256;
  await mkdir(join(privateRoot, "runtime-workspace"), { recursive: true });
  await writeJson(join(privateRoot, "runtime-state.json"), {
    schema_version: "wildclawbench.web-e2e-scoring-runtime/v1",
    task_id: "task-1",
    candidate_sha256: candidateSha256,
    service: { status: "RUNNING" },
  });
  await assert.rejects(
    () => prepareRetry(root, "task-1", "active runtime test"),
    /评分服务未进入可信终态/,
  );

  await writeJson(join(privateRoot, "runtime-state.json"), {
    schema_version: "wildclawbench.web-e2e-scoring-runtime/v1",
    task_id: "task-1",
    candidate_sha256: candidateSha256,
    service: { status: "STOPPED" },
  });
  await writeJson(join(privateRoot, "screenshot-receiver-state.json"), {
    schema_version: "wildclawbench.web-e2e-screenshot-receiver/v1",
    task_id: "task-1",
    candidate_sha256: candidateSha256,
    status: "RUNNING",
  });
  await assert.rejects(
    () => prepareRetry(root, "task-1", "active runtime test"),
    /截图接收器未进入可信终态/,
  );

  await writeJson(join(privateRoot, "screenshot-receiver-state.json"), {
    schema_version: "wildclawbench.web-e2e-screenshot-receiver/v1",
    task_id: "task-1",
    candidate_sha256: candidateSha256,
    status: "STOPPED",
  });
  const retry = await prepareRetry(root, "task-1", "active runtime test");
  assert.equal(retry.tasks[0].phase, "PROJECT_REGISTERED");
  assert.equal(retry.tasks[0].attempts[0].error_receipt.schema_version, "wildclawbench.web-e2e-scoring-attempt-error/v1");
});

test("prepareRetry refuses a runtime workspace without managed state", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-failed",
    waitStatus: "FAILED",
  });
  const privateRoot = join(root, "score", "tasks", "task-1", "private-scoring");
  await mkdir(join(privateRoot, "runtime-workspace"), { recursive: true });
  await assert.rejects(
    () => prepareRetry(root, "task-1", "missing runtime state test"),
    /缺少 runtime-state\.json/,
  );
});

test("prepareRetry resumes an interrupted attempt archive from its journal", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-interrupted",
    waitStatus: "INTERRUPTED",
    waitError: "desktop exited",
  });
  const privateRoot = join(root, "score", "tasks", "task-1", "private-scoring");
  await writeJson(join(privateRoot, "score_input.json"), { partial: true });

  await assert.rejects(
    () => prepareRetry(root, "task-1", "resume archive", { failAfterArchiveMove: true }),
    /故障注入/,
  );
  const recovered = await prepareRetry(root, "task-1", "resume archive");
  assert.equal(recovered.tasks[0].phase, "PROJECT_REGISTERED");
  assert.equal(recovered.tasks[0].attempts[0].error_receipt.schema_version, "wildclawbench.web-e2e-scoring-attempt-error/v1");
  assert.deepEqual((await readdir(privateRoot)).sort(), ["candidate_artifact.json", "task_contract.json"]);
  const pendingRoot = join(root, "score", ".orchestrate-web-e2e", "pending-attempt-archives");
  assert.deepEqual(await readdir(pendingRoot), []);
});

test("preflight rejects drift in an archived failed attempt", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  const skillRoot = await scoreSkillFixture();
  await passPreflight(root, { scoreSkillDir: skillRoot });
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordWait(root, "task-1", {
    waitSequence: 1,
    waitCursor: "cursor-failed",
    waitStatus: "FAILED",
    waitError: "failed attempt",
  });
  const privateRoot = join(root, "score", "tasks", "task-1", "private-scoring");
  await writeJson(join(privateRoot, "score_input.json"), { partial: true });
  const retry = await prepareRetry(root, "task-1", "archive integrity test");
  const archiveRoot = join(root, retry.tasks[0].attempts[0].error_receipt.archive_root, "private-scoring");
  await writeJson(join(archiveRoot, "score_input.json"), { tampered: true });
  await assert.rejects(
    () => passPreflight(root, { scoreSkillDir: skillRoot }),
    /评分 attempt 归档发生漂移/,
  );
});

test("a completed final score atomically builds submission exactly once", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordCompletedWait(root, "task-1");
  await writeValidScore(root, "task-1");
  const completed = await markComplete(root, "task-1");
  assert.equal(completed.phase, "COMPLETED");
  assert.equal(completed.submission.status, "COMPLETED");
  assert.match(completed.submission.sha256, /^[a-f0-9]{64}$/);
  assert.equal(completed.submission.attempt_count, 1);
  const originalSha = completed.submission.sha256;
  const repeated = await buildSubmissionControl(root);
  assert.equal(repeated.submission.sha256, originalSha);
  assert.equal(repeated.submission.attempt_count, 1);
  const submission = JSON.parse(await readFile(join(root, "submission.json"), "utf8"));
  assert.equal(submission.batch_id, "batch-1");
  assert.deepEqual(submission.task_ids, ["task-1"]);
});

test("a completed submission is fail-closed after file drift", async () => {
  const root = await fixture();
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await recordCompletedWait(root, "task-1");
  await writeValidScore(root, "task-1");
  await markComplete(root, "task-1");
  await writeFile(join(root, "submission.json"), "{}\n", "utf8");
  await assert.rejects(() => buildSubmissionControl(root), /发生漂移/);
  const current = await status(root);
  assert.equal(current.phase, "NEEDS_ATTENTION");
  assert.equal(current.submission.status, "FAILED");
});
