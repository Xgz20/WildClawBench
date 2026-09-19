import assert from "node:assert/strict";
import { readFile, rm, symlink, writeFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { finalizeGeneralExecution, verifyGeneralCollection } from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/finalize_general_execution.mjs";
import { queryTrace } from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/query_trace.mjs";
import { digest, fixture, fixtureHook, writeJson } from "./helpers/general-collection-fixture.mjs";

test("General collection freezes multiple raw files and preserves native null IDs", async () => {
  for (const harness of ["workbuddy", "qwenwork"]) {
    const value = await fixture({ harness });
    try {
      const result = await finalizeGeneralExecution(value.options, { processCleanup: fixtureHook(harness) });
      assert.equal(result.status, "PASS");
      assert.equal(result.receipt_status, "completed");
      const record = JSON.parse(await readFile(join(result.evidence_root, "execution-record.json")));
      assert.equal(record.session.thread_id, null);
      assert.equal(record.session.turn_id, harness === "workbuddy" ? "request-one" : null);
      assert.equal(record.harness.id, harness);
      for (const path of ["raw/part-one.jsonl", "raw/part-two.jsonl", "bindings/session.json"]) {
        assert.deepEqual(await readFile(join(result.evidence_root, "trace", path)), await readFile(join(value.traceRoot, path)));
      }
      assert.equal((await verifyGeneralCollection({ unitRoot: value.root, taskId: value.taskId })).status, "PASS");
      const query = await queryTrace({ traceIndex: join(result.evidence_root, "trace/trace-index.json"), page: 1, pageSize: 10 });
      assert.equal(query.status, "PASS");
    } finally { await rm(value.root, { recursive: true, force: true }); }
  }
});

test("General collection rejects untrusted provenance and mismatched native scope before cleanup", async () => {
  for (const mutation of ["duplicate", "escape", "symlink", "binding", "session", "metric", "metric-duplicate", "range", "call", "uncertain"]) {
    const value = await fixture();
    let called = false;
    try {
      if (mutation === "duplicate") value.index.raw_trace.push(value.index.raw_trace[0]);
      if (mutation === "escape") value.index.raw_trace[0].path = "raw/../../outside";
      if (mutation === "symlink") {
        const source = join(value.traceRoot, "raw/part-one.jsonl");
        await rm(source);
        await symlink(join(value.traceRoot, "raw/part-two.jsonl"), source);
      }
      if (mutation === "binding") {
        const data = Buffer.from('{"foreign":"binding"}\n');
        await writeFile(join(value.traceRoot, "bindings/session.json"), data);
        Object.assign(value.index.binding_evidence[0], { sha256: digest(data), size: data.length });
      }
      if (mutation === "session") value.index.session.session_id = "foreign";
      if (mutation === "call") value.index.calls[0].call_id = "foreign";
      if (mutation === "range") {
        const path = join(value.traceRoot, "transcript.jsonl");
        const data = Buffer.from((await readFile(path, "utf8")).replace("part-one.jsonl#L1", "part-one.jsonl#L999"));
        await writeFile(path, data);
        Object.assign(value.index.transcript, { sha256: digest(data), size: data.length });
      }
      if (mutation === "uncertain") {
        value.state.phase = "FAILED";
        value.state.execution.business_status = "infrastructure_error";
        value.state.prompt.send_status = "uncertain";
        await writeJson(value.statePath, value.state);
      }
      await writeJson(value.indexPath, value.index);
      await value.updateResourceSources();
      if (mutation === "metric") value.metrics.collection.sources[2].path = "trace/raw/foreign.jsonl";
      if (mutation === "metric-duplicate") value.metrics.collection.sources.push(value.metrics.collection.sources[0]);
      await writeJson(value.resourcePath, value.metrics);
      await assert.rejects(finalizeGeneralExecution(value.options, {
        processCleanup: { ...fixtureHook(), run: async () => { called = true; return { success: true }; } },
      }), /COLLECTION_VALIDATION_FAILED/u, mutation);
      assert.equal(called, false, mutation);
      await assert.rejects(readFile(join(value.root, "receipts/collect-evidence-receipt.json")), /ENOENT/u);
    } finally { await rm(value.root, { recursive: true, force: true }); }
  }
});

test("General collection requires a supported cleanup hook and real quiet-window evidence", async () => {
  for (const mutation of ["missing", "boolean-only", "unsupported", "platform", "workspace", "residual", "quiet", "fabricated-duration"]) {
    const value = await fixture();
    try {
      let hook = fixtureHook();
      if (mutation === "missing") hook = null;
      else if (mutation === "boolean-only") hook.run = async () => ({ supported: true, success: true });
      else if (mutation === "platform") hook.platform = "win32";
      else hook = fixtureHook("qwenwork", (result) => {
        if (mutation === "unsupported") result.supported = false;
        if (mutation === "workspace") result.after.workspace = value.root;
        if (mutation === "residual") result.after.targets = [{ pid: 1 }];
        if (mutation === "quiet") result.quiet_observed_milliseconds = 0;
        if (mutation === "fabricated-duration") result.quiet_observed_milliseconds = 60_000;
      });
      await assert.rejects(finalizeGeneralExecution(value.options, { processCleanup: hook }), /TASK_PROCESS_CLEANUP/u, mutation);
      await assert.rejects(readFile(join(value.root, "receipts/collect-evidence-receipt.json")), /ENOENT/u);
    } finally { await rm(value.root, { recursive: true, force: true }); }
  }
});

test("General verifier detects raw artifact drift after collection", async () => {
  const value = await fixture();
  try {
    const result = await finalizeGeneralExecution(value.options, { processCleanup: fixtureHook() });
    await writeFile(join(result.evidence_root, "trace/raw/part-two.jsonl"), "tampered\n");
    await assert.rejects(verifyGeneralCollection({ unitRoot: value.root, taskId: value.taskId }), /EVIDENCE_MANIFEST_SCOPE_MISMATCH/u);
  } finally { await rm(value.root, { recursive: true, force: true }); }
});

test("General collection rejects state revival during cleanup before publication", async () => {
  const value = await fixture();
  try {
    const hook = fixtureHook();
    const run = hook.run;
    hook.run = async (workspace, options) => {
      const cleanup = await run(workspace, options);
      value.state.phase = "RUNNING";
      value.state.execution.finished_at = null;
      await writeJson(value.statePath, value.state);
      return cleanup;
    };
    await assert.rejects(finalizeGeneralExecution(value.options, { processCleanup: hook }), /COLLECTION_INPUT_CHANGED/u);
    await assert.rejects(readFile(join(value.root, "receipts/collect-evidence-receipt.json")), /ENOENT/u);
    await assert.rejects(readFile(join(value.root, "evidence/tasks/task-one/attempt-one/execution-record.json")), /ENOENT/u);
  } finally { await rm(value.root, { recursive: true, force: true }); }
});
