import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import test from 'node:test';
import {runCapture} from '../../tools/report/e2e-shared/desktop-runtime/process.mjs';
function spawnFixture(stdout,stderr,code){return ()=>{const child=new EventEmitter();child.stdout=new EventEmitter();child.stderr=new EventEmitter();queueMicrotask(()=>{for(const byte of Buffer.from(stdout))child.stdout.emit('data',Buffer.from([byte]));child.emit('exit',code);for(const byte of Buffer.from(stderr))child.stderr.emit('data',Buffer.from([byte]));child.onceAfterExit=true;child.emit('close',code);});return child;};}
test('split UTF-8 bytes and trailing stderr after exit survive exactly',async()=>{const stdout='中文🙂跨块\n{"原件":"不修改"}',stderr='尾部错误：校验';const r=await runCapture('fixture',[],{capture:true},{spawnProcess:spawnFixture(stdout,stderr,0)});assert.equal(r.stdout,stdout);assert.equal(r.stderr,stderr);assert.equal(r.code,0);});
test('allowed nonzero completion retains complete Unicode evidence',async()=>{const r=await runCapture('fixture',[],{allowFailure:true},{spawnProcess:spawnFixture('结果','拒绝：目录外',3)});assert.deepEqual(r,{code:3,stdout:'结果',stderr:'拒绝：目录外'});});
test('failed process reports complete UTF-8 stderr after stream close',async()=>{await assert.rejects(runCapture('fixture',[],{},{spawnProcess:spawnFixture('','完整错误🙂',1)}),/完整错误🙂/);});
