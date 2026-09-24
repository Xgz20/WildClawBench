import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import { createHash } from "node:crypto";
import { link, lstat, open, readFile, realpath, rm } from "node:fs/promises";
import { isAbsolute, join, resolve } from "node:path";
import { hostname } from "node:os";
import { acquireExclusiveWorkerLock, readWorkerLock } from "./controller.mjs";

const execFile = promisify(execFileCallback), LOCK = ".doubaowork-driver.lock";
const sha = bytes => createHash("sha256").update(bytes).digest("hex");

export async function inspectRecoveryOwner(owner, overrides = {}) {
  if (owner.host !== (overrides.host ?? hostname())) throw new Error("DOUBAOWORK_RECOVERY_FOREIGN_HOST");
  const table = overrides.processTable ?? (await execFile("/bin/ps", ["-axo", "pid=,lstart="], { timeout: 5000, maxBuffer: 4 * 1024 * 1024 })).stdout;
  const rows = new Map();
  for (const line of table.split(/\r?\n/u).filter(s => s.trim())) {
    const match = line.match(/^\s*(\d+)\s+([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s*$/u);
    if (!match || rows.has(Number(match[1]))) throw new Error("DOUBAOWORK_RECOVERY_PROCESS_IDENTITY_UNKNOWN");
    rows.set(Number(match[1]), match[2].replace(/\s+/gu, " "));
  }
  if (!rows.has(overrides.selfPid ?? process.pid)) throw new Error("DOUBAOWORK_RECOVERY_PROCESS_TABLE_INCOMPLETE");
  const current = rows.get(owner.pid) ?? null;
  if (current === owner.process_start_identity) throw new Error("DOUBAOWORK_RECOVERY_OWNER_ACTIVE");
  return { stale: true, reason: current === null ? "owner-exited" : "pid-reused", current_start_identity: current };
}

async function ordinaryFile(path) {
  if (!isAbsolute(path) || await realpath(path) !== resolve(path)) throw new Error("DOUBAOWORK_RECOVERY_PATH_UNSAFE");
  const st = await lstat(path);
  if (!st.isFile() || st.isSymbolicLink()) throw new Error("DOUBAOWORK_RECOVERY_PATH_UNSAFE");
  return { bytes: await readFile(path), dev: st.dev, ino: st.ino };
}

// Explicit single-attempt recovery. It never edits the journal, sends a Prompt,
// kills a process, or substitutes a new attempt. A managed queue needs its own
// owner recovery protocol and is deliberately rejected by the scene adapter.
export async function recoverStaleAttemptLock({ attemptRoot, uiRoot, expectedOwnerId, protectedFiles, verifyIdle, beforeRelease }, overrides = {}) {
  if (typeof expectedOwnerId !== "string" || !/^[A-Za-z0-9-]{1,64}$/u.test(expectedOwnerId)
      || typeof verifyIdle !== "function" || !protectedFiles?.length) throw new Error("DOUBAOWORK_RECOVERY_INPUT_INVALID");
  for (const root of [attemptRoot, uiRoot]) {
    if (!isAbsolute(root) || await realpath(root) !== resolve(root) || !(await lstat(root)).isDirectory()) throw new Error("DOUBAOWORK_RECOVERY_PATH_UNSAFE");
  }
  const inspectOwner = overrides.inspectOwner ?? inspectRecoveryOwner;
  const guardPath = join(uiRoot, ".recovery-guard");
  const guard = await open(guardPath, "wx", 0o600).catch(e => {
    if (e.code === "EEXIST") throw new Error("DOUBAOWORK_RECOVERY_ALREADY_ACTIVE");
    throw e;
  });
  const guardInfo = await guard.stat();
  let releaseUi;
  try {
    const files = await Promise.all(protectedFiles.map(async path => ({ path, ...await ordinaryFile(path) })));
    const lockPath = join(attemptRoot, LOCK), owner = await readWorkerLock(lockPath);
    if (owner.instance_id !== expectedOwnerId) throw new Error("DOUBAOWORK_RECOVERY_OWNER_MISMATCH");
    const locked = await ordinaryFile(lockPath), ownerStatus = await inspectOwner(owner);
    const uiPath = join(uiRoot, LOCK);
    let ui = null;
    try {
      const record = await readWorkerLock(uiPath);
      // Do not reclaim an unrelated dead worker's global UI lock.
      if (record.host !== owner.host || record.pid !== owner.pid || record.process_start_identity !== owner.process_start_identity) {
        throw new Error("DOUBAOWORK_RECOVERY_UI_OWNER_MISMATCH");
      }
      await inspectOwner(record); ui = { record, ...await ordinaryFile(uiPath) };
    } catch (e) { if (e.code !== "ENOENT") throw e; }
    const unchanged = async () => {
      for (const file of files) {
        const current = await ordinaryFile(file.path);
        if (current.dev !== file.dev || current.ino !== file.ino || !current.bytes.equals(file.bytes)) throw new Error("DOUBAOWORK_RECOVERY_JOURNAL_OR_INPUT_CHANGED");
      }
    };
    const archive = async (path, original, record) => {
      const check = async () => {
        const current = await ordinaryFile(path);
        if (current.dev !== original.dev || current.ino !== original.ino || !current.bytes.equals(original.bytes)) throw new Error("DOUBAOWORK_RECOVERY_LOCK_CHANGED");
      };
      await inspectOwner(record); await unchanged(); await check();
      const destination = `${path}.stale-${record.instance_id}.json`;
      // Exclusive hard link keeps the exact original inode before unlinking.
      await link(path, destination).catch(e => { if (e.code === "EEXIST") throw new Error("DOUBAOWORK_RECOVERY_ARCHIVE_EXISTS"); throw e; });
      const saved = await ordinaryFile(destination);
      if (saved.dev !== original.dev || saved.ino !== original.ino || !saved.bytes.equals(original.bytes)) throw new Error("DOUBAOWORK_RECOVERY_ARCHIVE_CHANGED");
      await unchanged(); await check(); await inspectOwner(record);
      await rm(path, { force: false });
      return { path: destination, sha256: sha(saved.bytes), owner_id: record.instance_id, previous_pid: record.pid };
    };
    const checkIdle = async () => {
      const proof = await verifyIdle();
      if (proof?.verified !== true) throw new Error("DOUBAOWORK_RECOVERY_IDLE_PROOF_REQUIRED");
      return proof;
    };
    const firstProbe = await checkIdle();
    await unchanged();
    const archives = [];
    if (ui) archives.push(await archive(uiPath, ui, ui.record));
    // The regular Driver uses this same lock. If another worker wins this
    // handover, stop before touching the attempt lock.
    releaseUi = await acquireExclusiveWorkerLock(uiRoot);
    const finalProbe = await checkIdle();
    await unchanged();
    const auxiliaryRecovery = beforeRelease ? await beforeRelease() : null;
    await unchanged();
    archives.push(await archive(lockPath, locked, owner));
    await unchanged();
    return { schema: "wildclawbench.doubaowork-lock-recovery/v1", status: "RECOVERED", owner_id: owner.instance_id,
      owner_status: ownerStatus, archives, protected_files: files.map(f => ({ path: f.path, sha256: sha(f.bytes), size: f.bytes.length })),
      journal_unchanged: true, prompt_sent: 0, first_probe: firstProbe, final_probe: finalProbe,
      auxiliary_recovery: auxiliaryRecovery, completed_at: new Date().toISOString() };
  } finally {
    try { await releaseUi?.(); } finally {
      await guard.close();
      const current = await lstat(guardPath);
      if (current.dev !== guardInfo.dev || current.ino !== guardInfo.ino || current.isSymbolicLink()) throw new Error("DOUBAOWORK_RECOVERY_GUARD_CHANGED");
      await rm(guardPath, { force: false });
    }
  }
}
