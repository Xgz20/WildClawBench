import test from 'node:test';
import assert from 'node:assert/strict';
import {collectNativeSnapshots} from '../native-snapshots.mjs';
const targets=[1,2,3].map(n=>({threadId:'thread-'+n,hostId:'local',afterCursor:'old'}));
function raw(t,status='inProgress'){return {content:[{type:'text',text:JSON.stringify({polls:[{thread:{id:t.threadId,hostId:t.hostId},cursor:'fresh-'+t.threadId,latestTurn:{status}}]})}]}}
test('snapshot each native target without old cursors; preserve raw results',async()=>{
  const calls=[];const results=await collectNativeSnapshots(async args=>{calls.push(args);assert.equal(args.targets.length,1);assert.equal(args.timeoutMs,0);assert.equal(args.targets[0].afterCursor,undefined);return raw(args.targets[0],args.targets[0].threadId==='thread-1'?'completed':'inProgress')},targets);
  assert.equal(calls.length,3);assert.equal(results.length,3);assert.equal(results[0].poll.latestTurn.status,'completed');assert.equal(results[1].poll.latestTurn.status,'inProgress');assert.ok(results.every(r=>r.raw.content));
});
test('missing or wrong native identity never releases a slot',async()=>{
  await assert.rejects(collectNativeSnapshots(async()=>({polls:[]}),targets),/INCOMPLETE/);
  await assert.rejects(collectNativeSnapshots(async()=>raw({threadId:'wrong',hostId:'local'}),targets),/BINDING/);
});
test('duplicate targets and partial tool errors fail closed',async()=>{
  await assert.rejects(collectNativeSnapshots(async()=>{},[targets[0],targets[0]]),/DUPLICATE/);
  await assert.rejects(collectNativeSnapshots(async()=>({isError:true}),targets),/TOOL_ERROR/);
});
