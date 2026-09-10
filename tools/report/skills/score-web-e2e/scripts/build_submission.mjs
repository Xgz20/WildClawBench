#!/usr/bin/env node
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { processIdentity, windowsCommandIncludesPath } from "./managed_runtime.mjs";
import { SCREENSHOT_RECEIVER_SCHEMA, detectImageFormat } from "./screenshot_receiver.mjs";
import {
  CANDIDATE_ARTIFACT_SCHEMA,
  FORBIDDEN_CANDIDATE_DIRS,
  IGNORED_RUNTIME_DIRS,
  TREE_HASH_ALGORITHM,
  loadCandidateArtifact,
  sameRuntimeDirectoryPolicy,
  validateRuntimeDirectoryPolicy,
  verifyWorkspace,
} from "./workspace-integrity.mjs";

const SUBMISSION_SCHEMA = "wildclawbench.web-e2e-submission/v1";
const SCORE_SCHEMA = "wildclawbench.web-e2e-task-score/v1";
const EXECUTION_RECEIPT_SCHEMA = "wildclawbench.web-e2e-execution-receipt/v1";
const RUNTIME_SCHEMA = "wildclawbench.web-e2e-scoring-runtime/v1";
const RUNTIME_PORT_OVERRIDE_SCHEMA = "wildclawbench.web-e2e-runtime-port-override/v1";
const SCREENSHOT_RECEIVER_TERMINAL_STATUSES = new Set(["COMPLETED", "STOPPED", "TIMED_OUT", "FAILED", "LOST"]);
const SCREENSHOT_RECEIVER_SCRIPT = fs.realpathSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "screenshot_receiver.mjs"));
const DETAILED_PROFILE = "web-e2e-detailed-v1";
const SUPPORTED_METRIC_PROFILES = new Set([DETAILED_PROFILE, "artifactsbench-web-v1"]);
const SECRET_NAMES = new Set([".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json", "secrets.json", "my_api.json"]);
const SECRET_SUFFIXES = [".pem", ".key", ".p12", ".pfx"];
const FORBIDDEN_DIR_NAMES = new Set([...FORBIDDEN_CANDIDATE_DIRS, "runtime-workspace"]);
const PORT_CONFLICT_PATTERNS = [
  /EADDRINUSE/i,
  /address\s+already\s+in\s+use/i,
  /port\s+[^\r\n]*already\s+in\s+use/i,
  /端口[^\r\n]*(?:占用|已被使用|正在使用)/i,
];

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`参数格式错误: ${key ?? ""}`);
    result[key.slice(2)] = value;
  }
  return result;
}

