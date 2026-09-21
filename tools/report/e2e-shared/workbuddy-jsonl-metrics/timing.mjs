import { createHash } from "node:crypto";
import { lstat } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { artifact, equal, originalResources, safeRead, verifySupplement } from "./index.mjs";

export const TIMING_VERSION = "0.1.0";
export const TIMING_SCHEMA = "wildclawbench.workbuddy-timing-supplement/v1";
function fail(message) { throw new Error(`WORKBUDDY_TIMING_${message}`); }
const digest = bytes => createHash("sha256").update(bytes).digest("hex");

function epoch(value, field) {
  if (value == null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0
      || !Number.isFinite(new Date(value).getTime())) fail(`INVALID_TIMESTAMP: ${field}`);
  return value;
}
function sentEpoch(value) {
  if (value == null) return null;
  if (typeof value !== "string" || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/u.test(value)
      || !Number.isFinite(Date.parse(value))) fail("INVALID_TIMESTAMP: prompt.sent_at");
  return Date.parse(value);
}

export function workBuddyTiming({ snapshot, session, prompt }) {
  const request = snapshot?.request;
  if (!request || snapshot.conversation?.id !== session.session_id || request.id !== session.turn_id
      || snapshot.conversation?.space?.cwd !== session.cwd || session.verified !== true) fail("IDENTITY_MISMATCH");
  const content = request.userMessage?.content;
  const text = typeof content === "string" ? content : (content || []).filter(x => x.type === "text").map(x => x.text || "").join("");
  if (!prompt?.sha256 || digest(text) !== prompt.sha256) fail("PROMPT_MISMATCH");
  const started = epoch(request.startedAt, "request.startedAt"), timestamp = epoch(request.timestamp, "request.timestamp");
  const completed = epoch(request.completedAt, "request.completedAt"), finish = epoch(request.finishTimestamp, "request.finishTimestamp");
  const start = started ?? timestamp, end = completed ?? finish, sent = sentEpoch(prompt.sent_at);
  // finishTimestamp marks the earlier internal finish; completedAt includes final persistence.
  if ((start !== null && end !== null && end < start) || (finish !== null && start !== null && finish < start)
      || (completed !== null && finish !== null && completed < finish)
      || (sent !== null && ((start !== null && sent > start) || (end !== null && sent > end)))) fail("TIMESTAMP_ORDER");
  const startField = started !== null ? "startedAt" : "timestamp";
  const endField = completed !== null ? "completedAt" : "finishTimestamp";
  const metric = (from, basis) => ({
    value: from !== null && end !== null ? (end - from) / 1000 : null,
    status: from !== null && end !== null ? "observed" : "unavailable",
    basis: `${basis}; ${from === null || end === null ? "required timestamp missing" : "milliseconds converted to seconds"}; not model inference time`,
  });
  return {
    duration_seconds: metric(sent, `WorkBuddy task flow: prompt.sent_at -> request.${endField}; includes dispatch/queue wait`),
    agent_duration_seconds: metric(start, `WorkBuddy native request lifetime: request.${startField} -> request.${endField}; includes tools and client processing`),
  };
}

export function applyWorkBuddyTiming(base, binding, sources, collectedAt = base.collection.collected_at) {
  const result = structuredClone(base);
  if (!Number.isFinite(Date.parse(collectedAt))) fail("COLLECTION_TIME_INVALID");
  if (!Array.isArray(sources) || !sources.length) fail("SOURCES_MISSING");
  for (const source of sources) {
    const previous = result.collection.sources.find(x => x.path === source.path);
    if (previous && !equal(previous, source)) fail("SOURCE_DIGEST_CONFLICT");
    if (!previous) result.collection.sources.push(source);
  }
  const metrics = workBuddyTiming(binding);
  for (const [field, metric] of Object.entries(metrics)) {
    result.metrics.timing[field] = metric;
    result.collection.coverage[field] = { known: metric.value === null ? 0 : 1, total: 1, unit: "task" };
    result.collection.metric_sources[field] = sources.map(x => x.path);
    delete result.collection.known_subtotals[field];
  }
  result.collection.collected_at = collectedAt;
  result.collection.collector = "workbuddy-native-timing-resource-adapter";
  result.collection.version = TIMING_VERSION;
  return result;
}

