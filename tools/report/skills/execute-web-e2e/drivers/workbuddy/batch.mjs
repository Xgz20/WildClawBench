#!/usr/bin/env node
import { randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { realpathSync } from "node:fs";
import {
  access,
  mkdir,
  open,
  readFile,
  realpath,
  readdir,
  stat,
  unlink,
} from "node:fs/promises";
import { hostname } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { atomicWriteJson, readJsonIfExists } from "./lib.mjs";

export const QUEUE_SCHEMA = "wildclawbench.web-e2e-execution-queue/v1";
export const QUEUE_WORKER_VERSION = "1.3.0";

const SCRIPT_DIR = resolve(fileURLToPath(new URL(".", import.meta.url)));
const DRIVER_FILE = join(SCRIPT_DIR, "driver.mjs");
const TERMINAL_TASK_PHASES = new Set(["SUCCEEDED", "INFRA_FAILED", "TIMEOUT"]);
const EXPECTED_EXECUTION_STATUS = {
  SUCCEEDED: "completed",
  INFRA_FAILED: "execution_error",
  TIMEOUT: "timeout",
  NEEDS_ATTENTION: "pending",
};

function usage() {
  return `WorkBuddy Web E2E 串行队列 Worker

用法：
  node batch.mjs --harness-root <execution 包根目录> --run-id <ID> \\
    --task-id <任务 ID> [--task-id <任务 ID> ...] [选项]

选项：
  --model <UI名称>                 WorkBuddy UI 显示值，默认：均衡
  --permission-mode <模式>         current（保持现状）或 full-access（显式开启完全访问）
  --run-timeout-seconds <秒>       每题 Agent 总执行超时，默认：3600
  --poll-interval-seconds <秒>     每题终态轮询间隔，默认：2
  --post-cancel-quiescence-seconds <秒> 超时停止后的 workspace 静默观察，默认：5
  --restart-app-first              只在第一题前重启 WorkBuddy
  --restart-app-on-resume          恢复运行中题目时重启 WorkBuddy，并定位原会话
  --resume                         恢复同一 run-id 的未完成队列
  --retry-pre-send-failure          仅归档并重试发送前、产物零变化的 INFRA_FAILED
  --mark-manual <任务 ID>          记录人工介入并恢复检查；不绕过 Driver 终态门禁
  --status                         只读取并打印队列状态
  --continue-on-terminal-failure   单题明确失败/超时后继续下一题
  -h, --help                       显示帮助`;
}

function positiveNumber(value, option) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`${option} 必须是正数`);
  return parsed;
}

