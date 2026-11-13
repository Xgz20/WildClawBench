import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {submitExactProjectPath,readProjectPathCompletion} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-cdp.mjs';

function fixture({attribute='/target',value='/target',count=1,disabled=false,rowKnown=true,buttons=1}={}) {
  let submitted=0,sidebarClicked=0;
  class Element {getBoundingClientRect(){return {width:10,height:10};} closest(){return null;}}
  const submit=Object.assign(new Element(),{disabled,click:()=>submitted++});
  const sidebar=Object.assign(new Element(),{disabled:false,click:()=>sidebarClicked++});
  const row={querySelectorAll:s=>s==='input'?[input]:Array(buttons).fill(submit)};
  const input=Object.assign(new Element(),{value,getAttribute:()=>attribute,
    closest:selector=>selector==='[data-slot="input-control"]'&&rowKnown?{parentElement:row}:null});
  const document={querySelectorAll:s=>s.startsWith('input')?Array(count).fill(input):[sidebar,submit]};
  const client={evaluate:expr=>vm.runInNewContext(expr,{document,Element,getComputedStyle:()=>({visibility:'visible',display:'block'})})};
  return {client,counts:()=>({submitted,sidebarClicked})};
}
test('a committed exact path submits only its own field button',async()=>{
  const f=fixture();assert.equal((await submitExactProjectPath(f.client,'/target')).clicked,true);
  assert.deepEqual(f.counts(),{submitted:1,sidebarClicked:0});
});
for(const [name,options] of [['uncommitted rendered path',{attribute:'/previous'}],['wrong value',{value:'/other'}],
  ['duplicate path fields',{count:2}],['unknown field structure',{rowKnown:false}],['disabled submit',{disabled:true}],
  ['ambiguous submit controls',{buttons:2}]])test('project submission rejects '+name,async()=>{
  const f=fixture(options);assert.equal((await submitExactProjectPath(f.client,'/target')).clicked,false);
  assert.deepEqual(f.counts(),{submitted:0,sidebarClicked:0});
});

test('native registration with a previous workspace or a still-mounted form is not UI completion',async()=>{
  for(const [path,input,cancel,dialog,expected] of [['/previous',0,0,0,false],['/target',1,1,0,false],
    ['/target',0,1,0,false],['/target',0,0,1,false],['/target',0,0,0,true]]) {
    class Element {getBoundingClientRect(){return {width:10,height:10};}closest(){return null;}getAttribute(){return path;}}
    const element=new Element();
    const document={querySelectorAll:s=>s.includes('workspace-picker-trigger')?[element]:s.startsWith('input')?Array(input).fill(element):s.startsWith('button')?Array(cancel).fill(element):Array(dialog).fill(element)};
    const client={evaluate:expr=>vm.runInNewContext(expr,{document,Element,getComputedStyle:()=>({visibility:'visible',display:'block'})})};
    assert.equal((await readProjectPathCompletion(client,'/target')).complete,expected);
  }
});
