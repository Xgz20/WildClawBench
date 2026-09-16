import assert from "node:assert/strict";
import test from "node:test";
import { parseAstron, parseWorkBuddy, parseQwen } from "../parsers.mjs";
import { captureResourceMetrics } from "../capture.mjs";
import { QWEN_PROFILE } from "../qwen-profile.mjs";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";

const usage = { requests: 1, inputTokens: 10, outputTokens: 2, totalTokens: 12, inputTokensDetails: [{ cached_tokens: 5 }] };
const response = (id = "response") => ({ type: "function_call", callId: id, name: "Read", providerData: { messageId: "message", usage } });
const wb = () => [{ type: "message", role: "user", timestamp: 1000 }, response(), { type: "message", role: "assistant", timestamp: 4000 }];

test("WorkBuddy 同一响应多工具只计一次 usage，结果条目不计工具", () => {
  const rows = wb(); rows.splice(2, 0, response("other"), { type: "function_call_result", callId: "response" }, { type: "message", role: "user", providerData: { isMeta: true } });
  const result = parseWorkBuddy(rows);
  assert.equal(result.usage.total_tokens, 12);
  assert.equal(result.usage.cache_read_input_tokens, 5);
  assert.equal(result.usage.cache_creation_input_tokens, null);
  assert.equal(result.usage.request_count, 1);
  assert.equal(result.tools.call_count, 2);
  assert.equal(result.execution.agent_duration_seconds, 3);
});
test("WorkBuddy 缺失和冲突 usage 不伪造完整总量", () => {
  const rows = wb(); rows.push({ providerData: { messageId: "missing" } });
  assert.equal(parseWorkBuddy(rows).usage.total_tokens, null);
  assert.equal(parseWorkBuddy(rows).collection.known_subtotals.total_tokens, 12);
  assert.equal(parseWorkBuddy(rows).collection.metrics.total_tokens.status, "partial");
  assert.equal(parseWorkBuddy(rows).usage.request_count, 2);
  assert.throws(() => parseWorkBuddy([...wb(), { providerData: { messageId: "message", usage: { ...usage, totalTokens: 20 } } }]), /CONFLICT/);
  assert.throws(() => parseWorkBuddy([...wb(), { type: "message", role: "user" }]), /AMBIGUOUS/);
});

test("Astron 无新快照不能把前轮或空缺当作零消耗，跨轮未完成则拒绝", () => {
  const result = parseAstron([token(), event("task_started", { turn_id: "turn" }), event("task_complete", { turn_id: "turn" })], "turn");
  assert.equal(result.usage.total_tokens, null);
  assert.throws(() => parseAstron([event("task_started", { turn_id: "turn" }), event("task_started", { turn_id: "other" })], "turn"), /INTERLEAVED/);
});

