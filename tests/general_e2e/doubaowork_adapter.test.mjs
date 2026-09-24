import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, writeFile, rm, symlink, realpath } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { validateGeneralTask, validateGeneralResume } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/doubaowork/prepared-task.mjs";
import { inspectGuiSession } from "../../tools/report/e2e-shared/doubaowork/platform.mjs";
import { isKnownInformationalDialog, assertNoConflictingActivity, canAcceptNativeCompletion, selectComposerProjectControl } from "../../tools/report/e2e-shared/doubaowork/controller.mjs";
import { assertNativeActivityAllowed } from "../../tools/report/e2e-shared/doubaowork/runtime-activity.mjs";

async function fixture(t) {
  const root = await realpath(await mkdtemp(join(tmpdir(), "doubao-general-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const taskId = "02_Code_Intelligence_task_fixture", prefix = `execution/tasks/${taskId}`;
  await mkdir(join(root, prefix, "workspace", ".git"), { recursive: true });
  const prompt = "Fixture prompt\n";
  await writeFile(join(root, prefix, "PROMPT.md"), prompt);
  const manifest = {
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1", manifest_kind: "execution",
    batch_id: "fixture", dataset: { id: "fixture", digest: "a".repeat(64) },
    unit: { unit_id: "doubao", harness: { id: "doubaowork", platform: "macos-x86-64", version: "2.31.3" }, model: { requested_id: "自动 高" } },
    tasks: [{ task_id: taskId, prompt: { path: `${prefix}/PROMPT.md`, sent_sha256: createHash("sha256").update(prompt).digest("hex") }, workspace: { path: `${prefix}/workspace` } }],
  };
  const save = () => writeFile(join(root, "manifest.json"), JSON.stringify(manifest));
  await save();
  return { root, taskId, manifest, save, options: { unitRoot: root, taskId } };
}

test("General adapter preserves exact prepared identity and permits General Git materials", async t => {
  const f = await fixture(t), c = await validateGeneralTask(f.options);
  assert.equal(c.scene, "general");
  assert.equal(c.workspace, join(f.root, "execution/tasks", f.taskId, "workspace"));
  assert.equal(c.frozenIdentity.unit_id, "doubao");
  assert.equal(c.expectedAppVersion, "2.31.3");
});

test("General rejects Web/scoring packages, duplicate tasks and Prompt drift", async t => {
  const f = await fixture(t);
  f.manifest.manifest_kind = "scoring"; await f.save();
  await assert.rejects(validateGeneralTask(f.options), /MANIFEST_INVALID/);
  f.manifest.manifest_kind = "execution"; f.manifest.tasks.push(f.manifest.tasks[0]); await f.save();
  await assert.rejects(validateGeneralTask(f.options), /TASK_AMBIGUOUS/);
  f.manifest.tasks.pop(); f.manifest.tasks[0].prompt.sent_sha256 = "b".repeat(64); await f.save();
  await assert.rejects(validateGeneralTask(f.options), /PROMPT_DRIFT/);
});

test("General rejects traversal, same basename outside task and symlink ancestors", async t => {
  const f = await fixture(t), task = f.manifest.tasks[0], original = task.prompt.path;
  task.prompt.path = "../PROMPT.md"; await f.save();
  await assert.rejects(validateGeneralTask(f.options), /MEMBER_UNSAFE/);
  task.prompt.path = "execution/tasks/other/PROMPT.md"; await f.save();
  await assert.rejects(validateGeneralTask(f.options), /OUTSIDE_TASK/);
  task.prompt.path = original; await f.save();
  const alias = join(f.root, "alias"); await symlink(join(f.root, "execution"), alias);
  task.prompt.path = `alias/tasks/${f.taskId}/PROMPT.md`; await f.save();
  await assert.rejects(validateGeneralTask(f.options), /OUTSIDE_TASK/);
  await assert.rejects(validateGeneralTask({ ...f.options, unitRoot: alias }), /PATH_UNSAFE/);
});

test("General resume rejects cross-scene and frozen configuration drift", async t => {
  const f = await fixture(t), c = await validateGeneralTask(f.options);
  const state = { scene: "general", prepared: c.frozenIdentity, prompt: { sha256: c.promptSha256 }, workspace: c.workspace,
    requested: { model: c.requestedModel, permission_mode: c.requestedPermissionMode } };
  await validateGeneralResume(state, c);
  await assert.rejects(validateGeneralResume({ ...state, scene: "web" }, c), /RESUME_DRIFT/);
  await assert.rejects(validateGeneralResume(state, { ...c, requestedModel: "other" }), /RESUME_DRIFT/);
  await assert.rejects(validateGeneralResume(state, { ...c, frozenIdentity: { ...c.frozenIdentity, manifest_sha256: "b".repeat(64) } }), /RESUME_DRIFT/);
});

test("GUI probe does not interpret locked or unavailable state as unlocked", async () => {
  for (const [stdout, unlocked] of [['"IOConsoleLocked" = No', true], ['"IOConsoleLocked" = Yes', false], ["", false]]) {
    assert.equal((await inspectGuiSession({ run: async () => ({ stdout }) })).unlocked, unlocked);
  }
});

test("Composer project identity survives sidebar collapse and excludes permission menus", () => {
  const project = { title: "project-hidden-in-sidebar", aria: "project-hidden-in-sidebar", visible: true,
    suggestion_trigger: "true", popup: "menu" };
  const permission = { title: "全部允许", aria: "全部允许", visible: true, popup: "menu" };
  assert.equal(selectComposerProjectControl([permission, project]), project.title);
  assert.equal(selectComposerProjectControl([permission, { ...project, visible: false }]), null);
  assert.throws(() => selectComposerProjectControl([project, { ...project }]), /不唯一/);
});

test("Only the exact non-semantic onboarding dialog is eligible for automatic close", () => {
  const known = "多条消息支持列队发送\n无需等待当前回复完成，你可以继续补充信息或后续问题，豆包将按照发送顺序依次处理。\n开启体验";
  assert.equal(isKnownInformationalDialog(known), true);
  assert.equal(isKnownInformationalDialog(`${known}\n允许执行命令`), false);
  assert.equal(isKnownInformationalDialog("需要授权工具运行"), false);
  assert.equal(isKnownInformationalDialog("请选择题目答案"), false);
});

test("UI and native activity admit only registered peer sessions and still reject interactions", () => {
  const ui = { current_conversation_id: "1", stop_control_count: 1, busy_conversation_count: 1, busy_conversation_ids: ["1"],
    visible_dialog_count: 0, user_question_count: 0, approval_count: 0 };
  assert.throws(() => assertNoConflictingActivity(ui), /拒绝/);
  assertNoConflictingActivity(ui, ["1"]);
  assert.throws(() => assertNoConflictingActivity({ ...ui, busy_conversation_ids: ["2"] }, ["1"]), /拒绝/);
  assert.throws(() => assertNoConflictingActivity({ ...ui, approval_count: 1 }, ["1"]), /拒绝/);
  const native = { initialized: true, active: [{ session_id: "native", conversation_ids: ["1"] }] };
  assertNativeActivityAllowed(native, ["1"]);
  assertNativeActivityAllowed({ initialized: true, active: [{ session_id: "native", conversation_ids: [] }] }, [], ["native"]);
  assert.throws(() => assertNativeActivityAllowed(native), /UNREGISTERED/);
  assert.throws(() => assertNativeActivityAllowed({ initialized: true, active: [{ session_id: "other", conversation_ids: [] }] }, ["1"]), /UNREGISTERED/);
  assert.throws(() => assertNativeActivityAllowed({ initialized: false, active: [] }), /UNVERIFIED/);
});

test("A recovered native success is distinct from a prior tool error display", () => {
  const ui = { stop_control_count: 0, bound_conversation_busy_count: 0, visible_dialog_count: 0, user_question_count: 0, approval_count: 0, visible_error_count: 1 };
  assert.equal(canAcceptNativeCompletion(ui, { terminal: "completed" }), true);
  assert.equal(canAcceptNativeCompletion(ui, { terminal: "unverified" }), false);
  assert.equal(canAcceptNativeCompletion({ ...ui, approval_count: 1 }, { terminal: "completed" }), false);
});
