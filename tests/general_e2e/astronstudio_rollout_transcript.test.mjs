import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { normalizeRolloutTranscript } from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout-transcript.mjs';
import { normalizeRolloutTranscript as vendoredNormalizer } from '../../tools/report/skills/general-e2e/collect-general-e2e/vendor/e2e-shared/general-resource-supplements/astronstudio-rollout-transcript.mjs';

const prompt = 'Inspect installer without executing it.';
const state = { identity: { batch_id: 'b', unit_id: 'u', task_id: 't', attempt_id: 'a' }, phase: 'COMPLETED',
  prompt: { send_status: 'sent', sha256: createHash('sha256').update(prompt).digest('hex') },
  session: { verified: true, session_id: 's', turn_id: 'turn', cwd: '/tmp/rollout-workspace' } };
const r = (type, payload) => ({ timestamp: '2026-10-10T15:00:00Z', type, payload });
const fixture = () => [r('session_meta', { id: 's', cwd: state.session.cwd }),
  r('event_msg', { type: 'task_started', turn_id: 'turn' }),
  r('turn_context', { turn_id: 'turn', cwd: state.session.cwd }),
  r('event_msg', { type: 'user_message', message: prompt }),
  r('response_item', { type: 'function_call', name: 'exec_command', call_id: 'c', arguments: '{"cmd":"cat installer.sh"}' }),
  r('response_item', { type: 'function_call_output', call_id: 'c', output: 'unsafe command' }),
  r('event_msg', { type: 'agent_message', message: 'Refused execution.' }),
  r('response_item', { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'Refused execution.' }] }),
  r('event_msg', { type: 'task_complete', turn_id: 'turn', duration_ms: 1000, last_agent_message: 'Refused execution.' })];
const bytes = rows => Buffer.from(rows.map(v => JSON.stringify(v)).join('\n') + '\n');
const projection = { events: [], calls: [] };

function toolSearchFixture() {
  const rows=fixture();
  rows[4].payload={type:'tool_search_call',call_id:'search',id:'search',status:'completed',execution:'client',arguments:{query:'read browser text'}};
  rows[5].payload={type:'tool_search_output',call_id:'search',status:'completed',execution:'client',tools:[
    {type:'function',name:'mcp__fixture__snapshot',description:'Synthetic schema',defer_loading:true,parameters:{type:'object',properties:{scope:{type:'string'}}}},
  ]};
  return rows;
}

