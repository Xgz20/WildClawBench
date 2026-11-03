import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseBoundJsonl, applyJsonlMetrics, artifact, jsonBytes, verifySupplement, discoverJsonl,
  withoutModelResponseCount } from "../../tools/report/e2e-shared/workbuddy-jsonl-metrics/index.mjs";
import { supplementWorkBuddyResources } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/workbuddy/supplement-resources.mjs";
import { supplementWorkBuddyTiming } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/workbuddy/supplement-timing.mjs";
import { workBuddyTiming, verifyTimingSupplement } from "../../tools/report/e2e-shared/workbuddy-jsonl-metrics/timing.mjs";
import { collectWorkBuddyEvidence } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/workbuddy/collector.mjs";
import { finalizeGeneralExecution } from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/finalize_general_execution.mjs";
import { fixtureHook } from "./helpers/general-collection-fixture.mjs";
import { buildWorkBuddyRuntimeSnapshot, loadWorkBuddyRuntimeConversation } from "../../tools/report/e2e-shared/workbuddy-evidence/runtime-api.mjs";
import { normalizeWorkBuddyConversation, toGeneralResourceMetrics } from "../../tools/report/e2e-shared/workbuddy-evidence/native-history.mjs";

const hash = x => createHash("sha256").update(x).digest("hex");
function fixture(workspace = "/fixture/workspace") {
  const identity = { batch_id: "batch", unit_id: "unit", task_id: "task", attempt_id: "attempt" };
  const session = { thread_id: null, session_id: "conversation-fixture", turn_id: "request-fixture", cwd: workspace, verified: true };
  const prompt = "Do the fixture task.";
  const snapshot = buildWorkBuddyRuntimeSnapshot({
    conversation: { id: session.session_id, space: { cwd: session.cwd }, state: "idle", lifecycle: "active" },
    request: { id: session.turn_id, traceId: "trace-fixture", state: "completed", timestamp: Date.parse("2026-09-21T00:00:01Z"),
      userMessage: { state: "completed", content: [{ type: "text", text: prompt }] },
      assistantMessage: { state: "completed", content: [
        ...["call-1", "call-2"].map(toolCallId => ({ type: "tool", toolCallId, title: "Read", status: "completed" })),
        { type: "text", text: "Done." },
      ] }, usage: {}, completedAt: Date.parse("2026-09-21T00:00:05Z"), finishTimestamp: Date.parse("2026-09-21T00:00:04.980Z") },
    requestEntries: { totalRequests: 1, historyReady: true }, capturedAt: "2026-09-21T00:00:00Z",
  });
  const usage = (input, output) => ({ requests: 1, inputTokens: input, outputTokens: output, totalTokens: input + output,
    inputTokensDetails: [{ cached_tokens: input - 10 }], outputTokensDetails: [{ reasoning_tokens: 0 }] });
  const provider = (id, input, output) => ({ messageId: id, conversationRequestId: "trace-fixture", usage: usage(input, output),
    rawUsage: { prompt_tokens: input, completion_tokens: output, total_tokens: input + output, prompt_tokens_details: { cached_tokens: input - 10 } } });
  const row = x => ({ sessionId: session.session_id, cwd: session.cwd, ...x });
  const rows = [
    row({ type: "message", id: "user", role: "user", content: [{ type: "input_text", text: `<system-reminder>context</system-reminder>\n<user_query>${prompt}</user_query>` }] }),
    row({ type: "function_call", id: "response1", callId: "call-1", name: "Read", providerData: provider("response1", 100, 20) }),
    row({ type: "function_call", id: "response1", callId: "call-2", name: "Read", providerData: { messageId: "response1", conversationRequestId: "trace-fixture" } }),
    row({ type: "message", id: "response2", role: "assistant", content: [{ type: "output_text", text: "Done." }], providerData: provider("response2", 200, 30) }),
  ];
  const options = { snapshot, session, promptSha256: hash(prompt) };
  const bytes = () => Buffer.from(rows.map(x => JSON.stringify(x)).join("\n") + "\n");
  const loaded = loadWorkBuddyRuntimeConversation({ snapshot });
  const observation = normalizeWorkBuddyConversation(loaded, { identity }).resources;
  const base = toGeneralResourceMetrics({ identity, observation, sourceArtifact: artifact("trace-index.json", Buffer.from("{}")), collectedAt: "2026-09-21T00:00:00Z" });
  return { rows, options, bytes, base, identity, snapshot, session };
}

