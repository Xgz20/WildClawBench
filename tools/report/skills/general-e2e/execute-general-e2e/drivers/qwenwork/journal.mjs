import { randomUUID } from "node:crypto";
import { lstat, mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { dirname, parse, resolve } from "node:path";

export const QWENWORK_JOURNAL_SCHEMA = "wildclawbench.general-e2e-qwenwork-attempt-journal/v1";
export const QWENWORK_JOURNAL_VERSION = "0.1.0";

const IDENTITY_FIELDS = Object.freeze(["batch_id", "unit_id", "task_id", "attempt_id"]);
const TERMINAL_PHASES = new Set(["COMPLETED", "FAILED"]);

function requireString(value, name) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`QWENWORK_JOURNAL_FIELD_MISSING: ${name}`);
  return value;
}

function normalizeIdentity(identity) {
  return Object.fromEntries(IDENTITY_FIELDS.map((field) => [field, requireString(identity?.[field], `identity.${field}`)]));
}

function event(type, at, details = {}) {
  return { type, at: requireString(at, `${type}.at`), details };
}

function appendEvent(state, type, at, details = {}) {
  state.events.push(event(type, at, details));
}

function normalizedBaseline(baseline) {
  if (!Array.isArray(baseline)) throw new Error("QWENWORK_BASELINE_INVALID");
  return baseline.map((entry) => ({
    session_id: entry?.session_id || null,
    sub_chat_id: entry?.sub_chat_id || null,
    conversation_id: entry?.conversation_id || null,
    local_project_id: entry?.local_project_id || null,
    cwd: entry?.cwd ? resolve(String(entry.cwd)) : null,
    updated_at_ms: Number.isFinite(Number(entry?.updated_at_ms)) ? Number(entry.updated_at_ms) : null,
  }));
}

function assertProject(project, workspace) {
  requireString(project?.project_id, "project.project_id");
  requireString(project?.project_name, "project.project_name");
  requireString(project?.confirmed_path, "project.confirmed_path");
  if (resolve(project.confirmed_path) !== resolve(workspace)) {
    throw new Error("QWENWORK_WORKSPACE_READBACK_MISMATCH");
  }
}

function assertUiConfiguration(configuration) {
  requireString(configuration?.model?.actual_model, "configuration.model.actual_model");
  const permission = requireString(configuration?.permission?.confirmed_mode, "configuration.permission.confirmed_mode");
  if (!new Set(["default-sandbox", "full-access"]).has(permission)) {
    throw new Error(`QWENWORK_PERMISSION_UNKNOWN: ${permission}`);
  }
  if (configuration.model.changed === true || configuration.permission.changed === true) {
    throw new Error("QWENWORK_CONFIGURATION_MUTATION_FORBIDDEN");
  }
}

export function createQwenAttemptJournal({
  identity,
  dataset,
  taskRoot,
  candidateWorkspace,
  prompt,
  configDigest,
  now,
}) {
  const normalizedIdentity = normalizeIdentity(identity);
  const createdAt = requireString(now, "now");
  const state = {
    schema_version: QWENWORK_JOURNAL_SCHEMA,
    journal_version: QWENWORK_JOURNAL_VERSION,
    identity: normalizedIdentity,
    dataset: {
      id: requireString(dataset?.id, "dataset.id"),
      digest: requireString(dataset?.digest, "dataset.digest"),
    },
    config_digest: requireString(configDigest, "config_digest"),
    phase: "PREPARING",
    task_root: resolve(requireString(taskRoot, "task_root")),
    candidate_workspace: resolve(requireString(candidateWorkspace, "candidate_workspace")),
    prompt: {
      path: resolve(requireString(prompt?.path, "prompt.path")),
      sha256: requireString(prompt?.sha256, "prompt.sha256"),
      send_status: "not_sent",
      sent_at: null,
    },
    workspace: {
      requested_path: resolve(candidateWorkspace),
      confirmed_path: null,
      local_project_id: null,
      project_name: null,
      verification_method: null,
    },
    configuration: {
      model: null,
      permission: null,
      verified_at: null,
    },
    send: {
      reservation_id: null,
      dispatch_attempt_count: 0,
      state: "not_reserved",
      invoking_at: null,
      returned_at: null,
      method: null,
    },
    session: {
      baseline: [],
      conversation_id: null,
      sub_chat_id: null,
      session_id: null,
      local_project_id: null,
      cwd: null,
      verified: false,
      captured_at: null,
      prompt_evidence: null,
    },
    attention: null,
    execution_state: null,
    recovery: {
      resume_count: 0,
      last_decision: "prepare",
      last_resumed_at: null,
      last_readonly_probe: null,
    },
    created_at: createdAt,
    updated_at: createdAt,
    events: [event("JOURNAL_CREATED", createdAt)],
  };
  return state;
}

