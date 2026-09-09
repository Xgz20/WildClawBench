import { homedir } from "node:os";
import { join } from "node:path";

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

export const DRIVER_VERSION = "1.9.3";
export const DEFAULT_APP_PATH = "/Applications/QwenWorkCN.app";
export const DEFAULT_BUNDLE_ID = "cn.qwenwork.desktop.mac";
export const DEFAULT_ENDPOINT = "http://127.0.0.1:9250";
export const DEFAULT_SESSION_DB = join(homedir(), "Library", "Application Support", "QwenWorkCN", "data", "agents.db");
export const QWENWORK_PROFILE = Object.freeze({
  id: "qwenwork",
  displayName: "QwenWork",
  driverVersion: DRIVER_VERSION,
  controlBackend: "electron-cdp+qwenwork-project-dialog+macos-accessibility+agents-sqlite",
});

function optionWasProvided(argv, name) {
  return argv.some((value) => value === name);
}

export function parseArgs(argv) {
  const parsed = parseBaseArgs(argv);
  if (!optionWasProvided(argv, "--app-path")) parsed.appPath = DEFAULT_APP_PATH;
  if (!optionWasProvided(argv, "--endpoint")) parsed.endpoint = DEFAULT_ENDPOINT;
  if (!optionWasProvided(argv, "--session-db")) parsed.sessionDb = DEFAULT_SESSION_DB;
  return parsed;
}

export async function resolveConfig(parsed) {
  return resolveBaseConfig(parsed);
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
