#!/usr/bin/env node

import { readFile, realpath } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { finalizeGeneralExecution, verifyGeneralCollection } from "../../scripts/finalize_general_execution.mjs";
import { parseArgs } from "../../scripts/lib/general-finalizer.mjs";
import { terminateDarwinTaskProcesses } from "../../scripts/lib/macos-task-processes.mjs";

export const QWENWORK_CLEANUP_HOOK_ID = "qwenwork-macos-task-processes";
export const QWENWORK_CLEANUP_HOOK_VERSION = "0.1.0";

function createQwenWorkCleanupHook() {
  return {
    id: QWENWORK_CLEANUP_HOOK_ID,
    version: QWENWORK_CLEANUP_HOOK_VERSION,
    harness: "qwenwork",
    platform: "darwin",
    run: (workspace, options = {}) => terminateDarwinTaskProcesses(workspace, options),
  };
}

export async function finalizeQwenWorkExecution(options) {
  if (options.verifyOnly) return verifyGeneralCollection(options);
  if (process.platform !== "darwin") throw new Error("QWENWORK_FINALIZER_REQUIRES_MACOS");
  const [state, traceIndex, resourceMetrics] = await Promise.all(
    [options.stateFile, options.traceIndex, options.resourceMetrics].map(async (path) => JSON.parse(await readFile(path, "utf8"))),
  );
  if (state?.driver?.harness !== "qwenwork" || !String(state?.driver?.platform || "").startsWith("macos")) {
    throw new Error("QWENWORK_FINALIZER_STATE_IDENTITY_INVALID");
  }
  return finalizeGeneralExecution({
    ...options,
    pythonExecutable: options.pythonExecutable || process.env.PYTHON || "python3",
  }, { processCleanup: createQwenWorkCleanupHook() });
}

export async function main(argv = process.argv.slice(2)) {
  const args = [...argv];
  const index = args.indexOf("--python");
  let pythonExecutable = null;
  if (index >= 0) {
    pythonExecutable = args[index + 1];
    if (!pythonExecutable || pythonExecutable.startsWith("--")) throw new Error("--python 缺少值");
    args.splice(index, 2);
  }
  const options = parseArgs(args);
  if (options.help) {
    console.log(`QwenWork macOS General 正式证据收口\nnode drivers/qwenwork/finalize.mjs --unit-root PATH --state-file PATH --trace-index PATH --resource-metrics PATH [--python PATH]\nnode drivers/qwenwork/finalize.mjs --verify-only --unit-root PATH --task-id ID`);
    return;
  }
  console.log(JSON.stringify(await finalizeQwenWorkExecution({ ...options, pythonExecutable }), null, 2));
}

if (process.argv[1] && await realpath(resolve(process.argv[1])) === await realpath(fileURLToPath(import.meta.url))) {
  main().catch((error) => { console.error(error.message); process.exitCode = 1; });
}
