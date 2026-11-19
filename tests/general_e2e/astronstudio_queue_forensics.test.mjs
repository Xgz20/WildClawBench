import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFile, spawn } from "node:child_process";
import { appendFile, mkdir, mkdtemp, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as wait } from "node:timers/promises";
import test from "node:test";
import { promisify } from "node:util";
import { createNativeLogSpool } from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-log-spool.mjs";
import { startNativeLogSpool } from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-log-supervisor.mjs";
import { assertLiveArchiveAllowed } from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/archive_astronstudio_trace.mjs";
import { calculateRunConfigDigest } from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/probe_astronstudio_macos.mjs";

test("rotation preserves the incident, its original bytes, three tasks and matching external records", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-log-spool-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const log = join(root, "server.log");
  const output = join(root, "spool");
  const queueState = join(root, "queue-state.json");
  const journal = join(root, "framework.jsonl");
  let now = Date.parse("2026-11-19T04:20:00.000Z");
  const at = () => new Date(now).toISOString();
  const active_task_ids = ["task1", "task2", "task3"];
  const tasks = active_task_ids.map(task_id => ({ task_id, phase: "RUNNING", selected_attempt_id: "a-" + task_id,
    session: { thread_id: "thread-" + task_id, turn_id: "turn-" + task_id } }));
  const identity = { queue_id: "queue" };
  await writeFile(queueState, JSON.stringify({ identity, active_task_ids, tasks }));
  await writeFile(log, "before\n");
  const options = { queueState, journal, bootId: "boot", afterMs: 1_000, segmentLimit: 2 };
  let sample = await createNativeLogSpool(root, output, () => now, options);
  await sample();
  await appendFile(log, "server.shutdown.stage.");
  now += 100;
  await sample();
  await appendFile(log, "started pid=123\n");
  await rename(log, log + ".1");
  await writeFile(log, "new process\n");
  now += 100;
  await writeFile(journal, JSON.stringify({ at: at(), event: "process.signal.intent", queue_identity: identity }) + "\n");
  const index = await sample();
  assert.ok(index.recent_incident_at);
  await mkdir(join(output, "external"));
  await writeFile(join(output, "external", "endpoint-security.jsonl"), [
    { at: at(), event: "signal", boot_id: "boot", source_pid: 234, target_pid: 123, signal: 9 },
    { at: at(), event: "signal", boot_id: "another-boot", source_pid: 345, target_pid: 123, signal: 9 },
  ].map(row => JSON.stringify(row)).join("\n"));
  // Recreate the sampler with an incident still open, then seal the same incident.
  assert.ok(index.evicted_segments > 0);
  sample = await createNativeLogSpool(root, output, () => now, options);
  await appendFile(log, "post-fault context\n");
  now += 500;
  await sample();
  now += 600;
  await sample();
  const incidentRoot = join(output, "incidents");
  const [name] = await readdir(incidentRoot);
  assert.match(name, /^incident-/);
  const bytes = await readFile(join(incidentRoot, name, "incident.json"));
  const record = JSON.parse(bytes);
  assert.deepEqual(record.active_at_trigger.map(row => row.turn_id), tasks.map(row => row.session.turn_id));
  assert.equal(record.triggers[0].pid, 123);
  assert.equal(record.triggers[0].offset, 7);
  assert.equal(record.endpoint_security.rows[0].source_pid, 234);
  assert.equal(record.endpoint_security.rows.length, 1);
  assert.equal(record.framework_events.rows[0].event, "process.signal.intent");
  assert.equal(record.window_closed_early, false);
  assert.deepEqual(await Promise.all(record.raw_segments.map(async segment => {
    const raw = await readFile(join(incidentRoot, name, "raw", segment.name));
    assert.equal(createHash("sha256").update(raw).digest("hex"), segment.sha256);
    return raw.toString();
  })), ["before\n", "server.shutdown.stage.", "started pid=123\n", "new process\n", "post-fault context\n"]);
  const integrity = JSON.parse(await readFile(join(incidentRoot, name, "integrity.json")));
  assert.equal(integrity.incident_json_sha256, createHash("sha256").update(bytes).digest("hex"));
});

