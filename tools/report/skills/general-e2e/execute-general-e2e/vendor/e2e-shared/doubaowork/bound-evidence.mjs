// Scene-neutral native evidence verification. No General/Web receipt schema or UI mutation.
import { createHash } from "node:crypto";
import { lstat, readFile, realpath } from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import { normalizeRuntimeMessages, normalizeRuntimePrompt } from "./runtime-messages.mjs";
import { normalizeNativeToolEvents } from "./runtime-tools.mjs";
import { normalizeNativeLifecycle } from "./runtime-lifecycle.mjs";
import { inspectNativeResourceObservations } from "./resource-observations.mjs";
import { discoverNativeSources, defaultNativeRoots } from "./platform.mjs";
import { buildNativeEvidence, deduplicateTrajectoryEvents, parseTrajectoryJsonl } from "./native-evidence.mjs";
import { summarizePromptReadback } from "./lib.mjs";
import { mergeNativeToolTimeline, mergeObservedToolTimeline } from "./trajectory-merge.mjs";
import { inspectNativeAuthorizationHistory } from "./interactions.mjs";
import { verifyCancellationEvidence, verifyFailureEvidence } from "./terminal-evidence.mjs";

const sha = bytes => createHash("sha256").update(bytes).digest("hex");
export async function readRegular(path) {
  const st = await lstat(path);
  if (!st.isFile() || st.isSymbolicLink() || st.size > 32 * 1024 * 1024 || await realpath(path) !== resolve(path)) throw new Error("DOUBAOWORK_COLLECTOR_INPUT_UNSAFE");
  return readFile(path);
}
export async function boundArtifact(control, row) {
  if (!row || basename(row.file || "") !== row.file) throw new Error("DOUBAOWORK_COLLECTOR_ARTIFACT_PATH_INVALID");
  const bytes = await readRegular(join(control, row.file));
  if (sha(bytes) !== row.sha256 || bytes.length !== row.size_bytes) throw new Error("DOUBAOWORK_COLLECTOR_ARTIFACT_DRIFT");
  return bytes;
}

export function verifyTrajectoryPrompt(events, expectedHash, { sourceBytes, nonSuccessVerified = false }) {
  const users = events.filter(event => event.kind === "user_message");
  if (users.some(event => typeof event.content !== "string"
      || summarizePromptReadback(event.content).sha256 !== expectedHash)) {
    throw new Error("DOUBAOWORK_TRAJECTORY_PROMPT_MISMATCH");
  }
  if (!users.length) {
    const empty = sourceBytes === null || sourceBytes.toString("utf8").trim() === "";
    if (!nonSuccessVerified || !empty || events.length) throw new Error("DOUBAOWORK_TRAJECTORY_PROMPT_MISMATCH");
    return { status: "unavailable", reason: sourceBytes === null ? "native-trajectory-missing" : "native-trajectory-empty-at-capture" };
  }
  return { status: "verified", user_event_count: users.length };
}

export function verifyRecoveredDispatchAcknowledgement(snapshot, journal, native) {
  // The user's acknowledgement can precede exposure of the request ID. Bind
  // its user/conversation/Prompt now; compare any exposed request ID below.
  const proof = journal.send.recovery_ack, acknowledged = normalizeRuntimePrompt(snapshot,
    { ...journal, session: { ...journal.session, native_request_session_id: null } });
  if (journal.send.acceptance_source !== "native-im-user-acknowledgement-observed-during-recovery"
      || !proof || journal.send.click_returned_at !== null
      || snapshot.observed_at !== proof.observed_at || journal.send.accepted_at !== proof.observed_at
      || !Number.isFinite(Date.parse(proof.observed_at)) || !Number.isFinite(Date.parse(journal.send.dispatch_started_at))
      || Date.parse(proof.observed_at) < Date.parse(journal.send.dispatch_started_at)
      || journal.timing.sent_at !== journal.send.dispatch_started_at
      || acknowledged.conversation_id !== native.conversation_id || proof.conversation_id !== native.conversation_id
      || acknowledged.user_message_id !== native.user_message_id || proof.user_message_id !== native.user_message_id
      || acknowledged.native_request_session_id !== proof.native_request_session_id
      || acknowledged.native_request_session_id && acknowledged.native_request_session_id !== native.native_request_session_id) {
    throw new Error("DOUBAOWORK_RECOVERY_ACK_BINDING_INVALID");
  }
  return { source: journal.send.acceptance_source, observed_at: proof.observed_at,
    raw_ref: "raw/recovered-send-ack.json", click_returned_at: null };
}