for (const [name,normalize] of [['canonical',normalizeRolloutTranscript],['vendored',vendoredNormalizer]]) {
  test(`${name}: a retained SDK message can lack only its redundant mirror at adjacent compaction`,()=>{
    const rows=fixture();rows.splice(6,0,
      r('response_item',{type:'message',id:'before-compaction',role:'assistant',content:[{type:'output_text',text:'Retained original.'}],internal_chat_message_metadata_passthrough:{turn_id:'turn'}}),
      r('compacted',{message:'Synthetic compacted context',replacement_history:[]}));
    const result=normalize(bytes(rows),state,projection);
    assert.equal(result.completeness.status,'complete');assert.equal(result.compaction_mirror_gaps.length,1);
    assert.ok(result.events.some(e=>e.content==='Retained original.'));
    for(const mutate of [
      rows=>rows[7].timestamp='2026-10-10T15:00:02Z',
      rows=>rows[7].payload.replacement_history=null,
      rows=>rows[6].payload.internal_chat_message_metadata_passthrough.turn_id='wrong',
      rows=>rows[7].type='unknown',
    ]) {const changed=structuredClone(rows);mutate(changed);assert.throws(()=>normalize(bytes(changed),state,projection));}
  });
  test(`${name}: structured tool search results preserve complete schemas and raw references`,()=>{
    for(const tools of [toolSearchFixture()[5].payload.tools,[]]) {
      const rows=toolSearchFixture();rows[5].payload.tools=tools;
      const result=normalize(bytes(rows),state,projection),output=result.events.find(e=>e.type==='tool_result');
      assert.equal(result.completeness.status,'complete');assert.deepEqual(output.tool.result,{tools});
      assert.deepEqual(output.message.content[0].content,{tools});assert.equal(output.source.raw_ref,'raw/astronstudio-rollout.jsonl#L6');
    }
  });
  test(`${name}: missing, malformed, ambiguous and failed tool searches do not become complete`,()=>{
    for(const [mutate,error] of [
      [p=>p.tools={},/TOOLS_INVALID/],[p=>p.tools=[{type:'unknown'}],/TOOLS_INVALID/],
      [p=>p.tools=[p.tools[0],p.tools[0]],/TOOLS_INVALID/],
      [p=>p.status='failed',/STATUS_UNSUPPORTED/],[p=>p.execution='server',/STATUS_UNSUPPORTED/],
      [p=>p.output='conflicting',/OUTPUT_AMBIGUOUS/],
    ]){const rows=toolSearchFixture();mutate(rows[5].payload);assert.throws(()=>normalize(bytes(rows),state,projection),error);}
    const rows=toolSearchFixture();delete rows[5].payload.tools;
    assert.deepEqual(normalize(bytes(rows),state,projection).completeness.missing,['tool_result_content:search']);
    const repeated=toolSearchFixture();repeated.splice(6,0,structuredClone(repeated[5]));
    assert.equal(normalize(bytes(repeated),state,projection).calls.length,1);
    repeated[6].payload.tools=[];assert.throws(()=>normalize(bytes(repeated),state,projection),/RESULT_CONFLICT/);
  });
  test(`${name}: SDK canonical policy retains projection differences separately and leaves strict mode unchanged`,()=>{
    const provider={completeness:{status:'complete',missing:[]},calls:[{call_id:'c'}],events:[
      {type:'tool_result',source:{raw_ref:'raw/astronstudio-provider-events.jsonl#L9'},tool:{call_id:'c',name:'exec_command',result:'projected suffix'}},
    ]};
    assert.throws(()=>normalize(bytes(fixture()),state,provider),/TOOL_CONFLICT/);
    const r=normalize(bytes(fixture()),state,provider,{sourcePolicy:'bound-native-sdk'});
    assert.equal(r.completeness.status,'complete');assert.equal(r.source_reconciliation.status,'partial');
    assert.equal(r.source_reconciliation.source_content_identity_verified,false);assert.equal(r.projection_conflicts.length,1);
    assert.equal(r.events.find(e=>e.type==='tool_result').tool.result,'unsafe command');
    const incomplete=fixture();delete incomplete[5].payload.output;
    assert.equal(normalize(bytes(incomplete),state,provider,{sourcePolicy:'bound-native-sdk'}).completeness.status,'partial');
    const missingResult=fixture().filter(r=>r.payload.type!=='function_call_output');
    assert.ok(normalize(bytes(missingResult),state,provider,{sourcePolicy:'bound-native-sdk'}).completeness.missing.includes('tool_result:c'));
    assert.throws(()=>normalize(bytes(fixture()),state,provider,{sourcePolicy:'unknown'}),/POLICY_UNSUPPORTED/);
    for(const bad of [
      {...provider,calls:[{call_id:'unbound'}]},
      {...provider,events:[{type:'user_message',content:'wrong'}]},
      {...provider,events:[{type:'assistant_message',content:'wrong',final:true}]},
      {...provider,events:[{type:'tool_result',tool:{call_id:'unbound',name:'exec_command',result:'unbound'}}]},
    ])assert.throws(()=>normalize(bytes(fixture()),state,bad,{sourcePolicy:'bound-native-sdk'}));
  });
}

test('SDK transcript preserves native tool arguments/results and line references despite absent projection', () => {
  const rows = fixture(), result = normalizeRolloutTranscript(bytes(rows), state, projection);
  assert.equal(result.completeness.status, 'complete');
  assert.deepEqual(result.calls, [{ call_id: 'c', call_sequence: 2, result_sequence: 3 }]);
  assert.equal(result.events.filter(e => e.type === 'user_message').length, 1);
  const tool = result.events.find(e => e.type === 'tool_call');
  assert.equal(tool.tool.name, 'exec_command');
  assert.deepEqual(tool.tool.arguments, { cmd: 'cat installer.sh' });
  assert.equal(tool.source.raw_ref, 'raw/astronstudio-rollout.jsonl#L5');
  assert.equal(result.events.find(e => e.type === 'tool_result').tool.result, 'unsafe command');
  assert.equal(result.events.find(e => e.final).content, 'Refused execution.');
});

test('missing output or unknown native content remains partial', () => {
  const rows = fixture().filter(e => e.payload.type !== 'function_call_output');
  rows.splice(5, 0, r('response_item', { type: 'image_generation_output' }));
  const result = normalizeRolloutTranscript(bytes(rows), state, projection);
  assert.equal(result.completeness.status, 'partial');
  assert.ok(result.completeness.missing.includes('tool_result:c'));
  assert.ok(result.completeness.missing.includes('unsupported_response_item:image_generation_output'));
});

