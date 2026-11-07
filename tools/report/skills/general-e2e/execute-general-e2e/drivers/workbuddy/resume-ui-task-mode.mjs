#!/usr/bin/env node
// Continue one already observed refresh; never refresh, send or select a model.
import { createHash } from 'node:crypto';
import { lstat, open, readFile, realpath, unlink, writeFile } from 'node:fs/promises';
import { hostname } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveWorkBuddyBatchInvocation } from './batch.mjs';
import { assertWorkBuddyExecutionReadiness, assertWorkBuddyNativeIdle } from './execute.mjs';
import { inspectWorkBuddyMacos, parseArgs as parseProbeArgs } from './probe.mjs';
import { WorkBuddyCdpClient, createFreshWorkBuddyTask, discoverWorkBuddyMainTarget, readWorkBuddyUi } from './ui.mjs';

const hash = value => createHash('sha256').update(value).digest('hex');
const json = value => JSON.stringify(value, null, 2) + '\n';
const need = (value, code) => { if (!value) throw new Error('WORKBUDDY_TASK_MODE_RESUME_' + code); };
const absent = async path => { try { await lstat(path); return false; } catch (e) { if (e.code === 'ENOENT') return true; throw e; } };
async function plain(path) {
  need(await realpath(path) === resolve(path), 'SYMLINK');
  const before = await lstat(path); need(before.isFile() && !before.isSymbolicLink(), 'SOURCE_INVALID');
  const bytes = await readFile(path), after = await lstat(path);
  need(before.ino === after.ino && before.dev === after.dev && before.size === after.size && before.mtimeMs === after.mtimeMs, 'SOURCE_CHANGED');
  return { path, bytes, sha256: hash(bytes), size: bytes.length };
}
const sessionKeys = proof => JSON.stringify(proof.sessions.map(s => [s.conversation_id, s.cwd]).sort((a,b) => String(a).localeCompare(String(b))));
export function assertOriginalRefresh(original, invocationSha) {
  need(original.schema_version === 'wildclawbench.workbuddy-native-ui-recovery/v1'
    && original.status === 'NEEDS_ATTENTION'
    && original.error === 'WORKBUDDY_UI_RECOVERY_REFRESH_NOT_VERIFIED_DO_NOT_REPEAT'
    && original.invocation_sha256 === invocationSha && original.refresh_attempt_count === 1
    && original.refresh_returned?.clicked === true && original.prompt_send_count === 0
    && original.before_ui?.app_error_boundary === true
    && original.first_native_idle?.idle?.verified === true, 'ORIGINAL_REFRESH_NOT_PROVEN');
}
export function isTaskModeReady(ui, config) {
  return ui.app_error_boundary === false && ui.workspace_picker_count === 1 && ui.workspace_provider_count === 1
    && ui.editor_count === 1 && ui.editor_nonempty_count === 0 && ui.busy_control_count === 0
    && ui.selected_conversation_id === null && ui.model_count === 1 && ui.model === config.expectedModel
    && ui.permission_count === 1 && ui.permission === config.expectedPermission;
}
export function assertAssistantHomepage(ui, markers) {
  need(ui.app_error_boundary === false && ui.workspace_picker_count === 0 && ui.workspace_provider_count === 0
    && ui.workspace_path === null && ui.selected_conversation_id === null
    && ui.editor_count === 1 && ui.editor_nonempty_count === 0 && ui.busy_control_count === 0
    && ui.model_count === 1 && ui.model === '快速' && ui.permission_count === 1 && ui.permission === 'default-sandbox'
    && markers.assistant_home === true && markers.new_task_count === 1, 'NOT_REGISTERED_EMPTY_ASSISTANT_HOME');
}
async function inspectIdle(config) {
  const report = await inspectWorkBuddyMacos({ ...parseProbeArgs([]), appPath: config.appPath, sessionDb: config.sessionDb,
    extensionDataRoot: config.dataRoot, endpoint: config.endpoint, timeoutMs: 10000 });
  assertWorkBuddyExecutionReadiness(report, config.endpoint);
  const idle = assertWorkBuddyNativeIdle(report);
  need(report.application.version === '5.9.3' && report.application.version === config.manifest.unit.harness.version, 'VERSION_DRIFT');
  return { idle, application: { path: report.application.path, version: report.application.version },
    process: { pid: report.process.pid, started_at: report.process.started_at, command_sha256: hash(report.process.command) },
    sessions: report.native_sources.session_index.sessions };
}
async function assertDead(owner) {
  need(owner.host === hostname() && Number.isSafeInteger(owner.pid) && owner.pid > 0, 'OWNER_INVALID');
  try { process.kill(owner.pid, 0); } catch (e) { if (e.code === 'ESRCH') return; throw e; }
  throw new Error('WORKBUDDY_TASK_MODE_RESUME_OWNER_ACTIVE');
}
export async function resumeWorkBuddyTaskMode({ invocationPath, auditRoot, expectedOwnerPid, verifyOnly = false }, deps = {}) {
  const invocation = await plain(resolve(invocationPath));
  const cfg = await (deps.resolveInvocation || resolveWorkBuddyBatchInvocation)(JSON.parse(invocation.bytes).argv.slice(2));
  const config = cfg.configs[0], audit = resolve(auditRoot), rel = relative(cfg.root, audit);
  need(rel.startsWith('.general-e2e/ui-recoveries/') && !rel.split('/').includes('..') && await realpath(audit) === audit, 'AUDIT_OUTSIDE_UNIT');
  const originalRef = await plain(join(audit, 'recovery.json')), original = JSON.parse(originalRef.bytes);
  assertOriginalRefresh(original, invocation.sha256);
  const queueRef = await plain(join(cfg.root, '.general-e2e/queues/workbuddy', cfg.batch.queueId + '.json'));
  const queue = JSON.parse(queueRef.bytes), owner = queue.last_owner;
  need(original.owner_source === 'persisted-queue-owner' && original.owner_queue_sha256 === queueRef.sha256, 'ORIGINAL_QUEUE_DRIFT');
  need(owner?.pid === expectedOwnerPid && owner.queue_id === cfg.batch.queueId, 'OWNER_MISMATCH');
  await (deps.assertDead || assertDead)(owner);
  need(queue.phase === 'NEEDS_ATTENTION' && queue.tasks.every(t => !['RUNNING','DISPATCHING','NEEDS_ATTENTION'].includes(t.phase)), 'QUEUE_NOT_IDLE');
  need(await absent(join(cfg.root, '.general-e2e/queues/workbuddy/owner-lock.json')), 'QUEUE_OWNER_LOCK_EXISTS');
  for (const task of cfg.configs) need(await absent(task.lockFile), 'ATTEMPT_LOCK_EXISTS');
  const receiptPath = join(audit, 'task-mode-resume.json'), uiLockPath = join(cfg.root, '.general-e2e/workbuddy-ui.lock');
  let state = await absent(receiptPath) ? null : JSON.parse((await plain(receiptPath)).bytes);
  if (state) need(state.schema_version === 'wildclawbench.workbuddy-ui-task-mode-resume/v1'
    && state.source_original_refresh.sha256 === originalRef.sha256 && state.invocation_sha256 === invocation.sha256
    && state.original_queue_sha256 === queueRef.sha256 && [0,1].includes(state.new_task_navigation_count)
    && state.refresh_attempt_count === 1 && state.prompt_send_count === 0 && state.model_selection_actions === 0
    && state.permission_changes === 0 && state.operator_sha256 === hash(await readFile(fileURLToPath(import.meta.url))), 'RESUME_SOURCE_DRIFT');
  const nativeIdle = deps.inspectIdle || inspectIdle, readUi = deps.readUi || readWorkBuddyUi;
  const first = await nativeIdle(config);
  need(first.idle?.verified === true && JSON.stringify(first.process) === JSON.stringify(original.first_native_idle.process)
    && sessionKeys(first) === sessionKeys(original.first_native_idle), 'NATIVE_IDENTITY_OR_SESSION_DRIFT');
  const client = await (deps.connect || (async () => {
    const target = await discoverWorkBuddyMainTarget(config.endpoint, 10000);
    return WorkBuddyCdpClient.connect(target.webSocketDebuggerUrl, 10000);
  }))();
  let lock, lockStat;
  const save = () => writeFile(receiptPath, json(state), { mode: 0o600 });
  try {
    const before = await readUi(client);
    if (!isTaskModeReady(before, config)) {
      const markers = await (deps.readMarkers || (c => c.evaluate(`(() => {
        const visible = e => {const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none';};
        return {assistant_home:document.body.innerText.includes('本地助理'),new_task_count:[...document.querySelectorAll('button')].filter(e=>visible(e)&&/^(新建任务|New task)$/i.test((e.innerText||'').trim())).length};
      })()`)))(client);
      assertAssistantHomepage(before, markers);
    }
    if (verifyOnly) return { status: 'PASS_READ_ONLY_TASK_MODE_ADMISSION', navigation_needed: !isTaskModeReady(before, config),
      refresh_attempt_count: 1, prompt_send_count: 0, current_ui: before };
    if (state?.status === 'PASS_UI_RECOVERED_WITHOUT_PROMPT') {
      need(isTaskModeReady(before, config), 'COMPLETED_UI_CHANGED');
      return { status: state.status, receipt: receiptPath, prompt_send_count: 0,
        refresh_attempt_count: 1, new_task_navigation_count: state.new_task_navigation_count, idempotent: true };
    }
    lock = await open(uiLockPath, 'wx', 0o600); lockStat = await lock.stat();
    await lock.writeFile(json({ host: hostname(), pid: process.pid, type: 'resume-original-refresh-task-view', audit_root: audit }));
    const second = await nativeIdle(config);
    need(second.idle?.verified === true && JSON.stringify(second.process) === JSON.stringify(first.process)
      && sessionKeys(second) === sessionKeys(first), 'PRE_NAVIGATION_NATIVE_DRIFT');
    if (!state) {
      state = { schema_version: 'wildclawbench.workbuddy-ui-task-mode-resume/v1', status: 'PREFLIGHT',
        source_original_refresh: { path: originalRef.path, sha256: originalRef.sha256, size: originalRef.size },
        invocation_sha256: invocation.sha256, original_queue_sha256: queueRef.sha256,
        operator_sha256: hash(await readFile(fileURLToPath(import.meta.url))), first_native_idle: first, pre_navigation_native_idle: second,
        before_ui: before, refresh_attempt_count: 1, new_task_navigation_count: 0,
        model_selection_actions: 0, permission_changes: 0, prompt_send_count: 0 };
      await save();
    }
    if (!isTaskModeReady(before, config) && state.new_task_navigation_count === 0) {
      state.status = 'TASK_MODE_NAVIGATION_ARMED'; state.new_task_navigation_count = 1; await save();
      // The ordinary first-party entry changes view, not either model selector.
      await (deps.navigate || createFreshWorkBuddyTask)(client, 10000);
      state.status = 'OBSERVING_ORIGINAL_TASK_MODE_NAVIGATION'; await save();
    }
    const end = Date.now() + (deps.observationMs ?? 30000); let after = before;
    do {
      after = await readUi(client);
      if (isTaskModeReady(after, config)) break;
      await (deps.sleep || (ms => new Promise(r => setTimeout(r, ms))))(250);
    } while (Date.now() < end);
    state.after_ui = after;
    need(isTaskModeReady(after, config), 'TASK_VIEW_NOT_VERIFIED_DO_NOT_REPEAT');
    const final = await nativeIdle(config);
    need(final.idle?.verified === true && JSON.stringify(final.process) === JSON.stringify(first.process)
      && sessionKeys(final) === sessionKeys(first), 'FINAL_NATIVE_DRIFT');
    need((await plain(originalRef.path)).sha256 === originalRef.sha256 && (await plain(queueRef.path)).sha256 === queueRef.sha256, 'SOURCE_CHANGED');
    state.final_native_idle = final; state.status = 'PASS_UI_RECOVERED_WITHOUT_PROMPT';
    state.completed_at = new Date().toISOString(); await save();
    return { status: state.status, receipt: receiptPath, prompt_send_count: 0, refresh_attempt_count: 1,
      new_task_navigation_count: state.new_task_navigation_count, model_selection_actions: 0, permission_changes: 0 };
  } catch (e) {
    if (state && !verifyOnly) { state.status = 'NEEDS_ATTENTION'; state.error = String(e.message); await save(); }
    throw e;
  } finally {
    client.close();
    if (lock) { await lock.close(); const st = await lstat(uiLockPath).catch(() => null); if (st?.ino === lockStat.ino && st.dev === lockStat.dev) await unlink(uiLockPath); }
  }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), get = flag => args[args.indexOf(flag) + 1];
  need(['--invocation','--audit-root','--expected-owner-pid'].every(f => args.includes(f)), 'ARGUMENTS_REQUIRED');
  resumeWorkBuddyTaskMode({ invocationPath: get('--invocation'), auditRoot: get('--audit-root'),
    expectedOwnerPid: Number(get('--expected-owner-pid')), verifyOnly: args.includes('--verify-only') })
    .then(r => console.log(json(r))).catch(e => { console.error(e.message); process.exitCode = 1; });
}
