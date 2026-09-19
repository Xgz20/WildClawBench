import { resolve } from "node:path";

import { qwenWorkNativeResourceParsers } from "./components.mjs";
export {
  QWENWORK_GENERAL_PROFILES,
  QWENWORK_MACOS_1_0_5_PROFILE,
  inspectQwenWorkRuntimeIdentity,
  matchQwenWorkRuntimeProfile,
} from "./runtime-profile.mjs";

export const QWENWORK_GENERAL_ADAPTER_ID = "qwenwork-native-general";
export const QWENWORK_GENERAL_ADAPTER_VERSION = "0.1.0";
export const QWENWORK_RESOURCE_SCHEMA = "urn:wildclawbench:schema:general-e2e:resource-metrics:v1";
const TASK_IDENTITY_FIELDS = Object.freeze(["batch_id", "unit_id", "task_id", "attempt_id"]);
const TOKEN_FIELDS = Object.freeze([
  "input_tokens",
  "output_tokens",
  "total_tokens",
  "cache_read_input_tokens",
  "cache_creation_input_tokens",
  "reasoning_output_tokens",
]);

function requireTaskIdentity(identity) {
  for (const field of TASK_IDENTITY_FIELDS) {
    if (typeof identity?.[field] !== "string" || !identity[field].trim()) {
      throw new Error(`QWENWORK_TASK_IDENTITY_MISSING: ${field}`);
    }
  }
  return Object.fromEntries(TASK_IDENTITY_FIELDS.map((field) => [field, identity[field]]));
}

function safeDate(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : null;
}

function normalizedToolStatus(value) {
  const status = String(value || "").trim().toLowerCase().replace(/[\s_-]+/gu, "");
  if (["success", "succeeded", "ok", "passed"].includes(status)) return "success";
  if (["error", "failed", "failure", "denied"].includes(status)) return "error";
  return "unknown";
}

function toolOutcomes(segmentRows) {
  const observations = new Map();
  const record = (callId, observation) => {
    const current = observations.get(callId) || [];
    current.push(observation);
    observations.set(callId, current);
  };
  for (const row of segmentRows) {
    const callId = typeof row?.tool_call_id === "string" ? row.tool_call_id : null;
    if (!callId) continue;
    if (row.type === "tool.shell.finished") {
      const aborted = row.data?.aborted === true;
      const exitCode = Number.isSafeInteger(row.data?.exit_code) ? row.data.exit_code : null;
      record(callId, {
        source_type: row.type,
        status: aborted ? "error" : exitCode === 0 ? "success" : exitCode == null ? "unknown" : "error",
        native_outcome: aborted ? "cancelled" : exitCode === 0 ? "success" : exitCode == null ? "unknown" : "error",
        exit_code: exitCode,
      });
    } else if (row.type === "tool.execution.finished") {
      const status = normalizedToolStatus(row.data?.status);
      record(callId, {
        source_type: row.type,
        status,
        native_outcome: String(row.data?.status || "unknown"),
      });
    } else if (row.type === "permission.resolved" && row.data?.allowed === false) {
      record(callId, {
        source_type: row.type,
        status: "error",
        native_outcome: "denied",
        decision_reason: row.data?.decision_reason || null,
      });
    }
  }
  const outcomes = new Map();
  for (const [callId, values] of observations) {
    const decisive = [...new Set(values.map((value) => value.status).filter((status) => status !== "unknown"))];
    const conflict = decisive.length > 1;
    const shell = [...values].reverse().find((value) => value.source_type === "tool.shell.finished");
    outcomes.set(callId, {
      status: conflict ? "unknown" : decisive[0] || "unknown",
      native_outcome: conflict
        ? "conflict"
        : values.map((value) => value.native_outcome).find((value) => value && value !== "unknown") || "unknown",
      ...(shell?.exit_code == null ? {} : { exit_code: shell.exit_code }),
      ...(values.find((value) => value.decision_reason)?.decision_reason
        ? { decision_reason: values.find((value) => value.decision_reason).decision_reason }
        : {}),
      native_outcomes: values.map((value) => ({
        source_type: value.source_type,
        status: value.status,
        native_outcome: value.native_outcome,
      })),
      outcome_conflict: conflict,
    });
  }
  return outcomes;
}

