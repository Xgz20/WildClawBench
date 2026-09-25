// Web-only persistence adapter over the shared DoubaoWork native evidence core.
import { publishFrozenTransaction } from "./publication.mjs";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, lstat, realpath, rename, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve, sep } from "node:path";
import { readBoundNativeEvidence, readRegular, boundArtifact } from "../../vendor/e2e-shared/doubaowork/bound-evidence.mjs";
import { managedPeerConversations } from "./managed-peers.mjs";
import { readNativeActivity, assertNativeActivityAllowed } from "../../vendor/e2e-shared/doubaowork/runtime-activity.mjs";
import { readNativeToolActivity, assertNativeToolActivityAllowed } from "../../vendor/e2e-shared/doubaowork/runtime-tools.mjs";
import { cleanupDoubaoCandidateProcesses } from "../../vendor/e2e-shared/doubaowork/process-cleanup.mjs";
import { DRIVER_VERSION } from "./lib.mjs";
import { validatePreparedTaskRoot } from "./prepared-task.mjs";
import { assessDoubaoNativeWebFinalization } from "./finalizer.mjs";
import { mapDoubaoAssessmentToWebReceiptBridge } from "./receipt-bridge.mjs";
import { snapshotTree, atomicWriteJson, createExecutionRecord } from "../workbuddy/lib.mjs";
import { buildExecutionReceipt } from "../workbuddy/batch.mjs";
import { empty, setMetric } from "../metrics/parsers.mjs";
const sha = value => createHash("sha256").update(value).digest("hex");
const json = value => Buffer.from(`${JSON.stringify(value, null, 2)}\n`);
const profile = { id: "doubaowork", displayName: "DoubaoWork" };
const contained = (root, file) => file.startsWith(root + sep);

export async function validateFormalResume(state) {
  const batch = state.prepared?.mode === "web-native-batch-task/v1";
  if (!batch && state.prepared?.mode !== "web-native-single/v1") throw new Error("DOUBAOWORK_WEB_FROZEN_MODE_INVALID");
  const config = await validatePreparedTaskRoot(state.workspace, { resume: true, formal: true, batch });
  if (!state.prepared.initial?.sha256
      || batch && (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/u.test(state.prepared.run_id ?? "")
        || JSON.stringify(state.prepared.task_ids) !== JSON.stringify(config.manifest.tasks.map(t => t.task_id)))
      || config.manifestSha256 !== state.client.manifest_sha256 || config.promptSha256 !== state.prompt.sha256
      || config.taskId !== state.identity.task_id || config.batchId !== state.identity.batch_id) throw new Error("DOUBAOWORK_WEB_FROZEN_INPUT_DRIFT");
  return config;
}

export function projectWebMetrics(proof, calls) {
  const result = empty("NATIVE_TOKEN_AND_REQUEST_ACCOUNTING_UNAVAILABLE");
  const known = !proof.nonSuccess && Boolean(proof.nativeTools) && !proof.unknownBlocks.length && proof.remoteCoverageVerified;
  setMetric(result, "tools", "call_count", known ? calls : null, known ? "observed" : "partial", "Bound native tool IDs and session trajectory union");
  if (!known) {
    result.collection.metrics.call_count.status = "partial";
    result.collection.known_subtotals = { call_count: calls };
  }
  setMetric(result, "execution", "agent_duration_seconds", proof.native.agent_duration_seconds, "observed", "Native elapsed_block duration");
  const duration = proof.nonSuccess ? (Date.parse(proof.nonSuccess.observed_at) - Date.parse(proof.journal.timing.sent_at)) / 1000
    : proof.lifecycle?.status === "observed" ? proof.lifecycle.duration_seconds
    : proof.native.raw_terminal.profile === "native-im-api-history/v1" ? null
    : (Date.parse(proof.native.finished_at) - Date.parse(proof.journal.timing.sent_at)) / 1000;
  if (duration !== null && (!Number.isFinite(duration) || duration < 0)) throw new Error("DOUBAOWORK_WEB_INVALID_TIMING");
  result.collection.metrics.duration_seconds = { status: duration === null ? "unavailable" : "observed",
    basis: proof.nonSuccess ? "Dispatch to terminal observation; includes observer delay, not agent runtime"
      : proof.lifecycle?.status === "observed" ? proof.lifecycle.source : duration === null ? "Different native and controller clock domains" : proof.native.sources.finished_at };
  result.collection.tool_coverage = { numerator: calls, denominator: known ? calls : null };
  result.collection.trace_completeness = proof.completeToolTrace ? "complete" : "partial";
  result.collection.session_id = proof.native.conversation_id;
  result.collection.native_terminal_status = "verified";
  return { ...result, duration_seconds: duration };
}

