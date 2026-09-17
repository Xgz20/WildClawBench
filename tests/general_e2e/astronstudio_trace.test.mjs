import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";

import {
  archiveAstronStudioTrace,
  normalizeTraceRows,
  parseArgs as parseArchiveArgs,
} from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/archive_astronstudio_trace.mjs";
import {
  parseArgs as parseQueryArgs,
  queryTrace,
} from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/query_trace.mjs";

const TASK_ID = "02_Code_Intelligence_task_001_temperature_cli_fix";
const THREAD_ID = "thread-trace-fixture";
const TURN_ID = "turn-trace-fixture";
const SESSION_ID = "session-trace-fixture";
const LIFECYCLE_ID = "lifecycle-trace-fixture";

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function nativeEvent(type, data = {}) {
  const event = {
    eventId: data.eventId,
    type,
    threadId: THREAD_ID,
    turnId: TURN_ID,
    createdAt: data.createdAt,
    provider: "acode",
    providerRefs: {
      providerThreadId: data.providerSessionId || SESSION_ID,
      providerTurnId: "provider-turn-fixture",
      providerItemId: data.itemId || null,
    },
    payload: data.payload || {},
    raw: { source: "fixture", method: type, payload: {} },
  };
  if (data.itemId) event.itemId = data.itemId;
  return event;
}

function itemPayload(item, itemType) {
  return {
    itemType,
    data: { threadId: THREAD_ID, turnId: TURN_ID, item },
  };
}

async function createFixture() {
  const root = await import("node:fs/promises").then(({ mkdtemp }) => (
    mkdtemp(join(tmpdir(), "general-e2e-trace-test-"))
  ));
  const unitRoot = join(root, "unit");
  const taskRoot = join(unitRoot, "execution", "tasks", TASK_ID);
  const workspace = join(taskRoot, "workspace");
  const controlRoot = join(unitRoot, ".general-e2e", "execution", TASK_ID);
  const stateFile = join(controlRoot, "automation-state.json");
  const promptPath = join(taskRoot, "PROMPT.md");
  const finalResponsePath = join(controlRoot, "final-response.md");
  const stateDatabase = join(root, "state.sqlite");
  const outputDir = join(root, "trace");
  await mkdir(join(workspace, "project"), { recursive: true });
  await mkdir(controlRoot, { recursive: true });
  const prompt = Buffer.from("请修复温度换算程序。", "utf8");
  const finalResponse = Buffer.from("已完成修复，测试 OK。\n", "utf8");
  await writeFile(promptPath, prompt);
  await writeFile(finalResponsePath, finalResponse);
  const state = {
    schema_version: "wildclawbench.general-e2e-astronstudio-execution-state/v1",
    identity: {
      batch_id: "batch-trace-fixture",
      unit_id: "astronstudio-macos",
      task_id: TASK_ID,
      attempt_id: "attempt-trace-fixture",
    },
    phase: "COMPLETED",
    task_root: taskRoot,
    prompt: {
      path: promptPath,
      sha256: digest(prompt),
      send_status: "sent",
      sent_at: "2026-09-17T10:00:01.000Z",
    },
    send: { dispatch_attempt_count: 1 },
    session: {
      thread_id: THREAD_ID,
      turn_id: TURN_ID,
      session_id: SESSION_ID,
      cwd: workspace,
      verified: true,
    },
    run_config: { path: join(root, "run-config.json") },
    evidence: {
      final_response_path: `.general-e2e/execution/${TASK_ID}/final-response.md`,
      final_response_sha256: digest(finalResponse),
    },
  };
  await writeFile(stateFile, `${JSON.stringify(state, null, 2)}\n`, "utf8");

  const database = new DatabaseSync(stateDatabase);
  database.exec(`
CREATE TABLE projection_projects (project_id TEXT PRIMARY KEY, workspace_root TEXT NOT NULL);
CREATE TABLE projection_threads (thread_id TEXT PRIMARY KEY, project_id TEXT NOT NULL);
CREATE TABLE projection_turns (
  thread_id TEXT NOT NULL, turn_id TEXT NOT NULL, state TEXT NOT NULL,
  requested_at TEXT, started_at TEXT, completed_at TEXT
);
CREATE TABLE provider_runtime_events (
  sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL, thread_id TEXT NOT NULL,
  turn_id TEXT, lifecycle_generation TEXT, event_type TEXT NOT NULL,
  event_json TEXT NOT NULL, persisted_at TEXT NOT NULL
);
`);
  database.prepare("INSERT INTO projection_projects VALUES (?, ?)").run("project-fixture", workspace);
  database.prepare("INSERT INTO projection_threads VALUES (?, ?)").run(THREAD_ID, "project-fixture");
  database.prepare("INSERT INTO projection_turns VALUES (?, ?, ?, ?, ?, ?)").run(
    THREAD_ID,
    TURN_ID,
    "completed",
    "2026-09-17T10:00:00.000Z",
    "2026-09-17T10:00:01.000Z",
    "2026-09-17T10:00:07.000Z",
  );
  const insert = database.prepare("INSERT INTO provider_runtime_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)");
  const rows = [
    [100, "event-turn-start", "turn.started", nativeEvent("turn.started", {
      eventId: "event-turn-start", createdAt: "2026-09-17T10:00:01.000Z",
    })],
    [101, "event-user", "item.completed", nativeEvent("item.completed", {
      eventId: "event-user", itemId: "item-user", createdAt: "2026-09-17T10:00:02.000Z",
      payload: itemPayload({
        type: "userMessage", id: "item-user",
        content: [{ type: "text", text: prompt.toString("utf8") }],
      }, "user_message"),
    })],
    [102, "event-call", "item.started", nativeEvent("item.started", {
      eventId: "event-call", itemId: "call-command-1", createdAt: "2026-09-17T10:00:03.000Z",
      payload: itemPayload({
        type: "commandExecution", id: "call-command-1", status: "inProgress",
        command: "python3 project/test_converter.py", cwd: workspace,
        commandActions: [{ type: "unknown", command: "python3 project/test_converter.py" }],
      }, "command_execution"),
    })],
    [103, "event-result", "item.completed", nativeEvent("item.completed", {
      eventId: "event-result", itemId: "call-command-1", createdAt: "2026-09-17T10:00:04.000Z",
      payload: itemPayload({
        type: "commandExecution", id: "call-command-1", status: "completed",
        command: "python3 project/test_converter.py", cwd: workspace,
        commandActions: [{ type: "unknown", command: "python3 project/test_converter.py" }],
        aggregatedOutput: "3 tests OK\n", exitCode: 0, durationMs: 250,
      }, "command_execution"),
    })],
    [104, "event-assistant", "item.completed", nativeEvent("item.completed", {
      eventId: "event-assistant", itemId: "item-assistant", createdAt: "2026-09-17T10:00:05.000Z",
      payload: itemPayload({
        type: "agentMessage", id: "item-assistant", text: finalResponse.toString("utf8").trim(),
      }, "assistant_message"),
    })],
    [105, "event-usage", "thread.token-usage.updated", nativeEvent("thread.token-usage.updated", {
      eventId: "event-usage", createdAt: "2026-09-17T10:00:06.000Z",
      payload: { inputTokens: 10, outputTokens: 5 },
    })],
    [106, "event-turn-complete", "turn.completed", nativeEvent("turn.completed", {
      eventId: "event-turn-complete", createdAt: "2026-09-17T10:00:07.000Z",
    })],
  ];
  for (const [sequence, eventId, eventType, event] of rows) {
    insert.run(
      sequence, eventId, THREAD_ID, TURN_ID, LIFECYCLE_ID, eventType,
      JSON.stringify(event), `2026-09-17T10:00:${String(sequence - 99).padStart(2, "0")}.500Z`,
    );
  }
  insert.run(
    107,
    "event-other-thread",
    "item.completed",
    "other-thread",
    "other-turn",
    "other-lifecycle",
    JSON.stringify({
      eventId: "event-other-thread",
      type: "item.completed",
      threadId: "other-thread",
      turnId: "other-turn",
      providerRefs: { providerThreadId: "other-session" },
      payload: itemPayload({ type: "agentMessage", text: "MUST_NOT_APPEAR" }, "assistant_message"),
    }),
    "2026-09-17T10:00:08.500Z",
  );
  database.close();
  return { root, state, stateFile, stateDatabase, outputDir, workspace };
}

