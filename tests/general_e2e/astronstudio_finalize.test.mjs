import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { chmod, mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { readBoundNativeLogBundle } from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-native-provider-log.mjs';
import { normalizeTraceRows } from '../../tools/report/e2e-shared/general-resource-supplements/archive_astronstudio_trace.mjs';
import { normalizeRolloutTranscript } from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout-transcript.mjs';
import { collectAstronStudioResourceMetrics } from '../../tools/report/e2e-shared/general-resource-supplements/collect_astronstudio_resource_metrics.mjs';
import { prepareTerminalFinalRecapture, recaptureCandidateTree } from '../../tools/report/e2e-shared/general-resource-supplements/astronstudio-terminal-final-recapture.mjs';
import { archiveAstronStudioTrace } from '../../tools/report/e2e-shared/general-resource-supplements/archive_astronstudio_trace.mjs';
import { recaptureFixture, writeRecaptureInput } from './fixtures/terminal-final-recapture.mjs';
import { DatabaseSync } from 'node:sqlite';

import {
  finalizeAstronStudioExecution,
  parseArgs,
  verifyAstronStudioCollection,
} from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/finalize_astronstudio_execution.mjs";
import {
  parseDarwinProcessTable,
  selectDarwinTaskProcesses,
  terminateDarwinTaskProcesses,
} from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/lib/macos-task-processes.mjs";

const DATASET_DIGEST = "1".repeat(64);

function digest(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`);
}

function identity(taskId = "task-fixture", attemptId = "attempt-fixture") {
  return {
    batch_id: "batch-fixture",
    unit_id: "astronstudio-macos-x86-64",
    task_id: taskId,
    attempt_id: attemptId,
  };
}

function successfulCleanup() {
  return {
    schema_version: "wildclawbench.general-e2e-task-process-cleanup/v1",
    supported: true,
    platform: "darwin",
    success: true,
    quiet_window_milliseconds: 0,
    quiet_observed_milliseconds: 0,
    late_process_detected: false,
    before: { supported: true, targets: [], seed_pids: [], root_pids: [] },
    termination_attempts: [],
    after: { supported: true, targets: [], seed_pids: [], root_pids: [] },
  };
}

function metric(value, status = "observed") {
  return { value, status, basis: "fixture" };
}

async function fixture({
  businessStatus = "completed",
  traceStatus = "complete",
  includeTrace = true,
  includeResource = true,
  taskId = "task-fixture",
  attemptId = "attempt-fixture",
} = {}) {
  const root = await mkdtemp(join(tmpdir(), "general-e2e-finalize-fixture-"));
  const taskIdentity = identity(taskId, attemptId);
  const taskRoot = join(root, "execution", "tasks", taskId);
  const workspace = join(taskRoot, "workspace");
  const stateRoot = join(root, ".general-e2e", "execution", taskId);
  const traceRoot = join(root, "fixture-input", "trace");
  await mkdir(workspace, { recursive: true });
  await mkdir(stateRoot, { recursive: true });
  await mkdir(join(traceRoot, "raw"), { recursive: true });
  await mkdir(join(root, "receipts"), { recursive: true });
  await writeFile(join(workspace, "answer.txt"), "candidate\n");
  const prompt = Buffer.from("Do the task.\n", "utf8");
  const promptPath = join(taskRoot, "PROMPT.md");
  await writeFile(promptPath, prompt);
  const finalResponse = Buffer.from("Done.\n", "utf8");
  const finalResponseRelative = `.general-e2e/execution/${taskId}/final-response.md`;
  await writeFile(join(stateRoot, "final-response.md"), finalResponse);

  const manifest = {
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1",
    schema_version: 1,
    manifest_kind: "execution",
    batch_id: taskIdentity.batch_id,
    unit_id: taskIdentity.unit_id,
    dataset: { id: "general-custom60-v1", digest: DATASET_DIGEST },
    task_ids: [taskId],
    tasks: [{
      task_id: taskId,
      prompt: { path: `execution/tasks/${taskId}/PROMPT.md`, sent_sha256: digest(prompt) },
      workspace: { path: `execution/tasks/${taskId}/workspace` },
    }],
    unit: {
      harness: { id: "astronstudio", platform: "macos-x86-64", version: "3.3.1" },
      model: { requested_id: "GLM-5.2", reasoning_effort: "high" },
    },
  };
  await writeJson(join(root, "manifest.json"), manifest);

  const state = {
    schema_version: "wildclawbench.general-e2e-astronstudio-execution-state/v1",
    identity: taskIdentity,
    dataset: { id: "general-custom60-v1", digest: DATASET_DIGEST },
    phase: businessStatus === "completed" ? "COMPLETED" : "FAILED",
    task_root: taskRoot,
    candidate_workspace: workspace,
    prompt: {
      path: promptPath,
      sha256: digest(prompt),
      send_status: "sent",
      sent_at: "2026-09-18T00:00:01.000Z",
    },
    send: { dispatch_attempt_count: 1 },
    session: {
      thread_id: "thread-fixture",
      turn_id: "turn-fixture",
      session_id: "session-fixture",
      cwd: workspace,
      verified: true,
      native_status: businessStatus === "completed" ? "completed" : "stopped",
    },
    client: { version: "3.3.1", model: "GLM-5.2", reasoning: "High" },
    execution: {
      business_status: businessStatus,
      started_at: "2026-09-18T00:00:00.000Z",
      finished_at: "2026-09-18T00:00:10.000Z",
      duration_seconds: 10,
      agent_duration_seconds: null,
      error: businessStatus === "completed" ? null : `${businessStatus} fixture`,
    },
    evidence: {
      final_response_path: finalResponseRelative,
      final_response_sha256: digest(finalResponse),
    },
    human_assistance: { mode: "automatic", operation_count: 0, semantic_intervention_count: 0 },
  };
  if (["timeout", "cancelled"].includes(businessStatus)) {
    state.timeout = { cancellation_confirmed: true };
  }
  const statePath = join(stateRoot, "automation-state.json");
  await writeJson(statePath, state);
  await writeJson(join(stateRoot, "execution-record.json"), { provisional: true });

  let indexPath = "";
  let metricsPath = "";
  if (includeTrace) {
    const transcript = Buffer.from('{"event":"fixture"}\n', "utf8");
    const raw = Buffer.from('{"raw":"fixture"}\n', "utf8");
    await writeFile(join(traceRoot, "transcript.jsonl"), transcript);
    await writeFile(join(traceRoot, "raw", "astronstudio-provider-events.jsonl"), raw);
    const index = {
      schema_id: "urn:wildclawbench:schema:general-e2e:trace-index:v1",
      schema_version: 1,
      identity: taskIdentity,
      session: {
        thread_id: state.session.thread_id,
        turn_id: state.session.turn_id,
        session_id: state.session.session_id,
        cwd: workspace,
      },
      transcript: { path: "transcript.jsonl", sha256: digest(transcript), size: transcript.length },
      raw_trace: [{ path: "raw/astronstudio-provider-events.jsonl", sha256: digest(raw), size: raw.length }],
      completeness: {
        status: traceStatus,
        omitted_event_count: traceStatus === "complete" ? 0 : 1,
        missing: traceStatus === "complete" ? [] : ["turn.completed"],
      },
    };
    indexPath = join(traceRoot, "trace-index.json");
    await writeJson(indexPath, index);
    if (includeResource) {
      const stateBytes = await readFile(statePath);
      const indexBytes = await readFile(indexPath);
      const metrics = {
        schema_id: "urn:wildclawbench:schema:general-e2e:resource-metrics:v1",
        schema_version: 1,
        identity: taskIdentity,
        collection: {
          status: traceStatus === "complete" ? "complete" : "partial",
          sources: [
            { path: "execution/automation-state.json", sha256: digest(stateBytes), size: stateBytes.length },
            { path: "trace/trace-index.json", sha256: digest(indexBytes), size: indexBytes.length },
            { path: "trace/raw/astronstudio-provider-events.jsonl", sha256: digest(raw), size: raw.length },
          ],
        },
        metrics: {
          usage: {
            input_tokens: metric(10), output_tokens: metric(2), total_tokens: metric(12),
            cache_read_input_tokens: metric(5), cache_creation_input_tokens: metric(null, "unavailable"),
            reasoning_output_tokens: metric(1),
          },
          requests: { request_count: metric(1, "inferred"), request_attempt_count: metric(null, "unavailable") },
          tools: { call_count: metric(0) },
          timing: { duration_seconds: metric(10), agent_duration_seconds: metric(4) },
        },
      };
      metricsPath = join(root, "fixture-input", "resource-metrics.json");
      await writeJson(metricsPath, metrics);
    }
  }
  return { root, taskId, attemptId, workspace, statePath, indexPath, metricsPath };
}

function options(value) {
  return {
    unitRoot: value.root,
    stateFile: value.statePath,
    traceIndex: value.indexPath,
    resourceMetrics: value.metricsPath,
    candidatePolicy: "",
    stabilityMilliseconds: 0,
    processQuietMilliseconds: 0,
    processWaitMilliseconds: 0,
  };
}

test('native log resource production includes binding closure and passes real finalize plus verify-only', async () => {
  const value = await fixture({ includeTrace: false, includeResource: false });
  try {
    const stateBytes = await readFile(value.statePath), state = JSON.parse(stateBytes);
    const time = n => `2026-09-18T00:00:${String(n).padStart(2,'0')}.000Z`;
    const notification = (id, method, payload, n) => ({ id, kind:'notification', method,
      threadId:state.session.thread_id, turnId:state.session.turn_id,
      providerThreadId:state.session.session_id, lifecycleGeneration:'native-life', createdAt:time(n),
      ...(payload.item ? { itemId:payload.item.id } : {}), payload });
    const notifications = [
      notification('start','turn/started',{turn:{id:state.session.turn_id,status:'inProgress'}},1),
      notification('user','item/completed',{item:{id:'user-item',type:'userMessage',content:[{text:'Do the task.\n'}]}},2),
      notification('assistant','item/completed',{item:{id:'assistant-item',type:'agentMessage',text:'Done.'}},9),
      notification('end','turn/completed',{turn:{id:state.session.turn_id,status:'completed',error:null}},10),
    ];
    const nativeBytes = Buffer.from(notifications.map(e=>`[${e.createdAt}] NTIVE: ${JSON.stringify(e)}`).join('\n')+'\n');
    const input = join(value.root,'native-input'); await mkdir(input);
    const nativeSource = join(input,'native.log'); await writeFile(nativeSource,nativeBytes);
    const provenanceBytes = Buffer.from(JSON.stringify({selected_lines:4,selected_bytes_sha256:digest(nativeBytes),
      sources:[{source_path:'/synthetic/provider.log',captured_source_sha256:digest(nativeBytes),captured_size:nativeBytes.length,selected_original_line_numbers:[1,2,3,4]}]}));
    await writeFile(join(input,'provenance.json'),provenanceBytes);
    const sourceManifest = {schema_version:'wildclawbench.astronstudio-native-provider-log-bundle/v1',
      identity:state.identity,session:state.session,execution_state_sha256:digest(stateBytes),
      native_log:{path:'native.log',sha256:digest(nativeBytes),size:nativeBytes.length},
      provenance:{path:'provenance.json',sha256:digest(provenanceBytes),size:provenanceBytes.length}};
    await writeJson(join(input,'manifest.json'),sourceManifest);
    const parsed = await readBoundNativeLogBundle(join(input,'manifest.json'),state,stateBytes);
    const r=(type,payload,n)=>({timestamp:time(n),type,payload});
    const sdkRows = [r('session_meta',{id:state.session.session_id,cwd:state.session.cwd},0),
      r('event_msg',{type:'task_started',turn_id:state.session.turn_id},1),
      r('turn_context',{turn_id:state.session.turn_id,cwd:state.session.cwd},1),
      r('event_msg',{type:'user_message',message:'Do the task.\n'},2),
      r('event_msg',{type:'agent_message',message:'Done.'},9),
      r('response_item',{type:'message',role:'assistant',content:[{type:'output_text',text:'Done.'}]},9),
      r('event_msg',{type:'task_complete',turn_id:state.session.turn_id,last_agent_message:'Done.',duration_ms:9000},10)];
    const sdkBytes=Buffer.from(sdkRows.map(e=>JSON.stringify(e)).join('\n')+'\n');
    const provider=normalizeTraceRows(parsed.rows,state);
    const normalized=normalizeRolloutTranscript(sdkBytes,state,{...provider,projection_rows:parsed.rows},{sourcePolicy:'bound-native-sdk'});
    const trace=join(value.root,'fixture-input','trace');await mkdir(join(trace,'raw'),{recursive:true});
    const transcript=Buffer.from(normalized.events.map(e=>JSON.stringify(e)).join('\n')+'\n');
    const ref=(path,bytes)=>({path,sha256:digest(bytes),size:bytes.length});
    await writeFile(join(trace,parsed.raw_path),nativeBytes);
    await writeFile(join(trace,'raw/astronstudio-rollout.jsonl'),sdkBytes);
    await writeFile(join(trace,'transcript.jsonl'),transcript);
    for(const a of parsed.binding_artifacts){await mkdir(join(trace,'bindings'),{recursive:true});await writeFile(join(trace,a.path),a.bytes);}
    const index={schema_id:'urn:wildclawbench:schema:general-e2e:trace-index:v1',schema_version:1,identity:state.identity,
      adapter:{id:'astronstudio-provider-runtime-events',version:'0.3.1',source:'bound_rollout_transcript+bound_native_provider_log_audit'},
      session:{thread_id:state.session.thread_id,turn_id:state.session.turn_id,session_id:state.session.session_id,cwd:state.session.cwd,lifecycle_generation:parsed.lifecycle_generation},
      transcript:{...ref('transcript.jsonl',transcript),event_count:normalized.events.length},
      raw_trace:[ref(parsed.raw_path,nativeBytes),ref('raw/astronstudio-rollout.jsonl',sdkBytes)],
      binding_evidence:parsed.binding_artifacts.map(a=>ref(a.path,a.bytes)),
      native_provider_log_profile:{id:'bound-native-provider-log/v1',runtime_turn_projection_event_count:0,native_notification_count:4,comparison_rows_are_database_sequences:false},
      canonical_source_policy:{id:'bound-native-sdk-canonical/v1'},completeness:normalized.completeness,calls:normalized.calls};
    value.indexPath=join(trace,'trace-index.json');await writeJson(value.indexPath,index);
    value.metricsPath=join(trace,'resource-metrics.json');
    await collectAstronStudioResourceMetrics({stateFile:value.statePath,traceIndex:value.indexPath,output:value.metricsPath});
    const metrics=JSON.parse(await readFile(value.metricsPath,'utf8'));
    assert.equal(metrics.collection.sources.length,7);
    assert.equal(metrics.collection.sources.filter(s=>s.path.startsWith('trace/bindings/')).length,3);
    const result=await finalizeAstronStudioExecution(options(value),{terminateProcesses:async()=>successfulCleanup()});
    assert.equal(result.status,'PASS');
    await verifyAstronStudioCollection({unitRoot:value.root,taskId:value.taskId});
  } finally { await rm(value.root,{recursive:true,force:true}); }
});

test('authorized terminal recapture passes archive, metrics, finalize and immutable verify with original proof closure', async () => {
  const value = await fixture({ includeTrace: false, includeResource: false });
  try {
    const data = recaptureFixture(JSON.parse(await readFile(value.statePath, 'utf8')));
    data.candidateBefore = data.candidateAfter = await recaptureCandidateTree(value.workspace);
    await writeJson(value.statePath, data.originalState);
    await writeFile(join(value.root, data.originalState.evidence.final_response_path), data.originalFinal);
    const originalState = await readFile(value.statePath);
    const inputManifest = await writeRecaptureInput(join(value.root, 'input'), data);
    const prepared = await prepareTerminalFinalRecapture({ inputManifest, outputDir: join(value.root, 'recapture') });
    const databasePath = join(value.root, 'native.sqlite'), db = new DatabaseSync(databasePath);
    db.exec(`CREATE TABLE projection_projects(project_id TEXT,workspace_root TEXT);
      CREATE TABLE projection_threads(thread_id TEXT,project_id TEXT);
      CREATE TABLE projection_turns(thread_id TEXT,turn_id TEXT,state TEXT,requested_at TEXT,started_at TEXT,completed_at TEXT);
      CREATE TABLE provider_runtime_events(sequence INTEGER,event_id TEXT,thread_id TEXT,turn_id TEXT,lifecycle_generation TEXT,event_type TEXT,event_json TEXT,persisted_at TEXT);`);
    db.prepare('INSERT INTO projection_projects VALUES(?,?)').run('project', data.originalState.session.cwd);
    db.prepare('INSERT INTO projection_threads VALUES(?,?)').run(data.originalState.session.thread_id, 'project');
    db.prepare('INSERT INTO projection_turns VALUES(?,?,?,?,?,?)').run(data.originalState.session.thread_id, data.originalState.session.turn_id,
      'completed', '2026-09-18T00:00:00.000Z', '2026-09-18T00:00:01.000Z', '2026-09-18T00:00:10.000Z');
    const insert = db.prepare('INSERT INTO provider_runtime_events VALUES(?,?,?,?,?,?,?,?)');
    for (const r of data.provider) insert.run(r.sequence,r.event_id,r.thread_id,r.turn_id,r.lifecycle_generation,r.event_type,r.event_json,r.persisted_at);
    db.close();
    const trace = join(value.root, 'recapture/trace');
    const sdkFile = join(value.root, 'input/inputs/sdk.json');
    await assert.rejects(archiveAstronStudioTrace({ stateFile: value.statePath, stateDb: databasePath, rolloutFile: sdkFile,
      sourcePolicy: 'bound-native-sdk', outputDir: join(value.root, 'original-rejected-trace') }), /ARCHIVED_FINAL_RESPONSE_MISMATCH/);
    const archived = await archiveAstronStudioTrace({ stateFile: prepared.state_file, stateDb: databasePath, rolloutFile: sdkFile,
      sourcePolicy: 'bound-native-sdk', terminalFinalRecaptureManifest: prepared.manifest, outputDir: trace });
    assert.equal(archived.status, 'PASS');
    await assert.rejects(archiveAstronStudioTrace({ stateFile: prepared.state_file, stateDb: databasePath, rolloutFile: sdkFile,
      sourcePolicy: 'bound-native-sdk', outputDir: join(value.root, 'missing-manifest-rejected') }), /RECAPTURE_MANIFEST_REQUIRED/);
    value.statePath = prepared.state_file; value.indexPath = join(trace, 'trace-index.json'); value.metricsPath = join(trace, 'resource-metrics.json');
    await collectAstronStudioResourceMetrics({ stateFile: value.statePath, traceIndex: value.indexPath, output: value.metricsPath });
    const metrics = JSON.parse(await readFile(value.metricsPath, 'utf8'));
    assert.equal(metrics.collection.sources.length, 19);
    const result = await finalizeAstronStudioExecution(options(value), { terminateProcesses: async () => successfulCleanup() });
    assert.equal(result.status, 'PASS');
    await verifyAstronStudioCollection({ unitRoot: value.root, taskId: value.taskId });
    assert.deepEqual(await readFile(join(value.root, '.general-e2e/execution', value.taskId, 'automation-state.json')), originalState);
    const frozen = join(result.evidence_root, 'trace/bindings/terminal-final-recapture/inputs/original_final.md');
    assert.deepEqual(await readFile(frozen), data.originalFinal);
    await rm(frozen);
    await assert.rejects(verifyAstronStudioCollection({ unitRoot: value.root, taskId: value.taskId }), /ENOENT|EVIDENCE|ARTIFACT/);
  } finally { await rm(value.root, { recursive: true, force: true }); }
});

test("CLI separates finalization from immutable verification", () => {
  assert.throws(() => parseArgs([]), /--unit-root/u);
  assert.throws(() => parseArgs(["--unit-root", "/tmp/unit"]), /--state-file/u);
  assert.throws(
    () => parseArgs(["--verify-only", "--unit-root", "/tmp/unit"]),
    /--task-id/u,
  );
  assert.equal(parseArgs(["--help"]).help, true);
});

async function addBinding(value) {
  const index=JSON.parse(await readFile(value.indexPath,'utf8'));
  const directory=join(value.indexPath,'..','bindings');await mkdir(directory,{recursive:true});
  const data=Buffer.from('{"synthetic":"native provenance"}\n');
  await writeFile(join(directory,'native.json'),data);
  index.binding_evidence=[{path:'bindings/native.json',sha256:digest(data),size:data.length}];
  await writeJson(value.indexPath,index);
  const metrics=JSON.parse(await readFile(value.metricsPath,'utf8')),bytes=await readFile(value.indexPath);
  Object.assign(metrics.collection.sources.find(r=>r.path==='trace/trace-index.json'),{sha256:digest(bytes),size:bytes.length});
  metrics.collection.sources.push({path:'trace/bindings/native.json',sha256:digest(data),size:data.length});
  await writeJson(value.metricsPath,metrics);return data;
}

test('AstronStudio v1 copies every binding file and verifies its archived reference closure',async()=>{
  const value=await fixture();
  try {
    const original=await addBinding(value);
    const result=await finalizeAstronStudioExecution(options(value),{terminateProcesses:async()=>successfulCleanup()});
    const archived=join(result.evidence_root,'trace/bindings/native.json');
    assert.deepEqual(await readFile(archived),original);
    await verifyAstronStudioCollection({unitRoot:value.root,taskId:value.taskId});
    // Reproduce a collector that omitted a referenced binding and then wrote
    // otherwise self-consistent manifest/receipt inventories.
    await rm(archived);
    const manifestPath=join(result.evidence_root,'evidence-manifest.json'),manifest=JSON.parse(await readFile(manifestPath,'utf8'));
    manifest.artifacts=manifest.artifacts.filter(r=>!r.path.endsWith('/trace/bindings/native.json'));await writeJson(manifestPath,manifest);
    const receiptPath=join(value.root,'receipts/collect-evidence-receipt.json'),receipt=JSON.parse(await readFile(receiptPath,'utf8')),bytes=await readFile(manifestPath);
    Object.assign(receipt.artifacts.find(r=>r.path.endsWith('/evidence-manifest.json')),{sha256:digest(bytes),size:bytes.length});await writeJson(receiptPath,receipt);
    await assert.rejects(verifyAstronStudioCollection({unitRoot:value.root,taskId:value.taskId}),/ENOENT|TRACE_ARTIFACT/);
  } finally {await rm(value.root,{recursive:true,force:true});}
});

test('missing or tampered binding evidence rejects before freezing a candidate',async()=>{
  for(const change of ['missing','hash','escape']) {
    const value=await fixture();
    try {
      await addBinding(value);
      if(change==='missing')await rm(join(value.indexPath,'..','bindings/native.json'));
      else {
        const index=JSON.parse(await readFile(value.indexPath,'utf8'));
        if(change==='hash')index.binding_evidence[0].sha256='0'.repeat(64);
        else index.binding_evidence[0].path='../escaped.json';
        await writeJson(value.indexPath,index);
      }
      await assert.rejects(finalizeAstronStudioExecution(options(value),{terminateProcesses:async()=>{throw Error('cleanup must not run');}}),/ENOENT|ARTIFACT|artifact/);
    } finally {await rm(value.root,{recursive:true,force:true});}
  }
});

test("completed execution freezes an exact candidate and creates a verified receipt", async () => {
  const value = await fixture();
  try {
    const result = await finalizeAstronStudioExecution(options(value), {
      now: () => "2026-09-18T00:00:20.000Z",
      terminateProcesses: async () => successfulCleanup(),
    });
    assert.equal(result.status, "PASS");
    assert.equal(result.receipt_status, "completed");
    const record = JSON.parse(await readFile(join(result.evidence_root, "execution-record.json"), "utf8"));
    assert.equal(record.evidence.completeness, "complete");
    assert.equal(record.execution.agent_duration_seconds, 4);
    assert.equal(record.candidate.drift_status, "stable");
    const verified = await verifyAstronStudioCollection({ unitRoot: value.root, taskId: value.taskId });
    assert.equal(verified.status, "PASS");
    assert.equal(verified.candidate_sha256, result.candidate_sha256);
    const siblingPath = "evidence/tasks/sibling-task/sibling-attempt/process-cleanup.json";
    const siblingBytes = Buffer.from("{\"sibling\":true}\n", "utf8");
    await mkdir(join(value.root, "evidence", "tasks", "sibling-task", "sibling-attempt"), { recursive: true });
    await writeFile(join(value.root, siblingPath), siblingBytes);
    const receiptPath = join(value.root, "receipts", "collect-evidence-receipt.json");
    const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
    receipt.artifacts.push({
      path: siblingPath,
      sha256: digest(siblingBytes),
      size: siblingBytes.length,
    });
    receipt.artifacts.sort((left, right) => left.path.localeCompare(right.path));
    await writeJson(receiptPath, receipt);
    const verifiedWithSibling = await verifyAstronStudioCollection({
      unitRoot: value.root,
      taskId: value.taskId,
    });
    assert.equal(verifiedWithSibling.status, "PASS");
    await assert.rejects(
      finalizeAstronStudioExecution(options(value), {
        terminateProcesses: async () => successfulCleanup(),
      }),
      /OUTPUT_EXISTS/u,
    );
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});

test("existing receipt fails before process cleanup or evidence publication", async () => {
  const value = await fixture({ attemptId: "attempt-existing-receipt" });
  let cleanupCalled = false;
  try {
    await writeFile(join(value.root, "receipts", "collect-evidence-receipt.json"), "occupied\n");
    await assert.rejects(
      finalizeAstronStudioExecution(options(value), {
        terminateProcesses: async () => {
          cleanupCalled = true;
          return successfulCleanup();
        },
      }),
      /OUTPUT_EXISTS/u,
    );
    assert.equal(cleanupCalled, false);
    await assert.rejects(
      readFile(join(value.root, "evidence", "tasks", value.taskId, value.attemptId, "execution-record.json")),
      /ENOENT/u,
    );
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});

test("verification fails closed after source or frozen candidate drift", async () => {
  const value = await fixture();
  try {
    const result = await finalizeAstronStudioExecution(options(value), {
      terminateProcesses: async () => successfulCleanup(),
    });
    await writeFile(join(result.evidence_root, "candidate", "workspace", "answer.txt"), "drift\n");
    await assert.rejects(
      verifyAstronStudioCollection({ unitRoot: value.root, taskId: value.taskId }),
      /EVIDENCE_MANIFEST_SCOPE_MISMATCH|EVIDENCE_ARTIFACT_DIGEST_MISMATCH|候选产物发生漂移/u,
    );
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }

  const sourceValue = await fixture({ attemptId: "attempt-source-drift" });
  try {
    await finalizeAstronStudioExecution(options(sourceValue), {
      terminateProcesses: async () => successfulCleanup(),
    });
    await writeFile(join(sourceValue.workspace, "late.txt"), "late\n");
    await assert.rejects(
      verifyAstronStudioCollection({ unitRoot: sourceValue.root, taskId: sourceValue.taskId }),
      /候选产物发生漂移/u,
    );
  } finally {
    await rm(sourceValue.root, { recursive: true, force: true });
  }
});

test("verification rejects omitted manifest artifacts and candidate mode drift", async () => {
  const manifestValue = await fixture({ attemptId: "attempt-manifest-omission" });
  try {
    const result = await finalizeAstronStudioExecution(options(manifestValue), {
      terminateProcesses: async () => successfulCleanup(),
    });
    const manifestPath = join(result.evidence_root, "evidence-manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    manifest.artifacts.pop();
    await writeJson(manifestPath, manifest);
    const receiptPath = join(manifestValue.root, "receipts", "collect-evidence-receipt.json");
    const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
    const bytes = await readFile(manifestPath);
    const row = receipt.artifacts.find((item) => item.path.endsWith("/evidence-manifest.json"));
    row.sha256 = digest(bytes);
    row.size = bytes.length;
    await writeJson(receiptPath, receipt);
    await assert.rejects(
      verifyAstronStudioCollection({ unitRoot: manifestValue.root, taskId: manifestValue.taskId }),
      /EVIDENCE_MANIFEST_SCOPE_MISMATCH/u,
    );
  } finally {
    await rm(manifestValue.root, { recursive: true, force: true });
  }

  const modeValue = await fixture({ attemptId: "attempt-mode-drift" });
  try {
    const result = await finalizeAstronStudioExecution(options(modeValue), {
      terminateProcesses: async () => successfulCleanup(),
    });
    await chmod(join(result.evidence_root, "candidate", "workspace", "answer.txt"), 0o755);
    await assert.rejects(
      verifyAstronStudioCollection({ unitRoot: modeValue.root, taskId: modeValue.taskId }),
      /CANDIDATE_ARTIFACT_SCOPE_MISMATCH/u,
    );
  } finally {
    await rm(modeValue.root, { recursive: true, force: true });
  }
});

test("process cleanup and stability failures stop before candidate publication", async () => {
  const cleanupFailure = await fixture({ attemptId: "attempt-cleanup-failure" });
  try {
    await assert.rejects(
      finalizeAstronStudioExecution(options(cleanupFailure), {
        terminateProcesses: async () => ({ supported: true, success: false, error: "residual process" }),
      }),
      /TASK_PROCESS_CLEANUP_FAILED/u,
    );
  } finally {
    await rm(cleanupFailure.root, { recursive: true, force: true });
  }

  const unstable = await fixture({ attemptId: "attempt-unstable" });
  try {
    await assert.rejects(
      finalizeAstronStudioExecution({ ...options(unstable), stabilityMilliseconds: 1 }, {
        terminateProcesses: async () => successfulCleanup(),
        sleep: async () => writeFile(join(unstable.workspace, "late.txt"), "late\n"),
      }),
      /WORKSPACE_NOT_STABLE/u,
    );
  } finally {
    await rm(unstable.root, { recursive: true, force: true });
  }
});

test("timeout keeps partial trace and infrastructure failure remains a partial stage", async () => {
  const timeout = await fixture({
    businessStatus: "timeout",
    traceStatus: "partial",
    includeResource: false,
    attemptId: "attempt-timeout",
  });
  try {
    const result = await finalizeAstronStudioExecution(options(timeout), {
      terminateProcesses: async () => successfulCleanup(),
    });
    const record = JSON.parse(await readFile(join(result.evidence_root, "execution-record.json"), "utf8"));
    assert.equal(record.execution.business_status, "timeout");
    assert.equal(record.evidence.completeness, "partial");
    assert.equal(result.receipt_status, "completed");
  } finally {
    await rm(timeout.root, { recursive: true, force: true });
  }

  const infrastructure = await fixture({
    businessStatus: "infrastructure_error",
    includeTrace: false,
    includeResource: false,
    attemptId: "attempt-infrastructure",
  });
  try {
    const result = await finalizeAstronStudioExecution(options(infrastructure), {
      terminateProcesses: async () => successfulCleanup(),
    });
    assert.equal(result.receipt_status, "partial");
    const record = JSON.parse(await readFile(join(result.evidence_root, "execution-record.json"), "utf8"));
    assert.equal(record.evidence.completeness, "unavailable");
    assert.equal(record.evidence.final_response_path, null);
    assert.equal(record.execution.business_status, "infrastructure_error");
  } finally {
    await rm(infrastructure.root, { recursive: true, force: true });
  }
});

test("a bound native candidate failure freezes its proof without relabelling an intermediate reply as final", async () => {
  const value=await fixture({businessStatus:"candidate_error",includeResource:false,attemptId:"native-failure-proof"});
  try{
    const state=JSON.parse(await readFile(value.statePath,"utf8"));
    state.session.native_status="error";state.execution.error={code:"ASTRONSTUDIO_TURN_ERROR",message:"native max_output_tokens"};
    await writeJson(value.statePath,state);
    const result=await finalizeAstronStudioExecution(options(value),{terminateProcesses:async()=>successfulCleanup()});
    const record=JSON.parse(await readFile(join(result.evidence_root,"execution-record.json"),"utf8"));
    assert.equal(record.execution.business_status,"candidate_error");assert.equal(record.evidence.final_response_path,null);
    assert.equal(record.failure_evidence.schema,"verified-failed-output-evidence/v1");
    const proofBytes=await readFile(join(value.root,record.failure_evidence.path));
    assert.equal(digest(proofBytes),record.failure_evidence.sha256);
    const proof=JSON.parse(proofBytes);assert.deepEqual(proof.identity,record.identity);
    const verified=await verifyAstronStudioCollection({unitRoot:value.root,taskId:value.taskId});
    assert.equal(verified.status,"PASS");
  }finally{await rm(value.root,{recursive:true,force:true});}
});

test("candidate freeze rejects an escaping symlink", async () => {
  const value = await fixture({ attemptId: "attempt-symlink" });
  try {
    await symlink("/tmp", join(value.workspace, "escape"));
    await assert.rejects(
      finalizeAstronStudioExecution(options(value), {
        terminateProcesses: async () => successfulCleanup(),
      }),
      /CANDIDATE_SYMLINK_ESCAPES_ROOT/u,
    );
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});

test("macOS process selection uses exact command or cwd seeds and includes descendants", () => {
  const workspace = "/tmp/general-e2e/task/workspace";
  const table = parseDarwinProcessTable(`
  100 1 Thu Sep 18 01:02:03 2026 /bin/sleep 30
  101 100 Thu Sep 18 01:02:04 2026 /usr/bin/python child.py
  102 1 Thu Sep 18 01:02:05 2026 /usr/bin/python /tmp/general-e2e/task/workspace/run.py
  103 1 Thu Sep 18 01:02:06 2026 /usr/bin/python /tmp/general-e2e/task/workspace-other/run.py
  `);
  const selected = selectDarwinTaskProcesses(table, workspace, { cwdPids: [100] });
  assert.deepEqual(selected.seed_pids, [100, 102]);
  assert.deepEqual(selected.targets.map((item) => item.pid), [100, 101, 102]);
  assert.equal(selected.targets.find((item) => item.pid === 101).descendant_of_seed, true);
});

test("macOS live cleanup terminates only the process whose cwd is the candidate", {
  skip: process.platform !== "darwin",
}, async () => {
  const root = await mkdtemp(join(tmpdir(), "general-e2e-process-cleanup-"));
  const workspace = join(root, "workspace");
  await mkdir(workspace);
  const child = spawn("/bin/sh", ["-c", `cd "${workspace}" && exec /bin/sleep 30`], {
    stdio: "ignore",
  });
  try {
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
    const result = await terminateDarwinTaskProcesses(workspace, {
      quietMilliseconds: 250,
      waitMilliseconds: 3_000,
      termGraceMilliseconds: 100,
    });
    assert.equal(result.success, true);
    assert.ok(result.before.targets.some((item) => item.pid === child.pid));
    assert.equal(result.after.targets.length, 0);
  } finally {
    try { child.kill("SIGKILL"); } catch {}
    await rm(root, { recursive: true, force: true });
  }
});
