/* Pure control-layer policy. Archived source-build receipts remain readable. */
export function assertAStudioProductionProfile(profile) {
  const protocol=profile.memory_protocol??{},boundary=profile.non_target_memory_boundary??{};
  if(['installed_kernel_reference','compiled_kernel','native_executor'].some(key=>Object.hasOwn(profile,key))
    ||protocol.compiled_kernel_diagnostic===true||protocol.automatic_generation_diagnostic_allowed===true
    ||(boundary.admitted_adapter!=null&&boundary.admitted_adapter!=='macos-seatbelt-astudio-backend/v1'))
    throw Error('ASTUDIO_PRODUCTION_PACKAGE_REQUIRED');
}
