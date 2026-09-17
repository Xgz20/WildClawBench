// Web adapter: Web-specific schema, directory policy, and managed-scoring
// marker rules remain local to score-web-e2e.
import fs from "node:fs";
import path from "node:path";
import { createWorkspaceIntegrity } from "../vendor/e2e-shared/handoff/workspace-integrity.mjs";

export const TREE_HASH_ALGORITHM = "wildclawbench.workspace-tree-sha256/v1";
export const CANDIDATE_ARTIFACT_SCHEMA = "wildclawbench.web-e2e-candidate-artifact/v1";
export const RUNTIME_DIRECTORY_POLICY_SCHEMA = "wildclawbench.web-e2e-runtime-directory-policy/v1";

const integrity = createWorkspaceIntegrity({
  treeHashAlgorithm: TREE_HASH_ALGORITHM,
  candidateArtifactSchema: CANDIDATE_ARTIFACT_SCHEMA,
  runtimeDirectoryPolicySchema: RUNTIME_DIRECTORY_POLICY_SCHEMA,
  ignoredDirectories: [".cache", ".vite", "node_modules"],
  forbiddenDirectories: [".git"],
});

export const IGNORED_RUNTIME_DIRS = integrity.ignoredRuntimeDirs;
export const FORBIDDEN_CANDIDATE_DIRS = integrity.forbiddenCandidateDirs;
export const EXCLUDED_TREE_DIRS = integrity.excludedTreeDirs;
export const runtimeDirectoryPolicy = integrity.runtimeDirectoryPolicy;
export const validateRuntimeDirectoryPolicy = integrity.validateRuntimeDirectoryPolicy;
export const sameRuntimeDirectoryPolicy = integrity.sameRuntimeDirectoryPolicy;
export const snapshotWorkspace = integrity.snapshotWorkspace;
export const loadCandidateArtifact = integrity.loadCandidateArtifact;
export const verifyWorkspace = integrity.verifyWorkspace;

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
    const portableExpected = path.relative(taskRoot, expected).split(path.sep).join("/");
    throw new Error(`受管评分任务只能写入 ${portableExpected}`);
  }
}
