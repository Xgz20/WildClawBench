#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { realpathSync } from "node:fs";
import {
  lstat,
  mkdir,
  readFile,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

export const RESOURCE_SCHEMA = "urn:wildclawbench:schema:general-e2e:resource-metrics:v1";
export const RESOURCE_COLLECTOR = "astronstudio-provider-runtime-resource-metrics";
export const RESOURCE_COLLECTOR_VERSION = "0.1.0";
const EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-astronstudio-execution-state/v1";
const TRACE_INDEX_SCHEMA = "urn:wildclawbench:schema:general-e2e:trace-index:v1";
const TRACE_ADAPTER_ID = "astronstudio-provider-runtime-events";
const MAX_JSON_BYTES = 64 * 1024 * 1024;
const TOOL_ITEM_TYPES = new Set(["commandExecution", "fileChange", "mcpToolCall"]);
const EXPOSED_USAGE = Object.freeze({
  input_tokens: ["lastInputTokens", "totalInputTokens"],
  output_tokens: ["lastOutputTokens", "totalOutputTokens"],
  total_tokens: ["lastUsedTokens", "totalProcessedTokens"],
  cache_read_input_tokens: ["lastCachedInputTokens", "totalCachedInputTokens"],
  reasoning_output_tokens: ["lastReasoningOutputTokens", "totalReasoningOutputTokens"],
});
const METRIC_NAMES = Object.freeze([
  ...Object.keys(EXPOSED_USAGE),
  "cache_creation_input_tokens",
  "request_count",
  "request_attempt_count",
  "call_count",
  "duration_seconds",
  "agent_duration_seconds",
]);

function usage() {
  return `AstronStudio General E2E 资源指标采集器

用法：
  node scripts/collect_astronstudio_resource_metrics.mjs \\
    --state-file /absolute/automation-state.json \\
    --trace-index /absolute/trace-index.json [选项]

选项：
  --output /absolute/resource-metrics.json  默认写入 trace-index 同目录
  --replace                                原子覆盖已有输出
  -h, --help                               显示帮助

本工具只读取已归档且通过哈希校验的精确 turn 轨迹。未知缓存写入和
HTTP 尝试保持 null；它不冻结候选、不生成正式执行回执。`;
}

export function parseArgs(argv) {
  const values = {
    stateFile: "",
    traceIndex: "",
    output: "",
    replace: false,
    help: false,
  };
  const valued = new Map([
    ["--state-file", "stateFile"],
    ["--trace-index", "traceIndex"],
    ["--output", "output"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else if (arg === "--replace") values.replace = true;
    else {
      const key = valued.get(arg);
      if (!key) throw new Error(`未知选项：${arg}`);
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      values[key] = value;
      index += 1;
    }
  }
  if (!values.help) {
    if (!values.stateFile) throw new Error("必须指定 --state-file");
    if (!values.traceIndex) throw new Error("必须指定 --trace-index");
  }
  return values;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function count(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function elapsedSeconds(start, end) {
  const startMs = Date.parse(start);
  const endMs = Date.parse(end);
  const value = (endMs - startMs) / 1000;
  return Number.isFinite(value) && value >= 0 ? value : null;
}

function sameIdentity(left, right) {
  return ["batch_id", "unit_id", "task_id", "attempt_id"]
    .every((field) => typeof left?.[field] === "string" && left[field] === right?.[field]);
}

function sameSession(state, index) {
  return ["thread_id", "turn_id", "session_id", "cwd"]
    .every((field) => typeof state?.session?.[field] === "string"
      && state.session[field] === index?.session?.[field]);
}

async function readRegularFile(path, maximumBytes = MAX_JSON_BYTES) {
  const absolute = resolve(path);
  const info = await lstat(absolute);
  if (!info.isFile() || info.isSymbolicLink() || info.size > maximumBytes) {
    throw new Error(`UNSAFE_OR_OVERSIZED_FILE: ${absolute}`);
  }
  const bytes = await readFile(absolute);
  if (bytes.length > maximumBytes) throw new Error(`OVERSIZED_FILE: ${absolute}`);
  return { absolute, bytes };
}

async function readJsonFile(path) {
  const source = await readRegularFile(path);
  let value;
  try {
    value = JSON.parse(source.bytes.toString("utf8"));
  } catch (error) {
    throw new Error(`JSON_INVALID: ${source.absolute}: ${error.message}`);
  }
  return { ...source, value };
}

function assertExecutionState(state) {
  if (state?.schema_version !== EXECUTION_STATE_SCHEMA) {
    throw new Error(`EXECUTION_STATE_UNSUPPORTED: ${state?.schema_version || "missing"}`);
  }
  if (!new Set(["COMPLETED", "FAILED"]).has(state.phase)) {
    throw new Error(`EXECUTION_NOT_TERMINAL: ${state.phase || "missing"}`);
  }
  if (state.prompt?.send_status !== "sent" || state.send?.dispatch_attempt_count !== 1) {
    throw new Error("PROMPT_IDENTITY_UNVERIFIED");
  }
  if (state.session?.verified !== true) throw new Error("SESSION_IDENTITY_UNVERIFIED");
  for (const field of ["thread_id", "turn_id", "session_id", "cwd"]) {
    if (typeof state.session?.[field] !== "string" || !state.session[field].trim()) {
      throw new Error(`SESSION_IDENTITY_MISSING: ${field}`);
    }
  }
  if (typeof state.execution?.started_at !== "string") {
    throw new Error("EXECUTION_TIMING_MISSING: started_at");
  }
}

function assertTraceBinding(state, index) {
  if (index?.schema_id !== TRACE_INDEX_SCHEMA || index?.schema_version !== 1) {
    throw new Error("TRACE_INDEX_UNSUPPORTED");
  }
  if (index.adapter?.id !== TRACE_ADAPTER_ID) throw new Error("TRACE_ADAPTER_UNSUPPORTED");
  if (!sameIdentity(state.identity, index.identity)) throw new Error("TRACE_IDENTITY_MISMATCH");
  if (!sameSession(state, index)) throw new Error("TRACE_SESSION_MISMATCH");
  if (!Array.isArray(index.raw_trace) || index.raw_trace.length !== 1) {
    throw new Error("RAW_TRACE_AMBIGUOUS");
  }
}

function safeRelativePath(value) {
  if (typeof value !== "string" || !value || isAbsolute(value) || value.includes("\\")) {
    throw new Error(`RAW_TRACE_PATH_INVALID: ${value}`);
  }
  const parts = value.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) {
    throw new Error(`RAW_TRACE_PATH_INVALID: ${value}`);
  }
  return value;
}

async function readIndexedRawTrace(traceIndexPath, index) {
  const root = await realpath(dirname(resolve(traceIndexPath)));
  const rawArtifact = index.raw_trace[0];
  const rawRelative = safeRelativePath(rawArtifact.path);
  const candidate = resolve(root, rawRelative);
  const resolved = await realpath(candidate);
  const rel = relative(root, resolved);
  if (!rel || rel === ".." || rel.startsWith(`..${sep}`) || isAbsolute(rel)) {
    throw new Error("RAW_TRACE_OUTSIDE_INDEX_ROOT");
  }
  const source = await readRegularFile(resolved);
  if (source.bytes.length !== rawArtifact.size || sha256(source.bytes) !== rawArtifact.sha256) {
    throw new Error("RAW_TRACE_ARTIFACT_MISMATCH");
  }
  const lines = source.bytes.toString("utf8").split(/\r?\n/u).filter((line) => line.trim());
  const rows = lines.map((line, lineIndex) => {
    try {
      return { ...JSON.parse(line), raw_line: lineIndex + 1 };
    } catch (error) {
      throw new Error(`RAW_TRACE_JSON_INVALID: line=${lineIndex + 1}: ${error.message}`);
    }
  });
  const range = index.raw_event_range;
  if (!range || rows.length !== range.event_count
      || rows[0]?.sequence !== range.first_sequence
      || rows.at(-1)?.sequence !== range.last_sequence) {
    throw new Error("RAW_TRACE_RANGE_MISMATCH");
  }
  let previous = -1;
  for (const row of rows) {
    if (!Number.isSafeInteger(row.sequence) || row.sequence <= previous) {
      throw new Error(`RAW_TRACE_SEQUENCE_INVALID: ${row.sequence}`);
    }
    if (row.thread_id !== index.session.thread_id || row.turn_id !== index.session.turn_id
        || row.lifecycle_generation !== index.session.lifecycle_generation) {
      throw new Error(`RAW_TRACE_SESSION_MISMATCH: sequence=${row.sequence}`);
    }
    previous = row.sequence;
  }
  return { ...source, rows, artifact: rawArtifact };
}

function rawRef(row) {
  return `trace/raw/astronstudio-provider-events.jsonl#L${row.raw_line}`;
}

function uniqueUsageRows(rows) {
  const selected = rows.filter((row) => row.event_type === "thread.token-usage.updated");
  const result = [];
  let previousSignature = null;
  let previousUsage = null;
  for (const row of selected) {
    const usageValue = row.event?.payload?.usage;
    if (!usageValue || typeof usageValue !== "object") {
      result.push({ ...row, usage: null });
      previousSignature = null;
      previousUsage = null;
      continue;
    }
    const signature = JSON.stringify(Object.fromEntries(
      Object.values(EXPOSED_USAGE).flat().map((field) => [field, usageValue[field] ?? null]),
    ));
    if (signature === previousSignature) continue;
    if (previousUsage) {
      for (const [, cumulativeField] of Object.values(EXPOSED_USAGE)) {
        const before = count(previousUsage[cumulativeField]);
        const after = count(usageValue[cumulativeField]);
        if (before != null && after != null && after < before) {
          throw new Error(`CUMULATIVE_USAGE_RESET: ${cumulativeField}`);
        }
      }
    }
    result.push({ ...row, usage: usageValue });
    previousSignature = signature;
    previousUsage = usageValue;
  }
  return result;
}

function metric(value, status, basis) {
  return { value, status, basis };
}

function coverage(known, total, unit) {
  return { known, total, unit };
}

function sum(values) {
  return values.reduce((total, value) => total + value, 0);
}

function parseUsageMetrics(rows, warnings, knownSubtotals, coverages, metricSources) {
  const usageRows = uniqueUsageRows(rows);
  const totalUpdates = usageRows.length;
  const output = {};
  for (const [metricName, [lastField, cumulativeField]] of Object.entries(EXPOSED_USAGE)) {
    const known = usageRows.filter((row) => count(row.usage?.[lastField]) != null
      && count(row.usage?.[cumulativeField]) != null);
    const values = known.map((row) => row.usage[lastField]);
    let reconciled = totalUpdates > 0 && known.length === totalUpdates;
    if (reconciled) {
      let previous = usageRows[0].usage[cumulativeField] - usageRows[0].usage[lastField];
      reconciled = count(previous) != null;
      for (const row of usageRows) {
        const next = row.usage[cumulativeField];
        const increment = row.usage[lastField];
        if (next !== previous + increment) reconciled = false;
        previous = next;
      }
    }
    const subtotal = values.length ? sum(values) : null;
    if (reconciled) {
      output[metricName] = metric(
        subtotal,
        "observed",
        `native per-response ${lastField} sum reconciled with ${cumulativeField}; cache and reasoning are subsets`,
      );
    } else {
      output[metricName] = metric(
        null,
        totalUpdates ? "partial" : "unavailable",
        totalUpdates
          ? `incomplete or unreconciled ${lastField}/${cumulativeField} observations`
          : "bound turn exposes no native usage update",
      );
      if (subtotal != null) knownSubtotals[metricName] = subtotal;
      if (totalUpdates) warnings.push(`USAGE_${metricName.toUpperCase()}_PARTIAL`);
    }
    coverages[metricName] = coverage(known.length, totalUpdates, "usage_update");
    metricSources[metricName] = usageRows.length
      ? usageRows.map(rawRef)
      : ["trace/raw/astronstudio-provider-events.jsonl"];
  }

  for (const row of usageRows) {
    const usageValue = row.usage;
    if (!usageValue) continue;
    const input = count(usageValue.lastInputTokens);
    const outputValue = count(usageValue.lastOutputTokens);
    const total = count(usageValue.lastUsedTokens);
    const cached = count(usageValue.lastCachedInputTokens);
    const reasoning = count(usageValue.lastReasoningOutputTokens);
    if (input != null && outputValue != null && total != null && total !== input + outputValue) {
      throw new Error(`TOKEN_SEMANTICS_MISMATCH: line=${row.raw_line}`);
    }
    if (input != null && cached != null && cached > input) {
      throw new Error(`CACHE_SEMANTICS_MISMATCH: line=${row.raw_line}`);
    }
    if (outputValue != null && reasoning != null && reasoning > outputValue) {
      throw new Error(`REASONING_SEMANTICS_MISMATCH: line=${row.raw_line}`);
    }
  }
  if (output.input_tokens.value != null && output.output_tokens.value != null
      && output.total_tokens.value != null
      && output.total_tokens.value !== output.input_tokens.value + output.output_tokens.value) {
    throw new Error("TOKEN_TOTAL_RECONCILIATION_FAILED");
  }
  if (output.input_tokens.value != null && output.cache_read_input_tokens.value != null
      && output.cache_read_input_tokens.value > output.input_tokens.value) {
    throw new Error("CACHE_TOTAL_RECONCILIATION_FAILED");
  }
  if (output.output_tokens.value != null && output.reasoning_output_tokens.value != null
      && output.reasoning_output_tokens.value > output.output_tokens.value) {
    throw new Error("REASONING_TOTAL_RECONCILIATION_FAILED");
  }

  output.cache_creation_input_tokens = metric(
    null,
    "unavailable",
    "AstronStudio provider runtime events do not expose cache creation input tokens",
  );
  coverages.cache_creation_input_tokens = coverage(0, totalUpdates, "usage_update");
  metricSources.cache_creation_input_tokens = usageRows.length
    ? usageRows.map(rawRef)
    : ["trace/raw/astronstudio-provider-events.jsonl"];

  const requestReconciled = output.total_tokens.status === "observed";
  output.request_count = metric(
    requestReconciled ? totalUpdates : null,
    requestReconciled ? "inferred" : totalUpdates ? "partial" : "unavailable",
    "count of advancing native usage snapshots reconciled with per-response token increments; not HTTP attempts",
  );
  if (!requestReconciled && totalUpdates) knownSubtotals.request_count = totalUpdates;
  coverages.request_count = coverage(requestReconciled ? totalUpdates : 0, totalUpdates, "usage_update");
  metricSources.request_count = usageRows.length
    ? usageRows.map(rawRef)
    : ["trace/raw/astronstudio-provider-events.jsonl"];

  output.request_attempt_count = metric(
    null,
    "unavailable",
    "provider runtime events do not expose lower-level HTTP attempts or retries",
  );
  coverages.request_attempt_count = coverage(0, null, "http_attempt");
  metricSources.request_attempt_count = ["trace/raw/astronstudio-provider-events.jsonl"];
  return { output, usageRows };
}

function parseToolMetric(rows, traceIndex, knownSubtotals, coverages, metricSources) {
  const calls = new Map();
  for (const row of rows) {
    const item = row.event?.payload?.data?.item;
    if (row.event_type !== "item.started" || !TOOL_ITEM_TYPES.has(item?.type)) continue;
    const callId = String(item?.id || row.event?.itemId || "");
    if (!callId) throw new Error(`TOOL_CALL_ID_MISSING: line=${row.raw_line}`);
    if (calls.has(callId)) throw new Error(`TOOL_CALL_DUPLICATE: ${callId}`);
    calls.set(callId, row);
  }
  const indexed = new Set((traceIndex.calls || []).map((entry) => entry.call_id));
  if (indexed.size !== calls.size || [...calls.keys()].some((callId) => !indexed.has(callId))) {
    throw new Error("TOOL_CALL_INDEX_MISMATCH");
  }
  const complete = traceIndex.completeness?.status === "complete";
  if (!complete) knownSubtotals.call_count = calls.size;
  coverages.call_count = coverage(calls.size, complete ? calls.size : null, "tool_call");
  metricSources.call_count = calls.size
    ? [...calls.values()].map(rawRef)
    : ["trace/trace-index.json#/calls", "trace/raw/astronstudio-provider-events.jsonl"];
  return metric(
    complete ? calls.size : null,
    complete ? "observed" : "partial",
    "unique native item.started call ID; result events excluded and call set reconciled with trace index",
  );
}

function parseTimingMetrics(rows, state, knownSubtotals, coverages, metricSources) {
  const start = state.execution.started_at;
  const finish = state.execution.finished_at;
  const calculatedDuration = typeof finish === "string" ? elapsedSeconds(start, finish) : null;
  const recordedDuration = typeof state.execution.duration_seconds === "number"
    && Number.isFinite(state.execution.duration_seconds)
    && state.execution.duration_seconds >= 0
    ? state.execution.duration_seconds
    : null;
  if (calculatedDuration != null && recordedDuration != null
      && Math.abs(calculatedDuration - recordedDuration) > 0.001) {
    throw new Error("EXECUTION_DURATION_MISMATCH");
  }
  const duration = recordedDuration ?? calculatedDuration;
  const durationMetric = metric(
    duration,
    duration == null ? "unavailable" : "observed",
    "execution driver wall clock from attempt start through terminal observation",
  );
  coverages.duration_seconds = coverage(duration == null ? 0 : 1, 1, "attempt");
  metricSources.duration_seconds = ["execution/automation-state.json#/execution"];

  const starts = rows.filter((row) => row.event_type === "turn.started");
  const finishes = rows.filter((row) => row.event_type === "turn.completed");
  let agentDuration = null;
  if (starts.length === 1 && finishes.length === 1) {
    const startAt = starts[0].event?.createdAt || starts[0].persisted_at;
    const finishAt = finishes[0].event?.createdAt || finishes[0].persisted_at;
    agentDuration = elapsedSeconds(startAt, finishAt);
  }
  const complete = agentDuration != null && state.session.native_status === "completed";
  if (!complete && agentDuration != null) knownSubtotals.agent_duration_seconds = agentDuration;
  coverages.agent_duration_seconds = coverage(complete ? 1 : 0, 1, "turn");
  metricSources.agent_duration_seconds = [
    ...(starts[0] ? [rawRef(starts[0])] : []),
    ...(finishes[0] ? [rawRef(finishes[0])] : []),
  ];
  if (!metricSources.agent_duration_seconds.length) {
    metricSources.agent_duration_seconds = ["trace/raw/astronstudio-provider-events.jsonl"];
  }
  return {
    duration_seconds: durationMetric,
    agent_duration_seconds: metric(
      complete ? agentDuration : null,
      complete ? "observed" : agentDuration == null ? "unavailable" : "partial",
      "native turn.started to turn.completed timestamp for the bound turn",
    ),
  };
}

function downgradeEventMetricsForPartialTrace(document, traceComplete) {
  if (traceComplete) return;
  const eventMetrics = [
    [document.metrics.usage, "input_tokens"],
    [document.metrics.usage, "output_tokens"],
    [document.metrics.usage, "total_tokens"],
    [document.metrics.usage, "cache_read_input_tokens"],
    [document.metrics.usage, "reasoning_output_tokens"],
    [document.metrics.requests, "request_count"],
    [document.metrics.tools, "call_count"],
    [document.metrics.timing, "agent_duration_seconds"],
  ];
  for (const [group, name] of eventMetrics) {
    const entry = group[name];
    if (!new Set(["observed", "inferred"]).has(entry.status)) continue;
    document.collection.known_subtotals[name] = entry.value;
    entry.value = null;
    entry.status = "partial";
    entry.basis = `${entry.basis}; trace index is not complete`;
  }
}

function artifact(path, bytes) {
  return { path, sha256: sha256(bytes), size: bytes.length };
}

export function buildAstronStudioResourceMetrics({ state, traceIndex, rows, sources }) {
  assertExecutionState(state);
  assertTraceBinding(state, traceIndex);
  const warnings = [];
  const knownSubtotals = {};
  const coverages = {};
  const metricSources = {};
  const parsedUsage = parseUsageMetrics(
    rows,
    warnings,
    knownSubtotals,
    coverages,
    metricSources,
  );
  const toolMetric = parseToolMetric(
    rows,
    traceIndex,
    knownSubtotals,
    coverages,
    metricSources,
  );
  const timingMetrics = parseTimingMetrics(
    rows,
    state,
    knownSubtotals,
    coverages,
    metricSources,
  );
  const traceComplete = traceIndex.completeness?.status === "complete"
    && traceIndex.completeness?.omitted_event_count === 0;
  const exposedComplete = Object.keys(EXPOSED_USAGE)
    .every((name) => parsedUsage.output[name].status === "observed");
  const collectionStatus = traceComplete && exposedComplete
    && toolMetric.status === "observed"
    && timingMetrics.duration_seconds.status === "observed"
    && timingMetrics.agent_duration_seconds.status === "observed"
    ? "complete"
    : "partial";
  if (!traceComplete) warnings.push("TRACE_INCOMPLETE");
  const collectedAt = state.execution.finished_at
    || state.session.last_observed_at
    || rows.at(-1)?.persisted_at;
  if (typeof collectedAt !== "string" || !Number.isFinite(Date.parse(collectedAt))) {
    throw new Error("COLLECTION_TIMESTAMP_UNAVAILABLE");
  }
  const document = {
    schema_id: RESOURCE_SCHEMA,
    schema_version: 1,
    identity: { ...state.identity },
    collection: {
      collector: RESOURCE_COLLECTOR,
      version: RESOURCE_COLLECTOR_VERSION,
      status: collectionStatus,
      collected_at: collectedAt,
      sources,
      warnings: [...new Set(warnings)].sort(),
      excluded_scope: [
        "judge_usage",
        "control_usage",
        "client_background_services",
        "unobserved_http_retries",
        "cache_creation_input_tokens",
        "request_attempt_count",
      ],
      coverage: Object.fromEntries(METRIC_NAMES.map((name) => [name, coverages[name]])),
      known_subtotals: knownSubtotals,
      metric_sources: Object.fromEntries(METRIC_NAMES.map((name) => [name, metricSources[name]])),
    },
    metrics: {
      usage: {
        input_tokens: parsedUsage.output.input_tokens,
        output_tokens: parsedUsage.output.output_tokens,
        total_tokens: parsedUsage.output.total_tokens,
        cache_read_input_tokens: parsedUsage.output.cache_read_input_tokens,
        cache_creation_input_tokens: parsedUsage.output.cache_creation_input_tokens,
        reasoning_output_tokens: parsedUsage.output.reasoning_output_tokens,
      },
      requests: {
        request_count: parsedUsage.output.request_count,
        request_attempt_count: parsedUsage.output.request_attempt_count,
      },
      tools: { call_count: toolMetric },
      timing: timingMetrics,
    },
  };
  downgradeEventMetricsForPartialTrace(document, traceComplete);
  return document;
}

async function atomicWrite(path, bytes) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  await writeFile(temporary, bytes, { flag: "wx" });
  try {
    await rename(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

async function assertWritableTarget(path, replace) {
  try {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error(`UNSAFE_OUTPUT_TARGET: ${path}`);
    if (!replace) throw new Error(`OUTPUT_EXISTS: ${path}`);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

export async function collectAstronStudioResourceMetrics(options) {
  const stateSource = await readJsonFile(options.stateFile);
  const indexSource = await readJsonFile(options.traceIndex);
  assertExecutionState(stateSource.value);
  assertTraceBinding(stateSource.value, indexSource.value);
  const rawSource = await readIndexedRawTrace(indexSource.absolute, indexSource.value);
  const outputPath = resolve(options.output || resolve(dirname(indexSource.absolute), "resource-metrics.json"));
  await assertWritableTarget(outputPath, Boolean(options.replace));
  const sources = [
    artifact("execution/automation-state.json", stateSource.bytes),
    artifact("trace/trace-index.json", indexSource.bytes),
    artifact("trace/raw/astronstudio-provider-events.jsonl", rawSource.bytes),
  ];
  const document = buildAstronStudioResourceMetrics({
    state: stateSource.value,
    traceIndex: indexSource.value,
    rows: rawSource.rows,
    sources,
  });
  const bytes = Buffer.from(`${JSON.stringify(document, null, 2)}\n`, "utf8");
  await atomicWrite(outputPath, bytes);
  return {
    status: "PASS",
    output: outputPath,
    sha256: sha256(bytes),
    size: bytes.length,
    collection_status: document.collection.status,
    metrics: document.metrics,
  };
}

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  if (parsed.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  const result = await collectAstronStudioResourceMetrics(parsed);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

const isEntrypoint = process.argv[1]
  && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