test("unread burst bytes wait at the cursor and rotation beyond retention reports exact offsets", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-log-spool-burst-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const log = join(root, "server.log");
  await writeFile(log, "");
  const sample = await createNativeLogSpool(root, join(root, "spool"));
  await sample();
  const mib = 1024 * 1024;
  const burst = Buffer.alloc(364 * 1024 + 2 * mib, "a");
  await appendFile(log, burst);
  assert.equal((await sample()).retained_bytes, mib);
  await rename(log, log + ".1");
  await writeFile(log, "new");
  assert.equal((await sample()).retained_bytes, 2 * mib + 3);
  assert.equal((await sample()).retained_bytes, burst.length + 3);
  await appendFile(log, Buffer.alloc(2 * mib, "b"));
  await sample();
  await rm(log);
  await writeFile(log, "replacement");
  const index = await sample();
  const gap = index.gaps.find(row => row.reason === "rotated_before_drain");
  assert.equal(gap.from, mib + 3);
  assert.equal(gap.to, 2 * mib + 3);
});

test("overlapping post-windows distinguish two backend generations", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-collector-generations-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const output = join(root, "spool");
  let now = Date.parse("2026-11-19T04:20:00.000Z");
  let pid = 100;
  const sample = await createNativeLogSpool(root, output, () => now, {
    appPath: "/fixture",
    bootId: "boot",
    sampleHost: async () => ({ at: new Date(now).toISOString(), monotonic_ns: String(now),
      observations_unavailable: [], processes: [{ pid, started_at: String(pid), role: "astudio-backend" }] }),
  });
  await sample();
  now += 5_000;
  pid++;
  await sample();
  now += 5_000;
  pid++;
  await sample();
  now += 75_000;
  await sample();
  const incidents = join(output, "incidents");
  const files = await readdir(incidents);
  const records = await Promise.all(files.map(async name => JSON.parse(await readFile(join(incidents, name, "incident.json")))));
  assert.equal(records.length, 2);
  assert.deepEqual(records.map(row => row.triggers[0].pid).sort(), [100, 101]);
  assert.ok(records.every(row => row.triggers.length === 1));
  assert.deepEqual(records.map(row => row.host_samples.length).sort(), [3, 4]);
});

test("a failed raw write leaves offsets retryable after collector restart", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-log-write-fail-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const log = join(root, "server.log");
  const output = join(root, "spool");
  await writeFile(log, "abc");
  let sample = await createNativeLogSpool(root, output, Date.now, {
    writeRaw: async () => { throw Object.assign(new Error("disk full"), { code: "ENOSPC" }); },
  });
  const failed = await sample();
  assert.equal(Object.values(failed.cursors)[0].offset, 0);
  assert.deepEqual(failed.gaps.filter(row => row.reason === "raw_write_failed").map(row => [row.from, row.to, row.error]), [[0, 3, "ENOSPC"]]);
  sample = await createNativeLogSpool(root, output);
  const recovered = await sample();
  assert.equal(Object.values(recovered.cursors)[0].offset, 3);
  assert.equal(await readFile(join(output, recovered.segments[0].name), "utf8"), "abc");
});

test("the log worker drains and exits before a standalone owner with top-level await exits", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-log-worker-stop-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const logs = join(root, "logs");
  const output = join(root, "spool");
  const script = join(root, "owner.mjs");
  const spoolModule = new URL("../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-log-supervisor.mjs", import.meta.url);
  await mkdir(logs);
  await writeFile(join(logs, "server.log"), "before\n");
  await writeFile(script, `
    import { appendFile } from "node:fs/promises";
    import { startNativeLogSpool } from ${JSON.stringify(spoolModule.href)};
    const spool = await startNativeLogSpool(${JSON.stringify(join(root, "state.sqlite"))}, ${JSON.stringify(output)});
    await appendFile(${JSON.stringify(join(logs, "server.log"))}, "last event\\n");
    process.exitCode = await spool.stop();
  `);
  await promisify(execFile)(process.execPath, [script], { timeout: 15_000 });
  const index = JSON.parse(await readFile(join(output, "index.json"), "utf8"));
  const last = index.segments.at(-1);
  assert.equal(await readFile(join(output, last.name), "utf8"), "last event\n");
});

