import { randomUUID } from "node:crypto";
import { lstat, mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, normalize } from "node:path";

import {
  DEFAULT_APP_PATH,
  DEFAULT_ENDPOINT,
  DRIVER_VERSION,
  sha256Text,
  validateSessionId,
  workspaceReadbackMatches,
} from "./lib.mjs";

export const AUTOMATION_SCHEMA = "wildclawbench.web-e2e-automation-state/v1";
export const DRIVER_ID = "doubaowork";
export const TERMINAL_PHASES = new Set(["SUCCEEDED", "INFRA_FAILED", "TIMEOUT"]);
export const PRE_SEND_PHASES = new Set([
  "PREPARED",
  "CLIENT_READY",
  "WORKSPACE_CONFIRMED",
  "PERMISSION_CONFIRMED",
  "MODEL_CONFIRMED",
]);
const KNOWN_PHASES = new Set([
  ...PRE_SEND_PHASES,
  "READY_TO_SEND",
  "PROMPT_SENT",
  "RUNNING",
  "NEEDS_ATTENTION",
  ...TERMINAL_PHASES,
]);
const ACCEPTED_SEND_PHASES = new Set(["PROMPT_SENT", "RUNNING", "SUCCEEDED", "TIMEOUT"]);

const ALLOWED_PHASE_TRANSITIONS = new Map([
  ["PREPARED", new Set(["CLIENT_READY", "INFRA_FAILED"])],
  ["CLIENT_READY", new Set(["WORKSPACE_CONFIRMED", "INFRA_FAILED"])],
  ["WORKSPACE_CONFIRMED", new Set(["PERMISSION_CONFIRMED", "INFRA_FAILED"])],
  ["PERMISSION_CONFIRMED", new Set(["MODEL_CONFIRMED", "INFRA_FAILED"])],
  ["MODEL_CONFIRMED", new Set(["READY_TO_SEND", "INFRA_FAILED"])],
  ["READY_TO_SEND", new Set(["PROMPT_SENT", "NEEDS_ATTENTION"])],
  ["PROMPT_SENT", new Set(["RUNNING", "NEEDS_ATTENTION"])],
  ["RUNNING", new Set(["NEEDS_ATTENTION"])],
  ["NEEDS_ATTENTION", new Set(["PROMPT_SENT", "RUNNING", "NEEDS_ATTENTION"])],
]);

function isoNow(now = new Date()) {
  const value = now instanceof Date ? now : new Date(now);
  if (Number.isNaN(value.getTime())) throw new Error("无效状态时间");
  return value.toISOString();
}

function requireNonEmpty(value, name) {
  const normalized = String(value ?? "").trim();
  if (!normalized) throw new Error(`${name} 不能为空`);
  return normalized;
}

function requireTimestamp(value, name) {
  const normalized = requireNonEmpty(value, name);
  if (isoNow(normalized) !== normalized) throw new Error(`${name} 必须是规范 ISO 时间`);
  return normalized;
}

function validateIdList(values, name) {
  if (!Array.isArray(values)) throw new Error(`${name} 必须是数组`);
  return [...new Set(values.map(validateSessionId))].sort();
}

