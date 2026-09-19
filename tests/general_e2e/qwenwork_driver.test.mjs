import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  QWENWORK_CANARY_CONFIG_SCHEMA,
  calculateQwenCanaryConfigDigest,
  runQwenGeneralAttempt,
  verifyQwenSessionPromptEvidence,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs";
import {
  assertQwenJournalMatches,
  atomicWriteQwenJournal,
  confirmQwenDispatchBinding,
  createQwenAttemptJournal,
  planQwenRecovery,
  recordQwenDispatchIntent,
  reserveQwenDispatch,
  readQwenJournal,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/journal.mjs";
import {
  assertStableQwenUiConfiguration,
  confirmQwenWorkspaceProject,
  readQwenUiConfiguration,
  requireUniqueVisible,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/ui.mjs";

const WORKSPACE = "/private/tmp/qwenwork-general-driver/workspace";
const PROMPT_SHA = "e".repeat(64);

function makeConfig(overrides = {}) {
  const config = {
    schema_version: QWENWORK_CANARY_CONFIG_SCHEMA,
    config_digest_algorithm: "sha256-canonical-json/v1",
    identity: {
      batch_id: "batch-fixture",
      unit_id: "qwenwork-macos",
      task_id: "task-fixture",
      attempt_id: "attempt-fixture",
    },
    dataset: { id: "dataset-fixture", digest: "d".repeat(64) },
    task_root: "/private/tmp/qwenwork-general-driver",
    candidate_workspace: WORKSPACE,
    prompt: {
      path: "/private/tmp/qwenwork-general-driver/prompt.md",
      sha256: PROMPT_SHA,
      content: "fixture prompt",
    },
    state_file: "/private/tmp/qwenwork-general-driver/automation-state.json",
    evidence_root: "/private/tmp/qwenwork-general-driver/evidence/qwenwork",
    client: {
      bundle_id: "cn.qwenwork.desktop.mac",
      endpoint: "http://127.0.0.1:9250",
      session_db: "/private/tmp/qwenwork-general-driver/agents.db",
      trace_root: "/private/tmp/qwenwork-general-driver/.qwenworkcn",
    },
    control: {
      desktop_slot_id: "slot-fixture",
      probe_path: "/private/tmp/qwenwork-general-driver/probe.json",
      probe_sha256: "a".repeat(64),
      probe_max_age_seconds: 300,
      model_policy: "keep-current",
      permission_policy: "keep-current",
      create_new_project: true,
      live_execution_authorized: true,
    },
    resume: false,
    ...overrides,
  };
  config.config_digest = calculateQwenCanaryConfigDigest(config);
  return config;
}

function configuration(model = "qwen-model", permission = "default-sandbox") {
  return {
    model: { actual_model: model, changed: false },
    permission: { confirmed_mode: permission, changed: false },
  };
}

function project() {
  return {
    project_id: "project-fixture",
    project_name: "WCB-GEN-fixture",
    confirmed_path: WORKSPACE,
    verification_method: "fixture-sqlite-root-path",
  };
}

function session(id = "session-fixture") {
  return {
    conversation_id: `conversation-${id}`,
    sub_chat_id: `sub-chat-${id}`,
    session_id: id,
    local_project_id: "project-fixture",
    cwd: WORKSPACE,
    native_status: "completed",
    stream_id: null,
    created_at_ms: Date.parse("2026-09-19T10:00:20.000Z"),
    updated_at_ms: Date.parse("2026-09-19T10:00:25.000Z"),
  };
}

function clock() {
  let tick = 0;
  return () => new Date(Date.parse("2026-09-19T10:00:00.000Z") + tick++ * 1_000).toISOString();
}

function fakeLocator(elements) {
  return {
    count: async () => elements.length,
    nth: (index) => elements[index],
  };
}

function fakeElement({ visible = true, text = "", attributes = {} } = {}) {
  return {
    isVisible: async () => visible,
    innerText: async () => text,
    getAttribute: async (name) => attributes[name] ?? null,
  };
}

test("UI locators fail closed on duplicate controls and configuration drift", async () => {
  await assert.rejects(
    requireUniqueVisible(fakeLocator([fakeElement(), fakeElement()]), "send-button"),
    /send-button:2/u,
  );
  const page = {
    locator: (selector) => selector.includes("model-selector")
      ? fakeLocator([fakeElement({ attributes: { title: "Qwen Fixture" } })])
      : fakeLocator([fakeElement({ text: "默认权限" })]),
  };
  const current = await readQwenUiConfiguration(page);
  assert.equal(current.model.actual_model, "Qwen Fixture");
  assert.equal(current.permission.confirmed_mode, "default-sandbox");
  assert.throws(
    () => assertStableQwenUiConfiguration(current, configuration("Other Model", "default-sandbox")),
    /MODEL_DRIFT/u,
  );
  assert.throws(
    () => assertStableQwenUiConfiguration(current, configuration("Qwen Fixture", "full-access")),
    /PERMISSION_DRIFT/u,
  );
});

test("workspace confirmation uses the complete database root path", () => {
  assert.throws(() => confirmQwenWorkspaceProject({
    projects: [{ project_id: "project-fixture", project_name: "same-basename", cwd: "/private/other/workspace" }],
    workspace: WORKSPACE,
  }), /PROJECT_COUNT: 0/u);
  assert.equal(confirmQwenWorkspaceProject({
    projects: [{ project_id: "project-fixture", project_name: "fixture", cwd: WORKSPACE }],
    workspace: WORKSPACE,
  }).confirmed_path, WORKSPACE);
});

test("session prompt binding reads one exact transcript instead of trusting project recency", async () => {
  const root = await mkdtemp(join(tmpdir(), "qwen-general-prompt-evidence-"));
  try {
    const directory = join(root, "projects", "encoded-workspace");
    await mkdir(directory, { recursive: true });
    const text = "exact canary prompt";
    const content = `${JSON.stringify({
      type: "user",
      sessionId: "session-fixture",
      cwd: WORKSPACE,
      message: { content: [{ type: "text", text }] },
    })}\n`;
    await writeFile(join(directory, "session-fixture.jsonl"), content, "utf8");
    const evidence = await verifyQwenSessionPromptEvidence({
      traceRoot: root,
      session: session(),
      prompt: { sha256: createHash("sha256").update(text).digest("hex") },
    });
    assert.equal(evidence.verified, true);
    assert.equal(evidence.match_count, 1);
    await assert.rejects(verifyQwenSessionPromptEvidence({
      traceRoot: root,
      session: session(),
      prompt: { sha256: "0".repeat(64) },
    }), /PROMPT_MATCH_COUNT: 0/u);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("journal persists intent before a single uncertain dispatch reservation", () => {
  const config = makeConfig();
  const state = createQwenAttemptJournal({
    identity: config.identity,
    dataset: config.dataset,
    taskRoot: config.task_root,
    candidateWorkspace: config.candidate_workspace,
    prompt: config.prompt,
    configDigest: config.config_digest,
    now: "2026-09-19T10:00:00.000Z",
  });
  recordQwenDispatchIntent(state, {
    project: project(),
    configuration: configuration(),
    baseline: [],
    now: "2026-09-19T10:00:01.000Z",
  });
  assert.equal(planQwenRecovery(state, "2026-09-19T10:00:02.000Z"), "dispatch-once");
  reserveQwenDispatch(state, { now: "2026-09-19T10:00:03.000Z", reservationId: "reservation-fixture" });
  assert.equal(state.prompt.send_status, "uncertain");
  assert.equal(state.send.dispatch_attempt_count, 1);
  assert.equal(planQwenRecovery(state, "2026-09-19T10:00:04.000Z"), "inspect-only");
  assert.throws(
    () => reserveQwenDispatch(state, { now: "2026-09-19T10:00:05.000Z" }),
    /RESERVATION_INVALID/u,
  );
});

test("fresh driver dispatches once, binds the unique new session, and requires trusted stop evidence", async () => {
  const config = makeConfig();
  let stored = null;
  let dispatches = 0;
  let sessionReads = 0;
  const now = clock();
  const result = await runQwenGeneralAttempt(config, {
    now,
    readJournal: async () => stored,
    writeJournal: async (_path, state) => { stored = structuredClone(state); },
    prepareUi: async () => ({ project: project(), configuration: configuration() }),
    fillPrompt: async () => {},
    verifyPreparedUi: async () => ({ project: project(), configuration: configuration(), prompt_sha256: PROMPT_SHA }),
    dispatchPrompt: async () => { dispatches += 1; return { method: "fixture-click" }; },
    querySessions: async () => (++sessionReads === 1 ? [] : [session()]),
    verifySessionPrompt: async () => ({ verified: true, prompt_sha256: PROMPT_SHA, match_count: 1 }),
    observeUi: async () => ({
      observed_at: now(),
      source: "fixture-db+ui",
      active_stream: false,
      stop_confirmed: true,
      conflicts: [],
    }),
    writeBindingEvidence: async () => [{ path: "evidence/binding.json", sha256: "b".repeat(64), size: 10 }],
  });
  assert.equal(dispatches, 1);
  assert.equal(result.journal.send.dispatch_attempt_count, 1);
  assert.equal(result.journal.session.session_id, "session-fixture");
  assert.equal(result.execution_state.phase, "COMPLETED");
});

test("invoking recovery inspects only and never resends when no session or two sessions exist", async () => {
  const config = makeConfig({ resume: true });
  const state = createQwenAttemptJournal({
    identity: config.identity,
    dataset: config.dataset,
    taskRoot: config.task_root,
    candidateWorkspace: config.candidate_workspace,
    prompt: config.prompt,
    configDigest: config.config_digest,
    now: "2026-09-19T10:00:00.000Z",
  });
  recordQwenDispatchIntent(state, {
    project: project(),
    configuration: configuration(),
    baseline: [],
    now: "2026-09-19T10:00:01.000Z",
  });
  reserveQwenDispatch(state, { now: "2026-09-19T10:00:02.000Z", reservationId: "reservation-fixture" });
  let stored = structuredClone(state);
  let dispatches = 0;
  const dependencies = {
    now: clock(),
    readJournal: async () => structuredClone(stored),
    writeJournal: async (_path, next) => { stored = structuredClone(next); },
    prepareUi: async () => { throw new Error("must not prepare"); },
    verifyPreparedUi: async () => { throw new Error("must not verify"); },
    fillPrompt: async () => { throw new Error("must not fill"); },
    dispatchPrompt: async () => { dispatches += 1; },
    querySessions: async () => [],
    verifySessionPrompt: async () => ({ verified: true, prompt_sha256: PROMPT_SHA, match_count: 1 }),
    observeUi: async () => { throw new Error("must not observe unbound session"); },
    writeBindingEvidence: async () => [],
  };
  const missing = await runQwenGeneralAttempt(config, dependencies);
  assert.equal(missing.journal.phase, "NEEDS_ATTENTION");
  assert.equal(dispatches, 0);

  stored = structuredClone(state);
  dependencies.querySessions = async () => [session("session-a"), session("session-b")];
  const ambiguous = await runQwenGeneralAttempt(config, dependencies);
  assert.equal(ambiguous.journal.phase, "NEEDS_ATTENTION");
  assert.equal(ambiguous.journal.attention.code, "QWENWORK_SESSION_AMBIGUOUS");
  assert.equal(dispatches, 0);

  stored = structuredClone(state);
  dependencies.querySessions = async () => [session()];
  dependencies.verifySessionPrompt = async () => { throw new Error("fixture prompt mismatch"); };
  const wrongPrompt = await runQwenGeneralAttempt(config, dependencies);
  assert.equal(wrongPrompt.journal.attention.code, "QWENWORK_SESSION_PROMPT_UNVERIFIED");
  assert.equal(dispatches, 0);
});

test("same attempt can bind later without resend while a different attempt is rejected", async () => {
  const base = makeConfig({ resume: true });
  const state = createQwenAttemptJournal({
    identity: base.identity,
    dataset: base.dataset,
    taskRoot: base.task_root,
    candidateWorkspace: base.candidate_workspace,
    prompt: base.prompt,
    configDigest: base.config_digest,
    now: "2026-09-19T10:00:00.000Z",
  });
  recordQwenDispatchIntent(state, {
    project: project(),
    configuration: configuration(),
    baseline: [],
    now: "2026-09-19T10:00:01.000Z",
  });
  reserveQwenDispatch(state, { now: "2026-09-19T10:00:02.000Z", reservationId: "reservation-fixture" });
  let stored = structuredClone(state);
  let dispatches = 0;
  const now = clock();
  const result = await runQwenGeneralAttempt(base, {
    now,
    readJournal: async () => structuredClone(stored),
    writeJournal: async (_path, next) => { stored = structuredClone(next); },
    prepareUi: async () => { throw new Error("must not prepare"); },
    verifyPreparedUi: async () => { throw new Error("must not verify"); },
    fillPrompt: async () => { throw new Error("must not fill"); },
    dispatchPrompt: async () => { dispatches += 1; },
    querySessions: async () => [session()],
    verifySessionPrompt: async () => ({ verified: true, prompt_sha256: PROMPT_SHA, match_count: 1 }),
    observeUi: async () => ({ observed_at: now(), source: "fixture", active_stream: false, stop_confirmed: true, conflicts: [] }),
    writeBindingEvidence: async () => [{ path: "evidence/binding.json", sha256: "b".repeat(64), size: 10 }],
  });
  assert.equal(result.execution_state.phase, "COMPLETED");
  assert.equal(dispatches, 0);

  const other = makeConfig({
    resume: true,
    identity: { ...base.identity, attempt_id: "attempt-other" },
  });
  assert.throws(
    () => assertQwenJournalMatches(stored, {
      identity: other.identity,
      dataset: other.dataset,
      candidateWorkspace: other.candidate_workspace,
      prompt: other.prompt,
      configDigest: other.config_digest,
    }),
    /IDENTITY_MISMATCH/u,
  );
});

test("binding helper refuses the wrong project even with a matching cwd", () => {
  const config = makeConfig();
  const state = createQwenAttemptJournal({
    identity: config.identity,
    dataset: config.dataset,
    taskRoot: config.task_root,
    candidateWorkspace: config.candidate_workspace,
    prompt: config.prompt,
    configDigest: config.config_digest,
    now: "2026-09-19T10:00:00.000Z",
  });
  recordQwenDispatchIntent(state, {
    project: project(),
    configuration: configuration(),
    baseline: [],
    now: "2026-09-19T10:00:01.000Z",
  });
  reserveQwenDispatch(state, { now: "2026-09-19T10:00:02.000Z", reservationId: "reservation-fixture" });
  assert.throws(() => confirmQwenDispatchBinding(state, {
    session: { ...session(), local_project_id: "other-project" },
    promptEvidence: { verified: true, prompt_sha256: PROMPT_SHA },
    now: "2026-09-19T10:00:03.000Z",
  }), /PROJECT_MISMATCH/u);
});

test("journal read and write reject symlink leaves and ancestors", async () => {
  const root = await mkdtemp(join(tmpdir(), "qwen-general-journal-symlink-"));
  try {
    const realDirectory = join(root, "real");
    await mkdir(realDirectory);
    const realState = join(realDirectory, "state.json");
    await writeFile(realState, "{}\n", "utf8");
    const linkedState = join(root, "linked-state.json");
    await symlink(realState, linkedState);
    await assert.rejects(readQwenJournal(linkedState), /STATE_SYMLINK_REJECTED/u);

    const linkedDirectory = join(root, "linked-directory");
    await symlink(realDirectory, linkedDirectory);
    await assert.rejects(
      atomicWriteQwenJournal(join(linkedDirectory, "new-state.json"), { fixture: true }),
      /STATE_SYMLINK_REJECTED/u,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("attempt lock keeps two concurrent workers to at most one dispatch", async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "qwen-general-attempt-lock-")));
  try {
    const config = makeConfig({
      state_file: join(root, "automation-state.json"),
      evidence_root: join(root, "evidence"),
    });
    let stored = null;
    let dispatches = 0;
    let releasePreparation;
    let announcePreparation;
    const preparationEntered = new Promise((resolvePromise) => { announcePreparation = resolvePromise; });
    const preparationGate = new Promise((resolvePromise) => { releasePreparation = resolvePromise; });
    const now = clock();
    const dependencies = {
      now,
      readJournal: async () => structuredClone(stored),
      writeJournal: async (_path, state) => { stored = structuredClone(state); },
      prepareUi: async () => {
        announcePreparation();
        await preparationGate;
        return { project: project(), configuration: configuration() };
      },
      fillPrompt: async () => {},
      verifyPreparedUi: async () => ({ project: project(), configuration: configuration(), prompt_sha256: PROMPT_SHA }),
      dispatchPrompt: async () => { dispatches += 1; return { method: "fixture-click" }; },
      querySessions: async () => stored?.send?.dispatch_attempt_count === 1 ? [session()] : [],
      verifySessionPrompt: async () => ({ verified: true, prompt_sha256: PROMPT_SHA, match_count: 1 }),
      observeUi: async () => ({ observed_at: now(), source: "fixture", active_stream: false, stop_confirmed: true, conflicts: [] }),
      writeBindingEvidence: async () => [{ path: "evidence/binding.json", sha256: "b".repeat(64), size: 10 }],
    };
    const first = runQwenGeneralAttempt(config, dependencies);
    await preparationEntered;
    const second = runQwenGeneralAttempt(config, dependencies);
    await assert.rejects(second, /ATTEMPT_LOCK_ACTIVE/u);
    releasePreparation();
    const result = await first;
    assert.equal(result.execution_state.phase, "COMPLETED");
    assert.equal(dispatches, 1);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
