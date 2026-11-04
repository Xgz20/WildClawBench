import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { SDK_CLEANUP_PROFILE, validateQwenSdkCleanupCancellation } from '../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/sdk-human-interaction.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
const json = value => { const bytes = Buffer.from(JSON.stringify(value) + '\n'); return { value, bytes, sha256: sha(bytes) }; };
const sdk = (values, absolute) => ({ bytes: Buffer.from(values.map(x => JSON.stringify(x)).join('\n') + '\n'), absolute });

function fixture() {
  const identity = { task_id: 'task-a', execution_attempt_id: 'attempt-a', host_session_id: 'session-a', agent_id: 'agent-a' };
  const state = { identity: { task_id: 'task-a', attempt_id: 'attempt-a' }, session: { session_id: 'session-a', cwd: '/workspace/task-a' },
    human_assistance: { mode: 'automatic', operation_count: 0, semantic_intervention_count: 0 } };
  const row = { sessionId: 'session-a', cwd: '/workspace/task-a', agentId: 'agent-a', parent_tool_use_id: 'parent-call', isSidechain: true };
  const use = { ...row, uuid: 'use-uuid', message: { content: [{ type: 'tool_use', id: 'delete-call',
    name: 'mcp__qw-builtin__host_safe_delete', input: { items: [{ path: '/private/tmp/item.pdf' }] } }] } };
  const denial = { ...row, uuid: 'denial-uuid', message: { content: [{ type: 'tool_result', tool_use_id: 'delete-call', is_error: true,
    content: JSON.stringify({ results: [{ path: '/private/tmp/item.pdf', status: 'failed', errorCode: 'PATH_NOT_AUTHORIZED' }] }) }] } };
  const parent = { sessionId: 'session-a', cwd: '/workspace/task-a', message: { content: [{ type: 'tool_use', id: 'parent-call', name: 'Task' }] } };
  const beforeRoot = sdk([parent], '/native/session-a.jsonl'), beforeChild = sdk([use], '/native/session-a/subagents/agent-agent-a.jsonl');
  const beforeMeta = json({ toolUseId: 'parent-call' });
  const nativeMeta = { ...beforeMeta, absolute: '/native/session-a/subagents/agent-agent-a.meta.json' };
  const nativeRoot = sdk([parent], beforeRoot.absolute), nativeChild = sdk([use, denial], beforeChild.absolute);
  const b = { schema_version: 'wildclawbench.qwenwork-sdk-cleanup-pending/v1', ...identity, parent_tool_use_id: 'parent-call',
    native_tool_event_uuid: 'use-uuid', native_call_id: 'delete-call', native_tool_name: 'mcp__qw-builtin__host_safe_delete',
    original_input_paths: ['/private/tmp/item.pdf'], ui_targets: ['/private/tmp/item.pdf'], ui_title: '确认移至回收站', sdk_sources: {} };
  for (const [name, source, current] of [['before-sdk-root.jsonl', beforeRoot, nativeRoot],
    ['before-sdk-child.jsonl', beforeChild, nativeChild], ['before-sdk-child.meta.json', beforeMeta, nativeMeta]]) {
    b.sdk_sources[name] = { native_path: current.absolute, size: source.bytes.length, sha256: sha(source.bytes) };
  }
  const before = json(b);
  const a = { schema_version: 'wildclawbench.qwenwork-native-ui-interaction-authorization/v1', profile: SDK_CLEANUP_PROFILE,
    identity, action: 'cancel-cleanup', native_call_id: 'delete-call', native_tool_event_uuid: 'use-uuid',
    authorization_source: 'direct-user-question-reply-in-control-chat', user_answer: '取消清理并继续',
    approved_targets: b.ui_targets, before_pending_sha256: before.sha256, prompt_resend_allowed: false };
  const i = { action: 'click-unique-cancel-button', ui_title: b.ui_title, native_call_id: 'delete-call',
    ui_targets: b.ui_targets, pre_click_sdk_row: JSON.stringify(use), pre_click_sdk_row_sha256: sha(JSON.stringify(use)), prompt_dispatch_operations: 0 };
  const authorization = json(a), invocation = json(i);
  const receipt = json({ schema_version: 'wildclawbench.qwenwork-native-ui-interaction-receipt/v1', profile: SDK_CLEANUP_PROFILE,
    identity, action: 'cancel-cleanup', native_call_id: 'delete-call', native_tool_event_uuid: 'use-uuid', approved_targets: b.ui_targets,
    authorization: a, invocation: i, authorization_sha256: authorization.sha256, invocation_sha256: invocation.sha256,
    post_click_sdk_row: JSON.stringify(denial), post_click_sdk_row_sha256: sha(JSON.stringify(denial)),
    prompt_dispatch_operations: 0, human_assistance: { mode: 'human_assisted', operation_count: 1, semantic_intervention_count: 0 } });
  return { receipt, authorization, invocation, before, beforeRoot, beforeChild, beforeMeta, nativeRoot, nativeChild, nativeMeta, state };
}

