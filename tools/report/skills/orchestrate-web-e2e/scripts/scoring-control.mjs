#!/usr/bin/env node
import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { mkdir, readFile, realpath, rename, stat, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  CANDIDATE_ARTIFACT_SCHEMA,
  TREE_HASH_ALGORITHM,
  loadCandidateArtifact,
  verifyWorkspace,
} from "./workspace-integrity.mjs";

const STATE_SCHEMA = "wildclawbench.web-e2e-scoring-automation/v1";
const STATE_REVISION = 2;
const REGISTRY_SCHEMA = "wildclawbench.codex-project-registry/v1";
const SCORE_SCHEMA = "wildclawbench.web-e2e-task-score/v1";
const SCORE_SKILL_SCHEMA = "wildclawbench.web-e2e-score-skill/v1";
const EXECUTION_RECEIPT_SCHEMA = "wildclawbench.web-e2e-execution-receipt/v1";
const SUBMISSION_SCHEMA = "wildclawbench.web-e2e-submission/v1";
const CONTROL_DIR = join("score", ".orchestrate-web-e2e");
const DEFAULT_SCORE_TIMEOUT_SECONDS = 7200;
const DEFAULT_MAX_RETRIES = 1;
const WAIT_STATUSES = new Set([
  "RUNNING",
  "POLL_TIMEOUT",
  "NEEDS_ATTENTION",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "INTERRUPTED",
]);
const TERMINAL_THREAD_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"]);
const REGISTRATION_METHODS = new Set([
  "direct-open-folder",
  "create-local-project-dialog",
  "add-project-then-open-folder",
  "renderer-bridge",
]);

export function usage() {
  return `Web E2E 评分控制状态

用法：
  node scoring-control.mjs init --package-root <目录> [--task-id <ID> ...] [--score-timeout-seconds <秒>] [--max-retries <次数>]
  node scoring-control.mjs status --package-root <目录>
  node scoring-control.mjs resume --package-root <目录>
  node scoring-control.mjs record-project --package-root <目录> --task-id <ID> --project-id <ID> --project-path <目录> --host-id <ID> --desktop-version <版本> --registration-method <方式>
  node scoring-control.mjs preflight --package-root <目录> --desktop-version <版本> --score-skill-dir <目录> [--allow-renderer-bridge]
  node scoring-control.mjs record-thread --package-root <目录> --task-id <ID> --thread-id <ID> --host-id <ID>
  node scoring-control.mjs record-wait --package-root <目录> --task-id <ID> --wait-sequence <序号> --wait-cursor <游标> --wait-status <状态> [--wait-error <说明>]
  node scoring-control.mjs mark-timeout --package-root <目录> --task-id <ID>
  node scoring-control.mjs prepare-retry --package-root <目录> --task-id <ID> --retry-reason <说明>
  node scoring-control.mjs mark-complete --package-root <目录> --task-id <ID>
  node scoring-control.mjs mark-failed --package-root <目录> --task-id <ID> --error <说明>
  node scoring-control.mjs build-submission --package-root <目录> [--score-skill-dir <目录>]
`;
}

export function parseArgs(argv) {
  const command = argv[0] || "";
  const values = { command, taskIds: [] };
  for (let index = 1; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--task-id") values.taskIds.push(argv[++index] || "");
    else if (token === "--package-root") values.packageRoot = argv[++index] || "";
    else if (token === "--project-id") values.projectId = argv[++index] || "";
    else if (token === "--project-path") values.projectPath = argv[++index] || "";
    else if (token === "--thread-id") values.threadId = argv[++index] || "";
    else if (token === "--host-id") values.hostId = argv[++index] || "";
    else if (token === "--desktop-version") values.desktopVersion = argv[++index] || "";
    else if (token === "--registration-method") values.registrationMethod = argv[++index] || "";
    else if (token === "--score-skill-dir") values.scoreSkillDir = argv[++index] || "";
    else if (token === "--allow-renderer-bridge") values.allowRendererBridge = true;
    else if (token === "--error") values.error = argv[++index] || "";
    else if (token === "--score-timeout-seconds") values.scoreTimeoutSeconds = Number(argv[++index]);
    else if (token === "--max-retries") values.maxRetries = Number(argv[++index]);
    else if (token === "--wait-sequence") values.waitSequence = Number(argv[++index]);
    else if (token === "--wait-cursor") values.waitCursor = argv[++index] || "";
    else if (token === "--wait-status") values.waitStatus = String(argv[++index] || "").toUpperCase();
    else if (token === "--wait-error") values.waitError = argv[++index] || "";
    else if (token === "--retry-reason") values.retryReason = argv[++index] || "";
    else if (token === "--help" || token === "-h") values.help = true;
    else throw new Error(`未知参数：${token}`);
  }
  if (values.help) return values;
  if (!new Set([
    "init",
    "status",
    "resume",
    "record-project",
    "preflight",
    "record-thread",
    "record-wait",
    "mark-timeout",
    "prepare-retry",
    "mark-complete",
    "mark-failed",
    "build-submission",
  ]).has(command)) {
    throw new Error(`未知命令：${command || "未提供"}`);
  }
  if (!values.packageRoot) throw new Error("必须提供 --package-root");
  if (values.taskIds.some((taskId) => !taskId)) throw new Error("--task-id 不能为空");
  if (values.scoreTimeoutSeconds !== undefined && (!Number.isInteger(values.scoreTimeoutSeconds) || values.scoreTimeoutSeconds < 1)) {
    throw new Error("--score-timeout-seconds 必须是正整数");
  }
  if (values.maxRetries !== undefined && (!Number.isInteger(values.maxRetries) || values.maxRetries < 0)) {
    throw new Error("--max-retries 必须是非负整数");
  }
  return values;
}

