#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { finalizeGeneralExecution, verifyGeneralCollection } from "../../scripts/finalize_general_execution.mjs";
import { parseArgs } from "../../scripts/lib/general-finalizer.mjs";
import { cleanupDoubaoCandidateProcesses } from "../../vendor/e2e-shared/doubaowork/process-cleanup.mjs";
import { DRIVER_VERSION } from "../../vendor/e2e-shared/doubaowork/lib.mjs";

export function createDoubaoCleanupHook() {
  return { id: "doubaowork-macos-process-cleanup", version: DRIVER_VERSION, harness: "doubaowork", platform: "darwin",
    run: async (workspace, options) => {
      const result = await cleanupDoubaoCandidateProcesses(workspace, options);
      const snapshot = s => s && ({ ...s, platform: "darwin", workspace_identity: s.workspace,
        workspace: s.workspace?.canonical_path, seed_pids: s.workspace_seed_pids });
      return { ...result, schema_version: "wildclawbench.general-e2e-task-process-cleanup/v1", platform: "darwin",
        before: snapshot(result.before), after: snapshot(result.after) };
    } };
}

export async function main(argv = process.argv.slice(2)) {
  const args = [...argv]; let pythonExecutable = "python3";
  const i = args.indexOf("--python");
  if (i >= 0) { pythonExecutable = args[i + 1]; if (!pythonExecutable || pythonExecutable.startsWith("--")) throw new Error("--python requires a path"); args.splice(i, 2); }
  const options = parseArgs(args);
  if (options.help) { console.log("DoubaoWork General finalizer: --unit-root --state-file --trace-index --resource-metrics --python; --verify-only --task-id"); return; }
  if (options.verifyOnly) { console.log(JSON.stringify(await verifyGeneralCollection(options), null, 2)); return; }
  if (process.platform !== "darwin") throw new Error("DOUBAOWORK_FINALIZER_REQUIRES_MACOS");
  const state = JSON.parse(await readFile(options.stateFile, "utf8"));
  if (state.driver.harness !== "doubaowork" || !state.extensions.doubaowork.native_sources?.terminal || !state.extensions.doubaowork.native_sources?.cwd) throw new Error("DOUBAOWORK_NATIVE_SOURCE_GATE_FAILED");
  console.log(JSON.stringify(await finalizeGeneralExecution({ ...options, pythonExecutable }, { processCleanup: createDoubaoCleanupHook() }), null, 2));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(e => { console.error(e.message); process.exitCode = 1; });
