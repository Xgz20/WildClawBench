#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import {
  mkdir,
  open,
  readFile,
  realpath,
  lstat,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { isRetryablePreSendFailure } from "./execute_astronstudio_macos.mjs";
import { isQuotaError, pristineUnsentAttempt, readQuotaAuthorization, assertQuotaAuthorization, assertRetryableQuotaState,
  recoveryFiles, digest } from './lib/astronstudio-quota-retry.mjs';

export const QUEUE_SCHEMA = "wildclawbench.general-e2e-astronstudio-execution-queue/v1";
export const QUEUE_WORKER_VERSION = "0.1.2";
export const QUEUE_REVISION = 1;
export const UI_SLOTS = 1;
export const RUN_SLOTS = 3;
export const MAX_RUN_SLOTS = 8;

const SINGLE_TASK_SCRIPT = resolve(
  fileURLToPath(new URL("./execute_astronstudio_macos.mjs", import.meta.url)),
);
const TASK_TERMINAL_PHASES = new Set(["COMPLETED", "FAILED"]);

function externalQuotaFailure(task) {
  return task.phase === "FAILED" && isQuotaError(task.error);
}

function usage() {
  return `AstronStudio General E2E macOS 并发队列 Worker

用法：
  node scripts/run_astronstudio_macos_batch.mjs \\
    --unit-root /absolute/extracted-unit \\
    --run-config /absolute/frozen-run-config.json \\
    --queue-id <稳定ID> [--task-id <完整任务ID> ...] [选项]

选项：
  --resume                       恢复同一 queue 和已登记 attempt；不重发 Prompt
  --retry-pre-send-task-id <ID>  与 --resume 使用；只接续指定零发送准备失败
  --retry-quota-task-id <ID>     与 --resume 及额度恢复授权一起使用；仅重试指定失败题
  --quota-retry-authorization <JSON> 绑定旧 attempt/SHA/原队列的一次性人工授权
  --status                       只读取持久化队列状态
  --continue-on-terminal-failure 明确失败终态后继续下一题
  --run-slots <1-8>              后台 Agent 槽位，默认 3；UI 发送固定单槽
  --timeout-ms <毫秒>            传给单题执行器，默认 30000
  --poll-interval-ms <毫秒>      传给单题执行器，默认 1000
  --identity-timeout-ms <毫秒>   传给单题执行器，默认 120000
  -h, --help                     显示帮助

未指定 --task-id 时按 execution manifest.task_ids 的冻结顺序执行全部任务。
queue digest、任务顺序和并发策略保持冻结；attempt 只可通过受审计额度授权显式更换。
成功题不重跑；重试发送一经 armed，恢复只观察，不再发送。`;
}

function positiveInteger(value, name) {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) throw new Error(`${name} 必须是正整数`);
  return parsed;
}

export function parseBatchArgs(argv) {
  const values = {
    unitRoot: "",
    runConfig: "",
    queueId: "",
    taskIds: [],
    resume: false,
    retryPreSendTaskId: null,
    retryQuotaTaskId: null,
    quotaRetryAuthorization: null,
    status: false,
    continueOnTerminalFailure: false,
    runSlots: RUN_SLOTS,
    timeoutMs: 30_000,
    pollIntervalMs: 1_000,
    identityTimeoutMs: 120_000,
    help: false,
  };
  const valued = new Map([
    ["--unit-root", "unitRoot"],
    ["--run-config", "runConfig"],
    ["--queue-id", "queueId"],
    ["--run-slots", "runSlots"],
    ["--timeout-ms", "timeoutMs"],
    ["--poll-interval-ms", "pollIntervalMs"],
    ["--identity-timeout-ms", "identityTimeoutMs"],
    ["--retry-pre-send-task-id", "retryPreSendTaskId"],
    ["--retry-quota-task-id", "retryQuotaTaskId"],
    ["--quota-retry-authorization", "quotaRetryAuthorization"],
  ]);
  const numeric = new Set(["runSlots", "timeoutMs", "pollIntervalMs", "identityTimeoutMs"]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") values.help = true;
    else if (arg === "--resume") values.resume = true;
    else if (arg === "--status") values.status = true;
    else if (arg === "--continue-on-terminal-failure") values.continueOnTerminalFailure = true;
    else if (arg === "--task-id") {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error("--task-id 缺少值");
      values.taskIds.push(value);
      index += 1;
    } else {
      const key = valued.get(arg);
      if (!key) throw new Error(`未知选项：${arg}`);
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      values[key] = numeric.has(key) ? positiveInteger(value, arg) : value;
      index += 1;
    }
  }
  if (values.runSlots > MAX_RUN_SLOTS) {
    throw new Error(`--run-slots 必须在 1–${MAX_RUN_SLOTS} 之间`);
  }
  if (values.identityTimeoutMs < 120_000 || values.identityTimeoutMs > 180_000) {
    throw new Error("--identity-timeout-ms 必须在 120000–180000 之间");
  }
  if (new Set(values.taskIds).size !== values.taskIds.length) throw new Error("--task-id 不能重复");
  if (!values.help && (!values.unitRoot || !values.runConfig || !values.queueId)) {
    throw new Error("必须指定 --unit-root、--run-config 和 --queue-id");
  }
  if (values.status && values.resume) throw new Error("--status 与 --resume 不能同时使用");
  if (values.retryPreSendTaskId && (!values.resume || values.status)) {
    throw new Error("--retry-pre-send-task-id 只允许恢复原队列");
  }
  if (Boolean(values.retryQuotaTaskId) !== Boolean(values.quotaRetryAuthorization)
      || (values.retryQuotaTaskId && (!values.resume || values.status || values.retryPreSendTaskId))) {
    throw new Error("额度重试须同时指定 --resume、--retry-quota-task-id 和 --quota-retry-authorization，不能与零发送重试混用");
  }
  return values;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
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

async function atomicWriteJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  const file = await open(temporary, 'wx');
  try { await file.writeFile(`${JSON.stringify(value, null, 2)}\n`, 'utf8'); await file.sync(); }
  finally { await file.close(); }
  try {
    await rename(temporary, path);
    const directory = await open(dirname(path), 'r');
    try { await directory.sync(); } finally { await directory.close(); }
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
}

async function ownedDirectory(root, destination) {
  if (!isInside(root, destination)) throw new Error('QUOTA_DIRECTORY_SCOPE');
  let current = root;
  for (const part of relative(root, destination).split('/').filter(Boolean)) {
    current = join(current, part);
    try { await mkdir(current); } catch (error) { if (error?.code !== 'EEXIST') throw error; }
    const info = await lstat(current);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error('QUOTA_DIRECTORY_SYMLINK');
  }
}

function isInside(parent, child) {
  const value = relative(parent, child);
  return value === "" || (!value.startsWith("..") && !isAbsolute(value));
}

function safeQueueId(value) {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value)) {
    throw new Error("--queue-id 只能包含字母、数字、点、下划线和连字符，最长 128 个字符");
  }
  return value;
}

