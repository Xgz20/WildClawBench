import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  QWENWORK_CANARY_CONFIG_SCHEMA,
  calculateQwenCanaryConfigDigest,
  loadQwenCanaryConfig,
  runQwenGeneralAttempt,
  verifyQwenSessionPromptEvidence,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/driver.mjs";
import {
  applyQwenExecutionProjection,
  assertQwenJournalMatches,
  atomicWriteQwenJournal,
  confirmQwenDispatchBinding,
  createQwenAttemptJournal,
  markQwenDispatchReturned,
  planQwenRecovery,
  recordQwenDispatchIntent,
  reserveQwenDispatch,
  readQwenJournal,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/journal.mjs";
import {
  assertStableQwenUiConfiguration,
  confirmQwenWorkspaceProject,
  ensureQwenNewTaskView,
  inspectQwenTaskUi,
  QWEN_NEW_TASK_SELECTOR,
  QWEN_TASK_VIEW_SELECTOR,
  readQwenUiConfiguration,
  readSelectedQwenProjectName,
  requireUniqueVisible,
  normalizeQwenPromptText,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/ui.mjs";

const SELECT_FOLDER = new URL(
  "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/select-folder.swift",
  import.meta.url,
).pathname;

const WORKSPACE = "/private/tmp/qwenwork-general-driver/workspace";
const PROMPT_SHA = "e".repeat(64);

test("contenteditable prompt readback normalizes macOS paragraph boundaries", () => {
  assert.equal(normalizeQwenPromptText("第一段\n\n\n第二段\r\n\r\n第三段"), "第一段\n\n第二段\n\n第三段");
});

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
  if (config.resume) {
    config.recovery_probe = {
      verified: true,
      path: "/private/tmp/qwenwork-general-driver/resume-probe.json",
      sha256: "f".repeat(64),
      probed_at: "2026-09-19T10:00:00.000Z",
      active_or_pending_count: 1,
    };
  }
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
    sub_chat_name: "Fixture Session",
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

function probeAt(probedAt, activeOrPendingCount = 0) {
  return {
    schema_version: "wildclawbench.general-e2e-qwenwork-readonly-probe/v1",
    probed_at: probedAt,
    driver: { harness: "qwenwork", platform: "macos" },
    app: { bundle_id: "cn.qwenwork.desktop.mac", identity_verified: true },
    ready_for_read_only_mapping: true,
    native_state: {
      database: { quick_check: "ok", active_or_pending_count: activeOrPendingCount },
    },
    operations_performed: ["read-only-app-discovery", "read-only-native-state"],
  };
}

function fakeLocator(elements) {
  return {
    count: async () => elements.length,
    nth: (index) => elements[index],
  };
}

function fakeElement({ visible = true, text = "", attributes = {}, onClick = null } = {}) {
  return {
    isVisible: async () => visible,
    innerText: async () => text,
    getAttribute: async (name) => attributes[name] ?? null,
    click: async () => { if (onClick) await onClick(); },
  };
}

function fakeTaskView(projectControls, { visible = true } = {}) {
  return {
    ...fakeElement({ visible }),
    locator: () => fakeLocator(projectControls),
  };
}

function fakeProjectPage(taskViews) {
  return {
    locator: (selector) => selector === QWEN_TASK_VIEW_SELECTOR
      ? fakeLocator(taskViews)
      : fakeLocator([]),
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

test("project trigger uses current visible task view and exact project semantics", async () => {
  const permission = fakeElement({ text: "选择权限模式", attributes: { "aria-haspopup": "menu" } });
  const workspaceMode = fakeElement({ text: "通用模式", attributes: { "aria-haspopup": "menu" } });
  const selectedProject = fakeElement({ text: "WCB-GEN-fixture", attributes: { "aria-label": "WCB-GEN-fixture", "aria-haspopup": "menu" } });
  const hiddenDuplicate = fakeElement({ visible: false, text: "WCB-GEN-fixture", attributes: { "aria-label": "WCB-GEN-fixture", "aria-haspopup": "menu" } });

  const page = fakeProjectPage([
    fakeTaskView([permission, workspaceMode, selectedProject, hiddenDuplicate]),
    fakeTaskView([fakeElement({ text: "WCB-GEN-fixture", attributes: { "aria-label": "WCB-GEN-fixture", "aria-haspopup": "menu" } })], { visible: false }),
  ]);
  assert.equal(await readSelectedQwenProjectName(page, "WCB-GEN-fixture"), "WCB-GEN-fixture");

  await assert.rejects(
    readSelectedQwenProjectName(fakeProjectPage([
      fakeTaskView([selectedProject, fakeElement({ text: "WCB-GEN-fixture", attributes: { "aria-label": "WCB-GEN-fixture", "aria-haspopup": "menu" } })]),
    ]), "WCB-GEN-fixture"),
    /project-trigger:2/u,
  );
  await assert.rejects(
    readSelectedQwenProjectName(fakeProjectPage([
      fakeTaskView([selectedProject]),
      fakeTaskView([selectedProject]),
    ]), "WCB-GEN-fixture"),
    /task-view:2/u,
  );
});

test("project trigger accepts the semantic empty-project label without confusing workspace or permission menus", async () => {
  const page = fakeProjectPage([fakeTaskView([
    fakeElement({ text: "选择权限模式", attributes: { "aria-label": "选择权限模式", "aria-haspopup": "menu" } }),
    fakeElement({ text: "通用模式", attributes: { "aria-label": "通用模式", "aria-haspopup": "menu" } }),
    fakeElement({ text: "选择项目", attributes: { "aria-label": "选择项目", "aria-haspopup": "menu" } }),
  ])]);
  assert.equal(await readSelectedQwenProjectName(page), "选择项目");
});

test("completed conversation route navigates through the unique new-task control", async () => {
  const projectControls = [];
  const selectedProject = fakeElement({
    text: "选择项目",
    attributes: { "aria-label": "选择项目", "aria-haspopup": "menu" },
  });
  let clickCount = 0;
  const newTask = fakeElement({
    attributes: { "aria-label": "新任务" },
    onClick: () => {
      clickCount += 1;
      projectControls.push(selectedProject);
    },
  });
  const taskView = fakeTaskView(projectControls);
  const page = {
    locator: (selector) => {
      if (selector === QWEN_TASK_VIEW_SELECTOR) return fakeLocator([taskView]);
      if (selector === QWEN_NEW_TASK_SELECTOR) return fakeLocator([newTask]);
      return fakeLocator([]);
    },
  };

  const result = await ensureQwenNewTaskView(page, 100);
  assert.equal(result, selectedProject);
  assert.equal(clickCount, 1);
});

test("terminal UI observation binds the visible chat and unique sub-chat before confirming stop", async () => {
  const target = session();
  const page = {
    url: () => `file:///qwenwork/index.html?windowId=main&chat=${target.conversation_id}`,
    title: async () => target.sub_chat_name,
    locator: (selector) => selector === QWEN_TASK_VIEW_SELECTOR
      ? fakeLocator([fakeElement()])
      : fakeLocator([]),
  };
  const exact = await inspectQwenTaskUi(page, "2026-09-19T10:00:30.000Z", target, [target]);
  assert.equal(exact.target_session_verified, true);
  assert.equal(exact.stop_confirmed, true);
  assert.equal(exact.active_stream, false);
  assert.equal(exact.ui_binding.session_id, target.session_id);

  const wrongPage = {
    ...page,
    url: () => "file:///qwenwork/index.html?windowId=main",
    title: async () => "",
  };
  const unbound = await inspectQwenTaskUi(wrongPage, "2026-09-19T10:00:31.000Z", target, [target]);
  assert.equal(unbound.target_session_verified, false);
  assert.equal(unbound.stop_confirmed, false);
  assert.equal(unbound.active_stream, null);
  assert.ok(unbound.conflicts.some((value) => value.startsWith("ui-conversation-mismatch:")));

  const emptyDom = await inspectQwenTaskUi({
    ...page,
    locator: () => fakeLocator([]),
  }, "2026-09-19T10:00:31.500Z", target, [target]);
  assert.equal(emptyDom.target_session_verified, false);
  assert.equal(emptyDom.stop_confirmed, false);
  assert.equal(emptyDom.active_stream, null);
  assert.ok(emptyDom.conflicts.includes("ui-task-view-count:0"));

  const duplicateName = await inspectQwenTaskUi(page, "2026-09-19T10:00:32.000Z", target, [
    target,
    { ...session("session-other"), conversation_id: target.conversation_id },
  ]);
  assert.equal(duplicateName.target_session_verified, false);
  assert.equal(duplicateName.stop_confirmed, false);
  assert.ok(duplicateName.conflicts.includes("ui-sub-chat-identity-count:2"));
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

test("resume uses a distinct fresh read-only probe without changing the frozen config digest", async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "qwen-general-resume-probe-")));
  try {
    const workspace = join(root, "workspace");
    const promptPath = join(root, "prompt.md");
    const frozenProbePath = join(root, "probe-initial.json");
    const resumeProbePath = join(root, "probe-resume.json");
    const configPath = join(root, "config.json");
    await mkdir(workspace);
    const prompt = "fixture prompt";
    await writeFile(promptPath, prompt, "utf8");
    const oldTime = new Date(Date.now() - 60 * 60 * 1_000).toISOString();
    const currentTime = new Date().toISOString();
    const frozenProbe = `${JSON.stringify(probeAt(oldTime), null, 2)}\n`;
    const resumeProbe = `${JSON.stringify(probeAt(currentTime, 1), null, 2)}\n`;
    await writeFile(frozenProbePath, frozenProbe, "utf8");
    await writeFile(resumeProbePath, resumeProbe, "utf8");

    const config = makeConfig();
    config.task_root = root;
    config.candidate_workspace = workspace;
    config.prompt = {
      path: promptPath,
      sha256: createHash("sha256").update(prompt).digest("hex"),
    };
    config.state_file = join(root, "automation-state.json");
    config.evidence_root = join(root, "evidence");
    config.client = {
      ...config.client,
      session_db: join(root, "agents.db"),
      trace_root: join(root, "trace"),
    };
    config.control = {
      ...config.control,
      probe_path: frozenProbePath,
      probe_sha256: createHash("sha256").update(frozenProbe).digest("hex"),
    };
    config.config_digest = calculateQwenCanaryConfigDigest(config);
    const frozenDigest = config.config_digest;
    await writeFile(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");

    await assert.rejects(loadQwenCanaryConfig(configPath), /PROBE_STALE/u);
    const loaded = await loadQwenCanaryConfig(configPath, {
      resume: true,
      resumeProbePath,
      resumeProbeSha256: createHash("sha256").update(resumeProbe).digest("hex"),
    });
    assert.equal(loaded.config_digest, frozenDigest);
    assert.equal(loaded.recovery_probe.verified, true);
    assert.equal(loaded.recovery_probe.active_or_pending_count, 1);
    assert.equal(calculateQwenCanaryConfigDigest(loaded), frozenDigest);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("terminal journal replay returns the persisted execution projection without observing or resending", async () => {
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
  markQwenDispatchReturned(state, { now: "2026-09-19T10:00:03.000Z", method: "fixture-click" });
  confirmQwenDispatchBinding(state, {
    session: session(),
    promptEvidence: { verified: true, prompt_sha256: PROMPT_SHA },
    now: "2026-09-19T10:00:04.000Z",
  });
  const projection = {
    identity: config.identity,
    phase: "COMPLETED",
    send: { dispatch_attempt_count: 1 },
    execution: { business_status: "completed" },
  };
  applyQwenExecutionProjection(state, projection, "2026-09-19T10:00:05.000Z");
  let stored = structuredClone(state);
  const forbidden = async () => { throw new Error("terminal replay must not perform live work"); };
  const result = await runQwenGeneralAttempt(config, {
    withAttemptLock: async (_config, operation) => operation(),
    now: clock(),
    readJournal: async () => structuredClone(stored),
    writeJournal: async (_path, next) => { stored = structuredClone(next); },
    prepareUi: forbidden,
    verifyPreparedUi: forbidden,
    fillPrompt: forbidden,
    dispatchPrompt: forbidden,
    querySessions: forbidden,
    verifySessionPrompt: forbidden,
    observeUi: forbidden,
    writeBindingEvidence: forbidden,
  });
  assert.deepEqual(result.execution_state, projection);
  assert.equal(result.journal.phase, "COMPLETED");
  assert.equal(result.journal.recovery.last_readonly_probe.sha256, config.recovery_probe.sha256);
});

test("native folder picker only operates on the QwenWork AX sheet subtree", async () => {
  const source = await readFile(SELECT_FOLDER, "utf8");
  for (const forbidden of [
    "openAndSavePanelService",
    "currentOpenPanel",
    "postShortcutGlobally",
    "panelFrameMatchesOwner",
  ]) {
    assert.doesNotMatch(source, new RegExp(forbidden, "u"));
  }
  assert.match(source, /descendants\(outerSheet, role:/u);
  assert.match(source, /postShortcut\(processIdentifier: application\.processIdentifier/u);
  assert.match(source, /qwen-application-ax-sheet-descendant-only/u);
});

test("a lost bound session clears a stale RUNNING projection and can complete on the next resume", async () => {
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
  markQwenDispatchReturned(state, { now: "2026-09-19T10:00:03.000Z", method: "fixture-click" });
  confirmQwenDispatchBinding(state, {
    session: session(),
    promptEvidence: { verified: true, prompt_sha256: PROMPT_SHA },
    now: "2026-09-19T10:00:04.000Z",
  });
  applyQwenExecutionProjection(state, {
    identity: config.identity,
    phase: "RUNNING",
    send: { dispatch_attempt_count: 1 },
    execution: { business_status: null },
  }, "2026-09-19T10:00:05.000Z");

  let stored = structuredClone(state);
  let visibleSessions = [];
  let dispatches = 0;
  const now = clock();
  const dependencies = {
    withAttemptLock: async (_config, operation) => operation(),
    now,
    readJournal: async () => structuredClone(stored),
    writeJournal: async (_path, next) => { stored = structuredClone(next); },
    prepareUi: async () => { throw new Error("must not prepare"); },
    verifyPreparedUi: async () => { throw new Error("must not verify prepared UI"); },
    fillPrompt: async () => { throw new Error("must not fill"); },
    dispatchPrompt: async () => { dispatches += 1; },
    querySessions: async () => visibleSessions,
    verifySessionPrompt: async () => { throw new Error("must not rebind prompt"); },
    observeUi: async () => ({
      observed_at: now(),
      source: "fixture",
      target_session_verified: true,
      active_stream: false,
      stop_confirmed: true,
      conflicts: [],
    }),
    writeBindingEvidence: async () => [
      { path: "evidence/binding.json", sha256: "b".repeat(64), size: 10 },
    ],
  };

  const missing = await runQwenGeneralAttempt(config, dependencies);
  assert.equal(missing.journal.phase, "NEEDS_ATTENTION");
  assert.equal(missing.journal.execution_state, null);
  assert.equal(dispatches, 0);

  visibleSessions = [session()];
  const completed = await runQwenGeneralAttempt(config, dependencies);
  assert.equal(completed.journal.phase, "COMPLETED");
  assert.equal(completed.execution_state.phase, "COMPLETED");
  assert.equal(dispatches, 0);
});

test("PREPARING resume requires an idle recovery probe before any UI work", async () => {
  const config = makeConfig({ resume: true });
  let stored = createQwenAttemptJournal({
    identity: config.identity,
    dataset: config.dataset,
    taskRoot: config.task_root,
    candidateWorkspace: config.candidate_workspace,
    prompt: config.prompt,
    configDigest: config.config_digest,
    now: "2026-09-19T10:00:00.000Z",
  });
  const calls = {
    prepare: 0,
    verify: 0,
    fill: 0,
    dispatch: 0,
    query: 0,
    prompt: 0,
    observe: 0,
    binding: 0,
  };
  const counted = (name, value = undefined) => async () => {
    calls[name] += 1;
    return value;
  };
  const result = await runQwenGeneralAttempt(config, {
    withAttemptLock: async (_config, operation) => operation(),
    now: clock(),
    readJournal: async () => structuredClone(stored),
    writeJournal: async (_path, next) => { stored = structuredClone(next); },
    prepareUi: counted("prepare"),
    verifyPreparedUi: counted("verify"),
    fillPrompt: counted("fill"),
    dispatchPrompt: counted("dispatch"),
    querySessions: counted("query", []),
    verifySessionPrompt: counted("prompt"),
    observeUi: counted("observe"),
    writeBindingEvidence: counted("binding", []),
  });
  assert.equal(result.journal.phase, "NEEDS_ATTENTION");
  assert.equal(result.journal.attention.code, "QWENWORK_RECOVERY_PROBE_NOT_IDLE_FOR_UNSENT_ATTEMPT");
  assert.deepEqual(calls, {
    prepare: 0,
    verify: 0,
    fill: 0,
    dispatch: 0,
    query: 0,
    prompt: 0,
    observe: 0,
    binding: 0,
  });
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
      target_session_verified: true,
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
    observeUi: async () => ({ observed_at: now(), source: "fixture", target_session_verified: true, active_stream: false, stop_confirmed: true, conflicts: [] }),
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
      observeUi: async () => ({ observed_at: now(), source: "fixture", target_session_verified: true, active_stream: false, stop_confirmed: true, conflicts: [] }),
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

test("two workers refuse the same stale lock instead of racing to replace a new owner", async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "qwen-general-stale-lock-")));
  try {
    const config = makeConfig({
      state_file: join(root, "automation-state.json"),
      evidence_root: join(root, "evidence"),
    });
    const lockPath = `${config.state_file}.lock`;
    const staleOwner = {
      schema_version: "wildclawbench.general-e2e-qwenwork-attempt-lock/v1",
      owner_id: "stale-owner-fixture",
      attempt_id: config.identity.attempt_id,
      host: hostname(),
      pid: 99_999_999,
      process_start_identity: "stale-process-fixture",
      acquired_at: "2026-09-19T09:00:00.000Z",
      driver_version: "0.1.1",
      state_file: config.state_file,
    };
    await writeFile(lockPath, `${JSON.stringify(staleOwner, null, 2)}\n`, "utf8");
    let dispatches = 0;
    const dependencies = {
      prepareUi: async () => ({ project: project(), configuration: configuration() }),
      verifyPreparedUi: async () => ({ project: project(), configuration: configuration(), prompt_sha256: PROMPT_SHA }),
      fillPrompt: async () => {},
      dispatchPrompt: async () => { dispatches += 1; },
      querySessions: async () => [],
      verifySessionPrompt: async () => ({ verified: true, prompt_sha256: PROMPT_SHA }),
      observeUi: async () => ({ target_session_verified: true, active_stream: false, stop_confirmed: true, conflicts: [] }),
      writeBindingEvidence: async () => [],
    };
    const results = await Promise.allSettled([
      runQwenGeneralAttempt(config, dependencies),
      runQwenGeneralAttempt(config, dependencies),
    ]);
    assert.equal(results.filter((result) => result.status === "rejected").length, 2);
    assert.ok(results.every((result) => (
      result.status === "rejected"
      && /LOCK_STALE_REQUIRES_CONTROLLED_RECOVERY/u.test(String(result.reason?.message))
    )));
    assert.equal(dispatches, 0);
    assert.equal(JSON.parse(await readFile(lockPath, "utf8")).owner_id, staleOwner.owner_id);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
