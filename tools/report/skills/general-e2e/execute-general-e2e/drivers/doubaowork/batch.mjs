#!/usr/bin/env node
import { execFile as execFileCallback } from "node:child_process";
import { promisify, parseArgs } from "node:util";
import { createHash, randomUUID } from "node:crypto";
import { lstat, readFile, realpath, rename, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { acquireExclusiveWorkerLock } from "../../vendor/e2e-shared/doubaowork/controller.mjs";
import { validateGeneralTask } from "./prepared-task.mjs";
import { DEFAULT_APP_PATH, DEFAULT_ENDPOINT } from "../../vendor/e2e-shared/doubaowork/lib.mjs";
import { startTrajectoryArchivePump } from "../../vendor/e2e-shared/doubaowork/trajectory-archive.mjs";

const execFile = promisify(execFileCallback), HERE = dirname(fileURLToPath(import.meta.url));
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const now = () => new Date().toISOString();
const sleep = ms => new Promise(r => setTimeout(r, ms));

export function decideQueueTaskAction(row, journal) {
  if (row.phase === "PENDING") return journal ? "reject-existing-attempt" : "dispatch";
  if (["PREPARING", "PREPARED"].includes(row.phase)) {
    if (!journal?.prepared_project || journal.phase !== "WORKSPACE_CONFIRMED" || journal.send?.dispatch_attempt_count !== 0
        || journal.send.intent_persisted_at || (row.attempt_id && row.attempt_id !== journal.attempt_id)) return "pause";
    return row.phase === "PREPARING" ? "prepared" : "dispatch-prepared";
  }
  if (!journal || journal.send?.dispatch_attempt_count !== 1) return "pause";
  if (row.attempt_id && row.attempt_id !== journal.attempt_id) return "reject-attempt-drift";
  if (journal.native_observation?.terminal === "completed") return "complete";
  return "observe";
}

export function selectQueueAction(rows, slots, cursor = 0) {
  const recovering = rows.find(r => ["DISPATCHING", "NEEDS_ATTENTION"].includes(r.phase));
  if (recovering) return { task_id: recovering.task_id, action: "observe" };
  const active = rows.filter(r => r.phase === "RUNNING");
  const next = rows.find(r => ["PENDING", "PREPARED"].includes(r.phase));
  if (next && active.length < slots) return { task_id: next.task_id, action: next.phase === "PREPARED" ? "dispatch-prepared" : "dispatch" };
  if (active.length) return { task_id: active[cursor % active.length].task_id, action: "observe" };
  throw new Error("DOUBAOWORK_QUEUE_STATE_UNSCHEDULABLE");
}

export function summarizeQueueConcurrency(rows, configured) {
  const peak = (startKey, endKey) => {
    const points = [], missing = [];
    for (const r of rows) {
      const a = Date.parse(r[startKey]), b = Date.parse(r[endKey]);
      if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) { missing.push(r.task_id); continue; }
      points.push([a, 1], [b, -1]);
    }
    points.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let active = 0, maximum = 0;
    for (const [, delta] of points) { active += delta; maximum = Math.max(maximum, active); }
    return { value: missing.length ? null : maximum, known_lower_bound: maximum, covered_tasks: rows.length - missing.length, missing_task_ids: missing };
  };
  return { configured_run_slots: configured, ui_slots: 1,
    scheduling_occupancy: peak("prompt_sent_at", "slot_released_at"),
    native_agent_overlap: peak("native_started_at", "native_finished_at"),
    native_source: "bound assistant elapsed_block.start_time_s/end_time_s", native_resolution_seconds: 1 };
}

async function readJournal(path) {
  try {
    const st = await lstat(path);
    if (!st.isFile() || st.isSymbolicLink()) throw new Error("DOUBAOWORK_QUEUE_JOURNAL_UNSAFE");
    return JSON.parse(await readFile(path, "utf8"));
  } catch (e) { if (e.code === "ENOENT") return null; throw e; }
}
async function save(path, value) {
  const temp = `${path}.tmp-${randomUUID()}`;
  await writeFile(temp, `${JSON.stringify(value, null, 2)}\n`, { flag: "wx", mode: 0o600 });
  await rename(temp, path);
}
async function sourceDigest() {
  const names = ["driver.mjs", "batch.mjs", "prepared-task.mjs", "managed-queue.mjs", "package-lock.json",
    ...["controller.mjs", "path-preflight.mjs", "runtime-messages.mjs", "runtime-stream.mjs", "runtime-tools.mjs", "runtime-lifecycle.mjs", "runtime-activity.mjs", "trajectory-archive.mjs", "native-evidence.mjs", "state.mjs", "lib.mjs", "platform.mjs", "select-folder.swift"].map(n => `../../vendor/e2e-shared/doubaowork/${n}`)];
  return sha(JSON.stringify(await Promise.all(names.map(async n => [n, sha(await readFile(join(HERE, n)))]))));
}

