// Native counters only: missing, masked, partial, or conflicting values never
// become a measured zero. Scenario adapters supply their output profile.
export const COMPONENT_NAME = "resource-metrics";
export const COMPONENT_VERSION = "1.0.0";
export const TOKEN_KEYS = Object.freeze([
  "input_tokens",
  "output_tokens",
  "total_tokens",
  "cache_read_input_tokens",
  "cache_creation_input_tokens",
  "reasoning_output_tokens",
]);
const METRIC_KEYS = Object.freeze([
  ...TOKEN_KEYS,
  "request_count",
  "request_attempt_count",
  "call_count",
  "agent_duration_seconds",
]);

function requireProfile(profile) {
  for (const key of ["schemaVersion", "version", "scope"]) {
    if (typeof profile?.[key] !== "string" || !profile[key].trim()) {
      throw new TypeError(`resource metric profile ${key} must be a non-empty string`);
    }
  }
  if (!Array.isArray(profile.excludedScope) || profile.excludedScope.some((item) => typeof item !== "string" || !item)) {
    throw new TypeError("resource metric profile excludedScope must be a string array");
  }
  if (profile.resolveQwenProfile != null && typeof profile.resolveQwenProfile !== "function") {
    throw new TypeError("resource metric profile resolveQwenProfile must be a function");
  }
  return Object.freeze({
    schemaVersion: profile.schemaVersion,
    version: profile.version,
    scope: profile.scope,
    excludedScope: Object.freeze([...profile.excludedScope]),
    resolveQwenProfile: profile.resolveQwenProfile || (() => null),
  });
}

