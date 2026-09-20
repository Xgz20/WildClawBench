import { resolve } from "node:path";

export const WORKBUDDY_EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-execution-state/v1";
export const WORKBUDDY_DRIVER_ID = "workbuddy-macos-general";
export const WORKBUDDY_DRIVER_VERSION = "0.1.0";

const SUCCESS_STATES = new Set(["complete", "completed", "success", "succeeded"]);
const FAILURE_STATES = new Set(["failed", "failure", "error", "errored"]);
const CANCELLED_STATES = new Set(["cancelled", "canceled", "aborted"]);
const INTERRUPTED_STATES = new Set(["interrupted"]);
const RUNNING_STATES = new Set(["created", "pending", "queued", "running", "working", "streaming", "processing", "active"]);

function assertObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} 必须是对象`);
  return value;
}

function assertString(value, label) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} 必须是非空字符串`);
  return value;
}

function classify(value) {
  const raw = String(value || "").trim();
  const normalized = raw.toLowerCase();
  if (SUCCESS_STATES.has(normalized)) return "success";
  if (FAILURE_STATES.has(normalized)) return "failure";
  if (CANCELLED_STATES.has(normalized)) return "cancelled";
  if (INTERRUPTED_STATES.has(normalized)) return "interrupted";
  if (RUNNING_STATES.has(normalized)) return "running";
  return raw ? "unknown" : "missing";
}

function isoFromEpoch(value) {
  return Number.isFinite(value) ? new Date(value).toISOString() : null;
}

function isoTimestamp(value) {
  if (!value) return null;
  const timestamp = new Date(value);
  if (!Number.isFinite(timestamp.getTime())) throw new Error(`无效时间：${value}`);
  return timestamp.toISOString();
}

function durationSeconds(startedAt, finishedAt) {
  if (!startedAt || !finishedAt) return null;
  const value = (Date.parse(finishedAt) - Date.parse(startedAt)) / 1000;
  if (!Number.isFinite(value) || value < 0) throw new Error("WorkBuddy 完成时间早于开始时间");
  return value;
}