export async function resolveBatchPlan(args) {
  safeQueueId(args.queueId);
  const unitRoot = await realpath(resolve(args.unitRoot));
  if (!(await stat(unitRoot)).isDirectory()) throw new Error(`unit root 不是目录：${unitRoot}`);
  const manifestPath = join(unitRoot, "manifest.json");
  const manifestBytes = await readFile(manifestPath);
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  if (
    manifest?.manifest_kind !== "execution"
    || manifest?.schema_id !== "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
    || manifest?.unit?.harness?.id !== "astronstudio"
  ) {
    throw new Error("unit root 不是 AstronStudio General E2E execution 包");
  }
  const manifestTaskIds = manifest.task_ids || [];
  if (!manifestTaskIds.length || new Set(manifestTaskIds).size !== manifestTaskIds.length) {
    throw new Error("execution manifest.task_ids 为空或重复");
  }
  const taskIds = args.taskIds.length ? args.taskIds : manifestTaskIds;
  const manifestTaskSet = new Set(manifestTaskIds);
  for (const taskId of taskIds) {
    if (!manifestTaskSet.has(taskId)) throw new Error(`任务不在 execution manifest：${taskId}`);
  }
  const runConfigPath = await realpath(resolve(args.runConfig));
  const runConfig = await readJson(runConfigPath);
  if (typeof runConfig.config_digest !== "string" || !/^[0-9a-f]{64}$/.test(runConfig.config_digest)) {
    throw new Error("冻结运行配置缺少有效 config_digest");
  }
  const maximumConcurrency = Number(runConfig.control?.maximum_execution_concurrency || 8);
  if (
    !Number.isInteger(maximumConcurrency)
    || maximumConcurrency < 1
    || maximumConcurrency > MAX_RUN_SLOTS
    || args.runSlots > maximumConcurrency
  ) {
    throw new Error(`--run-slots 超出冻结配置上限：${maximumConcurrency}`);
  }
  const queueRoot = join(unitRoot, ".general-e2e", "queues", args.queueId);
  const frozen = {
    batch_id: manifest.batch_id,
    unit_id: manifest.unit_id,
    dataset_id: manifest.dataset?.id,
    dataset_digest: manifest.dataset?.digest,
    manifest_sha256: sha256(manifestBytes),
    run_config_digest: runConfig.config_digest,
    task_ids: [...taskIds],
    ui_slots: UI_SLOTS,
    run_slots: args.runSlots,
    continue_on_terminal_failure: args.continueOnTerminalFailure,
    driver_options: {
      timeout_ms: args.timeoutMs,
      poll_interval_ms: args.pollIntervalMs,
      identity_timeout_ms: args.identityTimeoutMs,
    },
  };
  return {
    unitRoot,
    manifestPath,
    manifest,
    runConfigPath,
    runConfig,
    taskIds: [...taskIds],
    queueId: args.queueId,
    queueRoot,
    queueStateFile: join(queueRoot, "queue-state.json"),
    queueReceiptFile: join(queueRoot, "queue-receipt.json"),
    workerLockFile: join(queueRoot, "worker.lock"),
    frozen,
    queueDigest: sha256(canonicalJson(frozen)),
  };
}

function controlPath(plan, taskId, name) {
  return join(plan.unitRoot, ".general-e2e", "execution", taskId, name);
}

function relativePosix(root, path) {
  const value = relative(root, path).split("\\").join("/");
  if (!value || value === ".." || value.startsWith("../")) throw new Error(`路径越出 unit：${path}`);
  return value;
}

export function createQueueState(plan, now = new Date().toISOString()) {
  return {
    schema_version: QUEUE_SCHEMA,
    revision: QUEUE_REVISION,
    worker: { id: "astronstudio-macos-concurrent", version: QUEUE_WORKER_VERSION },
    identity: {
      batch_id: plan.manifest.batch_id,
      unit_id: plan.manifest.unit_id,
      queue_id: plan.queueId,
      queue_digest: plan.queueDigest,
    },
    dataset: {
      id: plan.manifest.dataset.id,
      digest: plan.manifest.dataset.digest,
    },
    configuration: { ...plan.frozen },
    phase: "PREPARED",
    current_task_id: null,
    active_task_ids: [],
    runtime: {
      worker_pid: null,
      worker_started_at: null,
      heartbeat_at: now,
      interrupted_at: null,
      recovered_stale_lock: false,
    },
    tasks: plan.taskIds.map((taskId, index) => ({
      index,
      task_id: taskId,
      phase: "PENDING",
      selected_attempt_id: null,
      attempts: [],
      execution_state_path: relativePosix(
        plan.unitRoot,
        controlPath(plan, taskId, "automation-state.json"),
      ),
      execution_record_path: relativePosix(
        plan.unitRoot,
        controlPath(plan, taskId, "execution-record.json"),
      ),
      started_at: null,
      finished_at: null,
      driver_exit_code: null,
      dispatch_attempt_count: 0,
      session: { thread_id: null, turn_id: null, session_id: null, cwd: null },
      error: null,
    })),
    history: [{ at: now, event: "QUEUE_PREPARED" }],
    error: null,
  };
}