test("the detached collector records a shutdown after the queue Worker dies, then reattaches", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-collector-worker-loss-"));
  const logs = join(root, "logs");
  const output = join(root, "spool");
  const database = join(root, "state.sqlite");
  const script = join(root, "owner.mjs");
  const spoolModule = new URL("../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-log-supervisor.mjs", import.meta.url);
  const status = async () => JSON.parse(await readFile(join(output, "status.json"), "utf8"));
  await mkdir(logs);
  await writeFile(join(logs, "server.log"), "before\n");
  await writeFile(script, `
    import { startNativeLogSpool } from ${JSON.stringify(spoolModule.href)};
    await startNativeLogSpool(${JSON.stringify(database)}, ${JSON.stringify(output)});
    console.log("ready");
    setInterval(() => {}, 1000);
  `);
  const owner = spawn(process.execPath, [script]);
  t.after(async () => {
    if (owner.exitCode === null && owner.signalCode === null) owner.kill();
    const live = await status().catch(() => null);
    if (live && !["STOPPED", "ERROR"].includes(live.phase)) {
      const cleanup = await startNativeLogSpool(database, output);
      await cleanup.stop();
    }
    await rm(root, { recursive: true, force: true });
  });
  await new Promise((ready, reject) => {
    owner.stdout.once("data", ready);
    owner.once("error", reject);
    owner.once("exit", () => reject(Error("fixture owner exited before ready")));
  });
  const before = await status();
  owner.kill("SIGKILL");
  await new Promise(ready => owner.once("exit", ready));
  await appendFile(join(logs, "server.log"), "APP SESSION END pid=123 signal=SIGKILL\n");
  for (let i = 0; i < 50 && (await status()).phase !== "DRAINING"; i++) await wait(100);
  assert.equal((await status()).phase, "DRAINING");
  const spool = await startNativeLogSpool(database, output);
  assert.equal((await status()).instance_id, before.instance_id);
  process.kill(before.pid, "SIGKILL");
  await appendFile(join(logs, "server.log"), "after collector restart\n");
  for (let i = 0; i < 50; i++) {
    try { process.kill(before.pid, 0); await wait(100); } catch (error) {
      if (error.code !== "ESRCH") throw error;
      break;
    }
  }
  assert.equal(await spool.ensure(), true);
  assert.notEqual((await status()).instance_id, before.instance_id);
  await spool.stop();
  const result = JSON.parse(await readFile(join(output, "index.json"), "utf8"));
  assert.ok(result.gaps.some(row => row.reason === "queue_worker_exited"));
  assert.ok(result.gaps.some(row => row.reason === "queue_worker_changed"));
  assert.ok(result.recent_incident_at);
  assert.ok(result.gaps.some(row => row.reason === "collector_restarted"));
  assert.deepEqual(result.segments.map(row => row.offset), [0, 7, 7 + Buffer.byteLength("APP SESSION END pid=123 signal=SIGKILL\n")]);
});

test("online archive is refused during execution and when a foreign native session is active", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-log-idle-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const control = join(root, ".general-e2e");
  const target = join(control, "execution", "task");
  const file = join(target, "automation-state.json");
  const configPath = join(root, "config.json");
  const database = join(root, "state.sqlite");
  await mkdir(target, { recursive: true });
  await writeFile(database, "");
  const payload = {
    schema_version: "wildclawbench.general-e2e-astronstudio-run-config/v1",
    state_database: { path: database },
  };
  const configDigest = calculateRunConfigDigest(payload);
  await writeFile(configPath, JSON.stringify({
    ...payload, config_digest: configDigest, config_digest_algorithm: "sha256-canonical-json/v1",
  }));
  const state = { phase: "RUNNING", identity: { task_id: "task" },
    run_config: { path: configPath, config_digest: configDigest } };
  await writeFile(file, JSON.stringify(state));
  const input = { stateFile: file, state, stateDatabase: database };
  await assert.rejects(assertLiveArchiveAllowed(input), /ASTUDIO_COLLECT_EXECUTION_ACTIVE/);
  state.phase = "COMPLETED";
  await writeFile(file, JSON.stringify(state));
  const snapshot = { sessions: [], orphan_sessions: [], pending_interactions: [], orphan_turns: [] };
  await assert.rejects(assertLiveArchiveAllowed(input, {
    querySafety: async () => ({ ...snapshot, sessions: [{ status: "running", active_turn_id: "foreign" }] }),
  }), /ASTUDIO_COLLECT_NATIVE_ACTIVITY/);
  await assertLiveArchiveAllowed(input, { querySafety: async () => snapshot });
  const journal = await readFile(join(control, "diagnostics", "framework-events.jsonl"), "utf8");
  assert.match(journal, /archive.native-idle-verified/);
});
