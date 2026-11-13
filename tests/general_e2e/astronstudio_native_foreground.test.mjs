import assert from 'node:assert/strict';
import test from 'node:test';
import {parseNativeForegroundApp,readNativeForegroundApp} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-native-foreground.mjs';
import {clickSend} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';

const asn='ASN:0x0-0x395d95a:\n';
const info='"CFBundleIdentifier"="cn.xfyun.acode"\n"pid"=77876\n';
test('native foreground reader parses the current ASN and unique PID/bundle',async()=>{
  const calls=[];const result=await readNativeForegroundApp({runCommand:async(command,args)=>{calls.push([command,args]);return{code:0,stdout:args[0]==='front'?asn:info};}});
  assert.equal(result.pid,77876);assert.equal(result.bundle_id,'cn.xfyun.acode');
  assert.deepEqual(calls,[['/usr/bin/lsappinfo',['front']],['/usr/bin/lsappinfo',['info','-only','bundleid,pid',asn.trim()]]]);
});
for(const [name,front,text] of [['unknown ASN','whatever',info],['duplicate PID',asn,info+'"pid"=12\n'],['missing bundle',asn,'"pid"=77876\n'],['bad PID',asn,'"CFBundleIdentifier"="x"\n"pid"=1\n']])test('native foreground refuses '+name,()=>{
  assert.throws(()=>parseNativeForegroundApp(front,text),/FOREGROUND_/);
});
test('native foreground command failure fails closed',async()=>{
  await assert.rejects(readNativeForegroundApp({runCommand:async()=>({code:1,stdout:asn})}),/READ_FAILED/);
});
for(const pid of [77876,96898])test('physical send checks native foreground PID '+pid,async()=>{
  const calls=[];const client={evaluate:async()=>({ready:true,count:1,x:10,y:20,thread_id:'owned'}),send:async(...args)=>calls.push(args)};
  const result=await clickSend(client,'prompt','/workspace',{expectedNativePid:77876,readNativeForegroundApp:async()=>({pid,bundle_id:pid===77876?'cn.xfyun.acode':'com.openai.codex'})});
  assert.equal(result.clicked,pid===77876);assert.equal(calls.length,pid===77876?3:0);
});
