#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { lstat, open, readFile, readdir, realpath, stat, writeFile, mkdir, rename, rm } from "node:fs/promises";
import { hostname } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";
import { buildQwenGeneralExecutionState } from "./execution-state.mjs";
import {
  applyQwenExecutionProjection,
  assertNoSymlinkPath,
  assertQwenJournalMatches,
  atomicWriteQwenJournal,
  confirmQwenDispatchBinding,
  createQwenAttemptJournal,
  markQwenDispatchReturned,
  markQwenNeedsAttention,
  planQwenRecovery,
  readQwenJournal,
  recordQwenRecoveryProbe,
  recordQwenDispatchIntent,
  reserveQwenDispatch,
  refreshQwenPromptEvidence,
} from "./journal.mjs";
import {
  queryQwenProjectRows,
  queryQwenSessionRows,
  selectQwenSessionForAttempt,
} from "./session-state.mjs";
import {
  assertStableQwenUiConfiguration,
  chooseQwenWorkMainPage,
  confirmQwenWorkspaceProject,
  createQwenLocalProject,
  dispatchQwenPrompt,
  fillQwenPrompt,
  inspectQwenTaskUi,
  inspectQwenPendingInteraction,
  openQwenTaskByProjectAndName,
  readQwenUiConfiguration,
  readQwenPrompt,
  restoreQwenPreparedProject,
  skipQwenClarification,
} from "./ui.mjs";

export const QWENWORK_CANARY_CONFIG_SCHEMA = "wildclawbench.general-e2e-qwenwork-canary-config/v1";
export const QWENWORK_CANARY_DRIVER_VERSION = "0.1.8";
const PROVISIONAL_SESSION_SETTLE_MS = 60_000;
const SCRIPT_DIR = resolve(fileURLToPath(new URL(".", import.meta.url)));
const BUNDLE_ID = "cn.qwenwork.desktop.mac";
const PROBE_SCHEMA = "wildclawbench.general-e2e-qwenwork-readonly-probe/v1";

function usage() {
  return `QwenWork macOS General E2E 单题 canary Driver

用法：
  node drivers/qwenwork/driver.mjs --config /absolute/qwenwork-canary.json --validate-only
  node drivers/qwenwork/driver.mjs --config /absolute/qwenwork-canary.json
  node drivers/qwenwork/driver.mjs --config /absolute/qwenwork-canary.json --resume \
    --resume-probe /absolute/fresh-readonly-probe.json \
    --resume-probe-sha256 <sha256> [--observe-once]

选项：
  --validate-only   只校验冻结配置、Prompt、Workspace 和 probe，不连接或操作 QwenWork
  --resume          恢复同一 attempt；进入发送临界区后只观察原 session，禁止重发
  --resume-probe    本次恢复新生成的只读 probe；不参与冻结 config digest
  --resume-probe-sha256  本次恢复 probe 的独立 SHA-256
  --initial-probe    托管队列本次初始发送使用的 fresh probe；不改冻结配置
  --initial-probe-sha256  initial probe 文件的 SHA-256
  --prepare-only    托管队列只创建并核验本题项目和草稿，发送留给同 attempt resume
  --observe-once    与 --resume 一起使用；只做一次原生状态/UI 观察
  --managed-queue-id  由 QwenWork 批量队列传入的稳定队列 ID
  --allowed-active-session-id  批量队列当前允许保持 running 的原生 session；可重复
  --allowed-active-conversation-id  session_id 延迟落库时允许保持 running 的 conversation；可重复
  -h, --help        显示帮助

Driver 不启动、重启或退出 QwenWork，不切换模型或权限。live 模式要求配置中登记独占桌面时段和显式执行授权。`;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableValue(value[key])]));
  }
  return value;
}

export function calculateQwenCanaryConfigDigest(config) {
  const copy = structuredClone(config);
  delete copy.config_digest;
  delete copy.resume;
  delete copy.recovery_probe;
  delete copy.managed_queue_id;
  delete copy.allowed_active_session_ids;
  delete copy.allowed_active_conversation_ids;
  delete copy.prepare_only;
  if (copy.prompt) delete copy.prompt.content;
  return sha256(JSON.stringify(stableValue(copy)));
}

function requiredString(value, name) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`QWENWORK_CANARY_FIELD_MISSING: ${name}`);
  return value;
}

function absolutePath(value, name) {
  const path = requiredString(value, name);
  if (!isAbsolute(path)) throw new Error(`QWENWORK_CANARY_PATH_NOT_ABSOLUTE: ${name}`);
  return resolve(path);
}

function loopbackEndpoint(value) {
  const parsed = new URL(requiredString(value, "client.endpoint"));
  if (!new Set(["127.0.0.1", "localhost", "::1"]).has(parsed.hostname)) {
    throw new Error("QWENWORK_CANARY_ENDPOINT_NOT_LOOPBACK");
  }
  return parsed.toString().replace(/\/$/u, "");
}

