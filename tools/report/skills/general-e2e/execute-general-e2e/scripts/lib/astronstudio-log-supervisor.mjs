import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { link, lstat, mkdir, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { setTimeout as wait } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { readEvidenceJson, syncEvidenceDirectory, writeEvidenceBytes, writeEvidenceJson } from "./astronstudio-evidence-files.mjs";
import { hostBootId } from "./astronstudio-host-evidence.mjs";
import { createNativeLogSpool } from "./astronstudio-log-spool.mjs";

const entry = fileURLToPath(import.meta.url);
const orphanMs = 120_000;
const pollMs = 2_000;

function isAlive(pid) {
  if (!Number.isInteger(pid) || pid < 2) throw Error("ASTUDIO_COLLECTOR_INVALID_PID");
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    throw error;
  }
}

function paths(output) {
  return Object.fromEntries(["config", "control", "owner", "status"].map(name => [name, join(output, name + ".json")]));
}

async function awaitStatus(files, request, phases) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    const status = await readEvidenceJson(files.status);
    if (status?.request_id === request && status.phase === "ERROR") throw Error(status.error);
    if (status?.request_id === request && phases.includes(status.phase)) {
      if (status.phase !== "STOPPED" || !await readEvidenceJson(files.owner)) return status;
    }
    await wait(100);
  }
  throw Error("ASTUDIO_COLLECTOR_ACK_TIMEOUT");
}

export async function startNativeLogSpool(database, output, options = {}) {
  await mkdir(output, { mode: 0o700, recursive: true });
  const info = await lstat(output);
  if (!info.isDirectory() || info.isSymbolicLink() || (info.mode & 0o077)) throw Error("ASTUDIO_COLLECTOR_DIRECTORY_UNSAFE");
  const files = paths(output);
  const config = {
    log_root: join(dirname(database), "logs"), queueState: options.queueState ?? null,
    journal: options.journal ?? null, appPath: options.appPath ?? null, queueLock: options.queueLock ?? null,
  };
  const stored = await readEvidenceJson(files.config);
  if (stored && Object.keys(config).some(key => config[key] !== stored[key])) throw Error("ASTUDIO_COLLECTOR_CONFIG_MISMATCH");
  if (!stored) await writeEvidenceJson(files.config, config);

  async function command(action) {
    const request = randomUUID();
    await writeEvidenceJson(files.control, { request_id: request, action, owner_pid: process.pid,
      owner_token: options.ownerToken ?? null, requested_ms: Date.now() });
    return request;
  }

  async function ensureCollector() {
    const owner = await readEvidenceJson(files.owner);
    if (owner && isAlive(owner.pid)) return owner;
    if (owner) {
      if (!/^[0-9a-f-]{36}$/u.test(owner.instance_id)) throw Error("ASTUDIO_COLLECTOR_UNKNOWN_OWNER");
      // Caller holds the queue Worker lock. Recheck before recovering this known collector.
      const same = await readEvidenceJson(files.owner);
      if (owner.instance_id !== same?.instance_id || isAlive(same.pid)) throw Error("ASTUDIO_COLLECTOR_OWNER_CHANGED");
      await rm(files.owner);
    }
    const worker = spawn(process.execPath, [entry, output, randomUUID()], { detached: true, stdio: "ignore" });
    worker.unref();
    await new Promise((ready, reject) => {
      worker.once("spawn", ready);
      worker.once("error", reject);
    });
    return null;
  }

  let request = await command("capture");
  await ensureCollector();
  await awaitStatus(files, request, ["CAPTURING"]);
  let nextCheck = 0;
  let restarts = 0;
  return {
    async ensure() {
      if (Date.now() < nextCheck) return;
      nextCheck = Date.now() + 5_000;
      const owner = await readEvidenceJson(files.owner);
      if (!owner || !isAlive(owner.pid)) {
        if (restarts >= 2) throw Error("ASTUDIO_COLLECTOR_RESTART_LIMIT");
        restarts++;
        request = await command("capture");
        await ensureCollector();
        await awaitStatus(files, request, ["CAPTURING"]);
        return true;
      }
      const status = await readEvidenceJson(files.status);
      if (status?.request_id !== request || status?.phase !== "CAPTURING"
          || Date.now() - Date.parse(status.at) > 30_000
          || (owner && owner.instance_id !== status.instance_id)) {
        throw Error("ASTUDIO_COLLECTOR_HEARTBEAT_UNAVAILABLE");
      }
      return true;
    },
    async stop(action = "stop") {
      const stop = await command(action);
      await ensureCollector();
      await awaitStatus(files, stop, action === "stop" ? ["STOPPED"] : ["DRAINING"]);
      return 0;
    },
  };
}

