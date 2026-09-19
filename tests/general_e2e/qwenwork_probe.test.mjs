import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  buildReadOnlyProbe,
  parseProbeArgs,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/probe.mjs";
import {
  buildQwenGeneralSessionBinding,
  classifyQwenSessionStatus,
  selectQwenSessionForAttempt,
  summarizeQwenSessions,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/session-state.mjs";
import {
  buildQwenGeneralExecutionState,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/execution-state.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const FIXTURES = join(ROOT, "tests/general_e2e/fixtures/qwenwork");
const WORKSPACE = "/private/tmp/qwenwork-general-fixture/workspace";

async function json(name) {
  return JSON.parse(await readFile(join(FIXTURES, name), "utf8"));
}

test("probe CLI rejects non-loopback endpoints and exposes no mutating flag", () => {
  assert.throws(() => parseProbeArgs(["--endpoint", "https://example.com"]), /loopback/u);
  assert.throws(() => parseProbeArgs(["--restart-app"]), /unknown option/u);
  const parsed = parseProbeArgs(["--endpoint", "http://localhost:9250"]);
  assert.equal(parsed.endpoint, "http://localhost:9250");
});

test("native terminal mapping preserves cancelled/interrupted and unknown separately", () => {
  assert.equal(classifyQwenSessionStatus("completed").business_status, "completed");
  assert.equal(classifyQwenSessionStatus("cancelled").business_status, "cancelled");
  assert.equal(classifyQwenSessionStatus("interrupted").business_status, "interrupted");
  assert.equal(classifyQwenSessionStatus("future-state").kind, "unknown");
  assert.equal(classifyQwenSessionStatus("completed", "active-stream").kind, "running");
});

test("session selection requires exact cwd plus native identity and never guesses by recency", async () => {
  const sessions = await json("sessions-redacted.json");
  const selected = selectQwenSessionForAttempt({
    sessions,
    workspace: WORKSPACE,
    nativeBinding: { session_id: "session-fixture-001" },
  });
  assert.equal(selected.session_id, "session-fixture-001");
  assert.equal(selectQwenSessionForAttempt({ sessions, workspace: WORKSPACE }), null);
  assert.equal(selectQwenSessionForAttempt({
    sessions,
    workspace: WORKSPACE,
    nativeBinding: { local_project_id: "project-fixture-001" },
    baseline: [],
  }), null);
  assert.equal(selectQwenSessionForAttempt({
    sessions,
    workspace: WORKSPACE,
    nativeBinding: { session_id: "session-fixture-002" },
  }), null);
  const summary = summarizeQwenSessions(sessions);
  assert.equal(summary.session_count, 3);
  assert.equal(summary.active_or_pending_count, 1);
  assert.equal(summary.stable_identity_coverage.session_id, 3);
});

test("fresh session binding rejects relative cwd and updated baseline sessions", () => {
  const sentAt = "2026-09-17T03:00:01.000Z";
  const fresh = {
    conversation_id: "conversation-new",
    sub_chat_id: "sub-chat-new",
    session_id: "session-new",
    local_project_id: "project-fixture-001",
    cwd: WORKSPACE,
    native_status: "running",
    created_at_ms: Date.parse(sentAt),
    updated_at_ms: Date.parse(sentAt),
  };
  assert.equal(selectQwenSessionForAttempt({
    sessions: [{ ...fresh, cwd: "relative/workspace" }],
    workspace: WORKSPACE,
    nativeBinding: { local_project_id: "project-fixture-001" },
    baseline: [],
    sentAt,
  }), null);
  assert.equal(selectQwenSessionForAttempt({
    sessions: [fresh],
    workspace: WORKSPACE,
    nativeBinding: { local_project_id: "project-fixture-001" },
    baseline: [{ ...fresh, updated_at_ms: Date.parse(sentAt) - 1_000 }],
    sentAt,
  }), null);
  assert.equal(selectQwenSessionForAttempt({
    sessions: [fresh],
    workspace: WORKSPACE,
    nativeBinding: { local_project_id: "project-fixture-001" },
    baseline: [],
    sentAt,
  }).session_id, "session-new");
});

test("CB-A session binding uses native session ID and leaves nonexistent thread/turn null", async () => {
  const session = (await json("sessions-redacted.json"))[0];
  const binding = buildQwenGeneralSessionBinding(session, [{
    path: "evidence/qwenwork/session-binding.json",
    sha256: "a".repeat(64),
    size: 10,
  }]);
  assert.deepEqual(binding, {
    thread_id: null,
    turn_id: null,
    session_id: "session-fixture-001",
    cwd: WORKSPACE,
    verified: true,
    binding_evidence: [{
      path: "evidence/qwenwork/session-binding.json",
      sha256: "a".repeat(64),
      size: 10,
    }],
  });
});

test("CB-A state maps completed and ambiguous cancellation without fabricating proof", async () => {
  const sessions = await json("sessions-redacted.json");
  const base = {
    identity: { batch_id: "batch", unit_id: "qwenwork-macos", task_id: "task", attempt_id: "attempt" },
    dataset: { id: "dataset", digest: "d".repeat(64) },
    taskRoot: "/private/tmp/qwenwork-general-fixture",
    candidateWorkspace: WORKSPACE,
    prompt: { path: "/private/tmp/qwenwork-general-fixture/prompt.md", sha256: "e".repeat(64), send_status: "sent", sent_at: "2026-09-17T03:00:01Z" },
    dispatchAttemptCount: 1,
    bindingEvidence: [{ path: "evidence/binding.json", sha256: "a".repeat(64), size: 10 }],
    startedAt: "2026-09-17T03:00:01Z",
    finishedAt: "2026-09-17T03:00:06Z",
    durationSeconds: 5,
  };
  const trustedTerminal = {
    observed_at: "2026-09-17T03:00:06Z",
    source: "fixture-db+ui",
    active_stream: false,
    stop_confirmed: true,
    binding_consistent: true,
    conflicts: [],
  };
  const completed = buildQwenGeneralExecutionState({
    ...base,
    session: sessions[0],
    terminalObservation: trustedTerminal,
  });
  assert.equal(completed.phase, "COMPLETED");
  assert.equal(completed.execution.business_status, "completed");
  assert.equal(completed.session.thread_id, null);
  assert.equal(completed.session.turn_id, null);
  const cancelledSession = { ...sessions[1], cwd: WORKSPACE };
  const cancelled = buildQwenGeneralExecutionState({ ...base, session: cancelledSession });
  assert.equal(cancelled.phase, "NEEDS_ATTENTION");
  assert.equal(cancelled.execution.business_status, null);
  const confirmed = buildQwenGeneralExecutionState({
    ...base,
    session: cancelledSession,
    cancellationConfirmed: true,
    terminalObservation: trustedTerminal,
  });
  assert.equal(confirmed.phase, "FAILED");
  assert.equal(confirmed.execution.business_status, "cancelled");
});

test("terminal states require stop, stream, cwd, and binding agreement", async () => {
  const sessions = await json("sessions-redacted.json");
  const base = {
    identity: { batch_id: "batch", unit_id: "qwenwork-macos", task_id: "task", attempt_id: "attempt" },
    dataset: { id: "dataset", digest: "d".repeat(64) },
    taskRoot: "/private/tmp/qwenwork-general-fixture",
    candidateWorkspace: WORKSPACE,
    prompt: { path: "/private/tmp/qwenwork-general-fixture/prompt.md", sha256: "e".repeat(64), send_status: "sent", sent_at: "2026-09-17T03:00:01Z" },
    dispatchAttemptCount: 1,
    bindingEvidence: [{ path: "evidence/binding.json", sha256: "a".repeat(64), size: 10 }],
    startedAt: "2026-09-17T03:00:01Z",
    finishedAt: "2026-09-17T03:00:06Z",
    durationSeconds: 5,
  };
  const unconfirmed = buildQwenGeneralExecutionState({
    ...base,
    session: sessions[0],
    terminalObservation: { active_stream: false, stop_confirmed: false, binding_consistent: true, conflicts: [] },
  });
  assert.equal(unconfirmed.phase, "NEEDS_ATTENTION");
  const conflict = buildQwenGeneralExecutionState({
    ...base,
    session: sessions[0],
    terminalObservation: { active_stream: true, stop_confirmed: true, binding_consistent: true, conflicts: [] },
  });
  assert.equal(conflict.phase, "NEEDS_ATTENTION");
  assert.ok(conflict.extensions.qwenwork.terminal_observation.conflicts.includes("active-stream-observation-mismatch"));
  const failedWithoutStop = buildQwenGeneralExecutionState({
    ...base,
    session: { ...sessions[0], native_status: "failed" },
    terminalObservation: { active_stream: false, stop_confirmed: false, binding_consistent: true, conflicts: [] },
  });
  assert.equal(failedWithoutStop.phase, "NEEDS_ATTENTION");
  const interruptedWithoutStop = buildQwenGeneralExecutionState({
    ...base,
    session: { ...sessions[0], native_status: "interrupted" },
    terminalObservation: { active_stream: false, stop_confirmed: false, binding_consistent: true, conflicts: [] },
  });
  assert.equal(interruptedWithoutStop.phase, "NEEDS_ATTENTION");
  const timeoutWithoutStop = buildQwenGeneralExecutionState({
    ...base,
    session: sessions[0],
    timeoutReached: true,
    terminalObservation: { active_stream: false, stop_confirmed: false, binding_consistent: true, conflicts: [] },
  });
  assert.equal(timeoutWithoutStop.phase, "NEEDS_ATTENTION");
});

test("read-only probe report keeps current 1.0.6 profile unverified and declares no UI mutation", async () => {
  const runtime = await json("runtime-current-macos-1.0.6.json");
  const report = await buildReadOnlyProbe({
    appPath: "",
    sessionDb: "/private/tmp/agents.db",
    traceRoot: "/private/tmp/.qwenworkcn",
    endpoint: "http://127.0.0.1:9250",
  }, {
    discoverDesktopApp: async () => ({
      path: "/Applications/QwenWorkCN.app",
      executable_path: "/Applications/QwenWorkCN.app/Contents/MacOS/QwenWorkCN",
      source: "fixture",
      identity_verified: true,
      bundle_id: "cn.qwenwork.desktop.mac",
      version: "1.0.6",
    }),
    inspectTrace: async () => ({
      root_exists: true,
      transcript_file_count: 1,
      segment_file_count: 1,
      discovered_jsonl_count: 2,
      transcript_versions: ["1.1.32"],
      warnings: [],
    }),
    inspectDatabase: async () => ({
      readable: true,
      quick_check: "ok",
      session_count: 3,
      active_or_pending_count: 0,
    }),
    inspectRuntime: async () => runtime,
    inspectProcess: async () => ({ running: false, unique_main_process: false, process_count: 0, processes: [] }),
    inspectEndpoint: async () => ({ ready: false, status: null, browser_identity_present: false }),
    inspectArchitecture: async () => ({ architectures: ["x86_64"], universal: false }),
  });
  assert.equal(report.ready_for_read_only_mapping, true);
  assert.equal(report.ready_for_automated_execution, false);
  assert.equal(report.runtime.normalization_profile, null);
  assert.equal(report.runtime.token_metrics_admission, "unverified-null");
  assert.ok(report.operations_not_performed.includes("send-prompt"));
  assert.ok(report.warnings.includes("QWENWORK_RUNTIME_PROFILE_UNVERIFIED"));
});
