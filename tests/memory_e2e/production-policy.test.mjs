import test from 'node:test';
import assert from 'node:assert/strict';
import {assertAStudioProductionProfile} from '../../eval_memory_e2e/native/production.mjs';
import {assertMemoryFilesystemBoundary} from '../../eval_memory_e2e/native/common.mjs';

test('legacy unscored diagnostics cannot enter dispatch or namespace preparation',()=>{
  const legacy={memory_protocol:{automatic_generation_diagnostic_allowed:true,compiled_kernel_diagnostic:true,formal_scoring_allowed:false},
    non_target_memory_boundary:{admitted_adapter:'macos-seatbelt-astudio-compiled-kernel/v3',status:'os_enforced'},
    astudio_scope:{contract:'astudio-case-memory-unit/v1'}};
  const profiles=[legacy,{installed_kernel_reference:{}},{compiled_kernel:null},{native_executor:null},
    {non_target_memory_boundary:{admitted_adapter:'macos-seatbelt-astudio-native-executor/v2'}}];
  for(const profile of profiles){
    assert.throws(()=>assertAStudioProductionProfile(profile),/ASTUDIO_PRODUCTION_PACKAGE_REQUIRED/);
    for(const action of ['execute_step','prepare_namespace'])
      assert.throws(()=>assertMemoryFilesystemBoundary({harness:'AstronStudio',transport_action:'dispatch',action},profile),/ASTUDIO_PRODUCTION_PACKAGE_REQUIRED/);
    // Old accepted requests remain observation-only; this function never sends.
    assert.equal(assertMemoryFilesystemBoundary({harness:'AstronStudio',transport_action:'observe',action:'execute_step'},profile),null);
  }
  assert.doesNotThrow(()=>assertAStudioProductionProfile({non_target_memory_boundary:{admitted_adapter:'macos-seatbelt-astudio-backend/v1'}}));
});
