#!/usr/bin/env node
import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdir, readFile, realpath, rename, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { normalizeRuntimeMessages } from "../../vendor/e2e-shared/doubaowork/runtime-messages.mjs";
import { normalizeNativeToolEvents } from "../../vendor/e2e-shared/doubaowork/runtime-tools.mjs";
import { normalizeNativeLifecycle } from "../../vendor/e2e-shared/doubaowork/runtime-lifecycle.mjs";
import { inspectNativeResourceObservations } from "../../vendor/e2e-shared/doubaowork/resource-observations.mjs";
import { discoverNativeSources, defaultNativeRoots } from "../../vendor/e2e-shared/doubaowork/platform.mjs";
import { buildNativeEvidence, deduplicateTrajectoryEvents, parseTrajectoryJsonl } from "../../vendor/e2e-shared/doubaowork/native-evidence.mjs";
import { summarizePromptReadback } from "../../vendor/e2e-shared/doubaowork/lib.mjs";
import { mergeNativeToolTimeline, mergeObservedToolTimeline } from "../../vendor/e2e-shared/doubaowork/trajectory-merge.mjs";

const ADAPTER = "doubaowork-native-evidence", VERSION = "0.2.1";
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const json = value => Buffer.from(`${JSON.stringify(value, null, 2)}\n`);
const artifact = (path, bytes, extra = {}) => ({ path, sha256: sha(bytes), size: bytes.length, ...extra });
const within = (root, path) => { const r = relative(root, path); return r && r !== ".." && !r.startsWith(`..${sep}`) && !isAbsolute(r); };
async function readRegular(path) {
  const st = await lstat(path);
  if (!st.isFile() || st.isSymbolicLink() || st.size > 32 * 1024 * 1024 || await realpath(path) !== resolve(path)) throw new Error("DOUBAOWORK_COLLECTOR_INPUT_UNSAFE");
  return readFile(path);
}
async function boundArtifact(control, row) {
  if (!row || basename(row.file || "") !== row.file) throw new Error("DOUBAOWORK_COLLECTOR_ARTIFACT_PATH_INVALID");
  const bytes = await readRegular(join(control, row.file));
  if (sha(bytes) !== row.sha256 || bytes.length !== row.size_bytes) throw new Error("DOUBAOWORK_COLLECTOR_ARTIFACT_DRIFT");
  return bytes;
}

