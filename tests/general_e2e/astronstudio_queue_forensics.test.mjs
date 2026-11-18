import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { appendFile, mkdir, mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { createNativeLogSpool } from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-log-spool.mjs";
import { assertLiveArchiveAllowed } from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/archive_astronstudio_trace.mjs";
import { calculateRunConfigDigest } from "../../tools/report/skills/general-e2e/execute-general-e2e/scripts/probe_astronstudio_macos.mjs";

test("native log spool follows the previous inode through rotation and pins the incident", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-log-spool-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const log = join(root, "server.log");
  const output = join(root, "spool");
  await writeFile(log, "before\n");
  const sample = await createNativeLogSpool(root, output);
  await sample();
  await appendFile(log, "server.shutdown.stage.started\n");
  await rename(log, log + ".1");
  await writeFile(log, "new process\n");
  const index = await sample();
  assert.ok(index.recent_incident_at);
  assert.equal(index.segments.length, 3);
  assert.ok(index.segments.every(segment => segment.pinned));
  assert.deepEqual(await Promise.all(index.segments.map(segment => readFile(join(output, segment.name), "utf8"))),
    ["before\n", "server.shutdown.stage.started\n", "new process\n"]);
});

test("native log spool retains a 364 KiB burst and reports bytes lost beyond its sample limit", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-log-spool-burst-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const log = join(root, "server.log");
  await writeFile(log, "");
  const sample = await createNativeLogSpool(root, join(root, "spool"));
  await sample();
  const burst = Buffer.alloc(364 * 1024, "a");
  await appendFile(log, burst);
  const complete = await sample();
  assert.equal(complete.retained_bytes, burst.length);
  assert.ok(!complete.gaps.some(gap => gap.reason === "sample_byte_limit"));
  await appendFile(log, Buffer.alloc(2 * 1024 * 1024, "b"));
  const capped = await sample();
  const gap = capped.gaps.find(row => row.reason === "sample_byte_limit");
  assert.equal(gap.to - gap.from, 1024 * 1024);
  assert.equal(capped.retained_bytes, burst.length + 1024 * 1024);
  assert.equal(capped.retained_byte_limit, 64 * 1024 * 1024);
});

test("the log worker drains and exits before a standalone owner with top-level await exits", async t => {
  const root = await mkdtemp(join(tmpdir(), "astudio-log-worker-stop-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const logs = join(root, "logs");
  const output = join(root, "spool");
  const script = join(root, "owner.mjs");
  const spoolModule = new URL("../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-log-spool.mjs", import.meta.url);
  await mkdir(logs);
  await writeFile(join(logs, "server.log"), "before\n");
  await writeFile(script, `
    import { appendFile } from "node:fs/promises";
    import { startNativeLogSpool } from ${JSON.stringify(spoolModule.href)};
    const stop = await startNativeLogSpool(${JSON.stringify(join(root, "state.sqlite"))}, ${JSON.stringify(output)});
    await appendFile(${JSON.stringify(join(logs, "server.log"))}, "last event\\n");
    process.exitCode = await stop();
  `);
  await promisify(execFile)(process.execPath, [script], { timeout: 15_000 });
  const index = JSON.parse(await readFile(join(output, "index.json"), "utf8"));
  const last = index.segments.at(-1);
  assert.equal(await readFile(join(output, last.name), "utf8"), "last event\n");
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