export function normalizeVerifiedNonSuccessToolSubset(snapshot, options, { nonSuccessVerified = false } = {}) {
  try { return { ...normalizeNativeToolEvents(snapshot, options), dropped_failed_upload_count: 0 }; }
  catch (error) {
    if (!nonSuccessVerified || error.message !== "NATIVE_TOOL_LEDGER_INVALID"
        || !snapshot.ledger_observation_policy || !Array.isArray(snapshot.ledger)
        || !Array.isArray(snapshot.ledger_samples) || !Array.isArray(snapshot.events)) throw error;
    const uploaded = snapshot.ledger.filter(row => row.uploadState === "uploaded");
    const failed = snapshot.ledger.filter(row => row.uploadState !== "uploaded");
    const sampled = new Set(snapshot.ledger_samples.map(row => row.row?.toolCallId));
    if (!failed.length || failed.some(row => row.uploadState !== "failed" || !row.toolCallId || sampled.has(row.toolCallId))) throw error;
    const ids = new Set(uploaded.map(row => row.toolCallId));
    const strictSubset = { ...snapshot, ledger: uploaded,
      ledger_samples: snapshot.ledger_samples.filter(row => ids.has(row.row?.toolCallId)),
      events: snapshot.events.filter(row => ids.has(row.tool_call_id)) };
    const verified = normalizeNativeToolEvents(strictSubset, options);
    return { ...verified, status: "partial", scope: "bound-native-agent-uploaded-tool-subset",
      dropped_failed_upload_count: failed.length };
  }
}