export function recordQwenDispatchIntent(state, {
  project,
  configuration,
  baseline,
  now,
}) {
  if (state.phase !== "PREPARING" || state.send.dispatch_attempt_count !== 0) {
    throw new Error("QWENWORK_INTENT_STATE_INVALID");
  }
  assertProject(project, state.candidate_workspace);
  assertUiConfiguration(configuration);
  state.workspace = {
    requested_path: state.candidate_workspace,
    confirmed_path: resolve(project.confirmed_path),
    local_project_id: project.project_id,
    project_name: project.project_name,
    verification_method: project.verification_method || "agents-sqlite-root_paths[0]",
  };
  state.configuration = {
    model: structuredClone(configuration.model),
    permission: structuredClone(configuration.permission),
    verified_at: now,
  };
  state.session.baseline = normalizedBaseline(baseline);
  state.prompt.send_status = "intent_persisted";
  state.phase = "READY_TO_DISPATCH";
  state.updated_at = now;
  appendEvent(state, "DISPATCH_INTENT_PERSISTED", now, {
    project_id: project.project_id,
    prompt_sha256: state.prompt.sha256,
    baseline_count: state.session.baseline.length,
  });
  return state;
}

export function reserveQwenDispatch(state, { now, reservationId = randomUUID() }) {
  if (
    state.phase !== "READY_TO_DISPATCH"
    || state.prompt.send_status !== "intent_persisted"
    || state.send.dispatch_attempt_count !== 0
  ) {
    throw new Error("QWENWORK_DISPATCH_RESERVATION_INVALID");
  }
  state.send.reservation_id = requireString(reservationId, "reservation_id");
  state.send.dispatch_attempt_count = 1;
  state.send.state = "invoking";
  state.send.invoking_at = now;
  state.prompt.send_status = "uncertain";
  state.phase = "DISPATCH_UNCERTAIN";
  state.updated_at = now;
  appendEvent(state, "DISPATCH_INVOKING", now, { reservation_id: state.send.reservation_id });
  return state;
}

export function markQwenDispatchReturned(state, { now, method }) {
  if (state.send.dispatch_attempt_count !== 1 || state.send.state !== "invoking") {
    throw new Error("QWENWORK_DISPATCH_RETURN_INVALID");
  }
  state.send.state = "attempted";
  state.send.returned_at = now;
  state.send.method = requireString(method, "dispatch.method");
  state.updated_at = now;
  appendEvent(state, "DISPATCH_RETURNED", now, { method: state.send.method });
  return state;
}

export function confirmQwenDispatchBinding(state, { session, promptEvidence, now }) {
  if (state.send.dispatch_attempt_count !== 1 || !new Set(["invoking", "attempted"]).has(state.send.state)) {
    throw new Error("QWENWORK_BINDING_STATE_INVALID");
  }
  requireString(session?.session_id, "session.session_id");
  requireString(session?.local_project_id, "session.local_project_id");
  requireString(session?.cwd, "session.cwd");
  if (session.local_project_id !== state.workspace.local_project_id) {
    throw new Error("QWENWORK_SESSION_PROJECT_MISMATCH");
  }
  if (resolve(session.cwd) !== state.candidate_workspace) {
    throw new Error("QWENWORK_SESSION_WORKSPACE_MISMATCH");
  }
  if (promptEvidence?.verified !== true || promptEvidence?.prompt_sha256 !== state.prompt.sha256) {
    throw new Error("QWENWORK_SESSION_PROMPT_MISMATCH");
  }
  state.session = {
    ...state.session,
    conversation_id: session.conversation_id || null,
    sub_chat_id: session.sub_chat_id || null,
    session_id: session.session_id,
    local_project_id: session.local_project_id,
    cwd: resolve(session.cwd),
    verified: true,
    captured_at: now,
    prompt_evidence: structuredClone(promptEvidence),
  };
  state.prompt.send_status = "sent";
  state.prompt.sent_at = state.send.returned_at || state.send.invoking_at;
  state.send.state = "confirmed";
  state.phase = "RUNNING";
  state.attention = null;
  state.updated_at = now;
  appendEvent(state, "DISPATCH_BOUND", now, { session_id: session.session_id });
  return state;
}

