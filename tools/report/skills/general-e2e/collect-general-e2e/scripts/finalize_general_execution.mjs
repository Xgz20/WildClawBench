#!/usr/bin/env node
import { realpathSync } from "node:fs";
import { access, readFile, realpath } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { performance } from "node:perf_hooks";
import { runCapture } from "../vendor/e2e-shared/desktop-runtime/process.mjs";
import { finalizeExecution, parseArgs, verifyGeneralCollection } from "./lib/general-finalizer.mjs";

export { verifyGeneralCollection };
export const FINALIZER_ID = "general-e2e-finalizer";
export const FINALIZER_VERSION = "0.1.0";
const PROFILE = Object.freeze({
  id: FINALIZER_ID, version: FINALIZER_VERSION, generic: true,
  executionStateSchema: "wildclawbench.general-e2e-execution-state/v1",
  traceIndexSchema: "urn:wildclawbench:schema:general-e2e:trace-index:v2", traceVersion: 2,
});

async function validatorPath() {
  const skill = dirname(dirname(fileURLToPath(import.meta.url)));
  const vendored = join(skill, "vendor/e2e-shared/general-contracts/collection_validation.py");
  try { await access(vendored); return vendored; } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  // Development checkout only. Released Skill packages use the vendored source.
  let parent = skill;
  while (dirname(parent) !== parent) {
    const candidate = join(parent, "eval_general_e2e/contracts/collection_validation.py");
    try { await access(candidate); return candidate; } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    parent = dirname(parent);
  }
  throw new Error("GENERAL_COLLECTION_VALIDATOR_UNAVAILABLE");
}

export function assertCleanupEvidence(cleanup, workspace, options, hook, elapsedMilliseconds) {
  const minimum = options.processQuietMilliseconds ?? 5_000;
  if (!Number.isFinite(minimum) || minimum <= 0) throw new Error("TASK_PROCESS_QUIET_WINDOW_REQUIRED");
  if (cleanup?.schema_version !== "wildclawbench.general-e2e-task-process-cleanup/v1"
      || cleanup.supported !== true || cleanup.success !== true || cleanup.platform !== hook.platform
      || !Number.isFinite(cleanup.quiet_window_milliseconds) || cleanup.quiet_window_milliseconds < minimum
      || !Number.isFinite(cleanup.quiet_observed_milliseconds) || cleanup.quiet_observed_milliseconds < minimum
      || cleanup.quiet_observed_milliseconds > elapsedMilliseconds + 1
      || typeof cleanup.late_process_detected !== "boolean" || !Array.isArray(cleanup.termination_attempts)) {
    throw new Error("TASK_PROCESS_CLEANUP_EVIDENCE_INVALID");
  }
  for (const name of ["before", "after"]) {
    const snapshot = cleanup[name];
    if (snapshot?.supported !== true || snapshot.platform !== hook.platform
        || snapshot.workspace !== workspace || !Array.isArray(snapshot.targets)
        || !Array.isArray(snapshot.seed_pids) || !Array.isArray(snapshot.root_pids)) {
      throw new Error(`TASK_PROCESS_CLEANUP_SNAPSHOT_INVALID: ${name}`);
    }
  }
  if (cleanup.after.targets.length !== 0) throw new Error("TASK_PROCESS_CLEANUP_RESIDUAL_PROCESSES");
}

/** Trusted adapter code supplies a real cleanup implementation; no default hook. */
export async function finalizeGeneralExecution(options, hooks = {}) {
  const hook = hooks.processCleanup;
  if (!hook || typeof hook.run !== "function" || !hook.id || !hook.version
      || !hook.harness || !["darwin", "win32"].includes(hook.platform)) {
    throw new Error("TASK_PROCESS_CLEANUP_HOOK_REQUIRED");
  }
  if (!options.pythonExecutable || !options.traceIndex || !options.resourceMetrics) {
    throw new Error("GENERAL_COLLECTION_INPUT_REQUIRED: pythonExecutable, traceIndex, resourceMetrics");
  }
  const inputs = await runCapture(options.pythonExecutable, [
    await validatorPath(), "--unit-root", options.unitRoot, "--state-file", options.stateFile,
    "--trace-index", options.traceIndex, "--resource-metrics", options.resourceMetrics,
  ]);
  const validated = JSON.parse(inputs.stdout);
  if (validated.status !== "PASS" || !validated.locks) throw new Error("COLLECTION_VALIDATION_INCOMPLETE");
  let elapsedMilliseconds = 0;
  return finalizeExecution(options, PROFILE, {
    validateInputs: async ({ manifestSource, stateSource, traceBundle, resource, finalResponse }) => {
      const state = stateSource.value;
      const platform = state.driver.platform === "windows" || state.driver.platform.startsWith("windows-") ? "win32"
        : state.driver.platform === "macos" || state.driver.platform.startsWith("macos-") ? "darwin" : null;
      if (hook.harness !== state.driver.harness || hook.platform !== platform) throw new Error("TASK_PROCESS_CLEANUP_HOOK_MISMATCH");
      const sources = [manifestSource, stateSource, traceBundle.indexSource, traceBundle.transcriptSource,
        ...traceBundle.traceArtifacts.map((item) => item.source), resource.source, ...(finalResponse ? [finalResponse] : [])];
      for (const source of sources) {
        const expected = validated.locks[await realpath(source.absolute)];
        if (!expected || source.sha256 !== expected.sha256 || source.size !== expected.size) {
          throw new Error("COLLECTION_INPUT_SNAPSHOT_MISMATCH");
        }
      }
      for (const [path, expected] of Object.entries(validated.locks)) {
        const data = await readFile(path);
        if (data.length !== expected.size || createHash("sha256").update(data).digest("hex") !== expected.sha256) {
          throw new Error("COLLECTION_INPUT_CHANGED");
        }
      }
    },
    terminateProcesses: async (workspace, cleanupOptions) => {
      const started = performance.now();
      const result = await hook.run(workspace, cleanupOptions);
      elapsedMilliseconds = performance.now() - started;
      return result;
    },
    validateCleanup: (cleanup, workspace, resolvedOptions) => assertCleanupEvidence(
      cleanup, workspace, resolvedOptions, hook, elapsedMilliseconds,
    ),
  });
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write("General E2E 通用正式收口接口：finalizeGeneralExecution(options, { processCleanup })。\n"
      + "必须显式提供目标 Harness/平台的进程清理实现；CLI 只提供 --verify-only --unit-root PATH --task-id ID。\n");
    return;
  }
  if (!options.verifyOnly) throw new Error("TASK_PROCESS_CLEANUP_HOOK_REQUIRED: use a platform adapter entrypoint");
  process.stdout.write(`${JSON.stringify(await verifyGeneralCollection(options), null, 2)}\n`);
}
if (process.argv[1] && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url))) {
  main().catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}
