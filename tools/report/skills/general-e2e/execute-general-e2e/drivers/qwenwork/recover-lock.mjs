#!/usr/bin/env node

import { createHash } from "node:crypto";
import { link, lstat, mkdir, open, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { assertQwenCanaryConfig, assertQwenCanaryProbe, inspectLockOwner, loadQwenCanaryConfig } from "./driver.mjs";
import { assertNoSymlinkPath, assertQwenJournalMatches } from "./journal.mjs";

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const readJson = async (path) => JSON.parse(await readFile(path, "utf8"));

export async function recoverQwenAttemptLock({ unitRoot, config, expectedOwnerId }, overrides = {}) {
  const inspect = overrides.inspectOwner || inspectLockOwner;
  assertQwenCanaryConfig(config, { requireLiveAuthorization: true });
  await assertNoSymlinkPath(unitRoot);
  const root = await realpath(unitRoot);
  const rel = relative(root, config.state_file);
  if (!rel || rel.startsWith("..") || isAbsolute(rel)) throw new Error("QWEN_RECOVERY_STATE_OUTSIDE_UNIT");
  if (!/^[A-Za-z0-9-]{1,64}$/u.test(expectedOwnerId || "")) throw new Error("QWEN_RECOVERY_OWNER_ID_INVALID");
  if (config.recovery_probe?.verified !== true || config.recovery_probe.active_or_pending_count !== 0) {
    throw new Error("QWEN_RECOVERY_IDLE_PROBE_REQUIRED");
  }
  const verifyProbe = async () => {
    const path = config.recovery_probe.path;
    if (!isAbsolute(path || "") || resolve(path) === resolve(config.control.probe_path)) {
      throw new Error("QWEN_RECOVERY_DISTINCT_PROBE_REQUIRED");
    }
    await assertNoSymlinkPath(path, { requireLeaf: true });
    const bytes = await readFile(path);
    if (sha256(bytes) !== config.recovery_probe.sha256) throw new Error("QWEN_RECOVERY_PROBE_CHANGED");
    const probe = JSON.parse(bytes);
    assertQwenCanaryProbe(probe, config, Date.now(), { requireFresh: true, requireIdle: true });
    if (probe.app?.cdp?.ready !== true || probe.app?.cdp?.browser_identity_present !== true) {
      throw new Error("QWEN_RECOVERY_CDP_NOT_READY");
    }
  };
  await verifyProbe();
  await assertNoSymlinkPath(join(root, "manifest.json"), { requireLeaf: true });
  const manifest = await readJson(join(root, "manifest.json"));
  if (manifest.batch_id !== config.identity.batch_id || manifest.unit_id !== config.identity.unit_id
      || !manifest.task_ids?.includes(config.identity.task_id)) throw new Error("QWEN_RECOVERY_MANIFEST_MISMATCH");
  const lockPath = `${config.state_file}.lock`;
  await assertNoSymlinkPath(config.state_file, { requireLeaf: true });
  await assertNoSymlinkPath(lockPath, { requireLeaf: true });
  const guardPath = `${lockPath}.recovery`;
  const guard = await open(guardPath, "wx", 0o600).catch((error) => {
    if (error.code === "EEXIST") throw new Error("QWEN_RECOVERY_ALREADY_ACTIVE");
    throw error;
  });
  try {
    const journalBefore = await readFile(config.state_file);
    assertQwenJournalMatches(JSON.parse(journalBefore), {
      identity: config.identity, dataset: config.dataset, configDigest: config.config_digest,
      candidateWorkspace: config.candidate_workspace, prompt: config.prompt,
    });
    const lockBefore = await readFile(lockPath);
    const owner = JSON.parse(lockBefore);
    if (owner.schema_version !== "wildclawbench.general-e2e-qwenwork-attempt-lock/v1"
        || owner.owner_id !== expectedOwnerId || owner.attempt_id !== config.identity.attempt_id
        || resolve(owner.state_file || "/") !== resolve(config.state_file)
        || !owner.process_start_identity) throw new Error("QWEN_RECOVERY_LOCK_IDENTITY_MISMATCH");
    const status = await inspect(owner);
    if (!status.verifiable || !status.stale || status.active) throw new Error("QWEN_RECOVERY_DRIVER_ACTIVE_OR_UNKNOWN");
    const queueOwnerPath = join(root, ".general-e2e", "queues", "qwenwork", "owner-lock.json");
    let queueBefore = null;
    try {
      await assertNoSymlinkPath(queueOwnerPath, { requireLeaf: true });
      queueBefore = await readFile(queueOwnerPath);
      const queueOwner = JSON.parse(queueBefore);
      if (queueOwner.schema_version !== "wildclawbench.general-e2e-qwenwork-queue-owner/v1"
          || !queueOwner.process_start_identity) throw new Error("QWEN_RECOVERY_QUEUE_IDENTITY_INVALID");
      const queueStatus = await inspect(queueOwner);
      if (!queueStatus.verifiable || !queueStatus.stale || queueStatus.active) {
        throw new Error("QWEN_RECOVERY_QUEUE_ACTIVE_OR_UNKNOWN");
      }
    } catch (error) { if (error.code !== "ENOENT") throw error; }
    const archivePath = `${lockPath}.stale-${expectedOwnerId}.json`;
    const assertUnchanged = async () => {
      await assertNoSymlinkPath(lockPath, { requireLeaf: true });
      await assertNoSymlinkPath(config.state_file, { requireLeaf: true });
      await assertNoSymlinkPath(queueOwnerPath);
      const queueNow = await readFile(queueOwnerPath).catch((error) => {
        if (error.code === "ENOENT") return null;
        throw error;
      });
      if (!(await readFile(lockPath)).equals(lockBefore)
          || !(await readFile(config.state_file)).equals(journalBefore)
          || (queueBefore === null ? queueNow !== null : !queueBefore.equals(queueNow || Buffer.alloc(0)))) {
        throw new Error("QWEN_RECOVERY_SOURCE_CHANGED");
      }
    };
    await verifyProbe();
    await assertUnchanged();
    // Exclusive hard-link creation cannot overwrite an earlier recovery receipt.
    // Keep the blocking lock until its archived inode and journal are verified.
    await link(lockPath, archivePath).catch((error) => {
      if (error.code === "EEXIST") throw new Error("QWEN_RECOVERY_ARCHIVE_EXISTS");
      throw error;
    });
    const [sourceInfo, archiveInfo] = await Promise.all([lstat(lockPath), lstat(archivePath)]);
    if (sourceInfo.dev !== archiveInfo.dev || sourceInfo.ino !== archiveInfo.ino
        || !(await readFile(archivePath)).equals(lockBefore)) throw new Error("QWEN_RECOVERY_ARCHIVE_CHANGED");
    await assertUnchanged();
    await rm(lockPath, { force: false });
    return {
      schema_version: "wildclawbench.general-e2e-qwenwork-lock-recovery/v1",
      status: "RECOVERED", identity: config.identity, config_digest: config.config_digest,
      owner_id: owner.owner_id, previous_pid: owner.pid, reason: status.reason,
      archive_path: archivePath, lock_sha256: sha256(lockBefore),
      journal_sha256: sha256(journalBefore), journal_unchanged: true,
      probe: config.recovery_probe, operations: ["archive-verified-stale-attempt-lock"],
      completed_at: new Date().toISOString(),
    };
  } finally { await guard.close(); await rm(guardPath, { force: false }); }
}

async function main(args) {
  if (args.includes("--help")) {
    console.log("node recover-lock.mjs --unit-root PATH --config PATH --expected-owner-id ID --probe FRESH_JSON --probe-sha256 SHA --output NEW_JSON；仅归档已证实退出的同 attempt 锁，不发送 Prompt、不修改 journal。");
    return;
  }
  const names = new Map([["--unit-root", "unitRoot"], ["--config", "configPath"],
    ["--expected-owner-id", "expectedOwnerId"], ["--probe", "probe"],
    ["--probe-sha256", "probeSha256"], ["--output", "output"]]);
  const options = {};
  for (let index = 0; index < args.length; index += 2) {
    const key = names.get(args[index]);
    if (!key || options[key] !== undefined || !args[index + 1]
        || args[index + 1].startsWith("--")) throw new Error("QWEN_RECOVERY_ARGS_INVALID");
    options[key] = args[index + 1];
  }
  for (const key of ["unitRoot", "configPath", "probe", "output"]) {
    if (!isAbsolute(options[key] || "")) throw new Error(`QWEN_RECOVERY_PATH_INVALID: ${key}`);
    await assertNoSymlinkPath(options[key]);
  }
  const config = await loadQwenCanaryConfig(options.configPath, {
    requireLiveAuthorization: true, resume: true,
    resumeProbePath: options.probe, resumeProbeSha256: options.probeSha256,
  });
  await mkdir(dirname(options.output), { recursive: true });
  await writeFile(options.output, JSON.stringify({ status: "STARTED" }) + "\n", { flag: "wx", mode: 0o600 });
  try {
    const result = await recoverQwenAttemptLock({ ...options, config });
    await writeFile(options.output, JSON.stringify(result, null, 2) + "\n");
    console.log(JSON.stringify({ status: result.status, previous_pid: result.previous_pid,
      journal_unchanged: result.journal_unchanged, output: options.output }));
  } catch (error) {
    await writeFile(options.output, JSON.stringify({ status: "NEEDS_ATTENTION", error: error.message }, null, 2) + "\n");
    throw error;
  }
}

if (process.argv[1] && await realpath(resolve(process.argv[1])) === await realpath(fileURLToPath(import.meta.url))) {
  main(process.argv.slice(2)).catch((error) => { console.error(error.message); process.exitCode = 1; });
}
