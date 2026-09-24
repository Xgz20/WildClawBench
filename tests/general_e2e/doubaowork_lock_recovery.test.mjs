import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, writeFile, readFile, realpath, rm, symlink } from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import { inspectRecoveryOwner, recoverStaleAttemptLock } from "../../tools/report/e2e-shared/doubaowork/lock-recovery.mjs";

const START = "Thu Sep 24 08:00:00 2026";
async function fixture(t) {
  const root = await realpath(await mkdtemp(join(tmpdir(), "doubao-recovery-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const attemptRoot = join(root, "attempt"), uiRoot = join(root, "ui"), file = join(root, "journal.json");
  await mkdir(attemptRoot); await mkdir(uiRoot); await writeFile(file, '{"original":true}\n');
  const owner = { schema: "wildclawbench.doubaowork-worker-lock/v1", host: hostname(), pid: 999999,
    process_start_identity: START, instance_id: "attempt-owner", acquired_at: "2026-09-24T00:00:00Z" };
  const attemptLock = join(attemptRoot, ".doubaowork-driver.lock"), uiLock = join(uiRoot, ".doubaowork-driver.lock");
  await writeFile(attemptLock, JSON.stringify(owner)); await writeFile(uiLock, JSON.stringify({ ...owner, instance_id: "ui-owner" }));
  const inspectOwner = record => inspectRecoveryOwner(record, { selfPid: 42, processTable: `42 ${START}\n` });
  const options = { attemptRoot, uiRoot, expectedOwnerId: owner.instance_id, protectedFiles: [file], verifyIdle: async () => ({ verified: true }) };
  return { root, options, attemptLock, uiLock, file, owner, inspectOwner };
}

test("Recovery distinguishes exited/reused owners from live, foreign and unverifiable owners", async () => {
  const owner = { host: hostname(), pid: 7, process_start_identity: START };
  const opt = { selfPid: 42, processTable: `42 ${START}\n` };
  assert.equal((await inspectRecoveryOwner(owner, opt)).reason, "owner-exited");
  assert.equal((await inspectRecoveryOwner(owner, { ...opt, processTable: `${opt.processTable}7 Thu Sep 24 09:00:00 2026\n` })).reason, "pid-reused");
  await assert.rejects(inspectRecoveryOwner(owner, { ...opt, processTable: `${opt.processTable}7 ${START}\n` }), /OWNER_ACTIVE/);
  await assert.rejects(inspectRecoveryOwner({ ...owner, host: "elsewhere" }, opt), /FOREIGN_HOST/);
  await assert.rejects(inspectRecoveryOwner(owner, { ...opt, processTable: "" }), /TABLE_INCOMPLETE/);
  await assert.rejects(inspectRecoveryOwner(owner, { ...opt, processTable: "malformed" }), /IDENTITY_UNKNOWN/);
});

test("Recovery archives exact stale lock bytes and leaves the original journal unchanged", async t => {
  const f = await fixture(t), before = await readFile(f.file), lock = await readFile(f.attemptLock), ui = await readFile(f.uiLock);
  const result = await recoverStaleAttemptLock(f.options, { inspectOwner: f.inspectOwner });
  assert.equal(result.status, "RECOVERED"); assert.equal(result.prompt_sent, 0); assert.equal(result.archives.length, 2);
  assert.deepEqual(await readFile(result.archives[0].path), ui); assert.deepEqual(await readFile(result.archives[1].path), lock);
  assert.deepEqual(await readFile(f.file), before);
  for (const path of [f.attemptLock, f.uiLock, join(f.options.uiRoot, ".recovery-guard")]) await assert.rejects(readFile(path), { code: "ENOENT" });
});

test("Recovery rejects wrong owner, unrelated UI owner, pending activity and existing archives", async t => {
  for (const kind of ["wrong-owner", "ui-owner", "not-idle", "archive"]) {
    const f = await fixture(t), before = await readFile(f.attemptLock);
    if (kind === "wrong-owner") f.options.expectedOwnerId = "other";
    if (kind === "ui-owner") await writeFile(f.uiLock, JSON.stringify({ ...f.owner, pid: 999998 }));
    if (kind === "not-idle") f.options.verifyIdle = async () => ({ verified: false });
    if (kind === "archive") await writeFile(`${f.uiLock}.stale-ui-owner.json`, "existing");
    await assert.rejects(recoverStaleAttemptLock(f.options, { inspectOwner: f.inspectOwner }), /DOUBAOWORK_RECOVERY_/);
    assert.deepEqual(await readFile(f.attemptLock), before);
  }
});

test("Journal drift on fresh recheck keeps the attempt lock blocking; symlinks never pass", async t => {
  const f = await fixture(t); let calls = 0;
  f.options.verifyIdle = async () => { if (++calls === 2) await writeFile(f.file, "changed"); return { verified: true }; };
  const before = await readFile(f.attemptLock);
  await assert.rejects(recoverStaleAttemptLock(f.options, { inspectOwner: f.inspectOwner }), /INPUT_CHANGED/);
  assert.deepEqual(await readFile(f.attemptLock), before);
  const g = await fixture(t); await symlink(g.file, join(g.root, "alias")); g.options.protectedFiles = [join(g.root, "alias")];
  await assert.rejects(recoverStaleAttemptLock(g.options, { inspectOwner: g.inspectOwner }), /PATH_UNSAFE/);
});

test("Concurrent recovery guard and owner revival cannot release a stale attempt", async t => {
  const f = await fixture(t), guard = join(f.options.uiRoot, ".recovery-guard");
  await writeFile(guard, "other recovery");
  await assert.rejects(recoverStaleAttemptLock(f.options, { inspectOwner: f.inspectOwner }), /ALREADY_ACTIVE/);
  assert.equal(await readFile(guard, "utf8"), "other recovery"); await rm(guard);
  let probes = 0; f.options.verifyIdle = async () => { probes++; return { verified: true }; };
  await assert.rejects(recoverStaleAttemptLock(f.options, { inspectOwner: async owner => {
    if (probes && owner.instance_id === "ui-owner") throw new Error("DOUBAOWORK_RECOVERY_OWNER_ACTIVE");
    return f.inspectOwner(owner);
  } }), /OWNER_ACTIVE/);
  assert.ok(await readFile(f.attemptLock)); assert.ok(await readFile(f.uiLock));
});

test("A failed observer cleanup keeps the original attempt lock blocking", async t => {
  const f = await fixture(t), before = await readFile(f.attemptLock);
  f.options.beforeRelease = async () => { throw new Error("UNSENT_OBSERVER_HAS_EVENTS"); };
  await assert.rejects(recoverStaleAttemptLock(f.options, { inspectOwner: f.inspectOwner }), /UNSENT_OBSERVER/);
  assert.deepEqual(await readFile(f.attemptLock), before);
});
