export const RECEIPT_BRIDGE_SCHEMA =
  "wildclawbench.doubaowork-web-receipt-bridge/v1";

const REQUIRED_REASONS = new Set([
  "UI_EQUIVALENT_BINDING_UNVERIFIED",
  "NATIVE_EVIDENCE_MISSING",
  "NATIVE_EVIDENCE_IDENTITY_MISMATCH",
  "PROCESS_CLEANUP_UNVERIFIED",
  "CANDIDATE_FREEZE_UNVERIFIED",
]);

function valueOrNull(value) {
  return typeof value === "string" && value.trim() ? value : null;
}

function assessmentGate(assessment) {
  const reasons = Array.isArray(assessment?.reasons) ? assessment.reasons : [];
  const requiredReasons = reasons.filter((reason) => REQUIRED_REASONS.has(reason));
  const valid = assessment?.integrity?.valid === true
    && assessment?.formal_execution_receipt_allowed === true
    && requiredReasons.length === 0;
  return { valid, reasons: requiredReasons };
}

/**
 * Map a Doubao finalizer assessment to the public Web v1 field vocabulary.
 *
 * This is an in-memory bridge only. It does not read or write execution
 * records/receipts and never upgrades UI evidence into native terminal/cwd.
 */
export function mapDoubaoAssessmentToWebReceiptBridge({
  assessment,
  taskId = null,
  batchId = null,
  attemptId = null,
  model = null,
} = {}) {
  const gate = assessmentGate(assessment);
  const status = gate.valid ? "READY_FOR_WEB_RECEIPT" : "NEEDS_ATTENTION";
  const terminalStatus = valueOrNull(assessment?.native?.terminal_status) ?? "unavailable";
  const cwdStatus = valueOrNull(assessment?.native?.cwd_status) ?? "unavailable";
  const reasons = [...new Set([
    ...gate.reasons,
    ...(gate.valid ? [] : ["DOUBAO_RECEIPT_BRIDGE_GATE_FAILED"]),
  ])];

  return {
    schema: RECEIPT_BRIDGE_SCHEMA,
    status,
    formal_execution_receipt_allowed: gate.valid,
    public_mapping: {
      task_id: taskId,
      batch_id: batchId,
      attempt_id: attemptId,
      automation_phase: gate.valid ? "SUCCEEDED" : "NEEDS_ATTENTION",
      execution_status: gate.valid ? "completed" : "pending",
      model: model || null,
      terminal: {
        status: terminalStatus,
        verified: terminalStatus === "verified",
      },
      workspace_binding: {
        status: cwdStatus,
        verified: cwdStatus === "verified"
          && assessment?.native?.cwd_verified === true,
      },
    },
    identity: assessment?.identity ?? null,
    integrity: {
      valid: gate.valid,
      equivalent_web_binding: assessment?.integrity?.equivalent_web_binding === true,
      native_terminal_verified: assessment?.integrity?.native_terminal_verified === true,
      native_cwd_verified: assessment?.integrity?.native_cwd_verified === true,
      process_cleanup_verified: assessment?.integrity?.process_cleanup_verified === true,
      candidate_frozen: assessment?.integrity?.candidate_frozen === true,
    },
    reasons,
    source_assessment_schema: assessment?.schema ?? null,
  };
}