test("archive CLI requires a state file and query CLI bounds pagination", () => {
  assert.throws(() => parseArchiveArgs([]), /--state-file/u);
  assert.throws(
    () => parseQueryArgs(["--trace-index", "/tmp/index.json", "--page-size", "201"]),
    /1–200/u,
  );
  assert.throws(
    () => parseQueryArgs([
      "--trace-index", "/tmp/index.json", "--from-sequence", "5", "--to-sequence", "4",
    ]),
    /from-sequence/u,
  );
});

test("exact bound turn archives raw and normalized events without cross-session pollution", async () => {
  const fixture = await createFixture();
  try {
    const result = await archiveAstronStudioTrace({
      stateFile: fixture.stateFile,
      stateDb: fixture.stateDatabase,
      outputDir: fixture.outputDir,
      replace: false,
    });
    assert.equal(result.trace_index.completeness.status, "complete");
    assert.equal(result.trace_index.raw_event_range.event_count, 7);
    assert.equal(result.trace_index.calls.length, 1);
    const raw = await readFile(join(fixture.outputDir, "raw/astronstudio-provider-events.jsonl"), "utf8");
    const transcript = (await readFile(join(fixture.outputDir, "transcript.jsonl"), "utf8"))
      .trim().split("\n").map((line) => JSON.parse(line));
    assert.doesNotMatch(raw, /MUST_NOT_APPEAR/u);
    assert.equal(transcript.filter((event) => event.type === "tool_call").length, 1);
    assert.equal(transcript.filter((event) => event.type === "tool_result").length, 1);
    const call = transcript.find((event) => event.type === "tool_call");
    const returned = transcript.find((event) => event.type === "tool_result");
    assert.equal(call.tool.call_id, "call-command-1");
    assert.equal(returned.tool.call_id, "call-command-1");
    assert.equal(call.tool.name, "command");
    assert.equal(call.tool.arguments.command, "python3 project/test_converter.py");
    assert.equal(returned.tool.result.output, "3 tests OK\n");
    assert.deepEqual(call.path_mappings, [{
      kind: "cwd", raw: fixture.workspace, normalized: "/tmp_workspace",
    }]);

    const oldRuleCalls = transcript.flatMap((entry) => {
      const message = entry.message || entry;
      if (message.role !== "assistant") return [];
      const blocks = Array.isArray(message.content) ? message.content : [];
      return blocks.filter((block) => block?.type === "tool_use")
        .map((block) => [block.name, block.input]);
    });
    assert.deepEqual(oldRuleCalls, [["command", {
      command: "python3 project/test_converter.py",
      cwd: fixture.workspace,
      normalized_cwd: "/tmp_workspace",
      command_actions: [{ type: "unknown", command: "python3 project/test_converter.py" }],
    }]]);
    assert.equal(
      transcript.filter((event) => event.role === "assistant" && typeof event.content === "string").at(-1).content,
      "已完成修复，测试 OK。",
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("read-only query returns total hits pagination and exact locations", async () => {
  const fixture = await createFixture();
  try {
    await archiveAstronStudioTrace({
      stateFile: fixture.stateFile,
      stateDb: fixture.stateDatabase,
      outputDir: fixture.outputDir,
      replace: false,
    });
    const traceIndex = join(fixture.outputDir, "trace-index.json");
    const byCall = await queryTrace({
      traceIndex, callId: "call-command-1", page: 1, pageSize: 1,
    });
    assert.equal(byCall.pagination.total_matches, 2);
    assert.equal(byCall.pagination.total_pages, 2);
    assert.equal(byCall.pagination.has_previous, false);
    assert.equal(byCall.pagination.has_next, true);
    assert.equal(byCall.matches[0].location.transcript_line, 3);
    assert.match(byCall.matches[0].location.raw_ref, /#L3$/u);

    const byPath = await queryTrace({
      traceIndex, path: "/tmp_workspace", page: 1, pageSize: 50,
    });
    assert.equal(byPath.pagination.total_matches, 2);
    const byText = await queryTrace({
      traceIndex, text: "3 TESTS ok", page: 1, pageSize: 50,
    });
    assert.equal(byText.pagination.total_matches, 1);
    assert.equal(byText.matches[0].type, "tool_result");
    const byRange = await queryTrace({
      traceIndex, fromSequence: 2, toSequence: 3, page: 1, pageSize: 50,
    });
    assert.deepEqual(byRange.matches.map((item) => item.sequence), [2, 3]);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("missing native boundaries and tool results remain partial instead of pretending complete", async () => {
  const fixture = await createFixture();
  try {
    const database = new DatabaseSync(fixture.stateDatabase, { readOnly: true });
    const rows = database.prepare(`
SELECT sequence,event_id,thread_id,turn_id,lifecycle_generation,event_type,event_json,persisted_at
FROM provider_runtime_events WHERE thread_id=? AND turn_id=? ORDER BY sequence
`).all(THREAD_ID, TURN_ID).map((row) => ({ ...row, event: JSON.parse(row.event_json) }));
    database.close();
    const incomplete = rows.filter((row) => !new Set(["turn.completed", "event-result"]).has(
      row.event_type === "turn.completed" ? "turn.completed" : row.event_id,
    ));
    const normalized = normalizeTraceRows(incomplete, fixture.state);
    assert.equal(normalized.completeness.status, "partial");
    assert.ok(normalized.completeness.missing.includes("turn.completed"));
    assert.ok(normalized.completeness.missing.includes("tool_result:call-command-1"));
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("provider session mismatch fails closed", async () => {
  const fixture = await createFixture();
  try {
    const database = new DatabaseSync(fixture.stateDatabase);
    const row = database.prepare("SELECT event_json FROM provider_runtime_events WHERE event_id=?")
      .get("event-result");
    const event = JSON.parse(row.event_json);
    event.providerRefs.providerThreadId = "wrong-provider-session";
    database.prepare("UPDATE provider_runtime_events SET event_json=? WHERE event_id=?")
      .run(JSON.stringify(event), "event-result");
    database.close();
    await assert.rejects(
      archiveAstronStudioTrace({
        stateFile: fixture.stateFile,
        stateDb: fixture.stateDatabase,
        outputDir: fixture.outputDir,
        replace: false,
      }),
      /PROVIDER_SESSION_MISMATCH/u,
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("query refuses a transcript changed after indexing", async () => {
  const fixture = await createFixture();
  try {
    await archiveAstronStudioTrace({
      stateFile: fixture.stateFile,
      stateDb: fixture.stateDatabase,
      outputDir: fixture.outputDir,
      replace: false,
    });
    await writeFile(join(fixture.outputDir, "transcript.jsonl"), "{}\n", "utf8");
    await assert.rejects(
      queryTrace({
        traceIndex: join(fixture.outputDir, "trace-index.json"), page: 1, pageSize: 50,
      }),
      /TRANSCRIPT_ARTIFACT_MISMATCH/u,
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});