async function assertStable(config, state, journalFile, journalBytes, proof, candidate) {
  if (sha(await readRegular(journalFile)) !== sha(journalBytes)
      || sha(await readRegular(config.manifestPath)) !== config.manifestSha256
      || sha(await readRegular(config.promptFile)) !== state.prompt.sha256
      || proof.trajectoryPath && sha(await readRegular(proof.trajectoryPath)) !== proof.source.sha256
      || proof.archiveIndexBytes && sha(await readRegular(proof.archiveIndexPath)) !== sha(proof.archiveIndexBytes)) throw new Error("DOUBAOWORK_WEB_COLLECTION_INPUT_DRIFT");
  const check = await snapshotTree(config.candidateWorkspace);
  if (check.sha256 !== candidate.sha256 || check.forbidden_directories.length) throw new Error("DOUBAOWORK_WEB_CANDIDATE_DRIFT");
}

export async function verifyFormalReceipt(outputDir) {
  const marker = JSON.parse(await readRegular(join(outputDir, "formal-publication.json")));
  const journal = JSON.parse(await readRegular(join(outputDir, "automation_state.json")));
  const config = await validateFormalResume(journal);
  if (marker.attempt_id !== journal.attempt_id || marker.manifest_sha256 !== config.manifestSha256) throw new Error("DOUBAOWORK_WEB_PUBLICATION_IDENTITY_DRIFT");
  for (const row of marker.files) {
    const path = resolve(config.harnessRoot, row.path);
    if (!contained(config.harnessRoot, path) || sha(await readRegular(path)) !== row.sha256) throw new Error("DOUBAOWORK_WEB_PUBLICATION_DRIFT");
  }
  const snapshot = await snapshotTree(config.candidateWorkspace);
  if (snapshot.sha256 !== marker.candidate_sha256 || snapshot.forbidden_directories.length) throw new Error("DOUBAOWORK_WEB_PUBLISHED_CANDIDATE_DRIFT");
  const batch = journal.prepared?.mode === "web-native-batch-task/v1";
  return { status: batch ? "BATCH_TASK_VERIFIED" : "FORMAL_RECEIPT_VERIFIED",
    receipt: batch ? null : join(config.harnessRoot, "execution-receipt.json"), attempt_id: journal.attempt_id };
}

