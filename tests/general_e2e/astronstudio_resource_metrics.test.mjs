import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  buildAstronStudioResourceMetrics,
  collectAstronStudioResourceMetrics,
  parseArgs,
} from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/collect_astronstudio_resource_metrics.mjs";

const IDENTITY = Object.freeze({
  batch_id: "batch-fixture",
  unit_id: "astronstudio-macos",
  task_id: "task-fixture",
  attempt_id: "attempt-fixture",
});
const SESSION = Object.freeze({
  thread_id: "thread-fixture",
  turn_id: "turn-fixture",
  session_id: "session-fixture",
  cwd: "/tmp/general-e2e-workspace-fixture",
  lifecycle_generation: "lifecycle-fixture",
});

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function state() {
  return {
    schema_version: "wildclawbench.general-e2e-astronstudio-execution-state/v1",
    identity: { ...IDENTITY },
    phase: "COMPLETED",
    prompt: { send_status: "sent" },
    send: { dispatch_attempt_count: 1 },
    session: {
      thread_id: SESSION.thread_id,
      turn_id: SESSION.turn_id,
      session_id: SESSION.session_id,
      cwd: SESSION.cwd,
      verified: true,
      native_status: "completed",
      last_observed_at: "2026-09-18T00:00:10.000Z",
    },
    execution: {
      started_at: "2026-09-18T00:00:00.000Z",
      finished_at: "2026-09-18T00:00:10.000Z",
      duration_seconds: 10,
    },
  };
}

function row(sequence, eventType, event, persistedAt = event.createdAt) {
  return {
    sequence,
    event_id: `event-${sequence}`,
    thread_id: SESSION.thread_id,
    turn_id: SESSION.turn_id,
    lifecycle_generation: SESSION.lifecycle_generation,
    event_type: eventType,
    persisted_at: persistedAt,
    event: {
      eventId: `event-${sequence}`,
      type: eventType,
      threadId: SESSION.thread_id,
      turnId: SESSION.turn_id,
      providerRefs: { providerThreadId: SESSION.session_id },
      ...event,
    },
  };
}

function usage(sequence, values, at) {
  return row(sequence, "thread.token-usage.updated", {
    createdAt: at,
    payload: { usage: values },
  });
}

function fixtureRows() {
  const first = {
    lastInputTokens: 10,
    totalInputTokens: 110,
    lastOutputTokens: 2,
    totalOutputTokens: 22,
    lastUsedTokens: 12,
    totalProcessedTokens: 132,
    lastCachedInputTokens: 5,
    totalCachedInputTokens: 55,
    lastReasoningOutputTokens: 1,
    totalReasoningOutputTokens: 5,
  };
  const second = {
    lastInputTokens: 20,
    totalInputTokens: 130,
    lastOutputTokens: 3,
    totalOutputTokens: 25,
    lastUsedTokens: 23,
    totalProcessedTokens: 155,
    lastCachedInputTokens: 10,
    totalCachedInputTokens: 65,
    lastReasoningOutputTokens: 1,
    totalReasoningOutputTokens: 6,
  };
  return [
    row(100, "turn.started", { createdAt: "2026-09-18T00:00:02.000Z", payload: {} }),
    usage(101, first, "2026-09-18T00:00:03.000Z"),
    row(102, "item.started", {
      createdAt: "2026-09-18T00:00:04.000Z",
      itemId: "call-fixture",
      payload: { data: { item: { id: "call-fixture", type: "commandExecution" } } },
    }),
    row(103, "item.completed", {
      createdAt: "2026-09-18T00:00:05.000Z",
      itemId: "call-fixture",
      payload: { data: { item: { id: "call-fixture", type: "commandExecution" } } },
    }),
    usage(104, second, "2026-09-18T00:00:06.000Z"),
    row(105, "turn.completed", {
      createdAt: "2026-09-18T00:00:07.000Z",
      payload: { state: "completed" },
    }),
  ];
}