export async function runSerialQueue(options) {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/u.test(options.queueId || "")) throw new Error("DOUBAOWORK_QUEUE_ID_INVALID");
  if (!Number.isInteger(options.runSlots) || options.runSlots < 1 || options.runSlots > 3) throw new Error("DOUBAOWORK_CONCURRENCY_NOT_ADMITTED: run-slots must be 1–3");
  if (!options.expectedPermission || options.expectedPermission === "current") throw new Error("DOUBAOWORK_QUEUE_EXPLICIT_PERMISSION_REQUIRED");
  if (!isAbsolute(options.unitRoot || "") || await realpath(options.unitRoot) !== resolve(options.unitRoot)) throw new Error("DOUBAOWORK_QUEUE_ROOT_UNSAFE");
  const unitRoot = await realpath(options.unitRoot), manifestBytes = await readFile(join(unitRoot, "manifest.json"));
  const manifest = JSON.parse(manifestBytes), taskIds = manifest.tasks.map(t => t.task_id);
  if (!taskIds.length || new Set(taskIds).size !== taskIds.length) throw new Error("DOUBAOWORK_QUEUE_TASK_SCOPE_INVALID");
  for (const taskId of taskIds) await validateGeneralTask({ unitRoot, taskId, expectedPermission: options.expectedPermission });
  const queueRoot = join(unitRoot, ".general-e2e", "queues", "doubaowork", options.queueId);
  const release = await acquireExclusiveWorkerLock(queueRoot), stateFile = join(queueRoot, "queue.json");
  let stopArchive;
  try {
    const config = { unit_root: unitRoot, queue_id: options.queueId, manifest_sha256: sha(manifestBytes), task_ids: taskIds,
      app_path: options.appPath, endpoint: options.endpoint, expected_permission: options.expectedPermission,
      ui_slots: 1, run_slots: options.runSlots, preprepare_projects: true, source_root: HERE, source_digest: await sourceDigest() };
    let state;
    try {
      const st = await lstat(stateFile);
      if (!st.isFile() || st.isSymbolicLink()) throw new Error("DOUBAOWORK_QUEUE_STATE_UNSAFE");
      state = JSON.parse(await readFile(stateFile, "utf8"));
      if (!options.resume) throw new Error("DOUBAOWORK_QUEUE_EXISTS_USE_RESUME");
      if (state.config_digest !== sha(JSON.stringify(config)) || sha(JSON.stringify(state.config)) !== state.config_digest
          || JSON.stringify(state.tasks.map(r => r.task_id)) !== JSON.stringify(taskIds)) throw new Error("DOUBAOWORK_QUEUE_CONFIG_DRIFT");
    } catch (e) {
      if (e.code !== "ENOENT") throw e;
      if (options.resume) throw new Error("DOUBAOWORK_QUEUE_NOT_FOUND");
      state = { schema: "wildclawbench.doubaowork-general-queue/v1", config, config_digest: sha(JSON.stringify(config)),
        created_at: now(), status: "RUNNING", tasks: taskIds.map((task_id, i) => ({ task_id, order: i, phase: "PENDING", attempt_id: null,
          project_name: `WCB-${options.queueId}-${String(i + 1).padStart(2, "0")}`, dispatch_attempt_count: 0, native_started_at: null, native_finished_at: null })), history: [] };
      await save(stateFile, state);
    }
    if (state.error) state.history.push({ event: "RESUME_AFTER_ATTENTION", at: now(), previous_error: state.error });
    state.error = null;
    state.status = "RUNNING";
    const pathFor = row => join(unitRoot, ".general-e2e", "execution", row.task_id, "doubaowork", "automation_state.json");
    state.trajectory_archive_errors ||= [];
    stopArchive = startTrajectoryArchivePump({ journals: async () => {
      const inputs = [];
      for (const row of state.tasks.filter(r => ["DISPATCHING", "RUNNING", "NEEDS_ATTENTION"].includes(r.phase))) {
        const journal = await readJournal(pathFor(row));
        if (journal?.session?.conversation_id && journal.send?.dispatch_attempt_count === 1) {
          if (journal.attempt_id !== row.attempt_id || journal.prepared?.managed_queue_id !== options.queueId
              || journal.client.manifest_sha256 !== config.manifest_sha256 || journal.identity.task_id !== row.task_id) throw new Error("DOUBAOWORK_ARCHIVE_QUEUE_BINDING_DRIFT");
          inputs.push({ journal, outputRoot: join(dirname(pathFor(row)), "trajectory-observations") });
        }
      }
      return inputs;
    }, onError: async error => {
      if (!state.trajectory_archive_errors.some(e => e.attempt_id === error.attempt_id && e.message === error.message)) state.trajectory_archive_errors.push(error);
    } });
    for (const row of state.tasks.filter(r => ["PENDING", "PREPARING"].includes(r.phase))) {
      let journal = await readJournal(pathFor(row));
      if (row.phase === "PREPARING" && decideQueueTaskAction(row, journal) === "prepared") {
        row.phase = "PREPARED"; row.attempt_id = journal.attempt_id; await save(stateFile, state); continue;
      }
      if (journal || row.phase !== "PENDING") throw new Error("DOUBAOWORK_QUEUE_PREPARATION_UNCERTAIN");
      row.phase = "PREPARING"; state.history.push({ task_id: row.task_id, event: "PROJECT_PREPARATION_INTENT", at: now() });
      await save(stateFile, state);
      let error = null;
      try {
        await execFile(process.execPath, [join(HERE, "driver.mjs"), "--unit-root", unitRoot, "--task-id", row.task_id,
          "--managed-queue-id", options.queueId, "--expected-permission", options.expectedPermission,
          "--app-path", options.appPath, "--endpoint", options.endpoint, "--project-name", row.project_name, "--prepare-only"],
        { cwd: HERE, maxBuffer: 2 * 1024 * 1024 });
      } catch (e) { error = { code: String(e.code), message: String(e.stderr || e.message).slice(0, 2000) }; }
      journal = await readJournal(pathFor(row));
      if (error || decideQueueTaskAction(row, journal) !== "prepared") {
        row.phase = "NEEDS_ATTENTION"; row.attempt_id = journal?.attempt_id ?? null; state.status = "NEEDS_ATTENTION";
        state.error = { task_id: row.task_id, phase: "prepare-project", worker: error, native: journal?.error ?? null };
        await save(stateFile, state); return state;
      }
      row.phase = "PREPARED"; row.attempt_id = journal.attempt_id;
      state.history.push({ task_id: row.task_id, event: "PROJECT_PREPARED", at: now(), dispatch_attempt_count: 0 });
      await save(stateFile, state);
    }
    const markComplete = (row, journal) => {
      row.attempt_id = journal.attempt_id; row.dispatch_attempt_count = journal.send.dispatch_attempt_count;
      row.prompt_sent_at = journal.timing.sent_at;
      row.native_request_started_at = journal.native_observation.started_at;
      row.native_started_at = journal.native_observation.agent_started_at;
      row.native_finished_at = journal.native_observation.agent_finished_at;
      row.slot_released_at = now(); row.phase = "NATIVE_COMPLETED";
      state.history.push({ task_id: row.task_id, event: "NATIVE_COMPLETED", at: row.slot_released_at });
    };
    let pollIndex = 0;
    while (state.tasks.some(row => row.phase !== "NATIVE_COMPLETED")) {
      if (state.trajectory_archive_errors.length) {
        state.status = "NEEDS_ATTENTION"; state.error = { code: "DOUBAOWORK_TRAJECTORY_ARCHIVE_FAILED", errors: state.trajectory_archive_errors };
        await save(stateFile, state); return state;
      }
      // Reconcile every reserved/sent row before considering a new dispatch.
      for (const row of state.tasks.filter(r => r.phase !== "PENDING")) {
        const journal = await readJournal(pathFor(row));
        const action = decideQueueTaskAction(row, journal);
        if (row.phase === "PREPARED") {
          if (action !== "dispatch-prepared") throw new Error("DOUBAOWORK_QUEUE_PREPARED_STATE_DRIFT");
          continue;
        }
        if (row.phase === "NATIVE_COMPLETED") {
          if (action !== "complete") throw new Error("DOUBAOWORK_QUEUE_TERMINAL_DRIFT");
        } else if (action === "complete") markComplete(row, journal);
        else if (action !== "observe") {
          row.phase = "NEEDS_ATTENTION"; state.status = "NEEDS_ATTENTION"; state.error = { code: action, task_id: row.task_id };
          await save(stateFile, state); return state;
        }
      }
      await save(stateFile, state);
      if (state.tasks.every(r => r.phase === "NATIVE_COMPLETED")) break;
      const selected = selectQueueAction(state.tasks, options.runSlots, pollIndex++);
      const row = state.tasks.find(r => r.task_id === selected.task_id), action = selected.action;
      const previous = await readJournal(pathFor(row));
      if (action === "dispatch" && previous) throw new Error("DOUBAOWORK_QUEUE_TASK_ALREADY_HAS_ATTEMPT");
      if (action === "dispatch" || action === "dispatch-prepared") {
        row.phase = "DISPATCHING"; state.history.push({ task_id: row.task_id, event: "DISPATCH_INTENT", at: now() });
        await save(stateFile, state);
      }
      const args = [join(HERE, "driver.mjs"), "--unit-root", unitRoot, "--task-id", row.task_id,
        "--managed-queue-id", options.queueId, "--expected-permission", options.expectedPermission,
        "--app-path", options.appPath, "--endpoint", options.endpoint,
        ...(action === "dispatch" ? ["--project-name", row.project_name]
          : action === "dispatch-prepared" ? ["--resume", "--dispatch-prepared"] : ["--resume", "--observe-seconds", "2"])];
      let workerError = null;
      try { await execFile(process.execPath, args, { cwd: HERE, maxBuffer: 2 * 1024 * 1024 }); }
      catch (e) { workerError = { code: String(e.code), message: String(e.stderr || e.message).slice(0, 2000) }; }
      const observed = await readJournal(pathFor(row));
      if (observed) {
        if (row.attempt_id && row.attempt_id !== observed.attempt_id) throw new Error("DOUBAOWORK_QUEUE_ATTEMPT_DRIFT");
        row.attempt_id = observed.attempt_id; row.dispatch_attempt_count = observed.send.dispatch_attempt_count;
        row.prompt_sent_at = observed.timing.sent_at;
      }
      if (workerError || !observed || (observed.phase === "NEEDS_ATTENTION" && !observed.native_observation)) {
        row.phase = "NEEDS_ATTENTION"; state.status = "NEEDS_ATTENTION";
        state.error = { task_id: row.task_id, worker: workerError, native: observed?.error ?? null };
        await save(stateFile, state); return state;
      }
      row.phase = "RUNNING";
      if (observed.native_observation?.terminal === "completed") markComplete(row, observed);
      await save(stateFile, state);
      if (action === "observe" && !observed.native_observation) await sleep(1000);
    }
    state.concurrency = summarizeQueueConcurrency(state.tasks, options.runSlots);
    state.status = "EXECUTION_COMPLETED_PENDING_COLLECTION"; state.finished_at = now();
    await save(stateFile, state); return state;
  } finally { try { await stopArchive?.(); } finally { await release(); } }
}

export async function main(argv = process.argv.slice(2)) {
  const { values: v } = parseArgs({ args: argv, options: {
    "unit-root": { type: "string" }, "queue-id": { type: "string" }, "run-slots": { type: "string", default: "1" },
    "expected-permission": { type: "string" }, "app-path": { type: "string", default: DEFAULT_APP_PATH },
    endpoint: { type: "string", default: DEFAULT_ENDPOINT }, resume: { type: "boolean" }, help: { type: "boolean" },
  } });
  if (v.help) { console.log("DoubaoWork General queue (development admission): --unit-root ABS --queue-id ID --expected-permission LABEL [--resume] [--run-slots 1–3]. No task deadline; unknown dispatch never repeats."); return; }
  const result = await runSerialQueue({ unitRoot: v["unit-root"], queueId: v["queue-id"], runSlots: Number(v["run-slots"]),
    expectedPermission: v["expected-permission"], appPath: v["app-path"], endpoint: v.endpoint, resume: v.resume });
  console.log(JSON.stringify({ status: result.status, tasks: result.tasks, error: result.error ?? null }, null, 2));
  if (result.status === "NEEDS_ATTENTION") process.exitCode = 3;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(e => { console.error(e.message); process.exitCode = 1; });
