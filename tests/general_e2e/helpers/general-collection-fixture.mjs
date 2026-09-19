import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, realpath, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
export const writeJson = async (path, value) => writeFile(path, `${JSON.stringify(value, null, 2)}\n`);
export async function fixture({ harness = "qwenwork", platform = "macos", parent = tmpdir() } = {}) {
  await mkdir(parent, { recursive: true });
  const root = await realpath(await mkdtemp(join(parent, "general-collection-")));
  const taskRoot = join(root, "execution/tasks/task-one");
  const workspace = join(taskRoot, "workspace");
  const stateRoot = join(root, ".general-e2e/execution/task-one");
  const traceRoot = join(root, "inputs/trace");
  for (const path of [workspace, stateRoot, join(traceRoot, "raw"), join(traceRoot, "bindings")]) await mkdir(path, { recursive: true });
  const identity = { batch_id: "batch-one", unit_id: `${harness}-${platform}`, task_id: "task-one", attempt_id: "attempt-one" };
  const dataset = { id: "fixture-dataset", digest: "1".repeat(64) };
  const promptPath = join(taskRoot, "PROMPT.md");
  const prompt = "Create answer.txt.\n";
  await writeFile(promptPath, prompt);
  await writeFile(join(workspace, "answer.txt"), "answer\n");
  const manifest = {
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1", schema_version: 1, manifest_kind: "execution",
    batch_id: identity.batch_id, unit_id: identity.unit_id, dataset, task_ids: [identity.task_id],
    unit: { harness: { id: harness, platform, version: "fixture" }, model: { requested_id: "fixture-model", reasoning_effort: null } },
    tasks: [{ task_id: identity.task_id, workspace: { path: "execution/tasks/task-one/workspace" },
      prompt: { path: "execution/tasks/task-one/PROMPT.md", sent_sha256: digest(prompt) } }],
  };
  await writeJson(join(root, "manifest.json"), manifest);
  const bindingBytes = Buffer.from(`${JSON.stringify({ native_session_id: "native-one", workspace, prompt_sha256: digest(prompt) })}\n`);
  await writeFile(join(stateRoot, "binding.json"), bindingBytes);
  await writeFile(join(traceRoot, "bindings/session.json"), bindingBytes);
  const session = { thread_id: null, turn_id: harness === "workbuddy" ? "request-one" : null,
    session_id: "native-one", cwd: workspace, verified: true,
    binding_evidence: [{ path: ".general-e2e/execution/task-one/binding.json", sha256: digest(bindingBytes), size: bindingBytes.length }] };
  const state = {
    schema_version: "wildclawbench.general-e2e-execution-state/v1",
    driver: { id: `${harness}-fixture`, version: "0.1.0", harness, platform }, identity, dataset,
    phase: "COMPLETED", task_root: taskRoot, candidate_workspace: workspace,
    prompt: { path: promptPath, sha256: digest(prompt), send_status: "sent", sent_at: "2026-09-19T00:00:00Z" },
    send: { dispatch_attempt_count: 1 }, session,
    execution: { business_status: "completed", started_at: "2026-09-19T00:00:00Z", finished_at: "2026-09-19T00:01:00Z", duration_seconds: 60, error: null, cancellation_confirmed: null },
    human_assistance: { mode: "automatic", operation_count: 0, semantic_intervention_count: 0 },
  };
  const statePath = join(stateRoot, "automation-state.json");
  await writeJson(statePath, state);
  const events = [
    { type: "user_message", role: "user", content: prompt },
    { type: "tool_call", tool: { call_id: "call-one", name: "Write", arguments: { path: "answer.txt" } } },
    { type: "tool_result", tool: { call_id: "call-one", status: "success", result: "written" } },
    { type: "assistant_message", role: "assistant", content: "Done" },
  ].map((event, sequence) => ({
    schema_id: "urn:wildclawbench:schema:general-e2e:transcript-event:v1", schema_version: 1,
    identity, event_id: `event-${sequence}`, sequence, occurred_at: "2026-09-19T00:00:00Z",
    source: { adapter: `${harness}-fixture`, raw_ref: `raw/part-${sequence < 2 ? "one" : "two"}.jsonl#L${sequence % 2 + 1}`, redacted: true }, ...event,
  }));
  const transcript = Buffer.from(events.map((event) => JSON.stringify(event)).join("\n") + "\n");
  await writeFile(join(traceRoot, "transcript.jsonl"), transcript);
  const rawArtifacts = [];
  for (const [index, name] of ["one", "two"].entries()) {
    const bytes = Buffer.from(events.slice(index * 2, index * 2 + 2).map((event) => JSON.stringify({ native: event.type })).join("\n") + "\n");
    await writeFile(join(traceRoot, `raw/part-${name}.jsonl`), bytes);
    rawArtifacts.push({ path: `raw/part-${name}.jsonl`, sha256: digest(bytes), size: bytes.length });
  }
  const index = {
    schema_id: "urn:wildclawbench:schema:general-e2e:trace-index:v2", schema_version: 2, identity,
    adapter: { id: `${harness}-fixture`, version: "0.1.0", source: "redacted-fixture" },
    session: { thread_id: session.thread_id, turn_id: session.turn_id, session_id: session.session_id, cwd: workspace, lifecycle_generation: null },
    transcript: { path: "transcript.jsonl", sha256: digest(transcript), size: transcript.length, event_count: events.length },
    raw_trace: rawArtifacts,
    binding_evidence: [{ path: "bindings/session.json", sha256: digest(bindingBytes), size: bindingBytes.length }],
    completeness: { status: "complete", omitted_event_count: 0, missing: [] },
    calls: [{ call_id: "call-one", call_sequence: 1, result_sequence: 2 }],
  };
  const indexPath = join(traceRoot, "trace-index.json");
  await writeJson(indexPath, index);
  const metrics = JSON.parse(await readFile(new URL("../../../eval_general_e2e/contracts/examples/valid/resource-metrics-zero.json", import.meta.url), "utf8"));
  metrics.identity = identity;
  const resourcePath = join(root, "inputs/resource-metrics.json");
  async function updateResourceSources() {
    const stateBytes = await readFile(statePath);
    const indexBytes = await readFile(indexPath);
    metrics.collection.sources = [
      { path: "execution/automation-state.json", sha256: digest(stateBytes), size: stateBytes.length },
      { path: "trace/trace-index.json", sha256: digest(indexBytes), size: indexBytes.length },
      ...rawArtifacts.map((artifact) => ({ ...artifact, path: `trace/${artifact.path}` })),
    ];
    await writeJson(resourcePath, metrics);
  }
  await updateResourceSources();
  return { root, workspace, taskId: identity.task_id, state, statePath, index, indexPath, traceRoot, metrics, resourcePath, updateResourceSources,
    options: { unitRoot: root, stateFile: statePath, traceIndex: indexPath, resourceMetrics: resourcePath,
      pythonExecutable: process.env.PYTHON || "python3", stabilityMilliseconds: 1, processQuietMilliseconds: 5, processWaitMilliseconds: 50 } };
}

export function fixtureHook(harness = "qwenwork", mutation = null) {
  return { id: "fixture-only", version: "0.1.0", harness, platform: "darwin", run: async (workspace) => {
    await new Promise((resolve) => setTimeout(resolve, 10));
    const snapshot = { supported: true, platform: "darwin", workspace, targets: [], seed_pids: [], root_pids: [] };
    const value = { schema_version: "wildclawbench.general-e2e-task-process-cleanup/v1", supported: true, success: true,
      platform: "darwin", quiet_window_milliseconds: 5, quiet_observed_milliseconds: 5,
      late_process_detected: false, before: structuredClone(snapshot), after: structuredClone(snapshot), termination_attempts: [] };
    if (mutation) mutation(value);
    return value;
  } };
}
