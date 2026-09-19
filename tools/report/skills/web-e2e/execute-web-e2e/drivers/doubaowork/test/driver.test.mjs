import assert from "node:assert/strict";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  acquireExclusiveWorkerLock,
  assertPreSendRetryEligible,
  canonicalEditorBlockText,
  classifyDevelopmentObservation,
  selectConfigurationReadback,
  selectWorkspaceReadbackCandidate,
  validateOutputDirectory,
  validatePreparedTaskRoot,
} from "../driver.mjs";
import {
  confirmWorkspaceReadback,
  createAttemptState,
  transitionAttempt,
} from "../state.mjs";

async function createPreparedTask(root) {
  const harnessRoot = join(root, "harness");
  const taskId = "07_Website_Generation_task_fixture";
  const taskRoot = join(harnessRoot, "execution", "tasks", taskId);
  await mkdir(join(taskRoot, "workspace"), { recursive: true });
  await writeFile(join(taskRoot, "PROMPT.md"), "Build the fixture site.\n", "utf8");
  await writeFile(join(taskRoot, "workspace", ".gitkeep"), "", "utf8");
  await writeFile(join(harnessRoot, "manifest.json"), `${JSON.stringify({
    schema_version: "wildclawbench.web-e2e-batch/v3",
    batch_id: "web-e2e-fixture",
    harness: { id: "doubaowork", display_name: "DoubaoWork" },
    tasks: [{
      task_id: taskId,
      task_name: "Fixture",
      difficulty: "L1",
      execution_dir: `execution/tasks/${taskId}`,
      prompt_file: `execution/tasks/${taskId}/PROMPT.md`,
      task_sha256: "a".repeat(64),
    }],
  }, null, 2)}\n`, "utf8");
  return { harnessRoot, taskId, taskRoot };
}

test("prepared task root 只接受 v3 DoubaoWork manifest 的精确单题映射", async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-driver-task-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const { harnessRoot, taskId, taskRoot } = await createPreparedTask(root);

  const prepared = await validatePreparedTaskRoot(taskRoot);
  assert.equal(prepared.batchId, "web-e2e-fixture");
  assert.equal(prepared.taskId, taskId);
  assert.equal(prepared.workspace, taskRoot);
  assert.equal(prepared.candidateWorkspace, join(taskRoot, "workspace"));
  assert.equal(prepared.prompt, "Build the fixture site.\n");
  assert.match(prepared.promptSha256, /^[0-9a-f]{64}$/);

  await assert.rejects(() => validatePreparedTaskRoot(), /--task-root 必填/);
  await assert.rejects(() => validatePreparedTaskRoot("relative/task"), /绝对路径/);

  const manifestPath = join(harnessRoot, "manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  manifest.schema_version = "wildclawbench.web-e2e-batch/v2";
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  await assert.rejects(() => validatePreparedTaskRoot(taskRoot), /schema_version 不受支持/);
});

test("prepared workspace 的私有评分目录失败关闭", async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-driver-private-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const { taskRoot } = await createPreparedTask(root);
  await mkdir(join(taskRoot, "workspace", "private-scoring"));
  await assert.rejects(() => validatePreparedTaskRoot(taskRoot), /禁止目录/);
});

test("自动化输出目录拒绝 task root 本身、其子目录和相对路径", async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-driver-output-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const { taskRoot } = await createPreparedTask(root);
  assert.throws(() => validateOutputDirectory(taskRoot, taskRoot), /单题目录外/);
  assert.throws(() => validateOutputDirectory(taskRoot, join(taskRoot, "debug")), /单题目录外/);
  assert.throws(() => validateOutputDirectory(taskRoot, "relative-output"), /绝对路径/);
  assert.equal(validateOutputDirectory(taskRoot, join(root, "debug")), join(root, "debug"));
});

test("目录 tooltip 只接受完整绝对路径或开头 ~/ 的严格等价回读", () => {
  const expected = "/Users/fixture/debug/task-root";
  assert.equal(selectWorkspaceReadbackCandidate([
    "task-root",
    "主要",
    "~/debug/task-root",
  ], expected, "/Users/fixture"), "~/debug/task-root");
  assert.equal(selectWorkspaceReadbackCandidate([
    "task-root",
    "/Users/fixture/debug/other-task-root",
  ], expected, "/Users/fixture"), null);
});

