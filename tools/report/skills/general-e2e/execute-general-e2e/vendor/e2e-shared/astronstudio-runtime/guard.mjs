import {createHash} from "node:crypto";
import {lstat,readFile,readdir} from "node:fs/promises";
import {join,resolve} from "node:path";
import {queryNativeRuntimeSafety} from "./state.mjs";

const terminal=new Set(["COMPLETED","FAILED"]);
const idle=new Set(["ready","completed","error","interrupted","cancelled","canceled","stopped","closed"]);
const hash=bytes=>createHash("sha256").update(bytes).digest("hex");
function stable(value) {
  if(Array.isArray(value))return value.map(stable);
  if(!value||typeof value!=="object")return value;
  return Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])]));
}
async function json(path) {
  const info=await lstat(path);
  if(!info.isFile()||info.isSymbolicLink()||info.size>16*1024*1024)throw Error("ASTUDIO_GUARD_UNSAFE_INPUT");
  return JSON.parse(await readFile(path,"utf8"));
}
async function directories(path) {
  try{return (await readdir(path,{withFileTypes:true})).filter(x=>x.isDirectory()&&!x.isSymbolicLink()).map(x=>x.name);}
  catch(error){if(error.code==="ENOENT")return [];throw error;}
}
export async function assertUnitExecutionQuiescent(unitRoot,taskId) {
  const blockers=[];
  for(const id of await directories(join(unitRoot,".general-e2e","execution"))) {
    try {await lstat(join(unitRoot,".general-e2e","execution",id,"driver.lock"));
      blockers.push({kind:"driver-owner-lock",task_id:id});}
    catch(error){if(error.code!=="ENOENT")throw error;}
    let state;try{state=await json(join(unitRoot,".general-e2e","execution",id,"automation-state.json"));}
    catch(error){if(error.code==="ENOENT")continue;throw error;}
    if(!terminal.has(state.phase)&&(state.phase!=="PENDING"||state.send?.dispatch_attempt_count>0||state.send?.dispatch_armed_at
        ||["sent","uncertain"].includes(state.prompt?.send_status)||state.phase==="RUNNING"))
      blockers.push({kind:"execution-not-terminal",task_id:id,phase:state.phase});
  }
  try {await lstat(join(unitRoot,".general-e2e","astronstudio-ui.lock"));
    blockers.push({kind:"ui-owner-lock"});}
  catch(error){if(error.code!=="ENOENT")throw error;}
  for(const id of await directories(join(unitRoot,".general-e2e","queues"))) {
    const path=join(unitRoot,".general-e2e","queues",id);
    let queue;try{queue=await json(join(path,"queue-state.json"));}catch(error){if(error.code==="ENOENT")continue;throw error;}
    if(!["COMPLETED","COMPLETED_WITH_FAILURES","FAILED"].includes(queue.phase))
      blockers.push({kind:"queue-not-closed",queue_id:id,phase:queue.phase});
    try {await lstat(join(path,"worker.lock"));blockers.push({kind:"queue-owner-lock",queue_id:id});}
    catch(error){if(error.code!=="ENOENT")throw error;}
  }
  if(blockers.length) {
    const error=Error("ASTUDIO_COLLECT_EXECUTION_ACTIVE");
    error.blockers=blockers;throw error;
  }
  return {checked_at:new Date().toISOString(),unit_root:resolve(unitRoot),task_id:taskId,blockers:[]};
}
export async function readRuntimeConfig(state) {
  if(!state.run_config?.path)return null;
  const config=await json(state.run_config.path);
  const {config_digest_algorithm:_algorithm,config_digest:_digest,...payload}=config;
  const calculated=hash(JSON.stringify(stable(payload)));
  if(config.schema_version!=="wildclawbench.general-e2e-astronstudio-run-config/v1"
      ||config.config_digest_algorithm!=="sha256-canonical-json/v1"
      ||calculated!==config.config_digest||calculated!==state.run_config.config_digest
      ||!config.state_database?.path)throw Error("ASTUDIO_RUNTIME_CONFIG_BINDING_INVALID");
  return config;
}
export function nativeSafetyBlockers(snapshot) {
  if(!snapshot||["sessions","orphan_sessions","pending_interactions","orphan_turns"].some(key=>!Array.isArray(snapshot[key])))
    throw Error("ASTUDIO_NATIVE_SAFETY_SNAPSHOT_INVALID");
  const blockers=[];
  for(const session of snapshot.sessions||[]) {
    if(session.active_turn_id||session.pending_count>0||!idle.has(String(session.status||"").toLowerCase()))
      blockers.push({kind:"native-session-not-idle",thread_id:session.thread_id,turn_id:session.turn_id,
        status:session.status,active_turn_id:session.active_turn_id,pending_count:session.pending_count??null});
  }
  for(const [key,kind] of [["orphan_sessions","orphan-native-session"],["pending_interactions","native-interaction-pending"],["orphan_turns","orphan-native-turn"]])
    for(const row of snapshot[key]||[])blockers.push({kind,...row});
  return blockers;
}
export function createCleanupGuard({unitRoot,state,snapshotProcesses,querySafety=queryNativeRuntimeSafety}) {
  let last;
  return async () => {
    const unit=await assertUnitExecutionQuiescent(unitRoot,state.identity.task_id);
    const config=await readRuntimeConfig(state);
    if(!config) {
      const processes=await snapshotProcesses();
      if(processes.infrastructure_roots?.length)throw Error("ASTUDIO_RUNTIME_GUARD_CONFIG_REQUIRED");
      last={...unit,native_check:"application-absent",legacy_config_missing:true};
      return last;
    }
    const snapshot=await querySafety(config.state_database.path);
    const blockers=nativeSafetyBlockers(snapshot);
    last={...unit,native_check:"queried",state_database:config.state_database.path,
      snapshot_sha256:hash(JSON.stringify(stable(snapshot))),sessions:snapshot.sessions.map(s=>({
        thread_id:s.thread_id,turn_id:s.turn_id,status:s.status,active_turn_id:s.active_turn_id
      })),settled_structured_ledgers:snapshot.settled_structured_ledgers||[],blockers};
    if(blockers.length){const error=Error("ASTUDIO_COLLECT_NATIVE_ACTIVITY");error.blockers=blockers;throw error;}
    return last;
  };
}
