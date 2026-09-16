import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, symlink, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { collectLocalMetrics } from "../collect.mjs";

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