export async function readBoundNativeEvidence({ journalFile, journal, workspace = journal.workspace }) {
  if (journal.native_interactions?.confirmation_seen) throw new Error("DOUBAOWORK_NATIVE_INTERACTION_UNACCOUNTED");
  if (journal.send?.dispatch_attempt_count !== 1 || journal.session?.prompt_readback?.status !== "verified" || !journal.native_observation) throw new Error("DOUBAOWORK_NATIVE_EXECUTION_NOT_VERIFIED");
  const control = dirname(journalFile), runtimeBytes = await boundArtifact(control, journal.native_observation.artifact);
  const runtime = JSON.parse(runtimeBytes), native = normalizeRuntimeMessages(runtime, journal);
  if (inspectNativeAuthorizationHistory(runtime, native.native_request_session_id).length) throw new Error("DOUBAOWORK_NATIVE_AUTHORIZATION_HISTORY_UNACCOUNTED");
  let cancellation = null, failure = null, cancellationIntentBytes = null, terminalObservationBytes = null;
  if (native.terminal === "interrupted") {
    cancellationIntentBytes = await boundArtifact(control, journal.cancellation?.intent_artifact);
    terminalObservationBytes = await boundArtifact(control, journal.cancellation?.terminal_observation);
    cancellation = verifyCancellationEvidence({ state: journal, native, runtime,
      intent: JSON.parse(cancellationIntentBytes), observation: JSON.parse(terminalObservationBytes) });
  } else if (native.terminal === "failed") {
    terminalObservationBytes = await boundArtifact(control, journal.native_failure_observation);
    failure = verifyFailureEvidence({ state: journal, native, runtime, observation: JSON.parse(terminalObservationBytes) });
  } else if (native.terminal !== "completed" || !native.finished_at) throw new Error("DOUBAOWORK_NATIVE_TERMINAL_OR_TIME_UNAVAILABLE");
  const nonSuccess = cancellation ?? failure;
  let recoveryAckBytes = null, recoveryAcknowledgement = null;
  if (journal.send.recovery_ack || journal.send.acceptance_source) {
    recoveryAckBytes = await boundArtifact(control, journal.send.recovery_ack?.artifact);
    recoveryAcknowledgement = verifyRecoveredDispatchAcknowledgement(JSON.parse(recoveryAckBytes), journal, native);
  }
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
  if (finalBytes.toString("utf8") !== (native.final_text ?? "")) throw new Error("DOUBAOWORK_FINAL_REPLY_DRIFT");
  let nativeTools = null, nativeToolBytes = null;
  if (journal.native_observation.native_tools_artifact) {
    nativeToolBytes = await boundArtifact(control, journal.native_observation.native_tools_artifact);
    const snapshot = JSON.parse(nativeToolBytes);
    if (snapshot.profile_sha256 !== journal.native_tool_observer?.profile_sha256) throw new Error("DOUBAOWORK_NATIVE_TOOL_PROFILE_DRIFT");
    nativeTools = normalizeVerifiedNonSuccessToolSubset(snapshot, { attemptId: journal.attempt_id, workspace,
      agentId: native.native_request_session_id, conversationId: native.conversation_id,
      sentAt: journal.timing.sent_at, finishedAt: nonSuccess?.observed_at ?? native.finished_at },
    { nonSuccessVerified: nonSuccess?.verified === true });
  }
  const nativeToolCoverageDiagnostic = nativeTools?.dropped_failed_upload_count
    ? { status: "partial", reason: "native-tool-upload-failed-before-terminal", uploaded_count: nativeTools.known_subtotal,
      failed_upload_count: nativeTools.dropped_failed_upload_count } : null;
  const assistant = Object.values(runtime.maps.messageMap).find(m => m.message_id === native.reply_message_id);
  const supportedBlocks = new Set(["text_block", "thinking_block", "elapsed_block", "file_operation_block", "local_file_block", "generic_tool_block"]);
  const unknownBlocks = (assistant.content_blocks_v2 || []).filter(b => Object.entries(b.content || {}).some(([k, v]) => !supportedBlocks.has(k)
    && !(k === "pc_event_block" && v === "")));
  const multimodalBypassCount = (nativeTools?.events || []).filter(e => e.phase === "settled"
    && e.output?.structuredResultFacts?.localFileReadV2Bypass?.reason === "image").length;
  let completeToolTrace = !nonSuccess && Boolean(nativeTools) && unknownBlocks.length === 0 && multimodalBypassCount === 0;
  const missingToolDisplays = [];
  if (nativeTools && nativeTools.known_subtotal === 0 && assistant.content_blocks_v2.some(b => b.content?.file_operation_block)) {
    if (!nonSuccess) throw new Error("DOUBAOWORK_TOOL_DISPLAY_WITHOUT_NATIVE_EVENTS");
    missingToolDisplays.push("file_operation_block");
  }
  const discovery = await discoverNativeSources({ sessionId: native.conversation_id });
  const evidence = nonSuccess && discovery.session?.trajectories?.length === 0
    ? { trace: { sources: [], events: [], warnings: [] } }
    : await buildNativeEvidence({ sessionId: native.conversation_id, workspace, discovery });
  if (evidence.trace.sources.length !== 1 && !(nonSuccess && evidence.trace.sources.length === 0)) throw new Error("DOUBAOWORK_MAIN_AGENT_AMBIGUOUS");
  const source = evidence.trace.sources[0], trajectoryPath = source ? join(defaultNativeRoots().sessions_root, source.relative_path) : null;
  const trajectory = trajectoryPath ? await readRegular(trajectoryPath) : null;
  if (trajectory && sha(trajectory) !== source.sha256) throw new Error("DOUBAOWORK_TRAJECTORY_CHANGED_DURING_COLLECTION");
  if (evidence.trace.warnings.some(w => !["NATIVE_CWD_UNAVAILABLE", "NATIVE_TERMINAL_UNAVAILABLE", "FINAL_ASSISTANT_MISSING_FROM_TRAJECTORY",
    "DUPLICATE_SCOPED_TOOL_CALL_ID", "DUPLICATE_SCOPED_TOOL_RESULT_ID"].includes(w.code))) throw new Error("DOUBAOWORK_TRAJECTORY_DIAGNOSTICS_REQUIRE_REVIEW");
  const snapshots = [], archiveRaw = [];
  const archiveRoot = join(control, "trajectory-observations"), archiveIndexPath = join(archiveRoot, "index.json");
  let archiveIndexBytes = null;
  try { archiveIndexBytes = await readRegular(archiveIndexPath); } catch (e) { if (e.code !== "ENOENT") throw e; }
  if (archiveIndexBytes) {
    if (!source) throw new Error("DOUBAOWORK_ARCHIVE_WITHOUT_NATIVE_SOURCE");
    // The validated native emitter stamps debug events with this host's
    // Date.now(). Unknown runtimes must not use filesystem time to order them.
    // The installed 2.31.6 module 955025 was SHA-pinned from the live client;
    // its emitToolCallDebugEvent stamps ts:Date.now(). The exact source and all
    // sixty bound tool artifacts are audited in repair-control, and no other
    // profile is admitted by this independent collector runtime.
    if (!nativeToolBytes || JSON.parse(nativeToolBytes).profile_sha256 !== "f765c160a6d8661b95cddbbbee9bed1ab90902e910259c5c241ae4cd7df78e75") throw new Error("DOUBAOWORK_ARCHIVE_CLOCK_PROFILE_UNVERIFIED");
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
  const trajectoryPromptBinding = verifyTrajectoryPrompt(legacy.events, journal.prompt.readback_sha256,
    { sourceBytes: trajectory, nonSuccessVerified: nonSuccess?.verified === true });
  const nativeCalls = new Map((nativeTools?.events || []).filter(e => e.phase === "started").map(e => [e.tool_call_id, e]));
  const remoteCalls = legacy.events.filter(e => e.kind === "assistant_tool_call" && !nativeCalls.has(e.call_id));
  const observedToolNames = new Set([...nativeCalls.values()].map(e => e.tool_name).concat(remoteCalls.map(e => e.tool_name)));
  for (const b of assistant.content_blocks_v2.filter(b => b.content?.generic_tool_block)) {
    if (!observedToolNames.has(b.content.generic_tool_block.tool_name)) {
      // Preserve a native-completed candidate with a verified Prompt and local
      // tool ledger, but explicitly downgrade its trace to partial. Do not
      // synthesize a call/result from the assistant's display block.
      if (!nonSuccess && (native.terminal !== "completed" || !nativeTools
          || trajectoryPromptBinding.status !== "verified")) throw new Error("DOUBAOWORK_GENERIC_TOOL_WITHOUT_TRACE");
      missingToolDisplays.push("generic_tool_block");
      completeToolTrace = false;
    }
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
  return { control, runtimeBytes, runtime, native, cancellation, failure, cancellationIntentBytes, terminalObservationBytes, nonSuccess, recoveryAckBytes, recoveryAcknowledgement, lifecycleBytes, lifecycle, nativeResourceObservations, finalBytes, nativeTools, nativeToolBytes, nativeToolCoverageDiagnostic, assistant, unknownBlocks, completeToolTrace, multimodalBypassCount, missingToolDisplays, discovery, evidence, source, trajectoryPath, trajectory, snapshots, archiveRaw, archiveRoot, archiveIndexPath, archiveIndexBytes, currentEvents, allNativeEvents, legacy, trajectoryPromptBinding, nativeCalls, remoteCalls, observedToolNames, localNames, displayedRemoteNames, remoteCoverageVerified, timeline, crossSourceOrderUnknown };
}