export function parseBatchArgs(argv) {
  const values = {
    harnessRoot: "",
    runId: "",
    taskIds: [],
    model: "均衡",
    permissionMode: "current",
    runTimeoutSeconds: 3600,
    pollIntervalSeconds: 2,
    postCancelQuiescenceSeconds: 5,
    restartAppFirst: false,
    restartAppOnResume: false,
    resume: false,
    retryPreSendFailure: false,
    markManualTaskId: "",
    status: false,
    continueOnTerminalFailure: false,
    help: false,
  };
  const scalarOptions = new Map([
    ["--harness-root", "harnessRoot"],
    ["--run-id", "runId"],
    ["--model", "model"],
    ["--permission-mode", "permissionMode"],
    ["--run-timeout-seconds", "runTimeoutSeconds"],
    ["--poll-interval-seconds", "pollIntervalSeconds"],
    ["--post-cancel-quiescence-seconds", "postCancelQuiescenceSeconds"],
    ["--mark-manual", "markManualTaskId"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else if (arg === "--restart-app-first") values.restartAppFirst = true;
    else if (arg === "--restart-app-on-resume") values.restartAppOnResume = true;
    else if (arg === "--resume") values.resume = true;
    else if (arg === "--retry-pre-send-failure") values.retryPreSendFailure = true;
    else if (arg === "--status") values.status = true;
    else if (arg === "--continue-on-terminal-failure") values.continueOnTerminalFailure = true;
    else if (arg === "--task-id") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error("--task-id 缺少参数值");
      values.taskIds.push(value);
      index += 1;
    } else {
      const key = scalarOptions.get(arg);
      if (!key) throw new Error(`未知参数：${arg}`);
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少参数值`);
      values[key] = value;
      index += 1;
    }
  }
  values.runTimeoutSeconds = positiveNumber(values.runTimeoutSeconds, "--run-timeout-seconds");
  values.pollIntervalSeconds = positiveNumber(values.pollIntervalSeconds, "--poll-interval-seconds");
  values.postCancelQuiescenceSeconds = positiveNumber(values.postCancelQuiescenceSeconds, "--post-cancel-quiescence-seconds");
  if (!new Set(["current", "full-access"]).has(values.permissionMode)) {
    throw new Error("--permission-mode 仅支持 current 或 full-access");
  }
  if (values.retryPreSendFailure && !values.resume) {
    throw new Error("--retry-pre-send-failure 必须与 --resume 一起使用");
  }
  if (values.restartAppOnResume && !values.resume) {
    throw new Error("--restart-app-on-resume 必须与 --resume 一起使用");
  }
  if (values.markManualTaskId && !values.resume) {
    throw new Error("--mark-manual 必须与 --resume 一起使用");
  }
  return values;
}

function isInside(parent, child) {
  const rel = relative(parent, child);
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
}

function assertRunId(runId) {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(runId)) {
    throw new Error("--run-id 只能包含字母、数字、点、下划线和连字符，且不能超过 128 个字符");
  }
}

async function requireDirectory(path, label) {
  const info = await stat(path);
  if (!info.isDirectory()) throw new Error(`${label} 不是目录：${path}`);
}

export async function resolveQueuePlan(args) {
  if (!args.harnessRoot) throw new Error("必须指定 --harness-root");
  if (!args.runId) throw new Error("必须指定 --run-id，确保状态可以确定性恢复");
  assertRunId(args.runId);
  if (!args.taskIds.length && !args.status) throw new Error("至少指定一个 --task-id");
  if (new Set(args.taskIds).size !== args.taskIds.length) throw new Error("--task-id 不能重复");

  const harnessRoot = await realpath(resolve(args.harnessRoot));
  await requireDirectory(harnessRoot, "Harness 根目录");
  const manifestPath = join(harnessRoot, "manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  if (manifest.harness?.id !== "workbuddy") {
    throw new Error(`当前 Worker 不能执行 Harness：${manifest.harness?.id || "未声明"}`);
  }
  if (!manifest.batch_id) throw new Error("manifest.json 缺少 batch_id");

  const manifestTasks = new Map((manifest.tasks || []).map((task) => [task.task_id, task]));
  const tasks = [];
  for (const taskId of args.taskIds) {
    const task = manifestTasks.get(taskId);
    if (!task?.execution_dir) throw new Error(`manifest.json 中不存在任务：${taskId}`);
    const taskRoot = await realpath(join(harnessRoot, task.execution_dir));
    if (!isInside(harnessRoot, taskRoot)) throw new Error(`任务目录越出 Harness 根目录：${taskId}`);
    await requireDirectory(taskRoot, "任务目录");
    await access(join(taskRoot, "PROMPT.md"));
    await requireDirectory(join(taskRoot, "workspace"), "候选 workspace");
    const names = new Set(await readdir(taskRoot));
    for (const forbidden of ["eval", "gt", "rubric", "checker"]) {
      if (names.has(forbidden)) throw new Error(`execution 任务包含禁止材料 ${forbidden}：${taskId}`);
    }
    tasks.push({
      taskId,
      taskName: task.task_name || taskId,
      difficulty: task.difficulty || "",
      executionDir: task.execution_dir,
      taskRoot,
      automationStateFile: join(dirname(taskRoot), ".execute-web-e2e", basename(taskRoot), "automation_state.json"),
      executionRecordFile: join(taskRoot, "execution_record.json"),
    });
  }

  const controlRoot = join(harnessRoot, "execution", ".execute-web-e2e");
  return {
    harnessRoot,
    manifestPath,
    manifest,
    tasks,
    runId: args.runId,
    queueDir: join(controlRoot, "queues", args.runId),
    queueStateFile: join(controlRoot, "queues", args.runId, "queue_state.json"),
    lockFile: join(controlRoot, "workbuddy-ui.lock"),
    receiptFile: join(harnessRoot, "execution-receipt.json"),
  };
}

export function createQueueState(plan, args) {
  const now = new Date().toISOString();
  return {
    schema_version: QUEUE_SCHEMA,
    worker: { id: "workbuddy-serial", version: QUEUE_WORKER_VERSION },
    run_id: plan.runId,
    batch_id: plan.manifest.batch_id,
    harness_id: "workbuddy",
    requested_ui_model: args.model,
    requested_permission_mode: args.permissionMode,
    phase: "PREPARED",
    current_index: null,
    timing: { prepared_at: now, started_at: null, finished_at: null },
    runtime: {
      worker: null,
      driver: null,
      last_driver: null,
      heartbeat_at: null,
      interrupted_at: null,
      interrupt_signal: null,
    },
    tasks: plan.tasks.map((task, index) => ({
      index,
      task_id: task.taskId,
      task_name: task.taskName,
      difficulty: task.difficulty,
      phase: "PENDING",
      attempt_id: null,
      started_at: null,
      finished_at: null,
      driver_exit_code: null,
      automation_state_file: relative(plan.harnessRoot, task.automationStateFile),
      execution_record_file: relative(plan.harnessRoot, task.executionRecordFile),
      error: null,
    })),
    history: [{ event: "QUEUE_PREPARED", at: now }],
    error: null,
  };
}

export function assertQueueState(state, plan, args) {
  const mismatches = [];
  if (state.schema_version !== QUEUE_SCHEMA) mismatches.push("schema_version");
  if (state.run_id !== plan.runId) mismatches.push("run_id");
  if (state.batch_id !== plan.manifest.batch_id) mismatches.push("batch_id");
  if (state.harness_id !== "workbuddy") mismatches.push("harness_id");
  if (state.requested_ui_model !== args.model) mismatches.push("requested_ui_model");
  if (state.requested_permission_mode && state.requested_permission_mode !== args.permissionMode) {
    mismatches.push("requested_permission_mode");
  }
  const existingIds = (state.tasks || []).map((task) => task.task_id);
  const requestedIds = plan.tasks.map((task) => task.taskId);
  if (JSON.stringify(existingIds) !== JSON.stringify(requestedIds)) mismatches.push("task_ids");
  if (mismatches.length) throw new Error(`已有 queue_state 与本次调用不一致：${mismatches.join(", ")}`);
}

export function pidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

async function acquireUiLock(lockFile) {
  await mkdir(dirname(lockFile), { recursive: true });
  const owner = { token: randomUUID(), pid: process.pid, hostname: hostname(), acquired_at: new Date().toISOString() };
  let recoveredLock = null;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const handle = await open(lockFile, "wx", 0o600);
      await handle.writeFile(`${JSON.stringify(owner, null, 2)}\n`, "utf8");
      await handle.close();
      return { owner, recoveredLock };
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      const existing = await readJsonIfExists(lockFile).catch(() => null);
      if (existing?.hostname === hostname() && !pidAlive(Number(existing.pid))) {
        recoveredLock = existing;
        await unlink(lockFile);
        continue;
      }
      throw new Error(`WorkBuddy UI 已被其他队列占用：${lockFile}`);
    }
  }
  throw new Error(`无法获取 WorkBuddy UI 锁：${lockFile}`);
}

async function releaseUiLock(lockFile, owner) {
  const current = await readJsonIfExists(lockFile).catch(() => null);
  if (current?.token === owner.token) await unlink(lockFile).catch(() => {});
}

function launchDriver(args) {
  const child = spawn(process.execPath, [DRIVER_FILE, ...args], { stdio: "inherit" });
  const completed = new Promise((resolvePromise, rejectPromise) => {
    child.once("error", rejectPromise);
    child.once("exit", (code, signal) => resolvePromise({ code: code ?? 1, signal }));
  });
  return { child, completed };
}

export function buildDriverArgs(args, task, index, existingAutomation = null) {
  const driverArgs = [
    "--workspace", task.taskRoot,
    "--model", args.model,
    "--permission-mode", args.permissionMode,
    "--run-timeout-seconds", String(args.runTimeoutSeconds),
    "--poll-interval-seconds", String(args.pollIntervalSeconds),
    "--post-cancel-quiescence-seconds", String(args.postCancelQuiescenceSeconds),
  ];
  if (args.restartAppFirst && index === 0) driverArgs.push("--restart-app");
  if (existingAutomation) {
    driverArgs.push("--resume");
    if (args.restartAppOnResume) driverArgs.push("--restart-app");
    if (args.retryPreSendFailure) driverArgs.push("--retry-pre-send-failure");
  }
  return driverArgs;
}

export function recordTaskOrchestrationFailure(state, queueTask, task, index, error, driverResult = null) {
  const at = new Date().toISOString();
  const message = error instanceof Error ? error.message : String(error);
  queueTask.phase = "WORKER_ERROR";
  queueTask.finished_at = at;
  queueTask.driver_exit_code = driverResult?.code ?? null;
  queueTask.error = message;
  state.phase = "FAILED";
  state.error = `任务编排失败：${task.taskId} (${message})`;
  state.history.push({
    event: "TASK_ORCHESTRATION_FAILED",
    at,
    index,
    task_id: task.taskId,
    driver_exit_code: queueTask.driver_exit_code,
    error: message,
  });
  return state;
}

export function canAdvanceTask(automation, continueOnTerminalFailure = false) {
  if (automation.phase === "SUCCEEDED") return true;
  if (!continueOnTerminalFailure) return false;
  if (automation.phase === "INFRA_FAILED") return true;
  if (automation.phase === "TIMEOUT") {
    return automation.timeout?.cancellation_confirmed === true
      && automation.timeout?.quiescence?.stable === true;
  }
  return false;
}

export function recordWorkerInterruption(state, signal, activeChild = null) {
  const at = new Date().toISOString();
  state.phase = "INTERRUPTED";
  state.error = `队列 Worker 收到 ${signal}，当前题保留为可恢复状态`;
  state.runtime ||= {};
  state.runtime.interrupted_at = at;
  state.runtime.interrupt_signal = signal;
  state.runtime.heartbeat_at = at;
  state.history.push({
    event: "WORKER_INTERRUPTED",
    at,
    signal,
    current_index: state.current_index,
    driver_pid: activeChild?.pid || state.runtime.driver?.pid || null,
  });
  return state;
}

export function recordManualIntervention(state, taskId, automation) {
  const queueTask = state.tasks.find((task) => task.task_id === taskId);
  if (!queueTask) throw new Error(`--mark-manual 指定的任务不在当前队列：${taskId}`);
  if (!new Set(["NEEDS_ATTENTION", "RUNNING", "WORKER_ERROR"]).has(queueTask.phase)) {
    throw new Error(`任务 ${taskId} 当前状态 ${queueTask.phase} 不接受人工介入标记`);
  }
  if (!automation || TERMINAL_TASK_PHASES.has(automation.phase)) {
    throw new Error(`任务 ${taskId} 没有可恢复的非终态 automation_state`);
  }
  const at = new Date().toISOString();
  const lastReason = [...(automation.history || [])].reverse().find((entry) => entry.reason)?.reason || null;
  queueTask.manual_interventions ||= [];
  queueTask.manual_interventions.push({ at, automation_phase: automation.phase, reason: lastReason });
  state.history.push({
    event: "MANUAL_INTERVENTION_MARKED",
    at,
    task_id: taskId,
    automation_phase: automation.phase,
    reason: lastReason,
  });
  return state;
}

async function inspectTaskResult(plan, task, driverResult) {
  const automation = await readJsonIfExists(task.automationStateFile);
  if (!automation) throw new Error(`Driver 未生成 automation_state：${task.taskId}`);
  if (automation.identity?.batch_id !== plan.manifest.batch_id
    || automation.identity?.task_id !== task.taskId
    || automation.identity?.harness_id !== "workbuddy") {
    throw new Error(`automation_state 身份不一致：${task.taskId}`);
  }
  const execution = await readJsonIfExists(task.executionRecordFile);
  const expectedStatus = EXPECTED_EXECUTION_STATUS[automation.phase];
  if (!expectedStatus) throw new Error(`Driver 返回未知状态 ${automation.phase}：${task.taskId}`);
  if (!execution || execution.execution?.status !== expectedStatus) {
    throw new Error(`execution_record 状态与 ${automation.phase} 不一致：${task.taskId}`);
  }
  if (TERMINAL_TASK_PHASES.has(automation.phase)
    && (!automation.evidence?.terminal_source || !automation.artifacts?.final)) {
    throw new Error(`终态任务缺少终态或产物证据：${task.taskId}`);
  }
  if (automation.phase === "TIMEOUT" && !canAdvanceTask(automation, true)) {
    throw new Error(`超时任务缺少已停止且 workspace 静默的证据：${task.taskId}`);
  }
  return { automation, execution, driverResult };
}

async function saveQueue(plan, state) {
  await atomicWriteJson(plan.queueStateFile, state);
}

function receiptRelativePath(plan, path) {
  if (!path) return null;
  const value = relative(plan.harnessRoot, resolve(path));
  return value && !value.startsWith("..") && !isAbsolute(value) ? value.split("\\").join("/") : null;
}

export async function buildExecutionReceipt(plan, state) {
  const manifestTaskIds = (plan.manifest.tasks || []).map((task) => task.task_id);
  const requestedTaskIds = plan.tasks.map((task) => task.taskId);
  const sameScope = JSON.stringify([...manifestTaskIds].sort()) === JSON.stringify([...requestedTaskIds].sort());
  const tasks = [];
  let recordsPresent = true;
  let identitiesMatch = true;
  let modelsMatch = true;
  let allTerminal = true;
  for (const task of plan.tasks) {
    const queueTask = state.tasks.find((item) => item.task_id === task.taskId);
    const automation = await readJsonIfExists(task.automationStateFile);
    const execution = await readJsonIfExists(task.executionRecordFile);
    if (!automation || !execution) recordsPresent = false;
    if (automation && (automation.identity?.batch_id !== plan.manifest.batch_id
      || automation.identity?.task_id !== task.taskId
      || automation.identity?.harness_id !== "workbuddy")) identitiesMatch = false;
    if (execution && (execution.batch_id !== plan.manifest.batch_id
      || execution.task_id !== task.taskId
      || execution.harness?.id !== "workbuddy")) identitiesMatch = false;
    const actualUiModel = automation?.model_selection?.actual_model || automation?.model_selection?.model || null;
    if (automation?.requested_ui_model && automation.requested_ui_model !== state.requested_ui_model) modelsMatch = false;
    if (automation && new Set(["SUCCEEDED", "TIMEOUT"]).has(automation.phase)
      && actualUiModel !== automation.requested_ui_model) modelsMatch = false;
    if (!automation || !TERMINAL_TASK_PHASES.has(automation.phase)) allTerminal = false;
    tasks.push({
      task_id: task.taskId,
      attempt_id: automation?.attempt_id || null,
      automation_phase: automation?.phase || "PENDING",
      execution_status: execution?.execution?.status || "pending",
      started_at: automation?.timing?.started_at || execution?.execution?.started_at || null,
      sent_at: automation?.timing?.sent_at || null,
      finished_at: automation?.timing?.finished_at || execution?.execution?.finished_at || null,
      error: automation?.error || execution?.execution?.error || null,
      client_version: automation?.client?.version || execution?.harness?.version || null,
      driver: automation?.driver || null,
      model_selection: automation ? {
        requested_model: automation.requested_ui_model || null,
        actual_model: actualUiModel,
        method: automation.model_selection?.method || null,
      } : null,
      permission_mode: automation?.permission_selection?.confirmed_mode
        || automation?.permission_selection?.actual_mode
        || automation?.requested_permission_mode
        || null,
      terminal_source: automation?.evidence?.terminal_source || null,
      prompt: automation ? { sha256: automation.prompt_sha256, bytes: automation.prompt_bytes } : null,
      workspace: automation ? {
        initial_sha256: automation.artifacts?.initial?.sha256 || null,
        final_sha256: automation.artifacts?.final?.sha256 || null,
      } : null,
      timeout: automation?.timeout || null,
      manual_interventions: queueTask?.manual_interventions || [],
      evidence: {
        automation_state: receiptRelativePath(plan, task.automationStateFile),
        execution_record: receiptRelativePath(plan, task.executionRecordFile),
        final_screenshot: receiptRelativePath(plan, automation?.evidence?.final_screenshot_path),
        transcript: receiptRelativePath(plan, automation?.evidence?.transcript_path),
        screenshots: (automation?.evidence?.screenshots || []).map((path) => receiptRelativePath(plan, path)).filter(Boolean),
      },
    });
  }
  return {
    schema_version: "wildclawbench.web-e2e-execution-receipt/v1",
    generated_at: new Date().toISOString(),
    batch_id: plan.manifest.batch_id,
    run_id: state.run_id,
    harness: plan.manifest.harness,
    model: plan.manifest.model || null,
    worker: state.worker,
    queue: {
      phase: state.phase,
      requested_ui_model: state.requested_ui_model,
      requested_permission_mode: state.requested_permission_mode,
      state_path: receiptRelativePath(plan, plan.queueStateFile),
    },
    scope: {
      manifest_task_ids: manifestTaskIds,
      requested_task_ids: requestedTaskIds,
      matches_manifest: sameScope,
    },
    tasks,
    integrity: {
      records_present: recordsPresent,
      identities_match: identitiesMatch,
      models_match: modelsMatch,
      all_tasks_terminal: allTerminal,
      valid: sameScope && recordsPresent && identitiesMatch && modelsMatch && allTerminal,
    },
  };
}

async function saveExecutionReceipt(plan, state) {
  const receipt = await buildExecutionReceipt(plan, state);
  await atomicWriteJson(plan.receiptFile, receipt);
  return receipt;
}

async function runQueue(plan, args) {
  await mkdir(plan.queueDir, { recursive: true });
  let state = await readJsonIfExists(plan.queueStateFile);
  if (state) {
    assertQueueState(state, plan, args);
    if (new Set(["COMPLETED", "COMPLETED_WITH_FAILURES"]).has(state.phase)) {
      await saveExecutionReceipt(plan, state);
      return state;
    }
    if (!args.resume) throw new Error(`已有未完成队列 ${state.phase}；必须使用 --resume`);
    if (!state.requested_permission_mode) {
      state.requested_permission_mode = args.permissionMode;
      state.history.push({
        event: "QUEUE_CONFIGURATION_MIGRATED",
        at: new Date().toISOString(),
        requested_permission_mode: args.permissionMode,
      });
      await saveQueue(plan, state);
    }
  } else {
    if (args.resume) throw new Error("--resume 要求已有 queue_state.json");
    state = createQueueState(plan, args);
    await saveQueue(plan, state);
  }

  const { owner: lockOwner, recoveredLock } = await acquireUiLock(plan.lockFile);
  let activeDriver = null;
  let interruptSignal = null;
  let interruptWrite = Promise.resolve();
  let heartbeatWrite = Promise.resolve();
  let heartbeatTimer = null;
  const signalHandlers = new Map();
  try {
    if (args.markManualTaskId) {
      const target = plan.tasks.find((task) => task.taskId === args.markManualTaskId);
      if (!target) throw new Error(`--mark-manual 指定的任务不在当前队列：${args.markManualTaskId}`);
      const automation = await readJsonIfExists(target.automationStateFile);
      recordManualIntervention(state, args.markManualTaskId, automation);
      await saveQueue(plan, state);
    }
    state.runtime ||= {
      worker: null,
      driver: null,
      last_driver: null,
      heartbeat_at: null,
      interrupted_at: null,
      interrupt_signal: null,
    };
    if (recoveredLock) {
      state.history.push({
        event: "STALE_UI_LOCK_RECOVERED",
        at: new Date().toISOString(),
        previous_pid: recoveredLock.pid || null,
        previous_hostname: recoveredLock.hostname || null,
      });
    }
    const previousDriver = state.runtime.driver;
    if (previousDriver?.hostname === hostname() && pidAlive(Number(previousDriver.pid))) {
      throw new Error(`上一次 Driver 仍在运行（PID ${previousDriver.pid}）；拒绝启动第二个 Driver`);
    }
    if (previousDriver) {
      state.history.push({
        event: "STALE_DRIVER_CLEARED",
        at: new Date().toISOString(),
        driver_pid: previousDriver.pid || null,
        task_id: previousDriver.task_id || null,
      });
      state.runtime.last_driver = previousDriver;
      state.runtime.driver = null;
    }
    state.runtime.worker = {
      pid: process.pid,
      hostname: hostname(),
      started_at: new Date().toISOString(),
    };
    state.runtime.interrupted_at = null;
    state.runtime.interrupt_signal = null;
    state.phase = "RUNNING";
    state.timing.started_at ||= new Date().toISOString();
    state.error = null;
    await saveQueue(plan, state);

    for (const signal of ["SIGINT", "SIGTERM"]) {
      const handler = () => {
        if (interruptSignal) return;
        interruptSignal = signal;
        recordWorkerInterruption(state, signal, activeDriver?.child || null);
        if (activeDriver?.child && !activeDriver.exited) {
          activeDriver.child.kill("SIGTERM");
          activeDriver.forceTimer = setTimeout(() => {
            if (!activeDriver?.exited) activeDriver?.child.kill("SIGKILL");
          }, 5000);
          activeDriver.forceTimer.unref();
        }
        interruptWrite = saveQueue(plan, state);
      };
      signalHandlers.set(signal, handler);
      process.on(signal, handler);
    }
    heartbeatTimer = setInterval(() => {
      state.runtime.heartbeat_at = new Date().toISOString();
      heartbeatWrite = heartbeatWrite.then(() => saveQueue(plan, state)).catch(() => {});
    }, 5000);
    heartbeatTimer.unref();

    for (let index = 0; index < plan.tasks.length; index += 1) {
      if (interruptSignal) {
        await interruptWrite;
        return state;
      }
      const queueTask = state.tasks[index];
      const task = plan.tasks[index];
      if (queueTask.phase === "SUCCEEDED") continue;
      if (TERMINAL_TASK_PHASES.has(queueTask.phase) && args.continueOnTerminalFailure) {
        const previousResult = await inspectTaskResult(plan, task, { code: queueTask.driver_exit_code, signal: null });
        if (!canAdvanceTask(previousResult.automation, true)) {
          state.phase = "FAILED";
          state.error = `任务不满足安全继续条件：${task.taskId} (${queueTask.phase})`;
          await saveQueue(plan, state);
          return state;
        }
        if (index + 1 < plan.tasks.length) {
          state.history.push({
            event: "AUTO_ADVANCE",
            at: new Date().toISOString(),
            from_task_id: task.taskId,
            to_task_id: plan.tasks[index + 1].taskId,
            resumed_after_terminal_failure: true,
          });
          await saveQueue(plan, state);
        }
        continue;
      }

      state.current_index = index;
      queueTask.phase = "RUNNING";
      queueTask.started_at ||= new Date().toISOString();
      queueTask.error = null;
      state.history.push({ event: "TASK_STARTED", at: new Date().toISOString(), index, task_id: task.taskId });
      await saveQueue(plan, state);

      const existingAutomation = args.resume ? await readJsonIfExists(task.automationStateFile) : null;
      const driverArgs = buildDriverArgs(args, task, index, existingAutomation);

      if (interruptSignal) {
        await interruptWrite;
        return state;
      }

      let driverResult = null;
      let result;
      try {
        const launchedAt = new Date().toISOString();
        const launched = launchDriver(driverArgs);
        activeDriver = { ...launched, exited: false, forceTimer: null };
        state.runtime.driver = {
          pid: launched.child.pid,
          hostname: hostname(),
          task_id: task.taskId,
          started_at: launchedAt,
        };
        state.runtime.heartbeat_at = launchedAt;
        await saveQueue(plan, state);
        driverResult = await launched.completed;
        activeDriver.exited = true;
        if (activeDriver.forceTimer) clearTimeout(activeDriver.forceTimer);
        state.runtime.last_driver = {
          ...state.runtime.driver,
          finished_at: new Date().toISOString(),
          exit_code: driverResult.code,
          signal: driverResult.signal,
        };
        state.runtime.driver = null;
        activeDriver = null;
        if (interruptSignal) {
          await interruptWrite;
          await saveQueue(plan, state);
          return state;
        }
        result = await inspectTaskResult(plan, task, driverResult);
      } catch (error) {
        if (interruptSignal) {
          await interruptWrite.catch(() => {});
          await saveQueue(plan, state);
          return state;
        }
        recordTaskOrchestrationFailure(state, queueTask, task, index, error, driverResult);
        await saveQueue(plan, state);
        return state;
      }
      queueTask.phase = result.automation.phase;
      queueTask.attempt_id = result.automation.attempt_id;
      queueTask.finished_at = result.automation.timing?.finished_at || new Date().toISOString();
      queueTask.driver_exit_code = driverResult.code;
      queueTask.error = result.automation.error || null;
      state.history.push({
        event: "TASK_FINISHED",
        at: new Date().toISOString(),
        index,
        task_id: task.taskId,
        phase: queueTask.phase,
        attempt_id: queueTask.attempt_id,
      });
      await saveQueue(plan, state);

      if (queueTask.phase === "NEEDS_ATTENTION") {
        state.phase = "NEEDS_ATTENTION";
        state.error = `任务需要人工处理：${task.taskId}`;
        await saveQueue(plan, state);
        return state;
      }
      if (!canAdvanceTask(result.automation, args.continueOnTerminalFailure)) {
        state.phase = "FAILED";
        state.error = queueTask.phase === "TIMEOUT"
          ? `超时任务没有已停止且 workspace 静默的证据：${task.taskId}`
          : `任务未成功：${task.taskId} (${queueTask.phase})`;
        await saveQueue(plan, state);
        return state;
      }
      if (index + 1 < plan.tasks.length) {
        state.history.push({
          event: "AUTO_ADVANCE",
          at: new Date().toISOString(),
          from_task_id: task.taskId,
          to_task_id: plan.tasks[index + 1].taskId,
        });
        await saveQueue(plan, state);
      }
    }

    state.phase = state.tasks.every((task) => task.phase === "SUCCEEDED") ? "COMPLETED" : "COMPLETED_WITH_FAILURES";
    state.current_index = null;
    state.timing.finished_at = new Date().toISOString();
    state.history.push({ event: state.phase, at: state.timing.finished_at });
    await saveQueue(plan, state);
    return state;
  } finally {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    await heartbeatWrite;
    for (const [signal, handler] of signalHandlers) process.off(signal, handler);
    state.runtime ||= {};
    state.runtime.worker = null;
    state.runtime.heartbeat_at = new Date().toISOString();
    await saveQueue(plan, state).catch(() => {});
    try {
      await saveExecutionReceipt(plan, state);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      state.history.push({ event: "EXECUTION_RECEIPT_FAILED", at: new Date().toISOString(), error: message });
      state.error = `生成 execution-receipt.json 失败：${message}`;
      if (new Set(["COMPLETED", "COMPLETED_WITH_FAILURES"]).has(state.phase)) state.phase = "FAILED";
      await saveQueue(plan, state).catch(() => {});
    }
    await releaseUiLock(plan.lockFile, lockOwner);
  }
}

export async function main(argv) {
  try {
    const args = parseBatchArgs(argv);
    if (args.help) {
      console.log(usage());
      return 0;
    }
    const plan = await resolveQueuePlan(args);
    if (args.status) {
      const state = await readJsonIfExists(plan.queueStateFile);
      if (!state) throw new Error(`队列状态不存在：${plan.queueStateFile}`);
      console.log(JSON.stringify(state, null, 2));
      return state.phase === "COMPLETED" ? 0 : 3;
    }
    const state = await runQueue(plan, args);
    console.log(`WorkBuddy 队列状态：${state.phase}；状态文件：${plan.queueStateFile}`);
    if (state.phase === "COMPLETED") return 0;
    if (state.phase === "NEEDS_ATTENTION") return 3;
    if (state.phase === "INTERRUPTED") return 130;
    return 1;
  } catch (error) {
    console.error(`WorkBuddy 队列失败：${error.message}`);
    return 1;
  }
}

const isEntrypoint = process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  const exitCode = await main(process.argv.slice(2));
  process.exitCode = exitCode;
  setImmediate(() => process.exit(exitCode));
}
