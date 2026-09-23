import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { lstat, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { calculateQwenCanaryConfigDigest, QWENWORK_CANARY_CONFIG_SCHEMA } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs";
import { createQwenAttemptJournal } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/journal.mjs";
import { recoverQwenAttemptLock } from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/recover-lock.mjs";

const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const dead = { verifiable: true, stale: true, active: false, reason: "pid-not-running" };
const live = { verifiable: true, stale: false, active: true, reason: "owner-process-active" };
const save = (path, value) => writeFile(path, JSON.stringify(value) + "\n");
async function fixture(t) {
  const root = await realpath(await mkdtemp(join(tmpdir(), "qwen-lock-recovery-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const config = {
    schema_version: QWENWORK_CANARY_CONFIG_SCHEMA,
    config_digest_algorithm: "sha256-canonical-json/v1",
    identity: { batch_id: "batch", unit_id: "unit", task_id: "task", attempt_id: "attempt" },
    dataset: { id: "dataset", digest: "d".repeat(64) },
    task_root: root, candidate_workspace: join(root, "workspace"),
    prompt: { path: join(root, "prompt.md"), sha256: sha("prompt") },
    state_file: join(root, "journal.json"), evidence_root: join(root, "evidence"),
    client: { bundle_id: "cn.qwenwork.desktop.mac", endpoint: "http://127.0.0.1:9250", session_db: join(root, "db"), trace_root: join(root, "traces") },
    control: { desktop_slot_id: "slot", probe_path: join(root, "initial.json"), probe_sha256: "a".repeat(64), probe_max_age_seconds: 300,
      model_policy: "keep-current", permission_policy: "keep-current", create_new_project: true, live_execution_authorized: true },
  };
  config.config_digest = calculateQwenCanaryConfigDigest(config);
  const probePath = join(root, "fresh.json");
  const probe = { schema_version: "wildclawbench.general-e2e-qwenwork-readonly-probe/v1", probed_at: new Date().toISOString(),
    driver: { harness: "qwenwork", platform: "macos" },
    app: { bundle_id: "cn.qwenwork.desktop.mac", identity_verified: true, cdp: { ready: true, browser_identity_present: true } },
    ready_for_read_only_mapping: true, native_state: { database: { quick_check: "ok", active_or_pending_count: 0 } }, operations_performed: ["read-only-native-state"] };
  const updateProbe = async () => {
    await save(probePath, probe);
    config.recovery_probe = { verified: true, path: probePath, sha256: sha(await readFile(probePath)), probed_at: probe.probed_at, active_or_pending_count: probe.native_state.database.active_or_pending_count };
  };
  await updateProbe();
  await save(join(root, "manifest.json"), { batch_id: "batch", unit_id: "unit", task_ids: ["task"] });
  const journal = createQwenAttemptJournal({ identity: config.identity, dataset: config.dataset, taskRoot: root,
    candidateWorkspace: config.candidate_workspace, prompt: config.prompt, configDigest: config.config_digest, now: new Date().toISOString() });
  journal.phase = "DISPATCH_UNCERTAIN";
  journal.send.state = "attempted";
  journal.send.dispatch_attempt_count = 1;
  journal.prompt.send_status = "uncertain";
  await save(config.state_file, journal);
  const lockPath = config.state_file + ".lock";
  const owner = { schema_version: "wildclawbench.general-e2e-qwenwork-attempt-lock/v1", owner_id: "owner", attempt_id: "attempt",
    state_file: config.state_file, host: hostname(), pid: 12345, process_start_identity: "fixture-start" };
  await save(lockPath, owner);
  const queuePath = join(root, ".general-e2e", "queues", "qwenwork", "owner-lock.json");
  await mkdir(join(root, ".general-e2e", "queues", "qwenwork"), { recursive: true });
  const args = { unitRoot: root, config, expectedOwnerId: "owner" };
  const run = (inspectOwner = async () => dead) => recoverQwenAttemptLock(args, { inspectOwner });
  return { root, config, probe, probePath, updateProbe, journal, lockPath, owner, queuePath, args, run };
}

test("stale attempt recovery archives exact bytes and never changes uncertain journal", async (t) => {
  const f = await fixture(t);
  const before = await readFile(f.config.state_file);
  const lock = await readFile(f.lockPath);
  const result = await f.run();
  assert.equal(result.status, "RECOVERED");
  assert.equal(result.lock_sha256, sha(lock));
  assert.equal(result.journal_sha256, sha(before));
  assert.deepEqual(await readFile(result.archive_path), lock);
  assert.deepEqual(await readFile(f.config.state_file), before);
  await assert.rejects(lstat(f.lockPath), { code: "ENOENT" });
  await assert.rejects(f.run(), { code: "ENOENT" });
});

for (const [name, status] of [["live", live], ["unknown", { ...dead, verifiable: false }]]) {
  test(`${name} Driver cannot be recovered`, async (t) => {
    const f = await fixture(t);
    await assert.rejects(f.run(async () => status), /DRIVER_ACTIVE_OR_UNKNOWN/u);
    assert.equal(JSON.parse(await readFile(f.lockPath)).owner_id, "owner");
  });
}

test("active queue refuses recovery even when the attempt Driver exited", async (t) => {
  const f = await fixture(t);
  await save(f.queuePath, { schema_version: "wildclawbench.general-e2e-qwenwork-queue-owner/v1", owner_id: "queue", process_start_identity: "start" });
  await assert.rejects(f.run(async (owner) => owner.owner_id === "queue" ? live : dead), /QUEUE_ACTIVE_OR_UNKNOWN/u);
});

for (const field of ["owner_id", "attempt_id", "state_file", "process_start_identity"]) {
  test(`mismatched attempt lock ${field} remains intact`, async (t) => {
    const f = await fixture(t);
    f.owner[field] = field === "process_start_identity" ? "" : "mismatch";
    await save(f.lockPath, f.owner);
    await assert.rejects(f.run(), /LOCK_IDENTITY_MISMATCH/u);
    assert.deepEqual(JSON.parse(await readFile(f.lockPath)), f.owner);
  });
}

test("config and manifest identity drift are refused", async (t) => {
  const f = await fixture(t);
  f.config.config_digest = "b".repeat(64);
  await assert.rejects(f.run(), /DIGEST_MISMATCH/u);
  f.config.config_digest = calculateQwenCanaryConfigDigest(f.config);
  await save(join(f.root, "manifest.json"), { batch_id: "other", unit_id: "unit", task_ids: ["task"] });
  await assert.rejects(f.run(), /MANIFEST_MISMATCH/u);
});

test("two recovery workers cannot both archive or remove the lock", async (t) => {
  const f = await fixture(t);
  let release, entered;
  const waiting = new Promise((r) => { release = r; });
  const inspecting = new Promise((r) => { entered = r; });
  const first = f.run(async () => { entered(); await waiting; return dead; });
  await inspecting;
  try { await assert.rejects(f.run(), /RECOVERY_ALREADY_ACTIVE/u); }
  finally { release(); }
  assert.equal((await first).status, "RECOVERED");
});

test("existing archive is never overwritten", async (t) => {
  const f = await fixture(t);
  const archive = f.lockPath + ".stale-owner.json";
  await writeFile(archive, "preserve-me");
  await assert.rejects(f.run(), /ARCHIVE_EXISTS/u);
  assert.equal(await readFile(archive, "utf8"), "preserve-me");
  assert.equal(JSON.parse(await readFile(f.lockPath)).owner_id, "owner");
});

for (const target of ["journal", "queue"]) {
  test(`${target} changes while inspecting owner stop recovery`, async (t) => {
    const f = await fixture(t);
    if (target === "queue") await save(f.queuePath, {
      schema_version: "wildclawbench.general-e2e-qwenwork-queue-owner/v1", owner_id: "queue", process_start_identity: "start",
    });
    await assert.rejects(f.run(async (owner) => {
      if (target === "journal") await writeFile(f.config.state_file, "changed");
      else if (owner.owner_id === "queue") await save(f.queuePath, { ...owner, owner_id: "other" });
      return dead;
    }), /SOURCE_CHANGED/u);
    assert.equal(JSON.parse(await readFile(f.lockPath)).owner_id, "owner");
  });
}

for (const kind of ["stale", "active", "disconnected", "changed"]) {
  test(`${kind} probe refuses recovery`, async (t) => {
    const f = await fixture(t);
    if (kind === "stale") f.probe.probed_at = new Date(Date.now() - 3600000).toISOString();
    if (kind === "active") f.probe.native_state.database.active_or_pending_count = 1;
    if (kind === "disconnected") f.probe.app.cdp.ready = false;
    await f.updateProbe();
    if (kind === "changed") await writeFile(f.probePath, "changed");
    await assert.rejects(f.run(), /PROBE_STALE|IDLE_PROBE_REQUIRED|CDP_NOT_READY|PROBE_CHANGED/u);
    assert.equal(JSON.parse(await readFile(f.lockPath)).owner_id, "owner");
  });
}

test("journal symlink cannot redirect recovery outside the unit", async (t) => {
  const f = await fixture(t);
  const target = join(f.root, "original.json");
  await writeFile(target, await readFile(f.config.state_file));
  await rm(f.config.state_file);
  await symlink(target, f.config.state_file);
  await assert.rejects(f.run(), /SYMLINK_REJECTED/u);
});
