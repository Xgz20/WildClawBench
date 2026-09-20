import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import test from "node:test";

import {
  executeWorkBuddyTask,
  closeWorkBuddyUiHandle,
  main,
  parseArgs,
  resolveExecutionConfig,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/execute.mjs";
import {
  assertWorkBuddyRuntimeSupport,
  assertWorkBuddyUiConfiguration,
  assertWorkBuddyUiIdle,
  fillWorkBuddyPrompt,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/ui.mjs";

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function createExecutionUnit() {
  let root = await mkdtemp(join(tmpdir(), "workbuddy-execution-test-"));
  root = await realpath(root);
  const taskId = "fixture-task";
  const taskRoot = join(root, "execution", "tasks", taskId);
  const workspace = join(taskRoot, "workspace");
  const promptPath = join(taskRoot, "prompt.md");
  const prompt = "Create the P2 fixture output.\n";
  await mkdir(workspace, { recursive: true });
  await writeFile(promptPath, prompt, "utf8");
  await writeFile(join(root, "manifest.json"), `${JSON.stringify({
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1",
    manifest_kind: "execution",
    batch_id: "fixture-batch",
    unit_id: "fixture-unit",
    task_ids: [taskId],
    dataset: { id: "fixture-dataset", digest: "d".repeat(64) },
    unit: {
      harness: { id: "workbuddy", platform: "macos", version: "5.5.3" },
      model: { requested_id: "fixture-model", reasoning_effort: null },
      execution_mode: "automated",
    },
    tasks: [{
      task_id: taskId,
      timeout_seconds: 60,
      prompt: { path: `execution/tasks/${taskId}/prompt.md`, sent_sha256: sha256(prompt) },
      workspace: { path: `execution/tasks/${taskId}/workspace` },
    }],
  }, null, 2)}\n`);
  const args = [
    "--unit-root", root,
    "--task-id", taskId,
    "--endpoint", "http://127.0.0.1:9229",
    "--expected-permission", "full-access",
    "--detach-after-submit",
  ];
  const parsed = parseArgs(args);
  const config = await resolveExecutionConfig(parsed);
  return { root, taskId, taskRoot, workspace: await realpath(workspace), prompt, config, args };
}

function runtime() {
  return {
    application: {
      path: "/Applications/WorkBuddy.app",
      version: "5.5.3",
      installation_variant: "workbuddy-macos-electron",
    },
    captured_at: "2026-09-19T08:00:00.000Z",
    native_sources: {
      session_index: {
        status: "observed",
        metadata: { size: 123, modified_at: "2026-09-19T07:59:59.000Z" },
        sessions: [],
      },
    },
  };
}

function rawUi(workspace) {
  return {
    workspace_picker_count: 1,
    workspace_provider_count: 1,
    workspace_path: workspace,
    model_count: 1,
    model: "fixture-model",
    permission_count: 1,
    permission: "full-access",
    editor_count: 1,
    editor_nonempty_count: 0,
    busy_control_count: 0,
    selected_conversation_id: null,
  };
}

function binding(config, state = "running") {
  const completed = state === "complete";
  return {
    session_snapshot: {
      conversation_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      cwd: config.candidateWorkspace,
      status: completed ? "Completed" : "Running",
    },
    history: {
      binding: {
        conversation_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        request_id: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        request_state: { raw: state },
        workspace_history_key: "c".repeat(32),
      },
      prompt: { content: config.prompt, sha256: config.promptSha256 },
      completeness: completed ? { status: "complete", missing: [] } : { status: "partial", missing: ["final_response"] },
      final_response: completed ? "fixture complete" : null,
      request: { startedAt: Date.parse("2026-09-19T08:00:00.000Z") },
      conversation: { lastMessageAt: "2026-09-19T08:00:04.000Z" },
      resources: null,
    },
    artifacts: [{ path: "/fixture/index.json", sha256: "a".repeat(64), size: 123 }],
  };
}

function dependencies(config, counters, selectedBinding) {
  let clock = Date.parse("2026-09-19T08:00:00.000Z");
  return {
    inspectRuntime: async () => runtime(),
    prepareUi: async () => {
      counters.prepare += 1;
      return {
        handle: { fixture: true },
        ui: rawUi(config.candidateWorkspace),
        ui_idle: { verified: true, editor_count: 1, editor_nonempty_count: 0, busy_control_count: 0 },
      };
    },
    fillPrompt: async (_handle, prompt) => {
      counters.fill += 1;
      assert.equal(prompt, config.prompt);
    },
    dispatchPrompt: async () => {
      counters.dispatch += 1;
      return { selected_conversation_id: null };
    },
    snapshotBaseline: async () => ({ workspace: config.candidateWorkspace, sessions: [], request_ids: {} }),
    selectBinding: async () => ({ binding: selectedBinding(), ambiguous: false, match_count: 1 }),
    closeUi: async () => { counters.close += 1; },
    sleep: async () => {},
    now: () => new Date(clock += 1_000).toISOString(),
    nowMilliseconds: () => clock,
  };
}

test("WorkBuddy P2 arguments and UI readback fail closed", () => {
  assert.throws(
    () => parseArgs(["--unit-root", "/tmp/u", "--task-id", "t", "--endpoint", "http://example.com:9229", "--expected-permission", "full-access"]),
    /loopback/u,
  );
  assert.throws(
    () => assertWorkBuddyUiConfiguration({ ...rawUi("/workspace"), model_count: 2 }, {
      workspace: "/workspace",
      model: "fixture-model",
      permission: "full-access",
    }),
    /model/u,
  );
  assert.throws(
    () => assertWorkBuddyRuntimeSupport({
      nodeVersion: "20.18.0",
      fetchImpl: () => {},
      WebSocketImpl: class {},
      abortSignalTimeout: () => {},
    }),
    /Node\.js >=22/u,
  );
  assert.throws(
    () => assertWorkBuddyUiIdle({ ...rawUi("/workspace"), busy_control_count: 1 }),
    /活动或未知交互/u,
  );
});

test("WorkBuddy P2 uses CDP real input and requires an enabled send control", async () => {
  class StatefulEditorClient {
    constructor({ enableOnInsert }) {
      this.content = "";
      this.focused = false;
      this.sendEnabled = false;
      this.enableOnInsert = enableOnInsert;
      this.insertCalls = 0;
    }

    async evaluate(source) {
      if (source.includes("document.activeElement === editor")) {
        this.focused = true;
        return { focused: true, count: 1, initial_content: this.content };
      }
      if (source.includes("new InputEvent('input'")) {
        return { dispatched: true, count: 1 };
      }
      if (source.includes("send_enabled_count")) {
        return {
          editor_count: 1,
          content: this.content,
          send_control_count: 1,
          send_enabled_count: this.sendEnabled ? 1 : 0,
        };
      }
      throw new Error("unexpected evaluate expression");
    }

    async send(method, params) {
      assert.equal(method, "Input.insertText");
      assert.equal(this.focused, true);
      this.insertCalls += 1;
      this.content = params.text;
      this.sendEnabled = this.enableOnInsert;
      return {};
    }
  }

  const prompt = "Stateful editor fixture\n";
  const enabled = new StatefulEditorClient({ enableOnInsert: true });
  const ready = await fillWorkBuddyPrompt(enabled, prompt, 20);
  assert.equal(enabled.insertCalls, 1);
  assert.equal(ready.content, prompt);
  assert.equal(ready.send_enabled_count, 1);

  const domOnly = new StatefulEditorClient({ enableOnInsert: false });
  await assert.rejects(
    fillWorkBuddyPrompt(domOnly, prompt, 5),
    /发送控件启用超时/u,
  );
  assert.equal(domOnly.content, prompt);
  assert.equal(domOnly.sendEnabled, false);
  assert.equal(domOnly.insertCalls, 1);
});

test("WorkBuddy P2 keeps a disabled send control before dispatch arming", async () => {
  const fixture = await createExecutionUnit();
  try {
    const counters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const deps = dependencies(fixture.config, counters, () => binding(fixture.config, "running"));
    deps.fillPrompt = async () => {
      counters.fill += 1;
      throw new Error("等待 WorkBuddy Prompt 真实输入和发送控件启用超时");
    };
    const result = await executeWorkBuddyTask(fixture.config, deps);
    assert.equal(counters.fill, 1);
    assert.equal(counters.dispatch, 0);
    assert.equal(result.journal.send.dispatch_attempt_count, 0);
    assert.equal(result.journal.prompt.send_status, "not_sent");
    assert.equal(result.journal.phase, "FAILED");
    assert.equal(result.journal.execution.error.code, "WORKBUDDY_PRE_SEND_DRIVER_ERROR");
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 accepts synchronous default UI cleanup", async () => {
  const fixture = await createExecutionUnit();
  try {
    let closed = 0;
    const counters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const deps = dependencies(fixture.config, counters, () => binding(fixture.config, "running"));
    deps.prepareUi = async () => ({
      handle: { close: () => { closed += 1; } },
      ui: rawUi(fixture.config.candidateWorkspace),
      ui_idle: { verified: true, editor_count: 1, editor_nonempty_count: 0, busy_control_count: 0 },
    });
    delete deps.closeUi;
    const result = await executeWorkBuddyTask(fixture.config, deps);
    assert.equal(result.state.phase, "RUNNING");
    assert.equal(closed, 1);
    await closeWorkBuddyUiHandle(null);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 rejects conflicting native sessions before UI preparation", async () => {
  const fixture = await createExecutionUnit();
  try {
    const counters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const deps = dependencies(fixture.config, counters, () => binding(fixture.config, "running"));
    deps.inspectRuntime = async () => ({
      ...runtime(),
      native_sources: {
        session_index: {
          status: "observed",
          metadata: { size: 123, modified_at: "2026-09-19T07:59:59.000Z" },
          sessions: [{ status: "Pending" }],
        },
      },
    });
    await assert.rejects(executeWorkBuddyTask(fixture.config, deps), /活动或未知原生 session/u);
    assert.equal(counters.prepare, 0);
    assert.equal(counters.dispatch, 0);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 persists intent before exactly one dispatch and binds native IDs", async () => {
  const fixture = await createExecutionUnit();
  try {
    const counters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const result = await executeWorkBuddyTask(
      fixture.config,
      dependencies(fixture.config, counters, () => binding(fixture.config, "running")),
    );
    assert.equal(counters.prepare, 1);
    assert.equal(counters.fill, 1);
    assert.equal(counters.dispatch, 1);
    assert.equal(counters.close, 1);
    assert.equal(result.journal.send.dispatch_attempt_count, 1);
    assert.equal(result.journal.prompt.send_status, "sent");
    assert.equal(result.journal.native.conversation_id, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    assert.equal(result.journal.native.request_id, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    assert.equal(result.state.phase, "RUNNING");
    assert.equal(result.state.session.thread_id, null);
    assert.equal(result.state.session.turn_id, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    const persisted = JSON.parse(await readFile(fixture.config.journalFile, "utf8"));
    const armedIndex = persisted.history.findIndex((item) => item.event === "PROMPT_DISPATCH_ARMED");
    const returnedIndex = persisted.history.findIndex((item) => item.event === "PROMPT_DISPATCH_RETURNED");
    assert.equal(armedIndex >= 0 && returnedIndex > armedIndex, true);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 resume observes the same attempt without redispatch", async () => {
  const fixture = await createExecutionUnit();
  try {
    const firstCounters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const first = await executeWorkBuddyTask(
      fixture.config,
      dependencies(fixture.config, firstCounters, () => binding(fixture.config, "running")),
    );
    const attemptId = first.journal.identity.attempt_id;
    const resumedConfig = { ...fixture.config, resume: true, detachAfterSubmit: false, observeOnce: true };
    const resumedCounters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const resumed = await executeWorkBuddyTask(
      resumedConfig,
      dependencies(resumedConfig, resumedCounters, () => binding(resumedConfig, "complete")),
    );
    assert.equal(resumed.journal.identity.attempt_id, attemptId);
    assert.equal(resumedCounters.prepare, 0);
    assert.equal(resumedCounters.fill, 0);
    assert.equal(resumedCounters.dispatch, 0);
    assert.equal(resumed.state.phase, "COMPLETED");
    assert.equal(resumed.journal.send.dispatch_attempt_count, 1);
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
        cwd: resolve(dirname(new URL(import.meta.url).pathname), "../.."),
        encoding: "utf8",
        input: JSON.stringify({ state: resumed.state, root: fixture.root, manifest: fixture.config.manifest }),
      },
    );
    assert.equal(validation.status, 0, validation.stderr);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 treats a dispatch exception as uncertain and never retries the click", async () => {
  const fixture = await createExecutionUnit();
  try {
    const counters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const deps = dependencies(fixture.config, counters, () => binding(fixture.config, "running"));
    deps.dispatchPrompt = async () => {
      counters.dispatch += 1;
      throw new Error("socket closed after click boundary");
    };
    const result = await executeWorkBuddyTask(fixture.config, deps);
    assert.equal(counters.dispatch, 1);
    assert.equal(result.journal.send.dispatch_attempt_count, 1);
    assert.equal(result.journal.native.conversation_id, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    assert.equal(result.journal.history.some((item) => item.event === "PROMPT_DISPATCH_THROWN"), true);
    assert.equal(result.state.phase, "RUNNING");
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 owner lock limits two concurrent workers to one dispatch", async () => {
  const fixture = await createExecutionUnit();
  try {
    const counters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const deps = dependencies(fixture.config, counters, () => binding(fixture.config, "running"));
    let releasePrepare;
    const gate = new Promise((resolveGate) => { releasePrepare = resolveGate; });
    let signalStarted;
    const started = new Promise((resolveStarted) => { signalStarted = resolveStarted; });
    const originalPrepare = deps.prepareUi;
    deps.prepareUi = async (...args) => {
      signalStarted();
      await gate;
      return originalPrepare(...args);
    };

    const sink = { write: () => {} };
    const first = main(fixture.args, { allowNonDarwin: true, dependencies: deps, stdout: sink, stderr: sink });
    await started;
    const lock = JSON.parse(await readFile(fixture.config.uiLockFile, "utf8"));
    assert.equal(lock.pid, process.pid);
    assert.equal(typeof lock.host, "string");
    assert.equal(typeof lock.process_started_at, "string");
    assert.equal(typeof lock.process_start_identity, "string");

    const secondCode = await main(fixture.args, {
      allowNonDarwin: true,
      dependencies: deps,
      stdout: sink,
      stderr: sink,
    });
    releasePrepare();
    const firstCode = await first;
    assert.equal(firstCode, 4);
    assert.equal(secondCode, 2);
    assert.equal(counters.dispatch, 1);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 refuses two concurrent stale-lock reclaimers without dispatch", async () => {
  const fixture = await createExecutionUnit();
  try {
    const staleOwner = {
      pid: 2_147_483_647,
      host: hostname(),
      owner_token: "stale-owner",
      process_start_identity: "stale-process",
    };
    await writeFile(fixture.config.uiLockFile, `${JSON.stringify(staleOwner)}\n`, "utf8");
    const counters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    const deps = dependencies(fixture.config, counters, () => binding(fixture.config, "running"));
    const sink = { write: () => {} };
    const args = [...fixture.args, "--resume"];
    const codes = await Promise.all([
      main(args, { allowNonDarwin: true, dependencies: deps, stdout: sink, stderr: sink }),
      main(args, { allowNonDarwin: true, dependencies: deps, stdout: sink, stderr: sink }),
    ]);
    assert.deepEqual(codes, [2, 2]);
    assert.equal(counters.prepare, 0);
    assert.equal(counters.dispatch, 0);
    assert.deepEqual(JSON.parse(await readFile(fixture.config.uiLockFile, "utf8")), staleOwner);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 rejects escaped and symlinked manifest task paths before UI preparation", async () => {
  const escapedFixture = await createExecutionUnit();
  const externalRoot = await mkdtemp(join(tmpdir(), "workbuddy-external-task-"));
  try {
    const externalWorkspace = join(externalRoot, "workspace");
    const externalPrompt = join(externalRoot, "prompt.md");
    await mkdir(externalWorkspace);
    await writeFile(externalPrompt, escapedFixture.prompt, "utf8");
    const manifestPath = join(escapedFixture.root, "manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    manifest.tasks[0].prompt.path = relative(escapedFixture.root, externalPrompt);
    manifest.tasks[0].workspace.path = relative(escapedFixture.root, externalWorkspace);
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    await assert.rejects(
      resolveExecutionConfig(parseArgs(escapedFixture.args)),
      /不含 \.\.|越出 unit root/u,
    );
  } finally {
    await rm(escapedFixture.root, { recursive: true, force: true });
    await rm(externalRoot, { recursive: true, force: true });
  }

  const symlinkFixture = await createExecutionUnit();
  try {
    const externalWorkspace = join(symlinkFixture.root, "external-workspace");
    await mkdir(externalWorkspace);
    await rm(join(symlinkFixture.taskRoot, "workspace"), { recursive: true, force: true });
    await symlink(externalWorkspace, join(symlinkFixture.taskRoot, "workspace"));
    await assert.rejects(
      resolveExecutionConfig(parseArgs(symlinkFixture.args)),
      /符号链接/u,
    );
  } finally {
    await rm(symlinkFixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 rejects symlinked state leaves and ancestors", async () => {
  const leafFixture = await createExecutionUnit();
  try {
    const external = join(leafFixture.root, "external-journal.json");
    await writeFile(external, "{}\n");
    await symlink(external, leafFixture.config.journalFile);
    const counters = { prepare: 0, fill: 0, dispatch: 0, close: 0 };
    await assert.rejects(
      executeWorkBuddyTask(
        leafFixture.config,
        dependencies(leafFixture.config, counters, () => binding(leafFixture.config, "running")),
      ),
      /符号链接/u,
    );
    assert.equal(counters.dispatch, 0);
  } finally {
    await rm(leafFixture.root, { recursive: true, force: true });
  }

  const ancestorFixture = await createExecutionUnit();
  try {
    const external = join(ancestorFixture.root, "external-control");
    await mkdir(external);
    await rm(join(ancestorFixture.root, ".general-e2e"), { recursive: true, force: true });
    await symlink(external, join(ancestorFixture.root, ".general-e2e"));
    await assert.rejects(
      resolveExecutionConfig(parseArgs(ancestorFixture.args)),
      /符号链接/u,
    );
  } finally {
    await rm(ancestorFixture.root, { recursive: true, force: true });
  }
});