test("富文本 Prompt 回读保留内部空行并仅移除尾部空段", () => {
  assert.equal(
    canonicalEditorBlockText(["第一段", "", "第二段", ""]),
    "第一段\n\n第二段",
  );
  assert.equal(canonicalEditorBlockText(["第一段", "第二段"]), "第一段\n第二段");
});

test("开发终态分类始终保持非可信并对 pending 失败关闭", () => {
  assert.deepEqual(classifyDevelopmentObservation({
    visible_error_count: 1,
    user_question_count: 0,
    visible_dialog_count: 0,
    approval_count: 0,
    stop_control_count: 0,
    final_assistant_bytes: 0,
    final_reply_action_count: 0,
  }), { kind: "failure-candidate", trusted: false });
  assert.deepEqual(classifyDevelopmentObservation({
    visible_error_count: 0,
    user_question_count: 0,
    visible_dialog_count: 0,
    approval_count: 1,
    stop_control_count: 0,
    final_assistant_bytes: 0,
    final_reply_action_count: 0,
  }), { kind: "needs-attention", trusted: false });
  assert.deepEqual(classifyDevelopmentObservation({
    visible_error_count: 0,
    user_question_count: 0,
    visible_dialog_count: 0,
    approval_count: 0,
    stop_control_count: 0,
    final_assistant_bytes: 42,
    final_reply_action_count: 2,
  }), { kind: "ui-completion-candidate", trusted: false });
  assert.deepEqual(classifyDevelopmentObservation({
    visible_error_count: 0,
    user_question_count: 0,
    visible_dialog_count: 0,
    approval_count: 0,
    stop_control_count: 0,
    busy_conversation_count: 1,
    final_assistant_bytes: 42,
    final_reply_action_count: 2,
  }), { kind: "running", trusted: false });
});

test("配置回读要求本地电脑、项目、权限和非空模型各自唯一", () => {
  const controls = [
    { visible: true, text: "本地电脑", title: null, aria_label: null, testid: "mode" },
    { visible: true, text: "Fixture", title: "WCB-Fixture", aria_label: "WCB-Fixture", testid: "project" },
    { visible: true, text: "按需确认", title: "按需确认", aria_label: "按需确认", testid: "permission" },
    { visible: true, text: "自动 高", title: null, aria_label: null, testid: null },
  ];
  assert.deepEqual(selectConfigurationReadback(controls, "WCB-Fixture"), {
    permission: "按需确认",
    model: "自动 高",
  });
  assert.throws(
    () => selectConfigurationReadback([
      ...controls,
      { visible: true, text: "另一个模型", title: null, aria_label: null, testid: null },
    ], "WCB-Fixture"),
    /唯一回读当前非空模型/,
  );
  assert.throws(
    () => selectConfigurationReadback([
      ...controls,
      { visible: true, text: "每次询问", title: "每次询问", aria_label: "每次询问", testid: "permission-2" },
    ], "WCB-Fixture"),
    /唯一回读当前权限/,
  );
});

test("发送前重试只接受 workspace 已确认且 dispatch 为零的失败 attempt", () => {
  const state = createAttemptState({
    attemptId: "pre-send-retry-fixture",
    batchId: "batch-fixture",
    taskId: "task-fixture",
    workspace: "/Users/fixture/debug/task-root",
    promptFile: "/Users/fixture/debug/task-root/PROMPT.md",
    prompt: "fixture prompt",
    now: "2026-09-19T00:00:00.000Z",
  });
  transitionAttempt(state, "CLIENT_READY", {}, "2026-09-19T00:00:01.000Z");
  confirmWorkspaceReadback(
    state,
    "~/debug/task-root",
    "/Users/fixture",
    "2026-09-19T00:00:02.000Z",
  );
  transitionAttempt(state, "INFRA_FAILED", {}, "2026-09-19T00:00:03.000Z");
  state.error = { code: "DEVELOPMENT_PRE_SEND_FAILED", message: "fixture", at: "2026-09-19T00:00:03.000Z" };
  state.client.project_id_sha256 = "a".repeat(64);
  assert.equal(assertPreSendRetryEligible(state), state);

  const unsafe = structuredClone(state);
  unsafe.send.intent_persisted_at = "2026-09-19T00:00:04.000Z";
  assert.throws(() => assertPreSendRetryEligible(unsafe), /只允许/);
  const mismatched = structuredClone(state);
  mismatched.workspace_selection.actual_path = "/Users/fixture/debug/other";
  assert.throws(() => assertPreSendRetryEligible(mismatched), /只允许/);
  const missingProjectId = structuredClone(state);
  missingProjectId.client.project_id_sha256 = null;
  assert.throws(() => assertPreSendRetryEligible(missingProjectId), /只允许/);
});

