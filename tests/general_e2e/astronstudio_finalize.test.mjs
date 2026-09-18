import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { chmod, mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  finalizeAstronStudioExecution,
  parseArgs,
  verifyAstronStudioCollection,
} from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/finalize_astronstudio_execution.mjs";
import {
  parseDarwinProcessTable,
  selectDarwinTaskProcesses,
  terminateDarwinTaskProcesses,
} from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/lib/macos-task-processes.mjs";

const DATASET_DIGEST = "1".repeat(64);

function digest(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`);
}

function identity(taskId = "task-fixture", attemptId = "attempt-fixture") {
  return {
    batch_id: "batch-fixture",
    unit_id: "astronstudio-macos-x86-64",
    task_id: taskId,
    attempt_id: attemptId,
  };
}

function successfulCleanup() {
  return {
    schema_version: "wildclawbench.general-e2e-task-process-cleanup/v1",
    supported: true,
    platform: "darwin",
    success: true,
    quiet_window_milliseconds: 0,
    quiet_observed_milliseconds: 0,
    late_process_detected: false,
    before: { supported: true, targets: [], seed_pids: [], root_pids: [] },
    termination_attempts: [],
    after: { supported: true, targets: [], seed_pids: [], root_pids: [] },
  };
}

function metric(value, status = "observed") {
  return { value, status, basis: "fixture" };
}

async function fixture({
  businessStatus = "completed",
  traceStatus = "complete",
  includeTrace = true,
  includeResource = true,
  taskId = "task-fixture",
  attemptId = "attempt-fixture",
} = {}) {
  const root = await mkdtemp(join(tmpdir(), "general-e2e-finalize-fixture-"));
  const taskIdentity = identity(taskId, attemptId);
  const taskRoot = join(root, "execution", "tasks", taskId);
  const workspace = join(taskRoot, "workspace");
  const stateRoot = join(root, ".general-e2e", "execution", taskId);
  const traceRoot = join(root, "fixture-input", "trace");
  await mkdir(workspace, { recursive: true });
  await mkdir(stateRoot, { recursive: true });
  await mkdir(join(traceRoot, "raw"), { recursive: true });
  await mkdir(join(root, "receipts"), { recursive: true });
  await writeFile(join(workspace, "answer.txt"), "candidate\n");
  const prompt = Buffer.from("Do the task.\n", "utf8");
  const promptPath = join(taskRoot, "PROMPT.md");
  await writeFile(promptPath, prompt);
  const finalResponse = Buffer.from("Done.\n", "utf8");
  const finalResponseRelative = `.general-e2e/execution/${taskId}/final-response.md`;
  await writeFile(join(stateRoot, "final-response.md"), finalResponse);

  const manifest = {
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1",
    schema_version: 1,
    manifest_kind: "execution",
    batch_id: taskIdentity.batch_id,
    unit_id: taskIdentity.unit_id,
    dataset: { id: "general-custom60-v1", digest: DATASET_DIGEST },
    task_ids: [taskId],
    tasks: [{
      task_id: taskId,
      prompt: { path: `execution/tasks/${taskId}/PROMPT.md`, sent_sha256: digest(prompt) },
      workspace: { path: `execution/tasks/${taskId}/workspace` },
    }],
    unit: {
      harness: { id: "astronstudio", platform: "macos-x86-64", version: "3.3.1" },
      model: { requested_id: "GLM-5.2", reasoning_effort: "high" },
    },
  };
  await writeJson(join(root, "manifest.json"), manifest);

  const state = {
    schema_version: "wildclawbench.general-e2e-astronstudio-execution-state/v1",
    identity: taskIdentity,
    dataset: { id: "general-custom60-v1", digest: DATASET_DIGEST },
    phase: businessStatus === "completed" ? "COMPLETED" : "FAILED",
    task_root: taskRoot,
    candidate_workspace: workspace,
    prompt: {
      path: promptPath,
      sha256: digest(prompt),
      send_status: "sent",
      sent_at: "2026-09-18T00:00:01.000Z",
    },
    send: { dispatch_attempt_count: 1 },
    session: {
      thread_id: "thread-fixture",
      turn_id: "turn-fixture",
      session_id: "session-fixture",
      cwd: workspace,
      verified: true,
      native_status: businessStatus === "completed" ? "completed" : "stopped",
    },
    client: { version: "3.3.1", model: "GLM-5.2", reasoning: "High" },
    execution: {
      business_status: businessStatus,
      started_at: "2026-09-18T00:00:00.000Z",
      finished_at: "2026-09-18T00:00:10.000Z",
      duration_seconds: 10,
      agent_duration_seconds: null,
      error: businessStatus === "completed" ? null : `${businessStatus} fixture`,
    },
    evidence: {
      final_response_path: finalResponseRelative,
      final_response_sha256: digest(finalResponse),
    },
    human_assistance: { mode: "automatic", operation_count: 0, semantic_intervention_count: 0 },
  };
  if (["timeout", "cancelled"].includes(businessStatus)) {
    state.timeout = { cancellation_confirmed: true };
  }
  const statePath = join(stateRoot, "automation-state.json");
  await writeJson(statePath, state);
  await writeJson(join(stateRoot, "execution-record.json"), { provisional: true });

  let indexPath = "";
  let metricsPath = "";
  if (includeTrace) {
    const transcript = Buffer.from('{"event":"fixture"}\n', "utf8");
    const raw = Buffer.from('{"raw":"fixture"}\n', "utf8");
    await writeFile(join(traceRoot, "transcript.jsonl"), transcript);
    await writeFile(join(traceRoot, "raw", "astronstudio-provider-events.jsonl"), raw);
    const index = {
      schema_id: "urn:wildclawbench:schema:general-e2e:trace-index:v1",
      schema_version: 1,
      identity: taskIdentity,
      session: {
        thread_id: state.session.thread_id,
        turn_id: state.session.turn_id,
        session_id: state.session.session_id,
        cwd: workspace,
      },
      transcript: { path: "transcript.jsonl", sha256: digest(transcript), size: transcript.length },
      raw_trace: [{ path: "raw/astronstudio-provider-events.jsonl", sha256: digest(raw), size: raw.length }],
      completeness: {
        status: traceStatus,
        omitted_event_count: traceStatus === "complete" ? 0 : 1,
        missing: traceStatus === "complete" ? [] : ["turn.completed"],
      },
    };
    indexPath = join(traceRoot, "trace-index.json");
    await writeJson(indexPath, index);
    if (includeResource) {
      const stateBytes = await readFile(statePath);
      const indexBytes = await readFile(indexPath);
      const metrics = {
        schema_id: "urn:wildclawbench:schema:general-e2e:resource-metrics:v1",
        schema_version: 1,
        identity: taskIdentity,
        collection: {
          status: traceStatus === "complete" ? "complete" : "partial",
          sources: [
            { path: "execution/automation-state.json", sha256: digest(stateBytes), size: stateBytes.length },
            { path: "trace/trace-index.json", sha256: digest(indexBytes), size: indexBytes.length },
            { path: "trace/raw/astronstudio-provider-events.jsonl", sha256: digest(raw), size: raw.length },
          ],
        },
        metrics: {
          usage: {
            input_tokens: metric(10), output_tokens: metric(2), total_tokens: metric(12),
            cache_read_input_tokens: metric(5), cache_creation_input_tokens: metric(null, "unavailable"),
            reasoning_output_tokens: metric(1),
          },
          requests: { request_count: metric(1, "inferred"), request_attempt_count: metric(null, "unavailable") },
          tools: { call_count: metric(0) },
          timing: { duration_seconds: metric(10), agent_duration_seconds: metric(4) },
        },
      };
      metricsPath = join(root, "fixture-input", "resource-metrics.json");
      await writeJson(metricsPath, metrics);
    }
  }
  return { root, taskId, attemptId, workspace, statePath, indexPath, metricsPath };
}

function options(value) {
  return {
    unitRoot: value.root,
    stateFile: value.statePath,
    traceIndex: value.indexPath,
    resourceMetrics: value.metricsPath,
    candidatePolicy: "",
    stabilityMilliseconds: 0,
    processQuietMilliseconds: 0,
    processWaitMilliseconds: 0,
  };
}

test("CLI separates finalization from immutable verification", () => {
  assert.throws(() => parseArgs([]), /--unit-root/u);
  assert.throws(() => parseArgs(["--unit-root", "/tmp/unit"]), /--state-file/u);
  assert.throws(
    () => parseArgs(["--verify-only", "--unit-root", "/tmp/unit"]),
    /--task-id/u,
  );
  assert.equal(parseArgs(["--help"]).help, true);
});

test("completed execution freezes an exact candidate and creates a verified receipt", async () => {
  const value = await fixture();
  try {
    const result = await finalizeAstronStudioExecution(options(value), {
      now: () => "2026-09-18T00:00:20.000Z",
      terminateProcesses: async () => successfulCleanup(),
    });
    assert.equal(result.status, "PASS");
    assert.equal(result.receipt_status, "completed");
    const record = JSON.parse(await readFile(join(result.evidence_root, "execution-record.json"), "utf8"));
    assert.equal(record.evidence.completeness, "complete");
    assert.equal(record.execution.agent_duration_seconds, 4);
    assert.equal(record.candidate.drift_status, "stable");
    const verified = await verifyAstronStudioCollection({ unitRoot: value.root, taskId: value.taskId });
    assert.equal(verified.status, "PASS");
    assert.equal(verified.candidate_sha256, result.candidate_sha256);
    const siblingPath = "evidence/tasks/sibling-task/sibling-attempt/process-cleanup.json";
    const siblingBytes = Buffer.from("{\"sibling\":true}\n", "utf8");
    await mkdir(join(value.root, "evidence", "tasks", "sibling-task", "sibling-attempt"), { recursive: true });
    await writeFile(join(value.root, siblingPath), siblingBytes);
    const receiptPath = join(value.root, "receipts", "collect-evidence-receipt.json");
    const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
    receipt.artifacts.push({
      path: siblingPath,
      sha256: digest(siblingBytes),
      size: siblingBytes.length,
    });
    receipt.artifacts.sort((left, right) => left.path.localeCompare(right.path));
    await writeJson(receiptPath, receipt);
    const verifiedWithSibling = await verifyAstronStudioCollection({
      unitRoot: value.root,
      taskId: value.taskId,
    });
    assert.equal(verifiedWithSibling.status, "PASS");
    await assert.rejects(
      finalizeAstronStudioExecution(options(value), {
        terminateProcesses: async () => successfulCleanup(),
      }),
      /OUTPUT_EXISTS/u,
    );
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});

test("existing receipt fails before process cleanup or evidence publication", async () => {
  const value = await fixture({ attemptId: "attempt-existing-receipt" });
  let cleanupCalled = false;
  try {
    await writeFile(join(value.root, "receipts", "collect-evidence-receipt.json"), "occupied\n");
    await assert.rejects(
      finalizeAstronStudioExecution(options(value), {
        terminateProcesses: async () => {
          cleanupCalled = true;
          return successfulCleanup();
        },
      }),
      /OUTPUT_EXISTS/u,
    );
    assert.equal(cleanupCalled, false);
    await assert.rejects(
      readFile(join(value.root, "evidence", "tasks", value.taskId, value.attemptId, "execution-record.json")),
      /ENOENT/u,
    );
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});

test("verification fails closed after source or frozen candidate drift", async () => {
  const value = await fixture();
  try {
    const result = await finalizeAstronStudioExecution(options(value), {
      terminateProcesses: async () => successfulCleanup(),
    });
    await writeFile(join(result.evidence_root, "candidate", "workspace", "answer.txt"), "drift\n");
    await assert.rejects(
      verifyAstronStudioCollection({ unitRoot: value.root, taskId: value.taskId }),
      /EVIDENCE_MANIFEST_SCOPE_MISMATCH|EVIDENCE_ARTIFACT_DIGEST_MISMATCH|候选产物发生漂移/u,
    );
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }

  const sourceValue = await fixture({ attemptId: "attempt-source-drift" });
  try {
    await finalizeAstronStudioExecution(options(sourceValue), {
      terminateProcesses: async () => successfulCleanup(),
    });
    await writeFile(join(sourceValue.workspace, "late.txt"), "late\n");
    await assert.rejects(
      verifyAstronStudioCollection({ unitRoot: sourceValue.root, taskId: sourceValue.taskId }),
      /候选产物发生漂移/u,
    );
  } finally {
    await rm(sourceValue.root, { recursive: true, force: true });
  }
});

test("verification rejects omitted manifest artifacts and candidate mode drift", async () => {
  const manifestValue = await fixture({ attemptId: "attempt-manifest-omission" });
  try {
    const result = await finalizeAstronStudioExecution(options(manifestValue), {
      terminateProcesses: async () => successfulCleanup(),
    });
    const manifestPath = join(result.evidence_root, "evidence-manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    manifest.artifacts.pop();
    await writeJson(manifestPath, manifest);
    const receiptPath = join(manifestValue.root, "receipts", "collect-evidence-receipt.json");
    const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
    const bytes = await readFile(manifestPath);
    const row = receipt.artifacts.find((item) => item.path.endsWith("/evidence-manifest.json"));
    row.sha256 = digest(bytes);
    row.size = bytes.length;
    await writeJson(receiptPath, receipt);
    await assert.rejects(
      verifyAstronStudioCollection({ unitRoot: manifestValue.root, taskId: manifestValue.taskId }),
      /EVIDENCE_MANIFEST_SCOPE_MISMATCH/u,
    );
  } finally {
    await rm(manifestValue.root, { recursive: true, force: true });
  }

  const modeValue = await fixture({ attemptId: "attempt-mode-drift" });
  try {
    const result = await finalizeAstronStudioExecution(options(modeValue), {
      terminateProcesses: async () => successfulCleanup(),
    });
    await chmod(join(result.evidence_root, "candidate", "workspace", "answer.txt"), 0o755);
    await assert.rejects(
      verifyAstronStudioCollection({ unitRoot: modeValue.root, taskId: modeValue.taskId }),
      /CANDIDATE_ARTIFACT_SCOPE_MISMATCH/u,
    );
  } finally {
    await rm(modeValue.root, { recursive: true, force: true });
  }
});

test("process cleanup and stability failures stop before candidate publication", async () => {
  const cleanupFailure = await fixture({ attemptId: "attempt-cleanup-failure" });
  try {
    await assert.rejects(
      finalizeAstronStudioExecution(options(cleanupFailure), {
        terminateProcesses: async () => ({ supported: true, success: false, error: "residual process" }),
      }),
      /TASK_PROCESS_CLEANUP_FAILED/u,
    );
  } finally {
    await rm(cleanupFailure.root, { recursive: true, force: true });
  }

  const unstable = await fixture({ attemptId: "attempt-unstable" });
  try {
    await assert.rejects(
      finalizeAstronStudioExecution({ ...options(unstable), stabilityMilliseconds: 1 }, {
        terminateProcesses: async () => successfulCleanup(),
        sleep: async () => writeFile(join(unstable.workspace, "late.txt"), "late\n"),
      }),
      /WORKSPACE_NOT_STABLE/u,
    );
  } finally {
    await rm(unstable.root, { recursive: true, force: true });
  }
});

test("timeout keeps partial trace and infrastructure failure remains a partial stage", async () => {
  const timeout = await fixture({
    businessStatus: "timeout",
    traceStatus: "partial",
    includeResource: false,
    attemptId: "attempt-timeout",
  });
  try {
    const result = await finalizeAstronStudioExecution(options(timeout), {
      terminateProcesses: async () => successfulCleanup(),
    });
    const record = JSON.parse(await readFile(join(result.evidence_root, "execution-record.json"), "utf8"));
    assert.equal(record.execution.business_status, "timeout");
    assert.equal(record.evidence.completeness, "partial");
    assert.equal(result.receipt_status, "completed");
  } finally {
    await rm(timeout.root, { recursive: true, force: true });
  }

  const infrastructure = await fixture({
    businessStatus: "infrastructure_error",
    includeTrace: false,
    includeResource: false,
    attemptId: "attempt-infrastructure",
  });
  try {
    const result = await finalizeAstronStudioExecution(options(infrastructure), {
      terminateProcesses: async () => successfulCleanup(),
    });
    assert.equal(result.receipt_status, "partial");
    const record = JSON.parse(await readFile(join(result.evidence_root, "execution-record.json"), "utf8"));
    assert.equal(record.evidence.completeness, "partial");
    assert.equal(record.execution.business_status, "infrastructure_error");
  } finally {
    await rm(infrastructure.root, { recursive: true, force: true });
  }
});

test("candidate freeze rejects an escaping symlink", async () => {
  const value = await fixture({ attemptId: "attempt-symlink" });
  try {
    await symlink("/tmp", join(value.workspace, "escape"));
    await assert.rejects(
      finalizeAstronStudioExecution(options(value), {
        terminateProcesses: async () => successfulCleanup(),
      }),
      /CANDIDATE_SYMLINK_ESCAPES_ROOT/u,
    );
  } finally {
    await rm(value.root, { recursive: true, force: true });
  }
});

test("macOS process selection uses exact command or cwd seeds and includes descendants", () => {
  const workspace = "/tmp/general-e2e/task/workspace";
  const table = parseDarwinProcessTable(`
  100 1 Thu Sep 18 01:02:03 2026 /bin/sleep 30
  101 100 Thu Sep 18 01:02:04 2026 /usr/bin/python child.py
  102 1 Thu Sep 18 01:02:05 2026 /usr/bin/python /tmp/general-e2e/task/workspace/run.py
  103 1 Thu Sep 18 01:02:06 2026 /usr/bin/python /tmp/general-e2e/task/workspace-other/run.py
  `);
  const selected = selectDarwinTaskProcesses(table, workspace, { cwdPids: [100] });
  assert.deepEqual(selected.seed_pids, [100, 102]);
  assert.deepEqual(selected.targets.map((item) => item.pid), [100, 101, 102]);
  assert.equal(selected.targets.find((item) => item.pid === 101).descendant_of_seed, true);
});

test("macOS live cleanup terminates only the process whose cwd is the candidate", {
  skip: process.platform !== "darwin",
}, async () => {
  const root = await mkdtemp(join(tmpdir(), "general-e2e-process-cleanup-"));
  const workspace = join(root, "workspace");
  await mkdir(workspace);
  const child = spawn("/bin/sh", ["-c", `cd "${workspace}" && exec /bin/sleep 30`], {
    stdio: "ignore",
  });
  try {
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
    const result = await terminateDarwinTaskProcesses(workspace, {
      quietMilliseconds: 250,
      waitMilliseconds: 3_000,
      termGraceMilliseconds: 100,
    });
    assert.equal(result.success, true);
    assert.ok(result.before.targets.some((item) => item.pid === child.pid));
    assert.equal(result.after.targets.length, 0);
  } finally {
    try { child.kill("SIGKILL"); } catch {}
    await rm(root, { recursive: true, force: true });
  }
});
