import assert from "node:assert/strict";
import test from "node:test";
import {createHash} from "node:crypto";
import {applyQueueSourceRepair} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/doubaowork/batch.mjs";
const sha=b=>createHash("sha256").update(b).digest("hex");

test("runtime repair binds the exact paused queue and preserves every sent and pending attempt",()=>{
  const old={queue_id:"q",unit_root:"/unit",task_ids:["t1","t2"],run_slots:3,source_root:"/old",source_digest:"a".repeat(64)};
  const config={...old,source_root:"/new",source_digest:"b".repeat(64)};
  const state={schema:"wildclawbench.doubaowork-general-queue/v1",config:old,config_digest:sha(JSON.stringify(old)),status:"NEEDS_ATTENTION",
    tasks:[{task_id:"t1",attempt_id:"sent-once",dispatch_attempt_count:1,phase:"NEEDS_ATTENTION"},{task_id:"t2",attempt_id:null,dispatch_attempt_count:0,phase:"PENDING"}],history:[]};
  const bytes=Buffer.from(JSON.stringify(state));
  const repair={schema_version:1,reason:"bounded route observation repair",queue_id:"q",unit_root:"/unit",original_source_sha256:old.source_digest,
    patched_source_sha256:config.source_digest,original_queue_sha256:sha(bytes),preserve_attempts:true};
  const result=applyQueueSourceRepair(state,config,repair,bytes);
  assert.deepEqual(result.tasks,state.tasks);assert.equal(result.config.source_digest,config.source_digest);assert.equal(state.config.source_root,"/old");
  assert.throws(()=>applyQueueSourceRepair(state,{...config,run_slots:1},repair,bytes),/SOURCE_REPAIR_INVALID/);
  assert.throws(()=>applyQueueSourceRepair(state,config,{...repair,original_queue_sha256:"c".repeat(64)},bytes),/SOURCE_REPAIR_INVALID/);
  assert.throws(()=>applyQueueSourceRepair({...state,status:"RUNNING"},config,repair,bytes),/SOURCE_REPAIR_INVALID/);
});

test("pre-journal recovery accepts only the exact missing-session-root failure with no send boundary", () => {
  const old={queue_id:"q",unit_root:"/unit",task_ids:["t"],run_slots:3,source_root:"/old",source_digest:"a".repeat(64)};
  const config={...old,source_root:"/new",source_digest:"b".repeat(64)};
  const state={schema:"wildclawbench.doubaowork-general-queue/v1",config:old,config_digest:sha(JSON.stringify(old)),status:"NEEDS_ATTENTION",
    tasks:[{task_id:"t",attempt_id:null,dispatch_attempt_count:0,phase:"NEEDS_ATTENTION"}],
    error:{task_id:"t",phase:"prepare-project",native:null,worker:{message:"ENOENT: no such file or directory, lstat '/native/.sessions'\n"}},
    history:[{task_id:"t",event:"PROJECT_PREPARATION_INTENT"}]};
  const bytes=Buffer.from(JSON.stringify(state));
  const repair={schema_version:1,reason:"lazy native directory inventory",queue_id:"q",unit_root:"/unit",original_source_sha256:old.source_digest,
    patched_source_sha256:config.source_digest,original_queue_sha256:sha(bytes),preserve_attempts:true,retry_pre_journal_preparation_task_id:"t"};
  assert.equal(applyQueueSourceRepair(state,config,repair,bytes).tasks[0].phase,"PENDING");
  assert.equal(state.tasks[0].phase,"NEEDS_ATTENTION");
  for (const patch of [{attempt_id:"a"},{dispatch_attempt_count:1},{phase:"DISPATCHING"}]) {
    const changed=structuredClone(state);Object.assign(changed.tasks[0],patch);
    const raw=Buffer.from(JSON.stringify(changed));
    assert.throws(()=>applyQueueSourceRepair(changed,config,{...repair,original_queue_sha256:sha(raw)},raw),/PRE_JOURNAL_RECOVERY_UNVERIFIED/);
  }
  const changed=structuredClone(state);changed.error.worker.message="Timeout waiting for send";
  const raw=Buffer.from(JSON.stringify(changed));
  assert.throws(()=>applyQueueSourceRepair(changed,config,{...repair,original_queue_sha256:sha(raw)},raw),/PRE_JOURNAL_RECOVERY_UNVERIFIED/);
});
