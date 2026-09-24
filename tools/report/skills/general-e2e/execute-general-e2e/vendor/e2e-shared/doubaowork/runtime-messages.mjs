import { createHash, randomUUID } from "node:crypto";
import { validateSessionId, summarizePromptReadback, sha256Text } from "./lib.mjs";
import { isAbsolute, normalize } from "node:path";

const sha = text => createHash("sha256").update(text).digest("hex");
const privateFields = new Set(["fetch_token", "sec_sender", "sender", "inner_user_ip", "inner_did", "local_device_id"]);
const requestUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u;
function requestIdentity(user, assistant) {
  const inputKey = user.ext?.reply_unique_key, replyKey = assistant?.ext?.reply_unique_key;
  const live = assistant?.session_id;
  if ((inputKey && replyKey && inputKey !== replyKey)
      || (live && (inputKey && live !== inputKey || replyKey && live !== replyKey))) {
    throw new Error("DOUBAOWORK_RUNTIME_REQUEST_ID_MISMATCH");
  }
  // Native resume code maps ext.reply_unique_key to sessionId. Require both
  // messages to agree before accepting a persisted reply under that identity.
  if (live) return live;
  return requestUuid.test(inputKey || "") && (!assistant || replyKey === inputKey) ? inputKey : null;
}
function nativeInteger(value) {
  const number = typeof value === "number" ? value
    : typeof value === "string" && /^(0|[1-9][0-9]*)$/u.test(value) ? Number(value) : NaN;
  return Number.isSafeInteger(number) && number >= 0 ? number : null;
}
export function redactRuntimeMessages(value) {
  if (Array.isArray(value)) return value.map(redactRuntimeMessages);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k,
    privateFields.has(k) ? "[REDACTED_SECRET]" : redactRuntimeMessages(v)]));
  return value;
}

// Acknowledged user input can bind a running turn before the assistant has a
// complete runtime record. It never establishes native cwd or a terminal state.
export function normalizeRuntimePrompt(snapshot, state) {
  const id = validateSessionId(snapshot?.conversation_id);
  if (snapshot.schema !== "wildclawbench.doubaowork-runtime-messages/v1"
      || snapshot.source !== "native-im.useMessageStore.getState"
      || snapshot.payload_sha256 !== sha(JSON.stringify({ conversation_id: id, maps: snapshot.maps }))) throw new Error("DOUBAOWORK_RUNTIME_INTEGRITY_INVALID");
  if (state.session.conversation_id && state.session.conversation_id !== id) throw new Error("DOUBAOWORK_RUNTIME_SESSION_MISMATCH");
  const messages = Object.values(snapshot.maps.messageMap || {}), users = messages.filter(m => m.user_type === 1);
  if (users.length !== 1 || messages.some(m => m.conversation_id !== id || ![1, 2].includes(m.user_type))
      || messages.filter(m => m.user_type === 2).length > 1) throw new Error("DOUBAOWORK_RUNTIME_TURN_AMBIGUOUS");
  const user = users[0];
  if (user.status !== 1 || user.final_status?.message !== "Success" || !user.message_id) throw new Error("DOUBAOWORK_NATIVE_PROMPT_UNACKNOWLEDGED");
  const texts = (user.content_blocks_v2 || []).filter(b => b.block_type === 10000);
  if (texts.length !== 1 || typeof texts[0].content?.text_block?.text !== "string") throw new Error("DOUBAOWORK_NATIVE_PROMPT_UNAVAILABLE");
  const prompt = summarizePromptReadback(texts[0].content.text_block.text);
  if (prompt.sha256 !== state.prompt.readback_sha256 || prompt.bytes !== state.prompt.readback_bytes) throw new Error("DOUBAOWORK_NATIVE_PROMPT_MISMATCH");
  let config, project;
  try { config = JSON.parse(user.ext.general_task_param); project = JSON.parse(user.ext.conversation_init_option).project_id; }
  catch { throw new Error("DOUBAOWORK_NATIVE_INPUT_CONFIG_UNAVAILABLE"); }
  if (!project || sha256Text(project) !== state.client.project_id_sha256) throw new Error("DOUBAOWORK_NATIVE_PROJECT_MISMATCH");
  for (const path of [config.client_option?.workspace, config.agent_task_param?.workspace]) {
    if (!isAbsolute(path || "") || normalize(path) !== state.workspace) throw new Error("DOUBAOWORK_NATIVE_WORKSPACE_MISMATCH");
  }
  if (config.runtime_type !== 2 || config.agent_task_param?.runtime_type !== 2) throw new Error("DOUBAOWORK_NATIVE_RUNTIME_NOT_LOCAL");
  const assistant = messages.find(m => m.user_type === 2);
  const requestId = !assistant || assistant.reply_id === user.message_id ? requestIdentity(user, assistant) : null;
  if (state.session.native_request_session_id && state.session.native_request_session_id !== requestId) throw new Error("DOUBAOWORK_RUNTIME_REQUEST_ID_MISMATCH");
  return { conversation_id: id, user_message_id: user.message_id, native_request_session_id: requestId, prompt, native_cwd: null, terminal: "unverified",
    binding_status: "acknowledged-user-input", final_text: null, finished_at: null, agent_duration_seconds: null };
}