export function buildWorkBuddyExecutionState({
  identity,
  dataset,
  taskRoot,
  candidateWorkspace,
  prompt,
  send,
  sessionSnapshot,
  history,
  bindingEvidence,
  cancellationConfirmed = false,
  humanAssistance = { mode: "automatic", operation_count: 0, semantic_intervention_count: 0 },
}) {
  assertObject(identity, "identity");
  assertObject(dataset, "dataset");
  assertObject(prompt, "prompt");
  assertObject(send, "send");
  assertObject(sessionSnapshot, "sessionSnapshot");
  assertObject(history, "history");
  const workspace = resolve(assertString(candidateWorkspace, "candidateWorkspace"));
  const nativeCwd = resolve(assertString(sessionSnapshot.cwd, "sessionSnapshot.cwd"));
  if (workspace !== nativeCwd) throw new Error("WORKBUDDY_SESSION_CWD_MISMATCH");
  const conversationId = assertString(sessionSnapshot.conversation_id, "sessionSnapshot.conversation_id");
  if (history.binding?.conversation_id !== conversationId) {
    throw new Error("WORKBUDDY_CONVERSATION_ID_MISMATCH");
  }
  const requestId = assertString(history.binding?.request_id, "history.binding.request_id");
  if (prompt.sha256 !== history.prompt?.sha256) throw new Error("WORKBUDDY_PROMPT_HASH_MISMATCH");
  if (prompt.send_status !== "sent" || send.dispatch_attempt_count !== 1 || !prompt.sent_at) {
    throw new Error("WORKBUDDY_SEND_NOT_RECONCILED");
  }
  if (!Array.isArray(bindingEvidence) || bindingEvidence.length === 0) {
    throw new Error("WORKBUDDY_BINDING_EVIDENCE_MISSING");
  }

  const sessionKind = classify(sessionSnapshot.status);
  const requestKind = classify(history.binding?.request_state?.raw);
  let phase = "NEEDS_ATTENTION";
  let businessStatus = null;
  let error = null;
  if (sessionKind === "success" && requestKind === "success" && history.completeness?.status === "complete") {
    phase = "COMPLETED";
    businessStatus = "completed";
  } else if (sessionKind === "running" && requestKind === "running") {
    phase = "RUNNING";
  } else if (sessionKind === "failure" && requestKind === "failure") {
    phase = "FAILED";
    businessStatus = "candidate_error";
    error = {
      code: "WORKBUDDY_NATIVE_FAILURE",
      message: `session=${sessionSnapshot.status || "missing"}; request=${history.binding?.request_state?.raw || "missing"}`,
    };
  } else if (
    sessionKind === "cancelled"
    && requestKind === "cancelled"
    && cancellationConfirmed === true
  ) {
    phase = "FAILED";
    businessStatus = "cancelled";
    error = {
      code: "WORKBUDDY_NATIVE_CANCELLED",
      message: `session=${sessionSnapshot.status}; request=${history.binding.request_state.raw}; cancellation_confirmed=true`,
    };
  } else {
    const code = sessionKind === "interrupted" || requestKind === "interrupted"
      ? "WORKBUDDY_INTERRUPTION_UNVERIFIED"
      : sessionKind === "cancelled" || requestKind === "cancelled"
        ? "WORKBUDDY_CANCELLATION_UNCONFIRMED"
        : sessionKind === "failure" || requestKind === "failure"
          ? "WORKBUDDY_TERMINAL_STATE_CONFLICT"
          : "WORKBUDDY_TERMINAL_STATE_UNVERIFIED";
    error = {
      code,
      message: `session=${sessionSnapshot.status || "missing"}; request=${history.binding?.request_state?.raw || "missing"}; trace=${history.completeness?.status || "missing"}`,
    };
  }

  const startedAt = isoFromEpoch(history.request?.startedAt)
    || isoTimestamp(prompt.sent_at);
  const finishedAt = new Set(["COMPLETED", "FAILED"]).has(phase)
    ? isoTimestamp(history.conversation?.lastMessageAt)
    : null;
  return {
    schema_version: WORKBUDDY_EXECUTION_STATE_SCHEMA,
    driver: {
      id: WORKBUDDY_DRIVER_ID,
      version: WORKBUDDY_DRIVER_VERSION,
      harness: "workbuddy",
      platform: "macos",
    },
    identity,
    dataset,
    phase,
    task_root: resolve(assertString(taskRoot, "taskRoot")),
    candidate_workspace: workspace,
    prompt: {
      path: resolve(assertString(prompt.path, "prompt.path")),
      sha256: assertString(prompt.sha256, "prompt.sha256"),
      send_status: "sent",
      sent_at: isoTimestamp(prompt.sent_at),
    },
    send: { dispatch_attempt_count: 1 },
    session: {
      // WorkBuddy exposes a conversation id and per-request id. It does not
      // expose a distinct AstronStudio-style thread id.
      thread_id: null,
      turn_id: requestId,
      session_id: conversationId,
      cwd: workspace,
      verified: true,
      binding_evidence: bindingEvidence,
    },
    execution: {
      business_status: businessStatus,
      started_at: startedAt,
      finished_at: finishedAt,
      duration_seconds: durationSeconds(startedAt, finishedAt),
      error,
      cancellation_confirmed: phase === "FAILED" && businessStatus === "cancelled"
        ? true
        : null,
    },
    human_assistance: humanAssistance,
    extensions: {
      workbuddy: {
        identity_mapping: {
          thread_id: null,
          turn_id_source: "conversation-index.requests[].id",
          session_id_source: "codebuddy-sessions.vscdb.session:*.conversationId",
          cwd_source: "codebuddy-sessions.vscdb.session:*.cwd",
          terminal_status_source: "codebuddy-sessions.vscdb.session:*.status + conversation-index.requests[].state",
        },
        session_status: sessionSnapshot.status || null,
        request_state: history.binding?.request_state?.raw || null,
        workspace_history_key: history.binding?.workspace_history_key || null,
        trace_completeness: history.completeness || null,
        resource_observation: history.resources || null,
        final_response_present: Boolean(history.final_response?.trim()),
      },
    },
  };
}
