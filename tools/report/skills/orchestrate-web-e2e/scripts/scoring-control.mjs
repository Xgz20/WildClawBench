#!/usr/bin/env node
import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { mkdir, readFile, realpath, rename, stat, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CANDIDATE_ARTIFACT_SCHEMA,
  TREE_HASH_ALGORITHM,
  loadCandidateArtifact,
  verifyWorkspace,
} from "./workspace-integrity.mjs";

const STATE_SCHEMA = "wildclawbench.web-e2e-scoring-automation/v1";
const REGISTRY_SCHEMA = "wildclawbench.codex-project-registry/v1";
const SCORE_SCHEMA = "wildclawbench.web-e2e-task-score/v1";
const SCORE_SKILL_SCHEMA = "wildclawbench.web-e2e-score-skill/v1";
const EXECUTION_RECEIPT_SCHEMA = "wildclawbench.web-e2e-execution-receipt/v1";
const CONTROL_DIR = join("score", ".orchestrate-web-e2e");
const REGISTRATION_METHODS = new Set([
  "direct-open-folder",
  "create-local-project-dialog",
  "add-project-then-open-folder",
  "renderer-bridge",
]);

export function usage() {
  return `Web E2E 评分控制状态

用法：
  node scoring-control.mjs init --package-root <目录> [--task-id <ID> ...]
  node scoring-control.mjs status --package-root <目录>
  node scoring-control.mjs record-project --package-root <目录> --task-id <ID> --project-id <ID> --project-path <目录> --host-id <ID> --desktop-version <版本> --registration-method <方式>
  node scoring-control.mjs preflight --package-root <目录> --desktop-version <版本> --score-skill-dir <目录> [--allow-renderer-bridge]
  node scoring-control.mjs record-thread --package-root <目录> --task-id <ID> --thread-id <ID> --host-id <ID>
  node scoring-control.mjs mark-complete --package-root <目录> --task-id <ID>
  node scoring-control.mjs mark-failed --package-root <目录> --task-id <ID> --error <说明>
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
    else if (token === "--help" || token === "-h") values.help = true;
    else throw new Error(`未知参数：${token}`);
  }
  if (values.help) return values;
  if (!new Set(["init", "status", "record-project", "preflight", "record-thread", "mark-complete", "mark-failed"]).has(command)) {
    throw new Error(`未知命令：${command || "未提供"}`);
  }
  if (!values.packageRoot) throw new Error("必须提供 --package-root");
  if (values.taskIds.some((taskId) => !taskId)) throw new Error("--task-id 不能为空");
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
  if (state.tasks.some((task) => task.phase === "FAILED")) return null;
  return state.tasks.find((task) => task.phase !== "COMPLETED") || null;
}

function publicStatus(state) {
  return {
    schema_version: state.schema_version,
    batch_id: state.batch_id,
    harness_id: state.harness_id,
    phase: state.phase,
    score_slots: state.score_slots,
    preflight: state.preflight || null,
    next_task: nextTask(state),
    tasks: state.tasks,
  };
}

function refreshPhase(state) {
  if (state.tasks.every((task) => task.phase === "COMPLETED")) {
    state.phase = "COMPLETED";
    state.finished_at ||= new Date().toISOString();
  } else if (state.tasks.some((task) => task.phase === "SCORING")) state.phase = "SCORING";
  else if (state.tasks.some((task) => task.phase === "FAILED")) state.phase = "NEEDS_ATTENTION";
  else state.phase = "PREPARED";
}

export async function initialize(packageRoot, selectedTaskIds = []) {
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
  const existing = await loadJsonIfExists(plan.stateFile);
  if (existing) {
    if (existing.schema_version !== STATE_SCHEMA || existing.batch_id !== plan.manifest.batch_id || existing.harness_id !== plan.manifest.harness.id) {
      throw new Error("已有评分状态身份不一致");
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
    batch_id: plan.manifest.batch_id,
    harness_id: plan.manifest.harness.id,
    score_slots: 1,
    phase: "PREPARED",
    created_at: now,
    updated_at: now,
    finished_at: null,
    tasks,
    preflight: { status: "PENDING", checked_at: null, task_id: null },
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
  const state = await loadJson(plan.stateFile);
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

export async function recordThread(packageRoot, taskId, thread) {
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
  const now = new Date().toISOString();
  task.thread_id = thread.threadId;
  task.thread_host_id = thread.hostId;
  task.phase = "SCORING";
  task.timing.thread_created_at ||= now;
  state.history.push({ event: "THREAD_RECORDED", at: now, task_id: taskId, thread_id: thread.threadId, host_id: thread.hostId });
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
  await verifyTaskCandidateOrFail(plan, state, task, "mark-complete");
  await validateTaskScore(plan, task);
  if (task.phase === "COMPLETED") return publicStatus(state);
  const now = new Date().toISOString();
  task.phase = "COMPLETED";
  task.error = null;
  task.timing.finished_at = now;
  state.history.push({ event: "TASK_SCORE_VALIDATED", at: now, task_id: taskId, thread_id: task.thread_id });
  state.preflight = { status: "PENDING", checked_at: null, task_id: nextTask(state)?.task_id || null };
  await saveControl(plan, state);
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
  state.history.push({ event: "SCORING_FAILED", at: now, task_id: taskId, thread_id: task.thread_id, error: errorMessage });
  await saveControl(plan, state);
  return publicStatus(state);
}

export async function status(packageRoot) {
  const { state } = await loadControl(packageRoot);
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
    if (args.command === "init") result = publicStatus((await initialize(args.packageRoot, args.taskIds)).state);
    else if (args.command === "status") result = await status(args.packageRoot);
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