function loadJson(filename) {
  const value = JSON.parse(fs.readFileSync(filename, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error(`JSON 顶层必须是对象: ${filename}`);
  return value;
}

function validPort(value) {
  return Number.isInteger(value) && value >= 1 && value <= 65535;
}

function safeRelativePath(raw) {
  const value = String(raw || "");
  return Boolean(value) && !path.isAbsolute(value) && !value.split(/[\\/]+/).includes("..");
}

function pathInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative !== "" && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

function validatePortOverrideAudit(taskRoot, taskId, expectedSha256, runtimeState) {
  const auditFile = path.join(taskRoot, "private-scoring", "runtime-port-override.json");
  const stateOverrides = runtimeState?.port_overrides ?? [];
  if (!Array.isArray(stateOverrides)) throw new Error(`runtime-state.json 的 port_overrides 无效: ${taskId}`);
  if (!fs.existsSync(auditFile)) {
    if (stateOverrides.length) throw new Error(`runtime-state.json 记录了端口补丁但缺少审计文件: ${taskId}`);
    return { count: 0, audit_file: null, audit_sha256: null };
  }
  if (!runtimeState) throw new Error(`端口补丁存在但缺少 runtime-state.json: ${taskId}`);
  const auditBytes = fs.readFileSync(auditFile);
  const audit = JSON.parse(auditBytes.toString("utf8"));
  if (!audit || Array.isArray(audit) || typeof audit !== "object"
    || audit.schema_version !== RUNTIME_PORT_OVERRIDE_SCHEMA
    || audit.task_id !== taskId
    || audit.candidate_sha256 !== expectedSha256
    || !Array.isArray(audit.overrides)
    || audit.overrides.length === 0) {
    throw new Error(`端口补丁审计记录无效: ${taskId}`);
  }
  if (JSON.stringify(stateOverrides) !== JSON.stringify(audit.overrides)) {
    throw new Error(`runtime-state.json 与端口补丁审计记录不一致: ${taskId}`);
  }
  for (const [index, event] of audit.overrides.entries()) {
    const label = `${taskId}#${index + 1}`;
    const conflict = event?.conflict;
    const patch = event?.patch;
    if (!event?.recorded_at || !event?.runtime_created_at
      || conflict?.service_status !== "START_FAILED_STOPPED"
      || !Array.isArray(conflict.command)
      || !safeRelativePath(conflict.evidence_path)
      || !String(conflict.evidence_path).startsWith("private-scoring/runtime-logs/")
      || !/^[a-f0-9]{64}$/.test(String(conflict.evidence_sha256 || ""))) {
      throw new Error(`端口冲突证据记录无效: ${label}`);
    }
    let attemptedUrl;
    try {
      attemptedUrl = new URL(String(conflict.attempted_url || ""));
    } catch {
      throw new Error(`端口冲突 URL 无效: ${label}`);
    }
    if (!new Set(["127.0.0.1", "localhost", "::1"]).has(attemptedUrl.hostname)) {
      throw new Error(`端口冲突 URL 不是回环地址: ${label}`);
    }
    if (!patch || !safeRelativePath(patch.file)
      || !validPort(patch.from_port)
      || !validPort(patch.to_port)
      || patch.from_port === patch.to_port
      || patch.occurrence_count !== 1
      || patch.method !== "single-numeric-token-replacement"
      || !/^[a-f0-9]{64}$/.test(String(patch.before_sha256 || ""))
      || !/^[a-f0-9]{64}$/.test(String(patch.after_sha256 || ""))
      || patch.before_sha256 === patch.after_sha256) {
      throw new Error(`端口补丁记录无效: ${label}`);
    }
    const attemptedPort = Number(attemptedUrl.port || (attemptedUrl.protocol === "https:" ? 443 : 80));
    if (attemptedPort !== patch.from_port) throw new Error(`端口补丁与冲突 URL 不一致: ${label}`);
    const evidenceFile = path.resolve(taskRoot, conflict.evidence_path);
    if (!fs.existsSync(evidenceFile) || fs.lstatSync(evidenceFile).isSymbolicLink() || !fs.lstatSync(evidenceFile).isFile()) {
      throw new Error(`端口冲突证据文件不存在或不是普通文件: ${label}`);
    }
    const logRoot = path.join(taskRoot, "private-scoring", "runtime-logs");
    if (!fs.existsSync(logRoot) || fs.lstatSync(logRoot).isSymbolicLink()
      || !pathInside(fs.realpathSync(logRoot), fs.realpathSync(evidenceFile))) {
      throw new Error(`端口冲突证据文件不在受管日志目录内: ${label}`);
    }
    const evidenceBytes = fs.readFileSync(evidenceFile);
    const evidenceText = evidenceBytes.toString("utf8");
    const portPattern = new RegExp(`(^|\\D)${patch.from_port}(?!\\d)`);
    if (sha256(evidenceBytes) !== conflict.evidence_sha256
      || !PORT_CONFLICT_PATTERNS.some((pattern) => pattern.test(evidenceText))
      || !portPattern.test(evidenceText)) {
      throw new Error(`端口冲突证据文件校验失败: ${label}`);
    }
  }
  return {
    count: audit.overrides.length,
    audit_file: "private-scoring/runtime-port-override.json",
    audit_sha256: sha256(auditBytes),
  };
}

function liveScreenshotReceiverIdentity(taskRoot, state) {
  let identity;
  try {
    identity = processIdentity(Number(state.pid));
  } catch (error) {
    try {
      process.kill(Number(state.pid), 0);
    } catch (probeError) {
      if (probeError?.code !== "EPERM") return null;
    }
    throw new Error(`无法确认截图接收器进程身份: ${state.task_id}: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (!identity) return null;
  const platformIdentityMatches = process.platform === "win32"
    ? identity.process_group_mode === "windows-process-tree"
      && (!state.process_group_mode || state.process_group_mode === "windows-process-tree")
      && windowsCommandIncludesPath(identity.command, fs.realpathSync(taskRoot))
    : identity.cwd === fs.realpathSync(taskRoot);
  const exact = identity.pgid === Number(state.pgid)
    && identity.started_at_text === state.process_started_at_text
    && platformIdentityMatches
    && (process.platform === "win32"
      ? windowsCommandIncludesPath(identity.command, SCREENSHOT_RECEIVER_SCRIPT)
      : identity.command.includes(SCREENSHOT_RECEIVER_SCRIPT))
    && identity.command.includes("serve")
    && identity.command.includes(String(state.receiver_id || ""));
  return exact ? identity : null;
}

function validateScreenshotReceiver(taskRoot, taskId, expectedSha256) {
  const stateFile = path.join(taskRoot, "private-scoring", "screenshot-receiver-state.json");
  if (!fs.existsSync(stateFile)) return;
  const state = loadJson(stateFile);
  const filename = String(state.filename || "");
  const extension = path.extname(filename).toLowerCase();
  const expectedFormat = extension === ".png" ? "png" : new Set([".jpg", ".jpeg"]).has(extension) ? "jpeg" : null;
  if (state.schema_version !== SCREENSHOT_RECEIVER_SCHEMA
    || state.task_id !== taskId
    || state.candidate_sha256 !== expectedSha256
    || !/^[a-f0-9-]{36}$/i.test(String(state.receiver_id || ""))
    || !Number.isInteger(state.pid) || state.pid < 1
    || !Number.isInteger(state.pgid) || state.pgid < 1
    || !String(state.process_started_at_text || "").trim()
    || state.cwd !== "."
    || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.(?:png|jpe?g)$/i.test(filename)
    || !expectedFormat || state.format !== expectedFormat
    || state.content_type !== (expectedFormat === "png" ? "image/png" : "image/jpeg")
    || !/^[a-f0-9]{64}$/.test(String(state.token_sha256 || ""))
    || state.upload_url !== null
    || !SCREENSHOT_RECEIVER_TERMINAL_STATUSES.has(state.status)) {
    throw new Error(`截图接收器未进入可信终态: ${taskId}`);
  }
  const identity = state.pid ? liveScreenshotReceiverIdentity(taskRoot, state) : null;
  if (identity) throw new Error(`截图接收器仍在运行: ${taskId}: PID ${identity.pid}`);
  if (state.status !== "COMPLETED") return;

  const output = state.output;
  const expectedPath = `private-scoring/evidence/${state.filename}`;
  if (!output || output.path !== expectedPath
    || output.format !== state.format
    || output.content_type !== state.content_type
    || !Number.isInteger(output.bytes) || output.bytes < 1
    || !/^[a-f0-9]{64}$/.test(String(output.sha256 || ""))) {
    throw new Error(`截图接收器完成记录无效: ${taskId}`);
  }
  const evidenceRoot = path.join(taskRoot, "private-scoring", "evidence");
  const outputFile = path.resolve(taskRoot, output.path);
  if (!fs.existsSync(evidenceRoot) || fs.lstatSync(evidenceRoot).isSymbolicLink()
    || !fs.existsSync(outputFile) || fs.lstatSync(outputFile).isSymbolicLink() || !fs.lstatSync(outputFile).isFile()
    || !pathInside(fs.realpathSync(evidenceRoot), fs.realpathSync(outputFile))) {
    throw new Error(`截图接收器证据文件不存在或越界: ${taskId}`);
  }
  const bytes = fs.readFileSync(outputFile);
  if (bytes.length !== output.bytes || sha256(bytes) !== output.sha256 || detectImageFormat(bytes) !== output.format) {
    throw new Error(`截图接收器证据文件校验失败: ${taskId}`);
  }
}

function auditTree(root) {
  if (!fs.existsSync(root)) return { files: [], forbiddenDirectories: [], ignoredRuntimeDirectories: [] };
  const files = [];
  const forbiddenDirectories = [];
  const ignoredRuntimeDirectories = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const filename = path.join(root, entry.name);
    if (entry.isDirectory()) {
      if (IGNORED_RUNTIME_DIRS.has(entry.name)) ignoredRuntimeDirectories.push(filename);
      else if (FORBIDDEN_DIR_NAMES.has(entry.name)) forbiddenDirectories.push(filename);
      else {
        const nested = auditTree(filename);
        files.push(...nested.files);
        forbiddenDirectories.push(...nested.forbiddenDirectories);
        ignoredRuntimeDirectories.push(...nested.ignoredRuntimeDirectories);
      }
    } else if (entry.isFile()) files.push(filename);
  }
  return { files, forbiddenDirectories, ignoredRuntimeDirectories };
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
    throw new Error(`execution-receipt.json 模型回读无效: ${receiptTask?.task_id || "unknown"}`);
  }
  const declared = receipt.model || {};
  const declaredId = String(declared.id || "").trim();
  const declaredDisplayName = String(declared.display_name || "").trim();
  if (declaredId && !new Set([declaredId, declaredDisplayName]).has(actual)) {
    throw new Error(`execution-receipt.json 顶层模型与实际回读不一致: ${declaredId}/${declaredDisplayName} vs ${actual}`);
  }
  return {
    id: declaredId || actual,
    display_name: declaredDisplayName || actual,
    selection_mode: mode,
  };
}

export function buildSubmission(packageRoot) {
  const manifest = loadJson(path.join(packageRoot, "manifest.json"));
  const entries = manifest.tasks ?? [];
  if (entries.length === 0) throw new Error("manifest.tasks 为空");
  const receiptFile = path.join(packageRoot, "execution-receipt.json");
  const receiptRaw = fs.readFileSync(receiptFile, "utf8");
  const receipt = JSON.parse(receiptRaw);
  if (!receipt || Array.isArray(receipt) || typeof receipt !== "object") throw new Error(`JSON 顶层必须是对象: ${receiptFile}`);
  const receiptSha256 = sha256(receiptRaw);
  if (receipt.schema_version !== EXECUTION_RECEIPT_SCHEMA || receipt.integrity?.valid !== true) {
    throw new Error("execution-receipt.json 缺失、schema 不兼容或 integrity.valid 不是 true");
  }
  const allowIgnoredRuntimeDirectories = validateRuntimeDirectoryPolicy(receipt.runtime_directory_policy);
  if (receipt.batch_id !== manifest.batch_id || receipt.harness?.id !== manifest.harness?.id) {
    throw new Error("execution-receipt.json 身份与 manifest 不一致");
  }
  const receiptTasks = receipt.tasks || [];
  const receiptById = new Map(receiptTasks.map((task) => [String(task.task_id || ""), task]));
  if (receiptById.size !== receiptTasks.length
    || JSON.stringify([...receiptById.keys()].sort()) !== JSON.stringify(entries.map((entry) => entry.task_id).sort())) {
    throw new Error("execution-receipt.json 任务范围与 manifest 不一致");
  }
  const tasks = [];
  const candidateArtifacts = [];
  for (const entry of entries) {
    const taskRoot = path.join(packageRoot, "score", "tasks", entry.task_id);
    const receiptTask = receiptById.get(entry.task_id);
    const expectedSha256 = String(receiptTask?.workspace?.final_sha256 || "");
    if (!/^[a-f0-9]{64}$/.test(expectedSha256)) throw new Error(`执行回执缺少候选最终 SHA-256: ${entry.task_id}`);
    const candidateLockPath = path.join(taskRoot, "private-scoring", "candidate_artifact.json");
    const candidateLock = loadCandidateArtifact(candidateLockPath);
    const receiptModel = resolveReceiptModel(receipt, receiptTask);
    const candidateSelectionMode = candidateLock.model_selection?.mode
      || (candidateLock.model_selection?.requested_model ? "explicit" : "current");
    if (candidateLock.schema_version !== CANDIDATE_ARTIFACT_SCHEMA
      || candidateLock.hash_algorithm !== TREE_HASH_ALGORITHM
      || candidateLock.batch_id !== manifest.batch_id
      || candidateLock.task_id !== entry.task_id
      || candidateLock.harness_id !== manifest.harness?.id
      || candidateLock.expected_sha256 !== expectedSha256
      || candidateLock.execution_receipt?.sha256 !== receiptSha256
      || !sameRuntimeDirectoryPolicy(candidateLock.runtime_directory_policy, receipt.runtime_directory_policy)
      || candidateLock.model?.id !== receiptModel.id
      || candidateLock.model?.display_name !== receiptModel.display_name
      || candidateSelectionMode !== receiptModel.selection_mode
      || (candidateLock.model_selection?.requested_model || null) !== (receiptTask.model_selection?.requested_model || null)
      || candidateLock.model_selection?.actual_model !== receiptTask.model_selection?.actual_model) {
      throw new Error(`candidate_artifact.json 与执行回执不一致: ${entry.task_id}`);
    }
    const executionCheck = verifyWorkspace(
      path.join(packageRoot, "execution", "tasks", entry.task_id, "workspace"),
      expectedSha256,
      `build-submission:${entry.task_id}:execution`,
      { allowIgnoredRuntimeDirectories },
    );
    const scoreCheck = verifyWorkspace(
      path.join(taskRoot, "workspace"),
      expectedSha256,
      `build-submission:${entry.task_id}:score`,
    );
    const runtimeWorkspace = path.join(taskRoot, "private-scoring", "runtime-workspace");
    if (fs.existsSync(runtimeWorkspace)) throw new Error(`评分运行时副本尚未清理: ${entry.task_id}`);
    validateScreenshotReceiver(taskRoot, entry.task_id, expectedSha256);
    const runtimeStateFile = path.join(taskRoot, "private-scoring", "runtime-state.json");
    let runtimeState = null;
    if (fs.existsSync(runtimeStateFile)) {
      runtimeState = loadJson(runtimeStateFile);
      if (runtimeState.schema_version !== RUNTIME_SCHEMA
        || runtimeState.task_id !== entry.task_id
        || runtimeState.candidate_sha256 !== expectedSha256) {
        throw new Error(`runtime-state.json 与冻结候选身份不一致: ${entry.task_id}`);
      }
      const service = runtimeState.service;
      if (service?.pid) {
        let alive = true;
        try {
          process.kill(Number(service.pid), 0);
        } catch (error) {
          alive = error?.code === "EPERM";
        }
        if (alive || !new Set(["STOPPED", "START_FAILED_STOPPED"]).has(service.status)) {
          throw new Error(`评分服务未按受管流程停止: ${entry.task_id}: PID ${service.pid}`);
        }
      }
    }
    const portOverrideAudit = validatePortOverrideAudit(taskRoot, entry.task_id, expectedSha256, runtimeState);
    const scorePath = path.join(packageRoot, "score", "tasks", entry.task_id, "private-scoring", "task_score.json");
    if (!fs.existsSync(scorePath)) throw new Error(`缺少 task_score.json: ${entry.task_id}`);
    const score = loadJson(scorePath);
    if (score.schema_version !== SCORE_SCHEMA) throw new Error(`task_score schema 不兼容: ${entry.task_id}`);
    const scoreProfile = String(score.metric_profile ?? DETAILED_PROFILE);
    if (!SUPPORTED_METRIC_PROFILES.has(scoreProfile)) {
      throw new Error(`task_score metric_profile 不兼容: ${entry.task_id}: ${scoreProfile}`);
    }
    if (score.identity?.batch_id !== manifest.batch_id || score.identity?.task_id !== entry.task_id) {
      throw new Error(`task_score 身份与 manifest 不一致: ${entry.task_id}`);
    }
    if (score.identity?.model?.id !== receiptModel.id
      || score.identity?.model?.display_name !== receiptModel.display_name) {
      throw new Error(`task_score 模型与执行回读不一致: ${entry.task_id}`);
    }
    if (
      score.provenance?.source_revision
      && manifest.source_revision
      && score.provenance.source_revision !== manifest.source_revision
    ) {
      throw new Error(`task_score source_revision 与 manifest 不一致: ${entry.task_id}`);
    }
    if (entry.task_sha256 && score.provenance?.task_sha256 !== entry.task_sha256) {
      throw new Error(`task_score task_sha256 与 manifest 不一致: ${entry.task_id}`);
    }
    if (entry.workspace_exec_sha256 && score.provenance?.workspace_exec_sha256 !== entry.workspace_exec_sha256) {
      throw new Error(`task_score workspace_exec_sha256 与 manifest 不一致: ${entry.task_id}`);
    }
    if (score.provenance?.candidate_workspace_sha256 !== expectedSha256) {
      throw new Error(`task_score candidate_workspace_sha256 与冻结产物不一致: ${entry.task_id}`);
    }
    if (score.execution?.status === "pending") throw new Error(`执行状态仍为 pending: ${entry.task_id}`);
    const scoringDir = path.dirname(scorePath);
    for (const criterion of score.evaluation?.criteria ?? []) {
      for (const evidence of criterion.evidence ?? []) {
        const raw = String(evidence?.path ?? "");
        const parts = raw.split(/[\\/]+/);
        if (!raw || path.isAbsolute(raw) || parts.includes("..") || parts[0] !== "evidence") {
          throw new Error(`评分证据必须位于 private-scoring/evidence 下: ${entry.task_id}: ${raw}`);
        }
        if (!fs.existsSync(path.join(scoringDir, ...parts))) throw new Error(`评分证据文件不存在: ${entry.task_id}: ${raw}`);
      }
    }
    for (const screenshot of score.evaluation?.aesthetic?.screenshots ?? []) {
      const raw = String(screenshot?.path ?? "");
      const parts = raw.split(/[\\/]+/);
      if (!raw || path.isAbsolute(raw) || parts.includes("..") || parts[0] !== "evidence") {
        throw new Error(`美观度截图必须位于 private-scoring/evidence 下: ${entry.task_id}: ${raw}`);
      }
      if (!fs.existsSync(path.join(scoringDir, ...parts))) {
        throw new Error(`美观度截图文件不存在: ${entry.task_id}: ${raw}`);
      }
    }
    tasks.push(score);
    candidateArtifacts.push({
      task_id: entry.task_id,
      hash_algorithm: TREE_HASH_ALGORITHM,
      expected_sha256: expectedSha256,
      checked_at: scoreCheck.checked_at,
      execution_sha256: executionCheck.sha256,
      score_sha256: scoreCheck.sha256,
      ignored_runtime_directories: executionCheck.ignored_runtime_directories,
      runtime_port_overrides: portOverrideAudit,
      valid: true,
    });
  }
  const metricProfiles = new Set(tasks.map((task) => String(task.metric_profile ?? DETAILED_PROFILE)));
  if (metricProfiles.size !== 1) throw new Error("一个回传包不能混合 metric_profile");
  const metricProfile = [...metricProfiles][0];
  const manifestProfile = String(manifest.metric_profile ?? DETAILED_PROFILE);
  if (manifestProfile !== metricProfile) throw new Error("task_score metric_profile 与 manifest 不一致");
  const harnessIds = new Set(tasks.map((task) => String(task.identity?.harness?.id ?? "")));
  const modelIds = new Set(tasks.map((task) => String(task.identity?.model?.id ?? "")));
  if (harnessIds.size !== 1 || modelIds.size !== 1) throw new Error("一个回传包只能包含一个 model@harness");
  const harnessId = [...harnessIds][0];
  const modelId = [...modelIds][0];
  if (!harnessId) throw new Error("回传前必须填写 harness.id");
  if (!modelId) throw new Error("回传前必须填写执行回读的 model.id");
  const manifestHarnessId = String(manifest.harness?.id ?? "");
  if (manifestHarnessId && harnessId !== manifestHarnessId) throw new Error("task_score harness.id 与 manifest 不一致");

  const audit = auditTree(packageRoot);
  const sensitive = [];
  for (const filename of audit.files) {
    const name = path.basename(filename).toLowerCase();
    if (SECRET_NAMES.has(name) || name.startsWith(".env.") || SECRET_SUFFIXES.some((suffix) => name.endsWith(suffix))) {
      sensitive.push(path.relative(packageRoot, filename).split(path.sep).join("/"));
    }
  }
  if (sensitive.length) throw new Error(`回传目录包含敏感文件，打包前必须处理: ${sensitive.join(", ")}`);
  if (audit.forbiddenDirectories.length) {
    const relative = audit.forbiddenDirectories.map((filename) => path.relative(packageRoot, filename).split(path.sep).join("/"));
    throw new Error(`回传目录包含不应打包的目录，请先删除: ${relative.join(", ")}`);
  }
  return {
    schema_version: SUBMISSION_SCHEMA,
    batch_id: manifest.batch_id,
    source_revision: manifest.source_revision ?? null,
    metric_profile: metricProfile,
    created_at: new Date().toISOString(),
    unit: {
      model_id: modelId,
      model_display_name: tasks[0].identity?.model?.display_name || modelId,
      harness_id: harnessId,
      harness_display_name: tasks[0].identity?.harness?.display_name || harnessId,
    },
    task_ids: entries.map((item) => item.task_id),
    candidate_artifacts: candidateArtifacts,
    tasks,
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args["package-root"]) throw new Error("必须提供 --package-root");
  const packageRoot = path.resolve(args["package-root"]);
  const output = path.resolve(args.output || path.join(packageRoot, "submission.json"));
  if (output !== path.join(packageRoot, "submission.json")) {
    throw new Error("submission 只能写入 Harness 根目录的 submission.json");
  }
  fs.writeFileSync(output, `${JSON.stringify(buildSubmission(packageRoot), null, 2)}\n`, "utf8");
  process.stdout.write(`PASS: ${output}\n`);
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`FAIL: ${error.message}\n`);
    process.exitCode = 2;
  }
}
