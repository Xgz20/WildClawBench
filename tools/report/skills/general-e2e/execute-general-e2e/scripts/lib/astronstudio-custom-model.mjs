// Account-scoped, read-only custom model identity gates.
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { queryCustomModelConfigurations } from './astronstudio-state.mjs';

export const sha256 = (text) => createHash('sha256').update(String(text)).digest('hex');
export const CURRENT_MODEL_SELECTOR = 'button[aria-label="切换模型和推理设置"], button[aria-label="Change model and reasoning"], button[aria-label="切换模型"], button[aria-label="Change model"]';
export const NEW_PROJECT_TASK_LABEL = /^(?:在 .+ 中新建(?:对话|任务)|New chat in .+|New task in .+)$/u;

function requireValue(ok, code) {
  if (!ok) throw new Error(code);
}

export function parseCustomTrigger({ count, text }) {
  requireValue(count === 1, 'MODEL_TRIGGER_NOT_UNIQUE');
  const lines = String(text || '').split(/\r?\n/u).map(s => s.trim()).filter(Boolean);
  // The second line is a custom badge, never a reasoning effort.
  requireValue(lines.length === 2 && ['自定义', 'Custom'].includes(lines[1]), 'NOT_EXACT_CUSTOM_TRIGGER');
  return { display_name: lines[0], kind: 'custom', reasoning_from_ui: null };
}

export function bindSelectedCustomModel({ trigger, configs, account_scope_sha256, expected_reasoning = null }) {
  const selected = parseCustomTrigger(trigger);
  requireValue(/^[a-f0-9]{64}$/u.test(account_scope_sha256), 'ACCOUNT_SCOPE_UNKNOWN');
  const matches = configs.filter(c => c.display_name === selected.display_name
    && c.owner_scope_sha256 === account_scope_sha256);
  requireValue(matches.length === 1, 'CUSTOM_CONFIG_NOT_UNIQUE_IN_ACCOUNT');
  const c = matches[0];
  requireValue(c.lifecycle === 'active' && c.has_credential === 1, 'CUSTOM_CONFIG_NOT_READY');
  requireValue(c.reasoning_mode === 'explicit' && ['low', 'medium', 'high', 'xhigh', 'max'].includes(c.default_reasoning), 'CUSTOM_REASONING_NOT_EXPLICIT');
  if (expected_reasoning !== null) requireValue(c.default_reasoning === expected_reasoning, 'CUSTOM_REASONING_NOT_HIGH');
  requireValue(Number.isInteger(c.execution_revision) && c.execution_revision > 0, 'CUSTOM_REVISION_UNKNOWN');
  requireValue(['chat_completions', 'responses'].includes(c.protocol), 'CUSTOM_PROTOCOL_UNKNOWN');
  requireValue(typeof c.model === 'string' && c.model.length > 0, 'CUSTOM_MODEL_UNKNOWN');
  requireValue(c.last_test?.status === 'succeeded' && c.last_test?.httpStatus === 200
    && c.last_test?.requestedReasoning === c.default_reasoning
    && c.last_test?.revision === c.execution_revision, 'CUSTOM_HIGH_CONNECTION_NOT_PROVEN');
  return {
    display_name: selected.display_name,
    configured_model_name: c.model,
    config_id: c.config_id,
    execution_revision: c.execution_revision,
    account_scope_sha256,
    protocol: c.protocol,
    reasoning_effort: c.default_reasoning,
    verification: 'cdp-visible-selection+account-scoped-custom-config',
    reasoning_source: 'account-scoped-custom-config.explicit-defaultReasoning',
    connection_requested_reasoning_accepted: true,
    server_reasoning_behavior_verified: false,
  };
}

function strictDecode(value) {
  requireValue(typeof value === 'string' && /^[A-Za-z0-9_-]+$/u.test(value), 'INVALID_CUSTOM_SDK_ENCODING');
  const result = Buffer.from(value, 'base64url').toString('utf8');
  requireValue(Buffer.from(result, 'utf8').toString('base64url') === value, 'INVALID_CUSTOM_SDK_ENCODING');
  return result;
}