function textParts(row) {
  return Array.isArray(row?.message?.content) ? row.message.content : [];
}

function rawSource(rawRef, redacted) {
  return {
    adapter: QWENWORK_GENERAL_ADAPTER_ID,
    raw_ref: rawRef,
    redacted: Boolean(redacted),
  };
}

function pendingEvent({ eventId, occurredAt, type, role = null, content = null, tool = undefined, source, extra = {} }) {
  return {
    event_id: eventId,
    occurred_at: safeDate(occurredAt),
    type,
    role,
    content,
    ...(tool ? { tool } : {}),
    source,
    ...extra,
  };
}

export function assertQwenTranscriptBinding(transcriptRows, { sessionId, workspace }) {
  if (!Array.isArray(transcriptRows) || !transcriptRows.length) {
    throw new Error("QWENWORK_TRANSCRIPT_EMPTY");
  }
  if (typeof sessionId !== "string" || !sessionId.trim()) throw new Error("QWENWORK_SESSION_ID_MISSING");
  if (typeof workspace !== "string" || !workspace.trim()) throw new Error("QWENWORK_WORKSPACE_MISSING");
  const sessionValues = [...new Set(transcriptRows.map((row) => row?.sessionId).filter(Boolean))];
  const cwdValues = [...new Set(transcriptRows.map((row) => row?.cwd).filter(Boolean).map((value) => resolve(value)))];
  if (sessionValues.length !== 1 || sessionValues[0] !== sessionId) {
    throw new Error("QWENWORK_TRANSCRIPT_SESSION_MISMATCH");
  }
  if (cwdValues.length !== 1 || cwdValues[0] !== resolve(workspace)) {
    throw new Error("QWENWORK_TRANSCRIPT_WORKSPACE_MISMATCH");
  }
  const transcriptVersions = [...new Set(transcriptRows.map((row) => row?.version).filter(Boolean))];
  return {
    session_id: sessionId,
    cwd: resolve(workspace),
    transcript_version: transcriptVersions.length === 1 ? transcriptVersions[0] : null,
    transcript_version_consistent: transcriptVersions.length === 1,
  };
}