export function createAttemptState({
  attemptId = randomUUID(),
  batchId,
  taskId,
  workspace,
  promptFile,
  prompt,
  requestedModel = null,
  requestedPermissionMode = "current",
  appPath = DEFAULT_APP_PATH,
  endpoint = DEFAULT_ENDPOINT,
  baselineConversationIds = [],
  baselineSessionDirectoryIds = [],
  now = new Date(),
}) {
  if (!isAbsolute(workspace)) throw new Error("workspace 必须是绝对路径");
  if (!isAbsolute(promptFile)) throw new Error("promptFile 必须是绝对路径");
  const baselineConversations = validateIdList(baselineConversationIds, "baselineConversationIds");
  const baselineDirectories = validateIdList(
    baselineSessionDirectoryIds,
    "baselineSessionDirectoryIds",
  );
  const preparedAt = isoNow(now);
  const promptValue = String(prompt);
  const state = {
    schema_version: AUTOMATION_SCHEMA,
    driver: {
      id: DRIVER_ID,
      version: DRIVER_VERSION,
      control_backend: "cdp+macos-accessibility",
      platform: "darwin",
    },
    attempt_id: requireNonEmpty(attemptId, "attemptId"),
    phase: "PREPARED",
    terminal: false,
    identity: {
      batch_id: requireNonEmpty(batchId, "batchId"),
      task_id: requireNonEmpty(taskId, "taskId"),
      harness_id: DRIVER_ID,
    },
    workspace: normalize(workspace),
    prompt: {
      file: normalize(promptFile),
      sha256: sha256Text(promptValue),
      bytes: Buffer.byteLength(promptValue),
      plaintext_persisted: false,
    },
    requested: {
      model: requestedModel ? String(requestedModel) : null,
      permission_mode: requireNonEmpty(requestedPermissionMode, "requestedPermissionMode"),
    },
    actual: { model: null, permission_mode: null },
    client: {
      app_path: appPath,
      endpoint,
      version: null,
      process: null,
    },
    workspace_selection: {
      requested_path: normalize(workspace),
      display_value: null,
      actual_path: null,
      confirmed: false,
      confirmed_at: null,
      source: null,
    },
    session: {
      conversation_id: null,
      session_directory_id: null,
      turn_id: null,
      native_cwd: null,
      binding_status: "unverified",
      binding_evidence: [],
      baseline_conversation_ids: baselineConversations,
      baseline_session_directory_ids: baselineDirectories,
    },
    send: {
      intent_persisted_at: null,
      dispatch_started_at: null,
      click_returned_at: null,
      accepted_at: null,
      dispatch_attempt_count: 0,
    },
    timing: {
      prepared_at: preparedAt,
      sent_at: null,
      finished_at: null,
    },
    runtime: {
      driver_pid: process.pid,
      heartbeat_at: preparedAt,
      interruption: null,
    },
    error: null,
    history: [{ phase: "PREPARED", at: preparedAt }],
  };
  assertAttemptState(state);
  return state;
}

export function assertAttemptState(state) {
  if (state?.schema_version !== AUTOMATION_SCHEMA) throw new Error("不支持的 DoubaoWork automation state schema");
  if (state.driver?.id !== DRIVER_ID) throw new Error("automation state driver 不是 doubaowork");
  requireNonEmpty(state.attempt_id, "attempt_id");
  requireNonEmpty(state.identity?.batch_id, "identity.batch_id");
  requireNonEmpty(state.identity?.task_id, "identity.task_id");
  if (state.identity?.harness_id !== DRIVER_ID) throw new Error("identity.harness_id 必须是 doubaowork");
  if (!KNOWN_PHASES.has(state.phase)) throw new Error(`未知 automation phase: ${state.phase}`);
  if (!isAbsolute(state.workspace)) throw new Error("state.workspace 必须是绝对路径");
  if (!isAbsolute(state.prompt?.file) || !/^[0-9a-f]{64}$/.test(state.prompt?.sha256 ?? "")) {
    throw new Error("prompt 路径或 SHA-256 无效");
  }
  if (state.prompt?.plaintext_persisted !== false) throw new Error("automation state 禁止持久化 Prompt 明文");
  validateIdList(state.session?.baseline_conversation_ids ?? [], "baseline_conversation_ids");
  validateIdList(
    state.session?.baseline_session_directory_ids ?? [],
    "baseline_session_directory_ids",
  );
  if (![0, 1].includes(state.send?.dispatch_attempt_count)) {
    throw new Error("dispatch_attempt_count 只能是 0 或 1");
  }
  if (state.send.intent_persisted_at) {
    requireTimestamp(state.send.intent_persisted_at, "send.intent_persisted_at");
  }
  if (state.send.dispatch_attempt_count === 0
      && (state.send.dispatch_started_at || state.send.click_returned_at
        || state.send.accepted_at || state.timing?.sent_at)) {
    throw new Error("未登记 dispatch attempt 时不能存在发送时间");
  }
  if (state.send.dispatch_attempt_count === 1 && !state.send.dispatch_started_at) {
    throw new Error("dispatch attempt=1 必须有 dispatch_started_at");
  }
  if (state.send.dispatch_started_at) {
    requireTimestamp(state.send.dispatch_started_at, "send.dispatch_started_at");
  }
  if (state.send.click_returned_at) requireTimestamp(state.send.click_returned_at, "send.click_returned_at");
  if (state.send.accepted_at) requireTimestamp(state.send.accepted_at, "send.accepted_at");
  if (state.timing?.sent_at) requireTimestamp(state.timing.sent_at, "timing.sent_at");
  if (PRE_SEND_PHASES.has(state.phase)
      && (state.send.intent_persisted_at || state.send.dispatch_attempt_count !== 0)) {
    throw new Error(`${state.phase} 不能已有发送意图或发送尝试`);
  }
  if (state.phase === "READY_TO_SEND" && !state.send.intent_persisted_at) {
    throw new Error("READY_TO_SEND 必须已持久化发送意图");
  }
  if (ACCEPTED_SEND_PHASES.has(state.phase)
      && (state.send.dispatch_attempt_count !== 1 || !state.send.accepted_at || !state.timing.sent_at)) {
    throw new Error(`${state.phase} 必须已有一次发送尝试、接受确认和 sent_at`);
  }
  if (state.timing?.sent_at && state.timing.sent_at !== state.send.dispatch_started_at) {
    throw new Error("sent_at 必须等于发送临界区开始时间");
  }
  if (state.session?.conversation_id) validateSessionId(state.session.conversation_id);
  if (state.session?.session_directory_id) validateSessionId(state.session.session_directory_id);
  if (state.session?.conversation_id && state.session?.session_directory_id
      && state.session.conversation_id !== state.session.session_directory_id) {
    throw new Error("conversation ID 与 session directory ID 不一致");
  }
  if ((state.session?.conversation_id || state.session?.session_directory_id)
      && state.send.dispatch_attempt_count !== 1) {
    throw new Error("发送后 session 绑定必须已有一次发送尝试");
  }
  if (Boolean(state.terminal) !== TERMINAL_PHASES.has(state.phase)) {
    throw new Error("terminal 与 phase 不一致");
  }
  return state;
}