async function runCollector(output, instance) {
  const files = paths(output);
  const temporary = join(output, "owner-" + instance + ".tmp");
  try {
    await writeEvidenceBytes(temporary, JSON.stringify({ pid: process.pid, instance_id: instance }));
    await link(temporary, files.owner);
    await syncEvidenceDirectory(output);
  } finally {
    await rm(temporary, { force: true });
  }
  let control;
  let status;
  let phase;
  let orphanedAt;
  let previousControl;
  let previousPhase;
  try {
    const config = await readEvidenceJson(files.config);
    const bootId = await hostBootId();
    const old = await readEvidenceJson(files.status);
    const sample = await createNativeLogSpool(config.log_root, output, Date.now, { ...config, bootId });
    let outage = old && !["STOPPED", "DRAINING"].includes(old.phase) ? {
      reason: "collector_restarted", previous_instance_id: old.instance_id, from_at: old.at,
    } : null;
    while (true) {
      control = await readEvidenceJson(files.control);
      if (!control) throw Error("ASTUDIO_COLLECTOR_CONTROL_MISSING");
      const now = Date.now();
      const queueOwner = config.queueLock ? await readEvidenceJson(config.queueLock) : null;
      const sameQueueOwner = !config.queueLock || (queueOwner?.token === control.owner_token && queueOwner?.pid === control.owner_pid);
      if (control.action === "capture" && sameQueueOwner && isAlive(control.owner_pid)) {
        orphanedAt = null;
        phase = "CAPTURING";
      } else {
        orphanedAt ??= control.action === "capture" ? now : control.requested_ms;
        phase = "DRAINING";
      }
      if (previousControl && control.action === "capture"
          && (previousControl.owner_pid !== control.owner_pid || previousControl.owner_token !== control.owner_token)) {
        outage ??= { reason: "queue_worker_changed", previous_pid: previousControl.owner_pid, current_pid: control.owner_pid };
      } else if (previousPhase === "CAPTURING" && phase === "DRAINING" && control.action === "capture") {
        outage ??= { reason: "queue_worker_exited", previous_pid: control.owner_pid };
      }
      const finalReason = control.action === "stop" ? "explicit_stop"
        : orphanedAt !== null && now - orphanedAt >= orphanMs ? "collector_grace_elapsed" : null;
      await sample({ finalReason, outage });
      outage = null;
      status = { at: new Date().toISOString(), pid: process.pid, instance_id: instance,
        request_id: control.request_id, phase: finalReason ? "STOPPED" : phase };
      await writeEvidenceJson(files.status, status);
      if (finalReason) break;
      previousControl = control;
      previousPhase = phase;
      await wait(pollMs);
    }
  } catch (error) {
    await writeEvidenceJson(files.status, {
      at: new Date().toISOString(), instance_id: instance, pid: process.pid,
      request_id: control?.request_id, phase: "ERROR", error: error.code || error.message,
    }).catch(() => {});
    throw error;
  } finally {
    const owner = await readEvidenceJson(files.owner);
    if (owner?.instance_id === instance) await rm(files.owner);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === entry) {
  try {
    await runCollector(process.argv[2], process.argv[3]);
  } catch {
    process.exitCode = 1;
  }
}
