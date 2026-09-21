import { createHash } from "node:crypto";
import { lstat, readFile, realpath } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createNativeResourceMetricParsers } from "../resource-metrics/native-parsers.mjs";
import { findTraceFiles } from "../resource-metrics/trace-io.mjs";

// Version of the frozen JSONL supplement algorithm, retained for old packages.
export const VERSION = "0.1.0";
export const SUPPLEMENT_SCHEMA = "wildclawbench.workbuddy-resource-supplement/v1";
const MAX_BYTES = 64 * 1024 * 1024;
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
export const jsonBytes = (value) => Buffer.from(JSON.stringify(value, null, 2) + "\n");
export const artifact = (path, bytes) => ({ path, sha256: sha(bytes), size: bytes.length });
const canonical = (value) => Array.isArray(value) ? value.map(canonical)
  : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])])) : value;
export const equal = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
function fail(message) { throw new Error(`WORKBUDDY_JSONL_${message}`); }

export async function safeRead(root, path) {
  const base = await realpath(root);
  const rel = relative(resolve(root), resolve(path));
  if (!rel || rel === ".." || rel.startsWith("../") || isAbsolute(rel)) fail("PATH_OUTSIDE_ROOT");
  let current = base;
  for (const part of rel.split("/")) {
    current = join(current, part);
    const info = await lstat(current);
    if (info.isSymbolicLink()) fail("SYMLINK");
  }
  const before = await lstat(current);
  if (!before.isFile() || before.size > MAX_BYTES) fail("UNSAFE_FILE");
  const bytes = await readFile(current);
  const after = await lstat(current);
  if (bytes.length > MAX_BYTES || before.ino !== after.ino || before.size !== after.size
      || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs) fail("SOURCE_CHANGED");
  return bytes;
}

export async function discoverJsonl(root, sessionId) {
  if (!/^[A-Za-z0-9_-]{8,100}$/u.test(sessionId || "")) fail("SESSION_ID_INVALID");
  try {
    const info = await lstat(root);
    if (!info.isDirectory() || info.isSymbolicLink()) fail("UNSAFE_ROOT");
  } catch (error) { if (error.code === "ENOENT") return null; throw error; }
  const files = await findTraceFiles(root, 1, name => name === `${sessionId}.jsonl`);
  if (!files.length) return null;
  if (files.length !== 1) fail("AMBIGUOUS_TRACE");
  return { bytes: await safeRead(root, files[0]), path: files[0] };
}

const parser = createNativeResourceMetricParsers({
  schemaVersion: "wildclawbench.workbuddy-jsonl-metrics/v1", version: VERSION,
  scope: "bound-primary-conversation-responses", excludedScope: ["unobserved-http-retries", "unlinked-child-agents"],
}).parseWorkBuddy;
const textOf = content => typeof content === "string" ? content
  : Array.isArray(content) ? content.filter(x => ["text", "input_text", "output_text"].includes(x.type)).map(x => x.text || "").join("") : "";

