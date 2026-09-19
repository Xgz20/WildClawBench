import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cp, mkdir, mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";

import {
  selectWorkBuddyNativeBinding,
  snapshotWorkBuddyNativeBaseline,
} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/native-binding.mjs";

const REPO_ROOT = resolve(dirname(new URL(import.meta.url).pathname), "../..");
const FIXTURE_ROOT = join(REPO_ROOT, "tests/general_e2e/fixtures/workbuddy/native-history");
const CONVERSATION_ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const REQUEST_ID = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

async function createFixture() {
  const root = await mkdtemp(join(tmpdir(), "workbuddy-native-binding-test-"));
  const workspace = await realpath(await mkdir(join(root, "candidate", "workspace"), { recursive: true }).then(() => join(root, "candidate", "workspace")));
  const key = createHash("md5").update(workspace).digest("hex");
  const dataRoot = join(root, "WorkBuddyExtension", "Data");
  const historyRoot = join(dataRoot, "account", "VSCode", "identity", "history", key);
  const conversationRoot = join(historyRoot, CONVERSATION_ID);
  await mkdir(conversationRoot, { recursive: true });
  await cp(join(FIXTURE_ROOT, "workspace-index.json"), join(historyRoot, "index.json"));
  await cp(join(FIXTURE_ROOT, "conversation-index.json"), join(conversationRoot, "index.json"));
  await cp(join(FIXTURE_ROOT, "messages"), join(conversationRoot, "messages"), { recursive: true });
  return { root, workspace, dataRoot };
}

function queryResult(workspace, conversationId = CONVERSATION_ID) {
  return {
    status: "observed",
    sessions: [{
      conversation_id: conversationId,
      cwd: workspace,
      status: "Completed",
      created_at_ms: 1,
      updated_at_ms: 2,
    }],
    error: null,
  };
}

test("WorkBuddy P2 native baseline and binding use exact conversation/request/cwd", async () => {
  const fixture = await createFixture();
  try {
    const baseline = await snapshotWorkBuddyNativeBaseline({
      sessionDb: join(fixture.root, "fixture.vscdb"),
      dataRoot: fixture.dataRoot,
      workspace: fixture.workspace,
    }, {
      querySessions: async () => queryResult(fixture.workspace),
    });
    assert.deepEqual(baseline.request_ids[CONVERSATION_ID], [REQUEST_ID]);

    const selected = await selectWorkBuddyNativeBinding({
      sessionDb: join(fixture.root, "fixture.vscdb"),
      dataRoot: fixture.dataRoot,
      workspace: fixture.workspace,
      baseline: { workspace: fixture.workspace, sessions: [], request_ids: {} },
    }, {
      querySessions: async () => queryResult(fixture.workspace),
    });
    assert.equal(selected.ambiguous, false);
    assert.equal(selected.binding.session_snapshot.conversation_id, CONVERSATION_ID);
    assert.equal(selected.binding.history.binding.request_id, REQUEST_ID);
    assert.equal(selected.binding.history.prompt.content, "Create the synthetic fixture output.\n");
    assert.equal(selected.binding.history.completeness.status, "complete");
    assert.equal(selected.binding.artifacts.length, 6);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("WorkBuddy P2 native binding rejects path-escape conversation IDs", async () => {
  const fixture = await createFixture();
  try {
    await assert.rejects(
      selectWorkBuddyNativeBinding({
        sessionDb: join(fixture.root, "fixture.vscdb"),
        dataRoot: fixture.dataRoot,
        workspace: fixture.workspace,
        baseline: { workspace: fixture.workspace, sessions: [], request_ids: {} },
      }, {
        querySessions: async () => queryResult(fixture.workspace, "../escape"),
      }),
      /安全/u,
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});