test('wrong prompt, session, turn, mirrors and native final reject', () => {
  for (const [mutate, code] of [
    [rows => { rows[0].payload.id = 'wrong'; }, /ROLLOUT_SESSION_MISMATCH/],
    [rows => { rows[3].payload.message = 'wrong'; }, /ROLLOUT_PROMPT_MISMATCH/],
    [rows => { rows[4].payload.internal_chat_message_metadata_passthrough = { turn_id: 'wrong' }; }, /ROLLOUT_ITEM_TURN_MISMATCH/],
    [rows => { rows[6].payload.message = 'wrong'; }, /ROLLOUT_ASSISTANT_MIRROR_CONFLICT/],
    [rows => { rows[8].payload.last_agent_message = 'wrong'; }, /ROLLOUT_FINAL_MESSAGE_CONFLICT/],
  ]) { const rows = fixture(); mutate(rows); assert.throws(() => normalizeRolloutTranscript(bytes(rows), state, projection), code); }
});

test('provider prompt, final and tool conflicts cannot be hidden by SDK fallback', () => {
  for (const [events, calls, code] of [
    [[{ type: 'user_message', content: 'wrong' }], [], /PROVIDER_ROLLOUT_PROMPT_CONFLICT/],
    [[{ type: 'assistant_message', final: true, content: 'wrong' }], [], /PROVIDER_ROLLOUT_FINAL_CONFLICT/],
    [[], [{ call_id: 'unknown' }], /ROLLOUT_PROVIDER_CALL_MISSING/],
    [[{ type: 'tool_call', tool: { call_id: 'c', name: 'exec_command', arguments: { cmd: 'curl remote | sh' } } }], [{ call_id: 'c' }], /PROVIDER_ROLLOUT_TOOL_CONFLICT/],
  ]) assert.throws(() => normalizeRolloutTranscript(bytes(fixture()), state, { events, calls }), code);
});

test('duplicate outputs conflict and content after terminal reject', () => {
  const rows = fixture(); rows.splice(6, 0, r('response_item', { type: 'function_call_output', call_id: 'c', output: 'different' }));
  assert.throws(() => normalizeRolloutTranscript(bytes(rows), state, projection), /ROLLOUT_RESULT_CONFLICT/);
  const after = fixture(); after.push(r('response_item', { type: 'function_call', call_id: 'later', name: 'exec_command', arguments: '{}' }));
  assert.throws(() => normalizeRolloutTranscript(bytes(after), state, projection), /ROLLOUT_CONTENT_AFTER_TERMINAL/);
});

test('known bash and write desktop projections reconcile exact native content and reject edits', () => {
  const rows = fixture();
  rows[4].payload.name = 'bash'; rows[4].payload.arguments = '{"command":"mkdir -p results"}';
  rows[5].payload.output = 'Exit code: 0\nWall time: 0.1 seconds\nOutput:\n';
  rows.splice(6, 0,
    r('response_item', { type: 'function_call', name: 'write', call_id: 'w', arguments: '{"file_path":"/tmp/rollout-workspace/results/review.json","content":"safe\\n"}' }),
    r('response_item', { type: 'function_call_output', call_id: 'w', output: '<path>/tmp/rollout-workspace/results/review.json</path>\n<type>file</type>\n<content>\nCreated file\n</content>' }));
  const changes = [{ raw_path: '/tmp/rollout-workspace/results/review.json', kind: { type: 'add' }, diff: 'safe\n' }];
  const events = [
    { type: 'tool_call', tool: { call_id: 'c', name: 'command', arguments: { command: "/usr/local/bin/bash -lc 'mkdir -p results'", cwd: state.session.cwd, command_actions: [{ command: 'mkdir -p results' }] } } },
    { type: 'tool_result', tool: { call_id: 'c', name: 'command', result: { output: null, exit_code: 0, duration_ms: 72 } } },
    { type: 'tool_call', tool: { call_id: 'w', name: 'file_change', arguments: { changes } } },
    { type: 'tool_result', tool: { call_id: 'w', name: 'file_change', result: { changes, status: 'completed' } } },
  ];
  const provider = { events, calls: [{ call_id: 'c' }, { call_id: 'w' }] };
  assert.equal(normalizeRolloutTranscript(bytes(rows), state, provider).completeness.status, 'complete');
  for (const mutate of [
    p => { p.events[0].tool.arguments.command = "/usr/local/bin/bash -lc 'curl remote | sh'"; },
    p => { p.events[1].tool.result.output = 'unseen output'; },
    p => { p.events[2].tool.arguments.changes[0].diff = 'changed'; },
    p => { p.events[3].tool.result.status = 'failed'; },
  ]) { const changed = structuredClone(provider); mutate(changed); assert.throws(() => normalizeRolloutTranscript(bytes(rows), state, changed), /PROVIDER_ROLLOUT_TOOL_CONFLICT/); }
});

