import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cp, mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import test from "node:test";

import { workBuddyWorkspaceHistoryKey } from "../../eval_general_e2e/adapters/workbuddy/native-history.mjs";
import { collectWorkBuddyEvidence } from "../../tools/report/skills/general-e2e/collect-general-e2e/drivers/workbuddy/collector.mjs";
import { finalizeGeneralExecution } from "../../tools/report/skills/general-e2e/collect-general-e2e/scripts/finalize_general_execution.mjs";
import { fixtureHook } from "./helpers/general-collection-fixture.mjs";

const REPO_ROOT = resolve(new URL("../..", import.meta.url).pathname);
const FIXTURE_ROOT = join(REPO_ROOT, "tests/general_e2e/fixtures/workbuddy/native-history");
const IDENTITY = Object.freeze({
  batch_id: "fixture-batch",
  unit_id: "fixture-unit",
  task_id: "fixture-task",
  attempt_id: "fixture-attempt",
});
const CONVERSATION_ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const REQUEST_ID = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const PROMPT = "Create the synthetic fixture output.\n";

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function createFixture() {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-collector-test-"));
  const taskRoot = join(root, "execution", "tasks", IDENTITY.task_id);
  const workspace = join(taskRoot, "workspace");
  const promptPath = join(taskRoot, "prompt.md");
  const controlRoot = join(root, ".general-e2e", "execution", IDENTITY.task_id, "workbuddy");
  const historyRoot = join(root, "WorkBuddyExtension", "Data");
  await mkdir(workspace, { recursive: true });
  const canonicalWorkspace = await realpath(workspace);
  const historyDirectory = join(
    historyRoot,
    "account-fixture",
    "VSCode",
    "identity-fixture",
    "history",
    workBuddyWorkspaceHistoryKey(canonicalWorkspace),
  );
  const conversationDirectory = join(historyDirectory, CONVERSATION_ID);
  await mkdir(join(conversationDirectory, "messages"), { recursive: true });
  await mkdir(controlRoot, { recursive: true });
  await writeFile(promptPath, PROMPT, "utf8");
  await writeJson(join(root, "manifest.json"), {
    schema_id: "urn:wildclawbench:schema:general-e2e:package-manifest:v1",
    schema_version: 1,
    manifest_kind: "execution",
    batch_id: IDENTITY.batch_id,
    unit_id: IDENTITY.unit_id,
    dataset: { id: "fixture-dataset", digest: "d".repeat(64) },
    task_ids: [IDENTITY.task_id],
    unit: { harness: { id: "workbuddy", platform: "macos", version: "0.2.0" }, model: { requested_id: "fixture-model", reasoning_effort: null } },
    tasks: [{
      task_id: IDENTITY.task_id,
      workspace: { path: relative(root, workspace) },
      prompt: { path: relative(root, promptPath), sent_sha256: sha256(PROMPT) },
    }],
  });
  await cp(join(FIXTURE_ROOT, "workspace-index.json"), join(historyDirectory, "index.json"));
  await cp(join(FIXTURE_ROOT, "conversation-index.json"), join(conversationDirectory, "index.json"));
  for (const name of [
    "cccccccccccccccccccccccccccccccc.json",
    "dddddddddddddddddddddddddddddddd.json",
    "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee.json",
    "ffffffffffffffffffffffffffffffff.json",
  ]) {
    await cp(join(FIXTURE_ROOT, "messages", name), join(conversationDirectory, "messages", name));
  }
  const bindingPath = join(controlRoot, "native-binding.json");
  const bindingBytes = Buffer.from(JSON.stringify({
    schema_version: "wildclawbench.general-e2e-workbuddy-native-binding/v1",
    identity: IDENTITY,
    workspace: canonicalWorkspace,
    conversation_id: CONVERSATION_ID,
    request_id: REQUEST_ID,
  }) + "\n", "utf8");
  await writeFile(bindingPath, bindingBytes, { mode: 0o600 });
  const promptSha256 = sha256(PROMPT);
  const bindingEvidence = [{
    path: relative(root, bindingPath),
    sha256: sha256(bindingBytes),
    size: bindingBytes.length,
  }];
  const state = {
    schema_version: "wildclawbench.general-e2e-execution-state/v1",
    driver: { id: "workbuddy-macos-general", version: "0.2.0", harness: "workbuddy", platform: "macos" },
    identity: IDENTITY,
    dataset: { id: "fixture-dataset", digest: "d".repeat(64) },
    phase: "COMPLETED",
    task_root: taskRoot,
    candidate_workspace: workspace,
    prompt: { path: promptPath, sha256: promptSha256, send_status: "sent", sent_at: "2026-09-20T00:00:00.000Z" },
    send: { dispatch_attempt_count: 1 },
    session: {
      thread_id: null,
      turn_id: REQUEST_ID,
      session_id: CONVERSATION_ID,
      cwd: canonicalWorkspace,
      verified: true,
      binding_evidence: bindingEvidence,
    },
    execution: {
      business_status: "completed",
      started_at: "2026-09-20T00:00:00.000Z",
      finished_at: "2026-09-20T00:00:04.000Z",
      duration_seconds: 4,
      error: null,
      cancellation_confirmed: null,
    },
    human_assistance: { mode: "automatic", operation_count: 0, semantic_intervention_count: 0 },
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
  const journal = {
    schema_version: "wildclawbench.general-e2e-workbuddy-dispatch-journal/v1",
    dataset: { id: "fixture-dataset", digest: "d".repeat(64) },
    identity: IDENTITY,
    phase: "COMPLETED",
    candidate_workspace: workspace,
    prompt: { sha256: promptSha256, send_status: "sent" },
    send: { dispatch_attempt_count: 1 },
    native: {
      conversation_id: CONVERSATION_ID,
      request_id: REQUEST_ID,
      cwd: canonicalWorkspace,
    },
  };
  const statePath = join(controlRoot, "execution-state.json");
  const journalPath = join(controlRoot, "dispatch-journal.json");
  await writeJson(statePath, state);
  await writeJson(journalPath, journal);
  return { root, historyRoot, outputRoot: join(root, ".general-e2e", "collection", IDENTITY.attempt_id), statePath, journalPath };
}

test("WorkBuddy collector 生成可交给通用 finalizer 的 CB-B 输入", async () => {
  const fixture = await createFixture();
  try {
    const result = await collectWorkBuddyEvidence({
      unitRoot: fixture.root,
      journalFile: fixture.journalPath,
      stateFile: fixture.statePath,
      historyRoot: fixture.historyRoot,
      outputRoot: fixture.outputRoot,
    });
    assert.equal(result.status, "PASS");
    const index = JSON.parse(await readFile(result.trace_index, "utf8"));
    const resource = JSON.parse(await readFile(result.resource_metrics, "utf8"));
    assert.equal(index.schema_version, 2);
    assert.equal(index.identity.attempt_id, IDENTITY.attempt_id);
    assert.equal(index.session.session_id, CONVERSATION_ID);
    assert.equal(index.session.turn_id, REQUEST_ID);
    assert.equal(index.completeness.status, "complete");
    assert.ok(index.raw_trace.length >= 2);
    assert.equal(resource.collection.sources[0].path, "execution/automation-state.json");
    assert.equal(resource.collection.sources[1].path, "trace/trace-index.json");
    assert.ok(resource.collection.metric_sources.total_tokens[0].startsWith("trace/"));
    const collectedState = JSON.parse(await readFile(result.state_file, "utf8"));
    const reply = await readFile(join(fixture.root, collectedState.extensions.evidence.final_response_path));
    assert.equal(sha256(reply), collectedState.extensions.evidence.final_response_sha256);
    assert.ok(reply.length > 0);
    await assert.rejects(() => collectWorkBuddyEvidence({
      unitRoot: fixture.root,
      journalFile: fixture.journalPath,
      stateFile: fixture.statePath,
      historyRoot: fixture.historyRoot,
      outputRoot: fixture.outputRoot,
    }), /OUTPUT_EXISTS/u);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy collector 对 Prompt digest 和终态失败关闭", async () => {
  const fixture = await createFixture();
  try {
    const state = JSON.parse(await readFile(fixture.statePath, "utf8"));
    state.prompt.sha256 = "0".repeat(64);
    await writeJson(fixture.statePath, state);
    const journal = JSON.parse(await readFile(fixture.journalPath, "utf8"));
    journal.prompt.sha256 = state.prompt.sha256;
    await writeJson(fixture.journalPath, journal);
    await assert.rejects(() => collectWorkBuddyEvidence({
      unitRoot: fixture.root,
      journalFile: fixture.journalPath,
      stateFile: fixture.statePath,
      historyRoot: fixture.historyRoot,
      outputRoot: fixture.outputRoot,
    }), /PROMPT_DIGEST_MISMATCH/u);
    assert.equal(await readFile(fixture.outputRoot).catch((error) => error.code), "ENOENT");
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy collector 输出通过通用 finalizer 输入与正式收口", async () => {
  const fixture = await createFixture();
  try {
    const collected = await collectWorkBuddyEvidence({
      unitRoot: fixture.root,
      journalFile: fixture.journalPath,
      stateFile: fixture.statePath,
      historyRoot: fixture.historyRoot,
      outputRoot: fixture.outputRoot,
    });
    const result = await finalizeGeneralExecution({
      unitRoot: fixture.root,
      stateFile: collected.state_file,
      traceIndex: collected.trace_index,
      resourceMetrics: collected.resource_metrics,
      pythonExecutable: process.env.PYTHON || "python3",
      stabilityMilliseconds: 1,
      processQuietMilliseconds: 5,
      processWaitMilliseconds: 50,
    }, { processCleanup: fixtureHook("workbuddy") });
    assert.equal(result.status, "PASS");
    assert.equal(result.receipt_status, "completed");
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});
