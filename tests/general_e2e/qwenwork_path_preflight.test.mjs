import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { inspectQwenProjectEncoding, planQwenExecutionPaths, preflightQwenExecutionPaths, qwenProjectDirectoryName, QWEN_PATH_ENCODING } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/path-preflight.mjs";
import { createLiveDependencies } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs";

const SOURCE = 'function hashPath(p){let h=5381;for(let i=0;i<p.length;i++)h=33*h^p.charCodeAt(i);return h}function encode(p){let v=p.replace(/[^a-zA-Z0-9]/g,"-");if(v.length<=limit)return v;let h=Math.abs(hashPath(p)).toString(36);return`${v.slice(0,limit)}-${h}`}var limit=200;';
const encoding = inspectQwenProjectEncoding(SOURCE);
function config(root = "/private/tmp/path-case") {
  return { task_root: root, candidate_workspace: join(root, "workspace"), prompt: { path: join(root, "PROMPT.md") },
    state_file: join(root, "control/journal.json"), evidence_root: join(root, "evidence"), client: { trace_root: "/private/tmp/qwen-traces" } };
}

test("installed encoding capability is recognized by implementation rather than version or obfuscated names", () => {
  assert.equal(encoding.verified, true);
  assert.equal(encoding.algorithm, QWEN_PATH_ENCODING);
  assert.equal(inspectQwenProjectEncoding(SOURCE.replaceAll("hashPath", "x").replaceAll("limit", "prefixCap")).verified, true);
  for (const changed of [SOURCE.replace("33*h", "31*h"), SOURCE.replace("200;", "250;"), SOURCE + SOURCE]) {
    assert.equal(inspectQwenProjectEncoding(changed).verified, false);
  }
});

test("project encoding preserves exact UTF-16 hashing, spaces, Chinese and emoji semantics", () => {
  assert.equal(qwenProjectDirectoryName("/中文 路径/😀", encoding), "---------");
  // Frozen expected basename from the r27 native transcript; not a value recomputed by the test.
  const path = "/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-fault-r27/worker/qwenwork-macos-general-fault-r27__qwenwork-macos-x86-64/execution/tasks/01_Productivity_Flow_task_005_support_handoff/workspace";
  assert.equal(qwenProjectDirectoryName(path, encoding), "-Users-gzx-debug-workspace-e2e-evaluate-qwenwork-macos-general-fault-r27-worker-qwenwork-macos-general-fault-r27--qwenwork-macos-x86-64-execution-tasks-01-Productivity-Flow-task-005-support-handoff-wo-usu7dd");
  const a = "/" + "a".repeat(199);
  assert.equal(qwenProjectDirectoryName(a, encoding).length, 200);
  assert.match(qwenProjectDirectoryName(a + "b", encoding), /^-a{199}-[a-z0-9]+$/u);
  assert.notEqual(qwenProjectDirectoryName(a + "b", encoding), qwenProjectDirectoryName(a + "c", encoding));
});

test("byte budgets admit NAME_MAX and reject its first overflow, including Unicode", () => {
  const good = config("/private/tmp/" + "中".repeat(85));
  assert.equal(planQwenExecutionPaths(good, encoding).verified, true);
  assert.throws(() => planQwenExecutionPaths(config("/private/tmp/" + "中".repeat(86)), encoding), /BUDGET_EXCEEDED/u);
  assert.throws(() => planQwenExecutionPaths(config("/private/tmp/" + "x".repeat(256)), encoding), /BUDGET_EXCEEDED/u);
  assert.throws(() => planQwenExecutionPaths(config(), { verified: false }), /ENCODING_UNVERIFIED/u);
});

test("PATH_MAX includes NUL and native segment reserves, independently from workspace length", () => {
  const current = config();
  const plan = planQwenExecutionPaths(current, encoding);
  const maximum = Math.max(...plan.paths.map((row) => row.bytes));
  assert.equal(planQwenExecutionPaths(current, encoding, { pathMax: maximum + 1 }).verified, true);
  assert.throws(() => planQwenExecutionPaths(current, encoding, { pathMax: maximum }), /BUDGET_EXCEEDED/u);
  current.client.trace_root = "/" + ["t".repeat(180), "t".repeat(180), "t".repeat(180), "t".repeat(100)].join("/");
  assert.throws(() => planQwenExecutionPaths(current, encoding), /native-segment-budget/u);
});

test("workspace and Prompt cannot escape their task root", () => {
  for (const field of ["workspace", "prompt"]) {
    const value = config();
    if (field === "workspace") value.candidate_workspace = "/private/tmp/foreign/workspace";
    else value.prompt.path = "/private/tmp/foreign/PROMPT.md";
    assert.throws(() => planQwenExecutionPaths(value, encoding), /OUTSIDE_TASK/u);
  }
});

test("filesystem preflight rejects a native project symlink without writing or connecting CDP", async (t) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "qwen-path-check-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const c = config(join(root, "用例 有空格"));
  c.client.trace_root = join(root, "trace");
  await mkdir(c.candidate_workspace, { recursive: true });
  await mkdir(c.client.trace_root);
  await writeFile(c.prompt.path, "fixture");
  const before = await readFile(c.prompt.path);
  const actual = await preflightQwenExecutionPaths(c, encoding);
  assert.equal(actual.verified, true);
  assert.ok(actual.filesystem_limits.every((row) => row.name_max > 0 && row.path_max > 0));
  await symlink(root, join(c.client.trace_root, "projects"));
  await assert.rejects(preflightQwenExecutionPaths(c, encoding), /SYMLINK_REJECTED/u);
  assert.deepEqual(await readFile(c.prompt.path), before);
  await assert.rejects(createLiveDependencies(c), /PATH_PREFLIGHT_REQUIRED/u);
});
