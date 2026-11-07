// Child SDK transcripts retain their own session and event identities. They
// are evidence sidecars, never synthetic events in the primary transcript.
import { createHash } from "node:crypto";
import { lstat, readdir } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import { safeRead, equal, artifact } from "./index.mjs";

export const CHILD_SDK_SCHEMA = "wildclawbench.workbuddy-linked-child-sdk/v1";
export const CHILD_SDK_PROOF = "bindings/workbuddy-linked-child-sdk.json";
export const CHILD_TIME_PROFILE = "native-tool-execution-start/v1";
const LEGACY_TIME_PROFILE = "sdk-record-timestamp/v1";
const PREFIX = "raw/workbuddy-subagents/";
const hash = value => createHash("sha256").update(value).digest("hex");
const fail = code => { throw new Error(`WORKBUDDY_CHILD_SDK_${code}`); };
const text = value => typeof value === "string" ? value : Array.isArray(value)
  ? value.filter(x => ["text", "input_text", "output_text"].includes(x.type)).map(x => x.text || "").join("") : "";
const terminal = new Set(["completed", "failed", "error", "cancelled", "canceled", "interrupted"]);
const sessionKey = value => Object.fromEntries(["thread_id", "turn_id", "session_id", "cwd"]
  .map(key => [key, key === "thread_id" ? value[key] ?? null : value[key]]));