export function transitionAttempt(state, nextPhase, detail = {}, now = new Date()) {
  assertAttemptState(state);
  const allowed = ALLOWED_PHASE_TRANSITIONS.get(state.phase);
  if (!allowed?.has(nextPhase)) throw new Error(`不允许从 ${state.phase} 转到 ${nextPhase}`);
  const at = isoNow(now);
  const previous = {
    phase: state.phase,
    terminal: state.terminal,
    heartbeat_at: state.runtime.heartbeat_at,
    history_length: state.history.length,
  };
  state.phase = nextPhase;
  state.terminal = TERMINAL_PHASES.has(nextPhase);
  state.runtime.heartbeat_at = at;
  state.history.push({ ...detail, phase: nextPhase, at });
  try {
    assertAttemptState(state);
  } catch (error) {
    state.phase = previous.phase;
    state.terminal = previous.terminal;
    state.runtime.heartbeat_at = previous.heartbeat_at;
    state.history.length = previous.history_length;
    throw error;
  }
  return state;
}

export function confirmWorkspaceReadback(state, displayValue, userHome, now = new Date()) {
  assertAttemptState(state);
  if (state.phase !== "CLIENT_READY") throw new Error("只能在 CLIENT_READY 确认 workspace");
  if (!workspaceReadbackMatches(displayValue, state.workspace, userHome)) {
    throw new Error("DoubaoWork workspace tooltip 与请求绝对路径不一致");
  }
  const at = isoNow(now);
  state.workspace_selection = {
    requested_path: state.workspace,
    display_value: displayValue,
    actual_path: state.workspace,
    confirmed: true,
    confirmed_at: at,
    source: "project-folder-tooltip",
  };
  return transitionAttempt(state, "WORKSPACE_CONFIRMED", { source: "project-folder-tooltip" }, at);
}

export function confirmPermission(state, actualMode, now = new Date()) {
  if (state.phase !== "WORKSPACE_CONFIRMED") throw new Error("只能在 WORKSPACE_CONFIRMED 确认权限");
  const actual = requireNonEmpty(actualMode, "actual permission mode");
  if (state.requested.permission_mode !== "current" && actual !== state.requested.permission_mode) {
    throw new Error("DoubaoWork 实际权限与请求不一致");
  }
  state.actual.permission_mode = actual;
  return transitionAttempt(state, "PERMISSION_CONFIRMED", { actual_permission_mode: actual }, now);
}

export function confirmModel(state, actualModel, now = new Date()) {
  if (state.phase !== "PERMISSION_CONFIRMED") throw new Error("只能在 PERMISSION_CONFIRMED 确认模型");
  const actual = requireNonEmpty(actualModel, "actual model");
  if (state.requested.model && actual !== state.requested.model) {
    throw new Error("DoubaoWork 实际模型与请求不一致");
  }
  state.actual.model = actual;
  return transitionAttempt(state, "MODEL_CONFIRMED", { actual_model: actual }, now);
}

