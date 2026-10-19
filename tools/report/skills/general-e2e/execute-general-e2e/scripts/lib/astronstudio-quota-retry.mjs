import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const QUOTA_AUTH_SCHEMA = 'general-e2e.quota-retry-authorization/v1';
export const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const ensure = (condition, message) => { if (!condition) throw new Error(message); };
const readJson = async path => JSON.parse(await readFile(path, 'utf8'));

export function isQuotaError(error) {
  return ['ASTRONSTUDIO_TURN_ERROR', 'ASTRONSTUDIO_TURN_FAILED'].includes(error?.code)
    && typeof error?.message === 'string'
    && /^unexpected status 402(?: Payment Required)?: astron_points_exhausted(?:, url: \S+)?$/u.test(error.message)
    && !/[\r\n]/u.test(error.message);
}

export async function readQuotaAuthorization(path) {
  const bytes = await readFile(path), auth = JSON.parse(bytes.toString('utf8'));
  ensure(auth.schema_version === QUOTA_AUTH_SCHEMA, 'QUOTA_AUTHORIZATION_SCHEMA');
  ensure(auth.quota_restored === true && auth.retry_authorized === true, 'QUOTA_HUMAN_AUTHORIZATION_REQUIRED');
  for (const key of ['authorization_id', 'new_attempt_id', 'authorized_by', 'authorization_reference', 'authorized_at', 'reason', 'queue_id', 'batch_id', 'unit_id', 'task_id', 'old_attempt_id']) {
    ensure(typeof auth[key] === 'string' && auth[key].trim().length > 0, `QUOTA_AUTHORIZATION_FIELD:${key}`);
  }
  ensure(Number.isFinite(Date.parse(auth.authorized_at)), 'QUOTA_AUTHORIZATION_DATE');
  ensure(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u.test(auth.authorization_id), 'QUOTA_AUTHORIZATION_ID');
  ensure(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u.test(auth.queue_id)
    && /^[A-Za-z0-9][A-Za-z0-9._-]*$/u.test(auth.task_id), 'QUOTA_AUTHORIZATION_PATH_SCOPE');
  ensure(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u.test(auth.new_attempt_id)
    && auth.new_attempt_id !== auth.old_attempt_id, 'QUOTA_NEW_ATTEMPT_ID');
  for (const key of ['queue_digest', 'old_state_sha256', 'old_record_sha256', 'old_workspace_sha256', 'old_control_sha256', 'unit_manifest_sha256', 'run_config_digest']) {
    ensure(typeof auth[key] === 'string' && /^[0-9a-f]{64}$/u.test(auth[key]), `QUOTA_AUTHORIZATION_SHA:${key}`);
  }
  ensure(isAbsolute(auth.execution_package?.path || '') && /^[0-9a-f]{64}$/u.test(auth.execution_package?.sha256), 'QUOTA_EXECUTION_PACKAGE_REQUIRED');
  return { auth, bytes, sha256: digest(bytes) };
}

export function assertQuotaAuthorization(auth, { identity, configuration, taskId }) {
  for (const key of ['batch_id', 'unit_id', 'queue_id', 'queue_digest']) {
    ensure(auth[key] === identity[key], `QUOTA_AUTHORIZATION_IDENTITY:${key}`);
  }
  ensure(auth.task_id === taskId && configuration.manifest_sha256 === auth.unit_manifest_sha256
    && configuration.run_config_digest === auth.run_config_digest, 'QUOTA_AUTHORIZATION_SCOPE');
}

export function assertRetryableQuotaState(state, auth) {
  ensure(state?.identity?.attempt_id === auth.old_attempt_id && state.identity.task_id === auth.task_id
    && state.identity.batch_id === auth.batch_id && state.identity.unit_id === auth.unit_id, 'QUOTA_OLD_IDENTITY');
  ensure(state.phase === 'FAILED' && state.execution?.business_status === 'candidate_error'
    && isQuotaError(state.execution?.error), 'QUOTA_FAILURE_NOT_RETRYABLE');
  ensure(state.prompt?.send_status === 'sent' && state.send?.dispatch_attempt_count === 1
    && state.session?.verified === true && state.session.thread_id && state.session.turn_id && state.session.session_id,
  'QUOTA_NATIVE_TERMINAL_REQUIRED');
  ensure(state.run_config?.config_digest === auth.run_config_digest, 'QUOTA_RUN_CONFIG_DRIFT');
}

export function pristineUnsentAttempt(state) {
  return state?.phase === 'PENDING' && state.prompt?.send_status === 'not_sent' && state.prompt?.sent_at === null
    && state.send?.dispatch_attempt_count === 0 && !state.send.dispatch_armed_at && !state.send.dispatch_completed_at
    && state.session?.verified === false && !state.session.thread_id && !state.session.turn_id && !state.session.session_id
    && !state.history?.some(row => row.event === 'PROMPT_DISPATCH_ARMED' || row.event === 'PROMPT_DISPATCH_RETURNED');
}