export function normalizeRuntimeMessages(snapshot, state) {
  const id = validateSessionId(snapshot?.conversation_id);
  if (snapshot.schema !== "wildclawbench.doubaowork-runtime-messages/v1"
      || snapshot.source !== "native-im.useMessageStore.getState"
      || snapshot.payload_sha256 !== sha(JSON.stringify({ conversation_id: id, maps: snapshot.maps }))) {
    throw new Error("DOUBAOWORK_RUNTIME_INTEGRITY_INVALID");
  }
  if (state.session.conversation_id && state.session.conversation_id !== id) throw new Error("DOUBAOWORK_RUNTIME_SESSION_MISMATCH");
  const messages = Object.values(snapshot.maps.messageMap || {});
  const list = snapshot.maps.messageListStatusMap;
  if (!list || list.hasMore !== false || list.inIniting !== false || list.inLoadingMore !== false
      || Object.keys(snapshot.maps.localMessageMap || {}).length) throw new Error("DOUBAOWORK_RUNTIME_MESSAGE_RANGE_INCOMPLETE");
  if (!messages.length || messages.some(m => m.conversation_id !== id)) throw new Error("DOUBAOWORK_RUNTIME_MESSAGE_SCOPE_INVALID");
  const users = messages.filter(m => m.user_type === 1), assistants = messages.filter(m => m.user_type === 2);
  if (users.length !== 1 || assistants.length !== 1 || messages.length !== 2) throw new Error("DOUBAOWORK_RUNTIME_TURN_AMBIGUOUS");
  const user = users[0], assistant = assistants[0];
  const requestId = requestIdentity(user, assistant);
  if (!assistant.message_id || !requestId || !assistant.reply_id) throw new Error("DOUBAOWORK_RUNTIME_REPLY_INCOMPLETE");
  if (assistant.reply_id !== user.message_id) throw new Error("DOUBAOWORK_RUNTIME_REPLY_BINDING_INVALID");
  if (state.session.native_request_session_id && state.session.native_request_session_id !== requestId) throw new Error("DOUBAOWORK_RUNTIME_REQUEST_ID_MISMATCH");
  const promptBlocks = (user.content_blocks_v2 || []).filter(b => b.block_type === 10000);
  if (promptBlocks.length !== 1 || typeof promptBlocks[0].content?.text_block?.text !== "string") throw new Error("DOUBAOWORK_NATIVE_PROMPT_UNAVAILABLE");
  const prompt = summarizePromptReadback(promptBlocks[0].content.text_block.text);
  if (prompt.sha256 !== state.prompt.readback_sha256 || prompt.bytes !== state.prompt.readback_bytes) throw new Error("DOUBAOWORK_NATIVE_PROMPT_MISMATCH");
  const configs = [user, assistant].map(m => {
    try { return JSON.parse(m.ext.general_task_param); } catch { throw new Error("DOUBAOWORK_NATIVE_WORKSPACE_UNAVAILABLE"); }
  });
  for (const c of configs) {
    for (const path of [c.client_option?.workspace, c.agent_task_param?.workspace]) {
      if (!isAbsolute(path || "") || normalize(path) !== state.workspace) throw new Error("DOUBAOWORK_NATIVE_WORKSPACE_MISMATCH");
    }
    if (c.runtime_type !== 2 || c.agent_task_param?.runtime_type !== 2) throw new Error("DOUBAOWORK_NATIVE_RUNTIME_NOT_LOCAL");
  }
  let project;
  try { project = JSON.parse(user.ext.conversation_init_option).project_id; } catch { /* fail below */ }
  if (!project || sha256Text(project) !== state.client.project_id_sha256) throw new Error("DOUBAOWORK_NATIVE_PROJECT_MISMATCH");
  const blocks = assistant.content_blocks_v2 || [];
  const persisted = !assistant.session_id && assistant.stage === undefined && assistant.local_info?.from === "Api";
  const terminalProfile = persisted ? "native-im-api-history/v1" : "native-im-live/v1";
  const completed = assistant.final_status?.session === "Success" && assistant.status === 1
    && (persisted ? assistant.final_status.message === "Success" && assistant.ext?.finish_reason_chat === "succeed:completion" : assistant.stage === 4)
    && assistant.ext?.is_finish === "1"
    && blocks.length > 0 && blocks.every(b => b.is_finish === true);
  const texts = blocks.filter(b => b.block_type === 10000 && typeof b.content?.text_block?.text === "string");
  const finalText = completed ? texts.at(-1)?.content.text_block.text ?? null : null;
  const finishEvents = (assistant.local_info?.perf_mark_samples || []).filter(p => p.answerId === assistant.message_id
    && p.queryMessageId === user.message_id && p.taskId === requestId
    && p.marks?.some(m => m.evName === "task_finish"));
  const finished = persisted ? completed ? nativeInteger(assistant.ext?.finish_time_ms) : null
    : completed && finishEvents.length === 1 && Number.isFinite(finishEvents[0].receiveTimestamp)
      ? finishEvents[0].receiveTimestamp : null;
  const requestCreated = nativeInteger(user.create_time);
  const started = persisted ? requestCreated === null ? null : requestCreated * 1000 : assistant.local_info?.query_send_timestamp;
  if (finished !== null && (!Number.isFinite(started) || finished < started)) throw new Error("DOUBAOWORK_NATIVE_TIMING_INVALID");
  const elapsed = blocks.filter(b => b.block_type === 10091).map(b => b.content?.elapsed_block).filter(Boolean);
  const agentStart = elapsed.length === 1 ? nativeInteger(elapsed[0].start_time_s) : null;
  const agentEnd = elapsed.length === 1 ? nativeInteger(elapsed[0].end_time_s) : null;
  const agentDuration = completed && agentStart > 0 && agentEnd !== null && agentEnd >= agentStart ? agentEnd - agentStart : null;
  if (persisted && finished !== null && agentDuration !== null && finished < agentEnd * 1000) throw new Error("DOUBAOWORK_NATIVE_TIMING_INVALID");
  return {
    conversation_id: id, user_message_id: user.message_id, reply_message_id: assistant.message_id,
    native_request_session_id: requestId, native_cwd: state.workspace, project_id: project,
    prompt, terminal: completed && finalText ? "completed" : "unverified",
    raw_terminal: { profile: terminalProfile, final_status: assistant.final_status, status: assistant.status, stage: assistant.stage ?? null,
      is_finish: assistant.ext?.is_finish, finish_reason_chat: assistant.ext?.finish_reason_chat ?? null },
    final_text: finalText, finished_at: finished === null ? null : new Date(finished).toISOString(),
    started_at: Number.isFinite(started) ? new Date(started).toISOString() : null,
    agent_duration_seconds: agentDuration,
    agent_started_at: agentDuration === null ? null : new Date(agentStart * 1000).toISOString(),
    agent_finished_at: agentDuration === null ? null : new Date(agentEnd * 1000).toISOString(),
    sources: { prompt: "user.content_blocks_v2.text_block.text", cwd: "user+assistant.ext.general_task_param.client_option.workspace+agent_task_param.workspace",
      request_identity: persisted ? "user+assistant.ext.reply_unique_key" : "assistant.session_id",
      terminal: persisted ? "assistant.final_status.message+session+status+ext.is_finish+finish_reason_chat+content_blocks_v2.is_finish"
        : "assistant.final_status.session+status+stage+ext.is_finish+content_blocks_v2.is_finish",
      finished_at: persisted ? "assistant.ext.finish_time_ms (native server completion)" : "assistant.local_info.perf_mark_samples.task_finish.receiveTimestamp" },
  };
}