export function assertQwenCanaryConfig(config, { requireLiveAuthorization = false } = {}) {
  if (config?.schema_version !== QWENWORK_CANARY_CONFIG_SCHEMA) {
    throw new Error(`QWENWORK_CANARY_SCHEMA_UNSUPPORTED: ${config?.schema_version || "missing"}`);
  }
  if (config.config_digest_algorithm !== "sha256-canonical-json/v1") {
    throw new Error("QWENWORK_CANARY_DIGEST_ALGORITHM_UNSUPPORTED");
  }
  const digest = calculateQwenCanaryConfigDigest(config);
  if (digest !== config.config_digest) throw new Error(`QWENWORK_CANARY_DIGEST_MISMATCH: ${digest}`);
  for (const field of ["batch_id", "unit_id", "task_id", "attempt_id"]) {
    requiredString(config.identity?.[field], `identity.${field}`);
  }
  requiredString(config.dataset?.id, "dataset.id");
  requiredString(config.dataset?.digest, "dataset.digest");
  absolutePath(config.task_root, "task_root");
  absolutePath(config.candidate_workspace, "candidate_workspace");
  absolutePath(config.prompt?.path, "prompt.path");
  requiredString(config.prompt?.sha256, "prompt.sha256");
  absolutePath(config.state_file, "state_file");
  absolutePath(config.evidence_root, "evidence_root");
  absolutePath(config.client?.session_db, "client.session_db");
  absolutePath(config.client?.trace_root, "client.trace_root");
  if (config.client?.platform !== undefined && typeof config.client.platform !== "string") {
    throw new Error("QWENWORK_CANARY_PLATFORM_INVALID");
  }
  loopbackEndpoint(config.client?.endpoint);
  if (config.client?.bundle_id !== BUNDLE_ID) throw new Error("QWENWORK_CANARY_BUNDLE_ID_MISMATCH");
  requiredString(config.control?.desktop_slot_id, "control.desktop_slot_id");
  absolutePath(config.control?.probe_path, "control.probe_path");
  requiredString(config.control?.probe_sha256, "control.probe_sha256");
  if (config.control?.model_policy !== "keep-current" || config.control?.permission_policy !== "keep-current") {
    throw new Error("QWENWORK_CANARY_CONFIGURATION_POLICY_INVALID");
  }
  if (config.control?.create_new_project !== true) throw new Error("QWENWORK_CANARY_NEW_PROJECT_REQUIRED");
  if (config.control?.require_token_usage_exposure !== undefined
      && typeof config.control.require_token_usage_exposure !== "boolean") {
    throw new Error("QWENWORK_CANARY_TOKEN_EXPOSURE_POLICY_INVALID");
  }
  if (config.control?.clarification_policy !== undefined
      && !new Set(["manual", "skip-question-card"]).has(config.control.clarification_policy)) {
    throw new Error("QWENWORK_CANARY_CLARIFICATION_POLICY_INVALID");
  }
  const probeMaxAge = Number(config.control?.probe_max_age_seconds);
  if (!Number.isInteger(probeMaxAge) || probeMaxAge < 1 || probeMaxAge > 900) {
    throw new Error("QWENWORK_CANARY_PROBE_MAX_AGE_INVALID");
  }
  if (requireLiveAuthorization && config.control?.live_execution_authorized !== true) {
    throw new Error("QWENWORK_CANARY_LIVE_AUTHORIZATION_REQUIRED");
  }
  return config;
}

export function assertQwenCanaryProbe(
  probe,
  config,
  now = Date.now(),
  { requireFresh = true, requireIdle = true } = {},
) {
  if (probe?.schema_version !== PROBE_SCHEMA) throw new Error("QWENWORK_CANARY_PROBE_SCHEMA_MISMATCH");
  if (probe.driver?.harness !== "qwenwork" || probe.driver?.platform !== "macos") {
    throw new Error("QWENWORK_CANARY_PROBE_DRIVER_MISMATCH");
  }
  if (probe.app?.bundle_id !== config.client.bundle_id || probe.app?.identity_verified !== true) {
    throw new Error("QWENWORK_CANARY_PROBE_APP_MISMATCH");
  }
  if (config.control?.require_token_usage_exposure === true
      && (probe.app?.token_usage_exposure?.status !== "enabled"
        || !Number.isSafeInteger(probe.app?.token_usage_exposure?.listener_pid))) {
    throw new Error("QWENWORK_CANARY_TOKEN_EXPOSURE_REQUIRED");
  }
  if (probe.ready_for_read_only_mapping !== true
      || probe.native_state?.database?.quick_check !== "ok") {
    throw new Error("QWENWORK_CANARY_PROBE_NATIVE_STATE_INVALID");
  }
  if (requireIdle && probe.native_state?.database?.active_or_pending_count !== 0) {
    throw new Error("QWENWORK_CANARY_PROBE_ACTIVE_SESSION_PRESENT");
  }
  const probedAt = Date.parse(probe.probed_at || "");
  const maximumAge = Number(config.control.probe_max_age_seconds) * 1000;
  if (!Number.isFinite(probedAt) || probedAt > now || (requireFresh && now - probedAt > maximumAge)) {
    throw new Error("QWENWORK_CANARY_PROBE_STALE");
  }
  const forbidden = new Set(probe.operations_performed || []);
  if (["send-prompt", "change-model-or-permissions", "select-project-or-workspace"].some((item) => forbidden.has(item))) {
    throw new Error("QWENWORK_CANARY_PROBE_MUTATION_DETECTED");
  }
  return probe;
}

export function parseDriverArgs(argv) {
  const result = {
    config: "",
    resume: false,
    resumeProbe: "",
    resumeProbeSha256: "",
    initialProbe: "",
    initialProbeSha256: "",
    observeOnce: false,
    validateOnly: false,
    prepareOnly: false,
    managedQueueId: "",
    allowedActiveSessionIds: [],
    allowedActiveConversationIds: [],
    help: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "-h" || argument === "--help") result.help = true;
    else if (argument === "--resume") result.resume = true;
    else if (argument === "--resume-probe" || argument === "--resume-probe-sha256") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${argument} 缺少值`);
      if (argument === "--resume-probe") result.resumeProbe = value;
      else result.resumeProbeSha256 = value;
      index += 1;
    }
    else if (argument === "--initial-probe" || argument === "--initial-probe-sha256") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${argument} 缺少值`);
      if (argument === "--initial-probe") result.initialProbe = value;
      else result.initialProbeSha256 = value;
      index += 1;
    }
    else if (argument === "--observe-once") result.observeOnce = true;
    else if (argument === "--managed-queue-id") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error("--managed-queue-id 缺少值");
      result.managedQueueId = value;
      index += 1;
    }
    else if (argument === "--allowed-active-session-id") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error("--allowed-active-session-id 缺少值");
      result.allowedActiveSessionIds.push(value);
      index += 1;
    }
    else if (argument === "--allowed-active-conversation-id") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error("--allowed-active-conversation-id 缺少值");
      result.allowedActiveConversationIds.push(value);
      index += 1;
    }
    else if (argument === "--validate-only") result.validateOnly = true;
    else if (argument === "--prepare-only") result.prepareOnly = true;
    else if (argument === "--config") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error("--config 缺少值");
      result.config = value;
      index += 1;
    } else throw new Error(`未知选项：${argument}`);
  }
  if (result.observeOnce && !result.resume) throw new Error("--observe-once 必须与 --resume 一起使用");
  if (result.resume && (!result.resumeProbe || !result.resumeProbeSha256)) {
    throw new Error("--resume 必须同时指定 --resume-probe 和 --resume-probe-sha256");
  }
  if (!result.resume && (result.resumeProbe || result.resumeProbeSha256)) {
    throw new Error("--resume-probe 仅可与 --resume 一起使用");
  }
  if ((result.initialProbe && !result.initialProbeSha256)
      || (!result.initialProbe && result.initialProbeSha256)) {
    throw new Error("--initial-probe 与 --initial-probe-sha256 必须同时指定");
  }
  if (!result.help && !result.config) throw new Error("必须指定 --config");
  if (result.allowedActiveSessionIds.length && !result.managedQueueId) {
    throw new Error("--allowed-active-session-id 必须与 --managed-queue-id 一起使用");
  }
  if (result.prepareOnly && !result.managedQueueId) {
    throw new Error("--prepare-only 只能由托管队列使用");
  }
  return result;
}

