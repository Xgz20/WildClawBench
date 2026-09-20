import assert from "node:assert/strict";
import test from "node:test";

import {
  assertWorkBuddyCleanupEvidence,
  assertWorkBuddyCollectorReadiness,
  createWorkBuddyCleanupHook,
  selectDarwinTaskProcesses,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/cleanup.mjs";

const WORKSPACE = "/tmp/workbuddy-general/task/workspace";

function unavailable() {
  return {
    value: null,
    status: "unavailable",
    basis: "synthetic fixture does not expose this field",
    known_subtotal: 0,
    coverage: { known: 0, total: 1, unit: "conversation_request" },
  };
}

function cleanupEvidence(workspace = WORKSPACE) {
  const snapshot = {
    supported: true,
    platform: "darwin",
    workspace,
    seed_pids: [],
    root_pids: [],
    targets: [],
  };
  return {
    schema_version: "wildclawbench.general-e2e-task-process-cleanup/v1",
    supported: true,
    success: true,
    platform: "darwin",
    quiet_window_milliseconds: 5,
    quiet_observed_milliseconds: 5,
    late_process_detected: false,
    before: structuredClone(snapshot),
    termination_attempts: [],
    after: structuredClone(snapshot),
  };
}

function collectorFixture() {
  const identity = {
    batch_id: "batch-one",
    unit_id: "unit-one",
    task_id: "task-one",
    attempt_id: "attempt-one",
  };
  const state = {
    schema_version: "wildclawbench.general-e2e-execution-state/v1",
    driver: { harness: "workbuddy", platform: "macos" },
    identity,
    phase: "COMPLETED",
    execution: { business_status: "completed" },
    candidate_workspace: WORKSPACE,
    prompt: { send_status: "sent" },
    send: { dispatch_attempt_count: 1 },
    session: {
      thread_id: null,
      turn_id: "request-one",
      session_id: "conversation-one",
      cwd: WORKSPACE,
      verified: true,
    },
    extensions: {
      workbuddy: {
        identity_mapping: {
          turn_id_source: "conversation-index.requests[].id",
          session_id_source: "codebuddy-sessions.vscdb.session:*.conversationId",
          cwd_source: "codebuddy-sessions.vscdb.session:*.cwd",
          terminal_status_source: "codebuddy-sessions.vscdb.session:*.status + conversation-index.requests[].state",
        },
      },
    },
  };
  const traceIndex = {
    schema_id: "urn:wildclawbench:schema:general-e2e:trace-index:v2",
    schema_version: 2,
    adapter: {
      id: "workbuddy-native-history",
      version: "0.1.0",
      source: "synthetic WorkBuddy native history fixture",
    },
    identity,
    session: {
      thread_id: null,
      turn_id: "request-one",
      session_id: "conversation-one",
      cwd: WORKSPACE,
    },
    transcript: { path: "transcript.jsonl", event_count: 1 },
    raw_trace: [{ path: "raw/history.json", sha256: "a".repeat(64), size: 1 }],
    binding_evidence: [{ path: "bindings/session.json", sha256: "b".repeat(64), size: 1 }],
    normalization: {
      compatibility_profiles: ["workbuddy-native-history-5.5.3"],
    },
    calls: [],
    completeness: { status: "complete", omitted_event_count: 0, missing: [] },
  };
  const resourceMetrics = {
    schema_id: "urn:wildclawbench:schema:general-e2e:resource-metrics:v1",
    identity,
    collection: { status: "partial" },
    metrics: {
      usage: {
        cache_read_input_tokens: unavailable(),
        cache_creation_input_tokens: unavailable(),
        reasoning_output_tokens: unavailable(),
      },
      requests: { request_attempt_count: unavailable() },
      timing: { duration_seconds: unavailable(), agent_duration_seconds: unavailable() },
    },
  };
  return { state, traceIndex, resourceMetrics };
}

test("WorkBuddy cleanup selection uses exact cwd/command seeds and descendants", () => {
  const processes = [
    { pid: 100, parent_pid: 1, started_at: "a", command: `/bin/sh -c ${WORKSPACE}/run.sh`, command_name: "sh", command_sha256: "a" },
    { pid: 101, parent_pid: 100, started_at: "b", command: "/usr/bin/python child.py", command_name: "python", command_sha256: "b" },
    { pid: 102, parent_pid: 1, started_at: "c", command: `/usr/bin/python ${WORKSPACE}/server.py`, command_name: "python", command_sha256: "c" },
    { pid: 103, parent_pid: 1, started_at: "d", command: `/usr/bin/python ${WORKSPACE}-other/server.py`, command_name: "python", command_sha256: "d" },
  ];
  const selected = selectDarwinTaskProcesses(processes, WORKSPACE, { cwdPids: [100] });
  assert.deepEqual(selected.seed_pids, [100, 102]);
  assert.deepEqual(selected.targets.map((item) => item.pid), [100, 101, 102]);
  assert.equal(selected.targets.some((item) => item.pid === 103), false);
});

test("WorkBuddy cleanup hook uses the shared contract and rejects residual evidence", () => {
  const hook = createWorkBuddyCleanupHook({ run: async () => cleanupEvidence() });
  assert.equal(hook.harness, "workbuddy");
  assert.equal(hook.platform, "darwin");
  assert.doesNotThrow(() => assertWorkBuddyCleanupEvidence(
    cleanupEvidence(), WORKSPACE, { processQuietMilliseconds: 5 }, 10,
  ));
  const residual = cleanupEvidence();
  residual.after.targets.push({ pid: 321 });
  assert.throws(
    () => assertWorkBuddyCleanupEvidence(residual, WORKSPACE, { processQuietMilliseconds: 5 }, 10),
    /TASK_PROCESS_CLEANUP_RESIDUAL_PROCESSES/u,
  );
});

test("WorkBuddy collector readiness preserves unavailable retry/credit fields", () => {
  const fixture = collectorFixture();
  const result = assertWorkBuddyCollectorReadiness({
    ...fixture,
    cleanupHook: createWorkBuddyCleanupHook({ run: async () => cleanupEvidence() }),
  });
  assert.equal(result.status, "READY_FOR_GENERAL_FINALIZER");
  assert.equal(result.transport_retry, "unavailable");
  assert.equal(result.credit, "unverified");
});

test("WorkBuddy collector readiness fails closed on unknown native terminal/cwd and primary credit", () => {
  const fixture = collectorFixture();
  const hook = createWorkBuddyCleanupHook({ run: async () => cleanupEvidence() });
  const cases = [
    ["terminal", (value) => { value.state.phase = "NEEDS_ATTENTION"; }, /NATIVE_TERMINAL_STATE_UNVERIFIED/u],
    ["cwd", (value) => { value.traceIndex.session.cwd = null; }, /NATIVE_CWD_UNVERIFIED/u],
    ["credit", (value) => { value.resourceMetrics.metrics.credit = unavailable(); }, /CREDIT_MUST_REMAIN_OUTSIDE_PRIMARY_METRICS/u],
    ["derived-native-source", (value) => { value.state.extensions.workbuddy.identity_mapping.cwd_source = "state.candidate_workspace"; }, /NATIVE_SOURCE_UNVERIFIED/u],
    ["missing-terminal-source", (value) => { delete value.state.extensions.workbuddy.identity_mapping.terminal_status_source; }, /NATIVE_SOURCE_UNVERIFIED/u],
  ];
  for (const [name, mutate, expected] of cases) {
    const value = structuredClone(fixture);
    mutate(value);
    assert.throws(
      () => assertWorkBuddyCollectorReadiness({ ...value, cleanupHook: hook }),
      expected,
      name,
    );
  }
});

test("WorkBuddy collector readiness rejects cross-attempt trace or resource identity", () => {
  const fixture = collectorFixture();
  const hook = createWorkBuddyCleanupHook({ run: async () => cleanupEvidence() });
  for (const mutate of [
    (value) => {
      value.traceIndex.identity = { ...value.traceIndex.identity, attempt_id: "other-attempt" };
    },
    (value) => {
      value.resourceMetrics.identity = { ...value.resourceMetrics.identity, unit_id: "other-unit" };
    },
  ]) {
    const value = structuredClone(fixture);
    mutate(value);
    assert.throws(
      () => assertWorkBuddyCollectorReadiness({ ...value, cleanupHook: hook }),
      /WORKBUDDY_IDENTITY_MISMATCH/u,
    );
  }
});

test("WorkBuddy collector readiness rejects incomplete v2 trace metadata", () => {
  const fixture = collectorFixture();
  const hook = createWorkBuddyCleanupHook({ run: async () => cleanupEvidence() });
  for (const mutate of [
    (value) => { delete value.traceIndex.adapter.source; },
    (value) => { value.traceIndex.completeness.omitted_event_count = 1; },
    (value) => { delete value.traceIndex.transcript.event_count; },
  ]) {
    const value = structuredClone(fixture);
    mutate(value);
    assert.throws(
      () => assertWorkBuddyCollectorReadiness({ ...value, cleanupHook: hook }),
      /WORKBUDDY_TRACE_INDEX_(CONTRACT_INVALID|INCOMPLETE)/u,
    );
  }
});

test("WorkBuddy cleanup evidence rejects wrong workspace and impossible quiet window", () => {
  const wrongWorkspace = cleanupEvidence("/tmp/another-workspace");
  assert.throws(
    () => assertWorkBuddyCleanupEvidence(wrongWorkspace, WORKSPACE, { processQuietMilliseconds: 5 }, 10),
    /TASK_PROCESS_CLEANUP_SNAPSHOT_INVALID/u,
  );
  const impossible = cleanupEvidence();
  impossible.quiet_observed_milliseconds = 20;
  assert.throws(
    () => assertWorkBuddyCleanupEvidence(impossible, WORKSPACE, { processQuietMilliseconds: 5 }, 10),
    /TASK_PROCESS_CLEANUP_EVIDENCE_INVALID/u,
  );
});