export function recordPreSendBaselines(state, {
  conversationIds = [],
  sessionDirectoryIds = [],
} = {}, now = new Date()) {
  assertAttemptState(state);
  if (state.phase !== "MODEL_CONFIRMED") {
    throw new Error("发送前基线只能在 MODEL_CONFIRMED 后登记");
  }
  const at = isoNow(now);
  state.session.baseline_conversation_ids = validateIdList(
    conversationIds,
    "conversationIds",
  );
  state.session.baseline_session_directory_ids = validateIdList(
    sessionDirectoryIds,
    "sessionDirectoryIds",
  );
  state.runtime.heartbeat_at = at;
  state.history.push({
    phase: state.phase,
    event: "PRE_SEND_BASELINES_RECORDED",
    conversation_count: state.session.baseline_conversation_ids.length,
    session_directory_count: state.session.baseline_session_directory_ids.length,
    at,
  });
  assertAttemptState(state);
  return state;
}

export function recordSendIntent(state, now = new Date()) {
  assertAttemptState(state);
  if (state.phase !== "MODEL_CONFIRMED") throw new Error("发送意图只能从 MODEL_CONFIRMED 落盘");
  if (!state.workspace_selection.confirmed || !state.actual.model || !state.actual.permission_mode) {
    throw new Error("workspace、模型和权限必须在发送前完成回读");
  }
  const at = isoNow(now);
  state.send.intent_persisted_at = at;
  state.phase = "READY_TO_SEND";
  state.runtime.heartbeat_at = at;
  state.history.push({ prompt_sha256: state.prompt.sha256, phase: "READY_TO_SEND", at });
  assertAttemptState(state);
  return state;
}

export function recordDispatchStart(state, now = new Date()) {
  assertAttemptState(state);
  if (state.phase !== "READY_TO_SEND" || !state.send.intent_persisted_at) {
    throw new Error("只能在已持久化 READY_TO_SEND 后登记发送尝试");
  }
  if (state.send.dispatch_attempt_count !== 0) throw new Error("同一 attempt 禁止第二次发送");
  const at = isoNow(now);
  state.send.dispatch_attempt_count = 1;
  state.send.dispatch_started_at = at;
  state.runtime.heartbeat_at = at;
  state.history.push({ phase: "READY_TO_SEND", event: "DISPATCH_STARTED", at });
  assertAttemptState(state);
  return state;
}

export function recordPromptAccepted(state, { clickReturnedAt = null } = {}, now = new Date()) {
  assertAttemptState(state);
  if (state.phase !== "READY_TO_SEND" || state.send.dispatch_attempt_count !== 1) {
    throw new Error("Prompt 接受确认要求恰好一次已登记发送尝试");
  }
  const at = isoNow(now);
  state.send.click_returned_at = clickReturnedAt ? isoNow(clickReturnedAt) : at;
  state.send.accepted_at = at;
  state.timing.sent_at = state.send.dispatch_started_at;
  return transitionAttempt(state, "PROMPT_SENT", { send_accepted_at: at }, at);
}

export function bindConversation(state, {
  conversationId,
  sessionDirectoryId,
  evidence = [],
} = {}, now = new Date()) {
  assertAttemptState(state);
  const conversation = validateSessionId(conversationId);
  const directory = validateSessionId(sessionDirectoryId);
  if (conversation !== directory) throw new Error("conversation ID 与原生 session 目录不一致");
  if (state.send.dispatch_attempt_count !== 1) {
    throw new Error("绑定发送后 conversation 前必须已登记一次发送尝试");
  }
  if (!new Set(["READY_TO_SEND", "PROMPT_SENT", "RUNNING", "NEEDS_ATTENTION"]).has(state.phase)) {
    throw new Error("当前 phase 不允许绑定发送后 conversation");
  }
  state.session.conversation_id = conversation;
  state.session.session_directory_id = directory;
  state.session.binding_status = "tentative";
  state.session.binding_evidence = evidence;
  state.session.turn_id = null;
  state.session.native_cwd = null;
  const at = isoNow(now);
  state.runtime.heartbeat_at = at;
  state.history.push({ phase: state.phase, event: "SESSION_BOUND_TENTATIVE", at });
  assertAttemptState(state);
  return state;
}

