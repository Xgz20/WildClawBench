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
test('v1 cannot smuggle an unverified executor and v2 requires a scoped loopback channel',()=>{
  const f=fixture();
  assert.throws(()=>f.exports.install({...f.spec,native_executor:{launch:{url:'ws://127.0.0.1:7777/'+'a'.repeat(64)}}}),/NATIVE_CONTRACT/);
  assert.throws(()=>f.exports.install({...f.spec,contract:'macos-seatbelt-astudio-native-executor/v2'}),/NATIVE_EXECUTOR_REQUIRED/);
  assert.throws(()=>f.exports.install({...f.spec,contract:'macos-seatbelt-astudio-native-executor/v2',astudio_scope:{},
    native_executor:{launch:{url:'ws://example.invalid:7777/'+'a'.repeat(64)}}}),/NATIVE_EXECUTOR_REQUIRED/);
  assert.equal(f.calls.length,0);
});
test('a scoped backend redirects only its native data homes and preserves login/IPC environment',()=>{
  for(const contract of ['macos-seatbelt-astudio-backend/v1','macos-seatbelt-astudio-native-executor/v2']){
  const calls=[],exports={},paths={runtime:'/Users/synthetic/debug/unit/runtime',desktop:'/Users/synthetic/debug/unit/runtime/desktop',
    acode:'/Users/synthetic/debug/unit/runtime/source-home',temp:'/Users/synthetic/debug/unit/runtime/tmp'};
  const saved={unit_id:'unit1',paths},profile=Buffer.from('(version 1)'),scopeBytes=Buffer.from(JSON.stringify(saved));
  const cp={spawn(...args){calls.push(args);return {pid:123}},execFileSync(){return app+' '+entry}};
  vm.runInNewContext(source,{exports,process:{execPath:app,stderr:{write(){}}},Date,
    require:n=>({'node:fs':{realpathSync:p=>p,readFileSync:(p,encoding)=>{
      const value=p.endsWith('scope.json')?scopeBytes:profile;return encoding?value.toString(encoding):value;
    }},'node:crypto':{createHash},'node:child_process':cp,'node:module':{syncBuiltinESMExports(){}}})[n]});
  // Frozen JSON sorts keys; ordering must not make an equivalent scope fail.
  const astudio_scope={contract:'astudio-case-memory-unit/v1',scope:'/Users/synthetic/debug/unit/scope.json',unit_id:'unit1',
    scope_sha256:createHash('sha256').update(scopeBytes).digest('hex'),paths:Object.fromEntries(Object.entries(paths).reverse())};
  const spec={contract,profile:'/Users/synthetic/profile.sb',
    profile_sha256:createHash('sha256').update(profile).digest('hex'),astudio_scope};
  if(contract.endsWith('/v2'))spec.native_executor={launch:{url:'ws://127.0.0.1:7777/'+'a'.repeat(64)}};
  exports.install(spec);
  const options={env:{ELECTRON_RUN_AS_NODE:'1',ASTUDIO_HOME:paths.desktop,ASTUDIO_ACODE_HOME:'/ordinary',HOME:'/Users/synthetic',existing:'keep'},stdio:['ignore','pipe','pipe','ipc']};
  cp.spawn(app,[entry],options);
  assert.equal(calls[0][2].env.ASTUDIO_ACODE_HOME,paths.acode);
  assert.equal(calls[0][2].env.ACODE_HOME,paths.acode);
  assert.equal(calls[0][2].env.TMPDIR,paths.temp+'/');
  assert.equal(calls[0][2].env.HOME,'/Users/synthetic');
  assert.equal(calls[0][2].env.existing,'keep');
  assert.equal(calls[0][2].stdio,options.stdio);
  assert.equal(options.env.ASTUDIO_ACODE_HOME,'/ordinary');
  assert.equal(calls[0][2].env.ACODE_EXEC_SERVER_URL,spec.native_executor?.launch.url);
  assert.equal(options.env.ACODE_EXEC_SERVER_URL,undefined);
  assert.throws(()=>cp.spawn(app,[entry],{env:{...options.env,ASTUDIO_HOME:'/foreign'}}),/UNIT_ENVIRONMENT_REJECTED/);
  assert.equal(calls.length,1);
  }
});