export function normalizeQwenTranscript({
  identity,
  transcriptRows,
  segmentRows,
  sessionId,
  workspace,
  redacted = false,
}) {
  const normalizedIdentity = requireTaskIdentity(identity);
  const binding = assertQwenTranscriptBinding(transcriptRows, { sessionId, workspace });
  if (!Array.isArray(segmentRows)) throw new Error("QWENWORK_SEGMENTS_INVALID");
  const outcomes = toolOutcomes(segmentRows);
  const events = [];
  let sourceOrder = 0;
  let filteredNativeEventCount = 0;

  const append = (event) => events.push({ ...event, source_order: sourceOrder++ });
  transcriptRows.forEach((row, rowIndex) => {
    const parts = textParts(row);
    if (!parts.length) {
      filteredNativeEventCount += 1;
      return;
    }
    parts.forEach((part, partIndex) => {
      const nativeId = row.uuid || row.messageId || `line-${rowIndex + 1}`;
      const eventId = `qwen-transcript-${nativeId}-${partIndex}`;
      const source = rawSource(`transcript.jsonl#L${rowIndex + 1}`, redacted);
      if (row.type === "user" && part.type === "text") {
        append(pendingEvent({
          eventId,
          occurredAt: row.timestamp,
          type: "user_message",
          role: "user",
          content: typeof part.text === "string" ? part.text : null,
          source,
        }));
      } else if (row.type === "assistant" && part.type === "text") {
        append(pendingEvent({
          eventId,
          occurredAt: row.timestamp,
          type: "assistant_message",
          role: "assistant",
          content: typeof part.text === "string" ? part.text : null,
          source,
        }));
      } else if (row.type === "assistant" && part.type === "tool_use") {
        if (typeof part.id !== "string" || !part.id || typeof part.name !== "string" || !part.name) {
          throw new Error(`QWENWORK_TOOL_CALL_IDENTITY_MISSING: line=${rowIndex + 1}`);
        }
        append(pendingEvent({
          eventId,
          occurredAt: row.timestamp,
          type: "tool_call",
          role: "assistant",
          source,
          tool: {
            call_id: String(part.id || ""),
            name: String(part.name || ""),
            arguments: part.input ?? null,
            status: "unknown",
          },
        }));
      } else if (row.type === "user" && part.type === "tool_result") {
        const callId = String(part.tool_use_id || "");
        if (!callId) throw new Error(`QWENWORK_TOOL_RESULT_IDENTITY_MISSING: line=${rowIndex + 1}`);
        const outcome = outcomes.get(callId) || { status: "unknown", native_outcome: "unknown" };
        append(pendingEvent({
          eventId,
          occurredAt: row.timestamp,
          type: "tool_result",
          role: "user",
          source,
          tool: {
            call_id: callId,
            result: row.toolUseResult ?? part.content ?? null,
            status: outcome.status || "unknown",
            native_outcome: outcome.native_outcome || "unknown",
            ...(outcome.exit_code == null ? {} : { exit_code: outcome.exit_code }),
            native_outcomes: outcome.native_outcomes || [],
            outcome_conflict: outcome.outcome_conflict === true,
          },
        }));
      } else {
        filteredNativeEventCount += 1;
      }
    });
  });

  segmentRows.forEach((row, rowIndex) => {
    const source = rawSource(`segments.jsonl#L${rowIndex + 1}`, redacted);
    const base = {
      eventId: `qwen-segment-${row.seq ?? rowIndex + 1}-${row.type || "unknown"}`,
      occurredAt: row.ts,
      source,
    };
    if (row.type === "turn.started" || row.type === "turn.finished") {
      append(pendingEvent({
        ...base,
        type: "status",
        extra: {
          native_type: row.type,
          native_turn_id: row.turn_id || null,
          is_subagent: row.data?.is_subagent === true,
          native_status: row.type === "turn.finished" ? row.data?.reason || "finished" : "started",
        },
      }));
    } else if (row.type === "model.response.completed") {
      append(pendingEvent({
        ...base,
        type: "usage",
        extra: {
          native_turn_id: row.turn_id || null,
          native_request_id: row.request_id || null,
          usage: {
            input_tokens: row.data?.input_tokens ?? null,
            output_tokens: row.data?.output_tokens ?? null,
            cache_read_input_tokens: row.data?.cache_read_input_tokens ?? null,
            cache_creation_input_tokens: row.data?.cache_creation_input_tokens ?? null,
          },
        },
      }));
    } else if (String(row.level || "").toLowerCase() === "error") {
      append(pendingEvent({
        ...base,
        type: "error",
        content: String(row.data?.message || row.type || "native error"),
        extra: { native_type: row.type || null },
      }));
    } else {
      filteredNativeEventCount += 1;
    }
  });

  events.sort((left, right) => {
    const leftTime = left.occurred_at ? Date.parse(left.occurred_at) : Number.MAX_SAFE_INTEGER;
    const rightTime = right.occurred_at ? Date.parse(right.occurred_at) : Number.MAX_SAFE_INTEGER;
    return leftTime - rightTime || left.source_order - right.source_order;
  });
  const normalized = events.map(({ source_order: ignored, ...event }, sequence) => ({
    schema_id: "urn:wildclawbench:schema:general-e2e:transcript-event:v1",
    schema_version: 1,
    identity: normalizedIdentity,
    ...event,
    sequence,
  }));
  return {
    binding,
    events: normalized,
    native_event_count: transcriptRows.length + segmentRows.length,
    normalized_event_count: normalized.length,
    filtered_native_event_count: filteredNativeEventCount,
  };
}

