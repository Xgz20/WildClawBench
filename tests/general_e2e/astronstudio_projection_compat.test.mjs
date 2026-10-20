import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { normalizeRolloutTranscript as canonical } from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout-transcript.mjs';
import { normalizeRolloutTranscript as vendored } from '../../tools/report/skills/general-e2e/collect-general-e2e/vendor/e2e-shared/general-resource-supplements/astronstudio-rollout-transcript.mjs';

const prompt = 'Synthetic projection fixture.';
const state = {identity: {batch_id: 'batch', unit_id: 'unit', task_id: 'task', attempt_id: 'attempt'},
  phase: 'COMPLETED', prompt: {send_status: 'sent', sha256: createHash('sha256').update(prompt).digest('hex')},
  session: {verified: true, session_id: 'session', turn_id: 'turn', cwd: '/tmp/synthetic-workspace'}};
const row = (type,payload) => ({type,timestamp: '2026-10-20T00:00:00Z',payload});
function sdk(name,args,output) {
  return [row('session_meta',{id:'session',cwd:state.session.cwd}),
    row('event_msg',{type:'task_started',turn_id:'turn'}),row('turn_context',{turn_id:'turn',cwd:state.session.cwd}),
    row('event_msg',{type:'user_message',message:prompt}),
    row('response_item',{type:'function_call',name,call_id:'call',arguments:JSON.stringify(args)}),
    row('response_item',{type:'function_call_output',call_id:'call',output}),
    row('response_item',{type:'message',role:'assistant',content:[{type:'output_text',text:'Finished.'}]}),
    row('event_msg',{type:'task_complete',turn_id:'turn',duration_ms:100,last_agent_message:'Finished.'})];
}
const bytes = rows => Buffer.from(rows.map(r=>JSON.stringify(r)).join('\n')+'\n');
function commandFixture(tool='bash',login=false,workdir=state.session.cwd) {
  const args = {[tool==='bash'?'command':'cmd']:'pwd',login,workdir};
  const output = tool==='bash' ? 'Exit code: 0\nWall time: 0.1 seconds\nOutput:\nok\n'
    : 'Chunk ID: chunk\nWall time: 0.1 seconds\nProcess exited with code 0\nOriginal token count: 1\nOutput:\nok\n';
  return {rows:sdk(tool,args,output),provider:{calls:[{call_id:'call'}],events:[
    {type:'tool_call',tool:{name:'command',call_id:'call',arguments:{command:`/bin/zsh ${login?'-lc':'-c'} 'pwd'`,cwd:workdir,command_actions:[{command:'pwd'}]}}},
    {type:'tool_result',tool:{name:'command',call_id:'call',result:{exit_code:0,output:'ok\n',duration_ms:100}}}]}};
}
function artifactFixture(tool='astron_publish_artifact') {
  const success=tool==='astron_publish_artifact', args={path:'result.txt'}, output=success?'Published.':'Target exists.';
  const raw=(event_type,line,item)=>({event_type,raw_line:line,event:{payload:{data:{item}}}});
  const common={type:'dynamicToolCall',namespace:'acode_artifacts',tool,id:'call',arguments:args};
  const start=raw('item.started',10,{...common,status:'inProgress'});
  const end=raw('item.completed',11,{...common,status:success?'completed':'failed',success,durationMs:5,
    contentItems:[{type:'inputText',text:output}]});
  return {rows:sdk(`acode_artifacts__${tool}`,args,output),provider:{projection_rows:[start,end],calls:[{call_id:'call'}],events:[
    {type:'tool_call',source:{raw_ref:'raw/astronstudio-provider-events.jsonl#L10'},tool:{name:tool,call_id:'call',arguments:args}},
    {type:'tool_result',source:{raw_ref:'raw/astronstudio-provider-events.jsonl#L11'},tool:{name:tool,call_id:'call',result:{
      status:success?'completed':'failed',duration_ms:5,error:null,result:null,server:null,plugin_id:null}}}]}};
}

