import test from 'node:test';
import assert from 'node:assert/strict';
import {ensureLocalRuntimeMode} from '../../eval_memory_e2e/native/common.mjs';

function fixture({open=false, initial='云电脑', ambiguous=false}={}) {
  const events=[]; let current=initial;
  const local={count:async()=>open?(ambiguous?2:1):0, isVisible:async()=>open,
    waitFor:async()=>{events.push('wait-menu');open=true;},
    click:async()=>{events.push('select-local');current='本地电脑';}};
  const page={getByTestId:()=>({count:async()=>1,innerText:async()=>current,
    click:async()=>{events.push('open-menu');}}),
    getByRole:(role,opts)=>{assert.equal(role,'menuitem');assert.equal(opts.exact,true);return local;},
    waitForFunction:async()=>{assert.equal(current,'本地电脑');events.push('readback');}};
  return {page,events,record:async()=>events.push('intent')};
}
test('a delayed runtime menu is awaited before selecting local mode and verifying readback',async()=>{
  const f=fixture();await ensureLocalRuntimeMode(f.page,f.record);
  assert.deepEqual(f.events,['intent','open-menu','wait-menu','select-local','readback']);
});
test('an already visible owned menu is used without toggling it closed',async()=>{
  const f=fixture({open:true});await ensureLocalRuntimeMode(f.page,f.record);
  assert.deepEqual(f.events,['intent','wait-menu','select-local','readback']);
});
test('unknown modes and duplicate menu entries never reach selection',async()=>{
  for(const opts of [{initial:'unknown'},{open:true,ambiguous:true}]) {
    const f=fixture(opts);await assert.rejects(()=>ensureLocalRuntimeMode(f.page,f.record));
    assert.ok(!f.events.includes('select-local'));
  }
});
