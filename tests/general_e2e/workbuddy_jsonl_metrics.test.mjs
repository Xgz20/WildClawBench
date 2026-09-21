import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseBoundJsonl, applyJsonlMetrics, artifact, jsonBytes, verifySupplement, discoverJsonl,
  withoutModelResponseCount } from "../../tools/report/e2e-shared/workbuddy-jsonl-metrics/index.mjs";
import { supplementWorkBuddyResources } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/workbuddy/supplement-resources.mjs";
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
    request: { id: session.turn_id, traceId: "trace-fixture", state: "completed", timestamp: 1,
      userMessage: { state: "completed", content: [{ type: "text", text: prompt }] },
      assistantMessage: { state: "completed", content: [
        ...["call-1", "call-2"].map(toolCallId => ({ type: "tool", toolCallId, title: "Read", status: "completed" })),
        { type: "text", text: "Done." },
      ] }, usage: {}, completedAt: 5000 },
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
    const finalized = await finalizeGeneralExecution({ unitRoot: unit, stateFile: collected.state_file, traceIndex: collected.trace_index,
      resourceMetrics: collected.resource_metrics, pythonExecutable: process.env.PYTHON || "python3", stabilityMilliseconds: 1, processQuietMilliseconds: 5, processWaitMilliseconds: 50 }, { processCleanup: fixtureHook("workbuddy") });
    assert.equal(finalized.status, "PASS");
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
      session: f.session, prompt: { sha256: f.options.promptSha256 }, resource_metrics_path: resourcePath, evidence: { trace_index_path: trace + "/trace-index.json" } };
    const recordBytes = jsonBytes(record), recordRelative = "evidence/tasks/task/attempt/execution-record.json";
    const path = await write(recordRelative, recordBytes);
    const evidenceManifest = jsonBytes({ artifacts: [artifact(resourcePath, resource), artifact(trace + "/trace-index.json", traceBytes)] });
    const evidenceManifestPath = "evidence/tasks/task/attempt/evidence-manifest.json";
    await write(evidenceManifestPath, evidenceManifest);
    await write("receipts/collect-evidence-receipt.json", jsonBytes({ status: "completed", stage: "collect-evidence", scope: { batch_id: "batch", unit_id: "unit" }, artifacts: [artifact(recordRelative, recordBytes), artifact(evidenceManifestPath, evidenceManifest)] }));
    await mkdir(join(projects, "workspace"), { recursive: true });
    await writeFile(join(projects, "workspace", f.session.session_id + ".jsonl"), f.bytes());
    const result = await supplementWorkBuddyResources({ unitRoot: unit, executionRecord: path, nativeProjectsRoot: projects });
    assert.equal(result.status, "PASS");
    assert.deepEqual(await readFile(path), recordBytes);
    assert.deepEqual(await readFile(join(unit, resourcePath)), resource);
    await assert.rejects(() => supplementWorkBuddyResources({ unitRoot: unit, executionRecord: path, nativeProjectsRoot: projects }), /EEXIST/);
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
