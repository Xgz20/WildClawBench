export const COMPONENT_NAME = "task-process-cleanup";
export const COMPONENT_VERSION = "0.2.0";

export function assertCleanupEvidence(cleanup, workspace, options, hook, elapsedMilliseconds) {
  const minimum = options.processQuietMilliseconds ?? 5_000;
  if (!Number.isFinite(minimum) || minimum <= 0) throw new Error("TASK_PROCESS_QUIET_WINDOW_REQUIRED");
  if (cleanup?.schema_version !== "wildclawbench.general-e2e-task-process-cleanup/v1"
      || cleanup.supported !== true || cleanup.success !== true || cleanup.platform !== hook.platform
      || !Number.isFinite(cleanup.quiet_window_milliseconds) || cleanup.quiet_window_milliseconds < minimum
      || !Number.isFinite(cleanup.quiet_observed_milliseconds) || cleanup.quiet_observed_milliseconds < minimum
      || cleanup.quiet_observed_milliseconds > elapsedMilliseconds + 1
      || typeof cleanup.late_process_detected !== "boolean" || !Array.isArray(cleanup.termination_attempts)) {
    throw new Error("TASK_PROCESS_CLEANUP_EVIDENCE_INVALID");
  }
  for (const name of ["before", "after"]) {
    const snapshot = cleanup[name];
    if (snapshot?.supported !== true || snapshot.platform !== hook.platform
        || snapshot.workspace !== workspace || !Array.isArray(snapshot.targets)
        || !Array.isArray(snapshot.seed_pids) || !Array.isArray(snapshot.root_pids)) {
      throw new Error(`TASK_PROCESS_CLEANUP_SNAPSHOT_INVALID: ${name}`);
    }
  }
  if (cleanup.after.targets.length !== 0) throw new Error("TASK_PROCESS_CLEANUP_RESIDUAL_PROCESSES");
  if(cleanup.before.blocked_shared_processes?.length||cleanup.after.blocked_shared_processes?.length)
    throw Error("SHARED_NATIVE_TASK_PROCESSES_ACTIVE");
  const protectedPids=new Set(["before","after"].flatMap(name=>[
    ...(cleanup[name].infrastructure_roots||[]),...(cleanup[name].protected_processes||[]),
  ]).map(row=>row.pid));
  if(cleanup.termination_attempts.some(row=>protectedPids.has(row.pid)&&row.exit_code===0))
    throw Error("SHARED_NATIVE_INFRASTRUCTURE_SIGNALED");
}