export function buildQwenCallIndex(events) {
  const calls = new Map();
  for (const event of events) {
    const callId = event.tool?.call_id;
    if (!callId) continue;
    const current = calls.get(callId) || { call_id: callId, call_sequence: null, result_sequence: null };
    if (event.type === "tool_call") {
      if (current.call_sequence != null) throw new Error(`QWENWORK_DUPLICATE_TOOL_CALL: ${callId}`);
      current.call_sequence = event.sequence;
    } else if (event.type === "tool_result") {
      if (current.result_sequence != null) throw new Error(`QWENWORK_DUPLICATE_TOOL_RESULT: ${callId}`);
      current.result_sequence = event.sequence;
    }
    calls.set(callId, current);
  }
  return [...calls.values()].sort((left, right) => (left.call_sequence ?? Number.MAX_SAFE_INTEGER)
    - (right.call_sequence ?? Number.MAX_SAFE_INTEGER));
}

function sourceReferences(sources) {
  const refs = sources.map((source) => source?.path).filter((value) => typeof value === "string" && value);
  return refs.length ? [...new Set(refs)] : ["qwenwork-native-source-unavailable"];
}

function resourceMetric(value, observation, key, fallbackBasis) {
  const metadata = observation.collection?.metrics?.[key] || {};
  const rawStatus = metadata.status || "unavailable";
  // General resource-metrics v1 semantic validation requires an unverified
  // metric to carry a numeric value. Unknown Qwen normalization must not
  // publish that native number as a normalized metric, so the strict public
  // view uses unavailable/null while the returned private observation keeps
  // unverified native_usage for audit and future profile work.
  const status = value == null && rawStatus === "unverified" ? "unavailable" : rawStatus;
  return {
    value: value ?? null,
    status,
    basis: rawStatus === "unverified" && status === "unavailable"
      ? `${metadata.basis || fallbackBasis}; strict General v1 withholds unverified native value`
      : metadata.basis || fallbackBasis,
  };
}

function coverage(known, total, unit) {
  return { known, total, unit };
}

