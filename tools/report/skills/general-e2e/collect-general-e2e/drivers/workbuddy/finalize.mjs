#!/usr/bin/env node
import { readFile, realpath } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { finalizeGeneralExecution, verifyGeneralCollection } from "../../scripts/finalize_general_execution.mjs";
import { parseArgs } from "../../scripts/lib/general-finalizer.mjs";
import {
  assertWorkBuddyCollectorReadiness,
  createWorkBuddyCleanupHook,
} from "../../vendor/e2e-shared/workbuddy-evidence/cleanup.mjs";

export async function finalizeWorkBuddyExecution(options) {
  if (options.verifyOnly) return verifyGeneralCollection(options);
  if (process.platform !== "darwin") throw new Error("WORKBUDDY_FINALIZER_REQUIRES_MACOS");
  const [state, traceIndex, resourceMetrics] = await Promise.all(
    [options.stateFile, options.traceIndex, options.resourceMetrics].map(async (path) => JSON.parse(await readFile(path, "utf8"))),
  );
  const cleanupHook = createWorkBuddyCleanupHook();
  assertWorkBuddyCollectorReadiness({ state, traceIndex, resourceMetrics, cleanupHook });
  return finalizeGeneralExecution({
    ...options,
    pythonExecutable: options.pythonExecutable || process.env.PYTHON || "python3",
  }, { processCleanup: cleanupHook });
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
    console.log(`WorkBuddy macOS 正式证据收口
node drivers/workbuddy/finalize.mjs --unit-root PATH --state-file PATH --trace-index PATH --resource-metrics PATH [--python PATH]
node drivers/workbuddy/finalize.mjs --verify-only --unit-root PATH --task-id ID
执行真实 Workspace 进程清理、静默窗口、冻结候选和不可变回执；使用通用 finalizer 的目录策略与等待参数。`);
    return;
  }
  console.log(JSON.stringify(await finalizeWorkBuddyExecution({ ...options, pythonExecutable }), null, 2));
}

if (process.argv[1] && await realpath(resolve(process.argv[1])) === await realpath(fileURLToPath(import.meta.url))) {
  main().catch((error) => { console.error(error.message); process.exitCode = 1; });
}
