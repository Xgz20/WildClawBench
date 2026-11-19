import test from "node:test";
import assert from "node:assert/strict";
import {mkdtemp,mkdir,writeFile,readFile,rm,rename,symlink} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join,dirname} from "node:path";
import {createHash} from "node:crypto";
import {DatabaseSync} from "node:sqlite";
import {spawn} from "node:child_process";
import {calculateRunConfigDigest} from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/probe_astronstudio_macos.mjs";
import {selectDarwinTaskProcesses,terminateDarwinTaskProcesses,snapshotDarwinTaskProcesses}
  from "../../tools/report/e2e-shared/task-process-cleanup/macos-task-processes.mjs";
import {createCleanupGuard,nativeSafetyBlockers,assertUnitExecutionQuiescent}
  from "../../tools/report/e2e-shared/astronstudio-runtime/guard.mjs";
import {queryNativeRuntimeSafety} from "../../tools/report/e2e-shared/astronstudio-runtime/state.mjs";
import {captureRuntimeDiagnostics,loadDiagnosticArtifacts,projectKernelDiagnostic,redactDiagnosticText,
  appendFrameworkEvent,captureStandaloneDiagnostics,loadFrameworkAuditArtifacts}
  from "../../tools/report/e2e-shared/astronstudio-runtime/diagnostics.mjs";

const sha=b=>createHash("sha256").update(b).digest("hex");
const idle=()=>({sessions:[],orphan_sessions:[],pending_interactions:[],orphan_turns:[]});
async function temporary(fn) {
  const root=await mkdtemp(join(tmpdir(),"astudio-runtime-safety-"));
  try{return await fn(root);}finally{await rm(root,{recursive:true,force:true});}
}
const writeJson=async(path,value)=>{await mkdir(dirname(path),{recursive:true});await writeFile(path,JSON.stringify(value));};
function proc(pid,parent,command) {
  return {pid,parent_pid:parent,started_at:"Mon Nov 16 19:20:00 2026",command,command_name:command.split("/").at(-1).split(" ")[0],command_sha256:sha(command)};
}

