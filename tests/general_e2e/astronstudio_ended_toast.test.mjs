import assert from 'node:assert/strict';
import test from 'node:test';
import {isEndedCompletionToast} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';

function fixture() {
  const attributes={role:'dialog','aria-modal':'false','data-type':'success','data-position':'top-center','data-ending-style':''};
  const action={getAttribute:key=>key==='data-slot'?'toast-action':key==='aria-label'?'打开':null};
  const close={getAttribute:key=>key==='data-slot'?'toast-close':key==='aria-label'?'关闭通知':null};
  const f={attributes,buttons:[action,close],inputs:[],title:true,description:true,style:{opacity:'0',pointerEvents:'none'}};
  f.element={getAttribute:key=>attributes[key]??null,hasAttribute:key=>Object.hasOwn(attributes,key),
    querySelector:s=>s.includes('toast-title')?f.title:f.description,
    querySelectorAll:s=>s==='button'?f.buttons:f.inputs};return f;
}
test('only the exact ended noninteractive success completion toast is nonblocking',()=>{
  const f=fixture();assert.equal(isEndedCompletionToast(f.element,()=>f.style),true);
});
for(const [name,mutate] of [['visible toast',f=>f.style.opacity='1'],['intercepting toast',f=>f.style.pointerEvents='auto'],
  ['not ending',f=>delete f.attributes['data-ending-style']],['modal dialog',f=>f.attributes['aria-modal']='true'],
  ['error notification',f=>f.attributes['data-type']='error'],['unknown position',f=>f.attributes['data-position']='other'],
  ['unknown title',f=>f.title=false],['unknown structure',f=>f.description=false],['input or permission',f=>f.inputs=[{}]],
  ['extra action',f=>f.buttons.push({})],['missing close',f=>f.buttons.pop()]])test('blocking status is preserved for '+name,()=>{
  const f=fixture();mutate(f);assert.equal(isEndedCompletionToast(f.element,()=>f.style),false);
});
