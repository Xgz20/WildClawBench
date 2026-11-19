#!/usr/bin/env node
// Explicit recovery of a known, deliberately stopped controller; never deletes locks.
import { readFile, writeFile, mkdir, lstat, realpath, rename, readdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { hostname } from 'node:os';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { assertArchivedFailuresIdle, assertIdle, assertNativeActivity, captureNative, command, currentOwnedRuntime,
  digest, isEntrypoint, jsonBytes, requireValue, runtimeStatus, sha } from '../../vendor/e2e-shared/loomy/index.mjs';

export async function main(argv = process.argv.slice(2)) {
  const { values: args } = parseArgs({ args: argv, options: {
    'unit-root': { type: 'string' }, 'run-config': { type: 'string' }, 'stop-receipt': { type: 'string' },
    'stop-receipt-sha256': { type: 'string' }, output: { type: 'string' }, help: { type: 'boolean' },
  } });
  if (args.help) { console.log('Explicit known-controller lock archival after a verified stop; no send, no native process signal.\n--unit-root ABS --run-config ABS --stop-receipt ABS --stop-receipt-sha256 SHA --output NEW.json'); return; }
  const unit = await realpath(resolve(args['unit-root']));
  const bytes = await readFile(args['stop-receipt']);
  requireValue(sha(bytes) === args['stop-receipt-sha256'], 'CONTROLLER_STOP_RECEIPT_SHA');
  const stop = JSON.parse(bytes);
  requireValue(stop.profile === 'loomy-explicit-owned-controller-stop/v1' && stop.controller_exited === true
    && stop.no_task_owner_locks === true && stop.no_dispatching_rows === true && stop.native_processes_signalled === false
    && stop.locks_removed === false && stop.pid === stop.owner?.pid && stop.owner.host === hostname(), 'CONTROLLER_STOP_INVALID');
  const absent = async () => {
    let result;
    try { result = await promisify(execFile)('/bin/ps', ['-p', String(stop.pid), '-o', 'pid=,lstart=,command=']); }
    catch (error) { if (error.code === 1 && !error.stdout?.trim() && !error.stderr?.trim()) return; throw error; }
    requireValue(!result.stdout.trim(), 'CONTROLLER_OWNER_STILL_EXISTS');
  };
  await absent();
  const sources = new Map();
  for (const row of stop.sources) {
    const path = resolve(row.path);
    requireValue(path.startsWith(unit + '/') && await realpath(path) === path
      && (await lstat(path)).isFile(), 'CONTROLLER_STOP_SOURCE_PATH');
    const data = await readFile(path);
    requireValue(sha(data) === row.sha256 && data.length === row.size, 'CONTROLLER_STOP_SOURCE_CHANGED');
    sources.set(path, data);
  }
  const ownerPaths = [...sources.keys()].filter(path => path.endsWith('/owner.lock'));
  requireValue(ownerPaths.length === 1 && ownerPaths[0].startsWith(join(unit, 'control/loomy-queues') + '/'), 'CONTROLLER_OWNER_SCOPE');
  const ownerPath = ownerPaths[0], queuePath = join(resolve(ownerPath, '..'), 'queue.json');
  requireValue(sources.has(queuePath), 'CONTROLLER_QUEUE_SOURCE_REQUIRED');
  const queue = JSON.parse(sources.get(queuePath));
  const zeroSendTask = stop.zero_send_task_id ?? null;
  const paused = queue.tasks.filter(row => row.phase === 'NEEDS_ATTENTION');
  requireValue(queue.tasks.every(row => ['PENDING', 'RUNNING', 'COMPLETED', 'FAILED'].includes(row.phase)
      || row.phase === 'NEEDS_ATTENTION' && row.task_id === zeroSendTask)
    && (zeroSendTask === null ? paused.length === 0 : paused.length === 1 && queue.phase === 'NEEDS_ATTENTION'),
  'CONTROLLER_QUEUE_UNSAFE');
  const configBytes = await readFile(args['run-config']), config = JSON.parse(configBytes);
  const manifestBytes = sources.get(join(unit, 'manifest.json'));
  requireValue(manifestBytes && sha(manifestBytes) === queue.input.manifest_sha256
    && sha(configBytes) === queue.input.config_sha256
    && JSON.stringify(queue.tasks.map(row => row.task_id)) === JSON.stringify(JSON.parse(manifestBytes).task_ids), 'CONTROLLER_FROZEN_INPUT_CHANGED');
  const allowed = queue.tasks.filter(row => row.session_id).map(row => row.session_id);
  for (const row of queue.tasks) {
    const directory = join(unit, 'execution/tasks', row.task_id, 'automation/loomy');
    try { requireValue(!(await readdir(directory)).includes('owner.lock'), 'CONTROLLER_TASK_OWNER_EXISTS'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (row.state_file) {
      requireValue(sources.has(row.state_file), 'CONTROLLER_TASK_STATE_NOT_FROZEN');
      const state = JSON.parse(sources.get(row.state_file));
      if (row.task_id === zeroSendTask) {
        const journalPath = join(directory, 'dispatch-journal.json');
        requireValue(sources.has(journalPath), 'CONTROLLER_ZERO_SEND_JOURNAL_NOT_FROZEN');
        const journal = JSON.parse(sources.get(journalPath));
        requireValue(row.phase === 'NEEDS_ATTENTION' && row.dispatch_attempt_count === 0 && row.session_id === null
          && state.phase === 'NEEDS_ATTENTION' && state.send.dispatch_attempt_count === 0 && state.prompt.send_status === 'not_sent'
          && !state.session.verified && !state.session.session_id && state.identity.attempt_id === row.attempt_id
          && digest(journal.identity) === digest(state.identity) && journal.phase === 'NEEDS_ATTENTION'
          && journal.dispatch_attempt_count === 0 && journal.send_status === 'not_sent' && !journal.sent_at && !journal.session
          && journal.attention === 'LOOMY_UI_TIMEOUT:workspace-menu'
          && JSON.stringify(journal.history.map(item => item.event)) === JSON.stringify(['before-new-task', 'new-task']),
        'CONTROLLER_ZERO_SEND_TASK_IDENTITY');
      } else {
        requireValue(state.send.dispatch_attempt_count === 1 && state.prompt.send_status === 'sent'
          && state.session.verified && state.session.session_id === row.session_id, 'CONTROLLER_TASK_IDENTITY');
      }
    } else requireValue(row.phase === 'PENDING' && !row.attempt_id && !row.session_id, 'CONTROLLER_UNBOUND_ATTEMPT');
  }
  const runtime = await currentOwnedRuntime(config);
  const native = await captureNative({ database: runtime.database, python: config.python });
  assertNativeActivity(native, allowed, config.archived_http_failures);
  if (zeroSendTask !== null) {
    const directory = join(unit, 'execution/tasks', zeroSendTask, 'automation/loomy');
    const journal = JSON.parse(sources.get(join(directory, 'dispatch-journal.json')));
    const workspace = join(unit, 'execution/tasks', zeroSendTask, 'workspace');
    requireValue(native.session_index.filter(row => row.directory === workspace)
      .every(row => journal.baseline.includes(row.id)), 'CONTROLLER_ZERO_SEND_NEW_SESSION_EXISTS');
  }

  assertIdle(await runtimeStatus(runtime), allowed);
  await assertArchivedFailuresIdle(runtime, config.archived_http_failures);
  await absent();
  requireValue((await readFile(ownerPath)).equals(sources.get(ownerPath)), 'CONTROLLER_OWNER_CHANGED');
  const archive = join(unit, '.general-e2e/controller-recoveries', sha(bytes));
  await mkdir(join(unit, '.general-e2e/controller-recoveries'), { recursive: true });
  await mkdir(archive, { recursive: false });
  await writeFile(join(archive, 'stop-receipt.json'), bytes, { flag: 'wx', mode: 0o600 });
  await writeFile(join(archive, 'native-activity.json'), jsonBytes({ runtime, native }), { flag: 'wx', mode: 0o600 });
  await rename(ownerPath, join(archive, 'original-owner.lock'));
  const receipt = { status: 'ARCHIVED_VERIFIED_OWNED_CONTROLLER_LOCK', profile: 'loomy-controller-lock-recovery/v1',
    recovered_at: new Date().toISOString(), original_owner: stop.owner, original_owner_sha256: sha(sources.get(ownerPath)),
    stop_receipt_sha256: sha(bytes), archive, prompt_dispatches: 0, native_processes_signalled: false,
    queue_sha256: sha(sources.get(queuePath)), original_owner_preserved: true };
  await writeFile(args.output, jsonBytes(receipt), { flag: 'wx', mode: 0o600 });
  console.log(JSON.stringify(receipt));
}
if (await isEntrypoint(import.meta.url)) main().catch(error => { console.error(error.message); process.exitCode = 1; });
