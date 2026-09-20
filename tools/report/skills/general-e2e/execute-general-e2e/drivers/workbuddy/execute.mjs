#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdir, open, readFile, realpath, rename, rm, stat, writeFile } from "node:fs/promises";
import { homedir, hostname } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_EXTENSION_DATA_ROOT,
  DEFAULT_SESSION_DB,
  inspectWorkBuddyMacos,
} from "./probe.mjs";
import {
  selectWorkBuddyNativeBinding,
  snapshotWorkBuddyNativeBaseline,
} from "./native-binding.mjs";
import {
  selectWorkBuddyRuntimeBinding,
  snapshotWorkBuddyRuntimeBaseline,
} from "./runtime-binding.mjs";
import { buildWorkBuddyExecutionState } from "./state.mjs";
import {
  WorkBuddyCdpClient,
  assertWorkBuddyRuntimeSupport,
  assertWorkBuddyUiConfiguration,
  assertWorkBuddyUiIdle,
  createFreshWorkBuddyTask,
  discoverWorkBuddyMainTarget,
  dispatchWorkBuddyPrompt,
  fillWorkBuddyPrompt,
  readWorkBuddyUi,
  selectWorkBuddyWorkspace,
} from "./ui.mjs";

export const WORKBUDDY_EXECUTION_JOURNAL_SCHEMA =
  "wildclawbench.general-e2e-workbuddy-dispatch-journal/v1";
export const WORKBUDDY_EXECUTION_DRIVER_VERSION = "0.2.0";
const PROCESS_STARTED_AT = new Date().toISOString();
const PROCESS_START_IDENTITY = `${hostname()}:${process.pid}:${PROCESS_STARTED_AT}:${randomUUID()}`;

function usage() {
  return `WorkBuddy General E2E macOS 单题执行器

用法：
  node drivers/workbuddy/execute.mjs \
    --unit-root /absolute/extracted-unit \
    --task-id <完整任务ID> \
    --endpoint http://127.0.0.1:<端口> \
    --expected-permission <full-access|default-sandbox> [选项]

选项：
  --app-path <WorkBuddy.app>       可选；省略时只读发现
  --expected-model <UI显示值>      默认读取 manifest.unit.model.requested_id
  --session-db <vscdb>            默认 WorkBuddy codebuddy-sessions.vscdb
  --data-root <目录>               默认 WorkBuddyExtension/Data
  --resume                         恢复同一 attempt；dispatch_attempt_count=1 时禁止重发
  --detach-after-submit            绑定 conversation/request/cwd 后退出
  --observe-once                   仅恢复后观察一次原生状态
  --timeout-ms <毫秒>              UI 单步超时，默认 30000
  --identity-timeout-ms <毫秒>     发送后原生绑定时限，默认 120000
  --poll-interval-ms <毫秒>        原生终态轮询间隔，默认 1000
  -h, --help                       显示帮助

入口不会启动、重启或退出 WorkBuddy，也不会自动切换模型/权限。它只在精确回读
完整 Workspace、模型和权限后填入 Prompt；dispatch journal 落盘后最多点击发送一次。`;
}

function positiveInteger(value, label) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`${label} 必须是正整数`);
  return parsed;
}

function endpointOrigin(value) {
  const endpoint = new URL(value);
  if (
    endpoint.protocol !== "http:"
    || !new Set(["127.0.0.1", "localhost", "[::1]"]).has(endpoint.hostname)
    || !endpoint.port
    || endpoint.pathname !== "/"
    || endpoint.search
    || endpoint.hash
    || endpoint.username
    || endpoint.password
  ) {
    throw new Error("--endpoint 必须是带显式端口的 loopback http 根地址");
  }
  return endpoint.origin;
}