for (const [name,normalize] of [['canonical',canonical],['vendored',vendored]]) {
  const run = f => normalize(bytes(f.rows),state,f.provider);
  test(`${name}: explicit login flags and canonical in-workspace cwd preserve native SDK events`,()=>{
    for (const tool of ['bash','exec_command']) for (const login of [false,true]) {
      const f=commandFixture(tool,login,state.session.cwd+'/subdir');
      const result=run(f);
      assert.equal(result.completeness.status,'complete');
      assert.equal(result.events.find(e=>e.type==='tool_call').tool.name,tool);
      assert.deepEqual(result.events,normalize(bytes(f.rows),state,{events:[],calls:[]}).events);
    }
  });
  for (const [label,mutate] of [
    ['login-flag',f=>{f.provider.events[0].tool.arguments.command="/bin/zsh -lc 'pwd'";}],
    ['login-type',f=>{const a=JSON.parse(f.rows[4].payload.arguments);a.login='false';f.rows[4].payload.arguments=JSON.stringify(a);}],
    ['declared-shell',f=>{const a=JSON.parse(f.rows[4].payload.arguments);a.shell='/bin/bash';f.rows[4].payload.arguments=JSON.stringify(a);}],
    ['unknown-shell',f=>{f.provider.events[0].tool.arguments.command="/tmp/zsh -c 'pwd'";}],
    ['command-edit',f=>{f.provider.events[0].tool.arguments.command+="; touch /tmp/unbound";}],
    ['summary-edit',f=>{f.provider.events[0].tool.arguments.command_actions[0].command='other';}],
    ['output-edit',f=>{f.provider.events[1].tool.result.output='other';}],
    ['exit-edit',f=>{f.provider.events[1].tool.result.exit_code=1;}],
    ['timing-edit',f=>{f.provider.events[1].tool.result.duration_ms=999;}],
    ['cwd-disagreement',f=>{f.provider.events[0].tool.arguments.cwd+='/other';}],
    ['missing-workdir',f=>{const a=JSON.parse(f.rows[4].payload.arguments);delete a.workdir;f.rows[4].payload.arguments=JSON.stringify(a);}],
    ...['/tmp/outside','/tmp/synthetic-workspace-other','relative','/tmp/synthetic-workspace/../outside','/tmp/synthetic-workspace/./subdir','/tmp/synthetic-workspace/subdir/'].map(cwd=>
      ['cwd:'+cwd,f=>{const a=JSON.parse(f.rows[4].payload.arguments);a.workdir=cwd;f.rows[4].payload.arguments=JSON.stringify(a);f.provider.events[0].tool.arguments.cwd=cwd;}]),
  ]) test(`${name}: command rejects ${label}`,()=>{
    for(const tool of ['bash','exec_command']) {const f=commandFixture(tool,false,state.session.cwd+'/subdir');mutate(f);assert.throws(()=>run(f),/PROVIDER_ROLLOUT_TOOL_/);}
  });
  for (const tool of ['astron_publish_artifact','astron_allocate_artifact']) {
    test(`${name}: exact ${tool} projection preserves raw output and unknown SDK status`,()=>{
      const f=artifactFixture(tool),result=run(f);
      assert.equal(result.completeness.status,'complete');
      assert.deepEqual(result.events,normalize(bytes(f.rows),state,{events:[],calls:[]}).events);
      const returned=result.events.find(e=>e.type==='tool_result');
      assert.equal(returned.tool.status,'unknown');
      assert.equal(returned.tool.result,f.rows[5].payload.output);
    });
    for(const [label,mutate] of [
      ['missing-raw',f=>{delete f.provider.projection_rows;}],
      ['duplicate-raw',f=>{f.provider.projection_rows.push(structuredClone(f.provider.projection_rows[0]));}],
      ['namespace',f=>{f.provider.projection_rows[0].event.payload.data.item.namespace='untrusted';}],
      ['tool-name',f=>{f.provider.projection_rows[1].event.payload.data.item.tool='other';}],
      ['call-id',f=>{f.provider.projection_rows[1].event.payload.data.item.id='other';}],
      ['arguments',f=>{f.provider.projection_rows[1].event.payload.data.item.arguments={other:true};}],
      ['event-type',f=>{f.provider.projection_rows[1].event_type='item.started';}],
      ['item-type',f=>{f.provider.projection_rows[1].event.payload.data.item.type='mcpToolCall';}],
      ['status',f=>{f.provider.projection_rows[1].event.payload.data.item.status='unknown';}],
      ['opposite-profile',f=>{const item=f.provider.projection_rows[1].event.payload.data.item;item.success=!item.success;
        item.status=item.success?'completed':'failed';f.provider.events[1].tool.result.status=item.status;}],
      ['success-flip',f=>{f.provider.projection_rows[1].event.payload.data.item.success=!f.provider.projection_rows[1].event.payload.data.item.success;}],
      ['text-edit',f=>{f.provider.projection_rows[1].event.payload.data.item.contentItems[0].text+='x';}],
      ['content-type',f=>{f.provider.projection_rows[1].event.payload.data.item.contentItems[0].type='image';}],
      ['extra-content',f=>{f.provider.projection_rows[1].event.payload.data.item.contentItems.push({type:'inputText',text:'extra'});}],
      ['error',f=>{f.provider.projection_rows[1].event.payload.data.item.error='unseen';}],
      ['duration',f=>{f.provider.events[1].tool.result.duration_ms=6;}],
      ['negative-duration',f=>{f.provider.projection_rows[1].event.payload.data.item.durationMs=-1;}],
      ['projected-error',f=>{f.provider.events[1].tool.result.error='unseen';}],
      ['projected-result',f=>{f.provider.events[1].tool.result.result='unseen';}],
      ['projected-server',f=>{f.provider.events[1].tool.result.server='untrusted';}],
      ['projected-plugin',f=>{f.provider.events[1].tool.result.plugin_id='untrusted';}],
      ['projected-status',f=>{f.provider.events[1].tool.result.status='unknown';}],
      ['raw-reference',f=>{f.provider.events[1].source.raw_ref='raw/astronstudio-provider-events.jsonl#L99';}],
    ]) test(`${name}: ${tool} rejects ${label}`,()=>{
      const f=artifactFixture(tool);mutate(f);assert.throws(()=>run(f),/PROVIDER_ROLLOUT_TOOL_CONFLICT/);
    });
  }
  test(`${name}: artifact compatibility rejects empty failed output and unknown aliases`,()=>{
    const empty=artifactFixture('astron_allocate_artifact');
    empty.rows[5].payload.output='';empty.provider.projection_rows[1].event.payload.data.item.contentItems[0].text='';
    assert.throws(()=>run(empty),/PROVIDER_ROLLOUT_TOOL_CONFLICT/);
    const unknown=artifactFixture();unknown.rows[4].payload.name='unknown__astron_publish_artifact';
    assert.throws(()=>run(unknown),/PROVIDER_ROLLOUT_TOOL_CONFLICT/);
  });
}