function refresh(source) {
  for (const key of ['authorization', 'invocation', 'before']) source[key] = json(source[key].value);
  const r = source.receipt.value;
  r.authorization = source.authorization.value; r.authorization_sha256 = source.authorization.sha256;
  r.invocation = source.invocation.value; r.invocation_sha256 = source.invocation.sha256;
  source.receipt = json(r);
}

test('SDK sidechain cancellation counts one mechanical operation without rewriting original state', () => {
  const f = fixture(), original = structuredClone(f.state);
  assert.deepEqual(validateQwenSdkCleanupCancellation(f), { mode: 'human_assisted', operation_count: 1, semantic_intervention_count: 0 });
  assert.deepEqual(f.state, original);
});

for (const [name, mutate, pattern] of [
  ['missing direct user decision', f => { f.authorization.value.user_answer = ''; }, /EXPLICIT_USER_CANCEL_REQUIRED/],
  ['other task', f => { f.state.identity.task_id = 'foreign-task'; }, /IDENTITY_MISMATCH/],
  ['other SDK stream', f => { f.nativeChild.bytes = Buffer.from('different'); }, /SDK_PREFIX_MISMATCH/],
  ['changed child metadata', f => { f.nativeMeta.bytes = Buffer.from('{}'); }, /SDK_PREFIX_MISMATCH/],
  ['snapshot drift', f => { f.beforeChild.bytes = Buffer.from('changed'); }, /SDK_SNAPSHOT_DRIFT/],
  ['broader targets', f => { f.authorization.value.approved_targets = ['/private/tmp/other.pdf']; }, /TARGET_SCOPE_MISMATCH/],
  ['resend', f => { f.invocation.value.prompt_dispatch_operations = 1; }, /INTERVENTION_SCOPE_INVALID/],
  ['another UI action', f => { f.invocation.value.action = 'click-delete'; }, /UI_ACTION_INVALID/],
  ['pre-existing assistance', f => { f.state.human_assistance.operation_count = 1; }, /BASE_ASSISTANCE_UNSUPPORTED/],
]) test('SDK cancellation rejects ' + name, () => {
  const f = fixture(); mutate(f); refresh(f); assert.throws(() => validateQwenSdkCleanupCancellation(f), pattern);
});

for (const [name, edit, pattern] of [
  ['successful deletion', row => { row.message.content[0].content = JSON.stringify({ results: [{ path: '/private/tmp/item.pdf', status: 'deleted' }] }); }, /NATIVE_DENIAL_INVALID/],
  ['foreign child denial', row => { row.agentId = 'foreign-agent'; }, /DENIAL_SCOPE_MISMATCH/],
  ['wrong call result', row => { row.message.content[0].tool_use_id = 'other-call'; }, /DENIAL_NOT_UNIQUE/],
]) test('SDK cancellation rejects ' + name, () => {
  const f = fixture(), lines = f.nativeChild.bytes.toString().trim().split('\n'), row = JSON.parse(lines[1]); edit(row);
  lines[1] = JSON.stringify(row); f.nativeChild.bytes = Buffer.from(lines.join('\n') + '\n');
  f.receipt.value.post_click_sdk_row = lines[1]; f.receipt.value.post_click_sdk_row_sha256 = sha(lines[1]); refresh(f);
  assert.throws(() => validateQwenSdkCleanupCancellation(f), pattern);
});
