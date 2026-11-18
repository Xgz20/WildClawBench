import{test}from'node:test';import assert from'node:assert/strict';
import{analyzeWorkBuddy}from'../../tools/report/e2e-shared/general-resource-supplements/agentcube-workbuddy-binding.mjs';
function fixture(){const cwd='C:\\ProgramData\\WGUI\\workspace\\project',prompt='Do the task';const providerData={messageId:'m1',conversationRequestId:'r1',requestModelName:'GLM-5.3',usage:{requests:1,inputTokens:100,outputTokens:10,totalTokens:110},rawUsage:{prompt_tokens:100,completion_tokens:10,total_tokens:110,prompt_tokens_details:{cached_tokens:50}}};
 const rows=[{type:'message',role:'user',content:[{type:'input_text',text:'<user_query>'+prompt+'</user_query>'}],timestamp:'2026-11-17T00:00:00Z'},{type:'function_call',callId:'call1',name:'Read',arguments:'{}',providerData,timestamp:'2026-11-17T00:00:00.100Z'},{type:'function_call_result',callId:'call1',content:'data',timestamp:'2026-11-17T00:00:00.200Z'},{type:'message',role:'assistant',content:[{type:'output_text',text:'Done'}],status:'completed',providerData:{...providerData,messageId:'m2'},timestamp:'2026-11-17T00:00:01Z'}].map(x=>({sessionId:'session-123456',cwd,...x}));
 const options={identity:{batch_id:'b',unit_id:'u',task_id:'t',attempt_id:'a'},prompt,guest_cwd:cwd,requested_model:'GLM-5.3',raw_name:'s.jsonl',report:{schema_version:2,status:'completed'},product_report:{product_report:true,workflow:{workspace:cwd,model:'GLM-5.3'}},diagnostics:{model:'GLM-5.3',workspace:cwd,max_mode:false}};return {rows,options,bytes:()=>Buffer.from(rows.map(x=>JSON.stringify(x)).join('\n'))};}
test('bind native model, user, tools, final and deduplicated usage',()=>{const f=fixture(),b=analyzeWorkBuddy(f.bytes(),f.options);assert.deepEqual(b.missing,[]);assert.deepEqual(b.calls,[{call_id:'call1',call_sequence:1,result_sequence:2}]);assert.equal(b.native_resources.metrics.usage.total_tokens.value,220);assert.equal(b.final_response,'Done');});
test('reject cross-workspace, wrong prompt/model, unverified Max and incomplete native terminal',()=>{for(const kind of ['cwd','prompt','model','max','terminal']){const f=fixture();if(kind==='cwd')f.rows[1].cwd='C:\\other';if(kind==='prompt')f.options.prompt='different';if(kind==='model')f.rows[1].providerData.requestModelName='different';if(kind==='max')f.options.requested_max_mode=true;if(kind==='terminal')delete f.rows.at(-1).status;assert.throws(()=>analyzeWorkBuddy(f.bytes(),f.options),/WORKBUDDY_/);}});
test('missing raw provider counters remain unknown instead of normalized zero',()=>{const f=fixture();for(const row of f.rows)if(row.providerData){delete row.providerData.rawUsage;row.providerData.usage={requests:1,inputTokens:0,outputTokens:0,totalTokens:0}};assert.equal(analyzeWorkBuddy(f.bytes(),f.options).native_resources.metrics.usage.total_tokens.value,null);});

test('replay accepts only the observed WorkBuddy inline context newline projection', () => {
  const f = fixture();
  const prompt = '工作区公开指令（AGENTS.md）：\n\n# 范围\n只用公开资料。\n\n任务：\n\n调研指定主题';
  const prolog = '<system-reminder data-role="user-context">VM</system-reminder>\n';
  const record = (text, prefix = prolog) => [{type: 'input_text', text: prefix + '<user_query>' + text + '</user_query>'}];
  f.options = {...f.options, prompt};
  f.options.product_report.product_version = '5.9.3';
  const collapsed = prompt.replace(/\n{2,}/g, '\n');
  f.rows[0].content = record(collapsed);
  const bound = analyzeWorkBuddy(f.bytes(), f.options);
  assert.equal(bound.prompt_transport.kind, 'workbuddy-user-query-inline-context-blank-lines-collapsed');
  assert.equal(bound.prompt_transport.dropped_linefeeds, 3);
  assert.notEqual(bound.prompt_sha256, bound.prompt_transport.decoded_text_sha256);
  for (const [observed, prefix] of [[collapsed + '。', prolog], [collapsed, ''], [prompt.replaceAll('\n', ''), prolog]]) {
    f.rows[0].content = record(observed, prefix);
    assert.throws(() => analyzeWorkBuddy(f.bytes(), f.options), /WORKBUDDY_PROMPT_MISMATCH/);
  }
  f.options.prompt = prompt + '\n第二行';
  f.rows[0].content = record(collapsed + '\n第二行');
  assert.throws(() => analyzeWorkBuddy(f.bytes(), f.options), /WORKBUDDY_PROMPT_MISMATCH/);
});
