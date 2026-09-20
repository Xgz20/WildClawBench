#!/usr/bin/env node
import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdir, open, readFile, realpath, rename, rm, writeFile } from "node:fs/promises";
import { hostname } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { main as execute, parseArgs, resolveExecutionConfig } from "./execute.mjs";

const SCHEMA = "wildclawbench.general-e2e-workbuddy-serial-queue/v1";
const safeId = (id) => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(id);
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const readJson = async (path) => JSON.parse(await readFile(path, "utf8"));
async function optionalJson(path) {
  try { return await readJson(path); } catch (error) { if (error.code === "ENOENT") return null; throw error; }
}
async function persist(path, value) {
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

export async function runWorkBuddyBatch(argv, dependencies = {}) {
  const args = [...argv];
  const queueFlag = args.indexOf("--queue-id");
  const queueId = args[queueFlag + 1];
  if (queueFlag < 0 || !safeId(queueId)) throw new Error("--queue-id 必须是安全的非空 ID");
  args.splice(queueFlag, 2);
  const resume = args.includes("--resume");
  if (resume) args.splice(args.indexOf("--resume"), 1);
  if (["--task-id", "--attempt-id", "--detach-after-submit", "--observe-once"].some((flag) => args.includes(flag))) {
    throw new Error("串行队列执行 manifest 全集，不接受单题/脱离观察选项");
  }
  const parsed = parseArgs([...args, "--task-id", "queue-config"]);
  const root = await realpath(resolve(parsed.unitRoot));
  await assertPlainPath(root, ["manifest.json"]);
  const manifestBytes = await readFile(join(root, "manifest.json"));
  const manifest = JSON.parse(manifestBytes);
  const taskIds = manifest.task_ids;
  if (!Array.isArray(taskIds) || !taskIds.length || taskIds.some((id) => !safeId(id))
      || new Set(taskIds).size !== taskIds.length) throw new Error("WORKBUDDY_QUEUE_TASKS_INVALID");
  // Resolve every task before any dispatch, including paths and Prompt digests.
  const configs = [];
  for (const taskId of taskIds) configs.push(await resolveExecutionConfig({ ...parsed, taskId }));
  const frozen = {
    unit_root: root, manifest_sha256: hash(manifestBytes), task_ids: taskIds,
    endpoint: parsed.endpoint, app_path: parsed.appPath,
    model: configs[0].expectedModel, permission: parsed.expectedPermission,
    session_db: parsed.sessionDb, data_root: parsed.dataRoot,
    timeout_ms: parsed.timeoutMs, identity_timeout_ms: parsed.identityTimeoutMs,
    poll_interval_ms: parsed.pollIntervalMs, ui_slots: 1, run_slots: 1,
    driver_sha256: hash(await readFile(new URL("./execute.mjs", import.meta.url))),
  };
  const digest = hash(JSON.stringify(frozen));
  await assertPlainPath(root, [".general-e2e", "queues", "workbuddy", `${queueId}.json`]);
  const queueRoot = join(root, ".general-e2e", "queues", "workbuddy");
  await mkdir(queueRoot, { recursive: true });
  const statePath = join(queueRoot, `${queueId}.json`);
  const lockPath = join(queueRoot, "owner-lock.json");
  await assertPlainPath(root, [".general-e2e", "queues", "workbuddy", "owner-lock.json"]);
  const lock = await open(lockPath, "wx", 0o600).catch((error) => {
    if (error.code === "EEXIST") throw new Error("WORKBUDDY_QUEUE_OWNER_EXISTS: 不自动删除活动或陈旧锁");
    throw error;
  });
  const lockStat = await lock.stat({ bigint: true });
  try {
    await lock.writeFile(JSON.stringify({ pid: process.pid, host: hostname(), started_at: new Date().toISOString(), queue_id: queueId }));
    let state = await optionalJson(statePath);
    if (state && !resume) throw new Error("WORKBUDDY_QUEUE_EXISTS: 使用 --resume，禁止重建队列");
    if (!state && resume) throw new Error("WORKBUDDY_QUEUE_MISSING");
    if (state && (state.schema_version !== SCHEMA || state.frozen_sha256 !== digest)) {
      throw new Error("WORKBUDDY_QUEUE_CONFIG_DRIFT");
    }
    if (!state) {
      // A new queue never adopts attempts created outside this queue.
      for (const config of configs) {
        if (await optionalJson(config.journalFile)) throw new Error(`WORKBUDDY_QUEUE_ATTEMPT_ALREADY_EXISTS: ${config.task.task_id}`);
      }
      state = { schema_version: SCHEMA, queue_id: queueId, frozen, frozen_sha256: digest,
        phase: "PENDING", tasks: taskIds.map((task_id) => ({ task_id, phase: "PENDING", attempt_id: randomUUID() })), events: [] };
      await persist(statePath, state);
    }
    for (let index = 0; index < configs.length; index += 1) {
      const config = configs[index];
      const row = state.tasks[index];
      if (row.task_id !== config.task.task_id) throw new Error("WORKBUDDY_QUEUE_TASK_DRIFT");
      const before = await optionalJson(config.journalFile);
      if (before && before.identity?.attempt_id !== row.attempt_id) throw new Error("WORKBUDDY_QUEUE_ATTEMPT_DRIFT");
      if (!before && row.phase === "COMPLETED") throw new Error("WORKBUDDY_QUEUE_REGISTERED_ATTEMPT_MISSING");
      if (row.phase === "COMPLETED") {
        if (before?.phase !== "COMPLETED") throw new Error("WORKBUDDY_QUEUE_TERMINAL_DRIFT");
        continue;
      }
      if (before && row.phase === "PENDING") throw new Error("WORKBUDDY_QUEUE_UNREGISTERED_ATTEMPT");
      state.phase = "RUNNING";
      row.phase = "RUNNING";
      state.events.push({ task_id: row.task_id, event: before ? "RESUME" : "START", at: new Date().toISOString() });
      await persist(statePath, state);
      const code = await (dependencies.execute || execute)([
        ...args, "--task-id", row.task_id, "--attempt-id", row.attempt_id, ...(before ? ["--resume"] : []),
      ], dependencies.executeOverrides || {});
      const journal = await optionalJson(config.journalFile);
      if (journal && journal.identity?.attempt_id !== row.attempt_id) throw new Error("WORKBUDDY_QUEUE_ATTEMPT_DRIFT");
      row.phase = code === 0 && journal?.phase === "COMPLETED" ? "COMPLETED" : "NEEDS_ATTENTION";
      row.exit_code = code;
      state.events.push({ task_id: row.task_id, event: row.phase, attempt_id: row.attempt_id, at: new Date().toISOString() });
      if (row.phase !== "COMPLETED") {
        state.phase = "NEEDS_ATTENTION";
        await persist(statePath, state);
        return { ...state, state_file: statePath };
      }
      await persist(statePath, state);
    }
    state.phase = "COMPLETED";
    await persist(statePath, state);
    return { ...state, state_file: statePath };
  } finally {
    await lock.close();
    const current = await lstat(lockPath, { bigint: true }).catch(() => null);
    if (current && !current.isSymbolicLink() && current.dev === lockStat.dev && current.ino === lockStat.ino) await rm(lockPath);
  }
}

if (process.argv[1] && await realpath(resolve(process.argv[1])) === await realpath(fileURLToPath(import.meta.url))) {
  if (process.argv.includes("--help")) {
    console.log("WorkBuddy macOS 串行队列：node drivers/workbuddy/batch.mjs --unit-root PATH --queue-id ID --endpoint http://127.0.0.1:9229 --expected-permission default-sandbox [--resume]。按 manifest 全集执行；UI/运行均为单槽，遇异常停止新投递。");
  } else {
    runWorkBuddyBatch(process.argv.slice(2)).then((result) => {
      console.log(JSON.stringify(result, null, 2));
      if (result.phase !== "COMPLETED") process.exitCode = 3;
    }).catch((error) => { console.error(error.message); process.exitCode = 1; });
  }
}
