import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const source=readFileSync(new URL('../../eval_memory_e2e/native/seatbelt-spawn-guard.cjs',import.meta.url),'utf8');
const app='/Applications/AStudio.app/Contents/MacOS/AStudio';
const entry='/Applications/AStudio.app/Contents/Resources/app.asar/apps/server/dist/index.mjs';
function fixture(){
  let bytes=Buffer.from('(version 1)'),syncs=0;const calls=[],exports={};
  const cp={spawn(...args){calls.push(args);return {pid:123}},execFileSync(){return app+' --max-old-space-size=6144 '+entry}};
  const fs={realpathSync:p=>p,readFileSync:()=>bytes};
  const crypto={createHash};
  const context={exports,process:{execPath:app,stderr:{write(){}}},Date,
    require:n=>({'node:fs':fs,'node:crypto':crypto,'node:child_process':cp,'node:module':{syncBuiltinESMExports(){syncs++}}})[n]};
  vm.runInNewContext(source,context);
  const spec={contract:'macos-seatbelt-astudio-backend/v1',profile:'/Users/synthetic/profile.sb',profile_sha256:createHash('sha256').update(bytes).digest('hex')};
  return {cp,calls,exports,spec,mutate(){bytes=Buffer.from('changed')},syncs:()=>syncs};
}
test('only the exact installed Node backend spawn is wrapped; args/env/stdio/IPC stay intact',()=>{
  const f=fixture();assert.equal(f.exports.install(f.spec).installed,true);assert.equal(f.syncs(),1);
  const options={env:{ELECTRON_RUN_AS_NODE:'1',existing:'keep'},stdio:['ignore','pipe','pipe','ipc']};
  f.cp.spawn(app,['--max-old-space-size=6144',entry],options);
  assert.equal(f.calls[0][0],'/usr/bin/sandbox-exec');
  assert.deepEqual(Array.from(f.calls[0][1]),['-f',f.spec.profile,app,'--max-old-space-size=6144',entry]);
  assert.equal(f.calls[0][2],options);
  assert.ok(!f.calls[0][1].some(x=>x==='--no-sandbox'||x==='--disable-gpu-sandbox'));
});
test('renderer/helper and unrelated process spawns are delegated unchanged',()=>{
  const f=fixture();f.exports.install(f.spec);
  const args=['--type=renderer'],options={env:{original:true}};
  f.cp.spawn(app,args,options);f.cp.spawn('/bin/echo',['fixture'],{});
  assert.equal(f.calls[0][0],app);assert.equal(f.calls[0][1],args);assert.equal(f.calls[0][2],options);
  assert.equal(f.calls[1][0],'/bin/echo');
});
test('drift and a wrong backend execution mode stop before any spawn',()=>{
  const f=fixture();assert.throws(()=>f.exports.install({...f.spec,profile_sha256:'0'.repeat(64)}),/SPEC_UNVERIFIED/);
  f.exports.install(f.spec);
  assert.throws(()=>f.cp.spawn(app,[entry],{env:{}}),/SPAWN_REJECTED/);
  f.mutate();assert.throws(()=>f.cp.spawn(app,[entry],{env:{ELECTRON_RUN_AS_NODE:'1'}}),/SPAWN_REJECTED/);
  assert.equal(f.calls.length,0);
});
