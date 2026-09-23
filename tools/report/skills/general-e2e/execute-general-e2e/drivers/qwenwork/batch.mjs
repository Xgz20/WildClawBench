#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdir, open, readFile, readdir, realpath, rename, rm, writeFile } from "node:fs/promises";
import { hostname } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { runCapture } from "../../vendor/e2e-shared/desktop-runtime/process.mjs";
import { calculateQwenCanaryConfigDigest } from "./driver.mjs";

export const QWENWORK_QUEUE_SCHEMA = "wildclawbench.general-e2e-qwenwork-execution-queue/v1";
export const QWENWORK_QUEUE_VERSION = "0.2.0";
export const DEFAULT_RUN_SLOTS = 3;
export const MAX_RUN_SLOTS = 8;
const TERMINAL_PHASES = new Set(["COMPLETED", "FAILED"]);
const QUEUE_PHASES = new Set(["PENDING", "DISPATCHING", "RUNNING", "COMPLETED", "FAILED", "NEEDS_ATTENTION"]);
const DRIVER_DIR = resolve(fileURLToPath(new URL(".", import.meta.url)));
const DRIVER_PATH = join(DRIVER_DIR, "driver.mjs");
const PROBE_PATH = join(DRIVER_DIR, "probe.mjs");
const BUNDLE_ID = "cn.qwenwork.desktop.mac";
const DRIVER_SOURCE_FILES = [
  "batch.mjs", "driver.mjs", "execution-state.mjs", "journal.mjs",
  "probe.mjs", "runtime-profile.mjs", "select-folder.swift",
  "session-state.mjs", "ui.mjs", "package-lock.json",
];

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const safeId = (value) => typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(value);
const readJson = async (path) => JSON.parse(await readFile(path, "utf8"));

