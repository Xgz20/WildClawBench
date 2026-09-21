#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import {
  mkdir,
  open,
  readFile,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  calculateRunConfigDigest,
  probeAstronStudio,
} from "./probe_astronstudio_macos.mjs";
import {
  CdpClient,
  clickSend,
  currentThreadId,
  discoverMainTarget,
  fillPrompt,
  prepareExecutionUi,
} from "./lib/astronstudio-cdp.mjs";
import {
  queryFinalResponse,
  queryNativeSessions,
} from "./lib/astronstudio-state.mjs";
import { verifyDesktopAppPath } from "../vendor/e2e-shared/desktop-app-discovery/index.mjs";
import { ASTRONSTUDIO_APP_PROFILE } from "../vendor/e2e-shared/desktop-app-discovery/profiles.mjs";

export const EXECUTION_DRIVER_VERSION = "0.3.0";
export const EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-astronstudio-execution-state/v1";
export const EXECUTION_RECORD_SCHEMA = "urn:wildclawbench:schema:general-e2e:execution-record:v1";
const RUN_CONFIG_SCHEMA = "wildclawbench.general-e2e-astronstudio-run-config/v1";

function usage() {
  return `AstronStudio General E2E macOS 单题执行器

用法：
  node scripts/execute_astronstudio_macos.mjs \\
    --unit-root /absolute/extracted-unit \\
    --task-id <完整任务ID> \\
    --run-config /absolute/frozen-run-config.json [选项]

选项：
  --resume                       恢复同一 attempt；禁止重复发送 Prompt
  --detach-after-submit          绑定 thread/turn/session/cwd 后退出观察
  --observe-once                 恢复后只执行一次原生状态观察
  --managed-run-slots <1-8>     批队列冻结的后台 Agent 槽位，默认 1
  --allowed-active-session-id   批队列已登记的活动 session，可重复
  --timeout-ms <毫秒>            单次 UI/CDP 操作超时，默认 30000
  --poll-interval-ms <毫秒>      终态轮询间隔，默认 1000
  --identity-timeout-ms <毫秒>   发送后身份绑定时限，默认 120000，范围 120000–180000
  -h, --help                     显示帮助

执行器只接受已冻结的 AstronStudio macOS 配置和 execution 包。发送意图先落盘；
发送临界点不确定时进入 NEEDS_ATTENTION，不会重发。`;
}

function positiveInteger(value, name) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`${name} 必须是正整数`);
  return parsed;
}

function boundedSlots(value, name) {
  const parsed = positiveInteger(value, name);
  if (parsed > 8) throw new Error(`${name} 必须在 1–8 之间`);
  return parsed;
}

