#!/usr/bin/env node
import { isEntrypoint } from '../../vendor/e2e-shared/loomy/index.mjs';
import { resolve } from 'node:path';
import { finalizeGeneralExecution, verifyGeneralCollection } from '../../scripts/finalize_general_execution.mjs';
import { parseArgs } from '../../scripts/lib/general-finalizer.mjs';
import { terminateDarwinTaskProcesses } from '../../scripts/lib/macos-task-processes.mjs';

export async function finalizeLoomyExecution(options) {
  if (options.verifyOnly) return verifyGeneralCollection(options);
  if (process.platform !== 'darwin' || process.arch !== 'arm64') throw Error('LOOMY_FINALIZER_REQUIRES_MACOS_ARM64');
  return finalizeGeneralExecution({ ...options, pythonExecutable: options.pythonExecutable || process.env.PYTHON || 'python3' },
    { processCleanup: { id: 'loomy-macos-task-processes', version: '0.1.0', harness: 'loomy', platform: 'darwin',
      run: (workspace, cleanupOptions) => terminateDarwinTaskProcesses(workspace, cleanupOptions) } });
}
export async function main(argv = process.argv.slice(2)) {
  const args = [...argv]; let pythonExecutable = null;
  const index = args.indexOf('--python');
  if (index >= 0) { pythonExecutable = args[index + 1]; if (!pythonExecutable || pythonExecutable.startsWith('--')) throw Error('--python 缺少值'); args.splice(index, 2); }
  const options = parseArgs(args);
  if (options.help) { console.log('Loomy General 正式收口\nnode drivers/loomy/finalize.mjs --unit-root ABS --state-file ABS --trace-index ABS --resource-metrics ABS --python PYTHON\n复验：--verify-only --unit-root ABS --task-id ID'); return; }
  console.log(JSON.stringify(await finalizeLoomyExecution({ ...options, pythonExecutable }), null, 2));
}
if (await isEntrypoint(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
