import test from 'node:test';
import assert from 'node:assert/strict';
import {metricDisplay, scoreOrder, tokenComparison, timingComparison, pairedTokens, TIMING_HEADERS} from '../tools/report/skills/web-e2e/report-web-e2e/scripts/report-presentation.mjs';

function unit(name, total, subtotal = total, covered = 2, partial = 0) {
  return {unit:name,case_count:2,total_tokens:total,resource_metrics:{total_tokens:{total,known_subtotal:subtotal,covered_cases:covered,total_cases:2,partial_cases:partial}}};
}
function row(name, input, cached, written, statuses = {}) {
  return {unit:name,resource_metrics:{input_tokens:input,cache_read_input_tokens:cached,cache_creation_input_tokens:written},resource_collection:{metrics:Object.fromEntries(['input_tokens','cache_read_input_tokens','cache_creation_input_tokens'].map(key=>[key,{status:statuses[key]??'observed'}]))}};
}

test('总分排序保留真实零分且将缺失置末，不改原单元顺序',()=>{
  const rows=[{unit:'unknown',total_average_score:null},{unit:'zero',total_average_score:0},{unit:'best',total_average_score:95}];
  assert.deepEqual(scoreOrder(rows).map(x=>x.unit),['best','zero','unknown']);
  assert.equal(rows[0].unit,'unknown');
});
test('部分Token使用有标识小计和冻结题数，正式总量保持null且缺失不补零',()=>{
  const p=unit('partial',null,300,1,1),missing=unit('missing',null,null,0),zero=unit('zero',0);
  const view=tokenComparison({units:[missing,p,zero],detail_rows:[]});
  assert.deepEqual(view.units.map(x=>x.unit),['zero','partial','missing']);
  assert.deepEqual(view.rows.map(x=>x.slice(1,3)),[[0,0],[300,150],[null,null]]);
  assert.equal(view.cells[1][0].partial,true);
  assert.equal(view.cells[1][1].partial,true);
  assert.equal(p.resource_metrics.total_tokens.total,null);
  assert.deepEqual(metricDisplay(missing,'total_tokens'),{value:null,partial:false});
});
test('普通输入扣减命中和已观测写入，命中率分母包含缓存',()=>{
  const u=unit('a',200), rows=[row('a',100,60,10),row('a',200,100,20)];
  assert.deepEqual(pairedTokens(u,rows,['input_tokens','cache_read_input_tokens','cache_creation_input_tokens']),{value:110,partial:false});
  assert.deepEqual(pairedTokens(u,rows,['input_tokens','cache_read_input_tokens'],true),{value:160/300,partial:false});
});
test('不可用的零写入不当作实测零，不从不配对题目计算比率',()=>{
  const u=unit('a',200),rows=[row('a',100,60,0,{cache_creation_input_tokens:'unavailable'}),row('a',200,100,0,{cache_creation_input_tokens:'unavailable'})];
  assert.equal(pairedTokens(u,rows,['input_tokens','cache_read_input_tokens','cache_creation_input_tokens']).value,null);
  const disjoint=[row('a',100,null,null),row('a',null,60,null)];
  assert.equal(pairedTokens(u,disjoint,['input_tokens','cache_read_input_tokens'],true).value,null);
});
test('部分配对小计保留标识，unverified和缓存超过输入不进入派生量',()=>{
  const u=unit('a',200),p=row('a',null,null,null,{input_tokens:'partial',cache_read_input_tokens:'partial'});
  p.resource_collection.known_subtotals={input_tokens:100,cache_read_input_tokens:60};
  assert.deepEqual(pairedTokens(u,[p],['input_tokens','cache_read_input_tokens'],true),{value:0.6,partial:true});
  assert.equal(pairedTokens(u,[row('a',100,101,0)],['input_tokens','cache_read_input_tokens'],true).value,null);
  assert.equal(pairedTokens(u,[row('a',100,60,0,{input_tokens:'unverified'})],['input_tokens','cache_read_input_tokens'],true).value,null);
});
test('耗时升序不按Token排序，未知耗时置末且不推断小计为完整耗时',()=>{
  const rows=[{unit:'missing',total_duration_seconds:1},{unit:'long',total_agent_duration_seconds:20,total_duration_seconds:2},{unit:'zero',total_agent_duration_seconds:0,total_duration_seconds:999}];
  assert.deepEqual(timingComparison({units:rows}).units.map(x=>x.unit),['zero','long','missing']);
});
test('任务耗时从逐题原生值计算，流程耗时分位数不参与',()=>{
  const u={unit:'a',case_count:4,total_agent_duration_seconds:106,total_duration_seconds:4000,average_duration_seconds:1000,duration_p50_seconds:1000,duration_p90_seconds:1000};
  const detail=[1,2,3,100].map(value=>({unit:'a',resource_metrics:{agent_duration_seconds:value,duration_seconds:1000},resource_collection:{metrics:{agent_duration_seconds:{status:'observed'}}}}));
  const view=timingComparison({units:[u],detail_rows:detail});
  assert.deepEqual(TIMING_HEADERS,['模型@Harness','任务耗时(s)','平均任务耗时(s)','任务耗时P50(s)','任务耗时P90(s)']);
  assert.deepEqual(view.rows[0].slice(1,4),[106,26.5,2.5]);
  assert.ok(Math.abs(view.rows[0][4]-70.9)<1e-9);
  assert.equal(u.total_duration_seconds,4000);
  assert.throws(()=>timingComparison({units:[{...u,total_agent_duration_seconds:105}],detail_rows:detail}),/TASK_TIMING_TOTAL_MISMATCH/);
});
test('任务计时缺失不借用流程值，部分小计不补分位数，真实零保留',()=>{
  const missing={unit:'missing',case_count:2,total_duration_seconds:1000};
  assert.deepEqual(timingComparison({units:[missing],detail_rows:[]}).rows[0].slice(1),[null,null,null,null]);
  const partial={unit:'partial',case_count:2,resource_metrics:{agent_duration_seconds:{total:null,known_subtotal:10,covered_cases:1,total_cases:2,partial_cases:1}}};
  const p=timingComparison({units:[partial],detail_rows:[]});
  assert.deepEqual(p.rows[0].slice(1),[10,5,null,null]);assert.equal(p.cells[0][1].partial,true);
  const zero={unit:'zero',case_count:2,total_agent_duration_seconds:0};
  const detail=[0,0].map(value=>({unit:'zero',resource_metrics:{agent_duration_seconds:value},resource_collection:{metrics:{agent_duration_seconds:{status:'observed'}}}}));
  assert.deepEqual(timingComparison({units:[zero],detail_rows:detail}).rows[0].slice(1),[0,0,0,0]);
});