async function exists(path) {
  try { await lstat(path); return true; } catch (error) { if (error.code === "ENOENT") return false; throw error; }
}

export async function timingSupplementInput(unitRoot, executionPath) {
  const original = await originalResources(unitRoot, executionPath);
  const { record } = original;
  let base = structuredClone(original.base), tokenSupplement = null;
  const tokenPath = join(unitRoot, "evidence/resource-supplements", record.identity.task_id);
  if (await exists(tokenPath)) {
    const verified = await verifySupplement(unitRoot, record.identity.task_id, executionPath);
    base = JSON.parse(await safeRead(unitRoot, verified.resource_metrics_path));
    tokenSupplement = verified.supplement_sha256;
  } else {
    const prefix = dirname(original.resource.path);
    base.collection.sources = base.collection.sources.map(x => ({ ...x, path: `${prefix}/${x.path}` }));
    base.collection.metric_sources = Object.fromEntries(Object.entries(base.collection.metric_sources)
      .map(([key, refs]) => [key, refs.map(ref => `${prefix}/${ref}`)]));
  }
  const receiptBytes = await safeRead(unitRoot, join(unitRoot, "receipts/collect-evidence-receipt.json"));
  const value = JSON.parse(receiptBytes);
  if (value.status !== "completed" || value.stage !== "collect-evidence"
      || !equal(value.scope, { batch_id: record.identity.batch_id, unit_id: record.identity.unit_id })) fail("COLLECT_RECEIPT_MISMATCH");
  const receipt = artifact("receipts/collect-evidence-receipt.json", receiptBytes);
  return { original, base, binding: { snapshot: original.snapshot, session: record.session, prompt: record.prompt },
    sources: [original.snapshotSource, original.execution], manifest: {
      schema_version: TIMING_SCHEMA, collector_version: TIMING_VERSION, resource_path_base: "unit",
      identity: record.identity, dataset: record.dataset, base_execution: original.execution,
      base_resource: original.resource, base_collect_receipt: receipt, token_supplement_sha256: tokenSupplement,
    } };
}

export async function verifyTimingSupplement(unitRoot, taskId, executionPath) {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(taskId)) fail("TASK_ID_INVALID");
  const dir = join(unitRoot, "evidence/timing-supplements", taskId);
  const manifestBytes = await safeRead(unitRoot, join(dir, "supplement.json"));
  const { created_at, resource, ...manifest } = JSON.parse(manifestBytes);
  const input = await timingSupplementInput(unitRoot, executionPath);
  if (input.original.record.identity.task_id !== taskId || !equal(manifest, input.manifest)) fail("SUPPLEMENT_BINDING_MISMATCH");
  const expected = applyWorkBuddyTiming(input.base, input.binding, input.sources, created_at);
  for (const source of expected.collection.sources) {
    const bytes = await safeRead(unitRoot, join(unitRoot, source.path));
    if (!equal(artifact(source.path, bytes), source)) fail("SUPPLEMENT_SOURCE_DRIFT");
  }
  const metricsPath = join(dir, "resource-metrics.json"), bytes = await safeRead(unitRoot, metricsPath);
  if (!equal(artifact("resource-metrics.json", bytes), resource) || !equal(JSON.parse(bytes), expected)) fail("SUPPLEMENT_METRICS_MISMATCH");
  return { status: "PASS", resource_metrics_path: metricsPath, supplement_sha256: digest(manifestBytes),
    token_supplement_sha256: manifest.token_supplement_sha256, base_resource_sha256: input.original.resource.sha256 };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [flag, root, task, record] = process.argv.slice(2);
  if (flag !== "--verify-supplement" || !root || !task || !record) throw new Error("usage: --verify-supplement UNIT TASK EXECUTION_RECORD");
  console.log(JSON.stringify(await verifyTimingSupplement(root, task, record)));
}
