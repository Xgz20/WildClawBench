import { QWENWORK_MACOS_1_2_0_TOKEN_PROFILE } from "./token-profile.mjs";

export const QWENWORK_COLLECTOR_ADAPTER_ID = "qwenwork-native-general";
export const QWENWORK_COLLECTOR_VERSION = "0.1.2";
export const RESOURCE_SCHEMA = "urn:wildclawbench:schema:general-e2e:resource-metrics:v1";
const TOKEN_FIELDS = Object.freeze([
  "input_tokens",
  "output_tokens",
  "total_tokens",
  "cache_read_input_tokens",
  "cache_creation_input_tokens",
  "reasoning_output_tokens",
]);

function safeDate(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : null;
}

function toolStatus(value) {
  const status = String(value || "").trim().toLowerCase().replace(/[\s_-]+/gu, "");
  if (["success", "succeeded", "ok", "passed"].includes(status)) return "success";
  if (["error", "failed", "failure", "denied"].includes(status)) return "error";
  return "unknown";
}

function collectToolOutcomes(rows) {
  const observed = new Map();
  const append = (callId, value) => observed.set(callId, [...(observed.get(callId) || []), value]);
  for (const row of rows) {
    const callId = typeof row?.tool_call_id === "string" ? row.tool_call_id : null;
    if (!callId) continue;
    if (row.type === "tool.shell.finished") {
      const aborted = row.data?.aborted === true;
      const exitCode = Number.isSafeInteger(row.data?.exit_code) ? row.data.exit_code : null;
      append(callId, {
        source_type: row.type,
        status: aborted ? "error" : exitCode === 0 ? "success" : exitCode == null ? "unknown" : "error",
        native_outcome: aborted ? "cancelled" : exitCode === 0 ? "success" : exitCode == null ? "unknown" : "error",
        exit_code: exitCode,
      });
    } else if (row.type === "tool.execution.finished") {
      append(callId, {
        source_type: row.type,
        status: toolStatus(row.data?.status),
        native_outcome: String(row.data?.status || "unknown"),
      });
    } else if (row.type === "permission.resolved" && row.data?.allowed === false) {
      append(callId, { source_type: row.type, status: "error", native_outcome: "denied" });
    }
  }
  const result = new Map();
  for (const [callId, values] of observed) {
    const decisive = [...new Set(values.map((value) => value.status).filter((status) => status !== "unknown"))];
    const conflict = decisive.length > 1;
    const shell = [...values].reverse().find((value) => value.source_type === "tool.shell.finished");
    result.set(callId, {
      status: conflict ? "unknown" : decisive[0] || "unknown",
      native_outcome: conflict
        ? "conflict"
        : values.map((value) => value.native_outcome).find((value) => value !== "unknown") || "unknown",
      ...(shell?.exit_code == null ? {} : { exit_code: shell.exit_code }),
      outcome_conflict: conflict,
      native_outcomes: values.map(({ source_type, status, native_outcome }) => ({ source_type, status, native_outcome })),
    });
  }
  return result;
}

function requireNativeId(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`QWENWORK_NATIVE_ID_MISSING: ${label}`);
  }
  return value;
}

function source(row, redacted) {
  return {
    adapter: QWENWORK_COLLECTOR_ADAPTER_ID,
    raw_ref: `${row.__raw_path}#L${row.__raw_line}`,
    redacted: Boolean(redacted),
  };
}

function pending({ eventId, occurredAt, type, sourceValue, role = null, content = null, tool = undefined, extra = {} }) {
  return {
    event_id: eventId,
    occurred_at: safeDate(occurredAt),
    type,
    role,
    content,
    ...(tool ? { tool } : {}),
    source: sourceValue,
    ...extra,
  };
}

function isInjectedSystemReminder(text) {
  return typeof text === "string" && /^<system-reminder>\s/u.test(text);
}