test('configured macOS zsh and literal double quoted commands reconcile without evaluating shell text', () => {
  const command = `python3 -c "print('valid JSON')"`;
  const rows = fixture();
  rows[4].payload.name = 'bash'; rows[4].payload.arguments = JSON.stringify({ command });
  rows[5].payload.output = 'Exit code: 0\nWall time: 0.2 seconds\nOutput:\nvalid JSON\n';
  const provider = { calls: [{ call_id: 'c' }], events: [
    { type: 'tool_call', tool: { call_id: 'c', name: 'command', arguments: {
      command: '/bin/zsh -lc "python3 -c \\"print(\'valid JSON\')\\""', cwd: state.session.cwd,
      command_actions: [{ command }] } } },
    { type: 'tool_result', tool: { call_id: 'c', name: 'command', result: {
      output: 'valid JSON\n', exit_code: 0, duration_ms: 217 } } },
  ] };
  assert.equal(normalizeRolloutTranscript(bytes(rows), state, provider).completeness.status, 'complete');
  for (const mutate of [
    p => { p.events[0].tool.arguments.command += '; touch /tmp/unbound'; },
    p => { p.events[0].tool.arguments.command = p.events[0].tool.arguments.command.replace('/bin/zsh', '/tmp/zsh'); },
    p => { p.events[0].tool.arguments.command_actions[0].command = 'different'; },
    p => { p.events[1].tool.result.exit_code = 1; },
    p => { p.events[1].tool.result.duration_ms = 319; },
  ]) { const changed = structuredClone(provider); mutate(changed); assert.throws(() => normalizeRolloutTranscript(bytes(rows), state, changed), /PROVIDER_ROLLOUT_TOOL_CONFLICT/); }
  const shellText = `printf '%s' "$(touch /tmp/never-execute) $HOME \`uname\`"`;
  rows[4].payload.arguments = JSON.stringify({ command: shellText });
  const changed = structuredClone(provider);
  changed.events[0].tool.arguments.command_actions[0].command = shellText;
  changed.events[0].tool.arguments.command = `/bin/zsh -lc "${shellText.replaceAll('"', '\\"')}"`;
  assert.throws(() => normalizeRolloutTranscript(bytes(rows), state, changed), /PROVIDER_ROLLOUT_TOOL_CONFLICT/);
});

const singleQuote = value => `'${value.replaceAll("'", "'\\''")}'`;
function staticSearchFixture(command = 'wc -l "/tmp/another run/log.txt" && rg -c "CVE-2021-44228" "/tmp/another run/log.txt"') {
  const rows = fixture();
  rows[4].payload.name = 'bash'; rows[4].payload.arguments = JSON.stringify({ command });
  rows[5].payload.output = 'Exit code: 0\nWall time: 0.2 seconds\nOutput:\n12\n3\n';
  const provider = { calls: [{ call_id: 'c' }], events: [
    { type: 'tool_call', tool: { call_id: 'c', name: 'command', arguments: {
      command: `/bin/zsh -lc ${singleQuote(command.replaceAll('"', '\\"'))}`, cwd: state.session.cwd,
      command_actions: [{ type: 'search', command: `rg -c 'CVE-2021-44228' '/tmp/another run/log.txt'`,
        query: 'CVE-2021-44228', path: 'log.txt' }] } } },
    { type: 'tool_result', tool: { call_id: 'c', name: 'command', result: {
      output: '12\n3\n', exit_code: 0, duration_ms: 217 } } },
  ] };
  return { rows, provider, command };
}

