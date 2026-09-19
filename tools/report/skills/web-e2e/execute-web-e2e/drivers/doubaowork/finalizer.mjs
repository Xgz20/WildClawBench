import { createHash } from "node:crypto";

import { NATIVE_EVIDENCE_SCHEMA } from "./lib.mjs";

export const FINALIZER_ASSESSMENT_SCHEMA =
  "wildclawbench.doubaowork-web-finalizer-assessment/v1";

const UI_COMPLETION_KIND = "ui-completion-candidate";

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stringValue(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function assessUiBinding({ state, observation }) {
  const binding = observation?.binding ?? null;
  const ui = observation?.ui ?? observation?.snapshot ?? null;
  const classification = observation?.classification ?? null;
  const stableCount = Number(observation?.stable_completion_observations ?? 0);
  // The prepared Prompt digest is not a post-send conversation readback.
  // Only the state-side verified marker proves the bound conversation echoed it.
  const promptVerified = state?.session?.prompt_readback?.status === "verified";
  const workspaceVerified = state?.workspace_selection?.confirmed === true
    && state.workspace_selection.actual_path === state.workspace
    && state.workspace_selection.source === "project-folder-tooltip";
  const currentConversationMatches = Boolean(
    state?.session?.conversation_id
      && ui?.current_conversation_id === state.session.conversation_id,
  );
  const projectMatches = Boolean(
    state?.client?.project_id_sha256
      && ui?.conversation_project_id_sha256 === state.client.project_id_sha256
      && ui?.current_project_control_count === 1
      && ui?.current_project_name === state.client.project_name,
  );
  const statusVerified = binding?.status === "verified";
  const classificationVerified = classification?.kind === UI_COMPLETION_KIND
    && classification?.trusted === false;
  const uiCompletion = classificationVerified
    && stableCount >= 3
    && ui?.stop_control_count === 0
    && ui?.bound_conversation_busy_count === 0
    && ui?.visible_dialog_count === 0
    && ui?.user_question_count === 0
    && ui?.approval_count === 0
    && ui?.visible_error_count === 0
    && ui?.positive_completion_marker_count > 0;
  return {
    verified: statusVerified && currentConversationMatches && projectMatches
      && workspaceVerified && promptVerified && uiCompletion,
    binding_status: binding?.status ?? "unverified",
    current_conversation_matches: currentConversationMatches,
    project_matches: projectMatches,
    workspace_verified: workspaceVerified,
    prompt_verified: promptVerified,
    completion_candidate: classification?.kind === UI_COMPLETION_KIND,
    stable_completion_observations: stableCount,
    ui_completion: uiCompletion,
  };
}

function assessNativeEvidence({ state, nativeEvidence }) {
  const identity = nativeEvidence?.identity ?? null;
  const conversationMatches = Boolean(
    state?.session?.conversation_id
      && identity?.conversation_id === state.session.conversation_id,
  );
  const sessionMatches = Boolean(
    state?.session?.session_directory_id
      && identity?.session_directory_id === state.session.session_directory_id,
  );
  const workspaceMatches = Boolean(
    identity?.requested_workspace === state?.workspace
      || identity?.workspace_binding?.requested_path === state?.workspace,
  );
  const present = nativeEvidence?.schema === NATIVE_EVIDENCE_SCHEMA;
  const terminalStatus = stringValue(nativeEvidence?.terminal?.status) ?? "unavailable";
  const cwdStatus = stringValue(nativeEvidence?.identity?.workspace_binding?.status)
    ?? stringValue(nativeEvidence?.native_capabilities?.workspace_binding?.status)
    ?? "unavailable";
  return {
    present,
    identity_matches: present && conversationMatches && sessionMatches && workspaceMatches,
    conversation_matches: conversationMatches,
    session_matches: sessionMatches,
    workspace_matches: workspaceMatches,
    terminal_status: terminalStatus,
    terminal_verified: terminalStatus === "verified",
    cwd_status: cwdStatus,
    cwd_verified: cwdStatus === "verified"
      && typeof nativeEvidence?.identity?.native_cwd === "string"
      && nativeEvidence.identity.native_cwd.startsWith("/"),
  };
}

function assessCleanup(cleanup) {
  const supported = cleanup?.supported === true;
  const success = cleanup?.success === true;
  const noTrackedResidue = Array.isArray(cleanup?.tracked_residue)
    && cleanup.tracked_residue.length === 0;
  const noAfterTargets = Array.isArray(cleanup?.after?.targets)
    && cleanup.after.targets.length === 0;
  const quietWindow = Number(cleanup?.quiet_window_milliseconds);
  const quietObserved = Number(cleanup?.quiet_observed_milliseconds);
  const quietComplete = Number.isFinite(quietWindow)
    && quietWindow >= 0
    && Number.isFinite(quietObserved)
    && quietObserved >= quietWindow;
  return {
    supported,
    success,
    no_tracked_residue: noTrackedResidue,
    no_after_targets: noAfterTargets,
    quiet_window_complete: quietComplete,
    verified: supported && success && noTrackedResidue && noAfterTargets && quietComplete,
    error_code: cleanup?.error_code ?? null,
  };
}

function assessCandidate(candidate) {
  const frozen = candidate?.frozen === true;
  const sha = stringValue(candidate?.sha256);
  return {
    frozen,
    sha256: sha,
    verified: frozen && /^[0-9a-f]{64}$/u.test(sha ?? ""),
  };
}

/**
 * Assess whether a DoubaoWork UI completion can enter the existing Web v1
 * execution receipt. This adapter never manufactures native terminal/cwd.
 * Missing native evidence, cleanup, or candidate freeze is always invalid.
 */
export function assessDoubaoWebFinalization({
  state,
  observation,
  nativeEvidence = null,
  cleanup = observation?.terminal_process_cleanup ?? state?.terminal_process_cleanup ?? null,
  candidate = null,
  now = new Date(),
} = {}) {
  const ui = assessUiBinding({ state, observation });
  const native = assessNativeEvidence({ state, nativeEvidence });
  const processCleanup = assessCleanup(cleanup);
  const candidateAssessment = assessCandidate(candidate);
  const reasons = [];
  if (!ui.verified) reasons.push("UI_EQUIVALENT_BINDING_UNVERIFIED");
  if (!native.present) reasons.push("NATIVE_EVIDENCE_MISSING");
  else if (!native.identity_matches) reasons.push("NATIVE_EVIDENCE_IDENTITY_MISMATCH");
  if (!processCleanup.verified) reasons.push("PROCESS_CLEANUP_UNVERIFIED");
  if (!candidateAssessment.verified) reasons.push("CANDIDATE_FREEZE_UNVERIFIED");

  const valid = ui.verified && native.present && native.identity_matches
    && processCleanup.verified && candidateAssessment.verified;
  return {
    schema: FINALIZER_ASSESSMENT_SCHEMA,
    generated_at: (now instanceof Date ? now : new Date(now)).toISOString(),
    status: valid ? "READY_FOR_WEB_RECEIPT" : "NEEDS_ATTENTION",
    formal_execution_receipt_allowed: valid,
    identity: {
      batch_id: state?.identity?.batch_id ?? null,
      task_id: state?.identity?.task_id ?? null,
      attempt_id: state?.attempt_id ?? null,
      harness_id: "doubaowork",
      conversation_id_sha256: state?.session?.conversation_id
        ? sha256(state.session.conversation_id) : null,
      session_directory_id_sha256: state?.session?.session_directory_id
        ? sha256(state.session.session_directory_id) : null,
    },
    ui,
    native,
    process_cleanup: processCleanup,
    candidate: candidateAssessment,
    integrity: {
      valid,
      equivalent_web_binding: ui.verified && native.present && native.identity_matches,
      native_terminal_verified: native.terminal_verified,
      native_cwd_verified: native.cwd_verified,
      process_cleanup_verified: processCleanup.verified,
      candidate_frozen: candidateAssessment.verified,
    },
    reasons,
    warnings: [
      ...(native.present && !native.terminal_verified ? ["NATIVE_TERMINAL_REMAINS_UNVERIFIED"] : []),
      ...(native.present && !native.cwd_verified ? ["NATIVE_CWD_REMAINS_UNVERIFIED"] : []),
    ],
  };
}