export function buildQwenGeneralResourceMetrics({
  identity,
  segmentRows,
  runtimeIdentity,
  sources,
  collectedAt = new Date().toISOString(),
  executionDurationSeconds = null,
}) {
  const normalizedIdentity = requireTaskIdentity(identity);
  if (!Array.isArray(segmentRows) || !segmentRows.length) throw new Error("QWENWORK_SEGMENTS_EMPTY");
  if (!Array.isArray(sources) || !sources.length) throw new Error("QWENWORK_RESOURCE_SOURCES_EMPTY");
  const observation = qwenWorkNativeResourceParsers.parseQwen(segmentRows, { runtimeIdentity });
  const refs = sourceReferences(sources);
  const responseCoverage = observation.collection.response_coverage || { known: 0, total: 0 };
  const requestTotal = Number.isSafeInteger(responseCoverage.total) ? responseCoverage.total : null;
  const mainTurn = segmentRows.find((row) => row.type === "turn.started" && !row.data?.is_subagent)?.turn_id;
  const responseRows = segmentRows.filter((row) => row.type === "model.response.completed"
    && row.turn_id === mainTurn && row.data?.provider === "qoder");
  const metricKnownResponses = (field) => {
    const status = observation.collection.metrics?.[field]?.status;
    if (!new Set(["observed", "partial"]).has(status)) return 0;
    if (field === "total_tokens") {
      return responseRows.filter((row) => Number.isSafeInteger(row.data?.input_tokens)
        && row.data.input_tokens >= 0 && Number.isSafeInteger(row.data?.output_tokens)
        && row.data.output_tokens >= 0).length;
    }
    return responseRows.filter((row) => Number.isSafeInteger(row.data?.[field])
      && row.data[field] >= 0).length;
  };
  const tokenCoverage = Object.fromEntries(TOKEN_FIELDS.map((field) => [
    field,
    coverage(
      metricKnownResponses(field),
      requestTotal,
      "model_response",
    ),
  ]));

  const usage = Object.fromEntries(TOKEN_FIELDS.map((field) => [
    field,
    resourceMetric(observation.usage?.[field], observation, field, "QwenWork native event unavailable"),
  ]));
  const durationValue = Number.isFinite(executionDurationSeconds) && executionDurationSeconds >= 0
    ? executionDurationSeconds
    : null;
  const duration = {
    value: durationValue,
    status: durationValue == null ? "unavailable" : "observed",
    basis: durationValue == null
      ? "CB-A execution state wall-clock duration was not supplied"
      : "CB-A execution state started_at to finished_at wall clock",
  };
  const requestCount = resourceMetric(
    observation.usage?.request_count,
    observation,
    "request_count",
    "main-turn model.request.started IDs",
  );
  const requestAttempts = resourceMetric(
    observation.usage?.request_attempt_count,
    observation,
    "request_attempt_count",
    "QwenWork does not expose transport-level request attempts",
  );
  const callCount = resourceMetric(
    observation.tools?.call_count,
    observation,
    "call_count",
    "unique main-turn tool.requested IDs",
  );
  const agentDuration = resourceMetric(
    observation.execution?.agent_duration_seconds,
    observation,
    "agent_duration_seconds",
    "SDK turn.finished.duration_ms",
  );

  const coverageMap = {
    ...tokenCoverage,
    request_count: coverage(requestCount.value == null ? 0 : 1, 1, "attempt"),
    request_attempt_count: coverage(0, requestCount.value == null ? null : requestCount.value, "native_request"),
    call_count: coverage(callCount.value == null ? 0 : 1, 1, "attempt"),
    duration_seconds: coverage(duration.value == null ? 0 : 1, 1, "attempt"),
    agent_duration_seconds: coverage(agentDuration.value == null ? 0 : 1, 1, "attempt"),
  };
  const metricSources = Object.fromEntries([
    ...TOKEN_FIELDS,
    "request_count",
    "request_attempt_count",
    "call_count",
    "duration_seconds",
    "agent_duration_seconds",
  ].map((field) => [field, refs]));
  const essential = [
    usage.input_tokens,
    usage.output_tokens,
    usage.total_tokens,
    usage.cache_read_input_tokens,
    requestCount,
    callCount,
    duration,
    agentDuration,
  ];
  const collectionStatus = essential.every((item) => item.value != null
    && ["observed", "inferred"].includes(item.status)) ? "complete" : "partial";
  return {
    resource_metrics: {
      schema_id: QWENWORK_RESOURCE_SCHEMA,
      schema_version: 1,
      identity: normalizedIdentity,
      collection: {
        collector: "qwenwork-native-general-resource-metrics",
        version: QWENWORK_GENERAL_ADAPTER_VERSION,
        status: collectionStatus,
        collected_at: collectedAt,
        sources,
        warnings: [...new Set(observation.collection.warnings || [])],
        excluded_scope: [...(observation.collection.excluded_scope || [])],
        coverage: coverageMap,
        ...(observation.collection.known_subtotals
          ? { known_subtotals: observation.collection.known_subtotals }
          : {}),
        metric_sources: metricSources,
      },
      metrics: {
        usage,
        requests: {
          request_count: requestCount,
          request_attempt_count: requestAttempts,
        },
        tools: { call_count: callCount },
        timing: {
          duration_seconds: duration,
          agent_duration_seconds: agentDuration,
        },
      },
    },
    observation,
  };
}

export function buildQwenAdapterEvidence({
  session,
  runtimeIdentity,
  sources,
  terminalMapping,
}) {
  if (!session?.session_id || !session?.cwd) throw new Error("QWENWORK_NATIVE_BINDING_INCOMPLETE");
  return {
    schema_version: "wildclawbench.general-e2e-qwenwork-adapter-evidence/v1",
    adapter: { id: QWENWORK_GENERAL_ADAPTER_ID, version: QWENWORK_GENERAL_ADAPTER_VERSION },
    native_identity: {
      conversation_id: session.conversation_id || null,
      sub_chat_id: session.sub_chat_id || null,
      session_id: session.session_id,
      local_project_id: session.local_project_id || null,
      cwd: resolve(session.cwd),
    },
    runtime_identity: runtimeIdentity || null,
    terminal_mapping: terminalMapping || null,
    sources,
    limitations: [
      "not-a-public-trace-index",
      "formal-provenance-and-finalization-await-common-cb-b",
      "native-thread-id-and-native-turn-id-remain-null-unless-observed",
    ],
  };
}
