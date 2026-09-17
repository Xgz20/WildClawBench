// 资源指标只取原生计数；缺失、隐藏、冲突均不能转换成真实零消耗。
import { verifiedQwenProfile } from "./qwen-profile.mjs";
export const VERSION = "1.1.1";
export const TOKEN_KEYS = ["input_tokens", "output_tokens", "total_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_output_tokens"];
const METRIC_KEYS = [...TOKEN_KEYS, "request_count", "request_attempt_count", "call_count", "agent_duration_seconds"];
export const count = (n) => Number.isSafeInteger(n) && n >= 0 ? n : null;
export const elapsed = (a, b) => {
  if (a == null || b == null) return null;
  const value = (new Date(b).getTime() - new Date(a).getTime()) / 1000;
  return Number.isFinite(value) && value >= 0 ? value : null;
};
export function empty(reason = "unavailable") {
  return { usage: { ...Object.fromEntries(TOKEN_KEYS.map(k => [k, null])), request_count: null, request_attempt_count: null },
    tools: { call_count: null }, execution: { agent_duration_seconds: null },
    collection: { schema_version: "wildclawbench.web-e2e-resource-collection/v1", version: VERSION,
      scope: "primary-task", metrics: Object.fromEntries(METRIC_KEYS.map(k => [k, { status: "unavailable", basis: reason }])), warnings: [reason], sources: [], background_operations: [],
      excluded_scope: ["unobserved-http-retries", "unlinked-child-agents", "client-background-services"] } };
}
export function setMetric(result, group, key, value, status = "observed", basis = "") {
  result[group][key] = value;
  result.collection.metrics[key] = { status: value == null ? "unavailable" : status, basis };
}
function sumKnown(values) {
  if (!values.length || values.some(v => count(v) == null)) return null;
  return count(values.reduce((a, b) => a + b, 0));
}
function unique(rows, id, value) {
  const map = new Map();
  for (const row of rows) {
    const key = id(row);
    if (!key) throw new Error("MISSING_EVENT_ID");
    const next = value(row);
    if (map.has(key) && JSON.stringify(map.get(key)) !== JSON.stringify(next)) throw new Error("CONFLICTING_EVENT");
    map.set(key, next);
  }
  return map;
}

