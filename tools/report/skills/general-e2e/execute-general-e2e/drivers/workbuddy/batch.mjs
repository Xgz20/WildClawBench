#!/usr/bin/env node
import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdir, open, readFile, realpath, rename, rm, writeFile } from "node:fs/promises";
import { hostname } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { main as execute, parseArgs, resolveExecutionConfig } from "./execute.mjs";

export const WORKBUDDY_QUEUE_SCHEMA = "wildclawbench.general-e2e-workbuddy-execution-queue/v2";
export const WORKBUDDY_QUEUE_VERSION = "0.2.0";
export const DEFAULT_RUN_SLOTS = 3;
export const MAX_RUN_SLOTS = 8;
const TERMINAL_PHASES = new Set(["COMPLETED", "FAILED"]);
const safeId = (id) => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(id);
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const readJson = async (path) => JSON.parse(await readFile(path, "utf8"));

async function optionalJson(path) {
  try { return await readJson(path); } catch (error) { if (error.code === "ENOENT") return null; throw error; }
}

async function persist(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { flag: "wx", mode: 0o600 });
  await rename(temporary, path);
}

async function assertPlainPath(root, segments) {
  let current = root;
  for (const segment of segments) {
    current = join(current, segment);
    const info = await lstat(current).catch((error) => {
      if (error.code === "ENOENT") return null;
      throw error;
    });
    if (info?.isSymbolicLink()) throw new Error(`WORKBUDDY_QUEUE_SYMLINK: ${current}`);
  }
}

function positiveInteger(value, label) {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) throw new Error(`${label} 必须是正整数`);
  return parsed;
}

