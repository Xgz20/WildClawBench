#!/usr/bin/env node
// Conservative DoubaoWork Web queue: one UI/agent slot, exact manifest scope.
import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { lstat, mkdir, readFile, realpath, rename, writeFile } from "node:fs/promises";
import { isAbsolute, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { hostname } from "node:os";
import { acquireExclusiveWorkerLock, readWorkerLock } from "../../vendor/e2e-shared/doubaowork/controller.mjs";
import { snapshotTree, atomicWriteJson } from "../workbuddy/lib.mjs";
import { buildExecutionReceipt } from "../workbuddy/batch.mjs";
import { validatePreparedTaskRoot } from "./prepared-task.mjs";
import { isBoundNativeRequestId } from "./managed-peers.mjs";
import { verifyFormalReceipt } from "./formal.mjs";
import { DRIVER_VERSION } from "./lib.mjs";
const execFileAsync = promisify(execFile);
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const json = value => Buffer.from(`${JSON.stringify(value, null, 2)}\n`);
const SCHEMA = "wildclawbench.doubaowork-web-batch/v1";
const BATCH_VERSION = "1.1.1";
const STATUS = new Set(["PENDING", "DISPATCHING", "RUNNING", "NEEDS_ATTENTION", "SUCCEEDED", "INFRA_FAILED"]);
const terminal = new Set(["SUCCEEDED", "INFRA_FAILED"]);
const safeRunId = value => /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/u.test(value || "");
const driverFile = fileURLToPath(new URL("./driver.mjs", import.meta.url));

export function parseBatchArgs(argv) {
  const result = { resume: false, status: false, continueAttention: false, recoverStaleLock: false, adoptDriverVersion: false, adoptBatchVersion: false, runSlots: 1, observeSeconds: 60, projectPrefix: null };
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (["--resume", "--status", "--continue-attention", "--recover-stale-lock", "--adopt-driver-version", "--adopt-batch-version"].includes(key)) { result[{ "--resume": "resume", "--status": "status", "--continue-attention": "continueAttention", "--recover-stale-lock": "recoverStaleLock", "--adopt-driver-version": "adoptDriverVersion", "--adopt-batch-version": "adoptBatchVersion" }[key]] = true; continue; }
    if (!["--harness-root", "--run-id", "--run-slots", "--observe-seconds", "--project-prefix", "--endpoint", "--app-path"].includes(key)
        || i + 1 >= argv.length) throw new Error(`DOUBAOWORK_WEB_BATCH_ARG_INVALID:${key}`);
    const value = argv[++i];
    result[{ "--harness-root": "harnessRoot", "--run-id": "runId", "--run-slots": "runSlots", "--observe-seconds": "observeSeconds",
      "--project-prefix": "projectPrefix", "--endpoint": "endpoint", "--app-path": "appPath" }[key]] = value;
  }
  result.runSlots = Number(result.runSlots); result.observeSeconds = Number(result.observeSeconds);
  if (!result.projectPrefix && result.harnessRoot && safeRunId(result.runId)) {
    result.projectPrefix = `WCB-DW-Web-${sha(Buffer.from(`${resolve(result.harnessRoot)}\0${result.runId}`)).slice(0, 10)}`;
  }
  if (!result.harnessRoot || !isAbsolute(result.harnessRoot) || !safeRunId(result.runId)
      || (!Number.isInteger(result.runSlots) || result.runSlots < 1 || result.runSlots > 3) || !Number.isInteger(result.observeSeconds) || result.observeSeconds < 1 || result.observeSeconds > 900
      || !/^[\p{L}\p{N}][\p{L}\p{N}_-]{0,45}$/u.test(result.projectPrefix)) throw new Error("DOUBAOWORK_WEB_BATCH_CONFIG_INVALID");
  return result;
}

async function readOrdinaryJson(file) {
  let info;
  try { info = await lstat(file); } catch (error) { if (error.code === "ENOENT") return null; throw error; }
  if (!info.isFile() || info.isSymbolicLink() || await realpath(file) !== resolve(file)) throw new Error("DOUBAOWORK_WEB_BATCH_JSON_UNSAFE");
  return JSON.parse(await readFile(file, "utf8"));
}