export function parseBoundJsonl(bytes, { snapshot, session, promptSha256 }) {
  if (snapshot?.conversation?.id !== session.session_id || snapshot?.request?.id !== session.turn_id
      || snapshot?.conversation?.space?.cwd !== session.cwd) fail("RUNTIME_IDENTITY_MISMATCH");
  const prompt = textOf(snapshot.request.userMessage?.content);
  if (sha(prompt) !== promptSha256) fail("RUNTIME_PROMPT_MISMATCH");
  const rows = bytes.toString("utf8").split(/\r?\n/u).filter(x => x.trim()).map(JSON.parse);
  if (rows.some(x => (x.sessionId && x.sessionId !== session.session_id) || (x.cwd && x.cwd !== session.cwd))) fail("IDENTITY_MISMATCH");
  const events = rows.filter(x => ["message", "function_call", "function_call_result"].includes(x.type));
  if (!events.length || events.some(x => x.sessionId !== session.session_id || x.cwd !== session.cwd)) fail("IDENTITY_MISMATCH");
  const users = events.filter(x => x.type === "message" && x.role === "user" && !x.providerData?.isMeta);
  if (users.length !== 1) fail("USER_TURN_MISMATCH");
  const nativePrompt = textOf(users[0].content);
  // WorkBuddy adds context before the exact user_query. Require one terminal
  // wrapper and preserve the original Prompt digest rather than hashing context.
  const wrapped = [ `<user_query>${prompt}</user_query>`, `<user_query>\n${prompt}\n</user_query>` ].some(s => nativePrompt.endsWith(s))
    && nativePrompt.split("<user_query>").length === 2;
  if (nativePrompt !== prompt && !wrapped) fail("PROMPT_MISMATCH");
  const traceId = snapshot.request.traceId || snapshot.request.conversationRequestId;
  if (!traceId || events.filter(x => x.providerData?.messageId).some(x => x.providerData.conversationRequestId !== traceId)) fail("REQUEST_SCOPE_MISMATCH");
  const runtimeCalls = new Set((snapshot.request.assistantMessage?.content || [])
    .filter(x => x.type === "tool" || x.sessionUpdate === "tool_call_update").map(x => x.toolCallId));
  const nativeCalls = new Set(events.filter(x => x.type === "function_call").map(x => x.callId));
  if (!equal([...runtimeCalls].sort(), [...nativeCalls].sort())) fail("TOOL_COVERAGE_MISMATCH");
  const finals = [...new Map(events.filter(x => x.type === "message" && x.role === "assistant")
    .map(x => [JSON.stringify([x.id, x.content]), x])).values()];
  const runtimeFinal = textOf(snapshot.request.assistantMessage?.content);
  if (!finals.length || !runtimeFinal || finals.map(x => textOf(x.content)).join("") !== runtimeFinal) fail("FINAL_RESPONSE_MISMATCH");
  const rawById = new Map();
  for (const row of events) {
    const pd = row.providerData || {}, raw = pd.rawUsage, usage = pd.usage;
    if (raw && usage) {
      if (raw.prompt_tokens !== usage.inputTokens || raw.completion_tokens !== usage.outputTokens
          || raw.total_tokens !== usage.totalTokens) fail("RAW_USAGE_MISMATCH");
      if (raw.prompt_tokens_details?.cached_tokens != null
          && raw.prompt_tokens_details.cached_tokens !== usage.inputTokensDetails?.reduce((s, x) => s + x.cached_tokens, 0)) fail("CACHE_USAGE_MISMATCH");
      if (rawById.has(pd.messageId) && !equal(rawById.get(pd.messageId), raw)) fail("CONFLICTING_RAW_USAGE");
      rawById.set(pd.messageId, raw);
    }
  }
  const parsed = parser(rows);
  const usages = new Map(events.filter(x => x.providerData?.usage).map(x => [x.providerData.messageId, x.providerData.usage]));
  const read = (u, field) => ({ input_tokens: u.inputTokens, output_tokens: u.outputTokens, total_tokens: u.totalTokens,
    cache_read_input_tokens: u.inputTokensDetails?.reduce((sum, x) => sum + x.cached_tokens, 0),
    reasoning_output_tokens: u.outputTokensDetails?.reduce((sum, x) => sum + x.reasoning_tokens, 0) })[field];
  parsed.collection.field_coverage = Object.fromEntries(Object.keys(parsed.usage).map(field => [field, {
    known: field === "request_count" ? parsed.collection.response_coverage.total
      : [...usages.values()].filter(u => Number.isSafeInteger(read(u, field)) && read(u, field) >= 0).length,
    total: parsed.collection.response_coverage.total, unit: "model_response",
  }]));
  // Some client builds fill a missing reasoning detail with zero. Only claim
  // a measured reasoning value when the provider's raw usage exposes it.
  if ([...rawById.values()].some(x => x.completion_tokens_details?.reasoning_tokens == null)
      || rawById.size !== parsed.collection.response_coverage.total) {
    parsed.usage.reasoning_output_tokens = null;
    parsed.collection.metrics.reasoning_output_tokens = { status: "unavailable", basis: "Provider rawUsage does not expose reasoning tokens; normalized zero is not evidence" };
    parsed.collection.field_coverage.reasoning_output_tokens.known = 0;
    delete parsed.collection.known_subtotals?.reasoning_output_tokens;
  }
  return parsed;
}

