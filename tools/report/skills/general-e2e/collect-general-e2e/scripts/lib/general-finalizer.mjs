#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { realpathSync } from "node:fs";
import {
  chmod,
  copyFile,
  link,
  lstat,
  mkdir,
  readFile,
  readdir,
  readlink,
  realpath,
  rename,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import {
  dirname,
  isAbsolute,
  join,
  relative,
  resolve,
  sep,
} from "node:path";
import { fileURLToPath } from "node:url";

import { createWorkspaceIntegrity } from "../../vendor/e2e-shared/handoff/workspace-integrity.mjs";

export const EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-astronstudio-execution-state/v1";
export const EXECUTION_RECORD_SCHEMA = "urn:wildclawbench:schema:general-e2e:execution-record:v1";
export const TRACE_INDEX_SCHEMA = "urn:wildclawbench:schema:general-e2e:trace-index:v1";
export const RESOURCE_METRICS_SCHEMA = "urn:wildclawbench:schema:general-e2e:resource-metrics:v1";
export const RECEIPT_SCHEMA = "urn:wildclawbench:schema:general-e2e:receipt:v1";
export const CANDIDATE_ARTIFACT_SCHEMA = "wildclawbench.general-e2e-candidate-artifact/v1";
export const CANDIDATE_POLICY_SCHEMA = "wildclawbench.general-e2e-candidate-policy/v1";
export const RUNTIME_POLICY_SCHEMA = "wildclawbench.general-e2e-runtime-directory-policy/v1";
export const EVIDENCE_MANIFEST_SCHEMA = "wildclawbench.general-e2e-evidence-manifest/v1";
export const TREE_HASH_ALGORITHM = "wildclawbench.workspace-tree-sha256/v1";
const MAX_JSON_BYTES = 64 * 1024 * 1024;
const TERMINAL_PHASES = new Set(["COMPLETED", "FAILED"]);
const BUSINESS_STATUSES = new Set([
  "completed",
  "candidate_error",
  "timeout",
  "infrastructure_error",
  "cancelled",
]);

export function usage() {
  return `AstronStudio General E2E 正式收口器

用法：
  node scripts/finalize_astronstudio_execution.mjs \\
    --unit-root /absolute/unit-root \\
    --state-file /absolute/automation-state.json \\
    [--trace-index /absolute/trace-index.json] \\
    [--resource-metrics /absolute/resource-metrics.json] [选项]

验证已有收口：
  node scripts/finalize_astronstudio_execution.mjs \\
    --verify-only --unit-root /absolute/unit-root --task-id <task-id>

选项：
  --candidate-policy /absolute/policy.json  显式目录策略；默认完整保留全部目录
  --stability-ms <n>                       Workspace 静默窗口，默认 5000
  --process-quiet-ms <n>                   进程零残留窗口，默认 5000
  --process-wait-ms <n>                    进程收口总等待，默认 15000
  --verify-only                            只验证冻结候选、证据和回执，不改写
  --task-id <id>                           verify-only 必填
  -h, --help                               显示帮助

completed 执行必须提供完整 trace 和 resource metrics；timeout/candidate_error
允许按真实覆盖归档部分证据。正式候选和回执不可覆盖，后续使用 --verify-only。`;
}

function nonNegativeInteger(value, name) {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) throw new Error(`${name} 必须是非负整数`);
  return parsed;
}