export async function loadQwenCanaryConfig(path, options = {}) {
  const config = JSON.parse(await readFile(resolve(path), "utf8"));
  assertQwenCanaryConfig(config, options);
  const probePath = options.initialProbePath
    ? absolutePath(options.initialProbePath, "initial_probe.path")
    : absolutePath(config.control.probe_path, "control.probe_path");
  const probeSha256 = options.initialProbeSha256 || config.control.probe_sha256;
  const [prompt, probeContent] = await Promise.all([
    readFile(config.prompt.path, "utf8"),
    readFile(probePath),
  ]);
  if (sha256(prompt) !== config.prompt.sha256) throw new Error("QWENWORK_CANARY_PROMPT_DIGEST_MISMATCH");
  if (sha256(probeContent) !== probeSha256) throw new Error("QWENWORK_CANARY_PROBE_DIGEST_MISMATCH");
  const probe = JSON.parse(probeContent.toString("utf8"));
  assertQwenCanaryProbe(probe, config, Date.now(), {
    requireFresh: options.resume !== true,
    // A managed queue deliberately keeps already-bound native sessions alive
    // while it fills the remaining slots. The live driver performs the
    // stronger allow-list check against a fresh SQLite query before any UI
    // action; standalone attempts retain the idle gate.
    requireIdle: options.resume !== true && !options.managedQueueId,
  });
  let recoveryProbe = null;
  if (options.resume === true) {
    const recoveryProbePath = absolutePath(options.resumeProbePath, "resume_probe.path");
    const recoveryProbeSha256 = requiredString(options.resumeProbeSha256, "resume_probe.sha256");
    if (!/^[a-f0-9]{64}$/u.test(recoveryProbeSha256)) throw new Error("QWENWORK_RESUME_PROBE_DIGEST_INVALID");
    if (recoveryProbePath === resolve(config.control.probe_path)) {
      throw new Error("QWENWORK_RESUME_PROBE_MUST_BE_DISTINCT");
    }
    const recoveryContent = await readFile(recoveryProbePath);
    if (sha256(recoveryContent) !== recoveryProbeSha256) throw new Error("QWENWORK_RESUME_PROBE_DIGEST_MISMATCH");
    const recovery = JSON.parse(recoveryContent.toString("utf8"));
    assertQwenCanaryProbe(recovery, config, Date.now(), { requireFresh: true, requireIdle: false });
    recoveryProbe = {
      verified: true,
      path: recoveryProbePath,
      sha256: recoveryProbeSha256,
      probed_at: recovery.probed_at,
      active_or_pending_count: Number(recovery.native_state?.database?.active_or_pending_count),
    };
  }
  const workspace = await stat(config.candidate_workspace);
  if (!workspace.isDirectory()) throw new Error("QWENWORK_CANARY_WORKSPACE_NOT_DIRECTORY");
  return {
    ...config,
    task_root: resolve(config.task_root),
    candidate_workspace: resolve(config.candidate_workspace),
    state_file: resolve(config.state_file),
    evidence_root: resolve(config.evidence_root),
    client: {
      ...config.client,
      endpoint: loopbackEndpoint(config.client.endpoint),
      session_db: resolve(config.client.session_db),
      trace_root: resolve(config.client.trace_root),
    },
    prompt: { ...config.prompt, path: resolve(config.prompt.path), content: prompt },
    recovery_probe: recoveryProbe,
  };
}

function journalExpectation(config) {
  return {
    identity: config.identity,
    dataset: config.dataset,
    candidateWorkspace: config.candidate_workspace,
    prompt: config.prompt,
    configDigest: config.config_digest,
  };
}

function samePreparedProject(state, prepared) {
  const project = prepared?.project;
  if (
    project?.project_id !== state.workspace.local_project_id
    || resolve(project?.confirmed_path || "/") !== state.candidate_workspace
    || project?.project_name !== state.workspace.project_name
  ) throw new Error("QWENWORK_PREPARED_PROJECT_DRIFT");
  assertStableQwenUiConfiguration(state.configuration, prepared.configuration);
  if (prepared.prompt_sha256 !== state.prompt.sha256) throw new Error("QWENWORK_PREPARED_PROMPT_DRIFT");
  return prepared;
}

async function selectAttemptSession(config, state, dependencies) {
  const rows = await dependencies.querySessions();
  try {
    return selectQwenSessionForAttempt({
      sessions: rows,
      workspace: config.candidate_workspace,
      nativeBinding: state.session?.verified ? state.session : {
        local_project_id: state.workspace.local_project_id,
      },
      baseline: state.session.baseline,
      sentAt: state.send.invoking_at,
    });
  } catch (error) {
    if (/AMBIGUOUS/u.test(String(error?.message))) throw error;
    throw error;
  }
}

async function persistAttention(config, state, dependencies, code, message) {
  markQwenNeedsAttention(state, { code, message, now: dependencies.now() });
  await dependencies.writeJournal(config.state_file, state);
  return { journal: state, execution_state: null };
}