function orphanFixture() {
  const f = fixture(); f.snapshot.request.conversationRequestId = f.session.turn_id;
  for (const row of f.rows.filter(x => x.providerData?.messageId)) {
    row.providerData.conversationRequestId = f.session.turn_id; row.providerData.traceId = f.snapshot.request.traceId;
  }
  const response = "response-orphan";
  const tool = { type: "tool", sessionUpdate: "tool_call_update", toolCallId: "call-orphan", title: "present", status: "cancelled",
    rawInput: { files: "[]" }, _meta: { toolCancelReason: "orphan_pending_history", "codebuddy.ai/toolName": "present",
      "codebuddy.ai/requestId": f.session.turn_id, "codebuddy.ai/conversationRequestId": f.session.turn_id,
      "codebuddy.ai/llmMessageId": response, "codebuddy.ai/modelRequestId": response,
      "codebuddy.ai/traceId": f.snapshot.request.traceId, "codebuddy.ai/responseModelId": "fixture-model" } };
  f.snapshot.request.assistantMessage.content.splice(2, 0, tool);
  const row = { type: "model-usage", id: "usage-record", parentId: "model-parent", timestamp: 100, cwd: f.session.cwd,
    _meta: { baggage: `codebuddy.session_id=${f.session.session_id},codebuddy.conversation_request_id=${f.session.turn_id}` },
    providerData: { conversationRequestId: f.session.turn_id, messageId: response, traceId: f.snapshot.request.traceId, model: "fixture-model",
      usage: { requests: 1, inputTokens: 50, outputTokens: 5, totalTokens: 55,
        inputTokensDetails: [{ cached_tokens: 40 }], outputTokensDetails: [{ reasoning_tokens: 0 }] },
      rawUsage: { prompt_tokens: 50, completion_tokens: 5, total_tokens: 55, prompt_tokens_details: { cached_tokens: 40 } } } };
  f.rows.push(row);
  const error = { type: "message", role: "assistant", id: "admission-error", parentId: "model-parent", timestamp: 101,
    sessionId: f.session.session_id, cwd: f.session.cwd,
    content: [{ type: "output_text", text: 'Tool "present" does not exist in the current tool set.' }],
    providerData: { skipRun: true, agent: "cli", conversationRequestId: f.session.turn_id,
      error: { message: 'Tool "present" does not exist in the current tool set.', isNetworkError: false, isStreamTimeout: false, isRetryable: true } } };
  f.rows.push(error);
  return { ...f, orphan: tool, usageOnly: row, admissionError: error };
}

function runtimeCommentFixture() {
  const f = orphanFixture();
  const final = f.rows.splice(f.rows.findIndex(r => r.id === "response2"), 1)[0];
  f.rows.splice(f.rows.indexOf(f.usageOnly), 0, { type: "function_call_result", id: "model-parent",
    callId: "call-2", name: "Read", status: "completed", output: { type: "text", text: "ok" },
    sessionId: f.session.session_id, cwd: f.session.cwd });
  f.rows.push(final);
  const comment = { type: "text", messageId: "runtime-only-comment", text: "现在提交结果。" };
  const content = f.snapshot.request.assistantMessage.content;
  content.splice(content.indexOf(f.orphan), 0, comment);
  content.at(-1).messageId = "response2";
  return { ...f, comment };
}

test("bound rejected response keeps runtime-only intermediate comment and original SDK bytes", () => {
  const f = runtimeCommentFixture(), before = f.bytes();
  const result = parseBoundJsonl(before, f.options);
  assert.ok(result.collection.warnings.some(w => w.startsWith("WORKBUDDY_RUNTIME_ONLY_ADMISSION_COMMENT_V1:")));
  assert.equal(f.snapshot.request.assistantMessage.content.includes(f.comment), true);
  assert.equal(f.comment.text, "现在提交结果。");
  assert.equal(result.usage.total_tokens, 405);
  assert.equal(result.tools.call_count, null);
  assert.deepEqual(before, f.bytes());
});

test("runtime-only comment cannot hide missing final text, wrong result anchors or foreign SDK IDs", () => {
  for (const mutate of [
    f => { f.snapshot.request.assistantMessage.content.at(-1).text = "changed final"; },
    f => { f.snapshot.request.assistantMessage.content.at(-1).messageId = "foreign-final"; },
    f => { f.rows.find(r => r.id === "model-parent").callId = "foreign-call"; },
    f => { f.rows.find(r => r.id === "model-parent").status = "failed"; },
    f => { f.comment.messageId = "user"; },
    f => { f.snapshot.request.assistantMessage.content.splice(0, 0, f.comment); },
  ]) {
    const f = runtimeCommentFixture(); mutate(f);
    assert.throws(() => parseBoundJsonl(f.bytes(), f.options));
  }
});

test("an unbound additional runtime statement remains a strict response mismatch", () => {
  const f = fixture(); f.snapshot.request.assistantMessage.content.unshift({ type: "text", text: "unbound extra text" });
  assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /FINAL_RESPONSE_MISMATCH/);
});