function traceIndex(rows, completeness = "complete") {
  return {
    schema_id: "urn:wildclawbench:schema:general-e2e:trace-index:v1",
    schema_version: 1,
    identity: { ...IDENTITY },
    adapter: { id: "astronstudio-provider-runtime-events", version: "0.1.0" },
    session: { ...SESSION },
    raw_trace: [{
      path: "raw/astronstudio-provider-events.jsonl",
      sha256: "0".repeat(64),
      size: 0,
    }],
    raw_event_range: {
      first_sequence: rows[0].sequence,
      last_sequence: rows.at(-1).sequence,
      event_count: rows.length,
    },
    completeness: {
      status: completeness,
      omitted_event_count: completeness === "complete" ? 0 : 1,
      missing: completeness === "complete" ? [] : ["turn.completed"],
    },
    calls: [{ call_id: "call-fixture", call_sequence: 3, result_sequence: 4 }],
  };
}

function sources() {
  return [
    { path: "execution/automation-state.json", sha256: "1".repeat(64), size: 1 },
    { path: "trace/trace-index.json", sha256: "2".repeat(64), size: 2 },
    { path: "trace/raw/astronstudio-provider-events.jsonl", sha256: "3".repeat(64), size: 3 },
  ];
}

async function createFixture(rows = fixtureRows(), completeness = "complete") {
  const root = await mkdtemp(join(tmpdir(), "general-e2e-resource-fixture-"));
  const traceRoot = join(root, "trace");
  await mkdir(join(traceRoot, "raw"), { recursive: true });
  const rawPath = join(traceRoot, "raw/astronstudio-provider-events.jsonl");
  const statePath = join(root, "automation-state.json");
  const indexPath = join(traceRoot, "trace-index.json");
  const rawRows = rows.map(({ raw_line: ignored, ...entry }) => entry);
  const rawBytes = Buffer.from(`${rawRows.map((entry) => JSON.stringify(entry)).join("\n")}\n`);
  const index = traceIndex(rawRows, completeness);
  index.raw_trace[0].sha256 = sha256(rawBytes);
  index.raw_trace[0].size = rawBytes.length;
  await writeFile(rawPath, rawBytes);
  await writeFile(statePath, `${JSON.stringify(state(), null, 2)}\n`);
  await writeFile(indexPath, `${JSON.stringify(index, null, 2)}\n`);
  return { root, rawPath, statePath, indexPath, output: join(traceRoot, "resource-metrics.json") };
}

test("CLI requires state and trace index", () => {
  assert.throws(() => parseArgs([]), /--state-file/u);
  assert.throws(() => parseArgs(["--state-file", "/tmp/state.json"]), /--trace-index/u);
  assert.equal(parseArgs(["--help"]).help, true);
});

test("native usage deltas reconcile with cumulative totals and preserve prior-turn baseline", () => {
  const rows = fixtureRows().map((entry, index) => ({ ...entry, raw_line: index + 1 }));
  const result = buildAstronStudioResourceMetrics({
    state: state(),
    traceIndex: traceIndex(rows),
    rows,
    sources: sources(),
  });
  assert.equal(result.collection.status, "complete");
  assert.equal(result.metrics.usage.input_tokens.value, 30);
  assert.equal(result.metrics.usage.output_tokens.value, 5);
  assert.equal(result.metrics.usage.total_tokens.value, 35);
  assert.equal(result.metrics.usage.cache_read_input_tokens.value, 15);
  assert.equal(result.metrics.usage.reasoning_output_tokens.value, 2);
  assert.equal(result.metrics.usage.cache_creation_input_tokens.value, null);
  assert.equal(result.metrics.requests.request_count.value, 2);
  assert.equal(result.metrics.requests.request_count.status, "inferred");
  assert.equal(result.metrics.requests.request_attempt_count.value, null);
  assert.equal(result.metrics.tools.call_count.value, 1);
  assert.equal(result.metrics.timing.duration_seconds.value, 10);
  assert.equal(result.metrics.timing.agent_duration_seconds.value, 5);
  assert.deepEqual(result.collection.coverage.total_tokens, {
    known: 2, total: 2, unit: "usage_update",
  });
});

