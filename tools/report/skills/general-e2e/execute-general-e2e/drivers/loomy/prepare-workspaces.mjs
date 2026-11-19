#!/usr/bin/env node
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { atomicJson, inside, lease } from '../../vendor/e2e-shared/loomy/execution.mjs';
import { artifact, assertArchivedFailuresIdle, assertIdle, assertNativeActivity, captureNative, currentOwnedRuntime, digest,
  isAbsentRuntime, isEntrypoint, jsonBytes, requireValue, runtimeStatus, SEND_GUARD_PROFILE, sha } from '../../vendor/e2e-shared/loomy/index.mjs';
import { newTask, selectWorkspace } from '../../vendor/e2e-shared/loomy/ui.mjs';

export async function main(argv = process.argv.slice(2)) {
  const { values: args } = parseArgs({ args: argv, options: { 'unit-root': { type: 'string' },
    'run-config': { type: 'string' }, 'output-dir': { type: 'string' }, help: { type: 'boolean' } } });
  if (args.help) {
    console.log('node prepare-workspaces.mjs --unit-root ABS --run-config ABS --output-dir NEW_DIR');
    console.log('逐题通过 Loomy 公开 UI 设置并回读完全访问，只使用空白主页，不输入或发送消息。');
    return;
  }
  requireValue(args['unit-root'] && args['run-config'] && args['output-dir'], 'WORKSPACE_PREPARATION_ARGUMENTS_REQUIRED');
  const unitRoot = await realpath(resolve(args['unit-root']));
  const output = resolve(args['output-dir']);
  const [configBytes, manifestBytes] = await Promise.all([readFile(args['run-config']), readFile(join(unitRoot, 'manifest.json'))]);
  const config = JSON.parse(configBytes), manifest = JSON.parse(manifestBytes);
  const { config_digest, ...payload } = config;
  requireValue(config_digest === digest(payload) && config.permission_policy === 'require-full-access'
    && config.configuration.permission_label === '完全访问' && config.send_guard_profile === SEND_GUARD_PROFILE,
  'WORKSPACE_PREPARATION_CONFIG_INVALID');
  requireValue(manifest.manifest_kind === 'execution' && manifest.unit?.harness?.id === 'loomy'
    && manifest.unit.model?.requested_id === config.configuration.model
    && manifest.unit.model?.reasoning_effort === config.configuration.reasoning_effort
    && manifest.task_ids.length > 0 && new Set(manifest.task_ids).size === manifest.task_ids.length,
  'WORKSPACE_PREPARATION_MANIFEST_INVALID');
  const targets = await Promise.all(manifest.task_ids.map(async taskId => {
    const matches = manifest.tasks.filter(row => row.task_id === taskId);
    requireValue(matches.length === 1 && matches[0].workspace.path === 'execution/tasks/' + taskId + '/workspace',
      'WORKSPACE_PREPARATION_TARGET_INVALID');
    return { task_id: taskId, workspace: await inside(unitRoot, matches[0].workspace.path) };
  }));
  requireValue(new Set(targets.map(row => row.workspace)).size === targets.length, 'WORKSPACE_PREPARATION_TARGET_DUPLICATE');
  const release = await lease(join(homedir(), '.local/state/wildclawbench/ui-locks/loomy-' + config.process.pid + '.lock'));
  try {
    await mkdir(output, { mode: 0o700 });
    const save = async (name, value) => {
      const bytes = jsonBytes(value);
      await writeFile(join(output, name), bytes, { flag: 'wx', mode: 0o600 });
      return artifact(name, bytes);
    };
    const idle = async () => {
      const runtime = await currentOwnedRuntime(config);
      const status = isAbsentRuntime(runtime) ? null : await runtimeStatus(runtime);
      if (status) assertIdle(status);
      await assertArchivedFailuresIdle(runtime, config.archived_http_failures);
      const native = await captureNative({ database: runtime.database, python: config.python });
      assertNativeActivity(native, [], config.archived_http_failures);
      return { native, runtime, status };
    };
    const before = await idle();
    const baseline = digest(before.native.session_index);
    const receipt = { profile: 'loomy-full-access-workspace-preparation/v1', status: 'RUNNING',
      started_at: new Date().toISOString(), unit_root: unitRoot, manifest_sha256: sha(manifestBytes),
      run_config_sha256: sha(configBytes), process: config.process, configuration: config.configuration,
      before: await save('baseline-before.json', before), tasks: [] };
    const receiptPath = join(output, 'receipt.json');
    await atomicJson(receiptPath, receipt);
    try {
      for (const [index, target] of targets.entries()) {
        const native = await captureNative({ database: config.runtime.database, python: config.python });
        assertNativeActivity(native, [], config.archived_http_failures);
        requireValue(digest(native.session_index) === baseline, 'WORKSPACE_PREPARATION_NATIVE_SESSION_CHANGED');
        const evidence = [];
        const saveUi = async (event, snapshot) => evidence.push({ event, ...await save(index + '-' + evidence.length + '-' + event + '.json', snapshot) });
        await newTask(config, saveUi);
        const selected = await selectWorkspace(config, target.workspace, saveUi, { provisionFullAccess: true });
        receipt.tasks.push({ ...target, selected, evidence });
        await atomicJson(receiptPath, receipt);
        console.log(JSON.stringify({ completed: receipt.tasks.length, total: targets.length, task_id: target.task_id, permission: selected.configuration.permission_label }));
      }
      const after = await idle();
      receipt.after = await save('baseline-after.json', after);
      requireValue(digest(after.native.session_index) === baseline, 'WORKSPACE_PREPARATION_NATIVE_SESSION_CHANGED');
      receipt.zero_native_sessions_created = true;
      receipt.prompt_sends = 0;
      receipt.status = 'PASS';
    } catch (error) {
      receipt.status = 'NEEDS_ATTENTION';
      receipt.error = error.message;
      throw error;
    } finally {
      receipt.finished_at = new Date().toISOString();
      await atomicJson(receiptPath, receipt);
    }
  } finally { await release(); }
}

if (await isEntrypoint(import.meta.url)) main().catch(error => { console.error(error.message); process.exitCode = 1; });
