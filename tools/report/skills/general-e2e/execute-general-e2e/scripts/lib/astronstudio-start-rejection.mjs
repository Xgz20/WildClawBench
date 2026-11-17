import { withStateSnapshot, querySnapshot, STATE_SNAPSHOT_TABLES, START_REJECTION_TABLES } from './astronstudio-state.mjs';
import {readFile} from 'node:fs/promises';
import {readAdapterAttestation} from '../../vendor/e2e-shared/astronstudio-start-rejection/adapter-attestation.mjs';
export { START_REJECTION_PROFILE, verifyNativeStartRejection } from '../../vendor/e2e-shared/astronstudio-start-rejection/index.mjs';
const sql = text => `'${String(text).replaceAll("'", "''")}'`;
const assert = (ok, code) => { if (!ok) throw new Error(`NATIVE_START_REJECTION_${code}`); };

// Every row comes from one integrity-checked snapshot. No provider operation,
// UI action, cancellation or replay is performed by this reader.
export async function queryNativeStartRejection(database, state, overrides = {}) {
  const thread = state.send?.post_send_route_thread_id;
  assert(thread && thread === state.send?.pre_send_route_thread_id, 'ROUTE');
  return withStateSnapshot(database, async snapshot => {
    const data = {};
    for (const table of [...STATE_SNAPSHOT_TABLES, ...START_REJECTION_TABLES]) {
      const where = table === 'projection_projects'
        ? `project_id IN (SELECT project_id FROM projection_threads WHERE thread_id=${sql(thread)})`
        : table === 'orchestration_events' ? `stream_id=${sql(thread)}`
        : table === 'orchestration_command_receipts' ? `aggregate_id=${sql(thread)}`
        : `thread_id=${sql(thread)}`;
      data[table] = await querySnapshot(snapshot, `SELECT * FROM ${table} WHERE ${where}`, overrides);
    }
    if(state.run_config?.path){
      const config=JSON.parse(await readFile(state.run_config.path,'utf8'));
      const source=await readAdapterAttestation(config.app?.path,overrides.nativeProcess);
      if(source)data.native_adapter_source=source;
    }
    return data;
  }, overrides, [...STATE_SNAPSHOT_TABLES, ...START_REJECTION_TABLES]);
}
