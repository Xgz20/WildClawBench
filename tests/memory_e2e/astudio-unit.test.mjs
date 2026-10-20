import test from 'node:test';
import assert from 'node:assert/strict';
import {selectAStudioPaths,aStudioBoundaryListener,aStudioRolloutPathAllowed,configureAStudioControllerTmp,aStudioAutomaticGenerationDiagnosticAllowed} from '../../eval_memory_e2e/native/astronstudio.mjs';
import {MACHINE_PATHS} from '../../eval_memory_e2e/native/machine.mjs';
import {mkdtemp,rm,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {DatabaseSync} from 'node:sqlite';
import {withStateSnapshot} from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';
test('automatic generation diagnosis requires a compiled v3 unit and remains unscored',()=>{
  const profile={memory_protocol:{automatic_generation_diagnostic_allowed:true,compiled_kernel_diagnostic:true,formal_scoring_allowed:false},
    non_target_memory_boundary:{admitted_adapter:'macos-seatbelt-astudio-compiled-kernel/v3',status:'os_enforced'},
    astudio_scope:{contract:'astudio-case-memory-unit/v1'}};
  assert.equal(aStudioAutomaticGenerationDiagnosticAllowed(profile),true);
  for(const changed of [{...profile,memory_protocol:{...profile.memory_protocol,formal_scoring_allowed:true}},
    {...profile,memory_protocol:{...profile.memory_protocol,compiled_kernel_diagnostic:false}},
    {...profile,memory_protocol:{...profile.memory_protocol,automatic_generation_diagnostic_allowed:false}},
    {...profile,non_target_memory_boundary:{...profile.non_target_memory_boundary,status:'not_enforced'}},
    {...profile,non_target_memory_boundary:{...profile.non_target_memory_boundary,admitted_adapter:'macos-seatbelt-astudio-native-executor/v2'}},
    {...profile,astudio_scope:undefined}])assert.equal(aStudioAutomaticGenerationDiagnosticAllowed(changed),false);
});
test('unit-specific DB and memory observation paths cannot fall back to the ordinary account home',()=>{
  const root=MACHINE_PATHS.debug+'/test/batch',runtime=MACHINE_PATHS.debug+'/test/unit/runtime';
  const astudio_scope={contract:'astudio-case-memory-unit/v1',batch_root:root,paths:{runtime,
    acode:runtime+'/source-home',desktop:runtime+'/desktop',overlay:runtime+'/desktop/acode-home-overlay',
    astudio_db:runtime+'/desktop/userdata/state.sqlite'}};
  assert.equal(selectAStudioPaths({astudio_scope},root).astudio_db,astudio_scope.paths.astudio_db);
  assert.equal(selectAStudioPaths({},root),MACHINE_PATHS);
  for(const paths of [{...astudio_scope.paths,acode:MACHINE_PATHS.acode},
    {...astudio_scope.paths,astudio_db:MACHINE_PATHS.astudio_db}]){
    assert.throws(()=>selectAStudioPaths({astudio_scope:{...astudio_scope,paths}},root),/PATHS_UNVERIFIED/);
  }
  assert.throws(()=>selectAStudioPaths({astudio_scope},root+'-other'),/PATHS_UNVERIFIED/);
});
test('rollout collection admits only this unit source/overlay and rejects ordinary or previous-unit history',()=>{
  const runtime=MACHINE_PATHS.debug+'/test/unit2/runtime';
  const paths={acode:runtime+'/source-home',overlay:runtime+'/desktop/acode-home-overlay'};
  assert.equal(aStudioRolloutPathAllowed(paths.acode+'/sessions/owned.jsonl',paths),true);
  assert.equal(aStudioRolloutPathAllowed(paths.overlay+'/sessions/owned.jsonl',paths),true);
  for(const file of [MACHINE_PATHS.acode+'/sessions/old.jsonl',runtime.replace('/unit2/','/unit1/')+'/source-home/sessions/old.jsonl',
    paths.acode+'-other/sessions/old.jsonl'])assert.equal(aStudioRolloutPathAllowed(file,paths),false);
});
test('the final send gate requires an actual main PID in both legacy and case-unit attestation envelopes',()=>{
  for(const contract of ['macos-seatbelt-astudio-backend/v1','astudio-case-memory-unit/v1']){
    assert.equal(aStudioBoundaryListener({contract,status:'PASS',launch_identity:{pid:1234}},1234),true);
    for(const proof of [{contract,status:'PASS'}, {contract,status:'PASS',launch_identity:{pid:9999}},
      {contract,status:'FAILED',launch_identity:{pid:1234}}]){
      assert.throws(()=>aStudioBoundaryListener(proof,1234),/LISTENER_MISMATCH/);
    }
  }
});
test('real SQLite observation snapshots stay in the private controller tree and legacy profiles keep their temp policy',async()=>{
  const original=process.env.TMPDIR,root=await realpath(await mkdtemp(tmpdir()+'/memory-controller-test-'));
  try{
    assert.equal(await configureAStudioControllerTmp({root,control:root+'/.native/AstronStudio/op-test'},{}),null);
    assert.equal(process.env.TMPDIR,original);
    const dbPath=root+'/synthetic.sqlite',db=new DatabaseSync(dbPath);
    db.exec("CREATE TABLE projection_thread_messages(text TEXT);INSERT INTO projection_thread_messages VALUES('SYNTHETIC-ONLY')");db.close();
    const temp=await configureAStudioControllerTmp({root,control:root+'/.native/AstronStudio/op-test'},{astudio_scope:{}});
    assert.equal(tmpdir(),temp);
    await withStateSnapshot(dbPath,async snapshot=>{
      assert.ok(snapshot.startsWith(temp+'/'));
      const copy=new DatabaseSync(snapshot,{readOnly:true});
      try{assert.equal(copy.prepare('SELECT text FROM projection_thread_messages').get().text,'SYNTHETIC-ONLY')}finally{copy.close()}
    },{},['projection_thread_messages']);
    await assert.rejects(configureAStudioControllerTmp({root,control:root+'-other'},{astudio_scope:{}}),/TMP_SCOPE/);
  }finally{
    if(original===undefined)delete process.env.TMPDIR;else process.env.TMPDIR=original;
    await rm(root,{recursive:true,force:true});
  }
});