// Read the existing IM store through the native service's closure. Do not load
// modules, register webpack chunks, invoke send/stop methods or mutate stores.
// Unsupported runtime shapes stop here instead of guessing a terminal state.
export async function readRuntimeMessages(page, conversationId) {
  validateSessionId(conversationId);
  const cdp = await page.context().newCDPSession(page);
  const group = `wcb-doubao-read-${randomUUID()}`;
  try {
    const fn = await cdp.send("Runtime.evaluate", {
      expression: "window.__messageTaskAssociationService__?.resolveReplyMessageConversationId",
      objectGroup: group,
    });
    if (fn.result?.type !== "function" || !fn.result.objectId) throw new Error("DOUBAOWORK_RUNTIME_SERVICE_UNAVAILABLE");
    const props = await cdp.send("Runtime.getProperties", { objectId: fn.result.objectId });
    const scope = props.internalProperties?.find(p => p.name === "[[Scopes]]");
    if (!scope?.value?.objectId) throw new Error("DOUBAOWORK_RUNTIME_SCOPES_UNAVAILABLE");
    const scopes = await cdp.send("Runtime.getProperties", { objectId: scope.value.objectId });
    const candidates = new Set();
    for (const entry of scopes.result.filter(p => p.value?.description?.startsWith("Closure"))) {
      const variables = await cdp.send("Runtime.getProperties", { objectId: entry.value.objectId });
      if (variables.result.length > 256) throw new Error("DOUBAOWORK_RUNTIME_SCOPE_LIMIT");
      for (const variable of variables.result) {
        if (variable.value?.type !== "object" || !variable.value.objectId) continue;
        const properties = await cdp.send("Runtime.getProperties", { objectId: variable.value.objectId, ownProperties: true });
        const names = properties.result.map(p => p.name);
        if (names.includes("useMessageStore") && names.includes("initMessageStore") && names.includes("createStore")) {
          candidates.add(variable.value.objectId);
        }
      }
    }
    if (candidates.size !== 1) throw new Error(`DOUBAOWORK_RUNTIME_STORE_AMBIGUOUS: ${candidates.size}`);
    const [objectId] = candidates;
    const result = await cdp.send("Runtime.callFunctionOn", {
      objectId, objectGroup: group, returnByValue: true,
      arguments: [{ value: conversationId }],
      functionDeclaration: `function (id) {
        const state = this.useMessageStore.getState();
        const maps = {};
        for (const name of ["messageMap", "localMessageMap", "messageLinkMap", "messageListStatusMap", "lastMessageMap"]) {
          maps[name] = state[name]?.[id] ?? null;
        }
        return { conversation_id: id, maps };
      }`,
    });
    if (result.exceptionDetails || !result.result?.value) throw new Error("DOUBAOWORK_RUNTIME_READ_FAILED");
    const snapshot = redactRuntimeMessages(result.result.value);
    const serialized = JSON.stringify(snapshot);
    if (Buffer.byteLength(serialized) > 16 * 1024 * 1024) throw new Error("DOUBAOWORK_RUNTIME_MESSAGES_TOO_LARGE");
    return {
      schema: "wildclawbench.doubaowork-runtime-messages/v1",
      observed_at: new Date().toISOString(), source: "native-im.useMessageStore.getState",
      reader: "cdp-existing-closure/v1", mutation_performed: false,
      redaction: { policy: "message-private-fields/v1", fields: [...privateFields] },
      payload_sha256: createHash("sha256").update(serialized).digest("hex"),
      ...snapshot,
    };
  } finally {
    await cdp.send("Runtime.releaseObjectGroup", { objectGroup: group }).catch(() => {});
    await cdp.detach();
  }
}