export function applyJsonlMetrics(base, parsed, source, collectedAt = base.collection.collected_at) {
  const result = structuredClone(base);
  if (!Number.isFinite(Date.parse(collectedAt))) fail("COLLECTION_TIME_INVALID");
  result.collection.collected_at = collectedAt;
  const groups = { usage: parsed.usage, requests: parsed.usage, tools: parsed.tools };
  for (const [group, fields] of Object.entries(result.metrics)) {
    if (!groups[group]) continue;
    for (const field of Object.keys(fields)) {
      const value = groups[group][field] ?? null;
      const meta = parsed.collection.metrics[field];
      const coverage = { ...(parsed.collection.field_coverage[field] || parsed.collection.response_coverage), unit: "model_response" };
      if (field === "call_count") Object.assign(coverage, { known: value, total: value, unit: "tool_call" });
      if (value === null) coverage.known = meta.status === "partial" ? coverage.known : 0;
      fields[field] = { value, status: meta.status, basis: `WorkBuddy session JSONL: ${meta.basis}` };
      result.collection.coverage[field] = coverage;
      if (parsed.collection.known_subtotals?.[field] != null) result.collection.known_subtotals[field] = parsed.collection.known_subtotals[field];
      else delete result.collection.known_subtotals[field];
      result.collection.metric_sources[field] = [source.path];
    }
  }
  result.collection.collector = "workbuddy-jsonl-resource-adapter";
  result.collection.version = VERSION;
  const existing = result.collection.sources.find(x => x.path === source.path);
  if (existing && !equal(existing, source)) fail("SOURCE_DIGEST_CONFLICT");
  if (!existing) result.collection.sources.push(source);
  result.collection.warnings = [
    ...parsed.collection.warnings,
    "request_count counts persisted model responses, not user turns or HTTP attempts; cache-read is included in input_tokens.",
  ];
  return result;
}

export function withoutModelResponseCount(resource) {
  const r = structuredClone(resource);
  const coverage = { known: 0, total: 0, unit: "model_response" };
  r.metrics.requests.request_count = { value: null, status: "unavailable",
    basis: "A bound WorkBuddy conversation request does not identify its underlying model response count; session JSONL unavailable" };
  r.collection.coverage.request_count = coverage;
  delete r.collection.known_subtotals.request_count;
  r.collection.warnings.push("WORKBUDDY_SESSION_JSONL_UNAVAILABLE");
  return r;
}

export function supplementalMetrics(original, parsed, source, createdAt) {
  const base = structuredClone(original.base);
  const prefix = dirname(original.resource.path);
  // Supplements live beside immutable task evidence. Their provenance paths
  // explicitly use the unit root rather than the old resource file directory.
  base.collection.sources = base.collection.sources.map(x => ({ ...x, path: `${prefix}/${x.path}` }));
  base.collection.metric_sources = Object.fromEntries(Object.entries(base.collection.metric_sources)
    .map(([key, refs]) => [key, refs.map(ref => `${prefix}/${ref}`)]));
  return applyJsonlMetrics(base, parsed, { ...source, path: `evidence/resource-supplements/${original.record.identity.task_id}/${source.path}` }, createdAt);
}