test("bound cancelled orphan and usage-only metadata preserve content and unknown invocation total", () => {
  const f = orphanFixture(), bytes = f.bytes();
  const parsed = parseBoundJsonl(bytes, f.options);
  assert.equal(parsed.usage.request_count, 3);
  assert.equal(parsed.usage.total_tokens, 405);
  assert.equal(parsed.tools.call_count, null);
  assert.equal(parsed.collection.known_subtotals.call_count, 2);
  assert.deepEqual(parsed.collection.field_coverage.call_count, { known: 2, total: 3, unit: "tool_call" });
  assert.deepEqual(bytes, f.bytes());
  const metrics = applyJsonlMetrics(f.base, parsed, artifact("native.jsonl", bytes));
  assert.equal(metrics.metrics.tools.call_count.status, "partial");
  assert.equal(metrics.metrics.tools.call_count.value, null);
  assert.deepEqual(metrics.collection.coverage.call_count, { known: 2, total: 3, unit: "tool_call" });
  assert.equal(metrics.collection.known_subtotals.call_count, 2);
  assert.ok(f.base.collection.metric_sources.call_count.every(ref => metrics.collection.metric_sources.call_count.includes(ref)));
  assert.ok(metrics.collection.metric_sources.call_count.includes("native.jsonl"));
});

test("legacy usage-only records with explicit session and exact trace binding retain their counters", () => {
  const f = fixture(), usage = orphanFixture().usageOnly;
  usage.sessionId = f.session.session_id; usage.cwd = f.session.cwd; delete usage._meta;
  usage.providerData.conversationRequestId = f.snapshot.request.traceId;
  f.rows.push(usage);
  const result = parseBoundJsonl(f.bytes(), f.options);
  assert.equal(result.usage.total_tokens, 405);
  assert.equal(result.usage.request_count, 3);
  assert.equal(result.tools.call_count, 2);
  assert.equal(result.collection.warnings.some(x => x.startsWith("WORKBUDDY_CANCELLED_ORPHAN_TOOL")), false);
});

test("orphan compatibility cannot hide active tools, fabricated results, foreign usage or conflicting tokens", () => {
  for (const mutate of [
    f => { f.orphan.status = "in_progress"; },
    f => { f.orphan._meta.toolCancelReason = "unknown"; },
    f => { f.orphan._meta["codebuddy.ai/modelRequestId"] = "other"; },
    f => { f.orphan.rawOutput = "fabricated output"; },
    f => { f.usageOnly.cwd = "/foreign"; },
    f => { f.usageOnly.providerData.conversationRequestId = "foreign"; },
    f => { f.usageOnly._meta.baggage = "codebuddy.session_id=foreign,codebuddy.conversation_request_id=request-fixture"; },
    f => { f.usageOnly.providerData.rawUsage.total_tokens++; },
    f => { f.admissionError.parentId = "foreign-parent"; },
    f => { f.admissionError.providerData.skipRun = false; },
    f => { f.admissionError.providerData.error.isNetworkError = true; },
  ]) {
    const f = orphanFixture(); mutate(f);
    assert.throws(() => parseBoundJsonl(f.bytes(), f.options));
  }
});

test("WorkBuddy JSONL counts model responses once across multiple tools and mirrored usage fields", () => {
  const f = fixture(); f.rows.splice(2, 0, structuredClone(f.rows[1]));
  const parsed = parseBoundJsonl(f.bytes(), f.options);
  assert.equal(parsed.usage.request_count, 2);
  assert.equal(parsed.tools.call_count, 2);
  assert.equal(parsed.usage.total_tokens, 350);
  assert.equal(parsed.usage.cache_read_input_tokens, 280);
  assert.equal(parsed.usage.request_attempt_count, null);
  const metric = applyJsonlMetrics(f.base, parsed, artifact("native.jsonl", f.bytes()));
  assert.equal(metric.metrics.requests.request_count.value, 2);
  assert.equal(metric.metrics.usage.input_tokens.value, 300);
  assert.equal(metric.metrics.usage.total_tokens.value, 350);
  assert.equal(withoutModelResponseCount(f.base).metrics.requests.request_count.value, null);
});

test("explicit conversation request IDs remain distinct from distributed trace IDs", () => {
  const f = fixture();
  f.snapshot.request.conversationRequestId = f.snapshot.request.id;
  for (const row of f.rows.filter(x => x.providerData?.messageId)) {
    row.providerData.conversationRequestId = f.snapshot.request.id;
    row.providerData.traceId = f.snapshot.request.traceId;
  }
  const parsed = parseBoundJsonl(f.bytes(), f.options);
  assert.equal(parsed.usage.total_tokens, 350);
  assert.equal(parsed.usage.request_count, 2);
  assert.equal(parsed.tools.call_count, 2);
  assert.ok(parsed.collection.warnings.some(x => x.startsWith("WORKBUDDY_REQUEST_SCOPE_BINDING_V2")));
  f.rows[1].providerData.conversationRequestId = f.snapshot.request.traceId;
  assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /REQUEST_SCOPE_MISMATCH/u);
  f.rows[1].providerData.conversationRequestId = f.snapshot.request.id;
  f.rows[1].providerData.traceId = "unrelated-distributed-trace";
  assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /REQUEST_SCOPE_MISMATCH/u);
  f.rows[1].providerData.traceId = f.snapshot.request.traceId;
  f.snapshot.request.conversationRequestId = "unrelated-request";
  assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /RUNTIME_REQUEST_SCOPE_MISMATCH/u);
});

