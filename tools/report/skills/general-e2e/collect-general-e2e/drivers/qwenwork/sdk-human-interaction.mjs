import { createHash } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { resolve } from 'node:path';

export const SDK_CLEANUP_PROFILE = 'qwenwork-sdk-jsonl-cleanup-cancellation/v1';
const sha = value => createHash('sha256').update(value).digest('hex');
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const check = (ok, code) => { if (!ok) throw Error('QWEN_SDK_CANCEL_' + code); };
const rows = source => source.bytes.toString('utf8').split(/\r?\n/u).filter(Boolean)
  .map(raw => ({ raw, value: JSON.parse(raw) }));
const blocks = row => Array.isArray(row.value.message?.content) ? row.value.message.content : [];
const canonical = value => {
  check(typeof value === 'string' && value.startsWith('/') && resolve(value) === value, 'TARGET_INVALID');
  return value.startsWith('/tmp/') ? resolve(realpathSync('/tmp'), value.slice(5)) : value;
};

/** A distinct SDK proof, never coerced into the historical OpenCode SQL proof. */
export function validateQwenSdkCleanupCancellation(sources) {
  const { receipt, authorization, invocation, before, beforeRoot, beforeChild, beforeMeta,
    nativeRoot, nativeChild, nativeMeta, state } = sources;
  const r = receipt.value, a = authorization.value, i = invocation.value, b = before.value;
  check(r.profile === SDK_CLEANUP_PROFILE && a.profile === SDK_CLEANUP_PROFILE
    && r.schema_version === 'wildclawbench.qwenwork-native-ui-interaction-receipt/v1'
    && a.schema_version === 'wildclawbench.qwenwork-native-ui-interaction-authorization/v1'
    && b.schema_version === 'wildclawbench.qwenwork-sdk-cleanup-pending/v1', 'PROFILE_INVALID');
  check(r.action === 'cancel-cleanup' && a.action === r.action
    && a.authorization_source === 'direct-user-question-reply-in-control-chat'
    && typeof a.user_answer === 'string' && a.user_answer.trim(), 'EXPLICIT_USER_CANCEL_REQUIRED');
  check(i.action === 'click-unique-cancel-button' && i.ui_title === '确认移至回收站'
    && b.ui_title === i.ui_title, 'UI_ACTION_INVALID');
  check(r.authorization_sha256 === sha(authorization.bytes) && r.invocation_sha256 === sha(invocation.bytes)
    && a.before_pending_sha256 === sha(before.bytes) && equal(r.authorization, a) && equal(r.invocation, i), 'SOURCE_DIGEST_MISMATCH');
  const identity = a.identity;
  check(equal(r.identity, identity) && identity.task_id === state.identity.task_id
    && identity.execution_attempt_id === state.identity.attempt_id
    && identity.host_session_id === state.session.session_id
    && b.task_id === identity.task_id && b.execution_attempt_id === identity.execution_attempt_id
    && b.host_session_id === identity.host_session_id && b.agent_id === identity.agent_id
    && /^[A-Za-z0-9-]+$/u.test(identity.agent_id || ''), 'IDENTITY_MISMATCH');
  check(r.native_call_id === a.native_call_id && a.native_call_id === b.native_call_id
    && i.native_call_id === a.native_call_id && a.native_tool_event_uuid === b.native_tool_event_uuid
    && r.native_tool_event_uuid === b.native_tool_event_uuid, 'CALL_IDENTITY_MISMATCH');
  for (const [name, source] of Object.entries({ 'before-sdk-root.jsonl': beforeRoot,
    'before-sdk-child.jsonl': beforeChild, 'before-sdk-child.meta.json': beforeMeta })) {
    check(b.sdk_sources?.[name]?.sha256 === sha(source.bytes)
      && b.sdk_sources[name].size === source.bytes.length, 'SDK_SNAPSHOT_DRIFT');
  }
  check(nativeRoot.bytes.subarray(0, beforeRoot.bytes.length).equals(beforeRoot.bytes)
    && nativeChild.bytes.subarray(0, beforeChild.bytes.length).equals(beforeChild.bytes)
    && nativeMeta.bytes.equals(beforeMeta.bytes)
    && b.sdk_sources['before-sdk-root.jsonl'].native_path === nativeRoot.absolute
    && b.sdk_sources['before-sdk-child.jsonl'].native_path === nativeChild.absolute
    && b.sdk_sources['before-sdk-child.meta.json'].native_path === nativeMeta.absolute, 'SDK_PREFIX_MISMATCH');
  const root = rows(beforeRoot), child = rows(beforeChild), terminal = rows(nativeChild);
  const parent = root.flatMap(row => blocks(row).filter(x => x.type === 'tool_use'
    && x.id === b.parent_tool_use_id && ['Task', 'Agent'].includes(x.name)).map(block => ({ row, block })));
  check(parent.length === 1 && beforeMeta.value.toolUseId === b.parent_tool_use_id
    && parent[0].row.value.sessionId === state.session.session_id
    && resolve(parent[0].row.value.cwd || '/') === resolve(state.session.cwd), 'PARENT_SCOPE_MISMATCH');
  const uses = child.flatMap(row => blocks(row).filter(x => x.type === 'tool_use' && x.id === a.native_call_id)
    .map(block => ({ row, block })));
  check(uses.length === 1, 'TOOL_USE_NOT_UNIQUE');
  const { row, block } = uses[0];
  check(row.value.uuid === b.native_tool_event_uuid && row.value.sessionId === state.session.session_id
    && [row.value.session_id, row.value.promptId].every(x => x == null || x === state.session.session_id)
    && row.value.agentId === identity.agent_id && row.value.isSidechain === true
    && row.value.parent_tool_use_id === b.parent_tool_use_id
    && resolve(row.value.cwd || '/') === resolve(state.session.cwd)
    && block.name === 'mcp__qw-builtin__host_safe_delete' && block.name === b.native_tool_name
    && i.pre_click_sdk_row === row.raw && i.pre_click_sdk_row_sha256 === sha(row.raw), 'TOOL_SCOPE_MISMATCH');
  const targets = a.approved_targets;
  check(Array.isArray(targets) && targets.length > 0 && new Set(targets).size === targets.length
    && equal(targets.map(canonical), targets) && equal(r.approved_targets, targets)
    && equal(i.ui_targets, targets) && equal(b.ui_targets, targets)
    && equal(block.input?.items?.map(x => x.path), b.original_input_paths)
    && equal(b.original_input_paths.map(canonical), targets), 'TARGET_SCOPE_MISMATCH');
  const resultRows = terminal.filter(x => blocks(x).some(block => block.type === 'tool_result'
    && block.tool_use_id === a.native_call_id));
  check(resultRows.length === 1, 'DENIAL_NOT_UNIQUE');
  const post = resultRows[0], result = blocks(post).find(x => x.type === 'tool_result' && x.tool_use_id === a.native_call_id);
  check(post.value.sessionId === state.session.session_id && post.value.agentId === identity.agent_id
    && post.value.isSidechain === true
    && [post.value.session_id, post.value.promptId].every(x => x == null || x === state.session.session_id)
    && post.value.parent_tool_use_id === b.parent_tool_use_id
    && resolve(post.value.cwd || '/') === resolve(state.session.cwd)
    && result.is_error === true && r.post_click_sdk_row === post.raw
    && r.post_click_sdk_row_sha256 === sha(post.raw), 'DENIAL_SCOPE_MISMATCH');
  let payload;
  try { payload = JSON.parse(result.content); } catch { throw Error('QWEN_SDK_CANCEL_NATIVE_DENIAL_INVALID'); }
  check(Array.isArray(payload?.results) && payload.results.length === targets.length
    && equal(payload.results.map(x => canonical(x.path)), targets)
    && payload.results.every(x => x.status === 'failed' && x.errorCode === 'PATH_NOT_AUTHORIZED'), 'NATIVE_DENIAL_INVALID');
  check(r.prompt_dispatch_operations === 0 && i.prompt_dispatch_operations === 0 && a.prompt_resend_allowed === false
    && r.human_assistance?.mode === 'human_assisted' && r.human_assistance.operation_count === 1
    && r.human_assistance.semantic_intervention_count === 0, 'INTERVENTION_SCOPE_INVALID');
  check(state.human_assistance?.mode === 'automatic' && state.human_assistance.operation_count === 0
    && state.human_assistance.semantic_intervention_count === 0, 'BASE_ASSISTANCE_UNSUPPORTED');
  return { mode: 'human_assisted', operation_count: 1, semantic_intervention_count: 0 };
}