function batchPaths(harnessRoot, runId) {
  const queueRoot = join(harnessRoot, ".execute-web-e2e", "doubaowork-batch", runId);
  return { queueRoot, stateFile: join(queueRoot, "state.json"), intentFile: join(queueRoot, "receipt-intent.json"), receiptFile: join(harnessRoot, "execution-receipt.json") };
}
function taskOutput(paths, taskId) { return join(paths.queueRoot, "tasks", taskId); }

export async function planFor(args) {
  const root = await realpath(args.harnessRoot);
  if (root !== resolve(args.harnessRoot)) throw new Error("DOUBAOWORK_WEB_BATCH_ROOT_SYMLINK");
  const raw = await readFile(join(root, "manifest.json"));
  const manifest = JSON.parse(raw);
  if (manifest.schema_version !== "wildclawbench.web-e2e-batch/v3" || manifest.harness?.id !== "doubaowork"
      || !Array.isArray(manifest.tasks) || manifest.tasks.length < 2 || manifest.tasks.length > 8) throw new Error("DOUBAOWORK_WEB_BATCH_MANIFEST_INVALID");
  const seen = new Set(), tasks = [];
  for (const entry of manifest.tasks) {
    if (!entry.task_id || seen.has(entry.task_id)) throw new Error("DOUBAOWORK_WEB_BATCH_TASK_DUPLICATE");
    seen.add(entry.task_id);
    const taskRoot = join(root, "execution", "tasks", entry.task_id);
    const config = await validatePreparedTaskRoot(taskRoot, { resume: args.resume || args.status, formal: true, batch: true, runId: args.runId });
    if (config.manifestSha256 !== sha(raw) || config.taskRoot !== taskRoot) throw new Error("DOUBAOWORK_WEB_BATCH_TASK_DRIFT");
    tasks.push({ task_id: entry.task_id, task_root: taskRoot, prompt_sha256: config.promptSha256,
      initial_sha256: config.frozenIdentity?.initial.sha256 ?? null, project_name: `${args.projectPrefix}-${String(tasks.length + 1).padStart(2, "0")}` });
  }
  return { root, manifest, manifestSha256: sha(raw), tasks, paths: batchPaths(root, args.runId) };
}

export function summarizeBatchConcurrency(rows, configuredSlots) {
  const overlap = (startKey, endKey) => {
    const points = [], missing = [];
    for (const row of rows) {
      const start = Date.parse(row[startKey]), end = Date.parse(row[endKey]);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) { missing.push(row.task_id); continue; }
      points.push([start, 1], [end, -1]);
    }
    points.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let running = 0, maximum = 0;
    for (const [, change] of points) { running += change; maximum = Math.max(maximum, running); }
    return { value: missing.length ? null : maximum, known_lower_bound: maximum,
      covered_tasks: rows.length - missing.length, missing_task_ids: missing };
  };
  return { configured_run_slots: configuredSlots, ui_slots: 1,
    scheduling_occupancy: overlap("prompt_sent_at", "slot_released_at"),
    native_agent_overlap: overlap("native_started_at", "native_finished_at"),
    native_source: "bound assistant elapsed_block.start_time_s/end_time_s" };
}

export function createBatchState(plan, args) {
  return { schema: SCHEMA, run_id: args.runId, harness_root: plan.root, manifest_sha256: plan.manifestSha256,
    driver_version: DRIVER_VERSION, worker: { id: "doubaowork-web-serial", version: BATCH_VERSION, host: hostname(), pid: null },
    ui_slots: 1, run_slots: args.runSlots, phase: "PREPARED", model: null, client_version: null,
    requested_ui_model: null, requested_endpoint: args.endpoint ?? null, requested_app_path: args.appPath ?? null,
    requested_permission_mode: "current", project_prefix: args.projectPrefix,
    tasks: plan.tasks.map(t => ({ ...t, phase: "PENDING", manual_interventions: [], child_pid: null,
      child_start_identity: null, launch_count: 0, attempt_id_sha256: null, final_sha256: null })),
    history: [{ event: "QUEUE_CREATED", at: new Date().toISOString() }] };
}

