import {
  COMPONENT_VERSION as DESKTOP_RUNTIME_VERSION,
  isDirectory,
  isFile,
  runCapture,
} from "../../../tools/report/e2e-shared/desktop-runtime/process.mjs";
import {
  COMPONENT_VERSION as RESOURCE_METRICS_VERSION,
  createNativeResourceMetricParsers,
} from "../../../tools/report/e2e-shared/resource-metrics/native-parsers.mjs";
import {
  assertTraceWorkspace,
  findAstronTrace,
  isSafeNativeId,
  readTrace,
  sameNativePath,
} from "../../../tools/report/e2e-shared/resource-metrics/trace-io.mjs";
import {
  COMPONENT_VERSION as WORKSPACE_INTEGRITY_VERSION,
  createWorkspaceIntegrity,
} from "../../../tools/report/e2e-shared/handoff/workspace-integrity.mjs";

export const ASTRONSTUDIO_SHARED_COMPONENTS = Object.freeze({
  "desktop-runtime": DESKTOP_RUNTIME_VERSION,
  "resource-metrics": RESOURCE_METRICS_VERSION,
  "workspace-integrity": WORKSPACE_INTEGRITY_VERSION,
});

export const GENERAL_NATIVE_RESOURCE_PROFILE = Object.freeze({
  schemaVersion: "wildclawbench.general-e2e-native-resource-observation/v1",
  version: RESOURCE_METRICS_VERSION,
  scope: "primary-attempt",
  excludedScope: Object.freeze([
    "judge-usage",
    "control-usage",
    "unobserved-http-retries",
    "unlinked-child-agents",
    "client-background-services",
  ]),
});

export const nativeResourceParsers = createNativeResourceMetricParsers({
  ...GENERAL_NATIVE_RESOURCE_PROFILE,
  // Qwen is a deferred General adapter. Unknown runtime identities remain
  // unverified instead of inheriting Web's Qwen normalization profiles.
  resolveQwenProfile: () => null,
});

export function createGeneralWorkspaceIntegrity({ ignoredDirectories, forbiddenDirectories }) {
  if (!Array.isArray(ignoredDirectories) || !Array.isArray(forbiddenDirectories)) {
    throw new TypeError("General workspace policy must explicitly provide ignored and forbidden directories");
  }
  return createWorkspaceIntegrity({
    treeHashAlgorithm: "wildclawbench.workspace-tree-sha256/v1",
    candidateArtifactSchema: "wildclawbench.general-e2e-candidate-artifact/v1",
    runtimeDirectoryPolicySchema: "wildclawbench.general-e2e-runtime-directory-policy/v1",
    ignoredDirectories,
    forbiddenDirectories,
  });
}

export {
  assertTraceWorkspace,
  findAstronTrace,
  isDirectory,
  isFile,
  isSafeNativeId,
  readTrace,
  runCapture,
  sameNativePath,
};
