import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../../eval_memory_e2e/native/workbuddy-seatbelt-spawn-guard.cjs',import.meta.url),'utf8');
const app='/Applications/WorkBuddy.app/Contents/MacOS/Electron',entry='/Applications/WorkBuddy.app/Contents/Resources/app.asar/main/daemon-app-server-entry.js';
function setup(){
  const calls=[],cp={spawn(...args){calls.push(args);return {pid:100}}};
  const descriptor=name=>({path:'/Users/SYNTHETIC/unit/'+name,sha256:'fixed'});
  const spec={contract:'workbuddy-main-os-boundary/v1',main_pid:42,app_home:'/Users/SYNTHETIC/unit/app-home',temp:'/Users/SYNTHETIC/unit/tmp',
    backend_profile:descriptor('backend.sb'),center_profile:descriptor('center.sb'),gateway_spec:descriptor('gateway.json'),
    backend_guard:descriptor('guard.cjs'),center_binary:descriptor('sandbox-center'),native_cli:descriptor('sandbox-cli'),
    center_socket:'/tmp/workbuddy-sandbox-center-1234567890abcdef-42.sock',backend_inspector_port:9337};
  const exports={};
  const builtins={'node:fs':{readFileSync(){return Buffer.from('frozen')},realpathSync(p){return p}},'node:child_process':cp,
    'node:crypto':{createHash(){return {update(){return this},digest(){return 'fixed'}}}},'node:module':{syncBuiltinESMExports(){}}};
  vm.runInNewContext(source,{exports,require:name=>builtins[name],process:{execPath:app,pid:42,stderr:{write(){}}}});
  exports.install(spec);
  const env={WORKBUDDY_CONFIG_DIR:spec.app_home,CODEBUDDY_CONFIG_DIR:spec.app_home,ELECTRON_RUN_AS_NODE:'1',NATIVE_VALUE:'preserved'};
  return {cp,calls,spec,env};
}

test('WorkBuddy main guard preserves five native RPC pipes and scopes only the exact backend',()=>{
  const {cp,calls,spec,env}=setup(),stdio=['pipe','pipe','pipe','pipe','pipe'],options={stdio,env,windowsHide:true};
  const child=cp.spawn(app,[entry,'--stdio'],options);
  assert.equal(child.pid,100);assert.equal(calls.length,1);assert.equal(calls[0][0],'/usr/bin/sandbox-exec');
  assert.deepEqual(Array.from(calls[0][1]),['-f',spec.backend_profile.path,app,'--inspect=127.0.0.1:9337','--require',spec.backend_guard.path,entry,'--stdio']);
  assert.equal(calls[0][2].stdio,stdio);assert.equal(calls[0][2].env.NATIVE_VALUE,'preserved');
  assert.equal(calls[0][2].env.WCB_MEMORY_WB_GATEWAY,spec.gateway_spec.path);
  assert.equal(options.env.WCB_MEMORY_WB_GATEWAY,undefined);
});

test('foreign data homes, wrong RPC shapes and unbrokered native services are refused before spawning',()=>{
  const {cp,calls,spec,env}=setup();
  assert.throws(()=>cp.spawn(app,[entry,'--stdio'],{env:{...env,CODEBUDDY_CONFIG_DIR:'/Users/SYNTHETIC/other'},stdio:Array(5).fill('pipe')}),/DATA_HOME/);
  assert.throws(()=>cp.spawn(app,[entry,'--stdio'],{env,stdio:Array(3).fill('pipe')}),/RPC_SHAPE/);
  assert.throws(()=>cp.spawn(spec.native_cli.path,[],{env}),/UNBROKERED/);
  assert.equal(calls.length,0);
});

test('Center keeps its native config and other spawns remain unchanged',()=>{
  const {cp,calls,spec,env}=setup();
  const args=['--config',JSON.stringify({appHome:spec.app_home,ipcAddress:spec.center_socket,cipher:{detectionEnabled:true}}),'--app_home',spec.app_home];
  const options={env,stdio:'ignore'};cp.spawn(spec.center_binary.path,args,options);
  assert.deepEqual(Array.from(calls[0][1]),['-f',spec.center_profile.path,spec.center_binary.path,...args]);
  assert.equal(calls[0][2],options);
  cp.spawn('/usr/bin/true',[],options);assert.equal(calls[1][0],'/usr/bin/true');
  args[1]=JSON.stringify({appHome:spec.app_home,ipcAddress:'/tmp/wrong.sock'});
  assert.throws(()=>cp.spawn(spec.center_binary.path,args,options),/CENTER_EPOCH/);
  assert.equal(calls.length,2);
});
