import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {prepareUnitModel} from '../../eval_memory_e2e/native/workbuddy-unit-model.mjs';

test('an already prepared unit is observe-only and never reloads an active model context',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'wb-model-prepared-'));
  try{
    fs.writeFileSync(path.join(root,'model-selection-prepared.json'),'{}');
    const scope={root,contract:'workbuddy-case-memory-unit/v1',zero_model_bootstrap_only:true,model_preferences:{}};
    const ui={evaluate(){throw Error('must not touch UI')},send(){throw Error('must not reload')}};
    await assert.rejects(()=>prepareUnitModel(ui,scope),/ALREADY_PREPARED_OBSERVE_ONLY/);
  }finally{fs.rmSync(root,{recursive:true,force:true})}
});
