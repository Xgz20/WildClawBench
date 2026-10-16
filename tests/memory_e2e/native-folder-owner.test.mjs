import test from 'node:test';
import assert from 'node:assert/strict';
import {assertQwenNativeFolderDialogOwner} from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/environment.mjs';
const gui={schema:'wildclawbench.macos-gui-session/v1',unlocked:true,screen_locked:false,console_session_verified:true};
const listener={pid:42,process_start_identity:'fixed-start',command_sha256:'abc',token_usage_exposed:false};
const expected={schema:'wildclawbench.qwenwork-execution-environment/v1',verified:true,gui,listener,
  app_path:'/Applications/QwenWorkCN.app',endpoint:'http://127.0.0.1:9250',cdp:{ready:true,websocket_verified:true}};
test('owned native folder dialog requires the original OS listener without a CDP request',async()=>{
  const result=await assertQwenNativeFolderDialogOwner(expected,{inspectGui:async()=>gui,inspectListener:async()=>({...listener}),
    fetch:()=>{throw Error('CDP must not be entered while the native dialog is open')}});
  assert.equal(result.verified,true);
});
test('a changed or missing dialog owner never reaches the folder helper',async()=>{
  for(const observed of [null,{...listener,pid:43},{...listener,command_sha256:'changed'}]) {
    await assert.rejects(()=>assertQwenNativeFolderDialogOwner(expected,{inspectGui:async()=>gui,inspectListener:async()=>observed}),/OWNER_CHANGED/);
  }
});
test('a locked desktop is refused during a native dialog',async()=>{
  await assert.rejects(()=>assertQwenNativeFolderDialogOwner(expected,{inspectGui:async()=>({...gui,unlocked:false,screen_locked:true})}),/GUI/);
});
