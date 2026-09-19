import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import { test } from "node:test";

import {
  buildNativeEvidence,
  parseTrajectoryJsonl,
  summarizeNormalizedEvents,
} from "../native-evidence.mjs";

const fixtureUrl = new URL("fixtures/trajectory-partial.jsonl", import.meta.url);

test("脱敏 trajectory 解析工具调用与结果但不伪造成功", async () => {
  const text = await readFile(fixtureUrl, "utf8");
  const parsed = parseTrajectoryJsonl(text, "fixture/trajectory.jsonl");
  const summary = summarizeNormalizedEvents(parsed.events);
  assert.equal(summary.event_count, 3);
  assert.equal(summary.tool_call_known_subtotal, 1);
  assert.equal(summary.matched_tool_result_count, 1);
  assert.equal(summary.final_assistant_in_trajectory, false);
  const result = parsed.events.find((event) => event.kind === "tool_result");
  assert.equal(result.outcome, "unknown");
});

test("native evidence 将 cwd、终态与 Token 保持为空", async () => {
  const info = await stat(fixtureUrl);
  const evidence = await buildNativeEvidence({
    sessionId: "12345678901234567",
    workspace: "/private/debug/task/workspace",
    discovery: {
      session: {
        exists: true,
        trajectories: [{
          agent_id: "agent_fixture",
          path: fixtureUrl,
          relative_path: "12345678901234567/agents/agent_fixture/system/trajectory.jsonl",
          size_bytes: info.size,
        }],
      },
    },
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
  const parsed = parseTrajectoryJsonl("{broken\n{\"role\":\"user\",\"content\":\"ok\"}\n", "fixture");
  assert.equal(parsed.events.length, 1);
  assert.equal(parsed.warnings[0].code, "INVALID_JSON_LINE");
});
