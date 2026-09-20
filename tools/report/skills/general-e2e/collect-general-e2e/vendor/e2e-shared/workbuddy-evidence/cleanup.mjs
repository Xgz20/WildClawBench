import { assertCleanupEvidence } from "../task-process-cleanup/cleanup-evidence.mjs";
import {
  selectDarwinTaskProcesses,
  snapshotDarwinTaskProcesses,
  terminateDarwinTaskProcesses,
} from "../task-process-cleanup/macos-task-processes.mjs";

export const WORKBUDDY_CLEANUP_HOOK_ID = "workbuddy-macos-task-processes";
export const WORKBUDDY_CLEANUP_HOOK_VERSION = "0.1.0";

const TRACE_INDEX_SCHEMA = "urn:wildclawbench:schema:general-e2e:trace-index:v2";
const RESOURCE_METRICS_SCHEMA = "urn:wildclawbench:schema:general-e2e:resource-metrics:v1";
const EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-execution-state/v1";

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assertObject(value, label) {
  if (!isObject(value)) throw new Error(`${label} 必须是 JSON 对象`);
  return value;
}

function assertIdentityAligned(state, traceIndex, resourceMetrics) {
  const identity = assertObject(state.identity, "state.identity");
  for (const [label, value] of [
    ["traceIndex.identity", traceIndex.identity],
    ["resourceMetrics.identity", resourceMetrics.identity],
  ]) {
    const candidate = assertObject(value, label);
    for (const field of ["batch_id", "unit_id", "task_id", "attempt_id"]) {
      if (candidate[field] !== identity[field]) {
        throw new Error(`WORKBUDDY_IDENTITY_MISMATCH: ${label}.${field}`);
      }
    }
  }
}

function assertNullUnavailable(metric, label) {
  if (!isObject(metric) || metric.value !== null || metric.status !== "unavailable") {
    throw new Error(`WORKBUDDY_METRIC_MUST_REMAIN_UNAVAILABLE: ${label}`);
  }
  if (!isObject(metric.coverage)
      || metric.coverage.known !== 0
      || metric.coverage.total < 1
      || typeof metric.coverage.unit !== "string") {
    throw new Error(`WORKBUDDY_METRIC_COVERAGE_INVALID: ${label}`);
  }
}

function assertNativeSession(state, traceIndex) {
  const session = assertObject(state.session, "state.session");
  const traceSession = assertObject(traceIndex.session, "traceIndex.session");
  const mapping = assertObject(state.extensions?.workbuddy?.identity_mapping, "state.extensions.workbuddy.identity_mapping");
  const requiredSources = mapping.binding_source === "workbuddy-runtime-api" ? {
    turn_id_source: "runtime.conversations.current.requestEntries().requests[].id",
    session_id_source: "runtime.conversations.current.info.id",
    cwd_source: "runtime.conversations.current.info.space.cwd",
    terminal_status_source: "runtime.conversations.current.info.state/lifecycle + requestEntries().requests[].state + message.state",
  } : {
    turn_id_source: "conversation-index.requests[].id",
    session_id_source: "codebuddy-sessions.vscdb.session:*.conversationId",
    cwd_source: "codebuddy-sessions.vscdb.session:*.cwd",
    terminal_status_source: "codebuddy-sessions.vscdb.session:*.status + conversation-index.requests[].state",
  };
  for (const [field, expected] of Object.entries(requiredSources)) {
    if (mapping[field] !== expected) {
      throw new Error(`WORKBUDDY_NATIVE_SOURCE_UNVERIFIED: ${field}`);
    }
  }
  if (session.thread_id !== null || traceSession.thread_id !== null) {
    throw new Error("WORKBUDDY_THREAD_ID_MUST_REMAIN_NULL");
  }
  for (const [field, label] of [
    ["turn_id", "request/turn id"],
    ["session_id", "conversation/session id"],
  ]) {
    if (typeof session[field] !== "string" || !session[field]
        || traceSession[field] !== session[field]) {
      throw new Error(`WORKBUDDY_NATIVE_SESSION_BINDING_INVALID: ${label}`);
    }
  }
  if (typeof session.cwd !== "string" || !session.cwd
      || traceSession.cwd !== session.cwd
      || traceSession.cwd !== state.candidate_workspace) {
    throw new Error("WORKBUDDY_NATIVE_CWD_UNVERIFIED");
  }
  if (session.verified !== true) throw new Error("WORKBUDDY_NATIVE_SESSION_NOT_VERIFIED");
}

/**
 * Validate the WorkBuddy-specific part of the CB-B collector boundary.
 *
 * This is deliberately an input gate, not a receipt writer. The common
 * finalizer still validates all paths, hashes, transcript references and
 * cleanup evidence before publication. Unknown native terminal/cwd, retry and
 * credit values remain blocking or unavailable instead of being inferred.
 */