export function parseBatchArgs(argv) {
  const args = [...argv];
  let queueId = "";
  let runSlots = DEFAULT_RUN_SLOTS;
  let resume = false;
  let status = false;
  for (let index = 0; index < args.length;) {
    const arg = args[index];
    if (arg === "--queue-id" || arg === "--run-slots") {
      const value = args[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      if (arg === "--queue-id") queueId = value;
      else runSlots = positiveInteger(value, arg);
      args.splice(index, 2);
    } else if (arg === "--resume" || arg === "--status") {
      if (arg === "--resume") resume = true;
      else status = true;
      args.splice(index, 1);
    } else index += 1;
  }
  if (!safeId(queueId)) throw new Error("--queue-id 必须是安全的非空 ID");
  if (runSlots > MAX_RUN_SLOTS) throw new Error(`--run-slots 必须在 1–${MAX_RUN_SLOTS} 之间`);
  if (resume && status) throw new Error("--resume 与 --status 不能同时使用");
  if (["--task-id", "--attempt-id", "--detach-after-submit", "--observe-once", "--managed-queue-id", "--managed-run-slots"].some((flag) => args.includes(flag))) {
    throw new Error("队列执行 manifest 全集，不接受单题或内部托管选项");
  }
  return { args, queueId, runSlots, resume, status };
}

function executionPaths(root, taskId) {
  const controlRoot = join(root, ".general-e2e", "execution", taskId, "workbuddy");
  return {
    journal: join(controlRoot, "dispatch-journal.json"),
    state: join(controlRoot, "execution-state.json"),
  };
}

function phaseFrom(journal, publicState) {
  if (new Set(["NEEDS_ATTENTION", "FAILED"]).has(journal?.phase)) return journal.phase;
  return publicState?.phase || journal?.phase || null;
}

function terminalAt(journal, publicState) {
  if (!TERMINAL_PHASES.has(phaseFrom(journal, publicState))) return null;
  return publicState?.execution?.finished_at
    || [...(journal?.history || [])].reverse().find((event) => TERMINAL_PHASES.has(event.phase))?.at
    || null;
}

async function synchronizeRow(root, row) {
  const paths = executionPaths(root, row.task_id);
  const journal = await optionalJson(paths.journal);
  const publicState = await optionalJson(paths.state);
  if (!journal) {
    if (row.phase !== "PENDING" && row.phase !== "DISPATCHING") {
      throw new Error(`WORKBUDDY_QUEUE_REGISTERED_ATTEMPT_MISSING: ${row.task_id}`);
    }
    return row;
  }
  if (journal.identity?.attempt_id !== row.attempt_id) throw new Error("WORKBUDDY_QUEUE_ATTEMPT_DRIFT");
  if (journal.identity?.task_id !== row.task_id) throw new Error("WORKBUDDY_QUEUE_TASK_DRIFT");
  const phase = phaseFrom(journal, publicState);
  if (!new Set(["PENDING", "RUNNING", "COMPLETED", "FAILED", "NEEDS_ATTENTION"]).has(phase)) {
    throw new Error(`WORKBUDDY_QUEUE_PHASE_INVALID: ${row.task_id}: ${phase}`);
  }
  row.phase = phase;
  row.dispatch_attempt_count = Number(journal.send?.dispatch_attempt_count || 0);
  row.conversation_id = journal.native?.conversation_id || null;
  row.request_id = journal.native?.request_id || null;
  row.cwd = journal.native?.cwd || null;
  row.started_at ||= journal.prompt?.sent_at || journal.execution?.started_at || null;
  row.finished_at = terminalAt(journal, publicState);
  row.error = journal.execution?.error || publicState?.execution?.error || null;
  return row;
}

function observedConcurrency(tasks) {
  const points = [];
  for (const task of tasks) {
    const start = Date.parse(task.started_at || "");
    const finish = Date.parse(task.finished_at || "");
    if (!Number.isFinite(start) || !Number.isFinite(finish) || finish < start) continue;
    points.push({ at: start, delta: 1 }, { at: finish, delta: -1 });
  }
  points.sort((left, right) => left.at - right.at || left.delta - right.delta);
  let current = 0;
  let maximum = 0;
  for (const point of points) {
    current += point.delta;
    maximum = Math.max(maximum, current);
  }
  return maximum;
}

function buildReceipt(state) {
  const maxConcurrency = observedConcurrency(state.tasks);
  const refillEvents = state.events.filter((event) => (
    event.event === "TASK_DISPATCH_RETURNED" && event.completed_before_dispatch > 0
  ));
  const allTerminal = state.tasks.every((row) => TERMINAL_PHASES.has(row.phase));
  const attemptsUnique = new Set(state.tasks.map((row) => row.attempt_id)).size === state.tasks.length;
  const noDuplicateDispatch = state.tasks.every((row) => row.dispatch_attempt_count === 1);
  const observedRequestedConcurrency = maxConcurrency === Math.min(state.frozen.run_slots, state.tasks.length);
  const dynamicRefillObserved = state.tasks.length <= state.frozen.run_slots || refillEvents.length > 0;
  return {
    schema_version: "wildclawbench.general-e2e-workbuddy-execution-queue-receipt/v1",
    generated_at: new Date().toISOString(),
    identity: {
      queue_id: state.queue_id,
      frozen_sha256: state.frozen_sha256,
      batch_id: state.frozen.batch_id,
      unit_id: state.frozen.unit_id,
    },
    phase: state.phase,
    ui_slots: 1,
    run_slots: state.frozen.run_slots,
    observed_max_concurrency: maxConcurrency,
    dynamic_refill_count: refillEvents.length,
    tasks: state.tasks.map((row) => ({
      task_id: row.task_id,
      attempt_id: row.attempt_id,
      phase: row.phase,
      dispatch_attempt_count: row.dispatch_attempt_count,
      conversation_id: row.conversation_id,
      request_id: row.request_id,
      cwd: row.cwd,
      started_at: row.started_at,
      finished_at: row.finished_at,
      error: row.error,
    })),
    integrity: {
      all_tasks_terminal: allTerminal,
      attempts_explicit_and_unique: attemptsUnique,
      no_duplicate_dispatch: noDuplicateDispatch,
      observed_requested_concurrency: observedRequestedConcurrency,
      dynamic_refill_observed: dynamicRefillObserved,
      valid: allTerminal && attemptsUnique && noDuplicateDispatch
        && observedRequestedConcurrency && dynamicRefillObserved,
    },
  };
}

async function persistState(statePath, receiptPath, state) {
  await persist(statePath, state);
  if (state.phase === "COMPLETED" || state.phase === "COMPLETED_WITH_FAILURES") {
    await persist(receiptPath, buildReceipt(state));
  }
}

export async function runWorkBuddyBatch(argv, dependencies = {}) {
  const batch = parseBatchArgs(argv);
  const parsed = parseArgs([...batch.args, "--task-id", "queue-config"]);
  const root = await realpath(resolve(parsed.unitRoot));
  await assertPlainPath(root, ["manifest.json"]);
  const manifestBytes = await readFile(join(root, "manifest.json"));
  const manifest = JSON.parse(manifestBytes);
  const taskIds = manifest.task_ids;
  if (!Array.isArray(taskIds) || !taskIds.length || taskIds.some((id) => !safeId(id))
      || new Set(taskIds).size !== taskIds.length) throw new Error("WORKBUDDY_QUEUE_TASKS_INVALID");
  const configs = [];
  for (const taskId of taskIds) configs.push(await resolveExecutionConfig({ ...parsed, taskId }));
  const frozen = {
    batch_id: manifest.batch_id,
    unit_id: manifest.unit_id,
    unit_root: root,
    manifest_sha256: hash(manifestBytes),
    task_ids: taskIds,
    endpoint: parsed.endpoint,
    app_path: parsed.appPath,
    model: configs[0].expectedModel,
    permission: parsed.expectedPermission,
    session_db: parsed.sessionDb,
    data_root: parsed.dataRoot,
    timeout_ms: parsed.timeoutMs,
    identity_timeout_ms: parsed.identityTimeoutMs,
    poll_interval_ms: parsed.pollIntervalMs,
    ui_slots: 1,
    run_slots: batch.runSlots,
    driver_sha256: hash(await readFile(new URL("./execute.mjs", import.meta.url))),
  };
  const digest = hash(JSON.stringify(frozen));
  const queueRoot = join(root, ".general-e2e", "queues", "workbuddy");
  const statePath = join(queueRoot, `${batch.queueId}.json`);
  const receiptPath = join(queueRoot, `${batch.queueId}-receipt.json`);
  const lockPath = join(queueRoot, "owner-lock.json");
  await assertPlainPath(root, [".general-e2e", "queues", "workbuddy", `${batch.queueId}.json`]);
  await mkdir(queueRoot, { recursive: true });
  let state = await optionalJson(statePath);
  if (batch.status) {
    if (!state) throw new Error("WORKBUDDY_QUEUE_MISSING");
    if (state.schema_version !== WORKBUDDY_QUEUE_SCHEMA || state.frozen_sha256 !== digest) {
      throw new Error("WORKBUDDY_QUEUE_CONFIG_DRIFT");
    }
    return { ...state, state_file: statePath, receipt_file: receiptPath };
  }
  await assertPlainPath(root, [".general-e2e", "queues", "workbuddy", "owner-lock.json"]);
  const lock = await open(lockPath, "wx", 0o600).catch((error) => {
    if (error.code === "EEXIST") throw new Error("WORKBUDDY_QUEUE_OWNER_EXISTS: 不自动删除活动或陈旧锁");
    throw error;
  });
  const lockStat = await lock.stat({ bigint: true });
  const runTask = dependencies.execute || execute;
  const sleep = dependencies.sleep || ((milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds)));
  const now = dependencies.now || (() => new Date().toISOString());
  try {
    await lock.writeFile(JSON.stringify({ pid: process.pid, host: hostname(), started_at: now(), queue_id: batch.queueId }));
    if (state && !batch.resume) throw new Error("WORKBUDDY_QUEUE_EXISTS: 使用 --resume，禁止重建队列");
    if (!state && batch.resume) throw new Error("WORKBUDDY_QUEUE_MISSING");
    if (state && (state.schema_version !== WORKBUDDY_QUEUE_SCHEMA || state.frozen_sha256 !== digest)) {
      throw new Error("WORKBUDDY_QUEUE_CONFIG_DRIFT");
    }
    if (!state) {
      for (const config of configs) {
        if (await optionalJson(config.journalFile)) throw new Error("WORKBUDDY_QUEUE_ATTEMPT_ALREADY_EXISTS: " + config.task.task_id);
      }
      state = {
        schema_version: WORKBUDDY_QUEUE_SCHEMA,
        worker: { id: "workbuddy-macos-concurrent", version: WORKBUDDY_QUEUE_VERSION },
        queue_id: batch.queueId,
        frozen,
        frozen_sha256: digest,
        phase: "PENDING",
        active_task_ids: [],
        tasks: taskIds.map((task_id) => ({
          task_id,
          phase: "PENDING",
          attempt_id: randomUUID(),
          dispatch_attempt_count: 0,
          conversation_id: null,
          request_id: null,
          cwd: null,
          started_at: null,
          finished_at: null,
          error: null,
          exit_code: null,
        })),
        events: [{ event: "QUEUE_CREATED", at: now() }],
      };
      await persistState(statePath, receiptPath, state);
    }
    if (state.phase === "COMPLETED" || state.phase === "COMPLETED_WITH_FAILURES") {
      for (const row of state.tasks) await synchronizeRow(root, row);
      return { ...state, state_file: statePath, receipt_file: receiptPath };
    }
    state.phase = "RUNNING";
    state.events.push({ event: batch.resume ? "QUEUE_RESUMED" : "QUEUE_STARTED", at: now() });
    await persistState(statePath, receiptPath, state);
    const recoveredAttention = new Set();

    for (;;) {
      for (const row of state.tasks) await synchronizeRow(root, row);
      let running = state.tasks.filter((row) => row.phase === "RUNNING");
      let attention = state.tasks.filter((row) => row.phase === "NEEDS_ATTENTION");
      if (batch.resume) {
        for (const row of attention.filter((item) => !recoveredAttention.has(item.task_id))) {
          recoveredAttention.add(row.task_id);
          const code = await runTask([
            ...batch.args,
            "--task-id", row.task_id,
            "--attempt-id", row.attempt_id,
            "--resume",
            "--observe-once",
            "--managed-queue-id", batch.queueId,
            "--managed-run-slots", String(batch.runSlots),
          ], dependencies.executeOverrides || {});
          row.exit_code = code;
          await synchronizeRow(root, row);
          state.events.push({ event: "TASK_ATTENTION_RECOVERY_RETURNED", at: now(), task_id: row.task_id, task_phase: row.phase, exit_code: code });
          await persistState(statePath, receiptPath, state);
        }
        running = state.tasks.filter((row) => row.phase === "RUNNING");
        attention = state.tasks.filter((row) => row.phase === "NEEDS_ATTENTION");
      }
      if (attention.length) {
        state.phase = "NEEDS_ATTENTION";
        state.active_task_ids = running.map((row) => row.task_id);
        await persistState(statePath, receiptPath, state);
        return { ...state, state_file: statePath, receipt_file: receiptPath };
      }
      while (running.length < batch.runSlots) {
        const pending = state.tasks.find((row) => row.phase === "PENDING");
        if (!pending) break;
        if (running.some((row) => !row.conversation_id || !row.cwd)) break;
        pending.phase = "DISPATCHING";
        state.active_task_ids = [...running.map((row) => row.task_id), pending.task_id];
        state.events.push({
          event: "TASK_DISPATCH_REQUESTED",
          at: now(),
          task_id: pending.task_id,
          active_before_dispatch: running.length,
          completed_before_dispatch: state.tasks.filter((row) => row.phase === "COMPLETED").length,
        });
        await persistState(statePath, receiptPath, state);
        const code = await runTask([
          ...batch.args,
          "--task-id", pending.task_id,
          "--attempt-id", pending.attempt_id,
          "--detach-after-submit",
          "--managed-queue-id", batch.queueId,
          "--managed-run-slots", String(batch.runSlots),
        ], dependencies.executeOverrides || {});
        pending.exit_code = code;
        await synchronizeRow(root, pending);
        state.events.push({
          event: "TASK_DISPATCH_RETURNED",
          at: now(),
          task_id: pending.task_id,
          task_phase: pending.phase,
          exit_code: code,
          active_before_dispatch: running.length,
          completed_before_dispatch: state.tasks.filter((row) => row.phase === "COMPLETED").length,
        });
        await persistState(statePath, receiptPath, state);
        if (pending.phase === "NEEDS_ATTENTION" || pending.phase === "FAILED") break;
        running = state.tasks.filter((row) => row.phase === "RUNNING");
      }

      running = state.tasks.filter((row) => row.phase === "RUNNING");
      const pending = state.tasks.filter((row) => row.phase === "PENDING");
      if (!running.length && !pending.length) {
        const failed = state.tasks.filter((row) => row.phase === "FAILED");
        state.phase = failed.length ? "COMPLETED_WITH_FAILURES" : "COMPLETED";
        state.active_task_ids = [];
        state.events.push({ event: state.phase === "COMPLETED" ? "QUEUE_COMPLETED" : "QUEUE_COMPLETED_WITH_FAILURES", at: now() });
        await persistState(statePath, receiptPath, state);
        return { ...state, state_file: statePath, receipt_file: receiptPath };
      }
      if (!running.length) {
        state.phase = "NEEDS_ATTENTION";
        state.events.push({ event: "QUEUE_STALLED", at: now() });
        await persistState(statePath, receiptPath, state);
        return { ...state, state_file: statePath, receipt_file: receiptPath };
      }

      let changed = false;
      for (const row of running) {
        const before = row.phase;
        const code = await runTask([
          ...batch.args,
          "--task-id", row.task_id,
          "--attempt-id", row.attempt_id,
          "--resume",
          "--observe-once",
          "--managed-queue-id", batch.queueId,
          "--managed-run-slots", String(batch.runSlots),
        ], dependencies.executeOverrides || {});
        row.exit_code = code;
        await synchronizeRow(root, row);
        changed ||= row.phase !== before;
        state.events.push({ event: "TASK_OBSERVATION_RETURNED", at: now(), task_id: row.task_id, task_phase: row.phase, exit_code: code });
        await persistState(statePath, receiptPath, state);
      }
      state.active_task_ids = state.tasks.filter((row) => row.phase === "RUNNING").map((row) => row.task_id);
      if (!changed) await sleep(parsed.pollIntervalMs);
    }
  } finally {
    await lock.close();
    const current = await lstat(lockPath, { bigint: true }).catch(() => null);
    if (current && !current.isSymbolicLink() && current.dev === lockStat.dev && current.ino === lockStat.ino) await rm(lockPath);
  }
}

if (process.argv[1] && await realpath(resolve(process.argv[1])) === await realpath(fileURLToPath(import.meta.url))) {
  if (process.argv.includes("--help")) {
    console.log("WorkBuddy macOS 队列：node drivers/workbuddy/batch.mjs --unit-root PATH --queue-id ID --endpoint http://127.0.0.1:9229 --expected-permission default-sandbox [--run-slots 1-8] [--resume|--status]。UI 单槽，后台默认三路并按可信终态动态补位。");
  } else {
    runWorkBuddyBatch(process.argv.slice(2)).then((result) => {
      console.log(JSON.stringify(result, null, 2));
      if (!new Set(["COMPLETED", "COMPLETED_WITH_FAILURES"]).has(result.phase)) process.exitCode = 3;
    }).catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
  }
}