async function processStartIdentity(pid) {
  const result = await runCapture(
    "/bin/ps",
    ["-o", "lstart=", "-p", String(pid)],
    { capture: true, allowFailure: true },
  );
  return result.code === 0 ? String(result.stdout || "").trim() || null : null;
}

export async function inspectLockOwner(owner) {
  if (!owner || owner.host !== hostname() || !Number.isInteger(owner.pid) || owner.pid <= 0) {
    return { stale: false, active: false, verifiable: false, reason: "owner-not-locally-verifiable" };
  }
  let alive = false;
  try {
    process.kill(owner.pid, 0);
    alive = true;
  } catch (error) {
    alive = error?.code === "EPERM";
  }
  if (!alive) return { stale: true, active: false, verifiable: true, reason: "pid-not-running" };
  const currentIdentity = await processStartIdentity(owner.pid);
  if (!currentIdentity || !owner.process_start_identity) {
    return { stale: false, active: true, verifiable: false, reason: "process-start-identity-unavailable" };
  }
  if (currentIdentity !== owner.process_start_identity) {
    return { stale: true, active: false, verifiable: true, reason: "pid-reused" };
  }
  return { stale: false, active: true, verifiable: true, reason: "owner-process-active" };
}

async function acquireQwenAttemptLock(config, overrides = {}) {
  const lockPath = `${config.state_file}.lock`;
  const inspectOwner = overrides.inspectOwner || inspectLockOwner;
  const host = overrides.hostname || hostname();
  const pid = overrides.pid || process.pid;
  const startIdentity = overrides.processStartIdentity
    ? await overrides.processStartIdentity(pid)
    : await processStartIdentity(pid);
  if (!startIdentity) throw new Error("QWENWORK_LOCK_PROCESS_IDENTITY_UNAVAILABLE");
  const owner = {
    schema_version: "wildclawbench.general-e2e-qwenwork-attempt-lock/v1",
    owner_id: randomUUID(),
    attempt_id: config.identity.attempt_id,
    host,
    pid,
    process_start_identity: startIdentity,
    acquired_at: new Date().toISOString(),
    driver_version: QWENWORK_CANARY_DRIVER_VERSION,
    state_file: config.state_file,
  };
  const create = async () => {
    await assertNoSymlinkPath(lockPath);
    await mkdir(dirname(lockPath), { recursive: true });
    await assertNoSymlinkPath(lockPath);
    const handle = await open(lockPath, "wx", 0o600);
    try {
      await handle.writeFile(`${JSON.stringify(owner, null, 2)}\n`, "utf8");
    } finally {
      await handle.close();
    }
  };
  try {
    await create();
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    await assertNoSymlinkPath(lockPath, { requireLeaf: true });
    let existing;
    try {
      existing = JSON.parse(await readFile(lockPath, "utf8"));
    } catch (readError) {
      throw new Error(`QWENWORK_ATTEMPT_LOCK_UNREADABLE: ${readError instanceof Error ? readError.message : String(readError)}`);
    }
    const status = await inspectOwner(existing);
    if (!status.stale || status.active || !status.verifiable) {
      throw new Error(`QWENWORK_ATTEMPT_LOCK_ACTIVE: ${status.reason}`);
    }
    throw new Error(`QWENWORK_ATTEMPT_LOCK_STALE_REQUIRES_CONTROLLED_RECOVERY: ${status.reason}`);
  }
  return {
    path: lockPath,
    owner,
    release: async () => {
      await assertNoSymlinkPath(lockPath, { requireLeaf: true });
      const current = JSON.parse(await readFile(lockPath, "utf8"));
      if (current.owner_id !== owner.owner_id) throw new Error("QWENWORK_ATTEMPT_LOCK_OWNER_CHANGED");
      await rm(lockPath, { force: false });
    },
  };
}

export async function withQwenAttemptLock(config, operation, overrides = {}) {
  const lock = await acquireQwenAttemptLock(config, overrides);
  try {
    return await operation(lock.owner);
  } finally {
    await lock.release();
  }
}

async function bindOrAttend(config, state, dependencies) {
  let session;
  try {
    session = await selectAttemptSession(config, state, dependencies);
  } catch (error) {
    return persistAttention(
      config,
      state,
      dependencies,
      "QWENWORK_SESSION_AMBIGUOUS",
      `${error instanceof Error ? error.message : String(error)}；禁止重发`,
    );
  }
  if (!session) {
    return persistAttention(
      config,
      state,
      dependencies,
      "QWENWORK_SESSION_NOT_UNIQUELY_BOUND",
      "未找到同时满足完整 cwd、local project、发送时间和 pre-send baseline 的唯一新 session；禁止重发",
    );
  }
  let promptEvidence;
  try {
    promptEvidence = await dependencies.verifySessionPrompt(session, config.prompt);
  } catch (error) {
    if (
      config.managed_queue_id
      && !session.session_id
      && session.conversation_id
      && session.sub_chat_id
      && session.local_project_id
      && session.cwd === state.candidate_workspace
      && /QWENWORK_SESSION_ID_UNSAFE_FOR_TRACE_LOOKUP/u.test(String(error?.message))
    ) {
      return provisionalSessionOrAttend(config, state, dependencies, session);
    }
    return persistAttention(
      config,
      state,
      dependencies,
      "QWENWORK_SESSION_PROMPT_UNVERIFIED",
      `${error instanceof Error ? error.message : String(error)}；禁止重发`,
    );
  }
  confirmQwenDispatchBinding(state, { session, promptEvidence, now: dependencies.now() });
  await dependencies.writeJournal(config.state_file, state);
  return { journal: state, session };
}

async function persistProvisionalSession(config, state, dependencies, session) {
  const now = dependencies.now();
  state.session = {
    ...state.session,
    conversation_id: session.conversation_id,
    sub_chat_id: session.sub_chat_id,
    session_id: null,
    local_project_id: session.local_project_id,
    cwd: session.cwd,
    verified: false,
    captured_at: now,
    prompt_evidence: null,
  };
  state.prompt.send_status = "uncertain";
  state.send.state = "attempted";
  state.phase = "RUNNING";
  state.attention = {
    code: "QWENWORK_SESSION_ID_PENDING",
    message: "原生 session_id 尚未落库；保留 conversation/sub-chat/cwd 临时绑定，resume 时补齐，禁止重发",
    at: now,
  };
  state.updated_at = now;
  state.events.push({
    type: "PROVISIONAL_SESSION_BOUND",
    at: now,
    details: {
      conversation_id: session.conversation_id,
      sub_chat_id: session.sub_chat_id,
      cwd: session.cwd,
    },
  });
  await dependencies.writeJournal(config.state_file, state);
  return { journal: state, session, provisional: true };
}