async function processStart(pid) {
  try { const { stdout } = await execFileAsync("ps", ["-p", String(pid), "-o", "lstart="], { timeout: 3000 }); return stdout.trim() || null; }
  catch { return null; }
}
export async function assertNoLiveChild(task) {
  if (!task.child_pid) return;
  if ((await processStart(task.child_pid)) === task.child_start_identity) throw new Error("DOUBAOWORK_WEB_BATCH_CHILD_STILL_LIVE");
}
export function assertStateMatches(state, plan, args, { allowVersionDrift = false, allowWorkerVersionDrift = false } = {}) {
  if (state?.schema !== SCHEMA || state.run_id !== args.runId || state.harness_root !== plan.root
      || state.manifest_sha256 !== plan.manifestSha256 || !allowVersionDrift && state.driver_version !== DRIVER_VERSION
      || !allowWorkerVersionDrift && state.worker?.version !== BATCH_VERSION
      || state.project_prefix !== args.projectPrefix || state.run_slots !== args.runSlots
      || (state.requested_endpoint ?? null) !== (args.endpoint ?? null)
      || (state.requested_app_path ?? null) !== (args.appPath ?? null)
      || JSON.stringify(state.tasks.map(t => t.task_id)) !== JSON.stringify(plan.tasks.map(t => t.task_id))) throw new Error("DOUBAOWORK_WEB_BATCH_PLAN_DRIFT");
  for (let i = 0; i < plan.tasks.length; i++) if (state.tasks[i].prompt_sha256 !== plan.tasks[i].prompt_sha256
      || (plan.tasks[i].initial_sha256 && state.tasks[i].initial_sha256 !== plan.tasks[i].initial_sha256) || !STATUS.has(state.tasks[i].phase)) throw new Error("DOUBAOWORK_WEB_BATCH_TASK_PLAN_DRIFT");
}

function driverArgs(task, state, paths, args, resume) {
  const argv = ["--output-dir", taskOutput(paths, task.task_id), "--formal-receipt", "--managed-run-id", state.run_id];
  if (resume) argv.push("--resume", "--observe-seconds", String(args.observeSeconds));
  else argv.push("--task-root", task.task_root, "--project-name", task.project_name);
  if (!resume && state.model) argv.push("--expected-ui-model", state.model);
  if (args.endpoint) argv.push("--endpoint", args.endpoint);
  if (args.appPath) argv.push("--app-path", args.appPath);
  return argv;
}

async function runDriver(task, state, plan, args, resume, save) {
  const output = taskOutput(plan.paths, task.task_id);
  await mkdir(output, { recursive: true });
  const log = join(output, `batch-driver-${String(task.launch_count + 1).padStart(4, "0")}.log`);
  const handle = await import("node:fs/promises").then(fs => fs.open(log, "wx", 0o600));
  const child = spawn(process.execPath, [driverFile, ...driverArgs(task, state, plan.paths, args, resume)], { stdio: ["ignore", handle.fd, handle.fd] });
  task.child_pid = child.pid; task.child_start_identity = await processStart(child.pid);
  if (!task.child_start_identity) throw new Error("DOUBAOWORK_WEB_BATCH_CHILD_IDENTITY_UNAVAILABLE");
  task.launch_count += 1; await save("DRIVER_LAUNCHED", { task_id: task.task_id, child_pid: child.pid, resume });
  const code = await new Promise((resolveCode, reject) => { child.once("error", reject); child.once("close", resolveCode); });
  await handle.close(); task.child_pid = null; task.child_start_identity = null;
  await save("DRIVER_EXITED", { task_id: task.task_id, exit_code: code });
  return code;
}


async function acquireQueueLock(paths, state, args) {
  try { return await acquireExclusiveWorkerLock(paths.queueRoot); }
  catch (error) {
    if (!args.recoverStaleLock || !args.resume || !state || !String(error.message).includes("foreign、stale")) throw error;
    const lockPath = join(paths.queueRoot, ".doubaowork-driver.lock");
    const old = await readWorkerLock(lockPath);
    if (old.host !== hostname() || await processStart(old.pid) === old.process_start_identity) throw error;
    for (const task of state.tasks) await assertNoLiveChild(task);
    const before = await readFile(lockPath), signature = sha(before);
    const archiveDir = join(paths.queueRoot, ".stale-locks");
    await mkdir(archiveDir, { recursive: true });
    if (sha(await readFile(lockPath)) !== signature) throw new Error("DOUBAOWORK_WEB_BATCH_LOCK_CHANGED");
    await rename(lockPath, join(archiveDir, `stale-${randomUUID()}.json`));
    return acquireExclusiveWorkerLock(paths.queueRoot);
  }
}
export function selectBatchTaskAction(state, journals, slots, cursor = 0) {
  if (!Number.isInteger(slots) || slots < 1 || slots > 3) throw new Error("DOUBAOWORK_WEB_RUN_SLOTS_INVALID");
  const blocked = state.tasks.find(t => t.phase === "NEEDS_ATTENTION");
  if (blocked) return { action: "pause", task_id: blocked.task_id };
  const recovering = state.tasks.find(t => t.phase === "DISPATCHING");
  if (recovering) return nextTaskAction({ tasks: [recovering] }, journals);
  const active = state.tasks.filter(t => t.phase === "RUNNING");
  const pending = state.tasks.find(t => t.phase === "PENDING");
  const peersBound = active.every(t => {
    const j = journals[t.task_id];
    return j?.send?.dispatch_attempt_count === 1
      && j.session?.prompt_readback?.status === "verified"
      && /^[0-9]{1,64}$/u.test(j.session?.conversation_id || "")
      && isBoundNativeRequestId(j.session?.native_request_session_id)
      && t.attempt_id_sha256 === sha(Buffer.from(j.attempt_id || ""));
  });
  if (pending && active.length < slots && peersBound) return { action: "dispatch", task_id: pending.task_id };
  if (active.length) return { action: "resume", task_id: active[cursor % active.length].task_id };
  if (pending) return { action: "pause", task_id: pending.task_id, reason: "PEER_BINDING_UNVERIFIED" };
  return { action: "receipt" };
}