for (const [implementation, normalize] of [['canonical', normalizeRolloutTranscript], ['vendored', vendoredNormalizer]]) {
  test(`${implementation}: literal compound search summaries preserve the complete SDK command`, () => {
    for (const shell of ['/bin/zsh', '/bin/bash', '/usr/local/bin/bash']) {
      const { rows, provider, command } = staticSearchFixture();
      for (const wrapped of [singleQuote(command), JSON.stringify(command), singleQuote(command.replaceAll('"', '\\"'))]) {
        provider.events[0].tool.arguments.command = `${shell} -lc ${wrapped}`;
        const result = normalize(bytes(rows), state, provider);
        assert.equal(result.completeness.status, 'complete');
        const tool = result.events.find(e => e.type === 'tool_call');
        assert.equal(tool.tool.name, 'bash');
        assert.deepEqual(tool.tool.arguments, { command });
        assert.equal(result.events.find(e => e.type === 'tool_result').tool.result, rows[5].payload.output);
      }
    }
    // Different identities/materials and a longer literal prefix use the same profile.
    const command = `printf '统计' && wc -l '/tmp/新目录/记录.txt' && rg -c '警告' '/tmp/新目录/记录.txt'`;
    const { rows, provider } = staticSearchFixture(command);
    provider.events[0].tool.arguments.command_actions[0] = {
      type: 'search', command: `rg -c "警告" "/tmp/新目录/记录.txt"`, query: '警告', path: '/tmp/新目录/记录.txt' };
    assert.equal(normalize(bytes(rows), state, provider).completeness.status, 'complete');
  });

  test(`${implementation}: static search compatibility retains command, source and result gates`, () => {
    for (const mutate of [
      p => { p.events[0].tool.arguments.command = p.events[0].tool.arguments.command.replace('wc -l', 'wc -c'); },
      p => { p.events[0].tool.arguments.command_actions[0].command = 'rg -c other other.txt'; },
      p => { p.events[0].tool.arguments.command_actions[0].query = 'other'; },
      p => { p.events[0].tool.arguments.command_actions[0].path = 'other.txt'; },
      p => { p.events[0].tool.arguments.command_actions[0].type = 'read'; },
      p => { p.events[0].tool.arguments.command_actions.push(p.events[0].tool.arguments.command_actions[0]); },
      p => { p.events[0].tool.arguments.command = p.events[0].tool.arguments.command.replace('/bin/zsh', '/tmp/zsh'); },
      p => { p.events[1].tool.result.output = 'changed'; },
      p => { p.events[1].tool.result.exit_code = 1; },
      p => { p.events[1].tool.result.duration_ms = 319; },
    ]) {
      const { rows, provider } = staticSearchFixture(); mutate(provider);
      assert.throws(() => normalize(bytes(rows), state, provider), /PROVIDER_ROLLOUT_TOOL_CONFLICT/);
    }
    const { rows, provider } = staticSearchFixture();
    provider.events[0].tool.arguments.cwd = '/tmp/wrong';
    assert.throws(() => normalize(bytes(rows), state, provider), /PROVIDER_ROLLOUT_TOOL_CWD_CONFLICT/);
    provider.events[0].tool.arguments.cwd = state.session.cwd;
    provider.events[0].tool.call_id = 'unknown';
    assert.throws(() => normalize(bytes(rows), state, provider), /PROVIDER_ROLLOUT_TOOL_CONFLICT/);
  });

  test(`${implementation}: summaries with expansion, comments or ambiguous operators fail closed`, () => {
    for (const prefix of ['echo $HOME', 'echo $(uname)', 'echo `uname`', 'echo x # comment',
      'echo x; echo y', 'echo x | cat', 'echo x > out', 'echo *', 'echo x &&', 'echo "unterminated', 'echo x\necho y']) {
      const { rows, provider } = staticSearchFixture(`${prefix} && rg -c "CVE-2021-44228" "/tmp/another run/log.txt"`);
      assert.throws(() => normalize(bytes(rows), state, provider), /PROVIDER_ROLLOUT_TOOL_CONFLICT/);
    }
    for (const suffix of [' && echo later', ' || echo fallback', '; echo later', ' > out']) {
      const initial = staticSearchFixture();
      const { rows, provider } = staticSearchFixture(initial.command + suffix);
      assert.throws(() => normalize(bytes(rows), state, provider), /PROVIDER_ROLLOUT_TOOL_CONFLICT/);
    }
    for (const separator of ['\u00a0', '\v', '\0']) {
      const { rows, provider } = staticSearchFixture(`true && rg${separator}-c${separator}"CVE-2021-44228"${separator}"/tmp/another run/log.txt"`);
      assert.throws(() => normalize(bytes(rows), state, provider), /PROVIDER_ROLLOUT_TOOL_CONFLICT/);
    }
  });
}