async function provisionalSessionOrAttend(config, state, dependencies, session) {
  // Keep the exact native conversation/cwd binding even if its title or CDP
  // view is not ready yet, so resume can recognize this queue-owned session.
  const provisional = await persistProvisionalSession(config, state, dependencies, session);
  if (typeof dependencies.inspectPendingInteraction === "function" && session.sub_chat_name) {
    try {
      await dependencies.navigateToSession(session);
    } catch (error) {
      return persistAttention(config, state, dependencies, "QWENWORK_SESSION_UI_UNVERIFIED", error.message);
    }
    const interaction = await handlePendingInteraction(config, state, dependencies, session);
    if (interaction?.journal) return interaction;
    // The cached SQLite row predates the authorized skip. Reobserve before
    // applying the inactive identity window to it.
    if (interaction?.skipped) return provisional;
  }
  const sinceSend = Date.parse(state.send?.returned_at || state.send?.invoking_at || "");
  const observedAt = Date.parse(dependencies.now());
  if (!Number.isFinite(sinceSend) || !Number.isFinite(observedAt) || observedAt < sinceSend) {
    return persistAttention(config, state, dependencies,
      "QWENWORK_PROVISIONAL_SESSION_TIME_INVALID", "发送时间无法对账；禁止重发");
  }
  if (observedAt - sinceSend >= PROVISIONAL_SESSION_SETTLE_MS
      && session.classification?.kind !== "running" && !session.stream_id) {
    return persistAttention(config, state, dependencies,
      "QWENWORK_PROVISIONAL_SESSION_INACTIVE",
      "发送后仅有 conversation/sub-chat/cwd，原生 session_id 与活动 stream 长时间未出现；保留原 attempt 并禁止重发");
  }
  return provisional;
}

async function handlePendingInteraction(config, state, dependencies, session) {
  if (typeof dependencies.inspectPendingInteraction !== "function") return null;
  try {
    const pending = await dependencies.inspectPendingInteraction(session);
    if (pending.kind === "none") return null;
    if (pending.kind === "clarification" && config.control.clarification_policy === "skip-question-card"
        && typeof dependencies.skipClarification === "function") {
      const result = await dependencies.skipClarification(session);
      if (!result?.skipped) throw new Error("QWENWORK_CLARIFICATION_NOT_SKIPPED");
      state.phase = "RUNNING";
      state.execution_state = null;
      state.attention = null;
      state.updated_at = dependencies.now();
      state.events.push({ type: "USER_AUTHORIZED_CLARIFICATION_SKIPPED", at: dependencies.now(),
        details: { conversation_id: session.conversation_id, sub_chat_id: session.sub_chat_id, method: result.method } });
      await dependencies.writeJournal(config.state_file, state);
      return result;
    }
    return persistAttention(config, state, dependencies, "QWENWORK_PENDING_INTERACTION",
      `当前会话等待 ${pending.kind}；保持原 attempt，不自动批准或代答`);
  } catch (error) {
    return persistAttention(config, state, dependencies, "QWENWORK_INTERACTION_UNVERIFIED", error.message);
  }
}

async function observeBoundAttempt(config, state, dependencies) {
  const session = await selectAttemptSession(config, state, dependencies);
  if (!session) {
    return persistAttention(
      config,
      state,
      dependencies,
      "QWENWORK_BOUND_SESSION_MISSING",
      "已持久化的原生 session/cwd/local project 无法精确回读；禁止选择其他会话或重发",
    );
  }
  if (
    config.managed_queue_id
    && !session.session_id
    && session.conversation_id
    && session.sub_chat_id
    && session.local_project_id
    && session.cwd === state.candidate_workspace
  ) {
    return provisionalSessionOrAttend(config, state, dependencies, session);
  }
  if (typeof dependencies.navigateToSession === "function") {
    try {
      await dependencies.navigateToSession(session);
    } catch (error) {
      return persistAttention(
        config,
        state,
        dependencies,
        "QWENWORK_SESSION_UI_UNVERIFIED",
        `${error instanceof Error ? error.message : String(error)}；禁止重发`,
      );
    }
  }
  try {
    const promptEvidence = await dependencies.verifySessionPrompt(session, config.prompt);
    refreshQwenPromptEvidence(state, promptEvidence, dependencies.now());
    await dependencies.writeJournal(config.state_file, state);
  } catch (error) {
    return persistAttention(
      config,
      state,
      dependencies,
      "QWENWORK_SESSION_PROMPT_UNVERIFIED",
      `${error instanceof Error ? error.message : String(error)}；禁止重发`,
    );
  }
  const interaction = await handlePendingInteraction(config, state, dependencies, session);
  if (interaction?.journal) return interaction;
  // The skip changed native state after selectAttemptSession's snapshot. Let
  // the queue reobserve it rather than treating that stale row as a conflict.
  if (interaction?.skipped) return { journal: state, execution_state: null };
  const ui = await dependencies.observeUi(session, state);
  const terminalObservation = {
    ...ui,
    binding_consistent: Boolean(
      ui.target_session_verified === true
      &&
      session.session_id === state.session.session_id
      && session.local_project_id === state.workspace.local_project_id
      && session.cwd === state.candidate_workspace
    ),
  };
  const bindingEvidence = await dependencies.writeBindingEvidence({ state, session, terminalObservation });
  const classification = session.classification || {};
  const now = dependencies.now();
  const isNativeTerminal = classification.kind === "terminal";
  const executionState = buildQwenGeneralExecutionState({
    identity: config.identity,
    dataset: config.dataset,
    taskRoot: config.task_root,
    candidateWorkspace: config.candidate_workspace,
    prompt: state.prompt,
    dispatchAttemptCount: state.send.dispatch_attempt_count,
    session,
    bindingEvidence,
    startedAt: state.send.invoking_at,
    finishedAt: isNativeTerminal ? now : null,
    durationSeconds: isNativeTerminal
      ? Math.max(0, (Date.parse(now) - Date.parse(state.send.invoking_at)) / 1000)
      : null,
    cancellationConfirmed: classification.business_status === "cancelled" && terminalObservation.stop_confirmed === true,
    terminalObservation,
    recovery: state.recovery,
    platform: config.client.platform || "macos",
  });
  applyQwenExecutionProjection(state, executionState, now);
  await dependencies.writeJournal(config.state_file, state);
  return { journal: state, execution_state: executionState };
}