async function optionalJson(path) {
  try { return await readJson(path); } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
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
      if (error?.code === "ENOENT") return null;
      throw error;
    });
    if (info?.isSymbolicLink()) throw new Error(`QWENWORK_QUEUE_SYMLINK: ${current}`);
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
  let endpoint = "http://127.0.0.1:9250";
  let sessionDb = "";
  let traceRoot = "";
  let probe = "";
  let probeSha256 = "";
  let configDir = "";
  let preprepareProjects = false;
  let skipClarifications = false;
  let resume = false;
  let status = false;
  for (let index = 0; index < args.length;) {
    const arg = args[index];
    if (["--queue-id", "--run-slots", "--endpoint", "--session-db", "--trace-root", "--probe", "--probe-sha256", "--config-dir"].includes(arg)) {
      const value = args[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} 缺少值`);
      if (arg === "--queue-id") queueId = value;
      else if (arg === "--run-slots") runSlots = positiveInteger(value, arg);
      else if (arg === "--endpoint") endpoint = value;
      else if (arg === "--session-db") sessionDb = value;
      else if (arg === "--trace-root") traceRoot = value;
      else if (arg === "--probe") probe = value;
      else if (arg === "--config-dir") configDir = value;
      else probeSha256 = value;
      args.splice(index, 2);
    } else if (arg === "--resume" || arg === "--status") {
      if (arg === "--resume") resume = true;
      else status = true;
      args.splice(index, 1);
    } else if (arg === "--preprepare-projects") {
      preprepareProjects = true;
      args.splice(index, 1);
    } else if (arg === "--skip-clarifications") {
      skipClarifications = true;
      args.splice(index, 1);
    } else index += 1;
  }
  if (!safeId(queueId)) throw new Error("--queue-id 必须是安全的非空 ID");
  if (runSlots > MAX_RUN_SLOTS) throw new Error(`--run-slots 必须在 1–${MAX_RUN_SLOTS} 之间`);
  if (resume && status) throw new Error("--resume 与 --status 不能同时使用");
  if (!probe || !probeSha256) throw new Error("--probe 与 --probe-sha256 必须同时指定");
  if (!/^[a-f0-9]{64}$/u.test(probeSha256)) throw new Error("--probe-sha256 必须是 SHA-256");
  const parsedEndpoint = new URL(endpoint);
  if (!new Set(["127.0.0.1", "localhost", "::1"]).has(parsedEndpoint.hostname)) {
    throw new Error("--endpoint 必须使用 loopback host");
  }
  return {
    args,
    queueId,
    runSlots,
    endpoint: parsedEndpoint.origin,
    sessionDb: sessionDb ? resolve(sessionDb) : "",
    traceRoot: traceRoot ? resolve(traceRoot) : "",
    probe: resolve(probe),
    probeSha256,
    configDir: configDir ? resolve(configDir) : "",
    preprepareProjects,
    skipClarifications,
    resume,
    status,
  };
}

function executionPaths(root, taskId, attemptId) {
  const controlRoot = join(root, ".general-e2e", "execution", taskId, "qwenwork");
  return {
    root: controlRoot,
    config: join(controlRoot, "config.json"),
    journal: join(controlRoot, "dispatch-journal.json"),
    evidence: join(controlRoot, "evidence"),
    attemptId,
  };
}

function pathInside(root, value, field) {
  const resolved = resolve(root, value);
  const rel = relative(root, resolved);
  if (!rel || rel.startsWith("..") || rel.includes("\\") || rel.startsWith("/")) {
    throw new Error(`QWENWORK_QUEUE_PATH_OUTSIDE_ROOT: ${field}`);
  }
  return resolved;
}

async function readManifest(root) {
  await assertPlainPath(root, ["manifest.json"]);
  const bytes = await readFile(join(root, "manifest.json"));
  const manifest = JSON.parse(bytes.toString("utf8"));
  const taskIds = manifest.task_ids;
  if (!Array.isArray(taskIds) || !taskIds.length || taskIds.some((id) => !safeId(id))
      || new Set(taskIds).size !== taskIds.length) throw new Error("QWENWORK_QUEUE_TASKS_INVALID");
  if (manifest.manifest_kind !== "execution" || manifest.unit?.harness?.id !== "qwenwork") {
    throw new Error("QWENWORK_QUEUE_MANIFEST_NOT_QWENWORK");
  }
  const tasks = new Map((manifest.tasks || []).map((task) => [task.task_id, task]));
  if (taskIds.some((id) => !tasks.has(id))) throw new Error("QWENWORK_QUEUE_TASK_DEFINITION_MISSING");
  return { manifest, taskIds, tasks, bytes };
}

async function driverSourceDigest() {
  const parts = [];
  for (const file of DRIVER_SOURCE_FILES) {
    parts.push(Buffer.from(file + "\0"));
    parts.push(Buffer.from(sha256(await readFile(join(DRIVER_DIR, file))), "hex"));
  }
  return sha256(Buffer.concat(parts));
}

async function loadExistingConfigs(configDir, taskIds, manifest) {
  await assertPlainPath(configDir, []);
  const entries = (await readdir(configDir, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"));
  const byTask = new Map();
  for (const entry of entries) {
    const path = join(configDir, entry.name);
    const config = await readJson(path);
    const taskId = config.identity?.task_id;
    if (!taskIds.includes(taskId)) continue;
    if (byTask.has(taskId)) throw new Error(`QWENWORK_QUEUE_CONFIG_DUPLICATE: ${taskId}`);
    if (config.identity?.batch_id !== manifest.batch_id || config.identity?.unit_id !== manifest.unit_id) {
      throw new Error(`QWENWORK_QUEUE_CONFIG_IDENTITY_MISMATCH: ${taskId}`);
    }
    if (calculateQwenCanaryConfigDigest(config) !== config.config_digest) {
      throw new Error(`QWENWORK_QUEUE_CONFIG_DIGEST_MISMATCH: ${taskId}`);
    }
    byTask.set(taskId, { path, config, sha256: sha256(await readFile(path)) });
  }
  if (taskIds.some((taskId) => !byTask.has(taskId))) {
    throw new Error("QWENWORK_QUEUE_CONFIG_MISSING");
  }
  return byTask;
}

async function buildTaskConfig(root, manifestInfo, taskId, attemptId, options, frozen) {
  const task = manifestInfo.tasks.get(taskId);
  const taskRoot = pathInside(root, task.prompt.path.replace(/\/PROMPT\.md$/u, ""), "task_root");
  const promptPath = pathInside(root, task.prompt.path, "prompt.path");
  const candidateWorkspace = pathInside(root, task.workspace.path, "candidate_workspace");
  const promptContent = await readFile(promptPath, "utf8");
  const promptSha = sha256(promptContent);
  const expectedSha = task.prompt.sent_sha256 || task.prompt.source_sha256 || task.prompt.original_sha256;
  if (expectedSha && expectedSha !== promptSha) throw new Error(`QWENWORK_QUEUE_PROMPT_DIGEST_MISMATCH: ${taskId}`);
  const paths = executionPaths(root, taskId, attemptId);
  const config = {
    schema_version: "wildclawbench.general-e2e-qwenwork-canary-config/v1",
    config_digest_algorithm: "sha256-canonical-json/v1",
    config_digest: "",
    batch_id: manifestInfo.manifest.batch_id,
    unit_id: manifestInfo.manifest.unit_id,
    identity: {
      batch_id: manifestInfo.manifest.batch_id,
      unit_id: manifestInfo.manifest.unit_id,
      task_id: taskId,
      attempt_id: attemptId,
    },
    dataset: {
      bundle_sha256: manifestInfo.manifest.dataset.bundle_sha256 || null,
      digest: manifestInfo.manifest.dataset.digest,
      id: manifestInfo.manifest.dataset.id,
    },
    task_root: taskRoot,
    candidate_workspace: candidateWorkspace,
    prompt: { path: promptPath, sha256: promptSha },
    state_file: paths.journal,
    evidence_root: paths.evidence,
    client: {
      platform: manifestInfo.manifest.unit.harness.platform || "macos-x86-64",
      endpoint: options.endpoint,
      bundle_id: BUNDLE_ID,
      session_db: options.sessionDb,
      trace_root: options.traceRoot,
    },
    control: {
      desktop_slot_id: `QWENWORK-${options.queueId}`,
      probe_path: options.probe,
      probe_sha256: options.probeSha256,
      model_policy: "keep-current",
      permission_policy: "keep-current",
      create_new_project: true,
      probe_max_age_seconds: 900,
      live_execution_authorized: true,
      clarification_policy: options.skipClarifications ? "skip-question-card" : "manual",
    },
  };
  config.config_digest = calculateQwenCanaryConfigDigest(config);
  await persist(paths.config, config);
  return { config, paths, promptSha };
}

function phaseFrom(journal) {
  if (journal?.phase === "READY_TO_DISPATCH") return "PENDING";
  if (journal?.phase === "NEEDS_ATTENTION") return "NEEDS_ATTENTION";
  if (journal?.phase === "COMPLETED") return "COMPLETED";
  if (journal?.phase === "FAILED") return "FAILED";
  if (journal?.phase === "RUNNING") return "RUNNING";
  return journal?.phase ? "DISPATCHING" : null;
}

function terminalAt(journal) {
  if (!TERMINAL_PHASES.has(phaseFrom(journal))) return null;
  return journal?.execution_state?.execution?.finished_at
    || journal?.execution?.finished_at
    || journal?.updated_at
    || null;
}

async function synchronizeRow(root, row) {
  const paths = executionPaths(root, row.task_id, row.attempt_id);
  const journalPath = row.state_file || paths.journal;
  const relativeJournal = relative(root, resolve(journalPath));
  if (!relativeJournal || relativeJournal.startsWith("..") || relativeJournal.includes("\\")) {
    throw new Error(`QWENWORK_QUEUE_STATE_OUTSIDE_ROOT: ${row.task_id}`);
  }
  await assertPlainPath(root, relativeJournal.split("/").filter(Boolean));
  const journal = await optionalJson(journalPath);
  if (!journal) {
    if (!["PENDING", "DISPATCHING"].includes(row.phase)) {
      throw new Error(`QWENWORK_QUEUE_ATTEMPT_MISSING: ${row.task_id}`);
    }
    return row;
  }
  if (journal.identity?.task_id !== row.task_id || journal.identity?.attempt_id !== row.attempt_id) {
    throw new Error("QWENWORK_QUEUE_ATTEMPT_DRIFT");
  }
  const phase = phaseFrom(journal);
  if (!QUEUE_PHASES.has(phase)) throw new Error(`QWENWORK_QUEUE_PHASE_INVALID: ${row.task_id}: ${phase}`);
  row.phase = phase;
  row.prepared = journal.phase === "READY_TO_DISPATCH";
  row.dispatch_attempt_count = Number(journal.send?.dispatch_attempt_count || 0);
  row.session_id = journal.session?.session_id || null;
  row.conversation_id = journal.session?.conversation_id || null;
  row.sub_chat_id = journal.session?.sub_chat_id || null;
  row.cwd = journal.session?.cwd || journal.candidate_workspace || null;
  row.dispatch_started_at = journal.prompt?.sent_at || journal.send?.invoking_at || row.dispatch_started_at || null;
  row.started_at = row.dispatch_started_at || row.started_at;
  row.finished_at = terminalAt(journal);
  row.native_started_at = journal.native?.started_at || journal.execution_state?.native?.started_at || null;
  row.native_finished_at = journal.native?.finished_at || journal.execution_state?.native?.finished_at || null;
  row.error = journal.attention?.message || journal.execution?.error || journal.execution_state?.execution?.error || null;
  return row;
}

function observedConcurrency(tasks, startField, finishField) {
  const points = [];
  for (const task of tasks) {
    const start = Date.parse(task[startField] || "");
    const finish = Date.parse(task[finishField] || "");
    if (!Number.isFinite(start) || !Number.isFinite(finish) || finish < start) continue;
    points.push({ at: start, delta: 1 }, { at: finish, delta: -1 });
  }
  points.sort((left, right) => left.at - right.at || left.delta - right.delta);
  let current = 0;
  let maximum = 0;
  for (const point of points) { current += point.delta; maximum = Math.max(maximum, current); }
  return { maximum, known_intervals: points.length / 2 };
}

function buildReceipt(state) {
  const dispatch = observedConcurrency(state.tasks, "dispatch_started_at", "finished_at");
  const native = observedConcurrency(state.tasks, "native_started_at", "native_finished_at");
  const completed = state.tasks.filter((row) => row.phase === "COMPLETED").length;
  const allTerminal = state.tasks.every((row) => TERMINAL_PHASES.has(row.phase));
  const attemptsUnique = new Set(state.tasks.map((row) => row.attempt_id)).size === state.tasks.length;
  const noDuplicateDispatch = state.tasks.every((row) => row.dispatch_attempt_count === 1);
  const requested = Math.min(state.frozen.run_slots, state.tasks.length);
  const nativeKnownTotal = state.tasks.filter((row) => row.dispatch_attempt_count === 1).length;
  const nativeObserved = native.known_intervals === nativeKnownTotal && nativeKnownTotal > 0;
  const refillEvents = state.events.filter((event) => event.event === "TASK_DISPATCH_RETURNED" && event.completed_before_dispatch > 0);
  const concurrencyObserved = nativeObserved && native.maximum === requested;
  return {
    schema_version: "wildclawbench.general-e2e-qwenwork-execution-queue-receipt/v1",
    generated_at: new Date().toISOString(),
    identity: { queue_id: state.queue_id, frozen_sha256: state.frozen_sha256, batch_id: state.frozen.batch_id, unit_id: state.frozen.unit_id },
    phase: state.phase,
    ui_slots: 1,
    run_slots: state.frozen.run_slots,
    observed_max_concurrency: dispatch.maximum,
    observed_max_concurrency_basis: "prompt-sent-to-terminal-dispatch-occupancy",
    native_observed_max_concurrency: nativeKnownTotal ? native.maximum : null,
    native_interval_coverage: { known: native.known_intervals, total: nativeKnownTotal, unit: "task" },
    dynamic_refill_count: refillEvents.length,
    completed_count: completed,
    tasks: state.tasks.map((row) => ({
      task_id: row.task_id, attempt_id: row.attempt_id, phase: row.phase,
      dispatch_attempt_count: row.dispatch_attempt_count, session_id: row.session_id,
      conversation_id: row.conversation_id, sub_chat_id: row.sub_chat_id, cwd: row.cwd,
      started_at: row.started_at, dispatch_started_at: row.dispatch_started_at,
      finished_at: row.finished_at, native_started_at: row.native_started_at,
      native_finished_at: row.native_finished_at, error: row.error,
    })),
    integrity: {
      all_tasks_terminal: allTerminal,
      attempts_explicit_and_unique: attemptsUnique,
      no_duplicate_dispatch: noDuplicateDispatch,
      observed_requested_concurrency: concurrencyObserved,
      dynamic_refill_observed: state.tasks.length <= state.frozen.run_slots || refillEvents.length > 0,
      valid: allTerminal && attemptsUnique && noDuplicateDispatch,
    },
    concurrency_evidence: {
      requested_slots: requested,
      dispatch_occupancy_peak: dispatch.maximum,
      native_execution_peak: nativeKnownTotal ? native.maximum : null,
      native_interval_coverage: { known: native.known_intervals, total: nativeKnownTotal },
      requested_native_concurrency_observed: concurrencyObserved,
      dynamic_refill_observed: state.tasks.length <= state.frozen.run_slots || refillEvents.length > 0,
      status: concurrencyObserved ? "PASS" : "INSUFFICIENT_EVIDENCE",
    },
  };
}

async function refreshProbe(config, destination) {
  await mkdir(dirname(destination), { recursive: true });
  const result = await runCapture(process.execPath, [
    PROBE_PATH,
    "--app-path", "/Applications/QwenWorkCN.app",
    "--session-db", config.client.session_db,
    "--trace-root", config.client.trace_root,
    "--endpoint", config.client.endpoint,
    "--output", destination,
    "--replace",
    "--online-snapshot",
  ], { capture: true, allowFailure: true });
  if (result.code !== 0) throw new Error(`QWENWORK_QUEUE_PROBE_FAILED: ${result.stderr || result.stdout}`);
  const content = await readFile(destination);
  return { path: destination, sha256: sha256(content) };
}

function activeSessionArgs(state) {
  return state.tasks.filter((row) => row.phase === "RUNNING")
    .flatMap((row) => [
      ...(row.session_id ? ["--allowed-active-session-id", row.session_id] : []),
      ...(row.conversation_id ? ["--allowed-active-conversation-id", row.conversation_id] : []),
    ]);
}

async function runQwenTask(configPath, row, state, options, dependencies, {
  resume = false, probe = null, prepareOnly = false, initialProbe = null,
} = {}) {
  const args = ["--config", configPath];
  if (resume) {
    args.push("--resume", "--observe-once", "--resume-probe", probe.path, "--resume-probe-sha256", probe.sha256);
  } else {
    args.push("--initial-probe", initialProbe?.path || options.probe,
      "--initial-probe-sha256", initialProbe?.sha256 || options.probeSha256);
  }
  if (prepareOnly) args.push("--prepare-only");
  args.push("--managed-queue-id", state.queue_id, ...activeSessionArgs(state));
  if (dependencies.execute) return dependencies.execute(args);
  const result = await runCapture(process.execPath, [DRIVER_PATH, ...args], { capture: true, allowFailure: true });
  return result.code;
}

async function acquireOwner(path) {
  await mkdir(dirname(path), { recursive: true });
  const handle = await open(path, "wx", 0o600).catch((error) => {
    if (error?.code === "EEXIST") throw new Error("QWENWORK_QUEUE_OWNER_EXISTS: 不自动删除活动或陈旧锁");
    throw error;
  });
  await handle.writeFile(JSON.stringify({ pid: process.pid, host: hostname(), acquired_at: new Date().toISOString() }));
  return async () => { await handle.close(); await rm(path, { force: true }); };
}

export async function runQwenWorkBatch(argv, dependencies = {}) {
  const batch = parseBatchArgs(argv);
  const root = resolve(batch.args[batch.args.indexOf("--unit-root") + 1] || "");
  const manifestInfo = await readManifest(root);
  if (!batch.sessionDb || !batch.traceRoot) throw new Error("--session-db 与 --trace-root 必须指定");
  const queueRoot = join(root, ".general-e2e", "queues", "qwenwork");
  const statePath = join(queueRoot, `${batch.queueId}.json`);
  const receiptPath = join(queueRoot, `${batch.queueId}-receipt.json`);
  const ownerPath = join(queueRoot, "owner-lock.json");
  const existingConfigs = batch.configDir
    ? await loadExistingConfigs(batch.configDir, manifestInfo.taskIds, manifestInfo.manifest)
    : null;
  const manifestHash = sha256(manifestInfo.bytes);
  const frozen = {
    batch_id: manifestInfo.manifest.batch_id,
    unit_id: manifestInfo.manifest.unit_id,
    unit_root: root,
    manifest_sha256: manifestHash,
    task_ids: manifestInfo.taskIds,
    endpoint: batch.endpoint,
    session_db: batch.sessionDb,
    trace_root: batch.traceRoot,
    config_dir: batch.configDir || null,
    config_sources: existingConfigs
      ? manifestInfo.taskIds.map((taskId) => ({ task_id: taskId, sha256: existingConfigs.get(taskId).sha256 }))
      : null,
    ui_slots: 1,
    run_slots: batch.runSlots,
    preprepare_projects: batch.preprepareProjects,
    clarification_policy: batch.skipClarifications ? "skip-question-card" : "manual",
    driver_sha256: await driverSourceDigest(),
  };
  const digest = sha256(JSON.stringify(frozen));
  let state = await optionalJson(statePath);
  if (batch.status) {
    if (!state) throw new Error("QWENWORK_QUEUE_MISSING");
    if (state.schema_version !== QWENWORK_QUEUE_SCHEMA || state.frozen_sha256 !== digest) throw new Error("QWENWORK_QUEUE_CONFIG_DRIFT");
    return { ...state, state_file: statePath, receipt_file: receiptPath };
  }
  const releaseOwner = await acquireOwner(ownerPath);
  const sleep = dependencies.sleep || ((milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds)));
  const now = dependencies.now || (() => new Date().toISOString());
  try {
    if (state && !batch.resume) throw new Error("QWENWORK_QUEUE_EXISTS: 使用 --resume，禁止重建队列");
    if (!state && batch.resume) throw new Error("QWENWORK_QUEUE_MISSING");
    if (state && (state.schema_version !== QWENWORK_QUEUE_SCHEMA || state.frozen_sha256 !== digest)) throw new Error("QWENWORK_QUEUE_CONFIG_DRIFT");
    if (!state) {
      const tasks = [];
      for (let index = 0; index < manifestInfo.taskIds.length; index += 1) {
        const taskId = manifestInfo.taskIds[index];
        const attemptId = `${manifestInfo.manifest.batch_id}-${String(index + 1).padStart(3, "0")}`;
        const existing = existingConfigs?.get(taskId);
        const built = existing
          ? { paths: executionPaths(root, taskId, existing.config.identity.attempt_id), config: existing.config }
          : await buildTaskConfig(root, manifestInfo, taskId, attemptId, batch, frozen);
        tasks.push({
          task_id: taskId,
          attempt_id: existing?.config.identity.attempt_id || attemptId,
          config_path: existing?.path || built.paths.config,
          state_file: existing?.config.state_file || built.paths.journal,
          phase: "PENDING", prepared: false, dispatch_attempt_count: 0, session_id: null,
          conversation_id: null, sub_chat_id: null, cwd: null, started_at: null,
          dispatch_started_at: null, finished_at: null, native_started_at: null,
          native_finished_at: null, error: null, exit_code: null,
        });
      }
      state = {
        schema_version: QWENWORK_QUEUE_SCHEMA,
        worker: { id: "qwenwork-macos-concurrent", version: QWENWORK_QUEUE_VERSION },
        queue_id: batch.queueId, frozen, frozen_sha256: digest, phase: "PENDING",
        active_task_ids: [], tasks, events: [{ event: "QUEUE_CREATED", at: now() }],
      };
      await persist(statePath, state);
    }
    if (TERMINAL_PHASES.has(state.phase) || state.phase === "COMPLETED_WITH_FAILURES") {
      for (const row of state.tasks) await synchronizeRow(root, row);
      return { ...state, state_file: statePath, receipt_file: receiptPath };
    }
    state.phase = "RUNNING";
    state.events.push({ event: batch.resume ? "QUEUE_RESUMED" : "QUEUE_STARTED", at: now() });
    await persist(statePath, state);
    const recoveredAttention = new Set();
    for (;;) {
      for (const row of state.tasks) await synchronizeRow(root, row);
      let running = state.tasks.filter((row) => row.phase === "RUNNING");
      let attention = state.tasks.filter((row) => row.phase === "NEEDS_ATTENTION");
      if (batch.resume) {
        for (const row of attention.filter((item) => !recoveredAttention.has(item.task_id))) {
          recoveredAttention.add(row.task_id);
          const baseConfig = await readJson(row.config_path);
          const probePath = join(queueRoot, "probes", `${row.task_id}-${Date.now()}.json`);
          const probe = dependencies.execute ? { path: batch.probe, sha256: batch.probeSha256 } : await refreshProbe(baseConfig, probePath);
          row.exit_code = await runQwenTask(row.config_path, row, state, batch, dependencies, {
            resume: true, probe,
            prepareOnly: batch.preprepareProjects && row.dispatch_attempt_count === 0,
          });
          await synchronizeRow(root, row);
          state.events.push({ event: "TASK_ATTENTION_RECOVERY_RETURNED", at: now(), task_id: row.task_id, task_phase: row.phase, exit_code: row.exit_code });
          await persist(statePath, state);
        }
        running = state.tasks.filter((row) => row.phase === "RUNNING");
        attention = state.tasks.filter((row) => row.phase === "NEEDS_ATTENTION");
      }
      if (attention.length) {
        state.phase = "NEEDS_ATTENTION";
        state.active_task_ids = running.map((row) => row.task_id);
        await persist(statePath, state);
        return { ...state, state_file: statePath, receipt_file: receiptPath };
      }
      if (batch.preprepareProjects) {
        for (const row of state.tasks.filter((item) => item.phase === "PENDING" && !item.prepared)) {
          const baseConfig = await readJson(row.config_path);
          const probePath = join(queueRoot, "probes", `prepare-${row.task_id}-${Date.now()}.json`);
          const probe = dependencies.execute
            ? { path: batch.probe, sha256: batch.probeSha256 }
            : await refreshProbe(baseConfig, probePath);
          row.exit_code = await runQwenTask(row.config_path, row, state, batch, dependencies, {
            prepareOnly: true, initialProbe: probe,
          });
          await synchronizeRow(root, row);
          state.events.push({ event: "TASK_PREPARATION_RETURNED", at: now(),
            task_id: row.task_id, task_phase: row.phase, prepared: row.prepared, exit_code: row.exit_code });
          await persist(statePath, state);
          if (!row.prepared) {
            state.phase = "NEEDS_ATTENTION";
            state.active_task_ids = running.map((item) => item.task_id);
            await persist(statePath, state);
            return { ...state, state_file: statePath, receipt_file: receiptPath };
          }
        }
      }
      while (running.length < state.frozen.run_slots) {
        const pending = state.tasks.find((row) => row.phase === "PENDING");
        if (!pending) break;
        pending.phase = "DISPATCHING";
        state.active_task_ids = [...running.map((row) => row.task_id), pending.task_id];
        state.events.push({ event: "TASK_DISPATCH_REQUESTED", at: now(), task_id: pending.task_id, active_before_dispatch: running.length, completed_before_dispatch: state.tasks.filter((row) => row.phase === "COMPLETED").length });
        await persist(statePath, state);
        let dispatchProbe = null;
        if (pending.prepared && !dependencies.execute) {
          const baseConfig = await readJson(pending.config_path);
          dispatchProbe = await refreshProbe(baseConfig,
            join(queueRoot, "probes", `dispatch-${pending.task_id}-${Date.now()}.json`));
        }
        pending.exit_code = await runQwenTask(pending.config_path, pending, state, batch, dependencies,
          pending.prepared ? { resume: true, probe: dispatchProbe || { path: batch.probe, sha256: batch.probeSha256 } } : {});
        await synchronizeRow(root, pending);
        state.events.push({ event: "TASK_DISPATCH_RETURNED", at: now(), task_id: pending.task_id, task_phase: pending.phase, exit_code: pending.exit_code, active_before_dispatch: running.length, completed_before_dispatch: state.tasks.filter((row) => row.phase === "COMPLETED").length });
        await persist(statePath, state);
        if (["NEEDS_ATTENTION", "FAILED"].includes(pending.phase)) break;
        running = state.tasks.filter((row) => row.phase === "RUNNING");
      }
      running = state.tasks.filter((row) => row.phase === "RUNNING");
      const pending = state.tasks.filter((row) => row.phase === "PENDING");
      const attentionAfterObservation = state.tasks.filter((row) => row.phase === "NEEDS_ATTENTION");
      if (attentionAfterObservation.length) {
        state.phase = "NEEDS_ATTENTION";
        state.active_task_ids = running.map((row) => row.task_id);
        await persist(statePath, state);
        return { ...state, state_file: statePath, receipt_file: receiptPath };
      }
      if (!running.length && !pending.length) {
        const failed = state.tasks.filter((row) => row.phase === "FAILED");
        state.phase = failed.length ? "COMPLETED_WITH_FAILURES" : "COMPLETED";
        state.active_task_ids = [];
        state.events.push({ event: state.phase === "COMPLETED" ? "QUEUE_COMPLETED" : "QUEUE_COMPLETED_WITH_FAILURES", at: now() });
        await persist(statePath, state);
        await persist(receiptPath, buildReceipt(state));
        return { ...state, state_file: statePath, receipt_file: receiptPath };
      }
      if (!running.length) {
        state.phase = "NEEDS_ATTENTION";
        state.events.push({ event: "QUEUE_STALLED", at: now() });
        await persist(statePath, state);
        return { ...state, state_file: statePath, receipt_file: receiptPath };
      }
      let changed = false;
      for (const row of running) {
        const before = row.phase;
        const baseConfig = await readJson(row.config_path);
        const probePath = join(queueRoot, "probes", `${row.task_id}-${Date.now()}.json`);
        const probe = dependencies.execute ? { path: batch.probe, sha256: batch.probeSha256 } : await refreshProbe(baseConfig, probePath);
        row.exit_code = await runQwenTask(row.config_path, row, state, batch, dependencies, { resume: true, probe });
        await synchronizeRow(root, row);
        changed ||= row.phase !== before;
        state.events.push({ event: "TASK_OBSERVATION_RETURNED", at: now(), task_id: row.task_id, task_phase: row.phase, exit_code: row.exit_code });
        await persist(statePath, state);
      }
      state.active_task_ids = state.tasks.filter((row) => row.phase === "RUNNING").map((row) => row.task_id);
      if (state.tasks.some((row) => row.phase === "NEEDS_ATTENTION")) {
        state.phase = "NEEDS_ATTENTION";
        await persist(statePath, state);
        return { ...state, state_file: statePath, receipt_file: receiptPath };
      }
      if (!changed) await sleep(1000);
    }
  } finally {
    await releaseOwner();
  }
}

if (process.argv[1] && await realpath(resolve(process.argv[1])) === await realpath(fileURLToPath(import.meta.url))) {
  if (process.argv.includes("--help")) {
    console.log("QwenWork macOS General 队列：node drivers/qwenwork/batch.mjs --unit-root PATH --queue-id ID --endpoint http://127.0.0.1:9250 --session-db PATH --trace-root PATH --probe PATH --probe-sha256 SHA [--run-slots 1-8] [--preprepare-projects] [--skip-clarifications] [--resume|--status]。UI 单槽，后台默认三路并按可信终态动态补位。");
  } else {
    runQwenWorkBatch(process.argv.slice(2)).then((result) => {
      console.log(JSON.stringify(result, null, 2));
      if (!["COMPLETED", "COMPLETED_WITH_FAILURES"].includes(result.phase)) process.exitCode = 3;
    }).catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
  }
}
