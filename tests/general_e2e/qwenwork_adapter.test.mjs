import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  buildQwenAdapterEvidence,
  buildQwenCallIndex,
  buildQwenGeneralResourceMetrics,
  matchQwenWorkRuntimeProfile,
  normalizeQwenTranscript,
} from "../../eval_general_e2e/adapters/qwenwork/index.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const FIXTURES = join(ROOT, "tests/general_e2e/fixtures/qwenwork");
const WORKSPACE = "/private/tmp/qwenwork-general-fixture/workspace";
const IDENTITY = Object.freeze({
  batch_id: "batch-fixture",
  unit_id: "qwenwork-macos",
  task_id: "task-fixture",
  attempt_id: "attempt-fixture",
});
const SOURCES = Object.freeze([
  { path: "evidence/qwenwork/transcript-redacted.jsonl", sha256: "1".repeat(64), size: 512 },
  { path: "evidence/qwenwork/segments-redacted.jsonl", sha256: "2".repeat(64), size: 1024 },
]);

async function json(name) {
  return JSON.parse(await readFile(join(FIXTURES, name), "utf8"));
}

async function jsonl(name) {
  return (await readFile(join(FIXTURES, name), "utf8"))
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

test("historical macOS runtime matches exactly while installed 1.0.6 remains unverified", async () => {
  const historical = await json("runtime-historical-macos-1.0.5.json");
  const current = await json("runtime-current-macos-1.0.6.json");
  assert.equal(matchQwenWorkRuntimeProfile(historical), "qwenwork-macos-1.0.5-qoder-cache-inclusive-v1");
  assert.equal(matchQwenWorkRuntimeProfile(current), null);
  assert.equal(matchQwenWorkRuntimeProfile({ ...historical, runtime_sha256: "0".repeat(64) }), null);
});

test("resource adapter reconciles the verified primary turn and excludes background usage", async () => {
  const segmentRows = await jsonl("segments-redacted.jsonl");
  const runtimeIdentity = await json("runtime-historical-macos-1.0.5.json");
  const { resource_metrics: metrics, observation } = buildQwenGeneralResourceMetrics({
    identity: IDENTITY,
    segmentRows,
    runtimeIdentity,
    sources: SOURCES,
    collectedAt: "2026-09-17T03:01:00.000Z",
    executionDurationSeconds: 6,
  });
  assert.equal(metrics.collection.status, "complete");
  assert.equal(metrics.metrics.usage.input_tokens.value, 250);
  assert.equal(metrics.metrics.usage.output_tokens.value, 50);
  assert.equal(metrics.metrics.usage.total_tokens.value, 300);
  assert.equal(metrics.metrics.usage.cache_read_input_tokens.value, 200);
  assert.equal(metrics.metrics.usage.cache_creation_input_tokens.value, null);
  assert.equal(metrics.metrics.usage.cache_creation_input_tokens.status, "unavailable");
  assert.equal(metrics.metrics.requests.request_count.value, 2);
  assert.equal(metrics.metrics.requests.request_attempt_count.value, null);
  assert.equal(metrics.metrics.tools.call_count.value, 1);
  assert.equal(metrics.metrics.timing.agent_duration_seconds.value, 5);
  assert.equal(metrics.metrics.timing.duration_seconds.value, 6);
  assert.deepEqual(metrics.collection.coverage.total_tokens, {
    known: 2,
    total: 2,
    unit: "model_response",
  });
  assert.equal(observation.collection.background_operations.length, 1);
  assert.equal(observation.collection.background_operations[0].request_count, 1);
});

test("unknown current runtime preserves unverified native usage but strict v1 publishes null unavailable metrics", async () => {
  const segmentRows = await jsonl("segments-redacted.jsonl");
  const runtimeIdentity = await json("runtime-current-macos-1.0.6.json");
  const { resource_metrics: metrics, observation } = buildQwenGeneralResourceMetrics({
    identity: IDENTITY,
    segmentRows,
    runtimeIdentity,
    sources: SOURCES,
    collectedAt: "2026-09-17T03:01:00.000Z",
    executionDurationSeconds: 6,
  });
  assert.equal(metrics.collection.status, "partial");
  assert.equal(metrics.metrics.usage.total_tokens.value, null);
  assert.equal(metrics.metrics.usage.total_tokens.status, "unavailable");
  assert.equal(metrics.collection.coverage.total_tokens.known, 0);
  assert.deepEqual(observation.collection.native_usage, {
    input_tokens: 250,
    output_tokens: 50,
    cache_read_input_tokens: 200,
    cache_creation_input_tokens: 0,
  });
  assert.equal(observation.collection.metrics.total_tokens.status, "unverified");
  assert.ok(metrics.collection.warnings.includes("QWEN_TOKEN_SEMANTICS_UNVERIFIED"));
});

test("partial request evidence keeps null, known subtotal, and coverage", async () => {
  const segmentRows = (await jsonl("segments-redacted.jsonl"))
    .filter((row) => !(row.type === "model.response.completed" && row.request_id === "request-fixture-002"));
  const runtimeIdentity = await json("runtime-historical-macos-1.0.5.json");
  const { resource_metrics: metrics } = buildQwenGeneralResourceMetrics({
    identity: IDENTITY,
    segmentRows,
    runtimeIdentity,
    sources: SOURCES,
    collectedAt: "2026-09-17T03:01:00.000Z",
    executionDurationSeconds: 6,
  });
  assert.equal(metrics.metrics.usage.input_tokens.value, null);
  assert.equal(metrics.metrics.usage.input_tokens.status, "partial");
  assert.equal(metrics.collection.known_subtotals.input_tokens, 100);
  assert.deepEqual(metrics.collection.coverage.input_tokens, {
    known: 1,
    total: 2,
    unit: "model_response",
  });
  assert.equal(metrics.metrics.tools.call_count.value, 1);
});

test("transcript normalization binds exact session/cwd and correlates tool outcomes", async () => {
  const transcriptRows = await jsonl("transcript-redacted.jsonl");
  const segmentRows = await jsonl("segments-redacted.jsonl");
  const result = normalizeQwenTranscript({
    identity: IDENTITY,
    transcriptRows,
    segmentRows,
    sessionId: "session-fixture-001",
    workspace: WORKSPACE,
    redacted: true,
  });
  assert.equal(result.binding.transcript_version, "1.1.32");
  assert.ok(result.events.every((event, index) => event.sequence === index));
  assert.ok(result.events.every((event) => event.source.redacted));
  assert.deepEqual(
    result.events.filter((event) => ["user_message", "assistant_message", "tool_call", "tool_result"].includes(event.type))
      .map((event) => event.type),
    ["user_message", "tool_call", "tool_result", "assistant_message"],
  );
  const toolResult = result.events.find((event) => event.type === "tool_result");
  assert.equal(toolResult.tool.call_id, "tool-call-fixture-001");
  assert.equal(toolResult.tool.status, "success");
  assert.equal(toolResult.tool.exit_code, 0);
  assert.deepEqual(buildQwenCallIndex(result.events), [{
    call_id: "tool-call-fixture-001",
    call_sequence: result.events.find((event) => event.type === "tool_call").sequence,
    result_sequence: toolResult.sequence,
  }]);
  assert.throws(() => normalizeQwenTranscript({
    identity: IDENTITY,
    transcriptRows,
    segmentRows,
    sessionId: "wrong-session",
    workspace: WORKSPACE,
  }), /SESSION_MISMATCH/u);
});

test("private adapter evidence keeps native IDs without inventing thread or turn", async () => {
  const evidence = buildQwenAdapterEvidence({
    session: {
      conversation_id: "conversation-fixture-001",
      sub_chat_id: "sub-chat-fixture-001",
      session_id: "session-fixture-001",
      local_project_id: "project-fixture-001",
      cwd: WORKSPACE,
    },
    runtimeIdentity: await json("runtime-current-macos-1.0.6.json"),
    sources: SOURCES,
    terminalMapping: { native_status: "completed", business_status: "completed" },
  });
  assert.equal(evidence.native_identity.session_id, "session-fixture-001");
  assert.equal("thread_id" in evidence.native_identity, false);
  assert.ok(evidence.limitations.includes("not-a-public-trace-index"));
});
