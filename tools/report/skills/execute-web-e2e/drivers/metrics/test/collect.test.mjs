import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile, symlink, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { collectLocalMetrics, findAstronTrace } from "../collect.mjs";
import { empty } from "../parsers.mjs";
import { inspectQwenRuntime, QWEN_PROFILE, QWEN_WINDOWS_PROFILE, QWEN_WINDOWS_1_0_6_PROFILE, verifiedQwenProfile } from "../qwen-profile.mjs";
import { updateExecutionRecord, createExecutionRecord } from "../../workbuddy/lib.mjs";
import { queryResourceIdentity } from "../../astronstudio/lib.mjs";

async function fixture(t, overrides = {}) {
  const home = await mkdtemp(join(tmpdir(), "web-resource-test-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const project = join(home, ".workbuddy/projects/project");
  await mkdir(project, { recursive: true });
  const input = { home, harness: "workbuddy", workspace: join(home, "task"), state: { session: { conversation_id: "session-123" }, attempt_id: "attempt" } };
  const file = join(project, "session-123.jsonl");
  const rows = [
    { type: "message", role: "user", timestamp: 1000, cwd: input.workspace, sessionId: "session-123", content: "PRIVATE_PROMPT", ...overrides },
    { type: "message", role: "assistant", timestamp: 2000, providerData: { messageId: "response-1", usage: { requests: 1, inputTokens: 10, outputTokens: 2, totalTokens: 12 } } },
  ];
  await writeFile(file, rows.map(r => JSON.stringify(r)).join("\n"));
  return { input, file, project };
}

test("本机会话按 ID/cwd 精确关联，只输出数值、来源和哈希", async t => {
  const { input } = await fixture(t);
  const result = await collectLocalMetrics(input);
  assert.equal(result.usage.total_tokens, 12);
  assert.equal(result.collection.attempt_id, "attempt");
  assert.match(result.collection.sources[0].sha256, /^[a-f0-9]{64}$/);
  assert.equal(result.collection.sources[0].path, "project/session-123.jsonl");
  assert.ok(!JSON.stringify(result).includes("PRIVATE_PROMPT"));
});

test("统一记录写入器透传资源，不改变执行状态、模型和工具准确率", async t => {
  const root = await mkdtemp(join(tmpdir(), "web-resource-record-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const identity = { batchId: "batch", taskId: "task", harness: { id: "qwenwork" }, model: { id: "model" } };
  const existing = createExecutionRecord(identity);
  existing.tools.format_accuracy = 0.8;
  existing.usage.cost_usd = 1;
  const metrics = empty("DISABLED");
  metrics.usage.total_tokens = 123;
  metrics.execution.agent_duration_seconds = 2;
  const file = join(root, "execution_record.json");
  const info = { identity, existing };
  await updateExecutionRecord({ executionRecord: file }, info, { resourceMetrics: metrics, execution: { status: "completed", duration_seconds: 5 } });
  const result = JSON.parse(await readFile(file, "utf8"));
  assert.equal(result.execution.status, "completed");
  assert.equal(result.execution.duration_seconds, 5);
  assert.equal(result.execution.agent_duration_seconds, 2);
  assert.equal(result.usage.total_tokens, 123);
  assert.equal(result.tools.format_accuracy, 0.8);
  assert.equal(result.usage.cost_usd, 1);
  assert.deepEqual(result.usage.collection.warnings, ["DISABLED"]);
  assert.equal(result.model.id, "model");
  await updateExecutionRecord({ executionRecord: file }, info, { execution: { error: null } });
  assert.equal(info.existing.usage.total_tokens, 123);
});

test("Astron 原生身份查询限定 thread 和 turn，非唯一映射拒绝", async () => {
  let rows = [{ cursor: JSON.stringify({ threadId: "native-session" }), cwd: "/task" }];
  const overrides = { copySnapshot: async () => {}, loadNodeSqlite: async () => ({ DatabaseSync: class {
    prepare(sql) {
      assert.match(sql, /runtime.thread_id = 'desktop-thread'/);
      assert.match(sql, /turns.turn_id = 'target-turn'/);
      return { all: () => rows };
    }
    close() {}
  } }) };
  assert.deepEqual(await queryResourceIdentity("ignored", "desktop-thread", "target-turn", overrides), { nativeId: "native-session", cwd: "/task" });
  rows = [];
  await assert.rejects(queryResourceIdentity("ignored", "desktop-thread", "target-turn", overrides), /AMBIGUOUS_NATIVE_SESSION/);
});

test("未知本地 Qwen SDK 与混合 transcript 版本不能命中已验 Profile", async t => {
  const root = await mkdtemp(join(tmpdir(), "web-resource-profile-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const sdk = join(root, "Contents/Resources/app.asar.unpacked/node_modules/@qoder-ai/qoder-agent-sdk");
  await mkdir(join(sdk, "dist/_worker"), { recursive: true });
  await writeFile(join(sdk, "package.json"), JSON.stringify({ name: "@ali/qodercn-agent-sdk-next", version: "1.0.28" }));
  await writeFile(join(sdk, "dist/_worker/qoder-worker-runtime.obf.mjs"), "unknown runtime");
  const identity = await inspectQwenRuntime(root, "1.0.5", [{ type: "assistant", version: "1.1.32" }], "darwin");
  assert.equal(identity.sdk_version, "1.0.28");
  assert.match(identity.runtime_sha256, /^[a-f0-9]{64}$/);
  assert.equal(verifiedQwenProfile(identity), null);
  const mixed = await inspectQwenRuntime(root, "1.0.5", [{ type: "assistant", version: "1.1.32" }, { type: "assistant" }], "darwin");
  assert.equal(mixed.transcript_version, null);
});
test("Qwen Windows 仅接受已核对的客户端和相同 runtime 身份", () => {
  assert.equal(verifiedQwenProfile(QWEN_WINDOWS_PROFILE), QWEN_PROFILE.id);
  assert.equal(verifiedQwenProfile(QWEN_WINDOWS_1_0_6_PROFILE), QWEN_WINDOWS_1_0_6_PROFILE.id);
  assert.equal(verifiedQwenProfile({ ...QWEN_WINDOWS_PROFILE, client_version: "1.0.6.0" }), QWEN_WINDOWS_1_0_6_PROFILE.id);
  assert.equal(verifiedQwenProfile({ ...QWEN_WINDOWS_1_0_6_PROFILE, client_version: "1.0.7.0" }), null);
  assert.equal(verifiedQwenProfile({ ...QWEN_WINDOWS_PROFILE, runtime_sha256: "unknown" }), null);
  assert.equal(verifiedQwenProfile({ ...QWEN_WINDOWS_PROFILE, transcript_version: "next" }), null);
});
test("Astron 日志发现支持 Windows AStudio Data 并拒绝跨根重复命中", async t => {
  const home = await mkdtemp(join(tmpdir(), "web-resource-astron-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const stateDb = join(home, "Programs/AStudio Data/userdata/state.sqlite");
  const windowsRoot = join(home, "Programs/AStudio Data/acode-home-overlay/sessions/2026/09/17");
  const sessionId = "native-session-123";
  await mkdir(windowsRoot, { recursive: true });
  const expected = join(windowsRoot, `rollout-${sessionId}.jsonl`);
  await writeFile(expected, "{}\n");
  assert.deepEqual(await findAstronTrace(home, stateDb, sessionId), {
    file: expected, root: join(home, "Programs/AStudio Data/acode-home-overlay/sessions"),
  });
  const legacy = join(home, ".acode/sessions/2026/09/17");
  await mkdir(legacy, { recursive: true });
  await writeFile(join(legacy, `rollout-${sessionId}.jsonl`), "{}\n");
  await assert.rejects(findAstronTrace(home, stateDb, sessionId), /AMBIGUOUS_TRACE/);
});
test("cwd 和 session 不一致、符号链接与坏 JSON 失败关闭", async t => {
  const { input, file, project } = await fixture(t, { cwd: "/different-task" });
  await assert.rejects(collectLocalMetrics(input), /TRACE_CWD_MISMATCH/);
  await writeFile(file, JSON.stringify({ cwd: input.workspace, sessionId: "wrong-session" }));
  await assert.rejects(collectLocalMetrics(input), /SESSION_IDENTITY_MISMATCH/);
  await writeFile(file, "invalid");
  await assert.rejects(collectLocalMetrics(input), SyntaxError);
  await rm(file);
  const target = join(project, "other.jsonl"); await writeFile(target, "{}");
  await symlink(target, file);
  await assert.rejects(collectLocalMetrics(input), /AMBIGUOUS_TRACE/);
});