export function parseArgs(argv) {
  const values = {
    unitRoot: "",
    taskId: "",
    endpoint: "",
    appPath: "",
    expectedModel: "",
    expectedPermission: "",
    sessionDb: DEFAULT_SESSION_DB,
    dataRoot: DEFAULT_EXTENSION_DATA_ROOT,
    resume: false,
    detachAfterSubmit: false,
    observeOnce: false,
    timeoutMs: 30_000,
    identityTimeoutMs: 120_000,
    pollIntervalMs: 1_000,
    help: false,
  };
  const valued = new Map([
    ["--unit-root", "unitRoot"],
    ["--task-id", "taskId"],
    ["--endpoint", "endpoint"],
    ["--app-path", "appPath"],
    ["--expected-model", "expectedModel"],
    ["--expected-permission", "expectedPermission"],
    ["--session-db", "sessionDb"],
    ["--data-root", "dataRoot"],
    ["--timeout-ms", "timeoutMs"],
    ["--identity-timeout-ms", "identityTimeoutMs"],
    ["--poll-interval-ms", "pollIntervalMs"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else if (arg === "--resume") values.resume = true;
    else if (arg === "--detach-after-submit") values.detachAfterSubmit = true;
    else if (arg === "--observe-once") values.observeOnce = true;
    else {
      const key = valued.get(arg);
      if (!key) throw new Error(`未知选项：${arg}`);
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      values[key] = new Set(["timeoutMs", "identityTimeoutMs", "pollIntervalMs"]).has(key)
        ? positiveInteger(value, arg)
        : value;
      index += 1;
    }
  }
  if (values.endpoint) values.endpoint = endpointOrigin(values.endpoint);
  if (values.observeOnce && !values.resume) throw new Error("--observe-once 必须与 --resume 一起使用");
  if (values.observeOnce && values.detachAfterSubmit) {
    throw new Error("--observe-once 与 --detach-after-submit 不能同时使用");
  }
  if (values.identityTimeoutMs < 120_000 || values.identityTimeoutMs > 180_000) {
    throw new Error("--identity-timeout-ms 必须在 120000–180000 之间");
  }
  if (!values.help && (!values.unitRoot || !values.taskId || !values.endpoint || !values.expectedPermission)) {
    throw new Error("必须指定 --unit-root、--task-id、--endpoint 和 --expected-permission");
  }
  if (values.expectedPermission && !new Set(["full-access", "default-sandbox"]).has(values.expectedPermission)) {
    throw new Error("--expected-permission 仅支持 full-access 或 default-sandbox");
  }
  return values;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function isInside(root, path) {
  const value = relative(root, path);
  return value === "" || (!value.startsWith("..") && !isAbsolute(value));
}

function assertSafeTaskId(value) {
  const taskId = String(value || "");
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(taskId) || taskId === "." || taskId === "..") {
    throw new Error("task_id 不是安全的 execution 路径段");
  }
  return taskId;
}

function resolveManifestRelativePath(unitRoot, rawPath, label) {
  if (
    typeof rawPath !== "string"
    || !rawPath
    || rawPath.includes("\0")
    || isAbsolute(rawPath)
    || /^[A-Za-z]:[\\/]/u.test(rawPath)
    || rawPath.split(/[\\/]+/u).some((segment) => segment === "..")
  ) {
    throw new Error(`${label} 必须是 unit root 内不含 .. 的相对路径`);
  }
  const target = resolve(unitRoot, rawPath);
  if (!isInside(unitRoot, target)) throw new Error(`${label} 越出 unit root`);
  return target;
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function assertNoSymlinkPath(root, target, label) {
  const canonicalRoot = await realpath(resolve(root));
  const lexicalTarget = resolve(target);
  if (!isInside(canonicalRoot, lexicalTarget)) throw new Error(`${label} 越出 unit root`);
  let current = canonicalRoot;
  for (const segment of relative(canonicalRoot, lexicalTarget).split(/[\\/]+/u).filter(Boolean)) {
    current = join(current, segment);
    try {
      const info = await lstat(current);
      if (info.isSymbolicLink()) throw new Error(`${label} 路径包含符号链接：${current}`);
    } catch (error) {
      if (error?.code === "ENOENT") return;
      throw error;
    }
  }
}

async function readJsonIfPresent(path, trustedRoot = null) {
  if (trustedRoot) await assertNoSymlinkPath(trustedRoot, path, "状态文件");
  try {
    return await readJson(path);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

async function atomicWriteJson(path, value, trustedRoot = null) {
  if (trustedRoot) await assertNoSymlinkPath(trustedRoot, path, "状态写入目标");
  await mkdir(dirname(path), { recursive: true });
  if (trustedRoot) await assertNoSymlinkPath(trustedRoot, dirname(path), "状态写入目录");
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  try {
    await rename(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

export async function resolveExecutionConfig(parsed) {
  const unitRoot = await realpath(resolve(parsed.unitRoot));
  if (!(await stat(unitRoot)).isDirectory()) throw new Error("unit root 不是目录");
  const manifestPath = join(unitRoot, "manifest.json");
  await assertNoSymlinkPath(unitRoot, manifestPath, "manifest");
  const manifest = await readJson(manifestPath);
  if (
    manifest?.manifest_kind !== "execution"
    || manifest?.schema_id !== "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
    || manifest?.unit?.harness?.id !== "workbuddy"
  ) {
    throw new Error("unit root 不是 WorkBuddy General E2E execution 包");
  }
  if (!/^macos(?:-[a-z0-9-]+)?$/u.test(manifest.unit.harness.platform || "")) {
    throw new Error("WORKBUDDY_PLATFORM_UNSUPPORTED");
  }
  const matches = (manifest.tasks || []).filter((item) => item.task_id === parsed.taskId);
  if (matches.length !== 1) throw new Error(`manifest 中任务数量异常：${matches.length}`);
  const task = matches[0];
  const taskId = assertSafeTaskId(task.task_id);
  const lexicalTaskRoot = join(unitRoot, "execution", "tasks", taskId);
  const lexicalPromptPath = resolveManifestRelativePath(unitRoot, task.prompt?.path, "Prompt path");
  const lexicalWorkspace = resolveManifestRelativePath(unitRoot, task.workspace?.path, "Workspace path");
  for (const [target, label] of [
    [lexicalTaskRoot, "execution task root"],
    [lexicalPromptPath, "Prompt path"],
    [lexicalWorkspace, "Workspace path"],
  ]) {
    await assertNoSymlinkPath(unitRoot, target, label);
  }
  const taskRoot = await realpath(lexicalTaskRoot);
  const promptPath = await realpath(lexicalPromptPath);
  const candidateWorkspace = await realpath(lexicalWorkspace);
  if (!isInside(taskRoot, promptPath) || !isInside(taskRoot, candidateWorkspace)) {
    throw new Error("Prompt 或 Workspace 越出 execution task");
  }
  if (!(await stat(candidateWorkspace)).isDirectory()) throw new Error("候选 Workspace 不是目录");
  const prompt = await readFile(promptPath, "utf8");
  const promptSha256 = sha256(prompt);
  if (promptSha256 !== task.prompt.sent_sha256) throw new Error("Prompt digest 与 manifest 不一致");
  const expectedModel = parsed.expectedModel || String(manifest.unit.model?.requested_id || "").trim();
  if (!expectedModel) throw new Error("缺少 WorkBuddy 预期模型 UI 显示值");
  const controlRoot = join(unitRoot, ".general-e2e", "execution", parsed.taskId, "workbuddy");
  await assertNoSymlinkPath(unitRoot, controlRoot, "WorkBuddy control root");
  await mkdir(controlRoot, { recursive: true });
  await assertNoSymlinkPath(unitRoot, controlRoot, "WorkBuddy control root");
  return {
    ...parsed,
    unitRoot,
    manifest,
    task,
    taskRoot,
    candidateWorkspace,
    promptPath,
    prompt,
    promptSha256,
    expectedModel,
    expectedPermission: parsed.expectedPermission,
    controlRoot,
    journalFile: join(controlRoot, "dispatch-journal.json"),
    stateFile: join(controlRoot, "execution-state.json"),
    bindingFile: join(controlRoot, "native-binding.json"),
    lockFile: join(controlRoot, "driver.lock"),
    uiLockFile: join(unitRoot, ".general-e2e", "workbuddy-ui.lock"),
    runTimeoutSeconds: Number(task.timeout_seconds || 3600),
  };
}

function createJournal(config, runtime, nativeIdleEvidence, now) {
  return {
    schema_version: WORKBUDDY_EXECUTION_JOURNAL_SCHEMA,
    driver: { id: "workbuddy-macos-general", version: WORKBUDDY_EXECUTION_DRIVER_VERSION },
    identity: {
      batch_id: config.manifest.batch_id,
      unit_id: config.manifest.unit_id,
      task_id: config.task.task_id,
      attempt_id: randomUUID(),
    },
    dataset: { id: config.manifest.dataset.id, digest: config.manifest.dataset.digest },
    phase: "PENDING",
    task_root: config.taskRoot,
    candidate_workspace: config.candidateWorkspace,
    prompt: {
      path: config.promptPath,
      sha256: config.promptSha256,
      send_status: "not_sent",
      sent_at: null,
    },
    expected_ui: {
      workspace: config.candidateWorkspace,
      model: config.expectedModel,
      permission: config.expectedPermission,
    },
    verified_ui: null,
    runtime: {
      app_path: runtime.application.path,
      expected_client_version: config.manifest.unit.harness.version || null,
      client_version: runtime.application.version,
      client_version_match: config.manifest.unit.harness.version
        ? config.manifest.unit.harness.version === runtime.application.version
        : null,
      compatibility_status: runtime.application.compatibility_status || "unverified",
      installation_variant: runtime.application.installation_variant,
      endpoint: config.endpoint,
    },
    preflight: {
      native_sessions: nativeIdleEvidence,
      ui_idle: null,
    },
    send: {
      dispatch_attempt_count: 0,
      dispatch_armed_at: null,
      dispatch_returned_at: null,
      pre_send_dom_conversation_id: null,
      post_send_dom_conversation_id: null,
      error: null,
    },
    native: {
      baseline: null,
      conversation_id: null,
      request_id: null,
      cwd: null,
      last_observed_at: null,
    },
    execution: {
      started_at: now,
      deadline_at: new Date(Date.parse(now) + config.runTimeoutSeconds * 1000).toISOString(),
      error: null,
    },
    history: [{ phase: "PENDING", event: "ATTEMPT_CREATED", at: now }],
  };
}

function assertJournalMatches(config, journal) {
  if (journal.schema_version !== WORKBUDDY_EXECUTION_JOURNAL_SCHEMA) throw new Error("dispatch journal schema 不受支持");
  const mismatches = [];
  if (journal.identity?.batch_id !== config.manifest.batch_id) mismatches.push("batch_id");
  if (journal.identity?.unit_id !== config.manifest.unit_id) mismatches.push("unit_id");
  if (journal.identity?.task_id !== config.task.task_id) mismatches.push("task_id");
  if (journal.prompt?.sha256 !== config.promptSha256) mismatches.push("prompt_sha256");
  if (journal.candidate_workspace !== config.candidateWorkspace) mismatches.push("workspace");
  if (journal.runtime?.endpoint !== config.endpoint) mismatches.push("endpoint");
  if (journal.expected_ui?.model !== config.expectedModel) mismatches.push("model");
  if (journal.expected_ui?.permission !== config.expectedPermission) mismatches.push("permission");
  if (mismatches.length) throw new Error(`dispatch journal 与本次调用不一致：${mismatches.join(",")}`);
}

function transition(journal, phase, event, now, detail = {}) {
  journal.phase = phase;
  journal.history.push({ phase, event, at: now, ...detail });
}

async function persistJournal(config, journal) {
  await atomicWriteJson(config.journalFile, journal, config.unitRoot);
}

async function defaultInspectRuntime(config) {
  const report = await inspectWorkBuddyMacos({
    appPath: config.appPath,
    sessionDb: config.sessionDb,
    extensionDataRoot: config.dataRoot,
    extensionLogRoot: join(homedir(), "Library", "Application Support", "WorkBuddyExtension", "Logs", "VSCode"),
    appLogRoot: join(homedir(), "Library", "Application Support", "WorkBuddy", "logs"),
    endpoint: config.endpoint,
    timeoutMs: Math.min(config.timeoutMs, 10_000),
  });
  if (
    report.status !== "PASS"
    || report.process?.running !== true
    || report.cdp?.status !== "observed"
    || report.cdp.endpoint !== config.endpoint
  ) {
    throw new Error(`WorkBuddy 执行前只读检查未通过：status=${report.status}; process=${report.process?.running}; cdp=${report.cdp?.status}`);
  }
  return report;
}

const NATIVE_TERMINAL_STATES = new Set([
  "complete", "completed", "success", "succeeded",
  "failed", "failure", "error", "errored",
  "cancelled", "canceled", "aborted", "interrupted",
]);

export function assertWorkBuddyNativeIdle(report) {
  const sessionIndex = report?.native_sources?.session_index;
  if (sessionIndex?.status !== "observed" || !Array.isArray(sessionIndex.sessions)) {
    throw new Error("WorkBuddy 原生 session index 不可用，禁止首次发送");
  }
  const statusCounts = {};
  let blockingCount = 0;
  for (const session of sessionIndex.sessions) {
    const status = String(session?.status || "missing").trim().toLowerCase() || "missing";
    statusCounts[status] = (statusCounts[status] || 0) + 1;
    if (!NATIVE_TERMINAL_STATES.has(status)) blockingCount += 1;
  }
  const evidence = {
    verified: blockingCount === 0,
    source_status: sessionIndex.status,
    source_size: sessionIndex.metadata?.size ?? null,
    source_modified_at: sessionIndex.metadata?.modified_at ?? null,
    captured_at: report.captured_at || null,
    session_count: sessionIndex.sessions.length,
    blocking_session_count: blockingCount,
    status_counts: Object.fromEntries(Object.entries(statusCounts).sort(([left], [right]) => left.localeCompare(right))),
  };
  if (blockingCount > 0) {
    throw new Error(`WorkBuddy 存在活动或未知原生 session：${blockingCount}`);
  }
  return evidence;
}

async function defaultPrepareUi(config) {
  const target = await discoverWorkBuddyMainTarget(config.endpoint, config.timeoutMs);
  const client = await WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl, config.timeoutMs);
  try {
    const initialUi = await readWorkBuddyUi(client);
    const uiIdle = assertWorkBuddyUiIdle(initialUi);
    await createFreshWorkBuddyTask(client, config.timeoutMs);
    await selectWorkBuddyWorkspace(client, config.candidateWorkspace, config.timeoutMs);
    const ui = await readWorkBuddyUi(client);
    assertWorkBuddyUiConfiguration(ui, {
      workspace: config.candidateWorkspace,
      model: config.expectedModel,
      permission: config.expectedPermission,
    });
    return { handle: client, ui, ui_idle: uiIdle };
  } catch (error) {
    client.close();
    throw error;
  }
}

async function defaultConnectRuntime(config) {
  const target = await discoverWorkBuddyMainTarget(config.endpoint, config.timeoutMs);
  return WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl, config.timeoutMs);
}

export async function closeWorkBuddyUiHandle(handle) {
  await handle?.close();
}

async function writeBindingEvidence(config, journal, binding) {
  const evidence = {
    schema_version: "wildclawbench.general-e2e-workbuddy-native-binding/v2",
    source_kind: binding.source_kind || "workbuddy-native-history",
    identity: journal.identity,
    workspace: config.candidateWorkspace,
    conversation_id: binding.session_snapshot.conversation_id,
    request_id: binding.history.binding.request_id,
    source_artifacts: binding.artifacts,
    runtime_snapshot: binding.runtime_snapshot || null,
  };
  await atomicWriteJson(config.bindingFile, evidence, config.unitRoot);
  const bytes = await readFile(config.bindingFile);
  return [{
    path: relative(config.unitRoot, config.bindingFile).split("\\").join("/"),
    sha256: sha256(bytes),
    size: bytes.length,
  }];
}

async function buildAndPersistPublicState(config, journal, binding, bindingEvidence) {
  const state = buildWorkBuddyExecutionState({
    identity: journal.identity,
    dataset: journal.dataset,
    platform: config.manifest.unit.harness.platform,
    taskRoot: config.taskRoot,
    candidateWorkspace: config.candidateWorkspace,
    prompt: journal.prompt,
    send: journal.send,
    sessionSnapshot: binding.session_snapshot,
    history: binding.history,
    bindingEvidence,
  });
  state.extensions.client = {
    version: journal.runtime.client_version,
    model: journal.verified_ui?.model || null,
    permission: journal.verified_ui?.permission || null,
    reasoning_effort: null,
  };
  await atomicWriteJson(config.stateFile, state, config.unitRoot);
  return state;
}

async function captureBinding(config, journal, dependencies, runtimeClient = null) {
  const deadline = dependencies.nowMilliseconds() + config.identityTimeoutMs;
  let lastError = null;
  while (dependencies.nowMilliseconds() <= deadline) {
    try {
      const selected = await dependencies.selectBinding({
        sessionDb: config.sessionDb,
        dataRoot: config.dataRoot,
        workspace: config.candidateWorkspace,
        baseline: journal.native.baseline,
        boundConversationId: journal.native.conversation_id,
        boundRequestId: journal.native.request_id,
      }, { runtimeClient, promptSha256: config.promptSha256 });
      if (selected.ambiguous) throw new Error(`原生 conversation/request 绑定不唯一：${selected.match_count}`);
      if (selected.binding) return selected.binding;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await dependencies.sleep(250);
  }
  if (lastError) journal.history.push({
    phase: journal.phase,
    event: "NATIVE_BINDING_LAST_ERROR",
    at: dependencies.now(),
    error: lastError,
  });
  return null;
}

async function bindAndObserve(config, journal, dependencies, runtimeClient = null) {
  let binding = await captureBinding(config, journal, dependencies, runtimeClient);
  if (!binding) {
    journal.prompt.send_status = "uncertain";
    journal.execution.error = {
      code: "WORKBUDDY_PROMPT_SEND_UNCERTAIN",
      message: "无法唯一绑定 conversation/request/cwd；禁止重发",
    };
    transition(journal, "NEEDS_ATTENTION", "NATIVE_BINDING_UNAVAILABLE", dependencies.now());
    await persistJournal(config, journal);
    return { journal, state: null };
  }
  if (binding.history.prompt.sha256 !== config.promptSha256) {
    journal.execution.error = {
      code: "WORKBUDDY_PROMPT_HASH_MISMATCH",
      message: "原生历史 Prompt SHA 与 execution manifest 不一致",
    };
    transition(journal, "NEEDS_ATTENTION", "PROMPT_HASH_MISMATCH", dependencies.now());
    await persistJournal(config, journal);
    return { journal, state: null };
  }
  journal.native.conversation_id = binding.session_snapshot.conversation_id;
  journal.native.request_id = binding.history.binding.request_id;
  journal.native.cwd = binding.session_snapshot.cwd;
  journal.native.last_observed_at = dependencies.now();
  journal.prompt.send_status = "sent";
  journal.prompt.sent_at ||= journal.send.dispatch_returned_at || journal.send.dispatch_armed_at;
  let evidence = await writeBindingEvidence(config, journal, binding);
  let state = await buildAndPersistPublicState(config, journal, binding, evidence);
  transition(journal, state.phase, "NATIVE_BINDING_OBSERVED", dependencies.now(), {
    conversation_id: journal.native.conversation_id,
    request_id: journal.native.request_id,
  });
  await persistJournal(config, journal);
  if (config.detachAfterSubmit || config.observeOnce || state.phase !== "RUNNING") return { journal, state };

  for (;;) {
    if (dependencies.nowMilliseconds() >= Date.parse(journal.execution.deadline_at)) {
      journal.execution.error = {
        code: "WORKBUDDY_EXECUTION_DEADLINE_REACHED",
        message: "执行时限已到；未实现可信停止确认，保留现场且禁止重发",
      };
      transition(journal, "NEEDS_ATTENTION", "EXECUTION_DEADLINE_REACHED", dependencies.now());
      state.phase = "NEEDS_ATTENTION";
      state.execution.business_status = null;
      state.execution.error = { ...journal.execution.error };
      state.execution.finished_at = null;
      state.execution.duration_seconds = null;
      await atomicWriteJson(config.stateFile, state, config.unitRoot);
      await persistJournal(config, journal);
      return { journal, state };
    }
    await dependencies.sleep(config.pollIntervalMs);
    const selected = await dependencies.selectBinding({
      sessionDb: config.sessionDb,
      dataRoot: config.dataRoot,
      workspace: config.candidateWorkspace,
      baseline: journal.native.baseline,
      boundConversationId: journal.native.conversation_id,
      boundRequestId: journal.native.request_id,
    }, { runtimeClient, promptSha256: config.promptSha256 });
    if (!selected.binding || selected.ambiguous) {
      journal.execution.error = {
        code: "WORKBUDDY_NATIVE_BINDING_DRIFT",
        message: `已绑定的 conversation/request/cwd 不再唯一：${selected.match_count}`,
      };
      transition(journal, "NEEDS_ATTENTION", "NATIVE_BINDING_DRIFT", dependencies.now());
      await persistJournal(config, journal);
      return { journal, state };
    }
    binding = selected.binding;
    journal.native.last_observed_at = dependencies.now();
    evidence = await writeBindingEvidence(config, journal, binding);
    state = await buildAndPersistPublicState(config, journal, binding, evidence);
    transition(journal, state.phase, "NATIVE_STATE_OBSERVED", dependencies.now());
    await persistJournal(config, journal);
    if (state.phase !== "RUNNING") return { journal, state };
  }
}

export async function executeWorkBuddyTask(config, overrides = {}) {
  const dependencies = {
    inspectRuntime: defaultInspectRuntime,
    prepareUi: defaultPrepareUi,
    fillPrompt: (handle, prompt) => fillWorkBuddyPrompt(handle, prompt, config.timeoutMs),
    dispatchPrompt: (handle) => dispatchWorkBuddyPrompt(handle, config.timeoutMs),
    snapshotBaseline: snapshotWorkBuddyNativeBaseline,
    snapshotRuntimeBaseline: snapshotWorkBuddyRuntimeBaseline,
    connectRuntime: defaultConnectRuntime,
    selectBinding: async (args, runtime = {}) => {
      if (runtime.runtimeClient) {
        try {
          const selected = await selectWorkBuddyRuntimeBinding({
            client: runtime.runtimeClient,
            workspace: args.workspace,
            baseline: args.baseline?.runtime,
            boundConversationId: args.boundConversationId,
            boundRequestId: args.boundRequestId,
            promptSha256: runtime.promptSha256 || null,
          });
          if (selected.binding || selected.ambiguous) return selected;
        } catch (error) {
          if (runtime.runtimeOnly === true) throw error;
        }
      }
      return selectWorkBuddyNativeBinding(args);
    },
    closeUi: closeWorkBuddyUiHandle,
    sleep: (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds)),
    now: () => new Date().toISOString(),
    nowMilliseconds: () => Date.now(),
    ...overrides,
  };
  let journal = await readJsonIfPresent(config.journalFile, config.unitRoot);
  let runtimeClient = null;
  if (journal) {
    if (!config.resume) throw new Error("已有 dispatch journal；必须使用 --resume，禁止新建 attempt 或重发");
    assertJournalMatches(config, journal);
    if (new Set(["COMPLETED", "FAILED"]).has(journal.phase)) {
      return { journal, state: await readJsonIfPresent(config.stateFile, config.unitRoot) };
    }
    const runtime = await dependencies.inspectRuntime(config);
    if (journal.send.dispatch_attempt_count === 1) {
      try {
        runtimeClient = await dependencies.connectRuntime(config);
      } catch {
        runtimeClient = null;
      }
      try {
        return await bindAndObserve(config, journal, dependencies, runtimeClient);
      } finally {
        await dependencies.closeUi(runtimeClient);
      }
    }
    if (journal.send.dispatch_attempt_count !== 0 || journal.prompt.send_status !== "not_sent") {
      throw new Error("dispatch journal 发送边界无效，拒绝恢复");
    }
    journal.preflight ||= { native_sessions: null, ui_idle: null };
    journal.preflight.native_sessions = assertWorkBuddyNativeIdle(runtime);
  } else {
    if (config.resume) throw new Error("--resume 要求已有 dispatch-journal.json");
    const runtime = await dependencies.inspectRuntime(config);
    const nativeIdle = assertWorkBuddyNativeIdle(runtime);
    journal = createJournal(config, runtime, nativeIdle, dependencies.now());
    await persistJournal(config, journal);
  }

  let handle = null;
  try {
    const prepared = await dependencies.prepareUi(config);
    handle = prepared.handle;
    if (prepared.ui_idle?.verified !== true) throw new Error("WorkBuddy UI 空闲证据缺失");
    journal.preflight.ui_idle = prepared.ui_idle;
    journal.verified_ui = assertWorkBuddyUiConfiguration(prepared.ui, journal.expected_ui);
    journal.send.pre_send_dom_conversation_id = prepared.ui.selected_conversation_id || null;
    journal.native.baseline = await dependencies.snapshotBaseline({
      sessionDb: config.sessionDb,
      dataRoot: config.dataRoot,
      workspace: config.candidateWorkspace,
    });
    try {
      journal.native.baseline.runtime = await dependencies.snapshotRuntimeBaseline(
        handle,
        config.candidateWorkspace,
      );
    } catch (error) {
      journal.native.baseline.runtime = null;
      journal.history.push({
        phase: journal.phase,
        event: "RUNTIME_API_BASELINE_UNAVAILABLE",
        at: dependencies.now(),
        error: error instanceof Error ? error.message : String(error),
      });
    }
    await dependencies.fillPrompt(handle, config.prompt);
    journal.prompt.send_status = "intent_persisted";
    journal.send.dispatch_attempt_count = 1;
    journal.send.dispatch_armed_at = dependencies.now();
    transition(journal, "PENDING", "PROMPT_DISPATCH_ARMED", journal.send.dispatch_armed_at, {
      prompt_sha256: journal.prompt.sha256,
    });
    await persistJournal(config, journal);

    try {
      const result = await dependencies.dispatchPrompt(handle);
      journal.send.dispatch_returned_at = dependencies.now();
      journal.send.post_send_dom_conversation_id = result?.selected_conversation_id || null;
      journal.prompt.send_status = "sent";
      journal.prompt.sent_at = journal.send.dispatch_returned_at;
      transition(journal, "RUNNING", "PROMPT_DISPATCH_RETURNED", journal.send.dispatch_returned_at);
      await persistJournal(config, journal);
    } catch (error) {
      journal.send.error = error instanceof Error ? error.message : String(error);
      transition(journal, "RUNNING", "PROMPT_DISPATCH_THROWN", dependencies.now());
      await persistJournal(config, journal);
    }
    return await bindAndObserve(config, journal, dependencies, handle);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (journal.send.dispatch_attempt_count > 0) {
      journal.prompt.send_status = journal.native.conversation_id ? "sent" : "uncertain";
      journal.execution.error = { code: "WORKBUDDY_POST_ARM_DRIVER_ERROR", message: `${message}；禁止重发` };
      transition(journal, "NEEDS_ATTENTION", "POST_ARM_DRIVER_ERROR", dependencies.now());
    } else {
      journal.execution.error = { code: "WORKBUDDY_PRE_SEND_DRIVER_ERROR", message };
      transition(journal, "FAILED", "PRE_SEND_DRIVER_ERROR", dependencies.now());
    }
    await persistJournal(config, journal);
    return { journal, state: await readJsonIfPresent(config.stateFile, config.unitRoot) };
  } finally {
    try {
      await dependencies.closeUi(handle);
    } catch {
      // Cleanup must support both synchronous and asynchronous clients and
      // must not replace the execution result with a disconnect error.
    }
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

async function acquireLock(path, allowStaleRecovery, metadata, trustedRoot) {
  await assertNoSymlinkPath(trustedRoot, path, "owner lock");
  await mkdir(dirname(path), { recursive: true });
  await assertNoSymlinkPath(trustedRoot, dirname(path), "owner lock 目录");
  let handle;
  try {
    handle = await open(path, "wx", 0o600);
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    await assertNoSymlinkPath(trustedRoot, path, "owner lock");
    const existing = await readJsonIfPresent(path, trustedRoot).catch(() => null);
    const staleCandidate = allowStaleRecovery
      && existing?.host === hostname()
      && !processIsAlive(Number(existing?.pid));
    if (staleCandidate) {
      throw new Error(`检测到陈旧执行锁；为避免并发接管竞态，禁止自动回收：${path}`);
    }
    throw new Error(`执行锁已存在：${path}`);
  }
  const owner = {
    pid: process.pid,
    started_at: new Date().toISOString(),
    owner_token: randomUUID(),
    ...metadata,
  };
  await handle.writeFile(`${JSON.stringify(owner)}\n`);
  const ownedStat = await handle.stat({ bigint: true });
  return async () => {
    await handle.close().catch(() => {});
    const current = await lstat(path, { bigint: true }).catch(() => null);
    if (current && !current.isSymbolicLink() && current.dev === ownedStat.dev && current.ino === ownedStat.ino) {
      await rm(path, { force: true });
    }
  };
}

export async function main(argv = process.argv.slice(2), overrides = {}) {
  const stdout = overrides.stdout || process.stdout;
  const stderr = overrides.stderr || process.stderr;
  let parsed;
  try {
    parsed = parseArgs(argv);
  } catch (error) {
    stderr.write(`${error instanceof Error ? error.message : String(error)}\n${usage()}\n`);
    return 2;
  }
  if (parsed.help) {
    stdout.write(`${usage()}\n`);
    return 0;
  }
  if (process.platform !== "darwin" && !overrides.allowNonDarwin) {
    stderr.write("本入口只支持 WorkBuddy macOS\n");
    return 2;
  }
  const release = [];
  try {
    assertWorkBuddyRuntimeSupport();
    const config = await resolveExecutionConfig(parsed);
    release.push(await acquireLock(config.uiLockFile, parsed.resume, {
      kind: "workbuddy-ui",
      host: hostname(),
      process_started_at: PROCESS_STARTED_AT,
      process_start_identity: PROCESS_START_IDENTITY,
      batch_id: config.manifest.batch_id,
      unit_id: config.manifest.unit_id,
      task_id: config.task.task_id,
    }, config.unitRoot));
    release.push(await acquireLock(config.lockFile, parsed.resume, {
      kind: "workbuddy-task",
      host: hostname(),
      process_started_at: PROCESS_STARTED_AT,
      process_start_identity: PROCESS_START_IDENTITY,
      batch_id: config.manifest.batch_id,
      unit_id: config.manifest.unit_id,
      task_id: config.task.task_id,
    }, config.unitRoot));
    const result = await executeWorkBuddyTask(config, overrides.dependencies || {});
    const phase = new Set(["NEEDS_ATTENTION", "FAILED"]).has(result.journal.phase)
      ? result.journal.phase
      : result.state?.phase || result.journal.phase;
    stdout.write(`${JSON.stringify({
      phase,
      identity: result.journal.identity,
      prompt: result.journal.prompt,
      native: result.journal.native,
      journal_file: config.journalFile,
      state_file: result.state ? config.stateFile : null,
    }, null, 2)}\n`);
    if (phase === "COMPLETED") return 0;
    if (phase === "RUNNING") return 4;
    if (phase === "NEEDS_ATTENTION") return 3;
    return 2;
  } catch (error) {
    stderr.write(`${error instanceof Error ? error.stack || error.message : String(error)}\n`);
    return 2;
  } finally {
    for (const releaseLock of release.reverse()) await releaseLock().catch(() => {});
  }
}

let invoked = process.argv[1] ? resolve(process.argv[1]) : null;
let modulePath = fileURLToPath(import.meta.url);
try {
  if (invoked) invoked = await realpath(invoked);
  modulePath = await realpath(modulePath);
} catch {
  // Missing paths cannot compare equal below.
}
if (invoked && invoked === modulePath) process.exitCode = await main();