export async function recoveryFiles(unitRoot, authorization, verifyOnly = false, verifyPristine = false, validateOnly = false) {
  const python = process.env.GENERAL_E2E_PYTHON || 'python3';
  const args = ['-X', 'utf8', fileURLToPath(new URL('../prepare_quota_retry.py', import.meta.url)), '--unit-root', unitRoot,
    '--authorization', authorization.path, '--authorization-sha256', authorization.sha256];
  if (verifyOnly) args.push('--verify-receipt');
  if (verifyPristine) args.push('--verify-pristine');
  if (validateOnly) args.push('--validate-only');
  const result = await new Promise((resolvePromise, reject) => {
    const child = spawn(python, args, { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
    let stdout = '', stderr = '';
    child.stdout.setEncoding('utf8').on('data', value => { stdout += value; });
    child.stderr.setEncoding('utf8').on('data', value => { stderr += value; });
    child.once('error', reject);
    child.once('exit', code => resolvePromise({ code, stdout, stderr }));
  });
  ensure(result.code === 0, `QUOTA_RECOVERY_FILES_FAILED: ${result.stderr.slice(-2000)}`);
  return JSON.parse(result.stdout);
}

export async function quotaContext(config, existing) {
  const authorization = await readQuotaAuthorization(config.quotaRetryAuthorization);
  authorization.path = config.quotaRetryAuthorization;
  const { auth } = authorization;
  const queueRoot = join(config.unitRoot, '.general-e2e/queues', auth.queue_id);
  const queue = await readJson(join(queueRoot, 'queue-state.json'));
  assertQuotaAuthorization(auth, { identity: queue.identity, configuration: queue.configuration, taskId: config.task.task_id });
  ensure(digest(await readFile(config.manifestPath)) === auth.unit_manifest_sha256
    && config.runConfig.config_digest === auth.run_config_digest, 'QUOTA_CONFIG_DRIFT');
  const row = queue.tasks.find(task => task.task_id === auth.task_id);
  const transaction = row?.quota_recoveries?.find(item => item.authorization_sha256 === authorization.sha256);
  ensure(transaction?.old_attempt_id === auth.old_attempt_id && transaction.new_attempt_id === auth.new_attempt_id, 'QUOTA_QUEUE_INTENT_REQUIRED');
  ensure(existing && [auth.old_attempt_id, auth.new_attempt_id].includes(existing.identity?.attempt_id), 'QUOTA_EXISTING_ATTEMPT_REQUIRED');
  ensure([auth.old_attempt_id, auth.new_attempt_id].includes(row.selected_attempt_id)
    && (existing.identity.attempt_id !== auth.old_attempt_id || row.selected_attempt_id === auth.old_attempt_id),
  'QUOTA_SELECTED_ATTEMPT_DRIFT');
  let old = existing, receipt = null;
  if (existing.identity.attempt_id === auth.new_attempt_id) {
    receipt = await recoveryFiles(config.unitRoot, authorization, true);
    old = await readJson(join(config.unitRoot, receipt.old_state_archive));
  } else {
    ensure(digest(await readFile(config.stateFile)) === auth.old_state_sha256, 'QUOTA_OLD_STATE_SHA');
    ensure(digest(await readFile(config.recordFile)) === auth.old_record_sha256, 'QUOTA_OLD_RECORD_SHA');
  }
  assertRetryableQuotaState(old, auth);
  return { authorization, old, receipt };
}

export function assertNativeQuotaTerminal(sessions, old, workspace, isActive) {
  ensure(!sessions.some(isActive), 'QUOTA_RECOVERY_REQUIRES_NATIVE_IDLE');
  const matched = sessions.filter(row => row.thread_id === old.session.thread_id && row.turn_id === old.session.turn_id
    && row.session_id === old.session.session_id && resolve(String(row.cwd || '')) === resolve(workspace)
    && row.latest_turn_id === old.session.turn_id && ['error', 'failed'].includes(String(row.turn_state || row.status).toLowerCase()));
  ensure(matched.length === 1, 'QUOTA_NATIVE_FAILURE_NOT_UNIQUELY_BOUND');
  const known = [...(old.session.baseline || []), old.session];
  const unexpected = sessions.filter(row => resolve(String(row.cwd || '')) === resolve(workspace)
    && row.turn_id && row.session_id && !known.some(previous => previous.thread_id === row.thread_id
      && previous.turn_id === row.turn_id && previous.session_id === row.session_id));
  ensure(!unexpected.length, 'QUOTA_UNREGISTERED_NATIVE_TURN: inspect existing native acceptance before any retry');
}
