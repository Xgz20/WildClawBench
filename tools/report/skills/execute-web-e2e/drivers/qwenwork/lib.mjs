import {
  AUTOMATION_SCHEMA,
  EXECUTION_SCHEMA,
  PERMISSION_MODES,
  RESUMABLE_PHASES,
  TERMINAL_PHASES,
  assertStateMatches as assertBaseStateMatches,
  atomicWriteJson,
  chooseAttemptSession,
  classifyApprovalCommand,
  classifyDomStatus,
  classifySessionStatus,
  createInitialState as createBaseInitialState,
  diffSnapshots,
  isSubstantiveFinalResponse,
  parseArgs as parseBaseArgs,
  readJsonIfExists,
  resolveConfig as resolveBaseConfig,
  resolveExecutionIdentity as resolveBaseExecutionIdentity,
  runtimeDirectoryPolicy,
  snapshotTree,
  transitionState,
  updateExecutionRecord as updateBaseExecutionRecord,
} from "../workbuddy/lib.mjs";
import {
  MACOS_BUNDLE_ID,
  defaultQwenWorkAppPath,
  defaultQwenWorkSessionDb,
  resolveQwenWorkAppPath,
  validateQwenWorkAppPath,
} from "./platform.mjs";

export {
  AUTOMATION_SCHEMA,
  EXECUTION_SCHEMA,
  PERMISSION_MODES,
  RESUMABLE_PHASES,
  TERMINAL_PHASES,
  atomicWriteJson,
  chooseAttemptSession,
  classifyApprovalCommand,
  classifyDomStatus,
  classifySessionStatus,
  diffSnapshots,
  isSubstantiveFinalResponse,
  readJsonIfExists,
  runtimeDirectoryPolicy,
  snapshotTree,
  transitionState,
};

export const DRIVER_VERSION = "1.10.13";
export const DEFAULT_APP_PATH = defaultQwenWorkAppPath();
export const DEFAULT_BUNDLE_ID = MACOS_BUNDLE_ID;
export const DEFAULT_ENDPOINT = "http://127.0.0.1:9250";
export const DEFAULT_SESSION_DB = defaultQwenWorkSessionDb();
export const QWENWORK_PROFILE = Object.freeze({
  id: "qwenwork",
  displayName: "QwenWork",
  driverVersion: DRIVER_VERSION,
  controlBackend: "electron-cdp+qwenwork-project-dialog+platform-native-folder+agents-sqlite",
});

function optionWasProvided(argv, name) {
  return argv.some((value) => value === name);
}

export function parseArgs(argv) {
  const abandonUserQuestion = argv.includes("--abandon-user-question");
  const parsed = parseBaseArgs(argv.filter((value) => value !== "--abandon-user-question"));
  if (abandonUserQuestion && !parsed.resume) {
    throw new Error("--abandon-user-question 必须与 --resume 一起使用");
  }
  if (abandonUserQuestion && (parsed.retryPreSendFailure || parsed.detachAfterSubmit || parsed.observeOnce)) {
    throw new Error("--abandon-user-question 不能与重试、后台投递或单次观察参数组合使用");
  }
  parsed.abandonUserQuestion = abandonUserQuestion;
  if (!optionWasProvided(argv, "--app-path")) parsed.appPath = DEFAULT_APP_PATH;
  if (!optionWasProvided(argv, "--endpoint")) parsed.endpoint = DEFAULT_ENDPOINT;
  if (!optionWasProvided(argv, "--session-db")) parsed.sessionDb = DEFAULT_SESSION_DB;
  return parsed;
}

export async function resolveConfig(parsed) {
  return resolveBaseConfig(parsed, {
    resolveAppPath: resolveQwenWorkAppPath,
    validateAppPath: validateQwenWorkAppPath,
  });
}

export async function resolveExecutionIdentity(config) {
  return resolveBaseExecutionIdentity(config, QWENWORK_PROFILE);
}

export function createInitialState(config, identity, initialSnapshot) {
  return createBaseInitialState(config, identity, initialSnapshot, QWENWORK_PROFILE);
}

export function assertStateMatches(state, config, identity) {
  return assertBaseStateMatches(state, config, identity, QWENWORK_PROFILE);
}

export async function updateExecutionRecord(config, identityInfo, update) {
  return updateBaseExecutionRecord(config, identityInfo, update, QWENWORK_PROFILE);
}
