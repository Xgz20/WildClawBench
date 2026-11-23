// Formal General E2E dispatch policy. Historical observations are never promoted.
export const FULL_ACCESS_PROFILE = 'general-e2e-full-access-required/v1';
const labels = Object.freeze({
  astronstudio: ['完全访问', 'full-access'],
  loomy: ['完全访问'],
  workbuddy: ['full-access'],
  qwenwork: ['full-access'],
  doubaowork: ['全部允许', '完全访问'],
});

export function requireFullAccess(harness, observed, stage = 'before-dispatch') {
  if (!Object.hasOwn(labels, harness)) throw new Error('GENERAL_E2E_PERMISSION_HARNESS_UNSUPPORTED:' + harness);
  if (typeof observed !== 'string' || !labels[harness].includes(observed)) {
    throw new Error('GENERAL_E2E_FULL_ACCESS_REQUIRED:' + harness + ':' + stage
      + ':observed=' + (typeof observed === 'string' ? observed : '<unknown>'));
  }
  return { profile: FULL_ACCESS_PROFILE, harness, required_mode: 'full-access',
    observed_label: observed, stage, verified: true };
}

export async function invokeWithFullAccess(harness, readPermission, invoke) {
  const proof = requireFullAccess(harness, await readPermission(), 'physical-send');
  return { result: await invoke(), full_access_gate: proof };
}