function rows(bytes) {
  let body;
  try { body = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
  catch { fail("INVALID_UTF8"); }
  if (!body.endsWith("\n")) fail("INCOMPLETE_LINE");
  try { return body.split(/\r?\n/u).filter(x => x.trim()).map(JSON.parse); }
  catch { fail("INVALID_JSONL"); }
}
function baggage(row) {
  const values = new Map();
  for (const part of String(row._meta?.baggage || "").split(",")) {
    const at = part.indexOf("=");
    if (at < 0) fail("BAGGAGE_MISSING");
    const key = part.slice(0, at).trim();
    if (values.has(key)) fail("BAGGAGE_DUPLICATE");
    try { values.set(key, decodeURIComponent(part.slice(at + 1).trim())); }
    catch { fail("BAGGAGE_INVALID"); }
  }
  return values;
}
function uniqueRecords(input) {
  const byId = new Map();
  for (const row of input) {
    if (typeof row.id !== "string" || !row.id) fail("EVENT_ID_MISSING");
    if (byId.has(row.id) && !equal(byId.get(row.id), row)) fail("EVENT_ID_CONFLICT");
    byId.set(row.id, row);
  }
  return [...byId.values()];
}
function argumentsOf(row) {
  try {
    const value = typeof row.arguments === "string" ? JSON.parse(row.arguments) : row.arguments;
    if (!value || typeof value !== "object" || Array.isArray(value)) fail("PARENT_ARGUMENTS_INVALID");
    return value;
  } catch { fail("PARENT_ARGUMENTS_INVALID"); }
}

export function bindChildSdk(primaryBytes, snapshot, session, childSources, { timeProfile = CHILD_TIME_PROFILE } = {}) {
  if (![CHILD_TIME_PROFILE, LEGACY_TIME_PROFILE].includes(timeProfile)) fail("TIME_PROFILE_UNSUPPORTED");
  if (snapshot?.conversation?.id !== session.session_id || snapshot?.request?.id !== session.turn_id
      || snapshot.conversation.space?.cwd !== session.cwd || snapshot.request.state !== "completed"
      || snapshot.conversation.state !== "idle" || snapshot.request.assistantMessage?.state !== "completed"
      || snapshot.conversation.hasActiveChildAgents === true) fail("PRIMARY_NOT_COMPLETE");
  const primary = uniqueRecords(rows(primaryBytes).filter(x => x.name === "Agent"
    && ["function_call", "function_call_result"].includes(x.type)));
  const tools = (snapshot.request.assistantMessage?.content || []).filter(x => x.title === "Agent"
    && (x.type === "tool" || x.sessionUpdate === "tool_call_update"));
  const identities = new Set(), sourceNames = new Set(), bindings = [];
  for (const source of childSources) {
    if (!/^agent-[A-Za-z0-9_-]{1,160}\.jsonl$/u.test(source.name || "") || sourceNames.has(source.name)) fail("SOURCE_NAME_INVALID");
    sourceNames.add(source.name);
    const original = rows(source.bytes), child = uniqueRecords(original), first = child[0];
    const sid = first?.sessionId, requestId = first?.providerData?.conversationRequestId;
    if (first?.type !== "message" || first.role !== "user" || !text(first.content)
        || first.providerData?.rootRequestId !== session.turn_id
        || typeof sid !== "string" || !sid || sid === session.session_id
        || typeof requestId !== "string" || !requestId || requestId === session.turn_id) fail("HEADER_BINDING_INVALID");
    if (identities.has(sid)) fail("CHILD_SESSION_DUPLICATE");
    identities.add(sid);
    const matching = [];
    for (const tool of tools) {
      const calls = primary.filter(x => x.type === "function_call" && x.callId === tool.toolCallId);
      if (calls.length !== 1) continue;
      let args;
      try { args = argumentsOf(calls[0]); } catch { continue; }
      if (args.prompt === text(first.content) && args.subagent_type === first.providerData.agent) matching.push({ tool, args, call: calls[0] });
    }
    if (matching.length !== 1) fail("PARENT_CALL_AMBIGUOUS_OR_MISSING");
    const { tool, args } = matching[0];
    const calls = primary.filter(x => x.type === "function_call" && x.name === "Agent" && x.callId === tool.toolCallId);
    const returns = primary.filter(x => x.type === "function_call_result" && x.callId === tool.toolCallId);
    if (tool.status !== "completed" || calls.length !== 1 || returns.length !== 1
        || returns[0].name !== "Agent" || !terminal.has(returns[0].status)) fail("PARENT_CALL_NOT_CLOSED");
    const raw = tool.rawInput, meta = tool._meta || {};
    const fullArguments = raw?.prompt === args.prompt && raw?.subagent_type === args.subagent_type;
    const emptyDescription = raw?.description && typeof raw.description === "object"
      && !Array.isArray(raw.description) && Object.keys(raw.description).length === 0;
    const descriptionOnly = raw && Object.keys(raw).length === 1
      && (raw.description === args.description || emptyDescription)
      && typeof args.description === "string" && Boolean(args.description)
      && meta["codebuddy.ai/description"] === args.description && meta["codebuddy.ai/toolName"] === "Agent"
      && meta["codebuddy.ai/isSubagent"] === true && meta["codebuddy.ai/subagentType"] === args.subagent_type
      && meta["codebuddy.ai/requestId"] === session.turn_id
      && meta["codebuddy.ai/conversationRequestId"] === session.turn_id
      && typeof calls[0].providerData?.messageId === "string"
      && calls[0].providerData.messageId === meta["codebuddy.ai/llmMessageId"]
      && calls[0].providerData.messageId === meta["codebuddy.ai/modelRequestId"];
    if (!fullArguments && !descriptionOnly) fail("PARENT_ARGUMENTS_MISMATCH");
    const sdkStart = calls[0].timestamp, end = snapshot.request.completedAt ?? snapshot.request.finishTimestamp;
    let start = sdkStart, timeSource = "sdk.function_call.timestamp";
    const nativeStart = meta["codebuddy.ai/toolExecutionStartedAt"];
    if (timeProfile === CHILD_TIME_PROFILE && nativeStart != null) {
      const primaryStart = snapshot.request.startedAt ?? snapshot.request.timestamp;
      if (!Number.isFinite(nativeStart) || !Number.isFinite(primaryStart)
          || nativeStart < primaryStart || nativeStart > end
          || meta["codebuddy.ai/toolExecutionStarted"] !== true
          || meta["codebuddy.ai/toolName"] !== "Agent"
          || meta["codebuddy.ai/requestId"] !== session.turn_id
          || meta["codebuddy.ai/conversationRequestId"] !== session.turn_id
          || typeof calls[0].providerData?.messageId !== "string"
          || calls[0].providerData.messageId !== meta["codebuddy.ai/modelRequestId"]
          || calls[0].providerData.messageId !== meta["codebuddy.ai/llmMessageId"]
          || !Number.isFinite(returns[0].timestamp) || nativeStart > returns[0].timestamp) fail("NATIVE_START_UNBOUND");
      start = nativeStart; timeSource = "runtime.toolExecutionStartedAt";
    }
    if (!Number.isFinite(sdkStart) || !Number.isFinite(start) || !Number.isFinite(end)
        || start > end || sdkStart > end) fail("PARENT_TIME_INVALID");
    const callMap = new Map(), resultIds = new Set(), responseIds = new Set(), incompleteResults = new Set();
    const users = [];
    for (const row of child) {
      if (!["message", "function_call", "function_call_result", "model-usage"].includes(row.type)) fail("EVENT_TYPE_UNSUPPORTED");
      const bound = baggage(row);
      if (row.cwd !== session.cwd || row.sessionId !== sid
          || bound.get("codebuddy.session_id") !== session.session_id
          || bound.get("codebuddy.conversation_request_id") !== session.turn_id
          || row.providerData?.conversationRequestId !== requestId
          || (row.providerData.rootRequestId != null && row.providerData.rootRequestId !== session.turn_id)
          || (row.providerData.agent != null && row.providerData.agent !== first.providerData.agent)) fail("EVENT_BINDING_MISMATCH");
      if (!Number.isFinite(row.timestamp) || row.timestamp < start || row.timestamp > end) fail("EVENT_TIME_OUTSIDE_PARENT");
      if (row.type === "message" && row.role === "user" && !row.providerData.isMeta) {
        if (row.providerData.isCompactInternal === true) {
          if (row.providerData.skipRun !== false || row.providerData.startsNewUserRequest === true) fail("INTERNAL_USER_UNBOUND");
        } else users.push(row);
      }
      if (row.providerData.messageId) responseIds.add(row.providerData.messageId);
      if (row.type === "function_call") {
        if (typeof row.callId !== "string" || !row.callId || callMap.has(row.callId) || !row.name) fail("CALL_ID_INVALID");
        callMap.set(row.callId, row);
      }
      if (row.type === "function_call_result") {
        const call = callMap.get(row.callId);
        if (!call || resultIds.has(row.callId) || call.name !== row.name
            || (!terminal.has(row.status) && row.status !== "incomplete")) fail("RESULT_BINDING_MISMATCH");
        resultIds.add(row.callId);
        if (row.status === "incomplete") incompleteResults.add(row.callId);
      }
    }
    if (users.length !== 1 || users[0] !== first) fail("EXTRA_USER_TURN");
    const missing = [...callMap.keys()].filter(id => !resultIds.has(id));
    const last = child.filter(x => x.type !== "model-usage").at(-1);
    const finalPresent = last?.type === "message" && last.role === "assistant"
      && last.status === "completed" && Boolean(text(last.content));
    const attachmentNames = new Set(), attachments = [];
    const attachmentPrefix = source.name.slice(0, -6) + "/tool-results/";
    for (const attachment of source.attachments || []) {
      if (!attachment.name.startsWith(attachmentPrefix) || attachmentNames.has(attachment.name)) fail("AUXILIARY_PATH_INVALID");
      const file = attachment.name.slice(attachmentPrefix.length);
      if (!/^call_[A-Za-z0-9_-]+(?:-render)?\.txt$/u.test(file)) fail("AUXILIARY_PATH_INVALID");
      const callId = file.endsWith("-render.txt") ? file.slice(0, -11) : file.slice(0, -4);
      if (!callMap.has(callId)) fail("AUXILIARY_CALL_UNBOUND");
      attachmentNames.add(attachment.name);
      attachments.push({ call_id: callId, raw: artifact(PREFIX + attachment.name, attachment.bytes),
        binding_basis: "native child tool-results directory and exact SDK call ID; no inferred content equivalence" });
    }
    bindings.push({ parent_tool_call_id: tool.toolCallId, agent_type: first.providerData.agent,
      session_id: sid, conversation_request_id: requestId, prompt_sha256: hash(text(first.content)),
      argument_binding: fullArguments ? "runtime-and-sdk-full-prompt" : emptyDescription
        ? "runtime-empty-description-sdk-full-arguments/v1" : "runtime-description-only-sdk-full-arguments/v1",
      ...(timeProfile === CHILD_TIME_PROFILE ? { parent_time_binding: {
        profile: timeProfile, source: timeSource, sdk_call_recorded_at: sdkStart,
        native_execution_started_at: nativeStart ?? null, effective_lower_bound: start,
        primary_completed_at: end,
      } } : {}),
      raw: artifact(PREFIX + source.name, source.bytes), source_line_count: original.length,
      unique_event_count: child.length, observed_tool_call_count: callMap.size,
      observed_model_response_count: responseIds.size,
      first_timestamp: first.timestamp, last_timestamp: Math.max(...child.map(x => x.timestamp)),
      transcript_status: !missing.length && !incompleteResults.size && finalPresent ? "complete" : "partial",
      missing_result_call_ids: missing, final_assistant_present: finalPresent,
      incomplete_result_call_ids: [...incompleteResults],
      auxiliary_tool_results: attachments.sort((a, b) => a.raw.path.localeCompare(b.raw.path)),
      // No usage admission is implied by the archival or the counts above.
      token_usage_scope: "not-included-in-primary-resource-metrics" });
  }
  if (new Set(bindings.map(x => x.parent_tool_call_id)).size !== bindings.length) fail("PARENT_CALL_DUPLICATE");
  return bindings.sort((a, b) => a.raw.path.localeCompare(b.raw.path));
}

export async function discoverChildSdk(primaryNative, snapshot, session) {
  const root = dirname(primaryNative.path), dir = join(root, session.session_id, "subagents");
  for (const path of [join(root, session.session_id), dir]) {
    const st = await lstat(path).catch(e => { if (e.code === "ENOENT") return null; throw e; });
    if (!st) return [];
    if (!st.isDirectory() || st.isSymbolicLink()) fail("UNSAFE_DIRECTORY");
  }
  const entries = await readdir(dir, { withFileTypes: true });
  if (entries.some(x => x.isSymbolicLink())) fail("UNSAFE_DIRECTORY");
  const names = entries.filter(x => x.name.endsWith(".jsonl")).map(x => x.name).sort();
  if (names.length > 1024) fail("SOURCE_LIMIT");
  if (entries.some(x => x.isDirectory() && !names.includes(x.name + ".jsonl"))) fail("UNADMITTED_DESCENDANT");
  const sources = [];
  let totalBytes = 0;
  const boundedRead = async path => {
    const bytes = await safeRead(root, path); totalBytes += bytes.length;
    if (totalBytes > 512 * 1024 * 1024) fail("SOURCE_BYTES_LIMIT");
    return bytes;
  };
  for (const name of names) {
    const attachments = [], childDir = join(dir, name.slice(0, -6));
    const st = await lstat(childDir).catch(e => { if (e.code === "ENOENT") return null; throw e; });
    if (st) {
      if (!st.isDirectory() || st.isSymbolicLink()) fail("UNSAFE_DIRECTORY");
      const auxiliaries = await readdir(childDir, { withFileTypes: true });
      if (auxiliaries.some(x => x.name !== "tool-results" || !x.isDirectory() || x.isSymbolicLink())) fail("UNADMITTED_DESCENDANT");
      if (auxiliaries.length) {
        const toolDir = join(childDir, "tool-results"), files = await readdir(toolDir, { withFileTypes: true });
        if (files.length > 10000 || files.some(x => !x.isFile() || x.isSymbolicLink())) fail("UNSAFE_AUXILIARY");
        for (const file of files.sort((a, b) => a.name.localeCompare(b.name))) attachments.push({
          name: name.slice(0, -6) + "/tool-results/" + file.name,
          bytes: await boundedRead(join(toolDir, file.name)),
        });
      }
    }
    sources.push({ name, bytes: await boundedRead(join(dir, name)), attachments });
  }
  bindChildSdk(primaryNative.bytes, snapshot, session, sources);
  return sources;
}

export function childSdkProof(identity, session, snapshotRef, primaryRef, primaryBytes, snapshot, sources,
  { timeProfile = CHILD_TIME_PROFILE } = {}) {
  return { schema_version: CHILD_SDK_SCHEMA, identity, session: sessionKey(session),
    ...(timeProfile === CHILD_TIME_PROFILE ? { binding_time_profile: timeProfile } : {}),
    runtime_snapshot: snapshotRef, primary_sdk: primaryRef,
    primary_normalized_transcript_unchanged: true,
    metric_scope: "bound-primary-conversation-responses; child usage excluded; whole-execution totals unknown",
    children: bindChildSdk(primaryBytes, snapshot, session, sources, { timeProfile }) };
}

export async function verifyChildSdkArchive(traceRoot, index, identity, session) {
  const ref = index.binding_evidence?.find(x => x.path === CHILD_SDK_PROOF);
  const allChildren = (index.raw_trace || []).filter(x => x.path.startsWith(PREFIX));
  const children = allChildren.filter(x => x.path.endsWith(".jsonl"));
  if (!ref) { if (allChildren.length) fail("PROOF_MISSING"); return null; }
  const read = async reference => {
    const bytes = await safeRead(traceRoot, join(traceRoot, reference.path));
    if (!equal(artifact(reference.path, bytes), reference)) fail("ARCHIVE_DIGEST_MISMATCH");
    return bytes;
  };
  const proof = JSON.parse(await read(ref));
  if (proof.schema_version !== CHILD_SDK_SCHEMA || !equal(proof.identity, identity)
      || !equal(proof.session, sessionKey(session)) || !Array.isArray(proof.children)) fail("PROOF_IDENTITY_MISMATCH");
  const rawRefs = index.raw_trace || [];
  if (!rawRefs.some(x => equal(x, proof.runtime_snapshot)) || !rawRefs.some(x => equal(x, proof.primary_sdk))) fail("SOURCE_INDEX_MISMATCH");
  const runtime = JSON.parse(await read(proof.runtime_snapshot));
  if (runtime.source_kind !== "workbuddy-runtime-api" || !equal(runtime.identity, identity)
      || runtime.conversation_id !== session.session_id || runtime.request_id !== session.turn_id
      || runtime.workspace !== session.cwd) fail("RUNTIME_SOURCE_BINDING_MISMATCH");
  const primary = await read(proof.primary_sdk), sources = [];
  const declared = proof.children.flatMap(x => [x.raw, ...(x.auxiliary_tool_results || []).map(y => y.raw)]);
  if (allChildren.length !== declared.length || !allChildren.every(x => declared.some(y => equal(y, x)))
      || children.length !== proof.children.length) fail("CHILD_INDEX_MISMATCH");
  for (const child of children) {
    const prefix = child.path.slice(0, -6) + "/tool-results/";
    const attachments = [];
    for (const file of allChildren.filter(x => x.path.startsWith(prefix))) attachments.push({
      name: file.path.slice(PREFIX.length), bytes: await read(file),
    });
    sources.push({ name: basename(child.path), bytes: await read(child), attachments });
  }
  const expected = childSdkProof(identity, session, proof.runtime_snapshot, proof.primary_sdk, primary, runtime.runtime_snapshot, sources,
    { timeProfile: proof.binding_time_profile ?? LEGACY_TIME_PROFILE });
  if (!equal(proof, expected)) fail("PROOF_REPLAY_MISMATCH");
  return proof;
}