export function nextTaskAction(state, journals) {
  for (const task of state.tasks) {
    if (terminal.has(task.phase)) continue;
    if (task.phase === "NEEDS_ATTENTION") return { action: "pause", task_id: task.task_id };
    const journal = journals[task.task_id] ?? null;
    if (!journal && task.phase === "PENDING") return { action: "dispatch", task_id: task.task_id };
    if (!journal) return { action: "pause", task_id: task.task_id, reason: "LAUNCH_INTENT_WITHOUT_JOURNAL" };
    if (journal.send?.dispatch_attempt_count !== 1) return { action: "pause", task_id: task.task_id, reason: "DISPATCH_NOT_CONFIRMED" };
    return { action: "resume", task_id: task.task_id };
  }
  return { action: "receipt" };
}

async function verifyTaskPublication(task, plan) {
  const output = taskOutput(plan.paths, task.task_id);
  const result = await verifyFormalReceipt(output);
  if (result.status !== "BATCH_TASK_VERIFIED") throw new Error("DOUBAOWORK_WEB_BATCH_PUBLICATION_INVALID");
  const formal = JSON.parse(await readFile(join(output, "formal-automation-state.json")));
  if (formal.identity?.task_id !== task.task_id || formal.identity?.batch_id !== plan.manifest.batch_id
      || formal.prepared?.run_id !== plan.paths.queueRoot.split(sep).at(-1)
      || !terminal.has(formal.phase) || !formal.actual?.model) throw new Error("DOUBAOWORK_WEB_BATCH_FORMAL_IDENTITY_DRIFT");
  return formal;
}

async function completeTask(task, state, plan, save) {
  const formal = await verifyTaskPublication(task, plan);
  if (state.model && state.model !== formal.actual.model) throw new Error("DOUBAOWORK_WEB_BATCH_MODEL_DRIFT");
  if (state.client_version && state.client_version !== formal.client.version) throw new Error("DOUBAOWORK_WEB_BATCH_CLIENT_VERSION_DRIFT");
  state.model ??= formal.actual.model; state.client_version ??= formal.client.version;
  task.phase = formal.phase; task.final_sha256 = formal.artifacts.final.sha256;
  task.prompt_sent_at = formal.timing.sent_at;
  task.slot_released_at = new Date().toISOString();
  task.native_started_at = formal.native_observation?.agent_started_at ?? null;
  task.native_finished_at = formal.native_observation?.agent_finished_at ?? null;
  task.attempt_id_sha256 = sha(Buffer.from(formal.attempt_id));
  await save("TASK_FORMAL_VERIFIED", { task_id: task.task_id, phase: task.phase, candidate_sha256: task.final_sha256 });
}