test("identical usage snapshots do not inflate requests", () => {
  const rows = fixtureRows();
  rows.splice(2, 0, structuredClone(rows[1]));
  rows.forEach((entry, index) => {
    entry.sequence = 100 + index;
    entry.event_id = `event-${100 + index}`;
    entry.event.eventId = entry.event_id;
    entry.raw_line = index + 1;
  });
  const result = buildAstronStudioResourceMetrics({
    state: state(), traceIndex: traceIndex(rows), rows, sources: sources(),
  });
  assert.equal(result.metrics.requests.request_count.value, 2);
  assert.equal(result.metrics.usage.total_tokens.value, 35);
});

test("missing token fields keep null plus known subtotal and independent metrics", () => {
  const rows = fixtureRows().map((entry, index) => ({ ...entry, raw_line: index + 1 }));
  delete rows[4].event.payload.usage.lastOutputTokens;
  const result = buildAstronStudioResourceMetrics({
    state: state(), traceIndex: traceIndex(rows), rows, sources: sources(),
  });
  assert.equal(result.collection.status, "partial");
  assert.equal(result.metrics.usage.output_tokens.value, null);
  assert.equal(result.metrics.usage.output_tokens.status, "partial");
  assert.equal(result.collection.known_subtotals.output_tokens, 2);
  assert.deepEqual(result.collection.coverage.output_tokens, {
    known: 1, total: 2, unit: "usage_update",
  });
  assert.equal(result.metrics.tools.call_count.value, 1);
  assert.equal(result.metrics.timing.duration_seconds.value, 10);
});

test("partial trace downgrades event-derived values but preserves wall-clock duration", () => {
  const rows = fixtureRows().map((entry, index) => ({ ...entry, raw_line: index + 1 }));
  const index = traceIndex(rows, "partial");
  const result = buildAstronStudioResourceMetrics({
    state: state(), traceIndex: index, rows, sources: sources(),
  });
  assert.equal(result.metrics.usage.total_tokens.value, null);
  assert.equal(result.metrics.usage.total_tokens.status, "partial");
  assert.equal(result.collection.known_subtotals.total_tokens, 35);
  assert.equal(result.metrics.tools.call_count.value, null);
  assert.equal(result.collection.known_subtotals.call_count, 1);
  assert.equal(result.metrics.timing.agent_duration_seconds.value, null);
  assert.equal(result.metrics.timing.duration_seconds.value, 10);
});

test("semantic conflicts and indexed artifact tampering fail closed", async () => {
  const rows = fixtureRows().map((entry, index) => ({ ...entry, raw_line: index + 1 }));
  rows[1].event.payload.usage.lastUsedTokens = 13;
  assert.throws(
    () => buildAstronStudioResourceMetrics({
      state: state(), traceIndex: traceIndex(rows), rows, sources: sources(),
    }),
    /TOKEN_SEMANTICS_MISMATCH/u,
  );

  const fixture = await createFixture();
  try {
    const result = await collectAstronStudioResourceMetrics({
      stateFile: fixture.statePath,
      traceIndex: fixture.indexPath,
      output: fixture.output,
      replace: false,
    });
    assert.equal(result.collection_status, "complete");
    const document = JSON.parse(await readFile(fixture.output, "utf8"));
    assert.equal(document.metrics.usage.total_tokens.value, 35);
    await assert.rejects(
      collectAstronStudioResourceMetrics({
        stateFile: fixture.statePath,
        traceIndex: fixture.indexPath,
        output: fixture.output,
        replace: false,
      }),
      /OUTPUT_EXISTS/u,
    );
    await writeFile(fixture.rawPath, "{}\n");
    await assert.rejects(
      collectAstronStudioResourceMetrics({
        stateFile: fixture.statePath,
        traceIndex: fixture.indexPath,
        output: join(fixture.root, "tampered.json"),
        replace: false,
      }),
      /RAW_TRACE_ARTIFACT_MISMATCH/u,
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});