async function loadJson(filename) {
  const value = JSON.parse(await readFile(filename, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error(`JSON 顶层必须是对象：${filename}`);
  return value;
}

async function loadJsonIfExists(filename) {
  try {
    return await loadJson(filename);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

async function isDirectory(filename) {
  return (await stat(filename).catch(() => null))?.isDirectory() || false;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function inside(parent, child) {
  const rel = relative(parent, child);
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
}

async function atomicWriteJson(filename, value) {
  await mkdir(dirname(filename), { recursive: true });
  const temporary = `${filename}.tmp-${process.pid}`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  await rename(temporary, filename);
}

function asDate(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) throw new Error(`时间无效：${value}`);
  return date;
}

function deadlineFrom(startedAt, timeoutSeconds) {
  return new Date(asDate(startedAt).getTime() + timeoutSeconds * 1000).toISOString();
}

function submissionState() {
  return {
    status: "PENDING",
    attempt_count: 0,
    output_file: null,
    sha256: null,
    pending_file: null,
    started_at: null,
    generated_at: null,
    error: null,
    adopted_existing: false,
  };
}

function normalizeAttempt(attempt, task, state) {
  attempt.attempt_number ||= 1;
  attempt.thread_id ||= task.thread_id || null;
  attempt.host_id ||= task.thread_host_id || null;
  attempt.created_at ||= task.timing?.thread_created_at || null;
  attempt.deadline_at ||= attempt.created_at
    ? deadlineFrom(attempt.created_at, task.score_timeout_seconds || state.score_timeout_seconds)
    : null;
  attempt.wait_cursor ??= null;
  attempt.wait_count ??= 0;
  attempt.last_wait_sequence ??= 0;
  attempt.last_wait_status ??= null;
  attempt.last_wait_error ??= null;
  attempt.last_observed_at ??= null;
  attempt.deadline_exceeded_at ??= null;
  attempt.terminal_status ??= task.phase === "COMPLETED" ? "SCORE_VALIDATED" : null;
  attempt.finished_at ??= task.timing?.finished_at || null;
  attempt.score_validated_at ??= task.phase === "COMPLETED" ? task.timing?.finished_at || null : null;
  return attempt;
}

function normalizeState(state) {
  if (state.schema_version !== STATE_SCHEMA) throw new Error(`评分状态 schema 不兼容：${state.schema_version}`);
  state.schema_revision = STATE_REVISION;
  state.score_timeout_seconds ??= DEFAULT_SCORE_TIMEOUT_SECONDS;
  state.max_retries ??= DEFAULT_MAX_RETRIES;
  if (!Number.isInteger(state.score_timeout_seconds) || state.score_timeout_seconds < 1) throw new Error("评分状态的 score_timeout_seconds 无效");
  if (!Number.isInteger(state.max_retries) || state.max_retries < 0) throw new Error("评分状态的 max_retries 无效");
  state.score_skill ??= null;
  state.submission = { ...submissionState(), ...(state.submission || {}) };
  for (const task of state.tasks || []) {
    task.score_timeout_seconds ??= state.score_timeout_seconds;
    task.max_retries ??= state.max_retries;
    task.retry_count ??= 0;
    task.attempts ??= [];
    if (!task.attempts.length && task.thread_id) {
      task.attempts.push({
        attempt_number: 1,
        thread_id: task.thread_id,
        host_id: task.thread_host_id,
        created_at: task.timing?.thread_created_at || null,
      });
    }
    task.attempts = task.attempts.map((attempt) => normalizeAttempt(attempt, task, state));
    task.retry_count = Math.max(task.retry_count, Math.max(0, task.attempts.length - 1));
    if (task.retry_count > task.max_retries) throw new Error(`评分状态的 retry_count 超限：${task.task_id}`);
  }
  return state;
}

function currentAttempt(task) {
  return task.attempts?.at(-1) || null;
}

function promptForTask(taskId) {
  return [
    `使用 $score-web-e2e 对当前项目中的唯一 Web E2E 用例 ${taskId} 进行完整评分。`,
    "必须使用 Codex Desktop 内置 Browser，按照 private-scoring/task_contract.json 逐项实际操作和截图取证，并生成 private-scoring/task_score.json。",
    "workspace/ 是被评 Harness 已冻结的只读候选产物，严禁编辑、格式化、安装依赖、构建或生成任何文件；需要写入时只能使用 private-scoring/runtime-workspace/ 临时副本。",
    "不要访问当前项目目录之外的文件，不要创建或调度其他 Codex 任务；只用评分 Skill 的精确 PID 管理工具启动和停止本站服务，证据不足或浏览器不可用时按 Skill 契约记录 evaluation_error。",
    "完成全部评分文件后结束当前任务。",
    "",
  ].join("\n");
}

async function resolvePackage(packageRoot) {
  const root = await realpath(resolve(packageRoot));
  const manifestFile = join(root, "manifest.json");
  const manifest = await loadJson(manifestFile);
  if (!manifest.batch_id) throw new Error("manifest.json 缺少 batch_id");
  if (!manifest.harness?.id) throw new Error("manifest.json 缺少 harness.id");
  if (!Array.isArray(manifest.tasks) || !manifest.tasks.length) throw new Error("manifest.tasks 为空");
  return {
    root,
    manifest,
    manifestFile,
    controlRoot: join(root, CONTROL_DIR),
    stateFile: join(root, CONTROL_DIR, "scoring-automation-state.json"),
    registryFile: join(root, CONTROL_DIR, "project-registry.json"),
    promptRoot: join(root, CONTROL_DIR, "prompts"),
  };
}

async function loadExecutionReceipt(plan) {
  const receiptFile = join(plan.root, "execution-receipt.json");
  const receiptRaw = await readFile(receiptFile, "utf8");
  const receipt = JSON.parse(receiptRaw);
  if (!receipt || Array.isArray(receipt) || typeof receipt !== "object") throw new Error(`JSON 顶层必须是对象：${receiptFile}`);
  if (receipt.schema_version !== EXECUTION_RECEIPT_SCHEMA) throw new Error(`execution-receipt.json schema 不兼容：${receipt.schema_version}`);
  if (receipt.integrity?.valid !== true) throw new Error("execution-receipt.json 的 integrity.valid 不是 true");
  if (receipt.batch_id !== plan.manifest.batch_id) throw new Error("execution-receipt.json batch_id 与 manifest 不一致");
  if (receipt.harness?.id !== plan.manifest.harness.id) throw new Error("execution-receipt.json Harness 与 manifest 不一致");
  const receiptTasks = receipt.tasks || [];
  const byId = new Map(receiptTasks.map((task) => [String(task.task_id || ""), task]));
  const manifestIds = plan.manifest.tasks.map((entry) => entry.task_id);
  if (byId.size !== receiptTasks.length || JSON.stringify([...byId.keys()].sort()) !== JSON.stringify([...manifestIds].sort())) {
    throw new Error("execution-receipt.json 任务范围与 manifest 不一致");
  }
  return { receipt, byId, receiptSha256: sha256(receiptRaw) };
}

function resolveReceiptModel(receipt, receiptTask) {
  const selection = receiptTask?.model_selection || {};
  const requested = String(selection.requested_model || "").trim();
  const actual = String(selection.actual_model || "").trim();
  const mode = String(selection.mode || (requested ? "explicit" : "current")).trim();
  if (!new Set(["current", "explicit"]).has(mode)
    || !actual
    || (mode === "explicit" && (!requested || requested !== actual))
    || (mode === "current" && Boolean(requested))) {
    throw new Error(`execution-receipt.json 模型回读无效：${receiptTask?.task_id || "unknown"}`);
  }
  const declared = receipt.model || {};
  const declaredId = String(declared.id || "").trim();
  const declaredDisplayName = String(declared.display_name || "").trim();
  if (declaredId && !new Set([declaredId, declaredDisplayName]).has(actual)) {
    throw new Error(`execution-receipt.json 顶层模型与实际回读不一致：${declaredId}/${declaredDisplayName} vs ${actual}`);
  }
  return {
    model: { id: declaredId || actual, display_name: declaredDisplayName || actual },
    selection: {
      mode,
      requested_model: requested || null,
      actual_model: actual,
      method: selection.method || null,
    },
  };
}

async function inspectCandidateIntegrity(plan, taskId, scoreDir, receipt, receiptTask, receiptSha256, stage) {
  const expectedSha256 = String(receiptTask?.workspace?.final_sha256 || "");
  if (!/^[a-f0-9]{64}$/.test(expectedSha256)) throw new Error(`execution-receipt.json 缺少最终 workspace SHA-256：${taskId}`);
  const lockFile = join(scoreDir, "private-scoring", "candidate_artifact.json");
  const lock = loadCandidateArtifact(lockFile);
  const receiptModel = resolveReceiptModel(receipt, receiptTask);
  const lockSelectionMode = lock.model_selection?.mode
    || (lock.model_selection?.requested_model ? "explicit" : "current");
  if (lock.schema_version !== CANDIDATE_ARTIFACT_SCHEMA
    || lock.hash_algorithm !== TREE_HASH_ALGORITHM
    || lock.batch_id !== plan.manifest.batch_id
    || lock.task_id !== taskId
    || lock.harness_id !== plan.manifest.harness.id
    || lock.expected_sha256 !== expectedSha256
    || lock.execution_receipt?.sha256 !== receiptSha256
    || lock.model?.id !== receiptModel.model.id
    || lock.model?.display_name !== receiptModel.model.display_name
    || lockSelectionMode !== receiptModel.selection.mode
    || (lock.model_selection?.requested_model || null) !== receiptModel.selection.requested_model
    || lock.model_selection?.actual_model !== receiptModel.selection.actual_model
    || (lock.attempt_id && receiptTask.attempt_id && lock.attempt_id !== receiptTask.attempt_id)) {
    throw new Error(`candidate_artifact.json 与执行回执不一致：${taskId}`);
  }
  const executionWorkspace = await realpath(join(plan.root, "execution", "tasks", taskId, "workspace"));
  const scoreWorkspace = await realpath(join(scoreDir, "workspace"));
  const checks = [];
  try {
    checks.push(verifyWorkspace(executionWorkspace, expectedSha256, `${stage}:execution`));
    checks.push(verifyWorkspace(scoreWorkspace, expectedSha256, `${stage}:score`));
  } catch (error) {
    if (error?.integrityCheck) checks.push(error.integrityCheck);
    throw Object.assign(error, {
      candidateIntegrity: {
        stage,
        checked_at: new Date().toISOString(),
        expected_sha256: expectedSha256,
        checks,
        valid: false,
      },
    });
  }
  return {
    stage,
    checked_at: new Date().toISOString(),
    expected_sha256: expectedSha256,
    checks,
    valid: true,
  };
}

async function validatePreparedTask(plan, entry, receipt, receiptTask, receiptSha256) {
  const scoreDir = await realpath(join(plan.root, "score", "tasks", entry.task_id));
  if (!inside(join(plan.root, "score", "tasks"), scoreDir)) throw new Error(`评分目录越界：${entry.task_id}`);
  const required = [
    join(scoreDir, "workspace"),
    join(scoreDir, "private-scoring", "task_contract.json"),
    join(scoreDir, ".web-e2e-scoring-ready"),
  ];
  if (!(await isDirectory(required[0]))) throw new Error(`缺少评分 workspace：${entry.task_id}`);
  for (const filename of required.slice(1)) await stat(filename);
  const marker = (await readFile(required[2], "utf8")).split(/\r?\n/).filter(Boolean);
  if (JSON.stringify(marker) !== JSON.stringify([String(plan.manifest.batch_id), entry.task_id])) {
    throw new Error(`评分就绪标记不一致：${entry.task_id}`);
  }
  const contract = await loadJson(required[1]);
  if (contract.identity?.batch_id !== plan.manifest.batch_id || contract.identity?.task_id !== entry.task_id) {
    throw new Error(`task contract 身份不一致：${entry.task_id}`);
  }
  if (contract.identity?.harness?.id !== plan.manifest.harness.id) throw new Error(`task contract Harness 不一致：${entry.task_id}`);
  const receiptModel = resolveReceiptModel(receipt, receiptTask);
  if (contract.identity?.model?.id !== receiptModel.model.id
    || contract.identity?.model?.display_name !== receiptModel.model.display_name) {
    throw new Error(`task contract 模型与执行回读不一致：${entry.task_id}`);
  }
  const metricProfile = String(contract.metric_profile || "web-e2e-detailed-v1");
  if (entry.metric_profile && entry.metric_profile !== metricProfile) throw new Error(`task contract metric_profile 不一致：${entry.task_id}`);
  const candidateIntegrity = await inspectCandidateIntegrity(plan, entry.task_id, scoreDir, receipt, receiptTask, receiptSha256, "init");
  const prompt = promptForTask(entry.task_id);
  const promptFile = join(plan.promptRoot, `${entry.task_id}.md`);
  await mkdir(plan.promptRoot, { recursive: true });
  const existingPrompt = await readFile(promptFile, "utf8").catch((error) => error?.code === "ENOENT" ? null : Promise.reject(error));
  if (existingPrompt !== null && existingPrompt !== prompt) throw new Error(`评分 Prompt 已变化：${entry.task_id}`);
  if (existingPrompt === null) await writeFile(promptFile, prompt, { encoding: "utf8", mode: 0o600 });
  return {
    task_id: entry.task_id,
    task_name: entry.task_name || entry.task_id,
    metric_profile: metricProfile,
    model: receiptModel.model,
    score_dir: scoreDir,
    scoring_prompt_file: promptFile,
    scoring_prompt_sha256: sha256(prompt),
    phase: "PENDING_PROJECT",
    project_id: null,
    project_host_id: null,
    project_desktop_version: null,
    registration_method: null,
    thread_id: null,
    thread_host_id: null,
    score_timeout_seconds: null,
    max_retries: null,
    retry_count: 0,
    attempts: [],
    score_file: join(scoreDir, "private-scoring", "task_score.json"),
    candidate_integrity: {
      schema_version: CANDIDATE_ARTIFACT_SCHEMA,
      hash_algorithm: TREE_HASH_ALGORITHM,
      expected_sha256: candidateIntegrity.expected_sha256,
      lock_file: join(scoreDir, "private-scoring", "candidate_artifact.json"),
      checks: [candidateIntegrity],
    },
    error: null,
    timing: { project_registered_at: null, thread_created_at: null, finished_at: null },
  };
}

function nextTask(state) {
  if (state.tasks.some((task) => new Set(["FAILED", "TIMED_OUT"]).has(task.phase))) return null;
  return state.tasks.find((task) => task.phase !== "COMPLETED") || null;
}

function recommendedAction(state, at = new Date()) {
  if (state.tasks.every((task) => task.phase === "COMPLETED")) {
    if (state.submission?.status === "COMPLETED") return { type: "DONE", submission: state.submission };
    if (state.submission?.status === "FAILED") return { type: "RETRY_SUBMISSION", error: state.submission.error };
    return { type: "BUILD_SUBMISSION" };
  }
  const attention = state.tasks.find((task) => new Set(["FAILED", "TIMED_OUT"]).has(task.phase));
  if (attention) {
    const attempt = currentAttempt(attention);
    const retryAvailable = attention.retry_count < attention.max_retries;
    if (attempt?.terminal_status && retryAvailable) {
      return {
        type: "PREPARE_RETRY",
        task_id: attention.task_id,
        retry_count: attention.retry_count,
        max_retries: attention.max_retries,
      };
    }
    return {
      type: attempt?.deadline_exceeded_at && !attempt?.terminal_status
        ? "WAIT_FOR_TIMED_OUT_THREAD_TERMINAL"
        : "NEEDS_ATTENTION",
      task_id: attention.task_id,
      thread_id: attempt?.thread_id || attention.thread_id,
      host_id: attempt?.host_id || attention.thread_host_id,
      after_cursor: attempt?.wait_cursor || null,
      next_wait_sequence: (attempt?.wait_count || 0) + 1,
      error: attention.error,
    };
  }
  const task = state.tasks.find((entry) => entry.phase !== "COMPLETED");
  if (!task) return { type: "NEEDS_ATTENTION", error: "评分状态没有可执行任务" };
  if (task.phase === "PENDING_PROJECT") return { type: "REGISTER_PROJECT", task_id: task.task_id };
  if (task.phase === "PROJECT_REGISTERED") {
    if (state.preflight?.status !== "PASSED" || state.preflight?.task_id !== task.task_id) {
      return { type: "RUN_PREFLIGHT", task_id: task.task_id };
    }
    return { type: "CREATE_THREAD", task_id: task.task_id };
  }
  const attempt = currentAttempt(task);
  if (!attempt) return { type: "NEEDS_ATTENTION", task_id: task.task_id, error: "SCORING 任务缺少 attempt" };
  if (attempt.terminal_status === "COMPLETED") return { type: "VALIDATE_SCORE", task_id: task.task_id };
  if (attempt.last_wait_status === "NEEDS_ATTENTION") {
    return {
      type: "HANDLE_THREAD_ATTENTION",
      task_id: task.task_id,
      thread_id: attempt.thread_id,
      host_id: attempt.host_id,
      after_cursor: attempt.wait_cursor,
      next_wait_sequence: attempt.wait_count + 1,
    };
  }
  if (attempt.deadline_at && asDate(at).getTime() >= asDate(attempt.deadline_at).getTime()) {
    return { type: "MARK_TIMEOUT", task_id: task.task_id, deadline_at: attempt.deadline_at };
  }
  return {
    type: "WAIT_EXISTING_THREAD",
    task_id: task.task_id,
    thread_id: attempt.thread_id,
    host_id: attempt.host_id,
    after_cursor: attempt.wait_cursor,
    next_wait_sequence: attempt.wait_count + 1,
    deadline_at: attempt.deadline_at,
  };
}

function publicStatus(state) {
  return {
    schema_version: state.schema_version,
    batch_id: state.batch_id,
    harness_id: state.harness_id,
    phase: state.phase,
    score_slots: state.score_slots,
    score_timeout_seconds: state.score_timeout_seconds,
    max_retries: state.max_retries,
    preflight: state.preflight || null,
    score_skill: state.score_skill || null,
    submission: state.submission || null,
    recommended_action: recommendedAction(state),
    next_task: nextTask(state),
    tasks: state.tasks,
  };
}

function refreshPhase(state) {
  if (state.tasks.some((task) => new Set(["FAILED", "TIMED_OUT"]).has(task.phase))) {
    state.phase = "NEEDS_ATTENTION";
  } else if (state.tasks.every((task) => task.phase === "COMPLETED")) {
    if (state.submission?.status === "COMPLETED") {
      state.phase = "COMPLETED";
      state.finished_at ||= new Date().toISOString();
    } else if (state.submission?.status === "FAILED") state.phase = "NEEDS_ATTENTION";
    else state.phase = "FINALIZING";
  } else if (state.tasks.some((task) => task.phase === "SCORING")) state.phase = "SCORING";
  else state.phase = "PREPARED";
}

export async function initialize(packageRoot, selectedTaskIds = [], options = {}) {
  const plan = await resolvePackage(packageRoot);
  const { receipt, byId: receiptTasks, receiptSha256 } = await loadExecutionReceipt(plan);
  const ids = selectedTaskIds.length ? selectedTaskIds : plan.manifest.tasks.map((entry) => entry.task_id);
  if (new Set(ids).size !== ids.length) throw new Error("--task-id 不能重复");
  const byId = new Map(plan.manifest.tasks.map((entry) => [entry.task_id, entry]));
  const entries = ids.map((taskId) => {
    const entry = byId.get(taskId);
    if (!entry) throw new Error(`manifest 中没有任务：${taskId}`);
    return entry;
  });
  const tasks = [];
  for (const entry of entries) {
    tasks.push(await validatePreparedTask(plan, entry, receipt, receiptTasks.get(entry.task_id), receiptSha256));
  }
  const scoreTimeoutSeconds = options.scoreTimeoutSeconds ?? DEFAULT_SCORE_TIMEOUT_SECONDS;
  const maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
  if (!Number.isInteger(scoreTimeoutSeconds) || scoreTimeoutSeconds < 1) throw new Error("scoreTimeoutSeconds 必须是正整数");
  if (!Number.isInteger(maxRetries) || maxRetries < 0) throw new Error("maxRetries 必须是非负整数");
  for (const task of tasks) {
    task.score_timeout_seconds = scoreTimeoutSeconds;
    task.max_retries = maxRetries;
  }
  const existingRaw = await loadJsonIfExists(plan.stateFile);
  const existing = existingRaw ? normalizeState(existingRaw) : null;
  if (existing) {
    if (existing.schema_version !== STATE_SCHEMA || existing.batch_id !== plan.manifest.batch_id || existing.harness_id !== plan.manifest.harness.id) {
      throw new Error("已有评分状态身份不一致");
    }
    if (options.scoreTimeoutSeconds !== undefined && existing.score_timeout_seconds !== scoreTimeoutSeconds) {
      throw new Error("已有评分状态的 score_timeout_seconds 不可变");
    }
    if (options.maxRetries !== undefined && existing.max_retries !== maxRetries) {
      throw new Error("已有评分状态的 max_retries 不可变");
    }
    if (JSON.stringify(existing.tasks.map((task) => task.task_id)) !== JSON.stringify(ids)) throw new Error("已有评分状态的任务范围或顺序不可变");
    for (let index = 0; index < tasks.length; index += 1) {
      if (existing.tasks[index].score_dir !== tasks[index].score_dir
        || existing.tasks[index].scoring_prompt_sha256 !== tasks[index].scoring_prompt_sha256
        || existing.tasks[index].model?.id !== tasks[index].model.id
        || existing.tasks[index].candidate_integrity?.expected_sha256 !== tasks[index].candidate_integrity.expected_sha256) {
        throw new Error(`已有评分状态路径或 Prompt 不一致：${tasks[index].task_id}`);
      }
      existing.tasks[index].candidate_integrity.checks.push(tasks[index].candidate_integrity.checks[0]);
    }
    existing.history.push({
      event: "CANDIDATE_INTEGRITY_RECHECKED",
      at: new Date().toISOString(),
      stage: "init-resume",
      task_ids: ids,
      execution_receipt_generated_at: receipt.generated_at || null,
    });
    await saveControl(plan, existing);
    return { plan, state: existing };
  }
  const now = new Date().toISOString();
  const state = {
    schema_version: STATE_SCHEMA,
    schema_revision: STATE_REVISION,
    batch_id: plan.manifest.batch_id,
    harness_id: plan.manifest.harness.id,
    score_slots: 1,
    score_timeout_seconds: scoreTimeoutSeconds,
    max_retries: maxRetries,
    phase: "PREPARED",
    created_at: now,
    updated_at: now,
    finished_at: null,
    tasks,
    preflight: { status: "PENDING", checked_at: null, task_id: null },
    score_skill: null,
    submission: submissionState(),
    execution_receipt: {
      schema_version: receipt.schema_version,
      generated_at: receipt.generated_at || null,
      run_id: receipt.run_id || null,
    },
    history: [{ event: "SCORING_PREPARED", at: now, task_ids: ids }],
  };
  await atomicWriteJson(plan.stateFile, state);
  await atomicWriteJson(plan.registryFile, {
    schema_version: REGISTRY_SCHEMA,
    batch_id: state.batch_id,
    desktop_version: null,
    updated_at: now,
    projects: [],
  });
  return { plan, state };
}

async function loadControl(packageRoot) {
  const plan = await resolvePackage(packageRoot);
  const state = normalizeState(await loadJson(plan.stateFile));
  if (state.schema_version !== STATE_SCHEMA || state.batch_id !== plan.manifest.batch_id) throw new Error("评分状态身份不一致");
  return { plan, state };
}

function requireTask(state, taskId) {
  const task = state.tasks.find((entry) => entry.task_id === taskId);
  if (!task) throw new Error(`评分状态中没有任务：${taskId}`);
  return task;
}

async function saveControl(plan, state) {
  state.updated_at = new Date().toISOString();
  refreshPhase(state);
  await atomicWriteJson(plan.stateFile, state);
}

async function verifyTaskCandidateOrFail(plan, state, task, stage) {
  try {
    const { receipt, byId, receiptSha256 } = await loadExecutionReceipt(plan);
    const check = await inspectCandidateIntegrity(
      plan,
      task.task_id,
      task.score_dir,
      receipt,
      byId.get(task.task_id),
      receiptSha256,
      stage,
    );
    task.candidate_integrity.checks.push(check);
    return check;
  } catch (error) {
    const now = new Date().toISOString();
    const message = error instanceof Error ? error.message : String(error);
    if (error?.candidateIntegrity && task.candidate_integrity?.checks) {
      task.candidate_integrity.checks.push(error.candidateIntegrity);
    }
    task.phase = "FAILED";
    task.error = message;
    task.timing.finished_at = now;
    state.preflight = { status: "FAILED", checked_at: now, task_id: task.task_id, error: message };
    state.history.push({ event: "CANDIDATE_INTEGRITY_FAILED", at: now, task_id: task.task_id, stage, error: message });
    await saveControl(plan, state);
    throw error;
  }
}

export async function recordProject(packageRoot, taskId, project) {
  const { plan, state } = await loadControl(packageRoot);
  const task = requireTask(state, taskId);
  if (!project.projectId || !project.hostId || !project.projectPath || !project.desktopVersion || !project.registrationMethod) {
    throw new Error("projectId、hostId、projectPath、desktopVersion 和 registrationMethod 均不能为空");
  }
  if (!REGISTRATION_METHODS.has(project.registrationMethod)) throw new Error(`不支持的项目注册方式：${project.registrationMethod}`);
  const canonical = await realpath(resolve(project.projectPath));
  if (canonical !== task.score_dir) throw new Error(`projectPath 与评分目录不一致：${canonical}`);
  if (task.project_id && (
    task.project_id !== project.projectId
    || task.project_host_id !== project.hostId
    || task.project_desktop_version !== project.desktopVersion
    || task.registration_method !== project.registrationMethod
  )) throw new Error("任务已绑定不同项目或注册环境");
  if (task.phase === "COMPLETED") return publicStatus(state);
  const now = new Date().toISOString();
  task.project_id = project.projectId;
  task.project_host_id = project.hostId;
  task.project_desktop_version = project.desktopVersion;
  task.registration_method = project.registrationMethod;
  task.phase = task.thread_id ? "SCORING" : "PROJECT_REGISTERED";
  task.timing.project_registered_at ||= now;
  state.preflight = { status: "PENDING", checked_at: null, task_id: taskId };
  state.history.push({
    event: "PROJECT_REGISTERED",
    at: now,
    task_id: taskId,
    project_id: project.projectId,
    host_id: project.hostId,
    path: canonical,
    desktop_version: project.desktopVersion,
    registration_method: project.registrationMethod,
  });
  const registry = await loadJson(plan.registryFile);
  if (registry.desktop_version && registry.desktop_version !== project.desktopVersion) throw new Error("同一批次不能混用不同 Codex Desktop 版本");
  registry.desktop_version = project.desktopVersion;
  const existing = registry.projects.find((entry) => entry.task_id === taskId);
  const value = {
    task_id: taskId,
    project_id: project.projectId,
    host_id: project.hostId,
    path: canonical,
    path_sha256: sha256(canonical),
    desktop_version: project.desktopVersion,
    registration_method: project.registrationMethod,
    registered_at: now,
  };
  if (existing && (existing.project_id !== value.project_id || existing.host_id !== value.host_id || existing.path !== value.path)) {
    throw new Error("project-registry 已包含不同映射");
  }
  if (!existing) registry.projects.push(value);
  registry.updated_at = now;
  await atomicWriteJson(plan.registryFile, registry);
  await saveControl(plan, state);
  return publicStatus(state);
}

export async function preflight(packageRoot, options) {
  const { plan, state } = await loadControl(packageRoot);
  if (!options.desktopVersion || !options.scoreSkillDir) throw new Error("desktopVersion 和 scoreSkillDir 均不能为空");
  const task = nextTask(state);
  if (!task) throw new Error("没有待评分任务");
  if (!task.project_id || !task.project_host_id) throw new Error(`下一题尚未注册 Desktop 项目：${task.task_id}`);
  if (task.project_desktop_version !== options.desktopVersion) {
    throw new Error(`Codex Desktop 版本与项目注册时不一致：${options.desktopVersion} vs ${task.project_desktop_version}`);
  }
  if (task.registration_method === "renderer-bridge" && options.allowRendererBridge !== true) {
    throw new Error("当前项目使用 renderer-bridge 注册，必须显式传入 --allow-renderer-bridge");
  }
  await verifyTaskCandidateOrFail(plan, state, task, "preflight");

  const registry = await loadJson(plan.registryFile);
  if (registry.desktop_version !== options.desktopVersion) throw new Error("Codex Desktop 版本与 project-registry 不一致");
  const registryEntry = registry.projects.find((entry) => entry.task_id === task.task_id);
  if (!registryEntry
    || registryEntry.project_id !== task.project_id
    || registryEntry.host_id !== task.project_host_id
    || registryEntry.path !== task.score_dir
    || registryEntry.desktop_version !== options.desktopVersion
    || registryEntry.registration_method !== task.registration_method) {
    throw new Error(`project-registry 与下一题状态不一致：${task.task_id}`);
  }

  const skillRoot = await realpath(resolve(options.scoreSkillDir));
  const metadataFile = join(skillRoot, "skill-metadata.json");
  const metadataRaw = await readFile(metadataFile, "utf8");
  const metadata = JSON.parse(metadataRaw);
  if (metadata.schema_version !== SCORE_SKILL_SCHEMA || metadata.name !== "score-web-e2e" || !metadata.version) {
    throw new Error(`评分 Skill 元数据无效：${metadataFile}`);
  }
  const expected = plan.manifest.scoring_skill;
  if (!expected || expected.schema_version !== SCORE_SKILL_SCHEMA || !expected.version) {
    throw new Error("manifest.json 缺少可校验的 scoring_skill 元数据");
  }
  if (metadata.version !== expected.version || metadata.name !== expected.name) {
    throw new Error(`评分 Skill 版本不一致：已安装 ${metadata.name}@${metadata.version}，批次要求 ${expected.name}@${expected.version}`);
  }
  if (metadata.task_score_schema !== SCORE_SCHEMA) throw new Error(`评分 Skill task_score schema 不兼容：${metadata.task_score_schema}`);
  if (!Array.isArray(metadata.supported_metric_profiles) || !metadata.supported_metric_profiles.includes(task.metric_profile)) {
    throw new Error(`评分 Skill ${metadata.version} 不支持 metric_profile：${task.metric_profile}`);
  }
  if (plan.manifest.metric_profile && plan.manifest.metric_profile !== task.metric_profile) {
    throw new Error(`manifest metric_profile 与下一题不一致：${plan.manifest.metric_profile} vs ${task.metric_profile}`);
  }
  const contractFile = join(task.score_dir, "private-scoring", "task_contract.json");
  const contractRaw = await readFile(contractFile, "utf8");
  const contract = JSON.parse(contractRaw);
  const contractProfile = String(contract.metric_profile || "web-e2e-detailed-v1");
  if (contractProfile !== task.metric_profile) throw new Error(`task contract metric_profile 已变化：${task.task_id}`);

  const now = new Date().toISOString();
  state.preflight = {
    status: "PASSED",
    checked_at: now,
    task_id: task.task_id,
    desktop_version: options.desktopVersion,
    registration_method: task.registration_method,
    score_skill: {
      path: skillRoot,
      version: metadata.version,
      metadata_sha256: sha256(metadataRaw),
    },
    metric_profile: task.metric_profile,
    task_contract_sha256: sha256(contractRaw),
  };
  const scoreSkillBinding = {
    path: skillRoot,
    version: metadata.version,
    metadata_sha256: sha256(metadataRaw),
  };
  if (state.score_skill && (
    state.score_skill.path !== scoreSkillBinding.path
    || state.score_skill.version !== scoreSkillBinding.version
    || state.score_skill.metadata_sha256 !== scoreSkillBinding.metadata_sha256
  )) {
    throw new Error("同一批次不能切换评分 Skill 路径、版本或元数据");
  }
  state.score_skill = scoreSkillBinding;
  state.history.push({
    event: "SCORING_PREFLIGHT_PASSED",
    at: now,
    task_id: task.task_id,
    desktop_version: options.desktopVersion,
    registration_method: task.registration_method,
    score_skill_version: metadata.version,
    metric_profile: task.metric_profile,
  });
  await saveControl(plan, state);
  return publicStatus(state);
}

export async function recordThread(packageRoot, taskId, thread, options = {}) {
  const { plan, state } = await loadControl(packageRoot);
  const task = requireTask(state, taskId);
  if (!task.project_id) throw new Error("必须先记录 projectId");
  if (!thread.threadId || !thread.hostId) throw new Error("threadId 和 hostId 均不能为空");
  if (task.phase === "COMPLETED" && task.thread_id === thread.threadId && task.thread_host_id === thread.hostId) return publicStatus(state);
  const active = state.tasks.find((entry) => entry.phase === "SCORING" && entry.task_id !== taskId);
  if (active) throw new Error(`score_slots=1，已有评分任务运行中：${active.task_id}`);
  const expected = nextTask(state);
  if (expected?.task_id !== taskId) throw new Error(`只能为下一题创建会话：${expected?.task_id || "无"}`);
  if (state.preflight?.status !== "PASSED" || state.preflight.task_id !== taskId) {
    throw new Error(`必须先通过当前题评分 preflight：${taskId}`);
  }
  await verifyTaskCandidateOrFail(plan, state, task, "record-thread");
  if (task.thread_id && (task.thread_id !== thread.threadId || task.thread_host_id !== thread.hostId)) throw new Error("任务已绑定不同会话");
  const existingAttempt = task.thread_id ? currentAttempt(task) : null;
  if (existingAttempt?.thread_id && (
    existingAttempt.thread_id !== thread.threadId || existingAttempt.host_id !== thread.hostId
  )) throw new Error("当前 attempt 已绑定不同会话");
  const now = asDate(options.now).toISOString();
  task.thread_id = thread.threadId;
  task.thread_host_id = thread.hostId;
  task.phase = "SCORING";
  task.timing.thread_created_at ||= now;
  if (!existingAttempt) {
    task.attempts.push(normalizeAttempt({
      attempt_number: task.retry_count + 1,
      thread_id: thread.threadId,
      host_id: thread.hostId,
      created_at: now,
      deadline_at: deadlineFrom(now, task.score_timeout_seconds),
    }, task, state));
    state.history.push({
      event: "THREAD_RECORDED",
      at: now,
      task_id: taskId,
      attempt_number: task.retry_count + 1,
      thread_id: thread.threadId,
      host_id: thread.hostId,
      deadline_at: deadlineFrom(now, task.score_timeout_seconds),
    });
  }
  await saveControl(plan, state);
  return publicStatus(state);
}

export async function recordWait(packageRoot, taskId, observation, options = {}) {
  const { plan, state } = await loadControl(packageRoot);
  const task = requireTask(state, taskId);
  const attempt = currentAttempt(task);
  if (!attempt || !attempt.thread_id) throw new Error("任务没有已记录的评分会话");
  if (!new Set(["SCORING", "TIMED_OUT"]).has(task.phase)) throw new Error(`当前任务状态不能记录等待结果：${task.phase}`);
  const waitStatus = String(observation.waitStatus || "").toUpperCase();
  const waitCursor = String(observation.waitCursor || "");
  const waitSequence = Number(observation.waitSequence);
  if (!WAIT_STATUSES.has(waitStatus)) throw new Error(`waitStatus 无效：${waitStatus || "空"}`);
  if (!waitCursor) throw new Error("waitCursor 不能为空");
  if (!Number.isInteger(waitSequence) || waitSequence < 1) throw new Error("waitSequence 必须是正整数");
  const expectedSequence = attempt.wait_count + 1;
  if (waitSequence === attempt.last_wait_sequence) {
    if (attempt.wait_cursor === waitCursor
      && attempt.last_wait_status === waitStatus
      && (attempt.last_wait_error || "") === String(observation.waitError || "")) return publicStatus(state);
    throw new Error(`waitSequence ${waitSequence} 已记录但内容不一致`);
  }
  if (waitSequence !== expectedSequence) throw new Error(`waitSequence 应为 ${expectedSequence}，实际为 ${waitSequence}`);
  const now = asDate(options.now).toISOString();
  attempt.wait_count = waitSequence;
  attempt.last_wait_sequence = waitSequence;
  attempt.wait_cursor = waitCursor;
  attempt.last_wait_status = waitStatus;
  attempt.last_wait_error = observation.waitError || null;
  attempt.last_observed_at = now;
  state.history.push({
    event: "THREAD_WAIT_OBSERVED",
    at: now,
    task_id: taskId,
    attempt_number: attempt.attempt_number,
    thread_id: attempt.thread_id,
    wait_sequence: waitSequence,
    wait_cursor: waitCursor,
    wait_status: waitStatus,
    error: observation.waitError || null,
  });
  if (!attempt.deadline_exceeded_at && attempt.deadline_at && asDate(now).getTime() >= asDate(attempt.deadline_at).getTime()) {
    attempt.deadline_exceeded_at = now;
    task.phase = "TIMED_OUT";
    task.error = `评分任务超过 deadline：${attempt.deadline_at}`;
    state.history.push({
      event: "SCORING_DEADLINE_EXCEEDED",
      at: now,
      task_id: taskId,
      attempt_number: attempt.attempt_number,
      thread_id: attempt.thread_id,
      deadline_at: attempt.deadline_at,
    });
  }
  if (TERMINAL_THREAD_STATUSES.has(waitStatus)) {
    attempt.terminal_status = waitStatus;
    attempt.finished_at = now;
    if (waitStatus !== "COMPLETED" && !attempt.deadline_exceeded_at) {
      task.phase = "FAILED";
      task.error = observation.waitError || `评分任务终态：${waitStatus}`;
      task.timing.finished_at = now;
    }
  }
  await saveControl(plan, state);
  return publicStatus(state);
}

export async function markTimeout(packageRoot, taskId, options = {}) {
  const { plan, state } = await loadControl(packageRoot);
  const task = requireTask(state, taskId);
  const attempt = currentAttempt(task);
  if (!attempt || !attempt.deadline_at) throw new Error("任务没有可检查的评分 deadline");
  if (attempt.terminal_status) throw new Error("评分任务已有终态，不能再标记超时");
  const now = asDate(options.now);
  if (now.getTime() < asDate(attempt.deadline_at).getTime()) throw new Error(`评分 deadline 尚未到达：${attempt.deadline_at}`);
  if (!attempt.deadline_exceeded_at) {
    attempt.deadline_exceeded_at = now.toISOString();
    task.phase = "TIMED_OUT";
    task.error = `评分任务超过 deadline：${attempt.deadline_at}`;
    state.history.push({
      event: "SCORING_DEADLINE_EXCEEDED",
      at: now.toISOString(),
      task_id: taskId,
      attempt_number: attempt.attempt_number,
      thread_id: attempt.thread_id,
      deadline_at: attempt.deadline_at,
    });
    await saveControl(plan, state);
  }
  return publicStatus(state);
}

export async function prepareRetry(packageRoot, taskId, retryReason) {
  if (!retryReason) throw new Error("retryReason 不能为空");
  const { plan, state } = await loadControl(packageRoot);
  const task = requireTask(state, taskId);
  const attempt = currentAttempt(task);
  if (!new Set(["FAILED", "TIMED_OUT"]).has(task.phase)) throw new Error(`当前任务状态不能重试：${task.phase}`);
  if (!attempt?.terminal_status) throw new Error("原评分任务终态尚未确认，禁止创建重试任务");
  if (task.retry_count >= task.max_retries) throw new Error(`评分任务已达到最大重试次数：${task.max_retries}`);
  if (await stat(task.score_file).catch(() => null)) throw new Error("已有 task_score.json，必须先审计而不能直接重试");
  const privateRoot = join(task.score_dir, "private-scoring");
  const unsafeRetryArtifacts = [
    "score_input.json",
    "runtime-workspace",
    "runtime-state.json",
    "screenshot-receiver-state.json",
    "runtime-port-override.json",
    "evidence",
  ];
  for (const name of unsafeRetryArtifacts) {
    if (await stat(join(privateRoot, name)).catch(() => null)) {
      throw new Error(`评分 attempt 已产生 ${name}，必须隔离归档后才能重试`);
    }
  }
  await verifyTaskCandidateOrFail(plan, state, task, "prepare-retry");
  const now = new Date().toISOString();
  task.retry_count += 1;
  task.thread_id = null;
  task.thread_host_id = null;
  task.phase = "PROJECT_REGISTERED";
  task.error = null;
  task.timing.thread_created_at = null;
  task.timing.finished_at = null;
  state.preflight = { status: "PENDING", checked_at: null, task_id: taskId };
  state.history.push({
    event: "SCORING_RETRY_PREPARED",
    at: now,
    task_id: taskId,
    completed_attempt_number: attempt.attempt_number,
    next_attempt_number: task.retry_count + 1,
    reason: retryReason,
  });
  await saveControl(plan, state);
  return publicStatus(state);
}

export async function validateTaskScore(plan, task) {
  const score = await loadJson(task.score_file);
  const manifestEntry = plan.manifest.tasks.find((entry) => entry.task_id === task.task_id);
  const { receipt, byId } = await loadExecutionReceipt(plan);
  const receiptModel = resolveReceiptModel(receipt, byId.get(task.task_id)).model;
  if (score.schema_version !== SCORE_SCHEMA) throw new Error(`task_score schema 不兼容：${task.task_id}`);
  if (score.identity?.batch_id !== plan.manifest.batch_id || score.identity?.task_id !== task.task_id) throw new Error(`task_score 身份不一致：${task.task_id}`);
  if (score.identity?.harness?.id !== plan.manifest.harness.id) throw new Error(`task_score Harness 不一致：${task.task_id}`);
  if (score.identity?.model?.id !== receiptModel.id
    || score.identity?.model?.display_name !== receiptModel.display_name) {
    throw new Error(`task_score 模型与执行回读不一致：${task.task_id}`);
  }
  if (String(score.metric_profile || "web-e2e-detailed-v1") !== task.metric_profile) {
    throw new Error(`task_score metric_profile 不一致：${task.task_id}`);
  }
  if (manifestEntry.task_sha256 && score.provenance?.task_sha256 !== manifestEntry.task_sha256) throw new Error(`task_score task_sha256 不一致：${task.task_id}`);
  if (manifestEntry.workspace_exec_sha256 && score.provenance?.workspace_exec_sha256 !== manifestEntry.workspace_exec_sha256) throw new Error(`task_score workspace_exec_sha256 不一致：${task.task_id}`);
  if (score.provenance?.candidate_workspace_sha256 !== task.candidate_integrity?.expected_sha256) {
    throw new Error(`task_score candidate_workspace_sha256 与冻结产物不一致：${task.task_id}`);
  }
  if (score.execution?.status === "pending") throw new Error(`task_score 执行状态仍为 pending：${task.task_id}`);
  const scoringDir = dirname(task.score_file);
  const evidencePaths = [];
  for (const criterion of score.evaluation?.criteria || []) for (const evidence of criterion.evidence || []) evidencePaths.push(evidence?.path);
  for (const screenshot of score.evaluation?.aesthetic?.screenshots || []) evidencePaths.push(screenshot?.path);
  for (const rawValue of evidencePaths) {
    const raw = String(rawValue || "");
    const parts = raw.split(/[\\/]+/);
    if (!raw || isAbsolute(raw) || parts.includes("..") || parts[0] !== "evidence") throw new Error(`评分证据路径非法：${task.task_id}: ${raw}`);
    await stat(join(scoringDir, ...parts));
  }
  return score;
}

export async function markComplete(packageRoot, taskId) {
  const { plan, state } = await loadControl(packageRoot);
  const task = requireTask(state, taskId);
  if (!task.thread_id) throw new Error("任务没有已记录的评分会话");
  const attempt = currentAttempt(task);
  if (attempt?.deadline_exceeded_at) throw new Error("评分任务已超过 deadline，不能接受迟到结果");
  if (!attempt || (attempt.terminal_status !== "COMPLETED" && attempt.terminal_status !== "SCORE_VALIDATED")) {
    throw new Error(`必须先记录评分任务 COMPLETED 终态：${attempt?.terminal_status || "未记录"}`);
  }
  await verifyTaskCandidateOrFail(plan, state, task, "mark-complete");
  await validateTaskScore(plan, task);
  if (task.phase === "COMPLETED") {
    if (state.tasks.every((entry) => entry.phase === "COMPLETED") && state.submission.status !== "COMPLETED") {
      return buildSubmissionFromState(plan, state);
    }
    return publicStatus(state);
  }
  const now = new Date().toISOString();
  task.phase = "COMPLETED";
  task.error = null;
  task.timing.finished_at = now;
  if (attempt) {
    attempt.terminal_status ||= "COMPLETED";
    attempt.finished_at ||= now;
    attempt.score_validated_at = now;
  }
  state.history.push({ event: "TASK_SCORE_VALIDATED", at: now, task_id: taskId, thread_id: task.thread_id });
  state.preflight = { status: "PENDING", checked_at: null, task_id: nextTask(state)?.task_id || null };
  await saveControl(plan, state);
  if (state.tasks.every((entry) => entry.phase === "COMPLETED")) return buildSubmissionFromState(plan, state);
  return publicStatus(state);
}

export async function markFailed(packageRoot, taskId, errorMessage) {
  if (!errorMessage) throw new Error("--error 不能为空");
  const { plan, state } = await loadControl(packageRoot);
  const task = requireTask(state, taskId);
  if (task.phase === "COMPLETED") throw new Error("已完成任务不能改为失败");
  const now = new Date().toISOString();
  task.phase = "FAILED";
  task.error = errorMessage;
  task.timing.finished_at = now;
  const attempt = currentAttempt(task);
  if (attempt) {
    attempt.finished_at ||= now;
    attempt.last_wait_error ||= errorMessage;
  }
  state.history.push({ event: "SCORING_FAILED", at: now, task_id: taskId, thread_id: task.thread_id, error: errorMessage });
  await saveControl(plan, state);
  return publicStatus(state);
}

function comparableSubmission(value) {
  return {
    schema_version: value?.schema_version,
    batch_id: value?.batch_id,
    source_revision: value?.source_revision ?? null,
    metric_profile: value?.metric_profile,
    unit: value?.unit,
    task_ids: value?.task_ids,
    candidate_artifacts: (value?.candidate_artifacts || []).map(({ checked_at: _checkedAt, ...entry }) => entry),
    tasks: value?.tasks,
  };
}

function assertEquivalentSubmission(existing, current) {
  if (existing?.schema_version !== SUBMISSION_SCHEMA || existing?.batch_id !== current?.batch_id) {
    throw new Error("已有 submission.json 身份或 schema 无效");
  }
  if (JSON.stringify(comparableSubmission(existing)) !== JSON.stringify(comparableSubmission(current))) {
    throw new Error("已有 submission.json 与当前评分结果不一致");
  }
}

async function loadSubmissionBuilder(state, scoreSkillDir) {
  const requestedRoot = scoreSkillDir || state.score_skill?.path;
  if (!requestedRoot) throw new Error("缺少已通过 preflight 的 score-web-e2e Skill 路径");
  const skillRoot = await realpath(resolve(requestedRoot));
  const metadataFile = join(skillRoot, "skill-metadata.json");
  const metadataRaw = await readFile(metadataFile, "utf8");
  const metadata = JSON.parse(metadataRaw);
  if (metadata.schema_version !== SCORE_SKILL_SCHEMA || metadata.name !== "score-web-e2e" || !metadata.version) {
    throw new Error(`评分 Skill 元数据无效：${metadataFile}`);
  }
  const binding = { path: skillRoot, version: metadata.version, metadata_sha256: sha256(metadataRaw) };
  if (state.score_skill && (
    state.score_skill.path !== binding.path
    || state.score_skill.version !== binding.version
    || state.score_skill.metadata_sha256 !== binding.metadata_sha256
  )) throw new Error("生成 submission 时评分 Skill 与 preflight 绑定不一致");
  state.score_skill ||= binding;
  const script = await realpath(join(skillRoot, "scripts", "build_submission.mjs"));
  if (!inside(skillRoot, script)) throw new Error("build_submission.mjs 不在评分 Skill 目录内");
  const module = await import(`${pathToFileURL(script).href}?metadata=${binding.metadata_sha256}`);
  if (typeof module.buildSubmission !== "function") throw new Error("评分 Skill 未导出 buildSubmission");
  return module.buildSubmission;
}

async function buildSubmissionFromState(plan, state, options = {}) {
  if (!state.tasks.every((task) => task.phase === "COMPLETED")) throw new Error("仍有题目未完成，不能生成 submission");
  const outputFile = join(plan.root, "submission.json");
  const pendingFile = join(plan.controlRoot, "pending-submission.json");
  try {
    const builder = await loadSubmissionBuilder(state, options.scoreSkillDir);
    const current = builder(plan.root);
    if (current?.schema_version !== SUBMISSION_SCHEMA || current?.batch_id !== state.batch_id) {
      throw new Error("buildSubmission 返回的 schema 或 batch_id 无效");
    }
    const existingOutput = await readFile(outputFile).catch((error) => error?.code === "ENOENT" ? null : Promise.reject(error));
    if (existingOutput) {
      const existing = JSON.parse(existingOutput.toString("utf8"));
      assertEquivalentSubmission(existing, current);
      const outputSha256 = sha256(existingOutput);
      if (state.submission.status === "GENERATING" && state.submission.sha256 && state.submission.sha256 !== outputSha256) {
        throw new Error("submission.json 与生成中状态记录的 SHA-256 不一致");
      }
      const now = new Date().toISOString();
      state.submission = {
        ...state.submission,
        status: "COMPLETED",
        output_file: outputFile,
        sha256: outputSha256,
        pending_file: null,
        generated_at: now,
        error: null,
        adopted_existing: state.submission.status !== "GENERATING",
      };
      state.history.push({ event: "SUBMISSION_VERIFIED", at: now, output_file: outputFile, sha256: outputSha256 });
      await saveControl(plan, state);
      return publicStatus(state);
    }
    if (state.submission.status === "COMPLETED") throw new Error("状态记录 submission 已完成但文件不存在");
    if (state.submission.status === "GENERATING") {
      const pendingRaw = await readFile(pendingFile).catch((error) => error?.code === "ENOENT" ? null : Promise.reject(error));
      if (!pendingRaw) throw new Error("submission 生成中断且待发布文件不存在");
      const pending = JSON.parse(pendingRaw.toString("utf8"));
      assertEquivalentSubmission(pending, current);
      if (sha256(pendingRaw) !== state.submission.sha256) throw new Error("待发布 submission SHA-256 与状态不一致");
      await rename(pendingFile, outputFile);
    } else {
      const raw = `${JSON.stringify(current, null, 2)}\n`;
      const now = new Date().toISOString();
      await atomicWriteJson(pendingFile, current);
      state.submission = {
        ...state.submission,
        status: "GENERATING",
        attempt_count: state.submission.attempt_count + 1,
        output_file: outputFile,
        sha256: sha256(raw),
        pending_file: pendingFile,
        started_at: now,
        generated_at: null,
        error: null,
        adopted_existing: false,
      };
      state.history.push({ event: "SUBMISSION_GENERATING", at: now, output_file: outputFile, sha256: state.submission.sha256 });
      await saveControl(plan, state);
      await rename(pendingFile, outputFile);
    }
    const outputRaw = await readFile(outputFile);
    if (sha256(outputRaw) !== state.submission.sha256) throw new Error("发布后的 submission SHA-256 与状态不一致");
    const now = new Date().toISOString();
    state.submission.status = "COMPLETED";
    state.submission.pending_file = null;
    state.submission.generated_at = now;
    state.submission.error = null;
    state.history.push({ event: "SUBMISSION_COMPLETED", at: now, output_file: outputFile, sha256: state.submission.sha256 });
    await saveControl(plan, state);
    return publicStatus(state);
  } catch (error) {
    const now = new Date().toISOString();
    state.submission.status = "FAILED";
    state.submission.error = error instanceof Error ? error.message : String(error);
    state.history.push({ event: "SUBMISSION_FAILED", at: now, error: state.submission.error });
    await saveControl(plan, state);
    throw error;
  }
}

export async function buildSubmissionControl(packageRoot, options = {}) {
  const { plan, state } = await loadControl(packageRoot);
  if (state.submission.status === "COMPLETED") {
    const raw = state.submission.output_file && /^[a-f0-9]{64}$/.test(String(state.submission.sha256 || ""))
      ? await readFile(state.submission.output_file).catch((error) => error?.code === "ENOENT" ? null : Promise.reject(error))
      : null;
    if (raw && sha256(raw) === state.submission.sha256) return publicStatus(state);
    const message = raw ? "submission.json 完成后发生漂移" : "submission.json 完成后丢失";
    state.submission.status = "FAILED";
    state.submission.error = message;
    state.history.push({ event: "SUBMISSION_FAILED", at: new Date().toISOString(), error: message });
    await saveControl(plan, state);
    throw new Error(message);
  }
  return buildSubmissionFromState(plan, state, options);
}

export async function status(packageRoot) {
  const { state } = await loadControl(packageRoot);
  return publicStatus(state);
}

export async function resume(packageRoot) {
  const { plan, state } = await loadControl(packageRoot);
  state.history.push({ event: "CONTROL_RESUMED", at: new Date().toISOString(), action: recommendedAction(state).type });
  await saveControl(plan, state);
  return publicStatus(state);
}

async function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    if (args.help) {
      process.stdout.write(usage());
      return;
    }
    let result;
    if (args.command === "init") result = publicStatus((await initialize(args.packageRoot, args.taskIds, {
      scoreTimeoutSeconds: args.scoreTimeoutSeconds,
      maxRetries: args.maxRetries,
    })).state);
    else if (args.command === "status") result = await status(args.packageRoot);
    else if (args.command === "resume") result = await resume(args.packageRoot);
    else if (args.command === "build-submission") result = await buildSubmissionControl(args.packageRoot, { scoreSkillDir: args.scoreSkillDir });
    else if (args.command === "preflight") result = await preflight(args.packageRoot, {
      desktopVersion: args.desktopVersion,
      scoreSkillDir: args.scoreSkillDir,
      allowRendererBridge: args.allowRendererBridge,
    });
    else {
      if (args.taskIds.length !== 1) throw new Error(`${args.command} 必须且只能提供一个 --task-id`);
      const taskId = args.taskIds[0];
      if (args.command === "record-project") result = await recordProject(args.packageRoot, taskId, {
        projectId: args.projectId,
        projectPath: args.projectPath,
        hostId: args.hostId,
        desktopVersion: args.desktopVersion,
        registrationMethod: args.registrationMethod,
      });
      else if (args.command === "record-thread") result = await recordThread(args.packageRoot, taskId, { threadId: args.threadId, hostId: args.hostId });
      else if (args.command === "record-wait") result = await recordWait(args.packageRoot, taskId, {
        waitSequence: args.waitSequence,
        waitCursor: args.waitCursor,
        waitStatus: args.waitStatus,
        waitError: args.waitError,
      });
      else if (args.command === "mark-timeout") result = await markTimeout(args.packageRoot, taskId);
      else if (args.command === "prepare-retry") result = await prepareRetry(args.packageRoot, taskId, args.retryReason);
      else if (args.command === "mark-complete") result = await markComplete(args.packageRoot, taskId);
      else result = await markFailed(args.packageRoot, taskId, args.error);
    }
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`FAIL: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
  }
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