async function verifyReceipt(plan, state) {
  const bytes = await readFile(plan.paths.receiptFile);
  const intent = await readFile(plan.paths.intentFile);
  if (sha(bytes) !== sha(intent)) throw new Error("DOUBAOWORK_WEB_BATCH_RECEIPT_DRIFT");
  const receipt = JSON.parse(bytes);
  if (receipt.schema_version !== "wildclawbench.web-e2e-execution-receipt/v1" || receipt.run_id !== state.run_id
      || receipt.integrity?.valid !== true || receipt.scope?.matches_manifest !== true
      || JSON.stringify(receipt.tasks.map(t => t.task_id)) !== JSON.stringify(plan.tasks.map(t => t.task_id))) throw new Error("DOUBAOWORK_WEB_BATCH_RECEIPT_INVALID");
  for (let i = 0; i < plan.tasks.length; i++) {
    const snapshot = await snapshotTree(join(plan.tasks[i].task_root, "workspace"));
    if (snapshot.sha256 !== receipt.tasks[i].workspace?.final_sha256 || snapshot.forbidden_directories.length) throw new Error("DOUBAOWORK_WEB_BATCH_CANDIDATE_DRIFT");
  }
  return { status: "BATCH_RECEIPT_VERIFIED", receipt: plan.paths.receiptFile, task_count: plan.tasks.length };
}

