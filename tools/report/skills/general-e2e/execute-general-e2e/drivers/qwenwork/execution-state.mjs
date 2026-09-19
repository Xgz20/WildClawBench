import { resolve } from "node:path";

import {
  buildQwenGeneralSessionBinding,
  classifyQwenSessionStatus,
  QWENWORK_GENERAL_DRIVER_VERSION,
} from "./session-state.mjs";

export const GENERAL_EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-execution-state/v1";

function terminalMapping(session, cancellationConfirmed) {
  const classification = session?.classification
    || classifyQwenSessionStatus(session?.native_status, session?.stream_id);
  if (classification.business_status === "completed") {
    return { phase: "COMPLETED", business_status: "completed", error: null, cancellation_confirmed: null };
  }
  if (classification.business_status === "cancelled") {
    return {
      phase: cancellationConfirmed === true ? "FAILED" : "NEEDS_ATTENTION",
      business_status: cancellationConfirmed === true ? "cancelled" : null,
      error: cancellationConfirmed === true
        ? { code: "QWENWORK_CANCELLED", message: "QwenWork reported a confirmed cancelled terminal state" }
        : null,
      cancellation_confirmed: cancellationConfirmed === true ? true : null,
    };
  }
  if (classification.business_status === "execution_error") {
    return {
      phase: "FAILED",
      business_status: "infrastructure_error",
      error: { code: "QWENWORK_NATIVE_FAILURE", message: `QwenWork native terminal state: ${classification.native_status}` },
      cancellation_confirmed: null,
    };
  }
  if (classification.business_status === "interrupted") {
    return {
      phase: "FAILED",
      business_status: "infrastructure_error",
      error: { code: "QWENWORK_INTERRUPTED", message: "QwenWork reported an interrupted terminal state" },
      cancellation_confirmed: null,
    };
  }
  if (classification.kind === "running") {
    return { phase: "RUNNING", business_status: null, error: null, cancellation_confirmed: null };
  }
  return { phase: "NEEDS_ATTENTION", business_status: null, error: null, cancellation_confirmed: null };
}

export function buildQwenGeneralExecutionState({
  identity,
  dataset,
  taskRoot,
  candidateWorkspace,
  prompt,
  dispatchAttemptCount,
  session,
  bindingEvidence,
  startedAt = null,
  finishedAt = null,
  durationSeconds = null,
  cancellationConfirmed = null,
  humanAssistance = null,
  runtimeIdentity = null,
  recovery = null,
}) {
  let sessionBinding = buildQwenGeneralSessionBinding(session || {}, bindingEvidence);
  let mapping = terminalMapping(session || {}, cancellationConfirmed);
  if (prompt?.send_status === "intent_persisted" || prompt?.send_status === "uncertain") {
    mapping = { phase: "NEEDS_ATTENTION", business_status: null, error: null, cancellation_confirmed: null };
  } else if (prompt?.send_status === "not_sent") {
    if (dispatchAttemptCount !== 0) throw new Error("QWENWORK_NOT_SENT_DISPATCH_MISMATCH");
    sessionBinding = {
      thread_id: null,
      turn_id: null,
      session_id: null,
      cwd: null,
      verified: false,
      binding_evidence: [],
    };
    mapping = {
      phase: "FAILED",
      business_status: "infrastructure_error",
      error: { code: "QWENWORK_NOT_SENT", message: "QwenWork prompt was not sent" },
      cancellation_confirmed: null,
    };
  }
  if (prompt?.send_status === "sent" && dispatchAttemptCount !== 1) {
    throw new Error("QWENWORK_SENT_DISPATCH_MISMATCH");
  }
  if (["COMPLETED", "FAILED"].includes(mapping.phase) && !sessionBinding.verified
      && prompt?.send_status === "sent") {
    mapping = { phase: "NEEDS_ATTENTION", business_status: null, error: null, cancellation_confirmed: null };
  }
  return {
    schema_version: GENERAL_EXECUTION_STATE_SCHEMA,
    driver: {
      id: "qwenwork-macos-general",
      version: QWENWORK_GENERAL_DRIVER_VERSION,
      harness: "qwenwork",
      platform: "macos",
    },
    identity: {
      batch_id: identity.batch_id,
      unit_id: identity.unit_id,
      task_id: identity.task_id,
      attempt_id: identity.attempt_id,
    },
    dataset: { id: dataset.id, digest: dataset.digest },
    phase: mapping.phase,
    task_root: resolve(taskRoot),
    candidate_workspace: resolve(candidateWorkspace),
    prompt: {
      path: resolve(prompt.path),
      sha256: prompt.sha256,
      send_status: prompt.send_status,
      sent_at: prompt.sent_at ?? null,
    },
    send: { dispatch_attempt_count: dispatchAttemptCount },
    session: sessionBinding,
    execution: {
      business_status: mapping.business_status,
      started_at: startedAt,
      finished_at: mapping.phase === "RUNNING" || mapping.phase === "NEEDS_ATTENTION" ? null : finishedAt,
      duration_seconds: mapping.phase === "RUNNING" || mapping.phase === "NEEDS_ATTENTION" ? null : durationSeconds,
      error: mapping.error,
      cancellation_confirmed: mapping.cancellation_confirmed,
    },
    human_assistance: humanAssistance || {
      mode: "automatic",
      operation_count: 0,
      semantic_intervention_count: 0,
    },
    extensions: {
      qwenwork: {
        conversation_id: session?.conversation_id || null,
        sub_chat_id: session?.sub_chat_id || null,
        local_project_id: session?.local_project_id || null,
        native_status: session?.native_status || null,
        stream_id_present: Boolean(session?.stream_id),
        model_level: session?.model_level || null,
        runtime_identity: runtimeIdentity,
        recovery,
      },
    },
  };
}
