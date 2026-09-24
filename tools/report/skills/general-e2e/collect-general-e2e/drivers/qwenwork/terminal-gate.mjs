// Reconcile the execution projection with the bound native main-turn log.
// Tool errors alone are not final agent errors, and an aborted turn is not a
// successful execution even when a stale state file says COMPLETED.
export function verifyQwenNativeTerminal(state, rows) {
  const starts = rows.filter(row => row.type === "turn.started" && row.data?.is_subagent !== true);
  const turnIds = [...new Set(starts.map(row => row.turn_id).filter(Boolean))];
  if (turnIds.length !== 1) throw Error("QWENWORK_TERMINAL_MAIN_TURN_AMBIGUOUS");
  const finishes = rows.filter(row => row.type === "turn.finished" && row.turn_id === turnIds[0]);
  if (finishes.length !== 1) throw Error("QWENWORK_TERMINAL_FINISH_UNVERIFIED");
  const finish = finishes[0], reason = finish.data?.reason;
  const native = String(state.extensions?.qwenwork?.native_status || "").toLowerCase().replace(/[\s_-]+/gu, "");
  const business = state.execution?.business_status;
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
