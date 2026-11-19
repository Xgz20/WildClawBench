#!/usr/bin/env node
import { isEntrypoint } from '../../vendor/e2e-shared/loomy/index.mjs';
import { resolve } from 'node:path';
import { join } from 'node:path';
import { readFile, access } from 'node:fs/promises';
import { assertArchivedFailuresIdle, assertNativeActivity, captureNative, currentOwnedRuntime, digest, sha } from '../../vendor/e2e-shared/loomy/index.mjs';
import { finalizeGeneralExecution, verifyGeneralCollection } from '../../scripts/finalize_general_execution.mjs';
import { parseArgs } from '../../scripts/lib/general-finalizer.mjs';
import { terminateDarwinTaskProcesses } from '../../scripts/lib/macos-task-processes.mjs';
import { verifyArchivedLoomy } from '../../vendor/e2e-shared/loomy/verification.mjs';

export async function finalizeLoomyExecution(options) {
  if (options.verifyOnly) return verifyGeneralCollection(options);
  if (process.platform !== 'darwin' || process.arch !== 'arm64') throw Error('LOOMY_FINALIZER_REQUIRES_MACOS_ARM64');
  const manifest = JSON.parse(await readFile(join(options.unitRoot, 'manifest.json'), 'utf8'));
  let database;
  let runConfig;
  const failedSessions = [];
  for (const task of manifest.tasks) {
    const state = JSON.parse(await readFile(join(options.unitRoot, 'execution/tasks', task.task_id, 'automation/loomy/automation-state.json'), 'utf8'));
    if (!['COMPLETED', 'FAILED'].includes(state.phase) || state.prompt.send_status !== 'sent'
      || state.send.dispatch_attempt_count !== 1) throw Error('LOOMY_ALL_EXECUTIONS_MUST_BE_TERMINAL_BEFORE_FINALIZE');
    const collected = join(options.unitRoot, '.general-e2e/collection/loomy', task.task_id, state.identity.attempt_id);
    for (const path of ['execution/automation-state.json', 'trace/trace-index.json', 'resource-metrics.json']) {
      await access(join(collected, path)).catch(() => { throw Error('LOOMY_ALL_NATIVE_COLLECTIONS_REQUIRED_BEFORE_FINALIZE'); });
    }
    const configBytes = await readFile(join(collected, 'trace/raw/frozen-run-config.json'));
    const journal = JSON.parse(await readFile(join(collected, 'trace/raw/dispatch-journal.json'), 'utf8'));
    const config = JSON.parse(configBytes);
    const { config_digest, ...payload } = config;
    if (config_digest !== digest(payload) || sha(configBytes) !== journal.input_locks.config
      || runConfig && runConfig.config_digest !== config_digest) throw Error('LOOMY_FINALIZER_RUN_CONFIG_MISMATCH');
    runConfig = config;
    if (state.phase === 'FAILED' && (state.extensions?.loomy?.native_http_failure || state.extensions?.loomy?.native_length_failure || state.extensions?.loomy?.native_terminal_failure)) {
      const index = JSON.parse(await readFile(join(collected, 'trace/trace-index.json'), 'utf8'));
      const frozen = JSON.parse(await readFile(join(collected, 'execution/automation-state.json'), 'utf8'));
      await verifyArchivedLoomy(index, frozen, join(collected, 'trace'));
      failedSessions.push({ session_id: state.session.session_id, final_message_id: state.extensions.loomy.final_message_id });
    }
    database = state.extensions.loomy.runtime.database;
  }
  const activity = await captureNative({ database, python: options.pythonExecutable || process.env.PYTHON || 'python3' });
  for (const row of failedSessions) {
    const native = activity.session_activity.find(item => item.session_id === row.session_id);
    if (native?.last_message_id !== row.final_message_id || native.pending_tool_count !== 0) throw Error('LOOMY_FAILED_HEAD_CHANGED');
  }
  assertNativeActivity(activity, failedSessions.map(row => row.session_id), runConfig?.archived_http_failures);
  if (runConfig?.archived_http_failures?.length) {
    const runtime = await currentOwnedRuntime(runConfig).catch(error => {
      if (error.message !== 'LOOMY_RUNTIME_NOT_RUNNING') throw error;
      return null;
    });
    if (runtime) await assertArchivedFailuresIdle(runtime, runConfig.archived_http_failures);
  }
  return finalizeGeneralExecution({ ...options, pythonExecutable: options.pythonExecutable || process.env.PYTHON || 'python3' },
    { processCleanup: { id: 'loomy-macos-task-processes', version: '0.1.1', harness: 'loomy', platform: 'darwin',
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