export async function collectDoubaoGeneral({ unitRoot, journalFile, outputRoot }) {
  unitRoot = await realpath(unitRoot); journalFile = resolve(journalFile); outputRoot = resolve(outputRoot);
  if (!within(unitRoot, journalFile) || !within(unitRoot, outputRoot) || !relative(unitRoot, outputRoot).startsWith(".general-e2e/collection/")) throw new Error("DOUBAOWORK_COLLECTION_SCOPE_INVALID");
  const journalBytes = await readRegular(journalFile), journal = JSON.parse(journalBytes);
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
  const control = dirname(journalFile), runtimeBytes = await boundArtifact(control, journal.native_observation.artifact);
  const runtime = JSON.parse(runtimeBytes), native = normalizeRuntimeMessages(runtime, journal);
  if (native.terminal !== "completed" || !native.finished_at) throw new Error("DOUBAOWORK_NATIVE_TERMINAL_OR_TIME_UNAVAILABLE");
  let lifecycleBytes = null, lifecycle = null;
  if (journal.native_observation.native_lifecycle_artifact) {
    lifecycleBytes = await boundArtifact(control, journal.native_observation.native_lifecycle_artifact);
    const snapshot = JSON.parse(lifecycleBytes);
    if (snapshot.status === "unavailable") lifecycle = { status: "unavailable", reason: snapshot.reason };
    else lifecycle = normalizeNativeLifecycle(snapshot, { attemptId: journal.attempt_id, workspace, native,
      sentAt: journal.timing.sent_at, profileSha: journal.native_lifecycle_observer?.profile_sha256 });
    if (lifecycle.status === "observed") {
      native.server_or_store_finished_at = native.finished_at;
      native.finished_at = lifecycle.finished_at;
      native.sources.finished_at = lifecycle.source;
    }
  }
  const nativeResourceObservations = inspectNativeResourceObservations(runtime, native);
  const finalBytes = await boundArtifact(control, journal.native_observation.final_reply);
  if (finalBytes.toString("utf8") !== native.final_text) throw new Error("DOUBAOWORK_FINAL_REPLY_DRIFT");
  let nativeTools = null, nativeToolBytes = null;
  if (journal.native_observation.native_tools_artifact) {
    nativeToolBytes = await boundArtifact(control, journal.native_observation.native_tools_artifact);
    const snapshot = JSON.parse(nativeToolBytes);
    if (snapshot.profile_sha256 !== journal.native_tool_observer?.profile_sha256) throw new Error("DOUBAOWORK_NATIVE_TOOL_PROFILE_DRIFT");
    nativeTools = normalizeNativeToolEvents(snapshot, { attemptId: journal.attempt_id, workspace,
      agentId: native.native_request_session_id, conversationId: native.conversation_id,
      sentAt: journal.timing.sent_at, finishedAt: native.finished_at });
  }
  const assistant = Object.values(runtime.maps.messageMap).find(m => m.message_id === native.reply_message_id);
  const supportedBlocks = new Set(["text_block", "thinking_block", "elapsed_block", "file_operation_block", "local_file_block", "generic_tool_block"]);
  const unknownBlocks = (assistant.content_blocks_v2 || []).filter(b => Object.entries(b.content || {}).some(([k, v]) => !supportedBlocks.has(k)
    && !(k === "pc_event_block" && v === "")));
  let completeToolTrace = Boolean(nativeTools) && unknownBlocks.length === 0;
  if (nativeTools && nativeTools.known_subtotal === 0 && assistant.content_blocks_v2.some(b => b.content?.file_operation_block)) throw new Error("DOUBAOWORK_TOOL_DISPLAY_WITHOUT_NATIVE_EVENTS");
  const discovery = await discoverNativeSources({ sessionId: native.conversation_id });
  const evidence = await buildNativeEvidence({ sessionId: native.conversation_id, workspace, discovery });
  if (evidence.trace.sources.length !== 1) throw new Error("DOUBAOWORK_MAIN_AGENT_AMBIGUOUS");
  const source = evidence.trace.sources[0], trajectoryPath = join(defaultNativeRoots().sessions_root, source.relative_path);
  const trajectory = await readRegular(trajectoryPath);
  if (sha(trajectory) !== source.sha256) throw new Error("DOUBAOWORK_TRAJECTORY_CHANGED_DURING_COLLECTION");
  if (evidence.trace.warnings.some(w => !["NATIVE_CWD_UNAVAILABLE", "NATIVE_TERMINAL_UNAVAILABLE", "FINAL_ASSISTANT_MISSING_FROM_TRAJECTORY",
    "DUPLICATE_SCOPED_TOOL_CALL_ID", "DUPLICATE_SCOPED_TOOL_RESULT_ID"].includes(w.code))) throw new Error("DOUBAOWORK_TRAJECTORY_DIAGNOSTICS_REQUIRE_REVIEW");
  const snapshots = [], archiveRaw = [];
  const archiveRoot = join(control, "trajectory-observations"), archiveIndexPath = join(archiveRoot, "index.json");
  let archiveIndexBytes = null;
  try { archiveIndexBytes = await readRegular(archiveIndexPath); } catch (e) { if (e.code !== "ENOENT") throw e; }
  if (archiveIndexBytes) {
    // The validated native emitter stamps debug events with this host's
    // Date.now(). Unknown runtimes must not use filesystem time to order them.
    if (!nativeToolBytes || JSON.parse(nativeToolBytes).profile_sha256 !== "72d22bb10d4c0a49bcd4a75e2b8d55b1c5346eda9af7b1a4c5a5f8b6cb26122e") throw new Error("DOUBAOWORK_ARCHIVE_CLOCK_PROFILE_UNVERIFIED");
    const index = JSON.parse(archiveIndexBytes);
    if (index.schema !== "wildclawbench.doubaowork-trajectory-observations/v1"
        || index.identity.attempt_id !== journal.attempt_id || index.identity.conversation_id !== native.conversation_id
        || index.identity.workspace !== workspace || !Array.isArray(index.snapshots) || index.snapshots.length > 256) throw new Error("DOUBAOWORK_ARCHIVE_BINDING_INVALID");
    let previous = 0, bytesTotal = 0;
    for (const row of index.snapshots) {
      const time = Date.parse(row.captured_at);
      if (!/^[0-9]{4}-[0-9a-f]{64}\.jsonl$/u.test(row.file) || row.native_source !== trajectoryPath
          || row.agent_id !== source.agent_id || !Number.isFinite(time) || time < previous || time < Date.parse(journal.timing.sent_at)) throw new Error("DOUBAOWORK_ARCHIVE_ROW_INVALID");
      const bytes = await readRegular(join(archiveRoot, row.file)); bytesTotal += bytes.length;
      if (sha(bytes) !== row.sha256 || bytes.length !== row.size || bytesTotal > 128 * 1024 * 1024) throw new Error("DOUBAOWORK_ARCHIVE_HASH_OR_CAPACITY_INVALID");
      const rawPath = `raw/trajectory-observations/${row.file}`, parsed = parseTrajectoryJsonl(bytes.toString("utf8"), rawPath);
      if (parsed.warnings.length) throw new Error("DOUBAOWORK_ARCHIVE_PARSE_INCOMPLETE");
      snapshots.push({ captured_at: row.captured_at, events: parsed.events.map(e => ({ ...e, agent_id: row.agent_id })) });
      archiveRaw.push({ path: rawPath, bytes }); previous = time;
    }
    archiveRaw.push({ path: "raw/trajectory-observations/index.json", bytes: archiveIndexBytes });
  }
  const currentEvents = evidence.trace.events.map(e => ({ ...e, source: { ...e.source, file: "raw/trajectory.jsonl" } }));
  const allNativeEvents = [...snapshots.flatMap(s => s.events), ...currentEvents];
  const legacy = deduplicateTrajectoryEvents(allNativeEvents);
  const users = legacy.events.filter(e => e.kind === "user_message");
  if (!users.length || users.some(e => typeof e.content !== "string" || summarizePromptReadback(e.content).sha256 !== journal.prompt.readback_sha256)) throw new Error("DOUBAOWORK_TRAJECTORY_PROMPT_MISMATCH");
  const nativeCalls = new Map((nativeTools?.events || []).filter(e => e.phase === "started").map(e => [e.tool_call_id, e]));
  const remoteCalls = legacy.events.filter(e => e.kind === "assistant_tool_call" && !nativeCalls.has(e.call_id));
  const observedToolNames = new Set([...nativeCalls.values()].map(e => e.tool_name).concat(remoteCalls.map(e => e.tool_name)));
  for (const b of assistant.content_blocks_v2.filter(b => b.content?.generic_tool_block)) {
    if (!observedToolNames.has(b.content.generic_tool_block.tool_name)) throw new Error("DOUBAOWORK_GENERIC_TOOL_WITHOUT_TRACE");
  }
  const localNames = new Set([...nativeCalls.values()].map(e => e.tool_name));
  const displayedRemoteNames = new Set(assistant.content_blocks_v2.filter(b => b.content?.generic_tool_block)
    .map(b => b.content.generic_tool_block.tool_name).filter(name => !localNames.has(name)));
  const remoteCoverageVerified = [...displayedRemoteNames].every(name => remoteCalls.filter(e => e.tool_name === name).length
    === assistant.content_blocks_v2.filter(b => b.content?.generic_tool_block?.tool_name === name).length);
  if (!remoteCoverageVerified) completeToolTrace = false;
  const timeline = snapshots.length
    ? mergeObservedToolTimeline([...snapshots, { captured_at: null, events: currentEvents }], nativeTools?.events || [])
    : mergeNativeToolTimeline(legacy.events, nativeTools?.events || []);
  const crossSourceOrderUnknown = !timeline.order_verified;
  if (crossSourceOrderUnknown) completeToolTrace = false;
  const identity = { batch_id: manifest.batch_id, unit_id: manifest.unit.unit_id, task_id: task.task_id, attempt_id: journal.attempt_id };
  await mkdir(dirname(outputRoot), { recursive: true });
  if (await realpath(dirname(outputRoot)) !== dirname(outputRoot)) throw new Error("DOUBAOWORK_COLLECTION_SYMLINK_PARENT");
  try { await lstat(outputRoot); throw new Error("DOUBAOWORK_COLLECTION_ALREADY_EXISTS"); } catch (e) { if (e.code !== "ENOENT") throw e; }
  const staging = `${outputRoot}.staging-${randomUUID()}`;
  await mkdir(staging);
  const write = async (name, bytes) => { await mkdir(dirname(join(staging, name)), { recursive: true }); await writeFile(join(staging, name), bytes, { flag: "wx", mode: 0o600 }); return artifact(name, bytes); };
  const raw = [await write("raw/runtime-messages.json", runtimeBytes), await write("raw/trajectory.jsonl", trajectory)];
  raw.push(await write("raw/native-resource-observations.json", json(nativeResourceObservations)));
  if (lifecycleBytes) raw.push(await write("raw/native-lifecycle.json", lifecycleBytes));
  for (const row of archiveRaw) raw.push(await write(row.path, row.bytes));
  if (nativeToolBytes) raw.push(await write("raw/native-tools.json", nativeToolBytes));
  raw.push(await write("raw/normalization-diagnostics.json", json({ duplicate_events: legacy.duplicates, cross_source_order_unknown: crossSourceOrderUnknown,
    tool_order_basis: timeline.basis, shared_call_count: timeline.shared_call_count ?? null })));
  const binding = await write("bindings/runtime-messages.json", runtimeBytes);
  await write("bindings/dispatch-journal.json", journalBytes);
  const response = await write("final-response.txt", finalBytes);
  const session = { thread_id: null, turn_id: native.reply_message_id, session_id: native.conversation_id, cwd: workspace, lifecycle_generation: null };
  const state = {
    schema_version: "wildclawbench.general-e2e-execution-state/v1",
    driver: { id: "doubaowork-macos-general", version: VERSION, harness: "doubaowork", platform: manifest.unit.harness.platform },
    identity, dataset: { id: manifest.dataset.id, digest: manifest.dataset.digest }, phase: "COMPLETED", task_root: taskRoot, candidate_workspace: workspace,
    prompt: { path: promptPath, sha256: journal.prompt.sha256, send_status: "sent", sent_at: journal.timing.sent_at },
    send: { dispatch_attempt_count: 1 },
    session: { thread_id: null, turn_id: native.reply_message_id, session_id: native.conversation_id, cwd: workspace, verified: true,
      binding_evidence: [{ ...binding, path: relative(unitRoot, join(outputRoot, binding.path)) }] },
    execution: { business_status: "completed", started_at: journal.timing.sent_at, finished_at: native.finished_at,
      duration_seconds: lifecycle?.status === "observed" ? lifecycle.duration_seconds : native.raw_terminal.profile === "native-im-api-history/v1" ? null
        : (Date.parse(native.finished_at) - Date.parse(journal.timing.sent_at)) / 1000, error: null, cancellation_confirmed: null },
    human_assistance: { mode: "automatic", operation_count: 0, semantic_intervention_count: 0 },
    extensions: { evidence: { final_response_path: relative(unitRoot, join(outputRoot, response.path)), final_response_sha256: response.sha256 },
      client: { version: journal.client.version, model: journal.actual.model, reasoning: manifest.unit.model.reasoning_effort },
      doubaowork: { native_sources: native.sources, native_request_session_id: native.native_request_session_id,
        raw_terminal: native.raw_terminal, agent_duration_seconds: native.agent_duration_seconds, source_journal_sha256: sha(journalBytes),
        lifecycle_timing: lifecycle, server_or_store_finished_at: native.server_or_store_finished_at ?? null,
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
  add("assistant_message", "assistant", native.final_text, "raw/runtime-messages.json#L1", { native: { reply_message_id: native.reply_message_id } });
  const transcript = await write("transcript.jsonl", Buffer.from(events.map(e => JSON.stringify(e)).join("\n") + "\n"));
  const index = { schema_id: "urn:wildclawbench:schema:general-e2e:trace-index:v2", schema_version: 2, identity,
    adapter: { id: ADAPTER, version: VERSION, source: "Bound native IM messages and explicit session trajectory" }, session,
    transcript: { ...transcript, event_count: events.length }, raw_trace: raw, binding_evidence: [binding],
    completeness: { status: completeToolTrace ? "complete" : "partial", omitted_event_count: 0,
      missing: completeToolTrace ? [] : [...(!nativeTools ? ["native-tool-trajectory-incomplete"] : []), ...(unknownBlocks.length ? ["unmapped-native-message-block"] : []),
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
  const toolCountKnown = Boolean(nativeTools) && unknownBlocks.length === 0 && remoteCoverageVerified;
  const metrics = { usage: Object.fromEntries(usageFields.map(k => [k, metric()])), requests: { request_count: metric(), request_attempt_count: metric() },
    tools: { call_count: toolCountKnown ? metric(calls.size, "Union of bound local-tool protocol and session trajectory; native call IDs deduplicated with retained raw provenance")
      : { value: null, status: "partial", basis: "Unique calls in the bound trajectory; provider total coverage unknown" } },
    timing: { duration_seconds: metric(state.execution.duration_seconds, lifecycle?.status === "observed" ? `Dispatch boundary to ${lifecycle.source}` : native.raw_terminal.profile === "native-im-api-history/v1"
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
  if (sha(await readRegular(journalFile)) !== sha(journalBytes) || sha(await readRegular(trajectoryPath)) !== source.sha256) throw new Error("DOUBAOWORK_COLLECTION_INPUT_CHANGED");
  if (archiveIndexBytes && sha(await readRegular(archiveIndexPath)) !== sha(archiveIndexBytes)) throw new Error("DOUBAOWORK_ARCHIVE_CHANGED_DURING_COLLECTION");
  await rename(staging, outputRoot);
  return { status: "COLLECTED_NOT_FINALIZED", output_root: outputRoot, identity, trace_event_count: events.length, tool_known_subtotal: calls.size };
}

export async function main(argv = process.argv.slice(2)) {
  const { values: v } = parseArgs({ args: argv, options: { "unit-root": { type: "string" }, "journal-file": { type: "string" }, "output-root": { type: "string" } } });
  console.log(JSON.stringify(await collectDoubaoGeneral({ unitRoot: v["unit-root"], journalFile: v["journal-file"], outputRoot: v["output-root"] }), null, 2));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(e => { console.error(e.message); process.exitCode = 1; });
