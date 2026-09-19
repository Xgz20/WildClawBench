import assert from "node:assert/strict";
import { test } from "node:test";

import {
  assessDoubaoWebFinalization,
  FINALIZER_ASSESSMENT_SCHEMA,
} from "../finalizer.mjs";
import { NATIVE_EVIDENCE_SCHEMA, sha256Text } from "../lib.mjs";

function fixtureState() {
  return {
    attempt_id: "attempt-finalizer",
    identity: { batch_id: "batch-finalizer", task_id: "task-finalizer" },
    workspace: "/private/debug/task/workspace",
    prompt: { readback_sha256: "a".repeat(64) },
    session: {
      conversation_id: "123",
      session_directory_id: "123",
      prompt_readback: { status: "verified" },
    },
    client: { project_id_sha256: sha256Text("project-42"), project_name: "Fixture" },
    workspace_selection: {
      confirmed: true,
      actual_path: "/private/debug/task/workspace",
      source: "project-folder-tooltip",
    },
  };
}

function fixtureObservation() {
  const state = fixtureState();
  return {
    state,
    observation: {
      ui: {
        current_conversation_id: "123",
        conversation_project_id_sha256: state.client.project_id_sha256,
        current_project_control_count: 1,
        current_project_name: "Fixture",
        stop_control_count: 0,
        bound_conversation_busy_count: 0,
        visible_dialog_count: 0,
        user_question_count: 0,
        approval_count: 0,
        visible_error_count: 0,
        positive_completion_marker_count: 1,
      },
      binding: { status: "verified" },
      classification: { kind: "ui-completion-candidate", trusted: false },
      stable_completion_observations: 3,
    },
  };
}

function fixtureNativeEvidence(state = fixtureState()) {
  return {
    schema: NATIVE_EVIDENCE_SCHEMA,
    identity: {
      conversation_id: state.session.conversation_id,
      session_directory_id: state.session.session_directory_id,
      requested_workspace: state.workspace,
      native_cwd: null,
      workspace_binding: { status: "unverified", requested_path: state.workspace },
    },
    terminal: { status: "unverified" },
  };
}

function fixtureCleanup() {
  return {
    supported: true,
    success: true,
    tracked_residue: [],
    after: { targets: [] },
    quiet_window_milliseconds: 1000,
    quiet_observed_milliseconds: 1000,
  };
}

function fixtureCandidate() {
  return { frozen: true, sha256: "b".repeat(64) };
}

test("UI 已 verified 但 native evidence、cleanup、candidate 任一缺失时失败关闭", () => {
  const { state, observation } = fixtureObservation();
  const result = assessDoubaoWebFinalization({ state, observation });
  assert.equal(result.schema, FINALIZER_ASSESSMENT_SCHEMA);
  assert.equal(result.status, "NEEDS_ATTENTION");
  assert.equal(result.formal_execution_receipt_allowed, false);
  assert.equal(result.ui.verified, true);
  assert.equal(result.native.present, false);
  assert.ok(result.reasons.includes("NATIVE_EVIDENCE_MISSING"));
  assert.ok(result.reasons.includes("PROCESS_CLEANUP_UNVERIFIED"));
  assert.ok(result.reasons.includes("CANDIDATE_FREEZE_UNVERIFIED"));
  assert.equal(result.integrity.native_terminal_verified, false);
  assert.equal(result.integrity.native_cwd_verified, false);
});

test("Web 等价证据可通过收口条件，但不会把 unverified native 字段伪造成 verified", () => {
  const { state, observation } = fixtureObservation();
  const result = assessDoubaoWebFinalization({
    state,
    observation,
    nativeEvidence: fixtureNativeEvidence(state),
    cleanup: fixtureCleanup(),
    candidate: fixtureCandidate(),
    now: "2026-09-19T15:00:00.000Z",
  });
  assert.equal(result.status, "READY_FOR_WEB_RECEIPT");
  assert.equal(result.formal_execution_receipt_allowed, true);
  assert.equal(result.integrity.equivalent_web_binding, true);
  assert.equal(result.native.terminal_status, "unverified");
  assert.equal(result.native.cwd_status, "unverified");
  assert.equal(result.integrity.native_terminal_verified, false);
  assert.equal(result.integrity.native_cwd_verified, false);
  assert.deepEqual(result.warnings, [
    "NATIVE_TERMINAL_REMAINS_UNVERIFIED",
    "NATIVE_CWD_REMAINS_UNVERIFIED",
  ]);
});

test("native evidence 会话或 workspace 绑定不一致时拒绝复用 UI 完成", () => {
  const { state, observation } = fixtureObservation();
  const nativeEvidence = fixtureNativeEvidence(state);
  nativeEvidence.identity.conversation_id = "999";
  const result = assessDoubaoWebFinalization({
    state,
    observation,
    nativeEvidence,
    cleanup: fixtureCleanup(),
    candidate: fixtureCandidate(),
  });
  assert.equal(result.status, "NEEDS_ATTENTION");
  assert.equal(result.formal_execution_receipt_allowed, false);
  assert.ok(result.reasons.includes("NATIVE_EVIDENCE_IDENTITY_MISMATCH"));
});

test("发送前 Prompt 摘要存在但 conversation 尚未回读时仍失败关闭", () => {
  const { state, observation } = fixtureObservation();
  state.session.prompt_readback.status = "unverified";
  const result = assessDoubaoWebFinalization({
    state,
    observation,
    nativeEvidence: fixtureNativeEvidence(state),
    cleanup: fixtureCleanup(),
    candidate: fixtureCandidate(),
  });
  assert.equal(result.ui.prompt_verified, false);
  assert.equal(result.ui.verified, false);
  assert.equal(result.status, "NEEDS_ATTENTION");
  assert.ok(result.reasons.includes("UI_EQUIVALENT_BINDING_UNVERIFIED"));
});