test("legacy trace-ID bindings retain identical metrics even when snapshots carry another conversationRequestId", () => {
  const f = fixture();
  const original = parseBoundJsonl(f.bytes(), f.options);
  f.snapshot.request.conversationRequestId = "legacy-secondary-runtime-id";
  const retained = parseBoundJsonl(f.bytes(), f.options);
  assert.deepEqual(retained, original);
  assert.equal(retained.collection.warnings.some(x => x.startsWith("WORKBUDDY_REQUEST_SCOPE_BINDING_V2")), false);
});

test("bound native compaction internal messages do not become extra human prompts", () => {
  const f = fixture();
  f.rows.splice(3, 0, ...["summary", "continuation"].map(id => ({
    type: "message", role: "user", id, sessionId: f.session.session_id, cwd: f.session.cwd,
    content: [{ type: "input_text", text: "Internal compaction content" }],
    providerData: { isCompactInternal: true, skipRun: false, agent: "cli", conversationRequestId: f.session.turn_id },
  })));
  const original = f.bytes();
  const p = parseBoundJsonl(original, f.options);
  assert.equal(p.usage.request_count, 2);
  assert.equal(p.usage.total_tokens, 350);
  assert.deepEqual(f.bytes(), original);
  assert.ok(p.collection.warnings.some(x => x.startsWith("WORKBUDDY_COMPACTION_INTERNAL_USER_V1")));
  f.rows[3].providerData.startsNewUserRequest = true;
  assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /COMPACTION_USER_BINDING_MISMATCH/u);
  delete f.rows[3].providerData.startsNewUserRequest;
  f.rows[3].providerData.conversationRequestId = "foreign-request";
  assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /COMPACTION_USER_BINDING_MISMATCH/u);
  f.rows[3].providerData.conversationRequestId = f.session.turn_id;
  delete f.rows[3].providerData.isCompactInternal;
  assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /USER_TURN_MISMATCH/u);
});

