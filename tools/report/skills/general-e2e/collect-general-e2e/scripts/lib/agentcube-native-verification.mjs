import { createHash } from 'node:crypto';
import { readFile, lstat } from 'node:fs/promises';
import { resolve, relative, isAbsolute, win32 } from 'node:path';

function requireValue(condition, code) {
  if (!condition) throw new Error(code);
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  }
  return value;
}

const same = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

export function mcpCallableMatches(name, server, tool) {
  if (![name, server, tool].every(value => typeof value === 'string' && value.length)) return false;
  if (name.startsWith(`mcp__${server}__`) && name.endsWith(`__${tool}`)) return true;
  if (server !== 'acode_apps' || name.length !== 64 || !/^[A-Za-z0-9_]+$/.test(tool)) return false;
  const match = /^mcp__acode_apps__(connector_[A-Za-z0-9_]+)__(.+)$/.exec(name);
  if (!match) return false;
  const connector = match[1], namespace = `${server}__${connector}`;
  const prefix = `mcp__${namespace}__`;
  if ((prefix + tool).length <= 64) return false;
  const identity = [server, namespace, connector, tool, tool].join('\0');
  const suffix = '_' + createHash('sha1').update(identity, 'ascii').digest('hex').slice(0, 12);
  const keep = 64 - prefix.length - suffix.length;
  return keep >= 1 && name === prefix + tool.slice(0, keep) + suffix;
}

async function child(root, name) {
  requireValue(typeof name === 'string' && name && !name.includes('\\'), 'AGENTCUBE_PATH_INVALID');
  const path = resolve(root, name);
  const rel = relative(resolve(root), path);
  requireValue(rel && !rel.startsWith('..') && !isAbsolute(rel), 'AGENTCUBE_PATH_ESCAPE');
  requireValue((await lstat(path)).isFile(), 'AGENTCUBE_FILE_INVALID');
  return readFile(path);
}

