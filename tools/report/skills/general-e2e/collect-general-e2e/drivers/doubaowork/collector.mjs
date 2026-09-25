#!/usr/bin/env node
import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdir, readFile, realpath, rename, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { readBoundNativeEvidence, readRegular } from "../../vendor/e2e-shared/doubaowork/bound-evidence.mjs";
export { verifyTrajectoryPrompt, verifyRecoveredDispatchAcknowledgement } from "../../vendor/e2e-shared/doubaowork/bound-evidence.mjs";

const ADAPTER = "doubaowork-native-evidence", VERSION = "0.2.7";
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const json = value => Buffer.from(`${JSON.stringify(value, null, 2)}\n`);
const artifact = (path, bytes, extra = {}) => ({ path, sha256: sha(bytes), size: bytes.length, ...extra });
const within = (root, path) => { const r = relative(root, path); return r && r !== ".." && !r.startsWith(`..${sep}`) && !isAbsolute(r); };
export async function collectDoubaoGeneral({ unitRoot, journalFile, outputRoot }) {
  unitRoot = await realpath(unitRoot); journalFile = resolve(journalFile); outputRoot = resolve(outputRoot);
  if (!within(unitRoot, journalFile) || !within(unitRoot, outputRoot) || !relative(unitRoot, outputRoot).startsWith(".general-e2e/collection/")) throw new Error("DOUBAOWORK_COLLECTION_SCOPE_INVALID");
  const journalBytes = await readRegular(journalFile), journal = JSON.parse(journalBytes);
  if (journal.native_interactions?.confirmation_seen) throw new Error("DOUBAOWORK_NATIVE_INTERACTION_UNACCOUNTED: automatic collection cannot assume no human intervention");
  if (journal.scene !== "general" || journal.send.dispatch_attempt_count !== 1
      || journal.session.prompt_readback.status !== "verified" || !journal.native_observation) throw new Error("DOUBAOWORK_NATIVE_EXECUTION_NOT_VERIFIED");
  const manifestBytes = await readRegular(join(unitRoot, "manifest.json")), manifest = JSON.parse(manifestBytes);
  if (sha(manifestBytes) !== journal.client.manifest_sha256 || manifest.manifest_kind !== "execution"
      || manifest.unit.harness.id !== "doubaowork" || manifest.batch_id !== journal.identity.batch_id
      || manifest.unit.unit_id !== journal.prepared.unit_id) throw new Error("DOUBAOWORK_COLLECTOR_MANIFEST_DRIFT");
  const tasks = manifest.tasks.filter(t => t.task_id === journal.identity.task_id);
  if (tasks.length !== 1) throw new Error("DOUBAOWORK_COLLECTOR_TASK_AMBIGUOUS");
  const task = tasks[0], promptPath = resolve(unitRoot, task.prompt.path), workspace = resolve(unitRoot, task.workspace.path);
  const taskRoot = join(unitRoot, "execution/tasks", task.task_id);
  if (!within(taskRoot, promptPath) || !within(taskRoot, workspace) || workspace !== journal.workspace || promptPath !== journal.prompt.file
      || sha(await readRegular(promptPath)) !== journal.prompt.sha256 || task.prompt.sent_sha256 !== journal.prompt.sha256) throw new Error("DOUBAOWORK_COLLECTOR_TASK_DRIFT");
  const { control, runtimeBytes, runtime, native, cancellation, failure, cancellationIntentBytes, terminalObservationBytes, nonSuccess, recoveryAckBytes, recoveryAcknowledgement, lifecycleBytes, lifecycle, nativeResourceObservations, finalBytes, nativeTools, nativeToolBytes, assistant, unknownBlocks, completeToolTrace, multimodalBypassCount, missingToolDisplays, discovery, evidence, source, trajectoryPath, trajectory, snapshots, archiveRaw, archiveRoot, archiveIndexPath, archiveIndexBytes, currentEvents, allNativeEvents, legacy, trajectoryPromptBinding, nativeCalls, remoteCalls, observedToolNames, localNames, displayedRemoteNames, remoteCoverageVerified, timeline, crossSourceOrderUnknown } = await readBoundNativeEvidence({ journalFile, journal, workspace });
  const identity = { batch_id: manifest.batch_id, unit_id: manifest.unit.unit_id, task_id: task.task_id, attempt_id: journal.attempt_id };
  await mkdir(dirname(outputRoot), { recursive: true });
  if (await realpath(dirname(outputRoot)) !== dirname(outputRoot)) throw new Error("DOUBAOWORK_COLLECTION_SYMLINK_PARENT");
  try { await lstat(outputRoot); throw new Error("DOUBAOWORK_COLLECTION_ALREADY_EXISTS"); } catch (e) { if (e.code !== "ENOENT") throw e; }
  const staging = `${outputRoot}.staging-${randomUUID()}`;
  await mkdir(staging);
  const write = async (name, bytes) => { await mkdir(dirname(join(staging, name)), { recursive: true }); await writeFile(join(staging, name), bytes, { flag: "wx", mode: 0o600 }); return artifact(name, bytes); };
  const raw = [await write("raw/runtime-messages.json", runtimeBytes)];
  if (trajectory) raw.push(await write("raw/trajectory.jsonl", trajectory));
  if (cancellationIntentBytes) raw.push(await write("raw/cancellation-intent.json", cancellationIntentBytes));
  if (terminalObservationBytes) raw.push(await write("raw/native-terminal-observation.json", terminalObservationBytes));
  raw.push(await write("raw/native-resource-observations.json", json(nativeResourceObservations)));
  if (recoveryAckBytes) raw.push(await write("raw/recovered-send-ack.json", recoveryAckBytes));
  if (lifecycleBytes) raw.push(await write("raw/native-lifecycle.json", lifecycleBytes));
  for (const row of archiveRaw) raw.push(await write(row.path, row.bytes));
  if (nativeToolBytes) raw.push(await write("raw/native-tools.json", nativeToolBytes));
  raw.push(await write("raw/normalization-diagnostics.json", json({ duplicate_events: legacy.duplicates, cross_source_order_unknown: crossSourceOrderUnknown,
    tool_order_basis: timeline.basis, shared_call_count: timeline.shared_call_count ?? null,
    trajectory_prompt_binding: trajectoryPromptBinding,
    non_success_tool_displays_without_execution: missingToolDisplays })));
  const binding = await write("bindings/runtime-messages.json", runtimeBytes);
  const dispatchBinding = await write("bindings/dispatch-journal.json", journalBytes);
  const bindings = [binding, dispatchBinding];
  const response = await write("final-response.txt", finalBytes);
  const session = { thread_id: null, turn_id: native.reply_message_id, session_id: native.conversation_id, cwd: workspace, lifecycle_generation: null };
  const state = {
    schema_version: "wildclawbench.general-e2e-execution-state/v1",
    driver: { id: "doubaowork-macos-general", version: VERSION, harness: "doubaowork", platform: manifest.unit.harness.platform },
    identity, dataset: { id: manifest.dataset.id, digest: manifest.dataset.digest }, phase: nonSuccess ? "FAILED" : "COMPLETED", task_root: taskRoot, candidate_workspace: workspace,
    prompt: { path: promptPath, sha256: journal.prompt.sha256, send_status: "sent", sent_at: journal.timing.sent_at },
    send: { dispatch_attempt_count: 1 },
    session: { thread_id: null, turn_id: native.reply_message_id, session_id: native.conversation_id, cwd: workspace, verified: true,
      binding_evidence: bindings.map(row => ({ ...row, path: relative(unitRoot, join(outputRoot, row.path)) })) },
    execution: { business_status: nonSuccess?.business_status ?? "completed", started_at: journal.timing.sent_at, finished_at: nonSuccess?.observed_at ?? native.finished_at,
      duration_seconds: nonSuccess ? (Date.parse(nonSuccess.observed_at) - Date.parse(journal.timing.sent_at)) / 1000
        : lifecycle?.status === "observed" ? lifecycle.duration_seconds : native.raw_terminal.profile === "native-im-api-history/v1" ? null
        : (Date.parse(native.finished_at) - Date.parse(journal.timing.sent_at)) / 1000,
      error: failure ? { code: "DOUBAOWORK_NATIVE_FAILURE", message: "Bound native transport failure confirmed by Error status and idle runtime" }
        : cancellation ? { code: "DOUBAOWORK_CANCELLED", message: "Bound native Stop confirmed by Broken status and idle runtime" } : null,
      cancellation_confirmed: cancellation ? true : null },
    human_assistance: { mode: "automatic", operation_count: 0, semantic_intervention_count: 0 },
    extensions: { evidence: { final_response_path: relative(unitRoot, join(outputRoot, response.path)), final_response_sha256: response.sha256 },
      client: { version: journal.client.version, model: journal.actual.model, reasoning: manifest.unit.model.reasoning_effort },
      doubaowork: { native_sources: native.sources, native_request_session_id: native.native_request_session_id,
        raw_terminal: native.raw_terminal, agent_duration_seconds: native.agent_duration_seconds, source_journal_sha256: sha(journalBytes),
        lifecycle_timing: lifecycle, server_or_store_finished_at: native.server_or_store_finished_at ?? null,
        cancellation,
        native_failure: failure,
        recovered_send_acknowledgement: recoveryAcknowledgement,
        tool_trace_scope: nativeTools?.scope ?? null, tool_trace_status: nativeTools?.status ?? "partial" } },
  };
  const events = [], calls = new Map();
  const add = (type, role, content, rawRef, extra = {}) => events.push({ schema_id: "urn:wildclawbench:schema:general-e2e:transcript-event:v1", schema_version: 1,
    identity, event_id: `${journal.attempt_id}:${events.length}`, sequence: events.length, occurred_at: null, type, role, content,
    source: { adapter: ADAPTER, raw_ref: rawRef, redacted: rawRef.includes("runtime-messages") }, ...extra });
  const user = Object.values(runtime.maps.messageMap).find(m => m.user_type === 1);
  add("user_message", "user", user.content_blocks_v2.find(b => b.block_type === 10000).content.text_block.text, "raw/runtime-messages.json#L1");
  const addLocal = (e, orderRef = null) => {
    const ref = `raw/native-tools.json#/events/${e.raw_event_index}`;
    const extra = { occurred_at: e.observed_at, native: { agent_id: native.native_request_session_id, instance_id: e.instance_id,
      source_profile: "doubaowork-local-tool-debug-sink/v1", scope: nativeTools.scope, native_order_ref: orderRef } };
    if (e.phase === "started") {
      calls.set(e.tool_call_id, { call_id: e.tool_call_id, call_sequence: events.length, result_sequence: null });
      add("tool_call", "assistant", null, ref, { ...extra, tool: { call_id: e.tool_call_id, name: e.tool_name, arguments: e.input, result: null, status: "unknown" } });
    } else {
      calls.get(e.tool_call_id).result_sequence = events.length;
      add("tool_result", null, null, ref, { ...extra, tool: { call_id: e.tool_call_id, name: e.tool_name, arguments: null,
        result: e.output, status: e.output?.status === "error" ? "error" : "unknown" } });
    }
  };
  for (const entry of timeline.entries) {
    if (entry.source === "local") { addLocal(entry.event); continue; }
    const e = entry.event;
    const ref = `${e.source.file}#L${e.source.line}`;
    if (e.kind === "user_message") continue;
    if (entry.local) { addLocal(entry.local, ref); continue; }
    const sourceMetadata = entry.native_canonical ? { native: { order_semantics: "native-model-request-result-order",
      execution_observed_at: entry.execution_event?.observed_at ?? null,
      local_execution_raw_ref: entry.execution_event ? `raw/native-tools.json#/events/${entry.execution_event.raw_event_index}` : null } } : {};
    if (e.kind === "assistant_tool_call") {
      if (!e.call_id || calls.has(e.call_id)) throw new Error("DOUBAOWORK_DUPLICATE_OR_MISSING_CALL_ID");
      calls.set(e.call_id, { call_id: e.call_id, call_sequence: events.length, result_sequence: null });
      add("tool_call", "assistant", null, ref, { ...sourceMetadata, tool: { call_id: e.call_id, name: e.tool_name, arguments: e.arguments, result: null, status: "unknown" } });
    } else if (e.kind === "tool_result") {
      const call = calls.get(e.call_id);
      if (!call || call.result_sequence !== null) throw new Error("DOUBAOWORK_ORPHAN_OR_DUPLICATE_TOOL_RESULT");
      call.result_sequence = events.length;
      add("tool_result", null, null, ref, { ...sourceMetadata, tool: { call_id: e.call_id, name: events[call.call_sequence].tool.name, arguments: null, result: e.content, status: "unknown" } });
    } else if (e.kind === "assistant_message" && e.content !== native.final_text) add("assistant_message", "assistant", e.content, ref);
  }
  if (native.final_text) add("assistant_message", "assistant", native.final_text, "raw/runtime-messages.json#L1", { native: { reply_message_id: native.reply_message_id } });
  const transcript = await write("transcript.jsonl", Buffer.from(events.map(e => JSON.stringify(e)).join("\n") + "\n"));
  const index = { schema_id: "urn:wildclawbench:schema:general-e2e:trace-index:v2", schema_version: 2, identity,
    adapter: { id: ADAPTER, version: VERSION, source: "Bound native IM messages and explicit session trajectory" }, session,
    transcript: { ...transcript, event_count: events.length }, raw_trace: raw, binding_evidence: bindings,
    completeness: { status: completeToolTrace ? "complete" : "partial", omitted_event_count: 0,
      missing: completeToolTrace ? [] : [...(cancellation ? ["native-task-cancelled-before-complete-trace"] : failure ? ["native-task-failed-before-complete-trace"] : []), ...(!trajectory ? ["native-trajectory-unavailable"] : []),
        ...(multimodalBypassCount ? ["multimodal-tool-result-content-unverified"] : []),
        ...(trajectoryPromptBinding.status !== "verified" ? [trajectoryPromptBinding.reason] : []),
        ...(missingToolDisplays.length ? ["non-success-tool-display-without-execution-evidence"] : []),
        ...(!native.final_text ? ["final-assistant-text-unavailable"] : []), ...(!nativeTools ? ["native-tool-trajectory-incomplete"] : []), ...(unknownBlocks.length ? ["unmapped-native-message-block"] : []),
        ...(crossSourceOrderUnknown ? ["cross-source-tool-order-unavailable"] : []),
        ...(!remoteCoverageVerified ? ["remote-tool-event-coverage-incomplete"] : [])] }, calls: [...calls.values()],
    normalization: { native_event_count: allNativeEvents.length + (nativeTools?.events.length || 0) + 2,
      normalized_event_count: events.length,
      filtered_native_event_count: allNativeEvents.length + (nativeTools?.events.length || 0) + 2 - events.length,
      compatibility_profiles: ["doubaowork-native-im/v1", "doubaowork-trajectory-replay-dedup/v1", ...(nativeTools ? ["doubaowork-local-tool-debug-sink/v1"] : [])] } };
  const indexArtifact = await write("trace-index.json", json(index));
  const stateArtifact = await write("execution-state.json", json(state));
  const metric = (value = null, basis = "No verified native accounting profile for this metric") => ({ value, status: value === null ? "unavailable" : "observed", basis });
  const usageFields = ["input_tokens", "output_tokens", "total_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_output_tokens"];
  const fields = [...usageFields, "request_count", "request_attempt_count", "call_count", "duration_seconds", "agent_duration_seconds"];
  const toolCountKnown = !nonSuccess && Boolean(nativeTools) && unknownBlocks.length === 0 && remoteCoverageVerified;
  const metrics = { usage: Object.fromEntries(usageFields.map(k => [k, metric()])), requests: { request_count: metric(), request_attempt_count: metric() },
    tools: { call_count: toolCountKnown ? metric(calls.size, "Union of bound local-tool protocol and session trajectory; native call IDs deduplicated with retained raw provenance")
      : { value: null, status: "partial", basis: "Unique calls in the bound trajectory; provider total coverage unknown" } },
    timing: { duration_seconds: metric(state.execution.duration_seconds, nonSuccess ? "Dispatch to observed native terminal and idle runtime; includes controller observation delay, not agent runtime"
      : lifecycle?.status === "observed" ? `Dispatch boundary to ${lifecycle.source}` : native.raw_terminal.profile === "native-im-api-history/v1"
      ? "Unavailable: client dispatch and native server finish have different clock domains"
      : `Dispatch boundary to ${native.sources.finished_at}`), agent_duration_seconds: metric(native.agent_duration_seconds, "Native elapsed_block end_time_s - start_time_s") } };
  const flat = { ...metrics.usage, ...metrics.requests, ...metrics.tools, ...metrics.timing };
  const resource = { schema_id: "urn:wildclawbench:schema:general-e2e:resource-metrics:v1", schema_version: 1, identity, metrics,
    collection: { collector: ADAPTER, version: VERSION, status: "partial", collected_at: new Date().toISOString(),
      sources: [{ ...stateArtifact, path: "execution/automation-state.json" }, { ...indexArtifact, path: "trace/trace-index.json" }, ...raw.map(r => ({ ...r, path: `trace/${r.path}` }))],
      warnings: ["Token/request accounting unavailable; context-window occupancy is not cumulative token consumption; subscription display has no verified unit.", ...(toolCountKnown ? [] : ["Tool count is a known subtotal."])], excluded_scope: ["unbound native logs", "other conversations", "unexposed provider-internal requests/reasoning"],
      coverage: Object.fromEntries(fields.map(k => [k, k === "call_count"
        ? { known: calls.size, total: toolCountKnown ? calls.size : null, unit: "tool-call" }
        : { known: flat[k].status === "observed" ? 1 : 0, total: flat[k].status === "observed" ? 1 : null, unit: "turn" }])),
      known_subtotals: toolCountKnown ? {} : { call_count: calls.size } } };
  await write("resource-metrics.json", json(resource));
  if (sha(await readRegular(journalFile)) !== sha(journalBytes) || trajectoryPath && sha(await readRegular(trajectoryPath)) !== source.sha256) throw new Error("DOUBAOWORK_COLLECTION_INPUT_CHANGED");
  if (archiveIndexBytes && sha(await readRegular(archiveIndexPath)) !== sha(archiveIndexBytes)) throw new Error("DOUBAOWORK_ARCHIVE_CHANGED_DURING_COLLECTION");
  await rename(staging, outputRoot);
  return { status: "COLLECTED_NOT_FINALIZED", output_root: outputRoot, identity, trace_event_count: events.length, tool_known_subtotal: calls.size };
}

export async function main(argv = process.argv.slice(2)) {
  const { values: v } = parseArgs({ args: argv, options: { "unit-root": { type: "string" }, "journal-file": { type: "string" }, "output-root": { type: "string" } } });
  console.log(JSON.stringify(await collectDoubaoGeneral({ unitRoot: v["unit-root"], journalFile: v["journal-file"], outputRoot: v["output-root"] }), null, 2));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(e => { console.error(e.message); process.exitCode = 1; });
