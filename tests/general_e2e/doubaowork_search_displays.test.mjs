import assert from 'node:assert/strict';
import test from 'node:test';
import { reconcileNativeSearchDisplays, reconcileNativeGuiDisplays } from '../../tools/report/e2e-shared/doubaowork/search-displays.mjs';
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