test("WorkBuddy fresh collector archives JSONL and passes the formal finalizer with corrected counters", async () => {
  const root = await mkdtemp(join(tmpdir(), "wb-jsonl-collect-"));
  try {
    const { realpath } = await import("node:fs/promises");
    const unit = await realpath(root), taskRoot = join(unit, "execution/tasks/task"), cwd = join(taskRoot, "workspace");
    await mkdir(cwd, { recursive: true }); const f = fixture(cwd);
    const put = async (p, value) => { await mkdir(join(p, ".."), { recursive: true }); await writeFile(p, jsonBytes(value)); };
    const promptPath = join(taskRoot, "PROMPT.md"); await writeFile(promptPath, "Do the fixture task.");
    const dataset = { id: "dataset", digest: "d".repeat(64) };
    await put(join(unit, "manifest.json"), { schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1", schema_version: 1,
      manifest_kind: "execution", batch_id: "batch", unit_id: "unit", dataset, task_ids: ["task"],
      unit: { harness: { id: "workbuddy", platform: "macos", version: "5.5.6" }, model: { requested_id: "fixture", reasoning_effort: null } },
      tasks: [{ task_id: "task", workspace: { path: "execution/tasks/task/workspace" }, prompt: { path: "execution/tasks/task/PROMPT.md", sent_sha256: f.options.promptSha256 } }] });
    const binding = jsonBytes({ schema_version: "wildclawbench.general-e2e-workbuddy-native-binding/v2", source_kind: "workbuddy-runtime-api",
      identity: f.identity, workspace: cwd, conversation_id: f.session.session_id, request_id: f.session.turn_id, runtime_snapshot: f.snapshot, source_artifacts: [] });
    await writeFile(join(taskRoot, "binding.json"), binding);
    const state = { schema_version: "wildclawbench.general-e2e-execution-state/v1", driver: { id: "workbuddy-macos-general", version: "0.4.0", harness: "workbuddy", platform: "macos" },
      identity: f.identity, dataset, phase: "COMPLETED", task_root: taskRoot, candidate_workspace: cwd,
      prompt: { path: promptPath, sha256: f.options.promptSha256, send_status: "sent", sent_at: "2026-09-21T00:00:00Z" }, send: { dispatch_attempt_count: 1 },
      session: { ...f.session, binding_evidence: [artifact("execution/tasks/task/binding.json", binding)] },
      execution: { business_status: "completed", started_at: "2026-09-21T00:00:00Z", finished_at: "2026-09-21T00:00:05Z", duration_seconds: 5, error: null, cancellation_confirmed: null },
      human_assistance: { mode: "automatic", operation_count: 0, semantic_intervention_count: 0 },
      extensions: { workbuddy: { identity_mapping: { binding_source: "workbuddy-runtime-api", turn_id_source: "runtime.conversations.current.requestEntries().requests[].id",
        session_id_source: "runtime.conversations.current.info.id", cwd_source: "runtime.conversations.current.info.space.cwd",
        terminal_status_source: "runtime.conversations.current.info.state/lifecycle + requestEntries().requests[].state + message.state" } } } };
    const statePath = join(unit, "state.json"), journalPath = join(unit, "journal.json");
    await put(statePath, state);
    await put(journalPath, { ...state, schema_version: "wildclawbench.general-e2e-workbuddy-dispatch-journal/v1", native: { conversation_id: f.session.session_id, request_id: f.session.turn_id, cwd } });
    const nativeRoot = join(unit, "native-projects"); await mkdir(join(nativeRoot, "w"), { recursive: true });
    await writeFile(join(nativeRoot, "w", f.session.session_id + ".jsonl"), f.bytes());
    const collected = await collectWorkBuddyEvidence({ unitRoot: unit, journalFile: journalPath, stateFile: statePath, nativeProjectsRoot: nativeRoot, outputRoot: join(unit, ".general-e2e/collection/attempt") });
    const metrics = JSON.parse(await readFile(collected.resource_metrics));
    assert.equal(metrics.metrics.requests.request_count.value, 2);
    assert.equal(metrics.metrics.usage.total_tokens.value, 350);
    assert.equal(metrics.metrics.timing.duration_seconds.value, 5);
    assert.equal(metrics.metrics.timing.agent_duration_seconds.value, 4);
    const finalized = await finalizeGeneralExecution({ unitRoot: unit, stateFile: collected.state_file, traceIndex: collected.trace_index,
      resourceMetrics: collected.resource_metrics, pythonExecutable: process.env.PYTHON || "python3", stabilityMilliseconds: 1, processQuietMilliseconds: 5, processWaitMilliseconds: 50 }, { processCleanup: fixtureHook("workbuddy") });
    assert.equal(finalized.status, "PASS");
    const missing = await collectWorkBuddyEvidence({ unitRoot: unit, journalFile: journalPath, stateFile: statePath,
      nativeProjectsRoot: join(unit, "missing"), outputRoot: join(unit, ".general-e2e/collection/no-jsonl") });
    const withoutJsonl = JSON.parse(await readFile(missing.resource_metrics));
    assert.equal(withoutJsonl.metrics.requests.request_count.value, null);
    assert.equal(withoutJsonl.metrics.timing.agent_duration_seconds.value, 4);
    const mirror = fixture(cwd);
    mirror.rows[3].providerData.rawUsage = { inputTokens: 0, outputTokens: 0, totalTokens: 0,
      inputTokensDetails: { cached_tokens: 0 }, outputTokensDetails: { reasoning_tokens: 0 } };
    mirror.rows[3].providerData.usage = { requests: 1, inputTokens: 0, outputTokens: 0, totalTokens: 0,
      inputTokensDetails: [{ cached_tokens: 0 }], outputTokensDetails: [{ reasoning_tokens: 0 }] };
    const mirrorRoot = join(unit, "native-mirror");
    await mkdir(join(mirrorRoot, "w"), { recursive: true });
    await writeFile(join(mirrorRoot, "w", f.session.session_id + ".jsonl"), mirror.bytes());
    const mirrored = await collectWorkBuddyEvidence({ unitRoot: unit, journalFile: journalPath, stateFile: statePath,
      nativeProjectsRoot: mirrorRoot, outputRoot: join(unit, ".general-e2e/collection/normalized-mirror") });
    assert.equal(mirrored.status, "PASS");
    const mirrorMetrics = JSON.parse(await readFile(mirrored.resource_metrics));
    assert.equal(mirrorMetrics.metrics.usage.total_tokens.value, null);
    assert.equal(mirrorMetrics.metrics.usage.total_tokens.status, "partial");
    assert.equal(mirrorMetrics.collection.known_subtotals.total_tokens, 120);
    assert.deepEqual(await readFile(join(mirrored.output_root, "trace/raw/workbuddy-session.jsonl")), mirror.bytes());
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("WorkBuddy JSONL preserves unknown coverage and observed zero without inventing usage", () => {
  const f = fixture(); delete f.rows[3].providerData.usage; delete f.rows[3].providerData.rawUsage;
  const parsed = parseBoundJsonl(f.bytes(), f.options);
  const metric = applyJsonlMetrics(f.base, parsed, artifact("native.jsonl", f.bytes()));
  assert.equal(metric.metrics.usage.total_tokens.value, null);
  assert.equal(metric.collection.known_subtotals.total_tokens, 120);
  assert.deepEqual(metric.collection.coverage.total_tokens, { known: 1, total: 2, unit: "model_response" });
  assert.equal(metric.metrics.requests.request_count.value, 2);
  assert.equal(metric.metrics.usage.cache_creation_input_tokens.value, null);
  assert.equal(parseBoundJsonl(fixture().bytes(), fixture().options).usage.reasoning_output_tokens, null);
  const explicit = fixture();
  for (const row of explicit.rows.filter(x => x.providerData?.rawUsage)) row.providerData.rawUsage.completion_tokens_details = { reasoning_tokens: 0 };
  assert.equal(parseBoundJsonl(explicit.bytes(), explicit.options).usage.reasoning_output_tokens, 0);
});

test("normalized-only zero usage keeps complete content and partial measured token coverage", () => {
  const f = fixture();
  const pd = f.rows[3].providerData;
  pd.rawUsage = { inputTokens: 0, outputTokens: 0, totalTokens: 0,
    inputTokensDetails: { cached_tokens: 0 }, outputTokensDetails: { reasoning_tokens: 0 } };
  pd.usage = { requests: 1, inputTokens: 0, outputTokens: 0, totalTokens: 0,
    inputTokensDetails: [{ cached_tokens: 0 }], outputTokensDetails: [{ reasoning_tokens: 0 }] };
  const original = f.bytes();
  const parsed = parseBoundJsonl(original, f.options);
  assert.deepEqual(f.bytes(), original);
  assert.equal(parsed.usage.request_count, 2);
  assert.equal(parsed.tools.call_count, 2);
  assert.equal(parsed.usage.total_tokens, null);
  assert.equal(parsed.collection.known_subtotals.total_tokens, 120);
  assert.deepEqual(parsed.collection.field_coverage.total_tokens,
    { known: 1, total: 2, unit: "model_response" });
  assert.ok(parsed.collection.warnings.some(x => x.startsWith("WORKBUDDY_NORMALIZED_ZERO_USAGE_UNVERIFIED_V1")));
  const result = applyJsonlMetrics(f.base, parsed, artifact("native.jsonl", original));
  assert.equal(result.metrics.usage.total_tokens.status, "partial");
  assert.equal(result.metrics.usage.total_tokens.value, null);
  assert.equal(result.collection.known_subtotals.total_tokens, 120);
  assert.deepEqual(result.collection.coverage.request_count, { known: 2, total: 2, unit: "model_response" });
  f.rows.push({ ...structuredClone(f.rows[3]), providerData: { ...pd, rawUsage: undefined,
    usage: { ...pd.usage, inputTokens: 1 } } });
  assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /CONFLICTING_NORMALIZED_USAGE/u);
});

test("provider-native measured zero remains observed rather than normalized-only unknown", () => {
  const f = fixture();
  for (const row of f.rows.filter(x => x.providerData?.usage)) {
    row.providerData.rawUsage = { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0,
      prompt_tokens_details: { cached_tokens: 0 }, completion_tokens_details: { reasoning_tokens: 0 } };
    row.providerData.usage = { requests: 1, inputTokens: 0, outputTokens: 0, totalTokens: 0,
      inputTokensDetails: [{ cached_tokens: 0 }], outputTokensDetails: [{ reasoning_tokens: 0 }] };
  }
  const parsed = parseBoundJsonl(f.bytes(), f.options);
  assert.equal(parsed.usage.total_tokens, 0);
  assert.equal(parsed.collection.metrics.total_tokens.status, "observed");
  assert.equal(parsed.usage.reasoning_output_tokens, 0);
  assert.equal(parsed.collection.warnings.some(x => x.startsWith("WORKBUDDY_NORMALIZED_ZERO_USAGE_UNVERIFIED_V1")), false);
});

test("normalized-only zero compatibility rejects altered counters and unknown raw shapes", () => {
  for (const change of [
    pd => { pd.rawUsage.inputTokens = 1; },
    pd => { pd.usage.totalTokens = 1; },
    pd => { pd.rawUsage.extra = 0; },
    pd => { pd.rawUsage.inputTokensDetails.cached_tokens = 1; },
    pd => { pd.usage.outputTokensDetails = []; },
  ]) {
    const f = fixture(), pd = f.rows[3].providerData;
    pd.rawUsage = { inputTokens: 0, outputTokens: 0, totalTokens: 0,
      inputTokensDetails: { cached_tokens: 0 }, outputTokensDetails: { reasoning_tokens: 0 } };
    pd.usage = { requests: 1, inputTokens: 0, outputTokens: 0, totalTokens: 0,
      inputTokensDetails: [{ cached_tokens: 0 }], outputTokensDetails: [{ reasoning_tokens: 0 }] };
    change(pd);
    assert.throws(() => parseBoundJsonl(f.bytes(), f.options), /RAW_USAGE_MISMATCH/u);
  }
});

test("WorkBuddy JSONL rejects wrong session, workspace, Prompt, request, tool coverage, final text and usage conflicts", () => {
  const changes = [
    f => { f.rows[1].sessionId = "wrong-session"; },
    f => { f.rows[1].cwd = "/other"; },
    f => { f.rows[0].content[0].text += " extra"; },
    f => { f.rows[1].providerData.conversationRequestId = "other-request"; },
    f => { f.rows[2].callId = "other-call"; },
    f => { f.rows[3].content[0].text = "wrong final"; },
    f => { f.rows[1].providerData.rawUsage.prompt_tokens++; },
    f => { f.rows.push({ ...structuredClone(f.rows[1]), providerData: { ...f.rows[1].providerData, usage: { ...f.rows[1].providerData.usage, outputTokens: 99 } } }); },
  ];
  for (const change of changes) { const f = fixture(); change(f); assert.throws(() => parseBoundJsonl(f.bytes(), f.options)); }
});

test("WorkBuddy supplement leaves frozen records intact and recomputes metrics on verification", async () => {
  const dir = await mkdtemp(join(tmpdir(), "wb-supplement-"));
  try {
    const f = fixture(), unit = join(dir, "unit"), projects = join(dir, "projects"), trace = "evidence/tasks/task/attempt/trace";
    const write = async (name, bytes) => { const path = join(unit, name); await mkdir(join(path, ".."), { recursive: true }); await writeFile(path, bytes); return path; };
    const binding = jsonBytes({ runtime_snapshot: f.snapshot });
    await write(trace + "/binding.json", binding);
    const traceBytes = jsonBytes({ raw_trace: [artifact("binding.json", binding)] });
    await write(trace + "/trace-index.json", traceBytes);
    f.base.collection.sources = [artifact("trace/trace-index.json", traceBytes)];
    f.base.collection.metric_sources = Object.fromEntries(Object.keys(f.base.collection.metric_sources).map(k => [k, ["trace/trace-index.json"]]));
    const resource = jsonBytes(f.base), resourcePath = "evidence/tasks/task/attempt/resource-metrics.json";
    await write(resourcePath, resource);
    const record = { identity: f.identity, dataset: { id: "dataset", digest: "d".repeat(64) }, harness: { id: "workbuddy" }, phase: "COMPLETED",
      session: f.session, prompt: { sha256: f.options.promptSha256, sent_at: "2026-09-21T00:00:00Z" }, resource_metrics_path: resourcePath, evidence: { trace_index_path: trace + "/trace-index.json" } };
    const recordBytes = jsonBytes(record), recordRelative = "evidence/tasks/task/attempt/execution-record.json";
    const path = await write(recordRelative, recordBytes);
    const evidenceManifest = jsonBytes({ artifacts: [artifact(resourcePath, resource), artifact(trace + "/trace-index.json", traceBytes)] });
    const evidenceManifestPath = "evidence/tasks/task/attempt/evidence-manifest.json";
    await write(evidenceManifestPath, evidenceManifest);
    await write("receipts/collect-evidence-receipt.json", jsonBytes({ status: "completed", stage: "collect-evidence", scope: { batch_id: "batch", unit_id: "unit" }, artifacts: [artifact(recordRelative, recordBytes), artifact(evidenceManifestPath, evidenceManifest)] }));
    await mkdir(join(projects, "workspace"), { recursive: true });
    await writeFile(join(projects, "workspace", f.session.session_id + ".jsonl"), f.bytes());
    const timingOnly = await supplementWorkBuddyTiming({ unitRoot: unit, executionRecord: path });
    assert.equal(timingOnly.token_supplement_sha256, null);
    assert.equal(JSON.parse(await readFile(timingOnly.resource_metrics_path)).metrics.timing.agent_duration_seconds.value, 4);
    await rm(join(unit, "evidence/timing-supplements/task"), { recursive: true });
    const result = await supplementWorkBuddyResources({ unitRoot: unit, executionRecord: path, nativeProjectsRoot: projects });
    assert.equal(result.status, "PASS");
    assert.deepEqual(await readFile(path), recordBytes);
    assert.deepEqual(await readFile(join(unit, resourcePath)), resource);
    await assert.rejects(() => supplementWorkBuddyResources({ unitRoot: unit, executionRecord: path, nativeProjectsRoot: projects }), /EEXIST/);
    const tokenBefore = await readFile(result.resource_metrics_path);
    const timing = await supplementWorkBuddyTiming({ unitRoot: unit, executionRecord: path });
    assert.equal(timing.status, "PASS");
    assert.equal(timing.token_supplement_sha256, result.supplement_sha256);
    assert.deepEqual(await readFile(path), recordBytes);
    assert.deepEqual(await readFile(result.resource_metrics_path), tokenBefore);
    const timed = JSON.parse(await readFile(timing.resource_metrics_path));
    assert.equal(timed.metrics.usage.total_tokens.value, 350);
    assert.equal(timed.metrics.timing.agent_duration_seconds.value, 4);
    assert.equal(timed.metrics.timing.duration_seconds.value, 5);
    await assert.rejects(() => supplementWorkBuddyTiming({ unitRoot: unit, executionRecord: path }), /EEXIST/);
    // Re-hashing a forged metric must not bypass recomputation from frozen evidence.
    timed.metrics.timing.agent_duration_seconds.value++;
    const forged = jsonBytes(timed), timingManifestPath = join(unit, "evidence/timing-supplements/task/supplement.json");
    await writeFile(timing.resource_metrics_path, forged);
    const timingManifest = JSON.parse(await readFile(timingManifestPath));
    timingManifest.resource = artifact("resource-metrics.json", forged);
    await writeFile(timingManifestPath, jsonBytes(timingManifest));
    await assert.rejects(() => verifyTimingSupplement(unit, "task", path), /METRICS_MISMATCH/);
    await writeFile(join(unit, trace, "binding.json"), jsonBytes({ runtime_snapshot: { ...f.snapshot, request: { ...f.snapshot.request, completedAt: 1 } } }));
    await assert.rejects(() => verifyTimingSupplement(unit, "task", path), /ORIGINAL_TRACE_DRIFT/);
    await writeFile(join(unit, trace, "binding.json"), binding);
    const metrics = JSON.parse(await readFile(result.resource_metrics_path)); metrics.metrics.usage.total_tokens.value++;
    const changed = jsonBytes(metrics); await writeFile(result.resource_metrics_path, changed);
    const manifestPath = join(unit, "evidence/resource-supplements/task/supplement.json");
    const manifest = JSON.parse(await readFile(manifestPath)); manifest.resource = artifact("resource-metrics.json", changed); await writeFile(manifestPath, jsonBytes(manifest));
    await assert.rejects(() => verifySupplement(unit, "task", path), /METRICS_MISMATCH/);
    await symlink(join(projects, "workspace", f.session.session_id + ".jsonl"), join(projects, f.session.session_id + ".jsonl"));
    await mkdir(join(projects, "other")); await writeFile(join(projects, "other", f.session.session_id + ".jsonl"), f.bytes());
    await assert.rejects(() => discoverJsonl(projects, f.session.session_id), /AMBIGUOUS/);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test("WorkBuddy native timing distinguishes flow from native lifetime and accepts earlier internal finish", () => {
  const f = fixture();
  const binding = { ...f.options, prompt: { sha256: f.options.promptSha256, sent_at: "2026-09-21T00:00:00Z" } };
  let values = workBuddyTiming(binding);
  assert.equal(values.duration_seconds.value, 5);
  assert.equal(values.agent_duration_seconds.value, 4);
  const controller = workBuddyTiming({ ...binding, controllerTiming: { profile: "prompt-send-to-controller-terminal/v1", observed_at: "2026-09-21T00:00:07.250Z" } });
  assert.equal(controller.duration_seconds.value, 7.25);
  assert.equal(controller.agent_duration_seconds.value, 4);
  assert.match(controller.duration_seconds.basis, /prompt-send-to-controller-terminal/);
  delete f.snapshot.request.completedAt;
  assert.equal(workBuddyTiming(binding).agent_duration_seconds.value, 3.98);
  f.snapshot.request.startedAt = f.snapshot.request.finishTimestamp;
  assert.equal(workBuddyTiming(binding).agent_duration_seconds.value, 0);
  delete f.snapshot.request.finishTimestamp;
  values = workBuddyTiming(binding);
  assert.equal(values.duration_seconds.value, null);
  assert.equal(values.agent_duration_seconds.status, "unavailable");
  f.snapshot.request.completedAt = Date.parse("2026-09-21T00:00:05Z");
  delete f.snapshot.request.startedAt; delete f.snapshot.request.timestamp;
  assert.equal(workBuddyTiming(binding).agent_duration_seconds.value, null);
  assert.equal(workBuddyTiming(binding).duration_seconds.value, 5);
  delete binding.prompt.sent_at;
  assert.equal(workBuddyTiming(binding).duration_seconds.value, null);
});

test("WorkBuddy timing rejects invalid, reversed, conflicting timestamps and wrong identity", () => {
  const changes = [
    b => { b.snapshot.request.timestamp = "2026-09-21T00:00:01Z"; },
    b => { b.snapshot.request.timestamp = NaN; },
    b => { b.snapshot.request.timestamp = -1; },
    b => { b.snapshot.request.timestamp = 1.5; },
    b => { b.snapshot.request.completedAt = b.snapshot.request.timestamp - 1; },
    b => { b.snapshot.request.finishTimestamp = b.snapshot.request.completedAt + 1; },
    b => { b.prompt.sent_at = "2026-09-21T00:00:02Z"; },
    b => { b.prompt.sent_at = "invalid"; },
    b => { b.session = { ...b.session, turn_id: "wrong" }; },
    b => { b.session = { ...b.session, cwd: "/wrong" }; },
    b => { b.prompt.sha256 = "f".repeat(64); },
  ];
  for (const change of changes) {
    const f = fixture(), binding = { ...f.options, prompt: { sha256: f.options.promptSha256, sent_at: "2026-09-21T00:00:00Z" } };
    change(binding);
    assert.throws(() => workBuddyTiming(binding), /WORKBUDDY_TIMING_/);
  }
});