async function assertManagedActiveSessions(config, state, dependencies) {
  if (!config.managed_queue_id) return;
  const rows = await dependencies.querySessions();
  const active = rows.filter((row) => row?.classification?.kind === "running");
  const allowed = new Set(config.allowed_active_session_ids || []);
  const allowedConversations = new Set(config.allowed_active_conversation_ids || []);
  if (state.session?.session_id) allowed.add(state.session.session_id);
  if (state.session?.conversation_id) allowedConversations.add(state.session.conversation_id);
  const unknown = active.filter((row) => (
    row.session_id
      ? !allowed.has(row.session_id) && !allowedConversations.has(row.conversation_id)
      : !row.conversation_id || !allowedConversations.has(row.conversation_id)
  ));
  if (unknown.length) {
    throw new Error(`QWENWORK_MANAGED_ACTIVE_SESSION_NOT_ALLOWED: ${unknown.map((row) => row.session_id || row.conversation_id || "<missing>").join(",")}`);
  }
}

async function runQwenGeneralAttemptLocked(config, overrides = {}) {
  assertQwenCanaryConfig(config, { requireLiveAuthorization: true });
  const dependencies = {
    now: () => new Date().toISOString(),
    readJournal: readQwenJournal,
    writeJournal: atomicWriteQwenJournal,
    ...overrides,
  };
  for (const name of [
    "prepareUi", "verifyPreparedUi", "fillPrompt", "dispatchPrompt",
    "querySessions", "verifySessionPrompt", "observeUi", "writeBindingEvidence",
  ]) {
    if (typeof dependencies[name] !== "function") throw new Error(`QWENWORK_DRIVER_DEPENDENCY_MISSING: ${name}`);
  }

  let state = await dependencies.readJournal(config.state_file);
  const recordDispatchStage = async (stage) => {
    state.events.push({ type: "DISPATCH_STAGE_OBSERVED", at: dependencies.now(), details: { stage } });
    await dependencies.writeJournal(config.state_file, state);
  };
  let action = "prepare";
  if (state) {
    if (!config.resume) throw new Error("QWENWORK_EXISTING_JOURNAL_REQUIRES_RESUME");
    assertQwenJournalMatches(state, journalExpectation(config));
    if (config.recovery_probe?.verified !== true) throw new Error("QWENWORK_RESUME_PROBE_REQUIRED");
    recordQwenRecoveryProbe(state, config.recovery_probe, dependencies.now());
    action = planQwenRecovery(state, dependencies.now());
    await dependencies.writeJournal(config.state_file, state);
  } else {
    if (config.resume) throw new Error("QWENWORK_RESUME_JOURNAL_MISSING");
    state = createQwenAttemptJournal({
      identity: config.identity,
      dataset: config.dataset,
      taskRoot: config.task_root,
      candidateWorkspace: config.candidate_workspace,
      prompt: config.prompt,
      configDigest: config.config_digest,
      now: dependencies.now(),
    });
    await dependencies.writeJournal(config.state_file, state);
  }

  if (
    config.resume === true
    && state.send.dispatch_attempt_count === 0
    && !config.managed_queue_id
    && config.recovery_probe.active_or_pending_count !== 0
  ) {
    return persistAttention(
      config,
      state,
      dependencies,
      "QWENWORK_RECOVERY_PROBE_NOT_IDLE_FOR_UNSENT_ATTEMPT",
      "恢复时仍存在活动或待处理原生会话；本 attempt 尚未发送，禁止准备或进入发送临界区",
    );
  }

  try {
    await assertManagedActiveSessions(config, state, dependencies);
  } catch (error) {
    return persistAttention(
      config,
      state,
      dependencies,
      "QWENWORK_MANAGED_ACTIVE_SESSION_NOT_ALLOWED",
      `${error instanceof Error ? error.message : String(error)}；禁止发送或切换会话`,
    );
  }

  if (action === "dispatch-once") await recordDispatchStage("managed-active-check-completed");

  if (action === "return-terminal") return { journal: state, execution_state: structuredClone(state.execution_state) };
  if (action === "observe-bound-session") return observeBoundAttempt(config, state, dependencies);
  if (action === "inspect-only") {
    const bound = await bindOrAttend(config, state, dependencies);
    if (!bound.session) return bound;
    if (bound.provisional === true) return { journal: state, execution_state: null };
    return observeBoundAttempt(config, state, dependencies);
  }

  if (action === "prepare") {
    let prepared;
    try {
      prepared = await dependencies.prepareUi(config, state);
      await dependencies.fillPrompt(config.prompt.content);
      const verified = await dependencies.verifyPreparedUi(config, state, prepared);
      assertStableQwenUiConfiguration(prepared.configuration, verified.configuration);
      if (prepared.project.project_id !== verified.project.project_id
          || resolve(prepared.project.confirmed_path) !== resolve(verified.project.confirmed_path)) {
        throw new Error("QWENWORK_PRE_SEND_WORKSPACE_DRIFT");
      }
      if (verified.prompt_sha256 !== config.prompt.sha256) throw new Error("QWENWORK_PRE_SEND_PROMPT_DRIFT");
      const baseline = await dependencies.querySessions();
      recordQwenDispatchIntent(state, {
        project: verified.project,
        configuration: verified.configuration,
        baseline,
        now: dependencies.now(),
      });
      await dependencies.writeJournal(config.state_file, state);
    } catch (error) {
      return persistAttention(
        config,
        state,
        dependencies,
        "QWENWORK_PRE_SEND_PREPARATION_FAILED",
        error instanceof Error ? error.message : String(error),
      );
    }
  }

  if (config.prepare_only) {
    if (state.phase !== "READY_TO_DISPATCH" || state.send.dispatch_attempt_count !== 0) {
      throw new Error("QWENWORK_PREPARE_ONLY_STATE_INVALID");
    }
    return { journal: state, execution_state: null };
  }

  if (action === "dispatch-once") {
    try {
      // The queue may have prepared several projects before dispatch. Navigate
      // to this exact project and restore its frozen prompt before readback.
      await dependencies.verifyPreparedUi(config, state);
      await recordDispatchStage("prepared-project-restored");
      await dependencies.fillPrompt(config.prompt.content);
      await recordDispatchStage("frozen-prompt-filled");
    } catch (error) {
      return persistAttention(
        config, state, dependencies, "QWENWORK_PRE_DISPATCH_READBACK_FAILED",
        error instanceof Error ? error.message : String(error),
      );
    }
  }

  try {
    const prepared = await dependencies.verifyPreparedUi(config, state);
    samePreparedProject(state, prepared);
    if (action === "dispatch-once") await recordDispatchStage("final-readback-verified");
  } catch (error) {
    return persistAttention(
      config,
      state,
      dependencies,
      "QWENWORK_PRE_DISPATCH_READBACK_FAILED",
      error instanceof Error ? error.message : String(error),
    );
  }

  reserveQwenDispatch(state, { now: dependencies.now() });
  await dependencies.writeJournal(config.state_file, state);
  try {
    const result = await dependencies.dispatchPrompt();
    markQwenDispatchReturned(state, {
      now: dependencies.now(),
      method: result?.method || "client-ui",
    });
    await dependencies.writeJournal(config.state_file, state);
  } catch (error) {
    const bound = await bindOrAttend(config, state, dependencies);
    if (!bound.session) {
      if (bound.journal?.attention) {
        bound.journal.attention.message = `${error instanceof Error ? error.message : String(error)}；${bound.journal.attention.message}`;
        await dependencies.writeJournal(config.state_file, bound.journal);
      }
      return bound;
    }
    if (bound.provisional === true) return { journal: state, execution_state: null };
    return observeBoundAttempt(config, state, dependencies);
  }

  const bound = await bindOrAttend(config, state, dependencies);
  if (!bound.session) return bound;
  if (bound.provisional === true) return { journal: state, execution_state: null };
  return observeBoundAttempt(config, state, dependencies);
}

