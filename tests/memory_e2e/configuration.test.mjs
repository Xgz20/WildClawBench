import test from 'node:test';
import assert from 'node:assert/strict';
import { targetFor, TARGETS, roundtripValues, runConfiguration, selectClientPage, qwenMemorySettingsUrl, qwenMemoryControlPolicy } from '../../eval_memory_e2e/native/configuration.mjs';
import {MEMORY_UI_LOCK,memoryUiLockPath} from '../../eval_memory_e2e/native/common.mjs';

test('new batches in different parents share the exact UI lock while legacy paths remain frozen',()=>{
  assert.equal(memoryUiLockPath('/a/batch',{ui_lock_path:MEMORY_UI_LOCK}),memoryUiLockPath('/b/nested/batch',{ui_lock_path:MEMORY_UI_LOCK}));
  assert.equal(memoryUiLockPath('/old/parent/batch',{}),'/old/parent/.memory-native-ui.lock');
  assert.throws(()=>memoryUiLockPath('/a/batch',{ui_lock_path:'/Users/gzx/.codex/config.toml'}),/POLICY/);
});

test('Qwen global memory is one read/write control, without inventing a separate automatic switch',()=>{
  const policy=qwenMemoryControlPolicy('记忆 全局记忆 开启后读取和更新',1);
  assert.deepEqual(policy.keys,['global']);assert.equal(policy.separate_automatic_toggle,false);
  assert.throws(()=>qwenMemoryControlPolicy('全局记忆',2),/AMBIGUOUS/);
  assert.deepEqual(qwenMemoryControlPolicy('意识模式 自动记忆',2).keys,['automatic','awareness']);
  assert.throws(()=>qwenMemoryControlPolicy('other settings',1),/UNKNOWN/);
});

test('Qwen memory settings use the verified awareness route and retain the window identity',()=>{
  const root='file:///Applications/QwenWorkCN.app/Contents/Resources/app.asar/out/renderer/';
  assert.equal(new URL(qwenMemorySettingsUrl(root+'index.html#windowId=main',[root+'assets/index-D4wDUh3V.js'])).searchParams.get('tab'),'awareness');
  const route=new URL(qwenMemorySettingsUrl(root+'index.html?chat=synthetic#windowId=main',[root+'assets/index-DkViyRcX.js']));
  assert.equal(route.searchParams.get('view'),'settings');
  assert.equal(route.searchParams.get('tab'),'awareness');
  assert.equal(route.searchParams.get('chat'),'synthetic');
  assert.equal(route.hash,'#windowId=main');
});
test('Qwen settings reject another app, remote content and an unknown renderer',()=>{
  const root='file:///Applications/QwenWorkCN.app/Contents/Resources/app.asar/out/renderer/';
  for(const [url,scripts] of [[root+'index.html',[root+'assets/index-new.js']],
    ['https://example.test/index.html',[root+'assets/index-DkViyRcX.js']],
    [root.replace('QwenWorkCN.app','Other.app')+'index.html',[root+'assets/index-DkViyRcX.js']]]){
    assert.throws(()=>qwenMemorySettingsUrl(url,scripts),/CONFIG_QWEN_SETTINGS_ROUTE_UNVERIFIED/);
  }
});

test('Doubao settings selection follows the verified app URL when the chat title changes',()=>{
  const main={type:'page',title:'记忆测试 - 豆包工作',url:'chrome://doubaowork-chat/chat/123'};
  assert.equal(selectClientPage([main,{type:'page',title:'豆包工作',url:'https://example.test/'}],'DoubaoWork'),main);
  const native={...main,url:'doubaowork://doubaowork-chat/chat/123'};
  assert.equal(selectClientPage([native,{type:'iframe',url:'https://example.test/?private=value'}],'DoubaoWork'),native);
  assert.throws(()=>selectClientPage([main,{...main,url:'chrome://doubaowork-chat/chat/456'}],'DoubaoWork'),/AMBIGUOUS/);
  assert.throws(()=>selectClientPage([],'Codex'),/NOT_ALLOWED/);
});

test('Codex and unknown clients are rejected before filesystem or transport access', async()=>{
  for(const name of ['Codex','codex','ChatGPT','__proto__','constructor']) {
    assert.throws(()=>targetFor(name),/CONFIG_TARGET_NOT_ALLOWED/);
    await assert.rejects(()=>runConfiguration({harness:name}),/CONFIG_TARGET_NOT_ALLOWED/);
  }
  assert.deepEqual(Object.keys(TARGETS),['WorkBuddy','QwenWork','DoubaoWork']);
});
test('each switch is restored before moving to the next switch', async()=>{
  let values={automatic:true,awareness:true};const events=[];
  const result=await roundtripValues({read:async()=>({ready:true,values:{...values}}),
    change:async(k,v)=>{values[k]=v},log:async e=>events.push(e),keys:Object.keys(values)});
  assert.equal(result.restored,true);assert.deepEqual(values,{automatic:true,awareness:true});
  assert.equal(events.filter(e=>e.kind==='RESTORE_VERIFIED').length,2);
});
test('transport failure after an applied switch restores the original value', async()=>{
  let values={enabled:true};let calls=0;const events=[];
  await assert.rejects(()=>roundtripValues({read:async()=>({ready:true,values:{...values}}),
    change:async(k,v)=>{values[k]=v;if(++calls===1)throw Error('transport lost after click')},
    log:async e=>events.push(e),keys:['enabled']}),/transport lost/);
  assert.equal(values.enabled,true);assert.equal(events.at(-1).restored,true);
});
test('a dependent switch can disappear while the parent is disabled and is checked after restore', async()=>{
  let values={automatic:true,awareness:true};
  const result=await roundtripValues({read:async()=>({ready:true,values:{...values,automatic:values.awareness?values.automatic:null}}),
    change:async(k,v)=>{values[k]=v},log:async()=>{},keys:['automatic','awareness']});
  assert.equal(result.restored,true);assert.deepEqual(values,{automatic:true,awareness:true});
});
test('unrelated setting drift fails without proceeding to a second mutation', async()=>{
  let reads=0;let mutations=0;
  await assert.rejects(()=>roundtripValues({read:async()=>({ready:true,values:{enabled:++reads===1}}),
    change:async()=>mutations++,log:async()=>{},keys:['enabled']}),/CONFIG_RESTORE_INCOMPLETE/);
  assert.equal(mutations,0);
});