export function assertQueueIdentity(state, plan) {
  const mismatches = [];
  if (state.schema_version !== QUEUE_SCHEMA) mismatches.push("schema_version");
  if (state.revision !== QUEUE_REVISION) mismatches.push("revision");
  if (state.identity?.batch_id !== plan.manifest.batch_id) mismatches.push("batch_id");
  if (state.identity?.unit_id !== plan.manifest.unit_id) mismatches.push("unit_id");
  if (state.identity?.queue_id !== plan.queueId) mismatches.push("queue_id");
  if (state.identity?.queue_digest !== plan.queueDigest) mismatches.push("queue_digest");
  if (JSON.stringify(state.configuration) !== JSON.stringify(plan.frozen)) mismatches.push("configuration");
  if (JSON.stringify(state.tasks?.map((item) => item.task_id)) !== JSON.stringify(plan.taskIds)) {
    mismatches.push("task_ids");
  }
  if (mismatches.length) throw new Error(`已有 queue-state 与冻结计划不一致：${mismatches.join(",")}`);
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

async function acquireWorkerLock(path, allowStaleRecovery, isAlive = processIsAlive) {
  await mkdir(dirname(path), { recursive: true });
  let recovered = false;
  let handle;
  try {
    handle = await open(path, "wx", 0o600);
  } catch (error) {
    if (error?.code !== "EEXIST") throw error;
    const existing = await readJsonIfPresent(path).catch(() => null);
    if (!allowStaleRecovery || isAlive(Number(existing?.pid))) {
      throw new Error(`队列 Worker 锁已存在：${path}`);
    }
    await rm(path, { force: true });
    recovered = true;
    handle = await open(path, "wx", 0o600);
  }
  const owner = { pid: process.pid, token: randomUUID(), started_at: new Date().toISOString() };
  await handle.writeFile(`${JSON.stringify(owner)}\n`);
  return {
    owner,
    recovered,
    release: async () => {
      await handle.close().catch(() => {});
      const current = await readJsonIfPresent(path).catch(() => null);
      if (current?.token === owner.token) await rm(path, { force: true });
    },
  };
}

function validateAutomation(plan, queueTask, automation, quotaProof = null) {
  if (
    automation?.identity?.batch_id !== plan.manifest.batch_id
    || automation?.identity?.unit_id !== plan.manifest.unit_id
    || automation?.identity?.task_id !== queueTask.task_id
  ) {
    throw new Error(`automation-state 身份不一致：${queueTask.task_id}`);
  }
  const attemptId = automation.identity.attempt_id;
  if (typeof attemptId !== "string" || !attemptId) {
    throw new Error(`automation-state 缺少 attempt_id：${queueTask.task_id}`);
  }
  if (queueTask.selected_attempt_id && queueTask.selected_attempt_id !== attemptId) {
    const recovery = queueTask.quota_recoveries?.at(-1);
    if (recovery?.old_attempt_id === queueTask.selected_attempt_id && recovery.new_attempt_id === attemptId
        && quotaProof?.authorization_sha256 === recovery.authorization_sha256
        && quotaProof?.new_attempt_id === attemptId) {
      const old = queueTask.attempts.find(item => item.attempt_id === recovery.old_attempt_id);
      if (!old || queueTask.attempts.some(item => item.attempt_id === attemptId)) throw new Error('QUOTA_ATTEMPT_LINEAGE_INVALID');
      old.selected = false;
      old.dispatch_attempt_count = queueTask.dispatch_attempt_count;
      old.started_at = queueTask.started_at;
      old.finished_at = queueTask.finished_at;
      old.session = { ...queueTask.session };
      old.error = queueTask.error;
      old.state_path = `.general-e2e/quota-recoveries/${queueTask.task_id}/${attemptId}/failed-control/automation-state.json`;
      old.state_sha256 = recovery.old_state_sha256;
      queueTask.selected_attempt_id = attemptId;
      queueTask.attempts.push({ attempt_id: attemptId, state_path: queueTask.execution_state_path,
        registered_at: new Date().toISOString(), selected: true, previous_attempt_id: recovery.old_attempt_id,
        authorization_sha256: recovery.authorization_sha256 });
      recovery.status = 'ADOPTED';
      queueTask.started_at = null;
      queueTask.finished_at = null;
    } else throw new Error(
      `ATTEMPT_SWITCH_REQUIRES_NEW_QUEUE: ${queueTask.task_id}: `
      + `${queueTask.selected_attempt_id} -> ${attemptId}`,
    );
  }
  if (!queueTask.selected_attempt_id) {
    queueTask.selected_attempt_id = attemptId;
    queueTask.attempts.push({
      attempt_id: attemptId,
      state_path: queueTask.execution_state_path,
      registered_at: new Date().toISOString(),
      selected: true,
    });
  }
  return automation;
}

export function synchronizeTaskFromAutomation(plan, queueTask, automation, now = new Date().toISOString(), quotaProof = null) {
  validateAutomation(plan, queueTask, automation, quotaProof);
  queueTask.phase = automation.phase;
  queueTask.started_at ||= automation.execution?.started_at || null;
  queueTask.finished_at = TASK_TERMINAL_PHASES.has(automation.phase)
    ? automation.execution?.finished_at || now
    : null;
  queueTask.dispatch_attempt_count = Number(automation.send?.dispatch_attempt_count || 0);
  queueTask.session = {
    thread_id: automation.session?.thread_id || null,
    turn_id: automation.session?.turn_id || null,
    session_id: automation.session?.session_id || null,
    cwd: automation.session?.cwd || null,
  };
  queueTask.error = automation.execution?.error || null;
  return queueTask;
}

async function cachedAuthorization(plan, state, row, transaction) {
  const path = resolve(plan.unitRoot, transaction.authorization_path);
  if (!isInside(plan.queueRoot, path) || await realpath(path) !== path) throw new Error('QUOTA_AUTHORIZATION_CACHE_PATH');
  const authorization = await readQuotaAuthorization(path);
  authorization.path = path;
  if (authorization.sha256 !== transaction.authorization_sha256) throw new Error('QUOTA_AUTHORIZATION_CACHE_SHA');
  assertQuotaAuthorization(authorization.auth, { identity: state.identity, configuration: state.configuration, taskId: row.task_id });
  if (authorization.auth.old_attempt_id !== transaction.old_attempt_id || authorization.auth.new_attempt_id !== transaction.new_attempt_id) {
    throw new Error('QUOTA_TRANSACTION_IDENTITY');
  }
  if (transaction.previous_queue_receipt) {
    const previous = resolve(plan.unitRoot, transaction.previous_queue_receipt.path);
    if (!isInside(plan.queueRoot, previous)) throw new Error('QUOTA_PREVIOUS_RECEIPT_SCOPE');
    let bytes;
    try { bytes = await readFile(previous); }
    catch (error) {
      if (error?.code !== 'ENOENT') throw error;
      bytes = await readFile(plan.queueReceiptFile);
    }
    if (digest(bytes) !== transaction.previous_queue_receipt.sha256) throw new Error('QUOTA_PREVIOUS_RECEIPT_SHA');
  }
  return authorization;
}

async function synchronizationProof(plan, state, row, automation, dependencies) {
  if (!row.selected_attempt_id || row.selected_attempt_id === automation.identity?.attempt_id) return null;
  const transaction = row.quota_recoveries?.at(-1);
  if (!transaction || transaction.old_attempt_id !== row.selected_attempt_id || transaction.new_attempt_id !== automation.identity?.attempt_id) return null;
  const authorization = await cachedAuthorization(plan, state, row, transaction);
  return dependencies.recoveryFiles(plan.unitRoot, authorization, true);
}

async function refreshAutomations(plan, state, dependencies) {
  for (const row of state.tasks) {
    for (const transaction of row.quota_recoveries || []) {
      const authorization = await cachedAuthorization(plan, state, row, transaction);
      if (transaction.status === 'ADOPTED' && !dependencies.verifiedQuotaReceipts.has(transaction.authorization_sha256)) {
        await dependencies.recoveryFiles(plan.unitRoot, authorization, true);
        dependencies.verifiedQuotaReceipts.add(transaction.authorization_sha256);
      }
    }
    const automation = await readJsonIfPresent(controlPath(plan, row.task_id, 'automation-state.json'));
    if (automation) synchronizeTaskFromAutomation(plan, row, automation, dependencies.now(),
      await synchronizationProof(plan, state, row, automation, dependencies));
  }
}

async function registerQuotaAuthorization(plan, state, args, dependencies) {
  if (!args.retryQuotaTaskId) return;
  const row = state.tasks.find(task => task.task_id === args.retryQuotaTaskId);
  if (!row) throw new Error('QUOTA_TASK_NOT_IN_QUEUE');
  const authorization = await readQuotaAuthorization(args.quotaRetryAuthorization);
  authorization.path = resolve(args.quotaRetryAuthorization);
  assertQuotaAuthorization(authorization.auth, { identity: state.identity, configuration: state.configuration, taskId: row.task_id });
  const previous = row.quota_recoveries?.find(tx => tx.authorization_sha256 === authorization.sha256);
  if (previous) { await cachedAuthorization(plan, state, row, previous); return; }
  if (!externalQuotaFailure(row) || row.selected_attempt_id !== authorization.auth.old_attempt_id) throw new Error('QUOTA_TASK_NOT_ELIGIBLE');
  if (row.attempts.filter(attempt => attempt.selected).length !== 1
      || !row.attempts.some(attempt => attempt.selected && attempt.attempt_id === row.selected_attempt_id)) {
    throw new Error('QUOTA_OLD_ATTEMPT_LINEAGE_INVALID');
  }
  if (row.quota_recoveries?.at(-1)?.status === 'REQUESTED') throw new Error('QUOTA_RECOVERY_ALREADY_PENDING');
  if (state.tasks.some(task => task.attempts.some(attempt => attempt.attempt_id === authorization.auth.new_attempt_id))) {
    throw new Error('QUOTA_NEW_ATTEMPT_ALREADY_USED');
  }
  const raw = await readFile(controlPath(plan, row.task_id, 'automation-state.json'));
  const record = await readFile(controlPath(plan, row.task_id, 'execution-record.json'));
  assertRetryableQuotaState(JSON.parse(raw), authorization.auth);
  if (digest(raw) !== authorization.auth.old_state_sha256 || digest(record) !== authorization.auth.old_record_sha256) {
    throw new Error('QUOTA_SOURCE_SHA_MISMATCH');
  }
  await dependencies.recoveryFiles(plan.unitRoot, authorization, false, false, true);
  const path = join(plan.queueRoot, 'quota-authorizations', authorization.auth.authorization_id + '.json');
  await ownedDirectory(plan.unitRoot, dirname(path));
  try { await writeFile(path, authorization.bytes, { flag: 'wx', mode: 0o600 }); }
  catch (error) {
    if (error?.code !== 'EEXIST' || digest(await readFile(path)) !== authorization.sha256) throw error;
  }
  (row.quota_recoveries ||= []).push({ authorization_id: authorization.auth.authorization_id,
    authorization_sha256: authorization.sha256, authorization_path: relativePosix(plan.unitRoot, path),
    old_attempt_id: authorization.auth.old_attempt_id, new_attempt_id: authorization.auth.new_attempt_id,
    old_state_sha256: authorization.auth.old_state_sha256, status: 'REQUESTED' });
  state.history.push({ at: dependencies.now(), event: 'QUOTA_RETRY_AUTHORIZED', task_id: row.task_id,
    old_attempt_id: authorization.auth.old_attempt_id, new_attempt_id: authorization.auth.new_attempt_id,
    authorization_sha256: authorization.sha256 });
  await persist(plan, state, dependencies.now());
}

async function archivePreviousReceipt(plan, state, transaction, dependencies) {
  let bytes;
  try { bytes = await readFile(plan.queueReceiptFile); }
  catch (error) { if (error?.code === 'ENOENT') return; throw error; }
  const receiptSha = digest(bytes);
  const target = join(plan.queueRoot, 'receipt-history', receiptSha + '.json');
  await ownedDirectory(plan.unitRoot, dirname(target));
  if (transaction.previous_queue_receipt && transaction.previous_queue_receipt.sha256 !== receiptSha) {
    throw new Error('QUOTA_PREVIOUS_RECEIPT_DRIFT');
  }
  transaction.previous_queue_receipt = { path: relativePosix(plan.unitRoot, target), sha256: receiptSha };
  await persist(plan, state, dependencies.now());
  try { await writeFile(target, bytes, { flag: 'wx' }); }
  catch (error) { if (error?.code !== 'EEXIST' || digest(await readFile(target)) !== receiptSha) throw error; }
  await rm(plan.queueReceiptFile);
}

async function launchSingleTask(plan, args, taskId, operation, activeSessionIds = [], authorizationPath = null) {
  const childArgs = [
    SINGLE_TASK_SCRIPT,
    "--unit-root", plan.unitRoot,
    "--task-id", taskId,
    "--run-config", plan.runConfigPath,
    "--timeout-ms", String(args.timeoutMs),
    "--poll-interval-ms", String(args.pollIntervalMs),
    "--identity-timeout-ms", String(args.identityTimeoutMs),
  ];
  if (operation === "dispatch" || operation === "retry-pre-send" || operation === 'retry-quota') {
    childArgs.push("--detach-after-submit", "--managed-run-slots", String(args.runSlots));
    if (operation === "retry-pre-send") childArgs.push("--resume", "--retry-pre-send-failure");
    if (operation === 'retry-pre-send' && authorizationPath) childArgs.push('--quota-retry-authorization', authorizationPath);
    if (operation === 'retry-quota') childArgs.push('--resume', '--quota-retry-authorization', authorizationPath);
    for (const sessionId of activeSessionIds) {
      childArgs.push("--allowed-active-session-id", sessionId);
    }
  } else if (operation === "observe") {
    childArgs.push("--resume", "--observe-once");
  } else {
    throw new Error(`不支持的单题操作：${operation}`);
  }
  const child = spawn(process.execPath, childArgs, { stdio: "inherit" });
  return new Promise((resolvePromise, rejectPromise) => {
    child.once("error", rejectPromise);
    child.once("exit", (code, signal) => resolvePromise({ code: code ?? 2, signal }));
  });
}

function buildQueueReceipt(plan, state, now) {
  const allTerminal = state.tasks.every((task) => TASK_TERMINAL_PHASES.has(task.phase));
  const attemptsUnique = state.tasks.every((task) => (
    new Set(task.attempts.map(item => item.attempt_id)).size === task.attempts.length
    && (!task.selected_attempt_id || (task.attempts.filter(item => item.selected).length === 1
      && task.attempts.find(item => item.selected)?.attempt_id === task.selected_attempt_id))
    && task.attempts.every((item, index) => index === 0 || task.quota_recoveries?.some(tx =>
      tx.new_attempt_id === item.attempt_id && tx.old_attempt_id === item.previous_attempt_id
      && tx.authorization_sha256 === item.authorization_sha256))
  ));
  const noDuplicateDispatch = state.tasks.every((task) => task.dispatch_attempt_count <= 1
    && task.attempts.every(attempt => (attempt.dispatch_attempt_count || 0) <= 1));
  return {
    schema_version: "wildclawbench.general-e2e-astronstudio-execution-queue-receipt/v1",
    generated_at: now,
    identity: { ...state.identity },
    phase: state.phase,
    ui_slots: UI_SLOTS,
    run_slots: state.configuration.run_slots,
    tasks: state.tasks.map((task) => ({
      task_id: task.task_id,
      phase: task.phase,
      selected_attempt_id: task.selected_attempt_id,
      dispatch_attempt_count: task.dispatch_attempt_count,
      session: { ...task.session },
      error: task.error,
      attempts: task.attempts,
      quota_recoveries: task.quota_recoveries || [],
    })),
    integrity: {
      queue_digest_matches: state.identity.queue_digest === plan.queueDigest,
      all_tasks_terminal: allTerminal,
      attempts_explicit_and_unique: attemptsUnique,
      no_duplicate_dispatch: noDuplicateDispatch,
      valid: allTerminal && attemptsUnique && noDuplicateDispatch,
    },
  };
}

async function persist(plan, state, now = new Date().toISOString()) {
  state.runtime.heartbeat_at = now;
  await atomicWriteJson(plan.queueStateFile, state);
  if (new Set(["COMPLETED", "COMPLETED_WITH_FAILURES"]).has(state.phase)) {
    await atomicWriteJson(plan.queueReceiptFile, buildQueueReceipt(plan, state, now));
  }
}

function recordUnexpectedWorkerLoss(state, isAlive, now) {
  const previousPid = Number(state.runtime?.worker_pid);
  if (!previousPid || isAlive(previousPid) || new Set(["COMPLETED", "COMPLETED_WITH_FAILURES"]).has(state.phase)) {
    return false;
  }
  state.runtime.interrupted_at = now;
  state.history.push({
    at: now,
    event: "WORKER_PROCESS_LOST",
    previous_worker_pid: previousPid,
    current_task_id: state.current_task_id,
    active_task_ids: [...(state.active_task_ids || [])],
  });
  return true;
}

export async function runQueue(plan, args, overrides = {}) {
  const dependencies = {
    now: () => new Date().toISOString(),
    pid: process.pid,
    isProcessAlive: processIsAlive,
    recoveryFiles,
    verifiedQuotaReceipts: new Set(),
    runTask: (taskId, operation, activeSessionIds, authorizationPath) => (
      launchSingleTask(plan, args, taskId, operation, activeSessionIds, authorizationPath)
    ),
    sleep: (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds)),
    ...overrides,
  };
  let state = await readJsonIfPresent(plan.queueStateFile);
  if (args.status) {
    if (!state) throw new Error(`队列不存在：${plan.queueStateFile}`);
    assertQueueIdentity(state, plan);
    return state;
  }
  if (state) {
    assertQueueIdentity(state, plan);
    if (!args.resume) throw new Error("已有 queue-state；必须使用 --resume，禁止创建新队列或隐式选择 attempt");
  } else {
    if (args.resume) throw new Error("--resume 要求已有 queue-state.json");
    for (const taskId of plan.taskIds) {
      if (await readJsonIfPresent(controlPath(plan, taskId, "automation-state.json"))) {
        throw new Error(`未登记的既有 attempt：${taskId}；请使用原 queue 恢复或重新准备 execution unit`);
      }
    }
    state = createQueueState(plan, dependencies.now());
    await persist(plan, state, dependencies.now());
  }

  if (new Set(["COMPLETED", "COMPLETED_WITH_FAILURES"]).has(state.phase)
    && !args.retryPreSendTaskId && !state.tasks.some(externalQuotaFailure)) {
    if (state.tasks.some(task => task.quota_recoveries?.length)) await refreshAutomations(plan, state, dependencies);
    if (args.retryQuotaTaskId) {
      const row = state.tasks.find(task => task.task_id === args.retryQuotaTaskId);
      const authorization = await readQuotaAuthorization(args.quotaRetryAuthorization);
      const transaction = row?.quota_recoveries?.find(tx => tx.authorization_sha256 === authorization.sha256);
      if (!transaction) throw new Error('QUOTA_TASK_NOT_ELIGIBLE');
      await cachedAuthorization(plan, state, row, transaction);
      await dependencies.recoveryFiles(plan.unitRoot, { ...authorization, path: resolve(args.quotaRetryAuthorization) }, true);
    }
    return state;
  }
  const now = dependencies.now();
  if (args.resume) recordUnexpectedWorkerLoss(state, dependencies.isProcessAlive, now);
  const lock = await acquireWorkerLock(plan.workerLockFile, args.resume, dependencies.isProcessAlive);
  try {
    state.runtime.worker_pid = dependencies.pid;
    state.runtime.worker_started_at = now;
    state.runtime.recovered_stale_lock = lock.recovered;
    state.runtime.interrupted_at = null;
    state.history.push({
      at: now,
      event: args.resume ? "WORKER_RESUMED" : "WORKER_STARTED",
      worker_pid: dependencies.pid,
      recovered_stale_lock: lock.recovered,
    });
    state.phase = "RUNNING";
    state.error = null;
    await persist(plan, state, dependencies.now());

    if (args.retryQuotaTaskId || state.tasks.some(task => task.quota_recoveries?.length)) await ownedDirectory(plan.unitRoot, plan.queueRoot);
    await refreshAutomations(plan, state, dependencies);
    await registerQuotaAuthorization(plan, state, args, dependencies);
    for (const row of state.tasks) {
      const transaction = row.quota_recoveries?.at(-1);
      if (!transaction) continue;
      const automation = await readJsonIfPresent(controlPath(plan, row.task_id, 'automation-state.json'));
      const retryPending = row.selected_attempt_id === transaction.old_attempt_id
        || (row.selected_attempt_id === transaction.new_attempt_id && ['PENDING', 'NEEDS_ATTENTION'].includes(automation?.phase));
      if (!retryPending) continue;
      // Drain already accepted peers by observation only. Successful tasks are
      // never redispatched; a retry starts only after native activity settles.
      const needsNewSend = row.selected_attempt_id === transaction.old_attempt_id || pristineUnsentAttempt(automation);
      for (const peer of state.tasks.filter(task => needsNewSend && task !== row && task.phase === 'RUNNING')) {
        await dependencies.runTask(peer.task_id, 'observe', []);
        const observed = await readJsonIfPresent(controlPath(plan, peer.task_id, 'automation-state.json'));
        if (observed) synchronizeTaskFromAutomation(plan, peer, observed, dependencies.now());
      }
      if (needsNewSend && state.tasks.some(task => task !== row && ['RUNNING', 'NEEDS_ATTENTION'].includes(task.phase))) {
        state.phase = 'NEEDS_ATTENTION';
        state.error = 'QUOTA_RECOVERY_WAIT_FOR_INFLIGHT_TASKS';
        await persist(plan, state, dependencies.now());
        return state;
      }
      const authorization = await cachedAuthorization(plan, state, row, transaction);
      await archivePreviousReceipt(plan, state, transaction, dependencies);
      const result = await dependencies.runTask(row.task_id, 'retry-quota', [], authorization.path);
      row.driver_exit_code = result.code;
      const current = await readJsonIfPresent(controlPath(plan, row.task_id, 'automation-state.json'));
      if (current) synchronizeTaskFromAutomation(plan, row, current, dependencies.now(),
        await synchronizationProof(plan, state, row, current, dependencies));
      await persist(plan, state, dependencies.now());
      if (!current || current.identity.attempt_id !== transaction.new_attempt_id || current.phase === 'PENDING') {
        state.phase = 'NEEDS_ATTENTION';
        state.error = 'QUOTA_RECOVERY_INCOMPLETE: 保留授权和原状态，只能恢复同一事务，不得新发重复 Prompt';
        await persist(plan, state, dependencies.now());
        return state;
      }
    }

    if (args.retryPreSendTaskId) {
      await refreshAutomations(plan, state, dependencies);
    }
    if (args.retryPreSendTaskId && !state.tasks.some(externalQuotaFailure)) {
      const row = state.tasks.find((task) => task.task_id === args.retryPreSendTaskId);
      if (!row) throw new Error("指定的准备失败任务不在冻结队列中");
      const automation = await readJsonIfPresent(controlPath(plan, row.task_id, "automation-state.json"));
      validateAutomation(plan, row, automation);
      if (!isRetryablePreSendFailure(automation)
        || state.tasks.some((task) => ["RUNNING", "NEEDS_ATTENTION"].includes(task.phase))) {
        throw new Error("准备失败接续要求指定任务零发送且队列没有活动或未知发送任务");
      }
      state.history.push({ at: dependencies.now(), event: "ZERO_SEND_PREPARATION_RETRY_REQUESTED",
        task_id: row.task_id, attempt_id: row.selected_attempt_id });
      await persist(plan, state, dependencies.now());
      const quotaTransaction = row.quota_recoveries?.at(-1);
      const quotaAuthorization = quotaTransaction?.new_attempt_id === row.selected_attempt_id
        ? await cachedAuthorization(plan, state, row, quotaTransaction) : null;
      const result = await dependencies.runTask(row.task_id, "retry-pre-send", [], quotaAuthorization?.path || null);
      row.driver_exit_code = result.code;
      const recovered = await readJsonIfPresent(controlPath(plan, row.task_id, "automation-state.json"));
      synchronizeTaskFromAutomation(plan, row, recovered, dependencies.now());
      await persist(plan, state, dependencies.now());
    }

    for (;;) {
      await refreshAutomations(plan, state, dependencies);

      let running = state.tasks.filter((task) => task.phase === "RUNNING");
      const attention = state.tasks.filter((task) => task.phase === "NEEDS_ATTENTION");
      const failed = state.tasks.filter((task) => task.phase === "FAILED");
      state.active_task_ids = running.map((task) => task.task_id);
      state.current_task_id = state.active_task_ids[0] || null;

      const quotaFailures = failed.filter(externalQuotaFailure);
      const unsentRecoveryFailures = failed.filter(task => task.selected_attempt_id === task.quota_recoveries?.at(-1)?.new_attempt_id
        && task.dispatch_attempt_count === 0);
      if (unsentRecoveryFailures.length) {
        state.phase = 'NEEDS_ATTENTION';
        state.error = 'QUOTA_RETRY_PRE_SEND_FAILURE: 新 attempt 尚未发送，保留现场等待人工处理';
        await persist(plan, state, dependencies.now());
        return state;
      }
      if (quotaFailures.length) {
        state.phase = "NEEDS_ATTENTION";
        state.current_task_id = quotaFailures[0].task_id;
        state.error = `EXECUTION_EXTERNAL_QUOTA_EXHAUSTED: ${quotaFailures.map(task => task.task_id).join(",")}; 等待人工恢复额度及明确恢复/重测决定，不自动跳过或重发`;
        state.history.push({ at: dependencies.now(), event: "QUEUE_BLOCKED_EXTERNAL_QUOTA",
          task_ids: quotaFailures.map(task => task.task_id), active_task_ids: [...state.active_task_ids] });
        await persist(plan, state, dependencies.now());
        return state;
      }

      if (attention.length) {
        state.phase = "NEEDS_ATTENTION";
        state.error = `任务需要人工关注：${attention.map((task) => task.task_id).join(",")}`;
        await persist(plan, state, dependencies.now());
        return state;
      }

      let dispatchBlocked = failed.length > 0 && !args.continueOnTerminalFailure;
      while (!dispatchBlocked && running.length < args.runSlots) {
        const pending = state.tasks.find((task) => task.phase === "PENDING");
        if (!pending) break;
        const activeSessionIds = running.map((task) => task.session.session_id).filter(Boolean);
        if (activeSessionIds.length !== running.length) break;
        pending.phase = "RUNNING";
        pending.started_at ||= dependencies.now();
        state.active_task_ids = [...running.map((task) => task.task_id), pending.task_id];
        state.current_task_id = state.active_task_ids[0] || null;
        state.history.push({
          at: dependencies.now(),
          event: "TASK_DISPATCH_REQUESTED",
          task_id: pending.task_id,
          active_task_ids: [...state.active_task_ids],
        });
        await persist(plan, state, dependencies.now());

        let driverResult;
        try {
          driverResult = await dependencies.runTask(pending.task_id, "dispatch", activeSessionIds);
        } catch (error) {
          driverResult = {
            code: 2,
            signal: null,
            error: error instanceof Error ? error.message : String(error),
          };
        }
        pending.driver_exit_code = driverResult.code;
        const automation = await readJsonIfPresent(
          controlPath(plan, pending.task_id, "automation-state.json"),
        );
        if (!automation) {
          pending.phase = "NEEDS_ATTENTION";
          pending.error = {
            code: "DRIVER_STATE_MISSING",
            message: driverResult.error || `单题 Driver 退出码 ${driverResult.code}，且未生成 automation-state`,
          };
        } else {
          synchronizeTaskFromAutomation(plan, pending, automation, dependencies.now());
        }
        state.history.push({
          at: dependencies.now(),
          event: "TASK_DISPATCH_RETURNED",
          task_id: pending.task_id,
          attempt_id: pending.selected_attempt_id,
          task_phase: pending.phase,
          driver_exit_code: driverResult.code,
          driver_signal: driverResult.signal || null,
        });
        await persist(plan, state, dependencies.now());
        if (externalQuotaFailure(pending)) break;
        if (pending.phase === "NEEDS_ATTENTION") break;
        if (pending.phase === "FAILED" && !args.continueOnTerminalFailure) {
          dispatchBlocked = true;
        }
        running = state.tasks.filter((task) => task.phase === "RUNNING");
      }

      running = state.tasks.filter((task) => task.phase === "RUNNING");
      const pending = state.tasks.filter((task) => task.phase === "PENDING");
      const currentAttention = state.tasks.filter((task) => task.phase === "NEEDS_ATTENTION");
      if (state.tasks.some(externalQuotaFailure)) continue;
      if (currentAttention.length) continue;
      if (!running.length && !pending.length) {
        const terminalFailures = state.tasks.filter((task) => task.phase === "FAILED");
        state.phase = terminalFailures.length ? "COMPLETED_WITH_FAILURES" : "COMPLETED";
        state.active_task_ids = [];
        state.current_task_id = null;
        state.error = terminalFailures.length
          ? `${terminalFailures.length} 个任务以明确失败终态结束`
          : null;
        state.history.push({
          at: dependencies.now(),
          event: state.phase === "COMPLETED" ? "QUEUE_COMPLETED" : "QUEUE_COMPLETED_WITH_FAILURES",
          failed_task_ids: terminalFailures.map((task) => task.task_id),
        });
        await persist(plan, state, dependencies.now());
        return state;
      }
      if (!running.length && dispatchBlocked) {
        const currentFailures = state.tasks.filter((task) => task.phase === "FAILED");
        state.phase = "FAILED";
        state.active_task_ids = [];
        state.current_task_id = currentFailures[0]?.task_id || null;
        state.error = `任务失败，未启用继续策略：${currentFailures[0]?.task_id}`;
        await persist(plan, state, dependencies.now());
        return state;
      }

      let observedChange = false;
      for (const queueTask of running) {
        const previousPhase = queueTask.phase;
        let driverResult;
        try {
          driverResult = await dependencies.runTask(queueTask.task_id, "observe", []);
        } catch (error) {
          driverResult = {
            code: 2,
            signal: null,
            error: error instanceof Error ? error.message : String(error),
          };
        }
        queueTask.driver_exit_code = driverResult.code;
        const automation = await readJsonIfPresent(
          controlPath(plan, queueTask.task_id, "automation-state.json"),
        );
        if (!automation) {
          queueTask.phase = "NEEDS_ATTENTION";
          queueTask.error = {
            code: "DRIVER_STATE_MISSING",
            message: driverResult.error || "观察阶段缺少 automation-state",
          };
        } else {
          synchronizeTaskFromAutomation(plan, queueTask, automation, dependencies.now());
        }
        observedChange ||= queueTask.phase !== previousPhase;
        state.history.push({
          at: dependencies.now(),
          event: "TASK_OBSERVATION_RETURNED",
          task_id: queueTask.task_id,
          attempt_id: queueTask.selected_attempt_id,
          task_phase: queueTask.phase,
          driver_exit_code: driverResult.code,
          driver_signal: driverResult.signal || null,
        });
        await persist(plan, state, dependencies.now());
        if (externalQuotaFailure(queueTask)) break;
      }
      if (!observedChange) await dependencies.sleep(args.pollIntervalMs);
    }
  } catch (error) {
    state.phase = "FAILED";
    state.error = error instanceof Error ? error.message : String(error);
    state.history.push({ at: dependencies.now(), event: "QUEUE_WORKER_ERROR", error: state.error });
    await persist(plan, state, dependencies.now());
    throw error;
  } finally {
    await lock.release();
  }
}

