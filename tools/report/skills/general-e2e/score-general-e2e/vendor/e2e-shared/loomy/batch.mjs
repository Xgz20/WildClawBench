import { mkdir, readFile, realpath } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { captureNative, digest, requireValue, SEND_GUARD_PROFILE, sha, verifyBinding } from './index.mjs';
import { atomicJson, executeTask, inside, lease, loadTask } from './execution.mjs';

import { assertConfiguration, registeredWorkspaceItems } from './ui.mjs';
import { requireFullAccess } from '../desktop-gui/formal-permission.mjs';

async function preparationDigest(receiptPath, unitRoot, manifestBytes, manifest, config) {
  requireValue(typeof receiptPath === 'string', 'QUEUE_WORKSPACE_PREPARATION_REQUIRED');
  const path = await realpath(resolve(receiptPath));
  const bytes = await readFile(path), receipt = JSON.parse(bytes);
  requireValue(receipt.profile === 'loomy-full-access-workspace-preparation/v1' && receipt.status === 'PASS'
    && receipt.prompt_sends === 0 && receipt.zero_native_sessions_created === true
    && receipt.unit_root === unitRoot && receipt.manifest_sha256 === sha(manifestBytes)
    && digest(receipt.process) === digest(config.process) && digest(receipt.configuration) === digest(config.configuration)
    && digest(receipt.tasks.map(row => row.task_id)) === digest(manifest.task_ids), 'QUEUE_WORKSPACE_PREPARATION_INVALID');
  const evidence = async row => {
    const data = await readFile(await inside(dirname(path), row.path));
    requireValue(row.size === data.length && row.sha256 === sha(data), 'QUEUE_WORKSPACE_PREPARATION_EVIDENCE_CHANGED');
    return JSON.parse(data);
  };
  const [before, after] = await Promise.all([evidence(receipt.before), evidence(receipt.after)]);
  requireValue(digest(before.native.session_index) === digest(after.native.session_index), 'QUEUE_WORKSPACE_PREPARATION_SESSION_CHANGED');
  for (const row of receipt.tasks) {
    const workspace = await inside(unitRoot, manifest.tasks.find(task => task.task_id === row.task_id).workspace.path);
    const checks = new Map();
    for (const artifact of row.evidence) checks.set(artifact.event, await evidence(artifact));
    const selected = checks.get('workspace-selected'), menu = checks.get('workspace-full-path-readback');
    requireValue(row.workspace === workspace && row.selected.workspace === workspace && row.selected.full_path_verified
      && registeredWorkspaceItems(menu, workspace).length === 1 && selected.pid === config.process.pid
      && assertConfiguration(selected, config).composer.value === ''
      && digest(row.selected.full_access_gate) === digest(requireFullAccess('loomy', '完全访问', 'workspace-selected')),
    'QUEUE_WORKSPACE_PREPARATION_TASK_INVALID');
  }
  return sha(bytes);
}