export async function finalizeWebObservation({ state, record, outputDir, stateFile, observationPath, client }) {
  const config = await validateFormalResume(state);
  if (!contained(config.harnessRoot, outputDir) || contained(config.taskRoot, outputDir)) throw new Error("DOUBAOWORK_WEB_CONTROL_PATH_INVALID");
  const journalBytes = await readRegular(stateFile);
  if (JSON.parse(journalBytes).attempt_id !== state.attempt_id) throw new Error("DOUBAOWORK_WEB_JOURNAL_DRIFT");
  const proof = await readBoundNativeEvidence({ journalFile: stateFile, journal: state });
  const peers = state.prepared?.mode === "web-native-batch-task/v1"
    ? await managedPeerConversations(config, state.prepared.run_id) : { conversationIds: [], sessionIds: [], peers: [] };
  if (!client?.page || !client?.browser) throw new Error("DOUBAOWORK_WEB_LIVE_ACTIVITY_CONTEXT_MISSING");
  let frontend, background, activityError;
  for (let attempt = 0; attempt < 5; attempt++) {
    frontend = await readNativeActivity(client.page); background = await readNativeToolActivity(client.browser);
    try {
      assertNativeActivityAllowed(frontend, peers.conversationIds, peers.sessionIds);
      assertNativeToolActivityAllowed(background, peers.peers, frontend);
      activityError = null; break;
    } catch (error) {
      activityError = error;
      if (attempt < 4) await client.page.waitForTimeout(500);
    }
  }
  if (activityError) throw activityError;
  const observed = { ...record, native_frontend_activity: frontend, native_background_activity: background };
  // Validate current native/UI binding and idleness before any process is signalled.
  const preAssessment = assessDoubaoNativeWebFinalization({ state, observation: observed, native: proof.native,
    nonSuccess: proof.nonSuccess, allowedBackgroundPeers: peers.peers });
  if (preAssessment.reasons.some(reason => reason.startsWith("NATIVE_WEB_"))) throw new Error(`DOUBAOWORK_WEB_PRE_CLEANUP_GATE:${preAssessment.reasons.join(",")}`);
  const cleanup = await cleanupDoubaoCandidateProcesses(config.taskRoot);
  const candidate = await snapshotTree(config.candidateWorkspace);
  if (candidate.forbidden_directories.length) throw new Error("DOUBAOWORK_WEB_FORBIDDEN_CANDIDATE");
  const assessment = assessDoubaoNativeWebFinalization({ state, observation: observed, native: proof.native,
    nonSuccess: proof.nonSuccess, cleanup, candidate: { ...candidate, frozen: true }, allowedBackgroundPeers: peers.peers });
  const bridge = mapDoubaoAssessmentToWebReceiptBridge({ assessment, taskId: config.taskId, batchId: config.batchId,
    attemptId: state.attempt_id, model: state.actual.model });
  await atomicWriteJson(join(outputDir, `formal-assessment-${randomUUID()}.json`), { assessment, bridge, cleanup });
  if (!bridge.formal_execution_receipt_allowed) throw new Error(`DOUBAOWORK_WEB_FINALIZATION_REJECTED:${assessment.reasons.join(",")}`);
  const model = state.actual.model;
  if (!model || config.manifest.model?.id && !new Set([config.manifest.model.id, config.manifest.model.display_name]).has(model)) throw new Error("DOUBAOWORK_WEB_MODEL_DRIFT");
  const evidenceRoot = join(config.taskRoot, ".web-e2e-evidence", state.attempt_id);
  const staging = join(outputDir, `formal-staging-${randomUUID()}`);
  await mkdir(staging, { recursive: false });
  const raw = [];
  const write = async (path, bytes) => { await mkdir(dirname(join(staging, path)), { recursive: true }); await writeFile(join(staging, path), bytes, { flag: "wx", mode: 0o600 });
    const row = { path, sha256: sha(bytes), size_bytes: bytes.length }; raw.push(row); return row; };
  await write("raw/dispatch-journal.json", journalBytes);
  await write("raw/terminal-observation.json", await readRegular(observationPath));
  await write("raw/live-activity.json", json({ observed_at: new Date().toISOString(), frontend, background,
    admitted_peer_identity_hashes: peers.peers.map(peer => sha(Buffer.from(`${peer.conversation_id}:${peer.native_request_session_id}:${peer.workspace}`))) }));
  await write("raw/runtime-messages.json", proof.runtimeBytes);
  for (const [name, bytes] of [["trajectory.jsonl", proof.trajectory], ["native-tools.json", proof.nativeToolBytes], ["native-lifecycle.json", proof.lifecycleBytes],
    ["recovered-send-ack.json", proof.recoveryAckBytes], ["native-terminal-observation.json", proof.terminalObservationBytes]]) if (bytes) await write(`raw/${name}`, bytes);
  for (const row of proof.archiveRaw) await write(row.path, row.bytes);
  await write("raw/native-resource-observations.json", json(proof.nativeResourceObservations));
  await write("final-response.txt", proof.finalBytes);
  await write("final.png", await boundArtifact(outputDir, record.artifacts.screenshot));
  const transcript = [{ type: "user_message", content: config.prompt, source: "raw/runtime-messages.json" },
    ...proof.timeline.entries.map(entry => ({ type: "native_tool_or_message", ...entry })),
    { type: "assistant_message", content: proof.native.final_text, source: "raw/runtime-messages.json" }];
  await write("transcript.jsonl", Buffer.from(transcript.map(row => JSON.stringify(row)).join("\n") + "\n"));
  const callIds = new Set([...proof.nativeCalls.keys(), ...proof.remoteCalls.map(row => row.call_id)]);
  const metrics = projectWebMetrics({ ...proof, journal: state }, callIds.size);
  metrics.collection.sources = raw.map(row => ({ ...row, path: relative(config.taskRoot, join(evidenceRoot, row.path)) }));
  await write("resource-metrics.json", json(metrics));
  await write("finalizer.json", json({ assessment, bridge, cleanup }));
  await write("trace-index.json", json({ schema: "wildclawbench.doubaowork-web-trace/v1", attempt_id: state.attempt_id,
    identity: state.identity, raw: [...raw], completeness: proof.completeToolTrace ? "complete" : "partial", tool_order_basis: proof.timeline.basis,
    tool_known_subtotal: callIds.size, duplicate_events: proof.legacy.duplicates, multimodal_result_content_unverified: proof.multimodalBypassCount }));
  await assertStable(config, state, stateFile, journalBytes, proof, candidate);
  const phase = proof.nonSuccess ? "INFRA_FAILED" : "SUCCEEDED";
  const finishedAt = proof.nonSuccess?.observed_at ?? proof.native.finished_at;
  const formalState = { ...state, phase, terminal: true, driver: { ...state.driver, version: DRIVER_VERSION },
    timing: { ...state.timing, started_at: state.timing.sent_at, finished_at: finishedAt, duration_seconds: metrics.duration_seconds },
    model_selection: { mode: "current", actual_model: model, method: "native-ui-readback" },
    permission_selection: { actual_mode: state.actual.permission_mode },
    prompt_sha256: state.prompt.sha256, prompt_bytes: state.prompt.size_bytes ?? config.promptBytes,
    terminal_process_cleanup: cleanup, artifacts: { initial: state.prepared.initial, final: candidate },
    error: proof.nonSuccess ? proof.nonSuccess.business_status : null,
    evidence: { terminal_source: "bound-native-im+native-lifecycle", final_screenshot_path: join(evidenceRoot, "final.png"),
      transcript_path: join(evidenceRoot, "transcript.jsonl"), screenshots: [join(evidenceRoot, "final.png")] } };
  const automationFile = join(outputDir, "formal-automation-state.json");

  const executionFile = join(config.taskRoot, "execution_record.json");
  const execution = createExecutionRecord({ batchId: config.batchId, taskId: config.taskId, harness: config.manifest.harness,
    model: { id: model, display_name: model } }, profile);
  execution.harness.version = state.client.version;
  execution.execution = { status: proof.nonSuccess ? "execution_error" : "completed", started_at: state.timing.sent_at, finished_at: finishedAt,
    duration_seconds: metrics.duration_seconds, agent_duration_seconds: metrics.execution.agent_duration_seconds, error: formalState.error };
  execution.usage = { ...execution.usage, ...metrics.usage, collection: metrics.collection };
  execution.tools = { ...execution.tools, ...metrics.tools };
  execution.artifacts.harness_transcript = relative(config.taskRoot, join(evidenceRoot, "transcript.jsonl"));
  const oldBytes = await readRegular(executionFile).catch(e => { if (e.code !== "ENOENT") throw e; return null; });
  const old = oldBytes ? JSON.parse(oldBytes) : null;
  if (old && (old.execution?.status !== "pending" || old.batch_id !== config.batchId || old.task_id !== config.taskId || old.harness?.id !== "doubaowork")) throw new Error("DOUBAOWORK_WEB_EXECUTION_RECORD_CONFLICT");

  const batch = state.prepared.mode === "web-native-batch-task/v1";
  const queueFile = join(outputDir, "single-task-state.json");
  let queue = null, receipt = null;
  const receiptFile = join(config.harnessRoot, "execution-receipt.json");
  if (!batch) {
    queue = { run_id: state.attempt_id, phase: proof.nonSuccess ? "COMPLETED_WITH_FAILURES" : "COMPLETED", ui_slots: 1, run_slots: 1,
    worker: { id: "doubaowork-native-single", version: DRIVER_VERSION }, requested_ui_model: null,
    requested_endpoint: state.client.endpoint, requested_app_path: state.client.app_path, requested_permission_mode: "current",
    tasks: [{ task_id: config.taskId, manual_interventions: [] }] };

    receipt = await buildExecutionReceipt({ harnessRoot: config.harnessRoot, manifest: config.manifest, queueStateFile: queueFile,
    tasks: [{ taskId: config.taskId, taskRoot: config.taskRoot, automationStateFile: automationFile, executionRecordFile: executionFile }] }, queue, { harnessId: "doubaowork", readRecord: async path => path === automationFile ? formalState : path === executionFile ? execution : null });
  if (!receipt.integrity.valid) throw new Error("DOUBAOWORK_WEB_RECEIPT_INTEGRITY_FAILED");
  await assertStable(config, state, stateFile, journalBytes, proof, candidate);
  }
  const rows = raw.map(row => ({ path: relative(config.harnessRoot, join(evidenceRoot, row.path)),
    staged_path: relative(config.harnessRoot, join(staging, row.path)), sha256: row.sha256 }));
  const publications = [["automation.json", automationFile, formalState, null],
    ["execution.json", executionFile, execution, oldBytes]];
  if (!batch) publications.push(["single-task.json", queueFile, queue, null], ["receipt.json", receiptFile, receipt, null]);
  for (const [name, path, value, previous] of publications) {
    const stagedPath = join(staging, name), bytes = json(value);
    await writeFile(stagedPath, bytes, { flag: "wx", mode: 0o600 });
    rows.push({ path: relative(config.harnessRoot, path), staged_path: relative(config.harnessRoot, stagedPath),
      sha256: sha(bytes), previous_sha256: previous ? sha(previous) : null });
  }
  const prerequisites = await Promise.all([stateFile, observationPath, config.manifestPath, config.promptFile].map(async path =>
    ({ path: relative(config.harnessRoot, path), sha256: sha(await readRegular(path)) })));
  await writeFile(join(outputDir, "formal-transaction.json"), json({ schema: "wildclawbench.doubaowork-web-publication/v1",
    harness_root: config.harnessRoot, attempt_id: state.attempt_id, manifest_sha256: config.manifestSha256,
    candidate_path: relative(config.harnessRoot, config.candidateWorkspace), candidate_sha256: candidate.sha256,
    prerequisites, files: rows }), { flag: "wx", mode: 0o600 });
  await publishFrozenTransaction(outputDir);
  return verifyFormalReceipt(outputDir);
}
