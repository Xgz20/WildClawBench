import assert from 'node:assert/strict';
import test from 'node:test';
import { reconcileNativeSearchDisplays, reconcileNativeGuiDisplays, reconcileNativePlatformNotices } from '../../tools/report/e2e-shared/doubaowork/search-displays.mjs';
const call=(id,query='q')=>({kind:'assistant_tool_call',call_id:id,tool_name:'general_search',arguments:{query}});
const result=id=>({kind:'tool_result',call_id:id,content:'exact model-visible protocol output'});
const card=id=>({block_id:id,block_type:10025,is_finish:true,content:{pc_event_block:'',search_query_result_block:{queries:['q'],results:[{text_card:{url:'https://example.com/ui-preview',title:'UI preview'}}]}}});
test('search cards reconcile input multiplicity while preserving model-result provenance',()=>{
 const p=reconcileNativeSearchDisplays([card('b1'),card('b2')],[call('c1'),result('c1'),call('c2'),result('c2')]);
 assert.deepEqual(p.matched_block_ids,['b1','b2']);assert.match(p.mapping,/individual-result mapping is not asserted/);
 assert.deepEqual(p.matches[0].call_ids,['c1','c2']);
});
test('missing, duplicated, unfinished or foreign projection evidence remains unknown',()=>{
 assert.equal(reconcileNativeSearchDisplays([card('b1')],[call('c1'),result('c1'),call('c2'),result('c2')]).matched_block_ids.length,0);
 assert.equal(reconcileNativeSearchDisplays([card('b1')],[call('c1')]).matched_block_ids.length,0);
 assert.equal(reconcileNativeSearchDisplays([card('b1')],[call('c1'),result('c1'),result('c1')]).matched_block_ids.length,0);
 for(const b of [{...card('b1'),is_finish:false},{...card('b1'),content:{...card('b1').content,unknown_tool_block:{}}}])
  assert.equal(reconcileNativeSearchDisplays([b],[call('c1'),result('c1')]).matched_block_ids.length,0);
});
test('fetch cards require the exact requested URL and a native result',()=>{
 const b={block_id:'b',block_type:10006,is_finish:true,content:{link_reader_block:{summary:'已阅读内容: https://example.com/a',items:[{summary:'presentation chunk'}]}}};
 const c={kind:'assistant_tool_call',call_id:'c',tool_name:'web.fetch',arguments:{url:'https://example.com/a'}};
 assert.deepEqual(reconcileNativeSearchDisplays([b],[c,result('c')]).matched_block_ids,['b']);
 assert.equal(reconcileNativeSearchDisplays([b],[{...c,arguments:{url:'https://example.com/b'}},result('c')]).matched_block_ids.length,0);
 const stale={...b,content:{link_reader_block:{summary:'正在阅读内容: https://example.com/a',tool_name:'web.fetch',url:'https://example.com/a',items:[]}}};
 assert.deepEqual(reconcileNativeSearchDisplays([stale],[c,{...result('c'),content:'native fetch error'}]).matched_block_ids,['b']);
 stale.content.link_reader_block.url='https://example.com/other';
 assert.equal(reconcileNativeSearchDisplays([stale],[c,result('c')]).matched_block_ids.length,0);
});
test('finished GUI cards reconcile exact native tool names and multiplicities',()=>{
 const b={block_id:'b',block_type:10068,is_finish:true,content:{gui_tool_block:{tool_name:'Wait',header:{summary:'等待'}},pc_event_block:''}};
 const p={calls:[{call_id:'c',name:'Wait'}]};
 assert.deepEqual(reconcileNativeGuiDisplays([b],p).matched_block_ids,['b']);
 assert.equal(reconcileNativeGuiDisplays([b],{calls:[]}).matched_block_ids.length,0);
 assert.equal(reconcileNativeGuiDisplays([b,b],p).matched_block_ids.length,0);
 assert.equal(reconcileNativeGuiDisplays([{...b,is_finish:false}],p).matched_block_ids.length,0);
});

test('a URL-less preview still requires exact query multiplicity and the complete SDK result',()=>{
 const b=card('b');b.content.search_query_result_block.results=[{text_card:{title:'UI title',doc_id:'native-preview-id',index:6}}];
 assert.deepEqual(reconcileNativeSearchDisplays([b],[call('c'),result('c')]).matched_block_ids,['b']);
 delete b.content.search_query_result_block.results[0].text_card.doc_id;
 assert.equal(reconcileNativeSearchDisplays([b],[call('c'),result('c')]).matched_block_ids.length,0);
});
test('a collapsed fetch preview requires explicit matching URL, known render mode and original result',()=>{
 const b={block_id:'b',block_type:10006,is_finish:true,content:{link_reader_block:{
  summary:'已阅读内容: https://example.com/a',tool_name:'web.fetch',url:'https://example.com/a',extend_fields:{search_result_render_type:2}}}};
 const c={kind:'assistant_tool_call',call_id:'c',tool_name:'web.fetch',arguments:{url:'https://example.com/a'}};
 assert.deepEqual(reconcileNativeSearchDisplays([b],[c,result('c')]).matched_block_ids,['b']);
 delete b.content.link_reader_block.extend_fields;
 assert.equal(reconcileNativeSearchDisplays([b],[c,result('c')]).matched_block_ids.length,0);
});
test('empty scholar labels are only projections and never erase nonempty original model results',()=>{
 const b=id=>({block_id:id,block_type:10025,is_finish:true,content:{search_query_result_block:{
  summary:'没有搜索到相关结果',scene:1,search_type:4,extend_fields:{search_result_render_type:1},queries:[],results:[]}}});
 const c=id=>({kind:'assistant_tool_call',call_id:id,tool_name:'execute_defer_tool',arguments:{toolName:'seed_scholar_search',params:{query:'original '+id}}});
 const events=[c('c1'),result('c1'),c('c2'),result('c2')];
 assert.deepEqual(reconcileNativeSearchDisplays([b('b1'),b('b2')],events).matched_block_ids,['b1','b2']);
 assert.match(reconcileNativeSearchDisplays([b('b1'),b('b2')],events).matches[0].mapping,/does not determine/);
 assert.equal(reconcileNativeSearchDisplays([b('b1')],events).matched_block_ids.length,0);
 assert.equal(reconcileNativeSearchDisplays([b('b1'),b('b2')],events.slice(0,3)).matched_block_ids.length,0);
 const bad=b('b2');bad.content.search_query_result_block.results=[{unaccounted:'data'}];
 assert.equal(reconcileNativeSearchDisplays([b('b1'),bad],events).matched_block_ids.length,0);
});
test('only the exact completed platform investment disclaimer is a known notice',()=>{
 const b={block_id:'b',block_type:10053,is_finish:true,content:{tips_block:{type:1,text:'\n本回答由AI生成，仅供参考，请仔细甄别，谨慎投资。'},pc_event_block:''}};
 assert.deepEqual(reconcileNativePlatformNotices([b]).matched_block_ids,['b']);
 assert.equal(reconcileNativePlatformNotices([{...b,is_finish:false}]).matched_block_ids.length,0);
 assert.equal(reconcileNativePlatformNotices([{...b,content:{tips_block:{type:1,text:'unknown message'}}}]).matched_block_ids.length,0);
 assert.equal(reconcileNativePlatformNotices([b,b]).matched_block_ids.length,0);
});