export async function main(argv = process.argv.slice(2), overrides = {}) {
  let args;
  try {
    args = parseBatchArgs(argv);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    console.error(usage());
    return 2;
  }
  if (args.help) {
    console.log(usage());
    return 0;
  }
  if (process.platform !== "darwin" && !overrides.allowNonDarwin) {
    console.error("本入口只支持 AstronStudio macOS；Windows 由 G5 原生入口实现");
    return 2;
  }
  try {
    const plan = await resolveBatchPlan(args);
    const state = await runQueue(plan, args, overrides.dependencies || {});
    console.log(JSON.stringify({
      phase: state.phase,
      identity: state.identity,
      current_task_id: state.current_task_id,
      tasks: state.tasks,
      queue_state: plan.queueStateFile,
      queue_receipt: plan.queueReceiptFile,
    }, null, 2));
    if (new Set(["COMPLETED", "COMPLETED_WITH_FAILURES"]).has(state.phase)) return 0;
    if (state.phase === "NEEDS_ATTENTION") return 3;
    return 2;
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return 2;
  }
}

let invokedPath = process.argv[1] ? resolve(process.argv[1]) : null;
let modulePath = fileURLToPath(import.meta.url);
try {
  if (invokedPath) invokedPath = await realpath(invokedPath);
  modulePath = await realpath(modulePath);
} catch {
  // The normal comparison below remains false when either path disappears.
}
if (invokedPath && invokedPath === modulePath) process.exitCode = await main();
