import { analyzeRollout, ROLLOUT_PATH } from './astronstudio-rollout.mjs';

const ensure = (ok, code) => { if (!ok) throw Error(code); };
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])])) : value;
const signature = value => JSON.stringify(stable(value));
const shellQuote = value => `'${value.replaceAll("'", "'\\''")}'`;

function verifyProjectedTool(projected, native, call) {
  const p = projected.tool, n = native?.tool, args = call?.tool.arguments;
  ensure(n && call, 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
  if (p.name === n.name) {
    ensure(signature(projected.type === 'tool_call' ? p.arguments : p.result)
      === signature(projected.type === 'tool_call' ? n.arguments : n.result), 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    return;
  }
  if (p.name === 'command' && n.name === 'bash') {
    ensure(typeof args?.command === 'string', 'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    if (projected.type === 'tool_call') {
      const a = p.arguments;
      ensure(['/usr/local/bin/bash', '/bin/bash'].some(shell => a.command === `${shell} -lc ${shellQuote(args.command)}`)
        && a.command_actions?.length === 1 && a.command_actions[0].command === args.command,
      'PROVIDER_ROLLOUT_TOOL_CONFLICT');
    } else {
      const match = typeof n.result === 'string' && /^Exit code: (-?\d+)\nWall time: (\d+(?:\.\d+)?) seconds\nOutput:\n([\s\S]*)$/.exec(n.result);
      ensure(match && p.result?.exit_code === Number(match[1]) && (p.result.output ?? '') === match[3]
        && (p.result.duration_ms == null || Math.round(p.result.duration_ms / 100) / 10 === Number(match[2])),
      'PROVIDER_ROLLOUT_TOOL_CONFLICT');
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
export function normalizeRolloutTranscript(bytes, state, provider) {
  const analysis = analyzeRollout(bytes, state);
  const events = [], calls = new Map(), missing = [], assistants = [], mirrors = [];
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
      const call = calls.get(id), output = p.output;
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
  if (assistants.length && mirrors.length) ensure(signature(assistants.map(e => e.content)) === signature(mirrors.map(e => e.content)), 'ROLLOUT_ASSISTANT_MIRROR_CONFLICT');
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
      verifyProjectedTool(e, native, call);
      if (e.tool.name === 'command' && e.type === 'tool_call') ensure(e.tool.arguments.cwd === state.session.cwd, 'PROVIDER_ROLLOUT_TOOL_CWD_CONFLICT');
    }
  }
  return { events, calls: [...calls].map(([call_id, c]) => ({ call_id, call_sequence: c.call_sequence, result_sequence: c.result_sequence })),
    completeness: { status: missing.length ? 'partial' : 'complete', omitted_event_count: 0, missing: [...new Set(missing)].sort() } };
}