test("Worker 启动异常、超时和 JSON 输出损坏均降级为空值", async () => {
  let result = await captureResourceMetrics({}, {}, "workbuddy", { spawn: () => { throw new Error("sensitive detail"); } });
  assert.deepEqual(result.collection.warnings, ["COLLECTOR_START_FAILED"]);
  assert.equal(result.collection.metrics.call_count.status, "unavailable");
  const child = () => {
    const proc = new EventEmitter(); proc.stdout = new PassThrough(); proc.stdin = new PassThrough();
    proc.kill = () => { proc.killed = true; };
    return proc;
  };
  const stalled = child();
  result = await captureResourceMetrics({}, {}, "workbuddy", { spawn: () => stalled, timeoutMilliseconds: 20 });
  assert.deepEqual(result.collection.warnings, ["COLLECTION_TIMEOUT"]);
  assert.equal(stalled.killed, true);
  const invalid = child();
  const pending = captureResourceMetrics({}, {}, "workbuddy", { spawn: () => invalid });
  invalid.stdout.write("null"); invalid.emit("close", 0);
  assert.deepEqual((await pending).collection.warnings, ["COLLECTOR_INVALID_OUTPUT"]);
  result = await captureResourceMetrics({}, {}, "workbuddy", { environment: { WEB_E2E_RESOURCE_METRICS: "off" } });
  assert.deepEqual(result.collection.warnings, ["DISABLED"]);
});
const event = (type, payload, timestamp = "2026-09-16T00:00:00Z") => ({ type: "event_msg", timestamp, payload: { type, ...payload } });
const counts = { input_tokens: 10, output_tokens: 2, total_tokens: 12, cached_input_tokens: 5, reasoning_output_tokens: 1 };
const token = (total = counts, last = counts) => event("token_count", { info: { total_token_usage: total, last_token_usage: last } });
test("Astron 累计快照重复不计请求，缓存和思考不重复加总", () => {
  const rows = [event("task_started", { turn_id: "turn" }), token(), token(), event("task_complete", { turn_id: "turn" }, "2026-09-16T00:00:05Z")];
  const result = parseAstron(rows, "turn");
  assert.equal(result.usage.total_tokens, 12); assert.equal(result.usage.request_count, 1);
  assert.equal(result.execution.agent_duration_seconds, 5);
});
test("Astron 按 turn 减去前轮基线，缺终态标为 partial", () => {
  const doubled = Object.fromEntries(Object.entries(counts).map(([k, v]) => [k, v * 2]));
  const result = parseAstron([token(), event("task_started", { turn_id: "turn" }), token(doubled)], "turn");
  assert.equal(result.usage.total_tokens, 12);
  assert.equal(result.collection.metrics.total_tokens.status, "partial");
  assert.equal(result.execution.agent_duration_seconds, null);
});
const qwen = (tokens = 0) => [
  { type: "turn.started", turn_id: "main", data: { is_subagent: false } },
  { type: "model.request.started", turn_id: "main", request_id: "request", data: { request_index: 1 } },
  { type: "model.response.completed", turn_id: "main", request_id: "request", data: { provider: "qoder", input_tokens: tokens, output_tokens: tokens, cache_read_input_tokens: tokens / 2, cache_creation_input_tokens: 0 } },
  { type: "tool.requested", turn_id: "main", tool_call_id: "tool", data: { tool_name: "Bash" } },
  { type: "turn.finished", turn_id: "main", data: { duration_ms: 5000, input_tokens: tokens, output_tokens: tokens, cache_read_input_tokens: tokens / 2, cache_creation_input_tokens: 0 } },
  { type: "model.request.started", turn_id: "memory", request_id: "memory-request" },
  { type: "turn.finished", turn_id: "memory", data: { duration_ms: 1000 } },
];
test("Qwen 零值为 masked，后台记忆与主任务分离", () => {
  const result = parseQwen(qwen());
  assert.equal(result.usage.total_tokens, null); assert.equal(result.collection.metrics.total_tokens.status, "masked");
  assert.equal(result.usage.request_count, 1); assert.equal(result.tools.call_count, 1);
  assert.equal(result.collection.background_operations[0].request_count, 1);
});
test("Qwen 未显式验证时保留非零 native usage，验证后按输入含缓存归一化", () => {
  const unverified = parseQwen(qwen(10));
  assert.equal(unverified.usage.total_tokens, null);
  assert.equal(unverified.collection.native_usage.input_tokens, 10);
  assert.equal(unverified.collection.metrics.total_tokens.status, "unverified");
  const verified = parseQwen(qwen(10), { runtimeIdentity: QWEN_PROFILE });
  assert.equal(verified.usage.input_tokens, 10);
  assert.equal(verified.usage.output_tokens, 10);
  assert.equal(verified.usage.total_tokens, 20);
  assert.equal(verified.usage.cache_read_input_tokens, 5);
  assert.equal(verified.usage.cache_creation_input_tokens, null);
  assert.equal(verified.collection.metrics.total_tokens.status, "observed");
});
test("Qwen 不能用布尔开关、未知运行时或 provider 放行", () => {
  for (const runtimeIdentity of [null, { ...QWEN_PROFILE, runtime_sha256: "unknown" }, { ...QWEN_PROFILE, platform: "win32" }, { ...QWEN_PROFILE, transcript_version: "next" }]) {
    assert.equal(parseQwen(qwen(10), { runtimeIdentity, tokenExposureVerified: true }).collection.metrics.total_tokens.status, "unverified");
  }
  const rows = qwen(10); rows[2].data.provider = "other";
  assert.equal(parseQwen(rows, { runtimeIdentity: QWEN_PROFILE }).usage.total_tokens, null);
});
test("Qwen 重复事件只计一次，终值冲突和缓存大于输入不提供完整值", () => {
  const rows = qwen(10);
  const parse = () => parseQwen(rows, { runtimeIdentity: QWEN_PROFILE });
  rows.push(structuredClone(rows[2]));
  assert.equal(parse().usage.total_tokens, 20);
  rows[4].data.input_tokens = 100;
  assert.equal(parse().collection.metrics.total_tokens.status, "unverified");
  assert.equal(parse().usage.total_tokens, null);
  rows[4].data.input_tokens = 10;
  rows[2].data.cache_read_input_tokens = rows.at(-1).data.cache_read_input_tokens = rows[4].data.cache_read_input_tokens = 11;
  assert.equal(parse().usage.cache_read_input_tokens, null);
  assert.equal(parse().collection.metrics.cache_read_input_tokens.status, "unverified");
});
test("Qwen 缺响应、混合遮蔽、缺终态或字段保留 partial 与小计", () => {
  for (const change of [
    rows => rows.push({ type: "model.request.started", turn_id: "main", request_id: "missing" }),
    rows => rows.splice(4, 1),
    rows => delete rows[4].data.input_tokens,
    rows => { rows.push({ ...rows[1], request_id: "masked" }, { ...rows[2], request_id: "masked", data: { provider: "qoder", input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } }); },
  ]) {
    const rows = qwen(10); change(rows);
    const result = parseQwen(rows, { runtimeIdentity: QWEN_PROFILE });
    assert.equal(result.usage.total_tokens, null);
    assert.equal(result.collection.metrics.total_tokens.status, "partial");
    assert.equal(result.collection.known_subtotals.total_tokens, 20);
  }
  const rows = qwen(10); delete rows[2].data.cache_read_input_tokens;
  const result = parseQwen(rows, { runtimeIdentity: QWEN_PROFILE });
  assert.equal(result.usage.total_tokens, 20);
  assert.equal(result.usage.cache_read_input_tokens, null);
});
test("采集不可用不会抛出并污染执行终态", async () => {
  const result = await captureResourceMetrics({ workspace: "/tmp/nonexistent" }, { session: {} }, "workbuddy");
  assert.equal(result.usage.total_tokens, null);
  assert.deepEqual(result.collection.warnings, ["MISSING_STABLE_SESSION"]);
});