test("排他 worker lock 记录 host PID start identity 并拒绝第二个活 worker", async (context) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "doubaowork-driver-lock-")));
  context.after(() => rm(root, { recursive: true, force: true }));
  const release = await acquireExclusiveWorkerLock(root);
  const lockPath = join(root, ".doubaowork-driver.lock");
  const record = JSON.parse(await readFile(lockPath, "utf8"));
  assert.equal(record.schema, "wildclawbench.doubaowork-worker-lock/v1");
  assert.equal(record.pid, process.pid);
  assert.equal(typeof record.host, "string");
  assert.ok(record.host);
  assert.equal(typeof record.process_start_identity, "string");
  assert.ok(record.process_start_identity);
  await assert.rejects(() => acquireExclusiveWorkerLock(root), /仍存活/);
  await release();
  await assert.rejects(() => access(lockPath));
});

test("两个并发 worker 只能有一个获得 no-clobber lock", async (context) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "doubaowork-driver-lock-race-")));
  context.after(() => rm(root, { recursive: true, force: true }));
  const attempts = await Promise.allSettled([
    acquireExclusiveWorkerLock(root),
    acquireExclusiveWorkerLock(root),
  ]);
  const winners = attempts.filter((item) => item.status === "fulfilled");
  const losers = attempts.filter((item) => item.status === "rejected");
  assert.equal(winners.length, 1);
  assert.equal(losers.length, 1);
  await winners[0].value();
});

test("两个 stale reclaimer 都失败关闭且不会删除旧 lock 或抢占发送", async (context) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "doubaowork-driver-stale-lock-race-")));
  context.after(() => rm(root, { recursive: true, force: true }));
  const lockPath = join(root, ".doubaowork-driver.lock");
  const stale = {
    schema: "wildclawbench.doubaowork-worker-lock/v1",
    host: hostname(),
    pid: process.pid,
    process_start_identity: "stale-process-start-identity",
    instance_id: "stale-instance",
    acquired_at: "2026-09-19T00:00:00.000Z",
  };
  await writeFile(lockPath, `${JSON.stringify(stale, null, 2)}\n`, "utf8");
  const attempts = await Promise.allSettled([
    acquireExclusiveWorkerLock(root),
    acquireExclusiveWorkerLock(root),
  ]);
  assert.equal(attempts.filter((item) => item.status === "fulfilled").length, 0);
  assert.equal(attempts.filter((item) => item.status === "rejected").length, 2);
  assert.deepEqual(JSON.parse(await readFile(lockPath, "utf8")), stale);
});

test("worker lock 在创建、读取前拒绝 outputDir 任一祖先符号链接", async (context) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "doubaowork-driver-lock-symlink-")));
  context.after(() => rm(root, { recursive: true, force: true }));
  const realOutputParent = join(root, "real-output-parent");
  const linkedOutputParent = join(root, "linked-output-parent");
  await mkdir(realOutputParent);
  await symlink(realOutputParent, linkedOutputParent);
  const outputDir = join(linkedOutputParent, "run-01");
  await assert.rejects(() => acquireExclusiveWorkerLock(outputDir), /目录链禁止符号链接/);
  await assert.rejects(() => access(join(realOutputParent, "run-01")));
});
