import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import { fixture } from "./helpers/doubaowork-collection-fixture.mjs";
import { trajectoryArchiveClockPolicy, verifyEquivalentWebTerminal } from "../../tools/report/e2e-shared/doubaowork/bound-evidence.mjs";
import { DISPATCHER_PROFILE, DISPATCHER_SOURCE_SHA256 } from "../../tools/report/e2e-shared/doubaowork/runtime-dispatcher.mjs";

if (!vm.SourceTextModule) {
  test("bound evidence contracts run in an isolated native-discovery fixture", async () => {
    await promisify(execFile)(process.execPath, ["--experimental-vm-modules", "--test", fileURLToPath(import.meta.url)]);
  });
} else {
  test("archive timing bounds require the legacy emitter; modern and unknown clocks never inherit them", () => {
    assert.equal(trajectoryArchiveClockPolicy({ profile: "doubaowork-local-tool-debug-sink/v1",
      profile_sha256: "f765c160a6d8661b95cddbbbee9bed1ab90902e910259c5c241ae4cd7df78e75" }).use_observation_bounds, true);
    assert.equal(trajectoryArchiveClockPolicy({ profile: DISPATCHER_PROFILE,
      profile_sha256: DISPATCHER_SOURCE_SHA256 }).use_observation_bounds, false);
    for (const value of [null, { profile: DISPATCHER_PROFILE, profile_sha256: "a".repeat(64) },
      { profile: "unknown", profile_sha256: DISPATCHER_SOURCE_SHA256 }]) {
      assert.throws(() => trajectoryArchiveClockPolicy(value), /ARCHIVE_CLOCK_PROFILE_UNVERIFIED/);
    }
  });

  test("both scenes retain modern archives without inheriting cross-source clock bounds; General coverage stays partial", async t => {
    for (const scene of ["general", "web"]) {
    const f = await fixture(t);
    f.journal.scene = scene;
    const file = `0000-${f.source.sha256}.jsonl`;
    await f.writeArtifact(join(f.control, "trajectory-observations", file), f.trajectoryBytes);
    await f.writeArtifact(join(f.control, "trajectory-observations", "index.json"), {
      schema: "wildclawbench.doubaowork-trajectory-observations/v1",
      identity: { attempt_id: f.journal.attempt_id, conversation_id: f.journal.session.conversation_id, workspace: f.workspace },
      clock: "same-host-wall-clock-observation-upper-bound", snapshots: [{ file, sha256: f.source.sha256,
        size: f.trajectoryBytes.length, native_source: f.trajectoryPath, captured_at: new Date(2000).toISOString() }],
    });
    const bound = await f.readBound();
    assert.equal(bound.snapshots[0].captured_at, null);
    assert.equal(bound.snapshots[0].clock_policy, "verified-dispatcher-native-order-only/v1");
    assert.equal(bound.archiveRaw.length, 2);
    if (scene === "web") continue;
    await f.collect();
    const index = JSON.parse(await readFile(join(f.outputRoot, "trace-index.json")));
    assert.equal(index.completeness.status, "partial");
    assert.ok(index.completeness.missing.includes("native-tool-trajectory-incomplete"));
    }
  });

  test("General rejects a Web equivalent terminal even with otherwise bound native input", async t => {
    const f = await fixture(t);
    f.journal.native_observation.equivalent_web_binding = true;
    f.journal.native_observation.equivalent_finished_at = new Date(2000).toISOString();
    await assert.rejects(f.readBound(), /EQUIVALENT_TERMINAL_SCENE_MISMATCH/);
  });

  test("Web equivalent terminal requires its actual observation time and cannot promote failure", () => {
    const journal = { scene: "web", timing: { sent_at: new Date(1000).toISOString() },
      native_observation: { equivalent_web_binding: true, equivalent_finished_at: new Date(2000).toISOString() } };
    const runtime = { observed_at: new Date(3000).toISOString() };
    assert.equal(verifyEquivalentWebTerminal(journal, runtime, { terminal: "completed" }), journal.native_observation.equivalent_finished_at);
    for (const finish of [null, "invalid", new Date(500).toISOString(), new Date(4000).toISOString()]) {
      assert.throws(() => verifyEquivalentWebTerminal({ ...journal, native_observation: { ...journal.native_observation, equivalent_finished_at: finish } }, runtime, { terminal: "completed" }), /TIME_OR_STATUS_INVALID/);
    }
    for (const terminal of ["failed", "interrupted"]) assert.throws(() => verifyEquivalentWebTerminal(journal, runtime, { terminal }), /TIME_OR_STATUS_INVALID/);
  });

  test("modern tool subset keeps an explicit missing reason, original profile and unknown total", async t => {
    const f = await fixture(t);
    await f.collect();
    const index = JSON.parse(await readFile(join(f.outputRoot, "trace-index.json")));
    const state = JSON.parse(await readFile(join(f.outputRoot, "execution-state.json")));
    const resource = JSON.parse(await readFile(join(f.outputRoot, "resource-metrics.json")));
    const transcript = (await readFile(join(f.outputRoot, "transcript.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
    assert.equal(index.completeness.status, "partial");
    assert.ok(index.completeness.missing.includes("native-tool-trajectory-incomplete"));
    assert.ok(index.normalization.compatibility_profiles.includes(f.snapshot.profile));
    assert.equal(transcript.find(e => e.type === "tool_call").native.source_profile, f.snapshot.profile);
    assert.equal(resource.metrics.tools.call_count.value, null);
    assert.equal(resource.collection.known_subtotals.call_count, 1);
    assert.ok(f.project(index, state, resource).evidence.missing.includes("native-tool-trajectory-incomplete"));
    const corruptIndex = structuredClone(index); corruptIndex.completeness.missing = [];
    assert.ok(f.project(corruptIndex, state, resource).evidence.missing.includes("trace_completeness"));
  });

  test("retained complete legacy subset records capture loss without changing native success", async t => {
    const f = await fixture(t);
    f.snapshot.profile = "doubaowork-local-tool-debug-sink/v1";
    f.snapshot.overflow = true;
    f.journal.native_observation.native_tools_artifact = await f.writeArtifact(join(f.control, "tools.json"), f.snapshot);
    await f.collect();
    const index = JSON.parse(await readFile(join(f.outputRoot, "trace-index.json")));
    const state = JSON.parse(await readFile(join(f.outputRoot, "execution-state.json")));
    assert.ok(index.completeness.missing.includes("native-tool-capture-incomplete"));
    assert.equal(state.execution.business_status, "completed");
  });
}
