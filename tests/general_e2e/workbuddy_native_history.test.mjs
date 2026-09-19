import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { cp, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";

import {
  assertSafeWorkBuddyNativeId,
  collectWorkBuddyGeneralEvidence,
  findWorkBuddyWorkspaceHistory,
  loadWorkBuddyConversation,
  normalizeWorkBuddyConversation,
  toGeneralResourceMetrics,
  workBuddyWorkspaceHistoryKey,
} from "../../eval_general_e2e/adapters/workbuddy/native-history.mjs";

const REPO_ROOT = resolve(dirname(new URL(import.meta.url).pathname), "../..");
const FIXTURE_ROOT = join(REPO_ROOT, "tests/general_e2e/fixtures/workbuddy/native-history");
const IDENTITY = Object.freeze({
  batch_id: "fixture-batch",
  unit_id: "fixture-unit",
  task_id: "fixture-task",
  attempt_id: "fixture-attempt",
});
const CONVERSATION_ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const REQUEST_ID = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

async function createNativeHistoryFixture() {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-native-history-test-"));
  let workspace = join(root, "candidate", "workspace");
  const dataRoot = join(root, "WorkBuddyExtension", "Data");
  await mkdir(workspace, { recursive: true });
  workspace = await realpath(workspace);
  const historyKey = workBuddyWorkspaceHistoryKey(workspace);
  const historyRoot = join(
    dataRoot,
    "account-fixture",
    "VSCode",
    "identity-fixture",
    "history",
    historyKey,
  );
  const conversationRoot = join(historyRoot, CONVERSATION_ID);
  await mkdir(join(conversationRoot, "messages"), { recursive: true });
  await cp(join(FIXTURE_ROOT, "workspace-index.json"), join(historyRoot, "index.json"));
  await cp(join(FIXTURE_ROOT, "conversation-index.json"), join(conversationRoot, "index.json"));
  await cp(join(FIXTURE_ROOT, "messages"), join(conversationRoot, "messages"), { recursive: true, force: true });
  return { root, workspace, dataRoot, historyKey, historyRoot, conversationRoot };
}

test("WorkBuddy history layout binds exact workspace, conversation, and request", async () => {
  const fixture = await createNativeHistoryFixture();
  try {
    const located = await findWorkBuddyWorkspaceHistory(fixture);
    assert.equal(located.workspace_history_key, fixture.historyKey);
    assert.equal(located.history_directory, await realpath(fixture.historyRoot));
    const loaded = await loadWorkBuddyConversation({
      ...fixture,
      conversationId: CONVERSATION_ID,
      requestId: REQUEST_ID,
    });
    assert.equal(loaded.messages.length, 4);
    assert.deepEqual(loaded.messages.map((item) => item.envelope.role), [
      "user",
      "assistant",
      "tool",
      "assistant",
    ]);
    assert.equal(loaded.request.state, "complete");
    const conversationBytes = await readFile(join(fixture.conversationRoot, "index.json"));
    assert.equal(
      loaded.source_artifacts.conversation_index.sha256,
      createHash("sha256").update(conversationBytes).digest("hex"),
    );
    assert.equal(loaded.source_artifacts.messages.length, 4);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy history normalizes transcript, calls, resources, and coverage", async () => {
  const fixture = await createNativeHistoryFixture();
  try {
    const loaded = await loadWorkBuddyConversation({
      ...fixture,
      conversationId: CONVERSATION_ID,
      requestId: REQUEST_ID,
    });
    const normalized = normalizeWorkBuddyConversation(loaded, { identity: IDENTITY, redacted: true });
    assert.equal(normalized.completeness.status, "complete");
    assert.deepEqual(normalized.events.map((item) => item.type), [
      "user_message",
      "tool_call",
      "tool_result",
      "assistant_message",
    ]);
    assert.equal(normalized.calls.length, 1);
    assert.equal(normalized.calls[0].call_sequence, 1);
    assert.equal(normalized.calls[0].result_sequence, 2);
    assert.equal(normalized.final_response, "The synthetic fixture output is ready.");
    assert.equal(normalized.resources.primary_request.input_tokens.value, 120);
    assert.equal(normalized.resources.primary_request.request_count.value, 1);
    assert.equal(normalized.resources.primary_request.request_attempt_count.value, null);
    assert.equal(normalized.resources.primary_request.request_attempt_count.status, "unavailable");
    assert.equal(normalized.resources.primary_request.cache_read_input_tokens.value, null);
    assert.deepEqual(normalized.resources.primary_request.cache_read_input_tokens.coverage, {
      known: 0,
      total: 1,
      unit: "conversation_request",
    });
    assert.equal(normalized.resources.primary_request.cache_read_input_tokens.known_subtotal, 0);
    assert.equal(normalized.resources.linked_tool_usage.credit.value, 1.25);
    assert.equal(normalized.resources.linked_tool_usage.credit.status, "unverified");
    assert.equal(normalized.resources.cache_semantics.all_observed_checks_pass, true);
    assert.deepEqual(
      normalized.resources.tool_outcomes.map((item) => [item.scope, item.status]),
      [["conversation", "success"], ["linked-child", "unknown"]],
    );

    const resourceMetrics = toGeneralResourceMetrics({
      identity: IDENTITY,
      observation: normalized.resources,
      sourceArtifact: {
        path: "trace/raw/workbuddy-native-history.json",
        sha256: "a".repeat(64),
        size: 1234,
      },
      collectedAt: "2026-09-19T08:01:00.000Z",
    });
    assert.equal(resourceMetrics.collection.status, "partial");
    assert.equal(resourceMetrics.metrics.usage.input_tokens.value, 120);
    assert.equal(resourceMetrics.metrics.usage.cache_read_input_tokens.value, null);
    assert.equal(resourceMetrics.metrics.usage.cache_read_input_tokens.status, "unavailable");
    assert.equal(resourceMetrics.metrics.requests.request_count.value, 1);
    assert.equal(resourceMetrics.metrics.requests.request_attempt_count.value, null);
    assert.deepEqual(resourceMetrics.collection.known_subtotals, {});

    const validation = spawnSync(
      process.env.PYTHON || "python3",
      [
        "-c",
        "import json,sys; from eval_general_e2e.contracts.validator import validate_contract; validate_contract(json.load(sys.stdin))",
      ],
      {
        cwd: REPO_ROOT,
        encoding: "utf8",
        input: JSON.stringify(resourceMetrics),
      },
    );
    assert.equal(validation.status, 0, validation.stderr);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy collector emits CB-B trace-index v2 with multiple raw and binding artifacts", async () => {
  const fixture = await createNativeHistoryFixture();
  try {
    const loaded = await loadWorkBuddyConversation({
      ...fixture,
      conversationId: CONVERSATION_ID,
      requestId: REQUEST_ID,
    });
    const normalized = normalizeWorkBuddyConversation(loaded, { identity: IDENTITY, redacted: true });
    const bindingSource = join(fixture.root, "automation-state.json");
    await writeFile(bindingSource, JSON.stringify({
      schema_id: "wildclawbench.general-e2e-execution-state/v1",
      session_id: CONVERSATION_ID,
      cwd: fixture.workspace,
    }) + "\n", "utf8");
    const bindingBytes = await readFile(bindingSource);
    const outputRoot = join(fixture.root, "trace");
    const result = await collectWorkBuddyGeneralEvidence({
      identity: IDENTITY,
      loaded,
      normalized,
      outputRoot,
      bindingSources: [{ source: { path: bindingSource, sha256: createHash("sha256").update(bindingBytes).digest("hex"), size: bindingBytes.length }, target: "bindings/automation-state.json" }],
      writeResourceMetrics: true,
      collectedAt: "2026-09-19T08:01:00.000Z",
    });
    assert.equal(result.trace_index.schema_id, "urn:wildclawbench:schema:general-e2e:trace-index:v2");
    assert.equal(result.trace_index.schema_version, 2);
    assert.equal(result.trace_index.session.thread_id, null);
    assert.equal(result.trace_index.session.turn_id, REQUEST_ID);
    assert.equal(result.trace_index.session.session_id, CONVERSATION_ID);
    assert.equal(result.trace_index.session.cwd, fixture.workspace);
    assert.equal(result.trace_index.raw_trace.length, 6);
    assert.equal(result.trace_index.binding_evidence.length, 1);
    assert.equal(result.trace_index.transcript.event_count, normalized.events.length);
    assert.equal(result.trace_index.normalization.native_event_count, normalized.events.length);
    assert.equal(result.resource_metrics.collection.status, "partial");
    for (const relativePath of [
      "trace-index.json",
      "transcript.jsonl",
      "raw/workbuddy-history/workspace-index.json",
      "raw/workbuddy-history/conversation-index.json",
      "bindings/automation-state.json",
      "resource-metrics.json",
    ]) assert.ok((await readFile(join(outputRoot, relativePath))).length > 0, relativePath);
    for (const artifact of result.raw_trace) {
      assert.ok((await readFile(join(outputRoot, artifact.path))).length > 0, artifact.path);
    }
    const validation = spawnSync(
      process.env.PYTHON || "python3",
      ["-c", "import json,sys; from eval_general_e2e.contracts.validator import validate_contract; validate_contract(json.load(sys.stdin))"],
      { cwd: REPO_ROOT, encoding: "utf8", input: JSON.stringify(result.trace_index) },
    );
    assert.equal(validation.status, 0, validation.stderr);
    const resourceValidation = spawnSync(
      process.env.PYTHON || "python3",
      ["-c", "import json,sys; from eval_general_e2e.contracts.validator import validate_contract; validate_contract(json.load(sys.stdin))"],
      { cwd: REPO_ROOT, encoding: "utf8", input: JSON.stringify(result.resource_metrics) },
    );
    assert.equal(resourceValidation.status, 0, resourceValidation.stderr);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy history fails closed on cross-request and incomplete evidence", async () => {
  const fixture = await createNativeHistoryFixture();
  try {
    const userMessage = join(
      fixture.conversationRoot,
      "messages",
      "cccccccccccccccccccccccccccccccc.json",
    );
    const value = JSON.parse(await readFile(userMessage, "utf8"));
    value.extra = JSON.stringify({ requestId: "different-request" });
    await writeFile(userMessage, `${JSON.stringify(value, null, 2)}\n`, "utf8");
    await assert.rejects(
      loadWorkBuddyConversation({
        ...fixture,
        conversationId: CONVERSATION_ID,
        requestId: REQUEST_ID,
      }),
      /requestId 不匹配/u,
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy history rejects path escape IDs and symlinked sources", async () => {
  assert.throws(() => assertSafeWorkBuddyNativeId("../escape", "conversationId"), /安全/u);
  assert.throws(() => assertSafeWorkBuddyNativeId("C:escape", "conversationId"), /安全/u);
  assert.throws(() => assertSafeWorkBuddyNativeId("a\\b", "messageId"), /安全/u);

  const fixture = await createNativeHistoryFixture();
  try {
    await assert.rejects(
      loadWorkBuddyConversation({
        ...fixture,
        conversationId: "../escape",
        requestId: REQUEST_ID,
      }),
      /安全/u,
    );

    const external = join(fixture.root, "external-index.json");
    await writeFile(external, await readFile(join(fixture.conversationRoot, "index.json")));
    await rm(join(fixture.conversationRoot, "index.json"));
    await symlink(external, join(fixture.conversationRoot, "index.json"));
    await assert.rejects(
      loadWorkBuddyConversation({
        ...fixture,
        conversationId: CONVERSATION_ID,
        requestId: REQUEST_ID,
      }),
      /符号链接/u,
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }

  const ancestorFixture = await createNativeHistoryFixture();
  try {
    const externalConversation = join(ancestorFixture.root, "external-conversation");
    await cp(ancestorFixture.conversationRoot, externalConversation, { recursive: true });
    await rm(ancestorFixture.conversationRoot, { recursive: true, force: true });
    await symlink(externalConversation, ancestorFixture.conversationRoot);
    await assert.rejects(
      loadWorkBuddyConversation({
        ...ancestorFixture,
        conversationId: CONVERSATION_ID,
        requestId: REQUEST_ID,
      }),
      /符号链接/u,
    );
  } finally {
    await rm(ancestorFixture.root, { recursive: true, force: true });
  }
});
