import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const TREE_HASH_ALGORITHM = "wildclawbench.workspace-tree-sha256/v1";
export const CANDIDATE_ARTIFACT_SCHEMA = "wildclawbench.web-e2e-candidate-artifact/v1";
export const EXCLUDED_TREE_DIRS = new Set([".git", ".cache", ".vite", "node_modules"]);

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
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

export function snapshotWorkspace(root, { maximumFiles = 20_000 } = {}) {
  const rootInfo = fs.lstatSync(root);
  if (rootInfo.isSymbolicLink() || !rootInfo.isDirectory()) throw new Error(`候选 workspace 缺失或为符号链接：${root}`);
  const canonical = fs.realpathSync(root);
  const entries = [];
  const excludedRuntimeDirectories = [];
  function walk(current, prefix = "") {
    const children = fs.readdirSync(current, { withFileTypes: true });
    children.sort((left, right) => compareUnicodeCodePoints(left.name, right.name));
    for (const child of children) {
      const relative = prefix ? `${prefix}/${child.name}` : child.name;
      if (child.isDirectory()) {
        if (EXCLUDED_TREE_DIRS.has(child.name)) excludedRuntimeDirectories.push(relative);
        else walk(path.join(current, child.name), relative);
        continue;
      }
      if (entries.length >= maximumFiles) throw new Error(`候选目录文件数超过上限 ${maximumFiles}`);
      const filename = path.join(current, child.name);
      const info = fs.lstatSync(filename);
      if (info.isSymbolicLink()) {
        const target = fs.readlinkSync(filename);
        entries.push({ path: relative, type: "symlink", sha256: sha256(target), size: target.length });
      } else if (info.isFile()) {
        entries.push({ path: relative, type: "file", sha256: sha256(fs.readFileSync(filename)), size: info.size });
      }
    }
  }
  walk(canonical);
  const digest = createHash("sha256");
  for (const entry of entries) {
    digest.update(entry.path);
    digest.update("\0");
    digest.update(entry.type);
    digest.update("\0");
    digest.update(entry.sha256);
    digest.update("\n");
  }
  return {
    root: canonical,
    sha256: digest.digest("hex"),
    file_count: entries.length,
    total_bytes: entries.reduce((sum, entry) => sum + entry.size, 0),
    excluded_directories: [...EXCLUDED_TREE_DIRS].sort(),
    excluded_runtime_directories: excludedRuntimeDirectories.sort(compareUnicodeCodePoints),
  };
}

export function loadCandidateArtifact(lockFile) {
  const value = JSON.parse(fs.readFileSync(lockFile, "utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error(`候选冻结文件无效：${lockFile}`);
  if (value.schema_version !== CANDIDATE_ARTIFACT_SCHEMA) throw new Error(`候选冻结 schema 不兼容：${lockFile}`);
  if (value.hash_algorithm !== TREE_HASH_ALGORITHM) throw new Error(`候选冻结哈希算法不兼容：${lockFile}`);
  if (!/^[a-f0-9]{64}$/.test(String(value.expected_sha256 || ""))) throw new Error(`候选冻结 SHA-256 无效：${lockFile}`);
  return value;
}

export function verifyWorkspace(root, expectedSha256, label) {
  const snapshot = snapshotWorkspace(root);
  const result = {
    stage: label,
    checked_at: new Date().toISOString(),
    sha256: snapshot.sha256,
    file_count: snapshot.file_count,
    total_bytes: snapshot.total_bytes,
    excluded_runtime_directories: snapshot.excluded_runtime_directories,
    valid: snapshot.sha256 === expectedSha256 && snapshot.excluded_runtime_directories.length === 0,
  };
  if (!result.valid) {
    const detail = snapshot.excluded_runtime_directories.length
      ? `候选产物包含禁止的运行时目录：${snapshot.excluded_runtime_directories.join(", ")}`
      : `候选产物发生漂移：${label}，期望 ${expectedSha256}，实际 ${snapshot.sha256}`;
    throw Object.assign(
      new Error(detail),
      { integrityCheck: result },
    );
  }
  return result;
}

export function verifyManagedScoringTask(taskContractFile, stage) {
  const contractFile = path.resolve(taskContractFile);
  const taskRoot = path.dirname(path.dirname(contractFile));
  const markerFile = path.join(taskRoot, ".web-e2e-scoring-ready");
  const lockFile = path.join(taskRoot, "private-scoring", "candidate_artifact.json");
  if (!fs.existsSync(markerFile) && !fs.existsSync(lockFile)) return null;
  if (contractFile !== path.join(taskRoot, "private-scoring", "task_contract.json")) {
    throw new Error("受管评分任务必须使用 private-scoring/task_contract.json");
  }
  if (fs.lstatSync(path.join(taskRoot, "private-scoring")).isSymbolicLink()
    || fs.lstatSync(contractFile).isSymbolicLink()) {
    throw new Error("private-scoring 和 task_contract.json 不能是符号链接");
  }
  if (!fs.existsSync(lockFile)) throw new Error(`评分包缺少候选冻结文件：${lockFile}`);
  const lock = loadCandidateArtifact(lockFile);
  const marker = fs.readFileSync(markerFile, "utf8").split(/\r?\n/).filter(Boolean);
  if (marker.length !== 2 || lock.batch_id !== marker[0] || lock.task_id !== marker[1]) {
    throw new Error("候选冻结文件与评分就绪标记不一致");
  }
  return verifyWorkspace(path.join(taskRoot, "workspace"), lock.expected_sha256, stage);
}

export function assertManagedScoringOutput(taskContractFile, outputFile, expectedName) {
  const contractFile = path.resolve(taskContractFile);
  const taskRoot = path.dirname(path.dirname(contractFile));
  const markerFile = path.join(taskRoot, ".web-e2e-scoring-ready");
  const lockFile = path.join(taskRoot, "private-scoring", "candidate_artifact.json");
  if (!fs.existsSync(markerFile) && !fs.existsSync(lockFile)) return;
  const expected = path.join(taskRoot, "private-scoring", expectedName);
  if (path.resolve(outputFile) !== expected) {
    throw new Error(`受管评分任务只能写入 ${path.relative(taskRoot, expected)}`);
  }
}
