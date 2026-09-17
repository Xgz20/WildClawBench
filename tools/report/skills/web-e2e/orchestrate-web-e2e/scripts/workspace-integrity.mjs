// Web adapter: Web-specific schema and directory policy stay outside the
// scenario-neutral hashing and verification implementation.
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
