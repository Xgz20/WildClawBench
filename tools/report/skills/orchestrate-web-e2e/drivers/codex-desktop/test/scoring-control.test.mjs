import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, realpath, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import { CANDIDATE_ARTIFACT_SCHEMA, TREE_HASH_ALGORITHM, snapshotWorkspace } from "../../../scripts/workspace-integrity.mjs";

import {
  initialize,
  markComplete,
  preflight,
  recordProject,
  recordThread,
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
      version: "4.3.0",
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

async function scoreSkillFixture(version = "4.3.0", profiles = ["web-e2e-detailed-v1", "artifactsbench-web-v1"]) {
  const root = await mkdtemp(join(tmpdir(), "score-web-e2e-skill-"));
  await writeJson(join(root, "skill-metadata.json"), {
    schema_version: "wildclawbench.web-e2e-score-skill/v1",
    name: "score-web-e2e",
    version,
    supported_metric_profiles: profiles,
    task_score_schema: "wildclawbench.web-e2e-task-score/v1",
  });
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

test("init creates immutable serial state and scoring prompts", async () => {
  const root = await fixture(["task-1", "task-2"]);
  const { state } = await initialize(root, ["task-2", "task-1"]);
  assert.equal(state.score_slots, 1);
  assert.deepEqual(state.tasks.map((task) => task.task_id), ["task-2", "task-1"]);
  assert.match(await readFile(state.tasks[0].scoring_prompt_file, "utf8"), /\$score-web-e2e/);
  await assert.rejects(() => initialize(root, ["task-1", "task-2"]), /任务范围或顺序不可变/);
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
  assert.equal(result.preflight.score_skill.version, "4.3.0");
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
  const skillRoot = await scoreSkillFixture("4.3.0", ["web-e2e-detailed-v1"]);
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
  const { state } = await initialize(root);
  for (const task of state.tasks) {
    await registerTask(root, task);
  }
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
  await assert.rejects(() => recordThread(root, "task-2", { threadId: "thread-2", hostId: "local" }), /score_slots=1|只能为下一题/);
});

test("valid task score completes one task and advances to the next", async () => {
  const root = await fixture(["task-1", "task-2"]);
  const { state } = await initialize(root);
  await registerTask(root, state.tasks[0]);
  await passPreflight(root);
  await recordThread(root, "task-1", { threadId: "thread-1", hostId: "local" });
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
  await writeValidScore(root, "task-1");
  await writeFile(join(root, "score", "tasks", "task-1", "workspace", "index.html"), "modified by scorer", "utf8");
  await assert.rejects(() => markComplete(root, "task-1"), /候选产物发生漂移/);
  assert.equal((await status(root)).tasks[0].phase, "FAILED");
});