export function refreshQwenPromptEvidence(state, promptEvidence, now) {
  if (state?.session?.verified !== true || state?.prompt?.send_status !== "sent") {
    throw new Error("QWENWORK_PROMPT_EVIDENCE_REFRESH_STATE_INVALID");
  }
  if (promptEvidence?.verified !== true || promptEvidence?.prompt_sha256 !== state.prompt.sha256) {
    throw new Error("QWENWORK_SESSION_PROMPT_MISMATCH");
  }
  state.session.prompt_evidence = structuredClone(promptEvidence);
  state.updated_at = now;
  appendEvent(state, "PROMPT_EVIDENCE_REFRESHED", now, {
    transcript_sha256: promptEvidence.transcript_sha256,
    transcript_size: promptEvidence.transcript_size,
  });
  return state;
}

export function markQwenNeedsAttention(state, { code, message, now }) {
  state.phase = "NEEDS_ATTENTION";
  state.execution_state = null;
  state.attention = {
    code: requireString(code, "attention.code"),
    message: requireString(message, "attention.message"),
    at: now,
  };
  state.updated_at = now;
  appendEvent(state, "NEEDS_ATTENTION", now, { code, message });
  return state;
}

export function recordQwenRecoveryProbe(state, probe, now) {
  if (probe?.verified !== true || !probe?.sha256 || !probe?.path || !probe?.probed_at) {
    throw new Error("QWENWORK_RECOVERY_PROBE_INVALID");
  }
  state.recovery.last_readonly_probe = {
    path: resolve(probe.path),
    sha256: probe.sha256,
    probed_at: probe.probed_at,
    active_or_pending_count: Number.isInteger(probe.active_or_pending_count)
      ? probe.active_or_pending_count
      : null,
  };
  state.updated_at = now;
  appendEvent(state, "RECOVERY_PROBE_VERIFIED", now, state.recovery.last_readonly_probe);
  return state;
}

export function applyQwenExecutionProjection(state, executionState, now) {
  if (executionState?.identity?.attempt_id !== state.identity.attempt_id) {
    throw new Error("QWENWORK_PROJECTION_ATTEMPT_MISMATCH");
  }
  state.phase = executionState.phase;
  state.execution_state = structuredClone(executionState);
  state.updated_at = now;
  if (executionState.phase === "NEEDS_ATTENTION") {
    state.attention ||= {
      code: "QWENWORK_TERMINAL_EVIDENCE_INCOMPLETE",
      message: "QwenWork terminal observation is incomplete or contradictory",
      at: now,
    };
  } else if (executionState.phase !== "RUNNING") {
    state.attention = null;
  }
  appendEvent(state, "EXECUTION_PROJECTED", now, {
    phase: executionState.phase,
    business_status: executionState.execution?.business_status || null,
  });
  return state;
}