export function parseArgs(argv) {
  const result = {
    unitRoot: "",
    stateFile: "",
    traceIndex: "",
    resourceMetrics: "",
    candidatePolicy: "",
    stabilityMilliseconds: 5_000,
    processQuietMilliseconds: 5_000,
    processWaitMilliseconds: 15_000,
    verifyOnly: false,
    taskId: "",
    help: false,
  };
  const valued = new Map([
    ["--unit-root", "unitRoot"],
    ["--state-file", "stateFile"],
    ["--trace-index", "traceIndex"],
    ["--resource-metrics", "resourceMetrics"],
    ["--candidate-policy", "candidatePolicy"],
    ["--task-id", "taskId"],
  ]);
  const numeric = new Map([
    ["--stability-ms", "stabilityMilliseconds"],
    ["--process-quiet-ms", "processQuietMilliseconds"],
    ["--process-wait-ms", "processWaitMilliseconds"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") result.help = true;
    else if (arg === "--verify-only") result.verifyOnly = true;
    else if (valued.has(arg) || numeric.has(arg)) {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      if (valued.has(arg)) result[valued.get(arg)] = value;
      else result[numeric.get(arg)] = nonNegativeInteger(value, arg);
      index += 1;
    } else throw new Error(`未知选项：${arg}`);
  }
  if (!result.help) {
    if (!result.unitRoot) throw new Error("必须指定 --unit-root");
    if (result.verifyOnly) {
      if (!result.taskId) throw new Error("--verify-only 必须指定 --task-id");
    } else if (!result.stateFile) throw new Error("必须指定 --state-file");
  }
  return result;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function prettyJson(value) {
  return Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function compareUnicodeCodePoints(left, right) {
  const leftPoints = Array.from(left, (character) => character.codePointAt(0));
  const rightPoints = Array.from(right, (character) => character.codePointAt(0));
  const length = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < length; index += 1) {
    if (leftPoints[index] !== rightPoints[index]) return leftPoints[index] - rightPoints[index];
  }
  return leftPoints.length - rightPoints.length;
}

function isWithin(root, candidate) {
  const rel = relative(root, candidate);
  return rel === "" || (rel !== ".." && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

function safeRelativePath(value, label) {
  if (typeof value !== "string" || !value || value.includes("\\") || isAbsolute(value)) {
    throw new Error(`UNSAFE_RELATIVE_PATH: ${label}: ${value}`);
  }
  const parts = value.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) {
    throw new Error(`UNSAFE_RELATIVE_PATH: ${label}: ${value}`);
  }
  return value;
}

function unitRelative(unitRoot, absolute, label) {
  const value = relative(unitRoot, absolute);
  if (!value || value === ".." || value.startsWith(`..${sep}`) || isAbsolute(value)) {
    throw new Error(`PATH_OUTSIDE_UNIT: ${label}: ${absolute}`);
  }
  return value.split(sep).join("/");
}

function resolveWithin(unitRoot, value, label) {
  const relativePath = safeRelativePath(value, label);
  const absolute = resolve(unitRoot, relativePath);
  if (!isWithin(unitRoot, absolute)) throw new Error(`PATH_OUTSIDE_UNIT: ${label}: ${value}`);
  return absolute;
}

async function readRegularFile(path, maximumBytes = MAX_JSON_BYTES) {
  const absolute = resolve(path);
  const info = await lstat(absolute);
  if (!info.isFile() || info.isSymbolicLink() || info.size > maximumBytes) {
    throw new Error(`UNSAFE_OR_OVERSIZED_FILE: ${absolute}`);
  }
  const bytes = await readFile(absolute);
  if (bytes.length > maximumBytes) throw new Error(`OVERSIZED_FILE: ${absolute}`);
  return { absolute, bytes, sha256: sha256(bytes), size: bytes.length };
}

async function readJsonFile(path) {
  const source = await readRegularFile(path);
  try {
    return { ...source, value: JSON.parse(source.bytes.toString("utf8")) };
  } catch (error) {
    throw new Error(`JSON_INVALID: ${source.absolute}: ${error.message}`);
  }
}

function sameIdentity(left, right) {
  return ["batch_id", "unit_id", "task_id", "attempt_id"]
    .every((field) => typeof left?.[field] === "string" && left[field] === right?.[field]);
}

function assertArtifact(source, artifact, label) {
  if (artifact?.sha256 !== source.sha256 || artifact?.size !== source.size) {
    throw new Error(`ARTIFACT_DIGEST_MISMATCH: ${label}`);
  }
}

function artifact(path, source, extra = {}) {
  return { path, sha256: source.sha256, size: source.size, ...extra };
}

async function assertUnitAndState(unitRoot, manifestSource, stateSource, profile) {
  const manifest = manifestSource.value;
  const state = stateSource.value;
  if (manifest?.schema_id !== "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
      || manifest?.manifest_kind !== "execution") {
    throw new Error("EXECUTION_MANIFEST_UNSUPPORTED");
  }
  if (state?.schema_version !== profile.executionStateSchema || !TERMINAL_PHASES.has(state.phase)) {
    throw new Error(`EXECUTION_STATE_NOT_TERMINAL: ${state?.phase || "missing"}`);
  }
  if (!BUSINESS_STATUSES.has(state.execution?.business_status)) {
    throw new Error(`EXECUTION_BUSINESS_STATUS_INVALID: ${state.execution?.business_status || "missing"}`);
  }
  if (state.identity?.batch_id !== manifest.batch_id || state.identity?.unit_id !== manifest.unit_id) {
    throw new Error("EXECUTION_SCOPE_MISMATCH");
  }
  if (state.dataset?.id !== manifest.dataset?.id || state.dataset?.digest !== manifest.dataset?.digest) {
    throw new Error("EXECUTION_DATASET_MISMATCH");
  }
  const tasks = (manifest.tasks || []).filter((item) => item.task_id === state.identity?.task_id);
  if (tasks.length !== 1 || !(manifest.task_ids || []).includes(state.identity.task_id)) {
    throw new Error("EXECUTION_TASK_SCOPE_MISMATCH");
  }
  const task = tasks[0];
  const taskRoot = resolveWithin(unitRoot, `execution/tasks/${state.identity.task_id}`, "task root");
  const workspace = resolveWithin(unitRoot, `${task.workspace.path}`, "candidate workspace");
  const promptPath = resolveWithin(unitRoot, task.prompt.path, "prompt");
  const [actualTaskRoot, actualWorkspace, stateTaskRoot, stateWorkspace, statePrompt] = await Promise.all([
    realpath(taskRoot),
    realpath(workspace),
    realpath(state.task_root),
    realpath(state.candidate_workspace),
    realpath(state.prompt?.path),
  ]);
  if (actualTaskRoot !== stateTaskRoot || actualWorkspace !== stateWorkspace
      || await realpath(promptPath) !== statePrompt) {
    throw new Error("EXECUTION_PATH_BINDING_MISMATCH");
  }
  const promptSource = await readRegularFile(promptPath);
  if (promptSource.sha256 !== state.prompt?.sha256
      || promptSource.sha256 !== task.prompt?.sent_sha256) {
    throw new Error("PROMPT_DIGEST_MISMATCH");
  }
  if (state.prompt?.send_status === "sent") {
    if (state.send?.dispatch_attempt_count !== 1 || typeof state.prompt.sent_at !== "string") {
      throw new Error("PROMPT_DISPATCH_IDENTITY_INVALID");
    }
  }
  if (state.execution.business_status === "completed") {
    if (state.prompt?.send_status !== "sent" || state.session?.verified !== true
        || (!profile.generic && state.session?.native_status !== "completed")) {
      throw new Error("COMPLETED_EXECUTION_IDENTITY_UNVERIFIED");
    }
  }
  if (new Set(["timeout", "cancelled"]).has(state.execution.business_status)
      && (profile.generic ? state.execution?.cancellation_confirmed : state.timeout?.cancellation_confirmed) !== true) {
    throw new Error("EXECUTION_CANCELLATION_UNVERIFIED");
  }
  return { manifest, state, task, taskRoot: actualTaskRoot, workspace: actualWorkspace, promptSource };
}

async function loadTraceBundle(indexPath, state, profile) {
  if (!indexPath) return null;
  const indexSource = await readJsonFile(indexPath);
  const index = indexSource.value;
  if (index?.schema_id !== profile.traceIndexSchema || index?.schema_version !== profile.traceVersion
      || !sameIdentity(index.identity, state.identity)) {
    throw new Error("TRACE_INDEX_IDENTITY_MISMATCH");
  }
  for (const field of ["thread_id", "turn_id", "session_id", "cwd"]) {
    if (state.session?.[field] !== index.session?.[field]) {
      throw new Error(`TRACE_SESSION_MISMATCH: ${field}`);
    }
  }
  const root = await realpath(dirname(indexSource.absolute));
  const transcriptRelative = safeRelativePath(index.transcript?.path, "trace transcript");
  const transcriptSource = await readRegularFile(resolve(root, transcriptRelative));
  assertArtifact(transcriptSource, index.transcript, "trace transcript");
  if (!Array.isArray(index.raw_trace) || (!profile.generic && index.raw_trace.length !== 1)
      || (profile.generic && index.raw_trace.length === 0)) {
    throw new Error("TRACE_RAW_ARTIFACT_AMBIGUOUS");
  }
  const traceArtifacts = [];
  const seen = new Set(["trace-index.json", "transcript.jsonl"]);
  for (const item of [...index.raw_trace, ...(profile.generic ? index.binding_evidence : [])]) {
    const artifactRelative = safeRelativePath(item.path, "trace artifact");
    if (seen.has(artifactRelative)) throw new Error("TRACE_ARTIFACT_PATH_DUPLICATE");
    seen.add(artifactRelative);
    const artifactPath = resolveWithin(root, artifactRelative, "trace artifact");
    if (!isWithin(root, await realpath(artifactPath))) throw new Error("TRACE_ARTIFACT_OUTSIDE_ROOT");
    const source = await readRegularFile(artifactPath);
    assertArtifact(source, item, artifactRelative);
    traceArtifacts.push({ relative: artifactRelative, source });
  }
  return { indexSource, index, transcriptSource, transcriptRelative, traceArtifacts };

}

async function loadResourceMetrics(path, stateSource, traceBundle, profile) {
  if (!path) return null;
  if (!traceBundle) throw new Error("RESOURCE_METRICS_REQUIRE_TRACE");
  const source = await readJsonFile(path);
  const value = source.value;
  if (value?.schema_id !== RESOURCE_METRICS_SCHEMA || value?.schema_version !== 1
      || !sameIdentity(value.identity, stateSource.value.identity)) {
    throw new Error("RESOURCE_METRICS_IDENTITY_MISMATCH");
  }
  const expectedSources = new Map([
    ["execution/automation-state.json", stateSource],
    ["trace/trace-index.json", traceBundle.indexSource],
    ...traceBundle.traceArtifacts.map((item) => [`trace/${item.relative}`, item.source]),
  ]);
  const rows = value.collection?.sources;
  if (!Array.isArray(rows) || (!profile.generic && rows.length !== expectedSources.size)) {
    throw new Error("RESOURCE_METRICS_SOURCE_SCOPE_MISMATCH");
  }
  const seen = new Set();
  for (const row of rows) {
    if (seen.has(row.path)) throw new Error("RESOURCE_METRICS_SOURCE_DUPLICATE");
    seen.add(row.path);
    const expected = expectedSources.get(row.path);
    if (!expected) throw new Error(`RESOURCE_METRICS_SOURCE_UNKNOWN: ${row.path}`);
    assertArtifact(expected, row, row.path);
  }
  return { source, value };
}

async function loadFinalResponse(unitRoot, state) {
  const evidence = state.evidence || state.extensions?.evidence;
  const path = evidence?.final_response_path;
  if (!path) return null;
  const source = await readRegularFile(resolveWithin(unitRoot, path, "final response"));
  if (evidence?.final_response_sha256 !== source.sha256) {
    throw new Error("FINAL_RESPONSE_DIGEST_MISMATCH");
  }
  return source;
}

function normalizePolicyEntry(value, kind, index) {
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`CANDIDATE_POLICY_ENTRY_INVALID: ${kind}[${index}]`);
  }
  const name = String(value.name || "");
  const reason = String(value.reason || "").trim();
  if (!name || name.includes("/") || name.includes("\\") || name === "." || name === ".." || !reason) {
    throw new Error(`CANDIDATE_POLICY_ENTRY_INVALID: ${kind}[${index}]`);
  }
  return { name, reason };
}

async function loadCandidatePolicy(path) {
  if (!path) {
    return {
      schema_version: CANDIDATE_POLICY_SCHEMA,
      policy_source: "exact-all-default",
      ignored_directories: [],
      forbidden_directories: [],
    };
  }
  const source = await readJsonFile(path);
  const value = source.value;
  if (value?.schema_version !== CANDIDATE_POLICY_SCHEMA) {
    throw new Error(`CANDIDATE_POLICY_UNSUPPORTED: ${value?.schema_version || "missing"}`);
  }
  const ignored = (value.ignored_directories || []).map((item, index) => normalizePolicyEntry(item, "ignored", index));
  const forbidden = (value.forbidden_directories || []).map((item, index) => normalizePolicyEntry(item, "forbidden", index));
  const names = [...ignored, ...forbidden].map((item) => item.name);
  if (new Set(names).size !== names.length) throw new Error("CANDIDATE_POLICY_DIRECTORY_DUPLICATE");
  return {
    schema_version: CANDIDATE_POLICY_SCHEMA,
    policy_source: "explicit-file",
    ignored_directories: ignored,
    forbidden_directories: forbidden,
    source: artifact("candidate-policy.json", source),
  };
}

function createIntegrity(policy) {
  return createWorkspaceIntegrity({
    treeHashAlgorithm: TREE_HASH_ALGORITHM,
    candidateArtifactSchema: CANDIDATE_ARTIFACT_SCHEMA,
    runtimeDirectoryPolicySchema: RUNTIME_POLICY_SCHEMA,
    ignoredDirectories: policy.ignored_directories.map((item) => item.name),
    forbiddenDirectories: policy.forbidden_directories.map((item) => item.name),
  });
}

async function copyCandidateTree(sourceRoot, destinationRoot, policy) {
  const ignored = new Set(policy.ignored_directories.map((item) => item.name));
  const forbidden = new Set(policy.forbidden_directories.map((item) => item.name));
  const entries = [];
  async function walk(sourceDirectory, destinationDirectory, prefix = "") {
    const sourceInfo = await lstat(sourceDirectory);
    await mkdir(destinationDirectory, { recursive: true, mode: sourceInfo.mode & 0o777 });
    await chmod(destinationDirectory, sourceInfo.mode & 0o777);
    const children = await readdir(sourceDirectory, { withFileTypes: true });
    children.sort((left, right) => compareUnicodeCodePoints(left.name, right.name));
    for (const child of children) {
      const relativePath = prefix ? `${prefix}/${child.name}` : child.name;
      if (forbidden.has(child.name)) throw new Error(`CANDIDATE_FORBIDDEN_DIRECTORY: ${relativePath}`);
      if (child.isDirectory() && ignored.has(child.name)) continue;
      const sourcePath = join(sourceDirectory, child.name);
      const destinationPath = join(destinationDirectory, child.name);
      const info = await lstat(sourcePath);
      const mode = (info.mode & 0o777).toString(8).padStart(4, "0");
      if (info.isSymbolicLink()) {
        const target = await readlink(sourcePath);
        if (isAbsolute(target) || !isWithin(sourceRoot, resolve(dirname(sourcePath), target))) {
          throw new Error(`CANDIDATE_SYMLINK_ESCAPES_ROOT: ${relativePath}`);
        }
        await symlink(target, destinationPath);
        const bytes = Buffer.from(target, "utf8");
        entries.push({ path: relativePath, type: "symlink", target, sha256: sha256(bytes), size: bytes.length, mode });
      } else if (info.isDirectory()) {
        entries.push({ path: relativePath, type: "directory", sha256: null, size: 0, mode });
        await walk(sourcePath, destinationPath, relativePath);
      } else if (info.isFile()) {
        await copyFile(sourcePath, destinationPath);
        await chmod(destinationPath, info.mode & 0o777);
        const bytes = await readFile(destinationPath);
        entries.push({ path: relativePath, type: "file", sha256: sha256(bytes), size: bytes.length, mode });
      } else throw new Error(`CANDIDATE_SPECIAL_FILE_UNSUPPORTED: ${relativePath}`);
    }
  }
  await walk(sourceRoot, destinationRoot);
  return entries;
}

async function inventoryCandidateTree(root, policy) {
  const ignored = new Set(policy.ignored_directories.map((item) => item.name));
  const forbidden = new Set(policy.forbidden_directories.map((item) => item.name));
  const entries = [];
  async function walk(directory, prefix = "") {
    const children = await readdir(directory, { withFileTypes: true });
    children.sort((left, right) => compareUnicodeCodePoints(left.name, right.name));
    for (const child of children) {
      const relativePath = prefix ? `${prefix}/${child.name}` : child.name;
      if (forbidden.has(child.name)) throw new Error(`CANDIDATE_FORBIDDEN_DIRECTORY: ${relativePath}`);
      if (child.isDirectory() && ignored.has(child.name)) continue;
      const path = join(directory, child.name);
      const info = await lstat(path);
      const mode = (info.mode & 0o777).toString(8).padStart(4, "0");
      if (info.isSymbolicLink()) {
        const target = await readlink(path);
        if (isAbsolute(target) || !isWithin(root, resolve(dirname(path), target))) {
          throw new Error(`CANDIDATE_SYMLINK_ESCAPES_ROOT: ${relativePath}`);
        }
        const bytes = Buffer.from(target, "utf8");
        entries.push({ path: relativePath, type: "symlink", target, sha256: sha256(bytes), size: bytes.length, mode });
      } else if (info.isDirectory()) {
        entries.push({ path: relativePath, type: "directory", sha256: null, size: 0, mode });
        await walk(path, relativePath);
      } else if (info.isFile()) {
        const bytes = await readFile(path);
        entries.push({ path: relativePath, type: "file", sha256: sha256(bytes), size: bytes.length, mode });
      } else throw new Error(`CANDIDATE_SPECIAL_FILE_UNSUPPORTED: ${relativePath}`);
    }
  }
  await walk(root);
  return entries;
}

async function writeAtomic(path, bytes) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  await writeFile(temporary, bytes, { flag: "wx" });
  try {
    await link(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }
  await rm(temporary, { force: true }).catch(() => {});
}

async function assertOutputAbsent(path) {
  try {
    await lstat(path);
  } catch (error) {
    if (error?.code === "ENOENT") return;
    throw error;
  }
  throw new Error(`OUTPUT_EXISTS: ${path}`);
}

async function assertNoOtherCollectedAttempt(unitRoot, taskId, attemptId) {
  const taskEvidenceRoot = join(unitRoot, "evidence", "tasks", taskId);
  let directories;
  try {
    directories = (await readdir(taskEvidenceRoot, { withFileTypes: true }))
      .filter((item) => item.isDirectory() && !item.name.startsWith("."));
  } catch (error) {
    if (error?.code === "ENOENT") return;
    throw error;
  }
  const conflicting = directories.map((item) => item.name).filter((name) => name !== attemptId);
  if (conflicting.length) {
    throw new Error(`COLLECTED_ATTEMPT_AMBIGUOUS: ${taskId}: ${conflicting.join(",")}`);
  }
}

async function fileArtifact(unitRoot, path) {
  const source = await readRegularFile(path);
  return artifact(unitRelative(unitRoot, source.absolute, "artifact"), source);
}

async function inventoryEvidence(root, evidenceRootRelative, excluded = new Set()) {
  const artifacts = [];
  async function walk(directory) {
    const children = await readdir(directory, { withFileTypes: true });
    children.sort((left, right) => compareUnicodeCodePoints(left.name, right.name));
    for (const child of children) {
      const path = join(directory, child.name);
      const localPath = relative(root, path).split(sep).join("/");
      const unitPath = `${evidenceRootRelative}/${localPath}`;
      if (excluded.has(unitPath)) continue;
      const info = await lstat(path);
      if (info.isDirectory()) await walk(path);
      else if (info.isSymbolicLink()) {
        const target = await readlink(path);
        const bytes = Buffer.from(target, "utf8");
        artifacts.push({ path: unitPath, sha256: sha256(bytes), size: bytes.length, type: "symlink", target });
      } else if (info.isFile()) {
        const bytes = await readFile(path);
        artifacts.push({ path: unitPath, sha256: sha256(bytes), size: bytes.length, type: "file" });
      } else throw new Error(`EVIDENCE_SPECIAL_FILE_UNSUPPORTED: ${unitPath}`);
    }
  }
  await walk(root);
  return artifacts.sort((left, right) => compareUnicodeCodePoints(left.path, right.path));
}

function normalizeExecutionError(error, businessStatus) {
  if (!error && businessStatus === "completed") return null;
  if (error && typeof error === "object" && !Array.isArray(error)
      && typeof error.code === "string" && typeof error.message === "string") {
    return { code: error.code, message: error.message };
  }
  return {
    code: businessStatus.toUpperCase(),
    message: typeof error === "string" && error.trim() ? error : `execution ended with ${businessStatus}`,
  };
}

function collectionStageStatus(state, completeness) {
  if (state.execution.business_status === "infrastructure_error") return "partial";
  if (state.execution.business_status === "completed" && completeness !== "complete") return "partial";
  return "completed";
}

function buildExecutionRecord({
  manifest,
  state,
  traceBundle,
  resource,
  finalResponse,
  candidateArtifact,
  evidenceRootRelative,
}) {
  const traceComplete = traceBundle?.index?.completeness?.status === "complete"
    && traceBundle.index.completeness.omitted_event_count === 0;
  const resourceComplete = resource?.value?.collection?.status === "complete";
  const evidenceAvailable = Boolean(traceBundle || resource || finalResponse);
  const completeness = traceComplete && resourceComplete
    ? "complete"
    : evidenceAvailable ? "partial" : "unavailable";
  const missing = [];
  if (!traceBundle) missing.push("raw_trace", "transcript", "trace_index");
  else if (!traceComplete) missing.push(...(traceBundle.index.completeness?.missing || ["trace_completeness"]));
  if (!resource) missing.push("resource_metrics");
  else if (!resourceComplete) missing.push("resource_metrics_complete_coverage");
  const agentDuration = resource?.value?.metrics?.timing?.agent_duration_seconds?.value ?? null;
  const requestedModel = manifest.unit?.model?.requested_id;
  const client = state.client || state.extensions?.client || {};
  const actualModel = client.model || null;
  return {
    schema_id: EXECUTION_RECORD_SCHEMA,
    schema_version: 1,
    identity: { ...state.identity },
    dataset: { id: state.dataset.id, digest: state.dataset.digest },
    phase: state.phase,
    harness: {
      id: manifest.unit?.harness?.id || "astronstudio",
      platform: manifest.unit?.harness?.platform || state.identity.unit_id,
      version: client.version || manifest.unit?.harness?.version || null,
    },
    model: {
      requested_id: requestedModel,
      actual_id: actualModel,
      reasoning_effort: client.reasoning || manifest.unit?.model?.reasoning_effort || null,
      verification_status: actualModel && actualModel === requestedModel ? "verified" : actualModel ? "unverified" : "unknown",
    },
    execution: {
      business_status: state.execution.business_status,
      started_at: state.execution.started_at || null,
      finished_at: state.execution.finished_at || null,
      duration_seconds: state.execution.duration_seconds ?? null,
      agent_duration_seconds: agentDuration,
      error: normalizeExecutionError(state.execution.error, state.execution.business_status),
    },
    prompt: {
      sha256: state.prompt.sha256,
      send_status: state.prompt.send_status,
      sent_at: state.prompt.sent_at || null,
    },
    session: {
      thread_id: state.session?.thread_id || null,
      turn_id: state.session?.turn_id || null,
      session_id: state.session?.session_id || null,
      cwd: state.session?.cwd || null,
      verified: state.session?.verified === true,
    },
    evidence: {
      completeness,
      transcript_path: traceBundle ? `${evidenceRootRelative}/trace/transcript.jsonl` : null,
      trace_index_path: traceBundle ? `${evidenceRootRelative}/trace/trace-index.json` : null,
      final_response_path: finalResponse ? `${evidenceRootRelative}/final-response.md` : null,
      missing: [...new Set(missing)].sort(),
    },
    candidate: {
      path: candidateArtifact.candidate.path,
      frozen_sha256: candidateArtifact.expected_sha256,
      frozen_at: candidateArtifact.frozen_at,
      drift_status: "stable",
    },
    resource_metrics_path: resource ? `${evidenceRootRelative}/resource-metrics.json` : null,
    human_assistance: state.human_assistance || {
      mode: "automatic",
      operation_count: 0,
      semantic_intervention_count: 0,
    },
  };
}

async function verifyArtifactPath(unitRoot, row) {
  const path = resolveWithin(unitRoot, row.path, "artifact");
  const info = await lstat(path);
  let bytes;
  if (row.type === "symlink") {
    if (!info.isSymbolicLink()) throw new Error(`EVIDENCE_ARTIFACT_TYPE_MISMATCH: ${row.path}`);
    const target = await readlink(path);
    bytes = Buffer.from(target, "utf8");
    if (row.target !== target) throw new Error(`EVIDENCE_SYMLINK_TARGET_MISMATCH: ${row.path}`);
  } else {
    if (!info.isFile() || info.isSymbolicLink()) throw new Error(`EVIDENCE_ARTIFACT_TYPE_MISMATCH: ${row.path}`);
    bytes = await readFile(path);
  }
  if (row.sha256 !== sha256(bytes) || row.size !== bytes.length) {
    throw new Error(`EVIDENCE_ARTIFACT_DIGEST_MISMATCH: ${row.path}`);
  }
}

export async function verifyGeneralCollection(options) {
  const unitRoot = await realpath(resolve(options.unitRoot));
  const receiptSource = await readJsonFile(join(unitRoot, "receipts", "collect-evidence-receipt.json"));
  const receipt = receiptSource.value;
  if (receipt?.schema_id !== RECEIPT_SCHEMA || receipt?.stage !== "collect-evidence") {
    throw new Error("COLLECT_RECEIPT_UNSUPPORTED");
  }
  const rows = (receipt.tasks || []).filter((item) => item.task_id === options.taskId);
  if (rows.length !== 1) throw new Error(`COLLECT_RECEIPT_TASK_AMBIGUOUS: ${options.taskId}`);
  const row = rows[0];
  const evidenceRelative = `evidence/tasks/${options.taskId}/${row.attempt_id}`;
  const evidenceRoot = resolveWithin(unitRoot, evidenceRelative, "evidence root");
  const [manifestSource, recordSource, candidateSource] = await Promise.all([
    readJsonFile(join(evidenceRoot, "evidence-manifest.json")),
    readJsonFile(join(evidenceRoot, "execution-record.json")),
    readJsonFile(join(evidenceRoot, "candidate", "candidate-artifact.json")),
  ]);
  const evidenceManifest = manifestSource.value;
  const record = recordSource.value;
  const candidate = candidateSource.value;
  if (evidenceManifest?.schema_version !== EVIDENCE_MANIFEST_SCHEMA
      || !sameIdentity(evidenceManifest.identity, record.identity)
      || !sameIdentity(candidate.identity, record.identity)
      || candidate.schema_version !== CANDIDATE_ARTIFACT_SCHEMA) {
    throw new Error("COLLECTION_IDENTITY_MISMATCH");
  }
  if (receipt.scope?.batch_id !== record.identity.batch_id
      || receipt.scope?.unit_id !== record.identity.unit_id
      || receipt.dataset?.id !== record.dataset?.id
      || receipt.dataset?.digest !== record.dataset?.digest
      || row.attempt_id !== record.identity.attempt_id) {
    throw new Error("COLLECT_RECEIPT_IDENTITY_MISMATCH");
  }
  if (receipt.status === "completed"
      && (receipt.tasks || []).some((item) => item.status !== "completed")) {
    throw new Error("COLLECT_RECEIPT_STATUS_MISMATCH");
  }
  if (record.candidate?.drift_status !== "stable"
      || typeof record.candidate.path !== "string"
      || typeof record.candidate.frozen_at !== "string"
      || record.candidate.frozen_sha256 !== candidate.expected_sha256
      || record.candidate.path !== candidate.candidate?.path
      || record.candidate.frozen_at !== candidate.frozen_at
      || candidate.candidate?.sha256 !== candidate.expected_sha256) {
    throw new Error("EXECUTION_RECORD_CANDIDATE_MISMATCH");
  }
  const expectedEvidenceArtifacts = await inventoryEvidence(
    evidenceRoot,
    evidenceRelative,
    new Set([
      `${evidenceRelative}/evidence-manifest.json`,
      `${evidenceRelative}/execution-record.json`,
    ]),
  );
  if (JSON.stringify(evidenceManifest.artifacts) !== JSON.stringify(expectedEvidenceArtifacts)) {
    throw new Error("EVIDENCE_MANIFEST_SCOPE_MISMATCH");
  }
  const expectedReceiptPaths = [
    `${evidenceRelative}/candidate/candidate-artifact.json`,
    `${evidenceRelative}/evidence-manifest.json`,
    `${evidenceRelative}/execution-record.json`,
    `${evidenceRelative}/process-cleanup.json`,
  ];
  const actualReceiptPaths = (receipt.artifacts || [])
    .filter((item) => item.path.startsWith(`${evidenceRelative}/`))
    .map((item) => item.path);
  if (JSON.stringify(actualReceiptPaths) !== JSON.stringify(expectedReceiptPaths)) {
    throw new Error("COLLECT_RECEIPT_ARTIFACT_SCOPE_MISMATCH");
  }
  for (const item of receipt.artifacts || []) await verifyArtifactPath(unitRoot, { ...item, type: "file" });

  const runtimePolicy = candidate.runtime_directory_policy;
  const integrity = createWorkspaceIntegrity({
    treeHashAlgorithm: TREE_HASH_ALGORITHM,
    candidateArtifactSchema: CANDIDATE_ARTIFACT_SCHEMA,
    runtimeDirectoryPolicySchema: RUNTIME_POLICY_SCHEMA,
    ignoredDirectories: runtimePolicy?.ignored_directories || [],
    forbiddenDirectories: runtimePolicy?.forbidden_directories || [],
  });
  integrity.loadCandidateArtifact(candidateSource.absolute);
  const candidatePath = resolveWithin(unitRoot, candidate.candidate.path, "frozen candidate");
  const sourcePath = resolveWithin(unitRoot, candidate.source_workspace.path, "source workspace");
  const candidateCheck = integrity.verifyWorkspace(
    candidatePath,
    candidate.expected_sha256,
    "verify:frozen-candidate",
    { allowIgnoredRuntimeDirectories: true },
  );
  const sourceCheck = integrity.verifyWorkspace(
    sourcePath,
    candidate.source_workspace.sha256,
    "verify:source-workspace",
    { allowIgnoredRuntimeDirectories: true },
  );
  const artifactPolicy = {
    ignored_directories: (runtimePolicy?.ignored_directories || []).map((name) => ({ name })),
    forbidden_directories: (runtimePolicy?.forbidden_directories || []).map((name) => ({ name })),
  };
  const candidateEntries = await inventoryCandidateTree(candidatePath, artifactPolicy);
  if (JSON.stringify(candidate.entries) !== JSON.stringify(candidateEntries)
      || candidate.candidate.file_count !== candidateCheck.file_count
      || candidate.candidate.total_bytes !== candidateCheck.total_bytes
      || candidate.source_workspace.file_count !== sourceCheck.file_count
      || candidate.source_workspace.total_bytes !== sourceCheck.total_bytes
      || candidate.source_workspace.sha256 !== candidate.expected_sha256
      || candidate.source_workspace.snapshot_before_sha256 !== candidate.expected_sha256
      || candidate.source_workspace.snapshot_after_stability_sha256 !== candidate.expected_sha256
      || candidate.source_workspace.snapshot_after_copy_sha256 !== candidate.expected_sha256) {
    throw new Error("CANDIDATE_ARTIFACT_SCOPE_MISMATCH");
  }
  return {
    status: "PASS",
    task_id: options.taskId,
    attempt_id: row.attempt_id,
    evidence_root: evidenceRoot,
    candidate_sha256: candidate.expected_sha256,
    evidence_manifest_sha256: manifestSource.sha256,
    execution_record_sha256: recordSource.sha256,
    receipt_sha256: receiptSource.sha256,
    candidate_check: candidateCheck,
    source_check: sourceCheck,
  };
}

async function buildUnitReceipt(unitRoot, manifest, collectedAt) {
  const taskRows = [];
  const artifacts = [];
  for (const taskId of manifest.task_ids || []) {
    const root = join(unitRoot, "evidence", "tasks", taskId);
    let directories;
    try {
      directories = (await readdir(root, { withFileTypes: true }))
        .filter((item) => item.isDirectory() && !item.name.startsWith("."));
    } catch (error) {
      if (error?.code === "ENOENT") return null;
      throw error;
    }
    if (directories.length === 0) return null;
    if (directories.length !== 1) throw new Error(`COLLECTED_ATTEMPT_AMBIGUOUS: ${taskId}`);
    const attemptId = directories[0].name;
    const evidenceRoot = join(root, attemptId);
    const evidenceManifest = (await readJsonFile(join(evidenceRoot, "evidence-manifest.json"))).value;
    if (evidenceManifest.identity?.task_id !== taskId || evidenceManifest.identity?.attempt_id !== attemptId) {
      throw new Error(`COLLECTED_ATTEMPT_IDENTITY_MISMATCH: ${taskId}`);
    }
    taskRows.push({ task_id: taskId, attempt_id: attemptId, status: evidenceManifest.collection.stage_status });
    for (const name of [
      "execution-record.json",
      "evidence-manifest.json",
      "process-cleanup.json",
      "candidate/candidate-artifact.json",
    ]) {
      artifacts.push(await fileArtifact(unitRoot, join(evidenceRoot, name)));
    }
  }
  const allCompleted = taskRows.every((item) => item.status === "completed");
  return {
    schema_id: RECEIPT_SCHEMA,
    schema_version: 1,
    scope: { batch_id: manifest.batch_id, unit_id: manifest.unit_id },
    dataset: { id: manifest.dataset.id, digest: manifest.dataset.digest },
    stage: "collect-evidence",
    status: allCompleted ? "completed" : "partial",
    created_at: collectedAt,
    task_ids: [...manifest.task_ids],
    tasks: taskRows,
    artifacts: artifacts.sort((left, right) => compareUnicodeCodePoints(left.path, right.path)),
    integrity: {
      scope_matches: taskRows.map((item) => item.task_id).join("\0") === manifest.task_ids.join("\0"),
      identities_match: true,
      hashes_verified: true,
      valid: true,
    },
    error: null,
  };
}

export async function finalizeExecution(options, profile, overrides = {}) {
  if (profile.generic && (typeof overrides.validateInputs !== "function" || typeof overrides.validateCleanup !== "function")) {
    throw new Error("GENERAL_COLLECTION_GUARDS_REQUIRED");
  }
  const now = overrides.now || (() => new Date().toISOString());
  const sleep = overrides.sleep
    || ((milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds)));
  const terminateProcesses = overrides.terminateProcesses;
  if (typeof terminateProcesses !== "function") throw new Error("TASK_PROCESS_CLEANUP_HOOK_REQUIRED");
  const unitRoot = await realpath(resolve(options.unitRoot));
  const [manifestSource, stateSource] = await Promise.all([
    readJsonFile(join(unitRoot, "manifest.json")),
    readJsonFile(options.stateFile),
  ]);
  const binding = await assertUnitAndState(unitRoot, manifestSource, stateSource, profile);
  const { manifest, state, workspace, promptSource } = binding;
  const identity = state.identity;
  const evidenceRootRelative = `evidence/tasks/${identity.task_id}/${identity.attempt_id}`;
  const evidenceRoot = resolveWithin(unitRoot, evidenceRootRelative, "evidence root");
  const receiptOutputPath = join(unitRoot, "receipts", "collect-evidence-receipt.json");
  await Promise.all([
    assertOutputAbsent(evidenceRoot),
    assertOutputAbsent(receiptOutputPath),
    assertNoOtherCollectedAttempt(unitRoot, identity.task_id, identity.attempt_id),
  ]);
  const [traceBundle, resource, finalResponse, policy] = await Promise.all([
    loadTraceBundle(options.traceIndex, state, profile),
    options.resourceMetrics ? null : Promise.resolve(null),
    loadFinalResponse(unitRoot, state),
    loadCandidatePolicy(options.candidatePolicy),
  ]);
  const resolvedResource = options.resourceMetrics
    ? await loadResourceMetrics(options.resourceMetrics, stateSource, traceBundle, profile)
    : resource;
  if (state.execution.business_status === "completed" && (!traceBundle || !resolvedResource)) {
    throw new Error("COMPLETED_EXECUTION_EVIDENCE_INCOMPLETE");
  }
  const inputSnapshot = { manifestSource, stateSource, traceBundle, resource: resolvedResource, finalResponse };
  if (overrides.validateInputs) await overrides.validateInputs(inputSnapshot);
  const cleanup = await terminateProcesses(workspace, {
    quietMilliseconds: options.processQuietMilliseconds,
    waitMilliseconds: options.processWaitMilliseconds,
    ...overrides.processOverrides,
  });
  if (cleanup?.supported !== true || cleanup.success !== true) {
    throw new Error(`TASK_PROCESS_CLEANUP_FAILED: ${cleanup?.error || "residual task process or quiet window incomplete"}`);
  }

  if (overrides.validateCleanup) await overrides.validateCleanup(cleanup, workspace, options);

  const integrity = createIntegrity(policy);
  const before = integrity.snapshotWorkspace(workspace);
  if (before.forbidden_directories.length) {
    throw new Error(`CANDIDATE_FORBIDDEN_DIRECTORY: ${before.forbidden_directories.join(",")}`);
  }
  if (options.stabilityMilliseconds) await sleep(options.stabilityMilliseconds);
  const stable = integrity.snapshotWorkspace(workspace);
  if (before.sha256 !== stable.sha256) {
    throw new Error(`WORKSPACE_NOT_STABLE: before=${before.sha256}, after=${stable.sha256}`);
  }

  const parent = dirname(evidenceRoot);
  await mkdir(parent, { recursive: true });
  const staging = join(parent, `.${identity.attempt_id}.collecting-${process.pid}-${randomUUID()}`);
  const collectedAt = now();
  try {
    await mkdir(staging, { recursive: false });
    const candidateWorkspace = join(staging, "candidate", "workspace");
    const candidateEntries = await copyCandidateTree(workspace, candidateWorkspace, policy);
    const copied = integrity.snapshotWorkspace(candidateWorkspace);
    if (copied.sha256 !== stable.sha256) {
      throw new Error(`CANDIDATE_COPY_MISMATCH: source=${stable.sha256}, copy=${copied.sha256}`);
    }
    const sourceAfterCopy = integrity.snapshotWorkspace(workspace);
    if (sourceAfterCopy.sha256 !== stable.sha256) {
      throw new Error(`WORKSPACE_DRIFTED_DURING_FREEZE: frozen=${stable.sha256}, actual=${sourceAfterCopy.sha256}`);
    }
    const runtimePolicy = integrity.runtimeDirectoryPolicy();
    const candidateArtifact = {
      schema_version: CANDIDATE_ARTIFACT_SCHEMA,
      identity: { ...identity },
      hash_algorithm: TREE_HASH_ALGORITHM,
      expected_sha256: copied.sha256,
      frozen_at: collectedAt,
      policy: {
        schema_version: policy.schema_version,
        policy_source: policy.policy_source,
        ignored_directories: policy.ignored_directories,
        forbidden_directories: policy.forbidden_directories,
      },
      runtime_directory_policy: runtimePolicy,
      source_workspace: {
        path: unitRelative(unitRoot, workspace, "source workspace"),
        sha256: stable.sha256,
        file_count: stable.file_count,
        total_bytes: stable.total_bytes,
        snapshot_before_sha256: before.sha256,
        snapshot_after_stability_sha256: stable.sha256,
        snapshot_after_copy_sha256: sourceAfterCopy.sha256,
        stability_window_milliseconds: options.stabilityMilliseconds,
        ignored_runtime_directories: stable.ignored_runtime_directories,
        forbidden_directories: stable.forbidden_directories,
      },
      candidate: {
        path: `${evidenceRootRelative}/candidate/workspace`,
        sha256: copied.sha256,
        file_count: copied.file_count,
        total_bytes: copied.total_bytes,
      },
      entries: candidateEntries,
    };
    await mkdir(join(staging, "candidate"), { recursive: true });
    await writeFile(join(staging, "candidate", "candidate-artifact.json"), prettyJson(candidateArtifact), { flag: "wx" });

    await mkdir(join(staging, "execution"), { recursive: true });
    await writeFile(join(staging, "execution", "automation-state.json"), stateSource.bytes, { flag: "wx" });
    await writeFile(join(staging, "execution", "PROMPT.md"), promptSource.bytes, { flag: "wx" });
    await writeFile(join(staging, "execution", "unit-manifest.json"), manifestSource.bytes, { flag: "wx" });
    const preCollectRecord = join(dirname(stateSource.absolute), "execution-record.json");
    try {
      const source = await readRegularFile(preCollectRecord);
      await writeFile(join(staging, "execution", "execution-record.pre-collect.json"), source.bytes, { flag: "wx" });
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }

    if (traceBundle) {
      await mkdir(join(staging, "trace"), { recursive: true });
      await writeFile(join(staging, "trace", "trace-index.json"), traceBundle.indexSource.bytes, { flag: "wx" });
      await writeFile(join(staging, "trace", "transcript.jsonl"), traceBundle.transcriptSource.bytes, { flag: "wx" });
      for (const item of traceBundle.traceArtifacts) {
        await mkdir(join(staging, "trace", dirname(item.relative)), { recursive: true });
        await writeFile(join(staging, "trace", item.relative), item.source.bytes, { flag: "wx" });
      }
    }
    if (resolvedResource) {
      await writeFile(join(staging, "resource-metrics.json"), resolvedResource.source.bytes, { flag: "wx" });
    }
    if (finalResponse) await writeFile(join(staging, "final-response.md"), finalResponse.bytes, { flag: "wx" });
    const cleanupDocument = {
      ...cleanup,
      collected_at: collectedAt,
      identity: { ...identity },
      candidate_workspace: unitRelative(unitRoot, workspace, "cleanup workspace"),
    };
    await writeFile(join(staging, "process-cleanup.json"), prettyJson(cleanupDocument), { flag: "wx" });

    const record = buildExecutionRecord({
      manifest,
      state,
      traceBundle,
      resource: resolvedResource,
      finalResponse,
      candidateArtifact,
      evidenceRootRelative,
    });
    const stageStatus = collectionStageStatus(state, record.evidence.completeness);
    const manifestPath = `${evidenceRootRelative}/evidence-manifest.json`;
    const recordPath = `${evidenceRootRelative}/execution-record.json`;
    const evidenceArtifacts = await inventoryEvidence(staging, evidenceRootRelative, new Set([manifestPath, recordPath]));
    const evidenceManifest = {
      schema_version: EVIDENCE_MANIFEST_SCHEMA,
      identity: { ...identity },
      dataset: { id: state.dataset.id, digest: state.dataset.digest },
      collected_at: collectedAt,
      collection: {
        collector: profile.id,
        version: profile.version,
        stage_status: stageStatus,
        business_status: state.execution.business_status,
        process_cleanup_path: `${evidenceRootRelative}/process-cleanup.json`,
        candidate_artifact_path: `${evidenceRootRelative}/candidate/candidate-artifact.json`,
        execution_record_path: recordPath,
      },
      artifacts: evidenceArtifacts,
    };
    await writeFile(join(staging, "evidence-manifest.json"), prettyJson(evidenceManifest), { flag: "wx" });
    await writeFile(join(staging, "execution-record.json"), prettyJson(record), { flag: "wx" });
    if (overrides.validateInputs) await overrides.validateInputs(inputSnapshot);
    await rename(staging, evidenceRoot);
  } catch (error) {
    await rm(staging, { recursive: true, force: true }).catch(() => {});
    throw error;
  }

  const receipt = await buildUnitReceipt(unitRoot, manifest, collectedAt);
  let receiptPath = null;
  if (receipt) {
    receiptPath = receiptOutputPath;
    await writeAtomic(receiptPath, prettyJson(receipt));
  }
  const verification = receipt
    ? await verifyGeneralCollection({ unitRoot, taskId: identity.task_id })
    : null;
  return {
    status: "PASS",
    task_id: identity.task_id,
    attempt_id: identity.attempt_id,
    evidence_root: evidenceRoot,
    receipt_path: receiptPath,
    receipt_status: receipt?.status || null,
    candidate_sha256: verification?.candidate_sha256 || null,
    evidence_manifest_sha256: verification?.evidence_manifest_sha256 || null,
    execution_record_sha256: verification?.execution_record_sha256 || null,
    receipt_sha256: verification?.receipt_sha256 || null,
  };
}
