import test from 'node:test';
import assert from 'node:assert/strict';
import { bindSelectedCustomModel, verifyNativeCustomMapping, parseCustomTrigger, NEW_PROJECT_TASK_LABEL } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-custom-model.mjs';
import { readCurrentCustomModel, verifyNativeCustomBinding, sha256 } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-custom-model.mjs';
import { queryCustomModelConfigurations } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

const scope = 'a'.repeat(64);
const config = { config_id: 'synthetic-custom', display_name: 'Display', model: 'Configured',
  owner_scope_sha256: scope, lifecycle: 'active', has_credential: 1, reasoning_mode: 'explicit',
  default_reasoning: 'high', execution_revision: 3, protocol: 'chat_completions',
  last_test: { status: 'succeeded', httpStatus: 200, requestedReasoning: 'high', revision: 3 } };
const input = () => ({ trigger: { count: 1, text: 'Display\n自定义' }, configs: [structuredClone(config)], account_scope_sha256: scope, expected_reasoning: 'high' });
const mapping = () => bindSelectedCustomModel(input());
const evidence = () => ({ selection: { provider: 'acode', model: 'Configured', options: { reasoningEffort: 'high' }, customModel: { configId: 'synthetic-custom', executionRevision: 3 } },
  binding: { configId: 'synthetic-custom', revision: 3, model: 'Configured', effort: 'high', protocol: 'chat_completions', ownerScopeSha256: scope, kernelProviderId: 'astudio_custom_synthetic-custom_r3' },
  sdk_context: { model: `custom/${Buffer.from('synthetic-custom').toString('base64url')}/3/${Buffer.from('Configured').toString('base64url')}`, effort: 'high', cwd: '/synthetic/workspace', turn_id: 'synthetic-turn' },
  sdk_provider: 'astron_gateway', sdk_session_id: 'synthetic-session', sdk_session_cwd: '/synthetic/workspace',
  session_id: 'synthetic-session', turn_id: 'synthetic-turn', cwd: '/synthetic/workspace', thread_id: 'synthetic-thread' });

test('custom badge is not a reasoning setting', () => assert.equal(parseCustomTrigger(input().trigger).reasoning_from_ui, null));
test('explicit account-scoped mapping passes', () => assert.equal(mapping().configured_model_name, 'Configured'));
for (const [name, mutate, code] of [
  ['duplicate trigger', x => { x.trigger.count = 2; }, 'MODEL_TRIGGER_NOT_UNIQUE'],
  ['built-in display', x => { x.trigger.text = 'Display\nHigh'; }, 'NOT_EXACT_CUSTOM_TRIGGER'],
  ['wrong account', x => { x.account_scope_sha256 = 'b'.repeat(64); }, 'CUSTOM_CONFIG_NOT_UNIQUE_IN_ACCOUNT'],
  ['duplicate display in scope', x => { x.configs.push(structuredClone(config)); }, 'CUSTOM_CONFIG_NOT_UNIQUE_IN_ACCOUNT'],
  ['silent medium fallback', x => { x.configs[0].default_reasoning = 'medium'; }, 'CUSTOM_REASONING_NOT_HIGH'],
  ['stale connection revision', x => { x.configs[0].last_test.revision = 2; }, 'CUSTOM_HIGH_CONNECTION_NOT_PROVEN'],
  ['explicit high rejection', x => { x.configs[0].last_test.status = 'failed'; }, 'CUSTOM_HIGH_CONNECTION_NOT_PROVEN'],
]) test(name, () => { const x = input(); mutate(x); assert.throws(() => bindSelectedCustomModel(x), { message: code }); });
test('native selection binding and encoded SDK mapping agree', () => assert.equal(verifyNativeCustomMapping(mapping(), evidence()).native_mapping_verified, true));
for (const [name, mutate, code] of [
  ['wrong native config id', x => { x.selection.customModel.configId = 'other'; }, 'NATIVE_CUSTOM_REFERENCE_MISMATCH'],
  ['wrong native effort', x => { x.selection.options.reasoningEffort = 'medium'; }, 'NATIVE_REASONING_MISMATCH'],
  ['wrong binding account', x => { x.binding.ownerScopeSha256 = 'b'.repeat(64); }, 'NATIVE_BINDING_MISMATCH'],
  ['wrong SDK revision', x => { x.sdk_context.model = x.sdk_context.model.replace('/3/', '/4/'); }, 'SDK_MODEL_MAPPING_MISMATCH'],
  ['wrong SDK effort', x => { x.sdk_context.effort = 'medium'; }, 'SDK_REASONING_MISMATCH'],
  ['wrong SDK cwd', x => { x.sdk_context.cwd = '/other'; }, 'SDK_NATIVE_IDENTITY_MISMATCH'],
  ['wrong SDK session', x => { x.sdk_session_id = 'other'; }, 'SDK_NATIVE_IDENTITY_MISMATCH'],
  ['wrong SDK turn', x => { x.sdk_context.turn_id = 'other'; }, 'SDK_NATIVE_IDENTITY_MISMATCH'],
]) test(name, () => { const x = evidence(); mutate(x); assert.throws(() => verifyNativeCustomMapping(mapping(), x), { message: code }); });
test('task button excludes terminal task and ambiguous label', () => {
  assert.equal(NEW_PROJECT_TASK_LABEL.test('在 workspace 中新建任务'), true);
  assert.equal(NEW_PROJECT_TASK_LABEL.test('在 workspace 中新建终端任务'), false);
  assert.equal(NEW_PROJECT_TASK_LABEL.test('在 workspace 中新建对话'), true);
});

