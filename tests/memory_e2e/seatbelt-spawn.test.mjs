import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const source=readFileSync(new URL('../../eval_memory_e2e/native/seatbelt-spawn-guard.cjs',import.meta.url),'utf8');
const app='/Applications/AStudio.app/Contents/MacOS/AStudio';
const entry='/Applications/AStudio.app/Contents/Resources/app.asar/apps/server/dist/index.mjs';
const installed='/Applications/AStudio.app/Contents/Resources/bin/acode-darwin-arm64';
const hash=b=>createHash('sha256').update(b).digest('hex');
function fixture({environment={},scope=null}={}){
  let bytes=Buffer.from('(version 1)'),kernel=Buffer.from('SYNTHETIC-INSTALLED-KERNEL'),syncs=0;const calls=[],exports={};
  const cp={spawn(...args){calls.push(args);return {pid:123}},execFileSync(){return app+' --max-old-space-size=6144 '+entry}};
  const fs={realpathSync:p=>p,readFileSync:(p,encoding)=>{
    const result=p===installed?kernel:p.endsWith('scope.json')?Buffer.from(JSON.stringify(scope)):bytes;
    return encoding?result.toString(encoding):result;
  }};
  vm.runInNewContext(source,{exports,process:{execPath:app,env:environment,stderr:{write(){}}},Date,
    require:n=>({'node:fs':fs,'node:crypto':{createHash},'node:child_process':cp,'node:module':{syncBuiltinESMExports(){syncs++}}})[n]});
  const spec={contract:'macos-seatbelt-astudio-backend/v1',profile:'/Users/synthetic/profile.sb',profile_sha256:hash(bytes),
    kernel:{path:installed,sha256:hash(kernel)}};
  return {cp,calls,exports,spec,mutate(){bytes=Buffer.from('changed')},mutateKernel(){kernel=Buffer.from('changed')},syncs:()=>syncs};
}
test('only the installed backend spawn is wrapped; args/env/stdio/IPC stay intact',()=>{
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
test('policy drift and wrong backend mode stop before any spawn',()=>{
  const f=fixture();assert.throws(()=>f.exports.install({...f.spec,profile_sha256:'0'.repeat(64)}),/SPEC_UNVERIFIED/);
  f.exports.install(f.spec);
  assert.throws(()=>f.cp.spawn(app,[entry],{env:{}}),/SPAWN_REJECTED/);
  f.mutate();assert.throws(()=>f.cp.spawn(app,[entry],{env:{ELECTRON_RUN_AS_NODE:'1'}}),/SPAWN_REJECTED/);
  assert.equal(f.calls.length,0);
});
test('all legacy custom executors and compiled kernels are rejected before installation',()=>{
  const f=fixture();
  for(const changed of [{native_executor:null},{compiled_kernel:null},
    {contract:'macos-seatbelt-astudio-native-executor/v2'},
    {contract:'macos-seatbelt-astudio-compiled-kernel/v3'}])
    assert.throws(()=>f.exports.install({...f.spec,...changed}),/ASTUDIO_PRODUCTION_PACKAGE_REQUIRED/);
  assert.equal(f.calls.length,0);assert.equal(f.syncs(),0);
});
test('production kernel hash and inherited overrides are checked before bootstrap and each spawn',()=>{
  for(const environment of [{ASTUDIO_ACODE_BIN:'/synthetic/custom-acode'},{ACODE_EXEC_SERVER_URL:'ws://127.0.0.1/custom'}]){
    const f=fixture({environment});
    assert.throws(()=>f.exports.install(f.spec),/ASTUDIO_PRODUCTION_PACKAGE_REQUIRED/);
    assert.equal(f.syncs(),0);
  }
  const f=fixture();f.exports.install(f.spec);
  for(const env of [{ASTUDIO_ACODE_BIN:'/synthetic/custom-acode'},{ACODE_EXEC_SERVER_URL:'ws://127.0.0.1/custom'}])
    assert.throws(()=>f.cp.spawn(app,[entry],{env:{ELECTRON_RUN_AS_NODE:'1',...env}}),/ASTUDIO_PRODUCTION_PACKAGE_REQUIRED/);
  f.mutateKernel();assert.throws(()=>f.cp.spawn(app,[entry],{env:{ELECTRON_RUN_AS_NODE:'1'}}),/ASTUDIO_PRODUCTION_PACKAGE_REQUIRED/);
  assert.equal(f.calls.length,0);
});
test('scoped production backend redirects only data homes and preserves login/IPC environment',()=>{
  const paths={runtime:'/Users/synthetic/debug/unit/runtime',desktop:'/Users/synthetic/debug/unit/runtime/desktop',
    acode:'/Users/synthetic/debug/unit/runtime/source-home',temp:'/Users/synthetic/debug/unit/runtime/tmp'};
  const saved={unit_id:'unit1',paths},f=fixture({scope:saved});
  const astudio_scope={contract:'astudio-case-memory-unit/v1',scope:'/Users/synthetic/debug/unit/scope.json',unit_id:'unit1',
    scope_sha256:hash(Buffer.from(JSON.stringify(saved))),paths:Object.fromEntries(Object.entries(paths).reverse())};
  f.exports.install({...f.spec,astudio_scope});
  const options={env:{ELECTRON_RUN_AS_NODE:'1',ASTUDIO_HOME:paths.desktop,ASTUDIO_ACODE_HOME:'/ordinary',
    ASTUDIO_ACODE_BIN:installed,HOME:'/Users/synthetic',existing:'keep'},stdio:['ignore','pipe','pipe','ipc']};
  f.cp.spawn(app,[entry],options);
  const env=f.calls[0][2].env;
  assert.equal(env.ASTUDIO_ACODE_HOME,paths.acode);assert.equal(env.ACODE_HOME,paths.acode);
  assert.equal(env.TMPDIR,paths.temp+'/');assert.equal(env.HOME,'/Users/synthetic');assert.equal(env.existing,'keep');
  assert.equal(f.calls[0][2].stdio,options.stdio);assert.equal(options.env.ASTUDIO_ACODE_HOME,'/ordinary');
  assert.equal(env.ACODE_EXEC_SERVER_URL,undefined);assert.equal(env.ASTUDIO_ACODE_BIN,installed);
  assert.throws(()=>f.cp.spawn(app,[entry],{env:{...options.env,ASTUDIO_HOME:'/foreign'}}),/UNIT_ENVIRONMENT_REJECTED/);
  assert.equal(f.calls.length,1);
});