// Read an already frozen original record/binding, never infer an attempt from
// the latest session. This also works inside an imported return package.
export async function originalResources(unitRoot, executionPath) {
  const executionBytes = await safeRead(unitRoot, executionPath);
  const record = JSON.parse(executionBytes);
  if (record.harness?.id !== "workbuddy" || record.phase !== "COMPLETED" || record.session?.verified !== true) fail("ORIGINAL_NOT_COMPLETE");
  const receipt = JSON.parse(await safeRead(unitRoot, join(unitRoot, "receipts/collect-evidence-receipt.json")));
  const check = (refs, path, bytes) => {
    const ref = refs.find(x => x.path === relative(unitRoot, path));
    if (!ref || ref.sha256 !== sha(bytes) || ref.size !== bytes.length) fail("ORIGINAL_EVIDENCE_DRIFT");
  };
  check(receipt.artifacts, executionPath, executionBytes);
  const manifestPath = join(resolve(executionPath, ".."), "evidence-manifest.json");
  const manifestBytes = await safeRead(unitRoot, manifestPath);
  check(receipt.artifacts, manifestPath, manifestBytes);
  const artifacts = JSON.parse(manifestBytes).artifacts;
  const metricsPath = join(unitRoot, record.resource_metrics_path);
  const metricsBytes = await safeRead(unitRoot, metricsPath);
  check(artifacts, metricsPath, metricsBytes);
  const tracePath = join(unitRoot, record.evidence.trace_index_path);
  const traceBytes = await safeRead(unitRoot, tracePath);
  check(artifacts, tracePath, traceBytes);
  const index = JSON.parse(traceBytes);
  const traceRoot = resolve(tracePath, "..");
  const candidates = [];
  for (const ref of index.raw_trace || []) {
    const bytes = await safeRead(unitRoot, join(traceRoot, ref.path));
    if (sha(bytes) !== ref.sha256 || bytes.length !== ref.size) fail("ORIGINAL_TRACE_DRIFT");
    if (ref.path.endsWith(".json")) {
      const value = JSON.parse(bytes);
      if (value.runtime_snapshot) candidates.push({ snapshot: value.runtime_snapshot,
        source: artifact(relative(unitRoot, join(traceRoot, ref.path)), bytes) });
    }
  }
  if (candidates.length !== 1) fail("ORIGINAL_RUNTIME_MISSING_OR_AMBIGUOUS");
  return { record, base: JSON.parse(metricsBytes), snapshot: candidates[0].snapshot, snapshotSource: candidates[0].source,
    execution: artifact(relative(unitRoot, executionPath), executionBytes),
    resource: artifact(record.resource_metrics_path, metricsBytes) };
}

export async function verifySupplement(unitRoot, taskId, executionPath) {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(taskId)) fail("TASK_ID_INVALID");
  const dir = join(unitRoot, "evidence/resource-supplements", taskId);
  const manifest = JSON.parse(await safeRead(unitRoot, join(dir, "supplement.json")));
  const original = await originalResources(unitRoot, executionPath);
  if (manifest.schema_version !== SUPPLEMENT_SCHEMA || manifest.collector_version !== VERSION || manifest.resource_path_base !== "unit"
      || !equal(manifest.identity, original.record.identity)
      || !equal(manifest.dataset, original.record.dataset) || manifest.base_execution.sha256 !== original.execution.sha256
      || !equal(manifest.base_resource, original.resource)) fail("SUPPLEMENT_BINDING_MISMATCH");
  const receiptBytes = await safeRead(unitRoot, join(unitRoot, "receipts/collect-evidence-receipt.json"));
  if (!equal(artifact("receipts/collect-evidence-receipt.json", receiptBytes), manifest.base_collect_receipt)) fail("SUPPLEMENT_RECEIPT_DRIFT");
  const bytes = await safeRead(dir, join(dir, "native.jsonl"));
  const source = artifact("native.jsonl", bytes);
  if (!equal(source, manifest.native)) fail("SUPPLEMENT_NATIVE_DRIFT");
  const parsed = parseBoundJsonl(bytes, { snapshot: original.snapshot, session: original.record.session, promptSha256: original.record.prompt.sha256 });
  const expected = supplementalMetrics(original, parsed, source, manifest.created_at);
  for (const ref of expected.collection.sources) {
    const bytes = await safeRead(unitRoot, join(unitRoot, ref.path));
    if (sha(bytes) !== ref.sha256 || bytes.length !== ref.size) fail("SUPPLEMENT_SOURCE_DRIFT");
  }
  const metricsBytes = await safeRead(dir, join(dir, "resource-metrics.json"));
  if (!equal(artifact("resource-metrics.json", metricsBytes), manifest.resource)
      || !equal(JSON.parse(metricsBytes), expected)) fail("SUPPLEMENT_METRICS_MISMATCH");
  return { status: "PASS", resource_metrics_path: join(dir, "resource-metrics.json"),
    supplement_sha256: sha(await safeRead(unitRoot, join(dir, "supplement.json"))), base_resource_sha256: original.resource.sha256 };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [flag, root, task, record] = process.argv.slice(2);
  if (flag !== "--verify-supplement" || !root || !task || !record) throw new Error("usage: --verify-supplement UNIT TASK EXECUTION_RECORD");
  console.log(JSON.stringify(await verifySupplement(root, task, record)));
}