test('account metadata is used only as an identity hash and is not returned', async () => {
  const configs = [{ ...config, owner_scope_sha256: sha256('synthetic-owner') }];
  const result = await readCurrentCustomModel('/synthetic/state.sqlite', input().trigger, {
    readFile: async () => JSON.stringify({ accountId: 'synthetic-owner', token: 'SYNTHETIC_SECRET' }),
    queryConfigs: async () => configs,
  });
  assert.equal(result.account_scope_sha256, sha256('synthetic-owner'));
  assert.equal(JSON.stringify(result).includes('SYNTHETIC_SECRET'), false);
  await assert.rejects(readCurrentCustomModel('/synthetic/state.sqlite', input().trigger, {
    readFile: async () => JSON.stringify({ accountId: 'other' }), queryConfigs: async () => configs,
  }), /CUSTOM_CONFIG_NOT_UNIQUE_IN_ACCOUNT/u);
});

test('custom config snapshot returns whitelisted fields and validates stored owner/id', async () => {
  const root = await mkdtemp(join(tmpdir(), 'general-custom-config-'));
  const path = join(root, 'state.sqlite');
  const db = new DatabaseSync(path);
  try {
    db.exec('CREATE TABLE custom_model_configs(owner_scope TEXT, config_id TEXT, payload_json TEXT)');
    const record = { id: 'synthetic-custom', ownerScope: 'synthetic-owner', displayName: 'Display',
      model: 'Configured', protocol: 'chat_completions', defaultReasoning: 'high', reasoningMode: 'explicit',
      executionRevision: 3, lifecycle: 'active', credentialRef: 'SYNTHETIC_SECRET_REFERENCE',
      baseUrl: 'https://synthetic.invalid/?secret=SYNTHETIC_SECRET_URL',
      lastTest: { revision: 3, status: 'succeeded', httpStatus: 200, requestedReasoning: 'high' } };
    db.prepare('INSERT INTO custom_model_configs VALUES(?,?,?)').run('synthetic-owner', record.id, JSON.stringify(record));
    const rows = await queryCustomModelConfigurations(path);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].owner_scope_sha256, sha256('synthetic-owner'));
    assert.equal(JSON.stringify(rows).includes('SYNTHETIC_SECRET'), false);
    assert.equal(Object.hasOwn(rows[0], 'owner_scope'), false);
    record.ownerScope = 'other';
    db.prepare('UPDATE custom_model_configs SET payload_json=?').run(JSON.stringify(record));
    await assert.rejects(queryCustomModelConfigurations(path), /CUSTOM_CONFIG_STORED_IDENTITY_MISMATCH/u);
  } finally { db.close(); await rm(root, { recursive: true, force: true }); }
});

test('accepted native model binding is checked before managed dispatch releases its slot', () => {
  assert.equal(verifyNativeCustomBinding(mapping(), evidence()).native_binding_verified, true);
  const changed = evidence(); changed.binding.effort = 'medium';
  assert.throws(() => verifyNativeCustomBinding(mapping(), changed), /NATIVE_BINDING_MISMATCH/u);
});