export function assertWorkBuddyCollectorReadiness({ state, traceIndex, resourceMetrics, cleanupHook }) {
  assertObject(state, "state");
  assertObject(traceIndex, "traceIndex");
  assertObject(resourceMetrics, "resourceMetrics");
  if (state.schema_version !== EXECUTION_STATE_SCHEMA) {
    throw new Error("WORKBUDDY_EXECUTION_STATE_SCHEMA_UNSUPPORTED");
  }
  if (state.driver?.harness !== "workbuddy" || !/^macos(?:-[a-z0-9-]+)?$/u.test(state.driver?.platform || "")) {
    throw new Error("WORKBUDDY_EXECUTION_STATE_DRIVER_MISMATCH");
  }
  assertIdentityAligned(state, traceIndex, resourceMetrics);
  if (state.phase !== "COMPLETED" || state.execution?.business_status !== "completed") {
    throw new Error("WORKBUDDY_NATIVE_TERMINAL_STATE_UNVERIFIED");
  }
  if (state.prompt?.send_status !== "sent" || state.send?.dispatch_attempt_count !== 1) {
    throw new Error("WORKBUDDY_SEND_NOT_RECONCILED");
  }
  assertNativeSession(state, traceIndex);

  if (traceIndex.schema_id !== TRACE_INDEX_SCHEMA || traceIndex.schema_version !== 2
      || traceIndex.adapter?.id !== "workbuddy-native-history"
      || typeof traceIndex.adapter.source !== "string" || !traceIndex.adapter.source) {
    throw new Error("WORKBUDDY_TRACE_INDEX_CONTRACT_INVALID");
  }
  if (traceIndex.completeness?.status !== "complete"
      || !Number.isInteger(traceIndex.completeness.omitted_event_count)
      || traceIndex.completeness.omitted_event_count !== 0
      || !Array.isArray(traceIndex.raw_trace) || traceIndex.raw_trace.length === 0
      || !Array.isArray(traceIndex.binding_evidence) || traceIndex.binding_evidence.length === 0
      || traceIndex.transcript?.path !== "transcript.jsonl"
      || !Number.isInteger(traceIndex.transcript.event_count)
      || traceIndex.transcript.event_count < 1
      || !Array.isArray(traceIndex.calls)
      || !Array.isArray(traceIndex.normalization?.compatibility_profiles)
      || traceIndex.normalization.compatibility_profiles.length === 0) {
    throw new Error("WORKBUDDY_TRACE_INDEX_INCOMPLETE");
  }
  if (resourceMetrics.schema_id !== RESOURCE_METRICS_SCHEMA
      || resourceMetrics.identity?.task_id !== state.identity?.task_id) {
    throw new Error("WORKBUDDY_RESOURCE_METRICS_CONTRACT_INVALID");
  }
  const requests = resourceMetrics.metrics?.requests;
  const usage = resourceMetrics.metrics?.usage;
  const timing = resourceMetrics.metrics?.timing;
  assertNullUnavailable(requests?.request_attempt_count, "request_attempt_count");
  assertNullUnavailable(usage?.cache_read_input_tokens, "cache_read_input_tokens");
  assertNullUnavailable(usage?.cache_creation_input_tokens, "cache_creation_input_tokens");
  assertNullUnavailable(usage?.reasoning_output_tokens, "reasoning_output_tokens");
  assertNullUnavailable(timing?.duration_seconds, "duration_seconds");
  assertNullUnavailable(timing?.agent_duration_seconds, "agent_duration_seconds");
  if (Object.prototype.hasOwnProperty.call(resourceMetrics.metrics || {}, "credit")
      || Object.prototype.hasOwnProperty.call(resourceMetrics.metrics?.usage || {}, "credit")) {
    throw new Error("WORKBUDDY_CREDIT_MUST_REMAIN_OUTSIDE_PRIMARY_METRICS");
  }
  const hook = assertWorkBuddyCleanupHook(cleanupHook);
  return {
    status: "READY_FOR_GENERAL_FINALIZER",
    harness: "workbuddy",
    cleanup_hook: { id: hook.id, version: hook.version, platform: hook.platform },
    native_terminal: "verified",
    native_cwd: "verified",
    transport_retry: "unavailable",
    credit: "unverified",
  };
}

export function assertWorkBuddyCleanupHook(hook) {
  if (!isObject(hook)
      || hook.id !== WORKBUDDY_CLEANUP_HOOK_ID
      || hook.version !== WORKBUDDY_CLEANUP_HOOK_VERSION
      || hook.harness !== "workbuddy"
      || hook.platform !== "darwin"
      || typeof hook.run !== "function") {
    throw new Error("WORKBUDDY_CLEANUP_HOOK_INVALID");
  }
  return hook;
}

/**
 * WorkBuddy's trusted platform hook. Process selection and identity checks are
 * delegated to the shared macOS task-process primitive; no process name or
 * boolean-only fixture is accepted here.
 */
export function createWorkBuddyCleanupHook(overrides = {}) {
  const run = overrides.run || ((workspace, options = {}) => terminateDarwinTaskProcesses(workspace, options));
  const hook = {
    id: WORKBUDDY_CLEANUP_HOOK_ID,
    version: WORKBUDDY_CLEANUP_HOOK_VERSION,
    harness: "workbuddy",
    platform: "darwin",
    run,
  };
  return assertWorkBuddyCleanupHook(hook);
}

export function assertWorkBuddyCleanupEvidence(cleanup, workspace, options = {}, elapsedMilliseconds) {
  const hook = createWorkBuddyCleanupHook();
  return assertCleanupEvidence(cleanup, workspace, options, hook, elapsedMilliseconds);
}

export {
  selectDarwinTaskProcesses,
  snapshotDarwinTaskProcesses,
  terminateDarwinTaskProcesses,
};