export function findNewConversationCandidate(state, visibleConversationIds, sessionDirectoryIds) {
  assertAttemptState(state);
  const baselineVisible = new Set(state.session.baseline_conversation_ids ?? []);
  const baselineDirectories = new Set(state.session.baseline_session_directory_ids ?? []);
  const visible = new Set(visibleConversationIds.map(validateSessionId));
  const directories = new Set(sessionDirectoryIds.map(validateSessionId));
  const newVisible = [...visible].filter((id) => !baselineVisible.has(id)).sort();
  const newDirectories = [...directories].filter((id) => !baselineDirectories.has(id)).sort();
  if (newVisible.length === 1 && newDirectories.length === 1) {
    if (newVisible[0] === newDirectories[0]) {
      return { status: "unique", conversation_id: newVisible[0] };
    }
    return {
      status: "mismatch",
      conversation_id: null,
      visible_candidate_count: 1,
      directory_candidate_count: 1,
    };
  }
  if (newVisible.length === 0 || newDirectories.length === 0) {
    return {
      status: "missing",
      conversation_id: null,
      visible_candidate_count: newVisible.length,
      directory_candidate_count: newDirectories.length,
    };
  }
  return {
    status: "ambiguous",
    conversation_id: null,
    visible_candidate_count: newVisible.length,
    directory_candidate_count: newDirectories.length,
  };
}

export function decideResume(state, {
  visibleConversationIds = [],
  sessionDirectoryIds = [],
} = {}) {
  assertAttemptState(state);
  if (state.terminal) return { action: "terminal", allow_send: false, reason: "attempt-already-terminal" };
  if (PRE_SEND_PHASES.has(state.phase)) {
    return { action: "resume-setup", allow_send: false, reason: "send-intent-not-persisted" };
  }
  if (state.phase === "READY_TO_SEND" && state.send.dispatch_attempt_count === 0) {
    return { action: "dispatch-once", allow_send: true, reason: "dispatch-start-not-persisted" };
  }
  if (state.session.conversation_id) {
    const visible = new Set(visibleConversationIds.map(validateSessionId));
    const directories = new Set(sessionDirectoryIds.map(validateSessionId));
    if (visible.has(state.session.conversation_id) && directories.has(state.session.conversation_id)) {
      return { action: "observe-only", allow_send: false, reason: "persisted-session-reconfirmed" };
    }
    return { action: "needs-attention", allow_send: false, reason: "persisted-session-not-reconfirmed" };
  }
  const candidate = findNewConversationCandidate(state, visibleConversationIds, sessionDirectoryIds);
  if (candidate.status === "unique") {
    return {
      action: "bind-and-observe",
      allow_send: false,
      reason: "one-new-ui-and-session-directory-id",
      conversation_id: candidate.conversation_id,
    };
  }
  return {
    action: "needs-attention",
    allow_send: false,
    reason: candidate.status === "ambiguous"
      ? "multiple-new-session-candidates"
      : candidate.status === "mismatch"
        ? "new-ui-and-session-directory-id-mismatch"
        : "send-status-uncertain",
  };
}

async function rejectUnsafeExistingStateFile(pathValue) {
  try {
    const info = await lstat(pathValue);
    if (info.isSymbolicLink() || !info.isFile()) throw new Error("automation state 路径不是普通文件");
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

export async function atomicWriteAttemptState(pathValue, state, overrides = {}) {
  assertAttemptState(state);
  if (!isAbsolute(pathValue)) throw new Error("automation state 路径必须是绝对路径");
  await rejectUnsafeExistingStateFile(pathValue);
  const makeDirectory = overrides.mkdir ?? mkdir;
  const write = overrides.writeFile ?? writeFile;
  const move = overrides.rename ?? rename;
  const remove = overrides.rm ?? rm;
  await makeDirectory(dirname(pathValue), { recursive: true });
  const temporary = `${pathValue}.tmp-${process.pid}-${randomUUID()}`;
  try {
    await write(temporary, `${JSON.stringify(state, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
      flag: "wx",
    });
    await move(temporary, pathValue);
  } catch (error) {
    await remove(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

export async function readAttemptState(pathValue) {
  if (!isAbsolute(pathValue)) throw new Error("automation state 路径必须是绝对路径");
  const info = await lstat(pathValue);
  if (info.isSymbolicLink() || !info.isFile()) throw new Error("automation state 路径不是普通文件");
  const state = JSON.parse(await readFile(pathValue, "utf8"));
  return assertAttemptState(state);
}

export async function persistBeforeDispatch(pathValue, state, now = new Date(), overrides = {}) {
  recordDispatchStart(state, now);
  await atomicWriteAttemptState(pathValue, state, overrides);
  return state;
}