export function normalizeQwenNativeTrace({ identity, transcriptRows, segmentRows, redacted = false }) {
  const outcomes = collectToolOutcomes(segmentRows);
  const events = [];
  let sourceOrder = 0;
  let filteredNativeEventCount = 0;
  const append = (event) => events.push({ ...event, source_order: sourceOrder++ });

  for (const row of transcriptRows) {
    const parts = Array.isArray(row?.message?.content) ? row.message.content : [];
    if (!parts.length) {
      filteredNativeEventCount += 1;
      continue;
    }
    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index];
      const nativeId = row.uuid || row.messageId || `line-${row.__raw_line}`;
      const base = {
        eventId: `qwen-transcript-${nativeId}-${index}`,
        occurredAt: row.timestamp,
        sourceValue: source(row, redacted),
      };
      if (row.type === "user" && part.type === "text") {
        if (isInjectedSystemReminder(part.text)) {
          filteredNativeEventCount += 1;
          continue;
        }
        append(pending({ ...base, type: "user_message", role: "user", content: part.text ?? null }));
      } else if (row.type === "assistant" && part.type === "text") {
        append(pending({ ...base, type: "assistant_message", role: "assistant", content: part.text ?? null }));
      } else if (row.type === "assistant" && part.type === "tool_use") {
        requireNativeId(part.id, `tool_use.id:line=${row.__raw_line}`);
        if (!part.name) throw new Error(`QWENWORK_TOOL_CALL_IDENTITY_MISSING: line=${row.__raw_line}`);
        append(pending({
          ...base,
          type: "tool_call",
          role: "assistant",
          tool: { call_id: part.id, name: part.name, arguments: part.input ?? null, status: "unknown" },
        }));
      } else if (row.type === "user" && part.type === "tool_result") {
        const callId = requireNativeId(part.tool_use_id, `tool_result.tool_use_id:line=${row.__raw_line}`);
        const outcome = outcomes.get(callId) || {
          status: "unknown", native_outcome: "unknown", native_outcomes: [], outcome_conflict: false,
        };
        append(pending({
          ...base,
          type: "tool_result",
          role: "user",
          tool: {
            call_id: callId,
            result: row.toolUseResult ?? part.content ?? null,
            ...outcome,
          },
        }));
      } else filteredNativeEventCount += 1;
    }
  }

  for (const row of segmentRows) {
    const base = {
      eventId: `qwen-segment-${row.seq ?? row.__raw_line}-${row.type || "unknown"}`,
      occurredAt: row.ts,
      sourceValue: source(row, redacted),
    };
    if (row.type === "turn.started" || row.type === "turn.finished") {
      requireNativeId(row.turn_id, `${row.type}.turn_id:line=${row.__raw_line}`);
      append(pending({
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
      requireNativeId(row.request_id, `${row.type}.request_id:line=${row.__raw_line}`);
      append(pending({
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
      append(pending({
        ...base,
        type: "error",
        content: String(row.data?.message || row.type || "native error"),
        extra: { native_type: row.type || null },
      }));
    } else filteredNativeEventCount += 1;
  }

  events.sort((left, right) => {
    const leftTime = left.occurred_at ? Date.parse(left.occurred_at) : Number.MAX_SAFE_INTEGER;
    const rightTime = right.occurred_at ? Date.parse(right.occurred_at) : Number.MAX_SAFE_INTEGER;
    return leftTime - rightTime || left.source_order - right.source_order;
  });
  const normalized = events.map(({ source_order: ignored, ...event }, sequence) => ({
    schema_id: "urn:wildclawbench:schema:general-e2e:transcript-event:v1",
    schema_version: 1,
    identity: { ...identity },
    ...event,
    sequence,
  }));
  const nativeTranscriptEventCount = transcriptRows.reduce((count, row) => {
    const parts = Array.isArray(row?.message?.content) ? row.message.content : [];
    return count + Math.max(parts.length, 1);
  }, 0);
  return {
    events: normalized,
    native_event_count: nativeTranscriptEventCount + segmentRows.length,
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
  for (const value of calls.values()) {
    if (value.call_sequence == null) throw new Error(`QWENWORK_TOOL_RESULT_WITHOUT_CALL: ${value.call_id}`);
  }
  return [...calls.values()].sort((left, right) => left.call_sequence - right.call_sequence);
}

function metric(value, status, basis) {
  return { value, status: value == null ? status : status, basis };
}

function coverage(known, total, unit) {
  return { known, total, unit };
}

function uniqueIds(rows, field) {
  const values = rows.map((row, index) => {
    const value = row?.[field];
    return requireNativeId(value, `${field}:line=${row?.__raw_line || index + 1}`);
  });
  if (new Set(values).size !== values.length) throw new Error(`QWENWORK_DUPLICATE_NATIVE_ID: ${field}`);
  return new Set(values);
}

export function buildQwenStrictResourceMetrics({
  state, segmentRows, sources, collectedAt, traceCalls = null, tokenProfile = null,
}) {
  const mainStarts = segmentRows.filter((row) => row.type === "turn.started" && !row.data?.is_subagent);
  const mainTurnIds = [...new Set(mainStarts.map((row) => row.turn_id).filter(Boolean))];
  if (mainTurnIds.length !== 1) throw new Error("QWENWORK_MAIN_TURN_AMBIGUOUS");
  const turnId = mainTurnIds[0];
  const selected = segmentRows.filter((row) => row.turn_id === turnId);
  const requests = uniqueIds(selected.filter((row) => row.type === "model.request.started"), "request_id");
  const responses = selected.filter((row) => row.type === "model.response.completed");
  const responseIds = uniqueIds(responses, "request_id");
  const calls = uniqueIds(selected.filter((row) => row.type === "tool.requested"), "tool_call_id");
  if (traceCalls) {
    const normalizedCallIds = new Set(traceCalls.map((call) => call.call_id));
    if (calls.size !== normalizedCallIds.size || [...calls].some((callId) => !normalizedCallIds.has(callId))) {
      throw new Error("QWENWORK_TOOL_CALL_PROVENANCE_MISMATCH");
    }
  }
  const finishes = selected.filter((row) => row.type === "turn.finished");
  if (finishes.length !== 1) throw new Error(`QWENWORK_MAIN_TURN_FINISH_COUNT: ${finishes.length}`);
  const finish = finishes[0];
  const duration = Number(state.execution?.duration_seconds);
  const agentDuration = Number(finish.data?.duration_ms) / 1000;
  const refs = sources.map((source) => source.path);
  const tokenFields = ["input_tokens", "output_tokens", "cache_read_input_tokens"];
  const safeCount = (value) => Number.isSafeInteger(value) && value >= 0;
  const values = responses.map((row) => row.data || {});
  const nonzero = values.some((value) => tokenFields.some((field) => safeCount(value[field]) && value[field] > 0));
  const matched = requests.size > 0 && responseIds.size === requests.size
    && [...requests].every((id) => responseIds.has(id));
  const validResponses = values.length > 0 && values.every((value) => (
    value.provider === "qoder"
    && safeCount(value.input_tokens) && safeCount(value.output_tokens)
    && safeCount(value.cache_read_input_tokens)
    && value.input_tokens + value.output_tokens > 0
    && value.cache_read_input_tokens <= value.input_tokens
  ));
  const totals = Object.fromEntries(tokenFields.map((field) => [
    field, values.reduce((sum, value) => sum + (safeCount(value[field]) ? value[field] : 0), 0),
  ]));
  const reconciled = tokenFields.every((field) => safeCount(finish.data?.[field])
    && finish.data[field] === totals[field]);
  const tokenObserved = Boolean(tokenProfile?.id === QWENWORK_MACOS_1_2_0_TOKEN_PROFILE.id
    && nonzero && matched && validResponses && reconciled);
  const unavailableToken = (field) => metric(null, "unavailable",
    `QwenWork ${field} has no admitted native coverage`);
  const usage = Object.fromEntries(TOKEN_FIELDS.map((field) => [field, unavailableToken(field)]));
  const coverageMap = Object.fromEntries(TOKEN_FIELDS.map((field) => [field,
    coverage(0, requests.size, "model_response")]));
  if (tokenObserved) {
    for (const field of tokenFields) {
      usage[field] = metric(totals[field], "observed",
        `${tokenProfile.id}: unique Qoder response sum reconciled with main turn; input includes cache read`);
      coverageMap[field] = coverage(responses.length, requests.size, "model_response");
    }
    usage.total_tokens = metric(totals.input_tokens + totals.output_tokens, "observed",
      `${tokenProfile.id}: cache-inclusive input + output; cache read not added twice`);
    coverageMap.total_tokens = coverage(responses.length, requests.size, "model_response");
  } else if (nonzero && tokenProfile) {
    const status = !matched ? "partial" : "unverified";
    for (const field of [...tokenFields, "total_tokens"]) {
      usage[field] = metric(null, status,
        "QwenWork native request/response or turn usage did not reconcile");
    }
  } else if (responses.length && tokenProfile) {
    for (const field of [...tokenFields, "total_tokens"]) {
      usage[field] = metric(null, "masked", "QwenWork native response usage is hidden zero, not observed zero");
    }
  }
  Object.assign(coverageMap, {
    request_count: coverage(requests.size, requests.size, "model_request"),
    request_attempt_count: coverage(0, requests.size, "native_request"),
    call_count: coverage(1, 1, "attempt"),
    duration_seconds: coverage(Number.isFinite(duration) && duration >= 0 ? 1 : 0, 1, "attempt"),
    agent_duration_seconds: coverage(Number.isFinite(agentDuration) && agentDuration >= 0 ? 1 : 0, 1, "attempt"),
  });
  const metricSources = Object.fromEntries([
    ...TOKEN_FIELDS,
    "request_count",
    "request_attempt_count",
    "call_count",
    "duration_seconds",
    "agent_duration_seconds",
  ].map((field) => [field, refs]));
  return {
    schema_id: RESOURCE_SCHEMA,
    schema_version: 1,
    identity: { ...state.identity },
    collection: {
      collector: "qwenwork-native-general-resource-metrics",
      version: QWENWORK_COLLECTOR_VERSION,
      status: "partial",
      collected_at: collectedAt,
      sources,
      warnings: tokenObserved ? ["QWEN_CACHE_WRITE_UNVERIFIED", "QWEN_REASONING_USAGE_UNAVAILABLE"]
        : [tokenProfile ? (nonzero ? "QWEN_TOKEN_RESPONSE_MISMATCH" : "QWEN_TOKEN_USAGE_MASKED")
          : "QWEN_TOKEN_SEMANTICS_UNVERIFIED"],
      excluded_scope: [
        "judge-usage",
        "control-usage",
        "unobserved-http-retries",
        "unlinked-child-agents",
        "client-background-services",
      ],
      coverage: coverageMap,
      metric_sources: metricSources,
    },
    metrics: {
      usage,
      requests: {
        request_count: metric(requests.size, "observed", "unique main-turn model.request.started IDs; not HTTP attempts"),
        request_attempt_count: metric(null, "unavailable", "QwenWork does not expose transport-level attempts"),
      },
      tools: {
        call_count: metric(calls.size, "observed", "unique main-turn tool.requested IDs"),
      },
      timing: {
        duration_seconds: Number.isFinite(duration) && duration >= 0
          ? metric(duration, "observed", "CB-A execution state wall-clock duration")
          : metric(null, "unavailable", "CB-A execution duration unavailable"),
        agent_duration_seconds: Number.isFinite(agentDuration) && agentDuration >= 0
          ? metric(agentDuration, "observed", "SDK turn.finished.duration_ms")
          : metric(null, "unavailable", "SDK main turn duration unavailable"),
      },
    },
  };
}
