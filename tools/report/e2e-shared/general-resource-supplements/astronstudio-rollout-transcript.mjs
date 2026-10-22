import { posix as path } from 'node:path';
import { analyzeRollout, ROLLOUT_PATH } from './astronstudio-rollout.mjs';
import { verifyAssistantMirrors } from './assistant-mirror-compaction.mjs';

const ensure = (ok, code) => { if (!ok) throw Error(code); };
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])])) : value;
const signature = value => JSON.stringify(stable(value));
const shellQuote = value => `'${value.replaceAll("'", "'\\''")}'`;
const shellDoubleQuote = value => `"${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"').replaceAll('$', '\\$').replaceAll('`', '\\`')}"`;
// The native "bash" tool uses the configured desktop shell on macOS. Match
// only literal, fully quoted wrappers; never evaluate a projected command.
const desktopShells = ['/usr/local/bin/bash', '/bin/bash', '/bin/zsh'];
export const TRANSCRIPT_SOURCE_POLICIES = ['provider-reconciled', 'bound-native-sdk'];

// Parse only literal words and && separators. This is a comparison grammar,
// never a shell evaluator: expansion, comments, redirection and other operators
// are deliberately unsupported, including inside the search summary.
function literalShellTokens(value) {
  if (typeof value !== 'string' || /[\u0000-\u0008\u000a-\u001f\u007f$`]/u.test(value)) return null;
  const tokens = [];
  let word = '', started = false, quote = null;
  const flush = () => { if (started) tokens.push({ word }); word = ''; started = false; };
  for (let i = 0; i < value.length; i += 1) {
    const c = value[i];
    if (quote === "'") { if (c === "'") quote = null; else word += c; continue; }
    if (quote === '"') {
      if (c === '"') quote = null;
      else if (c === '\\') { const next = value[++i]; if (!['"', '\\'].includes(next)) return null; word += next; }
      else word += c;
      continue;
    }
    if (c === ' ' || c === '\t') { flush(); continue; }
    if (c === "'" || c === '"') { quote = c; started = true; continue; }
    if (c === '&' && value[i + 1] === '&') { flush(); tokens.push({ operator: '&&' }); i += 1; continue; }
    if ('|;&<>()*?[]{}~!#'.includes(c)) return null;
    if (c === '\\') {
      const next = value[++i];
      if (next === undefined || !/[ \t'"\\]/u.test(next)) return null;
      word += next; started = true; continue;
    }
    word += c; started = true;
  }
  if (quote) return null;
  flush();
  if (tokens.some((token, i) => token.operator && (!i || i === tokens.length - 1 || tokens[i - 1].operator))) return null;
  return tokens;
}

function verifiedStaticRgTail(command, actions) {
  if (actions?.length !== 1 || actions[0]?.type !== 'search') return false;
  const original = literalShellTokens(command), projected = literalShellTokens(actions[0].command);
  if (!original || !projected || projected.some(token => token.operator)) return false;
  const last = original.findLastIndex(token => token.operator === '&&');
  if (last <= 0) return false;
  const tail = original.slice(last + 1);
  if (tail.length !== 4 || tail.some(token => token.operator) || tail[0].word !== 'rg' || tail[1].word !== '-c') return false;
  const words = tail.map(token => token.word);
  return signature(words) === signature(projected.map(token => token.word))
    && actions[0].query === words[2]
    && [words[3], words[3].split('/').at(-1)].includes(actions[0].path);
}

function verifyArtifactProjection(projected, native, call, row) {
  const p = projected.tool, n = native.tool, item = row?.event?.payload?.data?.item;
  // Exact observed artifact profiles, not a general namespace-stripping rule.
  const profile = ['astron_publish_artifact', 'astron_bind_artifact'].includes(p.name) ? { status: 'completed', success: true }
    : { status: 'failed', success: false };
  ensure(item?.type === 'dynamicToolCall' && item.namespace === 'acode_artifacts'
    && item.tool === p.name && item.id === p.call_id && p.call_id === n.call_id
    && p.call_id === call.tool.call_id && signature(item.arguments) === signature(call.tool.arguments),
  'PROVIDER_ROLLOUT_TOOL_CONFLICT');
  if (projected.type === 'tool_call') {
    ensure(row.event_type === 'item.started' && item.status === 'inProgress'
      && signature(p.arguments) === signature(call.tool.arguments), 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
  } else {
    ensure(row.event_type === 'item.completed' && item.status === profile.status
      && item.success === profile.success && item.error == null && item.contentItems?.length === 1
      && item.contentItems[0].type === 'inputText' && typeof item.contentItems[0].text === 'string'
      && item.contentItems[0].text === n.result
      && (profile.success || n.result.length > 0)
      && p.result?.status === profile.status && p.result.error == null && p.result.result == null
      && p.result.server == null && p.result.plugin_id == null
      && Number.isFinite(item.durationMs) && item.durationMs >= 0 && p.result.duration_ms === item.durationMs,
    'PROVIDER_ROLLOUT_TOOL_CONFLICT');
  }
}

function verifyProjectedCwd(projected, call, workspace) {
  if (projected.tool.name !== 'command') return;
  const declared = call?.tool.arguments?.workdir;
  const expected = declared == null ? workspace : declared;
  ensure(typeof workspace === 'string' && path.isAbsolute(workspace) && path.resolve(workspace) === workspace
    && typeof expected === 'string' && path.isAbsolute(expected) && path.resolve(expected) === expected,
  'PROVIDER_ROLLOUT_TOOL_CWD_CONFLICT');
  const child = path.relative(workspace, expected);
  ensure((expected === workspace || ['bash', 'exec_command'].includes(call?.tool.name))
    && child !== '..' && !child.startsWith('../') && !path.isAbsolute(child)
    && projected.tool.arguments?.cwd === expected, 'PROVIDER_ROLLOUT_TOOL_CWD_CONFLICT');
}

function verifyProjectedTool(projected, native, call, projectionRow) {
  const p = projected.tool, n = native?.tool, args = call?.tool.arguments;
  ensure(n && call, 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
  if (['astron_publish_artifact', 'astron_bind_artifact', 'astron_allocate_artifact'].includes(p.name)
      && n.name === `acode_artifacts__${p.name}`) {
    verifyArtifactProjection(projected, native, call, projectionRow);
    return;
  }
  if (p.name === n.name) {
    ensure(signature(projected.type === 'tool_call' ? p.arguments : p.result)
      === signature(projected.type === 'tool_call' ? n.arguments : n.result), 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    return;
  }
  if (p.name === 'command' && ['bash', 'exec_command'].includes(n.name)) {
    const command = n.name === 'bash' ? args?.command : args?.cmd;
    ensure(typeof command === 'string' && (args.login == null || typeof args.login === 'boolean'), 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    if (projected.type === 'tool_call') {
      const a = p.arguments;
      const staticTail = n.name === 'bash' && verifiedStaticRgTail(command, a?.command_actions);
      const wrappers = [shellQuote(command), shellDoubleQuote(command),
        ...(staticTail ? [shellQuote(command.replaceAll('"', '\\"'))] : [])];
      const shells = args.shell == null ? desktopShells : desktopShells.filter(shell => shell === args.shell);
      const flag = args.login === false ? '-c' : '-lc';
      ensure(shells.some(shell => wrappers.some(quoted => a?.command === `${shell} ${flag} ${quoted}`))
        && a?.command_actions?.length === 1
        && (a.command_actions[0].command === command || staticTail),
      'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    } else if (n.name === 'bash') {
      const match = typeof n.result === 'string' && /^Exit code: (-?\d+)\nWall time: (\d+(?:\.\d+)?) seconds\nOutput:\n([\s\S]*)$/.exec(n.result);
      ensure(match && p.result?.exit_code === Number(match[1]) && (p.result.output ?? '') === match[3]
        && (p.result.duration_ms == null || Math.round(p.result.duration_ms / 100) / 10 === Number(match[2])),
      'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    } else {
      const match = typeof n.result === 'string'
        && /^Chunk ID: [a-zA-Z0-9_-]+\nWall time: (\d+(?:\.\d+)?) seconds\nProcess exited with code (-?\d+)\nOriginal token count: \d+\nOutput:\n([\s\S]*)$/.exec(n.result);
      ensure(match && p.result?.exit_code === Number(match[2]) && (p.result.output ?? '') === match[3]
        && (p.result.duration_ms == null || (Number.isFinite(p.result.duration_ms) && p.result.duration_ms >= 0
          && Math.round(p.result.duration_ms * 10) / 10000 === Number(match[1]))), 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    }
    return;
  }
  if (p.name === 'file_change' && n.name === 'write') {
    const changes = projected.type === 'tool_call' ? p.arguments?.changes : p.result?.changes;
    ensure(changes?.length === 1 && changes[0].raw_path === args?.file_path
      && changes[0].kind?.type === 'add' && !changes[0].kind?.raw_move_path
      && changes[0].diff === args?.content, 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    if (projected.type === 'tool_result') ensure(p.result.status === 'completed'
      && n.result === `<path>${args.file_path}</path>\n<type>file</type>\n<content>\nCreated file\n</content>`,
    'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    return;
  }
  throw Error('PROVIDER_ROLLOUT_TOOL_CONFLICT');
}
const text = content => {
  ensure(Array.isArray(content) && content.every(b =>
    ['input_text', 'output_text', 'text'].includes(b.type) && typeof b.text === 'string'),
  'ROLLOUT_MESSAGE_CONTENT_UNSUPPORTED');
  return content.map(b => b.text).join('\n');
};

// Only native rows in the verified turn may become transcript events. Provider
// projections are retained separately; never insert text from evaluator files.
export function normalizeRolloutTranscript(bytes, state, provider, { sourcePolicy = 'provider-reconciled' } = {}) {
  ensure(TRANSCRIPT_SOURCE_POLICIES.includes(sourcePolicy), 'ROLLOUT_SOURCE_POLICY_UNSUPPORTED');
  const analysis = analyzeRollout(bytes, state);
  const events = [], calls = new Map(), missing = [], assistants = [], mirrors = [], projectionConflicts = [];
  let current = null, terminal = null;
  const append = (row, line, event) => {
    const value = {
      schema_id: 'urn:wildclawbench:schema:general-e2e:transcript-event:v1',
      schema_version: 1, identity: { ...state.identity },
      event_id: `${state.session.session_id}:${state.session.turn_id}:L${line}`,
      sequence: events.length, occurred_at: row.timestamp ?? null,
      source: { adapter: 'astronstudio-bound-rollout@0.1.0', raw_ref: `${ROLLOUT_PATH}#L${line}`, redacted: false },
      ...event,
    };
    events.push(value);
    return value;
  };
  for (const [i, raw] of bytes.toString('utf8').split('\n').entries()) {
    if (!raw.trim()) continue;
    const row = JSON.parse(raw), p = row.payload ?? {}, line = i + 1;
    if (row.type === 'event_msg' && p.type === 'task_started') current = p.turn_id;
    if (row.type === 'turn_context') current = p.turn_id;
    if ((p.internal_chat_message_metadata_passthrough?.turn_id ?? current) !== state.session.turn_id) continue;
    if (row.type === 'event_msg') {
      if (p.type === 'task_started') append(row, line, { type: 'status', content: 'turn.started', status: p });
      if (p.type === 'user_message') {
        ensure(!terminal, 'ROLLOUT_CONTENT_AFTER_TERMINAL');
        append(row, line, { type: 'user_message', role: 'user', content: p.message });
        if (p.images?.length || p.local_images?.length) missing.push('unsupported_user_attachment');
      }
      if (p.type === 'agent_message') {
        ensure(!terminal, 'ROLLOUT_CONTENT_AFTER_TERMINAL');
        ensure(typeof p.message === 'string', 'ROLLOUT_ASSISTANT_TEXT_MISSING');
        mirrors.push({ row, line, content: p.message });
      }
      if (['task_complete', 'turn_aborted'].includes(p.type)) {
        ensure(!terminal, 'ROLLOUT_TERMINAL_AMBIGUOUS');
        terminal = p;
        append(row, line, { type: 'status', content: p.type === 'task_complete' ? 'turn.completed' : 'turn.aborted', status: p });
      }
      if (p.type === 'token_count') append(row, line, { type: 'usage', usage: p.info ?? null });
      if (p.type === 'error') append(row, line, { type: 'error', content: JSON.stringify(p) });
    }
    if (row.type !== 'response_item') continue;
    if (p.type === 'message' && p.role === 'assistant') {
      ensure(!terminal, 'ROLLOUT_CONTENT_AFTER_TERMINAL');
      assistants.push(append(row, line, { type: 'assistant_message', role: 'assistant', content: text(p.content), final: false }));
    } else if (['function_call', 'custom_tool_call', 'tool_search_call'].includes(p.type)) {
      ensure(!terminal, 'ROLLOUT_CONTENT_AFTER_TERMINAL');
      const id = p.call_id ?? p.id, name = p.type === 'tool_search_call' ? 'tool_search' : p.name;
      let args = p.arguments ?? p.input ?? (p.type === 'tool_search_call' ? p : null);
      if (p.type === 'function_call' && typeof args === 'string') {
        try { args = JSON.parse(args); } catch { missing.push(`tool_arguments_json:${id}`); }
      }
      const sig = signature([p.type, name, args]);
      if (calls.has(id)) { ensure(calls.get(id).signature === sig, 'ROLLOUT_CALL_ID_CONFLICT'); continue; }
      const event = append(row, line, { type: 'tool_call', role: 'assistant', content: null,
        tool: { call_id: id, name, arguments: args, status: 'unknown' },
        message: { role: 'assistant', content: [{ type: 'tool_use', id, name, input: args, arguments: args }] } });
      calls.set(id, { signature: sig, name, call_sequence: event.sequence, result_sequence: null, output: undefined });
    } else if (['function_call_output', 'custom_tool_call_output', 'tool_search_output'].includes(p.type)) {
      ensure(!terminal, 'ROLLOUT_CONTENT_AFTER_TERMINAL');
      const id = p.call_id ?? p.id;
      ensure(typeof id === 'string' && id, 'ROLLOUT_RESULT_ID_MISSING');
      const call = calls.get(id);
      let output = p.output;
      if (p.type === 'tool_search_output' && p.tools != null) {
        ensure(output == null, 'ROLLOUT_TOOL_SEARCH_OUTPUT_AMBIGUOUS');
        ensure(p.status === 'completed' && p.execution === 'client', 'ROLLOUT_TOOL_SEARCH_STATUS_UNSUPPORTED');
        ensure(Array.isArray(p.tools) && p.tools.every(t => t && typeof t === 'object'
          && !Array.isArray(t) && t.type === 'function' && typeof t.name === 'string' && t.name.length > 0
          && t.parameters && typeof t.parameters === 'object' && !Array.isArray(t.parameters))
          && new Set(p.tools.map(t => t.name)).size === p.tools.length, 'ROLLOUT_TOOL_SEARCH_TOOLS_INVALID');
        output = { tools: p.tools };
      }
      if (!call) { missing.push(`tool_call:${id}`); continue; }
      if (call.result_sequence !== null) { ensure(call.output === signature(output), 'ROLLOUT_RESULT_CONFLICT'); continue; }
      if (output === undefined || output === null) missing.push(`tool_result_content:${id}`);
      const event = append(row, line, { type: 'tool_result', role: null, content: null,
        tool: { call_id: id, name: call.name, result: output ?? null, status: 'unknown' },
        message: { role: 'tool', content: [{ type: 'tool_result', tool_use_id: id, content: output ?? null }] } });
      call.result_sequence = event.sequence; call.output = signature(output);
    } else if (p.type === 'message' && !['user', 'system', 'developer'].includes(p.role)) missing.push(`unsupported_message_role:${p.role}`);
    else if (!['message', 'reasoning'].includes(p.type)) missing.push(`unsupported_response_item:${p.type}`);
  }
  // SDK event_msg mirrors and response_item messages must agree if both exist.
  const mirrorGaps = assistants.length && mirrors.length ? verifyAssistantMirrors(assistants, mirrors, bytes, state) : [];
  if (!assistants.length) {
    for (const mirror of mirrors) assistants.push(append(mirror.row, mirror.line,
      { type: 'assistant_message', role: 'assistant', content: mirror.content, final: false }));
    events.sort((a, b) => Number(a.source.raw_ref.split('#L')[1]) - Number(b.source.raw_ref.split('#L')[1]));
    events.forEach((e, i) => { e.sequence = i; });
    // Tool sequence indexes must refer to the reordered transcript as well.
    for (const [id, call] of calls) {
      call.call_sequence = events.find(e => e.type === 'tool_call' && e.tool.call_id === id).sequence;
      call.result_sequence = events.find(e => e.type === 'tool_result' && e.tool.call_id === id)?.sequence ?? null;
    }
  }
  if (!assistants.length) missing.push('assistant_message');
  if (state.phase === 'COMPLETED') {
    ensure(terminal?.type === 'task_complete' && typeof terminal.last_agent_message === 'string', 'ROLLOUT_FINAL_BINDING_MISSING');
    ensure(assistants.at(-1)?.content === terminal.last_agent_message, 'ROLLOUT_FINAL_MESSAGE_CONFLICT');
    assistants.at(-1).final = true;
  }
  for (const [id, call] of calls) if (call.result_sequence === null) missing.push(`tool_result:${id}`);
  ensure(signature([...calls.keys()].sort()) === signature(analysis.tool_counts.catalog.map(c => c.call_id).sort()), 'ROLLOUT_TRANSCRIPT_CALL_COVERAGE');
  if (provider) {
    const users = provider.events.filter(e => e.type === 'user_message');
    ensure(users.length <= 1 && users.every(e => e.content === events.find(e => e.type === 'user_message')?.content), 'PROVIDER_ROLLOUT_PROMPT_CONFLICT');
    const finals = provider.events.filter(e => e.type === 'assistant_message' && e.final);
    ensure(finals.every(e => e.content === assistants.at(-1)?.content), 'PROVIDER_ROLLOUT_FINAL_CONFLICT');
    ensure(provider.events.filter(e => e.type === 'assistant_message').every(e => assistants.some(a => a.content === e.content)), 'PROVIDER_ROLLOUT_ASSISTANT_CONFLICT');
    ensure(provider.calls.every(c => calls.has(c.call_id)), 'ROLLOUT_PROVIDER_CALL_MISSING');
    for (const e of provider.events.filter(e => ['tool_call', 'tool_result'].includes(e.type))) {
      const native = events.find(n => n.type === e.type && n.tool.call_id === e.tool.call_id);
      const call = events.find(n => n.type === 'tool_call' && n.tool.call_id === e.tool.call_id);
      ensure(call, 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
      const rows = provider.projection_rows?.filter(row =>
        (row.raw_ref ?? `raw/astronstudio-provider-events.jsonl#L${row.raw_line}`) === e.source?.raw_ref) ?? [];
      ensure(rows.length <= 1, 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
      try {
        verifyProjectedTool(e, native, call, rows[0]);
        if (e.type === 'tool_call') verifyProjectedCwd(e, call, state.session.cwd);
      } catch (error) {
        if (sourcePolicy !== 'bound-native-sdk'
            || !['PROVIDER_ROLLOUT_TOOL_CONFLICT', 'PROVIDER_ROLLOUT_TOOL_CWD_CONFLICT'].includes(error.message)) throw error;
        projectionConflicts.push({ error: error.message, call_id: e.tool.call_id, event_type: e.type,
          provider_tool: e.tool.name, sdk_tool: native?.tool.name ?? call.tool.name, provider_raw_ref: e.source?.raw_ref ?? null,
          sdk_raw_ref: native?.source.raw_ref ?? null, source_content_identity_verified: false });
      }
    }
  }
  return { events, calls: [...calls].map(([call_id, c]) => ({ call_id, call_sequence: c.call_sequence, result_sequence: c.result_sequence })),
    ...(mirrorGaps.length ? { compaction_mirror_gaps: mirrorGaps } : {}),
    ...(sourcePolicy === 'bound-native-sdk' ? { projection_conflicts: projectionConflicts,
      source_reconciliation: { status: provider && provider.completeness?.status === 'complete' && !projectionConflicts.length ? 'verified' : 'partial',
        source_content_identity_verified: Boolean(provider && provider.completeness?.status === 'complete' && !projectionConflicts.length),
        verification_scope: 'observed retained provider projections only',
        provider_completeness: provider?.completeness ?? null, observed_provider_calls: provider?.calls.length ?? 0,
        sdk_calls: calls.size, unknown_shapes_accepted_as_equivalent: false } } : {}),
    completeness: { status: missing.length ? 'partial' : 'complete', omitted_event_count: 0, missing: [...new Set(missing)].sort() } };
}
