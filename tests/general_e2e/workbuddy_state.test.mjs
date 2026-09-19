import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import test from "node:test";

import {
  loadWorkBuddyConversation,
  normalizeWorkBuddyConversation,
  workBuddyWorkspaceHistoryKey,
} from "../../eval_general_e2e/adapters/workbuddy/native-history.mjs";
import {
  buildWorkBuddyExecutionState,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/state.mjs";

const REPO_ROOT = resolve(dirname(new URL(import.meta.url).pathname), "../..");
const FIXTURE_ROOT = join(REPO_ROOT, "tests/general_e2e/fixtures/workbuddy/native-history");
const IDENTITY = Object.freeze({
  batch_id: "fixture-batch",
  unit_id: "fixture-unit",
  task_id: "fixture-task",
  attempt_id: "fixture-attempt",
});
const DATASET = Object.freeze({ id: "fixture-dataset", digest: "d".repeat(64) });

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function createUnitFixture() {
  let root = await mkdtemp(join(tmpdir(), "workbuddy-state-test-"));
  root = await realpath(root);
  const taskRoot = join(root, "execution", "tasks", IDENTITY.task_id);
  let workspace = join(taskRoot, "workspace");
  const promptPath = join(taskRoot, "prompt.md");
  const promptText = "Create the synthetic fixture output.\n";
  const evidencePath = join(taskRoot, "evidence", "workbuddy-binding.json");
  await mkdir(workspace, { recursive: true });
  workspace = await realpath(workspace);
  await mkdir(dirname(evidencePath), { recursive: true });
  await writeFile(promptPath, promptText, "utf8");
  await writeFile(evidencePath, "{\"fixture\":true}\n", "utf8");
  const dataRoot = join(root, "WorkBuddyExtension", "Data");
  const historyRoot = join(
    dataRoot,
    "account-fixture",
    "VSCode",
    "identity-fixture",
    "history",
    workBuddyWorkspaceHistoryKey(workspace),
  );
  const conversationRoot = join(historyRoot, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
  await mkdir(join(conversationRoot, "messages"), { recursive: true });
  await writeFile(join(historyRoot, "index.json"), await readFile(join(FIXTURE_ROOT, "workspace-index.json")));
  await writeFile(join(conversationRoot, "index.json"), await readFile(join(FIXTURE_ROOT, "conversation-index.json")));
  for (const name of [
    "cccccccccccccccccccccccccccccccc.json",
    "dddddddddddddddddddddddddddddddd.json",
    "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee.json",
    "ffffffffffffffffffffffffffffffff.json",
  ]) {
    await writeFile(
      join(conversationRoot, "messages", name),
      await readFile(join(FIXTURE_ROOT, "messages", name)),
    );
  }
  const evidenceBytes = await readFile(evidencePath);
  return {
    root,
    taskRoot,
    workspace,
    promptPath,
    promptText,
    evidencePath,
    dataRoot,
    bindingEvidence: [{
      path: relative(root, evidencePath),
      sha256: sha256(evidenceBytes),
      size: evidenceBytes.length,
    }],
  };
}

test("WorkBuddy native identity maps to CB-A without inventing a thread id", async () => {
  const fixture = await createUnitFixture();
  try {
    const loaded = await loadWorkBuddyConversation({
      dataRoot: fixture.dataRoot,
      workspace: fixture.workspace,
      conversationId: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      requestId: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    });
    const history = normalizeWorkBuddyConversation(loaded, { identity: IDENTITY, redacted: true });
    history.request = loaded.request;
    history.conversation = loaded.conversation;
    history.binding.workspace_history_key = loaded.workspace_history_key;
    const state = buildWorkBuddyExecutionState({
      identity: IDENTITY,
      dataset: DATASET,
      taskRoot: fixture.taskRoot,
      candidateWorkspace: fixture.workspace,
      prompt: {
        path: fixture.promptPath,
        sha256: sha256(fixture.promptText),
        send_status: "sent",
        sent_at: "2026-09-19T08:00:00.000Z",
      },
      send: { dispatch_attempt_count: 1 },
      sessionSnapshot: {
        conversation_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        cwd: fixture.workspace,
        status: "Completed",
      },
      history,
      bindingEvidence: fixture.bindingEvidence,
    });
    assert.equal(state.phase, "COMPLETED");
    assert.equal(state.execution.business_status, "completed");
    assert.equal(state.session.thread_id, null);
    assert.equal(state.session.turn_id, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    assert.equal(state.session.session_id, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    assert.equal(state.session.verified, true);
    assert.equal(state.extensions.workbuddy.final_response_present, true);

    const manifest = {
      batch_id: IDENTITY.batch_id,
      unit_id: IDENTITY.unit_id,
      task_ids: [IDENTITY.task_id],
      dataset: DATASET,
      unit: { harness: { id: "workbuddy", platform: "macos" } },
      tasks: [{
        task_id: IDENTITY.task_id,
        workspace: { path: relative(fixture.root, fixture.workspace) },
        prompt: {
          path: relative(fixture.root, fixture.promptPath),
          sent_sha256: sha256(fixture.promptText),
        },
      }],
    };
    const validation = spawnSync(
      process.env.PYTHON || "python3",
      [
        "-c",
        [
          "import json,sys",
          "from pathlib import Path",
          "from eval_general_e2e.contracts.execution_state import validate_terminal_execution_state",
          "payload=json.load(sys.stdin)",
          "validate_terminal_execution_state(payload['state'], unit_root=Path(payload['root']), manifest=payload['manifest'])",
        ].join(";"),
      ],
      {
        cwd: REPO_ROOT,
        encoding: "utf8",
        input: JSON.stringify({ state, root: fixture.root, manifest }),
      },
    );
    assert.equal(validation.status, 0, validation.stderr);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy state mapping fails closed on cwd and prompt mismatches", async () => {
  const fixture = await createUnitFixture();
  try {
    const base = {
      identity: IDENTITY,
      dataset: DATASET,
      taskRoot: fixture.taskRoot,
      candidateWorkspace: fixture.workspace,
      prompt: {
        path: fixture.promptPath,
        sha256: sha256(fixture.promptText),
        send_status: "sent",
        sent_at: "2026-09-19T08:00:00.000Z",
      },
      send: { dispatch_attempt_count: 1 },
      sessionSnapshot: {
        conversation_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        cwd: fixture.workspace,
        status: "Completed",
      },
      history: {
        binding: {
          conversation_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          request_id: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          request_state: { raw: "complete" },
        },
        prompt: { sha256: sha256(fixture.promptText) },
        completeness: { status: "complete", missing: [] },
        final_response: "done",
        request: { startedAt: 1789804800000 },
        conversation: { lastMessageAt: "2026-09-19T08:00:04.000Z" },
        resources: null,
      },
      bindingEvidence: fixture.bindingEvidence,
    };
    assert.throws(
      () => buildWorkBuddyExecutionState({
        ...base,
        sessionSnapshot: { ...base.sessionSnapshot, cwd: join(fixture.root, "other") },
      }),
      /CWD_MISMATCH/u,
    );
    assert.throws(
      () => buildWorkBuddyExecutionState({
        ...base,
        prompt: { ...base.prompt, sha256: "0".repeat(64) },
      }),
      /PROMPT_HASH_MISMATCH/u,
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy state requires aligned terminal semantics and confirmed cancellation", async () => {
  const fixture = await createUnitFixture();
  try {
    const base = {
      identity: IDENTITY,
      dataset: DATASET,
      taskRoot: fixture.taskRoot,
      candidateWorkspace: fixture.workspace,
      prompt: {
        path: fixture.promptPath,
        sha256: sha256(fixture.promptText),
        send_status: "sent",
        sent_at: "2026-09-19T08:00:00.000Z",
      },
      send: { dispatch_attempt_count: 1 },
      sessionSnapshot: {
        conversation_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        cwd: fixture.workspace,
        status: "Failed",
      },
      history: {
        binding: {
          conversation_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          request_id: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          request_state: { raw: "running" },
        },
        prompt: { sha256: sha256(fixture.promptText) },
        completeness: { status: "partial", missing: ["request_terminal_state:running"] },
        final_response: null,
        request: { startedAt: 1789804800000 },
        conversation: { lastMessageAt: "2026-09-19T08:00:04.000Z" },
        resources: null,
      },
      bindingEvidence: fixture.bindingEvidence,
    };

    const conflict = buildWorkBuddyExecutionState(base);
    assert.equal(conflict.phase, "NEEDS_ATTENTION");
    assert.equal(conflict.execution.business_status, null);
    assert.equal(conflict.execution.error.code, "WORKBUDDY_TERMINAL_STATE_CONFLICT");

    const running = buildWorkBuddyExecutionState({
      ...base,
      sessionSnapshot: { ...base.sessionSnapshot, status: "Running" },
    });
    assert.equal(running.phase, "RUNNING");
    assert.equal(running.execution.finished_at, null);
    assert.equal(running.execution.duration_seconds, null);

    const interrupted = buildWorkBuddyExecutionState({
      ...base,
      sessionSnapshot: { ...base.sessionSnapshot, status: "Interrupted" },
      history: {
        ...base.history,
        binding: { ...base.history.binding, request_state: { raw: "interrupted" } },
      },
    });
    assert.equal(interrupted.phase, "NEEDS_ATTENTION");
    assert.equal(interrupted.execution.error.code, "WORKBUDDY_INTERRUPTION_UNVERIFIED");

    const unconfirmed = buildWorkBuddyExecutionState({
      ...base,
      sessionSnapshot: { ...base.sessionSnapshot, status: "Cancelled" },
      history: {
        ...base.history,
        binding: { ...base.history.binding, request_state: { raw: "cancelled" } },
      },
    });
    assert.equal(unconfirmed.phase, "NEEDS_ATTENTION");
    assert.equal(unconfirmed.execution.error.code, "WORKBUDDY_CANCELLATION_UNCONFIRMED");
    assert.equal(unconfirmed.execution.cancellation_confirmed, null);

    const confirmed = buildWorkBuddyExecutionState({
      ...base,
      sessionSnapshot: { ...base.sessionSnapshot, status: "Cancelled" },
      history: {
        ...base.history,
        binding: { ...base.history.binding, request_state: { raw: "cancelled" } },
      },
      cancellationConfirmed: true,
    });
    assert.equal(confirmed.phase, "FAILED");
    assert.equal(confirmed.execution.business_status, "cancelled");
    assert.equal(confirmed.execution.cancellation_confirmed, true);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});
