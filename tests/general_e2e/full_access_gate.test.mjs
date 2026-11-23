import test from 'node:test';
import assert from 'node:assert/strict';
import { requireFullAccess, invokeWithFullAccess } from '../../tools/report/e2e-shared/desktop-gui/formal-permission.mjs';
import { assertConfiguration, guardSend } from '../../tools/report/e2e-shared/loomy/ui.mjs';
import { clickSend } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';
import { dispatchWorkBuddyPrompt } from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs';
import { dispatchQwenPrompt, QWEN_PERMISSION_SELECTOR, QWEN_SEND_SELECTOR, classifyQwenPermissionLabel } from '../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/ui.mjs';

for (const [harness,label] of [['astronstudio','完全访问'],['loomy','完全访问'],['workbuddy','full-access'],['qwenwork','full-access'],['doubaowork','全部允许']]) {
  test(harness+' requires explicit full access and never invokes on default/unknown',async()=>{
    assert.equal(requireFullAccess(harness,label).verified,true);
    for(const invalid of [null,undefined,false,'','默认权限','default-sandbox','询问模式','current','not full-access','非完全访问']){
      let invoked=0;
      await assert.rejects(invokeWithFullAccess(harness,async()=>invalid,async()=>{invoked++;}),/GENERAL_E2E_FULL_ACCESS_REQUIRED/);
      assert.equal(invoked,0);
    }
    let count=0;const out=await invokeWithFullAccess(harness,async()=>label,async()=>++count);
    assert.equal(count,1);assert.equal(out.result,1);
  });
}
test('unknown Harness has no permissive fallback',()=>assert.throws(()=>requireFullAccess('other','full-access'),/HARNESS_UNSUPPORTED/));
const loomSnapshot=permission=>({nodes:[{role:'AXWindow'},{role:'AXPopUpButton',title:'Spark-X2.6 正式版 高'},
  {role:'AXPopUpButton',title:permission},{role:'AXTextArea',value:'prompt',value_settable:true}]});
test('new Loomy policy blocks default, while legacy replay retains observed default',async()=>{
  const legacy={permission_policy:'preserve-workspace-policy',configuration:{model_label:'Spark-X2.6 正式版 高',reasoning_effort:'high',permission_label:'默认权限'}};
  assert.equal(assertConfiguration(loomSnapshot('默认权限'),legacy).permission_label,'默认权限');
  assert.throws(()=>assertConfiguration(loomSnapshot('默认权限'),{...legacy,permission_policy:'require-full-access'}),/FULL_ACCESS_REQUIRED/);
  // Intermediate home/previous-project navigation has no send capability;
  // full access is enforced on the selected target and again during send.
  assert.equal(assertConfiguration(loomSnapshot('默认权限'),{...legacy,permission_policy:'require-full-access'},
    {preparingWorkspace:true}).permission_label,'默认权限');
  // Rejection precedes any attempt to use the absent AX helper.
  await assert.rejects(guardSend(legacy,'/workspace','prompt',true),/FULL_ACCESS_REQUIRED/);
});
test('AStudio rechecks permission after target readiness before any mouse event',async()=>{
  let reads=0;const events=[];const client={evaluate:async()=>++reads===1?{ready:true,count:1,x:1,y:2}:{permission_count:1,permission:'默认权限'},send:async(...a)=>events.push(a)};
  await assert.rejects(clickSend(client,'prompt','/workspace'),/FULL_ACCESS_REQUIRED/);assert.deepEqual(events,[]);
});
test('WorkBuddy rechecks permission at the physical click boundary',async()=>{
  const events=[];const client={send:async(...a)=>events.push(a),evaluate:async s=>s.includes('document.elementFromPoint')?{clicked:true,count:1,point:{x:1,y:2}}:{permission_count:1,permission:'default-sandbox'}};
  await assert.rejects(dispatchWorkBuddyPrompt(client,1000),/FULL_ACCESS_REQUIRED/);
  assert.equal(events.filter(([method])=>method==='Input.dispatchMouseEvent').length,0);
});
test('QwenWork final click rejects a changed permission and misleading labels',async()=>{
  let clicks=0;const element=text=>({isVisible:async()=>true,isEnabled:async()=>true,innerText:async()=>text,getAttribute:async()=>null,click:async()=>clicks++});
  const locator=e=>({count:async()=>1,nth:()=>e});
  const page={locator:s=>locator(element(s===QWEN_PERMISSION_SELECTOR?'默认权限':s===QWEN_SEND_SELECTOR?'发送':'模型'))};
  await assert.rejects(dispatchQwenPrompt(page,1000),/FULL_ACCESS_REQUIRED/);assert.equal(clicks,0);
  assert.equal(classifyQwenPermissionLabel('非完全访问'),null);
});
