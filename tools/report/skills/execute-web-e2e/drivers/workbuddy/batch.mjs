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
export const QUEUE_WORKER_VERSION = "1.2.0";

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
  --restart-app-first              只在第一题前重启 WorkBuddy
  --resume                         恢复同一 run-id 的未完成队列
  --retry-pre-send-failure          仅归档并重试发送前、产物零变化的 INFRA_FAILED
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
    restartAppFirst: false,
    resume: false,
    retryPreSendFailure: false,
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
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else if (arg === "--restart-app-first") values.restartAppFirst = true;
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
  if (!new Set(["current", "full-access"]).has(values.permissionMode)) {
    throw new Error("--permission-mode 仅支持 current 或 full-access");
  }
  if (values.retryPreSendFailure && !values.resume) {
    throw new Error("--retry-pre-send-failure 必须与 --resume 一起使用");
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

function pidAlive(pid) {
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
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const handle = await open(lockFile, "wx", 0o600);
      await handle.writeFile(`${JSON.stringify(owner, null, 2)}\n`, "utf8");
      await handle.close();
      return owner;
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      const existing = await readJsonIfExists(lockFile).catch(() => null);
      if (existing?.hostname === hostname() && !pidAlive(Number(existing.pid))) {
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

function spawnDriver(args) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(process.execPath, [DRIVER_FILE, ...args], { stdio: "inherit" });
    child.once("error", rejectPromise);
    child.once("exit", (code, signal) => resolvePromise({ code: code ?? 1, signal }));
  });
}

export function buildDriverArgs(args, task, index, existingAutomation = null) {
  const driverArgs = [
    "--workspace", task.taskRoot,
    "--model", args.model,
    "--permission-mode", args.permissionMode,
    "--run-timeout-seconds", String(args.runTimeoutSeconds),
    "--poll-interval-seconds", String(args.pollIntervalSeconds),
  ];
  if (args.restartAppFirst && index === 0) driverArgs.push("--restart-app");
  if (existingAutomation) {
    driverArgs.push("--resume");
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
  if (automation.phase === "SUCCEEDED"
    && (!automation.evidence?.terminal_source || !automation.artifacts?.final)) {
    throw new Error(`成功任务缺少终态或产物证据：${task.taskId}`);
  }
  return { automation, execution, driverResult };
}

async function saveQueue(plan, state) {
  await atomicWriteJson(plan.queueStateFile, state);
}

async function runQueue(plan, args) {
  await mkdir(plan.queueDir, { recursive: true });
  let state = await readJsonIfExists(plan.queueStateFile);
  if (state) {
    assertQueueState(state, plan, args);
    if (state.phase === "COMPLETED") return state;
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

  const lockOwner = await acquireUiLock(plan.lockFile);
  try {
    state.phase = "RUNNING";
    state.timing.started_at ||= new Date().toISOString();
    state.error = null;
    await saveQueue(plan, state);

    for (let index = 0; index < plan.tasks.length; index += 1) {
      const queueTask = state.tasks[index];
      const task = plan.tasks[index];
      if (queueTask.phase === "SUCCEEDED") continue;
      if (TERMINAL_TASK_PHASES.has(queueTask.phase) && args.continueOnTerminalFailure) continue;

      state.current_index = index;
      queueTask.phase = "RUNNING";
      queueTask.started_at ||= new Date().toISOString();
      queueTask.error = null;
      state.history.push({ event: "TASK_STARTED", at: new Date().toISOString(), index, task_id: task.taskId });
      await saveQueue(plan, state);

      const existingAutomation = args.resume ? await readJsonIfExists(task.automationStateFile) : null;
      const driverArgs = buildDriverArgs(args, task, index, existingAutomation);

      let driverResult = null;
      let result;
      try {
        driverResult = await spawnDriver(driverArgs);
        result = await inspectTaskResult(plan, task, driverResult);
      } catch (error) {
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
      if (queueTask.phase !== "SUCCEEDED" && !args.continueOnTerminalFailure) {
        state.phase = "FAILED";
        state.error = `任务未成功：${task.taskId} (${queueTask.phase})`;
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