export function parseWorkBuddy(rows) {
  const result = empty(); result.collection.warnings = [];
  const users = rows.filter(r => r.type === "message" && r.role === "user" && !r.providerData?.isMeta);
  if (users.length !== 1) throw new Error("AMBIGUOUS_USER_TURNS");
  const responseRows = rows.filter(r => r.providerData?.messageId);
  const ids = new Set(responseRows.map(r => r.providerData.messageId));
  const usage = unique(responseRows.filter(r => r.providerData.usage), r => r.providerData.messageId, r => r.providerData.usage);
  const values = [...usage.values()];
  const complete = ids.size > 0 && ids.size === usage.size;
  const basis = "unique-provider-message-id; persisted responses, not HTTP attempts";
  const record = (key, numbers, metricBasis = basis) => {
    const known = numbers.filter(n => count(n) != null);
    const isComplete = complete && known.length === numbers.length;
    setMetric(result, "usage", key, isComplete ? sumKnown(numbers) : null, "observed", metricBasis);
    if (!isComplete && known.length) {
      result.collection.known_subtotals ??= {};
      result.collection.known_subtotals[key] = sumKnown(known);
      result.collection.metrics[key].status = "partial";
    }
  };
  const mapping = { input_tokens: "inputTokens", output_tokens: "outputTokens", total_tokens: "totalTokens" };
  for (const [key, source] of Object.entries(mapping)) {
    record(key, values.map(u => u[source]));
  }
  const detailSum = (u, field, key) => Array.isArray(u[field]) ? sumKnown(u[field].map(d => d[key])) : null;
  record("cache_read_input_tokens", values.map(u => detailSum(u, "inputTokensDetails", "cached_tokens")), "input includes cache read");
  record("reasoning_output_tokens", values.map(u => detailSum(u, "outputTokensDetails", "reasoning_tokens")), "subset of output");
  setMetric(result, "usage", "request_count", ids.size || null, "observed", basis);
  if (values.some(u => u.requests !== 1)) throw new Error("UNSUPPORTED_REQUEST_USAGE");
  // 支持已核对的 cache-inclusive 协议；新 provider 若公式不一致，失败关闭等待适配。
  if (values.some(u => count(u.inputTokens) != null && count(u.outputTokens) != null && count(u.totalTokens) != null && u.totalTokens !== u.inputTokens + u.outputTokens)) throw new Error("TOKEN_SEMANTICS_MISMATCH");
  if (values.some(u => detailSum(u, "inputTokensDetails", "cached_tokens") > u.inputTokens)) throw new Error("CACHE_SEMANTICS_MISMATCH");
  const calls = unique(rows.filter(r => r.type === "function_call"), r => r.callId, r => ({ name: r.name }));
  setMetric(result, "tools", "call_count", calls.size, "observed", "unique model callId; results excluded");
  const messages = rows.filter(r => ["message", "function_call", "function_call_result"].includes(r.type));
  const last = messages.at(-1);
  setMetric(result, "execution", "agent_duration_seconds", last?.role === "assistant" ? elapsed(users[0].timestamp, last.timestamp) : null, "inferred", "first user to final assistant timestamp");
  if (!complete) result.collection.warnings.push("INCOMPLETE_RESPONSE_USAGE");
  result.collection.response_coverage = { known: usage.size, total: ids.size };
  if ([...calls.values()].some(c => /^(Agent|Task)$/iu.test(c.name || ""))) result.collection.warnings.push("CHILD_AGENT_USAGE_NOT_INCLUDED");
  return result;
}

export function parseAstron(rows, turnId) {
  const result = empty(); result.collection.warnings = [];
  let active = false, baseline = null, started = null, finished = null, last = null;
  const advances = [], calls = new Set();
  for (const row of rows) {
    const p = row.payload || {};
    if (row.type === "event_msg" && p.type === "task_started") {
      if (active && p.turn_id !== turnId) throw new Error("INTERLEAVED_NATIVE_TURN");
      if (p.turn_id === turnId && started) throw new Error("DUPLICATE_TURN_START");
      active = p.turn_id === turnId;
      if (active) { started = row.timestamp; baseline = last; }
    }
    if (row.type === "event_msg" && p.type === "token_count" && p.info) {
      const next = p.info.total_token_usage;
      if (active && ["input_tokens", "output_tokens", "total_tokens"].some(k => count(last?.[k]) != null && count(next?.[k]) != null && next[k] < last[k])) {
        throw new Error("CUMULATIVE_USAGE_RESET");
      }
      if (active && JSON.stringify(next) !== JSON.stringify(last)) advances.push(p.info);
      last = next;
    }
    if (active && row.type === "response_item" && ["function_call", "custom_tool_call", "local_shell_call"].includes(p.type)) {
      if (!p.call_id) throw new Error("MISSING_CALL_ID");
      calls.add(p.call_id);
    }
    if (active && row.type === "event_msg" && p.type === "task_complete" && p.turn_id === turnId) {
      finished = row.timestamp; break;
    }
  }
  if (!started) throw new Error("TURN_NOT_FOUND");
  const mapping = { input_tokens: "input_tokens", output_tokens: "output_tokens", total_tokens: "total_tokens", cache_read_input_tokens: "cached_input_tokens", reasoning_output_tokens: "reasoning_output_tokens" };
  let reconciled = advances.length > 0;
  for (const [key, source] of Object.entries(mapping)) {
    const end = advances.length ? count(last?.[source]) : null, start = baseline == null ? 0 : count(baseline[source]);
    const delta = end != null && start != null && end >= start ? end - start : null;
    const total = sumKnown(advances.map(u => u.last_token_usage?.[source]));
    if (delta !== total || (["input_tokens", "output_tokens", "total_tokens"].includes(key) && delta == null)) reconciled = false;
    setMetric(result, "usage", key, delta, finished ? "observed" : "partial", "turn cumulative delta; cache and reasoning are subsets");
  }
  const u = result.usage;
  if (u.total_tokens != null && u.input_tokens != null && u.output_tokens != null && u.total_tokens !== u.input_tokens + u.output_tokens) throw new Error("TOKEN_SEMANTICS_MISMATCH");
  if (u.input_tokens != null && u.cache_read_input_tokens > u.input_tokens) throw new Error("CACHE_SEMANTICS_MISMATCH");
  setMetric(result, "usage", "request_count", reconciled ? advances.length : null, finished ? "inferred" : "partial", "advancing cumulative snapshots reconciled with last usage; not HTTP attempts");
  setMetric(result, "tools", "call_count", calls.size, finished ? "observed" : "partial", "unique model call_id; results excluded");
  setMetric(result, "execution", "agent_duration_seconds", elapsed(started, finished), "observed", "native task_started to task_complete");
  if (!reconciled) result.collection.warnings.push("REQUEST_COUNT_NOT_RECONCILED");
  if (!finished) result.collection.warnings.push("INCOMPLETE_NATIVE_TURN");
  return result;
}