/** Replay the remote profile independently from the execution controller. */
export async function verifyAgentCubeNative({ unitRoot, traceRoot, index, stateBytes, record }) {
  const state = JSON.parse(stateBytes.toString('utf8'));
  requireValue(state.schema === 'wildclawbench.agentcube-execution-proof/v1'
    && index.adapter?.id === 'agentcube-astudio-native'
    && state.unit?.backend === 'agentcube' && state.unit?.harness === 'astronstudio', 'AGENTCUBE_PROFILE_INVALID');
  requireValue(same(state.identity, record.identity) && same(index.identity, record.identity), 'AGENTCUBE_IDENTITY_MISMATCH');
  const proof = await child(traceRoot, 'bindings/execution-proof.json');
  requireValue(sha(proof) === sha(stateBytes), 'AGENTCUBE_PROOF_STATE_MISMATCH');
  requireValue(state.report?.schema_version === 2 && state.report?.status === 'completed', 'AGENTCUBE_TERMINAL_UNVERIFIED');
  const cleanup = state.process_cleanup;
  requireValue(cleanup?.schema === 'wildclawbench.agentcube-process-cleanup/v1'
    && cleanup.phase === 'completed' && cleanup.supported === true && cleanup.success === true
    && Array.isArray(cleanup.before)
    && Array.isArray(cleanup.after) && cleanup.after.length === 0
    && cleanup.quiet_observed_milliseconds >= 5000, 'AGENTCUBE_CLEANUP_UNVERIFIED');
  const root = cleanup.before.find(item => item.pid === cleanup.root_pid);
  const alreadyExited = cleanup.disposition === 'already_exited'
    && cleanup.root_pid === null && cleanup.before.length === 0;
  requireValue(alreadyExited || (root?.name?.toLowerCase() === 'astudio.exe' && root.path && root.created),
    'AGENTCUBE_PROCESS_ROOT_INVALID');
  requireValue(state.native_binding && same(state.native_binding.session.cwd, record.session?.cwd)
    && win32.normalize(cleanup.workspace).toLowerCase() === win32.normalize(record.session.cwd).toLowerCase(), 'AGENTCUBE_WORKSPACE_MISMATCH');
  requireValue(index.raw_trace?.length === 1, 'AGENTCUBE_NATIVE_SOURCE_AMBIGUOUS');
  const rawRef = index.raw_trace[0];
  const raw = await child(traceRoot, rawRef.path);
  requireValue(sha(raw) === rawRef.sha256 && raw.length === rawRef.size
    && sha(raw) === state.native_binding.raw_sha256, 'AGENTCUBE_RAW_DRIFT');
  const rows = raw.toString('utf8').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const headers = rows.filter(item => item.type === 'session_meta').map(item => item.payload);
  const contexts = rows.filter(item => item.type === 'turn_context').map(item => item.payload);
  const users = rows.filter(item => item.type === 'event_msg' && item.payload?.type === 'user_message').map(item => item.payload);
  const terminals = rows.filter(item => item.type === 'event_msg' && item.payload?.type === 'task_complete').map(item => item.payload);
  requireValue(headers.length === 1 && headers[0].id === record.session.session_id && contexts.length > 0
    && contexts.every(item => item.turn_id === record.session.turn_id
      && win32.normalize(item.cwd).toLowerCase() === win32.normalize(record.session.cwd).toLowerCase())
    && users.length === 1 && terminals.length === 1 && terminals[0].turn_id === record.session.turn_id,
  'AGENTCUBE_NATIVE_BINDING_INVALID');
  const decodeModel = value => value.startsWith('builtin/')
    ? Buffer.from(value.slice('builtin/'.length), 'base64').toString('utf8') : value;
  const expectedModel = state.unit.model.toLowerCase() === 'auto' ? 'astronclaw-auto' : state.unit.model;
  const actualModels = [...new Set(contexts.map(item => decodeModel(String(item.model || ''))))];
  const recordModel = record.model.actual_id?.toLowerCase() === 'auto' ? 'astronclaw-auto' : record.model.actual_id;
  requireValue(record.session.verified === true && record.session.thread_id === null
    && actualModels.length === 1 && actualModels[0].toLowerCase() === expectedModel.toLowerCase()
    && String(recordModel).toLowerCase() === actualModels[0].toLowerCase()
    && record.model.requested_id === state.unit.model, 'AGENTCUBE_MODEL_BINDING_MISMATCH');
  if (state.unit.reasoning_effort != null) {
    requireValue(contexts.every(item => String(item.effort).toLowerCase() === state.unit.reasoning_effort.toLowerCase())
      && String(record.model.reasoning_effort).toLowerCase() === state.unit.reasoning_effort.toLowerCase(),
    'AGENTCUBE_REASONING_BINDING_MISMATCH');
  }
  let promptText = users[0].message;
  requireValue(typeof promptText === 'string', 'AGENTCUBE_NATIVE_PROMPT_MISMATCH');
  if (sha(Buffer.from(promptText, 'utf8')) !== record.prompt.sha256) {
    // 独立重放长粘贴传输，不信任执行器自报的解码结果，也不改写原始消息。
    const transport = state.native_binding.prompt_transport;
    const opening = '<pasted_text>\n', closing = '\n</pasted_text>';
    requireValue(transport?.kind === 'astudio-single-pasted-text-json'
      && transport.native_message_sha256 === sha(Buffer.from(promptText, 'utf8'))
      && promptText.startsWith(opening) && promptText.endsWith(closing), 'AGENTCUBE_NATIVE_PROMPT_MISMATCH');
    let entries;
    try { entries = JSON.parse(promptText.slice(opening.length, -closing.length)); } catch {}
    requireValue(Array.isArray(entries) && entries.length === 1 && entries[0]
      && Object.keys(entries[0]).length === 1 && typeof entries[0].text === 'string', 'AGENTCUBE_NATIVE_PROMPT_MISMATCH');
    promptText = entries[0].text;
    requireValue(transport.decoded_text_sha256 === sha(Buffer.from(promptText, 'utf8')), 'AGENTCUBE_NATIVE_PROMPT_MISMATCH');
  }
  requireValue(sha(Buffer.from(promptText, 'utf8')) === record.prompt.sha256
    && record.prompt.sha256 === state.prompt_sha256, 'AGENTCUBE_NATIVE_PROMPT_MISMATCH');
  const transcript = (await child(traceRoot, index.transcript.path)).toString('utf8').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const calls = rows.filter(item => item.type === 'response_item' && ['function_call', 'custom_tool_call'].includes(item.payload?.type)).map(item => item.payload);
  const results = rows.filter(item => item.type === 'response_item' && ['function_call_output', 'custom_tool_call_output'].includes(item.payload?.type)).map(item => item.payload);
  const mcpEnds = rows.filter(item => item.type === 'event_msg' && item.payload?.type === 'mcp_tool_call_end').map(item => item.payload);
  for (const end of mcpEnds) {
    const call = calls.find(item => item.call_id === end.call_id);
    const invocation = end.invocation || {};
    let args = call?.arguments ?? call?.input;
    if (typeof args === 'string') { try { args = JSON.parse(args); } catch {} }
    requireValue(call && results.some(item => item.call_id === end.call_id)
      && mcpCallableMatches(call.name, invocation.server, invocation.tool)
      && same(args, invocation.arguments),
    'AGENTCUBE_MCP_INVOCATION_MISMATCH');
  }
  const normalizedCalls = transcript.filter(item => item.type === 'tool_call');
  const normalizedResults = transcript.filter(item => item.type === 'tool_result');
  requireValue(calls.length === normalizedCalls.length && results.length === normalizedResults.length
    && calls.length === results.length && index.calls?.length === calls.length, 'AGENTCUBE_TOOL_COVERAGE_MISMATCH');
  for (const call of calls) {
    const found = normalizedCalls.filter(item => item.tool?.call_id === call.call_id);
    let args = call.arguments ?? call.input;
    if (typeof args === 'string') { try { args = JSON.parse(args); } catch {} }
    requireValue(found.length === 1 && found[0].tool.name === call.name && same(found[0].tool.arguments, args), 'AGENTCUBE_TOOL_CALL_MISMATCH');
  }
  for (const result of results) {
    const found = normalizedResults.filter(item => item.tool?.call_id === result.call_id);
    requireValue(found.length === 1 && same(found[0].tool.result, result.output), 'AGENTCUBE_TOOL_RESULT_MISMATCH');
  }
  const final = await child(unitRoot, record.evidence.final_response_path);
  requireValue(final.toString('utf8') === terminals[0].last_agent_message, 'AGENTCUBE_FINAL_RESPONSE_MISMATCH');
  return { profile: 'agentcube-astudio-native/v1', verified: true, native_tool_calls: calls.length };
}
