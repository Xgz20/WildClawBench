#!/usr/bin/env node
import { realpathSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {mkdir,writeFile} from "node:fs/promises";
import {join} from "node:path";
import {randomUUID} from "node:crypto";
import { finalizeExecution, parseArgs, usage, verifyGeneralCollection } from "./lib/general-finalizer.mjs";
import { terminateDarwinTaskProcesses,snapshotDarwinTaskProcesses } from "./lib/macos-task-processes.mjs";
import {createCleanupGuard} from "../vendor/e2e-shared/astronstudio-runtime/guard.mjs";
import {appendFrameworkEvent} from "../vendor/e2e-shared/astronstudio-runtime/diagnostics.mjs";
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
  const operationId=randomUUID(),events=[];
  const journal=join(resolve(options.unitRoot),".general-e2e","diagnostics","framework-events.jsonl");
  let state,guard;
  const audit=async event=>{
    const row=await appendFrameworkEvent(journal,{operation_id:operationId,
      caller:"finalize_astronstudio_execution",identity:state?.identity,...event},
      {durable:event.event==="process.signal.intent"});
    events.push(row);return row;
  };
  const blocked=async error=>{
    const failure=await audit({event:"collect.blocked",error:error.message,blockers:error.blockers||[]});
    const root=join(resolve(options.unitRoot),".general-e2e","diagnostics","blocked-collections",operationId);
    await mkdir(root,{recursive:true});
    await writeFile(join(root,"diagnostic.json"),JSON.stringify({identity:state?.identity,events,
      error:failure.error,blockers:failure.blockers,cleanup_available:Boolean(error.cleanup)},null,2)+"\n",{flag:"wx",mode:0o600})
      .catch(failure=>{if(failure.code!=="EEXIST")throw failure;});
  };
  const prepare=async input=>{
    await overrides.validateInputs?.(input);
    state=input.stateSource.value;
    guard ||= overrides.runtimeSafetyGuard || createCleanupGuard({
      unitRoot:resolve(options.unitRoot),state,
      snapshotProcesses:()=>snapshotDarwinTaskProcesses(input.stateSource.value.candidate_workspace,overrides.processOverrides),
    });
    // validateInputs is called again before publication; recheck global native
    // quiescence there as well as before every signal.
    if(events.length)try{await guard();}catch(error){await blocked(error);throw error;}
  };
  const terminate=overrides.terminateProcesses||terminateDarwinTaskProcesses;
  return finalizeExecution(options, PROFILE, {
    ...overrides,validateInputs:prepare,
    terminateProcesses:async(workspace,processOptions)=>{
      await audit({event:"collect.requested",workspace});
      try {
        const before=await guard();
        await audit({event:"collect.native-idle-verified",guard:before});
        const priorAudit=processOptions.audit,priorAssert=processOptions.assertSafe;
        const cleanup=await terminate(workspace,{...processOptions,operationId,
          audit:async event=>{await audit(event);await priorAudit?.(event);},
          assertSafe:async()=>{await guard();await priorAssert?.();}});
        if(!cleanup.success) {
          const error=Error(`TASK_PROCESS_CLEANUP_FAILED: ${cleanup.error||"quiet window or native writers unresolved"}`);
          error.cleanup=cleanup;throw error;
        }
        const after=await guard();
        await audit({event:cleanup.success?"collect.cleanup.completed":"collect.cleanup.blocked",
          success:cleanup.success,error:cleanup.error||null});
        return {...cleanup,native_runtime_guard:{before,after},framework_audit:{
          schema_version:"wildclawbench.astudio-framework-audit/v1",operation_id:operationId,events}};
      } catch(error) {
        await blocked(error);
        throw error;
      }
    },
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
