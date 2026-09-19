#!/usr/bin/env node
import { realpathSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { finalizeExecution, parseArgs, usage, verifyGeneralCollection } from "./lib/general-finalizer.mjs";
import { terminateDarwinTaskProcesses } from "./lib/macos-task-processes.mjs";
export * from "./lib/general-finalizer.mjs";
export const FINALIZER_ID = "astronstudio-macos-general-e2e-finalizer";
export const FINALIZER_VERSION = "0.1.0";
const PROFILE = Object.freeze({
  id: FINALIZER_ID, version: FINALIZER_VERSION, generic: false,
  executionStateSchema: "wildclawbench.general-e2e-astronstudio-execution-state/v1",
  traceIndexSchema: "urn:wildclawbench:schema:general-e2e:trace-index:v1", traceVersion: 1,
});
export const verifyAstronStudioCollection = verifyGeneralCollection;
export async function finalizeAstronStudioExecution(options, overrides = {}) {
  return finalizeExecution(options, PROFILE, {
    ...overrides, terminateProcesses: overrides.terminateProcesses || terminateDarwinTaskProcesses,
  });
}

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  if (parsed.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  const result = parsed.verifyOnly
    ? await verifyAstronStudioCollection(parsed)
    : await finalizeAstronStudioExecution(parsed);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

const isEntrypoint = process.argv[1]
  && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url));
if (isEntrypoint) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
