import test from 'node:test';
import assert from 'node:assert/strict';
import {userInfo,hostname,arch} from 'node:os';
import {execFileSync} from 'node:child_process';
import {MACHINE_PATHS,pathsForHome,verifyMachine,memoryPython} from '../../eval_memory_e2e/native/machine.mjs';

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
  assert.throws(()=>execFileSync(process.execPath,['--input-type=module','-e',code],
    {env:{...process.env,MEMORY_E2E_PYTHON:'/usr/bin/python3'},stdio:'pipe'}));
});