export function parseQwen(rows, { runtimeIdentity = null } = {}) {
  const result = empty(); result.collection.warnings = [];
  const starts = rows.filter(r => r.type === "turn.started" && !r.data?.is_subagent);
  const turns = [...new Set(starts.map(r => r.turn_id))];
  if (turns.length !== 1) throw new Error("AMBIGUOUS_USER_TURNS");
  const turnId = turns[0], selected = rows.filter(r => r.turn_id === turnId);
  const requests = unique(selected.filter(r => r.type === "model.request.started"), r => r.request_id, r => ({ index: r.data?.request_index }));
  const responses = unique(selected.filter(r => r.type === "model.response.completed"), r => r.request_id, r => r.data);
  const calls = unique(selected.filter(r => r.type === "tool.requested"), r => r.tool_call_id, r => ({ name: r.data?.tool_name }));
  const finishes = unique(selected.filter(r => r.type === "turn.finished"), r => r.turn_id, r => r.data);
  const finish = finishes.has(turnId) ? { data: finishes.get(turnId) } : null;
  const matched = requests.size > 0 && requests.size === responses.size && [...requests.keys()].every(k => responses.has(k));
  setMetric(result, "usage", "request_count", requests.size || null, finish ? "observed" : "partial", "main-turn model.request.started IDs; not HTTP attempts");
  setMetric(result, "tools", "call_count", calls.size, finish ? "observed" : "partial", "tool.requested IDs; Thinking UI excluded");
  setMetric(result, "execution", "agent_duration_seconds", count(finish?.data?.duration_ms) == null ? null : finish.data.duration_ms / 1000, "observed", "SDK turn.finished.duration_ms");
  // 暴露开关存在不等于语义已验收；未验证时保存原始已知小计，不伪造归一化总量。
  const values = [...responses.values()];
  const keys = ["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"];
  const raw = Object.fromEntries(keys.map(k => [k, sumKnown(values.map(u => u[k]))]));
  const nonzero = keys.some(k => raw[k] > 0);
  result.collection.native_usage = nonzero ? raw : null;
  const profile = verifiedQwenProfile(runtimeIdentity);
  result.collection.runtime_identity = runtimeIdentity;
  result.collection.normalization_profile = profile;
  // 单条全零可能是隐藏值；不能因同会话其他响应非零就把它视为真实零。
  const exposed = values.filter(u => count(u.input_tokens) != null && count(u.output_tokens) != null
    && u.input_tokens + u.output_tokens > 0);
  const masked = values.length > 0 && keys.every(k => raw[k] === 0);
  if (nonzero && profile && values.every(u => u.provider === "qoder")) {
    const invalidCache = exposed.some(u => count(u.cache_read_input_tokens) != null && u.cache_read_input_tokens > u.input_tokens);
    for (const key of ["input_tokens", "output_tokens", "cache_read_input_tokens"]) {
      const numbers = exposed.map(u => u[key]).filter(n => count(n) != null);
      const subtotal = sumKnown(numbers);
      const complete = matched && exposed.length === values.length && numbers.length === values.length;
      const final = count(finish?.data?.[key]);
      const conflict = (complete && final != null && subtotal !== final) || (key === "cache_read_input_tokens" && invalidCache);
      const observed = complete && final != null && !conflict;
      setMetric(result, "usage", key, observed ? subtotal : null, "observed", "verified Qoder response sum reconciled with turn.finished; input includes cache read");
      if (!observed) {
        result.collection.metrics[key].status = conflict ? "unverified" : "partial";
        if (!conflict && subtotal != null) {
          result.collection.known_subtotals ??= {};
          result.collection.known_subtotals[key] = subtotal;
        }
        result.collection.warnings.push(conflict ? `QWEN_${key.toUpperCase()}_MISMATCH` : `QWEN_${key.toUpperCase()}_INCOMPLETE`);
      }
    }
    setMetric(result, "usage", "total_tokens", sumKnown([result.usage.input_tokens, result.usage.output_tokens]), "observed", "cache-inclusive input + output; no extra cache addition");
    if (result.usage.total_tokens == null) {
      const invalid = ["input_tokens", "output_tokens"].some(k => result.collection.metrics[k].status === "unverified");
      result.collection.metrics.total_tokens.status = invalid ? "unverified" : "partial";
      const subtotal = sumKnown(exposed.map(u => count(u.input_tokens + u.output_tokens)));
      if (!invalid && subtotal != null) {
        result.collection.known_subtotals ??= {};
        result.collection.known_subtotals.total_tokens = subtotal;
      }
    }
    result.collection.metrics.cache_creation_input_tokens.basis = "Qoder adapter initializes zero; independent cache writes not observed";
    result.collection.metrics.reasoning_output_tokens.basis = "not exposed in native response events";
  } else {
    for (const key of TOKEN_KEYS) result.collection.metrics[key] = {
      status: nonzero ? "unverified" : masked ? "masked" : "unavailable",
      basis: nonzero ? "normalization requires validated runtime profile" : masked ? "qoder token exposure unavailable; zero is not usage" : "missing response usage",
    };
    result.collection.warnings.push(nonzero ? "QWEN_TOKEN_SEMANTICS_UNVERIFIED" : masked ? "QWEN_TOKEN_USAGE_MASKED" : "QWEN_TOKEN_USAGE_UNAVAILABLE");
  }
  for (const end of rows.filter(r => r.type === "turn.finished" && r.turn_id !== turnId)) {
    const part = rows.filter(r => r.turn_id === end.turn_id);
    result.collection.background_operations.push({ kind: "background-turn", request_count: new Set(part.filter(r => r.type === "model.request.started").map(r => r.request_id)).size,
      tool_call_count: new Set(part.filter(r => r.type === "tool.requested").map(r => r.tool_call_id)).size,
      duration_seconds: count(end.data?.duration_ms) == null ? null : end.data.duration_ms / 1000 });
  }
  result.collection.native_turn_id = turnId;
  result.collection.response_coverage = { known: exposed.length, total: requests.size };
  if (!matched) result.collection.warnings.push("INCOMPLETE_REQUEST_RESPONSES");
  if (!finish) result.collection.warnings.push("INCOMPLETE_NATIVE_TURN");
  return result;
}
