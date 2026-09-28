// Reconcile the execution projection with the bound native main-turn log.
// Tool errors alone are not final agent errors, and an aborted turn is not a
// successful execution even when a stale state file says COMPLETED.
import { verifyQwenSessionSnapshot } from "../../vendor/e2e-shared/qwenwork-native-state/index.mjs";

export function verifyQwenNativeTerminal(state, rows, { nativeSnapshot = null, transcriptRows = [] } = {}) {
  const starts = rows.filter(row => row.type === "turn.started" && row.data?.is_subagent !== true);
  const turnIds = [...new Set(starts.map(row => row.turn_id).filter(Boolean))];
  if (turnIds.length !== 1) throw Error("QWENWORK_TERMINAL_MAIN_TURN_AMBIGUOUS");
  const finishes = rows.filter(row => row.type === "turn.finished" && row.turn_id === turnIds[0]);
  const native = String(state.extensions?.qwenwork?.native_status || "").toLowerCase().replace(/[\s_-]+/gu, "");
  const business = state.execution?.business_status;
  if (native === "interrupted") {
    verifyQwenSessionSnapshot(nativeSnapshot, state);
    if (finishes.length === 0 && state.phase === "FAILED" && business === "infrastructure_error"
        && state.execution.error?.code === "QWENWORK_INTERRUPTED") {
      return { verified: true, mode: "native-interruption-without-finish", native_turn_id: turnIds[0],
        finish_reason: null, native_status: native, business_status: business,
        raw_ref: "raw/native-session-snapshot.json", raw_line: null,
        native_finish_present: false, metrics_complete: false };
    }
  }
  if (finishes.length !== 1) throw Error("QWENWORK_TERMINAL_FINISH_UNVERIFIED");
  const finish = finishes[0], reason = finish.data?.reason;
  // A protection hook can stop continuation without a model final reply. The
  // SDK still emits end_turn, while the desktop stores failed. Require all
  // native sources, exact tool identity and a fresh database snapshot.
  if (state.phase === "FAILED" && business === "infrastructure_error"
      && native === "failed" && reason === "end_turn"
      && state.execution.error?.code === "QWENWORK_NATIVE_FAILURE") {
    verifyQwenSessionSnapshot(nativeSnapshot, state);
    const stopped = transcriptRows.filter(row => row.type === "attachment"
      && row.attachment?.type === "hook_stopped_continuation"
      && row.attachment?.message === "Sensitive tool output protection failed. The turn was stopped before continuing to the model."
      && row.attachment?.hookEvent === "PostToolUse"
      && row.sessionId === state.session.session_id && row.cwd === state.session.cwd);
    if (stopped.length !== 1) throw Error("QWENWORK_PROTECTION_STOP_NOT_UNIQUE");
    const stop = stopped[0], callId = stop.attachment.toolUseID;
    const requested = rows.filter(row => row.type === "tool.requested"
      && row.turn_id === turnIds[0] && row.tool_call_id === callId);
    const hook = rows.filter(row => row.type === "hook.finished"
      && row.tool_call_id === callId && row.data?.hook_name === stop.attachment.hookName
      && row.data?.hook_event_name === "PostToolUse");
    const after = transcriptRows.filter(row => row.type === "assistant"
      && Date.parse(row.timestamp) > Date.parse(stop.timestamp));
    if (requested.length !== 1 || hook.length === 0 || after.length !== 0
        || !(Date.parse(finish.ts) >= Date.parse(stop.timestamp))) {
      throw Error("QWENWORK_PROTECTION_STOP_BINDING_INVALID");
    }
    return { verified: true, mode: "native-protection-hook-stopped", native_turn_id: turnIds[0],
      finish_reason: reason, native_status: native, business_status: business,
      raw_ref: finish.__raw_path ?? null, raw_line: finish.__raw_line ?? null,
      stop_raw_ref: stop.__raw_path ?? null, stop_raw_line: stop.__raw_line ?? null,
      stop_event_uuid: stop.uuid, tool_call_id: callId, native_snapshot_required: true };
  }
  let matched = false;
  if (business === "completed") {
    matched = state.phase === "COMPLETED" && ["end_turn", "completed"].includes(reason)
      && ["completed", "complete", "succeeded", "success", "finished", "done"].includes(native);
  } else if (business === "cancelled") {
    matched = state.phase === "FAILED" && reason === "abort" && state.execution.cancellation_confirmed === true
      && ["cancelled", "canceled", "aborted", "terminated", "stopped"].includes(native);
  } else if (business === "infrastructure_error") {
    matched = state.phase === "FAILED" && (
      reason === "error" && ["failed", "failure", "error", "errored"].includes(native)
        && state.execution.error?.code === "QWENWORK_NATIVE_FAILURE"
      || ["abort", "error"].includes(reason) && native === "interrupted"
        && state.execution.error?.code === "QWENWORK_INTERRUPTED");
  }
  if (!matched) throw Error("QWENWORK_NATIVE_TERMINAL_MISMATCH_OR_UNSUPPORTED");
  return { verified: true, native_turn_id: turnIds[0], finish_reason: reason, native_status: native,
    business_status: business, raw_ref: finish.__raw_path ?? null, raw_line: finish.__raw_line ?? null };
}