export async function runBatch(options, overrides = {}) {
  const performTask = overrides.executeTask || executeTask;
  const unitRoot = await realpath(resolve(options.unitRoot));
  requireValue(/^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/u.test(options.queueId || ''), 'QUEUE_ID_INVALID');
  const slots = options.runSlots ?? 1;
  requireValue(Number.isInteger(slots) && slots >= 1 && slots <= 3, 'RUN_SLOTS_INVALID');
  const manifestBytes = await readFile(join(unitRoot, 'manifest.json'));
  const configBytes = await readFile(options.runConfig);
  const manifest = JSON.parse(manifestBytes), config = JSON.parse(configBytes);
  const input = { manifest_sha256: sha(manifestBytes), config_sha256: sha(configBytes), task_ids: manifest.task_ids,
    run_slots: slots, continue_on_terminal_failure: options.continueOnTerminalFailure === true };
  requireValue(manifest.unit?.harness?.id === 'loomy' && slots <= config.execution_concurrency, 'QUEUE_HARNESS_OR_CAPACITY_INVALID');
  if (config.send_guard_profile === SEND_GUARD_PROFILE) {
    input.workspace_preparation_sha256 = await preparationDigest(options.workspacePreparation, unitRoot, manifestBytes, manifest, config);
  }
  const root = join(unitRoot, 'control/loomy-queues', options.queueId);
  await mkdir(root, { recursive: true, mode: 0o700 });
  const path = join(root, 'queue.json'), release = await lease(join(root, 'owner.lock'));
  let queue;
  try {
    try { queue = JSON.parse(await readFile(path, 'utf8')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (queue) {
      requireValue(options.resume === true && queue.input_digest === digest(input), 'QUEUE_FROZEN_INPUT_CHANGED_OR_RESUME_REQUIRED');
    } else {
      requireValue(!options.resume, 'QUEUE_RESUME_WITHOUT_STATE');
      queue = { schema_version: 'wildclawbench.general-e2e-loomy-queue/v1', queue_id: options.queueId,
        input, input_digest: digest(input), phase: 'RUNNING', created_at: new Date().toISOString(), history: [],
        tasks: manifest.task_ids.map(task_id => ({ task_id, phase: 'PENDING', attempt_id: null, session_id: null, state_file: null })) };
      await atomicJson(path, queue);
    }
    const update = async (row, result) => {
      const state = result.state;
      requireValue(!row.attempt_id || row.attempt_id === state.identity.attempt_id, 'QUEUE_ATTEMPT_REPLACED');
      row.attempt_id = state.identity.attempt_id; row.session_id = state.session.session_id;
      row.dispatch_attempt_count = state.send.dispatch_attempt_count;
      row.phase = state.phase; row.state_file = result.state_file;
      queue.history.push({ at: new Date().toISOString(), task_id: row.task_id, phase: row.phase, attempt_id: row.attempt_id });
      await atomicJson(path, queue);
    };
    const recordFailure = async (row, error) => {
      const context = await loadTask({ ...options, unitRoot, taskId: row.task_id });
      try {
        const journal = JSON.parse(await readFile(context.journalPath, 'utf8'));
        requireValue(digest(journal.input_locks) === digest(context.locks)
          && journal.identity.task_id === row.task_id, 'QUEUE_FAILED_ATTEMPT_BINDING_CHANGED');
        row.attempt_id = journal.identity.attempt_id; row.session_id = journal.session?.id ?? null;
        row.dispatch_attempt_count = journal.dispatch_attempt_count; row.state_file = context.statePath;
      } catch (failure) { if (failure.code !== 'ENOENT') throw failure; }
      row.phase = 'NEEDS_ATTENTION'; row.error ??= error.message;
      row.error_history = [...(row.error_history || []), { at: new Date().toISOString(), message: error.message }];
      await atomicJson(path, queue);
    };
    const allowed = async () => {
      const ids = [];
      for (const row of queue.tasks.filter(item => item.session_id)) {
        const context = await loadTask({ ...options, unitRoot, taskId: row.task_id });
        const journal = JSON.parse(await readFile(context.journalPath, 'utf8'));
        requireValue(journal.identity.attempt_id === row.attempt_id && journal.session?.id === row.session_id
          && digest(journal.input_locks) === digest(context.locks), 'QUEUE_SESSION_BINDING_CHANGED');
        const native = await captureNative({ database: config.runtime.database, sessionId: row.session_id, python: config.python });
        ids.push(...verifyBinding(native, { workspace: context.workspace, prompt: context.prompt,
          baseline: journal.baseline, sessionId: row.session_id }).session_ids);
      }
      return ids;
    };
    do {
      for (const row of queue.tasks.filter(item => ['RUNNING', 'DISPATCHING', 'NEEDS_ATTENTION'].includes(item.phase))) {
        const retryPreparation = row.dispatch_attempt_count === 0 && options.retryPreSendTaskIds?.includes(row.task_id);
        if (row.phase === 'NEEDS_ATTENTION' && row.dispatch_attempt_count !== 1 && !retryPreparation) continue;
        requireValue(row.state_file || row.phase !== 'DISPATCHING', 'QUEUE_DISPATCH_RESULT_UNKNOWN');
        try {
          await update(row, await performTask({ ...options, unitRoot, taskId: row.task_id,
            resume: true, observeOnce: !retryPreparation, detachAfterSubmit: retryPreparation,
            retryPreSendFailure: retryPreparation, allowedSessionIds: await allowed() }));
        } catch (error) { await recordFailure(row, error); }
      }
      if (queue.tasks.every(row => ['COMPLETED', 'FAILED'].includes(row.phase))) {
        queue.phase = 'COMPLETED'; queue.finished_at = new Date().toISOString(); await atomicJson(path, queue); return queue;
      }
      const attention = queue.tasks.some(row => row.phase === 'NEEDS_ATTENTION');
      const failed = queue.tasks.some(row => row.phase === 'FAILED') && !input.continue_on_terminal_failure;
      const active = queue.tasks.filter(row => row.phase === 'RUNNING').length;
      const next = queue.tasks.find(row => row.phase === 'PENDING');
      if (!attention && !failed && next && active < slots) {
        next.phase = 'DISPATCHING'; await atomicJson(path, queue);
        try {
          await update(next, await performTask({ ...options, unitRoot, taskId: next.task_id,
            resume: false, detachAfterSubmit: true, observeOnce: false, allowedSessionIds: await allowed() }));
        } catch (error) {
          await recordFailure(next, error);
        }
        continue;
      }
      if ((attention || failed) && active === 0) {
        queue.phase = 'NEEDS_ATTENTION'; await atomicJson(path, queue); return queue;
      }
      await delay(options.pollIntervalMs || 1000);
    } while (true);
  } finally { await release(); }
}