export async function readCurrentCustomModel(stateDatabase, trigger, overrides = {}) {
  const bytes = await (overrides.readFile || readFile)(join(dirname(stateDatabase), 'astron-session.json'), 'utf8');
  const accountId = JSON.parse(bytes)?.accountId;
  requireValue(typeof accountId === 'string' && accountId.trim().length > 0, 'ACCOUNT_SCOPE_UNKNOWN');
  const configs = await (overrides.queryConfigs || queryCustomModelConfigurations)(stateDatabase);
  return bindSelectedCustomModel({ trigger, configs, account_scope_sha256: sha256(accountId.trim()) });
}

export function verifyNativeCustomBinding(mapping, { selection, binding }) {
  requireValue(selection?.provider === 'acode' && selection.model === mapping.configured_model_name,
    'NATIVE_PROVIDER_MODEL_MISMATCH');
  requireValue(selection.customModel?.configId === mapping.config_id
    && selection.customModel?.executionRevision === mapping.execution_revision, 'NATIVE_CUSTOM_REFERENCE_MISMATCH');
  requireValue(selection.options?.reasoningEffort === mapping.reasoning_effort, 'NATIVE_REASONING_MISMATCH');
  const expectedKernel = `astudio_custom_${mapping.config_id.replace(/[^a-zA-Z0-9_-]/gu, '_')}_r${mapping.execution_revision}`;
  requireValue(binding?.configId === mapping.config_id && binding.revision === mapping.execution_revision
    && binding.model === mapping.configured_model_name && binding.effort === mapping.reasoning_effort
    && binding.protocol === mapping.protocol && binding.ownerScopeSha256 === mapping.account_scope_sha256
    && binding.kernelProviderId === expectedKernel, 'NATIVE_BINDING_MISMATCH');
  return { ...mapping, native_provider: selection.provider, kernel_provider_id: expectedKernel,
    native_binding_verified: true };
}

export function verifyNativeCustomMapping(mapping, { selection, binding, sdk_context, sdk_provider, sdk_session_id, sdk_session_cwd, session_id, turn_id, cwd, thread_id }) {
  requireValue(selection?.provider === 'acode' && selection.model === mapping.configured_model_name,
    'NATIVE_PROVIDER_MODEL_MISMATCH');
  requireValue(selection.customModel?.configId === mapping.config_id
    && selection.customModel?.executionRevision === mapping.execution_revision, 'NATIVE_CUSTOM_REFERENCE_MISMATCH');
  requireValue(selection.options?.reasoningEffort === mapping.reasoning_effort, 'NATIVE_REASONING_MISMATCH');
  requireValue(binding?.configId === mapping.config_id && binding.revision === mapping.execution_revision
    && binding.model === mapping.configured_model_name && binding.effort === mapping.reasoning_effort
    && binding.protocol === mapping.protocol && binding.ownerScopeSha256 === mapping.account_scope_sha256,
  'NATIVE_BINDING_MISMATCH');
  const expectedKernel = `astudio_custom_${mapping.config_id.replace(/[^a-zA-Z0-9_-]/gu, '_')}_r${mapping.execution_revision}`;
  requireValue(binding.kernelProviderId === expectedKernel, 'NATIVE_KERNEL_PROVIDER_MISMATCH');
  const parts = String(sdk_context?.model || '').split('/');
  requireValue(parts.length === 4 && parts[0] === 'custom', 'SDK_NOT_CUSTOM_MODEL');
  requireValue(strictDecode(parts[1]) === mapping.config_id
    && parts[2] === String(mapping.execution_revision)
    && strictDecode(parts[3]) === mapping.configured_model_name, 'SDK_MODEL_MAPPING_MISMATCH');
  requireValue(sdk_context.effort === mapping.reasoning_effort, 'SDK_REASONING_MISMATCH');
  requireValue(sdk_context.cwd === cwd && sdk_session_cwd === cwd
    && sdk_context.turn_id === turn_id && typeof turn_id === 'string' && turn_id.length > 0
    && sdk_session_id === session_id && typeof session_id === 'string' && session_id.length > 0
    && typeof thread_id === 'string' && thread_id.length > 0,
    'SDK_NATIVE_IDENTITY_MISMATCH');
  requireValue(sdk_provider === 'astron_gateway', 'SDK_PROVIDER_UNREVIEWED');
  return { ...mapping, native_provider: selection.provider, kernel_provider_id: expectedKernel,
    sdk_provider, sdk_model: sdk_context.model, sdk_effort: sdk_context.effort,
    sdk_cwd: sdk_context.cwd, native_thread_id: thread_id, native_turn_id: turn_id,
    native_session_id: session_id,
    native_mapping_verified: true };
}