export function assertQwenJournalMatches(state, expected) {
  if (state?.schema_version !== QWENWORK_JOURNAL_SCHEMA) throw new Error("QWENWORK_JOURNAL_SCHEMA_MISMATCH");
  const identity = normalizeIdentity(expected.identity);
  for (const field of IDENTITY_FIELDS) {
    if (state.identity?.[field] !== identity[field]) throw new Error(`QWENWORK_JOURNAL_IDENTITY_MISMATCH: ${field}`);
  }
  if (state.config_digest !== expected.configDigest) throw new Error("QWENWORK_JOURNAL_CONFIG_MISMATCH");
  if (state.dataset?.digest !== expected.dataset?.digest) throw new Error("QWENWORK_JOURNAL_DATASET_MISMATCH");
  if (resolve(state.candidate_workspace) !== resolve(expected.candidateWorkspace)) {
    throw new Error("QWENWORK_JOURNAL_WORKSPACE_MISMATCH");
  }
  if (state.prompt?.sha256 !== expected.prompt?.sha256 || resolve(state.prompt.path) !== resolve(expected.prompt.path)) {
    throw new Error("QWENWORK_JOURNAL_PROMPT_MISMATCH");
  }
  if (state.send.dispatch_attempt_count > 1) throw new Error("QWENWORK_DUPLICATE_DISPATCH_DETECTED");
  if (state.execution_state != null) {
    if (state.execution_state?.identity?.attempt_id !== state.identity.attempt_id) {
      throw new Error("QWENWORK_JOURNAL_EXECUTION_ATTEMPT_MISMATCH");
    }
    if (state.execution_state.phase !== state.phase) {
      throw new Error("QWENWORK_JOURNAL_EXECUTION_PHASE_MISMATCH");
    }
    if (state.execution_state.send?.dispatch_attempt_count !== state.send.dispatch_attempt_count) {
      throw new Error("QWENWORK_JOURNAL_EXECUTION_DISPATCH_MISMATCH");
    }
  }
  return state;
}

export function planQwenRecovery(state, now) {
  let action;
  if (TERMINAL_PHASES.has(state.phase) && state.execution_state) action = "return-terminal";
  else if (TERMINAL_PHASES.has(state.phase) && state.session?.verified) action = "observe-bound-session";
  else if (state.session?.verified && state.prompt?.send_status === "sent") action = "observe-bound-session";
  else if (
    state.send?.dispatch_attempt_count === 1
    || state.prompt?.send_status === "uncertain"
    || new Set(["invoking", "attempted"]).has(state.send?.state)
  ) action = "inspect-only";
  else if (
    state.phase === "READY_TO_DISPATCH"
    && state.prompt?.send_status === "intent_persisted"
    && state.send?.dispatch_attempt_count === 0
  ) action = "dispatch-once";
  else if (
    state.send?.dispatch_attempt_count === 0
    && state.send?.state === "not_reserved"
    && state.prompt?.send_status === "not_sent"
    && (state.phase === "PREPARING" || (
      state.phase === "NEEDS_ATTENTION"
      && state.attention?.code === "QWENWORK_PRE_SEND_PREPARATION_FAILED"
    ))
  ) {
    action = "prepare";
    state.phase = "PREPARING";
    state.attention = null;
  }
  else action = "inspect-only";
  state.recovery.resume_count += 1;
  state.recovery.last_decision = action;
  state.recovery.last_resumed_at = now;
  state.updated_at = now;
  appendEvent(state, "RECOVERY_PLANNED", now, { action });
  return action;
}

export async function readQwenJournal(path) {
  await assertNoSymlinkPath(path);
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

export async function atomicWriteQwenJournal(path, state) {
  await assertNoSymlinkPath(path);
  await mkdir(dirname(path), { recursive: true });
  await assertNoSymlinkPath(path);
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  await writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, { encoding: "utf8", flag: "wx", mode: 0o600 });
  try {
    await rename(temporary, path);
    await assertNoSymlinkPath(path, { requireLeaf: true });
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

export async function assertNoSymlinkPath(path, { requireLeaf = false } = {}) {
  const target = resolve(path);
  const parsed = parse(target);
  const segments = target.slice(parsed.root.length).split(/[\\/]+/u).filter(Boolean);
  let current = parsed.root;
  for (let index = 0; index < segments.length; index += 1) {
    current = resolve(current, segments[index]);
    let metadata;
    try {
      metadata = await lstat(current);
    } catch (error) {
      if (error?.code === "ENOENT") {
        if (requireLeaf && index === segments.length - 1) throw error;
        return;
      }
      throw error;
    }
    if (metadata.isSymbolicLink()) throw new Error(`QWENWORK_STATE_SYMLINK_REJECTED: ${current}`);
    if (index < segments.length - 1 && !metadata.isDirectory()) {
      throw new Error(`QWENWORK_STATE_ANCESTOR_NOT_DIRECTORY: ${current}`);
    }
    if (index === segments.length - 1 && requireLeaf && !metadata.isFile()) {
      throw new Error(`QWENWORK_STATE_LEAF_NOT_REGULAR: ${current}`);
    }
  }
}