async function publishBatchReceipt(plan, state, save) {
  if (state.tasks.some(t => !terminal.has(t.phase))) throw new Error("DOUBAOWORK_WEB_BATCH_SCOPE_INCOMPLETE");
  state.phase = state.tasks.some(t => t.phase === "INFRA_FAILED") ? "COMPLETED_WITH_FAILURES" : "COMPLETED";
  state.concurrency = summarizeBatchConcurrency(state.tasks, state.run_slots);
  await save("QUEUE_TERMINAL", { phase: state.phase });
  const tasks = plan.tasks.map(t => ({ taskId: t.task_id, taskRoot: t.task_root,
    automationStateFile: join(taskOutput(plan.paths, t.task_id), "formal-automation-state.json"),
    executionRecordFile: join(t.task_root, "execution_record.json") }));
  const receipt = await buildExecutionReceipt({ harnessRoot: plan.root, manifest: plan.manifest, tasks, queueStateFile: plan.paths.stateFile }, state, { harnessId: "doubaowork" });
  if (!receipt.integrity.valid) throw new Error("DOUBAOWORK_WEB_BATCH_RECEIPT_INTEGRITY_FAILED");
  const bytes = json(receipt);
  await writeFile(plan.paths.intentFile, bytes, { flag: "wx", mode: 0o600 });
  await writeFile(plan.paths.receiptFile, bytes, { flag: "wx", mode: 0o600 });
  return verifyReceipt(plan, state);
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseBatchArgs(argv), plan = await planFor(args);
  const old = await readOrdinaryJson(plan.paths.stateFile);
  if (args.status) { if (!old) throw new Error("DOUBAOWORK_WEB_BATCH_STATE_MISSING"); assertStateMatches(old, plan, args, { allowVersionDrift: true, allowWorkerVersionDrift: true });
    return { phase: old.phase, tasks: old.tasks.map(t => ({ task_id: t.task_id, phase: t.phase })), run_id: old.run_id }; }
  if (args.adoptBatchVersion && !args.resume) throw new Error("DOUBAOWORK_WEB_BATCH_WORKER_ADOPTION_REQUIRES_RESUME");
  if (args.adoptDriverVersion && !args.resume) throw new Error("DOUBAOWORK_WEB_BATCH_ADOPTION_REQUIRES_RESUME");
  if (args.recoverStaleLock && !args.resume) throw new Error("DOUBAOWORK_WEB_BATCH_RECOVERY_REQUIRES_RESUME");
  if (args.continueAttention && !args.resume) throw new Error("DOUBAOWORK_WEB_BATCH_CONTINUE_REQUIRES_RESUME");
  if (args.resume !== Boolean(old)) throw new Error(old ? "DOUBAOWORK_WEB_BATCH_REQUIRES_RESUME" : "DOUBAOWORK_WEB_BATCH_NEW_RUN_REJECTS_RESUME");
  const release = await acquireQueueLock(plan.paths, old, args);
  let interrupted = null;
  const onInterrupt = signal => { interrupted ??= signal; };
  const onInt = () => onInterrupt("SIGINT"), onTerm = () => onInterrupt("SIGTERM");
  process.on("SIGINT", onInt); process.on("SIGTERM", onTerm);
  try {
    const state = old ?? createBatchState(plan, args);
    if (state.driver_version !== DRIVER_VERSION) {
      const allowedUpgrade = ({ "0.7.2": "0.7.3", "0.7.4": "0.7.5", "0.7.5": "0.7.6", "0.7.6": "0.7.7" })[state.driver_version] === DRIVER_VERSION;
      if (!args.adoptDriverVersion || !allowedUpgrade)
        throw new Error("DOUBAOWORK_WEB_BATCH_VERSION_DRIFT");
      assertStateMatches(state, plan, args, { allowVersionDrift: true });
      for (const task of state.tasks.filter(t => !terminal.has(t.phase) && t.phase !== "PENDING")) {
        await assertNoLiveChild(task);
        const journal = await readOrdinaryJson(join(taskOutput(plan.paths, task.task_id), "automation_state.json"));
        if (!journal || journal.send?.dispatch_attempt_count !== 1 || journal.prepared?.run_id !== state.run_id
            || journal.identity?.task_id !== task.task_id || journal.client?.manifest_sha256 !== state.manifest_sha256)
          throw new Error("DOUBAOWORK_WEB_BATCH_ADOPTION_ATTEMPT_UNBOUND");
        const digest = sha(Buffer.from(journal.attempt_id));
        if (task.attempt_id_sha256 && task.attempt_id_sha256 !== digest) throw new Error("DOUBAOWORK_WEB_BATCH_ADOPTION_ATTEMPT_DRIFT");
        task.attempt_id_sha256 = digest;
      }
      const previous = state.driver_version;
      state.driver_version = DRIVER_VERSION;
      state.history.push({ event: "DRIVER_VERSION_ADOPTED", at: new Date().toISOString(), previous, current: DRIVER_VERSION,
        rule: "explicit-resume-original-attempt-only" });
      await atomicWriteJson(plan.paths.stateFile, state);
    }
    if (state.worker.version !== BATCH_VERSION) {
      if (!args.adoptBatchVersion || state.worker.version !== "1.1.0" || BATCH_VERSION !== "1.1.1")
        throw new Error("DOUBAOWORK_WEB_BATCH_WORKER_VERSION_DRIFT");
      assertStateMatches(state, plan, args, { allowWorkerVersionDrift: true });
      for (const task of state.tasks.filter(t => t.phase !== "PENDING" && !terminal.has(t.phase))) {
        await assertNoLiveChild(task);
        const journal = await readOrdinaryJson(join(taskOutput(plan.paths, task.task_id), "automation_state.json"));
        if (!journal || journal.send?.dispatch_attempt_count !== 1 || journal.prepared?.run_id !== state.run_id
            || journal.identity?.task_id !== task.task_id || journal.client?.manifest_sha256 !== state.manifest_sha256
            || task.attempt_id_sha256 !== sha(Buffer.from(journal.attempt_id)))
          throw new Error("DOUBAOWORK_WEB_BATCH_WORKER_ADOPTION_UNBOUND");
      }
      const previous = state.worker.version;
      state.worker.version = BATCH_VERSION;
      state.history.push({ event: "BATCH_WORKER_VERSION_ADOPTED", at: new Date().toISOString(), previous, current: BATCH_VERSION,
        rule: "explicit-resume-original-attempt-only" });
      await atomicWriteJson(plan.paths.stateFile, state);
    }
    assertStateMatches(state, plan, args);
    const save = async (event, detail = {}) => { state.worker.pid = process.pid; state.history.push({ event, at: new Date().toISOString(), ...detail });
      await atomicWriteJson(plan.paths.stateFile, state); };
    if (!old) await save("WORKER_STARTED"); else await save("WORKER_RESUMED");
    if (state.phase === "COMPLETED" || state.phase === "COMPLETED_WITH_FAILURES") {
      const intent = await readOrdinaryJson(plan.paths.intentFile);
      if (!intent) return publishBatchReceipt(plan, state, save);
      if (!await readOrdinaryJson(plan.paths.receiptFile)) await writeFile(plan.paths.receiptFile, json(intent), { flag: "wx", mode: 0o600 });
      return verifyReceipt(plan, state);
    }
    for (;;) {
      if (interrupted) {
        state.phase = "WORKER_INTERRUPTED";
        await save("WORKER_INTERRUPTED", { signal: interrupted });
        return { status: "WORKER_INTERRUPTED", signal: interrupted };
      }
      const journals = Object.fromEntries(await Promise.all(state.tasks.map(async t => [t.task_id,
        await readOrdinaryJson(join(taskOutput(plan.paths, t.task_id), "automation_state.json"))])));
      for (const task of state.tasks) if (await readOrdinaryJson(join(taskOutput(plan.paths, task.task_id), "formal-publication.json")) && !terminal.has(task.phase)) {
        await completeTask(task, state, plan, save);
      }
      let next = selectBatchTaskAction(state, journals, state.run_slots, state.history.filter(x => x.event === "TASK_RESUME_INTENT").length);
      if (next.action === "pause" && args.continueAttention && state.tasks.find(t => t.task_id === next.task_id)?.phase === "NEEDS_ATTENTION"
          && journals[next.task_id]?.send?.dispatch_attempt_count === 1) {
        state.tasks.find(t => t.task_id === next.task_id).phase = "RUNNING";
        state.phase = "RUNNING";
        args.continueAttention = false;
        await save("ATTENTION_EXPLICIT_RESUME", { task_id: next.task_id });
        next = selectBatchTaskAction(state, journals, state.run_slots, state.history.filter(x => x.event === "TASK_RESUME_INTENT").length);
      }
      if (next.action === "receipt") return publishBatchReceipt(plan, state, save);
      if (next.action === "pause") { state.phase = "NEEDS_ATTENTION"; await save("QUEUE_PAUSED", { task_id: next.task_id, reason: next.reason ?? "task-attention" });
        return { status: "NEEDS_ATTENTION", task_id: next.task_id, reason: next.reason ?? "task-attention" }; }
      const task = state.tasks.find(t => t.task_id === next.task_id);
      await assertNoLiveChild(task);
      if (next.action === "dispatch") {
        const initial = await snapshotTree(join(task.task_root, "workspace"));
        if (initial.sha256 !== task.initial_sha256 || initial.forbidden_directories.length) throw new Error("DOUBAOWORK_WEB_BATCH_PRE_SEND_CANDIDATE_DRIFT");
        task.phase = "DISPATCHING"; state.phase = "RUNNING"; await save("TASK_LAUNCH_INTENT", { task_id: task.task_id });
      } else { task.phase = "RUNNING"; state.phase = "RUNNING"; await save("TASK_RESUME_INTENT", { task_id: task.task_id }); }
      const exitCode = await runDriver(task, state, plan, args, next.action === "resume", save);
      if (await readOrdinaryJson(join(taskOutput(plan.paths, task.task_id), "formal-publication.json"))) { await completeTask(task, state, plan, save); continue; }
      const journal = await readOrdinaryJson(join(taskOutput(plan.paths, task.task_id), "automation_state.json"));
      if (journal?.send?.dispatch_attempt_count === 1 && journal.session?.prompt_readback?.status === "verified") {
        const digest = sha(Buffer.from(journal.attempt_id));
        if (task.attempt_id_sha256 && task.attempt_id_sha256 !== digest) throw new Error("DOUBAOWORK_WEB_BATCH_ATTEMPT_DRIFT");
        if (state.model && state.model !== journal.actual?.model) throw new Error("DOUBAOWORK_WEB_BATCH_MODEL_DRIFT");
        if (state.client_version && state.client_version !== journal.client?.version) throw new Error("DOUBAOWORK_WEB_BATCH_CLIENT_VERSION_DRIFT");
        task.attempt_id_sha256 = digest;
        state.model ??= journal.actual.model; state.client_version ??= journal.client.version;
        await save("TASK_BOUND", { task_id: task.task_id, attempt_id_sha256: digest });
      }
      if (!journal || journal.send?.dispatch_attempt_count !== 1 || exitCode !== 0 || journal.phase === "NEEDS_ATTENTION") {
        task.phase = "NEEDS_ATTENTION"; state.phase = "NEEDS_ATTENTION";
        await save("TASK_NEEDS_ATTENTION", { task_id: task.task_id, exit_code: exitCode,
          send_count: journal?.send?.dispatch_attempt_count ?? null });
        return { status: "NEEDS_ATTENTION", task_id: task.task_id, send_count: journal?.send?.dispatch_attempt_count ?? null };
      }
      task.phase = "RUNNING"; await save("TASK_OBSERVE_NEXT", { task_id: task.task_id });
    }
  } finally {
    process.off("SIGINT", onInt); process.off("SIGTERM", onTerm);
    await release();
  }
}

if (process.argv[1] && import.meta.url === new URL(`file://${resolve(process.argv[1])}`).href) {
  main().then(result => console.log(JSON.stringify(result, null, 2))).catch(e => { console.error(e.stack || e.message); process.exitCode = 1; });
}