test("a shared app-server matched by cwd is protected; unknown shared task descendants block cleanup",()=>{
  const ps=[proc(10,1,"/Applications/AStudio.app/Contents/MacOS/AStudio"),
    proc(11,10,"/app/acode-darwin-arm64 app-server"),proc(12,11,"/bin/sleep 60"),
    proc(20,1,"/bin/curl https://example.test")];
  const selected=selectDarwinTaskProcesses(ps,"/workspace/A",{cwdPids:[11,12,20]});
  assert.deepEqual(selected.targets.map(x=>x.pid),[20]);
  assert.deepEqual(selected.protected_processes.map(x=>x.pid),[11,12]);
  assert.deepEqual(selected.blocked_shared_processes.map(x=>x.pid),[12]);
  assert.equal(selected.protected_processes[0].matched_by_cwd,true);
  const bare=selectDarwinTaskProcesses(ps,"/workspace/A",{cwdPids:[11]});
  assert.equal(bare.targets.length,0);assert.equal(bare.blocked_shared_processes.length,0);
});
test("Loomy application and its bundled OpenCode service stay protected even when cwd names one task",()=>{
  const ps=[proc(10,1,"/Applications/Loomy.app/Contents/MacOS/Loomy"),
    proc(11,10,"opencode serve --hostname=127.0.0.1 --port=5054"),proc(12,11,"/bin/sleep 60"),
    proc(20,1,"/bin/python3 /workspace/A/tool.py")];
  const selected=selectDarwinTaskProcesses(ps,"/workspace/A",{cwdPids:[10,11,12,20]});
  assert.deepEqual(selected.targets.map(x=>x.pid),[20]);
  assert.deepEqual(selected.protected_processes.map(x=>x.pid),[10,11,12]);
  assert.deepEqual(selected.blocked_shared_processes.map(x=>x.pid),[12]);
  assert.equal(selected.infrastructure_roots.find(x=>x.pid===11).protection_reason,"shared-loomy-opencode");
});
test("a task wrapper holding a shared native child cannot be killed through ancestor selection",()=>{
  const ps=[proc(10,1,"/bin/sh /workspace/A/runner.sh"),proc(11,10,"/app/acode app-server")];
  const selected=selectDarwinTaskProcesses(ps,"/workspace/A",{cwdPids:[10]});
  assert.equal(selected.targets.length,0);
  assert.equal(selected.blocked_shared_processes[0].protection_reason,"shared-service-ancestor");
});
test("Codex control runtimes outside AStudio do not reclassify all evaluator children as AStudio services",()=>{
  const ps=[proc(10,1,"/Applications/Codex.app/bin/codex app-server"),proc(11,10,"/bin/sleep 60")];
  assert.deepEqual(selectDarwinTaskProcesses(ps,"/workspace/A",{cwdPids:[11]}).targets.map(x=>x.pid),[11]);
});
test("blocked shared task descendants produce evidence and zero signals",async()=>{
  const signals=[],base={supported:true,platform:"darwin",workspace:"/workspace/A",targets:[],seed_pids:[],root_pids:[],
    blocked_shared_processes:[{pid:99,protection_reason:"shared-service-descendant"}]};
  const result=await terminateDarwinTaskProcesses("/workspace/A",{snapshot:async()=>base,
    signalProcess:async(...x)=>{signals.push(x);},quietMilliseconds:0,waitMilliseconds:0});
  assert.equal(result.success,false);assert.equal(result.error,"SHARED_NATIVE_TASK_PROCESSES_ACTIVE");
  assert.deepEqual(signals,[]);
});
test("signal intent is durably observable before signalling, with actor and operation correlation",async()=>{
  const target=proc(90,1,"/bin/sleep 60"),events=[];let snapshots=0;
  const full={supported:true,platform:"darwin",workspace:"/workspace/A",targets:[target],seed_pids:[90],root_pids:[90]};
  const empty={...full,targets:[],seed_pids:[],root_pids:[]};
  const result=await terminateDarwinTaskProcesses("/workspace/A",{snapshot:async()=>snapshots++===0?full:empty,
    audit:async e=>events.push(e.event),signalProcess:async()=>{assert.equal(events.at(-1),"process.signal.intent");events.push("OS-signal");return {identity_matched:true,exit_code:0,error:null};},
    quietMilliseconds:0,waitMilliseconds:0,termGraceMilliseconds:0});
  assert.equal(result.success,true);assert.deepEqual(events.slice(-3),["process.signal.intent","OS-signal","process.signal.result"]);
  const record=result.termination_attempts[0];assert.equal(record.actor_pid,process.pid);
  assert.equal(record.operation_id,result.operation_id);assert.ok(Date.parse(record.result_at)>=Date.parse(record.intent_at));
});
test("a failed intent journal or a newly active native peer prevents the OS signal",async()=>{
  const target=proc(90,1,"/bin/sleep 60"),base={supported:true,platform:"darwin",workspace:"/workspace/A",targets:[target],seed_pids:[90],root_pids:[90]};
  let signals=0;
  await assert.rejects(terminateDarwinTaskProcesses("/workspace/A",{snapshot:async()=>base,
    audit:async event=>{if(event.event==="process.signal.intent")throw Error("audit storage unavailable");},
    signalProcess:async()=>{signals++;},quietMilliseconds:0,waitMilliseconds:0}),/audit storage/);
  let checks=0;
  await assert.rejects(terminateDarwinTaskProcesses("/workspace/A",{snapshot:async()=>base,
    assertSafe:async()=>{if(++checks===2)throw Error("new native activity");},
    signalProcess:async()=>{signals++;},quietMilliseconds:0,waitMilliseconds:0}),/new native activity/);
  assert.equal(signals,0);
});
test("another accepted task or an open queue blocks formal collection before cleanup",()=>temporary(async root=>{
  await writeJson(join(root,".general-e2e/execution/B/automation-state.json"),{phase:"RUNNING",send:{dispatch_attempt_count:1}});
  await assert.rejects(assertUnitExecutionQuiescent(root,"A"),/EXECUTION_ACTIVE/);
  await writeJson(join(root,".general-e2e/execution/B/automation-state.json"),{phase:"COMPLETED",send:{dispatch_attempt_count:1}});
  await writeJson(join(root,".general-e2e/queues/disjoint/queue-state.json"),{phase:"RUNNING",tasks:[{task_id:"B"}]});
  await assert.rejects(assertUnitExecutionQuiescent(root,"A"),/EXECUTION_ACTIVE/);
  await writeJson(join(root,".general-e2e/queues/disjoint/queue-state.json"),{phase:"COMPLETED",tasks:[{task_id:"B"}]});
  await writeFile(join(root,".general-e2e/queues/disjoint/worker.lock"),"owned");
  await assert.rejects(assertUnitExecutionQuiescent(root,"A"),/EXECUTION_ACTIVE/);
  await rm(join(root,".general-e2e/queues/disjoint/worker.lock"));
  assert.equal((await assertUnitExecutionQuiescent(root,"A")).blockers.length,0);
}));
test("unknown native status, pending interactions and orphan turns are never idle evidence",()=>{
  for(const patch of [{sessions:[{thread_id:"X",status:"unknown"}]},
    {sessions:[{thread_id:"X",status:"ready",active_turn_id:"turn"}]},
    {orphan_sessions:[{thread_id:"orphan",status:"running"}]},
    {pending_interactions:[{thread_id:"orphan",pending_count:1}]},
    {orphan_turns:[{thread_id:"orphan",turn_id:"turn"}]}])assert.ok(nativeSafetyBlockers({...idle(),...patch}).length);
  assert.deepEqual(nativeSafetyBlockers(idle()),[]);
  assert.throws(()=>nativeSafetyBlockers({}),/SNAPSHOT_INVALID/);
});
test("a legacy state without frozen config is accepted only with no live native infrastructure",()=>temporary(async root=>{
  const state={identity:{task_id:"A"}};
  const absent=createCleanupGuard({unitRoot:root,state,snapshotProcesses:async()=>({infrastructure_roots:[]})});
  assert.equal((await absent()).native_check,"application-absent");
  const present=createCleanupGuard({unitRoot:root,state,snapshotProcesses:async()=>({infrastructure_roots:[{pid:4}]})});
  await assert.rejects(present(),/CONFIG_REQUIRED/);
}));
test("frozen config binding is revalidated and an active session in another project blocks cleanup",()=>temporary(async root=>{
  const config={schema_version:"wildclawbench.general-e2e-astronstudio-run-config/v1",
    config_digest_algorithm:"sha256-canonical-json/v1",state_database:{path:join(root,"state.sqlite")}};
  config.config_digest=calculateRunConfigDigest(config);
  const path=join(root,"run-config.json");await writeJson(path,config);
  const state={identity:{task_id:"A"},run_config:{path,config_digest:config.config_digest}};
  let active=true,queries=0;
  const guard=createCleanupGuard({unitRoot:root,state,querySafety:async()=>{
    queries++;return {...idle(),sessions:active?[{thread_id:"other-project",status:"running",active_turn_id:"live"}]:[]};
  }});
  await assert.rejects(guard(),/NATIVE_ACTIVITY/);
  active=false;assert.equal((await guard()).native_check,"queried");
  config.state_database.path=join(root,"different.sqlite");await writeJson(path,config);
  await assert.rejects(guard(),/BINDING_INVALID/);assert.equal(queries,2);
}));
test("native safety reads deleted-project sessions and unjoined pending/open-turn state from a real readonly snapshot",()=>temporary(async root=>{
  const file=join(root,"state.sqlite"),db=new DatabaseSync(file);
  db.exec(`
    CREATE TABLE projection_threads(thread_id TEXT,project_id TEXT,latest_turn_id TEXT,deleted_at TEXT);
    CREATE TABLE projection_projects(project_id TEXT,workspace_root TEXT,deleted_at TEXT);
    CREATE TABLE projection_turns(row_id INTEGER,thread_id TEXT,turn_id TEXT,state TEXT,termination_origin TEXT,requested_at TEXT,started_at TEXT,completed_at TEXT,checkpoint_turn_count INTEGER);
    CREATE TABLE projection_thread_sessions(thread_id TEXT,status TEXT,active_turn_id TEXT,last_error TEXT,updated_at TEXT);
    CREATE TABLE projection_pending_interactions(thread_id TEXT,status TEXT);
    CREATE TABLE provider_session_runtime(thread_id TEXT,status TEXT,runtime_payload_json TEXT,resume_cursor_json TEXT);
    CREATE TABLE provider_runtime_open_turns(thread_id TEXT,turn_id TEXT,updated_at TEXT);
    CREATE TABLE provider_runtime_events(thread_id TEXT,turn_id TEXT,event_type TEXT,persisted_at TEXT);
    INSERT INTO projection_threads VALUES('A','project','turn',NULL);
    INSERT INTO projection_projects VALUES('project','/workspace/A',NULL);
    INSERT INTO projection_turns VALUES(1,'A','turn','completed',NULL,'2026-11-01T00:00:00Z','2026-11-01T00:00:00Z','2026-11-01T00:01:00Z',NULL);
    INSERT INTO projection_thread_sessions VALUES('A','ready',NULL,NULL,'2026-11-01T00:01:00Z');
    INSERT INTO provider_session_runtime VALUES('A','stopped','{}','{"threadId":"session"}');
    INSERT INTO projection_thread_sessions VALUES('deleted','running','live',NULL,'2026-11-01T00:01:00Z');
    INSERT INTO projection_pending_interactions VALUES('orphan-pending','pending');
    INSERT INTO provider_runtime_open_turns VALUES('orphan-turn','live','2026-11-01T00:01:00Z');
  `);db.close();
  const before=sha(await readFile(file)),result=await queryNativeRuntimeSafety(file);
  assert.equal(result.sessions.length,1);
  assert.equal(result.orphan_sessions[0].thread_id,"deleted");
  assert.equal(result.pending_interactions[0].thread_id,"orphan-pending");
  assert.equal(result.orphan_turns[0].thread_id,"orphan-turn");
  assert.equal(sha(await readFile(file)),before);
}));
test("diagnostics omit credential login frames and redact plain, escaped and bearer secrets",()=>{
  const secrets=["sk-abc123","opaque-secret","jwt-secret"];
  const input='apiKey="sk-abc123" accessToken=opaque-secret authorization=Bearer jwt-secret '+String.raw`{\"password\":\"secret-password\"}`;
  const safe=redactDiagnosticText(input);
  for(const s of [...secrets,"secret-password"])assert.ok(!safe.includes(s));
  assert.equal(projectKernelDiagnostic({feedback_log_body:'received raw app-server frame from client raw_frame={"id":2,"method":"account/login/start","params":{"accessToken":"secret"}}'}),null);
  const row=projectKernelDiagnostic({id:5,feedback_log_body:'received raw app-server frame from client raw_frame={"id":4,"method":"turn/interrupt","params":{"threadId":"thread","turnId":"turn","accessToken":"secret"}}'});
  assert.deepEqual(row.frame,{id:4,method:"turn/interrupt",threadId:"thread",turnId:"turn"});
  assert.ok(!JSON.stringify(row).includes('"secret"'));
});
test("concurrent audit appends remain parseable and omit caller-supplied secrets",()=>temporary(async root=>{
  const file=join(root,"events.jsonl");
  await Promise.all(Array.from({length:40},(_,n)=>appendFrameworkEvent(file,{event:"test",n,apiKey:"secret-value",prompt:"private prompt"})));
  const raw=await readFile(file,"utf8"),rows=raw.trim().split("\n").map(JSON.parse);
  assert.equal(rows.length,40);assert.equal(new Set(rows.map(x=>x.actor_sequence)).size,40);
  assert.ok(!raw.includes("secret-value"));assert.ok(!raw.includes("private prompt"));
  await appendFrameworkEvent(file,{event:"actor",actor_pid:999,origin:"spoofed"});
  const last=JSON.parse((await readFile(file,"utf8")).trim().split("\n").at(-1));
  assert.equal(last.actor_pid,process.pid);assert.equal(last.origin,"evaluation-framework");
  const before=sha(await readFile(file));
  await assert.rejects(appendFrameworkEvent(file,{event:"over-budget"},{maxBytes:1}),/AUDIT_BUDGET/);
  assert.equal(sha(await readFile(file)),before);
}));
test("journal evidence preserves original line order and discloses an incomplete trailing append",()=>temporary(async root=>{
  const file=join(root,".general-e2e/diagnostics/framework-events.jsonl");
  await appendFrameworkEvent(file,{event:"first"});
  const complete=await readFile(file);
  await writeFile(file,Buffer.concat([complete,Buffer.from('{"event":"partial')]));
  const before=sha(await readFile(file)),artifacts=await loadFrameworkAuditArtifacts(root);
  assert.deepEqual(artifacts[0].bytes,complete);
  const metadata=JSON.parse(artifacts[1].bytes);
  assert.equal(metadata.retained_lines,1);assert.equal(metadata.source_start_line,1);
  assert.ok(metadata.trailing_incomplete_bytes>0);assert.equal(metadata.retained_sha256,sha(complete));
  assert.equal(sha(await readFile(file)),before);
}));
test("diagnostic output budget does not disable later alarm detection; repeated identical forced faults are throttled",()=>temporary(async root=>{
  const config={stateFile:join(root,"control/automation-state.json"),candidateWorkspace:root};
  const state={identity:{task_id:"A",attempt_id:"attempt"},session:{},execution:{},evidence:{}};
  const file=join(root,"userdata/logs/server-child.log");await mkdir(dirname(file),{recursive:true});await writeFile(file,"startup\n");
  let databases=0;
  const opts={readConfig:async()=>({state_database:{path:join(root,"userdata/state.sqlite")}}),
    processSnapshot:async()=>({infrastructure_roots:[]}),databases:async()=>{databases++;return {fixture:true};},maxBytes:10,intervalMs:0};
  await captureRuntimeDiagnostics(config,state,opts);
  await writeFile(file,"startup\nserver.shutdown.stage.started\n");
  const ref=await captureRuntimeDiagnostics(config,state,opts);
  assert.equal(databases,1);state.evidence.runtime_diagnostics=ref;
  const artifacts=await loadDiagnosticArtifacts(state,config.stateFile);
  assert.ok(artifacts.some(x=>x.bytes.toString().includes('"new_alarm_count": 1')));
  await captureRuntimeDiagnostics(config,state,{...opts,reason:"repeat-fault",force:true});
  await captureRuntimeDiagnostics(config,state,{...opts,reason:"repeat-fault",force:true});
  assert.equal(databases,2);
}));
test("periodic sampling is throttled; log alarms escalate while preserving incomplete-line cursors",()=>temporary(async root=>{
  const config={stateFile:join(root,"control/automation-state.json"),candidateWorkspace:join(root,"workspace")};
  const state={identity:{batch_id:"batch",unit_id:"unit",task_id:"task",attempt_id:"attempt"},session:{},execution:{},evidence:{}};
  const dbPath=join(root,"userdata/state.sqlite"),log=join(root,"userdata/logs/server-child.log");
  await mkdir(dirname(log),{recursive:true});await writeFile(log,"ordinary startup\n");
  let samples=0,dbCaptures=0;
  const deps={readConfig:async()=>({state_database:{path:dbPath}}),
    processSnapshot:async()=>{samples++;return {infrastructure_roots:[]};},
    databases:async()=>{dbCaptures++;return {fixture:true};}};
  state.evidence.runtime_diagnostics=await captureRuntimeDiagnostics(config,state,deps);
  await captureRuntimeDiagnostics(config,state,deps);assert.equal(samples,1);assert.equal(dbCaptures,0);
  await writeFile(log,"ordinary startup\nabandoning stalled Acode turn accessToken=secret");
  await captureRuntimeDiagnostics(config,state,{...deps,intervalMs:0});assert.equal(dbCaptures,0);
  await writeFile(log,"ordinary startup\nabandoning stalled Acode turn accessToken=secret\n");
  state.evidence.runtime_diagnostics=await captureRuntimeDiagnostics(config,state,{...deps,intervalMs:0});
  assert.equal(dbCaptures,1);
  const artifacts=await loadDiagnosticArtifacts(state,config.stateFile);
  assert.ok(artifacts.length>=3);
  assert.ok(!artifacts.map(x=>x.bytes.toString()).join("").includes("accessToken=secret"));
  await writeFile(artifacts.at(-1).path,"tampered");
  await assert.rejects(loadDiagnosticArtifacts(state,config.stateFile),/HASH_MISMATCH/);
}));
test("a new attempt preserves the previous diagnostic index and artifacts",()=>temporary(async root=>{
  const config={stateFile:join(root,"control/automation-state.json"),candidateWorkspace:root};
  const first={identity:{task_id:"A",attempt_id:"first"},session:{},execution:{},evidence:{}};
  const options={readConfig:async()=>{throw Error("fixture-unavailable");},processSnapshot:async()=>({infrastructure_roots:[]})};
  first.evidence.runtime_diagnostics=await captureRuntimeDiagnostics(config,first,options);
  const artifacts=await loadDiagnosticArtifacts(first,config.stateFile);
  const before=artifacts.map(x=>[x.path,sha(x.bytes)]);
  const second={...first,identity:{...first.identity,attempt_id:"second"},evidence:{}};
  second.evidence.runtime_diagnostics=await captureRuntimeDiagnostics(config,second,options);
  assert.notEqual(second.evidence.runtime_diagnostics.index_path,first.evidence.runtime_diagnostics.index_path);
  for(const [path,digest] of before)assert.equal(sha(await readFile(path)),digest);
  assert.equal((await loadDiagnosticArtifacts(first,config.stateFile)).length,artifacts.length);
  assert.equal((await loadDiagnosticArtifacts(second,config.stateFile)).length,2);
}));
test("an explicit readonly manual capture creates a new output and preserves its source state",()=>temporary(async root=>{
  const workspace=join(root,"execution/tasks/A/workspace"),stateFile=join(root,".general-e2e/execution/A/automation-state.json");
  await mkdir(workspace,{recursive:true});
  const identity={batch_id:"batch",unit_id:"unit",task_id:"A",attempt_id:"attempt"};
  await writeJson(join(root,"manifest.json"),{batch_id:"batch",unit_id:"unit",task_ids:["A"]});
  await writeJson(stateFile,{identity,session:{},execution:{},evidence:{},candidate_workspace:workspace});
  const original=await readFile(stateFile),output=join(root,"manual-capture");
  const result=await captureStandaloneDiagnostics({unitRoot:root,stateFile,outputDir:output});
  assert.equal(result.read_only,true);assert.equal(result.score_changed,false);
  assert.equal(sha(await readFile(stateFile)),sha(original));
  assert.ok((await readFile(join(output,"receipt.json"))).length);
  await assert.rejects(captureStandaloneDiagnostics({unitRoot:root,stateFile,outputDir:output}),/EEXIST/);
  await assert.rejects(captureStandaloneDiagnostics({unitRoot:root,stateFile,outputDir:join(workspace,"bad")}),/OUTPUT_IN_CANDIDATE/);
}));
test("real process canary: shared acode survives cwd-based cleanup; only the independent owned task is terminated",
  {skip:process.platform!=="darwin"},()=>temporary(async root=>{
    const binary=join(root,"acode");await symlink(process.execPath,binary);
    const script=join(root,"daemon.mjs");await writeFile(script,"setInterval(()=>{},1000);");
    const workspace=join(root,"workspace");await mkdir(workspace);
    const shared=spawn(binary,[script,"app-server"],{cwd:workspace,stdio:"ignore"});
    const owned=spawn("/bin/sleep",["30"],{cwd:workspace,stdio:"ignore"});
    try {
      await Promise.all([shared,owned].map(c=>new Promise((r,e)=>{c.once("spawn",r);c.once("error",e);})));
      const snapshot=await snapshotDarwinTaskProcesses(workspace);
      assert.ok(snapshot.protected_processes.some(x=>x.pid===shared.pid));
      assert.deepEqual(snapshot.targets.map(x=>x.pid),[owned.pid]);
      const result=await terminateDarwinTaskProcesses(workspace,{quietMilliseconds:100,waitMilliseconds:1500,termGraceMilliseconds:50});
      assert.equal(result.success,true);
      assert.ok(result.termination_attempts.every(x=>x.pid===owned.pid));
      assert.equal(shared.exitCode,null);assert.equal(shared.signalCode,null);
    } finally {
      for(const child of [shared,owned])if(child.exitCode===null&&child.signalCode===null){child.kill("SIGTERM");await new Promise(r=>child.once("exit",r));}
    }
  }));
