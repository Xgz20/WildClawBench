import test from 'node:test';
import assert from 'node:assert/strict';
import {userInfo,hostname,arch,tmpdir} from 'node:os';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {MACHINE_PATHS,pathsForHome,verifyMachine,verifyNodeRuntime,memoryPython} from '../../eval_memory_e2e/native/machine.mjs';
import {assertMemoryFilesystemBoundary} from '../../eval_memory_e2e/native/common.mjs';

test('Python and native drivers resolve the same OS-account paths despite foreign HOME',()=>{
  const selected=memoryPython();
  const raw=execFileSync(selected,['-c','import json; from eval_memory_e2e.machine import machine_identity; print(json.dumps(machine_identity()))'],
    {encoding:'utf8',env:{...process.env,HOME:'/tmp/foreign/.codex'}});
  const profile=JSON.parse(raw);
  assert.deepEqual(profile.paths,MACHINE_PATHS);
  verifyMachine(profile);
  assert.throws(()=>verifyMachine({...profile,host:'old-machine'}),/MACHINE_DRIFT/);
  assert.throws(()=>verifyMachine({...profile,paths:pathsForHome('/Users/old-machine')}),/MACHINE_DRIFT/);
  assert.throws(()=>verifyMachine({...profile,architecture:arch()==='arm64'?'x86_64':'arm64'}),/MACHINE_DRIFT/);
  assert.equal(profile.uid,userInfo().uid);assert.equal(profile.host,hostname());
});
test('unsupported Python is rejected before reading any client data',()=>{
  const code="import {memoryPython} from './eval_memory_e2e/native/machine.mjs'; memoryPython()";
  const folder=mkdtempSync(join(tmpdir(),'memory-python-test-')),fake=join(folder,'python');
  try {
    writeFileSync(fake,'#!/usr/bin/env node\nconsole.log(JSON.stringify({version:[3,9],path:"/unavailable/old-python"}))\n',{mode:0o700});
    assert.throws(()=>execFileSync(process.execPath,['--input-type=module','-e',code],
      {env:{...process.env,MEMORY_E2E_PYTHON:fake},stdio:'pipe'}),e=>e.stderr.toString().includes('MEMORY_PYTHON_311_REQUIRED'));
  }finally{rmSync(folder,{recursive:true,force:true})}
});
test('a frozen Node version or executable cannot silently change',()=>{
  const current={version:process.version,architecture:arch(),executable:process.execPath};
  verifyNodeRuntime(current);
  assert.throws(()=>verifyNodeRuntime({...current,version:'v22.0.0'}),/NATIVE_NODE_DRIFT/);
  assert.throws(()=>verifyNodeRuntime({...current,executable:'/other/node'}),/NATIVE_NODE_DRIFT/);
});
test('an unimplemented filesystem guard rejects dispatch/retry even with a claimed proof; observation stays readonly',()=>{
  for(const boundary of [{required:true,status:'not_enforced'},{required:false,status:'verified',proof:'claimed'}]){
    const profile={non_target_memory_boundary:boundary};
    for(const transport_action of ['dispatch','retry_pre_send'])
      assert.throws(()=>assertMemoryFilesystemBoundary({action:'execute_step',transport_action},profile),/FILESYSTEM_BOUNDARY_UNVERIFIED/);
    assertMemoryFilesystemBoundary({action:'execute_step',transport_action:'observe'},profile);
    assertMemoryFilesystemBoundary({action:'prepare_namespace',transport_action:'dispatch'},profile);
  }
});
