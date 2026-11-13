import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import test from 'node:test';
import vm from 'node:vm';
import {ensureExecutionUiVisible} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-visibility.mjs';
import {clickSend} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';

function fixture({visible=false,pageFront=false,processChanged=false,openCode=0,neverVisible=false,foreign=false,neverForeground=false}={}) {
  const config={appPath:'/Applications/AStudio.app',endpoint:'http://127.0.0.1:9240'};
  const processInfo={pid:123,started_at:'2026-11-11T00:00:00Z',command:'verified-app-command'};
  const report={app:{path:config.appPath},gui:{unlocked:true},cdp:{ready:true,owned_by_main_process:true,endpoint:config.endpoint},
    process:{...processInfo,running:true,identity_verified:true,command_sha256:createHash('sha256').update(processInfo.command).digest('hex')}};
  let clock=0;const calls=[];let foregrounded=visible&&!foreign;
  const client={evaluate:async()=>({visibility:visible?'visible':'hidden',focus:visible,route:'#/owned'}),
    send:async method=>{calls.push({method});if(pageFront){visible=true;foregrounded=true;}},close(){}};
  const api={discoverMainTarget:async()=>({webSocketDebuggerUrl:'ws://verified'}),connect:async()=>client,
    inspect:async()=>({...processInfo,pid:processChanged?999:123}),
    foreground:async()=>({pid:foregrounded?123:456,bundle_id:foregrounded?'cn.xfyun.acode':'com.openai.codex',asn:'ASN:0x0-0x123:'}),
    runCommand:async(command,args)=>{calls.push({command,args});if(!neverVisible)visible=true;if(!neverForeground)foregrounded=true;return {code:openCode};},
    sleep:async ms=>{clock+=ms;},now:()=>clock,activationTimeoutMs:300};
  return {config,report,api,calls};
}
test('visible current page requires no native activation',async()=>{
  const f=fixture({visible:true});assert.equal((await ensureExecutionUiVisible(f.config,f.report,f.api)).changed,false);assert.deepEqual(f.calls,[]);
});
test('Page.bringToFront may restore visibility without an OS activation',async()=>{
  const f=fixture({pageFront:true});const r=await ensureExecutionUiVisible(f.config,f.report,f.api);assert.equal(r.changed,true);assert.equal(r.native_open_calls,0);
});
test('hidden Electron page activates only the same existing verified app without -n',async()=>{
  const f=fixture();const r=await ensureExecutionUiVisible(f.config,f.report,f.api);assert.equal(r.native_open_calls,1);assert.equal(r.prompt_send_calls,0);assert.equal(r.app_restart_calls,0);
  assert.deepEqual(f.calls.at(-1),{command:'/usr/bin/open',args:['-a','/Applications/AStudio.app']});
});
test('visible focused Electron document still activates when a foreign native app owns foreground',async()=>{
  const f=fixture({visible:true,foreign:true});const r=await ensureExecutionUiVisible(f.config,f.report,f.api);
  assert.equal(r.profile,'owned-native-visible-send/v2');assert.equal(r.before.visibility,'visible');
  assert.equal(r.native_before.pid,456);assert.equal(r.native_after.pid,123);assert.equal(r.native_open_calls,1);
});
for(const [name,options,expected] of [['changed process',{processChanged:true},/APP_CHANGED/],['failed activation',{openCode:1},/ACTIVATION_FAILED/],
  ['still hidden',{neverVisible:true},/NOT_VISIBLE/],['still foreign',{visible:true,foreign:true,neverForeground:true},/NOT_NATIVE_FOREGROUND/]])test('activation rejects '+name,async()=>{
    const f=fixture(options);await assert.rejects(ensureExecutionUiVisible(f.config,f.report,f.api),expected);
    if(options.processChanged)assert.equal(f.calls.some(c=>c.command),false);
});
for(const key of ['gui','process','cdp'])test('activation refuses an unverified '+key,async()=>{
  const f=fixture();if(key==='gui')f.report.gui.unlocked=false;if(key==='process')f.report.process.identity_verified=false;if(key==='cdp')f.report.cdp.owned_by_main_process=false;
  await assert.rejects(ensureExecutionUiVisible(f.config,f.report,f.api),/UNVERIFIED_APP_OR_GUI/);assert.deepEqual(f.calls,[]);
});

for(const visibility of ['hidden','visible'])test('actual send-target DOM evaluation enforces '+visibility+' document state',async()=>{
  class Element {closest(){return null;}getBoundingClientRect(){return {left:10,top:10,width:20,height:20};}}
  const editor=Object.assign(new Element(),{innerText:'prompt',querySelectorAll:()=>[]});
  const workspace=Object.assign(new Element(),{getAttribute:()=>'/workspace'});
  const button=Object.assign(new Element(),{disabled:false,contains:()=>false});
  const document={visibilityState:visibility,elementFromPoint:()=>button,querySelectorAll:s=>
    s.includes('composer-editor')?[editor]:s.includes('workspace-picker-trigger')?[workspace]:s.includes('project-picker-trigger')?[]:s.startsWith('button[type=')?[button]:[]};
  const calls=[];const client={evaluate:expr=>vm.runInNewContext(expr,{document,Element,location:{hash:'#/owned'},getComputedStyle:()=>({visibility:'visible',display:'block'})}),
    send:async(method,params)=>calls.push({method,params})};
  const result=await clickSend(client,'prompt','/workspace');assert.equal(result.clicked,visibility==='visible');assert.equal(calls.length,visibility==='visible'?3:0);
});