export function createNativeResourceMetricParsers(inputProfile) {
  const profile = requireProfile(inputProfile);
  const count = (number) => Number.isSafeInteger(number) && number >= 0 ? number : null;
  const elapsed = (start, end) => {
    if (start == null || end == null) return null;
    const value = (new Date(end).getTime() - new Date(start).getTime()) / 1000;
    return Number.isFinite(value) && value >= 0 ? value : null;
  };

  function empty(reason = "unavailable") {
    return {
      usage: {
        ...Object.fromEntries(TOKEN_KEYS.map((key) => [key, null])),
        request_count: null,
        request_attempt_count: null,
      },
      tools: { call_count: null },
      execution: { agent_duration_seconds: null },
      collection: {
        schema_version: profile.schemaVersion,
        version: profile.version,
        scope: profile.scope,
        metrics: Object.fromEntries(METRIC_KEYS.map((key) => [key, { status: "unavailable", basis: reason }])),
        warnings: [reason],
        sources: [],
        background_operations: [],
        excluded_scope: [...profile.excludedScope],
      },
    };
  }

  function setMetric(result, group, key, value, status = "observed", basis = "") {
    result[group][key] = value;
    result.collection.metrics[key] = { status: value == null ? "unavailable" : status, basis };
  }

  function sumKnown(values) {
    if (!values.length || values.some((value) => count(value) == null)) return null;
    return count(values.reduce((left, right) => left + right, 0));
  }

  function unique(rows, id, value) {
    const map = new Map();
    for (const row of rows) {
      const key = id(row);
      if (!key) throw new Error("MISSING_EVENT_ID");
      const next = value(row);
      if (map.has(key) && JSON.stringify(map.get(key)) !== JSON.stringify(next)) {
        throw new Error("CONFLICTING_EVENT");
      }
      map.set(key, next);
    }
    return map;
  }

  function parseWorkBuddy(rows) {
    const result = empty();
    result.collection.warnings = [];
    const users = rows.filter((row) => row.type === "message" && row.role === "user" && !row.providerData?.isMeta);
    if (users.length !== 1) throw new Error("AMBIGUOUS_USER_TURNS");
    const responseRows = rows.filter((row) => row.providerData?.messageId);
    const ids = new Set(responseRows.map((row) => row.providerData.messageId));
    const usage = unique(
      responseRows.filter((row) => row.providerData.usage),
      (row) => row.providerData.messageId,
      (row) => row.providerData.usage,
    );
    const values = [...usage.values()];
    const complete = ids.size > 0 && ids.size === usage.size;
    const basis = "unique-provider-message-id; persisted responses, not HTTP attempts";
    const record = (key, numbers, metricBasis = basis) => {
      const known = numbers.filter((number) => count(number) != null);
      const isComplete = complete && known.length === numbers.length;
      setMetric(result, "usage", key, isComplete ? sumKnown(numbers) : null, "observed", metricBasis);
      if (!isComplete && known.length) {
        result.collection.known_subtotals ??= {};
        result.collection.known_subtotals[key] = sumKnown(known);
        result.collection.metrics[key].status = "partial";
      }
    };
    const mapping = {
      input_tokens: "inputTokens",
      output_tokens: "outputTokens",
      total_tokens: "totalTokens",
    };
    for (const [key, source] of Object.entries(mapping)) record(key, values.map((usageValue) => usageValue[source]));
    const detailSum = (usageValue, field, key) => Array.isArray(usageValue[field])
      ? sumKnown(usageValue[field].map((detail) => detail[key]))
      : null;
    record(
      "cache_read_input_tokens",
      values.map((usageValue) => detailSum(usageValue, "inputTokensDetails", "cached_tokens")),
      "input includes cache read",
    );
    record(
      "reasoning_output_tokens",
      values.map((usageValue) => detailSum(usageValue, "outputTokensDetails", "reasoning_tokens")),
      "subset of output",
    );
    setMetric(result, "usage", "request_count", ids.size || null, "observed", basis);
    if (values.some((usageValue) => usageValue.requests !== 1)) throw new Error("UNSUPPORTED_REQUEST_USAGE");
    if (values.some((usageValue) => count(usageValue.inputTokens) != null
      && count(usageValue.outputTokens) != null
      && count(usageValue.totalTokens) != null
      && usageValue.totalTokens !== usageValue.inputTokens + usageValue.outputTokens)) {
      throw new Error("TOKEN_SEMANTICS_MISMATCH");
    }
    if (values.some((usageValue) => detailSum(usageValue, "inputTokensDetails", "cached_tokens") > usageValue.inputTokens)) {
      throw new Error("CACHE_SEMANTICS_MISMATCH");
    }
    const calls = unique(
      rows.filter((row) => row.type === "function_call"),
      (row) => row.callId,
      (row) => ({ name: row.name }),
    );
    setMetric(result, "tools", "call_count", calls.size, "observed", "unique model callId; results excluded");
    const messages = rows.filter((row) => ["message", "function_call", "function_call_result"].includes(row.type));
    const last = messages.at(-1);
    setMetric(
      result,
      "execution",
      "agent_duration_seconds",
      last?.role === "assistant" ? elapsed(users[0].timestamp, last.timestamp) : null,
      "inferred",
      "first user to final assistant timestamp",
    );
    if (!complete) result.collection.warnings.push("INCOMPLETE_RESPONSE_USAGE");
    result.collection.response_coverage = { known: usage.size, total: ids.size };
    if ([...calls.values()].some((call) => /^(Agent|Task)$/iu.test(call.name || ""))) {
      result.collection.warnings.push("CHILD_AGENT_USAGE_NOT_INCLUDED");
    }
    return result;
  }

  function parseAstron(rows, turnId) {
    const result = empty();
    result.collection.warnings = [];
    let active = false;
    let baseline = null;
    let started = null;
    let finished = null;
    let last = null;
    const advances = [];
    const calls = new Set();
    for (const row of rows) {
      const payload = row.payload || {};
      if (row.type === "event_msg" && payload.type === "task_started") {
        if (active && payload.turn_id !== turnId) throw new Error("INTERLEAVED_NATIVE_TURN");
        if (payload.turn_id === turnId && started) throw new Error("DUPLICATE_TURN_START");
        active = payload.turn_id === turnId;
        if (active) {
          started = row.timestamp;
          baseline = last;
        }
      }
      if (row.type === "event_msg" && payload.type === "token_count" && payload.info) {
        const next = payload.info.total_token_usage;
        if (active && ["input_tokens", "output_tokens", "total_tokens"].some((key) =>
          count(last?.[key]) != null && count(next?.[key]) != null && next[key] < last[key])) {
          throw new Error("CUMULATIVE_USAGE_RESET");
        }
        if (active && JSON.stringify(next) !== JSON.stringify(last)) advances.push(payload.info);
        last = next;
      }
      if (active && row.type === "response_item"
        && ["function_call", "custom_tool_call", "local_shell_call"].includes(payload.type)) {
        if (!payload.call_id) throw new Error("MISSING_CALL_ID");
        calls.add(payload.call_id);
      }
      if (active && row.type === "event_msg" && payload.type === "task_complete" && payload.turn_id === turnId) {
        finished = row.timestamp;
        break;
      }
    }
    if (!started) throw new Error("TURN_NOT_FOUND");
    const mapping = {
      input_tokens: "input_tokens",
      output_tokens: "output_tokens",
      total_tokens: "total_tokens",
      cache_read_input_tokens: "cached_input_tokens",
      reasoning_output_tokens: "reasoning_output_tokens",
    };
    let reconciled = advances.length > 0;
    for (const [key, source] of Object.entries(mapping)) {
      const end = advances.length ? count(last?.[source]) : null;
      const start = baseline == null ? 0 : count(baseline[source]);
      const delta = end != null && start != null && end >= start ? end - start : null;
      const total = sumKnown(advances.map((usageValue) => usageValue.last_token_usage?.[source]));
      if (delta !== total || (["input_tokens", "output_tokens", "total_tokens"].includes(key) && delta == null)) {
        reconciled = false;
      }
      setMetric(
        result,
        "usage",
        key,
        delta,
        finished ? "observed" : "partial",
        "turn cumulative delta; cache and reasoning are subsets",
      );
    }
    const usage = result.usage;
    if (usage.total_tokens != null && usage.input_tokens != null && usage.output_tokens != null
      && usage.total_tokens !== usage.input_tokens + usage.output_tokens) {
      throw new Error("TOKEN_SEMANTICS_MISMATCH");
    }
    if (usage.input_tokens != null && usage.cache_read_input_tokens > usage.input_tokens) {
      throw new Error("CACHE_SEMANTICS_MISMATCH");
    }
    setMetric(
      result,
      "usage",
      "request_count",
      reconciled ? advances.length : null,
      finished ? "inferred" : "partial",
      "advancing cumulative snapshots reconciled with last usage; not HTTP attempts",
    );
    setMetric(
      result,
      "tools",
      "call_count",
      calls.size,
      finished ? "observed" : "partial",
      "unique model call_id; results excluded",
    );
    setMetric(
      result,
      "execution",
      "agent_duration_seconds",
      elapsed(started, finished),
      "observed",
      "native task_started to task_complete",
    );
    if (!reconciled) result.collection.warnings.push("REQUEST_COUNT_NOT_RECONCILED");
    if (!finished) result.collection.warnings.push("INCOMPLETE_NATIVE_TURN");
    return result;
  }

  function parseQwen(rows, { runtimeIdentity = null } = {}) {
    const result = empty();
    result.collection.warnings = [];
    const starts = rows.filter((row) => row.type === "turn.started" && !row.data?.is_subagent);
    const turns = [...new Set(starts.map((row) => row.turn_id))];
    if (turns.length !== 1) throw new Error("AMBIGUOUS_USER_TURNS");
    const turnId = turns[0];
    const selected = rows.filter((row) => row.turn_id === turnId);
    const requests = unique(
      selected.filter((row) => row.type === "model.request.started"),
      (row) => row.request_id,
      (row) => ({ index: row.data?.request_index }),
    );
    const responses = unique(
      selected.filter((row) => row.type === "model.response.completed"),
      (row) => row.request_id,
      (row) => row.data,
    );
    const calls = unique(
      selected.filter((row) => row.type === "tool.requested"),
      (row) => row.tool_call_id,
      (row) => ({ name: row.data?.tool_name }),
    );
    const finishes = unique(
      selected.filter((row) => row.type === "turn.finished"),
      (row) => row.turn_id,
      (row) => row.data,
    );
    const finish = finishes.has(turnId) ? { data: finishes.get(turnId) } : null;
    const matched = requests.size > 0
      && requests.size === responses.size
      && [...requests.keys()].every((key) => responses.has(key));
    setMetric(
      result,
      "usage",
      "request_count",
      requests.size || null,
      finish ? "observed" : "partial",
      "main-turn model.request.started IDs; not HTTP attempts",
    );
    setMetric(
      result,
      "tools",
      "call_count",
      calls.size,
      finish ? "observed" : "partial",
      "tool.requested IDs; Thinking UI excluded",
    );
    setMetric(
      result,
      "execution",
      "agent_duration_seconds",
      count(finish?.data?.duration_ms) == null ? null : finish.data.duration_ms / 1000,
      "observed",
      "SDK turn.finished.duration_ms",
    );
    const values = [...responses.values()];
    const keys = ["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"];
    const raw = Object.fromEntries(keys.map((key) => [key, sumKnown(values.map((usageValue) => usageValue[key]))]));
    const nonzero = keys.some((key) => raw[key] > 0);
    result.collection.native_usage = nonzero ? raw : null;
    const normalizationProfile = profile.resolveQwenProfile(runtimeIdentity);
    result.collection.runtime_identity = runtimeIdentity;
    result.collection.normalization_profile = normalizationProfile;
    const exposed = values.filter((usageValue) => count(usageValue.input_tokens) != null
      && count(usageValue.output_tokens) != null
      && usageValue.input_tokens + usageValue.output_tokens > 0);
    const masked = values.length > 0 && keys.every((key) => raw[key] === 0);
    if (nonzero && normalizationProfile && values.every((usageValue) => usageValue.provider === "qoder")) {
      const invalidCache = exposed.some((usageValue) => count(usageValue.cache_read_input_tokens) != null
        && usageValue.cache_read_input_tokens > usageValue.input_tokens);
      for (const key of ["input_tokens", "output_tokens", "cache_read_input_tokens"]) {
        const numbers = exposed.map((usageValue) => usageValue[key]).filter((number) => count(number) != null);
        const subtotal = sumKnown(numbers);
        const complete = matched && exposed.length === values.length && numbers.length === values.length;
        const final = count(finish?.data?.[key]);
        const conflict = (complete && final != null && subtotal !== final)
          || (key === "cache_read_input_tokens" && invalidCache);
        const observed = complete && final != null && !conflict;
        setMetric(
          result,
          "usage",
          key,
          observed ? subtotal : null,
          "observed",
          "verified Qoder response sum reconciled with turn.finished; input includes cache read",
        );
        if (!observed) {
          result.collection.metrics[key].status = conflict ? "unverified" : "partial";
          if (!conflict && subtotal != null) {
            result.collection.known_subtotals ??= {};
            result.collection.known_subtotals[key] = subtotal;
          }
          result.collection.warnings.push(
            conflict ? `QWEN_${key.toUpperCase()}_MISMATCH` : `QWEN_${key.toUpperCase()}_INCOMPLETE`,
          );
        }
      }
      setMetric(
        result,
        "usage",
        "total_tokens",
        sumKnown([result.usage.input_tokens, result.usage.output_tokens]),
        "observed",
        "cache-inclusive input + output; no extra cache addition",
      );
      if (result.usage.total_tokens == null) {
        const invalid = ["input_tokens", "output_tokens"]
          .some((key) => result.collection.metrics[key].status === "unverified");
        result.collection.metrics.total_tokens.status = invalid ? "unverified" : "partial";
        const subtotal = sumKnown(exposed.map((usageValue) => count(usageValue.input_tokens + usageValue.output_tokens)));
        if (!invalid && subtotal != null) {
          result.collection.known_subtotals ??= {};
          result.collection.known_subtotals.total_tokens = subtotal;
        }
      }
      result.collection.metrics.cache_creation_input_tokens.basis = "Qoder adapter initializes zero; independent cache writes not observed";
      result.collection.metrics.reasoning_output_tokens.basis = "not exposed in native response events";
    } else {
      for (const key of TOKEN_KEYS) {
        result.collection.metrics[key] = {
          status: nonzero ? "unverified" : masked ? "masked" : "unavailable",
          basis: nonzero
            ? "normalization requires validated runtime profile"
            : masked
              ? "qoder token exposure unavailable; zero is not usage"
              : "missing response usage",
        };
      }
      result.collection.warnings.push(
        nonzero
          ? "QWEN_TOKEN_SEMANTICS_UNVERIFIED"
          : masked
            ? "QWEN_TOKEN_USAGE_MASKED"
            : "QWEN_TOKEN_USAGE_UNAVAILABLE",
      );
    }
    for (const end of rows.filter((row) => row.type === "turn.finished" && row.turn_id !== turnId)) {
      const part = rows.filter((row) => row.turn_id === end.turn_id);
      result.collection.background_operations.push({
        kind: "background-turn",
        request_count: new Set(part.filter((row) => row.type === "model.request.started").map((row) => row.request_id)).size,
        tool_call_count: new Set(part.filter((row) => row.type === "tool.requested").map((row) => row.tool_call_id)).size,
        duration_seconds: count(end.data?.duration_ms) == null ? null : end.data.duration_ms / 1000,
      });
    }
    result.collection.native_turn_id = turnId;
    result.collection.response_coverage = { known: exposed.length, total: requests.size };
    if (!matched) result.collection.warnings.push("INCOMPLETE_REQUEST_RESPONSES");
    if (!finish) result.collection.warnings.push("INCOMPLETE_NATIVE_TURN");
    return result;
  }

  return Object.freeze({
    profile,
    count,
    elapsed,
    empty,
    setMetric,
    parseWorkBuddy,
    parseAstron,
    parseQwen,
  });
}
