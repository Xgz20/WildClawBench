// Pure metadata proof; original state bytes and native SDK events stay intact.
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const TERMINAL_PROJECTION_PROFILE = 'bound-sdk-completed-turn-projection-status/v1';
export const TERMINAL_PROJECTION_STATE = 'bindings/terminal-projection-original-state.json';
export const TERMINAL_PROJECTION_PROOF = 'bindings/terminal-projection-proof.json';
export function historicalTerminalProjection(state) {
  return state?.phase === 'COMPLETED' && state.execution?.business_status === 'completed'
    && state.session?.native_status === 'running';
}
function invoke(request) {
  const own = dirname(fileURLToPath(import.meta.url));
  const script = join(own, '../general-contracts/astronstudio_terminal_projection.py');
  if (!existsSync(script)) throw Error('TERMINAL_PROJECTION_IMPLEMENTATION_MISSING');
  const result = spawnSync('python3', ['-X', 'utf8', script], {
    input: JSON.stringify(request), encoding: 'utf8', timeout: 30_000, maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error || result.status !== 0) throw Error(result.error?.message || result.stderr.trim()
    || 'TERMINAL_PROJECTION_VALIDATION_FAILED');
  return JSON.parse(result.stdout);
}
export function deriveTerminalProjection(stateBytes, index, sdkBytes, transcriptBytes) {
  return invoke({ operation: 'derive', state_bytes: stateBytes.toString('base64'), index,
    sdk_bytes: sdkBytes.toString('base64'), transcript_bytes: transcriptBytes.toString('base64') });
}
export function verifyTerminalProjection(index, stateBytes, traceRoot, execution = undefined) {
  if (!historicalTerminalProjection(JSON.parse(stateBytes))
      && !(index.binding_evidence ?? []).some(r => [TERMINAL_PROJECTION_STATE, TERMINAL_PROJECTION_PROOF].includes(r.path))) return null;
  return invoke({ operation: 'verify', index, state_bytes: stateBytes.toString('base64'),
    trace_root: traceRoot, execution });
}
