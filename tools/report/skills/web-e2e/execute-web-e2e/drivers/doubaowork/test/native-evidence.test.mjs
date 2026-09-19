import assert from "node:assert/strict";
import {
  copyFile,
  mkdtemp,
  mkdir,
  readFile,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  atomicWriteJson,
  buildNativeEvidence,
  parseTrajectoryJsonl,
  summarizeNormalizedEvents,
} from "../native-evidence.mjs";

const fixtureUrl = new URL("fixtures/trajectory-partial.jsonl", import.meta.url);
const SESSION_ID = "12345678901234567";

async function createNativeFixture(context, { symlinkSystem = false } = {}) {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-native-evidence-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const agentId = "agent_fixture";
  const agentRoot = join(root, SESSION_ID, "agents", agentId);
  const systemRoot = join(agentRoot, "system");
  let trajectoryPath = join(systemRoot, "trajectory.jsonl");
  if (symlinkSystem) {
    const externalSystem = join(root, "external-system");
    await mkdir(externalSystem, { recursive: true });
    await copyFile(fixtureUrl, join(externalSystem, "trajectory.jsonl"));
    await mkdir(agentRoot, { recursive: true });
    await symlink(externalSystem, systemRoot);
  } else {
    await mkdir(systemRoot, { recursive: true });
    await copyFile(fixtureUrl, trajectoryPath);
  }
  const info = await stat(trajectoryPath);
  return {
    root,
    discovery: {
      session: {
        exists: true,
        trajectories: [{
          agent_id: agentId,
          path: trajectoryPath,
          relative_path: `${SESSION_ID}/agents/${agentId}/system/trajectory.jsonl`,
          size_bytes: info.size,
        }],
      },
    },
  };
}

test("脱敏 trajectory 解析工具调用与结果但不伪造成功", async () => {
  const text = await readFile(fixtureUrl, "utf8");
  const parsed = parseTrajectoryJsonl(text, "fixture/trajectory.jsonl");
  const summary = summarizeNormalizedEvents(parsed.events.map((event) => ({
    ...event,
    agent_id: "agent_fixture",
  })));
  assert.equal(summary.event_count, 3);
  assert.equal(summary.tool_call_known_subtotal, 1);
  assert.equal(summary.matched_tool_result_count, 1);
  assert.equal(summary.final_assistant_in_trajectory, false);
  const result = parsed.events.find((event) => event.kind === "tool_result");
  assert.equal(result.outcome, "unknown");
});

test("native evidence 将 cwd、终态与 Token 保持为空", async (context) => {
  const fixture = await createNativeFixture(context);
  const evidence = await buildNativeEvidence({
    sessionId: SESSION_ID,
    workspace: "/private/debug/task/workspace",
    discovery: fixture.discovery,
  });
  assert.equal(evidence.identity.native_cwd, null);
  assert.equal(evidence.identity.workspace_binding.status, "unverified");
  assert.equal(evidence.terminal.status, "unverified");
  assert.equal(evidence.trace.completeness, "partial");
  assert.equal(evidence.resources.usage.total_tokens.value, null);
  assert.equal(evidence.resources.tools.call_count, 1);
  assert.equal(evidence.resources.tools.status, "partial");
  assert.deepEqual(evidence.resources.tools.coverage, { numerator: 1, denominator: null });
});

test("损坏行只形成缺口，不吞掉后续有效事件", () => {
  const parsed = parseTrajectoryJsonl(
    "{broken\nnull\n[]\n{\"role\":\"user\",\"content\":\"ok\"}\n",
    "fixture",
  );
  assert.equal(parsed.events.length, 1);
  assert.deepEqual(parsed.warnings.map((warning) => warning.code), [
    "INVALID_JSON_LINE",
    "INVALID_JSON_LINE",
    "INVALID_JSON_LINE",
  ]);
});

test("工具结果只按 session、agent 和 call ID 匹配", () => {
  const source = (line) => ({ file: "fixture", line });
  const summary = summarizeNormalizedEvents([
    { kind: "assistant_tool_call", agent_id: "agent-a", call_id: "same", source: source(1) },
    { kind: "assistant_tool_call", agent_id: "agent-b", call_id: "same", source: source(2) },
    { kind: "tool_result", agent_id: "agent-a", call_id: "same", source: source(3) },
  ]);
  assert.equal(summary.tool_call_known_subtotal, 2);
  assert.equal(summary.tool_result_known_subtotal, 1);
  assert.equal(summary.matched_tool_result_count, 1);
  assert.equal(summary.identifier_scope, "session+agent_id+call_id");
});

test("空 ID、重复与冲突来源保留诊断且不重复计数", () => {
  const event = (overrides) => ({
    kind: "assistant_tool_call",
    agent_id: "agent-a",
    call_id: "dup",
    tool_name: "Write",
    arguments: "{}",
    source: { file: "fixture", line: 1 },
    ...overrides,
  });
  const summary = summarizeNormalizedEvents([
    event({ source: { file: "fixture", line: 1 } }),
    event({ source: { file: "fixture", line: 2 } }),
    event({ call_id: "conflict", source: { file: "fixture", line: 3 } }),
    event({ call_id: "conflict", tool_name: "Shell", source: { file: "fixture", line: 4 } }),
    event({ call_id: null, source: { file: "fixture", line: 5 } }),
  ]);
  assert.equal(summary.tool_call_event_count, 5);
  assert.equal(summary.tool_call_known_subtotal, 2);
  assert.equal(summary.identifier_coverage.status, "incomplete");
  assert.deepEqual(new Set(summary.diagnostics.map((item) => item.code)), new Set([
    "TOOL_CALL_SCOPE_MISSING",
    "DUPLICATE_SCOPED_TOOL_CALL_ID",
    "CONFLICTING_SCOPED_TOOL_CALL_ID",
  ]));
  const conflict = summary.diagnostics.find((item) => item.code === "CONFLICTING_SCOPED_TOOL_CALL_ID");
  assert.deepEqual(conflict.sources, [
    { file: "fixture", line: 3 },
    { file: "fixture", line: 4 },
  ]);
});

test("trajectory system 祖先是符号链接时拒绝读取", async (context) => {
  const fixture = await createNativeFixture(context, { symlinkSystem: true });
  await assert.rejects(() => buildNativeEvidence({
    sessionId: SESSION_ID,
    workspace: "/private/debug/task/workspace",
    discovery: fixture.discovery,
  }), /符号链接/);
});

test("native evidence 输出只允许新文件", async (context) => {
  const root = await mkdtemp(join(tmpdir(), "doubaowork-native-output-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const output = join(root, "evidence.json");
  await writeFile(output, "original\n", "utf8");
  await assert.rejects(() => atomicWriteJson(output, { changed: true }), /拒绝覆盖/);
  assert.equal(await readFile(output, "utf8"), "original\n");
});
