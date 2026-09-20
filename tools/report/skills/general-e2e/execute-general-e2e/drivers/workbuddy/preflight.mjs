#!/usr/bin/env node

import { access, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DEFAULT_SKILL_ROOT = resolve(HERE, "../../..");
const SOURCE_FIELDS = Object.freeze({
  turn_id_source: "conversation-index.requests[].id",
  session_id_source: "codebuddy-sessions.vscdb.session:*.conversationId",
  cwd_source: "codebuddy-sessions.vscdb.session:*.cwd",
  terminal_status_source: "codebuddy-sessions.vscdb.session:*.status + conversation-index.requests[].state",
});

async function readable(path, label) {
  try {
    await access(path);
    return { name: label, path, status: "pass" };
  } catch {
    return { name: label, path, status: "fail", reason: "missing" };
  }
}

export async function runWorkBuddyOfflinePreflight({ skillRoot = DEFAULT_SKILL_ROOT } = {}) {
  const root = resolve(skillRoot);
  const cleanup = resolve(root, "collect-general-e2e/scripts/lib/macos-task-processes.mjs");
  const finalizer = resolve(root, "collect-general-e2e/scripts/finalize_general_execution.mjs");
  const collector = resolve(root, "collect-general-e2e/drivers/workbuddy/collector.mjs");
  const driverCleanup = resolve(root, "execute-general-e2e/drivers/workbuddy/cleanup.mjs");
  const state = resolve(root, "execute-general-e2e/drivers/workbuddy/state.mjs");
  const checks = await Promise.all([
    readable(cleanup, "task-process-cleanup shared component"),
    readable(finalizer, "CB-B general finalizer"),
    readable(collector, "WorkBuddy CB-B collector"),
    readable(driverCleanup, "WorkBuddy cleanup adapter"),
    readable(state, "WorkBuddy execution state adapter"),
  ]);
  const [cleanupSource, stateSource] = await Promise.all([
    readFile(driverCleanup, "utf8").catch(() => ""),
    readFile(state, "utf8").catch(() => ""),
  ]);
  const sourceGate = Object.entries(SOURCE_FIELDS).map(([field, value]) => ({
    name: `source gate ${field}`,
    value,
    status: cleanupSource.includes(value) && stateSource.includes(value) ? "pass" : "fail",
  }));
  checks.push(...sourceGate);
  const cbBInput = {
    state_schema: "wildclawbench.general-e2e-execution-state/v1",
    trace_schema: "urn:wildclawbench:schema:general-e2e:trace-index:v2",
    resource_schema: "urn:wildclawbench:schema:general-e2e:resource-metrics:v1",
    cleanup_hook: "workbuddy-macos-task-processes",
  };
  const status = checks.every((check) => check.status === "pass") ? "PASS" : "FAIL";
  return { status, skill_root: root, checks, cb_b_input: cbBInput, side_effects: "none" };
}

function usage() {
  return "用法：node preflight.mjs [--skill-root <脱仓后的 general-e2e skill 根目录>]";
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const index = process.argv.indexOf("--skill-root");
  const skillRoot = index >= 0 ? process.argv[index + 1] : DEFAULT_SKILL_ROOT;
  if (index >= 0 && (!skillRoot || skillRoot.startsWith("-"))) {
    console.error(usage());
    process.exitCode = 2;
  } else {
    runWorkBuddyOfflinePreflight({ skillRoot })
      .then((result) => {
        console.log(JSON.stringify(result, null, 2));
        if (result.status !== "PASS") process.exitCode = 1;
      })
      .catch((error) => { console.error(error.message); process.exitCode = 1; });
  }
}