export async function runQwenGeneralAttempt(config, overrides = {}) {
  assertQwenCanaryConfig(config, { requireLiveAuthorization: true });
  const lockRunner = overrides.withAttemptLock || withQwenAttemptLock;
  return lockRunner(config, () => runQwenGeneralAttemptLocked(config, overrides));
}

async function atomicWriteJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}`;
  const content = `${JSON.stringify(value, null, 2)}\n`;
  await writeFile(temporary, content, "utf8");
  try {
    await rename(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
  return { content, size: Buffer.byteLength(content), sha256: sha256(content) };
}

async function findFiles(root, name, matches = []) {
  const entries = await readdir(root, { withFileTypes: true });
  for (const entry of entries) {
    const path = join(root, entry.name);
    if (entry.isSymbolicLink()) continue;
    if (entry.isDirectory()) await findFiles(path, name, matches);
    else if (entry.isFile() && entry.name === name) matches.push(path);
  }
  return matches;
}

export async function verifyQwenSessionPromptEvidence({ traceRoot, session, prompt }) {
  if (!/^[A-Za-z0-9._:-]+$/u.test(String(session?.session_id || ""))) {
    throw new Error("QWENWORK_SESSION_ID_UNSAFE_FOR_TRACE_LOOKUP");
  }
  const projectsRoot = join(resolve(traceRoot), "projects");
  const matches = await findFiles(projectsRoot, `${session.session_id}.jsonl`);
  if (matches.length !== 1) throw new Error(`QWENWORK_SESSION_TRANSCRIPT_COUNT: ${matches.length}`);
  const path = matches[0];
  const metadata = await lstat(path);
  if (!metadata.isFile() || metadata.isSymbolicLink()) throw new Error("QWENWORK_SESSION_TRANSCRIPT_NOT_REGULAR");
  const content = await readFile(path, "utf8");
  const rows = content.split(/\r?\n/u).filter(Boolean).map((line) => JSON.parse(line));
  const sessionIds = new Set(rows.map((row) => row?.sessionId).filter(Boolean));
  const workspaces = new Set(rows.map((row) => row?.cwd).filter(Boolean).map((cwd) => (
    isAbsolute(cwd) ? resolve(cwd) : null
  )));
  if (sessionIds.size !== 1 || !sessionIds.has(session.session_id)) {
    throw new Error("QWENWORK_TRANSCRIPT_SESSION_MISMATCH");
  }
  if (workspaces.size !== 1 || !workspaces.has(resolve(session.cwd))) {
    throw new Error("QWENWORK_TRANSCRIPT_WORKSPACE_MISMATCH");
  }
  const userTexts = rows.flatMap((row) => row?.type === "user" && Array.isArray(row?.message?.content)
    ? row.message.content.filter((part) => part?.type === "text" && typeof part.text === "string").map((part) => part.text)
    : []);
  const exactMatches = userTexts.filter((text) => sha256(text) === prompt.sha256);
  if (exactMatches.length !== 1) throw new Error(`QWENWORK_TRANSCRIPT_PROMPT_MATCH_COUNT: ${exactMatches.length}`);
  return {
    verified: true,
    prompt_sha256: prompt.sha256,
    transcript_path: path,
    transcript_sha256: sha256(content),
    transcript_size: metadata.size,
    match_count: exactMatches.length,
  };
}

export async function createLiveDependencies(config) {
  const { chromium } = await import("playwright-core");
  const timeout = Number(config.control.timeout_ms || 30_000);
  const browser = await chromium.connectOverCDP(config.client.endpoint, { timeout });
  const page = await chooseQwenWorkMainPage(browser, timeout);
  page.setDefaultTimeout(timeout);
  await page.bringToFront();
  const snapshotOptions = { consistentOnlineBackup: Boolean(config.managed_queue_id) };
  const queryProjects = () => queryQwenProjectRows(config.client.session_db, snapshotOptions);
  // Attempt IDs used by prepared canaries may share a common prefix. Include
  // the frozen config digest so repeated attempts can never select an older
  // project with the same visible name.
  const projectName = `WCB-GEN-${config.identity.task_id.slice(-40)}-${config.config_digest.slice(0, 8)}`;
  const selectNativeFolder = async (workspace) => {
    const result = await runCapture(
      "/usr/bin/swift",
      [join(SCRIPT_DIR, "select-folder.swift"), BUNDLE_ID, workspace, String(Math.ceil(timeout / 1000))],
      { capture: true },
    );
    return JSON.parse(result.stdout.trim());
  };
  const preparedProject = async (state) => {
    const projects = await queryProjects();
    const project = confirmQwenWorkspaceProject({
      projects,
      workspace: config.candidate_workspace,
      expectedProjectId: state.workspace.local_project_id,
    });
    const knownProjectNames = projects.map((entry) => entry.project_name || entry.name).filter(Boolean);
    await restoreQwenPreparedProject(page, project.project_name, timeout, knownProjectNames);
    return project;
  };
  const navigateToSession = async (session) => {
    const projects = await queryProjects();
    const project = projects.find((entry) => entry.project_id === session.local_project_id);
    if (!project?.project_name) throw new Error("QWENWORK_SESSION_PROJECT_NAME_MISSING");
    return openQwenTaskByProjectAndName(
      page,
      project.project_name,
      session.sub_chat_name,
      session.conversation_id,
      timeout,
    );
  };
  return {
    browser,
    dependencies: {
    prepareUi: async () => ({
        project: await createQwenLocalProject({
          page,
          workspace: config.candidate_workspace,
          projectName,
          queryProjects,
          selectNativeFolder,
          timeoutMilliseconds: timeout,
        }),
        configuration: await readQwenUiConfiguration(page),
      }),
      verifyPreparedUi: async (_config, state, prepared = null) => ({
        project: state.workspace?.local_project_id ? await preparedProject(state) : prepared.project,
        configuration: await readQwenUiConfiguration(page),
        prompt_sha256: sha256(await readQwenPrompt(page)),
      }),
      fillPrompt: (prompt) => fillQwenPrompt(page, prompt, timeout),
      dispatchPrompt: () => dispatchQwenPrompt(page, timeout),
      querySessions: () => queryQwenSessionRows(config.client.session_db, snapshotOptions),
      verifySessionPrompt: (session, prompt) => verifyQwenSessionPromptEvidence({
        traceRoot: config.client.trace_root,
        session,
        prompt,
      }),
      navigateToSession,
      inspectPendingInteraction: async (session) => inspectQwenPendingInteraction(
        page, session, await queryQwenSessionRows(config.client.session_db, snapshotOptions),
      ),
      skipClarification: config.control.clarification_policy === "skip-question-card"
        ? (session) => skipQwenClarification(page, session.conversation_id, timeout)
        : undefined,
      observeUi: async (session, _state) => inspectQwenTaskUi(
        page,
        new Date().toISOString(),
        session,
        await queryQwenSessionRows(config.client.session_db, snapshotOptions),
      ),
      writeBindingEvidence: async ({ state, session, terminalObservation }) => {
        const path = join(config.evidence_root, "session-binding.json");
        const result = await atomicWriteJson(path, {
          schema_version: "wildclawbench.general-e2e-qwenwork-session-binding/v1",
          identity: state.identity,
          prompt_sha256: state.prompt.sha256,
          workspace: state.candidate_workspace,
          local_project_id: session.local_project_id,
          conversation_id: session.conversation_id,
          sub_chat_id: session.sub_chat_id,
          session_id: session.session_id,
          terminal_observation: terminalObservation,
        });
        return [{ path, sha256: result.sha256, size: result.size }];
      },
    },
  };
}

async function main(argv = process.argv.slice(2)) {
  const args = parseDriverArgs(argv);
  if (args.help) {
    process.stdout.write(`${usage()}\n`);
    return 0;
  }
  const config = await loadQwenCanaryConfig(args.config, {
    requireLiveAuthorization: !args.validateOnly,
    resume: args.resume,
    resumeProbePath: args.resumeProbe,
    resumeProbeSha256: args.resumeProbeSha256,
    initialProbePath: args.initialProbe,
    initialProbeSha256: args.initialProbeSha256,
    managedQueueId: args.managedQueueId,
  });
  config.resume = args.resume;
  config.managed_queue_id = args.managedQueueId || null;
  config.allowed_active_session_ids = [...args.allowedActiveSessionIds];
  config.allowed_active_conversation_ids = [...args.allowedActiveConversationIds];
  config.prepare_only = args.prepareOnly;
  if (args.validateOnly) {
    process.stdout.write(`${JSON.stringify({
      status: "VALID",
      schema_version: config.schema_version,
      identity: config.identity,
      candidate_workspace: config.candidate_workspace,
      model_policy: config.control.model_policy,
      permission_policy: config.control.permission_policy,
      live_actions_performed: [],
    }, null, 2)}\n`);
    return 0;
  }
  const live = await createLiveDependencies(config);
  try {
    const result = await runQwenGeneralAttempt(config, live.dependencies);
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return result.journal.phase === "COMPLETED" || (args.prepareOnly && result.journal.phase === "READY_TO_DISPATCH")
      ? 0 : result.journal.phase === "RUNNING" ? 4 : 3;
  } finally {
    await live.browser.close().catch(() => {});
  }
}

// Node resolves the module URL through aliases such as macOS /var -> /private/var.
const entryPath = process.argv[1] ? await realpath(process.argv[1]).catch(() => null) : null;
if (entryPath === await realpath(fileURLToPath(import.meta.url))) {
  main().then((code) => { process.exitCode = code; }).catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
  });
}