export function parseArgs(argv) {
  const values = {
    unitRoot: "",
    taskId: "",
    runConfig: "",
    resume: false,
    detachAfterSubmit: false,
    observeOnce: false,
    managedRunSlots: 1,
    allowedActiveSessionIds: [],
    timeoutMs: 30_000,
    pollIntervalMs: 1_000,
    identityTimeoutMs: 120_000,
    help: false,
  };
  const valued = new Map([
    ["--unit-root", "unitRoot"],
    ["--task-id", "taskId"],
    ["--run-config", "runConfig"],
    ["--timeout-ms", "timeoutMs"],
    ["--poll-interval-ms", "pollIntervalMs"],
    ["--identity-timeout-ms", "identityTimeoutMs"],
    ["--managed-run-slots", "managedRunSlots"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else if (arg === "--resume") values.resume = true;
    else if (arg === "--detach-after-submit") values.detachAfterSubmit = true;
    else if (arg === "--observe-once") values.observeOnce = true;
    else if (arg === "--allowed-active-session-id") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error("--allowed-active-session-id 缺少值");
      values.allowedActiveSessionIds.push(value);
      index += 1;
    }
    else {
      const key = valued.get(arg);
      if (!key) throw new Error(`未知选项：${arg}`);
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      values[key] = new Set(["timeoutMs", "pollIntervalMs", "identityTimeoutMs", "managedRunSlots"]).has(key)
        ? (key === "managedRunSlots" ? boundedSlots(value, arg) : positiveInteger(value, arg))
        : value;
      index += 1;
    }
  }
  if (values.observeOnce && !values.resume) throw new Error("--observe-once 必须与 --resume 一起使用");
  if (values.detachAfterSubmit && values.observeOnce) {
    throw new Error("--detach-after-submit 与 --observe-once 不能同时使用");
  }
  if (values.allowedActiveSessionIds.length && !values.detachAfterSubmit) {
    throw new Error("--allowed-active-session-id 只允许批队列发送阶段使用");
  }
  if (new Set(values.allowedActiveSessionIds).size !== values.allowedActiveSessionIds.length) {
    throw new Error("--allowed-active-session-id 不能重复");
  }
  if (values.allowedActiveSessionIds.length >= values.managedRunSlots) {
    throw new Error("已登记活动 session 数必须小于 --managed-run-slots");
  }
  if (values.identityTimeoutMs < 120_000 || values.identityTimeoutMs > 180_000) {
    throw new Error("--identity-timeout-ms 必须在 120000–180000 之间");
  }
  if (!values.help && (!values.unitRoot || !values.taskId || !values.runConfig)) {
    throw new Error("必须指定 --unit-root、--task-id 和 --run-config");
  }
  return values;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function readJsonIfPresent(path) {
  try {
    return await readJson(path);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function isInside(parent, child) {
  const value = relative(parent, child);
  return value === "" || (!value.startsWith("..") && !isAbsolute(value));
}

async function atomicWriteJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  try {
    await rename(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

function relativePosix(root, path) {
  const value = relative(root, path).split("\\").join("/");
  if (!value || value.startsWith("../") || value === "..") {
    throw new Error(`路径不在 unit root 内：${path}`);
  }
  return value;
}

function normalizeReasoning(value) {
  return String(value || "").trim().toLowerCase().replaceAll("_", "-");
}

function assertFrozenConfig(runConfig) {
  if (runConfig?.schema_version !== RUN_CONFIG_SCHEMA) {
    throw new Error(`不支持的冻结运行配置：${runConfig?.schema_version || "missing"}`);
  }
  if (runConfig.config_digest_algorithm !== "sha256-canonical-json/v1") {
    throw new Error("冻结运行配置 digest 算法不受支持");
  }
  const actual = calculateRunConfigDigest(runConfig);
  if (actual !== runConfig.config_digest) {
    throw new Error(`冻结运行配置 digest 不匹配：${actual} vs ${runConfig.config_digest}`);
  }
  if (runConfig.harness?.id !== "astronstudio" || runConfig.harness?.bundle_id !== "cn.xfyun.acode") {
    throw new Error("冻结运行配置不是 AstronStudio");
  }
  const configuredConcurrency = Number(runConfig.control?.execution_concurrency);
  const maximumConcurrency = Number(runConfig.control?.maximum_execution_concurrency || 8);
  if (
    runConfig.control?.backend !== "electron-cdp"
    || !Number.isInteger(configuredConcurrency)
    || configuredConcurrency < 1
    || configuredConcurrency > 8
    || !Number.isInteger(maximumConcurrency)
    || maximumConcurrency < configuredConcurrency
    || maximumConcurrency > 8
  ) {
    throw new Error("冻结运行配置的 electron-cdp 并发范围无效");
  }
  if (runConfig.execution_policy?.prompt_send_enabled_by_probe !== false) {
    throw new Error("冻结运行配置的 probe 边界无效");
  }
}

export async function resolveExecutionConfig(parsed) {
  const unitRoot = await realpath(resolve(parsed.unitRoot));
  if (!(await stat(unitRoot)).isDirectory()) throw new Error(`unit root 不是目录：${unitRoot}`);
  const manifestPath = join(unitRoot, "manifest.json");
  const manifest = await readJson(manifestPath);
  if (
    manifest?.manifest_kind !== "execution"
    || manifest?.schema_id !== "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
  ) {
    throw new Error("unit root 不是 General E2E execution 包");
  }
  if (manifest.unit?.harness?.id !== "astronstudio") throw new Error("当前执行器只支持 AstronStudio unit");
  const matches = (manifest.tasks || []).filter((item) => item.task_id === parsed.taskId);
  if (matches.length !== 1) throw new Error(`manifest 中任务数量异常：${matches.length}`);
  const task = matches[0];
  const promptPath = await realpath(join(unitRoot, task.prompt.path));
  const taskRoot = await realpath(dirname(promptPath));
  const candidateWorkspace = await realpath(join(unitRoot, task.workspace.path));
  if (!isInside(unitRoot, taskRoot) || !isInside(taskRoot, promptPath)) {
    throw new Error("Prompt 路径越出当前 execution task");
  }
  if (!isInside(taskRoot, candidateWorkspace) || !(await stat(candidateWorkspace)).isDirectory()) {
    throw new Error("候选 workspace 路径无效");
  }
  const prompt = await readFile(promptPath, "utf8");
  const promptSha256 = sha256(prompt);
  if (promptSha256 !== task.prompt.sent_sha256) throw new Error("Prompt digest 与 execution manifest 不一致");

  const runConfigPath = await realpath(resolve(parsed.runConfig));
  const runConfig = await readJson(runConfigPath);
  assertFrozenConfig(runConfig);
  if (
    !runConfig.harness.app_discovery?.identity_verified
    || runConfig.harness.app_discovery.path !== runConfig.harness.app_path
  ) {
    throw new Error("冻结运行配置缺少有效且一致的客户端发现证据");
  }
  const verifiedApp = await verifyDesktopAppPath({
    profile: ASTRONSTUDIO_APP_PROFILE,
    path: runConfig.harness.app_path,
    platform: "darwin",
  });
  if (verifiedApp.path !== runConfig.harness.app_path) {
    throw new Error("冻结的 AstronStudio 路径已改变，拒绝静默切换客户端");
  }
  if (
    manifest.unit.harness.version
    && manifest.unit.harness.version !== runConfig.harness.client_version
  ) {
    throw new Error("execution manifest 与冻结客户端版本不一致");
  }
  if (manifest.unit.model.requested_id !== runConfig.tested_model.display_name) {
    throw new Error("execution manifest 与冻结模型不一致");
  }
  if (
    normalizeReasoning(manifest.unit.model.reasoning_effort)
    !== normalizeReasoning(runConfig.tested_model.reasoning_display)
  ) {
    throw new Error("execution manifest 与冻结推理强度不一致");
  }

  const controlRoot = join(unitRoot, ".general-e2e", "execution", parsed.taskId);
  return {
    ...parsed,
    unitRoot,
    manifestPath,
    manifest,
    task,
    taskRoot,
    candidateWorkspace,
    promptPath,
    prompt,
    promptSha256,
    runConfigPath,
    runConfig,
    controlRoot,
    stateFile: join(controlRoot, "automation-state.json"),
    recordFile: join(controlRoot, "execution-record.json"),
    finalResponseFile: join(controlRoot, "final-response.md"),
    lockFile: join(controlRoot, "driver.lock"),
    uiLockFile: join(unitRoot, ".general-e2e", "astronstudio-ui.lock"),
    stateDatabase: runConfig.state_database.path,
    endpoint: runConfig.control.endpoint,
    appPath: runConfig.harness.app_path,
    expectedModel: runConfig.tested_model.display_name,
    expectedReasoning: runConfig.tested_model.reasoning_display,
    expectedPermission: runConfig.tested_model.permission_display,
  };
}

export function classifyNativeState(session) {
  const state = String(session?.turn_state || session?.status || "").trim().toLowerCase();
  if (state === "completed") return { kind: "completed", businessStatus: "completed" };
  if (state === "error" || state === "failed") {
    return { kind: "failed", businessStatus: "infrastructure_error" };
  }
  if (state === "interrupted" || state === "cancelled" || state === "canceled") {
    return { kind: "failed", businessStatus: "cancelled" };
  }
  if (session?.status === "needs_attention") return { kind: "needs_attention", businessStatus: null };
  if (
    session?.active_turn_id
    || new Set(["running", "starting", "pending", "ready", "created"]).has(state)
  ) {
    return { kind: "running", businessStatus: null };
  }
  return { kind: "unknown", businessStatus: null };
}

export function isBlockingActiveSession(session) {
  const state = String(session?.status || "").trim().toLowerCase();
  return Boolean(session?.active_turn_id)
    || new Set(["running", "starting", "pending", "needs_attention"]).has(state);
}

function baselineMap(state) {
  return new Map((state.session?.baseline || []).map((item) => [item.thread_id, item]));
}

function isChangedFromBaseline(session, state) {
  const baseline = baselineMap(state).get(session.thread_id);
  if (!baseline) return true;
  if (session.turn_id && session.turn_id !== baseline.turn_id) return true;
  return Number(session.updated_at_ms || 0) > Number(baseline.updated_at_ms || 0);
}

export function selectRouteBoundSession(sessions, state, workspace, observedRouteThreadId = null) {
  const routeIds = new Set([
    observedRouteThreadId,
    state.send?.post_send_route_thread_id,
    state.send?.pre_send_route_thread_id,
  ].filter(Boolean));
  const matches = sessions.filter((session) => (
    routeIds.has(session.thread_id)
    && resolve(String(session.cwd || "")) === resolve(workspace)
    && Boolean(session.turn_id)
    && Boolean(session.session_id)
    && session.latest_turn_id === session.turn_id
    && isChangedFromBaseline(session, state)
  ));
  if (matches.length === 1) return { session: matches[0], ambiguous: false };
  return { session: null, ambiguous: matches.length > 1, match_count: matches.length };
}

function createInitialState(config, now) {
  return {
    schema_version: EXECUTION_STATE_SCHEMA,
    driver: { id: "astronstudio-macos", version: EXECUTION_DRIVER_VERSION },
    identity: {
      batch_id: config.manifest.batch_id,
      unit_id: config.manifest.unit_id,
      task_id: config.task.task_id,
      attempt_id: randomUUID(),
    },
    dataset: {
      id: config.manifest.dataset.id,
      digest: config.manifest.dataset.digest,
    },
    phase: "PENDING",
    task_root: config.taskRoot,
    candidate_workspace: config.candidateWorkspace,
    run_config: {
      path: config.runConfigPath,
      config_digest: config.runConfig.config_digest,
    },
    prompt: {
      path: config.promptPath,
      sha256: config.promptSha256,
      send_status: "not_sent",
      sent_at: null,
    },
    send: {
      dispatch_attempt_count: 0,
      dispatch_armed_at: null,
      dispatch_completed_at: null,
      pre_send_route_thread_id: null,
      post_send_route_thread_id: null,
    },
    session: {
      thread_id: null,
      turn_id: null,
      session_id: null,
      cwd: null,
      verified: false,
      baseline: [],
      native_status: null,
      last_observed_at: null,
    },
    client: {
      version: config.runConfig.harness.client_version,
      model: config.expectedModel,
      reasoning: config.expectedReasoning,
      permission: config.expectedPermission,
    },
    execution: {
      business_status: null,
      started_at: now,
      finished_at: null,
      duration_seconds: null,
      agent_duration_seconds: null,
      // General E2E deliberately has no task-level execution deadline. Keep
      // the field for the AstronStudio v1 state envelope, but leave it null so
      // downstream consumers cannot mistake dataset timeout_seconds for a
      // controller-enforced Harness timeout.
      deadline_at: null,
      error: null,
    },
    evidence: {
      final_response_path: null,
      final_response_sha256: null,
    },
    human_assistance: {
      mode: config.manifest.unit.execution_mode,
      operation_count: 0,
      semantic_intervention_count: 0,
    },
    history: [{ phase: "PENDING", at: now, event: "ATTEMPT_CREATED" }],
  };
}

function transition(state, phase, event, detail = {}, now = new Date().toISOString()) {
  state.phase = phase;
  state.history.push({ phase, at: now, event, ...detail });
  return state;
}

function recordFromState(config, state) {
  const missing = ["raw_trace", "transcript", "trace_index", "resource_metrics", "candidate_freeze"];
  if (!state.evidence.final_response_path) missing.push("final_response");
  return {
    schema_id: EXECUTION_RECORD_SCHEMA,
    schema_version: 1,
    identity: { ...state.identity },
    dataset: { ...state.dataset },
    phase: state.phase,
    harness: {
      id: "astronstudio",
      platform: config.manifest.unit.harness.platform,
      version: state.client.version,
    },
    model: {
      requested_id: config.manifest.unit.model.requested_id,
      actual_id: state.client.model,
      reasoning_effort: state.client.reasoning,
      verification_status: "verified",
    },
    execution: {
      business_status: state.execution.business_status,
      started_at: state.execution.started_at,
      finished_at: state.execution.finished_at,
      duration_seconds: state.execution.duration_seconds,
      agent_duration_seconds: state.execution.agent_duration_seconds,
      error: state.execution.error,
    },
    prompt: {
      sha256: state.prompt.sha256,
      send_status: state.prompt.send_status,
      sent_at: state.prompt.sent_at,
    },
    session: {
      thread_id: state.session.thread_id,
      turn_id: state.session.turn_id,
      session_id: state.session.session_id,
      cwd: state.session.cwd,
      verified: state.session.verified,
    },
    evidence: {
      completeness: "partial",
      transcript_path: null,
      trace_index_path: null,
      final_response_path: state.evidence.final_response_path,
      missing,
    },
    candidate: {
      path: relativePosix(config.unitRoot, config.candidateWorkspace),
      frozen_sha256: null,
      frozen_at: null,
      drift_status: "not_frozen",
    },
    resource_metrics_path: null,
    human_assistance: { ...state.human_assistance },
  };
}

async function persist(config, state) {
  await atomicWriteJson(config.stateFile, state);
  await atomicWriteJson(config.recordFile, recordFromState(config, state));
}

function assertStateIdentity(config, state) {
  const expected = {
    batch_id: config.manifest.batch_id,
    unit_id: config.manifest.unit_id,
    task_id: config.task.task_id,
  };
  for (const [key, value] of Object.entries(expected)) {
    if (state.identity?.[key] !== value) throw new Error(`已有状态 ${key} 不匹配`);
  }
  if (state.prompt?.sha256 !== config.promptSha256) throw new Error("已有状态 Prompt digest 不匹配");
  if (state.run_config?.config_digest !== config.runConfig.config_digest) {
    throw new Error("已有状态冻结运行配置 digest 不匹配");
  }
}

function baselineRows(sessions, workspace) {
  return sessions
    .filter((session) => resolve(String(session.cwd || "")) === resolve(workspace))
    .map((session) => ({
      thread_id: session.thread_id,
      turn_id: session.turn_id,
      session_id: session.session_id,
      updated_at_ms: Number(session.updated_at_ms || 0),
    }));
}

async function currentProbe(config, dependencies, fresh) {
  const report = await dependencies.probeAstronStudio({
    appPath: config.appPath,
    stateDb: config.stateDatabase,
    endpoint: config.endpoint,
    endpointExplicit: true,
    output: null,
    configOutput: null,
    timeoutMs: Math.min(config.timeoutMs, 10_000),
  });
  if (!report.ready) throw new Error(`AstronStudio 执行前探针未通过：${report.failed_checks.join(",")}`);
  const current = report.frozen_run_config;
  const frozen = config.runConfig;
  const mismatches = [];
  if (current.harness.client_version !== frozen.harness.client_version) mismatches.push("client_version");
  if (current.control.endpoint !== frozen.control.endpoint) mismatches.push("endpoint");
  if (current.tested_model.display_name !== frozen.tested_model.display_name) mismatches.push("model");
  if (current.tested_model.reasoning_display !== frozen.tested_model.reasoning_display) mismatches.push("reasoning");
  if (current.tested_model.permission_display !== frozen.tested_model.permission_display) mismatches.push("permission");
  if (mismatches.length) throw new Error(`当前 AstronStudio 配置偏离冻结值：${mismatches.join(",")}`);
  const activeCount = report.state_database.active_or_pending_session_count;
  if (fresh && config.managedRunSlots === 1 && activeCount !== 0) {
    throw new Error(`AstronStudio 仍有 ${activeCount ?? "unknown"} 个活动或待处理任务`);
  }
  if (fresh && config.managedRunSlots > 1) {
    const allowed = new Set(config.allowedActiveSessionIds);
    const sessions = await dependencies.queryNativeSessions(config.stateDatabase);
    const activeSessions = sessions.filter(isBlockingActiveSession);
    const unknown = activeSessions.filter((session) => !allowed.has(session.session_id));
    if (unknown.length) {
      throw new Error(`AstronStudio 存在不属于当前队列的活动 session：${unknown.map((item) => item.session_id).join(",")}`);
    }
    if (activeSessions.length >= config.managedRunSlots) {
      throw new Error(`AstronStudio 活动 session 已达到并发上限 ${config.managedRunSlots}`);
    }
  }
  return report;
}

function recordSession(state, session, now) {
  state.session.thread_id = session.thread_id;
  state.session.turn_id = session.turn_id;
  state.session.session_id = session.session_id;
  state.session.cwd = session.cwd;
  state.session.verified = true;
  state.session.native_status = session.status;
  state.session.last_observed_at = now;
}

async function captureIdentity(config, state, dependencies, observedRouteThreadId = null) {
  const deadline = dependencies.nowMilliseconds() + config.identityTimeoutMs;
  while (dependencies.nowMilliseconds() <= deadline) {
    let sessions;
    try {
      sessions = await dependencies.queryNativeSessions(config.stateDatabase);
    } catch (error) {
      const now = dependencies.now();
      state.history.push({
        phase: state.phase,
        at: now,
        event: "NATIVE_IDENTITY_READ_RETRY",
        error: error instanceof Error ? error.message : String(error),
      });
      await persist(config, state);
      await dependencies.sleep(250);
      continue;
    }
    const selected = selectRouteBoundSession(
      sessions,
      state,
      config.candidateWorkspace,
      observedRouteThreadId,
    );
    if (selected.ambiguous) throw new Error("发送后出现多个 route/cwd 匹配的原生会话");
    if (selected.session) {
      const now = dependencies.now();
      recordSession(state, selected.session, now);
      state.prompt.send_status = "sent";
      state.prompt.sent_at ||= state.send.dispatch_completed_at || now;
      transition(state, "RUNNING", "NATIVE_IDENTITY_BOUND", {
        thread_id: selected.session.thread_id,
        turn_id: selected.session.turn_id,
        session_id: selected.session.session_id,
      }, now);
      await persist(config, state);
      return selected.session;
    }
    await dependencies.sleep(250);
  }
  return null;
}

async function persistAttention(config, state, code, message, dependencies) {
  const now = dependencies.now();
  state.prompt.send_status = state.send.dispatch_attempt_count > 0 && !state.session.verified
    ? "uncertain"
    : state.prompt.send_status;
  state.execution.error = { code, message };
  transition(state, "NEEDS_ATTENTION", code, {}, now);
  await persist(config, state);
  return state;
}

async function finalize(config, state, session, classification, dependencies) {
  const now = dependencies.now();
  recordSession(state, session, now);
  let finalResponse = "";
  try {
    finalResponse = await dependencies.queryFinalResponse(
      config.stateDatabase,
      session.thread_id,
      session.turn_id,
    );
  } catch (error) {
    state.history.push({
      phase: state.phase,
      at: now,
      event: "FINAL_RESPONSE_READ_FAILED",
      error: error instanceof Error ? error.message : String(error),
    });
  }
  if (finalResponse) {
    const finalResponseContent = `${finalResponse}\n`;
    await writeFile(config.finalResponseFile, finalResponseContent, "utf8");
    state.evidence.final_response_path = relativePosix(config.unitRoot, config.finalResponseFile);
    state.evidence.final_response_sha256 = sha256(finalResponseContent);
  }
  state.execution.business_status = classification.businessStatus;
  state.execution.finished_at = now;
  state.execution.duration_seconds = Math.max(
    0,
    (Date.parse(now) - Date.parse(state.execution.started_at)) / 1000,
  );
  state.execution.error = classification.kind === "completed"
    ? null
    : {
      code: `ASTRONSTUDIO_TURN_${String(session.turn_state || session.status || "UNKNOWN").toUpperCase()}`,
      message: session.error || `AstronStudio turn 终态：${session.turn_state || session.status}`,
    };
  transition(
    state,
    classification.kind === "completed" ? "COMPLETED" : "FAILED",
    "NATIVE_TERMINAL_OBSERVED",
    { native_status: session.status, turn_state: session.turn_state },
    now,
  );
  await persist(config, state);
  return state;
}

async function observeOnce(config, state, dependencies) {
  const sessions = await dependencies.queryNativeSessions(config.stateDatabase);
  const matches = sessions.filter((session) => (
    session.thread_id === state.session.thread_id
    && session.turn_id === state.session.turn_id
    && session.session_id === state.session.session_id
    && resolve(String(session.cwd || "")) === resolve(config.candidateWorkspace)
  ));
  if (matches.length !== 1) {
    return persistAttention(
      config,
      state,
      "NATIVE_IDENTITY_NOT_UNIQUE",
      `原生 thread/turn/session/cwd 匹配数量异常：${matches.length}`,
      dependencies,
    );
  }
  const session = matches[0];
  if (session.latest_turn_id !== state.session.turn_id) {
    return persistAttention(
      config,
      state,
      "NATIVE_TURN_DRIFT",
      "AstronStudio 原 thread 已出现其他 turn，拒绝把其状态归入当前 attempt",
      dependencies,
    );
  }
  recordSession(state, session, dependencies.now());
  const classification = classifyNativeState(session);
  if (classification.kind === "completed" || classification.kind === "failed") {
    return finalize(config, state, session, classification, dependencies);
  }
  if (classification.kind === "needs_attention") {
    return persistAttention(
      config,
      state,
      "PENDING_INTERACTION",
      "AstronStudio 正在等待授权或用户输入；执行器不会代替被测 Agent 作答",
      dependencies,
    );
  }
  if (classification.kind === "unknown") {
    return persistAttention(
      config,
      state,
      "UNKNOWN_NATIVE_STATUS",
      `无法识别 AstronStudio 原生状态：${session.status || session.turn_state || "missing"}`,
      dependencies,
    );
  }
  transition(state, "RUNNING", "NATIVE_RUNNING_OBSERVED", { native_status: session.status }, dependencies.now());
  await persist(config, state);
  return state;
}

async function waitForTerminal(config, state, dependencies) {
  let lastObservationError = null;
  // There is intentionally no task-level deadline here. The loop ends only
  // at a trusted native terminal state or an explicit NEEDS_ATTENTION result;
  // task.timeout_seconds belongs to the dataset contract, not Harness control.
  for (;;) {
    let result;
    try {
      result = await observeOnce(config, state, dependencies);
      lastObservationError = null;
    } catch (error) {
      lastObservationError = error instanceof Error ? error.message : String(error);
      const now = dependencies.now();
      state.phase = "RUNNING";
      state.history.push({
        phase: "RUNNING",
        at: now,
        event: "NATIVE_STATE_READ_RETRY",
        error: lastObservationError,
      });
      await persist(config, state);
      result = state;
    }
    if (new Set(["COMPLETED", "FAILED", "NEEDS_ATTENTION"]).has(result.phase)) return result;
    await dependencies.sleep(config.pollIntervalMs);
  }
}

async function resumeExecution(config, state, dependencies) {
  assertStateIdentity(config, state);
  if (new Set(["COMPLETED", "FAILED"]).has(state.phase)) return state;
  await currentProbe(config, dependencies, false);
  if (!state.session.verified) {
    const captured = await captureIdentity(
      config,
      state,
      dependencies,
      state.send.post_send_route_thread_id || state.send.pre_send_route_thread_id,
    );
    if (!captured) {
      return persistAttention(
        config,
        state,
        "PROMPT_SEND_UNCERTAIN",
        "无法从已持久化 route/baseline 唯一确认 Prompt 是否提交；禁止重发",
        dependencies,
      );
    }
  }
  if (config.observeOnce) {
    try {
      return await observeOnce(config, state, dependencies);
    } catch (error) {
      return persistAttention(
        config,
        state,
        "NATIVE_STATE_READ_FAILED",
        error instanceof Error ? error.message : String(error),
        dependencies,
      );
    }
  }
  return waitForTerminal(config, state, dependencies);
}

export async function executeSingleTask(config, overrides = {}) {
  const dependencies = {
    probeAstronStudio,
    queryNativeSessions,
    queryFinalResponse,
    discoverMainTarget,
    connectCdp: (url, timeout) => CdpClient.connect(url, timeout),
    prepareExecutionUi,
    fillPrompt,
    clickSend,
    currentThreadId,
    sleep: (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds)),
    now: () => new Date().toISOString(),
    nowMilliseconds: () => Date.now(),
    ...overrides,
  };
  const existing = await readJsonIfPresent(config.stateFile);
  if (existing) {
    if (!config.resume) throw new Error("已有执行状态；必须使用 --resume，禁止创建新 attempt 或重发 Prompt");
    return resumeExecution(config, existing, dependencies);
  }
  if (config.resume) throw new Error("--resume 要求已有 automation-state.json");

  await currentProbe(config, dependencies, true);
  const now = dependencies.now();
  const state = createInitialState(config, now);
  await persist(config, state);
  let client = null;
  try {
    const target = await dependencies.discoverMainTarget(config.endpoint, config.timeoutMs);
    client = await dependencies.connectCdp(target.webSocketDebuggerUrl, config.timeoutMs);
    const prepared = await dependencies.prepareExecutionUi(client, config);
    state.client.ui_verification = prepared.ui;
    state.client.workspace_selection = prepared.workspace;
    state.send.pre_send_route_thread_id = prepared.task.thread_id;
    const sessions = await dependencies.queryNativeSessions(config.stateDatabase);
    state.session.baseline = baselineRows(sessions, config.candidateWorkspace);
    await dependencies.fillPrompt(client, config.prompt, config.timeoutMs);
    state.prompt.send_status = "intent_persisted";
    state.send.dispatch_armed_at = dependencies.now();
    state.send.dispatch_attempt_count = 1;
    transition(state, "PENDING", "PROMPT_DISPATCH_ARMED", {
      route_thread_id: state.send.pre_send_route_thread_id,
      prompt_sha256: state.prompt.sha256,
    }, state.send.dispatch_armed_at);
    await persist(config, state);

    let sendResult;
    try {
      sendResult = await dependencies.clickSend(client);
      if (!sendResult?.clicked) {
        throw new Error(`AstronStudio 发送按钮数量异常：${sendResult?.count ?? "unknown"}`);
      }
      state.send.dispatch_completed_at = dependencies.now();
      state.prompt.send_status = "sent";
      state.prompt.sent_at = state.send.dispatch_completed_at;
      state.send.post_send_route_thread_id = sendResult.thread_id
        || await dependencies.currentThreadId(client);
      transition(state, "RUNNING", "PROMPT_DISPATCH_RETURNED", {
        route_thread_id: state.send.post_send_route_thread_id,
      }, state.send.dispatch_completed_at);
      await persist(config, state);
    } catch (error) {
      state.send.post_send_route_thread_id = await dependencies.currentThreadId(client).catch(() => null);
      const captured = await captureIdentity(
        config,
        state,
        dependencies,
        state.send.post_send_route_thread_id,
      );
      if (!captured) {
        return persistAttention(
          config,
          state,
          "PROMPT_SEND_UNCERTAIN",
          `${error instanceof Error ? error.message : String(error)}；无法唯一确认 Prompt 是否已提交，禁止重发`,
          dependencies,
        );
      }
    }

    if (!state.session.verified) {
      const captured = await captureIdentity(
        config,
        state,
        dependencies,
        state.send.post_send_route_thread_id,
      );
      if (!captured) {
        return persistAttention(
          config,
          state,
          "NATIVE_IDENTITY_UNAVAILABLE_AFTER_SEND",
          "Prompt 已发送，但未唯一绑定 thread/turn/session/cwd；禁止重发",
          dependencies,
        );
      }
    }
    if (config.detachAfterSubmit) return state;
    return await waitForTerminal(config, state, dependencies);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (state.send.dispatch_attempt_count > 0) {
      return persistAttention(
        config,
        state,
        "POST_ARM_DRIVER_ERROR",
        `${message}；Prompt 发送临界点可能已越过，禁止重发`,
        dependencies,
      );
    }
    state.execution.business_status = "infrastructure_error";
    state.execution.finished_at = dependencies.now();
    state.execution.duration_seconds = Math.max(
      0,
      (Date.parse(state.execution.finished_at) - Date.parse(state.execution.started_at)) / 1000,
    );
    state.execution.error = { code: "PRE_SEND_DRIVER_ERROR", message };
    transition(state, "FAILED", "PRE_SEND_DRIVER_ERROR", {}, state.execution.finished_at);
    await persist(config, state);
    return state;
  } finally {
    client?.close();
  }
}

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

async function acquireLock(path, allowStaleRecovery = false, metadata = {}) {
  await mkdir(dirname(path), { recursive: true });
  let handle;
  try {
    handle = await open(path, "wx", 0o600);
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    const existing = await readJsonIfPresent(path).catch(() => null);
    if (!allowStaleRecovery || processIsAlive(Number(existing?.pid))) {
      throw new Error(`执行锁已存在：${path}`);
    }
    await rm(path, { force: true });
    handle = await open(path, "wx", 0o600);
  }
  await handle.writeFile(`${JSON.stringify({
    pid: process.pid,
    started_at: new Date().toISOString(),
    ...metadata,
  })}\n`);
  return async () => {
    await handle.close().catch(() => {});
    await rm(path, { force: true });
  };
}

export async function main(argv = process.argv.slice(2), overrides = {}) {
  let parsed;
  try {
    parsed = parseArgs(argv);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    console.error(usage());
    return 2;
  }
  if (parsed.help) {
    console.log(usage());
    return 0;
  }
  if (process.platform !== "darwin" && !overrides.allowNonDarwin) {
    console.error("本入口只支持 AstronStudio macOS；Windows 由 G5 的原生入口实现");
    return 2;
  }
  const releaseLocks = [];
  try {
    const config = await resolveExecutionConfig(parsed);
    releaseLocks.push(await acquireLock(config.uiLockFile, parsed.resume, {
      kind: "astronstudio-ui",
      batch_id: config.manifest.batch_id,
      unit_id: config.manifest.unit_id,
      task_id: config.task.task_id,
    }));
    releaseLocks.push(await acquireLock(config.lockFile, parsed.resume, {
      kind: "task-driver",
      batch_id: config.manifest.batch_id,
      unit_id: config.manifest.unit_id,
      task_id: config.task.task_id,
    }));
    const state = await executeSingleTask(config, overrides.dependencies || {});
    console.log(JSON.stringify({
      phase: state.phase,
      identity: state.identity,
      prompt: state.prompt,
      session: state.session,
      execution: state.execution,
      state_file: config.stateFile,
      execution_record: config.recordFile,
    }, null, 2));
    if (state.phase === "COMPLETED") return 0;
    if (state.phase === "RUNNING") return 4;
    if (state.phase === "NEEDS_ATTENTION") return 3;
    return 2;
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return 2;
  } finally {
    for (const releaseLock of releaseLocks.reverse()) await releaseLock().catch(() => {});
  }
}

let invokedPath = process.argv[1] ? resolve(process.argv[1]) : null;
let modulePath = fileURLToPath(import.meta.url);
try {
  if (invokedPath) invokedPath = await realpath(invokedPath);
  modulePath = await realpath(modulePath);
} catch {
  // Normal comparison below remains false when either path disappears.
}
if (invokedPath && invokedPath === modulePath) process.exitCode = await main();
